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
    ActivationWindow,
    Atom,
    Cost,
    CounterKind,
    Duration,
    DurationUntilLeaves,
    EventSpec,
    FAnd,
    FAtom,
    Filter,
    FNot,
    FOr,
    KeywordAbility,
    PtDelta,
    PtDirection,
    QConst,
    Quantity,
    QUnbounded,
    Selector,
    SelectorMode,
    Step,
    TokenSpec,
    Verb,
    Zone,
    ZoneKind,
)
from MTG_bot.core.executor.decisions import site_digest
from MTG_bot.core.executor.durations_min import duration_tag
from MTG_bot.core.executor.events import KIND_GAME_LOST
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
        # 14c (B-13): the ONE_OF/REST partition modes SELECT specific
        # cards (the pick / its complement) — the top-n draw idiom and the
        # count clamp apply to the CHOOSE/draw idioms only; a partition
        # atom moves exactly what its Selector resolves.
        partition = sel.mode in (SelectorMode.ONE_OF, SelectorMode.REST)
        if (
            not partition
            and dest_kind == ZONE_HAND
            and sel.zone.kind is ZoneKind.LIBRARY
        ):
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
        cards = pool if partition else (pool[:n] if n else pool)
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
    # 14e (B-9) producer: the MOVED cards are the register ("…put it onto
    # the battlefield…. It gains haste" — the Liliana, Waker of the Dead
    # emblem tail 14b-1 attached; inside a firing the seed was the event
    # subject, but the ACTION's object is the honest antecedent). The
    # top-n draw-idiom early-returns above write nothing: no object was
    # chosen, and an unset register stays a loud read.
    ctx.bindings["result"] = list(cards)


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
        if (
            sel.referent is not None
            or sel.mode is SelectorMode.TARGET
            or sel.mode in (SelectorMode.ONE_OF, SelectorMode.REST)
        ):
            # designation / anaphora / partition paths all self-resolve
            # (the 13b 'result' register, the B-15 designation, the B-13
            # channel ask) — the hand scoping below is only for the raw
            # engine-side CHOOSE/RANDOM/ALL stand-ins.
            cards = resolve_selector(sel, ctx)
        else:
            # 14c (B-18): CR 701.8a — a discard moves cards from the
            # ACTOR'S OWN hand, so the selection pool is the actor's LIVE
            # hand re-read at take time, filtered through the Selector.
            # Bad Deal's compiled zone is Zone(HAND, ANY) (the documented
            # card-level divergence: the discarding player lives in the
            # ``controller`` role) and the raw Selector population spans
            # both hands — the Handle-sorted CHOOSE/RANDOM stand-ins were
            # picking the OTHER player's cards, and the not-in-hand raise
            # ended the game. C17 clamp: fewer cards than the ceiling in
            # hand simply discards fewer.
            live = list(ctx.world.players[player].zone(ZONE_HAND).entries)
            pool = sorted(h for h in live if eval_filter(sel.filter, h, ctx))
            if sel.mode is SelectorMode.RANDOM:
                rng = ctx.rng("RANDOM")
                rng.shuffle(pool)  # seeded: replay-identical
            cards = (
                pool
                if isinstance(sel.count, QUnbounded)
                else pool[: resolve(sel.count, ctx)]
            )
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
        # 16a (CR 120.4/120.6): damage is MARKED, never instant-lethal. The
        # mark rides the executor's damage ledger and the settle tail's
        # state-based check (CR 704.5a) does the destroying — so two
        # creatures trading non-lethal blows both survive, and a lethal
        # exchange is a simultaneous double kill. The DAMAGE tuple keeps
        # feeding the journal's KIND_DAMAGE row (events.py), so "is dealt
        # damage" triggers (Brash Taunter) are unchanged.
        _deal_damage_to_card(ctx, target, n)


