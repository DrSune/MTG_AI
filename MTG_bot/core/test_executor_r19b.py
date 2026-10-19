"""Round-19b regression tests: the silent-semantics fix batch (wave 2b).

Each test pins the FIXED reading of one r19b root cause and the green
behaviour it had to leave untouched:

1. IS_ATTACHED_TO write-direction + the ALL-mode population exemption in
   role_handles (Turn to Slag: "destroy all Equipment attached to that
   creature" must not be hijacked by the spell's own designation).
2. Discard-cost self-exclusion (Thrill of Possibility / Sparkhunter
   Masticore: CR 601.2h — the cast still in hand never pays with itself).
3. The dies-replacement lane with the designation snapshot (Scorching
   Dragonfire: the Eot window outlives the ExecCtx, but "that creature"
   still means the cast's target; the death is consumed BEFORE the
   graveyard move, the ACTION exiles the referent).
4. CostModifier folding into build_payment_plan (Discontinuity's {2}{U}
   your-turn window, the min-clamp, the no-colour-spill rule) plus the
   three new turn-history preds: TURN_OF, LIFE_GAINED_THIS_TURN_GE,
   INSTANT_OR_SORCERY_CAST_THIS_TURN.
5. END_TURN's self-exile (Discontinuity, CR 716.4a): the extra-turn
   request is the witness that routes the spell's stack->GY move to
   stack->exile.
6/7. The look window (Track Down / See the Truth): LOOK_AT/REVEAL publish
   the shown cards top-first; the Conditional judges the revealed card
   while the window is open; a non-look verb runs with the window OPEN
   and CLOSES it on completion; the library-TOP ONE_OF/REST partition
   resolves over the window (ONE_OF stashing it in one_of_window for its
   sibling REST), and a BOTTOM destination re-orders the pile ascending.
"""

from __future__ import annotations

import unittest

from MTG_bot.core.ability_tree import (
    Conditional,
    ControllerRef,
    Cost,
    CostDeltaReduceGeneric,
    CostDeltaReduceMana,
    CostDiscard,
    CostManaColor,
    CostManaGeneric,
    CostModifier,
    CreatureDiesEvent,
    FAnd,
    FAtom,
    FAtomPred,
    FOr,
    QConst,
    ReplacementAbility,
    Seq,
    Selector,
    SelectorMode,
    SpellKind,
    Verb,
    Zone,
    ZoneKind,
    ZonePosition,
)
from MTG_bot.core.executor.legality import spell_castable
from MTG_bot.core.executor.quantity import eval_filter
from MTG_bot.core.executor.stack import cast
from MTG_bot.core.state import (
    ZONE_BATTLEFIELD,
    ZONE_EXILE,
    ZONE_GRAVEYARD,
    ZONE_HAND,
    ZONE_LIBRARY,
)
from MTG_bot.core.test_executor_binding import (
    BF_ANY,
    BF_YOU,
    HAND_YOU,
    LIB_YOU,
    UNIV,
    BindingCase,
    atom,
    card_id,
    referent_sel,
)

CREATURE_F = FAtom(FAtomPred.TYPE_EQ, string_value="Creature")


def _look(n, who=ControllerRef.YOU):
    return atom(Verb.LOOK_AT, controller=who, count=QConst(n))


def _draw(n=1):
    return atom(Verb.DRAW, controller=ControllerRef.YOU, amount=QConst(n))


def _lib_top():
    return Zone(ZoneKind.LIBRARY, ControllerRef.YOU, ZonePosition.TOP)


def _lib_bottom():
    return Zone(ZoneKind.LIBRARY, ControllerRef.YOU, ZonePosition.BOTTOM)


# --------------------------------------------------------- 6/7 look window


