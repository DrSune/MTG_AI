"""One or more objects moved at once (2026-11-13, ontology round R10, DESIGN_ATOM_ONTOLOGY §14;
gate round 10 FIX-THEN-GO, fixed): a zone-change trigger that gathers the objects one event moves
(CR 603.2c), and "they" for the attackers a declaration gathers.

- ``TriggeredAbility.once_per_event`` on a ZoneChangeEvent whose subject is not the source or what
  it is attached to: one trigger for the objects one atom boundary moves (the tokens one effect
  creates, the cards one instruction or one state-based-action check moves; a draw is one card at
  a time, CR 121.2), ``GameEvent.batch``.
- Under the flag, on a declaration or a zone change, the event register holds every object the
  event gathered. Selector(referent="event") is "they" (Angelic Guardian): those the effect can
  still act on, not one that changed zones since (CR 400.7), was moved into a hidden zone or is a
  token off the battlefield (CR 111.8). QProp("event", THAT_MANY_COUNT) is their number ("that
  many", Woodland Champion, the ones that left included: its ruling), and "among them" (an
  aggregate or a filtered count over the referent) reads every one, by its last known
  information once it left (CR 608.2h). A gathered combat damage event keeps its one subject
  (Feline Sovereign).
- The IR refuses the flag on a zone change of one object and on a creature's death written as a
  zone change (second encodings), a read of one object of a gathered register ("its power"), and
  an unfiltered count of a referent Selector (a second encoding of THAT_MANY_COUNT).

Every test here fails on the base, 30fabc4a, except the controls named in
``reports/one_or_more_2026-11-13/base_runs.txt``, which pin what the base already did right.
"""

from __future__ import annotations

import dataclasses

import pytest

from MTG_bot.core import ability_tree as at
from MTG_bot.core.ability_tree import (
    Atom,
    AtomArgs,
    ControllerRef,
    DeclareAttackersEvent,
    FAnd,
    FAtom,
    FAtomPred,
    FNot,
    Keyword,
    QConst,
    QProp,
    QPropField,
    TokenSpec,
    TriggeredAbility,
    Verb,
    Zone,
    ZoneChangeEvent,
    ZoneKind,
)
from MTG_bot.core.executor.decisions import in_trigger_order
from MTG_bot.core.executor.events import (
    KIND_COUNTER_PLACED,
    KIND_LIFE_GAINED,
    KIND_ZONE_CHANGE,
    GameEvent,
)
from MTG_bot.core.executor.games import get_supply
from MTG_bot.core.state import ZONE_BATTLEFIELD, ZONE_EXILE, ZONE_GRAVEYARD, ZONE_HAND
from MTG_bot.core.test_executor_binding import BindingCase, atom, card_id, record_of, referent_sel
from tools.run_scenarios import ScenarioRunner

YOU = ControllerRef.YOU
YOU_ARE = FAtom(FAtomPred.CONTROLLER_IS, who=YOU)
CREATURE = FAtom(FAtomPred.TYPE_EQ, string_value="Creature")
SELF = FAtom(FAtomPred.IS_SOURCE)
ANY = Zone(ZoneKind.ANY, ControllerRef.ANY)
THAT_MANY = QProp(referent="event", field=QPropField.THAT_MANY_COUNT)


def _gain(amount) -> Atom:
    return Atom(Verb.GAIN_LIFE, AtomArgs(pairs=(("amount", amount), ("controller", YOU))))


def _enters(subject) -> ZoneChangeEvent:
    return ZoneChangeEvent(ANY, Zone(ZoneKind.BATTLEFIELD, YOU), subject=subject)


def _soldiers(n: int) -> Atom:
    spec = TokenSpec(name="Soldier", type_line="Creature — Soldier", types=("Creature",),
                     subtypes=("Soldier",), power=QConst(1), toughness=QConst(1), keywords=(),
                     abilities=(), colors=("W",))
    return Atom(Verb.CREATE_TOKEN, AtomArgs(pairs=(("count", QConst(n)), ("tokens", spec))))


def _move(destination: Zone) -> Atom:
    """A MOVE_ZONE of the objects bound under ``cards``: one instruction, one atom boundary."""
    every = at.Selector(QConst(9), at.SelectorMode.ALL, FAnd(()), zones=(ANY,))
    return atom(Verb.MOVE_ZONE, cards=every, destination=destination)


def _runner(code: str, cards: list[dict]) -> ScenarioRunner:
    pack = {"set": code, "world": {"life": 20, "seed": 7}, "cards": cards, "steps": []}
    return ScenarioRunner(pack, get_supply("all", code))


def _real(key: str, name: str, seat: int = 0, zone: str = "battlefield") -> dict:
    return {"key": key, "real": name, "zone": zone, "controller": seat}


def _creature(key: str, seat: int = 0, zone: str = "battlefield", **extra) -> dict:
    return {"key": key, "name": key.title(), "type": "Creature — Bear", "power": "2",
            "toughness": "2", "zone": zone, "controller": seat, **extra}