def _deal_damage_to_card(ctx: ExecCtx, target: Handle, n: int) -> None:
    """One card-side damage application: mark it, journal it, decide nothing."""
    if ctx.executor is None:
        raise ValueError(
            "executor: card damage needs an executor-backed ExecCtx "
            "(bare ExecCtx has no damage ledger)"
        )
    ctx.executor.mark_damage(target, n)
    ctx.events.append((len(ctx.events), "DAMAGE", str(target), n))


def _fight_attacker(ctx: ExecCtx) -> Handle:
    """The compiled FIGHT atom carries NO attacker role (the orphan-verb
    precedent, ability_tree R7-8): the attacker is the ability's SOURCE
    when that source is a battlefield permanent (Brash Taunter's
    {2}{R}{T} — "this creature fights"), else the PRECEDING atom's
    result register (Primal Might's "it also fights" anaphora, the
    compiler's documented executor-side binding — _apply_pt writes it)."""
    if (
        ctx.source.namespace == "card"
        and ctx.source in ctx.world.cards
        and ctx.world.zone_of(ctx.source).kind == ZONE_BATTLEFIELD
    ):
        return ctx.source
    result = ctx.binding_handles("result")
    if result:
        return result[0]
    raise NotImplementedError(
        f"executor: FIGHT has no attacker — {ctx.source} is not a battlefield "
        "permanent and no preceding atom wrote the result register"
    )


def _v_fight(ctx: ExecCtx, atom: Atom) -> None:
    """16a (CR 701.12b): "This creature fights another target creature" —
    each deals damage equal to its POWER to the other, simultaneously, and
    it is NOT combat damage (so no "whenever blocks/hits" reading; plain
    damage triggers do see it, CR 701.12e). Simultaneity is what the
    marked-damage ledger buys for free: both marks land inside this ONE
    atom boundary and the settle SBA resolves the exchange — a mutual kill
    kills both, a non-lethal trade leaves both standing.

    A CHOOSE/ONE_OF/RANDOM designation is resolved by the ATOM ITSELF
    (C-1/C-15: a resolution-time decision — the B-16 binding-first rule
    exists so a spell designation never hijacks an ANAPHORIC selector;
    here the hijack runs the other way: Primal Might's spell-level
    "target" IS its own +X/+X creature, and feeding it back would turn
    "fights ANOTHER creature" into a self-punch). TARGET mode keeps the
    ordinary designation path (Brash's activation designated the foe)."""
    attacker = _fight_attacker(ctx)
    sel = atom.args.get("target")
    if isinstance(sel, Selector) and sel.mode in (
        SelectorMode.CHOOSE,
        SelectorMode.ONE_OF,
        SelectorMode.RANDOM,
    ):
        foes = sorted(resolve_selector(sel, ctx))
    else:
        foes = role_handles(ctx, atom, "target")
    if not foes:
        # C17 clamp: nothing legal to fight — the fight simply is not.
        ctx.events.append((len(ctx.events), "FIGHT", str(attacker), None))
        return
    foe = foes[0]  # the compiled FIGHT surface designates exactly one
    ctx.events.append((len(ctx.events), "FIGHT", str(attacker), str(foe)))
    for a, b in ((attacker, foe), (foe, attacker)):
        power, _toughness = ctx.effective_pt(a)
        if power and power > 0:
            _deal_damage_to_card(ctx, b, power)


def _set_tapped(ctx: ExecCtx, atom: Atom, tapped: bool) -> None:
    if atom.args.get("duration") is not None:
        raise NotImplementedError(
            "executor: duration-tagged TAP/UNTAP is 12d (the ledger vocab)"
        )
    cards = role_handles(ctx, atom, "target")
    for card in cards:
        ctx.world.cards[card].tapped = tapped
        ctx.events.append((len(ctx.events), atom.verb.name, str(card), int(tapped)))
    # 14e (B-9): the object of the last ACTION is the closed anaphora's
    # antecedent ("Tap target creature: it gains X" / Traitorous Greed's
    # "Untap that creature. It gains haste"). The ``result`` register was
    # the trigger firing's alone; producers now write it INSIDE any effect
    # execution (per-resolution: the ctx's bindings dict is fresh per
    # execute/apply_effect/cast_ctx — 14c SEARCH/CHOOSE set the pattern).
    ctx.bindings["result"] = list(cards)


