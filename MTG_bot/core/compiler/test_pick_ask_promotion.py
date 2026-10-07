"""T4 P1b pins: the pick-ask promotion pass (docs/T4_PICK_ENUMERATION.md).

Stage 2: promotion is driven by the STRUCTURAL predicate _is_liftable_pick
(QConst(1), referent-less, non-cost, non-self-referential entity CHOOSE ->
the asking ONE_OF channel), not by card registration; the two override
frozensets are escape hatches only. These tests pin the failure modes:

1. the hand-picked pilot cards compile with the ONE_OF surface present
   (the predicate reproduces the whole pilot — no card lost);
2. the near-miss twins (k>1 choose, cost-victim choose, IS_SOURCE self-
   designation) compile with ZERO new ONE_OF — the lift never spreads
   across an axis;
3. a FORCE_ASK override whose candidate is a cost or self-designation
   raises StateCorruptionError LOUD (the r20c binding exemption is
   CHOOSE-mode-gated, so a silent flip there would mis-resolve);
4. a FORCE_ASK row hitting a predicate-declined NEAR-MISS surface raises
   NotImplementedError LOUD (review fix): the hatch has no honest lane
   (C2 forbids referent+ONE_OF; L-27 provider-seat routing absent), so a
   hit is a bug to fix, never a silent no-op.
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
        """Compile with the promotion predicate switched off (structural
        rule declined for every surface, both override sets emptied): the
        pre-P1b baseline shape, so CULTIVATE's pre-existing /31 search-lane
        ONE_OF surface is counted out of the comparison."""
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

    def test_pilot_cards_gain_exactly_where_baseline_had_none(self):
        # Stage 2 regression: the structural predicate must reproduce the
        # whole stage-1 pilot — no pilot card loses its ask.
        for name in ("Rain of Revelation", "Rousing Read", "Crypt Lurker"):
            self.assertLess(
                repr(self.compile_base(name).abilities).count("SelectorMode.ONE_OF"),
                repr(self.compile(name).abilities).count("SelectorMode.ONE_OF"),
                f"{name}: lift did not add the ask surface",
            )

    def test_separation_axes_under_the_predicate(self):
        # Crypt Lurker: BOTH modal victims (SACRIFICE + MOVE_ZONE discard)
        # are real QConst(1) entity decisions -> both lift (stage-2 widening
        # over the pilot's MOVE_ZONE-only row; the census counts both).
        self.assertEqual(self.one_of("Crypt Lurker"), 2)
        # Obsessive Stitcher: the effect-side MOVE_ZONE lifts; the
        # self-sacrifice COST never does (r22a lane + {context} axis).
        self.assertEqual(self.one_of("Obsessive Stitcher"), 1)
        self.assertGreaterEqual(self.choose("Obsessive Stitcher"), 1)

    def test_force_ask_hit_on_a_forbidden_shape_is_loud(self):
        """Synthesise the stale-override condition: a FORCE_ASK row whose
        candidate the pass rewrites into an IS_SOURCE self-designation —
        the guard must RAISE, never silently skip (a stale row is a bug,
        not a no-op; the r20c binding exemption is CHOOSE-mode-gated, so a
        silent flip there would mis-resolve the whole effect)."""
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
        """Review fix 2026-10-07: the hatch's DOCUMENTED use case — a
        FORCE_ASK row for a predicate-declined near-miss surface (here the
        referent-bound CHOOSE of the comment's example, rewritten into a
        compiled tree, C2-neutral zone) — must RAISE NotImplementedError,
        never silently no-op: the ONE_OF channel cannot honestly carry
        such a surface (C2 forbids referent+ONE_OF; L-27 provider-seat
        routing absent), so a row hit means someone trusts an unimplemented
        escape hatch."""

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
                        zone=Zone(ZoneKind.ANY, ControllerRef.ANY),
                        zones=(),
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
        """Escape hatch symmetry: registering a promoted surface in
        FORCE_SILENT keeps the pre-P1b CHOOSE encoding byte-identically."""
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
