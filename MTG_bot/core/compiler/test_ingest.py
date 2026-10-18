r"""Tests for the structured MTGJSON ingest (compiler step 1).

Pins down the decisions of MTG_bot/core/compiler/ingest.py:

- structured field mapping (oracle id, name, types, colours, mana value,
  P/T, loyalty, keywords, token/emblem flags, related-card names) with
  typed StateCorruptionError on malformed records (missing name or type
  line, colours outside the WUBRG set, negative mana value, wrong
  relatedCards shape);
- the deterministic PAREN-DEPTH-AWARE sentence split rule and how it
  treats parenthetical keyword reminders (single-sentence reminders stay
  one sentence; multi-sentence parentheticals stay ONE sentence);
- oracle-id keying over the explicit dedup key: a duplicate whose
  captured fields differ is corruption, a reprint differing only in
  non-captured raw fields (number, uuid, rarity, …) dedupes to one entry;
- the modal-DFC face fold (side a/b records sharing one oracle id fold
  into ``RawCard.back_face``; every other duplicate mismatch still
  raises) against synthetic pools and the real ZNR file;
- pool_stats shape (incl. ``emblems`` / ``emblem_owners``);
- the smoke test against the real M21 pool file.
"""

import dataclasses
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from MTG_bot.core.compiler.ingest import (
    CardFace,
    RawCard,
    ingest_card,
    ingest_pool,
    pool_stats,
    split_sentences,
)
from MTG_bot.core.errors import StateCorruptionError
from MTG_bot.core.identity import validate_oracle_id

# Fabricated but well-formed 36-char oracle ids for synthetic fixtures.
ORACLE_A = "1a2b3c4d-5e6f-4a7b-8c9d-0e1f2a3b4c5d"
ORACLE_B = "9f8e7d6c-5b4a-4321-0fed-cba987654321"
ORACLE_C = "00112233-4455-4666-8777-8899aabbccdd"
ORACLE_D = "abc12345-def6-4a7b-8c9d-0e1f2a3b4c5e"
ORACLE_E = "fedcba98-7654-4321-abcd-001122334455"

# The real pool file (KNOWLEDGE/NUMBERS.md baseline: 397 cards / 20 tokens).
M21_PATH = Path(__file__).resolve().parents[3] / "MTG_bot" / "data" / "M21.json"

# The real ZNR pool file (KNOWLEDGE/2026-10-18/92: 445 card records with
# 36 modal-DFC cards stored as per-face side a/b entries + 12 tokens).
ZNR_PATH = Path(__file__).resolve().parents[3] / "MTG_bot" / "data" / "ZNR.json"


def _card(
    oracle_id: str,
    name: str,
    *,
    text: str
    | None = "First strike (It deals combat damage before creatures without first strike.)",
    types: tuple[str, ...] = ("Creature",),
    subtypes: tuple[str, ...] = ("Beast",),
    supertypes: tuple[str, ...] = (),
    colors: tuple[str, ...] = ("G",),
    color_identity: tuple[str, ...] | None = None,
    mana_cost: str | None = "{2}{G}",
    mana_value: float | None = 3.0,
    power: str | None = "2",
    toughness: str | None = "2",
    loyalty: str | None = None,
    keywords: tuple[str, ...] = (),
    layout: str = "normal",
    set_code: str = "M21",
    number: str = "100",
    uuid: str = "00000000-0000-4000-8000-000000000001",
    related_cards: dict[str, Any] | None = None,
    side: str | None = None,
    face_name: str | None = None,
) -> dict[str, Any]:
    """Build a synthetic MTGJSON v5 card record (absent fields omitted)."""
    raw: dict[str, Any] = {
        "name": name,
        "type": "Creature — Beast" if types == ("Creature",) else " ".join(types),
        "types": list(types),
        "subtypes": list(subtypes),
        "supertypes": list(supertypes),
        "colors": list(colors),
        "layout": layout,
        "setCode": set_code,
        "number": number,
        "uuid": uuid,
        "identifiers": {"scryfallOracleId": oracle_id},
    }
    if side is not None:
        raw["side"] = side
    if face_name is not None:
        raw["faceName"] = face_name
    if color_identity is not None:
        raw["colorIdentity"] = list(color_identity)
    if mana_cost is not None:
        raw["manaCost"] = mana_cost
    if mana_value is not None:
        raw["manaValue"] = mana_value
    if power is not None:
        raw["power"] = power
    if toughness is not None:
        raw["toughness"] = toughness
    if loyalty is not None:
        raw["loyalty"] = loyalty
    if keywords:
        raw["keywords"] = list(keywords)
    if text is not None:
        raw["text"] = text
    if related_cards is not None:
        raw["relatedCards"] = related_cards
    return raw


