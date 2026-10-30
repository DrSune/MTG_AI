"""Bucket B11 — general clauses (sets round S-2, KNOWLEDGE /162; B-41).

The buckets before this one are mostly a library of sentence shapes, one template per wording that
M21 or ZNR happened to print. "Enchanted creature gets +N/+N and has flying." and "...and has
trample." are two templates, and a plain "Enchanted creature gets +2/+2." is none; "Destroy target
creature." parses and "Destroy target artifact." does not. First touch on two sets the compiler
had never seen (M20, KHM; /159) parsed 8-11% of unseen sentence shapes.

This bucket parses a clause FAMILY once, from shared parts, and builds exactly the IR the specific
templates build for the same meaning (identity law, DESIGN_ATOM_ONTOLOGY §6):

* a target noun phrase: one card type or two joined by "or", or "nonland permanent"; optional
  "you control" / "an opponent controls" / "you don't control"; optional "with <keyword>" or
  "with power N or less|greater". The pattern IS the grammar (built from the same tables the
  builder reads), so a pattern can never match a phrase its builder cannot encode (B-36).
* the verbs over it: destroy, exile, return to its owner's hand, tap, untap.
* exile it "until this <permanent> leaves the battlefield" (ontology R5-1, CR 610.3).
* "Enchanted|Equipped creature gets +P/+T [and has <keywords>]." statics.
* a bare "Equip {cost}" line (the specific template needs the reminder text, which rares omit).
* "Enchant <type phrase>".
* "Create <number word> P/T <color|colorless> <Subtypes> [artifact] creature token(s)
  [with <keywords>]." (named by its subtypes, CR 111.4, as the existing token carriers are).

Priority 10, below every other bucket: a sentence a specific template matches is decided as
before, and where both match the compiler's ambiguity check would record any difference. The
differential test (test_templates_b11.py) requires there be none over every sentence of M21, ZNR,
M20 and KHM. Encodings follow the existing carriers, including one divergence they already carry
and this bucket does not settle (B-42): MOVE_ZONE names the moved object ``target`` for exile but
``cards`` for return-to-hand. "Its owner's hand" is ``Zone(HAND, OWNER)``, as Unsubstantiate and
Read the Tides encode it; three M21 carriers use ``Zone(HAND, ANY)``, which the executor resolves
to seat 0's hand whoever owns the card (B-43, KNOWLEDGE /162).
"""

from __future__ import annotations

import re
from typing import Final

from MTG_bot.core.ability_tree import (
    Atom,
    AtomArgs,
    ControllerRef,
    DurationUntilLeaves,
    FAnd,
    FAtom,
    FAtomPred,
    Filter,
    FNot,
    FOr,
    Keyword,
    QConst,
    Selector,
    SelectorMode,
    Seq,
    StaticAbility,
    TokenSpec,
    Verb,
    Zone,
    ZoneKind,
)
from MTG_bot.core.compiler.templates import (
    AbilityOutcome,
    EffectOutcome,
    MetaOutcome,
    SentenceOutcome,
    Template,
)
from MTG_bot.core.compiler.templates_b5a import (
    _build_destroy,
    _build_equip,
    _enchant_pt,
    _grant_keyword_atom,
)

_BUCKET: Final[str] = "B11"
_PRIORITY: Final[int] = 10  # below every bucket (lowest today is 50): general = fallback only

# --------------------------------------------------------------------------- grammar tables

_TYPES: Final[dict[str, str]] = {
    "artifact": "Artifact",
    "creature": "Creature",
    "enchantment": "Enchantment",
    "land": "Land",
    "planeswalker": "Planeswalker",
}
#: Keywords a "with <keyword>" phrase or a "has <keywords>" grant may name: the bare keyword
#: abilities (compiler._LINE_KEYWORDS), lower-cased as printed mid-sentence.
_KEYWORDS: Final[dict[str, Keyword]] = {
    "deathtouch": Keyword.DEATHTOUCH,
    "defender": Keyword.DEFENDER,
    "double strike": Keyword.DOUBLE_STRIKE,
    "first strike": Keyword.FIRST_STRIKE,
    "flash": Keyword.FLASH,
    "flying": Keyword.FLYING,
    "haste": Keyword.HASTE,
    "hexproof": Keyword.HEXPROOF,
    "indestructible": Keyword.INDESTRUCTIBLE,
    "lifelink": Keyword.LIFELINK,
    "menace": Keyword.MENACE,
    "prowess": Keyword.PROWESS,
    "reach": Keyword.REACH,
    "trample": Keyword.TRAMPLE,
    "vigilance": Keyword.VIGILANCE,
}


def _alt(words: object) -> str:
    """A regex alternation, longest first so "double strike" wins over a shorter prefix."""
    return "|".join(re.escape(w) for w in sorted(words, key=len, reverse=True))  # type: ignore[arg-type]


