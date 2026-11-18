"""Read a network on the planning puzzles (P0's readout, docs/PLAN_PLANNING.md §4).

At each puzzle's decision (world 0: every world looks the same to the decider, the solver checks
it), for one checkpoint:
- the policy's probability on the right options (the puzzle's ``answer``) and its greedy pick;
- the value head's reading for the deciding seat, as (v + 1) / 2, beside the solver's value of the
  position (its best root option) — the same scale only for ``win`` and ``survive`` puzzles; a
  ``result`` puzzle scores an undecided game 0.5;
- with ``--search-seeds``, the searched pick: ``search.Searcher`` at window 1's anchor setting
  (KNOWLEDGE/2026-11-13/205: Gumbel root, m 16, n 4, horizon 1, uniform worlds, greedy
  continuation, skip at 0.97), act and priority decisions, one search per seed. Attack and block
  decisions are not searched here (the searcher plans them at the combat boundaries instead);
- for a planner network (docs/DESIGN_PLANNER.md v1), its forecast for each plannable object at
  the root (``forecast``): when, verb, window and target. Its read-back is blank there: the
  prelude is scripted, so the root is the network's first decision.

Per category, the twin-consistent pass rate: the share of twin pairs whose greedy picks are right
in both twins. A network that holds Cancel by habit passes one twin and fails the other.

    .venv/bin/python -m tools.puzzles.runner runs/r28_looks/r28_v2.pt --search-seeds 3 --out x.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import numpy as np

from MTG_bot.bench.view import OracleIndex, SeatLens, ViewOptions
from MTG_bot.core.executor.games import TURN_CAP, _play
from tools.puzzles import puzzle as P
from tools.selfplay import features as FT
from tools.selfplay import planner as PL
from tools.selfplay.model import LocalSlot, load
from tools.selfplay.rig import SelfplayRouter
from tools.selfplay.search import Searcher

SPEC = "net"
SEARCHED = ("act", "priority")


class _Root(Exception):
    def __init__(self, ask: Any, obs: Any) -> None:
        super().__init__(ask.site)
        self.ask, self.obs = ask, obs


class _Prelude:
    """Answers the puzzle's prelude, then stops at the next decision with more than one option:
    the puzzle's root, asked as a game asks it (``rig.SelfplayRouter``: the same AskContext)."""

    name = "puzzle-prelude"

    def __init__(self, script: list[str]) -> None:
        self.script = script
        self.i = 0

    def decide(self, ask: Any, obs: Any) -> int:
        if len(ask.options) == 1:
            return 0
        if self.i < len(self.script):
            word = self.script[self.i]
            self.i += 1
            return [o.token for o in ask.options].index(word)
        raise _Root(ask, obs)


def root(pz: dict) -> tuple[Any, Any, dict]:
    """The root decision of world 0: (ask, observation, the pack keys' handles)."""
    game, handles = P.build(pz, 0)
    supply = P.supply_of(pz)
    driver = _Prelude([P.resolve(w, handles) for w in pz.get("prelude", ())])
    oracle = OracleIndex.for_sets(pz["set"])
    router = SelfplayRouter(game, [driver, driver],
                            [SeatLens(s, oracle, ViewOptions()) for s in (0, 1)], supply=supply)
    try:
        _play(game, router, list(game.world.player_order), TURN_CAP, resumed=True)
    except _Root as r:
        if r.ask.seat != pz["decider"]:
            raise ValueError(f"{pz['name']}: the root is seat {r.ask.seat}'s, not the decider's")
        return r.ask, r.obs, handles
    raise ValueError(f"{pz['name']}: the game ended before the root")


def forecast(slot: Any, executor: Any, ask: Any, feats: dict, ents: list,
             handles: dict) -> dict[str, dict[str, str]]:
    """A planner network's forecast at the root for each plannable object (planner.plannable),
    by pack key: when, verb, window, and the target's pack key or "none"."""
    _, fc = slot.infer((0, ask.seat, SPEC, True, False, feats, 4))
    mask = PL.plannable(executor, executor.world.player_order[ask.seat], ents, feats)
    out = {}
    for r in np.flatnonzero(mask):
        when, verb, win, target = (int(x) for x in fc[r])
        out[P.keyed(str(ents[2 + r]), handles)] = {
            "when": PL.WHEN[when], "verb": PL.VERBS[verb], "window": PL.WINDOWS[win],
            "target": P.keyed(str(ents[target - 1]), handles) if target else "none"}
    return out


