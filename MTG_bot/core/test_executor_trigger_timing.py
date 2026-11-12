"""When a trigger's parts are read (2026-11-12).

- A reflexive trigger ("When you do, ...", CR 603.12) triggers on what its resolution did and
  chooses its targets as it goes on the stack, after that action: ``DelayedTrigger`` with no
  duration and no event, gated by ``Conditional(MAY_DONE)``. An ability designates only its own
  targets (``ability_tree.own_nodes``): never those of a delayed, reflexive or granted ability.
- A qualifier that is part of the trigger event ("with two or more", "and at least two other
  creatures attack", "when there are four or more counters") is read once, as the event occurs:
  it is in the event's filter. Only an intervening "if" is the trigger's condition, read again
  as it resolves (CR 603.4); Mangara's is, and reads a departed attacker's last attack.

Every case below fails on the engine before the fix (the reflexive target was chosen with the
ability's own, and the qualifiers were re-checked as conditions).
"""

from __future__ import annotations

from functools import cache

import pytest

from MTG_bot.core.ability_tree import (
    Atom,
    AtomArgs,
    CardDrawnEvent,
    Conditional,
    ControllerRef,
    DelayedTrigger,
    DurationEot,
    FAtom,
    FAtomPred,
    QConst,
    Selector,
    SelectorMode,
    Seq,
    TriggeredAbility,
    Verb,
    Zone,
    ZoneKind,
    from_dict,
    to_dict,
)
from MTG_bot.core.executor.events import KIND_TARGETING
from MTG_bot.core.executor.games import compile_supply, get_supply
from MTG_bot.core.test_executor_binding import record_of
from tools.run_scenarios import ScenarioRunner

DRAW = Atom(Verb.DRAW, AtomArgs(pairs=(("amount", QConst(1)), ("controller", ControllerRef.YOU))))
TAP = Atom(Verb.TAP, AtomArgs(pairs=((
    "target", Selector(QConst(1), SelectorMode.TARGET, FAtom(FAtomPred.TYPE_EQ, string_value="Creature"),
                       zones=(Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),))),)))
YOU_DRAW = CardDrawnEvent(actor=FAtom(FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU))


def reflexive(effect) -> DelayedTrigger:
    return DelayedTrigger(duration=None, event=None, condition=None, effect=effect)


def when_you_do(effect) -> Conditional:
    return Conditional(pred=FAtom(FAtomPred.MAY_DONE), then_effect=reflexive(effect))


@cache
def _records(code: str):
    """The set's supply with every card record applied, verified or not (``cardtool runpack``)."""
    return compile_supply("all", code, require_verified=False)


def _runner(cards: list[dict], *, code: str = "M21", mana: dict | None = None, records: bool = False):
    pack = {"set": code, "world": {"life": 20, "seed": 7}, "cards": cards, "steps": [], "mana": mana or {}}
    return ScenarioRunner(pack, _records(code) if records else get_supply("all", code))


def _creature(key: str, seat: int, subtype: str = "Bear", **extra) -> dict:
    return {"key": key, "name": key.title(), "type": f"Creature — {subtype}", "power": "2",
            "toughness": "2", "zone": "battlefield", "controller": seat, **extra}


def _targeting_rows(r) -> list:
    return [e for e in r.ex.journal.events if e.kind == KIND_TARGETING and e.cause_verb == "TARGET"]


def _recording(r) -> list[tuple[str, tuple[str, ...]]]:
    """Every (site, vocabulary) the engine asks from now on, whoever answers it."""
    seen: list[tuple[str, tuple[str, ...]]] = []
    take = r.ex.decisions.take

    def recording(vocab, what, *, seat=None):
        seen.append((what, tuple(vocab)))
        return take(vocab, what, seat=seat)

    r.ex.decisions.take = recording
    return seen


# ------------------------------------------------------------------- the IR node


def test_a_reflexive_trigger_is_a_delayed_trigger_with_no_duration_and_no_event() -> None:
    node = reflexive(TAP)
    assert node.reflexive
    d = to_dict(node)
    assert "duration" not in d and "event" not in d  # a delayed trigger keeps both keys
    assert from_dict("DelayedTrigger", d) == node
    delayed = DelayedTrigger(duration=DurationEot(), event=YOU_DRAW, condition=None, effect=TAP)
    assert not delayed.reflexive and {"duration", "event"} <= set(to_dict(delayed))
    with pytest.raises(ValueError, match="both set"):
        DelayedTrigger(duration=DurationEot(), event=None, condition=None, effect=TAP)
    with pytest.raises(ValueError, match="both set"):
        DelayedTrigger(duration=None, event=YOU_DRAW, condition=None, effect=TAP)
    with pytest.raises(ValueError, match="no condition and no once_per_event"):
        DelayedTrigger(duration=None, event=None, condition=FAtom(FAtomPred.IS_SOURCE), effect=TAP)
    with pytest.raises(ValueError, match="no condition and no once_per_event"):
        DelayedTrigger(duration=None, event=None, condition=None, effect=TAP, once_per_event=True)


