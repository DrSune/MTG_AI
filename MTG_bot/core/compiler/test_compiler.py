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
from pathlib import Path
from typing import Callable

from MTG_bot.core.ability_tree import (
    Ability,
    ActivatedAbility,
    Atom,
    AtomArgs,
    ControllerRef,
    Cost,
    CostManaColor,
    CostManaGeneric,
    CostManaHybrid,
    CostTap,
    Effect,
    FAtom,
    FAtomPred,
    FAnd,
    Filter,
    Keyword,
    KeywordAbility,
    OptionalEffect,
    QConst,
    QX,
    Selector,
    SelectorMode,
    Seq,
    SpellAbility,
    SpellKind,
    StaticAbility,
    Verb,
    Zone,
    ZoneKind,
)
from MTG_bot.core.compiler.compiler import (
    CompileResult,
    _bucket_hint,
    compile_card,
    compile_pool,
    parse_mana_cost,
    parse_pt,
)
from MTG_bot.core.compiler.ingest import RawCard, ingest_pool
from MTG_bot.core.compiler.templates import (
    AbilityOutcome,
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
            pairs=(("controller", ControllerRef.YOU), ("amount", QConst(1)), ("color", "W"))
        ),
    )


def _target_selector() -> Selector:
    return Selector(
        count=QConst(1),
        mode=SelectorMode.TARGET,
        filter=FAtom(pred=FAtomPred.SUBTYPE_EQ, string_value="creature"),
        zone=Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),
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


def _seq(effect: Effect) -> Seq:
    if not isinstance(effect, Seq):
        raise AssertionError(f"expected Seq, got {type(effect).__name__}")
    return effect


def _atom(effect: Effect) -> Atom:
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
        self.assertEqual(
            cost.parts,
            (
                CostManaGeneric(QConst(2)),
                CostManaColor("W", QConst(1)),
                CostManaColor("U", QConst(1)),
                CostManaColor("G", QConst(1)),
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
        self.assertEqual(
            _bucket_hint("Creatures you control get +1/+1."), "static"
        )
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
        self.assertEqual(
            res.rule_reminders, (RuleReminderOutcome("keyword_reminder"),)
        )
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
        self.assertEqual(res.card.keywords, (KeywordAbility(Keyword.HEXPROOF, (filt,)),))


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
        filt = FAtom(pred=FAtomPred.COLOR_HAS, color="B")
        raw = _raw_card(
            "C",
            1,
            types=("Creature", "Card"),
            keywords=("Hexproof",),
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
        self.assertEqual(
            res.card.keywords,
            (KeywordAbility(Keyword.HEXPROOF, ()), KeywordAbility(Keyword.HEXPROOF, (filt,))),
        )

    def test_unbuildable_keywords_reported(self) -> None:
        raw = _raw_card(
            "C", 1, types=("Creature", "Card"), keywords=("Scry", "Mill")
        )
        res = compile_card(raw, TemplateRegistry())
        self.assertEqual(res.card.keywords, ())
        self.assertEqual(len(res.known_gaps), 2)
        self.assertTrue(any("Scry" in g for g in res.known_gaps))
        self.assertTrue(any("Mill" in g for g in res.known_gaps))

    def test_hexproof_from_reported(self) -> None:
        raw = _raw_card(
            "C", 1, types=("Creature", "Card"), keywords=("Hexproof from",)
        )
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
        raw = _raw_card(
            "I", 1, sentences=("Draw a card.", "If you do, draw another.")
        )
        reg = TemplateRegistry()
        _draw_templates(reg)
        res = compile_card(raw, reg)
        self.assertEqual(res.unparsed, ())
        self.assertEqual(len(res.card.abilities), 1)
        ab = _spell(res.card.abilities[0])
        steps = _seq(ab.effect)
        self.assertEqual(steps.steps[0], _draw_atom(1))
        self.assertEqual(steps.steps[1], OptionalEffect(_draw_atom(2)))

    def test_continuation_without_previous_effect(self) -> None:
        raw = _raw_card("I", 1, sentences=("If you do, draw another.",))
        reg = TemplateRegistry()
        _draw_templates(reg)
        res = compile_card(raw, reg)
        ab = _spell(res.card.abilities[0])
        self.assertEqual(ab.effect, OptionalEffect(_draw_atom(2)))

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
        self.assertEqual(
            res.rule_reminders, (RuleReminderOutcome("keyword_reminder"),)
        )
        ab = _spell(res.card.abilities[0])
        steps = _seq(ab.effect)
        self.assertEqual(steps.steps[0], _draw_atom(1))
        self.assertEqual(steps.steps[1], OptionalEffect(_draw_atom(2)))

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
        # effect is left to fold.
        self.assertEqual(
            res.card.abilities,
            (
                StaticAbility(
                    effect=Seq(steps=(_draw_atom(1), OptionalEffect(_draw_atom(2))))
                ),
            ),
        )


# ---------------------------------------------------------------------------
# Meta-filter conjunction (Enchant X)
# ---------------------------------------------------------------------------


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
            _template("d", r"^Draw a card\.$", lambda m: EffectOutcome(effect=_draw_atom()))
        )
        res = compile_card(raw, reg)
        card = res.card
        self.assertEqual(card.mana_cost, parse_mana_cost("{1}{W}"))
        self.assertEqual(card.power, QConst(2))
        self.assertEqual(card.toughness, QConst(2))
        self.assertEqual(
            card.abilities, (SpellAbility(kind=SpellKind.CREATURE, effect=_draw_atom()),)
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
            _template("d", r"^Draw a card\.$", lambda m: EffectOutcome(effect=_draw_atom()))
        )
        res = compile_card(raw, reg)
        ab = _spell(res.card.abilities[0])
        self.assertIs(ab.kind, SpellKind.INSTANT)
        self.assertEqual(len(_seq(ab.effect).steps), 2)

    def test_sorcery_kind(self) -> None:
        raw = _raw_card(
            "S", 1, types=("Sorcery", "Card"), sentences=("Draw a card.",)
        )
        reg = TemplateRegistry()
        reg.register(
            _template("d", r"^Draw a card\.$", lambda m: EffectOutcome(effect=_draw_atom()))
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
            _template("d", r"^Draw a card\.$", lambda m: EffectOutcome(effect=_draw_atom()))
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
            _template("d", r"^Draw a card\.$", lambda m: EffectOutcome(effect=_draw_atom()))
        )
        res = compile_card(raw, reg)
        self.assertTrue(res.card.is_token)
        self.assertEqual(
            res.card.abilities, (StaticAbility(effect=_draw_atom()),)
        )

    def test_land_tap_ability(self) -> None:
        raw = _raw_card("L", 1, types=("Land", "Basic", "Card"), subtypes=("Plains",),
                       sentences=("({T}: Add {W}.)",))
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
            (
                ActivatedAbility(
                    cost=Cost(parts=(CostTap(),)), effect=_add_mana_atom()
                ),
            ),
        )
        self.assertIsNone(res.card.mana_cost)


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
            _template("d", r"^Draw a card\.$", lambda m: EffectOutcome(effect=_draw_atom()))
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
            _template("d", r"^Draw a card\.$", lambda m: EffectOutcome(effect=_draw_atom()))
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
        owner = _raw_card(
            "Owner", 1, types=("Planeswalker", "Card"), loyalty_raw="3"
        )
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


if __name__ == "__main__":
    unittest.main()
