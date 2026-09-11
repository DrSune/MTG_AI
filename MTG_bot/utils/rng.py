"""Seeded, stream-separated randomness.

This exists for pre-flight check P11 in docs/TRAINING_REVIEW_PROTOCOL.md, which requires
"All RNG seeded, streams separated (shuffle / engine / policy / exploration)" with "four
independent streams". P11 to P13 gate the entire protocol: until they pass, no comparison
in that document can conclude anything.

WHY SEPARATE STREAMS AND NOT JUST ONE SEED
------------------------------------------
Before this module, every random draw in MTG_bot came from the one global ``random``
module: library shuffles and starting player (game_initializer), deck construction
(deck_generator), engine choices (engine), and policy sampling and exploration (student).
A single global seed would not have been enough, and the reason is the whole point of P11.

Draws from one stream are consumed in sequence. If exploration and shuffling share a
stream, then changing the exploration rate changes *how many* numbers exploration consumes,
which shifts every subsequent shuffle. Two runs that differ only in a hyperparameter would
then face different decks, and the difference you measured would be the decks, not the
change. That makes an A/B comparison meaningless in exactly the way it looks trustworthy.

Separated streams mean a change to one concern cannot perturb another.

WHY STREAMS ARE DERIVED FROM A HASH OF THEIR NAME
-------------------------------------------------
Each stream's seed is ``sha256(master_seed : name)``, not a sequential split of a parent
generator. That is deliberate. With sequential splitting, adding a sixth stream later
renumbers the ones after it and silently invalidates every earlier run's reproducibility.
Name-derived seeds are stable: adding a stream changes nothing about the others, forever.

``hashlib`` is used rather than the builtin ``hash()`` because ``hash()`` on a str is
salted by PYTHONHASHSEED and differs between processes, which would break P12's
requirement that the same seed replays identically "in two processes".

WHAT THIS DOES NOT FIX
----------------------
P12, byte-identical replay, needs more than this. Entity ids are still ``uuid.uuid4()``
(game_graph.py:50) and zone-change triggers are computed by iterating ``set`` differences
of those UUIDs, so trigger ordering is still nondeterministic under a fixed seed. Integer
entity handles and an ordered trigger queue are the remaining work, and they belong to the
D1 engine rebuild because they change the state model. This module is the half of the
determinism problem that does not have to wait for that.
"""

from __future__ import annotations

import hashlib
import os
import random
from typing import Dict, Optional

from MTG_bot.utils.logger import setup_logger

logger = setup_logger("RNG")

# The four P11 requires, plus one. Deck construction is genuinely a different concern from
# in-game shuffling: it runs once per matchup, off the per-decision path, and its draw count
# changes whenever the archetype recipe changes. Folding it into "shuffle" would reintroduce
# the exact coupling this module exists to remove. Declared here rather than added silently.
STREAM_NAMES = (
    "shuffle",       # library shuffles, starting player
    "engine",        # engine-internal choices: discard to hand size, choice menus
    "policy",        # policy sampling and replay-buffer sampling
    "exploration",   # epsilon rolls, and the behaviour rails that bias action choice
    "deckbuild",     # deck construction and draft packs
    "teacher",       # curriculum and matchup curation
    "scenario",      # procedural puzzle generation
)

_master_seed: Optional[int] = None
_streams: Dict[str, random.Random] = {}


def _derive(master: int, name: str) -> int:
    digest = hashlib.sha256(f"{master}:{name}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def seed_all(master_seed: int, *, seed_frameworks: bool = True) -> int:
    """Seed every stream from one master seed. Returns the master seed.

    Record the return value in the run manifest: P1 and P11 both want it there, and a run
    whose seed was not written down is not reproducible even though it was deterministic.
    """
    global _master_seed
    _master_seed = int(master_seed)
    _streams.clear()
    for name in STREAM_NAMES:
        _streams[name] = random.Random(_derive(_master_seed, name))

    if seed_frameworks:
        # numpy and torch keep their own global state. Seed them off named streams too, so
        # they inherit the same stability property.
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


def get_master_seed() -> Optional[int]:
    """The master seed in force, or None if nothing has been seeded yet."""
    return _master_seed


def stream(name: str) -> random.Random:
    """Return the named generator. Use this instead of the ``random`` module.

    If nothing has been seeded yet, a master seed is drawn from OS entropy and logged at
    WARNING. That is deliberate: crashing would break every test and ad-hoc script, but an
    unseeded run must never be silent, because its numbers cannot be reproduced and the
    protocol forbids reporting them.
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
