"""Kill test K1b: does effect prediction on unseen cards improve with training volume (more sets)?

    MTG_REPO=<tree> .venv/bin/python tools/k1/curve.py --data DIR --out FILE.json [--cap 60]

The owner's reading of K1 (2026-10-27): about 200 training cards is far too few to learn encodings
of the atoms that generalize. "If volume is what we need, then try to give it volume." So: the same
task as tools/k1/train.py, trained on pools of 1, 4, 10 and 16 real sets. M14 is not among them:
its castable pool has 9 mana-capable cards, under the stress deck builder's MIN_MANA_SOURCES of 10.
Each step is scored on test sets that stay fixed, and unseen, at every step:
- **heldout**: 20% of all oracle ids in the 16-set pool (by hash), removed from training at every
  step;
- **M20** and **KHM**: cards in none of the 16 training sets.

Encoders:
- state (the floor);
- ir-bag;
- ir-pairs (IR tokens plus parent>child pairs);
- text-bag;
- hybrid (IR plus text);
- name, at the last step only. It cannot transfer by construction.

Metrics, on effect lanes:
- pooled R²;
- **per-card skill**: 1 − MSE(model)/MSE(state floor) for each test card, as the median over cards
  and the share of cards above 0.1. A single extreme card cannot dominate it.
- Medians are reported over all test cards and over **effect cards**, whose IR has a verb atom.
  Vanilla and keyword-only cards change no effect lane at resolution.
- Paired gaps between steps and between encoders, resampling test cards. The reading rules are in
  ``reports/k1b_2026-10-27_preregistration.md``.

Rows are capped per card per set (`--cap`) so frequently cast cards do not swamp the pool.
"""

from __future__ import annotations

import argparse
import itertools
import json
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import torch
import train as T

STEPS = (
    ("1 set", ("M21",)),
    ("4 sets", ("M21", "ZNR", "M19", "10E")),
    ("10 sets", ("M21", "ZNR", "M19", "10E", "M10", "M11", "M12", "M13", "M15", "ORI")),
    ("16 sets", ("M21", "ZNR", "M19", "10E", "M10", "M11", "M12", "M13", "M15", "ORI",
                 "DOM", "WAR", "FDN", "ELD", "THB", "IKO")),
)
ALL_TRAIN = STEPS[-1][1]
TESTS = ("heldout", "M20", "KHM")
POPULATIONS = ("effect", "all")


def capped(rows: list[dict[str, Any]], cap: int) -> list[dict[str, Any]]:
    """At most ``cap`` rows per card, chosen by a stable hash (no RNG, no order dependence)."""
    by_card: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_card[r["oid"]].append(r)
    out = []
    for group in by_card.values():
        group.sort(key=lambda r: T._h(f"cap:{r['seed']}:{r['turn']}:{r['pre']}"))
        out.extend(group[:cap])
    return out


def card_mse(pred: torch.Tensor, y: torch.Tensor, rows: list[dict[str, Any]]) -> dict[str, float]:
    """Effect-lane MSE of each test card over its own rows."""
    lanes = list(T.EFFECT_LANES)
    by_card: dict[str, list[int]] = defaultdict(list)
    for i, r in enumerate(rows):
        by_card[r["oid"]].append(i)
    return {oid: ((pred[idx][:, lanes] - y[idx][:, lanes]) ** 2).mean().item()
            for oid, idx in by_card.items()}


def skills(mse: dict[str, float], floor: dict[str, float], cards: set[str]) -> dict[str, float]:
    # a card the floor already predicts exactly carries no signal either way
    return {c: 1 - mse[c] / floor[c] for c in cards if c in mse and floor.get(c, 0) >= 1e-6}


def summary(values: dict[str, float]) -> dict[str, Any]:
    if not values:
        return {"cards": 0}
    v = list(values.values())
    return {"cards": len(v), "median_skill": round(statistics.median(v), 4),
            "share_above_0.1": round(sum(s > 0.1 for s in v) / len(v), 3)}