class LookWindowTest(BindingCase):
    """p0's library bottom->top: L1, L2, L3, L4 (L4 top); all creatures."""

    def _land_on_top(self):
        return self.world.add_card(
            card_id("Wastes", type_line="Land"), self.p0, ZONE_LIBRARY
        )

    def test_conditional_judges_the_revealed_card(self):
        # Track Down shape: look at the top, IF IT is a creature draw.
        hand_before = len(self.zone(self.p0, ZONE_HAND))
        self.ex.apply_effect(
            Seq(
                (
                    _look(1),
                    Conditional(CREATURE_F, _draw(1)),
                )
            ),
            source=self.watch,
            controller=self.p0,
        )
        # the top card L4 (a creature) satisfies the pred -> it is drawn
        self.assertEqual(len(self.zone(self.p0, ZONE_HAND)), hand_before + 1)
        self.assertIn(self.libs[3], self.zone(self.p0, ZONE_HAND))

    def test_conditional_rejects_a_non_matching_reveal(self):
        self._land_on_top()
        hand_before = len(self.zone(self.p0, ZONE_HAND))
        self.ex.apply_effect(
            Seq(
                (
                    _look(1),
                    Conditional(CREATURE_F, _draw(1)),
                )
            ),
            source=self.watch,
            controller=self.p0,
        )
        self.assertEqual(len(self.zone(self.p0, ZONE_HAND)), hand_before)

    def test_window_closes_after_a_non_look_verb(self):
        # Leak guard: after the window's ONE sentence, a bare Conditional
        # keeps the ctx.source subject — and the source here is an
        # INSTANT card, so the creature pred is False and nothing draws.
        bolt = self.world.add_card(
            card_id("Bolt", type_line="Instant"), self.p0, ZONE_HAND
        )
        hand_before = len(self.zone(self.p0, ZONE_HAND))
        self.ex.apply_effect(
            Seq(
                (
                    _look(1),
                    atom(
                        Verb.GAIN_LIFE, controller=ControllerRef.YOU, amount=QConst(1)
                    ),
                    Conditional(CREATURE_F, _draw(1)),
                )
            ),
            source=bolt,
            controller=self.p0,
        )
        self.assertEqual(self.life(self.p0), 21)
        self.assertEqual(len(self.zone(self.p0, ZONE_HAND)), hand_before)

    def test_see_the_truth_partition_and_bottom_order(self):
        # Seq[LOOK_AT 3, Seq[MOVE ONE_OF top->hand, MOVE REST top->bottom]]
        # window (top-first): L4, L3, L2. The decision picks L2; the rest
        # (L4, L3) land bottom in the canonical ASCENDING run.
        pick = str(self.libs[1])  # L2 — in-window, neither first nor last
        self.ex.apply_effect(
            Seq(
                (
                    _look(3),
                    Seq(
                        (
                            atom(
                                Verb.MOVE_ZONE,
                                cards=Selector(
                                    QConst(1), SelectorMode.ONE_OF, UNIV, zones=(_lib_top(),)
                                ),
                                destination=HAND_YOU,
                            ),
                            atom(
                                Verb.MOVE_ZONE,
                                cards=Selector(
                                    QConst(1), SelectorMode.REST, UNIV, zones=(_lib_top(),)
                                ),
                                destination=_lib_bottom(),
                            ),
                        )
                    ),
                )
            ),
            source=self.watch,
            controller=self.p0,
            decisions=(pick,),
        )
        self.assertEqual(self.zone(self.p0, ZONE_HAND), [self.libs[1]])
        # entries bottom->top: [L3, L4 (ascending bottom run), L1 (untouched)]
        self.assertEqual(
            self.zone(self.p0, ZONE_LIBRARY),
            [self.libs[2], self.libs[3], self.libs[0]],
        )

    def test_one_of_ask_is_scoped_to_the_window(self):
        # L1 is NOT in the window (top-3 = L4, L3, L2): the flag-not-degrade
        # reading rejects an out-of-vocabulary answer instead of guessing.
        with self.assertRaises(ValueError):
            self.ex.apply_effect(
                Seq(
                    (
                        _look(3),
                        atom(
                            Verb.MOVE_ZONE,
                            cards=Selector(
                                QConst(1), SelectorMode.ONE_OF, UNIV, zones=(_lib_top(),)
                            ),
                            destination=HAND_YOU,
                        ),
                    )
                ),
                source=self.watch,
                controller=self.p0,
                decisions=(str(self.libs[0]),),
            )

    def test_one_of_window_stash_pairs_with_the_pick(self):
        # The REST atom resolves AFTER run_atom closed the raw look window
        # at the ONE_OF's completion — its anchor is ctx.one_of_window.
        # Same-zone split: the pick moves to the library TOP, so it STAYS
        # live and the REST complement can only come from the stashed
        # window with ctx.one_of_picks subtracted.
        self.ex.apply_effect(
            Seq(
                (
                    _look(3),
                    Seq(
                        (
                            atom(
                                Verb.MOVE_ZONE,
                                cards=Selector(
                                    QConst(1), SelectorMode.ONE_OF, UNIV, zones=(_lib_top(),)
                                ),
                                destination=_lib_top(),
                            ),
                            atom(
                                Verb.MOVE_ZONE,
                                cards=Selector(
                                    QConst(1), SelectorMode.REST, UNIV, zones=(_lib_top(),)
                                ),
                                destination=_lib_bottom(),
                            ),
                        )
                    ),
                )
            ),
            source=self.watch,
            controller=self.p0,
            decisions=(str(self.libs[1]),),  # pick L2
        )
        # REST = stash {L4, L3, L2} minus the pick = {L4, L3} → bottom run
        # ascending; entries bottom->top: [L3, L4, L1, L2 (the top pick)]
        self.assertEqual(
            self.zone(self.p0, ZONE_LIBRARY),
            [self.libs[2], self.libs[3], self.libs[0], self.libs[1]],
        )


