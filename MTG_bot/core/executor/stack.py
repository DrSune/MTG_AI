"""The spell stack + the casting pipeline (round 13b, /11 §13b).

CR 601.2 ordered declaration, then resolution — folded into ONE engine call
per cast, exactly the way 12c folded ``ACTIVATE``: re-check legality, choose
modes/targets/X (601.2c–e), determine and LOCK the total cost (601.2f), pay
(601.2g), put the spell on the stack (601.2h), resolve it (601.4), move the
card to its after-resolution zone (601.2j / 400.7).
**Rung-1 response window vs CR 608.2 — the narrowed gap.** A real spell
waits on the stack while players get a RESPONSE WINDOW (CR 608.2: mana
abilities first, then spells/abilities in APNAP order). Round-13b had
none: casts resolved IMMEDIATELY and ``COUNTER_SPELL`` was a loud
NotImplementedError. RUNG-1 opens the first slice of that window: after
the cast's triggers settle and BEFORE resolution, every opponent in
seat order is asked (through the 14b decision channel, tag
``counter:<seat>:<digest>``) whether they respond — ``PASS`` or the
handle of a payable counterspell from hand, which is cast at the frame
in a nested LIFO push (a counter can itself be countered). The window
is ONE response round, in seat order, with no priority re-asks and no
mana-ability lane: a real window interleaves passes and active-player
rounds; this is rung 1 of the arc, and everything beyond it (instants-
in-reply, priority, mana abilities) STAYS a documented gap. A frame a
counter flags is popped without its effect running (601.4 interrupted;
the card still goes to its graveyard, 400.7). A seat with nothing
castable is never asked (C15 — an empty choice set is never offered).
Every declaration field the CR makes public (601.2b–e: modes, targets,
X, total cost, timing choices) is stored on :class:`SpellObject` and
journalled (risk-1, doc /11) — the window reads a complete frame
instead of re-deriving one.

Stack placement: the frozen :mod:`MTG_bot.core.state` already declares
``ZONE_STACK`` (L41) but keeps it OUT of ``PLAYER_ZONES``, and the
fingerprint loop (:meth:`GameWorld.fingerprint`) iterates exactly ``PLAYER
_ZONES`` — so a card parked in the stack zone is INVISIBLE to the world
fingerprint. This module therefore parks cards in a lazily-created per-
player ``ZONE_STACK`` :class:`~MTG_bot.core.state.ZoneState` slot
(``zones.setdefault`` — a zero-edit state.py win: ``zone_of``/``move_card``
see it, the world fingerprint does not), and the EXECUTOR fingerprint fold
(``Executor.state_fingerprint``) adds the stack dump + cast ledger — the
established ruling-1 pattern (journal/ledger/layers). The completeness test
is :meth:`SpellStack.dump` round-trip: two worlds differing only by a card
in the stack MUST produce different executor fingerprints (pinned).

LIFO: :attr:`Executor.stack` is a list, append = push, resolve = pop the
top. v1 pushes exactly the spell being cast (no other player can interpose
in a no-interaction world), so pop-top is trivially the CR 405 LIFO order;
the list still makes the ordering explicit and future-visible.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields, is_dataclass
from typing import TYPE_CHECKING

from MTG_bot.core.ability_tree import (
    Atom,
    BackFace,
    Cost,
    SpellAbility,
    SpellKind,
    Verb,
)
from MTG_bot.core.executor.decisions import site_digest
from MTG_bot.core.executor.events import (
    KIND_WINDOW_OPEN,
    KIND_WINDOW_PASS,
    parse_handle_tag,
)
from MTG_bot.core.executor.legality import (
    PaymentPlan,
    build_payment_plan,
    pay_costs,
    spell_castable,
    spell_record,
)
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
# loyalty, which the 13a binder seeds at registration (binding._register).
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
    """One stack frame: the 601.2b–e declaration record (risk-1 mitigation,
    doc /11). Every field is what the CR makes PUBLIC on the stack — the
    future response window reads this frame instead of re-deriving it.

    * ``node`` — the :class:`SpellAbility` IR (§8.3 identity: the same
      object ``legal_casts`` returned and ``apply_effect`` runs);
    * ``x_value`` — the locked X (601.2f — X is chosen with the total cost
      and can no longer change);
    * ``declared_targets`` — the designation tuple (601.2c; canonical
      Handle-sort, ruling 5);
    * ``mode_choices`` — chosen option-set indices under the 12d ORDER
      contract (601.2d "choose a mode"): stored as the positions in
      ``query.choose_options`` order. v1 CONSUMES modes through the effect
      tree's own ``decisions`` channel (the Choose runtime, 12d); this
      field records the declaration for the future window, and the
      sequence alignment is the caller's contract, pinned by cast()'s
      pass-through;
    * ``payment`` — the determined-and-locked plan (601.2f's total);
    * ``declared_clock`` — the journal clock the frame was pushed at;
    * ``kicked`` — ZND-1e (CR 702.27a): was the optional kicker cost paid
      with the total cost? The same truth rides the journalled CAST row
      (the durable carrier WAS_KICKED reads); the frame keeps it visible
      on the stack for the response window and the diagnostics dump.
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
    # RUNG-1: the counter flag. Set by the COUNTER_SPELL handler when a
    # response-window cast interrupts THIS frame; the popper sees it and
    # returns without running the effect (CR 601.4's interrupted
    # resolution). Transient within one cast() call — the frame pops the
    # same breath it is flagged, so dump()/fingerprints never observe it.
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
    """The per-player ``ZONE_STACK`` slot, created on first use (the state.
    py FROZEN-file convention: ``zones.setdefault``, never a constructor
    edit). The world fingerprint loop iterates ``PLAYER_ZONES`` and skips
    it BY DESIGN — :meth:`SpellStack.dump`'s fold is what makes the stack
    visible to the replay fingerprint (completeness test in
    test_executor_stack.py)."""
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
    type word (the frozen ``CardIdentity`` has no structured types field —
    the data-only word test, C12, same convention as TYPE_EQ). The corpus'
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
    is open, the phase is the seat's first main (or not yet stamped — the
    test-skeleton convention from 13a), the stack is empty (v1 proxy:
    nothing can actually be on it mid-op, but the parked-frame API keeps
    the gate honest), and the once-per-turn allowance (CR 305.1 widened by
    ``executor.extra_land_plays`` + the live ADD_LAND_PLAY layer sum, 13c)."""
    world = executor.world
    if not is_land_card(world, handle):
        return "land:not_a_land"
    if world.zone_of(handle) != world.players[seat].zone("hand"):
        return f"land:not_in_hand:{handle}"
    if world.active_player != seat or not executor.turn_open:
        return "land:not_own_turn"
    if executor.phase not in (None, "FIRST_MAIN"):
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
    ``legal_targets`` feeds a Slate — §8.3 identity); the TARGET_PLAYER
    channel (compiled "target opponent", a ControllerRef with NO selector
    to validate — the grammar's documented representational gap) is
    checked as a player-coordinate rule: an opponent seat of the caster.
    Multi-selector spells STAY loud: one designation tuple cannot serve
    two different populations."""
    from MTG_bot.core.executor.query import (
        spell_target_slots,
        validate_target_selection,
    )

    slots = spell_target_slots(executor, node, spell_handle=handle, seat=seat)
    if not targets and not slots:
        return  # targetless spell — the common case
    # 16e: a spell WITH a slot (TARGET selector or the synthesized aura
    # ENCHANT slot) designated nothing falls through to the validator
    # (count_below_min) — never a silent targetless resolution (the
    # Enthralling Hold no-op hole this phase closes).
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
        return
    if len(slots) > 1:
        # r19c (arc 3): per-slot POSITIONAL designation — the same rule the
        # cast lane's _plan_cast_designation applies.
        _validate_positional(slots, targets)
        return
    reason = validate_target_selection(slots[0], targets)
    if reason is not None:
        raise ValueError(f"executor: cast: illegal target selection: {reason}")


