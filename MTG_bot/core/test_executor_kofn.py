# -*- coding: utf-8 -*-
"""T2 k-of-n ONE_OF (doc 30 K-OF-N SPEC, 2026-10-07).

The partition selector ASKS ``want`` times over the shrinking menu — the
same loop shape ``binding.py``'s TARGET designation already runs (QConst
exact / QAtMost + NONE-stop after the mandatory first pick), the tag
progress token sits AFTER the frozen kind prefix (``one_of:1of2:…``) so
bc_data's site-kind law needs no new vocabulary, and the want==1 lane is
BYTE-FROZEN (every golden that exists today is QConst(1); the replay pins
must not move). Pool census (2026-10-07): ZERO pool cards fire want>1
yet — this atom deliberately enters at volume 0 (doc 30 transfer-test);
these fixtures are the seed the packs cannot yet provide.
"""

from __future__ import annotations

import unittest

from MTG_bot.core.ability_tree import (
    FAtom,
    FAtomPred,
    QAtMost,
    QConst,
    QUnbounded,
    Selector,
    SelectorMode,
    Seq,
    Verb,
)
from MTG_bot.core.executor.durations_min import DurationLedger
from MTG_bot.core.executor import Executor
from MTG_bot.core.executor.decisions import site_digest
from MTG_bot.core.executor.quantity import ExecCtx
from MTG_bot.core.executor.query import legal_targets, rest_of
from MTG_bot.core.executor.selectors import resolve_selector
from MTG_bot.core.state import (
    ZONE_BATTLEFIELD,
    ZONE_HAND,
    ZONE_LIBRARY,
    GameWorld,
)
from MTG_bot.core.test_executor_binding import (
    BF_YOU,
    HAND_YOU,
    LIB_YOU,
    UNIV,
    atom,
    card_id,
    reset_oracle_ids,
)

LAND = FAtom(FAtomPred.TYPE_EQ, string_value="Land")


