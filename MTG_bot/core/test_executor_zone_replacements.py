"""Zone-change replacements from anywhere (CR 614.1a, 614.6), and dies replacements by any cause.

A replacement over a ZoneChangeEvent applies to the move it describes wherever the object is: FDN
Dryad Militant's "If an instant or sorcery card would be put into a graveyard from anywhere,
exile it instead" and M20 Leyline of the Void's "If a card would be put into an opponent's
graveyard from anywhere, exile it instead" catch a spell resolving, countered or left without
targets, a discard, a mill, a destroy, a sacrifice and a state-based death. A dies replacement
(Scorching Dragonfire's "If that creature would die this turn, exile it instead") applies to every
move from the battlefield to a graveyard (CR 700.4), not only the state-based one (BACKLOG B-72).
The move is replaced, so it never happens: the card is not in the graveyard, the record's action
moves it, and a replaced death is no death (no dies trigger).
"""

from __future__ import annotations

from dataclasses import replace

from MTG_bot.core.ability_tree import (
    Atom,
    AtomArgs,
    ControllerRef,
    Cost,
    CostManaColor,
    CreatureDiesEvent,
    FAnd,
    FAtom,
    FAtomPred,
    FNot,
    QConst,
    QProp,
    QPropField,
    ReplacementAbility,
    Selector,
    SelectorMode,
    Seq,
    SpellKind,
    TriggeredAbility,
    Verb,
    Zone,
    ZoneChangeEvent,
    ZoneKind,
)
from MTG_bot.core.executor.stack import cast
from MTG_bot.core.state import (
    ZONE_BATTLEFIELD,
    ZONE_EXILE,
    ZONE_GRAVEYARD,
    ZONE_HAND,
    ZONE_LIBRARY,
)
from MTG_bot.core.test_executor_rung1 import STACK_TARGET
from MTG_bot.core.test_executor_stack import (
    BF_ANY,
    INSTANT_OR_SORCERY,
    StackCase,
    any_target,
    atom,
)

_ANY = Zone(ZoneKind.ANY, ControllerRef.ANY)
_GY_YOU = Zone(ZoneKind.GRAVEYARD, ControllerRef.YOU)
_EXILE_IT = Atom(verb=Verb.MOVE_ZONE, args=AtomArgs(pairs=(
    ("destination", Zone(ZoneKind.EXILE, ControllerRef.OWNER)),
    ("target", Selector(QConst(1), SelectorMode.CHOOSE, FAnd(()), zones=(_ANY,), referent="event")),
)))


def _into_a_graveyard(subject, graveyard=ControllerRef.ANY) -> ReplacementAbility:
    """"If <subject> would be put into <whose> graveyard from anywhere, exile it instead."""
    return ReplacementAbility(
        event=ZoneChangeEvent(from_zone=_ANY, to_zone=Zone(ZoneKind.GRAVEYARD, graveyard),
                              subject=subject),
        condition=None,
        action=_EXILE_IT,
    )


MILITANT = _into_a_graveyard(INSTANT_OR_SORCERY)
LEYLINE = _into_a_graveyard(FNot(FAtom(FAtomPred.IS_TOKEN)), ControllerRef.OPPONENT)
_TARGET_CREATURE = Selector(QConst(1), SelectorMode.TARGET, FAtom(FAtomPred.TYPE_EQ, string_value="Creature"),
                            zones=(BF_ANY,))


