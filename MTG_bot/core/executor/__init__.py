"""The core state-visible executor (rounds 12a–12d, plan /06 §12a–§12d).

``Executor(world)`` runs compiled ability IR against the Phase-0
:class:`~MTG_bot.core.state.GameWorld`: :meth:`Executor.execute` for one
Atom, :meth:`Executor.apply_effect` for an Effect tree (Seq /
OptionalEffect / Conditional — the decision-bearing nodes; Choose consumes
its decision at runtime from 12d (index into ``query.choose_options``'
ORDER contract — see that docstring); EachPlayer runs per-player
sub-executions with the CONTROLLER rotated (14f; the templates compile the
inner effect YOU-relative); Repeat remains not-implemented and RAISES at
dispatch; DelayedTrigger SCHEDULES into the
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
    13a gives the same skeleton a **phase clock** (``Executor.phase`` /
    ``turn_open``, the honest sorcery-window gate), an **extra-turn queue**
    (``advance_turn`` pops it before rotating, CR 500.7 stand-in), an
    ``END_TURN`` request flag consumed by the op loop, a ``lost_players``
    ledger and the CR 606.3 ``loyalty_clock`` the legality gate reads.

Design mandates:

  * **flag, don't degrade** — every unsupported verb/effect/quantity/pred
    raises ``NotImplementedError`` at dispatch, naming the node; the
    executor never guesses a silent no-op (LOOK_AT/REVEAL are recorded,
    legitimate no-ops).
  * **explicit decisions** — every controller decision is answered
    externally (C15): an explicit per-op ``decisions`` pool for a KNOWN
    tree, or the 14b vocabulary-addressed stream (per-(vocab, what) FIFO
    / ask-time provider, :mod:`executor.decisions`) which needs no
    pre-enumeration of what an op will arm (B-4 ruling). Exhaustion raises.
  * **executor-owned randomness** — the only randomness is a
    :class:`random.Random` seeded from ``sha256(master_seed:op_seq:tag)``;
    two executors fed the same ops replay byte-identically (P12). The
    replay fingerprint is ``world.fingerprint()`` + the
    :class:`DurationLedger` dump + the 12a event log + the 12b journal and
    binder dumps (ruling 1: the ledger IS replayed state, since state.py
    stays frozen).
  * ``SUPPORTED_VERBS_V1`` is the frozen round-12 capability **contract** —
    the literal 24-verb set v1 goldens were measured against, pinned as a
    version so a later round's handler cannot silently widen a v1 gate.
    ``SUPPORTED_VERBS_V2`` is the honest **live** capability set, derived
    from the dispatch table so the two can never drift. Neither is wired
    into ``compile_pool`` gating (that is 12e's job).

13a brought the library/turn verbs into the live set: ``DRAW`` (the atom the
v1 scope list excluded — now a real handler over :meth:`GameWorld.draw`; the
library->hand ``MOVE_ZONE`` idiom cards compile to stays equally valid),
``SEARCH`` (the Cultivate compile), and the turn-flow four ``FLIP_COIN`` /
``END_TURN`` / ``EXTRA_TURN`` / ``LOSE_GAME``, which mutate **executor-side**
ledgers (the frozen :class:`GameWorld` carries no flip/turn/loss fields) and
are therefore the only verbs needing an executor-backed context.
"""

from __future__ import annotations

import hashlib
import random
from collections.abc import Sequence