def _v_tap(ctx: ExecCtx, atom: Atom) -> None:
    _set_tapped(ctx, atom, True)


def _v_untap(ctx: ExecCtx, atom: Atom) -> None:
    _set_tapped(ctx, atom, False)


def _v_put_counter(ctx: ExecCtx, atom: Atom) -> None:
    kind = atom.args.get("counter_kind")
    assert isinstance(kind, CounterKind)
    n = amount(ctx, atom, "count")
    cards = role_handles(ctx, atom, "target")
    for card in cards:
        counters = ctx.world.cards[card].counters
        counters[kind.name] = counters.get(kind.name, 0) + n
        ctx.events.append((len(ctx.events), "PUT_COUNTER", str(card), kind.name, n))
    # 14e (B-9) producer: "Put a +1/+1 counter on target creature…. It gains
    # X" (Feat of Resistance at CAST resolution — the 14d headwall's dominant
    # face; Basri's two loyalty +2s). See _set_tapped's note.
    ctx.bindings["result"] = list(cards)


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
    cards = role_handles(ctx, atom, "target")
    for card in cards:
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
    # 16a (B-9 producer, FIGHT anaphora): "Target creature gets +X/+X. It
    # also fights another target creature" (Primal Might) — the fight
    # attacker is THIS atom's object, so the PT verbs write the register
    # the same way TAP/PUT_COUNTER do.
    ctx.bindings["result"] = list(cards)


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
        color = ctx.take_decision(_COLORS_VOCAB, f"mana:{ctx.source}")
    elif isinstance(color, str) and color in _COLORS_VOCAB:
        pass
    else:
        raise ValueError(f"executor: ADD_MANA colour {color!r} not in {_COLORS_VOCAB}")
    pool = ctx.world.players[player].mana_pool
    pool[color] = pool.get(color, 0) + n
    ctx.events.append((len(ctx.events), "ADD_MANA", str(player), color, n))
    if ctx.executor is not None:
        # 13b segment mirror (risk-2 design): the frozen totals write above
        # is UNTOUCHED — the segment rides alongside, tagged by the
        # source's live THIS_MANA policy (Vodalian Arcanist compiles its
        # "spend this mana only to cast instant or sorcery spells" as a
        # StaticAbility MANA_POLICY atom, so activating the SAME permanent
        # is what marks its own mana; mana from elsewhere stays clean).
        # Tags default EMPTY: every 12a/12b replay's plan arithmetic sees
        # exactly the pool totals, which is what keeps those pins
        # byte-identical.
        policy = ctx.executor.layers.this_mana_filter(ctx.source)
        ctx.executor.mana_ledger.add(
            player, color, n, (policy,) if policy is not None else ()
        )


def _v_scry(ctx: ExecCtx, atom: Atom) -> None:
    player = role_player(ctx, atom)
    n = amount(ctx, atom, "count")
    lib = ctx.world.players[player].zone(ZONE_LIBRARY)
    n = min(n, len(lib.entries))
    top_down = list(reversed(lib.entries[-n:])) if n else []
    bottoms: list[Handle] = []
    tops: list[Handle] = []
    # 14b site tag: owner + count (the /03 B-4 table). The per-card asks
    # share the key; the stream's FIFO serves them in ask order.
    what = f"scry:{player}:{n}"
    for card in top_down:  # decisions are consumed one per card, top first
        if ctx.take_decision(("top", "bottom"), what) == "top":
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
    stand-in, RANDOM = seeded ctx.rng draw, ONE_OF = the 14c channel ask
    (Handle-sorted candidate vocabulary; exhaustion stays loud); TARGET
    reads the spell's designation (B-15) or raises."""
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
    # 14c (B-16 lineage): the found cards land in the ability's ``result``
    # register — the same 13b read-back convention the CHOOSE atom pins
    # ("the follow-up atom's referent='result' Selector reads it"). The
    # compiler emits that referent after SEARCH (Necromentia's EXILE);
    # without this write the anaphora died B-9-style outside a firing.
    ctx.bindings["result"] = list(cards)


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
    """LOSE_GAME (13a; 13b audit-row fix): the frozen GameWorld carries no
    per-player lost flag (state.py is frozen) — so the loss lands on an
    EXECUTOR-side ledger, a documented divergence from a state-side flag;
    game-over evaluation (and the emptied library's CR 121.3 loss) is the
    later state-check phase. 13b quirk fix: the loss was ledger-only, a
    world-invisible mutation the STRUCTURED journal never saw (the
    fingerprint folded only the raw event-log row). It now also emits a
    GAME_LOST GameEvent row — subject the player — so every subscriber
    surface (dump, binder) sees the game end."""
    executor = _executor_or_raise(ctx, atom.verb.name)
    executor.lost_players.append(ctx.controller)
    executor.journal.emit(
        KIND_GAME_LOST, ctx.controller, None, "LOSE_GAME", ("LOSE_GAME",)
    )
    ctx.events.append((len(ctx.events), "LOSE_GAME", str(ctx.controller)))