class TestSplitSentences(unittest.TestCase):
    def test_two_sentence_text(self):
        # The spec's canonical case.
        sentences = split_sentences(
            "When ~ enters the battlefield, draw a card. ~ deals 1 damage."
        )
        self.assertEqual(
            sentences,
            ("When ~ enters the battlefield, draw a card.", "~ deals 1 damage."),
        )

    def test_parenthetical_reminder_stays_attached(self):
        # Decision: keyword-reminder parentheses contain no period+whitespace
        # boundary, so the reminder stays inside the one sentence chunk.
        sentence = "Flying (Attacking doesn't cause this creature to tap.)"
        self.assertEqual(split_sentences(sentence), (sentence,))

    def test_parenthetical_period_delimited_becomes_own_chunk(self):
        # Decision: a parenthetical chunk that is period+whitespace-delimited
        # from its neighbour becomes its own chunk.
        text = "When ~ enters the battlefield, draw a card. (This is a reminder.)"
        self.assertEqual(
            split_sentences(text),
            ("When ~ enters the battlefield, draw a card.", "(This is a reminder.)"),
        )

    def test_multi_sentence_parenthetical_stays_one_sentence(self):
        # The 2026-09-15 fix: a parenthetical reminder that contains its
        # own period+whitespace boundaries is ONE sentence — those
        # boundaries sit at paren depth 1, not 0, so they do not split.
        # (The old flat regex broke the M21 Opt text into three chunks.)
        text = (
            "Scry 1. (Look at the top card of your library. "
            "You may put that card on the bottom.)"
        )
        self.assertEqual(
            split_sentences(text),
            (
                "Scry 1.",
                "(Look at the top card of your library. You may put that card on the bottom.)",
            ),
        )

    def test_nested_parenthetical_boundaries_stay_inside(self):
        # Depth is tracked per level; a boundary inside the inner parens
        # (depth 2) or the outer parens (depth 1) never splits.
        text = "Do X. (A (B. C) D.)"
        self.assertEqual(split_sentences(text), ("Do X.", "(A (B. C) D.)"))

    def test_stray_closing_paren_does_not_poison_depth(self):
        # A ")" at depth 0 clamps to zero instead of going negative, so a
        # following "(" still opens real depth and the reminder's internal
        # period does not split.
        text = ")(Look at the top card. You may put it back.)"
        self.assertEqual(split_sentences(text), (text,))

    def test_line_breaks_separate_sentences(self):
        text = "[+2]: The planeswalker deals 3 damage to any target.\n[-10]: You gain 7 life."
        self.assertEqual(
            split_sentences(text),
            (
                "[+2]: The planeswalker deals 3 damage to any target.",
                "[-10]: You gain 7 life.",
            ),
        )

    def test_question_and_exclamation_boundaries(self):
        self.assertEqual(
            split_sentences("Draw a card? No! Yes."),
            ("Draw a card?", "No!", "Yes."),
        )

    def test_blank_and_none_text_give_empty_tuple(self):
        self.assertEqual(split_sentences(None), ())
        self.assertEqual(split_sentences(""), ())
        self.assertEqual(split_sentences("   "), ())

    def test_deterministic(self):
        text = "First strike. Then trample. Then nothing."
        self.assertEqual(split_sentences(text), split_sentences(text))


