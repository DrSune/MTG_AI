"""Continuous layers: static abilities, keyword/ability grants and losses
(round 12d, plan /06 §12d).

The 12b binder gave TriggeredAbility nodes a home; 12d gives the CONTINUOUS
nodes one. When a permanent's compiled record attaches (enters the
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
    QProp POWER/TOUGHNESS and the 12b dies snapshot need no changes: they
    already read the ledger.
  * **keyword / ability grants feed derived maps** rebuilt in recompute —
    printed identity keywords first, then live layers in LAYER-SEQ (first
    application-timestamp) order, so a later loss removes an earlier grant
    and a later grant re-applies over an earlier loss:
    :meth:`LayerRegistry.keyword_of` (the C18-adjacent removal matches
    printed AND granted keywords by name) and
    :meth:`LayerRegistry.granted_abilities` (what :mod:`legality` folds into
    ``legal_activations`` as negative-index rows).
  * **the controller rule for granted abilities (12d ruling):** the granted
    ability's SOURCE is the granted permanent and its ``you`` is the
    GRANTEE — the permanent's controller at activation time (legality runs
    the activation with ``source=granted handle``, ``controller=seat``);
    the granting permanent's controller only decides who WROTE the grant,
    never who may use it. Pinned by test.
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
Combat-side consumers of keywords (block/attack legality) are EXPOSED but
not wired — combat is a post-12e phase; the predicates exist so the future
consumer has a tested oracle.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, NamedTuple

from MTG_bot.core.ability_tree import (
    Ability,
    ActivatedAbility,
    Atom,
    Duration,
    DurationUntilLeaves,
    DurationUntilNextStep,
    DurationUntilNextTurn,
    DurationWhileCondition,
    FAnd,
    Filter,
    Keyword,
    KeywordAbility,
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
    node (§8.3 identity), the granting permanent, and the layer seq that
    ordered it (the canonical granted-ability index basis)."""

    node: Ability
    granter: Handle
    seq: int


_PT_VERBS = frozenset({Verb.MODIFY_PT, Verb.SET_PT})
_LAYER_PAYLOAD_VERBS = _PT_VERBS | {Verb.GRANT_ABILITY, Verb.LOSE_ABILITY}


def _is_universal(filter_: Filter) -> bool:
    """The grammar's universal filter (the binding.py twin — kept local to
    avoid importing the binder back into the layer registry)."""
    return isinstance(filter_, FAnd) and len(filter_.children) == 0


def _keyword_name(keyword) -> str:
    return keyword.name if isinstance(keyword, Keyword) else str(keyword)


def _lose_matches_keyword(payload: object, name: str) -> bool:
    """12d ruling: a LOSE keyword removes the keyword WORD, printed or
    granted (params are GRANT-side modifiers — "loses hexproof" drops
    "hexproof from blue" too, matching the CR's ability-word semantics)."""
    return isinstance(payload, KeywordAbility) and payload.keyword.name == name


def _lose_matches_ability(payload: object, node: object) -> bool:
    """Non-keyword removal matches by canonical node repr — the SAME node
    that was granted is what gets lost (C18-adjacent: printed and granted
    abilities carry identical reprs, so one LOSE hits both)."""
    return repr(payload) == repr(node)


