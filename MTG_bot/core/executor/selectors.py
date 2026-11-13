"""Zone/selector/target resolution for the executor.

The single mapping from IR designation to concrete handles:

  * ``players_for_ref`` — a ControllerRef -> the player seats it denotes;
  * ``enumerate_zone`` — a Zone IR -> its handles in **zone order** (the
    designated order-preserving slot; top of library = last entry);
  * ``resolve_selector`` — a Selector IR -> handles, per mode (see its
    docstring);
  * the role helpers (``role_handles``/``role_player``/``role_players``/
    ``amount``) read one Atom's roles off that machinery.

An unsupported designation (OWNER-scoped selector enumeration, a referent
outside the closed strings) RAISES: flag, don't degrade. CHOOSE takes
min(count, candidates).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from MTG_bot.core.ability_tree import (
    DESIGNATED_PLAYER_REFS,
    Atom,
    ControllerRef,
    Cost,
    FAnd,
    FAtom,
    FAtomPred,
    FNot,
    FOr,
    QAtMost,
    QConst,
    Quantity,
    QUnbounded,
    Selector,
    SelectorMode,
    Verb,
    Zone,
    ZoneKind,
    ZonePosition,
    count_semantics,
)
from MTG_bot.core.executor.decisions import site_digest
from MTG_bot.core.executor.quantity import (
    ExecCtx,
    eval_filter,
    last_known,
    phased_out,
    resolve,
)
from MTG_bot.core.identity import Handle
from MTG_bot.core.state import (
    PLAYER_ZONES,
    ZONE_BATTLEFIELD,
    ZONE_COMMAND,
    ZONE_EXILE,
    ZONE_GRAVEYARD,
    ZONE_HAND,
    ZONE_LIBRARY,
)

# ZoneKind enum member -> the state.py zone-kind string.
ZONE_KIND_TO_STATE: dict[ZoneKind, str] = {
    ZoneKind.LIBRARY: ZONE_LIBRARY,
    ZoneKind.HAND: ZONE_HAND,
    ZoneKind.BATTLEFIELD: ZONE_BATTLEFIELD,
    ZoneKind.GRAVEYARD: ZONE_GRAVEYARD,
    ZoneKind.EXILE: ZONE_EXILE,
    ZoneKind.COMMAND: ZONE_COMMAND,
}


def _opponents(ctx: ExecCtx) -> list[Handle]:
    controller = ctx.controller
    return [p for p in ctx.world.player_order if p != controller]


def controller_of(ctx: ExecCtx, handle: Handle) -> Handle:
    """The EFFECTIVE controller of a card: the executor's GAIN_CONTROL
    overlay wins over the zone-owner read. A bare ExecCtx (no executor) has
    no overlay and reads the zone owner."""
    ex = ctx.executor
    if ex is None:
        return ctx.world.controller_of(handle)
    return ex.controller_of(handle)


def apnap_order(world: object, players: list[Handle]) -> list[Handle]:
    """``players`` in APNAP order (CR 101.4): the active player first, then the others in turn
    order. Seat order when no turn is open."""
    order = list(world.player_order)  # type: ignore[attr-defined]
    active = getattr(world, "active_player", None)
    if active in order:
        start = order.index(active)
        order = order[start:] + order[:start]
    return [p for p in order if p in players]


def sacrificing_player(ctx: ExecCtx, menu: list[Handle]) -> Handle:
    """The player who picks from a sacrifice menu.

    CR 701.21a: a player can sacrifice only a permanent they control, so the menu of one
    sacrifice instruction belongs to one player, and that player chooses (CR 101.4's example:
    "Each player sacrifices a creature" — each player chooses a creature they control). The
    templates pin whose permanents through the filter (CONTROLLER_IS YOU, rotated by EachPlayer,
    or TARGET_PLAYER). A menu spanning several controllers means the tree does not say who
    sacrifices: that raises rather than let one player pick another's permanent. An empty menu
    has no chooser; the context's controller stands in."""
    owners = sorted({controller_of(ctx, h) for h in menu})
    if len(owners) > 1:
        raise ValueError(
            f"executor: a sacrifice menu spans the permanents of {owners}: a player sacrifices "
            "only what they control (CR 701.21a), so the tree must say whose (CONTROLLER_IS)"
        )
    return owners[0] if owners else ctx.controller


def defending_players(ctx: ExecCtx) -> list[Handle]:
    """The defending player (CR 506.2), as a list: empty outside combat.

    CR 508.5 makes it, for an ability of an attacking creature or one that names an attacking
    creature, the player that creature attacks or the controller of the planeswalker it attacks.
    The engine's combat has one defending player, whom every attacker attacks, it or a
    planeswalker that player controls (``Executor.combat_attacks``), so that player is the
    answer for every attacking creature. A multiplayer combat would resolve it per creature
    (CR 508.5a) from ``Executor.attacked``."""
    if ctx.executor is None:
        raise ValueError("executor: the defending player needs an executor-backed ExecCtx")
    seat = ctx.executor.defending_player
    return [] if seat is None else [seat]


def player_slot_selector(ref: ControllerRef) -> Selector:
    """The selector of the player slot the query synthesizes for "target player"
    (TARGET_PLAYER) or "target opponent" (TARGET_OPPONENT) (``query.player_target_slot``): no
    compiled Selector carries that designation, so this one keys it in a designation of several
    slots (``ExecCtx.slot_designations``)."""
    return Selector(
        count=QConst(1),
        mode=SelectorMode.TARGET,
        filter=FAnd(()),
        zones=(Zone(ZoneKind.PLAYER, ref),),
    )


_PLAYER_SLOT_KEYS = frozenset(repr(player_slot_selector(ref)) for ref in DESIGNATED_PLAYER_REFS)


def designated_player(ctx: ExecCtx) -> list[Handle] | None:
    """What a designated-player read ("target player", "target opponent", their anaphora) is
    bound to: the designation, or in a designation of several slots the player slot's own. The
    union of the slots names the other slots' objects too, and its first handle may be a card
    (Sublime Epiphany's "Target player draws a card." beside "Return target nonland permanent to
    its owner's hand." drew for the permanent's controller). Empty when the designation was made
    and holds nothing now: the player became an illegal target beside a target still legal, so
    the spell resolves and that player's part does nothing (CR 608.2b). None when no designation
    was made at all."""
    for key, handles in (ctx.slot_designations or {}).items():
        if key in _PLAYER_SLOT_KEYS:
            return list(handles[:1])
    bound = ctx.binding_handles("target")
    return None if bound is None else bound[:1]


def players_for_ref(ref: ControllerRef, ctx: ExecCtx) -> list[Handle]:
    """The player seats a ControllerRef denotes, in seat order."""
    if ref is ControllerRef.YOU:
        return [ctx.controller]
    if ref is ControllerRef.DEFENDING_PLAYER:
        return defending_players(ctx)
    if ref in (ControllerRef.OPPONENT, ControllerRef.ALL_OPPONENTS):
        return _opponents(ctx)
    if ref is ControllerRef.ANY:
        return list(ctx.world.player_order)
    if ref in DESIGNATED_PLAYER_REFS:
        # "target player" and "target opponent" read the same binding;
        # they differ only in who could be designated (query/binding slots).
        bound = designated_player(ctx)
        if bound is None:
            raise ValueError(
                "executor: TARGET_PLAYER needs a bound target (12c target prompt)"
            )
        # CR 608.2h: a designated object that has left the battlefield ("that player" of
        # Massacre Wurm's dies trigger) answers with the controller it last had there.
        return [h if h.namespace == "player" else last_known_controller(ctx, h) for h in bound]
    raise NotImplementedError(
        f"executor: ControllerRef.{ref.name} has no player-side meaning here"
    )


