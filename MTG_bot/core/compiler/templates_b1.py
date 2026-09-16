"""B1 bucket templates — 15 templates covering 15 of 15 B1 shapes.

Bucket input: ``/tmp/opencode/phase1_buckets/B1.json`` (15 normalized shape
keys → ``[card, sentence]`` pairs; sentences carry *concrete* keyword
strings and enchant targeting conjuncts).  Templates fullmatch the
**concrete** oracle sentence, never the normalized key.

Coverage (15 = 12 keyword + 3 enchant):

- **12 keyword shapes** → ``KeywordOutcome``:
  Deathtouch, Flash, Flying, Haste, Hexproof, Hexproof from black,
  Indestructible, Lifelink, Protection from planeswalkers, Reach,
  Trample, Vigilance.
- **3 enchant shapes** → ``MetaOutcome(kind="enchant", filter=...)``:
  Enchant creature, Enchant creature you control, Enchant permanent.

Conventions:
- Bare keyword sentences use ``params=()``.
- ``Hexproof from black`` → ``HEXPROOF`` with one ``Filter`` param
  (``FAtom(COLOR_HAS, color="B")``).
- ``Protection from planeswalkers`` → ``PROTECTION`` with one ``Filter``
  param (``FAtom(TYPE_EQ, string_value="Planeswalker")``).
- ``Enchant creature`` → ``MetaOutcome`` with ``FAtom(TYPE_EQ, "Creature")``.
- ``Enchant creature you control`` → ``MetaOutcome`` with
  ``FAnd(TYPE_EQ "Creature", CONTROLLER_IS YOU)``.
- ``Enchant permanent`` → ``MetaOutcome`` with ``FAtom(IS_PERMANENT)``.

PC-3: every B1 concrete sentence fullmatches **at most one** template
(patterns are pairwise disjoint by construction); verified in tests.
"""

from __future__ import annotations

import re

from MTG_bot.core.ability_tree import (
    ControllerRef,
    FAnd,
    FAtom,
    FAtomPred,
    Keyword,
)
from MTG_bot.core.compiler.templates import (
    KeywordOutcome,
    MetaOutcome,
    SentenceOutcome,
    Template,
)

_BUCKET = "B1"
_PRIORITY = 100


# ---------------------------------------------------------------------------
# Build functions (one per template)
# ---------------------------------------------------------------------------


def _build_kw_deathtouch(m: re.Match[str]) -> SentenceOutcome:
    return KeywordOutcome(keyword=Keyword.DEATHTOUCH)


def _build_kw_flash(m: re.Match[str]) -> SentenceOutcome:
    return KeywordOutcome(keyword=Keyword.FLASH)


def _build_kw_flying(m: re.Match[str]) -> SentenceOutcome:
    return KeywordOutcome(keyword=Keyword.FLYING)


def _build_kw_haste(m: re.Match[str]) -> SentenceOutcome:
    return KeywordOutcome(keyword=Keyword.HASTE)


def _build_kw_hexproof(m: re.Match[str]) -> SentenceOutcome:
    return KeywordOutcome(keyword=Keyword.HEXPROOF)


def _build_kw_hexproof_black(m: re.Match[str]) -> SentenceOutcome:
    return KeywordOutcome(
        keyword=Keyword.HEXPROOF,
        params=(FAtom(pred=FAtomPred.COLOR_HAS, color="B"),),
    )


def _build_kw_indestructible(m: re.Match[str]) -> SentenceOutcome:
    return KeywordOutcome(keyword=Keyword.INDESTRUCTIBLE)


def _build_kw_lifelink(m: re.Match[str]) -> SentenceOutcome:
    return KeywordOutcome(keyword=Keyword.LIFELINK)


def _build_kw_protection_planeswalkers(m: re.Match[str]) -> SentenceOutcome:
    return KeywordOutcome(
        keyword=Keyword.PROTECTION,
        params=(FAtom(pred=FAtomPred.TYPE_EQ, string_value="Planeswalker"),),
    )


def _build_kw_reach(m: re.Match[str]) -> SentenceOutcome:
    return KeywordOutcome(keyword=Keyword.REACH)


def _build_kw_trample(m: re.Match[str]) -> SentenceOutcome:
    return KeywordOutcome(keyword=Keyword.TRAMPLE)


def _build_kw_vigilance(m: re.Match[str]) -> SentenceOutcome:
    return KeywordOutcome(keyword=Keyword.VIGILANCE)


def _build_enchant_creature(m: re.Match[str]) -> SentenceOutcome:
    return MetaOutcome(
        kind="enchant",
        filter=FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
    )