def _counter_rows(r: ScenarioRunner, key: str) -> list[int]:
    """The +1/+1 counter placements on ``key``, one row per placing atom (one resolution)."""
    return [e.data[1] for e in r.ex.journal.events
            if e.kind == KIND_COUNTER_PLACED and e.subject == r.handles[key]
            and e.data[0] == "PLUS_1_PLUS_1"]


def _indestructible(r: ScenarioRunner, key: str) -> bool:
    r.ex.layers.recompute()
    return r.ex.layers.keyword_of(r.handles[key], Keyword.INDESTRUCTIBLE)


# ------------------------------------------------------------------------------- the IR


@pytest.mark.parametrize(
    "subject",
    [
        SELF,  # "when this creature enters": one object per event
        FAtom(FAtomPred.IS_ATTACHED_TO_SOURCE),  # "when equipped creature dies"-like: one
        FAnd((CREATURE, SELF)),
    ],
)
def test_once_per_event_on_a_zone_change_of_one_object_is_refused(subject) -> None:
    """Flagged, "when this creature enters" would be a second byte form of the unflagged
    trigger: one event never moves the source twice."""
    event = _enters(subject)
    with pytest.raises(ValueError, match="gathers occurrences"):
        TriggeredAbility(event, None, _gain(QConst(1)), once_per_event=True)
    with pytest.raises(ValueError, match="gathers occurrences"):
        at.DelayedTrigger(at.DurationEot(), event, None, _gain(QConst(1)), True)
    assert TriggeredAbility(event, None, _gain(QConst(1))).once_per_event is None


def test_once_per_event_gathers_a_zone_change_of_several_objects() -> None:
    for subject in (None, FAtom(FAtomPred.IS_TOKEN), FAnd((CREATURE, FNot(SELF))),
                    at.FOr((SELF, CREATURE))):
        event = _enters(subject)
        assert at.gathers_occurrences(event), subject
        assert TriggeredAbility(event, None, _gain(THAT_MANY), once_per_event=True).once_per_event


@pytest.mark.parametrize(
    "field",
    [QPropField.POWER, QPropField.TOUGHNESS, QPropField.CMC, QPropField.MANA_VALUE,
     QPropField.COUNTER_COUNT, QPropField.AMOUNT],
)
@pytest.mark.parametrize(
    "event",
    [_enters(FAtom(FAtomPred.IS_TOKEN)), DeclareAttackersEvent(filter=FAnd((YOU_ARE, CREATURE)))],
    ids=["zone change", "declaration"],
)
def test_a_gathered_register_has_no_it(event, field) -> None:
    """Under the flag the event register holds several objects: "its power" would read the one
    that comes first in handle order. Read the set ("they") or its size ("that many")."""
    one = _gain(QProp(referent="event", field=field))
    with pytest.raises(ValueError, match="a read of one of them"):
        TriggeredAbility(event, None, one, once_per_event=True)
    with pytest.raises(ValueError, match="a read of one of them"):
        at.DelayedTrigger(at.DurationEot(), event, None, one, True)
    # a reflexive trigger in it reads the same register (CR 603.12)
    when_you_do = at.Seq((
        at.OptionalEffect(_gain(QConst(1))),
        at.Conditional(FAtom(FAtomPred.MAY_DONE),
                       at.DelayedTrigger(None, None, None, one)),
    ))
    with pytest.raises(ValueError, match="a read of one of them"):
        TriggeredAbility(event, None, when_you_do, once_per_event=True)
    # and so does the intervening "if" ("if you control at least its power creatures")
    its_power = FAtom(FAtomPred.CONTROLLER_COUNT_GE, inner_filter=CREATURE,
                      count=QProp(referent="event", field=field))
    with pytest.raises(ValueError, match="a read of one of them"):
        TriggeredAbility(event, its_power, _gain(QConst(1)), once_per_event=True)
    # unflagged, the register holds the one object the event names; and the set and its size
    # are read under the flag
    TriggeredAbility(event, None, one)
    TriggeredAbility(event, its_power, _gain(QConst(1)))
    TriggeredAbility(event, None, _gain(THAT_MANY), once_per_event=True)
    grant = Atom(Verb.GRANT_ABILITY, AtomArgs(pairs=(
        ("ability", at.KeywordAbility(Keyword.INDESTRUCTIBLE)), ("duration", at.DurationEot()),
        ("target", referent_sel("event")))))
    TriggeredAbility(event, None, grant, once_per_event=True)


def test_attached_to_it_has_no_object_under_the_flag() -> None:
    """"Destroy each Aura attached to it" reads one object (FAtom IS_ATTACHED_TO, referent
    "event"): under the flag the register holds several, so the IR refuses it; unflagged it
    stands."""
    auras = at.Selector(at.QUnbounded(), at.SelectorMode.ALL,
                        FAtom(FAtomPred.IS_ATTACHED_TO, referent="event"),
                        zones=(Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),))
    destroy = Atom(Verb.DESTROY, AtomArgs(pairs=(("target", auras),)))
    event = _enters(FAtom(FAtomPred.IS_TOKEN))
    with pytest.raises(ValueError, match="a read of one of them"):
        TriggeredAbility(event, None, destroy, once_per_event=True)
    TriggeredAbility(event, None, destroy)


