"""Card-assembly compiler: RawCard → CardRecord via template matching.

Consumes the structured ingest (``RawCard``) and a ``TemplateRegistry``
to produce a typed ``CardRecord`` ability tree.  The compiler is the
boundary between English oracle sentences and the closed IR grammar:
every sentence is either matched by a template (→ structured outcome),
detected as a rule reminder, or routed to the explicit unparsed queue.

Public API:
    parse_mana_cost(raw) -> Cost | None
    parse_pt(raw) -> Quantity | None
    compile_card(raw, registry, supported_verbs=None) -> CompileResult
    compile_pool(pool, registry, supported_verbs=None) -> PoolCompile
"""

from __future__ import annotations

import re
from dataclasses import dataclass, fields, is_dataclass, replace
from typing import Any, cast, get_args

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
    DurationUntilNextTurn,
    EachPlayer,
    Effect,
    EtBState,
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
    QBin,
    QConst,
    QUnbounded,
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
# Keyword string → Keyword enum mapping (M21 pool-verified).
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
# KNOWN-GAP (restated 2026-10-07, doc 36): the GRAMMAR models all four
#   shapes fine — Verb.SCRY/MILL/BATTALION carry a Quantity and
#   Keyword.PROTECTION a Filter, and the Quantity/Filter grammar itself
#   is rich (10 Quantity forms, full FAnd/FOr/FNot). The real gap is
#   UPSTREAM of the grammar: the identity keyword pipeline delivers bare
#   strings ("Scry", "Mill") with no number/filter attached, and no
#   oracle-text extraction feeds _KEYWORD_PARAMS for them, so the
#   compiler skips them (reported via CompileResult.known_gaps) unless a
#   template supplies the params. Wiring identity → params is the fix;
#   extending the atomics is not.
_KEYWORDS_BARE_UNBUILDABLE: frozenset[Keyword] = frozenset(
    {Keyword.SCRY, Keyword.MILL, Keyword.BATTALION, Keyword.PROTECTION}
)

# ---------------------------------------------------------------------------
# Continuation prefixes (02-phase1-plan.md).
# ---------------------------------------------------------------------------

_CONTINUATION_PREFIXES: tuple[str, ...] = (
    "If you do",
    "If you do so",
    "If target",
    "If it ",
    "If that",
    "If you search your library this way",
    "Then ",
    # Grammar round 7, R7-3: "Otherwise" attaches as the else_effect of
    # the previous Conditional (_merge_otherwise, C13 fallback); "When
    # you do" (grammar round 9, R9-9) attaches INSIDE the previous
    # OptionalEffect whose inner pays a cost (Tolarian Kraken: antecedent
    # "you may pay {1}" — _merge_do_continuation, C24; the s2 template
    # ships with the 9-B batch).
    "Otherwise",
    "When you do",
)

# ---------------------------------------------------------------------------
# Search-shuffle boilerplate (compiler built-in, no template).
#
# "If you search your library this way, shuffle." (6x in M21) mandates the
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
# Voyager [−8]; 1x in M21) is the mandatory second sentence of a loyalty
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
    """Canonical phase-in prevention atom (T3 round 2, item 5 composition).

    Prevents the opponent's command-zone permanents entering the battlefield
    until the controller's next turn.  ``DurationUntilNextTurn`` carries the
    "until the end of your next turn" scope.
    """
    return Atom(
        verb=Verb.PREVENT_EFFECT,
        args=AtomArgs(
            pairs=(
                (
                    "condition",
                    FAtom(FAtomPred.CONTROLLER_IS, who=ControllerRef.OPPONENT),
                ),
                (
                    "event",
                    ZoneChangeEvent(
                        from_zone=Zone(
                            kind=ZoneKind.COMMAND, controller=ControllerRef.OPPONENT
                        ),
                        to_zone=Zone(
                            kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.OPPONENT
                        ),
                    ),
                ),
                ("duration", DurationUntilNextTurn()),
            )
        ),
    )


# ---------------------------------------------------------------------------
# Choose-opener boilerplate (compiler built-in, no template).
#
# "Choose one —" (7 cards in M21) is an opener sentence: the option bullets
# that follow are already parsed as sibling EffectOutcomes by the option
# templates, so only the opener itself fails template matching.  This pass
# folds the opener + its option bullets into one Choose node (or a triggered
# ability carrying one) so the card no longer reports an unparsed sentence.
#
# KNOWN-GAP: "Choose one or more —" (Sublime Epiphany) is approximated with
#   QUnbounded() — the grammar has no QAtLeast(1), so the minimum-1
#   constraint is lost.
# KNOWN-GAP: "attacks or blocks" (Elder Gargaroth) is decomposed into two
#   TriggeredAbility nodes (DeclareAttackersEvent + DeclareBlockersEvent)
#   sharing the same Choose effect — the grammar has no composite
#   "attacks or blocks" EventSpec.  A creature cannot attack and block in
#   the same turn, so the decomposition is behaviourally equivalent.
#
# Modal "Choose two/three —" openers (tokenizer refinement 2026-10-07, doc
# 29): the same fold, with the Choose combinator's EXISTING ``count`` slot
# carrying the modal cardinality (no grammar extension — the count axis is
# already orthogonal to the operation).  The current M21 pool contains no
# such card (measured: grep of cards.text over the 397-card corpus finds
# only "Choose one"/"Choose one or more"); this is tokenizer readiness for
# the next sets, per the AGENTS.md §8 tokenizer law.
# ---------------------------------------------------------------------------

