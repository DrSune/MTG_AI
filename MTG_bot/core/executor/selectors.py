"""Zone/selector/target resolution for the executor (round 12a, /06 §12a).

The single mapping from IR designation to concrete handles:

  * ``players_for_ref`` — a ControllerRef -> the player seats it denotes;
  * ``enumerate_zone`` — a Zone IR -> its handles in **zone order** (the
    designated order-preserving slot; top of library = last entry);
  * ``resolve_selector`` — a Selector IR -> handles, per mode (ALL = zone
    order; CHOOSE = the deterministic 12a stand-in for the 12c prompt;
    RANDOM = the executor-owned seeded Random; TARGET designation arrives
    as the caller's *bindings*, ruling 5 — Handle-sorted);
  * the role helpers (``role_handles``/``role_player``/``role_players``/
    ``amount``) read one Atom's roles off that machinery.

Unsupported designations (Zone(ANY) enumeration, TARGET/ONE_OF/REST mode,
OWNER-scoped selector enumeration) RAISE naming 12b/12c — flag, don't
degrade. Conventions honoured: C17 clamp lives with the callers (CHOOSE
takes min(count, candidates)); C12 referents are the closed strings.
"""

from __future__ import annotations

from MTG_bot.core.ability_tree import (
    Atom,
    ControllerRef,
    FAnd,
    FAtom,
    FAtomPred,
    FNot,
    FOr,
    Quantity,
    QUnbounded,
    Selector,
    SelectorMode,
    Zone,
    ZoneKind,
    ZonePosition,
)
from MTG_bot.core.executor.decisions import site_digest
from MTG_bot.core.executor.quantity import ExecCtx, eval_filter, resolve
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
    """The EFFECTIVE controller of a card (16e): the executor's GAIN_CONTROL
    overlay wins over the zone-owner read. A bare ExecCtx (no executor) has
    no overlay, so pre-16e bare-ctx paths read the owner byte-identically."""
    ex = ctx.executor
    if ex is None:
        return ctx.world.controller_of(handle)
    return ex.controller_of(handle)


def players_for_ref(ref: ControllerRef, ctx: ExecCtx) -> list[Handle]:
    """The player seats a ControllerRef denotes, in seat order."""
    if ref is ControllerRef.YOU:
        return [ctx.controller]
    if ref in (ControllerRef.OPPONENT, ControllerRef.ALL_OPPONENTS):
        return _opponents(ctx)
    if ref is ControllerRef.ANY:
        return list(ctx.world.player_order)
    if ref is ControllerRef.TARGET_PLAYER:
        bound = ctx.binding_one("target")
        if bound is None:
            raise ValueError(
                "executor: TARGET_PLAYER needs a bound target (12c target prompt)"
            )
        if bound.namespace == "player":
            return [bound]
        return [controller_of(ctx, bound)]
    raise NotImplementedError(
        f"executor: ControllerRef.{ref.name} has no player-side meaning here"
    )


def controller_matches(
    who: ControllerRef | Selector, actual: Handle, ctx: ExecCtx
) -> bool:
    """Did ``actual`` (a player handle) satisfy a CONTROLLER_IS ``who`` slot?"""
    if isinstance(who, Selector):
        # 12b: a referent Selector (e.g. the event subject's controller) —
        # resolve the bound object(s) and compare their player side.
        candidates = resolve_selector(who, ctx)
        players = [
            c if c.namespace == "player" else controller_of(ctx, c) for c in candidates
        ]
        return actual in players
    if who is ControllerRef.YOU:
        return actual == ctx.controller
    if who in (ControllerRef.OPPONENT, ControllerRef.ALL_OPPONENTS):
        return actual != ctx.controller
    if who is ControllerRef.TARGET_PLAYER:
        bound = ctx.binding_one("target")
        expected: Handle | None = bound
        if bound is not None and bound.namespace == "card":
            expected = controller_of(ctx, bound)
        return expected is not None and actual == expected
    return who is ControllerRef.ANY


def zone_owner(ctx: ExecCtx, zone_ir: Zone, owner: Handle | None) -> Handle:
    """The single player who owns a destination/movement zone IR."""
    ref = zone_ir.controller
    if ref is ControllerRef.OWNER:
        if owner is None:
            raise ValueError("executor: OWNER zone needs a card to own it")
        return owner
    if ref is ControllerRef.YOU:
        return ctx.controller
    if ref in (ControllerRef.ANY, ControllerRef.TARGET_PLAYER):
        return players_for_ref(ref, ctx)[0]
    raise NotImplementedError(
        f"executor: zone controller ref {ref.name} needs multiple owners (12b)"
    )