def test_every_single_object_read_is_refused_under_the_flag() -> None:
    """The other reads of one object of a gathered register (fresh-eyes review of 8b8c35b9): a
    token's power ("an X/X token, where X is its power", resolved as the token is made), "until
    it leaves", "it deals damage", "fights it" (FIGHT takes the first foe, verbs.py) and an
    intervening "if" that tests the event's object. Each stands unflagged. A subject-free
    condition (Mangara's count) stands under the flag."""
    event = _enters(FAtom(FAtomPred.IS_TOKEN))
    its_power = QProp(referent="event", field=QPropField.POWER)
    beast = Atom(Verb.CREATE_TOKEN, AtomArgs(pairs=(("count", QConst(1)), ("tokens", TokenSpec(
        name="Beast", type_line="Creature — Beast", types=("Creature",), subtypes=("Beast",),
        power=its_power, toughness=QConst(1), keywords=(), abilities=(), colors=("G",))))))
    exile_until = atom(Verb.MOVE_ZONE, cards=at.Selector(
        QConst(1), at.SelectorMode.TARGET, CREATURE, zones=(Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),)),
        destination=Zone(ZoneKind.EXILE, ControllerRef.OWNER), duration=at.DurationUntilLeaves("event"))
    it_deals = atom(Verb.DEAL_DAMAGE, amount=QConst(1), dealer=referent_sel("event"),
                    target=at.Selector(QConst(1), at.SelectorMode.TARGET, CREATURE,
                                       zones=(Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),)))
    fights_it = atom(Verb.FIGHT, target=referent_sel("event"))
    big = FAtom(FAtomPred.POWER_GE, count=QConst(5))
    for effect, condition in ((beast, None), (exile_until, None), (it_deals, None),
                              (fights_it, None), (_gain(QConst(1)), big)):
        with pytest.raises(ValueError, match="a read of one of them"):
            TriggeredAbility(event, condition, effect, once_per_event=True)
        TriggeredAbility(event, condition, effect)
    counted = FAtom(FAtomPred.CONTROLLER_COUNT_GE, inner_filter=CREATURE, count=QConst(2))
    TriggeredAbility(event, counted, _gain(QConst(1)), once_per_event=True)


def test_a_first_over_a_referent_selector_is_refused() -> None:
    """"Its power" is QProp("event", POWER), the one encoding: a FIRST over Selector(referent=
    "event") is its second byte form, and under the flag it read the first object by handle
    order. An aggregation over the referent ("the greatest power among them") is another
    meaning and stands."""
    for referent in ("event", "result", "target"):
        with pytest.raises(ValueError, match="not a FIRST over the Selector"):
            QProp(referent=referent_sel(referent), field=QPropField.POWER)
    greatest = QProp(referent=referent_sel("event"), field=QPropField.POWER, agg=at.QAgg.MAX)
    TriggeredAbility(_enters(FAtom(FAtomPred.IS_TOKEN)), None, _gain(greatest), once_per_event=True)


def test_a_gathered_damage_event_keeps_its_one_subject() -> None:
    """Feline Sovereign's "that player": a flagged combat damage trigger gathers the dealers, and
    its register is the one player they damaged, so a QProp of it is not refused."""
    dealt = at.DamageDealtEvent(at.QUnbounded(), FAnd(()), source=CREATURE, combat=True)
    assert not at.gathers_objects(dealt, True)
    TriggeredAbility(dealt, None, _gain(QProp(referent="event", field=QPropField.AMOUNT)),
                     once_per_event=True)


@pytest.mark.parametrize("referent", ["event", "result", "target", "source", "controller"])
def test_a_count_of_a_referent_selector_is_refused(referent) -> None:
    """"That many" is QProp("event", THAT_MANY_COUNT): a QCount of the register's Selector would
    be a second byte form of it (and of a different number once a gathered object leaves)."""
    with pytest.raises(ValueError, match="THAT_MANY_COUNT"):
        at.QCount(referent_sel(referent))


def test_a_count_of_some_of_them_is_a_filtered_referent_count() -> None:
    """Gate round 10's nit: "for each creature card exiled this way" counts some of the objects
    an instruction acted on, which THAT_MANY_COUNT cannot (it has no filter), and IS_RESULT in a
    selector's filter is refused as a second form of the referent: its one encoding is a QCount
    over the referent Selector with the filter. "Source" and "controller" name one object."""
    for referent in ("event", "result", "target"):
        at.QCount(referent_sel(referent, CREATURE))
    for referent in ("source", "controller"):
        with pytest.raises(ValueError, match="names one object"):
            at.QCount(referent_sel(referent, CREATURE))


