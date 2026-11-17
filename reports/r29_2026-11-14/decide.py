"""r29's decision (KNOWLEDGE/2026-11-14/208 §5), applied mechanically once the A/B's reads are in.

    .venv/bin/python reports/r29_2026-11-14/decide.py OUT_DIR      (queue.sh runs it)
    .venv/bin/python reports/r29_2026-11-14/decide.py --self-test

It reads the queue's directory, writes OUT_DIR/decision.json and prints one line, which the queue
logs, with every number it used.

- B1, the harm screen: the mean over the pairs k = 70, 80, 90, 100 that were played of b_k's
  score against a_k (b1_<k>/metrics.jsonl, the eval row's ``snap:opp`` score). Its 95% interval
  is ±1.96 × √(mean deal se² / n + 2 × 0.0070² / n): each pair's deal se by the learner's
  deal-level rule (learner.deal_interval: the deal scores' sd over √deals) on its
  eval_rows.jsonl, and r28's snapshot sd 0.0070 once for each snapshot of a pair. Falsified when
  the upper bound is below 0.50.
- B2 on L: the mean of B's snapshot ratings minus the mean of A's (rate_<player>.json, rate.py's
  output). Each side's se is √(mean rating se² / n + 4.9² / n), a rating's se being its 95%
  interval's width / 3.92, and the difference's √(se_A² + se_B²). The veto fires when the
  difference's upper bound is below 0.
- An arm is killed when its guard stopped it or the queue's progress check ended it (208 §3: the
  check stands in for K7), as the queue wrote in arm_<a>.done.
- Both arms killed: nothing resumes. B1 falsified, B2's veto or B killed: A resumes, unless A was
  killed. Otherwise B resumes. A read with no data vetoes nothing, and the line says so.

Standard library only, as the queue runs it: evalrows' rules for a deal are restated in
``deal_scores``, and ``--self-test`` checks them and every branch on synthetic runs.
"""

from __future__ import annotations

import json
import math
import statistics
import sys
import tempfile
from pathlib import Path

Z = 1.96
SNAP_SD = 0.0070  # r28's snapshot sd in score (208 §1), in B1's interval
SNAP_SD_ELO = 4.9  # the same in Elo, in B2's
PCTS = (70, 80, 90, 100)
KILLED = ("guard", "stall", "restarts")  # the queue's words for an arm a kill criterion ended


def rows(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text().splitlines()] if path.exists() else []


def deal_scores(path: Path) -> list[float]:
    """Each valid deal's score by evalrows' rules (tools/selfplay/evalrows.py): a game scores 1
    for a win, 0 for a loss and 0.5 for any draw; a deal counts only with both of its games,
    neither void nor leaky, and scores their mean; a row written again for the same deal and
    seat replaces the earlier one."""
    games: dict[tuple, dict[int, dict]] = {}
    for r in rows(path):
        deal = (r.get("opp"), r.get("set_code"), r.get("pool"), r["seed"], r.get("deck_mode"))
        games.setdefault(deal, {})[r["a_seat"]] = r
    return [sum(0.5 if r["outcome"] != "win" else float(r["winner"] == r["a_seat"])
                for r in g.values()) / 2
            for g in games.values()
            if set(g) == {0, 1} and not any(r["outcome"].startswith("void") or r.get("leaky")
                                            for r in g.values())]


def deal_se(scores: list[float]) -> float:
    """learner.deal_interval's se: the deal scores' sd over √deals (its interval is (0, 1) below
    two deals, a se of 0.5 / 1.96)."""
    return statistics.stdev(scores) / math.sqrt(len(scores)) if len(scores) >= 2 else 0.5 / Z


