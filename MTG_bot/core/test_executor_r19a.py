"""Round-19a regression tests: the five silent-semantic fixes.

Each test pins the FIXED reading of one r19a root cause and the green
behaviour it had to leave untouched:

1. P/T COUNTERS in the effective-P/T fold (Basri's Solidarity; CR 613.3b
   the counter layer folds AFTER the timestamp-ordered change stack).
2. IS_PERMANENT as the CR 110.1 TYPE-LINE reading, zone-independent
   (Fungal Rebirth's graveyard gate; Unsubstantiate's spell target).
3. DIED_THIS_TURN's existential fallback for a judged handle that could
   never have been the dead creature (player / non-creature spell), while
   creature-typed handles keep the strict per-handle reading (Gadrak).
4. The LIFE-GAINED replacement lane (Life Goes On): ephemeral Eot-tagged
   registration for a resolving instant, event consumption, the CR
   614.4a loop guard, and the EOT sweep.
5. SEARCH DESIGNATE-ONLY under a ONE_OF/REST partition (Cultivate): the
   found cards stay in the zone the partition re-searches; a lone SEARCH
   still delivers (Solemn Simulacrum shape unchanged).
Plus the printed-loyalty field identity_of stopped dropping (Chandra).
"""

import dataclasses
import unittest

from MTG_bot.core.ability_tree import (
    CardRecord,
    ControllerRef,
    FAnd,
    FAtom,
    FAtomPred,
    LifeGainedEvent,
    QConst,
    ReplacementAbility,
    Seq,
    Selector,
    SelectorMode,
    Verb,
    Zone,
    ZoneKind,
)
from MTG_bot.core.executor import Executor
from MTG_bot.core.executor.events import KIND_CREATURE_DIES
from MTG_bot.core.executor.games import identity_of
from MTG_bot.core.executor.quantity import _eval_atom
from MTG_bot.core.state import (
    ZONE_BATTLEFIELD,
    ZONE_GRAVEYARD,
    ZONE_HAND,
    ZONE_LIBRARY,
    GameWorld,
)
from MTG_bot.core.test_executor_binding import (
    BF_YOU,
    LIB_YOU,
    UNIV,
    BF_ANY,
    GY_ANY,
    BindingCase,
    atom,
    card_id,
    enter,
    record_of,
    reset_oracle_ids,
)


def _gain(n: int):
    return atom(Verb.GAIN_LIFE, controller=ControllerRef.YOU, amount=QConst(n))


def _is(pred: FAtomPred):
    return FAtom(pred)


LAND = FAtom(FAtomPred.TYPE_EQ, string_value="Land")


class CounterFoldTest(BindingCase):
    """Fix 1: effective_pt folds P/T counters after the change stack."""

    def setUp(self):
        super().setUp()
        self.vanilla = self.world.add_card(
            card_id("Vanilla", "2", "2"), self.p0, ZONE_BATTLEFIELD
        )
        self.ident = self.world.cards[self.vanilla].identity

    def test_no_counters_argument_is_the_head_fold(self):
        # byte-exact pre-19a behaviour for every caller that passes no map
        self.assertEqual(self.ex.ledger.effective_pt(self.ident, self.vanilla), (2, 2))
        self.ex.ledger.record(self.ident, "delta", self.vanilla, 1, 1, tag="Permanent")
        self.assertEqual(self.ex.ledger.effective_pt(self.ident, self.vanilla), (3, 3))

    def test_counters_fold_on_top_of_the_stack(self):
        self.ex.ledger.record(self.ident, "delta", self.vanilla, 1, 1, tag="Permanent")
        got = self.ex.ledger.effective_pt(
            self.ident, self.vanilla, {"PLUS_1_PLUS_1": 2}
        )
        self.assertEqual(
            got, (5, 5)
        )  # 2 printed + 1 effect + 2 counters - ... -1? no: 2+1+2=5 minus? check below

    def test_plus_minus_net_and_order(self):
        # CR 120.10 family: both kinds coexist until the SBA annihilates.
        got = self.ex.ledger.effective_pt(
            self.ident,
            self.vanilla,
            {"PLUS_1_PLUS_1": 3, "MINUS_1_MINUS_1": 3},
        )
        self.assertEqual(got, (2, 2))  # net zero over the printed 2/2

    def test_set_pt_then_counters(self):
        # CR 613.3b: the counter layer is AFTER the timestamp layers, so it
        # stacks on a SET_PT the way a counter stacks on "becomes a 1/1".
        self.ex.ledger.record(
            self.ident,
            "set",
            self.vanilla,
            power_set=1,
            toughness_set=1,
            tag="Permanent",
        )
        got = self.ex.ledger.effective_pt(
            self.ident, self.vanilla, {"PLUS_1_PLUS_1": 2}
        )
        self.assertEqual(got, (3, 3))

    def test_star_power_stays_undefined(self):
        star = self.world.add_card(card_id("Wild", "*", 1), self.p0, ZONE_BATTLEFIELD)
        ident = self.world.cards[star].identity
        got = self.ex.ledger.effective_pt(ident, star, {"PLUS_1_PLUS_1": 1})
        self.assertEqual(got, (None, 2))  # a counter never materializes '*'

    def test_dies_snapshot_folds_counters(self):
        # events.py: a 2/2 with one +1/+1 counter DIED a 3/3 (C18 row).
        self.world.cards[self.vanilla].counters["PLUS_1_PLUS_1"] = 1
        self.ex.execute(
            enter(GY_ANY),
            source=self.vanilla,
            controller=self.p0,
            bindings={"cards": self.vanilla},
        )
        rows = [
            e
            for e in self.ex.journal.turn_window()
            if e.kind == KIND_CREATURE_DIES and e.subject == self.vanilla
        ]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].data[3:5], (3, 3))


