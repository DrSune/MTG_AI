"""The spell stack and the casting pipeline.

A cast is one engine call, as an activation is, in CR 601.2 order: re-check
legality, choose modes/targets/X (601.2c–e), determine and LOCK the total cost
(601.2f), pay (601.2g), put the spell on the stack (601.2h), resolve it
(601.4), move the card to its after-resolution zone (601.2j / 400.7).

**Response window vs CR 608.2.** A real spell waits on the stack while
players get a RESPONSE WINDOW (CR 608.2: mana abilities first, then
spells/abilities in APNAP order). Here, after the cast's triggers settle and
BEFORE resolution, every opponent in seat order is asked (decision tag
``counter:<seat>:<digest>``) whether they respond — ``PASS`` or the handle of
a payable counterspell from hand, which is cast at the frame in a nested LIFO
push (a counter can itself be countered). The window is ONE response round,
in seat order, with no priority re-asks; the engine taps free mana sources to
pay (:func:`_window_taps`), and other mana abilities, non-counter replies and
real priority stay a documented gap. A frame a counter flags is popped
without its effect running (601.4 interrupted; the card still goes to its
graveyard, 400.7). A seat with nothing castable is never asked (an empty
choice set is never offered). Every declaration field the CR makes public
(601.2b–e: modes, targets, X, total cost, timing choices) is stored on
:class:`SpellObject` and journalled, so the window reads a complete frame
instead of re-deriving one. :func:`open_combat_window` is the same kind of
round for instants after blockers are declared.

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
(CR 405). A counterspell cast in the response window is pushed above the
frame it answers and resolves first.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field, fields, is_dataclass
from itertools import combinations, count
from typing import TYPE_CHECKING

from MTG_bot.core.ability_tree import (
    Atom,
    BackFace,
    Choose,
    Cost,
    FAtom,
    FAtomPred,
    Selector,
    Seq,
    SpellAbility,
    SpellKind,
    Verb,
    walk,
)
from MTG_bot.core.executor.decisions import site_digest
from MTG_bot.core.executor.events import (
    KIND_WINDOW_OPEN,
    KIND_WINDOW_PASS,
    parse_handle_tag,
)
from MTG_bot.core.executor.legality import (
    MAIN_PHASES,
    PaymentPlan,
    _cost_has_x,
    build_payment_plan,
    ctx_for,
    pay_costs,
    plan_mana_taps,
    protected_from,
    spell_castable,
    spell_cost,
    spell_record,
    tap_for_payment,
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
class SpellObject:
    """One stack frame: the 601.2b–e declaration record. Every field is what
    the CR makes PUBLIC on the stack — the response window reads this frame
    instead of re-deriving it.

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
      stack for the response window and the diagnostics dump.
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
    # The counter flag. Set by the COUNTER_SPELL handler when a
    # response-window cast interrupts THIS frame; the popper sees it and
    # returns without running the effect (CR 601.4's interrupted
    # resolution). Transient: the frame is popped as soon as the
    # counterspell's cast returns, so dump() leaves the flag out.
    countered: bool = False


@dataclass
class SpellStack:
    """Executor-side stack container: the LIFO frame list + the deterministic
    dump the fingerprint folds."""

    frames: list[SpellObject] = field(default_factory=list)

    def push(self, frame: SpellObject) -> None:
        self.frames.append(frame)

    def pop(self) -> SpellObject:
        if not self.frames:
            raise ValueError("executor: stack resolution with an empty stack")
        return self.frames.pop()

    def top(self) -> SpellObject | None:
        return self.frames[-1] if self.frames else None

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
    allowance = (
        1
        + executor.extra_land_plays
        + (executor.layers.land_play_bonus(seat) if executor.layers else 0)
    )
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
            getattr(slot, "synthetic", False)
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
def _option_sets(executor: Executor, node: SpellAbility, handle: Handle, seat: Handle):
    """The legal option sets of a Choose spell, in ``query.choose_options``'
    canonical order (the runtime Choose's own token contract: token = the
    set's index here)."""
    from MTG_bot.core.executor.query import choose_options

    assert isinstance(node.effect, Choose)
    return choose_options(executor, node.effect, source=handle, controller=seat)


