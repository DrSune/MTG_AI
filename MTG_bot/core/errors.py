"""Typed failure for the rebuilt engine.

The legacy engine swallowed its own errors (``engine.py`` caught every
exception, logged it, and returned), so the protocol's engine-correctness
gate EC-1 (``error_rate == 0``) was uncomputable: a broken game looked
identical to a drawn one. That is the defect this module exists to kill.

A move that is not legal is not a crash — it is ``IllegalMoveError``, and the
engine raises it instead of pretending the move happened. A card that cannot
be executed because a primitive is missing is ``UnsupportedAbilityError``
(the ``engine_supported`` flag made load-bearing). An internal invariant that
breaks is ``StateCorruptionError`` and must never be caught silently, because
it is an engine bug, not a game event.

Every error carries a ``context`` dict so a failure is reportable with the
state and the offending move attached, which is what the EC-1 and P8 gates
need to turn a red run into a diagnosis rather than a shrug.
"""

from __future__ import annotations

from typing import Any, Dict, Optional


class EngineError(Exception):
    """Base class for every failure the engine can report.

    ``message`` is human-readable. ``context`` is a machine-readable dict that
    callers (the test harness, the EC gate, the training loop) can inspect to
    find out exactly what state and what move produced the failure. Keeping
    the two separate means a log line stays readable while a gate gets
    structure.
    """

    def __init__(self, message: str, context: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.message = message
        self.context: Dict[str, Any] = dict(context or {})

    def with_context(self, **kwargs: Any) -> "EngineError":
        """Return self with extra context keys merged in. Fluent, in-place."""
        self.context.update(kwargs)
        return self

    def __str__(self) -> str:
        if self.context:
            ctx = ", ".join(f"{k}={v!r}" for k, v in sorted(self.context.items()))
            return f"{self.__class__.__name__}: {self.message} [{ctx}]"
        return f"{self.__class__.__name__}: {self.message}"


class IllegalMoveError(EngineError):
    """A move was attempted that is not legal in the current state.

    This is the single most important error to make first-class: the legacy
    engine was *permissive* (it accepted moves it should have rejected and
    then produced incoherent states). The rebuilt engine is *assertive* — one
    legality oracle, and anything it rejects raises here. A policy that
    proposes an illegal move is told so, cleanly, not by a crash later.
    """


class UnknownCardError(EngineError):
    """A reference to a card (oracle id or handle) that is not in the registry.

    Raised when state or a move names a card the world does not know. This is
    how the id-namespace separation is enforced: a stale rowid from a
    re-ingested database will not silently alias a different card, it will
    raise here.
    """


class UnsupportedAbilityError(EngineError):
    """A node in the ability tree has no executor (or no encoder token).

    This is the ``engine_supported = False`` path made load-bearing. A card
    that compiles to a tree containing an unimplemented primitive is *not in
    the enabled pool*; if it is played anyway, the engine raises here instead
    of silently no-op'ing the ability (the legacy failure mode: targeted
    spells were silent no-ops for months).
    """


class TargetingError(EngineError):
    """A move named a target that is not legal for that effect.

    Distinct from ``IllegalMoveError`` because it is the specific case the
    legacy engine got worst: targeted spells resolved as no-ops because
    targeting was never checked. A bad target must be a loud, typed failure.
    """


class InfiniteLoopError(EngineError):
    """An unbreakable loop was detected (a mandatory draw, CR 104.4b).

    Raised for the *mandatory* case, where no player has a choice that breaks
    the loop. Productive loops (a combo) are not an error — they are
    compressed into a first-class ``ShortcutLoop`` action instead — so this
    error is reserved for the draw case. ``kind`` distinguishes which
    classification produced it.
    """

    def __init__(self, message: str, kind: str = "mandatory", context: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message, context)
        self.kind = kind


class StateCorruptionError(EngineError):
    """An internal invariant of the state model was violated.

    This is an engine bug, not a game event, and it must never be caught
    silently. The legacy engine's blanket ``except Exception`` is exactly what
    let corruption propagate invisibly into the training corpus. Anything that
    reaches this error means the world object is no longer trustworthy and the
    surrounding game must be discarded and the bug fixed.
    """