# ------------------------------------------------- 1 attached-to anaphora


class AttachedAnaphoraTest(BindingCase):
    """Fix 1: IS_ATTACHED_TO's write direction + the population exemption."""

    def setUp(self):
        super().setUp()
        self.prey = self.world.add_card(
            card_id("Prey", "2", "2"), self.p0, ZONE_BATTLEFIELD
        )
        self.saw = self.world.add_card(
            card_id("Bone Saw", "1", "1", "Equipment"), self.p0, ZONE_BATTLEFIELD
        )
        self.ex.attach_aura(self.saw, self.prey)
        self.spell = self.world.add_card(
            card_id("Slag", type_line="Instant"), self.p0, ZONE_HAND
        )

    def _ctx(self, **bindings):
        return self.ex._ctx(
            source=self.spell, controller=self.p0, bindings=dict(bindings), decisions=()
        )

    def test_is_attached_to_judges_the_attachment_not_the_host(self):
        pred = FAtom(FAtomPred.IS_ATTACHED_TO, referent="target")
        ctx = self._ctx(target=[self.prey])
        self.assertTrue(eval_filter(pred, self.saw, ctx))  # table[saw] == prey
        self.assertFalse(eval_filter(pred, self.prey, ctx))  # write direction

    def test_ambiguous_target_binding_raises(self):
        pred = FAtom(FAtomPred.IS_ATTACHED_TO, referent="target")
        with self.assertRaises(ValueError):
            eval_filter(pred, self.saw, self._ctx(target=[self.prey, self.saw]))

    def test_destroy_population_is_not_binding_first(self):
        # Turn to Slag's DESTROY shape: an ALL BATTLEFIELD selector whose
        # filter carries the "attached to target" anaphora denotes its own
        # population — the designation must not hijack it.
        self.ex.execute(
            atom(
                Verb.DESTROY,
                target=Selector(
                    QConst(1),
                    SelectorMode.ALL,
                    FAtom(FAtomPred.IS_ATTACHED_TO, referent="target"),
                    zones=(BF_ANY,),
                ),
            ),
            source=self.spell,
            controller=self.p0,
            bindings={"target": [self.prey]},
        )
        self.assertEqual(self.world.zone_of(self.prey).kind, ZONE_BATTLEFIELD)
        self.assertEqual(self.world.zone_of(self.saw).kind, ZONE_GRAVEYARD)


