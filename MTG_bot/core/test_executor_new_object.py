"""An ability names the object its source was (CR 113.7a, 400.7): engine wave W1, cause A
(KNOWLEDGE/2026-11-18/215 §5, faults F14, F14b and the riders F14c, F48, F50).

A resolving ability whose source has changed zones since it was activated or triggered (the
``gone`` register: ``TriggerBinder._source_gone``, ``legality.resolve_activated``) names an object
that no longer exists: no object is "this creature" (``quantity._eval_atom``'s IS_SOURCE), so the
new object is "another" creature, and the source's information, its chosen quality included, is
its last known information (CR 608.2h). The exceptions the rule keeps: an ability triggered by its
source's own move finds it in a public zone (CR 400.7d: ``TriggerBinder._gone``, E3's tests), an
Aura's leaves-the-battlefield ability finds the Aura in its owner's graveyard (CR 400.7e), and an
object the ability's cost moved is found (CR 400.7h). End to end: the packs of
``source_left_and_came_back_still_acted_on`` (Griffin Protector, Colossus Hammer, Watcher of the
Spheres), E3's ``scavenging_ooze_that_left_the_battlefield_gets_no_counter`` and the Angelic
Destiny packs.
"""

from __future__ import annotations

from dataclasses import replace

from MTG_bot.core.ability_tree import (
    ControllerRef,
    CostSacrifice,
    CostTap,
    CreatureDiesEvent,
    DamageDealtEvent,
    DeclareBlockersEvent,
    DurationEot,
    EtBState,
    FAnd,
    FAtom,
    FAtomPred,
    FNot,
    Keyword,
    KeywordAbility,
    LifeGainedEvent,
    PtDelta,
    PtDirection,
    QAgg,
    QConst,
    QProp,
    QPropField,
    QUnbounded,
    Selector,
    SelectorMode,
    Seq,
    StaticAbility,
    TriggeredAbility,
    Verb,
    Zone,
    ZoneChangeEvent,
    ZoneKind,
)
from MTG_bot.core.executor.legality import activate
from MTG_bot.core.state import (
    ZONE_BATTLEFIELD,
    ZONE_EXILE,
    ZONE_GRAVEYARD,
    ZONE_HAND,
)
from MTG_bot.core.test_executor_binding import (
    ANY_ANY,
    BF_ANY,
    BF_YOU,
    CREATURE,
    GY_ANY,
    IS_SOURCE,
    BindingCase,
    enter,
    gain,
    record_of,
    referent_sel,
)
from MTG_bot.core.test_executor_legality import LegalityCase, ability, cost
from MTG_bot.core.test_executor_verbs import UNIV, atom, card_id, target_sel

_YOU = FAtom(FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU)
_EXILE = Zone(ZoneKind.EXILE, ControllerRef.OWNER)
_BF_OWNER = Zone(ZoneKind.BATTLEFIELD, ControllerRef.OWNER)
_HAND_OWNER = Zone(ZoneKind.HAND, ControllerRef.OWNER)


def _pump(selector: Selector, n: int = 1):
    """"<selector> get(s) +n/+n until end of turn"."""
    delta = PtDelta(direction=PtDirection.INCREASE, magnitude=QConst(n))
    return atom(Verb.MODIFY_PT, target=selector, power=delta, toughness=delta, duration=DurationEot())


def _all(filter_) -> Selector:
    return Selector(QConst(1), SelectorMode.ALL, filter_, zones=(BF_ANY,))