class IsPermanentTest(BindingCase):
    """Fix 2: CR 110.1 — permanent means HAS A PERMANENT TYPE, any zone."""

    def ctx(self):
        return self.ex._ctx(
            source=self.watch, controller=self.p0, bindings={}, decisions=()
        )

    def test_graveyard_creature_is_a_permanent_card(self):
        # Fungal Rebirth's gate: a creature CARD in a graveyard passes.
        self.world.move_to_zone(self.watch, self.p0, ZONE_GRAVEYARD)
        self.assertTrue(_eval_atom(_is(FAtomPred.IS_PERMANENT), self.watch, self.ctx()))

    def test_spell_on_the_stack_is_not(self):
        spell = self.world.add_card(
            card_id("Dispel", type_line="Instant"), self.p0, ZONE_HAND
        )
        self.assertFalse(_eval_atom(_is(FAtomPred.IS_PERMANENT), spell, self.ctx()))

    def test_player_handle_is_not(self):
        self.assertFalse(_eval_atom(_is(FAtomPred.IS_PERMANENT), self.p0, self.ctx()))

    def test_battlefield_agrees_with_the_old_zone_reading(self):
        self.assertTrue(_eval_atom(_is(FAtomPred.IS_PERMANENT), self.watch, self.ctx()))


class DiedThisTurnTest(BindingCase):
    """Fix 3: existential fallback for non-creature judged handles only."""

    def kill_watch(self):
        self.ex.execute(
            enter(GY_ANY),
            source=self.watch,
            controller=self.p0,
            bindings={"cards": self.watch},
        )

    def ctx(self, source=None):
        return self.ex._ctx(
            source=source or self.watch,
            controller=self.p0,
            bindings={},
            decisions=(),
        )

    def test_empty_journal_all_reads_false(self):
        self.assertFalse(_eval_atom(_is(FAtomPred.DIED_THIS_TURN), self.p0, self.ctx()))

    def test_strict_read_for_the_dead_creature_itself(self):
        self.kill_watch()
        self.assertTrue(
            _eval_atom(_is(FAtomPred.DIED_THIS_TURN), self.watch, self.ctx())
        )

    def test_other_creature_still_answers_false(self):
        # Gadrak / Liliana's Standard Bearer census: a creature-typed
        # handle that did not die is NOT "a creature that died".
        # AMENDED 2026-10-01 (round 21b): the strict per-handle reading
        # now ALSO requires the handle to be OFF the battlefield — a
        # battlefield creature can never itself be the dead one, so its
        # gate is the existential reading (Caged Zombie's activation
        # source). The graveyard handle keeps the strict False below.
        other = self.world.add_card(
            card_id("Bystander", "1", "1"), self.p0, ZONE_BATTLEFIELD
        )
        self.kill_watch()
        self.assertTrue(
            _eval_atom(_is(FAtomPred.DIED_THIS_TURN), other, self.ctx(source=other))
        )
        graveyard = self.world.add_card(
            card_id("Grave Bystander", "1", "1"), self.p0, ZONE_GRAVEYARD
        )
        self.assertFalse(
            _eval_atom(
                _is(FAtomPred.DIED_THIS_TURN), graveyard, self.ctx(source=graveyard)
            )
        )

    def test_player_and_spell_read_existentially(self):
        # Life Goes On: the replacement's condition is judged over the
        # gaining PLAYER, and over the resolving instant — neither could
        # ever be the dead creature, so any dies row answers True.
        self.kill_watch()
        self.assertTrue(_eval_atom(_is(FAtomPred.DIED_THIS_TURN), self.p0, self.ctx()))
        instant = self.world.add_card(
            card_id("Go On", type_line="Instant"), self.p0, ZONE_HAND
        )
        self.assertTrue(
            _eval_atom(_is(FAtomPred.DIED_THIS_TURN), instant, self.ctx(source=instant))
        )

    def test_noncreature_permanent_death_is_not_a_creature_death(self):
        # B-56 (2026-10-29, M21 Twinblade Assassins): a sacrificed Treasure
        # is put into a graveyard from the battlefield (it "dies", CR 700.4),
        # and the journal writes its dies row — but "if a creature died
        # this turn" asks for a CREATURE. Neither the existential reading
        # (player, battlefield source) nor the dead artifact's own strict
        # reading may count it; a real creature death afterwards still does.
        treasure = self.world.add_card(
            card_id("Treasure", type_line="Token Artifact — Treasure"),
            self.p0,
            ZONE_BATTLEFIELD,
        )
        self.ex.execute(
            enter(GY_ANY),
            source=treasure,
            controller=self.p0,
            bindings={"cards": treasure},
        )
        died = _is(FAtomPred.DIED_THIS_TURN)
        self.assertTrue(
            any(
                e.kind == KIND_CREATURE_DIES and e.subject == treasure
                for e in self.ex.journal.events
            ),
            "precondition: the Treasure's battlefield-to-graveyard move is journalled",
        )
        self.assertFalse(_eval_atom(died, self.p0, self.ctx()))
        self.assertFalse(_eval_atom(died, self.watch, self.ctx()))
        self.assertFalse(_eval_atom(died, treasure, self.ctx(source=treasure)))
        self.kill_watch()
        self.assertTrue(_eval_atom(died, self.p0, self.ctx()))