# ------------------------------------------------------ 2 discard self-lock


class DiscardCostTest(unittest.TestCase):
    """Fix 2: CR 601.2h — the cast in hand never pays its own discard."""

    def setUp(self):
        from MTG_bot.core.test_executor_binding import reset_oracle_ids

        reset_oracle_ids()
        from MTG_bot.core.state import GameWorld
        from MTG_bot.core.executor import Executor

        self.world = GameWorld(num_players=2, start_life=20, master_seed=7)
        self.p0, self.p1 = self.world.player_order[0], self.world.player_order[1]
        self.ex = Executor(self.world)
        self.ex.begin_turn(self.p0)

    def _thrill(self, name="Thrill"):
        from MTG_bot.core.test_executor_stack import spell_rec
        from MTG_bot.core.identity import CardIdentity

        rec = spell_rec(
            name,
            SpellKind.INSTANT,
            cost=Cost(
                (CostDiscard(Selector(QConst(1), SelectorMode.ALL, UNIV, zones=(HAND_YOU,))),)
            ),
            effect=atom(Verb.DRAW, controller=ControllerRef.YOU, amount=QConst(2)),
        )
        handle = self.world.add_card(
            CardIdentity(
                oracle_id=rec.oracle_id, name=name, type_line="Instant", cmc=2
            ),
            self.p0,
            ZONE_HAND,
        )
        self.ex.attach_card(handle, rec)
        return handle

    def test_discard_cost_spends_another_card(self):
        thrill = self._thrill()
        fodder = self.world.add_card(card_id("Fodder"), self.p0, ZONE_HAND)
        # two library cards so the resolution's DRAW 2 has real targets
        for i in (1, 2):
            self.world.add_card(card_id(f"D{i}"), self.p0, ZONE_LIBRARY)
        cast(self.ex, self.p0, thrill)
        self.assertEqual(self.world.zone_of(fodder).kind, ZONE_GRAVEYARD)
        # the spell resolved and drew 2 — it is NOT the discarded card
        self.assertEqual(self.world.zone_of(thrill).kind, ZONE_GRAVEYARD)
        self.assertEqual(len(self.zone(self.p0, ZONE_HAND)), 2)

    def test_only_the_spell_in_hand_is_not_legal(self):
        thrill = self._thrill()
        reason, *_ = spell_castable(self.ex, self.p0, thrill)
        self.assertIsNotNone(reason)
        self.assertIn("discard", str(reason))

    def zone(self, player, kind):
        return self.world.players[player].zone(kind).entries


# ------------------------------------------------- 4 cost-modifier folding


