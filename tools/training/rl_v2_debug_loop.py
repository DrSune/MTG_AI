"""RL v2 ON-POLY debug loop — the 5-iteration DISCARDED run pre-registered
in RL_V2_DEBUG_PRE_REGISTRATION.md (mechanics checklist only; no strength
claim; everything trained here is thrown away — today's engine is
known-broken, real runs wait for the era-boundary merge, /176 + plan
Step 4 item 7).

Loop (owner spec): collect G = 50 FRESH games with the CURRENT policy
against the FROZEN anchor (mirror matchup, --rl-collect records the
learner seat's sampled asks), then ONE PPO update over that batch, save,
repeat. Warm-start of the value head happens ONCE, up front, on the
recorded pilot episodes (the spec's "warm-start it on recorded games
before the first policy update").

Memory law (AGENTS.md 0, post-reboot): --device defaults to cpu; while
vLLM is resident, no CUDA. The trainer's assert_cuda_headroom is the
hard guard.

Collection runs in the MAIN repo (the pinned tree, fingerprint
31b3b78c..., "today's engine") as a subprocess; the trainer side runs
from this worktree (tools/training/train_rl_v2). The learner rows are
selected by the v1 episode guard (row.policy SHA == the collecting
checkpoint), so the frozen anchor's own rows are skipped automatically.

Seeds: iteration i uses seed-base --seed-base + i*1000 (50 games each),
--dps-base + i, --rlseed-base + i. Fresh blocks, disjoint from every
consumed block (pilot 510201+/511xxx/512002; /172 reserves 513001-
515501 and probes 516001-518001; this loop starts at 520001). The
summary file lists the exact blocks consumed.

Run (from the worktree, main-repo default below):
    .venv/bin/python tools/training/rl_v2_debug_loop.py \
        --anchor /home/sune/Desktop/MTG_AI/tools/training/bsh_S3a_s1_best.pt \
        --episodes /tmp/opencode/rld_n1/episodes_iter1.jsonl \
        --out-dir /tmp/opencode/rld_v2dbg
"""

from __future__ import annotations

import argparse
import json
import math
import random
import subprocess
import sys
from pathlib import Path

from tools.training import train_rl_v2 as T

MAIN_REPO = Path("/home/sune/Desktop/MTG_AI")


def log(msg: str) -> None:
    print(f"[rlv2dbg] {msg}", flush=True)


