"""One event at a time (2026-11-13): the rules faults of docs/BACKLOG.md "Triggers, events and the
journal" that ontology round R10 found, fixed in the binder and the journal with no IR change.

- Permanents moved by one event see each other's moves (CR 603.6a, 603.10a): the binder matches an
  event's rows together (``TriggerBinder.on_events``), its look-back triggers (``looks_back``)
  against what existed before it, every other trigger against what exists after it; a
  graveyard-functioning ability does not look back onto the battlefield (CR 113.6m), and a dies
  trigger that moves its own card looks back from the battlefield.
- The layers are brought up to date before the triggers that do not look back are matched (CR
  603.10: an anthem's bonus on a creature that just entered); the departed objects are read by
  their last known information, so a later event of the same drain still sees them as they were.
- A trigger's "it" is the object its event named only while that object has not changed zones
  since (CR 400.7, ``TriggerBinder._gone``); a read of its information finds it as it last
  existed (CR 608.2h).
- One instruction every player performs through EachPlayer is one event (CR 101.4), and so is a
  state-based check with the exile that replaced one of its deaths (CR 614.6, 704.3); an object
  an "until" effect returns comes back after the whole event (CR 610.3).

Every test here fails on the base, 891113a2, except the ones named controls, which pin what the
base already did right and the new code must keep.
"""

from __future__ import annotations

import pytest

from MTG_bot.core import ability_tree as at
from MTG_bot.core.ability_tree import (
    ControllerRef,
    CreatureDiesEvent,
    FAnd,
    FAtom,
    FAtomPred,
    FNot,
    Keyword,
    QConst,
    QProp,
    QPropField,
    TriggeredAbility,
    Verb,
    Zone,
    ZoneChangeEvent,
    ZoneKind,
)
from MTG_bot.core.executor.binding import functions_from_graveyard
from MTG_bot.core.executor.decisions import in_trigger_order
from MTG_bot.core.executor.events import (
    KIND_CARD_DRAWN,
    KIND_LIFE_GAINED,
    KIND_ZONE_CHANGE,
    GameEvent,
)
from MTG_bot.core.executor.games import get_supply
from MTG_bot.core.state import (
    ZONE_BATTLEFIELD,
    ZONE_EXILE,
    ZONE_GRAVEYARD,
    ZONE_HAND,
    ZONE_LIBRARY,
)
from MTG_bot.core.test_executor_binding import BindingCase, atom, card_id, record_of
from tools.run_scenarios import ScenarioRunner

YOU = ControllerRef.YOU
CREATURE = FAtom(FAtomPred.TYPE_EQ, string_value="Creature")
SELF = FAtom(FAtomPred.IS_SOURCE)
YOU_ARE = FAtom(FAtomPred.CONTROLLER_IS, who=YOU)
OTHER_OF_YOURS = FAnd((CREATURE, FNot(SELF), YOU_ARE))
ANY = Zone(ZoneKind.ANY, ControllerRef.ANY)
BF_YOU = Zone(ZoneKind.BATTLEFIELD, YOU)
EVERY = at.Selector(QConst(9), at.SelectorMode.ALL, FAnd(()), zones=(ANY,))
THAT_MANY = QProp(referent="event", field=QPropField.THAT_MANY_COUNT)
ONE = QConst(1)


def _gain(amount=ONE) -> at.Atom:
    return atom(Verb.GAIN_LIFE, controller=YOU, amount=amount)


def _move(destination: Zone) -> at.Atom:
    """One instruction, one atom boundary: the objects bound under ``cards`` go to ``destination``."""
    return atom(Verb.MOVE_ZONE, cards=EVERY, destination=destination)


ENTERS = ZoneChangeEvent(ANY, BF_YOU, OTHER_OF_YOURS)
LEAVES = ZoneChangeEvent(BF_YOU, ANY, OTHER_OF_YOURS)
DIES = CreatureDiesEvent(filter=OTHER_OF_YOURS)


def _runner(code: str, cards: list[dict]) -> ScenarioRunner:
    pack = {"set": code, "world": {"life": 20, "seed": 7}, "cards": cards, "steps": []}
    return ScenarioRunner(pack, get_supply("all", code))


def _real(key: str, name: str, seat: int = 0, zone: str = "battlefield") -> dict:
    return {"key": key, "real": name, "zone": zone, "controller": seat}


def _creature(key: str, p: str = "2", t: str = "2", seat: int = 0, zone: str = "battlefield") -> dict:
    return {"key": key, "name": key.title(), "type": "Creature — Bear", "power": p,
            "toughness": t, "zone": zone, "controller": seat}


def _held(ex, *steps) -> None:
    """Run ``steps`` (callables) while the triggers they cause wait, as in response to them."""
    ex.binder.hold = True
    try:
        for step in steps:
            step()
    finally:
        ex.binder.hold = False


