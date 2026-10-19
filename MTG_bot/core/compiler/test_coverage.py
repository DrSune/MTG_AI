"""Tests for the T5 coverage measurement module (coverage.py).

Fast by design: one shared M21 ingest + one shared full-pool measurement in
``setUpClass``.  Denominators are pinned to the real ingest (305 entries /
639 sentences / 510 unique) and the PC-10 null test runs in both directions
on in-memory synthetic cards only.
"""

from __future__ import annotations

import dataclasses
import json
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
from MTG_bot.core.compiler.ingest import CardFace, RawCard, ingest_pool, pool_stats
from MTG_bot.core.identity import CardIdentity

_M21 = Path(__file__).resolve().parents[2] / "data" / "M21.json"

PLANTED_UNPARSED = "Nobody understands this."


def _synthetic_raw(
    oid: str,
    name: str,
    sentences: tuple[str, ...],
    power_raw: str | None = None,
) -> RawCard:
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
        power_raw=power_raw,
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


def _synthetic_face(sentences: tuple[str, ...], name: str = "Back Side") -> CardFace:
    """Minimal synthetic back face (field pipeline mirrors :class:`CardFace`)."""
    return CardFace(
        name=name,
        type_line="Creature — Spirit",
        types=("Creature",),
        subtypes=("Spirit",),
        supertypes=(),
        colors=(),
        color_identity=frozenset(),
        mana_cost_raw=None,
        mana_value=0,
        power_raw="2",
        toughness_raw="2",
        loyalty_raw=None,
        keywords=(),
        sentences=sentences,
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
    def test_all_buckets_registered(self) -> None:
        registry = build_full_registry()
        buckets = {t.bucket for t in registry.all()}
        self.assertEqual(
            buckets,
            {
                "B1",
                "B2a",
                "B2b",
                "B3",
                "B4",
                "B5a",
                "B5b",
                "B5c",
                "B6",
                "B7",
                "B8",
                "B9",
                "B10",
            },
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
        # OMIT-IF-EMPTY law: a zero-gap pool gains no "shape_gaps" key.
        self.assertNotIn("shape_gaps", data)
        # Same law for the back-face census: M21 has no modal faces, so the
        # real-JSON report gains NO "backface" key and the queue has no
        # "BFACE" rows.
        self.assertNotIn("backface", data)
        self.assertIsNone(self.report.backface_summary)
        self.assertEqual(
            self.report.sentence_total, self.report.pool_stats["sentence_total"]
        )
        self.assertFalse(
            any(e.bucket_hint == "BFACE" for e in self.report.unparsed_queue)
        )


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


class TestShapeGaps(unittest.TestCase):
    """§8/§11 gap-ledger law: unparsable printed shapes are REPORTED rows,
    never a crash, never a silent drop; denominators stay the full pool."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = build_full_registry()

    def test_unparsable_shape_is_reported_not_crash(self) -> None:
        gap = _synthetic_raw(
            "00000000-0000-0000-0000-000000000003",
            "Gap Walker",
            ("Draw a card.",),
            power_raw="1+*",
        )
        # must not raise
        report = measure_pool({gap.identity.oracle_id: gap}, self.registry)
        self.assertEqual(len(report.shape_gaps), 1)
        row = report.shape_gaps[0]
        self.assertEqual(row.card, gap.identity.oracle_id)
        self.assertEqual(row.name, "Gap Walker")
        self.assertIn("parse_pt: unexpected value '1+*'", row.error)
        self.assertLessEqual(len(row.error), 160)
        # excluded from compiled metrics, counted AGAINST coverage:
        self.assertEqual(report.cards_zero_unparsed, 0)
        self.assertEqual(report.entry_count, 1)
        self.assertEqual(report.pc1_card_coverage, 0.0)
        self.assertEqual(report.pc8_targetable_fraction, 0.0)
        self.assertEqual(report.atom_total, 0)  # no compiled atoms walked
        data = report.to_json()
        self.assertIn("shape_gaps", data)
        self.assertEqual(data["shape_gaps"][0]["card"], gap.identity.oracle_id)

    def test_gap_mixed_with_good_keeps_full_denominator(self) -> None:
        good = _synthetic_raw(
            "00000000-0000-0000-0000-000000000004", "Good", ("Draw a card.",)
        )
        gap = _synthetic_raw(
            "00000000-0000-0000-0000-000000000005",
            "Gap",
            ("Draw a card.",),
            power_raw="1+*",
        )
        pool = {good.identity.oracle_id: good, gap.identity.oracle_id: gap}
        report = measure_pool(pool, self.registry)
        self.assertEqual(report.entry_count, 2)  # denominator NOT shrunk
        self.assertEqual(len(report.shape_gaps), 1)
        self.assertEqual(report.cards_zero_unparsed, 1)
        self.assertEqual(report.pc1_card_coverage, 0.5)

    def test_clean_pool_has_no_shape_gaps_key(self) -> None:
        good = _synthetic_raw(
            "00000000-0000-0000-0000-000000000006", "Clean", ("Draw a card.",)
        )
        report = measure_pool({good.identity.oracle_id: good}, self.registry)
        self.assertEqual(report.shape_gaps, ())
        self.assertNotIn("shape_gaps", report.to_json())


class TestBackFaceCensus(unittest.TestCase):
    """Back-face census under ZND-2f (supersedes the /93 measurement-only
    census, KNOWLEDGE/2026-10-18/106 amendment 2): the compiler now READS
    ``RawCard.back_face`` — matched face sentences are covered for real and
    ride in the tree's BackFace node; ONLY unmatched face sentences enter
    the PC-2 denominator's register as "[face B]"/"BFACE" rows. Face verbs
    are TAGGED separately and never merge into the front histogram."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = build_full_registry()

    def test_backface_rows_enter_register_and_grow_denominator(self) -> None:
        card = _synthetic_raw(
            "00000000-0000-0000-0000-000000000010",
            "Modal Mite",
            ("Draw a card.",),  # front: fully parseable
        )
        card = dataclasses.replace(
            card,
            # "Draw two cards." MATCHES a front template — ZND-2f means the
            # face compile covers it, so it is NO LONGER a forced row.
            # "Flip a coin." stays unmatched residue.
            back_face=_synthetic_face(("Draw two cards.", "Flip a coin.")),
        )
        report = measure_pool({card.identity.oracle_id: card}, self.registry)
        # Denominator = front (1) + back (2); only the UNMATCHED face
        # sentence is a register row (TRUTH LAW in both directions).
        self.assertEqual(report.sentence_total, 3)
        self.assertEqual(report.unparsed_count, 1)
        self.assertEqual(report.sentences_matched, 2)
        self.assertAlmostEqual(report.pc2_sentence_coverage, 2.0 / 3.0)
        rows = [e for e in report.unparsed_queue if e.bucket_hint == "BFACE"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].oracle_id, card.identity.oracle_id)
        self.assertEqual(rows[0].name, "Modal Mite [face B]")
        self.assertEqual(rows[0].sentence, "Flip a coin.")
        # PC-1 formula untouched (/96 law): a clean FRONT still counts as
        # compiled even with face residue in the register.
        self.assertEqual(report.cards_zero_unparsed, 1)
        self.assertEqual(report.pc1_card_coverage, 1.0)
        summary = report.backface_summary
        assert summary is not None
        self.assertEqual(summary["unparsed_rows"], 1)
        self.assertEqual(summary["cards_face_whole"], 0)

    def test_faceless_card_report_shape_unchanged(self) -> None:
        card = _synthetic_raw(
            "00000000-0000-0000-0000-000000000011", "Plain", ("Draw a card.",)
        )
        report = measure_pool({card.identity.oracle_id: card}, self.registry)
        self.assertIsNone(report.backface_summary)
        data = report.to_json()
        self.assertNotIn("backface", data)
        self.assertEqual(report.sentence_total, 1)
        self.assertEqual(report.unparsed_queue, ())
        self.assertEqual(report.pc2_sentence_coverage, 1.0)

    def test_backface_summary_counts_and_determinism(self) -> None:
        first = dataclasses.replace(
            _synthetic_raw(
                "00000000-0000-0000-0000-000000000012",
                "A // B",
                ("Whenever A dies, draw a card.",),
            ),
            back_face=_synthetic_face(
                (
                    "Create a 2/2 Spirit creature token.",
                    "Spirits you control get +1/+1.",
                )
            ),
        )
        second = dataclasses.replace(
            _synthetic_raw(
                "00000000-0000-0000-0000-000000000013",
                "Solo",
                ("Draw a card.",),
            ),
            back_face=_synthetic_face(("Scry 1.",)),
        )
        pool = {
            second.identity.oracle_id: second,
            first.identity.oracle_id: first,
        }
        report = measure_pool(pool, self.registry)
        self.assertEqual(
            report.backface_summary,
            {
                "cards_with_faces": 2,
                "sentence_total": 3,
                # ZND-2f: both Spirit sentences are unmatched residue; the
                # Scry face compiles whole (cards_face_whole) and its verb
                # is TAGGED in the face histogram, not the front one.
                "unparsed_rows": 2,
                "cards_face_whole": 1,
                "verb_histogram": {"SCRY": 1},
            },
        )
        data = report.to_json()
        self.assertEqual(data["backface"], report.backface_summary)
        # Deterministic ordering: identical inputs give byte-identical JSON,
        # and the queue is in total (oracle_id, sentence) order.
        again = measure_pool(dict(reversed(list(pool.items()))), self.registry)
        self.assertEqual(
            json.dumps(again.to_json()),
            json.dumps(data),
        )
        keys = [(e.oracle_id, e.sentence) for e in report.unparsed_queue]
        self.assertEqual(keys, sorted(keys))

    def test_gap_card_backface_still_counted(self) -> None:
        # A card whose FRONT shape fails to compile still contributes its
        # back-face sentences to the denominator and the register (honesty
        # law: a gap counts against coverage, never shrinks the sample).
        gap = dataclasses.replace(
            _synthetic_raw(
                "00000000-0000-0000-0000-000000000014",
                "Gap Face",
                ("Draw a card.",),
                power_raw="1+*",
            ),
            back_face=_synthetic_face(("Flip a coin.",)),
        )
        report = measure_pool({gap.identity.oracle_id: gap}, self.registry)
        self.assertEqual(len(report.shape_gaps), 1)
        self.assertEqual(report.sentence_total, 2)  # 1 front + 1 back
        self.assertEqual(report.unparsed_count, 1)  # the BFACE row
        row = report.unparsed_queue[0]
        self.assertEqual(row.bucket_hint, "BFACE")
        self.assertEqual(row.name, "Gap Face [face B]")


if __name__ == "__main__":
    unittest.main()
