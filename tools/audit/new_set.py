"""Bring a new card set in honestly: verify its source, seal a test split, measure first touch.

    .venv/bin/python tools/audit/new_set.py verify --set M20
    .venv/bin/python tools/audit/new_set.py first-touch --set M20
    .venv/bin/python tools/audit/new_set.py first-touch --set M20 --sealed-read --reason "..."

``verify`` checks MTG_bot/data/<SET>.json (an MTGJSON v5 set file) against this world's Scryfall,
the canonical source (KNOWLEDGE/2026-10-18/92): the roster of names, every printing's
``identifiers.scryfallId``, and the oracle text of every card, face and token. It writes
reports/set_source_<SET>.json and names mismatching cards without printing their text. This is the
second source; the owner's sign-off on a set's source stays the owner's.

``first-touch`` compiles the set with the compiler exactly as it stands and measures PC-1 and PC-2
(MTG_bot/core/compiler/coverage.py) on three disjoint groups of pool entries:

* carry-over: the oracle id, or the shape tuple of the sentences, already exists in a set the
  compiler was developed on (M21, ZNR). Compiling a reprint is not generalization, so these are
  reported apart.
* dev: novel entries that grammar rounds may read.
* test: novel entries sealed by ``sha256(salt:oracle_id)``. Their numbers and register are printed
  only under ``--sealed-read``, and every sealed read is appended to reports/sealed_reads_<SET>.tsv
  with the time, the commit and the reason. Reading them after every template change would turn
  the seal into a tuning set (Goodhart's law): read them once per grammar round.

A sentence's shape replaces the card's own names with "~" and digit runs with "N". Sentences whose
shape never occurs in the development sets are "unseen", and PC-2 on unseen shapes isolates how
well the grammar handles text it was never shaped on: the parser half of NORTH_STAR's tied rank 1.

The report (reports/first_touch_<SET>_<stamp>.json) carries the dev register grouped by shape and
never a test sentence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from MTG_bot.core.compiler.coverage import (
    build_full_registry,
    measure_pool,
)
from MTG_bot.core.compiler.ingest import RawCard, ingest_pool

DATA = REPO / "MTG_bot" / "data"
REPORTS = REPO / "reports"
#: Sets whose text the compiler was shaped on. ZNR counts: its register was iterated on (REVIEW A-5).
DEVELOPED_ON = ("M21", "ZNR")
TEST_SHARE = 0.4
SCRYFALL = "https://api.scryfall.com"
USER_AGENT = "MTG_AI-new-set/1.0 (research; github.com/DrSune/MTG_AI)"


# --------------------------------------------------------------------------- split and shapes


def salt_for(set_code: str) -> str:
    return f"{set_code.upper()}-sealed-v1"


def split_of(oracle_id: str, salt: str, share: float = TEST_SHARE) -> str:
    """'test' for about ``share`` of oracle ids, stable across runs and machines."""
    value = int(hashlib.sha256(f"{salt}:{oracle_id}".encode()).hexdigest()[:8], 16)
    return "test" if value / 0x1_0000_0000 < share else "dev"


def card_names(raw: RawCard) -> tuple[str, ...]:
    """Every name a card's own text can use for itself: full, short legendary, back face."""
    names = {raw.identity.name}
    if "," in raw.identity.name:
        names.add(raw.identity.name.split(",", 1)[0].strip())
    if raw.back_face is not None and raw.back_face.name:
        names.add(raw.back_face.name)
    return tuple(sorted((n for n in names if n), key=len, reverse=True))


def shape(sentence: str, names: tuple[str, ...]) -> str:
    out = sentence
    for name in names:
        out = re.sub(rf"(?<!\w){re.escape(name)}(?!\w)", "~", out)
    return re.sub(r"\d+", "N", out)


def front_shapes(raw: RawCard) -> tuple[str, ...]:
    names = card_names(raw)
    return tuple(shape(s, names) for s in raw.sentences)


def all_shapes(raw: RawCard) -> list[str]:
    names = card_names(raw)
    faces = raw.back_face.sentences if raw.back_face is not None else ()
    return [shape(s, names) for s in (*raw.sentences, *faces)]


