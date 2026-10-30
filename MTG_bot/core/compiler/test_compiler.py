"""Tests for the card-assembly compiler (compiler.py).

Covers: mana-cost parsing, P/T parsing, the local bucket classifier,
rule-reminder detection, keyword dedup, continuation folding, meta-filter
conjunction, per-type assembly, star-P/T coverage gaps, engine support,
ambiguity records, pool assembly with emblems, and a real M21.json smoke
test.
"""

from __future__ import annotations

import re
import unittest
from collections.abc import Callable
from pathlib import Path

from MTG_bot.core.ability_tree import (
    QX,
    Ability,
    ActivatedAbility,
    Atom,
    AtomArgs,
    CardRecord,
    Choose,
    Conditional,
    ControllerRef,
    Cost,
    CostDiscard,
    CostLoyalty,
    CostManaColor,
    CostManaGeneric,
    CostManaHybrid,
    CostSacrifice,
    CostTap,
    DeclareAttackersEvent,
    DeclareBlockersEvent,
    DurationUntilNextTurn,
    Effect,
    FAnd,
    FAtom,
    FAtomPred,
    Filter,
    Keyword,
    KeywordAbility,
    OptionalEffect,
    QConst,
    QUnbounded,
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
    canonical_json,
    walk,
)
from MTG_bot.core.compiler.compiler import (
    CompileResult,
    _bucket_hint,
    compile_card,
    compile_pool,
    parse_mana_cost,
    parse_pt,
)
from MTG_bot.core.compiler.coverage import build_full_registry
from MTG_bot.core.compiler.ingest import RawCard, ingest_pool
from MTG_bot.core.compiler.templates import (
    AbilityOutcome,
    ActivationGateOutcome,
    AdditionalCostOutcome,
    EffectOutcome,
    KeywordOutcome,
    MetaOutcome,
    RuleReminderOutcome,
    SentenceOutcome,
    Template,
    TemplateRegistry,
)
from MTG_bot.core.errors import StateCorruptionError
from MTG_bot.core.identity import CardIdentity

# ---------------------------------------------------------------------------
# Synthetic-data helpers
# ---------------------------------------------------------------------------


def _oid(n: int) -> str:
    """A valid lowercase oracle id (identity.validate_oracle_id)."""
    return f"00000000-0000-0000-0000-{n:012d}"


def _raw_card(
    name: str,
    n: int,
    *,
    types: tuple[str, ...] = ("Instant",),
    colors: tuple[str, ...] = (),
    mana_cost_raw: str | None = None,
    mana_value: int = 0,
    power_raw: str | None = None,
    toughness_raw: str | None = None,
    loyalty_raw: str | None = None,
    keywords: tuple[str, ...] = (),
    sentences: tuple[str, ...] = (),
    subtypes: tuple[str, ...] = (),
    is_token: bool = False,
    is_emblem: bool = False,
    related_names: tuple[str, ...] = (),
) -> RawCard:
    return RawCard(
        identity=CardIdentity(oracle_id=_oid(n), name=name),
        type_line=" ".join(types),
        types=types,
        subtypes=subtypes,
        supertypes=(),
        colors=colors,
        color_identity=frozenset(colors),
        mana_cost_raw=mana_cost_raw,
        mana_value=mana_value,
        power_raw=power_raw,
        toughness_raw=toughness_raw,
        loyalty_raw=loyalty_raw,
        keywords=keywords,
        sentences=sentences,
        layout="normal",
        is_token=is_token,
        is_emblem=is_emblem,
        token_name_refs=(),
        related_names=related_names,
    )


def _draw_atom(amount: int = 1) -> Atom:
    return Atom(
        verb=Verb.DRAW,
        args=AtomArgs(
            pairs=(("controller", ControllerRef.YOU), ("amount", QConst(amount)))
        ),
    )


def _add_mana_atom() -> Atom:
    return Atom(
        verb=Verb.ADD_MANA,
        args=AtomArgs(
            pairs=(
                ("controller", ControllerRef.YOU),
                ("amount", QConst(1)),
                ("color", "W"),
            )
        ),
    )


def _target_selector() -> Selector:
    return Selector(
        count=QConst(1),
        mode=SelectorMode.TARGET,
        filter=FAtom(pred=FAtomPred.SUBTYPE_EQ, string_value="creature"),
        zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
    )


def _destroy_atom() -> Atom:
    return Atom(
        verb=Verb.DESTROY, args=AtomArgs(pairs=(("target", _target_selector()),))
    )


def _set_pt_atom() -> Atom:
    return Atom(
        verb=Verb.SET_PT,
        args=AtomArgs(
            pairs=(
                ("target", _target_selector()),
                ("power", QConst(1)),
                ("toughness", QConst(1)),
            )
        ),
    )


def _shuffle_atom() -> Atom:
    """The compiler's canonical search-shuffle boilerplate atom."""
    return Atom(
        verb=Verb.SHUFFLE,
        args=AtomArgs(
            pairs=(("zone", Zone(kind=ZoneKind.LIBRARY, controller=ControllerRef.YOU)),)
        ),
    )


def _search_atom() -> Atom:
    return Atom(
        verb=Verb.SEARCH,
        args=AtomArgs(
            pairs=(
                (
                    "cards",
                    # Doc 29 ②: up-to-one SEARCH picks compile to the ONE_OF
                    # asking channel (was the silent CHOOSE stand-in).
                    Selector(
                        QConst(1),
                        SelectorMode.ONE_OF,
                        FAnd(children=()),
                        zones=(
                            Zone(kind=ZoneKind.LIBRARY, controller=ControllerRef.YOU),
                        ),
                    ),
                ),
                ("destination", Zone(kind=ZoneKind.HAND, controller=ControllerRef.YOU)),
                ("controller", ControllerRef.YOU),
            )
        ),
    )


def _phase_out_atom() -> Atom:
    """A canonical phase-out atom (the mandatory first half of a loyalty
    activation whose creatures must not phase back in)."""
    return Atom(
        verb=Verb.PHASE_OUT,
        args=AtomArgs(pairs=(("target", _target_selector()),)),
    )


