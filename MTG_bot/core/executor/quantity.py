"""Quantity resolution, the Filter evaluator, and the per-resolution context.

A node this module cannot resolve raises ``NotImplementedError`` naming it:
an unsupported quantity or predicate is flagged, never given a default.

Conventions:
  * ``QAtMost(n)`` resolves to its ceiling ``n``; the callers clamp to the
    0..n handles actually available.
  * QProp referents are the closed structured strings, never English
    substrings.
  * Determinism: every handle list this module produces is Handle-sorted
    unless it is an order-preserving slot (zone order).
"""

from __future__ import annotations

import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final, NamedTuple, Union

if TYPE_CHECKING:  # pragma: no cover - typing-only, dodges runtime cycles
    from MTG_bot.core.executor import Executor
    from MTG_bot.core.executor.events import EventJournal
    from MTG_bot.core.executor.layers import GrantedAbility, LayerRegistry
    from MTG_bot.core.executor.replacements import (
        ReplacementRecord,
        ReplacementRegistry,
    )

from MTG_bot.core.ability_tree import (
    QX,
    ControllerRef,
    CounterKind,
    FAnd,
    FAtom,
    FAtomPred,
    Filter,
    FNot,
    FOr,
    QAtLeast,
    QAtMost,
    QBin,
    QBinOp,
    Rounding,
    QConst,
    QCount,
    QDistinctColorCount,
    QPartyCount,
    QProp,
    QPropField,
    QThisTurn,
    Quantity,
    QUnbounded,
    Selector,
    SelectorMode,
    ThisTurnKind,
    ZonePosition,
)
from MTG_bot.core.executor.decisions import DecisionStream
from MTG_bot.core.executor.durations import DurationLedger
from MTG_bot.core.executor.events import KIND_DECLARE_ATTACKERS, KIND_ZONE_CHANGE, GameEvent
from MTG_bot.core.identity import Handle
from MTG_bot.core.state import (
    ZONE_BATTLEFIELD,
    ZONE_EXILE,
    ZONE_GRAVEYARD,
    ZONE_HAND,
    ZONE_LIBRARY,
    GameWorld,
)

Binding = Union[Handle, list[Handle]]


def _default_rng(tag: str) -> random.Random:  # pragma: no cover - replaced
    """Placeholder factory; the Executor always injects its seeded factory."""
    return random.Random(0)


@dataclass
class ExecCtx:
    """Everything one effect-resolution needs: the world, the executor's
    ledger, the ability's coordinates, and the explicit decision channel.

    ``decisions`` is the explicit per-op pool consumed in ask order via
    :meth:`take_decision`; ``stream`` adds the vocabulary-addressed lanes
    that need no pre-enumeration. Every decision is enumerable and
    explicit: the executor holds no hidden randomness and no hidden choice.
    """

    world: GameWorld
    ledger: DurationLedger
    controller: Handle
    source: Handle
    bindings: dict[str, Binding]
    decisions: Sequence[str]
    decision_idx: int = 0
    # The executor's vocabulary-addressed decision stream. None only in
    # bare unit-test contexts that pass their own decisions pool.
    stream: DecisionStream | None = None
    events: list[tuple[object, ...]] = field(default_factory=list)
    rng: Callable[[str], random.Random] = _default_rng  # executor-owned seeds
    token_counts: dict[str, int] = field(default_factory=dict)
    # The event register: the triggering GameEvent (or None outside trigger
    # context) and the damage or life amount it carried, so QProp("event",
    # AMOUNT) and the event|result referents resolve inside a firing; inside
    # a life-gain replacement's action, the replaced gain's amount.
    event: object = None
    event_amount: int | None = None
    # The counter count a CounterPlacedEvent replacement is rewriting
    # (Conclave Mentor): QProp("event", COUNTER_COUNT) reads it inside a
    # counter replacement's action ("that many plus one"), where the card's
    # accumulated counters are the wrong answer (the event names what is
    # being placed, not what already sits there). None outside the
    # counter-replacement drain, where COUNTER_COUNT sums the card's counters.
    event_counter_count: int | None = None
    # The layer/replacement registries and the owning executor: the layer verbs
    # (GRANT/LOSE_ABILITY, PREVENT_EFFECT) and the damage-replacement
    # interceptor reach them through the ctx; None only in bare unit-test
    # contexts (the handlers raise a clean ValueError if invoked there).
    layers: LayerRegistry | None = None  # executor.layers
    replacements: ReplacementRegistry | None = None  # executor.replacements
    executor: Executor | None = None  # nested replacement effects
    # The executor's structured event journal, bound at every ExecCtx
    # construction site: the effect runtime and the query/legality paths (a
    # predicate the query must answer cannot live off a register the query
    # does not carry). The journal is state: a pure query is a deterministic
    # read, not an amnesiac one. The history preds read the same journalled
    # rows the fingerprint dumps, so replay stays byte-identical. None only
    # in bare unit-test contexts; the history-backed preds then raise naming
    # themselves.
    journal: EventJournal | None = None
    # The cast's declared X (CR 601.2f: chosen with the total cost). None
    # means undeclared, and resolving a QX then raises; cast() binds it from
    # its x parameter, effect-side CASTs default it to 0.
    x_value: int | None = None
    # The ONE_OF picks made in THIS resolution: the partition anchors the
    # sibling REST atom subtracts ("put one of them in your hand, the rest
    # into your graveyard"). The re-search idiom usually makes the
    # subtraction a no-op (the picked card already left the zone); it
    # matters for a same-zone split. Seq order pairs the nearest preceding
    # ONE_OF with its REST. A tuple: a k-of-n partition asks k times and
    # REST subtracts every pick. A REVEAL with ``until`` writes its matches
    # here too ("that card", the rest being the other revealed cards).
    one_of_picks: tuple[Handle, ...] = ()
    # The windowed candidate list a library-TOP ONE_OF partition resolved
    # from (See the Truth), or every card a REVEAL ``until`` revealed: the
    # sibling REST atom's population after run_atom has closed the raw look
    # window. Same lifetime and pairing rule as one_of_picks (Seq order
    # pairs a REST with its nearest preceding partition).
    one_of_window: tuple[Handle, ...] = ()
    # Replacements consume the event and queue their ACTION; the action
    # runs AFTER the consuming atom's journal boundary (one diff per
    # mutation, no double-emitted events). Damage and draw replacements
    # queue bare records (a bindings-less action ctx). A ZONE-CHANGE
    # replacement (Containment Priest) queues ``(record, moving card)`` so
    # the drain can bind the moving card as ``event`` for the action's
    # referent selector. A LIFE-GAIN replacement (Angel of Vitality) queues
    # ``(record, player, amount)``: the drain binds the gaining player as
    # ``event`` and publishes the replaced amount into ``event_amount``, so
    # "that much life plus 1" reads the event. A COUNTER-PLACEMENT
    # replacement (Conclave Mentor) queues ``(record, card, kind, count)``:
    # the drain binds the receiving card as ``event`` AND publishes the
    # placed count into ``event_counter_count`` so the action's "that many
    # plus one" reads the EVENT, not the card's accumulated ledger.
    pending_replacements: list[
        ReplacementRecord
        | tuple[ReplacementRecord, Handle]
        | tuple[ReplacementRecord, Handle, int]
        | tuple[ReplacementRecord, Handle, CounterKind, int]
    ] = field(default_factory=list)
    # The CR 614.4a loop guard (Life Goes On): the seqs of the
    # replacement records that already consumed an event in THIS chain.
    # A replacement's own ACTION runs with the producing record's seq in
    # the set, so the same effect can never re-replace its own replacement
    # (one application per event chain, per event kind).
    replaced_seq: frozenset[int] = frozenset()
    # One source's damage dealt at once is ONE life-gain event, whatever the
    # number of recipients (CR 120.3f; the rulings of Ajani's Pridemate and
    # Angel of Vitality), so a DEAL_DAMAGE atom gains its lifelink damage once,
    # after all its recipients (verbs._v_deal_damage). A combat damage step
    # runs one atom per (dealer, recipient): Executor._damage_wave gives a
    # dealer's earlier atoms ``lifelink_held``, where each leaves what it
    # dealt, and its last atom ``lifelink_carried``, their sum, which that
    # atom's one gain adds.
    lifelink_held: list[int] | None = None
    lifelink_carried: int = 0
    # A Seq that contains ONE_OF/REST partition MOVE_ZONE siblings
    # (Cultivate) searches to DESIGNATE, not to deliver: set by
    # the Seq walker's pre-scan so the SEARCH atom knows its found cards
    # must stay put for the partition atoms to re-find.
    search_partition: bool = False
    # The cards a partition SEARCH found (Cultivate), in the order it found
    # them. The sibling ONE_OF/REST atoms choose among THESE
    # (CR 701.23a: "put one onto the battlefield tapped and the other into
    # your hand" divides the found cards), not among every card in the zone
    # that passes the filter. None when no partition search has run.
    search_found: tuple[Handle, ...] | None = None
    # The cards LOOK_AT/REVEAL showed THIS resolution, top-first (Track
    # Down, See the Truth): the compiler's register convention for the
    # following sentence (templates_b5b._build_if_it_type_then: "Conditional
    # whose subject is the previous sentence's revealed card"). run_atom
    # clears it before every verb that is not a look verb, so it survives
    # exactly one sentence: the Conditional's subject rule and the
    # library-TOP partition selectors ("put ONE OF [the looked-at cards]
    # into your hand") read it, and a bare Conditional after any other atom
    # keeps ctx.source as its subject. Empty (the default) everywhere else.
    look_window: tuple[Handle, ...] = ()
    # Did the last atom run write the ``result`` register?
    # The one-sentence width of "it" for a bare Conditional (run_atom sets
    # it after every atom; transient per resolution, like look_window).
    result_fresh: bool = False
    # MULTI-slot spell designation (Rookie Mistake, Hunter's Edge): the
    # per-TARGET-selector designations keyed by the Selector's ``repr()``
    # (the same identity key ``spell_target_slots`` dedupes on). None for
    # ordinary single-slot spells. _run_effect's Atom branch shadows
    # ``bindings["target"]`` to the atom's own slot while its verbs run
    # (CR 601.2c: one spell, one designation PER SELECTOR; the shared union
    # binding cannot serve two populations).
    slot_designations: dict[str, tuple[Handle, ...]] | None = None
    # the WHOLE designation (every slot's handles, Handle-sorted): what
    # IS_ANY_TARGET anaphora means at resolution — "another target
    # creature" is decided against ALL designations, never the per-atom
    # shadow alone. None = single-slot spell: the binding is read.
    designation_union: tuple[Handle, ...] | None = None
    # Modes declared at CAST time (Return to Nature; CR 601.2b: modes
    # before targets) arrive here as ORDER tokens so the runtime
    # Choose CONSUMES the declaration instead of re-asking for a choice
    # the caster already made. Consumed in ask order; empty elsewhere.
    prechosen_modes: list[str] = field(default_factory=list)
    # Per may-offer site (``may:<source>``) of this resolution, whether the
    # optional action (or a mandatory Seq step, Executor._note_step_done) was
    # carried out (CR 118.12); MAY_DONE reads it. Transient, per resolution,
    # like look_window.
    may_done: dict[str, bool] = field(default_factory=dict)

    def take_decision(self, vocab: tuple[str, ...], what: str) -> str:
        """Consume the next decision for THIS demand site; raise when no
        lane can answer (never a default).

        Lanes, in order (see ``decisions.py``):

        1. the explicit per-op POOL (``decisions=`` kwarg, ask order): a
           KNOWN-tree pre-supply, still vocabulary-validated,
        2. the executor's :class:`~MTG_bot.core.executor.decisions.DecisionStream`
           FIFO primed under this exact ``(vocab, what)`` key, the
           enumeration-free lane: an answer queued by the policy is picked
           up whenever the demand arrives, including from a trigger the
           running op itself armed,
        3. the stream's ask-time PROVIDER: the engine hands the exact
           vocabulary to the external answerer at the moment of demand.

        The provider sees this context's controller as the deciding player
        (``DecisionStream.asking_seat``); a site whose decider is another
        player asks through :meth:`take_decision_of`. The scry site relies on
        its controller being the scrying player, and the bench router's tag
        check raises loudly if a card ever breaks that.
        """
        if self.decision_idx < len(self.decisions):
            choice = self.decisions[self.decision_idx]
            if choice in vocab:
                self.decision_idx += 1
                if self.stream is not None:
                    self.stream.ask_log.append((what, choice))
                    self.stream.journal.append((what, choice))
                return choice
            # The next pool word does not answer THIS site (a may-offer
            # cannot eat a card name, a candidate-index ask cannot eat a
            # pack key). A mismatched word is NOT consumed: it stays in the
            # pool for the site it was scripted for, and THIS site falls
            # through to the stream / provider lanes, which answer from the
            # vocabulary itself. When no stream lane can answer, the raise
            # names the mismatched word (pinned by
            # ``test_mismatched_word_is_never_consumed``).
            if self.stream is not None:
                try:
                    return self.stream.take(vocab, what, seat=self.controller)
                except ValueError:
                    pass
            raise ValueError(f"executor: {what} decision {choice!r} not in {vocab}")
        if self.stream is not None:
            return self.stream.take(vocab, what, seat=self.controller)
        raise ValueError(
            f"executor: {what} needs a decision from {vocab}, "
            f"got only {len(self.decisions)} supplied"
        )

    def take_decision_of(self, player: Handle, vocab: tuple[str, ...], what: str) -> str:
        """:meth:`take_decision`, asked of ``player``: the player the rules say makes this choice
        when it is not this context's controller (CR 701.9b: the discarding player picks the
        cards; CR 701.21a with 101.4: a player sacrifices only what they control, so they pick).

        For the length of the ask the context's controller IS that player. ``take_decision`` then
        names them as the stream's ``asking_seat``. Nothing else runs while it is swapped."""
        if player == self.controller:
            return self.take_decision(vocab, what)
        outer = self.controller
        self.controller = player
        try:
            return self.take_decision(vocab, what)
        finally:
            self.controller = outer

    def binding_handles(self, role: str) -> list[Handle] | None:
        """The caller-supplied handles for a role, Handle-sorted."""
        value = self.bindings.get(role)
        if value is None:
            return None
        handles = [value] if isinstance(value, Handle) else list(value)
        return sorted(handles)

    def binding_one(self, role: str) -> Handle | None:
        handles = self.binding_handles(role)
        return handles[0] if handles else None

    def effective_pt(self, card: Handle) -> tuple[int | None, int | None]:
        card_state = self.world.cards[card]
        return self.ledger.effective_pt(card_state.identity, card, card_state.counters)


