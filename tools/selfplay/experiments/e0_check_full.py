"""Full-capture integrity: every opponent card accounted for (all positions); every held-out label inside the rules' masks."""
import json, sys
from collections import Counter
from pathlib import Path
import numpy as np, torch
from tools.selfplay import features as FT, simulator as S

d = sys.argv[1]
table = FT.CardTable.from_json(json.loads((Path(d) / "table.json").read_text()))
data = S.Data.load([d], table)
a = data.a
n = len(data)
tot = np.diff(a["public_off"]) + a["h"] + a["l"]
games = np.unique(a["seed"])
ho = np.flatnonzero(S.held_out(a["seed"]))
print(json.dumps({"positions": n, "games": len(games), "held-out positions": len(ho),
                  "held-out games": len(np.unique(a["seed"][ho])), "accounted (==60)": float(np.mean(tot == 60)),
                  "sets": Counter(a["set"].tolist()), "net (me,opp)": {str(k): v for k, v in Counter(map(tuple, a["net"].tolist())).items()},
                  "turn pct 10/25/50/75/90": np.percentile(a["turn"], [10, 25, 50, 75, 90]).tolist(),
                  "mid-game share": float(np.mean((a["turn"] >= 7) & (a["turn"] <= 12))),
                  "h mean": float(a["h"].mean()), "l mean": float(a["l"].mean())}, default=str))
bad = 0
for ch in np.array_split(ho, max(1, len(ho) // 512)):
    b = data.batch(ch, "cpu")
    for seq, k, cap in ((b["hand"], b["h"], b["cap"]), (b["lib"], b["l"], b["cap"] - S.counts(b["hand"], b["h"], b["cap"].shape[1]).long())):
        ok = S.allowed(seq, k, cap).gather(-1, seq[..., None]).squeeze(-1) | (torch.arange(seq.shape[1])[None] >= k[:, None])
        bad += int((~ok.all(1)).sum())
print("held-out labels outside the rules' masks:", bad)