class KOfNCase(unittest.TestCase):
    def setUp(self) -> None:
        reset_oracle_ids()
        self.world = GameWorld(num_players=2, start_life=20, master_seed=41)
        self.p0, self.p1 = self.world.player_order[0], self.world.player_order[1]
        self.fo = self.world.add_card(
            card_id("Forest", type_line="Basic Land"), self.p0, ZONE_LIBRARY
        )
        self.pl = self.world.add_card(
            card_id("Plains", type_line="Basic Land"), self.p0, ZONE_LIBRARY
        )
        self.sw = self.world.add_card(
            card_id("Swamp", type_line="Basic Land"), self.p0, ZONE_LIBRARY
        )
        self.spell = self.world.add_card(
            card_id("Twin Fetch", type_line="Instant"), self.p0, ZONE_HAND
        )
        self.ex = Executor(self.world)

    def _seq(self, sel: Selector) -> Seq:
        return Seq((atom(Verb.MOVE_ZONE, cards=sel, destination=HAND_YOU),))

    def _one_of(self, count) -> Selector:
        return Selector(count, SelectorMode.ONE_OF, LAND, LIB_YOU)

    # ------------------------------------------------------ want = 2 exact

    def test_want2_asks_twice_menu_shrinks(self):
        self.ex.apply_effect(
            self._seq(self._one_of(QConst(2))),
            source=self.spell,
            controller=self.p0,
            decisions=(str(self.fo), str(self.pl)),
        )
        self.assertEqual(self.world.zone_of(self.fo).kind, ZONE_HAND)
        self.assertEqual(self.world.zone_of(self.pl).kind, ZONE_HAND)
        self.assertEqual(self.world.zone_of(self.sw).kind, ZONE_LIBRARY)
        log = self.ex.decisions.ask_log
        self.assertEqual(len(log), 2)  # one ask per pick, ask order

    def test_want2_progress_tag_after_kind_prefix(self):
        self.ex.apply_effect(
            self._seq(self._one_of(QConst(2))),
            source=self.spell,
            controller=self.p0,
            decisions=(str(self.sw), str(self.pl)),
        )
        (what1, a1), (what2, a2) = self.ex.decisions.ask_log
        self.assertTrue(what1.startswith("one_of:"))  # frozen KIND prefix
        self.assertIn(":1of2:", what1)
        self.assertIn(":2of2:", what2)
        self.assertEqual((a1, a2), (str(self.sw), str(self.pl)))

    def test_want2_singleton_autofills_no_ask(self):
        for h in (self.pl, self.sw):
            self.world.move_card(
                h, self.world.players[self.p0].zone(ZONE_HAND)
            )  # only Forest remains in the library
        self.ex.apply_effect(
            self._seq(self._one_of(QConst(2))),
            source=self.spell,
            controller=self.p0,
            decisions=(),
        )
        self.assertEqual(self.world.zone_of(self.fo).kind, ZONE_HAND)
        self.assertEqual(self.ex.decisions.ask_log, [])  # §1.4: nothing to ask

    def test_want2_over2_asks_once_then_autofills(self):
        # n == want: the menu offers ONE real decision; the last legal
        # filler is taken without a second ask (binding.py:1392 shape).
        self.world.move_card(self.sw, self.world.players[self.p0].zone(ZONE_HAND))
        self.ex.apply_effect(
            self._seq(self._one_of(QConst(2))),
            source=self.spell,
            controller=self.p0,
            decisions=(str(self.fo),),
        )
        self.assertEqual(len(self.ex.decisions.ask_log), 1)
        zones = {self.world.zone_of(h).kind for h in (self.fo, self.pl)}
        self.assertEqual(zones, {ZONE_HAND})

    # ------------------------------------------------------ frozen want = 1

    def test_want1_lane_is_byte_frozen(self):
        vocab = tuple(str(h) for h in sorted([self.fo, self.pl, self.sw]))
        self.ex.apply_effect(
            self._seq(self._one_of(QConst(1))),
            source=self.spell,
            controller=self.p0,
            decisions=(str(self.pl),),
        )
        ((what, answer),) = self.ex.decisions.ask_log
        # the EXACT pre-T2 tag: kind : source : digest — no progress token.
        self.assertEqual(what, f"one_of:{self.spell}:{site_digest(vocab)}")
        self.assertEqual(answer, str(self.pl))

    # ------------------------------------------------------ QAtMost + NONE

    def test_qatmost_none_stops_after_first_pick(self):
        seen: list[tuple[str, tuple[str, ...]]] = []

        def prov(vocab, what):
            seen.append((what, tuple(vocab)))
            return str(self.sw) if len(seen) == 1 else "NONE"

        self.ex.decisions.provider = prov
        self.ex.apply_effect(
            self._seq(self._one_of(QAtMost(2))),
            source=self.spell,
            controller=self.p0,
            decisions=(),
        )
        self.assertEqual(self.world.zone_of(self.sw).kind, ZONE_HAND)
        self.assertEqual(self.world.zone_of(self.fo).kind, ZONE_LIBRARY)
        self.assertEqual(len(seen), 2)
        (what2, vocab2) = seen[1]
        self.assertIn(":2of2:", what2)
        self.assertEqual(vocab2[-1], "NONE")  # stoppable lane, not vocab[0]

    def test_qatmost_none_at_first_ask_refused(self):
        # C17: the FIRST pick is mandatory — NONE is not in the first menu,
        # so a pool word the vocabulary lacks cannot answer it (raises).
        with self.assertRaises(ValueError):
            self.ex.apply_effect(
                self._seq(self._one_of(QAtMost(2))),
                source=self.spell,
                controller=self.p0,
                decisions=("NONE",),
            )

    # ------------------------------------------------------ count shapes

    def test_qunbounded_one_of_raises_naming_the_shape(self):
        # Two guard layers: the Selector CONSTRUCTOR already refuses a
        # QUnbounded ONE_OF, and the resolve loop refuses any other
        # non-QConst/QAtMost shape (flag, never guess).
        with self.assertRaises(ValueError) as cm:
            self._one_of(QUnbounded())
        self.assertIn("QUnbounded", str(cm.exception))
        from MTG_bot.core.ability_tree import QAtLeast

        with self.assertRaises(NotImplementedError) as cm:
            self.ex.apply_effect(
                self._seq(self._one_of(QAtLeast(2))),
                source=self.spell,
                controller=self.p0,
                decisions=(),
            )
        self.assertIn("QAtLeast", str(cm.exception))

    # ------------------------------------------------------ effect per pick

    def test_effect_applies_to_each_pick(self):
        # {effect-of-each-choice}: the verb iterates the pick-set — two
        # lands on the battlefield, ONE_OF(2) TAP, ask once, auto-fill.
        for h in (self.fo, self.pl):
            self.world.move_card(h, self.world.players[self.p0].zone(ZONE_BATTLEFIELD))
        self.world.move_card(self.sw, self.world.players[self.p0].zone(ZONE_HAND))
        sel = Selector(QConst(2), SelectorMode.ONE_OF, LAND, BF_YOU)
        self.ex.apply_effect(
            Seq((atom(Verb.TAP, target=sel),)),
            source=self.spell,
            controller=self.p0,
            decisions=(str(self.pl),),
        )
        self.assertTrue(self.world.cards[self.fo].tapped)
        self.assertTrue(self.world.cards[self.pl].tapped)

    # ------------------------------------------------------ REST, k picks

    def test_rest_subtracts_every_pick(self):
        ctx = ExecCtx(
            world=self.world,
            ledger=DurationLedger(),
            controller=self.p0,
            source=self.spell,
            bindings={},
            decisions=(str(self.fo), str(self.pl)),
        )
        picked = resolve_selector(self._one_of(QConst(2)), ctx)
        self.assertEqual(picked, sorted([self.fo, self.pl]))
        rest = resolve_selector(
            Selector(QConst(1), SelectorMode.REST, LAND, LIB_YOU), ctx
        )
        self.assertEqual(rest, [self.sw])  # BOTH picks subtracted
        self.assertEqual(ctx.one_of_picks, tuple(sorted([self.fo, self.pl])))