def enumerate_zone(ctx: ExecCtx, zone_ir: Zone) -> list[Handle]:
    """The handles in one Zone IR, in **zone order** (order-preserving)."""
    kind = zone_ir.kind
    if kind is ZoneKind.PLAYER:
        return players_for_ref(zone_ir.controller, ctx)
    if kind is ZoneKind.ANY:
        # 18b: Zone(ANY) at RUNTIME — the exact seat-order × PLAYER_ZONES
        # loop legality._zone_handles has answered for the QUERY side since
        # 12c, lifted so §8.3's query/runtime enumeration identity holds
        # for the "any target"/"any zone" selectors that compile this way
        # (Meteorite, Skeleton Archer, Terror of the Peaks). The controller
        # ref is deliberately NOT a filter here (the frozen 12c reading:
        # ANY spans every player's zones — an opinion, one implementation,
        # two lanes). HIDDEN zones (libraries, the opponent's hand) ride
        # along: the executor is an OMNISCIENT v1 policy — the hidden-
        # information model gap is documented (doc 2026-10-01/20) exactly
        # like the combat-uninterrupted gap, never silently papered.
        if zone_ir.controller is ControllerRef.OWNER:
            raise NotImplementedError(
                "executor: OWNER in selector enumeration needs per-candidate "
                "owner scoping (12b)"
            )
        handles_all: list[Handle] = []
        for player in ctx.world.player_order:
            for any_kind in PLAYER_ZONES:
                handles_all.extend(ctx.world.players[player].zone(any_kind).entries)
        return handles_all
    ref = zone_ir.controller
    if kind is ZoneKind.STACK:
        # 14d (B-19): B-2's RUNTIME twin. ZONE_KIND_TO_STATE has no STACK
        # entry (the frozen state.py has no stack zone kind), so the old
        # bare KeyError(ZoneKind.STACK) is replaced by F-2's fix shape:
        # enumerate each seat's parked frames through
        # :func:`stack.stack_zone` (the per-player ZONE_STACK slot created
        # on first use — the SAME source the query side reads since 14a,
        # keeping §8.3 query/runtime enumeration identity). TOP = the last
        # entry = the top frame (LIFO order-preserving, the stack's own
        # convention). OWNER stays the existing 12b selector raise — the
        # honest flag every zone carries at runtime (the QUERY side
        # answers OWNER via source_owner, legality.py F-2).
        if ref is ControllerRef.OWNER:
            raise NotImplementedError(
                "executor: OWNER in selector enumeration needs per-candidate "
                "owner scoping (12b)"
            )
        from MTG_bot.core.executor.stack import stack_zone

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
        return stack_handles
    state_kind = ZONE_KIND_TO_STATE[kind]
    if ref is ControllerRef.OWNER:
        raise NotImplementedError(
            "executor: OWNER in selector enumeration needs per-candidate "
            "owner scoping (12b)"
        )
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
    return handles


def _is_any_universal(sel: Selector) -> bool:
    """True for the "any target" IR shape: an ANY-kind zone (primary or
    extra) with the empty FAnd filter — query._widen_any_target's twin
    predicate, shared here because the runtime TARGET legality set must
    widen over exactly the same population the query offers (CR 109.5)."""
    return bool(
        sel.filter is not None
        and isinstance(sel.filter, FAnd)
        and not sel.filter.children
    ) and any(z.kind is ZoneKind.ANY for z in (sel.zone, *sel.zones))


