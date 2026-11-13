"""The scenario-pack runner's newer capabilities (tools/run_scenarios.py), each shown working and
shown refusing what it must refuse: a response window while a combat trigger waits, worlds of
three or more players, and a test permission to cast a card from a zone other than the hand.
A runner op that lets a pack pass wrongly is worse than a missing one, so the refusals are the
point, and the silent-pass guards (an expect lane the runner never reads, a decision word no ask
offers) are checked on the new ops too."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from MTG_bot.core.executor.events import KIND_CAST
from MTG_bot.core.executor.games import get_supply
from tools.run_scenarios import ScenarioRunner, run_pack

TWO = {"life": 20, "seed": 7}
THREE = {"life": 20, "seed": 7, "players": 3}
THEIR_TURN = [{"op": "end_turn"}, {"op": "advance_turn"}]


def _pack(pack: dict) -> dict:
    return {"set": "M21", "world": TWO, "cards": [], "steps": [], "expect": {}, **pack}


def _run(tmp_path: Path, pack: dict) -> list[str]:
    """run_pack's failures for ``pack``, [] when it passes."""
    path = tmp_path / "pack.json"
    path.write_text(json.dumps(_pack(pack)))
    return run_pack(path, get_supply("all", "M21"))


def _runner(pack: dict) -> ScenarioRunner:
    return ScenarioRunner(_pack(pack), get_supply("all", "M21"))


def _creature(key: str, seat: int, power: str = "2") -> dict:
    return {"key": key, "name": key.title(), "type": "Creature — Bear", "power": power,
            "toughness": power, "zone": "battlefield", "controller": seat}


def _card(key: str, name: str, zone: str, seat: int = 0) -> dict:
    return {"key": key, "real": name, "zone": zone, "controller": seat}


def _fails_with(fails: list[str], text: str) -> bool:
    return len(fails) == 1 and text in fails[0]


# ------------------------------------------------------- a response while a combat trigger waits

MANGARA = _card("m", "Mangara, the Diplomat", "battlefield")
DESTROY_B = [{"op": "move", "key": "b", "to": "graveyard"}]


def _mangara(**windows) -> dict:
    """Seat 1 attacks Mangara's controller with a and b."""
    combat = {"op": "combat", "seat": 1, "attack": {"a": True, "b": True}, **windows}
    return {"cards": [MANGARA, _creature("a", 1), _creature("b", 1)], "steps": [*THEIR_TURN, combat]}


def test_the_trigger_window_opens_with_the_attack_trigger_on_the_stack() -> None:
    """respond_to_triggers runs its steps at the declare attackers step's first priority point:
    Mangara's trigger is on the stack and nobody has passed. Destroyed there, b still counts by
    what it was attacking (Mangara's ruling), so seat 0 draws."""
    pack = _mangara(respond_to_triggers={"DECLARE_ATTACKERS": DESTROY_B})
    r = _runner(pack)
    for step in pack["steps"][:-1]:
        r.run_step(step)
    stacks = []
    run_step = r.run_step

    def spy(step: dict) -> None:
        stacks.append([(f.spell_kind, f.source) for f in r.ex.stack.frames])
        run_step(step)

    r.run_step = spy  # the window's steps run through it
    r._dispatch(pack["steps"][-1])
    assert stacks == [[("TRIGGERED", r.handles["m"])]]
    assert len(r.world.players[r.p0].zone("hand").entries) == 1
    assert r.world.zone_of(r.handles["b"]).kind == "graveyard"


