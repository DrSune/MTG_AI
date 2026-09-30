"""The model-facing QUERY SURFACE (round 12c, /06 §12c).

The Slate contract of `docs/DESIGN_ACTION_SPACE.md`, served on the executor
side: **one engine call per decision** (§1.4), returning typed references
to the SAME IR objects the executor consumes — §8.3 builder/executor
identity: no DTO layer, no prose anywhere in an option (V_role tags from
§1.2 are type tags on slots, never payload strings), every candidate list
canonical Handle-sorted (§5.5, ruling 5).

Role mapping (V_role §1.2 → this module), for the verbs in the §1.3 field
schedule:

* ``ACTIVATE`` — :func:`legal_activations` produces the candidate rows of
  the ``ABILITY:PTR`` field; each row's payment is the folded
  :class:`~MTG_bot.core.executor.legality.PaymentPlan` covering the
  ``COST_TARGET:PTR*`` + ``PAYMENT:PTR*`` slots (§1.3: mana payment folds
  into the move, CR 601.2g).
* ``TARGET:PTR x n`` — :func:`legal_targets` returns ONE per-slot
  :class:`TargetSlot` (candidates + legal cardinality), never a
  cross-slot product (explosion guard); whole-selection legality is
  :func:`validate_target_selection`. ``forced`` is §1.4's field-level
  auto-fill (exactly one legal filler).
* ``MODE:PTR*`` / ``OPTION:PTR*`` / RESOLVE_CHOICE's ``CHOICE_SLOT`` —
  :func:`choose_options` enumerates every legal option SET of a
  :class:`~MTG_bot.core.ability_tree.Choose` node (C15: every decision is
  enumerable; a missed option is a contract violation).
* the may-offer (``OptionalEffect``) — :func:`optional_offer` returns the
  two-way decision tokens exactly as the 12b/12a decision channel consumes
  them (``"fire"``/``"skip"``), narrowed to one when firing is not
  actionable (a cost-bearing may with nothing to pay it with).
* ``ONE_OF`` / ``REST`` (the split-selection pair, SelectorMode docstring)
  — :func:`legal_targets` reports ``ONE_OF`` as an exactly-one slot over
  the partition population, and the deterministic remainder with
  :func:`rest_of` (:class:`TargetSlot` marks ``REST`` forced — the engine
  takes everything left).

C-contract pins encoded here:

* **C17** — ``TARGET`` + :class:`QAtMost` is a legal *designation* range
  ``1..n`` (still targeted; min 1), resolving to ``0..remaining``;
  ``CHOOSE`` + up-to (and ``Choose`` + ``QAtMost``) is a resolution-time
  enumeration that DOES include the empty selection (``0..n``). The two
  zero-cards sit in different phases and the tests pin both.
* **C15** — completeness of enumeration: may = both options when
  actionable, Choose = every legal option set, QAtMost = every legal
  cardinality, ONE_OF/REST = the partition.
* **§5.5** — option/selection enumeration order is canonical: sizes
  ascending, then index-lex (a bijection from set to sequence).

The 12a NotImplemented-map closures delivered here (in-scope per /06 §12c):
ONE_OF/REST partition enumeration, OWNER referent (the activation context
supplies the owner — see legality.source_owner), CHOOSE-mode candidate
enumeration, and Zone(ANY) population. AMENDED 14c (B-13/B-15): the
resolution side now consumes THESE enumerations rather than re-deriving
them — ONE_OF asks the vocabulary-addressed channel with the Handle-sorted
candidate list (``selectors.resolve_selector``), TARGET reads the spell's
designation, REST takes the deterministic complement — and the raises
stay honest exactly where the world is illegal: an ONE_OF ask no lane can
answer, or an UNdesignated TARGET, is never guessed. The Choose NODE's
dispatch has been wired since 12d (the ORDER contract below); the option
subtree it dispatches is the same enumeration :func:`choose_options`
returns, which is what a Slate answer unfolds to anyway.
"""

from __future__ import annotations

import itertools
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from MTG_bot.core.ability_tree import (
    ActivatedAbility,
    Atom,
    Choose,
    ControllerRef,
    Cost,
    Effect,
    FAnd,
    FAtom,
    FAtomPred,
    OptionalEffect,
    QAtLeast,
    QAtMost,
    QConst,
    QUnbounded,
    Selector,
    SelectorMode,
    SpellAbility,
    Verb,
    Zone,
    ZoneKind,
    walk,
)
from MTG_bot.core.executor.legality import (
    PaymentPlan,
    ability_playable,
    build_payment_plan,
    ctx_for,
    spell_castable,
)
from MTG_bot.core.executor.quantity import Binding, Quantity, resolve
from MTG_bot.core.identity import Handle
from MTG_bot.core.state import GameWorld