class _Case(BindingCase):
    def creatures(self, n: int, abilities, zone=ZONE_BATTLEFIELD, player=None) -> list:
        """``n`` 2/2 creatures carrying ``abilities``, on the battlefield (attached) or elsewhere
        (bound by oracle id, as a dealt game binds a card that is not there yet)."""
        out = []
        for i in range(n):
            h = self.world.add_card(card_id(f"Bear{len(self.world.cards)}{i}", "2", "2"),
                                    player or self.p0, zone)
            rec = record_of(abilities, oid=self.world.cards[h].identity.oracle_id)
            if zone == ZONE_BATTLEFIELD:
                self.ex.attach_card(h, rec)
            else:
                self.ex.binder.records[rec.oracle_id] = rec
            out.append(h)
        return out

    def gains(self, player=None) -> list[int]:
        return [e.data[0] for e in self.ex.journal.events
                if e.kind == KIND_LIFE_GAINED and e.subject == (player or self.p0)]

    def one_boundary(self, *moves: tuple) -> None:
        """One atom boundary moving each (card, zone kind) given, as one event (two moves no verb
        makes at once: an object leaves while another arrives), then the settle."""
        before = self.ex.journal.snapshot()
        for card, kind in moves:
            self.world.move_to_zone(card, self.world.controller_of(card), kind)
        rows = self.ex.journal.record_atom(before, None, "TEST", [])
        self.ex._on_zone_changes(rows)
        self.ex.fire_triggers()


# ------------------------------------------------------- CR 603.6a, 603.10a: one event, together


class TestOneEventMovesTogether(_Case):
    def test_creatures_dying_at_once_each_see_the_other_die(self) -> None:
        """CR 603.10a: leaves-the-battlefield abilities look back. Two creatures with "whenever
        another creature you control dies, you gain 1 life" die to one DESTROY: each sees the
        other, 2 life (the base: 1, the second's trigger was detached with the first's row)."""
        pair = self.creatures(2, [TriggeredAbility(DIES, None, _gain())])
        self.ex.decisions.provider = in_trigger_order
        self.ex.execute(atom(Verb.DESTROY, target=EVERY), source=pair[0], controller=self.p0,
                        bindings={"target": pair})
        assert self.gains() == [1, 1]

    def test_creatures_entering_at_once_each_see_the_other_enter(self) -> None:
        """CR 603.6a: every permanent on the battlefield after the event, the newcomers included,
        is checked. Two creatures with "whenever another creature you control enters, you gain 1
        life" enter in one MOVE_ZONE: 2 life (the base: 1)."""
        pair = self.creatures(2, [TriggeredAbility(ENTERS, None, _gain())], zone=ZONE_HAND)
        self.ex.decisions.provider = in_trigger_order
        self.ex.execute(_move(BF_YOU), source=pair[0], controller=self.p0, bindings={"cards": pair})
        assert self.gains() == [1, 1]

    def test_a_holder_leaving_with_them_counts_them(self) -> None:
        """Gate round 10's MINOR-2: one DESTROY of the Watchdog, which holds "whenever one or more
        other creatures you control leave the battlefield, you gain that much life", and three
        creatures. CR 603.10a: one trigger, counting 3 (the base: none, the Watchdog's own row
        came first and detached it)."""
        self.ex.attach_card(self.watch, self.record_for(self.watch, [
            TriggeredAbility(LEAVES, None, _gain(THAT_MANY), once_per_event=True)]))
        bears = self.creatures(3, [])
        everyone = at.Selector(at.QUnbounded(), at.SelectorMode.ALL, CREATURE,
                               zones=(Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),))
        self.ex.execute(atom(Verb.DESTROY, target=everyone), source=bears[0], controller=self.p1)
        assert self.gains() == [3]

    def test_a_permanent_that_leaves_does_not_see_what_enters_with_it(self) -> None:
        """CR 603.10: a trigger that does not look back is checked against what exists after the
        event, and the permanent that left is not there: "whenever another creature you control
        enters" on a creature that leaves as another enters, in one event, does not trigger (the
        base: it did, the newcomer's row came first)."""
        [leaver] = self.creatures(1, [TriggeredAbility(ENTERS, None, _gain())])
        [newcomer] = self.creatures(1, [], zone=ZONE_HAND)
        self.one_boundary((leaver, ZONE_GRAVEYARD), (newcomer, ZONE_BATTLEFIELD))
        assert self.gains() == []

    def test_a_permanent_that_enters_does_not_see_what_leaves_with_it(self, bound_early=False) -> None:
        """CR 603.10a: a leaves-the-battlefield trigger uses the abilities that existed before the
        event, and the newcomer's did not: its "whenever another creature you control leaves the
        battlefield" does not see a creature that leaves as it enters (the base: it did)."""
        [leaver] = self.creatures(1, [])
        [newcomer] = self.creatures(1, [TriggeredAbility(LEAVES, None, _gain())], zone=ZONE_HAND)
        if bound_early:
            rec = self.ex.binder.records[self.world.cards[newcomer].identity.oracle_id]
            self.ex.attach_card(newcomer, rec)
        self.one_boundary((leaver, ZONE_GRAVEYARD), (newcomer, ZONE_BATTLEFIELD))
        assert self.gains() == []

    def test_a_newcomer_bound_before_its_row_does_not_see_what_leaves_with_it(self) -> None:
        """The same when the newcomer is bound before its row is matched, as a permanent spell or a
        land is as it is put onto the battlefield (``stack.cast``, ``stack.play_land``)."""
        self.test_a_permanent_that_enters_does_not_see_what_leaves_with_it(bound_early=True)

    def test_a_stolen_creature_looks_back_as_the_controller_it_had(self) -> None:
        """CR 603.3a, 603.10a: the player who controlled a leaves-the-battlefield ability's source
        as it left controls the trigger. A creature of yours that the opponent controls, with
        "whenever another creature you control dies, you gain 1 life", dies with one of the
        opponent's creatures in one DESTROY: the opponent gains 1 (the base: nothing, it read the
        creature in your graveyard as yours, after the other's row)."""
        [stolen] = self.creatures(1, [TriggeredAbility(DIES, None, _gain())])
        [theirs] = self.creatures(1, [], player=self.p1)
        self.ex.gain_control(stolen, self.p1, "Permanent")
        assert self.ex.controller_of(stolen) == self.p1
        self.ex.execute(atom(Verb.DESTROY, target=EVERY), source=theirs, controller=self.p1,
                        bindings={"target": [stolen, theirs]})
        assert self.gains(self.p1) == [1] and self.gains(self.p0) == []