# ------------------------------------------------- 13b: cast-side new verbs


def _v_pay(ctx: ExecCtx, atom: Atom) -> None:
    """PAY (13b; grammar round 7's "pay a cost as an effect" — "You may
    pay {2}", the Kraken/Devotee/Pilferer compile idiom). The
    OptionalEffect ancestor consumed the may-decision UPSTREAM
    (:meth:`Executor._run_effect`, C15 tree order), so reaching this
    handler IS the choice to pay; CR 117.3 then leaves no second choice —
    a cost that cannot be paid RAISES (the offer surface
    ``query.optional_offer`` narrows unactionable may-offers in advance).

    Payer coordinate: ``ctx.controller`` — the ability's "you". The role
    table gives PAY no payer role, and the corpus rows whose English
    names a different player ("that player may pay") ride the same atom;
    honouring the third-party payer is a documented coordinate gap for a
    later round (the engine cannot silently pick a DIFFERENT payer than
    the Slate planned around, so v1 pins the coordinate's own controller).

    Mana restrictions are honoured through the ordinary fold: this is
    :func:`legality.pay_costs` again, with no cast-use subject (effect
    mana purchases may not consume THIS_MANA — the conservative reading).
    Trigger settlement inside the nested payment consumes no decisions
    (``trigger_decisions=()`` — the decision channel is owned by the
    running effect, not its cost payment)."""
    from MTG_bot.core.executor.legality import (
        build_payment_plan,
        ctx_for,
        pay_costs,
    )

    executor = _executor_or_raise(ctx, atom.verb.name)
    cost = atom.args.get("cost")
    if not isinstance(cost, Cost):
        raise TypeError(f"executor: PAY needs a Cost role, got {cost!r}")
    plan, why = build_payment_plan(
        ctx.world, ctx_for(executor, source=ctx.source, controller=ctx.controller), cost
    )
    if plan is None:
        raise ValueError(f"executor: PAY cannot pay: {why}")
    pay_costs(
        executor,
        plan,
        source=ctx.source,
        controller=ctx.controller,
    )
    ctx.events.append((len(ctx.events), "PAY", str(ctx.controller), repr(cost)))


