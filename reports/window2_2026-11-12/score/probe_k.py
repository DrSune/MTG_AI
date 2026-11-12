"""194 §2's K1-K4 from the probe's outputs. Run: .venv/bin/python <this> OUT.jsonl
The read is at the lr where base has the higher held-out mid-game explained variance at the end;
deep - base and wide - base at the end of the epoch, paired by held-out game, with 95% intervals
from 2,000 bootstrap resamples of the held-out games; K3 is base's end against its step 0 at each
lr; K4 the peak memory of a step."""
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

out = sys.argv[1]
rows = [json.loads(x) for x in Path(out).read_text().splitlines()]
end = {}
for r in rows:
    if r["step"] == r["steps"]:
        end[(r["arm"], r["lr"])] = r
lrs = sorted({lr for arm, lr in end if arm == "base"})
read = max(lrs, key=lambda lr: end[("base", lr)]["ev_mid"])


def npz(arm, lr, step):
    return np.load(f"{out}.{arm}.lr{lr:g}.s{step}.npz")


def ev(v, r):
    return 1 - np.var(r - v) / max(np.var(r), 1e-8)


rng = np.random.default_rng(0)
res = {"read_lr": read}
for lr in lrs:
    e = end[("base", lr)]
    z0, z1 = npz("base", lr, 0), npz("base", lr, e["steps"])
    m = z0["phase"] == 1
    res[f"K3_lr{lr:g}"] = round(float(ev(z1["v"][m], z1["ret"][m]) - ev(z0["v"][m], z0["ret"][m])), 5)
base = npz("base", read, end[("base", read)]["steps"])
games = defaultdict(list)
for i, g in enumerate(base["gid"]):
    games[int(g)].append(i)
keys = np.array(sorted(games))
for arm in ("deep", "wide"):
    if (arm, read) not in end:
        continue
    z = npz(arm, read, end[(arm, read)]["steps"])
    assert np.array_equal(z["gid"], base["gid"])
    m = base["phase"] == 1

    def d(ix, z=z, m=m):  # ix may repeat a game: a bootstrap resample counts it each time
        sel = ix[m[ix]]
        return ev(z["v"][sel], z["ret"][sel]) - ev(base["v"][sel], base["ret"][sel])

    point = d(np.arange(len(m)))
    boot = [d(np.concatenate([games[k] for k in rng.choice(keys, len(keys))]))
            for _ in range(2000)]
    res[f"{arm}-base_ev_mid"] = round(float(point), 5)
    res[f"{arm}-base_ci95"] = [round(float(np.percentile(boot, 2.5)), 5),
                              round(float(np.percentile(boot, 97.5)), 5)]
    res[f"{arm}-base_nll"] = round(end[(arm, read)]["policy_nll"] - end[("base", read)]["policy_nll"], 5)
    res[f"{arm}_peak_gib"] = end[(arm, read)].get("peak_gib")
    res[f"{arm}_s_per_step"] = end[(arm, read)].get("s_per_step")
# The read lr is chosen on the same held-out games and metric K1/K2 are read on (194 §3), so
# base at it is the larger of two noisy estimates and deep - base, wide - base lean toward the
# null. Its size: base at one lr minus the other, paired by game (bug hunt 197). An interval far
# from 0 means the pick was not noise and the lean is small.
if len(lrs) == 2:
    za, zb = (npz("base", lr, end[("base", lr)]["steps"]) for lr in lrs)
    assert np.array_equal(za["gid"], zb["gid"])
    m = za["phase"] == 1

    def dlr(ix):
        sel = ix[m[ix]]
        return ev(za["v"][sel], za["ret"][sel]) - ev(zb["v"][sel], zb["ret"][sel])

    boot = [dlr(np.concatenate([games[k] for k in rng.choice(keys, len(keys))]))
            for _ in range(2000)]
    res[f"base_lr{lrs[0]:g}-lr{lrs[1]:g}_ev_mid"] = round(float(dlr(np.arange(len(m)))), 5)
    res["lr_pick_ci95"] = [round(float(np.percentile(boot, 2.5)), 5),
                           round(float(np.percentile(boot, 97.5)), 5)]
res["base_peak_gib"] = end[("base", read)].get("peak_gib")
res["base_s_per_step"] = end[("base", read)].get("s_per_step")
res["base_end"] = {k: end[("base", read)][k] for k in ("ev_early", "ev_mid", "ev_late", "ev_all", "policy_nll")}
print(json.dumps(res))