class _SourceCase(BindingCase):
    def _creature(self, effect, name="Grower", type_line="Creature", also=()):
        """A 1/1 on p0's battlefield with "Whenever you gain life, <effect>" (and ``also``)."""
        card = self.world.add_card(card_id(name, "1", "1", type_line=type_line), self.p0, ZONE_BATTLEFIELD)
        oid = self.world.cards[card].identity.oracle_id
        record = record_of([*also, TriggeredAbility(LifeGainedEvent(_YOU), None, effect)], name=name, oid=oid)
        self.ex.binder.records[oid] = record
        self.ex.attach_card(card, record)
        return card

    def _move(self, cards, dest):
        self.ex.execute(enter(dest), source=self.watch, controller=self.p0, bindings={"cards": cards})

    def _flicker_while_it_waits(self, card):
        """Gain life (the trigger waits on the stack), then the creature leaves and comes back as a
        new object (CR 400.7); then everything resolves."""
        with self.ex.holding_priority():
            self.ex.execute(gain(2), source=self.watch, controller=self.p0)
            self._move(card, _EXILE)
            self._move(card, _BF_OWNER)
        self.ex.fire_triggers()
        self.assertEqual(self.world.zone_of(card).kind, ZONE_BATTLEFIELD)

    def pt(self, card):
        return self.ex.ledger.effective_pt(self.world.cards[card].identity, card)


class TheReturnedSourceIsAnotherObject(_SourceCase):
    def test_a_pump_of_this_creature_misses_the_new_object(self):
        """The unit twin of the Griffin Protector pack: "this creature gets +1/+1"."""
        grower = self._creature(_pump(Selector(QConst(1), SelectorMode.CHOOSE, IS_SOURCE, zones=(BF_ANY,))))
        self._flicker_while_it_waits(grower)
        self.assertEqual(self.pt(grower), (1, 1))

    def test_the_new_object_is_another_creature(self):
        """"Other creatures you control get +1/+1" (Syr Alin's shape): the creature back on the
        battlefield is not the object the ability names, so it is one of the others. Before W1 the
        handle passed IS_SOURCE and the new object was left out."""
        grower = self._creature(_pump(_all(FAnd((FNot(IS_SOURCE), CREATURE, _YOU)))))
        self._flicker_while_it_waits(grower)
        self.assertEqual(self.pt(grower), (2, 2))
        self.assertEqual(self.pt(self.watch), (3, 3))

    def test_its_power_is_its_last_known_power(self):
        """"Each opponent loses life equal to this creature's power": the source was a 4/4 as it
        left (+3/+3 until end of turn); the new object is a 1/1 (CR 608.2h)."""
        loses = atom(
            Verb.LOSE_LIFE,
            controller=ControllerRef.OPPONENT,
            amount=QProp(referent="source", field=QPropField.POWER, agg=QAgg.FIRST),
        )
        grower = self._creature(loses)
        self.ex.execute(_pump(target_sel(), 3), source=self.watch, controller=self.p0,
                        bindings={"target": [grower]})
        self.assertEqual(self.pt(grower), (4, 4))
        self._flicker_while_it_waits(grower)
        self.assertEqual(self.pt(grower), (1, 1))
        self.assertEqual(self.life(self.p1), 16)

    def test_its_chosen_quality_is_the_old_objects(self):
        """F14b (Icon of Ancestry's shape): "creatures of the chosen type get +1/+1". The source
        chose Elf; it leaves and comes back choosing Goblin while the ability waits: the ability
        reads the Elf choice of the object it names (CR 400.7, 608.2h)."""
        chosen = FAtom(FAtomPred.NAME_CHOSEN, string_value="CREATURE_TYPE")
        choose = EtBState(effect=atom(Verb.CHOOSE_NAME, quality="CREATURE_TYPE"))
        grower = self._creature(_pump(_all(FAnd((CREATURE, chosen)))), type_line="Creature — Shaman",
                                also=(choose,))
        elf = self.world.add_card(card_id("Elf", "1", "1", type_line="Creature — Elf"), self.p0, ZONE_BATTLEFIELD)
        goblin = self.world.add_card(card_id("Goblin", "1", "1", type_line="Creature — Goblin"), self.p0,
                                     ZONE_BATTLEFIELD)
        self.ex.name_choices[(grower, "CREATURE_TYPE")] = "Elf"  # chosen as it entered, before the test
        self.ex.decisions.provider = lambda vocab, what: "Goblin" if "Goblin" in vocab else vocab[0]
        self._flicker_while_it_waits(grower)
        self.assertEqual(self.ex.name_choices[(grower, "CREATURE_TYPE")], "Goblin")  # the new object's
        self.assertEqual((self.pt(elf), self.pt(goblin)), ((2, 2), (1, 1)))


