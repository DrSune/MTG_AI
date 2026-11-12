"""Continuous layers: static abilities, keyword/ability grants and losses.

The trigger binder (binding.py) holds TriggeredAbility nodes; this registry
holds the CONTINUOUS ones. When a permanent's compiled record attaches (enters the
battlefield), its :class:`KeywordAbility` nodes (printed keywords, typed
params) and :class:`StaticAbility` nodes (anthems, "as long as …", granted
statics) register here as :class:`LayerRecord`\\ s; the registry recomputes
after every public executor op (set changes + duration events flow through
the executor's settle pass → :meth:`LayerRegistry.recompute`):

  * **PT payloads materialize into the DurationLedger** — a static's
    MODIFY_PT is recorded per (layer, target) as an ordinary ledger entry
    carrying the layer's Duration meta, so the single PT stack documented on
    :mod:`~MTG_bot.core.executor.durations` folds verb and layer modifiers
    under one rule: printed base, then timestamp-then-order. Lethal damage,
    QProp POWER/TOUGHNESS and the dies snapshot read the ledger, so they see
    layer modifiers too.
  * **keyword / ability grants feed derived maps** rebuilt in recompute —
    printed identity keywords first, then live layers in LAYER-SEQ (first
    application-timestamp) order, so a later loss removes an earlier grant
    and a later grant re-applies over an earlier loss:
    :meth:`LayerRegistry.keyword_of` (a keyword removal matches printed AND
    granted keywords by name) and
    :meth:`LayerRegistry.granted_abilities` (what :mod:`legality` folds into
    ``legal_activations`` as negative-index rows).
  * **the controller rule for granted abilities:** the granted
    ability's SOURCE is the granted permanent and its ``you`` is the
    GRANTEE — the permanent's controller at activation time (legality runs
    the activation with ``source=granted handle``, ``controller=seat``);
    the granting permanent's controller only decides who WROTE the grant,
    never who may use it. Pinned by
    ``test_granted_activated_legality_and_the_grantee_rule``.
  * **continuous = recompute, not execute-once** — a scope-resolved static
    (an anthem) re-reads its selector every recompute, so creatures that
    enter later are covered and leaving ones drop out (their materialized
    ledger entries terminal-expire). Fixed-target layers (runtime
    GRANT/LOSE_ABILITY verbs) act on their designated set.

Duration vocab is honoured through the same expiry points the ledger uses:
Eot sweep, WHILE condition cycles (journal-driven recompute), UNTIL_NEXT_
STEP ticks, UNTIL_LEAVES zone interception, UNTIL_NEXT_TURN begin-turn.
Non-PT payloads expire at LAYER granularity; materialized PT entries carry
per-entry Duration meta in the ledger and expire object-correctly there.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, NamedTuple, cast

from MTG_bot.core.ability_tree import (
    Ability,
    ActivatedAbility,
    ActivationWindow,
    Atom,
    Duration,
    DurationPermanent,
    DurationUntilEndOfNextTurn,
    DurationUntilLeaves,
    DurationUntilNextStep,
    DurationUntilNextTurn,
    DurationWhileCondition,
    EventSpec,
    FAnd,
    FAtom,
    FAtomPred,
    Filter,
    FNot,
    FOr,
    Keyword,
    KeywordAbility,
    OptionalEffect,
    QConst,
    Selector,
    Seq,
    StaticAbility,
    Step,
    Verb,
)
from MTG_bot.core.executor.durations import duration_tag
from MTG_bot.core.executor.quantity import ExecCtx, eval_filter
from MTG_bot.core.identity import Handle

if TYPE_CHECKING:  # pragma: no cover - typing-only, dodges the import cycle
    from MTG_bot.core.compiler.compiler import CardRecord
    from MTG_bot.core.executor import Executor


class GrantedAbility(NamedTuple):
    """One granted ability as :mod:`legality` consumes it: the typed IR
    node and the granting permanent (:meth:`LayerRegistry.granted_abilities`
    keeps them in layer-seq order, the canonical granted-ability index
    basis)."""

    node: Ability
    granter: Handle


_PT_VERBS = frozenset({Verb.MODIFY_PT, Verb.SET_PT})
# GRANT_TYPE is a static payload too (Dub, Demonic Embrace compile their
# type-grant as a StaticAbility). It is NOT a _PT_VERB (no ledger
# materialization) — it is carried by the generic "static" record and read
# through the derived type-overlay map (:meth:`LayerRegistry.type_overlay`).
_LAYER_PAYLOAD_VERBS = _PT_VERBS | {
    Verb.GRANT_ABILITY,
    Verb.LOSE_ABILITY,
    Verb.GRANT_TYPE,
}


def _is_universal(filter_: Filter) -> bool:
    """The grammar's universal filter (the binding.py twin — kept local to
    avoid importing the binder back into the layer registry)."""
    return isinstance(filter_, FAnd) and len(filter_.children) == 0


def _keyword_name(keyword) -> str:
    return keyword.name if isinstance(keyword, Keyword) else str(keyword)


def _lose_matches_keyword(payload: object, name: str) -> bool:
    """A LOSE keyword removes the keyword WORD, printed or granted (params
    are GRANT-side modifiers — "loses hexproof" drops "hexproof from blue"
    too, matching the CR's ability-word semantics)."""
    return isinstance(payload, KeywordAbility) and payload.keyword.name == name


def _lose_matches_ability(payload: object, node: object) -> bool:
    """Non-keyword removal matches by canonical node repr — the granted node
    equal to the one the LOSE names is what gets lost (a printed non-keyword
    ability is not in the granted map, so a LOSE leaves it alone)."""
    return repr(payload) == repr(node)


def _validate_activation_grant(atom: Atom) -> None:
    """The GRANT_ACTIVATION shape contract (role table: filter REQUIRED,
    window optional): the filter is the permanent-shape gate (Teferi,
    Master of Time's compiled ``FAnd(TYPE_EQ Planeswalker, NAME_CONTAINS
    "Teferi")``) and the window is the timing relaxation. The ONLY
    relaxation the grammar and the corpus support is INSTANT ("activate …
    any time you could cast an instant"); anything else is flagged, not
    guessed."""
    filter_ = atom.args.get("filter")
    if filter_ is None or not isinstance(filter_, (FAnd, FOr, FNot, FAtom)):
        raise ValueError(f"executor: GRANT_ACTIVATION needs a Filter, got {filter_!r}")
    window = atom.args.get("window")
    if window is not None and window is not ActivationWindow.INSTANT:
        raise NotImplementedError(
            f"executor: GRANT_ACTIVATION window {window!r} has no consumer "
            "(13c implements the INSTANT relaxation only)"
        )


def _static_while_duration(atoms: list[Atom] | tuple[Atom, ...]) -> Duration | None:
    """Fold the atoms' ``duration`` ROLE into the record's duration lane.
    Some while-statics place the "as long as" gate INSIDE the atom
    (``duration`` -> DurationWhileCondition) instead of on
    ``StaticAbility.condition``; dropped, it would leave the static
    EVER-LIVE. The record's Duration lane already honours a WHILE —
    :meth:`LayerRegistry._layer_live` re-judges ``layer.duration.filter``
    at every recompute and the ledger's ``settle_while`` drives the
    materialized entries — so the role rides that lane, no parallel gate.
    PERMANENT is the ABSENCE of a window (the Conspicuous Snoop shape),
    equivalent to no role.

    The gate's SUBJECT: a BARE FAtom is judged of the source ("as long as
    IT has a counter", Sigiled Contender's HAS_COUNTER); an FAnd COMPOUND
    (TYPE/SUBTYPE/CONTROLLER_IS conjuncts) reads as existence — some
    battlefield permanent under ctx.controller matches the conjunct — and
    is re-encoded as CONTROLLER_COUNT_GE 1 over it, the corpus's own
    existence mechanism. FOr/FNot composites have no precedent for the
    existence-vs-source reading, and two atoms of one record DISAGREEING
    about the gate have no honest reading either: both are flagged "not
    layer-parseable", never guessed (attach_source skips such a static and
    records the refusal, so the game goes on)."""
    found: DurationWhileCondition | None = None
    for atom in atoms:
        dur = atom.args.get("duration")
        if dur is None or isinstance(dur, DurationPermanent):
            continue
        if not isinstance(dur, DurationWhileCondition):
            raise NotImplementedError(
                "executor: StaticAbility duration "
                f"{type(dur).__name__} is not layer-parseable (ZND-4d)"
            )
        cond = dur.filter
        if isinstance(cond, (FNot, FOr)):
            raise NotImplementedError(
                "executor: StaticAbility FOr/FNot while-condition duration "
                "has no precedent reading, is not layer-parseable (ZND-4d)"
            )
        if isinstance(cond, FAnd) and not _is_universal(cond):
            # Existence reading of the candidate-shape conjunct through the
            # ONE executed counting atom (handle-free, per-candidate
            # inner_filter under the layer's controller — quantity.py).
            cond = FAtom(
                pred=FAtomPred.CONTROLLER_COUNT_GE,
                count=QConst(1),
                inner_filter=cond,
            )
            dur = DurationWhileCondition(filter=cond)
        if found is not None and dur != found:
            raise NotImplementedError(
                "executor: StaticAbility with two distinct while-condition "
                "durations is not layer-parseable (ZND-4d)"
            )
        found = dur
    return found


@dataclass
class LayerRecord:
    """One continuous effect's registry entry.

    ``kind`` — ``"keyword"`` (a card's own KeywordAbility node),
    ``"static"`` (a StaticAbility node, scope-resolved), ``"grant"`` /
    ``"lose"`` (runtime GRANT_ABILITY / LOSE_ABILITY verbs, fixed targets),
    ``"mana_policy"`` (spend permissions), ``"type_grant"``
    (runtime GRANT_TYPE), ``"activation_grant"`` (GRANT_ACTIVATION timing
    permissions) / ``"land_play"`` (ADD_LAND_PLAY allowances — the last two
    permission kinds are selector-less, like mana_policy),
    ``"mandate"`` / ``"mandate_block"`` (MANDATE_ATTACK / MANDATE_BLOCK
    rules — "attacks each combat if able"; the legality surface resolves
    the atom's ``cards`` selector at every declare-attackers /
    declare-blockers), ``"attack_policy"`` (ATTACK_POLICY, the same
    ``cards`` shape: "can attack as though it didn't have defender",
    read by the attack legality), and
    ``"disclosure"`` (REVEAL/LOOK_AT payload statics — the recorded zone-
    knowledge fact, selector-less and inert at re-apply by rules right).
    ``status`` — ``live`` | ``dormant`` (a condition currently false — the
    record survives, its effect does not apply) | ``expired`` (terminal; the
    record stays for the audit dump). ``ledger_ids`` maps each materialized
    PT target to its DurationLedger record id. ``resolved`` marks a record
    a RESOLVED spell or ability created (a dispatched "mandate"/
    "mandate_block"/"attack_policy" with fixed ``targets``; the runtime "grant",
    "lose" and "type_grant" records): CR 611.2a, it lasts as long as its
    duration says, so its source leaving the battlefield does not end it
    (:meth:`LayerRegistry.detach_source` skips it; an UntilLeaves duration
    still ends it, :meth:`LayerRegistry.expire_leaves`).
    """

    seq: int
    kind: str
    source: Handle
    controller: Handle
    payload: object
    tag: str
    targets: tuple[Handle, ...] = ()
    selector: Selector | None = None
    duration: Duration | None = None
    condition: Filter | None = None  # StaticAbility/While-condition
    status: str = "live"
    ledger_ids: dict[Handle, int] = field(default_factory=dict)
    resolved: bool = False
    # CR 702.26b: the record IS one of its source's own static
    # or keyword abilities (attach_source registered it), so it does not
    # function while the source is phased out. Effects a resolved spell or
    # ability created are not abilities of the source and keep applying.
    # Not in dump(): the flag is a function of the attach history.
    from_static: bool = False

    @property
    def atoms(self) -> tuple[Atom, ...]:
        """The payload tuple: the parsed Atoms of every atom-carrying kind
        (``land_play`` holds one QConst instead). ``keyword`` / ``grant`` /
        ``lose`` wrap a single Ability node, so atoms is then empty."""
        return self.payload if isinstance(self.payload, tuple) else ()


class LayerRegistry:
    """The continuous-layers registry owned by one
    :class:`~MTG_bot.core.executor.Executor`."""

    def __init__(self, executor: Executor) -> None:
        self.executor = executor
        self.records: list[LayerRecord] = []
        self._seq = 0
        # Derived maps — rebuilt (never incrementally patched) on every
        # recompute, so the fingerprint and every predicate read one
        # deterministic snapshot.
        self._keywords: dict[Handle, tuple[str, ...]] = {}
        self._granted: dict[Handle, tuple[GrantedAbility, ...]] = {}
        # The type-grant overlay (GRANT_TYPE "is a Knight in addition
        # to its other types") — rebuilt alongside the keyword/granted maps,
        # read by the TYPE_EQ/SUBTYPE_EQ/SUPERTYPE_EQ filter evaluator.
        self._types: dict[Handle, tuple[str, ...]] = {}
        # The ``resolved`` records (a subset of ``records``), so the
        # per-departure :meth:`forget_departed` scan stays O(resolved).
        self._resolved: list[LayerRecord] = []

    # ------------------------------------------------------------ lifecycle

    @property
    def world(self):
        return self.executor.world

    def attach_source(
        self, handle: Handle, record: CardRecord, controller: Handle | None = None
    ) -> int:
        """Battlefield attach: register the card's own KeywordAbility nodes
        and StaticAbility nodes as layers (idempotent — this detaches the
        handle's old layers first, and the binder detaches on re-entry).

        ``controller`` lets an OFF-world record (an emblem's synthetic
        handle, which is not in ``world.cards``) bind its statics to a
        chosen anchor (the emblem's OWNER) instead of the battlefield
        ``controller_of`` lookup — the synthetic handle has no world card to
        resolve. ``None`` = the ordinary battlefield resolution."""
        self.detach_source(handle)
        count = 0
        first_new = len(self.records)
        if controller is None:
            controller = self.executor.controller_of(handle)  # GAIN_CONTROL overlay
        for kw in record.keywords:
            self._new("keyword", handle, controller, kw, (handle,))
            count += 1
        for node in record.abilities:
            if isinstance(node, KeywordAbility):
                self._new("keyword", handle, controller, node, (handle,))
                count += 1
            elif isinstance(node, StaticAbility):
                try:
                    count += len(self._new_static(handle, node, controller=controller))
                except NotImplementedError as e:
                    # A static whose payload is not layer-parseable (Rin
                    # and Seri, Inseparable's mis-compiled GAIN_LIFE static)
                    # must NOT kill the game. _new_static keeps raising by
                    # design (the unit contract: a layer question never
                    # gets a silent guess), but a permanent entering with a
                    # compiler-mis-shaped static half should lose THAT
                    # half, not the match. This is a LOUD refusal: the
                    # skipped static is recorded on the executor
                    # (unparseable_statics, coverage-visible). Only the
                    # parseability flag is caught — any other
                    # NotImplementedError still propagates.
                    if "not layer-parseable" not in str(e):
                        raise
                    flag = f"{handle}: {e}"
                    if flag not in self.executor.unparseable_statics:
                        self.executor.unparseable_statics.append(flag)
        for layer in self.records[first_new:]:
            layer.from_static = True  # CR 702.26b: see LayerRecord.from_static
        return count

    def detach_source(self, handle: Handle) -> int:
        """Battlefield departure: expire every layer whose SOURCE is this
        permanent (and terminal-expire its materialized ledger entries).
        A ``resolved`` record is not the permanent's own ability: its
        duration alone ends it (CR 611.2a)."""
        dropped = 0
        for layer in self.records:
            if layer.source == handle and layer.status != "expired" and not layer.resolved:
                self._expire_layer(layer)
                dropped += 1
        return dropped

    def register_rule(
        self,
        kind: str,
        source: Handle,
        controller: Handle,
        targets: tuple[Handle, ...],
        atom: Atom,
        duration: Duration | None,
    ) -> LayerRecord:
        """A DISPATCHED combat rule atom: a MANDATE_ATTACK / MANDATE_BLOCK
        that carries a duration ("attacks this turn if able", "must be blocked
        this turn if able", goad's "until your next turn"), or an
        ATTACK_POLICY ("it can attack this turn as though it didn't have
        defender"). The creatures were designated at resolution (fixed
        ``targets``), and the record rides the registry's duration expiry:
        Eot at cleanup (CR 514.2), UntilNextTurn when the controller's next
        turn begins (CR 611.2b), UntilNextStep at its step, While while its
        condition holds, UntilLeaves when the source leaves. ``kind`` is
        ``"mandate"``, ``"mandate_block"`` or ``"attack_policy"``, so legality
        reads it beside the static ones."""
        return self._new_resolved(kind, source, controller, (atom,), targets, duration)

    def _new_resolved(
        self,
        kind: str,
        source: Handle,
        controller: Handle,
        payload: object,
        targets: tuple[Handle, ...],
        duration: Duration | None,
    ) -> LayerRecord:
        """A record a RESOLVED spell or ability made over the objects it designated: it outlives
        its source (CR 611.2a, :meth:`detach_source` skips it) and drops an object that leaves
        the battlefield (CR 400.7, :meth:`forget_departed`)."""
        layer = self._new(
            kind, source, controller, payload, targets, duration=duration, resolved=True
        )
        self._resolved.append(layer)
        return layer

    def forget_departed(self, handle: Handle) -> int:
        """A designated object left the battlefield: if it returns it is a
        new object (CR 400.7) that no resolved effect was applied to, so it
        drops out of every live ``resolved`` record's targets (a record left
        with none expires). Returns the number of records touched."""
        touched = 0
        for layer in self._resolved:
            if layer.status != "expired" and handle in layer.targets:
                layer.targets = tuple(t for t in layer.targets if t != handle)
                if not layer.targets:
                    self._expire_layer(layer)
                touched += 1
        return touched

    def forget_materialized(self, handle: Handle) -> None:
        """CR 400.7: ``handle`` left the battlefield, and ``DurationLedger.forget`` expired
        its P/T entries, a static's materialized one included. Drop the statics' links to
        them, so if it returns the next recompute gives the new object an entry of its own (a
        leave-and-return inside one op meets no recompute in between that would have found
        the link stale)."""
        for layer in self.records:
            layer.ledger_ids.pop(handle, None)

    def register_grant(
        self,
        source: Handle,
        controller: Handle,
        targets: tuple[Handle, ...],
        ability: Ability,
        duration: Duration | None,
    ) -> LayerRecord:
        """The runtime GRANT_ABILITY verb: a resolved record over the
        designated objects; durations respected incl. until-end-of-turn
        grants (an Embercleave-style EoT keyword grant)."""
        return self._new_resolved("grant", source, controller, ability, targets, duration)

    def register_lose(
        self,
        source: Handle,
        controller: Handle,
        targets: tuple[Handle, ...],
        ability: Ability,
        duration: Duration | None,
    ) -> LayerRecord:
        """The runtime LOSE_ABILITY verb (Soul Sear): a keyword is removed
        whether printed or granted, any other ability from the granted ones
        (see the module-level matchers)."""
        return self._new_resolved("lose", source, controller, ability, targets, duration)

    def _new(
        self,
        kind: str,
        source: Handle,
        controller: Handle,
        payload: object,
        targets: tuple[Handle, ...] = (),
        duration: Duration | None = None,
        selector: Selector | None = None,
        condition: Filter | None = None,
        resolved: bool = False,
    ) -> LayerRecord:
        self._seq += 1
        layer = LayerRecord(
            seq=self._seq,
            kind=kind,
            source=source,
            controller=controller,
            payload=payload,
            tag=duration_tag(duration),
            targets=targets,
            selector=selector,
            duration=duration,
            condition=condition,
            resolved=resolved,
        )
        self.records.append(layer)
        return layer

    def _new_static(
        self, handle: Handle, static: StaticAbility, controller: Handle | None = None
    ) -> list[LayerRecord]:
        """Parse a StaticAbility node and return the layer records it
        registers: a single Atom or a Seq of Atoms over the layer-capable
        verbs; anything else is flagged, not guessed. An ``OptionalEffect``
        wrapper is stripped first: Teferi, Master of Time's static compiles
        its GRANT_ACTIVATION payload inside one ("you may activate"), and
        the MAY belongs to the USE side (the permission layer is
        unconditional once the static is live).

        Mandate, prevention and disclosure atoms split out (comment below);
        the rest becomes one record. A MANA_POLICY-bearing static takes the
        ``mana_policy`` branch — the corpus compiles BOTH spend-policy
        shapes this way (Vodalian Arcanist's THIS_MANA, Chromatic Orrery's
        ALL_YOURS), and neither carries the ``target`` selector the
        PT/grant payloads require (their role table is scope/filter), so
        the generic path would die on its own assert. GRANT_ACTIVATION
        (role table: filter/window) and ADD_LAND_PLAY take the same
        selector-less shape. Such a layer is a PERMISSION: no selector, no
        materialization, and its liveness is exactly the anchor permanent's
        (``_layer_live`` — source on the battlefield, condition holding).
        ``controller`` overrides the battlefield anchor (emblem statics)."""
        if controller is None:
            controller = self.executor.controller_of(handle)  # GAIN_CONTROL overlay
        steps = static.effect
        if isinstance(steps, OptionalEffect):  # the "you may" is the use
            steps = steps.inner
        atoms: list[Atom] = []
        if isinstance(steps, Atom):
            atoms = [steps]
        elif isinstance(steps, Seq):
            for step in steps.steps:
                if not isinstance(step, Atom):
                    raise NotImplementedError(
                        "executor: StaticAbility payload "
                        f"{type(step).__name__} is not layer-parseable (12e)"
                    )
                atoms.append(step)
        else:
            raise NotImplementedError(
                "executor: StaticAbility payload "
                f"{type(steps).__name__} is not layer-parseable (12e)"
            )
        # MANDATE_ATTACK (CR 508.1 "attacks each combat if able") is a RULE,
        # not a layer payload — Furor of the Bitten compiles the enchanted
        # creature's "+2/+2 AND attacks if able" as one static, so the
        # mandate atoms are SPLIT OUT and registered as "mandate" permission
        # layers (the atom's ``cards`` selector names the subjects; liveness
        # exactly like any static record — Furor leaving ends the mandate
        # with it); the remaining atoms take the ordinary layer path below.
        # MANDATE_BLOCK (Canopy Stalker "must be blocked if able", CR 509.1h)
        # and ATTACK_POLICY (Drowsing Tyrannodon "can attack as though it
        # didn't have defender", CR 609.4) split the same way into
        # "mandate_block" / "attack_policy" layers, and PREVENT_EFFECT
        # atoms (the PREVENTION static family — Tome Anima "can't be blocked", Faith's Fetters'
        # two-part attack/block veto) route to the REPLACEMENT registry as
        # lifetime PreventionRecords — the same record shape the activated
        # prevents register, consumed by the block/attack legality. The
        # StaticAbility.condition (Tome Anima's "as long as you've drawn two
        # or more") becomes the record's condition, judged LIVE at every
        # consult (the draw clock can flip mid-combat); the atom's own
        # ``condition`` argument mirrors an event slot in every corpus
        # prevention shape (the ``_dbe_both`` idiom), so the event carries it.
        # REVEAL/LOOK_AT payload statics (Conspicuous Snoop "Play with the
        # top card of your library revealed.") split into "disclosure"
        # layers. A continuous disclosure is a ZONE-KNOWLEDGE rule, not a
        # layer mutation (the verb lane records REVEAL/LOOK_AT as no-ops
        # too), so the static lane registers the fact as a lifetime record
        # — visible in the layer registry, anchored to the source's
        # liveness exactly like a mandate, and inert at re-apply because it
        # mutates nothing by rules right: the record IS the promise ("the
        # card is played revealed").
        prevents = [atom for atom in atoms if atom.verb is Verb.PREVENT_EFFECT]
        # One record per atom, kind by kind in this order (the record seq is
        # fingerprinted), each live exactly while the static is.
        split_kinds = (
            ("disclosure", (Verb.REVEAL, Verb.LOOK_AT)),
            ("mandate", (Verb.MANDATE_ATTACK,)),
            ("mandate_block", (Verb.MANDATE_BLOCK,)),
            ("attack_policy", (Verb.ATTACK_POLICY,)),
        )
        split_verbs = {verb for _kind, verbs in split_kinds for verb in verbs}
        rest = [
            atom
            for atom in atoms
            if atom.verb not in split_verbs and atom.verb is not Verb.PREVENT_EFFECT
        ]
        records: list[LayerRecord] = [
            self._new(
                kind,
                handle,
                controller,
                (atom,),
                condition=static.condition,
                duration=_static_while_duration([atom]),
            )
            for kind, verbs in split_kinds
            for atom in atoms
            if atom.verb in verbs
        ]
        for atom in prevents:
            event = atom.args.get("event")
            step = atom.args.get("step")
            self.executor.replacements.register_prevention(
                handle,
                controller,
                static.condition,
                cast(EventSpec, event),
                cast("Step | None", step),
                _static_while_duration([atom]),
                (),
            )
        if not rest:
            return records
        atoms = rest
        if any(atom.verb == Verb.MANA_POLICY for atom in atoms):
            if any(atom.verb != Verb.MANA_POLICY for atom in atoms):
                raise NotImplementedError(
                    "executor: StaticAbility mixing MANA_POLICY with other "
                    "payload verbs is not parseable (13b scope)"
                )
            records.append(
                self._new(
                    "mana_policy",
                    handle,
                    controller,
                    tuple(atoms),
                    condition=static.condition,
                    duration=_static_while_duration(atoms),
                )
            )
            return records
        if any(atom.verb == Verb.GRANT_ACTIVATION for atom in atoms):
            if any(atom.verb != Verb.GRANT_ACTIVATION for atom in atoms):
                raise NotImplementedError(
                    "executor: StaticAbility mixing GRANT_ACTIVATION with "
                    "other payload verbs is not parseable (13c scope)"
                )
            for atom in atoms:
                _validate_activation_grant(atom)
            records.append(
                self._new(
                    "activation_grant",
                    handle,
                    controller,
                    tuple(atoms),
                    condition=static.condition,
                    duration=_static_while_duration(atoms),
                )
            )
            return records
        if any(atom.verb == Verb.ADD_LAND_PLAY for atom in atoms):
            # Azusa's "You may play two additional lands on each of your
            # turns" is a STATIC ability (CR 604.1): a continuous effect
            # that raises its controller's land allowance while the
            # permanent is on the battlefield (CR 305.2). Same
            # selector-less "land_play" record the runtime handler registers
            # (verbs._v_add_land_play), so land_play_bonus sums both; its
            # liveness is the anchor permanent's, like mana_policy. The "you
            # may" was unwrapped above: it is the use, playing the land.
            if any(atom.verb != Verb.ADD_LAND_PLAY for atom in atoms):
                raise NotImplementedError(
                    "executor: StaticAbility mixing ADD_LAND_PLAY with other "
                    "payload verbs is not parseable"
                )
            for atom in atoms:
                count_q = atom.args.get("count")
                if count_q is None:
                    count_q = QConst(1)  # "an additional land" (role optional)
                if not isinstance(count_q, QConst) or count_q.value < 0:
                    raise NotImplementedError(
                        f"executor: static ADD_LAND_PLAY count {count_q!r} is not "
                        "layer-parseable (a constant is the only shape in the pool)"
                    )
                records.append(
                    self._new(
                        "land_play",
                        handle,
                        controller,
                        (QConst(count_q.value),),
                        condition=static.condition,
                        duration=_static_while_duration([atom]),
                    )
                )
            return records
        for atom in atoms:
            if atom.verb not in _LAYER_PAYLOAD_VERBS:
                raise NotImplementedError(
                    f"executor: StaticAbility payload verb {atom.verb.name} "
                    "is not layer-parseable (12e)"
                )
        selector = atoms[0].args.get("target")
        assert isinstance(selector, Selector)  # role table: target is required
        if any(a.args.get("target") != selector for a in atoms[1:]):
            raise NotImplementedError(
                "executor: StaticAbility steps on different populations are "
                "not layer-parseable (a layer record holds one selector)"
            )
        records.append(
            self._new(
                "static",
                handle,
                controller,
                tuple(atoms),
                selector=selector,
                condition=static.condition,
                duration=_static_while_duration(atoms),
            )
        )
        return records

    def register_mana_policy(self, source: Handle, controller: Handle, atom: Atom) -> LayerRecord:
        """The RUNTIME-dispatched MANA_POLICY atom (the handler path,
        ``verbs._v_mana_policy`` — an atom executed as an effect). It joins
        the SAME record list as the static-attached policies, so recompute
        and detach treat it identically; it carries no duration (the role
        table has none), so it lives while its anchor does (corpus:
        Orrery/Vodalian arrive via attach, not dispatch)."""
        return self._new("mana_policy", source, controller, (atom,))

    def register_type_grant(
        self,
        source: Handle,
        controller: Handle,
        targets: tuple[Handle, ...],
        atom: Atom,
        duration: Duration | None = None,
    ) -> LayerRecord:
        """The RUNTIME-dispatched GRANT_TYPE atom (the handler path —
        Riddleform's ETB trigger dispatches a fixed-target, EoT-bounded
        ``"is a Sphinx in addition to its other types"``). It carries the
        atom as a single-element payload tuple and a fixed ``targets`` set
        (the designated set, NOT a re-resolved selector — a runtime grant
        designates its objects once). The generic static path
        (:meth:`_new_static`) covers the PRINTED Anthems-style GRANT_TYPE;
        this is the trigger-dispatched sibling. :meth:`type_overlay` reads
        both."""
        return self._new_resolved("type_grant", source, controller, (atom,), targets, duration)

    def register_activation_grant(
        self, source: Handle, controller: Handle, atom: Atom
    ) -> LayerRecord:
        """The RUNTIME-dispatched GRANT_ACTIVATION permission (Teferi,
        Master of Time's static registers through :meth:`_new_static`; this
        is the handler path for a granted/inline shape). Selector-less
        permission layer, validated like the static branch."""
        _validate_activation_grant(atom)
        return self._new("activation_grant", source, controller, (atom,))

    def register_land_play(
        self,
        source: Handle,
        controller: Handle,
        count: int,
        duration: Duration | None = None,
    ) -> LayerRecord:
        """The RUNTIME-dispatched ADD_LAND_PLAY permission
        (``verbs._v_add_land_play``; Azusa's printed static registers the
        same record through :meth:`_new_static`). A SELECTOR-LESS permission
        layer (no target/materialization) whose only payload is the integer
        bonus ``count``; :meth:`land_play_bonus` sums the live layers anchored to
        a seat and the land gate (:func:`stack.land_playable`) folds that
        sum into the CR 305.1 allowance. The payload tuple wraps the count
        as ``QConst(count)`` so the canonical dump prints it as a Quantity
        repr (audit-stable, not a bare int)."""
        if count < 0:
            raise ValueError(f"executor: ADD_LAND_PLAY count must be >= 0, got {count}")
        return self._new(
            "land_play",
            source,
            controller,
            (QConst(count),),
            duration=duration,
        )

    def this_mana_filter(self, source: Handle) -> Filter | None:
        """The live THIS_MANA restriction governing ``source``'s mana (the
        permanent's own compiled Vodalian policy, or a runtime-dispatched
        one anchored to it), else None. First-live-record order (a second
        policy on the same permanent intersects the first in real MTG; the
        corpus has exactly one)."""
        for layer in sorted(self.records, key=lambda l: l.seq):
            if layer.kind != "mana_policy" or layer.status != "live":
                continue
            if layer.source != source:
                continue
            for atom in layer.atoms:
                if atom.args.get("scope") == "THIS_MANA":
                    value = atom.args.get("filter")
                    if value is None:
                        return None
                    assert isinstance(
                        value, (FAnd, FOr, FNot, FAtom)
                    )  # role table: Filter
                    return value
        return None

    def all_yours_live(self, controller: Handle) -> bool:
        """Is an ALL_YOURS permission (Orrery's "spend mana as though it
        were mana of any color") currently live for ``controller``?"""
        for layer in self.records:
            if layer.kind != "mana_policy" or layer.status != "live":
                continue
            if layer.controller != controller:
                continue
            if any(atom.args.get("scope") == "ALL_YOURS" for atom in layer.atoms):
                return True
        return False

    # -------------------------------------------------------------- recompute

    def _ctx(self, source: Handle, controller: Handle) -> ExecCtx:
        ex = self.executor
        return ExecCtx(
            world=ex.world,
            ledger=ex.ledger,
            controller=controller,
            source=source,
            bindings={},
            decisions=(),
            events=[],
            rng=ex.rng,
            token_counts=ex.token_counts,
            # Static-target enumeration and permission filters read the
            # ATTACHMENT table (IS_ATTACHED_TO_SOURCE) and the type overlay
            # through these — state-free reads, replay-safe.
            layers=self,
            executor=ex,
            # ... and the journal (journal-aware eval at ALL entry points).
            journal=ex.journal,
        )

    def _layer_live(self, layer: LayerRecord) -> bool:
        if layer.status == "expired":
            return False
        world = self.world
        # An emblem's synthetic handle is replayed state on the
        # EXECUTOR (emblems are not world cards), so its statics live
        # while the emblem is granted. A resolved record does not need its
        # source (CR 611.2a: a token that made it may have ceased to exist,
        # CR 704.5d), unless its duration is a condition read off the source.
        if (
            layer.source not in world.cards
            and layer.source not in self.executor.emblems.values()
            and (not layer.resolved or isinstance(layer.duration, DurationWhileCondition))
        ):
            return False
        if layer.from_static and layer.source in self.executor.phased_out:
            # CR 702.26b: a phased-out permanent's static abilities do not
            # function (dormant, not expired: they resume when it phases in).
            return False
        if layer.condition is not None and not eval_filter(
            layer.condition, layer.source, self._ctx(layer.source, layer.controller)
        ):
            return False
        if isinstance(layer.duration, DurationWhileCondition):
            return eval_filter(
                layer.duration.filter,
                layer.source,
                self._ctx(layer.source, layer.controller),
            )
        return True

    def _static_targets(self, layer: LayerRecord) -> tuple[Handle, ...]:
        from MTG_bot.core.executor.legality import enumerate_candidates

        assert layer.selector is not None
        ctx = self._ctx(layer.source, layer.controller)
        return tuple(
            h
            for h in enumerate_candidates(layer.selector, ctx)
            if h.namespace == "card" and self.world.zone_of(h).kind == "battlefield"
        )

    def recompute(self) -> int:
        """The set-change + duration-event pass (the executor calls it at
        the end of every public op). Conditions update layer status,
        static PT payloads (re-)materialize per live target, and the
        keyword / granted-ability derived maps are rebuilt from scratch.
        Returns the number of state transitions (a diagnostics count)."""
        changed = 0
        for layer in self.records:
            if layer.status != "expired":
                live_now = self._layer_live(layer)
                want = "live" if live_now else "dormant"
                if layer.status != want:
                    layer.status = want
                    changed += 1
            if layer.kind == "static" and layer.status == "live":
                changed += self._materialize_static(layer)
            elif layer.status != "live":
                changed += self._unmaterialize(layer)
        self._rebuild_maps()
        return changed

    def _materialize_static(self, layer: LayerRecord) -> int:
        """Ensure every live target of a PT-bearing static owns exactly one
        live ledger entry carrying the static's CURRENT value; stale
        targets' entries terminal-expire."""
        from MTG_bot.core.executor.verbs import pt_atom_delta

        targets = set(self._static_targets(layer))
        changed = 0
        stale = [h for h in layer.ledger_ids if h not in targets]
        if stale:
            self.executor.ledger.expire(layer.ledger_ids[h] for h in stale)
            for h in stale:
                del layer.ledger_ids[h]
            changed += len(stale)
        atoms = [a for a in layer.atoms if a.verb in _PT_VERBS]
        if not atoms:
            return changed
        ctx = self._ctx(layer.source, layer.controller)
        for target in sorted(targets):
            power_delta = toughness_delta = 0
            power_set = toughness_set = None
            for atom in atoms:
                p_delta, t_delta, p_set, t_set = pt_atom_delta(atom, ctx)
                power_delta += p_delta
                toughness_delta += t_delta
                power_set = p_set if p_set is not None else power_set
                toughness_set = t_set if t_set is not None else toughness_set
            kind = (
                "set"
                if (power_set is not None or toughness_set is not None)
                else "delta"
            )
            linked = layer.ledger_ids.get(target)
            if linked is not None:
                # The value is re-read on EVERY pass. A static's effect is
                # not locked in (CR 611.3a), so a counted bonus (Malefic
                # Scythe's soul counters, Carrion Grub's graveyard power)
                # follows its count up AND down (CR 613.4a/c). The entry is
                # revalued in place: same effect, same timestamp (CR 613.7a).
                if self.executor.ledger.revalue(
                    linked, kind, power_delta, toughness_delta, power_set, toughness_set
                ):
                    changed += 1
                continue
            change = self.executor.ledger.record(
                self.world.cards[target].identity,
                kind,
                target,
                power_delta=power_delta,
                toughness_delta=toughness_delta,
                power_set=power_set,
                toughness_set=toughness_set,
                tag=layer.tag,
                clock=self.executor.journal.clock,
                duration=layer.duration,
                source=layer.source,
                controller=layer.controller,
            )
            layer.ledger_ids[target] = change.record_id
            changed += 1
        return changed

    def _unmaterialize(self, layer: LayerRecord) -> int:
        """A dormant/expired layer's materialized entries terminal-expire;
        a WHILE layer that goes live again re-materializes a fresh entry on
        the next pass (the ledger dump keeps every row — the audit trail
        replays, and the re-materialization's own timestamp is the rule:
        the buff restarts when the condition restarts)."""
        if not layer.ledger_ids:
            return 0
        self.executor.ledger.expire(list(layer.ledger_ids.values()))
        layer.ledger_ids.clear()
        return 1

    # ------------------------------------------------------------ expiry API

    def _expire_layer(self, layer: LayerRecord) -> None:
        layer.status = "expired"
        if layer.ledger_ids:
            self.executor.ledger.expire(list(layer.ledger_ids.values()))
            layer.ledger_ids.clear()

    def sweep_at_eot(self) -> int:
        """End-of-turn: expire every live Eot-tagged layer (Embercleave-
        style grants die here — tested)."""
        expired = 0
        for layer in self.records:
            if layer.tag == "Eot" and layer.status != "expired":
                self._expire_layer(layer)
                expired += 1
        return expired

    def expire_leaves(self, anchor: Handle) -> int:
        """UNTIL_LEAVES zone interceptor (terminal — a return to the zone
        does not restore it). ``source`` (the ability's own permanent) is
        the only referent the pool data for this duration uses, so the
        anchor IS the layer source."""
        expired = 0
        for layer in self.records:
            dur = layer.duration
            if (
                isinstance(dur, DurationUntilLeaves)
                and dur.source == "source"
                and layer.source == anchor
                and layer.status != "expired"
            ):
                self._expire_layer(layer)
                expired += 1
        return expired

    def expire_at_step(self, step: Step, active: Handle, controller_of) -> int:
        """UNTIL_NEXT_STEP tick (the executor ticks only UNTAP).
        Owner-scoped layers expire when an AFFECTED permanent's controller
        experiences the tick; unscoped layers bind to the active turn."""
        expired = 0
        for layer in self.records:
            dur = layer.duration
            if not isinstance(dur, DurationUntilNextStep) or dur.step is not step:
                continue
            if layer.status == "expired":
                continue
            if dur.owner_scoped:
                affected = list(layer.targets) or [layer.source]
                if any(
                    t.namespace == "card" and controller_of(t) == active
                    for t in affected
                ):
                    self._expire_layer(layer)
                    expired += 1
            else:
                self._expire_layer(layer)
                expired += 1
        return expired

    def expire_until_next_turn(self, player: Handle) -> int:
        """``player``'s turn begins: "until your next turn" records end (CR 611.2b),
        and "until the end of your next turn" ones become "until end of turn", so this
        turn's cleanup sweep ends them (CR 514.2)."""
        expired = 0
        for layer in self.records:
            if layer.status == "expired" or layer.controller != player:
                continue
            if isinstance(layer.duration, DurationUntilNextTurn):
                self._expire_layer(layer)
                expired += 1
            elif isinstance(layer.duration, DurationUntilEndOfNextTurn):
                layer.tag = "Eot"
        return expired

    # ------------------------------------------------------------- derived

    def _rebuild_maps(self) -> None:
        """Rebuild keyword / granted-ability views: printed identity
        keywords as the base, then LIVE layers in seq order — grants add,
        losses remove, later seq wins (continuous effects timestamp-order,
        the same principle as the PT stack)."""
        world = self.world
        keywords: dict[Handle, list[str]] = {
            handle: list(card.identity.keywords)
            for handle, card in sorted(world.cards.items())
        }
        granted: dict[Handle, list[GrantedAbility]] = {}
        types: dict[Handle, list[str]] = {}

        for layer in sorted(self.records, key=lambda l: l.seq):
            if layer.status != "live":
                continue
            if layer.kind == "static":
                targets = self._static_targets(layer)
                for atom in layer.atoms:
                    payload = atom.args.get("ability")
                    if atom.verb == Verb.GRANT_ABILITY:
                        for target in targets:
                            self._apply_add(keywords, granted, target, payload, layer)
                    elif atom.verb == Verb.LOSE_ABILITY:
                        for target in targets:
                            self._apply_remove(keywords, granted, target, payload)
                    elif atom.verb == Verb.GRANT_TYPE:
                        # Printed static type-grant anthem (Dub, Demonic
                        # Embrace): scope-resolved every recompute, so a
                        # creature entering later is covered too.
                        for target in targets:
                            self._apply_type(types, target, atom)
            elif layer.kind == "type_grant":
                for atom in layer.atoms:
                    for target in layer.targets:
                        self._apply_type(types, target, atom)
            elif layer.kind == "lose":
                for target in layer.targets:
                    self._apply_remove(keywords, granted, target, layer.payload)
            else:  # "keyword" / "grant"
                for target in layer.targets:
                    self._apply_add(keywords, granted, target, layer.payload, layer)

        self._keywords = {
            handle: tuple(sorted(set(names))) for handle, names in keywords.items()
        }
        self._granted = {
            handle: tuple(group) for handle, group in granted.items() if group
        }
        self._types = {
            handle: tuple(sorted(set(words))) for handle, words in types.items()
        }

    @staticmethod
    def _apply_type(types: dict[Handle, list[str]], target, atom: Atom) -> None:
        """GRANT_TYPE payload: the ``types`` role is the tuple of type/subtype
        words added ("Knight", "Demon", "Sphinx"). Union into the overlay —
        "in addition to its other types" never REMOVES (the corpus has no
        type-removing verb)."""
        words = atom.args.get("types")
        if not isinstance(words, tuple):
            raise TypeError(
                f"executor: GRANT_TYPE types role must be a tuple, got {words!r}"
            )
        bucket = types.setdefault(target, [])
        bucket.extend(words)

    @staticmethod
    def _apply_add(keywords, granted, target, payload, layer: LayerRecord) -> None:
        if isinstance(payload, KeywordAbility):
            names = keywords.setdefault(target, [])
            if payload.keyword.name not in names:
                names.append(payload.keyword.name)
        elif isinstance(payload, Ability):
            granted.setdefault(target, []).append(GrantedAbility(payload, layer.source))

    @staticmethod
    def _apply_remove(keywords, granted, target, payload) -> None:
        if isinstance(payload, KeywordAbility):
            keywords[target] = [
                name
                for name in keywords.get(target, [])
                if not _lose_matches_keyword(payload, name)
            ]
        else:
            granted[target] = [
                g
                for g in granted.get(target, [])
                if not _lose_matches_ability(payload, g.node)
            ]

    # ------------------------------------------------------------ predicates

    def keyword_of(self, handle: Handle, keyword) -> bool:
        """Does ``handle`` currently have the keyword (printed ∪ granted,
        minus live losses)? The oracle combat and legality read (flying,
        haste, trample, ...)."""
        return _keyword_name(keyword) in self._keywords.get(handle, ())

    def keywords(self, handle: Handle) -> tuple[str, ...]:
        return self._keywords.get(handle, ())

    def holders(self, keyword) -> tuple[Handle, ...]:
        """Every card currently carrying the keyword (printed ∪ granted,
        minus live losses), Handle-sorted. ``keyword_of`` answers one
        handle; the binder's keyword-trigger drain (PROWESS, BATTALION)
        needs the POPULATION — the same oracle, inverted."""
        name = _keyword_name(keyword)
        return tuple(
            handle
            for handle in sorted(self._keywords)
            if name in self._keywords[handle]
        )

    def granted_abilities(self, handle: Handle) -> tuple[GrantedAbility, ...]:
        """Every live granted ability on ``handle``, layer-seq ordered (the
        canonical negative-index basis legality's ``legal_activations``
        uses: row ``-k-1`` is entry ``k`` of THIS tuple)."""
        return self._granted.get(handle, ())

    def granted_activated(self, handle: Handle) -> tuple[GrantedAbility, ...]:
        return tuple(
            g
            for g in self._granted.get(handle, ())
            if isinstance(g.node, ActivatedAbility)
        )

    # ------------------------------------------------------- layer views

    def type_overlay(self, handle: Handle) -> tuple[str, ...]:
        """The extra type/subtype words a live GRANT_TYPE layer adds to
        ``handle`` (empty when none) — the ORACLE the TYPE_EQ / SUBTYPE_EQ /
        SUPERTYPE_EQ filter evaluator unions into the printed type line
        ("is a Knight in addition to its other types")."""
        return self._types.get(handle, ())

    def instant_window_granted(self, handle: Handle) -> bool:
        """Teferi, Master of Time: may ``handle``'s sorcery-timed
        activations run at INSTANT speed right now? True when some live
        GRANT_ACTIVATION layer's filter matches ``handle`` (the filter reads
        the permanent's shape — Teferi's compiled TYPE_EQ Planeswalker +
        NAME_CONTAINS "Teferi" gate). The filter is anchored at the LAYER's
        source/controller, so a NAME_CHOSEN-bearing filter would see the
        granting permanent's record — the corpus filter is shape-only."""
        for layer in self.records:
            if layer.kind != "activation_grant" or layer.status != "live":
                continue
            for atom in layer.atoms:
                # _validate_activation_grant ran at registration: a Filter and
                # an INSTANT (or absent) window.
                filter_ = cast(Filter, atom.args.get("filter"))
                if eval_filter(
                    filter_,
                    handle,
                    self._ctx(layer.source, layer.controller),
                ):
                    return True
        return False

    def live_records(self, kind: str) -> list[LayerRecord]:
        """Every LIVE layer record of a combat-rule ``kind`` (``"mandate"``:
        MANDATE_ATTACK; ``"mandate_block"``: MANDATE_BLOCK, CR 509.1h;
        ``"attack_policy"``: ATTACK_POLICY), static or dispatched. NOT keyed by
        the anchor controller — the rule's subject set comes from each layer's
        own ``cards`` selector or designated ``targets`` (an aura's "enchanted
        creature attacks if able" binds that creature's CONTROLLER, which may
        be an opponent of the aura's controller)."""
        return [
            layer
            for layer in self.records
            if layer.kind == kind and layer.status == "live"
        ]

    # ------------------------------------------- damage policy + protection

    def policy_as_unblocked(self, handle: Handle) -> bool:
        """Garruk, Savage Herald's −7: does ``handle`` currently
        carry the granted ``DAMAGE_ASSIGN_POLICY`` scope ``AS_UNBLOCKED``
        — "you may have this creature assign its combat damage as though
        it weren't blocked"? The corpus carrier is the runtime
        GRANT_ABILITY row (the granted map is rebuilt live by recompute,
        so expiry/leaves liveness is exact); the walk unwraps the
        OptionalEffect ("you may" is the DAMAGE-STEP ask, not a layer
        gate) and the Seq."""

        def carries(node: object) -> bool:
            effect = getattr(node, "effect", None)
            stack: list[object] = [effect] if effect is not None else []
            while stack:
                step = stack.pop()
                if isinstance(step, Atom):
                    if step.verb is Verb.DAMAGE_ASSIGN_POLICY and (
                        step.args.get("scope") == "AS_UNBLOCKED"
                    ):
                        return True
                elif isinstance(step, Seq):
                    stack.extend(step.steps)
                elif isinstance(step, OptionalEffect):
                    stack.append(step.inner)
            return False

        return any(carries(g.node) for g in self._granted.get(handle, ()))

    def protection_rows(self, handle: Handle) -> tuple[tuple[Filter, Handle, Handle], ...]:
        """CR 702.16a: the live protection qualities on a permanent OR A PLAYER,
        each with the coordinates its quality is judged in: (quality filter, the
        source of the ability that gives the protection, that source's controller).
        Rows come from printed PROTECTION keywords and one-shot grants (the keyword /
        grant records: Basri's Lieutenant, Feat of Resistance), from static grants
        (an anthem or an Aura giving protection, and Runed Halo's "You have protection
        from the chosen card name", whose target is a PLAYER), and from granted keyword
        nodes. A card whose PROTECTION was lost (LOSE_ABILITY strips the name from the
        keyword map) has none. The coordinates matter for qualities that read their
        source: NAME_CHOSEN is the Halo's chosen name."""

        def params_of(node: object) -> tuple[Filter, ...]:
            if not isinstance(node, KeywordAbility):
                return ()
            if _keyword_name(node.keyword) != _keyword_name(Keyword.PROTECTION):
                return ()
            return tuple(
                p for p in node.params if isinstance(p, (FAnd, FOr, FNot, FAtom))
            )

        is_card = handle.namespace == "card"
        if is_card and _keyword_name(Keyword.PROTECTION) not in self._keywords.get(handle, ()):
            return ()
        found: list[tuple[Filter, Handle, Handle]] = []
        for layer in self.records:
            if layer.status != "live":
                continue
            if layer.kind in ("keyword", "grant"):
                if handle in layer.targets:
                    found.extend(
                        (q, layer.source, layer.controller) for q in params_of(layer.payload)
                    )
                continue
            if layer.kind != "static" or layer.selector is None:
                continue
            grants = [
                q
                for atom in layer.atoms
                if atom.verb == Verb.GRANT_ABILITY
                for q in params_of(atom.args.get("ability"))
            ]
            if grants and handle in self._static_grant_targets(layer):
                found.extend((q, layer.source, layer.controller) for q in grants)
        for granted in self._granted.get(handle, ()):
            if granted.granter not in self.world.cards:
                continue
            controller = self.executor.controller_of(granted.granter)
            found.extend((q, granted.granter, controller) for q in params_of(granted.node))
        return tuple(found)

    def _static_grant_targets(self, layer: LayerRecord) -> tuple[Handle, ...]:
        """A static grant's targets including PLAYERS ("You have protection
        from ...", Runed Halo); _static_targets keeps battlefield cards only, which
        is what the P/T and keyword maps are keyed on."""
        from MTG_bot.core.executor.legality import enumerate_candidates

        assert layer.selector is not None
        ctx = self._ctx(layer.source, layer.controller)
        return tuple(
            h
            for h in enumerate_candidates(layer.selector, ctx)
            if h.namespace == "player"
            or (h.namespace == "card" and self.world.zone_of(h).kind == "battlefield")
        )

    def hexproof_of(self, handle: Handle) -> tuple[Filter | None, ...]:
        """CR 702.11b: the live HEXPROOF rows on ``handle`` — one entry per
        row: ``None`` for a bare "Hexproof"
        (blocks EVERY opponent-controlled source) and the row's Filter
        for "Hexproof from {quality}" (Spined Megalodon's compiled
        COLOR_HAS-U param; a multi-quality row blocks from any of its
        qualities, the ``protection_rows`` pair-consumer's twin).

        The loss-aware gate is ``_keywords`` (the materialized map, not a
        raw record scan): ``_apply_remove`` on a live LOSE_ABILITY strips
        the NAME while the originating layer records stay live, so a raw
        record scan would keep a lost keyword blocking (``protection_rows``
        gates on the same map). Name-without-a-live-params-row: the printed
        identity seeds the NAME zone-lessly, so the nameless read is the
        bare blocking row. Zone relevance is the CONSUMER's guard (legality:
        battlefield only, CR 702.11b), not this map's: the base names are
        zone-less by construction."""

        def rows_of(node: object) -> tuple[Filter | None, ...]:
            if not isinstance(node, KeywordAbility):
                return ()
            if _keyword_name(node.keyword) != _keyword_name(Keyword.HEXPROOF):
                return ()
            params = tuple(
                p for p in node.params if isinstance(p, (FAnd, FOr, FNot, FAtom))
            )
            return params or (None,)

        if _keyword_name(Keyword.HEXPROOF) not in self._keywords.get(handle, ()):
            return ()
        found: list[Filter | None] = []
        for layer in self.records:
            if layer.status != "live" or layer.kind not in ("keyword", "grant"):
                continue
            if handle not in layer.targets:
                continue
            found.extend(rows_of(layer.payload))
        for granted in self._granted.get(handle, ()):
            found.extend(rows_of(granted.node))
        return tuple(found) or (None,)

    def land_play_bonus(self, controller: Handle) -> int:
        """Azusa, Lost but Seeking: the total additional lands the
        seat's live ADD_LAND_PLAY permissions grant this turn. Summed over
        live layers ANCHORED TO ``controller`` (the controller whose land
        gate is relaxed — Azusa's "on your turn" is the permanent's
        controller's turn, matching the mana-policy controller anchor)."""
        total = 0
        for layer in self.records:
            if layer.kind != "land_play" or layer.status != "live":
                continue
            if layer.controller != controller:
                continue
            for payload in layer.atoms:
                total += cast(QConst, payload).value  # both producers wrap a QConst
        return total

    # ---------------------------------------------------------- determinism

    def dump(self) -> tuple[tuple[object, ...], ...]:
        """Canonical registry view for the replay fingerprint: every layer
        (incl. expired audit rows) in seq order, with its status, targets,
        duration tag and materialized ledger links."""
        return tuple(
            (
                layer.seq,
                layer.kind,
                str(layer.source),
                str(layer.controller),
                layer.tag,
                layer.status,
                tuple(str(t) for t in layer.targets),
                (
                    tuple(repr(a) for a in layer.payload)
                    if isinstance(layer.payload, tuple)
                    else repr(layer.payload)
                ),
                tuple(sorted((str(h), rid) for h, rid in layer.ledger_ids.items())),
            )
            for layer in sorted(self.records, key=lambda l: l.seq)
        )
