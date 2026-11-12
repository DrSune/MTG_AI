"""Atom handlers: one function per verb, dispatched through :data:`HANDLERS`.

Dispatch is a flat verb -> handler table: anything the executor cannot
honestly run raises ``NotImplementedError`` *at dispatch time* — never a
silent no-op (LOOK_AT/REVEAL move nothing, but they are recorded as events).

Determinism contract:
  * multi-object effects iterate their targets **Handle-sorted**
    — pinned by ``test_handle_sorting_is_canonical``;
  * library operations (draw, mill, scry) iterate **zone order** — the
    designated order-preserving slot (top of library = last entry);
  * randomness (SHUFFLE, RANDOM selectors, FLIP_COIN) flows only through the
    executor-owned :class:`random.Random` streams seeded from ``master_seed``;
  * decisions (scry top/bottom, any-color mana, choices) are asked through
    the decision channel (``ExecCtx.take_decision``) — zero hidden randomness.

Role names are the ``ability_tree._VERB_ROLES`` table; designation machinery
lives in :mod:`.selectors`.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import replace

from MTG_bot.core.executor.events import KIND_ABILITY_TRIGGERED
from MTG_bot.core.ability_tree import (
    Atom,
    AtomArgs,
    CardRecord,
    ControllerRef,
    Cost,
    CounterKind,
    Duration,
    DurationEot,
    DurationPermanent,
    DurationUntilLeaves,
    EventSpec,
    FAnd,
    FAtom,
    FAtomPred,
    Filter,
    FNot,
    FOr,
    Keyword,
    KeywordAbility,
    PtDelta,
    PtDirection,
    QAtMost,
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
    ZonePosition,
)
from MTG_bot.core.executor.decisions import site_digest
from MTG_bot.core.executor.offers import offer_or_autopick
from MTG_bot.core.executor.durations import duration_tag
from MTG_bot.core.executor.events import (
    KIND_COUNTER,
    KIND_GAME_LOST,
    KIND_KICKBACK,
)
from MTG_bot.core.executor.quantity import (
    ExecCtx,
    _type_line_tokens,
    eval_filter,
    last_known,
    referent_handle,
    resolve,
)
from MTG_bot.core.executor.returns import anchor_unmoved, battlefield_entry_clock
from MTG_bot.core.executor.selectors import (
    ZONE_KIND_TO_STATE,
    amount,
    apnap_order,
    existing,
    last_known_controller,
    move_destination,
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

# "One mana of any color" is one of the five colors (CR 105.1, 106.1a); colorless is
# a type of mana, not a color (CR 106.1b), so {C} is not an answer to an any-color
# choice. A fixed "Add {C}" stays valid.
_ANY_COLOR_VOCAB = ("W", "U", "B", "R", "G")


# ------------------------------------------------------------------- handlers


def _move_to(
    ctx: ExecCtx,
    card: Handle,
    player: Handle,
    kind: str,
    journal_kind: str = "MOVE",
) -> None:
    # journal_kind is the event-kind column of the raw journalled row: a SLOT
    # of the MOVE_ZONE atom, never derived from the verb, so a mill writes "MILL".
    src = ctx.world.zone_of(card)
    ctx.world.move_to_zone(card, player, kind)
    ctx.events.append((len(ctx.events), journal_kind, str(card), f"{src.kind}->{kind}"))


def _discard_picks(ctx: ExecCtx, sel: Selector, player: Handle) -> list[Handle]:
    """The cards ``player`` discards for one discard instruction.

    A discard moves cards from the discarding player's OWN hand (CR 701.9a), so the pool is that
    hand re-read at take time and filtered through the Selector (the raw Selector population of
    Bad Deal spans both hands). Fewer cards than the count simply discards fewer. CR 701.9b: by
    default the discarding player chooses which cards; a CHOOSE discard asks THAT player, one
    card per ask over the shrinking hand, in the cost lane's ``discard:<seat>:<source>:<digest>``
    shape (legality.pay_costs). A fixed count no smaller than the pool leaves no choice and asks
    nothing. "Up to N" (QAtMost) lets the player stop at any pick, the first included: "up to N"
    names every number from zero to N. RANDOM keeps the executor-seeded draw; QUnbounded takes
    the whole pool.
    """
    live = list(ctx.world.players[player].zone(ZONE_HAND).entries)
    pool = sorted(h for h in live if eval_filter(sel.filter, h, ctx))
    if sel.mode is SelectorMode.RANDOM:
        rng = ctx.rng("RANDOM")
        rng.shuffle(pool)  # seeded: replay-identical
    if isinstance(sel.count, QUnbounded):
        return pool
    want = resolve(sel.count, ctx)
    optional = isinstance(sel.count, QAtMost)
    if sel.mode is not SelectorMode.CHOOSE or want <= 0 or (want >= len(pool) and not optional):
        return pool[:want]
    picks: list[Handle] = []
    remaining = list(pool)
    for _pick in range(min(want, len(pool))):
        vocab = tuple(str(h) for h in remaining) + (("NONE",) if optional else ())
        answer = ctx.take_decision_of(
            player, vocab, f"discard:{player}:{ctx.source}:{site_digest(vocab)}"
        )
        if answer == "NONE":
            break
        pick = next(h for h in remaining if str(h) == answer)
        picks.append(pick)
        remaining.remove(pick)
    return picks


def _enter_under_control(ctx: ExecCtx, card: Handle, controller: Handle) -> None:
    """CR 110.2, 110.2a: a card put onto the battlefield under the control of a
    player other than its owner sits in its owner's zone (the frozen world reads the
    owner off the zone) and gets a control entry for that player, which ends when it
    leaves the battlefield (Executor._on_zone_changes)."""
    if ctx.executor is None:
        raise ValueError(
            "executor: a permanent entering under a non-owner's control needs an "
            "executor-backed ExecCtx (the control overlay)"
        )
    ctx.executor.gain_control(card, controller, "Permanent", None)


def _v_move_zone(ctx: ExecCtx, atom: Atom) -> None:
    dest_ir = atom.args.get("destination")
    assert isinstance(dest_ir, Zone)  # Atom validation guarantees it
    dest_kind = ZONE_KIND_TO_STATE.get(dest_ir.kind)
    if dest_kind is None:
        raise NotImplementedError(
            f"executor: MOVE_ZONE to {dest_ir.kind.name} is not a card zone (12b/12c)"
        )
    # The ONE move atom: mill, discard and exile compile onto MOVE_ZONE with
    # orthogonal slots — {from} states the departure zone, {journal_kind} the
    # raw-row kind, {pop_order} the library pop, {target} the designation lane.
    # The shape branches below journal and write the result register exactly
    # as the separate verbs did (test_executor_p1a_move locks it).
    journal_kind = str(atom.args.get("journal_kind") or "MOVE")
    frm = atom.args.get("from")
    if atom.args.get("pop_order") == "TOP":
        # The mill shape: pop TOP of the named library — an EXPLICIT order,
        # never a selector resolution — into the destination. The raw row's
        # kind ("MILL") comes from the journal_kind slot.
        if not isinstance(frm, Zone) or frm.kind is not ZoneKind.LIBRARY:
            raise ValueError("executor: MOVE pop_order=TOP needs from=LIBRARY")
        player = role_player(ctx, atom)
        n = amount(ctx, atom, "amount")
        lib = ctx.world.players[player].zone(ZONE_LIBRARY)
        dest_zone = ctx.world.players[player].zone(dest_kind)
        for _ in range(min(n, len(lib.entries))):
            card = lib.entries.pop()  # top of library, zone order
            dest_zone.entries.append(card)
            ctx.events.append(
                (
                    len(ctx.events),
                    journal_kind,
                    str(card),
                    f"{ZONE_LIBRARY}->{dest_kind}",
                )
            )
        return
    if isinstance(frm, Zone) and frm.kind is ZoneKind.HAND:
        # The discard shape: EVERY player the controller role denotes discards
        # ("each player discards a card"), and each discarding player chooses
        # their own cards (CR 701.9b) from their live hand.
        players = role_players(ctx, atom)
        cards = ctx.binding_handles("cards")
        if cards is None:
            sel = atom.args.get("cards")
            if not isinstance(sel, Selector):
                raise ValueError("executor: MOVE_ZONE cards role has no binding")
            if (
                sel.referent is not None
                or sel.mode is SelectorMode.TARGET
                or sel.mode in (SelectorMode.ONE_OF, SelectorMode.REST)
            ):
                # designation / anaphora / partition paths all self-resolve
                # (the spell's designation, the 'result' register, the
                # partition ask) — the hand scoping below is only for the
                # CHOOSE/RANDOM/ALL discards.
                cards = resolve_selector(
                    sel,
                    ctx,
                    journal_partition=sel.mode
                    in (SelectorMode.ONE_OF, SelectorMode.REST),
                )
            else:
                # CR 608.2e / 101.4: the discarding players choose in APNAP
                # order, then the cards are discarded simultaneously (below).
                cards = []
                for player in apnap_order(ctx.world, players):
                    cards.extend(_discard_picks(ctx, sel, player))
        hands = {p: ctx.world.players[p].zone(ZONE_HAND).entries for p in players}
        moved: list = []
        for card in sorted(cards):
            owner = next((p for p, hand in hands.items() if card in hand), None)
            if owner is None:
                raise ValueError(
                    f"executor: MOVE_ZONE discard card {card} is not in the hand of "
                    f"{', '.join(str(p) for p in players) or 'any discarding player'}"
                )
            # CR 701.9a: from its owner's hand to that player's graveyard.
            _move_to(ctx, card, owner, dest_kind, journal_kind)
            moved.append(card)
        # The DISCARDED SET is the result register, written even when empty:
        # "discard ..., then draw that many" (THAT_MANY_COUNT, Kinetic Augur)
        # reads 0, not a missing antecedent.
        ctx.bindings["result"] = moved
        return
    tapped_on_enter = bool(atom.args.get("tapped_on_enter"))
    cards = ctx.binding_handles("cards")
    if cards is not None:
        cards = existing(ctx, cards)  # CR 702.26b: a phased-out designation is skipped
    if cards is None:
        sel = atom.args.get("cards")
        if sel is None:
            # The designation lane: the objects ride `target`, NOT cards, so
            # the spell's designation (bound under "target") still finds the
            # key. The moved set is the result register, as in every other
            # lane, so "Exile target card from a graveyard. If it was a
            # creature card, ..." (Scavenging Ooze) judges the exiled card.
            moved_targets: list = []
            for card in role_handles(ctx, atom, "target"):
                _move_to(
                    ctx,
                    card,
                    ctx.world.controller_of(card),
                    dest_kind,
                    journal_kind,
                )
                moved_targets.append(card)
            ctx.bindings["result"] = moved_targets
            return
        if not isinstance(sel, Selector):
            raise ValueError("executor: MOVE_ZONE cards role has no binding")
        n = 0 if isinstance(sel.count, QUnbounded) else resolve(sel.count, ctx)
        # The ONE_OF/REST partition modes SELECT specific cards (the pick /
        # its complement) — the top-n draw idiom and the count clamp apply
        # to the CHOOSE/draw idioms only; a partition atom moves exactly what
        # its Selector resolves.
        partition = sel.mode in (SelectorMode.ONE_OF, SelectorMode.REST)
        # The draw idiom is "move THE top n of your library to hand" — an
        # UNFILTERED, referent-less selector. A filtered CHOOSE on a library
        # zone is a SEARCH tail ("put IT into your hand", Chandra's Firemaw):
        # its population is the filter's answer, resolved below, never a
        # blind top-n draw that would put an unrelated library card in hand.
        universal = isinstance(sel.filter, FAnd) and not sel.filter.children
        if (
            not partition
            and dest_kind == ZONE_HAND
            # Only a selector over the library ALONE: a LIBRARY∪GRAVEYARD (or
            # HAND∪LIBRARY) selector is a SEARCH answer and must not take the
            # blind top-n draw lane.
            and len(sel.zones) == 1
            and sel.zones[0].kind is ZoneKind.LIBRARY
            and sel.referent is None
            and universal
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
        pool = [
            h
            for h in resolve_selector(
                sel, ctx, journal_partition=partition, ask_choose=True
            )
            if h.namespace == "card"
        ]
        cards = pool if partition else (pool[:n] if n else pool)
    # A destination Zone.position == BOTTOM (See the Truth) means the cards
    # land at the BOTTOM of the pile — move_card appends (top for a library /
    # end of order) and no-ops on a same-zone move, so the bottom-put is
    # completed here: each card is re-inserted at index 0, iterating
    # Handle-DESCENDING so the final bottom run reads ascending (the scry
    # rule's sorted(bottoms)). The compiler emits NO position for "put it on
    # the bottom of your library" (Epitaph Golem), while every other
    # MOVE_ZONE→LIBRARY carries an explicit TOP or BOTTOM, so a position-less
    # LIBRARY destination IS the bottom-put.
    bottom_dest = dest_ir.position is ZonePosition.BOTTOM or (
        dest_ir.position is None and dest_kind == ZONE_LIBRARY
    )
    stayed: set[Handle] = set()
    for card in sorted(cards, reverse=True) if bottom_dest else cards:
        # The owner's zone always (CR 400.3); a battlefield controller other than
        # the owner becomes a control entry below, never a zone (CR 108.3).
        target_player, new_controller = move_destination(ctx, dest_ir, dest_kind, card)
        src = ctx.world.zone_of(card)
        host: Handle | None = None
        if dest_kind == ZONE_BATTLEFIELD:
            # Replacement before apply for the ENTER move itself (Containment
            # Priest): a live ZoneChangeEvent replacement consumes the ETB (the
            # permanent never becomes a permanent, no battlefield placement, no
            # tapped_on_enter stamp), and the action (EXILE referent=event) runs
            # as a journalled nested effect with the moving card bound, as in
            # the life lane.
            repl = (
                ctx.replacements.replacement_for_zone_change(
                    card, src.kind, dest_kind, ctx.replaced_seq
                )
                if ctx.replacements is not None
                else None
            )
            if repl is not None:
                ctx.pending_replacements.append((repl, card))
                ctx.events.append(
                    (len(ctx.events), "ZONE_REPLACED", str(card), str(repl.source))
                )
                continue
            # CR 303.4f: the player the Aura enters under chooses its host, which
            # is the controller when that is not the owner (whose zone it joins).
            enters, host = _aura_entry_host(ctx, card, new_controller or target_player)
            if not enters:
                stayed.add(card)  # CR 303.4g: nothing to enchant, it stays
                continue
        zone = ctx.world.players[target_player].zone(dest_kind)
        ctx.world.move_card(card, zone)
        if new_controller is not None:
            _enter_under_control(ctx, card, new_controller)
        if bottom_dest:
            zone.entries.remove(card)
            zone.entries.insert(0, card)
        if tapped_on_enter and dest_kind == ZONE_BATTLEFIELD:
            ctx.world.cards[card].tapped = True
        ctx.events.append(
            (len(ctx.events), "MOVE", str(card), f"{src.kind}->{dest_kind}")
        )
        if host is not None:
            _attach_entering_aura(ctx, card, host)
    # The MOVED cards are the result register ("…put it onto the
    # battlefield…. It gains haste", the Liliana, Waker of the Dead emblem:
    # inside a firing the ACTION's object, not the event subject, is the
    # antecedent). The top-n draw idiom above writes nothing: no object was
    # chosen, and reading an unset register raises.
    ctx.bindings["result"] = [c for c in cards if c not in stayed]


def _aura_entry_host(ctx: ExecCtx, card: Handle, player: Handle) -> tuple[bool, Handle | None]:
    """CR 303.4f-g: an Aura an effect puts onto the battlefield (not
    resolving as an Aura spell) enters attached to what ``player``, the
    player it enters under, chooses; with nothing legal it does not enter.
    Returns (enters, host); host is None for a card that is not an Aura (the
    ENCHANT keyword marker, query.is_aura_spell's test)."""
    ex = ctx.executor
    if ex is None or "ENCHANT" not in ctx.world.cards[card].identity.keywords:
        return True, None
    from MTG_bot.core.executor.aura_entry import choose_aura_host

    host = choose_aura_host(ex, card, player)
    return host is not None, host


def _attach_entering_aura(ctx: ExecCtx, card: Handle, host: Handle) -> None:
    """The attachment edge of an Aura that just entered (the cast lane's
    ATTACH row, stack.py), so the 704.5q sweep sees it attached."""
    assert ctx.executor is not None  # _aura_entry_host chose a host only with one
    ctx.executor.attach_aura(card, host)
    ctx.events.append((len(ctx.events), "ATTACH", str(card), str(host)))


#: The zones a move "until" may take an object from. The return puts it back there (CR 610.3);
#: a library or the stack has no position rule for that here, so such a move raises.
_RETURNABLE_ZONES = (ZONE_BATTLEFIELD, ZONE_HAND, ZONE_GRAVEYARD, ZONE_EXILE)


def _zone_map(world) -> dict[Handle, tuple[Handle, str]]:
    """card -> (zone owner, zone kind) over every zone, without opening a journal boundary."""
    out: dict[Handle, tuple[Handle, str]] = {}
    for player in world.player_order:
        for kind, zone in world.players[player].zones.items():
            for card in zone.entries:
                out[card] = (player, kind)
    return out


def _v_move_zone_until(ctx: ExecCtx, atom: Atom) -> None:
    """MOVE_ZONE's handler. Without a ``duration`` role it is :func:`_v_move_zone`, unchanged.

    CR 610.3: with one, the move is the first of two one-shot effects ("exile that
    card until this creature leaves the battlefield"). The objects move exactly as without it, and
    each one that arrives gets a row in the executor's return registry (``returns.py``). When the
    duration ends, the executor returns it to its previous zone (``Executor._run_returns``).
    CR 610.3a/b: if the anchor already left the battlefield after the ability triggered or the
    spell was cast, the event has happened and nothing moves."""
    duration = atom.args.get("duration")
    if duration is None:
        _v_move_zone(ctx, atom)
        return
    executor = ctx.executor
    if executor is None:
        raise ValueError(
            "executor: MOVE_ZONE with a duration needs an executor-backed ExecCtx "
            "(the return registry)"
        )
    assert isinstance(duration, Duration)  # the role table types it
    tag = duration_tag(duration)
    anchor: Handle | None = None
    anchor_clock = 0
    if isinstance(duration, DurationUntilLeaves):
        anchor = referent_handle(duration.source, ctx)
        if not anchor_unmoved(ctx, anchor):
            # CR 610.3a/b: "the specified event has already occurred": the object doesn't move.
            if atom.args.get("cards") is not None:
                ctx.bindings["result"] = []
            ctx.events.append((len(ctx.events), "MOVE_UNTIL_ENDED", str(anchor), tag))
            return
        if ctx.journal is not None:
            anchor_clock = battlefield_entry_clock(ctx.journal, anchor)
    before = _zone_map(ctx.world)
    _v_move_zone(ctx, atom)
    after = _zone_map(ctx.world)
    for card in sorted(after):
        was = before.get(card)
        now = after[card]
        if was is None or was == now:
            continue
        if was[1] not in _RETURNABLE_ZONES:
            raise NotImplementedError(
                f"executor: MOVE_ZONE until … from the {was[1]}: returning an object to a "
                "library or the stack has no position rule here (flag, don't degrade)"
            )
        executor.returns.stage(
            card,
            zone=now[1],
            previous_zone=was[1],
            owner=now[0],
            tag=tag,
            anchor=anchor,
            anchor_clock=anchor_clock,
            source=ctx.source,
            controller=ctx.controller,
        )


def _to_graveyard(ctx: ExecCtx, atom: Atom) -> None:
    for card in role_handles(ctx, atom, "target"):
        _move_to(ctx, card, ctx.world.controller_of(card), ZONE_GRAVEYARD)


def _v_gain_life(ctx: ExecCtx, atom: Atom) -> None:
    n = amount(ctx, atom, "amount")
    for player in sorted(role_players(ctx, atom)):
        # Replacement before apply, as in _v_deal_damage. A live
        # LifeGainedEvent replacement (Life Goes On) consumes the event — no
        # life mutation happens (the journal sees no gain at all), the
        # replacement's ACTION runs as a nested journalled effect once this
        # atom's boundary closes, and the CR 614.4a chain guard (the
        # executor's drain) keeps the same record from re-replacing its own
        # 8-life action.
        repl = (
            ctx.replacements.replacement_for_life_gained(ctx, player)
            if ctx.replacements is not None
            else None
        )
        if repl is not None:
            ctx.pending_replacements.append(repl)
            ctx.events.append(
                (
                    len(ctx.events),
                    "LIFE_REPLACED",
                    str(player),
                    str(repl.source),
                    n,
                )
            )
            continue
        ctx.world.players[player].life += n
        ctx.events.append((len(ctx.events), "GAIN_LIFE", str(player), n))


def _lifelink_gain(ctx: ExecCtx, n: int) -> None:
    """LIFELINK (CR 702.15b): damage dealt by a source with lifelink makes its
    controller gain that much life. The keyword is read as the source has it
    (:func:`_source_has`, as for deathtouch), so a granted lifelink counts and
    a lost one stops counting. The gain is routed through the GAIN_LIFE VERB
    lane rather than a direct life bump: life-gain replacements then apply,
    and the KIND_LIFE_GAINED rows that Light of Promise's granted trigger and
    Indulging Patrician's LIFE_GAINED_THIS_TURN_GE threshold read are real
    life-gain events, not invisible arithmetic. The gain belongs to the
    SOURCE's (last known) controller."""
    if n <= 0:
        return
    if ctx.executor is None or ctx.layers is None:
        return
    if ctx.source.namespace != "card":
        return
    if not _source_has(ctx, Keyword.LIFELINK):
        return
    atom = Atom(
        verb=Verb.GAIN_LIFE,
        args=AtomArgs(pairs=(("controller", ControllerRef.YOU), ("amount", QConst(n)))),
    )
    _v_gain_life(replace(ctx, controller=last_known_controller(ctx, ctx.source)), atom)


def _source_has(ctx: ExecCtx, keyword: Keyword) -> bool:
    """Does the damage's source have ``keyword``? CR 113.7a, 608.2h: a source that has left the
    battlefield (Heartfire Immolator sacrificed for its ability, Pitchburn Devils dead) deals
    the damage with the keywords it last had there, granted ones included."""
    lki = last_known(ctx.source, ctx)
    if lki is not None:
        return keyword.name in lki.keywords
    return ctx.layers.keyword_of(ctx.source, keyword)


def _v_trigger_additional(ctx: ExecCtx, atom: Atom) -> None:
    """TRIGGER_ADDITIONAL (Sanctum of All): re-queue the ability THIS firing matched
    `count` extra times. The AbilityTriggerEvent fan-out stored the matched
    firing payload in the synthetic event's data; the re-queued firings are
    marked additional=True — CR 603.2d: an extra trigger is created without
    a triggering event, so it never re-arms an AbilityTriggerEvent (this is
    what keeps two extra-trigger carriers, or a self-counting carrier,
    from chasing each other forever). Each re-queued firing is a FULL
    resolution: its own targets, its own may-asks."""
    event = ctx.event
    if (
        event is None
        or getattr(event, "kind", None) != KIND_ABILITY_TRIGGERED
        or not event.data
    ):  # pragma: no cover - only a mis-compiled card can dispatch here
        raise ValueError(
            "executor: TRIGGER_ADDITIONAL outside an ability-triggered firing"
        )
    original = event.data[0]
    if ctx.executor is None:  # pragma: no cover - bare-ctx guard
        raise ValueError("executor: TRIGGER_ADDITIONAL needs the executor binder")
    extra = amount(ctx, atom, "count")
    for _ in range(extra):
        ctx.executor.binder._queue(
            original.source,
            original.controller,
            original.node,
            original.event,
            additional=True,
        )


def _v_lose_life(ctx: ExecCtx, atom: Atom) -> None:
    n = amount(ctx, atom, "amount")
    for player in sorted(role_players(ctx, atom)):
        p = ctx.world.players[player]
        # CR 119.3/119.6: the life total is adjusted, and may go below 0; a player at
        # 0 or less loses as a state-based action (Executor._player_losses).
        p.life = p.life - n
        ctx.events.append((len(ctx.events), "LOSE_LIFE", str(player), p.life))


def damage_source(ctx: ExecCtx, atom: Atom) -> Handle | None:
    """The object that deals a DEAL_DAMAGE atom's damage. CR 120.1/120.2b:
    "the spell or ability will specify which object deals that damage". A
    ``dealer`` Selector names it ("Then that creature deals damage equal to
    its power", Hunter's Edge; Garruk, Savage Herald's -2); without one it is
    the ability's own source. None: the named dealer is gone (an illegal
    target, CR 608.2b), so no damage is dealt. A non-Selector dealer (Fiery
    Emancipation's Filter, a replacement action's) is consumed by the
    replacement lane, never here."""
    dealer = atom.args.get("dealer")
    if dealer is None:
        return ctx.source
    if not isinstance(dealer, Selector):
        raise NotImplementedError(
            f"executor: DEAL_DAMAGE dealer {type(dealer).__name__} has no "
            "consumer outside the replacement lane"
        )
    found = sorted(resolve_selector(dealer, ctx))
    return found[0] if found else None


def _v_deal_damage(ctx: ExecCtx, atom: Atom) -> None:
    if atom.args.get("recipient") is not None:
        raise NotImplementedError(
            "executor: DEAL_DAMAGE recipient (C-4 damage surface) is 12b/12d"
        )
    source = damage_source(ctx, atom)
    if source is None:
        ctx.events.append((len(ctx.events), "DAMAGE_NO_DEALER", str(ctx.source)))
        ctx.bindings["result"] = []  # no object was dealt damage this way
        return
    # CR 107.1b: a negative result (a negative power) means 0; CR 120.8: a
    # source that would deal 0 damage deals no damage at all.
    n = max(0, amount(ctx, atom, "amount"))
    if n == 0:
        ctx.bindings["result"] = []
        return
    targets = role_handles(ctx, atom, "target")
    # The result register names the objects this sentence dealt damage to, so
    # "If a Dinosaur is dealt damage this way" (Marauding Raptor) judges them, not the source.
    dealt: list[Handle] = []
    if source != ctx.source:
        # The dealer is the damage source for everything below (deathtouch,
        # lifelink, source-keyed replacement and prevention); targets and
        # amount were read in the ability's own coordinates above.
        ctx = replace(ctx, source=source)
    combat = bool(getattr(ctx.executor, "_combat_wave_open", False))
    for target in targets:
        n_i = n
        if target.namespace == "player" and _protection_prevents(ctx, target, n_i):
            continue  # CR 702.16e: a player with protection from the source
        if target.namespace == "player":
            # Replacement before apply. The damage consult serves both kinds:
            # a live replacement that CONSUMES the event (Nine Lives) leaves
            # no life mutation (the journal sees no damage at all) and queues
            # its action for the drain; one that MODIFIES the event's quantity
            # (Fiery Emancipation's DEAL_DAMAGE action rewriting QProp(event,
            # AMOUNT)) rewrites the amount IN PLACE, so exactly one journalled
            # DAMAGE row lands on the tripled number and dealer attribution /
            # lifelink stay on the dealt amount. CR 616.1: several may apply in
            # turn, in the order the damaged player chose; a consume is the last.
            steps = (
                ctx.replacements.replacements_for_damage(
                    ctx, target, ctx.source, n_i, combat
                )
                if ctx.replacements is not None
                else []
            )
            consumed = False
            for repl, new_n in steps:
                if new_n is None:
                    ctx.pending_replacements.append(repl)
                    ctx.events.append(
                        (
                            len(ctx.events),
                            "DAMAGE_REPLACED",
                            str(target),
                            str(repl.source),
                            n_i,
                        )
                    )
                    consumed = True
                    break
                ctx.events.append(
                    (
                        len(ctx.events),
                        "DAMAGE_MODIFIED",
                        str(target),
                        str(repl.source),
                        n_i,
                        new_n,
                    )
                )
                n_i = new_n
            if consumed:
                continue
            p = ctx.world.players[target]
            # CR 120.3a, 119.3: damage to a player is that much life lost, below 0 too.
            # No clamp at 0: the journal's DAMAGE row is the life difference, and
            # "that much damage" readers count it.
            p.life = p.life - n_i
            ctx.events.append((len(ctx.events), "DAMAGE", str(target), p.life))
            _lifelink_gain(ctx, n_i)  # lifelink reads ANY damage dealt
            continue
        # CR 120.4/120.6: damage is MARKED, never instant-lethal. The mark
        # rides the executor's damage ledger and the settle tail's
        # state-based check (CR 704.5a) does the destroying — so two
        # creatures trading non-lethal blows both survive, and a lethal
        # exchange is a simultaneous double kill. The DAMAGE tuple feeds the
        # journal's KIND_DAMAGE row (events.py), which "is dealt damage"
        # triggers (Brash Taunter) read.
        if _deal_damage_to_card(ctx, target, n_i):
            dealt.append(target)
    ctx.bindings["result"] = dealt


#: CR 120.1a: the only objects damage can be dealt to.
_DAMAGEABLE = FOr(
    children=tuple(
        FAtom(pred=FAtomPred.TYPE_EQ, string_value=kind)
        for kind in ("Battle", "Creature", "Planeswalker")
    )
)


def _protection_prevents(ctx: ExecCtx, recipient: Handle, n: int) -> bool:
    """CR 702.16e: "Any damage that would be dealt by sources that have the
    stated quality to a permanent or player with protection is prevented." The
    source is the damage's dealer (``ctx.source``: the spell, the ability's source,
    the fighting or combat creature). Prevented damage is never dealt: no mark, no
    life loss, no lifelink, no "is dealt damage" trigger; a DAMAGE_PREVENTED audit
    row records it, the shape the PREVENT_EFFECT lane writes."""
    from MTG_bot.core.executor.legality import protected_from

    if n <= 0 or not protected_from(ctx.executor, recipient, ctx.source):
        return False
    ctx.events.append(
        (len(ctx.events), "DAMAGE_PREVENTED", str(recipient), "PROTECTION", n)
    )
    return True


def _deal_damage_to_card(ctx: ExecCtx, target: Handle, n: int) -> bool:
    """One card-side damage application: mark it, journal it, decide nothing.
    CR 702.2b: when the SOURCE carries DEATHTOUCH the mark is flagged
    lethal-in-itself, so the state check buries a 3/3 under one point of
    Fetid Imp venom (the keyword is read by :func:`_source_has`, so a
    granted deathtouch counts and a lost one stops counting). Returns whether
    damage was dealt (False: not damageable, protected, or prevented)."""
    if ctx.executor is None:
        raise ValueError(
            "executor: card damage needs an executor-backed ExecCtx "
            "(bare ExecCtx has no damage ledger)"
        )
    if not eval_filter(_DAMAGEABLE, target, ctx):
        # CR 120.1a: damage can't be dealt to an object that's not a battle,
        # a creature or a planeswalker (a land, a noncreature artifact): no
        # mark, no DAMAGE row, no lifelink. Selectors never offer one; a
        # forced binding (a harness stimulus) can.
        return False
    if _protection_prevents(ctx, target, n):
        return False  # CR 702.16e: a permanent with protection from the source
    # Prevention before apply for card damage (Pack Leader). A live
    # DamageDealtEvent PreventionRecord (from the PREVENT_EFFECT lane) vetoes
    # the WHOLE mark (QUnbounded = "all"); the vetoed event leaves NO DAMAGE
    # row, so "whenever dealt damage" triggers correctly never see it. The
    # combat flag rides the same executor signal the journal's is_combat
    # half reads.
    if ctx.replacements is not None:
        rec = ctx.replacements.prevented_card_damage(
            ctx,
            target,
            combat=bool(ctx.executor._combat_wave_open),
        )
        if rec is not None:
            ctx.events.append(
                (
                    len(ctx.events),
                    "DAMAGE_PREVENTED",
                    str(target),
                    str(rec.source),
                    n,
                )
            )
            return False
    # The replacement lane over CARD damage (Fiery Emancipation). The
    # consult's QUANTITY-MODIFICATION half rewrites the mark before it lands
    # — the permanent lane (walker loyalty below, the damage ledger, the
    # DAMAGE row and its lifelink twin) then reads the dealt number exactly
    # like the player lane. A record in the CONSUME shape (an action that is
    # not the DEAL_DAMAGE quantity rewrite) would have to prevent the mark AND
    # run its action against a card; nothing here does that (Nine Lives' "to
    # you" filter never reaches this lane: the consult's player-idiom gate
    # skips it), so it raises, never silently dropped. CR 616.1: several may
    # apply in turn, in the order the permanent's controller chose.
    if ctx.replacements is not None:
        for repl, new_n in ctx.replacements.replacements_for_damage(
            ctx,
            target,
            ctx.source,
            n,
            combat=bool(ctx.executor._combat_wave_open),
        ):
            if new_n is None:
                raise NotImplementedError(
                    "executor: a card-damage replacement whose action is "
                    "not a quantity rewrite has no consumer (flag, never "
                    "guess) — r22b"
                )
            ctx.events.append(
                (
                    len(ctx.events),
                    "DAMAGE_MODIFIED",
                    str(target),
                    str(repl.source),
                    n,
                    new_n,
                )
            )
            n = new_n
    # CR 120.4d: damage dealt to a PLANESWALKER removes that many loyalty
    # counters — the walker lane never MARKS damage (there is no toughness
    # read for it; the zero-loyalty state check in the settle sweep does the
    # burying). The DAMAGE row and lifelink ride the dealt amount exactly
    # like the creature lane.
    state = ctx.world.cards.get(target)
    if state is not None and state.identity.loyalty is not None:
        counters = state.counters
        have = counters.get("LOYALTY")
        if have is None:  # unseeded ledger: the printed loyalty (legality._loyalty_of)
            have = int(str(state.identity.loyalty))
        counters["LOYALTY"] = max(0, have - n)
        ctx.events.append((len(ctx.events), "DAMAGE", str(target), n))
        _lifelink_gain(ctx, n)
        return True
    deathtouch = _source_has(ctx, Keyword.DEATHTOUCH)
    ctx.executor.mark_damage(target, n, deathtouch=deathtouch)
    ctx.events.append((len(ctx.events), "DAMAGE", str(target), n))
    _lifelink_gain(ctx, n)  # after the mark, on the dealt amount
    return True


def _fight_attacker(ctx: ExecCtx) -> Handle | None:
    """The compiled FIGHT atom carries NO attacker role: the attacker is the
    ability's SOURCE when that source is a battlefield permanent (Brash
    Taunter's {2}{R}{T} — "this creature fights"), else the PRECEDING atom's
    result register (Primal Might's "it also fights" anaphora — _apply_pt
    writes it).

    An EMPTY register means the preceding atom acted on nothing: Primal
    Might's own creature left or became an illegal target while its fight
    target is still legal, so the spell resolves. CR 701.14b: neither
    creature fights, so None, never a raise. So does a permanent's ability
    whose source left the battlefield (its last known information is kept,
    ``departed_lki``) while it waited on the stack: "this creature fights",
    and CR 701.12b: a creature no longer on the battlefield deals and is dealt
    no damage. Otherwise no register at all raises (no antecedent was
    compiled)."""
    if (
        ctx.source.namespace == "card"
        and ctx.source in ctx.world.cards
        and ctx.world.zone_of(ctx.source).kind == ZONE_BATTLEFIELD
    ):
        return ctx.source
    result = ctx.binding_handles("result")
    if result:
        return result[0]
    if result is not None or (ctx.executor is not None and ctx.source in ctx.executor.departed_lki):
        return None
    raise NotImplementedError(
        f"executor: FIGHT has no attacker — {ctx.source} is not a battlefield "
        "permanent and no preceding atom wrote the result register"
    )


def _v_fight(ctx: ExecCtx, atom: Atom) -> None:
    """CR 701.12b: "This creature fights another target creature" — each
    deals damage equal to its POWER to the other, simultaneously, and it is
    NOT combat damage (so no "whenever blocks/hits" reading; plain damage
    triggers do see it, CR 701.12e). Simultaneity is what the marked-damage
    ledger buys for free: both marks land inside this ONE atom boundary and
    the settle SBA resolves the exchange — a mutual kill kills both, a
    non-lethal trade leaves both standing.

    A CHOOSE/ONE_OF/RANDOM designation is resolved by the ATOM ITSELF, at
    resolution, not read from the spell's bindings: Primal Might's
    spell-level "target" IS its own +X/+X creature, and feeding it back
    would turn "fights ANOTHER creature" into a self-punch. TARGET mode keeps
    the ordinary designation path (Brash Taunter's activation designated
    the foe)."""
    attacker = _fight_attacker(ctx)
    if attacker is None:
        # CR 701.14b: the creature told to fight is gone — no fight.
        ctx.events.append((len(ctx.events), "FIGHT", None, None))
        return
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
        # Nothing legal to fight — the fight simply is not.
        ctx.events.append((len(ctx.events), "FIGHT", str(attacker), None))
        return
    foe = foes[0]  # the compiled FIGHT surface designates exactly one
    ctx.events.append((len(ctx.events), "FIGHT", str(attacker), str(foe)))
    for a, b in ((attacker, foe), (foe, attacker)):
        power, _toughness = ctx.effective_pt(a)
        if power and power > 0:
            # CR 701.12b, 120.1: each fighting creature deals its own damage, so
            # the creature, not the spell or ability, is the source that protection
            # (702.16e), deathtouch (702.2b) and lifelink (702.15b) read.
            _deal_damage_to_card(replace(ctx, source=a), b, power)


def _set_tapped(ctx: ExecCtx, atom: Atom, tapped: bool) -> None:
    if atom.args.get("duration") is not None:
        raise NotImplementedError(
            "executor: duration-tagged TAP/UNTAP is 12d (the ledger vocab)"
        )
    cards = role_handles(ctx, atom, "target")
    for card in cards:
        ctx.world.cards[card].tapped = tapped
        ctx.events.append((len(ctx.events), atom.verb.name, str(card), int(tapped)))
    if tapped:
        # "for each creature tapped THIS WAY" (Siege Striker) reads this
        # register — the last TAP atom of the same effect execution (fresh
        # bindings per resolution; a skipped Optional tap leaves it absent
        # -> magnitude 0).
        ctx.bindings["tapped_this_way"] = list(cards)
    # The object of the last ACTION is the antecedent of a following "it"
    # ("Tap target creature: it gains X" / Traitorous Greed's "Untap that
    # creature. It gains haste"). Producers write the ``result`` register
    # inside any effect execution; the ctx's bindings dict is fresh per
    # execute/apply_effect/cast_ctx, so it never leaks into the next one.
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
        # Blightbeetle: a card that can't have these counters put on it gets none (and no
        # replacement modifies a placement that does not happen).
        barred = (
            ctx.replacements.prevents_counter_placement(ctx, card, kind)
            if ctx.replacements is not None
            else None
        )
        if barred is not None:
            ctx.events.append(
                (
                    len(ctx.events),
                    "COUNTER_PREVENTED",
                    str(card),
                    str(barred.source),
                    kind.name,
                    n,
                )
            )
            continue
        # The CounterPlacedEvent replacement lane (Conclave Mentor) —
        # per RECEIVING card, the same consult-per-item shape the damage
        # lane uses. The queued 4-tuple carries (record, card, kind, n):
        # the drain binds {"event": [card]} and stamps event_counter_count
        # so the action's COUNTER_COUNT prop reads what WAS put (CR 614.3a
        # the original placement never happened, but the event's amount is
        # what the replacement modifies FROM — Mentor is ADD(QProp(event,
        # COUNTER_COUNT), 1)).
        repl = (
            ctx.replacements.replacement_for_counter_placement(ctx, card, kind, n)
            if ctx.replacements is not None
            else None
        )
        if repl is not None:
            ctx.pending_replacements.append((repl, card, kind, n))
            ctx.events.append(
                (
                    len(ctx.events),
                    "COUNTER_REPLACED",
                    str(card),
                    str(repl.source),
                    kind.name,
                    n,
                )
            )
            continue
        counters = ctx.world.cards[card].counters
        counters[kind.name] = counters.get(kind.name, 0) + n
        ctx.events.append((len(ctx.events), "PUT_COUNTER", str(card), kind.name, n))
    # The result register: "Put a +1/+1 counter on target creature…. It gains
    # X" (Feat of Resistance). See _set_tapped's note.
    ctx.bindings["result"] = list(cards)


def _v_remove_counter(ctx: ExecCtx, atom: Atom) -> None:
    kind = atom.args.get("counter_kind")
    assert isinstance(kind, CounterKind)
    n = amount(ctx, atom, "count")
    for card in role_handles(ctx, atom, "target"):
        state = ctx.world.cards[card]
        counters = state.counters
        if kind is CounterKind.LOYALTY and (
            kind.name in counters
            or (
                state.identity.loyalty is not None
                and ctx.world.zone_of(card).kind == ZONE_BATTLEFIELD
            )
        ):
            # CR 306.5c, 704.5i: the LOYALTY key IS the loyalty, and an absent key
            # means an unseeded ledger that reads the printed loyalty
            # (legality._loyalty_of). So 0 stays a value: popping it would reset a
            # walker brought to 0 to its printed loyalty instead of letting the state
            # check put it into its owner's graveyard. Same read and write as the
            # damage lane (CR 120.3c); the key leaves with the walker (_on_zone_changes).
            have = counters.get(kind.name)
            if have is None:
                have = int(str(state.identity.loyalty))
            counters[kind.name] = max(0, have - n)
            ctx.events.append(
                (len(ctx.events), "REMOVE_COUNTER", str(card), kind.name, n)
            )
            continue
        remaining = max(0, counters.get(kind.name, 0) - n)
        if remaining:
            counters[kind.name] = remaining
        else:
            counters.pop(kind.name, None)
        ctx.events.append((len(ctx.events), "REMOVE_COUNTER", str(card), kind.name, n))


def _pt_delta_value(quantity: object, ctx: ExecCtx) -> int:
    """power/toughness role -> a signed int adjustment (PtDelta keeps
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
    power_set, toughness_set)`` — the shared extraction :func:`_apply_pt` and
    the static layers (``layers``) both run through (one numeric semantics,
    no second parser)."""
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
    # UNTIL_LEAVES resolves its referent NOW (register boundary) — the
    # ledger stores a Handle anchor, never a string to re-parse later.
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
    # The result register (FIGHT anaphora): "Target creature gets +X/+X. It
    # also fights another target creature" (Primal Might) — the fight
    # attacker is THIS atom's object, so the PT verbs write the register
    # the same way TAP/PUT_COUNTER do.
    ctx.bindings["result"] = list(cards)


def _v_modify_pt(ctx: ExecCtx, atom: Atom) -> None:
    _apply_pt(ctx, atom, "delta")


def _v_set_pt(ctx: ExecCtx, atom: Atom) -> None:
    _apply_pt(ctx, atom, "set")


# ---------------------------------------------------------- layer verbs


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
    """GRANT_ABILITY / LOSE_ABILITY: register a layer over the designated
    targets; the Duration vocab (incl. until-end-of-turn) is what ends it —
    layers never expire silently."""
    ability = atom.args.get("ability")
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
    # "Target creature gains deathtouch and lifelink until end of turn. If it's a Vampire,
    # ..." (Sorin, Imperious Bloodlord): the sentence names the objects it changed.
    ctx.bindings["result"] = list(targets)


def _v_grant(ctx: ExecCtx, atom: Atom) -> None:
    _v_grant_or_lose(ctx, atom, lose=False)


def _v_lose(ctx: ExecCtx, atom: Atom) -> None:
    _v_grant_or_lose(ctx, atom, lose=True)


def _v_prevent(ctx: ExecCtx, atom: Atom) -> None:
    """PREVENT_EFFECT: a pre-application veto record. The condition's
    affected set is materialized NOW (its anaphora is only decidable at this
    boundary): the designated targets (IS_ANY_TARGET, Frost Breath's "those
    creatures"), or the objects the previous instruction acted on (IS_RESULT,
    the ``result`` register: Teferi, Timeless Voyager's "they"). Each
    consuming lane reads the records for its event (the UNTAP step reads the
    TapStateEvent family, the phasing step the PhasingEvent one)."""
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
    # CR 608.2b: the targeting restrictions written beside IS_ANY_TARGET in
    # a combat slot ("another target creature with power 2 or less") are checked
    # as the ability resolves; the creatures that pass are locked in, and the
    # record reads only that set afterwards (replacements._slot_holds), so a
    # pump after resolution does not undo "can't be blocked this turn".
    from MTG_bot.core.executor.query import combat_target_filters, names_pred

    register = "result" if names_pred(condition, FAtomPred.IS_RESULT) else "target"
    designated = ctx.binding_handles(register)
    if designated is None and register == "result":
        raise NotImplementedError(
            "executor: PREVENT_EFFECT's IS_RESULT names the result register, and no "
            "instruction before it wrote one"
        )
    designated = designated or []
    bound = combat_target_filters(event)
    targets = tuple(
        h
        for h in designated
        if eval_filter(condition, h, ctx) and all(eval_filter(f, h, ctx) for f in bound)
    )
    ctx.replacements.register_prevention(
        ctx.source, ctx.controller, condition, event, step, duration, targets, resolved=True
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
    creator = ctx.controller
    if atom.args.get("controller") is not None:
        # The anaphoric creator — "ITS CONTROLLER creates a … token" (Secure
        # the Scene). The role resolves through the same role_players lane
        # LOSE_LIFE uses for its controller-of-the-referent reads (a
        # referent-target selector folds a card binding to its controller).
        # No role = the ability's controller. A resolution that names ZERO or
        # MULTIPLE players is flagged, never guessed — the printed clause has
        # exactly one antecedent.
        resolved = sorted(role_players(ctx, atom, "controller"))
        if len(resolved) != 1:
            raise ValueError(
                f"executor: CREATE_TOKEN controller role resolved to "
                f"{len(resolved)} players (need exactly 1)"
            )
        creator = resolved[0]
    created: list[Handle] = []
    for _ in range(n):
        power = None if spec.power is None else resolve(spec.power, ctx)
        toughness = None if spec.toughness is None else resolve(spec.toughness, ctx)
        oracle_id = token_oracle_id(spec.name)
        identity = CardIdentity(
            oracle_id=oracle_id,
            name=spec.name,
            type_line=spec.type_line,
            colors=spec.colors,  # every printed colour (WUBRG order)
            power=None if power is None else str(power),
            toughness=None if toughness is None else str(toughness),
            keywords=tuple(k.name for k in spec.keywords),
            is_token=True,
        )
        handle = ctx.world.add_card(identity, creator, ZONE_BATTLEFIELD)
        created.append(handle)
        # The token's own rule lines ("This token can't block", "Creatures
        # you control attack each combat if able" — the Pursued Whale
        # Pirate) are STATIC/TRIGGERED ability nodes on the TokenSpec. The
        # binder needs a record under the token's synthetic oracle id BEFORE
        # the battlefield row is journalled (record_atom's diff runs after
        # this atom), so the ZONE_CHANGE lifecycle finds it and registers
        # the statics (prevention registry + mandate layers) and binds any
        # trigger exactly like a printed permanent. The CardRecord is syn-
        # thesized from the spec (the same shape the compiler builds a token
        # record into) the first time its name is seen.
        if ctx.executor is not None and spec.abilities:
            record = ctx.executor.binder.records.get(oracle_id)
            if record is None:
                record = CardRecord(
                    oracle_id=oracle_id,
                    name=spec.name,
                    type_line=spec.type_line,
                    types=spec.types,
                    subtypes=spec.subtypes,
                    supertypes=(),
                    colors=spec.colors,
                    color_identity=frozenset(spec.colors),
                    mana_cost=None,
                    mana_value=0,
                    power=spec.power,
                    toughness=spec.toughness,
                    loyalty=None,
                    keywords=tuple(KeywordAbility(keyword=k) for k in spec.keywords),
                    abilities=spec.abilities,
                    is_token=True,
                )
            ctx.executor.binder.register_token(handle, record)
        if spec.enters_tapped:
            ctx.world.cards[handle].tapped = True
        if spec.enters_attacking:
            # CR 508.4 ("put those creatures onto the battlefield
            # attacking", Falconer Adept's Bird, Basri Ket's [-2] Soldier):
            # a token created DURING the declare-attackers window joins the
            # attack record without any legality pass. It was never
            # declared, it ENTERS attacking, so it has no declare row
            # (Executor.join_attack). Created outside the window (an ETB in
            # a main phase) the flag is inert: there is no attack to join.
            ex = ctx.executor
            if ex is not None and ex.declaring:
                ex.join_attack(handle)
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
    # The tokens are the objects this instruction acted on, so a later one names
    # them ("create a 1/1 Soldier creature token, then attach this Equipment to it").
    ctx.bindings["result"] = created


def _v_add_mana(ctx: ExecCtx, atom: Atom) -> None:
    player = role_player(ctx, atom)
    n = amount(ctx, atom, "amount")
    color = atom.args.get("color")
    if color is None or color == "ANY":
        color = ctx.take_decision(_ANY_COLOR_VOCAB, f"mana:{ctx.source}")
    pool = ctx.world.players[player].mana_pool
    pool[color] = pool.get(color, 0) + n
    ctx.events.append((len(ctx.events), "ADD_MANA", str(player), color, n))
    if ctx.executor is not None:
        # The segment mirror: the pool totals write above is UNTOUCHED — the
        # segment rides alongside, tagged by the source's live THIS_MANA
        # policy (Vodalian Arcanist compiles its "spend this mana only to cast
        # instant or sorcery spells" as a StaticAbility MANA_POLICY atom, so
        # activating the SAME permanent is what marks its own mana; mana from
        # elsewhere stays clean). Untagged mana pays exactly as the pool
        # totals say.
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
    # Site tag: owner + count. The per-card asks share the key; the stream's
    # FIFO serves them in ask order.
    what = f"scry:{player}:{n}"
    for card in top_down:  # decisions are consumed one per card, top first
        if ctx.take_decision(("top", "bottom"), what) == "top":
            tops.append(card)
        else:
            bottoms.append(card)
    # Canonical within-group order (the rules let the scryer order each
    # group freely; we pin Handle-ascending, ascending = toward the top).
    # CR 701.1: a card put on the BOTTOM goes under the WHOLE library — the
    # unviewed remainder keeps its order and the tops land above it.
    lib.entries = sorted(bottoms) + lib.entries[: len(lib.entries) - n] + sorted(tops)
    ctx.events.append((len(ctx.events), "SCRY", str(player), n))


def _v_shuffle(ctx: ExecCtx, atom: Atom) -> None:
    """"Shuffle it into its owner's library" (an OWNER zone) shuffles the library of the owner of
    each card the previous instruction put there (the ``result`` register, CR 108.3), not the
    ability controller's. With none put there ("it" left the zone it was expected in), the
    library is shuffled all the same (CR 701.24c): the source's, as every card printing the
    clause shuffles itself (Cavalier of Gales), or itself and its target (Void Stalker)."""
    zone_ir = atom.args.get("zone")
    assert isinstance(zone_ir, Zone)
    state_kind = ZONE_KIND_TO_STATE.get(zone_ir.kind)
    if state_kind is None:
        raise NotImplementedError("executor: SHUFFLE of a non-card zone is 12c")
    if zone_ir.controller is ControllerRef.OWNER:
        moved = ctx.binding_handles("result") or []
        owners = sorted({ctx.world.controller_of(c) for c in moved if c.namespace == "card"})
        owners = owners or [ctx.world.controller_of(ctx.source)]
    else:
        owners = [zone_owner(ctx, zone_ir, owner=ctx.controller)]
    rng = ctx.rng("SHUFFLE")
    for owner in owners:
        zone = ctx.world.players[owner].zone(state_kind)
        rng.shuffle(zone.entries)  # seeded Random — replay-identical
        ctx.events.append((len(ctx.events), "SHUFFLE", str(owner), zone.kind))


def _look(ctx: ExecCtx, atom: Atom) -> None:
    """LOOK_AT / REVEAL: nothing moves; the knowledge is the event record.

    The cards are the top N of the library (the REVEAL/LOOK_AT convention),
    for a REVEAL with ``until`` the cards from the top down to the Nth match,
    or for an anaphoric REVEAL the window an earlier look showed."""
    if atom.args.get("duration") is not None:
        raise NotImplementedError(
            f"executor: continuous {atom.verb.name} (duration) is 12d"
        )
    player = role_player(ctx, atom)
    lib = ctx.world.players[player].zone(ZONE_LIBRARY)
    count_q = atom.args.get("count")
    # A REVEAL inside a LOOK_AT sentence (Garruk's Harbinger) is
    # anaphoric — "reveal [one card] from among them" — not a fresh top-of-
    # library look. Record the top-of-window payload, but preserve the wider
    # LOOK_AT window for the following ONE_OF/REST partition instead of
    # collapsing the population to the first card.
    prior_window = tuple(ctx.look_window)
    until = atom.args.get("until")
    if until is not None:
        # "Reveal cards from the top of your library until you reveal a creature
        # card" (Transmogrify): one card at a time, top first, until ``count``
        # revealed cards match ``until``, or every card is revealed (no match).
        # The matches are "that card" (the ``result``), every revealed card the
        # window, so "the rest" are the window's other cards; nothing moves
        # (CR 701.20b).
        assert isinstance(until, Filter)  # role table: a Filter
        n = amount(ctx, atom, "count")
        seen_cards, found = [], []
        for card in reversed(lib.entries):
            if len(found) >= n:
                break
            seen_cards.append(card)
            if eval_filter(until, card, ctx):
                found.append(card)
        ctx.bindings["result"] = found
    elif isinstance(count_q, QUnbounded):
        # QUnbounded is not number-resolvable, and here it means the ENTIRE
        # zone — the Cultivate compile idiom (REVEAL with an unbounded count
        # stands for the searched library, since the grammar cannot
        # reference the found set).
        seen_cards = list(reversed(lib.entries))
    elif prior_window and atom.verb is Verb.REVEAL:
        n = amount(ctx, atom, "count")
        seen_cards = list(prior_window[:n]) if n else []
    else:
        n = amount(ctx, atom, "count")
        seen_cards = list(reversed(lib.entries[-n:])) if n else []
        # A fresh top-N look or reveal is a result PRODUCER. The compiled
        # "it" / "those cards" of the next instruction is referent="result",
        # and the controller follows the instructions in order (CR 608.2c):
        # Garruk, Savage Herald's +1 ("Reveal the top card of your library.
        # If it's a creature card, put it into your hand. Otherwise, put it on
        # the bottom of your library.") needs it. Revealing moves nothing, so
        # the cards are still on top. The unbounded idiom above and the
        # anaphoric reveal from among a look window stay non-producers:
        # neither names its own cards.
        ctx.bindings["result"] = list(seen_cards)
    # The look window — the handles shown, top-first, for the NEXT sentence
    # (Conditional subject / library-TOP partition candidates). The event
    # record holds their str view.
    if (
        prior_window
        and atom.verb is Verb.REVEAL
        and until is None
        and len(prior_window) > len(seen_cards)
    ):
        ctx.look_window = prior_window
    else:
        ctx.look_window = tuple(seen_cards)
    seen = tuple(str(c) for c in seen_cards)
    ctx.events.append((len(ctx.events), atom.verb.name, str(player), seen))


# ----------------------------------------------------------- turn/library verbs


def _v_draw(ctx: ExecCtx, atom: Atom) -> None:
    """DRAW: :meth:`GameWorld.draw` takes the top of the library
    (last entry, zone order). A draw the library cannot cover draws
    nothing more; the attempt is recorded and the player loses at the next
    state-based-action check (CR 704.5b, ``Executor._player_losses``). The journal
    auto-detects the library->hand move and emits CARD_DRAWN with the
    (drawer, ordinal) payload (events.py) — this row is the raw audit line,
    like MILL/MOVE."""
    player = role_player(ctx, atom, "controller")
    count_q = atom.args.get("amount")
    assert isinstance(count_q, Quantity)
    n = resolve(count_q, ctx)
    ex = ctx.executor
    # CR 121.2: drawing N cards is N single card draws, and a draw replacement applies to each
    # of them. The CardDrawnEvent replacement lane (Teferi's Ageless Insight): a live record
    # whose event matches a draw queues its ACTION for the executor drain and that draw NEVER
    # happens (CR 614.3a — the replaced event is replaced WHOLE, the card stays in the
    # library). One record per draw is taken (first match): a second carrier applies to each
    # draw of the first one's action (the drain's replaced_seq guard keeps a record from
    # replacing its own, CR 614.5), so two Insights make one draw four cards. The CR 616.1
    # choice is not asked here: the pools' draw replacements are one rewrite (Teferi's Ageless
    # Insight, Alhammarret's Archive), so the order changes nothing (the damage lane asks,
    # replacements._choose). Unreplaced draws in a row share one DRAW audit row.
    run = 0
    for _ in range(n):
        repl = (
            ctx.replacements.replacement_for_card_draw(ctx, player)
            if ctx.replacements is not None
            else None
        )
        if repl is not None:
            if run:
                ctx.events.append((len(ctx.events), "DRAW", str(player), run))
                run = 0
            ctx.pending_replacements.append(repl)
            ctx.events.append(
                (len(ctx.events), "DRAW_REPLACED", str(player), str(repl.source), 1)
            )
            continue
        drawn = ctx.world.draw(player, 1)
        run += 1
        if ex is not None and not drawn:
            ex.drew_from_empty.add(player)  # CR 704.5b
        # The CR 504.5 'the first draw of the draw step' register — the
        # executor stamps the per-turn ordinal ONLY while the skeleton's draw
        # step is open, so main-phase draws (Niya's Restock, Loot) never touch
        # it and NOT_FIRST_DRAW_THIS_STEP answers False for them (quantity.py
        # reads the same pair of trackers).
        if ex is not None and ex._draw_step_open:
            ex.draw_step_ordinal[player] = ex.draw_step_ordinal.get(player, 0) + 1
    if run or not n:  # "draw 0 cards" keeps its audit row
        ctx.events.append((len(ctx.events), "DRAW", str(player), run))


def _search_designation(atom: Atom, ctx: ExecCtx) -> list[Handle]:
    """The SEARCH ``cards`` role designation — the shared enumeration the
    handler runs and :func:`MTG_bot.core.executor.query.legal_search`
    mirrors. Explicit bindings take precedence (the caller designated the
    found cards); otherwise the selector resolves: CHOOSE = the
    controller's pick when there is a choice (``ask_choose``), RANDOM =
    seeded ctx.rng draw, ONE_OF = the channel ask (Handle-sorted candidate
    vocabulary; exhaustion stays loud); TARGET reads the spell's designation
    or raises."""
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
    return [
        h
        for h in resolve_selector(
            sel,
            ctx,
            journal_partition=sel.mode in (SelectorMode.ONE_OF, SelectorMode.REST),
            ask_choose=True,  # a CHOOSE search designation is a decision
        )
        if h.namespace == "card"
    ]


def _v_search(ctx: ExecCtx, atom: Atom) -> None:
    """SEARCH (the Cultivate compile idiom — see
    ``compiler/templates_b5b.py::_build_cultivate_search``): designate the
    found cards, then MOVE each from its current zone to the destination.
    The destination is role-based (``move_destination``: the owner's zone),
    ``tapped_on_enter`` is honored on battlefield entry, and every move gets
    its journal row. Inside a ONE_OF/REST partition the atom only
    designates (below)."""
    dest_ir = atom.args.get("destination")
    assert isinstance(dest_ir, Zone)  # Atom validation guarantees it
    dest_kind = ZONE_KIND_TO_STATE.get(dest_ir.kind)
    if dest_kind is None:
        raise NotImplementedError(
            f"executor: SEARCH to {dest_ir.kind.name} is not a card zone (13a)"
        )
    tapped_on_enter = bool(atom.args.get("tapped_on_enter"))
    cards = _search_designation(atom, ctx)
    if ctx.search_partition:
        # Cultivate: the Seq's sibling MOVE_ZONE atoms are a ONE_OF/REST
        # PARTITION ("put one onto the battlefield tapped and the other into
        # your hand") — the destination in this atom is a compile-time
        # PLACEHOLDER (the split carries the real destinations). Delivering
        # here would empty the zone the partition picks from and silently
        # skip the ask. DESIGNATE ONLY: the cards stay put, the REVEAL atom
        # sees them in the library, and the 'result' register below is the
        # found-set record.
        ctx.bindings["result"] = list(cards)
        # The partition's population. 'result' is rewritten by the ONE_OF
        # MOVE_ZONE before the REST reads it, so the found set has its own slot.
        ctx.search_found = tuple(cards)
        for card in cards:
            ctx.events.append((len(ctx.events), "SEARCH", str(card), "designated"))
        return
    stayed: set[Handle] = set()
    for card in cards:
        # The owner's zone, a non-owner controller as a control entry.
        target_player, new_controller = move_destination(ctx, dest_ir, dest_kind, card)
        src = ctx.world.zone_of(card)
        host: Handle | None = None
        if dest_kind == ZONE_BATTLEFIELD:
            # CR 303.4f: the player an Aura enters under (the controller if not the owner)
            # chooses its host.
            enters, host = _aura_entry_host(ctx, card, new_controller or target_player)
            if not enters:
                stayed.add(card)  # CR 303.4g: nothing to enchant, it stays
                continue
        zone = ctx.world.players[target_player].zone(dest_kind)
        ctx.world.move_card(card, zone)
        if new_controller is not None:
            _enter_under_control(ctx, card, new_controller)
        if tapped_on_enter and dest_kind == ZONE_BATTLEFIELD:
            ctx.world.cards[card].tapped = True
        ctx.events.append(
            (len(ctx.events), "SEARCH", str(card), f"{src.kind}->{dest_kind}")
        )
        if host is not None:
            _attach_entering_aura(ctx, card, host)
    # The found cards land in the ability's ``result`` register — the same
    # read-back convention the CHOOSE atom uses ("the follow-up atom's
    # referent='result' Selector reads it"). The compiler emits that
    # referent after SEARCH (Necromentia's EXILE).
    ctx.bindings["result"] = [c for c in cards if c not in stayed]


def _executor_or_raise(ctx: ExecCtx, verb: str):
    """The executor, for verbs that use EXECUTOR-side state (the turn, flip and
    loss ledgers, the binder, the layers: the frozen state carries none of
    it) — a bare unit-test ExecCtx has none."""
    if ctx.executor is None:
        raise ValueError(
            f"executor: {verb} needs an executor-backed ExecCtx "
            "(bare ExecCtx has no turn ledger)"
        )
    return ctx.executor


def _v_flip_coin(ctx: ExecCtx, atom: Atom) -> None:
    """FLIP_COIN (Tavern Swindler): the flip is the ONLY randomness — it
    flows through the executor-owned seeded ``ctx.rng`` (replay identical).
    Heads -> ``ctx.controller`` wins; tails -> the FIRST opponent (Handle
    order) wins, a 2-player simplification: the grammar's who-gates are
    YOU/opponent pairs, and the multiplayer reading is untested. The winner
    lives on the executor because the FLIP_WON conditional is a SEPARATE
    ability row (two compiled rows per Tavern Swindler)."""
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
    """END_TURN (Discontinuity): the request flag is set here; the turn
    ends at the op boundary through the CR 724.1 procedure
    (:meth:`Executor._end_the_turn`: no end step, straight to the cleanup
    step). The journal position is recorded as the process start, so the
    abilities that triggered before it cease to exist (724.1a)."""
    executor = _executor_or_raise(ctx, atom.verb.name)
    if not executor.end_turn_requested:
        executor.end_turn_mark = len(executor.journal.events)
    executor.end_turn_requested = True
    # The clock moves ahead of the close: an activation attempted later in
    # the SAME op is already out of the sorcery window (legality reads
    # ``executor.phase``), and the end of the turn re-stamps it.
    executor.phase = "END_TURN"
    ctx.events.append((len(ctx.events), "END_TURN", str(ctx.controller)))


def _v_extra_turn(ctx: ExecCtx, atom: Atom) -> None:
    """EXTRA_TURN (Teferi's -10): the controller takes
    ``count`` extra turns after this one. CR 500.7: the turns are added
    directly after the current turn, one at a time, and the most recently
    created turn is taken first, so they go to the FRONT of the queue
    (:meth:`Executor.advance_turn` pops index 0), ahead of any extra turn
    created earlier. The normal turn order resumes after the queue drains
    (``advance_turn`` keeps that rotation)."""
    executor = _executor_or_raise(ctx, atom.verb.name)
    count_q = atom.args.get("count")
    assert isinstance(count_q, Quantity)
    n = resolve(count_q, ctx)
    executor.extra_turn_queue[0:0] = [ctx.controller] * n
    ctx.events.append((len(ctx.events), "EXTRA_TURN", str(ctx.controller), n))


def _v_phase_out(ctx: ExecCtx, atom: Atom) -> None:
    """PHASE_OUT (CR 702.26; Teferi, Master of Time's [−3], Teferi, Timeless
    Voyager's [−8]): the permanents the ``target`` role names phase out
    (:meth:`Executor.phase_out`: the status, indirect phasing, removal from
    combat). The role's Selector resolves itself: a TARGET selector reads
    the designation (only targets still legal, CR 608.2b), an ALL selector
    ("each creature target opponent controls") its population, whose
    filter reads the designated player. ``role_handles``' binding-first
    lane would hand that designated PLAYER to the verb instead. The
    permanents that phased out directly are the ``result`` register (the
    anaphora "they" of a following instruction)."""
    executor = _executor_or_raise(ctx, atom.verb.name)
    sel = atom.args.get("target")
    assert isinstance(sel, Selector)  # role table: PHASE_OUT target is a Selector
    cards = [h for h in resolve_selector(sel, ctx) if h.namespace == "card"]
    ctx.bindings["result"] = executor.phase_out(cards)


def _v_lose_game(ctx: ExecCtx, atom: Atom) -> None:
    """LOSE_GAME: the frozen GameWorld carries no per-player lost flag
    (state.py is frozen) — so the loss lands on an EXECUTOR-side ledger;
    the game ends at the next state-based-action check
    (``Executor._player_losses``, which also owns the CR 704.5a/b losses).
    It also emits a GAME_LOST GameEvent row — subject the player — so every
    journal subscriber (dump, binder) sees the game end."""
    executor = _executor_or_raise(ctx, atom.verb.name)
    executor.lost_players.append(ctx.controller)
    executor.journal.emit(
        KIND_GAME_LOST, ctx.controller, None, "LOSE_GAME", ("LOSE_GAME",)
    )
    ctx.events.append((len(ctx.events), "LOSE_GAME", str(ctx.controller)))


# ------------------------------------------------------------ cast-side verbs


def _v_pay(ctx: ExecCtx, atom: Atom) -> None:
    """PAY ("pay a cost as an effect" — "You may pay {2}", the
    Kraken/Devotee/Pilferer compile idiom). The OptionalEffect ancestor
    consumed the may-decision UPSTREAM (:meth:`Executor._run_effect`, tree
    order), so reaching this handler IS the choice to pay; CR 117.3 then
    leaves no second choice — a cost that cannot be paid RAISES (the offer
    surface ``query.optional_offer`` narrows unactionable may-offers in
    advance).

    Payer coordinate: ``ctx.controller`` — the ability's "you", the payer
    ``query.optional_offer`` checked. The role table gives PAY no payer
    role, and rows whose English names a different player ("that player
    may pay") ride the same atom; honouring the third-party payer is a
    known gap.

    Mana restrictions are honoured through the ordinary fold: this is
    :func:`legality.pay_costs` again, with no cast-use subject (effect
    mana purchases may not consume THIS_MANA — the conservative reading).
    The payment runs in its own contexts (``ctx_for``), so it never consumes
    this effect's decision pool."""
    from MTG_bot.core.executor.legality import (
        build_payment_plan,
        ctx_for,
        pay_costs,
        plan_mana_taps,
        tap_for_payment,
    )

    executor = _executor_or_raise(ctx, atom.verb.name)
    cost = atom.args.get("cost")
    pctx = ctx_for(executor, source=ctx.source, controller=ctx.controller)
    # CR 605.3a: the payer may tap mana abilities while paying; the same taps
    # query.optional_offer proved sufficient when it offered "fire".
    taps = plan_mana_taps(
        executor, ctx.controller, lambda: build_payment_plan(ctx.world, pctx, cost)[1]
    )
    tap_for_payment(executor, ctx.controller, taps or (), inside_atom=True)
    plan, why = build_payment_plan(ctx.world, pctx, cost)
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
    """CAST: the CAST atom is NOT a permission ledger entry. Every compiled
    row is the effect verb "cast the designated card" — OptionalEffect("you
    may cast") wrapped, ``source`` a Selector designating the card(s) (the
    'result' referent of a preceding exile/reveal, top-of-library, the
    IS_SOURCE self-cast), and the OPTIONAL ``cost`` role carrying either an
    EMPTY Cost (the cost-waiver idiom, "without paying its mana cost",
    CR 498.2) or a real Cost (additional cost). So the handler delegates to
    :func:`stack.cast_card`: designate, park, pay (or not — empty Cost),
    push, resolve, put — and the CAST EVENT fires, so "whenever you cast"
    triggers see effect-casts too (CR 601.2m).

    Designation: bindings first (role ``source``), else the Selector
    (CHOOSE-mode deterministic first-n stand-in; the may-decision upstream
    already covered the whole atom).
    A designated card WITHOUT a SpellAbility (a land, an unregistered
    card) RAISES — the honest per-card flag, never a silent skip that
    would fake a cast."""
    from MTG_bot.core.executor.stack import cast_card

    executor = _executor_or_raise(ctx, atom.verb.name)
    cards = role_handles(ctx, atom, "source")
    cost = atom.args.get("cost")  # None = the spell's own printed cost
    for card in cards:
        cast_card(
            executor,
            ctx.controller,
            card,
            cost_override=cost,
            x=ctx.x_value if ctx.x_value is not None else 0,
        )


def _v_choose(ctx: ExecCtx, atom: Atom) -> None:
    """CHOOSE ("You choose a noncreature, nonland card from it",
    Duress/Kitesail): the PLAYER decision this atom owns, consumed as an
    explicit index token into the Handle-sorted candidate pool — the same
    ORDER contract as Choose NODES (vocab ``str(i)`` over
    ``query.verb_choose_options`` order, so the query and the runtime
    agree). The pick lands in the ability's ``result`` register (the
    follow-up atom's ``referent='result'`` Selector reads it),
    Handle-sorted like every designation.

    An empty pool chooses NOTHING without consuming a decision (there is
    no choice to make — the legal zero, and a caller-facing token would
    pretend otherwise). Multi-pick rows (count != 1) stay the loud flag:
    the corpus compiles count=1 only."""
    from MTG_bot.core.executor.query import verb_choose_options

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
        # Forward the live bindings — the pool this atom enumerates can
        # be scoped to them (Zone(HAND, TARGET_PLAYER) on Duress).
        bindings=ctx.bindings,
    )
    if rows == ((),):
        ctx.bindings["result"] = []
        ctx.events.append((len(ctx.events), "CHOOSE", str(ctx.source)))
        return
    vocab = tuple(str(i) for i in range(len(rows)))
    what = f"choose:{ctx.source}:{site_digest(tuple(rows))}"
    if len(rows) == 1:
        # One legal pick is forced, never asked (the phantom gate; the
        # handle alias below would make it a two-token ask).
        pick = offer_or_autopick(ctx, vocab, what)
    else:
        # ADDITIVE handle aliases (Duress). A provider that resolves a pack
        # key ("prey") gets back a HANDLE string — which is not a positional
        # index token. Each singleton candidate row's own handle is
        # therefore a legal token too; query and runtime still agree because
        # the aliases ARE members of the query's own enumeration (rows),
        # appended after the ORDER tokens — the digest and the index lane
        # are unchanged by them.
        alias = {str(row[0]): str(i) for i, row in enumerate(rows) if len(row) == 1}
        ask_vocab = vocab + tuple(a for a in alias if a not in vocab)
        pick = ctx.take_decision(ask_vocab, what)
        pick = alias.get(pick, pick)
    chosen = rows[int(pick)]
    ctx.bindings["result"] = list(chosen)
    ctx.events.append(
        (len(ctx.events), "CHOOSE", str(ctx.source), tuple(str(h) for h in chosen))
    )


def _printed_match(filter_: Filter, type_line: str) -> bool:
    """A CHOOSE_NAME ``name_filter`` judged on a card's printed type line: its type,
    subtype and supertype words, under and/or/not. Any other predicate has no printed reading
    here: flagged, never guessed."""
    if isinstance(filter_, FAnd):
        return all(_printed_match(c, type_line) for c in filter_.children)
    if isinstance(filter_, FOr):
        return any(_printed_match(c, type_line) for c in filter_.children)
    if isinstance(filter_, FNot):
        return not _printed_match(filter_.inner, type_line)
    if isinstance(filter_, FAtom) and filter_.pred in (
        FAtomPred.TYPE_EQ,
        FAtomPred.SUBTYPE_EQ,
        FAtomPred.SUPERTYPE_EQ,
    ):
        return filter_.string_value in _type_line_tokens(type_line)
    raise NotImplementedError(
        f"executor: CHOOSE_NAME name_filter {filter_!r} has no printed reading"
    )


def _v_choose_name(ctx: ExecCtx, atom: Atom) -> None:
    """CHOOSE_NAME (Runed Halo's "As this enchantment enters, choose a card
    name", made as it enters: EtBState.effect): the chosen name is RECORDED
    (executor.name_choices, keyed by the source that wrote it, until that
    object leaves the battlefield) and read back by the NAME_CHOSEN filter
    predicate (quantity._eval_atom), e.g. in the PROTECTION keyword param
    the static grants.

    For a free-text name the pick is a decision token out of the enumerable
    candidate NAMES, narrowed by the optional ``name_filter`` (Necromentia's
    "a nonbasic card name"). In a dealt game the names are the format's card
    pool (``executor.name_pool``, every card the deck builder could have
    used), the filter judged on each card's printed type line, so the menu's
    content and order never reveal a card in a hidden zone (the world's
    names would: a card found only in the opponent's hand or library). A
    rig with no format (unit tests, scenario packs) still names the world's
    non-token cards. Seeded-random fallback is NOT offered: the name is a
    player decision, so the decision channel owns it (it raises when no
    lane answers — never hidden randomness for a choice a player makes)."""
    executor = _executor_or_raise(ctx, atom.verb.name)
    name_filter = atom.args.get("name_filter")
    if name_filter is not None:
        assert isinstance(name_filter, Filter)  # role table: name_filter is a Filter
    candidates: set[str] = set()
    if executor.name_pool:
        for name, type_line in executor.name_pool:
            if name_filter is None or _printed_match(name_filter, type_line):
                candidates.add(name)
    else:
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
    """MANA_POLICY (the spend restrictions): the CORPUS ships both
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
    layers: LayerRegistry = executor.layers
    layers.register_mana_policy(ctx.source, ctx.controller, atom)
    layers.recompute()  # the permission must be LIVE before the next plan
    ctx.events.append((len(ctx.events), "MANA_POLICY", str(ctx.source), scope))


def _v_get_emblem(ctx: ExecCtx, atom: Atom) -> None:
    """GET_EMBLEM: the emblem is a nested
    ``CardRecord`` on the SOURCE's compiled record (the compiler links
    owner -> emblem one-directionally), so the handler resolves the record
    through the binder bridge and hands the emblem record to the binder's
    emblem path (:meth:`binding.TriggerBinder.bind_emblem`) under a
    synthetic executor-owned handle. The emblem is NOT a world card — it
    never enters a zone; its triggers bind to the OWNER and its statics
    anchor to the OWNER (the emblem's "you"). CR 113.7: getting a second
    copy of the same emblem does nothing — the (owner, emblem oid) table is
    the idempotence gate, recorded as a duplicate event, never a rebind."""
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
    """GRANT_TYPE (Riddleform's ETB — "is a Sphinx in addition to its
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
    """ADD_LAND_PLAY (Azusa): register a
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
    """GRANT_ACTIVATION: the timing-permission
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
    window = atom.args.get("window")
    layers = executor.layers
    # Validates the filter and window first (layers._validate_activation_grant).
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


def _v_mandate_attack(ctx: ExecCtx, atom: Atom) -> None:
    """MANDATE_ATTACK (CR 508.1): record every selected creature as "attacks
    each combat if able" on the executor's mandates ledger. The STATIC shape
    (Furor of the Bitten, the Pursued Whale Pirate token) registers a
    selector-bearing "mandate" LAYER through
    :meth:`layers.LayerRegistry._new_static` and is resolved at each
    declare; this handler covers the DISPATCH shape — Pursued Whale's
    ETB trigger carries the compiler-hoisted token rule line as a
    MANDATE_ATTACK atom. Declare-legality CONSUMES both: a mandated
    creature's binary ask narrows to ATTACK-only (the policy is never
    offered an answer that breaks the rule) and the assembled set is
    whole-set-checked. A ledger entry whose creature left the battlefield
    goes inert (the declare filter re-reads zone + controller every
    combat)."""
    if ctx.executor is None:
        raise ValueError(f"executor: {atom.verb.name} needs an executor-backed ExecCtx")
    cards = _dispatch_mandate(ctx, atom, "mandate", ctx.executor.mandates)
    ctx.events.append(
        (
            len(ctx.events),
            atom.verb.name,
            str(ctx.source),
            tuple(sorted(str(c) for c in cards)),
        )
    )


def _dispatch_mandate(
    ctx: ExecCtx, atom: Atom, kind: str, ledger: set[Handle] | None
) -> list[Handle]:
    """Record one dispatched combat rule (MANDATE_ATTACK / MANDATE_BLOCK /
    ATTACK_POLICY); returns the designated creatures. The atom's ``duration``
    role is honoured. Without one (or Permanent) a mandate's creatures join
    the dispatch ``ledger``, which lasts until each leaves the battlefield
    (a rule with no ledger, ``None``, becomes a duration-less ``resolved``
    record, which ends the same way, CR 400.7). With one ("this turn",
    "until your next turn") the rule ends with its duration (CR 611.2a/b,
    514.2), so it becomes a ``resolved`` layer record riding the registry's
    expiry points."""
    assert ctx.executor is not None
    cards = role_handles(ctx, atom, "cards")
    duration = atom.args.get("duration")
    assert duration is None or isinstance(duration, Duration)
    if ledger is not None and (duration is None or isinstance(duration, DurationPermanent)):
        ledger.update(cards)
        return cards
    if isinstance(duration, DurationUntilLeaves) and duration.source != "source":
        # layers.expire_leaves anchors on the record's source only; another
        # referent would never expire (flag, don't degrade).
        raise NotImplementedError(
            f"executor: {atom.verb.name} UntilLeaves({duration.source!r}) has no "
            "expiry anchor (only the ability's source is tracked)"
        )
    if cards:
        ctx.executor.layers.register_rule(
            kind, ctx.source, ctx.controller, tuple(cards), atom, duration
        )
    return cards


def _v_mandate_block(ctx: ExecCtx, atom: Atom) -> None:
    """MANDATE_BLOCK (CR 509.1h "must be blocked if able"): the mirror
    of :func:`_v_mandate_attack` on the declaring-blockers side. Canopy
    Stalker's rule line is the carrier (the STATIC shape registers a
    selector-bearing ``"mandate_block"`` layer through layers._new_static;
    this handler covers the dispatch shape). The block-ask loop CONSUMES
    both: an unassigned mandated attacker narrows a blocker's vocabulary
    onto itself, and the whole-assignment check re-derives the greedy
    guarantee."""
    if ctx.executor is None:
        raise ValueError(f"executor: {atom.verb.name} needs an executor-backed ExecCtx")
    cards = _dispatch_mandate(ctx, atom, "mandate_block", ctx.executor.mandate_block)
    ctx.events.append(
        (
            len(ctx.events),
            atom.verb.name,
            str(ctx.source),
            tuple(sorted(str(c) for c in cards)),
        )
    )


def _v_attack_policy(ctx: ExecCtx, atom: Atom) -> None:
    """ATTACK_POLICY (CR 609.4) made by a resolving ability — "It can attack this
    turn as though it didn't have defender" (Roving Keep, Skyclave Squid): the
    creatures designated now carry the policy for the atom's duration, a
    ``resolved`` "attack_policy" layer record. The static shape (Drowsing
    Tyrannodon) registers through layers._new_static; the attack legality reads
    both (:func:`legality.attack_policy_applies`)."""
    if ctx.executor is None:
        raise ValueError(f"executor: {atom.verb.name} needs an executor-backed ExecCtx")
    cards = _dispatch_mandate(ctx, atom, "attack_policy", None)
    ctx.events.append(
        (
            len(ctx.events),
            atom.verb.name,
            str(ctx.source),
            str(atom.args.get("scope")),
            tuple(sorted(str(c) for c in cards)),
        )
    )


def _v_damage_assign_policy(ctx: ExecCtx, atom: Atom) -> None:
    """DAMAGE_ASSIGN_POLICY: a combat-damage ASSIGNMENT rule keyed to
    its source. The corpus carrier is the granted-ability shape — Garruk,
    Savage Herald's [-7] hands every creature you control a until-EOT
    StaticAbility carrying ``AS_UNBLOCKED`` ("you may have this creature
    assign its combat damage as though it weren't turned in"), which rides
    the layer registry and is read by :meth:`layers.policy_as_unblocked`.
    This handler covers the DISPATCH shape: the scope word is recorded on
    the executor keyed by the ability's source (the damage step consumes
    ledger ∪ layers), so a directly-dispatched policy atom behaves exactly
    like its granted twin. Atom validation limits the scope to its closed
    vocabulary (AS_UNBLOCKED)."""
    if ctx.executor is None:
        raise ValueError(f"executor: {atom.verb.name} needs an executor-backed ExecCtx")
    scope = atom.args.get("scope")
    ctx.executor.damage_policies[ctx.source] = str(scope)
    ctx.events.append((len(ctx.events), atom.verb.name, str(ctx.source), str(scope)))


# ---------------------------------------------------------- control verbs


def _v_gain_control(ctx: ExecCtx, atom: Atom) -> None:
    """GAIN_CONTROL (CR 611): write the executor's control overlay — the
    frozen world derives controller_of from the ZONE OWNER, so the overlay
    lives on the executor, consulted at every controller-semantic executor
    read site. Carriers: Traitorous Greed (DurationEot, TARGET
    selector) and Enthralling Hold (no Duration node over "enchanted
    creature" — the continuous effect of an aura ends when the aura stops
    existing, so that row alone is anchored to the SOURCE, and CR 704.5q's
    unattached-aura check is what physically ends it; any other row lasts
    its duration, CR 611.2a). ``UntilLeaves`` pairs its referent anchor
    exactly like :func:`_apply_pt`. The controller slot is the STRICT YOU
    of the corpus (CR 611.2a "you gain control"); any other ControllerRef
    RAISES — flag, never guess. When the effective
    controller actually changes mid-combat the creature leaves combat
    (CR 506.4a, applied inside :meth:`Executor.gain_control`)."""
    if ctx.executor is None:
        raise ValueError(f"executor: {atom.verb.name} needs an executor-backed ExecCtx")
    ctrl = atom.args.get("controller")
    if ctrl is not None and ctrl is not ControllerRef.YOU:
        raise NotImplementedError(
            f"executor: GAIN_CONTROL controller {ctrl!r} has no meaning "
            "in this runtime (corpus vocabulary is YOU)"
        )
    duration = atom.args.get("duration")
    assert duration is None or isinstance(duration, Duration)
    if duration is not None and not isinstance(
        duration, (DurationEot, DurationPermanent, DurationUntilLeaves)
    ):
        # The control registry ends an entry at the end-of-turn sweep, when its anchor or
        # the creature leaves the battlefield, or never; any other duration would leave the
        # control permanent (flag, don't degrade).
        raise NotImplementedError(
            f"executor: GAIN_CONTROL duration {type(duration).__name__} has no expiry in the "
            "control registry (Executor._expire_control)"
        )
    tag = duration_tag(duration)
    # CR 611.2a: control a resolved spell or ability gives lasts as long as its duration says
    # (with none stated, the game), whatever happens to its source: Sorin, Vampire Lord's
    # granted "{T}: Gain control of target creature" outlasts the Vampire. The one row tied to
    # its source is the Aura's "You control enchanted creature" (Enthralling Hold, compiled onto
    # its spell): the Aura's own continuous effect, which ends when the Aura leaves.
    target = atom.args.get("target")
    anchor: Handle | None = None
    if (
        duration is None
        and isinstance(target, Selector)
        and _names_the_attached(target.filter)
    ):
        anchor = ctx.source
    if isinstance(duration, DurationUntilLeaves):
        anchor = referent_handle(duration.source, ctx)
    gained: list[Handle] = []
    for card in role_handles(ctx, atom, "target"):
        if ctx.executor.gain_control(card, ctx.controller, tag, anchor):
            gained.append(card)
    if gained:
        ctx.executor.layers.recompute()  # "you control" scopes re-anchor NOW
    ctx.events.append(
        (
            len(ctx.events),
            atom.verb.name,
            str(ctx.source),
            tuple(sorted(str(c) for c in gained)),
            tag,
        )
    )


def _names_the_attached(filter_: object) -> bool:
    """Does the filter pick the permanent the source is attached to ("enchanted creature")?"""
    if isinstance(filter_, FAtom):
        return filter_.pred is FAtomPred.IS_ATTACHED_TO_SOURCE
    if isinstance(filter_, (FAnd, FOr)):
        return any(_names_the_attached(child) for child in filter_.children)
    if isinstance(filter_, FNot):
        return _names_the_attached(filter_.inner)
    return False


def _v_attach(ctx: ExecCtx, atom: Atom) -> None:
    """ATTACH (CR 701.4 "Equip {W}"): move one attachment edge on the
    executor's attachments table — the SAME table IS_ATTACHED_TO_SOURCE and
    the "equipped creature" layer scopes read, so an equip re-anchor is a
    replay-folded op, not a mirror. Both ends must be on the battlefield,
    else nothing moves (below); more than one equipment or host raises.
    Re-attaching an equipment overwrites its edge (one host per attachment,
    CR 301.5); an aura cast attaches through the STACK's aura step, not this
    verb."""
    if ctx.executor is None:
        raise ValueError(f"executor: {atom.verb.name} needs an executor-backed ExecCtx")
    equipment = role_handles(ctx, atom, "equipment")
    hosts = role_handles(ctx, atom, "target")
    world = ctx.world
    if not equipment or not hosts or any(
        handle not in world.cards or world.zone_of(handle).kind != ZONE_BATTLEFIELD
        for handle in (*equipment, *hosts)
    ):
        # CR 701.3b: an Equipment that can't be attached doesn't move. One that left the
        # battlefield before "attach this Equipment to it" resolved (Ancestral Blade) stays
        # where it is, and the effect does nothing.
        return
    if len(equipment) != 1 or len(hosts) != 1:
        raise ValueError(
            f"executor: ATTACH needs exactly one equipment and one host, got "
            f"{len(equipment)}/{len(hosts)}"
        )
    equipment, host = equipment[0], hosts[0]
    ctx.executor.attach_aura(equipment, host)
    ctx.events.append((len(ctx.events), atom.verb.name, str(equipment), str(host)))


def _v_counter_spell(ctx: ExecCtx, atom: Atom) -> None:
    """COUNTER_SPELL: counter the designated spell or ability on the stack.

    The designated target is the framed card, or the ability's own handle.
    The handler removes the victim's
    :class:`~MTG_bot.core.executor.stack.StackObject` from the stack (CR
    701.6a-b), so it never resolves; a spell's card moves to its owner's
    graveyard (CR 400.7), an ability ceases to exist.

    The ``unless`` role (CR 601.2h "unless its controller pays <cost>", the
    Miscast/Lofty Denial shape) is an ASK-TIME decision, not a guess: when
    the victim's controller CAN pay (from the pool, or with mana abilities
    activated now), the payer is asked PAY/PASS through the decision stream
    (tag ``pay:<seat>:<digest>``; never asked when unpayable). PAY runs the
    plan through ``pay_costs`` mid-resolution and the spell LIVES; PASS (or
    no plan) counters. Every unless-site journals exactly one KICKBACK row —
    ``UNPAYABLE`` is the witness when no decision was asked."""
    from MTG_bot.core.executor.legality import (
        build_payment_plan,
        ctx_for,
        pay_costs,
        plan_mana_taps,
        tap_for_payment,
    )

    ex = ctx.executor
    if ex is None:
        raise ValueError("executor: COUNTER_SPELL needs an executor-bound ctx")
    targets = role_handles(ctx, atom, "target")
    if not targets:
        # CR 608.2b: a spell with several targets resolves while any is legal, and an
        # instruction whose target became illegal does nothing (stack.recheck_targets emptied
        # this slot: Sublime Epiphany's counter mode after its target was countered). The
        # cast already required a designation, so an empty one here is never a compile fault.
        return
    spell = targets[0]
    frame = next((f for f in ex.stack.frames if f.handle == spell), None)
    if frame is None:
        raise ValueError(
            f"executor: COUNTER_SPELL target {spell} is not on the stack "
            "(only a framed spell can be countered)"
        )

    unless = atom.args.get("unless")
    if unless is not None:
        assert isinstance(unless, Cost)  # _VERB_ROLES: the unless role is a Cost
        payer = frame.controller
        pctx = ctx_for(ex, source=ctx.source, controller=payer)
        # CR 605.3a: "unless its controller pays" may be paid with
        # mana abilities activated now; payable iff some set of them pays.
        taps = plan_mana_taps(
            ex,
            payer,
            lambda: build_payment_plan(ctx.world, pctx, unless, mana_use=ctx.source)[1],
        )
        answer = "UNPAYABLE"
        if taps is not None:
            digest = site_digest((str(spell), frame.declared_clock))
            answer = ex.decisions.take(("PASS", "PAY"), f"pay:{payer}:{digest}", seat=payer)
            if answer == "PAY":
                tap_for_payment(ex, payer, taps, inside_atom=True)
                plan, why = build_payment_plan(ctx.world, pctx, unless, mana_use=ctx.source)
                if plan is None:  # pragma: no cover - the taps were proven sufficient
                    raise ValueError(f"executor: KICKBACK cannot pay: {why}")
                pay_costs(
                    ex,
                    plan,
                    source=ctx.source,
                    controller=payer,
                    mana_use=ctx.source,
                )
                if ctx.journal is not None:
                    ctx.journal.emit(
                        KIND_KICKBACK, spell, ctx.source, "KICKBACK", ("PAY",)
                    )
                ctx.events.append(
                    (len(ctx.events), "KICKBACK_PAID", str(payer), str(spell))
                )
                return
        if ctx.journal is not None:
            ctx.journal.emit(KIND_KICKBACK, spell, ctx.source, "KICKBACK", (answer,))

    ability = frame.spell_kind in ("ACTIVATED", "TRIGGERED")
    if not ability and ex.replacements.prevents_countering(spell):
        # CR 101.2, 701.6a: the spell can't be countered. The
        # counterspell targeted it legally and resolves, and its other
        # instructions happen; this one does nothing. Nothing was countered,
        # so there is no COUNTER row.
        ctx.events.append((len(ctx.events), "NOT_COUNTERED", str(spell), str(ctx.source)))
        return
    ex.stack.frames.remove(frame)  # CR 701.6a-b: a countered spell or ability leaves the stack
    if ctx.journal is not None:
        ctx.journal.emit(KIND_COUNTER, spell, ctx.source, "COUNTER_SPELL", ())
    if not ability:  # a spell goes to its owner's graveyard; an ability ceases to exist
        _move_to(ctx, spell, ctx.world.controller_of(spell), ZONE_GRAVEYARD)
    ctx.events.append((len(ctx.events), "COUNTER", str(spell), str(ctx.source)))


#: ``SUPPORTED_VERBS_V2`` (executor/__init__.py) derives from this table: an entry here is
#: what makes a verb engine-supported.
HANDLERS: dict[Verb, Callable[[ExecCtx, Atom], None]] = {
    Verb.MOVE_ZONE: _v_move_zone_until,  # _v_move_zone plus the "until" duration
    Verb.SACRIFICE: _to_graveyard,
    Verb.DESTROY: _to_graveyard,
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
    # The continuous-layers verbs + the pre-application prevention record.
    Verb.GRANT_ABILITY: _v_grant,
    Verb.LOSE_ABILITY: _v_lose,
    Verb.PREVENT_EFFECT: _v_prevent,
    # The library/turn-flow verbs.
    Verb.DRAW: _v_draw,
    Verb.SEARCH: _v_search,
    Verb.FLIP_COIN: _v_flip_coin,
    Verb.END_TURN: _v_end_turn,
    Verb.EXTRA_TURN: _v_extra_turn,
    Verb.PHASE_OUT: _v_phase_out,  # CR 702.26
    Verb.LOSE_GAME: _v_lose_game,
    # The cast-side verbs.
    Verb.PAY: _v_pay,
    Verb.CAST: _v_cast,
    Verb.CHOOSE: _v_choose,
    Verb.CHOOSE_NAME: _v_choose_name,
    Verb.MANA_POLICY: _v_mana_policy,
    # The counter verb, with its unless-kickback ask.
    Verb.COUNTER_SPELL: _v_counter_spell,
    # The permission/effect verbs — emblem acquisition, static type
    # grants, the additional-land allowance and the activation-window
    # relaxation.
    Verb.GET_EMBLEM: _v_get_emblem,
    Verb.GRANT_TYPE: _v_grant_type,
    Verb.ADD_LAND_PLAY: _v_add_land_play,
    Verb.GRANT_ACTIVATION: _v_grant_activation,
    # The damage-exchange verb (CR 701.12).
    Verb.FIGHT: _v_fight,
    # The combat rule lines: attack and block mandates (CR 508.1 "attacks
    # if able", 509.1h), the damage-assignment and attack policies (CR 609.4).
    Verb.MANDATE_ATTACK: _v_mandate_attack,
    Verb.MANDATE_BLOCK: _v_mandate_block,
    Verb.DAMAGE_ASSIGN_POLICY: _v_damage_assign_policy,
    Verb.ATTACK_POLICY: _v_attack_policy,
    # The control/attachment verbs (Traitorous Greed, Enthralling Hold,
    # the Equip carriers).
    Verb.GAIN_CONTROL: _v_gain_control,
    Verb.ATTACH: _v_attach,
    # The extra-trigger verb (Sanctum of All), with the AbilityTriggerEvent
    # fan-out.
    Verb.TRIGGER_ADDITIONAL: _v_trigger_additional,
}


def run_atom(atom: Atom, ctx: ExecCtx) -> None:
    """Dispatch one Atom to its handler; unsupported verbs RAISE."""
    handler = HANDLERS.get(atom.verb)
    if handler is None:
        raise NotImplementedError(f"executor: verb {atom.verb.name} not implemented")
    # The look window is ONE sentence wide — a non-look verb runs
    # with the window OPEN (it may consume it: the library-TOP partition
    # idiom) and CLOSES it on completion, so a later Conditional after any
    # other atom keeps the old ctx.source subject and a stale library
    # window can never leak forward. A look verb keeps/refreshes it.
    before = ctx.bindings.get("result")
    handler(ctx, atom)
    if atom.verb not in (Verb.LOOK_AT, Verb.REVEAL):
        ctx.look_window = ()
    # The same one-sentence width for "it" = the result register: fresh only
    # when THIS atom wrote it (producers assign a new list), so a Conditional
    # reads the previous sentence's object and never one from further back.
    ctx.result_fresh = ctx.bindings.get("result") is not before
