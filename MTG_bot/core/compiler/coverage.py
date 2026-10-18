"""Phase-1 grammar coverage measurement (task T5).

Read-only measurement layer on top of ``ingest`` + ``compile``:

* ``build_full_registry`` — assembles the full 8-bucket TemplateRegistry.
* ``measure_pool``        — one per-card ``compile_card`` pass over a whole
  pool, reduced to the pre-registered Phase-1 numbers PC-1, PC-2, PC-3,
  PC-6, PC-8 plus the exact unparsed/ambiguity queues (PC-10 harness input).
  Cards whose printed shape raises ``StateCorruptionError`` are recorded as
  ``shape_gaps`` ledger rows (§8/§11: a gap is REPORTED, never a crash,
  never a silent drop) and stay in every PC denominator.
* ``check_pinned_denominators`` — fails loudly if the M21 ingest no longer
  yields the pinned 305 entries / 639 sentences / 510 unique sentences.

This module never mutates existing modules and never stubs an executor
(PC-7 stays ``pending_executor`` until T6 — reported by
``tools/measure_grammar.py``).

Measurement semantics (per KNOWLEDGE/2026-09-14/02-phase1-plan.md, with the
plan's 417/952 planning-time denominators replaced by the pinned real
M21 ingest denominators 305/639):

* PC-1 card_coverage — pool entries with zero unparsed fragments / total
  pool entries.  Denominator is the full pool (305, emblems included),
  matching "total pool" in the plan.
* PC-2 sentence_coverage — matched oracle sentences / total oracle
  sentences.  A sentence is *matched* when it is not in the compiler's
  unparsed queue: rule-reminder and keyword sentences are recognised
  outcomes and count as matched.
* PC-3 ambiguity — entries whose text matched >= 2 distinct template
  outcomes producing different trees (the compiler's own ambiguity
  records).
* PC-6 vocabulary_health — orphan verbs (0 uses across all compiled
  ``Atom`` nodes of the pool) and the max single-verb share of all Atom
  nodes.  All pool entries (emblems included) are walked.
* PC-8 targetable_card_fraction — pool entries with >= 1 TARGET-mode
  ``Selector`` anywhere in the compiled tree / total pool entries.
  Selectors only occur in Atom args (Filter = FAnd|FOr|FNot|FAtom), so
  walking the tree finds every one of them.
"""

from __future__ import annotations

import types
from dataclasses import dataclass, replace
from typing import Any

from MTG_bot.core.ability_tree import Atom, Selector, SelectorMode, Verb, walk
from MTG_bot.core.compiler import (
    templates_b1,
    templates_b2a,
    templates_b2b,
    templates_b3,
    templates_b4,
    templates_b5a,
    templates_b5b,
    templates_b5c,
)
from MTG_bot.core.compiler.compiler import CompileResult, compile_card
from MTG_bot.core.compiler.ingest import RawCard, pool_stats
from MTG_bot.core.compiler.templates import TemplateRegistry
from MTG_bot.core.errors import StateCorruptionError

# ---------------------------------------------------------------------------
# Pinned denominators (M21) — NUMBERS.md 2026-09-15/02 re-measurement.
# The phase plan's 417/952 were planning-time estimates; the deduplicated
# real pool is 305 entries / 639 sentences / 510 unique sentences.
# ---------------------------------------------------------------------------

PINNED_ENTRIES = 305
PINNED_SENTENCES = 639
PINNED_SENTENCES_UNIQUE = 510

#: The eight bucket modules, in registration order.  Explicit by design —
#: a new bucket module must be added here (and to NUMBERS.md) before its
#: templates participate in measurement.
_BUCKET_MODULES: tuple[types.ModuleType, ...] = (
    templates_b1,
    templates_b2a,
    templates_b2b,
    templates_b3,
    templates_b4,
    templates_b5a,
    templates_b5b,
    templates_b5c,
)


def build_full_registry() -> TemplateRegistry:
    """A TemplateRegistry holding every template of all 8 bucket modules."""
    registry = TemplateRegistry()
    for module in _BUCKET_MODULES:
        for template in module.TEMPLATES:
            registry.register(template)
    return registry


