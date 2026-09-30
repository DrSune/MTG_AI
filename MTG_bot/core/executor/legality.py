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
  vocabulary wins; there is no exile-as-cost node.) ``CostLoyalty`` is the
  13a addition: the frozen :class:`CardState` has no loyalty field, so the
  ledger rides on its ``counters`` map under ``CounterKind.LOYALTY.name``
  (seeded from the printed :attr:`CardIdentity.loyalty` at binding,
  :mod:`executor.binding`) and steps through the journalled counter verbs.

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
    QX,
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
    FAtom,
    FAtomPred,
    Filter,
    Keyword,
    Phase,
    QBin,
    QConst,
    Quantity,
    QUnbounded,
    Selector,
    SelectorMode,
    SpellAbility,
    SpellKind,
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
PAYMENT_ORDER = ("mana", "tap", "sacrifice", "discard", "counter", "loyalty", "life")


# ------------------------------------------------------------- mana segments


@dataclass
class ManaSegment:
    """One ADD_MANA production in the 13b side-ledger: a colour key, an
    amount, and the spend RESTRICTIONS carried as closed-grammar Filters
    (``tags`` — Vodalian Arcanist's "Spend this mana only to cast instant
    or sorcery spells" compiles to ``FOr(TYPE_EQ Instant, TYPE_EQ
    Sorcery)``). EMPTY tags = ordinary mana: every totals-path computation
    is exactly the 12a/12b arithmetic, which is what keeps the replay pins
    byte-identical (risk-2 mitigation, doc /11)."""

    color: str
    amount: int
    tags: tuple[Filter, ...] = ()  # spend-restriction Filters (R9-3 shape)


class ManaLedger:
    """The executor-side segment mirror of the frozen per-player mana pool.

    WHY a mirror: ``PlayerState.mana_pool`` is a colour-keyed ``Dict[str,
    int]`` totals map — it CANNOT express "this {C} came from Vodalian
    Arcanist and may only buy instants". Redesigning the frozen pool would
    churn every 12a/12b payment pin, so segments ride ALONGSIDE (ruling-1
    executor state, folded into the replay fingerprint):

    * ``add`` is called by the ADD_MANA handler next to the untouched pool
      totals write (tags decided by the source's live THIS_MANA policy);
    * :meth:`restricted_amounts` is the spend-validator's ONLY consult in
      :func:`build_payment_plan` — tagged segments whose filters do not
      match the payment's use (the spell being cast) are removed from the
      usable totals, so a plan can never BE built on forbidden mana;
    * :meth:`consume` settles the mirror after :func:`pay_costs` subtracts
      the frozen totals, untagged-first (the mission-sanctioned canonical
      order; the CR lets the payer choose, determinism pins the witness).

    A pool written to directly (bare tests, non-ADD_MANA grants) is simply
    UNTRACKED = unrestricted — documented mirror drift (the segment list
    floors at empty; nothing crashes), honest because the corpus' mana all
    arrives through ADD_MANA."""

    def __init__(self) -> None:
        self.segments: dict[Handle, list[ManaSegment]] = {}

    def add(
        self, player: Handle, color: str, amount: int, tags: tuple[Filter, ...] = ()
    ) -> None:
        if amount <= 0:
            return
        self.segments.setdefault(player, []).append(ManaSegment(color, amount, tags))

    def has(self, player: Handle) -> bool:
        return bool(self.segments.get(player))

    @staticmethod
    def _matches(seg: ManaSegment, use_ok) -> bool:
        if not seg.tags:
            return True
        return use_ok is not None and all(use_ok(f) for f in seg.tags)

    def restricted_amounts(
        self,
        player: Handle,
        use_ok,  # Callable[[Filter], bool] | None — None = no use context
    ) -> dict[str, int]:
        """Amounts per colour key that the CURRENT payment may not touch:
        tagged segments whose filters fail against the payment's use.
        Empty dict (the ONLY pre-13b reality) leaves the plan arithmetic
        byte-identical to the 12a/12b totals path."""
        out: dict[str, int] = {}
        for seg in self.segments.get(player, ()):
            if seg.tags and not self._matches(seg, use_ok):
                out[seg.color] = out.get(seg.color, 0) + seg.amount
        return out

    def consume(
        self, player: Handle, mana: tuple[tuple[str, int], ...], use_ok
    ) -> None:
        """Mirror the :func:`pay_costs` subtraction: for each (key, amount)
        draw untagged segments first, then filter-matching tagged ones;
        non-matching tagged segments are NEVER touched (the plan could not
        have used them, and a stale plan paying them must not silently
        drain a restriction). Untracked pool mana floors the draw at the
        available segments — mirror drift, documented, never a crash."""
        segs = self.segments.get(player, [])
        for key, amount in mana:
            left = amount
            # untagged first (canonical), then matching tagged, in order.
            for pass_matches in (True, False):
                for seg in segs:
                    if left <= 0 or seg.color != key or seg.amount <= 0:
                        continue
                    tagged = bool(seg.tags)
                    if tagged and (not pass_matches or not self._matches(seg, use_ok)):
                        continue
                    if not tagged and not pass_matches:
                        continue
                    take = min(seg.amount, left)
                    seg.amount -= take
                    left -= take
        self.segments[player] = [s for s in segs if s.amount > 0]

    def dump(self) -> tuple[tuple[object, ...], ...]:
        """Canonical segment view for the fingerprint fold."""
        return tuple(
            (
                str(player),
                tuple(
                    (s.color, s.amount, tuple(repr(t) for t in s.tags)) for s in segs
                ),
            )
            for player, segs in sorted(self.segments.items(), key=lambda kv: str(kv[0]))
            if segs
        )


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
    loyalty: int = 0
    life: int = 0

    def is_empty(self) -> bool:
        """True for a free activation (empty Cost parts — legal MTG)."""
        return not (
            self.mana
            or self.tap
            or self.sacrifice
            or self.discard
            or self.counters
            or self.loyalty
            or self.life
        )