@pytest.mark.parametrize(
    ("node", "row", "back"),
    [
        (DIES, (ZONE_BATTLEFIELD, ZONE_GRAVEYARD), True),
        (at.SacrificeEvent(actor=YOU_ARE), (ZONE_BATTLEFIELD, ZONE_GRAVEYARD), True),
        (LEAVES, (ZONE_BATTLEFIELD, ZONE_EXILE), True),
        (ZoneChangeEvent(Zone(ZoneKind.GRAVEYARD, YOU), ANY), (ZONE_GRAVEYARD, ZONE_EXILE), True),
        # CR 603.6c: "from anywhere" is never a leaves-the-battlefield ability
        (ZoneChangeEvent(ANY, Zone(ZoneKind.GRAVEYARD, YOU)), (ZONE_BATTLEFIELD, ZONE_GRAVEYARD), False),
        # an object all players can see put into a hand looks back; a card from a library is not one
        (ZoneChangeEvent(ANY, Zone(ZoneKind.HAND, YOU)), (ZONE_BATTLEFIELD, ZONE_HAND), True),
        (ZoneChangeEvent(ANY, Zone(ZoneKind.HAND, YOU)), (ZONE_LIBRARY, ZONE_HAND), False),
        (ENTERS, (ZONE_HAND, ZONE_BATTLEFIELD), False),
        # an enters ability is checked after the event, from a graveyard too (CR 603.6a)
        (ZoneChangeEvent(Zone(ZoneKind.GRAVEYARD, YOU), BF_YOU), (ZONE_GRAVEYARD, ZONE_BATTLEFIELD),
         False),
    ],
)
def test_which_triggers_look_back(node, row, back) -> None:
    """CR 603.10a's list, row by row (``binding.looks_back``)."""
    from MTG_bot.core.executor.binding import looks_back
    from MTG_bot.core.identity import Handle

    seat = Handle("player", 0)
    event = GameEvent(5, KIND_ZONE_CHANGE, Handle("card", 9), None, "TEST", (*row, seat, seat), 5)
    assert looks_back(node, event) is back


def test_a_dies_trigger_that_moves_its_card_functions_on_the_battlefield() -> None:
    """CR 113.6m: an ability whose effect moves its own card out of a zone functions only there,
    "unless its trigger condition ... specifies that the object is put into that zone". The
    three M20 dies triggers that move their own card from the graveyard (Immortal Phoenix,
    Cavalier of Gales, Cavalier of Thorns) are bound on the battlefield and look back at their
    death (the base bound them in the graveyard as it died, which only its row order made
    work). A Phoenix dying beside another creature still returns."""
    r = _runner("M20", [_real("phoenix", "Immortal Phoenix"), _real("gales", "Cavalier of Gales"),
                        _real("thorns", "Cavalier of Thorns"), _creature("bear")])
    for key in ("phoenix", "gales", "thorns"):
        h = r.handles[key]
        dies = next(i for i, ab in enumerate(r.ex.binder.handle_record[h].abilities)
                    if isinstance(ab, TriggeredAbility) and isinstance(ab.event, CreatureDiesEvent))
        assert not functions_from_graveyard(r.ex.binder.handle_record[h].abilities[dies]), key
        assert (h, dies) in r.ex.binder.attached, key
    r.ex.execute(atom(Verb.DESTROY, target=EVERY), source=r.handles["bear"], controller=r.p1,
                 bindings={"target": [r.handles["phoenix"], r.handles["bear"]]})
    assert r.world.zone_of(r.handles["phoenix"]).kind == ZONE_HAND
    # "another": an IS_SOURCE under a negation is not the card itself (the base counted it)
    another = atom(Verb.MOVE_ZONE, cards=at.Selector(
        QConst(1), at.SelectorMode.TARGET, FAnd((CREATURE, FNot(SELF))),
        zones=(Zone(ZoneKind.GRAVEYARD, YOU),)), destination=Zone(ZoneKind.HAND, YOU))
    assert not functions_from_graveyard(TriggeredAbility(DIES, None, another))


