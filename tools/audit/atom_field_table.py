#!/usr/bin/env python3
"""Single-source field-classification generator for the atom-ontology checker.

Detection rule (the ONLY rule; the CLASSIFY dict below is the single source
of truth for what each container field means semantically):

    A field of a registered IR dataclass is a CONTAINER field iff the raw
    annotation STRING contains one of 'tuple[', 'frozenset[' or 'list['.

    ability_tree.py is written under ``from __future__ import annotations``,
    so ``dataclasses.Field.type`` is already the raw source string; no type
    resolution is needed (and forward references need not be resolvable).

Anything else (a scalar, e.g. a ``Zone``) is not a container and is
deliberately absent from CLASSIFY.

``main()`` re-derives the container set from the live module, checks it
against CLASSIFY both ways (no UNCLASSIFIED runtime field, no stale CLASSIFY
entry: single-source drift control), and prints:
  (a) a markdown table |class|field|annotation|CLASSIFY| (sorted, '?' = ?)
  (b) a python dict literal of the FULL runtime-observed classification
      (runtime field -> token) for the checker to import, and
  (c) counts per token.
Exit code 1 iff any runtime field is UNCLASSIFIED or any CLASSIFY entry is
stale (its (class, field) no longer exists as a runtime container field).
"""

from __future__ import annotations

import dataclasses
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from MTG_bot.core import ability_tree as at  # noqa: E402

CONTAINER_MARKERS = ("tuple[", "frozenset[", "list[")

# Single source of truth: (class_name, field_name) -> classification token.
CLASSIFY: dict[tuple[str, str], str] = {
    ("Seq", "steps"): "TIME",
    ("Choose", "options"): "MENU",
    ("CardRecord", "abilities"): "IDENTITY",
    ("BackFace", "abilities"): "IDENTITY",
    ("TokenSpec", "abilities"): "IDENTITY",
    ("EmblemSpec", "abilities"): "IDENTITY",
    ("CardRecord", "types"): "IDENTITY",
    ("CardRecord", "subtypes"): "IDENTITY",
    ("CardRecord", "supertypes"): "IDENTITY",
    ("CardRecord", "colors"): "IDENTITY",
    ("CardRecord", "color_identity"): "IDENTITY",
    ("AtomArgs", "pairs"): "SET-ENFORCED",
    ("FAnd", "children"): "SET-R1a",
    ("FOr", "children"): "SET-R1a",
    ("CardRecord", "keywords"): "SET-R1a",
    ("TokenSpec", "types"): "SET-R1a",
    ("TokenSpec", "subtypes"): "SET-R1a",
    ("TokenSpec", "keywords"): "SET-R1a",
    # the token's colour SET, construction-sorted in WUBRG order (CR 105.1)
    # rather than by canonical_json
    ("TokenSpec", "colors"): "SET-R1a",
    ("FAtom", "colors"): "SET-R1a",
    ("EtBState", "initial_counters"): "SET-R1a",
    ("Cost", "parts"): "SET-ENFORCED",
    ("SpellAbility", "additional_costs"): "SET-ENFORCED",
    ("CostManaHybrid", "colors"): "SET-ENFORCED",
    ("Selector", "zones"): "SET-R0",
    ("KeywordAbility", "params"): "OPERATOR",
    ("CostModifier", "extra_deltas"): "SET-ENFORCED",
}


def runtime_container_fields() -> dict[tuple[str, str], str]:
    """(class, field) -> raw annotation string, for every container field."""
    found: dict[tuple[str, str], str] = {}
    for cls in at._DATACLASSES:
        for f in dataclasses.fields(cls):
            if any(mark in f.type for mark in CONTAINER_MARKERS):
                found[(cls.__name__, f.name)] = f.type
    return found


def main() -> int:
    runtime = runtime_container_fields()

    unclassified = sorted(k for k in runtime if k not in CLASSIFY)
    stale = sorted(k for k in CLASSIFY if k not in runtime)

    # (a) markdown table, sorted by class then field; '?' = UNCLASSIFIED
    print("| class | field | annotation | CLASSIFY |\n|---|---|---|---|")
    for cls, fld in sorted(runtime):
        tok = CLASSIFY.get((cls, fld), "?")
        print(f"| {cls} | {fld} | `{runtime[(cls, fld)]}` | {tok} |")

    # (b) python dict literal of the FULL runtime-observed classification
    print("\nRUNTIME_CLASSIFY = {")
    for cls, fld in sorted(runtime):
        print(f"    ({cls!r}, {fld!r}): {CLASSIFY.get((cls, fld), '?')!r},")
    print("}")

    # (c) counts per token (UNCLASSIFIED grouped as '?')
    counts = Counter(CLASSIFY.get(k, "?") for k in runtime)
    print("\ncounts per token:")
    for tok in sorted(counts):
        print(f"  {tok}: {counts[tok]}")
    print(f"total container fields: {len(runtime)}")

    for k in unclassified:
        print(f"UNCLASSIFIED runtime field: {k}", file=sys.stderr)
    for k in stale:
        print(f"STALE CLASSIFY entry (not in runtime): {k}", file=sys.stderr)
    return 1 if (unclassified or stale) else 0


if __name__ == "__main__":
    raise SystemExit(main())