class CostModifierFoldTest(unittest.TestCase):
    """Fix 4: the CR 601.2f fold + the TURN_OF / history preds."""

    def setUp(self):
        from MTG_bot.core.test_executor_binding import reset_oracle_ids

        reset_oracle_ids()
        from MTG_bot.core.state import GameWorld
        from MTG_bot.core.executor import Executor

        self.world = GameWorld(num_players=2, start_life=20, master_seed=7)
        self.p0, self.p1 = self.world.player_order[0], self.world.player_order[1]
        self.ex = Executor(self.world)
        self.ex.begin_turn(self.p0)

    def mana(self, seat, **keys):
        pool = self.world.players[seat].mana_pool
        for key, amount in keys.items():
            pool[key] = pool.get(key, 0) + amount

    def _spell(self, name, cost, kind=SpellKind.INSTANT):
        from MTG_bot.core.test_executor_stack import spell_rec
        from MTG_bot.core.identity import CardIdentity

        rec = spell_rec(
            name,
            kind,
            cost=cost,
            effect=atom(Verb.GAIN_LIFE, controller=ControllerRef.YOU, amount=QConst(1)),
            type_line="Sorcery" if kind is SpellKind.SORCERY else "Instant",
            types=("Sorcery",) if kind is SpellKind.SORCERY else ("Instant",),
        )
        handle = self.world.add_card(
            CardIdentity(
                oracle_id=rec.oracle_id,
                name=name,
                type_line=rec.type_line,
                cmc=4,
            ),
            self.p0,
            ZONE_HAND,
        )
        self.ex.attach_card(handle, rec)
        return handle

    def _watcher(self, modifier):
        from MTG_bot.core.test_executor_stack import spell_rec
        from MTG_bot.core.identity import CardIdentity

        rec = spell_rec(
            "Watcher",
            SpellKind.CREATURE,
            type_line="Creature",
            types=("Creature",),
            power="2",
            toughness="2",
            extra_abilities=(modifier,),
        )
        handle = self.world.add_card(
            CardIdentity(
                oracle_id=rec.oracle_id,
                name="Watcher",
                type_line="Creature",
                power="2",
                toughness="2",
                cmc=4,
            ),
            self.p0,
            ZONE_BATTLEFIELD,
        )
        self.ex.attach_card(handle, rec)
        return handle

    def test_turn_window_discount_and_history_preds(self):
        # Discontinuity shape: {3}{U}, costs {2}{U} less during YOUR turn.
        mod = CostModifier(
            filter=UNIV,
            controller_ref=ControllerRef.YOU,
            delta=CostDeltaReduceGeneric(QConst(2)),
            condition=FAtom(FAtomPred.TURN_OF, who=ControllerRef.YOU),
            extra_deltas=(CostDeltaReduceMana("U", QConst(1)),),
        )
        self._watcher(mod)
        spell = self._spell(
            "Discont", Cost((CostManaGeneric(QConst(3)), CostManaColor("U", QConst(1))))
        )
        self.mana(self.p0, G=1, U=1)
        cast(self.ex, self.p0, spell)  # folded cost: 1 generic + 0 blue
        self.assertEqual(self.world.players[self.p0].life, 21)
        self.assertEqual(self.world.zone_of(spell).kind, ZONE_GRAVEYARD)
        # pred witnesses on the same journal
        ctx = self.ex._ctx(source=spell, controller=self.p0, bindings={}, decisions=())
        turn_of_you = FAtom(FAtomPred.TURN_OF, who=ControllerRef.YOU)
        self.assertTrue(eval_filter(turn_of_you, spell, ctx))  # still p0's turn
        self.ex.begin_turn(self.p1)
        self.assertFalse(eval_filter(turn_of_you, spell, ctx))
        # off-turn now: the fold is gone — the FULL {3}{U} bill applies
        spell2 = self._spell(
            "Discont2",
            Cost((CostManaGeneric(QConst(3)), CostManaColor("U", QConst(1)))),
        )
        self.mana(self.p0, G=1, U=1)
        reason, *_ = spell_castable(self.ex, self.p0, spell2)
        self.assertIsNotNone(reason)
        self.mana(self.p0, G=2)
        ok, *_ = spell_castable(self.ex, self.p0, spell2)
        self.assertIsNone(ok)

    def test_discount_clamps_and_never_spills_colour(self):
        # {1}{R} with a {2}{U} unconditional discount: the generic floor
        # clamps at zero (no credit) and the blue cut cannot pay RED.
        mod = CostModifier(
            filter=UNIV,
            controller_ref=ControllerRef.YOU,
            delta=CostDeltaReduceGeneric(QConst(2)),
            extra_deltas=(CostDeltaReduceMana("U", QConst(1)),),
        )
        self._watcher(mod)
        spell = self._spell(
            "Spike", Cost((CostManaGeneric(QConst(1)), CostManaColor("R", QConst(1))))
        )
        self.mana(self.p0, R=1, U=2, G=1)
        cast(self.ex, self.p0, spell)
        pool = self.world.players[self.p0].mana_pool
        self.assertEqual(pool.get("R", 0), 0)  # red was the ONLY real bill
        self.assertEqual(pool.get("U", 0), 2)  # the blue cut stayed unused
        self.assertEqual(pool.get("G", 0), 1)  # the clamp left it whole

    def test_history_preds_family(self):
        # LIFE_GAINED_THIS_TURN_GE is a SUM, not a row count.
        sp = self.world.add_card(
            card_id("Probe", type_line="Instant"), self.p0, ZONE_HAND
        )
        gain1 = atom(Verb.GAIN_LIFE, controller=ControllerRef.YOU, amount=QConst(2))
        self.ex.execute(gain1, source=sp, controller=self.p0)
        self.ex.execute(gain1, source=sp, controller=self.p0)
        ctx = self.ex._ctx(source=sp, controller=self.p0, bindings={}, decisions=())
        self.assertTrue(
            eval_filter(
                FAtom(
                    FAtomPred.LIFE_GAINED_THIS_TURN_GE,
                    count=QConst(3),
                    who=ControllerRef.YOU,
                ),
                sp,
                ctx,
            )
        )  # 2 + 2 >= 3
        self.assertFalse(
            eval_filter(
                FAtom(
                    FAtomPred.LIFE_GAINED_THIS_TURN_GE,
                    count=QConst(5),
                    who=ControllerRef.YOU,
                ),
                sp,
                ctx,
            )
        )
        # INSTANT_OR_SORCERY_CAST_THIS_TURN rides the 13b CAST feed.
        fam = FAtom(FAtomPred.INSTANT_OR_SORCERY_CAST_THIS_TURN, who=ControllerRef.YOU)
        self.assertFalse(eval_filter(fam, sp, ctx))
        shock = self._spell("Shock", Cost((CostManaColor("R", QConst(1)),)))
        self.mana(self.p0, R=1)
        cast(self.ex, self.p0, shock)
        self.assertTrue(eval_filter(fam, shock, ctx))
        opp = FAtom(
            FAtomPred.INSTANT_OR_SORCERY_CAST_THIS_TURN, who=ControllerRef.OPPONENT
        )
        self.assertFalse(eval_filter(opp, shock, ctx))


