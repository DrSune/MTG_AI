"""A spell an effect moves off the stack leaves it as a spell does (gate round 13, items 3 and 4; a
bug-hunt fault, KNOWLEDGE 212): its frame ends, so it never resolves (the card in its new zone is a
new object, CR 400.7), and its rider replaces the move (flashback's exile from the stack to
anywhere, CR 702.34a). Before, `verbs._move_all` moved the card and left its frame on the stack:
Unsubstantiate (M21, verified) returning your own Shock to your hand let the Shock resolve anyway,
2 damage with the card back in hand, and a bounced flashback spell went to the hand."""

from __future__ import annotations

from functools import cache

from MTG_bot.core import ability_tree as at
from MTG_bot.core.executor.games import compile_supply
from MTG_bot.core.state import ZONE_BATTLEFIELD, ZONE_EXILE, ZONE_GRAVEYARD, ZONE_HAND, ZONE_LIBRARY
from tools.run_scenarios import ScenarioRunner


@cache
def _supply(code: str):
    return compile_supply("all", code, require_verified=False)


def _runner(cards: list[dict], mana: dict) -> ScenarioRunner:
    pack = {"set": "M21", "world": {"life": 20, "seed": 7}, "cards": cards, "mana": mana,
            "steps": []}
    return ScenarioRunner(pack, _supply("M21"))


def _real(key: str, name: str, seat: int = 0, zone: str = "hand") -> dict:
    return {"key": key, "real": name, "zone": zone, "controller": seat}


def _zone(r: ScenarioRunner, key: str) -> str:
    return r.world.zone_of(r.handles[key]).kind


def _frames(r: ScenarioRunner) -> list[str]:
    return [str(f.handle) for f in r.ex.stack.frames]


def test_your_own_spell_returned_to_your_hand_never_resolves() -> None:
    """Through the menu, as a dealt game asks it: Shock at the opponent's Walking Corpse, then
    Unsubstantiate on the Shock. The Shock is back in hand and the Corpse is unharmed."""
    r = _runner([_real("s", "Shock"), _real("u", "Unsubstantiate"),
                 _real("bear", "Walking Corpse", seat=1, zone="battlefield")],
                {"0": {"R": 1, "U": 1, "C": 1}})
    r.run_step({"op": "act", "seat": 0, "words": ["cast:s", "bear"], "hold": True})
    r.run_step({"op": "act", "seat": 0, "words": ["cast:u", "s"]})
    assert _zone(r, "s") == ZONE_HAND and _frames(r) == []
    assert _zone(r, "bear") == ZONE_BATTLEFIELD and not r.ex.damage


def test_a_creature_spell_returned_to_hand_never_enters() -> None:
    r = _runner([_real("bear", "Walking Corpse"), _real("u", "Unsubstantiate", seat=1)],
                {"0": {"B": 1, "C": 1}, "1": {"U": 1, "C": 1}})
    r.run_step({"op": "cast", "key": "bear", "real": "Walking Corpse", "hold": True})
    r.run_step({"op": "cast", "key": "u", "real": "Unsubstantiate", "controller": 1,
                "targets": ["bear"]})
    assert _zone(r, "bear") == ZONE_HAND and _frames(r) == []


def _held_shock(r: ScenarioRunner) -> None:
    r.run_step({"op": "cast", "key": "s", "real": "Shock", "targets": ["p1"], "hold": True})
    assert _frames(r) == [str(r.handles["s"])]


def _move_spell(r: ScenarioRunner, destination: at.Zone) -> None:
    any_zone = at.Zone(at.ZoneKind.ANY, at.ControllerRef.ANY)
    atom = at.Atom(verb=at.Verb.MOVE_ZONE, args=at.AtomArgs(pairs=(
        ("cards", at.Selector(at.QConst(1), at.SelectorMode.CHOOSE, at.FAnd(()), zones=(any_zone,),
                              referent="result")),
        ("destination", destination))))
    r.ex.apply_effect(atom, source=r.handles["s"], controller=r.seats[0],
                      bindings={"result": [r.handles["s"]]})


def test_a_spell_exiled_or_put_into_a_library_leaves_the_stack() -> None:
    for destination, zone in ((at.Zone(at.ZoneKind.EXILE, at.ControllerRef.OWNER), ZONE_EXILE),
                              (at.Zone(at.ZoneKind.LIBRARY, at.ControllerRef.OWNER), ZONE_LIBRARY)):
        r = _runner([_real("s", "Shock")], {"0": {"R": 1}})
        _held_shock(r)
        _move_spell(r, destination)
        assert _zone(r, "s") == zone and _frames(r) == []
        r.run_step({"op": "pass"})
        assert r.world.players[r.seats[1]].life == 20, zone  # it never resolved


def _ridden_shock(rider: at.ReplacementAbility) -> ScenarioRunner:
    """A Shock cast from the graveyard through a test permission carrying ``rider``, waiting on
    the stack at the opponent."""
    r = _runner([_real("s", "Shock", zone="graveyard"), _real("u", "Unsubstantiate", seat=1)],
                {"0": {"R": 1}, "1": {"U": 1, "C": 1}})
    own = at.Selector(at.QUnbounded(), at.SelectorMode.ALL, at.FAtom(pred=at.FAtomPred.IS_SOURCE),
                      zones=(at.Zone(at.ZoneKind.GRAVEYARD, at.ControllerRef.YOU),))
    permit = at.Atom(verb=at.Verb.PERMIT, args=at.AtomArgs(pairs=(
        ("source", own), ("count", at.QConst(1)), ("duration", at.DurationEot()), ("replace", rider))))
    r.ex.layers.register_permit(r.handles["s"], r.seats[0], permit, (), at.DurationEot(), 1)
    r.run_step({"op": "act", "seat": 0, "words": ["cast:s:via:s", "p1"], "hold": True})
    return r


def test_flashbacks_exile_replaces_a_return_to_hand() -> None:
    """CR 702.34a: "exile it instead of putting it anywhere else any time it would leave the
    stack" — Unsubstantiate's return included (the base put it into the hand, to be cast again)."""
    r = _ridden_shock(at.spell_rider(at.Zone(at.ZoneKind.ANY, at.ControllerRef.ANY)))
    r.run_step({"op": "cast", "key": "u", "real": "Unsubstantiate", "controller": 1,
                "targets": ["s"]})
    assert _zone(r, "s") == ZONE_EXILE and _frames(r) == []
    assert r.world.players[r.seats[1]].life == 20


def test_a_graveyard_rider_leaves_a_return_to_hand_alone() -> None:
    """"If that spell would be put into your graveyard, exile it instead" replaces only the move
    to the graveyard: returned to hand, the card goes to the hand."""
    r = _ridden_shock(at.spell_rider(at.Zone(at.ZoneKind.GRAVEYARD, at.ControllerRef.YOU)))
    r.run_step({"op": "cast", "key": "u", "real": "Unsubstantiate", "controller": 1,
                "targets": ["s"]})
    assert _zone(r, "s") == ZONE_HAND and _frames(r) == []
    assert _zone(r, "u") == ZONE_GRAVEYARD
    assert r.world.players[r.seats[1]].life == 20  # the Shock never resolved