class TestLookingBackAcrossOneDrain(_Case):
    """Controls: an event matched after another in the same drain (two instructions of one
    resolution) still finds a departed object as it was, though the layers were brought up to
    date for the first event's other triggers (here "whenever you gain life", whose filter the
    first instruction's gain makes the binder read): its last known information answers."""

    READS = TriggeredAbility(at.LifeGainedEvent(actor=YOU_ARE), None, _gain(QConst(0)))

    def test_a_granted_keyword_of_a_creature_that_died_in_the_second_instruction(self) -> None:
        flying = FAtom(FAtomPred.KEYWORD_HAS, keyword=Keyword.FLYING)
        grant = atom(Verb.GRANT_ABILITY, ability=at.KeywordAbility(Keyword.FLYING),
                     target=at.Selector(at.QUnbounded(), at.SelectorMode.ALL, FAnd((CREATURE, YOU_ARE)),
                                        zones=(BF_YOU,)))
        self.ex.attach_card(self.watch, self.record_for(self.watch, [
            at.StaticAbility(grant),
            TriggeredAbility(CreatureDiesEvent(filter=FAnd((OTHER_OF_YOURS, flying))), None, _gain()), self.READS]))
        self.ex.layers.recompute()
        [bear] = self.creatures(1, [])
        self.ex.layers.recompute()
        assert self.ex.layers.keyword_of(bear, Keyword.FLYING)
        self.ex.decisions.provider = in_trigger_order
        self.ex.apply_effect(at.Seq((_gain(QConst(5)), atom(Verb.DESTROY, target=EVERY))),
                             source=self.watch, controller=self.p0, bindings={"target": [bear]})
        assert self.gains() == [5, 1]

    def test_a_granted_type_of_a_creature_that_died_in_the_second_instruction(self) -> None:
        """The same for a type an effect gave it ("is a Knight in addition to its other types"):
        "whenever a Knight you control dies" sees the creature as the Knight it was."""
        knight = FAtom(FAtomPred.SUBTYPE_EQ, string_value="Knight")
        make = atom(Verb.GRANT_TYPE, types=("Knight",),
                    target=at.Selector(at.QUnbounded(), at.SelectorMode.ALL,
                                       FAnd((CREATURE, YOU_ARE)), zones=(BF_YOU,)))
        self.ex.attach_card(self.watch, self.record_for(self.watch, [
            at.StaticAbility(make),
            TriggeredAbility(CreatureDiesEvent(filter=FAnd((OTHER_OF_YOURS, knight))), None, _gain()), self.READS]))
        [bear] = self.creatures(1, [])
        self.ex.layers.recompute()
        assert "Knight" in self.ex.layers.type_overlay(bear)
        self.ex.decisions.provider = in_trigger_order
        self.ex.apply_effect(at.Seq((_gain(QConst(5)), atom(Verb.DESTROY, target=EVERY))),
                             source=self.watch, controller=self.p0, bindings={"target": [bear]})
        assert self.gains() == [5, 1]


def test_infernal_scarring_draws_when_its_creature_dies_in_a_later_instruction() -> None:
    """Control. M21 Infernal Scarring's granted "When this creature dies, draw a card" looks back
    at the death (CR 603.10a), also when the death is the second instruction of a resolution,
    after the layers were brought up to date for the first: the dead creature's granted
    abilities are its last known information."""
    r = _runner("M21", [_real("scarring", "Infernal Scarring"), _creature("host"),
                        {"key": "lib", "name": "L", "type": "Land", "zone": "library", "controller": 0}])
    r.run_step({"op": "enchant", "aura": "scarring", "host": "host"})
    draws = sum(1 for e in r.ex.journal.events if e.kind == KIND_CARD_DRAWN)
    r.ex.apply_effect(at.Seq((_gain(QConst(5)), atom(Verb.DESTROY, target=EVERY))),
                      source=r.handles["host"], controller=r.p1,
                      bindings={"target": [r.handles["host"]]})
    assert r.world.zone_of(r.handles["host"]).kind == ZONE_GRAVEYARD
    assert sum(1 for e in r.ex.journal.events if e.kind == KIND_CARD_DRAWN) == draws + 1


