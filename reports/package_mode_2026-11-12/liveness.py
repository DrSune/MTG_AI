"""Is the package live? (docs/PLAN_CEILING.md §14.3; tools/selfplay/packages.py)

The heuristic against itself on package decks, and on coherent decks from the same seeds. Per
deck and game it counts what each family's consumers did, a family being kept by a package:
- a trigger: a resolution (TriggerBinder.resolve returned "resolved") of a triggered ability
  whose shapes (packages.shapes) include a kept one, prowess's synthesized trigger included;
- a static: at each of its controller's combats (the pre-attacks boundary, rig.before_attacks),
  a live static layer whose consumer part acted: its selector picked a permanent besides its
  source, a count in it counted one, or a condition (or a while-duration) of it held.
A package deck is read for the families of the package it was built around; a coherent deck for
every family (and apart, for those whose consumer it was dealt).

    CUDA_VISIBLE_DEVICES= OMP_NUM_THREADS=2 nice -n 19 .venv/bin/python \
        reports/package_mode_2026-11-12/liveness.py --deals 150 --sets M21 M20 FDN \
        --out reports/package_mode_2026-11-12/liveness.json
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from MTG_bot.core.ability_tree import FAtom, FNot, QCount, Selector, walk
from MTG_bot.core.executor import binding
from MTG_bot.core.executor.games import deal_decks, get_supply
from MTG_bot.core.executor.legality import enumerate_candidates
from tools.selfplay import packages as PK
from tools.selfplay.heuristic import HeuristicAgent
from tools.selfplay.rig import play_game

KEPT: dict = {}  # a kept package's shape -> its family
FIRED: Counter = Counter()  # (seat, family) -> what consumers of the family did this game


def _families(shapes: set) -> set:
    return {KEPT[s] for s in shapes if s in KEPT}


_resolve = binding.TriggerBinder.resolve


def _counting_resolve(self, obj):
    out = _resolve(self, obj)
    if out == "resolved":
        seat = self.world.player_order.index(obj.controller)
        for fam in _families(PK.shapes(obj.node)):
            FIRED[(seat, fam)] += 1
    return out


binding.TriggerBinder.resolve = _counting_resolve


def static_did(ex, layer) -> set:
    """The families a live static layer acted for: its selector's, its counts', its conditions'
    (packages.shapes' parts, read one at a time)."""
    reg = ex.layers
    ctx = reg._ctx(layer.source, layer.controller)
    targeted = layer.selector is not None and any(h != layer.source
                                                  for h in reg._static_targets(layer))
    out = set()
    parts = [*layer.atoms, *(() if layer.condition is None else (layer.condition,))]
    for part in parts:
        nodes = list(walk(part))
        negated = {id(x) for n in nodes if isinstance(n, FNot) for x in walk(n.inner)}
        sel = part.args.get("target") if hasattr(part, "args") else None
        in_sel = {id(x) for x in walk(sel)} if isinstance(sel, Selector) else set()
        for n in nodes:
            if n is part and hasattr(part, "args"):
                fam, ok = KEPT.get(PK._static_shapes(n)), targeted
            elif isinstance(n, QCount):
                fam = KEPT.get(PK._count_shape(n))
                ok = fam is not None and any(h != layer.source
                                             for h in enumerate_candidates(n.selector, ctx))
            elif isinstance(n, FAtom) and n.pred in PK.PREDICATES and id(n) not in negated:
                fam, ok = KEPT.get(PK.PREDICATES[n.pred](n)), targeted if id(n) in in_sel else True
            else:
                continue
            if fam is not None and ok:
                out.add(fam)
    return out


class Watch(HeuristicAgent):
    """The heuristic, looking at its side's static consumers at each of its combats."""

    def plan_combat(self, game, seat: int) -> None:
        ex = game.executor
        me = game.world.player_order[seat]
        for layer in ex.layers.records:
            if layer.kind == "static" and layer.status == "live" and layer.controller == me:
                for fam in static_did(ex, layer):
                    FIRED[(seat, fam)] += 1


def run(set_code: str, deals: int, seed0: int) -> dict:
    sup = get_supply("verified", set_code)
    kept = PK.packages(sup)
    KEPT.clear()
    KEPT.update({s: s[0] for p in kept for s in p.shapes})
    cons_fams = {c: _families(PK.consumer_shapes(sup.pool.results[c].card)) for c in sup.deckable}
    rows = []
    for i in range(deals):
        seed = seed0 + i
        rng = random.Random(f"package:{PK.DEAL_SEED}:{seed}")
        built = [PK.build(rng.randrange(1 << 40), sup, kept) for _ in range(2)]
        assert tuple(d for _, d in built) == PK.package_decks(seed, sup)
        for mode, decks, pkgs in (("package", tuple(d for _, d in built), [p for p, _ in built]),
                                  ("coherent", deal_decks(seed, PK.DEAL_SEED, sup, "coherent"),
                                   [None, None])):
            FIRED.clear()
            res = play_game(seed, [Watch(), Watch()], deck_mode=mode, set_code=set_code,
                            decks=decks)
            for seat in (0, 1):
                rows.append({
                    "set": set_code, "seed": seed, "mode": mode, "seat": seat,
                    "outcome": res["outcome"], "turns": res["turns"],
                    "package": PK.label(pkgs[seat]) if pkgs[seat] else None,
                    "families": sorted({s[0] for s in pkgs[seat].shapes}) if pkgs[seat] else [],
                    "dealt": sorted(set().union(*(cons_fams[c] for c in set(decks[seat])))),
                    "fired": {f: n for (s, f), n in FIRED.items() if s == seat}})
    return {"set": set_code, "packages": [PK.label(p) for p in kept], "rows": rows}


def summary(rows: list[dict]) -> dict:
    """Per family: package decks built around it against coherent decks (all of them, and
    those dealt one of its consumers): mean firings per deck and game, share with any."""
    out: dict = {}
    for mode in ("package", "coherent"):
        games = {(r["set"], r["seed"]): r for r in rows if r["mode"] == mode}
        out[mode] = {"games": len(games),
                     "voids": sum(r["outcome"].startswith("void") for r in games.values()),
                     "turns": round(sum(r["turns"] for r in games.values()) / max(len(games), 1),
                                    2)}
    fams: dict = defaultdict(dict)
    groups = {"package": lambda r, f: r["mode"] == "package" and f in r["families"],
              "coherent": lambda r, f: r["mode"] == "coherent",
              "coherent_dealt": lambda r, f: r["mode"] == "coherent" and f in r["dealt"]}
    for f in sorted({f for r in rows for f in r["families"]}):
        for name, keep in groups.items():
            got = [r["fired"].get(f, 0) for r in rows if keep(r, f)]
            fams[f][name] = {"decks": len(got),
                             "mean": round(sum(got) / max(len(got), 1), 3),
                             "any": round(sum(g > 0 for g in got) / max(len(got), 1), 3)}
    out["families"] = fams
    by_pkg: dict = defaultdict(list)
    for r in rows:
        if r["mode"] == "package":
            by_pkg[(r["set"], r["package"])].append(sum(r["fired"].get(f, 0)
                                                        for f in r["families"]))
    out["packages"] = {f"{s} {p}": {"decks": len(v), "mean": round(sum(v) / len(v), 3),
                                    "any": round(sum(x > 0 for x in v) / len(v), 3)}
                       for (s, p), v in sorted(by_pkg.items())}
    return out


def table(s: dict) -> str:
    out = [f"games: package {s['package']}, coherent {s['coherent']}",
           (f"{'family':10s} {'package decks':>22s} {'coherent decks':>22s} "
            f"{'coherent, consumer dealt':>26s}   (decks, firings per game, share firing)")]
    for f, g in s["families"].items():
        out.append(f"{f:10s} " + " ".join(
            f"{g[k]['decks']:>8d} {g[k]['mean']:>6.2f} {g[k]['any']:>6.2f}" + " " * (w - 22)
            for k, w in (("package", 22), ("coherent", 22), ("coherent_dealt", 26))))
    out += [f"  {k:52s} {v['decks']:>4d} {v['mean']:>6.2f} {v['any']:>6.2f}"
            for k, v in s["packages"].items()]
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sets", nargs="+", default=["M21", "M20", "FDN"])
    ap.add_argument("--deals", type=int, default=150)
    ap.add_argument("--seed0", type=int, default=7_000_001)
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    t0 = time.time()
    runs = [run(s, a.deals, a.seed0) for s in a.sets]
    rows = [r for x in runs for r in x["rows"]]
    res = {"argv": sys.argv[1:], "secs": round(time.time() - t0, 1), "summary": summary(rows),
           "by_set": {x["set"]: summary(x["rows"]) for x in runs}}
    if a.out:
        Path(a.out).write_text(json.dumps({**res, "rows": rows}, indent=1) + "\n")
    print(f"{res['secs']} s\n" + table(res["summary"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