# ---------------------------------------------------------------- contexts


def ctx_for(
    executor: Executor,
    source: Handle,
    controller: Handle,
    bindings: dict[str, Binding] | None = None,
    x_value: int | None = None,
) -> ExecCtx:
    """An :class:`ExecCtx` sharing the executor's world, ledger, seeded rng
    factory and token counters — the activation context that closes the 12a
    OWNER-referent gap: OWNER reads resolve to the source's zone controller
    (:func:`enumerate_candidates`), which is exactly what an activation
    context supplies (/06 §12c close-out list). 13b: ``x_value`` carries
    the cast's declared X (QX resolves; ``None`` keeps the 12c flag)."""
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
        x_value=x_value,
        stream=executor.decisions,
        # 14d (B-7): the journal binds into the QUERY context as well —
        # journal-aware eval at every entry point. Purity holds: the journal
        # is state, the read is deterministic and fingerprinted (12b dump).
        journal=executor.journal,
    )


def source_owner(world: GameWorld, ctx: ExecCtx) -> Handle:
    """The OWNER referent in an activation context: the zone controller of
    the source (the frozen state tracks zone control only — the documented
    stand-in, matching ``selectors.zone_owner``'s OWNER handling)."""
    if ctx.source.namespace == "card" and ctx.source in world.cards:
        return world.controller_of(ctx.source)
    return ctx.controller


def _loyalty_of(world: GameWorld, handle: Handle) -> int:
    """The loyalty ledger value (13a): the ``"LOYALTY"`` counter, falling
    back to the printed :attr:`CardIdentity.loyalty` only for a raw card
    whose ledger has not been seeded yet (a card built straight into a
    zone, before binding). 0 when the card has no loyalty at all (a non-
    planeswalker paying a loyalty cost is illegal, and
    :func:`build_payment_plan` flags it).

    Note: the generic counter verb deletes a zeroed counter key.  A payment
    that brings loyalty to exactly 0 therefore passes the resulting ledger
    value to :func:`_loyalty_death_check` directly rather than rereading it
    here.
    """
    state = world.cards.get(handle)
    if state is None:
        return 0
    if "LOYALTY" in state.counters:
        return state.counters["LOYALTY"]
    printed = state.identity.loyalty
    if printed is None:
        return 0
    try:
        return int(printed)
    except ValueError:  # pragma: no cover - printed loyalty is a numeral
        return 0


# ------------------------------------------------------- candidate search