def read_b1(out: Path) -> dict:
    pairs = {}
    for k in PCTS:
        run = out / f"b1_{k}"
        ev = [r for r in rows(run / "metrics.jsonl") if r.get("event") == "eval" and "snap:opp" in r]
        if ev:
            scores = deal_scores(run / "eval_rows.jsonl")
            pairs[k] = {"score": ev[-1]["snap:opp"]["score"], "deals": len(scores),
                        "se": deal_se(scores)}
    if not pairs:
        return {"pairs": {}}
    n = len(pairs)
    mean = sum(p["score"] for p in pairs.values()) / n
    se = math.sqrt(sum(p["se"] ** 2 for p in pairs.values()) / n / n + 2 * SNAP_SD ** 2 / n)
    return {"pairs": pairs, "n": n, "mean": mean, "se": se, "ci95": [mean - Z * se, mean + Z * se],
            "falsified": mean + Z * se < 0.50}


def read_b2(out: Path) -> dict:
    ratings = {}
    for p in ["init"] + [f"{arm}{k}" for arm in "ab" for k in PCTS]:
        if (out / f"rate_{p}.json").exists():
            r = json.loads((out / f"rate_{p}.json").read_text())
            ratings[p] = {"elo": r["elo"], "se": (r["ci95"][1] - r["ci95"][0]) / 3.92}
    sides = {}
    for arm in "ab":
        rs = [ratings[f"{arm}{k}"] for k in PCTS if f"{arm}{k}" in ratings]
        if rs:
            n = len(rs)
            sides[arm] = {"n": n, "mean": sum(r["elo"] for r in rs) / n,
                          "se": math.sqrt(sum(r["se"] ** 2 for r in rs) / n / n + SNAP_SD_ELO ** 2 / n)}
    b2 = {"ratings": ratings, "sides": sides}
    if len(sides) == 2:
        diff = sides["b"]["mean"] - sides["a"]["mean"]
        se = math.hypot(sides["a"]["se"], sides["b"]["se"])
        b2 |= {"diff": diff, "se": se, "ci95": [diff - Z * se, diff + Z * se],
               "veto": diff + Z * se < 0}
    return b2


def choose(b1: dict, b2: dict, ends: dict[str, str]) -> tuple[str | None, str]:
    """208 §5 on the reads and the arms' ends: the arm that resumes (or None) and why."""
    killed = {arm: ends[arm] in KILLED for arm in "ab"}
    if killed["a"] and killed["b"]:
        return None, f"both arms were killed (A: {ends['a']}, B: {ends['b']})"
    against_b = (["B1 falsified"] * bool(b1.get("falsified")) + ["B2's veto"] * bool(b2.get("veto"))
                 + [f"B was killed ({ends['b']})"] * killed["b"])
    if against_b:
        if killed["a"]:
            return None, f"{', '.join(against_b)}, and A was killed ({ends['a']})"
        return "a", ", ".join(against_b)
    return "b", "neither read vetoes B and B was not killed"


def decide(out: Path) -> dict:
    ends = {}
    for arm in "ab":
        done = out / f"arm_{arm}.done"
        ends[arm] = (done.read_text().split() or ["unknown"])[0] if done.exists() else "unknown"
    b1, b2 = read_b1(out), read_b2(out)
    resume, why = choose(b1, b2, ends)
    return {"resume": resume, "why": why, "arms": ends, "b1": b1, "b2": b2}


def line(d: dict) -> str:
    """The decision and every number behind it, on one line for the queue's log."""
    b1, b2 = d["b1"], d["b2"]
    if b1["pairs"]:
        pairs = ", ".join(f"{k}: {p['score']:.4f} se {p['se']:.4f} on {p['deals']} deals"
                          for k, p in b1["pairs"].items())
        s1 = (f"B1 {b1['mean']:.4f} [{b1['ci95'][0]:.4f}, {b1['ci95'][1]:.4f}] se {b1['se']:.4f}, "
              f"{b1['n']} pairs ({pairs}): {'falsified' if b1['falsified'] else 'not falsified'}")
    else:
        s1 = "B1: no pair was played, so no veto from it"
    ratings = ", ".join(f"{p} {r['elo']:.1f} se {r['se']:.1f}" for p, r in b2["ratings"].items())
    sides = "; ".join(f"{arm.upper()} {s['mean']:.1f} se {s['se']:.1f} over {s['n']}"
                      for arm, s in b2["sides"].items())
    if "diff" in b2:
        s2 = (f"B2 B-A {b2['diff']:+.1f} [{b2['ci95'][0]:+.1f}, {b2['ci95'][1]:+.1f}] se "
              f"{b2['se']:.1f} ({sides}; {ratings}): {'veto' if b2['veto'] else 'no veto'}")
    else:
        missing = " or ".join(arm.upper() for arm in "ab" if arm not in b2["sides"])
        s2 = f"B2: no rating for {missing}, so no veto from it ({ratings or 'no rating'})"
    arms = f"arms ended: A {d['arms']['a']}, B {d['arms']['b']}"
    resume = f"{d['resume'].upper()} resumes" if d["resume"] else "nothing resumes"
    return f"decide: {s1}. {s2}. {arms}. {resume}: {d['why']}"