def _validate_positional(
    slots: list,
    targets: tuple[Handle, ...],
    skip: frozenset[int] | set[int] = frozenset(),
) -> None:
    """r19c (arc 3 closes): MULTI-slot designation is POSITIONAL — the i-th
    entry of the cast's ``targets`` designates the i-th TARGET selector in
    WALK ORDER, each validated against its OWN slot (the same
    ``validate_target_selection`` oracle — §8.3 identity, one population
    per selector, no cross-slot hijack). Scope: every slot exactly-one
    (QConst(1)); an up-to/one-or-more multi-slot keeps the loud raise (no
    corpus card needs it, and a greedy split would be a guess). A handle
    MAY repeat across slots — the CR's "another target" clause lives in the
    selector's own filter (IS_ANY_TARGET), which is the rules' answer, not
    a second opinion invented here."""
    from MTG_bot.core.executor.query import validate_target_selection

    if any(s.min_count != 1 or s.max_count != 1 for s in slots):
        raise NotImplementedError(
            "executor: cast: multi-slot designation supports exactly-one "
            "TARGET selectors only (r19c)"
        )
    if len(targets) != len(slots):
        raise ValueError(
            f"executor: cast: {len(slots)} TARGET slots need {len(slots)} "
            f"designations, got {len(targets)}"
        )
    for i, (slot, one) in enumerate(zip(slots, targets, strict=True)):
        if i in skip:
            # forced auto-designation (CR 115.4 self-clause): the handle IS
            # the spell, population enumeration cannot see it yet — the
            # designation is trusted BY CONSTRUCTION, not by a pass.
            continue
        reason = validate_target_selection(slot, (one,))
        if reason is not None:
            raise ValueError(f"executor: cast: illegal target selection: {reason}")


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
    tuple[Handle, ...], dict[str, tuple[Handle, ...]], tuple[str, ...], tuple[int, ...]
]:
    """r19c: the CR 601.2b/2c DECLARATION lane — modes, then targets, with
    the three machinery gaps the suspects pinned, each closing a loud raise:

    * **modes before targets** (601.2b): a Choose spell whose options carry
      more than one TARGET slot cannot be validated option-blind — the
      chosen mode decides WHICH slots exist at all. The mode arrives as
      ``mode_choices[0]`` or, when absent, as the leading index token of
      ``decisions`` (the pack's scripted answer, consumed HERE so the
      runtime Choose never re-asks a decision already made);
    * **forced auto-designation** (601.2c, the 18b trigger-lane convention
      mirrored): when the spell designated nothing and EVERY slot has one
      single legal filler — a lone-opponent TARGET_PLAYER population
      (Duress/Mind Rot/Peer/Necromentia), a one-candidate target, or the
      self-exile clause (a TARGET selector whose only satisfier is the
      source spell — Experimental Overload's IS_SOURCE/BATTLEFIELD shape,
      empty at designation because 601.2h parks the spell only LATER; CR
      115.4's own-spell clause) — the cast takes THE answer, because there
      is exactly one and the Slate cannot state it any other way. Any
      slot that leaves a real choice stays loud (count_below_min), never a
      guess;
    * **multi-slot designation** (601.2c): several exactly-one TARGET
      selectors designate POSITIONALLY (:func:`_validate_positional`) and
      return the repr-keyed per-slot map the effect runtime threads into
      ExecCtx.slot_designations.

    Returns ``(designated_targets, slot_designations, remaining_decisions,
    declared_modes)``. Validation of the finished designation happens
    HERE — :func:`cast` must not re-validate mode-blind."""
    from MTG_bot.core.ability_tree import Choose, FAtomPred
    from MTG_bot.core.executor.query import filter_has_pred, spell_target_slots

    slots = spell_target_slots(executor, node, spell_handle=handle, seat=seat)
    remaining = tuple(decisions)
    modes: tuple[int, ...] = ()

    # --- modes before targets (601.2b) ------------------------------------
    if len(slots) > 1 and isinstance(node.effect, Choose):
        if mode_choices:
            mode = int(mode_choices[0])
        elif remaining and remaining[0].lstrip("-").isdigit():
            mode = int(remaining[0])
            remaining = remaining[1:]
        else:
            raise ValueError(
                "executor: cast: a multi-target Choose spell must declare "
                "its mode (mode_choices= or a leading index decision token)"
            )
        if not 0 <= mode < len(node.effect.options):
            raise ValueError(
                f"executor: cast: Choose mode {mode} outside "
                f"0..{len(node.effect.options) - 1}"
            )
        from dataclasses import replace

        active = replace(node, effect=node.effect.options[mode])
        slots = spell_target_slots(executor, active, spell_handle=handle, seat=seat)
        modes = (mode,)

    if not slots:
        # targetless / TARGET_PLAYER-only legacy shapes: the original
        # player-coordinate oracle validates (it re-derives the same slots).
        _validate_spell_targets(executor, seat, handle, node, targets)
        return targets, {}, remaining, modes

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
        return targets, {}, remaining, modes

    _validate_positional(slots, targets, skip=auto_skip)
    slot_designations = {
        repr(slot.selector): (one,) for slot, one in zip(slots, targets, strict=True)
    }
    # a Choose-pruned multi-slot spell lands in the len==1 branch above;
    # a mode the caller supplied AND a multi-slot residue would mean the
    # option STILL fans slots — positional threading covers it unchanged.
    return targets, slot_designations, remaining, modes


