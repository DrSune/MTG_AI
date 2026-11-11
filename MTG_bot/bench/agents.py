"""The agent protocol, and the floors every result table must carry.

An agent has a ``name`` and answers an ``Ask`` with an option index, ``decide(ask, obs) -> int``.
Two kinds of seat driver plug into ``SeatRouter``:
- agents (decide per Ask; what LLM seats and the floors are);
- raw engine policies with ``answer(vocab, what)`` and ``take_priority(game, seat)``, such as
  ``RandomPolicy`` or a future adapter around our network. These pass straight through.

The floors (docs/DESIGN_BENCHMARK.md §4; METRICS §17):
- ``PassAgent``, the do-nothing policy: it never casts, never attacks, never blocks, and declines
  every optional effect. Any metric it scores well on must be published paired with one that
  requires acting well.
- ``UniformRandomAgent``: uniform over the offered options at every ask. Unlike the hand-weighted
  ``RandomPolicy`` (``core/executor/games.py``), it is the honest random-legal baseline.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from MTG_bot.bench.view import SeatView, render_view

if TYPE_CHECKING:
    from MTG_bot.bench.protocol import Ask
    from MTG_bot.bench.view import SeatLens
    from MTG_bot.core.executor import Executor


@dataclass
class Observation:
    """The deciding seat's view, built lazily so agents that ignore it pay nothing."""

    lens: SeatLens
    executor: Executor
    _view: SeatView | None = field(default=None, repr=False)
    _text: str | None = field(default=None, repr=False)

    @property
    def view(self) -> SeatView:
        if self._view is None:
            self._view = self.lens.view(self.executor)
        return self._view

    @property
    def text(self) -> str:
        text = self._text
        if text is None:
            text = self._text = render_view(self.view)
        return text


class InfraError(RuntimeError):
    """A driver's backing service failed (a model endpoint, a network). The game is voided, never
    scored: an outage is not the agent's loss."""


class AgentError(RuntimeError):
    """An agent broke the protocol (for example, returned an out-of-range index). The game is voided,
    never scored: an agent bug is not a loss, and it must not be mistaken for an engine crash."""


class AgentForfeitError(AgentError):
    """An agent exhausted its strikes on an ask that offers no do-nothing option. The game is voided
    (``void-forfeit``): the bench never plays a default move on the agent's behalf."""


@runtime_checkable
class RawPolicy(Protocol):
    def answer(self, vocab: tuple[str, ...], what: str) -> str: ...

    def take_priority(self, game: Any, seat: Any) -> bool: ...


def is_raw(driver: object) -> bool:
    return isinstance(driver, RawPolicy)


class PassAgent:
    name = "pass"

    def decide(self, ask: Ask, obs: Observation) -> int:
        return ask.refuse if ask.refuse is not None else 0


class UniformRandomAgent:
    name = "uniform"

    def __init__(self, rng: random.Random) -> None:
        self.rng = rng

    def decide(self, ask: Ask, obs: Observation) -> int:
        return self.rng.randrange(len(ask.options))
