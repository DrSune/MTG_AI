"""Deprecated name for :mod:`MTG_bot.core.executor.durations`.

A re-export shim: the import sites that still use this path (``verbs``,
``binding``, ``events``, ``quantity`` and some tests) resolve to the single
real implementation — there is exactly one ``DurationLedger`` class object
in the package, so isinstance checks and dump formats cannot drift between
call sites.
"""

from __future__ import annotations

from MTG_bot.core.executor.durations import (
    EOT_TAG,
    STATUS_EXPIRED,
    STATUS_LIVE,
    STATUS_WHILE_OFF,
    DurationLedger,
    DurationMeta,
    PtChange,
    duration_tag,
    parse_pt,
)

__all__ = [
    "EOT_TAG",
    "STATUS_EXPIRED",
    "STATUS_LIVE",
    "STATUS_WHILE_OFF",
    "DurationLedger",
    "DurationMeta",
    "PtChange",
    "duration_tag",
    "parse_pt",
]
