"""Head-to-head inside the LEGACY rig: a tools/selfplay checkpoint against the old PointerBC
anchor or the old HeuristicTeacher, through ``tools/eval/gameplay_eval_v2.run_v2_game``.

The legacy side is untouched: it sees exactly the omniscient input it was trained on, its auto-
tapped act menu and its own seat routing. Only the new model goes through an adapter: its act
tokens are rebuilt from the rig's ``_lands`` / ``_acts`` lists (``card:N`` -> ``land:card:N``,
``cast:card:N[:k]``, ``act:card:N:0``), its features come from the live executor for the seat the
rig names, and it never gets the combat/scry context the new rig adds. So the adapter can only
handicap the new model.

    .venv/bin/python -m tools.selfplay.vs_legacy --new runs/selfplay/X/best.pt \
        --old teacher --games 200 --workers 4
"""

from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import os
import sys
from collections import Counter
from typing import Any

_STATE: dict[str, Any] = {}


def _init(new_path: str, seed_base: int) -> None:
    import torch

    torch.set_num_threads(1)  # one forward per decision: a thread pool only churns threads
    torch.set_num_interop_threads(1)
    from tools.eval import gameplay_eval_v2 as G
    from tools.selfplay import model as M

    model, table, _ = M.load(new_path, "cpu")
    model.eval()
    _STATE.update(model=model, table=table, seed_base=seed_base)
    orig_setup = G._setup_game

    def setup(*a: Any, **kw: Any) -> Any:
        game = orig_setup(*a, **kw)
        _STATE["game"] = game
        return game

    G._setup_game = setup
    orig_make = G.make_eval_policy

    def make(spec: str, seat_seed: int, device: str) -> Any:
        if spec == "NEW":
            return Adapter()
        return orig_make(spec, seat_seed, device)

    G.make_eval_policy = make


class Adapter:
    truncations = 0

    def decide(self, ctx: Any) -> int:
        import torch

        from MTG_bot.bench.protocol import Ask, Option, ask_kind
        from tools.selfplay import features as FT
        from tools.selfplay import model as M

        cands = list(ctx.candidates)
        if len(cands) == 1:
            return 0
        what = ctx.vocab
        kind = ask_kind(what)
        world = ctx.world
        if kind == "act":
            lands, acts = set(world.get("_lands", [])), set(world.get("_acts", []))
            toks = []
            for c in cands:
                if c == "PASS":
                    toks.append(c)
                elif c in lands:
                    toks.append(f"land:{c}")
                elif c in acts:
                    toks.append(f"act:{c}:0")
                elif c.endswith("+kick"):
                    toks.append(f"cast:{c[:-5]}:k")
                else:
                    toks.append(f"cast:{c}")
        else:
            toks = cands
        refuse = next((i for i, t in enumerate(cands) if t in ("PASS", "NONE", "DECLINE", "skip")),
                      None)
        if len(toks) > FT.MAX_OPTIONS or kind == "name":
            return next((i for i in range(len(cands)) if i != refuse), 0)
        seat = int(world["_seat"])
        ask = Ask(seat=seat, kind=kind, site=what, prompt="",
                  options=tuple(Option(t, t) for t in toks), refuse=refuse)
        ex = _STATE["game"].executor
        feats = FT.encode(ex, seat, ask, _STATE["table"], FT.AskContext())
        with torch.no_grad():
            logits, _ = _STATE["model"](M.collate([feats], "cpu"))
        return int(logits.argmax(-1)[0])


def _play(job: tuple[int, bool, str, str]) -> dict:
    from MTG_bot.core.executor.games import get_supply
    from tools.eval import gameplay_eval_v2 as G

    seed, swap, old, old_device = job
    supply = get_supply("castable")
    r = G.run_v2_game(seed, swap, "NEW", old, supply, device=old_device)
    return {"seed": seed, "swap": swap, "outcome": r["outcome"], "turns": r["turns"],
            "crash": r.get("crash")}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--new", required=True, help="tools/selfplay checkpoint")
    ap.add_argument("--old", default="teacher",
                    help="'teacher' or a legacy checkpoint path (e.g. tools/training/bsh_S3a_s1_best.pt)")
    ap.add_argument("--games", type=int, default=200, help="deals; each is played twice, seats swapped")
    ap.add_argument("--seed-base", type=int, default=991001)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--old-device", default="cpu", choices=("cpu", "cuda"),
                    help="device of a legacy checkpoint (its 1024-token stream is slow on 1 CPU thread)")
    ap.add_argument("--out", default="")
    args = ap.parse_args(argv)
    jobs = [(args.seed_base + i, swap, args.old, args.old_device) for i in range(args.games)
            for swap in (False, True)]
    # libgomp otherwise starts one spin-waiting thread per core in every worker: measured ~4.7x
    # the useful CPU burnt in idle spinning. Spawned workers inherit the environment.
    os.environ["OMP_NUM_THREADS"] = "1"
    os.environ["OMP_WAIT_POLICY"] = "PASSIVE"
    ctx = mp.get_context("spawn")
    with ctx.Pool(args.workers, initializer=_init, initargs=(args.new, args.seed_base)) as pool:
        rows = pool.map(_play, jobs, chunksize=2)
    out = Counter(r["outcome"] for r in rows)
    decided = [r for r in rows if r["outcome"] != "crash"]
    score = sum(1.0 if r["outcome"] == "a" else 0.5 if r["outcome"].startswith("draw") else 0.0
                for r in decided)
    n = len(decided)
    from tools.selfplay.learner import wilson

    summary = {"new": args.new, "old": args.old, "games": len(rows), "outcomes": dict(out),
               "new_score": round(score / max(n, 1), 4), "ci95": wilson(score, n),
               "turns": round(sum(r["turns"] for r in decided) / max(n, 1), 1),
               "seed_base": args.seed_base, "rig": "tools/eval/gameplay_eval_v2.run_v2_game castable"}
    print(json.dumps(summary))
    if args.out:
        with open(args.out, "a") as fh:
            fh.write(json.dumps(summary) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