def phased_out(ctx: ExecCtx, handle: Handle) -> bool:
    """CR 702.26b: is ``handle`` a phased-out permanent, treated as though
    it does not exist? The status lives on the executor; a bare ExecCtx (no
    executor) has no phasing."""
    executor = ctx.executor
    return executor is not None and handle in executor.phased_out


def resolve(quantity: Quantity, ctx: ExecCtx) -> int:
    """Quantity IR -> a non-negative int.

    Raises ``NotImplementedError`` for a node it cannot resolve (an
    undeclared X, an unsupported QThisTurn kind, an event-field QProp
    outside a firing), never a silent default.
    """
    if isinstance(quantity, QConst):
        return quantity.value
    if isinstance(quantity, (QAtMost, QAtLeast)):
        # n: QAtMost reports its ceiling (callers clamp to what is actually
        # available, 0..n, before acting), QAtLeast its floor.
        return quantity.n
    if isinstance(quantity, QBin):
        left = resolve(quantity.left, ctx)
        right = resolve(quantity.right, ctx)
        if quantity.op is QBinOp.ADD:
            return left + right
        if quantity.op is QBinOp.SUB:
            return max(0, left - right)
        if quantity.op is QBinOp.MUL:
            return left * right
        if quantity.op is QBinOp.DIV:
            if right == 0:
                raise ValueError("executor: QBin DIV by zero")
            if quantity.rounding is Rounding.CEIL:
                # Ceiling division (Peer into the Abyss "Round up each
                # time.", CR 107.1a); every other rounding floors.
                return -(-left // right)
            return left // right
        if quantity.op is QBinOp.MAX:
            return max(left, right)
        if quantity.op is QBinOp.MIN:
            return min(left, right)
        raise NotImplementedError(f"executor: QBin op {quantity.op.name}")
    if isinstance(quantity, QCount):
        deaths = _died_this_turn_census(quantity.selector, ctx)
        if deaths is not None:
            return deaths
        return len(read_population(quantity.selector, ctx))
    if isinstance(quantity, QDistinctColorCount):
        from MTG_bot.core.executor.selectors import resolve_selector

        colors: set[str] = set()
        for handle in resolve_selector(quantity.selector, ctx):
            if handle.namespace == "card":
                colors.update(ctx.world.cards[handle].identity.colors)
        return len(colors)
    if isinstance(quantity, QPartyCount):
        from MTG_bot.core.executor.selectors import (
            resolve_selector,
        )  # cycle-free at call time

        # Party size = the number of DISTINCT party classes (PARTY_CLASSES)
        # PRESENT among the selector's objects, at most one per class: two
        # Clerics + one Wizard = 2, never 3. The class test reads the LIVE
        # type oracle (printed type line ∪ GRANT_TYPE overlay, the same
        # oracle the SUBTYPE_EQ lane uses below), so class grants move the
        # census. A subset of the fixed 4-set caps the size at 0..4.
        classes: set[str] = set()
        for handle in resolve_selector(quantity.selector, ctx):
            if handle.namespace != "card" or handle not in ctx.world.cards:
                continue
            words = set(_type_line_tokens(ctx.world.cards[handle].identity.type_line))
            if ctx.layers is not None:
                words.update(ctx.layers.type_overlay(handle))
            classes.update(words & PARTY_CLASSES)
        return len(classes)
    if isinstance(quantity, QProp):
        return _resolve_prop(quantity, ctx)
    if isinstance(quantity, QX):
        # X as declared by cast(x=...) via ExecCtx.x_value (CR 601.2f). An
        # undeclared X raises, never a guess.
        if ctx.x_value is None:
            raise NotImplementedError(
                "executor: QX has no declared X (cast(x=...) binds it; "
                "12c cost-context flag)"
            )
        return ctx.x_value
    if isinstance(quantity, QUnbounded):
        raise NotImplementedError(
            "executor: QUnbounded not resolvable to a number (12c choice surface)"
        )
    if isinstance(quantity, QThisTurn):
        # Only NONCOMBAT_DAMAGE is read: Chandra's Incinerator's cost reducer
        # ("where X is the total amount of noncombat damage dealt to your
        # opponents this turn", QThisTurn(NONCOMBAT_DAMAGE, ALL_OPPONENTS)).
        # It sums the turn window's noncombat DAMAGE rows (data ``(amount,)``,
        # or ``(amount, True)`` for combat damage) whose SUBJECT is a seat of
        # the referent side. A planeswalker-recipient row never counts:
        # "damage dealt to your opponents" names the PLAYER receiving it
        # (CR 118.5: damage to a planeswalker is not damage to that player),
        # and the row's subject is the actual recipient. The window is the
        # journal's ``turn_window()``, so the legality lane reads the same
        # rows the effect lane does.
        if quantity.kind is not ThisTurnKind.NONCOMBAT_DAMAGE:
            raise NotImplementedError(
                f"executor: QThisTurn({quantity.kind.name}) not implemented "
                "(12b turn ledger)"
            )
        from MTG_bot.core.executor.events import KIND_DAMAGE
        from MTG_bot.core.executor.selectors import players_for_ref

        if ctx.journal is None:
            raise NotImplementedError(
                "executor: QThisTurn(NONCOMBAT_DAMAGE) reads the journalled "
                "damage feed (this ExecCtx has no journal)"
            )
        receivers = set(players_for_ref(quantity.referent, ctx))
        return sum(
            row.amount
            for row in ctx.journal.turn_window()
            if row.kind == KIND_DAMAGE
            and not row.is_combat
            and row.subject in receivers
        )
    raise NotImplementedError(
        f"executor: quantity {type(quantity).__name__} not implemented"
    )


def referent_handle(referent: str, ctx: ExecCtx) -> Handle:
    """Public alias of the closed referent resolver: the verbs resolve a
    DurationUntilLeaves anchor through the SAME machinery the QProps use
    (one referent semantics, no second parser)."""
    return _referent_handle(referent, ctx)


def _referent_handle(referent: str, ctx: ExecCtx) -> Handle:
    if referent == "source":
        return ctx.source
    if referent == "controller":
        return ctx.controller
    if referent == "target":
        target = ctx.binding_one("target")
        if target is None:
            raise ValueError("executor: QProp 'target' referent has no target binding")
        return target
    # The trigger firing bound the event subject / result subject.
    if referent in ("event", "result"):
        if referent == "event" and len(ctx.binding_handles("event") or ()) > 1:
            # A gathered event (ability_tree.gathers_objects) names several objects, and none
            # of them is "it"; the IR refuses the reads it can see, this is the net for the rest.
            raise NotImplementedError(
                "executor: the event register holds several objects (a gathered event): "
                "a read of one of them has none to read"
            )
        bound = ctx.binding_one(referent)
        if bound is None:
            raise NotImplementedError(
                f"executor: QProp referent {referent!r} only resolves inside a "
                "trigger firing (no event register on this call)"
            )
        return bound
    raise NotImplementedError(
        f"executor: QProp referent {referent!r} is not in the closed C12 vocabulary"
    )


class LastKnown(NamedTuple):
    """An object's last known information as it left the battlefield (CR 608.2h), captured
    once, before its counters ceased (CR 122.2), its continuous effects ended (CR 400.7) and
    its control entries expired: what anything that needs the object as it last existed reads
    (Executor.departed_lki). ``op`` is the public op in which it left; ``attacking`` the player
    or planeswalker it was attacking then, None if it was not attacking (it leaves combat as it
    leaves the battlefield, CR 506.4); ``choices`` what it chose as it entered, as (quality,
    value) pairs (Executor.name_choices; quality None for a card name); ``types`` the type words
    an effect gave it (the layers' type overlay); ``granted`` the abilities an effect granted it
    (a granted "When this creature dies" looks back at its death, CR 603.10a)."""

    power: int | None
    toughness: int | None
    counters: dict[str, int]
    keywords: tuple[str, ...]
    controller: Handle
    op: int
    attacking: Handle | None = None
    choices: tuple[tuple[str | None, str], ...] = ()
    types: tuple[str, ...] = ()
    granted: tuple[GrantedAbility, ...] = ()


def departed_lki(handle: Handle, ctx: ExecCtx) -> LastKnown | None:
    """CR 603.10a: a leaves-the-battlefield trigger "looks back in time". When the
    firing event is the departure of ``handle`` from the battlefield (its dies row
    or zone change) and the object is gone, its last known information answers for
    it (Executor.departed_lki). A gathered zone change (CR 603.2c) is the departure of
    each object it gathered, each in its own row. Otherwise None: the caller reads the
    live object (a query's context, which carries the bindings but no event, included)."""
    found = departure_lki(handle, ctx.event, ctx.executor)
    ex, event = ctx.executor, ctx.event
    if (
        found is None
        and ex is not None
        and isinstance(event, GameEvent)
        and event.kind == KIND_ZONE_CHANGE
        and handle in (ctx.binding_handles("gathered") or ())
    ):
        row = next((e for e in ex.binder._occurrences(event) if e.subject == handle), None)
        found = departure_lki(handle, row, ex)
    return found


def departure_lki(handle: Handle, event: object, ex: Executor | None) -> LastKnown | None:
    """:func:`departed_lki` for a caller that holds the event but no context (the binder
    choosing the controller of the departed object's own trigger, CR 603.3a)."""
    if event is None or ex is None or getattr(event, "subject", None) != handle:
        return None
    kind = getattr(event, "kind", None)
    from MTG_bot.core.executor.events import KIND_CREATURE_DIES, KIND_ZONE_CHANGE

    if kind == KIND_ZONE_CHANGE:
        if event.zone_move[0] != ZONE_BATTLEFIELD:  # a GameEvent: its kind says so
            return None
    elif kind != KIND_CREATURE_DIES:
        return None
    if handle in ex.world.cards and ex.world.zone_of(handle).kind == ZONE_BATTLEFIELD:
        return None
    return ex.departed_lki.get(handle)


def last_known(handle: Handle, ctx: ExecCtx) -> LastKnown | None:
    """The last known information an effect uses for an object that has left the battlefield
    (CR 608.2h: "if it's no longer in the zone it was expected to be in ... the object's last
    known information"; CR 113.7a for the ability's own source): on the object's own departure
    event (:func:`departed_lki`); for the ability's source (Heartfire Immolator's "damage equal
    to its power" after it was sacrificed); for an object that left during the current op
    (Angelic Ascension's "its controller" after the exile); and for an object the trigger's
    event named that has become a new object since (the ``gone`` register,
    ``TriggerBinder._gone``: Terror of the Peaks' "that creature's power" once that creature
    has left). None otherwise: a card that has been sitting in a graveyard is read as it is
    now (its owner controls nothing, CR 108.4a; its printed power, CR 400.7)."""
    found = departed_lki(handle, ctx)
    if found is not None:
        return found
    ex = ctx.executor
    if ex is None or handle.namespace != "card":
        return None
    snap = ex.departed_lki.get(handle)
    if snap is None:
        return None
    if handle in ctx.world.cards and ctx.world.zone_of(handle).kind == ZONE_BATTLEFIELD:
        return None
    if handle == ctx.source or snap.op == ex._op_seq or handle in (ctx.binding_handles("gone") or ()):
        return snap
    return None


def _prop_value(field: QPropField, handle: Handle, ctx: ExecCtx) -> int:
    lki = last_known(handle, ctx) if handle.namespace == "card" else None
    if lki is not None and field in (QPropField.POWER, QPropField.TOUGHNESS):
        value = lki.power if field is QPropField.POWER else lki.toughness
        if value is None:
            raise ValueError(f"executor: {field.name} undefined on handle {handle}")
        return value
    if lki is not None and field is QPropField.COUNTER_COUNT and ctx.event_counter_count is None:
        return sum(lki.counters.values())
    if field in (QPropField.POWER, QPropField.TOUGHNESS):
        power, toughness = ctx.effective_pt(handle)
        value = power if field is QPropField.POWER else toughness
        if value is None:
            raise ValueError(f"executor: {field.name} undefined on handle {handle}")
        return value
    if field in (QPropField.CMC, QPropField.MANA_VALUE):
        if handle.namespace != "card":
            raise ValueError(f"executor: {field.name} needs a card handle")
        return ctx.world.cards[handle].identity.cmc or 0
    if field in (
        QPropField.CARDS_IN_HAND,
        QPropField.CARDS_IN_LIBRARY,
        QPropField.CARDS_IN_GRAVEYARD,
    ):
        kind = {
            QPropField.CARDS_IN_HAND: ZONE_HAND,
            QPropField.CARDS_IN_LIBRARY: ZONE_LIBRARY,
            QPropField.CARDS_IN_GRAVEYARD: ZONE_GRAVEYARD,
        }[field]
        return len(ctx.world.players[handle].zone(kind).entries)
    if field is QPropField.LIFE:
        # The life TOTAL ("loses half their life. Round up", Peer into the
        # Abyss): no zone to count, so QCount cannot carry it. Same
        # convention as the CARDS_IN_* fields above (referent "controller",
        # validated in QProp.__post_init__), a direct order-free attribute
        # read. Pinned end-to-end in test_executor_r24a.
        return ctx.world.players[handle].life
    if field is QPropField.COUNTER_COUNT:
        # Inside a counter placement's replacement action (Conclave Mentor),
        # "that many" names the count the EVENT is placing (the drain
        # publishes it), not the card's whole counter sum. Outside the
        # replacement drain the register is None and the card's counters
        # are summed.
        if ctx.event_counter_count is not None:
            return ctx.event_counter_count
        return sum(ctx.world.cards[handle].counters.values())
    raise NotImplementedError(
        f"executor: QProp field {field.name} not implemented (12c query surface)"
    )


#: The QProp fields that read a register of the resolution, not an object (QProp validates them to
#: the "event" referent): "that much" (AMOUNT), "this way" and "that many". No object is looked up
#: for them, so a gathered event whose objects have all left since still has its count (Woodland
#: Champion's and Basri Ket's rulings: those that left are counted).
_REGISTER_FIELDS = frozenset(
    {QPropField.AMOUNT, QPropField.THIS_WAY_COUNT, QPropField.THAT_MANY_COUNT}
)


def _register_value(field: QPropField, ctx: ExecCtx) -> int:
    if field is QPropField.AMOUNT:
        # The triggering event's damage or life amount (Brash Taunter, Light of
        # Promise), or the replaced gain's (Angel of Vitality).
        if ctx.event_amount is None:
            raise NotImplementedError(
                "executor: QProp AMOUNT needs a damage or life event (a trigger "
                "firing, or a life-gain replacement's action)"
            )
        return ctx.event_amount
    if field is QPropField.THIS_WAY_COUNT:
        # Siege Striker's attack trigger ("+1/+1 for each creature tapped
        # this way"): the count of creatures the SAME effect execution's
        # last TAP atom tapped, a per-resolution register (fresh bindings
        # dict per effect run), so an Optional-wrapped tap that DECLINED
        # leaves the register absent and the magnitude 0. (No object is read:
        # "this way" counts an action, not a permanent's property.)
        reg = ctx.bindings.get("tapped_this_way")
        return len(reg) if isinstance(reg, (list, tuple)) else 0
    if field is QPropField.THAT_MANY_COUNT:
        # "then do that many": the count of objects the PRECEDING producer
        # atom acted on in THIS resolution, from the ``result`` register
        # (TAP/UNTAP/PUT_COUNTER/MOVE_ZONE/SEARCH/CHOOSE/DISCARD write it;
        # Kinetic Augur's "discard …, then draw that many"). As for
        # THIS_WAY_COUNT, no object is read. An UNSET register RAISES, where
        # THIS_WAY's absence is the benign 0 (a declined may legitimately
        # leaves it unwritten): the compiler only places "that many" in a
        # mandatory continuation, so a missing antecedent is flagged, never
        # guessed.
        handles = ctx.binding_handles("result")
        if handles is None:
            # The trigger-antecedent reading (Basri Ket's -2, Woodland
            # Champion). When the "that many" rides the effect of a trigger
            # that gathers objects (ability_tree.gathers_objects) there IS no
            # preceding producer atom: the event's objects are the antecedent
            # set, every one it gathered, those that have left since included
            # (the cards' rulings), which the binder's _put records under this
            # register. The ``result`` register keeps strict precedence
            # (Kinetic Augur stays on the producer path); this fallback only
            # answers when it is absent, and a single event never writes it.
            handles = ctx.binding_handles("gathered")
        if handles is None:
            raise NotImplementedError(
                "executor: THAT_MANY_COUNT has no producer register — no "
                "preceding atom wrote the result register in this resolution"
            )
        return len(handles)
    raise NotImplementedError(f"executor: QProp field {field.name} reads no register")


def read_population(sel: Selector, ctx: ExecCtx) -> list[Handle]:
    """The objects a read of ``sel`` (a count, "the greatest power among them") is about: those
    it resolves to, read for their information (CR 608.2h). The event referent's are every
    object the event named (a gathered event's every object it gathered), those the effect no
    longer acts on included (TriggerBinder._gone), each read by its last known information
    once it left."""
    from MTG_bot.core.executor.selectors import resolve_selector  # cycle-free at call time

    return resolve_selector(sel, ctx, info=True)


def _resolve_prop(prop: QProp, ctx: ExecCtx) -> int:
    if isinstance(prop.referent, str):
        if prop.field in _REGISTER_FIELDS:
            return _register_value(prop.field, ctx)
        return _prop_value(prop.field, _referent_handle(prop.referent, ctx), ctx)
    # An AGGREGATION over a selector skips objects whose power/toughness is
    # undefined (Carrion Grub: "X is the greatest power among creature cards
    # in your graveyard", with a Kinetic Augur there, whose "*/4" CDA the
    # engine does not model). An object with no power is not one of the
    # "powers among" being maxed/summed: the same characteristic-absent rule
    # that makes the POWER_LE/POWER_GE filters read False for it. The scalar
    # read of an undefined property stays the strict ValueError in
    # _prop_value (never a zero). An all-undefined population falls to the
    # empty-set 0 below.
    aggregate_pt = prop.field in (QPropField.POWER, QPropField.TOUGHNESS)
    referent = prop.referent.referent
    values = []
    for handle in read_population(prop.referent, ctx):
        if aggregate_pt:
            # Objects a referent names are read as "its power" is (_prop_value): through their
            # last known information once they left. A zone's population (Carrion Grub's
            # graveyard) is read as it is now (CR 400.7).
            lki = None
            if referent is not None and handle.namespace == "card":
                lki = last_known(handle, ctx)
            power, toughness = (
                (lki.power, lki.toughness) if lki is not None else ctx.effective_pt(handle)
            )
            value = power if prop.field is QPropField.POWER else toughness
            if value is None:
                continue
            values.append(value)
        else:
            values.append(_prop_value(prop.field, handle, ctx))
    if not values:
        return 0
    if prop.agg.name == "FIRST":
        return values[0]
    if prop.agg.name == "SUM":
        return sum(values)
    if prop.agg.name == "MAX":
        return max(values)
    if prop.agg.name == "MIN":
        return min(values)
    raise NotImplementedError(f"executor: QAgg {prop.agg.name}")


# --------------------------------------------------------------------- filters

_TYPE_LINE_SEPARATORS = ("//", "/", ",")

# The four party classes, as MTG_bot/data/ZNR.json prints on every party
# card: "Your party consists of up to one each of Cleric, Rogue, Warrior,
# and Wizard." Party size = |present ∩ this set| ∈ 0..4, one per class.
PARTY_CLASSES: Final[frozenset[str]] = frozenset(
    {"Cleric", "Rogue", "Warrior", "Wizard"}
)


# The CR 110.1 permanent card types (IS_PERMANENT): a card whose type
# line names one of these is a permanent card wherever it currently sits
# (library, stack, graveyard, exile included).
_PERMANENT_TYPE_WORDS = frozenset(
    {"Artifact", "Creature", "Enchantment", "Land", "Planeswalker", "Battle"}
)


def _type_line_tokens(identity_text: str) -> list[str]:
    """Split a printed type line into its words (supertypes, types and
    subtypes), also splitting on "//", "/" and ",". Data only: no oracle
    text is parsed."""
    text = identity_text
    for sep in _TYPE_LINE_SEPARATORS:
        text = text.replace(sep, " ")
    return [t for t in text.split() if t]


def _type_words(handle: Handle, ctx: ExecCtx) -> set[str]:
    """A card's type words: its printed type line and those an effect gives it, the layers'
    overlay ("is a Knight in addition to its other types"). Judged on its own departure, the
    ones it had as it left (CR 603.10a: its last known information)."""
    words = set(_type_line_tokens(ctx.world.cards[handle].identity.type_line))
    lki = departed_lki(handle, ctx)
    if lki is not None:
        words.update(lki.types)
    elif ctx.layers is not None:
        words.update(ctx.layers.type_overlay(handle))
    return words


#: The subtypes of the card types a creature face can share its type line with: artifact,
#: enchantment and land types (CR 205.3g-i, the rules of 2026-11-06).
_OTHER_SUBTYPES = {
    "Artifact": frozenset({
        "Attraction", "Blood", "Bobblehead", "Book", "Clue", "Communicator", "Contraption",
        "Equipment", "Food", "Fortification", "Gold", "Heartwood", "Incubator", "Infinity", "Junk",
        "Lander", "Map", "Mutagen", "Powerstone", "Spacecraft", "Stone", "Treasure", "Vehicle",
        "Vibranium"}),
    "Enchantment": frozenset({
        "Aura", "Background", "Cartouche", "Case", "Class", "Curse", "Plan", "Role", "Room", "Rune",
        "Saga", "Shard", "Shrine"}),
    "Land": frozenset({
        "Cave", "Desert", "Forest", "Gate", "Island", "Lair", "Locus", "Mine", "Mountain", "Plains",
        "Planet", "Power-Plant", "Sphere", "Swamp", "Tower", "Town", "Urza's"}),
}


#: The card types and supertypes (CR 205.2a, 205.4a): the words of a type line that are no subtype.
_TYPE_LINE_KINDS = frozenset({
    "Artifact", "Battle", "Conspiracy", "Creature", "Dungeon", "Enchantment", "Instant", "Kindred",
    "Land", "Phenomenon", "Plane", "Planeswalker", "Scheme", "Sorcery", "Tribal", "Vanguard",
    "Basic", "Legendary", "Ongoing", "Snow", "World"})


def creature_types(type_line: str) -> list[str]:
    """The creature types a printed type line gives: the subtypes of each face that is a creature
    or kindred card, less those of its other card types (CR 205.3d: each subtype is one of its
    own card types'; 205.3m). ELD Gingerbrute, "Artifact Creature — Food Golem", is a Golem."""
    out: list[str] = []
    for face in type_line.split("//"):
        types, _, subtypes = face.partition("—")
        kinds = set(types.split())
        if {"Creature", "Kindred", "Tribal"} & kinds:
            other = frozenset().union(*(_OTHER_SUBTYPES.get(kind, ()) for kind in kinds))
            out.extend(s for s in subtypes.split() if s not in other)
    return out


def granted_creature_types(words: tuple[str, ...]) -> list[str]:
    """The creature types among a GRANT_TYPE's words (M21 Riddleform's "3/3 Sphinx creature",
    Dub's "is a Knight"): every word that is no card type or supertype and no artifact,
    enchantment or land type (CR 205.3g-i)."""
    other = frozenset().union(*_OTHER_SUBTYPES.values())
    return [w for w in words if w not in _TYPE_LINE_KINDS and w not in other]


def eval_filter(filter_: Filter, handle: Handle, ctx: ExecCtx) -> bool:
    """Match one handle against a Filter IR node.

    The JOURNAL-BACKED history preds (MOVED_TO_ZONE_THIS_TURN, DIED_THIS_TURN,
    ...) answer from the executor's journalled rows at EVERY eval entry point
    (runtime, legality, query, layer, trigger gate), because the journal is
    state: a pure query stays a deterministic read. A predicate without a
    branch here raises ``NotImplementedError`` naming itself: an unsupported
    pred is flagged, never guessed.
    """
    if isinstance(filter_, FAnd):
        return all(eval_filter(c, handle, ctx) for c in filter_.children)
    if isinstance(filter_, FOr):
        return any(eval_filter(c, handle, ctx) for c in filter_.children)
    if isinstance(filter_, FNot):
        return not eval_filter(filter_.inner, handle, ctx)
    if isinstance(filter_, FAtom):
        return _eval_atom(filter_, handle, ctx)
    raise NotImplementedError(
        f"executor: filter node {type(filter_).__name__} not implemented"
    )


def _eval_atom(atom: FAtom, handle: Handle, ctx: ExecCtx) -> bool:
    pred = atom.pred
    world = ctx.world
    if pred is FAtomPred.IS_SOURCE:
        return handle == ctx.source
    if pred is FAtomPred.IS_ANY_TARGET:
        # The object is one of the ability's designated targets (Frost
        # Breath, Selfless Savior anaphora), judged against the call's
        # target bindings. On a MULTI-slot spell the per-atom "target"
        # shadow (ExecCtx.slot_designations) would shrink "any target" to
        # one slot; the spell-wide union is the designation and means ANY
        # of them.
        if ctx.designation_union is not None:
            return handle in ctx.designation_union
        bound = ctx.binding_handles("target")
        return bound is not None and handle in bound
    if pred is FAtomPred.IS_RESULT:
        # The object is one the previous instruction acted on, the ``result``
        # register ("they" after "each creature target opponent controls phases
        # out", Teferi, Timeless Voyager's [-8]). A read with nothing written is
        # a missing antecedent: flagged, never an empty set (selectors' referent
        # lane raises the same way).
        bound = ctx.binding_handles("result")
        if bound is None:
            raise NotImplementedError(
                "executor: filter pred IS_RESULT reads the result register, and no "
                "instruction before it wrote one"
            )
        return handle in bound
    if pred is FAtomPred.TARGETS_SOURCE:
        # Pursued Whale (CR 601.2f cost fold): "Spells your opponents cast
        # that target this creature cost {3} more to cast." The filter asks
        # whether the JUDGED object (the casting spell in the fold's
        # coordinates: legality.py builds mod_ctx with source=the modifier's
        # host and copies the cast ctx's target bindings) designated the
        # filter's SOURCE (the static's host) among its targets. Before the
        # target declaration there is no designation at all, so the
        # pre-target cost enumeration reads False and the printed cost
        # shows; the +3 lands at PAYMENT, where stack.cast has already
        # journaled bindings["target"] (the fold re-runs there). The mirror
        # of IS_ANY_TARGET: that pred asks "object ∈ my targets", this asks
        # "source ∈ judge's targets", judged in the host's coordinates.
        if ctx.designation_union is not None:
            return ctx.source in ctx.designation_union
        bound = ctx.binding_handles("target")
        return bound is not None and ctx.source in bound
    if handle.namespace == "ability":
        # An ability on the stack (stack.StackObject) is no card and has no
        # characteristics (CR 113.7a): only its kind tells it apart.
        if pred is not FAtomPred.STACK_KIND_EQ or ctx.executor is None:
            return False
        frame = next((f for f in ctx.executor.stack.frames if f.handle == handle), None)
        return frame is not None and frame.spell_kind == atom.string_value
    if pred is FAtomPred.IS_TAPPED:
        return world.cards[handle].tapped
    if pred is FAtomPred.IS_UNTAPPED:
        return not world.cards[handle].tapped
    if pred is FAtomPred.IS_PERMANENT:
        # CR 110.1: a permanent card is a CARD THAT HAS A PERMANENT CARD
        # TYPE, not "a card sitting on the battlefield". Gates asked OFF the
        # battlefield answer about the card: Fungal Rebirth's graveyard test
        # ("creature card in a graveyard") and Unsubstantiate's
        # spell-on-the-stack target. The type-line test is zone-independent;
        # on the battlefield it agrees with the zone reading.
        if handle not in world.cards:
            return False
        words = set(_type_line_tokens(world.cards[handle].identity.type_line))
        return bool(words & _PERMANENT_TYPE_WORDS)
    if pred is FAtomPred.IS_TOKEN:
        # "nontoken creature that died": printed token-ness (identity data,
        # so it survives death).
        return world.cards[handle].identity.is_token
    if pred in (FAtomPred.TYPE_EQ, FAtomPred.SUBTYPE_EQ, FAtomPred.SUPERTYPE_EQ):
        # Supertypes share the type-word match: the identity has no
        # ``supertypes`` field, but every supertype ("Basic", "Legendary",
        # "Snow") is PRINTED in the type line, so the data-only word test is
        # the honest reading (no oracle text is parsed). Live GRANT_TYPE
        # layers UNION their overlay words in ("is a Knight in addition to
        # its other types"): the layer registry is the single type oracle.
        assert atom.string_value is not None
        if handle not in world.cards:
            return False
        return atom.string_value in _type_words(handle, ctx)
    if pred is FAtomPred.NAME_CONTAINS:
        # Teferi's "a Teferi planeswalker" gate: case-sensitive substring on
        # the printed name, the grammar's NAME_EQ twin. The corpus gate word
        # ("Teferi") is a proper noun matching the printed capitalization;
        # NAME_CHOSEN's unanswered-question convention does not apply (this
        # is pure identity data, no question to answer).
        assert atom.string_value is not None
        if handle not in world.cards:
            return False
        return atom.string_value in world.cards[handle].identity.name
    if pred is FAtomPred.IS_ATTACHED_TO_SOURCE:
        # Malefic Scythe's "equipped creature", Dub's compiled aura shape:
        # the world has NO attachment state (CardState has no aura/equipment
        # fields), so the answer is the EXECUTOR's attachment table, an
        # AURA/EQUIPMENT -> HOST map maintained by ``executor.attach_aura``
        # and dropped on zone change. A bare ExecCtx has no table: flagged,
        # never guessed.
        if ctx.executor is None:
            raise ValueError(
                "executor: IS_ATTACHED_TO_SOURCE needs an executor-backed "
                "ExecCtx (bare ExecCtx has no attachment table)"
            )
        if ctx.executor.attachments.get(ctx.source) == handle:
            return True
        # A dies-trigger's filter (Malefic Scythe) is judged after the
        # binder's leave-detach has pruned the live table (the ZONE_CHANGE
        # row lands before the CREATURE_DIES row of the same diff sweep).
        # Once the judged object has LEFT the battlefield, the live table
        # can no longer speak for it: the object's own departure-time
        # snapshot (executor.detach_lki) is its last known information
        # (CR 400.7). On the battlefield the live table is the only word.
        if handle in world.cards and world.zone_of(handle).kind == ZONE_BATTLEFIELD:
            return False
        return ctx.source in ctx.executor.detach_lki.get(handle, ())
    if pred is FAtomPred.IS_ATTACHED_TO:
        # "attached to the REFERENT object" (Turn to Slag): the same
        # attachment-table answer as IS_ATTACHED_TO_SOURCE, but the host
        # arrives through the closed _QPROP_STR_REFERENTS anaphora instead
        # of the source. Here the JUDGED object is the attachment, so the
        # lookup is ``table[the object] == host``: the attachment is the
        # KEY and the host the VALUE, as attach_aura writes the table
        # (attachments[aura] = host). IS_ATTACHED_TO_SOURCE asks
        # ``table[source] == handle`` because there the SOURCE is the
        # attachment. The referent resolves like resolve_selector's referent
        # lane: source and controller are coordinates, "target" is the one
        # designation (CR 601.2c), anything else is a binding under that
        # name. A missing/ambiguous referent and a bare ExecCtx raise, never
        # a guess.
        if ctx.executor is None:
            raise ValueError(
                "executor: IS_ATTACHED_TO needs an executor-backed "
                "ExecCtx (bare ExecCtx has no attachment table)"
            )
        referent = atom.referent
        if referent == "source":
            host = ctx.source
        elif referent == "controller":
            host = ctx.controller
        elif referent == "target":
            bound = ctx.binding_handles("target")
            if bound is None or len(bound) != 1:
                raise ValueError(
                    "executor: IS_ATTACHED_TO referent 'target' needs "
                    f"exactly one designation, got {bound!r}"
                )
            host = bound[0]
        else:
            bound = ctx.binding_handles(referent or "")
            if bound is None or len(bound) != 1:
                raise ValueError(
                    f"executor: IS_ATTACHED_TO referent {referent!r} has "
                    "no single binding"
                )
            host = bound[0]
        return ctx.executor.attachments.get(handle) == host
    if pred is FAtomPred.NAME_EQ:
        assert atom.string_value is not None
        return world.cards[handle].identity.name == atom.string_value
    if pred in (FAtomPred.COLOR_IN, FAtomPred.COLOR_HAS):
        # COLOR_IN is the grammar's SUBSET reading ("colours are a non-empty
        # subset of the given set"), COLOR_HAS the single-colour membership
        # ("hexproof from black"; a spell "that's white or blue" is the FOr
        # of COLOR_HAS, CR 105.2). Identity data: works for a card in any
        # zone, incl. the stack (the cast-trigger feed reads spells).
        if handle.namespace != "card":
            return False
        card_colors = set(world.cards[handle].identity.colors)
        if pred is FAtomPred.COLOR_HAS:
            assert atom.color is not None
            return atom.color in card_colors
        assert atom.colors  # FAtom validation: COLOR_IN requires non-empty
        return bool(card_colors) and card_colors <= set(atom.colors)
    if pred is FAtomPred.COLOR_COUNT_GE:
        # The subject has COUNT or more colors (CR 901.3's color-count
        # test): "protection from multicolored" (Basri's Lieutenant,
        # count=2, read by block_pair_blocked_reason as a blocker-quality
        # filter over the attacker) and Ugin's "-X: exile each permanent ...
        # that's one or more colors" (count=1, inside the effect selector's
        # FAnd). Same identity data as the COLOR_HAS/COLOR_IN twin above:
        # the engine carries no color-changing continuous effects (layers.py
        # never writes color), so an object's printed colors ARE its colors
        # in every zone.
        if handle.namespace != "card":
            return False
        assert atom.count is not None  # FAtom: count is a required slot
        threshold = resolve(atom.count, ctx)
        return len(world.cards[handle].identity.colors) >= threshold
    if pred is FAtomPred.NAME_CHOSEN:
        # The object has what the SOURCE's CHOOSE_NAME of this quality recorded (CR 607.2d: the
        # read refers only to its own object's choice): Runed Halo's name, Diamond Knight's
        # colour, Icon of Ancestry's creature type, chosen as the source entered (EtBState.effect,
        # CR 614.12a). A source that has left the battlefield answers from its last known
        # information (CR 113.7a, 608.2h): the Icon's {3},{T} ability after a Disenchant in
        # response, a protection its granter gave before it left. No record is an UNANSWERED
        # question: flagged, never "False" (the FLIP_WON convention).
        ex = ctx.executor
        quality = atom.string_value
        chosen = None if ex is None else ex.name_choices.get((ctx.source, quality))
        if chosen is None and ex is not None and ctx.source is not None:
            snap = last_known(ctx.source, ctx)
            if snap is not None:
                chosen = dict(snap.choices).get(quality)
        if chosen is None:
            raise NotImplementedError(
                f"executor: NAME_CHOSEN of a {quality or 'card name'} needs a CHOOSE_NAME record "
                f"of the source {ctx.source} (nothing chosen yet, or it chose none)"
            )
        if handle.namespace != "card":
            return False
        identity = world.cards[handle].identity
        if quality == "COLOR":
            return chosen in identity.colors  # printed colours: no effect changes a colour
        if quality == "CREATURE_TYPE":
            # SUBTYPE_EQ's reading, live types included ("is a Knight in addition"). The pick is a
            # creature type and no other kind of type shares its word, so the word is enough.
            return chosen in _type_words(handle, ctx)
        return identity.name == chosen
    if pred is FAtomPred.POWER_LE or pred is FAtomPred.PT_LE:
        assert atom.count is not None
        threshold = resolve(atom.count, ctx)
        power, toughness = ctx.effective_pt(handle)
        if power is None:
            return False
        if pred is FAtomPred.POWER_LE:
            return power <= threshold
        return toughness is not None and power <= threshold and toughness <= threshold
    if pred is FAtomPred.POWER_GE:
        # The GE twin of POWER_LE (Legion's Judgment "destroy target creature
        # with power 4 or greater"; Turret Ogre's / Drowsing Tyrannodon's
        # gates). The SAME live-P/T read as POWER_LE, layers folded, so a
        # buffed creature crosses the threshold honestly. A card with no
        # power (land, instant) is not "a creature with power 4 or greater":
        # characteristic absent, pred False, the POWER_LE convention.
        assert atom.count is not None
        threshold = resolve(atom.count, ctx)
        power, _toughness = ctx.effective_pt(handle)
        if power is None:
            return False
        return power >= threshold
    if pred is FAtomPred.CMC_LE:
        # "converted mana cost X or less" (Eliminate's target filter, Idol of
        # Endurance, Ugin's QX twin: QX rides the cast's declared X like
        # every other quantity, CR 601.2f). IDENTITY data, read exactly the
        # way the QProp CMC/MANA_VALUE field reads it (``_prop_value``: a
        # missing cmc, as on synthetic tokens, is mana value 0).
        assert atom.count is not None
        threshold = resolve(atom.count, ctx)
        if handle.namespace != "card":
            return False
        return (world.cards[handle].identity.cmc or 0) <= threshold
    if pred is FAtomPred.CMC_GE:
        # The GE twin of CMC_LE, the SAME identity read (a missing cmc is
        # mana value 0). Fierce Empath's "reveals a creature with converted
        # mana cost 6 or greater" search filter; one evaluator answers the
        # query lane (enumerate_candidates) and the runtime lane alike.
        assert atom.count is not None
        threshold = resolve(atom.count, ctx)
        if handle.namespace != "card":
            return False
        return (world.cards[handle].identity.cmc or 0) >= threshold
    if pred is FAtomPred.KEYWORD_HAS:
        # "with <keyword>", in a selector filter (Run Afoul's "sacrifices a
        # creature of their choice with flying" CHOOSE pool) and in gate
        # positions (Tide Skimmer / Snarespinner trigger filters+conditions,
        # Portcullis Vine's cost-target gate, Lofty Denial's cost-modifier
        # condition). The answer is the LAYER REGISTRY's live keyword oracle:
        # printed identity keywords ∪ live grants − live losses, rebuilt at
        # every settle. A bare ExecCtx has no registry: flagged, never a
        # printed-only guess that would silently miss a granted or stripped
        # keyword. A handle outside the card set (a player seat) has no
        # keywords: characteristic absent, False.
        assert atom.keyword is not None
        if handle.namespace != "card" or handle not in world.cards:
            return False
        lki = departed_lki(handle, ctx)
        if lki is not None:
            # CR 603.10a: judged on its own departure, the object as it left, its granted
            # keywords included (the layers drop them once they are brought up to date).
            return atom.keyword.name in lki.keywords
        if ctx.layers is None:
            raise NotImplementedError(
                "executor: filter pred KEYWORD_HAS needs the layer "
                "registry for the live keyword oracle (bare ExecCtx has none)"
            )
        return ctx.layers.keyword_of(handle, atom.keyword)
    if pred is FAtomPred.HAS_COUNTER:
        # "put a +1/+1 counter on target creature WITH a +1/+1 counter on
        # it" (Tempered Veteran) compiles to HAS_COUNTER(counter_kind=
        # PLUS_1_PLUS_1, count=None): _FATOM_RULES marks count required,
        # but FAtom.__post_init__ does not enforce "count", so the shape
        # reaches both the query lane (enumerate_candidates) and the runtime
        # gate. An unbound count is the existence reading the pred's own
        # name states, "with a {kind} counter on it" ⇔ count >= 1. NOT a
        # zero default: a threshold of 0 makes the pred vacuously True for
        # every object (every creature would be a legal Tempered Veteran
        # target). A BOUND count resolves through the ordinary quantity lane
        # (its own refusals propagate). counter_kind is a required slot.
        assert atom.counter_kind is not None
        if handle.namespace != "card":
            return False  # characteristic absent (the KEYWORD_HAS convention)
        threshold = 1 if atom.count is None else resolve(atom.count, ctx)
        lki = departed_lki(handle, ctx)
        if lki is not None:
            # "if it had a +1/+1 counter on it" (Basri's Lieutenant): CR 603.10a
            return lki.counters.get(atom.counter_kind.name, 0) >= threshold
        if handle not in world.cards:
            return False
        return world.cards[handle].counters.get(atom.counter_kind.name, 0) >= threshold
    if pred is FAtomPred.CONTROLLER_IS:
        who = atom.who
        assert who is not None
        from MTG_bot.core.executor.selectors import controller_matches, controller_of

        if handle.namespace != "card":
            # A PLAYER handle answers for ITSELF: the attacked-side filters
            # ("two or more ... attacking YOU and/or planeswalkers you
            # control", Mangara) read CONTROLLER_IS YOU off the attack
            # record, whose object is a seat for player-attacks. A player
            # controls themself: the same coordinate oracle the
            # players_for_ref channels use.
            if handle.namespace == "player":
                return controller_matches(who, handle, ctx)
            return False
        lki = departed_lki(handle, ctx)
        if lki is not None:
            # CR 603.10a: judged on its own departure ("whenever a creature an opponent
            # controls dies", Massacre Wurm), the object is the one that left: the
            # controller it had there, not the owner whose graveyard it went to.
            return controller_matches(who, lki.controller, ctx)
        actual = controller_of(ctx, handle)
        return controller_matches(who, actual, ctx)
    if pred is FAtomPred.OPPONENT_OF:
        # The DESTINATION identity pred: the subject must BE a player on the
        # far side of ``who``. Mirrors controller_matches' OPPONENT row: a
        # player that is not on ``who``'s side is an opponent. A CARD
        # subject is FALSE (CR 109.5: a permanent is not a player), so
        # damage to an opponent's creature never satisfies "to an opponent".
        if handle.namespace != "player":
            return False
        from MTG_bot.core.executor.selectors import (
            controller_of,
            players_for_ref,
            resolve_selector,
        )

        who = atom.who
        assert who is not None
        if isinstance(who, Selector):
            side = [
                c if c.namespace == "player" else controller_of(ctx, c)
                for c in resolve_selector(who, ctx)
            ]
        else:
            side = players_for_ref(who, ctx)
        return handle not in side
    if pred is FAtomPred.NOT_FIRST_DRAW_THIS_STEP:
        # Teferi's Ageless Insight ("except the first one you draw in each
        # of your draw steps"). A PLAYER-coordinate pred: the drawn card
        # (the CardDrawnEvent subject) is not inspected; the ``who`` seat
        # answers it off the executor's draw-step tracker (set by
        # Executor._turn_draw, advanced by every APPLIED draw the verb lane
        # makes). Outside a draw step every draw is vacuously "not the first
        # of the step": the exclusion names a step, and no step is open.
        from MTG_bot.core.executor.selectors import players_for_ref

        if not isinstance(atom.who, ControllerRef):
            raise NotImplementedError(
                "executor: NOT_FIRST_DRAW_THIS_STEP with a referent-Selector "
                "who has no corpus carrier (flag, never guess) — r22b"
            )
        seats = players_for_ref(atom.who, ctx)
        if len(seats) != 1:
            raise NotImplementedError(
                "executor: NOT_FIRST_DRAW_THIS_STEP names a single drawer; "
                f"{atom.who.name} denotes {len(seats)} seats (r22b)"
            )
        ex = ctx.executor
        if ex is None:
            raise NotImplementedError(
                "executor: NOT_FIRST_DRAW_THIS_STEP needs the executor's "
                "draw-step tracker (bare ExecCtx has none) — r22b"
            )
        if not ex._draw_step_open:
            return True
        return ex.draw_step_ordinal.get(seats[0], 0) > 0
    if pred is FAtomPred.FLIP_WON:
        # Tavern Swindler compiles the flip and its winner-gate to two rows,
        # so the predicate runs in a SEPARATE context from the FLIP_COIN
        # atom: the answer is the executor's flip ledger. No ledger at all (a
        # bare ExecCtx) or no flip recorded yet is flagged, never guessed as
        # "lost": the conditional has no antecedent.
        if ctx.executor is None or ctx.executor.last_flip_won_by is None:
            raise NotImplementedError(
                "executor: FLIP_WON needs an executor flip ledger with a "
                "recorded FLIP_COIN (bare ExecCtx / no flip yet)"
            )
        assert atom.who is not None
        from MTG_bot.core.executor.selectors import controller_matches

        return controller_matches(atom.who, ctx.executor.last_flip_won_by, ctx)
    if pred is FAtomPred.MAY_DONE:
        # CR 611.1: "do X. If you do, Y": Y executes iff the OPTIONAL X
        # actually executed. The answer is this resolution's record
        # (ctx.may_done), else the decision channel's own audit row: the
        # may-offer at THIS ability's site (``may:<source>``, the tag
        # Executor._run_effect asks with) was answered 'fire'. The guard
        # reads the logged outcome and never re-asks (the question was
        # answered once, in tree order). Handle-free like FLIP_WON: the same
        # answer for every candidate the filter gates. No record at the site
        # is an UNANSWERED QUESTION: flagged, never guessed False (the
        # FLIP_WON / NAME_CHOSEN convention), because a MAY_DONE Conditional
        # only ever rides the seam directly after its own may-offer.
        ex = ctx.executor
        if ex is None:
            raise NotImplementedError(
                "executor: MAY_DONE needs the executor's decision channel "
                "(bare ExecCtx has no may-offer log)"
            )
        # The site tag carries the per-site offer digest
        # (``may:<source>:<digest>``) and a FORCED offer (query-narrowed
        # skip-only) is auto-picked into the JOURNAL, never asked into
        # ask_log, so the guard reads the journal (asked + auto-picked,
        # occurrence order), prefix-matching the site.
        site = f"may:{ctx.source}"
        if site in ctx.may_done:
            # CR 118.12: the optional action's outcome in this resolution:
            # "fire" and the action changed something. The Seq runners also
            # record a MANDATORY step here (Executor._note_step_done):
            # "[Do something]. If you do" reads whether it actually happened.
            return ctx.may_done[site]

        def at_site(what: str) -> bool:
            return what == site or what.startswith(f"{site}:")

        for what, answer in reversed(ex.decisions.journal):
            if at_site(what):
                return answer == "fire"
        raise NotImplementedError(
            f"executor: MAY_DONE has no may-offer record for {site} — the "
            "conditional has no antecedent (unanswered question, flagged "
            "never False)"
        )
    if pred is FAtomPred.CONTROLLER_COUNT_GE:
        # "you control four or more <inner>" (Gadrak's attack gate; the
        # Fabled Passage "Then if you control four or more lands, untap
        # that land." tail). A WORLD count, not history: the same
        # battlefield population the CONTROLLER_IS reading defines, under
        # ctx.controller (the vocab has no who slot — YOU is the ability
        # controller). Handle-free like FLIP_WON: the same answer for every
        # candidate the filter gates, and it judges a sacrificed source
        # correctly (Fabled Passage is already in the graveyard here).
        assert atom.count is not None and atom.inner_filter is not None
        threshold = resolve(atom.count, ctx)
        from MTG_bot.core.executor.selectors import controller_of

        counted = 0
        for card in sorted(world.cards):
            if (
                world.zone_of(card).kind == ZONE_BATTLEFIELD
                and not phased_out(ctx, card)  # CR 702.26b: not counted
                and controller_of(ctx, card) == ctx.controller
                and eval_filter(atom.inner_filter, card, ctx)
            ):
                counted += 1
                if counted >= threshold:
                    return True
        return counted >= threshold
    if pred is FAtomPred.CONTROLLER_COUNT_GT:
        # Garruk, Unleashed's -2: the DUAL-filter population comparison "if
        # an opponent controls more <inner_filter> than you
        # <right_inner_filter>". The two sides carry their OWN CONTROLLER_IS
        # atoms (the compiled Garruk atom: inner = Creature AND
        # CONTROLLER_IS OPPONENT, right_inner = Creature AND CONTROLLER_IS
        # YOU), so each side's count is just its filter over the battlefield
        # population, the same handle-free WORLD count the GE sibling
        # defines. Two-player reading: with several opponents the inner
        # count spans all of them, where "an opponent" means any single one.
        assert atom.inner_filter is not None
        assert atom.right_inner_filter is not None

        def _bf_count(filt) -> int:
            return sum(
                1
                for card in sorted(world.cards)
                if world.zone_of(card).kind == ZONE_BATTLEFIELD
                and not phased_out(ctx, card)  # CR 702.26b: not counted
                and eval_filter(filt, card, ctx)
            )

        return _bf_count(atom.inner_filter) > _bf_count(atom.right_inner_filter)
    if pred is FAtomPred.ZONE_COUNT_GE:
        # Thieves' Guild Enforcer: "<who> has >= count cards in their <zone>
        # matching inner_filter". Handle-free set gate like
        # CONTROLLER_COUNT_GE (the trigger-condition judge); TRUE when ANY
        # denoted player's zone meets the threshold ("an opponent has eight
        # or more cards in their graveyard"). WHO drives the population: in
        # the corpus the IR's zone.controller rides with WHO, so reading WHO
        # is the whole answer (a ControllerRef, or a referent Selector as for
        # CONTROLLER_IS). A non-card zone (PLAYER position) is flagged, never
        # counted empty.
        from MTG_bot.core.executor.selectors import (
            ZONE_KIND_TO_STATE,
            controller_of,
            players_for_ref,
            resolve_selector,
        )

        assert (
            atom.count is not None
            and atom.zone is not None
            and atom.who is not None
            and atom.inner_filter is not None
        )
        threshold = resolve(atom.count, ctx)
        zone_ir = atom.zone
        state_kind = ZONE_KIND_TO_STATE.get(zone_ir.kind)
        if state_kind is None:
            raise NotImplementedError(
                f"executor: ZONE_COUNT_GE zone {zone_ir.kind.name} is not a "
                "card zone (flag, never a zero-count guess)"
            )
        who = atom.who
        if isinstance(who, ControllerRef):
            players = players_for_ref(who, ctx)
        else:
            players = [
                c if c.namespace == "player" else controller_of(ctx, c)
                for c in resolve_selector(who, ctx)
            ]
        for player in players:
            entries = ctx.world.players[player].zone(state_kind).entries
            # The Zone's OPTIONAL position bounds the population (Conspicuous
            # Snoop): TOP counts only the top entry, mirroring the selector
            # side (enumerate_zone: top of library = last entry), so "the top
            # card of your library is X" is this predicate with
            # position=TOP and count=1.
            position = zone_ir.position
            if position is ZonePosition.TOP:
                entries = entries[-1:]
            elif position is ZonePosition.BOTTOM:
                entries = entries[:1]
            counted = sum(1 for h in entries if eval_filter(atom.inner_filter, h, ctx))
            if counted >= threshold:
                return True
        return False
    if pred is FAtomPred.NAME_PARTITION_COUNT_GE:
        # Chrome Replicator: among the permanents ctx.controller CONTROLS,
        # those passing inner_filter group by EXACT printed name and the
        # largest group must reach count (templates_b2a's reading: "grouped
        # by EXACT name, the largest group; no pairwise name-equality
        # vocabulary"). Handle-free like CONTROLLER_COUNT_GE; the
        # battlefield population read through the GAIN_CONTROL overlay
        # (controller_of).
        from MTG_bot.core.executor.selectors import controller_of

        assert atom.count is not None and atom.inner_filter is not None
        threshold = resolve(atom.count, ctx)
        groups: dict[str, int] = {}
        for card in sorted(world.cards):
            if (
                world.zone_of(card).kind != ZONE_BATTLEFIELD
                or phased_out(ctx, card)  # CR 702.26b: not counted
                or controller_of(ctx, card) != ctx.controller
                or not eval_filter(atom.inner_filter, card, ctx)
            ):
                continue
            name = world.cards[card].identity.name
            groups[name] = groups.get(name, 0) + 1
            if groups[name] >= threshold:
                return True
        return False
    if pred is FAtomPred.MOVED_TO_ZONE_THIS_TURN:
        # Necromentia's "-1/-0… for each card exiled from their hand this
        # way" counts per CANDIDATE (the QCount Selector filters the exile
        # population card by card); Barrin's end-step gate ("if a permanent
        # was put into your hand from the battlefield this turn") is about
        # SOME permanent. The two readings are discriminated by the handle
        # itself: a card that currently sits in the pred's DESTINATION zone
        # answers for itself; anything else (the gate's source anchor) is
        # existential. ZONE_CHANGE rows carry the zone OWNERS in their owner
        # columns (the snapshot keys zones by player), so both endpoints
        # answer.
        from MTG_bot.core.executor.events import KIND_ZONE_CHANGE
        from MTG_bot.core.executor.selectors import (
            ZONE_KIND_TO_STATE,
            controller_matches,
            players_for_ref,
        )

        assert (
            atom.from_zone is not None
            and atom.to_zone is not None
            and atom.who is not None
        )
        who = atom.who  # local bind: the closure reads the narrowed type
        if any(
            z.controller is ControllerRef.OWNER for z in (atom.from_zone, atom.to_zone)
        ):
            raise NotImplementedError(
                "executor: MOVED_TO_ZONE_THIS_TURN OWNER zone slots need "
                "original-owner history (no corpus use — flagged, not guessed)"
            )
        to_state = ZONE_KIND_TO_STATE[atom.to_zone.kind]
        from_state = ZONE_KIND_TO_STATE[atom.from_zone.kind]
        dest_players = players_for_ref(atom.to_zone.controller, ctx)
        src_players = players_for_ref(atom.from_zone.controller, ctx)

        def _moved_row(e: GameEvent) -> bool:
            frm, to, owner_before, owner_after = e.zone_move
            return (
                to == to_state
                and frm == from_state
                and owner_after in dest_players
                and owner_before in src_players
                and controller_matches(who, owner_after, ctx)
            )

        rows = [
            e
            for e in _turn_rows(ctx, pred.name)
            if e.kind == KIND_ZONE_CHANGE and _moved_row(e)
        ]
        in_destination = (
            handle.namespace == "card"
            and handle in world.cards
            and world.zone_of(handle).kind == to_state
            and world.controller_of(handle) in dest_players
        )
        if in_destination:
            return any(e.subject == handle for e in rows)
        return any(e.subject is not None for e in rows)
    if pred is FAtomPred.ENTERED_THIS_TURN_FROM:
        # The ETB-entry twin the Archfiend's Vessel gate compiles beside
        # CAST_THIS_TURN_FROM ("if it entered from your graveyard or you
        # cast it from your graveyard"). Handle-scoped by the grammar's own
        # reading ("it entered"): THIS object entered the battlefield from
        # that zone this turn.
        from MTG_bot.core.executor.events import KIND_ZONE_CHANGE
        from MTG_bot.core.executor.selectors import (
            ZONE_KIND_TO_STATE,
            players_for_ref,
        )

        assert atom.zone is not None
        if atom.zone.controller is ControllerRef.OWNER:
            raise NotImplementedError(
                "executor: ENTERED_THIS_TURN_FROM OWNER zone slots need "
                "original-owner history (no corpus use — flagged, not guessed)"
            )
        from_state = ZONE_KIND_TO_STATE[atom.zone.kind]
        owners = players_for_ref(atom.zone.controller, ctx)
        # CR 400.7: the entry must be THIS object's. A card that entered from
        # the graveyard, left, and entered again from the stack is a new
        # object that did not enter from the graveyard. Its object is the one
        # its LAST battlefield entry made (the permanent now, or the
        # last-known one after it left); any older entry of the card this
        # turn belongs to an older object.
        entry = None
        for e in _turn_rows(ctx, pred.name):
            if (
                e.kind == KIND_ZONE_CHANGE
                and e.subject == handle
                and e.zone_move[1] == ZONE_BATTLEFIELD
            ):
                entry = e
        if entry is None or entry is not _last_battlefield_entry(ctx, handle):
            return False
        frm, _to, owner_before, _after = entry.zone_move
        return frm == from_state and owner_before in owners
    if pred is FAtomPred.CAST_THIS_TURN_FROM:
        # "you cast it from your graveyard" (Archfiend's Vessel), "if this
        # spell was cast from anywhere other than your hand" (See the
        # Truth's FNot twin). Handle-scoped over the CAST rows, whose
        # payload carries (caster, ordinal, spell_kind, from_zone, x_value,
        # kicked): the from_zone column makes the origin readable after the
        # spell has moved on.
        from MTG_bot.core.executor.events import KIND_CAST
        from MTG_bot.core.executor.selectors import (
            ZONE_KIND_TO_STATE,
            controller_matches,
        )

        assert atom.zone is not None and atom.who is not None
        from_state = ZONE_KIND_TO_STATE[atom.zone.kind]
        for e in _turn_rows(ctx, pred.name):
            if e.kind != KIND_CAST or e.subject != handle:
                continue
            caster, _ordinal, _kind, row_from, _x, _kicked = e.cast
            if row_from != from_state:
                continue
            if not controller_matches(atom.who, caster, ctx):
                continue
            if atom.zone.controller is ControllerRef.OWNER:
                # "from its owner's zone": the caster is the owner-side
                # witness (a spell sits in its caster's stack seat).
                if handle not in world.cards or caster != world.controller_of(handle):
                    continue
            elif not controller_matches(atom.zone.controller, caster, ctx):
                continue
            return True
        return False
    if pred is FAtomPred.WAS_CAST_THIS_TURN:
        # Containment Priest: the zone-agnostic twin of CAST_THIS_TURN_FROM,
        # "it was cast this turn (by who)". Same KIND_CAST rows (emitted at
        # 601.2h, before resolution, so the row is already journalled by the
        # time an enters-the-battlefield replacement judges it: the Priest
        # spares its own casting spell and every other cast creature, but
        # not a put-onto-the-battlefield creature, which never passed
        # through the stack).
        # CR 400.7: the cast must be THIS object's. A card cast earlier this
        # turn that died and was returned is a new object that was not cast
        # (the Priest must not spare a reanimated creature).
        # _object_cast_row follows the object across its own zone changes.
        from MTG_bot.core.executor.selectors import controller_matches

        assert atom.who is not None
        row = _object_cast_row(ctx, handle)
        if row is None or row not in _turn_rows(ctx, pred.name):
            return False
        return controller_matches(atom.who, row.cast[0], ctx)
    if pred is FAtomPred.WAS_KICKED:
        # CR 702.27a, three reader lanes over ONE carrier: the CAST row's
        # trailing kicked column (journal.emit_cast) is the paid/not-paid
        # choice of the cast. The read splits by the JUDGED object's
        # provenance:
        #
        # * SPELL lane — the judged handle sits on the STACK (a Conditional
        #   resolved by a spell frame, Into the Roil's arm): the object IS
        #   the spell; its own CAST row in the turn window is the answer.
        # * TRIGGER lane — a condition/event filter judged against the
        #   casting spell ("whenever you cast a kicked spell", Roost's cast
        #   arm): same stack-scoped window read, CR 603.2's event scope.
        # * PERMANENT lane — the judged handle sits on the BATTLEFIELD
        #   (the gated EtBState stamped on entry, Cragplate; an ETB-trigger
        #   condition reading "if it was kicked", Kitesail/Roost's ETB
        #   arm): "was kicked" is a property of how THIS OBJECT entered.
        #   A permanent that left and re-entered is a NEW object that was
        #   never cast (CR 400.7), so the stale CAST row must not re-apply
        #   the gated entering state (CR 614.1c), so the read is ENTRY-BOUND
        #   (_permanent_was_kicked): the entry ZONE_CHANGE row's from_state
        #   carries the provenance.
        #
        # No CAST row / no journalled entry (a setup card, a token) and any
        # entry from anywhere but the stack read False — CR 702.27a: an
        # object that was not cast was never kicked.
        if (
            handle.namespace == "card"
            and handle in world.cards
            and world.zone_of(handle).kind == ZONE_BATTLEFIELD
        ):
            return _permanent_was_kicked(ctx, handle)
        from MTG_bot.core.executor.events import KIND_CAST

        kicked = False
        for e in _turn_rows(ctx, pred.name):
            if e.kind == KIND_CAST and e.subject == handle:
                kicked = e.kicked
        return kicked
    if pred is FAtomPred.DIED_THIS_TURN:
        # CREATURE_DIES carries the was-snapshot (type line + effective P/T
        # AT EVENT TIME), which is how a "nontoken creature that died this
        # turn" count answers after the world has moved the card (Gadrak's
        # end-step Treasures). The snapshot's consumers are this row lookup
        # and the binder's event matcher; the FAtomPred vocabulary has no
        # WAS_* member.
        from MTG_bot.core.executor.events import KIND_CREATURE_DIES

        rows = _turn_rows(ctx, pred.name)
        # The journal writes a dies row for EVERY battlefield-to-graveyard
        # move (CR 700.4: any permanent "dies"), and every compiled reading
        # of this pred is about a CREATURE ("if a creature died this turn",
        # "creature that died this turn"). So only rows whose was-snapshot
        # type line names Creature count (CR 603.10a: the object as it last
        # existed on the battlefield). A sacrificed Treasure died, but no
        # creature did (Twinblade Assassins must not draw off it).
        dies = [
            e
            for e in rows
            if e.kind == KIND_CREATURE_DIES
            and "Creature" in _type_line_tokens(e.dies[2])
        ]
        if any(e.subject == handle for e in dies):
            return True
        # An EXISTENTIAL reading ("if a creature died this turn") for a
        # judged handle that could never itself be the dead creature: a
        # player handle (a LifeGainedEvent replacement judged over its
        # subject, Life Goes On), a card whose printed type line names no
        # creature (a Conditional judged over the resolving spell, Fungal
        # Rebirth), or a creature sitting on the battlefield (an activation
        # source's gate, Caged Zombie). A creature-typed handle off the
        # battlefield (graveyard / exile / hand) keeps the strict per-handle
        # reading, "did THIS creature die": the subject match above answers
        # True for a dead one, and anything else answers False.
        creature_typed = (
            handle.namespace == "card"
            and handle in world.cards
            and "Creature"
            in set(_type_line_tokens(world.cards[handle].identity.type_line))
            and world.zone_of(handle).kind != ZONE_BATTLEFIELD
        )
        if not creature_typed:
            return bool(dies)
        return False
    if pred is FAtomPred.IS_EXILED_WITH_SOURCE:
        # "cards exiled with ~" (Idol of Endurance, Chandra, Heart of Fire).
        # WORLD half: the card is in exile NOW. HISTORY half: the source
        # CAUSED the exile: the journal's diff-inspect writes the acting
        # ability's source into the cause column, so "exiled with this
        # artifact" is a cause read, not a heuristic. NOT turn-windowed:
        # an exile-with persists across turns (the world half prunes what
        # has since moved on).
        from MTG_bot.core.executor.events import KIND_ZONE_CHANGE

        jrn = ctx.journal
        if jrn is None:
            raise NotImplementedError(
                "executor: filter pred IS_EXILED_WITH_SOURCE reads the "
                "journalled exile history (this ExecCtx has no journal)"
            )
        if handle not in world.cards or world.zone_of(handle).kind != ZONE_EXILE:
            return False
        return any(
            e.kind == KIND_ZONE_CHANGE
            and e.subject == handle
            and e.zone_move[1] == ZONE_EXILE
            and e.cause == ctx.source
            for e in jrn.events
        )
    if pred is FAtomPred.IS_ATTACKING:
        # CR 506.4: the executor's live attack record, the attacker
        # set the COMBAT skeleton fills at declaration and clears at end
        # of combat. Tide Skimmer's "you attack with two or more" gate and
        # the templates' IS_ATTACKING selectors read exactly this state.
        if ctx.executor is None:
            raise NotImplementedError(
                "executor: filter pred IS_ATTACKING reads the executor's "
                "attack record (bare ExecCtx)"
            )
        return handle in ctx.executor.attackers
    if pred is FAtomPred.IS_BLOCKING:
        # CR 506.4: the executor's live block record: a handle IS blocking
        # while it stands in some attacker's blocker list (the record clears
        # with the attack record at end of combat).
        if ctx.executor is None:
            raise NotImplementedError(
                "executor: filter pred IS_BLOCKING reads the executor's "
                "block record (bare ExecCtx)"
            )
        return any(handle in blockers for blockers in ctx.executor.blocked_by.values())
    if pred is FAtomPred.ATTACK_AGAINST_COUNT_GE:
        # Mangara, the Diplomat's intervening "if" (CR 603.4): "if two or
        # more of THOSE creatures are attacking you and/or planeswalkers you
        # control", read as the attackers are declared and again as the
        # ability resolves. Those creatures are every creature declared in the
        # triggering declaration (its DECLARE_ATTACKERS rows: one put onto the
        # battlefield attacking is not among them, CR 508.4); outside an attack
        # firing, the attack record. Each is judged by what it attacks now, in
        # the firing ability's coordinates: CONTROLLER_IS YOU = "attacking you"
        # (a player matches themself), an attacked planeswalker matches through
        # its controller (CR 508.1b). One removed from combat attacks nothing;
        # one that left the battlefield is judged by what it was attacking as
        # it left (its last known information, CR 608.2h; the card's ruling).
        ex = ctx.executor
        if ex is None:
            raise NotImplementedError(
                "executor: filter pred ATTACK_AGAINST_COUNT_GE reads the "
                "executor's attack record (bare ExecCtx)"
            )
        assert atom.count is not None and atom.inner_filter is not None
        threshold = resolve(atom.count, ctx)
        those = list(ex.attackers)
        event = ctx.event
        if isinstance(event, GameEvent) and event.kind == KIND_DECLARE_ATTACKERS:
            those = [
                row.subject
                for row in ex.journal.turn_window()
                if row.kind == KIND_DECLARE_ATTACKERS and row.declare_group == event.declare_group
            ]
        counted = 0
        for attacker in those:
            lki = ex.departed_lki.get(attacker)
            if attacker in ex.attackers:
                attacked = ex.attacked.get(attacker)
            elif lki is not None and not (
                attacker in world.cards and world.zone_of(attacker).kind == ZONE_BATTLEFIELD
            ):
                attacked = lki.attacking
            else:
                attacked = None
            if attacked is None:
                continue
            if eval_filter(atom.inner_filter, attacked, ctx):
                counted += 1
                if counted >= threshold:
                    return True
        return counted >= threshold
    if pred is FAtomPred.CARDS_DRAWN_THIS_TURN_GE:
        # Tome Anima's "can't be blocked as long as you've drawn two or more
        # cards this turn" static gate, consulted live at every block pair:
        # count the journal's CARD_DRAWN rows of the turn window (subject =
        # the card drawn, data[0] = the drawing player) against WHO's seat.
        from MTG_bot.core.executor.events import KIND_CARD_DRAWN
        from MTG_bot.core.executor.selectors import players_for_ref

        assert atom.count is not None
        threshold = resolve(atom.count, ctx)
        if not isinstance(atom.who, ControllerRef):
            raise NotImplementedError(
                "executor: CARDS_DRAWN_THIS_TURN_GE with a Selector seat "
                "has no consumer (the corpus carries ControllerRef)"
            )
        drawners = set(players_for_ref(atom.who, ctx))
        drawn = 0
        for row in _turn_rows(ctx, pred.name):
            if row.kind != KIND_CARD_DRAWN:
                continue
            if row.draw[0] in drawners:
                drawn += 1
                if drawn >= threshold:
                    return True
        return drawn >= threshold
    if pred is FAtomPred.LIFE_LEAD_OVER_START_GE:
        # Speaker of the Heavens: "you have at least N life more than your
        # starting life total". The rule text reads CURRENT life minus the
        # player's START, so this is a ledger read, not a journal sum of
        # gains (which would overstate the lead after any life loss). The
        # start is the executor's construction-time snapshot (the
        # start_life the world was built with; replay rebuilds the world at
        # that value). Bare-count atom: WHO is implicitly YOU, the ability's
        # controller (the gate never carries a seat).
        from MTG_bot.core.executor.selectors import players_for_ref

        assert atom.count is not None
        if ctx.executor is None:
            raise ValueError(
                "executor: LIFE_LEAD_OVER_START_GE needs an executor-backed "
                "ExecCtx (the starting-life ledger lives on the executor)"
            )
        threshold = resolve(atom.count, ctx)
        player = players_for_ref(ControllerRef.YOU, ctx)[0]
        lead = world.players[player].life - ctx.executor.starting_life[player]
        return lead >= threshold
    if pred is FAtomPred.LIFE_TOTAL_GE:
        # Twinblade Paladin's "as long as you have 25 or more life": your life total
        # now (CR 119.1), whatever it started at (CR 103.4; the card's ruling for
        # formats that do not start at 20). ``who`` is YOU (FAtom refuses any other);
        # the judged handle is unused.
        assert atom.count is not None
        return world.players[ctx.controller].life >= resolve(atom.count, ctx)
    if pred is FAtomPred.LIFE_GAINED_THIS_TURN_GE:
        # Sanguine Indulgence's CostModifier condition: the
        # CARDS_DRAWN_THIS_TURN_GE twin over the LIFE_GAINED rows (subject is
        # the gaining player, payload the amount, journalled by the
        # event-diff layer for EVERY life gain, so verbs need not know the
        # pred exists). The comparison is a SUM ("gained N or more life"),
        # not a row count: two separate 2-life gains satisfy a threshold of 3.
        from MTG_bot.core.executor.events import KIND_LIFE_GAINED
        from MTG_bot.core.executor.selectors import players_for_ref

        assert atom.count is not None
        threshold = resolve(atom.count, ctx)
        if not isinstance(atom.who, ControllerRef):
            raise NotImplementedError(
                "executor: LIFE_GAINED_THIS_TURN_GE with a Selector seat "
                "has no consumer (the corpus carries ControllerRef)"
            )
        gainers = set(players_for_ref(atom.who, ctx))
        gained = 0
        for row in _turn_rows(ctx, pred.name):
            if row.kind != KIND_LIFE_GAINED:
                continue
            if row.subject in gainers:
                gained += row.amount
                if gained >= threshold:
                    return True
        return gained >= threshold
    if pred is FAtomPred.INSTANT_OR_SORCERY_CAST_THIS_TURN:
        # Stormwing Entity's CostModifier condition: scan the CAST feed.
        # Payload column 3 carries the SpellKind NAME (stack.emit_cast
        # passes ``node.kind.name``), so the instant-or-sorcery test is a
        # row filter; WHO scopes the caster seat like the other history
        # preds.
        from MTG_bot.core.executor.events import KIND_CAST
        from MTG_bot.core.executor.selectors import controller_matches

        assert atom.who is not None
        if not isinstance(atom.who, ControllerRef):
            raise NotImplementedError(
                "executor: INSTANT_OR_SORCERY_CAST_THIS_TURN with a Selector "
                "seat has no consumer (the corpus carries ControllerRef)"
            )
        for row in _turn_rows(ctx, pred.name):
            if row.kind != KIND_CAST:
                continue
            caster, _ordinal, kind, _from, _x, _kicked = row.cast
            if kind in ("INSTANT", "SORCERY") and controller_matches(
                atom.who, caster, ctx
            ):
                return True
        return False
    if pred in (FAtomPred.EVENT_THIS_TURN, FAtomPred.SUBJECT_OF_EVENT_THIS_TURN):
        return _event_this_turn(atom, handle, ctx)
    if pred is FAtomPred.TURN_OF:
        # Discontinuity's your-turn cost window: the active-seat column
        # answers directly, no journal read. WHO maps through the
        # canonical controller_matches (YOU = my seat is active; OPPONENT
        # = an opponent's seat is, which is how a "During your turn" gate
        # reads False from the opponent's coordinates).
        from MTG_bot.core.executor.selectors import controller_matches

        assert atom.who is not None
        if not isinstance(atom.who, ControllerRef):
            raise NotImplementedError(
                "executor: TURN_OF with a Selector seat has no consumer "
                "(the corpus carries ControllerRef)"
            )
        if world.active_player is None:
            return False
        return controller_matches(atom.who, world.active_player, ctx)
    if pred is FAtomPred.HAS_KICKER:
        # Murasa Sproutling's "target card with a kicker ability" graveyard
        # filter. PRINTED-property reading: the ground truth is the card's
        # COMPILED record. A card HAS a kicker iff its FRONT-FACE ability
        # tuple carries a KickerAbility node, the same top-level scan
        # legal_casts and the cast fold use via legality.kicker_of. The
        # record resolves through legality.spell_record (the per-handle
        # bridge, else the oracle-id registry), so cards OFF the battlefield
        # answer too. A BackFace node carries its abilities in its OWN
        # tuple, which this scan never descends: a back-face-only kicker
        # does NOT satisfy HAS_KICKER for a front-face decision; if a face
        # other than the front is ever judged, this is the site to amend.
        # Tokens: a created token has no compiled record (or carries the
        # token record with is_token); a token never has a printed kicker,
        # so both lanes read False, never raise.
        from MTG_bot.core.ability_tree import KickerAbility
        from MTG_bot.core.executor.legality import spell_record

        if ctx.executor is None:
            raise NotImplementedError(
                "executor: filter pred HAS_KICKER needs an executor-backed "
                "ExecCtx (the compiled-record registry lives on the binder)"
            )
        record = spell_record(ctx.executor, handle)
        if record is None or record.is_token:
            return False
        return any(isinstance(a, KickerAbility) for a in record.abilities)
    if pred is FAtomPred.STACK_KIND_EQ:
        # CR 405.1, 111.1/112.1: a card or a copy of a card on the stack is a
        # spell; abilities on the stack are not (CR 113.7a) and are answered
        # above, by their own kind.
        from MTG_bot.core.state import ZONE_STACK

        if atom.string_value != "SPELL":
            return False
        return handle in world.cards and world.zone_of(handle).kind == ZONE_STACK
    raise NotImplementedError(
        f"executor: filter pred {pred.name} not implemented (12c query surface)"
    )


def _last_battlefield_entry(ctx: ExecCtx, handle: Handle) -> GameEvent | None:
    """The journal row of ``handle``'s most recent entry onto the battlefield,
    over the whole journal (None if it never entered). Its object is the
    permanent now, or the last-known one if it has left since."""
    from MTG_bot.core.executor.events import KIND_ZONE_CHANGE

    jrn = ctx.journal
    if jrn is None:
        raise NotImplementedError(
            "executor: an entered-from read needs the journalled zone history "
            "(this ExecCtx has no journal)"
        )
    for e in reversed(jrn.events):
        if (
            e.kind == KIND_ZONE_CHANGE
            and e.subject == handle
            and e.zone_move[1] == ZONE_BATTLEFIELD
        ):
            return e
    return None


def _object_cast_row(ctx: ExecCtx, handle: Handle) -> GameEvent | None:
    """The CAST row of the object ``handle`` is now, or None when this object
    was not cast (CR 400.7: a card that changes zones becomes a new
    object). On the stack, the CAST row after its move onto the stack; on the
    battlefield, the CAST row inside the stack residency its last entry came
    from (a resolving permanent spell is the object that was cast, the
    WAS_KICKED permanent-lane reading); in any other zone, None. The whole
    journal is read: the object's cast may be older than this turn."""
    from MTG_bot.core.executor.events import KIND_CAST, KIND_ZONE_CHANGE
    from MTG_bot.core.state import ZONE_STACK

    jrn = ctx.journal
    if jrn is None:
        raise NotImplementedError(
            "executor: a was-cast read needs the journalled zone history "
            "(this ExecCtx has no journal)"
        )
    zone = ctx.world.zone_of(handle).kind
    if zone not in (ZONE_STACK, ZONE_BATTLEFIELD):
        return None
    rows = [
        e
        for e in jrn.events
        if e.subject == handle and e.kind in (KIND_ZONE_CHANGE, KIND_CAST)
    ]
    need_entry = zone == ZONE_BATTLEFIELD
    for e in reversed(rows):
        if need_entry:
            if e.kind == KIND_ZONE_CHANGE and e.zone_move[1] == ZONE_BATTLEFIELD:
                if e.zone_move[0] != ZONE_STACK:
                    return None  # put onto the battlefield, never cast
                need_entry = False
            continue
        if e.kind == KIND_CAST:
            return e
        if e.kind == KIND_ZONE_CHANGE and e.zone_move[1] == ZONE_STACK:
            return None  # the stack residency began without a cast
    return None


def _permanent_was_kicked(ctx: ExecCtx, handle: Handle) -> bool:
    """WAS_KICKED's PERMANENT lane (CR 400.7 object identity + 614.1c
    entered state + 702.27a the kick choice). Judged for a handle ON the
    battlefield; answers from the CURRENT entry, not the turn window: a
    kicked permanent blinked and returned through exile is a NEW object that
    was never cast, so its gated EtBState must not re-apply and a later "if
    it was kicked" must follow the entry's provenance.

    The provenance is the LAST battlefield-entry ZONE_CHANGE row's
    ``from_state``. An entry whose from_state is not the stack (put onto
    the battlefield from hand/graveyard, blink return, token creation) was
    not a cast: False, and the CAST rows are never consulted. An entry FROM
    the stack carries the kick of the CAST row of that same stack residency:
    emit_cast fires after the card is parked on the stack (stack.cast), so
    the cast row's clock is strictly later than the residency-opening
    ZONE_CHANGE row and strictly earlier than the entry. A residency with no
    cast row inside (a put onto the stack) therefore reads False, never the
    object's older cast. The scan is the WHOLE journal, not the turn window:
    a permanent cast kicked LAST turn still answers True today.
    """
    from MTG_bot.core.executor.events import KIND_CAST, KIND_ZONE_CHANGE
    from MTG_bot.core.state import ZONE_STACK

    jrn = ctx.journal
    if jrn is None:
        raise NotImplementedError(
            "executor: filter pred WAS_KICKED reads the journalled entry "
            "provenance (this ExecCtx has no journal)"
        )
    entry_from: str | None = None  # last battlefield entry's from_state
    stack_in_clock = -1  # last move of the handle ONTO the stack zone
    cast_kicked = False  # last CAST row's paid/not-paid flag
    cast_clock = -1
    for e in jrn.events:  # ascending: last matching row wins
        if e.subject != handle:
            continue
        if e.kind == KIND_ZONE_CHANGE:
            frm, to, _before, _after = e.zone_move
            if to == ZONE_BATTLEFIELD:
                entry_from = frm
            elif to == ZONE_STACK:
                stack_in_clock = e.clock
        elif e.kind == KIND_CAST:
            cast_kicked = e.kicked
            cast_clock = e.clock
    if entry_from != ZONE_STACK:
        return False  # not entered by a spell resolution: never cast
    # the kick of THIS stack residency — the cast row must belong to it
    # (a residency with no cast row inside: a put-on-stack / copy entry —
    # was never cast, never kicked).
    return cast_kicked and cast_clock > stack_in_clock


def _died_this_turn_census(sel: Selector, ctx: ExecCtx) -> int | None:
    """The census for "the number of [nontoken] creatures that died [under
    your control] this turn" (Liliana's Standard Bearer, Gadrak, Canopy
    Stalker): it counts this turn's DEATH EVENTS, never graveyard contents. To die
    is to be put into a graveyard from the battlefield (CR 700.4); the count
    reads each dead creature as it last existed on the battlefield (CR
    603.10a): its type line, its controller, its token flag, all recorded on
    the CREATURE_DIES row. So a card that left the graveyard since still
    counts, a token that ceased to exist (CR 704.5d) counts, and the
    controller is the one at death, not the graveyard's owner.

    Applies to an ALL-mode census whose filter conjoins DIED_THIS_TURN; None
    for every other selector (the ordinary zone census). A conjunct this
    census cannot judge on the death row raises (flag, never guess)."""
    if sel.mode is not SelectorMode.ALL or sel.referent is not None:
        return None

    def conjuncts(f: Filter) -> list[Filter]:
        if isinstance(f, FAnd):
            return [c for child in f.children for c in conjuncts(child)]
        return [f]

    parts = conjuncts(sel.filter)
    if not any(isinstance(c, FAtom) and c.pred is FAtomPred.DIED_THIS_TURN for c in parts):
        return None
    from MTG_bot.core.executor.events import KIND_CREATURE_DIES
    from MTG_bot.core.executor.selectors import controller_matches

    def holds(part: Filter, row: GameEvent) -> bool:
        negate = isinstance(part, FNot)
        atom = part.inner if isinstance(part, FNot) else part
        if not isinstance(atom, FAtom):
            raise NotImplementedError(
                f"executor: died-this-turn census cannot judge {type(atom).__name__}"
            )
        data = row.data
        if atom.pred is FAtomPred.DIED_THIS_TURN:
            got = True
        elif atom.pred is FAtomPred.TYPE_EQ:
            got = atom.string_value in _type_line_tokens(str(data[2]))
        elif atom.pred is FAtomPred.IS_TOKEN:
            got = bool(data[6])
        elif atom.pred is FAtomPred.CONTROLLER_IS:
            assert atom.who is not None
            was_controller = data[5]
            assert isinstance(was_controller, Handle)
            got = controller_matches(atom.who, was_controller, ctx)
        else:
            raise NotImplementedError(
                f"executor: died-this-turn census cannot judge {atom.pred.name} "
                "on a death row"
            )
        return got != negate

    rows = [e for e in _turn_rows(ctx, "DIED_THIS_TURN") if e.kind == KIND_CREATURE_DIES]
    return sum(1 for row in rows if all(holds(part, row) for part in parts))


def _turn_rows(ctx: ExecCtx, pred_name: str) -> list[GameEvent]:
    """The current turn's journal rows a history predicate answers against.
    No journal on the ctx means no answer: the raise names the
    predicate (the FLIP_WON/NAME_CHOSEN convention — an unanswered question
    is flagged, never a guessed False)."""
    jrn = ctx.journal
    if jrn is None:
        raise NotImplementedError(
            f"executor: filter pred {pred_name} reads the journalled turn "
            "history (this ExecCtx has no journal)"
        )
    return jrn.turn_window()


def _event_this_turn(atom: FAtom, handle: Handle, ctx: ExecCtx) -> bool:
    """EVENT_THIS_TURN / SUBJECT_OF_EVENT_THIS_TURN: did the event
    ``atom.event`` describes happen this turn, ``atom.count`` or more?

    One reading for every "this turn" question an EventSpec can ask. The
    turn's journal rows are matched by the trigger binder's own matcher, in
    this ability's coordinates (its source and controller), so "an opponent",
    "a blue or black spell" and "an opponent was dealt damage" mean here what
    they mean in a trigger. A row counts 1, or its amount for life and damage
    rows ("lost 4 or more life"), and the count is kept per individual
    (:func:`_individual`): one player losing 4 life meets "a player lost 4 or
    more life this turn" (Knight of the Ebon Legion); two players losing 2
    each do not.

    SUBJECT_OF_EVENT_THIS_TURN reads only the rows whose subject is the
    judged object, from its last zone change on: an object that changes zones
    is a new object with no history (CR 400.7), so a creature dealt damage,
    then bounced and cast again, was not "dealt damage this turn"; the zone
    change that made it is its own ("entered the battlefield this turn")."""
    executor = ctx.executor
    if executor is None:
        raise NotImplementedError(
            f"executor: filter pred {atom.pred.name} matches the turn's journal "
            "with the trigger binder (bare ExecCtx)"
        )
    assert atom.event is not None and atom.count is not None  # FAtom validates both
    rows = _turn_rows(ctx, atom.pred.name)
    if atom.pred is FAtomPred.SUBJECT_OF_EVENT_THIS_TURN:
        from MTG_bot.core.executor.events import KIND_ZONE_CHANGE

        # A zone change before this turn precedes every row of it, so the
        # turn's own rows decide where the object began.
        rows = [e for e in rows if e.subject == handle]
        since = max((e.clock for e in rows if e.kind == KIND_ZONE_CHANGE), default=0)
        rows = [e for e in rows if e.clock >= since]
    threshold = resolve(atom.count, ctx)
    if threshold <= 0:
        return True  # at least nothing: holds with an empty history
    totals: dict[Handle | None, int] = {}
    for row in rows:
        if not executor.binder._match_node(atom.event, row, ctx.source, ctx.controller):
            continue
        who = _individual(row)
        totals[who] = totals.get(who, 0) + _measure(row)
        if totals[who] >= threshold:
            return True
    return False


def _individual(row: GameEvent) -> Handle | None:
    """Whom a turn-history row happened to or was done by, for a threshold: the
    player who gained or lost the life, the player or object dealt the damage
    (its recipient, never its dealer), the player who drew the card or cast the
    spell. Other rows name no one and count together ("three or more creatures
    died this turn")."""
    from MTG_bot.core.executor.events import (
        KIND_CARD_DRAWN,
        KIND_CAST,
        KIND_DAMAGE,
        KIND_LIFE_GAINED,
        KIND_LIFE_LOST,
    )

    if row.kind in (KIND_LIFE_GAINED, KIND_LIFE_LOST, KIND_DAMAGE):
        return row.subject
    if row.kind == KIND_CARD_DRAWN:
        return row.draw[0]
    if row.kind == KIND_CAST:
        return row.cast[0]
    return None


def _measure(row: GameEvent) -> int:
    """How much one row adds to a turn-history count: its amount for life and
    damage rows ("lost 4 or more life"), its number of counters for a counter
    row, else 1 (one card drawn, one spell)."""
    from MTG_bot.core.executor.events import (
        KIND_COUNTER_PLACED,
        KIND_DAMAGE,
        KIND_LIFE_GAINED,
        KIND_LIFE_LOST,
    )

    if row.kind in (KIND_LIFE_GAINED, KIND_LIFE_LOST, KIND_DAMAGE):
        return row.amount
    if row.kind == KIND_COUNTER_PLACED:
        return row.counter[1]
    return 1
