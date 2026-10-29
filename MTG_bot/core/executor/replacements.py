"""Replacement effects + pre-application prevention records (round 12d,
plan /06 §12d, C24: replacement-before-apply).

Two veto-shaped vocabularies live here, both keyed on the journal's event
shapes and both fingerprint-dumped:

  * :class:`ReplacementRecord` — a compiled :class:`ReplacementAbility`
    node attached to a battlefield permanent (canonical row: Nine Lives,
    whose template says "prevent that damage and put an incarnation counter
    on this enchantment" — the grammar carries the PREVENTION inside the
    replacement's action position, per the b5b row's own docstring: "the
    replacement itself carries the prevention, no PREVENT atom"). The
    interceptor runs in :func:`~MTG_bot.core.executor.verbs._v_deal_damage`
    BEFORE the world mutation: a matching live replacement consumes the
    damage-to-a-player event (no life change happens, so the journal emits
    no DAMAGE row and nothing downstream can mis-fire), appends a
    ``("REPLACED", …)`` audit row, and runs the replacement's ACTION as a
    nested journalled effect through the executor (the incarnation counter
    lands as a normal journalled PUT_COUNTER, arming Nine Lives' own
    HAS_COUNTER-9 exile trigger — the golden drives the whole chain).
    "First N times"-style partial replacements (a bounded event ``amount``)
    RAISE: the closed vocabulary models the cap as a trigger, not as a
    number on the replacement, and the executor does not guess caps.

  * :class:`PreventionRecord` — the PREVENT_EFFECT verb (the Capture-
    Sphere / Faith's-Fetters / Frost-Breath family). A veto-before-
    application record: condition + event spec + optional step + duration.
    The UNTAP consumer is live (12d's untap step consults
    :meth:`ReplacementRegistry.prevents_untap` — the Frost Breath freeze);
    combat-side prevents (attack/block) and mana-ability prevents are
    REGISTERED + EXPOSED (:meth:`combat_preventions`) with no consumer yet
    — the combat phase is post-12e territory and faking a consumer would
    violate the honest-unsupported mandate.

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
    Atom,
    BecomesBlockedEvent,
    CardDrawnEvent,
    ControllerRef,
    CounterKind,
    CounterPlacedEvent,
    CreatureDiesEvent,
    DamageDealtEvent,
    DeclareAttackersEvent,
    DeclareBlockersEvent,
    Duration,
    DurationEot,
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
    QAtLeast,
    Quantity,
    QUnbounded,
    ReplacementAbility,
    Step,
    TapStateEvent,
    Verb,
    Zone,
    ZoneChangeEvent,
    ZoneKind,
)
from MTG_bot.core.executor.durations import duration_tag
from MTG_bot.core.executor.quantity import ExecCtx, eval_filter, resolve
from MTG_bot.core.executor.selectors import (
    ZONE_KIND_TO_STATE,
    controller_matches,
)
from MTG_bot.core.identity import Handle

if TYPE_CHECKING:  # pragma: no cover - typing-only
    from MTG_bot.core.compiler.compiler import CardRecord
    from MTG_bot.core.executor import Executor

# Combat-side event kinds: registered + exposed, no consumer pre-12e.
# R2 fold (/140): CombatDamageEvent deleted — folded combat-damage
# replacements are DamageDealtEvent(combat=True) (handled by the damage
# path); this tuple keeps the declaration/block kinds only.
_COMBAT_EVENTS = (
    DeclareAttackersEvent,
    DeclareBlockersEvent,
    BecomesBlockedEvent,
)


@dataclass
class ReplacementRecord:
    """One compiled ReplacementAbility node while its source is attached.
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
    status: str = "live"  # live | dormant | expired
    # r19b (Scorching Dragonfire): the cast's designation snapshot, taken
    # when a SPELL-sourced (Eot) record registers. The record outlives the
    # resolution's ExecCtx, but its event filter (IS_ANY_TARGET "that
    # creature") still MEANS the designation — the PreventionRecord
    # ``_rec_ctx`` convention, extended to the replacement lane so the
    # dies window stays scoped to the object the spell named (CR 614.1:
    # the replacement applies to the event it was set up for).
    designated: tuple[Handle, ...] = ()


