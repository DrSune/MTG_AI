"""The menu of a player who holds priority (docs/DESIGN_PRIORITY.md §2.7).

Every action the rules allow ``seat`` now (CR 117.1), each priced with what pays it. The bench
router labels the rows and asks its seat; :func:`perform` carries one out. Rows:

- ``land:<card>``: a land drop (CR 305.1), where :func:`stack.land_playable` allows it.
- ``cast:<card>[:k][:x<N>]``: a spell in hand, base and kicked (CR 702.27), one row per X from 0
  to the largest payable X (CR 601.2b, 107.3a; no ``:x`` for X = 0).
- ``act:<card>:<index>``: a non-mana activated ability, printed or granted (a granted one is
  numbered -k-1), of a permanent the seat controls, or of a card in its hand whose cost discards
  it ("Discard this card:", Waker of Waves; ``legality.ability_playable`` opens no other zone).

Mana abilities are not rows: they are activated while paying (CR 601.2g, 605.3a). A row is offered
when the pool and the seat's mana sources pay its whole cost, a target's cost increase included
(CR 601.2f: Pursued Whale's {3}, Terror of the Peaks' 3 life; life only up to the life total, CR
119.4), and :func:`perform` taps the sources ``legality.plan_mana_taps`` picks (the registered
scaffold "Automatic payment": free sources first, then costly ones). What this gives up, a mana
ability activated for its side effect (sacrificing a Treasure in response to its removal), is
registered with that scaffold. A row whose targets cannot all be chosen (CR 601.2c:
``stack.can_designate``, a slot with too few candidates or an "another target" left without one)
is left out and counted in ``hidden``.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from itertools import count
from typing import TYPE_CHECKING, Any

from MTG_bot.core.ability_tree import (
    ActivatedAbility,
    CostTap,
    SpellAbility,
    is_mana_ability,
)
from MTG_bot.core.executor.legality import (
    MAIN_PHASES,
    _ability_discards_its_source,
    _cost_has_x,
    ability_playable,
    activate,
    kicker_of,
    plan_mana_taps,
    spell_castable,
    spell_cost,
    spell_record,
    tap_for_payment,
)
from MTG_bot.core.executor.query import (
    activation_target_slots,
    cast_mode_options,
    inert_row,
    modal_choose,
    spell_target_slots,
)
from MTG_bot.core.executor.stack import can_designate, cast, land_playable, play_land
from MTG_bot.core.identity import Handle
from MTG_bot.core.state import ZONE_BATTLEFIELD, ZONE_HAND

if TYPE_CHECKING:
    from MTG_bot.core.executor import Executor


@dataclass
class Row:
    """One action of the menu. ``slots`` are its target slots, None for a modal spell (its
    modes are announced first, CR 601.2b, and only theirs exist); ``exclude`` the permanents its
    cost taps itself (an ability's own {T}, never also tapped for mana); ``pay`` prices a cast's
    designation (``spell_target_slots``' and ``cast_mode_options``' ``pay``)."""

    token: str
    kind: str  # "land", "cast" or "activate"
    handle: Handle
    node: Any = None  # the SpellAbility cast, or the ActivatedAbility activated
    kicked: bool = False
    x: int | None = None
    ability_idx: int | None = None
    slots: list | None = None
    exclude: frozenset = frozenset()
    pay: Callable[[Sequence[Handle]], bool] | None = None


def menu(executor: Executor, seat: Handle, hidden: Counter | None = None) -> list[Row]:
    """``seat``'s actions now, PASS not included: land drops and casts in hand order, then
    activations in :func:`activated_abilities` order."""
    world = executor.world
    rows: list[Row] = []
    sources: dict = {}  # the seat's mana sources, listed once for every row priced here
    for handle in sorted(world.players[seat].zone(ZONE_HAND).entries):
        if land_playable(executor, seat, handle) is None:
            rows.append(Row(f"land:{handle}", "land", handle))
        else:
            rows.extend(_cast_rows(executor, seat, handle, hidden, sources))
    for source, idx, ability in activated_abilities(executor, seat):
        if is_mana_ability(ability):
            continue  # activated while paying (CR 605.3a), never a row
        row = _activation_row(executor, seat, source, idx, ability, hidden, sources)
        if row is not None:
            rows.append(row)
    return rows


def _cast_rows(
    executor: Executor, seat: Handle, handle: Handle, hidden: Counter | None, sources: dict
) -> list[Row]:
    """One row per payable declaration of a spell in hand: base and kicked, and one per X."""
    record = spell_record(executor, handle)
    node = next((a for a in record.abilities if isinstance(a, SpellAbility)), None) if record else None
    if node is None:
        return []
    kicker = kicker_of(record)
    rows: list[Row] = []
    for kicked in (False, True) if kicker is not None else (False,):
        extra = tuple(node.additional_costs) + ((kicker.cost,) if kicked else ())
        for x in count() if _cost_has_x(spell_cost(record, extra)) else (None,):

            def pay(targets: Sequence[Handle], kicked: bool = kicked, x: int | None = x) -> bool:
                return cast_taps(executor, seat, handle, kicked, x, tuple(targets), sources,
                                 payable_only=True) is not None

            if not pay(()):
                break  # a larger X costs more: no larger X is payable either
            slots: list[Any] | None = None
            if modal_choose(node) is None:
                slots = spell_target_slots(executor, node, spell_handle=handle, seat=seat, pay=pay)
                designable = can_designate(slots)
            else:
                # CR 601.2b-c, 700.2a: offered when some mode set is legal, i.e. its targets can
                # be chosen.
                designable = bool(cast_mode_options(executor, node, spell_handle=handle, seat=seat, pay=pay))
            if not designable:
                if hidden is not None:
                    hidden["hidden_rows"] += 1
                break
            token = f"cast:{handle}{':k' if kicked else ''}{f':x{x}' if x else ''}"
            rows.append(Row(token, "cast", handle, node, kicked, x, slots=slots, pay=pay))
    return rows


def _activation_row(
    executor: Executor, seat: Handle, source: Handle, idx: int, ability: ActivatedAbility,
    hidden: Counter | None, sources: dict,
) -> Row | None:
    # An ability whose cost taps its own source cannot also tap that source for mana.
    own_tap = any(isinstance(part, CostTap) and part.target is None for part in ability.cost.parts)
    exclude = frozenset({source}) if own_tap else frozenset()
    if activation_taps(executor, seat, source, idx, exclude, sources, payable_only=True) is None:
        return None
    if inert_row(executor, ability, source, seat):
        return None  # a phantom option: it could do nothing (Radha's land row)
    slots = list(activation_target_slots(executor, ability.effect, source=source, seat=seat))
    if not can_designate(slots):
        if hidden is not None:
            hidden["hidden_rows"] += 1
        return None
    return Row(f"act:{source}:{idx}", "activate", source, ability, ability_idx=idx, slots=slots, exclude=exclude)


def sorcery_timing(executor: Executor, seat: Handle) -> bool:
    """Whether ``seat`` may act at sorcery speed now (CR 117.1a, 307.1): its own turn, one of its
    main phases, an empty stack."""
    return (
        executor.world.active_player == seat
        and executor.turn_open
        and executor.phase in MAIN_PHASES
        and not executor.stack.frames
    )


def activated_abilities(executor: Executor, seat: Handle) -> list[tuple[Handle, int, ActivatedAbility]]:
    """Every activated ability ``seat`` may consider, unpriced: of the permanents it controls,
    printed and granted (a granted one is numbered -k-1), and of the cards in its hand the ones
    that work there (``legality._ability_discards_its_source``); sorted by source and index."""
    world = executor.world
    rows: list[tuple[Handle, int, ActivatedAbility]] = []
    for handle in (h for p in world.player_order for h in world.players[p].zone(ZONE_BATTLEFIELD).entries):
        if executor.controller_of(handle) != seat:
            continue
        record = executor.binder.handle_record.get(handle)
        printed = list(enumerate(record.abilities)) if record is not None else []
        granted = [(-k - 1, entry.node) for k, entry in enumerate(executor.layers.granted_activated(handle))]
        rows += [(handle, idx, ab) for idx, ab in printed + granted if isinstance(ab, ActivatedAbility)]
    for handle in world.players[seat].zone(ZONE_HAND).entries:
        record = spell_record(executor, handle)
        if record is None:
            continue
        rows += [
            (handle, idx, ab)
            for idx, ab in enumerate(record.abilities)
            if isinstance(ab, ActivatedAbility) and _ability_discards_its_source(ab)
        ]
    rows.sort(key=lambda row: (row[0], row[1]))
    return rows


def cast_taps(
    executor: Executor, seat: Handle, handle: Handle, kicked: bool, x: int | None,
    targets: tuple[Handle, ...], sources: dict | None = None, payable_only: bool = False,
) -> Any:
    """The mana sources that pay this declaration's total cost (CR 601.2f-h) with what the pool
    holds: () when the pool pays it, None when nothing does. ``sources``: a menu build's shared
    listing; ``payable_only``: only whether it can be paid (``legality.plan_mana_taps``)."""
    return plan_mana_taps(
        executor, seat, lambda: spell_castable(executor, seat, handle, x=x, kicked=kicked, targets=targets)[0],
        keep=frozenset(targets), costly=True, sources=sources, payable_only=payable_only,
    )


def activation_taps(
    executor: Executor, seat: Handle, source: Handle, idx: int, exclude: frozenset,
    sources: dict | None = None, payable_only: bool = False, targets: tuple[Handle, ...] = (),
) -> Any:
    """The mana sources, never one in ``exclude``, that pay an activation; as :func:`cast_taps`."""
    return plan_mana_taps(
        executor, seat, lambda: ability_playable(executor.world, executor, source, idx, seat=seat),
        exclude=exclude, keep=frozenset(targets), costly=True, sources=sources,
        payable_only=payable_only,
    )


def perform(
    executor: Executor, seat: Handle, row: Row, targets: tuple = (), modes: tuple[int, ...] = ()
) -> bool:
    """Carry out ``row`` with its designation (one slot's targets, or one tuple per slot) and a
    modal spell's declared modes: tap the sources that pay it, then play the land, cast the spell
    or activate the ability. False, with nothing done, when the targets together cost more than
    the sources pay (each candidate was priced alone; two taxed targets, CR 601.2f)."""
    if row.kind == "land":
        play_land(executor, seat, row.handle)
        return True
    flat = tuple(h for t in targets for h in ((t,) if isinstance(t, Handle) else t))
    if row.kind == "activate":
        assert row.ability_idx is not None
        taps = activation_taps(executor, seat, row.handle, row.ability_idx, row.exclude, targets=flat)
        if taps is None:
            return False
        tap_for_payment(executor, seat, taps)
        activate(executor, row.handle, row.ability_idx, seat=seat, targets=targets)
        return True
    taps = cast_taps(executor, seat, row.handle, row.kicked, row.x, flat)
    if taps is None:
        return False
    tap_for_payment(executor, seat, taps)
    cast(executor, seat, row.handle, x=row.x, kicked=row.kicked, mode_choices=modes, targets=targets)
    return True