def developed_index(codes: tuple[str, ...] = DEVELOPED_ON) -> dict[str, Any]:
    ids: set[str] = set()
    tuples: set[tuple[str, ...]] = set()
    shapes: set[str] = set()
    for code in codes:
        for oid, raw in ingest_pool(DATA / f"{code}.json").items():
            ids.add(oid)
            tuples.add(front_shapes(raw))
            shapes.update(all_shapes(raw))
    return {"ids": ids, "tuples": tuples, "shapes": shapes}


def assign_groups(
    pool: dict[str, RawCard], developed: dict[str, Any], salt: str
) -> tuple[dict[str, str], Counter]:
    """oracle id -> 'carry-over' | 'dev' | 'test', plus why each carry-over was carried."""
    groups: dict[str, str] = {}
    reasons: Counter = Counter()
    for oid, raw in pool.items():
        if oid in developed["ids"]:
            groups[oid] = "carry-over"
            reasons["reprint (same oracle id)"] += 1
        elif front_shapes(raw) in developed["tuples"]:
            groups[oid] = "carry-over"
            reasons["same text shape" if raw.sentences else "no rules text"] += 1
        else:
            groups[oid] = split_of(oid, salt)
    return groups, reasons


# --------------------------------------------------------------------------- measurement


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(REPO), *args], capture_output=True, text=True, check=False
    ).stdout.strip()


def provenance(set_code: str) -> dict[str, Any]:
    path = DATA / f"{set_code}.json"
    meta = json.loads(path.read_text(encoding="utf-8")).get("meta", {})
    dirty = [
        line[3:] for line in _git("status", "--porcelain", "--", "MTG_bot/core").splitlines()
    ]
    return {
        "data_file": str(path.relative_to(REPO)),
        "data_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "mtgjson": meta,
        "head": _git("rev-parse", "HEAD"),
        "engine_tree_dirty": dirty,
    }


def compile_crashes(pool: dict[str, RawCard]) -> dict[str, str]:
    """Cards whose compile raises anything but the compiler's honest refusal.

    ``measure_pool`` tolerates ``StateCorruptionError`` (a shape gap) and nothing else, so one
    such card stops a whole set's measurement. They are measured here as failures instead: in
    every denominator, with all their sentences unmatched.
    """
    from MTG_bot.core.compiler.compiler import compile_card
    from MTG_bot.core.errors import StateCorruptionError

    registry = build_full_registry()
    crashes: dict[str, str] = {}
    for oid, raw in sorted(pool.items()):
        try:
            compile_card(raw, registry)
        except StateCorruptionError:
            continue
        except Exception as exc:  # noqa: BLE001 - every other kind is the datum
            crashes[oid] = f"{type(exc).__name__}: {exc}"[:160]
    return crashes


def group_numbers(
    pool: dict[str, RawCard],
    ids: set[str],
    developed_shapes: set[str],
    supply: dict[str, frozenset[str] | None],
    crashes: dict[str, str],
    label: str,
) -> dict[str, Any]:
    crashed = {oid for oid in ids if oid in crashes}
    subset = {oid: pool[oid] for oid in sorted(ids - crashed)}
    report = measure_pool(subset, build_full_registry(), label)
    unparsed_by_oid: dict[str, int] = Counter(e.oracle_id for e in report.unparsed_queue)
    seen = Counter()
    unparsed_seen = Counter()
    crash_sentences = 0
    for oid in sorted(ids):
        for sentence_shape in all_shapes(pool[oid]):
            kind = "seen" if sentence_shape in developed_shapes else "unseen"
            seen[kind] += 1
            if oid in crashed:
                unparsed_seen[kind] += 1
                crash_sentences += 1
    for entry in report.unparsed_queue:
        names = card_names(pool[entry.oracle_id])
        kind = "seen" if shape(entry.sentence, names) in developed_shapes else "unseen"
        unparsed_seen[kind] += 1

    zero = {oid for oid in subset if unparsed_by_oid.get(oid, 0) == 0}
    gaps = {g.card for g in report.shape_gaps}
    numbers: dict[str, Any] = {
        "entries": report.entry_count + len(crashed),
        "sentences": report.sentence_total + crash_sentences,
        "pc1_count": report.cards_zero_unparsed,
        "unparsed": report.unparsed_count + crash_sentences,
        "shape_gaps": len(report.shape_gaps),
        "compile_crashes": len(crashed),
        "sentences_seen_shape": seen["seen"],
        "sentences_unseen_shape": seen["unseen"],
        "unparsed_seen_shape": unparsed_seen["seen"],
        "unparsed_unseen_shape": unparsed_seen["unseen"],
    }
    for mode, deckable in supply.items():
        if deckable is None:  # compile_supply raised: nothing of this set can be dealt
            numbers[f"dealable_{mode}"] = None
            continue
        in_group = deckable & set(ids)
        numbers[f"dealable_{mode}"] = len(in_group)
        # "Fully compiled" here = no unparsed sentence and no shape gap: what the deal pool
        # should hold under DESIGN_CARD_POOL's no-silent-degradation rule (REVIEW A-5).
        numbers[f"dealable_{mode}_fully_compiled"] = len(in_group & (zero - gaps))
    return with_rates(numbers)


