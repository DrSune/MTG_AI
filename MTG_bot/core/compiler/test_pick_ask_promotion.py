"""The pick-ask promotion pass.

Promotion is driven by the structural predicate _is_liftable_pick (a
QConst(1), referent-less, non-cost, non-self-referential entity CHOOSE ->
the asking ONE_OF channel), not by card registration; the two override
frozensets are escape hatches only. These tests pin the failure modes:

1. the pilot cards compile with the ONE_OF surface present;
2. the near-miss twins (k>1 choose, cost-victim choose, IS_SOURCE self-
   designation) gain no ONE_OF: the lift never spreads across an axis;
3. a FORCE_ASK override whose candidate is a cost or self-designation
   raises StateCorruptionError (the binding exemption is CHOOSE-mode-gated,
   so a silent flip there would mis-resolve);
4. a FORCE_ASK row hitting a predicate-declined near-miss surface raises
   NotImplementedError: the hatch has no lane for it (a referent-bound
   selector cannot be ONE_OF; no opponent-seat routing, gap ledger L-27),
   so a hit is a bug to fix, never a silent no-op.
"""

from __future__ import annotations

import copy
import unittest
from dataclasses import fields, is_dataclass, replace
from pathlib import Path
from typing import cast

from MTG_bot.core.ability_tree import (
    ControllerRef,
    FAtom,
    FAtomPred,
    Selector,
    SelectorMode,
    Zone,
    ZoneKind,
)
import MTG_bot.core.compiler.compiler as comp
from MTG_bot.core.compiler.compiler import (
    StateCorruptionError,
    _promote_liftable_picks,
    compile_card,
)
from MTG_bot.core.compiler.coverage import build_full_registry
from MTG_bot.core.compiler.ingest import ingest_pool

_M21_PATH = Path(__file__).resolve().parents[2] / "data" / "M21.json"


