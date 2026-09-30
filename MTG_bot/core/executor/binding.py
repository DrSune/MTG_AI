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
    trigger instances; beyond that a self-retriggering loop RAISES — the
    loop is a bug to flag, never a bug to run;
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
    BecomesBlockedEvent,
    CardDrawnEvent,
    CardRecord,
    CastSpellEvent,
    CombatDamageEvent,
    ControllerRef,
    CounterKind,
    CounterPlacedEvent,
    CreatureDiesEvent,
    DamageDealtEvent,
    DeclareAttackersEvent,
    DeclareBlockersEvent,
    DelayedTrigger,
    EventSpec,
    FAnd,
    FAtom,
    FAtomPred,
    Filter,
    LifeGainedEvent,
    LoyaltyActivatedEvent,
    SacrificeEvent,
    StepEvent,
    TapStateEvent,
    TargetingEvent,
    TriggeredAbility,
    TurnPhaseEvent,
    Zone,
    ZoneChangeEvent,
    ZoneKind,
)
from MTG_bot.core.compiler.compiler import PoolCompile
from MTG_bot.core.executor.durations_min import duration_tag
from MTG_bot.core.executor.events import (
    KIND_CARD_DRAWN,
    KIND_CAST,
    KIND_COMBAT_DAMAGE,
    KIND_COUNTER_PLACED,
    KIND_CREATURE_DIES,
    KIND_DAMAGE,
    KIND_DECLARE_ATTACKERS,
    KIND_DECLARE_BLOCKERS,
    KIND_LIFE_GAINED,
    KIND_TAP_STATE,
    KIND_TURN_PHASE,
    KIND_ZONE_CHANGE,
    GameEvent,
)
from MTG_bot.core.executor.quantity import ExecCtx, eval_filter, resolve
from MTG_bot.core.executor.selectors import ZONE_KIND_TO_STATE, controller_matches
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
# 16c: DeclareBlockersEvent and BecomesBlockedEvent LEFT this table too —
# the blocker step ships the feed (journal DECLARE_BLOCKERS rows, one per
# declaration PAIR: subject = the blocker, data = (attacker, group)) and
# :meth:`TriggerBinder._match_node` subscribes both node kinds.
_UNSUPPORTED_EVENTS: dict[type, str] = {
    LoyaltyActivatedEvent: "12c (loyalty activations)",
    StepEvent: (
        "12e (step-level subscription emitter; 12d's untap tick is an "
        "executor step that emits TapState/phase events, not StepEvents)"
    ),
    TargetingEvent: "12c (target designation)",
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
        self.delayed: list[DelayedBinding] = []
        self._seen_journal_len = 0
        self._seq = 0
        # 16b CR 603.2 dedup: (source, node-id, declare-group) for every
        # DeclareAttackersEvent queue already made. The journal carries ONE
        # row per declared attacker (the grammar's filter is subject-
        # scoped), but a triggered ability triggers ONCE on the whole
        # declare action — the shared group id collapses the row fan-out.
        self._declare_queued: set[tuple[Handle, int, int]] = set()

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
        return self.world.controller_of(handle)

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
        self.detach(handle)
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
        self.detach(handle)
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

    def detach(self, handle: Handle) -> int:
        """Battlefield departure: drop the handle's live bindings (the
        oracle-id record stays, ready for the re-entry re-registration) —
        and 12d: its continuous layers and replacement records expire with
        it (their durations govern separately for records the permanent
        GRANTED elsewhere)."""
        keys = [key for key in self.attached if key[0] == handle]
        for key in keys:
            del self.attached[key]
        # 13c: attachment is battlefield-to-battlefield (CR 303.4c/117.12 —
        # when either side of an aura/equipment pair leaves, the attachment
        # relationship ends). The executor's attachment table drops every
        # edge touching the departing handle. (Emblems never detach: an
        # emblem cannot leave the battlefield/ownership in the rules — no
        # code path calls detach on an emblem handle.)
        ex = self.executor
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
            for entry in list(self.delayed):
                if self._match_node(
                    entry.node.event, event, entry.source, entry.controller
                ):
                    self._queue(entry.source, entry.controller, entry.node, event)
            self._lifecycle(event, attach=False)

    def _lifecycle(self, event: GameEvent, attach: bool) -> None:
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
            self.detach(handle)

    def _queue(
        self,
        source: Handle,
        controller: Handle,
        node: _AnyTrigger,
        event: GameEvent,
    ) -> None:
        if event.kind == KIND_DECLARE_ATTACKERS and isinstance(
            node.event, DeclareAttackersEvent
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
        self.firings[instance.clock] = _Firing(
            source=source, controller=controller, node=node, event=event, seq=self._seq
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
            if not controller_matches(node.controller, drawer, ctx):
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
            return controller_matches(node.controller, active, ctx)
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
        if kind == KIND_COMBAT_DAMAGE and isinstance(node, CombatDamageEvent):
            # 16b: the combat-damage feed — filter over the DEALING
            # creature (Jeskai Elder's / Feline Sovereign's "deals combat
            # damage"; 0-power attackers never emit the row, CR 120.7).
            assert event.subject is not None  # the row names the dealer
            ctx = self._match_ctx(source, controller, event)
            return eval_filter(node.filter, event.subject, ctx)
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
            return controller_matches(node.controller, event.subject, ctx)
        if kind == KIND_CAST and isinstance(node, CastSpellEvent):
            return self._match_cast(node, event, source, controller)
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
        caster, ordinal, _kind, from_zone, _x = event.cast
        ctx = self._match_ctx(source, controller, event)
        if node.controller is not None and not controller_matches(
            node.controller, caster, ctx
        ):
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
        return controller_matches(node.controller, owner_before, ctx)

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
            raise NotImplementedError(
                "executor: DamageDealtEvent filter over a player subject "
                "is 12c's query surface"
            )
        assert subject is not None  # a damage event always names its subject
        return eval_filter(node.filter, subject, ctx)

    # -------------------------------------------------------------- fire

    def fire_all(self) -> int:
        """Drain the world's trigger queue: APNAP order_key, then
        ``str(source)`` then bind-seq (Handle-sort within a seat, ruling 5).
        Every firing runs through the 12a effect runner, whose journalled
        events queue the next batch; loop until empty or the tripwire
        raises. 14b (B-4 ruling): the drain consumes NO positional stream
        — every demand a firing makes reaches the executor's
        vocabulary-addressed decision channel (per-(vocab, what) FIFO /
        ask-time provider), so a trigger the op itself armed mid-drain is
        answerable exactly like one that was already pending."""
        fired = 0
        while self.world.triggers:
            if fired >= MAX_TRIGGER_FIRES:
                raise RuntimeError(
                    "executor: trigger-loop tripwire — one drain resolved "
                    f"{MAX_TRIGGER_FIRES} triggers and the queue is still "
                    "growing (self-retriggering loop: flag it, never run it)"
                )
            instance = self._pop_next()
            payload = self.firings.pop(instance.clock, None)
            if payload is None:  # pragma: no cover - instances only via _queue
                continue
            self._fire(payload)
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
        """One trigger resolution: the condition gate, then the effect.
        May-offers ask the executor's decision stream (14b, B-4)."""
        event = payload.event
        ctx = self._ctx(payload.source, payload.controller, event)
        node = payload.node
        if node.condition is not None:
            subject = event.subject if event.subject is not None else payload.source
            if not eval_filter(node.condition, subject, ctx):
                return
        # The 12a shared effect runner — the SAME dispatch execute() uses,
        # journalled at its Atom boundaries by the Executor.
        self.executor._run_effect(node.effect, ctx)

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
        amount = event.amount if event.kind == KIND_DAMAGE else None
        return ExecCtx(
            world=ex.world,
            ledger=ex.ledger,
            controller=controller,
            source=source,
            bindings=dict(bindings),
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
        return (("attached", attached), ("delayed", delayed), ("emblems", emblems))