def _chosen_effect(choose, chosen: tuple[int, ...]):
    """The effect a declared mode set amounts to: the one option, or the
    options in printed order (CR 700.2d; how the runtime Choose runs them)."""
    if len(chosen) == 1:
        return choose.options[chosen[0]]
    return Seq(steps=tuple(choose.options[i] for i in chosen))


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
    from MTG_bot.core.ability_tree import FAtomPred
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


def _tree_has_counter(node: object) -> bool:
    """Does an IR subtree (SpellAbility effect trees, Seq/Choose/
    Conditional shapes) contain a COUNTER_SPELL atom? Generic dataclass
    walk, so it does not re-encode the effect grammar; the IR is a finite
    tree (no cycles), so the recursion terminates."""
    if isinstance(node, Atom):
        return node.verb is Verb.COUNTER_SPELL
    if is_dataclass(node) and not isinstance(node, Handle):
        for f in fields(node):
            value = getattr(node, f.name)
            if isinstance(value, (list, tuple)):
                if any(_tree_has_counter(item) for item in value):
                    return True
            elif _tree_has_counter(value):
                return True
    return False


def _tree_verb_closure(node: object, acc: set) -> set:
    """Every Atom verb inside an IR subtree (the same generic dataclass
    walk as :func:`_tree_has_counter`). The windows' engine-support gate
    asks for the FULL closure, not just the counter atom: a card that
    counters a spell but also executes COPY (Sublime Epiphany) is not
    executable by the engine, so a vocab that promises executability must
    not offer it."""
    if isinstance(node, Atom):
        acc.add(node.verb)
    elif is_dataclass(node) and not isinstance(node, Handle):
        for f in fields(node):
            value = getattr(node, f.name)
            if isinstance(value, (list, tuple)):
                for item in value:
                    _tree_verb_closure(item, acc)
            else:
                _tree_verb_closure(value, acc)
    return acc


def _counter_vocab(
    executor: Executor, seat: Handle, frame_handle: Handle
) -> tuple[str, ...]:
    """The response vocabulary for one seat facing ONE stack frame: PASS
    plus the handle string of every hand card that is a counterspell it
    could legally cast AGAINST THAT FRAME right now. Four gates:

    * a COUNTER_SPELL atom, and castable now (:func:`_window_taps`:
      window, mana with the free sources the window may tap, record);
      nothing the seat cannot pay is offered;
    * **verb closure** — every atom of the spell node lies in HANDLERS
      (the runtime twin of the compile-time ``engine_supported`` gate; a
      counterspell with a COPY mode is not offered);
    * **designability** — the frame passes the counter's own TARGET-slot
      legality via :func:`validate_target_selection` (Miscast's
      instant/sorcery filter is never offered at a creature spell);
      ``spell_castable`` cannot see this because it is target-blind;
    * **declaration** — a modeless counter has exactly one TARGET slot
      and the frame passes it: the window casts it with
      ``targets=(frame,)``. A Choose-based counter ("choose one or more")
      is offered when some legal mode set counters the frame
      (:func:`_modal_counter_sets`); answering it opens the visible mode
      ask, then the target asks (:func:`_declare_modal_counter`), so no
      mode is ever a silent pick.

    Handle-sorted."""
    from MTG_bot.core.executor.query import (
        spell_target_slots,
        validate_target_selection,
    )
    from MTG_bot.core.executor.verbs import HANDLERS

    world = executor.world
    hand = world.players[seat].zone("hand")
    options: list[str] = []
    for handle in hand.entries:
        record = spell_record(executor, handle)
        if record is None:
            continue
        node = next((a for a in record.abilities if isinstance(a, SpellAbility)), None)
        if node is None or node.effect is None or not _tree_has_counter(node.effect):
            continue
        if not _tree_verb_closure(node, set()) <= set(HANDLERS):
            continue
        if _window_taps(executor, seat, handle) is None:
            continue
        if isinstance(node.effect, Choose):
            if _modal_counter_sets(executor, seat, handle, node, frame_handle):
                options.append(str(handle))
            continue
        slots = spell_target_slots(
            executor, node, spell_handle=handle, seat=seat, pay=_window_pay(executor, seat, handle)
        )
        if len(slots) != 1 or validate_target_selection(slots[0], (frame_handle,)):
            continue
        options.append(str(handle))
    return ("PASS",) + tuple(sorted(options))