def _v_cast(ctx: ExecCtx, atom: Atom) -> None:
    """CAST (13b — THE finding this round chased): in this corpus the CAST
    atom is NOT a permission ledger entry. All ten compiled rows are the
    effect verb "cast the designated card" — OptionalEffect("you may
    cast") wrapped, ``source`` a Selector designating the card(s) (the
    'result' referent of a preceding exile/reveal, top-of-library, the
    IS_SOURCE self-cast), and the OPTIONAL ``cost`` role carrying either an
    EMPTY Cost (the corpus-wide cost-waiver idiom, "without paying its
    mana cost", CR 498.2) or a real Cost (additional cost). The frozen
    grammar comment says the same (ability_tree CAST role entry). So the
    handler delegates to :func:`stack.cast_card`: designate, park, pay
    (or not — empty Cost), push, resolve, put — and the CAST EVENT fires,
    so "whenever you cast" triggers see effect-casts too (CR 601.2m).

    Designation follows the 12a convention: bindings first (role
    ``source``), else the Selector (CHOOSE-mode deterministic first-n
    stand-in; the may-decision upstream already covered the whole atom).
    A designated card WITHOUT a SpellAbility (a land, an unregistered
    card) RAISES — the honest per-card flag, never a silent skip that
    would fake a cast."""
    from MTG_bot.core.executor.stack import cast_card

    executor = _executor_or_raise(ctx, atom.verb.name)
    cards = role_handles(ctx, atom, "source")
    cost = atom.args.get("cost")  # None = the spell's own printed cost
    if cost is not None and not isinstance(cost, Cost):
        raise ValueError(f"executor: CAST cost role must be a Cost, got {cost!r}")
    for card in cards:
        cast_card(
            executor,
            ctx.controller,
            card,
            cost_override=cost,
            x=ctx.x_value if ctx.x_value is not None else 0,
        )


def _v_choose(ctx: ExecCtx, atom: Atom) -> None:
    """CHOOSE (13b, grammar round 7's R7-1 — "You choose a noncreature,
    nonland card from it", Duress/Kitesail): the PLAYER decision this atom
    owns, consumed as an explicit index token into the Handle-sorted
    candidate pool — the same ORDER contract 12d pinned for Choose NODES
    (vocab ``str(i)`` over ``query.verb_choose_options`` order, §8.3
    query/runtime identity). The pick lands in the ability's ``result``
    register (the grammar's documented read-back: the follow-up atom's
    ``referent='result'`` Selector reads it), Handle-sorted like every
    designation (ruling 5).

    An empty pool chooses NOTHING without consuming a decision (there is
    no choice to make — the legal zero, and a caller-facing token would
    pretend otherwise). Multi-pick rows (count != 1) stay the loud flag:
    the corpus compiles count=1 only."""
    from MTG_bot.core.executor.query import verb_choose_options

    selector = atom.args.get("target")
    if not isinstance(selector, Selector):
        raise TypeError(f"executor: CHOOSE needs a target Selector, got {selector!r}")
    count_role = atom.args.get("count")
    if count_role is not None:
        assert isinstance(count_role, Quantity)  # role table: count is a Quantity
    want = 1 if count_role is None else resolve(count_role, ctx)
    if want != 1:
        raise NotImplementedError(
            "executor: Verb.CHOOSE multi-pick is a later round (corpus is count=1 only)"
        )
    executor = _executor_or_raise(ctx, "CHOOSE")
    rows = verb_choose_options(
        executor,
        atom,
        source=ctx.source,
        controller=ctx.controller,
        # B-8a: forward the live bindings — the pool this atom enumerates can
        # be scoped to them (Zone(HAND, TARGET_PLAYER) on Duress).
        bindings=ctx.bindings,
    )
    if rows == ((),):
        ctx.bindings["result"] = []
        ctx.events.append((len(ctx.events), "CHOOSE", str(ctx.source)))
        return
    vocab = tuple(str(i) for i in range(len(rows)))
    pick = ctx.take_decision(vocab, f"choose:{ctx.source}:{site_digest(tuple(rows))}")
    chosen = rows[int(pick)]
    if len(chosen) < want:
        # the under-filled zero row picked when candidates ran out
        ctx.bindings["result"] = list(chosen)
        ctx.events.append((len(ctx.events), "CHOOSE", str(ctx.source)))
        return
    ctx.bindings["result"] = list(chosen)
    ctx.events.append(
        (len(ctx.events), "CHOOSE", str(ctx.source), tuple(str(h) for h in chosen))
    )