if TYPE_CHECKING:  # pragma: no cover - import cycle guard only
    from MTG_bot.core.executor import Executor

__all__ = [
    "ActivationOption",
    "CastOption",
    "OptionChoice",
    "TargetSlot",
    "choose_options",
    "legal_activations",
    "legal_casts",
    "legal_search",
    "legal_targets",
    "optional_offer",
    "rest_of",
    "spell_target_slots",
    "validate_target_selection",
    "verb_choose_options",
]

# The two-way may-decision vocabulary, verbatim as ExecCtx.take_decision
# consumes it (binding.py may-offers, 12b fire order).
MAY_VOCAB: tuple[str, str] = ("fire", "skip")


@dataclass(frozen=True)
class ActivationOption:
    """One candidate row of the ``ACTIVATE`` Slate (§1.4: a row of
    ``Slate.handles`` + its ``roles_ok`` type mask): the world Handle, the
    ability's index in the attached compiled record (the ``ABILITY:PTR``
    target), the typed IR object itself (§8.3), and the folded payment.
    Target/COST_TARGET slots are queried per slot (legal_targets) — an
    option never stores a cross-slot product."""

    source: Handle
    ability_idx: int
    ability: ActivatedAbility
    payment: PaymentPlan

    def order_key(self) -> tuple[Handle, int]:
        return (self.source, self.ability_idx)


@dataclass(frozen=True)
class TargetSlot:
    """The per-slot answer for one ``TARGET:PTR x n`` field (§1.3): the
    Selector IR (identity), the Handle-sorted candidate population, the
    legal cardinality range, and §1.4's ``forced`` flag (exactly one legal
    filler — the auto-resolve lever).

    Cardinality semantics (C17, Selector docstring):

    * ``TARGET`` + ``QConst(n)``   — exactly n (min = max = n);
    * ``TARGET`` + ``QAtMost(n)``  — DESIGNATION is 1..n (min 1: it is
      still targeted; C17), resolution clamps 0..remaining later;
    * ``TARGET`` + ``QAtLeast(n)`` — n..candidates ("one or more");
    * ``CHOOSE`` (up-to)           — 0..min(n, candidates): a resolution-
      time choice, so the EMPTY selection is legal (contrast the C17 pin
      above — the tests pin both zeros);
    * ``ALL``                      — the whole population, forced;
    * ``RANDOM``                   — engine-side: forced for the player
      (the seeded rng picks at resolution, never a model decision);
    * ``ONE_OF``                   — exactly 1 of the partition population;
    * ``REST``                     — the remainder: forced (engine takes
      everything the ONE_OF pick left — :func:`rest_of`)."""

    selector: Selector
    candidates: tuple[Handle, ...]
    min_count: int
    max_count: int
    forced: bool
    #: 14b (B-5/B-8): True for the SYNTHESIZED player-coordinate slot of a
    #: "target opponent" TARGET_PLAYER ControllerRef (no compiled Selector
    #: exists — the grammar gap). The candidate population (opponent seats)
    #: comes from the ENGINE's own CR rule, so no caller mirrors it.
    synthetic: bool = False


@dataclass(frozen=True)
class OptionChoice:
    """One legal OPTION-set of a ``Choose`` node (§1.3 ``OPTION:PTR*`` /
    RESOLVE_CHOICE ``CHOICE_OPTION:PTR``): the Choose IR (identity) and
    the ascending tuple of option indices; the typed option effects are
    ``choose.options[i]`` — the same objects apply_effect dispatches
    (§8.3). Executing a choice = ``executor.apply_effect`` on the chosen
    option subtree(s) directly, or (12d) dispatching the Choose NODE with
    a decision token.

    ORDER CONTRACT (12d-pinned): the runtime decision token for a Choose
    is ``str(i)`` where ``i`` is the position of the chosen OptionChoice
    in THIS module's enumeration order — size-ascending, index-lex
    (:func:`choose_options`). ``choose_options`` is the single source of
    both the Slate's OPTION slots and the executor's decision vocabulary;
    the runtime dispatches exactly what the query enumerated (pinned in
    test_executor_layers.py)."""

    choose: Choose
    option_idxs: tuple[int, ...]

    @property
    def options(self) -> tuple[Effect, ...]:
        return tuple(self.choose.options[i] for i in self.option_idxs)


# ------------------------------------------------------------ activations