class ZoneReplacementCase(StackCase):
    def permanent(self, name, replacement, seat=None):
        return self.give(name, SpellKind.CREATURE, zone=ZONE_BATTLEFIELD, type_line="Creature",
                         types=("Creature",), power="2", toughness="2", seat=seat,
                         extra_abilities=(replacement,))

    def creature(self, name, seat, toughness="2"):
        return self.give(name, SpellKind.CREATURE, zone=ZONE_BATTLEFIELD, type_line="Creature",
                         types=("Creature",), power="2", toughness=toughness, seat=seat)

    def sorcery(self, name, seat, effect=None, zone=ZONE_HAND):
        effect = effect or atom(Verb.GAIN_LIFE, controller=ControllerRef.YOU, amount=QConst(1))
        return self.give(name, SpellKind.SORCERY, effect=effect, seat=seat, zone=zone,
                         type_line="Sorcery", types=("Sorcery",))

    def zone(self, handle) -> str:
        return self.world.zone_of(handle).kind

    def do(self, effect, source, bindings, controller=None):
        self.ex.apply_effect(effect, source=source, controller=controller or self.p0, bindings=bindings)


class TestFromAnywhere(ZoneReplacementCase):
    def test_a_resolving_sorcery_is_exiled_instead(self) -> None:
        self.permanent("Militant", MILITANT)
        spell = self.sorcery("Musing", self.p0)
        cast(self.ex, self.p0, spell)
        self.assertEqual(self.world.players[self.p0].life, 21)  # it resolved first
        self.assertEqual(self.zone(spell), ZONE_EXILE)
        self.assertNotIn(("SPELL_PUT", str(spell), "stack->graveyard"),
                         [e[1:4] for e in self.ex.events])

    def test_a_countered_spell_is_exiled_instead(self) -> None:
        self.permanent("Militant", MILITANT)
        shock = self.shock()
        self.mana(self.p0, R=1)
        with self.ex.holding_priority():
            cast(self.ex, self.p0, shock, targets=(self.p1,))
        self.do(atom(Verb.COUNTER_SPELL, target=STACK_TARGET), shock, {"target": shock}, self.p1)
        self.assertEqual(self.zone(shock), ZONE_EXILE)
        self.assertEqual(self.ex.stack.frames, [])
        self.assertEqual(self.world.players[self.p1].life, 20)

    def test_a_spell_left_without_targets_is_exiled_instead(self) -> None:
        self.permanent("Militant", MILITANT)
        bear = self.creature("Bear", self.p1)
        bolt = self.give("Jab", SpellKind.INSTANT, cost=Cost((CostManaColor("R", QConst(1)),)),
                         effect=atom(Verb.DEAL_DAMAGE, target=_TARGET_CREATURE, amount=QConst(1)))
        self.mana(self.p0, R=1)
        with self.ex.holding_priority():
            cast(self.ex, self.p0, bolt, targets=(bear,))
        self.do(atom(Verb.MOVE_ZONE, target=any_target(), destination=Zone(ZoneKind.HAND, ControllerRef.OWNER)),
                 bear, {"target": bear})
        self.ex.fire_triggers()  # both pass: the bolt finds no legal target (CR 608.2b)
        self.assertEqual(self.zone(bear), ZONE_HAND)
        self.assertEqual(self.zone(bolt), ZONE_EXILE)

    def test_a_discard_is_exiled_instead_and_is_still_a_discard(self) -> None:
        """Leyline of the Void's ruling: the card is still discarded, so "then draw that many"
        draws one."""
        self.permanent("Leyline", LEYLINE)
        card = self.sorcery("Scrap", self.p1)
        hand = self.world.players[self.p1].zone(ZONE_HAND).entries
        discard = atom(Verb.MOVE_ZONE, cards=Selector(QConst(1), SelectorMode.CHOOSE, FAnd(()),
                                                      zones=(Zone(ZoneKind.HAND, ControllerRef.YOU),)),
                       controller=ControllerRef.YOU, destination=_GY_YOU,
                       **{"from": Zone(ZoneKind.HAND, ControllerRef.YOU)})
        draw_that_many = atom(Verb.DRAW, controller=ControllerRef.YOU,
                              amount=QProp(referent="event", field=QPropField.THAT_MANY_COUNT))
        self.do(Seq(steps=(discard, draw_that_many)), card, {"cards": [card]}, self.p1)
        self.assertEqual(self.zone(card), ZONE_EXILE)
        self.assertEqual(len(hand), 1)  # Scrap out, one card drawn

    def test_a_milled_card_is_exiled_instead(self) -> None:
        self.permanent("Militant", MILITANT)
        library = self.world.players[self.p0].zone(ZONE_LIBRARY).entries
        bear = self.creature("Bear Card", self.p0)
        instant = self.give("Quick", SpellKind.INSTANT, zone=ZONE_LIBRARY)
        self.world.move_to_zone(bear, self.p0, ZONE_LIBRARY)  # the top two: Quick, then Bear Card
        library.remove(instant)
        library.append(instant)
        mill_two = atom(Verb.MOVE_ZONE, controller=ControllerRef.YOU, amount=QConst(2),
                        destination=_GY_YOU, **{"from": Zone(ZoneKind.LIBRARY, ControllerRef.YOU),
                                                "journal_kind": "MILL", "pop_order": "TOP"})
        self.do(mill_two, instant, {})
        self.assertEqual((self.zone(instant), self.zone(bear)), (ZONE_EXILE, ZONE_GRAVEYARD))

    def test_a_destroyed_creature_is_exiled_and_does_not_die(self) -> None:
        """Into an opponent's graveyard: the Leyline's controller's own creature is not touched."""
        self.permanent("Leyline", LEYLINE)
        theirs, mine = self.creature("Theirs", self.p1), self.creature("Mine", self.p0)
        died: list[str] = []
        self.give("Watcher", SpellKind.CREATURE, zone=ZONE_BATTLEFIELD, type_line="Creature",
                  types=("Creature",), power="1", toughness="1", extra_abilities=(TriggeredAbility(
                      event=CreatureDiesEvent(FAnd(())), condition=None,
                      effect=atom(Verb.GAIN_LIFE, controller=ControllerRef.YOU, amount=QConst(1))),))
        for card in (theirs, mine):
            self.do(atom(Verb.DESTROY, target=_TARGET_CREATURE), card, {"target": card})
            died.append(self.zone(card))
        self.assertEqual(died, [ZONE_EXILE, ZONE_GRAVEYARD])
        self.assertEqual(self.world.players[self.p0].life, 21)  # one dies trigger: Mine's

    def test_a_sacrifice_and_a_lethal_damage_death_are_exiled_instead(self) -> None:
        self.permanent("Leyline", LEYLINE)
        fodder, target = self.creature("Fodder", self.p1), self.creature("Target", self.p1)
        self.do(atom(Verb.SACRIFICE, target=_TARGET_CREATURE), fodder, {"target": fodder}, self.p1)
        self.do(atom(Verb.DEAL_DAMAGE, target=_TARGET_CREATURE, amount=QConst(3)), target,
                 {"target": target})
        self.assertEqual((self.zone(fodder), self.zone(target)), (ZONE_EXILE, ZONE_EXILE))

    def test_a_token_is_no_card(self) -> None:
        """Leyline of the Void names cards: a token dies as usual (and then ceases to exist)."""
        self.permanent("Leyline", LEYLINE)
        token = self.creature("Spirit", self.p1)
        identity = self.world.cards[token].identity
        self.world.cards[token].identity = replace(identity, is_token=True)
        self.do(atom(Verb.DESTROY, target=_TARGET_CREATURE), token, {"target": token})
        self.assertNotIn(token, self.world.cards)  # put into the graveyard, then gone (CR 704.5d)


    def test_an_unattached_aura_is_exiled_instead(self) -> None:
        """The state-based put of an Aura attached to nothing (CR 704.5m) is a move from the
        battlefield to a graveyard like any other."""
        self.permanent("Leyline", LEYLINE)
        aura = self.give("Shackle", SpellKind.ENCHANTMENT, zone=ZONE_BATTLEFIELD, seat=self.p1,
                         type_line="Enchantment — Aura", types=("Enchantment",))
        identity = self.world.cards[aura].identity
        self.world.cards[aura].identity = replace(identity, keywords=("ENCHANT",))
        self.ex.fire_triggers()  # a priority check: the state-based actions
        self.assertEqual(self.zone(aura), ZONE_EXILE)


