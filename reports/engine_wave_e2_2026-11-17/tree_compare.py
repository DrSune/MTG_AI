"""Compare two tree_dump.py outputs: trees changed (game and mapped), deal-pool membership changed."""
import json
import sys
from pathlib import Path

a = json.loads(Path(sys.argv[1]).read_text())
b = json.loads(Path(sys.argv[2]).read_text())
total = 0
for code in sorted(a):
    ra, rb = a[code], b[code]
    changed = [o for o in ra if o in rb and (ra[o]["game"], ra[o]["mapped"]) != (rb[o]["game"], rb[o]["mapped"])]
    dealt = [o for o in ra if o in rb and ra[o]["dealt"] != rb[o]["dealt"]]
    only = sorted(set(ra) ^ set(rb))
    total += len(changed) + len(dealt) + len(only)
    print(f"{code}: cards {len(ra)}/{len(rb)}; trees changed {len(changed)}; dealt changed {len(dealt)}; "
          f"only on one side {len(only)}", changed[:5], dealt[:5], only[:5])
print("total differences", total)
