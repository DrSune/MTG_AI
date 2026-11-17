"""Blast radius from two tree_dump.py outputs (base, branch): the trees that changed (the
compiler's, and with card records applied), the verified cards that leave or join the verified
pool, the cards whose unparsed sentences went down (and the ones that now compile whole), and the
still-verified cards whose unchanged tree reads an engine path the change touched.

    tree_diff.py <trees_base.json> <trees_branch.json>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

base = json.loads(Path(sys.argv[1]).read_text())
new = json.loads(Path(sys.argv[2]).read_text())


def kind(row: dict) -> str:
    if row.get("needs_atom"):
        return "needs-atom record"
    return "record" if row.get("record") else "compiler"


changed_compiler, changed_tree, leaving, joining, engine, fewer, whole = [], [], [], [], [], [], []
for code in base:
    for oid, b in base[code].items():
        n = new[code][oid]
        if b["compiler"] != n["compiler"]:
            changed_compiler.append((code, b["name"]))
        if b["tree"] != n["tree"]:
            changed_tree.append((code, b["name"], f"{kind(b)} -> {kind(n)}",
                                 "verified" if b.get("verified") else "unverified"))
        if b.get("verified") and not n.get("verified"):
            leaving.append((code, b["name"]))
        if n.get("verified") and not b.get("verified"):
            joining.append((code, b["name"]))
        if b.get("verified") and n.get("verified") and b["tree"] == n["tree"] and b.get("facts"):
            engine.append((code, b["name"], b["facts"]))
        before, after = b.get("compiler_unparsed"), n.get("compiler_unparsed")
        if before is not None and after is not None and after < before:
            fewer.append((code, b["name"], f"{before} -> {after}"))
            if after == 0:
                whole.append((code, b["name"]))
print(f"compiler trees changed ({len(changed_compiler)}):")
for row in sorted(changed_compiler):
    print("  ", *row)
print(f"trees with records applied changed ({len(changed_tree)}):")
for row in sorted(changed_tree):
    print("  ", *row)
print(f"compiler: fewer unparsed sentences ({len(fewer)}):")
for row in sorted(fewer):
    print("  ", *row)
print(f"compiler: newly compiling whole ({len(whole)}): {sorted(whole)}")
print(f"verified cards leaving the verified pool ({len(leaving)}): {sorted(leaving)}")
print(f"verified cards joining ({len(joining)}): {sorted(joining)}")
print(f"still-verified cards (unchanged bytes) whose tree reads a changed engine path ({len(engine)}):")
for row in sorted(engine):
    print("  ", *row)
totals = {code: (sum(1 for r in base[code].values() if r.get("verified")),
                 sum(1 for r in new[code].values() if r.get("verified"))) for code in base}
print("verified stamps matching, per set (base -> branch):",
      {k: f"{a}->{b}" for k, (a, b) in totals.items() if a or b})
