"""The full Duration vocabulary on the executor-side ledger (round 12d,
plan /06 §12d, ruling 1).

This module supersedes :mod:`MTG_bot.core.executor.durations_min` (which
stays as a re-export shim so every 12a/12b import path keeps working — the
ledger class name ``DurationLedger`` is CARRIED, per the 12d delegation's
migration option). Ruling 1 stands: state.py is frozen and the
:class:`DurationLedger` *is* the replayed state — its :meth:`dump` feeds the
executor's replay fingerprint, so every expiry decision this module makes is
deterministic and audited.

The vocab, and where each expiry point is driven from (12d wiring, all
inside :class:`~MTG_bot.core.executor.Executor`):

  * ``DurationEot`` — ``"Eot"``: the end-of-turn sweep (``end_turn`` calls
    :meth:`sweep_at_eot`, unchanged 12a behaviour — a PHYSICAL removal,
    because a verb-level Eot buff has no continuing identity to audit).
  * ``DurationWhileCondition`` — ``"While"``: re-evaluated on journal-
    relevant events (:meth:`settle_while`, driven from the executor's
    recompute pass after every public op). A while-off entry is DORMANT, not
    deleted — the grant follows the condition's truth, so it must come back
    when the condition does; the entry (and its dormancy status) stays in
    the dump either way.
  * ``DurationUntilNextStep(step, owner_scoped)`` — ``"UntilNextStep:<STEP>
    [:owner|:active]"``: expired by the matching step tick (the 12d untap
    step; :meth:`expire_at_step`). ``owner_scoped`` True binds the tick to
    the affected object's CONTROLLER's turn ("their controller's next untap
    step" — Frost Breath); False binds it to the next step of the active
    turn. The tick consumes the effect during the step, then expires it —
    the Frost Breath freeze therefore survives exactly one untap tick.
  * ``DurationUntilLeaves`` — ``"UntilLeaves"``: a zone interceptor — the
    executor's journal hook calls :meth:`expire_leaves` when the anchor
    permanent LEAVES the tracked zone. Per the r5 convention (re-entry does
    not restore a spent duration), a return to the zone does NOT restore
    the entry: the expiry is terminal.
  * ``DurationUntilNextTurn`` — ``"UntilNextTurn"``: expires at the
    recorded controller's next ``begin_turn`` (:meth:`expire_until_next_turn`)
    — the precise next-turn-start expiry the 12a module deferred. (The 12b
    delayed-trigger matcher keeps its documented Eot-window stand-in; that
    is :mod:`binding`'s own table, not this ledger.)
  * ``DurationPermanent`` — ``"Permanent"``: only another effect removes it.

**PT resolution rule (12d ruling, documented):** effective P/T = printed
BASE, then every modifier — verb-recorded and layer-materialized — folded
in **timestamp order, then Handle/insertion order** (:meth:`_effective`).
C18 was-snapshots take that same base-first fold at application time (they
read the stack, never a "baked" value), and the journal's dies snapshot
keeps reading :meth:`effective_pt` exactly as 12b pinned it.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from MTG_bot.core.ability_tree import (
    Duration,
    DurationEot,
    DurationPermanent,
    DurationUntilLeaves,
    DurationUntilNextStep,
    DurationUntilNextTurn,
    DurationWhileCondition,
    Filter,
    Step,
)
from MTG_bot.core.identity import CardIdentity, Handle

# Duration IR node -> ledger expiry tag. The tag is the canonical identity
# of the expiry class: it rides in every dump row and in the layer /
# prevention records of 12d's other registries.
_DURATION_TAG: dict[type, str] = {
    DurationEot: "Eot",
    DurationPermanent: "Permanent",
    DurationUntilNextTurn: "UntilNextTurn",
    DurationWhileCondition: "While",
    DurationUntilLeaves: "UntilLeaves",
}

# The one expiry 12a implements (and still the only PHYSICAL sweep — every
# 12d expiry tombstones instead, so the audit trail replays).
EOT_TAG = "Eot"

# The status tags a dump row can carry. Absent from ``_dormant`` == "live".
STATUS_LIVE = "live"
STATUS_WHILE_OFF = "while_off"
STATUS_EXPIRED = "expired"


def duration_tag(duration: Duration | None) -> str:
    """The ledger expiry tag for a Duration IR node; absent = permanent.

    12d: every member of the frozen Duration union tags — the 12a
    NotImplementedError-raising default for WHILE/UNTIL_NEXT_STEP/UNTIL_
    LEAVES is replaced by the real machinery below. An unknown node still
    raises: flag, don't degrade."""
    if duration is None:
        return "Permanent"
    if isinstance(duration, DurationUntilNextStep):
        scope = "owner" if duration.owner_scoped else "active"
        return f"UntilNextStep:{duration.step.name}:{scope}"
    tag = _DURATION_TAG.get(type(duration))
    if tag is None:
        raise NotImplementedError(
            f"executor: duration {type(duration).__name__} not implemented"
        )
    return tag