def legal_activations(
    world: GameWorld, executor: Executor, seat: Handle
) -> list[ActivationOption]:
    """Every activation available to ``seat`` right now, Handle-sorted by
    (source, ability_idx) (§5.5; ruling 5) — the ``ACTIVATE`` field's
    candidate rows. Scans ``seat``'s battlefield permanents that carry an
    attached compiled record (the 12b oracle-id bridge) and keeps the
    :class:`ActivatedAbility` nodes whose gate triple
    (window/condition/cost — legality.ability_playable) is green.

    12d: GRANTED activated abilities (round-12d GRANT_ABILITY layers) are
    rows too — addressed by NEGATIVE index ``-k-1`` = entry ``k`` of
    ``executor.layers.granted_activated(source)`` (layer-seq order), so a
    Slate row can name a granted ability without a compiled record (the
    granted object may be a token). The final row list is sorted on the
    same documented ``order_key``: for one source, granted rows (-k)
    precede printed rows (0+), each internally ascending.

    A cost kind the executor cannot check (CostLoyalty, QX amounts)
    RAISES through the scan — flag, don't degrade: a hole in the legality
    oracle must crash the query, never silently shrink the option set
    (the mask oracle's bugs are silent, §8; this is the loud half)."""
    options: list[ActivationOption] = []
    for handle in sorted(executor.binder.handle_record):
        if handle not in world.cards:
            continue
        if executor.controller_of(handle) != seat:  # 16e overlay-aware
            continue
        if world.zone_of(handle).kind != "battlefield":
            continue
        record = executor.binder.handle_record[handle]
        for idx, ability in enumerate(record.abilities):
            if not isinstance(ability, ActivatedAbility):
                continue
            if ability_playable(world, executor, handle, idx, seat=seat) is not None:
                continue
            ctx = ctx_for(executor, source=handle, controller=seat)
            plan, _ = build_payment_plan(world, ctx, ability.cost)
            assert plan is not None  # ability_playable just greenlit
            options.append(
                ActivationOption(
                    source=handle, ability_idx=idx, ability=ability, payment=plan
                )
            )
    # 12d granted rows (see docstring): every battlefield permanent of the
    # seat — compiled record or not (tokens activate what they're granted).
    for handle in sorted(world.cards):
        if executor.controller_of(handle) != seat:  # 16e overlay-aware
            continue
        if world.zone_of(handle).kind != "battlefield":
            continue
        for k, entry in enumerate(executor.layers.granted_activated(handle)):
            idx = -k - 1
            # granted_activated filters to ActivatedAbility; the isinstance
            # re-checks the registry's -k-1 basis contract (see legality).
            node = entry.node
            assert isinstance(node, ActivatedAbility)
            if ability_playable(world, executor, handle, idx, seat=seat) is not None:
                continue
            ctx = ctx_for(executor, source=handle, controller=seat)
            plan, _ = build_payment_plan(world, ctx, node.cost)
            assert plan is not None  # ability_playable just greenlit
            options.append(
                ActivationOption(
                    source=handle, ability_idx=idx, ability=node, payment=plan
                )
            )
    options.sort(key=lambda o: o.order_key())
    return options


# --------------------------------------------------------------- targets


def legal_targets(
    world: GameWorld,
    executor: Executor,
    selector: Selector,
    *,
    source: Handle,
    controller: Handle,
    bindings: dict[str, Binding] | None = None,
) -> TargetSlot:
    """The per-slot candidate list + legal cardinality for one Selector
    (§1.3 ``TARGET:PTR x n``). See :class:`TargetSlot` for the per-mode
    range table (C17's declaration-1..n vs resolution-0..n live here)."""
    from MTG_bot.core.executor.legality import enumerate_candidates

    ctx = ctx_for(executor, source=source, controller=controller, bindings=bindings)
    candidates = tuple(enumerate_candidates(selector, ctx))
    n = len(candidates)
    mode = selector.mode
    forced = False
    if mode is SelectorMode.ALL:
        min_count, max_count, forced = n, n, True
    elif mode is SelectorMode.RANDOM:
        want = (
            n
            if isinstance(selector.count, QUnbounded)
            else resolve(selector.count, ctx)
        )
        min_count = max_count = min(want, n)
        forced = True  # the seeded rng designates, not the model
    elif mode is SelectorMode.ONE_OF:
        min_count, max_count = 1, min(1, n)  # n=0 → infeasible (max<min)
        forced = n == 1
    elif mode is SelectorMode.REST:
        # The remainder after the ONE_OF pick: count ignored (like ALL),
        # engine-side complement — see rest_of().
        min_count, max_count, forced = n, n, True
    elif mode is SelectorMode.TARGET:
        count = selector.count
        if isinstance(count, QAtMost):
            # C17: the DESIGNATION range is 1..n — an empty population
            # leaves the slot infeasible (min 1 > max 0), which is the
            # whole point of the pin: 0 is NOT a legal TARGET declaration.
            min_count = 1
            max_count = min(count.n, n)
        elif isinstance(count, QAtLeast):
            min_count, max_count = count.n, n
        elif isinstance(count, QConst):
            # exact designation: min = max = k even past the population —
            # an under-populated TARGET slot is simply infeasible (any
            # selection fails validation); resolution clamping is QAtMost
            # territory only.
            min_count = max_count = count.value
            forced = count.value == n  # unique filler = whole population
        else:
            want = resolve(count, ctx)  # QX raises cleanly (X_VALUE)
            min_count = max_count = want
            forced = want == n
    else:  # CHOOSE — up-to, resolution-time, the EMPTY set is legal
        count = selector.count
        if isinstance(count, QUnbounded):
            min_count, max_count = 0, n
        elif isinstance(count, QAtLeast):
            min_count, max_count = count.n, n
        else:
            want = resolve(count, ctx)
            min_count, max_count = 0, min(want, n)
        forced = max_count == 0  # nothing offerable: no decode step (§1.4)
    return TargetSlot(
        selector=selector,
        candidates=candidates,
        min_count=min_count,
        max_count=max_count,
        forced=forced,
    )


