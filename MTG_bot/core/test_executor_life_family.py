"""The life family (2026-11-13, ontology round R8, gate round 8): a life-total threshold, "for the
first time each turn" on life events, and a replaced gain's amount.

- ``FAtomPred.LIFE_TOTAL_GE(who, count)``: your life total now is at least ``count`` (CR 119.1),
  whatever it started at (CR 103.4). "N or less life" is FNot(LIFE_TOTAL_GE(N + 1)), never a
  second predicate; ``who`` is YOU, the only reading printed.
- ``LifeGainedEvent.ordinal`` / ``LifeLostEvent.ordinal``: the Nth gain or loss of that player
  this turn, CardDrawnEvent.ordinal's contract, counted by the trigger binder. One loss is one
  source's damage to the player at once, or one effect's or payment's loss (CR 120.3a, 119.3,
  119.4): the creatures that damage a player in one combat damage step are that many losses, all
  at once (CR 510.2), exactly one of them the first.
- A life-gain replacement's action reads the replaced gain as the event's amount (CR 614.6:
  Angel of Vitality's "that much life plus 1"), and a gain of 0 is no event (CR 119.10).

Every test here but one fails on the base, 07bf26ff: the predicate, the ordinal and the templates
do not exist there, and the replacement's action raises "QProp referent 'event' only resolves
inside a trigger firing" (``reports/life_family_2026-11-13/base_runs.txt``). The exception,
``test_an_event_class_without_an_ordinal_takes_none``, pins that the event classes with no ordinal
still take none, true on both.
"""

from __future__ import annotations

import pytest

from MTG_bot.core import ability_tree as at
from MTG_bot.core.ability_tree import (
    Atom,
    AtomArgs,
    ControllerRef,
    FAtom,
    FAtomPred,
    FNot,
    Keyword,
    LifeGainedEvent,
    LifeLostEvent,
    QConst,
    Verb,
)
from MTG_bot.core.executor import Executor
from MTG_bot.core.executor.events import KIND_DAMAGE, KIND_LIFE_GAINED
from MTG_bot.core.executor.games import get_supply
from MTG_bot.core.executor.legality import ctx_for
from MTG_bot.core.executor.quantity import eval_filter
from MTG_bot.core.state import ZONE_BATTLEFIELD, GameWorld
from MTG_bot.core.test_executor_binding import card_id, record_of, referent_sel
from tools.audit import ontology_conformance as oc
from tools.run_scenarios import ScenarioRunner

YOU = ControllerRef.YOU
YOU_ARE = FAtom(FAtomPred.CONTROLLER_IS, who=YOU)


def life_ge(n: int, who=YOU) -> FAtom:
    return FAtom(FAtomPred.LIFE_TOTAL_GE, who=who, count=QConst(n))


def _world(start_life: int = 20):
    world = GameWorld(num_players=2, start_life=start_life, master_seed=13)
    p0, p1 = world.player_order
    alpha = world.add_card(card_id("Alpha", "2", "2"), p0, ZONE_BATTLEFIELD)
    beta = world.add_card(card_id("Beta", "1", "1"), p1, ZONE_BATTLEFIELD)
    return world, Executor(world), p0, p1, alpha, beta


def _gain(n: int) -> Atom:
    return Atom(Verb.GAIN_LIFE, AtomArgs(pairs=(("amount", QConst(n)), ("controller", YOU))))


def _lose(n: int) -> Atom:
    return Atom(Verb.LOSE_LIFE, AtomArgs(pairs=(("amount", QConst(n)), ("controller", YOU))))


def _runner(code: str, cards: list[dict], life: int = 20) -> ScenarioRunner:
    pack = {"set": code, "world": {"life": life, "seed": 7}, "cards": cards, "steps": []}
    return ScenarioRunner(pack, get_supply("all", code))


def _real(key: str, name: str, seat: int = 0, zone: str = "battlefield") -> dict:
    return {"key": key, "real": name, "zone": zone, "controller": seat}