def _v_choose_name(ctx: ExecCtx, atom: Atom) -> None:
    """CHOOSE_NAME (13b, grammar round 7's R7-4 — Runed Halo's ETB "choose
    a card name"): the chosen name is RECORDED (executor.name_choices,
    keyed by the source that wrote it) and read back by the NAME_CHOSEN
    filter predicate — the grammar's closed write/read pair, implemented
    in quantity._eval_atom. The corpus' full consumer is the PROTECTION
    keyword param the static grants (combat-side): combat has no executor
    yet, so per the 12d EXPOSED-ORACLE precedent (keyword_of for
    block/attack legality), this handler + predicate make the choice real
    and queryable NOW — the damage/block consumer joins combat, the flag
    never fakes it.

    C15 enumerability for a free-text name: the pick is a decision token
    out of the enumerable candidate NAMES — the card names present in the
    world (the engine's own knowledge boundary), narrowed by the optional
    ``name_filter`` (Necromentia's "a nonbasic card name" reading over
    those identities). Seeded-random fallback is NOT offered: the name is
    a player decision, so the decision channel owns it (the C15
    take_contract raises when a caller skips it — never hidden
    randomness for a choice a player makes)."""
    executor = _executor_or_raise(ctx, atom.verb.name)
    name_filter = atom.args.get("name_filter")
    if name_filter is not None:
        assert isinstance(name_filter, Filter)  # role table: name_filter is a Filter
    candidates: set[str] = set()
    for handle, card in ctx.world.cards.items():
        if card.identity.is_token:
            continue
        if name_filter is not None and not eval_filter(name_filter, handle, ctx):
            continue
        candidates.add(card.identity.name)
    if not candidates:
        raise ValueError(
            "executor: CHOOSE_NAME has no enumerable candidates (empty world "
            "or a name_filter nothing satisfies)"
        )
    ordered = sorted(candidates)
    pick = ctx.take_decision(tuple(ordered), f"name:{ctx.source}")
    executor.name_choices[ctx.source] = pick
    ctx.events.append((len(ctx.events), "CHOOSE_NAME", str(ctx.source), pick))


def _v_mana_policy(ctx: ExecCtx, atom: Atom) -> None:
    """MANA_POLICY (13b, grammar round 9 R9-3's C21 spend-restriction
    verbs — the LIVE CONSUMER this gate demanded): the CORPUS ships both
    policies as StaticAbility atoms (Vodalian Arcanist's THIS_MANA on its
    own {T}, Chromatic Orrery's ALL_YOURS), which attach-register through
    :meth:`layers.LayerRegistry._new_static`; this handler covers the
    RUNTIME-dispatch shape (an inline sequence or granted policy) by
    registering the SAME layer kind, so recompute/expiry/detach treat
    every policy identically.

    The two consumers, concretely:
      * THIS_MANA — ADD_MANA consults ``layers.this_mana_filter(source)``
        and SEGMENTS its mana; :func:`legality.build_payment_plan` then
        cannot even BUILD a plan that spends restricted segments on a use
        their filter rejects (the spell being cast is the filter's
        subject — Vodalian's compiled ``FOr(TYPE_EQ Instant, TYPE_EQ
        Sorcery)`` reads over the spell card exactly like the grammar's
        CastSpellEvent-shape note).
      * ALL_YOURS — ``executor.mana_permission`` makes a coloured demand
        drawable from any colour key (Orrery), plan-side only.
    The layer carries no duration role (role table: scope/filter), so a
    dispatched policy lives while its anchor does — permanent-static
    semantics for a permanent-anchored atom."""
    from MTG_bot.core.executor.layers import LayerRegistry  # cycle-free, cheap

    executor = _executor_or_raise(ctx, atom.verb.name)
    scope = atom.args.get("scope")
    if scope not in ("THIS_MANA", "ALL_YOURS"):
        raise ValueError(
            f"executor: MANA_POLICY scope {scope!r} not in the closed pair"
        )
    layers: LayerRegistry = executor.layers
    layers.register_mana_policy(ctx.source, ctx.controller, atom)
    layers.recompute()  # the permission must be LIVE before the next plan
    ctx.events.append((len(ctx.events), "MANA_POLICY", str(ctx.source), scope))