def controller_matches(
    who: ControllerRef | Selector, actual: Handle, ctx: ExecCtx
) -> bool:
    """Did ``actual`` (a player handle) satisfy a CONTROLLER_IS ``who`` slot?"""
    if isinstance(who, Selector):
        # A referent Selector (e.g. the event subject's controller): resolve
        # the bound object(s) and compare their player side.
        candidates = resolve_selector(who, ctx)
        players = [
            c if c.namespace == "player" else controller_of(ctx, c) for c in candidates
        ]
        return actual in players
    if who is ControllerRef.YOU:
        return actual == ctx.controller
    if who is ControllerRef.DEFENDING_PLAYER:
        return actual in defending_players(ctx)
    if who in (ControllerRef.OPPONENT, ControllerRef.ALL_OPPONENTS):
        return actual != ctx.controller
    if who in DESIGNATED_PLAYER_REFS:
        bound = designated_player(ctx) or []
        return actual in [h if h.namespace == "player" else controller_of(ctx, h) for h in bound]
    return who is ControllerRef.ANY


def filter_bound_player_refs(filter_: object) -> set[ControllerRef]:
    """The designated-player refs (TARGET_PLAYER / TARGET_OPPONENT) a Filter
    reads through ``CONTROLLER_IS``, so a designation slot knows whether it is
    "target player" (any player) or "target opponent". A BATTLEFIELD seat is
    expressed ONLY as this atom (zone=BF-ANY + ``FAtom(CONTROLLER_IS,
    TARGET_PLAYER)``), so every designation scan (binding._designate, the query
    cast/activation lanes) must consult FILTERS, not just raw ControllerRef/Zone
    pair values. The query cast/activation lanes also open a player slot from a
    selector's zones (query._designated_player_refs): Tormod's Crypt's "Exile
    target player's graveyard" is a target (CR 115.1), not a container read."""
    if isinstance(filter_, FAtom):
        found: set[ControllerRef] = set()
        if (
            filter_.pred is FAtomPred.CONTROLLER_IS
            and filter_.who in DESIGNATED_PLAYER_REFS
        ):
            found.add(filter_.who)  # type: ignore[arg-type]
        for inner in (filter_.inner_filter, filter_.right_inner_filter):
            if inner is not None:
                found |= filter_bound_player_refs(inner)
        return found
    if isinstance(filter_, (FAnd, FOr)):
        out: set[ControllerRef] = set()
        for child in filter_.children:
            out |= filter_bound_player_refs(child)
        return out
    if isinstance(filter_, FNot):
        return filter_bound_player_refs(filter_.inner)
    return set()


def zone_owner(ctx: ExecCtx, zone_ir: Zone, owner: Handle | None) -> Handle:
    """The single player who owns a destination/movement zone IR.

    ANY names no player, so it resolves to ``owner`` when the caller has one,
    never to the first seat (a bounce to "its owner's hand" compiles as
    Zone(HAND, ANY); the first seat would take an opponent's creature). A
    MOVING CARD's destination goes through :func:`move_destination`."""
    ref = zone_ir.controller
    if ref is ControllerRef.OWNER or (ref is ControllerRef.ANY and owner is not None):
        if owner is None:
            raise ValueError("executor: OWNER zone needs a card to own it")
        return owner
    if ref is ControllerRef.YOU:
        return ctx.controller
    if ref is ControllerRef.ANY or ref in DESIGNATED_PLAYER_REFS:
        return players_for_ref(ref, ctx)[0]
    raise NotImplementedError(
        f"executor: zone controller ref {ref.name} needs multiple owners (12b)"
    )


def move_destination(
    ctx: ExecCtx, dest_ir: Zone, dest_kind: str, card: Handle
) -> tuple[Handle, Handle | None]:
    """CR 108.3, 400.3, 110.2a: where a moving card lands, as ``(the player
    whose zone receives it, the player who controls it if that is not its owner)``.

    The world reads a card's owner off the zone that holds it, so filing a
    card under another player's zone would change its owner, which never happens
    (108.3). A card goes to its OWNER's hand, library or graveyard whatever player
    the destination names (400.3), and to its owner's slice of exile. Only a
    battlefield destination names a controller (110.2a): the player the effect puts
    it under, which is the effect's controller (YOU, and ANY: "return it to the
    battlefield" puts it under the instructed player's control), the designated
    player (TARGET_PLAYER), or its owner (OWNER). A controller other than the owner
    is the caller's control entry (Executor.gain_control), never a zone."""
    owner = ctx.world.controller_of(card)  # the zone owner IS the card's owner
    if dest_kind != ZONE_BATTLEFIELD:
        return owner, None
    ref = dest_ir.controller
    if ref is ControllerRef.OWNER:
        return owner, None
    if ref in (ControllerRef.YOU, ControllerRef.ANY):
        controller = ctx.controller
    elif ref is ControllerRef.TARGET_PLAYER:
        controller = players_for_ref(ref, ctx)[0]
    else:
        raise NotImplementedError(
            f"executor: battlefield destination under {ref.name} names no single "
            "controller (CR 110.2a)"
        )
    return owner, (None if controller == owner else controller)


def enumerate_zone(ctx: ExecCtx, zone_ir: Zone) -> list[Handle]:
    """The handles in one Zone IR, in **zone order** (order-preserving)."""
    kind = zone_ir.kind
    if kind is ZoneKind.PLAYER:
        return players_for_ref(zone_ir.controller, ctx)
    ref = zone_ir.controller
    if ref is ControllerRef.OWNER:
        # Every card zone raises on OWNER at runtime (the QUERY side answers
        # OWNER via legality.source_owner).
        raise NotImplementedError(
            "executor: OWNER in selector enumeration needs per-candidate "
            "owner scoping (12b)"
        )
    if kind is ZoneKind.ANY:
        # Zone(ANY) at RUNTIME: the same seat-order × PLAYER_ZONES loop
        # legality._zone_handles runs for the QUERY side, so query and
        # runtime enumerate one population for the "any target"/"any zone"
        # selectors that compile this way (Meteorite, Terror of the Peaks).
        # The controller ref is deliberately NOT a filter here: ANY spans
        # every player's zones. HIDDEN zones (libraries, the opponent's
        # hand) ride along: the executor is omniscient.
        handles_all: list[Handle] = []
        for player in ctx.world.player_order:
            for any_kind in PLAYER_ZONES:
                handles_all.extend(ctx.world.players[player].zone(any_kind).entries)
        return existing(ctx, handles_all)
    if kind is ZoneKind.STACK:
        # ZONE_KIND_TO_STATE has no STACK entry: each seat's parked frames
        # are enumerated through :func:`stack.stack_zone` (the per-player
        # ZONE_STACK slot created on first use), the SAME source the query
        # side reads, so query and runtime enumerate one population. TOP =
        # the last entry = the top frame (LIFO order-preserving, the stack's
        # own convention). The player's abilities on the stack follow its spells
        # (stack.stack_abilities).
        from MTG_bot.core.executor.stack import stack_abilities, stack_zone

        stack_handles: list[Handle] = []
        for player in players_for_ref(ref, ctx):
            entries = stack_zone(ctx.world, player).entries
            position = zone_ir.position
            if position is ZonePosition.TOP:
                stack_handles.extend(entries[-1:])  # top frame = last entry
            elif position is ZonePosition.BOTTOM:
                stack_handles.extend(entries[:1])  # bottom frame = first
            else:
                stack_handles.extend(entries)
                stack_handles.extend(stack_abilities(ctx.executor, player))
        return stack_handles
    state_kind = ZONE_KIND_TO_STATE[kind]
    handles: list[Handle] = []
    for player in players_for_ref(ref, ctx):
        entries = ctx.world.players[player].zone(state_kind).entries
        position = zone_ir.position
        if position is ZonePosition.TOP:
            handles.extend(entries[-1:])  # top of library = last entry
        elif position is ZonePosition.BOTTOM:
            handles.extend(entries[:1])
        else:
            handles.extend(entries)
    return existing(ctx, handles)