def main(out: Path) -> int:
    d = decide(out)
    (out / "decision.json").write_text(json.dumps(d, indent=1) + "\n")
    print(line(d))
    return 0


# ---------------------------------------------------------------------------------- self-test

def _pair(out: Path, k: int, results: list[tuple]) -> None:
    """A synthetic B1 run: one deal per (seat-0 game, seat-1 game) result of the evaluated seat
    (1 win, 0 loss, None a draw), its eval rows and its eval row."""
    run = out / f"b1_{k}"
    run.mkdir(parents=True)
    lines = []
    for seed, games in enumerate(results):
        for seat, res in enumerate(games):
            lines.append({"seed": seed, "a_seat": seat, "opp": "snap:opp", "set_code": "M21",
                          "pool": "verified", "deck_mode": "coherent", "leaky": 0,
                          "outcome": "draw-cap" if res is None else "win",
                          "winner": None if res is None else seat if res else 1 - seat})
    (run / "eval_rows.jsonl").write_text("".join(json.dumps(x) + "\n" for x in lines))
    score = statistics.mean(deal_scores(run / "eval_rows.jsonl"))
    (run / "metrics.jsonl").write_text(json.dumps(
        {"event": "eval", "tag": "eval-only", "snap:opp": {"score": round(score, 4)}}) + "\n")


def _rate(out: Path, player: str, elo: float, half: float) -> None:
    (out / f"rate_{player}.json").write_text(json.dumps(
        {"player": player, "elo": elo, "ci95": [elo - half, elo + half], "deals": 2000}) + "\n")


def _case(out: Path, ends: dict[str, str], b1_score: float | None, b_elo: float | None) -> dict:
    """A queue directory: the arms' ends, 4 B1 pairs of 400 deals scoring b1_score, A's four
    ratings at 600 and B's at b_elo (a read is left out when its value is None)."""
    out.mkdir()
    for arm, end in ends.items():
        (out / f"arm_{arm}.done").write_text(end + "\n")
    if b1_score is not None:
        wins = round(b1_score * 400)
        for k in PCTS:
            _pair(out, k, [(1, 1)] * wins + [(0, 0)] * (400 - wins))
    _rate(out, "init", 590.0, 8.0)
    if b_elo is not None:
        for k in PCTS:
            _rate(out, f"a{k}", 600.0, 8.0)
            _rate(out, f"b{k}", b_elo, 8.0)
    return decide(out)