def legal_search(
    world: GameWorld,
    executor: Executor,
    node: Atom | Selector,
    *,
    seat: Handle,
) -> tuple[Handle, ...]:
    """The SEARCH offer surface (13a): the candidate set one SEARCH atom's
    ``cards`` role may designate — the same enumeration
    :func:`MTG_bot.core.executor.verbs._search_designation` resolves at
    effect time, so the query and the handler can never disagree about what
    was searchable (§8.3 identity). Handle-sorted (ruling 5), card-namespace
    only. ``node`` is the SEARCH Atom or its ``cards`` Selector directly."""
    from MTG_bot.core.executor.legality import enumerate_candidates

    selector = node.args.get("cards") if isinstance(node, Atom) else node
    if not isinstance(selector, Selector):
        # ValueError, not TypeError: "no offerable search" is the domain
        # answer this query surface gives for a malformed node.
        raise ValueError(  # noqa: TRY004
            f"legal_search: no cards selector on {node!r}"
        )
    ctx = ctx_for(executor, source=seat, controller=seat)
    return tuple(
        sorted(h for h in enumerate_candidates(selector, ctx) if h.namespace == "card")
    )


def validate_target_selection(slot: TargetSlot, chosen: Sequence[Handle]) -> str | None:
    """Whole-legality of one selection against its slot: no duplicates,
    every handle from the candidate population, cardinality inside the
    slot's C17/legal range, and the list in canonical Handle-sort (§5.5 —
    the canonicalisation is a bijection, so an unsorted emission is a
    different token for the same set: illegal at the Slate). ``None`` when
    legal, else the machine reason."""
    seq = list(chosen)
    if len(set(seq)) != len(seq):
        return "selection:duplicate_handles"  # checked BEFORE sort order:
    # a repeated handle is also a sort violation, and the duplicate reason
    # is the informative one (ruling 5: handles are strictly ordered).
    if any(seq[i] >= seq[i + 1] for i in range(len(seq) - 1)):
        return "selection:not_canonically_sorted"
    population = set(slot.candidates)
    for handle in seq:
        if handle not in population:
            return f"selection:off_population:{handle}"
    if len(seq) < slot.min_count:
        return f"selection:count_below_min:{len(seq)}<{slot.min_count}"
    if len(seq) > slot.max_count:
        return f"selection:count_above_max:{len(seq)}>{slot.max_count}"
    return None


def rest_of(slot: TargetSlot, one_of_pick: Handle) -> tuple[Handle, ...]:
    """The REST partition of a ONE_OF/REST split, given the pick — the
    deterministic complement (§5.5-sorted), i.e. everything the exactly-1
    choice left ("put one of them in your hand, the rest into your
    graveyard")."""
    return tuple(h for h in slot.candidates if h != one_of_pick)


# --------------------------------------------------------------- options


def _choice_bounds(choose: Choose, ctx) -> tuple[int, int]:
    count = choose.count
    k_options = len(choose.options)
    if isinstance(count, QAtMost):
        return 0, min(count.n, k_options)  # CHOOSE-side up-to: 0 allowed
    if isinstance(count, QAtLeast):
        return min(count.n, k_options), k_options
    if isinstance(count, QUnbounded):
        return 0, k_options
    want = resolve(count, ctx)  # QConst path; QX raises cleanly (X_VALUE)
    return min(want, k_options), min(want, k_options)


