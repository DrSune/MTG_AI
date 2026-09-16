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
from dataclasses import dataclass, replace
from typing import Any

from MTG_bot.core.ability_tree import (
    Ability,
    ActivatedAbility,
    Atom,
    AtomArgs,
    CardRecord,
    Choose,
    Conditional,
    Cost,
    CostManaColor,
    CostManaGeneric,
    CostManaHybrid,
    CostPart,
    Effect,
    FAnd,
    Filter,
    Keyword,
    KeywordAbility,
    OptionalEffect,
    QConst,
    QX,
    Repeat,
    Selector,
    SelectorMode,
    Seq,
    SpellAbility,
    SpellKind,
    StaticAbility,
    TriggeredAbility,
    Verb,
    walk,
)
from MTG_bot.core.compiler.ingest import RawCard
from MTG_bot.core.compiler.templates import (
    AbilityOutcome,
    AmbiguityRecord,
    EffectOutcome,
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
# # KNOWN-GAP: SCRY/MILL/BATTALION need a Quantity; PROTECTION needs a Filter.
#   The compiler skips them unless a template supplies the params.
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
    "Then ",
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

_KEYWORD_WORDS: frozenset[str] = frozenset(
    kw for kw in _KEYWORD_STRING_TO_ENUM
)
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
    """

    card: CardRecord
    legality: LegalityFlags
    unparsed: tuple[tuple[str, str], ...] = ()
    ambiguities: tuple[AmbiguityRecord, ...] = ()
    rule_reminders: tuple[RuleReminderOutcome, ...] = ()
    known_gaps: tuple[str, ...] = ()


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


def _is_rule_reminder(
    sentence: str, raw: RawCard
) -> RuleReminderOutcome | None:
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


def _is_continuation(sentence: str) -> bool:
    """Check if a sentence starts with a continuation prefix."""
    s = sentence.strip()
    return any(s.startswith(p) for p in _CONTINUATION_PREFIXES)


def _append_optional_to_seq(effect: Effect, inner: Effect) -> Effect:
    """Append ``OptionalEffect(inner)`` to ``effect``'s step sequence.

    ``inner`` is the *unwrapped* continuation effect; this helper applies the
    single ``OptionalEffect`` wrap.  If ``effect`` is not already a ``Seq``, it
    is wrapped into a two-step ``Seq``.
    """
    if isinstance(effect, Seq):
        return Seq(steps=effect.steps + (OptionalEffect(inner),))
    return Seq(steps=(effect, OptionalEffect(inner)))


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
                    new_pairs.append(
                        (role, Selector(value.count, value.mode, new_filter, value.zone))
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
    # Each entry is a SentenceOutcome or None (unparsed).
    outcomes: list[SentenceOutcome | None] = []

    for sentence in raw.sentences:
        # Step 1: rule reminder check
        rr = _is_rule_reminder(sentence, raw)
        if rr is not None:
            rule_reminders.append(rr)
            outcomes.append(rr)
            continue

        # Step 2: template match
        matches = registry.match(sentence)
        best_match = matches[0] if matches else None
        if best_match is None:
            hint = _bucket_hint(sentence)
            unparsed.append((sentence, hint))
            outcomes.append(None)
            continue

        # Ambiguity detection
        if len(matches) > 1:
            tids = tuple(m.template.tid for m in matches)
            # Check if outcomes are truly distinct (different type or value)
            distinct = len({type(m.outcome).__name__ for m in matches}) > 1 or len(
                {repr(m.outcome) for m in matches}
            ) > 1
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

    # -- Handle continuation prefixes ---------------------------------------
    # A continuation sentence's effect is wrapped in OptionalEffect and
    # appended to the previous sentence's effect Seq.  We search backwards
    # in the *processed* list (not the raw outcomes list) so indices stay
    # stable even when earlier continuations consumed entries.
    processed: list[SentenceOutcome | None] = []
    for i, outcome in enumerate(outcomes):
        # Non-effect entries pass through unchanged.
        if outcome is None or not isinstance(outcome, EffectOutcome):
            processed.append(outcome)
            continue

        sentence = raw.sentences[i]
        if not _is_continuation(sentence):
            processed.append(outcome)
            continue

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
                    (StaticAbility, ActivatedAbility, SpellAbility, TriggeredAbility),
                ):
                    prev_idx = j
                    break
                # KeywordAbility / ReplacementAbility: skip, keep searching.
            # KeywordOutcome / MetaOutcome: no effect to merge into; skip.

        if prev_idx is not None:
            prev = processed[prev_idx]
            if isinstance(prev, EffectOutcome):
                merged = _append_optional_to_seq(prev.effect, outcome.effect)
                processed[prev_idx] = EffectOutcome(effect=merged)
            elif isinstance(prev, AbilityOutcome):
                ab = prev.ability
                if isinstance(ab, StaticAbility):
                    merged_eff = _append_optional_to_seq(
                        ab.effect, outcome.effect
                    )
                    processed[prev_idx] = AbilityOutcome(
                        ability=StaticAbility(effect=merged_eff)
                    )
                elif isinstance(ab, ActivatedAbility):
                    merged_eff = _append_optional_to_seq(
                        ab.effect, outcome.effect
                    )
                    processed[prev_idx] = AbilityOutcome(
                        ability=ActivatedAbility(cost=ab.cost, effect=merged_eff)
                    )
                elif isinstance(ab, SpellAbility):
                    merged_eff = _append_optional_to_seq(
                        ab.effect, outcome.effect
                    )
                    processed[prev_idx] = AbilityOutcome(
                        ability=SpellAbility(kind=ab.kind, effect=merged_eff)
                    )
                elif isinstance(ab, TriggeredAbility):
                    merged_eff = _append_optional_to_seq(
                        ab.effect, outcome.effect
                    )
                    processed[prev_idx] = AbilityOutcome(
                        ability=TriggeredAbility(
                            event=ab.event,
                            condition=ab.condition,
                            effect=merged_eff,
                        )
                    )
            # The continuation sentence is consumed — not appended.
            continue

        # No previous effect to attach to: create own OptionalEffect.
        processed.append(EffectOutcome(effect=OptionalEffect(outcome.effect)))

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

    # -- Separate abilities and effects -------------------------------------
    ability_outcomes: list[Ability] = []
    effect_outcomes: list[Effect] = []
    for outcome in processed:
        if isinstance(outcome, AbilityOutcome):
            ability_outcomes.append(outcome.ability)
        elif isinstance(outcome, EffectOutcome):
            effect_outcomes.append(outcome.effect)

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
    abilities.extend(ability_outcomes)

    if is_emblem or is_token:
        # Tokens/emblems: effects become standalone abilities
        # (no SpellAbility for tokens — they're not cast).
        for eff in effect_outcomes:
            # Wrap in a StaticAbility if no better category is apparent.
            # # KNOWN-GAP: token effect categorization is bucket-specific;
            #   for now, StaticAbility is the closest honest wrapper.
            abilities.append(StaticAbility(effect=eff))
    elif is_planeswalker:
        # Planeswalker: effects become SpellAbility (PLANESWALKER)
        if effect_outcomes:
            combined = (
                effect_outcomes[0]
                if len(effect_outcomes) == 1
                else Seq(steps=tuple(effect_outcomes))
            )
            abilities.append(
                SpellAbility(kind=SpellKind.PLANESWALKER, effect=combined)
            )
    elif is_land:
        # Land: effects become ActivatedAbility (free cost if no cost given).
        # # KNOWN-GAP: land cost extraction is bucket-specific.
        for eff in effect_outcomes:
            abilities.append(ActivatedAbility(cost=Cost(parts=()), effect=eff))
    elif is_creature:
        # Creature: EffectOutcome → SpellAbility(CREATURE, effect)
        if effect_outcomes:
            combined = (
                effect_outcomes[0]
                if len(effect_outcomes) == 1
                else Seq(steps=tuple(effect_outcomes))
            )
            abilities.append(
                SpellAbility(kind=SpellKind.CREATURE, effect=combined)
            )
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

    # -- Build CardRecord ----------------------------------------------------
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
    needs_set_pt = (
        (raw.power_raw is not None and raw.power_raw.strip() == "*")
        or (raw.toughness_raw is not None and raw.toughness_raw.strip() == "*")
    )
    if needs_set_pt:
        has_set_pt = False
        for node in walk(card):
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
        for node in walk(card):
            if isinstance(node, Atom) and node.verb not in supported_verbs:
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
            if owner_oid is None:
                orphan_emblems.append(oid)
            else:
                # Rebuild owner's CardRecord with emblem
                owner_result = results[owner_oid]
                owner_card = replace(
                    owner_result.card, emblem=results[oid].card
                )
                results[owner_oid] = replace(
                    owner_result, card=owner_card
                )

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
        if not result.unparsed and not result.ambiguities:
            fully_compiled += 1
        else:
            partially_compiled += 1
        ambiguity_count += len(result.ambiguities)
        unparsed_count += len(result.unparsed)
        known_gap_count += len(result.known_gaps)

        for node in walk(result.card):
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
