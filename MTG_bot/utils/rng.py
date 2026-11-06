"""Seeded, stream-separated randomness (pre-flight P11, docs/TRAINING_REVIEW_PROTOCOL.md).

Each concern draws from its own named stream. Draws from one stream are consumed in sequence,
so two concerns sharing a stream are coupled: raising the exploration rate consumes more
numbers and shifts every later library shuffle, and an A/B comparison then measures different
decks, not the change.

Each stream's seed is ``sha256(master_seed:name)``, not a sequential split of a parent
generator, so adding a stream never renumbers the others. ``hashlib``, not the builtin
``hash()``, which is salted per process and would break replay across processes (P12).
"""

from __future__ import annotations

import hashlib
import logging
import os
import random
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# One stream per concern. Add a name rather than reuse a stream: sharing couples draw counts.
STREAM_NAMES = (
    "shuffle",       # library shuffles, starting player
    "engine",        # engine-internal choices: discard to hand size, choice menus
    "policy",        # policy sampling and replay-buffer sampling
    "exploration",   # epsilon rolls, and the behaviour rails that bias action choice
    "deckbuild",     # deck construction and draft packs
    "teacher",       # curriculum and matchup curation
    "scenario",      # procedural puzzle generation
    "bench",         # benchmark agents and deals (MTG_bot/bench); per-game via substream()
)

_master_seed: Optional[int] = None
_streams: Dict[str, random.Random] = {}


def _derive(master: int, name: str) -> int:
    digest = hashlib.sha256(f"{master}:{name}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def seed_all(master_seed: int, *, seed_frameworks: bool = True) -> int:
    """Seed every stream from one master seed and return it. Record it in the run manifest
    (P1, P11): a run whose seed was not written down cannot be reproduced."""
    global _master_seed
    _master_seed = int(master_seed)
    _streams.clear()
    for name in STREAM_NAMES:
        _streams[name] = random.Random(_derive(_master_seed, name))

    if seed_frameworks:
        # numpy and torch keep their own global state; seed them from name-derived seeds too.
        try:
            import numpy as np

            np.random.seed(_derive(_master_seed, "numpy") % (2**32))
        except ImportError:
            pass
        try:
            import torch

            torch.manual_seed(_derive(_master_seed, "torch") % (2**63))
        except ImportError:
            pass

    logger.info("RNG seeded, master_seed=%d, streams=%s", _master_seed, list(STREAM_NAMES))
    return _master_seed


def substream(name: str, *key: object) -> random.Random:
    """A fresh generator derived from the master seed, a declared stream name and a key.

    For randomness that must not depend on how many draws other games made from the shared
    stream (the benchmark seeds each (deal, game, seat) agent this way). The same inputs give the
    same generator, and the named stream itself is never consumed.
    """
    stream(name)  # validates the name and auto-seeds exactly as stream() does
    assert _master_seed is not None
    return random.Random(_derive(_master_seed, ":".join([name, *map(str, key)])))


def get_master_seed() -> Optional[int]:
    """The master seed in force, or None if nothing has been seeded yet."""
    return _master_seed


def stream(name: str) -> random.Random:
    """Return the named generator. Use this instead of the ``random`` module.

    If nothing has been seeded yet, a master seed is drawn from OS entropy and logged at
    WARNING: crashing would break every test and ad-hoc script, but an unseeded run must never
    be silent, because its numbers cannot be reproduced.
    """
    if name not in _streams:
        if _master_seed is None:
            auto = int.from_bytes(os.urandom(8), "big")
            logger.warning(
                "RNG used before seed_all(); auto-seeding master_seed=%d. "
                "This run is NOT reproducible unless that seed is recorded. "
                "Call seed_all() explicitly before any training run (pre-flight P11).",
                auto,
            )
            seed_all(auto)
        if name not in _streams:
            raise KeyError(
                f"unknown RNG stream {name!r}; declared streams are {list(STREAM_NAMES)}. "
                f"Add it to STREAM_NAMES rather than reusing another stream, because "
                f"sharing a stream couples the two concerns' draw counts."
            )
    return _streams[name]
