"""Replacement effects + pre-application prevention records.

Two veto-shaped vocabularies live here, both keyed on the journal's event
shapes and both fingerprint-dumped:

  * :class:`ReplacementRecord` — a compiled :class:`ReplacementAbility`
    node attached to a battlefield permanent, or to a resolving spell for
    the rest of the turn (canonical row: Nine Lives, whose template says
    "prevent that damage and put an incarnation counter on this
    enchantment" — the grammar carries the PREVENTION inside the
    replacement's action position, no PREVENT atom). The damage
    interceptor runs in :func:`~MTG_bot.core.executor.verbs._v_deal_damage`
    BEFORE the world mutation: a matching live replacement consumes the
    damage-to-a-player event (no life change happens, so the journal emits
    no DAMAGE row and nothing downstream can mis-fire), appends a
    ``("DAMAGE_REPLACED", …)`` audit row, and runs the replacement's ACTION
    as a nested journalled effect through the executor (the incarnation
    counter lands as a normal journalled PUT_COUNTER, arming Nine Lives' own
    HAS_COUNTER-9 exile trigger); a quantity rewrite (Fiery Emancipation)
    modifies the amount in place instead. The life-gain, draw, counter,
    death and zone-change lanes consume their events the same way.
    "First N times"-style partial replacements (a bounded event ``amount``)
    RAISE: the closed vocabulary models the cap as a trigger, not as a
    number on the replacement, and the executor does not guess caps.

  * :class:`PreventionRecord` — a PREVENT_EFFECT, from the verb or a static
    ability (the Capture Sphere / Faith's Fetters / Frost Breath family). A
    veto-before-application record: condition + event spec + optional step
    + duration. Consumers: the untap step
    (:meth:`ReplacementRegistry.prevents_untap` — the Frost Breath freeze —
    and :meth:`ReplacementRegistry.prevents_phase_in`, Teferi, Timeless
    Voyager's "they can't phase in"),
    card damage, counter placement, the attack/block declarations,
    activation (legality's ``ability_playable`` through
    :meth:`ReplacementRegistry.prevents_activation`) and countering.

Matching rules (documented, pinned): the player-subject filter of a
DamageDealtEvent replacement is read with the PLAYER as subject —
``CONTROLLER_IS YOU`` means "this damage is about to hit YOU", the CR's
damaged-object reading; other preds raise (flag, never guess). A
prevention's IR condition/event-filter is materialized to its affected
set at the register boundary (IS_ANY_TARGET = the designated targets), so
the untap tick needs no re-evaluation of cast-time anaphora.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from MTG_bot.core.ability_tree import (
    QX,
    AbilityActivatedEvent,
    Atom,
    CardDrawnEvent,
    ControllerRef,
    CounteredEvent,
    CounterKind,
    CounterPlacedEvent,
    CreatureDiesEvent,
    DamageDealtEvent,
    DeclareAttackersEvent,
    DeclareBlockersEvent,
    Duration,
    DurationEot,
    DurationUntilEndOfNextTurn,
    DurationUntilLeaves,
    DurationUntilNextStep,
    DurationUntilNextTurn,
    DurationWhileCondition,
    Effect,
    EventSpec,
    FAnd,
    FAtom,
    FAtomPred,
    Filter,
    FNot,
    FOr,
    LifeGainedEvent,
    PhasingEvent,
    QAtLeast,
    Quantity,
    QUnbounded,
    ReplacementAbility,
    Seq,
    StaticAbility,
    Step,
    TapStateEvent,
    Verb,
    Zone,
    ZoneChangeEvent,
    ZoneKind,
    activation_matches_kind,
)
from MTG_bot.core.executor.decisions import site_digest
from MTG_bot.core.executor.durations import duration_tag
from MTG_bot.core.executor.quantity import ExecCtx, eval_filter, resolve
from MTG_bot.core.executor.selectors import (
    ZONE_KIND_TO_STATE,
    _filter_names_the_source,
    controller_matches,
)
from MTG_bot.core.identity import Handle

if TYPE_CHECKING:  # pragma: no cover - typing-only
    from MTG_bot.core.compiler.compiler import CardRecord
    from MTG_bot.core.executor import Executor


@dataclass
class ReplacementRecord:
    """One compiled ReplacementAbility node while its source is attached
    (a resolving spell's: until end of turn, ``tag="Eot"``).
    The duration fields (``tag``/``duration``) stay on the shape because
    both registry kinds share the expiry API; node replacements are
    battlefield-lifetime (``tag="Permanent"``, the detach expires them)."""

    seq: int
    source: Handle
    controller: Handle
    event: EventSpec
    action: Effect
    tag: str = "Permanent"
    duration: Duration | None = None
    condition: Filter | None = None
    status: str = "live"  # live | expired
    # Scorching Dragonfire: the cast's designation snapshot, taken
    # when a SPELL-sourced (Eot) record registers. The record outlives the
    # resolution's ExecCtx, but its event filter (IS_ANY_TARGET "that
    # creature") still MEANS the designation — the PreventionRecord
    # ``_rec_ctx`` convention, extended to the replacement lane so the
    # dies window stays scoped to the object the spell named (CR 614.1:
    # the replacement applies to the event it was set up for).
    designated: tuple[Handle, ...] = ()


@dataclass
class PreventionRecord:
    """One PREVENT_EFFECT record: event veto + step + affected set.

    ``resolved``: a resolving spell or ability made it (the PREVENT_EFFECT verb), not a static
    ability. CR 611.2a: it lasts as long as its duration says, whatever happens to its source;
    a static carrier works only while its source is on the battlefield."""

    seq: int
    source: Handle
    controller: Handle
    event: EventSpec
    step: Step | None
    targets: tuple[Handle, ...]
    tag: str = "Permanent"
    duration: Duration | None = None
    condition: Filter | None = None
    status: str = "live"  # live | expired
    resolved: bool = False


class ReplacementRegistry:
    """The replacement + prevention registry owned by one
    :class:`~MTG_bot.core.executor.Executor`."""

    def __init__(self, executor: Executor) -> None:
        self.executor = executor
        self.replacements: list[ReplacementRecord] = []
        self.preventions: list[PreventionRecord] = []
        self._seq = 0

    @property
    def world(self):
        return self.executor.world

    # ------------------------------------------------------------ lifecycle

    def attach_source(self, handle: Handle, record: CardRecord) -> int:
        """Register the permanent's ReplacementAbility nodes (lifetime:
        while attached — the binder's detach expires them)."""
        self.detach_source(handle)
        count = 0
        for node in record.abilities:
            if isinstance(node, ReplacementAbility):
                self._seq += 1
                self.replacements.append(
                    ReplacementRecord(
                        seq=self._seq,
                        tag="Permanent",
                        duration=None,
                        condition=node.condition,
                        status="live",
                        source=handle,
                        controller=self.executor.controller_of(handle),
                        event=node.event,
                        action=node.action,
                    )
                )
                count += 1
        return count

    def detach_source(self, handle: Handle) -> int:
        expired = 0
        for rec in self.replacements:
            if rec.source == handle and rec.status != "expired":
                rec.status = "expired"
                expired += 1
        for rec in self.preventions:
            if rec.source == handle and rec.status != "expired" and not rec.resolved:
                rec.status = "expired"
                expired += 1
        return expired

    def follow_controller(self, handle: Handle, controller: Handle) -> None:
        """``handle`` changed controller on the battlefield: its own replacement and prevention
        abilities now read "you" as ``controller`` (CR 109.5, 611.3a; a stolen Blightbeetle bars
        counters from the creatures of its new controller's opponents). A record a resolved
        spell or ability made keeps the controller it resolved under (CR 611.2c): the
        ``resolved`` preventions and the spell-sourced Eot replacements."""
        for rec in self.replacements:
            if rec.source == handle and rec.tag == "Permanent" and rec.status != "expired":
                rec.controller = controller
        for rec in self.preventions:
            if rec.source == handle and not rec.resolved and rec.status != "expired":
                rec.controller = controller

    def register_ephemeral_replacements(
        self,
        source: Handle,
        controller: Handle,
        record: CardRecord,
        designated: tuple[Handle, ...] = (),
    ) -> int:
        """A RESOLVING INSTANT/SORCERY's ReplacementAbility nodes. A spell
        never attaches (it hits the graveyard), so the
        battlefield lifecycle that normally registers replacements never
        sees it — yet the grammar carries the corpus' turn-shaped replacement
        idiom ("If that creature or planeswalker would die this turn, exile
        it instead": Scorching Dragonfire, Obliterating Bolt) as a card-level
        ReplacementAbility on the spell itself. Registering at resolution
        start (stack.py) with an Eot tag is the honest home: the effect is
        live from resolution to end of turn, expires in the EOT sweep, and
        never survives the window its own text names."""
        count = 0
        for node in record.abilities:
            if isinstance(node, ReplacementAbility):
                self._seq += 1
                self.replacements.append(
                    ReplacementRecord(
                        seq=self._seq,
                        tag="Eot",
                        duration=DurationEot(),
                        condition=node.condition,
                        status="live",
                        source=source,
                        controller=controller,
                        event=node.event,
                        action=node.action,
                        designated=designated,  # the cast's designation
                        # rides the record — the dies window must stay
                        # scoped to the object the spell named (CR 614.1)
                    )
                )
                count += 1
        return count

    def register_prevention(
        self,
        source: Handle,
        controller: Handle,
        condition: Filter | None,
        event: EventSpec,
        step: Step | None,
        duration: Duration | None,
        targets: tuple[Handle, ...],
        resolved: bool = False,
    ) -> PreventionRecord:
        """The PREVENT_EFFECT verb's runtime registration (targets already
        materialized from the cast's designated set, ``resolved`` True), and a
        static carrier's (layers._new_static)."""
        self._seq += 1
        rec = PreventionRecord(
            seq=self._seq,
            tag=duration_tag(duration),
            duration=duration,
            condition=condition,
            status="live",
            source=source,
            controller=controller,
            event=event,
            step=step,
            targets=targets,
            resolved=resolved,
        )
        self.preventions.append(rec)
        return rec

    # -------------------------------------------------------------- matching

    def _source_alive(self, source: Handle) -> bool:
        """The battlefield-lifetime gate of a permanent's own replacement and
        prevention records. A phased-out source does not exist (CR 702.26b),
        so its static records do not apply until it phases in."""
        world = self.world
        return (
            source in world.cards
            and world.zone_of(source).kind == "battlefield"
            and source not in self.executor.phased_out
        )

    def _condition_holds(self, rec, subject: Handle, ctx: ExecCtx) -> bool:
        """A record's condition is judged over the EVENT SUBJECT (the
        TriggeredAbility convention the frozen grammar shares with
        replacements/preventions); the WHILE duration's filter is a state
        predicate over the source (StaticAbility convention). Callers pass
        live records only."""
        if isinstance(rec.duration, DurationWhileCondition):
            if not self._source_alive(rec.source):
                return False
            if not eval_filter(rec.duration.filter, rec.source, ctx):
                return False
        if rec.condition is not None:
            return eval_filter(rec.condition, subject, ctx)
        return True

    @staticmethod
    def _player_filter_matches(filter_: Filter, victim: Handle, ctx: ExecCtx) -> bool:
        """A DamageDealtEvent filter over a PLAYER subject (CR: the event's
        subject is the damaged object): only the ControllerRef-bearing
        ``CONTROLLER_IS`` atom (and the boolean nodes / the universal FAnd)
        have a meaning over a player — everything else RAISES."""
        if isinstance(filter_, FAnd):
            return all(
                ReplacementRegistry._player_filter_matches(c, victim, ctx)
                for c in filter_.children
            )
        if isinstance(filter_, FOr):
            return any(
                ReplacementRegistry._player_filter_matches(c, victim, ctx)
                for c in filter_.children
            )
        if isinstance(filter_, FNot):
            return not ReplacementRegistry._player_filter_matches(
                filter_.inner, victim, ctx
            )
        if isinstance(filter_, FAtom) and filter_.who is not None:
            return controller_matches(filter_.who, victim, ctx)
        raise NotImplementedError(
            "executor: damage-replacement filter over a player subject must "
            "name a ControllerRef (got " + type(filter_).__name__ + ") — 12e"
        )

    @staticmethod
    def _is_player_only_filter(filter_: Filter) -> bool:
        """Is a DamageDealtEvent filter pure PLAYER-COORDINATE — a predicate
        whose only meaning is "the damaged object IS a named seat"? A bare
        ``CONTROLLER_IS YOU`` on a damage event reads as the CR's damaged-object
        idiom "this damage is about to hit YOU" (Nine Lives), so such a
        record never reaches the CARD lane; a filter carrying even one
        card-shape leaf (TYPE_EQ ...) is read over the damaged object by
        ``eval_filter`` (and its CONTROLLER_IS leaves then mean "a card
        YOU control" — the quantity.py card branch). A universal node
        (the empty FAnd Fiery Emancipation compiles to) is NOT player-
        only: it matches every subject, both lanes. Unknown node shapes
        are NOT player-only — they fall through to eval_filter's own
        flag-raise rather than being silently excluded."""
        if isinstance(filter_, FAtom):
            return filter_.pred.name == "CONTROLLER_IS" and filter_.who is not None
        if isinstance(filter_, FAnd):
            return bool(filter_.children) and all(
                ReplacementRegistry._is_player_only_filter(c) for c in filter_.children
            )
        if isinstance(filter_, FOr):
            return bool(filter_.children) and all(
                ReplacementRegistry._is_player_only_filter(c) for c in filter_.children
            )
        if isinstance(filter_, FNot):
            return ReplacementRegistry._is_player_only_filter(filter_.inner)
        return False

    def replacements_for_damage(
        self,
        ctx: ExecCtx,
        victim: Handle,
        dealer: Handle,
        amount: int,
        combat: bool,
    ) -> list[tuple[ReplacementRecord, int | None]]:
        """The apply-pipeline interceptor for a DAMAGE event, both lanes
        (player and card), before the damage applies.
        Returns the replacements that apply, in the order they apply, each
        ``(record, None)`` when the record CONSUMES the event (the Nine Lives
        doctrine — the damage never applies, the action runs in the drain)
        or ``(record, new_amount)`` when it MODIFIES the event's quantity in
        place (the Fiery Emancipation idiom: the action is a DEAL_DAMAGE
        whose amount quantity rewrites the event's —
        ``QBin(MUL, 3, QProp(event, AMOUNT))`` — so exactly one journalled
        DAMAGE row lands, dealer attribution and lifelink stay on the dealt
        amount, and the action itself is never executed). A
        consume is always last: nothing is left to replace. Empty when
        nothing applies.

        CR 616.1: when two or more records apply, the
        affected player or the controller of the affected permanent chooses
        one (:meth:`_choose`); it applies, then the records that still apply
        are checked again, until none is left (616.1e-f). Each record applies
        to the event once (CR 614.5). A record whose action re-queues damage
        cannot self-replace: the drain's CR 614.4a ``replaced_seq`` guard
        covers the consume half, and the modify half never executes an
        action. The matching is :meth:`_damage_matches`."""
        applied: list[tuple[ReplacementRecord, int | None]] = []
        while True:
            used = {rec.seq for rec, _amount in applied}
            options = [
                (rec, self._damage_rewrite(rec, ctx, victim, amount))
                for rec in self._damage_matches(ctx, victim, dealer, combat)
                if rec.seq not in used
            ]
            if not options:
                return applied
            rec, new_amount = self._choose(ctx, victim, options)
            applied.append((rec, new_amount))
            if new_amount is None:
                return applied  # consumed: the event no longer happens
            amount = new_amount

    def _damage_matches(
        self, ctx: ExecCtx, victim: Handle, dealer: Handle, combat: bool
    ) -> list[ReplacementRecord]:
        """The live DamageDealtEvent records that apply to damage from
        ``dealer`` to ``victim``, in record order.

        The event's slots read as matchers over the about-to-happen event:
        ``amount`` accepts the two no-constraint idioms (QUnbounded "all",
        QX the compiler's amount placeholder) and flags the first-N cap
        (caps are counters + triggers, never guessed); ``combat`` True
        is the standing later-phase flag, False scopes to non-combat;
        ``source`` is a Filter over the DEALER, evaluated in the record's
        coordinates (the CONTROLLER_IS card branch resolves a spell
        handle through the zone-owner controller_of — the caster).
        CONTROLLER RULE as in every other lane: every predicate is judged
        in the RECORD's own coordinates. Nothing here reads the amount, so
        a modification never changes which records apply."""
        matches: list[ReplacementRecord] = []
        for rec in sorted(self.replacements, key=lambda r: r.seq):
            event = rec.event
            if not isinstance(event, DamageDealtEvent):
                continue
            if event.combat is True:
                raise NotImplementedError(
                    "executor: combat-damage replacement is later phase (combat)"
                )
            if not isinstance(event.amount, (QUnbounded, QX)):
                raise NotImplementedError(
                    "executor: bounded damage-replacement caps ('the first "
                    "N') are modeled as counters + triggers, not guessed "
                    "here (12e)"
                )
            if rec.status != "live" or rec.seq in ctx.replaced_seq:
                continue
            if event.combat is False and combat:
                continue
            if rec.tag == "Permanent" and not self._source_alive(rec.source):
                continue
            rec_ctx = replace(ctx, source=rec.source, controller=rec.controller)
            if victim.namespace == "player":
                if not self._player_filter_matches(event.filter, victim, rec_ctx):
                    continue
            else:
                if self._is_player_only_filter(event.filter):
                    continue  # "to you" — the player idiom skips the card lane
                if not eval_filter(event.filter, victim, rec_ctx):
                    continue
            if event.source is not None and not eval_filter(
                event.source, dealer, rec_ctx
            ):
                continue
            if not self._condition_holds(rec, victim, rec_ctx):
                continue
            matches.append(rec)
        return matches

    @staticmethod
    def _damage_rewrite(
        rec: ReplacementRecord, ctx: ExecCtx, victim: Handle, amount: int
    ) -> int | None:
        """What ``rec`` does to an event of ``amount`` damage to ``victim``:
        the new amount when its action is the DEAL_DAMAGE quantity rewrite
        (the Fiery idiom), None when it consumes the event."""
        if not (isinstance(rec.action, Atom) and rec.action.verb is Verb.DEAL_DAMAGE):
            return None
        quantity = rec.action.args.get("amount")
        if quantity is None:
            raise NotImplementedError(
                "executor: a DEAL_DAMAGE replacement action without an "
                "amount slot is not the Fiery idiom (flag, not guess)"
            )
        assert isinstance(quantity, Quantity)
        # the record's own coordinates, plus the event register the action's
        # QProp(event, AMOUNT) reads and the victim bound as ``event``.
        ev_ctx = replace(
            ctx,
            source=rec.source,
            controller=rec.controller,
            bindings={"event": [victim]},
            event_amount=amount,
        )
        return max(0, resolve(quantity, ev_ctx))

    def _choose(
        self,
        ctx: ExecCtx,
        affected: Handle,
        options: list[tuple[ReplacementRecord, int | None]],
    ) -> tuple[ReplacementRecord, int | None]:
        """CR 616.1: the affected player, or the controller of the affected
        permanent, chooses which applicable replacement applies next. Only
        choices with a consequence are asked (AGENTS §10, no phantom asks):

        - When a consuming option applies, the modifications do not matter:
          the consume still applies after any of them (matching never reads
          the amount) and its action never reads the amount (the executor
          drain runs it without the event). So only the consumes are options,
          each its own, because its action runs at its own source (which Nine
          Lives gets the counter).
        - Otherwise, options that modify the event the same way are one
          option: the same rewrite (action, event, condition, controller)
          giving the same new amount, as two Fiery Emancipations do.

        With one option left it applies without an ask; otherwise the decider
        is asked under ``replace:<seat>:<digest>``, the vocabulary being the
        options' sources in record order."""
        consumes = [(rec, new_amount) for rec, new_amount in options if new_amount is None]
        if consumes:
            options = consumes
        choices: list[tuple[ReplacementRecord, int | None]] = []
        for rec, new_amount in options:
            if new_amount is not None and any(
                other_amount == new_amount
                and (other.action, other.event, other.condition, other.controller)
                == (rec.action, rec.event, rec.condition, rec.controller)
                for other, other_amount in choices
            ):
                continue
            choices.append((rec, new_amount))
        if len(choices) == 1:
            return choices[0]
        decider = (
            affected
            if affected.namespace == "player"
            else self.executor.controller_of(affected)
        )
        vocab = tuple(str(rec.source) for rec, _amount in choices)
        if len(set(vocab)) != len(vocab):
            raise NotImplementedError(
                "executor: two applicable damage replacements share a source, so "
                "the CR 616.1 choice has no vocabulary for them (no card does this)"
            )
        answer = ctx.take_decision_of(
            decider, vocab, f"replace:{decider}:{site_digest(vocab)}"
        )
        return choices[vocab.index(answer)]

    def prevented_card_damage(
        self, ctx: ExecCtx, victim: Handle, combat: bool
    ) -> PreventionRecord | None:
        """The prevention-before-apply interceptor for damage a CARD would
        be dealt (Pack Leader's "prevent all combat damage ... Dogs" half).
        combat-scope mirrors the binding-side DamageDealtEvent matcher:
        ``combat=True`` matches combat damage only, ``False`` only the
        rest, ``None`` anything. QUnbounded
        amount prevents ALL; the first-N cap flags (never guesses).
        CONTROLLER RULE as in the damage hook: every predicate is judged
        in the record's own coordinates (source=the preventing object,
        controller=its controller)."""
        for rec in sorted(self.preventions, key=lambda r: r.seq):
            if rec.status != "live":
                continue
            event = rec.event
            if not isinstance(event, DamageDealtEvent):
                continue
            if event.source is not None:
                raise NotImplementedError(
                    "executor: damage-prevention source filter is later "
                    "phase (C-4 damage surface)"
                )
            if event.combat is not None and event.combat != combat:
                continue
            if event.amount is not None and not isinstance(event.amount, QUnbounded):
                raise NotImplementedError(
                    "executor: bounded damage-prevention caps ('the first "
                    "N') are modeled as counters + triggers, not guessed "
                    "here (12e)"
                )
            if rec.targets and victim not in rec.targets:
                continue
            if not rec.resolved and not self._source_alive(rec.source):
                continue  # a static carrier works while its source is there (CR 611.2a)
            rec_ctx = replace(ctx, source=rec.source, controller=rec.controller)
            if event.filter is not None and not eval_filter(
                event.filter, victim, rec_ctx
            ):
                continue
            if not self._condition_holds(rec, victim, rec_ctx):
                continue
            return rec
        return None

    def replacement_for_life_gained(
        self, ctx: ExecCtx, player: Handle
    ) -> ReplacementRecord | None:
        """The apply-pipeline interceptor for a LIFE-GAINED event
        (replacement before apply, mirrored from the damage hook). The
        subject of a LifeGainedEvent is the gaining player, so the record's
        condition is judged over the PLAYER handle.
        CONTROLLER RULE as in the damage lane: every predicate is judged
        in the record's own coordinates.

        The CR 614.4a loop guard lives in ``ctx.replaced_seq``: a record
        already applied in this event chain is skipped, so the replacement
        action's own life gain cannot be re-replaced by the same effect.
        A permanent-sourced record must still be on the battlefield; the
        spell-sourced (Eot) half of the grammar's idiom is deliberately
        exempt — the spell has resolved and moved on."""
        for rec in sorted(self.replacements, key=lambda r: r.seq):
            event = rec.event
            if not isinstance(event, LifeGainedEvent):
                continue
            if rec.status != "live" or rec.seq in ctx.replaced_seq:
                continue
            if event.actor != FAtom(
                pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU
            ):
                raise NotImplementedError(
                    "executor: LifeGainedEvent with a non-YOU actor "
                    "reference is not in the corpus (flag, not guess)"
                )
            if player != rec.controller:
                continue  # "you" means the REPLACEMENT's controller
            if rec.tag == "Permanent" and not self._source_alive(rec.source):
                continue
            rec_ctx = replace(ctx, source=rec.source, controller=rec.controller)
            if not self._condition_holds(rec, player, rec_ctx):
                continue
            return rec
        return None

    def replacement_for_card_draw(
        self, ctx: ExecCtx, drawer: Handle
    ) -> ReplacementRecord | None:
        """Teferi's Ageless Insight: the apply-pipeline interceptor
        for a CARD-DRAW event (replacement before apply, mirrored from
        the life lane — the draw never touches the library, so the journal
        sees no CARD_DRAWN row for it, and the replacement's DRAW action
        runs in the drain with the record's coordinates; the CR 614.4a
        guard in ``ctx.replaced_seq`` stops the action's own draw from
        re-arming the same record, while a second carrier chains exactly
        as the CR's sequential-replacement reading demands).

        The subject of a CardDrawnEvent is the drawn card, which does not
        exist yet at the consult — the PLAYER-coordinate condition
        (NOT_FIRST_DRAW_THIS_STEP, judged over the drawer) is what the
        corpus carries, so the drawer handle serves as subject. The
        ``ordinal`` slot ("whenever you draw your second card") belongs to
        the TRIGGER table (Mystic Skyfish reads the journalled per-turn
        count there); a draw REPLACEMENT naming one has no corpus carrier
        — the raise, never a silent ignore. CONTROLLER RULE as in the
        other lanes: the condition is judged in the record's coordinates,
        and "you" is the REPLACEMENT's controller."""
        for rec in sorted(self.replacements, key=lambda r: r.seq):
            event = rec.event
            if not isinstance(event, CardDrawnEvent):
                continue
            if rec.status != "live" or rec.seq in ctx.replaced_seq:
                continue
            if event.actor != FAtom(
                pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU
            ):
                raise NotImplementedError(
                    "executor: CardDrawnEvent replacement with a non-YOU "
                    "actor reference is not in the corpus (flag, not "
                    "guess)"
                )
            if drawer != rec.controller:
                continue  # "you" means the REPLACEMENT's controller
            if event.ordinal is not None:
                raise NotImplementedError(
                    "executor: ordinal-scoped draw replacement has no "
                    "consumer (the corpus carries ordinals on triggers "
                    "only)"
                )
            if rec.tag == "Permanent" and not self._source_alive(rec.source):
                continue
            rec_ctx = replace(ctx, source=rec.source, controller=rec.controller)
            if not self._condition_holds(rec, drawer, rec_ctx):
                continue
            return rec
        return None

    def prevents_counter_placement(
        self, ctx: ExecCtx, card: Handle, kind: CounterKind
    ) -> PreventionRecord | None:
        """Can ``card`` not have ``kind`` counters put on it? Blightbeetle's "Creatures your
        opponents control can't have +1/+1 counters put on them" registers a PREVENT_EFFECT
        record over a CounterPlacedEvent; this is its consumer, consulted wherever counters
        are put (the PUT_COUNTER verb, and the counters a permanent enters with, CR 122.6).
        Judged in the record's coordinates like the other consults: the event's filter and the
        record's condition over the receiving card, "opponents" relative to the record's
        controller. A static carrier works while its source is on the battlefield; a resolved
        record over designated objects covers those objects. A count slot on a prevention has
        no carrier: the raise, never a guess."""
        for rec in sorted(self.preventions, key=lambda r: r.seq):
            event = rec.event
            if rec.status == "expired" or not isinstance(event, CounterPlacedEvent):
                continue
            if event.counter_kind is not kind:
                continue
            if event.count is not None:
                raise NotImplementedError(
                    "executor: a counter-placement prevention with a count slot has no "
                    "carrier (flag, never guess)"
                )
            if rec.targets and card not in rec.targets:
                continue
            if not rec.resolved and not self._source_alive(rec.source):
                continue
            rec_ctx = replace(ctx, source=rec.source, controller=rec.controller)
            if not eval_filter(event.filter, card, rec_ctx):
                continue
            if not self._condition_holds(rec, card, rec_ctx):
                continue
            return rec
        return None

    def replacement_for_counter_placement(
        self,
        ctx: ExecCtx,
        card: Handle,
        kind: CounterKind,
        amount: int,
    ) -> ReplacementRecord | None:
        """Conclave Mentor: the apply-pipeline interceptor for a
        COUNTER-PLACEMENT event (replacement before apply): the PUT-
        COUNTER verb consults this per receiving card BEFORE the counter
        ledger is touched; a match consumes the placement (no counters
        land, so the state diff emits no COUNTER_PLACED row for it) and
        the action runs in the drain with the receiving card bound as
        ``event`` and the placed count published into
        ``event_counter_count`` — the register the action's
        ``QProp(event, COUNTER_COUNT)`` ("that many plus one") reads,
        where the card's accumulated counters would be the wrong answer.
        The CR 614.4a guard lets a SECOND carrier chain: the first
        action's placement re-consults and the second record sees the
        rewritten count (two Mentors make a +1 a +3, CR-correct through
        the same drain the single carrier uses).

        The event's ``count`` slot is the "one or more" matcher
        (QAtLeast(1), the grammar's idiom): n >= 1 satisfies it;
        QUnbounded matches any placement. Any other shape is a cap the
        executor does not guess. The subject filter ("a creature
        you control") is a CARD-shape predicate, judged over the
        receiving card in the RECORD's coordinates — CONTROLLER RULE."""
        for rec in sorted(self.replacements, key=lambda r: r.seq):
            event = rec.event
            if not isinstance(event, CounterPlacedEvent):
                continue
            if rec.status != "live" or rec.seq in ctx.replaced_seq:
                continue
            if event.counter_kind is not kind:
                continue
            count = event.count
            if isinstance(count, QAtLeast):
                if amount < count.n:
                    continue
            elif not isinstance(count, (QUnbounded, QX, type(None))):
                raise NotImplementedError(
                    "executor: bounded counter-placement replacement caps "
                    "are modeled as counters + triggers, not guessed here "
                    "(12e shape rule)"
                )
            if rec.tag == "Permanent" and not self._source_alive(rec.source):
                continue
            rec_ctx = replace(ctx, source=rec.source, controller=rec.controller)
            if not eval_filter(event.filter, card, rec_ctx):
                continue
            if not self._condition_holds(rec, card, rec_ctx):
                continue
            return rec
        return None

    def replacement_for_death(self, card: Handle) -> ReplacementRecord | None:
        """Scorching Dragonfire: the state-check interceptor for a
        CREATURE-DIES event — the die lane mirrors the damage/life hooks
        (replacement before apply): the SBA loop consults this BEFORE
        moving the creature to the graveyard, and a match consumes the
        death (no graveyard move, no CREATURE_DIES journal row — see the
        documented gap in the executor's state-check drain).

        Both dying lanes of the SBA sweep consult it, the lethal
        creature AND the zero-loyalty planeswalker (CR 704.5i: both are put
        into a graveyard from the battlefield, which is dying, CR 700.4).
        The record's filter decides which dying object it covers, e.g.
        Obliterating Bolt's "that creature or planeswalker" (IS_ANY_TARGET).

        CONTROLLER RULE as in the other lanes: every predicate is judged
        in the RECORD's coordinates (the ``_rec_ctx`` convention). The
        spell-sourced record's anaphora ("that creature" — IS_ANY_TARGET)
        reads the designation snapshot the record carries, and the dead
        card is bound as ``event`` so the replacement's ACTION (EXILE
        referent=event) resolves. A Permanent-sourced record must still be
        on the battlefield; the Eot half is exempt (the spell has
        resolved)."""
        for rec in sorted(self.replacements, key=lambda r: r.seq):
            event = rec.event
            if not isinstance(event, CreatureDiesEvent):
                continue
            if rec.status != "live":
                continue
            if rec.tag == "Permanent" and not self._source_alive(rec.source):
                continue
            rec_ctx = self.executor._ctx(
                source=rec.source,
                controller=rec.controller,
                bindings={"target": list(rec.designated), "event": [card]},
                decisions=(),
            )
            if not eval_filter(event.filter, card, rec_ctx):
                continue
            if not self._condition_holds(rec, card, rec_ctx):
                continue
            return rec
        return None

    def _endpoint_matches(
        self,
        zone_ir: Zone | None,
        state_kind: str | None,
        card: Handle,
        ctx: ExecCtx,
    ) -> bool:
        """One ZoneChangeEvent endpoint vs the about-to-happen move — the
        binding-side ``_zone_matches`` convention, so the trigger lane and
        the replacement lane read endpoints alike:
        ANY matches, a created object's missing ``from`` matches ANY, and
        OWNER scopes to the card's owner (who in this frozen model is
        exactly the zone owner)."""
        if zone_ir is None or zone_ir.kind is ZoneKind.ANY:
            return True
        want = ZONE_KIND_TO_STATE.get(zone_ir.kind)
        if want is None or state_kind is None or want != state_kind:
            return False
        ref = zone_ir.controller
        if ref is ControllerRef.ANY or ref is ControllerRef.OWNER:
            return True
        return controller_matches(ref, self.world.controller_of(card), ctx)

    def replacement_for_zone_change(
        self,
        card: Handle,
        from_state: str | None,
        to_state: str,
        replaced_seq: frozenset[int] = frozenset(),
    ) -> ReplacementRecord | None:
        """Containment Priest: the apply-pipeline interceptor for a
        ZONE-CHANGE event — the enter lane mirrors the death hook
        (replacement before apply): ``_v_move_zone`` consults this
        BEFORE the battlefield move, and a match consumes the enter (no
        battlefield placement; the action — EXILE referent=event — runs
        through the pending-replacement drain with the moving card bound
        as ``event``, exactly like the die lane).

        CONTROLLER RULE as in the other lanes: every predicate is judged
        in the RECORD's coordinates. The WAS_CAST_THIS_TURN condition
        reads the journalled CR 601.2h CAST rows, so a spell that cast its
        way onto the battlefield is spared and a put-onto creature (which
        never touched the stack) is not. The CR 614.4a chain guard rides
        ``replaced_seq``; a Permanent-sourced record must still be on the
        battlefield, the Eot half is exempt."""
        for rec in sorted(self.replacements, key=lambda r: r.seq):
            event = rec.event
            if not isinstance(event, ZoneChangeEvent):
                continue
            if rec.status != "live" or rec.seq in replaced_seq:
                continue
            if rec.tag == "Permanent" and not self._source_alive(rec.source):
                continue
            rec_ctx = self.executor._ctx(
                source=rec.source,
                controller=rec.controller,
                bindings={"event": [card]},
                decisions=(),
            )
            if not self._endpoint_matches(event.to_zone, to_state, card, rec_ctx):
                continue
            if not self._endpoint_matches(event.from_zone, from_state, card, rec_ctx):
                continue
            if event.subject is not None and not eval_filter(
                event.subject, card, rec_ctx
            ):
                continue
            if not self._condition_holds(rec, card, rec_ctx):
                continue
            return rec
        return None

    def prevents_untap(self, card: Handle) -> bool:
        """The UNTAP-step consumer: does a live prevention veto this
        permanent's untap? (Frost Breath's compiled s2 lands here:
        TapStateEvent(tapped=False), step UNTAP, targets = the cast's
        designated creatures.)

        CR 502.3 ("effects can keep one or more of a player's permanents
        from untapping"): a STATIC carrier designates
        nothing; its affected set is the event's filter, judged over the card
        in the record's coordinates (Capture Sphere: "Enchanted creature
        doesn't untap during its controller's untap step" is IS_ATTACHED_TO_
        SOURCE ∧ creature, read off the Aura). A static carrier works while
        its source is on the battlefield."""
        return self._status_change_vetoed(
            card,
            lambda rec: isinstance(rec.event, TapStateEvent)
            and rec.event.tapped is False
            and rec.step in (None, Step.UNTAP),
        )

    def prevents_phase_in(self, card: Handle) -> bool:
        """The phasing consumer (CR 702.26a, the untap step's first action): does a
        live prevention keep this phased-out permanent from phasing in? Teferi,
        Timeless Voyager's [−8] "Until the end of your next turn, they can't phase
        in." is PhasingEvent(phased_in=True) over the creatures it phased out (the
        ``result`` register, locked into ``targets`` as it resolved). Judged like
        :meth:`prevents_untap`."""
        return self._status_change_vetoed(
            card, lambda rec: isinstance(rec.event, PhasingEvent) and rec.event.phased_in
        )

    def _status_change_vetoed(self, card: Handle, applies) -> bool:
        """Does a live prevention the ``applies(rec)`` test picks veto ``card``'s
        status change? A resolved record covers the objects locked into its
        ``targets``; one with none, and a static carrier while its source is on the
        battlefield, covers what its condition and event filter match, judged over
        the card in the record's coordinates."""
        for rec in sorted(self.preventions, key=lambda r: r.seq):
            if rec.status == "expired" or not applies(rec):
                continue
            event = rec.event
            if rec.targets:
                if card in rec.targets:
                    return True
                continue
            if not rec.resolved and not self._source_alive(rec.source):
                # a static carrier works while its source is on the
                # battlefield; a resolved effect outlives its source (CR
                # 611.2a, as in _live_ctx)
                continue
            ctx = self._rec_ctx(rec)
            if not self._condition_holds(rec, card, ctx):
                continue
            if not eval_filter(event.filter, card, ctx):
                continue
            return True
        return False

    # ------------------------------------------------ declaration consumers

    def _rec_ctx(self, rec) -> ExecCtx:
        """The consult context in the RECORD's own coordinates (the con-
        troller rule the replacement/prevention filters follow): source =
        the preventing permanent, controller = its controller, and the
        materialized designated set bound as ``target`` so an IS_ANY_TAR-
        GET slot reads the cast that opened the window (Subira) instead of
        a long-gone resolution. A resolved record's set is also its
        ``result``: the objects an IS_RESULT condition named as it resolved
        (``verbs._v_prevent``). A static carrier never resolved, so it has
        no result, and an IS_RESULT read there raises."""
        bindings: dict = {"target": list(rec.targets)}
        if rec.resolved:
            bindings["result"] = list(rec.targets)
        return self.executor._ctx(
            source=rec.source,
            controller=rec.controller,
            bindings=bindings,
            decisions=(),
        )

    def _pair_vetoed(self, rec, subject: Handle, other: Handle) -> bool:
        """One prevention record vs one declaration pair, judged in the
        record's coordinates. ``rec.condition`` is judged over the DECLAR-
        ATION'S OWN SIDE of the pair it restricts; the block consult judges
        it over BOTH sides, the attack consult over the attacker (its own
        side). Both sides is the reading the corpus inventory supports: the
        static carriers register their static's state gate (Tome Anima's
        draw clock, subject-independent) or NOTHING at all (Fetters/
        Shacklegeist carry the restriction in the event slots), Subira's
        IS_ANY_TARGET is designation-bound, and the only subject-naming
        block condition is Ghostly Pilferer's IS_SOURCE, which names the
        BLOCKED side — a future "this creature can't block" activation
        would name the BLOCKER side, and either reading passes here while
        neither false-vetoes (the blocker/blocked slot filters still gate
        the pair). Then the event node's own slots: block records filter/
        subject over the BLOCKER and blocked over the ATTACKER; attack
        records filter over the ATTACKER (an ``attacked`` slot has no
        corpus carrier — the raise, never a silent ignore)."""
        ctx = self._live_ctx(rec)
        if ctx is None:
            return False
        event = rec.event
        if isinstance(event, DeclareBlockersEvent):
            if event.count is not None:
                return False  # a limit on the number of blockers: blockers_allowed
            blocker, blocked = subject, other
            if rec.condition is not None and not (
                eval_filter(rec.condition, blocker, ctx)
                or eval_filter(rec.condition, blocked, ctx)
            ):
                return False
            if not self._slot_holds(rec, event.filter, blocker, ctx):
                return False
            if event.subject is not None and not self._slot_holds(
                rec, event.subject, blocker, ctx
            ):
                return False
            # the blocked slot must MATCH the attacker side (IS_SOURCE for
            # "can't be blocked" carriers, FNot(FLYING) for the block-only
            # restriction family - a matching slot vetoes the pair)
            return event.blocked is None or self._slot_holds(
                rec, event.blocked, blocked, ctx
            )
        if isinstance(event, DeclareAttackersEvent):
            if event.attacked is not None:
                raise NotImplementedError(
                    "executor: DeclareAttackersEvent 'attacked' slot on a "
                    "prevention record has no consumer (no corpus carrier)"
                )
            if rec.condition is not None and not eval_filter(
                rec.condition, subject, ctx
            ):
                return False
            return self._slot_holds(rec, event.filter, subject, ctx)
        return False

    def _live_ctx(self, rec) -> ExecCtx | None:
        """The consult context of a combat prevention that applies now, or None."""
        if rec.status == "expired":
            return None
        # Destructive Tampering ("can't block this turn"): a RESOLVED
        # effect outlives its source (CR 611.2a — the sorcery is long in the
        # graveyard by the declare-blockers step), whatever its duration: a
        # "can't block" with no end or until your next turn applies too.
        # Static carriers (registered through the battlefield lifecycle)
        # keep the liveness gate.
        if not rec.resolved and not self._source_alive(rec.source):
            return None
        ctx = self._rec_ctx(rec)
        if isinstance(rec.duration, DurationWhileCondition) and not eval_filter(
            rec.duration.filter, rec.source, ctx
        ):
            return None
        return ctx

    def blockers_allowed(self, attacker: Handle) -> int | None:
        """CR 509.1b: the most creatures that may block ``attacker``, None for no
        limit. "This creature can't be blocked by more than one creature." is a prevention of
        the attacker becoming blocked by ``QAtLeast(2)`` creatures, so it allows one. Judged in
        the record's coordinates like the pair consults, the condition and the ``blocked`` slot
        over the attacker. Which creatures count is the event's ``filter``; every carrier counts
        any creature, and a narrower one is refused rather than counted wrong."""
        allowed: int | None = None
        for rec in sorted(self.preventions, key=lambda r: r.seq):
            event = rec.event
            if not isinstance(event, DeclareBlockersEvent) or event.count is None:
                continue
            ctx = self._live_ctx(rec)
            if ctx is None:
                continue
            if event.subject is not None or event.filter != FAnd(()):
                raise NotImplementedError(
                    "executor: a blocker-count limit that counts only some blockers has no "
                    "consumer (no carrier prints one)"
                )
            if rec.condition is not None and not eval_filter(rec.condition, attacker, ctx):
                continue
            assert event.blocked is not None and isinstance(event.count, QAtLeast)
            if not self._slot_holds(rec, event.blocked, attacker, ctx):
                continue
            limit = event.count.n - 1
            allowed = limit if allowed is None else min(allowed, limit)
        return allowed

    @staticmethod
    def _slot_holds(rec, filter_, handle: Handle, ctx: ExecCtx) -> bool:
        """CR 608.2b: a combat slot that names the ability's target
        (an IS_ANY_TARGET conjunct) means the creatures designated and checked
        when the ability resolved (_v_prevent locked them into rec.targets); its
        targeting restrictions are not read again. Any other slot is evaluated
        live."""
        from MTG_bot.core.executor.query import designation_bound

        if designation_bound(filter_):
            return handle in rec.targets
        return eval_filter(filter_, handle, ctx)

    def prevents_block_declaration(self, blocker: Handle, attacker: Handle) -> bool:
        """CR 509 legality: does a live PREVENT_EFFECT veto the pair
        ``blocker`` blocking ``attacker``? Static carriers (Tome Anima "can't
        be blocked as long as...", Pirate token "can't block", Shacklegeist
        "can block only creatures with flying", Faith's Fetters' block half)
        and runtime carriers (Ghostly Pilferer's activated discard, Subira's
        "{1}: another target creature can't be blocked") ride the SAME
        PreventionRecord shape; the pair slots decide."""
        for rec in sorted(self.preventions, key=lambda r: r.seq):
            event = rec.event
            if not isinstance(event, DeclareBlockersEvent):
                continue
            if self._pair_vetoed(rec, blocker, attacker):
                return True
        return False

    def prevents_attack_declaration(self, attacker: Handle) -> bool:
        """CR 508.1 legality: does a live PREVENT_EFFECT veto
        ``attacker``'s attack declaration (Faith's Fetters' "enchanted
        permanent can't attack" — the aura edge runs through the attach-
        ment oracle the filter reads)?"""
        for rec in sorted(self.preventions, key=lambda r: r.seq):
            event = rec.event
            if not isinstance(event, DeclareAttackersEvent):
                continue
            if self._pair_vetoed(rec, attacker, attacker):
                return True
        return False

    def prevents_activation(
        self, permanent: Handle, activator: Handle, ability: object
    ) -> bool:
        """CR 602.5 (602.5a's "prohibited from being activated"): does a
        live PREVENT_EFFECT over an :class:`AbilityActivatedEvent` forbid
        ``activator`` activating ``ability`` of ``permanent``? Faith's
        Fetters' "its activated abilities can't be activated unless they're
        mana abilities" is such a record (kind NON_MANA, source the enchanted
        permanent). Judged in the record's coordinates like the declaration
        consults (:meth:`_pair_vetoed`): the same liveness rule, the record's
        designated set bound as ``target``, its condition over the permanent,
        the event's ``kind`` through the one 605.1a classifier, ``actor``
        over the activating player and ``source`` over the permanent."""
        for rec in sorted(self.preventions, key=lambda r: r.seq):
            event = rec.event
            if not isinstance(event, AbilityActivatedEvent) or rec.status == "expired":
                continue
            if not rec.resolved and not self._source_alive(rec.source):
                continue
            ctx = self._rec_ctx(rec)
            if isinstance(rec.duration, DurationWhileCondition) and not eval_filter(
                rec.duration.filter, rec.source, ctx
            ):
                continue
            if rec.condition is not None and not eval_filter(rec.condition, permanent, ctx):
                continue
            if not activation_matches_kind(ability, event.kind):
                continue
            if event.actor is not None and not eval_filter(event.actor, activator, ctx):
                continue
            if eval_filter(event.source, permanent, ctx):
                return True
        return False

    def prevents_countering(self, spell: Handle) -> bool:
        """CR 701.6a, 101.2: can't ``spell`` be countered? Yes when a
        live PREVENT_EFFECT over a :class:`CounteredEvent` names it: a static
        ability of a permanent ("Creature spells can't be countered.", Gaea's
        Herald), a resolved effect ("Spells you control can't be countered this
        turn.", Veil of Summer; it modifies the rules, so it covers spells cast
        after it resolved, CR 611.2c), or the spell's own ability, which
        functions on the stack (CR 113.6g, "This spell can't be countered.").
        Each is judged in its own coordinates, like the other consults; "you"
        of a permanent's static is its controller now (CR 109.5: a stolen
        Sphinx of the Final Word protects its new controller's spells). Only
        the counter fails: a counterspell may still target the spell."""
        from MTG_bot.core.executor.legality import spell_record

        executor = self.executor
        record = spell_record(executor, spell)
        if record is not None:
            ctx = executor._ctx(
                source=spell,
                controller=executor.controller_of(spell),
                bindings=None,
                decisions=(),
            )
            for ability in record.abilities:
                if not isinstance(ability, StaticAbility):
                    continue
                effect = ability.effect
                atoms = effect.steps if isinstance(effect, Seq) else (effect,)
                for atom in atoms:
                    if not (isinstance(atom, Atom) and atom.verb is Verb.PREVENT_EFFECT):
                        continue
                    event = atom.args.get("event")
                    # CR 113.6g: only an ability that says THIS object can't be
                    # countered works on the stack; "Creature spells can't be
                    # countered." works from the battlefield (CR 113.6), so it
                    # does not protect its own spell.
                    if not isinstance(event, CounteredEvent) or not _filter_names_the_source(
                        event.filter
                    ):
                        continue
                    if ability.condition is not None and not eval_filter(
                        ability.condition, spell, ctx
                    ):
                        continue
                    if eval_filter(event.filter, spell, ctx):
                        return True
        for rec in sorted(self.preventions, key=lambda r: r.seq):
            event = rec.event
            if not isinstance(event, CounteredEvent) or rec.status == "expired":
                continue
            if not rec.resolved and not self._source_alive(rec.source):
                continue
            if rec.targets:
                if spell in rec.targets:
                    return True
                continue
            ctx = executor._ctx(
                source=rec.source,
                controller=rec.controller,  # a static's follows its source (follow_controller)
                bindings=None,
                decisions=(),
            )
            if not self._condition_holds(rec, spell, ctx):
                continue
            if eval_filter(event.filter, spell, ctx):
                return True
        return False

    # ------------------------------------------------------------ expiry API

    def _expire(self, rec) -> int:
        if rec.status == "expired":
            return 0
        rec.status = "expired"
        return 1

    def sweep_at_eot(self) -> int:
        # Eot preventions and the spell-sourced "this turn" replacements
        # (live from resolution to end of turn).
        return sum(
            self._expire(rec)
            for rec in (*self.preventions, *self.replacements)
            if rec.tag == "Eot" and rec.status != "expired"
        )

    def forget_departed(self, handle: Handle) -> int:
        """CR 400.7: ``handle`` left the battlefield; if it returns it is a new object. A
        prevention a resolved spell or ability locked onto it ("those creatures don't untap",
        "can't be blocked this turn") no longer covers it, and a replacement scoped to it ("if
        that creature would die this turn") no longer finds it. A prevention left with no
        designated object expires: an empty ``targets`` means a static carrier, which reads its
        filter instead. Returns the number of records touched."""
        touched = 0
        for rec in self.preventions:
            if rec.status == "expired":
                continue
            if handle in rec.targets:
                rec.targets = tuple(t for t in rec.targets if t != handle)
                if not rec.targets:
                    self._expire(rec)
                touched += 1
            elif (
                rec.resolved
                and rec.source == handle
                and rec.condition is not None
                and _filter_names_the_source(rec.condition)
            ):
                # "Ghostly Pilferer can't be blocked this turn": a resolved effect about its
                # own source (CR 611.2a lets other effects outlive the source) ends with it.
                self._expire(rec)
                touched += 1
        for repl in self.replacements:
            if repl.status != "expired" and handle in repl.designated:
                repl.designated = tuple(t for t in repl.designated if t != handle)
                touched += 1
        return touched

    def expire_leaves(self, anchor: Handle) -> int:
        return sum(
            self._expire(rec)
            for rec in self.preventions
            if isinstance(rec.duration, DurationUntilLeaves)
            and rec.duration.source == "source"
            and rec.source == anchor
            and rec.status != "expired"
        )

    def expire_at_step(self, step: Step, active: Handle, controller_of) -> int:
        """The UNTAP tick's expiry half: UNTIL_NEXT_STEP(UNTAP) prevents are
        consumed DURING the tick and expire right after it — the Frost
        Breath freeze therefore survives exactly one untap step and the
        creature untaps on the following one (pinned by
        ``test_freeze_survives_exactly_one_untap_tick``).

        An owner-scoped record ("those creatures don't untap during
        their controller's next untap step") is consumed per object: this
        tick ends it only for the targets the active player controls, and
        the record expires once no target is left (Frost Breath on one
        creature of each player freezes each through its own controller's
        untap step)."""
        expired = 0
        for rec in self.preventions:
            dur = rec.duration
            if not isinstance(dur, DurationUntilNextStep) or dur.step is not step:
                continue
            if rec.status == "expired":
                continue
            if dur.owner_scoped:
                done = {
                    t
                    for t in rec.targets
                    if t.namespace == "card" and controller_of(t) == active
                }
                if done:
                    rec.targets = tuple(t for t in rec.targets if t not in done)
                    if not any(t.namespace == "card" for t in rec.targets):
                        expired += self._expire(rec)
            else:
                expired += self._expire(rec)
        return expired

    def expire_until_next_turn(self, player: Handle) -> int:
        """``player``'s turn begins: "until your next turn" preventions end (CR 611.2a),
        and "until the end of your next turn" ones become "until end of turn", so this
        turn's cleanup sweep ends them (CR 514.2)."""
        expired = 0
        for rec in self.preventions:
            if rec.status == "expired" or rec.controller != player:
                continue
            if isinstance(rec.duration, DurationUntilNextTurn):
                expired += self._expire(rec)
            elif isinstance(rec.duration, DurationUntilEndOfNextTurn):
                rec.tag = "Eot"
        return expired

    # ---------------------------------------------------------- determinism

    def dump(self) -> tuple[tuple[object, ...], ...]:
        """Canonical view for the replay fingerprint (replacements then
        preventions, seq order; status included)."""
        rows = tuple(
            (
                "repl",
                rec.seq,
                str(rec.source),
                str(rec.controller),
                rec.tag,
                rec.status,
                repr(rec.event),
                repr(rec.action),
            )
            for rec in sorted(self.replacements, key=lambda r: r.seq)
        )
        rows += tuple(
            (
                "prev",
                rec.seq,
                str(rec.source),
                str(rec.controller),
                rec.tag,
                rec.status,
                repr(rec.event),
                rec.step.name if rec.step is not None else None,
                tuple(str(t) for t in rec.targets),
            )
            for rec in sorted(self.preventions, key=lambda r: r.seq)
        )
        return rows

    def __len__(self) -> int:
        return len(self.replacements) + len(self.preventions)