def _creature(key: str, seat: int, power: str = "1", **extra) -> dict:
    return {"key": key, "name": key.title(), "type": "Creature — Bear", "power": power,
            "toughness": "3", "zone": "battlefield", "controller": seat, **extra}


def _plus_counters(r: ScenarioRunner, key: str) -> int:
    return r.world.cards[r.handles[key]].counters.get("PLUS_1_PLUS_1", 0)


# ------------------------------------------------------------------- LIFE_TOTAL_GE


def test_life_total_reads_one_players_life_now_both_ways_through_fnot() -> None:
    world, ex, p0, p1, alpha, _beta = _world()
    ctx = ctx_for(ex, source=alpha, controller=p0)
    at_least_25, at_most_24 = life_ge(25), FNot(life_ge(25))  # "24 or less life"
    at_most_25 = FNot(life_ge(26))  # "25 or less life"
    world.players[p1].life = 40  # the opponent's life is not mine
    for life, ge25, le24, le25 in ((25, True, False, True), (24, False, True, True),
                                   (26, True, False, False), (0, False, True, True)):
        world.players[p0].life = life
        assert eval_filter(at_least_25, alpha, ctx) is ge25, life
        assert eval_filter(at_most_24, alpha, ctx) is le24, life
        assert eval_filter(at_most_25, alpha, ctx) is le25, life
    world.players[p0].life = -3  # a life total can be negative (CR 119.6 ends the game later)
    assert eval_filter(FNot(life_ge(0)), alpha, ctx)
    assert not eval_filter(life_ge(0), alpha, ctx)


def test_life_total_is_not_the_lead_over_the_starting_life() -> None:
    """Not a second encoding of LIFE_LEAD_OVER_START_GE: in Commander (40 starting life, CR
    103.4c) "25 or more life" holds at the start, a 5-life lead does not (Angel of Vitality's
    ruling: "In formats where your life total doesn't start at 20, ... still applies if your
    life total is 25 or more")."""
    world, ex, p0, _p1, alpha, _beta = _world(start_life=40)
    ctx = ctx_for(ex, source=alpha, controller=p0)
    lead_5 = FAtom(FAtomPred.LIFE_LEAD_OVER_START_GE, count=QConst(5))
    assert eval_filter(life_ge(25), alpha, ctx) and not eval_filter(lead_5, alpha, ctx)
    world.players[p0].life = 45
    assert eval_filter(life_ge(25), alpha, ctx) and eval_filter(lead_5, alpha, ctx)
    world.players[p0].life = 25
    assert eval_filter(life_ge(25), alpha, ctx) and not eval_filter(lead_5, alpha, ctx)


@pytest.mark.parametrize(
    ("make", "message"),
    [
        (lambda: FAtom(FAtomPred.LIFE_TOTAL_GE, who=YOU), "requires slot 'count'"),
        (lambda: FAtom(FAtomPred.LIFE_TOTAL_GE, count=QConst(25)), "requires slot 'who'"),
        (lambda: FAtom(FAtomPred.LIFE_TOTAL_GE, who=YOU, count=QConst(-1)), "negative"),
        (lambda: FAtom(FAtomPred.LIFE_TOTAL_GE, who=YOU, count=QConst(25), string_value="x"),
         "does not take slot 'string_value'"),
        (lambda: FAtom(FAtomPred.LIFE_TOTAL_GE, who=YOU, count=QConst(25), inner_filter=YOU_ARE),
         "does not take slot 'inner_filter'"),
        # YOU is the only reading printed (gate round 8, M1). Several players would make "N or
        # less" through FNot read "each"; TARGET_PLAYER, TARGET_OPPONENT and a referent "target"
        # read one binding (three byte forms of one meaning), and a TARGET_* in a filter
        # designates nothing; "source" and "controller" are you again (CR 113.8).
        *[
            (lambda ref=ref: life_ge(10, ref), "who must be YOU")
            for ref in (ControllerRef.OPPONENT, ControllerRef.ANY, ControllerRef.ALL_OPPONENTS,
                        ControllerRef.DEFENDING_PLAYER, ControllerRef.OWNER,
                        ControllerRef.TARGET_PLAYER, ControllerRef.TARGET_OPPONENT)
        ],
        *[
            (lambda referent=referent: life_ge(10, referent_sel(referent)), "who must be YOU")
            for referent in ("target", "event", "result", "source", "controller")
        ],
        (lambda: life_ge(10, at.Selector(QConst(1), at.SelectorMode.CHOOSE, YOU_ARE,
                                          zones=(at.Zone(at.ZoneKind.BATTLEFIELD, YOU),))),
         "who must be YOU"),
    ],
)
def test_life_total_refuses_what_has_no_meaning(make, message) -> None:
    with pytest.raises(ValueError, match=message):
        make()


