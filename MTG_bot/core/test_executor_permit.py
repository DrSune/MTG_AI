"""Playing cards from another zone (ontology round R13, DESIGN_ATOM_ONTOLOGY §17): the engine side
of ``Verb.PERMIT`` (executor/permits.py), the menu's rows for it, the cast and land lanes, the
spell's rider, and the one-shot CAST's targets.

CR 601.3: a card is cast only where a rule or effect allows it; 305.1: a land is played from the
hand during your main phase with an empty stack, once a turn (305.2a counts a land played from
another zone too). A permission changes where from and at what cost, never when.

Required by the round's brief, each failing on the base (30736aba): an impulse play until end of
turn, then gone; a land played from another zone using the land drop; a spell cast from the
graveyard and exiled as it resolves (flashback, and Chandra, Flame's Catalyst's rider); a static
permission ending with its source while a resolving one outlives it; sorcery-speed permissions.
"""

from __future__ import annotations

from functools import cache

import pytest

from MTG_bot.core.executor.games import compile_supply
from MTG_bot.core.executor.menu import menu
from MTG_bot.core.state import ZONE_BATTLEFIELD, ZONE_EXILE, ZONE_GRAVEYARD, ZONE_HAND
from tools.run_scenarios import PackError, ScenarioRunner


@cache
def _supply(code: str):
    return compile_supply("all", code, require_verified=False)


def _runner(code: str, cards: list[dict], mana: dict | None = None) -> ScenarioRunner:
    pack = {"set": code, "world": {"life": 20, "seed": 7, "library_top": True}, "cards": cards,
            "steps": []}
    if mana:
        pack["mana"] = mana
    return ScenarioRunner(pack, _supply(code))


def _real(key, name, seat=0, zone="battlefield") -> dict:
    return {"key": key, "real": name, "zone": zone, "controller": seat}


def _zone(r: ScenarioRunner, key: str) -> str:
    return r.world.zone_of(r.handles[key]).kind


def _rows(r: ScenarioRunner, seat: int = 0) -> set[str]:
    """The seat's menu with each handle written as its pack key."""
    names = {str(h): k for k, h in r.handles.items()}
    words = set()
    for row in menu(r.ex, r.seats[seat]):
        token = row.token
        for handle, key in sorted(names.items(), key=lambda kv: -len(kv[0])):
            token = token.replace(handle, key)
        words.add(token)
    return words


def _act(r: ScenarioRunner, *words: str, seat: int = 0) -> None:
    r.run_step({"op": "act", "seat": seat, "words": list(words)})


# ------------------------------------------------------------------------------ impulse draw


#: Chandra, Heart of Fire's [+1] ("exile the top three cards of your library": the library pop, no target).
PLUS_ONE = {"op": "activate", "key": "ch", "idx": 0, "seat": 0}


def _chandra_heart_of_fire() -> ScenarioRunner:
    """Chandra, Heart of Fire on the battlefield; the top three cards of the library a Shock, a
    Mountain and a Goblin Arsonist (the last listed on top); a Forest in hand; {R}{R}{R} to spend."""
    return _runner(
        "M21",
        [
            _real("ch", "Chandra, Heart of Fire"),
            _real("shock", "Shock", zone="library"),
            _real("mtn", "Mountain", zone="library"),
            _real("gob", "Goblin Arsonist", zone="library"),
            _real("forest", "Forest", zone="hand"),
        ],
        {"0": {"R": 3}},
    )


def test_impulse_play_until_end_of_turn_then_gone() -> None:
    """[+1]: "Discard your hand, then exile the top three cards of your library. Until end of turn,
    you may play cards exiled this way." The exiled land is a land play from exile, the spells
    casts from exile, until the turn ends; on the next turn none is offered (CR 611.2a, 514.2)."""
    r = _chandra_heart_of_fire()
    r.run_step(PLUS_ONE)
    assert {_zone(r, k) for k in ("shock", "mtn", "gob")} == {ZONE_EXILE}
    assert _zone(r, "forest") == ZONE_GRAVEYARD  # discarded first
    rows = _rows(r)
    assert {"land:mtn", "cast:gob", "cast:shock"} <= rows, rows
    _act(r, "cast:gob")
    assert _zone(r, "gob") == ZONE_BATTLEFIELD
    r.run_step({"op": "advance_turn"})
    r.run_step({"op": "advance_turn"})  # seat 0's next turn
    assert _zone(r, "mtn") == ZONE_EXILE and _zone(r, "shock") == ZONE_EXILE
    assert not {"land:mtn", "cast:shock"} & _rows(r), _rows(r)