def test_a_reflexive_trigger_stands_only_as_the_then_effect_of_its_gate() -> None:
    """One encoding: the Conditional names the action it triggers on; a bare reflexive trigger
    would be a second encoding of one whose action always happens."""
    def card(effect):
        return record_of((TriggeredAbility(event=YOU_DRAW, condition=None, effect=effect),))

    card(Seq(steps=(DRAW, when_you_do(TAP))))
    for bare in (Seq(steps=(DRAW, reflexive(TAP))), reflexive(TAP),
                 Conditional(pred=FAtom(FAtomPred.MAY_DONE), then_effect=DRAW, else_effect=reflexive(TAP))):
        with pytest.raises(ValueError, match="reflexive DelayedTrigger"):
            card(bare)


# ------------------------------------------------------- reflexive triggers (CR 603.12)

KRAKEN = {"key": "k", "real": "Tolarian Kraken", "zone": "battlefield", "controller": 0}


def test_kraken_offers_the_payment_first_and_targets_among_what_is_left() -> None:
    """The draw trigger designates nothing: removing a creature while it waits changes nothing
    about it. It offers the {1}; the reflexive trigger then chooses among the creatures there."""
    r = _runner([KRAKEN, _creature("sheep", 0, "Sheep"), _creature("goat", 1, "Goat"),
                 {"key": "rev", "real": "Revitalize", "zone": "hand", "controller": 0}],
                mana={"0": {"W": 3}})
    r.run_step({"op": "cast", "key": "rev", "hold": True})
    r.run_step({"op": "resolve", "hold": True})  # the draw: the Kraken's trigger waits, unasked
    assert [f.spell_kind for f in r.ex.stack.frames] == ["TRIGGERED"] and not _targeting_rows(r)
    r.run_step({"op": "move", "key": "goat", "to": "graveyard", "decisions": ["fire", "sheep", "fire", "0"]})
    asks = [(what.split(":")[0], vocab) for what, vocab in r.asks_seen]
    assert asks[0] == ("may", ("fire", "skip"))  # the payment, first
    assert asks[1] == ("target", tuple(sorted((str(r.handles["k"]), str(r.handles["sheep"])))))
    assert not r.unoffered
    assert r.world.cards[r.handles["sheep"]].tapped and not r.world.cards[r.handles["k"]].tapped


def test_kraken_pays_with_no_legal_target_and_its_reflexive_trigger_is_removed() -> None:
    """The Kraken alone, with protection from blue: the {1} is still offered and paid; the
    reflexive trigger then has no legal target and is removed (CR 603.3d)."""
    r = _runner([KRAKEN, {"key": "feat", "real": "Feat of Resistance", "zone": "hand", "controller": 0},
                 {"key": "ct", "real": "Crash Through", "zone": "hand", "controller": 0}],
                mana={"0": {"W": 1, "R": 1, "C": 1}})
    r.run_step({"op": "cast", "key": "feat", "targets": ["k"], "decisions": ["1"]})
    r.run_step({"op": "cast", "key": "ct", "hold": True})
    r.run_step({"op": "resolve"})
    r.run_step({"op": "mana", "seat": 0, "add": {"C": 1}, "hold": True})
    assert [f.spell_kind for f in r.ex.stack.frames] == ["TRIGGERED"]  # not removed: no target
    r.run_step({"op": "resolve", "hold": True, "decisions": ["fire"]})
    assert [(what.split(":")[0], vocab) for what, vocab in r.asks_seen][-1] == ("may", ("fire", "skip"))
    assert not r.unoffered and not r.ex.stack.frames  # the reflexive trigger was removed
    assert not any(r.world.players[r.p0].mana_pool.values())  # the {1} was paid
    assert not [e for e in _targeting_rows(r) if e.data[0] == r.handles["k"]]


SORIN = {"key": "sorin", "real": "Sorin, Imperious Bloodlord", "zone": "battlefield", "controller": 0,
         "counters": {"LOYALTY": 4}}


