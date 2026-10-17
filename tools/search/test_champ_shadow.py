"""CHAMP-shadow gates (KNOWLEDGE/2026-10-13/75 option A).

(1) encode-exactness over REAL smoke rows: the emitted chunk budget equals
the encoder-visible stream length under the checkpoint's own vocab, every
episode fits the 1024 budget, every gold index is a legal menu index;
(2) per-game opponent cycling is deterministic, covers the full cycle, and
lands on the emitted episodes.
"""

from __future__ import annotations

import pytest

from MTG_bot.core.executor.games import get_supply
from tools.search.champ_shadow import (
    DEFAULT_CKPT,
    OPPONENTS,
    opponent_for_seed,
    run_champ_game,
    verify_episodes,
)
from tools.training import bc_data_v2

GAME_SEED = 7701  # 66 seat-0 asks -> multi-chunk smoke game (champ_stats run)


@pytest.fixture(scope="module")
def game():
    return run_champ_game(GAME_SEED, supply=get_supply("engine"))


@pytest.fixture(scope="module")
def vocab():
    """The checkpoint's own vocab (cached model — no second load)."""
    from tools.training.ab_duel import BcAsk

    return BcAsk.fresh(DEFAULT_CKPT, "cpu").vocab


def test_encode_exactness_on_smoke_rows(game, vocab):
    """chunk_seat's budget claim re-verified INDEPENDENTLY on the final
    rows with the encoder the next training wave will actually use."""
    eps = game["episodes"]
    assert eps, "smoke game produced no episodes"
    assert game["trunc"]["gold_row_overflow"] == 0
    for ep in eps:
        enc = bc_data_v2.encode_episode_v2(ep, vocab)
        assert len(enc["seq"]) == ep["n_tokens"] <= 1024
        assert len(enc["gold"]) == sum(1 for r in ep["asks"] if r["gold"]) > 0
    verify_episodes(eps, vocab, 1024)  # raises on any violation
    # every seat-0 ask became exactly one gold row, labelled by the champ
    assert sum(len(e["asks"]) for e in eps) == game["counters"]["seat0_asks"]


def test_opponent_cycling(game):
    """seed % 3 over the cycle, deterministic, full coverage, and the
    episode metadata carries the opponent that was actually played."""
    assert [opponent_for_seed(s) for s in range(6)] == [
        "teacher",
        "random",
        "champ",
        "teacher",
        "random",
        "champ",
    ]
    assert {opponent_for_seed(s) for s in range(len(OPPONENTS))} == set(OPPONENTS)
    for ep in game["episodes"]:
        assert ep["opponent"] == opponent_for_seed(game["seed"])
        assert ep["source"] == "champ"
        assert ep["pack"].startswith(f"champshadow-g{game['seed']}s0c")
