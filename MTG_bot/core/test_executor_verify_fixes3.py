"""M21 verification campaign, engine fixer 3 (2026-10-29): one test class per finding.

V31  A planeswalker brought to exactly 0 loyalty is put into its owner's graveyard
     (CR 704.5i) on every path: counter removal, a loyalty cost, damage. Its loyalty
     counters cease to exist when it leaves the battlefield (CR 122.2), so a re-entry
     starts from the printed loyalty (CR 306.5b).
V31b Counters on an object cease to exist when it moves to another zone (CR 122.2).
V24  Ownership never changes (CR 108.3): a moving card lands in its owner's hand,
     library, graveyard or exile whatever player the destination names (CR 400.3),
     and a permanent put onto the battlefield under another player's control is a
     control entry on the owner's zone (CR 110.2a).
V23  Only a draw is a draw (CR 121.1, 121.5): a library-to-hand move by any other verb
     is a zone change, not CARD_DRAWN. An atom boundary opened inside another (a CAST
     atom resolving a spell, a cost paid through journalled verbs) journals each change
     once: the enclosing boundary no longer re-emits it.
V33  "Discard your hand" as a cost discards every card in hand, and an empty hand pays
     it (CR 118.3, 701.9a).
V36  A spell cast by an effect pays its own additional costs on top of the mana cost or
     the effect's alternative cost (CR 601.2f, 118.9d); an unpayable total refuses.
V35  A token in a zone other than the battlefield ceases to exist (CR 704.5d, 111.7),
     after its leave triggers have fired.
V29  A cost increase for spells that target a permanent is folded with the declared
     targets (CR 601.2f), and a target whose total the caster cannot pay is not offered.
     End to end in the terror_* and pursued_whale_* packs.
V25  A target nested in a quantity ("deals damage equal to its power", where "its" is
     a target) gets its own slot, and each TARGET selector reads its own designation:
     Garruk, Savage Herald's -2 (packs garruk_herald_minus_two_*).
V34  An ability whose only trace of its target is IS_ANY_TARGET in a combat slot gets a
     target slot (Subira's {1}), and the targeting restriction is checked at resolution
     and not re-read afterwards (CR 608.2b; pack subira_unblockable_lasts_after_pump).
V28  A CHOOSE selector is never handed a TARGET designation it could not select
     (Rewind's "untap up to four lands" was handed the countered spell; CR 608.2c).
V30  A trigger whose effect moves its own card out of the graveyard functions only in
     the graveyard (CR 113.6m): Silversmote Ghoul's end-step return.
CAST cost role (coordinator, 2026-10-30): a CAST atom's Cost WITH parts is paid on top
     of the mana cost (CR 601.2f); only an EMPTY Cost waives the mana cost (118.9).
Radha's land row (coordinator, 2026-10-30): a free row that can do nothing is not
     offered (no phantom option), and running it with a land on top never raises.
V44  Protection (CR 702.16) on a permanent or a player, from any quality (a colour, a
     type, a name, everything): it can't be targeted (b), enchanted or equipped (c-d,
     SBAs 704.5m-n), dealt damage (e) or blocked (f) by a source with the quality. A
     protected creature may block such a creature. Each fighting creature is the source
     of its own damage (CR 701.12b). End to end in the protection packs (Baneslayer
     Angel, Basri's Lieutenant, Feat of Resistance, Feline Sovereign, Runed Halo,
     Sparkhunter Masticore).
W4-6 A search's ONE_OF/REST partition divides the cards the search found (Cultivate:
     one onto the battlefield, the other into your hand; CR 701.23a).
W4-1 "Create that many" after "whenever one or more nontoken creatures attack" counts
     the attackers the trigger's own filter names (Basri Ket's -2; CR 603.2c).
"""

from __future__ import annotations

import unittest

from MTG_bot.core.ability_tree import (
    ControllerRef,
    CounterKind,
    QConst,
    Verb,
    Zone,
    ZoneKind,
)
from MTG_bot.core.executor import Executor
from MTG_bot.core.identity import CardIdentity
from MTG_bot.core.state import (
    ZONE_BATTLEFIELD,
    ZONE_GRAVEYARD,
    ZONE_HAND,
    ZONE_LIBRARY,
    GameWorld,
)
from MTG_bot.core.test_executor_verbs import (
    UNIV,
    atom,
    card_id,
    reset_oracle_ids,
    target_sel,
)


class FixerCase(unittest.TestCase):
    """p0 Alpha (2/2) and p1 Beta (1/1) on the battlefield."""

    def setUp(self):
        reset_oracle_ids()
        self.world = GameWorld(num_players=2, start_life=20, master_seed=29)
        self.p0, self.p1 = self.world.player_order[0], self.world.player_order[1]
        self.alpha = self.world.add_card(
            card_id("Alpha", "2", "2"), self.p0, ZONE_BATTLEFIELD
        )
        self.beta = self.world.add_card(
            card_id("Beta", "1", "1"), self.p1, ZONE_BATTLEFIELD
        )
        self.ex = Executor(self.world)

    def walker(self, seat, loyalty="4", name="Walky"):
        ident = CardIdentity(
            oracle_id=card_id(name).oracle_id,
            name=name,
            type_line="Legendary Planeswalker — Walky",
            loyalty=loyalty,
            cmc=3,
        )
        return self.world.add_card(ident, seat, ZONE_BATTLEFIELD)