class TestAnyMove(ZoneReplacementCase):
    """Moves into other zones ask too: "If a creature would enter, exile it instead" (an enter
    replacement without Containment Priest's "and it wasn't cast")."""

    ENTER = ReplacementAbility(
        event=ZoneChangeEvent(from_zone=_ANY, to_zone=BF_ANY,
                              subject=FAtom(FAtomPred.TYPE_EQ, string_value="Creature")),
        condition=None,
        action=_EXILE_IT,
    )

    def test_a_cast_creatures_entry_is_replaced_and_it_never_enters(self) -> None:
        self.permanent("Warden", self.ENTER, seat=self.p1)
        bear = self.give("Bear", SpellKind.CREATURE, type_line="Creature", types=("Creature",),
                         power="2", toughness="2", extra_abilities=(TriggeredAbility(
                             event=ZoneChangeEvent(_ANY, Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU),
                                                   subject=FAtom(FAtomPred.IS_SOURCE)),
                             condition=None,
                             effect=atom(Verb.GAIN_LIFE, controller=ControllerRef.YOU, amount=QConst(3))),))
        cast(self.ex, self.p0, bear)
        self.assertEqual(self.zone(bear), ZONE_EXILE)
        self.assertEqual(self.world.players[self.p0].life, 20)  # it never entered: no trigger

    def test_a_searched_creature_is_exiled_instead_of_entering(self) -> None:
        self.permanent("Warden", self.ENTER, seat=self.p1)
        bear = self.creature("Bear Card", self.p0)
        self.world.move_to_zone(bear, self.p0, ZONE_LIBRARY)
        search = atom(Verb.SEARCH, destination=Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU),
                      cards=Selector(QConst(1), SelectorMode.CHOOSE,
                                     FAtom(FAtomPred.TYPE_EQ, string_value="Creature"),
                                     zones=(Zone(ZoneKind.LIBRARY, ControllerRef.YOU),)))
        self.do(search, bear, {"cards": [bear]})
        self.assertEqual(self.zone(bear), ZONE_EXILE)


