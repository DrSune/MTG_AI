"""One onboarding round: review packets with planted faults, calibration scores, verdicts applied.
docs/PLAN_CARD_ONBOARDING.md (gates G2-G4, gold calibration, planted-fault detection).

    PY=/home/sune/Desktop/MTG_AI/.venv/bin/python
    $PY tools/cards/round.py packets FDN --out PKT --key KEY [--plant-share 0.25] [--cards names.txt]
    $PY tools/cards/round.py score-mappers --masks masks.json --mapped OUT_DIR
    $PY tools/cards/round.py score-verifiers --key KEY --verdicts VERDICT_DIR
    $PY tools/cards/round.py apply FDN --key KEY --verdicts VERDICT_DIR --reviewer ID

Packet ids are hashes, so a verifier cannot tell a planted packet from a real one by its id or its
position. The key directory maps every id to its card and says which ids are planted; it is never
shown to a verifier.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
for _p in (REPO, HERE, HERE.parent):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import cardtool
import corpus
import irpy

from MTG_bot.core.compiler import card_records
from MTG_bot.core.compiler.compiler import compile_card
from MTG_bot.core.compiler.coverage import build_full_registry
from MTG_bot.core.compiler.ingest import ingest_pool
from MTG_bot.utils import rng


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    r = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - r) / d, (c + r) / d)


def _pid(*parts: object) -> str:
    return "P" + hashlib.sha256(":".join(map(str, parts)).encode()).hexdigest()[:10]


def cmd_packets(args: argparse.Namespace) -> int:
    sc = corpus.compile_set(args.set)
    if args.cards:
        names = [n.strip() for n in Path(args.cards).read_text().splitlines() if n.strip()]
        oids = [sc.by_name(n) for n in names]
    else:  # every mapped, unverified card of the set
        oids = [o for o, rec in sc.records.items()
                if "ir" in rec and not card_records.is_verified(sc.results[o], rec)]
    stream = rng.substream("scenario", "packets", args.set, args.round)
    plants = {o for o in oids if stream.random() < args.plant_share}
    key: dict[str, Any] = {}
    for oid in oids:
        name = sc.raw[oid].identity.name
        jobs = [("real", None)] + ([("planted", 1)] if oid in plants else [])
        for kind, seed in jobs:
            pid = _pid(args.round, args.set, oid, kind)
            ns = argparse.Namespace(set=args.set, card=name, out=args.out, id=pid,
                                    plant=seed, key=args.key if seed else None)
            if cardtool.cmd_packet(ns) == 0:
                key[pid] = {"set": args.set, "oracle_id": oid, "card": name, "planted": kind == "planted"}
    Path(args.key).mkdir(parents=True, exist_ok=True)
    (Path(args.key) / "index.json").write_text(json.dumps(key, indent=1) + "\n")
    print(f"{len(key)} packets ({sum(v['planted'] for v in key.values())} planted) in {args.out}")
    return 0


def cmd_score_mappers(args: argparse.Namespace) -> int:
    masks = json.loads(Path(args.masks).read_text())
    registry = build_full_registry()
    agree, rows = 0, []
    for key, idx in masks.items():
        code, oid = key.split(":", 1)
        raw = ingest_pool(corpus.DATA / f"{code}.json")[oid]
        truth = compile_card(raw, registry).card
        path = Path(args.mapped) / code / f"{oid}.json"
        if not path.exists():
            rows.append((raw.identity.name, idx, "not mapped"))
            continue
        rec = json.loads(path.read_text())
        if "needs_atom" in rec:
            rows.append((raw.identity.name, idx, f"needs-atom: {rec['needs_atom']['missing'][:80]}"))
            continue
        mine = card_records.build_card(raw, truth, rec["ir"])
        same = card_records.tree_sha(mine) == card_records.tree_sha(truth)
        agree += same
        if same:
            rows.append((raw.identity.name, idx, "exact"))
        else:
            rows.append((raw.identity.name, idx, "DIFFERENT"))
            if args.diff:
                print(f"--- {raw.identity.name} (sentence {idx}): compiler")
                print(irpy.render_card(truth.keywords, truth.abilities))
                print("--- mapper")
                print(irpy.render_card(mine.keywords, mine.abilities))
    n = sum(1 for r in rows if r[2] != "not mapped")  # a needs-atom on a gold card counts as a miss
    lo, hi = wilson(agree, n)
    print(f"gold agreement (exact bytes): {agree}/{n} attempted, {len(masks) - n} not yet mapped"
          f"  95% CI [{lo:.2f}, {hi:.2f}]")
    for row in rows:
        print(f"  {row[0]} [s{row[1]}]: {row[2]}")
    if args.cleanup:
        for key in masks:
            code, oid = key.split(":", 1)
            path = Path(args.mapped) / code / f"{oid}.json"
            if path.exists():
                path.unlink()
                print(f"  removed calibration record {path.name}")
    return 0


def cmd_score_verifiers(args: argparse.Namespace) -> int:
    key = json.loads((Path(args.key) / "index.json").read_text())
    caught = planted = 0
    flagged_real = real = 0
    missing = []
    for pid, info in key.items():
        vpath = Path(args.verdicts) / f"{pid}.json"
        if not vpath.exists():
            missing.append(pid)
            continue
        v = json.loads(vpath.read_text())
        wrong = v.get("verdict") != "OK" or any(c.get("status") == "WRONG" for c in v.get("clauses", []))
        if info["planted"]:
            planted += 1
            caught += wrong
            if not wrong:
                plant = json.loads((Path(args.key) / f"{pid}.json").read_text())
                print(f"  MISSED plant {pid} {info['card']}: {plant['planted']} at {plant['where']}")
        else:
            real += 1
            flagged_real += wrong
    lo, hi = wilson(caught, planted)
    print(f"planted faults caught: {caught}/{planted}  95% CI [{lo:.2f}, {hi:.2f}]")
    print(f"real packets flagged WRONG: {flagged_real}/{real} (each is a mapping bug or a false alarm: read them)")
    if missing:
        print(f"no verdict for {len(missing)} packet(s): {', '.join(missing[:10])}")
    return 0


def cmd_apply(args: argparse.Namespace) -> int:
    key = json.loads((Path(args.key) / "index.json").read_text())
    done = 0
    for pid, info in key.items():
        if info["planted"] or info["set"] != args.set:
            continue
        vpath = Path(args.verdicts) / f"{pid}.json"
        if not vpath.exists():
            continue
        ns = argparse.Namespace(set=args.set, card=info["card"], verdict=str(vpath),
                                reviewer=args.reviewer, limit=80)
        print(f"== {info['card']} ({pid})")
        done += cardtool.cmd_verify(ns) == 0
    print(f"verified {done} card(s)")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("packets")
    p.add_argument("set")
    p.add_argument("--out", required=True)
    p.add_argument("--key", required=True)
    p.add_argument("--plant-share", type=float, default=0.25)
    p.add_argument("--cards")
    p.add_argument("--round", default="r1")
    p = sub.add_parser("score-mappers")
    p.add_argument("--masks", required=True)
    p.add_argument("--mapped", default=str(card_records.RECORDS_DIR),
                   help="where the calibration records are (default: the records folder)")
    p.add_argument("--diff", action="store_true")
    p.add_argument("--cleanup", action="store_true",
                   help="delete the calibration records after scoring (they must never be verified)")
    p = sub.add_parser("score-verifiers")
    p.add_argument("--key", required=True)
    p.add_argument("--verdicts", required=True)
    p = sub.add_parser("apply")
    p.add_argument("set")
    p.add_argument("--key", required=True)
    p.add_argument("--verdicts", required=True)
    p.add_argument("--reviewer", required=True)
    args = ap.parse_args(argv)
    rng.seed_all(20261029)
    return {"packets": cmd_packets, "score-mappers": cmd_score_mappers,
            "score-verifiers": cmd_score_verifiers, "apply": cmd_apply}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