class TestV31LoyaltyZero(FixerCase):
    def remove_loyalty(self, pw, n):
        self.ex.execute(
            atom(
                Verb.REMOVE_COUNTER,
                target=target_sel(UNIV),
                counter_kind=CounterKind.LOYALTY,
                count=QConst(n),
            ),
            source=self.alpha,
            controller=self.p0,
            bindings={"target": [pw]},
        )

    def test_counter_removal_to_zero_buries_the_walker(self):
        pw = self.walker(self.p1, "5")
        self.world.cards[pw].counters["LOYALTY"] = 2  # a seeded, used walker
        self.remove_loyalty(pw, 2)
        # CR 704.5i: 0 loyalty puts it into its owner's graveyard; before V31 the
        # zeroed key was deleted and the walker read its printed 5 again.
        self.assertEqual(self.world.zone_of(pw).kind, ZONE_GRAVEYARD)
        self.assertEqual(self.world.controller_of(pw), self.p1)
        self.assertEqual(dict(self.world.cards[pw].counters), {})

    def test_counter_removal_below_zero_clamps_and_buries(self):
        pw = self.walker(self.p1, "5")
        self.world.cards[pw].counters["LOYALTY"] = 1
        self.remove_loyalty(pw, 2)
        self.assertEqual(self.world.zone_of(pw).kind, ZONE_GRAVEYARD)

    def test_counter_removal_from_an_unseeded_walker_reads_the_printed_loyalty(self):
        pw = self.walker(self.p1, "5")  # the rig never seeds the ledger
        self.remove_loyalty(pw, 2)
        self.assertEqual(dict(self.world.cards[pw].counters), {"LOYALTY": 3})
        self.assertEqual(self.world.zone_of(pw).kind, ZONE_BATTLEFIELD)

    def test_counter_removal_from_a_card_without_loyalty_adds_no_key(self):
        self.remove_loyalty(self.alpha, 1)
        self.assertEqual(dict(self.world.cards[self.alpha].counters), {})
        self.assertEqual(self.world.zone_of(self.alpha).kind, ZONE_BATTLEFIELD)

    def test_other_counter_kinds_still_drop_a_zeroed_key(self):
        self.world.cards[self.alpha].counters["PLUS_1_PLUS_1"] = 1
        self.ex.execute(
            atom(
                Verb.REMOVE_COUNTER,
                target=target_sel(UNIV),
                counter_kind=CounterKind.PLUS_1_PLUS_1,
                count=QConst(1),
            ),
            source=self.alpha,
            controller=self.p0,
            bindings={"target": [self.alpha]},
        )
        self.assertEqual(dict(self.world.cards[self.alpha].counters), {})

    def test_loyalty_leaves_with_the_walker_and_reentry_reads_printed(self):
        pw = self.walker(self.p0, "4")
        self.world.cards[pw].counters["LOYALTY"] = 1
        self.ex.execute(
            atom(
                Verb.MOVE_ZONE,
                cards=target_sel(UNIV),
                destination=Zone(ZoneKind.HAND, ControllerRef.OWNER),
            ),
            source=self.alpha,
            controller=self.p0,
            bindings={"cards": [pw]},
        )
        self.assertEqual(self.world.zone_of(pw).kind, ZONE_HAND)
        # CR 122.2: the counters ceased to exist; CR 306.5b: it enters again with
        # its printed loyalty (the binder seeds an absent key).
        self.assertEqual(dict(self.world.cards[pw].counters), {})
        from MTG_bot.core.executor.legality import _loyalty_of

        self.assertEqual(_loyalty_of(self.world, pw), 4)

    def test_counter_removal_on_a_walker_card_off_the_battlefield_adds_no_key(self):
        pw = self.walker(self.p0, "4")
        self.world.move_to_zone(pw, self.p0, ZONE_HAND)
        self.remove_loyalty(pw, 1)
        self.assertEqual(dict(self.world.cards[pw].counters), {})

    def test_loyalty_cost_paid_down_to_zero_buries_the_walker(self):
        from MTG_bot.core.ability_tree import Cost, CostLoyalty
        from MTG_bot.core.executor.legality import (
            build_payment_plan,
            ctx_for,
            pay_costs,
        )

        pw = self.walker(self.p0, "4")
        self.world.cards[pw].counters["LOYALTY"] = 3
        cost = Cost((CostLoyalty(delta=-3),))
        ctx = ctx_for(self.ex, source=pw, controller=self.p0)
        plan, why = build_payment_plan(self.world, ctx, cost)
        self.assertIsNone(why)
        pay_costs(self.ex, plan, source=pw, controller=self.p0)
        # CR 606.6: exactly its loyalty may be paid; CR 704.5i: then it dies.
        self.assertEqual(self.world.zone_of(pw).kind, ZONE_GRAVEYARD)
        self.assertEqual(dict(self.world.cards[pw].counters), {})


class TestV31bCountersCeaseOnZoneChange(FixerCase):
    def bounce(self, card):
        self.ex.execute(
            atom(
                Verb.MOVE_ZONE,
                cards=target_sel(UNIV),
                destination=Zone(ZoneKind.HAND, ControllerRef.OWNER),
            ),
            source=self.alpha,
            controller=self.p0,
            bindings={"cards": [card]},
        )

    def test_a_bounced_creature_loses_its_counters(self):
        self.world.cards[self.alpha].counters["PLUS_1_PLUS_1"] = 2
        self.bounce(self.alpha)
        self.assertEqual(self.world.zone_of(self.alpha).kind, ZONE_HAND)
        self.assertEqual(dict(self.world.cards[self.alpha].counters), {})

    def test_the_dies_row_still_folds_the_counters(self):
        from MTG_bot.core.executor.events import KIND_CREATURE_DIES

        self.world.cards[self.beta].counters["PLUS_1_PLUS_1"] = 1  # a 2/2 now
        self.ex.execute(
            atom(Verb.DEAL_DAMAGE, target=target_sel(UNIV), amount=QConst(2)),
            source=self.alpha,
            controller=self.p0,
            bindings={"target": [self.beta]},
        )
        self.assertEqual(self.world.zone_of(self.beta).kind, ZONE_GRAVEYARD)
        self.assertEqual(dict(self.world.cards[self.beta].counters), {})
        dies = [e for e in self.ex.journal.events if e.kind == KIND_CREATURE_DIES]
        self.assertEqual(len(dies), 1)
        # (from, owner, type line, was power, was toughness, ...): it died a 2/2.
        # re-pinned 2026-10-30: V7 (engine/verify-fixes) appends the controller
        # and the token flag as of death (data[5:7]), so the P/T is data[3:5].
        self.assertEqual(dies[0].dies[3:5], (2, 2))

    def test_counters_on_a_card_entering_the_battlefield_are_kept(self):
        card = self.world.add_card(card_id("Ent", "1", "1"), self.p0, ZONE_HAND)
        self.ex.execute(
            atom(
                Verb.MOVE_ZONE,
                cards=target_sel(UNIV),
                destination=Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU),
            ),
            source=card,
            controller=self.p0,
            bindings={"cards": [card]},
        )
        self.world.cards[card].counters["PLUS_1_PLUS_1"] = 1
        self.assertEqual(self.world.zone_of(card).kind, ZONE_BATTLEFIELD)
        self.assertEqual(dict(self.world.cards[card].counters), {"PLUS_1_PLUS_1": 1})


