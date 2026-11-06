"""Sound, fast fork of a live engine state.

``fork(state)`` returns an independent deep copy of a ``Game`` (or a bare ``Executor``):
mutating the clone never moves the parent's ``Executor.state_fingerprint()`` bytes (the
isolation test proves it).

Mechanism: ``copy.deepcopy`` with the memo pre-seeded to intern the shared, immutable compiled
IR. The card rule objects (``CardRecord`` ability trees and their atom graphs, reachable from
``binder.records`` and from ``Supply.pool``) are compile-time constants that the executor never
mutates, so cloning them per fork would only copy bytes that must stay identical. Everything
per-game (world zones, journal, ledger, binder runtime tables, layers) is deep-copied.

After the copy, three references must not survive into the clone:
* ``executor.rng`` is a bound method of the parent; it is rebound explicitly, because it is the
  engine's randomness anchor (``_rng`` is a pure sha256(master_seed, _op_seq, tag) factory, so
  the clone inherits the exact stream position through the copied ``_op_seq``).
* ``executor.decisions.provider`` may be a closure over the parent game; it is detached
  (``None``), and the rollout layer wires its own.
* ``Game.trace`` (the ``TraceRecorder``) is export-only bookkeeping; the clone carries none.
"""

from __future__ import annotations

import copy
import types
from collections import ChainMap, deque
from typing import Any

# Types ``copy.deepcopy`` treats as atomic (returned as-is): interning them
# would bloat the memo for zero benefit, and the walker must not chase the
# function -> module -> everything graph through them.
_ATOMIC = (
    type(None),
    bool,
    int,
    float,
    complex,
    str,
    bytes,
    bytearray,
    range,
    type,
    types.FunctionType,
    types.BuiltinFunctionType,
    types.ModuleType,
    types.MethodType,
    property,
)

# id(root) -> (strong ref keeping the id alive, {id: obj} intern map).
# Compiled IR is process-stable per Supply / per pool, so one walk per root
# serves every fork ever taken from it.
_INTERN_CACHE: dict[int, tuple[Any, dict[int, Any]]] = {}


def _walk_intern(root: Any) -> dict[int, Any]:
    """Iteratively map ``id(obj) -> obj`` for every MUTABLE container /
    attr-object reachable from ``root`` (cycles and diamonds handled by the
    id guard). ``__slots__`` objects without ``__dict__`` (e.g. the frozen
    ``Handle``) are immutable and tiny: they stay un-interned and deepcopy
    mints copies — cheap and harmless."""
    intern: dict[int, Any] = {}
    stack: list[Any] = [root]
    while stack:
        obj = stack.pop()
        if isinstance(obj, _ATOMIC):
            continue
        oid = id(obj)
        if oid in intern:
            continue
        if isinstance(obj, dict):
            intern[oid] = obj
            stack.extend(obj.keys())
            stack.extend(obj.values())
        elif isinstance(obj, (list, tuple, set, frozenset, deque)):
            intern[oid] = obj
            stack.extend(obj)
        else:
            fields = getattr(obj, "__dict__", None)
            if fields is None:
                slots = getattr(type(obj), "__slots__", ())
                if not slots:
                    continue  # opaque/atomic-ish: let deepcopy's own paths decide
                intern[oid] = obj
                stack.extend(
                    v for s in slots if not (v := getattr(obj, s, None)) is None
                )
                continue
            intern[oid] = obj
            stack.extend(fields.values())
    return intern


def _interned(root: Any) -> dict[int, Any]:
    cached = _INTERN_CACHE.get(id(root))
    if cached is not None and cached[0] is root:
        return cached[1]
    intern = _walk_intern(root)
    _INTERN_CACHE[id(root)] = (root, intern)  # strong ref pins the id
    return intern


def fork(state: Any, supply: Any = None) -> Any:
    """Fork a live ``Game`` (or ``Executor``) into an independent copy.

    ``supply``: pass the game's :class:`Supply` when you have it — the walk
    then interns the whole compiled pool (a superset of ``binder.records``);
    without it the walk roots at the binder's registered card records, which
    is already every IR object the game can reference.
    """
    from MTG_bot.core.executor.games import Game

    game = isinstance(state, Game)
    executor = state.executor if game else state
    if supply is None:
        # The oracle bridge: binder.records' values ARE the pool CardRecords.
        root: Any = tuple(executor.binder.records.values())
    else:
        root = supply
    memo: Any = ChainMap({}, _interned(root))
    trace = getattr(state, "trace", None)
    if trace is not None:
        memo[id(trace)] = None  # clone carries no TraceRecorder
    clone = copy.deepcopy(state, memo)
    clone_executor = clone.executor if game else clone
    clone_executor.rng = clone_executor._rng
    clone_executor.decisions.provider = None
    return clone
