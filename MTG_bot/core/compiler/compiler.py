"""Card-assembly compiler: RawCard → CardRecord via template matching.

Consumes the structured ingest (``RawCard``) and a ``TemplateRegistry``
to produce a typed ``CardRecord`` ability tree.  The compiler is the
boundary between English oracle sentences and the closed IR grammar:
every sentence is either matched by a template (→ structured outcome),
detected as a rule reminder, or routed to the explicit unparsed queue.

Entry points: ``compile_card`` (one card) and ``compile_pool`` (a pool);
``parse_mana_cost`` and ``parse_pt`` parse the printed scalars.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, fields, is_dataclass, replace
from typing import Any, cast

from MTG_bot.core.ability_tree import (
    QX,
    Ability,
    ActivatedAbility,
    Atom,
    AtomArgs,
    BackFace,
    CardRecord,
    Choose,
    Conditional,
    ControllerRef,
    Cost,
    CostLoyalty,
    CostManaColor,
    CostManaGeneric,
    CostManaHybrid,
    CostPart,
    DeclareAttackersEvent,
    DeclareBlockersEvent,
    DelayedTrigger,
    DurationUntilEndOfNextTurn,
    EachPlayer,
    Effect,
    FAnd,
    FAtom,
    FAtomPred,
    Filter,
    FNot,
    FOr,
    Keyword,
    KeywordAbility,
    KickerAbility,
    OptionalEffect,
    PhasingEvent,
    QBin,
    QAtLeast,
    QConst,
    Quantity,
    Repeat,
    Selector,
    SelectorMode,
    Seq,
    SpellAbility,
    SpellKind,
    StaticAbility,
    TriggeredAbility,
    Verb,
    Zone,
    ZoneChangeEvent,
    ZoneKind,
    walk,
)
from MTG_bot.core.compiler.ingest import RawCard
from MTG_bot.core.compiler.templates import (
    AbilityOutcome,
    ActivationGateOutcome,
    AdditionalCostOutcome,
    AmbiguityRecord,
    EffectOutcome,
    KickerEffectOutcome,
    KeywordOutcome,
    MetaOutcome,
    RuleReminderOutcome,
    SentenceOutcome,
    TemplateRegistry,
)
from MTG_bot.core.errors import StateCorruptionError
from MTG_bot.core.identity import LegalityFlags

# ---------------------------------------------------------------------------
# Keyword string → Keyword enum mapping.
# "Hexproof from" is HEXPROOF + a Filter param, not a separate keyword.
# ---------------------------------------------------------------------------

_KEYWORD_STRING_TO_ENUM: dict[str, Keyword] = {
    "Battalion": Keyword.BATTALION,
    "Deathtouch": Keyword.DEATHTOUCH,
    "Defender": Keyword.DEFENDER,
    "Double strike": Keyword.DOUBLE_STRIKE,
    "Enchant": Keyword.ENCHANT,
    "Equip": Keyword.EQUIP,
    "Fight": Keyword.FIGHT,
    "First strike": Keyword.FIRST_STRIKE,
    "Flash": Keyword.FLASH,
    "Flying": Keyword.FLYING,
    "Haste": Keyword.HASTE,
    "Hexproof": Keyword.HEXPROOF,
    "Hexproof from": Keyword.HEXPROOF,
    "Indestructible": Keyword.INDESTRUCTIBLE,
    "Lifelink": Keyword.LIFELINK,
    "Menace": Keyword.MENACE,
    "Mill": Keyword.MILL,
    "Protection": Keyword.PROTECTION,
    "Prowess": Keyword.PROWESS,
    "Reach": Keyword.REACH,
    "Scry": Keyword.SCRY,
    "Trample": Keyword.TRAMPLE,
    "Treasure": Keyword.TREASURE,
    "Vigilance": Keyword.VIGILANCE,
}

# Keywords whose _KEYWORD_PARAMS signatures all require ≥1 param —
# cannot be built from a bare identity string alone.
# KNOWN-GAP: the grammar models all four (Verb.SCRY/MILL/BATTALION carry a
#   Quantity, Keyword.PROTECTION a Filter); the gap is upstream of it. The
#   identity keyword pipeline delivers bare strings ("Scry", "Mill") and no
#   oracle-text extraction feeds _KEYWORD_PARAMS for them, so the compiler
#   skips them (reported via CompileResult.known_gaps) unless a template
#   supplies the params. Wiring identity → params is the fix, not new atoms.
_KEYWORDS_BARE_UNBUILDABLE: frozenset[Keyword] = frozenset(
    {Keyword.SCRY, Keyword.MILL, Keyword.BATTALION, Keyword.PROTECTION}
)

# ---------------------------------------------------------------------------
# Continuation prefixes: a sentence starting with one continues the previous
# sentence's effect.
# ---------------------------------------------------------------------------

_CONTINUATION_PREFIXES: tuple[str, ...] = (
    "If you do",
    "If you do so",
    "If target",
    "If it ",
    "If that",
    "If you search your library this way",
    "Then ",
    # "Otherwise" attaches as the else_effect of the previous Conditional
    # (_merge_otherwise); "When you do" attaches inside the previous
    # OptionalEffect whose inner pays a cost (Tolarian Kraken's "you may
    # pay {1}", _merge_do_continuation).
    "Otherwise",
    "When you do",
)

# ---------------------------------------------------------------------------
# Search-shuffle boilerplate (compiler built-in, no template).
#
# "If you search your library this way, shuffle." mandates the
# shuffle ONLY IF the preceding optional search was performed.  No template
# matches the sentence, so the compiler synthesizes a SHUFFLE EffectOutcome
# and the continuation pass injects it INSIDE the previous OptionalEffect's
# sequence — appending it as a sibling optional step would shuffle even when
# no search happened.
# ---------------------------------------------------------------------------

_SEARCH_SHUFFLE_TAIL_RE = re.compile(
    r"^If you search your library this way, shuffle\.$"
)


def _search_shuffle_effect() -> Atom:
    """Canonical mandatory library-shuffle atom for the boilerplate."""
    return Atom(
        verb=Verb.SHUFFLE,
        args=AtomArgs(
            pairs=(("zone", Zone(kind=ZoneKind.LIBRARY, controller=ControllerRef.YOU)),)
        ),
    )


# ---------------------------------------------------------------------------
# Phase-in prevention (compiler built-in, no template).
#
# "Until the end of your next turn, they can't phase in." (Teferi, Timeless
# Voyager [−8]) is the mandatory second sentence of a loyalty
# ability whose first sentence phases out the same creatures.  No template
# matches the bare sentence, so the compiler synthesizes a PREVENT_EFFECT
# EffectOutcome and the continuation pass appends it MANDATORILY (no
# OptionalEffect wrap) to the previous ability's effect.  Wrapping it in
# OptionalEffect would mis-model a guaranteed effect as optional, and
# leaving it standalone would mis-container it as an inherent planeswalker
# effect instead of part of the [−8] activation.
# ---------------------------------------------------------------------------

_PHASE_IN_PREVENT_RE = re.compile(
    r"^Until the end of your next turn, they can't phase in\.$"
)


def _phase_in_prevention_effect() -> Atom:
    """Canonical phase-in prevention atom.

    "They" are the permanents the previous instruction phased out (IS_RESULT,
    the ``result`` register PHASE_OUT writes), and what they can't do is phase
    in (a PhasingEvent: phasing is a status, not a zone change, CR 702.26d),
    until the end of the controller's next turn (DurationUntilEndOfNextTurn).
    """
    they = FAtom(FAtomPred.IS_RESULT)
    return Atom(
        verb=Verb.PREVENT_EFFECT,
        args=AtomArgs(
            pairs=(
                ("condition", they),
                ("event", PhasingEvent(phased_in=True, filter=they)),
                ("duration", DurationUntilEndOfNextTurn()),
            )
        ),
    )


# ---------------------------------------------------------------------------
# Choose-opener boilerplate (compiler built-in, no template).
#
# "Choose one —" is an opener sentence: the option bullets that follow are
# already parsed as sibling EffectOutcomes by the option templates, so only
# the opener itself fails template matching.  This pass folds the opener +
# its option bullets into one Choose node (or a triggered ability carrying
# one).
#
# "Choose one or more —" (Sublime Epiphany, Casualties of War) is
#   Choose(count=QAtLeast(1)): at least one mode, at most every mode once
#   (CR 700.2d).
# KNOWN-GAP: "attacks or blocks" (Elder Gargaroth) is decomposed into two
#   TriggeredAbility nodes (DeclareAttackersEvent + DeclareBlockersEvent)
#   sharing the same Choose effect — the grammar has no composite
#   "attacks or blocks" EventSpec.  A creature cannot attack and block in
#   the same turn, so the decomposition is behaviourally equivalent.
# "Choose two/three —": the same fold, with the Choose ``count`` carrying
#   the modal cardinality.
# ---------------------------------------------------------------------------

_CHOOSE_ONE_RE = re.compile(r"^Choose one —$")
_CHOOSE_TWO_RE = re.compile(r"^Choose two —$")
_CHOOSE_THREE_RE = re.compile(r"^Choose three —$")
_CHOOSE_ONE_OR_MORE_RE = re.compile(r"^Choose one or more —$")
_CHOOSE_ETB_RE = re.compile(r"^When this creature enters, choose one —$")
_CHOOSE_ATTACK_BLOCK_RE = re.compile(
    r"^Whenever this creature attacks or blocks, choose one —$"
)

# Option bullets are printed as "• <effect>" (oracle-text convention).
_OPTION_BULLET_PREFIX = "• "

# Opener kinds.
_CHOOSE_SPELL_ONE = "spell_one"
_CHOOSE_SPELL_TWO = "spell_two"
_CHOOSE_SPELL_THREE = "spell_three"
_CHOOSE_SPELL_ONE_OR_MORE = "spell_one_or_more"
_CHOOSE_ETB_ONE = "etb_one"
_CHOOSE_ATTACK_BLOCK_ONE = "attack_block_one"


@dataclass(frozen=True)
class _ChooseOpenerOutcome:
    """Compiler-internal: a choose-opener sentence folded with its options.

    Not part of the SentenceOutcome union: the continuation pass passes it
    through unchanged (it is neither an EffectOutcome nor an AbilityOutcome,
    so it is never a continuation merge target), and the
    separate-abilities/effects step expands it into its final nodes.
    """

    kind: str
    options: tuple[Effect, ...]


class _OptionConsumed:
    """Sentinel: an option bullet consumed into a choose-opener fold.

    Distinguishes consumed bullets from ``None`` (truly unparsed) so the
    post-fold unparsed rebuild only reports unmatched sentences.
    """

    __slots__ = ()


_OPTION_CONSUMED = _OptionConsumed()


# Outcome slot for the pre-assembly pipeline: a template outcome, an
# unfolded choose-opener, a consumed option bullet, or None (unparsed).
_OutcomeSlot = SentenceOutcome | _ChooseOpenerOutcome | _OptionConsumed | None


# Modal spell openers and their Choose counts.
_CHOOSE_SPELL_COUNTS: dict[str, Quantity] = {
    _CHOOSE_SPELL_ONE: QConst(1),
    _CHOOSE_SPELL_TWO: QConst(2),
    _CHOOSE_SPELL_THREE: QConst(3),
}


def _choose_opener_kind(sentence: str) -> str | None:
    """Classify an anchored choose-opener sentence; None if not one."""
    if _CHOOSE_ONE_RE.match(sentence):
        return _CHOOSE_SPELL_ONE
    if _CHOOSE_TWO_RE.match(sentence):
        return _CHOOSE_SPELL_TWO
    if _CHOOSE_THREE_RE.match(sentence):
        return _CHOOSE_SPELL_THREE
    if _CHOOSE_ONE_OR_MORE_RE.match(sentence):
        return _CHOOSE_SPELL_ONE_OR_MORE
    if _CHOOSE_ETB_RE.match(sentence):
        return _CHOOSE_ETB_ONE
    if _CHOOSE_ATTACK_BLOCK_RE.match(sentence):
        return _CHOOSE_ATTACK_BLOCK_ONE
    return None


def _wrap_choose_openers(
    outcomes: list[_OutcomeSlot],
    sentences: tuple[str, ...],
) -> list[_OutcomeSlot]:
    """Fold choose-opener sentences together with their parsed options.

    For each opener, the following consecutive sentences that are option
    bullets ("• …") parsed as EffectOutcomes are consumed into a
    _ChooseOpenerOutcome at the opener's index; the consumed option indices
    become the ``_OPTION_CONSUMED`` sentinel but KEEP their positions, so
    the one-entry-per-sentence alignment the continuation pass relies on
    (``raw.sentences[i]`` vs ``outcomes[i]``) is preserved and consumed
    bullets are never mistaken for unparsed sentences.  An opener with
    fewer than two parsed options is left untouched (the opener stays
    unparsed rather than being folded into a degenerate single-option
    Choose).
    """
    wrapped: list[_OutcomeSlot] = list(outcomes)
    total = len(sentences)
    for i, sentence in enumerate(sentences):
        kind = _choose_opener_kind(sentence)
        if kind is None:
            continue
        options: list[Effect] = []
        j = i + 1
        while j < total and sentences[j].startswith(_OPTION_BULLET_PREFIX):
            option = outcomes[j]
            if not isinstance(option, EffectOutcome):
                break
            options.append(option.effect)
            j += 1
        if len(options) < 2:
            continue
        wrapped[i] = _ChooseOpenerOutcome(kind=kind, options=tuple(options))
        for k in range(i + 1, j):
            wrapped[k] = _OPTION_CONSUMED
    return wrapped


def _choose_etb_event() -> ZoneChangeEvent:
    """Zone-change event for the "When this creature enters" opener: the
    entering object is the card itself, so the subject is IS_SOURCE."""
    return ZoneChangeEvent(
        from_zone=Zone(ZoneKind.ANY, ControllerRef.ANY),
        to_zone=Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU),
        subject=FAtom(pred=FAtomPred.IS_SOURCE),
    )


def _expand_choose_opener(
    outcome: _ChooseOpenerOutcome,
    abilities: list[Ability],
    effects: list[Effect],
) -> None:
    """Expand a folded choose-opener into its final ability/effect nodes.

    Spell openers emit the bare Choose into ``effects`` (the existing
    assembly folds it into the SpellAbility); the trigger openers emit
    TriggeredAbility nodes into ``abilities``.
    """
    count = (
        QAtLeast(1)  # "one or more": the empty mode set is not a choice (CR 700.2)
        if outcome.kind == _CHOOSE_SPELL_ONE_OR_MORE
        else _CHOOSE_SPELL_COUNTS.get(outcome.kind, QConst(1))
    )
    choose = Choose(count=count, options=outcome.options)
    if (
        outcome.kind in _CHOOSE_SPELL_COUNTS
        or outcome.kind == _CHOOSE_SPELL_ONE_OR_MORE
    ):
        effects.append(choose)
    elif outcome.kind == _CHOOSE_ETB_ONE:
        abilities.append(
            TriggeredAbility(event=_choose_etb_event(), condition=None, effect=choose)
        )
    elif outcome.kind == _CHOOSE_ATTACK_BLOCK_ONE:
        abilities.append(
            TriggeredAbility(
                event=DeclareAttackersEvent(filter=FAtom(pred=FAtomPred.IS_SOURCE)),
                condition=None,
                effect=choose,
            )
        )
        abilities.append(
            TriggeredAbility(
                event=DeclareBlockersEvent(filter=FAtom(pred=FAtomPred.IS_SOURCE)),
                condition=None,
                effect=choose,
            )
        )


# Parenthesised activated-cost sentence (basic lands print their tap
# ability as "({T}: Add {W}.)" — that is an ability, not a reminder).
_ACTIVATED_COST_RE = re.compile(r"^\{[^}]+\}:")

# ---------------------------------------------------------------------------
# Mana cost parsing
# ---------------------------------------------------------------------------

_MANA_TOKEN_RE = re.compile(r"\{([^}]*)\}")
_MANA_COST_FULL_RE = re.compile(r"(?:\{[^}]+\})+")
_COLORS = frozenset({"W", "U", "B", "R", "G"})


def parse_mana_cost(raw: str | None) -> Cost | None:
    """Parse a raw MTGJSON ``manaCost`` string into a typed ``Cost``.

    ``None`` → ``None`` (no mana cost).
    Valid inputs are a non-empty sequence of ``{...}`` tokens with no
    other characters.  Unknown token contents raise
    ``StateCorruptionError``.

    KNOWN-GAP: number-prefixed split hybrids (``{3/W}``) are not
    representable in the Cost grammar (which models two-colour hybrids
    only); they raise with their own message.
    """
    if raw is None:
        return None
    raw = raw.strip()
    if not raw:
        return None
    if not _MANA_COST_FULL_RE.fullmatch(raw):
        raise StateCorruptionError(
            f"parse_mana_cost: not a valid mana-cost string: {raw!r}",
            context={"raw": raw},
        )
    tokens = _MANA_TOKEN_RE.findall(raw)
    parts: list[CostPart] = []
    for tok in tokens:
        if tok == "X":
            parts.append(CostManaGeneric(QX()))
        elif re.fullmatch(r"\d+", tok):
            parts.append(CostManaGeneric(QConst(int(tok))))
        elif tok in _COLORS:
            parts.append(CostManaColor(tok, QConst(1)))
        elif re.fullmatch(r"[WUBRG]/[WUBRG]", tok):
            c1, c2 = tok.split("/")
            if c1 == c2:
                raise StateCorruptionError(
                    f"parse_mana_cost: hybrid colours must differ: {tok!r}",
                    context={"raw": raw, "token": tok},
                )
            parts.append(CostManaHybrid((c1, c2), QConst(1)))
        elif re.fullmatch(r"\d+/[WUBRG]", tok):
            raise StateCorruptionError(
                f"parse_mana_cost: split-cost hybrid {tok!r} is a "
                f"KNOWN-GAP (Cost grammar models two-colour hybrids only)",
                context={"raw": raw, "token": tok},
            )
        else:
            raise StateCorruptionError(
                f"parse_mana_cost: unknown mana token {tok!r}",
                context={"raw": raw, "token": tok},
            )
    return Cost(parts=tuple(parts))


# ---------------------------------------------------------------------------
# P/T parsing
# ---------------------------------------------------------------------------


def parse_pt(raw: str | None) -> QConst | QX | None:
    """Parse a raw power/toughness string into a ``Quantity``.

    ``None`` / ``''`` → ``None`` (absent).
    ``'*'`` → ``None`` (dynamic P/T; the caller must verify that a
    SET_PT/MODIFY_PT ability exists in the compiled text).
    Digit string → ``QConst(n)``.
    """
    if raw is None:
        return None
    raw = raw.strip()
    if raw == "" or raw == "*":
        return None
    if raw.isdigit():
        return QConst(int(raw))
    raise StateCorruptionError(
        f"parse_pt: unexpected value {raw!r}",
        context={"raw": raw},
    )


# ---------------------------------------------------------------------------
# Local bucket classifier for unparsed sentences.
# ---------------------------------------------------------------------------

_KEYWORD_WORDS: frozenset[str] = frozenset(kw for kw in _KEYWORD_STRING_TO_ENUM)
_TRIGGER_PREFIXES: tuple[str, ...] = (
    "When ",
    "Whenever ",
    "At the beginning",
    "At combat",
    "At the start",
)
_ACTIVATED_PREFIXES: tuple[str, ...] = (
    "{T}",
    "{0}",
    "{1}",
    "{2}",
    "{3}",
    "{4}",
    "{5}",
    "{W}",
    "{U}",
    "{B}",
    "{R}",
    "{G}",
    "Sacrifice",
)


def _bucket_hint(sentence: str) -> str:
    """Classify an unparsed sentence into a local bucket label."""
    s = sentence.strip()
    # Full parenthetical: an activated-cost sentence in parentheses is an
    # ability (basic lands), anything else is a rule reminder.
    if s.startswith("(") and s.endswith(")") and len(s) > 2:
        inner = s[1:-1].strip()
        if _ACTIVATED_COST_RE.match(inner):
            return "activated"
        return "rule-reminder"
    for prefix in _ACTIVATED_PREFIXES:
        if s.startswith(prefix):
            return "activated"
    for prefix in _TRIGGER_PREFIXES:
        if s.startswith(prefix):
            return "triggered"
    lowered = s.lower()
    if any(
        lowered.startswith(p)
        for p in (
            "creatures you control",
            "creatures with",
            "other creatures",
            "you control",
            "gives",
            "has ",
            "is a ",
            "each opponent",
        )
    ):
        return "static"
    first_word = s.split(" ", 1)[0].rstrip(".")
    if first_word in _KEYWORD_WORDS:
        return "keyword"
    return "spell-effect"


# ---------------------------------------------------------------------------
# Keyword dedup helpers
# ---------------------------------------------------------------------------


def _build_bare_keywords(raw: RawCard) -> tuple[KeywordAbility, ...]:
    """Build KeywordAbility candidates from raw.keywords where possible.

    KNOWN-GAP: keywords in _KEYWORDS_BARE_UNBUILDABLE cannot be
    constructed without params; "Hexproof from" needs a Filter.
    These are omitted (reported via CompileResult.known_gaps).

    A whole-ability keyword (``_LINE_KEYWORDS``) is built only if the face prints it
    (``_face_prints_keyword``): MTGJSON's list is not the face's own keyword list.
    """
    results: list[KeywordAbility] = []
    for kw_str in raw.keywords:
        kw_enum = _KEYWORD_STRING_TO_ENUM.get(kw_str)
        if kw_enum is None:
            continue
        if kw_str == "Hexproof from":
            continue
        if kw_enum in _KEYWORDS_BARE_UNBUILDABLE:
            continue
        if kw_str in _LINE_KEYWORDS and not _face_prints_keyword(raw, kw_str):
            continue
        results.append(KeywordAbility(keyword=kw_enum, params=()))
    return tuple(results)


def _face_prints_keyword(raw: RawCard, kw_str: str) -> bool:
    """Does this face print the whole-ability keyword ``kw_str`` as its own?

    MTGJSON's ``keywords`` field is not the face's keyword list, in two ways:

    - It lists the bare keyword beside a parameterized variant of it: "Hexproof" next to
      "Hexproof from" for "Hexproof from black" (Garruk's Harbinger). "Hexproof from [quality]"
      is a variant of hexproof that stops only [quality] spells and abilities (CR 702.11d), so a
      bare HEXPROOF beside it would be full hexproof (CR 702.11b): stronger than printed.
    - A modal double-faced card lists both faces' keywords on each face, and a face has only
      its own characteristics (CR 712.8a, 712.8f): Alrund, God of the Cosmos lists the Flying of
      its back face, Hakka.

    A whole-ability keyword is printed as one comma-separated part of a line, trailing reminder
    text dropped (CR 207.2): "Flying", "Reach, hexproof from blue" (Reach only), "First strike
    (This creature deals combat damage first.)". Keywords that only other objects get ("creatures
    you control have flying") are not in MTGJSON's list at all.
    """
    want = kw_str.lower()
    for sentence in raw.sentences:
        match = _TRAILING_REMINDER_RE.match(sentence.strip())
        head = (match.group("head") if match else sentence.strip()).rstrip(".")
        if any(part.strip().lower() == want for part in head.split(",")):
            return True
    return False


# ---------------------------------------------------------------------------
# CompileResult / PoolCompile
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CompileResult:
    """The output of compiling one RawCard.

    ``card``          — the assembled CardRecord.
    ``legality``      — LegalityFlags (format_legal always True here).
    ``unparsed``      — (sentence, bucket_hint) pairs for unmatched text.
    ``ambiguities``   — AmbiguityRecords for multi-match sentences.
    ``rule_reminders``— RuleReminderOutcome instances detected.
    ``known_gaps``    — human-readable KNOWN-GAP notes.
    ``back_face_unparsed`` — (sentence, hint) pairs for unmatched back-face
    sentences; ``unparsed`` holds the front face only.
    ``record``        — the tree sha of an applied card record (card_records.py;
    docs/PLAN_CARD_ONBOARDING.md), None when the tree is the compiler's own.
    """

    card: CardRecord
    legality: LegalityFlags
    unparsed: tuple[tuple[str, str], ...] = ()
    ambiguities: tuple[AmbiguityRecord, ...] = ()
    rule_reminders: tuple[RuleReminderOutcome, ...] = ()
    known_gaps: tuple[str, ...] = ()
    back_face_unparsed: tuple[tuple[str, str], ...] = ()
    record: str | None = None


@dataclass(frozen=True)
class PoolCompile:
    """The output of compiling a full pool.

    ``cards``          — oracle_id → CardRecord (excludes emblems).
    ``emblems``        — oracle_id → emblem CardRecord.
    ``orphan_emblems`` — oracle_ids of emblems whose owner was not found.
    ``results``        — oracle_id → CompileResult for every card.
    ``summary``        — aggregate stats (total, fully, partially, …).
    """

    cards: dict[str, CardRecord]
    emblems: dict[str, CardRecord]
    orphan_emblems: tuple[str, ...]
    results: dict[str, CompileResult]
    summary: dict[str, Any]


# ---------------------------------------------------------------------------
# Internal: sentence outcome processing
# ---------------------------------------------------------------------------

def _is_rule_reminder(sentence: str, raw: RawCard) -> RuleReminderOutcome | None:
    """Detect rule-reminder sentences before template matching."""
    s = sentence.strip()
    # Full parenthetical — except a parenthesised activated-cost sentence
    # (basic lands print their tap ability as "({T}: Add {W}.)"; that is
    # an ability, not a reminder).
    if s.startswith("(") and s.endswith(")") and len(s) > 2:
        inner = s[1:-1].strip()
        if _ACTIVATED_COST_RE.match(inner):
            return None
        return RuleReminderOutcome(reason="full_paren")
    bare = s.rstrip(".")
    for kw_str in raw.keywords:
        if bare == kw_str:
            return RuleReminderOutcome(reason="keyword_reminder")
    return None


#: Keywords a keyword line may list. Each is a whole ability on its own, and
#: ``_build_bare_keywords`` builds it from identity alone, so a line made only of
#: them adds nothing the tree lacks. Left out: keywords that need parameters
#: (Scry, Mill, Protection, Battalion, "Hexproof from") and the keyword actions
#: MTGJSON also lists (Enchant, Equip, Fight, Treasure).
_LINE_KEYWORDS: frozenset[str] = frozenset(
    {
        "Deathtouch",
        "Defender",
        "Double strike",
        "First strike",
        "Flash",
        "Flying",
        "Haste",
        "Hexproof",
        "Indestructible",
        "Lifelink",
        "Menace",
        "Prowess",
        "Reach",
        "Trample",
        "Vigilance",
    }
)
_TRAILING_REMINDER_RE = re.compile(r"^(?P<head>[^()]*?)\s*\([^()]*\)$")


def _is_keyword_line(sentence: str, raw: RawCard) -> bool:
    """A line of bare keywords, comma-separated, with optional trailing reminder text.

    "Flying, haste", "Deathtouch, lifelink", "Flying (This creature can't be blocked
    except by creatures with flying or reach.)". Reminder text has no rules effect
    (CR 207.2). Every listed keyword must be one the card's identity carries and
    ``_build_bare_keywords`` builds, so the abilities are already in the tree and
    nothing is dropped silently; an unbuildable or absent keyword keeps the line
    unparsed.
    """
    match = _TRAILING_REMINDER_RE.match(sentence.strip())
    head = (match.group("head") if match else sentence.strip()).rstrip(".")
    parts = [part.strip() for part in head.split(",")]
    carried = {kw.lower(): kw for kw in raw.keywords}
    return bool(parts) and all(carried.get(part.lower()) in _LINE_KEYWORDS for part in parts)


def _self_named_sentence(sentence: str, raw: RawCard) -> str | None:
    """``sentence`` with the card's own name written "~", or None if it does not name the card.

    Oracle text names an instant or sorcery by its own name ("Lava Axe deals 5 damage to target
    player or planeswalker."), and a legendary card also by the part before its comma. Only the
    B12 templates read the "~" form (compile_card's Step 2c). The name must stand alone:
    "Shockwave" does not name a card called "Shock".
    """
    name = raw.identity.name.split(" // ")[0]
    out = sentence
    for own in sorted({name, name.split(", ")[0]}, key=len, reverse=True):
        out = re.sub(rf"(?<![\w-]){re.escape(own)}(?![\w-])", "~", out)
    return out if out != sentence else None


def _leans_on_previous_sentence(node: object) -> bool:
    """Does an effect act on objects the previous sentence produced: the
    REST complement of a pick, or the ``result`` register (the objects the
    previous sentence acted on)?"""
    if isinstance(node, Selector) and (
        node.mode is SelectorMode.REST or node.referent == "result"
    ):
        return True
    if type(node) is tuple:
        return any(_leans_on_previous_sentence(x) for x in node)
    if is_dataclass(node) and not isinstance(node, type):
        return any(_leans_on_previous_sentence(getattr(node, f.name)) for f in fields(node))
    return False


def _dangles_after_unparsed(outcomes: list, outcome: object, sentence: str) -> bool:
    """Is ``outcome`` a sentence that leans on the one before it
    (:func:`_leans_on_previous_sentence`) while that sentence is unparsed (a
    None slot; reminder text in between is skipped)? Such a sentence has no
    antecedent (CR 608.2c reads the instructions in order, and "the rest" /
    "it" name the previous instruction's objects).

    A continuation sentence (:func:`_is_continuation`: "If you do, ...",
    "Then ...", "Otherwise ...") leans on the previous sentence by its
    wording. Compiled on its own it would be an effect of its own: Keldon
    Raider's "If you do, draw a card." would draw a card on cast (CR 118.12:
    "if you do" asks whether the previous instruction was done)."""
    if not isinstance(outcome, EffectOutcome) or not (
        _leans_on_previous_sentence(outcome.effect) or _is_continuation(sentence)
    ):
        return False
    for prev in reversed(outcomes):
        if isinstance(prev, RuleReminderOutcome):
            continue
        return prev is None
    return False


def _is_continuation(sentence: str) -> bool:
    """Check if a sentence starts with a continuation prefix."""
    s = sentence.strip()
    return any(s.startswith(p) for p in _CONTINUATION_PREFIXES)


# The optionality of a continuation / trailing rules sentence is decided by
# the presence of the word "may" in the sentence itself.  "If you do, <do X>"
# is MANDATORY (the condition already gates it); only "you may …" sentences
# earn an OptionalEffect wrap.
_MAY_RE = re.compile(r"\bmay\b")


def _loyalty_trailing_idx(processed: list[_OutcomeSlot]) -> int | None:
    """Index of the tail-most loyalty ability if it is the LAST meaningful
    processed entry, else None.

    Planeswalker trailing rules text (CR 113.6a — text printed under a
    loyalty bullet belongs to that ability; Basri Ket, Garruk, Savage Herald)
    arrives as a plain, non-continuation sentence.  If the nearest meaningful
    processed entry is an ActivatedAbility whose cost carries a CostLoyalty
    part, that ability is the sentence's owner.

    The empty-cost OPT(CAST) permission row is transparent
    (:func:`_is_cast_permission_row`): Chandra, Heart of Fire's "Add six
    {R}." is printed under the [−9] bullet, after "You may cast them this
    turn.".
    """
    for j in range(len(processed) - 1, -1, -1):
        prev = processed[j]
        if prev is None or isinstance(prev, RuleReminderOutcome):
            continue
        if _is_cast_permission_row(prev):
            continue  # the permission sentence is part of the same bullet
        if (
            isinstance(prev, AbilityOutcome)
            and isinstance(prev.ability, ActivatedAbility)
            and any(isinstance(p, CostLoyalty) for p in prev.ability.cost.parts)
        ):
            return j
        return None
    return None


def _trigger_trailing_idx(processed: list[_OutcomeSlot]) -> int | None:
    """Index of the tail-most TriggeredAbility if it is the LAST meaningful
    processed entry, else None.

    A triggered ability's text continues across sentence boundaries: plain
    sentences printed under a trigger run when the trigger resolves, not
    when the card is cast (Kitesail Freebooter, Garruk's Harbinger, Siege
    Striker).  If the nearest meaningful processed entry is a
    TriggeredAbility, that ability is the sentence's owner.  As in
    :func:`_loyalty_trailing_idx`, only unparsed slots and rule reminders
    are skipped — any other outcome (another ability, a keyword, a gate, a
    meta outcome) is a group boundary and breaks the chain.
    """
    for j in range(len(processed) - 1, -1, -1):
        prev = processed[j]
        if prev is None or isinstance(prev, RuleReminderOutcome):
            continue
        if isinstance(prev, AbilityOutcome) and isinstance(
            prev.ability, TriggeredAbility
        ):
            return j
        return None
    return None


def _is_cast_permission_row(slot: _OutcomeSlot) -> bool:
    """The empty-cost OPT(CAST) PERMISSION idiom (template B4 "cast/play
    them this turn"; Chandra, Heart of Fire's "You may cast them this turn.").

    The template compiles such a sentence into a free-cost ActivatedAbility
    whose whole effect is ``OptionalEffect(Atom(CAST))`` — the permission
    itself, not an action with consequences. It never owns a tail: a rules
    sentence printed under the loyalty bullet it follows stays owned by that
    bullet, so the tail matchers see through the permission row instead of
    capturing the loyalty tail ("Add six {R}.") as the permission's own.

    The CAST pays the card's costs (no ``cost`` role) or waives them (the
    empty Cost, "without paying its mana cost"); either is the same row.
    """
    if not isinstance(slot, AbilityOutcome) or not isinstance(
        slot.ability, ActivatedAbility
    ):
        return False
    ab = slot.ability
    if ab.cost.parts:
        return False
    return (
        isinstance(ab.effect, OptionalEffect)
        and isinstance(ab.effect.inner, Atom)
        and ab.effect.inner.verb is Verb.CAST
        and ab.effect.inner.args.get("cost") in (None, Cost(parts=()))
    )


# A permission that lasts "until end of turn" or "this turn" is the continuous
# effect of the ability whose resolution creates it (CR 611.2a). A static
# ability states no duration (CR 113.3d, 611.3a), so such a sentence is never
# an ability of its own.
_DURATION_PERMISSION_RE = re.compile(r"\b(?:until end of turn|this turn)\b", re.IGNORECASE)


def _is_duration_cast_permission(slot: _OutcomeSlot, sentence: str) -> bool:
    """A permission row (:func:`_is_cast_permission_row`) whose sentence states a
    duration. It belongs to the ability printed above it, but CAST has no
    duration role and the executor no permission lane, so it cannot be
    expressed there yet; as a sibling node it would be a free cast the
    controller could repeat whenever the permanent is on the battlefield
    (Chandra, Flame's Catalyst's [−8] "Until end of turn, you may cast spells
    from your hand without paying their mana costs."). A static permission
    (Conspicuous Snoop's "You may cast Goblin spells from the top of your
    library.") states no duration and waives no cost, so it stays an ability."""
    return _is_cast_permission_row(slot) and bool(_DURATION_PERMISSION_RE.search(sentence))


def casts_itself_from_another_zone(effect: object) -> bool:
    """Is ``effect`` a CAST of the card itself from a zone other than the battlefield
    ("You may cast this card from your graveyard by paying 3 life and discarding a card
    in addition to paying its other costs.", Demonic Embrace), optional or not? As an
    activated ability's effect it can never happen: the ability is activated while the
    card is on the battlefield, so the card is never in that zone. The printed sentence
    is a permission that works from that zone (CR 601.3: a card is cast only where a
    rule or effect allows it), and the IR has no permission lane yet (BACKLOG B-100).
    ``compile_card`` refuses such a row and ``query.inert_row`` never offers one."""
    inner = effect.inner if isinstance(effect, OptionalEffect) else effect
    if not isinstance(inner, Atom) or inner.verb is not Verb.CAST:
        return False
    source = inner.args.get("source")
    return (
        isinstance(source, Selector)
        and source.filter == FAtom(pred=FAtomPred.IS_SOURCE)
        and bool(source.zones)
        and all(zone.kind is not ZoneKind.BATTLEFIELD for zone in source.zones)
    )


def _activation_trailing_idx(processed: list[_OutcomeSlot]) -> int | None:
    """Index of the tail-most plain activated ability if it is the LAST
    meaningful processed entry, else None.

    Sentences printed under an ACTIVATED ability run when that ability
    resolves, not when the card is cast (Tavern Swindler's "If you win the
    flip, you gain 6 life.", Seasoned Hallowblade's "It gains indestructible
    until end of turn.").  Boundaries as in :func:`_trigger_trailing_idx`.
    Loyalty-costed abilities return None (their tails belong to
    :func:`_loyalty_trailing_idx`); the empty-cost OPT(CAST) permission row
    is transparent (:func:`_is_cast_permission_row`).
    """
    for j in range(len(processed) - 1, -1, -1):
        prev = processed[j]
        if prev is None or isinstance(prev, RuleReminderOutcome):
            continue
        if _is_cast_permission_row(prev):
            continue  # permission row: transparent boundary
        if isinstance(prev, AbilityOutcome) and isinstance(
            prev.ability, ActivatedAbility
        ):
            if any(isinstance(p, CostLoyalty) for p in prev.ability.cost.parts):
                return None  # the loyalty chain owns its own tails
            return j
        return None
    return None


def _append_optional_to_seq(effect: Effect, inner: Effect) -> Effect:
    """Append ``OptionalEffect(inner)`` to ``effect``'s step sequence.

    ``inner`` is the *unwrapped* continuation effect; this helper applies the
    single ``OptionalEffect`` wrap.  If ``effect`` is not already a ``Seq``, it
    is wrapped into a two-step ``Seq``.
    """
    if isinstance(effect, Seq):
        return Seq(steps=effect.steps + (OptionalEffect(inner),))
    return Seq(steps=(effect, OptionalEffect(inner)))


def _append_mandatory_to_seq(effect: Effect, inner: Effect) -> Effect:
    """Append ``inner`` MANDATORILY to ``effect``'s step sequence.

    Unlike :func:`_append_optional_to_seq`, no ``OptionalEffect`` wrap is
    applied: the inner effect always fires.  If ``effect`` is not already a
    ``Seq``, it is wrapped into a two-step ``Seq``.
    """
    if isinstance(effect, Seq):
        return Seq(steps=effect.steps + (inner,))
    return Seq(steps=(effect, inner))


#: "Each opponent who can't loses 3 life." (Liliana, Waker of the Dead): a tail about whether the
#: player COULD do the instruction just before it.
_WHO_CANT_TAIL_RE = re.compile(r"^Each (?:opponent|player) who can't\b")


def _insert_before_last_step(effect: Effect, inner: Effect) -> Effect:
    """Put a "who can't" check right before the instruction it is about.

    "Each player discards a card. Each opponent who can't loses 3 life.": the opponents who
    can't are those with no card to discard, so the check reads the hands BEFORE the discard.
    Appended after it, it would also hit an opponent who discarded their last card. Within one
    resolution nothing observable happens between the check and the instruction (no choice, no
    priority; triggers wait), so this order is the printed meaning. It departs from printed
    sentence order: docs/ATOM_DIVERGENCES.md D17.
    """
    if isinstance(effect, Seq):
        return Seq(steps=effect.steps[:-1] + (inner, effect.steps[-1]))
    return Seq(steps=(inner, effect))


def _merge_search_shuffle(prev_effect: Effect, shuffle: Effect) -> Effect:
    """Inject ``shuffle`` into the previous ``OptionalEffect``'s inner steps.

    Unlike the generic continuation append (sibling optional step), the
    search-shuffle boilerplate must run exactly when the optional search ran,
    so the shuffle joins the INNER sequence of the ``OptionalEffect``.
    Defensive fallback: if the previous effect carries no ``OptionalEffect``
    (a template bug), keep the shuffle mandatory and append it after.
    """
    if isinstance(prev_effect, OptionalEffect):
        inner = prev_effect.inner
        if isinstance(inner, Choose):
            # "search your library and/or graveyard" is a Choose over the
            # zone sets (templates.and_or_zone_search). "If you search your
            # library this way, shuffle" joins exactly the options that
            # search a library; the graveyard-only option keeps the
            # library's order.
            return OptionalEffect(
                inner=Choose(
                    count=inner.count,
                    options=tuple(
                        _append_mandatory_to_seq(option, shuffle)
                        if _searches_a_library(option)
                        else option
                        for option in inner.options
                    ),
                )
            )
        if isinstance(inner, Seq):
            return OptionalEffect(inner=Seq(steps=inner.steps + (shuffle,)))
        return OptionalEffect(inner=Seq(steps=(inner, shuffle)))
    return Seq(steps=(prev_effect, shuffle))


def _searches_a_library(effect: object) -> bool:
    """Does an effect hold a SEARCH whose ``cards`` selector looks in a library?"""
    if isinstance(effect, Atom):
        cards = effect.args.get("cards") if effect.verb is Verb.SEARCH else None
        return isinstance(cards, Selector) and any(
            z.kind is ZoneKind.LIBRARY for z in cards.zones
        )
    if isinstance(effect, Seq):
        return any(_searches_a_library(step) for step in effect.steps)
    return False


def _merge_otherwise(prev_effect: Effect, inner: Effect) -> Effect:
    """"Otherwise, …" becomes the ``else_effect`` of the previous sentence's
    ``Conditional`` (Garruk, Savage Herald: "If it's a creature card, put it
    into your hand. Otherwise, put it on the bottom of your library.").

    The Conditional is searched at the top level and as the LAST step of a
    Seq (the "do X. If it's Y, do Z." single-sentence idiom). A
    Conditional that already carries an else_effect is not overwritten.
    When no attachable Conditional is found, fall back to the default
    continuation merge (sibling optional step): "Otherwise" without a
    preceding Conditional must never be a parse failure.
    """

    def _attach(effect: Effect) -> Effect | None:
        if isinstance(effect, Conditional):
            if effect.else_effect is None:
                return replace(effect, else_effect=inner)
            return None
        if isinstance(effect, Seq) and effect.steps:
            new_last = _attach(effect.steps[-1])
            if new_last is not None:
                return Seq(steps=effect.steps[:-1] + (new_last,))
        return None

    attached = _attach(prev_effect)
    if attached is not None:
        return attached
    return _append_optional_to_seq(prev_effect, inner)


def _contains_pay_atom(effect: Effect) -> bool:
    """True if any Atom with ``Verb.PAY`` appears anywhere inside ``effect``.

    Structural test for the "When you do" antecedent: the continuation's
    "do" refers to paying the cost, so the prior effect must actually
    contain the PAY atom.
    """
    if isinstance(effect, Atom):
        return effect.verb is Verb.PAY
    if isinstance(effect, Seq):
        return any(_contains_pay_atom(s) for s in effect.steps)
    if isinstance(effect, Choose):
        return any(_contains_pay_atom(o) for o in effect.options)
    if isinstance(effect, OptionalEffect):
        return _contains_pay_atom(effect.inner)
    if isinstance(effect, Conditional):
        if _contains_pay_atom(effect.then_effect):
            return True
        return effect.else_effect is not None and _contains_pay_atom(effect.else_effect)
    if isinstance(effect, Repeat):
        return _contains_pay_atom(effect.inner)
    if isinstance(effect, EachPlayer):
        return _contains_pay_atom(effect.effect)
    if isinstance(effect, DelayedTrigger):
        return _contains_pay_atom(effect.effect)
    return False


def _merge_do_continuation(prev_effect: Effect, continuation: Effect) -> Effect:
    """"When you do, …" joins the INSIDE of the prior ``OptionalEffect``
    that pays a cost.

    Tolarian Kraken: "When you draw a card, you may pay {1}. When you do,
    …" — the second optional only EXISTS if the payment was made, so the
    parsed continuation (already optional if the text says "you may") is
    injected into the prior OptionalEffect's inner sequence, the shape of
    :func:`_merge_search_shuffle`.  A sibling append here would fabricate
    an independent optional the text never grants.  Any other prior falls
    back to the default continuation merge (sibling optional step), as in
    :func:`_merge_otherwise`.
    """
    if isinstance(prev_effect, OptionalEffect) and _contains_pay_atom(
        prev_effect.inner
    ):
        inner = prev_effect.inner
        if isinstance(inner, Seq):
            return OptionalEffect(inner=Seq(steps=inner.steps + (continuation,)))
        return OptionalEffect(inner=Seq(steps=(inner, continuation)))
    return _append_optional_to_seq(prev_effect, continuation)


def _merge_if_do_continuation(
    prev_effect: Effect, continuation: Effect, sentence: str
) -> Effect:
    """CR 611.1: "you may X. If you do, Y" — Y runs ONLY when the optional X
    actually executed (skip Crypt Lurker's sacrifice and there is no draw).

    The tail joins the sequence as ``Conditional(MAY_DONE, Y)``. A
    "may"-bearing tail ("If you do, you may Z") keeps its own inner optional
    INSIDE the gate.

    A MANDATORY antecedent is gated the same way. CR 118.12 reads "[Do
    something]. If you do, [effect]" exactly as it reads "You may [do
    something]. If you do": did the player do it. So it is one meaning with
    one encoding, and the executor records whether the step before the gate
    actually happened (Archfiend's Vessel's "exile it. If you do, create a
    Demon" makes no Demon when the Vessel left the battlefield first).
    """
    inner = continuation
    if _MAY_RE.search(sentence) and not isinstance(inner, OptionalEffect):
        inner = OptionalEffect(inner=inner)
    gated = Conditional(pred=FAtom(pred=FAtomPred.MAY_DONE), then_effect=inner)
    return _append_mandatory_to_seq(prev_effect, gated)


def _fold_meta_filter(effect: Effect, meta_filter: Filter) -> Effect:
    """Conjoin meta_filter onto every TARGET-mode Selector in effect.

    Recursively transforms the Effect grammar, rebuilding each node with
    TARGET-mode Selectors' filters AND-conjoined with ``meta_filter``.
    """

    def _transform(e: Effect) -> Effect:
        if isinstance(e, Seq):
            return Seq(steps=tuple(_transform(s) for s in e.steps))
        if isinstance(e, Choose):
            return Choose(
                count=e.count,
                options=tuple(_transform(o) for o in e.options),
            )
        if isinstance(e, OptionalEffect):
            return OptionalEffect(_transform(e.inner))
        if isinstance(e, Conditional):
            then_e = _transform(e.then_effect)
            else_e = _transform(e.else_effect) if e.else_effect is not None else None
            return Conditional(pred=e.pred, then_effect=then_e, else_effect=else_e)
        if isinstance(e, Repeat):
            return Repeat(count=e.count, inner=_transform(e.inner))
        if isinstance(e, Atom):
            new_pairs: list[tuple[str, object]] = []
            modified = False
            for role, value in e.args.pairs:
                if isinstance(value, Selector) and value.mode is SelectorMode.TARGET:
                    new_filter = FAnd(children=(value.filter, meta_filter))
                    modified = True
                    # The rebuild keeps the full zone set and the referent
                    # (pinned by test_ontology_r0).
                    new_pairs.append(
                        (
                            role,
                            Selector(
                                value.count,
                                value.mode,
                                new_filter,
                                zones=value.zones,
                                referent=value.referent,
                            ),
                        )
                    )
                else:
                    new_pairs.append((role, value))
            if modified:
                return Atom(verb=e.verb, args=AtomArgs(pairs=tuple(new_pairs)))
            return e
        return e

    return _transform(effect)


# ---------------------------------------------------------------------------
# compile_card
# ---------------------------------------------------------------------------


def _spell_kind_from_types(types: tuple[str, ...], is_creature: bool) -> SpellKind:
    """Derive the SpellAbility kind for a castable card from its type line,
    in compile_card's assembly order: creature, planeswalker, then Instant,
    Sorcery, Enchantment, Artifact, fallback Sorcery."""
    if is_creature:
        return SpellKind.CREATURE
    if "Planeswalker" in types:
        return SpellKind.PLANESWALKER
    if "Instant" in types:
        return SpellKind.INSTANT
    if "Sorcery" in types:
        return SpellKind.SORCERY
    if "Enchantment" in types:
        return SpellKind.ENCHANTMENT
    if "Artifact" in types:
        return SpellKind.ARTIFACT
    return SpellKind.SORCERY


def _is_result_anaphoric_cast_permission(ability: Ability) -> bool:
    """Furious Rise: an EMPTY-cost ActivatedAbility whose effect is an
    OptionalEffect-wrapped CAST over a ``referent="result"`` selector —
    ``_build_play_that_card_until``'s shape for "You may play that card
    until you exile another card with this enchantment."  The printed card
    carries NO activated ability: the play window is a permission created
    by the end-step trigger's exile, and the engine has no play-permission
    lane (the node would be a phantom whose activation finds no register).
    The template stays MATCHED (the sentence is parsed and reported); the
    NODE is suppressed at assembly with a KNOWN-GAP note.  The shape is
    narrow by design: other empty-cost activations carry other verbs, and
    every other may-cast permission names its cost or its object (no
    result referent)."""
    if not isinstance(ability, ActivatedAbility) or ability.cost.parts:
        return False
    inner = ability.effect.inner if isinstance(ability.effect, OptionalEffect) else None
    if not isinstance(inner, Atom) or inner.verb is not Verb.CAST:
        return False
    src = dict(inner.args.pairs).get("source")
    return isinstance(src, Selector) and src.referent == "result"


def _one_of_search_picks(node: object) -> object:
    """Recompile the search-pick CHOOSE selector to the ONE_OF asking channel.

    A SEARCH atom whose ``cards`` role is the up-to-one pick
    (``Selector(QConst(1), CHOOSE, …)``) would resolve the *which card did
    you find* decision silently, through the deterministic first-of-sort
    stand-in (selectors.py). ONE_OF asks with the Handle-sorted candidate
    list; a single candidate auto-fills, and exhaustion stays loud.
    QConst(2) picks (Cultivate, Alpine Houndmaster) and QUnbounded
    whole-zone finds are NOT rewritten: ONE_OF is exactly-one, so a
    multi-pick ask is a known grammar gap, not something this pass extends.
    """
    if type(node) is tuple:
        rebuilt = tuple(_one_of_search_picks(v) for v in node)
        return (
            rebuilt
            if any(a is not b for a, b in zip(rebuilt, node, strict=True))
            else node
        )
    if not (is_dataclass(node) and not isinstance(node, type)):
        return node
    if isinstance(node, Atom) and node.verb is Verb.SEARCH:
        flipped = False
        pairs: list[tuple[str, object]] = []
        for key, value in node.args.pairs:
            if (
                key == "cards"
                and isinstance(value, Selector)
                and value.mode is SelectorMode.CHOOSE
                and value.count == QConst(1)
            ):
                value = replace(value, mode=SelectorMode.ONE_OF)
                flipped = True
            pairs.append((key, value))
        if flipped:
            node = replace(node, args=replace(node.args, pairs=tuple(pairs)))
    updates = {
        f.name: _one_of_search_picks(getattr(node, f.name)) for f in fields(node)
    }
    if any(updates[f.name] is not getattr(node, f.name) for f in fields(node)):
        return replace(node, **updates)
    return node


def _flip_search_picks_in(ability: Ability) -> Ability:
    """Typed wrapper: the rewrite rebuilds nodes in place and never
    changes a node's type, so the Ability in is an Ability out."""
    return cast(Ability, _one_of_search_picks(ability))


# The STRUCTURAL PROMOTION RULE (docs/T4_PICK_ENUMERATION.md §2'): a
# QConst(1), referent-less entity CHOOSE selector that sits outside a cost
# and is not an IS_SOURCE self-designation IS a real controller decision and
# is promoted AUTOMATICALLY onto the asking ONE_OF channel. New sets need no
# registration; test_promotion_predicate.py pins the per-class census of the
# rule. The two frozensets below are the only overrides.
PICK_ASK_FORCE_ASK: frozenset[tuple[str, str]] = frozenset()
#   (card name, effect verb) TRIPWIRE rows — the hatch has no promotion
#   lane and every hit is LOUD by design: a hit on a COST or IS_SOURCE
#   self-designation is a stale override and raises StateCorruptionError; a
#   hit on any other predicate-declined near-miss raises
#   NotImplementedError — a referent-bound surface CANNOT ride ONE_OF at
#   all, and surfaces whose rules-decider is not the effect controller are
#   gap-ledger L-27 (the ask channel is controller-seat only). Rows on
#   surfaces the structural predicate already lifts are no-ops (the
#   structural branch fires first).
PICK_ASK_FORCE_SILENT: frozenset[tuple[str, str]] = frozenset(
    {
        # L-27 — no opponent/player-seat decision channel: the decider is
        # NOT the effect controller (CR 701.8a "that player chooses";
        # Goremand/Run Afoul "of their choice"), so the controller-primed
        # ONE_OF lane cannot answer these honestly.
        ("Goremand", "SACRIFICE"),  # "each opponent sacrifices"
        ("Run Afoul", "SACRIFICE"),  # "of their choice with flying"
        ("Liliana's Steward", "MOVE_ZONE"),  # "target opponent discards"
        ("Liliana, Waker of the Dead", "MOVE_ZONE"),  # "+1 each player discards"
        ("Keral Keep Disciples", "DEAL_DAMAGE"),
        # ^ forced-direction node: "1 damage to each opponent" is NO
        # decision at all — the singleton PLAYER pick auto-fills, so an
        # ask would be a phantom.
        # L-28 — card-NAME value menu absent (protection never reads the
        # selector; _v_grant resolves ability/duration roles only).
        ("Runed Halo", "GRANT_ABILITY"),
        # L-29 — top-of-library POSITION semantics, not an entity menu:
        # _v_move_zone pop_order=TOP never resolves the selector, _v_cast
        # designates via the look-at binding; an ask would offer a
        # library-wide menu the rules never grant.
        ("Furious Rise", "MOVE_ZONE"),
        ("Radha, Heart of Keld", "CAST"),
    }
)


def _filter_carries_is_source(filter_: Filter | None) -> bool:
    """Mirror of executor.selectors._filter_is_self_referential (kept local:
    the compiler layer must not import the executor). An IS_SOURCE atom
    anywhere in the tree means the selector denotes the ability's OWN
    source (CR 602.2c self-designation) — never a player decision, and the
    binding.py exemption for it is CHOOSE-mode-gated, so lifting one
    silently mis-resolves. Loud raise guards the allowlist instead."""
    if isinstance(filter_, FAtom):
        return filter_.pred is FAtomPred.IS_SOURCE
    if isinstance(filter_, (FAnd, FOr)):
        return any(_filter_carries_is_source(c) for c in filter_.children)
    if isinstance(filter_, FNot):
        return _filter_carries_is_source(filter_.inner)
    return False


def _is_liftable_pick(node: Selector, in_cost: bool) -> bool:
    """THE structural promotion predicate (census and per-class contract:
    test_promotion_predicate.py). Three orthogonal axes: {shape} a
    QConst(1) entity CHOOSE with no anaphoric referent (a referent-bound
    pick already follows a binding); {context} not a cost victim (the
    sacrifice lane already asks); {denotation} not an IS_SOURCE
    self-designation (CR 602.2c — not a decision, and the binding
    exemption is CHOOSE-mode-gated, so flipping one silently mis-resolves)."""
    return (
        node.mode is SelectorMode.CHOOSE
        and node.count == QConst(1)
        and node.referent is None
        and not in_cost
        and not _filter_carries_is_source(node.filter)
    )


def _pick_ask_promotions(
    node: object, name: str, in_cost: bool, verb: str | None
) -> object:
    """Entity-shape twin of _one_of_search_picks, driven by the structural
    predicate _is_liftable_pick. A matching surface gets the ONE_OF asking
    channel: Handle-sorted population, singleton auto-fill, exhaustion
    loud. PICK_ASK_FORCE_SILENT exempts surfaces whose ask has no
    answerable lane (gap ledger L-27..L-29); PICK_ASK_FORCE_ASK is a loud
    tripwire only — a hit on the cost/self-designation line raises
    StateCorruptionError, a hit on any other predicate-declined shape
    raises NotImplementedError (L-27 provider-seat routing absent)."""
    if type(node) is tuple:
        rebuilt = tuple(_pick_ask_promotions(v, name, in_cost, verb) for v in node)
        return (
            rebuilt
            if any(a is not b for a, b in zip(rebuilt, node, strict=True))
            else node
        )
    if not (is_dataclass(node) and not isinstance(node, type)):
        return node
    if type(node).__name__.startswith("Cost") and type(node).__name__ != "CostLoyalty":
        in_cost = True
    if isinstance(node, Atom):
        verb = node.verb.name
    if isinstance(node, Selector):
        key = (name, verb or "")
        if key in PICK_ASK_FORCE_SILENT:
            return node
        if _is_liftable_pick(node, in_cost):
            return replace(node, mode=SelectorMode.ONE_OF)
        # FORCE_ASK tripwire: gated on CHOOSE, not on the predicate's own
        # shape, so a row for a referent or count near-miss is seen too.
        if node.mode is SelectorMode.CHOOSE and key in PICK_ASK_FORCE_ASK:
            if in_cost or _filter_carries_is_source(node.filter):
                raise StateCorruptionError(
                    f"compile_card({name}): PICK_ASK_FORCE_ASK verb {verb} hit a "
                    "cost/self-designation selector — override stale"
                )
            raise NotImplementedError(
                f"compile_card({name}): PICK_ASK_FORCE_ASK row ({name}, {verb}) "
                "hit a predicate-declined near-miss selector and the force-ask "
                "hatch has no honest lane: referent surfaces cannot ride ONE_OF "
                "(Selector convention C2) and non-controller deciders are "
                "gap-ledger L-27 (controller-seat-only ask, provider-seat "
                "routing absent) — a forced ask there is a §10 phantom. Drop "
                "the row or land the routing first."
            )
        return node
    updates = {
        f.name: _pick_ask_promotions(getattr(node, f.name), name, in_cost, verb)
        for f in fields(node)
    }
    if any(updates[f.name] is not getattr(node, f.name) for f in fields(node)):
        return replace(node, **updates)
    return node


def _promote_liftable_picks(abilities: list[Ability], name: str) -> list[Ability]:
    """Run the structural promotion pass over each ability; type-pinned like
    _flip_search_picks_in."""
    return [cast(Ability, _pick_ask_promotions(ab, name, False, None)) for ab in abilities]


def _kicker_slot_effect(slot: object) -> Effect | None:
    """The mergeable effect of a processed slot for the kicker fold
    (mirrors the continuation search's mergeability rule)."""
    if isinstance(slot, EffectOutcome):
        return slot.effect
    if isinstance(slot, AbilityOutcome):
        ab = slot.ability
        if isinstance(
            ab, (StaticAbility, ActivatedAbility, TriggeredAbility, SpellAbility)
        ):
            return ab.effect
    return None


def _kicker_slot_with_effect(slot: _OutcomeSlot, new_effect: Effect) -> _OutcomeSlot:
    """Rebuild a processed slot carrying ``new_effect`` (field-preserving,
    mirrors the continuation merge rebuilds)."""
    if isinstance(slot, EffectOutcome):
        return EffectOutcome(effect=new_effect)
    assert isinstance(slot, AbilityOutcome)
    ab = slot.ability
    if isinstance(ab, StaticAbility):
        return AbilityOutcome(ability=StaticAbility(effect=new_effect))
    if isinstance(ab, ActivatedAbility):
        return AbilityOutcome(
            ability=ActivatedAbility(
                cost=ab.cost,
                effect=new_effect,
                condition=ab.condition,
                timing=ab.timing,
            )
        )
    if isinstance(ab, SpellAbility):
        return AbilityOutcome(
            ability=SpellAbility(
                kind=ab.kind,
                effect=new_effect,
                additional_costs=ab.additional_costs,
            )
        )
    assert isinstance(ab, TriggeredAbility)
    return AbilityOutcome(
        ability=TriggeredAbility(
            event=ab.event, condition=ab.condition, effect=new_effect
        )
    )


def _cost_has_x_quantity(cost: Cost) -> bool:
    """Does this Cost price anything with X (a QX amount, or a QBin tree
    carrying one)? Mirrors the executor's legality._cost_has_x — duplicated,
    not imported, because the compiler must not depend on the executor
    package."""

    def has_x(q: object) -> bool:
        if isinstance(q, QX):
            return True
        if isinstance(q, QBin):
            return has_x(q.left) or has_x(q.right)
        return False

    return any(
        isinstance(p, (CostManaColor, CostManaGeneric, CostManaHybrid))
        and has_x(p.amount)
        for p in cost.parts
    )


def _as_single_faced(raw: RawCard) -> RawCard:
    """Synthetic single-faced RawCard carrying ONLY the folded back face's
    printed data. Same oracle id (the face IS this card's second face), the
    face's own name, and ``back_face=None`` so the recursive compile_card
    pass terminates immediately. Pool-level flags are cleared: a face is
    never a token/emblem in its own right."""
    face = raw.back_face
    assert face is not None  # caller's guard; keeps the return typed
    return replace(
        raw,
        identity=replace(raw.identity, name=face.name),
        type_line=face.type_line,
        types=face.types,
        subtypes=face.subtypes,
        supertypes=face.supertypes,
        colors=face.colors,
        color_identity=face.color_identity,
        mana_cost_raw=face.mana_cost_raw,
        mana_value=face.mana_value,
        power_raw=face.power_raw,
        toughness_raw=face.toughness_raw,
        loyalty_raw=face.loyalty_raw,
        keywords=face.keywords,
        sentences=face.sentences,
        layout="normal",
        is_token=False,
        is_emblem=False,
        token_name_refs=(),
        related_names=(),
        back_face=None,
    )


def _star_pt_gaps(raw: RawCard, card: CardRecord) -> list[str]:
    """Known-gap notes for a printed '*' P/T that no SET_PT/MODIFY_PT atom covers.

    Shared by :func:`compile_card` and the card-record path (card_records.py), so a
    mapped tree is held to the same check as a compiled one."""
    gaps: list[str] = []
    # If power or toughness was '*' (→ None from parse_pt), check that a
    # SET_PT or MODIFY_PT verb exists somewhere in the compiled tree.
    # KNOWN-GAP: when no template produced such an atom the card's P/T is
    #   dynamic but uncovered — a template-coverage gap, not data corruption
    #   (the data itself is sound). Report it; power/toughness stay None
    #   (= "resolve at runtime").
    needs_set_pt = (raw.power_raw is not None and raw.power_raw.strip() == "*") or (
        raw.toughness_raw is not None and raw.toughness_raw.strip() == "*"
    )
    if needs_set_pt:
        has_set_pt = False
        for node in walk(card, skip=BackFace):
            if isinstance(node, Atom) and node.verb in (
                Verb.SET_PT,
                Verb.MODIFY_PT,
            ):
                has_set_pt = True
                break
        if not has_set_pt:
            star_fields = []
            if raw.power_raw is not None and raw.power_raw.strip() == "*":
                star_fields.append("power")
            if raw.toughness_raw is not None and raw.toughness_raw.strip() == "*":
                star_fields.append("toughness")
            gaps.append(
                f"star P/T: {'/'.join(star_fields)} is '*' but no SET_PT/MODIFY_PT "
                f"ability found in compiled text (template coverage gap)"
            )
    return gaps


def _engine_supported(card: CardRecord, supported_verbs: set[Verb] | None) -> bool:
    """The engine-support verdict for a built card (``supported_verbs=None`` is the
    ungated pass: always True). Shared with the card-record path."""
    engine_supported = True
    if supported_verbs is not None:
        # The BackFace subtree is EXCLUDED: the engine never plays a face,
        # so a face-only verb must never flip a front-face-supported card's
        # verdict (nor drop it from engine supply).
        for node in walk(card, skip=BackFace):
            if isinstance(node, Atom) and node.verb not in supported_verbs:
                engine_supported = False
                break
        # SHAPE gates, for what the verb check cannot see: an X-kicker ({X}
        # in the optional cost) is unsupported, since no producer wires the
        # kick choice to an X declaration.
        if engine_supported:
            for node in walk(card, skip=BackFace):
                if isinstance(node, KickerAbility) and _cost_has_x_quantity(node.cost):
                    engine_supported = False
                    break
                # A loyalty [−X] (Ugin) is supported: legality.activate
                # announces X before paying (CR 602.2b -> 601.2b, 107.3a),
                # capped by the loyalty counters (CR 606.6). The lane
                # handles a bare X only, so any other Quantity delta stays
                # unsupported.
                if (
                    isinstance(node, CostLoyalty)
                    and not isinstance(node.delta, int)
                    and not isinstance(node.delta, QX)
                ):
                    engine_supported = False
                    break
    return engine_supported


def compile_card(
    raw: RawCard,
    registry: TemplateRegistry,
    supported_verbs: set[Verb] | None = None,
) -> CompileResult:
    """Compile one RawCard into a CardRecord via template matching.

    Steps:
    1. Parse mana cost, P/T, loyalty from raw fields.
    2. Process each sentence: rule reminder → template match → unparsed.
    3. Handle continuation prefixes (OptionalEffect append).
    4. Dedup keywords (identity + template outcomes).
    5. Assemble abilities by card type.
    6. Build CardRecord; report star-P/T coverage gaps; determine
       engine_supported.
    """
    # -- Parse scalar fields ------------------------------------------------
    mana_cost = parse_mana_cost(raw.mana_cost_raw)
    power = parse_pt(raw.power_raw)
    toughness = parse_pt(raw.toughness_raw)
    loyalty = int(raw.loyalty_raw) if raw.loyalty_raw else None

    # -- Process sentences --------------------------------------------------
    unparsed: list[tuple[str, str]] = []
    ambiguities: list[AmbiguityRecord] = []
    rule_reminders: list[RuleReminderOutcome] = []
    known_gaps: list[str] = []

    # Per-sentence outcomes, in order.
    # Each entry is a SentenceOutcome, an unfolded choose-opener, or None
    # (unparsed).
    outcomes: list[_OutcomeSlot] = []

    for sentence in raw.sentences:
        # Step 1: rule reminder check
        rr = _is_rule_reminder(sentence, raw)
        if rr is not None:
            rule_reminders.append(rr)
            outcomes.append(rr)
            continue

        # Step 1b: search-shuffle boilerplate (compiler built-in — no
        # template; the continuation pass injects the shuffle inside the
        # previous OptionalEffect).
        if _SEARCH_SHUFFLE_TAIL_RE.match(sentence):
            outcomes.append(EffectOutcome(effect=_search_shuffle_effect()))
            continue

        # Step 1c: phase-in prevention boilerplate (compiler built-in — no
        # template; the continuation pass appends it MANDATORILY to the
        # previous ability's effect Seq).
        if _PHASE_IN_PREVENT_RE.match(sentence):
            outcomes.append(EffectOutcome(effect=_phase_in_prevention_effect()))
            continue

        # Step 2: template match
        matches = registry.match(sentence)
        best_match = matches[0] if matches else None
        # Step 2a: a keyword line no template matched (fallback only, so a
        # sentence a template matches is never re-read here).
        if best_match is None and _is_keyword_line(sentence, raw):
            rr = RuleReminderOutcome(reason="keyword_line")
            rule_reminders.append(rr)
            outcomes.append(rr)
            continue
        # Step 2c: the card's own name as a clause's subject (fallback only, B12). With the name
        # written "~", only the self-named bucket may match, so no other template is re-read.
        if best_match is None:
            self_named = _self_named_sentence(sentence, raw)
            if self_named is not None:
                matches = tuple(m for m in registry.match(self_named)
                                if m.template.bucket == "B12")
                best_match = matches[0] if matches else None
        # Step 2d: a trigger or cost frame around a clause that parses on its own (fallback only,
        # B13). Imported here: the frame helpers live in template modules, one of which imports
        # this module.
        if best_match is None:
            from MTG_bot.core.compiler.frames import compose as _compose_frame

            matches = _compose_frame(sentence, registry)
            best_match = matches[0] if matches else None
        if best_match is None:
            hint = _bucket_hint(sentence)
            unparsed.append((sentence, hint))
            outcomes.append(None)
            continue

        # Ambiguity detection
        if len(matches) > 1:
            tids = tuple(m.template.tid for m in matches)
            distinct = (
                len({type(m.outcome).__name__ for m in matches}) > 1
                or len({repr(m.outcome) for m in matches}) > 1
            )
            if distinct:
                ambiguities.append(
                    AmbiguityRecord(
                        sentence=sentence,
                        tids=tids,
                        note=f"{len(matches)} templates matched; highest priority used",
                    )
                )

        # A sentence that acts on what the sentence before it produced ("Put
        # the rest on the bottom of your library", "That player discards
        # that card", "It gains indestructible") has no antecedent when that
        # sentence did not parse. Compiled alone it would be an unprinted
        # effect of its own, so it is unparsed too (flag, don't degrade).
        if _dangles_after_unparsed(outcomes, best_match.outcome, sentence):
            outcomes.append(None)
            continue

        # Use highest-priority match (first in ordered tuple)
        outcomes.append(best_match.outcome)

    # Step 2b: choose-opener folding (compiler built-in — no template).
    # Runs before the continuation pass so consumed option bullets are
    # already sentinel slots (and thus never continuation merge targets,
    # and never mistaken for unparsed sentences).  Index alignment with
    # raw.sentences is preserved, so the continuation pass is unaffected.
    outcomes = _wrap_choose_openers(outcomes, raw.sentences)
    # Rebuild unparsed from the post-fold outcome list (one entry per
    # None slot, in sentence order) — folded openers drop out.
    unparsed = [
        (sentence, _bucket_hint(sentence))
        for sentence, outcome in zip(raw.sentences, outcomes)
        if outcome is None
    ]

    # -- Handle continuation prefixes ---------------------------------------
    # A continuation sentence's effect is merged into the previous
    # sentence's effect (the merge choice is below).  We search backwards
    # in the *processed* list (not the raw outcomes list) so indices stay
    # stable even when earlier continuations consumed entries.
    processed: list[_OutcomeSlot] = []
    # Parallel raw-sentence index for each processed entry (consumed
    # continuations are not appended), so post-assembly mechanisms can
    # anchor to the sentence that produced each ability.
    processed_sentence_idx: list[int] = []
    for i, outcome in enumerate(outcomes):
        # ZNR kicker tail ("If this spell/it was kicked, [instead] X"):
        # fold the WAS_KICKED-gated arm onto the previous effect-bearing
        # slot — additive append, or "instead" replacement (the arm wins,
        # the base moves to the Conditional's else_effect). The same fold
        # takes any other printed condition (outcome.pred): "You gain 4
        # life. If a creature died this turn, you gain 8 life instead." is
        # Conditional(DIED_THIS_TURN, 8, else=4) (CR 608.2c), not a
        # turn-long replacement.
        if isinstance(outcome, KickerEffectOutcome):
            arm_pred = (
                outcome.pred
                if outcome.pred is not None
                else FAtom(pred=FAtomPred.WAS_KICKED)
            )
            j: int | None = None
            base: Effect | None = None
            saw_unparsed_base = False
            for jj in range(len(processed) - 1, -1, -1):
                prev = processed[jj]
                if prev is None:
                    # An unmatched sentence: the base clause IS there in
                    # the text, it just compiled to residue.  That failed
                    # clause IS the base — searching past it would attach
                    # the arm to an UNRELATED earlier effect.
                    saw_unparsed_base = True
                    break
                if isinstance(prev, RuleReminderOutcome):
                    continue
                prev_effect = _kicker_slot_effect(prev)
                if prev_effect is not None:
                    j = jj
                    base = prev_effect
                    break
            if j is None or base is None:
                if outcome.replaces and not saw_unparsed_base:
                    # Corrupt fold: an "instead" arm as the card's first
                    # effect content — no base clause exists in the text
                    # at all; never silently drop the clause.
                    raise StateCorruptionError(
                        "compile_card: kicker or conditional 'instead' arm has "
                        "no preceding base effect to replace it",
                        context={"sentence": raw.sentences[i]},
                    )
                if outcome.replaces:
                    # A REPLACEMENT arm whose base compiled to residue must
                    # NOT fold standalone — Conditional(WAS_KICKED,
                    # then=arm) with no else encodes "un-kicked → no
                    # effect", which is rules-wrong (un-kicked Roil Eruption
                    # still deals 3 damage).  Leave the arm in the register
                    # as residue too: both clauses are uncovered.
                    unparsed.append((raw.sentences[i], _bucket_hint(raw.sentences[i])))
                    continue
                # No mergeable slot. Additive arms fold standalone (the
                # SpellAbility assembly Seq-fold yields the same tree).
                processed.append(
                    EffectOutcome(
                        effect=Conditional(
                            pred=arm_pred,
                            then_effect=outcome.effect,
                        )
                    )
                )
                processed_sentence_idx.append(i)
                continue
            merged = (
                Conditional(
                    pred=arm_pred,
                    then_effect=outcome.effect,
                    else_effect=base,
                )
                if outcome.replaces
                else _append_mandatory_to_seq(
                    base,
                    Conditional(
                        pred=arm_pred,
                        then_effect=outcome.effect,
                    ),
                )
            )
            processed[j] = _kicker_slot_with_effect(processed[j], merged)
            # The kicker tail is consumed — not appended.
            continue
        # Non-effect entries pass through unchanged.
        if outcome is None or not isinstance(outcome, EffectOutcome):
            processed.append(outcome)
            processed_sentence_idx.append(i)
            continue

        sentence = raw.sentences[i]
        if not _is_continuation(sentence) and not _PHASE_IN_PREVENT_RE.match(sentence):
            # Plain text right after a loyalty bullet is that ability's
            # trailing rules text, not a new card-level spell ability.  Merge
            # it into the loyalty ability's effect (mandatory unless the
            # sentence itself says "may").
            # A sentence starting with "[" is another ability bullet —
            # never a trailing sentence, even if it parsed to an effect.
            loy_idx = (
                None
                if sentence.lstrip().startswith("[")
                else _loyalty_trailing_idx(processed)
            )
            if loy_idx is not None:
                slot = processed[loy_idx]
                ab = slot.ability if isinstance(slot, AbilityOutcome) else None
                if isinstance(ab, ActivatedAbility):
                    merge = (
                        _insert_before_last_step
                        if _WHO_CANT_TAIL_RE.match(sentence.strip())
                        else _append_optional_to_seq
                        if _MAY_RE.search(sentence)
                        else _append_mandatory_to_seq
                    )
                    processed[loy_idx] = AbilityOutcome(
                        ability=ActivatedAbility(
                            cost=ab.cost,
                            effect=merge(ab.effect, outcome.effect),
                            condition=ab.condition,
                            timing=ab.timing,
                        )
                    )
                    # The trailing sentence is consumed — not appended.
                    continue
            # Plain text right after a triggered ability is that ability's
            # effect continuing, not a card-level spell ability — append it
            # to the trigger's effect (mandatory unless the sentence itself
            # says "may").
            trig_idx = (
                None
                if sentence.lstrip().startswith("[")
                else _trigger_trailing_idx(processed)
            )
            if trig_idx is not None:
                slot = processed[trig_idx]
                tab = slot.ability if isinstance(slot, AbilityOutcome) else None
                if isinstance(tab, TriggeredAbility):
                    # The may-rule, de-duplicated: a "may" sentence whose
                    # template ALREADY produced an OptionalEffect (Garruk's
                    # Harbinger "You may reveal … and put it into your hand")
                    # must not gain a phantom second wrap — the step is
                    # optional exactly once.
                    merge = (
                        _insert_before_last_step
                        if _WHO_CANT_TAIL_RE.match(sentence.strip())
                        else _append_optional_to_seq
                        if _MAY_RE.search(sentence)
                        and not isinstance(outcome.effect, OptionalEffect)
                        else _append_mandatory_to_seq
                    )
                    processed[trig_idx] = AbilityOutcome(
                        ability=TriggeredAbility(
                            event=tab.event,
                            condition=tab.condition,
                            effect=merge(tab.effect, outcome.effect),
                        )
                    )
                    # The trailing sentence is consumed — not appended.
                    continue
            # Plain text right after a plain activated ability is that
            # ability's activation tail — it runs when the ability resolves,
            # not when the card is cast.  Same may-rule and the same de-dup
            # guard as the trigger tail above (see
            # :func:`_activation_trailing_idx`).
            act_idx = (
                None
                if sentence.lstrip().startswith("[")
                else _activation_trailing_idx(processed)
            )
            if act_idx is not None:
                slot = processed[act_idx]
                aab = slot.ability if isinstance(slot, AbilityOutcome) else None
                if isinstance(aab, ActivatedAbility):
                    merge = (
                        _insert_before_last_step
                        if _WHO_CANT_TAIL_RE.match(sentence.strip())
                        else _append_optional_to_seq
                        if _MAY_RE.search(sentence)
                        and not isinstance(outcome.effect, OptionalEffect)
                        else _append_mandatory_to_seq
                    )
                    processed[act_idx] = AbilityOutcome(
                        ability=ActivatedAbility(
                            cost=aab.cost,
                            effect=merge(aab.effect, outcome.effect),
                            condition=aab.condition,
                            timing=aab.timing,
                        )
                    )
                    # The trailing sentence is consumed — not appended.
                    continue
            processed.append(outcome)
            processed_sentence_idx.append(i)
            continue

        # Special-case merges:
        #   - search-shuffle: the shuffle joins the INSIDE of the previous
        #     OptionalEffect (mandatory only if the optional search ran).
        #   - phase-in prevention: a MANDATORY append to the previous effect
        #     (no OptionalEffect wrap — the effect always fires).
        #   - "Otherwise": else_effect of the last Conditional, falling back
        #     to the default merge.
        #   - "When you do": inside the prior cost-paying OptionalEffect,
        #     falling back to the default merge.
        #   - "If you do" (CR 118.12): gated on whether the previous step
        #     happened, Conditional(MAY_DONE, tail).
        #   - default continuation: a step of its own, optional only when
        #     the sentence says "may".
        if _SEARCH_SHUFFLE_TAIL_RE.match(sentence):
            merge = _merge_search_shuffle
        elif _PHASE_IN_PREVENT_RE.match(sentence):
            merge = _append_mandatory_to_seq
        elif sentence.strip().startswith("Otherwise"):
            merge = _merge_otherwise
        elif sentence.strip().startswith("When you do"):
            merge = _merge_do_continuation
        elif sentence.strip().startswith(("If you do,", "If you do so,")):

            def _if_do_merge(
                prev_effect: Effect, continuation: Effect, _s: str = sentence
            ) -> Effect:  # default-arg binds the sentence NOW (no late closure)
                return _merge_if_do_continuation(prev_effect, continuation, _s)

            merge = _if_do_merge
        else:
            # A "may"-free continuation ("Then do X") is MANDATORY given its
            # antecedent.  Only "you may …" sentences are optional.
            merge = (
                _append_optional_to_seq
                if _MAY_RE.search(sentence)
                else _append_mandatory_to_seq
            )

        # --- continuation: find the previous meaningful entry in processed ---
        prev_idx: int | None = None
        for j in range(len(processed) - 1, -1, -1):
            prev = processed[j]
            if prev is None or isinstance(prev, RuleReminderOutcome):
                continue
            if isinstance(prev, EffectOutcome):
                prev_idx = j
                break
            if isinstance(prev, AbilityOutcome):
                # Only abilities that carry an Effect are merge targets.
                ab = prev.ability
                if isinstance(
                    ab,
                    (StaticAbility, ActivatedAbility, TriggeredAbility),
                ):
                    prev_idx = j
                    break
                # An effect-less SpellAbility (pure additional-costs
                # carrier) has nothing to merge into — keep searching.
                if isinstance(ab, SpellAbility) and ab.effect is not None:
                    prev_idx = j
                    break
                # KeywordAbility / ReplacementAbility: skip, keep searching.
            # KeywordOutcome / MetaOutcome: no effect to merge into; skip.

        if prev_idx is not None:
            prev = processed[prev_idx]
            if isinstance(prev, EffectOutcome):
                merged = merge(prev.effect, outcome.effect)
                processed[prev_idx] = EffectOutcome(effect=merged)
            elif isinstance(prev, AbilityOutcome):
                ab = prev.ability
                if isinstance(ab, StaticAbility):
                    merged_eff = merge(ab.effect, outcome.effect)
                    processed[prev_idx] = AbilityOutcome(
                        ability=StaticAbility(effect=merged_eff)
                    )
                elif isinstance(ab, ActivatedAbility):
                    merged_eff = merge(ab.effect, outcome.effect)
                    processed[prev_idx] = AbilityOutcome(
                        ability=ActivatedAbility(
                            cost=ab.cost,
                            effect=merged_eff,
                            condition=ab.condition,
                            # a continuation merge keeps the timing window
                            timing=ab.timing,
                        )
                    )
                elif isinstance(ab, SpellAbility):
                    assert ab.effect is not None  # the search skips effect-less spells
                    merged_eff = merge(ab.effect, outcome.effect)
                    processed[prev_idx] = AbilityOutcome(
                        ability=SpellAbility(
                            kind=ab.kind,
                            effect=merged_eff,
                            additional_costs=ab.additional_costs,
                        )
                    )
                elif isinstance(ab, TriggeredAbility):
                    merged_eff = merge(ab.effect, outcome.effect)
                    processed[prev_idx] = AbilityOutcome(
                        ability=TriggeredAbility(
                            event=ab.event,
                            condition=ab.condition,
                            effect=merged_eff,
                        )
                    )
            # The continuation sentence is consumed — not appended.
            continue

        # No previous effect to attach to.
        if _PHASE_IN_PREVENT_RE.match(sentence):
            # A phase-in prevention is mandatory even in isolation — append
            # it bare (no OptionalEffect wrap).
            processed.append(outcome)
            processed_sentence_idx.append(i)
            continue
        # A generic continuation becomes its own step — optional when the
        # sentence carries "may" or when it is an orphaned search-shuffle
        # (its anaphoric condition can never hold, so the never-fires wrap
        # is the safe encoding), else appended bare/mandatory.
        effect = outcome.effect
        if _MAY_RE.search(sentence) or _SEARCH_SHUFFLE_TAIL_RE.match(sentence):
            effect = OptionalEffect(effect)
        processed.append(EffectOutcome(effect=effect))
        processed_sentence_idx.append(i)

    # -- Collect keywords ---------------------------------------------------
    bare_keywords = _build_bare_keywords(raw)
    # KNOWN-GAP: report unbuildable keywords
    for kw_str in raw.keywords:
        kw_enum = _KEYWORD_STRING_TO_ENUM.get(kw_str)
        if kw_enum is None:
            continue
        if kw_enum in _KEYWORDS_BARE_UNBUILDABLE:
            known_gaps.append(
                f"keyword {kw_str!r}: requires params not available from identity alone"
            )
        if kw_str == "Hexproof from":
            known_gaps.append(
                "keyword 'Hexproof from': requires Filter param not available from identity alone"
            )

    template_keywords: list[KeywordAbility] = []
    for outcome in processed:
        if isinstance(outcome, KeywordOutcome):
            template_keywords.append(
                KeywordAbility(keyword=outcome.keyword, params=outcome.params)
            )

    # Dedup by (keyword, params)
    kw_set: dict[tuple[Keyword, tuple[object, ...]], KeywordAbility] = {}
    for ka in (*bare_keywords, *template_keywords):
        key = (ka.keyword, ka.params)
        if key not in kw_set:
            kw_set[key] = ka
    keywords: tuple[KeywordAbility, ...] = tuple(kw_set.values())

    # -- Collect meta outcomes ----------------------------------------------
    meta_filters: list[Filter] = []
    for outcome in processed:
        if isinstance(outcome, MetaOutcome) and outcome.filter is not None:
            meta_filters.append(outcome.filter)

    # The Enchant restriction rides on the ENCHANT keyword, "Enchant [object or player]"
    # (CR 702.5a), which limits what the Aura spell may target (CR 303.4a) and what the Aura
    # may enchant. On the keyword, not the spell's effect, so an Aura cast through the
    # effect-less carrier keeps it.
    if meta_filters:
        enchant = meta_filters[0] if len(meta_filters) == 1 else FAnd(tuple(meta_filters))
        keywords = tuple(
            KeywordAbility(keyword=Keyword.ENCHANT, params=(enchant,))
            if ka.keyword is Keyword.ENCHANT and not ka.params
            else ka
            for ka in keywords
        )

    # -- Collect additional costs -------------------------------------------
    # "As an additional cost to cast this spell, ..." sentences: attached
    # to the card's SpellAbility right after assembly (order preserved).
    additional_costs: tuple[Cost, ...] = tuple(
        outcome.cost
        for outcome in processed
        if isinstance(outcome, AdditionalCostOutcome)
    )

    # -- Collect activation gates -------------------------------------------
    # "Activate only if ..." sentences carry a condition that binds the
    # card's ActivatedAbility rather than a sentence of their own.  Collected
    # from ``outcomes`` (strictly sentence-aligned) rather than ``processed``
    # (whose indices can drift after consumed continuations).
    activation_gates: list[tuple[int, ActivationGateOutcome]] = [
        (i, outcome)
        for i, outcome in enumerate(outcomes)
        if isinstance(outcome, ActivationGateOutcome)
    ]

    # -- Separate abilities and effects -------------------------------------
    # Each outcome is tracked back to its source raw-sentence index so
    # post-assembly mechanisms (activation gates) can anchor to the
    # abilities they modify.
    ability_outcomes: list[Ability] = []
    ability_src: list[int] = []
    effect_outcomes: list[Effect] = []
    effect_src: list[int] = []
    # Set when a printed permission had to be suppressed; the card then
    # cannot be played as printed, so the gated pass marks it unsupported.
    permission_unsupported = False
    for src, outcome in zip(processed_sentence_idx, processed):
        if isinstance(outcome, AbilityOutcome):
            if _is_result_anaphoric_cast_permission(outcome.ability):
                # The phantom "you may play that card" permission —
                # never printed as an activated ability, unresolvable by
                # the executor (no play-permission lane, register-less
                # selector). Suppressed HERE, at emission into the card
                # tree; the sentence stays template-matched.
                known_gaps.append(
                    "KNOWN-GAP (play permission): anaphoric 'you may play "
                    "that card' cast-permission node suppressed at assembly "
                    "(no executor play-permission lane; the card prints no "
                    "activated ability)"
                )
                continue
            if _is_duration_cast_permission(outcome, raw.sentences[src]):
                # The same suppression for a duration-limited permission. It
                # is part of the ability printed above it (CR 611.2a) and must
                # never be a free, repeatable ability of its own; that ability
                # cannot be played as printed, so the card is engine-unsupported.
                known_gaps.append(
                    "KNOWN-GAP (cast permission): duration-limited permission "
                    f"{raw.sentences[src]!r} suppressed at assembly (it belongs to "
                    "the ability printed above it; CAST has no duration role); "
                    "the card is engine-unsupported"
                )
                permission_unsupported = True
                continue
            if isinstance(outcome.ability, ActivatedAbility) and casts_itself_from_another_zone(
                outcome.ability.effect
            ):
                # A card's permission to cast itself from another zone (Demonic Embrace)
                # would be an activated ability of the permanent, which can never cast it.
                # The IR has no permission lane yet (BACKLOG B-100), so the row is refused
                # and the card is engine-unsupported.
                known_gaps.append(
                    "KNOWN-GAP (cast permission): "
                    f"{raw.sentences[src]!r} refused (a permission to cast the card from "
                    "another zone; no permission lane, DESIGN_ATOM_ONTOLOGY R5-2); the "
                    "card is engine-unsupported"
                )
                permission_unsupported = True
                continue
            ability_outcomes.append(outcome.ability)
            ability_src.append(src)
        elif isinstance(outcome, EffectOutcome):
            effect_outcomes.append(outcome.effect)
            effect_src.append(src)
        elif isinstance(outcome, _ChooseOpenerOutcome):
            # Choose-opener folded by Step 2b — expand into its final
            # nodes (bare Choose into the spell's effects, or
            # TriggeredAbility nodes for the trigger openers).
            n_ab = len(ability_outcomes)
            n_eff = len(effect_outcomes)
            _expand_choose_opener(outcome, ability_outcomes, effect_outcomes)
            ability_src.extend([src] * (len(ability_outcomes) - n_ab))
            effect_src.extend([src] * (len(effect_outcomes) - n_eff))

    # Apply meta filters to all effects (Enchant X conjunct)
    if meta_filters:
        for i, eff in enumerate(effect_outcomes):
            for mf in meta_filters:
                eff = _fold_meta_filter(eff, mf)
            effect_outcomes[i] = eff

    # -- Assemble by card type ----------------------------------------------
    types = raw.types
    is_creature = "Creature" in types
    is_land = "Land" in types
    is_planeswalker = "Planeswalker" in types
    is_token = raw.is_token
    is_emblem = raw.is_emblem

    abilities: list[Ability] = []
    # Source sentence index per assembled ability (invariant:
    # len(ability_srcs) == len(abilities)).
    ability_srcs: list[int] = []
    abilities.extend(ability_outcomes)
    ability_srcs.extend(ability_src)

    if is_emblem or is_token:
        # Tokens/emblems: effects become standalone abilities
        # (no SpellAbility for tokens — they're not cast).
        for eff, src in zip(effect_outcomes, effect_src):
            # KNOWN-GAP: token effect categorization is bucket-specific;
            # StaticAbility is the closest honest wrapper.
            abilities.append(StaticAbility(effect=eff))
            ability_srcs.append(src)
    elif is_planeswalker:
        # Planeswalker: effects become SpellAbility (PLANESWALKER)
        if effect_outcomes:
            combined = (
                effect_outcomes[0]
                if len(effect_outcomes) == 1
                else Seq(steps=tuple(effect_outcomes))
            )
            abilities.append(SpellAbility(kind=SpellKind.PLANESWALKER, effect=combined))
            ability_srcs.append(max(effect_src))
    elif is_land:
        # Land: effects become ActivatedAbility (free cost if no cost given).
        # KNOWN-GAP: land cost extraction is bucket-specific.
        for eff, src in zip(effect_outcomes, effect_src):
            abilities.append(ActivatedAbility(cost=Cost(parts=()), effect=eff))
            ability_srcs.append(src)
    elif is_creature:
        # Creature: always a SpellAbility(CREATURE) — the cast lane.
        # EffectOutcome folds into it when present; a plain creature with
        # no effect sentence still gets an effect-less carrier, because
        # legality.cast needs a SpellAbility (creatures cast through the
        # same lane as instants).
        if effect_outcomes:
            combined = (
                effect_outcomes[0]
                if len(effect_outcomes) == 1
                else Seq(steps=tuple(effect_outcomes))
            )
            abilities.append(SpellAbility(kind=SpellKind.CREATURE, effect=combined))
            ability_srcs.append(max(effect_src))
        else:
            abilities.append(SpellAbility(kind=SpellKind.CREATURE))
            # Synthetic carrier, not tied to a sentence — use the last
            # sentence index so it can never masquerade as a "preceding"
            # ability when anchoring activation gates.
            ability_srcs.append(len(raw.sentences) - 1)
    else:
        # Instant/Sorcery/Enchantment/other: fold all effects into one
        # SpellAbility.
        if effect_outcomes:
            kind = _spell_kind_from_types(types, False)
            combined = (
                effect_outcomes[0]
                if len(effect_outcomes) == 1
                else Seq(steps=tuple(effect_outcomes))
            )
            abilities.append(SpellAbility(kind=kind, effect=combined))
            ability_srcs.append(max(effect_src))

    # -- Permanent-spell carrier ----------------------------------------------
    # A noncreature permanent whose text is all static, triggered or activated
    # abilities (an anthem, an equipment, a planeswalker) assembles NO
    # SpellAbility, so spell_castable would answer cast:not_a_spell. It is
    # plainly a permanent spell (CR 301.1, 303.1, 306.1), so it gets the
    # effect-less carrier creatures and kicker heads get. Lands are played,
    # not cast; tokens and emblems are never cast.
    if (
        not is_land
        and not is_token
        and not is_emblem
        and not is_creature
        and any(t in types for t in ("Enchantment", "Artifact", "Planeswalker"))
        and not any(isinstance(ab, SpellAbility) for ab in abilities)
        and not any(isinstance(ab, KickerAbility) for ab in abilities)
    ):
        abilities.append(SpellAbility(kind=_spell_kind_from_types(types, False)))
        # Synthetic carrier, not tied to a sentence (last-index convention).
        ability_srcs.append(len(raw.sentences) - 1)

    # -- Attach additional costs to the spell --------------------------------
    # Additional-cost sentences ride on a SpellAbility. A card that matched
    # one but compiled without one falls into two cases:
    #   - land / token / emblem: the card is never cast, so there is no
    #     spell to attach the cost to — state corruption, not a gap;
    #   - any other castable spell with no effect sentence (e.g. Goremand,
    #     whose only sentence is a triggered ability): build an effect-less
    #     SpellAbility (effect=None) carrying the additional costs.
    if additional_costs:
        if not any(isinstance(ab, SpellAbility) for ab in abilities):
            if is_land or is_token or is_emblem:
                raise StateCorruptionError(
                    "compile_card: additional-cost sentence matched but the "
                    "card compiled as a non-castable card (land, token, or "
                    f"emblem) with no SpellAbility to attach it to "
                    f"(type line: {raw.type_line!r})",
                    context={
                        "oracle_id": raw.identity.oracle_id,
                        "types": raw.types,
                    },
                )
            abilities.append(
                SpellAbility(
                    kind=_spell_kind_from_types(types, is_creature),
                    additional_costs=additional_costs,
                )
            )
            # Synthetic carrier, not tied to a sentence — use the last
            # sentence index so it can never masquerade as a "preceding"
            # ability when anchoring activation gates.
            ability_srcs.append(len(raw.sentences) - 1)
        else:
            abilities = [
                replace(ab, additional_costs=ab.additional_costs + additional_costs)
                if isinstance(ab, SpellAbility)
                else ab
                for ab in abilities
            ]

    # -- Kicker head carrier -------------------------------------------------
    # A noncreature spell whose every sentence compiled to a NON-effect
    # ability (Roost of Drakes: a bare "Kicker {2}{U}." head + triggered
    # abilities, no effect sentence) assembles no SpellAbility, and the cast
    # lane's spell_castable would answer ``cast:not_a_spell``. The kicker
    # head is a cast-time declaration (CR 702.27a: "this spell" may be
    # kicked — it is plainly a spell), so it earns the effect-less carrier
    # exactly as the additional-cost path above (Goremand) and the creature
    # branch do. The fold never fires for cards that already carry a
    # SpellAbility.
    if (
        not is_land
        and not is_token
        and not is_emblem
        and any(isinstance(ab, KickerAbility) for ab in abilities)
        and not any(isinstance(ab, SpellAbility) for ab in abilities)
    ):
        abilities.append(SpellAbility(kind=_spell_kind_from_types(types, False)))
        # Synthetic carrier, not tied to a sentence (last-index convention).
        ability_srcs.append(len(raw.sentences) - 1)

    # -- Attach activation gates ---------------------------------------------
    # Each gate binds its slots (window and/or condition) slot-disjointly
    # to the nearest preceding ActivatedAbility (source sentence index)
    # whose targeted slot(s) are still free: a window slot requires
    # ``timing is None``, a condition slot requires ``condition is None``; a
    # gate carrying BOTH (Speaker's compound) attaches both. Gates are
    # processed in sentence order; once an ability's needed slot is filled it
    # no longer qualifies for a later gate wanting that slot.
    for gate_src, gate in activation_gates:
        candidates = [
            (src, j)
            for j, (ab, src) in enumerate(zip(abilities, ability_srcs))
            if src < gate_src
            and isinstance(ab, ActivatedAbility)
            and (gate.window is None or ab.timing is None)
            and (gate.condition is None or ab.condition is None)
        ]
        if not candidates:
            raise StateCorruptionError(
                "compile_card: activation-gate sentence matched but no "
                "preceding ActivatedAbility with the gate's target slot(s) "
                f"free exists to attach it to (gate: {raw.sentences[gate_src]!r})",
                context={
                    "oracle_id": raw.identity.oracle_id,
                    "name": raw.identity.name,
                },
            )
        _, target = max(candidates)
        updates = {}
        if gate.window is not None:
            updates["timing"] = gate.window
        if gate.condition is not None:
            updates["condition"] = gate.condition
        abilities[target] = replace(abilities[target], **updates)

    # -- Search-pick observability rewrite ---------------------------------
    # Up-to-one SEARCH picks ask the ONE_OF channel instead of resolving
    # silently; see _one_of_search_picks.
    abilities = [_flip_search_picks_in(ab) for ab in abilities]

    # -- PICK-ask promotion (structural rule) --------------------------------
    # Every QConst(1) referent-less non-cost non-self-ref entity CHOOSE
    # asks the ONE_OF channel automatically; see _is_liftable_pick /
    # docs/T4_PICK_ENUMERATION.md.
    abilities = _promote_liftable_picks(abilities, raw.identity.name)

    # -- Back-face fold -------------------------------------------------------
    # A modal double-faced card's back face is the CARD'S OWN second face:
    # its sentences are compiled through the SAME tolerant machinery (a
    # synthetic single-faced RawCard carrying the face's printed data — same
    # split, same templates, same unparsed queue) and the results fold into
    # one BackFace ability node. Unmatched face sentences enter
    # CompileResult.back_face_unparsed (coverage.py rows them "[face B]"),
    # NEVER counted as covered. The node is ENCODED ONLY: every
    # walk()-consumer verdict gate below skips the BackFace subtree.
    back_face_unparsed: tuple[tuple[str, str], ...] = ()
    if raw.back_face is not None:
        # A malformed face (bad type_line/loyalty) degrades to face-unparsed:
        # it must NEVER crash the pool pass or sacrifice the playable FRONT
        # card.
        try:
            face_result = compile_card(_as_single_faced(raw), registry)
        except (ValueError, StateCorruptionError):
            back_face_unparsed = tuple(
                (s, "face-compile-failed") for s in raw.back_face.sentences
            )
        else:
            abilities.append(BackFace(raw.back_face.name, face_result.card.abilities))
            # Face-level ambiguities and rule reminders are the card's own
            # text facts — surface them in the card's report.
            ambiguities.extend(face_result.ambiguities)
            rule_reminders.extend(face_result.rule_reminders)
            back_face_unparsed = face_result.unparsed

    # -- Build CardRecord ----------------------------------------------------
    # A Vehicle prints P/T on a non-creature artifact; it is a creature only while crewed
    # (CR 301.7), and crew is not implemented. CardRecord rejects P/T on a non-creature with a
    # ValueError that would abort a whole-set compile, so refuse the shape here: the card
    # becomes a shape gap, counted against coverage.
    if "Creature" not in raw.types and (power is not None or toughness is not None):
        raise StateCorruptionError(
            "compile_card: printed P/T on a non-creature (a Vehicle needs crew, not implemented)",
            context={"card": raw.identity.name, "type_line": raw.type_line},
        )
    card = CardRecord(
        oracle_id=raw.identity.oracle_id,
        name=raw.identity.name,
        type_line=raw.type_line,
        types=raw.types,
        subtypes=raw.subtypes,
        supertypes=raw.supertypes,
        colors=raw.colors,
        color_identity=raw.color_identity,
        mana_cost=mana_cost,
        mana_value=raw.mana_value,
        power=power,
        toughness=toughness,
        loyalty=loyalty,
        keywords=keywords,
        abilities=tuple(abilities),
        # An emblem is a specialised token: the grammar requires a CardRecord
        # carried as ``emblem`` to be an "Emblem-typed token record"
        # (CardRecord.__post_init__).  Ingest models emblems with layout
        # "emblem" (is_token=False), so we normalise emblem => token here.
        is_token=raw.is_token or is_emblem,
    )

    known_gaps.extend(_star_pt_gaps(raw, card))
    engine_supported = _engine_supported(card, supported_verbs)
    if permission_unsupported and supported_verbs is not None:
        engine_supported = False  # a suppressed or refused permission

    legality = LegalityFlags(
        format_legal=True,
        engine_supported=engine_supported,
    )

    return CompileResult(
        card=card,
        legality=legality,
        unparsed=tuple(unparsed),
        ambiguities=tuple(ambiguities),
        rule_reminders=tuple(rule_reminders),
        known_gaps=tuple(known_gaps),
        back_face_unparsed=back_face_unparsed,
    )


# ---------------------------------------------------------------------------
# compile_pool
# ---------------------------------------------------------------------------


def compile_pool(
    pool: dict[str, RawCard],
    registry: TemplateRegistry,
    supported_verbs: set[Verb] | None = None,
    records: dict[str, dict[str, Any]] | None = None,
    *,
    require_verified: bool = True,
) -> PoolCompile:
    """Compile an entire pool (oracle_id → RawCard).

    Emblems are compiled and attached to their owner CardRecord via
    ``related_names``.  Emblems are excluded from the standalone ``cards``
    dict.  Missing owners become ``orphan_emblems``.

    ``records`` (oracle_id → card record, card_records.py) puts a mapped tree
    in place of the compiler's; with ``require_verified`` (the default) only a
    record whose tree passed verification is applied.

    Summary is internally consistent:
    - total = number of non-emblem cards
    - fully_compiled = cards with no unparsed and no ambiguities
    - partially_compiled = cards with some unparsed or ambiguities
    - ambiguity_count = total ambiguities across all cards
    - unparsed_count = total unparsed sentences across all cards
    - known_gap_count = total known-gap notes across all cards
    - verb_histogram = {Verb.name: count} across all compiled atoms
    - keyword_histogram = {Keyword.name: count} across all keywords
    """
    results: dict[str, CompileResult] = {}
    for oid, raw in pool.items():
        try:
            results[oid] = compile_card(raw, registry, supported_verbs)
        except StateCorruptionError:
            # A card whose text the compiler refuses can still be rescued by its card record:
            # the printed facts compile alone, the record supplies every ability. If the record
            # does not apply (absent, stale, unverified), the refusal stands.
            if not (records and "ir" in records.get(oid, {})):
                raise
            from MTG_bot.core.compiler.card_records import apply_record

            base = compile_card(replace(raw, sentences=(), back_face=None), registry, supported_verbs)
            rescued = apply_record(
                raw, base, records[oid], supported_verbs, require_verified=require_verified
            )
            if rescued.record is None:
                raise
            results[oid] = rescued
    if records:
        # Card records (docs/PLAN_CARD_ONBOARDING.md): a mapped tree replaces the compiler's
        # for its card; by default only a verified one.
        from MTG_bot.core.compiler.card_records import apply_record

        for oid, raw in pool.items():
            if oid in records and results[oid].record is None:
                results[oid] = apply_record(
                    raw, results[oid], records[oid], supported_verbs,
                    require_verified=require_verified,
                )

    # Separate emblems from non-emblems
    emblem_oids: set[str] = set()
    for oid, raw in pool.items():
        if raw.is_emblem:
            emblem_oids.add(oid)

    # Build name → oracle_id lookup for owner resolution
    name_to_oid: dict[str, str] = {}
    for oid, raw in pool.items():
        if not raw.is_emblem:
            name_to_oid[raw.identity.name] = oid

    # Attach emblems to owners, then build the card dict from the UPDATED
    # results. This must be two passes: the pool is name-sorted, so an owner
    # (e.g. "Basri Ket") always precedes its emblem ("Basri Ket Emblem"). A
    # single interleaved loop would capture the owner's pre-attachment card
    # into ``cards`` before the emblem pass updates ``results[owner_oid]``,
    # leaving every ``cards[...].emblem`` as None.
    emblems: dict[str, CardRecord] = {}
    orphan_emblems: list[str] = []

    for oid, raw in pool.items():
        if raw.is_emblem:
            emblems[oid] = results[oid].card
            # Find owner
            owner_oid: str | None = None
            for owner_name in raw.related_names:
                if owner_name in name_to_oid:
                    owner_oid = name_to_oid[owner_name]
                    break
            # An owner whose planeswalker is its BACK face (KHM Valki, God of Lies //
            # Tibalt, Cosmic Impostor) cannot carry the emblem on its creature front
            # (CardRecord: "only a Planeswalker may carry an emblem"), and faces are not
            # castable yet, so the emblem is unreachable in play: keep it an orphan.
            if owner_oid is None or "Planeswalker" not in results[owner_oid].card.types:
                orphan_emblems.append(oid)
            else:
                # Rebuild owner's CardRecord with emblem
                owner_result = results[owner_oid]
                owner_card = replace(owner_result.card, emblem=results[oid].card)
                results[owner_oid] = replace(owner_result, card=owner_card)

    # Second pass: collect non-emblem cards (now with emblems attached).
    cards: dict[str, CardRecord] = {}
    for oid, raw in pool.items():
        if not raw.is_emblem:
            cards[oid] = results[oid].card

    # -- Build summary -------------------------------------------------------
    total = len(cards)
    fully_compiled = 0
    partially_compiled = 0
    ambiguity_count = 0
    unparsed_count = 0
    known_gap_count = 0
    verb_histogram: dict[str, int] = {}
    keyword_histogram: dict[str, int] = {}

    for oid, result in results.items():
        if oid in emblem_oids:
            continue  # emblems excluded from card-level stats
        # Back-face residue counts: a card whose only unparsed text is its
        # face is NOT fully compiled.
        if not (result.unparsed or result.ambiguities or result.back_face_unparsed):
            fully_compiled += 1
        else:
            partially_compiled += 1
        ambiguity_count += len(result.ambiguities)
        unparsed_count += len(result.unparsed) + len(result.back_face_unparsed)
        known_gap_count += len(result.known_gaps)

        # The pool verb histogram stays FRONT-ONLY (face verbs are
        # census-tagged in coverage.py's backface summary, never merged
        # untagged here).
        for node in walk(result.card, skip=BackFace):
            if isinstance(node, Atom):
                vname = node.verb.name
                verb_histogram[vname] = verb_histogram.get(vname, 0) + 1
        for kw in result.card.keywords:
            kname = kw.keyword.name
            keyword_histogram[kname] = keyword_histogram.get(kname, 0) + 1

    summary: dict[str, Any] = {
        "total": total,
        "emblems": len(emblems),
        "orphan_emblems": len(orphan_emblems),
        "fully_compiled": fully_compiled,
        "partially_compiled": partially_compiled,
        "ambiguity_count": ambiguity_count,
        "unparsed_count": unparsed_count,
        "known_gap_count": known_gap_count,
        "verb_histogram": dict(sorted(verb_histogram.items())),
        "keyword_histogram": dict(sorted(keyword_histogram.items())),
    }

    return PoolCompile(
        cards=cards,
        emblems=emblems,
        orphan_emblems=tuple(sorted(orphan_emblems)),
        results=results,
        summary=summary,
    )
