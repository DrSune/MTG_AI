"""The soak's live-world invariant I1 (``soak.tokens_off_battlefield``, CR 704.5d, 111.7-8): no token
outside the battlefield where the game loop stops. Bug hunt 2026-11-17 (KNOWLEDGE 212 §2 A): a dead
token stayed in a graveyard while a trigger named it, and random games under invariants missed it.

What the soak finds on whole runs (reports/guards_400_7_2026-11-17/soak_counts.txt): 6 of 900
games on 7c5598f8^, 0 of 900 since, and 4 of 450 with fault A put back into the fixed engine
(make_mutant_a.py). Seeds that show fault A are not pinned here: a verification wave re-deals the
pools and moves them (FDN 91 lost its dead Cat at main 1fb4463f)."""

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
from MTG_bot.core.identity import CardIdentity
from MTG_bot.core.state import ZONE_BATTLEFIELD, ZONE_GRAVEYARD, GameWorld


def _i1(result: dict) -> list[str]:
    return [h["detail"] for h in result["hits"] if h["detector"] == "i1_tokens"]


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
    for seed in range(1, 11):  # the first game in which a token leaves the battlefield
        found = _i1(soak.play_one(("M21", "verified", False, "stress", seed)))
        if found:
            break
    assert found and all(line.startswith("token ") for line in found)


@pytest.mark.parametrize("code", ["M21", "M20", "FDN"])
def test_soak_games_leave_no_token_outside_the_battlefield(code: str) -> None:
    result = soak.play_one((code, "verified", False, "stress", 1))
    assert result["crash"] is None
    assert _i1(result) == []
