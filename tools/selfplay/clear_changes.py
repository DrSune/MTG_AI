"""What does the search correct? Decode clear overrides (margin >= 0.1) of one generation.

    .venv/bin/python -m tools.selfplay.clear_changes runs/selfplay/r13_exit/state.pkl 0 \
        runs/selfplay/r12_exit/v0.pt

Arguments: a run's state.pkl, the window index, the network that generated those labels.
"""
import pickle
import random
import sys
from collections import Counter

import torch

from tools.selfplay import features as FT
from tools.selfplay import model as M
from tools.selfplay.distill_lab import classify

state, gen, prior = sys.argv[1], int(sys.argv[2]), sys.argv[3]
dev = torch.device("cuda")
with open(state, "rb") as fh:
    rows = pickle.load(fh)["window"][gen]
rows = [r for r in rows if len(r) > 5 and r[5]]
net, table, _ = M.load(prior, dev)
infos = classify(rows, net, 0.05, dev)

def opt(feats, k):
    o = feats["opts_i"][k]
    typ = FT.OPTION_TYPES[o[0]] if o[0] < len(FT.OPTION_TYPES) else str(o[0])
    ref = int(o[1])
    who = "" if ref == 0 else "me" if ref == 1 else "opp" if ref == 2 else table.names[int(feats["cards_i"][ref - 3, 0])]
    return f"{typ}:{who}" if who else typ

trans = Counter(); kinds = Counter(); turns = Counter(); mine = Counter()
clear = [(r, i) for r, i in zip(rows, infos) if i["margin"] is not None and i["margin"] >= 0.1]
for r, i in clear:
    f = r[0]
    kinds[FT.ASK_KINDS[int(f["ask_i"][0])]] += 1
    a, b = opt(f, i["a0"]).split(":")[0], opt(f, r[1]).split(":")[0]
    trans[f"{a} -> {b}"] += 1
    turns[min(round(float(f["glob_f"][0]) * 20), 12)] += 1
    mine[bool(f["glob_f"][1])] += 1
print(f"clear overrides {len(clear)} of {len(rows)} searched")
print("ask kinds:", kinds.most_common())
print("net -> search option types:", trans.most_common(14))
print("turn:", sorted(turns.items()))
print("my turn:", dict(mine))
random.seed(1)
for r, i in random.sample(clear, 14):
    f = r[0]; pf = f["players_f"]
    print(f"\nturn {float(f['glob_f'][0])*20:.0f} {'mine' if f['glob_f'][1] else 'theirs'} | life {pf[0,0]*20:.0f}-{pf[1,0]*20:.0f} | hand {pf[0,1]*7:.0f} | lands {pf[0,12]*10:.0f}/{pf[1,12]*10:.0f} untapped {pf[0,14]*10:.0f} | creatures {pf[0,13]*10:.0f}/{pf[1,13]*10:.0f} | margin {i['margin']:.2f}")
    print(f"  net: {opt(f, i['a0'])} (p {i['probs'][i['a0']]:.2f})  search: {opt(f, r[1])} (p {i['probs'][r[1]]:.2f})  | options: {[opt(f, k) for k in range(f['opts_i'].shape[0])][:8]}")