class TestV24OwnershipNeverChanges(FixerCase):
    def setUp(self):
        super().setUp()
        self.corpse = self.world.add_card(
            card_id("Corpse", "2", "2"), self.p1, ZONE_GRAVEYARD
        )

    def move(self, card, dest, controller, zone=None):
        self.ex.execute(
            atom(
                Verb.MOVE_ZONE,
                cards=target_sel(UNIV, zone or Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY)),
                destination=dest,
            ),
            source=self.alpha,
            controller=controller,
            bindings={"cards": [card]},
        )

    def test_owners_hand_written_as_any_is_the_owners_hand(self):
        # B-43 (Barrin, Niambi, Roaming Ghostlight): Zone(HAND, ANY) went to seat 0.
        self.move(self.beta, Zone(ZoneKind.HAND, ControllerRef.ANY), self.p0)
        self.assertEqual(self.world.zone_of(self.beta).kind, ZONE_HAND)
        self.assertEqual(self.world.controller_of(self.beta), self.p1)

    def test_seat_one_bouncing_its_own_creature_keeps_it(self):
        self.move(self.beta, Zone(ZoneKind.HAND, ControllerRef.ANY), self.p1)
        self.assertEqual(self.world.controller_of(self.beta), self.p1)

    def test_a_hand_named_as_yours_is_still_the_owners_hand(self):
        # CR 400.3: an object that would go to a hand other than its owner's goes to
        # its owner's.
        self.move(self.beta, Zone(ZoneKind.HAND, ControllerRef.YOU), self.p0)
        self.assertEqual(self.world.controller_of(self.beta), self.p1)

    def test_under_your_control_is_a_control_entry_and_death_returns_it_home(self):
        self.move(
            self.corpse,
            Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU),
            self.p0,
            zone=Zone(ZoneKind.GRAVEYARD, ControllerRef.ANY),
        )
        self.assertEqual(self.world.zone_of(self.corpse).kind, ZONE_BATTLEFIELD)
        self.assertEqual(self.world.controller_of(self.corpse), self.p1)  # owner
        self.assertEqual(self.ex.controller_of(self.corpse), self.p0)  # controller
        self.ex.execute(
            atom(Verb.DEAL_DAMAGE, target=target_sel(UNIV), amount=QConst(2)),
            source=self.beta,
            controller=self.p1,
            bindings={"target": [self.corpse]},
        )
        # It dies into its OWNER's graveyard and the control entry ends with it.
        self.assertEqual(self.world.zone_of(self.corpse).kind, ZONE_GRAVEYARD)
        self.assertEqual(self.world.controller_of(self.corpse), self.p1)
        self.assertEqual(self.ex.control_entries, [])

    def test_return_to_the_battlefield_without_a_controller_is_the_instructed_player(self):
        # CR 110.2a: Zone(BATTLEFIELD, ANY) ("return ... to the battlefield") puts it
        # under the effect's controller; it used to land on seat 0's battlefield.
        self.move(
            self.corpse,
            Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),
            self.p1,
            zone=Zone(ZoneKind.GRAVEYARD, ControllerRef.ANY),
        )
        self.assertEqual(self.world.controller_of(self.corpse), self.p1)
        self.assertEqual(self.ex.controller_of(self.corpse), self.p1)
        self.assertEqual(self.ex.control_entries, [])

    def test_owner_destination_on_the_battlefield_needs_no_entry(self):
        self.move(
            self.corpse,
            Zone(ZoneKind.BATTLEFIELD, ControllerRef.OWNER),
            self.p0,
            zone=Zone(ZoneKind.GRAVEYARD, ControllerRef.ANY),
        )
        self.assertEqual(self.ex.controller_of(self.corpse), self.p1)
        self.assertEqual(self.ex.control_entries, [])


class TestV24CastRefusesAnotherPlayersCard(unittest.TestCase):
    def test_cast_card_refuses_a_card_the_caster_does_not_own(self):
        from MTG_bot.core.ability_tree import Cost, SpellKind
        from MTG_bot.core.executor.stack import cast_card
        from MTG_bot.core.state import ZONE_EXILE
        from MTG_bot.core.test_executor_stack import StackCase

        case = StackCase()
        case.setUp()
        theirs = case.give("Theirs", SpellKind.SORCERY, seat=case.p1, zone=ZONE_EXILE)
        with self.assertRaises(NotImplementedError):
            cast_card(case.ex, case.p0, theirs, cost_override=Cost(()))
        self.assertEqual(case.world.zone_of(theirs).kind, ZONE_EXILE)
        self.assertEqual(case.world.controller_of(theirs), case.p1)


class TestV23OnlyADrawIsADraw(FixerCase):
    def setUp(self):
        super().setUp()
        self.lib = [self.world.add_card(card_id(f"L{i}"), self.p0) for i in (1, 2, 3)]

    def rows(self, kind):
        return [e for e in self.ex.journal.events if e.kind == kind]

    def test_a_draw_is_journalled_as_a_draw(self):
        from MTG_bot.core.executor.events import KIND_CARD_DRAWN

        self.ex.execute(
            atom(Verb.DRAW, controller=ControllerRef.YOU, amount=QConst(1)),
            source=self.alpha,
            controller=self.p0,
        )
        drawn = self.rows(KIND_CARD_DRAWN)
        self.assertEqual([e.subject for e in drawn], [self.lib[-1]])
        self.assertEqual(self.ex.journal.draw_counts, {self.p0: 1})

    def test_putting_a_library_card_into_a_hand_is_not_a_draw(self):
        from MTG_bot.core.executor.events import KIND_CARD_DRAWN, KIND_ZONE_CHANGE

        self.ex.execute(
            atom(
                Verb.MOVE_ZONE,
                cards=target_sel(UNIV, Zone(ZoneKind.LIBRARY, ControllerRef.YOU)),
                destination=Zone(ZoneKind.HAND, ControllerRef.YOU),
            ),
            source=self.alpha,
            controller=self.p0,
            bindings={"cards": [self.lib[0]]},
        )
        self.assertEqual(self.world.zone_of(self.lib[0]).kind, ZONE_HAND)
        moves = [e for e in self.rows(KIND_ZONE_CHANGE) if e.subject == self.lib[0]]
        self.assertEqual(len(moves), 1)  # the zone change is still journalled
        self.assertEqual(self.rows(KIND_CARD_DRAWN), [])  # CR 121.5: not a draw
        self.assertEqual(self.ex.journal.draw_counts, {})

    def test_a_searched_card_put_into_the_hand_is_not_a_draw(self):
        from MTG_bot.core.ability_tree import Selector, SelectorMode
        from MTG_bot.core.executor.events import KIND_CARD_DRAWN

        self.ex.execute(
            atom(
                Verb.SEARCH,
                cards=Selector(
                    QConst(1),
                    SelectorMode.CHOOSE,
                    UNIV,
                    zones=(Zone(ZoneKind.LIBRARY, ControllerRef.YOU),),
                ),
                destination=Zone(ZoneKind.HAND, ControllerRef.YOU),
            ),
            source=self.alpha,
            controller=self.p0,
            bindings={"cards": [self.lib[1]]},
        )
        self.assertEqual(self.world.zone_of(self.lib[1]).kind, ZONE_HAND)
        self.assertEqual(self.rows(KIND_CARD_DRAWN), [])


