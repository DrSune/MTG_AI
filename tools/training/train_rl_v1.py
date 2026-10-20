"""REINFORCE trainer — /134 RL-pilot TASK B (owner GO 2026-10-20).

Pre-registered objective (/134 design v2 + /137, do not deviate):

    loss = -mean_over_games[(R_g - batchmean(R)) * SUM_owned_asks logpi(a)]
           + beta * mean_over_games(mean_over_asks KL(pi_cur || pi_anchor))
           - entropy_coef * mean_over_asks entropy(pi_cur)

* R per game from the COLLECTING seat's row field ``outcome``:
  win +1 / loss -1 / draw 0; ``crash`` counts as a loss (rig convention,
  cited r1_window 8/200 in /134 N1).
* pi_anchor = a FROZEN second copy of the anchor checkpoint
  (``--anchor``, default ``--policy``). Iteration 1 passes both = base;
  later iterations pass ``--policy rld_iN.pt --anchor <base>`` so the KL
  anchor stays the PRE-RL clone (cumulative-KL gate F4).
* Batch law: ONE iterations-file = one batch = ONE update (batch-1 law:
  no best-loss selection). Save = ``<tag>.pt`` + ``<tag>_diag.json``.

Recompute purity (the pilot's validity): logpi is recomputed through
``BcAsk._forward_menu(..., grad=True)`` — the EXACT encoding forward that
produced the recorded logp (same stream assembly, same per-policy
digit-lane swap, same candidate grounding and choose-stash re-entry as
rl_logprob_audit). Nothing here re-implements encoding.

NOTE (documented interpretations, not deviations of the objective):
* Optimizer is plain SGD. The pre-registration names LR 1e-5 + grad-clip
  but not the optimizer; Adam-style per-parameter scaling (lr*g/(sqrt(v)+
  eps)) amplifies the zero/float-noise gradient floor by ~1/eps and would
  destroy the F4 zero-variance no-op discriminator, so SGD is the only
  choice consistent with the mandated diagnostics.
* F4 diagnostics are the NO-OP DISCRIMINATOR: flat traces mean "no
  learning occurred" (pipeline), NEVER "lever negative" (/134 F4).

Run::

    .venv/bin/python tools/training/train_rl_v1.py \
        --episodes FILE.jsonl --policy tools/training/bsh_S3a_s1_best.pt \
        --tag rld_i1 [--anchor CKPT] [--device cpu|cuda] [--max-asks N]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

REWARD = {"win": 1.0, "loss": -1.0, "draw": 0.0, "crash": -1.0}
F4_KEYS = (
    "mean_abs_dlogp_chosen",
    "kl_mean_per_game",
    "entropy_mean",
    "grad_norm_preclip",
    "share_dlogp_gt_0p1",
    "reward_var",
)


def load_episodes(episodes_path: Path, policy: str) -> list[dict[str, Any]]:
    """Owned rl_episode rows with fail-loud contract checks: foreign-only
    file, non-episode rows, MISSING outcome, ask-row shape drift, empty
    menu, idx outside menu. (Recorded-logp correctness itself is
    rl_logprob_audit's gate, run by the harness before this trainer.)"""
    want = str(Path(policy).resolve())
    rows = [
        json.loads(line)
        for line in episodes_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    owned = [r for r in rows if str(Path(r["policy"]).resolve()) == want]
    if not owned:
        raise RuntimeError(
            f"train_rl_v1: 0/{len(rows)} episodes were collected with "
            f"{policy!r} — an update over nothing proves nothing"
        )
    for ei, ep in enumerate(owned):
        if ep.get("kind") != "rl_episode":
            raise RuntimeError(
                f"train_rl_v1: row #{ei} is not kind=rl_episode — collection "
                "format drift"
            )
        if ep.get("outcome") not in REWARD:
            raise RuntimeError(
                f"train_rl_v1: row #{ei} has outcome={ep.get('outcome')!r} "
                "— REINFORCE outcome reward is unanchored; rows predate the "
                "TASK B outcome field or the rig drifted (no silent default)"
            )
        for ai, a in enumerate(ep["asks"]):
            missing = {"what", "vocab", "idx", "logp", "choose"} - set(a)
            if missing:
                raise RuntimeError(
                    f"train_rl_v1: ep#{ei} ask#{ai} missing keys "
                    f"{sorted(missing)} — ask-row shape drift"
                )
            if not a["vocab"]:
                raise RuntimeError(
                    f"train_rl_v1: ep#{ei} ask#{ai} empty menu at {a['what']!r}"
                )
            if not 0 <= a["idx"] < len(a["vocab"]):
                raise RuntimeError(
                    f"train_rl_v1: ep#{ei} ask#{ai} idx {a['idx']} outside "
                    f"the {len(a['vocab'])}-menu at {a['what']!r}"
                )
    return owned


def _reenter_stash(bc_data_v2: Any, a: dict[str, Any]) -> None:
    """Replay the collector's digest-stash state exactly as
    rl_logprob_audit does (null stays null: blind stays blind)."""
    if a["what"].startswith("choose:"):
        digest = a["what"].rsplit(":", 1)[-1]
        if a["choose"] is None:
            bc_data_v2.stash_put(digest, None)
        else:
            pool, expand = a["choose"]
            bc_data_v2.stash_put(digest, [list(r) for r in pool], bool(expand))


def train(
    episodes: Path,
    policy: str,
    anchor: str | None = None,
    device: str = "cpu",
    tag: str = "rld_i1",
    out_dir: Path | None = None,
    lr: float = 1e-5,
    clip: float = 1.0,
    beta: float = 0.1,
    entropy_coef: float = 0.001,
    kl_ceiling: float = 0.05,
    max_asks: int = 0,
    kl_post_check: bool = True,
    save: bool = True,
) -> dict[str, Any]:
    """One REINFORCE update over the file's owned episodes; returns the F4
    diagnostic dict and writes <tag>.pt + <tag>_diag.json (save=True)."""
    import torch

    from tools.training import bc_data_v2
    from tools.training.ab_duel import BcAsk
    from tools.training.bc_model import PointerBC
    from tools.training.collector import AskContext

    anchor = anchor or policy

    eps = load_episodes(episodes, policy)
    dropped = 0
    if max_asks > 0:
        # TEST GUARD ONLY (never in a pilot run): cap asks per game to a
        # leading PREFIX of each owned causal stream — a prefix replays
        # byte-identically through BcAsk — while every game keeps its
        # outcome, so the batch-mean baseline stays non-trivial.
        per_game = max(1, max_asks // len(eps))
        eps = [dict(ep, asks=list(ep["asks"])[:per_game]) for ep in eps]
        dropped = sum(1 for ep in eps if len(ep["asks"]) == per_game)
        if not any(ep["asks"] for ep in eps):
            raise RuntimeError(
                f"train_rl_v1: --max-asks={max_asks} left zero asks — nothing "
                "to train on"
            )

    blob = torch.load(policy, map_location=device, weights_only=False)
    schema = str(blob.get("schema", "v1"))
    vocab = blob["vocab"]
    if schema == "v2":
        bc_data_v2.install_choose_stash()

    def build(frozen: bool) -> Any:
        m = PointerBC(**blob["config"])
        m.load_state_dict(blob["state"])
        m.to(device)
        for p in m.parameters():
            p.requires_grad_(not frozen)
        m.eval()  # no dropout: recomputed logpi == collected logpi
        return m

    model, anchor_model = build(False), build(True)
    max_len = model.max_len

    G = len(eps)  # batch-mean baseline over the iteration's games
    rs = [REWARD[ep["outcome"]] for ep in eps]
    r_mean = sum(rs) / G
    r_var = sum((r - r_mean) ** 2 for r in rs) / G
    adv = [r - r_mean for r in rs]
    ask_eps = [ep for ep in eps if ep["asks"]]
    Gk = len(ask_eps)  # KL/entropy are per-game means over games WITH asks

    model.zero_grad(set_to_none=True)
    pg_sum = kl_sum = ent_sum = loss_sum = 0.0
    n_asks = n_big = 0
    dlogs: list[float] = []
    kl_games: list[float] = []
    ents: list[float] = []
    anchor_menu_lps: list[list[list[float]]] = []  # cached for post-KL

    for gi, ep in enumerate(eps):
        cur = BcAsk(model, vocab, max_len, schema)
        anc = BcAsk(anchor_model, vocab, max_len, schema)
        n_a = len(ep["asks"])
        if n_a == 0:
            continue  # seat never asked: contributes 0 to every term
        w_pg = -adv[gi] / G  # per-ask weight: sum over asks == game's term
        w_kl = beta / (Gk * n_a)
        w_ent = -entropy_coef / (Gk * n_a)
        live = w_pg != 0.0 or w_kl != 0.0 or w_ent != 0.0
        g_kl: list[float] = []
        ep_anchor_lps: list[list[float]] = []
        for a in ep["asks"]:
            ctx = AskContext(
                vocab=a["what"], candidates=tuple(a["vocab"]), world=a["obs"]
            )
            _reenter_stash(bc_data_v2, a)
            logits = cur._forward_menu(torch, ctx, grad=live)
            lp = torch.log_softmax(logits.float()[0], dim=-1)
            if lp.numel() != len(a["vocab"]):
                raise RuntimeError(
                    f"train_rl_v1: checkpoint scored {lp.numel()} logits for "
                    f"a {len(a['vocab'])}-menu (ep#{gi} {a['what']!r}) — "
                    "vocab/encoding mismatch"
                )
            _reenter_stash(bc_data_v2, a)  # same digest re-read by anc
            with torch.no_grad():
                lp_a = torch.log_softmax(
                    anc._forward_menu(torch, ctx).float()[0], dim=-1
                )
            p = lp.exp()
            kl = (p * (lp - lp_a)).sum()
            ent = -(p * lp).sum()
            if live:
                loss = w_pg * lp[a["idx"]] + w_kl * kl + w_ent * ent
                loss.backward()
            lp_i = float(lp[a["idx"]].detach())
            kl_i = float(kl.detach())
            ent_i = float(ent.detach())
            pg_sum += w_pg * lp_i
            kl_sum += w_kl * kl_i
            ent_sum += w_ent * ent_i
            loss_sum += w_pg * lp_i + w_kl * kl_i + w_ent * ent_i
            dlogs.append(abs(lp_i - float(lp_a[a["idx"]])))
            n_big += dlogs[-1] > 0.1
            g_kl.append(kl_i)
            ents.append(ent_i)
            ep_anchor_lps.append(lp_a.detach().cpu().tolist())
            n_asks += 1
        kl_games.append(sum(g_kl) / len(g_kl))
        anchor_menu_lps.append(ep_anchor_lps)

    grad_pre = float(torch.nn.utils.clip_grad_norm_(model.parameters(), clip))
    opt = torch.optim.SGD(model.parameters(), lr=lr)
    opt.step()
    opt.zero_grad(set_to_none=True)

    kl_post: float | None = None
    if kl_post_check:
        # cumulative/post-step KL vs the SAME frozen anchor (F4 ceiling is
        # about where the policy LANDS, not just what it planned).
        games_post: list[float] = []
        with torch.no_grad():
            for ep, ep_anc in zip(ask_eps, anchor_menu_lps):
                cur = BcAsk(model, vocab, max_len, schema)
                per_ask: list[float] = []
                for a, anc_lps in zip(ep["asks"], ep_anc):
                    ctx = AskContext(
                        vocab=a["what"],
                        candidates=tuple(a["vocab"]),
                        world=a["obs"],
                    )
                    _reenter_stash(bc_data_v2, a)
                    lp = torch.log_softmax(
                        cur._forward_menu(torch, ctx).float()[0], dim=-1
                    )
                    # anchor log-probs were cached as plain lists (.cpu().
                    # tolist()): rebuild on the LIVE tensor's device or the
                    # subtraction below fails on cuda (night-1 crash).
                    t_anc = torch.tensor(anc_lps, dtype=torch.float32, device=lp.device)
                    per_ask.append(float((lp.exp() * (lp - t_anc)).sum()))
                games_post.append(sum(per_ask) / len(per_ask))
        kl_post = sum(games_post) / len(games_post)

    n = max(n_asks, 1)
    diag: dict[str, Any] = {
        "tag": tag,
        "policy": str(Path(policy).resolve()),
        "anchor": str(Path(anchor).resolve()),
        "device": device,
        "lr": lr,
        "beta": beta,
        "entropy_coef": entropy_coef,
        "clip": clip,
        "max_asks": max_asks,
        "episodes_owned": len(eps),
        "episodes_truncated_by_max_asks": dropped,
        "games": G,
        "games_with_asks": Gk,
        "asks": n_asks,
        "crashes": sum(1 for ep in eps if ep["outcome"] == "crash"),
        # ---- F4 no-op discriminator (all six mandated keys) ----
        "mean_abs_dlogp_chosen": sum(dlogs) / n,
        "kl_mean_per_game": sum(kl_games) / max(len(kl_games), 1),
        "entropy_mean": sum(ents) / n,
        "grad_norm_preclip": grad_pre,
        "share_dlogp_gt_0p1": n_big / n,
        "reward_var": r_var,
        # ---- reported loss decomposition (sums match total) ----
        "pg_loss": pg_sum,
        "kl_loss": kl_sum,
        "entropy_loss": ent_sum,
        "total_loss": loss_sum,
        "grad_norm_postclip": min(grad_pre, clip),
        "kl_mean_per_game_post": kl_post,
        "kl_ceiling": kl_ceiling,
        "kl_ceiling_breach": (kl_post is not None and kl_post > kl_ceiling),
    }
    for k in F4_KEYS:
        assert k in diag  # sidecar schema law: a missing key IS the no-op

    if save:
        out_dir = Path(out_dir or episodes.parent)
        out_dir.mkdir(parents=True, exist_ok=True)
        torch.save(
            {
                "schema": schema,
                "state": {k: v.cpu() for k, v in model.state_dict().items()},
                "config": blob["config"],
                "vocab": vocab,
                "seed": int(blob.get("seed", 0)),
                "train_info": {
                    "kind": "reinforce_v1",
                    "iter": tag,
                    "episodes": str(Path(episodes).resolve()),
                    "diag": diag,
                },
            },
            out_dir / f"{tag}.pt",
        )
        (out_dir / f"{tag}_diag.json").write_text(
            json.dumps(diag, indent=1), encoding="utf-8"
        )
    if diag["kl_ceiling_breach"]:
        print(
            f"train_rl_v1 LOUD: mean-KL/game AFTER update = {kl_post:.4f} "
            f"exceeds ceiling {kl_ceiling} — policy is moving off the BC "
            "anchor too fast (F4): raise beta / halt iteration chain.",
            file=sys.stderr,
        )
    return diag


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--episodes", type=Path, required=True)
    ap.add_argument("--policy", required=True, help="checkpoint to train")
    ap.add_argument("--anchor", default=None, help="frozen KL anchor")
    ap.add_argument("--device", default="cpu", choices=("cpu", "cuda"))
    ap.add_argument("--tag", default="rld_i1")
    ap.add_argument("--out-dir", type=Path, default=None)
    ap.add_argument("--lr", type=float, default=1e-5)
    ap.add_argument("--clip", type=float, default=1.0)
    ap.add_argument("--beta", type=float, default=0.1)
    ap.add_argument("--entropy-coef", type=float, default=0.001)
    ap.add_argument("--kl-ceiling", type=float, default=0.05)
    ap.add_argument(
        "--max-asks",
        type=int,
        default=0,
        help="cap asks per update (whole episodes, leading order); 0=off",
    )
    ap.add_argument("--no-kl-post-check", action="store_true", help="skip post-step KL")
    args = ap.parse_args(argv)
    diag = train(
        args.episodes,
        args.policy,
        anchor=args.anchor,
        device=args.device,
        tag=args.tag,
        out_dir=args.out_dir,
        lr=args.lr,
        clip=args.clip,
        beta=args.beta,
        entropy_coef=args.entropy_coef,
        kl_ceiling=args.kl_ceiling,
        max_asks=args.max_asks,
        kl_post_check=not args.no_kl_post_check,
    )
    print(json.dumps(diag, indent=1))
    print(
        f"train_rl_v1 [{args.tag}]: {diag['games']}g/{diag['asks']} asks | "
        f"grad={diag['grad_norm_preclip']:.4g} "
        f"KL={diag['kl_mean_per_game']:.4g} "
        f"|dlogp|={diag['mean_abs_dlogp_chosen']:.4g} "
        f"Rvar={diag['reward_var']:.4g}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