def existing(ctx: ExecCtx, handles: list[Handle]) -> list[Handle]:
    """CR 702.26b: a phased-out permanent is treated as though it does not
    exist, so no zone enumeration yields it: not a target, not an "each"
    population, not counted, not a cost candidate, not a static's scope.
    The ONE chokepoint every selector and query enumeration passes
    (``enumerate_zone`` here, ``legality._zone_handles`` for its own
    OWNER/ANY lanes). Order-preserving; free when nothing is phased out."""
    if ctx.executor is None or not ctx.executor.phased_out:
        return handles
    return [h for h in handles if not phased_out(ctx, h)]


def without_another_marker(filter_: object) -> object:
    """The filter beside the "another target" marker (templates_b5c's distinct-target
    encoding): FAnd(IS_ANY_TARGET, X) -> X; any other filter as it is."""
    if isinstance(filter_, FAnd) and len(filter_.children) == 2:
        rest = [
            c for c in filter_.children
            if not (isinstance(c, FAtom) and c.pred is FAtomPred.IS_ANY_TARGET)
        ]
        if len(rest) == 1:
            return rest[0]
    return filter_


def _is_any_target_idiom(filter_: object) -> bool:
    """Mirror of :func:`query._is_any_target_idiom`: the compiled
    printed-"any target" idiom, an FOr of exactly the three TYPE_EQ atoms
    ``Creature`` / ``Planeswalker`` / ``Player`` (the Player branch is the
    discriminator: no card matches it, and it separates this population
    from the printed "target creature or planeswalker" two-branch shape,
    which never denotes a player, CR 115.1d), alone or beside the "another
    target" marker ("other targets", Drakuseth). The twins are pinned equal by
    test_geyser_any_target_pins."""
    filter_ = without_another_marker(filter_)
    if not isinstance(filter_, FOr) or len(filter_.children) != 3:
        return False
    kinds = {
        (child.pred, child.string_value)
        for child in filter_.children
        if isinstance(child, FAtom)
    }
    return kinds == {
        (FAtomPred.TYPE_EQ, "Creature"),
        (FAtomPred.TYPE_EQ, "Planeswalker"),
        (FAtomPred.TYPE_EQ, "Player"),
    }


def _is_any_universal(sel: Selector) -> bool:
    """True for the "any target" IR shapes: the universal shape (an ANY-kind
    zone in the selector's zone SET with the empty FAnd filter) or the
    battlefield idiom (:func:`_is_any_target_idiom` over BATTLEFIELD zones
    only). This is query._player_widening_applies' twin predicate, shared
    here because the runtime TARGET legality set must widen over exactly the
    same population the query offers (CR 109.5)."""
    zones = sel.zones
    if bool(
        isinstance(sel.filter, FAnd)
        and not sel.filter.children
    ) and any(z.kind is ZoneKind.ANY for z in zones):
        return True
    return _is_any_target_idiom(sel.filter) and all(
        z.kind is ZoneKind.BATTLEFIELD for z in zones
    )


def _emit_partition_journal(
    ctx: ExecCtx, sel: Selector, chosen: list[Handle], journal_partition: bool
) -> None:
    """Journal the chosen set of a real ONE_OF/REST partition.

    The row verb is the selector mode itself, not ``TARGET``: branch
    coverage needs the chosen-cardinality evidence, while CR target
    triggers must stay silent for choices such as "put one of them into
    your hand". A bare test context without a journal emits nothing.
    """
    if not journal_partition or ctx.journal is None:
        return
    ctx.journal.emit_targeting(
        ctx.source, ctx.controller, chosen, cause_verb=sel.mode.name
    )


# The two dangling-anaphora refusals inside resolve_selector carry a
# DEDICATED TYPE, and the guard predicate (referent_absent) also requires
# the BYTE-EXACT site message. A substring mark would be unsafe twice over:
# an unrelated error whose text merely CONTAINS the mark would be silenced
# into the ledger, and a mark for the binding refusal also matches a third
# raise (quantity._referent_handle's QProp refusal) whose skip semantics
# are different. QProp and every other refusal therefore stay
# NON-skippable by construction.
_TARGET_BINDING_MSG = "executor: 'target' referent has no target binding"


def _no_register_msg(referent: str) -> str:
    return (
        f"executor: selector referent {referent!r} has no register — no "
        "trigger firing bound one and no producer atom wrote one in "
        "this execution"
    )


class ReferentAbsentError(Exception):
    """Base: resolve_selector's dangling-anaphora refusal (an unset
    designation / an unwritten register). Only these types, with the
    exact site message, may be skipped by the live-game guard."""


class ReferentAbsentBindingError(ReferentAbsentError, ValueError):
    """Unset ``target`` designation. A ValueError, so every caller and test
    that expects ValueError still catches it."""


class ReferentAbsentRegisterError(ReferentAbsentError, NotImplementedError):
    """Unwritten ``event``/``result`` register. A NotImplementedError, for
    the same reason."""

    def __init__(self, referent: str) -> None:
        super().__init__(_no_register_msg(referent))
        self.referent = referent


def referent_absent(exc: BaseException) -> bool:
    """True iff ``exc`` IS one of resolve_selector's two site errors —
    dedicated subclass AND byte-exact site message. Message-substring
    look-alikes, the QProp referent refusal and every other error return
    False (never skipped, never ledgered)."""
    if isinstance(exc, ReferentAbsentBindingError):
        return str(exc) == _TARGET_BINDING_MSG
    if isinstance(exc, ReferentAbsentRegisterError):
        return str(exc) == _no_register_msg(exc.referent)
    return False


def _choose_lift_allowed(sel: Selector, ctx: ExecCtx) -> bool:
    """May this CHOOSE ask the decider instead of taking the silent slice?
    A CHOOSE the effect runtime resolves is asked of the deciding player when
    this allows it; any other CHOOSE keeps the silent deterministic slice.

    The rules of ``tools.audit.r3_lane_ledger.lift_verdict``, on live IR
    (the ledger's lanes are pinned by :mod:`MTG_bot.core.test_ontology_r3`):
    a referent selector, or a menu that names the source itself, never
    asks; only a plain QConst count asks (QUnbounded takes the whole
    population, every other shape keeps the silent slice); every menu zone
    must be public or controller-owned: positional zones keep their fixed
    lanes, a hidden-side (hand/library) zone owned by anyone but YOU never
    asks, a PLAYER zone never asks (whose choice it is is not encoded), and
    a multi-zone menu with an ANY controller (a merged multi-seat menu)
    never asks.

    The ledger's fourth rule, "the chooser must be the card's controller",
    does not apply: the ask names the player who decides
    (:func:`resolve_selector`'s CHOOSE branch), so a choice the rules give
    another player (Goremand's "each opponent sacrifices", where EachPlayer
    rotates the controller to the opponent) is asked of that player.
    """
    if sel.referent is not None:
        return False
    if not isinstance(sel.count, QConst):
        return False
    if _filter_names_the_source(sel.filter):
        return False
    zones = list(sel.zones)
    if not zones:
        return False
    for zone in zones:
        if zone.position is not None:
            return False  # top-N / ordered-peek: fixed lanes
        if zone.kind is ZoneKind.PLAYER:
            return False  # seat menu: whose choice it is is not encoded
        if zone.kind in (ZoneKind.HAND, ZoneKind.LIBRARY) and (
            zone.controller is not ControllerRef.YOU
        ):
            return False
    if len(zones) > 1 and any(z.controller is ControllerRef.ANY for z in zones):
        return False  # a merged multi-seat menu
    src = ctx.source
    # A synthetic player-handle source (unit-world idiom) keeps the silent slice.
    return src.namespace == "card" and src in ctx.world.cards


