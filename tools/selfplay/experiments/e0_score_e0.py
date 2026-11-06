"""Score E0's gate (KNOWLEDGE 186 §1) from `simulator eval` outputs.

usage: score_e0.py NOWINDOW.npz WINDOW.npz [--sample CKPT DATA...]
"""
import json
import sys

import numpy as np

B = 2000
MID = (7, 12)


def boot_ratio(seed, num, den, mask, rng):
    """Ratio of means over ``mask`` positions, and its 95% interval from a bootstrap over games."""
    games, inv = np.unique(seed[mask], return_inverse=True)
    sn = np.bincount(inv, num[mask])
    sd = np.bincount(inv, den[mask])
    draws = rng.integers(0, len(games), (B, len(games)))
    r = sn[draws].sum(1) / sd[draws].sum(1)
    return round(float(num[mask].sum() / den[mask].sum()), 4), [round(float(x), 4) for x in np.percentile(r, [2.5, 97.5])], int(mask.sum()), len(games)


def ece(p, y, bins=15):
    order = np.argsort(p, kind="stable")
    p, y = p[order], y[order].astype(float)
    edges = np.linspace(0, len(p), bins + 1).astype(int)
    e = m = rel = res = 0.0
    ybar = y.mean()
    for a, b in zip(edges[:-1], edges[1:]):
        if b <= a:
            continue
        w = (b - a) / len(p)
        gap = abs(p[a:b].mean() - y[a:b].mean())
        e += w * gap
        m = max(m, gap)
        rel += w * (p[a:b].mean() - y[a:b].mean()) ** 2
        res += w * (y[a:b].mean() - ybar) ** 2
    return {"ece": round(e, 5), "mce": round(m, 5), "rel": round(rel, 6), "res": round(res, 6),
            "unc": round(ybar * (1 - ybar), 6), "n": len(p)}


def top_k(pos, p, k=24):
    """Mask of each position's k likeliest cards."""
    order = np.lexsort((-p, pos))
    ps = pos[order]
    start = np.r_[0, np.flatnonzero(np.diff(ps)) + 1]
    rank = np.arange(len(ps)) - np.repeat(start, np.diff(np.r_[start, len(ps)]))
    keep = np.zeros(len(p), bool)
    keep[order[rank < k]] = True
    return keep


def report(path, rng):
    z = np.load(path)
    seed, turn = z["seed"], z["turn"]
    out = {"file": path}
    buckets = {"all": np.ones(len(seed), bool), "early 0-6": turn < 7,
               "mid 7-12": (turn >= MID[0]) & (turn <= MID[1]), "late 13+": turn > 12}
    for name, m in buckets.items():
        r, ci, n, g = boot_ratio(seed, z["sim_hand"], z["yard_hand"], m, rng)
        out[f"hand {name}"] = {"sim": round(float(z["sim_hand"][m].mean()), 4),
                               "yard": round(float(z["yard_hand"][m].mean()), 4),
                               "ratio": r, "ci95": ci, "positions": n, "games": g}
    r, ci, n, g = boot_ratio(seed, z["sim_lib"], z["yard_lib"], buckets["all"], rng)
    out["library all"] = {"sim": round(float(z["sim_lib"].mean()), 3), "yard": round(float(z["yard_lib"].mean()), 3), "ratio": r, "ci95": ci}
    for s in np.unique(z["set"]):
        m = z["set"] == s
        out[f"hand set {s}"] = boot_ratio(seed, z["sim_hand"], z["yard_hand"], m, rng)[:2]
    for opp in (0, 1):
        m = z["net"][:, 1] == opp
        out[f"hand opponent {'network' if opp else 'heuristic'}"] = boot_ratio(seed, z["sim_hand"], z["yard_hand"], m, rng)[:2]
    y = z["y"]
    out["calibration sim (all pool cards)"] = ece(z["p_sim"], y)
    out["calibration yard (all pool cards)"] = ece(z["p_yard"], y)
    keep = top_k(z["pos"], z["p_sim"])
    out["calibration sim (top 24 per position)"] = ece(z["p_sim"][keep], y[keep])
    keep_y = top_k(z["pos"], z["p_yard"])
    out["calibration yard (top 24 per position)"] = ece(z["p_yard"][keep_y], y[keep_y])
    return out, z


def main():
    rng = np.random.default_rng(186)
    a, za = report(sys.argv[1], rng)
    b, zb = report(sys.argv[2], rng)
    assert np.array_equal(za["seed"], zb["seed"]) and np.array_equal(za["turn"], zb["turn"])
    mid = (za["turn"] >= MID[0]) & (za["turn"] <= MID[1])
    w = {name: boot_ratio(za["seed"], zb["sim_hand"], za["sim_hand"], m, rng)[:2]
         for name, m in (("all", np.ones(len(mid), bool)), ("mid", mid))}
    keep_window = w["mid"][0] <= 0.95
    arm = b if keep_window else a
    gate = {"window kept (mid ratio window/none <= 0.95)": keep_window, "window/none": w,
            "arm scored": "window" if keep_window else "no window",
            "G1 R_all <= 1": arm["hand all"]["ratio"] <= 1.0,
            "G2 R_mid <= 0.95": arm["hand mid 7-12"]["ratio"] <= 0.95,
            "G3 ECE < 0.05": arm["calibration sim (all pool cards)"]["ece"] < 0.05}
    print(json.dumps({"no window": a, "window": b, "gate": gate}, indent=1, default=str))


if __name__ == "__main__":
    main()
