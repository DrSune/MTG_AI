"""The yardstick's hand and library NLL on pilot-validation positions (seed % 25 == 1, training games)."""
import json, sys
from pathlib import Path
import numpy as np
from MTG_bot.core.executor.games import get_supply
from tools.selfplay import features as FT, simulator as S

d = sys.argv[1]
table = FT.CardTable.from_json(json.loads((Path(d) / "table.json").read_text()))
data = S.Data.load([d], table)
a = data.a
va = np.flatnonzero(a["seed"] % S.HOLDOUT == 1)
yards = {s: S.Yardstick.of(get_supply(S.POOL, s), table.row) for s in np.unique(a["set"])}
hs, ls = [], []
for i in va:
    pub = a["public"][a["public_off"][i]:a["public_off"][i + 1]].tolist()
    hd = a["hand"][a["hand_off"][i]:a["hand_off"][i + 1]].tolist()
    lb = a["lib"][a["lib_off"][i]:a["lib_off"][i + 1]].tolist()
    h, l, _ = yards[a["set"][i]].logp(pub, hd, lb)
    hs.append(-h); ls.append(-l)
hs, ls = np.array(hs), np.array(ls)
t = a["turn"][va]
mid = (t >= 7) & (t <= 12)
print(json.dumps({"val": len(va), "yard_hand": round(float(hs.mean()), 4), "yard_hand_mid": round(float(hs[mid].mean()), 4), "yard_lib": round(float(ls.mean()), 3), "inf": int(np.isinf(hs).sum() + np.isinf(ls).sum())}))
