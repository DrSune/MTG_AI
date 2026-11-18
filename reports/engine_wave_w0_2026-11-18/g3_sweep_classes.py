"""G3: what the stricter runner (W0's tools/run_scenarios.py) fails among the packs as they stood on
main 0b7f9c22 (the sweep's output, sweep_stricter_on_base_packs.txt), by cause; every one was
then fixed in its pack (W0's commit), and g3_pack_edits.txt shows the edits play the same games.

    g3_sweep_classes.py sweep_stricter_on_base_packs.txt
"""
import re
import sys
from collections import Counter
from pathlib import Path

packs: dict[str, list[str]] = {}
cur = None
for line in Path(sys.argv[1]).read_text().splitlines():
    if line.startswith("FAIL "):
        cur = line[5:].strip()
        packs[cur] = []
    elif line.startswith("     ") and cur:
        packs[cur].append(line.strip())
causes = Counter()
for name, lines in packs.items():
    if name.startswith("known_bugs/"):
        continue  # they fail by design, before and after
    text = " ".join(lines)
    if "is a word the runner reads itself" in text:
        causes["a card key that is a player word (renamed: p1 -> plains1 ...)"] += 1
    elif "no ask took" in text:
        causes["decision words no ask took (dropped; decoys pinned by kickback_asks/not_asked_to_block)"] += 1
    elif re.search(r"illegal target selection|needs a decision from|expected raise", text):
        causes["a cast whose player:N word was lifted into its targets (moved to targets: [pN])"] += 1
    else:
        causes["other: " + text[:120]] += 1
for cause, n in causes.most_common():
    print(f"{n:4}  {cause}")
print(f"{sum(causes.values()):4}  packs of the default sweep and the suite (known_bugs aside)")