class TestIngestCard(unittest.TestCase):
    def test_fields_mapped_correctly(self):
        raw = _card(ORACLE_A, "Grizzly Bears")
        card = ingest_card(raw)
        # identity
        self.assertEqual(card.identity.oracle_id, ORACLE_A)
        self.assertEqual(card.identity.name, "Grizzly Bears")
        self.assertEqual(card.identity.type_line, "Creature — Beast")
        self.assertEqual(card.identity.set_code, "M21")
        self.assertEqual(card.identity.colors, ("G",))
        self.assertEqual(card.identity.mana_cost, "{2}{G}")
        self.assertEqual(card.identity.cmc, 3)
        self.assertEqual(card.identity.power, "2")
        self.assertEqual(card.identity.toughness, "2")
        self.assertIsNone(card.identity.loyalty)
        self.assertEqual(
            card.identity.oracle_text,
            "First strike (It deals combat damage before creatures without first strike.)",
        )
        self.assertFalse(card.identity.is_token)
        # raw card
        self.assertEqual(card.type_line, "Creature — Beast")
        self.assertEqual(card.types, ("Creature",))
        self.assertEqual(card.subtypes, ("Beast",))
        self.assertEqual(card.supertypes, ())
        self.assertEqual(card.colors, ("G",))
        self.assertEqual(card.color_identity, frozenset({"G"}))
        self.assertEqual(card.mana_cost_raw, "{2}{G}")
        self.assertEqual(card.mana_value, 3)
        self.assertEqual(card.power_raw, "2")
        self.assertEqual(card.toughness_raw, "2")
        self.assertIsNone(card.loyalty_raw)
        self.assertEqual(card.keywords, ())
        self.assertEqual(
            card.sentences,
            (
                "First strike (It deals combat damage before creatures without first strike.)",
            ),
        )
        self.assertEqual(card.layout, "normal")
        self.assertFalse(card.is_token)
        self.assertFalse(card.is_emblem)
        self.assertEqual(card.token_name_refs, ())
        self.assertEqual(card.related_names, ())

    def test_multi_sentence_text_splits(self):
        raw = _card(
            ORACLE_A,
            "Grizzly Bears",
            text="When ~ enters the battlefield, draw a card. ~ deals 1 damage.",
        )
        card = ingest_card(raw)
        self.assertEqual(
            card.sentences,
            ("When ~ enters the battlefield, draw a card.", "~ deals 1 damage."),
        )

    def test_planeswalker_loyalty_is_loyalty_not_toughness(self):
        raw = _card(
            ORACLE_B,
            "Ugin, the Spirit Dragon",
            text="[+2]: Ugin deals 3 damage to any target.\n[-X]: Exile each permanent with mana value X.",
            types=("Planeswalker", "Ugin"),
            subtypes=("Ugin",),
            colors=("B",),
            color_identity=("B",),
            mana_cost="{4}{B}{B}",
            mana_value=6.0,
            power=None,
            toughness=None,
            loyalty="6",
        )
        card = ingest_card(raw)
        self.assertEqual(card.loyalty_raw, "6")
        self.assertIsNone(card.power_raw)
        self.assertIsNone(card.toughness_raw)
        self.assertEqual(card.identity.loyalty, "6")
        self.assertIsNone(card.identity.power)
        self.assertIsNone(card.identity.toughness)
        self.assertEqual(card.mana_value, 6)

    def test_token_is_detected_from_layout_and_types(self):
        raw = _card(
            ORACLE_C,
            "Angel",
            text="Flying",
            types=("Token", "Creature"),
            colors=(),
            color_identity=(),
            mana_cost=None,
            mana_value=None,
            keywords=("Flying",),
            layout="token",
        )
        card = ingest_card(raw)
        self.assertTrue(card.is_token)
        self.assertTrue(card.identity.is_token)
        self.assertFalse(card.is_emblem)
        self.assertIsNone(card.mana_cost_raw)
        self.assertEqual(card.mana_value, 0)
        self.assertEqual(card.keywords, ("Flying",))

    def test_emblem_is_emblem_not_token(self):
        # The pool's three emblems (CRITICAL-1): layout "emblem", typed
        # Emblem. An emblem is NOT a token, and its related_names is
        # exactly its owner names (their only relatedCards key is
        # reverseRelated — here including the token it creates).
        raw = _card(
            ORACLE_E,
            "Basri Ket Emblem",
            text="At the beginning of combat on your turn, create a 1/1 white Soldier creature token with flying.",
            types=("Emblem",),
            subtypes=(),
            colors=(),
            color_identity=(),
            mana_cost=None,
            mana_value=None,
            power=None,
            toughness=None,
            layout="emblem",
            related_cards={"reverseRelated": ["Basri Ket", "Soldier"]},
        )
        card = ingest_card(raw)
        self.assertTrue(card.is_emblem)
        self.assertFalse(card.is_token)
        self.assertFalse(card.identity.is_token)
        self.assertEqual(card.layout, "emblem")
        self.assertEqual(card.related_names, ("Basri Ket", "Soldier"))

    def test_related_names_union_across_related_cards_lists(self):
        # Structured, verbatim union over every list in relatedCards —
        # sorted and deduped. This pool dump mixes names and record uuids
        # in those lists; the ingest keeps them as-is (no NLP, no filter).
        raw = _card(
            ORACLE_A,
            "Some Card",
            related_cards={
                "reverseRelated": ["Beta", "Alpha"],
                "tokens": ["Alpha", "a9e8d7c6-5b4a-4321-0fed-cba987654321"],
            },
        )
        card = ingest_card(raw)
        self.assertEqual(
            card.related_names,
            ("Alpha", "Beta", "a9e8d7c6-5b4a-4321-0fed-cba987654321"),
        )

    def test_related_cards_wrong_shape_raises_state_corruption(self):
        raw = _card(ORACLE_A, "Grizzly Bears")
        raw["relatedCards"] = ["not", "a", "dict"]
        with self.assertRaises(StateCorruptionError):
            ingest_card(raw)
        raw["relatedCards"] = {"reverseRelated": "not-a-list"}
        with self.assertRaises(StateCorruptionError):
            ingest_card(raw)
        raw["relatedCards"] = {"reverseRelated": [1, 2]}
        with self.assertRaises(StateCorruptionError):
            ingest_card(raw)

    def test_color_identity_falls_back_to_colors_when_absent(self):
        raw = _card(ORACLE_D, "Some Card", color_identity=None, colors=("W", "U"))
        card = ingest_card(raw)
        self.assertEqual(card.color_identity, frozenset({"W", "U"}))

    def test_missing_oracle_id_raises_state_corruption(self):
        raw = _card(ORACLE_A, "Grizzly Bears")
        del raw["identifiers"]["scryfallOracleId"]
        with self.assertRaises(StateCorruptionError) as ctx:
            ingest_card(raw)
        self.assertIn("scryfallOracleId", str(ctx.exception))

    def test_malformed_oracle_id_raises_state_corruption(self):
        raw = _card(ORACLE_A, "Grizzly Bears")
        raw["identifiers"] = {"scryfallOracleId": "269"}  # a rowid slipped in
        with self.assertRaises(StateCorruptionError):
            ingest_card(raw)

    def test_missing_identifiers_block_raises_state_corruption(self):
        raw = _card(ORACLE_A, "Grizzly Bears")
        del raw["identifiers"]
        with self.assertRaises(StateCorruptionError):
            ingest_card(raw)

    def test_missing_name_raises_state_corruption(self):
        raw = _card(ORACLE_A, "Grizzly Bears")
        raw["name"] = ""
        with self.assertRaises(StateCorruptionError):
            ingest_card(raw)

    def test_text_absent_gives_none_and_no_sentences(self):
        raw = _card(ORACLE_A, "Wishcoin Crab", text=None)
        card = ingest_card(raw)
        self.assertIsNone(card.identity.oracle_text)
        self.assertEqual(card.sentences, ())

    def test_empty_text_gives_no_sentences(self):
        raw = _card(ORACLE_A, "Wishcoin Crab", text="")
        self.assertEqual(ingest_card(raw).sentences, ())

    def test_basic_land_has_no_power_toughness_or_loyalty(self):
        raw = _card(
            ORACLE_B,
            "Plains",
            text="({T}: Add {W}.)",
            types=("Basic Land", "Plains"),
            subtypes=(),
            supertypes=("Basic", "Land"),
            colors=(),
            color_identity=(),
            mana_cost=None,
            mana_value=None,
            power=None,
            toughness=None,
        )
        card = ingest_card(raw)
        self.assertIsNone(card.power_raw)
        self.assertIsNone(card.toughness_raw)
        self.assertIsNone(card.loyalty_raw)
        self.assertEqual(card.mana_value, 0)
        # The land ability reminder text is still one structured sentence.
        self.assertEqual(card.sentences, ("({T}: Add {W}.)",))

    def test_non_integer_mana_value_raises_state_corruption(self):
        raw = _card(ORACLE_A, "Grizzly Bears", mana_value=2.5)
        with self.assertRaises(StateCorruptionError):
            ingest_card(raw)

    def test_negative_mana_value_raises_state_corruption(self):
        raw = _card(ORACLE_A, "Grizzly Bears", mana_value=-2.0)
        with self.assertRaises(StateCorruptionError):
            ingest_card(raw)

    def test_missing_type_line_raises_state_corruption(self):
        # name and type are REQUIRED — a record missing either, or with a
        # blank type line, is corruption, not a card to guess at.
        raw = _card(ORACLE_A, "Grizzly Bears")
        del raw["type"]
        with self.assertRaises(StateCorruptionError):
            ingest_card(raw)
        raw = _card(ORACLE_A, "Grizzly Bears")
        raw["type"] = ""
        with self.assertRaises(StateCorruptionError):
            ingest_card(raw)

    def test_color_outside_five_colour_set_raises(self):
        raw = _card(ORACLE_A, "Grizzly Bears", colors=("G", "Q"))
        with self.assertRaises(StateCorruptionError):
            ingest_card(raw)
        # colorIdentity is checked against the same set.
        raw = _card(ORACLE_A, "Grizzly Bears", colors=(), color_identity=("Q",))
        with self.assertRaises(StateCorruptionError):
            ingest_card(raw)

    def test_wrong_type_field_raises_state_corruption(self):
        raw = _card(ORACLE_A, "Grizzly Bears")
        raw["keywords"] = "Flying"  # not a list
        with self.assertRaises(StateCorruptionError):
            ingest_card(raw)

    def test_record_is_frozen_and_hashable(self):
        card = ingest_card(_card(ORACLE_A, "Grizzly Bears"))
        self.assertEqual(hash(card), hash(card))
        # Frozen dataclass: __setattr__ raises FrozenInstanceError. Route the
        # mutation through an Any-typed alias so the check is dynamic
        # (pyright-clean).
        mutable: Any = card
        with self.assertRaises(dataclasses.FrozenInstanceError):
            mutable.sentences = ()


