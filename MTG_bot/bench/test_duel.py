"""Duplicate-format duels: deterministic, paired on the same deal, honest about voids."""

from __future__ import annotations

import pytest

from MTG_bot.bench.agents import AgentForfeitError, PassAgent, UniformRandomAgent
from MTG_bot.bench.duel import DealSpec, _settle_manifest, run_match, summarize
from MTG_bot.bench.router import SeatRouter
from MTG_bot.utils import rng

DEALS = [DealSpec(seed=s, turn_cap=20) for s in (1, 2)]


def uniform(deal: DealSpec, game: int, seat: int) -> UniformRandomAgent:
    return UniformRandomAgent(rng.substream("bench", deal.seed, game, seat))


def passive(deal: DealSpec, game: int, seat: int) -> PassAgent:
    return PassAgent()


def _strip(rows):
    return [{k: v for k, v in r.items() if k not in ("wall_s", "argv")} for r in rows]


def test_a_match_is_reproducible_and_each_pair_shares_its_deal() -> None:
    rng.seed_all(5, seed_frameworks=False)
    first = run_match(uniform, passive, DEALS, name_a="uniform", name_b="pass")
    rng.seed_all(5, seed_frameworks=False)
    second = run_match(uniform, passive, DEALS, name_a="uniform", name_b="pass")
    assert _strip(first) == _strip(second)
    games = [r for r in first if r["kind"] == "game"]
    assert len(games) == 4
    for deal in (1, 2):
        pair = [r for r in games if r["deal"] == deal]
        assert {r["a_seat"] for r in pair} == {0, 1}  # seats swapped
        assert pair[0]["setup_fp"] == pair[1]["setup_fp"]  # identical deal


def test_pass_against_itself_is_all_cap_draws_at_exactly_half() -> None:
    # The instrument's own null test: two do-nothing agents can produce nothing but draws.
    rows = run_match(passive, passive, DEALS, name_a="pass", name_b="pass")
    summary = summarize(rows)
    assert summary["outcomes"] == {"draw-cap": 4}
    assert summary["pair_score"][0] == 0.5


def test_uniform_beats_pass_on_the_same_deals() -> None:
    rng.seed_all(7, seed_frameworks=False)
    deals = [DealSpec(seed=s, turn_cap=30) for s in range(1, 4)]
    summary = summarize(
        run_match(uniform, passive, deals, name_a="uniform", name_b="pass")
    )
    assert summary["pair_score"][0] > 0.5
    assert summary["outcomes"].get("win", 0) > summary["outcomes"].get("loss", 0)


class _BrokenAgent:
    name = "broken"

    def decide(self, ask, obs) -> int:
        return len(ask.options)  # out of range


def test_a_protocol_breach_voids_the_pair_and_is_never_scored() -> None:
    rows = run_match(
        lambda d, g, s: _BrokenAgent(),
        passive,
        DEALS[:1],
        name_a="broken",
        name_b="pass",
    )
    games = [r for r in rows if r["kind"] == "game"]
    assert {r["outcome"] for r in games} == {"void-agent"}
    assert all(r["pair_void"] and r["score_a"] is None for r in games)
    assert summarize(rows)["pairs"] == 0


def test_leaky_asks_refuse_the_game_and_its_pair(monkeypatch) -> None:
    # §3.5 neutralization: any seat facing a leaky name ask (CHOOSE_NAME enumerates hidden
    # cards) is refused, the pair voids with it, and the summary counts it separately.
    real = SeatRouter._decide

    def leaky_decide(self, driver, ask):
        self.stats[ask.seat]["leaky_asks"] += 1
        return real(self, driver, ask)

    monkeypatch.setattr(SeatRouter, "_decide", leaky_decide)
    rng.seed_all(5, seed_frameworks=False)
    rows = run_match(uniform, passive, DEALS[:1], name_a="uniform", name_b="pass")
    games = [r for r in rows if r["kind"] == "game"]
    assert {r["outcome"] for r in games} == {"refused-leaky"}
    assert all(r["pair_void"] and r["score_a"] is None for r in games)
    assert all("leaky" in r["reason"] for r in games)
    assert any(
        sum(st.get("leaky_asks", 0) for st in r["seat_stats"]) > 0 for r in games
    )
    summary = summarize(rows)
    assert summary["refused_leaky"] == 2
    assert summary["pairs"] == 0


class _ForfeitAgent:
    name = "forfeit"

    def decide(self, ask, obs) -> int:
        raise AgentForfeitError(
            "forfeit-no-refuse: strikes exhausted without a do-nothing option"
        )


def test_forfeit_without_refuse_is_its_own_void_class() -> None:
    rows = run_match(
        lambda d, g, s: _ForfeitAgent(),
        passive,
        DEALS[:1],
        name_a="forfeit",
        name_b="pass",
    )
    games = [r for r in rows if r["kind"] == "game"]
    assert {r["outcome"] for r in games} == {"void-forfeit"}
    assert all(r["reason"].startswith("forfeit-no-refuse") for r in games)
    assert all(r["pair_void"] and r["score_a"] is None for r in games)
    assert summarize(rows)["pairs"] == 0


def test_the_manifest_records_llm_identity_and_refuses_to_start_without_one() -> None:
    ident = {
        "model": "qwen-test",
        "base_url": "http://localhost:8000/v1",
        "timeout_s": 600.0,
        "temperature": 0.0,
        "max_tokens": 512,
        "strikes": 3,
        "primer": False,
        "masked": True,
        "usage_missing": 0,
    }
    rows = run_match(
        passive,
        passive,
        DEALS[:1],
        name_a="llm",
        name_b="pass",
        identities={"a": dict(ident)},
    )
    man = rows[0]
    assert (
        man["identities"]["a"] == ident
    )  # settled usage_missing == 0 (pass seats report none)
    assert man["identities"]["b"] is None
    with pytest.raises(ValueError, match="no model identity"):
        run_match(
            passive,
            passive,
            DEALS[:1],
            name_a="llm",
            name_b="pass",
            identities={"a": dict(ident, model=None)},
        )


def test_the_manifest_settles_the_seats_usage_missing_after_play() -> None:
    man = {
        "identities": {
            "a": {"model": "m", "usage_missing": 0},
            "b": {"model": "m2", "usage_missing": 0},
        }
    }
    rows = [
        man,
        {
            "kind": "game",
            "a_seat": 0,
            "agent_stats": [{"usage_missing": 2}, {"usage_missing": 1}],
        },
        {"kind": "game", "a_seat": 1, "agent_stats": [{}, {"usage_missing": 4}]},
    ]
    _settle_manifest(man, rows)
    # a: seat 0 in game 1 (2), seat 1 in game 2 (4); b: seat 1 in game 1 (1), seat 0 in game 2 (0)
    assert man["identities"]["a"]["usage_missing"] == 6
    assert man["identities"]["b"]["usage_missing"] == 1