@pytest.mark.parametrize(("lane", "life"), [("respond_to_triggers", 18), ("respond", 16)])
def test_a_response_while_the_trigger_waits_changes_its_resolution(tmp_path, lane, life) -> None:
    """Ornery Dilophosaur: "Whenever this creature attacks, if you control a creature with power
    4 or greater, this creature gets +2/+2 until end of turn." The 4/4 destroyed while the
    trigger waits makes its "if" false as it resolves (CR 603.4): 2 damage. In the empty-stack
    window the trigger has already resolved: 4."""
    combat = {"op": "combat", "seat": 0, "attack": {"dilo": True, "big": False},
              lane: {"DECLARE_ATTACKERS": [{"op": "move", "key": "big", "to": "graveyard"}]}}
    pack = {"cards": [_card("dilo", "Ornery Dilophosaur", "battlefield"), _creature("big", 0, "4")],
            "steps": [combat], "expect": {"life": {"1": life}, "zone": {"big": "graveyard"}}}
    assert _run(tmp_path, pack) == []


@pytest.mark.parametrize(("windows", "error"), [
    ({"respond_to_triggers": {"END_TURN": DESTROY_B}}, "'END_TURN' is not a combat step"),
    ({"respond_to_trigger": {"DECLARE_ATTACKERS": DESTROY_B}}, "unknown keys ['respond_to_trigger']"),
    ({"respond_to_triggers": {"COMBAT_DAMAGE": DESTROY_B}}, "no triggered ability waits at COMBAT_DAMAGE"),
    ({"attack": {"a": False, "b": False}, "respond_to_triggers": {"DECLARE_BLOCKERS": DESTROY_B}},
     "the step DECLARE_BLOCKERS never came"),
])
def test_a_combat_window_refuses_what_it_cannot_apply(tmp_path, windows, error) -> None:
    """A window at a step outside the combat, a misspelt window (skipped, the pack would pass
    without its response), a window where no trigger waits (it responds to nothing) and one at
    a step the combat never reaches each fail the pack."""
    fails = _run(tmp_path, _mangara(**windows))
    assert _fails_with(fails, error), fails


def test_the_silent_pass_guards_hold_in_a_trigger_window(tmp_path) -> None:
    """A word its ask does not offer, given in the window (Alchemist's Gift asks "0" or "1"
    for deathtouch or lifelink), and an expect lane the runner never reads fail the pack."""
    window = [{"op": "mana", "seat": 0, "add": {"B": 1}},
              {"op": "cast", "key": "gift", "targets": ["m"], "decisions": ["deathtouch"]}]
    pack = _mangara(respond_to_triggers={"DECLARE_ATTACKERS": window})
    pack["cards"].append(_card("gift", "Alchemist's Gift", "hand"))
    fails = _run(tmp_path, {**pack, "expect": {"hnd": {"0": 1}}})
    assert any("pack word 'deathtouch' not offered" in f for f in fails), fails
    assert any("never checks: ['hnd']" in f for f in fails), fails


# ------------------------------------------------------------------------- three or more players


@pytest.mark.parametrize("shock", [
    {"op": "cast", "key": "shock", "targets": ["p2"]},
    {"op": "act", "seat": 0, "words": ["cast:shock", "p2"]},  # the bench router, one seat of three
])
def test_a_three_player_world(tmp_path, shock) -> None:
    """Three seats: turns go round the table, nobody skips the first draw (CR 103.8c), and a
    "p2" target and the seat-2 lanes reach the third player. An expect lane the runner never
    reads still fails the pack."""
    pack = {"world": THREE, "cards": [_card("shock", "Shock", "hand")], "mana": {"0": {"R": 1}},
            "steps": [shock, *THEIR_TURN, *THEIR_TURN],
            "expect": {"life": {"0": 20, "1": 20, "2": 18}, "hand": {"0": 1, "1": 1, "2": 1},
                       "turn_seats": [0, 1, 2], "graveyard": {"0": ["Shock"], "2": []}}}
    assert _run(tmp_path, pack) == []
    unread = _run(tmp_path, {**pack, "expect": {**pack["expect"], "hands": {"2": 1}}})
    assert unread == ["expect lanes this runner never checks: ['hands']"]