class TestIngestPool(unittest.TestCase):
    def _pool_path(self, doc: dict[str, Any]) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "pool.json"
        path.write_text(json.dumps(doc), encoding="utf-8")
        return path

    def test_two_cards_and_one_token_give_three_entries(self):
        cards = [_card(ORACLE_A, "Zeta Creature"), _card(ORACLE_B, "Alpha Beast")]
        tokens = [
            _card(
                ORACLE_C,
                "Angel",
                types=("Token", "Creature"),
                mana_cost=None,
                mana_value=None,
                layout="token",
            )
        ]
        path = self._pool_path({"meta": {}, "data": {"cards": cards, "tokens": tokens}})
        pool = ingest_pool(path)
        self.assertEqual(len(pool), 3)
        self.assertEqual(set(pool), {ORACLE_A, ORACLE_B, ORACLE_C})
        self.assertTrue(pool[ORACLE_C].is_token)
        # Stable deterministic order: by name, then oracle id.
        self.assertEqual(list(pool), [ORACLE_B, ORACLE_C, ORACLE_A])

    def test_conflicting_duplicate_oracle_id_raises(self):
        cards = [
            _card(
                ORACLE_A,
                "Alpha Beast",
                number="1",
                uuid="00000000-0000-4000-8000-000000000001",
            ),
            _card(
                ORACLE_A,
                "Beta Beast",
                number="2",
                uuid="00000000-0000-4000-8000-000000000002",
            ),
        ]
        path = self._pool_path({"meta": {}, "data": {"cards": cards, "tokens": []}})
        with self.assertRaises(StateCorruptionError) as ctx:
            ingest_pool(path)
        self.assertEqual(ctx.exception.context["oracle_id"], ORACLE_A)

    def test_identical_reprint_dedupes_to_one_entry(self):
        # Same card, different printing (number/uuid differ, all structured
        # fields identical): the oracle id names the card, so one entry.
        cards = [
            _card(
                ORACLE_A,
                "Alpha Beast",
                number="1",
                uuid="00000000-0000-4000-8000-000000000001",
            ),
            _card(
                ORACLE_A,
                "Alpha Beast",
                number="2",
                uuid="00000000-0000-4000-8000-000000000002",
            ),
        ]
        path = self._pool_path({"meta": {}, "data": {"cards": cards, "tokens": []}})
        pool = ingest_pool(path)
        self.assertEqual(len(pool), 1)
        self.assertEqual(pool[ORACLE_A].identity.name, "Alpha Beast")

    def test_duplicate_differing_only_in_ignored_raw_fields_dedupes(self):
        # The dedup key is over the CAPTURED fields (_dedup_key): rarity,
        # number, uuid and purchaseUrls differ between these printings,
        # but every captured field is identical, so this is the same card
        # — one entry (this is exactly the 112-reprint situation in the
        # real M21 file).
        cards = [
            _card(
                ORACLE_A,
                "Alpha Beast",
                number="1",
                uuid="00000000-0000-4000-8000-000000000001",
            ),
            _card(
                ORACLE_A,
                "Alpha Beast",
                number="2",
                uuid="00000000-0000-4000-8000-000000000002",
            ),
        ]
        cards[1]["rarity"] = "mythic"
        cards[1]["purchaseUrls"] = {"foo": "bar"}
        path = self._pool_path({"meta": {}, "data": {"cards": cards, "tokens": []}})
        pool = ingest_pool(path)
        self.assertEqual(len(pool), 1)
        self.assertEqual(pool[ORACLE_A].identity.name, "Alpha Beast")

    def test_duplicate_differing_in_captured_field_raises(self):
        # Same oracle id and name, different oracle text: that is not a
        # reprint, that is corruption.
        cards = [
            _card(ORACLE_A, "Alpha Beast", number="1", text="First ability."),
            _card(ORACLE_A, "Alpha Beast", number="2", text="Different ability."),
        ]
        path = self._pool_path({"meta": {}, "data": {"cards": cards, "tokens": []}})
        with self.assertRaises(StateCorruptionError) as ctx:
            ingest_pool(path)
        self.assertEqual(ctx.exception.context["oracle_id"], ORACLE_A)

    def test_missing_file_raises(self):
        with self.assertRaises(StateCorruptionError):
            ingest_pool("/nonexistent/pool.json")

    def test_malformed_json_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pool.json"
            path.write_text("{ not json", encoding="utf-8")
            with self.assertRaises(StateCorruptionError):
                ingest_pool(path)

    def test_bad_top_level_shape_raises(self):
        for doc in [
            {},
            {"data": {}},
            {"data": {"cards": []}},
            {"data": {"tokens": []}},
        ]:
            path = self._pool_path(doc)
            with self.assertRaises(StateCorruptionError):
                ingest_pool(path)

    def test_deterministic_across_calls(self):
        cards = [
            _card(ORACLE_A, "Zeta"),
            _card(ORACLE_B, "Alpha"),
            _card(ORACLE_C, "Beta"),
        ]
        path = self._pool_path({"meta": {}, "data": {"cards": cards, "tokens": []}})
        self.assertEqual(ingest_pool(path), ingest_pool(path))
        self.assertEqual(list(ingest_pool(path)), list(ingest_pool(path)))