class AnAurasHostIsTheOneItHadAsItLeft(_SourceCase):
    def test_tap_enchanted_creature_after_the_aura_came_back_on_another(self):
        """F14b's information half for an Aura (Sleep Paralysis, Capture Sphere): "When this Aura
        enters, tap enchanted creature" waits; the Aura leaves and comes back enchanting another
        creature. The waiting ability's "enchanted creature" is the one the Aura it names enchanted
        as it left (CR 400.7, 608.2h), so both creatures end tapped (the new Aura's own trigger
        taps the second). Before W1 the old trigger read the new object's host and tapped it
        again."""
        identity = replace(card_id("Paralysis", type_line="Enchantment — Aura"), keywords=("ENCHANT",))
        aura = self.world.add_card(identity, self.p0, ZONE_HAND)
        enchanted = Selector(QConst(1), SelectorMode.ALL, FAtom(FAtomPred.IS_ATTACHED_TO_SOURCE), zones=(BF_ANY,))
        enters = TriggeredAbility(ZoneChangeEvent(from_zone=ANY_ANY, to_zone=BF_YOU, subject=IS_SOURCE), None,
                                  atom(Verb.TAP, target=enchanted))
        record = replace(record_of([enters], name="Paralysis", oid=identity.oracle_id),
                         type_line="Enchantment — Aura", types=("Enchantment",), subtypes=("Aura",),
                         keywords=(KeywordAbility(keyword=Keyword.ENCHANT, params=(CREATURE,)),),
                         power=None, toughness=None)
        self.ex.binder.records[identity.oracle_id] = record
        self.ex.attach_card(aura, record)
        first = self.world.add_card(card_id("First", "2", "2"), self.p1, ZONE_BATTLEFIELD)
        second = self.world.add_card(card_id("Second", "2", "2"), self.p1, ZONE_BATTLEFIELD)
        hosts = [first, second]
        self.ex.decisions.provider = lambda vocab, what: str(hosts.pop(0)) if what.startswith("enchant:") else vocab[0]
        with self.ex.holding_priority():
            for dest in (_BF_OWNER, _EXILE, _BF_OWNER):  # enchants First; leaves; enchants Second
                self._move(aura, dest)
                self.ex._priority_check()  # a player receives priority between the ops (CR 117.5)
            self.assertEqual(len(self.ex.stack.frames), 2)  # both triggers wait
        self.ex.fire_triggers()
        self.assertEqual(self.ex.attachments.get(aura), second)
        self.assertEqual((self.world.cards[first].tapped, self.world.cards[second].tapped), (True, True))