def parse_pt(value: str | None) -> int | None:
    """Printed P/T string -> int. ``None`` (not a creature) or a non-numeric
    printed value (``*``, ``+1``, Tarmogoyf-class dynamic) -> ``None``; the
    caller then resolves the number from a QProp/SET_PT, never from print."""
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


@dataclass(frozen=True)
class PtChange:
    """One recorded P/T modification.

    ``kind`` is ``"delta"`` (MODIFY_PT: additive) or ``"set"`` (SET_PT:
    absolute, later sets win over earlier ones and over deltas in clock
    order). The ``was_*`` pair is the C18 was-snapshot of the *effective*
    P/T at application time. ``record_id`` is the ledger's monotone id (0 =
    the legacy/verb path predating 12d bookkeeping — never linked to a
    layer; layer-materialized entries carry their ledger-assigned id).
    """

    target: Handle
    kind: str  # "delta" | "set"
    power_delta: int
    toughness_delta: int
    power_set: int | None
    toughness_set: int | None
    tag: str  # the canonical duration tag (see duration_tag)
    created_clock: int
    was_power: int | None
    was_toughness: int | None
    record_id: int = 0


@dataclass(frozen=True)
class DurationMeta:
    """The expiry bookkeeping of one ledger entry whose Duration needs more
    than the Eot sweep: the WHILE condition (with its eval coordinates),
    the UNTIL_NEXT_STEP scope, the UNTIL_LEAVES anchor, or the UNTIL_NEXT_
    TURN owner. Plain Eot/Permanent entries carry no meta."""

    tag: str
    condition: Filter | None = None  # WHILE: the condition's Filter
    anchor: Handle | None = None  # WHILE eval subject (the source)
    controller: Handle | None = None  # the recording controller
    step: Step | None = None  # UNTIL_NEXT_STEP
    owner_scoped: bool = False
    leaves_anchor: Handle | None = None  # UNTIL_LEAVES tracked object
    next_turn_owner: Handle | None = None  # UNTIL_NEXT_TURN holder