# ------------------------------------------------------ 5 END_TURN exile


class EndTurnExileTest(unittest.TestCase):
    """Fix 5: the extra-turn request re-routes the spell's own put."""

    def setUp(self):
        from MTG_bot.core.test_executor_binding import reset_oracle_ids

        reset_oracle_ids()
        from MTG_bot.core.state import GameWorld
        from MTG_bot.core.executor import Executor

        self.world = GameWorld(num_players=2, start_life=20, master_seed=7)
        self.p0, self.p1 = self.world.player_order[0], self.world.player_order[1]
        self.ex = Executor(self.world)
        self.ex.begin_turn(self.p0)

    def mana(self, seat, **keys):
        pool = self.world.players[seat].mana_pool
        for key, amount in keys.items():
            pool[key] = pool.get(key, 0) + amount

    def _sorcery(self, name, effect):
        from MTG_bot.core.test_executor_stack import spell_rec
        from MTG_bot.core.identity import CardIdentity

        rec = spell_rec(
            name,
            SpellKind.SORCERY,
            cost=Cost((CostManaGeneric(QConst(1)), CostManaColor("U", QConst(1)))),
            effect=effect,
            type_line="Sorcery",
            types=("Sorcery",),
        )
        handle = self.world.add_card(
            CardIdentity(
                oracle_id=rec.oracle_id, name=name, type_line="Sorcery", cmc=2
            ),
            self.p0,
            ZONE_HAND,
        )
        self.ex.attach_card(handle, rec)
        return handle

    def test_end_turn_spell_exiles_itself(self):
        disc = self._sorcery("Discontinuity", atom(Verb.END_TURN))
        self.mana(self.p0, G=1, U=1)
        cast(self.ex, self.p0, disc)
        self.assertEqual(self.world.zone_of(disc).kind, ZONE_EXILE)
        self.assertFalse(self.ex.end_turn_requested)  # consumed by the op
        puts = [e for e in self.ex.events if e[1] == "SPELL_PUT"]
        self.assertIn("stack->exile", str(puts[-1][3]))

    def test_ordinary_sorcery_still_graveyards(self):
        plain = self._sorcery(
            "Gain", atom(Verb.GAIN_LIFE, controller=ControllerRef.YOU, amount=QConst(1))
        )
        self.mana(self.p0, G=1, U=1)
        cast(self.ex, self.p0, plain)
        self.assertEqual(self.world.zone_of(plain).kind, ZONE_GRAVEYARD)


