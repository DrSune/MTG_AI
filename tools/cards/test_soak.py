"""The soak's live-world invariant I1 (``soak.tokens_off_battlefield``, CR 704.5d, 111.7-8): no token
outside the battlefield where the game loop stops. Bug hunt 2026-11-17 (KNOWLEDGE 212 §2 A): a dead
token stayed in a graveyard while a trigger named it, and random games under invariants missed it."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
for _p in (HERE, HERE.parents[1] / "tools" / "audit"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import soak

from MTG_bot.core.executor import Executor
from MTG_bot.core.executor.games import (
    TURN_CAP,
    RandomPolicy,
    _play,
    _setup_game,
    deal_decks,
    get_supply,
)
from MTG_bot.core.identity import CardIdentity
from MTG_bot.core.state import ZONE_BATTLEFIELD, ZONE_GRAVEYARD, GameWorld


def test_i1_flags_a_token_outside_the_battlefield_only() -> None:
    world = GameWorld()
    seat = world.player_order[0]
    oid = "00000000-0000-4000-8000-000000000001"
    token = world.add_card(CardIdentity(oid, "Soldier", is_token=True), seat, ZONE_BATTLEFIELD)
    world.add_card(CardIdentity(oid.replace("1", "2", 1), "Bear"), seat, ZONE_GRAVEYARD)
    assert soak.tokens_off_battlefield(world) == []
    world.move_card(token, world.players[seat].zone(ZONE_GRAVEYARD))
    assert soak.tokens_off_battlefield(world) == ["token Soldier in graveyard"]


def test_the_soak_reports_a_token_an_engine_fault_leaves_outside_the_battlefield(monkeypatch) -> None:
    monkeypatch.setattr(Executor, "_cease_tokens", lambda self: [])  # tokens never cease
    result = soak.play_one(("M21", "verified", False, "stress", 7))
    i1 = [h["detail"] for h in result["hits"] if h["detector"] == "i1_tokens"]
    assert "token Goblin Wizard in graveyard" in i1


@pytest.mark.parametrize(("code", "seed"), [("M21", 7), ("FDN", 91)])
def test_a_token_that_dies_with_a_trigger_naming_it_is_gone_where_a_player_acts(code: str, seed: int) -> None:
    """The soak's games (play_one) M21 7 and FDN 91 put a trigger on the stack that names a token
    off the battlefield (a dies trigger's dead Goblin Wizard, a life-gain trigger caused by a dead
    Cat), the shape of fault A: with the fault put back (7c5598f8^'s ``pending_references`` spared
    a token a waiting trigger's source, event subject or cause named), I1 fires in both, and in 4
    of 450 soak games (M21, M20, FDN seeds 1-150)."""
    supply = get_supply("verified", code)
    game = _setup_game(seed, supply, deal_decks(seed, 1409, supply, "stress"))
    off: set[str] = set()
    named: list[str] = []

    def stop(g, _boundary: str) -> bool:
        world, ex = g.world, g.executor
        off.update(soak.tokens_off_battlefield(world))
        for frame in ex.stack.frames:
            if frame.spell_kind != "TRIGGERED":
                continue
            event = frame.event
            for h in {frame.source, getattr(event, "subject", None), getattr(event, "cause", None)}:
                lki = ex.departed_lki.get(h)
                gone = h not in world.cards or world.zone_of(h).kind != ZONE_BATTLEFIELD
                if gone and lki is not None and lki.identity is not None and lki.identity.is_token:
                    named.append(lki.identity.name)
        return False

    _play(game, RandomPolicy(seed), game.world.player_order, TURN_CAP, stop_after=stop)
    assert named, "the game no longer has a trigger naming a dead token: pick the seed again"
    assert not off
