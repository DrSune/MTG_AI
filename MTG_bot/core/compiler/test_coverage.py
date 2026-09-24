"""Tests for the T5 coverage measurement module (coverage.py).

Fast by design: one shared M21 ingest + one shared full-pool measurement in
``setUpClass``.  Denominators are pinned to the real ingest (305 entries /
639 sentences / 510 unique) and the PC-10 null test runs in both directions
on in-memory synthetic cards only.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from MTG_bot.core.ability_tree import Verb
from MTG_bot.core.compiler.coverage import (
    PINNED_ENTRIES,
    PINNED_SENTENCES,
    PINNED_SENTENCES_UNIQUE,
    build_full_registry,
    check_pinned_denominators,
    measure_pool,
)
from MTG_bot.core.compiler.ingest import RawCard, ingest_pool, pool_stats
from MTG_bot.core.identity import CardIdentity

_M21 = Path(__file__).resolve().parents[2] / "data" / "M21.json"

PLANTED_UNPARSED = "Nobody understands this."


def _synthetic_raw(oid: str, name: str, sentences: tuple[str, ...]) -> RawCard:
    return RawCard(
        identity=CardIdentity(oracle_id=oid, name=name),
        type_line="Instant",
        types=("Instant",),
        subtypes=(),
        supertypes=(),
        colors=(),
        color_identity=frozenset(),
        mana_cost_raw=None,
        mana_value=0,
        power_raw=None,
        toughness_raw=None,
        loyalty_raw=None,
        keywords=(),
        sentences=sentences,
        layout="normal",
        is_token=False,
        is_emblem=False,
        token_name_refs=(),
        related_names=(),
    )


class TestPinnedDenominators(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.pool = ingest_pool(_M21)
        cls.stats = pool_stats(cls.pool)

    def test_real_ingest_yields_pinned_denominators(self) -> None:
        self.assertEqual(self.stats["total"], PINNED_ENTRIES)
        self.assertEqual(self.stats["sentence_total"], PINNED_SENTENCES)
        self.assertEqual(self.stats["sentence_unique"], PINNED_SENTENCES_UNIQUE)

    def test_check_pinned_passes_on_real_pool(self) -> None:
        check_pinned_denominators(self.pool)  # must not raise

    def test_check_pinned_fails_loudly_on_drift(self) -> None:
        drifted = dict(self.pool)
        drifted["00000000-0000-0000-0000-000000000099"] = _synthetic_raw(
            "00000000-0000-0000-0000-000000000099", "Drift", ("Extra sentence.",)
        )
        with self.assertRaises(ValueError) as ctx:
            check_pinned_denominators(drifted)
        self.assertIn("pinned denominators changed", str(ctx.exception))


class TestRegistry(unittest.TestCase):
    def test_all_eight_buckets_registered(self) -> None:
        registry = build_full_registry()
        buckets = {t.bucket for t in registry.all()}
        self.assertEqual(
            buckets,
            {"B1", "B2a", "B2b", "B3", "B4", "B5a", "B5b", "B5c"},
        )

    def test_registry_is_nonempty(self) -> None:
        self.assertGreater(len(build_full_registry()), 0)


class TestMeasurePool(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.pool = ingest_pool(_M21)
        cls.registry = build_full_registry()
        cls.report = measure_pool(cls.pool, cls.registry, "M21")

    def test_entry_count_is_pinned(self) -> None:
        self.assertEqual(self.report.entry_count, PINNED_ENTRIES)
        self.assertEqual(self.report.sentence_total, PINNED_SENTENCES)
        self.assertEqual(self.report.sentence_unique, PINNED_SENTENCES_UNIQUE)

    def test_pc1_card_coverage_consistent(self) -> None:
        r = self.report
        entries_with_unparsed = {e.oracle_id for e in r.unparsed_queue}
        self.assertEqual(
            r.cards_zero_unparsed + len(entries_with_unparsed), r.entry_count
        )
        self.assertEqual(r.pc1_card_coverage, r.cards_zero_unparsed / r.entry_count)

    def test_pc2_sentence_coverage_consistent(self) -> None:
        r = self.report
        self.assertEqual(r.sentences_matched + r.unparsed_count, r.sentence_total)
        self.assertEqual(
            r.pc2_sentence_coverage, r.sentences_matched / r.sentence_total
        )
        self.assertEqual(r.unparsed_count, len(r.unparsed_queue))

    def test_pc3_ambiguity_records_shape(self) -> None:
        r = self.report
        self.assertEqual(r.pc3_ambiguous_entries, len(r.ambiguous_entries))
        for entry in r.ambiguous_entries:
            self.assertGreaterEqual(len(entry.tids), 2)
            self.assertIn(entry.oracle_id, self.pool)

    def test_pc6_vocab_consistent(self) -> None:
        r = self.report
        self.assertEqual(sum(r.verb_histogram.values()), r.atom_total)
        expected_orphans = {v.name for v in Verb if v.name not in r.verb_histogram}
        self.assertEqual(set(r.orphan_verbs), expected_orphans)
        if r.atom_total:
            self.assertEqual(
                r.max_verb_share, max(r.verb_histogram.values()) / r.atom_total
            )
        else:
            self.assertEqual(r.max_verb_share, 0.0)

    def test_pc8_targetable_within_bounds(self) -> None:
        r = self.report
        self.assertGreaterEqual(r.targetable_entries, 0)
        self.assertLessEqual(r.targetable_entries, r.entry_count)
        self.assertEqual(
            r.pc8_targetable_fraction, r.targetable_entries / r.entry_count
        )

    def test_to_json_schema(self) -> None:
        data = self.report.to_json()
        for key in (
            "set",
            "pool_stats",
            "entry_count",
            "sentence_total",
            "sentence_unique",
            "pc1",
            "pc2",
            "pc3",
            "pc6",
            "pc8",
            "unparsed_queue",
            "unparsed_count",
        ):
            self.assertIn(key, data)
        self.assertEqual(len(data["unparsed_queue"]), self.report.unparsed_count)


class TestPC10NullTest(unittest.TestCase):
    """Instrument null test — in-memory synthetic cards only, both directions."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = build_full_registry()

    def test_fully_parseable_card_reports_100(self) -> None:
        good = _synthetic_raw(
            "00000000-0000-0000-0000-000000000001", "Null Good", ("Draw a card.",)
        )
        report = measure_pool({good.identity.oracle_id: good}, self.registry)
        self.assertEqual(report.pc1_card_coverage, 1.0)
        self.assertEqual(report.pc2_sentence_coverage, 1.0)
        self.assertEqual(report.unparsed_queue, ())

    def test_planted_unknown_reports_0_with_exact_queue(self) -> None:
        bad = _synthetic_raw(
            "00000000-0000-0000-0000-000000000002", "Null Bad", (PLANTED_UNPARSED,)
        )
        report = measure_pool({bad.identity.oracle_id: bad}, self.registry)
        self.assertEqual(report.pc1_card_coverage, 0.0)
        self.assertEqual(report.pc2_sentence_coverage, 0.0)
        self.assertEqual(len(report.unparsed_queue), 1)
        entry = report.unparsed_queue[0]
        self.assertEqual(entry.sentence, PLANTED_UNPARSED)
        self.assertEqual(entry.oracle_id, bad.identity.oracle_id)
        self.assertEqual(entry.name, "Null Bad")


if __name__ == "__main__":
    unittest.main()