def _zone_handles(ctx: ExecCtx, zone: Zone) -> list[Handle]:
    """Candidate enumeration for the QUERY surface — the map that closes
    the 12a raises this phase owns (/06 §12c): ``Zone(ANY)`` becomes every
    player zone in seat × :data:`PLAYER_ZONES` order, and an ``OWNER``
    controller ref becomes the activation owner's zone.

    14a: Zone(STACK) USED to raise here ("the frozen state has no stack and
    the queue shapes are OUT") — that was round-12 truth and 13b made it
    stale: the executor has a stack now, journalled as each seat's
    ``ZONE_STACK`` slot by :func:`stack.stack_zone` with ``SpellStack`` frames
    on top. Answering instead of raising is load-bearing, not cosmetic: a card
    whose TARGET selector names the stack (M21 Unsubstantiate prints
    ``BATTLEFIELD + STACK``) was unreachable through the query surface by a
    route that looked legal — :func:`legal_casts` folded its cost and called it
    castable, then :func:`spell_target_slots` raised on the very next question
    (games harness /03 row B-2). The stack stays OUT of :data:`PLAYER_ZONES`,
    so ``Zone(ANY)`` keeps its 12a meaning and only an explicit STACK zone
    reaches these entries.

    The 12a :func:`~MTG_bot.core.executor.selectors.enumerate_zone` is
    reused for everything else, so effect-time resolution and query-time
    enumeration share one zone-order convention (§8.3 identity)."""
    world = ctx.world
    if zone.kind is ZoneKind.STACK:
        from MTG_bot.core.executor.selectors import players_for_ref
        from MTG_bot.core.executor.stack import stack_zone

        if zone.controller is ControllerRef.OWNER:
            return list(stack_zone(world, source_owner(world, ctx)).entries)
        return [
            handle
            for seat in players_for_ref(zone.controller, ctx)
            for handle in stack_zone(world, seat).entries
        ]
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


def _mana_use_ok(executor: Executor, ctx: ExecCtx, mana_use: Handle | None):
    """The 13b spend-validator's filter judge: does a restriction Filter
    accept this payment's use? The use subject is the SPELL being paid for
    (Vodalian's compiled filter is a CastSpellEvent-shape ``TYPE_EQ``
    reading over the spell card — the grammar R9-3 design). No use context
    (an activation cost, a payment outside a cast) can demonstrate the
    filter's subject, so a tagged segment is simply NOT available — the
    conservative, rule-honest reading ("Spend this mana only to cast
    instant or sorcery spells" cannot be demonstrated by an activation)."""
    if mana_use is None:
        return None

    def use_ok(filter_: Filter) -> bool:
        return eval_filter(filter_, mana_use, ctx)

    return use_ok


