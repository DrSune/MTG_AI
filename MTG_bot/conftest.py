"""Make every test deterministic.

Three tests in this suite were coin flips. Measured over six consecutive runs of just
those three, the pass count was 1, 1, 1, 2, 0 and 1 out of 3. They had always been flaky:
initialize_game_state picks the starting player at random and shuffles the library, so any
test that assumes a seat order or a particular opening hand wins or loses on the draw. The
recorded "17 passed" baseline was therefore partly luck, which makes pre-flight check P7
("rules conformance suite green") unmeasurable in principle, not just failing.

Seeding every test fixes the measurement rather than the tests. A test that now fails every
time was already broken; it was only hiding behind a favourable roll. That is the protocol's
own ordering: P11 to P13 gate everything, because until a result is reproducible the correct
response to any observed difference is "we do not know".

Deliberately a fixed constant and not a per-test hash. If a test only passes under a lucky
seed, the honest outcome is that it fails here consistently and gets fixed, not that it gets
a seed chosen to make it pass.
"""

import pytest

from MTG_bot.utils.rng import seed_all

TEST_MASTER_SEED = 20260911


@pytest.fixture(autouse=True)
def _deterministic_rng():
    seed_all(TEST_MASTER_SEED, seed_frameworks=True)
    yield