class WhatTheResolutionChoosesAndRegisters(_SourceCase):
    """The fresh-eyes review of W1: a gone source's own choice, records judged after the
    resolution, and a new object's records judged during it."""

    def test_a_lockbox_destroyed_in_response_reads_the_name_it_chooses_now(self):
        """Diviner's Lockbox, Disenchanted while its ability waits, an earlier activation of the
        same Lockbox having named "Nope": the ability's chosen name is the one it chooses as it
        resolves (ExecCtx.chosen), not the departed object's old choice, and it draws three. The
        pack diviners_lockbox_disenchanted_in_response_still_draws plays it without the old name."""
        import json
        from pathlib import Path

        from MTG_bot.core.executor.games import get_supply
        from tools.run_scenarios import ScenarioRunner, _Lanes

        path = Path(__file__).resolve().parents[2] / "tools/scenarios/diviners_lockbox_disenchanted_in_response_still_draws.json"
        pack = json.loads(path.read_text())
        pack["expect"] = _Lanes(pack["expect"])
        runner = ScenarioRunner(pack, get_supply("all", pack["set"]))
        runner.ex.name_choices[(runner.handles["box"], None)] = "Nope"
        for step in pack["steps"]:
            runner.run_step(step)
        self.assertEqual(runner.check() + runner.unoffered, [])

    def test_this_creature_cant_be_blocked_of_a_gone_source_makes_no_record(self):
        """Frilled Sea Serpent's "this creature can't be blocked this turn", its source destroyed
        and Brought Back while it waited: the record would be judged at the block, outside this
        resolution, where the new object passes IS_SOURCE; so none is made (CR 400.7)."""
        unblockable = atom(Verb.PREVENT_EFFECT, condition=IS_SOURCE, duration=DurationEot(),
                           event=DeclareBlockersEvent(filter=IS_SOURCE))
        before = len(self.ex.replacements.preventions)
        self.ex.apply_effect(unblockable, source=self.watch, controller=self.p0, bindings={"gone": [self.watch]})
        self.assertEqual(len(self.ex.replacements.preventions), before)
        self.ex.apply_effect(unblockable, source=self.watch, controller=self.p0)  # the control
        self.assertEqual(len(self.ex.replacements.preventions), before + 1)

    def test_a_new_objects_own_prevention_holds_while_an_old_ability_of_its_card_resolves(self):
        """"Prevent all damage that would be dealt to this creature" of the object now on the
        battlefield is judged with that object as its source, whatever the resolving ability's
        gone register says about the card's older object (replacements._record_ctx)."""
        prevent = StaticAbility(effect=atom(Verb.PREVENT_EFFECT, condition=IS_SOURCE,
                                            event=DamageDealtEvent(amount=QUnbounded(), filter=IS_SOURCE)))
        oid = self.world.cards[self.watch].identity.oracle_id
        self.ex.attach_card(self.watch, record_of([prevent], oid=oid))
        resolving = self.ex._ctx(source=self.watch, controller=self.p0, bindings={"gone": [self.watch]},
                                 decisions=())
        self.assertIsNotNone(self.ex.replacements.prevented_card_damage(resolving, self.watch, combat=False))

    def test_that_creatures_power_is_its_last_known_once_it_came_back(self):
        """Terror of the Peaks' shape: "whenever another creature you control enters, each opponent
        loses life equal to that creature's power". The creature is pumped to 5/5, then flickered
        while the trigger waits: "that creature" is the object that entered, read as it last
        existed (CR 400.7, 608.2h), not the 2/2 back on the battlefield."""
        loses = atom(Verb.LOSE_LIFE, controller=ControllerRef.OPPONENT,
                     amount=QProp(referent="event", field=QPropField.POWER, agg=QAgg.FIRST))
        enters = ZoneChangeEvent(from_zone=ANY_ANY, to_zone=BF_YOU, subject=FAnd((FNot(IS_SOURCE), CREATURE)))
        oid = self.world.cards[self.watch].identity.oracle_id
        self.ex.attach_card(self.watch, record_of([TriggeredAbility(enters, None, loses)], oid=oid))
        bear = self.world.add_card(card_id("Bear", "2", "2"), self.p0, ZONE_HAND)
        with self.ex.holding_priority():
            self._move(bear, _BF_OWNER)
            self.ex._priority_check()  # its trigger goes on the stack and waits (CR 117.5)
            self.ex.execute(_pump(target_sel(), 3), source=self.watch, controller=self.p0,
                            bindings={"target": [bear]})
            for dest in (_EXILE, _BF_OWNER):
                self._move(bear, dest)
                self.ex._priority_check()
        self.ex.fire_triggers()
        self.assertEqual(self.pt(bear), (2, 2))
        self.assertEqual(self.life(self.p1), 20 - 5 - 2)  # the old object's 5, then the new one's own trigger: 2


