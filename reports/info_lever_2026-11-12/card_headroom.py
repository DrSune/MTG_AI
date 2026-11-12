"""Skill headroom per card: where does the search clearly overrule the network? (PLAN_CEILING
§14.1; the red team's M1b.)

    PYTHONPATH=. .venv/bin/python reports/info_lever_2026-11-12/card_headroom.py CKPT CRITIC.json TARGETS_DIR...

TARGETS_DIR holds ``--search-record`` shards (window 1's n = 16 runs). A correction is a decision
where the search's pick differs from the network's top option and its mean result beats the top's
by more than two standard errors, each mean over +-1 results (var = 1 - q^2). It is counted for
the card of the option the search chose ("toward") and of the network's top ("away"). Per card:
corrections per decision where the card was a candidate; and the card's rank in the critic.
"""
import glob
import json
import pickle
import sys
from collections import Counter
from pathlib import Path

import numpy as np

from tools.selfplay import model as M

table = M.load(sys.argv[1], "cpu")[1]
value = json.loads(Path(sys.argv[2]).read_text())["value"]
order = sorted(value, key=lambda c: value[c])
crank = {table.names[table.row(c)]: i for i, c in enumerate(order)}
recs = []
for d in sys.argv[3:]:
    for f in sorted(glob.glob(f"{d}/*.pkl")):
        with open(f, "rb") as fh:
            recs += pickle.load(fh)


def card_of(feats: dict, opt: int) -> str:
    """The card an option names: opts_i[:, 1] is an entity index + 1, the two players first
    (features.py: me 0, the opponent 1, card j at 2 + j)."""
    e = int(np.asarray(feats["opts_i"])[opt, 1])
    if e <= 0:
        return "(no card: pass or decline)"
    if e <= 2:
        return "(a player)"
    return table.names[int(np.asarray(feats["cards_i"])[e - 3, 0])]


cand, toward, away, kinds = Counter(), Counter(), Counter(), Counter()
n_corr = 0
for r in recs:
    probs, alts, q, n = r["probs"], list(r["alts"]), r["q"], r["n"]
    top, pick = int(np.argmax(probs)), int(r["pick"])
    cards = {a: card_of(r["feats"], a) for a in alts}
    for c in set(cards.values()):
        cand[c] += 1
    if pick == top or top not in alts:
        continue
    ip, it = alts.index(pick), alts.index(top)
    se = np.sqrt((1 - q[ip] ** 2) / max(n[ip], 1) + (1 - q[it] ** 2) / max(n[it], 1) + 1e-6)
    if q[ip] - q[it] <= 2 * se:
        continue
    n_corr += 1
    kinds[r["kind"]] += 1
    toward[cards[pick]] += 1
    away[cards[top]] += 1
print(f"{len(recs)} searched decisions; clear corrections {n_corr} ({n_corr / len(recs):.3f}); by kind {dict(kinds)}")
rows = []
for c, k in cand.items():
    if k < 40:
        continue
    rows.append(((toward[c] + away[c]) / k, toward[c], away[c], k, c))
rows.sort(reverse=True)
print(f"\n{'card':34s} {'per cand.':>9s} {'toward':>6s} {'away':>5s} {'cand.':>6s} {'critic rank (0 = low)':>22s}")
for rate, t, a, k, c in rows[:30]:
    print(f"{c[:34]:34s} {rate:9.3f} {t:6d} {a:5d} {k:6d} {crank.get(c, '-')!s:>22s}")
cards = [x for x in rows if x[4] in crank]
if len(cards) > 10:
    rate = np.array([x[0] for x in cards])
    rk = np.array([crank[x[4]] for x in cards], float)
    rr = np.argsort(np.argsort(rate))
    print(f"\nrank correlation of correction rate with critic rank over {len(cards)} cards: "
          f"{np.corrcoef(rr, np.argsort(np.argsort(rk)))[0, 1]:+.3f} (negative: the critic ranks low the cards the search corrects most)")