@pytest.mark.parametrize(("pack", "error"), [
    ({"world": THREE, "expect": {"hand": {"3": 0}}}, "expect hand: no seat '3' in this 3-player world"),
    ({"world": THREE, "expect": {"life": {"-1": 20}}}, "expect life: no seat '-1'"),
    ({"expect": {"graveyard": {"2": []}}}, "expect graveyard: no seat '2' in this 2-player world"),
    ({"world": THREE, "cards": [_creature("x", 3)]}, "card 'x': no seat 3"),
    ({"world": THREE, "mana": {"0": {"R": 1}}, "cards": [_card("shock", "Shock", "hand")],
      "steps": [{"op": "cast", "key": "shock", "targets": ["p3"]}]}, "player word 'p3': no seat '3'"),
    ({"world": {**TWO, "player": 3}}, "world: unknown keys ['player']"),
    ({"world": {**TWO, "players": 1}}, "players must be a whole number of two or more"),
    ({"world": {**TWO, "players": "3"}}, "players must be a whole number of two or more"),
])
def test_a_seat_the_world_does_not_have_is_refused(tmp_path, pack, error) -> None:
    """A lane, card or target naming a seat the world lacks fails the pack instead of reading
    another seat (Python reads -1 as the last), and so does a misspelt or bad seat count."""
    fails = _run(tmp_path, pack)
    assert _fails_with(fails, error), fails


def test_a_loss_in_a_three_player_game_must_be_named(tmp_path) -> None:
    """With three players a loss does not end the game (the engine keeps the player in it), so
    a pack that does not say who lost fails; one that says so passes."""
    pack = {"world": THREE, "steps": [{"op": "life", "seat": 2, "set": 0}, {"op": "end_turn"}]}
    assert _run(tmp_path, pack) == ["lost[2]: seat 2 lost the game and the pack does not say so"]
    assert _run(tmp_path, {**pack, "expect": {"lost": {"2": True}}}) == []


# --------------------------------------------------------- casting from another zone by permission

PERMIT = {"op": "test_permission_cast", "from": "graveyard"}


def _cast_row(r: ScenarioRunner, key: str) -> tuple:
    """The card's last CAST row without its ordinal: (caster, kind, from zone, X, kicked)."""
    caster, _ordinal, *rest = [e.cast for e in r.ex.journal.events
                               if e.kind == KIND_CAST and e.subject == r.handles[key]][-1]
    return (caster, *rest)


def test_a_test_permission_cast_records_the_zone_as_a_real_permission_does() -> None:
    """Idol of Endurance's real permission casts one Walking Corpse from exile; the test
    permission casts another from exile. Both are cast (on the stack, paid or waived), journalled
    the same way, and resolve onto the battlefield."""
    r = _runner({"cards": [_card("idol", "Idol of Endurance", "hand"),
                           _card("wc1", "Walking Corpse", "graveyard"), _card("wc2", "Walking Corpse", "exile")]})
    for step in ({"op": "enter", "key": "idol"}, {"op": "mana", "seat": 0, "add": {"W": 1, "C": 1}},
                 {"op": "activate", "key": "idol", "idx": 1, "seat": 0, "decisions": ["fire", "wc1"]},
                 {"op": "mana", "seat": 0, "add": {"B": 1, "C": 1}},
                 {"op": "test_permission_cast", "key": "wc2", "from": "exile"}):
        r.run_step(step)
    assert _cast_row(r, "wc1") == _cast_row(r, "wc2") == (r.p0, "CREATURE", "exile", 0, False)
    assert [r.world.zone_of(r.handles[k]).kind for k in ("wc1", "wc2")] == ["battlefield", "battlefield"]
    assert not any(r.world.players[r.p0].mana_pool.values())  # wc2's {1}{B} was paid


