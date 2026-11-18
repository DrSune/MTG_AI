"""The soak baseline in one table: per pool, games, crashes and detector hits by class.

    soak_summary.py
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
for code in ("M21", "M20", "FDN"):
    d = json.loads((HERE / f"soak_{code}.json").read_text())
    hits = [(h["detector"], h["detail"][:80], h["games"]) for h in d["detector_hits"]]
    print(f"{code}: {d['games']} games, {d['crashed']} crashes, {sum(h[2] for h in hits)} hit rows: {hits}")