class TestModalDFCFaceFold(unittest.TestCase):
    """The ZNR face pattern (KNOWLEDGE/2026-10-18/92): side a/b records
    sharing one oracle id fold into ``RawCard.back_face``; EVERY other
    duplicate-oracle-id mismatch still raises StateCorruptionError."""

    def _pool_path(self, doc: dict[str, Any]) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "pool.json"
        path.write_text(json.dumps(doc), encoding="utf-8")
        return path

    def _ingest(self, cards: list[dict[str, Any]]) -> dict[str, RawCard]:
        return ingest_pool(
            self._pool_path({"meta": {}, "data": {"cards": cards, "tokens": []}})
        )

    @staticmethod
    def _front(oracle_id: str, number: str = "12", **overrides: Any) -> dict[str, Any]:
        raw = _card(
            oracle_id,
            "Alpha Spell // Alpha Land",
            layout="modal_dfc",
            side="a",
            face_name="Alpha Spell",
            number=number,
            text="Deal 2 damage.",
            mana_cost="{2}{R}",
            mana_value=3.0,
            power=None,
            toughness=None,
            colors=("R",),
            types=("Sorcery",),
            subtypes=(),
        )
        raw.update(overrides)
        return raw

    @staticmethod
    def _back(oracle_id: str, number: str = "12", **overrides: Any) -> dict[str, Any]:
        raw = _card(
            oracle_id,
            "Alpha Spell // Alpha Land",
            layout="modal_dfc",
            side="b",
            face_name="Alpha Land",
            number=number,
            text="{T}: Add {R}.",
            mana_cost=None,
            mana_value=None,
            power=None,
            toughness=None,
            colors=(),
            types=("Land",),
            subtypes=(),
        )
        raw.update(overrides)
        return raw

    def test_face_pair_folds_into_one_entry(self):
        pool = self._ingest([self._front(ORACLE_A), self._back(ORACLE_A)])
        self.assertEqual(len(pool), 1)
        card = pool[ORACLE_A]
        # The front becomes the RawCard as today.
        self.assertEqual(card.identity.name, "Alpha Spell // Alpha Land")
        self.assertEqual(card.layout, "modal_dfc")
        self.assertEqual(card.mana_cost_raw, "{2}{R}")
        self.assertEqual(card.sentences, ("Deal 2 damage.",))
        # The back folds into structured face data (zero-loss, §11). Use
        # assertEqual: assertIs on freshly constructed frozen dataclasses
        # always fails (PITFALLS).
        self.assertEqual(
            card.back_face,
            CardFace(
                name="Alpha Land",
                type_line="Land",
                types=("Land",),
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
                sentences=("{T}: Add {R}.",),
            ),
        )

    def test_face_name_derived_from_double_slash_when_absent(self):
        front = self._front(ORACLE_A)
        back = self._back(ORACLE_A)
        del front["faceName"]
        del back["faceName"]
        card = self._ingest([front, back])[ORACLE_A]
        self.assertIsNotNone(card.back_face)
        self.assertEqual(card.back_face.name, "Alpha Land")

    def test_variant_printings_of_both_faces_fold_to_one_entry(self):
        # The real ZNR shape: 2 printings (number 12 and 317) of EACH face;
        # the fold applies AFTER the per-side reprint dedup.
        pool = self._ingest(
            [
                self._front(ORACLE_A, number="12"),
                self._back(ORACLE_A, number="12"),
                self._front(
                    ORACLE_A, number="317", uuid="00000000-0000-4000-8000-000000000317"
                ),
                self._back(
                    ORACLE_A, number="317", uuid="00000000-0000-4000-8000-000000000318"
                ),
            ]
        )
        self.assertEqual(len(pool), 1)
        self.assertEqual(pool[ORACLE_A].back_face.name, "Alpha Land")

    def test_two_differing_front_faces_raise(self):
        # The law stays provably intact: two side-a records whose CAPTURED
        # fields differ are corruption, not a face fold.
        with self.assertRaises(StateCorruptionError) as ctx:
            self._ingest(
                [
                    self._front(ORACLE_A),
                    self._front(ORACLE_A, number="317", text="Deal 3 damage."),
                ]
            )
        self.assertEqual(ctx.exception.context["oracle_id"], ORACLE_A)

    def test_two_differing_back_faces_raise(self):
        with self.assertRaises(StateCorruptionError) as ctx:
            self._ingest(
                [
                    self._front(ORACLE_A),
                    self._back(ORACLE_A),
                    self._back(ORACLE_A, number="317", text="{T}: Add {G}."),
                ]
            )
        self.assertEqual(ctx.exception.context["oracle_id"], ORACLE_A)

    def test_back_without_front_raises(self):
        with self.assertRaises(StateCorruptionError) as ctx:
            self._ingest([self._back(ORACLE_A)])
        self.assertEqual(ctx.exception.context["oracle_id"], ORACLE_A)

    def test_normal_record_colliding_with_face_pair_raises(self):
        # A side-less record sharing the oracle id of a face pair is not the
        # face pattern: corruption.
        with self.assertRaises(StateCorruptionError):
            self._ingest(
                [
                    _card(ORACLE_A, "Impostor"),
                    self._front(ORACLE_A),
                    self._back(ORACLE_A),
                ]
            )
        with self.assertRaises(StateCorruptionError):
            self._ingest(
                [
                    self._front(ORACLE_A),
                    _card(ORACLE_A, "Impostor"),
                    self._back(ORACLE_A),
                ]
            )

    def test_unsupported_side_raises(self):
        with self.assertRaises(StateCorruptionError):
            self._ingest([self._front(ORACLE_A), self._back(ORACLE_A, side="c")])

    def test_lone_front_without_back_stands_as_single_faced_entry(self):
        # A side-a record with no side-b partner is not a duplicate at all:
        # it becomes an ordinary entry with back_face None.
        pool = self._ingest([self._front(ORACLE_A)])
        self.assertEqual(len(pool), 1)
        self.assertIsNone(pool[ORACLE_A].back_face)

    def test_normal_card_back_face_defaults_none(self):
        card = ingest_card(_card(ORACLE_A, "Grizzly Bears"))
        self.assertIsNone(card.back_face)


