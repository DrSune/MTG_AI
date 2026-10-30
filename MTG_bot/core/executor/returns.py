"""The return registry: zone moves "until" an event (ontology R5-1, 2026-10-29; CR 610.3).

"Exile that card until this creature leaves the battlefield" is two one-shot effects (CR 610.3):
the move, and a second one created immediately after the specified event, which returns the object
to its previous zone. A MOVE_ZONE atom with a ``duration`` role makes the move and leaves one row
here per moved object; the executor ends the rows when their duration ends and runs the return as
one simultaneous batch (CR 610.3d, ``Executor._run_returns``).

A row holds the object, the journal clock of its arrival in the destination zone, the zone it came
from, its owner, and the duration with its anchor as resolved when the effect began. Handles are
stable across zone moves (``identity.py``), while CR 400.7 makes a moved card a new object, so
"still the same object" is read from journal provenance, as WAS_KICKED reads it
(``quantity._permanent_was_kicked``): no ZONE_CHANGE row since its arrival moved it out of that
zone.

The registry is replayed state: :meth:`ReturnRegistry.dump` feeds the executor's replay fingerprint
(only while a row exists, so a replay that never uses it keeps its bytes), and the per-seat view
(``bench/view.py``) and the G1 probe show every row.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from MTG_bot.core.executor.events import KIND_CAST, KIND_ZONE_CHANGE, GameEvent
from MTG_bot.core.identity import Handle
from MTG_bot.core.state import ZONE_BATTLEFIELD, ZONE_STACK

if TYPE_CHECKING:
    from MTG_bot.core.executor import Executor
    from MTG_bot.core.executor.events import EventJournal
    from MTG_bot.core.executor.quantity import ExecCtx

#: The duration tags a row can carry: ``durations.duration_tag`` of the three nodes a MOVE_ZONE
#: accepts (``ability_tree._MOVE_ZONE_DURATIONS``).
TAG_UNTIL_LEAVES = "UntilLeaves"
TAG_EOT = "Eot"
TAG_UNTIL_NEXT_TURN = "UntilNextTurn"


@dataclass(frozen=True)
class ReturnRow:
    """One moved object waiting for its duration to end (CR 610.3)."""

    seq: int  # registry-monotone id: the deterministic order of the rows
    card: Handle  # the moved object
    zone: str  # the zone the move put it in (a state zone kind)
    entry_clock: int  # journal clock of the ZONE_CHANGE row that put it there (CR 400.7)
    previous_zone: str  # where it returns: the zone it came from
    owner: Handle  # it returns to its owner's zone, onto the battlefield under its owner (610.3c)
    tag: str  # TAG_UNTIL_LEAVES | TAG_EOT | TAG_UNTIL_NEXT_TURN
    anchor: Handle | None  # UntilLeaves: the object whose leaving the battlefield ends it
    anchor_clock: int  # the anchor's battlefield-entry clock when the effect began (0: none)
    source: Handle  # the ability's source: the return's journal cause
    controller: Handle  # the effect's controller (UntilNextTurn: whose next turn ends it)


@dataclass(frozen=True)
class _Staged:
    """A row the verb made inside its atom; the entry clock is known once the journal records the
    atom's boundary (:meth:`ReturnRegistry.complete`)."""

    card: Handle
    zone: str
    previous_zone: str
    owner: Handle
    tag: str
    anchor: Handle | None
    anchor_clock: int
    source: Handle
    controller: Handle


# ------------------------------------------------------------------ journal reads


def left_zone_since(journal: EventJournal, card: Handle, zone: str, clock: int) -> bool:
    """Did a journal row after ``clock`` move ``card`` out of ``zone``? (CR 400.7: the object in
    that zone now, if any, is then a new one.) Reading departures rather than "the latest row"
    keeps the answer right when an enclosing atom boundary journals a nested move a second time."""
    for event in reversed(journal.events):
        if event.clock <= clock:
            return False
        if (
            event.kind == KIND_ZONE_CHANGE
            and event.subject == card
            and event.zone_move[0] == zone
        ):
            return True
    return False


def battlefield_entry_clock(journal: EventJournal, card: Handle) -> int:
    """The clock of ``card``'s latest arrival on the battlefield; 0 when no such row exists (a card
    placed there before the journal began, as a pack's setup does)."""
    for event in reversed(journal.events):
        if (
            event.kind == KIND_ZONE_CHANGE
            and event.subject == card
            and event.zone_move[1] == ZONE_BATTLEFIELD
        ):
            return event.clock
    return 0


def effect_began_clock(ctx: ExecCtx) -> int | None:
    """When the effect's ability triggered (CR 610.3b: the triggering event's clock) or its spell
    was cast (610.3a: the spell's CAST row; only its costs come between being put on the stack and
    that row, and an anchor removed by a cost is caught by the presence check), as a journal clock.
    None for an effect with neither: an activated ability resolves inline right after its costs, so
    only the anchor's presence can be checked."""
    event = ctx.event
    if isinstance(event, GameEvent) and event.clock > 0:
        return event.clock
    journal = ctx.journal
    source = ctx.source
    if (
        journal is not None
        and source.namespace == "card"
        and source in ctx.world.cards
        and ctx.world.zone_of(source).kind == ZONE_STACK
    ):
        for row in reversed(journal.events):
            if row.kind == KIND_CAST and row.subject == source:
                return row.clock
    return None