_CHOOSE_ONE_RE = re.compile(r"^Choose one —$")
_CHOOSE_TWO_RE = re.compile(r"^Choose two —$")
_CHOOSE_THREE_RE = re.compile(r"^Choose three —$")
_CHOOSE_ONE_OR_MORE_RE = re.compile(r"^Choose one or more —$")
_CHOOSE_ETB_RE = re.compile(r"^When this creature enters, choose one —$")
_CHOOSE_ATTACK_BLOCK_RE = re.compile(
    r"^Whenever this creature attacks or blocks, choose one —$"
)

# Option bullets are printed as "• <effect>" (M21 oracle-text convention).
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


# Modal spell openers and their Choose counts (doc 29 refinement ①:
# same fold as "Choose one —", count axis carried by the existing slot).
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
    """Zone-change event for the "When this creature enters" opener.

    R11-B (audit 09-29/04 P0-2): the ``_CHOOSE_ETB_RE`` opener is
    literally ``When this creature enters`` — the entering object is the
    card itself, so the event subject anchors on IS_SOURCE."""
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
        QUnbounded()
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

    # KNOWN-GAP: number-prefixed split hybrids (``{3/W}``) are not
       representable in the Cost grammar (which models two-colour
       hybrids only).  They raise ``StateCorruptionError`` with a
       distinct split-hybrid message.  M21 contains none.
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
    if not tokens:
        return None
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
            # # KNOWN-GAP: split-cost hybrid ({3/W}) — the Cost grammar
            # models two-colour hybrids only; no M21 card uses this form.
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
# Local bucket classifier for unparsed sentences (no /tmp import).
# ---------------------------------------------------------------------------