def choose_options(
    executor: Executor,
    choose: Choose,
    *,
    source: Handle,
    controller: Handle,
    bindings: dict[str, Binding] | None = None,
) -> list[OptionChoice]:
    """EVERY legal option SET of a ``Choose`` node (C15 completeness; the
    ``OPTION:PTR*`` / ``CHOICE_OPTION`` slots of §1.3): all k-subsets for
    k in the node's legal range, canonicalised size-ascending then
    index-lex (§5.5 bijection). ``Choose`` + ``QAtMost`` includes the EMPTY
    set (resolution-time CHOOSE semantics — the option-set counterpart of
    the C17 resolution clamp); ``QConst(1)`` gives exactly the n printed
    options ('Choose one — A; B' → 2).

    An EMPTY-set choice consumes the skip path: dispatching zero option
    subtrees IS the no-op the rules call 'chose nothing'."""
    ctx = ctx_for(executor, source=source, controller=controller, bindings=bindings)
    lo, hi = _choice_bounds(choose, ctx)
    out: list[OptionChoice] = []
    for k in range(lo, hi + 1):
        for combo in itertools.combinations(range(len(choose.options)), k):
            out.append(OptionChoice(choose=choose, option_idxs=combo))
    return out


def optional_offer(
    executor: Executor,
    effect: OptionalEffect,
    *,
    source: Handle,
    controller: Handle,
    bindings: dict[str, Binding] | None = None,
) -> tuple[str, ...]:
    """The two-way may-offer as decision tokens — ``("fire", "skip")``
    when firing is actionable, narrowed to ``("skip",)`` when the inner
    action CANNOT be performed (a 'you may discard a card' with an empty
    hand: CR 117.3 — no resources, no action; the offer stays enumerable,
    just one-way that turn). Consumed by the 12a decision channel in tree
    order (C15), the same vocab binding.py's may-offers drain (§fire/skip).

    Actionability is deliberately narrow: only exact-count selector roles
    (TARGET/CHOOSE/RANDOM with a concrete count) gate the offer — a
    mandatory-count action with too few candidates. ALL-mode and pure
    numeric actions are always actionable (doing an empty ALL is a legal
    no-op, e.g. scrying with a bare library)."""
    from MTG_bot.core.executor.legality import enumerate_candidates

    if not isinstance(effect, OptionalEffect):
        # ValueError per the executor's validation convention (see
        # apply_effect's tree-shape gate): a wrong SHAPE into a query is a
        # contract misuse, surfaced loudly, not a silent empty offer.
        raise ValueError(  # noqa: TRY004
            f"optional_offer: needs an OptionalEffect, got {type(effect).__name__}"
        )
    ctx = ctx_for(executor, source=source, controller=controller, bindings=bindings)
    # 13b: a PAY atom is the other unactionable-action shape — "You may pay
    # {2}" with an empty pool offers only skip (CR 117.3: no resources, no
    # action), and _v_pay RAISES if a 'fire' decision ever reaches an
    # unpaid cost, so the offer MUST narrow first (query/runtime identity).
    for node in walk(effect.inner):
        if isinstance(node, Atom) and node.verb is Verb.PAY:
            pay_cost = node.args.get("cost")
            if isinstance(pay_cost, Cost):
                plan, _why = build_payment_plan(executor.world, ctx, pay_cost)
                if plan is None:
                    return MAY_VOCAB[1:]
    for node in walk(effect.inner):
        if not isinstance(node, Atom):
            continue
        for role in ("cards", "target"):
            value = node.args.get(role)
            if not isinstance(value, Selector):
                continue
            if value.mode not in (
                SelectorMode.TARGET,
                SelectorMode.CHOOSE,
                SelectorMode.RANDOM,
            ):
                continue  # ALL / ONE_OF / REST: no exact-count gate here
            if isinstance(value.count, QUnbounded):
                continue
            want = resolve(value.count, ctx)
            if want <= 0:
                continue
            if len(enumerate_candidates(value, ctx)) < want:
                return MAY_VOCAB[1:]
    return MAY_VOCAB


# ------------------------------------------------------------------ casting