def anchor_unmoved(ctx: ExecCtx, anchor: Handle) -> bool:
    """CR 610.3a/b: is the anchor still the battlefield object it was when the effect began? False
    if it is not on the battlefield, or if it left the battlefield after the ability triggered or
    the spell was put on the stack; then the "until" event has already happened and the object does
    not move. Phasing is not leaving (702.26d), so a phased-out anchor still counts."""
    world = ctx.world
    if anchor.namespace != "card" or anchor not in world.cards:
        return False
    if world.zone_of(anchor).kind != ZONE_BATTLEFIELD:
        return False
    began = effect_began_clock(ctx)
    if began is None or ctx.journal is None:
        return True
    return not left_zone_since(ctx.journal, anchor, ZONE_BATTLEFIELD, began)


# ------------------------------------------------------------------ the registry


class ReturnRegistry:
    """Rows of objects moved "until" an event (CR 610.3), in creation order."""

    def __init__(self) -> None:
        self.rows: list[ReturnRow] = []
        self._staged: list[_Staged] = []
        self._seq = 0

    def stage(
        self,
        card: Handle,
        *,
        zone: str,
        previous_zone: str,
        owner: Handle,
        tag: str,
        anchor: Handle | None,
        anchor_clock: int,
        source: Handle,
        controller: Handle,
    ) -> None:
        """The verb moved ``card``; the row goes live when its atom's boundary is journalled."""
        self._staged.append(
            _Staged(card, zone, previous_zone, owner, tag, anchor, anchor_clock, source, controller)
        )

    def complete(self, events: Sequence[GameEvent]) -> None:
        """Give each staged row its entry clock from the atom's journalled ZONE_CHANGE rows. A
        staged object with no such row never arrived (a replacement sent it elsewhere): there is
        nothing to return, so it gets no row."""
        staged, self._staged = self._staged, []
        for s in staged:
            clock = next(
                (
                    e.clock
                    for e in events
                    if e.kind == KIND_ZONE_CHANGE
                    and e.subject == s.card
                    and e.zone_move[1] == s.zone
                ),
                None,
            )
            if clock is None:
                continue
            self._seq += 1
            self.rows.append(
                ReturnRow(
                    seq=self._seq,
                    card=s.card,
                    zone=s.zone,
                    entry_clock=clock,
                    previous_zone=s.previous_zone,
                    owner=s.owner,
                    tag=s.tag,
                    anchor=s.anchor,
                    anchor_clock=s.anchor_clock,
                    source=s.source,
                    controller=s.controller,
                )
            )

    # ------------------------------------------------------------------ ending

    def _end(self, ends: Callable[[ReturnRow], bool]) -> list[ReturnRow]:
        ended = [r for r in self.rows if ends(r)]
        if ended:
            self.rows = [r for r in self.rows if not ends(r)]
        return ended

    def end_leaves(self, anchor: Handle) -> list[ReturnRow]:
        """``anchor`` left the battlefield: every row anchored on it ends."""
        return self._end(lambda r: r.tag == TAG_UNTIL_LEAVES and r.anchor == anchor)

    def end_eot(self) -> list[ReturnRow]:
        """The cleanup step (CR 514.2): every "until end of turn" row ends."""
        return self._end(lambda r: r.tag == TAG_EOT)

    def end_next_turn(self, player: Handle) -> list[ReturnRow]:
        """``player``'s turn begins: their "until your next turn" rows end."""
        return self._end(lambda r: r.tag == TAG_UNTIL_NEXT_TURN and r.controller == player)

    # ------------------------------------------------------------------ reads

    @staticmethod
    def still_there(executor: Executor, row: ReturnRow) -> bool:
        """Is the row's object the same object, still in the zone the move put it in (CR 400.7)?
        It is when it sits in that zone and no journal row since its arrival moved it out of that
        zone: a card that left and came back is a new object. A token has ceased to exist
        (CR 704.5d), whatever zone it sits in."""
        world = executor.world
        card = row.card
        if card not in world.cards:
            return False
        if world.cards[card].identity.is_token:
            return False
        record = executor.binder.handle_record.get(card)
        if record is not None and getattr(record, "is_token", False):
            return False
        if world.zone_of(card).kind != row.zone:
            return False
        return not left_zone_since(executor.journal, card, row.zone, row.entry_clock)

    def rows_for(self, card: Handle) -> tuple[ReturnRow, ...]:
        """The live rows of ``card`` (at most one per object in practice)."""
        return tuple(r for r in self.rows if r.card == card)

    def dump(self) -> tuple[tuple[object, ...], ...]:
        """A deterministic canonical view for the replay fingerprint."""
        return tuple(
            (
                r.seq,
                str(r.card),
                r.zone,
                r.entry_clock,
                r.previous_zone,
                str(r.owner),
                r.tag,
                str(r.anchor),
                r.anchor_clock,
                str(r.source),
                str(r.controller),
            )
            for r in self.rows
        )

    def __len__(self) -> int:
        return len(self.rows)
