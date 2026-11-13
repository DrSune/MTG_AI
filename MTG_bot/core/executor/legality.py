"""Activation legality + cost payment.

The state-side half of the ``ACTIVATE`` decision: is this activated ability
payable right now, and what exactly does paying it do to the world? The
question the model-facing Slate must answer for one candidate row of the
``ACTIVATE / ACTIVATE_MANA`` field schedule
(``docs/DESIGN_ACTION_SPACE.md`` §1.3 — ``ABILITY:PTR``,
``COST_TARGET:PTR*``, ``PAYMENT:PTR*``), and whose payment folds into the
move itself (CR 601.2g; §1.3 "Mana payment folds into the move that needs
it"). The module also holds the spell-casting gate (:func:`spell_castable`),
the free mana sources a payment may tap (:func:`plan_mana_taps`), and
attack and block legality.

Contract highlights:

* **Builder/executor identity** (DESIGN_ACTION_SPACE.md §8.3) —
  :func:`ability_playable` and the :class:`PaymentPlan` carry typed
  references to the SAME IR objects the executor consumes
  (:class:`ActivatedAbility`, :class:`Cost`, world :class:`Handle`\\ s). No
  DTOs, no prose in the data (role tags are type tags, never payloads); the
  optional ``reason`` return of the legality probes is a developer
  diagnostic, not model-facing data.
* **Canonical order** (DESIGN_ACTION_SPACE.md §5.5) — every handle tuple in
  a plan is Handle-sorted; the fold's choices (which land taps, which card
  discards) are the canonical first-``n``-sorted witness. The remaining
  payment freedom (which of five forests produced the ``{G}``) is the
  ``ARITH`` mana-array class of §3.3, not an enumerable option.
* **Cost vocabulary** is the closed grammar union in ``ability_tree`` —
  ``CostTap / CostManaColor / CostManaGeneric / CostManaHybrid / CostLife /
  CostSacrifice / CostDiscard / CostPutCounter / CostLoyalty``; there is no
  exile-as-cost node. :class:`CardState` has no loyalty field, so the
  ``CostLoyalty`` ledger rides on its ``counters`` map under
  ``CounterKind.LOYALTY.name`` (seeded from the printed
  :attr:`CardIdentity.loyalty` at binding, :mod:`executor.binding`) and
  steps through the journalled counter verbs.

Rules encoded, with citations:

* **CR 118.3** — "A player can't pay a cost unless they have the necessary
  resources to pay it fully … a permanent that's already tapped can't be
  tapped to pay a cost." That is the untapped check on :class:`CostTap`
  and the candidate-count floor on every selector-shaped cost.
* **CR 119.4** — a life payment ``N > 0`` is legal only if the payer's
  life total is ``>= N``; paying is losing that life, so reaching exactly
  0 by payment is LEGAL (the death is the state-based check afterwards, CR
  119.6/704). **CR 119.4b** — a 0-life payment is always legal.
* **Activation windows** (:class:`ActivationWindow`) — ``timing=SORCERY``
  means the seat's own turn, a main phase (:data:`MAIN_PHASES`) and an
  empty stack (``executor.stack``).
* **Summoning sickness (CR 302.6 / 602.5a)** — a creature's ability with
  ``{T}`` in its cost is refused unless the creature has been under its
  controller's control since their most recent turn began, or has haste
  (CR 702.10). The clock is the journal read
  :func:`_controlled_since_turn_start` that attack legality uses too.

:func:`pay_costs` executes a plan through the journalled verbs, so
costs fire the same ``TapState`` / ``ZONE_CHANGE`` / ``SACRIFICE`` events
as any other world mutation. Mana is the exception: no verb spends mana, so
the pool arithmetic is a direct deterministic subtraction with a
``("PAY_MANA", …)`` audit row appended to the executor's event log (which
the replay fingerprint folds in).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from functools import cache
from typing import TYPE_CHECKING

from MTG_bot.core.ability_tree import (
    QX,
    ActivatedAbility,
    ActivationWindow,
    Atom,
    AtomArgs,
    ControllerRef,
    Cost,
    CostDeltaIncreaseGeneric,
    CostDeltaIncreaseLife,
    CostDeltaReduceGeneric,
    CostDeltaReduceMana,
    CostDeltaWaiveMana,
    CostDiscard,
    CostLife,
    CostLoyalty,
    CostManaColor,
    CostManaGeneric,
    CostManaHybrid,
    CostModifier,
    CostPutCounter,
    CostSacrifice,
    CostTap,
    CounterKind,
    FAnd,
    FAtom,
    FAtomPred,
    Filter,
    Keyword,
    KeywordAbility,
    KickerAbility,
    Phase,
    QBin,
    QConst,
    Quantity,
    QUnbounded,
    Selector,
    SelectorMode,
    SpellAbility,
    SpellKind,
    StaticAbility,
    TargetingEvent,
    Verb,
    Zone,
    ZoneKind,
    is_loyalty_ability,
    is_mana_ability,
    own_nodes,
)
from MTG_bot.core.executor.decisions import site_digest
from MTG_bot.core.executor.quantity import Binding, ExecCtx, eval_filter, resolve
from MTG_bot.core.identity import Handle
from MTG_bot.core.state import (
    PLAYER_ZONES,
    ZONE_BATTLEFIELD,
    ZONE_LIBRARY,
    GameWorld,
)

if TYPE_CHECKING:  # pragma: no cover - import cycle guard only
    from MTG_bot.core.ability_tree import CardRecord
    from MTG_bot.core.executor import Executor
    from MTG_bot.core.executor.layers import LayerRecord

#: The steps of a turn (CR 500.1, 501-514), the values of ``Executor.phase``, in order. Where the
#: grammar's ``Phase`` (the trigger vocabulary) names a step, the step carries that name: UPKEEP,
#: FIRST_MAIN, COMBAT (the beginning of combat step) and END_TURN (the end step). A main phase
#: has no steps; it is its own entry. FIRST_STRIKE_DAMAGE is the first of two combat damage steps
#: (CR 510.4). TURN_ENDED is no step: the turn's last cleanup step is over and the next turn has
#: not begun.
UNTAP = "UNTAP"
UPKEEP = Phase.UPKEEP.name
DRAW = "DRAW"
FIRST_MAIN = Phase.FIRST_MAIN.name
BEGIN_COMBAT = Phase.COMBAT.name
DECLARE_ATTACKERS = "DECLARE_ATTACKERS"
DECLARE_BLOCKERS = "DECLARE_BLOCKERS"
FIRST_STRIKE_DAMAGE = "FIRST_STRIKE_DAMAGE"
COMBAT_DAMAGE = "COMBAT_DAMAGE"
END_OF_COMBAT = "END_OF_COMBAT"
SECOND_MAIN = "SECOND_MAIN"
END_STEP = Phase.END_TURN.name
CLEANUP = "CLEANUP"
TURN_ENDED = "TURN_ENDED"

#: CR 505.1: a turn has two main phases, the first (precombat) and the second (postcombat), with
#: the combat phase between them. Sorcery speed is "a main phase of your turn with an empty
#: stack" (CR 117.1a, 505.6a-b; per type 302.1, 305.1, 307.1; abilities 602.5d, 606.3), so every
#: sorcery-speed gate reads this one set. ``None`` is a world with no turn begun (bare test rigs),
#: read as inside.
MAIN_PHASES = frozenset({None, FIRST_MAIN, SECOND_MAIN})

# The mana-pool key convention written by ``_v_add_mana`` (verbs.py): pool
# keys are exactly W U B R G C. CostManaColor is payable only from its own
# key (CR 118.3a "removing the indicated mana").
MANA_KEYS = ("W", "U", "B", "R", "G", "C")
# Generic mana draws from any key, colourless first: colourless pays no
# coloured symbol (CR 106.1b), so a later coloured cost stays payable when it
# can be (CR 601.2h: the payer chooses which mana pays).
GENERIC_KEYS = ("C", "W", "U", "B", "R", "G")


# ------------------------------------------------------------- mana segments


@dataclass
class ManaSegment:
    """One ADD_MANA production in the :class:`ManaLedger`: a colour key, an
    amount, and the spend RESTRICTIONS carried as closed-grammar Filters
    (``tags`` — Vodalian Arcanist's "Spend this mana only to cast instant
    or sorcery spells" compiles to ``FOr(TYPE_EQ Instant, TYPE_EQ
    Sorcery)``). EMPTY tags = ordinary mana, paid exactly like the plain
    pool totals."""

    color: str
    amount: int
    tags: tuple[Filter, ...] = ()  # spend-restriction Filters


class ManaLedger:
    """The executor-side segment mirror of the per-player mana pool.

    WHY a mirror: ``PlayerState.mana_pool`` is a colour-keyed ``Dict[str,
    int]`` totals map — it CANNOT express "this {C} came from Vodalian
    Arcanist and may only buy instants". So segments ride ALONGSIDE the
    pool (executor state, folded into the replay fingerprint):

    * ``add`` is called wherever mana enters the pool (the ADD_MANA handler,
      :func:`tap_for_payment`), next to the pool totals write (tags decided
      by the source's live THIS_MANA policy);
    * :meth:`restricted_amounts` is the spend-validator's ONLY consult in
      :func:`build_payment_plan` — tagged segments whose filters do not
      match the payment's use (the spell being cast) are removed from the
      usable totals, so a plan can never BE built on forbidden mana;
    * :meth:`consume` settles the mirror after :func:`pay_costs` subtracts
      the pool totals, untagged-first (the CR lets the payer choose;
      determinism pins the witness).

    A pool written to directly (bare tests, non-ADD_MANA grants) is
    UNTRACKED = unrestricted: the segment list floors at empty and nothing
    crashes. All of the corpus' mana arrives through ADD_MANA."""

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
        tagged segments whose filters fail against the payment's use. An
        empty dict leaves the plan arithmetic on the plain pool totals."""
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
        available segments, never a crash."""
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
    references only, every handle tuple Handle-sorted.

    * ``mana``      — the ``PAYMENT:PTR``-array fold: (pool key, amount)
      pairs, sorted by key; ``tap``/``sacrifice``/``discard`` are the
      ``COST_TARGET:PTR*`` designations of the ACTIVATE schedule;
    * ``counters``  — (handle, CounterKind name, count) for CostPutCounter;
    * ``loyalty``   — the signed CostLoyalty delta;
    * ``life``      — the CostLife amount (CR 119.4-checked).
    """

    mana: tuple[tuple[str, int], ...] = ()
    tap: tuple[Handle, ...] = ()
    sacrifice: tuple[Handle, ...] = ()
    discard: tuple[Handle, ...] = ()
    counters: tuple[tuple[Handle, str, int], ...] = ()
    loyalty: int = 0
    life: int = 0
    # The FULL Handle-sorted candidate pool of every CostSacrifice segment,
    # with that segment's need: the decision space behind the ``sacrifice``
    # witness (its lowest Handles). The plan stays the canonical payable
    # WITNESS (a legality probe never asks); :func:`pay_costs` asks the
    # payer through the decision channel when a segment really offers a
    # choice (len(pool) > need) and keeps the forced witness pick when it
    # does not. Hand-built plans (tests) carry the default () and pay the
    # witness.
    sacrifice_options: tuple[tuple[tuple[Handle, ...], int], ...] = ()
    # The same choice for CostTap ("tap an untapped creature you control")
    # and CostDiscard ("discard a card"), recorded ONLY when
    # :func:`selectors._choose_lift_allowed` lets EVERY targeted segment of
    # that cost ask, judged at PLAN time: all-or-nothing per cost, so a cost
    # mixing an askable and a deferred segment pays its witness wholesale.
    # Deferred shapes and hand-built plans carry the default ().
    tap_options: tuple[tuple[tuple[Handle, ...], int], ...] = ()
    discard_options: tuple[tuple[tuple[Handle, ...], int], ...] = ()


# ---------------------------------------------------------------- contexts


def ctx_for(
    executor: Executor,
    source: Handle,
    controller: Handle,
    bindings: dict[str, Binding] | None = None,
    x_value: int | None = None,
) -> ExecCtx:
    """An :class:`ExecCtx` sharing the executor's world, ledger, seeded rng
    factory, token counters, registries and journal: the context for
    legality queries and payments. OWNER reads in it resolve to the
    source's zone controller (:func:`source_owner`). ``x_value`` carries
    the declared X (QX resolves; with ``None`` a QX read raises)."""
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
        # The query/payment context sees the registries too (a paid
        # tap-cost can trip a replacement).
        layers=executor.layers,
        replacements=executor.replacements,
        executor=executor,
        x_value=x_value,
        stream=executor.decisions,
        # The journal binds into the QUERY context as well, so history
        # predicates evaluate at every entry point. Purity holds: the journal
        # is state, the read is deterministic and fingerprinted.
        journal=executor.journal,
    )


def source_owner(world: GameWorld, ctx: ExecCtx) -> Handle:
    """The OWNER referent in an activation context: the zone controller of
    the source (the world tracks zone control only, matching
    ``selectors.zone_owner``'s OWNER handling)."""
    if ctx.source.namespace == "card" and ctx.source in world.cards:
        return world.controller_of(ctx.source)
    return ctx.controller


def _loyalty_of(world: GameWorld, handle: Handle) -> int:
    """The loyalty ledger value: the ``"LOYALTY"`` counter, falling
    back to the printed :attr:`CardIdentity.loyalty` only for a raw card
    whose ledger has not been seeded yet (a card built straight into a
    zone, before binding). 0 when the card has no loyalty at all (a non-
    planeswalker paying a loyalty cost is illegal, and
    :func:`build_payment_plan` flags it).

    The counter verb keeps a zeroed LOYALTY key (every other counter kind is
    deleted at 0), so a walker brought to 0 reads 0 here, never its printed
    loyalty. The key is dropped when the walker leaves the battlefield
    (CR 122.2).
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
    """Candidate enumeration for the QUERY surface: ``Zone(ANY)`` becomes
    every player zone in seat × :data:`PLAYER_ZONES` order, and an ``OWNER``
    controller ref becomes the activation owner's zone.

    ``Zone(STACK)`` answers each seat's ``ZONE_STACK`` slot
    (:func:`stack.stack_zone`) and then its abilities on the stack
    (:func:`stack.stack_abilities`). A card whose TARGET selector names the
    stack (M21 Unsubstantiate prints ``BATTLEFIELD + STACK``) must enumerate
    here, or :func:`legal_casts` would fold its cost and call it castable
    while :func:`spell_target_slots` raised on the very next question. The
    stack stays OUT of :data:`PLAYER_ZONES`, so ``Zone(ANY)`` never reaches
    it; only an explicit STACK zone does.

    The effect-time :func:`~MTG_bot.core.executor.selectors.enumerate_zone`
    serves everything else, so effect-time resolution and query-time
    enumeration share one zone-order convention."""
    world = ctx.world
    if zone.kind is ZoneKind.STACK:
        from MTG_bot.core.executor.selectors import players_for_ref
        from MTG_bot.core.executor.stack import stack_abilities, stack_zone

        seats = (
            [source_owner(world, ctx)]
            if zone.controller is ControllerRef.OWNER
            else players_for_ref(zone.controller, ctx)
        )
        return [
            handle
            for seat in seats
            for handle in (*stack_zone(world, seat).entries, *stack_abilities(ctx.executor, seat))
        ]
    from MTG_bot.core.executor.selectors import existing  # CR 702.26b

    owner = source_owner(world, ctx)
    if zone.controller is ControllerRef.OWNER:
        if zone.kind is ZoneKind.PLAYER:
            return [owner]
        return existing(ctx, list(world.players[owner].zone(_STATE_KIND[zone.kind]).entries))
    if zone.kind is ZoneKind.ANY:
        handles: list[Handle] = []
        for player in world.player_order:
            for kind in PLAYER_ZONES:
                handles.extend(world.players[player].zone(kind).entries)
        return existing(ctx, handles)
    # PLAYER refs, positions, TOP/BOTTOM: the effect-time enumeration.
    from MTG_bot.core.executor.selectors import enumerate_zone

    return enumerate_zone(ctx, zone)


from MTG_bot.core.executor.selectors import ZONE_KIND_TO_STATE as _STATE_KIND
from MTG_bot.core.executor.selectors import controller_matches
from MTG_bot.core.executor.selectors import controller_of as _effective_controller


def _hexproof_vetoes_target(candidate: Handle, ctx: ExecCtx) -> bool:
    """CR 702.11b: does ``candidate``'s live HEXPROOF forbid targeting from
    ``ctx``'s source? The keyword's quality rows are evaluated against the
    targeting source, the same single-oracle shape as protection
    (:func:`protected_from`).

    Direction (CR 702.11b): hexproof blocks only OPPONENT-controlled
    sources; any other seat is an opponent, and the controller always
    targets their own object freely. The candidate's controller is read
    through ``controller_of`` (GAIN_CONTROL overlay aware).

    Zone relevance (CR 702.11b "on a permanent"; CR 113.6): the keyword
    functions only on the battlefield. A creature spell is not a
    permanent, so an opponent's counterspell may target a hexproof spell
    (Sporeweb Weaver is countered by a blue Cancel; Carnage Tyrant prints
    "can't be countered" for this reason). The identity-seeded keyword
    names are zone-less, so this consumer guard is what keeps a hexproof
    card off the battlefield an ordinary target. A candidate the layers
    registry does not know (a player seat: 702.11 protects the hexproof
    OBJECT, never its controller) is never vetoed here.

    Filter rows evaluate against ``ctx.source`` through ``eval_filter``
    (COLOR_HAS reads the source card's own identity), so an opponent's
    blue spell trips a hexproof-from-blue permanent's COLOR_HAS-U row and
    a red Shock does not; a ``None`` row is plain hexproof."""
    layers = ctx.layers
    if layers is None:
        return False
    world = ctx.world
    if candidate not in world.cards:
        return False  # player seat / off-world handle: never hexproof here
    if world.zone_of(candidate).kind != ZONE_BATTLEFIELD:
        return False  # a permanent's keyword: dead anywhere else (CR 113.6)
    rows = layers.hexproof_of(candidate)
    if not rows:
        return False
    if _effective_controller(ctx, candidate) == ctx.controller:
        return False  # 702.11b: "an opponent controls", own target is free
    return any(row is None or eval_filter(row, ctx.source, ctx) for row in rows)


def _own_targeting_restrictions(ctx: ExecCtx) -> list[Filter]:
    """The targets the SOURCE's own static abilities forbid it to choose as
    it is cast. Enthralling Hold's "You can't choose an
    untapped creature as this spell's target as you cast it" compiles to
    ``StaticAbility(PREVENT_EFFECT(event=TargetingEvent(filter=untapped
    creature), condition=IS_ANY_TARGET))``, the condition naming the spell's
    own target choice (templates_b4 ``_build_enthralling_target_choice``).
    CR 113.6e: an object's ability that restricts how that object can be cast
    functions in the zones it can be cast from and on the stack, so it is read
    off the record while the source is anywhere but the battlefield, and only
    at the choice (resolution never re-checks it: "as you cast it")."""
    ex = ctx.executor
    source = ctx.source
    if ex is None or source.namespace != "card" or source not in ctx.world.cards:
        return []
    if ctx.world.zone_of(source).kind == ZONE_BATTLEFIELD:
        return []
    record = spell_record(ex, source)
    if record is None:
        return []
    out: list[Filter] = []
    for ability in record.abilities:
        if not isinstance(ability, StaticAbility):
            continue
        effect = ability.effect
        if not (isinstance(effect, Atom) and effect.verb is Verb.PREVENT_EFFECT):
            continue
        event = effect.args.get("event")
        condition = effect.args.get("condition")
        if (
            isinstance(event, TargetingEvent)
            and isinstance(condition, FAtom)
            and condition.pred is FAtomPred.IS_ANY_TARGET
        ):
            out.append(event.filter)
    return out


def protected_from(executor: Executor | None, holder: Handle, source: Handle | None) -> bool:
    """CR 702.16: does ``holder``, a permanent on the battlefield or a player,
    have protection from ``source``? The one oracle every protection consumer reads:
    targeting (702.16b), Auras and Equipment (702.16c-d), damage (702.16e) and
    blocking (702.16f).

    The quality is judged on the SOURCE object: a permanent, a spell, or a card in
    another zone (702.16a; 609.7c), through ``eval_filter``. It is judged in the
    coordinates of the ability that gives the protection (``protection_rows``), so a
    quality that reads its own source answers for that ability: Runed Halo's
    NAME_CHOSEN is the name the Halo chose. A universal quality (``FAnd(())``) is
    protection from everything (702.16j). Only a card can be a source with
    qualities here (an emblem or a player is not), and a card off the battlefield
    has no protection that functions (113.6)."""
    if executor is None or source is None or source.namespace != "card":
        return False
    world = executor.world
    if source not in world.cards:
        return False
    if holder.namespace == "card":
        if holder not in world.cards or world.zone_of(holder).kind != ZONE_BATTLEFIELD:
            return False
    elif holder.namespace != "player":
        return False
    for quality, granter, controller in executor.layers.protection_rows(holder):
        ctx = executor._ctx(source=granter, controller=controller, bindings=None, decisions=())
        if eval_filter(quality, source, ctx):
            return True
    return False


def _protection_vetoes_target(candidate: Handle, ctx: ExecCtx) -> bool:
    """CR 702.16b: "A permanent or player with protection can't be targeted
    by spells with the stated quality and can't be targeted by abilities from a
    source with the stated quality." ``ctx.source`` is the spell, or the source of
    the ability, doing the targeting."""
    return protected_from(ctx.executor, candidate, ctx.source)


def enumerate_candidates(sel: Selector, ctx: ExecCtx) -> list[Handle]:
    """The legal candidate set of one Selector IR node in ``ctx`` —
    Handle-sorted. This is the per-slot candidate list the query surface
    returns; whole-selection legality is
    :func:`query.validate_target_selection` (combinatorial explosion
    guard: candidates per slot, never a product of per-slot lists).

    A ``"target"`` referent reads the bound designation (none bound: no
    candidates); every other referent resolves through
    :func:`~MTG_bot.core.executor.selectors.resolve_selector` — the SAME
    resolver the executor runs at resolution time. A TARGET-mode selector
    with no designation yet is still enumerable here: the population is
    what the query asks for; the designation is what the Slate answers
    (CR 601.2, ``TARGET:PTR x n``). TARGET mode also drops what hexproof,
    protection or the source's own casting restriction forbids."""
    from MTG_bot.core.executor.selectors import resolve_selector

    if sel.referent is not None:
        if sel.referent == "target":
            bound = ctx.binding_handles("target")
            candidates = bound if bound is not None else []
        else:
            candidates = resolve_selector(sel, ctx)  # an unknown referent raises
    else:
        candidates = []
        for zone_spec in sel.zones:  # the zones field IS the legal-zone set
            candidates.extend(_zone_handles(ctx, zone_spec))
    handles = sorted(h for h in candidates if eval_filter(sel.filter, h, ctx))
    if sel.mode is SelectorMode.TARGET:
        # CR 702.11b: the ONE hexproof chokepoint. Every target surface
        # consumes this enumeration (legal_targets, spell_target_slots, the
        # 601.2c cast validator via validate_target_selection, the trigger
        # _designate ask menus, optional_offer actionability), so the query
        # and the runtime present the same legal menu. TARGET-only by mode:
        # ALL/CHOOSE/ONE_OF selections never TARGET, so sweepers are
        # untouched.
        handles = [h for h in handles if not _hexproof_vetoes_target(h, ctx)]
        # And the source's own "you can't choose ... as you cast it".
        for forbidden in _own_targeting_restrictions(ctx):
            handles = [h for h in handles if not eval_filter(forbidden, h, ctx)]
        # CR 702.16b: protection is another veto at the same chokepoint.
        handles = [h for h in handles if not _protection_vetoes_target(h, ctx)]
    return handles


def _required_count(sel: Selector, ctx: ExecCtx, available: int) -> int:
    """How many objects a cost's selector demands (costs pay in full —
    CR 118.3). QUnbounded in a cost position is the degenerate "any
    number"; the resource floor is one (paying zero is not paying).

    The exception is an ALL selector with no bound, "all of them" ("Discard
    your hand", Subira, Tulzidi Caravanner): it demands every one of the
    ``available`` candidates, and none when there are none. Discarding an empty
    hand pays that cost in full (CR 118.3; 701.9a), as paying 0 mana or 0 life
    does (118.3a/b)."""
    count = sel.count
    if isinstance(count, QUnbounded):
        return available if sel.mode is SelectorMode.ALL else 1
    return max(1, resolve(count, ctx))


# ---------------------------------------------------------------- payment


def _mana_use_ok(ctx: ExecCtx, mana_use: Handle | None):
    """The spend-validator's filter judge: does a restriction Filter
    accept this payment's use? The use subject is the SPELL being paid for
    (Vodalian Arcanist's compiled filter is a CastSpellEvent-shape
    ``TYPE_EQ`` reading over the spell card). No use context (an activation
    cost, a payment outside a cast) can demonstrate the filter's subject,
    so the judge is None and a tagged segment is NOT available ("Spend this
    mana only to cast instant or sorcery spells" cannot be demonstrated by
    an activation)."""
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
    activation: Handle | None = None,
) -> tuple[PaymentPlan | None, str | None]:
    """Fold one :class:`Cost` against the world into the canonical
    :class:`PaymentPlan`, or a machine-readable reason string.

    Returns ``(plan, None)`` when every part is payable and ``(None,
    reason)`` when a resource is short. A ``QX`` amount with no declared X
    raises ``NotImplementedError`` (``quantity.resolve``): the Slate's
    ``X_VALUE`` NUM field is a declaration the caller must supply.

    ``mana_use`` is the spell being paid for (the cast lane), ``activation``
    the source of the ability being activated (the activation lane); either
    one, when it is ``ctx.source``, turns on the cost-modifier fold below.
    Mana restrictions: the plan arithmetic runs on the RESTRICTION-ADJUSTED
    pool — an executor whose ManaLedger has tagged segments removes from the
    usable totals every tagged amount whose filter fails against
    ``mana_use`` (:func:`_mana_use_ok`). With no tagged segments the
    adjusted pool IS the pool. The OTHER policy axis, the ALL_YOURS
    permission (Chromatic Orrery's "spend mana as though it were mana of any
    color"), makes a coloured demand drawable from any colour key (own key
    first, then :data:`MANA_KEYS` order — the canonical witness; the CR lets
    the payer choose freely)."""
    tap: list[Handle] = []
    sacrifice: list[Handle] = []
    sacrifice_options: list[tuple[tuple[Handle, ...], int]] = []
    tap_options: list[tuple[tuple[Handle, ...], int]] = []
    discard_options: list[tuple[tuple[Handle, ...], int]] = []
    # All-or-nothing (see PaymentPlan.tap_options): one deferred targeted
    # segment keeps the WHOLE cost on its witness.
    tap_options_allowed = True
    discard_options_allowed = True
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
        # pool.
        all_yours = ex.mana_permission(ctx.controller)
        if ex.mana_ledger.has(ctx.controller):
            shortfall = ex.mana_ledger.restricted_amounts(
                ctx.controller, _mana_use_ok(ctx, mana_use)
            )
            for key, blocked in shortfall.items():
                left = remaining.get(key, 0) - blocked
                if left > 0:
                    remaining[key] = left
                else:
                    remaining.pop(key, None)

    # CR 601.2f: continuous :class:`CostModifier` nodes fold into the total
    # cost BEFORE the payment arithmetic — Discontinuity's your-turn {2}{U}
    # window, Sanguine Indulgence's gained-3 discount, Volcanic Salvo's
    # SUM(POWER) fold. ``judge`` (below) is the discounted object: the spell
    # being cast (``mana_use``) or the source of the ability being activated
    # (``activation``); a bare PAY atom passes neither and pays its printed
    # cost. Modifiers are read from the judge's OWN record (only "this spell
    # costs" for a permanent spell, CR 113.6; see the loop) plus every
    # battlefield permanent's record (both armies — Watcher of the Spheres
    # discounts through the permanent's controller, not the spell's owner),
    # each through :func:`spell_record`: a dealt card in hand has no
    # per-handle record until it is cast, played or put onto the
    # battlefield, so the oracle-id registry answers for it (else every
    # dealt Volcanic Salvo would cost {10}{R}{R}). Each modifier's filter,
    # payer scope and condition judge the CASTING SPELL in the MODIFIER
    # CARD's coordinates, exactly like a static trigger's filter reads the
    # world from its source's seat. Deltas sum additively, increases first
    # and reductions second (CR 601.2f's order), every component clamped at
    # zero — a discount never spills across colour or kind. Amounts
    # resolve in the modifier's coordinates, which is what Volcanic
    # Salvo's QProp (total power of ITS controller's creatures) requires.
    # ``CostDeltaWaiveMana`` is skipped by design, not by oversight: the
    # waiver is a PERMISSION the caster MAY take ("you may cast … without
    # paying its mana cost"), and paying the printed cost is always a
    # legal play the fold may conservatively plan.
    color_add: dict[str, int] = {}
    color_cut: dict[str, int] = {}
    generic_add = 0
    generic_cut = 0
    extra_life = 0
    # On the ACTIVATION lane only a modifier whose filter is exactly
    # ``FAtom(IS_SOURCE)`` folds ("activated abilities … cost less" describes
    # the host's OWN ability, Sanctum of Tranquil Light), so no cast-lane
    # reduction (Vryn/Watcher's blanket auras, Discontinuity's conditional
    # window, TARGETS_SOURCE/IS_ANY_TARGET spell filters) can leak into an
    # activation.
    judge = mana_use if mana_use is not None else activation
    if (
        ex is not None
        and judge is not None
        and judge == ctx.source
        and judge.namespace == "card"
    ):
        activation_lane = mana_use is None
        mod_hosts: list[Handle] = [judge]
        for seat in world.player_order:
            # CR 702.26b: a phased-out permanent's modifier does not exist.
            # On the activation lane the judge IS a battlefield permanent, so
            # it must not be scanned twice (Sanctum of Tranquil Light's "{1}
            # less for each Shrine" would cut {2} per Shrine). The cast lane's
            # judge is not on the battlefield.
            mod_hosts.extend(h for h in sorted(ex.battlefield(seat)) if h != judge)
        for host in mod_hosts:
            rec = spell_record(ex, host)
            if rec is None:
                continue
            mods = [n for n in rec.abilities if isinstance(n, CostModifier)]
            if not mods:
                continue
            if host == judge:
                mod_ctx = ctx  # the spell judges itself in its own seat
            else:
                mod_ctx = ex._ctx(
                    source=host,
                    # "your opponents" is relative to the host's controller
                    # (the control overlay), not its owner's zone.
                    controller=ex.controller_of(host),
                    bindings=dict(ctx.bindings),
                    decisions=(),
                    x_value=ctx.x_value,
                )
            # CR 113.6: a permanent spell's abilities do not function on the stack, so
            # the permanent being cast reads only its own "this spell costs" modifier
            # (IS_SOURCE, CR 601.2f); otherwise Warden of Evos Isle's "creature spells
            # with flying you cast cost {1} less" would discount its own cast. An
            # instant's or sorcery's abilities do function there.
            own_only = activation_lane or (
                host == judge and not {"Instant", "Sorcery"} & set(rec.types)
            )
            for mod in mods:
                if own_only and not (
                    isinstance(mod.filter, FAtom)
                    and mod.filter.pred is FAtomPred.IS_SOURCE
                ):
                    continue
                if not eval_filter(mod.filter, judge, mod_ctx):
                    continue
                if not controller_matches(mod.controller_ref, ctx.controller, mod_ctx):
                    continue
                if mod.condition is not None and not eval_filter(
                    mod.condition, judge, mod_ctx
                ):
                    continue
                for delta in (mod.delta, *mod.extra_deltas):
                    if isinstance(delta, CostDeltaReduceGeneric):
                        generic_cut += resolve(delta.amount, mod_ctx)
                    elif isinstance(delta, CostDeltaIncreaseGeneric):
                        generic_add += resolve(delta.amount, mod_ctx)
                    elif isinstance(delta, CostDeltaReduceMana):
                        color_cut[delta.color] = color_cut.get(
                            delta.color, 0
                        ) + resolve(delta.amount, mod_ctx)
                    elif isinstance(delta, CostDeltaIncreaseLife):
                        extra_life += resolve(delta.amount, mod_ctx)
                    elif isinstance(delta, CostDeltaWaiveMana):
                        continue
                    else:  # pragma: no cover - CostDelta is a closed union
                        raise NotImplementedError(
                            f"executor: cost delta {type(delta).__name__} "
                            "not implemented"
                        )

    for part in cost.parts:
        if isinstance(part, CostManaColor):
            # The folded symbol window applies before the colour
            # search — additive symbols first, the consumed share of the
            # discount is DEPLETED here (min-clamped), so a {U} discount
            # can never leak into a second symbol or another colour.
            need = resolve(part.amount, ctx) + color_add.get(part.color, 0)
            if color_cut.get(part.color, 0):
                take = min(color_cut[part.color], need)
                need -= take
                color_cut[part.color] -= take
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
                    # CR 118.3: an already-tapped permanent can't be tapped.
                    return None, "cost:tap:source_tapped"
                tap.append(ctx.source)
            else:
                # A tap cost acts on permanents YOU control (CR 701.20's tap
                # rule, mirroring the sacrifice lane's CR 701.14a clause): the
                # raw ANY-zone enumeration carries the opponent's permanents.
                # The clause is a property of the tap verb, not of the card,
                # so it is enforced HERE, lane-agnostic, before the pool is
                # recorded.
                cands = [
                    h
                    for h in enumerate_candidates(part.target, ctx)
                    if not world.cards[h].tapped
                    and world.controller_of(h) == ctx.controller
                ]
                need = _required_count(part.target, ctx, len(cands))
                if len(cands) < need:
                    return None, (
                        f"cost:tap:insufficient_candidates:{len(cands)}<{need}"
                    )
                from MTG_bot.core.executor.selectors import (
                    _choose_lift_allowed,
                )

                if not _choose_lift_allowed(part.target, ctx):
                    tap_options_allowed = False
                else:
                    tap_options.append((tuple(sorted(cands)), need))
                tap.extend(cands[:need])
        elif isinstance(part, CostSacrifice):
            # CR 701.14a: a sacrifice acts on a permanent YOU control. The
            # bridge compiles "sacrifice another creature" with a
            # controller=ANY battlefield zone (the filter only says Creature
            # AND NOT is-source), so the raw enumeration carries the
            # OPPONENT'S creatures, which the payer's ask must never offer.
            # The controller clause is a property of the sacrifice verb, not
            # of the card, so it is enforced HERE, lane-agnostic, before the
            # pool is recorded.
            cands = [
                h
                for h in enumerate_candidates(part.target, ctx)
                if world.controller_of(h) == ctx.controller
            ]
            need = _required_count(part.target, ctx, len(cands))
            if len(cands) < need:
                return None, (
                    f"cost:sacrifice:insufficient_candidates:{len(cands)}<{need}"
                )
            # The witness keeps the canonical cands[:need] pick (a probe
            # must never ask), but the FULL pool rides along on the plan —
            # pay_costs asks the payer through the decision channel when
            # this segment really offers a choice.
            sacrifice_options.append((tuple(cands), need))
            sacrifice.extend(cands[:need])
        elif isinstance(part, CostDiscard):
            cands = enumerate_candidates(part.target, ctx)
            # The cast fold runs the plan while the spell is STILL in hand
            # (stack.py pays, then parks), so the spell is a raw hand
            # candidate — the Handle-sorted cands[:need] would spend the
            # cast on itself (Thrill of Possibility, Sparkhunter Masticore).
            # CR 601.2h forbids an object paying its own cast cost; the
            # exclusion is lane-agnostic (every lane's ``source`` is the
            # object owning the cost — the same reading CostTap's no-target
            # "source itself" branch takes).
            # The exception (Waker of Waves): when the selector's filter
            # itself demands IS_SOURCE ("Discard this card:" activations,
            # cycling family), the source is the ONLY legal candidate —
            # excluding it would make a printed cost unsatisfiable. The
            # self-referential filter is the IR proof that this is the
            # printed self-cost, not a Thrill-shape "discard a card".
            from MTG_bot.core.executor.selectors import (
                _filter_is_self_referential,
            )

            if not _filter_is_self_referential(part.target.filter):
                cands = [h for h in cands if h != ctx.source]
            need = _required_count(part.target, ctx, len(cands))
            if len(cands) < need:
                return None, (
                    f"cost:discard:insufficient_candidates:{len(cands)}<{need}"
                )
            from MTG_bot.core.executor.selectors import _choose_lift_allowed

            if not _choose_lift_allowed(part.target, ctx):
                discard_options_allowed = False
            else:
                discard_options.append((tuple(sorted(cands)), need))
            discard.extend(cands[:need])
        elif isinstance(part, CostPutCounter):
            cands = enumerate_candidates(part.target, ctx)
            need = _required_count(part.target, ctx, len(cands))
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
            # The loyalty ledger lives on the source's counters map
            # (``"LOYALTY"``), seeded from the printed CardIdentity.loyalty
            # at binding (binding.py); :func:`_loyalty_of` reads the printed
            # value for an unseeded card. A source absent from the world (a
            # test calling build_payment_plan against a raw ctx) skips the
            # identity check below and reads loyalty 0.
            # A loyalty cost is legal ONLY on a card with a loyalty identity
            # — CR 606.1b "A loyalty ability can't be activated unless the
            # permanent has loyalty" cuts BOTH signs (a crafted [−2] or [+1]
            # cost on a plain creature returns a reason). Counters-seeded
            # loyalty counts as a loyalty identity: a token that gained
            # loyalty counters is the edge the CR allows.
            src = world.cards.get(ctx.source)
            if (
                src is not None
                and "LOYALTY" not in src.counters
                and src.identity.loyalty is None
            ):
                return None, "cost:loyalty:not_planeswalker"
            # A Quantity delta is Ugin's [−X]: always a REDUCTION of the
            # resolved amount (CostLoyalty's own contract; CR 606.4 removes
            # X counters). X is the activation's announced value (CR 602.2b
            # -> 601.2b, 107.3a), bound on ``ctx.x_value`` by the X lane.
            delta = (
                part.delta if isinstance(part.delta, int) else -resolve(part.delta, ctx)
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
    # The folded window lands on the generic symbol after the loop
    # (additions first, reductions second, CR 601.2f) — clamped at zero,
    # so an over-reduction is WASTED, never a credit or a colour spill.
    if generic_add or generic_cut:
        generic_need = max(0, generic_need + generic_add - generic_cut)
    if extra_life:
        # CR 118.1b: added life is part of the total cost the payer must
        # afford; re-run the CR 119.4 solvency test on the COMBINED bill
        # (the in-loop CostLife branch only saw the printed part).
        life += extra_life
        if world.players[ctx.controller].life < life:
            return None, f"cost:life:{world.players[ctx.controller].life}<{life}"
    # Generic mana draws from any remaining key, colourless first.
    if generic_need:
        pool_left = sum(remaining.get(k, 0) - spent.get(k, 0) for k in MANA_KEYS)
        if pool_left < generic_need:
            return None, f"cost:mana_generic:{pool_left}<{generic_need}"
        for key in GENERIC_KEYS:
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
        sacrifice_options=tuple(sacrifice_options),
        tap_options=(tuple(tap_options) if tap_options and tap_options_allowed else ()),
        discard_options=(
            tuple(discard_options)
            if discard_options and discard_options_allowed
            else ()
        ),
    )
    return plan, None


# ------------------------------------------------------------- legality


@cache  # a function of the frozen tree; every priority's menu and payment asks it
def activation_zone(ability: ActivatedAbility) -> str:
    """The zone an activated ability works in (CR 113.6), as a world zone kind: the
    battlefield, like every ability of a permanent, unless its cost or effect moves the object
    it's on out of a particular zone; then it works only in that zone (113.6m), the first such
    part deciding (the cost is paid first). Sanitarium Skeleton's "{2}{B}: Return this card from
    your graveyard to your hand" works from the graveyard and does nothing on the battlefield;
    Waker of Waves' "Discard this card:" works from the hand, a cost that can't be paid on the
    battlefield (113.6j). The tree says it: a discard or sacrifice cost, or a MOVE_ZONE, of the
    source itself (a selector naming IS_SOURCE, not "another"), out of zones of one kind (a
    discard from "hand or graveyard" names no zone, so it leaves the default)."""
    from MTG_bot.core.executor.selectors import (
        ZONE_KIND_TO_STATE,
        _filter_names_the_source,
    )

    def departure(sel: object) -> str | None:
        if not isinstance(sel, Selector) or sel.referent is not None:
            return None
        kinds = {zone.kind for zone in sel.zones}
        if len(kinds) != 1 or not _filter_names_the_source(sel.filter):
            return None
        return ZONE_KIND_TO_STATE.get(kinds.pop())

    for part in ability.cost.parts:
        if isinstance(part, (CostDiscard, CostSacrifice)):
            zone = departure(part.target)
            if zone is not None:
                return zone
    for node in own_nodes(ability.effect):  # a granted or delayed ability is another's
        if not (isinstance(node, Atom) and node.verb is Verb.MOVE_ZONE):
            continue
        dest = node.args.get("destination")
        for role in ("cards", "target"):
            zone = departure(node.args.get(role))
            if zone is not None and not (
                isinstance(dest, Zone) and ZONE_KIND_TO_STATE.get(dest.kind) == zone
            ):
                return zone
    return ZONE_BATTLEFIELD


def off_battlefield_activations(
    executor: Executor, seat: Handle
) -> list[tuple[Handle, int, ActivatedAbility]]:
    """The printed activated abilities of ``seat``'s cards off the battlefield that work where
    the card is (:func:`activation_zone`): "Discard this card:" in the hand, Sanitarium
    Skeleton's return in the graveyard. Such a card has no controller, so its owner activates
    it (CR 602.2). Nothing in a library, a hidden zone, is activated."""
    world = executor.world
    rows: list[tuple[Handle, int, ActivatedAbility]] = []
    for kind in PLAYER_ZONES:
        if kind in (ZONE_BATTLEFIELD, ZONE_LIBRARY):
            continue
        for handle in world.players[seat].zone(kind).entries:
            record = spell_record(executor, handle)
            if record is None:
                continue
            rows += [
                (handle, idx, ability)
                for idx, ability in enumerate(record.abilities)
                if isinstance(ability, ActivatedAbility) and activation_zone(ability) == kind
            ]
    return rows


def ability_playable(
    world: GameWorld,
    executor: Executor,
    handle: Handle,
    ability_idx: int,
    *,
    seat: Handle,
) -> str | None:
    """Is ``handle``'s ``ability_idx``-th compiled ability activatable by
    ``seat`` right now? ``None`` when legal, else a machine-readable reason
    string (a developer diagnostic — model-facing data is plan-shaped).

    Gates, in order:

    1. **window** — a printed ability's record must exist
       (:func:`spell_record`) and the node must be an
       :class:`ActivatedAbility`; the source must be in the zone the ability
       works in (:func:`activation_zone`), not phased out, and controlled by
       ``seat`` (its owner, off the battlefield: CR 602.2); the activation lock (CR 602.5: a live
       PREVENT_EFFECT over an AbilityActivatedEvent that covers this
       ability's kind and object) answers ``prohibited:activation_lock``. A
       loyalty ability and a ``timing=SORCERY`` one need the seat's own
       turn, a main phase and an empty stack unless a GRANT_ACTIVATION layer
       gives the permanent
       instant speed; a loyalty ability also runs once per permanent per
       turn.
    2. **summoning sickness** — CR 302.6 for a creature's ``{T}`` ability.
    3. **condition** — ``ActivatedAbility.condition`` (a state predicate
       over the source, the StaticAbility convention) judged against the
       source handle; an unsupported pred raises (flag, never guess).
    4. **cost** — :func:`build_payment_plan` (CR 118.3 resource
       arithmetic + the untapped check + CR 119.4 life floor), an X cost
       folded at X = 0.

    GRANTED abilities are addressed by NEGATIVE index: row ``-k-1``
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
        # spell_record first tries the battlefield bridge, then the
        # oracle-id registry — a hand card is never ATTACHED (attachment is
        # the battlefield lifecycle) but its compiled IR is the same record
        # (Waker of Waves activates from hand), the same lookup
        # spell_castable uses for hand casting.
        record = spell_record(executor, handle)
        if record is None:
            return f"bridge:no_record:{handle}"
        if not 0 <= ability_idx < len(record.abilities):
            raise ValueError(
                f"ability_playable: {handle} has no ability idx {ability_idx}"
            )
        ability = record.abilities[ability_idx]
    if not isinstance(ability, ActivatedAbility):
        return f"ability:not_activated:{type(ability).__name__}"
    # CR 113.6: an ability works in one zone (activation_zone), the battlefield unless its
    # cost or effect moves its object out of another; anywhere else it does not exist to be
    # activated (Sanitarium Skeleton's return on the battlefield, a {T} ability in the hand).
    zone = activation_zone(ability)
    if handle in world.cards and world.zone_of(handle).kind != zone:
        return f"window:not_in_{zone}:{handle}"
    if handle in executor.phased_out:
        # CR 702.26b: treated as though it does not exist (mana abilities too).
        return f"window:phased_out:{handle}"
    if handle in world.cards and executor.controller_of(handle) != seat:
        # CR 602.3: only the permanent's controller can activate it.
        return f"window:not_controller:{seat}"
    if executor.replacements.prevents_activation(handle, seat, ability):
        # CR 602.5: a player can't begin to activate an ability that's
        # prohibited from being activated (Faith's Fetters' NON_MANA lock).
        # The gate sits here, before anything is announced or paid, so every
        # caller that asks ability_playable inherits it: legal_activations,
        # activate(), and the payment witness that taps mana sources.
        return "prohibited:activation_lock"
    loyalty_ability = is_loyalty_ability(ability)
    if (
        loyalty_ability
        and not executor.layers.instant_window_granted(handle)
    ):
        # CR 606.3: a loyalty ability is activated only by its permanent's
        # controller, with priority and an empty stack, during a main phase
        # of their own turn. The compiler gives loyalty abilities no
        # ``timing`` (CR 606.3 is a rule of the ability type, not printed
        # text), so the window lives here. Teferi, Master of Time's
        # GRANT_ACTIVATION relaxes it to "any time you could cast an instant"
        # for itself, and the once-per-turn clock below still holds. A world
        # with no turn begun has no active player (bare test rigs): like
        # ``phase is None``, it reads as inside.
        if world.active_player is not None and world.active_player != seat:
            return "window:loyalty:not_own_turn"
        if executor.stack.frames:
            return "window:loyalty:stack_nonempty"
        if executor.phase not in MAIN_PHASES:
            return "window:loyalty:not_main_phase"
    if ability.timing is ActivationWindow.SORCERY and not (
        executor.layers.instant_window_granted(handle)
    ):
        # A live GRANT_ACTIVATION layer whose filter matches this permanent
        # (a controller-rule static, "You may activate ...") relaxes the
        # SORCERY block to instant speed — EVERY gate below and above it
        # (controller, loyalty clock, costs, conditions) stays. The grant is
        # not seat-scoped at THIS layer: layers are global views, and "You
        # may activate ..." is written to the permanent's controller, the
        # only seat that passes the not-controller gate above.
        if world.active_player != seat:
            return "window:sorcery:not_own_turn"
        if executor.stack.frames:
            return "window:sorcery:stack_nonempty"
        # The skeleton's phase clock (Executor.phase) is the sorcery-window
        # gate: "activate only as a sorcery" holds in either main phase
        # (CR 602.5d, 505.1), never in combat or once a mid-turn END_TURN
        # atom has stamped the ending phase.
        if executor.phase not in MAIN_PHASES:
            return "window:sorcery:phase"
    # CR 606.3: one loyalty ability per permanent per turn, keyed on
    # the permanent and the turn number. It holds inside Teferi, Master of
    # Time's widened window too (the static changes when, never how often);
    # the loyalty window itself is the gate above.
    if loyalty_ability and executor.loyalty_clock.get(handle) == world.turn:
        return "window:loyalty:once_per_turn"
    # The X lane (CR 602.2b -> 601.2b): an activation whose cost carries X is
    # legal iff some announcement is payable; X = 0 is the cheapest one (the
    # witness ``legal_casts`` uses for X spells), so the cost folds at X = 0.
    x_max = activation_x_max(world, handle, ability.cost)
    ctx = ctx_for(
        executor, source=handle, controller=seat, x_value=0 if x_max is not None else None
    )
    # CR 302.6 / 602.5a: a creature's activated ability with {T} in its cost
    # (CostTap with no target: "tap this permanent") can't be activated unless
    # the creature has been under its controller's control continuously since
    # their most recent turn began; haste exempts it (CR 702.10). Mana
    # abilities are activated abilities too (CR 605.3). Tapping OTHER
    # permanents as a cost ("Tap an untapped creature you control") is not the
    # {T} symbol and is not restricted. The IR has no {Q} (untap symbol) cost.
    if (
        handle in world.cards
        and any(isinstance(p, CostTap) and p.target is None for p in ability.cost.parts)
        and eval_filter(_IS_CREATURE, handle, ctx)
        and not executor.layers.keyword_of(handle, Keyword.HASTE)
        and not _controlled_since_turn_start(executor, handle, seat)
    ):
        return "summoning sickness (CR 302.6) without haste"
    if ability.condition is not None:
        if not eval_filter(ability.condition, handle, ctx):
            return "condition:false"
    return build_payment_plan(world, ctx, ability.cost, activation=handle)[1]


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


def kicker_of(record):
    """CR 702.27a: the card's KickerAbility node, or None. The cast lane,
    ``legal_casts``' kicked row and the engine-supported gate all ask the
    same question through this one accessor (one encoding per concept)."""
    return next((a for a in record.abilities if isinstance(a, KickerAbility)), None)


def spell_cost(record, additional: tuple[Cost, ...] = ()) -> Cost:
    """The spell's total printed cost: CardRecord.mana_cost (the frozen
    grammar keeps the printed cost on the record, NOT on SpellAbility)
    plus the "as an additional cost to cast" parts — one Cost the
    plan fold can walk in canonical part order."""
    parts: list = []
    if record.mana_cost is not None:
        parts.extend(record.mana_cost.parts)
    for cost in additional:
        parts.extend(cost.parts)
    return Cost(parts=tuple(parts))


def effect_cast_cost(record, node: SpellAbility, cost_override: Cost | None) -> Cost | None:
    """CR 601.2f, 118.9d: the total cost of a spell an effect casts
    (stack.cast_card, and the offer oracle query._cast_option_payable, so the two
    can never disagree). The CAST atom's ``cost`` role means (``verbs._v_cast``):
    - absent: the spell's mana cost;
    - an EMPTY Cost: "without paying its mana cost", an alternative cost (118.9);
    - a Cost WITH parts: additional costs paid on top of the mana cost ("by
      paying 3 life and discarding a card in addition to paying its other costs",
      Demonic Embrace). It never replaces the mana cost.
    Every additional cost the spell itself lists is added in all three cases
    ("As an additional cost to cast this spell, discard a card"): 118.9d applies
    additional costs to an alternative cost too. None or an empty Cost means
    nothing to pay."""
    if cost_override is not None and not cost_override.parts:
        base: Cost | None = cost_override  # the alternative cost: no mana cost
    else:
        base = record.mana_cost
    extras: list[Cost] = list(node.additional_costs)
    if cost_override is not None and cost_override.parts:
        extras.insert(0, cost_override)  # additional costs, CR 601.2f
    if not extras:
        return base
    parts: list = list(base.parts) if base is not None else []
    for extra in extras:
        parts.extend(extra.parts)
    return Cost(parts=tuple(parts))


def _cost_has_x(cost: Cost) -> bool:
    return any(
        isinstance(part, (CostManaColor, CostManaGeneric, CostManaHybrid))
        and _qty_has_x(part.amount)
        for part in cost.parts
    )


def _qty_has_x(quantity: Quantity) -> bool:
    if isinstance(quantity, QX):
        return True
    if isinstance(quantity, QBin):
        return _qty_has_x(quantity.left) or _qty_has_x(quantity.right)
    return False


def activation_x_max(world: GameWorld, source: Handle, cost: Cost) -> int | None:
    """The live bound of an activation's X announcement, or ``None`` when the
    activation cost has no X.

    CR 602.2b applies 601.2b to activations: the controller announces X as
    the ability is activated (107.3a), and while the ability is on the stack
    every X in it equals that value. The one carrier is a loyalty [−X]
    (Ugin, the Spirit Dragon): CR 606.6 refuses a negative loyalty cost
    larger than the permanent's loyalty counters, so X ranges over 0..loyalty
    (X = 0 is a legal announcement: the ability removes no counters and is
    still a loyalty ability, CR 606.3). An {X} mana activation cost has no
    carrier in the pools and no lane here, so it is flagged, never guessed."""
    loyalty_x = False
    for part in cost.parts:
        if isinstance(part, CostLoyalty) and not isinstance(part.delta, int):
            if not isinstance(part.delta, QX):
                raise NotImplementedError(
                    f"executor: loyalty cost delta {part.delta!r} is not a bare X "
                    "(no announcement lane for it)"
                )
            loyalty_x = True
    if _cost_has_x(cost):
        raise NotImplementedError(
            "executor: an {X} mana activation cost has no X lane (only a loyalty [−X])"
        )
    if not loyalty_x:
        return None
    return max(0, _loyalty_of(world, source))


def ask_activation_x(
    executor: Executor,
    source: Handle,
    seat: Handle,
    x_max: int,
    decisions: Sequence[str] = (),
) -> tuple[int, tuple[str, ...]]:
    """Announce X for an activation (CR 602.2b -> 601.2b). The menu is the
    live bounded range ``0..x_max`` (AGENTS §9/§10: every offered value is
    payable, and the bound is the menu itself). With one legal value there
    is no decision, so nothing is asked (AGENTS §10: no single-candidate phantom).
    The activation's explicit ``decisions`` pool answers first (ask order:
    X, then the effect's own asks); the rest of the pool is returned for
    the effect."""
    if x_max <= 0:
        return 0, tuple(decisions)
    vocab = tuple(str(n) for n in range(x_max + 1))
    ctx = executor._ctx(
        source=source, controller=seat, bindings=None, decisions=decisions
    )
    answer = ctx.take_decision(vocab, f"x:{seat}:{source}:{site_digest(vocab)}")
    return int(answer), tuple(decisions[ctx.decision_idx :])


# SpellAbility windows: the grammar gives SpellAbility NO timing slot (its
# own docstring: "what casting the card does" — the timing is the CARD
# CLASS, SpellKind), so the window folds from the kind:
#   INSTANT     — any time its controller would have priority. The window
#                 asks no priority question: instants are ungated —
#                 INCLUDING on the opponent's turn, the permissive reading
#                 ``test_window_table`` pins (an instant in hand is always
#                 an option).
#   every other kind — the sorcery window: the caster's own turn, either
#                 main phase (CR 505.1, :data:`MAIN_PHASES`), and an EMPTY
#                 stack (``executor.stack.frames``).
_SORCERY_WINDOW_KINDS = frozenset(
    {
        SpellKind.SORCERY,
        SpellKind.CREATURE,
        SpellKind.ENCHANTMENT,
        SpellKind.PLANESWALKER,
        SpellKind.LAND,
        SpellKind.ARTIFACT,
    }
)


def spell_window_reason(
    executor: Executor, seat: Handle, kind: SpellKind, *, flash: bool = False
) -> str | None:
    """Why a spell of ``kind`` cannot be cast by ``seat`` RIGHT NOW (None
    = the window holds). See the window table above.

    CR 702.9a (Masked Blackguard): ``flash`` — the card CARRIES the
    FLASH keyword (the cast lane's own record answers; a granted-from-
    battlefield FLASH would not describe a card sitting in hand) — is an
    ADDITIVE window bypass: it lifts ONLY the sorcery-window restrictions
    (not_your_turn / phase / empty-stack), never the OTHER gates (hand,
    mana and targets stay fully re-checked in spell_castable). An
    instant-timing spell already passes the table, so the flag only ever
    widens the other kinds' carriers, exactly as printed."""
    if kind not in _SORCERY_WINDOW_KINDS:
        return None
    if flash:
        # FLASH says "cast any time you could cast an INSTANT" — the
        # carrier joins the instant row of the table wholesale (every gate
        # below is a sorcery-window gate, and an instant answers none of
        # them).
        return None
    world = executor.world
    if world.active_player != seat:
        return "window:not_your_turn"
    if executor.phase not in MAIN_PHASES:
        return "window:phase"
    if executor.stack.frames:
        return "window:stack_nonempty"
    return None


def card_window_reason(
    executor: Executor, seat: Handle, record: CardRecord, node: SpellAbility
) -> str | None:
    """:func:`spell_window_reason` for one card: its spell's kind, with the card's own FLASH.

    CR 702.9a: the cast lane's own record answers FLASH — the compiled
    card carries KeywordAbility(FLASH) in its KEYWORDS tuple (Masked
    Blackguard); its abilities tuple is scanned too. Keyword grants from
    the battlefield describe permanents, not a card waiting in hand, so the
    record is the honest source for a cast."""
    flash = any(
        isinstance(k, KeywordAbility) and k.keyword is Keyword.FLASH
        for k in record.keywords
    ) or any(
        isinstance(a, KeywordAbility) and a.keyword is Keyword.FLASH
        for a in record.abilities
    )
    return spell_window_reason(executor, seat, node.kind, flash=flash)


def spell_castable(
    executor: Executor,
    seat: Handle,
    handle: Handle,
    *,
    x: int | None = None,
    kicked: bool = False,
    targets: tuple[Handle, ...] = (),
) -> tuple[str | None, SpellAbility | None, object, PaymentPlan | None]:
    """The CAST legality fold — re-checkable from the API at any time
    (same answer as the one ``legal_casts`` gave, until the world
    changes). Returns ``(reason, node, record, plan)``: exactly one of
    ``reason`` / (node+plan) is set.

    Gates, in CR order: the card sits in the caster's HAND (601.1 "cast
    it from where it is" — hand only; an effect's cast from another zone
    runs through ``stack.cast_card``); its record carries a SpellAbility
    (lands and unregistered cards have none); the kind's window holds;
    then the 601.2f fold — printed cost + additional costs (+ the kicker
    cost when ``kicked``) against the pool, with ``x`` bound for QX (a
    declared-too-big X shrinks the pool fold into an ordinary
    ``cost:mana`` SHORTAGE — an illegal-cast reason, never a raise: X is
    enumerated at 0-floor by ``legal_casts``) and the spell handle as the
    mana-USE subject (THIS_MANA restrictions read their filter over the
    spell being cast); last, an Aura needs something it could enchant.

    ``targets`` binds the declared targets into the fold, so a
    target-dependent cost increase ("Spells your opponents cast that target this
    creature cost {3} more", Pursued Whale; "... an additional 3 life", Terror of
    the Peaks) is part of the total. CR 601.2f determines the total cost after
    601.2c's targets; ``stack.cast`` re-folds with them before paying."""
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
    window = card_window_reason(executor, seat, record, node)
    if window is not None:
        return window, None, None, None
    additional = node.additional_costs
    if kicked:
        # CR 601.2b: the kick choice is MADE with the total cost — the
        # kicker cost joins the 601.2f fold, so the plan (and every later
        # re-check) prices the spell WITH the extra cost. A card without a
        # kicker cannot be kicked (reason, never a silent downgrade to the
        # base cost).
        # A kicker cost containing {X} rides the SAME fold — the cast's
        # ``x`` IS the kicker's announcement. Thieving Skydiver ("Kicker
        # {X}. X can't be 0."): the spell's printed cost {1}{U} carries no
        # X, so the kicker's {X} is the spell's ONLY X — CR 107.4a gives one
        # declared value per object, consumed by the cost AND the
        # (uncompiled) ETB filter alike, so ONE announcement serves both.
        # An X=0 kick pays zero and IS a legal kick (CR 107.1, x=0 folds
        # below): the printed "X can't be 0." is UNPARSED — the grammar has
        # no X-bound atom, and the engine never enforces a constraint it
        # cannot see through a side channel.
        kicker = kicker_of(record)
        if kicker is None:
            return f"cast:not_a_kicker:{handle}", None, None, None
        additional = tuple(additional) + (kicker.cost,)
    cost = spell_cost(record, additional)
    if _cost_has_x(cost) and x is None:
        # The declaration is the caller's; X=0 is legal (CR 107.1) — the
        # SURFACE enumerates at 0, an explicit x reaches the fold.
        x = 0
    ctx = ctx_for(
        executor,
        source=handle,
        controller=seat,
        bindings={"target": list(targets)} if targets else None,
        x_value=x,
    )
    plan, reason = build_payment_plan(world, ctx, cost, mana_use=handle)
    if plan is None:
        return reason, None, None, None
    from MTG_bot.core.executor.query import aura_enchant_slot

    aura_slot = aura_enchant_slot(executor, node, spell_handle=handle, seat=seat)
    if aura_slot is not None and not aura_slot.candidates:
        # CR 601.2e: an aura with nothing it could enchant is
        # UNCASTABLE — the synthesized ENCHANT slot's population is
        # the oracle, and an empty one disappears the legal_casts row
        # instead of letting a floating aura resolve into a no-op.
        return f"cast:aura_no_legal_target:{handle}", None, None, None
    return None, node, record, plan


# -------------------------------------------------------------- payment


def _binding_atom(verb: Verb, role: str, handles: Sequence[Handle], **extra) -> Atom:
    """An Atom whose ``role`` carries a placeholder Selector while the real
    designation rides in via bindings (role_handles checks bindings first),
    so the payment runs through the journalled verb dispatch unchanged."""
    pairs = dict(extra)
    pairs[role] = Selector(
        QConst(max(1, len(handles))),
        SelectorMode.TARGET,
        FAnd(()),
        zones=(Zone(ZoneKind.ANY, ControllerRef.ANY),),
    )
    return Atom(verb=verb, args=AtomArgs(pairs=tuple(pairs.items())))


def _ask_cost_choices(
    executor: Executor,
    options: tuple[tuple[tuple[Handle, ...], int], ...],
    lane: str,
    *,
    source: Handle,
    controller: Handle,
) -> tuple[Handle, ...]:
    """The payer's picks from a plan's recorded (pool, need) segments, Handle-sorted. A
    segment with no real choice (len(pool) <= need) is auto-filled; otherwise each pick is
    asked through the decision channel (ask key ``<lane>:<seat>:<source>:<digest>``,
    vocabulary = the Handle strings)."""
    ctx = ctx_for(executor, source=source, controller=controller)
    chosen: list[Handle] = []
    for pool, need in options:
        remaining = [h for h in pool if h not in chosen]
        if len(remaining) <= need:
            chosen.extend(remaining[:need])
            continue
        for _pick in range(need):
            vocab = tuple(str(h) for h in sorted(remaining))
            answer = ctx.take_decision(
                vocab, f"{lane}:{controller}:{source}:{site_digest(vocab)}"
            )
            pick = next(h for h in remaining if str(h) == answer)
            chosen.append(pick)
            remaining.remove(pick)
    return tuple(sorted(chosen))


def pay_costs(
    executor: Executor,
    plan: PaymentPlan,
    *,
    source: Handle,
    controller: Handle,
    mana_use: Handle | None = None,
) -> None:
    """Execute a :class:`PaymentPlan` through the journalled verbs in the
    order mana, tap, sacrifice, discard, counters, loyalty, life — taps,
    sacrifices, discards and counters fire their journal events exactly
    like effect atoms (TapState, ZONE_CHANGE, SACRIFICE…). Mana is the
    deterministic pool subtraction (no verb spends mana) with a
    ``PAY_MANA`` audit row on the executor event log. Where the plan
    recorded a real choice (``tap_options``, ``sacrifice_options``,
    ``discard_options``), the payer picks through the decision channel.

    Each step is its own op, and none settles: casting and activating pay
    inside ``Executor.atomic`` (CR 601.2g-h, 602.2b), and an effect's payment
    inside its resolution, so a sacrificed creature's dies trigger waits for
    the next priority point and goes on the stack above the spell or ability."""
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
            # Mirror the subtraction onto the segment side-ledger —
            # untagged first, then filter-matching tagged segments; a
            # restricted segment is NEVER touched unless the payment can
            # demonstrate its use (see ManaLedger.consume).
            ctx = ctx_for(executor, source=source, controller=controller)
            executor.mana_ledger.consume(
                controller, plan.mana, _mana_use_ok(ctx, mana_use)
            )
    if plan.tap:
        # WHICH permanent taps is the payer's decision when the recorded
        # pool really offers one (len(pool) > need). A forced segment
        # (auto-filled, no ask) and every plan without recorded options pay
        # the witness pick.
        tapped = plan.tap
        if plan.tap_options:
            tapped = _ask_cost_choices(
                executor, plan.tap_options, "tap", source=source, controller=controller
            )
        executor.apply_effect(
            _binding_atom(Verb.TAP, "target", tapped),
            source=source,
            controller=controller,
            bindings={"target": list(tapped)},
        )
    if plan.sacrifice:
        # WHO dies is the controller's decision, not an accident of Handle
        # order. When a segment's recorded pool really offers a choice
        # (len(pool) > need), the victims go through the decision channel
        # — the same lane the trigger designation and the ONE_OF choose use
        # (ask key sacrifice:<seat>:<source>:<digest>, vocabulary = the
        # Handle strings). A forced segment (len(pool) == need — every
        # IS_SOURCE self-sac, the sole-creature floor) keeps the plan's
        # witness pick: forced auto-fill, no ask. A hand-built plan
        # (default () options) pays the witness.
        victims = plan.sacrifice
        if plan.sacrifice_options:
            victims = _ask_cost_choices(
                executor, plan.sacrifice_options, "sacrifice", source=source, controller=controller
            )
        executor.apply_effect(
            _binding_atom(Verb.SACRIFICE, "target", victims),
            source=source,
            controller=controller,
            bindings={"target": list(victims)},
        )
    if plan.discard:
        # The discard-cost pool asks through the same lane as the sacrifice
        # above — WHICH cards burn is the payer's decision, not an accident
        # of Handle order.
        burned = plan.discard
        if plan.discard_options:
            burned = _ask_cost_choices(
                executor, plan.discard_options, "discard", source=source, controller=controller
            )
        executor.apply_effect(
            # A cost discard is a MOVE_ZONE (HAND -> GY) of the designated cards.
            _binding_atom(
                Verb.MOVE_ZONE,
                "cards",
                burned,
                controller=ControllerRef.YOU,
                destination=Zone(ZoneKind.GRAVEYARD, ControllerRef.YOU),
                **{"from": Zone(ZoneKind.HAND, ControllerRef.YOU)},
            ),
            source=source,
            controller=controller,
            bindings={"cards": list(burned)},
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
        # The loyalty ledger steps through the same journalled counter
        # verbs (PUT/REMOVE with CounterKind.LOYALTY). A walker paid down to 0
        # keeps a zeroed LOYALTY key, so the state check that settles this step
        # puts it into its owner's graveyard (CR 704.5i,
        # ``Executor._zero_loyalty_walkers``).
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


def activation_target_reason(
    executor: Executor,
    ability: ActivatedAbility,
    *,
    source: Handle,
    seat: Handle,
    targets: Sequence[Handle] | Sequence[Sequence[Handle]],
) -> str | None:
    """Why ``targets`` is not a legal designation for the
    ability's target slots (query.activation_target_slots, the slots the
    policies designate from), or None. One slot: the slot's own oracle
    (validate_target_selection, as a single-slot cast), on the sorted
    designation activate() binds. Several: per slot, exactly as a spell's
    (stack.designate_slots: one tuple per slot or one handle per slot, an "up
    to" slot possibly empty, an "another target" slot sharing no target). On
    the synthesized player slot ("target opponent") a card stands for its
    controller, the runtime's own re-point rule. No slot the walker can see:
    None (nothing to check). No targets: the first slot that needs one says
    why (CR 602.2b, 601.2c: an ability that says "target" is not activated
    without its targets, as stack.cast refuses a spell's empty designation);
    an "up to" slot may stay empty."""
    from MTG_bot.core.executor.query import (
        activation_target_slots,
        validate_target_selection,
    )
    from MTG_bot.core.executor.stack import designate_slots

    slots = activation_target_slots(executor, ability.effect, source=source, seat=seat)
    if not slots:
        return None
    if not targets:
        return next((why for slot in slots if (why := validate_target_selection(slot, ())) is not None), None)

    def designated(slot, handle: Handle) -> Handle:
        if slot.synthetic and handle.namespace == "card":
            return executor.controller_of(handle)
        return handle

    if len(slots) == 1:
        return validate_target_selection(
            slots[0], tuple(sorted(designated(slots[0], h) for h in targets))
        )
    try:
        designate_slots(slots, targets, stand_in=designated, lane="activate")
    except ValueError as e:
        return str(e).removeprefix("executor: activate: ")
    return None


def activate(
    executor: Executor,
    handle: Handle,
    ability_idx: int,
    *,
    seat: Handle,
    targets: Sequence[Handle] | Sequence[Sequence[Handle]] = (),
    decisions: Sequence[str] = (),
    x: int | None = None,
) -> tuple:
    """The folded ``ACTIVATE`` move (DESIGN_ACTION_SPACE.md §1.3: legality,
    payment, effect — one engine call, no five micro-decisions to tap five
    lands): re-check :func:`ability_playable` against the live world
    (illegal → ``ValueError(reason)``), validate ``targets`` against the
    ability's slots, :func:`pay_costs`, then run the ability's effect with
    ``targets`` designated as the ``target`` bindings the role readers
    consume (an ability with several target slots: one tuple per slot, or
    one handle per slot, as stack.designate_slots reads a spell's). The
    targets are checked again as the ability resolves (CR 608.2b); with
    none still legal it does not resolve and the call returns ``()``. The
    effect tree's own decisions (``OptionalEffect`` fire/skip, any-colour
    ADD_MANA) come through ``decisions`` in tree order. Returns the
    effect's event tuple.

    X lane (CR 602.2b -> 601.2b, 107.3a): an activation whose cost carries
    X announces it before paying. ``x`` is the caller's announcement
    (refused outside ``0..activation_x_max``); with ``x=None`` the X is
    asked through the decision channel (:func:`ask_activation_x`; the
    ``decisions`` pool answers first). The payment and the effect both read
    the announced X. Passing ``x`` for a cost with no X is refused."""
    reason = ability_playable(
        executor.world,
        executor,
        handle,
        ability_idx,
        seat=seat,
    )
    if reason is not None:
        raise ValueError(f"executor: illegal activation: {reason}")
    if ability_idx < 0:
        # A granted row (see ability_playable's controller rule): the
        # ability's SOURCE is the granted permanent and the effect runs in
        # the GRANTEE's coordinates (``seat``) — source=handle below.
        granted = executor.layers.granted_activated(handle)
        ability = granted[-ability_idx - 1].node
    else:
        # Same oracle-registry fallback as ability_playable — a hand
        # activation (Waker of Waves) has no bridge record.
        record = spell_record(executor, handle)
        ability = record.abilities[ability_idx]
    if not isinstance(ability, ActivatedAbility):  # pragma: no cover — checked
        # ValueError, not TypeError: "illegal activation" is the documented
        # domain contract of activate(), whatever the wrong input was.
        raise ValueError("executor: illegal activation: ability:not_activated")
    # CR 602.2b -> 601.2b: X is announced before the cost is paid.
    x_max = activation_x_max(executor.world, handle, ability.cost)
    x_value: int | None = None
    if x_max is not None:
        if x is None:
            x_value, decisions = ask_activation_x(
                executor, handle, seat, x_max, decisions
            )
        elif x < 0:
            raise ValueError(f"executor: illegal activation: x:{x}<0")
        elif x > x_max:
            # CR 606.6 (loyalty [−X]): X can't exceed the loyalty counters.
            raise ValueError(f"executor: illegal activation: x:{x}>max:{x_max}")
        else:
            x_value = x
    elif x is not None:
        raise ValueError("executor: illegal activation: x:no_x_in_cost")
    # The targets are announced next (CR 602.2b, 601.2c),
    # before costs are paid, and must be legal for the ability's own target
    # slots, exactly as stack.cast validates a spell's: a policy or tool
    # passing an illegal target is refused before anything is paid.
    target_reason = activation_target_reason(
        executor, ability, source=handle, seat=seat, targets=targets
    )
    if target_reason is not None:
        raise ValueError(f"executor: illegal activation: target:{target_reason}")
    ctx = ctx_for(executor, source=handle, controller=seat, x_value=x_value)
    plan, plan_reason = build_payment_plan(
        executor.world, ctx, ability.cost, activation=handle
    )
    if plan is None:  # pragma: no cover - ability_playable just checked
        raise ValueError(f"executor: illegal activation: {plan_reason}")
    with executor.atomic():  # CR 602.2b: the costs are paid as part of activating
        pay_costs(executor, plan, source=handle, controller=seat)
    loyalty_ability = is_loyalty_ability(ability)
    if loyalty_ability:
        # CR 606.3 once-per-turn clock, keyed on the permanent. Keyed
        # on the COST SHAPE, not the paid amount: a loyalty [−X] with X = 0
        # (or a [0] ability) removes no counter and is still the turn's
        # loyalty ability.
        executor.loyalty_clock[handle] = executor.world.turn
    # CR 602.2, 605.3b: ONE ABILITY_ACTIVATED row per activation, mana
    # abilities included — the AbilityActivatedEvent feed. The row carries the
    # 605.1a verdict and the paid loyalty delta (None = not a loyalty
    # ability), so a trigger of kind NON_MANA or LOYALTY reads the
    # classification made at activation time. It lands after payment (the
    # same one-call compromise as the targeting rows below): the queued
    # trigger sees the post-payment world.
    executor.journal.emit_ability_activation(
        handle,
        seat,
        ability_idx,
        mana=is_mana_ability(ability),
        loyalty=plan.loyalty if loyalty_ability else None,
    )
    flat = tuple(h for t in targets for h in ((t,) if isinstance(t, Handle) else t))
    chosen = sorted(flat)
    if chosen:
        # TARGETING feed. Clock-order caveat of the FOLDED move: the targets
        # are validated before payment but journalled after it, so these
        # rows land after the payment rows — a compromise of the one-call
        # surface, not CR 602.2b's declare-then-pay order.
        executor.journal.emit_targeting(handle, seat, chosen)
    # CR 602.2b, 601.2c: an ability with several targets ("Target creature
    # you control deals damage equal to its power to another target creature",
    # Garruk, Savage Herald's -2) designates per slot, exactly as the cast lane
    # threads a spell's (stack.designate_slots, validated above); each TARGET
    # selector then reads its own designation, not the union, and an "up to"
    # slot left empty acts on nothing.
    from MTG_bot.core.executor.stack import StackObject, slot_groups

    slot_designations: dict[str, tuple[Handle, ...]] = {}
    if targets:
        from MTG_bot.core.executor.query import activation_target_slots

        slots = activation_target_slots(executor, ability.effect, source=handle, seat=seat)
        if len(slots) > 1:
            slot_designations = {
                repr(slot.selector): tuple(sorted(group))
                for slot, group in zip(slots, slot_groups(slots, targets), strict=True)
            }
    obj = StackObject(
        handle=executor.ability_handles.allocate(),
        node=ability,
        controller=seat,
        spell_kind="ACTIVATED",
        x_value=x_value,
        declared_targets=tuple(chosen),
        payment=plan,
        declared_clock=executor.journal.clock,
        decisions=tuple(decisions),
        slot_designations=slot_designations,
        source=handle,
        ability_idx=ability_idx,
    )
    start = len(executor.events)
    if is_mana_ability(ability):
        # CR 605.3b: a mana ability does not use the stack; it resolves at once.
        with executor.atomic():
            resolve_activated(executor, obj)
    else:
        # What activating triggered goes on the stack above the ability and
        # resolves first (CR 117.5), then the ability (both players pass).
        executor.stack.push(obj)
    executor._finish_op()
    return tuple(executor.events[start:])


def resolve_activated(executor: Executor, obj) -> str:
    """CR 608.2: an activated ability resolves (``stack.resolve_top`` for one on
    the stack, :func:`activate` for a mana ability). Its targets are checked again
    (CR 608.2b): with none still legal it does not resolve ("no_targets", and a
    NO_LEGAL_TARGETS row). Otherwise its effect runs from its source, in its
    controller's coordinates, with the targets bound and every X the announced X
    (CR 107.3a). Returns "resolved"; the caller settles afterwards."""
    from MTG_bot.core.executor.query import activation_target_slots, designates
    from MTG_bot.core.executor.stack import recheck_targets

    ability, source, seat = obj.node, obj.source, obj.controller
    bindings: dict[str, Binding] = {}
    slot_designations = obj.slot_designations or None
    if not obj.declared_targets and designates(ability.effect):
        bindings["target"] = []  # an "up to" designation that chose nothing (CR 115.6)
    if obj.declared_targets:
        # CR 608.2b: the targets are checked again as the ability resolves, after its
        # costs are paid (Heartfire Immolator sacrificed itself while targeting itself).
        slots = activation_target_slots(executor, ability.effect, source=source, seat=seat)
        legal_now, kept = recheck_targets(
            executor, slots, obj.declared_targets, designations=slot_designations,
            since=obj.declared_clock,
        )
        if not legal_now:
            executor.events.append(
                (len(executor.events), "NO_LEGAL_TARGETS", str(source), str(obj.ability_idx))
            )
            return "no_targets"
        bindings["target"] = sorted(legal_now)
        if kept is not None:
            slot_designations = kept
    executor.apply_effect(
        ability.effect,
        source=source,
        controller=seat,
        bindings=bindings,
        decisions=obj.decisions,
        slot_designations=slot_designations,
        x_value=obj.x_value,
    )
    return "resolved"


# --------------------------------------------- mana abilities while paying
# CR 601.2g / 605.3a: a player may activate mana abilities while paying a
# cost, including in the middle of a resolution. The engine pays from the
# pool, and the pool empties as each step and phase ends, so these helpers
# let a payment tap the payer's mana sources: a minimal set the payment
# planner proves sufficient, never all. The menu (executor/menu.py) pays
# with free sources (non-creature permanents whose mana ability costs only
# {T}: lands, plain mana rocks), then costly ones (_source_tier); a payment
# inside a resolution ("you may pay", "unless its controller pays") with
# free sources only. A mana-cost filter is never activated on the
# player's behalf.
# SCAFFOLD (BACKLOG "scaffolds to remove"): the engine picks the sources, a
# decision hidden from the player (AGENTS §10); removed by the PAYMENT asks
# of DESIGN_ACTION_SPACE §1.3 (a learned payment choice).


@dataclass(frozen=True)
class ManaTap:
    """One mana ability to activate: ``decisions`` choose its colour (an
    any-colour ADD_MANA, or a Choose between ADD_MANA options) and
    ``production`` is what it adds, as (colour, amount, spend-restriction tags).
    ``tier`` is what activating it costs besides the mana (:func:`_source_tier`)."""

    source: Handle
    ability_idx: int
    decisions: tuple[str, ...]
    production: tuple[str, int, tuple[Filter, ...]]
    tier: int = 0


def _source_tier(ability: ActivatedAbility, creature: bool) -> int | None:
    """How dear a mana source is to tap while paying, None for one never tapped
    on the payer's behalf. 0: a free source, a non-creature permanent whose
    ability costs only {T} (lands, plain mana rocks). 1: a creature's {T}
    ability (tapped, it cannot attack or block). 2: an ability that also
    sacrifices its own permanent (the Treasure). Any other cost (a mana cost,
    a filter like Prismite's {2}; another permanent to sacrifice) is never
    paid for the payer."""
    from MTG_bot.core.executor.selectors import _filter_is_self_referential

    tap = sacrifice = False
    for part in ability.cost.parts:
        if isinstance(part, CostTap) and part.target is None:
            tap = True
        elif isinstance(part, CostSacrifice) and _filter_is_self_referential(part.target.filter):
            sacrifice = True
        else:
            return None
    if sacrifice:
        return 2
    if tap:
        return 1 if creature else 0
    return None


def _mana_atom_output(atom: object, ctx: ExecCtx) -> tuple[str | None, int] | None:
    """(colour or None for "any colour", amount) of a "you add" ADD_MANA atom;
    None for anything else."""
    if not (isinstance(atom, Atom) and atom.verb is Verb.ADD_MANA):
        return None
    controller = atom.args.get("controller")
    if controller is not None and controller is not ControllerRef.YOU:
        return None
    amount = atom.args.get("amount")
    if not isinstance(amount, Quantity):
        return None
    color = atom.args.get("color")
    return (None if color in (None, "ANY") else str(color)), resolve(amount, ctx)


def _mana_tap_options(
    executor: Executor, payer: Handle, costly: bool = False
) -> list[list[ManaTap]]:
    """Per mana source of ``payer`` (Handle order), the ways its first eligible
    ability can add mana. Free sources only (:func:`_source_tier` 0), or with
    ``costly`` the dearer ones too; eligible: an effect of one ADD_MANA atom
    (fixed colour or any colour) or a Choose between ADD_MANA atoms (dual
    lands), and activatable by ``payer`` right now (ability_playable: so tapped
    sources, summoning-sick creatures and locked abilities are out). Scans
    printed and granted abilities like legal_activations, which this does not
    call because it raises on cost kinds it cannot check."""
    from MTG_bot.core.ability_tree import Choose
    from MTG_bot.core.executor.query import choose_options
    from MTG_bot.core.executor.verbs import _ANY_COLOR_VOCAB

    world = executor.world
    out: list[list[ManaTap]] = []
    # The battlefields' entries, not every world card: this runs once per payment the menu
    # prices (a world.zone_of scan over every card cost a third of a game's time).
    permanents = (h for p in world.player_order for h in world.players[p].zone(ZONE_BATTLEFIELD).entries)
    for handle in sorted(permanents):
        if executor.controller_of(handle) != payer:
            continue
        creature = eval_filter(_IS_CREATURE, handle, ctx_for(executor, source=handle, controller=payer))
        if creature and not costly:
            continue
        rows: list[tuple[int, object]] = []
        record = executor.binder.handle_record.get(handle)
        if record is not None:
            rows.extend(enumerate(record.abilities))
        rows.extend(
            (-k - 1, entry.node)
            for k, entry in enumerate(executor.layers.granted_activated(handle))
        )
        for idx, ability in rows:
            if not isinstance(ability, ActivatedAbility):
                continue
            tier = _source_tier(ability, creature)
            if tier is None or (tier and not costly):
                continue  # (the cheap test first: is_mana_ability walks the whole tree)
            if not is_mana_ability(ability):
                continue  # CR 605.3a: only a mana ability (605.1a) is activated while paying
            ctx = ctx_for(executor, source=handle, controller=payer)
            policy = executor.layers.this_mana_filter(handle)
            tags: tuple[Filter, ...] = (policy,) if policy is not None else ()
            effect = ability.effect
            taps: list[ManaTap] = []
            if isinstance(effect, Atom):
                got = _mana_atom_output(effect, ctx)
                if got is not None:
                    color, n = got
                    colors = _ANY_COLOR_VOCAB if color is None else (color,)
                    decide = color is None
                    taps = [
                        ManaTap(handle, idx, (c,) if decide else (), (c, n, tags), tier)
                        for c in colors
                    ]
            elif isinstance(effect, Choose):
                for token, opt in enumerate(
                    choose_options(executor, effect, source=handle, controller=payer)
                ):
                    got = (
                        _mana_atom_output(effect.options[opt.option_idxs[0]], ctx)
                        if len(opt.option_idxs) == 1
                        else None
                    )
                    if got is None or got[0] is None:
                        taps = []
                        break
                    taps.append(ManaTap(handle, idx, (str(token),), (got[0], got[1], tags), tier))
            taps = [t for t in taps if t.production[1] > 0]
            if not taps:
                continue
            if ability_playable(world, executor, handle, idx, seat=payer) is not None:
                continue
            out.append(taps)
            break  # one {T} ability per permanent: it can tap once
    return out


def _mana_shortfall(reason: str | None) -> tuple[str, tuple[str, ...]] | None:
    """The mana a failed plan lacks, read from build_payment_plan's
    machine-readable reason: ("color", (c,)), ("hybrid", (c1, c2)) or
    ("generic", ()); None when the failure is not a mana shortage."""
    if reason is None:
        return None
    if reason.startswith("cost:mana_generic:"):
        return "generic", ()
    if reason.startswith("cost:mana_hybrid:"):
        colors = tuple(c for c in reason.split(":")[2] if c in MANA_KEYS)
        return ("hybrid", colors) if colors else None
    if reason.startswith("cost:mana:"):
        color = reason.split(":")[2]
        return ("color", (color,)) if color in MANA_KEYS else None
    return None


def _with_trial_mana(executor: Executor, payer: Handle, taps: Sequence[ManaTap], check):
    """``check()`` with the payer's pool and segment mirror holding the taps'
    production; both are restored exactly afterwards (nothing is journalled,
    so the trial leaves no trace in the replay)."""
    pool = executor.world.players[payer].mana_pool
    saved_pool = dict(pool)
    ledger = executor.mana_ledger
    had_segments = payer in ledger.segments
    saved_segments = list(ledger.segments.get(payer, []))
    try:
        for tap in taps:
            color, n, tags = tap.production
            pool[color] = pool.get(color, 0) + n
            ledger.add(payer, color, n, tags)
        return check()
    finally:
        pool.clear()
        pool.update(saved_pool)
        if had_segments:
            ledger.segments[payer] = saved_segments
        else:
            ledger.segments.pop(payer, None)


def _paying_tap(
    taps: list[ManaTap], kind: str, colors: tuple[str, ...], any_colour: bool
) -> ManaTap | None:
    """The way of this source that pays the shortfall (``_mana_shortfall``), if any."""
    if kind == "generic" or any_colour:
        return taps[0]
    return next((t for c in colors for t in taps if t.production[0] == c), None)


def _keeps_open(taps: list[ManaTap], free: list[list[ManaTap]]) -> tuple[int, int, int, Handle]:
    """plan_mana_taps' order, smallest first: the cheapest tier
    (:func:`_source_tier`), then the most colours the other untapped sources
    still make once this one is tapped, then the fewest colours this one makes,
    then the lowest Handle. Colourless is not a colour (CR 105.1, 106.1b): a
    colourless source pays only generic costs, so it pays them first."""
    left = {t.production[0] for other in free if other is not taps for t in other} - {"C"}
    return (taps[0].tier, -len(left), len({t.production[0] for t in taps} - {"C"}), taps[0].source)


def plan_mana_taps(
    executor: Executor,
    payer: Handle,
    check,
    *,
    exclude: frozenset[Handle] = frozenset(),
    keep: frozenset[Handle] = frozenset(),
    costly: bool = False,
    sources: dict[bool, list[list[ManaTap]]] | None = None,
    payable_only: bool = False,
) -> tuple[ManaTap, ...] | None:
    """The mana sources ``payer`` taps so a payment can be made (pool first).
    ``check()`` returns None when the payment is plannable, else the planner's
    reason. Returns () when the pool already pays, the taps when they make it
    pay, and None when no set of free sources does (the payment is then
    declined). ``exclude``: permanents the payment itself
    taps (an ability's own {T}), never tapped for mana. ``keep``: the spell's or
    ability's own targets, chosen before the costs are paid (CR 601.2c, 601.2h),
    never sacrificed to pay (the spell would lose them); tapping one stays
    allowed (an aura on the land that pays for it). Free sources pay first;
    with ``costly`` (a cast or activation from the menu, ``executor.menu``) the
    dearer sources pay what they cannot, a creature's before a sacrifice
    (:func:`_source_tier`). A payment inside a resolution taps free sources only
    (:func:`tap_for_payment` taps them in place). ``sources``: a dict a caller
    pricing many payments in one unchanged position (the menu) shares, so the
    payer's sources are listed once (:func:`_mana_tap_options`, by ``costly``).

    One deterministic rule, which keeps the most mana options open: each
    shortfall the planner names (coloured symbols before generic ones) is
    paid by the source whose loss leaves the most colours the other untapped
    free sources can still make, then the one that makes the fewest colours,
    then the lowest Handle (:func:`_keeps_open`). A coloured shortfall that
    leads nowhere tries the next source in that order (:func:`_fill`), so a
    payment is found whenever one exists ({R}{W} from a R/W and a B/R dual).
    With Chromatic Orrery's permission (mana of any colour pays a coloured
    symbol) every source pays every symbol. A last pass removes every tap the
    payment does not need, so the set is inclusion-minimal.

    ``payable_only``: the caller asks only whether the payment can be made (the menu); the
    taps returned are then some that pay, not the planned ones. One trial with every source
    tapped answers at once when it can: it pays, or it leaves generic mana short while no
    source's choice changes how much mana it makes, so no set of taps could pay."""
    reason = check()
    if reason is None:
        return ()
    if _mana_shortfall(reason) is None:
        return None  # not short of mana (the timing, a target, another cost): no source helps
    any_colour = executor.mana_permission(payer)
    chosen = None
    tiers = (costly,) if payable_only else (False, True) if costly else (False,)
    for dear in tiers:
        listed = sources.get(dear) if sources is not None else None
        if listed is None:
            listed = _mana_tap_options(executor, payer, dear)
            if sources is not None:
                sources[dear] = listed
        options = [
            taps for taps in listed
            if taps[0].source not in exclude and not (taps[0].tier == 2 and taps[0].source in keep)
        ]
        if payable_only:
            every = [taps[0] for taps in options]
            trial = _with_trial_mana(executor, payer, every, check)
            if trial is None:
                return tuple(every)
            fixed = all(t.production[1:] == taps[0].production[1:] for taps in options for t in taps)
            if fixed and _mana_shortfall(trial) == ("generic", ()):
                return None
        chosen = _fill(executor, payer, check, options, any_colour, [], reason, set())
        if chosen is not None:
            break
    if chosen is None or payable_only:
        return None if chosen is None else tuple(chosen)
    for tap in list(reversed(chosen)):
        rest = [t for t in chosen if t is not tap]
        if _with_trial_mana(executor, payer, rest, check) is None:
            chosen = rest
    return tuple(chosen)


def _fill(
    executor: Executor,
    payer: Handle,
    check,
    options: list[list[ManaTap]],
    any_colour: bool,
    chosen: list[ManaTap],
    reason: str | None,
    seen: set[frozenset[tuple[Handle, str]]],
) -> list[ManaTap] | None:
    """plan_mana_taps' search: the taps that complete ``chosen``, depth first
    over the shortfalls the planner names, sources in :func:`_keeps_open`
    order. Only a coloured or hybrid shortfall tries a second source: any
    source pays a generic one. ``seen`` holds the (source, colour) sets
    already tried, so an order of the same taps is never tried twice."""
    if reason is None:
        return chosen
    need = _mana_shortfall(reason)
    if need is None:
        return None
    kind, colors = need
    used = {tap.source for tap in chosen}
    free = [taps for taps in options if taps[0].source not in used]
    payers = sorted(
        (_keeps_open(taps, free), tap)
        for taps in free
        if (tap := _paying_tap(taps, kind, colors, any_colour)) is not None
    )  # the keys differ: each names its own source
    for _key, tap in payers:
        trial = [*chosen, tap]
        tried = frozenset((t.source, t.production[0]) for t in trial)
        if tried in seen:
            continue
        seen.add(tried)
        new_reason = _with_trial_mana(executor, payer, trial, check)
        if new_reason == reason and tap.production[2]:
            # Spend-restricted mana (Vodalian Arcanist's) that this payment may
            # not use leaves the shortfall as it was: try the next source.
            # Unrestricted mana always pays something (a repeated reason then
            # only means a second symbol of the same colour, as in {U}{U}).
            continue
        found = _fill(executor, payer, check, options, any_colour, trial, new_reason, seen)
        if found is not None or kind == "generic" or any_colour:
            return found
    return None


def tap_for_payment(
    executor: Executor,
    payer: Handle,
    taps: Sequence[ManaTap],
    *,
    inside_atom: bool = False,
) -> None:
    """Activate the planned mana abilities. At top level (paying for a cast or
    an activation) each is the ordinary journalled activation move, with no
    priority point between them. Inside a running atom ("you
    may pay", "unless its controller pays") a mana ability resolves at once
    without the stack (CR 605.3b): the permanent taps and its mana is added in
    place, and the running atom's journal diff records the tap once. A nested
    activation would journal the tap twice and settle unrelated triggers in the
    middle of the resolution. The planned taps are exactly the eligible
    single-ADD_MANA shapes, so the in-place result equals the activation's.

    Either way each tap journals the ABILITY_ACTIVATED row that
    :func:`activate` writes (CR 602.2, 605.3b: one per activation, mana
    abilities included), so a "whenever a player activates an ability" trigger
    sees a mana ability activated while paying. The planner only picks
    ability_playable sources, so an activation lock (CR 602.5) already keeps a
    locked mana ability out of the plan."""
    if not inside_atom:
        # Paying is part of the cast or activation (CR 601.2g, 605.3a): no
        # priority point between the taps, and what they trigger waits for
        # the one after the spell or ability is on the stack.
        with executor.atomic():
            for tap in taps:
                activate(executor, tap.source, tap.ability_idx, seat=payer, decisions=tap.decisions)
        return
    for tap in taps:
        executor.world.cards[tap.source].tapped = True
        color, n, tags = tap.production
        pool = executor.world.players[payer].mana_pool
        pool[color] = pool.get(color, 0) + n
        executor.mana_ledger.add(payer, color, n, tags)
        executor.events.append((len(executor.events), "ADD_MANA", str(payer), color, n))
        # The planner admits only 605.1a mana abilities (_mana_tap_options). The
        # row lands before the running atom's diff journals the tap itself.
        executor.journal.emit_ability_activation(
            tap.source, payer, tap.ability_idx, mana=True, loyalty=None
        )


# ------------------------------------------------------------ attack legality
# The CR 508.1 declare-attackers surface. The COMBAT skeleton asks one
# binary question per CREATURE; this module is the honest candidate list
# the ask is built from — the policy is NEVER offered a DECLINE it cannot
# legally answer, and the assembled set is whole-set-checked before
# anything taps.
_IS_CREATURE = FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature")

from MTG_bot.core.executor.events import (
    KIND_TURN_PHASE,
    KIND_ZONE_CHANGE,
)


def _controlled_since_turn_start(
    executor: Executor, creature: Handle, seat: Handle | None = None
) -> bool:
    """CR 302.6 (summoning sickness): has ``creature`` been under ``seat``'s
    control continuously since ``seat``'s most recent turn began?

    The answer is a JOURNAL read, never a mirror-table: the turn's UPKEEP
    marker (the same anchor :meth:`EventJournal.turn_window` uses) opens
    the turn; a ZONE_CHANGE row ENTERING the battlefield after that marker
    — first arrival, a blink return, a graveyard replay — means the
    permanent is not yet ready. No rows after the marker = continuous
    presence since the turn began (setup creatures carry no rows at all
    and read ready, which is the correct pre-game-control reading). A
    CONTROL change is not a zone change — the overlay's gained-turn
    marker is the second half of this oracle (CR 302.6 is control-based,
    not ownership-based), and a returned owner is a fresh period too.
    Both halves must hold: a marker left by an earlier control change does
    not excuse a later battlefield entry (a stolen, returned, bounced and
    recast creature is a new object, CR 400.7, and is sick).

    ``seat`` None or the active player anchors on the most recent UPKEEP
    marker (the attack lane: only the active player attacks). Any other
    seat anchors on ITS OWN most recent turn: a creature
    that entered during its controller's turn stays sick through the
    opponent's turn ("their most recent turn", CR 302.6). That turn's
    number is the current one minus the turns begun since."""
    world = executor.world
    events = executor.journal.events
    own_turn_only = seat is not None and seat != world.active_player
    start = -1
    turns_since = 0
    for i in range(len(events) - 1, -1, -1):
        row = events[i]
        if row.kind == KIND_TURN_PHASE and row.data[0] == Phase.UPKEEP.name:
            if own_turn_only and row.data[1] != seat:
                turns_since += 1
                continue
            start = i
            break
    gained = executor.control_gained_turn.get(creature)
    if gained is not None and gained >= world.turn - turns_since:
        return False  # control changed since that turn began
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
    check): on the battlefield and not phased out (CR 702.26b), controller,
    creature-ness (the LIVE type line — GRANT_TYPE overlay aware), untapped
    (CR 508.1a: the chosen creatures must be untapped, so a creature tapped
    for mana or by Frost Breath cannot attack; attacking then taps the rest,
    VIGILANCE excepted, CR 508.1f), DEFENDER (CR 702.3b) unless an
    attack policy lets the creature attack as though it didn't have defender
    (CR 609.4, :func:`attack_policy_applies`), summoning sickness (CR 302.6) unless the
    creature has HASTE (CR 702.10a), and the PREVENT_EFFECT attack veto
    (Faith's Fetters' "enchanted permanent can't attack", consumed through
    the prevention registry)."""
    world = executor.world
    if world.zone_of(creature).kind != ZONE_BATTLEFIELD:
        return "not on the battlefield"
    if creature in executor.phased_out:
        return "phased out (CR 702.26b)"
    if executor.controller_of(creature) != seat:
        return "not controlled by the declaring player"
    ctx = executor._ctx(source=creature, controller=seat, bindings=None, decisions=())
    if not eval_filter(_IS_CREATURE, creature, ctx):
        return "not a creature"
    if world.cards[creature].tapped:
        return "tapped (CR 508.1a)"
    if executor.layers.keyword_of(creature, Keyword.DEFENDER) and not attack_policy_applies(
        executor, creature, "AS_NO_DEFENDER"
    ):
        return "defender (CR 702.3b)"
    if not executor.layers.keyword_of(creature, Keyword.HASTE) and not (
        _controlled_since_turn_start(executor, creature)
    ):
        return "summoning sickness (CR 302.6) without haste"
    if executor.replacements.prevents_attack_declaration(creature):
        return "attack prevented (PREVENT_EFFECT, CR 508.1A)"
    return None


def attack_policy_applies(executor: Executor, creature: Handle, scope: str) -> bool:
    """CR 609.4: may ``creature`` attack "as though" ``scope`` were true? A live
    ATTACK_POLICY layer, static (Drowsing Tyrannodon's "As long as you control a
    creature with power 4 or greater, this creature can attack as though it didn't
    have defender") or made by a resolving ability, names it. ``AS_NO_DEFENDER``
    lifts only the defender restriction on attacking (CR 702.3b): the creature
    still has defender for every other purpose."""
    return any(
        layer.atoms[0].args.get("scope") == scope
        and creature in _rule_subjects(executor, layer)
        for layer in executor.layers.live_records("attack_policy")
    )


def legal_attackers(executor: Executor, seat: Handle) -> tuple[Handle, ...]:
    """The Handle-sorted candidate set the declare-attackers asks are
    enumerated from (canonical order)."""
    world = executor.world
    return tuple(
        card
        for card in sorted(world.cards)
        if executor.controller_of(card) == seat
        and world.zone_of(card).kind == ZONE_BATTLEFIELD
        and attack_blocked_reason(executor, seat, card) is None
    )


def _rule_subjects(executor: Executor, layer: LayerRecord) -> tuple[Handle, ...]:
    """The creatures one LIVE combat-rule layer (a mandate or an attack
    policy) binds. A ``resolved`` record (a dispatched rule with a duration)
    designated its creatures once, at resolution; a static one re-resolves
    its ``cards`` selector in the layer anchor's coordinates every combat,
    like any continuous-effect scope."""
    if layer.resolved:
        return layer.targets
    selector = layer.atoms[0].args.get("cards")
    assert isinstance(selector, Selector)  # role table: cards required
    ctx = executor._ctx(
        source=layer.source,
        controller=layer.controller,
        bindings=None,
        decisions=(),
    )
    return tuple(enumerate_candidates(selector, ctx))


def mandated_attackers(executor: Executor, seat: Handle) -> frozenset[Handle]:
    """Creatures ``seat`` controls that MUST attack this combat if able
    (CR 508.1 "attacks each combat if able"), from BOTH carrier shapes:
    the dispatched mandates ledger (MANDATE_ATTACK verb without a duration;
    with one it is a ``resolved`` layer) and the LIVE mandate layers
    (the static shape — Furor of the Bitten, the Pirate token), whose
    ``cards`` selectors resolve in the layer anchor's coordinates exactly
    like a continuous-effect scope. A mandated creature that is ILLEGAL
    (defender, sickness) simply never reaches the set — "if able"."""
    world = executor.world
    mandated: set[Handle] = set()
    for handle in executor.mandates:
        if (
            handle in world.cards
            and world.zone_of(handle).kind == ZONE_BATTLEFIELD
            and executor.controller_of(handle) == seat
        ):
            mandated.add(handle)
    for layer in executor.layers.live_records("mandate"):
        for handle in _rule_subjects(executor, layer):
            if (
                handle in world.cards
                and world.zone_of(handle).kind == ZONE_BATTLEFIELD
                and executor.controller_of(handle) == seat
            ):
                mandated.add(handle)
    return frozenset(mandated)


# ------------------------------------------------------------- block legality
# The CR 509 declare-blockers surface, mirrored on the attack side: the ask
# vocabulary is the honest candidate list — a blocker is never offered an
# attacker it cannot legally block, and NONE is dropped by the ASK LOOP in
# the executor only when dropping it keeps the assembled assignment CR-
# legal (must-be-blocked, menace repair). CR 509.1a: only UNTAPPED creatures
# block (as only untapped creatures attack, CR 508.1a); CR 509.1b: exactly one
# attacker per blocker; multiple blockers per attacker ARE legal, which is
# what the CR 510 order/trample asks in the damage step consume.


def block_pair_blocked_reason(
    executor: Executor, blocker: Handle, attacker: Handle
) -> str | None:
    """Why ``blocker`` may not block ``attacker`` right now, or ``None``.
    Static per-pair legality — the assignment-dependent MENACE count rule
    (CR 702.113 "except by two or more creatures", Bone Pit Brute) is a
    property of the WHOLE assignment, so the ask loop applies it beside
    this reason, never buried inside it. Consumers:
      * creature-ness (only creatures block). DEFENDER is no veto: it
        only forbids attacking (CR 702.3b), so a wall blocks;
      * REACH (CR 509.1b): a flying attacker is unblockable without reach
        (Snarespinner, Elder Gargaroth carry it for themselves);
      * PROTECTION (CR 702.16f): the ATTACKER's protection from the
        blocker vetoes the pair (Baneslayer Angel's "protection from red and
        from black"); a protected blocker may block (``protected_from``);
      * the PREVENT_EFFECT block veto: Tome Anima / Ghostly Pilferer
        "can't be blocked" (blocked-side slots), Pirate "can't block" and
        Shacklegeist "can block only creatures with flying" (blocker-side
        slots), Subira's activated "another target creature can't be
        blocked" (IS_ANY_TARGET materialized onto the record)."""
    world = executor.world
    if world.zone_of(blocker).kind != ZONE_BATTLEFIELD:
        return "not on the battlefield"
    if world.zone_of(attacker).kind != ZONE_BATTLEFIELD:
        return "attacker not on the battlefield"
    if blocker in executor.phased_out or attacker in executor.phased_out:
        return "phased out (CR 702.26b)"
    ctx_blocker = executor._ctx(
        source=blocker,
        controller=executor.controller_of(blocker),
        bindings=None,
        decisions=(),
    )
    if not eval_filter(_IS_CREATURE, blocker, ctx_blocker):
        return "not a creature (CR 509.1)"
    if world.cards[blocker].tapped:
        return "tapped (CR 509.1a)"
    # CR 702.7b: a flyer is blocked only by a creature with FLYING or REACH
    if executor.layers.keyword_of(attacker, Keyword.FLYING) and not (
        executor.layers.keyword_of(blocker, Keyword.REACH)
        or executor.layers.keyword_of(blocker, Keyword.FLYING)
    ):
        return "flying attacker, neither flying nor reach (CR 509.1b)"
    # CR 702.16f: "Attacking creatures with protection can't be blocked by
    # creatures that have the stated quality." Only the ATTACKER's protection
    # restricts the pair: a creature with protection from red may block a red
    # attacker (its damage to the blocker is prevented instead, 702.16e).
    if protected_from(executor, attacker, blocker):
        return "attacker's protection (CR 702.16f)"
    if executor.replacements.prevents_block_declaration(blocker, attacker):
        return "block prevented (PREVENT_EFFECT)"
    return None


def blocker_askable(
    executor: Executor, blocker: Handle, attackers: Sequence[Handle]
) -> bool:
    """Pre-filter for the block-ask candidate list: could ``blocker`` have
    ANY legal declaration against the current attackers? Creature-ness
    and tap state are attacker-independent; the pair vetoes are checked
    against each attacker. A blocker legal against nothing is never asked
    (no decision exists); tapped creatures fall out here — the "tapped
    creatures cannot block" face of CR 509.1a. A creature with defender
    blocks like any other (CR 702.3b forbids only attacking)."""
    world = executor.world
    if world.zone_of(blocker).kind != ZONE_BATTLEFIELD:
        return False
    if blocker in executor.phased_out:  # CR 702.26b
        return False
    ctx_blocker = executor._ctx(
        source=blocker,
        controller=executor.controller_of(blocker),
        bindings=None,
        decisions=(),
    )
    if not eval_filter(_IS_CREATURE, blocker, ctx_blocker):
        return False
    if world.cards[blocker].tapped:
        return False
    return any(
        block_pair_blocked_reason(executor, blocker, attacker) is None
        for attacker in attackers
    )


def mandated_to_be_blocked(executor: Executor) -> frozenset[Handle]:
    """Attackers that MUST be blocked if able (Canopy Stalker), from both
    carrier shapes like the attack side: the DISPATCHED MANDATE_BLOCK ledger
    (a timed one is a ``resolved`` layer) and the LIVE
    ``"mandate_block"`` layers (selector resolved in the layer anchor's
    coordinates). Each is one blocking requirement (CR 509.1c), obeyed by
    whichever creature blocks it; the declare-blockers asks keep the
    declaration obeying as many as it can (``Executor._declare_blockers``)."""
    world = executor.world
    mandated: set[Handle] = set()
    for handle in executor.mandate_block:
        if handle in world.cards and world.zone_of(handle).kind == ZONE_BATTLEFIELD:
            mandated.add(handle)
    for layer in executor.layers.live_records("mandate_block"):
        for handle in _rule_subjects(executor, layer):
            if handle in world.cards and world.zone_of(handle).kind == ZONE_BATTLEFIELD:
                mandated.add(handle)
    return frozenset(mandated)
