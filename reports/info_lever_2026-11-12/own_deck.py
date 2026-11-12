"""Does the network's own decklist carry outcome information its value lacks early in a game?
(PLAN_CEILING §14.4; the red team's M6.)

    PYTHONPATH=. .venv/bin/python reports/info_lever_2026-11-12/own_deck.py COLLECT.pkl ROWS.jsonl DECKS.npz CRITIC.json

COLLECT is a ``learner --collect`` file, ROWS its run's train_rows.jsonl and DECKS those games'
decks rebuilt at the collect's commit (``decks rebuild``). At the learner's first decision of each
game: the value v and the result z. Cross-validated R² (5 folds over games, ridge) of the residual
z - v on (a) own-deck features only, which the player legitimately knows (CR: a player knows their
own decklist), and (b) both decks' features, which include the opponent's hidden deck (an upper
bound, never an input).
"""
import json
import pickle
import sys
from pathlib import Path

import numpy as np

collect, rows_path, decks_path, critic_path = sys.argv[1:5]
games = [json.loads(x) for x in Path(rows_path).read_text().splitlines()]
k_of = {g["gid"]: k for k, g in enumerate(games)}
z = np.load(decks_path)
value = json.loads(Path(critic_path).read_text())["value"]
vals = np.array([value.get(str(c), 0.0) for c in z["card"]])
land, creature, mv = z["land"], z["creature"] & ~z["land"], z["mv"]
ci = z["ci"]


def deck_feats(k: int, seat: int) -> np.ndarray:
    a, b = z["off"][2 * k + seat], z["off"][2 * k + seat + 1]
    idx, cnt = z["idx"][a:b].astype(int), z["cnt"][a:b].astype(float)
    spell = ~land[idx]
    n = cnt.sum()
    lands = cnt[land[idx]].sum()
    hist = [cnt[spell & (np.clip(mv[idx], 0, 6) == m)].sum() for m in range(7)]
    colours = [cnt[spell & np.array([c in str(x) for x in ci[idx]])].sum() for c in "WUBRG"]
    return np.array([n, lands, cnt[creature[idx]].sum(), (cnt * vals[idx]).sum(),
                     (cnt[spell] * mv[idx][spell]).sum() / max(cnt[spell].sum(), 1), *hist, *colours])


with open(collect, "rb") as fh:
    data = pickle.load(fh)
first = {}
for r in data:
    if r[7] == 0 and r[5] in (-1.0, 0.0, 1.0):  # the seat's first decision; decided games
        first[r[6]] = (float(r[3]), float(r[5]))
del data
X_own, X_both, V, Z, SEAT = [], [], [], [], []
for gid, (v, zz) in first.items():
    k = k_of.get(gid)
    if k is None:
        continue
    g = games[k]
    seat = g["seats"].index("learner")
    own, opp = deck_feats(k, seat), deck_feats(k, 1 - seat)
    extra = [float(seat == 0), float(g["set_code"] == "M20")]
    X_own.append(np.concatenate([own, extra]))
    X_both.append(np.concatenate([own, opp, extra]))
    V.append(v)
    Z.append(zz)
    SEAT.append(seat)
X_own, X_both, V, Z = map(np.array, (X_own, X_both, V, Z))
R = Z - V
print(f"games {len(Z)}; at the first decision the value explains {1 - np.var(R) / np.var(Z):.4f} of the result's variance")


def cv_r2(X: np.ndarray, y: np.ndarray, lam: float = 1.0, folds: int = 5) -> float:
    rng = np.random.default_rng(0)
    order = rng.permutation(len(y))
    pred = np.zeros(len(y))
    for f in range(folds):
        te = order[f::folds]
        tr = np.setdiff1d(order, te)
        mu, sd = X[tr].mean(0), X[tr].std(0) + 1e-9
        A = np.c_[np.ones(len(tr)), (X[tr] - mu) / sd]
        w = np.linalg.solve(A.T @ A + lam * np.eye(A.shape[1]), A.T @ y[tr])
        pred[te] = np.c_[np.ones(len(te)), (X[te] - mu) / sd] @ w
    return 1 - np.mean((y - pred) ** 2) / np.var(y)


for name, X in (("own deck (legitimate)", X_own), ("both decks (privileged bound)", X_both)):
    r2 = cv_r2(X, R)
    print(f"{name:32s} CV R² of the residual {r2:+.4f}; of the result with the value in: "
          f"{cv_r2(np.c_[X, V], Z):+.4f} (the value alone {cv_r2(V[:, None], Z):+.4f})")