def test_one_or_more_creatures_dying_is_not_a_zone_change() -> None:
    """Gate round 10, MINOR-3 (divergence D24): "one or more creatures die" is CreatureDiesEvent's
    (CR 700.4); flagged, a creature's move from the battlefield to a graveyard would be its
    second encoding. Without a creature in the subject, or to another zone, the zone change is
    the one form and stands."""
    dies = Zone(ZoneKind.BATTLEFIELD, YOU), Zone(ZoneKind.GRAVEYARD, ControllerRef.ANY)
    for subject in (CREATURE, FAnd((CREATURE, YOU_ARE)), FAnd((CREATURE, FNot(SELF)))):
        with pytest.raises(ValueError, match="that is a CreatureDiesEvent"):
            TriggeredAbility(ZoneChangeEvent(*dies, subject=subject), None, _gain(THAT_MANY),
                             once_per_event=True)
        TriggeredAbility(ZoneChangeEvent(*dies, subject=subject), None, _gain(QConst(1)))
    artifact = FAtom(FAtomPred.TYPE_EQ, string_value="Artifact")
    for event in (ZoneChangeEvent(*dies, subject=artifact),
                  ZoneChangeEvent(*dies, subject=at.FOr((CREATURE, artifact))),
                  ZoneChangeEvent(Zone(ZoneKind.BATTLEFIELD, YOU), ANY, subject=CREATURE)):
        TriggeredAbility(event, None, _gain(THAT_MANY), once_per_event=True)


class TestTheBinderGathersOnlyWhatItGroups(BindingCase):
    def test_a_flag_on_a_sacrifice_is_refused_at_bind(self) -> None:
        """A sacrifice is a ZONE_CHANGE row too, but SacrificeEvent is not grouped: flagged, it
        would trigger once per occurrence (control: the base refuses it too)."""
        rec = self.record_for(self.watch, [TriggeredAbility(
            at.SacrificeEvent(actor=YOU_ARE), None, _gain(QConst(1)), once_per_event=True)])
        with self.assertRaises(NotImplementedError):
            self.ex.attach_card(self.watch, rec)

    def test_that_many_with_no_antecedent_still_raises(self) -> None:
        """An unflagged trigger's "that many" with no step before it has no antecedent: it
        raises, never read as the one object the event names (control)."""
        self.attach_trigger(self.watch, _enters(FNot(SELF)), _gain(THAT_MANY))
        bear = self.world.add_card(card_id("Bear", "2", "2"), self.p0, ZONE_HAND)
        with self.assertRaisesRegex(NotImplementedError, "THAT_MANY_COUNT has no producer"):
            self.ex.execute(_move(Zone(ZoneKind.BATTLEFIELD, YOU)), source=bear,
                            controller=self.p0, bindings={"cards": [bear]})


# ------------------------------------------------------------------- what is one event


