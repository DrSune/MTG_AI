"""Gate round 11's four surviving mutants (the reviewer's M9, M11, M14, M17, same replacements) and
five mutants of the gate's fixes, run against the round's tests and packs on a snapshot of the
branch (a `git archive` unpacked elsewhere: each mutant is written there and undone): which does
the battery kill now? Output: mutants_gate11.txt.

    .venv/bin/python reports/cost_twins_2026-11-14/mutate_gate11.py <snapshot dir>
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

T = Path(sys.argv[1]).resolve()
LEG = "MTG_bot/core/executor/legality.py"
AT = "MTG_bot/core/ability_tree.py"
B3 = "MTG_bot/core/compiler/templates_b3.py"

MUTANTS = [
    ("M9 exile goes to the payer's exile, not the owner's", LEG,
     "destination=Zone(ZoneKind.EXILE, ControllerRef.OWNER),\n            ),\n            source=source,\n            controller=controller,\n            bindings={\"cards\": list(exiled)},",
     "destination=Zone(ZoneKind.EXILE, ControllerRef.YOU),\n            ),\n            source=source,\n            controller=controller,\n            bindings={\"cards\": list(exiled)},"),
    ("M11 IR accepts a referent", AT, "    if sel.mode is not SelectorMode.CHOOSE or sel.referent is not None:",
     "    if sel.mode is not SelectorMode.CHOOSE:"),
    ("M14 605.1a no longer counts CostExile", AT, "isinstance(part, (CostSacrifice, CostDiscard, CostExile))",
     "isinstance(part, (CostSacrifice, CostDiscard))"),
    ("M17 removal count read as 1", B3, "        count=QConst(_COUNT_WORDS[m.group(\"n\")]),\n    )",
     "        count=QConst(1),\n    )"),
    ("G1 any filter naming the source, any count", AT,
     "if sel.filter != FAtom(pred=FAtomPred.IS_SOURCE) or sel.count != QConst(1):", "if False:"),
    ("G2 another permanent of any controller", AT,
     "if sel.filter != yours and not (isinstance(sel.filter, FAnd) and yours in sel.filter.children):",
     "if False:"),
    ("G3 zones checked by kind only (the round's first check)", AT,
     "if len(sel.zones) != 1 or sel.zones[0] not in zones:",
     "if any(z.kind not in {y.kind for y in zones} for z in sel.zones):"),
    ("G4 two exile parts or two removals of a kind in one cost", AT,
     "        if len(lanes) != len(set(lanes)):", "        if False:"),
    ("G5 a segment left short is paid partially", LEG,
     "        if len(remaining) < need:\n            raise ValueError(",
     "        if False:\n            raise ValueError("),
]

TESTS = ["MTG_bot/core/test_executor_cost_twins.py", "MTG_bot/core/test_scenario_packs.py",
         "tools/selfplay/test_selfplay.py", "tools/cards/test_gates.py", "tools/cards/test_lints.py"]
K = ("cost_twins or hanged_executioner or barkhide_troll or suspicious_shambler or fungal_plots or cost_asks "
     "or exiles_the_cheapest or enters_tapped_or_with_counters or exile_and_remove_counter or mana_ability")
for name, rel, old, new in MUTANTS:
    path = T / rel
    orig = path.read_text()
    assert orig.count(old) == 1, (name, orig.count(old))
    path.write_text(orig.replace(old, new))
    try:
        out = subprocess.run(
            ["/home/sune/Desktop/MTG_AI/.venv/bin/python", "-m", "pytest", "-p", "no:cacheprovider", "-q",
             "--tb=no", "-rf", *TESTS, "-k", K], cwd=T, capture_output=True, text=True, timeout=900,
            env={"PATH": "/usr/bin:/bin", "CUDA_VISIBLE_DEVICES": "", "OMP_NUM_THREADS": "2",
                 "TORCH_DISABLE_NATIVE_JIT": "1", "HOME": "/home/sune"})
        lines = out.stdout.strip().splitlines()
        failed = [ln.split(" ")[1].split("::")[-1] for ln in lines if ln.startswith("FAILED")]
        verdict = "KILLED" if failed else "SURVIVED"
        print(f"{verdict} | {name} | {lines[-1] if lines else out.stderr[-200:]} | {failed[:3]}", flush=True)
    finally:
        path.write_text(orig)
