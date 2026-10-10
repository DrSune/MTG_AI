"""Search substrate: sound state forks + rollouts over the REAL game loop.

KNOWLEDGE/2026-10-10/67 owner mandate: an AlphaZero-style tree needs
(1) a fast fork of a live position, (2) rollouts that drive the SAME
``games._play`` loop with pluggable seat policies, (3) single-step ask
expansion. Everything here composes those two primitives.
"""

from tools.search.fork import fork
from tools.search.rollout import (
    GREEDY_TEACHER,
    RANDOM,
    Expansion,
    Expansions,
    Position,
    RolloutResult,
    expand,
    play_position,
    rollout,
)

__all__ = [
    "GREEDY_TEACHER",
    "RANDOM",
    "Expansion",
    "Expansions",
    "Position",
    "RolloutResult",
    "expand",
    "fork",
    "play_position",
    "rollout",
]
