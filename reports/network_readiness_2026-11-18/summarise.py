"""Tables from meaningless.py's output (docs/PLAN_NETWORK_READINESS.md §2-§4).

    .venv/bin/python reports/network_readiness_2026-11-18/summarise.py OUT.jsonl [OUT2.jsonl ...]

Per ask kind: decisions, how many were tested by copies, decisions of nothing (one state class),
decisions with redundant options (fewer state classes than tested options), the options that were
redundant, decisions where one encoding class holds options of different state classes (the
network cannot tell them apart), and the copies' statuses. Then per game; then the value head's
explained variance by turn; then the observation-gap and knowledge indicators.
"""

from __future__ import annotations

import gzip
import json
import sys
from collections import Counter, defaultdict

import numpy as np


def _open(path: str):
    """A detector output, raw or gzipped (the committed copies are gzipped)."""
    return gzip.open(path, "rt") if path.endswith(".gz") else open(path)


def load(paths: list[str]) -> tuple[list[dict], list[dict]]:
    rows, games = [], []
    for k, p in enumerate(paths):
        for line in _open(p):
            r = json.loads(line)
            r["gid"] = (k, r["gid"])
            rows.append(r)
        for line in _open(p.replace(".jsonl", "_games.jsonl")):
            g = json.loads(line)
            g["gid"] = (k, g["gid"])
            games.append(g)
    return rows, games


def classify(r: dict) -> dict:
    cls = [c for c in r.get("cls", []) if c >= 0]
    out = {"tested": len(cls) >= 2, "nothing": False, "redundant": False, "red_opts": 0,
           "blind": False}
    if len(cls) < 2:
        return out
    k = len(set(cls))
    # a decision of nothing needs every option tested: a sample of a big menu (a name ask's 280
    # card names, 16 tested) that lands in one class says nothing about the rest
    out["nothing"] = k == 1 and len(cls) == len(r["cls"])
    out["redundant"] = k < len(cls)
    out["red_opts"] = len(cls) - k
    by_enc = defaultdict(set)
    for c, e in zip(r["cls"], r["enc"], strict=True):
        if c >= 0:
            by_enc[e].add(c)
    out["blind"] = any(len(s) > 1 for s in by_enc.values())
    return out