def _bump_back_to_selfref_choose(node: object) -> object:
    """Rewrite the promoted ONE_OF selectors of a compiled tree into a
    referent-less CHOOSE IS_SOURCE self-designation, so the loud guard runs
    against a real (card, verb) row."""
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
        """Compile with the promotion off (the predicate declines every
        surface, both override sets empty), so ONE_OF surfaces of other
        passes (Cultivate's search pick) count out of the comparison."""
        saved = comp._is_liftable_pick
        saved_ask, saved_silent = (
            comp.PICK_ASK_FORCE_ASK,
            comp.PICK_ASK_FORCE_SILENT,
        )
        try:
            comp._is_liftable_pick = lambda node, in_cost: False
            comp.PICK_ASK_FORCE_ASK = frozenset()
            comp.PICK_ASK_FORCE_SILENT = frozenset()
            return self.compile(name)
        finally:
            comp._is_liftable_pick = saved
            comp.PICK_ASK_FORCE_ASK = saved_ask
            comp.PICK_ASK_FORCE_SILENT = saved_silent

    def test_near_miss_twins_are_byte_identical_to_baseline(self):
        # k>1 choose (Cultivate's "choose two" stays with the search pick),
        # cost-victim choose (Village Rites' sacrifice, Scavenging Ooze's
        # exile: the cost lane already asks), IS_SOURCE self-designation
        # (Hobblefiend: the binding exemption is CHOOSE-mode-gated), and a
        # non-promoted effect choose (Malefic Scythe's equip victim).
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

    def test_pilot_cards_gain_exactly_where_baseline_had_none(self):
        # The structural predicate covers every pilot card: none loses its ask.
        for name in ("Rain of Revelation", "Rousing Read", "Crypt Lurker"):
            self.assertLess(
                repr(self.compile_base(name).abilities).count("SelectorMode.ONE_OF"),
                repr(self.compile(name).abilities).count("SelectorMode.ONE_OF"),
                f"{name}: lift did not add the ask surface",
            )

    def test_separation_axes_under_the_predicate(self):
        # Crypt Lurker: both modal victims (SACRIFICE + MOVE_ZONE discard)
        # are real QConst(1) entity decisions, so both lift.
        self.assertEqual(self.one_of("Crypt Lurker"), 2)
        # Obsessive Stitcher: the effect-side MOVE_ZONE lifts; the
        # self-sacrifice cost never does.
        self.assertEqual(self.one_of("Obsessive Stitcher"), 1)
        self.assertGreaterEqual(self.choose("Obsessive Stitcher"), 1)

    def test_force_ask_hit_on_a_forbidden_shape_is_loud(self):
        """A FORCE_ASK row whose candidate is an IS_SOURCE self-designation
        raises, never silently skips: the binding exemption is
        CHOOSE-mode-gated, so a flip there would mis-resolve the effect."""
        card = self.compile("Rain of Revelation")
        abilities = copy.deepcopy(list(card.abilities))
        poisoned = [_bump_back_to_selfref_choose(ab) for ab in abilities]
        self.assertEqual(
            repr(poisoned).count("SelectorMode.CHOOSE"),
            1,
            "fixture did not reach the promoted selector",
        )
        saved = comp.PICK_ASK_FORCE_ASK
        try:
            comp.PICK_ASK_FORCE_ASK = frozenset({("Rain of Revelation", "MOVE_ZONE")})
            with self.assertRaises(StateCorruptionError):
                _promote_liftable_picks(cast(list, poisoned), "Rain of Revelation")
        finally:
            comp.PICK_ASK_FORCE_ASK = saved

    def test_force_ask_hit_on_a_near_miss_is_loud_not_silent(self):
        """A FORCE_ASK row for a predicate-declined near-miss surface (here a
        referent-bound CHOOSE) raises NotImplementedError, never a silent
        no-op: the ONE_OF channel cannot carry such a surface."""

        def to_near_miss(node: object) -> object:
            if isinstance(node, list):
                rebuilt = [to_near_miss(v) for v in node]
                return (
                    rebuilt if any(a is not b for a, b in zip(rebuilt, node)) else node
                )
            if isinstance(node, tuple):
                rebuilt = tuple(to_near_miss(v) for v in node)
                return (
                    rebuilt if any(a is not b for a, b in zip(rebuilt, node)) else node
                )
            if is_dataclass(node) and not isinstance(node, type):
                if isinstance(node, Selector) and node.mode is SelectorMode.ONE_OF:
                    return replace(
                        node,
                        mode=SelectorMode.CHOOSE,
                        referent="result",
                        # a referent selector has one neutral zone
                        zones=(Zone(ZoneKind.ANY, ControllerRef.ANY),),
                    )
                updates = {
                    f.name: to_near_miss(getattr(node, f.name)) for f in fields(node)
                }
                if any(
                    updates[f.name] is not getattr(node, f.name) for f in fields(node)
                ):
                    return replace(node, **updates)
            return node

        near_miss = [
            to_near_miss(ab)
            for ab in copy.deepcopy(list(self.compile("Rain of Revelation").abilities))
        ]
        self.assertEqual(
            repr(near_miss).count("referent='result'"),
            1,
            "fixture did not reach the promoted selector",
        )
        saved = comp.PICK_ASK_FORCE_ASK
        try:
            comp.PICK_ASK_FORCE_ASK = frozenset({("Rain of Revelation", "MOVE_ZONE")})
            with self.assertRaises(NotImplementedError):
                _promote_liftable_picks(cast(list, near_miss), "Rain of Revelation")
        finally:
            comp.PICK_ASK_FORCE_ASK = saved

    def test_force_silent_row_pins_the_surface_to_choose(self):
        """A promoted surface registered in FORCE_SILENT keeps the CHOOSE
        encoding, byte-identical to the base compile."""
        self.assertEqual(self.one_of("Rain of Revelation"), 1)
        saved = comp.PICK_ASK_FORCE_SILENT
        try:
            comp.PICK_ASK_FORCE_SILENT = frozenset(
                {("Rain of Revelation", "MOVE_ZONE")}
            )
            self.assertEqual(
                repr(self.compile("Rain of Revelation").abilities),
                repr(self.compile_base("Rain of Revelation").abilities),
            )
        finally:
            comp.PICK_ASK_FORCE_SILENT = saved

    def test_promotion_is_identity_for_unknown_cards(self):
        abilities = self.compile("Titanic Growth").abilities
        self.assertEqual(
            _promote_liftable_picks(list(abilities), "Titanic Growth"), list(abilities)
        )


if __name__ == "__main__":
    unittest.main()