def test_sorin_chooses_the_reflexive_target_after_the_sacrifice() -> None:
    """M20 Sorin, Imperious Bloodlord's +1 (its card record), activated as a dealt game asks it:
    the activation asks no target; the sacrifice is offered as it resolves, and "any target" is
    chosen as the reflexive trigger goes on the stack, so the sacrificed Vampire is never offered
    (Sorin's ruling)."""
    r = _runner([SORIN, _creature("vamp", 0, "Vampire"), _creature("bear", 1)], code="M20", records=True)
    seen = _recording(r)
    r.run_step({"op": "act", "seat": 0, "words": ["act:sorin:1", "fire", "bear"]})
    kinds = [what.split(":")[0] for what, _vocab in seen]
    assert kinds.index("may") < kinds.index("target")
    target_vocab = next(vocab for what, vocab in seen if what.startswith("target:"))
    assert str(r.handles["vamp"]) not in target_vocab and str(r.handles["bear"]) in target_vocab
    zone = {k: r.world.zone_of(r.handles[k]).kind for k in ("vamp", "bear")}
    assert zone == {"vamp": "graveyard", "bear": "graveyard"}
    assert r.world.players[r.p0].life == 23


def test_sorin_declining_the_sacrifice_designates_nothing() -> None:
    """Declined, nothing triggers: no target is asked and no targeting event happens."""
    r = _runner([SORIN, _creature("vamp", 0, "Vampire"), _creature("bear", 1)], code="M20", records=True)
    seen = _recording(r)
    r.run_step({"op": "act", "seat": 0, "words": ["act:sorin:1", "skip"]})
    assert not any(what.startswith("target:") for what, _vocab in seen)
    assert not _targeting_rows(r)
    assert r.world.players[r.p0].life == 20 and r.world.zone_of(r.handles["vamp"]).kind == "battlefield"


def test_cavalier_of_night_may_sacrifice_with_no_opposing_creature() -> None:
    """M20 Cavalier of Night (its card record): the enters trigger has no target, so with no
    opposing creature it still offers the sacrifice; the reflexive trigger is then removed."""
    r = _runner([{"key": "cav", "real": "Cavalier of Night", "zone": "hand", "controller": 0},
                 _creature("fodder", 0)], code="M20", mana={"0": {"B": 5}}, records=True)
    r.run_step({"op": "cast", "key": "cav", "decisions": ["fire"]})
    assert not r.unoffered and not r.ex.stack.frames
    assert r.world.zone_of(r.handles["fodder"]).kind == "graveyard"


def test_sorin_vampire_lord_minus_eight_designates_nothing_it_grants() -> None:
    """M20 Sorin, Vampire Lord's -8 (verified, tree unchanged): "Until end of turn, each Vampire
    you control gains '{T}: Gain control of target creature.'" The granted ability's target is
    its own, chosen when it is activated: the -8 asks nothing, and the grant goes to each
    Vampire you control. Before, the -8 designated a creature and granted it to that one."""
    r = _runner([{"key": "svl", "real": "Sorin, Vampire Lord", "zone": "battlefield", "controller": 0,
                  "counters": {"LOYALTY": 8}},
                 _creature("vamp", 0, "Vampire"), _creature("bear", 1)], code="M20")
    r.run_step({"op": "act", "seat": 0, "words": ["act:svl:2"]})  # a target ask would find no word
    assert r.ex.layers.granted_activated(r.handles["vamp"])
    assert not r.ex.layers.granted_activated(r.handles["bear"])


# ------------------------------------------- event qualifiers are read once (CR 603.4)


def _attack(r, seat, attack: dict, interfere) -> None:
    """``seat`` declares the attack (``{key: True}`` attacks the player, a planeswalker's key
    attacks it); the triggers it causes wait (binder.hold) while ``interfere(r)`` runs, then go
    on the stack and resolve."""
    words = {f"attack:{r.handles[k]}": ("ATTACK" if v is True else str(r.handles[v]))
             for k, v in attack.items()}

    def answer(vocab, what):
        got = next((v for k, v in words.items() if what.startswith(k + ":")), None)
        if got is None:
            got = "DECLINE" if what.startswith("attack:") else ("NONE" if what.startswith("block:") else vocab[0])
        assert got in vocab, (what, got, vocab)
        return got

    r.ex.decisions.provider = answer
    try:
        r.ex.binder.hold = True
        r.ex.combat_attacks(seat)
        r.ex.binder.on_events()
        assert len(r.world.triggers) == 1, "the attack trigger waits"
        interfere(r)
        r.ex.decisions.provider = answer  # a pack step resets it
        r.ex.binder.hold = False
        r.ex.fire_triggers()
        r.ex.combat_blocks(seat)
    finally:
        r.ex.decisions.provider = None
        r.ex.binder.hold = False


