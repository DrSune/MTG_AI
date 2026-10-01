"""Round-22a pins: the own-dies trigger binding law + the sacrifice-cost
vocabulary law (KNOWLEDGE/2026-10-01 /21+/22 wave5a findings, fix A/B).

Scope A (binding.py): the journal records a death as a ZONE_CHANGE row
immediately followed by the CREATURE_DIES row (events.record_atom). The
binder used to drop the leaver's bindings on the ZONE_CHANGE row, so the
DEAD permanent's OWN "when ~ dies" trigger never matched. The fix defers
the detach across the adjacent pair (lookahead + CREATURE_DIES landing +
end-of-pass flush) — and the fire-time pre-bind of ``target =
event.subject`` is now gated: a trigger effect that carries its OWN
TARGET-mode designation selector must not be narrowed by the pre-bind
(CR 601.2a: the designation is chosen when the ability goes on the
stack, and it asks).

Scope B (legality.py): who a SACRIFICE cost kills is the controller's
decision — build_payment_plan records the FULL candidate pool per
segment (never asks), pay_costs re-opens the choice through the 14b
vocabulary channel when the segment really offers one, and CR 701.14a
keeps the opponent's permanents out of the pool entirely.
"""

import unittest

from MTG_bot.core.ability_tree import (
    ControllerRef,
    CostSacrifice,
    CreatureDiesEvent,
    QAgg,
    QConst,
    QProp,
    QPropField,
    Selector,
    SelectorMode,
    Verb,
)
from MTG_bot.core.executor import Executor
from MTG_bot.core.executor.legality import (
    build_payment_plan,
    ctx_for,
    pay_costs,
)
from MTG_bot.core.state import (
    ZONE_BATTLEFIELD,
    ZONE_GRAVEYARD,
    GameWorld,
)
from MTG_bot.core.test_executor_binding import (
    ANOTHER_CREATURE,
    BF_ANY,
    BF_YOU,
    CREATURE,
    IS_SOURCE,
    UNIV,
    atom,
    card_id,
    reset_oracle_ids,
)
from MTG_bot.core.test_executor_legality import cost


