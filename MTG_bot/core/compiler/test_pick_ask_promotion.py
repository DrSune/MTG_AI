"""T4 P1b pins: the PICK_ASK_ALLOWLIST promotion pass (docs/
T4_PICK_ENUMERATION.md).

The pass lifts the FIRST QConst(1), referent-less, non-cost, non-self-
referential entity CHOOSE selector of each allowlisted (card, verb) onto
the asking ONE_OF channel (the doc-29 lane the search-pick flip already
drives). These tests pin the three failure modes:

1. every allowlisted card compiles with the ONE_OF surface present;
2. the near-miss twins (k>1 choose, cost-victim choose, IS_SOURCE self-
   designation, non-allowlisted card) compile with ZERO ONE_OF — the
   lift never spreads;
3. an allowlist entry whose candidate is a cost or self-designation
   raises StateCorruptionError LOUD (the r20c binding exemption is
   CHOOSE-mode-gated, so a silent flip there would mis-resolve).
"""

from __future__ import annotations

import copy
import unittest
from dataclasses import fields, is_dataclass, replace
from pathlib import Path
from typing import cast

from MTG_bot.core.ability_tree import FAtom, FAtomPred, Selector, SelectorMode
from MTG_bot.core.compiler.compiler import (
    StateCorruptionError,
    _promote_pilot_picks,
    compile_card,
)
from MTG_bot.core.compiler.coverage import build_full_registry
from MTG_bot.core.compiler.ingest import ingest_pool

_M21_PATH = Path(__file__).resolve().parents[2] / "data" / "M21.json"


def _bump_back_to_selfref_choose(node: object) -> object:
    """Test fixture: rewrite the promoted ONE_OF selectors of a compiled
    tree back to the STALE-ALLOWLIST shape — CHOOSE mode, referent-less,
    IS_SOURCE-filtered self-designation — so the loud guard branch is
    exercised against a real allowlisted (card, verb)."""
    if isinstance(node, list):
        rebuilt = [_bump_back_to_selfref_choose(v) for v in node]
        return rebuilt if any(a is not b for a, b in zip(rebuilt, node)) else node
    if isinstance(node, tuple):
        rebuilt = tuple(_bump_back_to_selfref_choose(v) for v in node)
        return rebuilt if any(a is not b for a, b in zip(rebuilt, node)) else node
    if is_dataclass(node) and not isinstance(node, type):
        if isinstance(node, Selector) and node.mode is SelectorMode.ONE_OF:
            return replace(
                node,
                mode=SelectorMode.CHOOSE,
                referent=None,
                filter=FAtom(pred=FAtomPred.IS_SOURCE),
            )
        updates = {
            f.name: _bump_back_to_selfref_choose(getattr(node, f.name))
            for f in fields(node)
        }
        if any(updates[f.name] is not getattr(node, f.name) for f in fields(node)):
            return replace(node, **updates)
    return node


class PickAskPromotion(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.pool = ingest_pool(_M21_PATH)
        cls.registry = build_full_registry()
        cls.oid_of: dict[str, str] = {}
        for oid in cls.pool:
            cls.oid_of.setdefault(cls.pool[oid].identity.name, oid)

    def compile(self, name: str):
        return compile_card(self.pool[self.oid_of[name]], self.registry).card

    def one_of(self, name: str) -> int:
        return repr(self.compile(name).abilities).count("SelectorMode.ONE_OF")

    def choose(self, name: str) -> int:
        return repr(self.compile(name).abilities).count("SelectorMode.CHOOSE")

    def compile_base(self, name: str):
        """Compile with the pick-ask pass switched off (empty allowlist):
        the pre-P1b baseline shape, so CULTIVATE's pre-existing /31
        search-lane ONE_OF surface is counted out of the comparison."""
        import MTG_bot.core.compiler.compiler as comp

        saved = comp.PICK_ASK_ALLOWLIST
        try:
            comp.PICK_ASK_ALLOWLIST = frozenset()
            return self.compile(name)
        finally:
            comp.PICK_ASK_ALLOWLIST = saved

    def test_near_miss_twins_are_byte_identical_to_baseline(self):
        # k>1 choose (Cultivate's "choose two" stays with the /31 search
        # lane), cost-victim choose (Village Rites' sac victim, Scavenging
        # Ooze's exile victim — the r22a sacrifice lane already asks),
        # IS_SOURCE self-designation (Hobblefiend — the r20c exemption is
        # CHOOSE-mode-gated, flipping it is the wrong answer), and a
        # non-allowlisted effect choose (Malefic Scythe's equip victim).
        for name in (
            "Cultivate",
            "Village Rites",
            "Scavenging Ooze",
            "Hobblefiend",
            "Malefic Scythe",
        ):
            self.assertEqual(
                repr(self.compile(name).abilities),
                repr(self.compile_base(name).abilities),
                f"{name}: pick-ask pass changed a non-allowlisted card",
            )

    def test_allowlisted_cards_gain_exactly_where_baseline_had_none(self):
        for name in ("Rain of Revelation", "Rousing Read", "Crypt Lurker"):
            self.assertLess(
                repr(self.compile_base(name).abilities).count("SelectorMode.ONE_OF"),
                repr(self.compile(name).abilities).count("SelectorMode.ONE_OF"),
                f"{name}: lift did not add the ask surface",
            )

    def test_separation_within_allowlisted_cards(self):
        # Crypt Lurker: the MOVE_ZONE ask lifts; the SACRIFICE-menu sibling
        # keeps its CHOOSE encoding (verified against the pack lanes).
        self.assertEqual(self.one_of("Crypt Lurker"), 1)
        self.assertGreaterEqual(self.choose("Crypt Lurker"), 1)
        # Obsessive Stitcher: only the draw-discard MOVE_ZONE lifts; the
        # self-sacrifice COST never does.
        self.assertEqual(self.one_of("Obsessive Stitcher"), 1)
        self.assertGreaterEqual(self.choose("Obsessive Stitcher"), 1)

    def test_allowlist_hit_on_a_forbidden_shape_is_loud(self):
        """Synthesise the stale-allowlist condition: the candidate the
        pass lifts for an allowlisted (card, verb) rewritten into an
        IS_SOURCE self-designation — the guard must RAISE, never silently
        skip (a stale row is a bug, not a no-op; the r20c binding
        exemption is CHOOSE-mode-gated, so a silent flip there would
        mis-resolve the whole effect)."""
        card = self.compile("Rain of Revelation")
        abilities = copy.deepcopy(list(card.abilities))
        poisoned = [_bump_back_to_selfref_choose(ab) for ab in abilities]
        self.assertEqual(
            repr(poisoned).count("SelectorMode.CHOOSE"),
            1,
            "fixture did not reach the promoted selector",
        )
        with self.assertRaises(StateCorruptionError):
            _promote_pilot_picks(cast(list, poisoned), "Rain of Revelation")

    def test_promotion_is_identity_for_unknown_cards(self):
        abilities = self.compile("Titanic Growth").abilities
        self.assertEqual(
            _promote_pilot_picks(list(abilities), "Titanic Growth"), list(abilities)
        )


if __name__ == "__main__":
    unittest.main()
