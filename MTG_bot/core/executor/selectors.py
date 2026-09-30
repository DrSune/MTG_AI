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

from typing import Dict, List, Optional

from MTG_bot.core.ability_tree import (
    Atom,
    ControllerRef,
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
    ZONE_BATTLEFIELD,
    ZONE_COMMAND,
    ZONE_EXILE,
    ZONE_GRAVEYARD,
    ZONE_HAND,
    ZONE_LIBRARY,
)

# ZoneKind enum member -> the state.py zone-kind string.
ZONE_KIND_TO_STATE: Dict[ZoneKind, str] = {
    ZoneKind.LIBRARY: ZONE_LIBRARY,
    ZoneKind.HAND: ZONE_HAND,
    ZoneKind.BATTLEFIELD: ZONE_BATTLEFIELD,
    ZoneKind.GRAVEYARD: ZONE_GRAVEYARD,
    ZoneKind.EXILE: ZONE_EXILE,
    ZoneKind.COMMAND: ZONE_COMMAND,
}


def _opponents(ctx: ExecCtx) -> List[Handle]:
    controller = ctx.controller
    return [p for p in ctx.world.player_order if p != controller]


def players_for_ref(ref: ControllerRef, ctx: ExecCtx) -> List[Handle]:
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
        return [ctx.world.controller_of(bound)]
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
            c if c.namespace == "player" else ctx.world.controller_of(c)
            for c in candidates
        ]
        return actual in players
    if who is ControllerRef.YOU:
        return actual == ctx.controller
    if who in (ControllerRef.OPPONENT, ControllerRef.ALL_OPPONENTS):
        return actual != ctx.controller
    if who is ControllerRef.TARGET_PLAYER:
        bound = ctx.binding_one("target")
        expected: Optional[Handle] = bound
        if bound is not None and bound.namespace == "card":
            expected = ctx.world.controller_of(bound)
        return expected is not None and actual == expected
    return who is ControllerRef.ANY


def zone_owner(ctx: ExecCtx, zone_ir: Zone, owner: Optional[Handle]) -> Handle:
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


def enumerate_zone(ctx: ExecCtx, zone_ir: Zone) -> List[Handle]:
    """The handles in one Zone IR, in **zone order** (order-preserving)."""
    kind = zone_ir.kind
    if kind is ZoneKind.PLAYER:
        return players_for_ref(zone_ir.controller, ctx)
    if kind is ZoneKind.ANY:
        raise NotImplementedError(
            "executor: Zone(ANY) enumeration is 12c's query surface"
        )
    state_kind = ZONE_KIND_TO_STATE[kind]
    ref = zone_ir.controller
    if ref is ControllerRef.OWNER:
        raise NotImplementedError(
            "executor: OWNER in selector enumeration needs per-candidate "
            "owner scoping (12b)"
        )
    handles: List[Handle] = []
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


def resolve_selector(sel: Selector, ctx: ExecCtx) -> List[Handle]:
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
    if sel.referent is not None:
        if sel.referent in ("source", "controller"):
            candidates = [ctx.source if sel.referent == "source" else ctx.controller]
        elif sel.referent == "target":
            bound = ctx.binding_handles("target")
            if bound is None:
                raise ValueError("executor: 'target' referent has no target binding")
            candidates = bound
        elif sel.referent in ("event", "result"):
            # 12b: the trigger firing bound the event/result subject.
            bound = ctx.binding_handles(sel.referent)
            if bound is None:
                raise NotImplementedError(
                    f"executor: selector referent {sel.referent!r} only "
                    "resolves inside a trigger firing (no event register)"
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
        legal = set(candidates)
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


# ---------------------------------------------------------------- role readers


def role_handles(ctx: ExecCtx, atom: Atom, role: str) -> List[Handle]:
    """The handles a target/cards/equipment role acts on, Handle-sorted.

    Bindings take precedence (the caller designated them) EXCEPT for an
    ANAPHORIC Selector — one carrying its own ``referent`` (14c, B-16):
    "the cards the preceding atom found" is a reference the atom resolves
    itself, and a spell-level designation sharing the role NAME must not
    hijack it (Necromentia's EXILE-``target`` grabbed the designated
    OPPONENT under that binding and fed a player handle to ``controller_
    of``). A referent-less Selector stays binding-first (the 12a
    designation convention, ``_binding_atom`` payments included).
    """
    bound = ctx.binding_handles(role)
    value = atom.args.get(role)
    anaphoric = isinstance(value, Selector) and value.referent is not None
    if bound is not None and not anaphoric:
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


def role_players(ctx: ExecCtx, atom: Atom, role: str = "controller") -> List[Handle]:
    bound = ctx.binding_handles(role)
    if bound is not None:
        return bound
    value = atom.args.get(role)
    if isinstance(value, ControllerRef):
        return players_for_ref(value, ctx)
    raise NotImplementedError(
        f"executor: {atom.verb.name} {role!r} referent-selector players are 12b's"
    )


def amount(ctx: ExecCtx, atom: Atom, role: str) -> int:
    quantity = atom.args.get(role)
    if quantity is None:
        raise ValueError(f"executor: {atom.verb.name} missing role {role!r}")
    assert isinstance(quantity, Quantity)
    return resolve(quantity, ctx)
