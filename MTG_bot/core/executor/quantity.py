"""Quantity resolution + the minimal Filter evaluator (round 12a, /06 §12a).

The completeness boundary is deliberate: this resolves what the v1 verbs
need and raises ``NotImplementedError`` naming the node for everything
else — the flag-don't-degrade North Star. ``QX`` needs the cost context
(12c), ``QThisTurn``/event-field ``QProp`` need the trigger event register
(12b), and the full Filter vocab is 12c's gate.

Conventions honoured:
  * **C17** — ``QAtMost(n)`` resolves to its ceiling ``n`` here; the LEGAL
    designation range is 1..n and the *executor* clamps the resolution to
    the 0..n handles actually available (pinned in verbs/selector code).
  * **C12** — QProp referents are the closed structured strings, never
    English substrings.
  * Determinism — every handle list this module produces is Handle-sorted
    unless it is a designated order-preserving slot (zone order).
"""

from __future__ import annotations

import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final, Union

if TYPE_CHECKING:  # pragma: no cover - typing-only, dodges runtime cycles
    from MTG_bot.core.executor import Executor
    from MTG_bot.core.executor.events import EventJournal
    from MTG_bot.core.executor.layers import LayerRegistry
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
    ThisTurnKind,
    ZonePosition,
)
from MTG_bot.core.executor.decisions import DecisionStream
from MTG_bot.core.executor.durations_min import DurationLedger
from MTG_bot.core.executor.events import GameEvent
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

    ``decisions`` is the explicit per-op POOL consumed in ask order via
    :meth:`take_decision`; the 14b ``stream`` adds the vocabulary-addressed
    lanes that need no pre-enumeration (B-4). C15 throughout: every
    decision is enumerable and explicit — the executor holds no hidden
    randomness and no hidden choice.
    """

    world: GameWorld
    ledger: DurationLedger
    controller: Handle
    source: Handle
    bindings: dict[str, Binding]
    decisions: Sequence[str]
    decision_idx: int = 0
    # 14b: the executor's vocabulary-addressed stream (B-4 channel). None
    # only in bare unit-test contexts that pass their own decisions pool.
    stream: DecisionStream | None = None
    events: list[tuple[object, ...]] = field(default_factory=list)
    rng: Callable[[str], random.Random] = _default_rng  # executor-owned seeds
    token_counts: dict[str, int] = field(default_factory=dict)
    # 12b event register: the triggering GameEvent (or None outside trigger
    # context) and the damage amount it carried, so QProp("event", AMOUNT)
    # and the event|result referents resolve inside a firing.
    event: object = None
    event_amount: int | None = None
    # r22b (Conclave Mentor): the counter count a CounterPlacedEvent
    # REPLACEMENT is rewriting — the register QProp("event", COUNTER_COUNT)
    # reads INSIDE a counter replacement's action ("that many plus one"),
    # where the card's accumulated counters are the WRONG answer (the
    # event names what is being placed NOW, not what already sits there).
    # None outside the counter-replacement drain — the pre-r22b sum-of-
    # counters reading (Basri's Lieutenant-style "that many") is untouched.
    event_counter_count: int | None = None
    # 12d registries + the owning executor: the runtime layer verbs
    # (GRANT/LOSE_ABILITY, PREVENT_EFFECT) and the damage-replacement
    # interceptor reach them through the ctx; None only in bare unit-test
    # contexts (the handlers raise a clean ValueError if invoked there).
    layers: LayerRegistry | None = None  # executor.layers
    replacements: ReplacementRegistry | None = None  # executor.replacements
    executor: Executor | None = None  # nested replacement effects
    # 14d (B-7): the executor's structured event journal, bound at EVERY
    # ExecCtx construction site — the effect runtime AND the query/legality
    # paths (13a's FLIP_WON "bare-ctx" lesson: a predicate the query must
    # answer cannot live off a register the query does not carry). The
    # journal-is-state ruling (doc 09-30/07): a pure query is a DETERMINISTIC
    # read, not an amnesiac one — the history preds read the same journalled
    # rows the fingerprint dumps (12b dump()), so replay stays byte-identical.
    # None only in bare unit-test contexts; the history-backed preds then
    # raise naming themselves (flag, never guess).
    journal: EventJournal | None = None
    # 13b: the cast's declared X (CR 601.2f — chosen with the total cost).
    # None means UNDECLARED: resolving a QX raises exactly as before (12c's
    # unbound flag), so every pre-13b path is byte-unchanged; cast() binds
    # it from its x parameter, effect-side CASTs default it to 0.
    x_value: int | None = None
    # 14c (B-13): the ONE_OF picks made in THIS resolution — the
    # partition anchors the sibling REST atom subtracts ("put one of them
    # in your hand, the rest into your graveyard"). The re-search idiom
    # usually makes the subtraction a no-op (the picked card already left
    # the zone); it matters for a same-zone split. Seq order pairs the
    # nearest preceding ONE_OF with its REST. T2 k-of-n (doc 30): a TUPLE
    # — a want>1 partition asks k times and REST subtracts EVERY pick;
    # the want==1 lane keeps the old single-element tuple behaviour.
    one_of_picks: tuple[Handle, ...] = ()
    # r19b (See the Truth): the windowed candidate list a library-TOP
    # ONE_OF partition resolved from — the sibling REST atom's population
    # after run_atom has closed the raw look window at the ONE_OF atom's
    # completion. Same lifetime and pairing rule as one_of_picks (Seq order
    # pairs a REST with its nearest preceding ONE_OF).
    one_of_window: tuple[Handle, ...] = ()
    # 12d: damage replacements consume the event and queue their ACTION;
    # the action runs AFTER the consuming atom's journal boundary (one diff
    # per mutation — no double-emitted events). r20b (Containment Priest):
    # a ZONE-CHANGE replacement queues ``(record, moving card)`` so the
    # drain can bind the moving card as ``event`` for the action's
    # referent selector (the die-lane convention) — the damage/life lanes
    # keep bare records and a bindings-less action ctx. r22b (Conclave
    # Mentor): a COUNTER-PLACEMENT replacement queues
    # ``(record, card, kind, count)`` — the drain binds the receiving card
    # as ``event`` AND publishes the placed count into
    # ``event_counter_count`` so the action's "that many plus one" reads
    # the EVENT, not the card's accumulated ledger.
    pending_replacements: list[
        ReplacementRecord
        | tuple[ReplacementRecord, Handle]
        | tuple[ReplacementRecord, Handle, CounterKind, int]
    ] = field(default_factory=list)
    # r19a (Life Goes On): the CR 614.4a loop guard — the seqs of the
    # replacement records that already consumed an event in THIS chain.
    # A replacement's own ACTION runs with the producing record's seq in
    # the set, so the same effect can never re-replace its own replacement
    # (one application per event chain, per event kind).
    replaced_seq: frozenset[int] = frozenset()
    # r19a (Cultivate): a Seq that contains ONE_OF/REST partition
    # MOVE_ZONE siblings searches to DESIGNATE, not to deliver — set by
    # the Seq walker's pre-scan so the SEARCH atom knows its found cards
    # must stay put for the partition atoms to re-find.
    search_partition: bool = False
    # r19b (Track Down / See the Truth): the cards LOOK_AT/REVEAL showed
    # THIS resolution, top-first — the compiler's documented register
    # convention for the following sentence (templates_b5b
    # _build_if_it_type_then: "Conditional whose subject is the previous
    # sentence's revealed card"). run_atom clears it before every verb that
    # is not a look verb, so it survives exactly one sentence: the
    # Conditional's subject rule and the library-TOP partition selectors
    # ("put ONE OF [the looked-at cards] into your hand") read it, and a
    # bare Conditional after any other atom keeps the old ctx.source
    # subject, byte-unchanged. Empty (the default) everywhere else.
    look_window: tuple[Handle, ...] = ()
    # r19c (Rookie Mistake / Hunter's Edge): MULTI-slot spell designation —
    # per-TARGET-selector designations keyed by the Selector's ``repr()``
    # (the same identity key ``spell_target_slots`` dedupes on). None for
    # ordinary single-slot spells, so every pre-19c lane is byte-unchanged;
    # _run_effect's Atom branch shadows ``bindings["target"]`` to the atom's
    # own slot while its verbs run (CR 601.2c: one spell, one designation
    # PER SELECTOR — the shared union binding cannot serve two populations,
    # which is why multi-slot casts stayed loud for two arcs).
    slot_designations: dict[str, tuple[Handle, ...]] | None = None
    # the WHOLE designation (every slot's handles, Handle-sorted): what
    # IS_ANY_TARGET anaphora means at resolution — "another target
    # creature" is decided against ALL designations, never the per-atom
    # shadow alone. None = single-slot spell: the old binding-first read.
    designation_union: tuple[Handle, ...] | None = None
    # r19c (Return to Nature): modes declared at CAST time (CR 601.2b —
    # modes before targets) arrive here as ORDER tokens so the runtime
    # Choose CONSUMES the declaration instead of re-asking for a choice
    # the caster already made. Consumed in ask order; empty elsewhere.
    prechosen_modes: list[str] = field(default_factory=list)

    def take_decision(
        self, vocab: tuple[str, ...], what: str, *, seat: Handle | None = None
    ) -> str:
        """Consume the next decision for THIS demand site; raise when no
        lane can answer (C15: never a default).

        14b lanes, in order (the /03 B-4 ruling, doc ``decisions.py``):

        1. the explicit per-op POOL (``decisions=`` kwarg, ask order) —
           a KNOWN-tree pre-supply, byte-identical to the 12a-14a
           positional behaviour and still vocabulary-validated,
        2. the executor's :class:`~MTG_bot.core.executor.decisions.
        DecisionStream` FIFO primed under this exact ``(vocab, what)``
           key — the enumeration-free lane: an answer queued by the
           policy is picked up whenever the demand arrives, including
           from a trigger the running op itself armed (B-4),
        3. the stream's ask-time PROVIDER — the engine hands the exact
           vocabulary to the external answerer at the moment of demand.

        ``seat`` names the deciding player when it is not this context's
        controller; the provider sees it as ``DecisionStream.asking_seat``.
        No call site passes it today: four tools/training modules replace
        this method process-wide at import with the old ``(self, vocab,
        what)`` signature (packrec, packrec_v2, dagger_rollout_v3,
        puzzle_cert; BACKLOG B-35), so a caller passing ``seat=`` would
        crash whenever one of them is loaded. The scry site therefore relies
        on its controller being the scrying player, and the bench router's
        tag check raises loudly if a card ever breaks that.
        """
        decider = self.controller if seat is None else seat
        if self.decision_idx < len(self.decisions):
            choice = self.decisions[self.decision_idx]
            if choice in vocab:
                self.decision_idx += 1
                if self.stream is not None:
                    self.stream.ask_log.append((what, choice))
                    self.stream.journal.append((what, choice))
                return choice
            # r19c (Duress / Experimental Overload): the next pool word does
            # not answer THIS site — a may-offer cannot eat a card name, a
            # candidate-index ask cannot eat a pack key. A mismatched word
            # is NOT consumed: it stays in the pool for the site it was
            # scripted for, and THIS site falls through to the stream /
            # provider lanes, which answer from the vocabulary itself.
            # Green packs are byte-unchanged (their pool words always
            # matched); when no stream lane can answer, the ORIGINAL
            # raise shape is preserved (test_executor_games pins it).
            if self.stream is not None:
                try:
                    return self.stream.take(vocab, what, seat=decider)
                except ValueError:
                    pass
            raise ValueError(f"executor: {what} decision {choice!r} not in {vocab}")
        if self.stream is not None:
            return self.stream.take(vocab, what, seat=decider)
        raise ValueError(
            f"executor: {what} needs a decision from {vocab}, "
            f"got only {len(self.decisions)} supplied"
        )

    def binding_handles(self, role: str) -> list[Handle] | None:
        """The caller-supplied handles for a role, Handle-sorted (ruling 5)."""
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


def resolve(quantity: Quantity, ctx: ExecCtx) -> int:
    """Quantity IR -> a non-negative int, for the v1 subset.

    Raises ``NotImplementedError`` for nodes whose context 12b/12c own
    (QX cost values, QThisTurn turn ledgers, event-field QProps) — never a
    silent default.
    """
    if isinstance(quantity, QConst):
        return quantity.value
    if isinstance(quantity, QAtMost):
        # C17: resolve reports the ceiling; callers clamp to what is
        # actually available (0..n) before acting.
        return quantity.n
    if isinstance(quantity, QAtLeast):
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
                # T5-D (Peer into the Abyss "Round up each time.", CR 107.1a):
                # ceiling division; FLOOR/NONE/None keep the standing floor.
                return -(-left // right)
            return left // right
        if quantity.op is QBinOp.MAX:
            return max(left, right)
        if quantity.op is QBinOp.MIN:
            return min(left, right)
        raise NotImplementedError(f"executor: QBin op {quantity.op.name}")
    if isinstance(quantity, QCount):
        from MTG_bot.core.executor.selectors import (
            resolve_selector,
        )  # cycle-free at call time

        return len(resolve_selector(quantity.selector, ctx))
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

        # ZND-3 G1 (spec KNOWLEDGE/2026-10-18/107): party size = the
        # number of DISTINCT party classes PRESENT among the selector's
        # objects, at most one per class — world-canonical semantics are
        # ZNR.json's printed reminder text "Your party consists of up to
        # one each of Cleric, Rogue, Warrior, and Wizard" (/92 law: read
        # from the data file, not world-memory). Two Clerics + one Wizard
        # = 2, never 3. The class test reads the LIVE type oracle —
        # printed type line ∪ GRANT_TYPE overlay, the same single oracle
        # the SUBTYPE_EQ lane uses below — so class grants MOVE the
        # census (§11: board interaction is engine-side). len() of a
        # subset of the fixed 4-set caps 0..4 by construction.
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
        # 13b: the X binding — declared by cast(x=...) via ExecCtx.x_value
        # (CR 601.2f). Undeclared X stays the 12c flag, never a guess.
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
        # M21 fuzz S2 (seed 384, /109 addendum): the 12b turn ledger now
        # carries NONCOMBAT_DAMAGE — Chandra's Incinerator's cost reducer
        # ("This spell costs {X} less to cast, where X is the total amount
        # of noncombat damage dealt to your opponents this turn", compiled
        # by templates_b4 as QThisTurn(NONCOMBAT_DAMAGE, ALL_OPPONENTS)).
        # The datum EXISTS in the journal (events.py DAMAGE rows: data is
        # ``(amount,)``, or ``(amount, True)`` for COMBAT damage — the 16c
        # combat-scope flag), so this is an implementation, not a refusal.
        # Reading: sum the turn window's noncombat DAMAGE rows whose
        # SUBJECT is a seat of the referent side. A planeswalker-recipient
        # row never counts: "damage dealt to your opponents" names the
        # PLAYER receiving it (CR 118.5 — damage to a planeswalker is not
        # damage to that player), and the row's subject is the actual
        # recipient, so the seat filter is the CR-correct scope. The
        # window is the same journal-backed ``turn_window()`` every 14d
        # history predicate answers against (query/runtime identity: the
        # legality lane reads the identical rows the effect lane does).
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
    """Public alias of the closed C12 referent resolver (12d: the verbs
    resolve a DurationUntilLeaves anchor through the SAME machinery the
    QProps use — one referent semantics, no second parser)."""
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
    # 12b: the trigger firing bound the event subject / C18 result subject.
    if referent in ("event", "result"):
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


def _prop_value(field: QPropField, handle: Handle, ctx: ExecCtx) -> int:
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
        # r24a (2026-10-02): the life-TOTAL operand the C3 roadmap correction
        # named — "loses half their life. Round up" (Peer into the Abyss) has
        # no zone to count, so QCount could never carry it and C3 STOPPED the
        # card. This lane is the engine half of that split: the same twin
        # convention as the CARDS_IN_* fields above (referent "controller",
        # validated in QProp.__post_init__ — a referent mismatch raises there,
        # never silently re-scopes), and a direct order-free attribute read —
        # the determinism contract the zone-count twins keep. The future
        # compiler emit reads LOSE_LIFE(amount=QBin((QProp(controller, LIFE)
        # + 1) DIV 2)) through here; the frozen Peer golden carries no
        # LOSE_LIFE atom yet, so the print-still-drops-the-clause witness is
        # the promoted pack's documented deviation, and THIS lane is pinned
        # end-to-end in test_executor_r24a.
        return ctx.world.players[handle].life
    if field is QPropField.COUNTER_COUNT:
        # r22b (Conclave Mentor): inside a counter placement's replacement
        # action, "that many" names the count the EVENT is placing (the
        # drain publishes it), not the card's whole counter sum. Outside
        # the replacement drain the register is None and the pre-r22b
        # accumulated reading stands byte-unchanged.
        if ctx.event_counter_count is not None:
            return ctx.event_counter_count
        return sum(ctx.world.cards[handle].counters.values())
    if field is QPropField.AMOUNT:
        # The triggering event's damage amount (Brash Taunter) — 12b register.
        if ctx.event_amount is None:
            raise NotImplementedError(
                "executor: QProp AMOUNT needs a triggering damage event "
                "(fired from a DamageDealtEvent)"
            )
        return ctx.event_amount
    if field is QPropField.THIS_WAY_COUNT:
        # 16b (Siege Striker's attack trigger: "+1/+1 for each creature
        # tapped this way"): the count of creatures the SAME effect
        # execution's last TAP atom tapped — the per-resolution register
        # the 14e anaphora uses (fresh bindings dict per effect run), so
        # an Optional-wrapped tap that DECLINED leaves the register
        # absent and the magnitude 0, CR-correct with the answer given.
        # (Handle argument unused: "this way" counts an action, not a
        # permanent's property.)
        reg = ctx.bindings.get("tapped_this_way")
        return len(reg) if isinstance(reg, (list, tuple)) else 0
    if field is QPropField.THAT_MANY_COUNT:
        # Grammar round 7 (R7) "then do that many": the count of objects
        # the PRECEDING producer atom acted on in THIS resolution — the
        # 14e ``result`` register is the engine's own record of that set
        # (TAP/UNTAP/PUT_COUNTER/MOVE_ZONE/SEARCH/CHOOSE write it; DISCARD
        # joined in 18b for Kinetic Augur's "discard …, then draw that
        # many"). Handle argument unused, the THIS_WAY_COUNT sibling. An
        # UNSET register RAISES (16b made THIS_WAY's absence the benign 0
        # because a declined may legitimately leaves it unwritten — but
        # "that many" has no zero-reading: the compiler only places it in
        # a mandatory continuation, so a missing antecedent is a missing
        # question, the established flag-never-guess rule).
        handles = ctx.binding_handles("result")
        if handles is None:
            # r21b (Basri Ket's -2): the trigger-antecedent reading. When
            # the "that many" rides a DECLARE_ATTACKERS-triggered effect
            # there IS no preceding producer atom — the DECLARATION itself
            # is the antecedent set, and 21b's _fire records the whole
            # declaration group under this register. The ``result``
            # register keeps strict precedence (Kinetic Augur stays on the
            # producer path); this fallback only answers when it is absent.
            handles = ctx.binding_handles("declare_attackers")
        if handles is None:
            raise NotImplementedError(
                "executor: THAT_MANY_COUNT has no producer register — no "
                "preceding atom wrote the result register in this resolution"
            )
        return len(handles)
    raise NotImplementedError(
        f"executor: QProp field {field.name} not implemented (12c query surface)"
    )


def _resolve_prop(prop: QProp, ctx: ExecCtx) -> int:
    from MTG_bot.core.executor.selectors import (  # cycle-free at call time
        resolve_selector,
    )

    if isinstance(prop.referent, str):
        return _prop_value(prop.field, _referent_handle(prop.referent, ctx), ctx)
    # M21 fuzz S3 (seed 490, /109 addendum): Carrion Grub's static — "gets
    # +X/+0, where X is the greatest power among creature cards in your
    # graveyard" — aggregates QProp(POWER, graveyard-selector, MAX), and
    # the graveyard held a Kinetic Augur: P/T printed "*4", whose CDA the
    # engine does not model, so its identity power is UNDEFINED (the /99
    # shape-gap family: ZNR's Nighthawk Scavenger "1+*", /99). The scalar
    # read of an undefined property stays the strict ValueError above
    # (unresolvable named quantity — never a zero, per CR an object
    # without a P/T characteristic has NO power); but an AGGREGATION over
    # a selector is a read over a population, and CR keeps an undefined
    # characteristic out of the value set: an object with no power is not
    # one of the "powers among" being maxed/summed — the same
    # characteristic-absent rule that makes the POWER_LE/POWER_GE filters
    # read False for such an object. Skipping keeps the MAX honest about
    # what the engine can see (the Augur's true CDA power is a registered
    # coverage gap, not a number to guess); an all-undefined population
    # falls to the established empty-set 0 below.
    aggregate_pt = isinstance(prop.referent, Selector) and prop.field in (
        QPropField.POWER,
        QPropField.TOUGHNESS,
    )
    values = []
    for handle in resolve_selector(prop.referent, ctx):
        if aggregate_pt:
            power, toughness = ctx.effective_pt(handle)
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

# ZND-3 (spec KNOWLEDGE/2026-10-18/107): the four party classes. WORLD-
# CANONICAL (/92 law) — MTG_bot/data/ZNR.json prints on every party card:
# "Your party consists of up to one each of Cleric, Rogue, Warrior, and
# Wizard." The set is the party cap itself: party size = |present ∩ this
# set| ∈ 0..4, one per class.
PARTY_CLASSES: Final[frozenset[str]] = frozenset(
    {"Cleric", "Rogue", "Warrior", "Wizard"}
)


# r19a (IS_PERMANENT): the CR 110.1 permanent card types — a card whose
# type line names one of these is a permanent wherever it currently sits
# (library, stack, graveyard, exile included).
_PERMANENT_TYPE_WORDS = frozenset(
    {"Artifact", "Creature", "Enchantment", "Land", "Planeswalker", "Battle"}
)


def _type_line_tokens(identity_text: str) -> list[str]:
    """Split a printed type line into its type/subtype words, keeping the
    subtype group's card names intact (data-only, C12: no oracle text is
    parsed anywhere)."""
    text = identity_text
    for sep in _TYPE_LINE_SEPARATORS:
        text = text.replace(sep, " ")
    return [t for t in text.split() if t]


def eval_filter(filter_: Filter, handle: Handle, ctx: ExecCtx) -> bool:
    """Match one handle against a Filter IR node — the *minimal* evaluator.

    The v1 vocab: TYPE_EQ, SUBTYPE_EQ, NAME_EQ, POWER_LE, PT_LE, IS_TAPPED,
    IS_UNTAPPED, IS_SOURCE, IS_PERMANENT, CONTROLLER_IS, HAS_COUNTER, and
    the boolean nodes FAnd/FOr/FNot. (The mission's "ZONE_IN" has no
    ``FAtomPred`` member in the frozen grammar; IS_PERMANENT is the
    closed-grammar stand-in for "is on the battlefield".) 13a adds
    SUPERTYPE_EQ (printed type-line words) and FLIP_WON (the executor's flip
    ledger); 13c adds NAME_CONTAINS, IS_ATTACHED_TO_SOURCE (the executor
    attachment table) and makes the TYPE_EQ family read the live
    GRANT_TYPE overlay. 14d (B-7) adds the query-legal families that were
    the games' dominant headwall: the world count CONTROLLER_COUNT_GE, and
    the JOURNAL-BACKED history preds MOVED_TO_ZONE_THIS_TURN,
    ENTERED_THIS_TURN_FROM, CAST_THIS_TURN_FROM, DIED_THIS_TURN (C18 row)
    and IS_EXILED_WITH_SOURCE — answered from the executor's journalled
    rows at EVERY eval entry point (runtime, legality, query, layer,
    trigger gate), because the journal is state (purity = determinism,
    not amnesia; doc 09-30/07). 14e adds the WORLD-evaluable twins the 14d
    wall named: POWER_GE (the live-P/T family — Legion's Judgment line) and
    CMC_LE (the identity-mana-value family — Eliminate/Idol/Ugin, QX-capable
    off     the cast's declared X). 14f adds KEYWORD_HAS (the live-keyword oracle:
    printed ∪ granted − lost through the layer registry — Run Afoul's
    target filter, Portcullis Vine's cost gate, the Tide Skimmer family).
    Every other predicate raises
    ``NotImplementedError`` naming itself: its completeness is 12c's gate,
    and an unsupported pred is flagged, never guessed.
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
        # 12d (Frost Breath s2 / Selfless Savior anaphora): the object is
        # one of the ability's designated targets — the closed C12 reading,
        # judged against the call's target bindings. r19c: on a MULTI-slot
        # spell the per-atom "target" shadow (ExecCtx.slot_designations)
        # would shrink "any target" to one slot; the spell-wide union is
        # the designation and means ANY of them.
        if ctx.designation_union is not None:
            return handle in ctx.designation_union
        bound = ctx.binding_handles("target")
        return bound is not None and handle in bound
    if pred is FAtomPred.TARGETS_SOURCE:
        # r23a (Pursued Whale, CR 601.2f cost fold): "Spells your opponents
        # cast that target this creature cost {3} more to cast." The filter
        # asks whether the JUDGED object — the casting spell in the fold's
        # coordinates (legality.py builds mod_ctx with source=the modifier's
        # host and copies the cast ctx's target bindings) — designated the
        # filter's SOURCE (the static's host) among its targets. Before the
        # 601.2d target declaration there is no designation at all, so the
        # pre-target cost enumeration conservatively reads False and the
        # printed cost shows; the honest +3 lands at PAYMENT, where
        # stack.cast has already journaled bindings["target"] (the fold
        # re-runs there). This is the exact mirror of IS_ANY_TARGET: that
        # pred asks "object ∈ my targets", this asks "source ∈ judge's
        # targets", judged in the host's coordinates.
        if ctx.designation_union is not None:
            return ctx.source in ctx.designation_union
        bound = ctx.binding_handles("target")
        return bound is not None and ctx.source in bound
    if pred is FAtomPred.IS_TAPPED:
        return world.cards[handle].tapped
    if pred is FAtomPred.IS_UNTAPPED:
        return not world.cards[handle].tapped
    if pred is FAtomPred.IS_PERMANENT:
        # r19a (Fungal Rebirth): CR 110.1 — a permanent is a CARD THAT HAS A
        # PERMANENT CARD TYPE, not "a card sitting on the battlefield". The
        # zone reading silently misjudged every gate asked OFF the
        # battlefield: Fungal Rebirth's graveyard test ("creature card in a
        # graveyard") and Unsubstantiate's spell-on-the-stack target both
        # answer about the card, and answered wrong. The type-line test is
        # zone-independent; on the battlefield it agrees with the old zone
        # reading for every permanent (and non-permanent) there, so the
        # green lanes are unchanged.
        if handle not in world.cards:
            return False
        words = set(_type_line_tokens(world.cards[handle].identity.type_line))
        return bool(words & _PERMANENT_TYPE_WORDS)
    if pred is FAtomPred.IS_TOKEN:
        # "nontoken creature that died" — printed token-ness (identity data,
        # survives death; added for real 12b dies triggers).
        return world.cards[handle].identity.is_token
    if pred in (FAtomPred.TYPE_EQ, FAtomPred.SUBTYPE_EQ, FAtomPred.SUPERTYPE_EQ):
        # 13a: supertypes join the type-word match. The frozen identity has
        # no ``supertypes`` field, but every supertype ("Basic", "Legend",
        # "Snow") is PRINTED in the type line, so the data-only word test
        # that TYPE_EQ/SUBTYPE_EQ already use is the honest reading (C12:
        # no oracle text is parsed). 13c: live GRANT_TYPE layers UNION
        # their overlay words in ("is a Knight in addition to its other
        # types") — the layer registry is the single type oracle.
        assert atom.string_value is not None
        if handle not in world.cards:
            return False
        words = set(_type_line_tokens(world.cards[handle].identity.type_line))
        if ctx.layers is not None:
            words.update(ctx.layers.type_overlay(handle))
        return atom.string_value in words
    if pred is FAtomPred.NAME_CONTAINS:
        # 13c (Teferi's "a Teferi planeswalker" shape gate): case-sensitive
        # substring on the printed name — the grammar's NAME_EQ twin. The
        # corpus gate word ("Teferi") is a proper noun matching the printed
        # capitalization; NAME_CHOSEN's unanswered-question convention does
        # not apply (this is pure identity data, no question to answer).
        assert atom.string_value is not None
        if handle not in world.cards:
            return False
        return atom.string_value in world.cards[handle].identity.name
    if pred is FAtomPred.IS_ATTACHED_TO_SOURCE:
        # 13c (Malefic Scythe's "equipped creature", Dub's compiled aura
        # shape): the world has NO attachment state (the frozen CardState
        # has no aura/equipment fields), so the answer is the EXECUTOR's
        # attachment table — an AURA/EQUIPMENT -> HOST map maintained by
        # ``executor.attach_aura`` and dropped on zone change. A bare
        # ExecCtx has no table: flagged, never guessed.
        if ctx.executor is None:
            raise ValueError(
                "executor: IS_ATTACHED_TO_SOURCE needs an executor-backed "
                "ExecCtx (bare ExecCtx has no attachment table)"
            )
        if ctx.executor.attachments.get(ctx.source) == handle:
            return True
        # r20c (Malefic Scythe): the ZONE_CHANGE row lands before the
        # CREATURE_DIES row of the same diff sweep, and the binder's
        # leave-detach has already pruned the live table when a dies-
        # trigger's filter is judged. Once the judged object has LEFT the
        # battlefield, the live table can no longer speak for it — the
        # object's own departure-time snapshot (executor.detach_lki) is
        # its last known information (CR 400.7 doctrine). On the
        # battlefield the live table stays the only word.
        if handle in world.cards and world.zone_of(handle).kind == ZONE_BATTLEFIELD:
            return False
        return ctx.source in ctx.executor.detach_lki.get(handle, ())
    if pred is FAtomPred.IS_ATTACHED_TO:
        # r19b (Turn to Slag, grammar round 7's R7-1): "attached to the
        # REFERENT object" — the same attachment-table answer as
        # IS_ATTACHED_TO_SOURCE, but the host arrives through the closed
        # _QPROP_STR_REFERENTS anaphora instead of the hardcoded source.
        # Direction of the lookup: ``table[the object] == host`` — the
        # attachment is the KEY, the host the VALUE, which is exactly how
        # attach_aura WRITES the table (attachments[aura] = host) and how
        # the leave-detach sweep reads it (attachments.pop(card)). NOTE
        # the 13c SOURCE twin above asks the mirrored shape
        # (table[source] == handle); empirically the locked lanes
        # (test_detach_on_leave, the aura-scope enumerate_candidates at
        # legality.py:445) each require their own orientation, so this
        # pred follows the WRITE direction — verified against the real
        # attach edge (Turn to Slag) without touching the twin.
        # The resolution mirrors
        # resolve_selector's referent lane (selectors.py): source and
        # controller are coordinates, "target" is the one designation
        # (CR 601.2c), anything else is a binding under that name. A
        # missing/ambiguous referent and a bare ExecCtx are flagged,
        # never guessed (flag-not-degrade).
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
        # 13b (the cast-trigger feed reads these over SPELL cards): COLOR_IN
        # is the grammar's SUBSET reading ("colours are a non-empty subset
        # of the given set"), COLOR_HAS the single-colour membership
        # ("hexproof from black"; a spell "that's white or blue" is the FOr
        # of COLOR_HAS, CR 105.2 — V39 moved Quirion Dryad off COLOR_IN,
        # which no compiled card writes now). Identity data — works for a
        # card in any zone, incl. the stack.
        if handle.namespace != "card":
            return False
        card_colors = set(world.cards[handle].identity.colors)
        if pred is FAtomPred.COLOR_HAS:
            assert atom.color is not None
            return atom.color in card_colors
        assert atom.colors  # FAtom validation: COLOR_IN requires non-empty
        return bool(card_colors) and card_colors <= set(atom.colors)
    if pred is FAtomPred.COLOR_COUNT_GE:
        # r23a (the games' last crash class): "protection from multicolored"
        # (Basri's Lieutenant, count=2, read by block_pair_blocked_reason as
        # a blocker-quality filter over the attacker) and Ugin's "-X: exile
        # each permanent ... that's one or more colors" (count=1, inside the
        # effect selector's FAnd). The subject simply has COUNT or more
        # colors (CR 901.3's color-count test; the grammar's own doc line).
        # Same identity data as the COLOR_HAS/COLOR_IN twin above — the
        # engine carries no color-changing continuous effects (layers.py
        # never writes color), so an object's printed colors ARE its colors
        # in every zone.
        if handle.namespace != "card":
            return False
        assert atom.count is not None  # FAtom: count is a required slot
        threshold = resolve(atom.count, ctx)
        return len(world.cards[handle].identity.colors) >= threshold
    if pred is FAtomPred.NAME_CHOSEN:
        # 13b (Runed Halo): the object's name is the one the SOURCE's
        # CHOOSE_NAME atom recorded (grammar round 7's write/read pair).
        # No record is an UNANSWERED question — flagged, never "False",
        # the FLIP_WON convention.
        ex = ctx.executor
        if ex is None or ctx.source not in ex.name_choices:
            raise NotImplementedError(
                "executor: NAME_CHOSEN needs a CHOOSE_NAME record for the "
                f"source {ctx.source} (no name chosen yet)"
            )
        if handle.namespace != "card":
            return False
        return world.cards[handle].identity.name == ex.name_choices[ctx.source]
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
        # 14e: the GE twin of POWER_LE the games demanded (Legion's Judgment
        # "destroy target creature with power 4 or greater"; Turret Ogre's /
        # Drowsing Tyrannodon's gates, 2-3 crashes in every 14d pool). The
        # SAME live-P/T read as POWER_LE — layers folded — so a buffed
        # creature crosses the threshold honestly. A card with no power
        # (land, instant) is not "a creature with power 4 or greater":
        # characteristic absent, pred False, the POWER_LE convention.
        assert atom.count is not None
        threshold = resolve(atom.count, ctx)
        power, _toughness = ctx.effective_pt(handle)
        if power is None:
            return False
        return power >= threshold
    if pred is FAtomPred.CMC_LE:
        # 14e: "converted mana cost X or less" (Eliminate's target filter,
        # Idol of Endurance, Ugin's QX twin — QX rides the cast's declared X
        # like every other quantity, 14c CR 601.2f). IDENTITY data, read
        # exactly the way the QProp CMC/MANA_VALUE field already reads it
        # (``_prop_value``: a missing cmc — synthetic tokens — is mana
        # value 0, the CR truth for tokens and the executor's established
        # convention; not an invention of this pred).
        assert atom.count is not None
        threshold = resolve(atom.count, ctx)
        if handle.namespace != "card":
            return False
        return (world.cards[handle].identity.cmc or 0) <= threshold
    if pred is FAtomPred.CMC_GE:
        # 18b query-lane parity: the GE twin of CMC_LE (14e), the SAME
        # identity read (a missing cmc — synthetic tokens — is mana value
        # 0, the established convention). Fierce Empath's "reveals a
        # creature with converted mana cost 6 or greater" search filter;
        # one evaluator answers the query lane (enumerate_candidates) and
        # the runtime lane alike — the parity test pins they cannot drift.
        assert atom.count is not None
        threshold = resolve(atom.count, ctx)
        if handle.namespace != "card":
            return False
        return (world.cards[handle].identity.cmc or 0) >= threshold
    if pred is FAtomPred.KEYWORD_HAS:
        # 14f (B-21): "with <keyword>" introspection — the games demanded
        # it from BOTH surfaces the frozen grammar places it in: a selector
        # filter (Run Afoul's "sacrifices a creature of their choice with
        # flying" CHOOSE pool) and gate positions (Tide Skimmer / Snarespinner
        # trigger filters+conditions, Portcullis Vine's cost-target gate,
        # Lofty Denial's / Watcher of the Spheres' cost-modifier conditions).
        # The answer is the LAYER REGISTRY's live keyword oracle — printed
        # identity keywords ∪ live grants − live losses, rebuilt at every
        # settle (the 12d anthem oracle combat legality already calls). A
        # bare ExecCtx has no registry: flagged, never a printed-only guess
        # that would silently miss a granted or stripped keyword (the
        # IS_ATTACHED_TO_SOURCE convention). A handle outside the card set
        # (a player seat) has no keywords — characteristic absent, False.
        assert atom.keyword is not None
        if handle.namespace != "card" or handle not in world.cards:
            return False
        if ctx.layers is None:
            raise NotImplementedError(
                "executor: filter pred KEYWORD_HAS needs the layer "
                "registry for the live keyword oracle (bare ExecCtx has none)"
            )
        return ctx.layers.keyword_of(handle, atom.keyword)
    if pred is FAtomPred.HAS_COUNTER:
        # M21 fuzz S1 (seeds 27/95/239/274/412, /109 addendum): the assert
        # used to KILL the game when the atom's count slot arrived unbound.
        # The producing shape is the Tempered Veteran fold — "put a +1/+1
        # counter on target creature WITH a +1/+1 counter on it" compiles
        # (via the target-phrase template) to HAS_COUNTER(counter_kind=
        # PLUS_1_PLUS_1, count=None): _FATOM_RULES marks count required,
        # but FAtom.__post_init__'s required-slot enforcement list omits
        # "count", so the shape validates and reaches BOTH lanes (the 12c
        # query surface through enumerate_candidates — the fuzz crash —
        # and the runtime gate). Honest readings, by slot:
        #   * counter_kind unbound — "has a counter" without naming WHICH
        #     counter is not answerable from the world: typed, named
        #     refusal (the /112 flag-don't-degrade convention; the grammar
        #     enforces this slot, so the branch is defensive for hand-
        #     built atoms, never a silent pass).
        #   * count unbound — the existence reading the pred's own name
        #     states: "with a {kind} counter on it" ⇔ count >= 1. This is
        #     NOT the phantom-counter zero-default: a threshold of 0 makes
        #     the pred vacuously True for every object (every creature
        #     would be a legal Tempered Veteran target — the trap); 1 is
        #     the text's meaning, zone-true for every consumer of the
        #     "with a K counter" phrase. A BOUND count resolves through
        #     the ordinary quantity lane (its own refusals propagate).
        if atom.counter_kind is None:
            raise NotImplementedError(
                "executor: filter pred HAS_COUNTER has no bound counter_kind "
                "(12c query surface — which counter is asked for?)"
            )
        if handle.namespace != "card" or handle not in world.cards:
            return False  # characteristic absent (the KEYWORD_HAS convention)
        threshold = 1 if atom.count is None else resolve(atom.count, ctx)
        return world.cards[handle].counters.get(atom.counter_kind.name, 0) >= threshold
    if pred is FAtomPred.CONTROLLER_IS:
        who = atom.who
        if who is None:
            return False
        from MTG_bot.core.executor.selectors import controller_matches, controller_of

        if handle.namespace != "card":
            # 16b: a PLAYER handle answers for ITSELF — the 16b attacked-
            # side filters ("two or more ... attacking YOU and/or
            # planeswalkers you control", Mangara R10-3) read CONTROLLER_IS
            # YOU off the attack record, whose object is a seat for
            # player-attacks. A player controls themself: the same
            # coordinate oracle the players_for_ref channels use.
            if handle.namespace == "player":
                return controller_matches(who, handle, ctx)
            return False
        actual = controller_of(ctx, handle)
        return controller_matches(who, actual, ctx)
    if pred is FAtomPred.OPPONENT_OF:
        # r25 (grammar round 11, R11-1): the DESTINATION identity pred —
        # the subject must BE a player on the far side of ``who``. The
        # two-seat harness answer mirrors controller_matches' OPPONENT
        # row: a player that is not ``who``'s side is an opponent. A
        # CARD subject is honestly FALSE (CR 109.5 — a permanent is not
        # a player): the pyreling negative, damage to an opponent's
        # creature never satisfies "to an opponent".
        if handle.namespace != "player":
            return False
        from MTG_bot.core.executor.selectors import (
            controller_of,
            players_for_ref,
            resolve_selector,
        )

        who = atom.who
        if who is None:
            return False
        if isinstance(who, Selector):
            side = [
                c if c.namespace == "player" else controller_of(ctx, c)
                for c in resolve_selector(who, ctx)
            ]
        else:
            side = players_for_ref(who, ctx)
        return handle not in side
    if pred is FAtomPred.NOT_FIRST_DRAW_THIS_STEP:
        # r22b (Teferi's Ageless Insight, grammar R5-4): "not the first
        # card who draws in their draw step". A PLAYER-coordinate pred —
        # the drawn card (the CardDrawnEvent subject) is not inspected;
        # the ``who`` seat answers it off the executor's draw-step
        # tracker (set by Executor._turn_draw, advanced by every APPLIED
        # draw the verb lane makes). Outside a draw step every draw is
        # vacuously "not the first of the step" — the exclusion names a
        # step, and no step is open.
        from MTG_bot.core.executor.selectors import players_for_ref

        if atom.who is None:
            return False
        if isinstance(atom.who, Selector):
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
        if not getattr(ex, "_draw_step_open", False):
            return True
        return ex.draw_step_ordinal.get(seats[0], 0) > 0
    if pred is FAtomPred.FLIP_WON:
        # 13a (Tavern Swindler compiles the flip and its winner-gate to two
        # rows, so the predicate runs in a SEPARATE context from the
        # FLIP_COIN atom): the answer is the executor's flip ledger. No
        # ledger at all (a bare ExecCtx) or no flip recorded yet is flagged,
        # never guessed as "lost" — the conditional has no antecedent.
        if ctx.executor is None or ctx.executor.last_flip_won_by is None:
            raise NotImplementedError(
                "executor: FLIP_WON needs an executor flip ledger with a "
                "recorded FLIP_COIN (bare ExecCtx / no flip yet)"
            )
        assert atom.who is not None
        from MTG_bot.core.executor.selectors import controller_matches

        return controller_matches(atom.who, ctx.executor.last_flip_won_by, ctx)
    if pred is FAtomPred.MAY_DONE:
        # r18a (CR 611.1): "do X. If you do, Y" — Y executes iff the OPTIONAL
        # X actually executed. The answer is the 14b decision channel's own
        # audit row: the may-offer at THIS ability's site (``may:<source>``,
        # the tag Executor._run_effect asks with) was answered 'fire'. The
        # guard CONSUMES the logged outcome (DecisionStream.ask_log ==
        # ``answered()``) — it never re-asks (the question was answered once,
        # tree order, C15). Handle-free like FLIP_WON: the same answer for
        # every candidate the filter gates. No record at the site is an
        # UNANSWERED QUESTION — flagged, never guessed False (the FLIP_WON /
        # NAME_CHOSEN convention), because a MAY_DONE Conditional only ever
        # rides the seam directly after its own may-offer.
        ex = ctx.executor
        if ex is None:
            raise NotImplementedError(
                "executor: MAY_DONE needs the executor's decision channel "
                "(bare ExecCtx has no may-offer log)"
            )
        # T5-F1: the site tag carries the per-site offer digest
        # (``may:<source>:<digest>``) and a FORCED offer (query-narrowed
        # skip-only) is auto-picked into the JOURNAL, never asked into
        # ask_log — so the guard reads the journal (asked + auto-picked,
        # occurrence order), prefix-matching the site. The ask_log pass is
        # the patched-lane legacy mirror (puzzle_cert/dagger append there
        # without a journal row); consulted only when the journal holds
        # nothing for the site.
        site = f"may:{ctx.source}"

        def at_site(what: str) -> bool:
            return what == site or what.startswith(f"{site}:")

        for log in (ex.decisions.journal, ex.decisions.ask_log):
            for what, answer in reversed(log):
                if at_site(what):
                    return answer == "fire"
        raise NotImplementedError(
            f"executor: MAY_DONE has no may-offer record for {site} — the "
            "conditional has no antecedent (unanswered question, flagged "
            "never False)"
        )
    if pred is FAtomPred.CONTROLLER_COUNT_GE:
        # 14d (B-7): "you control four or more <inner>" (Gadrak's attack
        # gate; the Fabled Passage "Then if you control four or more lands,
        # untap that land." tail). A WORLD count, not history: the same
        # battlefield population the CONTROLLER_IS reading defines, under
        # ctx.controller (the vocab has no who slot — YOU is the ability
        # controller). Handle-free like FLIP_WON: the same answer for every
        # candidate the filter gates, and it judges a sacrificed source
        # correctly (Fabled Passage is already in the graveyard here).
        assert atom.count is not None
        threshold = resolve(atom.count, ctx)
        from MTG_bot.core.executor.selectors import controller_of

        counted = 0
        for card in sorted(world.cards):
            if (
                world.zone_of(card).kind == ZONE_BATTLEFIELD
                and controller_of(ctx, card) == ctx.controller
                and (
                    atom.inner_filter is None
                    or eval_filter(atom.inner_filter, card, ctx)
                )
            ):
                counted += 1
                if counted >= threshold:
                    return True
        return counted >= threshold
    if pred is FAtomPred.CONTROLLER_COUNT_GT:
        # r21b (Garruk, Unleashed's -2, grammar round 8 R8-9): the DUAL-
        # filter population comparison "if an opponent controls more
        # <inner_filter> than you <right_inner_filter>". The two sides
        # carry their OWN CONTROLLER_IS atoms (the compiled Garruk atom:
        # inner = Creature AND CONTROLLER_IS OPPONENT, right_inner =
        # Creature AND CONTROLLER_IS YOU), so each side's count is just
        # its filter over the battlefield population — the same handle-
        # free WORLD count the GE sibling defines, and the pack's
        # printed direction is the ground truth (an opponent's 3 Thrulls
        # over your new Beast → TRUE, loyalty counter). Two-player
        # reading: any-opponent existence and the global opponent count
        # coincide whenever one opponent holds the maximum, which is the
        # corpus shape.
        assert atom.inner_filter is not None
        assert atom.right_inner_filter is not None

        def _bf_count(filt) -> int:
            return sum(
                1
                for card in sorted(world.cards)
                if world.zone_of(card).kind == ZONE_BATTLEFIELD
                and eval_filter(filt, card, ctx)
            )

        return _bf_count(atom.inner_filter) > _bf_count(atom.right_inner_filter)
    if pred is FAtomPred.ZONE_COUNT_GE:
        # Grammar round 6 (R6-2, Thieves' Guild Enforcer): "<who> has >=
        # count cards in their <zone> matching inner_filter". Handle-free
        # set gate like CONTROLLER_COUNT_GE (the trigger-condition judge);
        # TRUE when ANY denoted player's zone meets the threshold ("an
        # opponent has eight or more cards in their graveyard"). WHO drives
        # the population — in the corpus the IR's zone.controller rides
        # with WHO, so reading WHO is the whole answer (ControllerRef or
        # the CONTROLLER_IS-precedent referent Selector). A non-card zone
        # (PLAYER position) is flagged, never counted empty.
        from MTG_bot.core.executor.selectors import (
            ZONE_KIND_TO_STATE,
            controller_of,
            players_for_ref,
            resolve_selector,
        )

        assert atom.count is not None and atom.zone is not None
        threshold = resolve(atom.count, ctx)
        zone_ir = atom.zone
        if atom.who is None:
            raise NotImplementedError(
                "executor: ZONE_COUNT_GE with no WHO has no consumer (R6-2 "
                "requires the player slot; flag, never guess YOU)"
            )
        state_kind = ZONE_KIND_TO_STATE.get(zone_ir.kind)
        if state_kind is None:
            raise NotImplementedError(
                f"executor: ZONE_COUNT_GE zone {zone_ir.kind.name} is not a "
                "card zone (flag, never a zero-count guess)"
            )
        who = atom.who
        if isinstance(who, ControllerRef):
            players = players_for_ref(who, ctx)
        elif isinstance(who, Selector):
            players = [
                c if c.namespace == "player" else controller_of(ctx, c)
                for c in resolve_selector(who, ctx)
            ]
        else:
            raise NotImplementedError(
                f"executor: ZONE_COUNT_GE who {who!r} is neither a "
                "ControllerRef nor a Selector (R6-2 closed vocabulary)"
            )
        for player in players:
            entries = ctx.world.players[player].zone(state_kind).entries
            # T5-E (Conspicuous Snoop s3): the Zone enum's OPTIONAL position
            # now bounds the population — TOP counts only the top entry,
            # mirroring the selector-side idiom (selectors.py "top of library
            # = last entry"). ZONE_TOP_IS becomes expressible as this
            # predicate with position=TOP and count=1. Every corpus user to
            # date (R6-2) carries an unpositioned Zone, so their counts are
            # byte-identical; a positioned zone was previously and silently
            # a whole-zone count, which the R10 note flags as a lie.
            position = zone_ir.position
            if position is ZonePosition.TOP:
                entries = entries[-1:]
            elif position is ZonePosition.BOTTOM:
                entries = entries[:1]
            counted = sum(
                1
                for h in entries
                if atom.inner_filter is None or eval_filter(atom.inner_filter, h, ctx)
            )
            if counted >= threshold:
                return True
        return False
    if pred is FAtomPred.NAME_PARTITION_COUNT_GE:
        # Grammar round 10 (R10-2, C26, Chrome Replicator): among the
        # permanents ctx.controller CONTROLS, those passing inner_filter
        # group by EXACT printed name and the largest group must reach
        # count — templates_b2a's pinned reading ("grouped by EXACT name,
        # the largest group; no pairwise name-equality vocabulary").
        # Handle-free like CONTROLLER_COUNT_GE; the battlefield population
        # read through the GAIN_CONTROL overlay (controller_of, 16e).
        from MTG_bot.core.executor.selectors import controller_of

        assert atom.count is not None and atom.inner_filter is not None
        threshold = resolve(atom.count, ctx)
        groups: dict[str, int] = {}
        for card in sorted(world.cards):
            if (
                world.zone_of(card).kind != ZONE_BATTLEFIELD
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
        # 14d (B-7): the journal-history family. Necromentia's "-1/-0… for
        # each card exiled from their hand this way" counts per CANDIDATE
        # (the QCount Selector filters the exile population card by card);
        # Barrin's end-step gate ("if a permanent was put into your hand
        # from the battlefield this turn") is about SOME permanent. The two
        # honest readings are discriminated by the handle itself: a card
        # that currently sits in the pred's DESTINATION zone answers for
        # itself; anything else (the gate's source anchor) is existential.
        # ZONE_CHANGE rows carry the zone OWNERS in their owner columns
        # (the 12b snapshot keys zones by player), so both endpoints answer.
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
        # 14d (B-7): the ETB-entry twin the Archfiend's Vessel gate compiles
        # beside CAST_THIS_TURN_FROM ("if it entered from your graveyard or
        # you cast it from your graveyard") — FOr judges BOTH children, so
        # the family ships together or the gate still raises. Handle-scoped
        # by the grammar's own reading ("it entered"): THIS object entered
        # the battlefield from that zone this turn.
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
        for e in _turn_rows(ctx, pred.name):
            if e.kind != KIND_ZONE_CHANGE or e.subject != handle:
                continue
            frm, to, owner_before, _after = e.zone_move
            if to == ZONE_BATTLEFIELD and frm == from_state and owner_before in owners:
                return True
        return False
    if pred is FAtomPred.CAST_THIS_TURN_FROM:
        # 14d (B-7): "you cast it from your graveyard" (Archfiend's Vessel),
        # "if this spell was cast from anywhere other than your hand" (See
        # the Truth's FNot twin). Handle-scoped over the 13b CAST rows,
        # whose payload carries (caster, ordinal, spell_kind, from_zone,
        # x_value) — the from_zone column makes the origin readable after
        # the spell has moved on.
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
        # r20b (Containment Priest, R5-1): the zone-agnostic twin of
        # CAST_THIS_TURN_FROM — "it was cast this turn (by who)". Same 13b
        # KIND_CAST rows (emitted at 601.2h, before resolution, so the row
        # is already journalled by the time a enters-the-battlefield
        # replacement judges it: the Priest spares its own casting spell
        # and every other cast creature, but not a put-onto-the-battlefield
        # creature — which never passed through the stack).
        from MTG_bot.core.executor.events import KIND_CAST
        from MTG_bot.core.executor.selectors import controller_matches

        assert atom.who is not None
        for e in _turn_rows(ctx, pred.name):
            if e.kind != KIND_CAST or e.subject != handle:
                continue
            caster = e.cast[0]
            if controller_matches(atom.who, caster, ctx):
                return True
        return False
    if pred is FAtomPred.WAS_KICKED:
        # ZND-1e (CR 702.27a), three reader lanes over ONE carrier: the
        # CAST row's trailing kicked column (journal.emit_cast) is the
        # paid/not-paid choice of the cast. ZND-1e follow-up (blink law,
        # the /100 deferred caveat closed) splits the read by the JUDGED
        # object's provenance:
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
        #   the gated entering state (CR 614.1c) — the read is ENTRY-BOUND
        #   (_permanent_was_kicked). The journal already carries the
        #   provenance field: the entry ZONE_CHANGE row's from_state. No
        #   payload extension, no new rows, fingerprint bytes unchanged.
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
        # 14d (B-7): the C18 row. CREATURE_DIES carries the was-snapshot
        # (type line + effective P/T AT EVENT TIME), which is exactly how a
        # "nontoken creature that died this turn" count answers after the
        # world has moved the card (Gadrak's end-step Treasures — 9 goldens
        # compile the pred). The snapshot's own consumers are this row
        # lookup and the binder's event matcher (12b): the frozen FAtomPred
        # vocabulary has no WAS_* member (verified — the evidence brief's
        # "WAS_TYPE" guess does not exist in the grammar), and C12 forbids
        # inventing one off English substrings.
        from MTG_bot.core.executor.events import KIND_CREATURE_DIES

        rows = _turn_rows(ctx, pred.name)
        # B-56 (2026-10-29): the journal writes a dies row for EVERY
        # battlefield-to-graveyard move (CR 700.4: any permanent "dies"),
        # and every compiled reading of this pred is about a CREATURE ("if
        # a creature died this turn", "creature that died this turn"). So
        # only rows whose C18 was-snapshot type line names Creature count
        # (CR 603.10a: the object as it last existed on the battlefield). A
        # sacrificed Treasure died, but no creature did (Twinblade
        # Assassins drew off it).
        dies = [
            e
            for e in rows
            if e.kind == KIND_CREATURE_DIES
            and "Creature" in _type_line_tokens(e.dies[2])
        ]
        if any(e.subject == handle for e in dies):
            return True
        # r19a (Life Goes On / Fungal Rebirth): an EXISTENTIAL reading for
        # a judged handle that could never itself have been the dead
        # creature — a player handle (a LifeGainedEvent replacement judged
        # over its subject) or a card whose printed type line names no
        # creature (a Conditional judged over the resolving spell, e.g.
        # "if a creature died this turn" on an instant). Selector
        # candidates ARE creature-typed (Gadrak's graveyard census,
        # Liliana's Standard Bearer), so their strict per-handle reading —
        # "did THIS creature die" — is untouched; a creature-typed handle
        # that did not die still answers False.
        # r21b (Caged Zombie / Sabertooth Mauler / Liliana's Devotee):
        # the strict per-handle reading now ALSO requires the handle to
        # be OFF the battlefield — a creature sitting on the battlefield
        # is, by definition, not the dead creature, so its condition
        # gate can only ever be the EXISTENTIAL "if a creature died this
        # turn" reading (the activation-source case the r19a note already
        # covers for non-creature types; the creature-typed battlefield
        # source was the overlooked twin). Graveyard / exile / hand
        # creature-typed handles keep the strict reading (Gadrak's
        # graveyard census, Liliana's Standard Bearer), and a handle
        # that IS one of the dead creatures still answers True via the
        # subject-match above.
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
        # 14d (B-7): "cards exiled with ~" (Idol of Endurance, Chandra,
        # Heart of Fire; the Necromentia name-exile station's sibling).
        # WORLD half: the card is in exile NOW. HISTORY half: the source
        # CAUSED the exile — the 12b diff-inspect writes the acting
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
        # 16b (CR 506.4): the executor's live attack record — the attacker
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
        # 16c (CR 506.4): the executor's live block record — a handle IS
        # blocking while it stands in some attacker's blocker list (the
        # record clears with the attack record at end of combat). No M21
        # card reads this pred; the closed grammar vocab answers it rather
        # than raising, because the state EXISTS from 16c on (the attack
        # sibling's precedent).
        if ctx.executor is None:
            raise NotImplementedError(
                "executor: filter pred IS_BLOCKING reads the executor's "
                "block record (bare ExecCtx)"
            )
        return any(handle in blockers for blockers in ctx.executor.blocked_by.values())
    if pred is FAtomPred.ATTACK_AGAINST_COUNT_GE:
        # 16b (grammar round 10, R10-3 — Mangara, the Diplomat): count the
        # CURRENT attacker set whose ATTACKED object passes inner_filter.
        # The pred reads the executor's attack record (the R10-3 "game
        # record" reading), evaluated in the firing ability's coordinates:
        # CONTROLLER_IS YOU = "attacking you", the Planeswalker child
        # short-circuits behind it in v1 (all attackers attack the
        # defending player — planeswalker attacking is 16c).
        if ctx.executor is None:
            raise NotImplementedError(
                "executor: filter pred ATTACK_AGAINST_COUNT_GE reads the "
                "executor's attack record (bare ExecCtx)"
            )
        assert atom.count is not None and atom.inner_filter is not None
        threshold = resolve(atom.count, ctx)
        counted = 0
        for attacker in ctx.executor.attackers:
            attacked = ctx.executor.attacked.get(attacker)
            if attacked is None:
                continue
            if eval_filter(atom.inner_filter, attacked, ctx):
                counted += 1
                if counted >= threshold:
                    return True
        return counted >= threshold
    if pred is FAtomPred.CARDS_DRAWN_THIS_TURN_GE:
        # 16c (the draw-clock family — Tome Anima's "can't be blocked as
        # long as you've drawn two or more cards this turn" static gate,
        # consumed live at every block-pair consult): count the journal's
        # CARD_DRAWN rows of the turn window (subject = the card drawn,
        # data[0] = the drawing player) against WHO's seat. Journal-backed
        # like the 14d history family — the journal IS state.
        from MTG_bot.core.executor.events import KIND_CARD_DRAWN
        from MTG_bot.core.executor.selectors import players_for_ref

        assert atom.count is not None
        threshold = resolve(atom.count, ctx)
        drawners: set[Handle] | None = None
        if atom.who is not None:
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
            if drawners is None or row.draw[0] in drawners:
                drawn += 1
                if drawn >= threshold:
                    return True
        return drawn >= threshold
    if pred is FAtomPred.LIFE_LEAD_OVER_START_GE:
        # r20c (Speaker of the Heavens, grammar round 9 R9-2): "you have at
        # least N life more than your starting life total" — the rule text
        # reads CURRENT life minus the player's START, so this is a ledger
        # read, not a LIFE_GAINED journal sum: a non-damage life loss
        # (CR 118.12 payment) leaves no journal row (events.py emits gains
        # and damage losses only), so a gains-sum would OVERSTATE the lead.
        # The start is the executor's construction-time snapshot (the same
        # start_life the world was built with; replay rebuilds the world at
        # that value, games.py:1017). Bare-count atom: WHO is implicitly
        # YOU — the ability's controller (the gate never carries a seat).
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
    if pred is FAtomPred.LIFE_GAINED_THIS_TURN_GE:
        # r19b (Sanguine Indulgence's CostModifier condition): the draw-
        # clock twin over the 16c LIFE_GAINED rows — subject is the gaining
        # player, payload the amount, journalled by the event-diff layer
        # for EVERY life gain (verbs need not know the pred exists). The
        # comparison is a SUM ("gained N or more life"), not a row count:
        # two separate 2-life gains satisfy a threshold of 3.
        from MTG_bot.core.executor.events import KIND_LIFE_GAINED
        from MTG_bot.core.executor.selectors import players_for_ref

        assert atom.count is not None
        threshold = resolve(atom.count, ctx)
        gainers: set[Handle] | None = None
        if atom.who is not None:
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
            if gainers is None or row.subject in gainers:
                gained += row.amount
                if gained >= threshold:
                    return True
        return gained >= threshold
    if pred is FAtomPred.INSTANT_OR_SORCERY_CAST_THIS_TURN:
        # r19b (Stormwing Entity's CostModifier condition): scan the 13b
        # CAST feed — payload column 3 carries the frozen SpellKind NAME
        # (stack.emit_cast passes ``node.kind.name``), so the instant-or-
        # sorcery family test is a row filter; WHO scopes the caster seat
        # like the 14d history family.
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
    if pred is FAtomPred.TURN_OF:
        # r19b (Discontinuity's your-turn cost window): the active-seat
        # column answers directly — no journal read. WHO maps through the
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
        # ZND-2 T4 first consumer (/98 registered this 'declarative, zero-
        # consumer'; Murasa Sproutling's "target card with a kicker ability"
        # graveyard filter is the first real ask). PRINTED-property reading:
        # the ground truth is the card's COMPILED record — a card HAS a
        # kicker iff its FRONT-FACE ability tuple carries a KickerAbility
        # node, the same accessor (top-level scan) legal_casts and the cast
        # fold use via legality.kicker_of (§9 one encoding). The record
        # resolves through legality.spell_record — the per-handle bridge
        # else the oracle-id registry, the pattern TYPE_EQ's identity reads
        # and the r20c hand-window lane share for cards OFF the battlefield.
        # FACE law (/106): a BackFace node carries its abilities in its OWN
        # tuple, which this scan never descends — a back-face-only kicker
        # does NOT satisfy HAS_KICKER for a front-face decision (the engine
        # never plays faces today; when face playability lands, the judged
        # face must become the coordinate, and this is the site to amend).
        # Tokens: a created token has no compiled record (or carries the
        # token record with is_token) — a token never has a printed kicker,
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
    raise NotImplementedError(
        f"executor: filter pred {pred.name} not implemented (12c query surface)"
    )


def _permanent_was_kicked(ctx: ExecCtx, handle: Handle) -> bool:
    """WAS_KICKED's PERMANENT lane (ZND-1e blink law: CR 400.7 object
    identity + 614.1c entered state + 702.27a the kick choice). Judged for
    a handle ON the battlefield; answers from the CURRENT entry, not the
    turn window: a kicked permanent blinked and returned through exile is a
    NEW object that was never cast, so its gated EtBState must not re-apply
    and a later "if it was kicked" must follow the entry's provenance.

    The provenance field is already journalled: the LAST battlefield-entry
    ZONE_CHANGE row's ``from_state``. An entry whose from_state is not the
    stack (put-enter from hand/graveyard, blink return, token create) was
    not a cast — False, and the CAST rows are never consulted. An entry
    FROM the stack carries the kick of the CAST row of that same stack
    residency: emit_cast fires after park (stack.cast), so the cast row's
    clock is strictly later than the residency-opening ZONE_CHANGE row and
    strictly earlier than the entry — a hypothetical future put-onto-the-
    stack (no cast row inside its residency) therefore reads False, never
    the object's older cast. The scan is the WHOLE journal, not the turn
    window: the kick of an uncalled-for permanent is object permanence, so
    a permanent cast kicked LAST turn still truthfully answers True today.
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


def _turn_rows(ctx: ExecCtx, pred_name: str) -> list[GameEvent]:
    """The current turn's journal rows a history predicate answers against
    (14d, B-7). No journal on the ctx means no answer: the raise names the
    predicate (the FLIP_WON/NAME_CHOSEN convention — an unanswered question
    is flagged, never a guessed False)."""
    jrn = ctx.journal
    if jrn is None:
        raise NotImplementedError(
            f"executor: filter pred {pred_name} reads the journalled turn "
            "history (this ExecCtx has no journal)"
        )
    return jrn.turn_window()