class TestQueryMirror(KOfNCase):
    """§8.3: the query slot reports what the runtime loop will actually do."""

    def _slot(self, count):
        return legal_targets(
            self.world,
            self.ex,
            self._one_of(count),
            source=self.spell,
            controller=self.p0,
        )

    def test_const1_slot_frozen(self):
        slot = self._slot(QConst(1))
        self.assertEqual((slot.min_count, slot.max_count, slot.forced), (1, 1, False))

    def test_const2_slot_exact(self):
        slot = self._slot(QConst(2))
        self.assertEqual((slot.min_count, slot.max_count, slot.forced), (2, 2, False))

    def test_const2_single_candidate_forced(self):
        for h in (self.pl, self.sw):
            self.world.move_card(h, self.world.players[self.p0].zone(ZONE_HAND))
        slot = self._slot(QConst(2))
        self.assertEqual((slot.min_count, slot.max_count, slot.forced), (1, 1, True))

    def test_qatmost2_slot_range(self):
        slot = self._slot(QAtMost(2))
        self.assertEqual((slot.min_count, slot.max_count, slot.forced), (1, 2, False))

    def test_empty_population_const_feasible_zero(self):
        for h in (self.fo, self.pl, self.sw):
            self.world.move_card(h, self.world.players[self.p0].zone(ZONE_HAND))
        slot = self._slot(QConst(2))
        self.assertEqual((slot.min_count, slot.max_count), (0, 0))

    def test_frozen_zero_population_stays_infeasible_for_want1(self):
        for h in (self.fo, self.pl, self.sw):
            self.world.move_card(h, self.world.players[self.p0].zone(ZONE_HAND))
        slot = self._slot(QConst(1))  # the frozen lane: min 1 > max 0
        self.assertEqual((slot.min_count, slot.max_count), (1, 0))

    def test_rest_of_accepts_a_pick_set(self):
        slot = self._slot(QConst(2))
        rest = rest_of(slot, (self.fo, self.pl))
        self.assertEqual(rest, (self.sw,))
        # the legacy single-Handle call keeps working (frozen callers)
        self.assertEqual(rest_of(slot, self.sw), tuple(sorted([self.fo, self.pl])))


if __name__ == "__main__":
    unittest.main()