_TYPE_ALT: Final[str] = _alt(_TYPES)
_KW_ALT: Final[str] = _alt(_KEYWORDS)
_TYPES_RE: Final[str] = (
    rf"(?:(?P<nonland>nonland permanent)|(?P<t1>{_TYPE_ALT})(?: or (?P<t2>{_TYPE_ALT}))?)"
)
_CTL_RE: Final[str] = r"(?P<ctl>you control|an opponent controls|you don't control)"
_WITH_RE: Final[str] = (
    rf"with (?:(?P<wkw>{_KW_ALT})|power (?P<pw>\d+) or (?P<pdir>less|greater))"
)
#: "target <types> [<controller>] [with ...]" in either suffix order.
_NP_RE: Final[str] = (
    rf"target {_TYPES_RE}"
    rf"(?:(?: {_CTL_RE})?(?: {_WITH_RE})?|(?: {_WITH_RE.replace('?P<', '?P<w2')})(?: "
    rf"{_CTL_RE.replace('?P<', '?P<c2')}))"
)
_KW_LIST_RE: Final[str] = rf"(?P<kws>(?:{_KW_ALT})(?:(?:, and |, | and )(?:{_KW_ALT}))*)"

# --------------------------------------------------------------------------- builders


def _type_filter(name: str) -> Filter:
    return FAtom(pred=FAtomPred.TYPE_EQ, string_value=_TYPES[name])


def _np_filter(m: re.Match[str]) -> Filter:
    """The filter of a matched target noun phrase, conjuncts sorted by construction (R1a)."""
    if m.group("nonland"):
        base: Filter = FAnd(
            children=(
                FAtom(pred=FAtomPred.IS_PERMANENT),
                FNot(inner=FAtom(pred=FAtomPred.TYPE_EQ, string_value="Land")),
            )
        )
    elif m.group("t2"):
        base = FOr(children=(_type_filter(m.group("t1")), _type_filter(m.group("t2"))))
    else:
        base = _type_filter(m.group("t1"))
    conjuncts: list[Filter] = []
    ctl = m.group("ctl") or m.group("c2ctl")
    if ctl == "you control":
        conjuncts.append(FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU))
    elif ctl == "an opponent controls":
        conjuncts.append(FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.OPPONENT))
    elif ctl == "you don't control":
        conjuncts.append(
            FNot(inner=FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU))
        )
    kw = m.group("wkw") or m.group("w2wkw")
    if kw:
        conjuncts.append(FAtom(pred=FAtomPred.KEYWORD_HAS, keyword=_KEYWORDS[kw]))
    power = m.group("pw") or m.group("w2pw")
    if power:
        direction = m.group("pdir") or m.group("w2pdir")
        pred = FAtomPred.POWER_LE if direction == "less" else FAtomPred.POWER_GE
        conjuncts.append(FAtom(pred=pred, count=QConst(int(power))))
    if not conjuncts:
        return base
    return FAnd(children=(base, *conjuncts))


def _bf() -> Zone:
    return Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY)


def _target(m: re.Match[str]) -> Selector:
    return Selector(QConst(1), SelectorMode.TARGET, _np_filter(m), zones=(_bf(),))


def _build_destroy_np(m: re.Match[str]) -> SentenceOutcome:
    return _build_destroy(m, _np_filter(m), _bf())