def paired_gap(a: dict[str, float], b: dict[str, float], key: str,
               draws: int = 1000) -> dict[str, Any]:
    """median(a) − median(b) over the cards both score, with a 95% card-resampling interval."""
    cards = sorted(set(a) & set(b))
    if not cards:
        return {"cards": 0}
    stream = T.rng.substream("bench", "k1b-paired", key)
    gaps = []
    for _ in range(draws):
        pick = [cards[stream.randrange(len(cards))] for _ in cards]
        gaps.append(statistics.median(a[c] for c in pick) - statistics.median(b[c] for c in pick))
    gaps.sort()
    point = statistics.median(a[c] for c in cards) - statistics.median(b[c] for c in cards)
    return {"cards": len(cards), "gap": round(point, 4),
            "ci95": [round(gaps[int(0.025 * draws)], 4), round(gaps[int(0.975 * draws) - 1], 4)]}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("--data", required=True)
    ap.add_argument("--cap", type=int, default=60)
    ap.add_argument("--epochs", type=int, default=15)
    ap.add_argument("--encoders", default="state,ir-bag,ir-pairs,text-bag,hybrid")
    ap.add_argument("--threads", type=int, default=12)
    ap.add_argument("--fully-compiled", action="store_true",
                    help="keep only rows of cards with nothing unparsed (amendment 1, rule 4)")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    torch.set_num_threads(args.threads)
    data = Path(args.data)
    started = time.perf_counter()
    inputs: dict = {}
    for code in (*ALL_TRAIN, "M20", "KHM"):
        for key, value in T.card_inputs(code).items():
            inputs.setdefault(key, value)
    rows_by_set = {code: capped(T.load(data, code), args.cap) for code in (*ALL_TRAIN, "M20", "KHM")}
    if args.fully_compiled:
        full = {oid for (oid, unit), card in inputs.items() if unit == "card" and card["full"]}
        rows_by_set = {code: [r for r in rows if r["oid"] in full]
                       for code, rows in rows_by_set.items()}
    pool_ids = {r["oid"] for code in ALL_TRAIN for r in rows_by_set[code]}
    held = {oid for oid in pool_ids if T._h(f"k1b:{oid}") < 0.2}
    tests = {
        "heldout": [r for code in ALL_TRAIN for r in rows_by_set[code] if r["oid"] in held],
        "M20": [r for r in rows_by_set["M20"] if r["oid"] not in pool_ids],
        "KHM": [r for r in rows_by_set["KHM"] if r["oid"] not in pool_ids],
    }
    effect_cards = {oid for (oid, unit), card in inputs.items()
                    if unit == "card" and any(t.startswith("Verb.") for t in card["ir"])}
    test_rows = [r for name in TESTS for r in tests[name]]
    bounds, at = {}, 0
    for name in TESTS:
        bounds[name] = (at, at + len(tests[name]))
        at += len(tests[name])
    population = {(name, pop): {r["oid"] for r in tests[name]
                                if pop == "all" or r["oid"] in effect_cards}
                  for name in TESTS for pop in POPULATIONS}
    report: dict[str, Any] = {
        "cap_rows_per_card_per_set": args.cap,
        "epochs": args.epochs,
        "fully_compiled_only": args.fully_compiled,
        "test_rows": {k: len(v) for k, v in tests.items()},
        "test_cards": {f"{n}/{p}": len(c) for (n, p), c in population.items()},
        "steps": {},
    }
    print(json.dumps({k: report[k] for k in ("test_rows", "test_cards")}), flush=True)
    # mse[step][encoder][test] = {oid: effect-lane MSE}, in this step's normalized units; raw is
    # the same in board units, so steps can be compared against one fixed floor (rule 6)
    mse: dict[str, dict[str, dict[str, dict[str, float]]]] = {}
    raw: dict[str, dict[str, dict[str, dict[str, float]]]] = {}
    for label, sets in STEPS:
        train = [r for code in sets for r in rows_by_set[code] if r["oid"] not in held]
        vocab = {"names": {c: i + 1 for i, c in enumerate(sorted({r["oid"] for r in train}))},
                 "ir": {}, "text": {}, "pairs": {}}
        for r in train:
            card = inputs.get((r["oid"], r["unit"])) or inputs.get((r["oid"], "card"))
            if card is None:
                continue
            for field in ("ir", "text", "pairs"):
                for t in card.get(field, ()):
                    vocab[field].setdefault(t, len(vocab[field]))
        pre = torch.tensor([r["pre"] for r in train], dtype=torch.float32)
        dlt = torch.tensor([r["delta"] for r in train], dtype=torch.float32)
        stats = {"s_mean": pre.mean(0), "s_std": pre.std(0).clamp(min=1e-3),
                 "y_std": dlt.std(0).clamp(min=1e-3)}
        table = T.CardTable(inputs, vocab)
        y = torch.tensor([r["delta"] for r in test_rows], dtype=torch.float32) / stats["y_std"]
        y_mean = (dlt / stats["y_std"]).mean(0)
        encoders = list(args.encoders.split(","))
        if label == STEPS[-1][0] and "name" not in encoders:
            encoders.append("name")
        train_cards = {r["oid"] for r in train}
        step: dict[str, Any] = {"sets": list(sets), "train_rows": len(train),
                                "train_cards": len(train_cards),
                                "train_effect_cards": len(train_cards & effect_cards),
                                "y_std": [round(v, 4) for v in stats["y_std"].tolist()]}
        mse[label], raw[label] = {}, {}
        for encoder in encoders:
            t0 = time.perf_counter()
            pred = T.fit_predict(encoder, train, test_rows, table, vocab, stats, args.epochs,
                                 seed=20261027)
            mse[label][encoder] = {}
            raw[label][encoder] = {}
            for name in TESTS:
                lo, hi = bounds[name]
                if hi == lo:
                    continue
                mse[label][encoder][name] = card_mse(pred[lo:hi], y[lo:hi], test_rows[lo:hi])
                raw[label][encoder][name] = card_mse(pred[lo:hi] * stats["y_std"],
                                                     y[lo:hi] * stats["y_std"], test_rows[lo:hi])
                cell: dict[str, Any] = {
                    "pooled_r2": T.r2(pred[lo:hi], y[lo:hi], y_mean, T.EFFECT_LANES)}
                floor = mse[label].get("state", {}).get(name)
                if floor is not None:
                    for pop in POPULATIONS:
                        cell[pop] = summary(skills(mse[label][encoder][name], floor,
                                                   population[(name, pop)]))
                step.setdefault(name, {})[encoder] = cell
            step[f"{encoder}_seconds"] = round(time.perf_counter() - t0, 1)
            print(json.dumps({label: {encoder: {n: step.get(n, {}).get(encoder) for n in TESTS}}}),
                  flush=True)
        report["steps"][label] = step
        Path(args.out).write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    # the per-card errors go to a side file first, so the paired gaps can be recomputed offline
    side = Path(args.out).with_suffix(".cards.json")
    side.write_text(json.dumps({"mse": mse, "raw": raw,
                                "population": {f"{n}/{p}": sorted(c)
                                               for (n, p), c in population.items()}}) + "\n",
                    encoding="utf-8")
    report["paired"] = paired_report(mse, raw, population)
    report["seconds"] = round(time.perf_counter() - started, 1)
    Path(args.out).write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(report["paired"], indent=1))
    print(f"done in {report['seconds']} s -> {args.out}")
    return 0


