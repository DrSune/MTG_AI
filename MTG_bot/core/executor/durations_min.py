"""Deprecated name for :mod:`MTG_bot.core.executor.durations` (round 12d).

12d superseded the minimal end-of-turn ledger with the full Duration
vocabulary. Per the delegation's migration option the ledger class name is
CARRIED and this module path stays importable: every 12a/12b import site
(``verbs``, ``binding``, ``events``, ``quantity``, ``__init__``) resolves
through this shim to the single real implementation — there is exactly one
``DurationLedger`` class object in the package, so isinstance checks and
dump formats cannot drift between call sites.
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