class TestOneEvent(BindingCase):
    """``GameEvent.batch``: the objects one atom boundary moves are one event."""

    def _gathering(self, event) -> None:
        self.ex.attach_card(self.watch, self.record_for(self.watch, [
            TriggeredAbility(event, None, _gain(THAT_MANY), once_per_event=True)]))

    def gains(self) -> list[int]:
        return [e.data[0] for e in self.ex.journal.events
                if e.kind == KIND_LIFE_GAINED and e.subject == self.p0]

    def test_one_state_based_action_check_is_one_event(self) -> None:
        """CR 704.3: the creatures one check puts into a graveyard die at once."""
        self._gathering(ZoneChangeEvent(Zone(ZoneKind.BATTLEFIELD, YOU), ANY,
                                        subject=FAnd((CREATURE, FNot(SELF)))))
        bears = [self.world.add_card(card_id(f"Bear{i}", "2", "2"), self.p0, ZONE_BATTLEFIELD)
                 for i in range(3)]
        everyone = at.Selector(at.QUnbounded(), at.SelectorMode.ALL, FAtom(FAtomPred.NAME_CONTAINS, string_value="Bear"),
                               zones=(Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),))
        self.ex.execute(atom(Verb.DEAL_DAMAGE, target=everyone, amount=QConst(2)),
                        source=self.watch, controller=self.p0)
        assert all(self.world.zone_of(b).kind == ZONE_GRAVEYARD for b in bears)
        assert self.gains() == [3]

    def test_a_draw_is_one_card_at_a_time(self) -> None:
        """CR 121.2: "draw two cards" is two draws, two events; two cards put into a hand by one
        instruction that is not a draw are one."""
        self._gathering(ZoneChangeEvent(Zone(ZoneKind.LIBRARY, YOU), Zone(ZoneKind.HAND, YOU)))
        self.ex.decisions.provider = in_trigger_order  # the two draws' triggers (CR 603.3b)
        self.ex.execute(atom(Verb.DRAW, controller=YOU, amount=QConst(2)),
                        source=self.watch, controller=self.p0)
        assert self.gains() == [1, 1]
        two = [h for h in self.libs if self.world.zone_of(h).kind != ZONE_HAND][:2]
        self.ex.execute(_move(Zone(ZoneKind.HAND, YOU)), source=self.watch, controller=self.p0,
                        bindings={"cards": two})
        assert self.gains() == [1, 1, 2]

    def test_two_instructions_of_one_resolution_are_two_events(self) -> None:
        """"Create a token, then create two": one resolution, two instructions, two events."""
        self._gathering(_enters(FAtom(FAtomPred.IS_TOKEN)))
        maker = self.world.add_card(card_id("Maker", "2", "2"), self.p0, ZONE_HAND)
        self.ex.attach_card(maker, record_of(
            [TriggeredAbility(_enters(SELF), None, at.Seq((_soldiers(1), _soldiers(2))))],
            oid=self.world.cards[maker].identity.oracle_id))
        self.ex.decisions.provider = in_trigger_order
        self.ex.execute(_move(Zone(ZoneKind.BATTLEFIELD, YOU)), source=maker, controller=self.p0,
                        bindings={"cards": [maker]})
        assert self.gains() == [1, 2]

    def test_a_read_of_one_of_several_gathered_objects_raises_at_run_time(self) -> None:
        """The executor's nets for what the IR cannot see: a bare Conditional after a sentence that
        names no object would be judged on one of the gathered objects (it was the trigger's
        source), and a singular referent read of the register would take the first."""
        cond = at.Conditional(FAtom(FAtomPred.POWER_GE, count=QConst(5)), _gain(QConst(10)))
        self._gathering(_enters(FAtom(FAtomPred.IS_TOKEN)))
        node = self.ex.binder.records[self.world.cards[self.watch].identity.oracle_id].abilities[0]
        self.ex.attach_card(self.watch, self.record_for(self.watch, [dataclasses.replace(
            node, effect=at.Seq((_gain(QConst(1)), cond)))]))
        with self.assertRaisesRegex(NotImplementedError, "no object to judge"):
            self.ex.execute(_soldiers(2), source=self.watch, controller=self.p0)
        from MTG_bot.core.executor.legality import ctx_for
        from MTG_bot.core.executor.quantity import referent_handle

        ctx = ctx_for(self.ex, source=self.watch, controller=self.p0,
                      bindings={"event": list(self.libs[:2])})
        with self.assertRaisesRegex(NotImplementedError, "holds several objects"):
            referent_handle("event", ctx)

    def test_the_batch_stays_out_of_the_journal_dump(self) -> None:
        """Replays and forks re-derive the batch: the dump rows, so every fingerprint and game
        log, keep their bytes (control: the base's rows have the same six fields)."""
        self.ex.execute(_soldiers(2), source=self.watch, controller=self.p0)
        rows = [e for e in self.ex.journal.events if e.kind == KIND_ZONE_CHANGE]
        assert len(rows) == 2 and all(len(row) == 6 for row in self.ex.journal.dump())
        assert rows[0].batch == rows[1].batch == rows[0].clock

    def test_a_zone_change_without_a_batch_fails_loudly(self) -> None:
        """Gate round 10, MINOR-6: batch 0 is "outside an atom boundary"; a zone change there
        would be gathered with every other such row of the game. The journal refuses the row,
        and the binder refuses to gather a batch-0 zone change."""
        with self.assertRaisesRegex(ValueError, "journalled by its atom boundary"):
            self.ex.journal.emit(KIND_ZONE_CHANGE, self.libs[0], None, "TEST",
                                 ("LIBRARY", "HAND", self.p0, self.p0))
        loose = GameEvent(clock=1, kind=KIND_ZONE_CHANGE, subject=self.libs[0], cause=None,
                          cause_verb="TEST", data=("LIBRARY", "HAND", self.p0, self.p0))
        with self.assertRaisesRegex(ValueError, "no event to gather"):
            self.ex.binder._occurrences(loose)

    def test_a_batch_gathers_only_the_rows_its_trigger_matches(self) -> None:
        """Gate round 10, MINOR-4: one instruction puts two creatures and an artifact onto the
        battlefield; "one or more creatures you control enter" counts the two."""
        self._gathering(_enters(FAnd((CREATURE, FNot(SELF)))))
        moved = [self.world.add_card(card_id(n, "2", "2"), self.p0, ZONE_HAND) for n in ("A", "B")]
        moved.append(self.world.add_card(card_id("Rock", type_line="Artifact"), self.p0, ZONE_HAND))
        self.ex.execute(_move(Zone(ZoneKind.BATTLEFIELD, YOU)), source=self.watch,
                        controller=self.p0, bindings={"cards": moved})
        assert all(self.world.zone_of(h).kind == ZONE_BATTLEFIELD for h in moved)
        assert self.gains() == [2]

    def test_two_tokens_that_die_in_the_check_after_entering_are_still_counted(self) -> None:
        """Gate round 10, MINOR-4: two 0/0 tokens die in the state-based check right after they
        enter, before the trigger goes on the stack. It gathered them as the event occurred
        (CR 603.10, each row judged as it happened), so "that many" is 2; gathering when the
        trigger is put on the stack would find no token you control."""
        self._gathering(_enters(FAnd((FAtom(FAtomPred.IS_TOKEN), YOU_ARE))))
        spec = TokenSpec(name="Spark", type_line="Creature — Elemental", types=("Creature",),
                         subtypes=("Elemental",), power=QConst(0), toughness=QConst(0),
                         keywords=(), abilities=(), colors=("R",))
        self.ex.execute(Atom(Verb.CREATE_TOKEN, AtomArgs(pairs=(("count", QConst(2)),
                                                                ("tokens", spec)))),
                        source=self.watch, controller=self.p0)
        assert not any(c.identity.name == "Spark" for c in self.world.cards.values())
        assert self.gains() == [2]


