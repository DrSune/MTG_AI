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
    FAnd,
    Keyword,
    OptionalEffect,
    Phase,
    QConst,
    Selector,
    SelectorMode,
    Seq,
    Step,
    Verb,
    Zone,
    ZoneKind,
)
from MTG_bot.core.compiler.compiler import PoolCompile
from MTG_bot.core.executor.binding import MAX_TRIGGER_FIRES, TriggerBinder
from MTG_bot.core.executor.decisions import DecisionStream, site_digest
from MTG_bot.core.executor.durations import DurationLedger, PtChange
from MTG_bot.core.executor.events import (
    KIND_COMBAT_DAMAGE,
    KIND_DECLARE_ATTACKERS,
    KIND_DECLARE_BLOCKERS,
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
    block_pair_blocked_reason,
    blocker_askable,
    build_payment_plan,
    legal_attackers,
    mandated_attackers,
    mandated_to_be_blocked,
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

# 16b: the player-side target of one combat-damage atom — the same
# PLAYER-zone TARGET Selector shape the player-damage tests use
# (test_executor_verbs L200); the dealer rides ctx.source (the journal's
# cause column), the recipient is the bound handle (14c B-16: a bound
# handle outranks the selector — a PLAYER handle bound to a PLAYER-zone
# selector is returned as-is).
_PLAYER_TARGET = Selector(
    QConst(1),
    SelectorMode.TARGET,
    FAnd(children=()),
    Zone(ZoneKind.PLAYER, ControllerRef.ANY),
)

# 16c: the CARD lane of the combat-damage atom. A player-zone selector is
# deliberately BLIND to a binding (the 16a Brash rule in role_handles), so
# a blocker recipient must be announced through a battlefield-zone TARGET
# selector — binding-first — or the wave would keep landing on the
# defending player no matter what was assigned.
_CARD_TARGET = Selector(
    QConst(1),
    SelectorMode.TARGET,
    FAnd(children=()),
    Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),
)