def _window_taps(
    executor: Executor, seat: Handle, handle: Handle, targets: tuple[Handle, ...] = (),
    x: int | None = None,
):
    """The free sources ``seat`` taps to cast ``handle`` at ``targets`` (with
    ``x`` for an X spell) in a response window (CR 601.2g, 605.3a: mana
    abilities may be activated while paying; 601.2f: the total includes X
    and a target's cost increase), () when the pool already pays, None when
    the spell cannot be cast (then it is never offered)."""
    return plan_mana_taps(
        executor, seat, lambda: spell_castable(executor, seat, handle, x=x, targets=targets)[0]
    )


def _window_pay(executor: Executor, seat: Handle, handle: Handle, x: int | None = None):
    """How a window prices a target (``spell_target_slots``' ``pay``): the
    pool plus the free sources the window would tap, as it pays."""
    return lambda targets: _window_taps(executor, seat, handle, targets, x) is not None


def _window_cast(
    executor: Executor, seat: Handle, handle: Handle, target: Handle, x: int | None = None
) -> None:
    """Cast a response-window answer: tap the planned mana abilities, then the
    ordinary :func:`cast` (which re-checks legality and pays from the pool)."""
    tap_for_payment(executor, seat, _window_taps(executor, seat, handle, (target,), x) or ())
    cast(executor, seat, handle, x=x, targets=(target,))


def _counter_selectors(effect: object) -> set[str]:
    """The ``repr`` of every COUNTER_SPELL atom's target selector in an IR
    subtree (the slot identity the cast lane designates by)."""
    out: set[str] = set()
    if isinstance(effect, Atom):
        if effect.verb is Verb.COUNTER_SPELL:
            target = effect.args.get("target")
            if isinstance(target, Selector):
                out.add(repr(target))
        return out
    if is_dataclass(effect) and not isinstance(effect, Handle):
        for f in fields(effect):
            value = getattr(effect, f.name)
            for item in value if isinstance(value, (list, tuple)) else (value,):
                out |= _counter_selectors(item)
    return out


def _modal_counter_sets(
    executor: Executor,
    seat: Handle,
    handle: Handle,
    node: SpellAbility,
    frame_handle: Handle,
) -> list[tuple[int, tuple[int, ...], list]]:
    """CR 601.2b, 700.2a: the mode sets a Choose-based counterspell
    may declare in the counter window against ``frame_handle``, as
    ``(option-set index, modes, target slots)`` in ``query.choose_options``'
    canonical order (the runtime Choose's own token contract). A set is
    offered when every one of its slots has a legal target (700.2a: a mode
    that cannot choose legal targets can't be chosen; "counter target
    activated or triggered ability" is never offered, as abilities never sit
    on this engine's stack) and one of its COUNTER_SPELL slots accepts the
    frame (the window answers this frame). Two limits narrow the menu, never
    guessing past them: this window's declaration asks exactly one target
    per slot (:func:`_declare_modal_counter`), and slots are keyed by their
    selector (the repr-keyed slot map), so a set with another slot shape or
    two equal selectors is left out."""
    from dataclasses import replace

    from MTG_bot.core.executor.query import (
        spell_target_slots,
        validate_target_selection,
    )

    assert isinstance(node.effect, Choose)
    out: list[tuple[int, tuple[int, ...], list]] = []
    for i, option_set in enumerate(_option_sets(executor, node, handle, seat)):
        modes = option_set.option_idxs
        if not modes:
            continue  # the empty set counters nothing
        effect = _chosen_effect(node.effect, modes)
        slots = spell_target_slots(
            executor,
            replace(node, effect=effect),
            spell_handle=handle,
            seat=seat,
            pay=_window_pay(executor, seat, handle),
        )
        if any(len(slot.candidates) < slot.min_count for slot in slots):
            continue
        if len(slots) > 1 and (
            any(slot.min_count != 1 or slot.max_count != 1 for slot in slots)
            or len({repr(slot.selector) for slot in slots}) != len(slots)
        ):
            continue
        counters = _counter_selectors(effect)
        if not any(
            repr(slot.selector) in counters
            and validate_target_selection(slot, (frame_handle,)) is None
            for slot in slots
        ):
            continue
        out.append((i, modes, slots))
    return out