def _v_get_emblem(ctx: ExecCtx, atom: Atom) -> None:
    """GET_EMBLEM (13c, grammar round 8 R8-7): the emblem is a nested
    ``CardRecord`` on the SOURCE's compiled record (the compiler links
    owner -> emblem one-directionally), so the handler resolves the record
    through the binder bridge and hands the emblem record to the binder's
    emblem path (:meth:`binding.TriggerBinder.bind_emblem`) under a
    synthetic executor-owned handle. The emblem is NOT a world card — it
    never enters a zone; its triggers bind to the OWNER and its statics
    anchor to the OWNER (the emblem's "you"). CR 113.7: getting a second
    copy of the same emblem does nothing — the (owner, emblem oid) table is
    the idempotence gate, recorded as a duplicate event, never a rebind."""
    if atom.args.pairs:  # AtomArgs is never falsy — inspect the tuple
        raise ValueError(
            f"executor: GET_EMBLEM carries no roles (role table empty), got "
            f"{sorted(str(k) for k, _ in atom.args.pairs)}"
        )
    executor = _executor_or_raise(ctx, atom.verb.name)
    record = executor.binder.handle_record.get(ctx.source)
    if record is None:
        state = ctx.world.cards.get(ctx.source)
        if state is not None:
            record = executor.binder.records.get(state.identity.oracle_id)
    if record is None:
        raise ValueError(
            f"executor: GET_EMBLEM source {ctx.source} has no compiled record "
            "to carry an emblem (attach the permanent or register its oracle)"
        )
    if record.emblem is None:
        raise ValueError(
            f"executor: {record.name} carries no emblem record — the compiler "
            "found no paired emblem card (orphan flag, not a guess)"
        )
    granted = executor.get_emblem(ctx.controller, record.emblem)
    ctx.events.append(
        (
            len(ctx.events),
            "GET_EMBLEM",
            str(ctx.source),
            record.emblem.oracle_id,
            str(granted) if granted is not None else "duplicate",
        )
    )


def _v_grant_type(ctx: ExecCtx, atom: Atom) -> None:
    """GRANT_TYPE (13c, Riddleform's ETB — "is a Sphinx in addition to its
    other types" until end of turn): register a fixed-target type-grant
    layer over the designated set; :meth:`layers.LayerRegistry.type_overlay`
    is what the TYPE_EQ family reads. The printed-StaticAbility anthems
    (Dub, Demonic Embrace) take the generic static path in the registry;
    this handler is the trigger-dispatched sibling, same map, same expiry
    sweeps (duration_tag drives the EoT death)."""
    duration = atom.args.get("duration")
    assert duration is None or isinstance(duration, Duration)
    words = atom.args.get("types")
    if (
        not isinstance(words, tuple)
        or not words
        or not all(isinstance(w, str) and w for w in words)
    ):
        raise ValueError(
            f"executor: GRANT_TYPE types role must be a non-empty str tuple, "
            f"got {words!r}"
        )
    layers = _layers_or_raise(ctx, atom.verb.name)
    targets = tuple(role_handles(ctx, atom, "target"))
    layers.register_type_grant(ctx.source, ctx.controller, targets, atom, duration)
    ctx.events.append(
        (
            len(ctx.events),
            atom.verb.name,
            str(ctx.source),
            words,
            tuple(str(t) for t in targets),
            duration_tag(duration),
        )
    )


def _v_add_land_play(ctx: ExecCtx, atom: Atom) -> None:
    """ADD_LAND_PLAY (13c, grammar round 8 R8-8, Azusa): register a
    selector-less land-play PERMISSION layer; the land gate
    (:func:`stack.land_playable`) folds the seat's live layer sum into the
    CR 305.1 allowance. ``count`` is optional in the role table — omitted
    reads as ONE additional land ("You may play an additional land").
    Azusa compiles inside an OptionalEffect, so the "you may" is decided
    BEFORE this atom runs (skip = no layer); repeat activations stack
    cumulatively, which is the honest CR reading of a repeatable
    free-cost ability (each activation grants +2 more)."""
    duration = atom.args.get("duration")
    assert duration is None or isinstance(duration, Duration)
    layers = _layers_or_raise(ctx, atom.verb.name)
    count_q = atom.args.get("count")
    if count_q is None:
        count_q = QConst(1)
    assert isinstance(count_q, Quantity)
    count = resolve(count_q, ctx)
    layers.register_land_play(ctx.source, ctx.controller, count, duration)
    ctx.events.append(
        (
            len(ctx.events),
            atom.verb.name,
            str(ctx.source),
            count,
            duration_tag(duration),
        )
    )


