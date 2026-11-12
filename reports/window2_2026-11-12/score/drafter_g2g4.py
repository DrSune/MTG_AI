"""193 §2's G2 and G4 from window 2's runs. Run from the repo root:
    PYTHONPATH=. .venv/bin/python <this> CRITIC.json G2RUN_K0 G2RUN_K4 G2RUN_K8 G2RUN_K16 G4_DRAFTED G4_COHERENT
G2: the drafted deck's score per deal (the evaluated seat holds it in both games), the critic's
predicted score per deal (pilots cancel: one network on both seats), the slope of observed on
predicted over all four arms with a bootstrap over deals. G4: the share of decided deals whose
winning seat changes when the pilots swap (the same pilot wins both games), drafted against
coherent; and G4's pass condition, 10,000 or more drafted-deck games over G2 and G4 without an
engine error, read both ways (K = 0 counted as drafted: 10,000; without it: 8,000).

Rows are read by evalrows' rules (tools/selfplay/evalrows.py; inlined here so the script runs on
the producing worktree's code): a later row replaces an earlier one, a void or leaky game drops
its deal. An arm without its 1,000 complete deals is flagged, never silently left out (bug hunt
197)."""
EXPECT_DEALS = 1000
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from MTG_bot.core.executor.games import get_supply
from tools.selfplay import decks as DK

critic = json.loads(Path(sys.argv[1]).read_text())
g2_runs, g4_drafted, g4_coherent = sys.argv[2:6], sys.argv[6], sys.argv[7]
value, b = critic["value"], critic["seat0"]
rng = np.random.default_rng(0)


def rows(run):
    return [json.loads(x) for x in (Path(run) / "eval_rows.jsonl").read_text().splitlines()]


def by_deal(run):
    """{seed: {a_seat: row}}, the last row per deal and seat."""
    out = defaultdict(dict)
    for r in rows(run):
        out[r["seed"]][r["a_seat"]] = r
    return out


def void(r):
    return r["outcome"].startswith("void") or bool(r.get("leaky"))


def errors(run):
    """Engine errors in a run: its void games (a crash voids a game), by the last row."""
    return sum(r["outcome"].startswith("void") for two in by_deal(run).values() for r in two.values())


def result(r):
    return 0.5 if r["outcome"] != "win" else float(r["winner"] == r["a_seat"])


def sig(z):
    return 1 / (1 + math.exp(-z))


supplies = {}
obs, pred, deal, arm = [], [], [], []
print("G2")
for j, run in enumerate(g2_runs):
    by = by_deal(run)
    mode = next((r["deck_mode"] for two in by.values() for r in two.values()), "none")
    sc, pr = [], []
    for seed, two in sorted(by.items()):
        if len(two) != 2 or any(void(r) for r in two.values()):
            continue
        r0 = two[0]
        sup = supplies.setdefault(r0["set_code"], get_supply("verified", r0["set_code"]))
        mine, theirs = DK.drafted_decks(seed, r0["deck_mode"], 0, sup, critic, r0["set_code"])
        d = sum(value.get(c, 0.0) * n for c, n in Counter(mine).items()) - sum(
            value.get(c, 0.0) * n for c, n in Counter(theirs).items())
        o = (result(two[0]) + result(two[1])) / 2
        p = (sig(b + d) + sig(d - b)) / 2
        sc.append(o)
        pr.append(p)
        obs.append(o)
        pred.append(p)
        deal.append(seed)
        arm.append(j)
    sc, pr = np.array(sc), np.array(pr)
    flag = "" if len(sc) == EXPECT_DEALS else f"  ARM INCOMPLETE: {len(sc)} of {EXPECT_DEALS} deals"
    if len(sc) < 2:
        print(f"  {run}: {mode} deals {len(sc)}{flag}")
        continue
    se = sc.std(ddof=1) / math.sqrt(len(sc))
    print(f"  {run}: {mode} deals {len(sc)} score {sc.mean():.4f} +- {se:.4f} "
          f"[{sc.mean() - 1.96 * se:.4f}, {sc.mean() + 1.96 * se:.4f}] predicted {pr.mean():.4f}"
          f"  engine errors {errors(run)}{flag}")
obs, pred, deal = np.array(obs), np.array(pred), np.array(deal)


def slope(ix):
    x, y = pred[ix], obs[ix]
    x = x - x.mean()
    return float((x * (y - y.mean())).sum() / (x * x).sum())


seeds = np.unique(deal)
where = {s: np.flatnonzero(deal == s) for s in seeds}
boot = [slope(np.concatenate([where[s] for s in rng.choice(seeds, len(seeds))]))
        for _ in range(2000)]
print(f"  slope of observed on predicted: {slope(np.arange(len(obs))):.3f} "
      f"95% [{np.percentile(boot, 2.5):.3f}, {np.percentile(boot, 97.5):.3f}] over {len(obs)} "
      f"deal-arms, {len(seeds)} deals")

print("G4")
share, flip_of = {}, {}
for name, run in (("drafted", g4_drafted), ("coherent", g4_coherent)):
    flips = decided = 0
    flip_of[name] = {}
    for seed, two in by_deal(run).items():
        if len(two) != 2 or any(void(r) or r["outcome"] != "win" for r in two.values()):
            continue
        decided += 1
        f = two[0]["winner"] != two[1]["winner"]  # the winning seat changed: one pilot won both
        flips += f
        flip_of[name][seed] = float(f)
    p = flips / decided
    se = math.sqrt(p * (1 - p) / decided)
    share[name] = (p, se)
    print(f"  {name}: {decided} decided deals, winning seat changes in {flips} = {p:.4f} +- {se:.4f}, "
          f"engine errors {errors(run)}")
d = share["drafted"][0] - share["coherent"][0]
se = math.hypot(share["drafted"][1], share["coherent"][1])
print(f"  drafted minus coherent: {d:+.4f} +- {se:.4f} [{d - 1.96 * se:+.4f}, {d + 1.96 * se:+.4f}]"
      " (as registered: the runs as independent)")
both = sorted(set(flip_of["drafted"]) & set(flip_of["coherent"]))  # the same seeds: paired
pd_ = np.array([flip_of["drafted"][s] - flip_of["coherent"][s] for s in both])
pse = pd_.std(ddof=1) / math.sqrt(len(pd_))
print(f"  paired by deal (exploratory): {pd_.mean():+.4f} +- {pse:.4f} over {len(both)} deals")
drafted_runs = list(g2_runs) + [g4_drafted]
games_all = sum(len(two) for run in drafted_runs for two in by_deal(run).values())
err_all = sum(errors(run) for run in drafted_runs)
games_k4 = sum(len(two) for run in drafted_runs[1:] for two in by_deal(run).values())
err_k4 = sum(errors(run) for run in drafted_runs[1:])
print(f"  pass condition (10,000+ drafted-deck games, no engine error): K = 0 counted: {games_all} "
      f"games, {err_all} errors -> {'PASS' if games_all >= 10000 and not err_all else 'FAIL'}; "
      f"without K = 0: {games_k4} games, {err_k4} errors")