def test_life_total_round_trips_and_is_a_subject_free_qualifier() -> None:
    atom = life_ge(25)
    assert at.from_dict("FAtom", at.to_dict(atom)) == atom
    assert FAtomPred.LIFE_TOTAL_GE in oc.SUBJECT_FREE
    draw = Atom(Verb.DRAW, AtomArgs(pairs=(("amount", QConst(1)), ("controller", YOU))))

    def trig(event):
        return (at.TriggeredAbility(event=event, condition=None, effect=draw),)

    # its one slot on a life event is ``actor``; on a cast, ``filter`` (§11 R6-2)
    good = LifeLostEvent(actor=at.FAnd((YOU_ARE, atom)))
    assert oc.misplaced_qualifiers(trig(good)) == []
    bad = at.CastSpellEvent(filter=at.FAnd(()), actor=at.FAnd((YOU_ARE, atom)))
    assert oc.misplaced_qualifiers(trig(bad)) == ["CastSpellEvent.actor: LIFE_TOTAL_GE"]


# ------------------------------------------------------------------ the ordinal: the IR


_ORDINAL_EVENTS = {
    "LifeGainedEvent": lambda o: LifeGainedEvent(actor=YOU_ARE, ordinal=o),
    "LifeLostEvent": lambda o: LifeLostEvent(actor=YOU_ARE, ordinal=o),
    "CardDrawnEvent": lambda o: at.CardDrawnEvent(actor=YOU_ARE, ordinal=o),
    "CastSpellEvent": lambda o: at.CastSpellEvent(filter=at.FAnd(()), actor=YOU_ARE, ordinal=o),
}


@pytest.mark.parametrize("cls", ["LifeGainedEvent", "LifeLostEvent"])
@pytest.mark.parametrize("bad", [0, -1, True, "1", 1.0])
def test_a_life_ordinal_is_an_int_from_one(cls, bad) -> None:
    with pytest.raises(ValueError, match="ordinal must be an int >= 1"):
        _ORDINAL_EVENTS[cls](bad)


def test_an_event_class_without_an_ordinal_takes_none() -> None:
    with pytest.raises(TypeError):
        at.DamageDealtEvent(amount=at.QUnbounded(), filter=at.FAnd(()), ordinal=1)  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        at.SacrificeEvent(actor=YOU_ARE, ordinal=1)  # type: ignore[call-arg]
    damage = at.to_dict(at.DamageDealtEvent(amount=at.QUnbounded(), filter=at.FAnd(())))
    with pytest.raises(ValueError):
        at.from_dict("DamageDealtEvent", {**damage, "ordinal": 1})


