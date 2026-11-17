"""The soak's live-world invariant I1 (``soak.tokens_off_battlefield``, CR 704.5d, 111.7): it flags a
token outside the battlefield, and the soak games in which the engine before the bug-hunt fix
(7c5598f8^, KNOWLEDGE/2026-11-17/212 §2 A) left a dead token in a graveyard at a priority point
now leave none there."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
for _p in (HERE, HERE.parents[1] / "tools" / "audit"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import soak

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


@pytest.mark.parametrize(("code", "seed"), [("M20", 64), ("FDN", 27)])
def test_no_token_is_left_outside_the_battlefield_where_a_player_acts(code: str, seed: int) -> None:
    # On 7c5598f8^ these games tripped I1 ("token Soldier in graveyard", "token Dog in graveyard").
    result = soak.play_one((code, "verified", False, "stress", seed))
    assert result["crash"] is None
    assert [h["detail"] for h in result["hits"] if h["detector"] == "i1_tokens"] == []