@dataclass(frozen=True)
class CastOption:
    """One row of the 13b ``CAST``/``PLAY_LAND`` decision surface — the
    SAME object ``legal_casts`` enumerates and ``stack.cast``/
    ``stack.play_land`` re-check (§8.3 identity: query answer and legality
    oracle are one computation, never two that can disagree).

    Two shapes share this row type because they share the Slate field
    (§1.4's CAST decision covers the land drop — both are "put a card
    from hand into play", and C15 demands BOTH be enumerable on one
    surface, or the model sees a hidden action):

    * spell row — ``land=False``: the :class:`SpellAbility` node (IR
      identity, §8.3), the compiled 601.2f cost fold in ``payment``
      (X enumerated at its documented 0-floor witness when the caller
      passed no ``x``), and the handle;
    * land row — ``land=True``: ``node=None, payment=None`` — a land has
      no SpellAbility node and no cost (CR 305.1 special action), and
      modelling it as ``payment=empty`` would pretend at a cost fold
      that does not exist.

    ``order_key`` is the bare Handle: rows sort Handle-first (ruling 5),
    spells and lands interleaved by their card handle — the world's own
    object order, stable across replays."""

    handle: Handle
    node: SpellAbility | None
    land: bool
    payment: PaymentPlan | None

    def order_key(self) -> Handle:
        return self.handle


def legal_casts(
    world: GameWorld, executor: Executor, seat: Handle, *, x: int | None = None
) -> list[CastOption]:
    """Every card ``seat`` may put into play from hand RIGHT NOW — spells
    via :func:`legality.spell_castable` (window + cost fold), lands via
    :func:`stack.land_playable` (the CR 305.1 special action, its own
    option SHAPE on the same surface — C15: the land drop must not be a
    hidden action). PURE: world read-only, no journal write, no rng —
    pre-cast enumeration of the total cost (601.2f) is a QUERY, exactly
    as ``legal_activations`` is; the cast itself RE-checks.

    X handling (12c's X_VALUE field folded): with ``x=None`` a QX spell is
    enumerated on the documented **X=0 witness** (a legal declaration, CR
    107.1) so the row stays enumerable; pass ``x=k`` to ask "is it
    castable declaring X=k" — the row's payment then folds {X}=k, and a
    too-big k disappears the row (shortage reason, never a raise).

    A cost the executor cannot check at all (e.g. a loyalty COST on a
    spell) RAISES through the scan — the loud-half convention of
    ``legal_activations``: a hole in the legality oracle must crash the
    query, never silently shrink the option set."""
    from MTG_bot.core.executor.stack import is_land_card, land_playable

    rows: list[CastOption] = []
    hand = world.players[seat].zone("hand").entries
    for handle in sorted(hand):
        if land_playable(executor, seat, handle) is None:
            rows.append(CastOption(handle=handle, node=None, land=True, payment=None))
            continue
        if not is_land_card(world, handle):
            reason, node, _record, plan = spell_castable(executor, seat, handle, x=x)
            if reason is None and node is not None and plan is not None:
                rows.append(
                    CastOption(handle=handle, node=node, land=False, payment=plan)
                )
    rows.sort(key=CastOption.order_key)
    return rows