@dataclass
class PreventionRecord:
    """One PREVENT_EFFECT record: event veto + step + affected set."""

    seq: int
    source: Handle
    controller: Handle
    event: EventSpec
    step: Step | None
    targets: tuple[Handle, ...]
    tag: str = "Permanent"
    duration: Duration | None = None
    condition: Filter | None = None
    status: str = "live"  # live | dormant | expired


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
        while attached — the detach half of the 12b lifecycle expires
        them)."""
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
                        controller=self.executor.controller_of(handle),  # 16e
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
            if rec.source == handle and rec.status != "expired":
                rec.status = "expired"
                expired += 1
        return expired

    def register_ephemeral_replacements(
        self,
        source: Handle,
        controller: Handle,
        record: CardRecord,
        designated: tuple[Handle, ...] = (),
    ) -> int:
        """r19a (Life Goes On): a RESOLVING INSTANT/SORCERY's ReplacementAbility
        nodes. A spell never attaches (it hits the graveyard), so the
        battlefield lifecycle that normally registers replacements never
        sees it — yet the grammar carries the corpus' turn-shaped replacement
        idiom ("If a creature died this turn, you'd gain 8 life instead") as
        a card-level ReplacementAbility on the spell itself. Registering at
        resolution start (stack.py) with an Eot tag is the honest home: the
        effect is live from resolution to end of turn, expires in the EOT
        sweep, and never survives the window its own text names."""
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
                        designated=designated,  # r19b Scorching: the cast's
                        # designation rides the record — the dies window must
                        # stay scoped to the object the spell named (CR 614.1)
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
    ) -> PreventionRecord:
        """The PREVENT_EFFECT verb's runtime registration (targets already
        materialized from the cast's designated set)."""
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
        predicate over the source (StaticAbility convention)."""
        if rec.status == "expired":
            return False
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
        """r22b (Fiery Emancipation): is a DamageDealtEvent filter pure
        PLAYER-COORDINATE — a predicate whose only meaning is "the damaged
        object IS a named seat"? The 12d reading of a bare
        ``CONTROLLER_IS YOU`` on a damage event is the CR's damaged-object
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

    def replacement_for_damage(
        self,
        ctx: ExecCtx,
        victim: Handle,
        dealer: Handle,
        amount: int,
        combat: bool,
    ) -> tuple[ReplacementRecord, int | None] | None:
        """r22b (Fiery Emancipation): the unified apply-pipeline interceptor
        for a DAMAGE event, both lanes (C24 replacement-before-apply).
        Returns ``(record, None)`` when the record CONSUMES the event (the
        Nine Lives doctrine — the damage never applies, the action runs in
        the drain) or ``(record, new_amount)`` when it MODIFIES the event's
        quantity in place (the Fiery Emancipation idiom: the action is a
        DEAL_DAMAGE whose amount quantity rewrites the event's —
        ``QBin(MUL, 3, QProp(event, AMOUNT))`` — so exactly one journalled
        DAMAGE row lands, dealer attribution and lifelink stay on the
        dealt amount, and the action's C-4 dealer surface is never
        executed). ``None`` when nothing applies.

        The event's slots read as matchers over the about-to-happen event:
        ``amount`` accepts the two no-constraint idioms (QUnbounded "all",
        QX the compiler's amount placeholder) and flags the first-N cap
        (12e: caps are counters + triggers, never guessed); ``combat`` True
        is the standing later-phase flag, False scopes to non-combat;
        ``source`` is a Filter over the DEALER, evaluated in the record's
        coordinates (the CONTROLLER_IS card branch resolves a spell
        handle through the zone-owner controller_of — the caster).
        CONTROLLER RULE as in every other lane: every predicate is judged
        in the RECORD's own coordinates.

        CR 616.1 ordering is unmodeled: when TWO live records match the
        same event, the choice belongs to the damaged player and the
        executor does not guess — RAISE (loud on hit, per the standing
        mandate). A single record whose action re-queues damage cannot
        self-replace: the drain's CR 614.4a ``replaced_seq`` guard covers
        the consume half, and the modify half never executes an action."""
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
        if len(matches) > 1:
            raise NotImplementedError(
                "executor: "
                + str(len(matches))
                + " damage replacements apply to one event; the CR 616.1 "
                "ordering choice belongs to the affected player (unmodeled)"
            )
        if not matches:
            return None
        rec = matches[0]
        if isinstance(rec.action, Atom) and rec.action.verb is Verb.DEAL_DAMAGE:
            quantity = rec.action.args.get("amount")
            if quantity is None:
                raise NotImplementedError(
                    "executor: a DEAL_DAMAGE replacement action without an "
                    "amount slot is not the Fiery idiom (flag, not guess)"
                )
            assert isinstance(quantity, Quantity)
            # the MATCHED record's own coordinates (never the loop's last
            # scan context), plus the event register the action's
            # QProp(event, AMOUNT) reads and the victim bound as ``event``.
            ev_ctx = replace(
                ctx,
                source=rec.source,
                controller=rec.controller,
                bindings={"event": [victim]},
                event_amount=amount,
            )
            return (rec, max(0, resolve(quantity, ev_ctx)))
        return (rec, None)

    def prevented_card_damage(
        self, ctx: ExecCtx, victim: Handle, combat: bool
    ) -> PreventionRecord | None:
        """r20a (Pack Leader): the prevention-before-apply interceptor for
        damage a CARD would be dealt. The PREVENT_EFFECT lane carried the
        untap / block-declaration / attack-declaration consumers but never
        a DAMAGE consumer, so a compiled DamageDealtEvent prevention (Pack
        Leader's "prevent all combat damage ... Dogs" half) was compile-
        but-never-apply. combat-scope mirrors the binding-side
        DamageDealtEvent matcher (16c): ``combat=True`` matches combat
        damage only, ``False`` only the rest, ``None`` anything. QUnbounded
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
            if not self._source_alive(rec.source):
                continue
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
        """r19a (Life Goes On): the apply-pipeline interceptor for a
        LIFE-GAINED event (C24 replacement-before-apply, mirrored from the
        damage hook). The subject of a LifeGainedEvent is the gaining
        player, so the record's condition (DIED_THIS_TURN) is judged over
        the PLAYER handle — quantity's existential reading answers it.
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
        self, ctx: ExecCtx, drawer: Handle, amount: int
    ) -> ReplacementRecord | None:
        """r22b (Teferi's Ageless Insight): the apply-pipeline interceptor
        for a CARD-DRAW event (C24 replacement-before-apply, mirrored from
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

    def replacement_for_counter_placement(
        self,
        ctx: ExecCtx,
        card: Handle,
        kind: CounterKind,
        amount: int,
    ) -> ReplacementRecord | None:
        """r22b (Conclave Mentor): the apply-pipeline interceptor for a
        COUNTER-PLACEMENT event (C24 replacement-before-apply): the PUT-
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
        (QAtLeast(1) — the grammar's R5-2 idiom): n >= 1 satisfies it;
        QUnbounded matches any placement. Any other shape is a cap the
        executor does not guess (12e). The subject filter ("a creature
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

    def replacement_for_death(
        self, card: Handle, replaced_seq: frozenset[int] = frozenset()
    ) -> ReplacementRecord | None:
        """r19b (Scorching Dragonfire): the state-check interceptor for a
        CREATURE-DIES event — the die lane mirrors the damage/life hooks
        (C24 replacement-before-apply): the SBA loop consults this BEFORE
        moving the creature to the graveyard, and a match consumes the
        death (no graveyard move, no CREATURE_DIES journal row — see the
        documented v1 gap in __init__.py's state-check drain).

        B-62: both dying lanes of the SBA sweep consult it, the lethal
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
        resolved). The CR 614.4a chain guard rides ``replaced_seq``."""
        for rec in sorted(self.replacements, key=lambda r: r.seq):
            event = rec.event
            if not isinstance(event, CreatureDiesEvent):
                continue
            if rec.status != "live" or rec.seq in replaced_seq:
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
        binding-side ``_zone_matches`` convention (12b) reused verbatim so
        the trigger lane and the replacement lane read endpoints alike:
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
        """r20b (Containment Priest): the apply-pipeline interceptor for a
        ZONE-CHANGE event — the enter lane mirrors the death hook
        (C24 replacement-before-apply): ``_v_move_zone`` consults this
        BEFORE the battlefield move, and a match consumes the enter (no
        battlefield placement; the action — EXILE referent=event — runs
        through the pending-replacement drain with the moving card bound
        as ``event``, exactly like the die lane).

        CONTROLLER RULE as in the other lanes: every predicate is judged
        in the RECORD's coordinates. The WAS_CAST_THIS_TURN condition
        reads the journalled 601.2h CAST rows, so a spell that cast its
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
        designated creatures.)"""
        for rec in sorted(self.preventions, key=lambda r: r.seq):
            if rec.status == "expired":
                continue
            event = rec.event
            if not isinstance(event, TapStateEvent) or event.tapped is not False:
                continue
            if rec.step not in (None, Step.UNTAP):
                continue
            if card not in rec.targets:
                continue
            return True
        return False

    def combat_preventions(self) -> tuple[PreventionRecord, ...]:
        """The LIVE attack/block/combat prevents (Faith's Fetters / Capture
        Sphere family). 16c: the consumers are live — the CR 508/509 de-
        claration legality in legality.py calls the two pair consults
        below; the dump stays for the audit trail."""
        return tuple(
            rec
            for rec in self.preventions
            if rec.status != "expired" and isinstance(rec.event, _COMBAT_EVENTS)
        )

    # ------------------------------------------- 16c: declaration consumers

    def _rec_ctx(self, rec, attacker: Handle) -> ExecCtx:
        """The consult context in the RECORD's own coordinates (the con-
        troller rule the replacement/prevention filters follow): source =
        the preventing permanent, controller = its controller, and the
        materialized designated set bound as ``target`` so an IS_ANY_TAR-
        GET slot reads the cast that opened the window (Subira) instead of
        a long-gone resolution."""
        return self.executor._ctx(
            source=rec.source,
            controller=rec.controller,
            bindings={"target": list(rec.targets)},
            decisions=(),
        )

    def _pair_vetoed(self, rec, subject: Handle, other: Handle) -> bool:
        """One prevention record vs one declaration pair, judged in the
        record's coordinates. ``rec.condition`` is judged over the DECLAR-
        ATION'S OWN SIDE of the pair it restricts; the block consult judges
        it over BOTH sides, the attack consult over the attacker (its own
        side). Both-sides is the r21a reading of the corpus inventory: the
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
        if rec.status == "expired":
            return False
        # C5 (Destructive Tampering "can't block this turn"): a RESOLVED
        # until-end-of-turn effect outlives its source (CR 611.2a — the
        # sorcery is long in the graveyard by the declare-blockers step).
        # Only the time-bounded DurationEot shape is exempt — its single
        # expiry is the EOT sweep (tag "Eot"). Static carriers (duration
        # None, registered through the battlefield lifecycle) and WHILE-
        # gated records keep the liveness gate exactly as before.
        if not isinstance(rec.duration, DurationEot) and not self._source_alive(
            rec.source
        ):
            return False
        ctx = self._rec_ctx(rec, subject)
        if isinstance(rec.duration, DurationWhileCondition) and not eval_filter(
            rec.duration.filter, rec.source, ctx
        ):
            return False
        event = rec.event
        if isinstance(event, DeclareBlockersEvent):
            blocker, blocked = subject, other
            if rec.condition is not None and not (
                eval_filter(rec.condition, blocker, ctx)
                or eval_filter(rec.condition, blocked, ctx)
            ):
                return False
            if not eval_filter(event.filter, blocker, ctx):
                return False
            if event.subject is not None and not eval_filter(
                event.subject, blocker, ctx
            ):
                return False
            # the blocked slot must MATCH the attacker side (IS_SOURCE for
            # "can't be blocked" carriers, FNot(FLYING) for the block-only
            # restriction family - a matching slot vetoes the pair)
            return event.blocked is None or eval_filter(event.blocked, blocked, ctx)
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
            return eval_filter(event.filter, subject, ctx)
        return False

    def prevents_block_declaration(self, blocker: Handle, attacker: Handle) -> bool:
        """16c (CR 509 legality): does a live PREVENT_EFFECT veto the pair
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
        """16c (CR 508.1 legality): does a live PREVENT_EFFECT veto
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

    # ------------------------------------------------------------ expiry API

    def _expire(self, rec) -> int:
        if rec.status == "expired":
            return 0
        rec.status = "expired"
        return 1

    def sweep_at_eot(self) -> int:
        # r19a: replacements join the EOT sweep (the spell-sourced
        # "this turn" replacements live resolution -> Eot; the damage lane
        # only ever had PERVENT_EFFECT prevents to sweep).
        return sum(
            self._expire(rec)
            for rec in (*self.preventions, *self.replacements)
            if rec.tag == "Eot" and rec.status != "expired"
        )

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
        creature untaps on the following one (pinned by test)."""
        expired = 0
        for rec in self.preventions:
            dur = rec.duration
            if not isinstance(dur, DurationUntilNextStep) or dur.step is not step:
                continue
            if rec.status == "expired":
                continue
            if dur.owner_scoped:
                if any(
                    t.namespace == "card" and controller_of(t) == active
                    for t in rec.targets
                ):
                    expired += self._expire(rec)
            else:
                expired += self._expire(rec)
        return expired

    def expire_until_next_turn(self, player: Handle) -> int:
        return sum(
            self._expire(rec)
            for rec in self.preventions
            if isinstance(rec.duration, DurationUntilNextTurn)
            and rec.controller == player
            and rec.status != "expired"
        )

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
