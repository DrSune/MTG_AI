"""Cards verified in two or more of the home sets: same tree bytes? verified twice?"""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

root = Path(sys.argv[1]) / "MTG_bot" / "data" / "cards"
by = defaultdict(dict)
for s in ("M21", "M20", "FDN"):
    for p in (root / s).glob("*.json"):
        r = json.loads(p.read_text())
        if r.get("verified"):
            by[p.stem][s] = r
multi = {o: d for o, d in by.items() if len(d) > 1}
c = Counter()
same_reviewer = Counter()
for o, d in multi.items():
    shas = {r["verified"]["tree_sha"] for r in d.values()}
    c["same_tree" if len(shas) == 1 else "different_tree"] += 1
    c[f"sets:{'+'.join(sorted(d))}"] += 1
    c["text_sha_equal" if len({r['text_sha'] for r in d.values()}) == 1 else "text_differs"] += 1
    revs = {r["verified"].get("reviewer") for r in d.values()}
    same_reviewer["one reviewer" if len(revs) == 1 else "different reviewers"] += 1
    packs = sum(len(r["verified"].get("packs", [])) for r in d.values())
    c["packs_total"] += packs
print(len(by), "verified oracle ids;", len(multi), "verified in 2+ home sets")
print(dict(c))
print(dict(same_reviewer))