@pytest.mark.parametrize("cls", sorted(_ORDINAL_EVENTS))
def test_an_ordinal_is_read_only_by_a_trigger(cls) -> None:
    """A history count says how much happened; an ordinal there would be a second byte form of
    the count, or a reading no card prints. No replacement or prevention lane counts events
    (gate round 8, m1: PREVENT_EFFECT's ``event`` role, resolving or static)."""
    event = _ORDINAL_EVENTS[cls](1)
    for pred in (FAtomPred.EVENT_THIS_TURN, FAtomPred.SUBJECT_OF_EVENT_THIS_TURN):
        if pred is FAtomPred.SUBJECT_OF_EVENT_THIS_TURN and cls == "CastSpellEvent":
            continue  # refused for another reason (WAS_CAST_THIS_TURN reads casts)
        with pytest.raises(ValueError, match="event ordinal is a trigger's"):
            FAtom(pred, event=event, count=QConst(1))
    with pytest.raises(ValueError, match="event ordinal is a trigger's"):
        at.ReplacementAbility(event=event, condition=None, action=_gain(1))
    with pytest.raises(ValueError, match="event ordinal is a trigger's"):
        Atom(Verb.PREVENT_EFFECT, AtomArgs(pairs=(("event", event),)))
    with pytest.raises(ValueError, match="event ordinal is a trigger's"):
        at.StaticAbility(effect=Atom(Verb.PREVENT_EFFECT, AtomArgs(pairs=(
            ("condition", YOU_ARE), ("event", _ORDINAL_EVENTS[cls](2))))))
    at.TriggeredAbility(event=event, condition=None, effect=_gain(1))  # where it belongs
    at.DelayedTrigger(duration=at.DurationEot(), event=event, condition=None, effect=_gain(1))


def test_an_absent_ordinal_keeps_every_trees_bytes() -> None:
    plain = LifeLostEvent(actor=YOU_ARE)
    assert "ordinal" not in at.to_dict(plain)
    first = LifeLostEvent(actor=YOU_ARE, ordinal=1)
    assert at.to_dict(first)["ordinal"] == 1
    assert at.from_dict("LifeLostEvent", at.to_dict(first)) == first
    assert at.fingerprint(first) != at.fingerprint(plain)
    gained = LifeGainedEvent(actor=YOU_ARE, ordinal=1)
    assert at.from_dict("LifeGainedEvent", at.to_dict(gained)) == gained


# ---------------------------------------------------------- the ordinal: the trigger binder


def test_warchief_counts_the_first_loss_of_each_turn_only() -> None:
    r = _runner("M20", [_real("chief", "Vengeful Warchief"), _creature("bear", 0)])
    chief, bear = r.handles["chief"], r.handles["bear"]
    r.ex.execute(_lose(2), source=bear, controller=r.p0)
    assert _plus_counters(r, "chief") == 1
    r.ex.execute(_lose(1), source=bear, controller=r.p0)  # the second loss this turn
    r.ex.execute(_lose(1), source=r.handles["bear"], controller=r.p1)  # the opponent's
    assert _plus_counters(r, "chief") == 1
    r.run_step({"op": "end_turn"})
    r.run_step({"op": "advance_turn"})
    r.ex.execute(_lose(1), source=bear, controller=r.p0)  # a new turn's first loss
    assert _plus_counters(r, "chief") == 2
    assert r.world.players[r.p0].life == 16 and r.world.zone_of(chief).kind == ZONE_BATTLEFIELD


def test_warchief_does_not_count_a_loss_from_before_it_arrived() -> None:
    """Its ruling: "If Vengeful Warchief comes under your control after you've already lost life
    in a turn, its ability can't trigger during that turn." The count is the turn's, not the
    permanent's."""
    r = _runner("M20", [_real("chief", "Vengeful Warchief", zone="hand"), _creature("bear", 0)])
    r.ex.execute(_lose(2), source=r.handles["bear"], controller=r.p0)
    r.run_step({"op": "enter", "key": "chief"})
    r.ex.execute(_lose(1), source=r.handles["bear"], controller=r.p0)
    assert _plus_counters(r, "chief") == 0
    r.run_step({"op": "end_turn"})
    r.run_step({"op": "advance_turn"})
    r.ex.execute(_lose(1), source=r.handles["bear"], controller=r.p0)
    assert _plus_counters(r, "chief") == 1


