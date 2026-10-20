"""Off-policy logprob audit — /134 RL-pilot PRECONDITION 2 discriminator.

Given an episode jsonl produced by
``tools/eval/gameplay_eval_v2.py --rl-collect F --sample`` (design decision
B, documented there) and the COLLECTING checkpoint, RE-COMPUTE every owned
ask's menu log-probability from the RECORDED observation encoding alone
(no live game replay) and compare against the recorded ``logp``:

* each episode row is one seat's causal stream; a fresh ``BcAsk`` of the
  checkpoint replays its asks IN ORDER through ``menu_logprobs`` — the same
  single ``_forward_menu`` that produced them, so stream assembly and the
  per-policy digit-lane env swap (KNOWLEDGE/78) rebuild exactly;
* reports max|Δ|, mean|Δ|, share|Δ| > tol (tol default 1e-3) and RAISES on
  any breach — a silently-diverging recorded pi is exactly the /83 pi_mix
  trap (an off-policy quantity nobody re-checked). Same weights must give
  Δ ≈ float determinism; this GREEN is the gate that must hold before any
  RL gradient is trusted. Missing/tampered fields RAISE naming the trap.

Run::

    .venv/bin/python tools/training/rl_logprob_audit.py \
        --episodes FILE.jsonl --policy tools/training/bsh_S3a_s1_best.pt
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

TRAP = (
    "/83 pi_mix trap: an off-policy quantity that is never re-checked "
    "silently becomes a lie under the first weight change — audit must "
    "fail LOUD here, never pass by omission"
)


def audit(
    episodes_path: Path,
    policy: str,
    device: str = "cpu",
    tol: float = 1e-3,
) -> dict[str, Any]:
    """Recompute-and-compare every owned ask. Returns the report dict;
    RAISES RuntimeError on any integrity breach (missing/tampered field,
    idx outside the menu, zero owned rows, or |Δ| > tol anywhere)."""
    from tools.training import bc_data_v2
    from tools.training.ab_duel import BcAsk
    from tools.training.collector import AskContext

    want = str(Path(policy).resolve())
    rows = [
        json.loads(line)
        for line in episodes_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    owned = [r for r in rows if str(Path(r["policy"]).resolve()) == want]
    foreign = len(rows) - len(owned)
    if not owned:
        raise RuntimeError(
            f"rl_logprob_audit: 0/{len(rows)} episodes were collected with "
            f"{policy!r} — auditing nothing while reporting success is the " + TRAP
        )

    deltas: list[float] = []
    worst = (0.0, -1, -1, "", -1e9, -1e9)  # |d|, ep#, ask#, site, rec, rec
    for ei, ep in enumerate(owned):
        if ep.get("kind") != "rl_episode" or "rng_seed" not in ep:
            raise RuntimeError(
                f"rl_logprob_audit: episode row #{ei} is not a contracted "
                "rl_episode (needs kind + rng_seed): the collection format "
                "drifted — " + TRAP
            )
        if not ep["asks"]:
            continue  # a seat never asked this game: legitimate, reported below
        net = BcAsk.fresh(policy, device)  # fresh instance per episode = fresh stream
        for ai, a in enumerate(ep["asks"]):
            for field in ("what", "vocab", "idx", "logp", "choose"):
                if field not in a:
                    why = (
                        "choose grounding is not re-derivable without it"
                        if field == "choose"
                        else "a row that cannot anchor its own logπ cannot be audited"
                    )
                    raise RuntimeError(
                        f"rl_logprob_audit: ep#{ei} ask#{ai} has no {field!r} "
                        "key — the row predates/ breaks the /134 audit "
                        f"contract ({why}); " + TRAP
                    )
            if a["what"].startswith("choose:"):
                # re-enter the capped digest stash in EXACTLY the state
                # the collector saw (null stays null: blind stays blind)
                digest = a["what"].rsplit(":", 1)[-1]
                if a["choose"] is None:
                    bc_data_v2.stash_put(digest, None)
                else:
                    pool, expand = a["choose"]
                    bc_data_v2.stash_put(digest, [list(r) for r in pool], bool(expand))
            for field in ("what", "vocab", "idx", "logp"):
                if a.get(field) is None:
                    raise RuntimeError(
                        f"rl_logprob_audit: ep#{ei} ask#{ai} has no {field!r} "
                        "— a row that cannot anchor its own logπ cannot be "
                        "audited; " + TRAP
                    )
            cands = tuple(a["vocab"])
            if not cands:
                raise RuntimeError(
                    f"rl_logprob_audit: ep#{ei} ask#{ai} has an empty menu "
                    f"at site {a['what']!r} (encoding mismatch); " + TRAP
                )
            if not 0 <= a["idx"] < len(cands):
                raise RuntimeError(
                    f"rl_logprob_audit: ep#{ei} ask#{ai} idx {a['idx']} "
                    f"outside the recorded {len(cands)}-menu at site "
                    f"{a['what']!r} (vocab/encoding mismatch); " + TRAP
                )
            lps = net.menu_logprobs(
                AskContext(vocab=a["what"], candidates=cands, world=a["obs"])
            )
            if len(lps) != len(cands):
                raise RuntimeError(
                    f"rl_logprob_audit: ep#{ei} ask#{ai}: checkpoint scored "
                    f"{len(lps)} logits for a {len(cands)}-menu (vocab/"
                    "encoding mismatch — the audit checkpoint is not the "
                    "collecting one); " + TRAP
                )
            d = abs(float(lps[a["idx"]]) - float(a["logp"]))
            deltas.append(d)
            if d > worst[0]:
                worst = (d, ei, ai, a["what"], float(a["logp"]), float(lps[a["idx"]]))

    if not deltas:
        raise RuntimeError(
            f"rl_logprob_audit: {len(owned)} owned episodes but ZERO asks — "
            "an audit over nothing proves nothing; " + TRAP
        )
    n = len(deltas)
    breaches = sum(d > tol for d in deltas)
    report = {
        "episodes_owned": len(owned),
        "episodes_foreign": foreign,
        "asks": n,
        "max_abs_delta": max(deltas),
        "mean_abs_delta": sum(deltas) / n,
        "share_gt_tol": breaches / n,
        "tol": tol,
        "worst": {
            "abs_delta": worst[0],
            "episode": worst[1],
            "ask": worst[2],
            "site": worst[3],
            "recorded_logp": worst[4],
            "recomputed_logp": worst[5],
        },
    }
    if breaches:
        raise RuntimeError(
            f"rl_logprob_audit: OFF-POLICY MISMATCH — {breaches}"
            f" of {n} asks exceed tol={tol} "
            f"(max|Δ|={report['max_abs_delta']:.6g} at ep#{worst[1]} "
            f"ask#{worst[2]} site {worst[3]!r}: recorded {worst[4]:.6g} vs "
            f"recomputed {worst[5]:.6g}). The recorded logπ does NOT come "
            "from the checkpoint under audit — " + TRAP
        )
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--episodes", type=Path, required=True)
    ap.add_argument("--policy", required=True, help="collecting checkpoint .pt")
    ap.add_argument("--device", default="cpu", choices=("auto", "cpu", "cuda"))
    ap.add_argument("--tol", type=float, default=1e-3)
    args = ap.parse_args(argv)
    rep = audit(args.episodes, args.policy, args.device, args.tol)
    print(json.dumps(rep, indent=1))
    print(
        f"rl_logprob_audit GREEN: {rep['asks']} asks / "
        f"{rep['episodes_owned']} episodes | max|Δ|={rep['max_abs_delta']:.3g} "
        f"mean|Δ|={rep['mean_abs_delta']:.3g} "
        f"share|Δ|>{args.tol:g}={rep['share_gt_tol']:.4f} "
        f"(foreign-policy rows skipped: {rep['episodes_foreign']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