def paired_report(mse: dict, raw: dict, population: dict) -> dict[str, Any]:
    """The pre-registered comparisons (rules 2 to 6), each as a paired median gap."""
    first, last = STEPS[0][0], STEPS[-1][0]
    labels = [label for label, _ in STEPS if label in mse]
    out: dict[str, Any] = {}

    def skill(label: str, encoder: str, name: str, pop: str, fixed: bool = False):
        if fixed:  # rule 6: board units, against the first step's floor
            return skills(raw[label][encoder][name], raw[first]["state"][name],
                          population[(name, pop)])
        return skills(mse[label][encoder][name], mse[label]["state"][name],
                      population[(name, pop)])

    for name in TESTS:
        if name not in mse[first].get("state", {}):
            continue
        for pop in POPULATIONS:
            key = f"{name}/{pop}"
            cell: dict[str, Any] = {}
            if last in mse:
                for encoder in ("ir-bag", "ir-pairs", "text-bag", "hybrid"):
                    if encoder not in mse[last] or encoder not in mse[first]:
                        continue
                    cell[f"{encoder}: {last} - {first}"] = paired_gap(
                        skill(last, encoder, name, pop), skill(first, encoder, name, pop),
                        f"{key}:{encoder}:vol")
                    cell[f"{encoder}: {last} - {first}, fixed floor"] = paired_gap(
                        skill(last, encoder, name, pop, fixed=True),
                        skill(first, encoder, name, pop, fixed=True),
                        f"{key}:{encoder}:vol-fixed")
                for a, b in itertools.pairwise(labels):
                    if "ir-bag" not in mse[a] or "ir-bag" not in mse[b]:
                        continue
                    cell[f"ir-bag: {b} - {a}"] = paired_gap(
                        skill(b, "ir-bag", name, pop), skill(a, "ir-bag", name, pop),
                        f"{key}:ir-bag:{a}>{b}")
                for a, b in (("ir-bag", "text-bag"), ("ir-pairs", "ir-bag"),
                             ("hybrid", "ir-bag"), ("name", "state")):
                    if a in mse[last] and b in mse[last]:
                        cell[f"{last}: {a} - {b}"] = paired_gap(
                            skill(last, a, name, pop), skill(last, b, name, pop),
                            f"{key}:{a}-{b}")
            out[key] = cell
    return out


if __name__ == "__main__":
    sys.exit(main())