def _window_pick(executor: Executor, vocab: tuple[str, ...], what: str, seat: Handle) -> str:
    """One counter-window declaration ask. A one-option surface is forced:
    journalled, never asked (the shared phantom rule of
    :func:`~MTG_bot.core.executor.offers.offer_or_autopick`)."""
    if len(vocab) == 1:
        executor.decisions.journal.append((what, vocab[0]))
        return vocab[0]
    return executor.decisions.take(vocab, what, seat=seat)


def _declare_modal_counter(
    executor: Executor,
    seat: Handle,
    handle: Handle,
    node: SpellAbility,
    frame_handle: Handle,
) -> tuple[tuple[int, ...], tuple[Handle, ...]]:
    """The declaration of a Choose-based counterspell answering the
    counter window, in CR 601.2b-c order. First the mode set (a ``choose``
    ask whose tokens are the runtime Choose's option-set indices, offering
    only the legal sets of :func:`_modal_counter_sets`), then the targets of
    the chosen modes slot by slot in walk order (a ``target`` ask over each
    slot's live candidates). The window's own frame is the target of the
    first counter slot that accepts it: answering the window with this card
    means countering that frame. Returns ``(modes, targets)`` for
    :func:`cast`'s ``mode_choices``/``targets``."""
    sets = _modal_counter_sets(executor, seat, handle, node, frame_handle)
    if not sets:
        raise ValueError(f"executor: counter window: {handle} has no legal mode set")
    vocab = tuple(str(i) for i, _modes, _slots in sets)
    digest = site_digest(("counter-modes", str(frame_handle), tuple(m for _i, m, _s in sets)))
    pick = _window_pick(executor, vocab, f"choose:{handle}:{digest}", seat)
    _i, modes, slots = next(row for row in sets if str(row[0]) == pick)
    counters = _counter_selectors(_chosen_effect(node.effect, modes))
    from MTG_bot.core.executor.query import validate_target_selection

    targets: list[Handle] = []
    frame_taken = False
    for slot in slots:
        if (
            not frame_taken
            and repr(slot.selector) in counters
            and validate_target_selection(slot, (frame_handle,)) is None
        ):
            targets.append(frame_handle)
            frame_taken = True
            continue
        candidates = tuple(sorted(slot.candidates))
        words = tuple(str(c) for c in candidates)
        answer = _window_pick(
            executor, words, f"target:{seat}:{handle}:{site_digest(words)}", seat
        )
        targets.append(next(c for c in candidates if str(c) == answer))
    return modes, tuple(targets)


#: The effect atoms that make an instant worth asking about in the
#: post-declare-blockers window (:func:`open_combat_window`) — the
#: combat-relevant payloads the corpus actually prints (burn a blocker /
#: attacker, pump your own creature's P/T). Deliberately NARROW, the same
#: way the counter vocab is narrow: an instant whose every atom is
#: combat-irrelevant (a discard, a draw) is never offered here — the
#: window exists to model the fight, not to re-open every decision.
_COMBAT_INSTANT_ATOMS = frozenset({Verb.DEAL_DAMAGE, Verb.MODIFY_PT, Verb.SET_PT})


