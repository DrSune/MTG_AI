"""The soak's counts per checkout and pool, from soak3.sh's outputs: games, crashes, the games
with an I1 finding (a token outside the battlefield where the game loop stopped) and with a D1-D6
detector hit.

    soak_counts.py <dir with soak_<tag>_<SET>.json> <tag>...
"""
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
for tag in sys.argv[2:]:
    for code in ("M21", "M20", "FDN"):
        d = json.loads((root / f"soak_{tag}_{code}.json").read_text())
        i1 = [h for h in d["detector_hits"] if h["detector"] == "i1_tokens"]
        rest = [h for h in d["detector_hits"] if h["detector"] != "i1_tokens"]
        print(f"{tag} {code}: games {d['games']}, crashed {d['crashed']}, "
              f"I1 {sum(h['games'] for h in i1)} {[h['detail'] for h in i1]}, "
              f"D1-D6 {sum(h['games'] for h in rest)} {sorted({h['detector'] for h in rest})}")
