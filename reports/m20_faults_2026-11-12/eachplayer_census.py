"""Divergence D21's census: "each opponent / each player <verb>s" written two ways over the 19 sets'
trees (every record applied).

    .venv/bin/python reports/m20_faults_2026-11-12/eachplayer_census.py ROOT OUT.json

- ``plural_role``: atoms whose ``controller`` role can name several players (ALL_OPPONENTS, ANY
  for "each player", OPPONENT, every opponent in multiplayer) outside any EachPlayer, by verb;
- ``eachplayer``: EachPlayer nodes, by the shape of their effect: one Atom (by verb, with its
  ``controller`` role), or more. Whether another role reads the rotated "you" is judged per card
  in docs/ATOM_DIVERGENCES.md D21 (a zone, a filter or an amount naming "you" or "their").
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

root = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(root))
sys.path.insert(1, str(root / "tools" / "cards"))
import corpus  # noqa: E402

from MTG_bot.core.ability_tree import Atom, ControllerRef, EachPlayer, walk  # noqa: E402
from MTG_bot.core.compiler import card_records  # noqa: E402

PLURAL = {ControllerRef.ALL_OPPONENTS, ControllerRef.ANY, ControllerRef.OPPONENT}


plural: dict = defaultdict(list)
each: dict = defaultdict(list)
for code in corpus.SETS:
    sc = corpus.compile_set(code)
    for oid, res in sc.results.items():
        tag = "verified" if card_records.is_verified(res, sc.records.get(oid)) else (
            "mapped" if "ir" in sc.records.get(oid, {}) else "compiled")
        name = res.card.name
        inside: set[int] = set()
        for node in walk(res.card):
            if isinstance(node, EachPlayer):
                inside |= {id(n) for n in walk(node.effect)}
                eff = node.effect
                if isinstance(eff, Atom):
                    who = eff.args.get("controller")
                    each[f"one atom: {eff.verb.name}"].append(
                        [code, name, tag, getattr(node.ref, "name", "selector"),
                         getattr(who, "name", None if who is None else "selector")])
                else:
                    each[f"{type(eff).__name__}"].append([code, name, tag, getattr(node.ref, "name", "selector")])
        for node in walk(res.card):
            if isinstance(node, Atom) and id(node) not in inside:
                who = node.args.get("controller")
                if isinstance(who, ControllerRef) and who in PLURAL:
                    plural[node.verb.name].append([code, name, tag, who.name])
out = {"plural_role": dict(sorted(plural.items())), "eachplayer": dict(sorted(each.items()))}
Path(sys.argv[2]).write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
print(json.dumps({"plural_role": {k: len(v) for k, v in out["plural_role"].items()},
                  "eachplayer": {k: len(v) for k, v in out["eachplayer"].items()}}, indent=1))