# --------------------------------------------- CR 603.10: the layers as they are after the event


def test_garruks_uprising_sees_an_anthems_bonus_on_a_creature_that_enters() -> None:
    """M21 Garruk's Uprising, "Whenever a creature you control with power 4 or greater enters,
    draw a card", with M21 Glorious Anthem ("Creatures you control get +1/+1"): a 3/3 enters
    and is a 4/4 right after (CR 603.10: the continuous effects that exist then decide). The
    base read the layers as they stood before the entry: no card."""
    r = _runner("M21", [_real("uprising", "Garruk's Uprising"), _real("anthem", "Glorious Anthem"),
                        _creature("big", "3", "3", zone="hand"),
                        {"key": "lib", "name": "L", "type": "Land", "zone": "library", "controller": 0}])
    draws = sum(1 for e in r.ex.journal.events if e.kind == KIND_CARD_DRAWN)
    r.run_step({"op": "enter", "key": "big"})
    assert sum(1 for e in r.ex.journal.events if e.kind == KIND_CARD_DRAWN) == draws + 1


class TestTheLayersAfterTheEvent(_Case):
    """CR 603.10: the triggers that do not look back are checked with the continuous effects
    that exist right after the event, also where no filter of a printed trigger is read first
    (the binder brings the layers up to date at the first read that needs them)."""

    def test_creatures_that_enter_have_the_triggered_ability_a_static_grants_them(self) -> None:
        """"Creatures you control have 'Whenever another creature you control enters, you gain 1
        life'": two creatures enter at once and have it right after; each sees the other enter
        (CR 603.6a), as does the granter: 4 life (the base: 2, the granter's alone)."""
        granted = TriggeredAbility(ENTERS, None, _gain())
        grant = atom(Verb.GRANT_ABILITY, ability=granted,
                     target=at.Selector(at.QUnbounded(), at.SelectorMode.ALL,
                                        FAnd((CREATURE, YOU_ARE)), zones=(BF_YOU,)))
        self.ex.attach_card(self.watch, self.record_for(self.watch, [at.StaticAbility(grant)]))
        self.ex.layers.recompute()
        pair = self.creatures(2, [], zone=ZONE_HAND)
        self.ex.decisions.provider = in_trigger_order
        self.ex.execute(_move(BF_YOU), source=self.watch, controller=self.p0,
                        bindings={"cards": pair})
        assert self.gains() == [1, 1, 1, 1]

    def test_a_trigger_from_anywhere_reads_the_card_in_its_new_zone(self) -> None:
        """CR 603.6c, 603.10: "whenever a creature card with flying is put into your graveyard
        from anywhere" does not look back, so it sees the card in the graveyard, which has no
        flying: a static gave the creature its flying on the battlefield (the base read the
        stale keyword map and triggered; the fresh-eyes review's repro)."""
        flying = FAtom(FAtomPred.KEYWORD_HAS, keyword=Keyword.FLYING)
        grant = atom(Verb.GRANT_ABILITY, ability=at.KeywordAbility(Keyword.FLYING),
                     target=at.Selector(at.QUnbounded(), at.SelectorMode.ALL,
                                        FAnd((CREATURE, YOU_ARE)), zones=(BF_YOU,)))
        to_graveyard = ZoneChangeEvent(ANY, Zone(ZoneKind.GRAVEYARD, YOU), FAnd((CREATURE, flying)))
        self.ex.attach_card(self.watch, self.record_for(self.watch, [
            at.StaticAbility(grant), TriggeredAbility(to_graveyard, None, _gain())]))
        [bear] = self.creatures(1, [])
        self.ex.layers.recompute()
        assert self.ex.layers.keyword_of(bear, Keyword.FLYING)
        with self.ex.atomic():  # the drain sees the death before any state check recomputes
            self.ex.execute(atom(Verb.DESTROY, target=EVERY), source=bear, controller=self.p1,
                            bindings={"target": [bear]})
        self.ex.fire_triggers()
        assert self.gains() == []

    def test_a_keyword_trigger_lost_in_the_same_drain_does_not_trigger(self) -> None:
        """Prowess granted by a static whose source dies in the same resolution as a cast row is
        journalled: the creature no longer has prowess right after (the base: it triggered on
        the stale keyword map)."""
        grant = atom(Verb.GRANT_ABILITY, ability=at.KeywordAbility(Keyword.PROWESS),
                     target=at.Selector(at.QUnbounded(), at.SelectorMode.ALL,
                                        FAnd((CREATURE, FNot(SELF), YOU_ARE)), zones=(BF_YOU,)))
        self.ex.attach_card(self.watch, self.record_for(self.watch, [at.StaticAbility(grant)]))
        [bear] = self.creatures(1, [])
        spell = self.world.add_card(card_id("Shock", type_line="Instant"), self.p0, ZONE_HAND)
        self.ex.layers.recompute()
        assert self.ex.layers.keyword_of(bear, Keyword.PROWESS)

        with self.ex.atomic():  # one action: no state check between the death and the cast
            self.ex.execute(atom(Verb.DESTROY, target=EVERY), source=bear, controller=self.p1,
                            bindings={"target": [self.watch]})
            self.ex.journal.emit_cast(spell, self.p0, "INSTANT", "hand", None)
        self.ex.fire_triggers()
        assert self.ex.ledger.effective_pt(self.world.cards[bear].identity, bear,
                                           self.world.cards[bear].counters) == (2, 2)


