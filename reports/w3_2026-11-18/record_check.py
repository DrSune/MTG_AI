"""Did gate round W3's re-map change only the reveals? For each card record that changed between
two checkouts: its stored tree with every REVEAL atom taken out must be byte-equal on both
sides, with as many REVEAL atoms on each (DESIGN_ATOM_ONTOLOGY §19: a reveal re-encoded, or moved
after the move it reveals the pick of, and nothing else).

    record_check.py <base checkout> <branch checkout>
"""
import json
import sys
from pathlib import Path

BASE, NEW = (Path(p).resolve() for p in sys.argv[1:3])


def strip(node, found: list) -> object:
    if isinstance(node, dict):
        return {k: strip(v, found) for k, v in node.items()}
    if isinstance(node, list):
        out = []
        for item in node:
            if isinstance(item, dict) and item.get("tag") == "Atom" and item.get("verb", {}).get("name") == "REVEAL":
                found.append(item)
                continue
            out.append(strip(item, found))
        return out
    return node


for path in sorted((NEW / "MTG_bot" / "data" / "cards").glob("*/*.json")):
    old_path = BASE / path.relative_to(NEW)
    if not old_path.exists() or old_path.read_text() == path.read_text():
        continue
    old, new = json.loads(old_path.read_text()), json.loads(path.read_text())
    if "ir" not in new:
        print(f"{path.parent.name} {new['name']}: no stored tree")
        continue
    if "ir" not in old:
        print(f"{path.parent.name} {new['name']}: new tree (was {sorted(old)})")
        continue
    a, b = [], []
    same = strip(old["ir"], a) == strip(new["ir"], b)
    print(f"{path.parent.name} {new['name']}: rest of the tree {'equal' if same else 'DIFFERS'}; "
          f"REVEAL atoms {len(a)} -> {len(b)}; verified block {'kept' if 'verified' in new else 'gone'}")