class AnActivatedAbilityNamesItsSource(LegalityCase):
    def test_this_creature_does_not_fight_once_it_came_back(self):
        """"{T}: This creature fights target creature" (Brash Taunter's shape), the creature
        flickered in response: the new object does not fight (CR 400.7, 701.12b)."""
        self.attach([ability(cost(CostTap()), effect=atom(Verb.FIGHT, target=target_sel()))])
        with self.ex.holding_priority():
            activate(self.ex, self.alpha, 0, seat=self.p0, targets=[self.beta])
            for dest in (_EXILE, _BF_OWNER):
                self.ex.execute(enter(dest), source=self.beta, controller=self.p1,
                                bindings={"cards": [self.alpha]})
        self.ex.fire_triggers()
        self.assertEqual(self.world.zone_of(self.beta).kind, ZONE_BATTLEFIELD)
        self.assertNotIn(self.beta, self.ex.damage)

    def test_an_object_its_cost_moved_is_found(self):
        """CR 400.7h: "Sacrifice this creature: return it from your graveyard to your hand" finds
        the card its cost put into the graveyard (the activation's moment comes after its costs)."""
        sacrifice = CostSacrifice(Selector(QConst(1), SelectorMode.CHOOSE, IS_SOURCE, zones=(BF_YOU,)))
        back = atom(Verb.MOVE_ZONE, cards=Selector(QConst(1), SelectorMode.CHOOSE, IS_SOURCE, zones=(GY_ANY,)),
                    destination=_HAND_OWNER)
        self.attach([ability(cost(sacrifice), effect=back)])
        activate(self.ex, self.alpha, 0, seat=self.p0)
        self.assertEqual(self.world.zone_of(self.alpha).kind, ZONE_HAND)


class AnAurasLeaveAbilityFindsTheAura(_SourceCase):
    """CR 400.7e: "When enchanted creature dies, return this card to its owner's hand" (FDN
    Angelic Destiny) finds the Aura in its owner's graveyard, put there with the creature or as
    the state-based action for an unattached Aura (704.5m); not once it moved again."""

    def setUp(self):
        super().setUp()
        identity = replace(card_id("Destiny", type_line="Enchantment — Aura"), keywords=("ENCHANT",))
        self.aura = self.world.add_card(identity, self.p0, ZONE_BATTLEFIELD)
        back = atom(Verb.MOVE_ZONE, cards=Selector(QConst(1), SelectorMode.CHOOSE, IS_SOURCE, zones=(GY_ANY,)),
                    destination=_HAND_OWNER)
        dies = TriggeredAbility(CreatureDiesEvent(filter=FAtom(FAtomPred.IS_ATTACHED_TO_SOURCE)), None, back)
        record = replace(record_of([dies], name="Destiny", oid=identity.oracle_id),
                         type_line="Enchantment — Aura", types=("Enchantment",), subtypes=("Aura",),
                         power=None, toughness=None)
        self.ex.binder.records[identity.oracle_id] = record
        self.ex.attach_card(self.aura, record)
        self.ex.attach_aura(self.aura, self.watch)

    def _destroy(self, cards):
        self.ex.execute(atom(Verb.DESTROY, target=target_sel(UNIV)), source=self.watch,
                        controller=self.p1, bindings={"target": cards})

    def test_put_into_the_graveyard_as_an_unattached_aura(self):
        self._destroy([self.watch])
        self.assertEqual(self.world.zone_of(self.aura).kind, ZONE_HAND)

    def test_put_into_the_graveyard_with_its_creature(self):
        self._destroy([self.watch, self.aura])
        self.assertEqual(self.world.zone_of(self.aura).kind, ZONE_HAND)

    def test_moved_again_it_is_a_new_object(self):
        with self.ex.holding_priority():
            self._destroy([self.watch, self.aura])
            self._move(self.aura, _EXILE)
        self.ex.fire_triggers()
        self.assertEqual(self.world.zone_of(self.aura).kind, ZONE_EXILE)


