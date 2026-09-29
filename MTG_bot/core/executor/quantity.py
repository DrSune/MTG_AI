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
from typing import Callable, Dict, List, Optional, Sequence, Tuple, Union

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
        raise NotImplementedError("executor: QX not implemented (12c cost context)")
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
    raise NotImplementedError(
        f"executor: QProp referent {referent!r} needs the event/result register (12b)"
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
    raise NotImplementedError(
        f"executor: QProp field {field.name} not implemented (12b event register)"
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
    closed-grammar stand-in for "is on the battlefield".) Every other
    predicate raises ``NotImplementedError`` naming itself: its completeness
    is 12c's gate, and an unsupported pred is flagged, never guessed.
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
    if pred is FAtomPred.IS_TAPPED:
        return world.cards[handle].tapped
    if pred is FAtomPred.IS_UNTAPPED:
        return not world.cards[handle].tapped
    if pred is FAtomPred.IS_PERMANENT:
        return (
            handle.namespace == "card" and world.zone_of(handle).kind == "battlefield"
        )
    if pred is FAtomPred.TYPE_EQ or pred is FAtomPred.SUBTYPE_EQ:
        assert atom.string_value is not None
        return atom.string_value in _type_line_tokens(
            world.cards[handle].identity.type_line
        )
    if pred is FAtomPred.NAME_EQ:
        assert atom.string_value is not None
        return world.cards[handle].identity.name == atom.string_value
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
    raise NotImplementedError(
        f"executor: filter pred {pred.name} not implemented (12c query surface)"
    )