def check_pinned_denominators(pool: dict[str, RawCard]) -> None:
    """Raise ``ValueError`` if the M21 pool no longer yields the pinned
    denominators (305 entries / 639 sentences / 510 unique).

    A changed denominator is a data-change signal, not a rescaling
    opportunity: re-measure, record it in KNOWLEDGE/NUMBERS.md, and only
    then update the pins.
    """
    stats = pool_stats(pool)
    problems = []
    if stats["total"] != PINNED_ENTRIES:
        problems.append(f"entries {stats['total']} != pinned {PINNED_ENTRIES}")
    if stats["sentence_total"] != PINNED_SENTENCES:
        problems.append(
            f"sentences {stats['sentence_total']} != pinned {PINNED_SENTENCES}"
        )
    if stats["sentence_unique"] != PINNED_SENTENCES_UNIQUE:
        problems.append(
            f"unique sentences {stats['sentence_unique']} != pinned "
            f"{PINNED_SENTENCES_UNIQUE}"
        )
    if problems:
        raise ValueError(
            "M21 pinned denominators changed: "
            + "; ".join(problems)
            + ". Re-measure and update NUMBERS.md before re-pinning."
        )


# ---------------------------------------------------------------------------
# Report structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class UnparsedEntry:
    """One unparsed (sentence, bucket_hint) fragment from one pool entry."""

    oracle_id: str
    name: str
    sentence: str
    bucket_hint: str

    def to_json(self) -> dict[str, str]:
        return {
            "oracle_id": self.oracle_id,
            "name": self.name,
            "sentence": self.sentence,
            "bucket_hint": self.bucket_hint,
        }


@dataclass(frozen=True)
class AmbiguityEntry:
    """One compiler-recorded multi-template ambiguity for one pool entry."""

    oracle_id: str
    name: str
    sentence: str
    tids: tuple[str, ...]
    note: str

    def to_json(self) -> dict[str, Any]:
        return {
            "oracle_id": self.oracle_id,
            "name": self.name,
            "sentence": self.sentence,
            "tids": list(self.tids),
            "note": self.note,
        }


@dataclass(frozen=True)
class ShapeGap:
    """One pool entry whose printed shape raised ``StateCorruptionError``.

    Per §8/§11 this is a REPORTED ledger row, not a crash and not a silent
    drop: the card is excluded from compiled-result metrics but stays in
    every PC denominator, and the error message is recorded verbatim
    (truncated to 160 chars).
    """

    card: str  # oracle_id
    name: str
    error: str

    def to_json(self) -> dict[str, str]:
        return {"card": self.card, "name": self.name, "error": self.error}


