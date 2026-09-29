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
from typing import Callable, Dict, List

from MTG_bot.core.ability_tree import (
    Atom,
    CounterKind,
    Duration,
    PtDelta,
    PtDirection,
    Quantity,
    QUnbounded,
    Selector,
    TokenSpec,
    Verb,
    Zone,
    ZoneKind,
)
from MTG_bot.core.executor.durations_min import duration_tag
from MTG_bot.core.executor.quantity import ExecCtx, resolve
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


def _apply_pt(ctx: ExecCtx, atom: Atom, kind: str) -> None:
    duration = atom.args.get("duration")
    assert duration is None or isinstance(duration, Duration)
    tag = duration_tag(duration)
    power_role = atom.args.get("power")
    tough_role = atom.args.get("toughness")
    for card in role_handles(ctx, atom, "target"):
        identity = ctx.world.cards[card].identity
        if kind == "delta":
            p_delta = _pt_delta_value(power_role, ctx) if power_role is not None else 0
            t_delta = _pt_delta_value(tough_role, ctx) if tough_role is not None else 0
            change = ctx.ledger.record(
                identity,
                "delta",
                card,
                power_delta=p_delta,
                toughness_delta=t_delta,
                tag=tag,
                clock=len(ctx.events),
            )
        else:
            if isinstance(power_role, PtDelta) or isinstance(tough_role, PtDelta):
                raise NotImplementedError(
                    "executor: SET_PT with a PtDelta (signed absolute) is "
                    "undefined (12c)"
                )
            assert power_role is None or isinstance(power_role, Quantity)
            assert tough_role is None or isinstance(tough_role, Quantity)
            change = ctx.ledger.record(
                identity,
                "set",
                card,
                power_set=None if power_role is None else resolve(power_role, ctx),
                toughness_set=None if tough_role is None else resolve(tough_role, ctx),
                tag=tag,
                clock=len(ctx.events),
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
    bottoms: List[Handle] = []
    tops: List[Handle] = []
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
    n = amount(ctx, atom, "count")
    lib = ctx.world.players[player].zone(ZONE_LIBRARY)
    seen = tuple(str(c) for c in reversed(lib.entries[-n:])) if n else ()
    ctx.events.append((len(ctx.events), atom.verb.name, str(player), seen))


HANDLERS: Dict[Verb, Callable[[ExecCtx, Atom], None]] = {
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
}


def run_atom(atom: Atom, ctx: ExecCtx) -> None:
    """Dispatch one Atom to its handler; unsupported verbs RAISE."""
    handler = HANDLERS.get(atom.verb)
    if handler is None:
        raise NotImplementedError(f"executor: verb {atom.verb.name} not implemented")
    handler(ctx, atom)