class TestTheGatheredObjectsAtResolution(BindingCase):
    """What "they" and "among them" are when a gathered trigger resolves (gate round 10). The
    trigger is held while the objects move, and resolves in the next op: nothing of the op the
    objects moved in answers for them there."""

    LEAVE = ZoneChangeEvent(Zone(ZoneKind.BATTLEFIELD, YOU), ANY,
                            subject=FAnd((CREATURE, FNot(SELF))))
    EXILE_THEM = atom(Verb.MOVE_ZONE, cards=referent_sel("event"),
                      destination=Zone(ZoneKind.EXILE, ControllerRef.OWNER))

    def _watch(self, event, effect) -> None:
        self.ex.attach_card(self.watch, self.record_for(self.watch, [
            TriggeredAbility(event, None, effect, once_per_event=True)]))

    def _held(self, objects, destination) -> None:
        """One instruction moves ``objects``; the trigger waits."""
        self.ex.binder.hold = True
        try:
            self.ex.execute(_move(destination), source=self.watch, controller=self.p0,
                            bindings={"cards": objects})
        finally:
            self.ex.binder.hold = False

    def _next_op(self) -> None:
        self.ex.execute(_gain(QConst(1)), source=self.watch, controller=self.p1)

    def gains(self) -> list[int]:
        return [e.data[0] for e in self.ex.journal.events
                if e.kind == KIND_LIFE_GAINED and e.subject == self.p0]

    def _among_them(self, agg, filter_=at.FAnd(())) -> at.Seq:
        among = QProp(referent=referent_sel("event", filter_), field=QPropField.POWER, agg=agg)
        return at.Seq((_gain(among), self.EXILE_THEM))

    def _tokens_leave(self, effect) -> list:
        """Gate round 10, MAJOR-1: two tokens leave in one instruction, one with two +1/+1
        counters. 88b7f7e8 let the second cease to exist before the trigger resolved (only the
        first row's object was kept for it): "the greatest power among them" raised KeyError
        reading it, and "among the creatures among them" skipped it. Every token is read by its
        last known information (CR 608.2h), and "exile them" moves none: a token that has left
        the battlefield can't change zones (CR 111.8) and ceases to exist (CR 111.7)."""
        self._watch(self.LEAVE, effect)
        self.ex.execute(_soldiers(2), source=self.watch, controller=self.p0)
        tokens = sorted(h for h, c in self.world.cards.items() if c.identity.name == "Soldier")
        self.world.cards[tokens[1]].counters["PLUS_1_PLUS_1"] = 2
        self._held(tokens, Zone(ZoneKind.GRAVEYARD, ControllerRef.OWNER))
        self._next_op()
        assert not [e for e in self.ex.journal.events if e.kind == KIND_ZONE_CHANGE
                    and e.subject in tokens and e.zone_move[0] == ZONE_GRAVEYARD]
        assert not any(t in self.world.cards for t in tokens)
        return self.gains()

    def test_the_greatest_power_among_tokens_that_left_at_once(self) -> None:
        assert self._tokens_leave(self._among_them(at.QAgg.MAX)) == [3]

    def test_the_total_power_of_the_creatures_among_tokens_that_left_at_once(self) -> None:
        assert self._tokens_leave(self._among_them(at.QAgg.SUM, CREATURE)) == [4]

    def test_creature_cards_that_died_at_once_are_read_as_they_last_existed(self) -> None:
        """Gate round 10, MAJOR-1: two creature cards die in one instruction, one a 3/3 with a
        +1/+1 counter. The aggregate read their cards in the graveyard, where the counter is gone
        (CR 122.2), and gained 2; "the greatest power among them" is 3 (CR 608.2h). "Exile them"
        finds both in the graveyard they went to (CR 400.7: an ability that triggers on the move
        finds the new object in the public zone it moved to)."""
        bears = [self.world.add_card(card_id(f"Bear{i}", "2", "2"), self.p0, ZONE_BATTLEFIELD)
                 for i in range(2)]
        self.world.cards[bears[1]].counters["PLUS_1_PLUS_1"] = 1
        self._watch(self.LEAVE, self._among_them(at.QAgg.MAX))
        self._held(bears, Zone(ZoneKind.GRAVEYARD, ControllerRef.OWNER))
        self._next_op()
        assert self.gains() == [3]
        assert all(self.world.zone_of(b).kind == ZONE_EXILE for b in bears)

    def test_a_count_among_them_reads_every_object_gathered(self) -> None:
        """"For each token among them": a QCount over the event referent with a filter, the one
        encoding of "for each <kind> ... this way" (gate round 10's nit). Two tokens and a Bear
        leave at once; the tokens are not among "they" any more, but the count is about every
        object the event gathered (CR 608.2h)."""
        self._watch(self.LEAVE, _gain(at.QCount(referent_sel("event", FAtom(FAtomPred.IS_TOKEN)))))
        self.ex.execute(_soldiers(2), source=self.watch, controller=self.p0)
        bear = self.world.add_card(card_id("Bear", "2", "2"), self.p0, ZONE_BATTLEFIELD)
        tokens = sorted(h for h, c in self.world.cards.items() if c.identity.name == "Soldier")
        self._held([*tokens, bear], Zone(ZoneKind.GRAVEYARD, ControllerRef.OWNER))
        self._next_op()
        assert self.gains() == [2]

    def test_they_are_not_found_in_a_hidden_zone(self) -> None:
        """An ability that triggers on a move finds the new object where it went only if that
        zone is public (CR 400.7's exception). Two creatures returned to their owner's hand at
        once are counted ("that many"), and "exile them" does not take them from the hand."""
        self._watch(self.LEAVE, at.Seq((_gain(THAT_MANY), self.EXILE_THEM)))
        bears = [self.world.add_card(card_id(f"Bear{i}", "2", "2"), self.p0, ZONE_BATTLEFIELD)
                 for i in range(2)]
        self._held(bears, Zone(ZoneKind.HAND, ControllerRef.OWNER))
        self._next_op()
        assert self.gains() == [2]
        assert all(self.world.zone_of(b).kind == ZONE_HAND for b in bears)

    def test_they_leave_out_a_gathered_object_that_changed_zones_since(self) -> None:
        """Gate round 10, MINOR-4: the CR 400.7 check of "they" on a zone-change event (the
        declaration's is Angelic Guardian's pack). Two creatures enter at once; one is returned
        to its owner's hand before the trigger resolves: "exile them" exiles the other, and the
        card in hand is a new object it does not touch."""
        self._watch(_enters(FAnd((CREATURE, FNot(SELF)))), self.EXILE_THEM)
        bears = [self.world.add_card(card_id(f"Bear{i}", "2", "2"), self.p0, ZONE_HAND)
                 for i in range(2)]
        self._held(bears, Zone(ZoneKind.BATTLEFIELD, YOU))
        self.ex.execute(_move(Zone(ZoneKind.HAND, ControllerRef.OWNER)), source=self.watch,
                        controller=self.p0, bindings={"cards": bears[1:]})
        assert self.world.zone_of(bears[0]).kind == ZONE_EXILE
        assert self.world.zone_of(bears[1]).kind == ZONE_HAND


