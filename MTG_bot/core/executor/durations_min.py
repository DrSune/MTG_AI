"""Minimal end-of-turn duration ledger (round 12a, plan /06 §12a, ruling 1).

The Phase-0 :class:`~MTG_bot.core.state.GameWorld` is FROZEN through 12c
(ruling 1: state.py carries no PT-modification fields and gains none), so
temporary P/T changes live here, on the executor side. Per ruling 1 the
default is "the executor-side DurationLedger *is* the replayed state": a
replay rebuilds the ledger by replaying the same atoms, and the ledger's
:attr:`DurationLedger.dump` participates in the executor's replay
fingerprint exactly like the world's own fingerprint does for zones and
life.

Conventions honoured:
  * **C18 was-snapshots** — every recorded change stores the target's
    *effective* P/T at application time (``was_power``/``was_toughness``),
    so a SET_PT under a Duration is auditable and revertible by inspection.
  * Determinism — the ledger is an ordered list; :meth:`effective_pt`
    applies entries in insertion (clock) order, never a dict iteration.
  * Minimal vocab — only :class:`DurationEot` expires here (:meth:`
    sweep_at_eot`); the rest of the Duration vocab (WHILE_CONDITION,
    UNTIL_NEXT_STEP, UNTIL_LEAVES, UNTIL_NEXT_TURN semantics) is 12d.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from MTG_bot.core.ability_tree import (
    Duration,
    DurationEot,
    DurationPermanent,
    DurationUntilNextTurn,
)
from MTG_bot.core.identity import CardIdentity, Handle

# Duration IR node -> ledger expiry tag. Only "Eot" is swept in 12a; the
# other tags record honestly but never expire until 12d builds the vocab.
_DURATION_TAG: Dict[type, str] = {
    DurationEot: "Eot",
    DurationPermanent: "Permanent",
    DurationUntilNextTurn: "UntilNextTurn",
}

# The one expiry 12a implements.
EOT_TAG = "Eot"


def duration_tag(duration: Duration | None) -> str:
    """The ledger expiry tag for a Duration IR node; absent = permanent."""
    if duration is None:
        return "Permanent"
    tag = _DURATION_TAG.get(type(duration))
    if tag is None:
        raise NotImplementedError(
            f"executor: duration {type(duration).__name__} not implemented (12d)"
        )
    return tag


def parse_pt(value: Optional[str]) -> Optional[int]:
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
    P/T at application time.
    """

    target: Handle
    kind: str  # "delta" | "set"
    power_delta: int
    toughness_delta: int
    power_set: Optional[int]
    toughness_set: Optional[int]
    tag: str  # "Eot" | "Permanent" | "UntilNextTurn"
    created_clock: int
    was_power: Optional[int]
    was_toughness: Optional[int]


class DurationLedger:
    """The executor-side record of temporary and permanent P/T changes.

    :meth:`effective_pt` folds the entries for one card in insertion order
    (base printed P/T, then clock-ordered delta/set applications), which is
    what lethal-damage checks and QProp POWER/TOUGHNESS read (plan /06:
    "use ledger-modified PT if set — keep simple base+ledger").
    """

    def __init__(self) -> None:
        self._changes: List[PtChange] = []

    def record(
        self,
        identity: CardIdentity,
        change_kind: str,
        target: Handle,
        power_delta: int = 0,
        toughness_delta: int = 0,
        power_set: Optional[int] = None,
        toughness_set: Optional[int] = None,
        tag: str = "Permanent",
        clock: int = 0,
    ) -> PtChange:
        """Append one change, snapshotting the target's effective P/T (C18)."""
        if change_kind not in ("delta", "set"):
            raise ValueError(f"DurationLedger: unknown change kind {change_kind!r}")
        was_power, was_toughness = self._effective(identity, target)
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
        )
        self._changes.append(change)
        return change

    def effective_pt(
        self, identity: CardIdentity, card: Handle
    ) -> Tuple[Optional[int], Optional[int]]:
        """(power, toughness) after all recorded changes, in clock order."""
        return self._effective(identity, card)

    def _effective(
        self, identity: CardIdentity, card: Handle
    ) -> Tuple[Optional[int], Optional[int]]:
        power = parse_pt(identity.power)
        toughness = parse_pt(identity.toughness)
        for change in self._changes:
            if change.target != card:
                continue
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

    def changes_for(self, card: Handle) -> Tuple[PtChange, ...]:
        """Every change recorded for ``card``, in clock order."""
        return tuple(c for c in self._changes if c.target == card)

    def sweep_at_eot(self) -> int:
        """End-of-turn expiry sweep (minimal: the Eot tag only).

        Returns the number of expired entries. Entries tagged otherwise
        persist — until-next-turn/while/step/leaves expiry is 12d.
        """
        keep = [c for c in self._changes if c.tag != EOT_TAG]
        expired = len(self._changes) - len(keep)
        self._changes = keep
        return expired

    def dump(self) -> Tuple[Tuple[object, ...], ...]:
        """A deterministic canonical view for the replay fingerprint."""
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
            )
            for c in self._changes
        )

    def __len__(self) -> int:
        return len(self._changes)
