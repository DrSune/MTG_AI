"""Compiled-ability attachment + trigger binding/fire.

Compiled ability IR (a ``CardRecord`` from ``compile_pool`` / a
``CompileResult``) attaches to world Handles; every
world event the :class:`~MTG_bot.core.executor.events.EventJournal` derives
is matched against the attached :class:`TriggeredAbility` nodes; a match
queues a canonical :class:`~MTG_bot.core.state.TriggerInstance` through
``world.queue_trigger`` (put on the stack by :meth:`TriggerBinder.put_waiting`),
and the binder drains the queue — condition -> may-offer -> effect through
the executor's effect runner, whose mutations are journalled and matched in
turn — firing until the queue empties.

Contracts honoured:

  * **attachment lifecycle** — triggers live while the permanent is on the
    battlefield: leaving detaches, re-entering re-registers. The compiled
    record stays registered by oracle id: the bridge from the game card's
    :class:`~MTG_bot.core.identity.CardIdentity` to its compiled IR;
  * **the stack's order** — waiting triggers go on the stack in APNAP order
    (CR 603.3b: the active player's first, so the non-active player's resolve
    first), each player's in the order that player chooses
    (:meth:`TriggerBinder.put_waiting`);
  * **was-snapshots** — a dies firing binds ``event``/``result`` to the dead
    subject, whose was-snapshot the journal carried, so the ``event``/
    ``result`` QProp referents read it;
  * **delayed triggers** — ``DelayedTrigger`` effect nodes schedule into
    the same matcher with a duration tag; the end-of-turn sweep expires the
    turn-window entries;
  * **tripwire** — after ``MAX_TRIGGER_FIRES`` triggered abilities resolved
    since the stack was last empty (``Executor._resolve_top``, shared by the
    undriven settle and the game loop) the guard QUARANTINES the runaway
    source (dropped firings recorded in ``executor.trigger_loops``) and play
    continues — the loop is a bug to flag, never a bug to run;
  * **flag, don't degrade** — an event node no journal feed serves
    (``_UNSUPPORTED_EVENTS``, a blocker-count DeclareBlockersEvent), or a
    once-per-event trigger on an event kind the binder does not group, RAISES
    ``NotImplementedError`` at *bind* time (a granted once-per-event trigger,
    never bound, when it triggers), instead of silently arming a trigger that
    could never fire or would fire too often.

May-offers: an ``OptionalEffect`` in a trigger effect answers through the
executor's vocabulary-addressed decision stream: the ask carries its own
(vocab, what) key, so firings the drain itself arms are answerable — pinned
deterministic by ``TestMayAndDeterminism`` (test_executor_binding.py).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, NamedTuple

from MTG_bot.core.ability_tree import (
    DESIGNATED_PLAYER_REFS,
    AbilityActivatedEvent,
    AbilityKind,
    AbilityTriggerEvent,
    Atom,
    AtomArgs,
    BecomesBlockedEvent,
    CardDrawnEvent,
    CardRecord,
    CastSpellEvent,
    Choose,
    Conditional,
    ControllerRef,
    CounteredEvent,
    CounterKind,
    CounterPlacedEvent,
    CreatureDiesEvent,
    DamageDealtEvent,
    DeclareAttackersEvent,
    DeclareBlockersEvent,
    DelayedTrigger,
    DurationEot,
    EachPlayer,
    EventSpec,
    FAnd,
    FAtom,
    FAtomPred,
    Filter,
    FNot,
    FOr,
    Keyword,
    LifeGainedEvent,
    LifeLostEvent,
    OptionalEffect,
    Phase,
    PhasingEvent,
    PtDelta,
    PtDirection,
    QAtMost,
    QConst,
    Repeat,
    SacrificeEvent,
    Selector,
    SelectorMode,
    Seq,
    StepEvent,
    TapStateEvent,
    TargetingEvent,
    TriggeredAbility,
    TurnPhaseEvent,
    Verb,
    Zone,
    ZoneChangeEvent,
    ZoneKind,
    count_semantics,
    gathers_objects,
    own_nodes,
    walk,
)
from MTG_bot.core.compiler.compiler import PoolCompile
from MTG_bot.core.executor.decisions import site_digest
from MTG_bot.core.executor.durations import duration_tag
from MTG_bot.core.executor.events import (
    KIND_ABILITY_ACTIVATED,
    KIND_ABILITY_TRIGGERED,
    KIND_CARD_DRAWN,
    KIND_CAST,
    KIND_COUNTER_PLACED,
    KIND_CREATURE_DIES,
    KIND_DAMAGE,
    KIND_DECLARE_ATTACKERS,
    KIND_DECLARE_BLOCKERS,
    KIND_LIFE_GAINED,
    KIND_LIFE_LOST,
    KIND_REFLEXIVE,
    KIND_TAP_STATE,
    KIND_TARGETING,
    KIND_TURN_PHASE,
    KIND_ZONE_CHANGE,
    GameEvent,
)
from MTG_bot.core.executor.quantity import ExecCtx, departure_lki, eval_filter, resolve
from MTG_bot.core.executor.selectors import (
    ZONE_KIND_TO_STATE,
    controller_matches,
    filter_bound_player_refs,
    players_for_ref,
)
from MTG_bot.core.identity import Handle
from MTG_bot.core.state import ZONE_BATTLEFIELD, ZONE_GRAVEYARD, GameWorld

if TYPE_CHECKING:  # pragma: no cover - typing only, dodges the import cycle
    from MTG_bot.core.executor import Executor

# Infinite-loop tripwire: after this many triggered abilities resolved in one
# settle (Executor._settle), TriggerBinder.quarantine stops the source that
# resolved most — we never spin.
MAX_TRIGGER_FIRES = 200

# EventSpec kinds no journal feed serves: binding one RAISES — flag, don't
# degrade.
_UNSUPPORTED_EVENTS: dict[type, str] = {
    StepEvent: (
        "12e (step-level subscription emitter; 12d's untap tick is an "
        "executor step that emits TapState/phase events, not StepEvents)"
    ),
    # "can't be countered" reads CounteredEvent (a PREVENT_EFFECT,
    # consumed while the spell is on the stack). No trigger reads it: the
    # drain would match the COUNTER row after the spell has left the stack, so
    # a "spell" filter could not be judged on the object as it was.
    CounteredEvent: "a prevention event only (no trigger feed: the countered "
    "spell has left the stack by the time the journal row is matched)",
    # "can't phase in" reads PhasingEvent (a PREVENT_EFFECT the phasing step
    # consults). Phasing is a status, not a zone change (CR 702.26d), and the
    # journal has no phasing row, so nothing feeds a "whenever ... phases" trigger.
    PhasingEvent: "a prevention event only (no journal row records phasing)",
}

# Delayed-trigger window tags the end-of-turn sweep expires. ``UntilNextTurn``
# rides the Eot sweep as a stand-in: the precise next-turn-start expiry
# applies to the ledger / layer / prevention records only, and a delayed
# window beyond the turn raises (schedule_delayed).
_SWEEP_TAGS = ("Eot", "UntilNextTurn")

# Any trigger node: attached TriggeredAbility or scheduled DelayedTrigger —
# both carry ``condition`` + ``effect``.
_AnyTrigger = TriggeredAbility | DelayedTrigger


def _required_target_keys(effect: object) -> frozenset[str]:
    """CR 603.3d: the TARGET slots an ability must fill to be put on
    the stack at all, keyed like :meth:`TriggerBinder._designate`'s
    collector (``repr`` of a referent-free TARGET-mode Selector).

    Every printed "target" outside a mode choice is required, whatever
    wraps it: "you may", "if you do", a repeat or a per-player loop are all
    resolution-time, and targets are announced before any of them (CR
    601.2c, which 603.3d applies to triggers). A slot inside a ``Choose``
    is mode-dependent (CR 700.2a): required only when EVERY option carries
    it (Tolarian Kraken's "tap or untap target permanent"), since otherwise
    a mode without it stays choosable. A nested ``DelayedTrigger`` chooses
    its own targets when it triggers (CR 603.7c), so it adds nothing."""
    if isinstance(effect, Atom):
        return frozenset(
            repr(value)
            for _role, value in effect.args.pairs
            if isinstance(value, Selector)
            and value.mode is SelectorMode.TARGET
            and value.referent is None
        )
    if isinstance(effect, Choose):
        return frozenset.intersection(
            *(_required_target_keys(option) for option in effect.options)
        )
    if isinstance(effect, Seq):
        return frozenset().union(*(_required_target_keys(s) for s in effect.steps))
    if isinstance(effect, Conditional):
        keys = _required_target_keys(effect.then_effect)
        if effect.else_effect is not None:
            keys |= _required_target_keys(effect.else_effect)
        return keys
    if isinstance(effect, (OptionalEffect, Repeat)):
        return _required_target_keys(effect.inner)
    if isinstance(effect, EachPlayer):
        return _required_target_keys(effect.effect)
    return frozenset()  # DelayedTrigger (CR 603.7c)


def _is_subject_identity(filter_: Filter) -> bool:
    """Brash Taunter: the bare IS_SOURCE identity pred alone. It is
    DEFINED for any handle (handle == ctx.source, no card data read), and a
    PLAYER subject can never be a card ability's source — so over a player
    damage subject it is honestly FALSE, not undefined (the echo's own
    player-damage row must not re-arm the "is dealt damage" trigger). Every
    other filter over a player goes to :func:`_player_subject_verdict`."""
    return isinstance(filter_, FAtom) and filter_.pred is FAtomPred.IS_SOURCE


# The preds whose answer over a PLAYER subject is decidable without reading
# any card data (Hooded Blightfang's SUPERTYPE_EQ) — a player IS none of these
# things, so each honest answer is FALSE (and TRUE under FNot). The rest
# of the vocab genuinely reads card data a player handle does not carry,
# and raises: flag, never guess.
_PLAYER_SHAPE_PREDS = frozenset(
    {
        FAtomPred.TYPE_EQ,
        FAtomPred.SUBTYPE_EQ,
        FAtomPred.SUPERTYPE_EQ,
        FAtomPred.NAME_EQ,
        FAtomPred.NAME_CONTAINS,
        FAtomPred.KEYWORD_HAS,
        FAtomPred.IS_TOKEN,
        FAtomPred.IS_PERMANENT,
    }
)


def _player_subject_verdict(filter_: Filter, subject: Handle, ctx: ExecCtx) -> bool:
    """A filter over a PLAYER subject: the boolean-algebra
    closure over the decidable player-subject preds. A player subject can
    never BE a card-shape thing, so those atoms answer FALSE outright; a
    player's CONTROLLER_IS is honestly the player itself. The nodes
    compose. Any pred outside the decidable set raises."""
    if isinstance(filter_, FAnd):
        return all(_player_subject_verdict(c, subject, ctx) for c in filter_.children)
    if isinstance(filter_, FOr):
        return any(_player_subject_verdict(c, subject, ctx) for c in filter_.children)
    if isinstance(filter_, FNot):
        return not _player_subject_verdict(filter_.inner, subject, ctx)
    if isinstance(filter_, FAtom):
        if filter_.pred in _PLAYER_SHAPE_PREDS and filter_.who is None:
            return False
        if filter_.pred is FAtomPred.CONTROLLER_IS and filter_.who is not None:
            # a player is its own controller (CR 109.5's player half)
            return controller_matches(filter_.who, subject, ctx)
        if filter_.pred is FAtomPred.OPPONENT_OF:
            # the destination identity pred is decidable over a player
            # subject by definition — the atom is player-total (its
            # _eval_atom branch reads only seats and bindings, never card
            # data), so the shared oracle answers here too.
            return eval_filter(filter_, subject, ctx)
    raise NotImplementedError(
        "executor: DamageDealtEvent filter over a player subject is 12c's query surface"
    )


def _compile_bridge(compiled: object) -> CardRecord:
    """The oracle-id bridge: a CardRecord, a CompileResult, or anything
    carrying ``.card`` — never a guess."""
    record = getattr(compiled, "card", compiled)
    if not isinstance(record, CardRecord):
        raise ValueError(  # noqa: TRY004 - ValueError type guards are the house convention
            "attach_card: need a CardRecord/CompileResult, got "
            f"{type(compiled).__name__}"
        )
    return record


class _Carried(NamedTuple):
    """What a reflexive trigger (CR 603.12) reads of the resolution that created it, as it was
    then: its bindings minus its own designation ("the sacrificed creature"), its X, and its
    event register ("that creature")."""

    bindings: dict
    x_value: int | None
    event: object
    event_amount: int | None


@dataclass
class _Firing:
    """One queued trigger instance's execution payload, keyed by the
    instance's (tick-unique) clock. ``carried``: a reflexive trigger's
    creating resolution (every other firing builds its context from its
    event). ``gathered``: the objects of a gathered event
    (:func:`~MTG_bot.core.ability_tree.gathers_objects`), read as it occurred."""

    source: Handle
    controller: Handle
    node: _AnyTrigger
    event: GameEvent
    seq: int
    carried: _Carried | None = None
    gathered: tuple[Handle, ...] | None = None


@dataclass
class DelayedBinding:
    """A DelayedTrigger scheduled into the journal matcher."""

    seq: int
    tag: str
    node: DelayedTrigger
    source: Handle
    controller: Handle


def functions_from_graveyard(ability: object) -> bool:
    """CR 113.6m ("An ability whose cost or effect specifies that it moves
    the object it's on out of a particular zone functions only in that zone"): a
    triggered ability whose effect moves its own source out of a graveyard
    ("return this card from your graveyard to the battlefield tapped", Silversmote
    Ghoul) functions only while that card is in a graveyard."""
    from MTG_bot.core.executor.selectors import _filter_is_self_referential

    if not isinstance(ability, TriggeredAbility):
        return False
    for node in walk(ability.effect):
        if not isinstance(node, Atom) or node.verb is not Verb.MOVE_ZONE:
            continue
        dest = node.args.get("destination")
        if isinstance(dest, Zone) and dest.kind is ZoneKind.GRAVEYARD:
            continue
        for role in ("cards", "target"):
            sel = node.args.get(role)
            if (
                isinstance(sel, Selector)
                and sel.zones
                and all(z.kind is ZoneKind.GRAVEYARD for z in sel.zones)
                and _filter_is_self_referential(sel.filter)
            ):
                return True
    return False


class TriggerBinder:
    """The (handle, ability-idx) trigger registry + event matcher; puts the
    waiting triggers on the stack (APNAP) and resolves them. Owned by one
    :class:`~MTG_bot.core.executor.Executor`."""

    def __init__(self, executor: Executor) -> None:
        self.executor = executor
        self.records: dict[str, CardRecord] = {}
        self.attached: dict[tuple[Handle, int], TriggeredAbility] = {}
        # CR 113.6m: the triggers of cards IN A GRAVEYARD whose ability
        # functions only there (functions_from_graveyard). Kept apart from
        # ``attached`` so a battlefield departure's detach never drops them.
        self.attached_graveyard: dict[tuple[Handle, int], TriggeredAbility] = {}
        self.handle_record: dict[Handle, CardRecord] = {}
        # Emblem synthetic handles -> their OWNER. Emblems are not
        # world cards, so ``world.controller_of`` cannot answer "who is
        # this trigger's you?" — this side-table does, and every trigger
        # match path consults it through :meth:`_controller_of`.
        self.emblem_owner: dict[Handle, Handle] = {}
        self.firings: dict[int, _Firing] = {}
        # Tripwire guard (Chandra's Incinerator): sources whose trigger
        # self-retriggers the settle are QUARANTINED (quarantine); _queue then
        # drops their firings for the rest of the game — "flag it, never
        # run it". This is replayed state: the executor folds it into
        # state_fingerprint through :meth:`dump`.
        self.quarantined: set[Handle] = set()
        self.delayed: list[DelayedBinding] = []
        self._seen_journal_len = 0
        self._seq = 0
        # CR 603.2c: (source, node-id, row kind, event id) for every queue a
        # once-per-event trigger on a declaration or a zone change already
        # made. The journal carries ONE row per declared attacker or moved
        # object; "whenever you attack" and "whenever one or more tokens you
        # control enter" trigger once on the whole event, so the shared declare
        # group or atom batch collapses the row fan-out (a once-per-occurrence
        # trigger takes every row it matches).
        self._gathered_queued: set[tuple[Handle, int, str, int]] = set()
        # Cached synthetic keyword-trigger nodes, keyed (family, holder):
        # ONE node object per (family, handle).
        self._kw_nodes: dict[tuple[str, Handle], TriggeredAbility] = {}
        # A battlefield departure normally detaches the leaver's triggers on
        # the ZONE_CHANGE journal row — but EventJournal.record_atom journals the
        # card's CREATURE_DIES row IMMEDIATELY after that row (same diff
        # iteration), and the dying permanent's own "when this dies"
        # trigger must still be attached when the dies row is matched. A
        # ZONE_CHANGE(bf→non-bf) whose very next journalled row is that
        # card's CREATURE_DIES parks its handle here; :meth:`_lifecycle`
        # runs the deferred detach at the dies row, after the match pass
        # queued the firing. Non-death departures (bounce/exile/hand) have
        # no dies row and detach on the spot.
        self._pending_dies_detach: set[Handle] = set()
        # CR 724.1c: while an effect ends the turn, state-based actions
        # are checked but no triggered ability is put onto the stack; the
        # firings stay queued for the cleanup step (724.1f). Set and cleared
        # inside one Executor call, so never set between ops.
        self.hold = False

    # ------------------------------------------------------------ attach

    @property
    def world(self) -> GameWorld:
        return self.executor.world

    def _controller_of(self, handle: Handle, event: GameEvent | None = None) -> Handle:
        """The trigger controller: the world's battlefield controller, or
        for an emblem's synthetic handle (never a world card) the
        recorded OWNER. The emblem's "you" is its owner for every event
        match (CR 113.7 the emblem is controlled by its owner). Matched on
        ``event``, the object's own departure from the battlefield, it is the
        controller the object had as it left (CR 603.3a with 603.10a): a
        stolen creature's "when this creature dies" trigger is the thief's."""
        owner = self.emblem_owner.get(handle)
        if owner is not None:
            return owner
        lki = departure_lki(handle, event, self.executor)
        if lki is not None:
            return lki.controller
        # triggers ride the CURRENT controller (CR 603.7b).
        return self.executor.controller_of(handle)

    def bind_emblem(self, handle: Handle, record: CardRecord, owner: Handle) -> int:
        """Bind a granted emblem's ability nodes. The emblem record is
        a token-shaped CardRecord (the compiler normalises emblem→token):
        TriggeredAbility nodes bind at (handle, idx) with the OWNER as
        controller (via :meth:`_controller_of`), StaticAbility nodes attach
        to the layer registry ANCHORED TO THE OWNER (Liliana's emblem
        grants haste to "creatures you control" — its ``you`` is the
        owner), and the synthetic handle never touches world zones, the
        loyalty seed, or the castable-card surfaces
        (:func:`legality.legal_activations` iterates world cards, so it can
        never see this handle)."""
        triggers = []
        for idx, ability in enumerate(record.abilities):
            if isinstance(ability, TriggeredAbility):
                self._check_trigger(ability, record.name)
                triggers.append((idx, ability))
        self.detach(handle, leaving=False)
        self.records.setdefault(record.oracle_id, record)
        self.handle_record[handle] = record
        self.emblem_owner[handle] = owner
        for idx, ability in triggers:
            self.attached[(handle, idx)] = ability
        # Same attach order as _register (replacements first - its
        # idempotence sweep must not expire the layers' static prevents).
        self.executor.replacements.attach_source(handle, record, controller=owner)
        self.executor.layers.attach_source(handle, record, controller=owner)
        return len(triggers)

    def register_token(self, handle: Handle, record: CardRecord) -> None:
        """File the token's synthesized record under its synthetic oracle id
        and attach it to the HANDLE, so the battlefield ZONE_CHANGE row's
        lifecycle registration (the SAME :meth:`_lifecycle` path a printed
        permanent uses) finds a record and binds the token's rule lines — the
        Pursued Whale Pirate's "can't block" prevention and the mandate layer
        its "creatures you control attack if able" static becomes, anchored to
        the token's CONTROLLER. Pure registration: the world card already
        exists (CREATE_TOKEN put it there); no zones, no loyalty seed."""
        if handle not in self.world.cards:
            raise ValueError(f"register_token: unknown world card {handle}")
        for ability in record.abilities:
            if isinstance(ability, TriggeredAbility):
                self._check_trigger(ability, record.name)
        self.records.setdefault(record.oracle_id, record)
        self.handle_record[handle] = record

    def attach_card(self, handle: Handle, compiled: object) -> int:
        """Register the compiled record for the world card ``handle`` and
        bind its TriggeredAbility nodes. The game card's identity oracle id
        must match the compiled record — the bridge is CHECKED, never
        assumed. A handle already carrying a DIFFERENT record raises: one
        permanent, one compiled record (re-attaching the same record is an
        idempotent refresh)."""
        if handle not in self.world.cards:
            raise ValueError(f"attach_card: unknown world card {handle}")
        record = _compile_bridge(compiled)
        identity = self.world.cards[handle].identity
        if identity.oracle_id != record.oracle_id:
            raise ValueError(
                f"attach_card: card {handle} is {identity.oracle_id!r} but the "
                f"compiled record is {record.oracle_id!r} — identity bridge mismatch"
            )
        existing = self.handle_record.get(handle)
        if existing is not None and existing.oracle_id != record.oracle_id:
            raise ValueError(
                f"attach_card: {handle} already carries {existing.name!r}; "
                "detach before swapping a permanent's compiled record"
            )
        # Check-then-commit: every event kind validates BEFORE any binding
        # mutates, so a raise leaves the registry untouched.
        for ability in record.abilities:
            if isinstance(ability, TriggeredAbility):
                self._check_trigger(ability, record.name)
        self.records[record.oracle_id] = record
        self.handle_record[handle] = record
        return self._register(handle, record)

    def attach_pool(self, pool: PoolCompile) -> int:
        """Register every compiled card of a mini pool by oracle id, then
        attach every card already on the battlefield (cards entering later
        re-register automatically from the registry)."""
        for result in pool.results.values():
            self.records[result.card.oracle_id] = result.card
        count = 0
        for card in sorted(self.world.cards, key=lambda h: h.index):
            identity = self.world.cards[card].identity
            record = self.records.get(identity.oracle_id)
            if record is None:
                continue
            self.handle_record[card] = record
            if self.world.zone_of(card).kind == ZONE_BATTLEFIELD:
                count += self._register(card, record)
            elif self.world.zone_of(card).kind == ZONE_GRAVEYARD:
                count += self._register_graveyard(card, record)
        return count

    def _register_graveyard(self, handle: Handle, record: CardRecord) -> int:
        """CR 113.6m: bind the record's graveyard-only triggers while the
        card is in a graveyard."""
        n = 0
        for idx, ability in enumerate(record.abilities):
            if functions_from_graveyard(ability):
                assert isinstance(ability, TriggeredAbility)
                self._check_trigger(ability, record.name)
                self.attached_graveyard[(handle, idx)] = ability
                n += 1
        return n

    def _register(self, handle: Handle, record: CardRecord) -> int:
        """Bind the record's TriggeredAbility nodes at (handle, idx), and
        register the record's CONTINUOUS half (KeywordAbility +
        StaticAbility nodes → the layer registry; ReplacementAbility nodes
        → the replacement registry) — one battlefield lifecycle for every
        ability shape. Check-then-commit: an unsupported event kind raises
        BEFORE the old bindings are dropped (flag, never degrade into a
        silent unlink)."""
        triggers = []
        for idx, ability in enumerate(record.abilities):
            if isinstance(ability, TriggeredAbility):
                self._check_trigger(ability, record.name)
                if functions_from_graveyard(ability):
                    continue  # CR 113.6m: it does not function here
                triggers.append((idx, ability))
        self.detach(handle, leaving=False)
        for idx, ability in triggers:
            self.attached[(handle, idx)] = ability
        # Loyalty: the frozen CardState has no loyalty field, so
        # the printed CardIdentity.loyalty is seeded into the counters map
        # (CounterKind.LOYALTY) at battlefield registration — the one path
        # covering BOTH first attach and re-entry (the lifecycle re-registers
        # through here). setdefault, so a mid-turn re-attach never overwrites
        # a loyalty the game already changed.
        state = self.executor.world.cards.get(handle)
        if state is not None and state.identity.loyalty is not None:
            try:
                printed = int(state.identity.loyalty)
            except ValueError:  # pragma: no cover - printed loyalty is numeric
                printed = 0
            if printed:
                state.counters.setdefault(CounterKind.LOYALTY.name, printed)
        # ORDER MATTERS: replacements.attach_source opens with its own
        # detach_source sweep (its idempotence rule), which would expire
        # the PreventionRecords that layers.attach_source registers for a
        # static PREVENT_EFFECT carrier (the Pursued Whale token's "can't
        # block"). Attach replacements FIRST, layers LAST, so the static
        # preventions are the final word for a freshly attached permanent.
        self.executor.replacements.attach_source(handle, record)
        self.executor.layers.attach_source(handle, record)
        return len(triggers)

    def detach(self, handle: Handle, *, leaving: bool = True) -> int:
        """Battlefield departure: drop the handle's live bindings (the
        oracle-id record stays, ready for the re-entry re-registration) —
        and its continuous layers and replacement records expire with
        it (their durations govern separately for records the permanent
        GRANTED elsewhere).

        ``leaving=False`` is the ATTACH-side idempotent refresh
        (attach_card/_register clear-then-rebind a handle that is
        ARRIVING, not departing). For a trigger-less permanent — an aura
        with only a StaticAbility — that refresh runs from _lifecycle AFTER
        the cast already attached its aura edge, and the departure
        sweep below would erase it, feeding the CR 704.5q SBA a false
        unattached read. The attachment drop belongs to DEPARTURES only."""
        keys = [key for key in self.attached if key[0] == handle]
        for key in keys:
            del self.attached[key]
        if not leaving:
            self.executor.layers.detach_source(handle)
            self.executor.replacements.detach_source(handle)
            return len(keys)
        # Attachment is battlefield-to-battlefield (CR 303.4c/117.12 —
        # when either side of an aura/equipment pair leaves, the attachment
        # relationship ends). The executor's attachment table drops every
        # edge touching the departing handle. (An emblem never departs:
        # only bind_emblem's leaving=False refresh detaches one.)
        ex = self.executor
        # Malefic Scythe: LKI capture BEFORE the prune — the edges
        # this sweep kills are the departing host's attachment truth for
        # the CREATURE_DIES row that follows the ZONE_CHANGE row in the
        # same journal batch (see Executor.detach_lki).
        ex.detach_lki[handle] = tuple(
            sorted(a for a, host in ex.attachments.items() if host == handle)
        )
        ex.attachments = {
            aura: host
            for aura, host in ex.attachments.items()
            if aura != handle and host != handle
        }
        self.executor.layers.detach_source(handle)
        self.executor.replacements.detach_source(handle)
        return len(keys)

    def _check_trigger(self, trigger: _AnyTrigger, card_name: str) -> None:
        event = trigger.event
        kind = type(event)
        if kind in _UNSUPPORTED_EVENTS:
            raise NotImplementedError(
                f"executor: {card_name} trigger event {kind.__name__} is "
                f"{_UNSUPPORTED_EVENTS[kind]}"
            )
        if isinstance(event, DeclareBlockersEvent) and event.count is not None:
            # only the blocker-limit prevention reads the count (a block row is
            # one pair, so a trigger matched on it would ignore the count)
            raise NotImplementedError(
                f"executor: {card_name} trigger event DeclareBlockersEvent with a blocker "
                "count has no trigger reader"
            )
        if trigger.once_per_event and not isinstance(
            event, (DeclareAttackersEvent, DamageDealtEvent, ZoneChangeEvent)
        ):
            # CR 603.2c: _queue gathers one event's occurrences only for a
            # declaration (its rows share a declare group), a zone change (its
            # rows share an atom boundary's batch) and a combat damage step (its
            # rows share the step); elsewhere the ability would trigger once per
            # occurrence, more often than printed.
            raise NotImplementedError(
                f"executor: {card_name} once-per-event trigger on {kind.__name__} has no "
                "event grouping"
            )

    # ------------------------------------------------------------ matching

    def _controller_memo(self, memo: dict, source: Handle, event: GameEvent) -> Handle:
        """:meth:`_controller_of`, looked up once per source within one
        event's matching pass (``memo`` lives for that pass only)."""
        ctrl = memo.get(source)
        if ctrl is None:
            ctrl = memo[source] = self._controller_of(source, event)
        return ctrl

    def on_events(self, upto: int | None = None) -> None:
        """Match every not-yet-seen journalled event against the attached
        triggers and the scheduled delayed triggers, queueing one
        TriggerInstance per match. The attach/detach lifecycle rides the
        same pass in journal order: a permanent ENTERING re-registers
        before matching (its own ETB trigger is live — IS_SOURCE sees it),
        a permanent LEAVING detaches only after matching (its own dies
        trigger still fires). ``upto`` stops before that journal
        position; it always falls between two atom boundaries, so it never
        splits a zone change from its dies row."""
        events = self.executor.journal.events
        end = len(events) if upto is None else min(upto, len(events))
        while self._seen_journal_len < end:
            event = events[self._seen_journal_len]
            self._seen_journal_len += 1
            self._lifecycle(event, attach=True)
            # Matching one event moves no card (queueing only appends trigger
            # instances), so each source's controller is looked up once per
            # event: per-card lookups dominated this pass.
            ctrl_of: dict = {}
            for (handle, _idx), ability in sorted(
                [*self.attached.items(), *self.attached_graveyard.items()],
                key=lambda kv: (str(kv[0][0]), kv[0][1]),
            ):
                ctrl = self._controller_memo(ctrl_of, handle, event)
                if self._match_node(ability.event, event, handle, ctrl):
                    self._queue(handle, ctrl, ability, event)
            # GRANTED triggers. A StaticAbility GRANT_ABILITY layer parks its
            # TriggeredAbility row in the layer registry — the ``attached``
            # map above only walks the card's PRINTED rows (Light of
            # Promise's granted life trigger lives here).
            # No battlefield gate, mirroring the attached loop's lifecycle:
            # the dies row must still see the grant while the aura is on.
            # Determinism: Handle order, then the registry's layer-seq order.
            layers = self.executor.layers
            for host in sorted(self.world.cards):
                granted_rows = layers.granted_abilities(host)
                if not granted_rows:
                    continue
                ctrl = self._controller_memo(ctrl_of, host, event)
                for granted in granted_rows:
                    node = granted.node
                    if isinstance(node, TriggeredAbility) and self._match_node(
                        node.event, event, host, ctrl
                    ):
                        self._queue(host, ctrl, node, event)
            # KEYWORD triggers (PROWESS / BATTALION). The compiler
            # folds printed keywords into CardRecord.keywords with NO
            # ability row (Blood Glutton compiles with an EMPTY abilities
            # tuple), so the engine constructs the canonical node itself —
            # EPHEMERAL IR construction: the frozen serialised IR and the
            # goldens on disk are untouched. Order: family, then the
            # registry's Handle-sorted holder list.
            for family in ("PROWESS", "BATTALION"):
                for host in layers.holders(Keyword[family]):
                    if (
                        host not in self.world.cards
                        or self.world.zone_of(host).kind != ZONE_BATTLEFIELD
                    ):
                        continue
                    node = self._keyword_node(family, host)
                    ctrl = self._controller_memo(ctrl_of, host, event)
                    if not self._match_node(node.event, event, host, ctrl):
                        continue
                    if family == "BATTALION" and self._group_size(event) < 3:
                        continue  # CR 508.2: a group of at least three
                    self._queue(host, ctrl, node, event)
            for entry in list(self.delayed):
                if self._match_node(
                    entry.node.event, event, entry.source, entry.controller
                ):
                    self._queue(
                        entry.source, entry.controller, entry.node, event, delayed=True
                    )
            self._lifecycle(event, attach=False)

    def _lifecycle(self, event: GameEvent, attach: bool) -> None:
        if event.kind == KIND_CREATURE_DIES and not attach:
            # The dies row was MATCHED above with the leaver still
            # attached (the ZONE_CHANGE row deferred its detach here), so
            # the dead card's own "when this dies" trigger queued its
            # firing. The departure now runs — still BEFORE any
            # resolution: firings drain in a later settle round, and
            # detach_lki is read at RESOLUTION time (quantity.py), so
            # the LKI lane is untouched by the deferral.
            handle = event.subject
            if handle is not None and handle in self._pending_dies_detach:
                self._pending_dies_detach.discard(handle)
                self.detach(handle)
            return
        if event.kind != KIND_ZONE_CHANGE or event.subject is None:
            return
        from_state, to_state = event.data[0], event.data[1]
        handle = event.subject
        if attach and to_state == ZONE_GRAVEYARD and from_state != ZONE_GRAVEYARD:
            record = self.handle_record.get(handle)
            if record is None and handle in self.world.cards:
                record = self.records.get(self.world.cards[handle].identity.oracle_id)
            if record is not None:
                self._register_graveyard(handle, record)  # CR 113.6m
        if not attach and from_state == ZONE_GRAVEYARD and to_state != ZONE_GRAVEYARD:
            for key in [k for k in self.attached_graveyard if k[0] == handle]:
                del self.attached_graveyard[key]  # it left the graveyard
        if attach:
            if to_state == ZONE_BATTLEFIELD:
                record = self.handle_record.get(handle)
                card = self.world.cards.get(handle)
                if record is None and card is not None and not card.identity.is_token:
                    # A dealt card an effect moves here (a fetched or ramped land) was never
                    # cast or played, so nothing bound its record (attach_pool runs before
                    # the decks are dealt): bind it by oracle id, as graveyard entry does.
                    # Not a token: its record comes only from CREATE_TOKEN, and the id is
                    # its name's hash, so the registry would give a vanilla token another's
                    # abilities.
                    record = self.records.get(card.identity.oracle_id)
                    if record is not None:
                        self.handle_record[handle] = record
                if record is not None and not any(
                    key[0] == handle for key in self.attached
                ):
                    self._register(handle, record)
        elif from_state == ZONE_BATTLEFIELD and to_state != ZONE_BATTLEFIELD:
            # When record_atom journalled this card's CREATURE_DIES row
            # immediately after this row (same diff iteration), defer the
            # detach to it so the IS_SOURCE dies trigger is still attached
            # when its own event is matched. Any other departure (bounce,
            # exile, hand, or a graveyard move with no dies twin) detaches
            # on the spot.
            events = self.executor.journal.events
            nxt = (
                events[self._seen_journal_len]
                if self._seen_journal_len < len(events)
                else None
            )
            if (
                nxt is not None
                and nxt.kind == KIND_CREATURE_DIES
                and nxt.subject == handle
            ):
                self._pending_dies_detach.add(handle)
            else:
                self.detach(handle)

    def _queue(
        self,
        source: Handle,
        controller: Handle,
        node: _AnyTrigger,
        event: GameEvent,
        additional: bool = False,
        delayed: bool = False,
        carried: _Carried | None = None,
        gathered: tuple[Handle, ...] | None = None,
    ) -> None:
        if source in self.quarantined:
            # Tripwire guard: a flagged loop source never queues
            # again this game (its firing was already recorded loudly in
            # executor.trigger_loops).
            return
        if not delayed and source in self.executor.phased_out:
            # CR 702.26b: a phased-out permanent's triggered abilities (its
            # printed, granted and keyword ones, and the AbilityTriggerEvent
            # subscribers) do not trigger. A delayed trigger is not an
            # ability of its source (CR 603.7) and still triggers.
            return
        if node.once_per_event:
            # The bind-time refusal for every flagged node that triggers: a granted
            # trigger (GRANT_ABILITY) is never bound, so it is checked here.
            record = self.handle_record.get(source)
            self._check_trigger(node, record.name if record is not None else str(source))
        if not additional and gathers_objects(node.event, node.once_per_event):
            # CR 603.2c, 508.3d: "whenever you attack", "whenever one or more
            # creatures you control attack" and "whenever one or more tokens you
            # control enter" trigger once on the whole event: the declaration, or
            # the objects one atom boundary moved (GameEvent.batch). Its rows fan
            # out one per object, so ONE instance is queued per ability per event
            # (Tide Skimmer's "attack with two or more" fires once); two identical
            # creatures are different sources. The instance holds every object of
            # the event its spec matches, judged as the event occurred (CR 603.10:
            # a departed one by its last known information): "they" and "that
            # many". A trigger without the flag ("whenever a creature you control
            # attacks", CR 508.3a) queues one instance per object it matches, that
            # object its event (Hooded Blightfang, Basri, Devoted Paladin's -1).
            group = event.declare_group if event.kind == KIND_DECLARE_ATTACKERS else event.batch
            key = (source, id(node), event.kind, group)
            if key in self._gathered_queued:
                return
            self._gathered_queued.add(key)
            gathered = tuple(
                e.subject
                for e in self._occurrences(event)
                if e.subject is not None and self._match_node(node.event, e, source, controller)
            )
        if (
            not additional
            and event.kind == KIND_DAMAGE
            and event.is_combat
            and isinstance(node.event, DamageDealtEvent)
            and (node.event.source is None or node.once_per_event)
        ):
            # CR 510.2, 603.2c: a combat damage step deals all its damage at once, as
            # one event, so "whenever this creature is dealt damage" triggers once
            # however many creatures dealt it damage (Sporeweb Weaver's ruling),
            # and "that much damage" is all of it (Brash Taunter). A once-per-event
            # trigger over dealers ("whenever one or more Cats you control deal
            # combat damage to a player", Feline Sovereign) triggers once per step
            # for each player those dealers damaged. Any other trigger that names
            # the dealer ("a source you control deals", "this creature deals combat
            # damage to a player") triggers per source, row by row. Any other DAMAGE
            # row is a whole event already: one DEAL_DAMAGE atom, one dealer.
            whole = self._combat_damage_event(event, node, source, controller)
            if whole is None:
                return
            event = whole
        if not additional and node.condition is not None:
            # CR 603.4: an intervening "if" is checked when the trigger event
            # occurs, and the ability triggers only if it is true. The matcher
            # runs before the settle's state-based sweep recomputes the layers,
            # so they are brought up to date first (CR 603.10: the effects that
            # exist right after the event; Warded Battlements' +1/+0 on the
            # creatures just declared as attackers). An extra instance (CR
            # 603.2d, ``additional``) is queued later, when the carrier
            # resolves; its original passed this check.
            self.executor.layers.recompute()
            if not self._condition_holds(
                node, event, source, self._ctx(source, controller, event)
            ):
                return
        self._seq += 1
        instance = self.world.queue_trigger(
            source, controller, f"{event.kind}#{self._seq}"
        )
        payload = _Firing(
            source=source,
            controller=controller,
            node=node,
            event=event,
            seq=self._seq,
            carried=carried,
            gathered=gathered,
        )
        self.firings[instance.clock] = payload
        if not additional:
            # Sanctum of All ("whenever another Shrine you control's
            # ability triggers"): an ordinary queued firing feeds every
            # AbilityTriggerEvent subscriber in a SYNTHETIC match pass --
            # no journal row is written, and `additional` firings (CR
            # 603.2d: an extra trigger has no triggering event) never feed
            # it again, which is what keeps two extra-trigger carriers from
            # chasing each other.
            self._fan_ability_triggers(payload)

    def _occurrences(self, event: GameEvent) -> list[GameEvent]:
        """The rows of the one event ``event`` is an occurrence of (CR 603.2c): the attacker rows
        of its declaration (one declare group), or the zone changes of its atom boundary (one
        batch, ``GameEvent.batch``). Each is journalled whole before the binder matches any of
        its rows."""
        journal = self.executor.journal
        if event.kind == KIND_DECLARE_ATTACKERS:
            return [
                e
                for e in journal.turn_window()
                if e.kind == KIND_DECLARE_ATTACKERS and e.declare_group == event.declare_group
            ]
        rows = []
        for e in reversed(journal.events):
            if e.clock < event.batch:  # a batch's rows begin at its own clock
                break
            if e.kind == KIND_ZONE_CHANGE and e.batch == event.batch:
                rows.append(e)
        return rows[::-1]

    def _combat_damage_event(
        self, event: GameEvent, node: _AnyTrigger, source: Handle, controller: Handle
    ) -> GameEvent | None:
        """The combat damage the step of ``event`` (a combat DAMAGE row ``node`` matched)
        dealt to its recipient, as the one event it is (CR 510.2), counting the rows
        ``node`` matches (its dealer filter; with none, every row to that recipient):
        ``event`` with their total amount when it is the first of them, else None (the
        event was already matched on that row). The journal has one row per dealer;
        the whole step is journalled before any of it is matched."""
        rows = [
            e
            for e in self.executor.journal.turn_window()
            if e.kind == KIND_DAMAGE
            and e.subject == event.subject
            and e.combat_step == event.combat_step
            and (e.clock == event.clock or self._match_node(node.event, e, source, controller))
        ]
        if rows[0].clock != event.clock:
            return None
        return replace(event, data=(sum(e.amount for e in rows), *event.data[1:]))

    def _fan_ability_triggers(self, payload: _Firing) -> None:
        """Queue one firing per AbilityTriggerEvent subscriber whose
        filter matches the triggering ability's SOURCE permanent, in the
        subscriber's coordinates (IS_SOURCE = the subscriber, so "another"
        is the filter's own FNot(IS_SOURCE)). The synthetic event carries
        the matched payload so the TRIGGER_ADDITIONAL verb can re-queue
        it; the subscriber's condition (Sanctum's "six or more Shrines")
        gates like any other trigger's: when it triggers and again at resolve
        time (CR 603.4). CR 603.2d: an
        extra-trigger carrier's OWN firings never fan out — the family's
        effect does not apply to instances of itself, which is what keeps
        two carriers from chasing each other (each adds its one extra per
        ORIGINAL firing; the extras carry no triggering event)."""
        effect = payload.node.effect
        if isinstance(effect, Atom) and effect.verb is Verb.TRIGGER_ADDITIONAL:
            return
        subscribers = [
            (handle, ability)
            for (handle, _idx), ability in sorted(
                self.attached.items(), key=lambda kv: (str(kv[0][0]), kv[0][1])
            )
            if isinstance(ability.event, AbilityTriggerEvent)
            and handle != payload.source
        ]
        for handle, ability in subscribers:
            ctrl = self._controller_of(handle)
            synth = GameEvent(
                clock=-1,
                kind=KIND_ABILITY_TRIGGERED,
                subject=payload.source,
                cause=handle,
                cause_verb="TRIGGER",
                data=(payload,),
            )
            ctx = self._ctx(handle, ctrl, synth)
            if eval_filter(ability.event.filter, payload.source, ctx):
                self._queue(handle, ctrl, ability, synth)

    def _keyword_node(self, family: str, handle: Handle) -> TriggeredAbility:
        """The canonical compiled-shape node for a printed keyword
        trigger, built ONCE per (family, holder) and cached. The
        shapes mirror the frozen-IR precedent (Quirion Dryad's compiled
        cast-trigger is exactly prowess minus the type exclusion):
        PROWESS  — "whenever you cast a noncreature spell" → +1/+1 until
        end of turn (PtDelta lanes, DurationEot sweep);
        BATTALION — "whenever this creature attacks alone-or-not" gated
        at the queue site on the CR 508.2 group-of-three → a +1/+1
        counter (the Dryad's PUT_COUNTER shape)."""
        key = (family, handle)
        node = self._kw_nodes.get(key)
        if node is not None:
            return node
        target = Selector(
            count=QConst(1),
            mode=SelectorMode.CHOOSE,
            filter=FAtom(pred=FAtomPred.IS_SOURCE),
            zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
        )
        if family == "PROWESS":
            node = TriggeredAbility(
                event=CastSpellEvent(
                    filter=FNot(
                        inner=FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature")
                    ),
                    actor=FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
                ),
                condition=None,
                effect=Atom(
                    verb=Verb.MODIFY_PT,
                    args=AtomArgs(
                        pairs=(
                            (
                                "power",
                                PtDelta(
                                    direction=PtDirection.INCREASE,
                                    magnitude=QConst(1),
                                ),
                            ),
                            (
                                "toughness",
                                PtDelta(
                                    direction=PtDirection.INCREASE,
                                    magnitude=QConst(1),
                                ),
                            ),
                            ("duration", DurationEot()),
                            ("target", target),
                        )
                    ),
                ),
            )
        else:  # BATTALION
            node = TriggeredAbility(
                event=DeclareAttackersEvent(filter=FAtom(pred=FAtomPred.IS_SOURCE)),
                condition=None,
                effect=Atom(
                    verb=Verb.PUT_COUNTER,
                    args=AtomArgs(
                        pairs=(
                            ("count", QConst(1)),
                            ("counter_kind", CounterKind.PLUS_1_PLUS_1),
                            ("target", target),
                        )
                    ),
                ),
            )
        self._kw_nodes[key] = node
        return node

    def _group_size(self, event: GameEvent) -> int:
        """CR 508.2 population for the BATTALION gate: how many attackers
        share this DECLARE_ATTACKERS row's declaration group. The declare
        step journalled EVERY row inside one atom boundary, so the whole
        declaration is already in the journal when the drain first sees
        any row of it — a pure journal read, no executor side-state."""
        return sum(
            1
            for other in self.executor.journal.events
            if other.kind == KIND_DECLARE_ATTACKERS and other.data == event.data
        )

    def _match_node(
        self, node: EventSpec, event: GameEvent, source: Handle, controller: Handle
    ) -> bool:
        """Does one IR event-spec node subscribe to one journalled event?
        Filters and counts evaluate in a match ctx (source = the bound
        permanent, controller = its controller) via the shared evaluator —
        unsupported preds/quantities raise through it (flag, don't degrade)."""
        kind = event.kind
        if kind == KIND_ZONE_CHANGE:
            if isinstance(node, ZoneChangeEvent):
                return self._match_zone_change(node, event, source, controller)
            if isinstance(node, SacrificeEvent):
                return self._match_sacrifice(node, event, source, controller)
            return False
        if kind == KIND_CREATURE_DIES and isinstance(node, CreatureDiesEvent):
            assert event.subject is not None  # the journal always names the dead
            ctx = self._ctx(source, controller, event)
            return eval_filter(node.filter, event.subject, ctx)
        if kind == KIND_CARD_DRAWN and isinstance(node, CardDrawnEvent):
            ctx = self._ctx(source, controller, event)
            drawer, ordinal = event.draw
            if node.actor is not None and not eval_filter(node.actor, drawer, ctx):
                return False
            return node.ordinal is None or node.ordinal == ordinal
        if kind == KIND_COUNTER_PLACED and isinstance(node, CounterPlacedEvent):
            return self._match_counter(node, event, source, controller)
        if kind == KIND_TAP_STATE and isinstance(node, TapStateEvent):
            if node.tapped != event.tapped_new:
                return False
            assert event.subject is not None
            ctx = self._ctx(source, controller, event)
            return eval_filter(node.filter, event.subject, ctx)
        if kind == KIND_TURN_PHASE and isinstance(node, TurnPhaseEvent):
            phase_name, active = event.phase
            if node.phase.name != phase_name:
                return False
            ctx = self._ctx(source, controller, event)
            return node.actor is None or eval_filter(node.actor, active, ctx)
        if kind == KIND_DECLARE_ATTACKERS and isinstance(node, DeclareAttackersEvent):
            # The attack feed. The filter reads the DECLARED creature
            # (IS_SOURCE = "whenever this creature attacks"); the optional
            # ``attacked`` filter reads the attacker's ATTACKED
            # object off the executor's attack record: the defending player
            # or a planeswalker that player controls (CR 508.1b).
            assert event.subject is not None  # the row names the attacker
            ctx = self._ctx(source, controller, event)
            if node.attacked is not None:
                attacked = self.executor.attacked.get(event.subject)
                if attacked is None or not eval_filter(node.attacked, attacked, ctx):
                    return False
            return eval_filter(node.filter, event.subject, ctx)
        if kind == KIND_DECLARE_BLOCKERS and isinstance(
            node, (DeclareBlockersEvent, BecomesBlockedEvent)
        ):
            # The block feed, ONE row per declaration pair (subject =
            # the BLOCKER, data = (attacker, group)). A DeclareBlockers-
            # Event node reads filter/SUBJECT over the blocker and the
            # BLOCKED slot over the attacker (Snarespinner's "blocks a
            # creature with flying", Elder Gargaroth's "attacks or blocks",
            # the Pirate/Shacklegeist prevention shapes share these slots).
            # A BecomesBlockedEvent node is anchored: the blocked partici-
            # pant must BE the trigger's source (Gloom Sower "whenever
            # THIS creature becomes blocked by a creature") — the grammar
            # gives the node no subject field of its own, the event name
            # carries the anchor.
            assert event.subject is not None  # the row names the blocker
            ctx = self._ctx(source, controller, event)
            blocker = event.subject
            attacker, _group = event.declare_blockers
            if isinstance(node, DeclareBlockersEvent):
                if node.subject is not None and not eval_filter(
                    node.subject, blocker, ctx
                ):
                    return False
                if node.blocked is not None and not eval_filter(
                    node.blocked, attacker, ctx
                ):
                    return False
                return eval_filter(node.filter, blocker, ctx)
            if attacker != source:
                return False
            return eval_filter(node.filter, blocker, ctx)
        if kind == KIND_DAMAGE and isinstance(node, DamageDealtEvent):
            return self._match_damage(node, event, source, controller)
        if (kind == KIND_LIFE_GAINED and isinstance(node, LifeGainedEvent)) or (
            isinstance(node, LifeLostEvent)
            and kind in (KIND_LIFE_LOST, KIND_DAMAGE)
            and event.subject is not None
            and event.subject.namespace == "player"
        ):
            # Life gained, or life lost, its twin: a player is dealt damage by
            # losing that much life (CR 120.3a; the DAMAGE row of a player is
            # journalled from the life change), and every other loss, a payment
            # included (CR 119.4), is a LIFE_LOST row.
            assert event.subject is not None  # the gaining or losing player
            ctx = self._ctx(source, controller, event)
            if node.actor is not None and not eval_filter(node.actor, event.subject, ctx):
                return False
            return node.ordinal is None or node.ordinal == self._life_ordinal(event)
        if kind == KIND_CAST and isinstance(node, CastSpellEvent):
            return self._match_cast(node, event, source, controller)
        if (
            kind == KIND_TARGETING
            and event.cause_verb == "TARGET"
            and isinstance(node, TargetingEvent)
        ):
            # Warden of the Woods: the designation feed — the filter
            # reads the DESIGNATED object (IS_SOURCE = "whenever THIS
            # becomes the target of a spell or ability"). A PLAYER subject
            # (a Duress-shaped cast) is answered with the same honest
            # three-valued shape as the damage lane: card-shape preds are
            # FALSE outright, undecidable preds raise.
            assert event.subject is not None  # the row names its object
            ctx = self._ctx(source, controller, event)
            # The actor filter reads the targeting spell's or ability's
            # controller, journalled as data[1] (events.emit_targeting) — "a
            # spell or ability an opponent controls" (Warden of the Woods).
            if node.actor is not None:
                actor = event.data[1]
                assert isinstance(actor, Handle)  # emit_targeting's (source, actor)
                if not eval_filter(node.actor, actor, ctx):
                    return False
            if event.subject.namespace == "player":
                if _is_subject_identity(node.filter):
                    return False
                return _player_subject_verdict(node.filter, event.subject, ctx)
            return eval_filter(node.filter, event.subject, ctx)
        if kind == KIND_ABILITY_ACTIVATED and isinstance(node, AbilityActivatedEvent):
            # One row per activation. ``kind`` reads the row's own
            # classification, made at activation time by the one CR 605.1a
            # classifier: NON_MANA skips mana abilities, LOYALTY keeps only
            # abilities that paid a loyalty symbol (CR 606.2, a [0]
            # included). ``actor`` reads the
            # ACTIVATING player (the row's cause), ``source`` the object
            # whose ability it is (Keral Keep Disciples' "a Chandra
            # planeswalker" — a Basri row evaluates FALSE here).
            assert event.subject is not None  # the row names the object
            assert event.cause is not None  # the row names its activator
            _idx, mana, loyalty = event.activation
            if node.kind is AbilityKind.NON_MANA and mana:
                return False
            if node.kind is AbilityKind.LOYALTY and loyalty is None:
                return False
            ctx = self._ctx(source, controller, event)
            if node.actor is not None and not eval_filter(node.actor, event.cause, ctx):
                return False
            return eval_filter(node.source, event.subject, ctx)
        return False  # no subscriber shape for this journalled kind

    def _match_cast(
        self, node: CastSpellEvent, event: GameEvent, source: Handle, controller: Handle
    ) -> bool:
        """The CAST feed — CR 603.2's "whenever you cast" half. The
        journalled tuple (``GameEvent.cast``) carries (caster, per-turn
        ordinal, spell kind, from-zone, X): ``controller`` scopes whose
        cast (OPPONENT = "an opponent casts" — Mangara, Ghostly Pilferer),
        ``ordinal`` is the Nth cast by THAT caster this turn among the
        spells the node describes (:meth:`_fitting_cast_ordinal` — "whenever
        you cast your second spell", Double Vision's first instant or sorcery
        ordinal 1), and the zone pair
        is mutually exclusive in the grammar: ``from_zone`` must
        equal the cast's source zone, ``from_zone_not`` EXCLUDES it
        (Ghostly Pilferer: "from anywhere other than their hand" — a zone
        whose controller ref scopes the caster, not the zone's owner: the
        cast came from the caster's zones). The filter reads the SPELL
        card (subject of the CAST row) — TYPE_EQ/SUBTYPE_EQ/COLOR_HAS over
        it; Quirion Dryad's "a spell that's white, blue, black, or red" is
        the FOr of COLOR_HAS W/U/B/R (any of them, CR 105.2)."""
        caster = event.cast[0]
        ctx = self._ctx(source, controller, event)
        if node.actor is not None and not eval_filter(node.actor, caster, ctx):
            return False
        if not self._cast_fits(node, event, source, controller):
            return False
        return node.ordinal is None or node.ordinal == self._fitting_cast_ordinal(
            node, event, source, controller
        )

    def _cast_fits(
        self, node: CastSpellEvent, event: GameEvent, source: Handle, controller: Handle
    ) -> bool:
        """Does one CAST row's spell fit the node's spell description: its
        from-zone pair and its filter (the SPELL card is the row's subject)?"""
        caster, _ordinal, _kind, from_zone, _x, _kicked = event.cast
        ctx = self._ctx(source, controller, event)
        if node.from_zone is not None and not self._cast_zone_matches(
            node.from_zone, caster, from_zone, ctx
        ):
            return False
        if node.from_zone_not is not None and self._cast_zone_matches(
            node.from_zone_not, caster, from_zone, ctx
        ):
            return False
        assert event.subject is not None  # the CAST row names the spell card
        # Gnarlback Rhino ("whenever you cast a spell that targets this
        # creature"): TARGETS_SOURCE asks whether the judged spell targets the filter's
        # source, and reads the ``target`` binding (quantity._eval_atom). This ctx is the
        # trigger's own, which binds no target, so the cast spell's
        # declared targets (its stack frame, CR 601.2c) are bound here.
        ctx.bindings["target"] = next(
            (
                list(frame.declared_targets)
                for frame in self.executor.stack.frames
                if frame.handle == event.subject
            ),
            [],
        )
        return eval_filter(node.filter, event.subject, ctx)

    def _fitting_cast_ordinal(
        self, node: CastSpellEvent, event: GameEvent, source: Handle, controller: Handle
    ) -> int:
        """The ordinal a CastSpellEvent's ``ordinal`` compares with (Double
        Vision): the number of spells THIS caster cast this turn that fit
        the node's description, up to and including this one. "Your first
        instant or sorcery spell each turn" is the first
        instant or sorcery, so a creature cast before it does not use it up;
        the journal row's own ordinal counts every spell, which is exactly
        this count for an unfiltered node (Mangara's "second spell"). The
        journal's turn window holds every CAST row since the turn began,
        including casts made before this permanent arrived, which the count
        must see. Earlier rows are judged now: the pool's ordinal filters read
        the spell's types and colours, which do not change as it resolves."""
        caster = event.cast[0]
        count = 0
        for row in self.executor.journal.turn_window():
            if row.kind != KIND_CAST or row.clock > event.clock or row.cast[0] != caster:
                continue
            if self._cast_fits(node, row, source, controller):
                count += 1
        return count

    def _life_ordinal(self, event: GameEvent) -> int:
        """The ordinal a LifeGainedEvent's or LifeLostEvent's ``ordinal`` compares with: the
        number of times this row's player gained (or lost) life this turn, up to and including
        this row (CardDrawnEvent.ordinal's contract, counted here instead of stamped on the
        row). One LIFE_GAINED row is one gain (an atom's net change for one player); a loss is
        a LIFE_LOST row or one player DAMAGE row, one per source, so the creatures that damage a
        player in one combat damage step are that many losses, of which exactly one is first.
        Every row of the row's own turn counts (back to that turn's upkeep marker, as
        ``EventJournal.turn_window`` reads a turn), rows from before the permanent arrived too
        (Vengeful Warchief's ruling)."""
        gain = event.kind == KIND_LIFE_GAINED
        kinds = (KIND_LIFE_GAINED,) if gain else (KIND_LIFE_LOST, KIND_DAMAGE)
        count = 0
        for row in reversed(self.executor.journal.events):
            if row.clock > event.clock:
                continue
            if row.kind == KIND_TURN_PHASE and row.data[0] == Phase.UPKEEP.name:
                break
            if row.kind in kinds and row.subject == event.subject:
                count += 1
        return count

    def _cast_zone_matches(
        self, zone_ir: Zone, caster: Handle, from_zone: str | None, ctx: ExecCtx
    ) -> bool:
        """One CastSpellEvent zone endpoint vs the journalled source zone.
        The zone KIND must equal the cast's origin zone, and the zone's
        controller ref scopes the CASTER (grammar reading: "from your
        graveyard" = the caster's graveyard — unlike ZoneChangeEvent,
        whose endpoint scopes the zone's owner)."""
        want = ZONE_KIND_TO_STATE.get(zone_ir.kind)
        if want is None or from_zone is None or want != from_zone:
            return False
        if zone_ir.controller is ControllerRef.ANY:
            return True
        return controller_matches(zone_ir.controller, caster, ctx)

    def _match_zone_change(
        self,
        node: ZoneChangeEvent,
        event: GameEvent,
        source: Handle,
        controller: Handle,
    ) -> bool:
        from_state, to_state, owner_before, owner_after = event.zone_move
        ctx = self._ctx(source, controller, event)
        if not self._zone_matches(node.from_zone, from_state, owner_before, ctx):
            return False
        if not self._zone_matches(node.to_zone, to_state, owner_after, ctx):
            return False
        if node.subject is None:
            return True
        assert event.subject is not None  # a zone move always names its subject
        return eval_filter(node.subject, event.subject, ctx)

    def _zone_matches(
        self,
        zone_ir: Zone,
        state_kind: str | None,
        zone_owner: Handle | None,
        ctx: ExecCtx,
    ) -> bool:
        """One ZoneChangeEvent endpoint vs the journalled move. A created
        object's ``from`` (None) matches ANY — an ETB from nowhere is an ETB
        from anywhere. STACK/PLAYER endpoints name no card zone and never
        match. OWNER scopes to the card's owner, who in this frozen model
        is exactly the zone owner."""
        if zone_ir.kind is not ZoneKind.ANY:
            want = ZONE_KIND_TO_STATE.get(zone_ir.kind)
            if want is None or state_kind is None or want != state_kind:
                return False
        ref = zone_ir.controller
        if ref is ControllerRef.ANY or zone_ir.kind is ZoneKind.ANY:
            return True
        if ref is ControllerRef.OWNER:
            return True  # zone owner IS the card's owner here
        if zone_owner is None:
            return False
        return controller_matches(ref, zone_owner, ctx)

    def _match_sacrifice(
        self, node: SacrificeEvent, event: GameEvent, source: Handle, controller: Handle
    ) -> bool:
        from_state, to_state, owner_before, _after = event.zone_move
        if (
            from_state != ZONE_BATTLEFIELD
            or to_state != ZONE_GRAVEYARD
            or event.cause_verb != "SACRIFICE"
        ):
            return False
        assert owner_before is not None  # a battlefield move has an owner
        ctx = self._ctx(source, controller, event)
        return node.actor is None or eval_filter(node.actor, owner_before, ctx)

    def _match_counter(
        self,
        node: CounterPlacedEvent,
        event: GameEvent,
        source: Handle,
        controller: Handle,
    ) -> bool:
        kind_name, placed = event.counter
        if node.counter_kind.name != kind_name:
            return False
        assert event.subject is not None
        ctx = self._ctx(source, controller, event)
        if not eval_filter(node.filter, event.subject, ctx):
            return False
        if node.count is None:
            return True
        return placed >= resolve(node.count, ctx)

    def _match_damage(
        self,
        node: DamageDealtEvent,
        event: GameEvent,
        source: Handle,
        controller: Handle,
    ) -> bool:
        subject = event.subject
        ctx = self._ctx(source, controller, event)
        # The node's SCOPE fields: Garruk's Harbinger's "deals combat damage
        # to a player" and Subira's delayed tail both compile ``combat: true``
        # + a ``source`` filter over the DEALER. The DAMAGE row carries the
        # dealer as ``cause`` and the combat flag as the optional second data
        # element.
        if node.combat is not None and event.is_combat != node.combat:
            return False
        if node.source is not None:
            dealer = event.cause
            if dealer is None or not eval_filter(node.source, dealer, ctx):
                return False
        if subject is not None and subject.namespace == "player":
            if _is_subject_identity(node.filter):
                return False  # a player is never the source CARD (Brash Taunter)
            # Hooded Blightfang: the player-damage row must be
            # ANSWERABLE by a card-shape filter — the Blightfang's "deals
            # combat damage to a planeswalker" node reads SUPERTYPE_EQ over
            # its subject, and a player is honestly not one: FALSE, not a
            # crash. Undecidable preds raise.
            return _player_subject_verdict(node.filter, subject, ctx)
        assert subject is not None  # a damage event always names its subject
        return eval_filter(node.filter, subject, ctx)

    # -------------------------------------------------------------- fire

    def put_waiting(self) -> int:
        """CR 603.3b: every ability that triggered since a player last received
        priority goes on the stack, the active player's first, then the next
        player's in turn order (APNAP), each player's in an order that player
        chooses (:meth:`_resolution_order`); modes and targets are chosen as
        each goes on (:meth:`_put`), and one with no legal mode or required
        target is removed (603.3d). Returns how many went on the stack."""
        world = self.world
        waiting = sorted(world.triggers, key=lambda t: t.clock)  # the order they triggered
        world.triggers.clear()
        order = [self.firings.pop(t.clock) for t in waiting]
        seats = world.player_order
        first = seats.index(world.active_player) if world.active_player is not None else 0
        put = 0
        for controller in seats[first:] + seats[:first]:  # APNAP: the active player's go on first
            mine = [p for p in order if p.controller == controller]
            for payload in reversed(self._resolution_order(controller, mine)):
                obj = self._put(payload)  # the last to resolve goes on first
                if obj is not None:
                    self.executor.stack.push(obj)
                    put += 1
        return put

    def _resolution_order(self, controller: Handle, mine: list[_Firing]) -> list[_Firing]:
        """CR 603.3b: ``controller`` orders its own simultaneous triggers (``mine``, in
        the order they triggered), returned in resolution order. While two or more
        different ones are left it is asked which resolves next
        (``trigger:<seat>:<digest>``). An option is a trigger's source, ``card:12``, or
        ``card:12:2`` for a second, different trigger of the same source; copies of
        one ability from one source and one event share an option, since their order
        cannot matter (two triggers of a doubled ability, CR 603.2d)."""
        tokens: list[str] = []
        per_source: dict[Handle, list[_Firing]] = {}
        for p in mine:
            same = per_source.setdefault(p.source, [])
            twin = next((q for q in same if q.node == p.node and q.event == p.event), None)
            if twin is None:
                same.append(p)
                twin = p
            tokens.append(str(p.source) if same[0] is twin else f"{p.source}:{same.index(twin) + 1}")
        left = list(zip(tokens, mine, strict=True))
        ordered: list[_Firing] = []
        while len({t for t, _ in left}) > 1:
            vocab = tuple(dict.fromkeys(t for t, _ in left))
            answer = self.executor.decisions.take(
                vocab, f"trigger:{controller}:{site_digest(vocab)}", seat=controller
            )
            k = next(i for i, (t, _) in enumerate(left) if t == answer)
            ordered.append(left.pop(k)[1])
        return ordered + [p for _, p in left]

    def quarantine(self, per_source: dict[Handle, int]) -> None:
        """The trigger-loop tripwire (``Executor._resolve_top``): since the stack was
        last empty ``MAX_TRIGGER_FIRES`` triggered abilities resolved and it still holds one.
        The tripwire GUARDS rather than kill the game. The culprit is the source
        whose triggers resolved MOST in it — its effect's own events re-arm it
        (Chandra's Incinerator's "whenever you deal noncombat damage" trigger
        eating its own damage row). QUARANTINE it: its triggered abilities leave
        the stack, its queued firings are dropped, its _queue is blocked for the
        rest of the game, and the event is recorded loudly in
        executor.trigger_loops — "flag it, never run it". With eight sources
        already quarantined in ONE game the next runaway raises: then the state
        itself is the anomaly, not a card."""
        culprit = next(
            (
                src
                for src, _n in sorted(per_source.items(), key=lambda kv: (-kv[1], str(kv[0])))
                if src not in self.quarantined
            ),
            None,
        )
        if culprit is None or len(self.quarantined) >= 8:
            raise RuntimeError(
                "executor: trigger-loop tripwire — "
                f"{MAX_TRIGGER_FIRES} triggers resolved since the stack was last empty "
                "and it is still growing (self-retriggering loop: flag it, never run it)"
            )
        record = self.handle_record.get(culprit)
        self.quarantined.add(culprit)
        stack = self.executor.stack.frames
        on_stack = [
            o for o in stack if o.spell_kind == "TRIGGERED" and o.source == culprit
        ]
        for obj in on_stack:
            stack.remove(obj)
        dropped = [t for t in self.world.triggers if t.source == culprit]
        for t in dropped:
            self.world.triggers.remove(t)
            self.firings.pop(t.clock, None)
        self.executor.trigger_loops.append(
            f"{culprit} ({getattr(record, 'name', culprit)!r}): "
            f"self-retriggering after {per_source.get(culprit, 0)} "
            f"drain fires — quarantined, {len(dropped) + len(on_stack)} queued "
            "firings dropped"
        )

    def pending_references(self) -> frozenset[Handle]:
        """The objects the waiting triggers (queued, or on the stack) still
        name: their source and their event's subject and cause. A token that left the battlefield stays in the
        world (as its own last-known information) until the triggers its leaving
        caused have resolved; see ``Executor._cease_tokens``."""
        out: set[Handle] = set()
        waiting = [(p.source, p.event) for p in self.firings.values()]
        waiting += [
            (o.source, o.event)
            for o in self.executor.stack.frames
            if o.spell_kind == "TRIGGERED"
        ]
        for source, event in waiting:
            out.add(source)
            for handle in (event.subject, event.cause):
                if isinstance(handle, Handle):
                    out.add(handle)
        # What a reflexive trigger read of its creating resolution ("the sacrificed creature"),
        # waiting or on the stack.
        carried = [p.carried.bindings for p in self.firings.values() if p.carried is not None]
        carried += [
            o.ctx.bindings
            for o in self.executor.stack.frames
            if o.spell_kind == "TRIGGERED" and o.event.kind == KIND_REFLEXIVE
        ]
        for bindings in carried:
            for value in bindings.values():
                out.update(h for h in (value if isinstance(value, list) else [value])
                           if isinstance(h, Handle))
        return frozenset(out)

    def cease_triggered_before(self, mark: int) -> int:
        """CR 724.1a: when an effect ends the turn, the abilities that
        triggered before that process began and were never put onto the
        stack cease to exist. The journal rows before ``mark`` (where the
        END_TURN atom ran) are matched first, so the attach/detach lifecycle
        still runs for them; then every queued firing is dropped, those and
        any a drain had not reached yet. Returns how many ceased."""
        self.on_events(upto=mark)
        ceased = list(self.world.triggers)
        for instance in ceased:
            self.world.triggers.remove(instance)
            self.firings.pop(instance.clock, None)
        return len(ceased)

    @staticmethod
    def _condition_holds(
        node: _AnyTrigger, event: GameEvent, source: Handle, ctx: ExecCtx
    ) -> bool:
        """CR 603.4: a trigger's condition (the intervening "if": "When X, if Y,
        Z"), a Filter over the event's subject, or over the source when the event
        names none, in the trigger's own coordinates. It is read twice by this one
        function: when the trigger event occurs (``_queue``: false means the
        ability does not trigger at all) and again as the ability resolves
        (``resolve``: false means it does nothing)."""
        if node.condition is None:
            return True
        subject = event.subject if event.subject is not None else source
        return eval_filter(node.condition, subject, ctx)

    def _put(self, payload: _Firing):
        """CR 603.3: the triggered ability is put on the stack, its mode chosen
        (603.3c) and its targets (603.3d, :meth:`_designate`) as it goes there;
        with no legal mode or no legal target for a required slot it is removed
        (None). Returns the :class:`~MTG_bot.core.executor.stack.StackObject`,
        which carries the context the choices were made in."""
        from MTG_bot.core.executor.stack import StackObject

        event = payload.event
        ctx = self._ctx(payload.source, payload.controller, event)
        if payload.carried is not None:
            # CR 603.12: a reflexive trigger reads the resolution that created it.
            ctx.bindings.update(payload.carried.bindings)
            ctx.x_value = payload.carried.x_value
            ctx.event, ctx.event_amount = payload.carried.event, payload.carried.event_amount
        if payload.gathered is not None:
            # CR 603.2c: a gathered event names every object it gathered (_queue), not
            # one row's: "they" (Selector(referent="event"), Angelic Guardian) is all of
            # them, and "that many" (QProp("event", THAT_MANY_COUNT), Woodland Champion,
            # Basri Ket's -2) their number, the ``gathered`` register, which keeps the
            # ones that leave before resolution (their rulings; :meth:`resolve`).
            # THAT_MANY_COUNT reads the in-resolution ``result`` register first
            # (Kinetic Augur's precedence).
            ctx.bindings["event"] = list(payload.gathered)
            ctx.bindings["gathered"] = list(payload.gathered)
        node = payload.node
        designated = False  # targets chosen through _designate, checked again at resolution
        if isinstance(node.effect, Choose) and self._modes_need_targets(node.effect):
            # CR 603.3c: a modal trigger's mode is chosen as it is put on the stack, before
            # its targets, and only the chosen mode's targets are chosen.
            node = self._declare_mode(node, ctx)
            if node is None:
                return None  # CR 700.2a: no mode can be chosen; the ability is removed
        # CR 603.1: designate targets BEFORE applying — the frozen IR
        # puts the ability's TARGET coordinates on the TRIGGERED-ABILITY node
        # itself, and CR 603.1 chooses targets as the ability goes on the
        # stack, which for a firing means before its first verb runs. A
        # DAMAGE firing already bound its anaphoric antecedent in _ctx
        # (the dealer); a DIES firing (Massacre Wurm's "that player")
        # binds here; anything else the effect reads as target/TARGET_PLAYER
        # gets a real designation ask through :meth:`_designate`.
        # The DAMAGE pre-bind serves only a designated player read with no
        # printed TARGET slot (the TARGET_PLAYER anaphora, divergence D18).
        if (
            event.kind == KIND_DAMAGE
            and event.cause is not None
            and ctx.bindings.get("target") == event.cause
            and (not self._designates(node) or self._designation_slots(node)[0])
        ):
            # An effect that designates nothing has no use for the dealer pre-bind, and a
            # binding-first role would read it: "creatures you control get +1/+0" (Wildfire
            # Elemental) would pump only the creature that dealt the damage.
            # A printed TARGET slot is chosen by the ability's controller as it goes on the stack
            # (CR 603.3d, 115.1): :meth:`_designate` asks, or fills the one legal choice. The dealer
            # never stands for it, even where it is a legal choice: resolve_selector takes a bound
            # handle as the designation, so Brash Taunter's "target opponent" was the dealer's
            # controller, unasked, with two opponents to choose from, and "whenever this deals
            # combat damage to a player, return target creature to its owner's hand" would bounce
            # its own dealer.
            del ctx.bindings["target"]
        if ctx.bindings.get("target") is None:
            if (
                event.kind == KIND_CREATURE_DIES
                and event.subject is not None
                and not self._trigger_designates_target(node)
                and self._designated_player_refs(node.effect)
            ):
                # The DAMAGE pre-bind's twin: in a DIES firing the antecedent
                # the frozen IR compiles to TARGET_PLAYER IS the dead creature —
                # players_for_ref folds a card designation to its controller, so
                # "that player loses 2 life" means the creature's controller
                # (the event's OWN filter scoped it to an opponent's creature
                # when the card text says so). The event object is the
                # honest antecedent, exactly as the DAMAGE dealer pre-bind.
                # The anaphora pre-bind is only the dead creature when the
                # effect reads the anaphora. A printed "…to ANY target"
                # (Pitchburn Devils) carries a real TARGET Selector slot —
                # CR 603.1 designates it through _designate, and the pre-bind
                # must never swallow the ask. An effect that reads no
                # designated player gets no pre-bind at all: a role reads its
                # binding before its own selector, so "each creature your
                # opponents control" (Cavalier of Flame) would hit the dead
                # creature instead.
                ctx.bindings["target"] = event.subject
            elif not self._designate(node, ctx):
                # CR 603.3d: a required target with no legal choice
                # removes the ability from the stack. None of its effect
                # happens, its untargeted steps included.
                return None
            else:
                designated = True
        target = ctx.bindings.get("target")
        targets = (target,) if isinstance(target, Handle) else tuple(target or ())
        per_slot = dict(ctx.slot_designations or {})  # several slots (_designate_slots)
        selectors = self._designation_slots(node)[0] if designated and not per_slot else []
        return StackObject(
            handle=self.executor.ability_handles.allocate(),
            node=node,
            controller=payload.controller,
            spell_kind="TRIGGERED",
            declared_targets=tuple(sorted(t for t in targets if isinstance(t, Handle))),
            declared_clock=self.executor.journal.clock,
            slot_designations=per_slot,
            source=payload.source,
            event=event,
            ctx=ctx,
            target_node=selectors[0] if selectors else None,
        )

    def resolve(self, obj) -> str:
        """CR 608.2: a triggered ability on the stack resolves (``stack.resolve_top``).
        Its intervening "if" is checked again (CR 603.4): false, it is removed and does
        nothing ("removed"). Its targets are checked again (CR 608.2b): none legal,
        it does not resolve ("no_targets"). Otherwise its effect runs through the shared effect runner,
        the SAME dispatch execute() uses, journalled at its Atom boundaries and guarded
        like the spell lanes: a template mis-fold whose anaphora has no producer skips
        LOUD (unresolved_effects) instead of killing the match; every other error still
        propagates. May-offers ask the executor's decision stream."""
        if not self._condition_holds(obj.node, obj.event, obj.source, obj.ctx):
            return "removed"
        gathered = obj.ctx.binding_handles("gathered")
        if gathered is not None:
            # CR 400.7: "they" are the objects the event gathered; one that has changed zones
            # since is a new object, which the effect does not touch. "That many" still counts
            # it (the ``gathered`` register). A reflexive trigger's ctx.event is its creator's.
            from MTG_bot.core.executor.returns import moved_since

            event = obj.ctx.event
            assert isinstance(event, GameEvent)
            since = max(e.clock for e in self._occurrences(event))
            obj.ctx.bindings["event"] = [
                h for h in gathered if not moved_since(self.executor.journal, h, since)
            ]
        kept: list[Handle] | None = None
        if obj.slot_designations and obj.declared_targets:
            # CR 608.2b, slot by slot, as a spell's targets are (stack.recheck_targets): an
            # illegal target leaves its own slot, and the ability does not resolve only when
            # every target is illegal.
            from MTG_bot.core.executor.query import activation_target_slots
            from MTG_bot.core.executor.stack import recheck_targets

            bindings = {k: v for k, v in obj.ctx.bindings.items() if k != "target"}
            slots = activation_target_slots(
                self.executor, obj.node.effect, source=obj.source, seat=obj.controller,
                bindings=bindings,
            )
            legal_now, per_slot = recheck_targets(
                self.executor, slots, obj.declared_targets, designations=obj.slot_designations,
                since=obj.declared_clock,
            )
            kept = list(legal_now)
            if per_slot is not None:
                obj.ctx.slot_designations = per_slot
                obj.ctx.designation_union = legal_now
        elif obj.target_node is not None and obj.declared_targets:
            # CR 608.2b: the targets chosen from a TARGET slot are checked again
            # against that slot now; with none still legal the ability does not
            # resolve, otherwise it acts on those still legal.
            from MTG_bot.core.executor.query import _widen_any_target, legal_targets

            bindings = {k: v for k, v in obj.ctx.bindings.items() if k != "target"}
            slot = legal_targets(
                self.world,
                self.executor,
                obj.target_node,
                source=obj.source,
                controller=obj.controller,
                bindings=bindings,
            )
            slot = (
                _widen_any_target(self.executor, obj.target_node, slot, obj.source, obj.controller)
                or slot
            )
            from MTG_bot.core.executor.returns import moved_since

            kept = [
                h for h in obj.declared_targets
                if h in slot.candidates
                and not (h.namespace == "card"
                         and moved_since(self.executor.journal, h, obj.declared_clock))
            ]  # CR 400.7: a target that changed zones since is a new object
        elif any(h.namespace == "player" for h in obj.declared_targets):
            # CR 608.2b: a designated player (_designate's player slot; a pre-bound
            # antecedent is a card) is checked again by the rule it was chosen by: one who
            # has since gained protection from the source is no longer a legal target.
            legal = self._target_players(obj.node, obj.ctx)
            kept = [h for h in obj.declared_targets if h in legal]
        if kept is not None:
            if not kept:
                self.executor.events.append(
                    (len(self.executor.events), "NO_LEGAL_TARGETS", str(obj.source), "trigger")
                )
                return "no_targets"
            obj.ctx.bindings["target"] = kept if len(kept) != 1 else kept[0]
        self.executor._run_guarded_effect(obj.node.effect, obj.ctx, "trigger")
        return "resolved"

    @classmethod
    def _modes_need_targets(cls, choose: Choose) -> bool:
        """Does any mode of a modal trigger designate (a TARGET selector or a designated
        player)? A modal trigger without one keeps its mode ask at resolution, where the
        runtime Choose makes it."""
        if cls._designated_player_refs(choose):
            return True
        return any(
            isinstance(value, Selector)
            and value.mode is SelectorMode.TARGET
            and value.referent is None
            for inner in own_nodes(choose)
            if isinstance(inner, Atom)
            for _role, value in inner.args.pairs
        )

    def _declare_mode(self, node: _AnyTrigger, ctx: ExecCtx) -> _AnyTrigger | None:
        """CR 603.3c, 700.2a: choose a modal trigger's mode as it goes on the stack. The
        menu is the option sets of :func:`query.choose_options` (its order index is the
        token, as the runtime Choose reads it) whose required targets can be chosen now;
        an exactly-n target needs n legal choices, an "up to" one none. Returns the trigger
        narrowed to the chosen options, in printed order, or None when no set is legal."""
        from MTG_bot.core.executor.offers import offer_or_autopick
        from MTG_bot.core.executor.query import (
            _widen_any_target,
            choose_options,
            legal_targets,
        )

        choose = node.effect
        assert isinstance(choose, Choose)
        options = choose_options(
            self.executor,
            choose,
            source=ctx.source,
            controller=ctx.controller,
            bindings=ctx.bindings,
        )

        def fillable(effect: object) -> bool:
            for inner in own_nodes(effect):
                if not isinstance(inner, Atom):
                    continue
                for _role, value in inner.args.pairs:
                    if not (
                        isinstance(value, Selector)
                        and value.mode is SelectorMode.TARGET
                        and value.referent is None
                    ):
                        continue
                    need = value.count.value if isinstance(value.count, QConst) else 0
                    slot = legal_targets(
                        self.world,
                        self.executor,
                        value,
                        source=ctx.source,
                        controller=ctx.controller,
                        bindings=ctx.bindings,
                    )
                    slot = (
                        _widen_any_target(self.executor, value, slot, ctx.source, ctx.controller)
                        or slot
                    )
                    if len(slot.candidates) < need:
                        return False
            return True

        legal = []
        for i, option in enumerate(options):
            picked = tuple(choose.options[j] for j in option.option_idxs)
            effect = picked[0] if len(picked) == 1 else (Seq(steps=picked) if picked else None)
            if effect is None or fillable(effect):
                legal.append((str(i), option.option_idxs, effect))
        if not legal:
            return None
        vocab = tuple(token for token, _idxs, _effect in legal)
        digest = site_digest(tuple(idxs for _token, idxs, _effect in legal))
        pick = offer_or_autopick(ctx, vocab, f"choose:{ctx.source}:{digest}")
        effect = next(effect for token, _idxs, effect in legal if token == pick)
        if effect is None:
            return None  # the empty set of an "up to" choice: nothing happens
        return replace(node, effect=effect)

    @staticmethod
    def _designated_player_refs(effect: object) -> set[ControllerRef]:
        """The designated-player refs (TARGET_PLAYER / TARGET_OPPONENT) a trigger's effect
        reads: a role value naming one, a zone it controls, or a filter reading the bound
        player (the scan :meth:`_designate` makes). Only its own nodes: a delayed, reflexive
        or granted ability designates for itself."""
        refs: set[ControllerRef] = set()
        for inner in own_nodes(effect):
            if not isinstance(inner, Atom):
                continue
            for _role, value in inner.args.pairs:
                if isinstance(value, ControllerRef) and value in DESIGNATED_PLAYER_REFS:
                    refs.add(value)
                elif isinstance(value, Zone) and value.controller in DESIGNATED_PLAYER_REFS:
                    refs.add(value.controller)
                elif isinstance(value, Selector):
                    refs |= filter_bound_player_refs(value.filter)
                else:
                    refs |= filter_bound_player_refs(value)
        return refs

    @classmethod
    def _trigger_designates_target(cls, node: _AnyTrigger) -> bool:
        """Does this trigger's effect carry a real TARGET designation
        slot — a TARGET-mode Selector with no referent (the collector of
        :meth:`_designation_slots`; walk enters Optional-/SeqEffect wrappers,
        so Goblin Arsonist's may-wrapped damage is seen)? A node that only
        reads the TARGET_PLAYER anaphora (Massacre Wurm's "that player")
        answers False and keeps the dies pre-bind in :meth:`_put`;
        a printed "…to ANY target" (Pitchburn Devils) answers True and
        routes to the designation ask."""
        selectors, _reads_player, _opponent_only = cls._designation_slots(node)
        return bool(selectors)

    @classmethod
    def _designation_slots(cls, node: _AnyTrigger) -> tuple[list[Selector], bool, bool]:
        """The designations a trigger's effect makes: its distinct TARGET-mode,
        referent-free Selectors; whether it reads a designated player
        (:meth:`_designated_player_refs`); and whether that read is "target
        opponent" only. Only its own nodes (``own_nodes``): a delayed or reflexive
        trigger it creates chooses its targets when it goes on the stack itself (CR
        603.7c, 603.12), and a granted ability when it is activated or triggers."""
        refs = cls._designated_player_refs(node.effect)
        selectors: list[Selector] = []
        seen: set[str] = set()
        for inner in own_nodes(node.effect):
            if not isinstance(inner, Atom):
                continue
            for _role, value in inner.args.pairs:
                if (
                    isinstance(value, Selector)
                    and value.mode is SelectorMode.TARGET
                    and value.referent is None
                ):
                    key = repr(value)
                    if key not in seen:
                        seen.add(key)
                        selectors.append(value)
        return selectors, bool(refs), ControllerRef.TARGET_OPPONENT in refs

    @classmethod
    def _designates(cls, node: _AnyTrigger) -> bool:
        """Does the trigger's effect make any designation (a TARGET slot or a designated-player
        read)?"""
        selectors, reads_target_player, _ = cls._designation_slots(node)
        return bool(selectors) or reads_target_player

    def _target_players(self, node: _AnyTrigger, ctx: ExecCtx) -> list[Handle]:
        """The players a trigger's "target opponent" / "target player" may designate now: the
        ability controller's opponents, or every player (CR 115.1, 102.2), minus those with
        protection from its source (CR 702.16b: Runed Halo naming the trigger's card) or
        hexproof against its controller (CR 702.11c). Chosen from as it goes on the stack
        (:meth:`_designate`) and checked against again as it resolves (:meth:`resolve`, CR
        608.2b)."""
        from MTG_bot.core.executor.legality import player_targetable

        opponent_only = self._designation_slots(node)[2]
        players = (
            players_for_ref(ControllerRef.OPPONENT, ctx)
            if opponent_only
            else list(ctx.world.player_order)
        )
        return [h for h in players if player_targetable(self.executor, h, ctx.source, ctx.controller)]

    def _designate(self, node: _AnyTrigger, ctx: ExecCtx) -> bool:
        """The trigger designation channel (CR 603.1).
        Returns False when the ability is removed from the stack (CR
        603.3d), True when it goes on and resolves.

        The engine enumerates the candidates through its OWN query surface
        (``query.legal_targets`` — query/runtime identity, no mirrored
        population) and asks the vocabulary-addressed decision channel for
        the choice (the Handle-sorted candidate list IS the vocabulary,
        ``take_decision`` re-validates membership). The answer lands in
        ``ctx.bindings["target"]`` BEFORE the effect runs, the exact mirror
        of ``stack.cast``'s designate-then-apply.

        Routing table (per-card, event-kind driven — see _put):
        * DAMAGE firing whose effect reads a designated player and prints no
          TARGET slot → the dealer (in _ctx);
        * CREATURE_DIES firing → the dead creature (in _put);
        * a single distinct TARGET-mode Selector → enumerated ask (below);
        * a designated-player read with no Selector ("target opponent",
          "target player") → the ABILITY CONTROLLER's opponents, or every
          player, minus those with protection from the source; one
          candidate is auto-filled (no ask), none removes the ability (the
          word "target" makes it a required target, CR 603.3d);
        * a multi-slot trigger (two distinct TARGETs, or a TARGET and a
          TARGET_PLAYER) → designated slot by slot (:meth:`_designate_slots`).

        The site tag carries the CONTROLLER seat (``target:<seat>:<source>:
        <digest>``, four segments like the combat lane): the answer belongs
        to the seat the rules gave the decision to, and a mirror pair of
        the same card asks two DIFFERENT keys (attribution, not collision).

        Zero-candidate honesty: nothing enumerable means no decision exists;
        never a crash, never a guess. A REQUIRED slot (an exact count the
        ability needs whatever mode it takes, see
        :func:`_required_target_keys`) that cannot be filled removes the
        ability from the stack (CR 603.3d): False, and none of the effect
        runs. An "up to N" or mode-dependent slot binds the EMPTY set and
        the ability resolves without it, since zero targets (or another
        mode) is a legal choice.

        Cardinality follows the frozen slot contract (``count_semantics``):
        ``QConst(1)`` designates exactly one (forced when one candidate);
        ``QAtMost(n)`` asks pick-by-pick, every pick carrying the ``"NONE"``
        stop token (CR 601.2c/115.6: the range is 0..n; zero picks = not
        targeted, and one candidate is still a choice of it or none);
        ``QConst(n>1)`` asks n picks without the stop token, and fewer than
        n candidates cannot fill it; ``QAtLeast``/QX in a trigger TARGET
        raises.
        """
        selectors, reads_target_player, _ = self._designation_slots(node)
        if not selectors and not reads_target_player:
            return True  # no designation to make
        if len(selectors) > 1 or (selectors and reads_target_player):
            return self._designate_slots(node, ctx)
        if reads_target_player:
            # The synthetic player slot (spell_target_slots' twin), populated by
            # _target_players; the cross-seat ruling is CR 603.1's: the
            # ABILITY's controller designates, so an opponent's trigger asks the
            # OPPONENT's seat (ctx.controller IS that seat, the firing context
            # was built from payload.controller).
            players = self._target_players(node, ctx)
            if not players:
                # CR 603.3d: "target opponent" / "target player" is a required target (every
                # trigger reaching here prints the word), so with no legal player the ability
                # is removed from the stack: Vito, Thorn of the Dusk Rose's "target opponent
                # loses that much life" with that opponent's Runed Halo naming Vito.
                return False
            if len(players) == 1:
                ctx.bindings["target"] = players[0]
            else:
                vocab = tuple(str(h) for h in sorted(players))
                answer = ctx.take_decision(
                    vocab,
                    f"target:{ctx.controller}:{ctx.source}:{site_digest(vocab)}",
                )
                ctx.bindings["target"] = next(
                    h for h in sorted(players) if str(h) == answer
                )
            # TARGETING feed — a genuine designation made here is an
            # event (pre-bound firings never reach this method).
            self.executor.journal.emit_targeting(
                ctx.source, ctx.controller, [ctx.bindings["target"]]
            )
            return True
        selector = selectors[0]
        from MTG_bot.core.executor.query import (  # cycle-free at call time
            _widen_any_target,  # the query lane's ONE widening opinion
            legal_targets,
        )

        slot = legal_targets(
            self.world,
            self.executor,
            selector,
            source=ctx.source,
            controller=ctx.controller,
            # Feline Sovereign: the firing ctx's bindings ride into
            # the candidate enumeration. The trigger already bound the
            # 'event' register (_ctx stamps event.subject before
            # designation), and the destroyed object's filter reads it —
            # "destroy target artifact or enchantment THAT CREATURE'S
            # CONTROLLER controls" compiles CONTROLLER_IS who=
            # Selector(referent='event'); without the firing bindings that
            # selector would ask a register it never saw.
            bindings=ctx.bindings,
        )
        slot = (
            _widen_any_target(self.executor, selector, slot, ctx.source, ctx.controller) or slot
        )
        candidates = sorted(slot.candidates)
        count = selector.count
        # CR 603.3d: an exact-count slot the ability needs in every
        # mode, with too few legal choices, removes it from the stack.
        required = isinstance(count, QConst) and repr(selector) in (
            _required_target_keys(node.effect)
        )
        if not candidates:
            if required:
                return False
            ctx.bindings["target"] = []  # "up to N" / mode-dependent slot:
            # zero targets is a legal choice, the ability resolves without
            return True
        if not isinstance(count, (QConst, QAtMost)):
            raise NotImplementedError(
                f"executor: trigger TARGET count {count!r} designates "
                "through the 12c prompt (QX/QAtLeast in a trigger TARGET "
                "is not a frozen-IR shape)"
            )
        # CR 601.2c: ONE answer for the count axis (count_semantics) —
        # QConst is EXACT, never clamped. A trigger that cannot complete its
        # full-size designation is removed from the stack when the slot is
        # required (CR 603.3d), otherwise designates NOTHING and resolves.
        # CR 601.2c, 115.6: "up to N" may designate zero, so the stop
        # word is offered from the first pick on.
        optional_stop = isinstance(count, QAtMost)
        announceable, wanted = count_semantics(count, len(candidates))
        if not announceable:
            if required:
                return False
            ctx.bindings["target"] = []
            return True
        picks: list[Handle] = []
        pool = list(candidates)
        for _ in range(wanted):
            if len(pool) == 1 and not optional_stop:
                picks.append(pool[0])  # auto-fill: one legal filler, no ask
                break
            vocab = tuple(str(h) for h in pool)
            if optional_stop:
                vocab = vocab + ("NONE",)
            answer = ctx.take_decision(
                vocab,
                f"target:{ctx.controller}:{ctx.source}:{site_digest(vocab)}",
            )
            if answer == "NONE":
                break
            pick = next(h for h in pool if str(h) == answer)
            picks.append(pick)
            pool.remove(pick)
        ctx.bindings["target"] = picks if len(picks) != 1 else picks[0]
        # TARGETING feed — see the player-slot note above; an empty
        # pick list (an "up to N" answered NONE) emits none.
        self.executor.journal.emit_targeting(ctx.source, ctx.controller, picks)
        return True

    def _designate_slots(self, node: _AnyTrigger, ctx: ExecCtx) -> bool:
        """CR 603.3d, 601.2c: a trigger with several designations ("deals 4 damage to any target
        and 3 damage to each of up to two other targets", Drakuseth, Maw of Flames) designates
        them as a spell or an activation does: the slots of ``query.activation_target_slots``
        (the player slot of "target player" included), the targets of each in turn, one ask per
        pick over the candidates ``stack.slot_options`` leaves: never one picked twice for one
        word "target" (CR 115.3), never one an "another"/"other" slot shares with another slot,
        and never one that leaves a later slot without its minimum. A slot with one legal filler
        and its minimum not reached takes it unasked; once it has its minimum, NONE ends it. With
        a required slot impossible to fill the ability is removed (False). The per-slot map rides
        the context (``ExecCtx.slot_designations``), which each TARGET selector then reads at
        resolution, and the union is ``target``. The ask site is the single slot's."""
        from MTG_bot.core.executor.query import activation_target_slots, designates
        from MTG_bot.core.executor.stack import can_designate, slot_options

        if any(isinstance(inner, Choose) and designates(inner) for inner in own_nodes(node.effect)):
            # CR 700.2a, 603.3c: a mode's targets are chosen for the chosen mode only.
            # _declare_mode narrows a top-level Choose before this; one inside the effect is
            # still whole, so every mode's slots would be asked and an unfillable one would
            # remove the ability while another mode stays choosable (the single-slot lane
            # treats such a slot as optional: _required_target_keys).
            raise NotImplementedError(
                f"executor: trigger {node.effect!r:.80}: a target under a mode not chosen yet "
                "(a Choose inside the effect) is not designated slot by slot"
            )
        slots = activation_target_slots(
            self.executor, node.effect, source=ctx.source, seat=ctx.controller,
            bindings=ctx.bindings,
        )
        if any(filter_bound_player_refs(slot.selector.filter) for slot in slots if not slot.synthetic):
            # "Exile target creature target opponent controls": that creature's legal set is
            # known only once the player is chosen; the slots are made independently, so its
            # population would be empty and the ability wrongly removed.
            raise NotImplementedError(
                f"executor: trigger {node.effect!r:.80}: a target's legal set reads the "
                "designated player beside it, which per-slot designation does not choose first"
            )
        if not can_designate(slots):
            return False
        groups: list[tuple[Handle, ...]] = []
        for slot in slots:
            picked: list[Handle] = []
            while len(picked) < slot.max_count:
                options = slot_options(slots, tuple(groups), picked)
                if not options:
                    break
                done = len(picked) >= slot.min_count
                if len(options) == 1 and not done:
                    picked.append(options[0])
                    continue
                vocab = tuple(str(h) for h in options) + (("NONE",) if done else ())
                answer = ctx.take_decision(
                    vocab, f"target:{ctx.controller}:{ctx.source}:{site_digest(vocab)}"
                )
                if answer == "NONE":
                    break
                picked.append(next(h for h in options if str(h) == answer))
            groups.append(tuple(sorted(picked)))
        union = tuple(sorted({h for group in groups for h in group}))
        ctx.slot_designations = {
            repr(slot.selector): group for slot, group in zip(slots, groups, strict=True)
        }
        ctx.designation_union = union
        ctx.bindings["target"] = list(union)
        self.executor.journal.emit_targeting(ctx.source, ctx.controller, list(union))
        return True

    def _ctx(
        self,
        source: Handle,
        controller: Handle,
        event: GameEvent,
    ) -> ExecCtx:
        ex = self.executor
        bindings: dict[str, Handle] = {}
        if event.subject is not None:
            bindings["event"] = event.subject
            if event.kind == KIND_CREATURE_DIES:
                bindings["result"] = event.subject  # the was-snapshot subject
        if event.kind == KIND_DAMAGE and event.cause is not None:
            # The dealer: a TARGET_PLAYER read with no printed target is the
            # anaphora "the controller of the source of that damage" (D18).
            # _put lifts the pre-bind for every other effect, a printed
            # TARGET slot included (CR 603.3d: its controller chooses).
            bindings["target"] = event.cause
        amount = (
            event.amount
            if event.kind in (KIND_DAMAGE, KIND_LIFE_GAINED, KIND_LIFE_LOST)
            else None
        )
        # Light of Promise: a LIFE_GAINED row's data[0] IS the amount
        # gained, so QProp(referent='event', field=AMOUNT) resolves inside a
        # life-gained firing exactly as it does inside a damage firing; a
        # LIFE_LOST row's is the amount lost.
        # Wildwood Scourge (CR 614.1c): a spell cast with a declared X
        # carries that X into every firing this ENTRY generates — stack.cast
        # recorded it as the spell landed. The read is NON-destructive on
        # purpose: _match_zone_change builds this same ctx for the matcher
        # (a pop there would rob the firing), and every ETB ability of the
        # entering permanent may legitimately mention X. The entry is
        # cleared when the permanent leaves the battlefield, so a later
        # re-entry carries no cast X. CR 107.3b: an object that was not cast
        # (reanimated, put onto the battlefield — Rise Again returning
        # Wildwood Scourge) has X = 0, so its own ETB firing resolves X as 0.
        # Every other undeclared X stays the loud flag.
        x_value: int | None = None
        if (
            event.kind == KIND_ZONE_CHANGE
            and event.subject is not None
            and event.subject == source
            and event.data[1] == ZONE_BATTLEFIELD
        ):
            x_value = ex.etb_x.get(source, 0)
        return ExecCtx(
            world=ex.world,
            ledger=ex.ledger,
            controller=controller,
            source=source,
            bindings=bindings,
            x_value=x_value,  # CR 614.1c cast-declared X at ETB
            decisions=(),  # firings answer through ex.decisions
            stream=ex.decisions,
            events=ex.events,
            rng=ex.rng,
            token_counts=ex.token_counts,
            event=event,
            event_amount=amount,
            # trigger-fired GRANT/LOSE/PREVENT atoms and damage
            # replacements reach the registries through the ctx.
            layers=ex.layers,
            replacements=ex.replacements,
            executor=ex,
            # the firing ctx reads the SAME journal the matcher
            # is draining (history preds at a trigger's condition gate).
            journal=ex.journal,
        )

    # ------------------------------------------------------------ delayed

    def fire_reflexive(self, node: DelayedTrigger, ctx: ExecCtx) -> None:
        """CR 603.12: a reflexive triggered ability ("When you do, ...") triggers as the
        resolution that creates it reaches it: the Conditional around it found the action it
        triggers on done earlier in that resolution. Like any triggered ability it then waits,
        and goes on the stack the next time a player would receive priority (CR 603.3), its
        targets chosen then (603.3d: with no legal one it is removed). Its source and controller
        are the resolving spell's or ability's (CR 603.7d-e). It reads that resolution's bindings,
        X and event register, but not its designation: it chooses its own targets, and cannot
        read the creating ability's (IKO Back for More, BACKLOG). A bound object that has left is
        read where it is now: "the sacrificed creature's power" would read the card in the
        graveyard, not its last known information (CR 608.2h; BACKLOG, no such card compiles).
        Its event names no object (``REFLEXIVE``); the journal never holds one."""
        carried = _Carried(
            {k: list(v) if isinstance(v, list) else v for k, v in ctx.bindings.items() if k != "target"},
            ctx.x_value,
            ctx.event,
            ctx.event_amount,
        )
        event = GameEvent(
            clock=self.executor.journal.clock,
            kind=KIND_REFLEXIVE,
            subject=None,
            cause=ctx.source,
            cause_verb="REFLEXIVE",
        )
        self._queue(ctx.source, ctx.controller, node, event, delayed=True, carried=carried)

    def schedule_delayed(
        self, node: DelayedTrigger, source: Handle, controller: Handle
    ) -> None:
        """Register a DelayedTrigger effect node into the journal matcher.
        Only the turn-window tags (``_SWEEP_TAGS``) sweep; a permanent-window
        or any longer duration RAISES (the Duration vocab governs ledger,
        layer and prevention records, not delayed-trigger windows) — never
        a leak. The scheduled EVENT kind gets the
        same unsupported-kind flag-don't-degrade check as an attached
        trigger."""
        self._check_trigger(node, "DelayedTrigger")
        tag = duration_tag(node.duration)
        if tag not in _SWEEP_TAGS:
            raise NotImplementedError(
                f"executor: DelayedTrigger duration tag {tag!r} exceeds the "
                "turn window (12e)"
            )
        self._seq += 1
        self.delayed.append(
            DelayedBinding(
                seq=self._seq, tag=tag, node=node, source=source, controller=controller
            )
        )

    def expire_delayed(self) -> int:
        """End-of-turn sweep: drop the turn-window delayed triggers."""
        keep = [entry for entry in self.delayed if entry.tag not in _SWEEP_TAGS]
        expired = len(self.delayed) - len(keep)
        self.delayed = keep
        return expired

    # ---------------------------------------------------------- canonical

    def dump(self) -> tuple[tuple[object, ...], ...]:
        """Deterministic registry/delayed view for the replay fingerprint."""
        attached = tuple(
            (str(handle), idx, repr(ability.event))
            for (handle, idx), ability in sorted(
                self.attached.items(), key=lambda kv: (str(kv[0][0]), kv[0][1])
            )
        )
        delayed = tuple(
            (d.seq, d.tag, str(d.source), str(d.controller), repr(d.node.event))
            for d in sorted(self.delayed, key=lambda d: d.seq)
        )
        emblems = tuple(
            sorted(
                (str(handle), str(owner)) for handle, owner in self.emblem_owner.items()
            )
        )
        quarantined = tuple(sorted(map(str, self.quarantined)))
        dump: tuple[tuple[object, ...], ...] = (
            ("attached", attached),
            ("delayed", delayed),
            ("emblems", emblems),
            ("quarantined", quarantined),
        )
        if self.attached_graveyard:
            # present only when a graveyard trigger is bound, so a game
            # without one keeps its fingerprint bytes.
            dump += (
                (
                    "graveyard",
                    tuple(
                        (str(handle), idx, repr(ability.event))
                        for (handle, idx), ability in sorted(
                            self.attached_graveyard.items(),
                            key=lambda kv: (str(kv[0][0]), kv[0][1]),
                        )
                    ),
                ),
            )
        return dump
