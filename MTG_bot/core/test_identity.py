"""Tests for the identity primitives.

Pins down the two fixes from DESIGN_CARD_POOL.md "Fix identity first":
keying on the stable scryfall oracle id, and the split handle namespaces
(a card handle and a zone handle can both be 5 and never collide).
"""

import unittest

from MTG_bot.core.identity import (
    Handle,
    HandleSpace,
    CardIdentity,
    LegalityFlags,
    validate_oracle_id,
)

A_ORACLE = "eecb3047-a563-441a-9175-200421981ac3"  # Ugin, the Spirit Dragon
B_ORACLE = "9c017fa9-8c01-7a53-8e2e-3df449644fcf"


class TestOracleId(unittest.TestCase):
    def test_valid_id_passes(self):
        self.assertEqual(validate_oracle_id(A_ORACLE), A_ORACLE)

    def test_rowid_rejected(self):
        # A volatile rowid slipping in as the key is exactly the bug we are killing.
        with self.assertRaises(ValueError):
            validate_oracle_id("269")

    def test_empty_rejected(self):
        with self.assertRaises(ValueError):
            validate_oracle_id("")

    def test_malformed_uuid_rejected(self):
        with self.assertRaises(ValueError):
            validate_oracle_id("not-a-uuid")


class TestHandle(unittest.TestCase):
    def test_namespace_is_part_of_identity(self):
        self.assertNotEqual(Handle("card", 5), Handle("zone", 5))

    def test_equal_when_both_match(self):
        self.assertEqual(Handle("card", 5), Handle("card", 5))

    def test_ordering_is_by_namespace_then_index(self):
        self.assertLess(Handle("card", 0), Handle("card", 1))
        self.assertLess(Handle("card", 9), Handle("zone", 0))

    def test_hashable_for_dict_keys(self):
        d = {Handle("card", 0): "x", Handle("zone", 0): "y"}
        self.assertEqual(d[Handle("card", 0)], "x")
        self.assertEqual(d[Handle("zone", 0)], "y")


class TestHandleSpace(unittest.TestCase):
    def test_monotonic(self):
        space = HandleSpace("card")
        self.assertEqual(space.allocate(), Handle("card", 0))
        self.assertEqual(space.allocate(), Handle("card", 1))
        self.assertEqual(space.allocate(), Handle("card", 2))

    def test_independent_namespaces_do_not_share_axis(self):
        cards = HandleSpace("card")
        zones = HandleSpace("zone")
        for _ in range(3):
            cards.allocate()
        self.assertEqual(zones.allocate(), Handle("zone", 0))
        self.assertEqual(cards.count, 3)
        self.assertEqual(zones.count, 1)

    def test_no_reuse_within_a_space(self):
        space = HandleSpace("card")
        allocated = {space.allocate() for _ in range(50)}
        self.assertEqual(len(allocated), 50)


class TestLegalityFlags(unittest.TestCase):
    def test_enabled_requires_both(self):
        self.assertTrue(LegalityFlags(True, True).enabled)
        self.assertFalse(LegalityFlags(True, False).enabled)
        self.assertFalse(LegalityFlags(False, True).enabled)
        self.assertFalse(LegalityFlags(False, False).enabled)

    def test_defaults_are_permissive(self):
        self.assertTrue(LegalityFlags().enabled)


class TestCardIdentity(unittest.TestCase):
    def _ugin(self) -> CardIdentity:
        return CardIdentity(
            oracle_id=A_ORACLE,
            name="Ugin, the Spirit Dragon",
            type_line="Legendary Planewalker — Ugin",
            set_code="M21",
            colors=("B",),
            mana_cost="{4}{B}{B}",
            cmc=6,
            loyalty="6",
            keywords=(),
            oracle_text="Some ability text.",
        )

    def test_frozen_and_hashable(self):
        c = self._ugin()
        h = hash(c)
        self.assertEqual(h, hash(c))
        with self.assertRaises(Exception):
            c.name = "changed"  # frozen dataclass

    def test_primary_key_is_oracle_id(self):
        self.assertEqual(self._ugin().primary_key, A_ORACLE)

    def test_distinct_cards_are_distinct(self):
        ugin = self._ugin()
        other = CardIdentity(oracle_id=B_ORACLE, name="Some Other Card")
        self.assertNotEqual(ugin, other)

    def test_color_identity_from_colors_and_cost(self):
        c = CardIdentity(oracle_id=A_ORACLE, name="X", colors=("W", "U"), mana_cost="{1}{U}", cmc=1)
        self.assertEqual(c.color_identity(), frozenset({"W", "U"}))

    def test_rejects_bad_oracle_id_at_construction(self):
        with self.assertRaises(ValueError):
            CardIdentity(oracle_id="42", name="Nope")

    def test_defaults_for_a_land(self):
        plains = CardIdentity(oracle_id=B_ORACLE, name="Plains", type_line="Basic Land — Plains", set_code="M21")
        self.assertIsNone(plains.cmc)
        self.assertEqual(plains.colors, ())
        self.assertFalse(plains.is_token)
        self.assertEqual(plains.color_identity(), frozenset())


if __name__ == "__main__":
    unittest.main()
