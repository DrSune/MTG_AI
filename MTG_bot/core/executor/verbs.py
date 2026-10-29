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
from dataclasses import replace

from MTG_bot.core.executor.events import KIND_ABILITY_TRIGGERED
from MTG_bot.core.ability_tree import (
    Ability,
    ActivationWindow,
    Atom,
    AtomArgs,
    CardRecord,
    ControllerRef,
    Cost,
    CounterKind,
    Duration,
    DurationPermanent,
    DurationUntilLeaves,
    EventSpec,
    FAnd,
    FAtom,
    Filter,
    FNot,
    FOr,
    Keyword,
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
    ZonePosition,
)
from MTG_bot.core.executor.decisions import site_digest
from MTG_bot.core.executor.durations_min import duration_tag
from MTG_bot.core.executor.events import (
    KIND_COUNTER,
    KIND_GAME_LOST,
    KIND_KICKBACK,
)
from MTG_bot.core.executor.quantity import (
    ExecCtx,
    eval_filter,
    referent_handle,
    resolve,
)
from MTG_bot.core.executor.selectors import (
    ZONE_KIND_TO_STATE,
    amount,
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

_COLORS_VOCAB = ("W", "U", "B", "R", "G", "C")


# ------------------------------------------------------------------- handlers


def _move_to(
    ctx: ExecCtx,
    card: Handle,
    player: Handle,
    kind: str,
    journal_kind: str = "MOVE",
) -> None:
    # journal_kind (T4 P1a A2 ii): the literal event-kind column of the
    # raw journalled row is a SLOT of the merged MOVE atom, never derived
    # from the verb — the milled shape still writes "MILL" bytes.
    src = ctx.world.zone_of(card)
    ctx.world.move_to_zone(card, player, kind)
    ctx.events.append((len(ctx.events), journal_kind, str(card), f"{src.kind}->{kind}"))


def _enter_under_control(ctx: ExecCtx, card: Handle, controller: Handle) -> None:
    """V24 (CR 110.2, 110.2a): a card put onto the battlefield under the control of a
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
    # T4 P1a (2026-10-07): the ONE move atom. MILL/DISCARD/EXILE compile
    # onto MOVE_ZONE with orthogonal slots — {from} states the departure
    # zone, {journal_kind} the raw-row kind (A2 ii), {pop_order} the
    # library pop (A2 iii), {target} the designation lane (A2 iv). The
    # three shape-branches below are the predecessor handlers' bodies
    # verbatim, so every journalled byte and register write is exactly
    # what the separate verbs produced (test_executor_p1a_move locks it).
    journal_kind = str(atom.args.get("journal_kind") or "MOVE")
    frm = atom.args.get("from")
    if atom.args.get("pop_order") == "TOP":
        # The mill shape (old _v_mill, verbatim): pop TOP of the named
        # library — an EXPLICIT order, never a selector resolution —
        # into the destination. The raw row keeps the literal "MILL"
        # because the kind rides in from the slot (A2 ii).
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
        # The discard shape (old _v_discard, verbatim — B-18 live-hand
        # re-read, C17 clamp, not-in-hand raise, A2(i) moved-set register).
        player = role_player(ctx, atom)
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
                # (the 13b 'result' register, the B-15 designation, the
                # B-13 channel ask) — the hand scoping below is only for
                # the raw engine-side CHOOSE/RANDOM/ALL stand-ins.
                cards = resolve_selector(
                    sel,
                    ctx,
                    journal_partition=sel.mode
                    in (SelectorMode.ONE_OF, SelectorMode.REST),
                )
            else:
                # 14c (B-18): CR 701.8a — a discard moves cards from the
                # ACTOR'S OWN hand, so the selection pool is the actor's
                # LIVE hand re-read at take time, filtered through the
                # Selector (Bad Deal: the discarding player lives in the
                # controller role; the raw Selector population spans both
                # hands). C17 clamp: fewer cards than the ceiling simply
                # discards fewer.
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
        moved: list = []
        for card in sorted(cards):
            if card not in hand:
                raise ValueError(
                    f"executor: MOVE_ZONE discard card {card} is not in {player}'s hand"
                )
            _move_to(ctx, card, player, dest_kind, journal_kind)
            moved.append(card)
        # 18b (R7 THAT_MANY_COUNT pairing): the DISCARDED SET is the
        # register — written even when empty (0 honestly, not a missing
        # question). A2(i): kept across the merge.
        ctx.bindings["result"] = moved
        return
    tapped_on_enter = bool(atom.args.get("tapped_on_enter"))
    cards = ctx.binding_handles("cards")
    if cards is None:
        sel = atom.args.get("cards")
        if sel is None:
            # A2(iv): the designation lane (old _v_exile verbatim) — the
            # objects ride `target`, NOT cards, so the r19c spell-
            # designation shadowing still finds the key; the result
            # register is written NOTHING (exile wrote none pre-merge).
            for card in role_handles(ctx, atom, "target"):
                _move_to(
                    ctx,
                    card,
                    ctx.world.controller_of(card),
                    dest_kind,
                    journal_kind,
                )
            return
        if not isinstance(sel, Selector):
            raise ValueError("executor: MOVE_ZONE cards role has no binding")
        n = 0 if isinstance(sel.count, QUnbounded) else resolve(sel.count, ctx)
        # 14c (B-13): the ONE_OF/REST partition modes SELECT specific
        # cards (the pick / its complement) — the top-n draw idiom and the
        # count clamp apply to the CHOOSE/draw idioms only; a partition
        # atom moves exactly what its Selector resolves.
        partition = sel.mode in (SelectorMode.ONE_OF, SelectorMode.REST)
        # r18a: the idiom is "move THE top n of your library to hand" —
        # an UNFILTERED, referent-less selector. A filtered CHOOSE on a
        # library zone is the 13a SEARCH tail (the named card already in
        # hand by the SEARCH atom; the tail stands for "put IT into your
        # hand" — Chandra's Firemaw / Garruk's Warsteed / Teferi's
        # Wavecaster): its population is the filter's answer, resolved
        # below, never the blind top-n draw that hoovered an unrelated
        # library card into hand (wave-1b firemaw over-draw).
        universal = isinstance(sel.filter, FAnd) and not sel.filter.children
        if (
            not partition
            and dest_kind == ZONE_HAND
            # R0 zone-fold (/129 §2 L5): the top-n draw idiom is guarded by
            # a SINGLETON-LIBRARY predicate on the zone set — deliberately
            # NOT ∃: a LIBRARY∪GRAVEYARD (or HAND∪LIBRARY) selector is a
            # SEARCH answer, and ∃-LIBRARY would let it take the blind
            # top-n draw lane (the wave-1b firemaw over-draw class).
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
    # r19b (See the Truth): a destination Zone.position == BOTTOM means the
    # cards land at the BOTTOM of the pile — move_card appends (top for a
    # library / end of order) and no-ops on a same-zone move, so the
    # bottom-put is completed here: each card is re-inserted at index 0,
    # iterating Handle-DESCENDING so the final bottom run reads ascending
    # (mirrors the scry canonical rule — doc-18a's sorted(bottoms)).
    # r21b (Epitaph Golem): the compiler emits NO position for the
    # "put it on the bottom of your library" idiom (verified corpus-wide:
    # every other MOVE_ZONE→LIBRARY consumer carries an explicit TOP or
    # BOTTOM — See the Truth's scry-puts, Bolas's Accumulator), so a
    # position-less LIBRARY destination IS the bottom-put. Defaulting it
    # to the append-top silently reversed Epitaph's printed card.
    bottom_dest = dest_ir.position is ZonePosition.BOTTOM or (
        dest_ir.position is None and dest_kind == ZONE_LIBRARY
    )
    for card in sorted(cards, reverse=True) if bottom_dest else cards:
        # V24: the owner's zone always (CR 400.3); a battlefield controller other
        # than the owner becomes a control entry below, never a zone (CR 108.3).
        target_player, new_controller = move_destination(ctx, dest_ir, dest_kind, card)
        src = ctx.world.zone_of(card)
        if dest_kind == ZONE_BATTLEFIELD:
            # r20b (Containment Priest): C24 replacement-before-apply for
            # the ENTER move itself — a live ZoneChangeEvent replacement
            # consumes the ETB (the permanent never becomes a permanent,
            # no battlefield placement, no tapped_on_enter stamp), and the
            # action (EXILE referent=event) runs as a journalled nested
            # effect with the moving card bound, mirroring the life lane.
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
    # 14e (B-9) producer: the MOVED cards are the register ("…put it onto
    # the battlefield…. It gains haste" — the Liliana, Waker of the Dead
    # emblem tail 14b-1 attached; inside a firing the seed was the event
    # subject, but the ACTION's object is the honest antecedent). The
    # top-n draw-idiom early-returns above write nothing: no object was
    # chosen, and an unset register stays a loud read.
    ctx.bindings["result"] = list(cards)


def _to_graveyard(ctx: ExecCtx, atom: Atom) -> None:
    for card in role_handles(ctx, atom, "target"):
        _move_to(ctx, card, ctx.world.controller_of(card), ZONE_GRAVEYARD)


def _v_gain_life(ctx: ExecCtx, atom: Atom) -> None:
    n = amount(ctx, atom, "amount")
    for player in sorted(role_players(ctx, atom)):
        # r19a (Life Goes On): C24 replacement-before-apply, mirrored from
        # the damage hook in _v_deal_damage. A live LifeGainedEvent
        # replacement consumes the event — no life mutation happens (the
        # journal sees no gain at all), the replacement's ACTION runs as a
        # nested journalled effect once this atom's boundary closes, and
        # the CR 614.4a chain guard (__init__.py's drain) keeps the same
        # record from re-replacing its own 8-life action.
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
    """r20a (CR 603.4): LIFELINK — "if this source deals damage, its
    controller gains that much life." The keyword is read through the
    layer registry (the deathtouch precedent, :func:`_deal_damage_to_card`),
    so a granted lifelink counts and a lost one stops counting. The gain
    is routed through the GAIN_LIFE VERB lane rather than a direct life
    bump: that keeps the C24 life-replacement interceptor honest AND
    journalled, so the KIND_LIFE_GAINED rows that Light of Promise's
    granted trigger and Indulging Patrician's LIFE_GAINED_THIS_TURN_GE
    threshold read are real life-gain events, not invisible arithmetic.
    The gain belongs to the SOURCE's controller — in the record's own
    coordinates, the CONTROLLER RULE again."""
    if n <= 0:
        return
    if ctx.executor is None or ctx.layers is None:
        return
    if ctx.source.namespace != "card":
        return
    if not ctx.layers.keyword_of(ctx.source, Keyword.LIFELINK):
        return
    atom = Atom(
        verb=Verb.GAIN_LIFE,
        args=AtomArgs(pairs=(("controller", ControllerRef.YOU), ("amount", QConst(n)))),
    )
    _v_gain_life(replace(ctx, controller=ctx.executor.controller_of(ctx.source)), atom)


def _v_trigger_additional(ctx: ExecCtx, atom: Atom) -> None:
    """T5-D (Sanctum of All): re-queue the ability THIS firing matched
    `count` extra times. The AbilityTriggerEvent fan-out stored the matched
    firing payload in the synthetic event's data; the re-queued firings are
    marked additional=True — CR 603.2e: an extra trigger is created without
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
        p.life = max(0, p.life - n)  # life clamps at 0; deaths are 12b state-checks
        ctx.events.append((len(ctx.events), "LOSE_LIFE", str(player), p.life))


def _v_deal_damage(ctx: ExecCtx, atom: Atom) -> None:
    if atom.args.get("dealer") is not None or atom.args.get("recipient") is not None:
        raise NotImplementedError(
            "executor: DEAL_DAMAGE dealer/recipient (C-4 damage surface) is 12b/12d"
        )
    n = amount(ctx, atom, "amount")
    combat = bool(getattr(ctx.executor, "_combat_wave_open", False))
    for target in role_handles(ctx, atom, "target"):
        n_i = n
        if target.namespace == "player":
            # 12d: C24 replacement-before-apply. r22b (Fiery Emancipation):
            # the unified damage consult serves both doctrines — a live
            # replacement that CONSUMES the event (Nine Lives' compiled row
            # is the canonical) leaves no life mutation (the journal sees
            # no damage at all) and queues its action for the drain; one
            # that MODIFIES the event's quantity (Fiery's DEAL_DAMAGE
            # action rewriting QProp(event, AMOUNT)) rewrites the amount
            # IN PLACE, so exactly one journalled DAMAGE row lands on the
            # tripled number and dealer attribution / lifelink stay on the
            # dealt amount.
            res = (
                ctx.replacements.replacement_for_damage(
                    ctx, target, ctx.source, n_i, combat
                )
                if ctx.replacements is not None
                else None
            )
            if res is not None:
                repl, new_n = res
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
                    continue
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
            p = ctx.world.players[target]
            p.life = max(0, p.life - n_i)
            ctx.events.append((len(ctx.events), "DAMAGE", str(target), p.life))
            _lifelink_gain(ctx, n_i)  # r20a: lifelink reads ANY damage dealt
            continue
        # 16a (CR 120.4/120.6): damage is MARKED, never instant-lethal. The
        # mark rides the executor's damage ledger and the settle tail's
        # state-based check (CR 704.5a) does the destroying — so two
        # creatures trading non-lethal blows both survive, and a lethal
        # exchange is a simultaneous double kill. The DAMAGE tuple keeps
        # feeding the journal's KIND_DAMAGE row (events.py), so "is dealt
        # damage" triggers (Brash Taunter) are unchanged.
        _deal_damage_to_card(ctx, target, n_i)


def _deal_damage_to_card(ctx: ExecCtx, target: Handle, n: int) -> None:
    """One card-side damage application: mark it, journal it, decide nothing.
    16c (CR 702.2b): when the SOURCE carries DEATHTOUCH the mark is flagged
    lethal-in-itself, so the state check buries a 3/3 under one point of
    Fetid Imp venom (the keyword is read through the layer registry, so a
    granted deathtouch counts and a lost one stops counting)."""
    if ctx.executor is None:
        raise ValueError(
            "executor: card damage needs an executor-backed ExecCtx "
            "(bare ExecCtx has no damage ledger)"
        )
    # r20a (Pack Leader): prevention-before-apply for card damage. A live
    # DamageDealtEvent PreventionRecord (the PREVENT_EFFECT lane's first
    # damage consumer) vetoes the WHOLE mark (QUnbounded = "all"); the
    # vetoed event leaves NO DAMAGE row, so "whenever dealt damage"
    # triggers correctly never see it. The combat flag rides the same
    # executor signal the journal's is_combat half reads.
    if ctx.replacements is not None:
        rec = ctx.replacements.prevented_card_damage(
            ctx,
            target,
            combat=bool(getattr(ctx.executor, "_combat_wave_open", False)),
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
            return
    # r22b (Fiery Emancipation): the replacement lane over CARD damage. The
    # unified consult's QUANTITY-MODIFICATION half rewrites the mark before
    # it lands — the permanent lane (walker loyalty below, the damage
    # ledger, the DAMAGE row and its lifelink twin) then reads the dealt
    # number exactly like the player lane. A record in the CONSUME shape
    # (an action that is not the DEAL_DAMAGE quantity rewrite) would have
    # to prevent the mark AND run its action against a card — the corpus
    # carries no such consumer (Nine Lives' "to you" filter never reaches
    # this lane: the consult's player-idiom gate skips it) — so it stays
    # loud, never silently dropped.
    if ctx.replacements is not None:
        res = ctx.replacements.replacement_for_damage(
            ctx,
            target,
            ctx.source,
            n,
            combat=bool(getattr(ctx.executor, "_combat_wave_open", False)),
        )
        if res is not None:
            repl, new_n = res
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
    # r21a (CR 120.4d): damage dealt to a PLANESWALKER removes that many
    # loyalty counters — the walker lane never MARKS damage (there is no
    # toughness read for it; the zero-loyalty state check in the settle
    # sweep does the burying), and prevention above has already vetoed the
    # whole mark when a DamageDealtEvent record matches. The DAMAGE row and
    # lifelink ride the dealt amount exactly like the creature lane.
    state = ctx.world.cards.get(target)
    if state is not None and state.identity.loyalty is not None:
        counters = state.counters
        have = counters.get("LOYALTY")
        if have is None:  # unseeded ledger: the printed loyalty (13a twin)
            have = int(str(state.identity.loyalty))
        counters["LOYALTY"] = max(0, have - n)
        ctx.events.append((len(ctx.events), "DAMAGE", str(target), n))
        _lifelink_gain(ctx, n)
        return
    deathtouch = ctx.executor.layers.keyword_of(ctx.source, Keyword.DEATHTOUCH)
    ctx.executor.mark_damage(target, n, deathtouch=deathtouch)
    ctx.events.append((len(ctx.events), "DAMAGE", str(target), n))
    _lifelink_gain(ctx, n)  # r20a: after the mark, on the dealt amount


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
    if tapped:
        # 16b: "for each creature tapped THIS WAY" (Siege Striker) reads
        # this register — the last TAP atom of the same effect execution
        # (fresh ctx per resolution, the 14e pattern; a skipped Optional
        # tap leaves it absent -> magnitude 0).
        ctx.bindings["tapped_this_way"] = list(cards)
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
        # r22b (Conclave Mentor): the CounterPlacedEvent replacement lane —
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
    # 14e (B-9) producer: "Put a +1/+1 counter on target creature…. It gains
    # X" (Feat of Resistance at CAST resolution — the 14d headwall's dominant
    # face; Basri's two loyalty +2s). See _set_tapped's note.
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
            # V31 (CR 306.5c, 704.5i): the LOYALTY key IS the loyalty, and an absent
            # key means an unseeded ledger that reads the printed loyalty
            # (legality._loyalty_of). So 0 stays a value: popping it reset a walker
            # brought to 0 to its printed loyalty instead of letting the state check
            # put it into its owner's graveyard. Same read and write as the damage
            # lane (CR 120.3c); the key leaves with the walker (_on_zone_changes).
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
    creator = ctx.controller
    if atom.args.get("controller") is not None:
        # r25 (grammar round 11, R11-2): the anaphoric creator — "ITS
        # CONTROLLER creates a … token" (Secure the Scene / Angelic
        # Ascension s2). The role resolves through the same
        # role_players lane LOSE_LIFE uses for its controller-of-the-
        # referent reads (referent-target selector folds a card
        # binding to its controller, Gloom-Sower/Death-Mage
        # precedent). No role = the ability's controller, every
        # pre-round-11 row unchanged. A resolution that names ZERO or
        # MULTIPLE players is flagged, never guessed — the printed
        # clause has exactly one antecedent.
        resolved = sorted(role_players(ctx, atom, "controller"))
        if len(resolved) != 1:
            raise ValueError(
                f"executor: CREATE_TOKEN controller role resolved to "
                f"{len(resolved)} players (need exactly 1)"
            )
        creator = resolved[0]
    for _ in range(n):
        power = None if spec.power is None else resolve(spec.power, ctx)
        toughness = None if spec.toughness is None else resolve(spec.toughness, ctx)
        oracle_id = token_oracle_id(spec.name)
        identity = CardIdentity(
            oracle_id=oracle_id,
            name=spec.name,
            type_line=spec.type_line,
            colors=(spec.color,) if spec.color else (),
            power=None if power is None else str(power),
            toughness=None if toughness is None else str(toughness),
            keywords=tuple(k.name for k in spec.keywords),
            is_token=True,
        )
        handle = ctx.world.add_card(identity, creator, ZONE_BATTLEFIELD)
        # 16c (the token-record binder registration — the /13 named gap):
        # the token's own rule lines ("This token can't block", "Creatures
        # you control attack each combat if able" — the Pursued Whale
        # Pirate) are STATIC/TRIGGERED ability nodes on the TokenSpec. The
        # binder needs a record under the token's synthetic oracle id BEFORE
        # the battlefield row is journalled (record_atom's diff runs after
        # this atom), so the ZONE_CHANGE lifecycle finds it and registers
        # the statics (prevention registry + mandate layers) and binds any
        # trigger exactly like a printed permanent. The CardRecord is syn-
        # thesized from the spec (the same shape the compiler builds a token
        # record into); a name-seen spec is registered once.
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
                    colors=(spec.color,) if spec.color else (),
                    color_identity=frozenset({spec.color} if spec.color else set()),
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
            # 16b (CR 508.1i — "put those creatures onto the battlefield
            # attacking", Falconer Adept's Bird, Basri Ket's [-2] Soldier):
            # a token created DURING the declare-attackers window joins the
            # attack record (and its DeclareAttackers journal row) without
            # any legality pass — it was never declared, it ENTERS
            # attacking. Created outside the window (an ETB in a main
            # phase) the flag is inert: there is no attack to join.
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
    # r18a (CR 701.1): a card put on the BOTTOM goes under the WHOLE
    # library — the unviewed remainder keeps its order (order-preservation
    # for the rest) and the tops land above it. The old regroup stayed
    # INSIDE the viewed window, making every scry-1 "bottom" an exact
    # no-op (the wave-1b B-10 deviation: Temple of Malady's printed
    # bottom-branch, Stormwing Entity's bottom branch).
    lib.entries = sorted(bottoms) + lib.entries[: len(lib.entries) - n] + sorted(tops)
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
    # H4 (Garruk's Harbinger): a REVEAL inside a LOOK_AT sentence is
    # anaphoric — "reveal [one card] from among them" — not a fresh top-of-
    # library look. Record the top-of-window payload, but preserve the wider
    # LOOK_AT window for the following ONE_OF/REST partition instead of
    # collapsing the population to the first card.
    prior_window = tuple(ctx.look_window)
    if isinstance(count_q, QUnbounded):
        # 13a: QUnbounded is not number-resolvable, and here it means the
        # ENTIRE zone — the Cultivate compile idiom (REVEAL with an
        # unbounded count "counts" the searched library; the grammar's
        # documented inability to reference the found set).
        seen_cards = list(reversed(lib.entries))
    elif prior_window and atom.verb is Verb.REVEAL:
        n = amount(ctx, atom, "count")
        seen_cards = list(prior_window[:n]) if n else []
    else:
        n = amount(ctx, atom, "count")
        seen_cards = list(reversed(lib.entries[-n:])) if n else []
        # B-49 follow-up #5 (2026-10-29): a fresh top-N look or reveal is a
        # result PRODUCER (14e B-9 law). The compiled "it" / "those cards"
        # of the next instruction is referent="result" (R7-1: "revealed /
        # chosen / exiled / moved"), and the controller follows the
        # instructions in order (CR 608.2c). Garruk, Savage Herald's +1
        # ("Reveal the top card of your library. If it's a creature card,
        # put it into your hand. Otherwise, put it on the bottom of your
        # library.") paid its loyalty, then raised on the unset register.
        # Revealing moves nothing, so the cards are still on top. The
        # unbounded idiom above and the anaphoric reveal from among a look
        # window stay non-producers: neither names its own cards.
        ctx.bindings["result"] = list(seen_cards)
    # r19b: the look window — the handles shown, top-first, for the NEXT
    # sentence (Conditional subject / library-TOP partition candidates).
    # The event record stays the str view, byte-identical to pre-19b.
    if (
        prior_window
        and atom.verb is Verb.REVEAL
        and len(prior_window) > len(seen_cards)
    ):
        ctx.look_window = prior_window
    else:
        ctx.look_window = tuple(seen_cards)
    seen = tuple(str(c) for c in seen_cards)
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
    # r22b (Teferi's Ageless Insight): the CardDrawnEvent replacement lane.
    # A live record whose event matches this draw queues its ACTION for the
    # executor drain and the draw NEVER happens (CR 614.3a — the replaced
    # event is replaced WHOLE, cards stay in the library). One record per
    # draw is taken (first match): duplicate carriers chain through the
    # drain's replaced_seq guard, the CR 616.1 choice among DIFFERENT
    # replacement effects is unmodelled and stays loud at consult time.
    if ctx.replacements is not None:
        repl = ctx.replacements.replacement_for_card_draw(ctx, player, n)
        if repl is not None:
            ctx.pending_replacements.append(repl)
            ctx.events.append(
                (len(ctx.events), "DRAW_REPLACED", str(player), str(repl.source), n)
            )
            return
    ctx.world.draw(player, n)
    ctx.events.append((len(ctx.events), "DRAW", str(player), n))
    # r22b: the CR 504.5 'the first draw of the draw step' register — the
    # executor stamps the per-turn ordinal ONLY while the skeleton's draw
    # step is open, so main-phase draws (Niya's Restock, Loot) never touch
    # it and NOT_FIRST_DRAW_THIS_STEP answers False for them (quantity.py
    # reads the same pair of trackers).
    ex = ctx.executor
    if ex is not None and getattr(ex, "_draw_step_open", False):
        ex.draw_step_ordinal[player] = ex.draw_step_ordinal.get(player, 0) + 1


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
    return [
        h
        for h in resolve_selector(
            sel,
            ctx,
            journal_partition=sel.mode in (SelectorMode.ONE_OF, SelectorMode.REST),
            ask_choose=True,  # R3: a CHOOSE search designation is a decision
        )
        if h.namespace == "card"
    ]


def _v_search(ctx: ExecCtx, atom: Atom) -> None:
    """SEARCH (13a, the Cultivate compile idiom — see
    ``compiler/templates_b5b.py::_build_cultivate_search``): designate the
    found cards, then MOVE each from its current zone to the destination.
    The compiler's documented debt is CARD-level divergence (the ONE_OF/
    REST split re-searches the library in sibling atoms); per-ATOM
    faithfulness is what this handler owns. The destination is role-based
    (``move_destination``: the owner's zone, V24), ``tapped_on_enter``
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
    if ctx.search_partition:
        # r19a (Cultivate): the Seq's sibling MOVE_ZONE atoms are a
        # ONE_OF/REST PARTITION ("put one onto the battlefield tapped and
        # the other into your hand") — the destination in this atom is a
        # documented compile-time PLACEHOLDER (the split carries the real
        # destinations). Delivering here would empty the zone the partition
        # re-searches and silently skip the ask. DESIGNATE ONLY: the cards
        # stay put, the REVEAL atom sees them in the library, and the
        # 'result' register below is the found-set record.
        ctx.bindings["result"] = list(cards)
        for card in cards:
            ctx.events.append((len(ctx.events), "SEARCH", str(card), "designated"))
        return
    for card in cards:
        # V24: the owner's zone, a non-owner controller as a control entry.
        target_player, new_controller = move_destination(ctx, dest_ir, dest_kind, card)
        src = ctx.world.zone_of(card)
        zone = ctx.world.players[target_player].zone(dest_kind)
        ctx.world.move_card(card, zone)
        if new_controller is not None:
            _enter_under_control(ctx, card, new_controller)
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
    # r19c (Duress): ADDITIVE handle aliases. A provider that resolves a
    # pack key ("prey") gets back a HANDLE string — which is not a
    # positional index token, so the old vocabulary could never accept the
    # resolution. Each singleton candidate row's own handle is therefore a
    # legal token too; §8.3 identity holds because the aliases ARE members
    # of the query's own enumeration (rows), appended after the ORDER
    # tokens — the digest and the index lane stay byte-unchanged.
    alias = {str(row[0]): str(i) for i, row in enumerate(rows) if len(row) == 1}
    ask_vocab = vocab + tuple(a for a in alias if a not in vocab)
    pick = ctx.take_decision(
        ask_vocab, f"choose:{ctx.source}:{site_digest(tuple(rows))}"
    )
    pick = alias.get(pick, pick)
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


def _v_mandate_attack(ctx: ExecCtx, atom: Atom) -> None:
    """MANDATE_ATTACK (16b, CR 508.1 consumer): record every selected
    creature as "attacks each combat if able" on the executor's mandates
    ledger. The STATIC shape (Furor of the Bitten, the Pursued Whale
    Pirate token) registers a selector-bearing "mandate" LAYER through
    :meth:`layers.LayerRegistry._new_static` and is resolved at each
    declare; this handler covers the DISPATCH shape — Pursued Whale's
    ETB trigger carries the compiler-hoisted token rule line as a
    MANDATE_ATTACK atom. Declare-legality CONSUMES both: a mandated
    creature's binary ask narrows to ATTACK-only (C15 honest narrowing —
    the policy is never offered an answer that breaks the rule) and the
    assembled set is whole-set-checked. A ledger entry whose creature
    left the battlefield goes inert (the declare filter re-reads zone +
    controller every combat)."""
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
    ctx: ExecCtx, atom: Atom, kind: str, ledger: set[Handle]
) -> list[Handle]:
    """Record one dispatched MANDATE_ATTACK / MANDATE_BLOCK; returns the
    designated creatures. B-59 (2026-10-29): the atom's ``duration`` role is
    honoured. Without one (or Permanent) the creatures join the dispatch
    ``ledger``, which lasts until each leaves the battlefield. With one
    ("this turn", "until your next turn") the rule ends with its duration
    (CR 611.2a/b, 514.2), so it becomes a ``resolved`` layer record riding
    the registry's expiry points; the ledger used to keep it for good."""
    assert ctx.executor is not None
    cards = role_handles(ctx, atom, "cards")
    duration = atom.args.get("duration")
    assert duration is None or isinstance(duration, Duration)
    if duration is None or isinstance(duration, DurationPermanent):
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
        ctx.executor.layers.register_mandate(
            kind, ctx.source, ctx.controller, tuple(cards), atom, duration
        )
    return cards


def _v_mandate_block(ctx: ExecCtx, atom: Atom) -> None:
    """MANDATE_BLOCK (16c, CR 509.1h "must be blocked if able"): the mirror
    of :func:`_v_mandate_attack` on the declaring-blockers side. Canopy
    Stalker's rule line is the carrier (the STATIC shape registers a
    selector-bearing ``"mandate_block"`` layer through layers._new_static;
    this handler covers the dispatch shape). The block-ask loop CONSUMES
    both: an unassigned mandated attacker narrows a blocker's vocabulary
    onto itself (C15 honest narrowing), and the whole-assignment check re-
    derives the greedy guarantee (doc 14)."""
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


def _v_damage_assign_policy(ctx: ExecCtx, atom: Atom) -> None:
    """DAMAGE_ASSIGN_POLICY (16c): a combat-damage ASSIGNMENT rule keyed to
    its source. The corpus carrier is the granted-ability shape — Garruk,
    Savage Herald's [-7] hands every creature you control a until-EOT
    StaticAbility carrying ``AS_UNBLOCKED`` ("you may have this creature
    assign its combat damage as though it weren't turned in"), which rides
    the layer registry and is read by :meth:`layers.policy_as_unblocked`.
    This handler covers the DISPATCH shape: the scope word is recorded on
    the executor keyed by the ability's source (the damage step consumes
    ledger ∪ layers), so a directly-dispatched policy atom behaves exactly
    like its granted twin. The scope vocabulary is checked, never guessed."""
    if ctx.executor is None:
        raise ValueError(f"executor: {atom.verb.name} needs an executor-backed ExecCtx")
    scope = atom.args.get("scope")
    if scope != "AS_UNBLOCKED":
        raise NotImplementedError(
            f"executor: DAMAGE_ASSIGN_POLICY scope {scope!r} has no consumer "
            "(16c ships AS_UNBLOCKED only — the grammar's closed scope vocab)"
        )
    ctx.executor.damage_policies[ctx.source] = str(scope)
    ctx.events.append((len(ctx.events), atom.verb.name, str(ctx.source), str(scope)))


# ------------------------------------------------------ 16e control verbs


def _v_gain_control(ctx: ExecCtx, atom: Atom) -> None:
    """GAIN_CONTROL (16e, CR 611): write the executor's control overlay —
    the frozen world derives controller_of from the ZONE OWNER and R16-4
    ruled the overlay LIVES HERE, consulted at every controller-semantic
    executor read site. Carriers: Traitorous Greed (DurationEot, TARGET
    selector) and Enthralling Hold (no Duration node — the continuous
    effect of an aura ends when the aura stops existing, so a durationless
    row is anchored to the SOURCE, and CR 704.5q's unattached-aura check
    is what physically ends it). ``UntilLeaves`` pairs its C12 referent
    anchor exactly like :func:`_apply_pt`. The controller slot is the
    STRICT YOU of the corpus (CR 611.2a "you gain control"); any other
    ControllerRef RAISES — flag, never guess. When the effective
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
    tag = duration_tag(duration)
    anchor: Handle | None = ctx.source  # durationless = the aura's continuous effect
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


def _v_attach(ctx: ExecCtx, atom: Atom) -> None:
    """ATTACH (16e, CR 701.4 "Equip {W}" / aura enqueue): move one
    attachment edge on the executor's attachments table — the SAME table
    IS_ATTACHED_TO_SOURCE and the "equipped creature" layer scopes read,
    so an equip re-anchor is a replay-folded op, not a mirror. Both ends
    are validated on the battlefield (the equip activation gate already
    narrowed equipment=source / target="creature you control"; the raise
    is the bare-ctx and hand-driven-op guard). Re-attaching an equipment
    overwrites its edge (one host per attachment, CR 301.5); an aura cast
    attaches through the STACK's aura step, not this verb."""
    if ctx.executor is None:
        raise ValueError(f"executor: {atom.verb.name} needs an executor-backed ExecCtx")
    equipment = role_handles(ctx, atom, "equipment")
    hosts = role_handles(ctx, atom, "target")
    if len(equipment) != 1 or len(hosts) != 1:
        raise ValueError(
            f"executor: ATTACH needs exactly one equipment and one host, got "
            f"{len(equipment)}/{len(hosts)}"
        )
    equipment, host = equipment[0], hosts[0]
    world = ctx.world
    for handle in (equipment, host):
        if handle not in world.cards or world.zone_of(handle).kind != ZONE_BATTLEFIELD:
            raise ValueError(f"executor: ATTACH ends must be battlefields ({handle})")
    ctx.executor.attach_aura(equipment, host)
    ctx.events.append((len(ctx.events), atom.verb.name, str(equipment), str(host)))


def _v_counter_spell(ctx: ExecCtx, atom: Atom) -> None:
    """RUNG-1: counter the designated spell on the stack.

    The designated target is the framed CARD (the window casts the counter
    with ``targets=(frame.handle,)``). The handler flags the victim's
    :class:`~MTG_bot.core.executor.stack.SpellObject`, so the popper in
    :func:`stack.cast` interrupts the resolution (CR 601.4) — the frame's
    effect never runs and the card moves to its owner's graveyard
    (CR 400.7).

    The frozen IR's ``unless`` role (CR 601.2h "unless its controller pays
    <cost>", the Miscast/Lofty Denial shape) is an ASK-TIME decision, not
    a guess: when the victim's controller CAN pay (a plan folds against
    the pool — the 601.2g lane's own arithmetic), the payer is asked
    PAY/PASS through the 14b provider lane (tag ``pay:<seat>:<digest>``,
    C15: never asked when unpayable). PAY runs the plan through
    ``pay_costs`` mid-resolution and the spell LIVES; PASS (or no plan)
    counters. Every unless-site journalled exactly one KICKBACK row —
    ``UNPAYABLE`` is the honest witness when no decision was asked."""
    from MTG_bot.core.executor.legality import (
        build_payment_plan,
        ctx_for,
        pay_costs,
    )

    ex = ctx.executor
    if ex is None:
        raise ValueError("executor: COUNTER_SPELL needs an executor-bound ctx")
    targets = role_handles(ctx, atom, "target")
    if not targets:
        raise ValueError("executor: COUNTER_SPELL with no designated spell")
    spell = targets[0]
    frame = next((f for f in ex.stack.frames if f.handle == spell), None)
    if frame is None:
        raise ValueError(
            f"executor: COUNTER_SPELL target {spell} is not on the stack "
            "(only a framed spell can be countered)"
        )
    if frame.countered:
        raise ValueError(f"executor: COUNTER_SPELL target {spell} already countered")

    unless = atom.args.get("unless")
    if unless is not None:
        assert isinstance(unless, Cost)  # _VERB_ROLES: the unless role is a Cost
        payer = frame.controller
        pctx = ctx_for(ex, source=ctx.source, controller=payer)
        plan, _reason = build_payment_plan(ctx.world, pctx, unless, mana_use=ctx.source)
        answer = "UNPAYABLE"
        if plan is not None:
            digest = site_digest((str(spell), frame.declared_clock))
            answer = ex.decisions.take(("PASS", "PAY"), f"pay:{payer}:{digest}", seat=payer)
            if answer == "PAY":
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

    frame.countered = True
    if ctx.journal is not None:
        ctx.journal.emit(KIND_COUNTER, spell, ctx.source, "COUNTER_SPELL", ())
    _move_to(ctx, spell, ctx.world.controller_of(spell), ZONE_GRAVEYARD)
    ctx.events.append((len(ctx.events), "COUNTER", str(spell), str(ctx.source)))


HANDLERS: dict[Verb, Callable[[ExecCtx, Atom], None]] = {
    Verb.MOVE_ZONE: _v_move_zone,
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
    # engine-supported count.
    Verb.PAY: _v_pay,
    Verb.CAST: _v_cast,
    Verb.CHOOSE: _v_choose,
    Verb.CHOOSE_NAME: _v_choose_name,
    Verb.MANA_POLICY: _v_mana_policy,
    # RUNG-1 (response-window arc): the counter verb, live with the
    # stack.cast response window and its honest unless-kickback ask.
    # SUPPORTED_VERBS_V2 derives from THIS table — 45 -> 46, the library
    # pin is amended dated; the four COUNTER_SPELL cards (Cancel, Miscast,
    # Rewind, Lofty Denial) leave deferral and enter game decks.
    Verb.COUNTER_SPELL: _v_counter_spell,
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
    # 16b: the attack-mandate rule line (CR 508.1 "attacks if able").
    # SUPPORTED_VERBS_V2 derives from THIS table — 40 -> 41, the library
    # pin is amended dated (carriers: Furor of the Bitten, Pursued Whale,
    # the Pirate token).
    Verb.MANDATE_ATTACK: _v_mandate_attack,
    Verb.MANDATE_BLOCK: _v_mandate_block,
    Verb.DAMAGE_ASSIGN_POLICY: _v_damage_assign_policy,
    # 16e: the control/attachment verbs (Traitorous Greed, Enthralling Hold,
    # the Equip carriers). SUPPORTED_VERBS_V2 derives from THIS table —
    # 43 -> 45, the library pin is amended dated.
    Verb.GAIN_CONTROL: _v_gain_control,
    Verb.ATTACH: _v_attach,
    # T5-D (Sanctum of All family): the extra-trigger verb, live with the
    # AbilityTriggerEvent fan-out. SUPPORTED_VERBS_V2 derives from THIS
    # table.
    Verb.TRIGGER_ADDITIONAL: _v_trigger_additional,
}


def run_atom(atom: Atom, ctx: ExecCtx) -> None:
    """Dispatch one Atom to its handler; unsupported verbs RAISE."""
    handler = HANDLERS.get(atom.verb)
    if handler is None:
        raise NotImplementedError(f"executor: verb {atom.verb.name} not implemented")
    # r19b: the look window is ONE sentence wide — a non-look verb runs
    # with the window OPEN (it may consume it: the library-TOP partition
    # idiom) and CLOSES it on completion, so a later Conditional after any
    # other atom keeps the old ctx.source subject and a stale library
    # window can never leak forward. A look verb keeps/refreshes it.
    handler(ctx, atom)
    if atom.verb not in (Verb.LOOK_AT, Verb.REVEAL):
        ctx.look_window = ()
