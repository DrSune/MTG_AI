"""Unseen-card generalization meter: eval accuracy split by CARD SEETINESS.

Splits the 199-item universal-gate corpus into SEEN vs FRESH halves and scores
any number of checkpoints on each, reporting gap = fresh_acc - seen_acc with a
card-cluster bootstrap SE on the gap (items of one card are correlated,
KNOWLEDGE/2026-10-07/26; the two sides are disjoint card sets, so their
cluster bootstraps are combined independently: SE_gap = sqrt(se_s^2 + se_f^2)).

Two split modes:

* ``--split set``  : FRESH = items whose card's SET CODE is in --fresh-sets.
  Set codes come from MTG_bot/data/mtg_bot.db (cards.set_code); M21 token
  names (Fodder / Spare Goat / Stray Aurochs / Treasure) fold into M21.
  Reality note (2026-10-15): only ONE set has ever been integrated (M21,
  golden/M21 added 2026-09-24; ZNR fetch HALTED 2026-10-08 /59, file still
  untracked 2026-10-15 /81 /85) -> with an empty --fresh-sets this mode is
  degenerate by construction and is kept for the day a second set lands.

* ``--split card`` : per-checkpoint LABEL-level seetiness against that
  checkpoint's OWN train corpus (train_file read from its *_report.json):
  a card is SEEN iff the checkpoint's train file contains >=1 eligible gold
  row for it under the trainer's exclusion law (train_bc_v3 keeps rows whose
  card is NOT in eval_families). Live rollout files (episodes_champ* style)
  carry no per-ask owner card (card field = episode id), so exposure is
  measured exactly: the card NAME appears verbatim as a game entity in some
  training ask observation. Fresh = never label-trained and never observed.

CRITICAL caveat (verified 2026-10-15, see KNOWLEDGE/2026-10-15/86):
"eval items never in TRAIN batches by construction" is FALSE for the curated
lineage. eval_split.json is family-wise (card-name rule), and the ladder arms
train ON episodes_v2.jsonl minus the 33 eval-family cards -- i.e. the 141
train-family gate items ARE the bc9/bc10 training rows, item for item. Only
the 58 eval-family items are held out. The card split below measures exactly
this; the set split cannot exist until a second set ships.

Usage:
  .venv/bin/python tools/eval/holdout_report.py \
      --ckpts tools/training/bc9_S3_s1_best.pt,tools/training/bsh_S3a_s1_best.pt,\
tools/training/bc10_S3a_s1_best.pt --out tools/eval/holdout_report.json
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sqlite3
from pathlib import Path
from typing import Any

import torch

from tools.training.bc_model import PointerBC
from tools.training import bc_data_v2
from tools.training.train_bc_v2 import EPISODES, SPLIT, eval_rows
from tools.training.train_bc_v3 import eval_side

REPO = Path(__file__).resolve().parents[2]
DB = REPO / "MTG_bot" / "data" / "mtg_bot.db"

#: M21 token names that never appear in the cards table (tokens are not cards).
TOKENS_TO_M21 = {"Fodder", "Spare Goat", "Stray Aurochs", "Treasure"}


def card_sets() -> dict[str, str]:
    """name -> set_code from the integration db, plus token fold-in."""
    con = sqlite3.connect(DB)
    out = {n: s for n, s in con.execute("select name, set_code from cards")}
    for t in TOKENS_TO_M21:
        out[t] = "M21"
    return out


def train_cards(train_file: Path, eval_families: set[str]) -> tuple[set[str], str]:
    """Cards the checkpoint could have received gold labels for.

    Returns (card-name set, method). Curated files carry the real card name
    per episode; the trainer's exclusion law (train_bc_v3: rows whose card is
    in eval_families are dropped from every train file) is applied here, so
    eval-family cards count as UNSEEN even though they sit in the same file.
    Live rollout files carry an episode id per card field, the filter is a
    no-op there (episode ids never match card names -- verified 2026-10-15),
    so we harvest card names appearing verbatim inside ask observations.
    """
    eps = bc_data_v2.load_episodes(train_file)
    names = {ep["card"] for ep in eps}
    # curated heuristic: majority of card fields look like real names
    # (live files: 'champshadow-g7704s0c0' style, zero spaces)
    if (
        sum(" " in n or n[0].isupper() and "-" not in n for n in names)
        > len(names) // 2
    ):
        return names - eval_families, "curated-card-field-minus-eval-families"

    known = set(card_sets())
    seen: set[str] = set()

    def walk(o: Any) -> None:
        if isinstance(o, str):
            if o in known:
                seen.add(o)
        elif isinstance(o, list):
            for x in o:
                walk(x)
        elif isinstance(o, dict):
            for v in o.values():
                walk(v)

    for ep in eps:
        walk(ep.get("asks", []))
    return seen, "live-obs-name-exposure"


def bootstrap_acc_se(
    by_card: dict[str, list[int]], B: int, seed: int
) -> tuple[float, int]:
    """Card-cluster bootstrap SE of accuracy (items grouped by card,
    resample CARDS with replacement, normalise by the original item count --
    same convention as train_bc.cluster_bootstrap_stats). Returns (se, n_items)."""
    groups = [by_card[c] for c in sorted(by_card)]
    n_items = sum(len(g) for g in groups)
    rng = random.Random(seed)
    accs = [
        sum(sum(p) for p in (groups[rng.randrange(len(groups))] for _ in groups))
        / n_items
        for _ in range(B)
    ]
    mean = sum(accs) / B
    se = math.sqrt(sum((a - mean) ** 2 for a in accs) / (B - 1))
    return se, n_items


def side_stats(rows: list[dict[str, Any]], B: int, seed: int) -> dict[str, Any]:
    by_card: dict[str, list[int]] = {}
    for r in rows:
        by_card.setdefault(r["card"], []).append(1 if r["correct"] else 0)
    n = len(rows)
    k = sum(r["correct"] for r in rows)
    se, _ = bootstrap_acc_se(by_card, B, seed) if n else (float("nan"), 0)
    return {
        "n_items": n,
        "n_cards": len(by_card),
        "acc": round(k / n, 4) if n else None,
        "boot_se": round(se, 4) if n else None,
        "cards": sorted(by_card),
    }


def score(
    ckpt: Path, seen_cards: set[str], fresh_sets: set[str], mode: str, B: int, seed: int
) -> dict[str, Any]:
    blob = torch.load(ckpt, map_location="cpu", weights_only=False)
    model = PointerBC(**blob["config"])
    model.load_state_dict(blob["state"])
    vocab: dict[str, int] = blob["vocab"]
    eval_ds, joined = eval_side(vocab, smoke=False)
    eval_families = set(json.loads(SPLIT.read_text())["eval_families"])
    bcs_of = {
        name: m["bcs"]
        for name, m in json.loads((REPO / "tools/audit/bcs.json").read_text())[
            "cards"
        ].items()
    }
    rows = [
        r
        for r in eval_rows(model, eval_ds, torch.device("cpu"), eval_families, bcs_of)
        if r["cert"]
    ]
    sets = card_sets()
    if mode == "set":
        fresh = [r for r in rows if sets.get(r["card"], "?") in fresh_sets]
        seen = [r for r in rows if r not in fresh]
    else:
        fresh = [r for r in rows if r["card"] not in seen_cards]
        seen = [r for r in rows if r["card"] in seen_cards]
    s_s, s_f = side_stats(seen, B, seed), side_stats(fresh, B, seed + 1)
    gap = None
    gap_se = None
    ci = None
    if s_s["acc"] is not None and s_f["acc"] is not None:
        gap = round(s_f["acc"] - s_s["acc"], 4)
        gap_se = round(math.sqrt(s_s["boot_se"] ** 2 + s_f["boot_se"] ** 2), 4)
        ci = [round(gap - 1.96 * gap_se, 4), round(gap + 1.96 * gap_se, 4)]
    return {
        "ckpt": ckpt.name,
        "eval_joined": joined,
        "gate_acc_all": round(sum(r["correct"] for r in rows) / len(rows), 4),
        "n_items_cert": len(rows),
        "seen": s_s,
        "fresh": s_f,
        "gap": gap,
        "gap_boot_se": gap_se,
        "gap_ci95": ci,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Unseen-card generalization meter (see module docstring)"
    )
    ap.add_argument("--ckpts", required=True, help="comma-separated .pt paths")
    ap.add_argument("--out", type=Path, default=None, help="json output path")
    ap.add_argument("--split", choices=("card", "set"), default="card")
    ap.add_argument("--fresh-sets", default="", help="set codes for --split set")
    ap.add_argument("--boot", type=int, default=4000)
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args(argv)

    fresh_sets = {s.strip() for s in args.fresh_sets.split(",") if s.strip()}
    eval_families = set(json.loads(SPLIT.read_text())["eval_families"])
    report: dict[str, Any] = {
        "split_mode": args.split,
        "fresh_sets": sorted(fresh_sets),
        "n_eval_families": len(eval_families),
        "boot": args.boot,
        "seed": args.seed,
        "results": [],
    }
    for ck in [Path(p.strip()) for p in args.ckpts.split(",")]:
        seen_cards: set[str] = set()
        method = ""
        tf = Path("")
        if args.split == "card":
            rep = ck.parent / (ck.name.replace("_best.pt", "_report.json"))
            if not rep.exists():
                raise SystemExit(f"no report json for {ck.name}: {rep}")
            tf = Path(json.loads(rep.read_text())["train_file"])
            seen_cards, method = train_cards(tf, eval_families)
        res = score(ck, seen_cards, fresh_sets, args.split, args.boot, args.seed)
        res["train_file"] = str(tf) if seen_cards or method else ""
        res["seeness_method"] = method
        report["results"].append(res)

    hdr = (
        f"{'ckpt':28s} {'seen_acc':>9s} {'n':>4s} {'fresh_acc':>9s} {'n':>4s} "
        f"{'GAP':>7s} {'SE_gap':>7s} {'CI95':>18s}"
    )
    print(hdr)
    print("-" * len(hdr))
    for r in report["results"]:
        s, f = r["seen"], r["fresh"]
        print(
            f"{r['ckpt']:28s} {s['acc']!s:>9s} {s['n_items']:>4d} "
            f"{f['acc']!s:>9s} {f['n_items']:>4d} {r['gap']!s:>7s} "
            f"{r['gap_boot_se']!s:>7s} {str(r['gap_ci95']):>18s}"
        )
    for r in report["results"]:
        print(
            f"{r['ckpt']}: gate_acc={r['gate_acc_all']} "
            f"(n={r['n_items_cert']}, joined={r['eval_joined']}) "
            f"train={Path(r['train_file']).name if r['train_file'] else '-'} "
            f"[{r['seeness_method']}] "
            f"seen_cards={r['seen']['n_cards']} fresh_cards={r['fresh']['n_cards']}"
        )
    if args.out:
        args.out.write_text(json.dumps(report, indent=1))
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
