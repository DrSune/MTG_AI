"""Duplicate-format duels: deterministic, paired on the same deal, honest about voids."""

from __future__ import annotations

from MTG_bot.bench.agents import PassAgent, UniformRandomAgent
from MTG_bot.bench.duel import DealSpec, run_match, summarize
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
    summary = summarize(run_match(uniform, passive, deals, name_a="uniform", name_b="pass"))
    assert summary["pair_score"][0] > 0.5
    assert summary["outcomes"].get("win", 0) > summary["outcomes"].get("loss", 0)


class _BrokenAgent:
    name = "broken"

    def decide(self, ask, obs) -> int:
        return len(ask.options)  # out of range


def test_a_protocol_breach_voids_the_pair_and_is_never_scored() -> None:
    rows = run_match(lambda d, g, s: _BrokenAgent(), passive, DEALS[:1], name_a="broken", name_b="pass")
    games = [r for r in rows if r["kind"] == "game"]
    assert {r["outcome"] for r in games} == {"void-agent"}
    assert all(r["pair_void"] and r["score_a"] is None for r in games)
    assert summarize(rows)["pairs"] == 0