class TestV23NestedBoundariesJournalOnce(FixerCase):
    def test_an_enclosing_boundary_does_not_rejournal_an_inner_atom(self):
        from MTG_bot.core.executor.events import KIND_CREATURE_DIES, KIND_ZONE_CHANGE

        journal = self.ex.journal
        outer = journal.snapshot()  # e.g. a cast's park boundary around its cost
        self.ex.execute(  # the inner, journalled atom: a sacrifice
            atom(Verb.SACRIFICE, target=target_sel(UNIV)),
            source=self.alpha,
            controller=self.p0,
            bindings={"target": [self.alpha]},
        )
        n_dies = len([e for e in journal.events if e.kind == KIND_CREATURE_DIES])
        self.world.cards[self.beta].tapped = True  # the outer's own change
        new = journal.record_atom(outer, None, "TEST", [])
        self.assertEqual(n_dies, 1)
        self.assertEqual(
            [e for e in new if e.kind in (KIND_CREATURE_DIES, KIND_ZONE_CHANGE)], []
        )
        self.assertEqual([(e.kind, e.subject) for e in new], [("TAP_STATE", self.beta)])
        self.assertEqual(journal.open_depth(), 0)

    def test_an_outer_change_made_before_an_inner_atom_is_still_journalled(self):
        # vfix's raw mana tap inside a running PAY atom (CR 605.3b, no nested atom)
        # happens BEFORE pay_costs runs a nested sacrifice: the fold moves only the
        # keys the inner boundary changed, so the outer diff still sees the tap.
        journal = self.ex.journal
        outer = journal.snapshot()
        self.world.cards[self.beta].tapped = True  # the outer's own raw change
        self.ex.execute(
            atom(Verb.SACRIFICE, target=target_sel(UNIV)),
            source=self.alpha,
            controller=self.p0,
            bindings={"target": [self.alpha]},
        )
        new = journal.record_atom(outer, None, "TEST", [])
        self.assertEqual([(e.kind, e.subject) for e in new], [("TAP_STATE", self.beta)])

    def test_inner_card_damage_is_not_rejournalled(self):
        from MTG_bot.core.executor.events import KIND_DAMAGE

        journal = self.ex.journal
        outer = journal.snapshot()
        start = len(self.ex.events)
        self.ex.execute(
            atom(Verb.DEAL_DAMAGE, target=target_sel(UNIV), amount=QConst(1)),
            source=self.beta,
            controller=self.p1,
            bindings={"target": [self.alpha]},
        )
        new = journal.record_atom(outer, None, "TEST", list(self.ex.events[start:]))
        damage = [e for e in journal.events if e.kind == KIND_DAMAGE]
        self.assertEqual(len(damage), 1)
        self.assertEqual([e for e in new if e.kind == KIND_DAMAGE], [])

    def test_a_dangling_boundary_is_dropped(self):
        journal = self.ex.journal
        depth = journal.open_depth()
        journal.snapshot()  # an atom that raised before closing its boundary
        journal.drop_open(depth)
        self.assertEqual(journal.open_depth(), depth)


class TestV33DiscardYourHand(FixerCase):
    def plan(self, count, mode):
        from MTG_bot.core.ability_tree import (
            Cost,
            CostDiscard,
            Selector,
        )
        from MTG_bot.core.executor.legality import build_payment_plan, ctx_for

        cost = Cost(
            (
                CostDiscard(
                    target=Selector(
                        count,
                        mode,
                        UNIV,
                        zones=(Zone(ZoneKind.HAND, ControllerRef.YOU),),
                    )
                ),
            )
        )
        ctx = ctx_for(self.ex, source=self.alpha, controller=self.p0)
        return build_payment_plan(self.world, ctx, cost)

    def test_discard_your_hand_takes_every_card(self):
        from MTG_bot.core.ability_tree import QUnbounded, SelectorMode

        hand = [
            self.world.add_card(card_id(f"H{i}"), self.p0, ZONE_HAND) for i in (1, 2, 3)
        ]
        plan, why = self.plan(QUnbounded(), SelectorMode.ALL)
        self.assertIsNone(why)
        self.assertEqual(sorted(plan.discard), sorted(hand))

    def test_discard_your_hand_with_an_empty_hand_pays(self):
        from MTG_bot.core.ability_tree import QUnbounded, SelectorMode

        plan, why = self.plan(QUnbounded(), SelectorMode.ALL)
        self.assertIsNone(why)
        self.assertEqual(plan.discard, ())

    def test_discard_a_card_still_needs_a_card(self):
        from MTG_bot.core.ability_tree import SelectorMode

        plan, why = self.plan(QConst(1), SelectorMode.CHOOSE)
        self.assertIsNone(plan)
        self.assertEqual(why, "cost:discard:insufficient_candidates:0<1")


class TestV36EffectCastPaysAdditionalCosts(unittest.TestCase):
    def setUp(self):
        from MTG_bot.core.ability_tree import (
            Cost,
            CostDiscard,
            Selector,
            SelectorMode,
            SpellKind,
        )
        from MTG_bot.core.state import ZONE_GRAVEYARD as GY
        from MTG_bot.core.test_executor_stack import StackCase

        self.case = StackCase()
        self.case.setUp()
        discard = Cost(
            (
                CostDiscard(
                    target=Selector(
                        QConst(1),
                        SelectorMode.CHOOSE,
                        UNIV,
                        zones=(Zone(ZoneKind.HAND, ControllerRef.YOU),),
                    )
                ),
            )
        )
        self.spell = self.case.give(
            "Thrilly",
            SpellKind.INSTANT,
            effect=atom(Verb.DRAW, controller=ControllerRef.YOU, amount=QConst(1)),
            zone=GY,
            additional_costs=(discard,),
        )
        self.free = Cost(())

    def test_the_additional_cost_is_paid_on_a_free_cast(self):
        from MTG_bot.core.executor.stack import cast_card

        junk = self.case.world.add_card(card_id("Junk"), self.case.p0, ZONE_HAND)
        cast_card(self.case.ex, self.case.p0, self.spell, cost_override=self.free)
        self.assertEqual(self.case.world.zone_of(junk).kind, ZONE_GRAVEYARD)
        self.assertEqual(self.case.world.zone_of(self.spell).kind, ZONE_GRAVEYARD)

    def test_an_unpayable_additional_cost_refuses_the_cast(self):
        from MTG_bot.core.executor.stack import cast_card

        for card in list(self.case.world.players[self.case.p0].zone(ZONE_HAND).entries):
            self.case.world.move_to_zone(card, self.case.p0, ZONE_GRAVEYARD)
        with self.assertRaises(ValueError) as caught:
            cast_card(self.case.ex, self.case.p0, self.spell, cost_override=self.free)
        self.assertIn("cost:discard:insufficient_candidates", str(caught.exception))
        self.assertEqual(self.case.world.zone_of(self.spell).kind, ZONE_GRAVEYARD)


