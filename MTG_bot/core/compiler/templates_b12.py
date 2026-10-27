"""Bucket B12 — self-named clauses (sets round S-3a, KNOWLEDGE /167; B-46).

Oracle text names an instant or sorcery by its own name ("Lava Axe deals 5 damage to target player
or planeswalker."), while the templates were written one card at a time: M21's burn template is
literally ``^Shock deals (\\d+) damage to any target\\.$``, so every other burn spell matched
nothing. First touch on 15 more sets found 254 unparsed dev sentences that name their own card, 53
of them a plain "<name> deals N damage to <target>."

``compile_card`` retries an unparsed sentence once with the card's own name written "~" (Step 2c)
and accepts only matches from this bucket. A sentence that compiles today is never re-read, so no
existing tree can change. Each builder is the existing carrier's builder, or the same atom over the
same selector helper, so the IR is byte-identical to the card that already carries the meaning
(identity law, DESIGN_ATOM_ONTOLOGY §6; ``test_templates_b12.py``):

* "any target": N as Shock (B5b), X as Volcanic Geyser (B5c);
* "target creature": N as Turn to Slag (B5c), X as the same atom with ``QX``;
* "target player or planeswalker", N: the effect of the B3 activated carrier;
* "each creature", N: the B6 "it deals 2 damage to each creature" atom, with N.

"target creature or planeswalker" already parses with any subject (B5b-named-damage).
"""

from __future__ import annotations

import re
from typing import Final

from MTG_bot.core.ability_tree import QX, Atom, AtomArgs, QConst, Verb
from MTG_bot.core.compiler.templates import EffectOutcome, SentenceOutcome, Template
from MTG_bot.core.compiler.templates_b3 import _sel_target_player_or_planeswalker
from MTG_bot.core.compiler.templates_b5b import _build_damage_any
from MTG_bot.core.compiler.templates_b5c import (
    _build_geyser_dmg,
    _build_turn_to_slag,
    _target_creature,
)
from MTG_bot.core.compiler.templates_b6 import _all_creatures

_BUCKET: Final[str] = "B12"
_PRIORITY: Final[int] = 10  # reached only through Step 2c, which keeps B12 matches alone


def _damage(target, amount) -> SentenceOutcome:
    return EffectOutcome(
        effect=Atom(verb=Verb.DEAL_DAMAGE, args=AtomArgs(pairs=(("target", target),
                                                                ("amount", amount))))
    )


def _build_damage_creature_x(m: re.Match[str]) -> SentenceOutcome:
    return _damage(_target_creature(), QX())


def _build_damage_player_or_planeswalker(m: re.Match[str]) -> SentenceOutcome:
    return _damage(_sel_target_player_or_planeswalker(), QConst(int(m.group(1))))


def _build_damage_each_creature(m: re.Match[str]) -> SentenceOutcome:
    return _damage(_all_creatures(), QConst(int(m.group(1))))


def _t(tid: str, name: str, pattern: str, build) -> Template:
    return Template(
        tid=tid,
        name=name,
        bucket=_BUCKET,
        pattern=re.compile(pattern),
        priority=_PRIORITY,
        build=build,
    )


TEMPLATES: tuple[Template, ...] = (
    _t("B12-damage-any", "<self> deals N damage to any target",
       r"^~ deals (\d+) damage to any target\.$", _build_damage_any),
    _t("B12-damage-any-x", "<self> deals X damage to any target",
       r"^~ deals X damage to any target\.$", _build_geyser_dmg),
    _t("B12-damage-creature", "<self> deals N damage to target creature",
       r"^~ deals (\d+) damage to target creature\.$", _build_turn_to_slag),
    _t("B12-damage-creature-x", "<self> deals X damage to target creature",
       r"^~ deals X damage to target creature\.$", _build_damage_creature_x),
    _t("B12-damage-player-or-planeswalker", "<self> deals N damage to target player or planeswalker",
       r"^~ deals (\d+) damage to target player or planeswalker\.$",
       _build_damage_player_or_planeswalker),
    _t("B12-damage-each-creature", "<self> deals N damage to each creature",
       r"^~ deals (\d+) damage to each creature\.$", _build_damage_each_creature),
)