def with_rates(numbers: dict[str, Any]) -> dict[str, Any]:
    def share(numer: int, denom: int) -> float | None:
        return round(numer / denom, 4) if denom else None

    seen, unseen = numbers["sentences_seen_shape"], numbers["sentences_unseen_shape"]
    return {
        **numbers,
        "pc1": share(numbers["pc1_count"], numbers["entries"]),
        "pc2": share(numbers["sentences"] - numbers["unparsed"], numbers["sentences"]),
        "pc2_seen_shape": share(seen - numbers["unparsed_seen_shape"], seen),
        "pc2_unseen_shape": share(unseen - numbers["unparsed_unseen_shape"], unseen),
    }


def combine(*parts: dict[str, Any]) -> dict[str, Any]:
    """The whole set as the sum of its disjoint groups.

    Summed rather than re-measured: one pool-level compile step (attaching emblems to their
    owners) can raise on a whole set while every group measures (KHM, 2026-10-27).
    """
    total: dict[str, Any] = {}
    for part in parts:
        for key, value in part.items():
            if key.startswith("pc"):
                if key == "pc1_count":
                    total[key] = total.get(key, 0) + value
                continue
            if value is None or total.get(key, 0) is None:
                total[key] = None
            else:
                total[key] = total.get(key, 0) + value
    return with_rates(total)


def dev_register(
    pool: dict[str, RawCard], ids: set[str], crashes: dict[str, str]
) -> list[dict[str, Any]]:
    subset = {oid: pool[oid] for oid in sorted(ids) if oid not in crashes}
    report = measure_pool(subset, build_full_registry(), "dev")
    rows: dict[str, dict[str, Any]] = defaultdict(lambda: {"count": 0, "cards": [], "hints": set()})
    for entry in report.unparsed_queue:
        key = shape(entry.sentence, card_names(pool[entry.oracle_id]))
        row = rows[key]
        row["count"] += 1
        row["hints"].add(entry.bucket_hint)
        if entry.name not in row["cards"]:
            row["cards"].append(entry.name)
    ordered = sorted(rows.items(), key=lambda kv: (-kv[1]["count"], kv[0]))
    register = [
        {"shape": k, "count": v["count"], "hints": sorted(v["hints"]), "cards": v["cards"]}
        for k, v in ordered
    ]
    for gap in report.shape_gaps:
        register.append({"shape": "<shape gap>", "count": 1, "hints": [], "cards": [gap.name],
                         "error": gap.error})
    for oid in sorted(ids):
        if oid in crashes:
            register.append({"shape": "<compile crash>", "count": 1, "hints": [],
                             "cards": [pool[oid].identity.name], "error": crashes[oid]})
    return register


def compiled_supply(set_code: str) -> dict[str, frozenset[str] | None]:
    """The engine's deal pools; ``None`` when building the pool raises (nothing is dealable)."""
    from MTG_bot.core.executor.games import compile_supply

    out: dict[str, frozenset[str] | None] = {}
    for mode in ("engine", "castable"):
        try:
            out[mode] = frozenset(compile_supply(mode, set_code).deckable)
        except Exception as exc:  # noqa: BLE001 - a set the engine cannot deal is the datum
            print(f"supply {mode}: {type(exc).__name__}: {exc}", file=sys.stderr)
            out[mode] = None
    return out