# ------------------------------------------------- 3 dies-replacement lane


class DeathReplacementTest(unittest.TestCase):
    """Fix 3: Scorching Dragonfire's designation-scoped dies window."""

    def setUp(self):
        from MTG_bot.core.test_executor_binding import reset_oracle_ids

        reset_oracle_ids()
        from MTG_bot.core.state import GameWorld
        from MTG_bot.core.executor import Executor

        self.world = GameWorld(num_players=2, start_life=20, master_seed=7)
        self.p0, self.p1 = self.world.player_order[0], self.world.player_order[1]
        self.ex = Executor(self.world)
        self.ex.begin_turn(self.p0)

    def _scorch(self):
        from MTG_bot.core.test_executor_stack import spell_rec, any_target
        from MTG_bot.core.identity import CardIdentity

        rec = spell_rec(
            "Scorch",
            SpellKind.INSTANT,
            cost=Cost((CostManaColor("R", QConst(1)),)),
            effect=atom(Verb.DEAL_DAMAGE, target=any_target(), amount=QConst(3)),
            extra_abilities=(
                ReplacementAbility(
                    event=CreatureDiesEvent(FAtom(FAtomPred.IS_ANY_TARGET)),
                    condition=None,
                    action=atom(
                        Verb.MOVE_ZONE,
                        cards=referent_sel("event"),
                        destination=Zone(ZoneKind.EXILE, ControllerRef.YOU),
                    ),
                ),
            ),
        )
        handle = self.world.add_card(
            CardIdentity(
                oracle_id=rec.oracle_id, name="Scorch", type_line="Instant", cmc=1
            ),
            self.p0,
            ZONE_HAND,
        )
        self.ex.attach_card(handle, rec)
        return handle

    def test_targeted_death_is_exiled_not_graveyarded(self):
        scorch = self._scorch()
        victim = self.world.add_card(
            card_id("Victim", "2", "2"), self.p1, ZONE_BATTLEFIELD
        )
        self.world.players[self.p0].mana_pool["R"] = 1
        cast(self.ex, self.p0, scorch, targets=(victim,))
        self.assertEqual(self.world.zone_of(victim).kind, ZONE_EXILE)
        self.assertEqual(self.world.zone_of(scorch).kind, ZONE_GRAVEYARD)
        # the consumed death emits no CREATURE_DIES row (documented v1
        # stand-in) — but the loud STATE_CHECK witness IS journalled
        kinds = {e[1] for e in self.ex.events}
        self.assertNotIn("CREATURE_DIES", kinds)
        self.assertTrue(
            any(
                e[1] == "STATE_CHECK" and e[3] == "DIES_REPLACED"
                for e in self.ex.events
            )
        )

    def test_unrelated_death_keeps_the_graveyard(self):
        scorch = self._scorch()
        victim = self.world.add_card(
            card_id("Victim", "2", "2"), self.p1, ZONE_BATTLEFIELD
        )
        bystander = self.world.add_card(
            card_id("Bystander", "2", "2"), self.p1, ZONE_BATTLEFIELD
        )
        self.world.players[self.p0].mana_pool["R"] = 1
        cast(self.ex, self.p0, scorch, targets=(victim,))
        self.assertEqual(self.world.zone_of(victim).kind, ZONE_EXILE)
        # the bystander dies to pre-marked damage WITHOUT being designated:
        # the window's IS_ANY_TARGET must not claim it (CR 614.1 scoping)
        self.ex.damage[bystander] = 3
        self.ex.execute(
            atom(Verb.GAIN_LIFE, controller=ControllerRef.YOU, amount=QConst(1)),
            source=scorch,
            controller=self.p0,
        )
        self.assertEqual(self.world.zone_of(bystander).kind, ZONE_GRAVEYARD)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
