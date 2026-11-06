"""Typed engine failures.

The engine never swallows its own errors: a broken game must not look like a
drawn one. Every error carries a ``context`` dict so a failure is reportable
with the state and the offending move attached.
"""

from __future__ import annotations

from typing import Any, Dict, Optional


class EngineError(Exception):
    """Base class for every failure the engine can report.

    ``message`` is human-readable; ``context`` is a machine-readable dict of
    the state and move that produced the failure, so a log line stays
    readable while a gate gets structure.
    """

    def __init__(self, message: str, context: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.message = message
        self.context: Dict[str, Any] = dict(context or {})

    def __str__(self) -> str:
        if self.context:
            ctx = ", ".join(f"{k}={v!r}" for k, v in sorted(self.context.items()))
            return f"{self.__class__.__name__}: {self.message} [{ctx}]"
        return f"{self.__class__.__name__}: {self.message}"


class StateCorruptionError(EngineError):
    """An internal invariant was violated.

    This is an engine bug, not a game event, and it must never be caught
    silently: the world object is no longer trustworthy and the surrounding
    game must be discarded.
    """