def _v_grant_activation(ctx: ExecCtx, atom: Atom) -> None:
    """GRANT_ACTIVATION (13c, grammar round 9 R9-7): the timing-permission
    layer ("activate … any time you could cast an instant"). Teferi's
    static registers the same kind through ``_new_static``; this handler is
    the RUNTIME-dispatch sibling (granted/inline shape) — registered like
    mana_policy (selector-less permission, recompute immediately so the
    relaxation is live before the next legality query). The consumer is
    :func:`legality.ability_playable`: a live grant whose filter matches the
    permanent skips the SORCERY-timing block; every OTHER activation gate
    (controller, loyalty once-per-turn, costs, conditions) is untouched —
    the permission relaxes timing, never legitimacy."""
    executor = _executor_or_raise(ctx, atom.verb.name)
    filter_ = atom.args.get("filter")
    if filter_ is None or not isinstance(filter_, (FAnd, FOr, FNot, FAtom)):
        raise ValueError(f"executor: GRANT_ACTIVATION needs a Filter, got {filter_!r}")
    window = atom.args.get("window")
    if window is not None and window is not ActivationWindow.INSTANT:
        raise NotImplementedError(
            f"executor: GRANT_ACTIVATION window {window!r} has no consumer "
            "(13c implements the INSTANT relaxation only)"
        )
    layers = executor.layers
    layers.register_activation_grant(ctx.source, ctx.controller, atom)
    layers.recompute()  # the permission must be LIVE before the next query
    ctx.events.append(
        (
            len(ctx.events),
            atom.verb.name,
            str(ctx.source),
            window.name if window is not None else "INSTANT",
        )
    )


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
    # 13b: the cast-side verbs — the gate-flip five (PAY, CAST, CHOOSE,
    # CHOOSE_NAME, MANA_POLICY). SUPPORTED_VERBS_V2 derives from THIS
    # table, so these entries are exactly what moves measure_grammar's
    # engine-supported count; COUNTER_SPELL deliberately stays out (no
    # interaction window in v1 — the four COUNTER_SPELL cards keep their
    # loud dispatch raise, pinned by test_counter_spell_still_raises).
    Verb.PAY: _v_pay,
    Verb.CAST: _v_cast,
    Verb.CHOOSE: _v_choose,
    Verb.CHOOSE_NAME: _v_choose_name,
    Verb.MANA_POLICY: _v_mana_policy,
    # 13c: the permission/effect verbs — emblem acquisition, static type
    # grants, the additional-land allowance and the activation-window
    # relaxation. SUPPORTED_VERBS_V2 derives from THIS table.
    Verb.GET_EMBLEM: _v_get_emblem,
    Verb.GRANT_TYPE: _v_grant_type,
    Verb.ADD_LAND_PLAY: _v_add_land_play,
    Verb.GRANT_ACTIVATION: _v_grant_activation,
    # 16a: the damage-exchange orphan verb (CR 701.12). SUPPORTED_VERBS_V2
    # derives from THIS table — 39 -> 40, the library pin is amended dated.
    Verb.FIGHT: _v_fight,
}


def run_atom(atom: Atom, ctx: ExecCtx) -> None:
    """Dispatch one Atom to its handler; unsupported verbs RAISE."""
    handler = HANDLERS.get(atom.verb)
    if handler is None:
        raise NotImplementedError(f"executor: verb {atom.verb.name} not implemented")
    handler(ctx, atom)