# ------------------------------------------------------ CR 400.7: "it" is the object, until it moves


def test_marauding_raptor_does_not_hit_the_new_object_a_flickered_creature_became() -> None:
    """M20 Marauding Raptor: "Whenever another creature you control enters, this creature deals
    2 damage to it." The creature is exiled and returned before the first trigger resolves: it
    is a new object (CR 400.7), which only the second trigger (its new entry) damages: 2 (the
    base: 4, both hit it)."""
    r = _runner("M20", [_real("raptor", "Marauding Raptor"), _creature("bear", "3", "5", zone="hand")])
    bear = r.handles["bear"]
    r.ex.decisions.provider = in_trigger_order

    def move(dest):
        return lambda: r.ex.execute(_move(dest), source=bear, controller=r.p0, bindings={"cards": [bear]})

    _held(r.ex, move(BF_YOU), move(Zone(ZoneKind.EXILE, ControllerRef.OWNER)), move(BF_YOU))
    r.ex.fire_triggers()
    assert r.world.zone_of(bear).kind == ZONE_BATTLEFIELD
    assert r.ex.damage.get(bear) == 2


def test_bag_of_holding_does_not_exile_a_discarded_card_that_left_the_graveyard() -> None:
    """M20 Bag of Holding: "Whenever you discard a card, exile that card from your graveyard."
    The card is returned to its owner's hand before the trigger resolves: the card in hand is a
    new object, and stays there (the base exiled it from the hand)."""
    r = _runner("M20", [_real("bag", "Bag of Holding"), _creature("card", zone="hand")])
    card = r.handles["card"]

    def move(kind):
        return lambda: r.ex.execute(_move(Zone(kind, ControllerRef.OWNER)), source=r.handles["bag"],
                                    controller=r.p0, bindings={"cards": [card]})

    _held(r.ex, move(ZoneKind.GRAVEYARD), move(ZoneKind.HAND))
    r.ex.fire_triggers()
    assert r.world.zone_of(card).kind == ZONE_HAND


def test_terror_of_the_peaks_reads_a_creature_that_left_as_it_last_existed() -> None:
    """M21 Terror of the Peaks: "Whenever another creature you control enters, this creature
    deals damage equal to that creature's power to any target." The creature gets a +1/+1
    counter and dies before the trigger resolves: "that creature's power" is its last known
    power, 3 (CR 608.2h; the base read the card in the graveyard, 2)."""
    r = _runner("M21", [_real("terror", "Terror of the Peaks"), _creature("bear", zone="hand")])
    bear, opponent = r.handles["bear"], r.p1
    counter = atom(Verb.PUT_COUNTER, target=EVERY, counter_kind=at.CounterKind.PLUS_1_PLUS_1,
                   count=QConst(1))
    _held(r.ex,
          lambda: r.run_step({"op": "enter", "key": "bear"}),
          lambda: r.ex.execute(counter, source=bear, controller=r.p0, bindings={"target": [bear]}),
          lambda: r.run_step({"op": "move", "key": "bear", "to": "graveyard"}))
    r.ex.decisions.provider = lambda vocab, what: str(opponent) if str(opponent) in vocab else vocab[0]
    r.ex.execute(_gain(), source=r.handles["terror"], controller=r.p0)  # the next op resolves it
    assert r.world.players[opponent].life == 17


def test_gloom_sower_reads_the_controller_of_a_blocker_that_left() -> None:
    """Control. M21 Gloom Sower: "Whenever this creature becomes blocked by a creature, that
    creature's controller loses 2 life and you gain 2 life." The blocker dies before the
    trigger resolves: its controller is read as it last existed (CR 608.2h), the effect does not
    act on it."""
    r = _runner("M21", [_real("sower", "Gloom Sower"), _creature("blocker", seat=1)])
    r.run_step({"op": "combat", "seat": 0, "attack": {"sower": True},
                "block": {"blocker": "sower"},
                "respond_to_triggers": {"DECLARE_BLOCKERS": [
                    {"op": "move", "key": "blocker", "to": "graveyard"}]}})
    assert r.world.players[r.p1].life == 18
    assert r.world.players[r.p0].life == 22


