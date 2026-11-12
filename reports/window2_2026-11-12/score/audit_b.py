"""195 §2-3's measures from an audit run's audits.jsonl. Run: .venv/bin/python <this> AUDITS.jsonl
Over audited decisions with at least two candidates and all four kinds scored: A(kind), the share
whose best candidate (the first maximum, candidates in the network's order) is the true worlds'
best; the mean per-decision rank correlation of the kind's means with true's; the primary
A(sim) - A(uniform), paired by decision, with a 95% interval from 2,000 bootstrap resamples of
the deals."""
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

KINDS = ("uniform", "sim", "true2")
rows = [json.loads(x) for x in Path(sys.argv[1]).read_text().splitlines()]
# a re-run step appends a second copy of its games (and their audits): count the games the run's
# eval_rows.jsonl logged more than once (the same menu asked twice in a turn is not a copy)
_games = [json.loads(x) for x in Path(sys.argv[1]).with_name("eval_rows.jsonl").read_text().splitlines()]
_keys = [(g["seed"], g["a_seat"]) for g in _games]
dups = len(_keys) - len(set(_keys))
ok = [r for r in rows if len(r["cands"]) >= 2 and all(r["q"].get(k) is not None
                                                     for k in ("uniform", "sim", "true", "true2"))]


def best(q):
    return int(np.argmax(q))  # the first maximum: candidates are in the network's order


def rank(v):
    """Average ranks (ties share the mean of their places), as Spearman's rho needs: an ordinal
    rank breaks ties by position, so two fully tied lists scored +1 (bug hunt 197)."""
    v = np.asarray(v, float)
    order = np.argsort(v, kind="stable")
    r = np.empty(len(v))
    r[order] = np.arange(len(v), dtype=float)
    for x in np.unique(v):
        tie = v == x
        r[tie] = r[tie].mean()
    return r


def rho(a, b):
    ra, rb = rank(a), rank(b)
    if ra.std() == 0 or rb.std() == 0:
        return np.nan  # a fully tied list ranks nothing: undefined, left out
    return float(np.corrcoef(ra, rb)[0, 1])


hit = {k: np.array([best(r["q"][k]) == best(r["q"]["true"]) for r in ok], float) for k in KINDS}
cor = {k: np.array([rho(r["q"][k], r["q"]["true"]) for r in ok]) for k in KINDS}
net = np.array([best(r["q"]["true"]) == 0 for r in ok], float)  # the network's top is true's best
deal = np.array([r["seed"] for r in ok])
seeds = np.unique(deal)
where = defaultdict(list)
for i, s in enumerate(deal):
    where[s].append(i)
rng = np.random.default_rng(0)
diff = hit["sim"] - hit["uniform"]
boot = []
for _ in range(2000):
    ix = np.concatenate([where[s] for s in rng.choice(seeds, len(seeds))])
    boot.append(diff[ix].mean())
print(json.dumps({"rows": len(rows), "games_logged_twice": dups, "audited": len(ok), "deals": len(seeds),
                  "A": {k: round(float(hit[k].mean()), 4) for k in KINDS},
                  "A_network_top": round(float(net.mean()), 4),
                  "rank_corr": {k: round(float(np.nanmean(cor[k])), 4) for k in KINDS},
                  "rank_corr_defined": {k: int(np.isfinite(cor[k]).sum()) for k in KINDS},
                  "B2_sim_minus_uniform": round(float(diff.mean()), 4),
                  "B2_ci95": [round(float(np.percentile(boot, 2.5)), 4),
                              round(float(np.percentile(boot, 97.5)), 4)]}))