def cmd_first_touch(args: argparse.Namespace) -> int:
    set_code = args.set.upper()
    if set_code in DEVELOPED_ON:
        raise SystemExit(f"{set_code} is a development set; first touch means a new one")
    if args.sealed_read and not args.reason:
        raise SystemExit("--sealed-read needs --reason (it is logged)")
    started = time.perf_counter()
    pool = ingest_pool(DATA / f"{set_code}.json")
    developed = developed_index()
    salt = salt_for(set_code)
    groups, reasons = assign_groups(pool, developed, salt)
    members: dict[str, set[str]] = defaultdict(set)
    for oid, group in groups.items():
        members[group].add(oid)
    supply = compiled_supply(set_code)
    crashes = compile_crashes(pool)
    shapes = developed["shapes"]
    stamp = datetime.now().astimezone().strftime("%Y-%m-%d_%H%M")
    result: dict[str, Any] = {
        "set": set_code,
        "stamp": stamp,
        "provenance": provenance(set_code),
        "split": {
            "salt": salt,
            "test_share": TEST_SHARE,
            "rule": "test iff int(sha256(salt:oracle_id)[:8], 16) / 2**32 < test_share",
            "developed_on": list(DEVELOPED_ON),
            "counts": {g: len(members[g]) for g in ("carry-over", "dev", "test")},
            "carry_over_reasons": dict(reasons),
        },
        "engine_dealable": {mode: pool_ids is not None for mode, pool_ids in supply.items()},
        "carry-over": group_numbers(pool, members["carry-over"], shapes, supply, crashes,
                                    "carry-over"),
        "dev": group_numbers(pool, members["dev"], shapes, supply, crashes, "dev"),
        "test": "sealed",
        "whole": "sealed",
    }
    if args.sealed_read:
        result["test"] = group_numbers(pool, members["test"], shapes, supply, crashes, "test")
        result["whole"] = combine(result["carry-over"], result["dev"], result["test"])
        log = REPORTS / f"sealed_reads_{set_code}.tsv"
        with log.open("a", encoding="utf-8") as fh:
            dirty = "dirty" if result["provenance"]["engine_tree_dirty"] else "clean"
            fh.write(f"{stamp}\t{result['provenance']['head'][:12]}\t{dirty}\t{args.reason}\n")
    result["dev_register"] = dev_register(pool, members["dev"], crashes)
    result["seconds"] = round(time.perf_counter() - started, 1)
    out = Path(args.out) if args.out else REPORTS / f"first_touch_{set_code}_{stamp}.json"
    out.write_text(json.dumps(result, indent=1, sort_keys=False) + "\n", encoding="utf-8")
    summary = {k: result[k] for k in ("set", "split", "engine_dealable", "carry-over", "dev",
                                      "test", "whole")}
    print(json.dumps(summary, indent=1))
    shown = out.relative_to(REPO) if out.is_relative_to(REPO) else out
    print(f"dev register: {len(result['dev_register'])} shapes -> {shown}")
    return 0


# --------------------------------------------------------------------------- source check


def _get(url: str) -> dict[str, Any]:
    request = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def scryfall_printings(code: str) -> list[dict[str, Any]]:
    """Every printing Scryfall lists for set ``code`` (variations and extras included)."""
    query = urllib.parse.urlencode(
        {"q": f"set:{code.lower()}", "unique": "prints", "include_extras": "true",
         "include_variations": "true", "order": "set"}
    )
    url: str | None = f"{SCRYFALL}/cards/search?{query}"
    cards: list[dict[str, Any]] = []
    while url:
        try:
            page = _get(url)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:  # Scryfall's "no cards found"
                return cards
            raise
        cards.extend(page.get("data", []))
        url = page.get("next_page") if page.get("has_more") else None
        time.sleep(0.12)  # Scryfall asks for 50-100 ms between requests
    return cards


def _norm(text: str | None) -> str:
    # MTGJSON brackets loyalty costs ("[+1]: ...") where Scryfall does not ("+1: ...").
    text = (text or "").replace("−", "-")
    text = re.sub(r"\[([+-]?(?:\d+|X))\]", r"\1", text)
    return re.sub(r"\s+", " ", text).strip()