class LifeReplacementTest(BindingCase):
    """Fix 4: the life-gained replacement lane (Life Goes On)."""

    def setUp(self):
        super().setUp()
        self.spell = self.world.add_card(
            card_id("Go On", type_line="Instant"), self.p0, ZONE_HAND
        )

    def _spell_record(self, condition=None, gain=8):
        rec = record_of(
            [
                ReplacementAbility(
                    event=LifeGainedEvent(
                        actor=FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU)
                    ),
                    condition=condition,
                    action=_gain(gain),
                )
            ],
            name="Go On",
            oid=self.world.cards[self.spell].identity.oracle_id,
        )
        # a spell, not a creature: the permanent-sourced liveness gate
        # must not apply to the ephemeral half of the idiom.
        return dataclasses.replace(
            rec, type_line="Instant", types=("Instant",), power=None, toughness=None
        )

    def test_gain_replaced_once_and_loop_guarded(self):
        self.ex.replacements.register_ephemeral_replacements(
            self.spell, self.p0, self._spell_record()
        )
        self.ex.execute(_gain(4), source=self.spell, controller=self.p0)
        # consumed -> the ACTION's 8 lands ONCE (CR 614.4a: the action's
        # own gain is not re-replaced by the same record).
        self.assertEqual(self.life(self.p0), 28)

    def test_condition_gated_replacement(self):
        cond = _is(FAtomPred.DIED_THIS_TURN)
        self.ex.replacements.register_ephemeral_replacements(
            self.spell, self.p0, self._spell_record(condition=cond)
        )
        self.ex.execute(_gain(4), source=self.spell, controller=self.p0)
        self.assertEqual(self.life(self.p0), 24)  # nobody died: plain gain
        self.ex.execute(
            enter(GY_ANY),
            source=self.watch,
            controller=self.p0,
            bindings={"cards": self.watch},
        )
        self.ex.execute(_gain(4), source=self.spell, controller=self.p0)
        self.assertEqual(self.life(self.p0), 32)  # 24 + replaced 8

    def test_opponent_gain_is_not_replaced(self):
        # "you" means the replacement's controller, not any player.
        self.ex.replacements.register_ephemeral_replacements(
            self.spell, self.p0, self._spell_record()
        )
        self.ex.execute(
            _gain(4),
            source=self.spell,
            controller=self.p1,
        )
        # judged with controller p1: no record matches, plain gain stands.
        self.assertEqual(self.life(self.p1), 24)

    def test_eot_sweep_expires_ephemerals(self):
        self.ex.replacements.register_ephemeral_replacements(
            self.spell, self.p0, self._spell_record()
        )
        self.ex.replacements.sweep_at_eot()
        self.ex.execute(_gain(4), source=self.spell, controller=self.p0)
        self.assertEqual(self.life(self.p0), 24)  # expired: plain gain