@dataclass(frozen=True)
class CoverageReport:
    """The reduced Phase-1 measurement of one compiled pool.

    ``pool_stats`` is ``ingest.pool_stats`` output verbatim (the pinned
    denominators live in it); the PC fields below are derived from a
    single per-card compile pass over the same pool (cards that raise
    ``StateCorruptionError`` appear in ``shape_gaps`` instead).
    """

    set_name: str
    pool_stats: dict[str, Any]
    entry_count: int
    sentence_total: int
    sentence_unique: int
    cards_zero_unparsed: int
    sentences_matched: int
    unparsed_count: int
    ambiguous_entries: tuple[AmbiguityEntry, ...]
    verb_histogram: dict[str, int]
    atom_total: int
    orphan_verbs: tuple[str, ...]
    max_verb_share: float
    targetable_entries: int
    unparsed_queue: tuple[UnparsedEntry, ...]
    shape_gaps: tuple[ShapeGap, ...] = ()

    # -- PC-1 ----------------------------------------------------------------
    @property
    def pc1_card_coverage(self) -> float:
        """Entries with zero unparsed fragments / total entries."""
        return self.cards_zero_unparsed / self.entry_count if self.entry_count else 0.0

    # -- PC-2 ----------------------------------------------------------------
    @property
    def pc2_sentence_coverage(self) -> float:
        """Matched sentences / total sentences (matched = not unparsed)."""
        return (
            self.sentences_matched / self.sentence_total if self.sentence_total else 0.0
        )

    # -- PC-3 ----------------------------------------------------------------
    @property
    def pc3_ambiguous_entries(self) -> int:
        """Number of entries with at least one distinct-outcome ambiguity."""
        return len(self.ambiguous_entries)

    # -- PC-6 ----------------------------------------------------------------
    @property
    def pc6_max_share_verb(self) -> str | None:
        """The verb achieving ``max_verb_share`` (None when no atoms)."""
        if not self.verb_histogram:
            return None
        return max(self.verb_histogram.items(), key=lambda kv: (kv[1], kv[0]))[0]

    # -- PC-8 ----------------------------------------------------------------
    @property
    def pc8_targetable_fraction(self) -> float:
        """Entries with >= 1 TARGET-mode selector / total entries."""
        return self.targetable_entries / self.entry_count if self.entry_count else 0.0

    def to_json(self) -> dict[str, Any]:
        """JSON-safe dict of every report field (queues fully expanded)."""
        data: dict[str, Any] = {
            "set": self.set_name,
            "pool_stats": self.pool_stats,
            "entry_count": self.entry_count,
            "sentence_total": self.sentence_total,
            "sentence_unique": self.sentence_unique,
            "pc1": {
                "cards_zero_unparsed": self.cards_zero_unparsed,
                "denominator": self.entry_count,
                "value": round(self.pc1_card_coverage, 6),
            },
            "pc2": {
                "sentences_matched": self.sentences_matched,
                "denominator": self.sentence_total,
                "value": round(self.pc2_sentence_coverage, 6),
            },
            "pc3": {
                "ambiguous_entries": self.pc3_ambiguous_entries,
                "entries": [e.to_json() for e in self.ambiguous_entries],
            },
            "pc6": {
                "verb_histogram": dict(sorted(self.verb_histogram.items())),
                "atom_total": self.atom_total,
                "orphan_verbs": list(self.orphan_verbs),
                "max_verb_share": round(self.max_verb_share, 6),
                "max_share_verb": self.pc6_max_share_verb,
            },
            "pc8": {
                "targetable_entries": self.targetable_entries,
                "denominator": self.entry_count,
                "value": round(self.pc8_targetable_fraction, 6),
            },
            "unparsed_queue": [e.to_json() for e in self.unparsed_queue],
            "unparsed_count": self.unparsed_count,
        }
        # House OMIT-IF-EMPTY law: zero shape failures adds NO new key, so a
        # gap-free pool (M21) keeps a byte-identical report.
        if self.shape_gaps:
            data["shape_gaps"] = [g.to_json() for g in self.shape_gaps]
        return data


# ---------------------------------------------------------------------------
# measure_pool
# ---------------------------------------------------------------------------


def _compile_pool_tolerant(
    pool: dict[str, RawCard],
    registry: TemplateRegistry,
) -> tuple[dict[str, CompileResult], list[ShapeGap]]:
    """Per-card ``compile_card`` pass mirroring ``compile_pool`` semantics.

    Identical to ``compile_pool`` except that a card whose printed shape
    raises ``StateCorruptionError`` is reported as a ``ShapeGap`` row
    (excluded from ``results``) instead of crashing the whole pass (§8/§11).
    Emblem attachment mirrors ``compiler.compile_pool`` exactly (owner
    lookup by ``related_names``, later same-named entries win) restricted
    to the successfully compiled subset, so the M21 walk semantics —
    emblem atoms reachable both via the owner's record and via the emblem's
    own result entry — are preserved byte-for-byte.
    """
    results: dict[str, CompileResult] = {}
    gaps: list[ShapeGap] = []
    for oid, raw in pool.items():
        try:
            results[oid] = compile_card(raw, registry, None)
        except StateCorruptionError as exc:
            gaps.append(ShapeGap(oid, raw.identity.name, str(exc)[:160]))

    name_to_oid: dict[str, str] = {}
    for oid, raw in pool.items():
        if not raw.is_emblem and oid in results:
            name_to_oid[raw.identity.name] = oid
    for oid, raw in pool.items():
        if not (raw.is_emblem and oid in results):
            continue
        owner_oid = next(
            (name_to_oid[n] for n in raw.related_names if n in name_to_oid), None
        )
        if owner_oid is not None:
            owner_result = results[owner_oid]
            results[owner_oid] = replace(
                owner_result, card=replace(owner_result.card, emblem=results[oid].card)
            )
    return results, gaps