class SacrificeVocabulary(unittest.TestCase):
    """r22a-B: p0 carries Alpha (the activation's source) plus Gamma and
    Delta; p1 carries Beta. 'Sacrifice a creature' can only ever touch
    Gamma/Delta — and WHICH one dies is a decision, not Handle order."""

    def setUp(self):
        reset_oracle_ids()
        self.world = GameWorld(num_players=2, start_life=20, master_seed=17)
        self.p0, self.p1 = self.world.player_order[0], self.world.player_order[1]
        self.alpha = self.world.add_card(
            card_id("Alpha", "2", "2"), self.p0, ZONE_BATTLEFIELD
        )
        self.gamma = self.world.add_card(
            card_id("Gamma", "1", "1"), self.p0, ZONE_BATTLEFIELD
        )
        self.delta = self.world.add_card(
            card_id("Delta", "1", "1"), self.p0, ZONE_BATTLEFIELD
        )
        self.beta = self.world.add_card(
            card_id("Beta", "1", "1"), self.p1, ZONE_BATTLEFIELD
        )
        self.ex = Executor(self.world)

    def plan_for(self, sel: Selector):
        ctx = ctx_for(self.ex, source=self.alpha, controller=self.p0)
        plan, reason = build_payment_plan(self.world, ctx, cost(CostSacrifice(sel)))
        assert plan is not None, reason
        return plan

    def recorder(self, answer=None):
        asks: list[tuple[str, tuple[str, ...]]] = []

        def prov(vocab, what):
            asks.append((what, tuple(vocab)))
            if answer is None:
                return vocab[0]
            return answer if answer in vocab else vocab[0]

        self.ex.decisions.provider = prov
        return asks

    def test_choice_segment_asks_and_the_answer_is_the_victim(self):
        plan = self.plan_for(
            Selector(QConst(1), SelectorMode.CHOOSE, ANOTHER_CREATURE, BF_YOU)
        )
        # The witness still carries the canonical lowest pick (a probe
        # never asks), and the FULL pool rides on the plan.
        self.assertEqual(plan.sacrifice, (min(self.gamma, self.delta),))
        self.assertEqual(
            plan.sacrifice_options, ((tuple(sorted((self.gamma, self.delta))), 1),)
        )
        asks = self.recorder(answer=str(self.delta))
        pay_costs(self.ex, plan, source=self.alpha, controller=self.p0)
        self.assertEqual(len(asks), 1)
        site, vocab = asks[0]
        self.assertTrue(site.startswith(f"sacrifice:{self.p0}:{self.alpha}"), site)
        self.assertEqual(vocab, tuple(str(h) for h in sorted((self.gamma, self.delta))))
        self.assertEqual(
            self.world.zone_of(self.delta).kind, ZONE_GRAVEYARD
        )  # the ANSWERED victim
        self.assertEqual(self.world.zone_of(self.gamma).kind, ZONE_BATTLEFIELD)
        self.assertEqual(self.world.zone_of(self.alpha).kind, ZONE_BATTLEFIELD)

    def test_forced_segment_stays_silent_and_byte_identical(self):
        # One candidate (Gamma): len(pool) == need -> §1.4 forced
        # auto-fill, NO ask, no provider needed at all.
        self.world.move_to_zone(self.delta, self.p0, ZONE_GRAVEYARD)
        plan = self.plan_for(
            Selector(QConst(1), SelectorMode.CHOOSE, ANOTHER_CREATURE, BF_YOU)
        )
        pay_costs(self.ex, plan, source=self.alpha, controller=self.p0)
        self.assertEqual(self.world.zone_of(self.gamma).kind, ZONE_GRAVEYARD)

    def test_self_sacrifice_never_asks(self):
        sel = Selector(QConst(1), SelectorMode.CHOOSE, IS_SOURCE, BF_YOU)
        plan = self.plan_for(sel)
        self.assertEqual(plan.sacrifice_options, (((self.alpha,), 1),))
        pay_costs(self.ex, plan, source=self.alpha, controller=self.p0)
        self.assertEqual(self.world.zone_of(self.alpha).kind, ZONE_GRAVEYARD)

    def test_pool_carries_only_permanents_you_control(self):
        # CR 701.14a — the bridge shape for "sacrifice another creature"
        # is a controller=ANY battlefield zone filtered only by
        # Creature AND NOT is-source; the opponent's Beta must not ride
        # the plan pool NOR the ask vocabulary.
        plan = self.plan_for(
            Selector(QConst(1), SelectorMode.TARGET, ANOTHER_CREATURE, BF_ANY)
        )
        pool, _need = plan.sacrifice_options[0]
        self.assertEqual(pool, tuple(sorted((self.gamma, self.delta))))
        self.assertNotIn(self.beta, pool)
        asks = self.recorder()
        pay_costs(self.ex, plan, source=self.alpha, controller=self.p0)
        self.assertNotIn(str(self.beta), asks[0][1])

    def test_unanswered_choice_raises_never_a_silent_pick(self):
        # C15: with no lane able to answer, the ask RAISES — the frozen
        # lowest-Handle auto-pick is dead.
        plan = self.plan_for(
            Selector(QConst(1), SelectorMode.CHOOSE, ANOTHER_CREATURE, BF_YOU)
        )
        with self.assertRaises(ValueError) as cm:
            pay_costs(self.ex, plan, source=self.alpha, controller=self.p0)
        self.assertIn("sacrifice:", str(cm.exception))

    def test_hand_built_plan_pays_the_frozen_path(self):
        # A pre-r22a plan (default empty options) pays its witness list
        # exactly as before, with no provider attached.
        from MTG_bot.core.executor.legality import PaymentPlan

        plan = PaymentPlan(sacrifice=(self.gamma,))
        pay_costs(self.ex, plan, source=self.alpha, controller=self.p0)
        self.assertEqual(self.world.zone_of(self.gamma).kind, ZONE_GRAVEYARD)
        self.assertEqual(self.world.zone_of(self.delta).kind, ZONE_BATTLEFIELD)


class OwnDiesTrigger(unittest.TestCase):
    """r22a-A: the leaver's OWN dies trigger must resolve — the binder
    defers the detach across the adjacent ZONE_CHANGE / CREATURE_DIES
    pair instead of dropping bindings on the leave row."""

    def setUp(self):
        reset_oracle_ids()
        self.world = GameWorld(num_players=2, start_life=20, master_seed=19)
        self.p0, self.p1 = self.world.player_order[0], self.world.player_order[1]
        self.beater = self.world.add_card(
            card_id("Beater", "5", "5"), self.p0, ZONE_BATTLEFIELD
        )
        self.watcher = self.world.add_card(
            card_id("Watcher", "1", "1"), self.p0, ZONE_BATTLEFIELD
        )
        self.ex = Executor(self.world)

    def record_for(self, handle, abilities):
        from MTG_bot.core.test_executor_binding import record_of

        return record_of(abilities, oid=self.world.cards[handle].identity.oracle_id)

    def kill(self, victim):
        self.ex.execute(
            atom(
                Verb.DESTROY, target=Selector(QConst(1), SelectorMode.ALL, UNIV, BF_ANY)
            ),
            source=self.beater,
            controller=self.p0,
            bindings={"target": victim},
        )

    def test_own_dies_trigger_resolves_after_the_leave_row(self):
        from MTG_bot.core.ability_tree import TriggeredAbility

        self.ex.attach_card(
            self.watcher,
            self.record_for(
                self.watcher,
                [
                    TriggeredAbility(
                        CreatureDiesEvent(filter=IS_SOURCE),
                        None,
                        atom(
                            Verb.GAIN_LIFE,
                            controller=ControllerRef.YOU,
                            amount=QConst(3),
                        ),
                    )
                ],
            ),
        )
        self.kill(self.watcher)
        self.assertEqual(self.world.players[self.p0].life, 23)  # the OWN trigger fired
        self.assertEqual(self.world.zone_of(self.watcher).kind, ZONE_GRAVEYARD)
        # ...and the deferred detach STILL lands: no live bindings survive
        # the pass for a permanent that left.
        self.assertFalse(
            [key for key in self.ex.binder.attached if key[0] == self.watcher]
        )

    def test_survivor_dies_trigger_still_fires(self):
        # Regression twin: a SURVIVING carrier's "whenever a creature
        # dies" binding is untouched by the deferral.
        from MTG_bot.core.ability_tree import TriggeredAbility

        self.ex.attach_card(
            self.beater,
            self.record_for(
                self.beater,
                [
                    TriggeredAbility(
                        CreatureDiesEvent(filter=UNIV),
                        None,
                        atom(
                            Verb.GAIN_LIFE,
                            controller=ControllerRef.YOU,
                            amount=QConst(1),
                        ),
                    )
                ],
            ),
        )
        self.kill(self.watcher)
        self.assertEqual(self.world.players[self.p0].life, 21)