class TestV35TokensCeaseOffTheBattlefield(FixerCase):
    def token(self, seat, name="Tok"):
        ident = CardIdentity(
            oracle_id=card_id(name).oracle_id,
            name=name,
            type_line="Creature — Soldier",
            power="1",
            toughness="1",
            is_token=True,
        )
        return self.world.add_card(ident, seat, ZONE_BATTLEFIELD)

    def kill(self, card):
        self.ex.execute(
            atom(Verb.DEAL_DAMAGE, target=target_sel(UNIV), amount=QConst(5)),
            source=self.beta,
            controller=self.p1,
            bindings={"target": [card]},
        )

    def test_a_dead_token_ceases_to_exist(self):
        from MTG_bot.core.executor.events import KIND_CREATURE_DIES

        tok = self.token(self.p0)
        self.kill(tok)
        self.assertNotIn(tok, self.world.cards)
        self.assertEqual(self.world.players[self.p0].zone(ZONE_GRAVEYARD).entries, [])
        # It did die first (CR 111.7: its leave triggers see the zone change).
        dies = [e for e in self.ex.journal.events if e.kind == KIND_CREATURE_DIES]
        self.assertEqual([e.subject for e in dies], [tok])

    def test_a_bounced_token_ceases_to_exist(self):
        tok = self.token(self.p1)
        self.ex.execute(
            atom(
                Verb.MOVE_ZONE,
                cards=target_sel(UNIV),
                destination=Zone(ZoneKind.HAND, ControllerRef.OWNER),
            ),
            source=self.alpha,
            controller=self.p0,
            bindings={"cards": [tok]},
        )
        self.assertNotIn(tok, self.world.cards)
        self.assertEqual(self.world.players[self.p1].zone(ZONE_HAND).entries, [])

    def test_a_dead_nontoken_card_stays_in_the_graveyard(self):
        self.kill(self.alpha)
        self.assertEqual(self.world.zone_of(self.alpha).kind, ZONE_GRAVEYARD)

    def test_a_token_on_the_battlefield_stays(self):
        tok = self.token(self.p0)
        self.ex.execute(
            atom(Verb.GAIN_LIFE, controller=ControllerRef.YOU, amount=QConst(1)),
            source=self.alpha,
            controller=self.p0,
        )
        self.assertEqual(self.world.zone_of(tok).kind, ZONE_BATTLEFIELD)


class TestV29TargetDependentTax(unittest.TestCase):
    def test_the_tax_detector_reads_targets_source_anywhere_in_a_filter(self):
        from MTG_bot.core.ability_tree import FAnd, FAtom, FAtomPred, FNot
        from MTG_bot.core.executor.query import _reads_targets_source

        ts = FAtom(FAtomPred.TARGETS_SOURCE)
        self.assertTrue(_reads_targets_source(ts))
        self.assertTrue(_reads_targets_source(FAnd((FAtom(FAtomPred.IS_PERMANENT), ts))))
        self.assertTrue(_reads_targets_source(FNot(ts)))
        self.assertFalse(_reads_targets_source(FAtom(FAtomPred.IS_SOURCE)))
        self.assertFalse(_reads_targets_source(None))


class TestV25EachTargetReadsItsOwnSlot(FixerCase):
    def test_a_target_nested_in_a_quantity_is_found(self):
        from MTG_bot.core.ability_tree import (
            PtDelta,
            PtDirection,
            QBin,
            QBinOp,
            QProp,
            QPropField,
        )
        from MTG_bot.core.executor.query import role_target_selectors

        sel = target_sel(UNIV)
        prop = QProp(referent=sel, field=QPropField.POWER)
        self.assertEqual(role_target_selectors(sel), [sel])
        self.assertEqual(role_target_selectors(prop), [sel])
        self.assertEqual(role_target_selectors(QBin(QBinOp.ADD, prop, QConst(1))), [sel])
        self.assertEqual(
            role_target_selectors(PtDelta(direction=PtDirection.INCREASE, magnitude=prop)),
            [sel],
        )
        self.assertEqual(role_target_selectors(QConst(2)), [])

    def test_the_damage_goes_to_the_second_target_at_the_first_ones_power(self):
        from MTG_bot.core.ability_tree import (
            FAnd,
            FAtom,
            FAtomPred,
            QProp,
            QPropField,
        )

        # "Target creature you control deals damage equal to its power to another
        # target creature": slot 1 = your Gamma (3/3), slot 2 = the opponent's Bigby.
        gamma = self.world.add_card(card_id("Gamma", "3", "3"), self.p0, ZONE_BATTLEFIELD)
        bigby = self.world.add_card(card_id("Bigby", "5", "5"), self.p1, ZONE_BATTLEFIELD)
        yours = target_sel(
            FAnd(
                (
                    FAtom(FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
                    FAtom(FAtomPred.TYPE_EQ, string_value="Creature"),
                )
            )
        )
        other = target_sel(FAtom(FAtomPred.TYPE_EQ, string_value="Creature"))
        effect = atom(
            Verb.DEAL_DAMAGE,
            amount=QProp(referent=yours, field=QPropField.POWER),
            target=other,
        )
        self.ex.apply_effect(
            effect,
            source=self.alpha,
            controller=self.p0,
            bindings={"target": [gamma, bigby]},
            slot_designations={repr(yours): (gamma,), repr(other): (bigby,)},
        )
        self.assertEqual(self.ex.damage.get(bigby), 3)  # Gamma's power
        self.assertNotIn(gamma, self.ex.damage)  # the first target is not hit


class TestV34DesignationOnlyTargetSlot(unittest.TestCase):
    def test_subira_unblockable_ability_offers_creatures_with_power_two_or_less(self):
        from MTG_bot.core.executor.games import get_supply
        from MTG_bot.core.executor.query import activation_target_slots
        from tools.run_scenarios import ScenarioRunner

        pack = {
            "set": "M21",
            "world": {"life": 20, "seed": 7},
            "cards": [
                {"key": "sub", "zone": "battlefield", "controller": 0,
                 "real": "Subira, Tulzidi Caravanner"},
                {"key": "runner", "zone": "battlefield", "controller": 0,
                 "name": "Runner", "power": 1, "toughness": 1},
                {"key": "big", "zone": "battlefield", "controller": 0,
                 "name": "Big", "power": 3, "toughness": 3},
                {"key": "obear", "zone": "battlefield", "controller": 1,
                 "name": "Opp Bear", "power": 2, "toughness": 2},
            ],
            "steps": [],
            "expect": {},
        }
        runner = ScenarioRunner(pack, get_supply("all", "M21"))
        ex, sub = runner.ex, runner.handles["sub"]
        ability = ex.binder.handle_record[sub].abilities[0]
        slots = activation_target_slots(ex, ability.effect, source=sub, seat=runner.p0)
        self.assertEqual(len(slots), 1)
        # "Another target creature with power 2 or less": not Subira (a 2/3, but
        # 'another'), not the 3/3; either side's creature.
        self.assertEqual(
            set(slots[0].candidates), {runner.handles["runner"], runner.handles["obear"]}
        )
        self.assertEqual((slots[0].min_count, slots[0].max_count), (1, 1))


class TestV28ChooseIgnoresAForeignDesignation(FixerCase):
    def lands_selector(self):
        from MTG_bot.core.ability_tree import FAtom, FAtomPred, Selector, SelectorMode

        return Selector(
            QConst(4),
            SelectorMode.CHOOSE,
            FAtom(FAtomPred.TYPE_EQ, string_value="Land"),
            zones=(Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),),
        )

    def test_a_foreign_designation_does_not_hijack_the_choice(self):
        from MTG_bot.core.executor.selectors import role_handles

        land = self.world.add_card(
            card_id("Plains", type_line="Basic Land — Plains"), self.p0, ZONE_BATTLEFIELD
        )
        spell = self.world.add_card(card_id("Shocky", type_line="Instant"), self.p1, ZONE_GRAVEYARD)
        ctx = self.ex._ctx(
            source=self.alpha, controller=self.p0, bindings={"target": [spell]}, decisions=()
        )
        untap = atom(Verb.UNTAP, target=self.lands_selector())
        self.assertEqual(role_handles(ctx, untap, "target"), [land])

    def test_a_designation_that_fits_still_binds(self):
        from MTG_bot.core.executor.selectors import role_handles

        land = self.world.add_card(
            card_id("Plains", type_line="Basic Land — Plains"), self.p0, ZONE_BATTLEFIELD
        )
        self.world.add_card(
            card_id("Island", type_line="Basic Land — Island"), self.p0, ZONE_BATTLEFIELD
        )
        ctx = self.ex._ctx(
            source=self.alpha, controller=self.p0, bindings={"target": [land]}, decisions=()
        )
        untap = atom(Verb.UNTAP, target=self.lands_selector())
        self.assertEqual(role_handles(ctx, untap, "target"), [land])


