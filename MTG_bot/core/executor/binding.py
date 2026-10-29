"""Compiled-ability attachment + trigger binding/fire (round 12b, /06 §12b).

Builds on 12a's Executor: compiled ability IR (a ``CardRecord`` from
``compile_pool`` / a ``CompileResult``) attaches to world Handles; every
world event the :class:`~MTG_bot.core.executor.events.EventJournal` derives
is matched against the attached :class:`TriggeredAbility` nodes; a match
queues a canonical :class:`~MTG_bot.core.state.TriggerInstance` through
``world.queue_trigger`` (APNAP ordering lives in the world's ``order_key``),
and the binder drains the queue — condition -> may-offer -> effect through
the 12a effect runner, whose mutations are journalled and matched in turn —
firing until the queue empties.

Contracts honoured:

  * **attachment lifecycle** — triggers live while the permanent is on the
    battlefield: leaving detaches, re-entering re-registers. The compiled
    record stays registered by oracle id: the bridge from the game card's
    :class:`~MTG_bot.core.identity.CardIdentity` to its compiled IR;
  * **APNAP then Handle-sorted** — the drain order is
    ``(controller_seat, clock, str(source), bind_seq)``: the world's
    order_key first (active player's triggers resolve first), a Handle
    tie-break within a seat, so one scripted game replays byte-identically;
  * **C18** — a dies firing binds ``event``/``result`` to the dead subject,
    whose was-snapshot the journal carried; the event register makes 12a's
    ``event``/``result`` QProp referents real;
  * **C22** — ``DelayedTrigger`` effect nodes schedule into the same
    matcher with a duration tag; the end-of-turn sweep expires the
    turn-window entries;
  * **tripwire** — one drain resolves at most ``MAX_TRIGGER_FIRES``
    trigger instances; beyond that the guard QUARANTINES its runaway
    source (dropped firings recorded in ``executor.trigger_loops``) and
    the drain continues — the loop is a bug to flag, never a bug to run;
  * **flag, don't degrade** — combat/cast/step/targeting event nodes have
    no emitter before the later phases: *binding* one RAISES
    ``NotImplementedError`` naming the owning phase, instead of silently
    arming a trigger that could never fire. Unsupported damage scopes
    (source filter, combat damage) raise at bind time too.

May-offers: an ``OptionalEffect`` in a trigger effect answers through the
executor's vocabulary-addressed decision stream (14b, B-4 ruling): the ask
carries its own (vocab, what) key, so firings the drain itself arms are
answerable — pinned deterministic by the replay test.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from MTG_bot.core.ability_tree import (
    AbilityTriggerEvent,
    Atom,
    AtomArgs,
    BecomesBlockedEvent,
    CardDrawnEvent,
    CardRecord,
    CastSpellEvent,
    Choose,
    Conditional,
    ControllerRef,
    CounterKind,
    CounterPlacedEvent,
    CreatureDiesEvent,
    DamageDealtEvent,
    DeclareAttackersEvent,
    DeclareBlockersEvent,
    DelayedTrigger,
    DurationEot,
    EachPlayer,
    EventSpec,
    FAnd,
    FAtom,
    FAtomPred,
    Filter,
    FNot,
    FOr,
    Keyword,
    LifeGainedEvent,
    LoyaltyActivatedEvent,
    OptionalEffect,
    PtDelta,
    PtDirection,
    QAtMost,
    QConst,
    Repeat,
    SacrificeEvent,
    Selector,
    SelectorMode,
    Seq,
    StepEvent,
    TapStateEvent,
    TargetingEvent,
    TriggeredAbility,
    TurnPhaseEvent,
    Verb,
    Zone,
    ZoneChangeEvent,
    ZoneKind,
    count_semantics,
    walk,
)
from MTG_bot.core.compiler.compiler import PoolCompile
from MTG_bot.core.executor.decisions import site_digest
from MTG_bot.core.executor.durations_min import duration_tag
from MTG_bot.core.executor.events import (
    KIND_ABILITY_TRIGGERED,
    KIND_CARD_DRAWN,
    KIND_CAST,
    KIND_COMBAT_DAMAGE,  # noqa: F401 — journal feed only since the R2 fold (/140): emitted, never subscribed
    KIND_COUNTER_PLACED,
    KIND_CREATURE_DIES,
    KIND_DAMAGE,
    KIND_DECLARE_ATTACKERS,
    KIND_DECLARE_BLOCKERS,
    KIND_LIFE_GAINED,
    KIND_LOYALTY_ACTIVATED,
    KIND_TAP_STATE,
    KIND_TARGETING,
    KIND_TURN_PHASE,
    KIND_ZONE_CHANGE,
    GameEvent,
)
from MTG_bot.core.executor.quantity import ExecCtx, eval_filter, resolve
from MTG_bot.core.executor.selectors import (
    ZONE_KIND_TO_STATE,
    controller_matches,
    filter_reads_bound_player,
    players_for_ref,
)
from MTG_bot.core.identity import Handle
from MTG_bot.core.state import ZONE_BATTLEFIELD, ZONE_GRAVEYARD, GameWorld

if TYPE_CHECKING:  # pragma: no cover - typing only, dodges the import cycle
    from MTG_bot.core.executor import Executor

# Infinite-loop tripwire: one drain resolves at most this many trigger
# instances (nested chains included). Exceeding it raises — we never spin.
MAX_TRIGGER_FIRES = 200

# EventSpec kinds with no emitter before the combat/target phases.
# Binding one RAISES — flag, don't degrade. 13b: CastSpellEvent LEFT this
# table — the spell stack ships the CAST feed (journal.emit_cast at
# 601.2h) and :meth:`TriggerBinder._match_cast` subscribes the node
# (controller / ordinal / from_zone / from_zone_not / filter — the full
# corpus surface, seven cards, tested in test_executor_stack.py).
# 16b: DeclareAttackersEvent and CombatDamageEvent LEFT this table — the
# COMBAT skeleton ships both feeds (journal DECLARE_ATTACKERS rows per
# declared attacker, group-deduped per ability; COMBAT_DAMAGE rows per
# dealing creature) and :meth:`TriggerBinder._match_node` subscribes them.
# R2 (2026-10-20, /140): CombatDamageEvent FOLDED into DamageDealtEvent —
# the COMBAT_DAMAGE journal rows still emit (audit feed, BREAK-2) but no
# trigger lane subscribes them any more: folded combat triggers bind the
# DAMAGE rows through _match_damage (is_combat distinguishes them).
# 16c: DeclareBlockersEvent and BecomesBlockedEvent LEFT this table too —
# the blocker step ships the feed (journal DECLARE_BLOCKERS rows, one per
# declaration PAIR: subject = the blocker, data = (attacker, group)) and
# :meth:`TriggerBinder._match_node` subscribes both node kinds.
# r20b (Warden of the Woods): TargetingEvent LEFT too — the three
# designation lanes (spell 601.2c plan, activation 602.2b, the 18b trigger
# channel) ship the journal TARGETING feed and ``_match_node`` subscribes
# the node (filter over the designated object, the grammar's only slot).
# r22c (Keral Keep Disciples): LoyaltyActivatedEvent LEFT too — the
# activation lane ships the journal LOYALTY_ACTIVATED feed (emitted at
# the loyalty-payment point of legality.activate, CR 606.2b's symbol) and
# ``_match_node`` subscribes the node (controller scope over the
# activating player, filter over the permanent — the grammar's two slots).
_UNSUPPORTED_EVENTS: dict[type, str] = {
    StepEvent: (
        "12e (step-level subscription emitter; 12d's untap tick is an "
        "executor step that emits TapState/phase events, not StepEvents)"
    ),
}

# Delayed-trigger window tags the end-of-turn sweep expires. ``UntilNextTurn``
# piggybacks on the Eot sweep as a documented stand-in; the precise
# next-turn-start expiry of the 12d Duration vocab applies to the LEDGER /
# layer / prevention records — a DELAYED trigger keeps the turn-window
# stand-in (delayed windows beyond the turn are 12e).
_SWEEP_TAGS = ("Eot", "UntilNextTurn")

# Any trigger node: attached TriggeredAbility or scheduled DelayedTrigger —
# both carry ``condition`` + ``effect`` (C22 convention).
_AnyTrigger = TriggeredAbility | DelayedTrigger


def _required_target_keys(effect: object) -> frozenset[str]:
    """B-55, CR 603.3d: the TARGET slots an ability must fill to be put on
    the stack at all, keyed like :meth:`TriggerBinder._designate`'s
    collector (``repr`` of a referent-free TARGET-mode Selector).

    Every printed "target" outside a mode choice is required, whatever
    wraps it: "you may", "if you do", a repeat or a per-player loop are all
    resolution-time, and targets are announced before any of them (CR
    601.2c, which 603.3d applies to triggers). A slot inside a ``Choose``
    is mode-dependent (CR 700.2a): required only when EVERY option carries
    it (Tolarian Kraken's "tap or untap target permanent"), since otherwise
    a mode without it stays choosable. A nested ``DelayedTrigger`` chooses
    its own targets when it triggers (CR 603.7c), so it adds nothing."""
    if isinstance(effect, Atom):
        return frozenset(
            repr(value)
            for _role, value in effect.args.pairs
            if isinstance(value, Selector)
            and value.mode is SelectorMode.TARGET
            and value.referent is None
        )
    if isinstance(effect, Choose):
        return frozenset.intersection(
            *(_required_target_keys(option) for option in effect.options)
        )
    if isinstance(effect, Seq):
        return frozenset().union(*(_required_target_keys(s) for s in effect.steps))
    if isinstance(effect, Conditional):
        keys = _required_target_keys(effect.then_effect)
        if effect.else_effect is not None:
            keys |= _required_target_keys(effect.else_effect)
        return keys
    if isinstance(effect, (OptionalEffect, Repeat)):
        return _required_target_keys(effect.inner)
    if isinstance(effect, EachPlayer):
        return _required_target_keys(effect.effect)
    return frozenset()  # DelayedTrigger (CR 603.7c)


def _is_universal(filter_: Filter) -> bool:
    """The grammar's universal filter: an empty conjunction (``FAnd(())``)."""
    return isinstance(filter_, FAnd) and len(filter_.children) == 0


def _is_subject_identity(filter_: Filter) -> bool:
    """16a (Brash Taunter): the bare IS_SOURCE identity pred alone. It is
    DEFINED for any handle (handle == ctx.source, no card data read), and a
    PLAYER subject can never be a card ability's source — so over a player
    damage subject it is honestly FALSE, not undefined (the echo's own
    player-damage row must not re-arm the "is dealt damage" trigger). The
    raise stays for every other filter: its preds read card data a player
    handle does not carry."""
    return isinstance(filter_, FAtom) and filter_.pred is FAtomPred.IS_SOURCE


# r20b (Hooded Blightfang): the preds whose answer over a PLAYER subject
# is decidable without reading any card data — a player IS none of these
# things, so each honest answer is FALSE (and TRUE under FNot). The rest
# of the vocab genuinely reads card data a player handle does not carry,
# and keeps the 12c raise: flag, never guess.
_PLAYER_SHAPE_PREDS = frozenset(
    {
        FAtomPred.TYPE_EQ,
        FAtomPred.SUBTYPE_EQ,
        FAtomPred.SUPERTYPE_EQ,
        FAtomPred.NAME_EQ,
        FAtomPred.NAME_CONTAINS,
        FAtomPred.KEYWORD_HAS,
        FAtomPred.IS_TOKEN,
        FAtomPred.IS_PERMANENT,
    }
)


def _player_subject_verdict(filter_: Filter, subject: Handle, ctx: ExecCtx) -> bool:
    """16a (Brash)'s identity reading, widened r20b: the boolean-algebra
    closure over the decidable player-subject preds. A player subject can
    never BE a card-shape thing, so those atoms answer FALSE outright; a
    player's CONTROLLER_IS is honestly the player itself. The nodes
    compose. Any pred outside the decidable set keeps the original 12c
    raise verbatim."""
    if isinstance(filter_, FAnd):
        return all(_player_subject_verdict(c, subject, ctx) for c in filter_.children)
    if isinstance(filter_, FOr):
        return any(_player_subject_verdict(c, subject, ctx) for c in filter_.children)
    if isinstance(filter_, FNot):
        return not _player_subject_verdict(filter_.inner, subject, ctx)
    if isinstance(filter_, FAtom):
        if filter_.pred in _PLAYER_SHAPE_PREDS and filter_.who is None:
            return False
        if filter_.pred is FAtomPred.CONTROLLER_IS and filter_.who is not None:
            # a player is its own controller (CR 109.5's player half)
            return controller_matches(filter_.who, subject, ctx)
        if filter_.pred is FAtomPred.OPPONENT_OF:
            # r25 (grammar round 11, R11-1): the destination identity pred
            # is decidable over a player subject by definition — the atom
            # is player-total (its _eval_atom branch reads only seats and
            # bindings, never card data), so the shared oracle answers
            # here too instead of the 12c raise.
            return eval_filter(filter_, subject, ctx)
    raise NotImplementedError(
        "executor: DamageDealtEvent filter over a player subject is 12c's query surface"
    )


def _compile_bridge(compiled: object) -> CardRecord:
    """The oracle-id bridge: a CardRecord, a CompileResult, or anything
    carrying ``.card`` — never a guess."""
    record = getattr(compiled, "card", compiled)
    if not isinstance(record, CardRecord):
        raise ValueError(  # noqa: TRY004 - ValueError type guards are the 12a house convention
            "attach_card: need a CardRecord/CompileResult, got "
            f"{type(compiled).__name__}"
        )
    return record


@dataclass
class _Firing:
    """One queued trigger instance's execution payload, keyed by the
    instance's (tick-unique) clock."""

    source: Handle
    controller: Handle
    node: _AnyTrigger
    event: GameEvent
    seq: int


@dataclass
class DelayedBinding:
    """A C22 DelayedTrigger scheduled into the 12b journal matcher."""

    seq: int
    tag: str
    node: DelayedTrigger
    source: Handle
    controller: Handle


class TriggerBinder:
    """The (handle, ability-idx) trigger registry + event matcher + APNAP
    fire loop. Owned by one :class:`~MTG_bot.core.executor.Executor`."""

    def __init__(self, executor: Executor) -> None:
        self.executor = executor
        self.records: dict[str, CardRecord] = {}
        self.attached: dict[tuple[Handle, int], TriggeredAbility] = {}
        self.handle_record: dict[Handle, CardRecord] = {}
        # 13c: emblem synthetic handles -> their OWNER. Emblems are not
        # world cards, so ``world.controller_of`` cannot answer "who is
        # this trigger's you?" — this side-table does, and every trigger
        # match path consults it through :meth:`_controller_of`.
        self.emblem_owner: dict[Handle, Handle] = {}
        self.firings: dict[int, _Firing] = {}
        # r23a (tripwire guard, Chandra's Incinerator seeds 17/50): sources
        # whose trigger self-retriggers the drain are QUARANTINED by
        # fire_all; _queue then drops their firings for the rest of the
        # game — "flag it, never run it". This is replayed state: the
        # executor folds it into state_fingerprint through this object.
        self.quarantined: set[Handle] = set()
        self.delayed: list[DelayedBinding] = []
        self._seen_journal_len = 0
        self._seq = 0
        # 16b CR 603.2 dedup: (source, node-id, declare-group) for every
        # DeclareAttackersEvent queue already made. The journal carries ONE
        # row per declared attacker (the grammar's filter is subject-
        # scoped), but a triggered ability triggers ONCE on the whole
        # declare action — the shared group id collapses the row fan-out.
        self._declare_queued: set[tuple[Handle, int, int]] = set()
        # r20a (wave-3): cached synthetic keyword-trigger nodes, keyed
        # (family, holder). ONE node object per (family, handle) keeps the
        # CR 603.2 declare-dedup (which keys on id(node)) stable across the
        # rows of one declaration, and dies with the handle's detach.
        self._kw_nodes: dict[tuple[str, Handle], TriggeredAbility] = {}
        # r22a (the self-dies law, /21 wave5a findings): a battlefield
        # departure normally detaches the leaver's triggers on the
        # ZONE_CHANGE journal row — but events.py:record_atom journals the
        # card's CREATURE_DIES row IMMEDIATELY after that row (same diff
        # iteration), and the dying permanent's own "when this dies"
        # trigger must still be attached when the dies row is matched. A
        # ZONE_CHANGE(bf→non-bf) whose very next journalled row is that
        # card's CREATURE_DIES parks its handle here; :meth:`_lifecycle`
        # runs the deferred detach at the dies row, after the match pass
        # queued the firing. Non-death departures (bounce/exile/hand) have
        # no dies row and detach on the spot, exactly as before.
        self._pending_dies_detach: set[Handle] = set()

    # ------------------------------------------------------------ attach

    @property
    def world(self) -> GameWorld:
        return self.executor.world

    def _controller_of(self, handle: Handle) -> Handle:
        """The trigger controller: the world's battlefield controller, or
        for an emblem's synthetic handle (never a world card — 13c) the
        recorded OWNER. The emblem's "you" is its owner for every event
        match (CR 113.7 the emblem is controlled by its owner)."""
        owner = self.emblem_owner.get(handle)
        if owner is not None:
            return owner
        # 16e: triggers ride the CURRENT controller (CR 603.7b).
        return self.executor.controller_of(handle)

    def bind_emblem(self, handle: Handle, record: CardRecord, owner: Handle) -> int:
        """13c: bind a granted emblem's ability nodes. The emblem record is
        a token-shaped CardRecord (the compiler normalises emblem→token):
        TriggeredAbility nodes bind at (handle, idx) with the OWNER as
        controller (via :meth:`_controller_of`), StaticAbility nodes attach
        to the layer registry ANCHORED TO THE OWNER (Liliana's emblem
        grants haste to "creatures you control" — its ``you`` is the
        owner), and the synthetic handle never touches world zones, the
        loyalty seed, or the castable-card surfaces (:func:
        `legality.legal_activations` iterates world cards, so it can never
        see this handle)."""
        triggers = []
        for idx, ability in enumerate(record.abilities):
            if isinstance(ability, TriggeredAbility):
                self._check_event(ability.event, record.name)
                triggers.append((idx, ability))
        self.detach(handle, leaving=False)
        self.records.setdefault(record.oracle_id, record)
        self.handle_record[handle] = record
        self.emblem_owner[handle] = owner
        for idx, ability in triggers:
            self.attached[(handle, idx)] = ability
        # 16c: same attach order as _register (replacements first - its
        # idempotence sweep must not expire the layers' static prevents).
        self.executor.replacements.attach_source(handle, record)
        self.executor.layers.attach_source(handle, record, controller=owner)
        return len(triggers)

    def register_token(self, handle: Handle, record: CardRecord) -> None:
        """16c (the token half of the /13 binder gap): file the token's
        synthesized record under its synthetic oracle id and attach it to
        the HANDLE, so the battlefield ZONE_CHANGE row's lifecycle regis-
        tration (the SAME :meth:`_lifecycle` path a printed permanent uses)
        finds a record and binds the token's rule lines — the Pursued
        Whale Pirate's "can't block" prevention and the mandate layer its
        "creatures you control attack if able" static becomes, anchored to
        the token's CONTROLLER. Pure registration: the world card already
        exists (CREATE_TOKEN put it there); no zones, no loyalty seed."""
        if handle not in self.world.cards:
            raise ValueError(f"register_token: unknown world card {handle}")
        for ability in record.abilities:
            if isinstance(ability, TriggeredAbility):
                self._check_event(ability.event, record.name)
        self.records.setdefault(record.oracle_id, record)
        self.handle_record[handle] = record

    def attach_card(self, handle: Handle, compiled: object) -> int:
        """Register the compiled record for the world card ``handle`` and
        bind its TriggeredAbility nodes. The game card's identity oracle id
        must match the compiled record — the bridge is CHECKED, never
        assumed. A handle already carrying a DIFFERENT record raises: one
        permanent, one compiled record (re-attaching the same record is an
        idempotent refresh)."""
        if handle not in self.world.cards:
            raise ValueError(f"attach_card: unknown world card {handle}")
        record = _compile_bridge(compiled)
        identity = self.world.cards[handle].identity
        if identity.oracle_id != record.oracle_id:
            raise ValueError(
                f"attach_card: card {handle} is {identity.oracle_id!r} but the "
                f"compiled record is {record.oracle_id!r} — identity bridge mismatch"
            )
        existing = self.handle_record.get(handle)
        if existing is not None and existing.oracle_id != record.oracle_id:
            raise ValueError(
                f"attach_card: {handle} already carries {existing.name!r}; "
                "detach before swapping a permanent's compiled record"
            )
        # Check-then-commit: every event kind validates BEFORE any binding
        # mutates, so a raise leaves the registry untouched.
        for ability in record.abilities:
            if isinstance(ability, TriggeredAbility):
                self._check_event(ability.event, record.name)
        self.records[record.oracle_id] = record
        self.handle_record[handle] = record
        return self._register(handle, record)

    def attach_pool(self, pool: PoolCompile) -> int:
        """Register every compiled card of a mini pool by oracle id, then
        attach every card already on the battlefield (cards entering later
        re-register automatically from the registry)."""
        for result in pool.results.values():
            self.records[result.card.oracle_id] = result.card
        count = 0
        for card in sorted(self.world.cards, key=lambda h: h.index):
            identity = self.world.cards[card].identity
            record = self.records.get(identity.oracle_id)
            if record is None:
                continue
            self.handle_record[card] = record
            if self.world.zone_of(card).kind == ZONE_BATTLEFIELD:
                count += self._register(card, record)
        return count

    def _register(self, handle: Handle, record: CardRecord) -> int:
        """Bind the record's TriggeredAbility nodes at (handle, idx), and
        12d: register the record's CONTINUOUS half (KeywordAbility +
        StaticAbility nodes → the layer registry; ReplacementAbility nodes
        → the replacement registry) — one battlefield lifecycle for every
        ability shape. Check-then-commit: an unsupported event kind raises
        BEFORE the old bindings are dropped (flag, never degrade into a
        silent unlink)."""
        triggers = []
        for idx, ability in enumerate(record.abilities):
            if isinstance(ability, TriggeredAbility):
                self._check_event(ability.event, record.name)
                triggers.append((idx, ability))
        self.detach(handle, leaving=False)
        for idx, ability in triggers:
            self.attached[(handle, idx)] = ability
        # 13a loyalty ledger: the frozen CardState has no loyalty field, so
        # the printed CardIdentity.loyalty is seeded into the counters map
        # (CounterKind.LOYALTY) at battlefield registration — the one path
        # covering BOTH first attach and re-entry (the lifecycle re-registers
        # through here). setdefault, so a mid-turn re-attach never overwrites
        # a loyalty the game already changed.
        state = self.executor.world.cards.get(handle)
        if state is not None and state.identity.loyalty is not None:
            try:
                printed = int(state.identity.loyalty)
            except ValueError:  # pragma: no cover - printed loyalty is numeric
                printed = 0
            if printed:
                state.counters.setdefault(CounterKind.LOYALTY.name, printed)
        # 16c ORDER MATTERS: replacements.attach_source opens with its own
        # detach_source sweep (its idempotence rule), which would expire
        # the PreventionRecords that layers.attach_source registers for a
        # static PREVENT_EFFECT carrier (the Pursued Whale token's "can't
        # block"). Attach replacements FIRST, layers LAST, so the static
        # preventions are the final word for a freshly attached permanent.
        self.executor.replacements.attach_source(handle, record)
        self.executor.layers.attach_source(handle, record)
        return len(triggers)

    def detach(self, handle: Handle, *, leaving: bool = True) -> int:
        """Battlefield departure: drop the handle's live bindings (the
        oracle-id record stays, ready for the re-entry re-registration) —
        and 12d: its continuous layers and replacement records expire with
        it (their durations govern separately for records the permanent
        GRANTED elsewhere).

        16e: ``leaving=False`` is the ATTACH-side idempotent refresh
        (attach_card/_register clear-then-rebind a handle that is
        ARRIVING, not departing). For a trigger-less permanent — an aura
        with only a StaticAbility — that refresh runs from _lifecycle AFTER
        the cast already attached its aura edge, and the 13c departure
        sweep below would erase it, feeding the CR 704.5q SBA a false
        unattached read. The attachment drop belongs to DEPARTURES only."""
        keys = [key for key in self.attached if key[0] == handle]
        for key in keys:
            del self.attached[key]
        if not leaving:
            self.executor.layers.detach_source(handle)
            self.executor.replacements.detach_source(handle)
            return len(keys)
        # 13c: attachment is battlefield-to-battlefield (CR 303.4c/117.12 —
        # when either side of an aura/equipment pair leaves, the attachment
        # relationship ends). The executor's attachment table drops every
        # edge touching the departing handle. (Emblems never detach: an
        # emblem cannot leave the battlefield/ownership in the rules — no
        # code path calls detach on an emblem handle.)
        ex = self.executor
        # r20c (Malefic Scythe): LKI capture BEFORE the prune — the edges
        # this sweep kills are the departing host's attachment truth for
        # the CREATURE_DIES row that follows the ZONE_CHANGE row in the
        # same journal batch (see Executor.detach_lki).
        ex.detach_lki[handle] = tuple(
            sorted(a for a, host in ex.attachments.items() if host == handle)
        )
        ex.attachments = {
            aura: host
            for aura, host in ex.attachments.items()
            if aura != handle and host != handle
        }
        self.executor.layers.detach_source(handle)
        self.executor.replacements.detach_source(handle)
        return len(keys)

    def _check_event(self, event: EventSpec, card_name: str) -> None:
        kind = type(event)
        if kind in _UNSUPPORTED_EVENTS:
            raise NotImplementedError(
                f"executor: {card_name} trigger event {kind.__name__} is "
                f"{_UNSUPPORTED_EVENTS[kind]}"
            )
        if isinstance(event, DamageDealtEvent):
            # 16c: the source filter and the combat scope are CONSUMED at
            # match time (the DAMAGE row's dealer/cause and the combat
            # flag), so a scoped node like Garruk's Harbinger's or Subira's
            # delayed tail binds clean — the pre-16c bind-time raise is
            # retired with its consumers.
            return

    # ------------------------------------------------------------ matching

    def on_events(self) -> None:
        """Match every not-yet-seen journalled event against the attached
        triggers and the scheduled delayed triggers, queueing one
        TriggerInstance per match. The attach/detach lifecycle rides the
        same pass in journal order: a permanent ENTERING re-registers
        before matching (its own ETB trigger is live — IS_SOURCE sees it),
        a permanent LEAVING detaches only after matching (its own dies
        trigger still fires)."""
        events = self.executor.journal.events
        while self._seen_journal_len < len(events):
            event = events[self._seen_journal_len]
            self._seen_journal_len += 1
            self._lifecycle(event, attach=True)
            for (handle, _idx), ability in sorted(
                self.attached.items(), key=lambda kv: (str(kv[0][0]), kv[0][1])
            ):
                if self._match_node(
                    ability.event, event, handle, self._controller_of(handle)
                ):
                    self._queue(handle, self._controller_of(handle), ability, event)
            # r20a (wave-3): GRANTED triggers. A StaticAbility GRANT_ABILITY
            # layer parks its TriggeredAbility row in the layer registry —
            # the ``attached`` map above only walks the card's PRINTED rows,
            # so Light of Promise's granted life trigger and Infernal
            # Scarring's granted dies-draw were compile-but-never-drain.
            # No battlefield gate, mirroring the attached loop's lifecycle:
            # the dies row must still see the grant while the aura is on.
            # Determinism: Handle order, then the registry's layer-seq order.
            layers = self.executor.layers
            for host in sorted(self.world.cards):
                ctrl = self._controller_of(host)
                for granted in layers.granted_abilities(host):
                    node = granted.node
                    if isinstance(node, TriggeredAbility) and self._match_node(
                        node.event, event, host, ctrl
                    ):
                        self._queue(host, ctrl, node, event)
            # r20a: KEYWORD triggers (PROWESS / BATTALION). The compiler
            # folds printed keywords into CardRecord.keywords with NO
            # ability row (Blood Glutton compiles with an EMPTY abilities
            # tuple), so the engine constructs the canonical node itself —
            # EPHEMERAL IR construction: the frozen serialised IR and the
            # goldens on disk are untouched. Order: family, then the
            # registry's Handle-sorted holder list.
            for family in ("PROWESS", "BATTALION"):
                for host in layers.holders(Keyword[family]):
                    if (
                        host not in self.world.cards
                        or self.world.zone_of(host).kind != ZONE_BATTLEFIELD
                    ):
                        continue
                    node = self._keyword_node(family, host)
                    ctrl = self._controller_of(host)
                    if not self._match_node(node.event, event, host, ctrl):
                        continue
                    if family == "BATTALION" and self._group_size(event) < 3:
                        continue  # CR 508.2: a group of at least three
                    self._queue(host, ctrl, node, event)
            for entry in list(self.delayed):
                if self._match_node(
                    entry.node.event, event, entry.source, entry.controller
                ):
                    self._queue(
                        entry.source, entry.controller, entry.node, event, delayed=True
                    )
            self._lifecycle(event, attach=False)
        # r22a defensive flush: record_atom always journalled the pair, so
        # a pending handle should never outlive the pass. If a hand-built
        # journal row (a test, or a future verb) ever splits the ZC/CD
        # twins across drains, the invariant "a departed permanent is
        # detached by the end of the pass" still holds.
        for handle in sorted(self._pending_dies_detach):
            self.detach(handle)
        self._pending_dies_detach.clear()

    def _lifecycle(self, event: GameEvent, attach: bool) -> None:
        if event.kind == KIND_CREATURE_DIES and not attach:
            # r22a: the dies row was MATCHED above with the leaver still
            # attached (the ZONE_CHANGE row deferred its detach here), so
            # the dead card's own "when this dies" trigger queued its
            # firing. The departure now runs — still BEFORE any
            # resolution: firings drain in a later settle round, and
            # detach_lki is read at RESOLUTION time (quantity.py), so
            # the r20c LKI lane is untouched by the deferral.
            handle = event.subject
            if handle is not None and handle in self._pending_dies_detach:
                self._pending_dies_detach.discard(handle)
                self.detach(handle)
            return
        if event.kind != KIND_ZONE_CHANGE or event.subject is None:
            return
        from_state, to_state = event.data[0], event.data[1]
        handle = event.subject
        if attach:
            if to_state == ZONE_BATTLEFIELD:
                record = self.handle_record.get(handle)
                if record is not None and not any(
                    key[0] == handle for key in self.attached
                ):
                    self._register(handle, record)
        elif from_state == ZONE_BATTLEFIELD and to_state != ZONE_BATTLEFIELD:
            # r22a: record_atom journalled this card's CREATURE_DIES row
            # immediately after this row (same diff iteration) — defer the
            # detach to it so the IS_SOURCE dies trigger is still attached
            # when its own event is matched. Any other departure (bounce,
            # exile, hand, or a graveyard move with no dies twin) detaches
            # on the spot, exactly as before.
            events = self.executor.journal.events
            nxt = (
                events[self._seen_journal_len]
                if self._seen_journal_len < len(events)
                else None
            )
            if (
                nxt is not None
                and nxt.kind == KIND_CREATURE_DIES
                and nxt.subject == handle
            ):
                self._pending_dies_detach.add(handle)
            else:
                self.detach(handle)

    def _queue(
        self,
        source: Handle,
        controller: Handle,
        node: _AnyTrigger,
        event: GameEvent,
        additional: bool = False,
        delayed: bool = False,
    ) -> None:
        if source in self.quarantined:
            # r23a tripwire guard: a flagged loop source never queues
            # again this game (its firing was already recorded loudly in
            # executor.trigger_loops).
            return
        if not delayed and source in self.executor.phased_out:
            # CR 702.26b: a phased-out permanent's triggered abilities (its
            # printed, granted and keyword ones, and the AbilityTriggerEvent
            # subscribers) do not trigger. A delayed trigger is not an
            # ability of its source (CR 603.7) and still triggers.
            return
        if (
            not additional
            and event.kind == KIND_DECLARE_ATTACKERS
            and isinstance(node.event, DeclareAttackersEvent)
        ):
            # CR 603.2 once-per-declaration (16b): the per-attacker row
            # fan-out must queue ONE instance per ability per declare
            # group — Tide Skimmer's "attack with two or more" fires once,
            # a per-creature IS_SOURCE filter still fires once (its own
            # row), and two identical creatures are different sources.
            key = (source, id(node), event.declare_group)
            if key in self._declare_queued:
                return
            self._declare_queued.add(key)
        self._seq += 1
        instance = self.world.queue_trigger(
            source, controller, f"{event.kind}#{self._seq}"
        )
        payload = _Firing(
            source=source, controller=controller, node=node, event=event, seq=self._seq
        )
        self.firings[instance.clock] = payload
        if not additional:
            # T5-D (Sanctum of All "whenever another Shrine you control's
            # ability triggers"): an ordinary queued firing feeds every
            # AbilityTriggerEvent subscriber in a SYNTHETIC match pass --
            # no journal row is written (fingerprints byte-stable), and
            # `additional` firings (CR 603.2e: an extra trigger has no
            # triggering event) never feed it again, which is what keeps
            # two extra-trigger carriers from chasing each other.
            self._fan_ability_triggers(payload)

    def _fan_ability_triggers(self, payload: _Firing) -> None:
        """T5-D: queue one firing per AbilityTriggerEvent subscriber whose
        filter matches the triggering ability's SOURCE permanent, in the
        subscriber's coordinates (IS_SOURCE = the subscriber, so "another"
        is the filter's own FNot(IS_SOURCE)). The synthetic event carries
        the matched payload so the TRIGGER_ADDITIONAL verb can re-queue
        it; the subscriber's condition (Sanctum's "six or more Shrines")
        gates at _fire time like any other trigger. CR 603.2e: an
        extra-trigger carrier's OWN firings never fan out — the family's
        effect does not apply to instances of itself, which is what keeps
        two carriers from chasing each other (each adds its one extra per
        ORIGINAL firing; the extras carry no triggering event)."""
        effect = getattr(payload.node, "effect", None)
        if isinstance(effect, Atom) and effect.verb is Verb.TRIGGER_ADDITIONAL:
            return
        subscribers = [
            (handle, ability)
            for (handle, _idx), ability in sorted(
                self.attached.items(), key=lambda kv: (str(kv[0][0]), kv[0][1])
            )
            if isinstance(ability.event, AbilityTriggerEvent)
            and handle != payload.source
        ]
        for handle, ability in subscribers:
            ctrl = self._controller_of(handle)
            synth = GameEvent(
                clock=-1,
                kind=KIND_ABILITY_TRIGGERED,
                subject=payload.source,
                cause=handle,
                cause_verb="TRIGGER",
                data=(payload,),
            )
            ctx = self._match_ctx(handle, ctrl, synth)
            if eval_filter(ability.event.filter, payload.source, ctx):
                self._queue(handle, ctrl, ability, synth)

    def _keyword_node(self, family: str, handle: Handle) -> TriggeredAbility:
        """r20a: the canonical compiled-shape node for a printed keyword
        trigger, built ONCE per (family, holder) and cached — the cache
        keeps ``id(node)`` stable for the CR 603.2 declare-dedup. The
        shapes mirror the frozen-IR precedent (Quirion Dryad's compiled
        cast-trigger is exactly prowess minus the type exclusion):
        PROWESS  — "whenever you cast a noncreature spell" → +1/+1 until
        end of turn (PtDelta lanes, DurationEot sweep);
        BATTALION — "whenever this creature attacks alone-or-not" gated
        at the queue site on the CR 508.2 group-of-three → a +1/+1
        counter (the Dryad's PUT_COUNTER shape)."""
        key = (family, handle)
        node = self._kw_nodes.get(key)
        if node is not None:
            return node
        target = Selector(
            count=QConst(1),
            mode=SelectorMode.CHOOSE,
            filter=FAtom(pred=FAtomPred.IS_SOURCE),
            zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
        )
        if family == "PROWESS":
            node = TriggeredAbility(
                event=CastSpellEvent(
                    filter=FNot(
                        inner=FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature")
                    ),
                    actor=FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
                ),
                condition=None,
                effect=Atom(
                    verb=Verb.MODIFY_PT,
                    args=AtomArgs(
                        pairs=(
                            (
                                "power",
                                PtDelta(
                                    direction=PtDirection.INCREASE,
                                    magnitude=QConst(1),
                                ),
                            ),
                            (
                                "toughness",
                                PtDelta(
                                    direction=PtDirection.INCREASE,
                                    magnitude=QConst(1),
                                ),
                            ),
                            ("duration", DurationEot()),
                            ("target", target),
                        )
                    ),
                ),
            )
        else:  # BATTALION
            node = TriggeredAbility(
                event=DeclareAttackersEvent(filter=FAtom(pred=FAtomPred.IS_SOURCE)),
                condition=None,
                effect=Atom(
                    verb=Verb.PUT_COUNTER,
                    args=AtomArgs(
                        pairs=(
                            ("count", QConst(1)),
                            ("counter_kind", CounterKind.PLUS_1_PLUS_1),
                            ("target", target),
                        )
                    ),
                ),
            )
        self._kw_nodes[key] = node
        return node

    def _group_size(self, event: GameEvent) -> int:
        """CR 508.2 population for the BATTALION gate: how many attackers
        share this DECLARE_ATTACKERS row's declaration group. The declare
        step journalled EVERY row inside one atom boundary, so the whole
        declaration is already in the journal when the drain first sees
        any row of it — a pure journal read, no executor side-state."""
        return sum(
            1
            for other in self.executor.journal.events
            if other.kind == KIND_DECLARE_ATTACKERS and other.data == event.data
        )

    def _match_node(
        self, node: EventSpec, event: GameEvent, source: Handle, controller: Handle
    ) -> bool:
        """Does one IR event-spec node subscribe to one journalled event?
        Filters and counts evaluate in a match ctx (source = the bound
        permanent, controller = its controller) via the 12a evaluator —
        unsupported preds/quantities raise through it (flag, don't degrade)."""
        kind = event.kind
        if kind == KIND_ZONE_CHANGE:
            if isinstance(node, ZoneChangeEvent):
                return self._match_zone_change(node, event, source, controller)
            if isinstance(node, SacrificeEvent):
                return self._match_sacrifice(node, event, source, controller)
            return False
        if kind == KIND_CREATURE_DIES and isinstance(node, CreatureDiesEvent):
            assert event.subject is not None  # the journal always names the dead
            ctx = self._match_ctx(source, controller, event)
            return eval_filter(node.filter, event.subject, ctx)
        if kind == KIND_CARD_DRAWN and isinstance(node, CardDrawnEvent):
            ctx = self._match_ctx(source, controller, event)
            drawer, ordinal = event.draw
            if node.actor is not None and not eval_filter(node.actor, drawer, ctx):
                return False
            return node.ordinal is None or node.ordinal == ordinal
        if kind == KIND_COUNTER_PLACED and isinstance(node, CounterPlacedEvent):
            return self._match_counter(node, event, source, controller)
        if kind == KIND_TAP_STATE and isinstance(node, TapStateEvent):
            if node.tapped != event.tapped_new:
                return False
            assert event.subject is not None
            ctx = self._match_ctx(source, controller, event)
            return eval_filter(node.filter, event.subject, ctx)
        if kind == KIND_TURN_PHASE and isinstance(node, TurnPhaseEvent):
            phase_name, active = event.phase
            if node.phase.name != phase_name:
                return False
            ctx = self._match_ctx(source, controller, event)
            return node.actor is None or eval_filter(node.actor, active, ctx)
        if kind == KIND_DECLARE_ATTACKERS and isinstance(node, DeclareAttackersEvent):
            # 16b: the attack feed. The filter reads the DECLARED creature
            # (IS_SOURCE = "whenever this creature attacks"); the optional
            # ``attacked`` filter (R10-3) reads the attacker's ATTACKED
            # object off the executor's attack record — v1: every attacker
            # attacks the defending player (planeswalker attacks are 16c).
            assert event.subject is not None  # the row names the attacker
            ctx = self._match_ctx(source, controller, event)
            if node.attacked is not None:
                attacked = self.executor.attacked.get(event.subject)
                if attacked is None or not eval_filter(node.attacked, attacked, ctx):
                    return False
            return eval_filter(node.filter, event.subject, ctx)
        # R2 fold (/140): the KIND_COMBAT_DAMAGE / CombatDamageEvent branch
        # is GONE — folded combat triggers read the DAMAGE rows here
        # (kind == KIND_DAMAGE, _match_damage, node.combat gating).
        if kind == KIND_DECLARE_BLOCKERS and isinstance(
            node, (DeclareBlockersEvent, BecomesBlockedEvent)
        ):
            # 16c: the block feed, ONE row per declaration pair (subject =
            # the BLOCKER, data = (attacker, group)). A DeclareBlockers-
            # Event node reads filter/SUBJECT over the blocker and the
            # BLOCKED slot over the attacker (Snarespinner's "blocks a
            # creature with flying", Elder Gargaroth's "attacks or blocks",
            # the Pirate/Shacklegeist prevention shapes share these slots).
            # A BecomesBlockedEvent node is anchored: the blocked partici-
            # pant must BE the trigger's source (Gloom Sower "whenever
            # THIS creature becomes blocked by a creature") — the grammar
            # gives the node no subject field of its own, the event name
            # carries the anchor.
            assert event.subject is not None  # the row names the blocker
            ctx = self._match_ctx(source, controller, event)
            blocker = event.subject
            attacker, _group = event.declare_blockers
            if isinstance(node, DeclareBlockersEvent):
                if node.subject is not None and not eval_filter(
                    node.subject, blocker, ctx
                ):
                    return False
                if node.blocked is not None and not eval_filter(
                    node.blocked, attacker, ctx
                ):
                    return False
                return eval_filter(node.filter, blocker, ctx)
            if attacker != source:
                return False
            return eval_filter(node.filter, blocker, ctx)
        if kind == KIND_DAMAGE and isinstance(node, DamageDealtEvent):
            return self._match_damage(node, event, source, controller)
        if kind == KIND_LIFE_GAINED and isinstance(node, LifeGainedEvent):
            assert event.subject is not None  # the gaining player
            ctx = self._match_ctx(source, controller, event)
            return node.actor is None or eval_filter(node.actor, event.subject, ctx)
        if kind == KIND_CAST and isinstance(node, CastSpellEvent):
            return self._match_cast(node, event, source, controller)
        if (
            kind == KIND_TARGETING
            and event.cause_verb == "TARGET"
            and isinstance(node, TargetingEvent)
        ):
            # r20b (Warden of the Woods): the designation feed — the filter
            # reads the DESIGNATED object (IS_SOURCE = "whenever THIS
            # becomes the target of a spell or ability"). A PLAYER subject
            # (a Duress-shaped cast) is answered with the same honest
            # three-valued shape as the damage lane: card-shape preds are
            # FALSE outright, undecidable preds keep the 12c raise.
            assert event.subject is not None  # the row names its object
            ctx = self._match_ctx(source, controller, event)
            if event.subject.namespace == "player":
                if _is_universal(node.filter):
                    return True
                if _is_subject_identity(node.filter):
                    return False
                return _player_subject_verdict(node.filter, event.subject, ctx)
            return eval_filter(node.filter, event.subject, ctx)
        if kind == KIND_LOYALTY_ACTIVATED and isinstance(node, LoyaltyActivatedEvent):
            # r22c (Keral Keep Disciples): the loyalty feed — the node's
            # CONTROLLER scope reads the ACTIVATING player (the row's
            # cause, the CR 606.3 seat), its FILTER reads the PERMANENT
            # whose loyalty ability was paid for (the grammar's "a
            # Chandra planeswalker" slot — a Basri row evaluates FALSE
            # here, the negative half of the pack).
            assert event.subject is not None  # the row names the permanent
            assert event.cause is not None  # the row names its activator
            ctx = self._match_ctx(source, controller, event)
            if node.actor is not None and not eval_filter(node.actor, event.cause, ctx):
                return False
            return eval_filter(node.filter, event.subject, ctx)
        return False  # no subscriber shape for this journalled kind

    def _match_cast(
        self, node: CastSpellEvent, event: GameEvent, source: Handle, controller: Handle
    ) -> bool:
        """13b: the CAST feed — CR 603.2's "whenever you cast" half. The
        journalled tuple (``GameEvent.cast``) carries (caster, per-turn
        ordinal, spell kind, from-zone, X): ``controller`` scopes whose
        cast (OPPONENT = "an opponent casts" — Mangara, Ghostly Pilferer),
        ``ordinal`` is the Nth cast by THAT caster this turn (journal-
        counted, reset at begin_turn — "whenever you cast your second
        spell", Double Vision's first-cast ordinal 1), and the zone pair
        is mutually exclusive in the grammar (R4-3): ``from_zone`` must
        equal the cast's source zone, ``from_zone_not`` EXCLUDES it
        (Ghostly Pilferer: "from anywhere other than their hand" — a zone
        whose controller ref scopes the caster, not the zone's owner: the
        cast came from the caster's zones). The filter reads the SPELL
        card (subject of the CAST row) — TYPE_EQ/SUBTYPE_EQ/COLOR_IN over
        it, which is exactly Quirion Dryad's compiled "colored spell"
        filter (COLOR_IN WUBR = non-empty subset, quantity.py 13b)."""
        caster, ordinal, _kind, from_zone, _x, _kicked = event.cast
        ctx = self._match_ctx(source, controller, event)
        if node.actor is not None and not eval_filter(node.actor, caster, ctx):
            return False
        if node.ordinal is not None and node.ordinal != ordinal:
            return False
        if node.from_zone is not None and not self._cast_zone_matches(
            node.from_zone, caster, from_zone, ctx
        ):
            return False
        if node.from_zone_not is not None and self._cast_zone_matches(
            node.from_zone_not, caster, from_zone, ctx
        ):
            return False
        assert event.subject is not None  # the CAST row names the spell card
        return eval_filter(node.filter, event.subject, ctx)

    def _cast_zone_matches(
        self, zone_ir: Zone, caster: Handle, from_zone: str | None, ctx: ExecCtx
    ) -> bool:
        """One CastSpellEvent zone endpoint vs the journalled source zone.
        The zone KIND must equal the cast's origin zone, and the zone's
        controller ref scopes the CASTER (grammar reading: "from your
        graveyard" = the caster's graveyard — unlike ZoneChangeEvent,
        whose endpoint scopes the zone's owner)."""
        want = ZONE_KIND_TO_STATE.get(zone_ir.kind)
        if want is None or from_zone is None or want != from_zone:
            return False
        if zone_ir.controller is ControllerRef.ANY:
            return True
        return controller_matches(zone_ir.controller, caster, ctx)

    def _match_ctx(
        self, source: Handle, controller: Handle, event: GameEvent
    ) -> ExecCtx:
        return self._ctx(source, controller, event)

    def _match_zone_change(
        self,
        node: ZoneChangeEvent,
        event: GameEvent,
        source: Handle,
        controller: Handle,
    ) -> bool:
        from_state, to_state, owner_before, owner_after = event.zone_move
        ctx = self._match_ctx(source, controller, event)
        if not self._zone_matches(node.from_zone, from_state, owner_before, ctx):
            return False
        if not self._zone_matches(node.to_zone, to_state, owner_after, ctx):
            return False
        if node.subject is None:
            return True
        assert event.subject is not None  # a zone move always names its subject
        return eval_filter(node.subject, event.subject, ctx)

    def _zone_matches(
        self,
        zone_ir: Zone,
        state_kind: str | None,
        zone_owner: Handle | None,
        ctx: ExecCtx,
    ) -> bool:
        """One ZoneChangeEvent endpoint vs the journalled move. A created
        object's ``from`` (None) matches ANY — an ETB from nowhere is an ETB
        from anywhere. STACK/PLAYER endpoints name no card zone and never
        match. OWNER scopes to the card's owner, who in this frozen model
        is exactly the zone owner."""
        if zone_ir.kind is not ZoneKind.ANY:
            want = ZONE_KIND_TO_STATE.get(zone_ir.kind)
            if want is None or state_kind is None or want != state_kind:
                return False
        ref = zone_ir.controller
        if ref is ControllerRef.ANY or zone_ir.kind is ZoneKind.ANY:
            return True
        if ref is ControllerRef.OWNER:
            return True  # zone owner IS the card's owner here
        if zone_owner is None:
            return False
        return controller_matches(ref, zone_owner, ctx)

    def _match_sacrifice(
        self, node: SacrificeEvent, event: GameEvent, source: Handle, controller: Handle
    ) -> bool:
        from_state, to_state, owner_before, _after = event.zone_move
        if (
            from_state != ZONE_BATTLEFIELD
            or to_state != ZONE_GRAVEYARD
            or event.cause_verb != "SACRIFICE"
        ):
            return False
        assert owner_before is not None  # a battlefield move has an owner
        ctx = self._match_ctx(source, controller, event)
        return node.actor is None or eval_filter(node.actor, owner_before, ctx)

    def _match_counter(
        self,
        node: CounterPlacedEvent,
        event: GameEvent,
        source: Handle,
        controller: Handle,
    ) -> bool:
        kind_name, placed = event.counter
        if node.counter_kind.name != kind_name:
            return False
        assert event.subject is not None
        ctx = self._match_ctx(source, controller, event)
        if not eval_filter(node.filter, event.subject, ctx):
            return False
        if node.count is None:
            return True
        return placed >= resolve(node.count, ctx)

    def _match_damage(
        self,
        node: DamageDealtEvent,
        event: GameEvent,
        source: Handle,
        controller: Handle,
    ) -> bool:
        subject = event.subject
        ctx = self._match_ctx(source, controller, event)
        # 16c: the node's SCOPE fields are consumed (Garruk's Harbinger's
        # "deals combat damage to a player" and Subira's delayed tail both
        # compile ``combat: true`` + a ``source`` filter over the DEALER;
        # pre-16c the matcher ignored them and the trigger fired on ANY
        # damage event). The DAMAGE row carries the dealer as ``cause``
        # and the combat flag as the optional second data element.
        if node.combat is not None and event.is_combat != node.combat:
            return False
        if node.source is not None:
            dealer = event.cause
            if dealer is None or not eval_filter(node.source, dealer, ctx):
                return False
        if subject is not None and subject.namespace == "player":
            if _is_universal(node.filter):
                return True
            if _is_subject_identity(node.filter):
                return False  # 16a: a player is never the source CARD (Brash)
            # r20b (Hooded Blightfang): the player-damage row must be
            # ANSWERABLE by a card-shape filter — the Blightfang's "deals
            # combat damage to a planeswalker" node reads SUPERTYPE_EQ over
            # its subject, and a player is honestly not one: FALSE, not a
            # crash. Undecidable preds keep the 12c raise.
            return _player_subject_verdict(node.filter, subject, ctx)
        assert subject is not None  # a damage event always names its subject
        return eval_filter(node.filter, subject, ctx)

    # -------------------------------------------------------------- fire

    def fire_all(self) -> int:
        """Drain the world's trigger queue: APNAP order_key, then
        ``str(source)`` then bind-seq (Handle-sort within a seat, ruling 5).
        Every firing runs through the 12a effect runner, whose journalled
        events queue the next batch; loop until empty — the r23a tripwire
        guard QUARANTINES a self-retriggering source (recorded in the
        executor's trigger_loops ledger) and the drain continues.
        14b (B-4 ruling): the drain consumes NO positional stream
        — every demand a firing makes reaches the executor's
        vocabulary-addressed decision channel (per-(vocab, what) FIFO /
        ask-time provider), so a trigger the op itself armed mid-drain is
        answerable exactly like one that was already pending."""
        fired = 0
        per_source: dict[Handle, int] = {}
        while self.world.triggers:
            if fired >= MAX_TRIGGER_FIRES:
                # r23a (Chandra's Incinerator, games seeds 17/50): the
                # tripwire GUARDS instead of killing the game. The culprit
                # is the source this drain fired MOST — its effect's own
                # events re-arm it (an Incinerator "whenever you deal
                # noncombat damage" trigger eating its own damage row).
                # QUARANTINE it: drop its queued instances, block its
                # _queue for the rest of the game, record the event loudly
                # in executor.trigger_loops — "flag it, never run it" —
                # and continue the drain with everything else. Only an
                # eighth distinct runaway in ONE game re-raises: then the
                # state itself is the anomaly, not a card.
                culprit = next(
                    (
                        src
                        for src, _n in sorted(
                            per_source.items(), key=lambda kv: (-kv[1], str(kv[0]))
                        )
                        if src not in self.quarantined
                    ),
                    None,
                )
                if culprit is None or len(self.quarantined) >= 8:
                    raise RuntimeError(
                        "executor: trigger-loop tripwire — one drain resolved "
                        f"{MAX_TRIGGER_FIRES} triggers and the queue is still "
                        "growing (self-retriggering loop: flag it, never run it)"
                    )
                record = self.handle_record.get(culprit)
                self.quarantined.add(culprit)
                dropped = [t for t in self.world.triggers if t.source == culprit]
                for t in dropped:
                    self.world.triggers.remove(t)
                    self.firings.pop(t.clock, None)
                self.executor.trigger_loops.append(
                    f"{culprit} ({getattr(record, 'name', culprit)!r}): "
                    f"self-retriggering after {per_source.get(culprit, 0)} "
                    f"drain fires — quarantined, {len(dropped)} queued "
                    "firings dropped"
                )
                fired = 0
                continue
            instance = self._pop_next()
            payload = self.firings.pop(instance.clock, None)
            if payload is None:  # pragma: no cover - instances only via _queue
                continue
            self._fire(payload)
            per_source[instance.source] = per_source.get(instance.source, 0) + 1
            fired += 1
            self.on_events()  # the firing's own events queue the next batch
        return fired

    def _pop_next(self):
        ordered = sorted(
            self.world.triggers,
            key=lambda t: (
                t.controller_seat,
                t.clock,
                str(t.source),
                self.firings[t.clock].seq if t.clock in self.firings else -1,
            ),
        )
        chosen = ordered[0]
        self.world.triggers.remove(chosen)
        return chosen

    def _fire(self, payload: _Firing) -> None:
        """One trigger resolution: the condition gate, the 18b TARGET-
        designation channel, then the effect. May-offers ask the executor's
        decision stream (14b, B-4)."""
        event = payload.event
        ctx = self._ctx(payload.source, payload.controller, event)
        # r21b (Basri Ket's -2): a DECLARE_ATTACKERS firing records its WHOLE
        # declaration group — every journalled attacker row sharing the
        # event's group id — into a dedicated ``declare_attackers`` register.
        # The granted "whenever … attacks, create a token" continuation
        # counts the attackers with THAT_MANY_COUNT, whose primary reading
        # is the in-resolution ``result`` register (Kinetic Augur's
        # precedence, untouched); the group register is the fallback that
        # answers when the trigger itself IS the antecedent (no producer
        # atom ran in this resolution). Rows are journalled at declaration
        # time, before the matcher drains any firing (16b's group dedup
        # already relies on that ordering), so the group is complete here.
        if event.kind == KIND_DECLARE_ATTACKERS and event.subject is not None:
            group = event.declare_group
            ctx.bindings["declare_attackers"] = [
                e.subject
                for e in self.executor.journal.turn_window()
                if e.kind == KIND_DECLARE_ATTACKERS
                and e.declare_group == group
                and e.subject is not None
            ]
        node = payload.node
        if node.condition is not None:
            subject = event.subject if event.subject is not None else payload.source
            if not eval_filter(node.condition, subject, ctx):
                return
        # 18b (CR 603.1): designate targets BEFORE applying — the frozen IR
        # puts the ability's TARGET coordinates on the TRIGGERED-ABILITY node
        # itself, and CR 603.1 chooses targets as the ability goes on the
        # stack, which for a firing means before its first verb runs. The
        # 16a DAMAGE echo already bound its anaphoric antecedent in _ctx
        # (the dealer); the 18b DIES twin (Massacre Wurm's "that player")
        # binds here; anything else the effect reads as target/TARGET_PLAYER
        # gets a real designation ask through the 14b channel.
        # R2 (2026-10-20, /140 fold): the 16a DAMAGE pre-bind is the
        # TARGET_PLAYER-anaphora read (Brash Taunter's echo). A trigger
        # whose printed TARGET slot designates from an EVENT-SUBJECT-
        # parameterized population (Feline Sovereign's / Chandra's
        # Incinerator's "that player controls", compiled as CONTROLLER_IS
        # who=<Selector referent='event'>) can never be served by the
        # dealer designation — the pre-bind must not swallow the 18b lane
        # for it. The narrow gate keeps every TARGET_PLAYER reader (Brash
        # Taunter's echo zone) exactly as 16a bound it.
        if (
            event.kind == KIND_DAMAGE
            and event.cause is not None
            and ctx.bindings.get("target") == event.cause
            and (
                self._damage_designation_is_event_borne(node)
                or not self._prebind_legal_for_targets(node, ctx)
            )
        ):
            # R2 diff-gate BREAK-3 fix: the shape gate alone was fail-OPEN
            # on the other polarity — a TARGET slot with a NON-event filter
            # (e.g. CONTROLLER_IS OPPONENT) kept the pre-bind, and
            # resolve_selector takes a bound handle as FROZEN DESIGNATION
            # WITHOUT CONSULTING the selector's zones+filter, so the dealer
            # resolved the slot against ITSELF (probe4 Variant A: the dealer
            # destroyed itself, no ask, no journal). The validation lift
            # closes that: the 16a dealer designation may only stand when
            # it is actually LEGAL for every printed TARGET slot. Known-
            # narrow by design, two ways: (i) the shape scan above never
            # reads trigger CONDITIONS; (ii) its TARGET_PLAYER scan misses
            # bare-role reads (LOSE_LIFE controller=TARGET_PLAYER) — for
            # both, _designation's broader scan + loud multi-slot raise is
            # the backstop (probe4 Variant D proved it catches the bare-
            # role case when a lift opens the ask lane).
            del ctx.bindings["target"]
        if ctx.bindings.get("target") is None:
            if (
                event.kind == KIND_CREATURE_DIES
                and event.subject is not None
                and not self._trigger_designates_target(node)
            ):
                # 16a's twin: in a DIES firing the antecedent the frozen IR
                # compiles to TARGET_PLAYER IS the dead creature — players
                # _for_ref folds a card designation to its controller, so
                # "that player loses 2 life" means the creature's controller
                # (the event's OWN filter scoped it to an opponent's creature
                # when the card text says so). The event object is the
                # honest antecedent, exactly the DAMAGE dealer ruling.
                # r22a (Pitchburn Devils / Goblin Arsonist): the anaphora
                # pre-bind is only the dead creature when the effect reads
                # the anaphora. A printed "…to ANY target" carries a real
                # TARGET Selector slot — CR 603.1 designates it through the
                # 18b channel, and the pre-bind must never swallow the ask.
                ctx.bindings["target"] = event.subject
            elif not self._designate(node, ctx):
                # B-55, CR 603.3d: a required target with no legal choice
                # removes the ability from the stack. None of its effect
                # happens, its untargeted steps included.
                return
        # The 12a shared effect runner — the SAME dispatch execute() uses,
        # journalled at its Atom boundaries by the Executor. r24 (/111):
        # guarded like the spell lanes — a template mis-fold whose
        # anaphora has no producer skips LOUD (unresolved_effects) instead
        # of killing the match; every other error still propagates.
        self.executor._run_guarded_effect(node.effect, ctx, "trigger")

    @staticmethod
    def _filter_reads_event_ref(filter_: object) -> bool:
        """R2 (/140): does this filter tree gate on CONTROLLER_IS whose
        ``who`` slot is an EVENT-REFERENT Selector (the frozen-IR shape of
        "that player controls" where THAT PLAYER is the event subject —
        Feline Sovereign's DESTROY, Chandra's Incinerator's burn)?"""
        if isinstance(filter_, FAtom):
            who = filter_.who
            if (
                filter_.pred is FAtomPred.CONTROLLER_IS
                and isinstance(who, Selector)
                and who.referent in ("event", "result")
            ):
                return True
            return any(
                TriggerBinder._filter_reads_event_ref(inner)
                for inner in (filter_.inner_filter, filter_.right_inner_filter)
                if inner is not None
            )
        if isinstance(filter_, (FAnd, FOr)):
            return any(
                TriggerBinder._filter_reads_event_ref(c) for c in filter_.children
            )
        if isinstance(filter_, FNot):
            return TriggerBinder._filter_reads_event_ref(filter_.inner)
        return False

    @classmethod
    def _damage_designation_is_event_borne(cls, node: _AnyTrigger) -> bool:
        """R2 narrow gate (/140): True iff the trigger's printed TARGET
        slots designate from an event-subject-parameterized population
        (every TARGET-mode, referent-free Selector's filter reads the
        event-ref CONTROLLER_IS) AND the node reads the TARGET_PLAYER
        designation nowhere (Brash Taunter's echo zone keeps its 16a
        dealer pre-bind untouched). A node failing either side keeps the
        pre-bind exactly as 16a bound it."""
        targets: list[Selector] = []
        for inner in walk(node.effect):
            if not isinstance(inner, Atom):
                continue
            for _role, value in inner.args.pairs:
                if isinstance(value, Selector):
                    if value.mode is SelectorMode.TARGET and value.referent is None:
                        targets.append(value)
                    if filter_reads_bound_player(value):
                        return False
                elif filter_reads_bound_player(value):
                    return False
            if filter_reads_bound_player(inner):
                return False
        if not targets:
            return False
        return all(cls._filter_reads_event_ref(sel.filter) for sel in targets)

    def _prebind_legal_for_targets(self, node: _AnyTrigger, ctx: ExecCtx) -> bool:
        """R2 diff-gate BREAK-3 fix: may the 16a dealer pre-bind stand as
        the FROZEN DESIGNATION of every printed TARGET slot of this
        trigger? resolve_selector takes a bound handle without re-checking
        the selector's filter, so the check must happen at the lift site.
        ONE legality opinion (query/runtime identity, §8.3): the slot's
        population is :func:`query.legal_targets` — the SAME enumeration
        the :meth:`_designate` ask lane uses; the designation is legal iff
        it is IN that population, with the 16a zone-side rule folded in: a
        CARD designation legalises a PLAYER-side slot through its
        controller (exactly what makes Brash Taunter's echo lane work).
        A trigger with no TARGET slot needs nothing of the pre-bind and
        answers True (the dealer stays). Validation never asks; a failing
        designation LIFTS the pre-bind and the 18b ask lane re-runs from
        the selector's own filter. KNOWN-NARROW (diff-gate FIX-3, by
        design): neither this check nor the shape gate above ever reads
        the trigger's CONDITION, and the TARGET_PLAYER scan misses
        BARE-ROLE reads (LOSE_LIFE controller=TARGET_PLAYER). A node
        whose lift opens both a TARGET slot and a bare-role read is
        caught LOUD by _designation's broader scan + multi-slot raise
        (probe4 Variant D proved the backstop) — never a silent bind."""
        from MTG_bot.core.executor.query import legal_targets

        designated = ctx.bindings.get("target")
        for inner in walk(node.effect):
            if not isinstance(inner, Atom):
                continue
            for _role, value in inner.args.pairs:
                if not (
                    isinstance(value, Selector)
                    and value.mode is SelectorMode.TARGET
                    and value.referent is None
                ):
                    continue
                slot = legal_targets(
                    self.world,
                    self.executor,
                    value,
                    source=ctx.source,
                    controller=ctx.controller,
                    bindings=ctx.bindings,
                )
                candidates = set(slot.candidates)
                if designated in candidates:
                    continue
                owner = self.executor.controller_of(designated)
                if owner is not None and owner in candidates:
                    continue  # 16a: a CARD designation legalises a player
                return False
        return True

    @staticmethod
    def _trigger_designates_target(node: _AnyTrigger) -> bool:
        """r22a: does this trigger's effect carry a real TARGET designation
        slot — a TARGET-mode Selector with no referent? Mirrors the
        Selector collector in :meth:`_designate` (walk enters Optional-
        /SeqEffect wrappers, so Goblin Arsonist's may-wrapped damage is
        seen). A node that only reads the TARGET_PLAYER anaphora (Massacre
        Wurm's "that player") answers False and keeps the 16a/18b dies
        pre-bind in :meth:`_fire`; a printed "…to ANY target" (Pitchburn
        Devils) answers True and routes to the designation ask."""
        for inner in walk(node.effect):
            if not isinstance(inner, Atom):
                continue
            for _role, value in inner.args.pairs:
                if (
                    isinstance(value, Selector)
                    and value.mode is SelectorMode.TARGET
                    and value.referent is None
                ):
                    return True
        return False

    def _designate(self, node: _AnyTrigger, ctx: ExecCtx) -> bool:
        """The 18b designation channel (CR 603.1, first PC-8 lift).
        Returns False when the ability is removed from the stack (CR
        603.3d, B-55), True when it goes on and resolves.

        The TARGET-bearing trigger no longer crashes at its first verb: the
        engine enumerates the candidates through its OWN 12c query surface
        (``query.legal_targets`` — §8.3 query/runtime identity, no mirrored
        population) and asks the 14b vocabulary-addressed channel for the
        choice (ask id ``target:<source>:<digest>``, the ONE_OF ask's shape
        — the Handle-sorted candidate list IS the vocabulary, C15-complete,
        ``take_decision`` re-validates membership). The answer lands in
        ``ctx.bindings["target"]`` BEFORE the effect runs, the exact mirror
        of ``stack.cast``'s designate-then-apply.

        Routing table (per-card, event-kind driven — see _fire):
        * DAMAGE firing → the dealer (16a, in _ctx);
        * CREATURE_DIES firing → the dead creature (18b, in _fire);
        * a single distinct TARGET-mode Selector → enumerated ask (below);
        * a TARGET_PLAYER ControllerRef with no Selector (the "target
          opponent" grammar gap, the 14b synthetic-slot twin) → the
          ABILITY CONTROLLER's opponent seats; in the duel that is one
          seat → auto-filled (§1.4 forced auto-fill, no ask);
        * a multi-slot trigger (two distinct TARGETs, or a TARGET and a
          TARGET_PLAYER) → the loud raise stands (the cast lane's
          per-slot designation is /06 arc 3; this channel never guess-
          binds a second slot).

        The site tag carries the CONTROLLER seat (``target:<seat>:<source>:
        <digest>``, four segments like the combat lane): the answer belongs
        to the seat the rules gave the decision to, and a mirror pair of
        the same card asks two DIFFERENT keys (attribution, not collision).

        Zero-candidate honesty: nothing enumerable means no decision exists
        (C15); never a crash, never a guess. A REQUIRED slot (an exact
        count the ability needs whatever mode it takes, see
        :func:`_required_target_keys`) that cannot be filled removes the
        ability from the stack (CR 603.3d, B-55): False, and none of the
        effect runs. Before B-55 the binding was the empty set and the
        effect ran anyway, so its untargeted steps still happened and an
        ATTACH with no host raised. An "up to N" or mode-dependent slot
        binds the EMPTY set and the ability resolves without it, since zero
        targets (or another mode) is a legal choice.

        Cardinality follows the frozen slot contract: ``QConst(1)``
        designates exactly one (forced when one candidate);
        ``QAtMost(n)`` asks pick-by-pick, the first pick mandatory (C17:
        TARGET designation range 1..n, the pinned contract the query lane
        already enforces), later picks carry the ``"NONE"`` stop token the
        block-ask lane established; ``QConst(n>1)`` asks n picks without
        the stop token and clamps at exhaustion (C17's 0..remaining
        sibling); ``QAtLeast``/QX-in-TARGET stays the flag it always was.
        """
        selectors: list[Selector] = []
        seen: set[str] = set()
        reads_target_player = False
        for inner in walk(node.effect):
            if not isinstance(inner, Atom):
                continue
            for _role, value in inner.args.pairs:
                if (
                    value is ControllerRef.TARGET_PLAYER
                    or isinstance(value, Zone)
                    and value.controller is ControllerRef.TARGET_PLAYER
                    or isinstance(value, Selector)
                    and filter_reads_bound_player(value.filter)
                    or filter_reads_bound_player(value)
                ):
                    reads_target_player = True
                if (
                    isinstance(value, Selector)
                    and value.mode is SelectorMode.TARGET
                    and value.referent is None
                ):
                    key = repr(value)
                    if key not in seen:
                        seen.add(key)
                        selectors.append(value)
        if not selectors and not reads_target_player:
            return True  # no designation to make
        if len(selectors) > 1 or (selectors and reads_target_player):
            raise NotImplementedError(
                f"executor: trigger {node.effect!r:.80} carries "
                f"{len(selectors) + int(reads_target_player)} designation "
                "slots; per-slot designation is /06 arc 3 (never guess-bind "
                "the second)"
            )
        if reads_target_player:
            # The synthetic player slot (spell_target_slots' 14b twin): the
            # candidate population is the ENGINE's player rule — the ability
            # controller's opponents — and the cross-seat ruling is CR
            # 603.1's: the ABILITY's controller designates, so an opponent's
            # trigger asks the OPPONENT's seat (ctx.controller IS that seat,
            # the firing context was built from payload.controller).
            opponents = players_for_ref(ControllerRef.OPPONENT, ctx)
            if not opponents:
                ctx.bindings["target"] = []  # resolves without a player (a
                # duel always has an opponent; the empty read is the honest
                # multiplayer-shape answer, not a crash). Not a CR 603.3d
                # removal: this slot cannot tell "target player" (you are a
                # legal target) from "target opponent" (B-53).
            elif len(opponents) == 1:
                ctx.bindings["target"] = opponents[0]
            else:
                vocab = tuple(str(h) for h in sorted(opponents))
                answer = ctx.take_decision(
                    vocab,
                    f"target:{ctx.controller}:{ctx.source}:{site_digest(vocab)}",
                )
                ctx.bindings["target"] = next(
                    h for h in sorted(opponents) if str(h) == answer
                )
            # r20b: TARGETING feed — a genuine designation made here is an
            # event (pre-bound firings never reach this method). The empty
            # set emits nothing.
            designated = ctx.bindings["target"]
            self.executor.journal.emit_targeting(
                ctx.source,
                ctx.controller,
                designated if isinstance(designated, list) else [designated],
            )
            return True
        selector = selectors[0]
        from MTG_bot.core.executor.query import (  # cycle-free at call time
            _widen_any_target,  # the query lane's ONE widening opinion (13b)
            legal_targets,
        )

        slot = legal_targets(
            self.world,
            self.executor,
            selector,
            source=ctx.source,
            controller=ctx.controller,
            # r23a (Feline Sovereign): the firing ctx's bindings ride into
            # the candidate enumeration. The trigger already bound the
            # 'event' register (binding.py _ctx stamps event.subject before
            # designation), and the destroyed object's filter reads it —
            # "destroy target artifact or enchantment THAT CREATURE'S
            # CONTROLLER controls" compiles CONTROLLER_IS who=
            # Selector(referent='event'). A fresh ctx without the firing
            # bindings made that selector ask a register it never saw
            # (selectors.py: 'event' has no register). legal_targets has
            # taken bindings= since 14a B-8a for exactly this; the trigger
            # lane was the last caller not passing it.
            bindings=ctx.bindings,
        )
        slot = _widen_any_target(self.executor, selector, slot) or slot
        candidates = sorted(slot.candidates)
        count = selector.count
        # B-55, CR 603.3d: an exact-count slot the ability needs in every
        # mode, with too few legal choices, removes it from the stack.
        required = isinstance(count, QConst) and repr(selector) in (
            _required_target_keys(node.effect)
        )
        if not candidates:
            if required:
                return False
            ctx.bindings["target"] = []  # "up to N" / mode-dependent slot:
            # zero targets is a legal choice, the ability resolves without
            return True
        if not isinstance(count, (QConst, QAtMost)):
            raise NotImplementedError(
                f"executor: trigger TARGET count {count!r} designates "
                "through the 12c prompt (QX/QAtLeast in a trigger TARGET "
                "is not a frozen-IR shape)"
            )
        # T3 legality unification (doc 36, CR 601.2c): ONE answer for the
        # count axis — QConst is EXACT, never clamped. A trigger that
        # cannot complete its full-size designation rides the empty-slot
        # lane above: removed from the stack when the slot is required
        # (CR 603.3d, B-55), otherwise designate NOTHING and resolve.
        # Asking over fewer than stated (the old unclamped loop running
        # the menu dry) was the third divergent answer of the legality
        # triad.
        optional_stop = isinstance(count, QAtMost)  # C17 first mandatory
        announceable, wanted = count_semantics(count, len(candidates))
        if not announceable:
            if required:
                return False
            ctx.bindings["target"] = []
            return True
        picks: list[Handle] = []
        pool = list(candidates)
        for pick_no in range(wanted):
            if len(pool) == 1 and not (optional_stop and pick_no > 0):
                picks.append(pool[0])  # §1.4 auto-fill: one legal filler
                break
            vocab = tuple(str(h) for h in pool)
            if optional_stop and pick_no > 0:
                vocab = vocab + ("NONE",)
            answer = ctx.take_decision(
                vocab,
                f"target:{ctx.controller}:{ctx.source}:{site_digest(vocab)}",
            )
            if answer == "NONE":
                break
            pick = next(h for h in pool if str(h) == answer)
            picks.append(pick)
            pool.remove(pick)
        ctx.bindings["target"] = picks if len(picks) != 1 else picks[0]
        # r20b: TARGETING feed — see the player-slot note above; an empty
        # pick list (impossible past the zero-candidate return) emits none.
        self.executor.journal.emit_targeting(ctx.source, ctx.controller, picks)
        return True

    def _ctx(
        self,
        source: Handle,
        controller: Handle,
        event: GameEvent,
    ) -> ExecCtx:
        ex = self.executor
        bindings: dict[str, Handle] = {}
        if event.subject is not None:
            bindings["event"] = event.subject
            if event.kind == KIND_CREATURE_DIES:
                bindings["result"] = event.subject  # C18 was-snapshot subject
        if event.kind == KIND_DAMAGE and event.cause is not None:
            # 16a (Brash Taunter): the frozen IR compiles the echo's
            # "it deals that much damage to any target" as TARGET_PLAYER,
            # which reads bindings["target"]. In a DAMAGE firing the
            # designation the frozen comment names IS the dealer — bind
            # it, so TARGET_PLAYER means "the controller of the source of
            # that damage" instead of the 12c prompt raise.
            bindings["target"] = event.cause
        amount = event.amount if event.kind in (KIND_DAMAGE, KIND_LIFE_GAINED) else None
        # r20a (Light of Promise): a LIFE_GAINED row's data[0] IS the amount
        # gained, so QProp(referent='event', field=AMOUNT) resolves inside a
        # life-gained firing exactly as it does inside a damage firing.
        # r23a (Wildwood Scourge, CR 614.1c): a spell cast with a declared X
        # carries that X into every firing this ENTRY generates — stack.cast
        # recorded it as the spell landed. The read is NON-destructive on
        # purpose: _match_zone_change builds this same ctx for the matcher
        # (a pop there would rob the firing), and every ETB ability of the
        # entering permanent may legitimately mention X. The entry is
        # cleared when the permanent leaves the battlefield, so a later
        # re-entry carries no cast X. CR 107.3b: an object that was not cast
        # (reanimated, put onto the battlefield) has X = 0, so its own ETB
        # firing resolves X as 0. Every other undeclared X stays the loud 12c
        # flag. Found 2026-10-27 by coherent decks (B-45, /164): Rise Again
        # returning Wildwood Scourge raised NotImplementedError mid-game.
        x_value: int | None = None
        if (
            event.kind == KIND_ZONE_CHANGE
            and event.subject is not None
            and event.subject == source
            and len(event.data) >= 2
            and event.data[1] == ZONE_BATTLEFIELD
        ):
            x_value = ex.etb_x.get(source, 0)
        return ExecCtx(
            world=ex.world,
            ledger=ex.ledger,
            controller=controller,
            source=source,
            bindings=dict(bindings),
            x_value=x_value,  # r23a: CR 614.1c cast-declared X at ETB
            decisions=(),  # 14b: firings answer through ex.decisions
            stream=ex.decisions,
            events=ex.events,
            rng=ex.rng,
            token_counts=ex.token_counts,
            event=event,
            event_amount=amount,
            # 12d: trigger-fired GRANT/LOSE/PREVENT atoms and damage
            # replacements reach the registries through the ctx.
            layers=ex.layers,
            replacements=ex.replacements,
            executor=ex,
            # 14d (B-7): the firing ctx reads the SAME journal the matcher
            # is draining (history preds at a trigger's condition gate).
            journal=ex.journal,
        )

    # ------------------------------------------------------ delayed (C22)

    def schedule_delayed(
        self, node: DelayedTrigger, source: Handle, controller: Handle
    ) -> None:
        """Register a DelayedTrigger effect node into the journal matcher.
        Only the turn-window tags sweep in 12b; a permanent-window or any
        longer duration RAISES (the 12d Duration vocab governs LEDGER,
        layer and prevention records; delayed-trigger windows beyond the
        turn are 12e) — never a leak. The scheduled EVENT kind gets the
        same unsupported-kind flag-don't-degrade check as an attached
        trigger."""
        self._check_event(node.event, "DelayedTrigger")
        tag = duration_tag(node.duration)
        if tag not in _SWEEP_TAGS:
            raise NotImplementedError(
                f"executor: DelayedTrigger duration tag {tag!r} exceeds the "
                "turn window (12e)"
            )
        self._seq += 1
        self.delayed.append(
            DelayedBinding(
                seq=self._seq, tag=tag, node=node, source=source, controller=controller
            )
        )

    def expire_delayed(self) -> int:
        """End-of-turn sweep: drop the turn-window delayed triggers."""
        keep = [entry for entry in self.delayed if entry.tag not in _SWEEP_TAGS]
        expired = len(self.delayed) - len(keep)
        self.delayed = keep
        return expired

    # ---------------------------------------------------------- canonical

    def dump(self) -> tuple[tuple[object, ...], ...]:
        """Deterministic registry/delayed view for the replay fingerprint."""
        attached = tuple(
            (str(handle), idx, repr(ability.event))
            for (handle, idx), ability in sorted(
                self.attached.items(), key=lambda kv: (str(kv[0][0]), kv[0][1])
            )
        )
        delayed = tuple(
            (d.seq, d.tag, str(d.source), str(d.controller), repr(d.node.event))
            for d in sorted(self.delayed, key=lambda d: d.seq)
        )
        emblems = tuple(
            sorted(
                (str(handle), str(owner)) for handle, owner in self.emblem_owner.items()
            )
        )
        quarantined = tuple(sorted(map(str, self.quarantined)))
        return (
            ("attached", attached),
            ("delayed", delayed),
            ("emblems", emblems),
            ("quarantined", quarantined),
        )
