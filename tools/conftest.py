"""Every test under tools/ starts from the same seeds, as the engine's tests do (MTG_bot/conftest.py
gives the reasons): one fixed master seed for the named streams, numpy and torch. A test that then
fails every time was already broken, and was only passing on a favourable roll."""

import pytest

from MTG_bot.utils.rng import seed_all

TEST_MASTER_SEED = 20260911


@pytest.fixture(autouse=True)
def _deterministic_rng():
    seed_all(TEST_MASTER_SEED, seed_frameworks=True)
    yield