def _combat_damage_atom(amount: int, recipient: object) -> Atom:
    """One DEAL_DAMAGE atom of ``amount`` to the announced recipient. A
    builder, not a constant: the amount is per-dealer, the RECIPIENT picks
    the lane (16c — blockers take their announced share, the attacked
    object takes the rest; pre-16c every combat atom was the unblocked
    player shape), and the frozen-Atom discipline keeps every atom of one
    damage step byte-identical across replays."""
    target = _PLAYER_TARGET if str(recipient).startswith("player:") else _CARD_TARGET
    return Atom(
        verb=Verb.DEAL_DAMAGE,
        args=AtomArgs(pairs=(("amount", QConst(amount)), ("target", target))),
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
        # --------------------------------------------------- 16b combat state
        # The frozen GameWorld has no combat fields, so the attack record
        # is executor-side replayed state (ruling 1, folded into
        # state_fingerprint): the current attackers in declaration order,
        # each one's ATTACKED object (v1: the defending player — blocker
        # and planeswalker assignment are 16c), the phase's defending seat,
        # and the declare-window flag the enters-attacking token path
        # reads (CR 508.1i). ``mandates`` is the DISPATCHED MANDATE_ATTACK
        # ledger (the static shape lives as layers' "mandate" records).
        self.attackers: list[Handle] = []
        self.attacked: dict[Handle, Handle] = {}
        self.defending_player: Handle | None = None
        self.declaring = False
        self._declare_group = 0
        self.mandates: set[Handle] = set()
        # -------------------------------------------------- 16c block state
        # ``blocked_by``: attacker -> the creatures blocking it, in DECLARE
        # order (CR 509.1b: one attacker per blocker, so a handle appears in
        # exactly one list; multiple blockers per attacker ARE legal — the
        # assignment order is asked per attacker, CR 510.1). Cleared with
        # the attack record at end of combat; replayed state (ruling 1).
        self.blocked_by: dict[Handle, list[Handle]] = {}
        # DISPATCHED MANDATE_BLOCK ledger (the static shape rides layers'
        # "mandate_block" records; Canopy Stalker's rule line).
        self.mandate_block: set[Handle] = set()
        # DISPATCHED DAMAGE_ASSIGN_POLICY scopes (GRANT_ABILITY-carried
        # statics read through layers.policy_as_unblocked; the dispatch
        # shape records the scope word here keyed by its source).
        self.damage_policies: dict[Handle, str] = {}
        # The combat-damage wave flag: set for the atom boundaries inside
        # one combat-damage substep so record_atom marks the DAMAGE rows
        # (amount, True) — the DamageDealtEvent ``combat`` scope (16c,
        # Garruk's Harbinger / Subira's delayed trigger).
        self._combat_wave_open = False
        # Deathtouch marks (CR 702.2b): a creature carrying ANY damage
        # marked by a deathtouch source dies at the state check even below
        # lethal; the flag rides the ledger beside the amount.
        self.damage_deathtouch: set[Handle] = set()
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
                before,
                ctx.source,
                effect.verb.name,
                self.events[start:],
                combat=self._combat_wave_open,
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
            self.damage_deathtouch.discard(anchor)  # 16c: the flag rides along
            # 16c: a departing permanent leaves no trace in the block record
            # (a dead blocker stops blocking, a dead attacker forgets).
            self.blocked_by.pop(anchor, None)
            for blockers in self.blocked_by.values():
                if anchor in blockers:
                    blockers.remove(anchor)
            self.mandates.discard(anchor)
            self.mandate_block.discard(anchor)
            self.damage_policies.pop(anchor, None)

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

    def mark_damage(self, card: Handle, n: int, deathtouch: bool = False) -> None:
        """Mark ``n`` damage on a card (CR 120.4). The mark STAYS — marked
        until the permanent leaves the battlefield (CR 120.6) or the cleanup
        step removes it (CR 514.2); destruction is the state-based check
        below, never the dealing of the damage itself. 16c: ``deathtouch``
        (CR 702.2b) — damage from a deathtouch source is LETHAL damage no
        matter the amount, so the flag rides the ledger for the SBA."""
        if n <= 0:
            return
        self.damage[card] = self.damage.get(card, 0) + n
        if deathtouch:
            self.damage_deathtouch.add(card)

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
                if (
                    toughness <= 0
                    or (
                        self.damage.get(card, 0) >= toughness
                        or card in self.damage_deathtouch  # 16c CR 702.2b
                    )
                    and not (self.layers.keyword_of(card, Keyword.INDESTRUCTIBLE))
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
                self.damage_deathtouch.discard(card)
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
    # the UNTAP STEP (12d) + phase markers. 16b adds the COMBAT phase
    # (:meth:`Executor.combat_step`, driven between the main-phase acts
    # and end_turn by the harness); the markers the frozen grammar has
    # triggers for: UPKEEP + FIRST_MAIN + COMBAT at the beginning of a
    # turn's work, END_TURN at the end of one. The untap step is a
    # RULE step, not an Atom: it mutates the
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

    # ------------------------------------------------- 16b: the COMBAT phase
    #
    # FIRST_MAIN -> COMBAT -> SECOND_MAIN -> END. R16-1 (doc /11): the
    # phase runs UNINTERRUPTED - no opponent response window (our instants
    # are own-turn-only by construction, so nothing illegal is claimed);
    # the CR 704.3 honesty is the SBA sweep at every settle point between
    # the damage steps and the phase hand-off. 16c ships the blocker step
    # (CR 509), the damage-assignment asks (CR 510), TRAMPLE, DEATHTOUCH
    # and the Herald AS_UNBLOCKED policy; the remaining documented v1
    # limit: planeswalker attack assignment (players only — the binary
    # attack ask names no attacked object and no corpus card needs a PW
    # attack, doc 14).
    # v1 limits, documented per the R16-1 mandate: no chain spells, no
    # flash responses.

    def combat_step(self, seat: Handle) -> int:
        """Run the active player's whole COMBAT phase (CR 506-511 v1):
        the beginning-of-combat marker (the Phase.COMBAT cards fire), the
        declare-attackers step (one binary ask per legal creature, whole-
        set validated, mandates narrowing the vocab), the declare-blockers
        step (CR 509: one ask per defending creature, candidates = the
        attackers it may legally block plus NONE, CR 509.1a untapped-only,
        whole-assignment validated), the combat damage step(s) with the
        first/double-strike split and the CR 510 assignment asks, and the
        end of combat. Returns the trigger-firing count. A creature with no
        legal declaration is never asked (it cannot attack); a mandatory
        attacker's ask is ATTACK-only (C15 - the policy is never offered
        an illegal answer)."""
        world = self.world
        if not self.turn_open:
            raise ValueError(f"combat_step: no turn is open ({seat})")
        if world.active_player != seat:
            raise ValueError(f"combat_step: {seat} is not the active player")
        opponents = [p for p in world.player_order if p != seat]
        if not opponents:
            raise ValueError(f"combat_step: {seat} has no defending player")
        self.defending_player = opponents[0]
        fired = 0
        # Beginning of combat (TurnPhaseEvent COMBAT - the BINDING 16b
        # feed: Battle-Rattle Shaman, Dire Fleet Warmonger, Adherent of
        # Hope, the Basri Ket / Liliana Waker emblems).
        self.journal.record_turn_phase(Phase.COMBAT.name)
        self.phase = Phase.COMBAT.name
        fired += self._settle()
        # Declare attackers (CR 508.1). The declare window stays open
        # across the post-declare settle so enters-attacking tokens the
        # attack triggers create JOIN the attack (CR 508.1i).
        self._op_seq += 1
        self._declare_group = self._op_seq
        self.declaring = True
        try:
            self._declare_attackers(seat)
            fired += self._settle()
        finally:
            self.declaring = False
        # Declare blockers (CR 509, 16c) - after the attack-trigger drain
        # (CR 508.3: the triggers resolve BEFORE the blocking player gets
        # the declaration duty), before any damage step.
        fired += self._declare_blockers(seat)
        # CR 509.4: the declare-blockers turn-based action ends, both
        # players get passes, and the BLOCK triggers (Snarespinner's
        # "blocks a creature with flying" pump, Gloom Sower's life swap,
        # Elder Gargaroth's choice) resolve BEFORE the combat damage step.
        fired += self._settle()
        fired += self._combat_damage(seat)
        # End of combat: the settle is the R16-1 SBA pass; the attack
        # record closes with the phase (CR 506.4 - nothing "is attacking"
        # once combat ended, and IS_ATTACKING reads exactly that).
        fired += self._settle()
        self.attackers = []
        self.attacked = {}
        self.blocked_by = {}
        self.defending_player = None
        # The frozen grammar's Phase vocab has no SECOND_MAIN member, so
        # the marker is executor-clock-only: the legality gates read the
        # phase string and correctly stop offering FIRST_MAIN activations.
        self.phase = "SECOND_MAIN"
        return fired

    def _declare_attackers(self, seat: Handle) -> None:
        """The CR 508.1 binary asks + the whole-set check, then the
        declaration commit: tap everything that declared except the
        vigilance carriers (CR 702.53a), journalled as TapState rows
        BEFORE the declare rows (a "becomes tapped" trigger sits UNDER
        the attack triggers, CR 508.1m), then one DECLARE_ATTACKERS row
        per attacker - shared declare-group id, the binder's CR 603.2
        dedup key. Tapped creatures are legal attackers (tapping to
        declare is not a cost); sickness reads the journal (legality.py).
        """
        world = self.world
        candidates = legal_attackers(self, seat)
        mandated = mandated_attackers(self, seat) & set(candidates)
        chosen: list[Handle] = []
        for card in candidates:
            vocab = ("ATTACK",) if card in mandated else ("ATTACK", "DECLINE")
            ctx = self._ctx(source=card, controller=seat, bindings=None, decisions=())
            if ctx.take_decision(vocab, f"attack:{card}:{world.turn}") == "ATTACK":
                chosen.append(card)
        # Whole-set validation of the ASSEMBLED set. The asks mutate no
        # state, so re-deriving legality is a re-check and the mandate
        # inclusion was narrowed at the ask - either failure here is an
        # engine invariant violation, not a policy error to repair.
        legal_now = set(legal_attackers(self, seat))
        if not set(chosen) <= legal_now:
            raise RuntimeError(
                f"executor: declare-attackers set check failed for {seat} - "
                f"{[str(c) for c in chosen if c not in legal_now]} are not "
                "legal attackers"
            )
        if not mandated <= set(chosen):
            raise RuntimeError(
                f"executor: MANDATE_ATTACK violated - "
                f"{[str(c) for c in sorted(mandated - set(chosen))]} had to "
                "attack (asks were narrowed, this cannot happen)"
            )
        if not chosen:
            return
        defender = self.defending_player
        assert defender is not None  # combat_step opens the phase with one
        for card in chosen:
            self.attackers.append(card)
            self.attacked[card] = defender
            if self.layers.keyword_of(card, Keyword.VIGILANCE):
                continue
            world.cards[card].tapped = True
            self.journal.emit(KIND_TAP_STATE, card, None, "ATTACK_STEP", (True,))
        for card in chosen:
            self.journal.emit(
                KIND_DECLARE_ATTACKERS,
                card,
                None,
                "ATTACK_STEP",
                (self._declare_group,),
            )

    # ------------------------------------------------ 16c: declare blockers

    def _declare_blockers(self, seat: Handle) -> int:
        """CR 509 v1 (16c). ONE ask per defending creature that could legal-
        ly block at least one attacker, Handle-sorted (C16), site
        ``block:<card>:<turn>``: the vocabulary is the attackers that perma-
        nent may block (CR 509.1a untapped-only, CR 509.1b one attacker per
        blocker, reach/menace/protection and the PREVENT_EFFECT restrictions
        — Tome Anima "can't be blocked", Pirate "can't block", Shacklegeist
        "can block only creatures with flying", Subira's activated target)
        plus the NONE option. The NONE word is DROPPED only when dropping
        it keeps the assembled assignment CR-legal (a must-be-blocked
        attacker this blocker may take — Canopy Stalker, CR 509.1h; or the
        last unasked blocker in front of a menace attacker stuck at one
        blocker, CR 702.113) — never when the answer would merely be
        inadvisable (C15). Tapped/defender creatures are never asked; a
        creature legal against nothing is never asked. Each committed pair
        emits one DECLARE_BLOCKERS row (subject = the blocker — the
        DeclareBlockersEvent feed: filter/subject read the blocker, blocked
        reads the attacker; BecomesBlockedEvent answers the same rows for
        the blocked-side source). The settle after the step drains the
        block triggers (Elder Gargaroth's choice, Snarespinner's +2/+0)
        before any damage step (CR 509.4)."""
        world = self.world
        defender = self.defending_player
        attackers = self._live_attackers(seat)
        if defender is None or not attackers:
            return 0
        assigned: dict[Handle, list[Handle]] = {}
        candidates = sorted(
            card
            for card in world.players[defender].zone(ZONE_BATTLEFIELD).entries
            if blocker_askable(self, card, attackers)
        )
        if not candidates:
            return 0
        mandated = mandated_to_be_blocked(self) & set(attackers)
        by_word = {str(a): a for a in attackers}
        asked: set[Handle] = set()
        for position, blocker in enumerate(candidates):
            remaining_after = len(candidates) - position - 1
            legal = [
                attacker
                for attacker in attackers
                if block_pair_blocked_reason(self, blocker, attacker) is None
                and (
                    not self.layers.keyword_of(attacker, Keyword.MENACE)
                    or len(assigned.get(attacker, ())) >= 1
                    or remaining_after >= 1
                )
            ]
            forced = [
                attacker
                for attacker in legal
                if attacker in mandated and not assigned.get(attacker)
            ]
            if forced:
                vocab = tuple(str(a) for a in forced)
            else:
                words = [str(a) for a in legal]
                repair = any(
                    self.layers.keyword_of(attacker, Keyword.MENACE)
                    and len(assigned.get(attacker, ())) == 1
                    for attacker in attackers
                )
                if not (repair and remaining_after == 0):
                    words.append("NONE")
                if not words:
                    raise RuntimeError(
                        f"executor: blocker ask for {blocker} narrowed to "
                        "nothing - the menace/must-block narrowing left an "
                        "unrepairable assignment (engine invariant)"
                    )
                vocab = tuple(words)
            if not legal and "NONE" not in vocab:
                raise RuntimeError(
                    f"executor: blocker ask for {blocker} forces an illegal "
                    f"pair {vocab} (engine invariant)"
                )
            asked.add(blocker)
            ctx = self._ctx(
                source=blocker, controller=defender, bindings=None, decisions=()
            )
            answer = ctx.take_decision(vocab, f"block:{blocker}:{world.turn}")
            if answer == "NONE":
                continue
            attacker = by_word[answer]
            reason = block_pair_blocked_reason(self, blocker, attacker)
            if reason is not None:
                raise RuntimeError(
                    f"executor: declare-blockers committed an illegal pair "
                    f"{blocker} -> {attacker}: {reason} (asks mutate no state, "
                    "so this is an engine bug, not a policy answer)"
                )
            assigned.setdefault(attacker, []).append(blocker)
        # Whole-assignment validation (asks mutate nothing, so re-deriving
        # legality is a re-check; a violation is an engine invariant breach).
        for attacker, blockers in assigned.items():
            if self.layers.keyword_of(attacker, Keyword.MENACE) and len(blockers) < 2:
                raise RuntimeError(
                    f"executor: menace attacker {attacker} was blocked by "
                    f"exactly one creature {[str(b) for b in blockers]} "
                    "(CR 702.113 — the ask narrowing should have prevented "
                    "this)"
                )
        for attacker in mandated:
            if assigned.get(attacker):
                continue
            assignable = {
                card
                for card in asked
                if block_pair_blocked_reason(self, card, attacker) is None
            }
            if assignable - {b for bs in assigned.values() for b in bs}:
                raise RuntimeError(
                    f"executor: MANDATE_BLOCK violated - {attacker} had to be "
                    "blocked and an unassigned legal blocker existed"
                )
        fired = 0
        for attacker in sorted(assigned):
            for blocker in assigned[attacker]:
                self.blocked_by.setdefault(attacker, []).append(blocker)
                self.journal.emit(
                    KIND_DECLARE_BLOCKERS,
                    blocker,
                    None,
                    "BLOCK_STEP",
                    (attacker, self._declare_group),
                )
        return fired

    def join_attack(self, creature: Handle) -> None:
        """CR 508.1i - a creature PUT ONTO THE BATTLEFIELD ATTACKING
        (Falconer Adept's Bird, Basri Ket's [-2] Soldier) joins the open
        attack record with its own declare row, no legality pass (it was
        never declared). Outside the declare window the verb path never
        calls this."""
        if self.defending_player is None or creature in self.attackers:
            return
        self.attackers.append(creature)
        self.attacked[creature] = self.defending_player
        self.journal.emit(
            KIND_DECLARE_ATTACKERS,
            creature,
            None,
            "ATTACK_STEP",
            (self._declare_group,),
        )

    def _live_attackers(self, seat: Handle) -> list[Handle]:
        """The attack record minus anything that left or changed sides -
        SBA-swept attackers simply stop existing for the next step."""
        world = self.world
        return [
            card
            for card in self.attackers
            if card in world.cards
            and world.zone_of(card).kind == ZONE_BATTLEFIELD
            and world.controller_of(card) == seat
        ]

    def _combat_damage(self, seat: Handle) -> int:
        """CR 702.7/702.8 first-strike / double-strike split. If anything
        ATTACKING OR BLOCKING has first or double strike there is a FIRST
        COMBAT DAMAGE STEP for the FS union DS carriers, then the settle's
        SBA sweep (a killer first strike buries its victim before the
        normal step), then the NORMAL step for the non-FS dealers plus the
        surviving DS carriers. 16c: the dealer set is BOTH SIDES of the
        attack (CR 510.1a — blockers assign to the attacker they blocked,
        in the same simultaneous step; the 16b attacker-only wave is
        superseded). Every damage atom is the 16a DEAL_DAMAGE funnel -
        the C24 replacement site intercepts (Nine Lives reads combat damage
        exactly like any other), marks ride the ledger, lethality is the
        settle's SBA. Each dealer's assignment obeys CR 510 (below) -
        blockers first up to lethal, TRAMPLE excess by asked partition,
        the Herald policy able to route it past blockers as though
        unblocked."""
        dealers = self._combat_dealers()

        def live(items: list[Handle]) -> list[Handle]:
            return [
                h
                for h in items
                if h in self.world.cards
                and self.world.zone_of(h).kind == ZONE_BATTLEFIELD
            ]

        first = {h for h in dealers if self.layers.keyword_of(h, Keyword.FIRST_STRIKE)}
        doubled = {
            h for h in dealers if self.layers.keyword_of(h, Keyword.DOUBLE_STRIKE)
        }
        fired = 0
        if first or doubled:
            fired += self._damage_wave(seat, sorted(first | doubled))
            dealers = live(dealers)  # a first-strike kill removes the dealer
        normal = [h for h in dealers if h not in first or h in doubled]
        fired += self._damage_wave(seat, sorted(normal))
        return fired

    def _combat_dealers(self) -> list[Handle]:
        """Everyone assigning combat damage: the live attackers plus every
        live blocker (a creature blocks exactly one attacker, CR 509.1b,
        so its recipient is determined; a multi-blocker pile contributes
        each blocker once)."""
        out = set(self.attackers)
        for blockers in self.blocked_by.values():
            out.update(blockers)
        return sorted(
            h
            for h in out
            if h in self.world.cards and self.world.zone_of(h).kind == ZONE_BATTLEFIELD
        )

    def _assign_damage(
        self, dealer: Handle, power: int, controller: Handle
    ) -> tuple[tuple[int, Handle], ...]:
        """CR 510.1 v1 (16c): one dealer's legal assignment announcement.

        * UNBLOCKED: everything to the ATTACKED object (v1: the defending
          player — planeswalker attacking is the documented players-only
          boundary, doc 14).
        * Herald policy (Garruk, Savage Herald's −7 grant, AS_UNBLOCKED):
          "you may have this creature assign its combat damage as though it
          weren't blocked" — an ASK (the "may"), site
          ``policy:<card>:<turn>``, vocabulary AS_BLOCKED/UNBLOCKED. The
          creature REMAINS blocked (the block triggers already fired and
          stand; CR 506.5a-style blocked status is untouched) — the policy
          only reroutes the ASSIGNMENT.
        * Multiple blockers: the ORDER is asked per attacker (site
          ``order:<card>:<turn>``) as a POSITIONAL pick from the Handle-
          sorted remaining candidates at each slot — the exact decision
          surface of the permutation index, with a ≤n-word vocabulary at
          every ask (a literal 6-permutation cap would raise inside live
          games at the 4th blocker: the gate demands zero crashes).
        * LETHAL per blocker is toughness-minus-marked (CR 704.2, the
          marked ledger keeps the first-strike step's scars) or 1 from a
          DEATHTOUCH dealer (CR 702.2b).
        * TRAMPLE (CR 702.9): once every blocker is covered lethal, the
          excess is asked RECIPIENT BY RECIPIENT in order — each blocker
          gets ``trample:<card>:<slot>:<turn>`` from 0..remaining, the
          defending player takes the rest (the composition space of the
          announcement, enumerated with ≤(excess+1)-word vocabularies).
        * Without trample the whole damage must hit the blockers: greedy
          lethal-first in order, the final survivor soaking any excess.
        """
        world = self.world
        defender = self.defending_player
        assert defender is not None  # combat_step opens the phase with one
        if dealer not in self.attackers:
            # 16c blocker-side dealer: a blocker assigns to the ONE attacker
            # it blocked (CR 510.1a). If that attacker has already left
            # combat (a first-strike kill), the blocker deals NOTHING -
            # there is no trample-style carryover for a blocker whose
            # prey is gone (CR 510.1, absent an attacking-object reading).
            blocked = next(
                (a for a, bs in self.blocked_by.items() if dealer in bs), None
            )
            if (
                blocked is None
                or blocked not in world.cards
                or world.zone_of(blocked).kind != ZONE_BATTLEFIELD
            ):
                return ()
            return ((power, blocked),)
        attacked = self.attacked.get(dealer, defender)
        blockers = [
            b
            for b in self.blocked_by.get(dealer, [])
            if b in world.cards and world.zone_of(b).kind == ZONE_BATTLEFIELD
        ]
        if not blockers:
            return ((power, attacked),)
        as_unblocked = (
            self.layers.policy_as_unblocked(dealer)
            or self.damage_policies.get(dealer) == "AS_UNBLOCKED"
        )
        if as_unblocked:
            ctx = self._ctx(
                source=dealer,
                controller=controller,
                bindings=None,
                decisions=(),
            )
            if (
                ctx.take_decision(
                    ("AS_BLOCKED", "UNBLOCKED"), f"policy:{dealer}:{world.turn}"
                )
                == "UNBLOCKED"
            ):
                return ((power, attacked),)
        ordered = list(blockers)
        if len(ordered) > 1:
            picked: list[Handle] = []
            remaining = sorted(ordered)
            for slot in range(len(ordered)):
                vocab = tuple(str(i) for i in range(len(remaining)))
                ctx = self._ctx(
                    source=dealer,
                    controller=controller,
                    bindings=None,
                    decisions=(),
                )
                answer = ctx.take_decision(vocab, f"order:{dealer}:{slot}:{world.turn}")
                chosen = remaining[int(answer)]
                picked.append(chosen)
                remaining.remove(chosen)
            ordered = picked
        deathtouch = self.layers.keyword_of(dealer, Keyword.DEATHTOUCH)

        def lethal_of(b: Handle) -> int:
            if deathtouch:
                return 1  # CR 702.2b: any nonzero damage from the source
            _p, toughness = self.ledger.effective_pt(world.cards[b].identity, b)
            return max(1, (toughness or 1) - self.damage.get(b, 0))

        if not self.layers.keyword_of(dealer, Keyword.TRAMPLE):
            plan: list[tuple[int, Handle]] = []
            left = power
            for b in ordered:
                share = min(lethal_of(b), left)
                if share:
                    plan.append((share, b))
                left -= share
                if left == 0:
                    break
            if left:  # no trample: the last blocker absorbs the excess
                plan[-1] = (plan[-1][0] + left, plan[-1][1])
            return tuple(plan)
        needs = [lethal_of(b) for b in ordered]
        covered = sum(needs)
        if power <= covered:  # not enough to reach lethal everywhere: greedy
            plan = []
            left = power
            for b, need in zip(ordered, needs):
                share = min(need, left)
                if share:
                    plan.append((share, b))
                left -= share
            return tuple(plan)
        plan = [(need, b) for b, need in zip(ordered, needs) if need]
        excess = power - covered
        for slot, b in enumerate(ordered):
            if excess == 0:
                break
            vocab = tuple(str(v) for v in range(excess + 1))
            ctx = self._ctx(
                source=dealer, controller=controller, bindings=None, decisions=()
            )
            give = int(
                ctx.take_decision(vocab, f"trample:{dealer}:{slot}:{world.turn}")
            )
            if give:
                # MERGE into the blocker's lethal entry (never a duplicate
                # recipient row - one announcement line per receiver)
                for i, (a, h) in enumerate(plan):
                    if h == b:
                        plan[i] = (a + give, b)
                        break
                else:
                    plan.append((give, b))
                excess -= give
        if excess:
            plan.append((excess, attacked))
        # CR 510.1: damage assignment is simultaneous within the step; the
        # canonical row order keeps the journal deterministic.
        return tuple(sorted(plan, key=lambda p: (p[1].namespace, p[1].index)))

    def _damage_wave(self, seat: Handle, dealers: list[Handle]) -> int:
        """One combat-damage substep: EVERY dealer's legal assignment is
        announced first (CR 510.1: all announcements, then all damage —
        nothing a later dealer's ask could read has mutated yet), then the
        atoms run inside ONE op boundary (simultaneous, CR 506/510 — no
        trigger can intervene between two attackers), each dealer's atoms
        journalled under ITS OWN cause (16a attribution fix), each damage-
        bearing dealer emits ONE COMBAT_DAMAGE row carrying the whole as-
        signment (CR 603.2: one "deals combat damage" event per dealer,
        however it splits), and the settle after the wave is the step's SBA
        + trigger drain. CR 120.7: a 0-power attacker deals no damage at
        all — no life change, no DAMAGE row, no CombatDamageEvent."""
        defender = self.defending_player
        assert defender is not None
        strikes: list[tuple[Handle, tuple[tuple[int, Handle], ...]]] = []
        for dealer in dealers:
            identity = self.world.cards[dealer].identity
            power, _toughness = self.ledger.effective_pt(identity, dealer)
            if not power:
                # 0 (or an unmaterialized *): CR 120.7 - not dealt at all.
                continue
            plan = self._assign_damage(dealer, power, self.world.controller_of(dealer))
            if not plan:
                # 16c: a blocker whose attacker left combat deals nothing -
                # no damage, no COMBAT_DAMAGE event (CR 120.7's reading).
                continue
            strikes.append((dealer, plan))
        if not strikes:
            return 0
        self._op_seq += 1
        self._combat_wave_open = True
        try:
            for dealer, plan in strikes:
                for amount, recipient in plan:
                    ctx = self._ctx(
                        source=dealer,
                        controller=self.world.controller_of(dealer),
                        bindings={"target": recipient},
                        decisions=(),
                    )
                    self._run_effect(_combat_damage_atom(amount, recipient), ctx)
        finally:
            self._combat_wave_open = False
        for dealer, plan in strikes:
            self.journal.emit(
                KIND_COMBAT_DAMAGE,
                dealer,
                dealer,
                "COMBAT_DAMAGE",
                (plan,),
            )
        return self._settle()

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
        self.damage_deathtouch.clear()  # 16c: the deathtouch flag rides along
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
        # 16c: the deathtouch flag rides the same fold (CR 702.2b kills).
        h.update(repr(sorted(map(str, self.damage_deathtouch))).encode())
        # 16b: the attack record + the dispatched mandate ledger are
        # replayed state under the same ruling — a replay that attacked
        # with a different set, or lost an "attacks if able" rule, MUST
        # differ here.
        h.update(
            repr(
                (
                    tuple(str(a) for a in self.attackers),
                    tuple(sorted((str(k), str(v)) for k, v in self.attacked.items())),
                    str(self.defending_player),
                    self.declaring,
                    self._declare_group,
                    tuple(sorted(map(str, self.mandates))),
                    # 16c: the block record, the must-block ledger and the
                    # dispatched damage-assignment policies are the same
                    # kind of replayed combat state.
                    tuple(
                        sorted(
                            (str(k), tuple(str(b) for b in bs))
                            for k, bs in self.blocked_by.items()
                        )
                    ),
                    tuple(sorted(map(str, self.mandate_block))),
                    tuple(sorted((str(k), v) for k, v in self.damage_policies.items())),
                )
            ).encode()
        )
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
