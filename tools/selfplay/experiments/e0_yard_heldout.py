"""The yardstick alone on the held-out positions: finite everywhere? (independent of the simulator)"""
import json, sys
from pathlib import Path
import numpy as np
from MTG_bot.core.executor.games import get_supply
from tools.selfplay import features as FT, simulator as S

d = sys.argv[1]
table = FT.CardTable.from_json(json.loads((Path(d) / "table.json").read_text()))
data = S.Data.load([d], table)
a = data.a
ho = np.flatnonzero(S.held_out(a["seed"]))
yards = {s: S.Yardstick.of(get_supply(S.POOL, s), table.row) for s in np.unique(a["set"])}
hs, ls = [], []
for i in ho:
    pub = a["public"][a["public_off"][i]:a["public_off"][i + 1]].tolist()
    hd = a["hand"][a["hand_off"][i]:a["hand_off"][i + 1]].tolist()
    lb = a["lib"][a["lib_off"][i]:a["lib_off"][i + 1]].tolist()
    h, l, _ = yards[a["set"][i]].logp(pub, hd, lb)
    hs.append(-h); ls.append(-l)
hs, ls = np.array(hs), np.array(ls)
print(json.dumps({"held-out": len(ho), "non-finite hand": int((~np.isfinite(hs)).sum()), "non-finite lib": int((~np.isfinite(ls)).sum()),
                  "yard hand mean": round(float(hs[np.isfinite(hs)].mean()), 4), "yard lib mean": round(float(ls[np.isfinite(ls)].mean()), 3)}))
