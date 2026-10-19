#!/usr/bin/env python3
"""Single-source field-classification generator for the atom-ontology checker.

Detection rule (the ONLY rule; the CLASSIFY dict below is the single source
of truth for what each container field means semantically):

    A field of a registered IR dataclass is a CONTAINER field iff the raw
    annotation STRING contains one of 'tuple[', 'frozenset[' or 'list['.

    ability_tree.py is written under ``from __future__ import annotations``,
    so ``dataclasses.Field.type`` is already the raw source string; no type
    resolution is needed (and forward references need not be resolvable).

Anything else (e.g. ``Selector.zone: Zone``, a scalar) is not a container and
is deliberately absent from CLASSIFY — R0 will delete ``Selector.zone``.

``main()`` re-derives the container set from the live module, checks it
against CLASSIFY both ways (no UNCLASSIFIED runtime field, no stale CLASSIFY
entry: single-source drift control), and prints:
  (a) a markdown table |class|field|annotation|CLASSIFY| (sorted, '?' = ?)
  (b) a python dict literal of the FULL runtime-observed classification
      (runtime field -> token) for the checker to import, and
  (c) counts per token.
Exit code 1 iff any runtime field is UNCLASSIFIED or any CLASSIFY entry is
stale (its (class, field) no longer exists as a runtime container field).

Runnable from anywhere as long as the repo root is importable; when copied to
tools/audit/ it runs as part of the repo with no changes.
"""

from __future__ import annotations

import dataclasses
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve()
for _anc in REPO.parents:  # walk up to find the repo root (contains MTG_bot)
    if (_anc / "MTG_bot" / "core" / "ability_tree.py").is_file():
        sys.path.insert(0, str(_anc))
        break

from MTG_bot.core import ability_tree as at  # noqa: E402

CONTAINER_MARKERS = ("tuple[", "frozenset[", "list[")

# Single source of truth: (class_name, field_name) -> classification token.
CLASSIFY: dict[tuple[str, str], str] = {
    ("Seq", "steps"): "TIME",
    ("Choose", "options"): "MENU",
    ("CardRecord", "abilities"): "IDENTITY",
    ("BackFace", "abilities"): "IDENTITY",
    ("TokenSpec", "abilities"): "IDENTITY",
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
    ("FAtom", "colors"): "SET-R1a",
    ("EtBState", "initial_counters"): "SET-R1a",
    ("Cost", "parts"): "SET-R1b",
    ("SpellAbility", "additional_costs"): "SET-R1b",
    ("CostManaHybrid", "colors"): "SET-R1b",
    ("Selector", "zones"): "SET-R0",
    ("KeywordAbility", "params"): "OPERATOR",
    ("CostModifier", "extra_deltas"): "OPERATOR-AUDIT",
    # NOTE: ('Selector', 'zone') is a SCALAR Zone field — NOT a container,
    # hence absent here; R0 will delete it.
}


def runtime_container_fields() -> dict[tuple[str, str], str]:
    """(class, field) -> raw annotation string, for every container field."""
    classes = getattr(at, "_DATACLASSES", None)
    if not classes:  # fallback: every dataclass defined in the module
        classes = [
            obj
            for obj in vars(at).values()
            if isinstance(obj, type) and dataclasses.is_dataclass(obj)
        ]
    found: dict[tuple[str, str], str] = {}
    for cls in classes:
        if not dataclasses.is_dataclass(cls):
            continue
        for f in dataclasses.fields(cls):
            ann = f.type if isinstance(f.type, str) else str(f.type)
            if any(mark in ann for mark in CONTAINER_MARKERS):
                found[(cls.__name__, f.name)] = ann
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