from MTG_bot.core.ability_tree import (
    Atom,
    AtomArgs,
    CardRecord,
    Choose,
    Conditional,
    ControllerRef,
    DelayedTrigger,
    EachPlayer,
    Effect,
    Keyword,
    OptionalEffect,
    Phase,
    QConst,
    Seq,
    Step,
    Verb,
)
from MTG_bot.core.compiler.compiler import PoolCompile
from MTG_bot.core.executor.binding import MAX_TRIGGER_FIRES, TriggerBinder
from MTG_bot.core.executor.decisions import DecisionStream, site_digest
from MTG_bot.core.executor.durations import DurationLedger, PtChange
from MTG_bot.core.executor.events import (
    KIND_TAP_STATE,
    KIND_ZONE_CHANGE,
    EventJournal,
    GameEvent,
)
from MTG_bot.core.executor.layers import GrantedAbility, LayerRecord, LayerRegistry
from MTG_bot.core.executor.legality import (
    ManaLedger,
    PaymentPlan,
    ability_playable,
    activate,
    build_payment_plan,
    pay_costs,
    spell_castable,
    spell_record,
)
from MTG_bot.core.executor.quantity import Binding, ExecCtx, eval_filter
from MTG_bot.core.executor.query import (
    ActivationOption,
    CastOption,
    OptionChoice,
    TargetSlot,
    choose_options,
    legal_activations,
    legal_casts,
    legal_search,
    legal_targets,
    optional_offer,
    rest_of,
    spell_target_slots,
    validate_target_selection,
    verb_choose_options,
)
from MTG_bot.core.executor.replacements import (
    PreventionRecord,
    ReplacementRecord,
    ReplacementRegistry,
)
from MTG_bot.core.executor.selectors import players_for_ref, resolve_selector
from MTG_bot.core.executor.stack import (
    SpellObject,
    SpellStack,
    cast,
    cast_card,
    is_land_card,
    land_playable,
    park,
    play_land,
    stack_zone,
)
from MTG_bot.core.executor.verbs import HANDLERS, run_atom, token_oracle_id
from MTG_bot.core.identity import Handle
from MTG_bot.core.state import ZONE_BATTLEFIELD, ZONE_GRAVEYARD, GameWorld

# The v1 capability CONTRACT — the round-12 24-verb set every v1 golden and
# the round-12 cross-check were measured against.  Deliberately a literal
# now, not a derivation: 13a grew the dispatch table (DRAW, SEARCH and the
# turn-flow four), and a versioned contract must not widen just because a
# later round shipped a handler.  ``SUPPORTED_VERBS_V2`` is the live set.
SUPPORTED_VERBS_V1 = frozenset(
    {
        Verb.MOVE_ZONE,
        Verb.EXILE,
        Verb.SACRIFICE,
        Verb.DESTROY,
        Verb.DISCARD,
        Verb.MILL,
        Verb.GAIN_LIFE,
        Verb.LOSE_LIFE,
        Verb.DEAL_DAMAGE,
        Verb.TAP,
        Verb.UNTAP,
        Verb.PUT_COUNTER,
        Verb.REMOVE_COUNTER,
        Verb.MODIFY_PT,
        Verb.SET_PT,
        Verb.CREATE_TOKEN,
        Verb.ADD_MANA,
        Verb.SCRY,
        Verb.SHUFFLE,
        Verb.LOOK_AT,
        Verb.REVEAL,
        Verb.GRANT_ABILITY,
        Verb.LOSE_ABILITY,
        Verb.PREVENT_EFFECT,
    }
)

# The 12e capability set: exactly the verbs ``run_atom`` dispatches to a real
# handler today (round-12 cross-check against all 48 corpus verbs).  Derived,
# never retyped: 12b/12d brought GRANT_ABILITY, LOSE_ABILITY and
# PREVENT_EFFECT, and 13a brought the library/turn verbs (DRAW, SEARCH,
# FLIP_COIN, END_TURN, EXTRA_TURN, LOSE_GAME), and 16a brought FIGHT
# (CR 701.12, the damage-exchange orphan verb).  The remaining non-dispatched
# verbs (CAST, COUNTER_SPELL, PHASE_OUT/PHASE_IN, COPY,
# MANDATE_ATTACK, MANDATE_BLOCK, PAY, ATTACH, GAIN_CONTROL, ...)
# stay outside: event-node-only or out-of-contract internals (ruling 6),
# flagged by ``compile_pool(supported_verbs=...)``, never faked.
SUPPORTED_VERBS_V2 = frozenset(HANDLERS)

Event = tuple[object, ...]

# 14a: the CR 504.5-c turn draw, as the IR node the turn skeleton runs for the
# active player. A module-level constant because ``Atom`` is frozen — one
# node shared by every turn, never re-constructed, so the DRAW atom is
# byte-identical across replays. ``ControllerRef.YOU`` resolves through
# :func:`selectors.role_player` to the context's controller, which the
# skeleton sets to the active seat (:meth:`Executor._turn_draw`).
_TURN_DRAW = Atom(
    verb=Verb.DRAW,
    args=AtomArgs(pairs=(("controller", ControllerRef.YOU), ("amount", QConst(1)))),
)