class DesignationPrebindGate(unittest.TestCase):
    """r22a-A2: the fire-time ``target = event.subject`` pre-bind is a
    convenience for referent-shaped trigger effects; a trigger carrying
    its OWN TARGET-mode designation (Goblin Arsonist's "any target")
    must still ASK — pre-binding it would silently narrow the choice to
    the dead creature itself."""

    def setUp(self):
        reset_oracle_ids()
        self.world = GameWorld(num_players=2, start_life=20, master_seed=23)
        self.p0, self.p1 = self.world.player_order[0], self.world.player_order[1]
        self.beater = self.world.add_card(
            card_id("Beater", "5", "5"), self.p0, ZONE_BATTLEFIELD
        )
        self.victim = self.world.add_card(
            card_id("Victim", "1", "1"), self.p0, ZONE_BATTLEFIELD
        )
        self.ex = Executor(self.world)

    def record_for(self, handle, abilities):
        from MTG_bot.core.test_executor_binding import record_of

        return record_of(abilities, oid=self.world.cards[handle].identity.oracle_id)

    def test_target_shaped_dies_trigger_asks(self):
        from MTG_bot.core.ability_tree import TriggeredAbility

        # TWO survivors on the field after the dies: with a single candi-
        # date the designation is FORCED (§1.4 auto-fill, no decision to
        # ask — C15), which would silently skip the very channel this test
        # pins. A second creature makes the TARGET slot a real choice.
        self.world.add_card(card_id("Stalwart", "2", "2"), self.p0, ZONE_BATTLEFIELD)
        self.ex.attach_card(
            self.victim,
            self.record_for(
                self.victim,
                [
                    TriggeredAbility(
                        CreatureDiesEvent(filter=IS_SOURCE),
                        None,
                        atom(
                            Verb.DEAL_DAMAGE,
                            target=Selector(
                                QConst(1), SelectorMode.TARGET, CREATURE, BF_ANY
                            ),
                            amount=QConst(3),
                        ),
                    )
                ],
            ),
        )
        asks: list[tuple[str, tuple[str, ...]]] = []

        def prov(vocab, what):
            asks.append((what, tuple(vocab)))
            return str(self.beater)

        self.ex.decisions.provider = prov
        self.ex.execute(
            atom(
                Verb.DESTROY,
                target=Selector(QConst(1), SelectorMode.ALL, UNIV, BF_ANY),
            ),
            source=self.beater,
            controller=self.p0,
            bindings={"target": self.victim},
        )
        self.assertTrue(asks and asks[0][0].startswith("target:"), asks)
        self.assertNotIn(str(self.victim), asks[0][1])  # it is already dead
        self.assertEqual(self.ex.damage.get(self.beater, 0), 3)

    def test_referent_shaped_dies_trigger_never_asks(self):
        # The Conclave/Deathbloom shape (referent="event" readers) keeps
        # the silent pre-bind path: NO provider is attached, so any ask
        # would raise out of take_decision.
        from MTG_bot.core.ability_tree import TriggeredAbility

        self.ex.attach_card(
            self.victim,
            self.record_for(
                self.victim,
                [
                    TriggeredAbility(
                        CreatureDiesEvent(filter=IS_SOURCE),
                        None,
                        atom(
                            Verb.GAIN_LIFE,
                            controller=ControllerRef.YOU,
                            amount=QProp(
                                referent="event", field=QPropField.POWER, agg=QAgg.FIRST
                            ),
                        ),
                    )
                ],
            ),
        )
        self.ex.execute(
            atom(
                Verb.DESTROY,
                target=Selector(QConst(1), SelectorMode.ALL, UNIV, BF_ANY),
            ),
            source=self.beater,
            controller=self.p0,
            bindings={"target": self.victim},
        )
        self.assertEqual(self.world.players[self.p0].life, 21)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
