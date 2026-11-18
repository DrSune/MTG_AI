"""On the battlefield a player's side is control, not ownership (CR 110.2).

A card's other zones are its owner's (CR 400.3), and the world files a permanent under its owner's
battlefield whoever controls it (a control entry, ``Executor.gain_control``). So a zone on the
battlefield scoped to a player reads the controller, as the subject filter's CONTROLLER_IS does:
* a trigger's endpoint, leaving: the controller the object had as it left (CR 603.6c, 603.10a):
  "an enchantment you control is put into a graveyard from the battlefield" (M20 Starfield
  Mystic; end to end in the pack starfield_mystic_an_enchantment_you_control_counts_whoever_owns_it),
  "When this enchantment leaves the battlefield, you lose the game" (M21 Nine Lives) for the
  player who stole it;
* a trigger's endpoint, entering: the controller it enters under (CR 603.6a): "When this creature
  enters" compiles as an entry from anywhere onto Zone(BATTLEFIELD, YOU), so a creature put onto
  the battlefield under the control of a player who does not own it triggers for that player;
* the last known controller of a permanent that leaves with the Aura that controls it (every
  departure is snapshotted before what is anchored on any of them ends);
* a replacement's endpoints, the same way (``ReplacementRegistry._endpoint_matches``);
* who sacrificed a permanent: its controller (CR 701.21a; M21 Havoc Jester, end to end in the pack
  havoc_jester_sees_its_controller_sacrifice_a_stolen_creature);
* what a permanent enters with: "you" is the player it enters under;
* a selector's zone: the permanents the player controls.
"""

from __future__ import annotations

from MTG_bot.core.ability_tree import (
    Atom,
    AtomArgs,
    ControllerRef,
    CounterKind,
    CreatureDiesEvent,
    EtBState,
    FAnd,
    FAtom,
    FAtomPred,
    FNot,
    QCount,
    QConst,
    QUnbounded,
    ReplacementAbility,
    Selector,
    SelectorMode,
    TriggeredAbility,
    Verb,
    Zone,
    ZoneChangeEvent,
    ZoneKind,
)
from MTG_bot.core.executor.legality import ctx_for
from MTG_bot.core.executor.selectors import resolve_selector
from MTG_bot.core.state import ZONE_BATTLEFIELD, ZONE_EXILE, ZONE_GRAVEYARD
from MTG_bot.core.test_executor_binding import (
    ANY_ANY,
    BF_ANY,
    BF_YOU,
    CREATURE,
    IS_SOURCE,
    BindingCase,
    all_bf,
    atom,
    card_id,
    enter,
    etb_trigger,
    gain,
    record_of,
)

_EXILE_IT = Atom(verb=Verb.MOVE_ZONE, args=AtomArgs(pairs=(
    ("destination", Zone(ZoneKind.EXILE, ControllerRef.OWNER)),
    ("target", Selector(QConst(1), SelectorMode.CHOOSE, FAnd(()), zones=(ANY_ANY,), referent="event")),
)))
_YOUR_CREATURES = Selector(QUnbounded(), SelectorMode.ALL,
                           FAnd((CREATURE, FAtom(FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU))),
                           zones=(BF_ANY,))


class EntersUnderYourControl(BindingCase):
    def test_a_creature_returned_under_another_players_control_triggers_for_that_player(self):
        """p1's creature card, put onto the battlefield from p1's graveyard under p0's control:
        its "When this creature enters, you gain 3 life" is p0's, and p0 gains the life."""
        visitor = self.world.add_card(card_id("Visitor", "1", "1"), self.p1, ZONE_GRAVEYARD)
        oid = self.world.cards[visitor].identity.oracle_id
        self.ex.binder.records[oid] = record_of([etb_trigger(gain(3))], name="Visitor", oid=oid)
        self.ex.execute(enter(BF_YOU), source=self.watch, controller=self.p0, bindings={"cards": visitor})
        self.assertEqual(self.world.zone_of(visitor).kind, ZONE_BATTLEFIELD)
        self.assertEqual(self.ex.controller_of(visitor), self.p0)
        self.assertEqual(self.world.controller_of(visitor), self.p1)  # its owner's zone (CR 108.3)
        self.assertEqual((self.life(self.p0), self.life(self.p1)), (23, 20))

    def test_a_creature_returned_under_its_owners_control_still_triggers_for_its_owner(self):
        visitor = self.world.add_card(card_id("Visitor", "1", "1"), self.p1, ZONE_GRAVEYARD)
        oid = self.world.cards[visitor].identity.oracle_id
        self.ex.binder.records[oid] = record_of([etb_trigger(gain(3))], name="Visitor", oid=oid)
        owner_bf = Zone(ZoneKind.BATTLEFIELD, ControllerRef.OWNER)
        self.ex.execute(enter(owner_bf), source=self.watch, controller=self.p0, bindings={"cards": visitor})
        self.assertEqual(self.ex.controller_of(visitor), self.p1)
        self.assertEqual((self.life(self.p0), self.life(self.p1)), (20, 23))