def collect_iteration(
    venv_python: Path,
    main_repo: Path,
    policy_a: str,
    anchor: str,
    games: int,
    workers: int,
    seed_base: int,
    dps: int,
    rl_seed: int,
    episodes_out: Path,
    collect_out: Path,
) -> None:
    """One fresh G-game collection: learner (policy_a) vs frozen anchor,
    mirror matchup, sampled asks recorded (temperature-1, the spec's
    only exploration). Runs in the MAIN repo on the pinned tree."""
    cmd = [
        str(venv_python),
        "-m",
        "tools.eval.gameplay_eval_v2",
        "--policy-a",
        policy_a,
        "--policy-b",
        anchor,
        "--matchups",
        "mirror",
        "--games",
        str(games),
        "--workers",
        str(workers),
        "--pool",
        "engine",
        "--device",
        "cpu",  # memory law: collection is CPU (net forwards ~95% of wall)
        "--sample",
        "--rl-collect",
        str(episodes_out),
        "--rl-seed",
        str(rl_seed),
        "--seed-base",
        str(seed_base),
        "--deck-pairs-seed",
        str(dps),
        "--out",
        str(collect_out),
    ]
    log(
        f"collect: {games}g seed-base={seed_base} dps={dps} rl-seed={rl_seed} "
        f"policy_a={Path(policy_a).name}"
    )
    r = subprocess.run(cmd, cwd=str(main_repo), capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(
            f"rlv2dbg: collection failed rc={r.returncode}\n"
            f"--- stderr tail ---\n{r.stderr[-3000:]}"
        )
    rows = sum(
        1
        for line in episodes_out.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )
    if rows != 2 * games:
        raise RuntimeError(
            f"rlv2dbg: expected {2 * games} episode rows (one per sampled "
            f"seat), got {rows} — collection rig drift"
        )


def checklist_row(line: dict, draws: int, completed: bool) -> dict:
    """Evaluate the pre-registration mechanics checklist for ONE update
    line (items 1-6 of RL_V2_DEBUG_PRE_REGISTRATION.md). Item 2 reads the
    early-stop consistently: the threshold is 'respected' when either the
    running KL stayed under it or the update early-stopped AT it."""
    ev = line["value_explained_variance"]
    kl = line["kl_per_update"]
    ent = line["entropy_mean"]
    scalars = [
        line["policy_loss"],
        line["value_loss"],
        line["advantage_mean"],
        line["advantage_std"],
        kl,
        ent,
        line["grad_norm_preclip"],
        line["chosen_dlogp_post"],
    ]
    finite = all(math.isfinite(s) for s in scalars)
    return {
        "1_value_ev_gt_0": ev > 0.0,
        "2_kl_moved_and_in_budget": (
            kl > 1e-6 and (kl <= 0.01 or line["early_stopped"])
        ),
        "3_entropy_0p02_to_0p5": 0.02 <= ent <= 0.5,
        "4_no_nans": finite,
        "5_no_trainer_crash": completed,
        "6_draw_rate_logged": "draws" in line,
        "draws": draws,
        "kl": kl,
        "entropy": ent,
        "ev": ev,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--anchor", required=True, help="frozen anchor .pt (read-only)")
    ap.add_argument(
        "--episodes",
        required=True,
        type=Path,
        help="recorded pilot episodes (1000g) for the warm-start",
    )
    ap.add_argument("--main-repo", type=Path, default=MAIN_REPO)
    ap.add_argument("--iters", type=int, default=5)
    ap.add_argument("--games", type=int, default=50)
    ap.add_argument("--seed-base", type=int, default=520001)
    ap.add_argument("--dps-base", type=int, default=1500)
    ap.add_argument("--rlseed-base", type=int, default=4300)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--out-dir", type=Path, default=Path("/tmp/opencode/rld_v2dbg"))
    ap.add_argument("--device", default="cpu", choices=("cpu", "cuda"))
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--lr", type=float, default=3e-4)
    ap.add_argument("--value-lr", type=float, default=1e-3)
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--minibatch", type=int, default=256)
    ap.add_argument("--gae-lambda", type=float, default=0.95)
    ap.add_argument("--kl-stop", type=float, default=T.DEFAULT_KL_STOP)
    ap.add_argument("--grad-clip", type=float, default=T.DEFAULT_GRAD_CLIP)
    ap.add_argument("--ratio-clip", type=float, default=0.2)
    ap.add_argument("--value-coef", type=float, default=0.5)
    ap.add_argument("--ev-games", type=int, default=200)
    ap.add_argument("--warm-start-games", type=int, default=500)
    args = ap.parse_args(argv)

    venv_python = MAIN_REPO / ".venv" / "bin" / "python"
    anchor = str(Path(args.anchor).resolve())

    blob = T.load_blob(anchor)
    schema = str(blob.get("schema", "v1"))
    vocab = blob["vocab"]
    max_len = int(blob["config"]["max_len"])
    policy_model = T.load_policy(blob, args.device, train=True)
    anchor_model = T.build_anchor(T.load_blob(anchor), args.device)

    # ---- warm-start (once, on the recorded episodes; spec item 2) ----
    eps = T.load_episodes(args.episodes, anchor, offline=True)
    rng = random.Random(args.seed)
    order = list(range(len(eps)))
    rng.shuffle(order)
    ev_idx, warm_idx, _pool = T._carve_games(
        order, args.ev_games, args.warm_start_games, 0
    )
    ws = T.warm_start_value(
        policy_model,
        [eps[i] for i in warm_idx],
        vocab,
        max_len,
        schema,
        args.device,
        lr=args.value_lr,
        minibatch=args.minibatch,
        seed=args.seed,
    )
    ev_holdout = T.measure_value_ev(
        policy_model,
        [eps[i] for i in ev_idx],
        vocab,
        max_len,
        schema,
        args.device,
        args.minibatch,
    )
    log(
        f"warm-start: {ws['decisions']} decisions / {ws['games']} games, "
        f"held-out EV = {ev_holdout:.4f} on {len(ev_idx)} games"
    )
    if ev_holdout <= 0.0:
        raise RuntimeError(
            f"rlv2dbg: warm-start held-out EV {ev_holdout:.4f} <= 0 — "
            "triage rule #1, aborting before any update"
        )

    # ---- the loop ----
    args.out_dir.mkdir(parents=True, exist_ok=True)
    rows_log: list[dict] = []
    seed_blocks: list[str] = []
    ckpt_collect = anchor  # iteration 0 collects from the anchor itself
    all_ok = True
    for i in range(args.iters):
        tag = f"rlv2dbg_i{i + 1}"
        seed_base = args.seed_base + i * 1000
        seed_blocks.append(
            f"{seed_base}-{seed_base + args.games - 1} (dps "
            f"{args.dps_base + i}, rl-seed {args.rlseed_base + i})"
        )
        epi = args.out_dir / f"episodes_i{i + 1}.jsonl"
        collect_out = args.out_dir / f"collect_i{i + 1}.json"
        collect_iteration(
            venv_python,
            args.main_repo,
            ckpt_collect,
            anchor,
            args.games,
            args.workers,
            seed_base,
            args.dps_base + i,
            args.rlseed_base + i,
            epi,
            collect_out,
        )
        rows = T.load_episodes(epi, ckpt_collect, offline=False)
        if len(rows) < args.games:
            raise RuntimeError(
                f"rlv2dbg: iteration {i + 1}: only {len(rows)} learner rows "
                f"after the episode guard (expected {args.games})"
            )
        dec: list[dict] = []
        offsets: list[int] = []
        for ep in rows:
            offsets.append(len(dec))
            dec.extend(T.encode_episode(ep, policy_model, vocab, max_len, schema))
        log(
            f"iter {i + 1}: {len(rows)} learner games -> {len(dec)} decisions; "
            "PPO update (device=" + args.device + ")"
        )
        u = T.ppo_update(
            policy_model,
            anchor_model,
            dec,
            offsets,
            epochs=args.epochs,
            minibatch=args.minibatch,
            lr=args.lr,
            value_lr=args.value_lr,
            ratio_clip=args.ratio_clip,
            kl_stop=args.kl_stop,
            grad_clip=args.grad_clip,
            value_coef=args.value_coef,
            gae_lambda=args.gae_lambda,
            seed=args.seed + 1000 * (i + 1),
            device=args.device,
        )
        line = {
            "iter": i + 1,
            "tag": tag,
            "device": args.device,
            "games": len(rows),
            "wins": sum(1 for e in rows if e["outcome"] == "win"),
            "losses": sum(1 for e in rows if e["outcome"] == "loss"),
            "draws": sum(1 for e in rows if e["outcome"] == "draw"),
            "crashes": sum(1 for e in rows if e["outcome"] == "crash"),
            "asks": u["decisions"],
            "policy_loss": u["policy_loss"],
            "value_loss": u["value_loss"],
            "value_explained_variance": u["value_explained_variance"],
            "advantage_mean": u["advantage_mean"],
            "advantage_std": u["advantage_std"],
            "entropy_mean": u["entropy_mean"],
            "kl_per_update": u["kl_per_update"],
            "grad_norm_preclip": u["grad_norm_preclip"],
            "grad_norm_max": u["grad_norm_max"],
            "epochs_run": u["epochs_run"],
            "epochs_planned": u["epochs"],
            "early_stopped": u["early_stopped"],
            "chosen_dlogp_post": u["chosen_dlogp_post"],
        }
        print(json.dumps(line), flush=True)
        rows_log.append(line)
        T.save_ckpt(
            policy_model,
            blob,
            tag,
            args.out_dir,
            {"tag": tag, "iter": i + 1, "updates": [line]},
            schema,
        )
        ckpt_collect = str(args.out_dir / f"{tag}_policy.pt")
        chk = checklist_row(line, line["draws"], completed=True)
        ok = all(v for k, v in chk.items() if isinstance(v, bool))
        all_ok = all_ok and ok
        failed = {k: chk[k] for k, v in chk.items() if isinstance(v, bool) and not v}
        log(
            f"iter {i + 1}: KL={u['kl_per_update']:.2e} "
            f"ent={u['entropy_mean']:.3f} ev={u['value_explained_variance']:.4f} "
            f"checklist={'PASS' if ok else 'FAIL: ' + str(failed)} "
            f"checkpointed {tag}_policy.pt"
        )

    summary = {
        "kind": "rl_v2_debug_loop_summary",
        "discarded": True,
        "note": "mechanics checklist only — no strength claim; trained on "
        "today's known-broken engine, thrown away (pre-registration)",
        "anchor": anchor,
        "device": args.device,
        "warm_start": ws,
        "value_ev_holdout": ev_holdout,
        "ev_games": len(ev_idx),
        "iterations": len(rows_log),
        "seed_blocks_consumed": seed_blocks,
        "all_checklist_items_pass": all_ok,
        "updates": rows_log,
    }
    (args.out_dir / "rlv2_dbg_summary.json").write_text(
        json.dumps(summary, indent=1), encoding="utf-8"
    )
    log(
        f"DONE: {len(rows_log)} iterations, "
        f"all checklist items pass = {all_ok} "
        f"(summary -> {args.out_dir / 'rlv2_dbg_summary.json'})"
    )
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