def test_three_attackers_in_one_damage_step_are_three_losses_one_of_them_first() -> None:
    """CR 120.3a: damage dealt to a player by a source makes that player lose that much life, so
    three unblocked creatures are three losses (one DAMAGE row each), dealt at once (CR 510.2):
    "the first time" is met once, and Warchief gets one counter, not three."""
    r = _runner("M20", [_real("chief", "Vengeful Warchief"),
                        *[_creature(f"a{i}", 1) for i in range(3)]])
    r.run_step({"op": "end_turn"})
    r.run_step({"op": "advance_turn"})
    r.run_step({"op": "combat", "seat": 1, "attack": {"a0": True, "a1": True, "a2": True}})
    losses = [e for e in r.ex.journal.turn_window()
              if e.kind == KIND_DAMAGE and e.subject == r.p0]
    assert len(losses) == 3 and {e.cause for e in losses} == {r.handles[f"a{i}"] for i in range(3)}
    assert len({e.combat_step for e in losses}) == 1  # one combat damage step
    assert r.world.players[r.p0].life == 17
    assert _plus_counters(r, "chief") == 1


def test_two_lifelinkers_at_once_are_two_gains_one_of_them_first() -> None:
    """ZNR Cleric of Life's Bond, "Whenever you gain life for the first time each turn": each
    creature with lifelink dealing combat damage is its own life-gain event (its ruling, CR
    119.9), so two lifelinkers are two gains and one counter."""
    r = _runner("ZNR", [_real("cleric", "Cleric of Life's Bond"),
                        _creature("l0", 0, keywords=["LIFELINK"]),
                        _creature("l1", 0, keywords=["LIFELINK"])])
    r.run_step({"op": "combat", "seat": 0, "attack": {"l0": True, "l1": True}})
    gains = [e for e in r.ex.journal.turn_window()
             if e.kind == KIND_LIFE_GAINED and e.subject == r.p0]
    assert len(gains) == 2 and r.world.players[r.p0].life == 22
    assert _plus_counters(r, "cleric") == 1
    r.ex.execute(_gain(1), source=r.handles["l0"], controller=r.p0)
    assert _plus_counters(r, "cleric") == 1


# One lifelink source's damage dealt at once is ONE life-gain event, whatever the number of
# recipients (CR 120.3f; the rulings of Ajani's Pridemate and Angel of Vitality: "if a single
# creature you control with lifelink deals combat damage to multiple creatures, players,
# planeswalkers, and/or battles at the same time ..., the ability will apply only once"). Each of
# these fails on 46aa2f3e, which made one gain per recipient
# (reports/life_family_2026-11-13/lifelink_cases.txt).


def _gains(r: ScenarioRunner) -> list[int]:
    return [e.amount for e in r.ex.journal.turn_window()
            if e.kind == KIND_LIFE_GAINED and e.subject == r.p0]


def _lifelinker(power: str, *keywords: str) -> dict:
    return _creature("lt", 0, power, toughness=power, keywords=["LIFELINK", *keywords])


@pytest.mark.parametrize(("angel", "life"), [(False, 25), (True, 26)])
def test_a_trampling_lifelinker_and_its_blocker_are_one_gain(angel, life) -> None:
    """A trampling 5/5 lifelinker blocked by a 0/2 assigns 2 to it and 3 to the player: one gain
    of 5 (with Angel of Vitality, of 6), one Pridemate counter. 46aa2f3e: rows 2 and 3 (3 and 4,
    27 life, with the Angel), 2 counters."""
    cards = [_lifelinker("5", "TRAMPLE"), _creature("wall", 1, "0", toughness="2"),
             _real("pm", "Ajani's Pridemate")]
    if angel:
        cards.append(_real("angel", "Angel of Vitality"))
    r = _runner("FDN", cards)
    r.run_step({"op": "combat", "seat": 0, "attack": {"lt": True}, "block": {"wall": "lt"},
                "trample": {"lt": [0]}})
    assert _gains(r) == [life - 20] and r.world.players[r.p0].life == life
    assert r.world.players[r.p1].life == 17
    assert _plus_counters(r, "pm") == 1