def test_a_resolving_permission_outlives_its_source() -> None:
    """CR 611.2a: the +1's permission is an effect of a resolved ability, not an ability of
    Chandra, so it lasts its turn after she leaves the battlefield."""
    r = _chandra_heart_of_fire()
    r.run_step(PLUS_ONE)
    r.run_step({"op": "move", "key": "ch", "to": "graveyard"})
    assert {"land:mtn", "cast:gob", "cast:shock"} <= _rows(r)


def test_a_card_that_leaves_its_zone_leaves_the_permission() -> None:
    """CR 400.7: an exiled card that moves is a new object the permission never named, back in
    exile or not."""
    r = _chandra_heart_of_fire()
    r.run_step(PLUS_ONE)
    r.run_step({"op": "move", "key": "shock", "to": "graveyard"})
    r.run_step({"op": "move", "key": "shock", "to": "exile"})
    assert "cast:shock" not in _rows(r) and "cast:gob" in _rows(r)


# ------------------------------------------------------------------------------ the land drop


def _radha(top: str = "Mountain") -> ScenarioRunner:
    return _runner(
        "M21",
        [_real("radha", "Radha, Heart of Keld"), _real("top", top, zone="library"),
         _real("forest", "Forest", zone="hand")],
    )


def test_a_land_played_from_the_top_of_the_library_is_the_land_drop() -> None:
    """Radha, Heart of Keld: "you may play lands from the top of your library". The land is played
    from the library (CR 116.2a), and it is the turn's land play (CR 305.2a): the land in hand is
    no longer offered, nor the next top card."""
    r = _radha()
    assert {"land:top", "land:forest"} <= _rows(r)
    _act(r, "land:top")
    assert _zone(r, "top") == ZONE_BATTLEFIELD
    assert not any(w.startswith("land:") for w in _rows(r)), _rows(r)
    with pytest.raises(PackError, match="does not offer|no ask took"):
        _act(r, "land:forest")


def test_a_land_played_from_hand_uses_the_drop_the_top_would_have() -> None:
    r = _radha()
    _act(r, "land:forest")
    assert "land:top" not in _rows(r)


def test_a_spell_on_top_is_not_played_through_a_lands_permission() -> None:
    """Radha permits lands only: a creature on top stays in the library."""
    r = _radha(top="Goblin Arsonist")
    r.run_step({"op": "mana", "seat": 0, "add": {"R": 1}})
    assert not any("top" in w for w in _rows(r))


def test_a_land_play_is_not_lost_to_an_older_cast_permission_with_the_same_cost() -> None:
    """A cast permission that also covers a land (Mystic Forge's "colorless spells": a land is
    colorless) offers the same plain cost path as Radha's "play lands"; one option per cost path is
    a cast's rule (R5-2 v3 point 6), so the land on top is still played through Radha's, though
    the Forge's permission is the older (the fresh-eyes review, finding 4)."""
    from MTG_bot.core.ability_tree import (
        AtomArgs, Atom, ControllerRef, FAtom, FAtomPred, FNot, QConst, QUnbounded, Selector,
        SelectorMode, StaticAbility, Verb, Zone, ZoneKind, ZonePosition,
    )
    from MTG_bot.core.executor import permits
    from MTG_bot.core.test_executor_binding import record_of

    r = _runner("M21", [{"key": "forge", "name": "Forge", "type": "Artifact", "zone": "battlefield",
                         "controller": 0},
                        _real("radha", "Radha, Heart of Keld", zone="hand"),
                        _real("top", "Mountain", zone="library")])
    colorless = Selector(QUnbounded(), SelectorMode.ALL,
                         FNot(inner=FAtom(pred=FAtomPred.COLOR_COUNT_GE, count=QConst(1))),
                         zones=(Zone(ZoneKind.LIBRARY, ControllerRef.YOU, ZonePosition.TOP),))
    forge = r.handles["forge"]
    r.ex.attach_card(forge, record_of(
        [StaticAbility(effect=Atom(verb=Verb.PERMIT, args=AtomArgs(pairs=(("source", colorless),))))],
        oid=r.world.cards[forge].identity.oracle_id))
    r.run_step({"op": "enter", "key": "radha"})  # Radha's permission is the newer
    path = permits.land_path(r.ex, r.seats[0], r.handles["top"])
    assert path is not None and path.source == r.handles["radha"]
    _act(r, "land:top")
    assert _zone(r, "top") == ZONE_BATTLEFIELD