class LeavesWhileYouControlIt(BindingCase):
    def _charm(self, owner):
        """An enchantment: "When this enchantment leaves the battlefield, you gain 3 life" (Nine
        Lives' trigger shape: from Zone(BATTLEFIELD, YOU), the source the subject)."""
        charm = self.world.add_card(card_id("Charm", type_line="Enchantment"), owner, ZONE_BATTLEFIELD)
        leaves = TriggeredAbility(
            event=ZoneChangeEvent(from_zone=BF_YOU, to_zone=ANY_ANY, subject=IS_SOURCE),
            condition=None,
            effect=gain(3),
        )
        self.ex.attach_card(charm, self.record_for(charm, [leaves], name="Charm"))
        return charm

    def _destroy(self, card):
        self.ex.execute(atom(Verb.DESTROY, target=all_bf()), source=self.watch, controller=self.p0,
                        bindings={"target": [card]})

    def test_the_player_who_controlled_it_as_it_left_is_you(self):
        charm = self._charm(self.p0)
        self.assertTrue(self.ex.gain_control(charm, self.p1, "Permanent"))
        self._destroy(charm)
        self.assertEqual(self.world.zone_of(charm).kind, ZONE_GRAVEYARD)
        self.assertEqual((self.life(self.p0), self.life(self.p1)), (20, 23))

    def test_its_owner_who_controls_it_is_you(self):
        charm = self._charm(self.p0)
        self._destroy(charm)
        self.assertEqual((self.life(self.p0), self.life(self.p1)), (23, 20))

    def test_another_creature_you_control_leaving_counts_for_its_controller(self):
        """"Whenever another creature you control leaves the battlefield, you gain 1 life", the
        "you control" in the zone alone: p1's creature p0 controls counts for p0, p0's creature p1
        controls does not."""
        self.attach_trigger(self.watch, ZoneChangeEvent(from_zone=BF_YOU, to_zone=ANY_ANY,
                                                        subject=FAnd((FNot(IS_SOURCE), CREATURE))), gain(1))
        stolen = self.world.add_card(card_id("Stolen", "2", "2"), self.p1, ZONE_BATTLEFIELD)
        lent = self.world.add_card(card_id("Lent", "2", "2"), self.p0, ZONE_BATTLEFIELD)
        self.ex.gain_control(stolen, self.p0, "Permanent")
        self.ex.gain_control(lent, self.p1, "Permanent")
        self._destroy(stolen)
        self.assertEqual(self.life(self.p0), 21)
        self._destroy(lent)
        self.assertEqual(self.life(self.p0), 21)


class LeavingWithWhatControlsIt(BindingCase):
    def test_a_creature_leaving_with_the_aura_that_steals_it_was_still_stolen(self):
        """p0's Aura gives p0 control of p1's creature ("You control enchanted creature"); one
        effect destroys both, the Aura's row first. The creature is read as it last existed on the
        battlefield (CR 603.10a), under p0's control: p0's "Whenever a creature you control dies,
        you gain 1 life" triggers."""
        aura = self.world.add_card(card_id("Theft", type_line="Enchantment — Aura"), self.p0, ZONE_BATTLEFIELD)
        creature = self.world.add_card(card_id("Victim", "2", "2"), self.p1, ZONE_BATTLEFIELD)
        self.ex.gain_control(creature, self.p0, "Permanent", aura)
        self.assertEqual(self.ex.controller_of(creature), self.p0)
        yours = FAnd((CREATURE, FAtom(FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU)))
        self.attach_trigger(self.watch, CreatureDiesEvent(filter=yours), gain(1))
        self.ex.execute(atom(Verb.DESTROY, target=all_bf()), source=self.watch, controller=self.p0,
                        bindings={"target": [aura, creature]})
        self.assertEqual(self.world.zone_of(creature).kind, ZONE_GRAVEYARD)
        self.assertEqual(self.ex.departed_lki[creature].controller, self.p0)
        self.assertEqual(self.life(self.p0), 21)