def resolve_selector(
    sel: Selector,
    ctx: ExecCtx,
    *,
    journal_partition: bool = False,
    ok: Callable[[Handle], bool] | None = None,
    ask_choose: bool = False,
    sacrifice: bool = False,
) -> list[Handle]:
    """A Selector IR -> concrete handles.

    ALL returns the filtered population in zone order; CHOOSE takes the
    first ``count`` of the Handle-sorted candidates (``QUnbounded`` takes
    all), unless ``ask_choose`` lets the decider pick
    (:func:`_choose_lift_allowed`); RANDOM draws through the executor-owned
    seeded Random; TARGET designation is the spell's/ability's designation
    binding under ``"target"`` (CR 601.2c designates the targets once and
    every "target" in the effect means THAT designation, whatever role the
    Selector sits in; UNDESIGNATED stays the loud raise); ONE_OF asks the
    vocabulary-addressed decision channel with the Handle-sorted candidate
    list as the exact vocabulary (the enumerate-then-answer shape the query
    surface serves via ``legal_targets``), and REST takes the deterministic
    complement of this resolution's ONE_OF pick (``query.rest_of``'s
    runtime twin; the re-search compile idiom makes the subtraction usually
    a no-op). A ONE_OF ask no lane can answer RAISES (never a default); an
    empty ONE_OF population chooses nothing.

    ``ok`` (the CAST-lane designee predicate) clamps with THREE shapes, one
    law per menu kind: POPULATION menus (ALL, CHOOSE-QUnbounded, ONE_OF's
    ask vocabulary, RANDOM, TARGET's legality set) are legal-set
    enumerations clamped over the whole population, so the designation
    falls through to the next payable carrier (an unpayable head must not
    be designated and then raise; offer gate, ask vocabulary and runtime
    read ONE predicate). The finite CHOOSE positional slice is NOT
    pre-clamped: it slices the RAW population first, then checks the HEAD.
    A failing head refuses the whole effect (no cast, no pool spend, a loud
    ledger row; NEVER a silent re-pick onto the next payable spell, which
    would break the "first ``count`` of the Handle-sorted candidates" law
    above and the CAST verb's deterministic first-n stand-in). BOUND TARGET
    designations drop with the legality clamp but register a ledger row
    naming the card (an explicit designation never leaves silently). The
    referent lane ("cast THIS card") is never clamped: the per-card
    :class:`stack.FaceCastAbsentError` / missing-record raise stays the
    loud miscompile flag, and the typed face-shape survives every
    population clamp for ``cast_card``'s own guard+ledger lane.

    Callers that are actually applying the selected set pass
    ``journal_partition=True``. That emits audit TARGETING rows for
    ONE_OF/REST chosen sets. Legality/query/count callers leave it false so
    hypothetical populations never pollute the journal.

    ``sacrifice``: the CHOOSE menu is what a SACRIFICE atom destroys,
    so the player who controls it picks (:func:`sacrificing_player`, CR
    701.21a), asked under the sacrifice-cost lane's
    ``sacrifice:<seat>:<source>:<digest>`` key. Every other CHOOSE is the
    effect's controller's pick (CR 608.2d), which inside EachPlayer is the
    rotated player.
    """
    partition_window: list[Handle] | None = None
    if sel.referent is not None:
        if sel.referent in ("source", "controller"):
            candidates = [ctx.source if sel.referent == "source" else ctx.controller]
        elif sel.referent == "target":
            bound = ctx.binding_handles("target")
            if bound is None:
                raise ReferentAbsentBindingError(_TARGET_BINDING_MSG)
            candidates = bound
        elif sel.referent in ("event", "result"):
            # The trigger firing binds event/result to the event subject.
            # The ``result`` register is also a PRODUCER slot inside any one
            # effect execution: SEARCH/CHOOSE and the object-action verbs
            # (TAP/UNTAP/PUT_COUNTER/MOVE_ZONE) write it (Feat of
            # Resistance). The register is per resolution, because every
            # ExecCtx gets a fresh bindings dict (Executor._ctx) and one
            # execution's writes never leak into the next. ``event`` is
            # firing-only: outside a firing no producer has an event to
            # write. An unset read RAISES naming the referent: a missing
            # antecedent is flagged, never a guessed empty population.
            bound = ctx.binding_handles(sel.referent)
            if bound is None:
                raise ReferentAbsentRegisterError(sel.referent)
            candidates = bound
        else:
            raise NotImplementedError(
                f"executor: selector referent {sel.referent!r} is not in the "
                "closed C12 vocabulary"
            )
    else:
        candidates = []
        for zone_spec in sel.zones:  # the zones field IS the legal-zone set
            candidates.extend(enumerate_zone(ctx, zone_spec))
        # The TOP-window partition opens iff a LIBRARY+TOP zone is in the
        # SET, and its CONTROLLER is taken from that matched zone, never
        # from a positional zones[0] (with mixed zones, a test that passes
        # on one zone and then reads another is a silent rules change). The
        # corpus has at most one LIBRARY entry per selector.
        matched_top_library = next(
            (
                z
                for z in sel.zones
                if z.kind is ZoneKind.LIBRARY and z.position is ZonePosition.TOP
            ),
            None,
        )
        if (
            sel.mode in (SelectorMode.ONE_OF, SelectorMode.REST)
            and matched_top_library is not None
        ):
            # See the Truth: "Look at the top three…. Put ONE OF THOSE cards
            # into your hand": the partition population is the LOOKED-AT
            # window, not the zone's single top card (TOP enumeration
            # answers one, so the ONE_OF ask would auto-fire and the REST
            # re-search would take the whole pile). The ONE_OF
            # stashes its windowed candidates in ctx.one_of_window (the
            # sibling REST's anchor — run_atom closes the raw window at the
            # ONE_OF atom's completion, before REST resolves). Cards that
            # left the library between the look and the partition drop out;
            # the Selector's filter still applies below.
            win = ctx.look_window or (
                ctx.one_of_window if sel.mode is SelectorMode.REST else ()
            )
            if win:
                for player in players_for_ref(matched_top_library.controller, ctx):
                    live = set(ctx.world.players[player].zone(ZONE_LIBRARY).entries)
                    partition_window = [h for h in win if h in live]
                    break
                if partition_window is not None:
                    candidates = list(partition_window)
        elif (
            sel.mode in (SelectorMode.ONE_OF, SelectorMode.REST)
            and ctx.search_partition
            and ctx.search_found is not None
        ):
            # Cultivate (CR 701.23a): "Search your library for up to two
            # basic land cards ... put one onto the battlefield tapped and the
            # other into your hand." The partition divides the cards the
            # search FOUND. The whole zone would let the ONE_OF pick an
            # unfound basic and the REST take every basic left in the library.
            # A found card that left the zone since the search drops out.
            found = set(ctx.search_found)
            candidates = [h for h in candidates if h in found]
    if partition_window is not None and sel.mode is SelectorMode.ONE_OF:
        ctx.one_of_window = tuple(partition_window)
    candidates = [h for h in candidates if eval_filter(sel.filter, h, ctx)]

    # The CAST-lane predicate arrives as ``ok``; the three clamp shapes are
    # the docstring's. A POPULATION clamp consumes the WHOLE population
    # before any mode folds it (a land is not a spell; CR 601.2e: the
    # payment must exist, so an uncastable member never enters a legal-set
    # designation or the ask vocabulary). The finite CHOOSE slice is
    # POSITIONAL, so the clamp checks only the HEAD of the RAW slice. A
    # clamp-drop of a BOUND TARGET designation (CR 603.3 mode) registers a
    # ledger row below. Referent lanes stay fully OUT.
    pre_clamp = candidates
    executor = ctx.executor  # branch-guarded non-None below; local narrows
    positional = (
        ok is not None
        and executor is not None
        and sel.referent is None
        and sel.mode is SelectorMode.CHOOSE
        and not isinstance(sel.count, QUnbounded)
    )
    if ok is not None and executor is not None and sel.referent is None:
        if not positional:
            candidates = [h for h in candidates if ok(h)]
        else:
            head = sorted(pre_clamp)[: resolve(sel.count, ctx)]
            bad = [h for h in head if not ok(h)]
            if bad:
                # Refusal, not re-pick: the positional designee fails the
                # cast gate, so the effect has no legal designation and
                # casts NOTHING (the empty list keeps every downstream
                # lane, _v_cast's loop and the pool, untouched). The loud
                # ledger row is the flag (never a silent no-op faking the
                # cast, and never a raise after the offer gate let the
                # action through); it mirrors _clamp_cast_target_slot's
                # include_zero answer: an illegal designation IS the
                # rules answer (CR 601.2e).
                # Imported lazily: query imports selectors at module level.
                from MTG_bot.core.executor.query import (
                    cast_refusal_note,
                    register_cast_gap,
                )

                register_cast_gap(
                    executor,
                    ctx.source,
                    "finite CAST head cannot execute: "
                    + cast_refusal_note(executor, bad),
                )
                candidates = []
            # Clean head: leave the RAW population to the mode fold
            # below, which performs the positional slice itself.
    if sel.mode is SelectorMode.ALL:
        # Designated order-preserving slot. The zones field is canonically
        # sorted AT CONSTRUCTION, so a multi-zone ALL slot enumerates in
        # canonical zone order (pinned by
        # ``test_zones_sorted_deduped_by_canonical_json``).
        return candidates
    if sel.mode is SelectorMode.CHOOSE:
        ordered = sorted(candidates)
        if isinstance(sel.count, QUnbounded):
            return ordered
        k = resolve(sel.count, ctx)
        # Who picks. A sacrifice menu is its controller's (CR 701.21a);
        # any other menu is the effect controller's (CR 608.2d).
        decider = sacrificing_player(ctx, ordered) if sacrifice else ctx.controller
        if (
            ask_choose
            and ok is None
            and isinstance(sel.count, QAtMost)
            and k > 0
            and ordered
            and _choose_lift_allowed(replace(sel, count=QConst(sel.count.n)), ctx)
        ):
            # "up to N" names every number from zero to N (the untargeted
            # twin of the 0..N target count, CR 115.6), so each pick may
            # stop with NONE, the first included (the discard lane's shape,
            # verbs._discard_picks): Ugin's -10 can keep a permanent card in
            # hand, a named library search can fail to find (CR 701.23b).
            # The other lift rules are the QConst lane's own (same zones,
            # same referent and self-reference refusals).
            picks = []
            pool = list(ordered)
            for pick_no in range(min(k, len(pool))):
                vocab = tuple(str(h) for h in sorted(pool)) + ("NONE",)
                if sacrifice:
                    what = f"sacrifice:{decider}:{ctx.source}:{site_digest(vocab)}"
                else:
                    mid = f"{pick_no + 1}of{k}:" if k > 1 else ""
                    what = f"choose:{ctx.source}:{mid}{site_digest(vocab)}"
                answer = ctx.take_decision_of(decider, vocab, what)
                if answer == "NONE":
                    break
                pick = next(h for h in pool if str(h) == answer)
                picks.append(pick)
                pool.remove(pick)
            return picks
        if (
            ask_choose
            and ok is None
            and 0 < k < len(ordered)
            and _choose_lift_allowed(sel, ctx)
        ):
            # WHICH k of the menu is the decider's decision, not an accident
            # of Handle order: the same sequential shrinking-menu ask as the
            # ONE_OF k-of-n loop below (fixed prefix, {i}of{k} middle
            # segment only when k > 1, digest tail, vocabulary = the
            # Handle-sorted remaining pool). The default-off ask_choose
            # keeps every quantity/legality/query caller on the silent slice
            # below.
            picks: list[Handle] = []
            pool = list(ordered)
            for pick_no in range(k):
                vocab = tuple(str(h) for h in sorted(pool))
                if sacrifice:
                    what = f"sacrifice:{decider}:{ctx.source}:{site_digest(vocab)}"
                else:
                    mid = f"{pick_no + 1}of{k}:" if k > 1 else ""
                    what = f"choose:{ctx.source}:{mid}{site_digest(vocab)}"
                answer = ctx.take_decision_of(decider, vocab, what)
                pick = next(h for h in pool if str(h) == answer)
                picks.append(pick)
                pool.remove(pick)
            return picks
        return ordered[:k]  # the ceiling, clamped to what is available
    if sel.mode is SelectorMode.RANDOM:
        # For the CAST lane the pool here is the CLAMPED population, so the
        # draw is uniform over the cards the cast lane can actually run, NOT
        # over the raw zone population. That is a DISTRIBUTION BIAS against
        # the unclamped RANDOM idiom (a "randomly cast" hand full of
        # unpayable spells skews to the payable ones), and it is intended:
        # the unpayable ones could never be cast anyway, so a raw draw could
        # only land on a raise.
        count = resolve(sel.count, ctx)
        pool = sorted(candidates)
        rng = ctx.rng("RANDOM")
        sampled = list(pool)
        rng.shuffle(sampled)  # seeded: replay-identical, never wall-clock
        return sorted(sampled[:count])
    if sel.mode is SelectorMode.TARGET:
        # CR 601.2c designates the targets ONCE per spell and
        # every TARGET-mode Selector in the effect means THAT designation,
        # whatever role it sits in (Read the Tides' and Rise Again's
        # MOVE_ZONE carries it under ``cards``). The designation arrives
        # as the spell's/ability's ``target`` binding; the ones that no
        # longer pass this Selector's filter left the zone mid-resolution
        # and drop out (CR 603.3's mode/targets rule, applied per handle).
        # UNDESIGNATED stays the loud raise: an unbound designation is
        # never guessed.
        # With per-slot designations (a spell or ability with several
        # targets), a TARGET selector means ITS OWN slot's designation, whatever
        # role or quantity it sits in ("deals damage equal to its power" reads
        # the first target, the damage goes to the second).
        own = ctx.slot_designations.get(repr(sel)) if ctx.slot_designations else None
        bound = list(own) if own is not None else ctx.binding_handles("target")
        if bound is None:
            if isinstance(sel.count, QAtMost):
                # CR 601.2c, 115.6: "up to N" designated zero targets;
                # the instruction acts on nothing (an exact count stays loud).
                return []
            raise ValueError(
                "executor: TARGET selector has no designation "
                "(pass bindings={'target': ...})"
            )
        if ok is not None and executor is not None and sel.referent is None:
            # A BOUND designation the CAST clamp removes is an explicit
            # designation being refused: it must not leave silently (the
            # legality-set drop itself stays CR 603.3-mode). Membership in
            # the raw filtered zone population separates a clamp-drop
            # (passes filter+zone, fails ``ok``) from the zone/filter drops
            # above.
            from MTG_bot.core.executor.query import (
                cast_refusal_note,
                register_cast_gap,
            )

            dropped = [h for h in bound if h in pre_clamp and not ok(h)]
            if dropped:
                register_cast_gap(
                    executor,
                    ctx.source,
                    "CAST TARGET designation left the legal set: "
                    + cast_refusal_note(executor, dropped),
                )
        if any(z.kind is ZoneKind.PLAYER for z in sel.zones):
            # A CARD designation on a PLAYER-SIDE designation (∃ over the
            # zone set: PLAYER alone or PLAYER∪BATTLEFIELD both re-point)
            # means its controller: players_for_ref's
            # TARGET_PLAYER rule (the zone-enumeration face) mirrored onto
            # the designation face, so the two agree. The canonical case is
            # Brash Taunter's compiled echo: the DAMAGE trigger binds the
            # journal cause (a card) under "target", and "target opponent"
            # means THAT card's player — never the card itself.
            bound = [
                h if h.namespace == "player" else controller_of(ctx, h) for h in bound
            ]
        legal = set(candidates)
        if _is_any_universal(sel):
            # CR 109.5: "any target" includes PLAYERS. The query side's
            # _widen_any_target joins the seats to an "any target"
            # population; the runtime legality set mirrors that widening
            # EXACTLY: one population, two lanes, no second opinion. A
            # NON-universal filter cannot denote a player ("target
            # creature" excludes them, the same rules answer query.py
            # documents).
            legal.update(ctx.world.player_order)
        return sorted(h for h in bound if h in legal)
    if sel.mode is SelectorMode.ONE_OF:
        # The partition choice: enumerate from the engine's own
        # populations, then ask. The vocabulary is EXACTLY the Handle-sorted
        # candidate list (no prose); the query surface's ``legal_targets``
        # ONE_OF slot is the same population on the ask side. Forced (no
        # ask) when only one filler is legal; an empty population chooses
        # NOTHING (there is nothing to pick, and no decision to consume); an
        # exhaustion raise means no lane answered, never a default.
        # k-of-n: the partition asks WANT times over the shrinking menu, the
        # shape of binding._designate's pick loop (QConst exact / QAtMost +
        # NONE-stop, the first pick mandatory in both). want==1 keeps one
        # unnumbered ask (replay pins depend on its tag). want>1 numbers the
        # asks AFTER the kind prefix ("one_of:…:1of2:…") so a consumer keyed
        # on the kind prefix (the bench's ``ask_kind``) needs no new
        # vocabulary.
        count = sel.count
        if isinstance(count, QConst):
            want = count.value
            optional_stop = False
        elif isinstance(count, QAtMost):
            want = count.n
            optional_stop = True  # first mandatory, later stoppable
        else:
            raise NotImplementedError(
                f"executor: ONE_OF count {count!r} is not a QConst/QAtMost "
                "partition shape (flag, never guess)"
            )
        ordered = sorted(candidates)
        if not ordered:
            return []
        # The count axis answers through the shared count_semantics; this
        # loop is the RESOLVE-TIME lane. A QConst over an under-size
        # population is rejected at announcement by the query slot
        # (min=max=N exceeds the population); arriving here short of
        # population mid-effect follows CR 608.2c: resolve as much as
        # possible with what exists, NOT a second announce-time answer
        # (that verdict lives in query.py).
        announceable, k = count_semantics(count, len(ordered))
        if not announceable:
            k = len(ordered)  # resolve-time best effort, see above
        if want == 1:
            # One ask over the whole menu (QAtMost(1) never offers NONE
            # either: binding.py's own k=1 loop never reaches the stoppable
            # branch).
            if len(ordered) == 1:
                ctx.one_of_picks = (ordered[0],)  # auto-fill: one legal filler
                result = ordered
            else:
                vocab = tuple(str(h) for h in ordered)
                answer = ctx.take_decision(
                    vocab, f"one_of:{ctx.source}:{site_digest(vocab)}"
                )
                pick = next(h for h in ordered if str(h) == answer)
                ctx.one_of_picks = (pick,)
                result = [pick]
        else:
            picks: list[Handle] = []
            pool = list(ordered)
            for pick_no in range(k):
                if len(pool) == 1 and not (optional_stop and pick_no > 0):
                    picks.append(pool[0])  # auto-fill: one legal filler
                    break
                vocab = tuple(str(h) for h in pool)
                if optional_stop and pick_no > 0:
                    vocab = vocab + ("NONE",)
                answer = ctx.take_decision(
                    vocab,
                    f"one_of:{ctx.source}:{pick_no + 1}of{k}:{site_digest(vocab)}",
                )
                if answer == "NONE":
                    break
                pick = next(h for h in pool if str(h) == answer)
                picks.append(pick)
                pool.remove(pick)
            ctx.one_of_picks = tuple(picks)
            result = picks
        _emit_partition_journal(ctx, sel, result, journal_partition)
        return result
    if sel.mode is SelectorMode.REST:
        # The deterministic complement: ``query.rest_of`` at runtime, no
        # ask (the engine takes what the ONE_OF left). Under
        # the re-search compile idiom the ONE_OF's atom already MOVED its
        # pick out of the zone, so the re-enumeration here already lacks
        # it; the subtraction covers the same-zone split.
        ordered = sorted(candidates)
        if ctx.one_of_picks:
            picked = set(ctx.one_of_picks)
            ordered = [h for h in ordered if h not in picked]
        _emit_partition_journal(ctx, sel, ordered, journal_partition)
        return ordered
    raise NotImplementedError(
        f"executor: SelectorMode.{sel.mode.name} designation is 12c's target prompt"
    )


