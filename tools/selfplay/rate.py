"""The held-out pool and its frozen ratings (docs/PLAN_CEILING.md §7.2): L, a player's Elo against
opponents that never appear in a training league, rated once and then held fixed.

Every input is an evaluation run (``learner.py --eval-only``): its "eval" seat is the network
``--init``, its opponent ``--opp-ckpt`` (as ``snap:opp``) or a scripted player (``heuristic``,
``random``), and each deal is played twice with the seats swapped. A seat that searches
(``eval+search``, ``snap:opp+search``) is its own member, named with its search: the same
network raw and searched are two players (the pool holds r27's v0 plus search, §7.2).

- ``fit POOL.json RUN...``: Bradley-Terry ratings of the pool's members from games among them
  (``learner.fit_elo``, uniform random play = 0 when it is a member, else the first by name),
  once.
  A member is a checkpoint path or a scripted player's name.
- ``rate POOL.json RUN...``: one player's Elo against the frozen ratings, by maximum likelihood,
  with a 95% interval from a bootstrap over deals (the deal is the independent unit). A joint
  refit would move every rating whenever the pool grows; held fixed, two players rated a week
  apart stay comparable.

    .venv/bin/python -m tools.selfplay.rate fit runs/pool/pool.json runs/pool/rr_*
    .venv/bin/python -m tools.selfplay.rate rate runs/pool/pool.json runs/selfplay/NAME_vs_*
"""

from __future__ import annotations

import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

from tools.selfplay.actor import SEARCH_SUFFIX
from tools.selfplay.learner import fit_elo

SCRIPTED = ("heuristic", "random")


def member(name: str, seat: str, args: dict) -> str:
    """A pool member's name: a checkpoint's path or a scripted player's name, with the search it
    plays with when ``seat`` searches."""
    if seat.endswith(SEARCH_SUFFIX):
        return f"{name}{SEARCH_SUFFIX}:{args['search_root']}:n{args['search_n']}"
    return name


def games(run: Path) -> tuple[str, str, list[tuple[int, float]]]:
    """(player, opponent, [(deal seed, the player's score)]) of one evaluation run."""
    args = json.loads((run / "manifest.json").read_text())[-1]["args"]
    opp = args["eval_opponents"]
    base = opp.removesuffix(SEARCH_SUFFIX)
    base = args["opp_ckpt"] if base == "snap:opp" else base
    out = []
    for line in (run / "eval_rows.jsonl").read_text().splitlines():
        r = json.loads(line)
        if r["outcome"].startswith("void") or r.get("leaky"):
            continue
        s = 0.5 if r["outcome"] != "win" else float(r["winner"] == r["a_seat"])
        out.append((r["seed"], s))
    return member(args["init"], args.get("eval_seat", "eval"), args), member(base, opp, args), out


def fit(runs: list[Path]) -> dict[str, float]:
    rows = []
    for run in runs:
        a, b, gs = games(run)
        rows += [(a, b, s) for _, s in gs]
    members = {x for a, b, _ in rows for x in (a, b)}
    anchor = "random" if "random" in members else min(members)
    return fit_elo(rows, anchor=anchor)


def mle(pairs: list[tuple[float, float]], start: float = 0.0) -> float:
    """The rating r maximising sum s log p + (1 - s) log(1 - p), p = 1 / (1 + 10^((R - r) / 400)),
    over (opponent rating R, score s) pairs (Newton's method)."""
    k = math.log(10) / 400
    r = start
    for _ in range(100):
        g = h = 0.0
        for rating, s in pairs:
            p = 1 / (1 + 10 ** ((rating - r) / 400))
            g += k * (s - p)
            h += k * k * p * (1 - p)
        step = g / max(h, 1e-12)
        r += max(-400.0, min(400.0, step))
        if abs(step) < 1e-6:
            break
    return r


def rate(pool: dict[str, float], runs: list[Path], reps: int = 200) -> dict:
    by_deal: dict = defaultdict(list)  # (opponent, deal) -> the player's scores
    players = set()
    for run in runs:
        a, b, gs = games(run)
        if b not in pool:
            raise ValueError(f"{run}: opponent {b!r} is not in the pool")
        players.add(a)
        for seed, s in gs:
            by_deal[(b, seed)].append(s)
    if len(players) != 1:
        raise ValueError(f"the runs rate {len(players)} players, not one")
    deals = list(by_deal)

    def pairs(keys: list) -> list[tuple[float, float]]:
        return [(pool[key[0]], s) for key in keys for s in by_deal[key]]

    elo = mle(pairs(deals))
    rng = np.random.default_rng(0)
    boot = sorted(mle(pairs([deals[i] for i in rng.integers(0, len(deals), len(deals))]), elo)
                  for _ in range(reps))
    return {"player": players.pop(), "elo": round(elo, 1),
            "ci95": [round(boot[int(0.025 * reps)], 1), round(boot[int(0.975 * reps) - 1], 1)],
            "deals": len(deals), "opponents": sorted({b for b, _ in deals})}


def main(argv: list[str]) -> None:
    cmd, pool_file, runs = argv[0], Path(argv[1]), [Path(r) for r in argv[2:]]
    if cmd == "fit":
        ratings = fit(runs)
        pool_file.write_text(json.dumps(ratings, indent=1) + "\n")
        print(json.dumps(ratings))
    elif cmd == "rate":
        print(json.dumps(rate(json.loads(pool_file.read_text()), runs)))
    else:
        raise SystemExit(f"unknown command {cmd!r}: fit or rate")


if __name__ == "__main__":
    main(sys.argv[1:])
