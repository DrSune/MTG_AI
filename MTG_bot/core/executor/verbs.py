"""Atom handlers for the state-visible v1 verbs (round 12a, /06 §12a).

Dispatch is a flat verb -> handler table: anything the executor cannot
honestly run raises ``NotImplementedError`` *at dispatch time* — never a
silent no-op (North Star; LOOK_AT/REVEAL are the only no-ops and they are
legitimate ones, recorded as events for the future action history).

Determinism contract:
  * multi-object effects iterate their targets **Handle-sorted** (ruling 5)
    — pinned by ``test_handle_sorting_is_canonical``;
  * library operations (draw, mill, scry) iterate **zone order** — the
    designated order-preserving slot (top of library = last entry);
  * randomness (SHUFFLE, RANDOM selectors) flows only through the
    executor-owned :class:`random.Random` seeded from ``master_seed``;
  * enumerable decisions (scry top/bottom, any-colour mana, may-fire)
    arrive as explicit ``decisions`` arguments — zero hidden randomness.

Role names are the frozen ``_VERB_ROLES`` table (ability_tree.py:3213);
designation machinery lives in :mod:`.selectors`.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable

from MTG_bot.core.ability_tree import (
    Ability,
    Atom,
    CounterKind,
    Duration,
    DurationUntilLeaves,
    EventSpec,
    Filter,
    KeywordAbility,
    PtDelta,
    PtDirection,
    Quantity,
    QUnbounded,
    Selector,
    Step,
    TokenSpec,
    Verb,
    Zone,
    ZoneKind,
)
from MTG_bot.core.executor.durations_min import duration_tag
from MTG_bot.core.executor.quantity import (
    ExecCtx,
    eval_filter,
    referent_handle,
    resolve,
)
from MTG_bot.core.executor.selectors import (
    ZONE_KIND_TO_STATE,
    amount,
    resolve_selector,
    role_handles,
    role_player,
    role_players,
    zone_owner,
)
from MTG_bot.core.identity import CardIdentity, Handle
from MTG_bot.core.state import (
    ZONE_BATTLEFIELD,
    ZONE_EXILE,
    ZONE_GRAVEYARD,
    ZONE_HAND,
    ZONE_LIBRARY,
)

_COLORS_VOCAB = ("W", "U", "B", "R", "G", "C")


# ------------------------------------------------------------------- handlers


def _move_to(ctx: ExecCtx, card: Handle, player: Handle, kind: str) -> None:
    src = ctx.world.zone_of(card)
    ctx.world.move_to_zone(card, player, kind)
    ctx.events.append((len(ctx.events), "MOVE", str(card), f"{src.kind}->{kind}"))


def _v_move_zone(ctx: ExecCtx, atom: Atom) -> None:
    dest_ir = atom.args.get("destination")
    assert isinstance(dest_ir, Zone)  # Atom validation guarantees it
    dest_kind = ZONE_KIND_TO_STATE.get(dest_ir.kind)
    if dest_kind is None:
        raise NotImplementedError(
            f"executor: MOVE_ZONE to {dest_ir.kind.name} is not a card zone (12b/12c)"
        )
    tapped_on_enter = bool(atom.args.get("tapped_on_enter"))
    cards = ctx.binding_handles("cards")
    if cards is None:
        # The draw idiom: "move the top n of the library to hand" with no
        # designated cards — n comes from the selector's count.
        sel = atom.args.get("cards")
        if not isinstance(sel, Selector):
            raise ValueError("executor: MOVE_ZONE cards role has no binding")
        n = 0 if isinstance(sel.count, QUnbounded) else resolve(sel.count, ctx)
        if dest_kind == ZONE_HAND and sel.zone.kind is ZoneKind.LIBRARY:
            owner = zone_owner(ctx, dest_ir, owner=ctx.controller)
            lib = ctx.world.players[owner].zone(ZONE_LIBRARY)
            n = min(n, len(lib.entries))
            if owner == ctx.controller:
                ctx.world.draw(ctx.controller, n)  # top = last entry, zone order
            else:
                for _ in range(n):
                    card = lib.entries.pop()
                    ctx.world.players[owner].zone(ZONE_HAND).entries.append(card)
                    ctx.events.append(
                        (len(ctx.events), "MOVE", str(card), "library->hand")
                    )
            return
        pool = [h for h in resolve_selector(sel, ctx) if h.namespace == "card"]
        cards = pool[:n] if n else pool
    for card in cards:
        owner = ctx.world.controller_of(card)
        target_player = zone_owner(ctx, dest_ir, owner=owner)
        src = ctx.world.zone_of(card)
        zone = ctx.world.players[target_player].zone(dest_kind)
        ctx.world.move_card(card, zone)
        if tapped_on_enter and dest_kind == ZONE_BATTLEFIELD:
            ctx.world.cards[card].tapped = True
        ctx.events.append(
            (len(ctx.events), "MOVE", str(card), f"{src.kind}->{dest_kind}")
        )


def _v_exile(ctx: ExecCtx, atom: Atom) -> None:
    for card in role_handles(ctx, atom, "target"):
        _move_to(ctx, card, ctx.world.controller_of(card), ZONE_EXILE)


def _to_graveyard(ctx: ExecCtx, atom: Atom) -> None:
    for card in role_handles(ctx, atom, "target"):
        _move_to(ctx, card, ctx.world.controller_of(card), ZONE_GRAVEYARD)


def _v_discard(ctx: ExecCtx, atom: Atom) -> None:
    player = role_player(ctx, atom)
    cards = ctx.binding_handles("cards")
    if cards is None:
        sel = atom.args.get("cards")
        if not isinstance(sel, Selector):
            raise ValueError("executor: DISCARD cards role has no binding")
        cards = resolve_selector(sel, ctx)
    hand = ctx.world.players[player].zone(ZONE_HAND).entries
    for card in sorted(cards):
        if card not in hand:
            raise ValueError(f"executor: DISCARD card {card} is not in {player}'s hand")
        _move_to(ctx, card, player, ZONE_GRAVEYARD)


def _v_mill(ctx: ExecCtx, atom: Atom) -> None:
    player = role_player(ctx, atom)
    n = amount(ctx, atom, "amount")
    lib = ctx.world.players[player].zone(ZONE_LIBRARY)
    gy = ctx.world.players[player].zone(ZONE_GRAVEYARD)
    for _ in range(min(n, len(lib.entries))):
        card = lib.entries.pop()  # top of library, zone order
        gy.entries.append(card)
        ctx.events.append((len(ctx.events), "MILL", str(card), "library->graveyard"))


def _v_gain_life(ctx: ExecCtx, atom: Atom) -> None:
    n = amount(ctx, atom, "amount")
    for player in sorted(role_players(ctx, atom)):
        ctx.world.players[player].life += n
        ctx.events.append((len(ctx.events), "GAIN_LIFE", str(player), n))


def _v_lose_life(ctx: ExecCtx, atom: Atom) -> None:
    n = amount(ctx, atom, "amount")
    for player in sorted(role_players(ctx, atom)):
        p = ctx.world.players[player]
        p.life = max(0, p.life - n)  # life clamps at 0; deaths are 12b state-checks
        ctx.events.append((len(ctx.events), "LOSE_LIFE", str(player), p.life))


def _v_deal_damage(ctx: ExecCtx, atom: Atom) -> None:
    if atom.args.get("dealer") is not None or atom.args.get("recipient") is not None:
        raise NotImplementedError(
            "executor: DEAL_DAMAGE dealer/recipient (C-4 damage surface) is 12b/12d"
        )
    n = amount(ctx, atom, "amount")
    for target in role_handles(ctx, atom, "target"):
        if target.namespace == "player":
            # 12d: C24 replacement-before-apply. A live ReplacementAbility
            # (Nine Lives' compiled row is the canonical) CONSUMES the
            # event: no life mutation happens (so the journal sees no
            # damage at all), and the replacement's action runs as a
            # nested journalled effect once this atom's boundary closes.
            repl = (
                ctx.replacements.replacement_for_player_damage(ctx, target)
                if ctx.replacements is not None
                else None
            )
            if repl is not None:
                ctx.pending_replacements.append(repl)
                ctx.events.append(
                    (
                        len(ctx.events),
                        "DAMAGE_REPLACED",
                        str(target),
                        str(repl.source),
                        n,
                    )
                )
                continue
            p = ctx.world.players[target]
            p.life = max(0, p.life - n)
            ctx.events.append((len(ctx.events), "DAMAGE", str(target), p.life))
            continue
        _, toughness = ctx.effective_pt(target)  # ledger-aware PT
        if toughness is not None and n >= toughness:
            _move_to(ctx, target, ctx.world.controller_of(target), ZONE_GRAVEYARD)
            ctx.events.append((len(ctx.events), "DAMAGE_LETHAL", str(target), n))
        else:
            ctx.events.append((len(ctx.events), "DAMAGE", str(target), n))


def _set_tapped(ctx: ExecCtx, atom: Atom, tapped: bool) -> None:
    if atom.args.get("duration") is not None:
        raise NotImplementedError(
            "executor: duration-tagged TAP/UNTAP is 12d (the ledger vocab)"
        )
    for card in role_handles(ctx, atom, "target"):
        ctx.world.cards[card].tapped = tapped
        ctx.events.append((len(ctx.events), atom.verb.name, str(card), int(tapped)))


def _v_tap(ctx: ExecCtx, atom: Atom) -> None:
    _set_tapped(ctx, atom, True)


def _v_untap(ctx: ExecCtx, atom: Atom) -> None:
    _set_tapped(ctx, atom, False)


def _v_put_counter(ctx: ExecCtx, atom: Atom) -> None:
    kind = atom.args.get("counter_kind")
    assert isinstance(kind, CounterKind)
    n = amount(ctx, atom, "count")
    for card in role_handles(ctx, atom, "target"):
        counters = ctx.world.cards[card].counters
        counters[kind.name] = counters.get(kind.name, 0) + n
        ctx.events.append((len(ctx.events), "PUT_COUNTER", str(card), kind.name, n))


def _v_remove_counter(ctx: ExecCtx, atom: Atom) -> None:
    kind = atom.args.get("counter_kind")
    assert isinstance(kind, CounterKind)
    n = amount(ctx, atom, "count")
    for card in role_handles(ctx, atom, "target"):
        counters = ctx.world.cards[card].counters
        remaining = max(0, counters.get(kind.name, 0) - n)
        if remaining:
            counters[kind.name] = remaining
        else:
            counters.pop(kind.name, None)
        ctx.events.append((len(ctx.events), "REMOVE_COUNTER", str(card), kind.name, n))


def _pt_delta_value(quantity: object, ctx: ExecCtx) -> int:
    """power/toughness role -> a signed int adjustment (C17: PtDelta keeps
    magnitudes non-negative; a bare Quantity reads as an increase)."""
    if isinstance(quantity, PtDelta):
        magnitude = resolve(quantity.magnitude, ctx)
        if quantity.direction is PtDirection.DECREASE:
            return -magnitude
        return magnitude
    assert isinstance(quantity, Quantity)
    return resolve(quantity, ctx)


def pt_atom_delta(atom: Atom, ctx: ExecCtx) -> tuple[int, int, int | None, int | None]:
    """One MODIFY_PT/SET_PT atom -> ``(power_delta, toughness_delta,
    power_set, toughness_set)`` — the shared extraction the 12a fold and
    12d's static-layer materialization both run through (one numeric
    semantics, no second parser)."""
    power_role = atom.args.get("power")
    tough_role = atom.args.get("toughness")
    if atom.verb is Verb.MODIFY_PT:
        p_delta = _pt_delta_value(power_role, ctx) if power_role is not None else 0
        t_delta = _pt_delta_value(tough_role, ctx) if tough_role is not None else 0
        return p_delta, t_delta, None, None
    if isinstance(power_role, PtDelta) or isinstance(tough_role, PtDelta):
        raise NotImplementedError(
            "executor: SET_PT with a PtDelta (signed absolute) is undefined (12c)"
        )
    assert power_role is None or isinstance(power_role, Quantity)
    assert tough_role is None or isinstance(tough_role, Quantity)
    return (
        0,
        0,
        None if power_role is None else resolve(power_role, ctx),
        None if tough_role is None else resolve(tough_role, ctx),
    )


def _apply_pt(ctx: ExecCtx, atom: Atom, kind: str) -> None:
    duration = atom.args.get("duration")
    assert duration is None or isinstance(duration, Duration)
    tag = duration_tag(duration)
    # 12d: UNTIL_LEAVES resolves its C12 referent NOW (register boundary) —
    # the ledger stores a Handle anchor, never a string to re-parse later.
    leaves_anchor = None
    if isinstance(duration, DurationUntilLeaves):
        leaves_anchor = referent_handle(duration.source, ctx)
    p_delta, t_delta, p_set, t_set = pt_atom_delta(atom, ctx)
    for card in role_handles(ctx, atom, "target"):
        identity = ctx.world.cards[card].identity
        change = ctx.ledger.record(
            identity,
            kind,
            card,
            power_delta=p_delta,
            toughness_delta=t_delta,
            power_set=p_set,
            toughness_set=t_set,
            tag=tag,
            clock=len(ctx.events),
            duration=duration,
            source=ctx.source,
            controller=ctx.controller,
            leaves_anchor=leaves_anchor,
        )
        ctx.events.append(
            (
                len(ctx.events),
                atom.verb.name,
                str(card),
                tag,
                change.was_power,
                change.was_toughness,
            )
        )


def _v_modify_pt(ctx: ExecCtx, atom: Atom) -> None:
    _apply_pt(ctx, atom, "delta")


def _v_set_pt(ctx: ExecCtx, atom: Atom) -> None:
    _apply_pt(ctx, atom, "set")


# ------------------------------------------------------ 12d layer verbs


def _ability_tag(ability: object) -> str:
    """The audit label for a grant/lose payload row (the fingerprint never
    depends on it for semantics — the full node reprs in the layer dump)."""
    if isinstance(ability, KeywordAbility):
        return f"keyword:{ability.keyword.name}"
    return type(ability).__name__


def _layers_or_raise(ctx: ExecCtx, verb: str):
    if ctx.layers is None:
        raise ValueError(
            f"executor: {verb} needs an executor-backed ExecCtx "
            "(bare ExecCtx has no layer registry)"
        )
    return ctx.layers


def _v_grant_or_lose(ctx: ExecCtx, atom: Atom, lose: bool) -> None:
    """GRANT_ABILITY / LOSE_ABILITY (the PC-6 #3 raise-list items, 12d):
    register a layer over the designated targets; the Duration vocab
    (incl. until-end-of-turn) is what ends it — layers never expire
    silently."""
    ability = atom.args.get("ability")
    if not isinstance(ability, Ability):
        raise ValueError(  # noqa: TRY004 — domain contract, see activate()
            f"executor: {atom.verb.name} ability role needs an Ability node, "
            f"got {type(ability).__name__}"
        )
    duration = atom.args.get("duration")
    assert duration is None or isinstance(duration, Duration)
    layers = _layers_or_raise(ctx, atom.verb.name)
    targets = tuple(role_handles(ctx, atom, "target"))
    if lose:
        layers.register_lose(ctx.source, ctx.controller, targets, ability, duration)
    else:
        layers.register_grant(ctx.source, ctx.controller, targets, ability, duration)
    ctx.events.append(
        (
            len(ctx.events),
            atom.verb.name,
            str(ctx.source),
            _ability_tag(ability),
            tuple(str(t) for t in targets),
            duration_tag(duration),
        )
    )


def _v_grant(ctx: ExecCtx, atom: Atom) -> None:
    _v_grant_or_lose(ctx, atom, lose=False)


def _v_lose(ctx: ExecCtx, atom: Atom) -> None:
    _v_grant_or_lose(ctx, atom, lose=True)


def _v_prevent(ctx: ExecCtx, atom: Atom) -> None:
    """PREVENT_EFFECT (12d): a pre-application veto record. The condition's
    affected set is materialized NOW from the designated targets (the
    IS_ANY_TARGET anaphora is only decidable at this boundary); combat- and
    mana-side prevents register + expose but have no consumer until the
    combat/mana phases — the UNTAP step consumes the TapStateEvent family
    (Frost Breath)."""
    condition = atom.args.get("condition")
    event = atom.args.get("event")
    assert isinstance(condition, Filter) and isinstance(event, EventSpec)
    step = atom.args.get("step")
    assert step is None or isinstance(step, Step)
    duration = atom.args.get("duration")
    assert duration is None or isinstance(duration, Duration)
    if atom.args.get("controller") is not None:
        raise NotImplementedError("executor: PREVENT_EFFECT controller scoping is 12e")
    if ctx.replacements is None:
        raise ValueError("executor: PREVENT_EFFECT needs an executor-backed ExecCtx")
    designated = ctx.binding_handles("target") or []
    targets = tuple(h for h in designated if eval_filter(condition, h, ctx))
    ctx.replacements.register_prevention(
        ctx.source, ctx.controller, condition, event, step, duration, targets
    )
    ctx.events.append(
        (
            len(ctx.events),
            atom.verb.name,
            str(ctx.source),
            type(event).__name__,
            step.name if step is not None else None,
            duration_tag(duration),
            tuple(str(t) for t in targets),
        )
    )


def token_oracle_id(name: str) -> str:
    """The synthetic token oracle id: a deterministic uuid-shaped hash of
    the token's name. Stable across worlds, distinct per name."""
    digest = hashlib.sha256(("mtg-token:" + name).encode()).hexdigest()
    return (
        f"{digest[:8]}-{digest[8:12]}-{digest[12:16]}-{digest[16:20]}-{digest[20:32]}"
    )


def _v_create_token(ctx: ExecCtx, atom: Atom) -> None:
    spec = atom.args.get("tokens")
    assert isinstance(spec, TokenSpec)
    count_quantity = atom.args.get("count")
    assert count_quantity is None or isinstance(count_quantity, Quantity)
    n = 1 if count_quantity is None else resolve(count_quantity, ctx)
    for _ in range(n):
        power = None if spec.power is None else resolve(spec.power, ctx)
        toughness = None if spec.toughness is None else resolve(spec.toughness, ctx)
        identity = CardIdentity(
            oracle_id=token_oracle_id(spec.name),
            name=spec.name,
            type_line=spec.type_line,
            colors=(spec.color,) if spec.color else (),
            power=None if power is None else str(power),
            toughness=None if toughness is None else str(toughness),
            keywords=tuple(k.name for k in spec.keywords),
            is_token=True,
        )
        handle = ctx.world.add_card(identity, ctx.controller, ZONE_BATTLEFIELD)
        if spec.enters_tapped:
            ctx.world.cards[handle].tapped = True
        seq = ctx.token_counts.get(spec.name, 0)
        ctx.token_counts[spec.name] = seq + 1
        ctx.events.append(
            (
                len(ctx.events),
                "CREATE_TOKEN",
                spec.name,
                f"token:{spec.name}:{seq}",
                str(handle),
            )
        )


def _v_add_mana(ctx: ExecCtx, atom: Atom) -> None:
    player = role_player(ctx, atom)
    n = amount(ctx, atom, "amount")
    color = atom.args.get("color")
    if color is None or color == "ANY":
        color = ctx.take_decision(_COLORS_VOCAB, "ADD_MANA any-colour")
    elif isinstance(color, str) and color in _COLORS_VOCAB:
        pass
    else:
        raise ValueError(f"executor: ADD_MANA colour {color!r} not in {_COLORS_VOCAB}")
    pool = ctx.world.players[player].mana_pool
    pool[color] = pool.get(color, 0) + n
    ctx.events.append((len(ctx.events), "ADD_MANA", str(player), color, n))


def _v_scry(ctx: ExecCtx, atom: Atom) -> None:
    player = role_player(ctx, atom)
    n = amount(ctx, atom, "count")
    lib = ctx.world.players[player].zone(ZONE_LIBRARY)
    n = min(n, len(lib.entries))
    top_down = list(reversed(lib.entries[-n:])) if n else []
    bottoms: list[Handle] = []
    tops: list[Handle] = []
    for card in top_down:  # decisions are consumed one per card, top first
        if ctx.take_decision(("top", "bottom"), "SCRY") == "top":
            tops.append(card)
        else:
            bottoms.append(card)
    # Canonical within-group order (the rules let the scryer order each
    # group freely; we pin Handle-ascending, ascending = toward the top).
    lib.entries = lib.entries[: len(lib.entries) - n] + sorted(bottoms) + sorted(tops)
    ctx.events.append((len(ctx.events), "SCRY", str(player), n))


def _v_shuffle(ctx: ExecCtx, atom: Atom) -> None:
    zone_ir = atom.args.get("zone")
    assert isinstance(zone_ir, Zone)
    state_kind = ZONE_KIND_TO_STATE.get(zone_ir.kind)
    if state_kind is None:
        raise NotImplementedError("executor: SHUFFLE of a non-card zone is 12c")
    owner = zone_owner(ctx, zone_ir, owner=ctx.controller)
    zone = ctx.world.players[owner].zone(state_kind)
    rng = ctx.rng("SHUFFLE")
    rng.shuffle(zone.entries)  # seeded Random — replay-identical
    ctx.events.append((len(ctx.events), "SHUFFLE", str(owner), zone.kind))


def _look(ctx: ExecCtx, atom: Atom) -> None:
    """LOOK_AT / REVEAL: a legitimate recorded no-op (action history, 12b).

    Top-N-of-library implicit per the REVEAL/LOOK_AT convention (doc /10):
    nothing moves; the knowledge is the event record."""
    if atom.args.get("duration") is not None:
        raise NotImplementedError(
            f"executor: continuous {atom.verb.name} (duration) is 12d"
        )
    player = role_player(ctx, atom)
    lib = ctx.world.players[player].zone(ZONE_LIBRARY)
    count_q = atom.args.get("count")
    if isinstance(count_q, QUnbounded):
        # 13a: QUnbounded is not number-resolvable, and here it means the
        # ENTIRE zone — the Cultivate compile idiom (REVEAL with an
        # unbounded count "counts" the searched library; the grammar's
        # documented inability to reference the found set).
        seen = tuple(str(c) for c in reversed(lib.entries))
    else:
        n = amount(ctx, atom, "count")
        seen = tuple(str(c) for c in reversed(lib.entries[-n:])) if n else ()
    ctx.events.append((len(ctx.events), atom.verb.name, str(player), seen))


# ------------------------------------------------------- 13a turn/library verbs


def _v_draw(ctx: ExecCtx, atom: Atom) -> None:
    """DRAW (13a): :meth:`GameWorld.draw` takes the top of the library
    (last entry, zone order); an empty library no-ops (CR 121.2 — the draw
    attempt itself is free; the loss is a state-check later). The journal
    auto-detects the library->hand move and emits CARD_DRAWN with the
    (drawer, ordinal) payload (events.py) — this row is the 12a-style
    audit line, mirroring MILL/MOVE."""
    player = role_player(ctx, atom, "controller")
    count_q = atom.args.get("amount")
    assert count_q is None or isinstance(count_q, Quantity)
    n = 1 if count_q is None else resolve(count_q, ctx)
    ctx.world.draw(player, n)
    ctx.events.append((len(ctx.events), "DRAW", str(player), n))


def _search_designation(atom: Atom, ctx: ExecCtx) -> list[Handle]:
    """The SEARCH ``cards`` role designation — the shared enumeration the
    handler runs and :func:`MTG_bot.core.executor.query.legal_search`
    mirrors. Explicit bindings take precedence (the caller designated the
    found cards — the e2e/Slate surface); otherwise the selector resolves
    through the 12a machinery: CHOOSE = deterministic first-n-sorted
    stand-in, RANDOM = seeded ctx.rng draw; an undesignated ONE_OF/TARGET
    propagates the existing clean raise (never a guess)."""
    cards = ctx.binding_handles("cards")
    if cards is not None:
        return cards
    sel = atom.args.get("cards")
    if not isinstance(sel, Selector):
        # ValueError, not TypeError: the domain contract is "this atom has
        # no designation" (mirrors the TARGET-selector raise in selectors).
        raise ValueError(  # noqa: TRY004
            "executor: SEARCH cards role has no binding"
        )
    return [h for h in resolve_selector(sel, ctx) if h.namespace == "card"]


def _v_search(ctx: ExecCtx, atom: Atom) -> None:
    """SEARCH (13a, the Cultivate compile idiom — see
    ``compiler/templates_b5b.py::_build_cultivate_search``): designate the
    found cards, then MOVE each from its current zone to the destination.
    The compiler's documented debt is CARD-level divergence (the ONE_OF/
    REST split re-searches the library in sibling atoms); per-ATOM
    faithfulness is what this handler owns. The destination is role-based
    (``zone_owner`` resolves the Zone's ControllerRef), ``tapped_on_enter``
    is honored on battlefield entry, and every move gets its journal row."""
    dest_ir = atom.args.get("destination")
    assert isinstance(dest_ir, Zone)  # Atom validation guarantees it
    dest_kind = ZONE_KIND_TO_STATE.get(dest_ir.kind)
    if dest_kind is None:
        raise NotImplementedError(
            f"executor: SEARCH to {dest_ir.kind.name} is not a card zone (13a)"
        )
    tapped_on_enter = bool(atom.args.get("tapped_on_enter"))
    cards = _search_designation(atom, ctx)
    for card in cards:
        owner = ctx.world.controller_of(card)
        target_player = zone_owner(ctx, dest_ir, owner=owner)
        src = ctx.world.zone_of(card)
        zone = ctx.world.players[target_player].zone(dest_kind)
        ctx.world.move_card(card, zone)
        if tapped_on_enter and dest_kind == ZONE_BATTLEFIELD:
            ctx.world.cards[card].tapped = True
        ctx.events.append(
            (len(ctx.events), "SEARCH", str(card), f"{src.kind}->{dest_kind}")
        )


def _executor_or_raise(ctx: ExecCtx, verb: str):
    """13a turn-state verbs (FLIP_COIN/END_TURN/EXTRA_TURN/LOSE_GAME) mutate
    EXECUTOR-side ledgers (the frozen state carries no flip/turn/loss
    fields) — a bare unit-test ExecCtx has none."""
    if ctx.executor is None:
        raise ValueError(
            f"executor: {verb} needs an executor-backed ExecCtx "
            "(bare ExecCtx has no turn ledger)"
        )
    return ctx.executor


def _v_flip_coin(ctx: ExecCtx, atom: Atom) -> None:
    """FLIP_COIN (13a, Tavern Swindler): the flip is the ONLY randomness —
    it flows through the executor-owned seeded ``ctx.rng`` (replay
    identical). Heads -> ``ctx.controller`` wins; tails -> the FIRST
    opponent wins (2-player simplification: the grammar's who-gates are
    YOU/opponent pairs, and every corpus flip card is 2-player — a
    multi-player tie-break order is untested debt). The winner lives on
    the executor because the FLIP_WON conditional is a SEPARATE ability
    row (two compiled rows per Tavern Swindler)."""
    executor = _executor_or_raise(ctx, atom.verb.name)
    rng = ctx.rng("FLIP_COIN")
    heads = rng.random() < 0.5
    if heads:
        winner = ctx.controller
    else:
        opponents = sorted(p for p in ctx.world.player_order if p != ctx.controller)
        winner = opponents[0] if opponents else ctx.controller
    executor.last_flip_won_by = winner
    ctx.events.append(
        (
            len(ctx.events),
            "FLIP_COIN",
            "HEADS" if heads else "TAILS",
            str(winner),
        )
    )


def _v_end_turn(ctx: ExecCtx, atom: Atom) -> None:
    """END_TURN (13a, Discontinuity): the request flag is set here; the
    actual close (marker + Eot sweeps) runs in the executor loop after the
    current op's settle, so the turn still closes through the ONE turn
    skeleton (:meth:`Executor.end_turn`) — no second end-of-turn path."""
    executor = _executor_or_raise(ctx, atom.verb.name)
    executor.end_turn_requested = True
    # The clock moves ahead of the close: an activation attempted later in
    # the SAME op is already out of the sorcery window (legality reads
    # ``executor.phase``), and :meth:`Executor.end_turn` re-stamps it.
    executor.phase = "END_TURN"
    ctx.events.append((len(ctx.events), "END_TURN", str(ctx.controller)))


def _v_extra_turn(ctx: ExecCtx, atom: Atom) -> None:
    """EXTRA_TURN (13a, Teferi's -10 / Extra Turns): enqueue the controller
    ``count`` times — :meth:`Executor.advance_turn` pops the queue before
    rotating, which is exactly CR 500.7's "next turn belongs to that
    player" for consecutive grants (documented simplification: nested
    extra turns from DIFFERENT players resolve queue-order, not the full
    CR 500.7 dependency ordering)."""
    executor = _executor_or_raise(ctx, atom.verb.name)
    count_q = atom.args.get("count")
    assert count_q is None or isinstance(count_q, Quantity)
    n = 1 if count_q is None else resolve(count_q, ctx)
    for _ in range(n):
        executor.extra_turn_queue.append(ctx.controller)
    ctx.events.append((len(ctx.events), "EXTRA_TURN", str(ctx.controller), n))


def _v_lose_game(ctx: ExecCtx, atom: Atom) -> None:
    """LOSE_GAME (13a): the frozen GameWorld carries no per-player lost
    flag (state.py is frozen) — so the loss lands on an EXECUTOR-side
    ledger, a documented divergence from a state-side flag; game-over
    evaluation (and the emptied library's CR 121.3 loss) is the later
    state-check phase."""
    executor = _executor_or_raise(ctx, atom.verb.name)
    executor.lost_players.append(ctx.controller)
    ctx.events.append((len(ctx.events), "LOSE_GAME", str(ctx.controller)))


HANDLERS: dict[Verb, Callable[[ExecCtx, Atom], None]] = {
    Verb.MOVE_ZONE: _v_move_zone,
    Verb.EXILE: _v_exile,
    Verb.SACRIFICE: _to_graveyard,
    Verb.DESTROY: _to_graveyard,
    Verb.DISCARD: _v_discard,
    Verb.MILL: _v_mill,
    Verb.GAIN_LIFE: _v_gain_life,
    Verb.LOSE_LIFE: _v_lose_life,
    Verb.DEAL_DAMAGE: _v_deal_damage,
    Verb.TAP: _v_tap,
    Verb.UNTAP: _v_untap,
    Verb.PUT_COUNTER: _v_put_counter,
    Verb.REMOVE_COUNTER: _v_remove_counter,
    Verb.MODIFY_PT: _v_modify_pt,
    Verb.SET_PT: _v_set_pt,
    Verb.CREATE_TOKEN: _v_create_token,
    Verb.ADD_MANA: _v_add_mana,
    Verb.SCRY: _v_scry,
    Verb.SHUFFLE: _v_shuffle,
    Verb.LOOK_AT: _look,
    Verb.REVEAL: _look,
    # 12d: the continuous-layers verbs (PC-6 #3 raise-list items, now real)
    # + the pre-application prevention record.
    Verb.GRANT_ABILITY: _v_grant,
    Verb.LOSE_ABILITY: _v_lose,
    Verb.PREVENT_EFFECT: _v_prevent,
    # 13a: the library/turn-flow verbs. SUPPORTED_VERBS_V1 stays the frozen
    # round-12 24-set (a V1 *contract* pin); V2 is what this table derives.
    Verb.DRAW: _v_draw,
    Verb.SEARCH: _v_search,
    Verb.FLIP_COIN: _v_flip_coin,
    Verb.END_TURN: _v_end_turn,
    Verb.EXTRA_TURN: _v_extra_turn,
    Verb.LOSE_GAME: _v_lose_game,
}


def run_atom(atom: Atom, ctx: ExecCtx) -> None:
    """Dispatch one Atom to its handler; unsupported verbs RAISE."""
    handler = HANDLERS.get(atom.verb)
    if handler is None:
        raise NotImplementedError(f"executor: verb {atom.verb.name} not implemented")
    handler(ctx, atom)
