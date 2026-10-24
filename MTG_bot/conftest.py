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

from pathlib import Path

import pytest

from MTG_bot.utils.rng import seed_all

TEST_MASTER_SEED = 20260911


@pytest.fixture(autouse=True)
def _deterministic_rng():
    seed_all(TEST_MASTER_SEED, seed_frameworks=True)
    yield


KNOWN_FAILURES = Path(__file__).with_name("known_failures.txt")


def _known_failures() -> dict[str, str]:
    """``node id -> reason`` from known_failures.txt (format documented in the file)."""
    known: dict[str, str] = {}
    for line in KNOWN_FAILURES.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        node_id, _, reason = line.partition("  # ")
        known[node_id.strip()] = reason.strip() or "recorded known failure"
    return known


def pytest_collection_modifyitems(config, items):
    """Run every registered known failure as a STRICT expected failure.

    The test still executes; an unexpected pass fails the run, which is the cue to delete its line.
    Added 2026-10-24 so that red in the default run means a regression, not the 21 legacy failures
    everyone had learned to ignore (docs/REVIEW_2026-10-24.md A-7).
    """
    known = _known_failures()
    for item in items:
        reason = known.get(item.nodeid)
        if reason is not None:
            item.add_marker(pytest.mark.xfail(strict=True, reason=f"known failure: {reason}"))
