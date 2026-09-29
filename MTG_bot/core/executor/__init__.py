"""The core state-visible executor (round 12a, plan /06 §12a).

``Executor(world)`` runs compiled ability IR against the Phase-0
:class:`~MTG_bot.core.state.GameWorld`: :meth:`Executor.execute` for one
Atom, :meth:`Executor.apply_effect` for an Effect tree (Seq /
OptionalEffect / Conditional — the decision-bearing nodes; Repeat/Choose/
EachPlayer are 12c and RAISE at dispatch). Design mandates:

  * **flag, don't degrade** — every unsupported verb/effect/quantity/pred
    raises ``NotImplementedError`` at dispatch, naming the node; the
    executor never guesses a silent no-op (LOOK_AT/REVEAL are recorded,
    legitimate no-ops).
  * **explicit decisions** — enumerable choices (may-fire, scry
    top/bottom, any-colour mana) arrive as the ``decisions`` sequence and
    are consumed strictly in order (C15).
  * **executor-owned randomness** — the only randomness is a
    :class:`random.Random` seeded from ``sha256(master_seed:op_seq:tag)``;
    two executors fed the same ops replay byte-identically (P12). The
    replay fingerprint is ``world.fingerprint()`` + the
    :class:`DurationLedger` dump + the event log (ruling 1: the ledger IS
    replayed state, since state.py stays frozen).
  * ``SUPPORTED_VERBS_V1`` is the honest capability set — it is *not*
    wired into ``compile_pool`` gating (that is 12e's job).

Verb.DRAW is deliberately outside v1 (the mission's scope list): the atom
stays unsupported and raises, with the DRAW idiom of library->hand MOVE_ZONE
handled by the verb that cards actually compile to.
"""

from __future__ import annotations

import hashlib
import random
from typing import Dict, List, Optional, Sequence, Tuple

from MTG_bot.core.ability_tree import Atom, Conditional, Effect, OptionalEffect, Seq
from MTG_bot.core.executor.durations_min import DurationLedger, PtChange
from MTG_bot.core.executor.quantity import Binding, ExecCtx, eval_filter
from MTG_bot.core.executor.selectors import resolve_selector
from MTG_bot.core.executor.verbs import HANDLERS, run_atom, token_oracle_id
from MTG_bot.core.identity import Handle
from MTG_bot.core.state import GameWorld

# The honest v1 capability set, derived from the dispatch table so the two
# can never drift apart.
SUPPORTED_VERBS_V1 = frozenset(HANDLERS)

Event = Tuple[object, ...]

__all__ = [
    "SUPPORTED_VERBS_V1",
    "DurationLedger",
    "Event",
    "ExecCtx",
    "Executor",
    "PtChange",
]


class Executor:
    """Runs IR against one :class:`GameWorld` (mutable across calls, like
    the world itself). One Executor per world/replay; a replay is a fresh
    Executor fed the same atom sequence."""

    def __init__(self, world: GameWorld) -> None:
        if not isinstance(world, GameWorld):
            raise ValueError(
                f"Executor: world must be a GameWorld, got {type(world).__name__}"
            )
        self.world = world
        self.ledger = DurationLedger()
        self.events: List[Event] = []
        self.token_counts: Dict[str, int] = {}
        self._op_seq = 0

    # ------------------------------------------------------------------ rng

    def _rng(self, tag: str) -> random.Random:
        """The executor-owned seeded factory: no wall-clock, no globals —
        the same (master_seed, op_seq, tag) always yields the same stream."""
        seed = hashlib.sha256(
            f"{self.world.master_seed}:{self._op_seq}:{tag}".encode()
        ).hexdigest()
        return random.Random(int(seed, 16))

    # -------------------------------------------------------------- context

    def _ctx(
        self,
        *,
        source: Handle,
        controller: Handle,
        bindings: Optional[Dict[str, Binding]],
        decisions: Sequence[str],
    ) -> ExecCtx:
        if not isinstance(source, Handle) or not isinstance(controller, Handle):
            raise ValueError("Executor: source and controller must be Handles")
        return ExecCtx(
            world=self.world,
            ledger=self.ledger,
            controller=controller,
            source=source,
            bindings=dict(bindings or {}),
            decisions=tuple(decisions),
            events=self.events,
            rng=self._rng,
            token_counts=self.token_counts,
        )

    # ------------------------------------------------------------ execution

    def execute(
        self,
        atom: Atom,
        *,
        source: Handle,
        controller: Handle,
        bindings: Optional[Dict[str, Binding]] = None,
        decisions: Sequence[str] = (),
    ) -> Tuple[Event, ...]:
        """Run one Atom; returns the events this call appended. Unsupported
        verbs raise ``NotImplementedError`` at dispatch."""
        if not isinstance(atom, Atom):
            raise ValueError(
                f"Executor: execute needs an Atom, got {type(atom).__name__}"
            )
        self._op_seq += 1
        ctx = self._ctx(
            source=source, controller=controller, bindings=bindings, decisions=decisions
        )
        start = len(self.events)
        run_atom(atom, ctx)
        return tuple(self.events[start:])

    def apply_effect(
        self,
        effect: Effect,
        *,
        source: Handle,
        controller: Handle,
        bindings: Optional[Dict[str, Binding]] = None,
        decisions: Sequence[str] = (),
    ) -> Tuple[Event, ...]:
        """Run an Effect tree; one decision channel spans the whole tree so
        nested choices consume ``decisions`` in tree order (C15). Seq,
        OptionalEffect (``'fire'``/``'skip'``) and Conditional (pred judged
        against the *source* handle — the minimal 12a subject) are wired;
        Repeat/Choose/EachPlayer raise as 12c nodes."""
        if not isinstance(effect, (Atom, Seq, OptionalEffect, Conditional)):
            raise NotImplementedError(
                f"executor: effect {type(effect).__name__} not implemented (12c)"
            )
        self._op_seq += 1
        ctx = self._ctx(
            source=source, controller=controller, bindings=bindings, decisions=decisions
        )
        start = len(self.events)
        self._run_effect(effect, ctx)
        return tuple(self.events[start:])

    def _run_effect(self, effect: Effect, ctx: ExecCtx) -> None:
        if isinstance(effect, Atom):
            run_atom(effect, ctx)
        elif isinstance(effect, Seq):
            for step in effect.steps:
                self._run_effect(step, ctx)
        elif isinstance(effect, OptionalEffect):
            if ctx.take_decision(("fire", "skip"), "OptionalEffect") == "fire":
                self._run_effect(effect.inner, ctx)
        elif isinstance(effect, Conditional):
            if eval_filter(effect.pred, ctx.source, ctx):
                self._run_effect(effect.then_effect, ctx)
            elif effect.else_effect is not None:
                self._run_effect(effect.else_effect, ctx)
        else:  # pragma: no cover - apply_effect pre-checks the node type
            raise NotImplementedError(
                f"executor: effect {type(effect).__name__} not implemented (12c)"
            )

    # ------------------------------------------------------------ replay id

    def state_fingerprint(self) -> str:
        """World fingerprint + ledger dump + event log (ruling 1): equal
        iff every replayed atom produced the same state transitions."""
        h = hashlib.sha256()
        h.update(self.world.fingerprint().encode())
        h.update(repr(self.ledger.dump()).encode())
        for event in self.events:
            h.update(repr(event).encode())
            h.update(b"\n")
        return h.hexdigest()

    # Alias the module-level helpers that tests and callers reach through
    # the package face.
    resolve_selector = staticmethod(resolve_selector)
    token_oracle_id = staticmethod(token_oracle_id)