def build_payment_plan(
    world: GameWorld,
    ctx: ExecCtx,
    cost: Cost,
    *,
    mana_use: Handle | None = None,
) -> tuple[PaymentPlan | None, str | None]:
    """Fold one :class:`Cost` against the world into the canonical
    :class:`PaymentPlan`, or a machine-readable reason string.

    Returns ``(plan, None)`` when every part is payable, ``(None, reason)``
    when a resource is short, and raises ``NotImplementedError`` for cost
    kinds the executor must not guess (``CostLoyalty``: no loyalty field in
    the frozen state; ``QX`` amounts: the Slate's ``X_VALUE`` NUM field is
    a declaration the caller must supply — ``quantity.resolve`` flags it).

    13b mana restrictions (only-when-tagged, risk-2): the plan arithmetic
    runs on the RESTRICTION-ADJUSTED pool — an executor whose ManaLedger
    has tagged segments removes from the usable totals every tagged amount
    whose filter fails against ``mana_use`` (the spell being paid for;
    :func:`_mana_use_ok`). With no segments/tags in play — every 12a/12b
    corpus payment — the adjusted pool IS the pool and the arithmetic is
    byte-identical. The OTHER policy axis, the ALL_YOURS permission
    (Chromatic Orrery's "spend mana as though it were mana of any color"),
    makes a coloured demand drawable from any colour key (own key first,
    then :data:`MANA_KEYS` order — the canonical witness; the CR lets the
    payer choose freely)."""
    tap: list[Handle] = []
    sacrifice: list[Handle] = []
    discard: list[Handle] = []
    counters: list[tuple[Handle, str, int]] = []
    life = 0
    loyalty = 0
    remaining: dict[str, int] = dict(world.players[ctx.controller].mana_pool)
    spent: dict[str, int] = {}
    generic_need = 0
    hybrid_demands: list[tuple[tuple[str, str], int]] = []
    all_yours = False
    ex = ctx.executor
    if ex is not None:
        # The Orrery permission is a LIVE-LAYER query (independent of the
        # segment mirror — a direct pool write has no segments but the
        # permission still governs). The restriction shortfall is the
        # mirror's alone: with no tagged segments the adjusted pool IS the
        # frozen pool, byte-identical to the 12a/12b arithmetic.
        all_yours = ex.mana_permission(ctx.controller)
        if ex.mana_ledger.has(ctx.controller):
            shortfall = ex.mana_ledger.restricted_amounts(
                ctx.controller, _mana_use_ok(ex, ctx, mana_use)
            )
            for key, blocked in shortfall.items():
                left = remaining.get(key, 0) - blocked
                if left > 0:
                    remaining[key] = left
                else:
                    remaining.pop(key, None)

    for part in cost.parts:
        if isinstance(part, CostManaColor):
            need = resolve(part.amount, ctx)
            have = remaining.get(part.color, 0) - spent.get(part.color, 0)
            if have >= need:
                spent[part.color] = spent.get(part.color, 0) + need
            elif all_yours:
                # Orrery permission: the shortfall draws from any other
                # colour key, canonical MANA_KEYS order (own key already
                # exhausted above; negative `have` contributes nothing).
                short = need - max(have, 0)
                if have > 0:
                    spent[part.color] = spent.get(part.color, 0) + have
                for key in MANA_KEYS:
                    if short <= 0:
                        break
                    if key == part.color:
                        continue
                    avail = remaining.get(key, 0) - spent.get(key, 0)
                    if avail > 0:
                        take = min(avail, short)
                        spent[key] = spent.get(key, 0) + take
                        short -= take
                if short > 0:
                    return None, f"cost:mana:{part.color}:{need - have}<any"
            else:
                return None, f"cost:mana:{part.color}:{have}<{need}"
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
            # 13a: the loyalty ledger lives on the source's counters map
            # (``"LOYALTY"``), seeded from the printed CardIdentity.loyalty
            # at binding (binding.py). The source may be absent (a test
            # calling build_payment_plan against a raw ctx), so the printed
            # identity is the fallback.
            # 13b QUIRK FIX (13a's pinned asymmetry): a loyalty cost is
            # legal ONLY on a card with a loyalty identity — CR 606.1b
            # "A loyalty ability can't be activated unless the permanent
            # has loyalty" cuts BOTH signs, and the +1 side previously read
            # "always payable" on a non-planeswalker (a crafted [−2]/[+1]
            # cost on a plain creature now returns a reason for either
            # sign; counters-seeded loyalty counts as a loyalty identity —
            # a token that gained loyalty counters is the edge the CR
            # actually allows).
            src = world.cards.get(ctx.source)
            if (
                src is not None
                and "LOYALTY" not in src.counters
                and src.identity.loyalty is None
            ):
                return None, "cost:loyalty:not_planeswalker"
            delta = (
                part.delta if isinstance(part.delta, int) else resolve(part.delta, ctx)
            )
            have = _loyalty_of(world, ctx.source)
            if delta < 0 and have < -delta:
                return None, f"cost:loyalty:{have}<{-delta}"
            loyalty += delta
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
        loyalty=loyalty,
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
    if ability.timing is ActivationWindow.SORCERY and not (
        executor.layers.instant_window_granted(handle)
    ):
        # 13c (Teferi, Who Outcast Oversight's controller-rule static): a
        # live GRANT_ACTIVATION layer whose filter matches this permanent
        # relaxes the SORCERY block to instant speed — EVERY gate below and
        # above it (controller, loyalty clock, costs, conditions) stays.
        # The grant is not seat-scoped at THIS layer: layers are global
        # views, so an opponent's Teferi static is visible to their own
        # activations exactly as printed ("You may activate ..." is written
        # to the permanent's controller, and only the controller passes the
        # not-controller gate above).
        if world.active_player != seat:
            return "window:sorcery:not_own_turn"
        if not stack_empty:
            return "window:sorcery:stack_nonempty"
        # 13a: the skeleton's phase clock (Executor.phase) is the honest
        # sorcery-window gate — a sorcery-timed activation after the first
        # main phase (the END_TURN marker of a mid-turn END_TURN atom) is
        # out of window. ``phase is None`` / FIRST_MAIN = inside.
        if executor.phase not in (None, Phase.FIRST_MAIN.name):
            return "window:sorcery:phase"
    # CR 606.3 (13a): one loyalty ability per permanent per turn. The
    # executor's simplification: the clock is keyed on the permanent and
    # the turn number, with NO turn-ownership gate layered on top (the
    # corpus' loyalty cards are all "activate only as a sorcery", which the
    # timing gate above already covers; a non-sorcery loyalty window would
    # additionally need the active-seat check — untested debt, documented).
    if any(isinstance(p, CostLoyalty) for p in ability.cost.parts) and (
        executor.loyalty_clock.get(handle) == world.turn
    ):
        return "window:loyalty:once_per_turn"
    ctx = ctx_for(executor, source=handle, controller=seat)
    if ability.condition is not None:
        subject = condition_ctx_source if condition_ctx_source is not None else handle
        if not eval_filter(ability.condition, subject, ctx):
            return "condition:false"
    plan, reason = build_payment_plan(world, ctx, ability.cost)
    if plan is None:
        return reason
    return None


