"""Score the ceiling-read window (reports/ceiling_window/queue.sh): docs/PLAN_CEILING.md §14.1's
skill spread per deal shape and §7.2's held-out pool L, read from the jobs' eval rows by evalrows'
rules (a void or leaky game drops its deal; a deal scores the mean of its two seat-swapped games).

    env PYTHONPATH=. .venv/bin/python reports/ceiling_window/score.py OUT_DIR

1. The skill spread of r28's latest network NET per deal shape (coherent, package, drafted): (a)
   NET searched at n = 4 against NET raw (jobs a_<shape>), (b) NET raw against the heuristic
   (b_<shape>). Per shape: the evaluated seat's score, its standard error over deals and a normal
   95% interval, the Elo it is worth, how the deals fell (the evaluated player won both games, lost
   both, or one each), turns per game, dropped deals, and the search's counts per game. Then each
   shape minus coherent, paired by seed (every shape is dealt from the same seeds, and a drafted
   deck is its seed's coherent deck after 8 critic swaps), with a bootstrap 95% interval over the
   shared seeds and the correlation of the paired deal scores.
2. L (L_*): rate.fit over every shape, the candidate for the frozen ratings (`rate.py fit` writes
   them); the same fit per shape, the networks' Elo range per shape, and each pairing's score per
   shape (exploratory: does the ladder spread out on the richer decks?).
3. NET on L (b_*, rate_*): rate.rate against the all-shape fit (exploratory).
"""

from __future__ import annotations

import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

from tools.selfplay import evalrows as ER
from tools.selfplay import rate as RT

SHAPES = ("coherent", "package", "drafted")


def shape(deck_mode: str) -> str:
    """A deal's shape: its deck mode without a drafted mode's K and critic hash."""
    return str(deck_mode).split(":")[0]


def jobs(out: Path, prefix: str) -> list[Path]:
    return sorted(p for p in out.glob(prefix + "_*") if (p / "eval_rows.jsonl").exists())


def mean_se(xs: list[float]) -> tuple[float, float]:
    m = sum(xs) / len(xs)
    if len(xs) < 2:
        return m, math.nan
    return m, math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1) / len(xs))


def elo(p: float) -> float:
    return 400 * math.log10(p / (1 - p)) if 0 < p < 1 else math.copysign(math.inf, p - 0.5)


def last_eval(run: Path) -> dict:
    """The run's evaluation summary (learner.eval_summary), or {} for a run cut before it."""
    path = run / "metrics.jsonl"
    rows = [json.loads(x) for x in path.read_text().splitlines()] if path.exists() else []
    ev = [r for r in rows if r.get("event") == "eval"]
    return ev[-1] if ev else {}


def spread(runs: list[Path]) -> tuple[dict, dict]:
    """The rows and the deal scores by seed, per shape, of one measure's runs (one opponent)."""
    rows: dict[str, dict] = {}
    scores: dict[str, dict[int, float]] = {}
    for run in runs:
        games = ER.read(run / "eval_rows.jsonl")
        valid = ER.valid(games)
        for sh in {shape(k[4]) for k in games}:
            rows[sh] = {"run": run, "all": [k for k in games if shape(k[4]) == sh],
                        "valid": {k: g for k, g in valid.items() if shape(k[4]) == sh}}
            scores[sh] = {k[3]: (ER.score(g[0]) + ER.score(g[1])) / 2
                          for k, g in rows[sh]["valid"].items()}
    return rows, scores