def resolve_selector(sel: Selector, ctx: ExecCtx) -> list[Handle]:
    """A Selector IR -> concrete handles.

    ALL returns the filtered population in zone order; CHOOSE resolves the
    deterministic 12a stand-in for the 12c choice prompt (first ``count``
    of the Handle-sorted candidates; ``QUnbounded`` takes all); RANDOM
    draws through the executor-owned seeded Random; TARGET designation is
    the spell's/ability's designation binding under ``"target"`` (14c,
    B-15 — CR 601.2c designates the targets once and every "target" in
    the effect means THAT designation, whatever role the Selector sits
    in; UNDESIGNATED stays the loud raise); ONE_OF (14c, B-13) asks the
    vocabulary-addressed decision channel with the Handle-sorted
    candidate list as the exact vocabulary — the enumerate-then-answer
    shape the query surface already serves via ``legal_targets`` — and
    REST takes the deterministic complement of this resolution's ONE_OF
    pick (``query.rest_of``'s runtime twin; the re-search compile idiom
    makes the subtraction usually a no-op). C15: an ONE_OF ask no lane
    can answer RAISES (never a default); an empty ONE_OF population
    chooses nothing (C17 clamp).
    """
    partition_window: list[Handle] | None = None
    if sel.referent is not None:
        if sel.referent in ("source", "controller"):
            candidates = [ctx.source if sel.referent == "source" else ctx.controller]
        elif sel.referent == "target":
            bound = ctx.binding_handles("target")
            if bound is None:
                raise ValueError("executor: 'target' referent has no target binding")
            candidates = bound
        elif sel.referent in ("event", "result"):
            # 12b: the trigger firing binds event/result to the event
            # subject. 14e (B-9): the ``result`` register is additionally a
            # PRODUCER slot inside any one effect execution — SEARCH/CHOOSE
            # since 14c, and the object-action verbs (TAP/UNTAP/PUT_COUNTER/
            # MOVE_ZONE) since the cast-resolution faces (Feat of Resistance,
            # the captured Hallowblade tail) demanded it; the register is per
            # resolution, because every ExecCtx gets a fresh bindings dict
            # (Executor._ctx) and one execution's writes never leak into the
            # next. ``event`` remains firing-only: outside a firing no
            # producer has an event to write. An unset read RAISES naming the
            # referent — a missing antecedent is flagged, never a guessed
            # empty population.
            bound = ctx.binding_handles(sel.referent)
            if bound is None:
                raise NotImplementedError(
                    f"executor: selector referent {sel.referent!r} has no "
                    "register — no trigger firing bound one and no producer "
                    "atom wrote one in this execution"
                )
            candidates = bound
        else:
            raise NotImplementedError(
                f"executor: selector referent {sel.referent!r} is not in the "
                "closed C12 vocabulary"
            )
    else:
        candidates = list(enumerate_zone(ctx, sel.zone))
        for extra in sel.zones:
            candidates.extend(enumerate_zone(ctx, extra))
        if (
            sel.mode in (SelectorMode.ONE_OF, SelectorMode.REST)
            and sel.zone.kind is ZoneKind.LIBRARY
            and sel.zone.position is ZonePosition.TOP
        ):
            # r19b (See the Truth): "Look at the top three…. Put ONE OF
            # THOSE cards into your hand" — the partition population is the
            # LOOKED-AT window, not the zone's single top card (TOP
            # enumeration answers one, which made the ONE_OF ask auto-fire
            # and the REST re-search hoover the whole pile). The ONE_OF
            # stashes its windowed candidates in ctx.one_of_window (the
            # sibling REST's anchor — run_atom closes the raw window at the
            # ONE_OF atom's completion, before REST resolves). Cards that
            # left the library between the look and the partition drop out;
            # the Selector's filter still applies below.
            win = ctx.look_window or (
                ctx.one_of_window if sel.mode is SelectorMode.REST else ()
            )
            if win:
                for player in players_for_ref(sel.zone.controller, ctx):
                    live = set(ctx.world.players[player].zone(ZONE_LIBRARY).entries)
                    partition_window = [h for h in win if h in live]
                    break
                if partition_window is not None:
                    candidates = list(partition_window)
    if partition_window is not None and sel.mode is SelectorMode.ONE_OF:
        ctx.one_of_window = tuple(partition_window)
    candidates = [h for h in candidates if eval_filter(sel.filter, h, ctx)]
    if sel.mode is SelectorMode.ALL:
        return candidates  # zone order — designated order-preserving slot
    if sel.mode is SelectorMode.CHOOSE:
        ordered = sorted(candidates)
        if isinstance(sel.count, QUnbounded):
            return ordered
        return ordered[: resolve(sel.count, ctx)]  # C17: ceiling vs availability
    if sel.mode is SelectorMode.RANDOM:
        count = resolve(sel.count, ctx)
        pool = sorted(candidates)
        rng = ctx.rng("RANDOM")
        sampled = list(pool)
        rng.shuffle(sampled)  # seeded: replay-identical, never wall-clock
        return sorted(sampled[:count])
    if sel.mode is SelectorMode.TARGET:
        # 14c (B-15): CR 601.2c designates the targets ONCE per spell and
        # every TARGET-mode Selector in the effect means THAT designation,
        # whatever role it sits in (Read the Tides' and Rise Again's
        # MOVE_ZONE carries it under ``cards``). The designation arrives
        # as the spell's/ability's ``target`` binding; the ones that no
        # longer pass this Selector's filter left the zone mid-resolution
        # and drop out (CR 603.3's mode/targets rule, applied per handle).
        # UNDESIGNATED stays the loud raise — an unbound designation is
        # still never guessed.
        bound = ctx.binding_handles("target")
        if bound is None:
            raise ValueError(
                "executor: TARGET selector has no designation "
                "(pass bindings={'target': ...})"
            )
        if sel.zone.kind is ZoneKind.PLAYER:
            # 16a: a CARD designation on a PLAYER-side designation means
            # its controller — players_for_ref's TARGET_PLAYER rule (the
            # zone-enumeration face) mirrored onto the designation face,
            # so the two agree. The canonical case is Brash Taunter's
            # compiled echo: the DAMAGE trigger binds the journal cause
            # (a card) under "target", and "target opponent" means THAT
            # card's player — never the card itself.
            bound = [
                h if h.namespace == "player" else controller_of(ctx, h) for h in bound
            ]
        legal = set(candidates)
        if _is_any_universal(sel):
            # 18b (CR 109.5): "any target" includes PLAYERS. The query
            # side's _widen_any_target has joined the seats to a
            # universal-filtered ANY population since 13b; the runtime
            # legality set mirrors that widening EXACTLY — one population,
            # two lanes, no second opinion (§8.3). A NON-universal filter
            # cannot denote a player ("target creature" excludes them,
            # the same rules answer query.py documents).
            legal.update(ctx.world.player_order)
        return sorted(h for h in bound if h in legal)
    if sel.mode is SelectorMode.ONE_OF:
        # 14c (B-13): the partition choice, asked as C15 prescribes —
        # enumerate from the engine's own populations, then answer. The
        # vocabulary is EXACTLY the Handle-sorted candidate list (no
        # prose); the query surface's ``legal_targets`` ONE_OF slot is
        # the same population on the ask side. Forced (no ask) when only
        # one filler is legal; an empty population chooses NOTHING (C17
        # clamp — there is nothing to pick, and no decision to consume);
        # an exhaustion raise means no lane answered — never a default.
        ordered = sorted(candidates)
        if not ordered:
            return []
        if len(ordered) == 1:
            ctx.one_of_pick = ordered[0]  # §1.4 auto-fill: one legal answer
            return ordered
        vocab = tuple(str(h) for h in ordered)
        answer = ctx.take_decision(vocab, f"one_of:{ctx.source}:{site_digest(vocab)}")
        pick = next(h for h in ordered if str(h) == answer)
        ctx.one_of_pick = pick
        return [pick]
    if sel.mode is SelectorMode.REST:
        # 14c (B-13): the deterministic complement — ``query.rest_of`` at
        # runtime, no ask (the engine takes what the ONE_OF left). Under
        # the re-search compile idiom the ONE_OF's atom already MOVED its
        # pick out of the zone, so the re-enumeration here already lacks
        # it; the subtraction covers the same-zone split.
        ordered = sorted(candidates)
        if ctx.one_of_pick is not None:
            ordered = [h for h in ordered if h != ctx.one_of_pick]
        return ordered
    raise NotImplementedError(
        f"executor: SelectorMode.{sel.mode.name} designation is 12c's target prompt"
    )