def _build_enchant_creature_you(m: re.Match[str]) -> SentenceOutcome:
    return MetaOutcome(
        kind="enchant",
        filter=FAnd(
            children=(
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
            )
        ),
    )


def _build_enchant_permanent(m: re.Match[str]) -> SentenceOutcome:
    return MetaOutcome(
        kind="enchant",
        filter=FAtom(pred=FAtomPred.IS_PERMANENT),
    )


# ---------------------------------------------------------------------------
# Template definitions
# ---------------------------------------------------------------------------

TEMPLATES: tuple[Template, ...] = (
    Template(
        tid="B1-kw-deathtouch",
        name="Deathtouch keyword",
        bucket=_BUCKET,
        pattern=re.compile(r"^Deathtouch$"),
        priority=_PRIORITY,
        build=_build_kw_deathtouch,
    ),
    Template(
        tid="B1-kw-flash",
        name="Flash keyword",
        bucket=_BUCKET,
        pattern=re.compile(r"^Flash$"),
        priority=_PRIORITY,
        build=_build_kw_flash,
    ),
    Template(
        tid="B1-kw-flying",
        name="Flying keyword",
        bucket=_BUCKET,
        pattern=re.compile(r"^Flying$"),
        priority=_PRIORITY,
        build=_build_kw_flying,
    ),
    Template(
        tid="B1-kw-haste",
        name="Haste keyword",
        bucket=_BUCKET,
        pattern=re.compile(r"^Haste$"),
        priority=_PRIORITY,
        build=_build_kw_haste,
    ),
    Template(
        tid="B1-kw-hexproof",
        name="Hexproof keyword (bare)",
        bucket=_BUCKET,
        pattern=re.compile(r"^Hexproof$"),
        priority=_PRIORITY,
        build=_build_kw_hexproof,
    ),
    Template(
        tid="B1-kw-hexproof-black",
        name="Hexproof from black",
        bucket=_BUCKET,
        pattern=re.compile(r"^Hexproof from black$"),
        priority=_PRIORITY,
        build=_build_kw_hexproof_black,
    ),
    Template(
        tid="B1-kw-indestructible",
        name="Indestructible keyword",
        bucket=_BUCKET,
        pattern=re.compile(r"^Indestructible$"),
        priority=_PRIORITY,
        build=_build_kw_indestructible,
    ),
    Template(
        tid="B1-kw-lifelink",
        name="Lifelink keyword",
        bucket=_BUCKET,
        pattern=re.compile(r"^Lifelink$"),
        priority=_PRIORITY,
        build=_build_kw_lifelink,
    ),
    Template(
        tid="B1-kw-protection-planeswalkers",
        name="Protection from planeswalkers",
        bucket=_BUCKET,
        pattern=re.compile(r"^Protection from planeswalkers$"),
        priority=_PRIORITY,
        build=_build_kw_protection_planeswalkers,
    ),
    Template(
        tid="B1-kw-reach",
        name="Reach keyword",
        bucket=_BUCKET,
        pattern=re.compile(r"^Reach$"),
        priority=_PRIORITY,
        build=_build_kw_reach,
    ),
    Template(
        tid="B1-kw-trample",
        name="Trample keyword",
        bucket=_BUCKET,
        pattern=re.compile(r"^Trample$"),
        priority=_PRIORITY,
        build=_build_kw_trample,
    ),
    Template(
        tid="B1-kw-vigilance",
        name="Vigilance keyword",
        bucket=_BUCKET,
        pattern=re.compile(r"^Vigilance$"),
        priority=_PRIORITY,
        build=_build_kw_vigilance,
    ),
    Template(
        tid="B1-enchant-creature",
        name="Enchant creature targeting",
        bucket=_BUCKET,
        pattern=re.compile(r"^Enchant creature$"),
        priority=_PRIORITY,
        build=_build_enchant_creature,
    ),
    Template(
        tid="B1-enchant-creature-you",
        name="Enchant creature you control targeting",
        bucket=_BUCKET,
        pattern=re.compile(r"^Enchant creature you control$"),
        priority=_PRIORITY,
        build=_build_enchant_creature_you,
    ),
    Template(
        tid="B1-enchant-permanent",
        name="Enchant permanent targeting",
        bucket=_BUCKET,
        pattern=re.compile(r"^Enchant permanent$"),
        priority=_PRIORITY,
        build=_build_enchant_permanent,
    ),
)

UNCOVERED: tuple[tuple[str, str], ...] = ()