# ----------------------------------------- CR 101.4, 614.6, 610.3: what one event is, and after it


class TestWhatOneEventIs(_Case):
    def test_each_player_sacrificing_is_one_event(self) -> None:
        """Gate round 10's MINOR-1: "each player sacrifices a Bear" against a flagged "whenever
        one or more other creatures leave the battlefield, you gain that much life": CR 101.4,
        the players' actions happen at the same time, one event: 2 (the base: 1, twice)."""
        leave = ZoneChangeEvent(Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY), ANY,
                                subject=FAnd((CREATURE, FNot(SELF))))
        self.ex.attach_card(self.watch, self.record_for(self.watch, [
            TriggeredAbility(leave, None, _gain(THAT_MANY), once_per_event=True)]))
        for player in (self.p0, self.p1):
            self.creatures(1, [], player=player)
        self.ex.decisions.provider = in_trigger_order
        self.ex.apply_effect(at.EachPlayer(ControllerRef.ANY, atom(Verb.SACRIFICE, target=self.a_bear())),
                             source=self.watch, controller=self.p0)
        assert self.gains() == [2]

    def a_bear(self) -> at.Selector:
        return at.Selector(QConst(1), at.SelectorMode.CHOOSE,
                           FAtom(FAtomPred.NAME_CONTAINS, string_value="Bear"), zones=(BF_YOU,))

    def test_a_return_waits_for_the_end_of_the_event_that_ended_it(self) -> None:
        """CR 610.3: an object exiled "until" a permanent leaves the battlefield returns right
        after the event in which it left. The two players' sacrifices are one event (CR 101.4),
        so the exiled card returns after both, and the two sacrificed creatures, each with
        "whenever another creature leaves the battlefield, you gain 1 life", see each other
        leave (the base: the return ran between the sacrifices, and only the second creature's
        trigger saw the first leave)."""
        leave = ZoneChangeEvent(Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY), ANY,
                                subject=FAnd((CREATURE, FNot(SELF))))
        [anchor] = self.creatures(1, [TriggeredAbility(leave, None, _gain())])
        [other] = self.creatures(1, [TriggeredAbility(leave, None, _gain())], player=self.p1)
        exiled = self.world.add_card(card_id("Exiled", "1", "1"), self.p0, ZONE_GRAVEYARD)
        until = atom(Verb.MOVE_ZONE, cards=EVERY, destination=Zone(ZoneKind.EXILE, ControllerRef.OWNER),
                     duration=at.DurationUntilLeaves("source"))
        self.ex.execute(until, source=anchor, controller=self.p0, bindings={"cards": [exiled]})
        assert self.world.zone_of(exiled).kind == ZONE_EXILE
        self.ex.decisions.provider = in_trigger_order
        self.ex.apply_effect(at.EachPlayer(ControllerRef.ANY, atom(Verb.SACRIFICE, target=self.a_bear())),
                             source=self.watch, controller=self.p0)
        rows = [e for e in self.ex.journal.events if e.kind == KIND_ZONE_CHANGE
                and e.subject in (anchor, other, exiled)]
        assert [(e.subject, e.zone_move[1]) for e in rows[-3:]] == [
            (anchor, ZONE_GRAVEYARD), (other, ZONE_GRAVEYARD), (exiled, ZONE_GRAVEYARD)]
        assert self.gains(self.p0) == [1] and self.gains(self.p1) == [1]

    def test_a_nested_event_does_not_run_the_returns_of_the_event_around_it(self) -> None:
        """A boundary nested inside another (a spell an effect casts and resolves) is an event of
        its own; when it ends, the returns the event around it is holding still wait for that
        one to end (CR 610.3)."""
        [anchor] = self.creatures(1, [])
        exiled = self.world.add_card(card_id("Exiled", "1", "1"), self.p0, ZONE_GRAVEYARD)
        until = atom(Verb.MOVE_ZONE, cards=EVERY, destination=Zone(ZoneKind.EXILE, ControllerRef.OWNER),
                     duration=at.DurationUntilLeaves("source"))
        self.ex.execute(until, source=anchor, controller=self.p0, bindings={"cards": [exiled]})
        sacrifice = atom(Verb.SACRIFICE, target=self.a_bear())
        with self.ex.atomic(), self.ex._one_event():
            self.ex.execute(sacrifice, source=self.watch, controller=self.p0)
            before = self.ex.journal.snapshot()  # a boundary opens
            with self.ex._one_event():  # an event nested in it ends
                pass
            self.ex.journal.record_atom(before, None, "TEST", [])
            assert self.world.zone_of(exiled).kind == ZONE_EXILE  # not yet
        assert self.world.zone_of(exiled).kind == ZONE_GRAVEYARD

    def test_a_return_still_comes_when_a_step_of_the_event_is_skipped(self) -> None:
        """Control. The guarded effect lane skips a step whose anaphora has no antecedent and goes
        on; the sacrifice before it in the same EachPlayer still ended the "until", so the card
        returns, once the event is over."""
        [anchor] = self.creatures(1, [])
        exiled = self.world.add_card(card_id("Exiled", "1", "1"), self.p0, ZONE_GRAVEYARD)
        until = atom(Verb.MOVE_ZONE, cards=EVERY, destination=Zone(ZoneKind.EXILE, ControllerRef.OWNER),
                     duration=at.DurationUntilLeaves("source"))
        self.ex.execute(until, source=anchor, controller=self.p0, bindings={"cards": [exiled]})
        dangling = atom(Verb.DESTROY, target=at.Selector(QConst(1), at.SelectorMode.CHOOSE, FAnd(()),
                                                         zones=(ANY,), referent="event"))
        body = at.Seq((atom(Verb.SACRIFICE, target=self.a_bear()), dangling))
        ctx = self.ex._ctx(source=self.watch, controller=self.p0, bindings=None, decisions=())
        self.ex._run_guarded_effect(at.EachPlayer(ControllerRef.YOU, body), ctx, "test")
        assert self.world.zone_of(anchor).kind == ZONE_GRAVEYARD
        assert self.world.zone_of(exiled).kind == ZONE_GRAVEYARD
        assert self.ex.unresolved_effects  # the skipped step, recorded