def paired(base: dict[int, float], other: dict[int, float], reps: int = 10000) -> str:
    """other minus base over the seeds both hold, with a bootstrap 95% interval over the seeds;
    then the same difference unpaired, over every deal of each (the better estimate when the deal
    scores do not correlate and one shape has more deals)."""
    seeds = sorted(set(base) & set(other))
    if len(seeds) < 2:
        return f"{len(seeds)} shared seeds"
    d = np.array([other[s] - base[s] for s in seeds])
    rng = np.random.default_rng(0)
    boot = np.concatenate([d[rng.integers(0, len(d), (1000, len(d)))].mean(1)
                           for _ in range(reps // 1000)])
    lo, hi = np.quantile(boot, [0.025, 0.975])
    xb, xo = np.array([base[s] for s in seeds]), np.array([other[s] for s in seeds])
    corr = np.corrcoef(xb, xo)[0, 1] if xb.std() > 0 and xo.std() > 0 else math.nan
    (mb, sb), (mo, so) = mean_se(list(base.values())), mean_se(list(other.values()))
    su = math.sqrt(sb ** 2 + so ** 2)
    return (f"{d.mean():+.4f} [{lo:+.4f}, {hi:+.4f}] (SE {d.std(ddof=1) / math.sqrt(len(d)):.4f}) "
            f"over {len(seeds)} shared seeds, deal-score correlation {corr:+.2f}; unpaired "
            f"{mo - mb:+.4f} [{mo - mb - 1.96 * su:+.4f}, {mo - mb + 1.96 * su:+.4f}] "
            f"({len(base)} and {len(other)} deals)")


def part1(out: Path) -> None:
    net = out / "net.sha256"
    first = (jobs(out, "a") + jobs(out, "b"))[:1]
    init = json.loads((first[0] / "manifest.json").read_text())[-1] if first else {}
    print("== 1. The skill spread per deal shape (PLAN_CEILING §14.1)")
    print(f"NET {init.get('args', {}).get('init')}, sha256 "
          f"{net.read_text().strip()[:16] if net.exists() else '?'}; code {init.get('git_commit')}"
          f"{' (dirty)' if init.get('git_dirty') else ''}")
    for prefix, title in (("a", "(a) NET searched at n = 4 against NET raw"),
                          ("b", "(b) NET raw against the heuristic")):
        rows, scores = spread(jobs(out, prefix))
        print(f"\n{title}")
        print(f"{'shape':<9} {'deals':>5} {'score':>7} {'SE':>7} {'95%':>17} {'Elo':>6} "
              f"{'won 2':>6} {'lost 2':>6} {'split':>6} {'turns':>6} {'dropped':>7} "
              f"{'srch/g':>6} {'chg':>6} {'clear/g':>7}")
        for sh in SHAPES:
            if sh not in rows:
                print(f"{sh:<9} not played")
                continue
            r = rows[sh]
            xs = list(scores[sh].values())
            m, se = mean_se(xs)
            fell = [sorted(ER.score(x) for x in g.values()) for g in r["valid"].values()]
            n = len(fell)
            turns = [x["turns"] for g in r["valid"].values() for x in g.values()]
            st = last_eval(r["run"]).get("search", {})
            searched, changed, clear = ((st.get("searched", 0) / (2 * n),
                                         st.get("changed", 0) / max(st.get("searched", 0), 1),
                                         st.get("clear", 0) / (2 * n)) if st else (math.nan,) * 3)
            print(f"{sh:<9} {n:>5} {m:>7.4f} {se:>7.4f} [{m - 1.96 * se:.4f}, {m + 1.96 * se:.4f}] "
                  f"{elo(m):>+6.1f} {sum(f == [1.0, 1.0] for f in fell) / n:>6.3f} "
                  f"{sum(f == [0.0, 0.0] for f in fell) / n:>6.3f} "
                  f"{sum(f not in ([1.0, 1.0], [0.0, 0.0]) for f in fell) / n:>6.3f} "
                  f"{sum(turns) / len(turns):>6.1f} {len(r['all']) - n:>7} "
                  f"{searched:>6.2f} {changed:>6.3f} {clear:>7.3f}")
        for sh in SHAPES[1:]:
            if sh in scores and "coherent" in scores:
                print(f"  {sh} - coherent: {paired(scores['coherent'], scores[sh])}")


def short(members: set[str]) -> dict[str, str]:
    """Each member's label: its checkpoint below runs/, +s<n> when it searches; the full name
    when two members would share a label."""
    out = {}
    for m in members:
        parts = m.split("+")
        n = [p[2:] for p in parts if p.startswith("n=")]
        out[m] = parts[0].split("/runs/")[-1].removeprefix("selfplay/") + (f"+s{n[0]}" if n else "")
    if len(set(out.values())) < len(out):
        return {m: m for m in members}
    return out


def run_shape(run: Path) -> str:
    shapes = {shape(k[4]) for k in ER.read(run / "eval_rows.jsonl")}
    if len(shapes) != 1:
        raise ValueError(f"{run}: deals of {len(shapes)} shapes, not one")
    return shapes.pop()


def part2(out: Path) -> dict[str, float]:
    runs = jobs(out, "L")
    print("\n== 2. The held-out pool L (PLAN_CEILING §7.2): Bradley-Terry ratings, random = 0")
    if not runs:
        print("no L job played")
        return {}
    pool = RT.fit(runs)
    by_shape = {sh: RT.fit([r for r in runs if run_shape(r) == sh])
                for sh in SHAPES if any(run_shape(r) == sh for r in runs)}
    pairs: dict = defaultdict(lambda: defaultdict(list))
    for run in runs:
        per_deal = defaultdict(list)
        for a, b, deal, s in RT.games(run):
            per_deal[(a, b, deal)].append(s)
        for (a, b, deal), ss in per_deal.items():
            sc = sum(ss) / len(ss)
            if a > b:
                a, b, sc = b, a, 1 - sc
            pairs[(a, b)][shape(deal[4])].append(sc)
    label = short(set(pool))
    print(f"{'member':<34} {'all':>7} " + " ".join(f"{sh:>9}" for sh in by_shape))
    for m in sorted(pool, key=pool.get):
        print(f"{label[m]:<34} {pool[m]:>7.1f} "
              + " ".join(f"{fit.get(m, math.nan):>9.1f}" for fit in by_shape.values()))
    nets = [m for m in pool if m.split("+")[0] not in ER.SCRIPTED]
    print(f"{'networks: Elo range (exploratory)':<34} "
          f"{max(pool[m] for m in nets) - min(pool[m] for m in nets):>7.1f} " + " ".join(
              f"{max(f[m] for m in nets if m in f) - min(f[m] for m in nets if m in f):>9.1f}"
              for f in by_shape.values()))
    print("\npairings: the first member's score over deals (+- SE, deals); the all-shape fit's "
          "expected score and the observed one's distance from it in SEs")
    for (a, b), per in sorted(pairs.items(), key=lambda kv: (pool[kv[0][0]], pool[kv[0][1]])):
        cells = []
        for sh in (*SHAPES, "all"):
            xs = [x for v in per.values() for x in v] if sh == "all" else per.get(sh, [])
            if xs:
                m, se = mean_se(xs)
                cells.append(f"{sh} {m:.3f} +- {se:.3f} ({len(xs)})")
        expected = 1 / (1 + 10 ** ((pool[b] - pool[a]) / 400))
        print(f"  {label[a]} vs {label[b]}: " + "; ".join(cells)
              + f"; fit {expected:.3f}, z {(m - expected) / se if se > 0 else math.nan:+.1f}")
    return pool


def part3(out: Path, pool: dict[str, float]) -> None:
    runs = jobs(out, "b") + jobs(out, "rate")
    print("\n== 3. NET on L (rate.py rate against the all-shape fit; exploratory)")
    if not (runs and pool):
        print("not played")
        return
    try:
        print(json.dumps(RT.rate(pool, runs)))
    except ValueError as e:
        print(f"not rated: {e}")


def main(argv: list[str]) -> None:
    out = Path(argv[0])
    part1(out)
    part3(out, part2(out))


if __name__ == "__main__":
    main(sys.argv[1:])