# --------------------------------------------------------------------- Woodland Champion


def test_woodland_champion_one_token_one_counter() -> None:
    r = _runner("M20", [_real("champ", "Woodland Champion")])
    r.ex.execute(_soldiers(1), source=r.handles["champ"], controller=r.p0)
    assert _counter_rows(r, "champ") == [1]


def test_woodland_champion_three_tokens_at_once_one_trigger_three_counters() -> None:
    r = _runner("M20", [_real("champ", "Woodland Champion")])
    r.ex.execute(_soldiers(3), source=r.handles["champ"], controller=r.p0)
    assert _counter_rows(r, "champ") == [3]  # one resolution put all three


def test_woodland_champion_two_token_effects_two_triggers() -> None:
    r = _runner("M20", [_real("champ", "Woodland Champion"), _creature("bear")])
    r.ex.execute(_soldiers(1), source=r.handles["bear"], controller=r.p0)
    r.ex.execute(_soldiers(2), source=r.handles["bear"], controller=r.p0)
    assert _counter_rows(r, "champ") == [1, 2]
    r.ex.execute(_soldiers(2), source=r.handles["bear"], controller=r.p1)  # not yours
    assert _counter_rows(r, "champ") == [1, 2]


def test_woodland_champion_counts_a_token_that_left_before_resolution() -> None:
    """Its ruling: "the number of tokens that entered the battlefield under your control, even if
    some or all of them leave the battlefield before the triggered ability resolves"."""
    r = _runner("M20", [_real("champ", "Woodland Champion")])
    binder = r.ex.binder
    binder.hold = True  # the trigger waits: a response comes first
    try:
        r.ex.execute(_soldiers(3), source=r.handles["champ"], controller=r.p0)
    finally:
        binder.hold = False
    def soldiers() -> list:
        return [h for h in r.world.players[r.p0].zone(ZONE_BATTLEFIELD).entries
                if r.world.cards[h].identity.name == "Soldier"]

    r.ex.execute(_move(Zone(ZoneKind.GRAVEYARD, ControllerRef.OWNER)), source=r.handles["champ"],
                 controller=r.p0, bindings={"cards": soldiers()[:1]})
    assert len(soldiers()) == 2  # one left (and, a token, ceased to exist) before resolution
    assert _counter_rows(r, "champ") == [3]


@pytest.mark.parametrize(("made", "leave"), [(3, 3), (1, 1)])
def test_woodland_champion_counts_its_tokens_when_all_of_them_left(made, leave) -> None:
    """"Even if some or ALL of them leave": with every gathered token gone, "they" names nothing
    and "that many" still counts them all (fresh-eyes review of 8b8c35b9: it raised, the count
    looking up an object first)."""
    r = _runner("M20", [_real("champ", "Woodland Champion")])
    r.ex.binder.hold = True
    try:
        r.ex.execute(_soldiers(made), source=r.handles["champ"], controller=r.p0)
    finally:
        r.ex.binder.hold = False
    gone = [h for h in r.world.players[r.p0].zone(ZONE_BATTLEFIELD).entries
            if r.world.cards[h].identity.name == "Soldier"][:leave]
    r.ex.execute(_move(Zone(ZoneKind.GRAVEYARD, ControllerRef.OWNER)), source=r.handles["champ"],
                 controller=r.p0, bindings={"cards": gone})
    assert _counter_rows(r, "champ") == [made]


