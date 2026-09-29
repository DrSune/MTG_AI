"""The core state-visible executor (rounds 12a + 12b, plan /06 §12a/§12b).

``Executor(world)`` runs compiled ability IR against the Phase-0
:class:`~MTG_bot.core.state.GameWorld`: :meth:`Executor.execute` for one
Atom, :meth:`Executor.apply_effect` for an Effect tree (Seq /
OptionalEffect / Conditional — the decision-bearing nodes; Repeat/Choose/
EachPlayer are 12c and RAISE at dispatch; DelayedTrigger SCHEDULES into the
12b binder, C22). 12b adds the living-ability half:

  * :meth:`Executor.attach_card` / :meth:`Executor.attach_pool` — compiled
    records bind to world Handles (oracle-id bridge, identity checked);
    leaving the battlefield detaches, re-entering re-registers;
  * an :class:`~MTG_bot.core.executor.events.EventJournal` — every Atom
    boundary diffs the world and emits the structured events triggers
    subscribe to (zone moves, C18 dies snapshots, draws, counters, taps,
    damage, life, turn phases);
  * :meth:`Executor.fire_triggers` / the auto-drain at the end of every
    public op — matched triggers resolve through the world's APNAP
    ``order_key``, in Handle-tie-broken order, until the queue empties
    (``MAX_TRIGGER_FIRES`` tripwire: a self-retriggering loop RAISES).

Design mandates:

  * **flag, don't degrade** — every unsupported verb/effect/quantity/pred
    raises ``NotImplementedError`` at dispatch, naming the node; the
    executor never guesses a silent no-op (LOOK_AT/REVEAL are recorded,
    legitimate no-ops).
  * **explicit decisions** — enumerable choices (may-fire, scry top/bottom,
    any-colour mana) arrive as the ``decisions`` sequence and are consumed
    strictly in order (C15). A trigger drain consumes its OWN
    ``trigger_decisions`` across the drain in APNAP fire order.
  * **executor-owned randomness** — the only randomness is a
    :class:`random.Random` seeded from ``sha256(master_seed:op_seq:tag)``;
    two executors fed the same ops replay byte-identically (P12). The
    replay fingerprint is ``world.fingerprint()`` + the
    :class:`DurationLedger` dump + the 12a event log + the 12b journal and
    binder dumps (ruling 1: the ledger IS replayed state, since state.py
    stays frozen).
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

from MTG_bot.core.ability_tree import (
    Atom,
    Conditional,
    DelayedTrigger,
    Effect,
    OptionalEffect,
    Phase,
    Seq,
)
from MTG_bot.core.compiler.compiler import PoolCompile
from MTG_bot.core.executor.binding import MAX_TRIGGER_FIRES, TriggerBinder
from MTG_bot.core.executor.durations_min import DurationLedger, PtChange
from MTG_bot.core.executor.events import EventJournal, GameEvent
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
    "MAX_TRIGGER_FIRES",
    "SUPPORTED_VERBS_V1",
    "DurationLedger",
    "Event",
    "EventJournal",
    "ExecCtx",
    "Executor",
    "GameEvent",
    "PtChange",
    "TriggerBinder",
]


class Executor:
    """Runs IR against one :class:`GameWorld` (mutable across calls, like
    the world itself). One Executor per world/replay; a replay is a fresh
    Executor fed the same atom/attach/turn sequence."""

    def __init__(self, world: GameWorld) -> None:
        if not isinstance(world, GameWorld):
            raise ValueError(
                f"Executor: world must be a GameWorld, got {type(world).__name__}"
            )
        self.world = world
        self.ledger = DurationLedger()
        self.events: List[Event] = []
        self.token_counts: Dict[str, int] = {}
        self.journal = EventJournal(world, self.ledger)
        self.binder = TriggerBinder(self)
        self._op_seq = 0
        self._turn_started = False
        # Public alias of the seeded factory (the binder builds ExecCtxs too).
        self.rng = self._rng

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
        trigger_decisions: Sequence[str] = (),
    ) -> Tuple[Event, ...]:
        """Run one Atom; returns the 12a events this call appended.
        Unsupported verbs raise ``NotImplementedError`` at dispatch. The
        atom's world changes are journalled; any trigger the change arms
        drains afterwards (APNAP), consuming ``trigger_decisions``."""
        if not isinstance(atom, Atom):
            raise ValueError(
                f"Executor: execute needs an Atom, got {type(atom).__name__}"
            )
        self._op_seq += 1
        ctx = self._ctx(
            source=source, controller=controller, bindings=bindings, decisions=decisions
        )
        start = len(self.events)
        self._run_effect(atom, ctx)
        self._settle(trigger_decisions)
        return tuple(self.events[start:])

    def apply_effect(
        self,
        effect: Effect,
        *,
        source: Handle,
        controller: Handle,
        bindings: Optional[Dict[str, Binding]] = None,
        decisions: Sequence[str] = (),
        trigger_decisions: Sequence[str] = (),
    ) -> Tuple[Event, ...]:
        """Run an Effect tree; one decision channel spans the whole tree so
        nested choices consume ``decisions`` in tree order (C15). Seq,
        OptionalEffect (``'fire'``/``'skip'``), Conditional (pred judged
        against the *source* handle) and DelayedTrigger (scheduled, C22)
        are wired; Repeat/Choose/EachPlayer raise as 12c nodes."""
        if not isinstance(
            effect, (Atom, Seq, OptionalEffect, Conditional, DelayedTrigger)
        ):
            raise NotImplementedError(
                f"executor: effect {type(effect).__name__} not implemented (12c)"
            )
        self._op_seq += 1
        ctx = self._ctx(
            source=source, controller=controller, bindings=bindings, decisions=decisions
        )
        start = len(self.events)
        self._run_effect(effect, ctx)
        self._settle(trigger_decisions)
        return tuple(self.events[start:])

    def _run_effect(self, effect: Effect, ctx: ExecCtx) -> None:
        if isinstance(effect, Atom):
            # 12b: the journalled Atom boundary — snapshot, run, diff. This
            # is the ONLY place world mutations happen on the executor path,
            # so the journal sees every trigger-relevant change without a
            # single verbs.py edit.
            before = self.journal.snapshot()
            start = len(self.events)
            run_atom(effect, ctx)
            self.journal.record_atom(
                before, ctx.source, effect.verb.name, self.events[start:]
            )
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
        elif isinstance(effect, DelayedTrigger):
            # C22: schedule into the journal matcher (12b), expire at Eot.
            self.binder.schedule_delayed(effect, ctx.source, ctx.controller)
        else:  # pragma: no cover - apply_effect pre-checks the node type
            raise NotImplementedError(
                f"executor: effect {type(effect).__name__} not implemented (12c)"
            )

    # -------------------------------------------------------- 12b: triggers

    def attach_card(self, handle: Handle, compiled: object) -> int:
        """Bind the compiled record's TriggeredAbility nodes to a world
        card (CardRecord or CompileResult — the oracle-id bridge is
        identity-checked). Returns the number of triggers bound."""
        return self.binder.attach_card(handle, compiled)

    def attach_pool(self, pool: PoolCompile) -> int:
        """Register a PoolCompile by oracle id and attach every registered
        card already on the battlefield."""
        return self.binder.attach_pool(pool)

    def fire_triggers(self, decisions: Sequence[str] = ()) -> int:
        """Drain the pending trigger queue (APNAP, Handle-tie-broken);
        ``decisions`` are consumed in fire order (may-offers). Returns the
        number of firings."""
        self.binder.on_events()
        return self.binder.fire_all(decisions)

    def _settle(self, trigger_decisions: Sequence[str] = ()) -> int:
        """Match the journal's new events and drain — the end of every
        public op. With nothing attached this is a no-op (12a behaviour)."""
        self.binder.on_events()
        return self.binder.fire_all(trigger_decisions)

    # ------------------------------------------------- 12b: turn skeleton
    #
    # The MINIMAL executor-owned turn: active rotation + world.turn clock +
    # phase markers. NO untap step (that is the 12d duration layer), no
    # combat/main phases (later phases) — the markers the frozen grammar
    # actually has triggers for: UPKEEP + FIRST_MAIN at the beginning of a
    # turn, END_TURN at the end of one.

    def begin_turn(self, player: Handle, trigger_decisions: Sequence[str] = ()) -> int:
        """Begin ``player``'s turn: active rotation, turn clock, UPKEEP and
        FIRST_MAIN markers, per-turn event trackers reset; drains triggers.
        Returns the firing count."""
        if player not in self.world.players:
            raise ValueError(f"begin_turn: {player} is not a player of this world")
        if self._turn_started:
            self.world.turn += 1
        self._turn_started = True
        self.world.active_player = player
        self.journal.begin_turn(player)
        self.journal.record_turn_phase(Phase.UPKEEP.name)
        self.journal.record_turn_phase(Phase.FIRST_MAIN.name)
        return self._settle(trigger_decisions)

    def advance_turn(self, trigger_decisions: Sequence[str] = ()) -> int:
        """End the active turn (if one is open) and begin the next seat's
        turn — the skeleton's round-robin. Returns the combined firings."""
        order = self.world.player_order
        if self.world.active_player is None or not self._turn_started:
            nxt = order[0]
        else:
            idx = order.index(self.world.active_player)
            nxt = order[(idx + 1) % len(order)]
            self.end_turn(trigger_decisions)
        return self.begin_turn(nxt, trigger_decisions)

    def end_turn(self, trigger_decisions: Sequence[str] = ()) -> int:
        """END_TURN marker FIRST (end-step triggers see the pre-expiry
        state), trigger drain, THEN the end-of-turn expiry sweep: Eot
        ledger entries and turn-window delayed triggers (C22). Returns the
        firing count."""
        self.journal.record_turn_phase(Phase.END_TURN.name)
        fired = self._settle(trigger_decisions)
        self.ledger.sweep_at_eot()
        self.binder.expire_delayed()
        return fired

    # ------------------------------------------------------------ replay id

    def state_fingerprint(self) -> str:
        """World fingerprint + ledger dump + event log + the 12b journal
        and binder dumps (ruling 1): equal iff every replayed atom and
        every fired trigger produced the same state transitions."""
        h = hashlib.sha256()
        h.update(self.world.fingerprint().encode())
        h.update(repr(self.ledger.dump()).encode())
        for event in self.events:
            h.update(repr(event).encode())
            h.update(b"\n")
        for row in self.journal.dump():
            h.update(repr(row).encode())
            h.update(b"\n")
        h.update(repr(self.binder.dump()).encode())
        return h.hexdigest()

    # Alias the module-level helpers that tests and callers reach through
    # the package face.
    resolve_selector = staticmethod(resolve_selector)
    token_oracle_id = staticmethod(token_oracle_id)
