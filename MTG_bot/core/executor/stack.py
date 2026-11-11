"""The stack and the casting pipeline.

A cast is one action (CR 601.2), as an activation is: re-check legality,
choose modes/targets/X (601.2b-c), determine and LOCK the total cost
(601.2f), pay (601.2g, inside ``Executor.atomic``), put the spell on the
stack (601.2h). It waits there: the caster receives priority again (CR
117.3c), what casting triggered goes on the stack above it, and when every
player has passed in succession the top object resolves (CR 117.4,
:func:`resolve_top`), the spell's card then moving to its
after-resolution zone (601.2j / 400.7). In a game loop the players decide
at every priority point (``Executor.driven``); outside one both pass at
once. A countered spell leaves the stack (CR 701.6a). Every declaration
field the CR makes public (601.2b-e: modes, targets, X, total cost, timing
choices) is stored on :class:`StackObject` and journalled.

Stack placement: :mod:`MTG_bot.core.state` declares ``ZONE_STACK`` but keeps
it OUT of ``PLAYER_ZONES``, and the world fingerprint
(:meth:`GameWorld.fingerprint`) iterates exactly ``PLAYER_ZONES``, so a card
parked in the stack zone is INVISIBLE to it. This module parks cards in a
per-player ``ZONE_STACK`` :class:`~MTG_bot.core.state.ZoneState` created on
first use (``zone_of``/``move_card`` see it), and the executor fingerprint
(``Executor.state_fingerprint``) folds in :meth:`SpellStack.dump`: two worlds
differing only by a card on the stack MUST produce different executor
fingerprints (pinned by ``test_stack_frame_fold_changes_the_fingerprint``).

LIFO: :attr:`Executor.stack` is a list, append = push, resolve = pop the top
(CR 405). A spell cast in response is pushed above what it answers and
resolves first.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from itertools import combinations
from typing import TYPE_CHECKING

from MTG_bot.core.ability_tree import (
    BackFace,
    Choose,
    Cost,
    FAtom,
    FAtomPred,
    SpellAbility,
    SpellKind,
    walk,
)
from MTG_bot.core.executor.decisions import site_digest
from MTG_bot.core.executor.legality import (
    MAIN_PHASES,
    PaymentPlan,
    _cost_has_x,
    build_payment_plan,
    ctx_for,
    pay_costs,
    protected_from,
    spell_castable,
    spell_cost,
    spell_record,
)
from MTG_bot.core.executor.offers import offer_or_autopick
from MTG_bot.core.executor.quantity import Binding
from MTG_bot.core.identity import Handle
from MTG_bot.core.state import (
    ZONE_BATTLEFIELD,
    ZONE_EXILE,
    ZONE_GRAVEYARD,
    ZONE_STACK,
    GameWorld,
    ZoneState,
)

if TYPE_CHECKING:  # pragma: no cover - import cycle guard only
    from MTG_bot.core.executor import Executor

# Where a resolved spell's card goes (CR 601.2j + 400.7). INSTANT/SORCERY
# are the only non-permanent kinds; PLANESWALKER enters with its printed
# loyalty, which the binder seeds at registration (binding._register).
_PERMANENT_KINDS = frozenset(
    {
        SpellKind.CREATURE,
        SpellKind.ENCHANTMENT,
        SpellKind.PLANESWALKER,
        SpellKind.LAND,
        SpellKind.ARTIFACT,
    }
)


@dataclass
class StackObject:
    """One object on the stack (CR 405.1): the 601.2b–e declaration record,
    public on the stack, and what its resolution reads (CR 608).

    * ``node`` — the :class:`SpellAbility` IR (the same object
      ``legal_casts`` returned and resolution runs);
    * ``x_value`` — the locked X (601.2f — X is chosen with the total cost
      and can no longer change);
    * ``declared_targets`` — the designation tuple (601.2c; canonical
      Handle-sort);
    * ``mode_choices`` — a modal spell's declared mode set (601.2b), as the
      set's index in ``query.choose_options`` order: the token the runtime
      Choose consumes at resolution instead of asking again;
    * ``payment`` — the determined-and-locked plan (601.2f's total);
    * ``declared_clock`` — the journal clock the frame was pushed at;
    * ``kicked`` — CR 702.27a: was the optional kicker cost paid with the
      total cost? The same truth rides the journalled CAST row (the
      durable carrier WAS_KICKED reads); the frame keeps it visible on the
      stack for the players and the diagnostics dump;
    * ``decisions``, ``slot_designations``, ``target_node`` — what the
      resolution reads and the declaration made: the per-op decision pool
      left after the modes and targets were taken from it, a multi-target
      spell's per-slot designation (:func:`designate_slots`), and what the
      targets are checked against again (CR 608.2b): a spell's node narrowed
      to its declared modes, a triggered ability's TARGET Selector.

    A countered object leaves the stack at once (CR 701.6a), so whoever
    pushed it tells it was countered by its absence.
    """

    handle: Handle
    node: SpellAbility
    controller: Handle
    spell_kind: str
    x_value: int | None = None
    declared_targets: tuple[Handle, ...] = ()
    mode_choices: tuple[int, ...] = ()
    payment: PaymentPlan | None = None
    declared_clock: int = 0
    from_zone: str | None = None
    kicked: bool = False
    decisions: tuple[str, ...] = ()
    slot_designations: dict[str, tuple[Handle, ...]] = field(default_factory=dict)
    target_node: object = None
    # An ability on the stack (CR 113.1b, 405.1; ``spell_kind`` ACTIVATED or
    # TRIGGERED, ``handle`` its own, in the "ability" namespace): ``node`` is
    # the ability itself, never an index (a granted ability's index can shift
    # while it waits, CR 113.7a), ``source`` the object it came from, and
    # ``ability_idx`` only names it in event rows. A triggered ability keeps
    # the event that triggered it and the context its modes and targets were
    # chosen in (CR 603.3c-d), which its resolution runs in.
    source: Handle | None = None
    ability_idx: int | None = None
    event: object = None
    ctx: object = None


@dataclass
class SpellStack:
    """Executor-side stack container: the LIFO frame list + the deterministic
    dump the fingerprint folds."""

    frames: list[StackObject] = field(default_factory=list)

    def push(self, frame: StackObject) -> None:
        self.frames.append(frame)

    def pop(self) -> StackObject:
        if not self.frames:
            raise ValueError("executor: stack resolution with an empty stack")
        return self.frames.pop()

    def dump(self) -> tuple[tuple[object, ...], ...]:
        """Canonical LIFO view (bottom → top) for the replay fingerprint:
        a parked card MUST change this row — the hidden-state-hole guard
        (two worlds differing only by a stack card must differ here)."""
        return tuple(
            (
                i,
                str(f.handle),
                f.spell_kind,
                str(f.controller),
                f.x_value,
                tuple(str(h) for h in f.declared_targets),
                f.mode_choices,
                repr(f.payment) if f.payment is not None else None,
                f.declared_clock,
                f.from_zone,
                f.kicked,
                f.decisions,
                tuple(sorted((k, tuple(map(str, v))) for k, v in f.slot_designations.items())),
            )
            for i, f in enumerate(self.frames)
        )


# ------------------------------------------------------------------ parking


def stack_zone(world: GameWorld, seat: Handle) -> ZoneState:
    """The per-player ``ZONE_STACK`` slot, created on first use (a player is
    built with ``PLAYER_ZONES`` only). The world fingerprint loop iterates
    ``PLAYER_ZONES`` and skips it BY DESIGN — :meth:`SpellStack.dump`'s fold
    is what makes the stack visible to the replay fingerprint (pinned by
    ``test_stack_frame_fold_changes_the_fingerprint``)."""
    player = world.players[seat]
    zone = player.zones.get(ZONE_STACK)
    if zone is None:
        zone = ZoneState(
            handle=Handle("stackzone", seat.index),
            kind=ZONE_STACK,
            controller=seat,
        )
        player.zones[ZONE_STACK] = zone
    return zone


def park(executor: Executor, seat: Handle, handle: Handle) -> ZoneState:
    """Move ``handle`` from its current zone into the stack zone (CR
    601.2h: the spell LEAVES its origin zone). Journalled by the caller's
    snapshot boundary."""
    zone = stack_zone(executor.world, seat)
    executor.world.move_card(handle, zone)
    return zone


# ---------------------------------------------------------------- legality


def is_land_card(world: GameWorld, handle: Handle) -> bool:
    """A card PLAYABLE as a land: the printed type line carries the Land
    type word (``CardIdentity`` has no structured types field — the
    data-only word test, same convention as TYPE_EQ). The corpus'
    lands carry no SpellAbility node (they compile to a bare {T}
    ActivatedAbility), which is exactly why the land drop is its own option
    shape on the ``legal_casts`` surface."""
    from MTG_bot.core.executor.quantity import _type_line_tokens

    state = world.cards.get(handle)
    if state is None:
        return False
    return "Land" in _type_line_tokens(state.identity.type_line)


def land_playable(executor: Executor, seat: Handle, handle: Handle) -> str | None:
    """Why this land cannot be played by ``seat`` right now (``None`` =
    legal). Gates: the card is a land in the seat's hand, the seat's turn
    is open, the phase is one of the seat's main phases (CR 305.1, 505.6b:
    :data:`legality.MAIN_PHASES`, which reads a world with no turn begun, a
    bare test rig, as inside), the stack is empty, and the allowance, one
    land per turn in total across both main phases (CR 305.2, 505.6b)
    widened by ``executor.extra_land_plays`` + the live ADD_LAND_PLAY layer
    sum."""
    world = executor.world
    if not is_land_card(world, handle):
        return "land:not_a_land"
    if world.zone_of(handle) != world.players[seat].zone("hand"):
        return f"land:not_in_hand:{handle}"
    if world.active_player != seat or not executor.turn_open:
        return "land:not_own_turn"
    if executor.phase not in MAIN_PHASES:
        return "land:phase"
    if executor.stack.frames:
        return "land:stack_nonempty"
    turn, plays = executor.land_ledger.get(seat, (world.turn, 0))
    if turn != world.turn:
        plays = 0
    allowance = 1 + executor.extra_land_plays + executor.layers.land_play_bonus(seat)
    if plays >= allowance:
        return f"land:used_this_turn:{plays}>={allowance}"
    return None


# ----------------------------------------------------------------- casting


def _validate_spell_targets(
    executor: Executor,
    seat: Handle,
    handle: Handle,
    node: SpellAbility,
    targets: tuple[Handle, ...],
) -> None:
    """CR 601.2c designation checks, raising ``ValueError(reason)``:
    TARGET-mode selectors are validated through the query surface's own
    :func:`validate_target_selection` (the SAME oracle
    ``legal_targets`` feeds a Slate); the TARGET_PLAYER
    channel (compiled "target opponent", a ControllerRef with NO selector
    to validate — the grammar's documented representational gap) is
    checked as a player-coordinate rule: an opponent seat of the caster.
    Several selectors are designated per slot (:func:`designate_slots`)."""
    from MTG_bot.core.executor.query import (
        spell_target_slots,
        validate_target_selection,
    )

    slots = spell_target_slots(executor, node, spell_handle=handle, seat=seat)
    if not targets and not slots:
        return  # targetless spell — the common case
    # A spell WITH a slot (TARGET selector or the synthesized aura ENCHANT
    # slot) that designated nothing falls through to the validator
    # (count_below_min) — never a silent targetless resolution (an
    # Enthralling Hold with no target would resolve as a no-op).
    if not slots:
        # TARGET_PLAYER-only designation (Duress shape): every entry must
        # be a player the caster's opponents include.
        for t in targets:
            if t.namespace != "player":
                raise ValueError(
                    f"executor: cast: target-player designation needs a "
                    f"player handle, got {t}"
                )
            if t == seat:
                raise ValueError(
                    "executor: cast: TARGET_PLAYER designation is the "
                    "caster themselves — not an opponent"
                )
            if protected_from(executor, t, handle):
                raise ValueError(
                    "executor: cast: illegal target selection: the player has "
                    "protection from this spell (CR 702.16b)"
                )
        return
    if len(slots) > 1:
        designate_slots(slots, targets)
        return
    reason = validate_target_selection(slots[0], targets)
    if reason is not None:
        raise ValueError(f"executor: cast: illegal target selection: {reason}")


#: One designation of several target slots (CR 601.2c): per slot, the targets
#: announced for it, () for an "up to" slot left empty.
SlotGroups = tuple[tuple[Handle, ...], ...]


def slot_groups(slots: list, targets: Sequence) -> SlotGroups:
    """The designation of each of ``slots``, in walk order (CR 601.2c: the
    targets are announced for each instance of the word "target"). Two
    spellings of ``targets``: one tuple of handles per slot (() leaves an "up
    to" slot empty, a slot of "two target creatures" takes two), or flat, the
    i-th handle designating the i-th slot and the slots after the last handle
    empty (one target per slot: packs and tests). Raises ``ValueError`` on a
    count that fits neither."""
    if targets and all(not isinstance(t, Handle) for t in targets):
        if len(targets) != len(slots):
            raise ValueError(
                f"{len(slots)} TARGET slots need {len(slots)} designations, got {len(targets)}"
            )
        return tuple(tuple(group) for group in targets)
    if any(not isinstance(t, Handle) for t in targets):
        raise ValueError("a designation is one tuple per slot or one handle per slot, not both")
    required = sum(1 for s in slots if s.min_count >= 1)
    if not required <= len(targets) <= len(slots):
        need = f"{required} to {len(slots)}" if required < len(slots) else f"{len(slots)}"
        raise ValueError(f"{len(slots)} TARGET slots need {need} designations, got {len(targets)}")
    return tuple((t,) for t in targets) + ((),) * (len(slots) - len(targets))


def designate_slots(
    slots: list,
    targets: Sequence,
    *,
    skip: frozenset[int] | set[int] = frozenset(),
    stand_in=None,
    lane: str = "cast",
) -> dict[str, tuple[Handle, ...]]:
    """A MULTI-slot designation (CR 601.2c), the cast and activation lanes'
    one rule. :func:`slot_groups` reads ``targets``; each slot's group is
    validated against its OWN slot by the query's oracle
    (``validate_target_selection``: its population, its count, and no object
    twice for one word "target", CR 115.3), and an "another target" slot must
    not share a target with another slot (:func:`another_target_reason`). The
    same object MAY fill two plain "target" words (CR 115.3). Returns the
    repr-keyed per-slot map the effect runtime threads into
    ExecCtx.slot_designations; a slot left empty maps to (), so its TARGET
    selector acts on nothing instead of reading the spell-wide binding.
    ``skip``: slots auto-designated by the self-clause (CR 115.4,
    :func:`_plan_cast_designation`), trusted by construction. ``stand_in``:
    the handle a slot is judged on (the activation lane's synthesized player
    slot reads a card as its controller). Raises
    ``ValueError("executor: <lane>: ...")``."""
    from MTG_bot.core.executor.query import validate_target_selection

    try:
        groups = slot_groups(slots, targets)
    except ValueError as e:
        raise ValueError(f"executor: {lane}: {e}") from None
    for i, (slot, group) in enumerate(zip(slots, groups, strict=True)):
        if i in skip:
            continue
        judged = group if stand_in is None else tuple(stand_in(slot, h) for h in group)
        reason = validate_target_selection(slot, tuple(sorted(judged)))
        if reason is not None:
            raise ValueError(f"executor: {lane}: illegal target selection: {reason}")
    reason = another_target_reason(slots, groups)
    if reason is not None:
        raise ValueError(f"executor: {lane}: illegal target selection: {reason}")
    return {repr(slot.selector): tuple(sorted(g)) for slot, g in zip(slots, groups, strict=True)}


def can_designate(slots: list, chosen: SlotGroups = ()) -> bool:
    """Can the slots after the designated ``chosen`` (one group per slot so
    far) each still take its minimum number of targets without breaking an
    "another target" (CR 601.2c: a spell or ability with a target that cannot
    be chosen cannot be cast or activated)? For one slot: it has enough
    candidates. The drivers' gate before they offer a row."""
    if another_target_reason(slots[: len(chosen)], chosen) is not None:
        return False
    if len(chosen) == len(slots):
        return True
    slot = slots[len(chosen)]
    return any(
        can_designate(slots, (*chosen, group))
        for group in combinations(slot.candidates, slot.min_count)
    )


def slot_options(slots: list, chosen: SlotGroups, picked: Sequence[Handle] = ()) -> tuple[Handle, ...]:
    """The candidates the next pick of slot ``len(chosen)`` may take, after
    the earlier slots' groups ``chosen`` and this slot's ``picked``: not
    already picked for this slot (CR 115.3), and leaving the designation
    completable, this slot up to its minimum and every later slot
    (:func:`can_designate`). The drivers ask one target question per pick
    from this (CR 601.2c), so no illegal pair is ever offered, and a slot's
    minimum reached, ending it there is completable too."""
    slot = slots[len(chosen)]

    def completes(group: tuple[Handle, ...]) -> bool:
        rest = [c for c in sorted(slot.candidates) if c not in group]
        need = max(0, slot.min_count - len(group))
        return any(can_designate(slots, (*chosen, (*group, *more))) for more in combinations(rest, need))

    return tuple(c for c in sorted(slot.candidates) if c not in picked and completes((*picked, c)))


def recheck_targets(
    executor: Executor,
    slots: list,
    targets: Sequence[Handle],
    *,
    own: Handle | None = None,
    designations: dict[str, tuple[Handle, ...]] | None = None,
) -> tuple[tuple[Handle, ...], dict[str, tuple[Handle, ...]] | None]:
    """CR 608.2b: as a spell or ability resolves, each of its targets is checked again against
    the slot it was chosen for, ``slots`` recomputed now (the same populations the choice
    was made from: zone, filter, protection and hexproof). Returns the targets still legal,
    and for a multi-slot designation (``designations``, :func:`designate_slots`' map) the
    per-slot map with each illegal target dropped from its slot (that slot's TARGET selector
    then acts on what is left, possibly nothing; CR 608.2b: an illegal target is not
    affected). With every target illegal the first value is empty and the caller does not
    resolve the spell or ability. ``own`` is a spell's own handle, the self-clause
    designation trusted by construction (CR 115.4, _plan_cast_designation). On a
    synthesized player slot a card stands for its controller, as when it was chosen
    (legality.activation_target_reason)."""

    def legal(slot, handle: Handle) -> bool:
        if handle == own or handle in slot.candidates:
            return True
        return (
            slot.synthetic
            and handle.namespace == "card"
            and executor.controller_of(handle) in slot.candidates
        )

    if len(slots) <= 1:
        if not slots:
            return tuple(targets), None
        return tuple(h for h in targets if legal(slots[0], h)), None
    assert designations is not None, "a multi-slot recheck reads the designation per slot"
    kept = {
        repr(slot.selector): tuple(h for h in designations[repr(slot.selector)] if legal(slot, h))
        for slot in slots
    }
    return tuple(sorted(h for one in kept.values() for h in one)), kept


def another_target_reason(slots: list, targets: Sequence) -> str | None:
    """The "another target" rule: "target creature ... and another target
    creature" (Rookie Mistake, Garruk, Savage Herald's -2). The compiler
    marks the "another" slot with FAtom(IS_ANY_TARGET) (templates_b5c: the
    documented distinct-target encoding); its targets must differ from every
    other slot's (CR 115.3 lets one object fill several "target" words;
    "another" forbids it here). ``targets``: one group per slot, or one
    handle per slot. None when the designation is legal."""
    groups = [(t,) if isinstance(t, Handle) else tuple(t) for t in targets]
    for i, slot in enumerate(slots):
        marked = any(
            isinstance(n, FAtom) and n.pred is FAtomPred.IS_ANY_TARGET
            for n in walk(slot.selector.filter)
        )
        if not marked:
            continue
        others = {t for j, group in enumerate(groups) if j != i for t in group}
        shared = sorted(set(groups[i]) & others)
        if shared:
            return f"another_target:{shared[0]} is already a target"
    return None


def cast_modes(
    executor: Executor,
    seat: Handle,
    handle: Handle,
    node: SpellAbility,
    *,
    mode_choices: tuple[int, ...] = (),
    decisions: tuple[str, ...] = (),
    pay=None,
) -> tuple[int, tuple[int, ...], tuple[str, ...]]:
    """Announce a modal spell's modes as it is cast (CR 601.2b, 700.2a).

    Returns ``(token, option indices, decisions left)``; ``token`` is the
    runtime Choose's decision token for that set (``query.choose_options``
    order), which the resolution consumes instead of asking again. The modes
    come from ``mode_choices`` (option indices, as the act windows and the
    probe pass them), else from a leading decision token naming a legal set
    (the pack lane), else from an ask of the caster over the legal sets,
    ``choose:<spell>:<digest>`` (forced when only one is legal, never a
    phantom). A set whose modes need a target that cannot be chosen is not
    legal (700.2a); with no legal set the spell cannot be cast. An act
    window calls this before choosing
    targets, then designates through ``spell_target_slots(..., modes=)``;
    ``pay`` prices the targets as that window pays (``spell_target_slots``)."""
    from MTG_bot.core.executor.query import cast_mode_options

    legal = cast_mode_options(executor, node, spell_handle=handle, seat=seat, pay=pay)
    remaining = tuple(decisions)
    if mode_choices:
        wanted = tuple(sorted(int(m) for m in mode_choices))
        for token, idxs in legal:
            if idxs == wanted:
                return token, idxs, remaining
        raise ValueError(
            f"executor: illegal cast: modes {wanted} are not a legal choice (CR 700.2a)"
        )
    if not legal:
        raise ValueError("executor: illegal cast: no mode can be chosen (CR 700.2a)")
    vocab = tuple(str(token) for token, _idxs in legal)
    if remaining and remaining[0] in vocab:
        pick, remaining = remaining[0], remaining[1:]
    else:
        ctx = ctx_for(executor, source=handle, controller=seat)
        digest = site_digest(tuple(idxs for _token, idxs in legal))
        pick = offer_or_autopick(ctx, vocab, f"choose:{handle}:{digest}")
    token = int(pick)
    return token, dict(legal)[token], remaining
def _plan_cast_designation(
    executor: Executor,
    seat: Handle,
    handle: Handle,
    node: SpellAbility,
    *,
    targets: tuple[Handle, ...],
    decisions: tuple[str, ...],
    mode_choices: tuple[int, ...],
) -> tuple[
    tuple[Handle, ...],
    dict[str, tuple[Handle, ...]],
    tuple[str, ...],
    tuple[int, ...],
    SpellAbility,
]:
    """The CR 601.2b/2c DECLARATION lane — modes, then targets:

    * **modes before targets** (601.2b): a modal spell cannot be validated
      option-blind — the chosen modes decide WHICH slots exist at all.
      Every modal spell announces its mode set here (:func:`cast_modes`):
      from ``mode_choices`` (the set's option indices; several for "choose
      one or more"), else from the leading token of ``decisions`` naming a
      legal set (the pack's scripted answer, consumed HERE so the runtime
      Choose never re-asks a decision already made), else from an ask of
      the caster over the legal sets;
    * **forced auto-designation** (601.2c, as the trigger lane does): when
      the spell designated nothing and EVERY slot has one single legal
      filler — a lone-opponent TARGET_PLAYER population (Duress, Mind
      Rot), a one-candidate target, or the self-exile clause (a TARGET
      selector whose only satisfier is the source spell — Experimental
      Overload's IS_SOURCE/BATTLEFIELD shape, empty at designation because
      601.2h parks the spell only LATER; CR 115.4's own-spell clause) — the
      cast takes THE answer, because there is exactly one and the Slate
      cannot state it any other way. Any slot that leaves a real choice
      stays loud (count_below_min), never a guess;
    * **multi-slot designation** (601.2c): several TARGET selectors
      designate slot by slot (:func:`designate_slots`), an "up to" slot
      possibly empty, and return the repr-keyed per-slot map the effect
      runtime threads into ExecCtx.slot_designations.

    Returns ``(designated_targets, slot_designations, remaining_decisions,
    declared_modes, node)``, ``node`` narrowed to the declared modes (its
    slots are the ones the targets were chosen for; resolution checks them
    again, CR 608.2b). Validation of the finished designation happens
    HERE — :func:`cast` must not re-validate mode-blind."""
    from MTG_bot.core.executor.query import (
        filter_has_pred,
        modal_choose,
        spell_target_slots,
        with_modes,
    )

    remaining = tuple(decisions)
    modes: tuple[int, ...] = ()

    # --- modes before targets (601.2b) ------------------------------------
    # Only the chosen modes' targets exist (CR 601.2c, 700.2a), so a mode
    # whose target is missing does not block a cast of the other modes. A
    # declaration may name a mode SET ("choose one or more", CR 700.2d), as
    # ``mode_choices`` with more than one entry; cast_modes matches it
    # against the legal sets, and the chosen modes' slots are designated in
    # walk order as one combined effect. ``modes`` carries the set's token,
    # the runtime Choose's own.
    if modal_choose(node) is not None:
        token, chosen, remaining = cast_modes(
            executor, seat, handle, node, mode_choices=mode_choices, decisions=remaining
        )
        node = with_modes(node, chosen)
        modes = (token,)
    slots = spell_target_slots(executor, node, spell_handle=handle, seat=seat)

    if not slots:
        # targetless or TARGET_PLAYER-only: the player-coordinate oracle
        # validates (it re-derives the same slots).
        _validate_spell_targets(executor, seat, handle, node, targets)
        return targets, {}, remaining, modes, node

    # --- forced auto-designation (601.2c, one legal answer per slot) ------
    # `auto_skip` marks slots filled by the SELF-CLAUSE branch below: their
    # designation cannot pass population validation (the spell is not in the
    # enumerated zone until 601.2h parks it), so it is trusted by
    # construction instead. One-candidate fills come FROM the population
    # and validate normally.
    auto_skip: set[int] = set()
    if not targets:
        auto: list[Handle] = []
        for slot in slots:
            if slot.min_count == slot.max_count == 1 and len(slot.candidates) == 1:
                auto.append(slot.candidates[0])
            elif (
                not slot.candidates
                and slot.min_count >= 1
                and filter_has_pred(slot.selector.filter, FAtomPred.IS_SOURCE)
            ):
                # the self-relocation clause: the source IS the only legal
                # designation; zone enumeration cannot see the spell until
                # 601.2h parks it, so population emptiness is expected.
                auto.append(handle)
                auto_skip.add(len(auto) - 1)
            else:
                auto = []
                auto_skip.clear()
                break
        if len(auto) == len(slots):
            targets = tuple(auto)

    # --- validate + thread -------------------------------------------------
    if len(slots) == 1:
        if 0 not in auto_skip:
            from MTG_bot.core.executor.query import validate_target_selection

            reason = validate_target_selection(slots[0], targets)
            if reason is not None:
                raise ValueError(f"executor: cast: illegal target selection: {reason}")
        return targets, {}, remaining, modes, node

    slot_designations = designate_slots(slots, targets, skip=auto_skip)
    targets = tuple(h for slot in slots for h in slot_designations[repr(slot.selector)])
    return targets, slot_designations, remaining, modes, node


def cast(
    executor: Executor,
    seat: Handle,
    handle: Handle,
    *,
    x: int | None = None,
    kicked: bool = False,
    mode_choices: tuple[int, ...] = (),
    targets: tuple[Handle, ...] | SlotGroups = (),
    decisions: tuple[str, ...] = (),
) -> StackObject:
    """The folded CR 601.2 → 601.4 move (the ``CAST`` decision of the
    Slate's field schedule — legality, declaration, payment, resolution,
    one call; ``legal_casts`` MUST be consulted first: an illegal cast
    raises ``ValueError``).

    Order (each step is the CR's):

    1. **window + shape gate** (:func:`legality.spell_castable`) — the
       card is in hand, its record carries a :class:`SpellAbility`, the
       spell's own window holds (instants anytime; the rest at sorcery
       speed: a main phase of the caster's turn with an empty stack).
    2. **modes** (601.2b) — a modal spell announces its mode set
       (:func:`cast_modes`), recorded on the frame; its top-level Choose
       runs the declared set at resolution instead of asking again.
    3. **targets** (601.2c) — validated through ``validate_target_
       selection`` (or the player-coordinate TARGET_PLAYER rule). A spell
       with several target slots takes one tuple per slot
       (:func:`designate_slots`), or one handle per slot.
    4. **X + total cost** (601.2f) — ``x`` binds ``ExecCtx.x_value`` and
       folds into the plan (a QX cost too big for the pool becomes an
       illegal-cast reason, never a guess).
    5. **payment** (601.2g) — ``pay_costs``, mana segments consumed
       untagged-first with THIS_MANA restrictions honoured for THIS
       spell as the use subject.
    5b. **kick** (601.2b, CR 702.27a) — ``kicked=True`` declares the
       optional extra cost PAID: the kicker Cost joins the 601.2f fold
       inside ``spell_castable`` (a pool too poor for it refuses the cast
       with an ordinary shortage), the choice rides the StackObject
       frame AND the journalled CAST row, and WAS_KICKED reads the row
       back for every later judge (spell arm, ETB trigger condition,
       gated EtBState). Kicking a card without a kicker is an
       illegal-cast REASON, never a guess; an X-kicker prices
       {X} with the cast's X declaration — the same zero-floor law as an
       X-spell (CR 107.1; an explicit ``x`` wins), and the declared X
       lands on the frame and the CAST row.
    6. **push** (601.2h) — park in the stack zone, push the frame, emit
       the journalled ``CAST`` event (the cast-trigger feed, ordinals
       included); the caster keeps priority (CR 117.3c), and cast triggers
       go on the stack ABOVE the spell.
    7. **resolve + put** (608, 601.2j) — :func:`resolve_top`.
    """
    reason, node, _record, plan = spell_castable(
        executor, seat, handle, x=x, kicked=kicked
    )
    if reason is not None or node is None or plan is None:
        raise ValueError(f"executor: illegal cast: {reason}")

    # CR 601.2f chooses X WITH the total cost, so the X the legality fold
    # paid (the documented X=0 floor, CR 107.1, when the caller passed no x)
    # MUST be the X the effect reads: a QX in an effect quantity (Primal
    # Might) needs a bound x_value. An explicit x wins; a spell without X
    # keeps x_value None. The kicker cost joins the total when the kick was
    # declared, so an X-KICKER announces X exactly like an X-spell — the
    # same zero-floor rule lands the value on the frame and the CAST row,
    # or the fold would pay {X}=0 while the journal claims no declaration.
    if x is None:
        from MTG_bot.core.executor.legality import kicker_of

        declared_extra = tuple(node.additional_costs)
        if kicked:
            kicker = kicker_of(_record)
            if kicker is not None:
                declared_extra = declared_extra + (kicker.cost,)
        if _cost_has_x(spell_cost(_record, declared_extra)):
            x = 0

    # 2-3: declaration — modes (601.2b) then targets (601.2c) through
    # _plan_cast_designation, which owns auto-designation, the mode narrowing
    # and per-slot multi-slot validation (and thereby the validation itself).
    targets, slot_designations, decisions, declared_modes, target_node = _plan_cast_designation(
        executor,
        seat,
        handle,
        node,
        targets=targets,
        decisions=decisions,
        mode_choices=mode_choices,
    )
    if targets:
        # CR 601.2f: the total cost is determined AFTER the targets are
        # chosen, so a cost increase for spells that target a permanent (Terror of
        # the Peaks' 3 life, Pursued Whale's {3}) is folded now; the plan above was
        # priced before any target existed. An unpayable total is an illegal cast
        # (601.2h), refused before anything is paid.
        reason, _node, _record, plan = spell_castable(
            executor, seat, handle, x=x, kicked=kicked, targets=tuple(targets)
        )
        if reason is not None or plan is None:
            raise ValueError(f"executor: illegal cast: {reason}")

    # The TARGETING feed (CR 601.2c). Designation IS an event — one row per
    # designated object, Handle-sorted — emitted the moment the targets are
    # declared, BEFORE payment and the park, so a "whenever ... targets"
    # trigger queues over the spell and drains at the next checkpoint.
    executor.journal.emit_targeting(handle, seat, targets)

    # 6: park + frame + event. The payment happens BEFORE the park
    # (pay_costs' own apply_effect boundaries journal the taps/sacrifices
    # exactly as activate() does); the parking gets its own journal
    # boundary so the hand->stack ZONE_CHANGE row exists at all.
    frame = StackObject(
        handle=handle,
        node=node,
        controller=seat,
        spell_kind=node.kind.name,
        x_value=x,
        declared_targets=tuple(sorted(targets)),
        mode_choices=declared_modes or tuple(mode_choices),
        payment=plan,
        declared_clock=executor.journal.clock,
        from_zone="hand",
        kicked=kicked,
        decisions=tuple(decisions),
        slot_designations=dict(slot_designations),
        target_node=target_node,
    )
    before = executor.journal.snapshot()
    start = len(executor.events)
    with executor.atomic():  # CR 601.2g-h: the costs are paid as part of casting
        pay_costs(
            executor,
            plan,
            source=handle,
            controller=seat,
            mana_use=handle,
        )
    park(executor, seat, handle)
    executor.journal.record_atom(before, handle, "CAST", list(executor.events[start:]))
    executor.stack.push(frame)
    executor.journal.emit_cast(handle, seat, node.kind.name, "hand", x, kicked)
    # CR 117.3c: the caster receives priority again; what casting triggered (its
    # costs included) goes on the stack above the spell first (CR 117.5, 601.2i).
    # Outside a game loop both players then pass until the stack is empty
    # (Executor._finish_op; Executor.holding_priority keeps it waiting).
    executor._finish_op()
    return frame


def resolve_top(executor: Executor) -> str:
    """CR 608: the top object of the stack resolves (an activated ability:
    ``legality.resolve_activated``; a triggered one: ``TriggerBinder.resolve``).
    Returns "no_targets" (every target illegal, CR 608.2b), "removed" (a
    trigger's intervening "if" is false, CR 603.4) or "resolved". The caller
    settles afterwards.

    A spell (CR 608.2-608.3, 601.2j): its targets are checked again, its
    effect runs with the targets bound as ``target`` and the declared modes
    consumed by its top-level Choose, and the card moves, an instant or
    sorcery to its owner's graveyard, a permanent spell to the battlefield
    (auto-attaching the registered compiled record so ETB triggers go live
    BEFORE the settle sees the ETB event). The effect runs WITHOUT an
    intervening settle: the spell leaves the stack and the PUT happens
    before anything its mutations armed may fire (CR 608.3: resolution is
    indivisible)."""
    frame = executor.stack.pop()
    with executor.atomic():  # CR 608.2: nothing settles inside a resolution
        if frame.spell_kind == "ACTIVATED":
            from MTG_bot.core.executor.legality import resolve_activated

            return resolve_activated(executor, frame)
        if frame.spell_kind == "TRIGGERED":
            return executor.binder.resolve(frame)
        return _resolve_spell(executor, frame)


def _resolve_spell(executor: Executor, frame: StackObject) -> str:
    """:func:`resolve_top` for a spell."""
    from MTG_bot.core.executor.query import is_aura_spell, spell_target_slots

    world = executor.world
    handle, seat, node, x = frame.handle, frame.controller, frame.node, frame.x_value
    targets: tuple[Handle, ...] = frame.declared_targets
    slot_designations = frame.slot_designations
    if targets:
        # CR 608.2b: the targets are checked again as the spell resolves.
        legal_now, kept = recheck_targets(
            executor,
            spell_target_slots(
                executor, frame.target_node or node, spell_handle=handle, seat=seat
            ),
            targets,
            own=handle,
            designations=slot_designations or None,
        )
        if not legal_now:
            # Every target is illegal: the spell doesn't resolve. It is removed from
            # the stack and put into its owner's graveyard (an Aura too, CR 608.3b).
            before_put = executor.journal.snapshot()
            start_put = len(executor.events)
            world.move_to_zone(handle, seat, ZONE_GRAVEYARD)
            executor.events.append(
                (len(executor.events), "NO_LEGAL_TARGETS", str(handle), "stack->graveyard")
            )
            executor.journal.record_atom(
                before_put, handle, "CAST", list(executor.events[start_put:])
            )
            return "no_targets"
        targets = legal_now
        if kept is not None:
            slot_designations = kept
    bindings: dict[str, Binding] = {}
    chosen = sorted(targets)
    if chosen:
        bindings["target"] = chosen
    ctx = executor._cast_ctx(handle, seat, bindings, frame.decisions, x)
    # A multi-TARGET spell threads its per-slot designation map and the
    # spell-wide union IS_ANY_TARGET means; a single-slot spell sets neither.
    if slot_designations:
        ctx.slot_designations = slot_designations
        ctx.designation_union = tuple(sorted(set(targets)))
    if frame.mode_choices and isinstance(node.effect, Choose):
        # Every modal spell's announced set (any count) is consumed by its
        # top-level Choose at resolution (CR 601.2b: chosen once, as cast).
        # The token is the set's index in choose_options' canonical order, so
        # a "choose one or more" (Sublime Epiphany) keeps its declared set
        # instead of being asked again at resolution.
        ctx.prechosen_modes = [str(m) for m in frame.mode_choices]
    # CR 303.4a/608.2a: an aura enters the battlefield ATTACHED, and
    # its resolution effect runs AFTER the edge exists — the corpus aura
    # effect (Enthralling Hold's GAIN_CONTROL) READS IS_ATTACHED_TO_SOURCE,
    # so attach-then-effect is not cosmetic: effect-first would resolve it
    # against nothing.
    aura = is_aura_spell(world, handle)
    if aura and not chosen:
        raise ValueError(
            "executor: cast: an aura resolution needs its enchant target "
            "(_validate_spell_targets should have refused the cast first)"
        )
    if not aura and node.kind not in _PERMANENT_KINDS:
        # An instant/sorcery's own ReplacementAbility nodes go live
        # AT RESOLUTION START — the spell never attaches, so this is the
        # only lifecycle hook the turn-shaped corpus idiom ("…would die
        # this turn, exile it instead", Scorching Dragonfire) has;
        # registering before the effect runs lets the spell replace events
        # its own effect causes. Eot-expired: the tree carries no duration,
        # and "this turn" is the printed one for every such card.
        record = spell_record(executor, handle)
        if record is not None:
            # The designation snapshot rides the record (Scorching
            # Dragonfire): the dies window outlives this ExecCtx, but its
            # anaphora ("that creature") still MEANS this cast's targets.
            executor.replacements.register_ephemeral_replacements(
                handle, seat, record, designated=tuple(chosen)
            )
    if not aura and node.effect is not None:  # effect-less castable creatures
        executor._run_guarded_effect(node.effect, ctx, "cast")
    before_put = executor.journal.snapshot()
    start_put = len(executor.events)
    dest = ZONE_GRAVEYARD if node.kind not in _PERMANENT_KINDS else ZONE_BATTLEFIELD
    if dest == ZONE_GRAVEYARD and executor.end_turn_requested:
        # Discontinuity, CR 724.1b: ending the turn exiles every object
        # on the stack, the resolving spell included, so the spell whose
        # effect just ended the turn is put into exile, not the graveyard.
        # _v_end_turn (verbs.py) is the only setter of the flag, it fires
        # from THIS spell's effect step just above, and the flag is not
        # consumed until the op closes (_consume_end_turn), so no other
        # spell's graveyard move can be re-routed by this branch.
        dest = ZONE_EXILE
    # Experimental Overload: a spell's own effect may relocate ITSELF
    # off the stack (the self-exile clause resolves before 601.2j's PUT).
    # The graveyard/battlefield move then has no subject — the spell is not
    # in the stack zone any more, its own MOVE row already journalled the
    # relocation, and a second move would drag it from exile into the
    # graveyard. The SPELL_PUT row stays (the cast DID put the spell, its
    # effect just chose where it landed).
    cur_kind = world.zone_of(handle).kind
    if cur_kind != ZONE_STACK:
        dest = cur_kind
    else:
        world.move_to_zone(handle, seat, dest)
    executor.events.append(
        (len(executor.events), "SPELL_PUT", str(handle), f"stack->{dest}")
    )
    if dest == ZONE_BATTLEFIELD:
        # Wildwood Scourge, CR 614.1c: the cast-declared X rides to this
        # permanent's ETB firings — recorded as the spell enters, the
        # binder consumes it for THIS entry only. The IR compiles "enters
        # with X counters" as a TriggeredAbility reading QX, so the trigger
        # needs the cast context the declaration created.
        if x is not None:
            executor.etb_x[handle] = x
        # The re-entry lifecycle: a pool-registered record re-attaches so
        # the card's own ETB triggers are live BEFORE the journal event is
        # matched (binding._lifecycle re-registers via handle_record; the
        # oracle bridge is identity-checked in attach_card).
        registered = executor.binder.records.get(world.cards[handle].identity.oracle_id)
        if registered is not None:
            executor.binder.attach_card(handle, registered)
        if aura:
            executor.attach_aura(handle, chosen[0])
            executor.events.append(
                (len(executor.events), "ATTACH", str(handle), str(chosen[0]))
            )
    entered = executor.journal.record_atom(
        before_put, handle, "CAST", list(executor.events[start_put:])
    )
    # CR 614.1c: the cast entry runs the SAME zone-change hooks as the land
    # drop runs — the compiled EtBState node (Malefic Scythe's "enters with
    # a soul counter", the corpus' entered-tapped idiom) is stamped HERE, as
    # the permanent enters, BEFORE its ETB triggers drain in the settle
    # that follows.
    executor._on_zone_changes(entered)
    if aura and node.effect is not None:
        executor._run_guarded_effect(node.effect, ctx, "cast")
    return "resolved"


def _face_cast_msg(name: str) -> str:
    return (
        f"executor: CAST {name}: no SpellAbility on the card — the "
        "compiled record carries only a BackFace (the front text never "
        "reached the spell grammar)"
    )


class FaceCastAbsentError(ValueError):
    """An effect-designated MDFC whose compiled record has NO SpellAbility
    — every ability of it sits behind a ``BackFace`` node (the ZNR
    spell-front MDFCs compile this way: the front text is unparsed at
    template level, so a cast producer like Coveted Prize can pick a card
    that cannot legally be cast). The refusal is LOUD and TYPED (dedicated
    type + byte-exact message, :func:`face_cast_absent`, so the live-game
    guard ``Executor._run_guarded_effect`` skips ONLY this site); a plain
    land/creature designation keeps its own ValueError. The card is never
    silently cast as its BACK face."""

    def __init__(self, name: str) -> None:
        super().__init__(_face_cast_msg(name))
        self.face_name = name


def face_cast_absent(exc: BaseException) -> bool:
    """True iff ``exc`` IS cast_card's face-cast refusal — dedicated type
    AND byte-exact message rebuilt from the stored name. Look-alikes
    (the plain no-SpellAbility land ValueError, any other text) return
    False and PROPAGATE."""
    return isinstance(exc, FaceCastAbsentError) and str(exc) == _face_cast_msg(
        exc.face_name
    )


def cast_card(
    executor: Executor,
    caster: Handle,
    handle: Handle,
    *,
    cost_override: Cost | None,
    targets: tuple[Handle, ...] = (),
    x: int | None = 0,
) -> None:
    """The effect-side CAST verb's engine (``verbs._v_cast``): cast a
    DESIGNATED card from wherever it sits, with the spell's printed cost
    paid as normal when ``cost_override is None``; an EMPTY Cost is the
    corpus' cost-waiver idiom (CR 118.9 "without paying its mana cost"),
    and a Cost WITH parts is paid on top of the printed cost (additional
    costs, CR 601.2f; legality.effect_cast_cost), plus the spell's own
    additional costs either way (CR 118.9d). No timing check here (an
    effect casts while it resolves, outside the normal timing; a
    permission's timing is judged before the cast,
    ``query.cast_designee_ok``). The spell is on the stack like one cast
    from hand (CR 601.2i, 117.3c, 608.1): it waits there for both players
    to pass and resolves through :func:`resolve_top`.

    ``targets`` (CR 603.3: an effect that lets you cast a spell still
    gets its normal target choices — the effect's caster designates them
    NOW) is validated and bound exactly like :func:`cast` step 3. The
    ATOM side has no target channel (the CAST role table is
    ``source``/``cost`` only), so ``verbs._v_cast`` passes an empty
    tuple: an effect-designated spell WITH targets can only be cast
    through this API directly. The gap is flagged by the spell's own
    unbound-target raise, never a silent no-target resolution: Chandra,
    Flame's Catalyst's [-2] recasting a targeted red spell raises
    (docs/BACKLOG.md, "The CAST atom has no target channel").

    The frame still gets parked, journalled and fingerprinted: an effect
    cast IS a cast — the ``CAST`` event fires, so "whenever you cast"
    triggers see it (CR 601.2i).

    In a game loop (``executor.driven``) the spell stays on the stack and
    the resolution that cast it goes on; the players get priority after it.
    Outside one, both players pass at once and the spell resolves here,
    inside the resolution that cast it (its cast triggers first, then the
    spell, then its ETB triggers), which holds because every compiled CAST
    is the last instruction of its effect (Idol of Endurance, Coveted
    Prize). The cost payment is part of the resolution and does not settle
    (Executor._run_resolution)."""
    from MTG_bot.core.executor.legality import effect_cast_cost

    world = executor.world
    record = spell_record(executor, handle)
    if record is None:
        raise ValueError(
            f"executor: CAST {handle} has no compiled record — the effect "
            "cannot know its spell shape"
        )
    node = next((a for a in record.abilities if isinstance(a, SpellAbility)), None)
    if node is None:
        if any(isinstance(a, BackFace) for a in record.abilities):
            # The designated card is a model DFC whose ONLY compiled
            # abilities live on the far face — the front was never
            # compiled into a SpellAbility. Refuse TYPED (the guard lane
            # skips + ledgers it); never fabricate a face cast.
            raise FaceCastAbsentError(record.name)
        raise ValueError(f"executor: CAST {record.name}: no SpellAbility on the card")
    if world.controller_of(handle) != caster:
        # CR 108.3, 400.3: a spell waits in its caster's stack slot (park), and
        # the world reads a card's owner off its zone, so a card cast by a
        # player who does not own it would come off the stack as the caster's. No
        # card in the dealt pools casts a card it does not own (every CAST source is
        # a YOU zone); refuse loudly rather than change an owner.
        raise NotImplementedError(
            f"executor: CAST {record.name}: casting a card the caster does not own "
            "needs the owner to survive the stack (V24)"
        )
    # A modal spell cast by an effect announces its modes too (CR 608.2g
    # runs 601.2a-i), and only those modes' targets are validated.
    from MTG_bot.core.executor.query import modal_choose, with_modes

    declared_modes: tuple[int, ...] = ()
    target_node = node
    if modal_choose(node) is not None:
        token, chosen_modes, _rest = cast_modes(executor, caster, handle, node)
        target_node = with_modes(node, chosen_modes)
        declared_modes = (token,)
    _validate_spell_targets(executor, caster, handle, target_node, targets)
    # TARGETING feed — same 601.2c contract as cast(): declare, then
    # journal the designation rows before payment.
    executor.journal.emit_targeting(handle, caster, targets)
    # CR 601.2f: the total cost adds the spell's own additional costs to the
    # mana cost or the effect's alternative cost; an unpayable total refuses below.
    cost = effect_cast_cost(record, node, cost_override)
    plan = None
    if cost is not None and cost.parts:
        ctx = ctx_for(executor, source=handle, controller=caster, x_value=x)
        plan, why = build_payment_plan(world, ctx, cost, mana_use=handle)
        if plan is None:
            raise ValueError(f"executor: CAST cannot pay: {why}")
    frame = StackObject(
        handle=handle,
        node=node,
        controller=caster,
        spell_kind=node.kind.name,
        x_value=x,
        declared_targets=tuple(sorted(targets)),
        mode_choices=declared_modes,
        payment=plan,
        declared_clock=executor.journal.clock,
        from_zone=world.zone_of(handle).kind,
        target_node=target_node,
    )
    floor = len(executor.stack.frames)
    before = executor.journal.snapshot()
    start = len(executor.events)
    if plan is not None:
        pay_costs(
            executor,
            plan,
            source=handle,
            controller=caster,
            mana_use=handle,
        )
    park(executor, caster, handle)
    executor.journal.record_atom(before, handle, "CAST", list(executor.events[start:]))
    executor.stack.push(frame)
    executor.journal.emit_cast(handle, caster, node.kind.name, frame.from_zone, x)
    if not executor.driven:
        executor._settle(floor)


def play_land(
    executor: Executor,
    seat: Handle,
    handle: Handle,
    *,
    tapped: bool = False,
) -> None:
    """The ``PLAY_LAND`` move (CR 305.1, folded one-call like activate/
    cast): re-check :func:`land_playable`, move hand → battlefield (a
    special action — no stack, no cost, not an event anyone can respond
    to), journal the ETB, stamp the once-per-turn ledger, and settle so
    land ETB triggers fire.
    ``tapped`` is the rig's explicit override; a land whose compiled
    record declares an EtBState (the M21 checklands and temples "enter
    the battlefield tapped") gets that state from the journal's entry
    hook instead — the flag is not how the corpus' entered state ships."""
    world = executor.world
    reason = land_playable(executor, seat, handle)
    if reason is not None:
        raise ValueError(f"executor: illegal land play: {reason}")
    before = executor.journal.snapshot()
    start = len(executor.events)
    world.move_to_zone(handle, seat, ZONE_BATTLEFIELD)
    if tapped:
        world.cards[handle].tapped = True
    executor.events.append(
        (len(executor.events), "PLAY_LAND", str(handle), "hand->battlefield")
    )
    registered = executor.binder.records.get(world.cards[handle].identity.oracle_id)
    if registered is not None:
        executor.binder.attach_card(handle, registered)
    entered = executor.journal.record_atom(
        before, handle, "PLAY_LAND", list(executor.events[start:])
    )
    # The land's entry runs the SAME zone-change hooks as every other
    # battlefield entry — the compiled EtBState node (checklands, temples:
    # "enters the battlefield tapped") is stamped here.
    executor._on_zone_changes(entered)
    turn, plays = executor.land_ledger.get(seat, (world.turn, 0))
    if turn != world.turn:
        plays = 0
    executor.land_ledger[seat] = (world.turn, plays + 1)
    executor._finish_op()