class TestSmokeRealZNRPool(unittest.TestCase):
    """Smoke test against the real ZNR pool file (KNOWLEDGE/2026-10-18/92):
    445 card records + 12 tokens, 270 unique card oracle ids (36 modal DFCS
    stored as per-face side a/b entries across 2 printings, plus frame /
    alt-art variant entries) and 12 token oracle ids disjoint from the
    cards: the oracle-id-keyed pool is 282 entries with 36 back faces."""

    def setUp(self) -> None:
        if not ZNR_PATH.is_file():
            self.skipTest(f"real pool file not present: {ZNR_PATH}")

    def test_pool_size(self):
        self.assertEqual(len(ingest_pool(ZNR_PATH)), 282)  # 270 cards + 12 tokens

    def test_emeria_fold(self):
        pool = ingest_pool(ZNR_PATH)
        matches = [
            c for c in pool.values() if c.identity.name.startswith("Emeria's Call //")
        ]
        self.assertEqual(len(matches), 1)  # 4 file entries (2 faces x 2 printings) -> 1
        card = matches[0]
        self.assertEqual(card.layout, "modal_dfc")
        self.assertIsNotNone(card.back_face)
        self.assertEqual(card.back_face.name, "Emeria, Shattered Skyclave")
        self.assertEqual(card.back_face.type_line, "Land")
        self.assertIsNone(card.back_face.mana_cost_raw)  # land back face: no mana cost
        self.assertEqual(card.back_face.mana_value, 0)
        self.assertEqual(card.back_face.colors, ())
        self.assertEqual(card.back_face.color_identity, frozenset({"W"}))
        self.assertTrue(
            card.back_face.sentences
        )  # back oracle text captured, zero-loss
        self.assertEqual(
            card.back_face.sentences[0], "As this land enters, you may pay 3 life."
        )
        # The front half stays the RawCard itself.
        self.assertEqual(card.mana_cost_raw, "{4}{W}{W}{W}")
        self.assertEqual(
            card.identity.name, "Emeria's Call // Emeria, Shattered Skyclave"
        )

    def test_every_modal_dfc_folded_and_tokens_untouched(self):
        pool = ingest_pool(ZNR_PATH)
        folded = [c for c in pool.values() if c.back_face is not None]
        self.assertEqual(len(folded), 36)
        for card in folded:
            self.assertEqual(card.layout, "modal_dfc")
            self.assertNotEqual(
                card.identity.name.split(" // ", 1)[0], card.back_face.name
            )
        tokens = [c for c in pool.values() if c.is_token]
        self.assertEqual(len(tokens), 12)
        for token in tokens:
            self.assertIsNone(token.back_face)

    def test_pool_is_deterministic(self):
        pool_a = ingest_pool(ZNR_PATH)
        pool_b = ingest_pool(ZNR_PATH)
        self.assertEqual(list(pool_a), list(pool_b))
        self.assertEqual(pool_a, pool_b)

    def test_m21_pool_unchanged(self):
        # No side fields present -> old path byte-for-byte: 285 cards + 20
        # tokens, zero back faces (the corruption law never saw a face).
        if not M21_PATH.is_file():
            self.skipTest(f"real pool file not present: {M21_PATH}")
        pool = ingest_pool(M21_PATH)
        self.assertEqual(len(pool), 305)
        self.assertEqual(sum(1 for c in pool.values() if c.back_face is not None), 0)