def self_test(tmp: Path) -> None:
    # evalrows' rules: a void game drops its deal, so does a leaky one or a missing seat; a draw
    # scores 0.5; a row written again replaces the earlier one
    _pair(tmp / "rules", 70, [(1, 1), (1, 0), (None, 1), (0, 0)])
    path = tmp / "rules" / "b1_70" / "eval_rows.jsonl"
    deal = {"opp": "snap:opp", "set_code": "M21", "pool": "verified", "deck_mode": "coherent"}
    extra = [{**deal, "seed": 9, "a_seat": 0, "outcome": "void-crash", "winner": None},
             {**deal, "seed": 9, "a_seat": 1, "outcome": "win", "winner": 1},
             {**deal, "seed": 8, "a_seat": 0, "outcome": "win", "winner": 0, "leaky": 1},
             {**deal, "seed": 8, "a_seat": 1, "outcome": "win", "winner": 1},
             {**deal, "seed": 7, "a_seat": 0, "outcome": "win", "winner": 0},
             # deal 3, lost twice above, is written again: its seat-1 game is now a win
             {**deal, "seed": 3, "a_seat": 1, "leaky": 0, "outcome": "win", "winner": 1}]
    with path.open("a") as fh:
        fh.write("".join(json.dumps(x) + "\n" for x in extra))
    scores = deal_scores(path)
    assert scores == [1.0, 0.5, 0.75, 0.5], scores
    assert abs(deal_se(scores) - statistics.stdev(scores) / 2) < 1e-12
    assert deal_se([1.0]) == 0.5 / Z

    # B1's interval: two pairs, se² averaged over the pairs, then over n, plus 2 x 0.0070² / n
    _pair(tmp / "b1", 70, [(1, 1), (0, 0), (1, 0), (1, 1)])
    _pair(tmp / "b1", 90, [(0, 0), (1, 0), (1, 0), (0, 1)])
    b1 = read_b1(tmp / "b1")
    s70, s90 = deal_se([1, 0, 0.5, 1]), deal_se([0, 0.5, 0.5, 0.5])
    want = math.sqrt((s70 ** 2 + s90 ** 2) / 2 / 2 + 2 * SNAP_SD ** 2 / 2)
    assert b1["n"] == 2 and abs(b1["mean"] - (0.625 + 0.375) / 2) < 1e-9, b1
    assert abs(b1["se"] - want) < 1e-12, (b1["se"], want)

    # B2's: a rating's se is its interval / 3.92; each side √(mean se² / n + 4.9² / n)
    (tmp / "b2").mkdir()
    for k in PCTS:
        _rate(tmp / "b2", f"a{k}", 600.0 + k / 10, 7.84)
        _rate(tmp / "b2", f"b{k}", 610.0, 3.92)
    b2 = read_b2(tmp / "b2")
    se_a = math.sqrt(4.0 ** 2 / 4 + 4.9 ** 2 / 4)
    se_b = math.sqrt(2.0 ** 2 / 4 + 4.9 ** 2 / 4)
    assert abs(b2["sides"]["a"]["se"] - se_a) < 1e-9 and abs(b2["sides"]["b"]["se"] - se_b) < 1e-9
    assert abs(b2["diff"] - (610.0 - 608.5)) < 1e-9 and not b2["veto"], b2

    # every branch of 208 §5
    budget = {"a": "budget", "b": "budget"}
    cases = [
        ("no veto: B", budget, 0.50, 600.0, "b"),
        ("B1 falsified: A", budget, 0.40, 600.0, "a"),
        ("B2's veto: A", budget, 0.50, 570.0, "a"),
        ("B stopped by its guard: A", {"a": "budget", "b": "guard"}, 0.50, 600.0, "a"),
        ("B ended by the progress check: A", {"a": "budget", "b": "restarts"}, 0.50, 600.0, "a"),
        ("A stopped by its guard, no veto: B", {"a": "guard", "b": "budget"}, 0.50, 600.0, "b"),
        ("B1 falsified, A killed: none", {"a": "stall", "b": "budget"}, 0.40, 600.0, None),
        ("both killed: none", {"a": "guard", "b": "guard"}, 0.50, 600.0, None),
        ("B ended inactive, not killed: B", {"a": "budget", "b": "inactive"}, 0.50, 600.0, "b"),
        ("no read at all: B", budget, None, None, "b"),
    ]
    for i, (name, ends, score, b_elo, want_arm) in enumerate(cases):
        d = _case(tmp / f"case{i}", ends, score, b_elo)
        assert d["resume"] == want_arm, (name, d["resume"], d["why"])
        if score is None:
            assert "B1: no pair was played, so no veto from it" in line(d), line(d)
            assert "B2: no rating for A or B, so no veto from it" in line(d), line(d)
        print(f"ok  {name}  ({d['why']})")
    print(line(_case(tmp / "example", budget, 0.40, 590.0)))
    print("self-test passed")


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        with tempfile.TemporaryDirectory() as tmp:
            self_test(Path(tmp))
        sys.exit(0)
    sys.exit(main(Path(sys.argv[1])))
