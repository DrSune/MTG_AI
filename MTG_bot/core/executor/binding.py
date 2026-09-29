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

May-offers: an ``OptionalEffect`` in a trigger effect consumes the drain's
``decisions`` (``"fire"``/``"skip"``, C15) in APNAP fire order — the 12b
stand-in for 12c's Slate, pinned deterministic by the replay test.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from MTG_bot.core.ability_tree import (
    BecomesBlockedEvent,
    CardDrawnEvent,
    CardRecord,
    CastSpellEvent,
    CombatDamageEvent,
    ControllerRef,
    CounterPlacedEvent,
    CreatureDiesEvent,
    DamageDealtEvent,
    DeclareAttackersEvent,
    DeclareBlockersEvent,
    DelayedTrigger,
    EventSpec,
    FAnd,
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
    KIND_COUNTER_PLACED,
    KIND_CREATURE_DIES,
    KIND_DAMAGE,
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

# EventSpec kinds with no emitter before the combat/cast/target phases.
# Binding one RAISES — flag, don't degrade.
_UNSUPPORTED_EVENTS: dict[type, str] = {
    CastSpellEvent: "outside 12b scope (casting is stack work, later phase)",
    DeclareAttackersEvent: "later phase (combat)",
    DeclareBlockersEvent: "later phase (combat)",
    CombatDamageEvent: "later phase (combat)",
    BecomesBlockedEvent: "later phase (combat)",
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
        self.firings: dict[int, _Firing] = {}
        self.delayed: list[DelayedBinding] = []
        self._seen_journal_len = 0
        self._seq = 0

    # ------------------------------------------------------------ attach

    @property
    def world(self) -> GameWorld:
        return self.executor.world

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
        self.executor.layers.attach_source(handle, record)
        self.executor.replacements.attach_source(handle, record)
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
            if event.source is not None:
                raise NotImplementedError(
                    f"executor: {card_name} DamageDealtEvent source filter is "
                    "later phase (C-4 damage-source surface)"
                )
            if event.combat is True:
                raise NotImplementedError(
                    f"executor: {card_name} combat-damage scope is later phase (combat)"
                )

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
                    ability.event, event, handle, self.world.controller_of(handle)
                ):
                    self._queue(
                        handle, self.world.controller_of(handle), ability, event
                    )
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
        if kind == KIND_DAMAGE and isinstance(node, DamageDealtEvent):
            return self._match_damage(node, event, source, controller)
        if kind == KIND_LIFE_GAINED and isinstance(node, LifeGainedEvent):
            assert event.subject is not None  # the gaining player
            ctx = self._match_ctx(source, controller, event)
            return controller_matches(node.controller, event.subject, ctx)
        return False  # no subscriber shape for this journalled kind

    def _match_ctx(
        self, source: Handle, controller: Handle, event: GameEvent
    ) -> ExecCtx:
        return self._ctx(source, controller, event, decisions=())

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
        if subject is not None and subject.namespace == "player":
            if not _is_universal(node.filter):
                raise NotImplementedError(
                    "executor: DamageDealtEvent filter over a player subject "
                    "is 12c's query surface"
                )
            return True
        assert subject is not None  # a damage event always names its subject
        return eval_filter(node.filter, subject, ctx)

    # -------------------------------------------------------------- fire

    def fire_all(self, decisions: Sequence[str] = ()) -> int:
        """Drain the world's trigger queue: APNAP order_key, then
        ``str(source)`` then bind-seq (Handle-sort within a seat, ruling 5).
        Every firing runs through the 12a effect runner, whose journalled
        events queue the next batch; loop until empty or the tripwire
        raises. ``decisions`` is consumed across the whole drain in fire
        order (C15): each may-offer takes the next ``fire``/``skip``."""
        cursor = 0
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
            cursor += self._fire(payload, decisions, cursor)
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

    def _fire(self, payload: _Firing, decisions: Sequence[str], cursor: int) -> int:
        """One trigger resolution: the condition gate, then the effect (its
        may-offers consume decisions here). Returns decisions consumed."""
        event = payload.event
        ctx = self._ctx(payload.source, payload.controller, event, decisions[cursor:])
        node = payload.node
        if node.condition is not None:
            subject = event.subject if event.subject is not None else payload.source
            if not eval_filter(node.condition, subject, ctx):
                return ctx.decision_idx
        # The 12a shared effect runner — the SAME dispatch execute() uses,
        # journalled at its Atom boundaries by the Executor.
        self.executor._run_effect(node.effect, ctx)
        return ctx.decision_idx

    def _ctx(
        self,
        source: Handle,
        controller: Handle,
        event: GameEvent,
        decisions: Sequence[str],
    ) -> ExecCtx:
        ex = self.executor
        bindings: dict[str, Handle] = {}
        if event.subject is not None:
            bindings["event"] = event.subject
            if event.kind == KIND_CREATURE_DIES:
                bindings["result"] = event.subject  # C18 was-snapshot subject
        amount = event.amount if event.kind == KIND_DAMAGE else None
        return ExecCtx(
            world=ex.world,
            ledger=ex.ledger,
            controller=controller,
            source=source,
            bindings=dict(bindings),
            decisions=tuple(decisions),
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
        return (("attached", attached), ("delayed", delayed))
