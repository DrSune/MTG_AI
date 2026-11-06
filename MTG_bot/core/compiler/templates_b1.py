"""B1 bucket templates: keyword lines and Enchant restrictions.

Bucket input: ``/tmp/opencode/phase1_buckets/B1.json`` (normalized shape keys → ``[card,
sentence]`` pairs). Templates fullmatch the concrete oracle sentence, never the normalized key.

A keyword line → ``KeywordOutcome`` (``params=()`` when bare; "Hexproof from black" and
"Protection from planeswalkers" carry one ``Filter`` param). "Enchant <object>" →
``MetaOutcome(kind="enchant", filter=...)``.

Every B1 sentence fullmatches at most one template (the patterns are pairwise disjoint); the tests
check it.
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