def _filter_has_referent(filter_: object) -> bool:
    """True when a Filter tree carries its own object anaphora: an
    ``FAtom.referent`` (the closed _QPROP_STR_REFERENTS strings) the atom
    resolves itself. role_handles' population exemption keys on exactly
    this: an ALL selector whose filter says "attached to TARGET" (Turn to
    Slag) denotes a population computed from the designation, not the
    designation itself."""
    if isinstance(filter_, FAtom):
        return filter_.referent is not None
    if isinstance(filter_, (FAnd, FOr)):
        return any(_filter_has_referent(c) for c in filter_.children)
    if isinstance(filter_, FNot):
        return _filter_has_referent(filter_.inner)
    return False


def _filter_is_self_referential(filter_: object) -> bool:
    """True when a Filter tree carries an ``IS_SOURCE`` atom: the closed
    "the source itself / this permanent / it" anaphora (Hobblefiend).
    A CHOOSE-mode selector filtered on IS_SOURCE is the effect's OWN
    self-designation (CR 602.2c "it" reads the ability's source), and the
    activation's cost-side TARGET pick (Hobblefiend's
    "Sacrifice another creature" binds under the shared role name
    ``target``) must never satisfy it — cost designation (601.2b payment)
    and effect designation (601.2c targets) are separate slots. Same
    shape as :func:`_filter_has_referent`, keyed on the pred instead of a
    ``referent`` field because the compiler spells self-reference as the
    IS_SOURCE predicate, not an anaphoric referent."""
    if isinstance(filter_, FAtom):
        return filter_.pred is FAtomPred.IS_SOURCE
    if isinstance(filter_, (FAnd, FOr)):
        return any(_filter_is_self_referential(c) for c in filter_.children)
    if isinstance(filter_, FNot):
        return _filter_is_self_referential(filter_.inner)
    return False