@dataclass
class LayerRecord:
    """One continuous effect's registry entry.

    ``kind`` — ``"keyword"`` (a card's own KeywordAbility node),
    ``"static"`` (a StaticAbility node, scope-resolved), ``"grant"`` /
    ``"lose"`` (runtime GRANT_ABILITY / LOSE_ABILITY verbs, fixed targets).
    ``status`` — ``live`` | ``dormant`` (a condition currently false — the
    record survives, its effect does not apply) | ``expired`` (terminal; the
    record stays for the audit dump). ``ledger_ids`` maps each materialized
    PT target to its DurationLedger record id.
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

    @property
    def atoms(self) -> tuple[Atom, ...]:
        """Static payloads are parsed Atom tuples; every other kind wraps a
        single Ability node (atoms is then empty)."""
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

    # ------------------------------------------------------------ lifecycle

    @property
    def world(self):
        return self.executor.world

    def attach_source(self, handle: Handle, record: CardRecord) -> int:
        """Battlefield attach: register the card's own KeywordAbility nodes
        and StaticAbility nodes as layers (idempotent — this detaches the
        handle's old layers first, and the binder detaches on re-entry)."""
        self.detach_source(handle)
        count = 0
        controller = self.world.controller_of(handle)
        for kw in record.keywords:
            self._new("keyword", handle, controller, kw, (handle,))
            count += 1
        for node in record.abilities:
            if isinstance(node, KeywordAbility):
                self._new("keyword", handle, controller, node, (handle,))
                count += 1
            elif isinstance(node, StaticAbility):
                self._new_static(handle, node)
                count += 1
        return count

    def detach_source(self, handle: Handle) -> int:
        """Battlefield departure: expire every layer whose SOURCE is this
        permanent (and terminal-expire its materialized ledger entries)."""
        dropped = 0
        for layer in self.records:
            if layer.source == handle and layer.status != "expired":
                self._expire_layer(layer)
                dropped += 1
        return dropped

    def register_grant(
        self,
        source: Handle,
        controller: Handle,
        targets: tuple[Handle, ...],
        ability: Ability,
        duration: Duration | None,
    ) -> LayerRecord:
        """The runtime GRANT_ABILITY verb (12d: the PC-6 #3 raise-list item
        — now a real layer; durations respected incl. until-end-of-turn
        grants, tested with an Embercleave-style EoT keyword grant)."""
        return self._new(
            "grant", source, controller, ability, targets, duration=duration
        )

    def register_lose(
        self,
        source: Handle,
        controller: Handle,
        targets: tuple[Handle, ...],
        ability: Ability,
        duration: Duration | None,
    ) -> LayerRecord:
        """The runtime LOSE_ABILITY verb (Soul-Sear family): removal matches
        printed AND granted payloads (see the module-level matchers)."""
        return self._new(
            "lose", source, controller, ability, targets, duration=duration
        )

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
        )
        self.records.append(layer)
        return layer

    def _new_static(self, handle: Handle, static: StaticAbility) -> LayerRecord:
        """Parse a StaticAbility node: a single Atom or a Seq of Atoms over
        the layer-capable verbs; anything else is flagged, not guessed."""
        steps = static.effect
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
        for atom in atoms:
            if atom.verb not in _LAYER_PAYLOAD_VERBS:
                raise NotImplementedError(
                    f"executor: StaticAbility payload verb {atom.verb.name} "
                    "is not layer-parseable (12e)"
                )
        selector = atoms[0].args.get("target")
        assert isinstance(selector, Selector)  # role table: target is required
        return self._new(
            "static",
            handle,
            self.world.controller_of(handle),
            tuple(atoms),
            selector=selector,
            condition=static.condition,
        )

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
        )

    def _layer_live(self, layer: LayerRecord) -> bool:
        if layer.status == "expired":
            return False
        world = self.world
        if layer.source not in world.cards:
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
        live ledger entry; stale targets' entries terminal-expire."""
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
            if target in layer.ledger_ids:
                continue
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
        """UNTIL_LEAVES zone interceptor (terminal — return-to-zone does not
        restore, r5 convention). The C12 referent is resolved at 12d's
        register boundary; ``source`` (the ability's own permanent) is the
        only referent the frozen pool data for this vocab uses, so the
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
        """UNTIL_NEXT_STEP tick (only UNTAP is ticked pre-combat).
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
        expired = 0
        for layer in self.records:
            if (
                isinstance(layer.duration, DurationUntilNextTurn)
                and layer.status != "expired"
                and layer.controller == player
            ):
                self._expire_layer(layer)
                expired += 1
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

    @staticmethod
    def _apply_add(keywords, granted, target, payload, layer: LayerRecord) -> None:
        if isinstance(payload, KeywordAbility):
            names = keywords.setdefault(target, [])
            if payload.keyword.name not in names:
                names.append(payload.keyword.name)
        elif isinstance(payload, Ability):
            granted.setdefault(target, []).append(
                GrantedAbility(payload, layer.source, layer.seq)
            )

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
        minus live losses)? The combat-legality consumers (block/attack)
        are EXPOSED-BUT-UNUSED pre-12e: this predicate is the tested oracle
        they will call, never a faked combat effect."""
        return _keyword_name(keyword) in self._keywords.get(handle, ())

    def keywords(self, handle: Handle) -> tuple[str, ...]:
        return self._keywords.get(handle, ())

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

    def __len__(self) -> int:
        return len(self.records)