def test_an_instant_is_cast_by_the_test_permission_on_any_turn(tmp_path) -> None:
    """A permission changes where a card is cast from, not when: Shock is cast from the
    graveyard on the opponent's turn and goes back there."""
    pack = {"cards": [_card("shock", "Shock", "graveyard")],
            "steps": [*THEIR_TURN, {"op": "mana", "seat": 0, "add": {"R": 1}},
                      {**PERMIT, "key": "shock", "targets": ["p1"]}],
            "expect": {"life": {"1": 18}, "zone": {"shock": "graveyard"},
                       "kick_rows": {"shock": {"from": "graveyard"}}}}
    assert _run(tmp_path, pack) == []


STT_MANA = {"op": "mana", "seat": 0, "add": {"U": 1, "C": 1}}
STT = {**PERMIT, "key": "stt"}


@pytest.mark.parametrize(("steps", "error"), [
    # a sorcery at instant speed is refused whatever let it be cast from the graveyard (CR 307.1)
    ([*THEIR_TURN, STT_MANA, STT], "illegal cast: window:not_your_turn"),
    ([{"op": "to_step", "step": "COMBAT"}, STT_MANA, STT], "illegal cast: window:phase"),
    ([STT_MANA, {"op": "mana", "seat": 0, "add": {"R": 1}},
      {"op": "cast", "key": "shock", "targets": ["p1"], "hold": True}, STT], "illegal cast: window:stack_nonempty"),
    # and so is a cast whose costs are not paid in full (CR 601.2h)
    ([STT], "illegal cast: cost: its total cost cannot be paid"),
    # the card is the caster's own and in the zone the permission names, a library's top card
    ([STT_MANA, {**STT, "from": "exile"}], "the card is in seat 0's graveyard, not the caster's exile"),
    ([STT_MANA, {**STT, "controller": 1}], "the card is in seat 0's graveyard, not the caster's graveyard"),
    ([STT_MANA, {"op": "test_permission_cast", "key": "deep", "from": "library"}], "cast from the top only"),
    # a zone nothing is cast from by permission, a land, and keys the lane cannot apply
    ([STT_MANA, {**STT, "from": "hand"}], "from 'hand'; it casts from ['exile', 'graveyard', 'library']"),
    ([{**PERMIT, "key": "plains"}], "illegal cast: cast:not_a_spell"),
    ([STT_MANA, {**STT, "kicked": True}], "keys it cannot apply ['kicked']"),
    ([STT_MANA, {**STT, "tap": True}], "keys it cannot apply ['tap']"),
])
def test_a_test_permission_cast_refuses_what_no_permission_allows(tmp_path, steps, error) -> None:
    cards = [_card("stt", "See the Truth", "graveyard"), _card("deep", "See the Truth", "library"),
             _card("shock", "Shock", "hand"), _card("plains", "Plains", "graveyard")]
    fails = _run(tmp_path, {"cards": cards, "steps": steps})
    assert _fails_with(fails, error), fails


@pytest.mark.parametrize(("words", "error"), [
    (["1"], None),
    (["deathtouch"], "pack word 'deathtouch' not offered"),
    (["1", "0"], "words no ask took: ['0']"),
])
def test_the_silent_pass_guards_hold_for_a_test_permission_cast(tmp_path, words, error) -> None:
    """Alchemist's Gift from the graveyard asks "0" (deathtouch) or "1" (lifelink): a word the
    ask does not offer fails the pack, and so does a word no ask takes."""
    cast = {**PERMIT, "key": "gift", "targets": ["bear"], "decisions": words}
    pack = {"cards": [_card("gift", "Alchemist's Gift", "graveyard"), _creature("bear", 0)],
            "mana": {"0": {"B": 1}}, "steps": [cast], "expect": {"power": {"bear": 3}}}
    fails = _run(tmp_path, pack)
    assert fails == [] if error is None else any(error in f for f in fails), fails
    unread = _run(tmp_path, {**pack, "expect": {"powr": {"bear": 3}}})
    assert any("never checks: ['powr']" in f for f in unread), unread