# ------------------------------------------------------------------------------ the graveyard


def test_flashback_casts_from_the_graveyard_and_exiles_on_resolution() -> None:
    """FDN Think Twice, "Flashback {2}{U}": cast from the graveyard for its flashback cost (one
    row, ``via`` itself: the cost path is not its mana cost), it draws, then it is exiled instead
    of returning to the graveyard (CR 702.34a)."""
    r = _runner("FDN", [_real("tt", "Think Twice", zone="graveyard")], {"0": {"U": 3}})
    assert _rows(r) == {"cast:tt:via:tt"}
    _act(r, "cast:tt:via:tt")
    assert _zone(r, "tt") == ZONE_EXILE
    assert len(r.world.players[r.seats[0]].zone(ZONE_HAND).entries) == 1
    assert not r.world.players[r.seats[0]].mana_pool  # {2}{U} paid, not {1}{U}


def test_a_countered_flashback_spell_is_exiled_too() -> None:
    """Flashback's exile replaces the spell's move off the stack to anywhere (CR 702.34a): a
    countered one goes to exile, not to the graveyard to be cast again."""
    r = _runner("FDN", [_real("tt", "Think Twice", zone="graveyard"),
                        _real("neg", "Negate", seat=1, zone="hand")],
                {"0": {"U": 3}, "1": {"U": 2}})
    r.run_step({"op": "act", "seat": 0, "words": ["cast:tt:via:tt"], "hold": True})
    assert r.ex.stack.frames and r.ex.stack.frames[-1].handle == r.handles["tt"]
    r.run_step({"op": "cast", "key": "neg", "real": "Negate", "controller": 1, "targets": ["tt"]})
    assert _zone(r, "tt") == ZONE_EXILE


def test_flashback_needs_its_own_cost() -> None:
    """The flashback cost, not the mana cost: {1}{U} in the pool casts nothing."""
    r = _runner("FDN", [_real("tt", "Think Twice", zone="graveyard")], {"0": {"U": 2}})
    assert _rows(r) == set()


def test_chandra_flames_catalyst_recasts_a_targeted_spell_and_exiles_it() -> None:
    """M21 Chandra, Flame's Catalyst [-2]: "You may cast target red instant or sorcery card from
    your graveyard. If that spell would be put into your graveyard, exile it instead." The Shock
    is cast as the ability resolves (CR 608.2g), its own target chosen then (CR 601.2c; the base
    raised: the CAST atom had no target channel), and it is exiled as it resolves (the base put it
    back into the graveyard, B-99)."""
    r = _runner("M21", [_real("cf", "Chandra, Flame's Catalyst"),
                        _real("shock", "Shock", zone="graveyard")], {"0": {"R": 1}})
    r.run_step({"op": "activate", "key": "cf", "idx": 1, "seat": 0, "targets": ["shock"],
                "decisions": ["fire", "player:1"]})
    assert r.world.players[r.seats[1]].life == 18
    assert _zone(r, "shock") == ZONE_EXILE


def test_the_recast_spell_that_fizzles_is_exiled_too() -> None:
    """The [-2]'s Shock at a creature that leaves before it resolves: the spell doesn't resolve
    and leaves the stack for the graveyard (CR 608.2b), which its rider replaces (gate round 13's
    surviving mutant M10: no rider on a fizzle)."""
    r = _runner("M21", [_real("cf", "Chandra, Flame's Catalyst"),
                        _real("shock", "Shock", zone="graveyard"),
                        _real("bear", "Walking Corpse", seat=1)], {"0": {"R": 1}})
    r.run_step({"op": "activate", "key": "cf", "idx": 1, "seat": 0, "targets": ["shock"],
                "hold": True})
    r.run_step({"op": "resolve", "decisions": ["fire", "bear"]})  # the Shock is cast and waits
    assert [f.handle for f in r.ex.stack.frames] == [r.handles["shock"]]
    r.run_step({"op": "move", "key": "bear", "to": "hand", "hold": True})
    r.run_step({"op": "pass"})
    assert _zone(r, "shock") == ZONE_EXILE and _zone(r, "bear") == ZONE_HAND


def test_a_static_permission_reaches_only_the_zone_it_names() -> None:
    """M19 Crucible of Worlds: "You may play lands from your graveyard." A land in exile is not
    covered (gate round 13's surviving mutant M6: a static covering every zone)."""
    r = _runner("M19", [_real("cru", "Crucible of Worlds"),
                        _real("gl", "Mountain", zone="graveyard"),
                        _real("el", "Mountain", zone="exile")])
    rows = _rows(r)
    assert "land:gl" in rows and "land:el" not in rows, rows


