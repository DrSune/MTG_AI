"""The core state-visible executor (rounds 12a–12d, plan /06 §12a–§12d).

``Executor(world)`` runs compiled ability IR against the Phase-0
:class:`~MTG_bot.core.state.GameWorld`: :meth:`Executor.execute` for one
Atom, :meth:`Executor.apply_effect` for an Effect tree (Seq /
OptionalEffect / Conditional — the decision-bearing nodes; Choose consumes
its decision at runtime from 12d (index into ``query.choose_options``'
ORDER contract — see that docstring); Repeat/EachPlayer remain
not-implemented and RAISE at dispatch; DelayedTrigger SCHEDULES into the
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
    12c adds the decision half: :mod:`executor.legality` (activation
    legality, the CR-checked cost fold, ``pay_costs`` through the
    journalled verbs, the folded ``activate`` move) and
    :mod:`executor.query` (the Slate-shaped query surface —
    ``legal_activations``/``legal_targets``/``choose_options``/
    ``optional_offer``, the C15/C17 enumerations; DESIGN_ACTION_SPACE
    §1.3/§1.4/§5.5/§8.3).
    12d adds the duration + continuous half: :mod:`executor.durations`
    (the full Duration vocab on the ledger — WHILE condition cycles,
    UNTIL_NEXT_STEP ticks, UNTIL_LEAVES zone interception, UNTIL_NEXT_
    TURN begin-turn expiry, all tombstoned for the audit dump),
    :mod:`executor.layers` (StaticAbility/KeywordAbility continuous
    layers: anthems recompute over the set, keyword_of / granted_abilities
    oracles, GRANT_ABILITY/LOSE_ABILITY verbs, PT payloads materialized
    into the single ledger PT stack) and :mod:`executor.replacements`
    (ReplacementAbility interceptor — Nine Lives' damage-to-you consumed
    before the world mutation, action journalled; PREVENT_EFFECT veto
    records with the UNTAP-step consumer live, combat-side exposed).
    The turn skeleton gains its UNTAP step: ``begin_turn`` untaps the
    active player's permanents except those a live prevention vetoes
    (Frost Breath freeze — survives exactly one untap tick), journalling
    every untap as a TapStateEvent, then expires the step-scoped durations.

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
from collections.abc import Sequence
from typing import Dict, List, Optional, Tuple

from MTG_bot.core.ability_tree import (
    Atom,
    Choose,
    Conditional,
    DelayedTrigger,
    Effect,
    OptionalEffect,
    Phase,
    Seq,
    Step,
)
from MTG_bot.core.compiler.compiler import PoolCompile
from MTG_bot.core.executor.binding import MAX_TRIGGER_FIRES, TriggerBinder
from MTG_bot.core.executor.durations import DurationLedger, PtChange
from MTG_bot.core.executor.events import (
    KIND_TAP_STATE,
    KIND_ZONE_CHANGE,
    EventJournal,
    GameEvent,
)
from MTG_bot.core.executor.layers import GrantedAbility, LayerRecord, LayerRegistry
from MTG_bot.core.executor.legality import (
    PaymentPlan,
    ability_playable,
    activate,
    build_payment_plan,
    pay_costs,
)
from MTG_bot.core.executor.quantity import Binding, ExecCtx, eval_filter
from MTG_bot.core.executor.query import (
    ActivationOption,
    OptionChoice,
    TargetSlot,
    choose_options,
    legal_activations,
    legal_targets,
    optional_offer,
    rest_of,
    validate_target_selection,
)
from MTG_bot.core.executor.replacements import (
    PreventionRecord,
    ReplacementRecord,
    ReplacementRegistry,
)
from MTG_bot.core.executor.selectors import resolve_selector
from MTG_bot.core.executor.verbs import HANDLERS, run_atom, token_oracle_id
from MTG_bot.core.identity import Handle
from MTG_bot.core.state import ZONE_BATTLEFIELD, GameWorld

# The honest v1 capability set, derived from the dispatch table so the two
# can never drift apart.
SUPPORTED_VERBS_V1 = frozenset(HANDLERS)

# The 12e capability set: exactly the verbs ``run_atom`` dispatches to a real
# handler today (round-12 cross-check against all 48 corpus verbs).  This is
# the same set as V1 — 12b/12d additions (GRANT_ABILITY, LOSE_ABILITY,
# PREVENT_EFFECT) already entered ``HANDLERS``, and no further verb gained a
# handler — so it is derived, not retyped.  The 25 non-dispatched verbs
# (CAST, COUNTER_SPELL, PHASE_OUT/PHASE_IN, FIGHT, COPY, MANDATE_ATTACK,
# MANDATE_BLOCK, DRAW, PAY, SEARCH, ATTACH, GAIN_CONTROL, GET_EMBLEM, ...)
# stay outside: event-node-only or out-of-contract internals (ruling 6),
# flagged by ``compile_pool(supported_verbs=...)``, never faked.
SUPPORTED_VERBS_V2 = frozenset(HANDLERS)

Event = tuple[object, ...]

__all__ = [
    "MAX_TRIGGER_FIRES",
    "SUPPORTED_VERBS_V1",
    "SUPPORTED_VERBS_V2",
    "ActivationOption",
    "Binding",
    "DurationLedger",
    "Event",
    "EventJournal",
    "ExecCtx",
    "Executor",
    "GameEvent",
    "GrantedAbility",
    "LayerRecord",
    "LayerRegistry",
    "OptionChoice",
    "PaymentPlan",
    "PreventionRecord",
    "PtChange",
    "ReplacementRecord",
    "ReplacementRegistry",
    "TargetSlot",
    "TriggerBinder",
    "ability_playable",
    "activate",
    "build_payment_plan",
    "choose_options",
    "legal_activations",
    "legal_targets",
    "optional_offer",
    "pay_costs",
    "rest_of",
    "validate_target_selection",
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
        self.events: list[Event] = []
        self.token_counts: dict[str, int] = {}
        self.journal = EventJournal(world, self.ledger)
        # 12d registries (built BEFORE the binder: the binder's lifecycle
        # hooks reach them during attach).
        self.layers = LayerRegistry(self)
        self.replacements = ReplacementRegistry(self)
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
        bindings: dict[str, Binding] | None,
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
            # 12d: the registries ride on every effect context (layer
            # verbs, the damage-replacement interceptor).
            layers=self.layers,
            replacements=self.replacements,
            executor=self,
        )

    # ------------------------------------------------------------ execution

    def execute(
        self,
        atom: Atom,
        *,
        source: Handle,
        controller: Handle,
        bindings: dict[str, Binding] | None = None,
        decisions: Sequence[str] = (),
        trigger_decisions: Sequence[str] = (),
    ) -> tuple[Event, ...]:
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
        bindings: dict[str, Binding] | None = None,
        decisions: Sequence[str] = (),
        trigger_decisions: Sequence[str] = (),
    ) -> tuple[Event, ...]:
        """Run an Effect tree; one decision channel spans the whole tree so
        nested choices consume ``decisions`` in tree order (C15). Seq,
        OptionalEffect (``'fire'``/``'skip'``), Conditional (pred judged
        against the *source* handle), Choose (12d: ONE decision token =
        the index of the chosen option-set in ``query.choose_options``
        order) and DelayedTrigger (scheduled, C22) are wired;
        Repeat/EachPlayer raise as unimplemented nodes (12e)."""
        if not isinstance(
            effect, (Atom, Seq, OptionalEffect, Conditional, DelayedTrigger, Choose)
        ):
            raise NotImplementedError(
                f"executor: effect {type(effect).__name__} not implemented (12e)"
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
            new_events = self.journal.record_atom(
                before, ctx.source, effect.verb.name, self.events[start:]
            )
            # 12d hook 1: the UNTIL_LEAVES zone interceptor. Every zone
            # change the journal just saw gets its anchor checked — a
            # permanent leaving the battlefield terminal-expires the
            # durations anchored on it (return does not restore, r5).
            self._on_zone_changes(new_events)
            # 12d hook 2: damage replacements consumed during the atom run
            # (C24: the damage never applied) queue their ACTION here, so
            # it journalled as ITS OWN atom boundary — one diff per
            # mutation, no double-emitted events.
            while ctx.pending_replacements:
                repl = ctx.pending_replacements.pop(0)
                inner = self._ctx(
                    source=repl.source,
                    controller=repl.controller,
                    bindings=None,
                    decisions=(),
                )
                self._run_effect(repl.action, inner)
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
        elif isinstance(effect, Choose):
            # 12d runtime consumption — ORDER CONTRACT (query.OptionChoice
            # docstring): the decision token is str(i), the i-th OPTION-SET
            # of query.choose_options (size-ascending, index-lex). One
            # decision picks the whole set (a k-choose is one compound
            # choice, C15: the Slate's OPTION:PTR* slot is one token).
            opts = choose_options(
                self,
                effect,
                source=ctx.source,
                controller=ctx.controller,
                bindings=ctx.bindings,
            )
            vocab = tuple(str(i) for i in range(len(opts)))
            pick = ctx.take_decision(vocab, "Choose")
            for idx in opts[int(pick)].option_idxs:
                self._run_effect(effect.options[idx], ctx)
        elif isinstance(effect, DelayedTrigger):
            # C22: schedule into the journal matcher (12b), expire at Eot.
            self.binder.schedule_delayed(effect, ctx.source, ctx.controller)
        else:  # pragma: no cover - apply_effect pre-checks the node type
            raise NotImplementedError(
                f"executor: effect {type(effect).__name__} not implemented (12e)"
            )

    def _on_zone_changes(self, events: list[GameEvent]) -> None:
        """UNTIL_LEAVES expiry: a tracked anchor leaving the battlefield
        terminal-expires every duration anchored on it (ledger entries,
        layer records, prevention records). Deterministic: the journal's
        emit order."""
        for event in events:
            if event.kind != KIND_ZONE_CHANGE or event.subject is None:
                continue
            from_state = event.zone_move[0]
            if from_state != ZONE_BATTLEFIELD:
                continue
            anchor = event.subject
            self.ledger.expire_leaves(anchor)
            self.layers.expire_leaves(anchor)
            self.replacements.expire_leaves(anchor)

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
        public op. With nothing attached this is a no-op (12a behaviour).
        12d: the settle tail is also the recompute point — WHILE-condition
        truth is re-evaluated on the ledger, and the layer registry
        re-reads the set (new/lost members, condition toggles) and rebuilds
        the keyword / granted-ability oracles. All of it is pure function
        of the journal's final state, so replays are byte-identical."""
        self.binder.on_events()
        fired = self.binder.fire_all(trigger_decisions)
        self.ledger.settle_while(self._while_eval)
        self.layers.recompute()
        return fired

    def _while_eval(self, change: object, meta: object) -> bool:
        """The ledger WHILE evaluator: the condition (a state predicate,
        StaticAbility convention) judged against the recording anchor in
        the recording controller's coordinates. An anchor that has left
        the world's card set can only be FALSE."""
        from MTG_bot.core.executor.durations import DurationMeta

        assert isinstance(meta, DurationMeta)
        if meta.anchor is None or meta.anchor not in self.world.cards:
            return False
        ctx = self._ctx(
            source=meta.anchor,
            controller=meta.controller if meta.controller is not None else meta.anchor,
            bindings=None,
            decisions=(),
        )
        assert meta.condition is not None
        return eval_filter(meta.condition, meta.anchor, ctx)

    # ------------------------------------------------- 12b/12d: turn skeleton
    #
    # The MINIMAL executor-owned turn: active rotation + world.turn clock +
    # the UNTAP STEP (12d) + phase markers. No combat/main phases (later
    # phases) — the markers the frozen grammar actually has triggers for:
    # UPKEEP + FIRST_MAIN at the beginning of a turn, END_TURN at the end
    # of one. The untap step is a RULE step, not an Atom: it mutates the
    # world directly and journalls one TapStateEvent per untap, so
    # "whenever a creature untaps" triggers and the fingerprint see it.

    def begin_turn(self, player: Handle, trigger_decisions: Sequence[str] = ()) -> int:
        """Begin ``player``'s turn: active rotation, turn clock, the UNTAP
        step (12d), UPKEEP and FIRST_MAIN markers, per-turn event trackers
        reset; drains triggers. Returns the firing count."""
        if player not in self.world.players:
            raise ValueError(f"begin_turn: {player} is not a player of this world")
        if self._turn_started:
            self.world.turn += 1
        self._turn_started = True
        self.world.active_player = player
        self.journal.begin_turn(player)
        self._untap_step(player)
        # UNTIL_NEXT_TURN expiry: the recorded owner's turn is beginning —
        # the precise next-turn-start end the 12a ledger deferred (the
        # binder's DELAYED windows keep their documented Eot stand-in).
        self.ledger.expire_until_next_turn(player)
        self.layers.expire_until_next_turn(player)
        self.replacements.expire_until_next_turn(player)
        self.journal.record_turn_phase(Phase.UPKEEP.name)
        self.journal.record_turn_phase(Phase.FIRST_MAIN.name)
        return self._settle(trigger_decisions)

    def _untap_step(self, player: Handle) -> int:
        """The 12d untap step. Every tapped permanent the ACTIVE player
        controls untaps — except one a live PREVENT/UNTIL_NEXT_STEP record
        vetoes (Frost Breath's freeze; no defender-style exclusions exist
        pre-combat, and there are none in the frozen data for this step).
        APNAP note: untap is a simultaneous rule action, not a player
        choice — the Handle-sorted loop is the deterministic stand-in for
        the simultaneous replacement (documented, no player interaction
        is involved, so no APNAP ordering applies).
        AFTER the tick: UNTIL_NEXT_STEP(UNTAP) records are consumed by the
        step they just survived and terminal-expire — the freeze therefore
        survives EXACTLY one untap tick (pinned). Returns the untap count."""
        world = self.world
        untapped = 0
        for card in sorted(world.cards):
            state = world.cards[card]
            if not state.tapped:
                continue
            if world.zone_of(card).kind != ZONE_BATTLEFIELD:
                continue
            if world.controller_of(card) != player:
                continue
            if self.replacements.prevents_untap(card):
                continue
            state.tapped = False
            self.journal.emit(KIND_TAP_STATE, card, None, "UNTAP_STEP", (False,))
            untapped += 1
        controller_of = world.controller_of
        self.replacements.expire_at_step(Step.UNTAP, player, controller_of)
        self.layers.expire_at_step(Step.UNTAP, player, controller_of)
        self.ledger.expire_at_step(Step.UNTAP, player, controller_of)
        return untapped

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
        ledger entries, Eot-tagged LAYER records (12d: until-end-of-turn
        grants die here) and Eot-tagged PREVENTION records, and the
        turn-window delayed triggers (C22). Returns the firing count."""
        self.journal.record_turn_phase(Phase.END_TURN.name)
        fired = self._settle(trigger_decisions)
        self.ledger.sweep_at_eot()
        self.layers.sweep_at_eot()
        self.replacements.sweep_at_eot()
        self.binder.expire_delayed()
        # Rebuild the oracles after the sweep — a granted keyword that
        # expired at end of turn must not survive into next turn's
        # keyword_of/legal_activations.
        self.layers.recompute()
        return fired

    # ------------------------------------------------------------ replay id

    def state_fingerprint(self) -> str:
        """World fingerprint + ledger dump + event log + the 12b journal
        and binder dumps + the 12d layer and replacement registries
        (ruling 1): equal iff every replayed atom and every fired trigger
        produced the same state transitions."""
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
        h.update(repr(self.layers.dump()).encode())
        h.update(repr(self.replacements.dump()).encode())
        return h.hexdigest()

    # Alias the module-level helpers that tests and callers reach through
    # the package face.
    resolve_selector = staticmethod(resolve_selector)
    token_oracle_id = staticmethod(token_oracle_id)
