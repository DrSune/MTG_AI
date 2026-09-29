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
    BecomesBlockedEvent,
    CombatDamageEvent,
    DamageDealtEvent,
    DeclareAttackersEvent,
    DeclareBlockersEvent,
    Duration,
    DurationUntilLeaves,
    DurationUntilNextStep,
    DurationUntilNextTurn,
    DurationWhileCondition,
    Effect,
    EventSpec,
    FAnd,
    FAtom,
    Filter,
    FNot,
    FOr,
    QUnbounded,
    ReplacementAbility,
    Step,
    TapStateEvent,
)
from MTG_bot.core.executor.durations import duration_tag
from MTG_bot.core.executor.quantity import ExecCtx, eval_filter
from MTG_bot.core.executor.selectors import controller_matches
from MTG_bot.core.identity import Handle

if TYPE_CHECKING:  # pragma: no cover - typing-only
    from MTG_bot.core.compiler.compiler import CardRecord
    from MTG_bot.core.executor import Executor

# Combat-side event kinds: registered + exposed, no consumer pre-12e.
_COMBAT_EVENTS = (
    DeclareAttackersEvent,
    DeclareBlockersEvent,
    BecomesBlockedEvent,
    CombatDamageEvent,
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
                        controller=self.world.controller_of(handle),
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
        world = self.world
        return source in world.cards and world.zone_of(source).kind == "battlefield"

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

    def replacement_for_player_damage(
        self, ctx: ExecCtx, victim: Handle
    ) -> ReplacementRecord | None:
        """The apply-pipeline interceptor hook: is a live replacement about
        to consume this damage-to-a-player event? (Checked BEFORE any life
        mutation — C24 replacement-before-apply.)

        CONTROLLER RULE: the atom runs in the DEALER's coordinates, but the
        replacement's filters ("to you") belong to the REPLACEMENT — every
        predicate here is judged in the record's own coordinates
        (source=the replacement's object, controller=its controller), the
        same rule granted abilities follow."""
        for rec in sorted(self.replacements, key=lambda r: r.seq):
            event = rec.event
            if not isinstance(event, DamageDealtEvent):
                continue
            if event.source is not None:
                raise NotImplementedError(
                    "executor: damage-replacement source filter is later "
                    "phase (C-4 damage surface)"
                )
            if event.combat is True:
                raise NotImplementedError(
                    "executor: combat-damage replacement is later phase (combat)"
                )
            if event.amount is not None and not isinstance(event.amount, QUnbounded):
                raise NotImplementedError(
                    "executor: bounded damage-replacement caps ('the first "
                    "N') are modeled as counters + triggers, not guessed "
                    "here (12e)"
                )
            if not self._source_alive(rec.source):
                continue
            rec_ctx = replace(ctx, source=rec.source, controller=rec.controller)
            if not self._player_filter_matches(event.filter, victim, rec_ctx):
                continue
            if not self._condition_holds(rec, victim, rec_ctx):
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
        """EXPOSED-BUT-UNUSED: the live attack/block/combat prevents (Faith's
        Fetters / Capture Sphere family). Combat legality (post-12e) is the
        consumer; the records exist, dump, and are predicate-tested today."""
        return tuple(
            rec
            for rec in self.preventions
            if rec.status != "expired" and isinstance(rec.event, _COMBAT_EVENTS)
        )

    # ------------------------------------------------------------ expiry API

    def _expire(self, rec) -> int:
        if rec.status == "expired":
            return 0
        rec.status = "expired"
        return 1

    def sweep_at_eot(self) -> int:
        return sum(
            self._expire(rec)
            for rec in self.preventions
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