def test_an_opponents_permission_is_not_yours() -> None:
    """The opponent's Crucible of Worlds lets its controller play lands from their graveyard,
    never you from yours (gate round 13's surviving mutant M7)."""
    r = _runner("M19", [_real("cru", "Crucible of Worlds", seat=1),
                        _real("gl", "Mountain", zone="graveyard")])
    assert "land:gl" not in _rows(r)


def test_an_uncounted_permission_is_used_before_a_counted_one() -> None:
    """Two permissions offer one card the same cost path, one with a single play (Idol of
    Endurance's) and one without: the cast uses the uncounted one, and the counted play is left
    for another card (gate round 13's surviving mutant M8: counted first)."""
    from MTG_bot.core.ability_tree import (
        Atom, AtomArgs, ControllerRef, Cost, DurationEot, FAnd, QConst, QUnbounded, Selector,
        SelectorMode, Verb, Zone, ZoneKind,
    )

    r = _runner("M21", [_real("a", "Goblin Arsonist", zone="exile")])
    seat = r.seats[0]
    exiled = Selector(QUnbounded(), SelectorMode.ALL, FAnd(()),
                      zones=(Zone(ZoneKind.EXILE, ControllerRef.YOU),))

    def free(count: int | None) -> Atom:
        roles = (("source", exiled), ("alternative", Cost()), ("duration", DurationEot()))
        if count is not None:
            roles += (("count", QConst(count)),)
        return Atom(verb=Verb.PERMIT, args=AtomArgs(pairs=roles))

    counted = r.ex.layers.register_permit(r.handles["a"], seat, free(1), (), DurationEot(), 1)
    uncounted = r.ex.layers.register_permit(r.handles["a"], seat, free(None), (), DurationEot(), None)
    assert _rows(r) == {"cast:a:via:a"}  # one option for one cost path
    _act(r, "cast:a:via:a")
    assert _zone(r, "a") == ZONE_BATTLEFIELD
    assert counted.uses == 1 and counted.status == "live" and uncounted.status == "live"


def test_demonic_embrace_casts_itself_from_the_graveyard_with_its_extra_costs() -> None:
    """M21 Demonic Embrace: "You may cast this card from your graveyard by paying 3 life and
    discarding a card in addition to paying its other costs." The card's own static works from the
    graveyard (CR 113.6f); its cost is {1}{B}{B}, 3 life and a discard (CR 601.2f)."""
    r = _runner("M21", [_real("de", "Demonic Embrace", zone="graveyard"),
                        _real("host", "Goblin Arsonist"),
                        _real("junk", "Forest", zone="hand")],
                {"0": {"B": 2, "C": 1}})
    _act(r, "cast:de:via:de")  # one creature: the enchant slot is forced
    assert _zone(r, "de") == ZONE_BATTLEFIELD and _zone(r, "junk") == ZONE_GRAVEYARD
    assert r.world.players[r.seats[0]].life == 17


# ------------------------------------------------------------------------------ static vs source


def _snoop() -> ScenarioRunner:
    return _runner("M21", [_real("snoop", "Conspicuous Snoop"),
                           _real("gob", "Goblin Arsonist", zone="library")], {"0": {"R": 1}})


def test_a_static_permission_ends_when_its_source_leaves() -> None:
    """Conspicuous Snoop's "You may cast Goblin spells from the top of your library" is its
    static's (CR 604.2, 611.3a): offered while the Snoop is on the battlefield, gone with it."""
    r = _snoop()
    assert "cast:gob" in _rows(r)
    r.run_step({"op": "move", "key": "snoop", "to": "graveyard"})
    assert "cast:gob" not in _rows(r)


def test_a_goblin_cast_from_the_top_resolves_onto_the_battlefield() -> None:
    r = _snoop()
    _act(r, "cast:gob")
    assert _zone(r, "gob") == ZONE_BATTLEFIELD


# ------------------------------------------------------------------------------ timing


