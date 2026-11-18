"""F65 (KNOWLEDGE/2026-11-18/215): each soak artefact the detectors flagged, as a fixture game,
judged by a checkout's tools/audit/detectors.py. Run it on the base (main 0b7f9c22, exported) and on
W0's branch: each artefact is a HIT before and clean after, and each control (the real fault of the
same shape) is a HIT on both. The new ReplayData fields (printed P/T, the watch) are passed only
where the checkout's ReplayData has them, so the base judges the same rows it always saw.

    f65_artefacts.py <checkout>
"""
from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / "tools" / "audit"))
import detectors as D  # noqa: E402

assert D.__file__.startswith(str(ROOT)), D.__file__
FIELDS = {f.name for f in dataclasses.fields(D.ReplayData)}
P0, P1 = "player:0", "player:1"


def game(rows, **kw):
    kw = {k: v for k, v in kw.items() if k in FIELDS}  # the base has no printed_pt / pt_changes / delayed_seen
    return D.ReplayData(seed="fixture", rows=rows, **kw)


def zc(i, h, frm, to):
    return D.Row(i, i, D.KIND_ZONE_CHANGE, h, P0, "MOVE", (frm, to, P0, P0))


def ctr(i, h, n):
    return D.Row(i, i, D.KIND_COUNTER_PLACED, h, P0, "PUT", ("PLUS_1_PLUS_1", n))


def dies(i, h, pt):
    return D.Row(i, i, D.KIND_CREATURE_DIES, h, P0, "DIED", (D.BATTLEFIELD, P0, "Creature", pt[0], pt[1]))


def upkeep(i, active):
    return D.Row(i, i, D.KIND_TURN_PHASE, "None", active, "TURN", ("UPKEEP", active))


BF = D.BATTLEFIELD
watcher = {"card:26": "Watcher of the Spheres", "card:118": "Watcher of the Spheres"}
leader = {"card:5": "Pack Leader", "card:6": "Pack Leader"}
CASES = [
    # (name, detector, game, artefact?) -- artefact: HIT before, clean after; control: HIT on both
    ("D5 counters folded across lives (M21 229: Watcher bounced and recast)", D.d5_pt_recompute, game(
        [zc(0, "card:118", "hand", BF), ctr(1, "card:118", 2), zc(2, "card:118", BF, "hand"),
         zc(3, "card:118", "hand", BF), dies(4, "card:26", (2, 2)), dies(5, "card:118", (2, 2))],
        identity_name=watcher, printed_pt={"card:26": (2, 2), "card:118": (2, 2)}, pt_changes=[], counter_removals=[]), True),
    ("D5 one card dying twice, a counter each life (FDN 123: Erudite Wizard)", D.d5_pt_recompute, game(
        [zc(0, "card:0", "hand", BF), ctr(1, "card:0", 1), dies(2, "card:0", (3, 4)), zc(3, "card:0", BF, "graveyard"),
         zc(4, "card:0", "graveyard", BF), ctr(5, "card:0", 1), dies(6, "card:0", (3, 4))],
        identity_name={"card:0": "Erudite Wizard"}, printed_pt={"card:0": (2, 3)}, pt_changes=[], counter_removals=[]), True),
    ("D5 a static and a pump on one copy (M21 172: Pack Leader beside another)", D.d5_pt_recompute, game(
        [zc(0, "card:5", "hand", BF), dies(1, "card:5", (4, 3)), zc(2, "card:6", "hand", BF), ctr(3, "card:6", 1),
         dies(4, "card:6", (3, 3))],
        identity_name=leader, printed_pt={"card:5": (2, 2), "card:6": (2, 2)}, pt_changes=[("card:5", 0)], counter_removals=[]), True),
    ("D5 control: a counter the death ignores (counter-blind)", D.d5_pt_recompute, game(
        [zc(0, "card:5", "hand", BF), dies(1, "card:5", (2, 2)), zc(2, "card:6", "hand", BF), ctr(3, "card:6", 1),
         dies(4, "card:6", (2, 2))],
        identity_name=leader, printed_pt={"card:5": (2, 2), "card:6": (2, 2)}, pt_changes=[], counter_removals=[]), False),
    ("D6(i) an Eot delayed trigger of the game's last turn (M21 9: Subira)", D.d6_lifecycle, game(
        [upkeep(5, P1)], binder_dump={"attached": [], "delayed": [(4, "Eot", "card:77", P1, "DamageDealtEvent")]},
        delayed_seen={4: 10}), True),
    ("D6(i) control: an Eot delayed trigger that saw the next turn begin", D.d6_lifecycle, game(
        [upkeep(5, P1), upkeep(12, P0)], binder_dump={"attached": [], "delayed": [(4, "Eot", "card:77", P1, "Dmg")]},
        delayed_seen={4: 10}), False),
    ("D6(iii) two Fiery Emancipations (M21 114, 297: CR 616.1)", D.d6_lifecycle, game(
        [], repl_rows=[("repl", 1, "card:9", P0, "", "live", "DamageDealtEvent", "triple"),
                       ("repl", 2, "card:3", P0, "", "live", "DamageDealtEvent", "triple")]), True),
    ("D6(iii) control: one source registered twice", D.d6_lifecycle, game(
        [], repl_rows=[("repl", 1, "card:9", P0, "", "live", "DamageDealtEvent", "triple"),
                       ("repl", 2, "card:9", P0, "", "live", "DamageDealtEvent", "triple")]), False),
]
for name, fn, g, artefact in CASES:
    print(f"{fn(g).status:6} {'artefact' if artefact else 'control '}  {name}")