class TestPoolStats(unittest.TestCase):
    def _pool(self) -> dict[str, RawCard]:
        card1 = ingest_card(
            _card(
                ORACLE_A,
                "Alpha",
                text="First strike (It deals combat damage before creatures without first strike.)",
            )
        )
        card2 = ingest_card(
            _card(
                ORACLE_B,
                "Beta",
                text="First strike (It deals combat damage before creatures without first strike.)\nWhen ~ enters the battlefield, draw a card.",
                keywords=("Flying", "Vigilance"),
            )
        )
        card3 = ingest_card(
            _card(
                ORACLE_C,
                "Gamma",
                text="First strike (It deals combat damage before creatures without first strike.)",
                mana_cost="{5}{U}{B}{R}",
                mana_value=9.0,
            )
        )
        token = ingest_card(
            _card(
                ORACLE_D,
                "Angel",
                text="Flying",
                types=("Token", "Creature"),
                mana_cost=None,
                mana_value=None,
                keywords=("Flying",),
                layout="token",
            )
        )
        land = ingest_card(
            _card(
                ORACLE_E,
                "Plains",
                text="({T}: Add {W}.)",
                types=("Basic Land", "Plains"),
                subtypes=(),
                colors=(),
                color_identity=(),
                mana_cost=None,
                mana_value=None,
                power=None,
                toughness=None,
            )
        )
        return {c.identity.oracle_id: c for c in (card1, card2, card3, token, land)}

    def test_stats_counts(self):
        stats = pool_stats(self._pool())
        self.assertEqual(stats["total"], 5)
        self.assertEqual(stats["with_text"], 5)
        # card1: 1, card2: 2, card3: 1, token: 1, land: 1
        self.assertEqual(stats["sentence_total"], 6)
        # the first-strike sentence is shared by card1, card2 and card3
        self.assertEqual(stats["sentence_unique"], 4)
        self.assertEqual(stats["keywords"], {"Flying": 2, "Vigilance": 1})
        self.assertEqual(stats["layouts"], {"normal": 4, "token": 1})
        # card1/card2 default to mana value 3, card3 to 9 (5+), token/land to 0.
        self.assertEqual(
            stats["mana_value"], {"0": 2, "1": 0, "2": 0, "3": 2, "4": 0, "5+": 1}
        )
        # No emblems in this pool.
        self.assertEqual(stats["emblems"], 0)
        self.assertEqual(stats["emblem_owners"], {})

    def test_stats_emblem_count_and_owners(self):
        # The emblem -> owner association the old ingest dropped: the
        # emblem's related_names (its only relatedCards key is
        # reverseRelated) is the owner association.
        card1 = ingest_card(
            _card(
                ORACLE_A,
                "Alpha",
                text="First strike (It deals combat damage before creatures without first strike.)",
            )
        )
        emblem = ingest_card(
            _card(
                ORACLE_E,
                "Basri Ket Emblem",
                text="At the beginning of combat on your turn, create a 1/1 white Soldier creature token with flying.",
                types=("Emblem",),
                subtypes=(),
                colors=(),
                color_identity=(),
                mana_cost=None,
                mana_value=None,
                power=None,
                toughness=None,
                layout="emblem",
                related_cards={"reverseRelated": ["Basri Ket", "Soldier"]},
            )
        )
        stats = pool_stats({c.identity.oracle_id: c for c in (card1, emblem)})
        self.assertEqual(stats["total"], 2)
        self.assertEqual(stats["layouts"], {"emblem": 1, "normal": 1})
        self.assertEqual(stats["emblems"], 1)
        self.assertEqual(stats["emblem_owners"], {ORACLE_E: ("Basri Ket", "Soldier")})

    def test_stats_empty_pool(self):
        stats = pool_stats({})
        self.assertEqual(stats["total"], 0)
        self.assertEqual(stats["with_text"], 0)
        self.assertEqual(stats["sentence_total"], 0)
        self.assertEqual(stats["sentence_unique"], 0)
        self.assertEqual(stats["keywords"], {})
        self.assertEqual(stats["layouts"], {})
        self.assertEqual(
            stats["mana_value"], {"0": 0, "1": 0, "2": 0, "3": 0, "4": 0, "5+": 0}
        )
        self.assertEqual(stats["emblems"], 0)
        self.assertEqual(stats["emblem_owners"], {})