def spell_target_slots(
    executor: Executor,
    node: SpellAbility,
    *,
    spell_handle: Handle,
    seat: Handle,
) -> list[TargetSlot]:
    """The TARGET-selection slots of a SPELL's effect tree: every
    TARGET-mode Selector reachable under the SpellAbility's effect, as the
    SAME per-slot :class:`TargetSlot` the activation surface returns
    (§8.3 identity — one slot type, one validation oracle for every
    ability in the game). Coordinates: ``source`` = the spell card itself
    (601.2c designates about the spell), ``controller`` = the caster.

    "Any target" widening (CR 109.5): a Zone(ANY) selection also names
    PLAYERS — the frozen card-only enumeration cannot know a DEAL_DAMAGE
    target may be a player, so for a universal-filtered ANY selector the
    player seats join the candidate population (a NON-universal filter
    cannot be evaluated against a player handle — the predicate would
    crash on ``world.cards[player]`` — so those selectors stay
    card-only, which is also the rules answer: "target creature" excludes
    players anyway).

    The corpus' "target opponent" (Duress) compiles to a TARGET_PLAYER
    ControllerRef with NO Selector. 14b (B-8/B-5 fix): that coordinate now
    gets a SYNTHESIZED slot — the opponent-seat population comes from the
    ENGINE's own player rule (exactly the one
    ``stack._validate_spell_targets`` re-checks, which stays the oracle),
    so a caller designates from a QUERY instead of mirroring the CR rule
    (/03 row B-5 mirror #4, deleted)."""
    slots: list[TargetSlot] = []
    seen: set[str] = set()
    if node.effect is None:
        return slots
    reads_target_player = False
    for inner in walk(node.effect):
        if not isinstance(inner, Atom):
            continue
        for _role, value in inner.args.pairs:
            if (
                value is ControllerRef.TARGET_PLAYER
                or isinstance(value, Zone)
                and value.controller is ControllerRef.TARGET_PLAYER
            ):
                reads_target_player = True
            if not isinstance(value, Selector) or value.mode is not SelectorMode.TARGET:
                continue
            key = repr(value)
            if key in seen:
                continue
            seen.add(key)
            slot = legal_targets(
                executor.world,
                executor,
                value,
                source=spell_handle,
                controller=seat,
            )
            widened = _widen_any_target(executor, value, slot)
            if widened is not None:
                slot = widened
            slots.append(slot)
    if not slots and not reads_target_player:
        # 16e (CR 702.5a): an AURA spell carries no TARGET-mode selector
        # (its effect reads IS_ATTACHED_TO_SOURCE, not a designation) —
        # yet the cast REQUIRES an enchant target (CR 601.2c). The slot is
        # synthesized from the aura's own tree: the enchantment filter is
        # the co-located selector's filter minus the IS_ATTACHED_TO_SOURCE
        # atom, falling back to "any permanent you could put an aura on".
        aura = aura_enchant_slot(executor, node, spell_handle=spell_handle, seat=seat)
        if aura is not None:
            slots.append(aura)
    if reads_target_player:
        # 14b (B-8/B-5): the TARGET_PLAYER coordinate's designation slot —
        # the CR population the runtime REQUIRES (an opponent seat of the
        # caster, the same rule _validate_spell_targets re-checks), now
        # answered by the query so no caller mirrors the rule.
        opponents = tuple(sorted(h for h in executor.world.player_order if h != seat))
        slots.append(
            TargetSlot(
                selector=Selector(
                    count=QConst(1),
                    mode=SelectorMode.TARGET,
                    filter=FAnd(()),
                    zone=Zone(ZoneKind.PLAYER, ControllerRef.TARGET_PLAYER),
                ),
                candidates=opponents,
                min_count=1,
                max_count=1,
                forced=len(opponents) == 1,
                synthetic=True,
            )
        )
    return slots


def _is_universal(filter_: object) -> bool:
    from MTG_bot.core.ability_tree import FAnd

    return isinstance(filter_, FAnd) and len(filter_.children) == 0


def _widen_any_target(
    executor: Executor, selector: Selector, slot: TargetSlot
) -> TargetSlot | None:
    """Players join an ANY-zone universal-filter target (see
    :func:`spell_target_slots`); None means "no widening applies"."""
    zones = [selector.zone, *selector.zones]
    if not any(z.kind is ZoneKind.ANY for z in zones):
        return None
    if not _is_universal(selector.filter):
        return None
    world = executor.world
    players = {h for h in world.players}
    if players & set(slot.candidates):
        return None
    candidates = tuple(sorted(set(slot.candidates) | players))
    forced = slot.forced
    if isinstance(selector.count, QConst):
        forced = selector.count.value == len(candidates)
    return TargetSlot(
        selector=slot.selector,
        candidates=candidates,
        min_count=slot.min_count,
        max_count=slot.max_count,
        forced=forced,
    )


def is_aura_spell(world: GameWorld, handle: Handle) -> bool:
    """16e: the ENCHANT keyword (CR 702.5) is the aura marker — every
    compiled aura in the corpus carries it (Enthralling Hold golden), and
    no non-aura does (equipment carry EQUIP, not ENCHANT)."""
    state = world.cards.get(handle)
    if state is None:
        return False
    # identity.keywords are the KEYWORD-ENUM NAMES as plain strings (the
    # one conversion is games.identity_of); the layers oracle reads them
    # the same way.
    return "ENCHANT" in state.identity.keywords


def _strip_attached(filter_: object) -> FAnd | None:
    """Split a selector filter around the IS_ATTACHED_TO_SOURCE atom: None
    means "this filter says nothing about being attached to the source";
    otherwise the returned FAnd is what an ENCHANTABLE candidate must
    satisfy (the enchantment filter, minus the self-reference the aura
    cannot check before it is attached). v1 shape: the atom sits at the
    top level or inside a top-level FAnd (the compiled aura idiom); any
    deeper nesting falls back to the unrestricted permanent population."""
    if isinstance(filter_, FAtom):
        return FAnd(()) if filter_.pred is FAtomPred.IS_ATTACHED_TO_SOURCE else None
    if isinstance(filter_, FAnd):
        keep = [
            c
            for c in filter_.children
            if not (isinstance(c, FAtom) and c.pred is FAtomPred.IS_ATTACHED_TO_SOURCE)
        ]
        if len(keep) == len(filter_.children):
            return None
        return FAnd(tuple(keep))
    return None