def test_a_lifelinker_blocked_by_two_creatures_is_one_gain() -> None:
    """A 4/4 lifelinker blocked by two 0/2s deals 2 to each at once: one gain of 4, one counter.
    46aa2f3e: rows 2 and 2, 2 counters."""
    r = _runner("FDN", [_lifelinker("4"), _creature("w1", 1, "0", toughness="2"),
                        _creature("w2", 1, "0", toughness="2"), _real("pm", "Ajani's Pridemate")])
    r.run_step({"op": "combat", "seat": 0, "attack": {"lt": True},
                "block": {"w1": "lt", "w2": "lt"}})
    assert _gains(r) == [4] and r.world.players[r.p0].life == 24
    assert _plus_counters(r, "pm") == 1


def test_one_lifelink_hit_on_two_creatures_is_one_replaced_gain() -> None:
    """Outside combat one DEAL_DAMAGE atom is one source's damage at once: 1 to each of two
    creatures is one gain of 2, which Angel of Vitality makes 3 (23 life), one Pridemate counter,
    and no trigger order to ask. 46aa2f3e: each per-target gain was replaced on its own, its action
    its own journal boundary: 24 life, 2 rows, 2 counters."""
    r = _runner("FDN", [_lifelinker("1"), _creature("b1", 1), _creature("b2", 1),
                        _real("pm", "Ajani's Pridemate"), _real("angel", "Angel of Vitality")])
    ping = Atom(Verb.DEAL_DAMAGE, AtomArgs(pairs=(
        ("amount", QConst(1)),
        ("target", at.Selector(QConst(2), at.SelectorMode.TARGET,
                               FAtom(FAtomPred.TYPE_EQ, string_value="Creature"),
                               zones=(at.Zone(at.ZoneKind.BATTLEFIELD, ControllerRef.ANY),))),
    )))
    r.ex.execute(ping, source=r.handles["lt"], controller=r.p0,
                 bindings={"target": [r.handles["b1"], r.handles["b2"]]})
    assert _gains(r) == [3] and r.world.players[r.p0].life == 23
    assert _plus_counters(r, "pm") == 1
    assert r.ex.damage == {r.handles["b1"]: 1, r.handles["b2"]: 1}


def test_a_double_striking_lifelinker_gains_once_per_damage_step() -> None:
    """The control, true before and after: each combat damage step is its own damage event (CR
    510.4), so a double striker's lifelink is two gains, and two counters."""
    r = _runner("FDN", [_lifelinker("2", "DOUBLE_STRIKE"), _real("pm", "Ajani's Pridemate")])
    r.run_step({"op": "combat", "seat": 0, "attack": {"lt": True}})
    assert _gains(r) == [2, 2] and r.world.players[r.p1].life == 16
    assert _plus_counters(r, "pm") == 2


def test_the_first_gain_during_each_of_your_turns() -> None:
    """FDN Cat Collector: "for the first time during each of your turns" is the first gain of the
    turn (ordinal 1) on your turn (TURN_OF YOU in the event's actor)."""
    r = _runner("FDN", [_real("cc", "Cat Collector"), _creature("bear", 0)])

    def cats() -> int:
        return sum(1 for h in r.world.cards if r.world.cards[h].identity.name == "Cat"
                   and r.world.zone_of(h).kind == ZONE_BATTLEFIELD)

    r.ex.execute(_gain(1), source=r.handles["bear"], controller=r.p0)
    r.ex.execute(_gain(1), source=r.handles["bear"], controller=r.p0)
    assert cats() == 1
    r.run_step({"op": "end_turn"})
    r.run_step({"op": "advance_turn"})  # the opponent's turn
    r.ex.execute(_gain(1), source=r.handles["bear"], controller=r.p0)
    assert cats() == 1


# ----------------------------------------------------- the replaced gain's amount (CR 614.6)

#: Angel of Vitality's replacement, built by hand: the engine fix alone, without the template.
PLUS_ONE = at.ReplacementAbility(
    event=LifeGainedEvent(actor=YOU_ARE),
    condition=None,
    action=Atom(Verb.GAIN_LIFE, AtomArgs(pairs=(
        ("amount", at.QBin(at.QBinOp.ADD, at.QProp("event", at.QPropField.AMOUNT), QConst(1))),
        ("controller", YOU),
    ))),
)