class TestSmokeRealM21Pool(unittest.TestCase):
    """Smoke test against the real M21 pool file (KNOWLEDGE/NUMBERS.md).

    File-level baselines (paren-depth-aware split, re-measured 2026-09-15):
    397 card records + 20 tokens, 391 with text, 927 sentences, 503 unique
    (cards). Supersedes the 2026-09-14 flat-regex baseline 952/509 — the
    old rule mis-split 23 records carrying multi-sentence parenthetical
    reminders (see ``split_sentences``); 25 sentence boundaries inside
    parens are no longer split (952 - 25 = 927).

    Pool-level reality (measured 2026-09-15): the file appends reprint
    printings — 112 of the 397 card records repeat an oracle id with every
    captured field identical (different card number/uuid/rarity). The
    oracle id names the card, not the printing, so ingest_pool dedupes
    those to one entry each: the oracle-id-keyed pool is 285 cards + 20
    tokens = 305 entries (291 with text, 639 sentences, 510 unique across
    cards+tokens; 3 emblems with their owner names).
    """

    def setUp(self) -> None:
        if not M21_PATH.is_file():
            self.skipTest(f"real pool file not present: {M21_PATH}")

    def test_file_level_baselines(self):
        doc = json.loads(M21_PATH.read_text(encoding="utf-8"))
        data = doc["data"]
        cards, tokens = data["cards"], data["tokens"]
        self.assertEqual(len(cards), 397)
        self.assertEqual(len(tokens), 20)
        # Every record carries a well-formed 36-char oracle id.
        for record in [*cards, *tokens]:
            validate_oracle_id(record["identifiers"]["scryfallOracleId"])
        # Re-measured 2026-09-15 (paren-depth-aware split): 391 cards with
        # text, 927 sentences, 503 unique (old flat-regex rule: 952/509).
        with_text = [c for c in cards if c.get("text")]
        self.assertEqual(len(with_text), 391)
        file_sentences = [s for c in with_text for s in split_sentences(c["text"])]
        self.assertEqual(len(file_sentences), 927)
        self.assertEqual(len(set(file_sentences)), 503)

    def test_pool_entries_and_keying(self):
        pool = ingest_pool(M21_PATH)
        self.assertEqual(len(pool), 305)  # 285 cards + 20 tokens after dedup
        for oracle_id in pool:
            self.assertEqual(len(oracle_id), 36)
            validate_oracle_id(oracle_id)
        stats = pool_stats(pool)
        self.assertEqual(stats["layouts"], {"emblem": 3, "normal": 285, "token": 17})
        self.assertEqual(stats["total"], 305)
        self.assertEqual(stats["with_text"], 291)
        self.assertEqual(stats["sentence_total"], 639)
        self.assertEqual(stats["sentence_unique"], 510)
        self.assertEqual(stats["emblems"], 3)
        self.assertEqual(
            stats["emblem_owners"],
            {
                "56c1893f-1382-4a31-a28a-ea604677fcdb": ("Liliana, Waker of the Dead",),
                "8a908da7-b41c-4712-b7dc-8c6027875d36": ("Garruk, Unleashed",),
                "ab67e4ec-9392-4130-970f-6ad65656e5c1": (
                    "Basri Ket",
                    "Soldier",
                ),
            },
        )
        for card in pool.values():
            self.assertFalse(card.is_token and card.is_emblem)
            if card.is_emblem:
                self.assertTrue(card.related_names)

    def test_pool_is_deterministic(self):
        pool_a = ingest_pool(M21_PATH)
        pool_b = ingest_pool(M21_PATH)
        self.assertEqual(list(pool_a), list(pool_b))
        self.assertEqual(pool_a, pool_b)


if __name__ == "__main__":
    unittest.main()