def aura_enchant_slot(
    executor: Executor,
    node: SpellAbility,
    *,
    spell_handle: Handle,
    seat: Handle,
) -> TargetSlot | None:
    """The synthesized exactly-1 ENCHANT slot of an aura spell (16e), or
    None for a non-aura. The host population comes from the aura's own
    effect tree: the first selector whose filter co-names
    IS_ATTACHED_TO_SOURCE contributes its remaining filter (Enthralling
    Hold: TYPE_EQ Creature); with no such selector the corpus fallback is
    any permanent on the battlefield. The aura itself is never a
    candidate (CR 702.5c "another object")."""
    world = executor.world
    if not is_aura_spell(world, spell_handle):
        return None
    enchant_filter: FAnd | None = None
    if node.effect is not None:
        for inner in walk(node.effect):
            if not isinstance(inner, Atom):
                continue
            for _role, value in inner.args.pairs:
                if not isinstance(value, Selector):
                    continue
                stripped = _strip_attached(value.filter)
                if stripped is not None and (
                    enchant_filter is None or len(stripped.children) > 0
                ):
                    enchant_filter = stripped
                    break
            if enchant_filter is not None and len(enchant_filter.children) > 0:
                break
    selector = Selector(
        count=QConst(1),
        mode=SelectorMode.TARGET,
        filter=enchant_filter if enchant_filter is not None else FAnd(()),
        zone=Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),
    )
    slot = legal_targets(
        world,
        executor,
        selector,
        source=spell_handle,
        controller=seat,
    )
    candidates = tuple(h for h in slot.candidates if h != spell_handle)
    return TargetSlot(
        selector=selector,
        candidates=candidates,
        min_count=1,
        max_count=1,
        forced=len(candidates) == 1,
        synthetic=True,
    )


def verb_choose_options(
    executor: Executor,
    atom: Atom,
    *,
    source: Handle,
    controller: Handle,
    bindings: dict[str, Binding] | None = None,
) -> tuple[tuple[Handle, ...], ...]:
    """The enumerable picks of a ``Verb.CHOOSE`` atom (Duress/Kitesail's
    "You choose a card from it"): the candidate pool resolved through the
    SAME machinery the runtime handler uses (§8.3 identity), one singleton
    row per candidate in Handle order. The handler's decision vocabulary
    is ``str(i)`` into THIS order — the same ORDER contract ``choose_
    options`` pins for Choose NODES (12d), extended to the atom.

    v1 scope is the corpus shape: a single pick (every compiled CHOOSE
    atom carries ``count = QConst(1)``). An under-filled pool makes the
    EMPTY row legal too (choosing nothing from fewer candidates than
    demanded is the C17-clamp sibling); a MULTI-pick CHOOSE atom raises —
    combination-order for its tokens is a later round, and the corpus has
    zero rows needing it (flag, don't degrade)."""
    from MTG_bot.core.executor.legality import enumerate_candidates

    selector = atom.args.get("target")
    if not isinstance(selector, Selector):
        raise TypeError(f"verb_choose_options: no target selector on {atom!r}")
    # 14a B-8a: the caller's bindings ride along. Without them a CHOOSE atom
    # whose pool is scoped to the spell's target — Duress's "You choose a card
    # from it" reads Zone(HAND, TARGET_PLAYER) — rebuilt a context with no
    # target and raised 'TARGET_PLAYER needs a bound target' INSIDE the runtime
    # handler that was holding the binding. Defaulting to None keeps every
    # pre-14a caller byte-identical.
    ctx = ctx_for(executor, source=source, controller=controller, bindings=bindings)
    # enumerate_candidates, NOT resolve_selector: the CHOOSE-mode resolver
    # applies its 12a deterministic-first-n stand-in (it returns the
    # DESIGNATION), which would clamp the pool to one row before ANY
    # choice exists. The query enumerates the filtered POPULATION; the
    # handler then consumes the player's pick and writes it to 'result'.
    pool = sorted(set(enumerate_candidates(selector, ctx)))
    count_role = atom.args.get("count")
    if count_role is not None:
        assert isinstance(count_role, Quantity)  # role table: count is a Quantity
    want = 1 if count_role is None else resolve(count_role, ctx)
    if want != 1:
        raise NotImplementedError(
            "executor: Verb.CHOOSE multi-pick enumeration is a later round "
            f"(count={count_role!r}); the corpus compiles count=1 only"
        )
    if not pool:
        return ((),)
    rows: list[tuple[Handle, ...]] = [(h,) for h in pool]
    rows.append(())  # the legal under-filled zero (C17 clamp sibling)
    return tuple(rows)