# ------------------------------------------------------- spell casting gate


def spell_record(executor: Executor, handle: Handle):
    """The compiled record for a card: the per-handle bridge when one was
    attached (battlefield lifecycle), else the oracle-id registry — a hand
    card is never ATTACHED (attachment is the battlefield lifecycle) yet
    the pool's registry knows its IR, and the oracle bridge is the same
    identity-checked mapping the binder itself uses (``records``). None
    when the pool never registered the card (a token with no compiled
    spec, a card from another set)."""
    binder = executor.binder
    record = binder.handle_record.get(handle)
    if record is not None:
        return record
    state = executor.world.cards.get(handle)
    if state is None:
        return None
    return binder.records.get(state.identity.oracle_id)


def spell_cost(record, additional: tuple[Cost, ...] = ()) -> Cost:
    """The spell's total printed cost: CardRecord.mana_cost (the frozen
    grammar keeps the printed cost on the record, NOT on SpellAbility)
    plus the "as an additional cost to cast" parts (T3 r2) — one Cost the
    plan fold can walk in canonical part order."""
    parts: list = []
    if record.mana_cost is not None:
        parts.extend(record.mana_cost.parts)
    for cost in additional:
        parts.extend(cost.parts)
    return Cost(parts=tuple(parts))


def _cost_has_x(cost: Cost) -> bool:
    for part in cost.parts:
        if isinstance(part, (CostManaColor, CostManaGeneric, CostManaHybrid)):
            amount = part.amount
            if isinstance(amount, QX):
                return True
            if isinstance(amount, QBin) and _qty_has_x(amount):
                return True
    return False


def _qty_has_x(quantity: Quantity) -> bool:
    if isinstance(quantity, QX):
        return True
    if isinstance(quantity, QBin):
        return _qty_has_x(quantity.left) or _qty_has_x(quantity.right)
    return False


# SpellAbility windows: the frozen grammar gives SpellAbility NO timing
# slot (its own docstring: "what casting the card does" — the timing is
# the CARD CLASS, SpellKind), so the window folds from the kind:
#   INSTANT     — any time its controller would have priority. The
#                 executor has no priority state (API boundary, 12c
#                 ruling): instants are ungated — INCLUDING on the
#                 opponent's turn, which the test suite pins as the
#                 documented permissive reading (an instant in hand is
#                 always an option; a future phase/priority ledger may
#                 narrow it, the cast() surface will not change).
#   everything else (SORCERY/CREATURE/ENCHANTMENT/PLANESWALKER/LAND) —
#                 the sorcery window: the caster's own turn, the first
#                 main phase (13a's phase clock; None = not-yet-stamped
#                 skeleton convention), and an EMPTY stack (v1: the
#                 executor's own LIFO frames — nothing else can be on it
#                 mid-op, but the parked-frame API keeps the gate real).
_SORCERY_WINDOW_KINDS = frozenset(
    {
        SpellKind.SORCERY,
        SpellKind.CREATURE,
        SpellKind.ENCHANTMENT,
        SpellKind.PLANESWALKER,
        SpellKind.LAND,
    }
)