class TestV30GraveyardTriggers(unittest.TestCase):
    def runner(self, zone):
        from MTG_bot.core.executor.games import get_supply
        from tools.run_scenarios import ScenarioRunner

        pack = {
            "set": "M21",
            "world": {"life": 20, "seed": 7},
            "cards": [
                {"key": "g", "real": "Silversmote Ghoul", "zone": zone, "controller": 0}
            ],
            "steps": [],
            "expect": {},
        }
        return ScenarioRunner(pack, get_supply("all", "M21"))

    def test_the_ghoul_trigger_functions_from_the_graveyard_only(self):
        from MTG_bot.core.executor.binding import functions_from_graveyard

        r = self.runner("graveyard")
        g = r.handles["g"]
        record = r.ex.binder.handle_record[g]
        self.assertTrue(functions_from_graveyard(record.abilities[0]))
        self.assertFalse(functions_from_graveyard(record.abilities[1]))  # activated
        self.assertIn((g, 0), r.ex.binder.attached_graveyard)
        self.assertNotIn((g, 0), r.ex.binder.attached)

    def test_on_the_battlefield_the_ghoul_trigger_does_not_function(self):
        r = self.runner("battlefield")
        g = r.handles["g"]
        self.assertNotIn((g, 0), r.ex.binder.attached)
        self.assertNotIn((g, 0), r.ex.binder.attached_graveyard)
        # it dies: now the trigger functions (and leaves again with the card)
        r.ex.execute(
            atom(Verb.SACRIFICE, target=target_sel(UNIV)),
            source=g,
            controller=r.p0,
            bindings={"target": [g]},
        )
        self.assertIn((g, 0), r.ex.binder.attached_graveyard)


class TestCastCostRoleIsAdditional(unittest.TestCase):
    def setUp(self):
        from MTG_bot.core.ability_tree import (
            Cost,
            CostManaColor,
            CostManaGeneric,
            SpellKind,
        )
        from MTG_bot.core.test_executor_stack import StackCase

        self.case = StackCase()
        self.case.setUp()
        self.spell = self.case.give(
            "Embracey",
            SpellKind.SORCERY,
            cost=Cost((CostManaColor("B", QConst(1)), CostManaGeneric(QConst(1)))),
            effect=atom(Verb.GAIN_LIFE, controller=ControllerRef.YOU, amount=QConst(1)),
            zone=ZONE_GRAVEYARD,
        )

    def cast(self, cost_override):
        from MTG_bot.core.executor.stack import cast_card

        cast_card(self.case.ex, self.case.p0, self.spell, cost_override=cost_override)

    def test_a_cost_with_parts_is_paid_on_top_of_the_mana_cost(self):
        from MTG_bot.core.ability_tree import Cost, CostLife

        self.case.mana(self.case.p0, B=2)
        self.cast(Cost((CostLife(QConst(3)),)))
        # {1}{B} AND 3 life (then the sorcery's own +1).
        self.assertEqual(self.case.world.players[self.case.p0].mana_pool, {})
        self.assertEqual(self.case.world.players[self.case.p0].life, 20 - 3 + 1)

    def test_a_cost_with_parts_cannot_skip_the_mana_cost(self):
        from MTG_bot.core.ability_tree import Cost, CostLife

        with self.assertRaises(ValueError):
            self.cast(Cost((CostLife(QConst(3)),)))  # no mana in the pool
        self.assertEqual(self.case.world.players[self.case.p0].life, 20)

    def test_an_empty_cost_still_waives_the_mana_cost(self):
        from MTG_bot.core.ability_tree import Cost

        self.cast(Cost(()))
        self.assertEqual(self.case.world.players[self.case.p0].life, 21)


class TestInertFreeRows(unittest.TestCase):
    def runner(self, top):
        from MTG_bot.core.executor.games import get_supply
        from tools.run_scenarios import ScenarioRunner

        pack = {
            "set": "M21",
            "world": {"life": 20, "seed": 7, "library_top": True},
            "cards": [
                {"key": "radha", "real": "Radha, Heart of Keld", "zone": "battlefield",
                 "controller": 0},
                {"key": "snoop", "real": "Conspicuous Snoop", "zone": "battlefield",
                 "controller": 0},
                {"key": "top", "real": top, "zone": "library", "controller": 0},
                {"key": "junk", "name": "Top Junk", "type": "Sorcery", "zone": "library",
                 "controller": 0},
            ],
            "mana": {"0": {"R": 1}},
            "steps": [],
            "expect": {},
        }
        return ScenarioRunner(pack, get_supply("all", "M21"))

    def offered(self, r, key):
        from MTG_bot.core.executor.query import legal_activations

        return [
            o.ability_idx
            for o in legal_activations(r.world, r.ex, r.p0)
            if o.source == r.handles[key]
        ]

    def test_radha_land_row_is_not_offered_and_never_raises(self):
        r = self.runner("Mountain")
        self.assertEqual(r.world.cards[r.world.players[r.p0].zone("library").entries[-1]].identity.name, "Mountain")
        self.assertNotIn(1, self.offered(r, "radha"))  # nothing castable: phantom
        # Running the row anyway (a direct activation) casts nothing and raises
        # nothing: the land stays on top (weaker than printed until R5-3).
        from MTG_bot.core.executor.legality import activate

        activate(r.ex, r.handles["radha"], 1, seat=r.p0, decisions=("fire", "fire"))
        self.assertEqual(r.world.zone_of(r.handles["top"]).kind, "library")

    def test_snoop_row_is_offered_when_a_goblin_on_top_can_be_cast(self):
        r = self.runner("Goblin Arsonist")
        self.assertTrue(self.offered(r, "snoop"))
        self.assertNotIn(1, self.offered(r, "radha"))