def _filter_names_the_source(filter_: object, positive: bool = True) -> bool:
    """Does the menu pin the source itself (an ``IS_SOURCE`` reached through
    an even number of negations)? "This creature" is a self-designation,
    never a choice. ``FNot(IS_SOURCE)`` is "another": a real menu (Dire
    Fleet Warmonger's "you may sacrifice another creature"), which the
    polarity-blind :func:`_filter_is_self_referential` (kept for its binding
    and cost callers) would count as self-reference, so the lift would never
    ask."""
    if isinstance(filter_, FAtom):
        return positive and filter_.pred is FAtomPred.IS_SOURCE
    if isinstance(filter_, (FAnd, FOr)):
        return any(_filter_names_the_source(c, positive) for c in filter_.children)
    if isinstance(filter_, FNot):
        return _filter_names_the_source(filter_.inner, not positive)
    return False


# ---------------------------------------------------------------- role readers


def atom_target_slot_key(atom: Atom, slot_designations: dict[str, tuple]) -> str | None:
    """Multi-slot casts: the repr-key of THIS atom's own TARGET selector,
    when the atom carries one the spell designated: the key the effect
    runtime uses to shadow ``bindings["target"]`` to the atom's own slot
    (ExecCtx.slot_designations). None when the atom designates nothing or
    its selector was not part of the spell's designation walk (the shared
    union binding then stands).

    The shadow is what the ``target`` ROLE reads (role_handles is
    binding-first), so an atom whose ``target`` role is designated shadows that
    slot even when another role sorts first (a ``dealer``); the other TARGET
    selectors read their own slots (resolve_selector)."""
    keys = [
        (role, repr(value))
        for role, value in atom.args.pairs
        if isinstance(value, Selector)
        and value.mode is SelectorMode.TARGET
        and repr(value) in slot_designations
    ]
    for role, key in keys:
        if role == "target":
            return key
    return keys[0][1] if keys else None