def _filter_has_referent(filter_: object) -> bool:
    """r19b (Turn to Slag): True when a Filter tree carries its own object
    anaphora — an ``FAtom.referent`` (the closed _QPROP_STR_REFERENTS
    strings) the atom resolves itself. role_handles' population exemption
    keys on exactly this: an ALL selector whose filter says "attached to
    TARGET" denotes a population computed from the designation, not the
    designation itself."""
    if isinstance(filter_, FAtom):
        return filter_.referent is not None
    if isinstance(filter_, (FAnd, FOr)):
        return any(_filter_has_referent(c) for c in filter_.children)
    if isinstance(filter_, FNot):
        return _filter_has_referent(filter_.inner)
    return False


def _filter_is_self_referential(filter_: object) -> bool:
    """r20c (Hobblefiend): True when a Filter tree carries an ``IS_SOURCE``
    atom — the closed "the source itself / this permanent / it" anaphora.
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


# ---------------------------------------------------------------- role readers


def atom_target_slot_key(atom: Atom, slot_designations: dict[str, tuple]) -> str | None:
    """r19c (multi-slot casts): the repr-key of THIS atom's own TARGET
    selector, when the atom carries one the spell designated — the key the
    effect runtime uses to shadow ``bindings["target"]`` to the atom's own
    slot (ExecCtx.slot_designations). None when the atom designates nothing
    or its selector was not part of the spell's designation walk (the
    shared union binding then stands, exactly as before)."""
    for _role, value in atom.args.pairs:
        if (
            isinstance(value, Selector)
            and value.mode is SelectorMode.TARGET
            and repr(value) in slot_designations
        ):
            return repr(value)
    return None


def role_handles(ctx: ExecCtx, atom: Atom, role: str) -> list[Handle]:
    """The handles a target/cards/equipment role acts on, Handle-sorted.

    Bindings take precedence (the caller designated them) EXCEPT for an
    ANAPHORIC Selector — one carrying its own ``referent`` (14c, B-16):
    "the cards the preceding atom found" is a reference the atom resolves
    itself, and a spell-level designation sharing the role NAME must not
    hijack it (Necromentia's EXILE-``target`` grabbed the designated
    OPPONENT under that binding and fed a player handle to ``controller_
    of``). A referent-less Selector stays binding-first (the 12a
    designation convention, ``_binding_atom`` payments included).

    r19b (Turn to Slag): a THIRD self-resolving shape — an ALL-mode
    Selector whose FILTER carries its own referent anaphora (IS_ATTACHED_
    TO's "attached to target") denotes a population the atom resolves
    itself, and the spell's designation under a shared role name must not
    hijack it. Turn to Slag's DESTROY carries ``ALL BATTLEFIELD
    (Equipment AND attached to target)`` under the ``target`` role;
    binding-first made it destroy the DESIGNATED creature (which survives
    the 5 damage) and leave the attached Equipment standing — the exact
    silent-semantics shape. The exemption stays NARROW: a referent-less
    ALL Selector keeps binding-first, because the engine's own unit-test
    idiom (and the 12a ``_binding_atom`` payments) drives designation
    effects as ``all_bf()`` + a binding (test_detach_on_leave's EXILE);
    a bare ALL population with no anaphora has nothing to resolve
    against, so it is NOT evidence of population intent. TARGET mode
    remains the designation lane (CR 601.2c, B-15).
    """
    bound = ctx.binding_handles(role)
    value = atom.args.get(role)
    anaphoric = isinstance(value, Selector) and value.referent is not None
    # 16a: a PLAYER-side Selector resolves through its own zone (the
    # TARGET_PLAYER/controller conversion above) — a designation binding
    # carrying a CARD must not be handed to a player verb raw, or Brash
    # Taunter's echo would mark the damage source instead of its player.
    # Same shape as the B-16 anaphoric exemption: the Selector knows best.
    player_side = isinstance(value, Selector) and value.zone.kind is (ZoneKind.PLAYER)
    # r19b: an ALL-mode Selector with referent-anaphora in its filter
    # denotes its own resolved population (Turn to Slag above).
    population = (
        isinstance(value, Selector)
        and value.mode is SelectorMode.ALL
        and _filter_has_referent(value.filter)
    )
    # r20c (Hobblefiend): a CHOOSE-mode selector filtered on IS_SOURCE is
    # the effect's OWN self-designation ("it"/"this creature" = CR 602.2c
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
    if (
        bound is not None
        and not anaphoric
        and not player_side
        and not population
        and not self_ref
    ):
        return bound
    if isinstance(value, Selector):
        return sorted(resolve_selector(value, ctx))
    if bound is not None:
        return bound
    raise ValueError(f"executor: {atom.verb.name} role {role!r} has no binding")


def role_player(ctx: ExecCtx, atom: Atom, role: str = "controller") -> Handle:
    bound = ctx.binding_one(role)
    if bound is not None:
        return bound
    value = atom.args.get(role)
    if isinstance(value, ControllerRef):
        return players_for_ref(value, ctx)[0]
    raise NotImplementedError(
        f"executor: {atom.verb.name} {role!r} referent-selector player is 12b's"
    )


def role_players(ctx: ExecCtx, atom: Atom, role: str = "controller") -> list[Handle]:
    """The PLAYERS a life/draw-style role acts on. Three lanes, in the same
    precedence order the card-side :func:`role_handles` uses: a Selector
    value resolves ITSELF when it is anaphoric (its own referent — 16c's
    Gloom Sower compiles "that creature's controller" as a referent=event
    selector whose resolution is a CREATURE, folded to ``controller_of``;
    a player handle passes through); a reference-less binding keeps its
    precedence (the 12a designation convention); a bare ControllerRef is
    the ordinary YOU/EACH_PLAYER lane."""
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
    world = ctx.world
    players: set[Handle] = set()
    for handle in handles:
        if handle.namespace == "player":
            players.add(handle)
        elif handle in world.cards:
            players.add(controller_of(ctx, handle))
    return sorted(players)


def amount(ctx: ExecCtx, atom: Atom, role: str) -> int:
    quantity = atom.args.get(role)
    if quantity is None:
        raise ValueError(f"executor: {atom.verb.name} missing role {role!r}")
    assert isinstance(quantity, Quantity)
    return resolve(quantity, ctx)