def spell_window_reason(
    executor: Executor, seat: Handle, kind: SpellKind
) -> str | None:
    """Why a spell of ``kind`` cannot be cast by ``seat`` RIGHT NOW (None
    = the window holds). See the window table above."""
    if kind not in _SORCERY_WINDOW_KINDS:
        return None
    world = executor.world
    if world.active_player != seat:
        return "window:not_your_turn"
    if executor.phase not in (None, "FIRST_MAIN"):
        return "window:phase"
    if executor.stack.frames:
        return "window:stack_nonempty"
    return None


def spell_castable(
    executor: Executor,
    seat: Handle,
    handle: Handle,
    *,
    x: int | None = None,
) -> tuple[str | None, SpellAbility | None, object, PaymentPlan | None]:
    """The CAST legality fold — re-checkable from the API at any time
    (§8.3: same answer as the one ``legal_casts`` gave, until the world
    changes). Returns ``(reason, node, record, plan)``: exactly one of
    ``reason`` / (node+plan) is set.

    Gates, in CR order: the card sits in the caster's HAND (601.1 "cast
    it from where it is" — v1 hand-only; the effect-side cast_from bypass
    covers library/graveyard casts); its record carries a SpellAbility
    (lands and unregistered cards have none); the kind's window holds;
    then the 601.2f fold — printed cost + additional costs against the
    pool, with ``x`` bound for QX (a declared-too-big X shrinks the pool
    fold into an ordinary ``cost:mana`` SHORTAGE — an illegal-cast reason,
    never a raise: X is enumerated at 0-floor by ``legal_casts``) and the
    spell handle as the mana-USE subject (THIS_MANA restrictions read
    their filter over the spell being cast)."""
    world = executor.world
    if handle not in world.cards:
        return f"cast:unknown_card:{handle}", None, None, None
    if world.zone_of(handle) != world.players[seat].zone("hand"):
        return f"cast:not_in_hand:{handle}", None, None, None
    record = spell_record(executor, handle)
    if record is None:
        return f"cast:no_record:{handle}", None, None, None
    node = next((a for a in record.abilities if isinstance(a, SpellAbility)), None)
    if node is None:
        return f"cast:not_a_spell:{handle}", None, None, None
    window = spell_window_reason(executor, seat, node.kind)
    if window is not None:
        return window, None, None, None
    cost = spell_cost(record, node.additional_costs)
    if _cost_has_x(cost) and x is None:
        # The declaration is the caller's; X=0 is legal (CR 107.1) — the
        # SURFACE enumerates at 0, an explicit x reaches the fold.
        x = 0
    ctx = ctx_for(executor, source=handle, controller=seat, x_value=x)
    plan, reason = build_payment_plan(world, ctx, cost, mana_use=handle)
    if plan is None:
        return reason, None, None, None
    return None, node, record, plan


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


def _loyalty_death_check(
    executor: Executor,
    source: Handle,
    controller: Handle,
    loyalty_after: int | None = None,
) -> None:
    """CR 704.2 (13a): a planeswalker with 0 or less loyalty is put into its
    owner's graveyard. The frozen world has no state-based-action pass, so
    this is the one place the check is run — immediately after the loyalty
    payment, which is the only legal way loyalty reaches 0 in the executor.
    It fires the journalled ``DESTROY`` verb (dies triggers, graveyard) as
    the documented stand-in for the SBZA's graveyard replacement; destroy
    *replacement* effects (Rest in Peace) would see it as a destroy, a
    corner the frozen corpus has no golden for."""
    world = executor.world
    state = world.cards.get(source)
    if state is None or state.identity.loyalty is None:
        return  # not a planeswalker — nothing to check
    if world.zone_of(source).kind != ZONE_BATTLEFIELD:
        return
    have = _loyalty_of(world, source) if loyalty_after is None else loyalty_after
    if have > 0:
        return
    executor.apply_effect(
        _binding_atom(Verb.DESTROY, "target", [source]),
        source=source,
        controller=controller,
        bindings={"target": [source]},
    )