class SearchPartitionTest(unittest.TestCase):
    """Fix 5: SEARCH designates under a ONE_OF/REST partition sibling."""

    def setUp(self):
        reset_oracle_ids()
        self.world = GameWorld(num_players=2, start_life=20, master_seed=11)
        self.p0, self.p1 = self.world.player_order[0], self.world.player_order[1]
        self.fo = self.world.add_card(
            card_id("Forest", type_line="Basic Land"), self.p0, ZONE_LIBRARY
        )
        self.pl = self.world.add_card(
            card_id("Plains", type_line="Basic Land"), self.p0, ZONE_LIBRARY
        )
        self.junk = self.world.add_card(
            card_id("Junk", "1", "1"), self.p0, ZONE_LIBRARY
        )
        self.spell = self.world.add_card(
            card_id("Cultivate", type_line="Instant"), self.p0, ZONE_HAND
        )
        self.ex = Executor(self.world)

    def _cultivate_seq(self):
        return Seq(
            (
                atom(
                    Verb.SEARCH,
                    cards=Selector(
                        QConst(2), SelectorMode.CHOOSE, LAND, zones=(LIB_YOU,)
                    ),
                    destination=BF_YOU,
                    tapped_on_enter=True,
                ),
                atom(
                    Verb.MOVE_ZONE,
                    cards=Selector(
                        QConst(1), SelectorMode.ONE_OF, LAND, zones=(LIB_YOU,)
                    ),
                    destination=BF_YOU,
                    tapped_on_enter=True,
                ),
                atom(
                    Verb.MOVE_ZONE,
                    cards=Selector(
                        QConst(1), SelectorMode.REST, LAND, zones=(LIB_YOU,)
                    ),
                    destination=Zone(ZoneKind.HAND, ControllerRef.YOU),
                ),
                atom(Verb.SHUFFLE, zone=LIB_YOU),
            )
        )

    def test_partition_designates_then_delivers(self):
        self.ex.apply_effect(
            self._cultivate_seq(),
            source=self.spell,
            controller=self.p0,
            decisions=(str(self.fo),),
        )
        # the ONE_OF pick went to the battlefield tapped, the REST to hand,
        # and NOTHING stayed in the library land-wise.
        self.assertEqual(self.world.zone_of(self.fo).kind, ZONE_BATTLEFIELD)
        self.assertTrue(self.world.cards[self.fo].tapped)
        self.assertEqual(self.world.zone_of(self.pl).kind, ZONE_HAND)
        self.assertEqual(self.world.zone_of(self.junk).kind, ZONE_LIBRARY)

    def test_lone_search_still_delivers(self):
        # Solemn Simulacrum shape (no partition siblings): unchanged — the
        # found land lands on the battlefield tapped.
        # R3 (/141 §6, 2026-10-20): the 1-of-N land search is a decision
        # now — script the pick the old silent first-n stand-in made.
        self.ex.decisions.provider = lambda vocab, what: str(self.fo)
        self.ex.apply_effect(
            atom(
                Verb.SEARCH,
                cards=Selector(QConst(1), SelectorMode.CHOOSE, LAND, zones=(LIB_YOU,)),
                destination=BF_YOU,
                tapped_on_enter=True,
            ),
            source=self.spell,
            controller=self.p0,
        )
        self.assertEqual(self.world.zone_of(self.fo).kind, ZONE_BATTLEFIELD)
        self.assertTrue(self.world.cards[self.fo].tapped)


class LoyaltyIdentityTest(unittest.TestCase):
    """Fix 6: identity_of stopped dropping the compiled record's loyalty."""

    def test_loyalty_carries_over(self):
        rec = record_of([], name="Chandra")
        rec = dataclasses.replace(
            rec,
            type_line="Planeswalker — Chandra",
            types=("Planeswalker",),
            power=None,
            toughness=None,
            loyalty=5,
        )
        ident = identity_of(rec)
        self.assertEqual(ident.loyalty, "5")

    def test_non_walkers_stay_none(self):
        rec = record_of([], name="Vanilla")
        self.assertIsNone(identity_of(rec).loyalty)


if __name__ == "__main__":
    unittest.main()