class TestV44Protection(FixerCase):
    """p1 also controls a red and a blue 1/1."""

    def setUp(self):
        super().setUp()
        self.red = self.world.add_card(self.ident("Red Imp", ("R",)), self.p1, ZONE_BATTLEFIELD)
        self.blue = self.world.add_card(self.ident("Blue Imp", ("U",)), self.p1, ZONE_BATTLEFIELD)

    @staticmethod
    def ident(name, colors, type_line="Creature", keywords=()):
        creature = type_line == "Creature"
        return CardIdentity(
            oracle_id=card_id(name).oracle_id,
            name=name,
            type_line=type_line,
            power="1" if creature else None,
            toughness="1" if creature else None,
            cmc=1,
            colors=colors,
            keywords=keywords,
        )

    def protect(self, holder, quality, zone=None):
        from MTG_bot.core.ability_tree import DurationEot, Keyword, KeywordAbility

        sel = target_sel(UNIV) if zone is None else target_sel(UNIV, zone)
        self.ex.execute(
            atom(
                Verb.GRANT_ABILITY,
                target=sel,
                ability=KeywordAbility(Keyword.PROTECTION, (quality,)),
                duration=DurationEot(),
            ),
            source=self.alpha,
            controller=self.p0,
            bindings={"target": [holder]},
        )

    def damage(self, source, target, n):
        from MTG_bot.core.ability_tree import Selector, SelectorMode

        sel = Selector(QConst(1), SelectorMode.TARGET, UNIV, zones=(Zone(ZoneKind.ANY, ControllerRef.ANY),))
        return self.ex.execute(
            atom(Verb.DEAL_DAMAGE, target=sel, amount=QConst(n)),
            source=source,
            controller=self.world.controller_of(source),
            bindings={"target": [target]},
        )

    @staticmethod
    def red_quality():
        from MTG_bot.core.ability_tree import FAtom, FAtomPred

        return FAtom(FAtomPred.COLOR_HAS, color="R")

    def test_damage_from_a_source_with_the_quality_is_prevented(self):
        self.protect(self.alpha, self.red_quality())
        events = self.damage(self.red, self.alpha, 2)
        self.assertNotIn(self.alpha, self.ex.damage)
        self.assertIn(("DAMAGE_PREVENTED", str(self.alpha), "PROTECTION", 2), [e[1:] for e in events])
        self.damage(self.blue, self.alpha, 1)
        self.assertEqual(self.ex.damage.get(self.alpha), 1)

    def test_it_cannot_be_targeted_by_a_source_with_the_quality(self):
        from MTG_bot.core.executor.legality import enumerate_candidates

        self.protect(self.alpha, self.red_quality())
        sel = target_sel()
        red_ctx = self.ex._ctx(source=self.red, controller=self.p1, bindings=None, decisions=())
        blue_ctx = self.ex._ctx(source=self.blue, controller=self.p1, bindings=None, decisions=())
        self.assertNotIn(self.alpha, enumerate_candidates(sel, red_ctx))
        self.assertIn(self.alpha, enumerate_candidates(sel, blue_ctx))
        # Its own controller's red source can't target it either (no "opponent" clause).
        own_red = self.world.add_card(self.ident("Own Red", ("R",)), self.p0, ZONE_BATTLEFIELD)
        own_ctx = self.ex._ctx(source=own_red, controller=self.p0, bindings=None, decisions=())
        self.assertNotIn(self.alpha, enumerate_candidates(sel, own_ctx))

    def test_only_the_attackers_protection_restricts_a_block(self):
        from MTG_bot.core.executor.legality import block_pair_blocked_reason

        self.protect(self.alpha, self.red_quality())
        # A red creature can't block Alpha (702.16f) ...
        self.assertIsNotNone(block_pair_blocked_reason(self.ex, self.red, self.alpha))
        # ... but Alpha may block a red creature, and the red damage is prevented (702.16e).
        self.assertIsNone(block_pair_blocked_reason(self.ex, self.alpha, self.red))

    def test_protection_from_everything(self):
        from MTG_bot.core.executor.legality import (
            block_pair_blocked_reason,
            protected_from,
        )

        self.protect(self.alpha, UNIV)
        for source in (self.red, self.blue, self.beta):  # beta is colourless
            self.assertTrue(protected_from(self.ex, self.alpha, source))
            self.assertIsNotNone(block_pair_blocked_reason(self.ex, source, self.alpha))
        self.damage(self.beta, self.alpha, 3)
        self.assertNotIn(self.alpha, self.ex.damage)

    def test_protection_functions_only_on_the_battlefield(self):
        from MTG_bot.core.executor.legality import protected_from

        self.protect(self.alpha, UNIV)
        self.assertTrue(protected_from(self.ex, self.alpha, self.red))
        self.world.move_to_zone(self.alpha, self.p0, ZONE_GRAVEYARD)
        self.assertFalse(protected_from(self.ex, self.alpha, self.red))

    def test_a_player_with_protection(self):
        from MTG_bot.core.ability_tree import Selector, SelectorMode
        from MTG_bot.core.executor.legality import enumerate_candidates
        from MTG_bot.core.executor.query import TargetSlot, _widen_any_target

        self.protect(self.p0, self.red_quality(), zone=Zone(ZoneKind.PLAYER, ControllerRef.ANY))
        life = self.world.players[self.p0].life
        self.damage(self.red, self.p0, 3)
        self.assertEqual(self.world.players[self.p0].life, life)  # prevented (702.16e)
        self.damage(self.blue, self.p0, 1)
        self.assertEqual(self.world.players[self.p0].life, life - 1)
        players = Selector(QConst(1), SelectorMode.TARGET, UNIV, zones=(Zone(ZoneKind.PLAYER, ControllerRef.ANY),))
        red_ctx = self.ex._ctx(source=self.red, controller=self.p1, bindings=None, decisions=())
        self.assertNotIn(self.p0, enumerate_candidates(players, red_ctx))
        # "Any target": the widening leaves the protected player out for a red source only.
        any_target = Selector(QConst(1), SelectorMode.TARGET, UNIV, zones=(Zone(ZoneKind.ANY, ControllerRef.ANY),))
        slot = TargetSlot(selector=any_target, candidates=(self.beta,), min_count=1, max_count=1, forced=True)
        self.assertNotIn(self.p0, _widen_any_target(self.ex, any_target, slot, self.red).candidates)
        self.assertIn(self.p0, _widen_any_target(self.ex, any_target, slot, self.blue).candidates)

    def test_auras_fall_off_and_equipment_unattaches(self):
        aura = self.world.add_card(
            self.ident("Red Aura", ("R",), "Enchantment — Aura", ("ENCHANT",)), self.p1, ZONE_BATTLEFIELD
        )
        gear = self.world.add_card(
            self.ident("Red Gear", ("R",), "Artifact — Equipment", ("EQUIP",)), self.p1, ZONE_BATTLEFIELD
        )
        blue_aura = self.world.add_card(
            self.ident("Blue Aura", ("U",), "Enchantment — Aura", ("ENCHANT",)), self.p1, ZONE_BATTLEFIELD
        )
        for card in (aura, gear, blue_aura):
            self.ex.attach_aura(card, self.alpha)
        self.protect(self.alpha, self.red_quality())
        self.assertEqual(self.world.zone_of(aura).kind, ZONE_GRAVEYARD)  # 704.5m
        self.assertNotIn(aura, self.ex.attachments)
        self.assertEqual(self.world.zone_of(gear).kind, ZONE_BATTLEFIELD)  # 704.5n: stays
        self.assertNotIn(gear, self.ex.attachments)
        self.assertEqual(self.ex.attachments.get(blue_aura), self.alpha)  # other colour stays

    def test_an_aura_entering_without_being_cast_cannot_choose_a_protected_host(self):
        from MTG_bot.core.executor.aura_entry import aura_entry_hosts

        aura = self.world.add_card(
            self.ident("Red Aura", ("R",), "Enchantment — Aura", ("ENCHANT",)), self.p1, ZONE_HAND
        )
        before = aura_entry_hosts(self.ex, aura, self.p1)
        self.protect(self.alpha, self.red_quality())
        after = aura_entry_hosts(self.ex, aura, self.p1)
        self.assertIn(self.alpha, before)
        self.assertEqual(set(before) - set(after), {self.alpha})

    def test_each_fighting_creature_deals_its_own_damage(self):
        self.protect(self.alpha, self.red_quality())
        # Alpha (the ability's source) fights the red 1/1: Alpha's 2 kills it; the
        # red creature's 1 comes from the red creature, so protection prevents it.
        self.ex.execute(
            atom(Verb.FIGHT, target=target_sel()),
            source=self.alpha,
            controller=self.p0,
            bindings={"target": [self.red]},
        )
        self.assertEqual(self.world.zone_of(self.red).kind, ZONE_GRAVEYARD)
        self.assertNotIn(self.alpha, self.ex.damage)


