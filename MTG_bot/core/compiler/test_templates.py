"""Tests for the template-matching registry (templates.py)."""

from __future__ import annotations

import re
import unittest
from typing import Any

from MTG_bot.core.ability_tree import (
    Atom,
    AtomArgs,
    ControllerRef,
    Cost,
    Filter,
    Keyword,
    QConst,
    SelectorMode,
    Zone,
    ZoneKind,
)
from MTG_bot.core.compiler.templates import (
    AbilityOutcome,
    AmbiguityRecord,
    EffectOutcome,
    KeywordOutcome,
    Match,
    MetaOutcome,
    RuleReminderOutcome,
    Template,
    TemplateRegistry,
)


def _simple_keyword_template(tid: str, priority: int = 1) -> Template:
    """A template that matches 'Flying' and returns a KeywordOutcome."""
    return Template(
        tid=tid,
        name="flying",
        bucket="B2",
        pattern=re.compile(r"^Flying$"),
        priority=priority,
        build=lambda m: KeywordOutcome(keyword=Keyword.FLYING, params=()),
    )


def _simple_effect_template(tid: str, priority: int = 1) -> Template:
    """A template that matches 'Draw a card.' and returns an EffectOutcome."""
    atom = Atom(
        verb=_DRAW_VERB,
        args=AtomArgs(pairs=(("controller", ControllerRef.YOU), ("amount", QConst(1)))),
    )
    return Template(
        tid=tid,
        name="draw-one",
        bucket="B5",
        pattern=re.compile(r"^Draw a card\.$"),
        priority=priority,
        build=lambda m: EffectOutcome(effect=atom),
    )


# Lazy import to avoid circularity at module level
from MTG_bot.core.ability_tree import Verb as _VERB  # noqa: E402

_DRAW_VERB = _VERB.DRAW


class TestTemplateRegistryRegistration(unittest.TestCase):
    def test_register_and_contains(self) -> None:
        reg = TemplateRegistry()
        t = _simple_keyword_template("t1")
        reg.register(t)
        self.assertIn("t1", reg)
        self.assertEqual(len(reg), 1)

    def test_duplicate_tid_raises(self) -> None:
        reg = TemplateRegistry()
        reg.register(_simple_keyword_template("t1"))
        with self.assertRaises(ValueError) as ctx:
            reg.register(_simple_keyword_template("t1"))
        self.assertIn("t1", str(ctx.exception))

    def test_all_returns_ordered_tuple(self) -> None:
        reg = TemplateRegistry()
        reg.register(_simple_keyword_template("t2", priority=5))
        reg.register(_simple_keyword_template("t1", priority=10))
        reg.register(_simple_keyword_template("t3", priority=5))
        templates = reg.all()
        self.assertIsInstance(templates, tuple)
        self.assertEqual(len(templates), 3)
        # t1 (priority 10) first, then t2/t3 (priority 5, tid asc)
        self.assertEqual(templates[0].tid, "t1")
        self.assertEqual(templates[1].tid, "t2")
        self.assertEqual(templates[2].tid, "t3")

    def test_all_priority_then_tid_ordering(self) -> None:
        reg = TemplateRegistry()
        reg.register(Template(
            tid="b", name="b", bucket="B", pattern=re.compile(r"x"), priority=1,
            build=lambda m: KeywordOutcome(keyword=Keyword.FLYING, params=()),
        ))
        reg.register(Template(
            tid="a", name="a", bucket="B", pattern=re.compile(r"x"), priority=1,
            build=lambda m: KeywordOutcome(keyword=Keyword.FLYING, params=()),
        ))
        reg.register(Template(
            tid="c", name="c", bucket="B", pattern=re.compile(r"x"), priority=2,
            build=lambda m: KeywordOutcome(keyword=Keyword.FLYING, params=()),
        ))
        tids = [t.tid for t in reg.all()]
        self.assertEqual(tids, ["c", "a", "b"])