def test_a_permission_keeps_the_cards_timing() -> None:
    """CR 601.3, 117.1a: a creature cast through a permission is cast at sorcery speed, so not
    while a spell waits on the stack, nor in the opponent's turn; an instant through the same kind
    of permission is cast whenever its controller holds priority."""
    r = _snoop()
    r.run_step({"op": "advance_turn"})  # the opponent's turn
    r.run_step({"op": "mana", "seat": 0, "add": {"R": 1}})
    assert "cast:gob" not in _rows(r)
    r = _chandra_heart_of_fire()
    r.run_step(PLUS_ONE)
    r.run_step({"op": "to_step", "step": "COMBAT"})
    r.run_step({"op": "mana", "seat": 0, "add": {"R": 1}})  # pools empty between steps, CR 500.5
    rows = _rows(r)
    assert "cast:shock" in rows and "cast:gob" not in rows and "land:mtn" not in rows, rows


# ------------------------------------------------------------------------------ count, cost paths


def test_idol_of_endurance_allows_one_cast_from_its_exile() -> None:
    """M21 Idol of Endurance's "{1}{W}, {T}: Until end of turn, you may cast a creature spell from
    among cards exiled with this artifact without paying its mana cost": one cast, later this
    turn at the creature's timing (the base cast at once, as the ability resolved)."""
    r = _runner(
        "M21",
        [_real("idol", "Idol of Endurance", zone="hand"),
         _real("a", "Goblin Arsonist", zone="graveyard"),
         _real("b", "Walking Corpse", zone="graveyard")],
        {"0": {"W": 1, "C": 1}},
    )
    r.run_step({"op": "enter", "key": "idol"})
    assert _zone(r, "a") == ZONE_EXILE and _zone(r, "b") == ZONE_EXILE
    r.run_step({"op": "activate", "key": "idol", "idx": 1, "seat": 0})
    assert _zone(r, "a") == ZONE_EXILE  # nothing cast as the ability resolved
    rows = _rows(r)
    assert {"cast:a:via:idol", "cast:b:via:idol"} <= rows, rows
    _act(r, "cast:a:via:idol")
    assert _zone(r, "a") == ZONE_BATTLEFIELD
    assert not any(w.startswith("cast:b") for w in _rows(r))


def test_omniscience_adds_a_free_path_beside_the_hand_path() -> None:
    """FDN Omniscience: "You may cast spells from your hand without paying their mana costs." A
    spell in hand has two rows: its mana cost and the free one (CR 118.9: an alternative cost is
    a choice, 601.2b)."""
    r = _runner("FDN", [_real("omni", "Omniscience"), _real("bolt", "Burst Lightning", zone="hand")],
                {"0": {"R": 1}})
    rows = _rows(r)
    assert {"cast:bolt", "cast:bolt:via:omni"} <= rows, rows
    _act(r, "cast:bolt:via:omni", "player:1")
    assert r.world.players[r.seats[0]].mana_pool == {"R": 1}  # nothing paid
    assert r.world.players[r.seats[1]].life == 18


def test_an_alternative_cost_with_x_announces_x() -> None:
    """CR 107.3b: X is 0 only when neither the mana cost nor an alternative cost with an X is paid.
    Primal Might ({X}{G}) cast from the graveyard through a permission for "{X}" announces X; for
    nothing at all, X is 0 (the fresh-eyes review, finding 7; no card of the 19 sets has such a
    cost yet)."""
    from MTG_bot.core.ability_tree import (
        Atom, AtomArgs, ControllerRef, Cost, CostManaGeneric, DurationEot, FAtom, FAtomPred, QUnbounded,
        QX, Selector, SelectorMode, Verb, Zone, ZoneKind,
    )
    from MTG_bot.core.executor import permits
    from MTG_bot.core.executor.legality import spell_castable

    r = _runner("M21", [_real("pm", "Primal Might", zone="graveyard")], {"0": {"C": 3}})
    seat, pm = r.seats[0], r.handles["pm"]
    own = Selector(QUnbounded(), SelectorMode.ALL, FAtom(pred=FAtomPred.IS_SOURCE),
                   zones=(Zone(ZoneKind.GRAVEYARD, ControllerRef.YOU),))
    for alternative, reason in ((Cost(parts=(CostManaGeneric(QX()),)), None),
                                (Cost(), "cast:x_unpaid")):
        atom = Atom(verb=Verb.PERMIT, args=AtomArgs(pairs=(
            ("source", own), ("alternative", alternative), ("duration", DurationEot()))))
        layer = r.ex.layers.register_permit(pm, seat, atom, (), DurationEot(), None)
        (path,) = [p for p in permits.cast_paths(r.ex, seat, pm) if p.layer is layer]
        got = spell_castable(r.ex, seat, pm, x=2, path=path)[0]
        if reason is None:
            assert got is None, got
        else:
            assert got is not None and got.startswith(reason), got
        layer.status = "expired"