def _expected_text(card: dict[str, Any], face_name: str | None) -> str | None:
    faces = card.get("card_faces") or []
    if face_name and faces:
        for face in faces:
            if face.get("name") == face_name:
                return face.get("oracle_text")
        return None
    if "oracle_text" in card:
        return card["oracle_text"]
    if faces:
        return "\n".join(face.get("oracle_text", "") for face in faces)
    return None


def compare(records: list[dict[str, Any]], printings: list[dict[str, Any]]) -> dict[str, Any]:
    by_id = {card["id"]: card for card in printings}
    file_ids = {r.get("identifiers", {}).get("scryfallId") for r in records} - {None}
    text_ok, text_bad, no_id = 0, [], []
    for record in records:
        sid = record.get("identifiers", {}).get("scryfallId")
        card = by_id.get(sid)
        if card is None:
            no_id.append(record.get("name"))
            continue
        face = record.get("faceName") if record.get("side") else None
        expected = _expected_text(card, face)
        if expected is None and face:
            time.sleep(0.12)
            expected = _expected_text(_get(f"{SCRYFALL}/cards/{sid}"), face)
        if _norm(record.get("text")) == _norm(expected):
            text_ok += 1
        else:
            text_bad.append(record.get("faceName") or record.get("name"))
    file_names = {str(r.get("name")) for r in records}
    canon_names = {str(c.get("name")) for c in printings}
    return {
        "records": len(records),
        "scryfall_printings": len(printings),
        "names_file": len(file_names),
        "names_scryfall": len(canon_names),
        "names_only_in_file": sorted(file_names - canon_names),
        "names_only_in_scryfall": sorted(canon_names - file_names),
        "ids_matched": len(file_ids & set(by_id)),
        "ids_only_in_file": len(file_ids - set(by_id)),
        "ids_only_in_scryfall": len(set(by_id) - file_ids),
        "records_without_scryfall_match": sorted(n for n in no_id if n),
        "text_match": text_ok,
        "text_mismatch": sorted(set(text_bad)),
    }


def cmd_verify(args: argparse.Namespace) -> int:
    set_code = args.set.upper()
    path = DATA / f"{set_code}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    data = payload["data"]
    set_object = _get(f"{SCRYFALL}/sets/{set_code.lower()}")
    cards = compare(data.get("cards", []), scryfall_printings(set_code))
    token_code = data.get("tokenSetCode") or f"T{set_code}"
    tokens = compare(data.get("tokens", []), scryfall_printings(token_code))
    clean = all(
        not part[key]
        for part in (cards, tokens)
        for key in ("names_only_in_file", "names_only_in_scryfall", "text_mismatch",
                    "records_without_scryfall_match")
    ) and not cards["ids_only_in_file"] and not tokens["ids_only_in_file"]
    report = {
        "set": set_code,
        "checked_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "source": {"file": str(path.relative_to(REPO)),
                   "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                   "mtgjson": payload.get("meta", {})},
        "scryfall_set": {k: set_object.get(k) for k in
                         ("code", "name", "released_at", "set_type", "card_count",
                          "printed_size")},
        "cards": cards,
        "tokens": {"set": token_code, **tokens},
        "verdict": "match" if clean else "MISMATCH (see names; texts deliberately not printed)",
        "owner_sign_off": "pending",
    }
    out = REPORTS / f"set_source_{set_code}.json"
    out.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=1))
    return 0 if clean else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("verify", help="check the set file against this world's Scryfall")
    v.add_argument("--set", required=True)
    f = sub.add_parser("first-touch", help="measure the set with the compiler as it stands")
    f.add_argument("--set", required=True)
    f.add_argument("--sealed-read", action="store_true",
                   help="also measure the sealed test split (logged)")
    f.add_argument("--reason", default="", help="why the seal is read (required with it)")
    f.add_argument("--out", help="report path (default reports/first_touch_<SET>_<stamp>.json)")
    args = ap.parse_args(argv)
    return {"verify": cmd_verify, "first-touch": cmd_first_touch}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
