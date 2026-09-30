"""The spell stack + the casting pipeline (round 13b, /11 §13b).

CR 601.2 ordered declaration, then resolution — folded into ONE engine call
per cast, exactly the way 12c folded ``ACTIVATE``: re-check legality, choose
modes/targets/X (601.2c–e), determine and LOCK the total cost (601.2f), pay
(601.2g), put the spell on the stack (601.2h), resolve it (601.4), move the
card to its after-resolution zone (601.2j / 400.7).

**No-interaction v1 vs CR 608.2 — the loud gap.** A real spell waits on the
stack while players get a RESPONSE WINDOW (CR 608.2: mana abilities first,
then spells/abilities in APNAP order); counterspells and instants-in-reply
live entirely in that window. This executor has no priority/passing state,
so v1 resolves a cast spell IMMEDIATELY: an uncontested cast always
resolves, and a response window simply does not exist — which means
counters CAN'T exist in v1 either. ``COUNTER_SPELL`` therefore STAYS a
NotImplementedError at dispatch (Cancel and its three siblings keep raising
— flagged, not degraded), and any "counter target spell" text is a
guaranteed loud crash until the arc-3 response API. To keep that API cheap
to add later, every declaration field the CR makes public
(601.2b–e: modes, targets, X, total cost, timing choices) is stored on
:class:`SpellObject` and journalled (risk-1, doc /11) — a future window
reads a complete frame instead of re-deriving one.

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

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from MTG_bot.core.ability_tree import (
    Cost,
    SpellAbility,
    SpellKind,
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
    * ``declared_clock`` — the journal clock the frame was pushed at.
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

    if not targets:
        return  # targetless spell — the common case
    slots = spell_target_slots(executor, node, spell_handle=handle, seat=seat)
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
        raise NotImplementedError(
            "executor: cast: a spell with more than one TARGET selector "
            "needs per-slot designation (arc 3)"
        )
    reason = validate_target_selection(slots[0], targets)
    if reason is not None:
        raise ValueError(f"executor: cast: illegal target selection: {reason}")


def cast(
    executor: Executor,
    seat: Handle,
    handle: Handle,
    *,
    x: int | None = None,
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
    reason, node, _record, plan = spell_castable(executor, seat, handle, x=x)
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
    if x is None:
        from MTG_bot.core.executor.legality import _cost_has_x, spell_cost

        if _cost_has_x(spell_cost(_record, node.additional_costs)):
            x = 0

    # 2-3: declaration.
    _validate_spell_targets(executor, seat, handle, node, targets)

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
        mode_choices=tuple(mode_choices),
        payment=plan,
        declared_clock=executor.journal.clock,
        from_zone="hand",
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
    executor.journal.emit_cast(handle, seat, node.kind.name, "hand", x)
    executor._settle()  # cast triggers resolve first

    # 7: resolution. The effect runs WITHOUT an intervening settle — the
    # spell leaves the stack and the PUT happens before anything its
    # mutations armed may fire (CR 608.3's resolution is indivisible in v1
    # no-interaction terms; the settle below is the spell's own trigger
    # aftermath).
    popped = executor.stack.pop()
    assert popped is frame  # LIFO: single-caster v1 always pops what pushed
    bindings: dict[str, Binding] = {}
    chosen = sorted(targets)
    if chosen:
        bindings["target"] = chosen
    ctx = executor._cast_ctx(handle, seat, bindings, decisions, x)
    if node.effect is not None:  # effect-less castable creatures (T3 r3)
        executor._run_effect(node.effect, ctx)
    before_put = executor.journal.snapshot()
    start_put = len(executor.events)
    dest = ZONE_GRAVEYARD if node.kind not in _PERMANENT_KINDS else ZONE_BATTLEFIELD
    world.move_to_zone(handle, seat, dest)
    executor.events.append(
        (len(executor.events), "SPELL_PUT", str(handle), f"stack->{dest}")
    )
    if dest == ZONE_BATTLEFIELD:
        # The re-entry lifecycle: a pool-registered record re-attaches so
        # the card's own ETB triggers are live BEFORE the journal event is
        # matched (binding._lifecycle re-registers via handle_record; the
        # oracle bridge is identity-checked in attach_card).
        registered = executor.binder.records.get(world.cards[handle].identity.oracle_id)
        if registered is not None:
            executor.binder.attach_card(handle, registered)
    executor.journal.record_atom(
        before_put, handle, "CAST", list(executor.events[start_put:])
    )
    executor._settle()
    executor._consume_end_turn()
    return frame


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
        raise ValueError(f"executor: CAST {record.name}: no SpellAbility on the card")
    _validate_spell_targets(executor, caster, handle, node, targets)
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
    if targets:
        bindings["target"] = sorted(targets)
    ctx = executor._cast_ctx(handle, caster, bindings, (), x)
    if node.effect is not None:
        executor._run_effect(node.effect, ctx)
    before_put = executor.journal.snapshot()
    start_put = len(executor.events)
    dest = ZONE_GRAVEYARD if node.kind not in _PERMANENT_KINDS else ZONE_BATTLEFIELD
    world.move_to_zone(handle, caster, dest)
    executor.events.append(
        (len(executor.events), "SPELL_PUT", str(handle), f"stack->{dest}")
    )
    if dest == ZONE_BATTLEFIELD:
        registered = executor.binder.records.get(world.cards[handle].identity.oracle_id)
        if registered is not None:
            executor.binder.attach_card(handle, registered)
    executor.journal.record_atom(
        before_put, handle, "CAST", list(executor.events[start_put:])
    )
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
    ``tapped`` mirrors the "enters tapped" idiom for lands that must
    (the corpus' lands all enter untapped — the flag is for crafted
    tests of the movement path)."""
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
    executor.journal.record_atom(
        before, handle, "PLAY_LAND", list(executor.events[start:])
    )
    turn, plays = executor.land_ledger.get(seat, (world.turn, 0))
    if turn != world.turn:
        plays = 0
    executor.land_ledger[seat] = (world.turn, plays + 1)
    executor._settle()