def _tree_has_any_atom(node: object, verbs: frozenset) -> bool:
    """Does an IR subtree contain ANY atom of ``verbs``? (The generic
    dataclass walk of :func:`_tree_has_counter`, generalised.)"""
    if isinstance(node, Atom):
        return node.verb in verbs
    if is_dataclass(node) and not isinstance(node, Handle):
        for f in fields(node):
            value = getattr(node, f.name)
            if isinstance(value, (list, tuple)):
                if any(_tree_has_any_atom(item, verbs) for item in value):
                    return True
            elif _tree_has_any_atom(value, verbs):
                return True
    return False


def _combat_instant_vocab(executor: Executor, seat: Handle) -> tuple[str, ...]:
    """The response vocabulary for one seat in the combat instant window:
    PASS plus one ``<card>@<target>`` token per legal (instant,
    single-target designation) pair it could cast RIGHT NOW; an X spell
    gets one token per payable X, ``:x<N>`` appended when X > 0. The four
    gates of :func:`_counter_vocab` are re-applied with the combat shape
    swapped in for the counter shape:

    * INSTANT kind + a combat-relevant atom (:data:`_COMBAT_INSTANT_ATOMS`)
      and castable now (:func:`_window_taps`: mana, record);
    * **verb closure** ⊆ HANDLERS (the runtime twin of engine_supported);
    * **designability** — exactly one TARGET slot with 1 inside its
      cardinality range, and EVERY token is candidate-checked through
      :func:`validate_target_selection` (the target rides INSIDE the
      token: unlike the counter lane there is no forced frame to
      auto-designate — burn has a whole population);
    * **modeless declaration** — a ``Choose`` fan can never open here
      (the lane casts with one target and no mode)."""
    from MTG_bot.core.ability_tree import Choose
    from MTG_bot.core.executor.query import (
        spell_target_slots,
        validate_target_selection,
    )
    from MTG_bot.core.executor.verbs import HANDLERS

    world = executor.world
    hand = world.players[seat].zone("hand")
    options: list[str] = []
    for handle in hand.entries:
        record = spell_record(executor, handle)
        if record is None:
            continue
        node = next((a for a in record.abilities if isinstance(a, SpellAbility)), None)
        if (
            node is None
            or node.effect is None
            or node.kind is not SpellKind.INSTANT
            or not _tree_has_any_atom(node.effect, _COMBAT_INSTANT_ATOMS)
        ):
            continue
        if isinstance(node.effect, Choose):
            continue
        if not _tree_verb_closure(node, set()) <= set(HANDLERS):
            continue
        # one token per payable X, as the act menu offers
        record_cost = spell_cost(record, tuple(node.additional_costs))
        for x in count() if _cost_has_x(record_cost) else (None,):
            if _window_taps(executor, seat, handle, (), x) is None:
                break  # a larger X costs more: none is payable either
            slots = spell_target_slots(
                executor, node, spell_handle=handle, seat=seat, pay=_window_pay(executor, seat, handle, x)
            )
            if len(slots) != 1 or not slots[0].min_count <= 1 <= slots[0].max_count:
                break
            for target in slots[0].candidates:
                if validate_target_selection(slots[0], (target,)) is None:
                    options.append(f"{handle}@{target}" + (f":x{x}" if x else ""))
    return ("PASS",) + tuple(sorted(options))


