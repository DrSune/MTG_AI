"""One-off: the compile delta of a compiler change over all 19 sets (2026-11-06, turn history and
"can't be countered"). Deleted once its numbers are in KNOWLEDGE/NUMBERS.md.

    PY=/home/sune/Desktop/MTG_AI/.venv/bin/python
    $PY tools/audit/compile_census.py snapshot <repo checkout> <out.json>   # pure compiler, no records
    $PY tools/audit/compile_census.py diff <before.json> <after.json>

``diff`` prints, per set, the sentences that newly parse and the cards that become fully compiled
(no unparsed sentence on either face, no ambiguity, not refused), and fails if a sentence stops
parsing, an ambiguity appears, or the tree of a card that compiled fully before changes.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

SETS = ("M21", "ZNR", "M20", "KHM", "10E", "M10", "M11", "M12", "M13", "M14", "M15", "ORI", "M19",
        "DOM", "WAR", "FDN", "ELD", "THB", "IKO")


def snapshot(repo: Path, out: Path) -> None:
    sys.path.insert(0, str(repo))
    from MTG_bot.core.ability_tree import canonical_json
    from MTG_bot.core.compiler.compiler import compile_card
    from MTG_bot.core.compiler.coverage import build_full_registry
    from MTG_bot.core.compiler.ingest import ingest_pool

    registry = build_full_registry()
    census: dict[str, dict[str, dict]] = {}
    for code in SETS:
        rows: dict[str, dict] = {}
        for oid, raw in ingest_pool(repo / "MTG_bot" / "data" / f"{code}.json").items():
            if raw.is_token or raw.is_emblem:
                continue
            row: dict = {"name": raw.identity.name,
                         "sentences": [*raw.sentences, *(raw.back_face.sentences if raw.back_face else ())]}
            try:
                res = compile_card(raw, registry)
            except Exception as exc:  # noqa: BLE001 - a refusal is a census row
                row["refused"] = f"{type(exc).__name__}: {exc}"[:200]
            else:
                row["unparsed"] = [s for s, _ in (*res.unparsed, *res.back_face_unparsed)]
                row["ambiguous"] = [a.sentence for a in res.ambiguities]
                row["tree"] = hashlib.sha256(canonical_json(res.card).encode()).hexdigest()
            rows[oid] = row
        census[code] = rows
    out.write_text(json.dumps(census))


def _full(row: dict) -> bool:
    return "refused" not in row and not row["unparsed"] and not row["ambiguous"]


def _unparsed(row: dict) -> set[str]:
    return set(row["sentences"]) if "refused" in row else set(row["unparsed"])


def diff(before: dict, after: dict) -> int:
    problems: list[str] = []
    total_sentences = total_cards = 0
    for code in SETS:
        parsed: list[str] = []
        full: list[str] = []
        changed = 0
        for oid, b in before[code].items():
            a = after[code][oid]
            if b.get("tree") != a.get("tree"):
                changed += 1
                if _full(b):
                    problems.append(f"{code} {b['name']}: compiled fully before, tree changed")
            if _unparsed(a) - _unparsed(b):
                problems.append(f"{code} {b['name']}: newly unparsed {sorted(_unparsed(a) - _unparsed(b))}")
            if set(a.get("ambiguous", [])) - set(b.get("ambiguous", [])):
                problems.append(f"{code} {b['name']}: new ambiguity")
            parsed += sorted(_unparsed(b) - _unparsed(a))
            if _full(a) and not _full(b):
                full.append(b["name"])
        total_sentences += len(parsed)
        total_cards += len(full)
        print(f"{code}: {len(parsed)} sentences newly parse, {len(full)} cards newly fully compiled"
              f"{' (' + ', '.join(sorted(full)) + ')' if full else ''}; {changed} trees changed")
    print(f"total: {total_sentences} sentences, {total_cards} cards")
    for line in problems:
        print("PROBLEM", line)
    return 1 if problems else 0


def main(argv: list[str]) -> int:
    if len(argv) == 3 and argv[0] == "snapshot":
        snapshot(Path(argv[1]).resolve(), Path(argv[2]))
        return 0
    if len(argv) == 3 and argv[0] == "diff":
        return diff(json.loads(Path(argv[1]).read_text()), json.loads(Path(argv[2]).read_text()))
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