def test_a_life_gain_replacement_reads_the_replaced_amount() -> None:
    """The base's drain ran the action with no event: "QProp referent 'event' only resolves
    inside a trigger firing". The replaced gain is the event; a gain of 0 is none (CR 119.10)."""
    world, ex, p0, _p1, alpha, _beta = _world()
    ex.attach_card(alpha, record_of([PLUS_ONE], oid=world.cards[alpha].identity.oracle_id))
    ex.execute(_gain(3), source=alpha, controller=p0)
    assert world.players[p0].life == 24
    ex.execute(_gain(0), source=alpha, controller=p0)
    assert world.players[p0].life == 24
    rows = [(e.subject, e.amount, e.cause) for e in ex.journal.events if e.kind == KIND_LIFE_GAINED]
    assert rows == [(p0, 4, alpha)]  # the replaced gain never happened (CR 614.6)


def test_angel_of_vitality_gains_that_much_plus_one_once_per_gain() -> None:
    r = _runner("M20", [_real("angel", "Angel of Vitality"), _real("tb", "Twinblade Paladin"),
                        _creature("bear", 0)])
    bear = r.handles["bear"]
    r.ex.execute(_gain(3), source=bear, controller=r.p0)
    assert r.world.players[r.p0].life == 24
    gains = [e for e in r.ex.journal.turn_window() if e.kind == KIND_LIFE_GAINED]
    assert [(e.subject, e.amount) for e in gains] == [(r.p0, 4)]  # one gain event, of 4
    assert _plus_counters(r, "tb") == 1  # Twinblade's "whenever you gain life": once
    r.ex.execute(_gain(0), source=bear, controller=r.p0)  # CR 119.10: no event, no replacement
    assert r.world.players[r.p0].life == 24 and _plus_counters(r, "tb") == 1
    r.ex.execute(_gain(3), source=bear, controller=r.p1)  # "you": the opponent's gain is theirs
    assert r.world.players[r.p1].life == 23


def test_two_angels_each_add_one() -> None:
    """Its ruling: "If you control two Angels of Vitality and you would gain life, you gain that
    much life plus 2." The second applies to the event the first made (CR 614.5, 616.1)."""
    r = _runner("M20", [_real("a1", "Angel of Vitality"), _real("a2", "Angel of Vitality"),
                        _creature("bear", 0)])
    r.ex.execute(_gain(3), source=r.handles["bear"], controller=r.p0)
    assert r.world.players[r.p0].life == 25


def test_the_life_thresholds_follow_the_life_total() -> None:
    """Twinblade Paladin has double strike and Angel of Vitality gets +2/+2 exactly while their
    controller has 25 or more life."""
    r = _runner("M20", [_real("angel", "Angel of Vitality"), _real("tb", "Twinblade Paladin"),
                        _creature("bear", 0)], life=24)
    angel, tb, bear = r.handles["angel"], r.handles["tb"], r.handles["bear"]

    def state():
        pt = r.ex.ledger.effective_pt(r.world.cards[angel].identity, angel, r.world.cards[angel].counters)
        return r.ex.layers.keyword_of(tb, Keyword.DOUBLE_STRIKE), pt

    assert state() == (False, (2, 2))
    r.ex.execute(_lose(0), source=bear, controller=r.p1)  # an op: the layers recompute
    assert state() == (False, (2, 2))
    r.ex.execute(_gain(1), source=bear, controller=r.p0)  # 24 + 1 + 1 (the Angel) = 26
    assert r.world.players[r.p0].life == 26 and state() == (True, (4, 4))
    r.ex.execute(_lose(1), source=bear, controller=r.p0)  # 25: still
    assert state() == (True, (4, 4))
    r.ex.execute(_lose(1), source=bear, controller=r.p0)  # 24
    assert state() == (False, (2, 2))


# ------------------------------------------------------------------------------ the templates


@pytest.fixture(scope="module")
def registry():
    from MTG_bot.core.compiler.coverage import build_full_registry

    return build_full_registry()