class TestW46SearchPartitionDividesTheFoundCards(FixerCase):
    def setUp(self):
        super().setUp()
        self.basics = [
            self.world.add_card(
                card_id(name, type_line=f"Basic Land — {name}"), self.p0, ZONE_LIBRARY
            )
            for name in ("Forest", "Plains", "Island", "Swamp")
        ]

    def partition(self, mode, ctx):
        from MTG_bot.core.ability_tree import FAtom, FAtomPred, Selector
        from MTG_bot.core.executor.selectors import resolve_selector

        basic = FAtom(FAtomPred.SUPERTYPE_EQ, string_value="Basic")
        sel = Selector(QConst(1), mode, basic, zones=(Zone(ZoneKind.LIBRARY, ControllerRef.YOU),))
        return resolve_selector(sel, ctx)

    def test_the_one_of_and_the_rest_read_only_the_found_cards(self):
        from MTG_bot.core.ability_tree import SelectorMode

        _forest, plains, island, _swamp = self.basics
        ctx = self.ex._ctx(
            source=self.alpha, controller=self.p0, bindings=None, decisions=(str(island),)
        )
        ctx.search_partition = True
        ctx.search_found = (plains, island)
        self.assertEqual(self.partition(SelectorMode.ONE_OF, ctx), [island])
        self.assertEqual(self.partition(SelectorMode.REST, ctx), [plains])

    def test_without_a_partition_search_the_rest_is_unchanged(self):
        from MTG_bot.core.ability_tree import SelectorMode

        ctx = self.ex._ctx(source=self.alpha, controller=self.p0, bindings=None, decisions=())
        self.assertEqual(self.partition(SelectorMode.REST, ctx), sorted(self.basics))

    def test_cultivate_puts_one_found_land_in_play_and_the_other_in_hand(self):
        from MTG_bot.core.executor.games import get_supply
        from tools.run_scenarios import ScenarioRunner

        lands = [
            {"key": k, "name": n, "type": f"Basic Land — {n}", "zone": "library", "controller": 0}
            for k, n in (("fo", "Forest"), ("pl", "Plains"), ("is", "Island"), ("sw", "Swamp"))
        ]
        pack = {
            "set": "M21",
            "world": {"life": 20, "seed": 7},
            "cards": [{"key": "cv", "real": "Cultivate", "zone": "hand", "controller": 0},
                      *lands,
                      {"key": "junk", "name": "Top Junk", "type": "Creature", "power": "1",
                       "toughness": "1", "zone": "library", "controller": 0}],
            "mana": {"0": {"G": 3}},
            "steps": [{"op": "cast", "real": "Cultivate", "key": "cv",
                       "decisions": ["sw", "fo", "sw"]}],
            "expect": {},
        }
        r = ScenarioRunner(pack, get_supply("all", "M21"))
        for step in pack["steps"]:
            r.run_step(step)
        zone = {k: r.world.zone_of(r.handles[k]).kind for k in ("fo", "pl", "is", "sw")}
        self.assertEqual(zone, {"fo": "hand", "pl": "library", "is": "library", "sw": "battlefield"})


class TestW41ThatManyCountsTheTriggersAttackers(unittest.TestCase):
    def soldiers_after_attack(self, attackers):
        from MTG_bot.core.executor.games import get_supply
        from tools.run_scenarios import ScenarioRunner

        def creature(key, name, token):
            return {"key": key, "name": name, "type": "Creature — Bear", "power": 2,
                    "toughness": 2, "token": token, "zone": "battlefield", "controller": 0}

        pack = {
            "set": "M21",
            "world": {"life": 20, "seed": 7},
            "cards": [{"key": "basri", "real": "Basri Ket", "zone": "battlefield", "controller": 0},
                      creature("bear", "Bear", False),
                      creature("t1", "Spirit", True),
                      creature("t2", "Spirit", True)],
            "steps": [{"op": "loyalty", "key": "basri", "set": 3},
                      {"op": "activate", "key": "basri", "idx": 1, "seat": 0},
                      {"op": "combat", "seat": 0, "attack": {k: True for k in attackers}}],
            "expect": {},
        }
        r = ScenarioRunner(pack, get_supply("all", "M21"))
        for step in pack["steps"]:
            r.run_step(step)
        return sum(
            1
            for state in r.world.cards.values()
            if state.identity.is_token and state.identity.name == "Soldier"
        )

    def test_one_nontoken_and_two_tokens_make_one_soldier(self):
        self.assertEqual(self.soldiers_after_attack(("bear", "t1", "t2")), 1)

    def test_tokens_alone_make_none(self):
        self.assertEqual(self.soldiers_after_attack(("t1", "t2")), 0)


if __name__ == "__main__":
    unittest.main()