def graveyard_sweep_shape(value: object, verb: object, dest: object) -> bool:
    """The whole-graveyard-sweep exemption shape (see role_handles).

    The GRAVEYARD∧TARGET_PLAYER clause is ONE zone spec satisfying BOTH
    conjuncts: a set-level ``∃-kind ∧ ∃-controller`` would be satisfied by
    two different zones (e.g. zones=(HAND/TARGET_PLAYER, GRAVEYARD/YOU))
    and wrongly exempt that selector from its designation. A named helper
    so the unit-level synthetic falsifier (test_ontology_r0) exercises the
    PRODUCTION predicate, not a copy."""
    return bool(
        isinstance(value, Selector)
        and value.mode is SelectorMode.ALL
        # Exile is a MOVE_ZONE whose destination kind is EXILE.
        and verb is Verb.MOVE_ZONE
        and isinstance(dest, Zone)
        and dest.kind is ZoneKind.EXILE
        and isinstance(value.filter, FAnd)
        and not value.filter.children
        and any(
            z.kind is ZoneKind.GRAVEYARD and z.controller in DESIGNATED_PLAYER_REFS
            for z in value.zones
        )
    )


def _in_population(sel: Selector, handle: Handle, ctx: ExecCtx) -> bool:
    """Could ``handle`` be one of the objects ``sel`` selects (in one of its
    zones and passing its filter)?"""
    if not any(handle in enumerate_zone(ctx, zone) for zone in sel.zones):
        return False
    return eval_filter(sel.filter, handle, ctx)


def role_handles(ctx: ExecCtx, atom: Atom, role: str) -> list[Handle]:
    """The handles a target/cards/equipment role acts on, Handle-sorted.

    Bindings take precedence (the caller designated them) EXCEPT where the
    role's Selector resolves itself, so a spell-level designation sharing
    the role NAME must not hijack it. The self-resolving shapes are flagged
    one by one below. The first is an ANAPHORIC Selector, one carrying its
    own ``referent``: "the cards the preceding atom found" is a reference
    the atom resolves itself (Necromentia's EXILE-``target`` would grab the
    designated OPPONENT under that binding and feed a player handle to
    ``controller_of``). A referent-less Selector stays binding-first
    (``_binding_atom`` payments included).

    An ALL-mode Selector whose FILTER carries its own referent anaphora
    (IS_ATTACHED_TO's "attached to target") also resolves itself. Turn to
    Slag's DESTROY carries ``ALL BATTLEFIELD (Equipment AND attached to
    target)`` under the ``target`` role; binding-first would destroy the
    DESIGNATED creature (which survives the 5 damage) and leave the
    attached Equipment standing. The exemption stays NARROW: a
    referent-less ALL Selector keeps binding-first, because the engine's
    own unit-test idiom (and the ``_binding_atom`` payments) drives
    designation effects as ``all_bf()`` + a binding (test_detach_on_leave's
    EXILE); a bare ALL population with no anaphora has nothing to resolve
    against, so it is NOT evidence of population intent. TARGET mode
    remains the designation lane (CR 601.2c).
    """
    bound = ctx.binding_handles(role)
    value = atom.args.get(role)
    anaphoric = isinstance(value, Selector) and value.referent is not None
    # A PLAYER-side Selector resolves through its own zone (the TARGET_PLAYER
    # card-to-controller conversion): a designation binding carrying a CARD
    # must not be handed to a player verb raw, or Brash Taunter's echo would
    # mark the damage source instead of its player. Same shape as the
    # anaphoric exemption: the Selector knows best. The exemption is for
    # PURE player selectors: the singleton len(zones)==1 ∧ PLAYER, NOT an ∃
    # over the set. The compiled "target player or planeswalker" shape
    # (Chandra's Magmutt) is a PLAYER ∪ BATTLEFIELD zone SET, where a CARD
    # handle (the walker) is a LEGAL designation (enumerate_candidates walks
    # the whole set); self-resolving it through the PLAYER zone would
    # silently re-point the printed damage at the player. A designation the
    # player actually made stands.
    player_side = (
        isinstance(value, Selector)
        and len(value.zones) == 1
        and value.zones[0].kind is ZoneKind.PLAYER
    )
    # An ALL-mode Selector with referent-anaphora in its filter denotes its
    # own resolved population (Turn to Slag, see the docstring).
    population = (
        isinstance(value, Selector)
        and value.mode is SelectorMode.ALL
        and _filter_has_referent(value.filter)
    )
    # Hobblefiend: a CHOOSE-mode selector filtered on IS_SOURCE is the
    # effect's OWN self-designation ("it"/"this creature" = CR 602.2c
    # reads the ability's source); the activation's cost-side TARGET pick
    # shares the role NAME ``target`` (build_payment_plan spends the
    # Sacrifice through the same journalled verb) and must not hijack it.
    # TARGET mode stays the designation lane (CR 601.2c) — a real effect
    # target never compiles as IS_SOURCE, so the exemption is inert for
    # every designation-driven pack.
    self_ref = (
        isinstance(value, Selector)
        and value.mode is SelectorMode.CHOOSE
        and _filter_is_self_referential(value.filter)
    )
    # Tormod's Crypt: the whole-graveyard sweep. "Exile target player's
    # graveyard" compiles as an ALL-mode EXILE over the single zone
    # GRAVEYARD/TARGET_PLAYER with a UNIVERSAL filter (empty FAnd: the zone
    # IS the population, there is nothing to filter); the designation names
    # a CARD in that graveyard, and the binding-first lane would exile just
    # the designated cards, a silent wrong answer. The exemption is pinned
    # to five conditions: ALL mode, EXILE, universal empty-FAnd filter, and
    # ONE zone that is both GRAVEYARD and TARGET_PLAYER (see
    # graveyard_sweep_shape). resolve_selector folds the card designation
    # through players_for_ref's TARGET_PLAYER lane and sweeps the full
    # graveyard.
    _dest = atom.args.get("destination")
    graveyard_sweep = graveyard_sweep_shape(value, atom.verb, _dest)
    # Rewind (CR 608.2c): a CHOOSE selector is a choice its controller makes
    # as the effect resolves, not a designation. It shares the role NAME
    # ``target`` with the spell's TARGET designation only by the compiler's
    # naming ("Counter target spell. Untap up to four lands." would hand the
    # countered spell to the untap). When none of the bound objects can be in
    # this selector's population, the designation is not for it, and it
    # resolves itself. A binding that does fit keeps the binding-first lane.
    foreign = (
        bound is not None
        and isinstance(value, Selector)
        and value.mode is SelectorMode.CHOOSE
        and value.referent is None
        and not any(_in_population(value, h, ctx) for h in bound)
    )
    # A designation made of PLAYER handles (the spell's TARGET_PLAYER
    # coordinate, Run Afoul's target opponent) is never a member of a CARD
    # population, so it must not take over a role whose non-TARGET selector
    # (a resolution-time CHOOSE/ALL pick) can hold only cards (no PLAYER/ANY
    # zone), as in "target opponent sacrifices a creature". The role resolves
    # its own selector instead, in the rotated coordinates. TARGET mode stays
    # the designation lane.
    player_into_cards = (
        bound is not None
        and bool(bound)
        and all(h.namespace == "player" for h in bound)
        and isinstance(value, Selector)
        and value.mode is not SelectorMode.TARGET
        and all(z.kind not in (ZoneKind.PLAYER, ZoneKind.ANY) for z in value.zones)
    )
    # CR 701.21a: a player sacrifices a permanent of their own choice as the instruction
    # resolves, so a sacrifice menu (a CHOOSE, or the ONE_OF the compiler promotes a count-1
    # CHOOSE to) is never the ability's target designation, whether or not the targeted object
    # could be on the menu. "You may sacrifice a Vampire. When you do, ~ deals 3 damage to any
    # target" would sacrifice the target instead (Sorin, Imperious Bloodlord). A TARGET-mode role
    # stays the designation lane (the payment placeholder of legality._binding_atom).
    sacrifice_choice = (
        atom.verb is Verb.SACRIFICE
        and isinstance(value, Selector)
        and value.mode in (SelectorMode.CHOOSE, SelectorMode.ONE_OF)
        and value.referent is None
    )
    if (
        bound is not None
        and not anaphoric
        and not player_side
        and not population
        and not self_ref
        and not graveyard_sweep
        and not foreign
        and not player_into_cards
        and not sacrifice_choice
    ):
        # CR 702.26b / 608.2b: a designated permanent that has phased out
        # since it was designated does not exist, so the verb skips it.
        return existing(ctx, bound)
    if isinstance(value, Selector):
        if (
            atom.verb is Verb.CAST
            and role == "source"
            and value.referent is None
            and ctx.executor is not None
        ):
            # THE single choke point where CAST atoms read populations. The
            # execution-acceptance predicate (:func:`query.cast_designee_ok`,
            # the offer gate's own law, so menu == acceptance) is threaded
            # INTO selector resolution; the clamp shapes it applies there
            # follow the three-law split documented on
            # :func:`resolve_selector` (population menus clamp; the finite
            # CHOOSE slice is checked HEAD-first, refusing loudly;
            # TARGET-bound drops ledger).
            # Explicit designations (the bound lane above, referent
            # selectors) stay raw: a designated card the cast lane cannot
            # run stays the LOUD per-card raise.
            from MTG_bot.core.executor.query import cast_designee_ok

            cost_override = atom.args.get("cost")
            if not isinstance(cost_override, Cost):
                cost_override = None  # printed cost, or a Ref the fold reads
            executor = ctx.executor  # branch-guarded non-None; local narrows

            def ok(handle: Handle) -> bool:
                return cast_designee_ok(executor, ctx, handle, cost_override, atom=atom)

            return sorted(resolve_selector(value, ctx, ok=ok))
        # The EFFECT-role choke point: a finite CHOOSE resolved here is a
        # real decision and the fold asks through the decision channel
        # (_choose_lift_allowed and the default-off ask_choose keep every
        # other caller on the silent slice). A SACRIFICE menu is asked of
        # the player who controls it (CR 701.21a).
        return sorted(
            resolve_selector(
                value, ctx, ask_choose=True, sacrifice=atom.verb is Verb.SACRIFICE
            )
        )
    if bound is not None:
        return bound
    raise ValueError(f"executor: {atom.verb.name} role {role!r} has no binding")


