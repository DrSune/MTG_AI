"""Activation legality + cost payment (round 12c, /06 §12c).

The state-side half of the ``ACTIVATE`` decision: is this activated ability
payable right now, and what exactly does paying it do to the world? The
question the model-facing Slate must answer for one candidate row of the
``ACTIVATE / ACTIVATE_MANA`` field schedule
(:class:`docs.DESIGN_ACTION_SPACE` §1.3 — ``ABILITY:PTR``,
``COST_TARGET:PTR*``, ``PAYMENT:PTR*``), and whose payment folds into the
move itself (CR 601.2g; §1.3 "Mana payment folds into the move that needs
it").

Contract highlights:

* **Builder/executor identity (§8.3)** — :func:`ability_playable` and the
  :class:`PaymentPlan` carry typed references to the SAME IR objects the
  executor consumes (:class:`ActivatedAbility`, :class:`Cost`, world
  :class:`Handle`\\ s). No DTOs, no prose in the data (§1.2 role tags are
  type tags, never payloads); the optional ``reason`` return of the
  legality probes is a developer diagnostic, not model-facing data.
* **Canonical order (§5.5)** — every handle tuple in a plan is Handle-sorted
  (ruling 5); the fold's choices (which land taps, which card discards) are
  the canonical first-``n``-sorted witness. The remaining payment freedom
  (which of five forests produced the ``{G}``) is the ``ARITH`` mana-array
  class of §3.3, not an enumerable option.
* **Cost vocabulary** is the closed grammar union in ``ability_tree`` —
  ``CostTap / CostManaColor / CostManaGeneric / CostManaHybrid / CostLife /
  CostSacrifice / CostDiscard / CostPutCounter / CostLoyalty``. (The
  mission's "CostExile" has no member in the frozen grammar — the closed
  vocabulary wins; there is no exile-as-cost node.) ``CostLoyalty`` raises
  a clean notimpl: the frozen :class:`CardState` carries no loyalty field.

Rules encoded, with citations:

* **CR 117.3** — "A player can't pay a cost unless they have the necessary
  resources to pay it fully … a permanent that's already tapped can't be
  tapped to pay a cost." That is the untapped check on :class:`CostTap`
  and the candidate-count floor on every selector-shaped cost.
* **CR 119.4** (life-payment; legacy numbering 118.4) — a life payment
  ``N > 0`` is legal only if the payer's life total is ``>= N``; paying is
  losing that life, so reaching exactly 0 by payment is LEGAL (the death
  is the state-based check afterwards, CR 119.6/704). **CR 119.4b** — a
  0-life payment is always legal. The mission's "life > 1" question is
  settled here as ``life >= amount``: the floor is 0, not 1.
* **C20** (:class:`ActivationWindow`) — ``timing=SORCERY`` means own-main
  phase with an empty stack. The executor has no stack (§1.3 note: the
  query is asked before anything is cast); ``stack_empty`` is an explicit
  parameter, and "own main" is the turn skeleton's ``world.active_player``
  (§12b skeleton: main phases are its only phases).
* **Summoning sickness (CR 302.6)** is NOT representable in the frozen
  state — ``CardState`` carries no "entered since start of turn" timestamp
  — so ``{T}`` costs are checked as CR 117.3 tap-legality only. A
  permissive gap, flagged here rather than faked; 12d's ``DurationLedger``
  is the honest place to add the timestamp if it matters.

:func:`pay_costs` executes a plan through the 12a journalled verbs, so
costs fire the same ``TapState`` / ``ZONE_CHANGE`` / ``SACRIFICE`` events
as any other world mutation (/06 §12c: "the journal sees them — good").
Mana is the exception: no spend-verb exists in ``SUPPORTED_VERBS_V1``, so
the pool arithmetic is a direct deterministic subtraction with a
``("PAY_MANA", …)`` audit row appended to the executor's event log (it
reaches the replay fingerprint, P12).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from MTG_bot.core.ability_tree import (
    ActivatedAbility,
    ActivationWindow,
    Atom,
    AtomArgs,
    ControllerRef,
    Cost,
    CostDiscard,
    CostLife,
    CostLoyalty,
    CostManaColor,
    CostManaGeneric,
    CostManaHybrid,
    CostPutCounter,
    CostSacrifice,
    CostTap,
    CounterKind,
    FAnd,
    QConst,
    Quantity,
    QUnbounded,
    Selector,
    SelectorMode,
    Verb,
    Zone,
    ZoneKind,
)
from MTG_bot.core.executor.quantity import Binding, ExecCtx, eval_filter, resolve
from MTG_bot.core.identity import Handle
from MTG_bot.core.state import (
    PLAYER_ZONES,
    ZONE_BATTLEFIELD,
    GameWorld,
)

if TYPE_CHECKING:  # pragma: no cover - import cycle guard only
    from MTG_bot.core.executor import Executor

# The mana-pool key convention written by ``_v_add_mana`` (verbs.py): pool
# keys are exactly _COLORS_VOCAB = W U B R G C. CostManaColor is payable
# only from its own key (CR 118.3a "removing the indicated mana"); generic
# mana draws from any key in this canonical order.
MANA_KEYS = ("W", "U", "B", "R", "G", "C")

# The payment fold's canonical step order (deterministic journal sequence).
PAYMENT_ORDER = ("mana", "tap", "sacrifice", "discard", "counter", "life")


@dataclass(frozen=True)
class PaymentPlan:
    """The canonical witness that a :class:`Cost` is payable: typed world
    references only (§8.3 identity, §1.2 role tags are types not tokens),
    every tuple Handle-sorted (§5.5, ruling 5).

    * ``mana``      — the ``PAYMENT:PTR``-array fold: (pool key, amount)
      pairs in :data:`MANA_KEYS` order; ``tap``/``sacrifice``/``discard``
      are the ``COST_TARGET:PTR*`` designations (§1.3 ACTIVATE schedule);
    * ``counters``  — (handle, CounterKind name, count) for CostPutCounter;
    * ``life``      — the CostLife amount (CR 119.4-checked).
    """

    mana: tuple[tuple[str, int], ...] = ()
    tap: tuple[Handle, ...] = ()
    sacrifice: tuple[Handle, ...] = ()
    discard: tuple[Handle, ...] = ()
    counters: tuple[tuple[Handle, str, int], ...] = ()
    life: int = 0

    def is_empty(self) -> bool:
        """True for a free activation (empty Cost parts — legal MTG)."""
        return not (
            self.mana
            or self.tap
            or self.sacrifice
            or self.discard
            or self.counters
            or self.life
        )


# ---------------------------------------------------------------- contexts


def ctx_for(
    executor: Executor,
    source: Handle,
    controller: Handle,
    bindings: dict[str, Binding] | None = None,
) -> ExecCtx:
    """An :class:`ExecCtx` sharing the executor's world, ledger, seeded rng
    factory and token counters — the activation context that closes the 12a
    OWNER-referent gap: OWNER reads resolve to the source's zone controller
    (:func:`enumerate_candidates`), which is exactly what an activation
    context supplies (/06 §12c close-out list)."""
    return ExecCtx(
        world=executor.world,
        ledger=executor.ledger,
        controller=controller,
        source=source,
        bindings=dict(bindings or {}),
        decisions=(),
        events=[],
        rng=executor.rng,
        token_counts=executor.token_counts,
        # 12d: the query/payment context sees the registries too (a paid
        # tap-cost can trip a replacement; layer verbs fired from an
        # activation effect reach them through the effect ctx).
        layers=executor.layers,
        replacements=executor.replacements,
        executor=executor,
    )


def source_owner(world: GameWorld, ctx: ExecCtx) -> Handle:
    """The OWNER referent in an activation context: the zone controller of
    the source (the frozen state tracks zone control only — the documented
    stand-in, matching ``selectors.zone_owner``'s OWNER handling)."""
    if ctx.source.namespace == "card" and ctx.source in world.cards:
        return world.controller_of(ctx.source)
    return ctx.controller


# ------------------------------------------------------- candidate search


def _zone_handles(ctx: ExecCtx, zone: Zone) -> list[Handle]:
    """Candidate enumeration for the QUERY surface — the map that closes
    the 12a raises this phase owns (/06 §12c): ``Zone(ANY)`` becomes every
    player zone in seat × :data:`PLAYER_ZONES` order, and an ``OWNER``
    controller ref becomes the activation owner's zone. Zone(STACK) still
    raises: the frozen state has no stack and the queue shapes are OUT.

    The 12a :func:`~MTG_bot.core.executor.selectors.enumerate_zone` is
    reused for everything else, so effect-time resolution and query-time
    enumeration share one zone-order convention (§8.3 identity)."""
    world = ctx.world
    if zone.kind is ZoneKind.STACK:
        raise NotImplementedError(
            "executor: Zone(STACK) enumeration needs the stack (queue "
            "shapes are OUT of round 12)"
        )
    owner = source_owner(world, ctx)
    if zone.controller is ControllerRef.OWNER:
        if zone.kind is ZoneKind.PLAYER:
            return [owner]
        return list(world.players[owner].zone(_STATE_KIND[zone.kind]).entries)
    if zone.kind is ZoneKind.ANY:
        handles: list[Handle] = []
        for player in world.player_order:
            for kind in PLAYER_ZONES:
                handles.extend(world.players[player].zone(kind).entries)
        return handles
    # 12a path (PLAYER refs, positions, TOP/BOTTOM): identical semantics.
    from MTG_bot.core.executor.selectors import enumerate_zone

    return enumerate_zone(ctx, zone)


# Local mirror of selectors.ZONE_KIND_TO_STATE (kept lazy-cycle-free; the
# enum is frozen so the table cannot drift silently — a test pins it).
from MTG_bot.core.executor.selectors import ZONE_KIND_TO_STATE as _STATE_KIND


def enumerate_candidates(sel: Selector, ctx: ExecCtx) -> list[Handle]:
    """The legal candidate set of one Selector IR node in ``ctx`` —
    Handle-sorted (§5.5). This is the per-slot candidate list the query
    surface returns; whole-selection legality is
    :func:`legality.validate_target_selection`'s counterpart in query.py
    (combinatorial explosion guard: candidates per slot, never a product
    of per-slot lists).

    A referent selector (C2/C12 closed vocab) resolves through
    :func:`~MTG_bot.core.executor.selectors.resolve_selector` — the SAME
    resolver the executor runs at resolution time. A TARGET-mode selector
    without the 12a designations is still enumerable here: the population
    is what the query asks for; the designation is what the Slate answers
    (CR 601.2 / §1.3 ``TARGET:PTR x n``)."""
    from MTG_bot.core.executor.selectors import resolve_selector

    if sel.referent is not None:
        if sel.referent == "target":
            bound = ctx.binding_handles("target")
            candidates = bound if bound is not None else []
        elif sel.referent in ("source", "controller"):
            candidates = resolve_selector(sel, ctx)
        else:
            candidates = resolve_selector(sel, ctx)  # raises cleanly (12b reg)
    else:
        candidates = list(_zone_handles(ctx, sel.zone))
        for extra in sel.zones:
            candidates.extend(_zone_handles(ctx, extra))
    return sorted(h for h in candidates if eval_filter(sel.filter, h, ctx))


def _required_count(count: Quantity, ctx: ExecCtx) -> int:
    """How many objects a cost's selector demands (costs pay in full —
    CR 117.3). QUnbounded in a cost position is the degenerate "any
    number"; the resource floor is one (paying zero is not paying)."""
    if isinstance(count, QUnbounded):
        return 1
    return max(1, resolve(count, ctx))


# ---------------------------------------------------------------- payment


def build_payment_plan(
    world: GameWorld, ctx: ExecCtx, cost: Cost
) -> tuple[PaymentPlan | None, str | None]:
    """Fold one :class:`Cost` against the world into the canonical
    :class:`PaymentPlan`, or a machine-readable reason string.

    Returns ``(plan, None)`` when every part is payable, ``(None, reason)``
    when a resource is short, and raises ``NotImplementedError`` for cost
    kinds the executor must not guess (``CostLoyalty``: no loyalty field in
    the frozen state; ``QX`` amounts: the Slate's ``X_VALUE`` NUM field is
    a declaration the caller must supply — ``quantity.resolve`` flags it).
    """
    tap: list[Handle] = []
    sacrifice: list[Handle] = []
    discard: list[Handle] = []
    counters: list[tuple[Handle, str, int]] = []
    life = 0
    remaining: dict[str, int] = dict(world.players[ctx.controller].mana_pool)
    spent: dict[str, int] = {}
    generic_need = 0
    hybrid_demands: list[tuple[tuple[str, str], int]] = []

    for part in cost.parts:
        if isinstance(part, CostManaColor):
            need = resolve(part.amount, ctx)
            have = remaining.get(part.color, 0) - spent.get(part.color, 0)
            if have < need:
                return None, f"cost:mana:{part.color}:{have}<{need}"
            spent[part.color] = spent.get(part.color, 0) + need
        elif isinstance(part, CostManaGeneric):
            generic_need += resolve(part.amount, ctx)
        elif isinstance(part, CostManaHybrid):
            hybrid_demands.append((part.colors, resolve(part.amount, ctx)))
        elif isinstance(part, CostTap):
            if part.target is None:  # "the source itself" — every {T}:
                if world.cards[ctx.source].tapped:
                    # CR 117.3: an already-tapped permanent can't be tapped.
                    return None, "cost:tap:source_tapped"
                tap.append(ctx.source)
            else:
                cands = [
                    h
                    for h in enumerate_candidates(part.target, ctx)
                    if not world.cards[h].tapped
                ]
                need = _required_count(part.target.count, ctx)
                if len(cands) < need:
                    return None, (
                        f"cost:tap:insufficient_candidates:{len(cands)}<{need}"
                    )
                tap.extend(cands[:need])
        elif isinstance(part, CostSacrifice):
            cands = enumerate_candidates(part.target, ctx)
            need = _required_count(part.target.count, ctx)
            if len(cands) < need:
                return None, (
                    f"cost:sacrifice:insufficient_candidates:{len(cands)}<{need}"
                )
            sacrifice.extend(cands[:need])
        elif isinstance(part, CostDiscard):
            cands = enumerate_candidates(part.target, ctx)
            need = _required_count(part.target.count, ctx)
            if len(cands) < need:
                return None, (
                    f"cost:discard:insufficient_candidates:{len(cands)}<{need}"
                )
            discard.extend(cands[:need])
        elif isinstance(part, CostPutCounter):
            cands = enumerate_candidates(part.target, ctx)
            need = _required_count(part.target.count, ctx)
            if len(cands) < need:
                return None, (
                    f"cost:put_counter:insufficient_candidates:{len(cands)}<{need}"
                )
            n = resolve(part.count, ctx)
            counters.extend((h, part.counter_kind.name, n) for h in cands[:need])
        elif isinstance(part, CostLife):
            amount = resolve(part.amount, ctx)
            payer = world.players[ctx.controller]
            # CR 119.4: an N>0 life payment is legal only with life >= N;
            # reaching exactly 0 is legal (payment IS life loss; the death
            # is the CR 119.6/704 state check afterwards). CR 119.4b: a
            # 0-life payment is always legal.
            if payer.life < amount:
                return None, f"cost:life:{payer.life}<{amount}"
            life += amount
        elif isinstance(part, CostLoyalty):
            raise NotImplementedError(
                "executor: CostLoyalty payment needs a loyalty field on the "
                "frozen CardState (planeswalker loyalty activations are 12d+)"
            )
        else:  # pragma: no cover - CostPart is a closed union
            raise NotImplementedError(
                f"executor: cost part {type(part).__name__} not implemented"
            )

    # Hybrid symbols (CR 118.13a: the payer chooses how each is paid when
    # the ability is proposed): the canonical witness prefers the symbol's
    # first printed colour, falling back to its second.
    for colors, count in hybrid_demands:
        for _ in range(count):
            chosen = next(
                (c for c in colors if remaining.get(c, 0) - spent.get(c, 0) > 0),
                None,
            )
            if chosen is None:
                return None, f"cost:mana_hybrid:{colors}:{count} unpayable"
            spent[chosen] = spent.get(chosen, 0) + 1
    # Generic mana draws from any remaining key in canonical order.
    if generic_need:
        pool_left = sum(remaining.get(k, 0) - spent.get(k, 0) for k in MANA_KEYS)
        if pool_left < generic_need:
            return None, f"cost:mana_generic:{pool_left}<{generic_need}"
        for key in MANA_KEYS:
            take = min(remaining.get(key, 0) - spent.get(key, 0), generic_need)
            if take > 0:
                spent[key] = spent.get(key, 0) + take
                generic_need -= take

    mana = tuple((k, v) for k, v in sorted(spent.items()) if v)
    plan = PaymentPlan(
        mana=mana,
        tap=tuple(sorted(tap)),
        sacrifice=tuple(sorted(set(sacrifice))),
        discard=tuple(sorted(set(discard))),
        counters=tuple(sorted(counters)),
        life=life,
    )
    return plan, None


# ------------------------------------------------------------- legality


def ability_playable(
    world: GameWorld,
    executor: Executor,
    handle: Handle,
    ability_idx: int,
    *,
    seat: Handle,
    stack_empty: bool = True,
    condition_ctx_source: Handle | None = None,
) -> str | None:
    """Is ``handle``'s ``ability_idx``-th compiled ability activatable by
    ``seat`` right now? ``None`` when legal, else a machine-readable reason
    string (a developer diagnostic — model-facing data is plan-shaped).

    Gates, in order:

    1. **window** — the attached record must exist (the 12b bridge), the
       node must be an :class:`ActivatedAbility`, and for
       ``timing=SORCERY`` (C20) the seat must be ``world.active_player``
       (the skeleton's own main phase) with ``stack_empty=True``. The
       executor has no stack, so emptiness is an explicit parameter of the
       pre-casting query, per the grammar's C20 note.
    2. **condition** — ``ActivatedAbility.condition`` (a state predicate
        over the source, the StaticAbility convention) judged against the
        source handle; an unsupported pred raises (flag, never guess).
    3. **cost** — :func:`build_payment_plan` (CR 117.3 resource
       arithmetic + the untapped check + CR 119.4 life floor).

    12d — GRANTED abilities are addressed by NEGATIVE index: row ``-k-1``
    is entry ``k`` of ``executor.layers.granted_activated(handle)`` (layer-
    seq order, the canonical basis :func:`legal_activations` uses). The
    CONTROLLER RULE: the source is the granted permanent and every
    coordinate of the run (cost ``you``, effects, mana pool) belongs to
    ``seat`` — the GRANTEE; a granted ability needs no compiled record for
    the granted object (tokens activate what they were granted).
    """
    if ability_idx < 0:
        granted = executor.layers.granted_activated(handle)
        idx = -ability_idx - 1
        if idx >= len(granted):
            raise ValueError(
                f"ability_playable: {handle} has no granted ability idx {ability_idx}"
            )
        ability = granted[idx].node
    else:
        record = executor.binder.handle_record.get(handle)
        if record is None:
            return f"bridge:no_record:{handle}"
        if not 0 <= ability_idx < len(record.abilities):
            raise ValueError(
                f"ability_playable: {handle} has no ability idx {ability_idx}"
            )
        ability = record.abilities[ability_idx]
    if not isinstance(ability, ActivatedAbility):
        return f"ability:not_activated:{type(ability).__name__}"
    if handle in world.cards and world.zone_of(handle).kind != ZONE_BATTLEFIELD:
        return f"window:not_on_battlefield:{handle}"
    if handle in world.cards and world.controller_of(handle) != seat:
        # CR 602.3: only the permanent's controller can activate it.
        return f"window:not_controller:{seat}"
    if ability.timing is ActivationWindow.SORCERY:
        if world.active_player != seat:
            return "window:sorcery:not_own_turn"
        if not stack_empty:
            return "window:sorcery:stack_nonempty"
    ctx = ctx_for(executor, source=handle, controller=seat)
    if ability.condition is not None:
        subject = condition_ctx_source if condition_ctx_source is not None else handle
        if not eval_filter(ability.condition, subject, ctx):
            return "condition:false"
    plan, reason = build_payment_plan(world, ctx, ability.cost)
    if plan is None:
        return reason
    return None


# -------------------------------------------------------------- payment


def _binding_atom(verb: Verb, role: str, handles: Sequence[Handle], **extra) -> Atom:
    """An Atom whose ``role`` carries a placeholder Selector while the real
    designation rides in via bindings — the 12a convention (role_handles
    checks bindings first), so the payment runs through the journalled
    verb dispatch unchanged."""
    pairs = dict(extra)
    pairs[role] = Selector(
        QConst(max(1, len(handles))),
        SelectorMode.TARGET,
        FAnd(()),
        Zone(ZoneKind.ANY, ControllerRef.ANY),
    )
    return Atom(verb=verb, args=AtomArgs(pairs=tuple(pairs.items())))


def pay_costs(
    executor: Executor,
    plan: PaymentPlan,
    *,
    source: Handle,
    controller: Handle,
    trigger_decisions: Sequence[str] = (),
) -> None:
    """Execute a :class:`PaymentPlan` through the 12a journalled verbs in
    :data:`PAYMENT_ORDER` — taps, sacrifices, discards and counters fire
    their journal events exactly like effect atoms (TapState, ZONE_CHANGE,
    SACRIFICE…), and each step settles triggers the payment armed. Mana is
    the deterministic pool subtraction (no v1 spend-verb exists) with a
    ``PAY_MANA`` audit row on the executor event log.

    Ordering note, honestly made: costs are paid simultaneously in the
    real game, and the trigger from a sacrificed permanent resolves
    ahead of the activation only because the stack orders it so — the
    executor has no stack (§1.3 note; queue shapes OUT), so a sac-trigger
    settles mid-payment here, at the step boundary. No golden exercises
    that interleaving; it is a documented stack-phase debt, not a silent
    one."""
    world = executor.world
    if plan.mana:
        pool = world.players[controller].mana_pool
        for key, amount in plan.mana:
            if pool.get(key, 0) < amount:
                raise ValueError(
                    f"executor: PAY_MANA {key} x{amount} exceeds pool "
                    f"{dict(pool)} (plan stale for this world?)"
                )
            pool[key] = pool[key] - amount
            if pool[key] == 0:
                del pool[key]
        executor.events.append(
            (len(executor.events), "PAY_MANA", str(controller), plan.mana)
        )
    if plan.tap:
        executor.apply_effect(
            _binding_atom(Verb.TAP, "target", plan.tap),
            source=source,
            controller=controller,
            bindings={"target": list(plan.tap)},
            trigger_decisions=trigger_decisions,
        )
    if plan.sacrifice:
        executor.apply_effect(
            _binding_atom(Verb.SACRIFICE, "target", plan.sacrifice),
            source=source,
            controller=controller,
            bindings={"target": list(plan.sacrifice)},
            trigger_decisions=trigger_decisions,
        )
    if plan.discard:
        executor.apply_effect(
            _binding_atom(
                Verb.DISCARD, "cards", plan.discard, controller=ControllerRef.YOU
            ),
            source=source,
            controller=controller,
            bindings={"cards": list(plan.discard)},
            trigger_decisions=trigger_decisions,
        )
    for handle, kind_name, count in plan.counters:
        executor.apply_effect(
            _binding_atom(
                Verb.PUT_COUNTER,
                "target",
                [handle],
                counter_kind=CounterKind[kind_name],
                count=QConst(count),
            ),
            source=source,
            controller=controller,
            bindings={"target": [handle]},
            trigger_decisions=trigger_decisions,
        )
    if plan.life:
        executor.apply_effect(
            Atom(
                verb=Verb.LOSE_LIFE,
                args=AtomArgs(
                    pairs=(
                        ("controller", ControllerRef.YOU),
                        ("amount", QConst(plan.life)),
                    )
                ),
            ),
            source=source,
            controller=controller,
            trigger_decisions=trigger_decisions,
        )


def activate(
    executor: Executor,
    handle: Handle,
    ability_idx: int,
    *,
    seat: Handle,
    targets: Sequence[Handle] = (),
    decisions: Sequence[str] = (),
    trigger_decisions: Sequence[str] = (),
    stack_empty: bool = True,
) -> tuple:
    """The folded ``ACTIVATE`` move (§1.3: legality, payment, effect — one
    engine call, no five micro-decisions to tap five lands): re-check
    :func:`ability_playable` against the live world (illegal →
    ``ValueError(reason)``), :func:`pay_costs`, then run the ability's
    effect with ``targets`` designated as the ``target`` bindings the 12a
    role readers consume. The effect tree's own decisions
    (``OptionalEffect`` fire/skip, any-colour ADD_MANA) come through
    ``decisions`` in tree order (C15). Returns the effect's event tuple."""
    reason = ability_playable(
        executor.world,
        executor,
        handle,
        ability_idx,
        seat=seat,
        stack_empty=stack_empty,
    )
    if reason is not None:
        raise ValueError(f"executor: illegal activation: {reason}")
    if ability_idx < 0:
        # 12d granted row (see ability_playable's controller rule): the
        # ability's SOURCE is the granted permanent and the effect runs in
        # the GRANTEE's coordinates (``seat``) — source=handle below.
        granted = executor.layers.granted_activated(handle)
        ability = granted[-ability_idx - 1].node
    else:
        record = executor.binder.handle_record[handle]
        ability = record.abilities[ability_idx]
    if not isinstance(ability, ActivatedAbility):  # pragma: no cover — checked
        # ValueError, not TypeError: "illegal activation" is the documented
        # domain contract of activate(), whatever the wrong input was.
        raise ValueError(  # noqa: TRY004
            "executor: illegal activation: ability:not_activated"
        )
    ctx = ctx_for(executor, source=handle, controller=seat)
    plan, plan_reason = build_payment_plan(executor.world, ctx, ability.cost)
    if plan is None:  # pragma: no cover - ability_playable just checked
        raise ValueError(f"executor: illegal activation: {plan_reason}")
    pay_costs(executor, plan, source=handle, controller=seat)
    bindings: dict[str, Binding] = {}
    chosen = sorted(targets)
    if chosen:
        bindings["target"] = chosen
    effect = ability.effect
    assert effect is not None  # ActivatedAbility.effect is a required field
    return executor.apply_effect(
        effect,
        source=handle,
        controller=seat,
        bindings=bindings,
        decisions=decisions,
        trigger_decisions=trigger_decisions,
    )