class TestDiesByAnyCause(ZoneReplacementCase):
    """Scorching Dragonfire's replacement on its target, registered as the spell resolves."""

    def _dragonfire(self, victim) -> None:
        fire = self.give("Dragonfire", SpellKind.INSTANT, cost=Cost((CostManaColor("R", QConst(1)),)),
                         effect=atom(Verb.DEAL_DAMAGE, target=_TARGET_CREATURE, amount=QConst(1)),
                         extra_abilities=(ReplacementAbility(
                             event=CreatureDiesEvent(FAtom(FAtomPred.IS_ANY_TARGET)), condition=None,
                             action=_EXILE_IT),))
        self.mana(self.p0, R=1)
        cast(self.ex, self.p0, fire, targets=(victim,))
        self.assertEqual(self.zone(victim), ZONE_BATTLEFIELD)  # 1 damage: it survives

    def test_destroyed_after_the_damage_it_is_exiled(self) -> None:
        victim, other = self.creature("Victim", self.p1, "3"), self.creature("Other", self.p1, "3")
        self._dragonfire(victim)
        for card in (victim, other):
            self.do(atom(Verb.DESTROY, target=_TARGET_CREATURE), card, {"target": card})
        self.assertEqual((self.zone(victim), self.zone(other)), (ZONE_EXILE, ZONE_GRAVEYARD))

    def test_sacrificed_after_the_damage_it_is_exiled(self) -> None:
        victim = self.creature("Victim", self.p1, "3")
        self._dragonfire(victim)
        self.do(atom(Verb.SACRIFICE, target=_TARGET_CREATURE), victim, {"target": victim}, self.p1)
        self.assertEqual(self.zone(victim), ZONE_EXILE)