def _build_exile_np(m: re.Match[str]) -> SentenceOutcome:
    # Mirrors templates_b5a._build_exile_target: moved object under ``target``.
    atom = Atom(
        verb=Verb.MOVE_ZONE,
        args=AtomArgs(
            pairs=(
                ("destination", Zone(ZoneKind.EXILE, ControllerRef.OWNER)),
                ("target", _target(m)),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _build_exile_np_until_leaves(m: re.Match[str]) -> SentenceOutcome:
    """Ontology R5-1 (2026-10-29, CR 610.3): "Exile target <noun phrase> until this <permanent>
    leaves the battlefield." The exile of :func:`_build_exile_np` with
    ``duration=DurationUntilLeaves()``; "this <permanent>" is the ability's source, the referent
    "source". Composed with an enters frame (frames.py) this is Hieromancer's Cage, Banishing Light,
    Journey to Oblivion, Banisher Priest, Stasis Snare and Prison Realm."""
    atom = Atom(
        verb=Verb.MOVE_ZONE,
        args=AtomArgs(
            pairs=(
                ("destination", Zone(ZoneKind.EXILE, ControllerRef.OWNER)),
                ("duration", DurationUntilLeaves()),
                ("target", _target(m)),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _build_bounce_np(m: re.Match[str]) -> SentenceOutcome:
    # Moved object under ``cards`` (the return-to-hand carriers); destination the OWNER's hand
    # (Unsubstantiate, Read the Tides), never Zone(HAND, ANY), which resolves to seat 0 (B-43).
    atom = Atom(
        verb=Verb.MOVE_ZONE,
        args=AtomArgs(
            pairs=(
                ("cards", _target(m)),
                ("destination", Zone(ZoneKind.HAND, ControllerRef.OWNER)),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _tap_like(verb: Verb):
    def build(m: re.Match[str]) -> SentenceOutcome:
        return EffectOutcome(effect=Atom(verb=verb, args=AtomArgs(pairs=(("target", _target(m)),))))

    return build


def _keyword_list(text: str) -> tuple[Keyword, ...]:
    parts = re.split(r", and |, | and ", text)
    return tuple(_KEYWORDS[p] for p in parts)


def _build_attached_pt(m: re.Match[str]) -> SentenceOutcome:
    """Mirrors templates_b5a._build_equipped_pt / _build_enchant_pt_flying: a bare MODIFY_PT, or
    Seq(MODIFY_PT, GRANT_ABILITY...) in printed order. "Equipped creature" and "enchanted
    creature" are the same attachment selector there (``_equipped_creature``)."""
    pt = _enchant_pt(m, (1, 2))
    if not m.group("kws"):
        return AbilityOutcome(ability=StaticAbility(effect=pt))
    grants = tuple(_grant_keyword_atom(k) for k in _keyword_list(m.group("kws")))
    return AbilityOutcome(ability=StaticAbility(effect=Seq(steps=(pt, *grants))))


def _build_enchant_types(m: re.Match[str]) -> SentenceOutcome:
    # Mirrors templates_b1._build_enchant_creature: MetaOutcome(kind="enchant", filter=...).
    if m.group("t2"):
        f: Filter = FOr(children=(_type_filter(m.group("t1")), _type_filter(m.group("t2"))))
    else:
        f = _type_filter(m.group("t1"))
    return MetaOutcome(kind="enchant", filter=f)


_NUMBER_WORDS: Final[dict[str, int]] = {
    "a": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}
_COLOR_LETTER: Final[dict[str, str]] = {
    "white": "W", "blue": "U", "black": "B", "red": "R", "green": "G",
}
_TOKEN_RE: Final[str] = (
    rf"^Create (?P<count>{_alt(_NUMBER_WORDS)}) (?P<p>\d+)/(?P<t>\d+) "
    rf"(?:(?P<color>{_alt(_COLOR_LETTER)})|colorless) "
    r"(?P<subs>[A-Z][a-z]+(?: [A-Z][a-z]+)*) (?P<art>artifact )?creature tokens?"
    rf"(?: with {_KW_LIST_RE})?\.$"
)


def _build_create_tokens(m: re.Match[str]) -> SentenceOutcome:
    """Mirrors the token carriers (b2a ``_soldier_token``, B5b-token-demon): CREATE_TOKEN with
    ``count`` and a TokenSpec named by its subtypes, a one-letter color or None (colorless)."""
    subtypes = tuple(m.group("subs").split(" "))
    artifact = bool(m.group("art"))
    spec = TokenSpec(
        name=" ".join(subtypes),
        type_line=("Artifact Creature — " if artifact else "Creature — ") + " ".join(subtypes),
        types=("Artifact", "Creature") if artifact else ("Creature",),
        subtypes=subtypes,
        power=QConst(int(m.group("p"))),
        toughness=QConst(int(m.group("t"))),
        keywords=_keyword_list(m.group("kws")) if m.group("kws") else (),
        abilities=(),
        color=_COLOR_LETTER[m.group("color")] if m.group("color") else None,
    )
    atom = Atom(
        verb=Verb.CREATE_TOKEN,
        args=AtomArgs(pairs=(("count", QConst(_NUMBER_WORDS[m.group("count")])), ("tokens", spec))),
    )
    return EffectOutcome(effect=atom)


# --------------------------------------------------------------------------- templates


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
    _t("B11-destroy-np", "destroy <target noun phrase>", rf"^Destroy {_NP_RE}\.$",
       _build_destroy_np),
    _t("B11-exile-np", "exile <target noun phrase>", rf"^Exile {_NP_RE}\.$", _build_exile_np),
    _t("B11-exile-np-until-leaves", "exile <target noun phrase> until this <permanent> leaves the battlefield",
       rf"^Exile {_NP_RE} until this (?:creature|artifact|enchantment) leaves the battlefield\.$",
       _build_exile_np_until_leaves),
    _t("B11-bounce-np", "return <target noun phrase> to its owner's hand",
       rf"^Return {_NP_RE} to its owner's hand\.$", _build_bounce_np),
    _t("B11-tap-np", "tap <target noun phrase>", rf"^Tap {_NP_RE}\.$", _tap_like(Verb.TAP)),
    _t("B11-untap-np", "untap <target noun phrase>", rf"^Untap {_NP_RE}\.$",
       _tap_like(Verb.UNTAP)),
    _t("B11-attached-pt", "enchanted/equipped creature gets +P/+T [and has <keywords>]",
       rf"^(?:Enchanted|Equipped) creature gets \+(\d+)/\+(\d+)(?: and has {_KW_LIST_RE})?\.$",
       _build_attached_pt),
    _t("B11-equip-bare", "equip <mana> without reminder text",
       r"^Equip (?P<cost>(?:\{[0-9WUBRGTX]+\})+)$", _build_equip),
    _t("B11-create-tokens", "create <n> P/T <color> <subtypes> creature token(s) [with <kws>]",
       _TOKEN_RE, _build_create_tokens),
    _t("B11-enchant-types", "enchant <type> [or <type>]",
       rf"^Enchant (?P<t1>{_TYPE_ALT})(?: or (?P<t2>{_TYPE_ALT}))?$", _build_enchant_types),
)