def test_entries_replaced_in_one_instruction_are_one_event() -> None:
    """CR 614.6: M21 Containment Priest ("If a nontoken creature would enter and it wasn't cast,
    exile it instead") replaces both entries of one instruction putting two creature cards onto
    the battlefield; the two exiles are that instruction's event: a flagged "whenever one or
    more creature cards are put into exile, you gain that much life" counts 2 (the base: 1,
    then 1, each replacement's action an event of its own)."""
    r = _runner("M21", [_real("priest", "Containment Priest"), _creature("watch"),
                        _creature("a", zone="graveyard"), _creature("b", zone="graveyard")])
    watch, cards = r.handles["watch"], [r.handles["a"], r.handles["b"]]
    exiled = ZoneChangeEvent(ANY, Zone(ZoneKind.EXILE, ControllerRef.ANY), CREATURE)
    r.ex.attach_card(watch, record_of([TriggeredAbility(exiled, None, _gain(THAT_MANY),
                                                        once_per_event=True)],
                                      oid=r.world.cards[watch].identity.oracle_id))
    r.ex.execute(_move(BF_YOU), source=watch, controller=r.p0, bindings={"cards": cards})
    assert all(r.world.zone_of(h).kind == ZONE_EXILE for h in cards)
    assert [e.data[0] for e in r.ex.journal.events
            if e.kind == KIND_LIFE_GAINED and e.subject == r.p0] == [2]


def test_a_death_replaced_in_a_state_based_check_is_part_of_its_event() -> None:
    """CR 614.6, 704.3: two creatures die in one state-based check, and Scorching Dragonfire's
    replacement exiles one of them instead. The exile is part of the check's event: a flagged
    "whenever one or more other creatures you control leave the battlefield, you gain that much
    life" counts 2 (the base: 1, then 1)."""
    r = _runner("M21", [_real("fire", "Scorching Dragonfire", zone="hand"), _creature("watch"),
                        _creature("bear"), _creature("tough", "2", "4")])
    watch, bear, tough = r.handles["watch"], r.handles["bear"], r.handles["tough"]
    r.ex.attach_card(watch, record_of([TriggeredAbility(LEAVES, None, _gain(THAT_MANY),
                                                        once_per_event=True)],
                                      oid=r.world.cards[watch].identity.oracle_id))
    r.run_step({"op": "mana", "seat": 0, "add": {"R": 2}})
    r.run_step({"op": "cast", "key": "fire", "real": "Scorching Dragonfire", "targets": ["tough"]})
    assert r.world.zone_of(tough).kind == ZONE_BATTLEFIELD  # 3 damage on a 2/4
    both = at.Selector(at.QUnbounded(), at.SelectorMode.ALL,
                       FAtom(FAtomPred.NAME_CONTAINS, string_value="o"), zones=(BF_YOU,))
    r.ex.execute(atom(Verb.DEAL_DAMAGE, target=both, amount=QConst(2)), source=watch,
                 controller=r.p1, bindings={"target": [bear, tough]})
    assert r.world.zone_of(bear).kind == ZONE_GRAVEYARD
    assert r.world.zone_of(tough).kind == ZONE_EXILE
    assert [e.data[0] for e in r.ex.journal.events
            if e.kind == KIND_LIFE_GAINED and e.subject == r.p0] == [2]