_KEYWORD_WORDS: frozenset[str] = frozenset(kw for kw in _KEYWORD_STRING_TO_ENUM)
_TRIGGER_PREFIXES: tuple[str, ...] = (
    "When ",
    "Whenever ",
    "At the beginning",
    "At combat",
    "At the start",
    "Whenever a",
    "Whenever the",
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
    # Activated: starts with a cost token
    for prefix in _ACTIVATED_PREFIXES:
        if s.startswith(prefix):
            return "activated"
    # Triggered: starts with a trigger word
    for prefix in _TRIGGER_PREFIXES:
        if s.startswith(prefix):
            return "triggered"
    # Static: "has", "gives", "is a", "creatures you control"
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
    # Keyword word
    first_word = s.split(" ", 1)[0].rstrip(".")
    if first_word in _KEYWORD_WORDS:
        return "keyword"
    return "spell-effect"


# ---------------------------------------------------------------------------
# Keyword dedup helpers
# ---------------------------------------------------------------------------


def _build_bare_keywords(raw: RawCard) -> tuple[KeywordAbility, ...]:
    """Build KeywordAbility candidates from raw.keywords where possible.

    # KNOWN-GAP: keywords in _KEYWORDS_BARE_UNBUILDABLE cannot be
    constructed without params; "Hexproof from" needs a Filter.
    These are silently omitted (reported via CompileResult.known_gaps).
    """
    results: list[KeywordAbility] = []
    for kw_str in raw.keywords:
        kw_enum = _KEYWORD_STRING_TO_ENUM.get(kw_str)
        if kw_enum is None:
            continue
        # "Hexproof from" needs a Filter param — can't build bare.
        if kw_str == "Hexproof from":
            continue
        # Keywords that require params in ALL their signatures.
        if kw_enum in _KEYWORDS_BARE_UNBUILDABLE:
            continue
        results.append(KeywordAbility(keyword=kw_enum, params=()))
    return tuple(results)


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
    ``back_face_unparsed`` — ZND-2f (/106): (sentence, hint) pairs for
    UNMATCHED back-face sentences only; ``unparsed`` stays the front-face
    register (PC-1's formula stays front-face compile results, /96 law).
    """

    card: CardRecord
    legality: LegalityFlags
    unparsed: tuple[tuple[str, str], ...] = ()
    ambiguities: tuple[AmbiguityRecord, ...] = ()
    rule_reminders: tuple[RuleReminderOutcome, ...] = ()
    known_gaps: tuple[str, ...] = ()
    back_face_unparsed: tuple[tuple[str, str], ...] = ()


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

# Sentinel for "no outcome" (unparsed).
_NO_OUTCOME = "__unparsed__"


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
    # Bare keyword: stripped sentence exactly matches a raw keyword string
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
    unparsed. B-41 grammar round S-1 (KNOWLEDGE /159): the cheapest general gap at
    first touch on M20 and KHM.
    """
    match = _TRAILING_REMINDER_RE.match(sentence.strip())
    head = (match.group("head") if match else sentence.strip()).rstrip(".")
    parts = [part.strip() for part in head.split(",")]
    carried = {kw.lower(): kw for kw in raw.keywords}
    return bool(parts) and all(carried.get(part.lower()) in _LINE_KEYWORDS for part in parts)


def _is_continuation(sentence: str) -> bool:
    """Check if a sentence starts with a continuation prefix."""
    s = sentence.strip()
    return any(s.startswith(p) for p in _CONTINUATION_PREFIXES)


# Grammar round 11 (R11-1): optionality of a continuation / trailing rules
# sentence is decided by the presence of the word "may" in the sentence
# itself.  "If you do, <do X>" is MANDATORY (the condition already gates it);
# only "you may …" sentences earn an OptionalEffect wrap.
_MAY_RE = re.compile(r"\bmay\b")


def _loyalty_trailing_idx(processed: list[_OutcomeSlot]) -> int | None:
    """Index of the tail-most loyalty ability if it is the LAST meaningful
    processed entry, else None.

    Grammar round 11 (R11-1, Basri Ket / Garruk, Savage Herald): planeswalker
    trailing rules text (CR 113.6a — text printed under a loyalty bullet
    belongs to that ability) arrives as a plain, non-continuation sentence
    and was previously orphaned as a card-level SpellAbility.  If the nearest
    meaningful processed entry is an ActivatedAbility whose cost carries a
    CostLoyalty part, that ability is the sentence's true owner.
    """
    for j in range(len(processed) - 1, -1, -1):
        prev = processed[j]
        if prev is None or isinstance(prev, RuleReminderOutcome):
            continue
        if (
            isinstance(prev, AbilityOutcome)
            and isinstance(prev.ability, ActivatedAbility)
            and prev.ability.cost is not None
            and any(isinstance(p, CostLoyalty) for p in prev.ability.cost.parts)
        ):
            return j
        return None
    return None


def _trigger_trailing_idx(processed: list[_OutcomeSlot]) -> int | None:
    """Index of the tail-most TriggeredAbility if it is the LAST meaningful
    processed entry, else None.

    Round 14b (B-11, Kitesail Freebooter / Garruk's Harbinger / Siege
    Striker): a triggered ability's text continues across sentence
    boundaries — plain sentences printed under a trigger run when the
    trigger resolves, not when the card is cast, but they arrived as bare
    EffectOutcomes and were previously orphaned onto the card-level
    SpellAbility (cast time).  If the nearest meaningful processed entry is
    a TriggeredAbility, that ability is the sentence's true owner.  Mirrors
    the boundary discipline of :func:`_loyalty_trailing_idx` (R11-1): only
    unparsed slots and rule reminders are skipped — any other outcome
    (another ability, a keyword, a gate, a meta outcome) is a group
    boundary and breaks the chain.  A sentence starting with "[" is another
    ability bullet — never a trailing sentence.
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
    """The documented empty-cost OPT(CAST) PERMISSION idiom (template B4
    "cast/play them this turn"; Chandra, Heart of Fire's "You may cast them
    this turn.", grammar round 8-C / round 14 history).

    The template compiles such a sentence into a free-cost ActivatedAbility
    whose whole effect is ``OptionalEffect(Atom(CAST, cost=Cost()))`` — the
    permission itself, not an action with consequences. It is EXEMPT from
    activation-tail ownership (r14e adjudication): a rules sentence printed
    under the loyalty bullet it follows stays owned by that bullet, so the
    tail matcher must see through the permission row instead of mis-capturing
    the loyalty tail ("Add six {R}.") as the permission's own.
    """
    if not isinstance(slot, AbilityOutcome) or not isinstance(
        slot.ability, ActivatedAbility
    ):
        return False
    ab = slot.ability
    if ab.cost is not None and ab.cost.parts:
        return False
    return (
        isinstance(ab.effect, OptionalEffect)
        and isinstance(ab.effect.inner, Atom)
        and ab.effect.inner.verb is Verb.CAST
        and ab.effect.inner.args.get("cost") == Cost(parts=())
    )


def _activation_trailing_idx(processed: list[_OutcomeSlot]) -> int | None:
    """Index of the tail-most plain activated ability if it is the LAST
    meaningful processed entry, else None.

    Round 14e (B-17, Tavern Swindler / Waker of Waves / Seasoned
    Hallowblade): sentences printed under an ACTIVATED ability run when
    that ability resolves, not when the card is cast — but they arrived as
    bare EffectOutcomes and were orphaned onto the card-level SpellAbility
    (the B-11 tail split one mechanism deeper; Swindler's
    "If you win the flip, you gain 6 life." raised FLIP_WON at cast,
    Hallowblade's "It gains indestructible until end of turn." raised the
    ``result`` referent, B-9).  Boundary discipline mirrors
    :func:`_loyalty_trailing_idx` / :func:`_trigger_trailing_idx`: only
    unparsed slots and rule reminders are skipped — any other outcome is a
    group boundary and breaks the chain.  Loyalty-costed abilities return
    None (their tails belong to the R11-1 loyalty chain, never this
    mechanism); the empty-cost OPT(CAST) permission row is EXEMPT — the
    scan sees through it (r14e adjudication, see
    :func:`_is_cast_permission_row`).
    """
    for j in range(len(processed) - 1, -1, -1):
        prev = processed[j]
        if prev is None or isinstance(prev, RuleReminderOutcome):
            continue
        if _is_cast_permission_row(prev):
            continue  # documented permission row: transparent boundary
        if isinstance(prev, AbilityOutcome) and isinstance(
            prev.ability, ActivatedAbility
        ):
            cost = prev.ability.cost
            if cost is not None and any(isinstance(p, CostLoyalty) for p in cost.parts):
                return None  # loyalty chain owns its own tails (R11-1)
            if prev.ability.effect is None:
                return None  # pure cost carrier: nothing to append to
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
    applied: the inner effect always fires.  Used by the phase-in prevention
    boilerplate, which is the guaranteed second half of a loyalty activation.
    If ``effect`` is not already a ``Seq``, it is wrapped into a two-step
    ``Seq``.
    """
    if isinstance(effect, Seq):
        return Seq(steps=effect.steps + (inner,))
    return Seq(steps=(effect, inner))


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
        if isinstance(inner, Seq):
            return OptionalEffect(inner=Seq(steps=inner.steps + (shuffle,)))
        return OptionalEffect(inner=Seq(steps=(inner, shuffle)))
    return Seq(steps=(prev_effect, shuffle))


def _merge_otherwise(prev_effect: Effect, inner: Effect) -> Effect:
    """Grammar round 7 (R7-3): "Otherwise, …" becomes the ``else_effect``
    of the previous sentence's ``Conditional`` (Garruk, Savage Herald:
    "If it's a creature card, put it into your hand. Otherwise, put it on
    the bottom of your library.").

    The Conditional is searched at the top level and as the LAST step of a
    Seq (the "do X. If it's Y, do Z." single-sentence idiom). A
    Conditional that already carries an else_effect is not overwritten.
    C13 (mandate): when no attachable Conditional is found, fall back to
    the EXISTING default continuation merge (sibling optional step) —
    "Otherwise" without a preceding Conditional must never be a parse
    failure.
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

    Structural test for the "When you do" antecedent (grammar round 9,
    R9-9): the continuation's "do" refers to paying the cost, so the prior
    effect must actually contain the PAY atom — mirrors the exhaustive
    Effect-union traversal of :func:`_fold_meta_filter`'s transform.
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
    """Grammar round 9 (R9-9, C24): "When you do, …" joins the INSIDE of
    the prior ``OptionalEffect`` that pays a cost.

    Tolarian Kraken: "When you draw a card, you may pay {1}. When you do,
    …" — the second optional only EXISTS if the payment was made, so the
    parsed continuation (already optional if the text says "you may") is
    injected into the prior OptionalEffect's inner sequence, the
    search-shuffle twin (:func:`_merge_search_shuffle`) shape.  C24
    (mandate): a sibling append here would fabricate an independent
    optional the text never grants.  Any other prior falls back to the
    EXISTING default continuation merge (sibling optional step), the same
    C13 discipline as :func:`_merge_otherwise`.
    """
    if isinstance(prev_effect, OptionalEffect) and _contains_pay_atom(
        prev_effect.inner
    ):
        inner = prev_effect.inner
        if isinstance(inner, Seq):
            return OptionalEffect(inner=Seq(steps=inner.steps + (continuation,)))
        return OptionalEffect(inner=Seq(steps=(inner, continuation)))
    return _append_optional_to_seq(prev_effect, continuation)


def _ends_with_optional(effect: Effect) -> bool:
    """r18a: does the continuation SEAM end in an ``OptionalEffect`` — the
    may-action a printed "If you do" anaphorically refers to (CR 611.1)?
    True for a bare optional and for a Seq whose last step is one (through
    nested Seqs); False means the antecedent was mandatory — the tail's
    condition already rode the mandatory action, keep today's append."""
    if isinstance(effect, OptionalEffect):
        return True
    if isinstance(effect, Seq) and effect.steps:
        return _ends_with_optional(effect.steps[-1])
    return False


def _merge_if_do_continuation(
    prev_effect: Effect, continuation: Effect, sentence: str
) -> Effect:
    """r18a (CR 611.1): "you may X. If you do, Y" — Y runs ONLY when the
    optional X actually executed.

    Round-11 (R11-1) made may-free continuations MANDATORY appends — right
    against the phantom second ask, but it left "If you do" tails running
    as free riders when the player answered ``skip`` (the wave-1b ledger's
    crypt_lurker_skip class: skip Crypt Lurker's sacrifice and the draw
    still landed). The correct gate is the may-decision's OUTCOME, so the
    tail joins the sequence as ``Conditional(MAY_DONE, Y)`` — the executor
    answers MAY_DONE from the 14b channel's logged may-offer (consumes the
    outcome, never re-asks). A "may"-bearing tail ("If you do, you may Z")
    keeps its own inner optional INSIDE the gate. A non-optional seam
    (mandatory antecedent, e.g. Archfiend's Vessel's condition-gated exile,
    Mazemind Tome's counter-ability) keeps today's plain append: its "if
    you do" is the mandatory action the sequence already performed.
    """
    if _ends_with_optional(prev_effect):
        inner = continuation
        if _MAY_RE.search(sentence) and not isinstance(inner, OptionalEffect):
            inner = OptionalEffect(inner=inner)
        gated = Conditional(pred=FAtom(pred=FAtomPred.MAY_DONE), then_effect=inner)
        return _append_mandatory_to_seq(prev_effect, gated)
    return (
        _append_optional_to_seq(prev_effect, continuation)
        if _MAY_RE.search(sentence)
        else _append_mandatory_to_seq(prev_effect, continuation)
    )


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
                    # R0 zone-fold KEYED-LOSS fix (/129 §2, gate F6): the
                    # rebuild carries the FULL zone set AND the referent —
                    # the pre-fold positional rebuild silently dropped
                    # zones (twin-loss vector; fold_meta_filter reaches 1
                    # template with 0 live rebuilds across 586 cards, so
                    # this is future-proofing pinned by test_ontology_r0).
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
    """Derive the SpellAbility kind for a castable card from its type line.

    Mirrors the assembly branches in compile_card: the creature and
    planeswalker branches win first, then the else-branch ordering
    (Instant, Sorcery, Enchantment, fallback Sorcery)."""
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
    return SpellKind.SORCERY


def _is_result_anaphoric_cast_permission(ability: Ability) -> bool:
    """C5 (Furious Rise): an EMPTY-cost ActivatedAbility whose effect is an
    OptionalEffect-wrapped CAST over a ``referent="result"`` selector —
    ``_build_play_that_card_until``'s shape for "You may play that card
    until you exile another card with this enchantment."  The printed card
    carries NO activated ability: the play window is a permission created
    by the end-step trigger's exile, and the engine has no play-permission
    lane (the node was a phantom whose activation crashed the executor on
    the register-less selector).  The template stays MATCHED (PC-1/PC-2
    honesty: the sentence is parsed and reported); the NODE is suppressed
    at assembly with a KNOWN-GAP note.  The shape is narrow by design:
    Azusa-style empty-cost activations carry other verbs, and every other
    corpus may-cast permission names its cost or its object (no result
    referent) — a corpus scan found exactly one carrier."""
    if not isinstance(ability, ActivatedAbility) or ability.cost.parts:
        return False
    inner = ability.effect.inner if isinstance(ability.effect, OptionalEffect) else None
    if not isinstance(inner, Atom) or inner.verb is not Verb.CAST:
        return False
    src = dict(inner.args.pairs).get("source")
    return isinstance(src, Selector) and src.referent == "result"


def _one_of_search_picks(node: object) -> object:
    """Doc 29 refinement ②: recompile the search-pick CHOOSE selector to
    the EXISTING 14c ONE_OF asking channel.

    A SEARCH atom whose ``cards`` role is the up-to-one pick
    (``Selector(QConst(1), CHOOSE, …)``) silently resolved the *which card
    did you find* decision through the deterministic 12a first-of-sort
    stand-in (selectors.py) — the measured silent-choice fail-core. ONE_OF
    asks the vocabulary-addressed channel with the Handle-sorted candidate
    list; single-candidate populations auto-fill (§1.4) exactly as the old
    stand-in did, and exhaustion stays loud (C15). QConst(2) picks
    (Cultivate/Alpine Houndmaster) and QUnbounded whole-zone finds are
    NOT rewritten: ONE_OF is exactly-one, so a multi-pick ask is a
    REGISTERED GRAMMAR GAP (doc 29), not something this pass extends.
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
    flipped = _one_of_search_picks(ability)
    if not isinstance(flipped, get_args(Ability)):  # pragma: no cover — invariant
        raise StateCorruptionError(
            "compile_card: search-pick rewrite changed an Ability node type"
        )
    return cast(Ability, flipped)


# T4 P1b stage 2 — the STRUCTURAL PROMOTION RULE (docs/T4_PICK_ENUMERATION.md
# §2'): a QConst(1), referent-less entity CHOOSE selector that sits outside a
# cost and is not an IS_SOURCE self-designation IS a real controller decision
# and is promoted AUTOMATICALLY onto the asking ONE_OF channel (doc-29 lane).
# Future sets need no registration; test_promotion_predicate.py pins the
# per-class census of the rule as the §9/§10 contract. The two frozensets
# below are the only registrations left — documented override escape hatches.
PICK_ASK_FORCE_ASK: frozenset[tuple[str, str]] = frozenset()
#   (card name, effect verb) TRIPWIRE rows — the hatch has no promotion
#   lane and every hit is LOUD by design (review fix 2026-10-07): a hit on
#   a COST or IS_SOURCE self-designation is a stale override and raises
#   StateCorruptionError (r20c mode-gate, enumeration doc §4); a hit on any
#   other predicate-declined near-miss raises NotImplementedError — a
#   referent-bound surface CANNOT ride ONE_OF at all (Selector convention
#   C2), and surfaces whose rules-decider is not the effect controller are
#   gap-ledger L-27 (the ask channel is controller-seat only; provider-seat
#   routing not implemented). Rows on surfaces the structural predicate
#   already lifts are redundant no-ops (the structural branch fires first).
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
        # decision at all — the singleton PLAYER pick auto-fills (§1.4), so
        # the encoded ask is pure phantom (§10).
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
    binding.py exemption for it is CHOOSE-mode-gated (r20c), so lifting one
    silently mis-resolves. Loud raise guards the allowlist instead."""
    if isinstance(filter_, FAtom):
        return filter_.pred is FAtomPred.IS_SOURCE
    if isinstance(filter_, (FAnd, FOr)):
        return any(_filter_carries_is_source(c) for c in filter_.children)
    if isinstance(filter_, FNot):
        return _filter_carries_is_source(filter_.inner)
    return False


def _is_liftable_pick(node: Selector, in_cost: bool) -> bool:
    """THE structural promotion predicate (T4 P1b stage 2 — the tokenizer
    requirement, AGENTS.md §8-§10; census + per-class contract:
    test_promotion_predicate.py). Every axis here is orthogonal (§9):
    {shape} QConst(1) entity CHOOSE with no anaphoric referent (a
    referent-bound pick already follows a binding the 12a lane serves —
    enumeration doc §1: 37 anaphoric surfaces stay), {context} not a cost
    victim (r22a's sacrifice lane already asks; 26 cost surfaces stay),
    {denotation} not an IS_SOURCE self-designation (CR 602.2c — 55
    surfaces, 44% of the census, are NOT decisions, and the r20c binding
    exemption is CHOOSE-mode-gated so flipping one silently mis-resolves,
    enumeration doc §4)."""
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
    """T4 P1b: entity-shape twin of _one_of_search_picks, now driven by the
    STRUCTURAL predicate _is_liftable_pick instead of a card registration
    (stage-2). A matching surface gets the EXISTING 14c ONE_OF asking
    channel: Handle-sorted population, singleton auto-fill (§1.4),
    exhaustion loud (C15). PICK_ASK_FORCE_SILENT exempts surfaces whose ask
    has no answerable lane (gap ledger L-27..L-29); PICK_ASK_FORCE_ASK is a
    loud tripwire only — a hit on the cost/self-designation line raises
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
        shape = (
            node.mode is SelectorMode.CHOOSE
            and node.count == QConst(1)
            and node.referent is None
        )
        if shape and _is_liftable_pick(node, in_cost):
            return replace(node, mode=SelectorMode.ONE_OF)
        # FORCE_ASK tripwire: gated on CHOOSE (not on the predicate's own
        # shape), so a row for the near-miss surface it documents can no
        # longer pass UNSEEN under the shape gate — the old branch only
        # ever reached its guard (shape-complete + declined ⇒ always
        # cost/self-ref), its "promotion" line was unreachable, and the
        # documented referent/count near-miss rows silently no-opped.
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
    """Card-level wrapper for the structural promotion pass (the pass runs
    per-ability; the rule is shape-driven so nothing is counted across
    abilities); type-pinned like _flip_search_picks_in."""
    out: list[Ability] = []
    for ab in abilities:
        promoted = _pick_ask_promotions(ab, name, False, None)
        if not isinstance(promoted, get_args(Ability)):  # pragma: no cover
            raise StateCorruptionError(
                f"compile_card({name}): pick-ask promotion changed node type"
            )
        out.append(cast(Ability, promoted))
    return out


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
    if not isinstance(slot, AbilityOutcome):  # pragma: no cover - defensive
        raise StateCorruptionError(
            "kicker fold: unmergeable slot " + type(slot).__name__
        )
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
    """ZND-1e engine-gate helper: does this Cost price anything with X
    (a QX amount, or a QBin tree carrying one)? Mirrors the executor's
    legality._cost_has_x — duplicated, not imported, because the compiler
    must not depend on the executor package."""

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
    printed data (ZND-2f, /106). Same oracle id (the face IS this card's
    second face), the face's own name, and ``back_face=None`` so the
    recursive compile_card pass terminates immediately. Pool-level flags
    are cleared: a face is never a token/emblem in its own right (the
    ingest CardFace docstring states the same law)."""
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
        # sentence that compiles today is never re-read here).
        if best_match is None and _is_keyword_line(sentence, raw):
            rr = RuleReminderOutcome(reason="keyword_line")
            rule_reminders.append(rr)
            outcomes.append(rr)
            continue
        if best_match is None:
            hint = _bucket_hint(sentence)
            unparsed.append((sentence, hint))
            outcomes.append(None)
            continue

        # Ambiguity detection
        if len(matches) > 1:
            tids = tuple(m.template.tid for m in matches)
            # Check if outcomes are truly distinct (different type or value)
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
    # A continuation sentence's effect is wrapped in OptionalEffect and
    # appended to the previous sentence's effect Seq.  We search backwards
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
        # the base moves to the Conditional's else_effect).
        if isinstance(outcome, KickerEffectOutcome):
            j: int | None = None
            base: Effect | None = None
            saw_unparsed_base = False
            for jj in range(len(processed) - 1, -1, -1):
                prev = processed[jj]
                if prev is None:
                    # An unmatched sentence: the base clause IS there in
                    # the text, it just compiled to residue.  That failed
                    # clause IS the base — searching past it would attach
                    # the arm to an UNRELATED earlier effect (F2 fix:
                    # the ZND-1 fold law stopped here).
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
                        "compile_card: kicker 'instead' arm has no "
                        "preceding base effect to replace it",
                        context={"sentence": raw.sentences[i]},
                    )
                if outcome.replaces:
                    # F1 fix (supersedes ZND-1 fold law): a REPLACEMENT
                    # arm whose base compiled to residue must NOT fold
                    # standalone — Conditional(WAS_KICKED, then=arm) with
                    # no else encodes "un-kicked → no effect", which is
                    # rules-wrong (un-kicked Roil Eruption still deals 3
                    # damage) and contradicts the register's "base is
                    # residue" (§11).  Leave the arm in the register as
                    # honest residue too: both clauses are uncovered.
                    unparsed.append((raw.sentences[i], _bucket_hint(raw.sentences[i])))
                    continue
                # No mergeable slot. Additive arms fold standalone (the
                # SpellAbility assembly Seq-fold yields the same tree).
                processed.append(
                    EffectOutcome(
                        effect=Conditional(
                            pred=FAtom(pred=FAtomPred.WAS_KICKED),
                            then_effect=outcome.effect,
                        )
                    )
                )
                processed_sentence_idx.append(i)
                continue
            merged = (
                Conditional(
                    pred=FAtom(pred=FAtomPred.WAS_KICKED),
                    then_effect=outcome.effect,
                    else_effect=base,
                )
                if outcome.replaces
                else _append_mandatory_to_seq(
                    base,
                    Conditional(
                        pred=FAtom(pred=FAtomPred.WAS_KICKED),
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
            # Grammar round 11 (R11-1): plain text right after a loyalty
            # bullet is that ability's trailing rules text, not a new card-
            # level spell ability.  Merge it into the loyalty ability's
            # effect (mandatory unless the sentence itself says "may").
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
                        _append_optional_to_seq
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
            # Grammar round 14b (B-11): plain text right after a triggered
            # ability is that ability's effect continuing, not a card-level
            # spell ability — append it to the trigger's effect (mandatory
            # unless the sentence itself says "may", R11-1 may-rule).
            trig_idx = (
                None
                if sentence.lstrip().startswith("[")
                else _trigger_trailing_idx(processed)
            )
            if trig_idx is not None:
                slot = processed[trig_idx]
                tab = slot.ability if isinstance(slot, AbilityOutcome) else None
                if isinstance(tab, TriggeredAbility):
                    # R11-1 may-rule, de-duplicated: a "may" sentence whose
                    # template ALREADY produced an OptionalEffect (Garruk's
                    # Harbinger "You may reveal … and put it into your hand")
                    # must not gain a phantom second wrap — the step is
                    # optional exactly once.
                    merge = (
                        _append_optional_to_seq
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
            # Round 14e (B-17, Tavern Swindler / Waker of Waves / Seasoned
            # Hallowblade): plain text right after a plain activated ability
            # is that ability's activation tail — it runs when the ability
            # resolves, not when the card is cast.  Same may-rule and the
            # same de-dup guard as the trigger tail above; the empty-cost
            # OPT(CAST) permission row is transparent to the ownership scan
            # and loyalty abilities stay R11-1-owned (see
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
                        _append_optional_to_seq
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
        #   - "Otherwise" (grammar round 7, R7-3): else_effect of the last
        #     Conditional, C13 fallback to the default merge.
        #   - "When you do" (grammar round 9, R9-9, C24): inside the prior
        #     cost-paying OptionalEffect, C13 fallback to the default merge.
        #   - "If you do" (r18a, CR 611.1): gated on the may-offer's OUTCOME
        #     (Conditional(MAY_DONE, tail)) when the seam ends in an
        #     OptionalEffect; else the default merge.
        #   - default continuation: a sibling optional step.
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
            # Grammar round 11 (R11-1): a "may"-free continuation ("If you
            # do, do X" / "Then do X") is MANDATORY given its antecedent —
            # the phantom OptionalEffect wrap was a semantics bug (Scavenging
            # Ooze, Fabled Passage).  Only "you may …" sentences stay optional.
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
                            # timing (grammar round 9, R9-1): a continuation
                            # merge must not silently drop the timing window.
                            timing=ab.timing,
                        )
                    )
                elif isinstance(ab, SpellAbility):
                    if ab.effect is None:
                        # Unreachable: the search loop above skips
                        # effect-less SpellAbilities. Consume the
                        # continuation, matching the existing
                        # fall-through for non-mergeable entries.
                        continue
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
        # sentence carries "may" (R11-1) or when it is an orphaned
        # search-shuffle (anaphoric condition can never hold — the
        # never-fires wrap is the safe encoding, prior-round decision),
        # else appended bare/mandatory.
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
    for src, outcome in zip(processed_sentence_idx, processed):
        if isinstance(outcome, AbilityOutcome):
            if _is_result_anaphoric_cast_permission(outcome.ability):
                # C5: the phantom "you may play that card" permission —
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
            # Wrap in a StaticAbility if no better category is apparent.
            # # KNOWN-GAP: token effect categorization is bucket-specific;
            #   for now, StaticAbility is the closest honest wrapper.
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
        # # KNOWN-GAP: land cost extraction is bucket-specific.
        for eff, src in zip(effect_outcomes, effect_src):
            abilities.append(ActivatedAbility(cost=Cost(parts=()), effect=eff))
            ability_srcs.append(src)
    elif is_creature:
        # Creature: always a SpellAbility(CREATURE) — the cast lane.
        # EffectOutcome folds into it when present; a plain creature with
        # no effect sentence still gets an effect-less carrier (effect=None
        # precedent: additional-costs cards, and grammar requires *some*
        # SpellAbility for legality.cast — creatures cast through the SAME
        # lane as instants; C4 roadmap batch 4).
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
            # Determine SpellKind
            if "Instant" in types:
                kind = SpellKind.INSTANT
            elif "Sorcery" in types:
                kind = SpellKind.SORCERY
            elif "Enchantment" in types:
                kind = SpellKind.ENCHANTMENT
            else:
                kind = SpellKind.SORCERY  # fallback
            combined = (
                effect_outcomes[0]
                if len(effect_outcomes) == 1
                else Seq(steps=tuple(effect_outcomes))
            )
            abilities.append(SpellAbility(kind=kind, effect=combined))
            ability_srcs.append(max(effect_src))

    # -- Attach additional costs to the spell --------------------------------
    # Additional-cost sentences ride on a SpellAbility. A card that matched
    # one but compiled without one falls into two cases (T3 round 3):
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
    # ZND-1e (Roost of Drakes): a noncreature spell whose every loaded
    # sentence compiled to a NON-effect ability (bare "Kicker {2}{U}." head
    # + triggered abilities, no effect sentence) assembled no SpellAbility
    # at all — and the cast lane's spell_castable answers
    # ``cast:not_a_spell``, making the card uncastable BY CONSTRUCTION.
    # The kicker head is a cast-time declaration (CR 702.27a: "this spell"
    # may be kicked — it is plainly a spell), so it earns the effect-less
    # carrier exactly as the additional-cost path above (Goremand) and the
    # creature branch do. The fold never fires for cards that already carry
    # a SpellAbility, and M21 has zero KickerAbility nodes — the M21
    # compiled output is byte-unchanged by construction.
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
    # (R10-1, C25) to the nearest preceding ActivatedAbility (source
    # sentence index) whose targeted slot(s) are still free: a window slot
    # requires ``timing is None`` (R9-1, C20), a condition slot requires
    # ``condition is None``; a gate carrying BOTH (Speaker's compound)
    # attaches both. Gates are processed in sentence order; once an
    # ability's needed slot is filled it no longer qualifies for a later
    # gate wanting that slot.
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

    # -- Search-pick observability rewrite (doc 29 refinement ②) -----------
    # Up-to-one SEARCH picks ask the ONE_OF channel instead of resolving
    # silently through the 12a stand-in; see _one_of_search_picks.
    abilities = [_flip_search_picks_in(ab) for ab in abilities]

    # -- PICK-ask promotion (T4 P1b stage 2, structural rule) -----------------
    # Every QConst(1) referent-less non-cost non-self-ref entity CHOOSE
    # asks the ONE_OF channel automatically; see _is_liftable_pick /
    # docs/T4_PICK_ENUMERATION.md.
    abilities = _promote_liftable_picks(abilities, raw.identity.name)

    # -- Back-face fold (ZND-2f, KNOWLEDGE/2026-10-18/106) --------------------
    # A modal double-faced card's back face is the CARD'S OWN second face
    # (§11 zero-loss): its sentences are compiled through the SAME tolerant
    # machinery (a synthetic single-faced RawCard carrying the face's
    # printed data — same split, same templates, same unparsed queue) and
    # the results fold into one BackFace ability node. Unmatched face
    # sentences enter CompileResult.back_face_unparsed — the honest
    # residual register (coverage.py rows them "[face B]"), NEVER counted
    # as covered (the pay-3-life pair is ZND-2f2 residue, /106 amendment 1).
    # The node is ENCODED ONLY: every walk()-consumer verdict gate below
    # skips the BackFace subtree (§10 phantom defense, /106 amendment 3).
    # None for every single-faced card: zero behavior change, M21 bytes
    # untouched.
    back_face_unparsed: tuple[tuple[str, str], ...] = ()
    if raw.back_face is not None:
        # Gate F1 (/106 review): the face field surface was UNREACHABLE code
        # until this wave; a malformed face (bad type_line/loyalty) must
        # degrade to face-unparsed — it may NEVER crash the pool pass or
        # sacrifice the playable FRONT card.
        try:
            face_result = compile_card(_as_single_faced(raw), registry)
        except (ValueError, StateCorruptionError):
            face_result = None
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
    # B-37: a Vehicle prints P/T on a non-creature artifact; it is a creature only while crewed
    # (CR 301.7), and crew is not implemented. CardRecord rejects P/T on a non-creature with a
    # ValueError that is not an honest refusal and took down whole-set compiles (KHM, THB), so
    # refuse the shape here: the card becomes a shape gap, counted against coverage.
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

    # -- Star P/T coverage check ----------------------------------------------
    # If power or toughness was '*' (→ None from parse_pt), check that a
    # SET_PT or MODIFY_PT verb exists somewhere in the compiled tree.
    # # KNOWN-GAP: when no template produced such an atom the card's P/T is
    #   dynamic but uncovered — a template-coverage gap, not data corruption
    #   (the data itself is sound). Report it; power/toughness stay None
    #   (= "resolve at runtime"). M21 has exactly two such cards: Weird and
    #   Kinetic Augur.
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
            known_gaps.append(
                f"star P/T: {'/'.join(star_fields)} is '*' but no SET_PT/MODIFY_PT "
                f"ability found in compiled text (template coverage gap)"
            )

    # -- Engine support check ------------------------------------------------
    if supported_verbs is None:
        engine_supported = True
    else:
        engine_supported = True
        # ZND-2f §3 (phantom defense, /106 amendment 3): the BackFace
        # subtree is EXCLUDED — the engine never plays a face (owner-gated,
        # spec §6), so a face-only verb must never flip a front-face-
        # supported card's verdict (and a face-unsupported verb must never
        # silently drop a front-face-supported card from engine supply).
        for node in walk(card, skip=BackFace):
            if isinstance(node, Atom) and node.verb not in supported_verbs:
                engine_supported = False
                break
        # ZND-1e SHAPE gates (the verb-only fold was dishonest for the
        # kicker family: it marked 41 of ZNR's 42 kicker cards supported
        # while the executor raised on every gated lane). The delivered
        # lanes — KickerAbility priced into the cast, WAS_KICKED read
        # from the CAST journal row, gated EtBState with constant
        # counters — stay SUPPORTED; what remains unplayable is marked
        # unsupported here, honestly:
        #   * an X-kicker ({X} in the optional cost): no producer wires
        #     the kick choice to an X declaration (deferred, /95);
        #   * a gated EtBState whose counters are not constants: the
        #     engine's entering-state stamp is QConst-only.
        if engine_supported:
            for node in walk(card, skip=BackFace):
                if isinstance(node, KickerAbility) and _cost_has_x_quantity(node.cost):
                    engine_supported = False
                    break
                if (
                    isinstance(node, EtBState)
                    and node.condition is not None
                    and any(
                        not isinstance(qty, QConst)
                        for _kind, qty in node.initial_counters
                    )
                ):
                    engine_supported = False
                    break

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
) -> PoolCompile:
    """Compile an entire pool (oracle_id → RawCard).

    Emblems are compiled and attached to their owner CardRecord via
    ``related_names``.  Emblems are excluded from the standalone ``cards``
    dict.  Missing owners become ``orphan_emblems``.

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
        results[oid] = compile_card(raw, registry, supported_verbs)

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
            # B-38: an owner whose planeswalker is its BACK face (KHM Valki, God of Lies //
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
        # ZND-2f: back-face residue is honest residue — a card whose only
        # unparsed text is its face is NOT fully compiled.
        if not (result.unparsed or result.ambiguities or result.back_face_unparsed):
            fully_compiled += 1
        else:
            partially_compiled += 1
        ambiguity_count += len(result.ambiguities)
        unparsed_count += len(result.unparsed) + len(result.back_face_unparsed)
        known_gap_count += len(result.known_gaps)

        # ZND-2f §3: the pool verb histogram stays FRONT-ONLY (face verbs
        # are census-tagged in coverage.py's backface summary, never
        # merged untagged here).
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
