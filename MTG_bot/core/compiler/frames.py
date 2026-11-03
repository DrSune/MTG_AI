"""Frames (sets round S-3b, KNOWLEDGE /168): a trigger or a cost, composed with an effect clause.

The templates parse a framed sentence whole. "When this creature enters, draw a card." is one
template, and the same trigger with "you gain 2 life." would need another. First touch on 15 sets
(/167) found 1,252 unparsed dev sentences with a trigger or cost frame; in 217 of them the clause
after the frame already parses on its own.

``compile_card`` Step 2d reads such a sentence as frame + clause:
- the frame's event or cost comes from the existing helpers (B2a, B2b, B3, B5c);
- the clause comes from the registry;
- the ability is assembled exactly as those carriers assemble theirs.

It is a fallback only: Step 2d runs on a sentence nothing else parsed. The clause must parse to a
pure effect (``EffectOutcome``) and must carry no pronoun. Standalone, "it" is an object named
earlier; inside a trigger it is often the source (Emeria Captain, ZNR), so the meaning would change.

``test_frames.py`` holds the differential. Over every sentence of M21, ZNR, M20 and KHM that a
specific template parses and that a frame also composes, the composed ability is byte-identical,
except for B-47 (one token carrier's type line).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import replace
from typing import Any, Final

from MTG_bot.core.ability_tree import FAtom, FAtomPred
from MTG_bot.core.compiler import (
    templates_b2a,
    templates_b2b,
    templates_b3,
    templates_b5c,
)
from MTG_bot.core.compiler.templates import (
    EffectOutcome,
    Match,
    SentenceOutcome,
    Template,
    TemplateRegistry,
)

_BUCKET: Final[str] = "B13"

#: Words whose referent lies outside the clause. "its owner('s)" stays: the object is in the clause.
_PRONOUN: Final[re.Pattern[str]] = re.compile(
    r"\b(?:it|itself|its(?! owner)|they|them|their|that|those)\b", re.IGNORECASE
)


def _never_alone(m: re.Match[str]) -> SentenceOutcome:
    raise AssertionError("a frame is composed with a clause, never matched on its own")


def _frame(tid: str, name: str, pattern: str) -> Template:
    return Template(tid=tid, name=name, bucket=_BUCKET, pattern=re.compile(pattern),
                    priority=0, build=_never_alone)


def _triggered(event: Callable[[], Any]) -> Callable[[re.Match[str], Any], SentenceOutcome]:
    return lambda m, effect: templates_b2a._ability(event(), effect)


#: (frame, assembler). Patterns are full matches; the first frame that matches decides.
FRAMES: Final[tuple[tuple[Template, Callable[[re.Match[str], Any], SentenceOutcome]], ...]] = (
    (_frame("B13-etb", "when this permanent enters, <clause>",
            r"When this (?:creature|artifact|enchantment|Aura|land|Equipment) enters, "
            r"(?P<clause>.+)"),
     _triggered(lambda: templates_b2a._etb_event(FAtom(pred=FAtomPred.IS_SOURCE)))),
    (_frame("B13-dies", "when this creature dies, <clause>",
            r"When this creature dies, (?P<clause>.+)"),
     _triggered(templates_b2a._dies_event)),
    (_frame("B13-upkeep", "at the beginning of your upkeep, <clause>",
            r"At the beginning of your upkeep, (?P<clause>.+)"),
     _triggered(templates_b2a._upkeep_event)),
    (_frame("B13-end-step", "at the beginning of your end step, <clause>",
            r"At the beginning of your end step, (?P<clause>.+)"),
     _triggered(templates_b2a._end_step_event)),
    (_frame("B13-combat", "at the beginning of combat on your turn, <clause>",
            r"At the beginning of combat on your turn, (?P<clause>.+)"),
     _triggered(templates_b2a._combat_event)),
    (_frame("B13-attacks", "whenever this creature attacks, <clause>",
            r"Whenever this creature attacks, (?P<clause>.+)"),
     _triggered(templates_b2b._attack_event)),
    # Ontology R5-6 (2026-10-29): the targeting trigger with its actor (Thorn Lieutenant).
    (_frame("B13-targeted",
            "whenever this creature becomes the target of a spell or ability an opponent controls, "
            "<clause>",
            r"Whenever this creature becomes the target of a spell or ability an opponent "
            r"controls, (?P<clause>.+)"),
     _triggered(lambda: templates_b2b._targeted_by_an_opponent(FAtom(pred=FAtomPred.IS_SOURCE)))),
    (_frame("B13-activated", "<mana and tap cost>: <clause>",
            rf"{templates_b3._COST}\s*:\s*(?P<clause>.+)"),
     lambda m, effect: templates_b3._build_activated(templates_b3._parse_cost(m), effect)),
    (_frame("B13-loyalty", "[+N] or [-N]: <clause>", r"\[([+−]\d+)\]: (?P<clause>.+)"),
     lambda m, effect: templates_b5c._loyalty_wrapper(effect, m)),
)


def compose(sentence: str, registry: TemplateRegistry) -> tuple[Match, ...]:
    """Every reading of ``sentence`` as frame + effect clause, best first; () if there is none."""
    for frame, assemble in FRAMES:
        m = frame.pattern.fullmatch(sentence)
        if m is None:
            continue
        clause = m.group("clause")
        if _PRONOUN.search(clause):
            return ()
        clause = clause[0].upper() + clause[1:]
        return tuple(
            Match(template=replace(frame, tid=f"{frame.tid}+{c.template.tid}"),
                  outcome=assemble(m, c.outcome.effect))
            for c in registry.match(clause)
            if isinstance(c.outcome, EffectOutcome)
        )
    return ()