class ALeaveTriggerReadsTheObjectAsItLeft(_SourceCase):
    def test_a_flicker_in_one_resolution_keeps_the_last_known_information(self):
        """F14c: a creature exiled and returned by two instructions of one resolution left as a
        flyer (flying until end of turn); "whenever a creature with flying you control leaves the
        battlefield" looks back at it (CR 603.10a) and triggers, though the new object has no
        flying. Closed since E1's third review (85dd1bfa: the snapshot survives the return);
        pinned here."""
        flyer = FAnd((CREATURE, _YOU, FAtom(FAtomPred.KEYWORD_HAS, keyword=Keyword.FLYING)))
        leaves = ZoneChangeEvent(from_zone=BF_YOU, to_zone=ANY_ANY, subject=flyer)
        oid = self.world.cards[self.watch].identity.oracle_id
        self.ex.attach_card(self.watch, record_of([TriggeredAbility(leaves, None, gain(1))], oid=oid))
        bear = self.world.add_card(card_id("Bear", "2", "2"), self.p0, ZONE_BATTLEFIELD)
        grant = atom(Verb.GRANT_ABILITY, target=target_sel(), ability=KeywordAbility(keyword=Keyword.FLYING),
                     duration=DurationEot())
        self.ex.execute(grant, source=self.watch, controller=self.p0, bindings={"target": [bear]})
        flicker = Seq(steps=(
            atom(Verb.MOVE_ZONE, cards=target_sel(UNIV), destination=_EXILE),
            atom(Verb.MOVE_ZONE, cards=referent_sel("result"), destination=_BF_OWNER),
        ))
        self.ex.apply_effect(flicker, source=self.watch, controller=self.p0, bindings={"cards": [bear]})
        self.ex.fire_triggers()
        self.assertEqual(self.world.zone_of(bear).kind, ZONE_BATTLEFIELD)
        self.assertFalse(self.ex.layers.keyword_of(bear, Keyword.FLYING))
        self.assertEqual(self.life(self.p0), 21)


class ATokenThatLeftStaysWhereItIs(_SourceCase):
    def test_exile_it_then_return_it_leaves_a_token_in_exile(self):
        """F48, CR 111.8: "exile it, then return it to the battlefield" of a token: the token can't
        come back; it stays in exile and ceases to exist at the next state-based check (704.5d)."""
        token = self.world.add_card(replace(card_id("Soldier", "1", "1"), is_token=True), self.p0,
                                    ZONE_BATTLEFIELD)
        flicker = Seq(steps=(
            atom(Verb.MOVE_ZONE, cards=target_sel(UNIV), destination=_EXILE),
            atom(Verb.MOVE_ZONE, cards=referent_sel("result"), destination=_BF_OWNER),
        ))
        self.ex.apply_effect(flicker, source=self.watch, controller=self.p0, bindings={"cards": [token]})
        self.ex.fire_triggers()
        self.assertNotIn(token, self.world.cards)
        self.assertFalse([r for r in self.ex.journal.events
                          if r.subject == token and r.kind == "ZONE_CHANGE" and r.zone_move[1] == ZONE_BATTLEFIELD])


class DamageToAnObjectThatLeft(_SourceCase):
    def test_a_creature_moved_earlier_in_the_resolution_is_dealt_no_damage(self):
        """F50, CR 120.1a, 400.7, 608.2b: "destroy it, then deal 3 damage to it": the card in the
        graveyard is no creature and is dealt none (no mark, no DAMAGE row)."""
        bear = self.world.add_card(card_id("Bear", "2", "2"), self.p1, ZONE_BATTLEFIELD)
        burn = Seq(steps=(
            atom(Verb.DESTROY, target=target_sel(UNIV)),
            atom(Verb.DEAL_DAMAGE, target=referent_sel("target"), amount=QConst(3)),
        ))
        self.ex.apply_effect(burn, source=self.watch, controller=self.p0, bindings={"target": [bear]})
        self.assertEqual(self.world.zone_of(bear).kind, ZONE_GRAVEYARD)
        self.assertNotIn(bear, self.ex.damage)
        self.assertFalse([r for r in self.ex.journal.events if r.subject == bear and r.kind == "DAMAGE"])