class ReplacementEndpoints(BindingCase):
    def _guard(self, event: ZoneChangeEvent) -> None:
        """p0's Watchdog: "If <event>, exile it instead"."""
        self.ex.attach_card(self.watch, self.record_for(
            self.watch, [ReplacementAbility(event=event, condition=None, action=_EXILE_IT)], name="Watchdog"))

    def test_a_creature_that_would_enter_under_an_opponents_control_is_exiled_instead(self):
        self._guard(ZoneChangeEvent(from_zone=ANY_ANY, to_zone=Zone(ZoneKind.BATTLEFIELD, ControllerRef.OPPONENT),
                                    subject=CREATURE))
        bear = self.world.add_card(card_id("Bear", "2", "2"), self.p0, ZONE_GRAVEYARD)
        self.ex.execute(enter(BF_YOU), source=bear, controller=self.p1, bindings={"cards": bear})  # p1 takes it
        self.assertEqual(self.world.zone_of(bear).kind, ZONE_EXILE)

    def test_a_creature_that_would_enter_under_your_control_is_not(self):
        self._guard(ZoneChangeEvent(from_zone=ANY_ANY, to_zone=Zone(ZoneKind.BATTLEFIELD, ControllerRef.OPPONENT),
                                    subject=CREATURE))
        bear = self.world.add_card(card_id("Bear", "2", "2"), self.p1, ZONE_GRAVEYARD)
        self.ex.execute(enter(BF_YOU), source=bear, controller=self.p0, bindings={"cards": bear})  # p0 takes it
        self.assertEqual(self.world.zone_of(bear).kind, ZONE_BATTLEFIELD)

    def test_a_creature_you_control_that_would_die_is_exiled_whoever_owns_it(self):
        """"If a creature you control would be put into a graveyard from the battlefield, exile it
        instead": p1's creature p0 controls is exiled, p0's creature p1 controls is not."""
        self._guard(ZoneChangeEvent(from_zone=BF_YOU, to_zone=Zone(ZoneKind.GRAVEYARD, ControllerRef.ANY),
                                    subject=CREATURE))
        stolen = self.world.add_card(card_id("Stolen", "2", "2"), self.p1, ZONE_BATTLEFIELD)
        lent = self.world.add_card(card_id("Lent", "2", "2"), self.p0, ZONE_BATTLEFIELD)
        self.ex.gain_control(stolen, self.p0, "Permanent")
        self.ex.gain_control(lent, self.p1, "Permanent")
        self.ex.execute(atom(Verb.DESTROY, target=all_bf()), source=self.watch, controller=self.p0,
                        bindings={"target": [stolen, lent]})
        self.assertEqual(self.world.zone_of(stolen).kind, ZONE_EXILE)
        self.assertEqual(self.world.zone_of(lent).kind, ZONE_GRAVEYARD)


class EntersWithUnderYourControl(BindingCase):
    def test_what_it_enters_with_counts_for_the_player_it_enters_under(self):
        """p1's creature card "enters with a +1/+1 counter for each creature you control", put onto
        the battlefield under p0's control: it counts p0's creatures, the Watchdog and itself."""
        card = self.world.add_card(card_id("Counter", "1", "1"), self.p1, ZONE_GRAVEYARD)
        oid = self.world.cards[card].identity.oracle_id
        state = EtBState(initial_counters=((CounterKind.PLUS_1_PLUS_1, QCount(_YOUR_CREATURES)),))
        self.ex.binder.records[oid] = record_of([state], name="Counter", oid=oid)
        self.ex.execute(enter(BF_YOU), source=self.watch, controller=self.p0, bindings={"cards": card})
        self.assertEqual(self.ex.controller_of(card), self.p0)
        self.assertEqual(dict(self.world.cards[card].counters), {"PLUS_1_PLUS_1": 2})


class YourBattlefield(BindingCase):
    def test_a_selector_over_your_battlefield_finds_the_permanents_you_control(self):
        stolen = self.world.add_card(card_id("Stolen", "2", "2"), self.p1, ZONE_BATTLEFIELD)
        lent = self.world.add_card(card_id("Lent", "2", "2"), self.p0, ZONE_BATTLEFIELD)
        self.ex.gain_control(stolen, self.p0, "Permanent")
        self.ex.gain_control(lent, self.p1, "Permanent")
        sel = Selector(QUnbounded(), SelectorMode.ALL, CREATURE, zones=(BF_YOU,))
        ctx = ctx_for(self.ex, source=self.watch, controller=self.p0)
        self.assertEqual(sorted(resolve_selector(sel, ctx)), sorted([self.watch, stolen]))