__all__ = [
    "MAX_TRIGGER_FIRES",
    "SUPPORTED_VERBS_V1",
    "SUPPORTED_VERBS_V2",
    "ActivationOption",
    "Binding",
    "CastOption",
    "DurationLedger",
    "Event",
    "EventJournal",
    "ExecCtx",
    "Executor",
    "GameEvent",
    "GrantedAbility",
    "LayerRecord",
    "LayerRegistry",
    "ManaLedger",
    "OptionChoice",
    "PaymentPlan",
    "PreventionRecord",
    "PtChange",
    "ReplacementRecord",
    "ReplacementRegistry",
    "SpellObject",
    "SpellStack",
    "TargetSlot",
    "TriggerBinder",
    "ability_playable",
    "activate",
    "build_payment_plan",
    "cast",
    "cast_card",
    "choose_options",
    "is_land_card",
    "land_playable",
    "legal_activations",
    "legal_casts",
    "legal_search",
    "legal_targets",
    "optional_offer",
    "park",
    "pay_costs",
    "play_land",
    "rest_of",
    "spell_castable",
    "spell_record",
    "spell_target_slots",
    "stack_zone",
    "validate_target_selection",
    "verb_choose_options",
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
        # 16a (CR 120.6): damage MARKED on cards. The frozen GameWorld has
        # no damage field, so the marks are executor-side replayed state
        # (ruling 1: folded into state_fingerprint, removed at the cleanup
        # step and when the permanent leaves the battlefield).
        self.damage: dict[Handle, int] = {}
        self.journal = EventJournal(world, self.ledger)
        # 12d registries (built BEFORE the binder: the binder's lifecycle
        # hooks reach them during attach).
        self.layers = LayerRegistry(self)
        self.replacements = ReplacementRegistry(self)
        self.binder = TriggerBinder(self)
        self._op_seq = 0
        self._turn_started = False
        # ------------------------------------------------------ 13a turn state
        # The frozen GameWorld has no phase/turn-flow/loss fields, so the
        # turn skeleton owns this ledger (ruling 1: replayed state lives on
        # the executor, and every field below is in state_fingerprint).
        # ``phase`` is the last phase marker recorded (None before the first
        # begin_turn); ``turn_open`` is the "a turn is in progress" flag the
        # legality gates read.
        self.phase: str | None = None
        self.turn_open = False
        # CR 500.7 stand-in: EXTRA_TURN enqueues, advance_turn pops.
        self.extra_turn_queue: list[Handle] = []
        # LOSE_GAME ledger (the emptied-library CR 121.3 loss is the later
        # state-check phase, not a verb).
        self.lost_players: list[Handle] = []
        # CR 606.3: handle -> turn of that permanent's last loyalty act.
        self.loyalty_clock: dict[Handle, int] = {}
        # FLIP_COIN's winner, read by the FLIP_WON conditional of a
        # separate ability row (Tavern Swindler compiles to two).
        self.last_flip_won_by: Handle | None = None
        # END_TURN's deferred close (consumed by the op loop).
        self.end_turn_requested = False
        self._closing_turn = False
        # ------------------------------------------------- 13b stack + mana
        # The spell stack (LIFO frames, CR 405): no-interaction v1 pushes
        # only during a cast, but the container, the ZONE_STACK parking and
        # the fingerprint fold are permanent (risk-1: a future response
        # window reads SpellObject frames, not a re-derived world).
        self.stack = SpellStack()
        # CR 305.1 once-per-turn land gate: seat -> (turn, plays);
        # extra_land_plays is the 13c ADD_LAND_PLAY hook (Azusa), 0 today.
        self.land_ledger: dict[Handle, tuple[int, int]] = {}
        self.extra_land_plays = 0
        # The segment mirror of the frozen mana pool (THIS_MANA
        # restrictions; tags EMPTY everywhere in the 12a/12b corpus, which
        # is what keeps their totals-path replay pins byte-identical).
        self.mana_ledger = ManaLedger()
        # CHOOSE_NAME's write-side (Runed Halo): source permanent -> the
        # chosen name, read back by the NAME_CHOSEN filter predicate.
        self.name_choices: dict[Handle, str] = {}
        # ------------------------------------------------- 13c emblems + attachments
        # Granted emblems are replayed state that is NOT world cards (an
        # emblem never enters a zone): (owner, emblem oracle_id) -> the
        # synthetic Handle("emblem", n) the binder bound its triggers to.
        # The key doubles as the CR 113.7 idempotence gate: a second copy
        # of the same emblem does nothing.
        self.emblems: dict[tuple[Handle, str], Handle] = {}
        self._emblem_seq = 0
        # Attachment relation (auras/equipment): AURA handle -> HOST handle.
        # The frozen CardState has no attachment field, so the table lives
        # here; IS_ATTACHED_TO_SOURCE reads it and the binder drops every
        # edge touching a handle that leaves the battlefield.
        self.attachments: dict[Handle, Handle] = {}
        # Public alias of the seeded factory (the binder builds ExecCtxs too).
        self.rng = self._rng
        # 14b: the vocabulary-addressed decision channel (B-4 ruling). One
        # stream per executor/replay: FIFO priming, ask-time provider and
        # the ask log ride EVERY context the executor builds — effect ops,
        # trigger firings, payments, replacement actions — which is what
        # lets a policy answer a demand a running op armed mid-drain.
        self.decisions = DecisionStream()

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
        x_value: int | None = None,
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
            x_value=x_value,
            stream=self.decisions,
            # 14d (B-7): the journal rides on every effect context too (the
            # history preds answer identically from a query ctx or a firing
            # ctx — §8.3 query/runtime identity over the SAME rows).
            journal=self.journal,
        )

    def _cast_ctx(
        self,
        handle: Handle,
        seat: Handle,
        bindings: dict[str, Binding],
        decisions: Sequence[str],
        x: int | None,
    ) -> ExecCtx:
        """13b: the spell-resolution context — the ordinary effect context
        with the cast's declared X bound (CR 601.2f: X was chosen with the
        total cost; the effect's ``{X}`` readings resolve off it)."""
        return self._ctx(
            source=handle,
            controller=seat,
            bindings=bindings,
            decisions=decisions,
            x_value=x,
        )

    def mana_permission(self, seat: Handle) -> bool:
        """ALL_YOURS for ``seat`` (Orrery's "you may spend mana as though
        it were mana of any color") — the live layer query in one place so
        plan-building never reaches into the registry directly."""
        return self.layers.all_yours_live(seat)

    # ------------------------------------------------------------ execution

    def execute(
        self,
        atom: Atom,
        *,
        source: Handle,
        controller: Handle,
        bindings: dict[str, Binding] | None = None,
        decisions: Sequence[str] = (),
    ) -> tuple[Event, ...]:
        """Run one Atom; returns the 12a events this call appended.
        Unsupported verbs raise ``NotImplementedError`` at dispatch. The
        atom's world changes are journalled; any trigger the change arms
        drains afterwards (APNAP). Trigger-drain decisions arrive through
        the executor's vocabulary-addressed stream (14b, B-4) — the old
        positional ``trigger_decisions`` kwarg is deleted: it could not
        carry demands the op itself armed."""
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
        self._settle()
        self._consume_end_turn()
        return tuple(self.events[start:])

    def apply_effect(
        self,
        effect: Effect,
        *,
        source: Handle,
        controller: Handle,
        bindings: dict[str, Binding] | None = None,
        decisions: Sequence[str] = (),
    ) -> tuple[Event, ...]:
        """Run an Effect tree; the per-op pool ``decisions`` covers the
        KNOWN tree in ask order, and every demand it cannot serve reaches
        the executor's vocabulary-addressed stream (14b). OptionalEffect
        asks the query-narrowed offer vocab (``fire``/``skip``), Seq runs
        its steps, Conditional judges the pred against the *source*
        handle, Choose (12d: ONE decision token = the index of the chosen
        option-set in ``query.choose_options`` order), EachPlayer (14f:
        one sub-execution per denoted player, controller rotated — the
        inner effect is compiled YOU-relative, so the rotation IS the
        rebinding) and DelayedTrigger (scheduled, C22) are wired; Repeat
        raises as an unimplemented node (12e)."""
        if not isinstance(
            effect,
            (
                Atom,
                Seq,
                OptionalEffect,
                Conditional,
                DelayedTrigger,
                Choose,
                EachPlayer,
            ),
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
        self._settle()
        self._consume_end_turn()
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
            # 14b (B-5, query/runtime identity): the ASK vocabulary is the
            # query surface's own narrowed optional_offer — the policy gets
            # exactly what a query would answer ("may pay {2}" with an empty
            # pool offers only skip, CR 117.3, so a provider can never
            # answer fire where firing is illegal). The site tag keys the
            # answer to THIS ability's offer (B-4 vocabulary addressing).
            offer = optional_offer(
                self,
                effect,
                source=ctx.source,
                controller=ctx.controller,
                bindings=ctx.bindings,
            )
            if ctx.take_decision(offer, f"may:{ctx.source}") == "fire":
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
            pick = ctx.take_decision(
                vocab,
                f"choose:{ctx.source}:{site_digest(tuple(o.option_idxs for o in opts))}",
            )
            for idx in opts[int(pick)].option_idxs:
                self._run_effect(effect.options[idx], ctx)
        elif isinstance(effect, EachPlayer):
            # 14f (B-20): "each opponent …" (Goremand's ETB sacrifice,
            # Keral Keep Disciples' damage, Pursued Whale's tokens, Thieves'
            # Guild Enforcer's mills — the four corpus faces, ALL_OPPONENTS).
            # One sub-execution per denoted player with the CONTROLLER
            # rotated: the templates compile the inner effect YOU-relative
            # (b2a/b2b ruling — Goremand's SACRIFICE filter CONTROLLER_IS
            # YOU, MILL's controller role, Zone(PLAYER,YOU)), so rotation
            # IS the rebinding; the spell's designations stay visible
            # (bindings carried, never rewritten). Iteration order is
            # players_for_ref's seat order; CR 800.2 runs each-player
            # effects APN-first — in the duel the two coincide, and the
            # seat-order reading is the documented convention (doc
            # 09-30/09), never a silent rule. The per-op decision POOL
            # cursor rides across the sub-contexts (one positional supply
            # answers every station in ask order, byte-identical to the
            # single-context consumption the 12a-era pins use) and is
            # written back; the vocabulary-addressed stream lanes are
            # executor-owned and need no forwarding. Each inner atom
            # journals its own boundary under the stable source.
            for player in players_for_ref(effect.ref, ctx):
                inner = self._ctx(
                    source=ctx.source,
                    controller=player,
                    bindings=ctx.bindings,
                    decisions=ctx.decisions,
                    x_value=ctx.x_value,
                )
                inner.decision_idx = ctx.decision_idx
                self._run_effect(effect.effect, inner)
                ctx.decision_idx = inner.decision_idx
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
            self.damage.pop(anchor, None)  # 16a: CR 120.6, marks leave with it

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

    def fire_triggers(self) -> int:
        """Drain the pending trigger queue (APNAP, Handle-tie-broken).
        Decisions arrive through the executor's stream (14b): may-offers
        hit the vocabulary-addressed lanes, nothing positional is consumed.
        Returns the number of firings."""
        self.binder.on_events()
        return self.binder.fire_all()

    # ------------------------------------ 16a: damage marks + state checks

    def mark_damage(self, card: Handle, n: int) -> None:
        """Mark ``n`` damage on a card (CR 120.4). The mark STAYS — marked
        until the permanent leaves the battlefield (CR 120.6) or the cleanup
        step removes it (CR 514.2); destruction is the state-based check
        below, never the dealing of the damage itself."""
        if n <= 0:
            return
        self.damage[card] = self.damage.get(card, 0) + n

    def _lethal_creatures(self) -> list[Handle]:
        """CR 704.5a + 704.3 read over the battlefield (Handle-sorted,
        ruling 5): a creature marked with damage >= its LIVE toughness dies
        unless it has indestructible (CR 702.12b); toughness <= 0 kills even
        an indestructible creature. A permanent with no toughness (lands,
        non-creature artifacts) is not a creature-side death at all."""
        dying: list[Handle] = []
        for player in self.world.player_order:
            for card in self.world.players[player].zone(ZONE_BATTLEFIELD).entries:
                identity = self.world.cards[card].identity
                _power, toughness = self.ledger.effective_pt(identity, card)
                if toughness is None:
                    continue
                if toughness <= 0:
                    dying.append(card)
                elif self.damage.get(card, 0) >= toughness and not (
                    self.layers.keyword_of(card, Keyword.INDESTRUCTIBLE)
                ):
                    dying.append(card)
        return sorted(dying)

    def _state_checks(self) -> int:
        """The 16a state-based action sweep (CR 704.3: repeat until the
        table is stable), run at every settle point — the end of each
        public op. Lethal creatures die when the thing that hurt them
        finishes, not inside the damage atom (the 12a instant-lethal
        stand-in is retired). Each kill batch is journalled as its OWN atom
        boundary (cause ``None``: an SBA has no card behind it, coverage
        credits none) so dies-triggers see the C18 was-PT snapshot, then
        those firings drain before the next scan."""
        fired = 0
        while True:
            self.layers.recompute()  # live keywords/toughness must be current
            dying = self._lethal_creatures()
            if not dying:
                return fired
            before = self.journal.snapshot()
            start = len(self.events)
            for card in dying:
                self.damage.pop(card, None)
                self.world.move_to_zone(
                    card, self.world.controller_of(card), ZONE_GRAVEYARD
                )
                self.events.append((len(self.events), "STATE_CHECK", str(card), "DIES"))
            new_events = self.journal.record_atom(
                before, None, "STATE_CHECK", self.events[start:]
            )
            self._on_zone_changes(new_events)
            self.binder.on_events()
            fired += self.binder.fire_all()

    def _settle(self) -> int:
        """Match the journal's new events and drain — the end of every
        public op. With nothing attached this is a no-op (12a behaviour).
        12d: the settle tail is also the recompute point — WHILE-condition
        truth is re-evaluated on the ledger, and the layer registry
        re-reads the set (new/lost members, condition toggles) and rebuilds
        the keyword / granted-ability oracles. All of it is pure function
        of the journal's final state, so replays are byte-identical."""
        self.binder.on_events()
        fired = self.binder.fire_all()
        # 16a: the state-based lethal-damage check sits at the settle point
        # (CR 704.3), so execute / apply_effect / end_turn all drain it.
        fired += self._state_checks()
        self.ledger.settle_while(self._while_eval)
        self.layers.recompute()
        return fired

    def _consume_end_turn(self) -> None:
        """13a: an END_TURN atom only SETS the request flag (mid-op state
        must not change under the atoms still running); the close happens at
        the op boundary through the ONE turn skeleton, so there is exactly
        one end-of-turn path (markers, sweeps, delayed-trigger expiry). A
        nested apply_effect (payment step, replacement action) consuming the
        flag first is harmless — the flag is single-shot."""
        if not self.end_turn_requested:
            return
        self.end_turn_requested = False
        if self.turn_open and not self._closing_turn:
            # Re-entrancy guard: a trigger fired BY the close may itself
            # request END_TURN; the turn is already closing, so that request
            # is consumed as a no-op rather than recursing.
            self._closing_turn = True
            try:
                self.end_turn()
            finally:
                self._closing_turn = False

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

    def begin_turn(self, player: Handle) -> int:
        """Begin ``player``'s turn: active rotation, turn clock, the UNTAP
        step (12d), UPKEEP and FIRST_MAIN markers, per-turn event trackers
        reset; drains triggers. Returns the firing count."""
        if player not in self.world.players:
            raise ValueError(f"begin_turn: {player} is not a player of this world")
        if self._turn_started:
            self.world.turn += 1
        self._turn_started = True
        self.world.active_player = player
        self.turn_open = True
        # The UNTAP step has no grammar phase marker (Phase is the closed
        # {UPKEEP, FIRST_MAIN, COMBAT, END_TURN} vocab), so the clock sits
        # at UPKEEP across it — nothing can activate during a rule step.
        self.phase = Phase.UPKEEP.name
        self.journal.begin_turn(player)
        self._untap_step(player)
        # UNTIL_NEXT_TURN expiry: the recorded owner's turn is beginning —
        # the precise next-turn-start end the 12a ledger deferred (the
        # binder's DELAYED windows keep their documented Eot stand-in).
        self.ledger.expire_until_next_turn(player)
        self.layers.expire_until_next_turn(player)
        self.replacements.expire_until_next_turn(player)
        self.journal.record_turn_phase(Phase.UPKEEP.name)
        self.phase = Phase.UPKEEP.name
        # 14a: the DRAW step (CR 504.5-c), journalled INSIDE the skeleton so
        # 'whenever you draw' triggers and the fingerprint see it, and AFTER
        # the UPKEEP marker so beginning-of-upkeep triggers keep their CR
        # ordering ahead of draw triggers.
        self._turn_draw(player)
        self.journal.record_turn_phase(Phase.FIRST_MAIN.name)
        self.phase = Phase.FIRST_MAIN.name
        return self._settle()

    def _turn_draw(self, player: Handle) -> None:
        """The CR 504.5-c draw step of the active player (14a).

        The frozen grammar has no phase-marker draw — the DRAW *verb* is the
        corpus idiom (`library -> hand`), so the skeleton runs the shared
        :data:`_TURN_DRAW` atom inline through the same journalled path a
        card's own draw uses: the DRAW handler calls
        :meth:`GameWorld.draw` and the journal auto-detects the
        library->hand move as a MOVE_ZONE atom boundary.

        Two deliberate omissions, both the skeleton's existing discipline:
        no nested ``_settle`` (the turn has exactly ONE settle, the one at
        the tail of :meth:`begin_turn`, and a draw-armed trigger already
        drains there in clock order behind the UPKEEP marker) and no nested
        ``_consume_end_turn`` (an END_TURN requested by such a trigger
        closes at the next op boundary, never mid-skeleton). An empty
        library no-ops here (CR 121.2 through ``_v_draw``); CR 121.3's
        'draw from empty = loss' is a STATE CHECK, not a verb (13a ruling),
        and belongs to the caller's loss scan, not to this step.

        ``source`` is the seat: no permanent drew this card, and the
        journal's cause column records the seat, which is what
        a 'you drew' trigger's APNAP controller already is."""
        self._op_seq += 1
        ctx = self._ctx(source=player, controller=player, bindings=None, decisions=())
        self._run_effect(_TURN_DRAW, ctx)

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

    def advance_turn(self) -> int:
        """End the active turn (if one is open) and begin the next seat's
        turn — the skeleton's round-robin, EXCEPT that a pending EXTRA_TURN
        entry is popped first (13a): "the next turn belongs to that player"
        (CR 500.7). Nested grants from DIFFERENT players resolve in queue
        order rather than the full CR 500.7 dependency graph — documented
        simplification, no golden exercises it. Returns the combined
        firings."""
        order = self.world.player_order
        if self.world.active_player is None or not self._turn_started:
            nxt = order[0]
        else:
            if self.extra_turn_queue:
                nxt = self.extra_turn_queue.pop(0)
            else:
                idx = order.index(self.world.active_player)
                nxt = order[(idx + 1) % len(order)]
            if self.turn_open:
                # An END_TURN atom already closed the turn inside the op —
                # never emit a second END_TURN marker for it.
                self.end_turn()
        return self.begin_turn(nxt)

    def end_turn(self) -> int:
        """END_TURN marker FIRST (end-step triggers see the pre-expiry
        state), trigger drain, THEN the end-of-turn expiry sweep: Eot
        ledger entries, Eot-tagged LAYER records (12d: until-end-of-turn
        grants die here) and Eot-tagged PREVENTION records, and the
        turn-window delayed triggers (C22). Returns the firing count."""
        self.phase = Phase.END_TURN.name
        self.turn_open = False
        self.journal.record_turn_phase(Phase.END_TURN.name)
        fired = self._settle()
        self.ledger.sweep_at_eot()
        self.layers.sweep_at_eot()
        self.replacements.sweep_at_eot()
        self.damage.clear()  # 16a: CR 514.2 — cleanup removes marked damage
        self.binder.expire_delayed()
        # Rebuild the oracles after the sweep — a granted keyword that
        # expired at end of turn must not survive into next turn's
        # keyword_of/legal_activations.
        self.layers.recompute()
        return fired

    # ---------------------------------------------------- 13c emblem / attach

    def get_emblem(self, owner: Handle, emblem: CardRecord) -> Handle | None:
        """Grant ``owner`` their emblem (CR 113.7). Returns the synthetic
        handle, or ``None`` when the owner ALREADY has this emblem (a
        second copy does nothing — the idempotence gate, visible as the
        duplicate event row in the verb handler). The emblem is executor
        replayed state, not a world card: its triggers bind to the owner
        through the binder, its statics anchor to the owner in the layer
        registry, and both are folded into the fingerprint."""
        key = (owner, emblem.oracle_id)
        if key in self.emblems:
            return None
        handle = Handle("emblem", self._emblem_seq)
        self._emblem_seq += 1
        self.emblems[key] = handle
        self.binder.bind_emblem(handle, emblem, owner)
        self.layers.recompute()  # emblem statics are live the moment it lands
        return handle

    def attach_aura(self, aura: Handle, host: Handle) -> None:
        """Record that ``aura`` (equipment/aura permanent) is attached to
        ``host`` — the API half of the IS_ATTACHED_TO_SOURCE oracle (the
        corpus has no enchantment/equipment cast surface in v1, so
        attachment is an explicit op, replayed and fingerprint-folded;
        CR 303.4-style leave-detachment is automatic in the binder)."""
        if aura not in self.world.cards or host not in self.world.cards:
            raise ValueError(
                f"attach_aura: both ends must be world cards ({aura}, {host})"
            )
        if aura == host:
            raise ValueError(f"attach_aura: {aura} cannot attach to itself")
        self.attachments[aura] = host
        self.layers.recompute()  # "equipped creature" scopes re-read the table

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
        # 16a: damage marks are replayed state too (ruling 1, CR 120.6).
        h.update(repr(sorted(self.damage.items())).encode())
        # 13a: the turn ledger is replayed state too (same ruling).
        h.update(
            repr(
                (
                    self.phase,
                    self.turn_open,
                    tuple(self.extra_turn_queue),
                    tuple(self.lost_players),
                    tuple(sorted(self.loyalty_clock.items())),
                    self.last_flip_won_by,
                    self.end_turn_requested,
                )
            ).encode()
        )
        # 13b: the STACK COMPLETENESS FOLD. state.py's fingerprint loop
        # iterates PLAYER_ZONES and ZONE_STACK is NOT one of them (L48:
        # "the stack is shared, so it is not in this list"), so a card
        # parked on the stack is invisible to world.fingerprint() BY
        # DESIGN — this fold is what closes that hole: two worlds
        # differing only by a stack card MUST differ here (pinned by
        # test_stack_visible_in_executor_fingerprint). The land ledger,
        # mana segments and chosen names are executor-side replayed
        # state under the same ruling.
        h.update(repr(self.stack.dump()).encode())
        h.update(
            repr(
                tuple(sorted((str(s), v) for s, v in self.land_ledger.items()))
            ).encode()
        )
        h.update(repr(self.extra_land_plays).encode())
        h.update(repr(self.mana_ledger.dump()).encode())
        h.update(
            repr(
                tuple(sorted((str(s), n) for s, n in self.name_choices.items()))
            ).encode()
        )
        # 13c: the emblems table (owner-keyed synthetic handles) and the
        # attachment edges are replayed state under the same ruling — a
        # replay that granted a different emblem set or missed an
        # attachment MUST differ here.
        h.update(
            repr(
                tuple(
                    sorted(
                        ((str(owner), oid), str(handle))
                        for (owner, oid), handle in self.emblems.items()
                    )
                )
            ).encode()
        )
        h.update(
            repr(
                tuple(sorted((str(a), str(h_)) for a, h_ in self.attachments.items()))
            ).encode()
        )
        return h.hexdigest()

    # Alias the module-level helpers that tests and callers reach through
    # the package face.
    resolve_selector = staticmethod(resolve_selector)
    token_oracle_id = staticmethod(token_oracle_id)