def main() -> int:
    rows, games = load(sys.argv[1:])
    ok = [g for g in games if not str(g["outcome"]).startswith("void")]
    print(f"games {len(games)} (void {len(games) - len(ok)}), decisions {len(rows)}, "
          f"per game {len(rows) / max(len(games), 1):.1f}, turns {np.mean([g['turns'] for g in ok]):.1f}")
    print(f"wall per game {np.mean([g['wall_s'] for g in games]):.1f} s, detect {np.mean([g['detect_s'] for g in games]):.1f} s")
    kinds = defaultdict(Counter)
    status = Counter()
    examples = defaultdict(list)
    for r in rows:
        c = classify(r)
        k = kinds[r["kind"]]
        k["n"] += 1
        k["opts"] += r["n"]
        k["tested"] += c["tested"]
        k["nothing"] += c["nothing"]
        k["redundant"] += c["redundant"]
        k["red_opts"] += c["red_opts"]
        k["blind"] += c["blind"]
        for s, n in (r.get("status") or {}).items():
            status[s] += n
        if "det" in r:
            status["det_" + str(r["det"])] += 1
        ex = (r["site"], r["n"], r.get("cls"), r["enc"], r.get("toks"))
        if c["nothing"] and len(examples[("nothing", r["kind"])]) < 4:
            examples[("nothing", r["kind"])].append(ex)
        if c["redundant"] and not c["nothing"] and len(examples[("redundant", r["kind"])]) < 3:
            examples[("redundant", r["kind"])].append(ex)
        if c["blind"] and len(examples[("blind", r["kind"])]) < 3:
            examples[("blind", r["kind"])].append(ex)
    n_games = max(len(games), 1)
    print("\nkind | decisions | per game | tested | nothing | per game | redundant | redundant options | blind")
    tot = Counter()
    for kind, k in sorted(kinds.items(), key=lambda kv: -kv[1]["n"]):
        print(f"{kind} | {k['n']} | {k['n'] / n_games:.2f} | {k['tested']} | {k['nothing']} | "
              f"{k['nothing'] / n_games:.3f} | {k['redundant']} | {k['red_opts']} | {k['blind']}")
        tot.update(k)
    print(f"ALL | {tot['n']} | {tot['n'] / n_games:.2f} | {tot['tested']} | {tot['nothing']} | "
          f"{tot['nothing'] / n_games:.3f} | {tot['redundant']} | {tot['red_opts']} | {tot['blind']}")
    print("\ncopy statuses:", dict(status.most_common(12)))
    for key, ex in sorted(examples.items()):
        print(key)
        for e in ex:
            print("   ", e)
    # the value head's explained variance by turn bucket (seat's own result)
    buckets = [(1, 2), (3, 4), (5, 6), (7, 9), (10, 14), (15, 999)]
    vs = defaultdict(list)
    by_game = defaultdict(lambda: defaultdict(list))  # bucket -> game -> [(v, z)]
    for g in ok:
        if g["outcome"] != "win":
            continue
        for seat, turn, v in g["values"]:
            z = 1.0 if g["winner"] == seat else -1.0
            for lo, hi in buckets:
                if lo <= turn <= hi:
                    vs[(lo, hi)].append((v, z))
                    by_game[(lo, hi)][g["gid"]].append((v, z))
    # a game's decisions share its result, so the standard errors resample whole games
    rng = np.random.default_rng(0)
    se: dict = {}
    for b, games_b in by_game.items():
        keys = list(games_b)
        evs, cs = [], []
        for _ in range(300):
            pick = [games_b[keys[i]] for i in rng.integers(0, len(keys), len(keys))]
            a = np.array([x for gl in pick for x in gl])
            v, z = a[:, 0], a[:, 1]
            evs.append(1 - np.var(z - v) / max(np.var(z), 1e-9))
            cs.append(np.cov(z, v)[0, 1] / max(np.var(v), 1e-9))
        se[b] = (np.std(evs), np.std(cs))
    print("\nvalue EV by turn (decisions, EV, mean |z - v|, Brier on (v+1)/2, mean |v|, "
          "c = Cov(z,v)/Var(v), EV of the baseline c*v):")
    allv = []
    for b in buckets:
        a = np.array(vs[b]) if vs[b] else np.zeros((0, 2))
        allv += vs[b]
        if len(a) > 50:
            v, z = a[:, 0], a[:, 1]
            ev = 1 - np.var(z - v) / max(np.var(z), 1e-9)
            brier = np.mean(((v + 1) / 2 - (z + 1) / 2) ** 2)
            c = np.cov(z, v)[0, 1] / max(np.var(v), 1e-9)
            ev_c = 1 - np.var(z - c * v) / max(np.var(z), 1e-9)
            s_ev, s_c = se.get(b, (float("nan"), float("nan")))
            print(f"  turns {b}: {len(a)} | {ev:.3f} (se {s_ev:.3f}) | {np.mean(np.abs(z - v)):.3f} | "
                  f"{brier:.3f} | {np.mean(np.abs(v)):.3f} | {c:.3f} (se {s_c:.3f}) | {ev_c:.3f}")
    a = np.array(allv)
    if len(a):
        print(f"  all: {len(a)} | {1 - np.var(a[:, 1] - a[:, 0]) / np.var(a[:, 1]):.3f}")
    # gap indicators: share of decisions where each is on
    gap = Counter()
    for r in rows:
        for k2, v in (r.get("gaps") or {}).items():
            gap[k2] += v > 0
    print("\nobservation-gap and knowledge indicators: decisions with it on (per game)")
    for k2, v in gap.most_common():
        print(f"  {k2}: {v} ({v / n_games:.2f} per game, {v / max(len(rows), 1):.4f} of decisions)")
    know = Counter()
    for g in games:
        know.update(g.get("knowledge") or {})
    print("\nknowledge events per game:", {k2: round(v / n_games, 2) for k2, v in know.most_common()})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
