"""Template-matching engine for oracle sentences.

The compiler's template layer: a registry of named, prioritised regex
templates that map a full-matched oracle sentence to a typed
``SentenceOutcome``.  Later agents add bucket modules (B1–B7) by
registering templates against this stable API; the compiler
(:mod:`compiler`) consumes the outcomes to assemble ``CardRecord`` trees.

Design constraints (KNOWLEDGE/PITFALLS.md, 02-phase1-plan.md):
- No English substrings as IR — every template maps to a structured
  outcome (Keyword, Effect, Ability, Meta, or RuleReminder).
- ``Template.pattern`` is pre-compiled for ``fullmatch``.
- ``TemplateRegistry.match`` returns ALL matching outcomes in
  priority-desc / tid-asc order; it never raises on multiple matches.
  The compiler decides ambiguity (see ``AmbiguityRecord``).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Union

from MTG_bot.core.ability_tree import (
    Ability,
    ActivationWindow,
    Cost,
    Effect,
    Filter,
    Keyword,
    Quantity,
)

# ---------------------------------------------------------------------------
# SentenceOutcome — the typed result of one template match.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class KeywordOutcome:
    """A keyword ability with typed params.

    ``params`` matches the arity/type contract of
    ``KeywordAbility.params`` (see ``_KEYWORD_PARAMS`` in ability_tree).
    """

    keyword: Keyword
    params: tuple[Quantity | Filter | Cost, ...] = ()


@dataclass(frozen=True)
class RuleReminderOutcome:
    """A sentence that is a rules reminder, not a game action.

    ``reason`` is ``'full_paren'`` for a fully-parenthesised note
    (e.g. ``(Scry a card …)``), ``'keyword_reminder'`` for a bare
    keyword sentence that matches the card's printed keyword list, or
    ``'keyword_line'`` for a comma-separated line of such keywords with
    optional trailing reminder text (``compiler._is_keyword_line``).
    """

    reason: str


@dataclass(frozen=True)
class AbilityOutcome:
    """A fully-built Ability node (triggered, activated, static, …)."""

    ability: Ability


@dataclass(frozen=True)
class EffectOutcome:
    """An Effect node to be folded into a SpellAbility or appended to a
    continuation Seq."""

    effect: Effect


@dataclass(frozen=True)
class MetaOutcome:
    """A meta-directive (e.g. ``Enchant X`` targeting conjunct).

    ``kind`` is a stable identifier (``'enchant'``, …).
    ``filter`` is the conjunct to AND onto every TARGET-mode Selector
    in the spell.
    """

    kind: str
    filter: Filter | None = None


@dataclass(frozen=True)
class AdditionalCostOutcome:
    """An additional-cost sentence for a spell.

    "As an additional cost to cast this spell, ..." produces a ``Cost``
    that the compiler attaches to the card's ``SpellAbility``
    ``additional_costs`` during assembly (on top of the printed cost,
    which stays on the ``CardRecord``).
    """

    cost: Cost



@dataclass(frozen=True)
class ActivationGateOutcome:
    """An activation-gate sentence: "Activate only if <condition>." or
    "Activate only as a sorcery." (grammar round 10, R10-1).

    The gate carries no ability or effect of its own — the compiler
    attaches its slots to the nearest preceding ``ActivatedAbility``
    during assembly, slot-disjointly (convention C25): a ``window``
    candidate must still have ``timing is None`` (R9-1, C20), a
    ``condition`` candidate must still have ``condition is None``, and a
    gate setting BOTH (Speaker's compound "only if … and only as a
    sorcery") requires both slots free. StateCorruptionError when
    nothing attachable remains. A both-None gate is a template bug and
    is rejected here.
    """

    window: ActivationWindow | None = None
    condition: Filter | None = None

    def __post_init__(self) -> None:
        if self.window is None and self.condition is None:
            raise ValueError(
                "ActivationGateOutcome: at least one of window/condition must be set"
            )


@dataclass(frozen=True)
class KickerEffectOutcome:
    """A "If this spell/it was kicked, [instead] X" sentence (ZNR).

    The compiler folds it onto the previous effect-bearing slot:
    ``replaces=False`` appends ``Conditional(WAS_KICKED, X)`` to the base
    effect (additive kicker); ``replaces=True`` makes the arm replace the
    base effect: ``Conditional(WAS_KICKED, X, else=base)`` (CR 601.2f
    alternative resolution).
    """

    effect: Effect
    replaces: bool = False


SentenceOutcome = Union[
    KeywordOutcome,
    RuleReminderOutcome,
    AbilityOutcome,
    EffectOutcome,
    KickerEffectOutcome,
    MetaOutcome,
    AdditionalCostOutcome,
    ActivationGateOutcome,
]

# ---------------------------------------------------------------------------
# Template and Match
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Template:
    """One named, prioritised regex template.

    ``pattern`` is pre-compiled (``re.compile``); the registry uses
    ``pattern.fullmatch(sentence)``.  ``build`` receives the match and
    returns the ``SentenceOutcome``.
    """

    tid: str
    name: str
    bucket: str
    pattern: re.Pattern[str]
    priority: int
    build: Callable[[re.Match[str]], SentenceOutcome]


@dataclass(frozen=True)
class Match:
    """The result of one template successfully matching a sentence."""

    template: Template
    outcome: SentenceOutcome


# ---------------------------------------------------------------------------
# AmbiguityRecord — reported by the compiler, not by the registry.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AmbiguityRecord:
    """A sentence matched ≥2 distinct outcomes; the compiler uses the
    highest-priority one but records the ambiguity for reporting."""

    sentence: str
    tids: tuple[str, ...]
    note: str


# ---------------------------------------------------------------------------
# TemplateRegistry
# ---------------------------------------------------------------------------


class TemplateRegistry:
    """Ordered registry of templates, keyed by unique ``tid``.

    Iteration and matching are in priority-descending, tid-ascending
    order (stable total order).
    """

    def __init__(self) -> None:
        self._templates: dict[str, Template] = {}

    def register(self, template: Template) -> None:
        """Add a template; raises ``ValueError`` on duplicate ``tid``."""
        if template.tid in self._templates:
            raise ValueError(f"TemplateRegistry: duplicate tid {template.tid!r}")
        self._templates[template.tid] = template

    def all(self) -> tuple[Template, ...]:
        """All registered templates in match order (priority desc, tid asc)."""
        return tuple(
            sorted(self._templates.values(), key=lambda t: (-t.priority, t.tid))
        )

    def __len__(self) -> int:
        return len(self._templates)

    def __contains__(self, tid: str) -> bool:
        return tid in self._templates

    def match(self, sentence: str) -> tuple[Match, ...]:
        """Return ALL fullmatch outcomes in priority order.

        Never raises on multiple matches — the compiler is responsible
        for ambiguity detection.  Propagates exceptions from
        ``template.build`` (a template bug is not a match failure).
        """
        matches: list[Match] = []
        for template in self.all():
            m = template.pattern.fullmatch(sentence)
            if m is not None:
                outcome = template.build(m)
                matches.append(Match(template=template, outcome=outcome))
        return tuple(matches)