def open_combat_window(executor: Executor) -> None:
    """The post-declare-blockers combat INSTANT window (CR 506.4/510's
    first slice). After blockers are declared and their triggers have
    settled, BEFORE the damage step, both players may cast instants (kill
    a blocker, pump a defender). One round in ``player_order`` (the active
    player gets the first priority of the step, CR 506.4), no priority
    re-asks: the same documented narrowing as the counter window, and
    every answer is a full-payload ``card@target`` token the lane casts via
    the SAME :func:`cast` pipeline (which nests its own counter window, so
    the windows compose, and settles triggers + SBAs internally, so a dead
    blocker is gone and a pumped creature's ledger is live before
    ``_combat_damage`` reads it).

    A seat with NOTHING castable is never asked and gets NO row.
    Journal rows reuse WINDOW_OPEN/WINDOW_PASS with cause_verb
    ``COMBAT_WINDOW`` and subject=None (no stack frame to point at); the
    decision tag is ``cw:<seat>:<digest>``, a lane of its own, apart from
    the counter window's ``counter:`` and the ``pay:`` asks."""
    digest = site_digest(("combat-window", str(executor.journal.clock)))
    for seat in executor.world.player_order:
        vocab = _combat_instant_vocab(executor, seat)
        if len(vocab) <= 1:
            continue
        executor.journal.emit(KIND_WINDOW_OPEN, None, seat, "COMBAT_WINDOW", (vocab,))
        answer = executor.decisions.take(vocab, f"cw:{seat}:{digest}", seat=seat)
        if answer == "PASS":
            executor.journal.emit(KIND_WINDOW_PASS, None, seat, "COMBAT_WINDOW", ())
            continue
        card_tag, _, target_tag = answer.partition("@")
        target_tag, _, x_tag = target_tag.partition(":x")
        _window_cast(executor, seat, parse_handle_tag(card_tag), parse_handle_tag(target_tag),
                     int(x_tag) if x_tag else None)


