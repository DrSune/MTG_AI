"""The first difference between two checkouts' runs of one replay.py game: the first journal row
that differs (with the rows before it and the cards named), and the first decision that differs.

    first_diff.py <base checkout> <branch checkout> <SET> <game index> [context rows]
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

base, branch, code, i = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
ctx = int(sys.argv[5]) if len(sys.argv) > 5 else 6
here = Path(__file__).resolve().parent
dumps = []
with tempfile.TemporaryDirectory(dir=here) as tmp:
    for checkout in (base, branch):
        out = Path(tmp) / f"{len(dumps)}.json"
        subprocess.run([sys.executable, str(here / "game_dump.py"), checkout, code, i, str(out)],
                       check=True, capture_output=True)
        dumps.append(json.loads(out.read_text()))
a, b = dumps
names = {**a["names"], **b["names"]}


def show(row: list[str]) -> str:
    clock, kind, subject, cause, verb, data = row
    return (f"{clock:>5} {kind:<18} {subject}={names.get(subject, '-')!s:<28} "
            f"cause {cause}={names.get(cause, '-')} {verb} {data}")


print(f"== {code} game {i}: base {a['outcome']} winner {a['winner']} turns {a['turns']} lives "
      f"{a['lives']} | branch {b['outcome']} winner {b['winner']} turns {b['turns']} lives {b['lives']}")
k = next((n for n, (x, y) in enumerate(zip(a["journal"], b["journal"])) if x != y),
         min(len(a["journal"]), len(b["journal"])))
print(f"first differing journal row: #{k} (base {len(a['journal'])} rows, branch {len(b['journal'])})")
for row in a["journal"][max(0, k - ctx):k]:
    print("   ", show(row))
for label, rows in (("base", a["journal"]), ("branch", b["journal"])):
    print(f"  {label}:")
    for row in rows[k:k + 4]:
        print("   ", show(row))
d = next((n for n, (x, y) in enumerate(zip(a["asks"], b["asks"])) if x != y),
         min(len(a["asks"]), len(b["asks"])))
print(f"first differing decision: #{d} of {len(a['asks'])} / {len(b['asks'])}")
for label, asks in (("base", a["asks"]), ("branch", b["asks"])):
    print(f"  {label}: {asks[d:d + 2]}")