def _phase_in_atom() -> Atom:
    """The compiler's canonical phase-in prevention atom.

    Mirrors ``compiler._phase_in_prevention_effect``: prevents the opponent's
    command-zone permanents re-entering the battlefield until the controller's
    next turn.
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


def _template(
    tid: str,
    pattern: str,
    build: Callable[[re.Match[str]], SentenceOutcome],
    priority: int = 1,
) -> Template:
    return Template(
        tid=tid,
        name=tid,
        bucket="B5",
        pattern=re.compile(pattern),
        priority=priority,
        build=build,
    )


# ---------------------------------------------------------------------------
# Pyright narrowing helpers
#
# ``unittest`` assertions do not narrow types for the LSP, so direct
# attribute access on the ``Ability`` / ``Effect`` / ``Filter`` unions is a
# static error. Each helper performs the same runtime check (an
# ``AssertionError`` fails the test and names the actual type) and returns
# the value under its narrowed type, keeping the test bodies readable.
# ---------------------------------------------------------------------------


def _cost(value: Cost | None) -> Cost:
    if value is None:
        raise AssertionError("expected a Cost, got None")
    return value


def _spell(ability: Ability) -> SpellAbility:
    if not isinstance(ability, SpellAbility):
        raise AssertionError(f"expected SpellAbility, got {type(ability).__name__}")
    return ability


def _seq(effect: Effect | None) -> Seq:
    if not isinstance(effect, Seq):
        raise AssertionError(f"expected a Seq, got {type(effect).__name__}")
    return effect


def _choose(effect: Effect | None) -> Choose:
    if not isinstance(effect, Choose):
        raise AssertionError(f"expected a Choose, got {type(effect).__name__}")
    return effect


def _triggered(ability: Ability) -> TriggeredAbility:
    if not isinstance(ability, TriggeredAbility):
        raise AssertionError(f"expected TriggeredAbility, got {type(ability).__name__}")
    return ability


def _atom(effect: Effect | None) -> Atom:
    if not isinstance(effect, Atom):
        raise AssertionError(f"expected Atom, got {type(effect).__name__}")
    return effect


def _selector(value: object) -> Selector:
    if not isinstance(value, Selector):
        raise AssertionError(f"expected Selector, got {type(value).__name__}")
    return value


def _fand(value: Filter) -> FAnd:
    if not isinstance(value, FAnd):
        raise AssertionError(f"expected FAnd, got {type(value).__name__}")
    return value


# ---------------------------------------------------------------------------
# parse_mana_cost
# ---------------------------------------------------------------------------


class TestParseManaCost(unittest.TestCase):
    def test_none_and_empty(self) -> None:
        self.assertIsNone(parse_mana_cost(None))
        self.assertIsNone(parse_mana_cost(""))
        self.assertIsNone(parse_mana_cost("   "))

    def test_single_color(self) -> None:
        cost = _cost(parse_mana_cost("{W}"))
        self.assertEqual(cost.parts, (CostManaColor("W", QConst(1)),))

    def test_multi_token_order(self) -> None:
        cost = _cost(parse_mana_cost("{2}{W}{U}{G}"))
        # R1b canonicalization: Cost.parts construction-sorted by canonical
        # tag (colors alphabetically, then generic) — source order is not kept.
        self.assertEqual(
            cost.parts,
            (
                CostManaColor("G", QConst(1)),
                CostManaColor("U", QConst(1)),
                CostManaColor("W", QConst(1)),
                CostManaGeneric(QConst(2)),
            ),
        )

    def test_generic_x(self) -> None:
        cost = _cost(parse_mana_cost("{X}"))
        self.assertEqual(cost.parts, (CostManaGeneric(QX()),))

    def test_hybrid(self) -> None:
        cost = _cost(parse_mana_cost("{W/U}"))
        self.assertEqual(cost.parts, (CostManaHybrid(("W", "U"), QConst(1)),))

    def test_same_color_hybrid_raises(self) -> None:
        with self.assertRaises(StateCorruptionError) as ctx:
            parse_mana_cost("{W/W}")
        self.assertIn("hybrid", str(ctx.exception))

    def test_split_hybrid_raises_known_gap(self) -> None:
        with self.assertRaises(StateCorruptionError) as ctx:
            parse_mana_cost("{3/W}")
        self.assertIn("KNOWN-GAP", str(ctx.exception))

    def test_unknown_token_raises(self) -> None:
        with self.assertRaises(StateCorruptionError) as ctx:
            parse_mana_cost("{Q}")
        self.assertIn("unknown mana token", str(ctx.exception))

    def test_multi_letter_token_raises(self) -> None:
        with self.assertRaises(StateCorruptionError):
            parse_mana_cost("{GW}")

    def test_non_mana_string_raises(self) -> None:
        with self.assertRaises(StateCorruptionError) as ctx:
            parse_mana_cost("{T}: Add {W}.")
        self.assertIn("not a valid mana-cost string", str(ctx.exception))


# ---------------------------------------------------------------------------
# parse_pt
# ---------------------------------------------------------------------------


class TestParsePt(unittest.TestCase):
    def test_none_and_empty(self) -> None:
        self.assertIsNone(parse_pt(None))
        self.assertIsNone(parse_pt(""))

    def test_star(self) -> None:
        self.assertIsNone(parse_pt("*"))
        self.assertIsNone(parse_pt(" * "))

    def test_digits(self) -> None:
        self.assertEqual(parse_pt("5"), QConst(5))
        self.assertEqual(parse_pt("0"), QConst(0))
        self.assertEqual(parse_pt(" 12 "), QConst(12))

    def test_invalid_raises(self) -> None:
        for bad in ("abc", "1.5", "5/3", "-1"):
            with self.assertRaises(StateCorruptionError, msg=bad):
                parse_pt(bad)


# ---------------------------------------------------------------------------
# _bucket_hint
# ---------------------------------------------------------------------------


class TestBucketHint(unittest.TestCase):
    def test_paren_activated(self) -> None:
        self.assertEqual(_bucket_hint("({T}: Add {W}.)"), "activated")

    def test_paren_prose(self) -> None:
        self.assertEqual(
            _bucket_hint("(Flying means this creature can't be blocked.)"),
            "rule-reminder",
        )

    def test_activated(self) -> None:
        self.assertEqual(
            _bucket_hint("{2}{W}, Sacrifice this creature: Draw a card."),
            "activated",
        )
        self.assertEqual(_bucket_hint("{T}: Draw a card."), "activated")

    def test_triggered(self) -> None:
        self.assertEqual(
            _bucket_hint("When this creature dies, draw a card."), "triggered"
        )
        self.assertEqual(
            _bucket_hint("At the beginning of your end step, draw a card."),
            "triggered",
        )

    def test_static(self) -> None:
        self.assertEqual(_bucket_hint("Creatures you control get +1/+1."), "static")
        self.assertEqual(_bucket_hint("Other creatures can't be blocked."), "static")

    def test_keyword(self) -> None:
        self.assertEqual(_bucket_hint("Flying."), "keyword")

    def test_spell_effect_fallback(self) -> None:
        self.assertEqual(_bucket_hint("Draw a card."), "spell-effect")


# ---------------------------------------------------------------------------
# Rule-reminder detection
# ---------------------------------------------------------------------------


class TestRuleReminder(unittest.TestCase):
    def test_full_paren_reminder(self) -> None:
        raw = _raw_card(
            "R",
            1,
            sentences=("Flying means this creature can't be blocked.",),
            keywords=(),
        )
        # Wrap the sentence in parentheses for the full-paren case.
        raw = _raw_card("R", 1, sentences=("(Flying means x.)",))
        res = compile_card(raw, TemplateRegistry())
        self.assertEqual(res.rule_reminders, (RuleReminderOutcome("full_paren"),))
        self.assertEqual(res.unparsed, ())

    def test_bare_keyword_reminder(self) -> None:
        raw = _raw_card("R", 1, keywords=("Flying",), sentences=("Flying.",))
        res = compile_card(raw, TemplateRegistry())
        self.assertEqual(res.rule_reminders, (RuleReminderOutcome("keyword_reminder"),))
        self.assertEqual(res.unparsed, ())

    def test_paren_activated_is_not_reminder(self) -> None:
        raw = _raw_card(
            "L",
            1,
            types=("Land",),
            sentences=("({T}: Add {W}.)",),
        )
        reg = TemplateRegistry()
        reg.register(
            _template(
                "land-tap",
                r"^\(\{T\}: Add \{W\}\.\)$",
                lambda m: AbilityOutcome(
                    ability=ActivatedAbility(
                        cost=Cost(parts=(CostTap(),)), effect=_add_mana_atom()
                    )
                ),
            )
        )
        res = compile_card(raw, reg)
        self.assertEqual(res.rule_reminders, ())
        self.assertEqual(res.unparsed, ())
        self.assertEqual(
            res.card.abilities,
            (ActivatedAbility(cost=Cost(parts=(CostTap(),)), effect=_add_mana_atom()),),
        )

    def test_qualified_keyword_not_reminder(self) -> None:
        filt = FAtom(pred=FAtomPred.COLOR_HAS, color="B")
        raw = _raw_card(
            "R",
            1,
            keywords=("Hexproof from",),
            sentences=("Hexproof from black.",),
        )
        reg = TemplateRegistry()
        reg.register(
            _template(
                "hexblack",
                r"^Hexproof from black\.$",
                lambda m: KeywordOutcome(keyword=Keyword.HEXPROOF, params=(filt,)),
            )
        )
        res = compile_card(raw, reg)
        self.assertEqual(res.rule_reminders, ())
        self.assertEqual(res.unparsed, ())
        self.assertEqual(
            res.card.keywords, (KeywordAbility(Keyword.HEXPROOF, (filt,)),)
        )


# ---------------------------------------------------------------------------
# Keyword dedup and known gaps
# ---------------------------------------------------------------------------


class TestKeywordDedup(unittest.TestCase):
    def test_identity_and_template_dedup(self) -> None:
        raw = _raw_card(
            "C",
            1,
            types=("Creature", "Card"),
            keywords=("Flying",),
            sentences=("This creature has flying.",),
        )
        reg = TemplateRegistry()
        reg.register(
            _template(
                "flying-sentence",
                r"^This creature has flying\.$",
                lambda m: KeywordOutcome(keyword=Keyword.FLYING, params=()),
            )
        )
        res = compile_card(raw, reg)
        self.assertEqual(res.card.keywords, (KeywordAbility(Keyword.FLYING, ()),))

    def test_parametrized_distinct_from_bare(self) -> None:
        # re-pinned 2026-10-29: m21-fidelity item 1 builds a bare keyword only if the face
        # prints it, so the card now prints both abilities; the dedup still keeps them apart.
        filt = FAtom(pred=FAtomPred.COLOR_HAS, color="B")
        raw = _raw_card(
            "C",
            1,
            types=("Creature", "Card"),
            keywords=("Hexproof",),
            sentences=("Hexproof", "Hexproof from black."),
        )
        reg = TemplateRegistry()
        reg.register(
            _template(
                "hexblack",
                r"^Hexproof from black\.$",
                lambda m: KeywordOutcome(keyword=Keyword.HEXPROOF, params=(filt,)),
            )
        )
        res = compile_card(raw, reg)
        self.assertEqual(
            res.card.keywords,
            (
                KeywordAbility(Keyword.HEXPROOF, ()),
                KeywordAbility(Keyword.HEXPROOF, (filt,)),
            ),
        )

    def test_bare_keyword_needs_the_face_to_print_it(self) -> None:
        # m21-fidelity item 1 (2026-10-29). MTGJSON lists "Hexproof" next to "Hexproof from"
        # for "Hexproof from black" (Garruk's Harbinger): only the variant is printed, so no
        # bare HEXPROOF, which would be full hexproof (CR 702.11b, 702.11d). Likewise a
        # keyword listed for the other face of a modal DFC (CR 712.8f).
        filt = FAtom(pred=FAtomPred.COLOR_HAS, color="B")
        reg = TemplateRegistry()
        reg.register(
            _template(
                "hexblack",
                r"^Hexproof from black$",
                lambda m: KeywordOutcome(keyword=Keyword.HEXPROOF, params=(filt,)),
            )
        )
        harbinger = _raw_card(
            "C",
            1,
            types=("Creature", "Card"),
            keywords=("Hexproof", "Hexproof from"),
            sentences=("Hexproof from black",),
        )
        self.assertEqual(
            compile_card(harbinger, reg).card.keywords,
            (KeywordAbility(Keyword.HEXPROOF, (filt,)),),
        )
        listed_for_other_face = _raw_card(
            "C",
            1,
            types=("Creature", "Card"),
            keywords=("Flying", "Reach"),
            sentences=("Reach (This creature can block creatures with flying.)",),
        )
        self.assertEqual(
            compile_card(listed_for_other_face, TemplateRegistry()).card.keywords,
            (KeywordAbility(Keyword.REACH, ()),),
        )
        keyword_line = _raw_card(
            "C",
            1,
            types=("Creature", "Card"),
            keywords=("First strike", "Lifelink"),
            sentences=("First strike, lifelink",),
        )
        self.assertEqual(
            {ka.keyword for ka in compile_card(keyword_line, TemplateRegistry()).card.keywords},
            {Keyword.FIRST_STRIKE, Keyword.LIFELINK},
        )

    def test_unbuildable_keywords_reported(self) -> None:
        raw = _raw_card("C", 1, types=("Creature", "Card"), keywords=("Scry", "Mill"))
        res = compile_card(raw, TemplateRegistry())
        self.assertEqual(res.card.keywords, ())
        self.assertEqual(len(res.known_gaps), 2)
        self.assertTrue(any("Scry" in g for g in res.known_gaps))
        self.assertTrue(any("Mill" in g for g in res.known_gaps))

    def test_hexproof_from_reported(self) -> None:
        raw = _raw_card("C", 1, types=("Creature", "Card"), keywords=("Hexproof from",))
        res = compile_card(raw, TemplateRegistry())
        self.assertEqual(res.card.keywords, ())
        self.assertTrue(any("Hexproof from" in g for g in res.known_gaps))

    def test_unknown_keyword_ignored(self) -> None:
        raw = _raw_card(
            "C", 1, types=("Creature", "Card"), keywords=("Nonsense Keyword",)
        )
        res = compile_card(raw, TemplateRegistry())
        self.assertEqual(res.card.keywords, ())
        self.assertEqual(res.known_gaps, ())


# ---------------------------------------------------------------------------
# Continuation folding
# ---------------------------------------------------------------------------


def _draw_templates(reg: TemplateRegistry) -> None:
    reg.register(
        _template(
            "draw-one",
            r"^Draw a card\.$",
            lambda m: EffectOutcome(effect=_draw_atom(1)),
        )
    )
    reg.register(
        _template(
            "draw-again",
            r"^If you do, draw another\.$",
            lambda m: EffectOutcome(effect=_draw_atom(2)),
        )
    )


class TestContinuation(unittest.TestCase):
    def test_merges_into_previous_effect(self) -> None:
        raw = _raw_card("I", 1, sentences=("Draw a card.", "If you do, draw another."))
        reg = TemplateRegistry()
        _draw_templates(reg)
        res = compile_card(raw, reg)
        self.assertEqual(res.unparsed, ())
        self.assertEqual(len(res.card.abilities), 1)
        ab = _spell(res.card.abilities[0])
        steps = _seq(ab.effect)
        self.assertEqual(steps.steps[0], _draw_atom(1))
        # R11-1: "If you do, …" without "may" merges MANDATORILY.
        self.assertEqual(steps.steps[1], _draw_atom(2))

    def test_continuation_without_previous_effect(self) -> None:
        raw = _raw_card("I", 1, sentences=("If you do, draw another.",))
        reg = TemplateRegistry()
        _draw_templates(reg)
        res = compile_card(raw, reg)
        ab = _spell(res.card.abilities[0])
        # R11-1: orphaned may-free continuation is appended bare (mandatory),
        # not phantom-wrapped in OptionalEffect.
        self.assertEqual(ab.effect, _draw_atom(2))

    def test_continuation_skips_reminder_and_merges(self) -> None:
        raw = _raw_card(
            "I",
            1,
            keywords=("Flying",),
            sentences=("Draw a card.", "Flying.", "If you do, draw another."),
        )
        reg = TemplateRegistry()
        _draw_templates(reg)
        res = compile_card(raw, reg)
        self.assertEqual(res.rule_reminders, (RuleReminderOutcome("keyword_reminder"),))
        ab = _spell(res.card.abilities[0])
        steps = _seq(ab.effect)
        self.assertEqual(steps.steps[0], _draw_atom(1))
        # R11-1: "If you do, …" without "may" merges MANDATORILY.
        self.assertEqual(steps.steps[1], _draw_atom(2))

    def test_merges_into_previous_ability(self) -> None:
        raw = _raw_card(
            "C",
            1,
            types=("Creature", "Card"),
            sentences=("This creature has an ability.", "If you do, draw a card."),
        )
        reg = TemplateRegistry()
        reg.register(
            _template(
                "static-ab",
                r"^This creature has an ability\.$",
                lambda m: AbilityOutcome(ability=StaticAbility(effect=_draw_atom(1))),
            )
        )
        reg.register(
            _template(
                "cont",
                r"^If you do, draw a card\.$",
                lambda m: EffectOutcome(effect=_draw_atom(2)),
            )
        )
        res = compile_card(raw, reg)
        # The continuation was consumed into the static ability; no spell
        # effect is left to fold (C4: the creature still carries its
        # effect-less cast-lane carrier).
        self.assertEqual(
            res.card.abilities,
            (
                StaticAbility(effect=Seq(steps=(_draw_atom(1), _draw_atom(2)))),
                SpellAbility(kind=SpellKind.CREATURE),
            ),
        )

    def test_may_continuation_stays_optional(self) -> None:
        """R11-1: a continuation carrying "may" KEEPS the OptionalEffect wrap."""
        raw = _raw_card(
            "I",
            1,
            sentences=("Draw a card.", "If you do, you may draw another."),
        )
        reg = TemplateRegistry()
        _draw_templates(reg)
        reg.register(
            _template(
                "cont-may-draw",
                r"^If you do, you may draw another\.$",
                lambda m: EffectOutcome(effect=_draw_atom(2)),
            )
        )
        res = compile_card(raw, reg)
        ab = _spell(res.card.abilities[0])
        steps = _seq(ab.effect)
        self.assertEqual(steps.steps[1], OptionalEffect(_draw_atom(2)))

    def test_loyalty_trailing_text_merges_mandatory(self) -> None:
        """R11-1 (Basri Ket): plain text after a loyalty bullet is that
        ability's trailing rules text — merged into its effect, NOT orphaned
        as a card-level SpellAbility."""
        raw = _raw_card(
            "P",
            1,
            types=("Planeswalker", "Card"),
            loyalty_raw="3",
            sentences=("[+1]: Draw a card.", "You draw another card."),
        )
        reg = TemplateRegistry()
        reg.register(
            _template(
                "loyalty-draw",
                r"^\[\+1\]: Draw a card\.$",
                lambda m: AbilityOutcome(
                    ability=ActivatedAbility(
                        cost=Cost(parts=(CostLoyalty(1),)),
                        effect=_draw_atom(1),
                    )
                ),
            )
        )
        reg.register(
            _template(
                "draw2",
                r"^You draw another card\.$",
                lambda m: EffectOutcome(effect=_draw_atom(2)),
            )
        )
        res = compile_card(raw, reg)
        self.assertEqual(res.unparsed, ())
        # B-49: the planeswalker also trails its effect-less cast carrier. The
        # trailing text did not orphan into it: the carrier has no effect.
        self.assertEqual(len(res.card.abilities), 2)
        self.assertEqual(res.card.abilities[1], SpellAbility(kind=SpellKind.PLANESWALKER))
        ab = res.card.abilities[0]
        if not isinstance(ab, ActivatedAbility):
            self.fail(f"expected ActivatedAbility, got {type(ab).__name__}")
        self.assertEqual(ab.cost, Cost(parts=(CostLoyalty(1),)))
        self.assertEqual(ab.effect, Seq(steps=(_draw_atom(1), _draw_atom(2))))

    def test_loyalty_trailing_may_stays_optional(self) -> None:
        """R11-1: a "may" trailing sentence keeps its optional wrap."""
        raw = _raw_card(
            "P",
            1,
            types=("Planeswalker", "Card"),
            loyalty_raw="3",
            sentences=("[+1]: Draw a card.", "You may draw another card."),
        )
        reg = TemplateRegistry()
        reg.register(
            _template(
                "loyalty-draw",
                r"^\[\+1\]: Draw a card\.$",
                lambda m: AbilityOutcome(
                    ability=ActivatedAbility(
                        cost=Cost(parts=(CostLoyalty(1),)),
                        effect=_draw_atom(1),
                    )
                ),
            )
        )
        reg.register(
            _template(
                "may-draw2",
                r"^You may draw another card\.$",
                lambda m: EffectOutcome(effect=_draw_atom(2)),
            )
        )
        res = compile_card(raw, reg)
        self.assertEqual(res.unparsed, ())
        ab = res.card.abilities[0]
        if not isinstance(ab, ActivatedAbility):
            self.fail(f"expected ActivatedAbility, got {type(ab).__name__}")
        self.assertEqual(
            ab.effect, Seq(steps=(_draw_atom(1), OptionalEffect(_draw_atom(2))))
        )

    def test_search_shuffle_injects_inside_optional_seq(self) -> None:
        """Boilerplate shuffle joins the inner Seq of the previous OptionalEffect.

        "If you search your library this way, shuffle." is compiler-built-in:
        the shuffle is mandatory only if the optional search ran, so it must
        land INSIDE the OptionalEffect, not as a sibling optional step.
        """
        raw = _raw_card(
            "I",
            1,
            sentences=(
                "You may search your library this way.",
                "If you search your library this way, shuffle.",
            ),
        )
        reg = TemplateRegistry()
        reg.register(
            _template(
                "search-opt",
                r"^You may search your library this way\.$",
                lambda m: EffectOutcome(
                    effect=OptionalEffect(Seq(steps=(_draw_atom(1), _draw_atom(2))))
                ),
            )
        )
        res = compile_card(raw, reg)
        self.assertEqual(res.unparsed, ())
        ab = _spell(res.card.abilities[0])
        self.assertEqual(
            ab.effect,
            OptionalEffect(Seq(steps=(_draw_atom(1), _draw_atom(2), _shuffle_atom()))),
        )

    def test_search_shuffle_wraps_single_atom_inner(self) -> None:
        """OptionalEffect(Atom) predecessor (Sanctum of All shape)."""
        raw = _raw_card(
            "I",
            1,
            sentences=(
                "You may search your library this way.",
                "If you search your library this way, shuffle.",
            ),
        )
        reg = TemplateRegistry()
        reg.register(
            _template(
                "search-opt",
                r"^You may search your library this way\.$",
                lambda m: EffectOutcome(effect=OptionalEffect(_search_atom())),
            )
        )
        res = compile_card(raw, reg)
        self.assertEqual(res.unparsed, ())
        ab = _spell(res.card.abilities[0])
        self.assertEqual(
            ab.effect,
            OptionalEffect(Seq(steps=(_search_atom(), _shuffle_atom()))),
        )

    def test_search_shuffle_merges_into_activated_ability(self) -> None:
        """B4 tutor shape: shuffle lands inside the ActivatedAbility's OptionalEffect.

        C4: the creature fixture now also trails the effect-less
        SpellAbility(CREATURE) cast carrier."""
        raw = _raw_card(
            "C",
            1,
            types=("Creature", "Card"),
            sentences=(
                "{2}{U}: You may search your library this way.",
                "If you search your library this way, shuffle.",
            ),
        )
        reg = TemplateRegistry()
        reg.register(
            _template(
                "tutor-opt",
                r"^\{2\}\{U\}: You may search your library this way\.$",
                lambda m: AbilityOutcome(
                    ability=ActivatedAbility(
                        cost=Cost(
                            parts=(
                                CostManaGeneric(QConst(2)),
                                CostManaColor("U", QConst(1)),
                            )
                        ),
                        effect=OptionalEffect(Seq(steps=(_search_atom(),))),
                    )
                ),
            )
        )
        res = compile_card(raw, reg)
        self.assertEqual(res.unparsed, ())
        self.assertEqual(len(res.card.abilities), 2)  # + C4 cast carrier
        ab = res.card.abilities[0]
        if not isinstance(ab, ActivatedAbility):
            self.fail(f"expected ActivatedAbility, got {type(ab).__name__}")
        self.assertEqual(
            ab.cost,
            Cost(parts=(CostManaGeneric(QConst(2)), CostManaColor("U", QConst(1)))),
        )
        self.assertEqual(
            ab.effect,
            OptionalEffect(Seq(steps=(_search_atom(), _shuffle_atom()))),
        )

    def test_search_shuffle_without_previous_effect(self) -> None:
        """Boilerplate with no searchable predecessor: standalone optional shuffle.

        With no preceding optional search the condition can never hold, so
        the generic OptionalEffect wrap is the correct (never-fires) encoding.
        """
        raw = _raw_card(
            "I", 1, sentences=("If you search your library this way, shuffle.",)
        )
        reg = TemplateRegistry()
        res = compile_card(raw, reg)
        self.assertEqual(res.unparsed, ())
        ab = _spell(res.card.abilities[0])
        self.assertEqual(ab.effect, OptionalEffect(_shuffle_atom()))

    def test_phase_in_merges_into_activated_ability(self) -> None:
        """B5c loyalty shape: phase-in prevention is appended MANDATORILY.

        "Until the end of your next turn, they can't phase in." is a
        compiler built-in: it joins the preceding [−N] activation's effect
        Seq without an OptionalEffect wrap (the effect always fires).
        """
        raw = _raw_card(
            "P",
            1,
            types=("Planeswalker", "Card"),
            loyalty_raw="8",
            sentences=(
                "[−8]: Each creature target opponent controls phases out.",
                "Until the end of your next turn, they can't phase in.",
            ),
        )
        reg = TemplateRegistry()
        reg.register(
            _template(
                "loyalty-phase-out",
                r"^\[−8\]: Each creature target opponent controls phases out\.$",
                lambda m: AbilityOutcome(
                    ability=ActivatedAbility(
                        cost=Cost(parts=(CostLoyalty(-8),)),
                        effect=_phase_out_atom(),
                    )
                ),
            )
        )
        res = compile_card(raw, reg)
        self.assertEqual(res.unparsed, ())
        # B-49: + the planeswalker's effect-less cast carrier (no effect, so
        # the phase-in sentence did not land in it).
        self.assertEqual(len(res.card.abilities), 2)
        self.assertEqual(res.card.abilities[1], SpellAbility(kind=SpellKind.PLANESWALKER))
        ab = res.card.abilities[0]
        if not isinstance(ab, ActivatedAbility):
            self.fail(f"expected ActivatedAbility, got {type(ab).__name__}")
        self.assertEqual(ab.cost, Cost(parts=(CostLoyalty(-8),)))
        self.assertEqual(ab.effect, Seq(steps=(_phase_out_atom(), _phase_in_atom())))

    def test_phase_in_merges_into_spell_effect(self) -> None:
        """Instant predecessor: phase-in prevention joins the spell effect Seq."""
        raw = _raw_card(
            "I",
            1,
            sentences=(
                "Each creature target opponent controls phases out.",
                "Until the end of your next turn, they can't phase in.",
            ),
        )
        reg = TemplateRegistry()
        reg.register(
            _template(
                "phase-out",
                r"^Each creature target opponent controls phases out\.$",
                lambda m: EffectOutcome(effect=_phase_out_atom()),
            )
        )
        res = compile_card(raw, reg)
        self.assertEqual(res.unparsed, ())
        ab = _spell(res.card.abilities[0])
        self.assertEqual(ab.effect, Seq(steps=(_phase_out_atom(), _phase_in_atom())))

    def test_phase_in_appends_to_existing_seq(self) -> None:
        """Predecessor already a Seq: phase-in prevention lands as the last step."""
        raw = _raw_card(
            "I",
            1,
            sentences=(
                (
                    "Each creature target opponent controls phases out, "
                    "then you draw a card."
                ),
                "Until the end of your next turn, they can't phase in.",
            ),
        )
        reg = TemplateRegistry()
        reg.register(
            _template(
                "phase-out-draw",
                r"^Each creature target opponent controls phases out, "
                r"then you draw a card\.$",
                lambda m: EffectOutcome(
                    effect=Seq(steps=(_phase_out_atom(), _draw_atom(1)))
                ),
            )
        )
        res = compile_card(raw, reg)
        self.assertEqual(res.unparsed, ())
        ab = _spell(res.card.abilities[0])
        self.assertEqual(
            ab.effect,
            Seq(steps=(_phase_out_atom(), _draw_atom(1), _phase_in_atom())),
        )

    def test_phase_in_without_previous_effect(self) -> None:
        """No predecessor: phase-in prevention stands alone, bare and mandatory.

        Unlike a generic orphaned continuation (wrapped in OptionalEffect),
        a phase-in prevention is a guaranteed effect, so it is appended
        bare — never inside an OptionalEffect.
        """
        raw = _raw_card(
            "I",
            1,
            sentences=("Until the end of your next turn, they can't phase in.",),
        )
        reg = TemplateRegistry()
        res = compile_card(raw, reg)
        self.assertEqual(res.unparsed, ())
        ab = _spell(res.card.abilities[0])
        self.assertEqual(ab.effect, _phase_in_atom())


# ---------------------------------------------------------------------------
# Trigger-tailing (grammar round 14b, B-11)
# ---------------------------------------------------------------------------


def _etb_event() -> ZoneChangeEvent:
    """Synthetic "When this creature enters" event (R11-B subject anchor)."""
    return ZoneChangeEvent(
        from_zone=Zone(ZoneKind.ANY, ControllerRef.ANY),
        to_zone=Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU),
        subject=FAtom(pred=FAtomPred.IS_SOURCE),
    )


class TestTriggerTrailing(unittest.TestCase):
    """Round 14b (B-11, Kitesail Freebooter / Garruk's Harbinger / Siege
    Striker): plain sentences printed under a triggered ability continue
    THAT ability's effect — they used to be orphaned onto the card-level
    SpellAbility and ran at CAST time. Boundary discipline mirrors the
    R11-1 loyalty tail (:func:`compiler._loyalty_trailing_idx`): only
    unparsed slots and rule reminders are skipped; an independently-matched
    sentence (any other outcome) is a group boundary."""

    @staticmethod
    def _etb_trigger_reg(
        tail_effects: dict[str, Effect],
        trigger_effect: Effect | None = None,
    ) -> TemplateRegistry:
        """Registry: one ETB trigger (default effect DRAW 1) plus one
        template per supplied bare tail sentence → its effect."""
        reg = TemplateRegistry()
        reg.register(
            _template(
                "etb-draw",
                r"^When this creature enters, draw a card\.$",
                lambda m: AbilityOutcome(
                    ability=TriggeredAbility(
                        event=_etb_event(),
                        condition=None,
                        effect=trigger_effect
                        if trigger_effect is not None
                        else _draw_atom(1),
                    )
                ),
            )
        )
        for n, (sentence, effect) in enumerate(tail_effects.items()):
            reg.register(
                _template(
                    f"tail-{n}",
                    rf"^{re.escape(sentence)}$",
                    lambda m, e=effect: EffectOutcome(effect=e),
                )
            )
        return reg

    def test_etb_three_sentences_all_owned_by_trigger(self) -> None:
        """Kitesail Freebooter shape: trigger + two bare tails → ONE
        TriggeredAbility whose Seq owns all three atoms; no SpellAbility."""
        raw = _raw_card(
            "C",
            1,
            types=("Creature",),
            power_raw="1",
            toughness_raw="1",
            sentences=(
                "When this creature enters, draw a card.",
                "You draw another card.",
                "It draws a third card.",
            ),
        )
        reg = self._etb_trigger_reg(
            {
                "You draw another card.": _draw_atom(2),
                "It draws a third card.": _draw_atom(3),
            }
        )
        res = compile_card(raw, reg)
        self.assertEqual(res.unparsed, ())
        self.assertEqual(
            res.card.abilities,
            (
                TriggeredAbility(
                    event=_etb_event(),
                    condition=None,
                    effect=Seq(steps=(_draw_atom(1), _draw_atom(2), _draw_atom(3))),
                ),
                # C4: plain creatures carry the effect-less cast lane.
                SpellAbility(kind=SpellKind.CREATURE),
            ),
        )

    def test_cast_trigger_tail(self) -> None:
        """ "When you cast" variant on an instant: the bare tail joins the
        trigger, so nothing is left to fold into a cast-time SpellAbility."""
        raw = _raw_card(
            "I",
            1,
            sentences=(
                "When this creature enters, draw a card.",
                "You draw another card.",
            ),
        )
        reg = self._etb_trigger_reg({"You draw another card.": _draw_atom(2)})
        res = compile_card(raw, reg)
        self.assertEqual(res.unparsed, ())
        self.assertEqual(len(res.card.abilities), 1)
        ab = res.card.abilities[0]
        assert isinstance(ab, TriggeredAbility)
        self.assertEqual(_seq(ab.effect).steps, (_draw_atom(1), _draw_atom(2)))
        self.assertFalse(any(isinstance(a, SpellAbility) for a in res.card.abilities))

    def test_may_tail_wraps_optional_once(self) -> None:
        """R11-1 may-rule: a "may" tail sentence earns an OptionalEffect
        wrap; a bare tail stays mandatory (Garruk's Harbinger shape)."""
        raw = _raw_card(
            "C",
            1,
            types=("Creature",),
            power_raw="1",
            toughness_raw="1",
            sentences=(
                "When this creature enters, draw a card.",
                "You may draw another card.",
                "It draws a third card.",
            ),
        )
        reg = self._etb_trigger_reg(
            {
                "You may draw another card.": _draw_atom(2),
                "It draws a third card.": _draw_atom(3),
            }
        )
        res = compile_card(raw, reg)
        ab = res.card.abilities[0]
        assert isinstance(ab, TriggeredAbility)
        self.assertEqual(
            _seq(ab.effect).steps,
            (_draw_atom(1), OptionalEffect(_draw_atom(2)), _draw_atom(3)),
        )

    def test_may_tail_already_optional_not_double_wrapped(self) -> None:
        """May-rule de-duplication: a "may" tail whose template ALREADY
        produces the OptionalEffect must not gain a phantom second wrap."""
        raw = _raw_card(
            "C",
            1,
            types=("Creature",),
            power_raw="1",
            toughness_raw="1",
            sentences=(
                "When this creature enters, draw a card.",
                "You may draw another card.",
            ),
        )
        reg = self._etb_trigger_reg(
            {"You may draw another card.": OptionalEffect(_draw_atom(2))}
        )
        res = compile_card(raw, reg)
        ab = res.card.abilities[0]
        assert isinstance(ab, TriggeredAbility)
        self.assertEqual(
            _seq(ab.effect).steps,
            (_draw_atom(1), OptionalEffect(_draw_atom(2))),
        )

    def test_otherwise_after_trigger_merges_inside_trigger(self) -> None:
        """Prefix continuations keep their merge paths INSIDE the trigger
        effect: "Otherwise, …" becomes the else_effect of the trigger's own
        Conditional, not a card-level sibling."""
        pred = FAtom(pred=FAtomPred.IS_SOURCE)
        raw = _raw_card(
            "C",
            1,
            types=("Creature",),
            power_raw="1",
            toughness_raw="1",
            sentences=(
                "When this creature enters, draw a card.",
                "Otherwise, draw another card.",
            ),
        )
        reg = self._etb_trigger_reg(
            {"Otherwise, draw another card.": _draw_atom(2)},
            trigger_effect=Conditional(pred=pred, then_effect=_draw_atom(1)),
        )
        res = compile_card(raw, reg)
        self.assertEqual(res.unparsed, ())
        self.assertEqual(
            res.card.abilities,
            (
                TriggeredAbility(
                    event=_etb_event(),
                    condition=None,
                    effect=Conditional(
                        pred=pred,
                        then_effect=_draw_atom(1),
                        else_effect=_draw_atom(2),
                    ),
                ),
                # C4: plain creatures carry the effect-less cast lane.
                SpellAbility(kind=SpellKind.CREATURE),
            ),
        )

    def test_independently_matched_sentence_breaks_the_chain(self) -> None:
        """Negative: an activated-ability sentence after the trigger is its
        own ability (never captured by the TRIGGER), and it is a GROUP
        BOUNDARY — the bare tail is NOT pulled back into the trigger
        (mirror of _loyalty_trailing_idx discipline).

        AMENDED 14e (B-17): the tail's NEW owner is the activation itself
        (activation-tailing capture); the pre-14e reading parked it
        card-level on the SpellAbility (Swindler/Waker/Hallowblade — the
        ruled miscompile). Boundary half unchanged: the trigger still owns
        ONLY its own sentence."""
        raw = _raw_card(
            "C",
            1,
            types=("Creature",),
            power_raw="1",
            toughness_raw="1",
            sentences=(
                "When this creature enters, draw a card.",
                "Tap this creature: Draw two cards.",
                "You draw another card.",
            ),
        )
        reg = self._etb_trigger_reg({"You draw another card.": _draw_atom(3)})
        reg.register(
            _template(
                "tap-draw2",
                r"^Tap this creature: Draw two cards\.$",
                lambda m: AbilityOutcome(
                    ability=ActivatedAbility(
                        cost=Cost(parts=(CostTap(),)),
                        effect=_draw_atom(2),
                    )
                ),
            )
        )
        res = compile_card(raw, reg)
        self.assertEqual(res.unparsed, ())
        trigger, activated, carrier = res.card.abilities  # + C4 cast carrier
        assert isinstance(trigger, TriggeredAbility)
        assert isinstance(activated, ActivatedAbility)
        assert isinstance(carrier, SpellAbility)
        self.assertIsNone(carrier.effect)  # effect-less CREATURE carrier
        # The trigger owns ONLY its own sentence (boundary half, intact).
        self.assertEqual(trigger.effect, _draw_atom(1))
        # 14e (B-17): the post-activated bare tail is the ACTIVATION's tail.
        self.assertEqual(activated.effect, Seq(steps=(_draw_atom(2), _draw_atom(3))))

    def test_bullet_sentence_never_captured(self) -> None:
        """Negative: a sentence starting with "[" is another ability bullet —
        never a trailing sentence, even when it parses to a bare effect."""
        raw = _raw_card(
            "C",
            1,
            types=("Creature",),
            power_raw="1",
            toughness_raw="1",
            sentences=(
                "When this creature enters, draw a card.",
                "[X]: You draw another card.",
            ),
        )
        reg = self._etb_trigger_reg({"[X]: You draw another card.": _draw_atom(2)})
        res = compile_card(raw, reg)
        self.assertEqual(len(res.card.abilities), 2)
        trigger, spell = res.card.abilities
        assert isinstance(trigger, TriggeredAbility)
        self.assertEqual(trigger.effect, _draw_atom(1))
        self.assertEqual(_spell(spell).effect, _draw_atom(2))


# ---------------------------------------------------------------------------
# Round 14e (B-17): activation-tail capture, OPT(CAST)-permission exemption
# ---------------------------------------------------------------------------


def _cast_permission_effect() -> Effect:
    """The B4-cast-them-this-turn permission idiom's compiled shape: an
    empty-cost ActivatedAbility whose whole effect is OPT(CAST, cost=empty).
    (Chandra, Heart of Fire's "You may cast them this turn.")"""
    return OptionalEffect(
        inner=Atom(
            verb=Verb.CAST,
            args=AtomArgs(
                pairs=(
                    ("cost", Cost(parts=())),
                    (
                        "source",
                        Selector(
                            count=QUnbounded(),
                            mode=SelectorMode.CHOOSE,
                            filter=FAnd(()),
                            zones=(
                                Zone(
                                    kind=ZoneKind.GRAVEYARD,
                                    controller=ControllerRef.YOU,
                                ),
                            ),
                        ),
                    ),
                )
            ),
        )
    )


class TestActivationTrailing(unittest.TestCase):
    """Round 14e (B-17, Tavern Swindler / Waker of Waves / Seasoned
    Hallowblade): plain sentences printed under a PLAIN activated ability
    are that ability's ACTIVATION tail — they used to be orphaned onto the
    card-level SpellAbility and ran at CAST time (Swindler's flip gate
    raised FLIP_WON there, Hallowblade's GRANT raised the B-9 ``result``
    referent). Boundary discipline mirrors the trigger/loyalty tail; the
    empty-cost OPT(CAST) permission row is an EXEMPT (transparent) boundary
    and loyalty-costed abilities stay owned by the R11-1 loyalty chain."""

    @staticmethod
    def _reg(
        activation: ActivatedAbility,
        tail_effects: dict[str, Effect],
        *,
        permission_sentence: str | None = None,
        permission: ActivatedAbility | None = None,
        loyalty: bool = False,
    ) -> TemplateRegistry:
        reg = TemplateRegistry()
        opener = "Activation opener." if not loyalty else "[+1]: Activation opener."
        reg.register(
            _template(
                "activation",
                rf"^{re.escape(opener)}$",
                lambda m, a=activation: AbilityOutcome(ability=a),
            )
        )
        if permission is not None and permission_sentence is not None:
            reg.register(
                _template(
                    "permission",
                    rf"^{re.escape(permission_sentence)}$",
                    lambda m, p=permission: AbilityOutcome(ability=p),
                )
            )
        for n, (sentence, effect) in enumerate(tail_effects.items()):
            reg.register(
                _template(
                    f"tail-{n}",
                    rf"^{re.escape(sentence)}$",
                    lambda m, e=effect: EffectOutcome(effect=e),
                )
            )
        return reg

    def test_plain_activation_owns_its_tail(self) -> None:
        """Swindler shape: {T}: Draw a card. / You draw another card. ->
        ONE ActivatedAbility Seq, no SpellAbility tail effect (the trailing
        C4 node is the effect-less cast carrier, not an effect owner)."""
        raw = _raw_card(
            "S",
            71,
            types=("Creature",),
            power_raw="1",
            toughness_raw="1",
            sentences=("Activation opener.", "You draw another card."),
        )
        reg = self._reg(
            ActivatedAbility(cost=Cost(parts=(CostTap(),)), effect=_draw_atom(1)),
            {"You draw another card.": _draw_atom(2)},
        )
        res = compile_card(raw, reg)
        self.assertEqual(res.unparsed, ())
        activated, carrier = res.card.abilities  # + C4 cast carrier
        assert isinstance(activated, ActivatedAbility)
        self.assertEqual(activated.effect, Seq(steps=(_draw_atom(1), _draw_atom(2))))
        assert isinstance(carrier, SpellAbility)
        self.assertIsNone(carrier.effect)

    def test_permission_row_is_transparent_boundary(self) -> None:
        """The exemption: activation / OPT(CAST) permission / bare tail ->
        the tail skips the permission row and joins the ACTIVATION (a
        permission is never an action's owner)."""
        raw = _raw_card(
            "P",
            72,
            types=("Creature",),
            power_raw="1",
            toughness_raw="1",
            sentences=(
                "Activation opener.",
                "You may cast them this turn.",
                "You draw another card.",
            ),
        )
        reg = self._reg(
            ActivatedAbility(cost=Cost(parts=(CostTap(),)), effect=_draw_atom(1)),
            {"You draw another card.": _draw_atom(2)},
            permission_sentence="You may cast them this turn.",
            permission=ActivatedAbility(
                cost=Cost(parts=()), effect=_cast_permission_effect()
            ),
        )
        res = compile_card(raw, reg)
        self.assertEqual(res.unparsed, ())
        # B-49 follow-up #1: "this turn" makes the row a permission created by the
        # activation's resolution (CR 611.2a), so it is suppressed at assembly
        # instead of standing as a free ability. The tail still skipped it.
        activation, carrier = res.card.abilities  # + C4 carrier
        assert isinstance(activation, ActivatedAbility)
        assert isinstance(carrier, SpellAbility)
        self.assertIsNone(carrier.effect)
        # The activation owns the tail…
        self.assertEqual(activation.effect, Seq(steps=(_draw_atom(1), _draw_atom(2))))
        # …and the permission row is gone from the tree, announced as a gap.
        self.assertTrue(
            any("You may cast them this turn." in gap for gap in res.known_gaps),
            res.known_gaps,
        )

    def test_loyalty_tail_never_routes_through_this_mechanism(self) -> None:
        """Chandra boundary, synthetic: loyalty bullet / permission row /
        bare tail. The loyalty EXCLUSION keeps this mechanism out, and the
        tail never joins the permission row.

        B-49 follow-up #1 (2026-10-29): the R11-1 loyalty chain now sees through the
        permission row (the r14e intent), so the bullet owns its tail. Before,
        the tail landed card-level: Chandra, Heart of Fire's "Add six {R}." ran
        when she was cast. The row itself states a duration and is suppressed."""
        raw = _raw_card(
            "C",
            73,
            types=("Planeswalker",),
            loyalty_raw="3",
            sentences=(
                "[+1]: Activation opener.",
                "You may cast them this turn.",
                "You draw another card.",
            ),
        )
        reg = self._reg(
            ActivatedAbility(cost=Cost(parts=(CostLoyalty(1),)), effect=_draw_atom(1)),
            {"You draw another card.": _draw_atom(2)},
            permission_sentence="You may cast them this turn.",
            permission=ActivatedAbility(
                cost=Cost(parts=()), effect=_cast_permission_effect()
            ),
            loyalty=True,
        )
        res = compile_card(raw, reg)
        self.assertEqual(res.unparsed, ())
        act, carrier = res.card.abilities
        assert isinstance(act, ActivatedAbility)
        # The loyalty bullet owns the tail; nothing is left for the cast.
        self.assertEqual(act.effect, Seq(steps=(_draw_atom(1), _draw_atom(2))))
        self.assertEqual(carrier, SpellAbility(kind=SpellKind.PLANESWALKER))


class TestDurationPermissionRows(unittest.TestCase):
    """B-49 follow-up #1 (2026-10-29): a cast permission that lasts "until end of turn" or
    "this turn" is part of the ability whose resolution creates it (CR
    611.2a). It compiled as a free empty-cost activation of its own, which
    the controller could repeat any turn: Chandra, Flame's Catalyst cast any
    spell from her hand for nothing. CAST has no duration role yet, so the
    row is suppressed (the C5 mechanism) and the card is engine-unsupported.
    A static permission (Conspicuous Snoop) states no duration and stays."""

    @classmethod
    def setUpClass(cls) -> None:
        from MTG_bot.core.executor import SUPPORTED_VERBS_V2

        pool = ingest_pool(_M21_PATH)
        cls.reg = build_full_registry()
        cls.raw = {raw.identity.name: raw for raw in pool.values()}
        cls.gated_verbs = set(SUPPORTED_VERBS_V2)

    def _compile(self, name: str, *, gated: bool = False) -> CompileResult:
        verbs = self.gated_verbs if gated else None
        return compile_card(self.raw[name], self.reg, supported_verbs=verbs)

    @staticmethod
    def _free_activations(card: CardRecord) -> list[ActivatedAbility]:
        return [
            ab for ab in card.abilities if isinstance(ab, ActivatedAbility) and not ab.cost.parts
        ]

    def test_catalyst_has_no_free_activation_and_is_unsupported(self) -> None:
        res = self._compile("Chandra, Flame's Catalyst")
        self.assertEqual(self._free_activations(res.card), [])
        loyalty = [
            next(p.delta for p in ab.cost.parts if isinstance(p, CostLoyalty))
            for ab in res.card.abilities
            if isinstance(ab, ActivatedAbility)
        ]
        self.assertEqual(loyalty, [1, -2, -8])
        self.assertEqual(res.card.abilities[-1], SpellAbility(kind=SpellKind.PLANESWALKER))
        self.assertTrue(any("Until end of turn, you may cast" in g for g in res.known_gaps))
        self.assertFalse(self._compile("Chandra, Flame's Catalyst", gated=True).legality.engine_supported)

    def test_heart_of_fire_minus_nine_owns_its_mana_and_the_cast_adds_none(self) -> None:
        res = self._compile("Chandra, Heart of Fire")
        self.assertEqual(self._free_activations(res.card), [])
        (minus_nine,) = [
            ab
            for ab in res.card.abilities
            if isinstance(ab, ActivatedAbility) and CostLoyalty(-9) in ab.cost.parts
        ]
        verbs = [n.verb for n in walk(minus_nine) if isinstance(n, Atom)]
        self.assertIn(Verb.ADD_MANA, verbs)  # "Add six {R}." is the [−9]'s
        (spell,) = [ab for ab in res.card.abilities if isinstance(ab, SpellAbility)]
        self.assertIsNone(spell.effect)  # casting her adds no mana
        self.assertEqual(len([g for g in res.known_gaps if "cast permission" in g]), 2)
        self.assertFalse(self._compile("Chandra, Heart of Fire", gated=True).legality.engine_supported)

    def test_static_permission_stays_an_ability(self) -> None:
        res = self._compile("Conspicuous Snoop", gated=True)
        (row,) = self._free_activations(res.card)
        assert isinstance(row.effect, OptionalEffect) and isinstance(row.effect.inner, Atom)
        self.assertIs(row.effect.inner.verb, Verb.CAST)
        self.assertIsNone(row.effect.inner.args.get("cost"))  # costs are paid
        self.assertTrue(res.legality.engine_supported)


class TestDynamicLoyaltyCostGate(unittest.TestCase):
    """B-49 follow-up #4 (2026-10-29): Ugin, the Spirit Dragon's [−X]. X is
    announced as the ability is activated (CR 601.2b via 602.2b). The
    activation lane had no X declaration, so once the B-49 carrier made Ugin
    castable, legal_activations raised NotImplementedError ("QX has no declared
    X") on its controller's next scan. That was 58 of the 153 crashes in the
    800-game castable sweep, and the shape gate marked a Quantity loyalty
    delta engine-unsupported.

    Re-pinned 2026-10-29: the activation X lane (legality.activation_x_max /
    ask_activation_x, CR 606.6 caps X at the loyalty counters) supports a
    bare X, so Ugin is engine-supported. Any other Quantity delta has no
    announcement lane and stays gated."""

    @classmethod
    def setUpClass(cls) -> None:
        from MTG_bot.core.executor import SUPPORTED_VERBS_V2

        pool = ingest_pool(_M21_PATH)
        cls.reg = build_full_registry()
        cls.raw = {raw.identity.name: raw for raw in pool.values()}
        cls.verbs = set(SUPPORTED_VERBS_V2)

    def _gated(self, name: str) -> CompileResult:
        return compile_card(self.raw[name], self.reg, supported_verbs=self.verbs)

    def test_ugin_minus_x_is_supported_by_the_x_lane(self) -> None:
        # re-pinned 2026-10-29: the activation X lane changes Ugin from
        # gated to supported (it asserted assertFalse before the lane).
        res = self._gated("Ugin, the Spirit Dragon")
        deltas = [
            part.delta
            for ab in res.card.abilities
            if isinstance(ab, ActivatedAbility)
            for part in ab.cost.parts
            if isinstance(part, CostLoyalty)
        ]
        self.assertEqual(deltas, [2, QX(), -10])
        self.assertTrue(res.legality.engine_supported)

    def test_a_non_bare_x_loyalty_delta_stays_unsupported(self) -> None:
        from dataclasses import replace

        from MTG_bot.core.ability_tree import QBin, QBinOp, QConst
        from MTG_bot.core.compiler.compiler import _engine_supported

        res = self._gated("Ugin, the Spirit Dragon")
        minus_x = res.card.abilities[1]
        assert isinstance(minus_x, ActivatedAbility)
        crafted = replace(
            minus_x,
            cost=Cost(
                parts=(CostLoyalty(delta=QBin(QBinOp.ADD, QX(), QConst(1))),)
            ),
        )
        card = replace(
            res.card, abilities=(res.card.abilities[0], crafted, *res.card.abilities[2:])
        )
        self.assertFalse(_engine_supported(card, self.verbs))

    def test_fixed_loyalty_costs_stay_supported(self) -> None:
        for name in ("Basri Ket", "Liliana, Death Mage", "Garruk, Savage Herald"):
            self.assertTrue(self._gated(name).legality.engine_supported, name)


# ---------------------------------------------------------------------------
# Meta-filter conjunction (Enchant X)
# ---------------------------------------------------------------------------


class TestRound14fFidelity(unittest.TestCase):
    """Round 14f: the two audited compiler fidelities. (1) The
    B4-cast-them-this-turn permission row's anaphor CROSSes resolutions
    (the [−9]'s exile ran in its own execution; the permission activates
    later), so it compiles the executor's exiled-with POPULATION — the
    14d ``IS_EXILED_WITH_SOURCE`` pred, Chandra's own [+1] row's shape —
    never the per-resolution ``result`` register 14e closed (the residual
    it named). (2) A bare static anthem sentence is an ABILITY: the
    opponents-debuff row was the lone outlier emitting a raw
    EffectOutcome, which folded into the creature's SpellAbility and ran
    ONCE at cast (Waker of Waves). The StaticAbility wrapper is the
    family's established shape (the five sibling rows) and the card then
    carries no SpellAbility — the same B-1 move the 14e capture ruled for
    Swindler/Hallowblade."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.pool = ingest_pool(_M21_PATH)
        cls.reg = build_full_registry()
        cls.pc = compile_pool(cls.pool, cls.reg)

    def test_cast_them_row_compiles_the_exiled_with_population(self) -> None:
        raw = _raw_card(
            "Permission Fixture",
            791,
            sentences=("You may cast them this turn.",),
        )
        res = compile_card(raw, self.reg)
        self.assertEqual(res.unparsed, ())
        # B-49 follow-up #1: the row states a duration, so compile_card suppresses it (a
        # permission created by a resolving ability, CR 611.2a). The fidelity
        # this test pins is the template's own row, read from the registry.
        self.assertEqual(res.card.abilities, ())
        self.assertEqual(len(res.known_gaps), 1)
        (match,) = self.reg.match("You may cast them this turn.")
        assert isinstance(match.outcome, AbilityOutcome)
        ability = match.outcome.ability
        assert isinstance(ability, ActivatedAbility)
        self.assertEqual(ability.cost, Cost())  # the empty-cost permission
        assert isinstance(ability.effect, OptionalEffect)
        cast_atom = ability.effect.inner
        assert isinstance(cast_atom, Atom)
        self.assertIs(cast_atom.verb, Verb.CAST)
        selector = cast_atom.args.get("source")
        assert isinstance(selector, Selector)
        self.assertIsNone(selector.referent)  # NO register hop anymore
        self.assertIsInstance(selector.count, QUnbounded)  # plural "them"
        self.assertIs(selector.mode, SelectorMode.CHOOSE)
        self.assertEqual(selector.zones[0].kind, ZoneKind.EXILE)
        self.assertIs(selector.zones[0].controller, ControllerRef.YOU)
        self.assertEqual(selector.filter, FAtom(pred=FAtomPred.IS_EXILED_WITH_SOURCE))

    def test_corpus_scope_of_the_two_rows(self) -> None:
        # The audit's set-equality premise: each fidelity touches EXACTLY
        # the named card in the 305.
        cast_them = {
            self.pool[oid].identity.name
            for oid in self.pool
            if "You may cast them this turn."
            in (self.pool[oid].identity.oracle_text or "")
        }
        static_opp = {
            self.pool[oid].identity.name
            for oid in self.pool
            if re.search(
                r"Creatures your opponents control get -\d+/-\d+\.",
                self.pool[oid].identity.oracle_text or "",
            )
        }
        self.assertEqual(cast_them, {"Chandra, Heart of Fire"})
        self.assertEqual(static_opp, {"Waker of Waves"})

    def test_waker_static_lives_on_a_static_ability(self) -> None:
        (waker,) = [
            res.card
            for res in self.pc.results.values()
            if res.card.name == "Waker of Waves"
        ]
        kinds = [type(a).__name__ for a in waker.abilities]
        self.assertEqual(kinds, ["StaticAbility", "ActivatedAbility", "SpellAbility"])
        static = waker.abilities[0]
        assert isinstance(static, StaticAbility)
        atom = static.effect
        assert isinstance(atom, Atom)
        self.assertIs(atom.verb, Verb.MODIFY_PT)
        self.assertIsNone(atom.args.get("duration"))  # continuous, not timed
        # C4: the miscompile stays GONE — the trailing SpellAbility is the
        # effect-less CREATURE cast carrier, NOT the old tail-effect node.
        carrier = waker.abilities[2]
        assert isinstance(carrier, SpellAbility)
        self.assertIsNone(carrier.effect)
        self.assertIs(carrier.kind, SpellKind.CREATURE)
        # the 14e activation capture is untouched by the re-wrap
        activation = waker.abilities[1]
        assert isinstance(activation, ActivatedAbility)
        self.assertIsInstance(activation.effect, Seq)


class TestMetaFilter(unittest.TestCase):
    def test_enchant_filter_conjoined_into_target(self) -> None:
        meta = FAtom(pred=FAtomPred.SUBTYPE_EQ, string_value="creature")
        raw = _raw_card(
            "E",
            1,
            types=("Enchantment", "Card"),
            subtypes=("Curse",),
            sentences=("Enchant target creature.", "Destroy target creature."),
        )
        reg = TemplateRegistry()
        reg.register(
            _template(
                "enchant",
                r"^Enchant target creature\.$",
                lambda m: MetaOutcome(kind="enchant", filter=meta),
            )
        )
        reg.register(
            _template(
                "destroy",
                r"^Destroy target creature\.$",
                lambda m: EffectOutcome(effect=_destroy_atom()),
            )
        )
        res = compile_card(raw, reg)
        self.assertEqual(len(res.card.abilities), 1)
        ab = _spell(res.card.abilities[0])
        self.assertIs(ab.kind, SpellKind.ENCHANTMENT)
        target = _selector(dict(_atom(ab.effect).args.pairs)["target"])
        self.assertEqual(_fand(target.filter).children, (meta, meta))


# ---------------------------------------------------------------------------
# Assembly by card type
# ---------------------------------------------------------------------------


class TestAssembly(unittest.TestCase):
    def test_creature_spell_ability(self) -> None:
        raw = _raw_card(
            "C",
            1,
            types=("Creature", "Card"),
            colors=("W",),
            mana_cost_raw="{1}{W}",
            mana_value=2,
            power_raw="2",
            toughness_raw="2",
            sentences=("Draw a card.",),
        )
        reg = TemplateRegistry()
        reg.register(
            _template(
                "d", r"^Draw a card\.$", lambda m: EffectOutcome(effect=_draw_atom())
            )
        )
        res = compile_card(raw, reg)
        card = res.card
        self.assertEqual(card.mana_cost, parse_mana_cost("{1}{W}"))
        self.assertEqual(card.power, QConst(2))
        self.assertEqual(card.toughness, QConst(2))
        self.assertEqual(
            card.abilities,
            (SpellAbility(kind=SpellKind.CREATURE, effect=_draw_atom()),),
        )

    def test_instant_folds_sequence(self) -> None:
        raw = _raw_card(
            "I",
            1,
            types=("Instant", "Card"),
            sentences=("Draw a card.", "Draw a card."),
        )
        reg = TemplateRegistry()
        reg.register(
            _template(
                "d", r"^Draw a card\.$", lambda m: EffectOutcome(effect=_draw_atom())
            )
        )
        res = compile_card(raw, reg)
        ab = _spell(res.card.abilities[0])
        self.assertIs(ab.kind, SpellKind.INSTANT)
        self.assertEqual(len(_seq(ab.effect).steps), 2)

    def test_sorcery_kind(self) -> None:
        raw = _raw_card("S", 1, types=("Sorcery", "Card"), sentences=("Draw a card.",))
        reg = TemplateRegistry()
        reg.register(
            _template(
                "d", r"^Draw a card\.$", lambda m: EffectOutcome(effect=_draw_atom())
            )
        )
        res = compile_card(raw, reg)
        ab = _spell(res.card.abilities[0])
        self.assertIs(ab.kind, SpellKind.SORCERY)

    def test_planeswalker(self) -> None:
        raw = _raw_card(
            "P",
            1,
            types=("Planeswalker", "Card"),
            colors=("B",),
            mana_cost_raw="{2}{B}",
            mana_value=3,
            loyalty_raw="3",
            sentences=("Draw a card.",),
        )
        reg = TemplateRegistry()
        reg.register(
            _template(
                "d", r"^Draw a card\.$", lambda m: EffectOutcome(effect=_draw_atom())
            )
        )
        res = compile_card(raw, reg)
        self.assertEqual(res.card.loyalty, 3)
        self.assertEqual(
            res.card.abilities,
            (SpellAbility(kind=SpellKind.PLANESWALKER, effect=_draw_atom()),),
        )

    def test_token_becomes_static_ability(self) -> None:
        raw = _raw_card(
            "T",
            1,
            types=("Creature", "Token", "Card"),
            subtypes=("Bird",),
            power_raw="1",
            toughness_raw="1",
            is_token=True,
            sentences=("Draw a card.",),
        )
        reg = TemplateRegistry()
        reg.register(
            _template(
                "d", r"^Draw a card\.$", lambda m: EffectOutcome(effect=_draw_atom())
            )
        )
        res = compile_card(raw, reg)
        self.assertTrue(res.card.is_token)
        self.assertEqual(res.card.abilities, (StaticAbility(effect=_draw_atom()),))

    def test_land_tap_ability(self) -> None:
        raw = _raw_card(
            "L",
            1,
            types=("Land", "Basic", "Card"),
            subtypes=("Plains",),
            sentences=("({T}: Add {W}.)",),
        )
        reg = TemplateRegistry()
        reg.register(
            _template(
                "land-tap",
                r"^\(\{T\}: Add \{W\}\.\)$",
                lambda m: AbilityOutcome(
                    ability=ActivatedAbility(
                        cost=Cost(parts=(CostTap(),)), effect=_add_mana_atom()
                    )
                ),
            )
        )
        res = compile_card(raw, reg)
        self.assertEqual(
            res.card.abilities,
            (ActivatedAbility(cost=Cost(parts=(CostTap(),)), effect=_add_mana_atom()),),
        )
        self.assertIsNone(res.card.mana_cost)


# ---------------------------------------------------------------------------
# Additional-cost sentences ("As an additional cost to cast this spell, …")
# ---------------------------------------------------------------------------


def _hand_card_selector() -> Selector:
    """Choose a card from your hand (B5a additional-cost discard target)."""
    return Selector(
        count=QConst(1),
        mode=SelectorMode.CHOOSE,
        filter=FAnd(children=()),
        zones=(Zone(kind=ZoneKind.HAND, controller=ControllerRef.YOU),),
    )


def _additional_cost_discard() -> Cost:
    """The canonical "discard a card" additional cost."""
    return Cost(parts=(CostDiscard(target=_hand_card_selector()),))


def _additional_cost_sacrifice() -> Cost:
    """The canonical "sacrifice a creature" additional cost."""
    return Cost(parts=(CostSacrifice(target=_target_selector()),))


def _additional_cost_templates(reg: TemplateRegistry) -> None:
    reg.register(
        _template(
            "ac-discard",
            r"^As an additional cost to cast this spell, discard a card\.$",
            lambda m: AdditionalCostOutcome(cost=_additional_cost_discard()),
        )
    )
    reg.register(
        _template(
            "ac-sacrifice",
            r"^As an additional cost to cast this spell, sacrifice a creature\.$",
            lambda m: AdditionalCostOutcome(cost=_additional_cost_sacrifice()),
        )
    )


class TestAdditionalCost(unittest.TestCase):
    def test_sorcery_discard_additional_cost(self) -> None:
        raw = _raw_card(
            "S",
            1,
            types=("Sorcery", "Card"),
            colors=("B",),
            mana_cost_raw="{2}{B}",
            mana_value=3,
            sentences=(
                "Draw a card.",
                "As an additional cost to cast this spell, discard a card.",
            ),
        )
        reg = TemplateRegistry()
        reg.register(
            _template(
                "d", r"^Draw a card\.$", lambda m: EffectOutcome(effect=_draw_atom())
            )
        )
        _additional_cost_templates(reg)
        res = compile_card(raw, reg)
        self.assertEqual(res.unparsed, ())
        ab = _spell(res.card.abilities[0])
        self.assertIs(ab.kind, SpellKind.SORCERY)
        self.assertEqual(ab.effect, _draw_atom())
        self.assertEqual(ab.additional_costs, (_additional_cost_discard(),))

    def test_instant_sacrifice_additional_cost(self) -> None:
        raw = _raw_card(
            "I",
            1,
            types=("Instant", "Card"),
            colors=("R",),
            mana_cost_raw="{1}{R}",
            mana_value=2,
            sentences=(
                "Destroy target creature.",
                "As an additional cost to cast this spell, sacrifice a creature.",
            ),
        )
        reg = TemplateRegistry()
        reg.register(
            _template(
                "dest",
                r"^Destroy target creature\.$",
                lambda m: EffectOutcome(effect=_destroy_atom()),
            )
        )
        _additional_cost_templates(reg)
        res = compile_card(raw, reg)
        self.assertEqual(res.unparsed, ())
        ab = _spell(res.card.abilities[0])
        self.assertIs(ab.kind, SpellKind.INSTANT)
        self.assertEqual(ab.additional_costs, (_additional_cost_sacrifice(),))

    def test_multiple_additional_costs_attached_in_order(self) -> None:
        raw = _raw_card(
            "S",
            1,
            types=("Sorcery", "Card"),
            sentences=(
                "Draw a card.",
                "As an additional cost to cast this spell, discard a card.",
                "As an additional cost to cast this spell, sacrifice a creature.",
            ),
        )
        reg = TemplateRegistry()
        reg.register(
            _template(
                "d", r"^Draw a card\.$", lambda m: EffectOutcome(effect=_draw_atom())
            )
        )
        _additional_cost_templates(reg)
        res = compile_card(raw, reg)
        self.assertEqual(res.unparsed, ())
        ab = _spell(res.card.abilities[0])
        self.assertEqual(
            ab.additional_costs,
            (_additional_cost_discard(), _additional_cost_sacrifice()),
        )

    def test_canonical_json_omits_empty_costs(self) -> None:
        raw = _raw_card("S", 1, types=("Sorcery", "Card"), sentences=("Draw a card.",))
        reg = TemplateRegistry()
        reg.register(
            _template(
                "d", r"^Draw a card\.$", lambda m: EffectOutcome(effect=_draw_atom())
            )
        )
        res = compile_card(raw, reg)
        self.assertNotIn("additional_costs", canonical_json(res.card))

    def test_canonical_json_includes_costs(self) -> None:
        raw = _raw_card(
            "S",
            1,
            types=("Sorcery", "Card"),
            sentences=(
                "Draw a card.",
                "As an additional cost to cast this spell, discard a card.",
            ),
        )
        reg = TemplateRegistry()
        reg.register(
            _template(
                "d", r"^Draw a card\.$", lambda m: EffectOutcome(effect=_draw_atom())
            )
        )
        _additional_cost_templates(reg)
        res = compile_card(raw, reg)
        self.assertIn("additional_costs", canonical_json(res.card))

    def test_orphan_land_raises(self) -> None:
        raw = _raw_card(
            "L",
            1,
            types=("Land", "Basic", "Card"),
            subtypes=("Plains",),
            sentences=("As an additional cost to cast this spell, discard a card.",),
        )
        reg = TemplateRegistry()
        _additional_cost_templates(reg)
        with self.assertRaises(StateCorruptionError):
            compile_card(raw, reg)

    def test_orphan_token_raises(self) -> None:
        raw = _raw_card(
            "T",
            1,
            types=("Creature", "Token", "Card"),
            subtypes=("Bird",),
            power_raw="1",
            toughness_raw="1",
            is_token=True,
            sentences=("As an additional cost to cast this spell, discard a card.",),
        )
        reg = TemplateRegistry()
        _additional_cost_templates(reg)
        with self.assertRaises(StateCorruptionError):
            compile_card(raw, reg)

    def test_continuation_preserves_additional_costs(self) -> None:
        # A template-carried SpellAbility with additional costs must keep
        # them when a continuation sentence merges into its effect.
        raw = _raw_card(
            "S",
            1,
            types=("Sorcery", "Card"),
            sentences=(
                "Fireball hits.",
                "Then draw another.",
            ),
        )
        reg = TemplateRegistry()
        reg.register(
            _template(
                "spell",
                r"^Fireball hits\.$",
                lambda m: AbilityOutcome(
                    ability=SpellAbility(
                        kind=SpellKind.SORCERY,
                        effect=_destroy_atom(),
                        additional_costs=(_additional_cost_sacrifice(),),
                    )
                ),
            )
        )
        reg.register(
            _template(
                "then-draw",
                r"^Then draw another\.$",
                lambda m: EffectOutcome(effect=_draw_atom(2)),
            )
        )
        res = compile_card(raw, reg)
        self.assertEqual(res.unparsed, ())
        self.assertEqual(len(res.card.abilities), 1)
        ab = _spell(res.card.abilities[0])
        steps = _seq(ab.effect)
        self.assertEqual(steps.steps[0], _destroy_atom())
        # R11-1: "If you do, …" without "may" merges MANDATORILY.
        self.assertEqual(steps.steps[1], _draw_atom(2))
        self.assertEqual(ab.additional_costs, (_additional_cost_sacrifice(),))

    def test_creature_discard_additional_cost_no_effect(self) -> None:
        # A castable creature whose only relevant sentence is the
        # additional cost (M21 Goremand / Sparkhunter Masticore shape):
        # the compiler must build an effect-less SpellAbility, not raise.
        raw = _raw_card(
            "C",
            1,
            types=("Creature", "Demon", "Card"),
            colors=("B",),
            mana_cost_raw="{2}{B}",
            mana_value=3,
            power_raw="3",
            toughness_raw="1",
            sentences=(
                "Flying.",
                "As an additional cost to cast this spell, discard a card.",
            ),
        )
        reg = TemplateRegistry()
        reg.register(
            _template(
                "fly",
                r"^Flying\.$",
                lambda m: KeywordOutcome(keyword=Keyword.FLYING, params=()),
            )
        )
        _additional_cost_templates(reg)
        res = compile_card(raw, reg)
        self.assertEqual(res.unparsed, ())
        spells = [a for a in res.card.abilities if isinstance(a, SpellAbility)]
        self.assertEqual(len(spells), 1)
        ab = spells[0]
        self.assertIs(ab.kind, SpellKind.CREATURE)
        self.assertIsNone(ab.effect)
        self.assertEqual(ab.additional_costs, (_additional_cost_discard(),))


# ---------------------------------------------------------------------------
# Activation-gate sentences ("Activate only if ...")
# ---------------------------------------------------------------------------


def _gate_dead_filter() -> Filter:
    """Gate condition: a creature died this turn."""
    return FAtom(pred=FAtomPred.DIED_THIS_TURN)


def _gate_flying_filter() -> Filter:
    """Gate condition: you control at least one creature with flying."""
    return FAtom(
        pred=FAtomPred.CONTROLLER_COUNT_GE,
        count=QConst(1),
        inner_filter=FAnd(
            children=(
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                FAtom(pred=FAtomPred.KEYWORD_HAS, keyword=Keyword.FLYING),
            )
        ),
    )


def _activation_gate_templates(reg: TemplateRegistry) -> None:
    reg.register(
        _template(
            "gate-death",
            r"^Activate only if a creature died this turn\.$",
            lambda m: ActivationGateOutcome(condition=_gate_dead_filter()),
        )
    )
    reg.register(
        _template(
            "gate-flying",
            r"^Activate only if you control a creature with flying\.$",
            lambda m: ActivationGateOutcome(condition=_gate_flying_filter()),
        )
    )


def _activated_templates(reg: TemplateRegistry) -> None:
    """Two tap-style activated abilities for gates to anchor to."""
    reg.register(
        _template(
            "act-tap-draw",
            r"^Tap to draw a card\.$",
            lambda m: AbilityOutcome(
                ability=ActivatedAbility(
                    cost=Cost(parts=(CostTap(),)),
                    effect=_draw_atom(),
                )
            ),
        )
    )
    reg.register(
        _template(
            "act-two-tap-mana",
            r"^\{2\}, Tap: Add \{W\}\.$",
            lambda m: AbilityOutcome(
                ability=ActivatedAbility(
                    cost=Cost(parts=(CostManaGeneric(QConst(2)), CostTap())),
                    effect=_add_mana_atom(),
                )
            ),
        )
    )


class TestActivationGate(unittest.TestCase):
    def test_gate_attaches_to_preceding_activated_ability(self) -> None:
        raw = _raw_card(
            "C",
            1,
            types=("Creature", "Card"),
            sentences=(
                "Tap to draw a card.",
                "Activate only if a creature died this turn.",
            ),
        )
        reg = TemplateRegistry()
        _activated_templates(reg)
        _activation_gate_templates(reg)
        res = compile_card(raw, reg)
        self.assertEqual(res.unparsed, ())
        acts = [a for a in res.card.abilities if isinstance(a, ActivatedAbility)]
        self.assertEqual(len(acts), 1)
        ab = acts[0]
        self.assertEqual(ab.condition, _gate_dead_filter())
        self.assertEqual(ab.effect, _draw_atom())

    def test_gates_pair_with_preceding_abilities_in_order(self) -> None:
        # Once an ability carries a condition it stops qualifying, so the
        # second gate must land on the second activated ability, not
        # re-bind the first.
        raw = _raw_card(
            "C",
            2,
            types=("Creature", "Card"),
            sentences=(
                "Tap to draw a card.",
                "Activate only if a creature died this turn.",
                "{2}, Tap: Add {W}.",
                "Activate only if you control a creature with flying.",
            ),
        )
        reg = TemplateRegistry()
        _activated_templates(reg)
        _activation_gate_templates(reg)
        res = compile_card(raw, reg)
        self.assertEqual(res.unparsed, ())
        acts = [a for a in res.card.abilities if isinstance(a, ActivatedAbility)]
        self.assertEqual(len(acts), 2)
        self.assertEqual(acts[0].condition, _gate_dead_filter())
        self.assertEqual(acts[1].condition, _gate_flying_filter())

    def test_orphan_gate_raises(self) -> None:
        raw = _raw_card(
            "S",
            3,
            types=("Sorcery", "Card"),
            sentences=("Activate only if a creature died this turn.",),
        )
        reg = TemplateRegistry()
        _activation_gate_templates(reg)
        with self.assertRaises(StateCorruptionError):
            compile_card(raw, reg)

    def test_gate_does_not_attach_to_non_activated_ability(self) -> None:
        # A SpellAbility is not a valid anchor: even though the card
        # compiled an ability, the gate has no ActivatedAbility to bind.
        raw = _raw_card(
            "S",
            4,
            types=("Sorcery", "Card"),
            sentences=(
                "Draw a card.",
                "Activate only if a creature died this turn.",
            ),
        )
        reg = TemplateRegistry()
        reg.register(
            _template(
                "d", r"^Draw a card\.$", lambda m: EffectOutcome(effect=_draw_atom())
            )
        )
        _activation_gate_templates(reg)
        with self.assertRaises(StateCorruptionError):
            compile_card(raw, reg)


# ---------------------------------------------------------------------------
# Star P/T coverage
# ---------------------------------------------------------------------------


class TestStarPt(unittest.TestCase):
    def test_star_without_set_pt_reports_gap(self) -> None:
        raw = _raw_card(
            "W",
            1,
            types=("Creature", "Card"),
            power_raw="*",
            toughness_raw="4",
            sentences=("Draw a card.",),
        )
        reg = TemplateRegistry()
        reg.register(
            _template(
                "d", r"^Draw a card\.$", lambda m: EffectOutcome(effect=_draw_atom())
            )
        )
        res = compile_card(raw, reg)  # must not raise
        self.assertIsNone(res.card.power)
        self.assertEqual(res.card.toughness, QConst(4))
        self.assertTrue(
            any(g.startswith("star P/T") and "power" in g for g in res.known_gaps)
        )

    def test_star_with_set_pt_is_clean(self) -> None:
        raw = _raw_card(
            "W",
            1,
            types=("Creature", "Card"),
            power_raw="*",
            toughness_raw="*",
            sentences=("Set its power and toughness to 1/1.",),
        )
        reg = TemplateRegistry()
        reg.register(
            _template(
                "setpt",
                r"^Set its power and toughness to 1/1\.$",
                lambda m: EffectOutcome(effect=_set_pt_atom()),
            )
        )
        res = compile_card(raw, reg)
        self.assertIsNone(res.card.power)
        self.assertIsNone(res.card.toughness)
        self.assertFalse(any(g.startswith("star P/T") for g in res.known_gaps))


# ---------------------------------------------------------------------------
# engine_supported / LegalityFlags
# ---------------------------------------------------------------------------


class TestEngineSupported(unittest.TestCase):
    def _result(self, supported: set[Verb] | None) -> CompileResult:
        raw = _raw_card("I", 1, sentences=("Draw a card.",))
        reg = TemplateRegistry()
        reg.register(
            _template(
                "d", r"^Draw a card\.$", lambda m: EffectOutcome(effect=_draw_atom())
            )
        )
        return compile_card(raw, reg, supported_verbs=supported)

    def test_none_means_supported(self) -> None:
        res = self._result(None)
        self.assertTrue(res.legality.engine_supported)
        self.assertTrue(res.legality.format_legal)
        self.assertTrue(res.legality.enabled)

    def test_supported_verbs_all_present(self) -> None:
        res = self._result({Verb.DRAW})
        self.assertTrue(res.legality.engine_supported)

    def test_missing_verb_not_supported(self) -> None:
        res = self._result({Verb.TAP})
        self.assertFalse(res.legality.engine_supported)


# ---------------------------------------------------------------------------
# Ambiguity
# ---------------------------------------------------------------------------


class TestAmbiguity(unittest.TestCase):
    def test_distinct_outcomes_recorded(self) -> None:
        raw = _raw_card("I", 1, sentences=("Flying",))
        reg = TemplateRegistry()
        reg.register(
            _template(
                "t_hi",
                r"^Flying$",
                lambda m: KeywordOutcome(keyword=Keyword.HASTE, params=()),
                priority=10,
            )
        )
        reg.register(
            _template(
                "t_lo",
                r"^Flying$",
                lambda m: KeywordOutcome(keyword=Keyword.FLYING, params=()),
                priority=1,
            )
        )
        res = compile_card(raw, reg)
        self.assertEqual(len(res.ambiguities), 1)
        self.assertEqual(res.ambiguities[0].tids, ("t_hi", "t_lo"))
        self.assertEqual(res.ambiguities[0].sentence, "Flying")
        # Highest-priority outcome used.
        self.assertEqual(res.card.keywords, (KeywordAbility(Keyword.HASTE, ()),))

    def test_identical_outcomes_not_recorded(self) -> None:
        raw = _raw_card("I", 1, sentences=("Flying",))
        reg = TemplateRegistry()
        reg.register(
            _template(
                "t_a",
                r"^Flying$",
                lambda m: KeywordOutcome(keyword=Keyword.FLYING, params=()),
                priority=1,
            )
        )
        reg.register(
            _template(
                "t_b",
                r"^Flying$",
                lambda m: KeywordOutcome(keyword=Keyword.FLYING, params=()),
                priority=2,
            )
        )
        res = compile_card(raw, reg)
        self.assertEqual(res.ambiguities, ())
        self.assertEqual(res.card.keywords, (KeywordAbility(Keyword.FLYING, ()),))


# ---------------------------------------------------------------------------
# compile_pool (synthetic)
# ---------------------------------------------------------------------------


class TestCompilePoolSynthetic(unittest.TestCase):
    def _pool(self) -> dict[str, RawCard]:
        # The grammar requires an emblem's owner to be a Planeswalker with a
        # loyalty value (CardRecord.__post_init__), and an emblem to be an
        # "Emblem"-typed token record — mirror the real M21 pool shape.
        owner = _raw_card("Owner", 1, types=("Planeswalker", "Card"), loyalty_raw="3")
        emblem = _raw_card(
            "Emblem",
            2,
            types=("Emblem",),
            is_emblem=True,
            related_names=("Owner",),
        )
        orphan = _raw_card(
            "Stray Emblem",
            3,
            types=("Emblem",),
            is_emblem=True,
            related_names=("Ghost",),
        )
        return {_oid(1): owner, _oid(2): emblem, _oid(3): orphan}

    def test_emblem_attachment_and_orphans(self) -> None:
        pc = compile_pool(self._pool(), TemplateRegistry())
        self.assertEqual(set(pc.cards), {_oid(1)})
        self.assertEqual(set(pc.emblems), {_oid(2), _oid(3)})
        self.assertEqual(pc.orphan_emblems, (_oid(3),))
        self.assertIs(pc.cards[_oid(1)].emblem, pc.emblems[_oid(2)])
        s = pc.summary
        self.assertEqual(s["total"], 1)
        self.assertEqual(s["emblems"], 2)
        self.assertEqual(s["orphan_emblems"], 1)
        self.assertEqual(s["fully_compiled"], 1)
        self.assertEqual(s["partially_compiled"], 0)
        self.assertEqual(s["known_gap_count"], 0)
        self.assertEqual(set(pc.results), {_oid(1), _oid(2), _oid(3)})

    def test_unparsed_counted_partially(self) -> None:
        pool = {_oid(1): _raw_card("C", 1, sentences=("Nobody understands this.",))}
        pc = compile_pool(pool, TemplateRegistry())
        s = pc.summary
        self.assertEqual(s["partially_compiled"], 1)
        self.assertEqual(s["unparsed_count"], 1)
        self.assertEqual(
            pc.results[_oid(1)].unparsed,
            (("Nobody understands this.", "spell-effect"),),
        )


# ---------------------------------------------------------------------------
# Real M21.json smoke test
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Choose-opener built-in ("Choose one —" folding)
# ---------------------------------------------------------------------------


def _choose_option_templates(reg: TemplateRegistry) -> None:
    reg.register(
        _template(
            "opt-draw",
            r"^• Draw a card\.$",
            lambda m: EffectOutcome(effect=_draw_atom(1)),
        )
    )
    reg.register(
        _template(
            "opt-destroy",
            r"^• Destroy target artifact\.$",
            lambda m: EffectOutcome(effect=_destroy_atom()),
        )
    )


class TestChooseOpener(unittest.TestCase):
    """Compiler built-in folding a choose-opener sentence with its parsed
    option bullets into a Choose node (or trigger-owned Choose nodes)."""

    def test_spell_choose_one_folds_into_choose(self) -> None:
        raw = _raw_card(
            "I",
            1,
            sentences=(
                "Choose one —",
                "• Draw a card.",
                "• Destroy target artifact.",
            ),
        )
        reg = TemplateRegistry()
        _choose_option_templates(reg)
        res = compile_card(raw, reg)
        self.assertEqual(res.unparsed, ())
        self.assertEqual(
            res.card.abilities,
            (
                SpellAbility(
                    kind=SpellKind.INSTANT,
                    effect=Choose(
                        count=QConst(1),
                        options=(_draw_atom(1), _destroy_atom()),
                    ),
                ),
            ),
        )

    def test_spell_choose_two_uses_count_two(self) -> None:
        raw = _raw_card(
            "I",
            1,
            sentences=(
                "Choose two —",
                "• Draw a card.",
                "• Destroy target artifact.",
                "• Draw a card.",
            ),
        )
        reg = TemplateRegistry()
        _choose_option_templates(reg)
        res = compile_card(raw, reg)
        self.assertEqual(res.unparsed, ())
        choose = _choose(_spell(res.card.abilities[0]).effect)
        self.assertEqual(choose.count, QConst(2))
        self.assertEqual(len(choose.options), 3)

    def test_spell_choose_three_uses_count_three(self) -> None:
        raw = _raw_card(
            "I",
            1,
            sentences=(
                "Choose three —",
                "• Draw a card.",
                "• Destroy target artifact.",
                "• Draw a card.",
            ),
        )
        reg = TemplateRegistry()
        _choose_option_templates(reg)
        res = compile_card(raw, reg)
        self.assertEqual(res.unparsed, ())
        choose = _choose(_spell(res.card.abilities[0]).effect)
        self.assertEqual(choose.count, QConst(3))

    def test_spell_choose_one_or_more_uses_unbounded(self) -> None:
        raw = _raw_card(
            "I",
            1,
            sentences=(
                "Choose one or more —",
                "• Draw a card.",
                "• Destroy target artifact.",
                "• Draw a card.",
            ),
        )
        reg = TemplateRegistry()
        _choose_option_templates(reg)
        res = compile_card(raw, reg)
        self.assertEqual(res.unparsed, ())
        ab = _spell(res.card.abilities[0])
        choose = _choose(ab.effect)
        self.assertEqual(choose.count, QUnbounded())
        self.assertEqual(
            choose.options, (_draw_atom(1), _destroy_atom(), _draw_atom(1))
        )

    def test_etb_choose_one_becomes_triggered_ability(self) -> None:
        raw = _raw_card(
            "C",
            1,
            types=("Creature",),
            sentences=(
                "When this creature enters, choose one —",
                "• Draw a card.",
                "• Destroy target artifact.",
            ),
        )
        reg = TemplateRegistry()
        _choose_option_templates(reg)
        res = compile_card(raw, reg)
        self.assertEqual(res.unparsed, ())
        self.assertEqual(
            res.card.abilities,
            (
                TriggeredAbility(
                    event=ZoneChangeEvent(
                        from_zone=Zone(ZoneKind.ANY, ControllerRef.ANY),
                        to_zone=Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU),
                        # R11-B: "When THIS creature enters" anchors on the
                        # card itself (audit 09-29/04 P0-2).
                        subject=FAtom(pred=FAtomPred.IS_SOURCE),
                    ),
                    condition=None,
                    effect=Choose(
                        count=QConst(1),
                        options=(_draw_atom(1), _destroy_atom()),
                    ),
                ),
                # C4: plain creatures carry the effect-less cast lane.
                SpellAbility(kind=SpellKind.CREATURE),
            ),
        )

    def test_attack_block_choose_one_decomposes_into_two_triggers(self) -> None:
        raw = _raw_card(
            "C",
            1,
            types=("Creature",),
            sentences=(
                "Whenever this creature attacks or blocks, choose one —",
                "• Draw a card.",
                "• Destroy target artifact.",
            ),
        )
        reg = TemplateRegistry()
        _choose_option_templates(reg)
        res = compile_card(raw, reg)
        self.assertEqual(res.unparsed, ())
        choose = Choose(count=QConst(1), options=(_draw_atom(1), _destroy_atom()))
        self.assertEqual(
            res.card.abilities,
            (
                TriggeredAbility(
                    event=DeclareAttackersEvent(filter=FAtom(pred=FAtomPred.IS_SOURCE)),
                    condition=None,
                    effect=choose,
                ),
                TriggeredAbility(
                    event=DeclareBlockersEvent(filter=FAtom(pred=FAtomPred.IS_SOURCE)),
                    condition=None,
                    effect=choose,
                ),
                # C4: plain creatures carry the effect-less cast lane.
                SpellAbility(kind=SpellKind.CREATURE),
            ),
        )

    def test_single_option_opener_stays_unparsed(self) -> None:
        """Fewer than two parsed options: the opener must NOT be folded
        into a degenerate single-option Choose."""
        raw = _raw_card(
            "I",
            1,
            sentences=("Choose one —", "• Draw a card."),
        )
        reg = TemplateRegistry()
        _choose_option_templates(reg)
        res = compile_card(raw, reg)
        self.assertEqual(res.unparsed, (("Choose one —", "spell-effect"),))
        self.assertEqual(
            res.card.abilities,
            (SpellAbility(kind=SpellKind.INSTANT, effect=_draw_atom(1)),),
        )

    def test_opener_without_options_stays_unparsed(self) -> None:
        raw = _raw_card("I", 1, sentences=("Choose one —",))
        reg = TemplateRegistry()
        res = compile_card(raw, reg)
        self.assertEqual(res.unparsed, (("Choose one —", "spell-effect"),))
        self.assertEqual(res.card.abilities, ())

    def test_continuation_after_options_not_folded_into_choose(self) -> None:
        """A continuation after the option bullets must not merge into the
        Choose; with no other merge target it becomes its own optional
        step beside the Choose in the spell effect Seq."""
        raw = _raw_card(
            "I",
            1,
            sentences=(
                "Choose one —",
                "• Draw a card.",
                "• Destroy target artifact.",
                "If you do, draw another.",
            ),
        )
        reg = TemplateRegistry()
        _choose_option_templates(reg)
        reg.register(
            _template(
                "cont-draw",
                r"^If you do, draw another\.$",
                lambda m: EffectOutcome(effect=_draw_atom(2)),
            )
        )
        res = compile_card(raw, reg)
        self.assertEqual(res.unparsed, ())
        ab = _spell(res.card.abilities[0])
        steps = _seq(ab.effect)
        self.assertEqual(
            steps.steps[0],
            Choose(count=QConst(1), options=(_draw_atom(1), _destroy_atom())),
        )
        # R11-1: "If you do, …" without "may" merges MANDATORILY.
        self.assertEqual(steps.steps[1], _draw_atom(2))


_M21_PATH = Path(__file__).resolve().parents[2] / "data" / "M21.json"


class TestM21Smoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.pool = ingest_pool(_M21_PATH)
        cls.pc = compile_pool(cls.pool, TemplateRegistry())

    def test_all_results_present(self) -> None:
        self.assertEqual(len(self.pc.results), len(self.pool))

    def test_emblems_attached(self) -> None:
        self.assertEqual(self.pc.summary["emblems"], 3)
        self.assertEqual(len(self.pc.orphan_emblems), 0)
        attached = sum(1 for c in self.pc.cards.values() if c.emblem is not None)
        self.assertEqual(attached, 3)

    def test_summary_consistency(self) -> None:
        s = self.pc.summary
        self.assertEqual(s["total"], len(self.pool) - 3)
        self.assertEqual(s["fully_compiled"] + s["partially_compiled"], s["total"])
        self.assertGreater(s["unparsed_count"], 0)
        self.assertGreaterEqual(s["known_gap_count"], 2)

    def test_star_pt_cards_report_gap_not_exception(self) -> None:
        star = [
            r
            for r in self.pc.results.values()
            if r.card.name in ("Weird", "Kinetic Augur")
        ]
        self.assertEqual(len(star), 2)
        for r in star:
            self.assertTrue(
                any(g.startswith("star P/T") for g in r.known_gaps),
                f"{r.card.name} should report a star P/T coverage gap",
            )
            self.assertIsNone(r.card.power)


class TestChooseOpenerM21(unittest.TestCase):
    """The seven M21 choose-opener cards must compile with zero unparsed
    sentences once the built-in is in place (full registry)."""

    EXPECTED_NAMES = (
        "Return to Nature",
        "Pestilent Haze",
        "Read the Tides",
        "Destructive Tampering",
        "Sublime Epiphany",
        "Trufflesnout",
        "Elder Gargaroth",
    )

    @classmethod
    def setUpClass(cls) -> None:
        cls.pool = ingest_pool(_M21_PATH)
        cls.reg = build_full_registry()
        cls.by_name = {raw.identity.name: raw for raw in cls.pool.values()}

    def _compile(self, name: str) -> CompileResult:
        self.assertIn(name, self.by_name, f"{name} missing from M21 pool")
        return compile_card(self.by_name[name], self.reg)

    def test_all_seven_cards_present(self) -> None:
        for name in self.EXPECTED_NAMES:
            self.assertIn(name, self.by_name, f"{name} missing from M21 pool")

    def test_no_unparsed_opener(self) -> None:
        for name in self.EXPECTED_NAMES:
            res = self._compile(name)
            self.assertEqual(res.unparsed, (), f"{name}: {res.unparsed}")

    def test_spell_opener_shape(self) -> None:
        for name in self.EXPECTED_NAMES[:4]:
            res = self._compile(name)
            self.assertEqual(len(res.card.abilities), 1, name)
            ab = _spell(res.card.abilities[0])
            choose = _choose(ab.effect)
            self.assertEqual(choose.count, QConst(1), name)
            self.assertGreaterEqual(len(choose.options), 2, name)

    def test_one_or_more_shape(self) -> None:
        res = self._compile("Sublime Epiphany")
        self.assertEqual(len(res.card.abilities), 1)
        ab = _spell(res.card.abilities[0])
        choose = _choose(ab.effect)
        self.assertEqual(choose.count, QUnbounded())
        self.assertEqual(len(choose.options), 5)

    def test_etb_shape(self) -> None:
        res = self._compile("Trufflesnout")
        self.assertEqual(len(res.card.abilities), 2)  # trigger + C4 cast carrier
        ab = _triggered(res.card.abilities[0])
        event = ab.event
        assert isinstance(event, ZoneChangeEvent)
        self.assertEqual(event.from_zone, Zone(ZoneKind.ANY, ControllerRef.ANY))
        self.assertEqual(event.to_zone, Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU))
        choose = _choose(ab.effect)
        self.assertEqual(choose.count, QConst(1))
        self.assertEqual(len(choose.options), 2)

    def test_attack_block_shape(self) -> None:
        res = self._compile("Elder Gargaroth")
        triggers = [a for a in res.card.abilities if isinstance(a, TriggeredAbility)]
        self.assertEqual(len(triggers), 2)
        self.assertIsInstance(triggers[0].event, DeclareAttackersEvent)
        self.assertIsInstance(triggers[1].event, DeclareBlockersEvent)
        # Both triggers share the same Choose effect.
        choose = _choose(triggers[0].effect)
        self.assertEqual(choose, triggers[1].effect)
        self.assertEqual(choose.count, QConst(1))
        self.assertEqual(len(choose.options), 3)


class TestAdditionalCostM21(unittest.TestCase):
    """The four M21 additional-cost cards must compile cleanly (full
    registry, round-3 behavior): instants keep their effect and gain the
    additional cost; effect-less creatures get an effect-less SpellAbility
    carrying the additional cost. No card raises StateCorruptionError."""

    NAMES = (
        "Goremand",
        "Sparkhunter Masticore",
        "Thrill of Possibility",
        "Village Rites",
    )

    @classmethod
    def setUpClass(cls) -> None:
        cls.pool = ingest_pool(_M21_PATH)
        cls.reg = build_full_registry()
        cls.by_name = {raw.identity.name: raw for raw in cls.pool.values()}

    def _compile(self, name: str) -> CompileResult:
        self.assertIn(name, self.by_name, f"{name} missing from M21 pool")
        return compile_card(self.by_name[name], self.reg)

    def test_all_four_cards_present(self) -> None:
        for name in self.NAMES:
            self.assertIn(name, self.by_name, f"{name} missing from M21 pool")

    def test_exactly_one_spell_with_one_additional_cost(self) -> None:
        for name in self.NAMES:
            res = self._compile(name)
            spells = [a for a in res.card.abilities if isinstance(a, SpellAbility)]
            self.assertEqual(len(spells), 1, name)
            self.assertEqual(len(spells[0].additional_costs), 1, name)

    def test_creatures_are_effectless(self) -> None:
        for name in ("Goremand", "Sparkhunter Masticore"):
            res = self._compile(name)
            spells = [a for a in res.card.abilities if isinstance(a, SpellAbility)]
            self.assertEqual(len(spells), 1, name)
            self.assertIsNone(spells[0].effect, name)

    def test_instants_carry_effect(self) -> None:
        for name in ("Thrill of Possibility", "Village Rites"):
            res = self._compile(name)
            spells = [a for a in res.card.abilities if isinstance(a, SpellAbility)]
            self.assertEqual(len(spells), 1, name)
            self.assertIsNotNone(spells[0].effect, name)

    def test_no_unparsed_additional_cost_sentences(self) -> None:
        for name in self.NAMES:
            res = self._compile(name)
            for sentence, _hint in res.unparsed:
                self.assertFalse(
                    sentence.startswith("As an additional cost"),
                    f"{name}: {sentence!r} left unparsed",
                )


if __name__ == "__main__":
    unittest.main()