def _tree_has_counter(node: object) -> bool:
    """Does an IR subtree (SpellAbility effect trees, Seq/Choose/
    Conditional shapes) contain a COUNTER_SPELL atom? Generic dataclass
    walk — rung-1 must not re-encode the effect grammar; the IR is a
    finite tree (no cycles), so the recursion terminates."""
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
    walk as :func:`_tree_has_counter`). The window's engine-support gate
    asks for the FULL closure, not just the counter atom: a card that
    counts a spell but also executes COPY (Sublime Epiphany) is not
    executable by the engine, and offering it in a vocab that promises
    executability crashed seed 96 of the 100-seed games smoke."""
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
    """RUNG-1 response vocabulary for one seat facing ONE stack frame:
    PASS plus the HANDLED string of every hand card that is a counter
    spell it could legally cast AGAINST THAT FRAME right now. Four gates,
    each the honest answer to a smoke-test failure:

    * counter atom AND ``spell_castable`` (window, mana, record; C15:
      nothing the seat cannot pay is offered);
    * **verb closure** — every atom of the spell node lies in HANDLERS
      (the runtime twin of the compile-time ``engine_supported`` gate;
      Sublime Epiphany's COPY is not offered);
    * **designability** — the frame passes the counter's own TARGET-slot
      legality via :func:`validate_target_selection` (Miscast's
      instant/sorcery filter is never offered at a creature spell — the
      seed-16 crash); ``spell_castable`` cannot see this because it is
      target-blind;
    * **modeless declaration** — exactly one TARGET slot and no Choose
      fan: the window lane casts with ``targets=(frame,)`` and declares
      no mode, so a multi-slot/Choose counter is not offered (seed 96).

    Handle-sorted (ruling 5)."""
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
        reason, _n, _r, plan = spell_castable(executor, seat, handle)
        if reason is not None or plan is None:
            continue
        slots = spell_target_slots(executor, node, spell_handle=handle, seat=seat)
        if len(slots) != 1 or validate_target_selection(slots[0], (frame_handle,)):
            continue
        options.append(str(handle))
    return ("PASS",) + tuple(sorted(options))


#: RUNG-2 (2026-10-05 combat-window arc): the effect atoms that make an
#: instant worth asking about in a post-declare-blockers window — the
#: combat-relevant payloads the corpus actually prints (burn a blocker /
#: attacker, pump your own creature's P/T). Deliberately NARROW, the same
#: way the rung-1 counter vocab is narrow: an instant whose every atom is
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
    """RUNG-2 response vocabulary for one seat in the combat instant
    window: PASS plus one ``<card>@<target>`` token per legal
    (instant, single-target designation) pair it could cast RIGHT NOW.
    The four rung-1 gates (docstring of :func:`_counter_vocab` — each
    one the honest answer to a seed-crash) are re-applied with the
    combat shape swapped in for the counter shape:

    * INSTANT kind + a combat-relevant atom (:data:`_COMBAT_INSTANT_ATOMS`)
      and ``spell_castable`` (mana, record; C15);
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
        reason, _n, _r, plan = spell_castable(executor, seat, handle)
        if reason is not None or plan is None:
            continue
        slots = spell_target_slots(executor, node, spell_handle=handle, seat=seat)
        if len(slots) != 1 or not slots[0].min_count <= 1 <= slots[0].max_count:
            continue
        for target in slots[0].candidates:
            if validate_target_selection(slots[0], (target,)) is None:
                options.append(f"{handle}@{target}")
    return ("PASS",) + tuple(sorted(options))


def open_combat_window(executor: Executor) -> None:
    """RUNG-2 (CR 506.4/510's first slice): the post-declare-blockers
    combat INSTANT window. After blockers are declared and their triggers
    have settled, BEFORE the damage step, both players may cast instants
    (the H3 kill-shot / pump-the-defender fight). One round in
    ``player_order`` (the active player gets the first priority of the
    step, CR 506.4 — the design doc's defender-first sketch is superseded
    by the CR), no priority re-asks: the same documented narrowing as
    rung 1, and every answer is a full-payload ``card@target`` token the
    lane casts via the SAME :func:`cast` pipeline (which nests its own
    rung-1 counter window — the windows compose for free — and settles
    triggers + SBAs internally, so a dead blocker is gone and a pumped
    creature's ledger is live before ``_combat_damage`` reads it).

    A seat with NOTHING castable is never asked and gets NO row (C15).
    Journal rows reuse WINDOW_OPEN/WINDOW_PASS with cause_verb
    ``COMBAT_WINDOW`` and subject=None (no stack frame to point at); the
    decision tag is ``cw:<seat>:<digest>`` — a distinct lane the rig can
    fall back on WITHOUT touching the rung-1 counter:/pay: bytes."""
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
        cast(
            executor,
            seat,
            parse_handle_tag(card_tag),
            targets=(parse_handle_tag(target_tag),),
        )


def cast(
    executor: Executor,
    seat: Handle,
    handle: Handle,
    *,
    x: int | None = None,
    kicked: bool = False,
    mode_choices: tuple[int, ...] = (),
    targets: tuple[Handle, ...] = (),
    decisions: tuple[str, ...] = (),
) -> SpellObject:
    """The folded CR 601.2 → 601.4 move (the ``CAST`` decision of the
    Slate's field schedule — legality, declaration, payment, resolution,
    one call; ``legal_casts`` MUST be consulted first per C15).

    Order (each step is the CR's, and the step names appear in the event
    audit):

    1. **window + shape gate** (:func:`legality.spell_castable`) — the
       card is in hand, its record carries a :class:`SpellAbility`, the
       spell's own window holds (instants anytime; the rest sorcery-
       timed — 13a's phase clock × the empty stack).
    2. **modes** (601.2d) — recorded on the frame; the effect tree's
       Choose nodes CONSUME the 12d ORDER tokens from ``decisions``.
    3. **targets** (601.2c) — validated through ``validate_target_
       selection`` (or the player-coordinate TARGET_PLAYER rule).
    4. **X + total cost** (601.2f) — ``x`` binds ``ExecCtx.x_value`` and
       folds into the plan (a QX cost too big for the pool becomes an
       illegal-cast reason, never a guess).
    5. **payment** (601.2g) — ``pay_costs``, mana segments consumed
       untagged-first with THIS_MANA restrictions honoured for THIS
       spell as the use subject.
    5b. **kick** (601.2b, ZND-1e / CR 702.27a) — ``kicked=True`` declares
       the optional extra cost PAID: the kicker Cost joins the 601.2f
       fold inside ``spell_castable`` (a too-poor pool disappears the
       cast with an ordinary shortage), the choice rides the SpellObject
       frame AND the journalled CAST row, and WAS_KICKED reads the row
       back for every later judge (spell arm, ETB trigger condition,
       gated EtBState). Kicking a card without a kicker is an
       illegal-cast REASON, never a guess; an X-kicker (ZND-1g) prices
       {X} with the cast's X declaration — the same zero-floor law as an
       X-spell (CR 107.1; an explicit ``x`` wins), and the declared X
       lands on the frame and the CAST row.
    6. **push** (601.2h) — park in the stack zone, push the frame, emit
       the journalled ``CAST`` event (the cast-trigger feed, ordinals
       included) and settle — cast triggers resolve ABOVE the spell.
    7. **resolve + put** (601.4, 601.2j) — pop the LIFO frame, run the
       effect (targets bound as ``target``), move the card: instants and
       sorceries to the owner's graveyard, creatures/enchantments/
       planeswalkers to the battlefield (auto-attaching the registered
       compiled record so ETB triggers go live BEFORE the settle sees the
       ETB event).
    """
    world = executor.world
    reason, node, _record, plan = spell_castable(
        executor, seat, handle, x=x, kicked=kicked
    )
    if reason is not None or node is None or plan is None:
        raise ValueError(f"executor: illegal cast: {reason}")

    # 14c (QX, /11 B-14 follow-up): CR 601.2f chooses X WITH the total
    # cost, so the X the legality fold paid (the documented X=0 floor,
    # CR 107.1, when the caller passed no x) MUST be the X the effect
    # reads — the 13b wiring only ever bound the caller's x, leaving
    # x_value None and killing Primal Might deep in resolution when a QX
    # sat in an effect quantity instead of the cost. An explicit x still
    # wins; a spell without X keeps x_value None (the 12c unbound flag
    # outside casting is untouched).
    # ZND-1g (X-kicker, /95 closed): the kicker cost joins the total when
    # the kick was declared, so an X-KICKER announces X exactly like an
    # X-spell — the same zero-floor rule must land the value on the
    # frame and the CAST row, or the fold pays {X}=0 while the journal
    # claims no declaration was made (the Primal Might bug, cost-side).
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

    # 2-3: declaration — r19c: modes (601.2b) then targets (601.2c) through
    # the PLAN lane, which owns auto-designation, the Choose-mode prune and
    # positional multi-slot validation (and thereby the validation itself).
    targets, slot_designations, decisions, declared_modes = _plan_cast_designation(
        executor,
        seat,
        handle,
        node,
        targets=targets,
        decisions=decisions,
        mode_choices=mode_choices,
    )

    # r20b: the TARGETING feed (CR 601.2c). Designation IS an event — one
    # row per designated object, Handle-sorted — emitted the moment the
    # targets are declared, BEFORE payment and the park, so a "whenever
    # ... targets" trigger queues over the spell and drains at the next
    # checkpoint (the mission's mid-cast-feed contract).
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

    # 6b (RUNG-1, CR 608.2's first slice): the RESPONSE WINDOW. Every
    # opponent in seat order MAY answer the frame with a counterspell.
    # One round, seat-ordered, no priority re-asks (documented narrowing
    # above); a dead frame ends the round early; a seat with nothing to
    # offer is skipped WITHOUT an ask (C15) and without a journal row.
    # The nested ``cast`` is the LIFO push — the counter resolves ON TOP
    # of this frame, and its own window opens recursively (a counter can
    # be countered). Answers arrive through the 14b channel's provider
    # lane: ``executor.decisions.take`` DIRECTLY, bypassing the pool —
    # the per-op ``decisions=`` pool belongs to THIS spell's declaration
    # (modes/targets), and letting a window answer consume it would
    # silently re-target the cast (the contamination the pin tests).
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
        cast(executor, responder, parse_handle_tag(answer), targets=(handle,))

    # 7: resolution. The effect runs WITHOUT an intervening settle — the
    # spell leaves the stack and the PUT happens before anything its
    # mutations armed may fire (CR 608.3's resolution is indivisible in v1
    # no-interaction terms; the settle below is the spell's own trigger
    # aftermath).
    popped = executor.stack.pop()
    assert popped is frame  # LIFO: single-caster v1 always pops what pushed
    if frame.countered:
        # RUNG-1 (CR 601.4 interrupted): the COUNTER_SPELL handler already
        # flagged the frame, journalled the COUNTER row and moved the card
        # to its graveyard (400.7). The effect never runs and the spell
        # gets no SPELL_PUT — a countered spell was never put anywhere.
        return frame
    bindings: dict[str, Binding] = {}
    chosen = sorted(targets)
    if chosen:
        bindings["target"] = chosen
    ctx = executor._cast_ctx(handle, seat, bindings, decisions, x)
    # r19c: the per-slot designation map (multi-TARGET spells) and the
    # spell-wide union IS_ANY_TARGET means; both None/empty on every pre-
    # 19c single-slot shape, leaving those lanes byte-unchanged. A mode the
    # declaration consumed for a single-option-set Choose rides on as a
    # PRE-CHOSEN token so the runtime node honours the 601.2b answer
    # instead of re-asking a decision the caster already made.
    if slot_designations:
        ctx.slot_designations = slot_designations
        ctx.designation_union = tuple(sorted(set(targets)))
    if declared_modes:
        from MTG_bot.core.ability_tree import Choose, QConst

        if (
            isinstance(node.effect, Choose)
            and isinstance(node.effect.count, QConst)
            and node.effect.count.value == 1
        ):
            ctx.prechosen_modes = [str(m) for m in declared_modes]
    from MTG_bot.core.executor.query import is_aura_spell

    # 16e (CR 303.4a/608.2a): an aura enters the battlefield ATTACHED, and
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
        # r19a (Life Goes On): an instant/sorcery's own ReplacementAbility
        # nodes go live AT RESOLUTION START — the spell never attaches, so
        # this is the only lifecycle hook the turn-shaped corpus idiom
        # ("…you'd gain 8 life instead") has; registering before the
        # effect runs lets the spell replace its own event. Eot-expired.
        registered = executor.binder.records.get(world.cards[handle].identity.oracle_id)
        if registered is not None:
            # r19b (Scorching Dragonfire): the designation snapshot rides
            # the record — the dies window outlives this ExecCtx, but its
            # anaphora ("that creature") still MEANS this cast's targets.
            executor.replacements.register_ephemeral_replacements(
                handle, seat, registered, designated=tuple(chosen)
            )
    if not aura and node.effect is not None:  # effect-less castable creatures (T3 r3)
        executor._run_guarded_effect(node.effect, ctx, "cast")
    before_put = executor.journal.snapshot()
    start_put = len(executor.events)
    dest = ZONE_GRAVEYARD if node.kind not in _PERMANENT_KINDS else ZONE_BATTLEFIELD
    if dest == ZONE_GRAVEYARD and executor.end_turn_requested:
        # r19b (Discontinuity, CR 716.4a's self-exile clause): the grammar
        # compiles "Take an extra turn after this one. Exile Discontinuity"
        # as the single Atom(END_TURN) — the card-named exile has no slot
        # of its own, so the extra-turn REQUEST itself is the witness:
        # _v_end_turn (verbs.py) is the only setter of the flag, it fires
        # from THIS spell's effect step just above, and the flag is not
        # consumed until the op closes (_consume_end_turn), so no other
        # spell's graveyard move can be re-routed by this branch.
        dest = ZONE_EXILE
    # r19c (Experimental Overload): a spell's own effect may relocate ITSELF
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
        # r23a (Wildwood Scourge, CR 614.1c): the cast-declared X rides to
        # this permanent's ETB firings — recorded as the spell enters, the
        # binder consumes it for THIS entry only. The frozen IR compiles
        # "enters with X counters" as a TriggeredAbility reading QX (EtBState
        # initial-counters shape is a compiler follow-up), so the trigger
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
    # H5 (CR 614.1c): the cast entry runs the SAME zone-change hooks the
    # land drop runs — the compiled EtBState node (Malefic Scythe's "enters
    # with a soul counter", the corpus' entered-tapped idiom) is stamped
    # HERE, as the permanent enters, BEFORE its ETB triggers drain in
    # _settle below. Without this call the node only lit on PLAY_LAND and
    # the execute lane, so CASTING an EtB-state permanent entered with
    # none of its declared entered state.
    executor._on_zone_changes(entered)
    if aura and node.effect is not None:
        executor._run_guarded_effect(node.effect, ctx, "cast")
    executor._settle()
    executor._consume_end_turn()
    return frame


def _face_cast_msg(name: str) -> str:
    return (
        f"executor: CAST {name}: no SpellAbility on the card — the "
        "compiled record carries only a BackFace (the front text never "
        "reached the spell grammar)"
    )


class FaceCastAbsentError(ValueError):
    """/115 (ZNR fuzz seed 1715): an effect-designated MDFC whose compiled
    record has NO SpellAbility — every ability of it sits behind a
    ``BackFace`` node (all 20 ZNR spell-front MDFCs compile this way: the
    front text is unparsed at template level, so the cast producer like
    Coveted Prize picks a card that cannot legally be cast). The refusal
    is LOUD and TYPED (r24a law: dedicated type + byte-exact message, so
    the live-game guard skips ONLY this site); a plain land/creature
    designation keeps the original byte-identical ValueError. The card is
    never silently cast as its BACK face — /106 owner-gates back-face
    casting."""

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
    paid as normal when ``cost_override is None``, otherwise with that
    Cost object as the entire cost (an empty Cost = the corpus' cost-
    waiver idiom, CR 498.2 "without paying its mana cost"). No window
    check (effects cast outside the normal timing — CR 601.2b exemptions;
    v1 documents no further exemption bookkeeping), no response.
    Returns ``True`` when the spell was cast and resolved.

    ``targets`` (CR 603.3: an effect that lets you cast a spell still
    gets its normal target choices — the effect's caster designates them
    NOW) is validated and bound exactly like :func:`cast` step 3. The
    ATOM side has no target channel (the CAST role table is
    ``source``/``cost`` only), so ``verbs._v_cast`` passes an empty
    tuple: an effect-designated spell WITH targets can only be cast
    through this API directly — the corpus' cast-from-effect cards
    (Idol, Snoop, the Chandras) designate target-less creature casts,
    and the gap is flagged by the spell's own unbound-target raise, never
    a silent no-target resolution.

    The frame still gets parked, journalled and fingerprinted: an effect
    cast IS a cast — the ``CAST`` event fires, so "whenever you cast"
    triggers see it (CR 601.2m)."""
    from MTG_bot.core.executor.legality import ctx_for

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
            # /115 seed 1715: the designated card is a model DFC whose
            # ONLY compiled abilities live on the far face — the front
            # was never compiled into a SpellAbility. Refuse TYPED (the
            # guard lane skips + ledgers it); never fabricate a face cast.
            raise FaceCastAbsentError(record.name)
        raise ValueError(f"executor: CAST {record.name}: no SpellAbility on the card")
    _validate_spell_targets(executor, caster, handle, node, targets)
    # r20b: TARGETING feed — same 601.2c contract as cast(): declare, then
    # journal the designation rows before payment.
    executor.journal.emit_targeting(handle, caster, targets)
    cost = cost_override if cost_override is not None else record.mana_cost
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
    popped = executor.stack.pop()
    assert popped is frame
    bindings: dict[str, Binding] = {}
    chosen = sorted(targets)
    if chosen:
        bindings["target"] = chosen
    ctx = executor._cast_ctx(handle, caster, bindings, (), x)
    from MTG_bot.core.executor.query import is_aura_spell

    aura = is_aura_spell(world, handle)
    if aura and not chosen:
        raise ValueError("executor: CAST: an aura cast needs its enchant target")
    if not aura and node.kind not in _PERMANENT_KINDS:
        # r19a: same instant-resolution replacement registration as the
        # normal resolve lane (see resolve_spell's hook).
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
        if x is not None:  # r23a: same CR 614.1c X ride as the cast lane
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
    # H5: same CR 614.1c entered-state stamp as the cast lane above —
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
    to, which is precisely why it IS safe in v1), journal the ETB, stamp
    the once-per-turn ledger, and settle so land ETB triggers fire.
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
    # 17a: the land's entry runs the SAME zone-change hooks as every other
    # battlefield entry — the compiled EtBState node (checklands, temples:
    # "enters the battlefield tapped") is stamped here.
    executor._on_zone_changes(entered)
    turn, plays = executor.land_ledger.get(seat, (world.turn, 0))
    if turn != world.turn:
        plays = 0
    executor.land_ledger[seat] = (world.turn, plays + 1)
    executor._settle()