def pay_costs(
    executor: Executor,
    plan: PaymentPlan,
    *,
    source: Handle,
    controller: Handle,
    mana_use: Handle | None = None,
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
        if executor.mana_ledger.has(controller):
            # 13b: mirror the subtraction onto the segment side-ledger —
            # untagged first, then filter-matching tagged segments; a
            # restricted segment is NEVER touched unless the payment can
            # demonstrate its use (see ManaLedger.consume). The totals
            # subtraction above stays the frozen path; only the mirror
            # moves here, so a tag-free world pays exactly as in 12a/12b.
            ctx = ctx_for(executor, source=source, controller=controller)
            executor.mana_ledger.consume(
                controller, plan.mana, _mana_use_ok(executor, ctx, mana_use)
            )
    if plan.tap:
        executor.apply_effect(
            _binding_atom(Verb.TAP, "target", plan.tap),
            source=source,
            controller=controller,
            bindings={"target": list(plan.tap)},
        )
    if plan.sacrifice:
        executor.apply_effect(
            _binding_atom(Verb.SACRIFICE, "target", plan.sacrifice),
            source=source,
            controller=controller,
            bindings={"target": list(plan.sacrifice)},
        )
    if plan.discard:
        executor.apply_effect(
            _binding_atom(
                Verb.DISCARD, "cards", plan.discard, controller=ControllerRef.YOU
            ),
            source=source,
            controller=controller,
            bindings={"cards": list(plan.discard)},
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
        )
    if plan.loyalty:
        # 13a: the loyalty ledger steps through the same journalled counter
        # verbs (PUT/REMOVE with CounterKind.LOYALTY) so the +1/-0/-N rows
        # are the ones the golden event stream already knows, then the
        # zero-loyalty planeswalker death check (CR 704.2) fires its own
        # journalled DESTROY.
        loyalty_before = _loyalty_of(world, source)
        executor.apply_effect(
            _binding_atom(
                Verb.PUT_COUNTER if plan.loyalty > 0 else Verb.REMOVE_COUNTER,
                "target",
                [source],
                counter_kind=CounterKind.LOYALTY,
                count=QConst(abs(plan.loyalty)),
            ),
            source=source,
            controller=controller,
            bindings={"target": [source]},
        )
        _loyalty_death_check(
            executor,
            source,
            controller,
            loyalty_before + plan.loyalty,
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
        )


def activate(
    executor: Executor,
    handle: Handle,
    ability_idx: int,
    *,
    seat: Handle,
    targets: Sequence[Handle] = (),
    decisions: Sequence[str] = (),
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
        raise ValueError(
            "executor: illegal activation: ability:not_activated"
        )
    ctx = ctx_for(executor, source=handle, controller=seat)
    plan, plan_reason = build_payment_plan(executor.world, ctx, ability.cost)
    if plan is None:  # pragma: no cover - ability_playable just checked
        raise ValueError(f"executor: illegal activation: {plan_reason}")
    pay_costs(executor, plan, source=handle, controller=seat)
    if plan.loyalty:
        # CR 606.3 once-per-turn clock (13a), keyed on the permanent.
        executor.loyalty_clock[handle] = executor.world.turn
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
    )


# ------------------------------------------------------- 16b: attack legality
# The CR 508.1 declare-attackers surface. The COMBAT skeleton asks one
# binary question per CREATURE (v1 = no blocker-side decisions, doc /11
# §16c); this module is the honest candidate list the ask is built from —
# the policy is NEVER offered a DECLINE it cannot legally answer (C15),
# and the assembled set is whole-set-checked before anything taps.
_IS_CREATURE = FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature")

from MTG_bot.core.executor.events import (
    KIND_TURN_PHASE,
    KIND_ZONE_CHANGE,
)


def _controlled_since_turn_start(executor: Executor, creature: Handle) -> bool:
    """CR 302.6 (summoning sickness): has ``creature`` been under control
    continuously since the start of the current turn?

    The answer is a JOURNAL read, never a mirror-table: the turn's UPKEEP
    marker (the same anchor :meth:`EventJournal.turn_window` uses) opens
    the turn; a ZONE_CHANGE row ENTERING the battlefield after that marker
    — first arrival, a blink return, a graveyard replay — means the
    permanent is not yet ready. No rows after the marker = continuous
    presence since the turn began (setup creatures carry no rows at all
    and read ready, which is the correct pre-game-control reading). A
    control-change path would need its own marker row; the only one in
    the corpus is the unimplemented GAIN_CONTROL verb (16e)."""
    events = executor.journal.events
    start = -1
    for i in range(len(events) - 1, -1, -1):
        row = events[i]
        if row.kind == KIND_TURN_PHASE and row.data[0] == Phase.UPKEEP.name:
            start = i
            break
    for row in events[start + 1 :]:
        if (
            row.kind == KIND_ZONE_CHANGE
            and row.subject == creature
            and row.zone_move[1] == ZONE_BATTLEFIELD
        ):
            return False
    return True


def attack_blocked_reason(
    executor: Executor, seat: Handle, creature: Handle
) -> str | None:
    """Why ``creature`` may not attack for ``seat`` right now, or ``None``
    when the declaration is legal. Encoded restrictions (CR 508.1 pre-
    check): creature-ness (the LIVE type line — GRANT_TYPE overlay aware),
    controller, DEFENDER (CR 702.4a — no "can attack as though it didn't"
    carrier in the corpus), and summoning sickness (CR 302.6) unless the
    creature has HASTE (CR 702.10a). TAPPED creatures are legal attackers
    (tapping to declare is not a cost — CR 508.1c skips VIGILANCE creatures
    and re-taps nothing). Card-text "can't attack" restrictions (the
    PREVENT/DeclareAttackersEvent consumer) are 16c."""
    world = executor.world
    if world.zone_of(creature).kind != ZONE_BATTLEFIELD:
        return "not on the battlefield"
    if world.controller_of(creature) != seat:
        return "not controlled by the declaring player"
    ctx = executor._ctx(
        source=creature, controller=seat, bindings=None, decisions=()
    )
    if not eval_filter(_IS_CREATURE, creature, ctx):
        return "not a creature"
    if executor.layers.keyword_of(creature, Keyword.DEFENDER):
        return "defender (CR 702.4a)"
    if not executor.layers.keyword_of(creature, Keyword.HASTE) and not (
        _controlled_since_turn_start(executor, creature)
    ):
        return "summoning sickness (CR 302.6) without haste"
    return None


def legal_attackers(executor: Executor, seat: Handle) -> tuple[Handle, ...]:
    """The Handle-sorted candidate set the declare-attackers asks are
    enumerated from (ruling 5 canonical order)."""
    world = executor.world
    return tuple(
        card
        for card in sorted(world.cards)
        if world.controller_of(card) == seat
        and world.zone_of(card).kind == ZONE_BATTLEFIELD
        and attack_blocked_reason(executor, seat, card) is None
    )


def mandated_attackers(executor: Executor, seat: Handle) -> frozenset[Handle]:
    """Creatures ``seat`` controls that MUST attack this combat if able
    (CR 508.1 "attacks each combat if able"), from BOTH carrier shapes:
    the dispatched mandates ledger (MANDATE_ATTACK verb — Pursued Whale's
    hoisted token rule line) and the LIVE mandate layers (the static
    shape — Furor of the Bitten, the Pirate token), whose ``cards``
    selectors resolve in the layer anchor's coordinates exactly like a
    continuous-effect scope. A mandated creature that is ILLEGAL
    (defender, sickness) simply never reaches the set — "if able"."""
    world = executor.world
    mandated: set[Handle] = set()
    for handle in executor.mandates:
        if (
            handle in world.cards
            and world.zone_of(handle).kind == ZONE_BATTLEFIELD
            and world.controller_of(handle) == seat
        ):
            mandated.add(handle)
    for layer in executor.layers.live_mandate_layers():
        selector = layer.atoms[0].args.get("cards")
        assert isinstance(selector, Selector)  # role table: cards required
        ctx = executor._ctx(
            source=layer.source,
            controller=layer.controller,
            bindings=None,
            decisions=(),
        )
        for handle in enumerate_candidates(selector, ctx):
            if (
                handle in world.cards
                and world.zone_of(handle).kind == ZONE_BATTLEFIELD
                and world.controller_of(handle) == seat
            ):
                mandated.add(handle)
    return frozenset(mandated)
