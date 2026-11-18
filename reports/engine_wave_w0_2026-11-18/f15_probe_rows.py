"""F15 (KNOWLEDGE/2026-11-18/215): the card probe's cast section now reads the menu (menu.menu) in
place of query.legal_casts. For every card of M21, M20 and FDN (records applied, verified or not,
as the card tools compile them), on the probe's standard board with the card in hand: the rows
legal_casts gave (its rule: a land drop, or spell_castable's base and kicked declarations) against
the rows the probe now reads (probe.hand_rows). Only a card whose rows differ can have a different
probe trace (gate G1's text, whose sha a verdict records); those are listed, then probed with the
base's probe and the branch's to compare the shas.

    f15_probe_rows.py <checkout> [--sha <base checkout>]
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
for p in (ROOT, ROOT / "tools", ROOT / "tools" / "cards"):
    sys.path.insert(0, str(p))
import probe  # noqa: E402

from MTG_bot.core.executor.games import compile_supply  # noqa: E402
from MTG_bot.core.executor.legality import spell_castable  # noqa: E402
from MTG_bot.core.executor.stack import land_playable  # noqa: E402

if sys.argv[2:3] == ["--probe"]:  # a child: print the probe sha of each named card of one set
    code = sys.argv[3]
    sup = compile_supply("all", code, require_verified=False)
    for name in sys.argv[4:]:
        oid = next(o for o, m in sup.metas.items() if m.name == name)
        print(code, name, probe.Probe(sup, code, oid).report().sha()[:16], flush=True)
    sys.exit(0)

differ: dict[str, list[str]] = {}
for code in ("M21", "M20", "FDN"):
    sup = compile_supply("all", code, require_verified=False)
    n = 0
    for oid, meta in sorted(sup.metas.items(), key=lambda kv: kv[1].name):
        try:
            r = probe.Probe(sup, code, oid).board("hand")
        except Exception as exc:  # noqa: BLE001 - a card the probe cannot set up: reported
            print(f"{code} {meta.name}: board raised {type(exc).__name__}")
            continue
        if isinstance(r, probe.Variant):
            continue
        h = r.handles["card"]
        n += 1
        old = set()
        if land_playable(r.ex, r.p0, h) is None:
            old.add(("land", False))
        else:
            for kicked in (False, True):
                if spell_castable(r.ex, r.p0, h, kicked=kicked)[0] is None:
                    old.add(("cast", kicked))
        new = {(row.kind, row.kicked) for row in probe.hand_rows(r, h)}
        if old != new:
            differ.setdefault(code, []).append(meta.name)
            print(f"{code} {meta.name}: legal_casts {sorted(old)} -> menu {sorted(new)}")
    print(f"{code}: {n} cards on the board, {len(differ.get(code, []))} with other rows")
if "--sha" in sys.argv:
    base = sys.argv[sys.argv.index("--sha") + 1]
    for code, names in differ.items():
        for side in (base, str(ROOT)):
            out = subprocess.run([sys.executable, __file__, side, "--probe", code, *names],
                                 capture_output=True, text=True, check=True).stdout
            print(f"probe shas, {'base' if side == base else 'branch'} ({side}):")
            print(out, end="")
