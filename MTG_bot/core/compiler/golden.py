"""Golden-tree write/verify for PC-4 stability and PC-9 determinism (T5).

One golden file per pool entry: ``<golden_dir>/<oracle_id>.json`` whose
byte content is exactly ``canonical_json(record)`` of the entry's
compiled ``CardRecord``.  Emblems are separate pool entries with their
own oracle ids, so each gets its own file.

* ``write_goldens``  — explicit re-baselining action: (re)generate every
  golden file; returns the count.  NOT called by the measurement path.
* ``verify_goldens`` — the default PC-4 measurement path: recompile the
  pool and byte-compare against the committed (VCS-tracked) golden files
  without writing anything; returns a sorted diff list (missing, content
  mismatch, stale).  Empty list == stable (PC-4).  A missing golden file
  is a diff, never a silent rewrite.
* ``fingerprint_multiset`` — Counter of ``fingerprint(record)`` over all
  entries; two independent pools compiled this way must be equal (PC-9).

Both functions take an optional ``root`` so tests can target a temp dir;
production uses :data:`GOLDEN_ROOT` = ``MTG_bot/core/golden``.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from MTG_bot.core.ability_tree import canonical_json, fingerprint
from MTG_bot.core.compiler.compiler import compile_pool
from MTG_bot.core.compiler.ingest import RawCard
from MTG_bot.core.compiler.templates import TemplateRegistry

#: Production golden root: MTG_bot/core/golden/<set>/<oracle_id>.json
GOLDEN_ROOT = Path(__file__).resolve().parents[1] / "golden"


def _golden_dir(set_name: str, root: Path | None) -> Path:
    return (root if root is not None else GOLDEN_ROOT) / set_name


def _compile_records(
    pool: dict[str, RawCard], registry: TemplateRegistry
) -> dict[str, str]:
    """oracle_id -> canonical_json of the compiled record, all entries."""
    compiled = compile_pool(pool, registry)
    return {oid: canonical_json(compiled.results[oid].card) for oid in compiled.results}


def write_goldens(
    pool: dict[str, RawCard],
    registry: TemplateRegistry,
    set_name: str = "M21",
    root: Path | None = None,
) -> int:
    """Write ``<oracle_id>.json`` (exact ``canonical_json`` content) for
    every pool entry under ``<root|GOLDEN_ROOT>/<set_name>/``.

    Returns the number of files written.  Overwrites existing files — a
    golden refresh is always a full regenerate, never a merge.
    """
    records = _compile_records(pool, registry)
    directory = _golden_dir(set_name, root)
    directory.mkdir(parents=True, exist_ok=True)
    for oid in sorted(records):
        path = directory / f"{oid}.json"
        path.write_text(records[oid], encoding="utf-8")
    return len(records)


def verify_goldens(
    pool: dict[str, RawCard],
    registry: TemplateRegistry,
    set_name: str = "M21",
    root: Path | None = None,
) -> list[str]:
    """Recompile the pool and byte-compare every committed golden file.

    Read-only: never creates, rewrites, or deletes files.  This is the
    default measurement path — drift is reported, not repaired.

    Returns a sorted diff list; empty == stable (PC-4).  Diff forms:

    * ``"<oid>: missing"``          — entry has no golden file
    * ``"<oid>: content mismatch"`` — file bytes != fresh canonical_json
    * ``"<oid>: stale"``            — file exists but oid is not in pool
    * ``"golden dir <dir> does not exist"`` — nothing written yet
    """
    directory = _golden_dir(set_name, root)
    if not directory.is_dir():
        return [f"golden dir {directory} does not exist"]

    records = _compile_records(pool, registry)
    diffs: list[str] = []
    for oid in sorted(records):
        path = directory / f"{oid}.json"
        if not path.exists():
            diffs.append(f"{oid}: missing")
            continue
        if path.read_text(encoding="utf-8") != records[oid]:
            diffs.append(f"{oid}: content mismatch")
    for path in sorted(directory.glob("*.json")):
        if path.stem not in records:
            diffs.append(f"{path.stem}: stale")
    return sorted(diffs)


def fingerprint_multiset(
    pool: dict[str, RawCard],
    registry: TemplateRegistry,
) -> Counter[str]:
    """Multiset of ``fingerprint(record)`` over every compiled entry.

    Two independent compilations of the same input must produce equal
    multisets (PC-9 determinism).
    """
    compiled = compile_pool(pool, registry)
    return Counter(fingerprint(compiled.results[oid].card) for oid in compiled.results)
