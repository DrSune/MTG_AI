"""Classify the 4th positional arg of each prod/test Selector(...) site:
Zone(...) literal vs a forwarded variable/expression."""

import ast
import json
import os
from collections import Counter

ROOT = "/home/sune/Desktop/MTG_AI"
d = json.load(open("/tmp/opencode/r0_scan.json"))
sites = d["constructions"]

files = {}
for s in sites:
    p = os.path.join(ROOT, s["file"])
    if p not in files:
        files[p] = open(p, encoding="utf-8").read()

out = []
for s in sites:
    tree = ast.parse(files[os.path.join(ROOT, s["file"])])
    found = None
    for n in ast.walk(tree):
        if (
            isinstance(n, ast.Call)
            and n.lineno == s["line"]
            and isinstance(n.func, ast.Name)
            and n.func.id == "Selector"
        ):
            found = n
            break
    if found is None or len(found.args) < 4:
        s["arg4"] = "n/a"
        out.append(s)
        continue
    a4 = found.args[3]
    if isinstance(a4, ast.Call):
        f = a4.func
        nm = f.id if isinstance(f, ast.Name) else getattr(f, "attr", "?")
        s["arg4"] = f"CALL:{nm}"
    elif isinstance(a4, ast.Name):
        s["arg4"] = f"VAR:{a4.id}"
    elif isinstance(a4, ast.Attribute):
        s["arg4"] = f"ATTR:{a4.attr}"
    elif isinstance(a4, ast.Subscript):
        s["arg4"] = "SUBSCRIPT"
    else:
        s["arg4"] = type(a4).__name__
    out.append(s)

c = Counter((s["test"], s["arg4"]) for s in out if s["npos"] >= 4)
for k, v in c.most_common(40):
    print(v, k)
json.dump(out, open("/tmp/opencode/r0_scan_typed.json", "w"), indent=1)
print(
    "VAR-forwarding prod count:",
    sum(
        v
        for (t, k), v in c.items()
        if t == "prod" and k.startswith(("VAR", "ATTR", "SUBSCRIPT"))
    ),
)
print(
    "Zone-literal prod count:",
    sum(v for (t, k), v in c.items() if t == "prod" and k == "CALL:Zone"),
)
print(
    "other-call prod count:",
    sum(
        v
        for (t, k), v in c.items()
        if t == "prod" and k.startswith("CALL:") and k != "CALL:Zone"
    ),
)
