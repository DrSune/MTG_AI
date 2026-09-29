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
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable, Dict, List, Optional, Sequence, Tuple, Union

if TYPE_CHECKING:  # pragma: no cover - typing-only, dodges runtime cycles
    from MTG_bot.core.executor import Executor
    from MTG_bot.core.executor.layers import LayerRegistry
    from MTG_bot.core.executor.replacements import (
        ReplacementRecord,
        ReplacementRegistry,
    )

from MTG_bot.core.ability_tree import (
    QX,
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
    QConst,
    QCount,
    QDistinctColorCount,
    QProp,
    QPropField,
    QThisTurn,
    Quantity,
    QUnbounded,
)
from MTG_bot.core.executor.durations_min import DurationLedger
from MTG_bot.core.identity import Handle
from MTG_bot.core.state import (
    ZONE_GRAVEYARD,
    ZONE_HAND,
    ZONE_LIBRARY,
    GameWorld,
)

Binding = Union[Handle, List[Handle]]


def _default_rng(tag: str) -> random.Random:  # pragma: no cover - replaced
    """Placeholder factory; the Executor always injects its seeded factory."""
    return random.Random(0)


@dataclass
class ExecCtx:
    """Everything one effect-resolution needs: the world, the executor's
    ledger, the ability's coordinates, and the explicit decision channel.

    ``decisions`` is consumed strictly in order via :meth:`take_decision`
    (C15: every decision is enumerable and explicit — the executor holds no
    hidden randomness and no hidden choice).
    """

    world: GameWorld
    ledger: DurationLedger
    controller: Handle
    source: Handle
    bindings: Dict[str, Binding]
    decisions: Sequence[str]
    decision_idx: int = 0
    events: List[Tuple[object, ...]] = field(default_factory=list)
    rng: Callable[[str], random.Random] = _default_rng  # executor-owned seeds
    token_counts: Dict[str, int] = field(default_factory=dict)
    # 12b event register: the triggering GameEvent (or None outside trigger
    # context) and the damage amount it carried, so QProp("event", AMOUNT)
    # and the event|result referents resolve inside a firing.
    event: object = None
    event_amount: int | None = None
    # 12d registries + the owning executor: the runtime layer verbs
    # (GRANT/LOSE_ABILITY, PREVENT_EFFECT) and the damage-replacement
    # interceptor reach them through the ctx; None only in bare unit-test
    # contexts (the handlers raise a clean ValueError if invoked there).
    layers: LayerRegistry | None = None  # executor.layers
    replacements: ReplacementRegistry | None = None  # executor.replacements
    executor: Executor | None = None  # nested replacement effects
    # 13b: the cast's declared X (CR 601.2f — chosen with the total cost).
    # None means UNDECLARED: resolving a QX raises exactly as before (12c's
    # unbound flag), so every pre-13b path is byte-unchanged; cast() binds
    # it from its x parameter, effect-side CASTs default it to 0.
    x_value: int | None = None
    # 12d: damage replacements consume the event and queue their ACTION;
    # the action runs AFTER the consuming atom's journal boundary (one diff
    # per mutation — no double-emitted events), by the executor's run_atom
    # wrapper draining this list.
    pending_replacements: list[ReplacementRecord] = field(default_factory=list)

    def take_decision(self, vocab: Tuple[str, ...], what: str) -> str:
        """Consume the next decision; raise if missing or out-of-vocab."""
        if self.decision_idx >= len(self.decisions):
            raise ValueError(
                f"executor: {what} needs a decision from {vocab}, "
                f"got only {len(self.decisions)} supplied"
            )
        choice = self.decisions[self.decision_idx]
        self.decision_idx += 1
        if choice not in vocab:
            raise ValueError(f"executor: {what} decision {choice!r} not in {vocab}")
        return choice

    def binding_handles(self, role: str) -> Optional[List[Handle]]:
        """The caller-supplied handles for a role, Handle-sorted (ruling 5)."""
        value = self.bindings.get(role)
        if value is None:
            return None
        handles = [value] if isinstance(value, Handle) else list(value)
        return sorted(handles)

    def binding_one(self, role: str) -> Optional[Handle]:
        handles = self.binding_handles(role)
        return handles[0] if handles else None

    def effective_pt(self, card: Handle) -> Tuple[Optional[int], Optional[int]]:
        identity = self.world.cards[card].identity
        return self.ledger.effective_pt(identity, card)


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
        raise NotImplementedError(
            f"executor: QThisTurn({quantity.kind.name}) not implemented (12b turn ledger)"
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
    if field is QPropField.COUNTER_COUNT:
        return sum(ctx.world.cards[handle].counters.values())
    if field is QPropField.AMOUNT:
        # The triggering event's damage amount (Brash Taunter) — 12b register.
        if ctx.event_amount is None:
            raise NotImplementedError(
                "executor: QProp AMOUNT needs a triggering damage event "
                "(fired from a DamageDealtEvent)"
            )
        return ctx.event_amount
    raise NotImplementedError(
        f"executor: QProp field {field.name} not implemented (12c query surface)"
    )


def _resolve_prop(prop: QProp, ctx: ExecCtx) -> int:
    from MTG_bot.core.executor.selectors import (  # cycle-free at call time
        resolve_selector,
    )

    if isinstance(prop.referent, str):
        return _prop_value(prop.field, _referent_handle(prop.referent, ctx), ctx)
    values = [
        _prop_value(prop.field, handle, ctx)
        for handle in resolve_selector(prop.referent, ctx)
    ]
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


def _type_line_tokens(identity_text: str) -> List[str]:
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
    GRANT_TYPE overlay. Every other predicate raises
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
        # judged against the call's target bindings.
        bound = ctx.binding_handles("target")
        return bound is not None and handle in bound
    if pred is FAtomPred.IS_TAPPED:
        return world.cards[handle].tapped
    if pred is FAtomPred.IS_UNTAPPED:
        return not world.cards[handle].tapped
    if pred is FAtomPred.IS_PERMANENT:
        return (
            handle.namespace == "card" and world.zone_of(handle).kind == "battlefield"
        )
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
        return ctx.executor.attachments.get(ctx.source) == handle
    if pred is FAtomPred.NAME_EQ:
        assert atom.string_value is not None
        return world.cards[handle].identity.name == atom.string_value
    if pred in (FAtomPred.COLOR_IN, FAtomPred.COLOR_HAS):
        # 13b (the cast-trigger feed reads these over SPELL cards): COLOR_IN
        # is the grammar's SUBSET reading ("colours are a non-empty subset
        # of the given set" — Quirion Dryad's compiled blue), COLOR_HAS the
        # single-colour membership ("hexproof from black"). Identity data —
        # works for a card in any zone, incl. the stack.
        if handle.namespace != "card":
            return False
        card_colors = set(world.cards[handle].identity.colors)
        if pred is FAtomPred.COLOR_HAS:
            assert atom.color is not None
            return atom.color in card_colors
        assert atom.colors  # FAtom validation: COLOR_IN requires non-empty
        return bool(card_colors) and card_colors <= set(atom.colors)
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
    if pred is FAtomPred.HAS_COUNTER:
        assert atom.count is not None and atom.counter_kind is not None
        threshold = resolve(atom.count, ctx)
        return world.cards[handle].counters.get(atom.counter_kind.name, 0) >= threshold
    if pred is FAtomPred.CONTROLLER_IS:
        who = atom.who
        if handle.namespace != "card":
            return False
        actual = world.controller_of(handle)
        if who is None:
            return False
        from MTG_bot.core.executor.selectors import controller_matches

        return controller_matches(who, actual, ctx)
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
    raise NotImplementedError(
        f"executor: filter pred {pred.name} not implemented (12c query surface)"
    )
