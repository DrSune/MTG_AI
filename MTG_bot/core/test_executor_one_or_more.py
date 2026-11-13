"""One or more objects moved at once (2026-11-13, ontology round R10, gate round 10): a
zone-change trigger that gathers the objects one event moves (CR 603.2c), and "they" for the
attackers a declaration gathers.

- ``TriggeredAbility.once_per_event`` on a ZoneChangeEvent whose subject is not the source or what
  it is attached to: one trigger for the objects one atom boundary moves (the tokens one effect
  creates, the cards one instruction or one state-based-action check moves; a draw is one card at
  a time, CR 121.2), ``GameEvent.batch``.
- Under the flag, on a declaration or a zone change, the event register holds every object the
  event gathered: Selector(referent="event") is all of them ("they", Angelic Guardian, the ones
  that changed zones since excluded, CR 400.7) and QProp("event", THAT_MANY_COUNT) their number
  ("that many", Woodland Champion, the ones that left included: its ruling). A gathered combat
  damage event keeps its one subject (Feline Sovereign).
- The IR refuses the flag on a zone change of one object (a second encoding), a read of one
  object of a gathered register ("its power"), and a count of a referent Selector (a second
  encoding of THAT_MANY_COUNT).

Every test here fails on the base, 30fabc4a, except the controls named in
``reports/one_or_more_2026-11-13/base_runs.txt``, which pin what the base already did right.
"""

from __future__ import annotations

import pytest

from MTG_bot.core import ability_tree as at
from MTG_bot.core.ability_tree import (
    Atom,
    AtomArgs,
    ControllerRef,
    CounterKind,
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
from MTG_bot.core.executor.events import KIND_COUNTER_PLACED, KIND_LIFE_GAINED, KIND_ZONE_CHANGE
from MTG_bot.core.executor.games import get_supply
from MTG_bot.core.state import ZONE_BATTLEFIELD, ZONE_GRAVEYARD, ZONE_HAND
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
    with pytest.raises(ValueError, match="reads one of them"):
        TriggeredAbility(event, None, one, once_per_event=True)
    with pytest.raises(ValueError, match="reads one of them"):
        at.DelayedTrigger(at.DurationEot(), event, None, one, True)
    # a reflexive trigger in it reads the same register (CR 603.12)
    when_you_do = at.Seq((
        at.OptionalEffect(_gain(QConst(1))),
        at.Conditional(FAtom(FAtomPred.MAY_DONE),
                       at.DelayedTrigger(None, None, None, one)),
    ))
    with pytest.raises(ValueError, match="reads one of them"):
        TriggeredAbility(event, None, when_you_do, once_per_event=True)
    # unflagged, the register holds the one object the event names; and the set and its size
    # are read under the flag
    TriggeredAbility(event, None, one)
    TriggeredAbility(event, None, _gain(THAT_MANY), once_per_event=True)
    grant = Atom(Verb.GRANT_ABILITY, AtomArgs(pairs=(
        ("ability", at.KeywordAbility(Keyword.INDESTRUCTIBLE)), ("duration", at.DurationEot()),
        ("target", referent_sel("event")))))
    TriggeredAbility(event, None, grant, once_per_event=True)


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

    def test_the_batch_stays_out_of_the_journal_dump(self) -> None:
        """Replays and forks re-derive the batch: the dump rows, so every fingerprint and game
        log, keep their bytes (control: the base's rows have the same six fields)."""
        self.ex.execute(_soldiers(2), source=self.watch, controller=self.p0)
        rows = [e for e in self.ex.journal.events if e.kind == KIND_ZONE_CHANGE]
        assert len(rows) == 2 and all(len(row) == 6 for row in self.ex.journal.dump())
        assert rows[0].batch == rows[1].batch == rows[0].clock


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