def _gone(key: str):
    def move(r) -> None:
        r.run_step({"op": "move", "key": key, "to": "graveyard"})
    return move


def _flyer(key: str) -> dict:
    return _creature(key, 0, "Bird", keywords=["FLYING"])


def _hand(r, seat) -> int:
    return len(r.world.players[seat].zone("hand").entries)


def test_tide_skimmer_draws_when_a_flyer_leaves_before_its_trigger_resolves() -> None:
    """"Whenever you attack with two or more creatures with flying": the count is part of the
    trigger event (its ruling: "You draw a card even if some or all of the attacking creatures
    lose flying or leave combat")."""
    r = _runner([{"key": "skim", "real": "Tide Skimmer", "zone": "battlefield", "controller": 0},
                 _flyer("bird")])
    before = _hand(r, r.p0)
    _attack(r, r.p0, {"skim": True, "bird": True}, _gone("bird"))
    assert _hand(r, r.p0) == before + 1


def test_makeshift_battalion_counter_when_an_attacker_leaves_before_its_trigger_resolves() -> None:
    """"Whenever this creature and at least two other creatures attack" (its ruling: "it doesn't
    matter how many creatures are still attacking when that ability resolves")."""
    r = _runner([{"key": "bat", "real": "Makeshift Battalion", "zone": "battlefield", "controller": 0},
                 _creature("a", 0), _creature("b", 0)])
    _attack(r, r.p0, {"bat": True, "a": True, "b": True}, _gone("b"))
    assert r.world.cards[r.handles["bat"]].counters.get("PLUS_1_PLUS_1") == 1


MANGARA = {"key": "m", "real": "Mangara, the Diplomat", "zone": "battlefield", "controller": 0}
WALKER = {"key": "pw", "name": "Walker", "type": "Legendary Planeswalker — Test", "loyalty": "5",
          "counters": {"LOYALTY": 5}, "zone": "battlefield", "controller": 0}


def _mangara_game(attack: dict, interfere) -> int:
    """Seat 1 attacks seat 0 (Mangara's controller); returns seat 0's draws from the trigger."""
    r = _runner([MANGARA, WALKER, _creature("a", 1), _creature("b", 1)])
    r.run_step({"op": "advance_turn"})
    before = _hand(r, r.p0)
    _attack(r, r.p1, attack, interfere)
    return _hand(r, r.p0) - before


def test_mangara_counts_an_attacker_that_left_by_what_it_was_attacking() -> None:
    """Mangara's "if two or more of those creatures are attacking you and/or planeswalkers you
    control" IS an intervening "if" (its Oracle text), read again as it resolves; its ruling: an
    attacker that left the battlefield counts by what it was attacking before it left."""
    assert _mangara_game({"a": True, "b": True}, _gone("b")) == 1


def test_mangara_does_not_count_an_attack_on_a_planeswalker_you_no_longer_control() -> None:
    """The walker b attacks changes control while the trigger waits: b no longer attacks a
    planeswalker you control (it is removed from combat, CR 506.4), so one is left: no card."""
    def steal(r) -> None:
        atom = Atom(Verb.GAIN_CONTROL, AtomArgs(pairs=(
            ("controller", ControllerRef.YOU),
            ("target", Selector(QConst(1), SelectorMode.TARGET, FAtom(FAtomPred.IS_PERMANENT),
                                zones=(Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),))))))
        r.ex.execute(atom, source=r.handles["a"], controller=r.p1, bindings={"target": r.handles["pw"]})
        assert r.ex.controller_of(r.handles["pw"]) == r.p1

    assert _mangara_game({"a": True, "b": "pw"}, steal) == 0


def test_mazemind_tome_exiles_when_its_counters_drop_before_its_trigger_resolves() -> None:
    """"When there are four or more page counters on this artifact, exile it" is a state
    trigger (CR 603.8): the threshold is not re-read as it resolves."""
    r = _runner([{"key": "tome", "real": "Mazemind Tome", "zone": "battlefield", "controller": 0,
                  "counters": {"PAGE": 3}}], mana={"0": {"C": 2}})
    r.run_step({"op": "activate", "key": "tome", "idx": 1, "seat": 0, "hold": True})
    # the fourth counter is paid as the cost: the trigger waits above the ability
    assert [f.spell_kind for f in r.ex.stack.frames] == ["ACTIVATED", "TRIGGERED"]
    r.world.cards[r.handles["tome"]].counters["PAGE"] = 1  # counters removed in response
    r.run_step({"op": "pass"})
    assert r.world.zone_of(r.handles["tome"]).kind == "exile"
    assert r.world.players[r.p0].life == 24