def test_basri_ket_counts_an_attacker_that_died_before_its_trigger_resolved() -> None:
    """M21 Basri Ket's -2 (verified): its ruling counts "attacking nontoken creatures that leave
    combat before the triggered ability resolves". Its one Bear dies in response: 1 Soldier, as
    on the base (8b8c35b9 raised: every gathered attacker had left)."""
    r = _runner("M21", [_real("basri", "Basri Ket"), _creature("bear")])
    r.run_step({"op": "loyalty", "key": "basri", "set": 3})
    r.run_step({"op": "activate", "key": "basri", "idx": 1, "seat": 0})
    r.run_step({"op": "combat", "seat": 0, "attack": {"bear": True},
                "respond_to_triggers": {"DECLARE_ATTACKERS": [
                    {"op": "move", "key": "bear", "to": "graveyard"}]}})
    assert sum(1 for c in r.world.cards.values() if c.identity.name == "Soldier") == 1


def test_battlesong_berserker_targets_one_of_the_attackers_it_gathered() -> None:
    """FDN Battlesong Berserker (verified): "Whenever you attack, target creature you control gets
    +1/+0 and gains menace until end of turn." Its target is chosen as it goes on the stack, by a
    query that carries the gathered attackers but no event, and asks "a creature you control" of
    each; the last-known lookup of a gathered object's own row must not run there (the gate
    round 10 fixes' first version raised AttributeError in 7 of 100 FDN replays)."""
    r = _runner("FDN", [_real("berserker", "Battlesong Berserker"), _creature("bear")])
    r.run_step({"op": "combat", "seat": 0, "attack": {"berserker": True, "bear": True}})
    r.ex.layers.recompute()
    menace = [k for k in ("berserker", "bear")
              if r.ex.layers.keyword_of(r.handles[k], Keyword.MENACE)]
    assert len(menace) == 1
    assert r.world.players[r.world.player_order[1]].life == 20 - 3 - 2 - 1


# ---------------------------------------------------------------------- Angelic Guardian


def test_angelic_guardian_they_are_the_declared_attackers() -> None:
    r = _runner("M20", [_real("guardian", "Angelic Guardian"), _creature("bear"),
                        _creature("homebody")])
    r.run_step({"op": "combat", "seat": 0, "attack": {"guardian": True, "bear": True}})
    assert _indestructible(r, "guardian") and _indestructible(r, "bear")
    assert not _indestructible(r, "homebody")


def test_angelic_guardian_not_a_creature_put_onto_the_battlefield_attacking() -> None:
    """CR 508.4: Skyknight Vanguard's Soldier enters attacking but was never declared, so it is
    not one of "they"."""
    r = _runner("M20", [_real("guardian", "Angelic Guardian"), _real("knight", "Skyknight Vanguard")])
    r.run_step({"op": "combat", "seat": 0, "attack": {"guardian": True, "knight": True}})
    soldier = next(h for h, c in r.world.cards.items() if c.identity.name == "Soldier")
    assert _indestructible(r, "guardian") and _indestructible(r, "knight")
    r.ex.layers.recompute()
    assert not r.ex.layers.keyword_of(soldier, Keyword.INDESTRUCTIBLE)


def test_angelic_guardian_an_attacker_that_changed_zones_is_a_new_object() -> None:
    """CR 400.7: a bear bounced and put back before the trigger resolves is a new object, not
    one of the attackers; the guardian, still the same object, gains indestructible."""
    r = _runner("M20", [_real("guardian", "Angelic Guardian"), _creature("bear")])
    r.run_step({"op": "combat", "seat": 0, "attack": {"guardian": True, "bear": True},
                "respond_to_triggers": {"DECLARE_ATTACKERS": [
                    {"op": "move", "key": "bear", "to": "hand"},
                    {"op": "enter", "key": "bear"}]}})
    assert r.world.zone_of(r.handles["bear"]).kind == ZONE_BATTLEFIELD
    assert _indestructible(r, "guardian") and not _indestructible(r, "bear")


# --------------------------------------------------------------------- Desecrated Tomb


def test_desecrated_tomb_one_bat_per_event() -> None:
    """Its ruling: "one Bat token each time Desecrated Tomb's ability triggers, no matter how
    many cards left your graveyard"."""
    r = _runner("M19", [_real("tomb", "Desecrated Tomb"),
                        _creature("a", zone="graveyard"), _creature("b", zone="graveyard"),
                        _creature("c", zone="graveyard"),
                        {"key": "rock", "name": "Rock", "type": "Artifact", "zone": "graveyard",
                         "controller": 0}])

    def leave(*keys: str) -> None:
        r.ex.execute(_move(Zone(ZoneKind.EXILE, ControllerRef.OWNER)), source=r.handles["tomb"],
                     controller=r.p0, bindings={"cards": [r.handles[k] for k in keys]})

    def bats() -> int:
        return sum(1 for c in r.world.cards.values() if c.identity.name == "Bat")

    leave("a", "b")
    assert bats() == 1
    leave("c")
    assert bats() == 2
    leave("rock")  # not a creature card
    assert bats() == 2
