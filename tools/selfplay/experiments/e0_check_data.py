"""Sanity of captured simulator data: labels obey the rules' masks, every card accounted for, mixes."""
import json, sys
from collections import Counter
from pathlib import Path
import numpy as np, torch
from tools.selfplay import features as FT, simulator as S

d = sys.argv[1:]
table = FT.CardTable.from_json(json.loads((Path(d[0]) / "table.json").read_text()))
data = S.Data.load(d, table)
a = data.a
n = len(data)
pub_n = np.diff(a["public_off"])
print("positions", n, "games", len(np.unique(a["seed"])), "per game", round(n / len(np.unique(a["seed"])), 1))
print("public+h+l == 60:", np.mean(pub_n + a["h"] + a["l"] == 60), Counter((pub_n + a["h"] + a["l"]).tolist()).most_common(4))
print("sets", Counter(a["set"].tolist()), "net (me, opp)", Counter(map(tuple, a["net"].tolist())))
print("turn pct", np.percentile(a["turn"], [10, 25, 50, 75, 90]).tolist(), "h mean", a["h"].mean().round(2), "l mean", a["l"].mean().round(2))
games_turns = {}
for s, t in zip(a["seed"], a["turn"]):
    games_turns[s] = max(games_turns.get(s, 0), t)
print("max turn per game pct", np.percentile(list(games_turns.values()), [10, 25, 50, 75, 90]).tolist())
bad = 0
for ch in np.array_split(np.arange(n), max(1, n // 512)):
    b = data.batch(ch, "cpu")
    for name, nn_, cap in (("hand", "h", b["cap"]), ):
        ok = S.allowed(b[name], b[nn_], cap)
        hit = ok.gather(-1, b[name][..., None]).squeeze(-1) | (torch.arange(b[name].shape[1])[None] >= b[nn_][:, None])
        bad += int((~hit.all(1)).sum())
    lib_cap = b["cap"] - S.counts(b["hand"], b["h"], b["cap"].shape[1]).long()
    ok = S.allowed(b["lib"], b["l"], lib_cap)
    hit = ok.gather(-1, b["lib"][..., None]).squeeze(-1) | (torch.arange(b["lib"].shape[1])[None] >= b["l"][:, None])
    bad += int((~hit.all(1)).sum())
print("labels outside the rules' masks:", bad)
ev = a["ev_i"]
print("window: events per position mean", (ev[..., 0] > 0).sum(1).mean().round(1), "named share", ((ev[..., 1] > 1).sum() / max(1, (ev[..., 0] > 0).sum())).round(3))