def measure_pool(
    pool: dict[str, RawCard],
    registry: TemplateRegistry,
    set_name: str = "M21",
) -> CoverageReport:
    """One per-card ``compile_card`` pass over ``pool``, reduced to a
    CoverageReport.

    Every pool entry (emblems included) is walked for PC-6 atoms and
    PC-8 selectors; the unparsed queue is the exact per-entry list of
    (oracle_id, name, sentence, bucket_hint) — the instrument that PC-10
    probes in both directions.

    Cards that raise ``StateCorruptionError`` are recorded under
    ``shape_gaps`` and excluded from compiled-result metrics, but every
    PC denominator stays the FULL pool (honesty law: a gap card counts
    against coverage, never shrinks the sample).
    """
    stats = pool_stats(pool)
    results, gaps = _compile_pool_tolerant(pool, registry)

    unparsed_queue: list[UnparsedEntry] = []
    ambiguous_entries: list[AmbiguityEntry] = []
    cards_zero_unparsed = 0
    targetable_entries = 0
    verb_counts: dict[str, int] = {}

    for oid in sorted(results):
        raw = pool[oid]
        result = results[oid]
        name = raw.identity.name

        if not result.unparsed:
            cards_zero_unparsed += 1
        for sentence, hint in result.unparsed:
            unparsed_queue.append(UnparsedEntry(oid, name, sentence, hint))
        for record in result.ambiguities:
            ambiguous_entries.append(
                AmbiguityEntry(
                    oracle_id=oid,
                    name=name,
                    sentence=record.sentence,
                    tids=record.tids,
                    note=record.note,
                )
            )

        has_target_selector = False
        for node in walk(result.card):
            if isinstance(node, Selector) and node.mode is SelectorMode.TARGET:
                has_target_selector = True
            if isinstance(node, Atom):
                vname = node.verb.name
                verb_counts[vname] = verb_counts.get(vname, 0) + 1
        if has_target_selector:
            targetable_entries += 1

    sentence_total = int(stats["sentence_total"])
    unparsed_count = len(unparsed_queue)
    atom_total = sum(verb_counts.values())
    max_verb_share = max(verb_counts.values()) / atom_total if atom_total else 0.0
    orphan_verbs = tuple(
        sorted(v.name for v in Verb if verb_counts.get(v.name, 0) == 0)
    )

    return CoverageReport(
        set_name=set_name,
        pool_stats=stats,
        entry_count=len(pool),
        sentence_total=sentence_total,
        sentence_unique=int(stats["sentence_unique"]),
        cards_zero_unparsed=cards_zero_unparsed,
        sentences_matched=sentence_total - unparsed_count,
        unparsed_count=unparsed_count,
        ambiguous_entries=tuple(sorted(ambiguous_entries, key=_amb_key)),
        verb_histogram=dict(sorted(verb_counts.items())),
        atom_total=atom_total,
        orphan_verbs=orphan_verbs,
        max_verb_share=max_verb_share,
        targetable_entries=targetable_entries,
        unparsed_queue=tuple(sorted(unparsed_queue, key=_unparsed_key)),
        shape_gaps=tuple(sorted(gaps, key=lambda g: (g.card, g.name, g.error))),
    )


def _unparsed_key(entry: UnparsedEntry) -> tuple[str, str]:
    return (entry.oracle_id, entry.sentence)


def _amb_key(entry: AmbiguityEntry) -> tuple[str, str]:
    return (entry.oracle_id, entry.sentence)