def role_player(ctx: ExecCtx, atom: Atom, role: str = "controller") -> Handle:
    bound = ctx.binding_one(role)
    if bound is not None:
        return bound
    value = atom.args.get(role)
    if isinstance(value, ControllerRef):
        players = players_for_ref(value, ctx)
        if len(players) > 1:
            # One acting player cannot stand for several. With three or more seats OPPONENT
            # ("an opponent") names one of several, and somebody must choose which;
            # ALL_OPPONENTS ("each opponent") means every one of them. Taking the first would be a
            # silent wrong answer, so it is loud until the verb iterates or the tree wraps it in
            # EachPlayer (BACKLOG B-108). Two seats never reach this with an opponent ref.
            raise NotImplementedError(
                f"executor: {atom.verb.name} {role!r} is one player, but ControllerRef."
                f"{value.name} denotes {len(players)} here (B-108)"
            )
        if not players:
            # DEFENDING_PLAYER outside combat names nobody (CR 506.2)
            raise NotImplementedError(
                f"executor: {atom.verb.name} {role!r} is one player, but ControllerRef."
                f"{value.name} denotes none here"
            )
        return players[0]
    if isinstance(value, Selector) and value.referent is not None:
        # "That creature's controller reveals ..." (Transmogrify): the controller of
        # the one object in scope (role_players' fold, CR 608.2h).
        players = role_players(ctx, atom, role)
        if len(players) != 1:
            raise ValueError(
                f"executor: {atom.verb.name} {role!r} is one player, but the referent "
                f"{value.referent!r} names {len(players)}"
            )
        return players[0]
    raise NotImplementedError(
        f"executor: {atom.verb.name} {role!r} referent-selector player is 12b's"
    )


def role_players(ctx: ExecCtx, atom: Atom, role: str = "controller") -> list[Handle]:
    """The PLAYERS a life/draw-style role acts on. Three lanes, in the same
    precedence order the card-side :func:`role_handles` uses: a Selector
    value resolves ITSELF when it is anaphoric (its own referent: Gloom
    Sower compiles "that creature's controller" as a referent=event
    selector whose resolution is a CREATURE, folded to its controller by
    :func:`last_known_controller`; a player handle passes through); a
    reference-less binding keeps its precedence (the designation
    convention); a bare ControllerRef is the ordinary YOU/EACH_PLAYER
    lane."""
    value = atom.args.get(role)
    bound = ctx.binding_handles(role)
    handles: list[Handle] | None = None
    if isinstance(value, Selector):
        anaphoric = value.referent is not None
        if bound is not None and not anaphoric:
            handles = bound
        else:
            handles = sorted(resolve_selector(value, ctx))
    elif bound is not None:
        handles = bound
    elif isinstance(value, ControllerRef):
        return players_for_ref(value, ctx)
    else:
        raise NotImplementedError(
            f"executor: {atom.verb.name} {role!r} referent-selector players are 12b's"
        )
    return _players_of(ctx, handles)


def players_for(ref: ControllerRef | Selector, ctx: ExecCtx) -> list[Handle]:
    """The players an EachPlayer ``ref`` denotes: a ControllerRef's seats
    (:func:`players_for_ref`), or for a referent Selector the controller of each
    object it names ("That player puts that card onto the battlefield, then
    shuffles the rest into their library", Transmogrify: the creature's
    controller as it last existed, CR 608.2h)."""
    if isinstance(ref, Selector):
        return _players_of(ctx, resolve_selector(ref, ctx))
    return players_for_ref(ref, ctx)


def _players_of(ctx: ExecCtx, handles: list[Handle]) -> list[Handle]:
    """Each handle's player side: a player itself, a card its (last known)
    controller."""
    world = ctx.world
    players: set[Handle] = set()
    for handle in handles:
        if handle.namespace == "player":
            players.add(handle)
        elif handle in world.cards:
            players.add(last_known_controller(ctx, handle))
    return sorted(players)


def last_known_controller(ctx: ExecCtx, handle: Handle) -> Handle:
    """The player "its controller" names (CR 608.2h). An object that has left the battlefield
    answers with the controller it last had there (its last known information,
    :func:`quantity.last_known`), not with its owner: "Destroy target creature. Its controller
    loses 2 life" on a stolen creature costs the player who stole it the life. Anything else
    answers with its effective controller; a card that has been sitting in a graveyard, with
    its owner (CR 108.4a)."""
    lki = last_known(handle, ctx)
    return lki.controller if lki is not None else controller_of(ctx, handle)


def amount(ctx: ExecCtx, atom: Atom, role: str) -> int:
    quantity = atom.args.get(role)
    if quantity is None:
        raise ValueError(f"executor: {atom.verb.name} missing role {role!r}")
    assert isinstance(quantity, Quantity)
    return resolve(quantity, ctx)