def _one(registry, sentence: str):
    from MTG_bot.core.compiler.frames import compose

    matches = registry.match(sentence) or compose(sentence, registry)
    assert len(matches) == 1, [m.template.tid for m in matches]
    return matches[0]


def test_the_life_condition_phrases() -> None:
    from MTG_bot.core.compiler import conditions

    assert conditions.condition("you have 25 or more life") == life_ge(25)
    assert conditions.condition("you have seven or less life") == FNot(life_ge(8))


def test_as_long_as_reads_the_same_either_way_round(registry) -> None:
    """Twinblade Paladin and Angel of Vitality print the condition first and last; one meaning,
    one tree. "Gets +P/+T and has <keyword>" is Thieves' Guild Enforcer's effect, byte for byte."""
    first = _one(registry, "As long as you have 25 or more life, this creature gets +2/+2.").outcome
    last = _one(registry, "This creature gets +2/+2 as long as you have 25 or more life.").outcome
    assert first == last and first.ability.condition == life_ge(25)
    paladin = _one(registry, "As long as you have 25 or more life, this creature has double strike.")
    assert paladin.template.tid == "B14-as-long-as-self"
    grant = paladin.outcome.ability.effect
    assert grant.verb is Verb.GRANT_ABILITY
    assert grant.args.get("ability") == at.KeywordAbility(keyword=Keyword.DOUBLE_STRIKE)
    ours = _one(registry, "As long as you have 25 or more life, this creature gets +2/+1 and has "
                          "deathtouch.").outcome.ability.effect
    enforcer = _one(registry, "As long as an opponent has eight or more cards in their graveyard, "
                              "this creature gets +2/+1 and has deathtouch.").outcome.ability.effect
    assert at.canonical_json(ours) == at.canonical_json(enforcer)


def test_a_static_grants_its_keywords_in_one_order(registry) -> None:
    """One static's effects share a timestamp (CR 613.7): "has flying and lifelink" and "has
    lifelink and flying" are one tree, the grants sorted (gate round 8, m6)."""
    for head in ("this creature has", "this creature gets +5/+5 and has"):
        trees = {at.canonical_json(_one(registry, f"As long as you have 30 or more life, {head} "
                                                  f"{kws}.").outcome.ability)
                 for kws in ("flying and lifelink", "lifelink and flying")}
        assert len(trees) == 1, head
    grants = _one(registry, "As long as you have 30 or more life, this creature has vigilance, "
                            "lifelink, and flying.").outcome.ability.effect.steps
    assert [g.args.get("ability").keyword.name for g in grants] == ["FLYING", "LIFELINK",
                                                                    "VIGILANCE"]


def test_the_first_time_each_turn_is_an_ordinal(registry) -> None:
    chief = _one(registry, "Whenever you lose life for the first time each turn, put a +1/+1 "
                           "counter on this creature.").outcome.ability
    assert chief.event == LifeLostEvent(actor=YOU_ARE, ordinal=1)
    plain = _one(registry, "Whenever you gain life, put a +1/+1 counter on this creature.")
    assert plain.outcome.ability.event == LifeGainedEvent(actor=YOU_ARE)  # its bytes kept
    framed = _one(registry, "When you gain life for the first time each turn, draw a card.")
    assert framed.template.tid.startswith("B13-life+")
    assert framed.outcome.ability.event == LifeGainedEvent(actor=YOU_ARE, ordinal=1)
    yours = _one(registry, "Whenever you gain life for the first time during each of your turns, "
                           "draw a card.").outcome.ability.event
    turn_of = FAtom(FAtomPred.TURN_OF, who=YOU)
    assert yours == LifeGainedEvent(actor=at.FAnd((YOU_ARE, turn_of)), ordinal=1)
    assert oc.misplaced_qualifiers((framed.outcome.ability,)) == []


def test_that_much_life_plus_one_is_the_hand_built_replacement(registry) -> None:
    angel = _one(registry, "If you would gain life, you gain that much life plus 1 instead.")
    assert angel.outcome.ability == PLUS_ONE