class TestTemplateMatch(unittest.TestCase):
    def test_fullmatch_only(self) -> None:
        reg = TemplateRegistry()
        reg.register(_simple_keyword_template("t1"))
        # Exact match works
        matches = reg.match("Flying")
        self.assertEqual(len(matches), 1)
        # Partial match does NOT work (fullmatch semantics)
        self.assertEqual(len(reg.match("Flying.")), 0)
        self.assertEqual(len(reg.match("X Flying X")), 0)
        self.assertEqual(len(reg.match("flying")), 0)

    def test_no_match_returns_empty_tuple(self) -> None:
        reg = TemplateRegistry()
        reg.register(_simple_keyword_template("t1"))
        self.assertEqual(reg.match("Some other sentence"), ())

    def test_multiple_matches(self) -> None:
        reg = TemplateRegistry()
        reg.register(_simple_keyword_template("t1", priority=1))
        reg.register(_simple_keyword_template("t2", priority=10))
        matches = reg.match("Flying")
        self.assertEqual(len(matches), 2)
        # Higher priority first
        self.assertEqual(matches[0].template.tid, "t2")
        self.assertEqual(matches[1].template.tid, "t1")

    def test_match_returns_match_objects(self) -> None:
        reg = TemplateRegistry()
        reg.register(_simple_keyword_template("t1"))
        matches = reg.match("Flying")
        self.assertIsInstance(matches[0], Match)
        self.assertIsInstance(matches[0].template, Template)
        self.assertIsInstance(matches[0].outcome, KeywordOutcome)

    def test_build_exception_propagates(self) -> None:
        def _boom(m: re.Match[str]) -> KeywordOutcome:
            raise RuntimeError("template bug")

        reg = TemplateRegistry()
        reg.register(Template(
            tid="t1", name="boom", bucket="B",
            pattern=re.compile(r"^Flying$"), priority=1,
            build=_boom,
        ))
        with self.assertRaises(RuntimeError) as ctx:
            reg.match("Flying")
        self.assertIn("template bug", str(ctx.exception))


class TestSentenceOutcomes(unittest.TestCase):
    def test_keyword_outcome_frozen(self) -> None:
        ko = KeywordOutcome(keyword=Keyword.FLYING, params=())
        with self.assertRaises(AttributeError):
            ko.keyword = Keyword.HASTE  # type: ignore[misc]

    def test_rule_reminder_outcome(self) -> None:
        rr = RuleReminderOutcome(reason="full_paren")
        self.assertEqual(rr.reason, "full_paren")
        rr2 = RuleReminderOutcome(reason="keyword_reminder")
        self.assertEqual(rr2.reason, "keyword_reminder")

    def test_meta_outcome(self) -> None:
        meta = MetaOutcome(kind="enchant", filter=None)
        self.assertEqual(meta.kind, "enchant")
        self.assertIsNone(meta.filter)

    def test_ambiguity_record_frozen(self) -> None:
        ar = AmbiguityRecord(
            sentence="Flying",
            tids=("t1", "t2"),
            note="2 templates matched",
        )
        self.assertEqual(ar.sentence, "Flying")
        self.assertEqual(ar.tids, ("t1", "t2"))
        self.assertEqual(ar.note, "2 templates matched")
        with self.assertRaises(AttributeError):
            ar.sentence = "other"  # type: ignore[misc]

    def test_effect_outcome(self) -> None:
        atom = Atom(
            verb=_DRAW_VERB,
            args=AtomArgs(pairs=(("controller", ControllerRef.YOU), ("amount", QConst(1)))),
        )
        eo = EffectOutcome(effect=atom)
        self.assertIsInstance(eo.effect, Atom)


class TestTemplateDataclass(unittest.TestCase):
    def test_template_frozen(self) -> None:
        t = _simple_keyword_template("t1")
        with self.assertRaises(AttributeError):
            t.tid = "other"  # type: ignore[misc]

    def test_template_fields(self) -> None:
        t = _simple_keyword_template("t42", priority=7)
        self.assertEqual(t.tid, "t42")
        self.assertEqual(t.name, "flying")
        self.assertEqual(t.bucket, "B2")
        self.assertIsInstance(t.pattern, re.Pattern)
        self.assertEqual(t.priority, 7)
        self.assertTrue(callable(t.build))


if __name__ == "__main__":
    unittest.main()