class DurationLedger:
    """The executor-side record of temporary and permanent P/T changes.

    :meth:`effective_pt` folds the entries for one card as documented on the
    module docstring (base, then timestamp-then-order applications, skipping
    dormant/expired tombstones), which is what lethal-damage checks, QProp
    POWER/TOUGHNESS and the 12b dies snapshot read.
    """

    def __init__(self) -> None:
        self._changes: list[PtChange] = []
        self._meta: dict[int, DurationMeta] = {}
        self._dormant: dict[int, str] = {}  # record_id -> while_off/expired
        self._next_id = 1

    # ------------------------------------------------------------- recording

    def record(
        self,
        identity: CardIdentity,
        change_kind: str,
        target: Handle,
        power_delta: int = 0,
        toughness_delta: int = 0,
        power_set: int | None = None,
        toughness_set: int | None = None,
        tag: str = "Permanent",
        clock: int = 0,
        duration: Duration | None = None,
        source: Handle | None = None,
        controller: Handle | None = None,
        leaves_anchor: Handle | None = None,
    ) -> PtChange:
        """Append one change, snapshotting the target's effective P/T (C18).

        12d additions: pass the Duration IR node (``duration``) for the
        condition-carrying vocabularies — WHILE re-evaluates against
        ``source`` in the recording ``controller``'s context, UNTIL_NEXT_
        STEP records the step + owner-scope, UNTIL_NEXT_TURN records the
        owner, UNTIL_LEAVES gets its tracked object as ``leaves_anchor``
        (the caller resolves the C12 referent string — the ledger never
        parses English)."""
        if change_kind not in ("delta", "set"):
            raise ValueError(f"DurationLedger: unknown change kind {change_kind!r}")
        was_power, was_toughness = self._effective(identity, target)
        record_id = self._next_id
        self._next_id += 1
        change = PtChange(
            target=target,
            kind=change_kind,
            power_delta=power_delta,
            toughness_delta=toughness_delta,
            power_set=power_set,
            toughness_set=toughness_set,
            tag=tag,
            created_clock=clock,
            was_power=was_power,
            was_toughness=was_toughness,
            record_id=record_id,
        )
        self._changes.append(change)
        meta = self._meta_for(duration, tag, source, controller, leaves_anchor)
        if meta is None:
            # Every RECORDED entry gets a meta row — plain Eot/Permanent
            # entries carry just the tag: expire() tombstones through
            # _meta, so an entry without a row would leak live past its
            # expiry (the detach-expiry pin in test_executor_layers.py).
            meta = DurationMeta(tag=tag, controller=controller)
        self._meta[record_id] = meta
        return change

    @staticmethod
    def _meta_for(
        duration: Duration | None,
        tag: str,
        source: Handle | None,
        controller: Handle | None,
        leaves_anchor: Handle | None,
    ) -> DurationMeta | None:
        if isinstance(duration, DurationWhileCondition):
            return DurationMeta(
                tag=tag,
                condition=duration.filter,
                anchor=source,
                controller=controller,
            )
        if isinstance(duration, DurationUntilNextStep):
            return DurationMeta(
                tag=tag,
                step=duration.step,
                owner_scoped=duration.owner_scoped,
                controller=controller,
            )
        if isinstance(duration, DurationUntilLeaves):
            return DurationMeta(
                tag=tag, leaves_anchor=leaves_anchor, controller=controller
            )
        if isinstance(duration, DurationUntilNextTurn):
            return DurationMeta(tag=tag, next_turn_owner=controller)
        return None

    # -------------------------------------------------------------- folding

    def effective_pt(
        self, identity: CardIdentity, card: Handle
    ) -> tuple[int | None, int | None]:
        """(power, toughness) after every LIVE recorded change, in the
        documented base -> timestamp -> order fold."""
        return self._effective(identity, card)

    def _effective(
        self, identity: CardIdentity, card: Handle
    ) -> tuple[int | None, int | None]:
        power = parse_pt(identity.power)
        toughness = parse_pt(identity.toughness)
        stack = self._fold_stack(card)
        for change in stack:
            if change.kind == "delta":
                if power is not None or change.power_delta:
                    base = power if power is not None else 0
                    power = base + change.power_delta
                if toughness is not None or change.toughness_delta:
                    base = toughness if toughness is not None else 0
                    toughness = base + change.toughness_delta
            else:  # "set"
                if change.power_set is not None:
                    power = change.power_set
                if change.toughness_set is not None:
                    toughness = change.toughness_set
        return power, toughness

    def _fold_stack(self, card: Handle) -> list[PtChange]:
        """The live changes for one target, ordered (created_clock,
        record_id) — the documented timestamp-then-order rule (a stable
        sort; same-clock same-target entries keep insertion order)."""
        entries = [
            c
            for c in self._changes
            if c.target == card and self._dormant.get(c.record_id) is None
        ]
        return sorted(entries, key=lambda c: (c.created_clock, c.record_id))

    # -------------------------------------------------------------- expiry

    def status(self, record_id: int) -> str:
        """``live`` | ``while_off`` | ``expired`` for one ledger entry."""
        return self._dormant.get(record_id, STATUS_LIVE)

    def meta(self, record_id: int) -> DurationMeta | None:
        return self._meta.get(record_id)

    def set_while(self, record_id: int, holds: bool) -> bool:
        """Set one WHILE entry's condition truth; returns True if the
        status actually toggled (the recompute's change signal)."""
        if record_id not in self._meta:
            raise ValueError(f"DurationLedger: no duration meta for {record_id}")
        want = None if holds else STATUS_WHILE_OFF
        was_off = self._dormant.get(record_id) == STATUS_WHILE_OFF
        if self._dormant.get(record_id) == STATUS_EXPIRED:
            return False  # terminal expiry: a while condition cannot revive
        if want is None:
            if was_off:
                del self._dormant[record_id]
                return True
            return False
        if not was_off:
            self._dormant[record_id] = STATUS_WHILE_OFF
            return True
        return False

    def settle_while(self, evaluate: Callable[[PtChange, DurationMeta], bool]) -> int:
        """Re-evaluate every live WHILE-tagged entry through ``evaluate``
        (the executor supplies the journal-relevant context). Returns the
        number of truth-changes."""
        changed = 0
        for change in self._changes:
            meta = self._meta.get(change.record_id)
            if meta is None or meta.condition is None:
                continue
            if self._dormant.get(change.record_id) == STATUS_EXPIRED:
                continue
            if self.set_while(change.record_id, evaluate(change, meta)):
                changed += 1
        return changed

    def expire(self, record_ids) -> int:
        """Terminal expiry: tombstone these entries (the dump keeps them,
        the fold and effective_pt drop them). Unknown ids are ignored —
        sweeps run speculatively over the whole log every turn."""
        expired = 0
        for record_id in record_ids:
            if (
                record_id in self._meta
                and self._dormant.get(record_id) != STATUS_EXPIRED
            ):
                self._dormant[record_id] = STATUS_EXPIRED
                expired += 1
        return expired

    def expire_leaves(self, anchor: Handle) -> int:
        """The UNTIL_LEAVES zone interceptor: terminal-expire every entry
        anchored to ``anchor``. Re-entering the zone does NOT restore (r5
        convention — expiry is terminal)."""
        return self.expire(
            rid
            for rid, meta in list(self._meta.items())
            if meta.leaves_anchor is not None and meta.leaves_anchor == anchor
        )

    def expire_at_step(
        self, step: Step, active: Handle, controller_of: Callable[[Handle], Handle]
    ) -> int:
        """The UNTIL_NEXT_STEP tick: the active player's ``step`` is
        happening. ``owner_scoped`` entries expire when the affected
        object's controller is the active player; unscoped entries bind to
        the active turn and expire on its next occurrence of the step."""
        expired = []
        for change in self._changes:
            rid = change.record_id
            meta = self._meta.get(rid)
            if meta is None or meta.step is not step:
                continue
            if self._dormant.get(rid) not in (None, STATUS_WHILE_OFF):
                continue
            if meta.owner_scoped and controller_of(change.target) != active:
                continue
            expired.append(rid)
        return self.expire(expired)

    def expire_until_next_turn(self, player: Handle) -> int:
        """The UNTIL_NEXT_TURN expiry: the recorded owner's turn is
        BEGINNING (called from the executor's begin_turn)."""
        return self.expire(
            rid
            for rid, meta in list(self._meta.items())
            if meta.next_turn_owner is not None and meta.next_turn_owner == player
        )

    def sweep_at_eot(self) -> int:
        """End-of-turn expiry sweep (the Eot tag only — 12a semantics kept
        byte-identical: a PHYSICAL removal, because a verb-level Eot buff
        has no continuing identity). Every other vocabulary expires through
        its own tombstoning path so the audit trail replays."""
        keep = [c for c in self._changes if c.tag != EOT_TAG]
        expired = len(self._changes) - len(keep)
        gone = {c.record_id for c in self._changes} - {c.record_id for c in keep}
        self._changes = keep
        for record_id in gone:
            self._meta.pop(record_id, None)
            self._dormant.pop(record_id, None)
        return expired

    # ------------------------------------------------------------- access

    def changes_for(self, card: Handle) -> tuple[PtChange, ...]:
        """EVERY change recorded for ``card`` (audit view, clock order —
        dormant/expired tombstones included; the fold is what drops them)."""
        return tuple(c for c in self._changes if c.target == card)

    def dump(self) -> tuple[tuple[object, ...], ...]:
        """A deterministic canonical view for the replay fingerprint. 12d
        extends each row with the layer-link id and the expiry status
        (live / while_off / expired) so every condition cycle and expiry is
        fingerprint-audited."""
        return tuple(
            (
                str(c.target),
                c.kind,
                c.power_delta,
                c.toughness_delta,
                c.power_set,
                c.toughness_set,
                c.tag,
                c.created_clock,
                c.was_power,
                c.was_toughness,
                c.record_id,
                self.status(c.record_id),
            )
            for c in self._changes
        )

    def __len__(self) -> int:
        return len(self._changes)