def read(slot: Any, table: FT.CardTable, pz: dict, search_seeds: int = 0) -> dict:
    ask, obs, handles = root(pz)
    words = [P.keyed(o.token, handles) for o in ask.options]
    feats, ents = FT.encode_entities(obs.executor, ask.seat, ask, table, obs.ctx)
    a, v, probs = slot.infer((0, ask.seat, SPEC, True, False, feats, 2))
    right = set(pz["answer"])
    row = {
        "puzzle": pz["name"], "category": pz["category"], "kind": ask.kind,
        "options": words, "probs": [round(p, 4) for p in probs],
        "p_right": round(sum(p for w, p in zip(words, probs) if w in right), 4),
        "greedy": words[int(a)], "pass": words[int(a)] in right,
        "value": round((float(v) + 1) / 2, 4), "solver_value": max(pz["solver"]["values"].values()),
        # visible cards the checkpoint's card table does not hold (row 1: features.CardTable)
        "unknown_cards": int((feats["cards_i"][:, 0] == 1).sum()),
    }
    if slot.nets[SPEC].planner:
        row["forecast"] = forecast(slot, obs.executor, ask, feats, ents, handles)
    if search_seeds and ask.kind in SEARCHED:
        picks = []
        for seed in range(search_seeds):
            searcher = Searcher(slot, 0, SPEC, table, pool_mode="verified", set_code=pz["set"],
                                seed=seed, root="gumbel", m=16, n=4, horizon=1,
                                kinds=SEARCHED, continuation="greedy")
            picks.append(words[searcher.choose(ask, obs, feats)])
        row["searched"] = picks
        row["searched_pass"] = round(sum(p in right for p in picks) / len(picks), 4)
    return row


def _block(names: list[str], by: dict[str, dict], puzzles: dict[str, dict]) -> dict:
    """One category's (or the whole suite's) figures. ``searched_twin_consistent``: pairs whose
    searched picks are right in most seeds in both twins, over the searched pairs.
    ``value_order``: pairs the solver values differently whose value-head readings are in the
    solver's order, over those pairs."""
    pairs = sorted({tuple(sorted((n, puzzles[n]["twin"]))) for n in names})
    both = [all(by[n]["pass"] for n in pair) for pair in pairs]
    searched = [by[n]["searched_pass"] for n in names if "searched_pass" in by[n]]
    spairs = [pr for pr in pairs if all("searched_pass" in by[n] for n in pr)]
    ordered = [pr for pr in pairs if by[pr[0]]["solver_value"] != by[pr[1]]["solver_value"]]
    in_order = [(by[a]["solver_value"] - by[b]["solver_value"]) * (by[a]["value"] - by[b]["value"]) > 0
                for a, b in ordered]
    return {
        "pairs": len(pairs), "twin_consistent": round(sum(both) / len(pairs), 4),
        "single_pass": round(sum(by[n]["pass"] for n in names) / len(names), 4),
        "p_right": round(sum(by[n]["p_right"] for n in names) / len(names), 4),
        "searched_pass": round(sum(searched) / len(searched), 4) if searched else None,
        "searched_twin_consistent": (round(sum(all(by[n]["searched_pass"] > 0.5 for n in pr)
                                               for pr in spairs) / len(spairs), 4)
                                     if spairs else None),
        "value_order": round(sum(in_order) / len(in_order), 4) if in_order else None,
    }


def summarise(rows: list[dict], puzzles: dict[str, dict]) -> dict:
    """Per category and for the suite (``_block``)."""
    by = {r["puzzle"]: r for r in rows}
    out = {cat: _block(sorted(n for n, p in puzzles.items() if p["category"] == cat), by, puzzles)
           for cat in sorted({p["category"] for p in puzzles.values()})}
    out["all"] = _block(sorted(puzzles), by, puzzles)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("checkpoints", nargs="+")
    ap.add_argument("--search-seeds", type=int, default=0)
    ap.add_argument("--out", default="")
    args = ap.parse_args(argv)
    puzzles = {p.stem: P.load(p) for p in sorted(P.SUITE.glob("*.json"))}
    report = []
    for path in args.checkpoints:
        t0 = time.perf_counter()
        model, table, _ = load(path, "cpu")  # a planner network loads as one (model.load)
        slot = LocalSlot({SPEC: model})
        rows = [read(slot, table, pz, args.search_seeds) for pz in puzzles.values()]
        rec = {"checkpoint": path, "rows": rows, "summary": summarise(rows, puzzles),
               "seconds": round(time.perf_counter() - t0, 1)}
        report.append(rec)
        shown = {"checkpoint": path, "summary": rec["summary"], "seconds": rec["seconds"]}
        if model.planner:  # each puzzle's root forecast (``forecast``)
            shown["forecasts"] = {r["puzzle"]: r["forecast"] for r in rows}
        print(json.dumps(shown))
        if args.out:
            Path(args.out).write_text(json.dumps(report, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
