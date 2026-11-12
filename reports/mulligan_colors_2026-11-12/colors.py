"""Does the mulligan read whether the hand's lands can cast its spells, or only how many lands
there are? (The owner's question, 2026-11-12.)

    PYTHONPATH=. .venv/bin/python reports/mulligan_colors_2026-11-12/colors.py BATCH.pkl CKPT...

BATCH is a ``learner --collect`` file; its 7-card mulligan declarations whose lands are all basic
are scored by every CKPT on the CPU in fp32. A spell is castable by colour when each of its
colours is made by one of the hand's basic lands (colourless spells always are).
- Observational: p(mulligan) by land count and by the share of the hand's spells castable by
  colour.
- Counterfactual, paired by hand: 3-land hands whose lands cast every spell, with only the
  lands' identities changed. "mono": every land becomes the basic of the deck colour fewer of
  the hand's spells use (a hand the deck can deal). "off": every land becomes a basic of a colour
  no spell in the hand uses (never dealt by a two-colour deck).
"""
import pickle
import sys

import numpy as np
import torch

from tools.selfplay import features as FT
from tools.selfplay import model as M

BASIC = {"Plains": "W", "Island": "U", "Swamp": "B", "Mountain": "R", "Forest": "G"}
COLORS = FT.COLORS

with open(sys.argv[1], "rb") as fh:
    rows = pickle.load(fh)
mk = FT.ASK_KINDS.index("mulligan")
rows = [r for r in rows if int(np.asarray(r[0]["ask_i"]).reshape(-1)[0]) == mk]
table = M.load(sys.argv[2], "cpu")[1]
row_of = {n: i for i, n in enumerate(table.names) if n in BASIC}
hz = FT.ZONE_INDEX[FT.ZONE_HAND]

hands = []  # (row index, land entity positions, land colours, spell colour sets, jm)
for i, r in enumerate(rows):
    f = r[0]
    ci, cf = np.asarray(f["cards_i"]), np.asarray(f["cards_f"], np.float32)
    pos = np.flatnonzero(ci[:, 1] == hz)
    if len(pos) != 7:
        continue
    lands = [p for p in pos if cf[p, FT.F_TYPE0] > 0.5]
    names = [table.names[int(ci[p, 0])] for p in lands]
    if any(n not in BASIC for n in names):
        continue
    spells = [frozenset(c for k, c in enumerate(COLORS) if cf[p, FT.F_COLOR0 + k] > 0.5)
              for p in pos if cf[p, FT.F_TYPE0] <= 0.5]
    jm = [FT.OPTION_TYPES[int(t)] for t in np.asarray(f["opts_i"])[:, 0]].index("mulligan")
    hands.append((i, lands, frozenset(BASIC[n] for n in names), spells, jm))
print(f"{len(rows)} declarations; {len(hands)} 7-card hands with only basic lands")


def share(lc, spells):
    return sum(s <= lc for s in spells) / max(len(spells), 1)


def p_mull(net, feats, jms):
    packed = M.pack(feats)
    out = np.zeros(len(feats))
    with torch.no_grad():
        for s in range(0, len(feats), 512):
            idx = np.arange(s, min(s + 512, len(feats)))
            logits, _ = net(M.collate_packed(packed, idx, "cpu"))
            out[idx] = torch.softmax(logits.float(), -1).numpy()[np.arange(len(idx)), jms[idx]]
    return out


def swapped(i, lands, colour):
    f = {k: np.array(v, copy=True) for k, v in rows[i][0].items()}
    name = next(n for n, c in BASIC.items() if c == colour)
    for p in lands:
        f["cards_i"][p, 0] = row_of[name]
    return f


nl = np.array([len(h[1]) for h in hands])
sh = np.array([share(h[2], h[3]) for h in hands])
feats = [rows[h[0]][0] for h in hands]
jms = np.array([h[4] for h in hands])
# the counterfactual hands: 3 lands, every spell castable, the deck's two colours known
cf_idx, mono, off = [], [], []
for k, (i, lands, lc, spells, jm) in enumerate(hands):
    used = set().union(*spells) if spells else set()
    if len(lands) != 3 or sh[k] < 1 or not spells or len(used | lc) != 2:
        continue
    deck = sorted(used | lc)
    count = {c: sum(c in s for s in spells) for c in deck}
    fewer = min(deck, key=lambda c: (count[c], c))
    other = next(c for c in deck if c != fewer)
    if not count[other]:  # mono must leave some spell dead
        continue
    spare = next(c for c in COLORS if c not in used)
    cf_idx.append(k)
    mono.append(swapped(i, lands, fewer))
    off.append(swapped(i, lands, spare))
cf_idx = np.array(cf_idx)
print(f"counterfactual hands (3 basics, every spell castable, two colours): {len(cf_idx)}")
for path in sys.argv[2:]:
    net = M.load(path, "cpu")[0].float().eval()
    p = p_mull(net, feats, jms)
    print(f"\n{path}")
    for k in (2, 3, 4):
        cells = []
        for lo, hi, name in ((0, 0, "none"), (1e-9, 0.999, "some"), (1, 1, "all")):
            sel = (nl == k) & (sh >= lo) & (sh <= hi)
            cells.append(f"{name} {p[sel].mean():.3f} (n {sel.sum()})" if sel.any() else f"{name} -")
        print(f"  {k} lands, p(mulligan) by the share of spells castable by colour: " + "; ".join(cells))
    pm = p_mull(net, mono, jms[cf_idx])
    po = p_mull(net, off, jms[cf_idx])
    base = p[cf_idx]
    for name, q in (("mono", pm), ("off", po)):
        d = q - base
        print(f"  3 lands, every spell castable -> {name}: p(mulligan) {base.mean():.3f} -> {q.mean():.3f}, "
              f"paired difference {d.mean():+.3f} (se {d.std(ddof=1) / np.sqrt(len(d)):.3f}), "
              f"raised in {(d > 0.01).mean():.2f} of hands")