def _response_window(executor: Executor, frame: SpellObject) -> None:
    """The RESPONSE WINDOW of a spell just cast (CR 608.2's first slice),
    after its cast triggers have settled and before it resolves. Every
    opponent of its caster, in seat order, MAY answer the frame with a
    counterspell. One round, seat-ordered, no priority re-asks (the
    documented narrowing in the module docstring); a dead frame ends the
    round early; a seat with nothing to offer is skipped WITHOUT an ask
    and without a journal row. The nested ``cast`` is the LIFO push:
    the counter resolves ON TOP of this frame, and its own window opens
    recursively (a counter can be countered). Answers come from
    ``executor.decisions.take`` DIRECTLY, bypassing the pool, because the
    per-op ``decisions=`` pool belongs to the spell's declaration
    (modes/targets), and letting a window answer consume it would silently
    re-target the cast (pinned by
    ``test_window_bypasses_the_declaration_pool``).

    Both cast lanes open it: :func:`cast` and the CAST atom's
    :func:`cast_card`. A spell cast through a permission or by an effect is
    a spell on the stack like one cast from hand (CR 601.2i, 117.3c,
    608.1), so it gets the same chances to be answered."""
    world = executor.world
    handle, seat = frame.handle, frame.controller
    digest = site_digest((str(handle), frame.declared_clock))
    for responder in world.player_order:
        if responder == seat:
            continue
        if frame.countered or world.zone_of(handle).kind != ZONE_STACK:
            break
        vocab = _counter_vocab(executor, responder, handle)
        if len(vocab) <= 1:
            continue
        executor.journal.emit(KIND_WINDOW_OPEN, handle, responder, "WINDOW", (vocab,))
        answer = executor.decisions.take(vocab, f"counter:{responder}:{digest}", seat=responder)
        if answer == "PASS":
            executor.journal.emit(KIND_WINDOW_PASS, handle, responder, "WINDOW", ())
            continue
        counter = parse_handle_tag(answer)
        counter_record = spell_record(executor, counter)
        counter_node = next(
            (a for a in counter_record.abilities if isinstance(a, SpellAbility)), None
        ) if counter_record is not None else None
        if counter_node is not None and isinstance(counter_node.effect, Choose):
            # CR 601.2b-c: a modal counter declares its mode set, then its
            # targets, through visible asks; the window never picks a mode.
            modes, chosen = _declare_modal_counter(
                executor, responder, counter, counter_node, handle
            )
            # CR 601.2g: the mana abilities are activated after the
            # declaration (601.2b-c), while the cost is paid.
            tap_for_payment(
                executor, responder, _window_taps(executor, responder, counter, chosen) or ()
            )
            cast(executor, responder, counter, mode_choices=modes, targets=chosen)
            continue
        _window_cast(executor, responder, counter, handle)


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
) -> SpellObject:
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
       with an ordinary shortage), the choice rides the SpellObject
       frame AND the journalled CAST row, and WAS_KICKED reads the row
       back for every later judge (spell arm, ETB trigger condition,
       gated EtBState). Kicking a card without a kicker is an
       illegal-cast REASON, never a guess; an X-kicker prices
       {X} with the cast's X declaration — the same zero-floor law as an
       X-spell (CR 107.1; an explicit ``x`` wins), and the declared X
       lands on the frame and the CAST row.
    6. **push** (601.2h) — park in the stack zone, push the frame, emit
       the journalled ``CAST`` event (the cast-trigger feed, ordinals
       included) and settle — cast triggers resolve ABOVE the spell; then
       the response window (:func:`_response_window`).
    7. **resolve + put** (601.4, 601.2j) — pop the LIFO frame (a countered
       frame stops here), check the targets again (CR 608.2b: with none
       legal the spell does not resolve), run the effect (targets bound as
       ``target``), move the card: instants and sorceries to the owner's
       graveyard, permanent spells to the battlefield (auto-attaching the
       registered compiled record so ETB triggers go live BEFORE the
       settle sees the ETB event).
    """
    world = executor.world
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
        from MTG_bot.core.executor.legality import (
            _cost_has_x,
            kicker_of,
            spell_cost,
        )

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
    frame = SpellObject(
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
    )
    before = executor.journal.snapshot()
    start = len(executor.events)
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
    assert executor.stack.top() is frame  # LIFO: this cast is the top frame
    executor.journal.emit_cast(handle, seat, node.kind.name, "hand", x, kicked)
    executor._settle()  # cast triggers resolve first
    _response_window(executor, frame)  # 6b

    # 7: resolution. The effect runs WITHOUT an intervening settle — the
    # spell leaves the stack and the PUT happens before anything its
    # mutations armed may fire (CR 608.3: resolution is indivisible; the
    # settle in _finish_op below is the spell's own trigger aftermath).
    popped = executor.stack.pop()
    assert popped is frame  # LIFO: every response cast above it has resolved
    if frame.countered:
        # CR 601.4 interrupted: the COUNTER_SPELL handler already
        # flagged the frame, journalled the COUNTER row and moved the card
        # to its graveyard (400.7). The effect never runs and the spell
        # gets no SPELL_PUT — a countered spell was never put anywhere.
        return frame
    if targets:
        # CR 608.2b: the targets are checked again as the spell resolves; the cast
        # triggers above it have resolved by now.
        from MTG_bot.core.executor.query import spell_target_slots

        legal_now, kept = recheck_targets(
            executor,
            spell_target_slots(executor, target_node, spell_handle=handle, seat=seat),
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
            executor._finish_op()
            return frame
        targets = legal_now
        if kept is not None:
            slot_designations = kept
    bindings: dict[str, Binding] = {}
    chosen = sorted(targets)
    if chosen:
        bindings["target"] = chosen
    ctx = executor._cast_ctx(handle, seat, bindings, decisions, x)
    # A multi-TARGET spell threads its per-slot designation map and the
    # spell-wide union IS_ANY_TARGET means; a single-slot spell sets neither.
    if slot_designations:
        ctx.slot_designations = slot_designations
        ctx.designation_union = tuple(sorted(set(targets)))
    if declared_modes and isinstance(node.effect, Choose):
        # Every modal spell's announced set (any count) is consumed by its
        # top-level Choose at resolution (CR 601.2b: chosen once, as cast).
        # The token is the set's index in choose_options' canonical order, so
        # a "choose one or more" (Sublime Epiphany) keeps its declared set
        # instead of being asked again at resolution.
        ctx.prechosen_modes = [str(m) for m in declared_modes]
    from MTG_bot.core.executor.query import is_aura_spell

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
        registered = executor.binder.records.get(world.cards[handle].identity.oracle_id)
        if registered is not None:
            # The designation snapshot rides the record (Scorching
            # Dragonfire): the dies window outlives this ExecCtx, but its
            # anaphora ("that creature") still MEANS this cast's targets.
            executor.replacements.register_ephemeral_replacements(
                handle, seat, registered, designated=tuple(chosen)
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
    # CR 614.1c: the cast entry runs the SAME zone-change hooks the land
    # drop runs — the compiled EtBState node (Malefic Scythe's "enters with
    # a soul counter", the corpus' entered-tapped idiom) is stamped HERE, as
    # the permanent enters, BEFORE its ETB triggers drain in the settle
    # below.
    executor._on_zone_changes(entered)
    if aura and node.effect is not None:
        executor._run_guarded_effect(node.effect, ctx, "cast")
    executor._finish_op()  # an effect that ended the turn goes first (CR 724.1)
    return frame


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
) -> bool:
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
    from hand (CR 601.2i, 117.3c, 608.1), so after its cast triggers it
    gets the same counter window (:func:`_response_window`). Returns
    ``True`` when the spell was cast and resolved, ``False`` when it was
    countered.

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

    CR 704.3: the spell is resolved here, inside the resolution that cast
    it, and the two settles below stand for the priority points that
    follow that resolution (its cast triggers above the spell, then the
    response window and the spell, then its ETB triggers). That holds
    because every compiled CAST is the last instruction of its effect
    (Idol of Endurance, Coveted Prize). The cost payment above is part of
    the resolution and does not settle (Executor._run_resolution)."""
    from MTG_bot.core.executor.legality import ctx_for, effect_cast_cost

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
    frame = SpellObject(
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
    )
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
    executor._settle()
    _response_window(executor, frame)
    popped = executor.stack.pop()
    assert popped is frame
    if frame.countered:
        return False  # CR 701.6a: removed from the stack, none of its effects occur
    bindings: dict[str, Binding] = {}
    chosen = sorted(targets)
    if chosen:
        bindings["target"] = chosen
    ctx = executor._cast_ctx(handle, caster, bindings, (), x)
    if declared_modes:
        ctx.prechosen_modes = [str(m) for m in declared_modes]
    from MTG_bot.core.executor.query import is_aura_spell

    aura = is_aura_spell(world, handle)
    if aura and not chosen:
        raise ValueError("executor: CAST: an aura cast needs its enchant target")
    if not aura and node.kind not in _PERMANENT_KINDS:
        # The spell's own replacements go live at resolution start, as in
        # cast().
        executor.replacements.register_ephemeral_replacements(handle, caster, record)
    if not aura and node.effect is not None:
        executor._run_guarded_effect(node.effect, ctx, "cast_card")
    before_put = executor.journal.snapshot()
    start_put = len(executor.events)
    dest = ZONE_GRAVEYARD if node.kind not in _PERMANENT_KINDS else ZONE_BATTLEFIELD
    world.move_to_zone(handle, caster, dest)
    executor.events.append(
        (len(executor.events), "SPELL_PUT", str(handle), f"stack->{dest}")
    )
    if dest == ZONE_BATTLEFIELD:
        if x is not None:  # same CR 614.1c X ride as cast()
            executor.etb_x[handle] = x
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
    # Same CR 614.1c entered-state stamp as cast() —
    # effect-cast permanents declare their EtBState too.
    executor._on_zone_changes(entered)
    if aura and node.effect is not None:
        executor._run_guarded_effect(node.effect, ctx, "cast_card")
    executor._settle()
    return True


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
    executor._settle()
