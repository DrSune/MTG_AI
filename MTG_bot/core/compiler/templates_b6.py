"""B6 bucket templates — the ZNR KICKER family (grammar round 19).

Kicker is a {cost-variant} axis (owner decision 2026-10-18, /94): the head
sentence declares an OPTIONAL extra cast cost (``KickerAbility`` — NOT a
CostModifier, the printed cost is never raised); every effect the kicker
gates reuses the SAME components the base spell/etb/trigger already use,
connected only through the contextual ``FAtomPred.WAS_KICKED`` predicate.
Cost and effect never fuse into one atom (§9 axis orthogonality).

Shapes covered (sentences as they appear in the committed 2026-10-18
work register, ``reports/grammar_2026-10-18.json``):

- Kicker heads: ``Kicker {2}{U} (You may pay an additional {2}{U} as you
  cast this spell.)``, bare ``Kicker {2}{G}`` / ``Kicker {X}.`` — one
  family template; the parenthetical must MIRROR the cost via a
  ``(?P=cost)`` backreference so a non-mirroring paren leaves the
  sentence unmatched (never mis-parsed): PC-3 pairwise-disjoint law.
- Conditional entering states: ``If this creature was kicked, it enters
  with two +1/+1 counters on it.`` → ``EtBState(condition=WAS_KICKED)``.
- Conditional ETB triggers: ``When this <noun> enters, if it was kicked,
  <effect>.`` → TriggeredAbility(condition=WAS_KICKED).
- Cast triggers: ``Whenever you cast a kicked spell, <effect>.`` →
  CastSpellEvent(filter=WAS_KICKED, actor=you).
- Spell-effect kicker arms: ``If this spell was kicked, <effect>.``
  (additive), ``… instead <effect>.`` / ``… <effect> instead.``
  (replacement) → KickerEffectOutcome, folded by the compiler onto the
  base spell effect (additive: Seq-append of the gated arm; replaces:
  the arm wins and the base moves to the Conditional's else_effect).

UNCOVERED on purpose (gap ledger 2026-10-18, honest residue):
- ``…choose any number instead.`` (Inscription ×3 — replaces the base X
  chooser, not an effect arm) and ``…two basic land cards instead of
  one.`` (quantity-only replacement, no M21 idiom).
- ``…each opponent mills half their library, rounded up.`` / ``loses
  half their life`` — no HALF quantity in the grammar.
- ``copy that spell twice instead`` (Sea Gate Stormcaller, trigger-
  internal kick test), Jace copy-exception token, ``has base power and
  toughness 5/5`` (no BASE_PT atom), ``those creatures get +2/+1``
  (whole-set anaphor of a static grant — no plural referent),
  ``…with a kicker ability`` (needs HAS_KICKER), ``all creatures able to
  block target creature this turn do so.`` (Taunting Arbormage —
  MANDATE_BLOCK is subject-scoped {cards}+{controller}+{duration} only
  (R6-5) and the 16c executor enforces CR 509.1h "must be blocked if
  able", never the inverted CR 509.1b block-the-designated-creature
  reading: a blocked-side {target} role would be un-executable), Verazol
  remove-counters + copy ("If you do" chain after a trigger), mana-policy
  and cost-reduction sentences, ``X can't be 0.``, per-for-each counter
  counts (no NONBASIC filter / per-each count), ``…with mana value X or
  less`` tails (no X-binding), copy-of-this-artifact tokens (no TokenSpec
  copy source).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Final

from MTG_bot.core.ability_tree import (
    Atom,
    AtomArgs,
    CastSpellEvent,
    ControllerRef,
    Cost,
    CounterKind,
    DurationEot,
    Effect,
    EtBState,
    FAnd,
    FAtom,
    FAtomPred,
    FOr,
    Keyword,
    KeywordAbility,
    KickerAbility,
    PtDelta,
    PtDirection,
    QAtMost,
    QConst,
    QUnbounded,
    Selector,
    SelectorMode,
    Seq,
    TokenSpec,
    TriggeredAbility,
    Verb,
    Zone,
    ZoneChangeEvent,
    ZoneKind,
)
from MTG_bot.core.compiler.templates import (
    AbilityOutcome,
    KickerEffectOutcome,
    SentenceOutcome,
    Template,
)

_BUCKET: Final = "B6"
_PRIORITY: Final[int] = 110  # above every existing bucket: kicker heads and
# kicker-gated tails are concrete sentences no other module claims.


# ---------------------------------------------------------------------------
# Shared builders
# ---------------------------------------------------------------------------


def _template(tid: str, name: str, pattern: str, build) -> Template:
    return Template(
        tid=tid,
        name=name,
        bucket=_BUCKET,
        pattern=re.compile(pattern),
        priority=_PRIORITY,
        build=build,
    )


def _kicked() -> FAtom:
    """``if it/this spell was kicked`` — contextual pred, no slots."""
    return FAtom(pred=FAtomPred.WAS_KICKED)


def _etb_event() -> ZoneChangeEvent:
    """``When this <permanent> enters`` — class-A self anchor (b2b R11-B
    convention: subject is FAtom(IS_SOURCE))."""
    return ZoneChangeEvent(
        from_zone=Zone(ZoneKind.ANY, ControllerRef.ANY),
        to_zone=Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU),
        subject=FAtom(pred=FAtomPred.IS_SOURCE),
    )


def _self_selector() -> Selector:
    return Selector(
        QConst(1),
        SelectorMode.CHOOSE,
        FAtom(pred=FAtomPred.IS_SOURCE),
        Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),
    )


def _referent_target_creature() -> Selector:
    """``that creature`` / ``enchanted creature`` — R7-1 referent="target"
    neutral-zone convention (B5c untap-that-creature idiom)."""
    return Selector(
        QConst(1),
        SelectorMode.CHOOSE,
        FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
        Zone(kind=ZoneKind.ANY, controller=ControllerRef.ANY),
        referent="target",
    )


def _up_to_two_target_creatures() -> Selector:
    return Selector(
        QAtMost(2),
        SelectorMode.TARGET,
        FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
        Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),
    )


def _up_to_one_other_target_creature() -> Selector:
    """``up to one other target creature`` — "other" is the lossy
    distinct-target convention (b5c: IS_ANY_TARGET never re-targets self
    in practice; b5c ``another target`` precedent)."""
    return Selector(
        QAtMost(1),
        SelectorMode.TARGET,
        FAnd(
            children=(
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                FAtom(pred=FAtomPred.IS_ANY_TARGET),
            )
        ),
        Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),
    )


def _creatures_you_control() -> Selector:
    return Selector(
        QUnbounded(),
        SelectorMode.ALL,
        FAnd(
            children=(
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
            )
        ),
        Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),
    )


def _all_creatures() -> Selector:
    return Selector(
        QUnbounded(),
        SelectorMode.ALL,
        FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
        Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),
    )


def _any_target() -> Selector:
    """CR 109.5 ``any target`` — the exact r17-2 three-branch shape
    (templates_b2a._any_target) so the engine's any-target widening
    recognizes it."""
    return Selector(
        QConst(1),
        SelectorMode.TARGET,
        FOr(
            (
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Planeswalker"),
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Player"),
            )
        ),
        Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),
    )


def _drake_token() -> Atom:
    """``create a 2/2 blue Drake creature token with flying.`` — b5c
    TokenSpec idiom (name/type_line/types/subtypes/power/toughness/
    keywords/color)."""
    return Atom(
        verb=Verb.CREATE_TOKEN,
        args=AtomArgs(
            pairs=(
                (
                    "tokens",
                    TokenSpec(
                        name="Drake",
                        type_line="Creature — Drake",
                        types=("Creature",),
                        subtypes=("Drake",),
                        power=QConst(2),
                        toughness=QConst(2),
                        keywords=(Keyword.FLYING,),
                        abilities=(),
                        color="U",
                    ),
                ),
                ("count", QConst(1)),
            )
        ),
    )


def _draw_then_discard() -> Seq:
    """``draw a card, then discard a card.`` — DRAW (b5a shape) followed by
    DISCARD with the canonical b3 hand-chooser ``cards`` role."""
    return Seq(
        steps=(
            Atom(
                verb=Verb.DRAW,
                args=AtomArgs(
                    pairs=(
                        ("controller", ControllerRef.YOU),
                        ("amount", QConst(1)),
                    )
                ),
            ),
            Atom(
                verb=Verb.DISCARD,
                args=AtomArgs(
                    pairs=(
                        ("controller", ControllerRef.YOU),
                        (
                            "cards",
                            Selector(
                                count=QConst(1),
                                mode=SelectorMode.CHOOSE,
                                filter=FAnd(children=()),
                                zone=Zone(
                                    kind=ZoneKind.HAND, controller=ControllerRef.YOU
                                ),
                            ),
                        ),
                    )
                ),
            ),
        )
    )


def _put_counter_self(kind_count: int = 1) -> Atom:
    return Atom(
        verb=Verb.PUT_COUNTER,
        args=AtomArgs(
            pairs=(
                ("target", _self_selector()),
                ("counter_kind", CounterKind.PLUS_1_PLUS_1),
                ("count", QConst(kind_count)),
            )
        ),
    )


def _gain_life(amount: int) -> Atom:
    return Atom(
        verb=Verb.GAIN_LIFE,
        args=AtomArgs(
            pairs=(
                ("controller", ControllerRef.YOU),
                ("amount", QConst(amount)),
            )
        ),
    )


def _scry(amount: int) -> Atom:
    """``scry 2.`` — the b5b SCR atom shape (controller + count)."""
    return Atom(
        verb=Verb.SCRY,
        args=AtomArgs(
            pairs=(
                ("controller", ControllerRef.YOU),
                ("count", QConst(amount)),
            )
        ),
    )


# ---------------------------------------------------------------------------
# Kicker tail effect table — tail sentence -> Effect builder.
#
# Every tail here is an effect sentence whose shape is already proven in an
# M21 bucket; B6 re-derives the atom from the SAME idioms (shapes copied
# from templates_b5b/b5c/b4 builders). The tail table + the family patterns
# below are kept concrete so an unmapped ZNR tail stays UNPARSED (honest
# gap) instead of being folded from a guessed shape.
# ---------------------------------------------------------------------------

_TAIL_DRAKE = "create a 2/2 blue Drake creature token with flying."
_TAIL_TAP2 = "tap up to two target creatures."
_TAIL_REVEAL6 = "reveal the top six cards of your library."
_TAIL_RETURN_OTHER_HAND = "return up to one other target creature to its owner's hand."
_TAIL_RETURN_IS_HAND = (
    "return target instant or sorcery card from your graveyard to your hand."
)
_TAIL_RETURN_CREATURE_BF = (
    "return target creature card from your graveyard to the battlefield."
)
_TAIL_HASTE = "it gains haste until end of turn."
_TAIL_TAP_ENCHANTED = "tap enchanted creature."


def _tap2() -> Atom:
    return Atom(
        verb=Verb.TAP, args=AtomArgs(pairs=(("target", _up_to_two_target_creatures()),))
    )


def _reveal_top_six() -> Atom:
    """b5b reveal idiom: controller + count (top-of-library provenance is
    the M21 lossy convention for reveal counts)."""
    return Atom(
        verb=Verb.REVEAL,
        args=AtomArgs(
            pairs=(
                ("controller", ControllerRef.YOU),
                ("count", QConst(6)),
            )
        ),
    )


def _return_other_to_owner_hand() -> Atom:
    return Atom(
        verb=Verb.MOVE_ZONE,
        args=AtomArgs(
            pairs=(
                ("cards", _up_to_one_other_target_creature()),
                (
                    "destination",
                    Zone(kind=ZoneKind.HAND, controller=ControllerRef.OWNER),
                ),
            )
        ),
    )


def _return_instant_or_sorcery_hand() -> Atom:
    return Atom(
        verb=Verb.MOVE_ZONE,
        args=AtomArgs(
            pairs=(
                (
                    "cards",
                    Selector(
                        QConst(1),
                        SelectorMode.TARGET,
                        FOr(
                            children=(
                                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Instant"),
                                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Sorcery"),
                            )
                        ),
                        Zone(kind=ZoneKind.GRAVEYARD, controller=ControllerRef.YOU),
                    ),
                ),
                ("destination", Zone(kind=ZoneKind.HAND, controller=ControllerRef.YOU)),
            )
        ),
    )


def _return_creature_to_battlefield() -> Atom:
    """b5b ``return target creature card from your graveyard to the
    battlefield`` atom (B5b-return-creatures-battlefield shape)."""
    return Atom(
        verb=Verb.MOVE_ZONE,
        args=AtomArgs(
            pairs=(
                (
                    "cards",
                    Selector(
                        QConst(1),
                        SelectorMode.TARGET,
                        FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                        Zone(kind=ZoneKind.GRAVEYARD, controller=ControllerRef.YOU),
                    ),
                ),
                (
                    "destination",
                    Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),
                ),
            )
        ),
    )


def _it_gains_haste_eot() -> Atom:
    """ETB-trigger ``it`` = the entering permanent = the source (class-A
    self reference — b5c ``this creature`` convention)."""
    return Atom(
        verb=Verb.GRANT_ABILITY,
        args=AtomArgs(
            pairs=(
                ("target", _self_selector()),
                ("ability", KeywordAbility(keyword=Keyword.HASTE)),
                ("duration", DurationEot()),
            )
        ),
    )


def _tap_enchanted() -> Atom:
    return Atom(
        verb=Verb.TAP, args=AtomArgs(pairs=(("target", _referent_target_creature()),))
    )


def _draw_a_card() -> Atom:
    return Atom(
        verb=Verb.DRAW,
        args=AtomArgs(
            pairs=(
                ("controller", ControllerRef.YOU),
                ("amount", QConst(1)),
            )
        ),
    )


def _put_two_counters_each_you_control() -> Atom:
    return Atom(
        verb=Verb.PUT_COUNTER,
        args=AtomArgs(
            pairs=(
                ("target", _creatures_you_control()),
                ("counter_kind", CounterKind.PLUS_1_PLUS_1),
                ("count", QConst(2)),
            )
        ),
    )


def _that_creature_gains_hexproof() -> Atom:
    """Spell-target anaphor: ``that creature`` = referent="target" (R7-1)."""
    return Atom(
        verb=Verb.GRANT_ABILITY,
        args=AtomArgs(
            pairs=(
                ("target", _referent_target_creature()),
                ("ability", KeywordAbility(keyword=Keyword.HEXPROOF)),
                ("duration", DurationEot()),
            )
        ),
    )


def _destroy_cw_pw() -> Atom:
    return Atom(
        verb=Verb.DESTROY,
        args=AtomArgs(
            pairs=(
                (
                    "target",
                    Selector(
                        QConst(1),
                        SelectorMode.TARGET,
                        FOr(
                            children=(
                                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                                FAtom(
                                    pred=FAtomPred.TYPE_EQ, string_value="Planeswalker"
                                ),
                            )
                        ),
                        Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),
                    ),
                ),
            )
        ),
    )


def _draw_three() -> Atom:
    return Atom(
        verb=Verb.DRAW,
        args=AtomArgs(
            pairs=(
                ("controller", ControllerRef.YOU),
                ("amount", QConst(3)),
            )
        ),
    )


def _deals_5_any() -> Atom:
    return Atom(
        verb=Verb.DEAL_DAMAGE,
        args=AtomArgs(
            pairs=(
                ("target", _any_target()),
                ("amount", QConst(5)),
            )
        ),
    )


def _deals_2_each_creature() -> Atom:
    return Atom(
        verb=Verb.DEAL_DAMAGE,
        args=AtomArgs(
            pairs=(
                ("target", _all_creatures()),
                ("amount", QConst(2)),
            )
        ),
    )


def _that_creature_5_5_eot() -> Atom:
    return Atom(
        verb=Verb.MODIFY_PT,
        args=AtomArgs(
            pairs=(
                ("target", _referent_target_creature()),
                ("power", PtDelta(PtDirection.INCREASE, QConst(5))),
                ("toughness", PtDelta(PtDirection.INCREASE, QConst(5))),
                ("duration", DurationEot()),
            )
        ),
    )


def _return_two_creature_cards_hand() -> Atom:
    return Atom(
        verb=Verb.MOVE_ZONE,
        args=AtomArgs(
            pairs=(
                (
                    "cards",
                    Selector(
                        QConst(2),
                        SelectorMode.TARGET,
                        FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                        Zone(kind=ZoneKind.GRAVEYARD, controller=ControllerRef.YOU),
                    ),
                ),
                ("destination", Zone(kind=ZoneKind.HAND, controller=ControllerRef.YOU)),
            )
        ),
    )


_TAIL_BUILDERS: dict[str, Callable[[], Effect]] = {
    # effect tails shared by the ETB-trigger and cast-trigger families and
    # by the class-E spell arms — one encoding per tail, every consumer
    # reuses it (§9 shared-atom law).
    _TAIL_DRAKE: _drake_token,
    _TAIL_TAP2: _tap2,
    _TAIL_REVEAL6: _reveal_top_six,
    _TAIL_RETURN_OTHER_HAND: _return_other_to_owner_hand,
    _TAIL_RETURN_IS_HAND: _return_instant_or_sorcery_hand,
    _TAIL_RETURN_CREATURE_BF: _return_creature_to_battlefield,
    _TAIL_HASTE: _it_gains_haste_eot,
    _TAIL_TAP_ENCHANTED: _tap_enchanted,
    "you gain 2 life.": lambda: _gain_life(2),
    "scry 2.": lambda: _scry(2),
    "put a +1/+1 counter on this creature.": lambda: _put_counter_self(1),
    "draw a card, then discard a card.": _draw_then_discard,
    "draw a card.": _draw_a_card,
    "put two +1/+1 counters on each creature you control.": (
        _put_two_counters_each_you_control
    ),
    "that creature also gains hexproof until end of turn.": (
        _that_creature_gains_hexproof
    ),
    "destroy target creature or planeswalker.": _destroy_cw_pw,
    "draw three cards.": _draw_three,
    "it deals 5 damage.": _deals_5_any,
    "it deals 2 damage to each creature.": _deals_2_each_creature,
    "that creature gets +5/+5 until end of turn.": _that_creature_5_5_eot,
    "return two target creature cards from your graveyard to your hand.": (
        _return_two_creature_cards_hand
    ),
}


def _alts_suffix(tails: list[str]) -> str:
    """Same as ``_alts`` but WITHOUT each tail's terminal period — inside a
    ``…, X instead.`` sentence the period is carried by the "instead."
    ending, not the tail."""
    return "|".join(
        re.escape(t.removesuffix(".")) for t in sorted(tails, key=len, reverse=True)
    )


def _alts(tails: list[str]) -> str:
    """Regex alternation of literal tail sentences, longest-first so no
    tail is a prefix shadow of another."""
    return "|".join(re.escape(t) for t in sorted(tails, key=len, reverse=True))


def _build_tail(tail: str) -> Effect:
    # The instead-SUFFIX captures the tail without its terminal period
    # (the "instead." carries it) — accept both spellings.
    fn = _TAIL_BUILDERS.get(tail) or _TAIL_BUILDERS.get(tail + ".")
    if fn is None:  # pragma: no cover - pattern and table share the list
        raise KeyError(f"unmapped kicker tail: {tail!r}")
    return fn()


# ---------------------------------------------------------------------------
# 1. Kicker heads
# ---------------------------------------------------------------------------


def _parse_kicker_cost(raw: str) -> Cost:
    # Lazy import: templates_b6 is registered by coverage.py, which the
    # compiler imports later; the build() runs at compile time only.
    from MTG_bot.core.compiler.compiler import (
        StateCorruptionError,
        parse_mana_cost,
    )

    cost = parse_mana_cost(raw)
    if cost is None:
        # parse_mana_cost returns None only for None/empty input; the
        # template's cost group can only match a non-empty {…} string.
        raise StateCorruptionError(f"_parse_kicker_cost: empty kicker cost {raw!r}")
    return cost


def _build_kicker_head(m: re.Match[str]) -> SentenceOutcome:
    return AbilityOutcome(
        ability=KickerAbility(cost=_parse_kicker_cost(m.group("cost")))
    )


# ---------------------------------------------------------------------------
# 2. Conditional entering states
# ---------------------------------------------------------------------------

_WORD_COUNT = {"a": 1, "one": 1, "two": 2, "three": 3, "four": 4}


def _build_kicker_etb_counters(m: re.Match[str]) -> SentenceOutcome:
    n = _WORD_COUNT[m.group("n")]
    return AbilityOutcome(
        ability=EtBState(
            initial_counters=((CounterKind.PLUS_1_PLUS_1, QConst(n)),),
            condition=_kicked(),
        )
    )


# ---------------------------------------------------------------------------
# 3-4. Kicker-gated triggers
# ---------------------------------------------------------------------------


def _build_etb_kicked_trigger(m: re.Match[str]) -> SentenceOutcome:
    return AbilityOutcome(
        ability=TriggeredAbility(
            event=_etb_event(),
            condition=_kicked(),
            effect=_build_tail(m.group("tail")),
        )
    )


def _build_cast_kicked_trigger(m: re.Match[str]) -> SentenceOutcome:
    return AbilityOutcome(
        ability=TriggeredAbility(
            event=CastSpellEvent(
                filter=_kicked(),
                actor=FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
            ),
            condition=None,
            effect=_build_tail(m.group("tail")),
        )
    )


# ---------------------------------------------------------------------------
# 5-7. Kicker spell-effect arms (folded by the compiler)
# ---------------------------------------------------------------------------


def _build_kicker_additive(m: re.Match[str]) -> SentenceOutcome:
    return KickerEffectOutcome(effect=_build_tail(m.group("tail")), replaces=False)


def _build_kicker_replaces(m: re.Match[str]) -> SentenceOutcome:
    return KickerEffectOutcome(effect=_build_tail(m.group("tail")), replaces=True)


_ETB_TAILS = [
    _TAIL_DRAKE,
    _TAIL_TAP2,
    _TAIL_REVEAL6,
    _TAIL_RETURN_OTHER_HAND,
    _TAIL_RETURN_IS_HAND,
    _TAIL_RETURN_CREATURE_BF,
    _TAIL_HASTE,
    _TAIL_TAP_ENCHANTED,
]
_CAST_TAILS = [
    "you gain 2 life.",
    "scry 2.",
    "put a +1/+1 counter on this creature.",
    "draw a card, then discard a card.",
    _TAIL_DRAKE,
]
_ADDITIVE_TAILS = [
    "draw a card.",
    "put two +1/+1 counters on each creature you control.",
    "that creature also gains hexproof until end of turn.",
]
_INSTEAD_PREFIX_TAILS = [
    "destroy target creature or planeswalker.",
    "return two target creature cards from your graveyard to your hand.",
]
_INSTEAD_SUFFIX_TAILS = [
    "draw three cards.",
    "it deals 5 damage.",
    "it deals 2 damage to each creature.",
    "that creature gets +5/+5 until end of turn.",
]

TEMPLATES: tuple[Template, ...] = (
    _template(
        "B6-kicker-head",
        "kicker cost head (paren mirrors the cost by backreference)",
        r"^Kicker (?P<cost>(?:\{[^{}]+\})+)"
        r"(?: \(You may pay an additional (?P=cost) as you cast this spell\.\))?\.?$",
        _build_kicker_head,
    ),
    _template(
        "B6-kicker-etb-counters",
        "if kicked, enters with N +1/+1 counters (gated EtBState)",
        r"^If this creature was kicked, it enters with "
        r"(?P<n>a|one|two|three|four) \+1/\+1 counters? on it\.$",
        _build_kicker_etb_counters,
    ),
    _template(
        "B6-etb-kicked-trigger",
        "When this <permanent> enters, if it was kicked, <effect>",
        r"^When this (?:creature|enchantment|artifact|Aura|planeswalker|land|token) "
        r"enters, if it was kicked, (?P<tail>" + _alts(_ETB_TAILS) + r")$",
        _build_etb_kicked_trigger,
    ),
    _template(
        "B6-cast-kicked-trigger",
        "Whenever you cast a kicked spell, <effect>",
        r"^Whenever you cast a kicked spell, (?P<tail>" + _alts(_CAST_TAILS) + r")$",
        _build_cast_kicked_trigger,
    ),
    _template(
        "B6-kicker-additive",
        "If this spell was kicked, <effect> (additive arm)",
        r"^If this spell was kicked, (?P<tail>" + _alts(_ADDITIVE_TAILS) + r")$",
        _build_kicker_additive,
    ),
    _template(
        "B6-kicker-instead-prefix",
        "If this spell/it was kicked, instead <effect> (replacement arm)",
        r"^If (?:this spell|it) was kicked, instead (?P<tail>"
        + _alts(_INSTEAD_PREFIX_TAILS)
        + r")$",
        _build_kicker_replaces,
    ),
    _template(
        "B6-kicker-instead-suffix",
        "If this spell/it was kicked, <effect> instead (replacement arm)",
        r"^If (?:this spell|it) was kicked, (?P<tail>"
        + _alts_suffix(_INSTEAD_SUFFIX_TAILS)
        + r") instead\.$",
        _build_kicker_replaces,
    ),
)
