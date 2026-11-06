"""Tests for the B6 bucket (templates_b6.py), the Kicker family:

- kicker heads: with the reminder, bare, and ``{X}``; a reminder that does
  not repeat the cost never matches;
- the gated entering state (``EtBState(condition=WAS_KICKED)``); an ungated
  EtBState serializes without a condition key;
- kicker-gated ETB triggers and cast triggers;
- the compiler's fold of spell arms: additive Seq-append and the "instead"
  replacement ``Conditional(WAS_KICKED, arm, else=base)``;
- hand-built goldens derived from the oracle text (Kitesail Cleric, Roost of
  Drakes, Bloodchief's Thirst) and the Thieving Skydiver ``Kicker {X}`` head;
- unmapped tails (Taunting Arbormage's block tail) never match.
"""

from __future__ import annotations

import re
import unittest
import uuid

from MTG_bot.core.ability_tree import (
    QX,
    Atom,
    AtomArgs,
    CastSpellEvent,
    Conditional,
    ControllerRef,
    Cost,
    CostManaGeneric,
    CounterKind,
    EtBState,
    FAnd,
    FAtom,
    FAtomPred,
    FOr,
    Keyword,
    KickerAbility,
    QAtMost,
    QConst,
    Selector,
    SelectorMode,
    Seq,
    SpellAbility,
    SpellKind,
    TokenSpec,
    TriggeredAbility,
    Verb,
    Zone,
    ZoneChangeEvent,
    ZoneKind,
    canonical_json,
    from_dict,
    to_dict,
)
from MTG_bot.core.compiler.compiler import (
    compile_card,
    parse_mana_cost,
)
from MTG_bot.core.compiler.coverage import build_full_registry
from MTG_bot.core.compiler.ingest import CardIdentity, RawCard
from MTG_bot.core.compiler.templates import (
    AbilityOutcome,
    KickerEffectOutcome,
)
from MTG_bot.core.compiler.templates_b6 import (
    _TAIL_BUILDERS,
    TEMPLATES,
    _build_kicker_additive,
    _build_kicker_head,
    _build_kicker_replaces,
)
from MTG_bot.core.errors import StateCorruptionError

REGISTRY = build_full_registry()


def _template(tid: str):
    for t in TEMPLATES:
        if t.tid == tid:
            return t
    raise AssertionError(f"template {tid} missing")


def _b6_match(tid: str, sentence: str) -> re.Match[str] | None:
    """Fullmatch ``sentence`` against the B6 template ``tid`` only."""
    return _template(tid).pattern.fullmatch(sentence)


def _b6_m(tid: str, sentence: str) -> re.Match[str]:
    """Match that must succeed (Pyright type guard)."""
    m = _b6_match(tid, sentence)
    if m is None:
        raise AssertionError(f"{tid} did not match {sentence!r}")
    return m


def _as_ability(outcome: object) -> AbilityOutcome:
    """Narrow to AbilityOutcome (Pyright type guard)."""
    if not isinstance(outcome, AbilityOutcome):
        raise AssertionError(  # noqa: TRY004
            f"expected AbilityOutcome, got {type(outcome)}"
        )
    return outcome


def _as_trigger(ability: object) -> TriggeredAbility:
    """Narrow to TriggeredAbility (Pyright type guard)."""
    if not isinstance(ability, TriggeredAbility):
        raise AssertionError(  # noqa: TRY004
            f"expected TriggeredAbility, got {type(ability)}"
        )
    return ability


def _as_kicker(ability: object) -> KickerAbility:
    """Narrow to KickerAbility (Pyright type guard)."""
    if not isinstance(ability, KickerAbility):
        raise AssertionError(  # noqa: TRY004
            f"expected KickerAbility, got {type(ability)}"
        )
    return ability


def _as_seq(effect: object) -> Seq:
    """Narrow to Seq (Pyright type guard)."""
    if not isinstance(effect, Seq):
        raise AssertionError(  # noqa: TRY004
            f"expected Seq, got {type(effect)}"
        )
    return effect


def _as_conditional(effect: object) -> Conditional:
    """Narrow to Conditional (Pyright type guard)."""
    if not isinstance(effect, Conditional):
        raise AssertionError(  # noqa: TRY004
            f"expected Conditional, got {type(effect)}"
        )
    return effect


def _cost(raw: str) -> Cost:
    """parse_mana_cost with the non-None the callers here guarantee."""
    cost = parse_mana_cost(raw)
    if cost is None:
        raise AssertionError(f"unparseable cost {raw!r}")
    return cost


def _any_b6_match(sentence: str) -> str | None:
    """The tid of the (at most one) B6 template matching the sentence."""
    hits = [t.tid for t in TEMPLATES if t.pattern.fullmatch(sentence)]
    assert len(hits) <= 1, f"PC-3 violated: {hits} all match {sentence!r}"
    return hits[0] if hits else None


def _raw(
    name: str,
    sentences: tuple[str, ...],
    *,
    types: tuple[str, ...] = ("Instant",),
    subtypes: tuple[str, ...] = (),
    colors: tuple[str, ...] = (),
    mana_cost_raw: str | None = None,
    mana_value: int = 0,
    power_raw: str | None = None,
    toughness_raw: str | None = None,
    keywords: tuple[str, ...] = (),
) -> RawCard:
    """Minimal RawCard stub for end-to-end compile_card tests."""
    identity = CardIdentity(
        oracle_id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"mtg://{name}")),
        name=name,
    )
    type_line = " ".join(types)
    if subtypes:
        type_line += " — " + " ".join(subtypes)
    return RawCard(
        identity=identity,
        type_line=type_line,
        types=types,
        subtypes=subtypes,
        supertypes=(),
        colors=colors,
        color_identity=frozenset(colors),
        mana_cost_raw=mana_cost_raw,
        mana_value=mana_value,
        power_raw=power_raw,
        toughness_raw=toughness_raw,
        loyalty_raw=None,
        keywords=keywords,
        sentences=sentences,
        layout="normal",
        is_token=False,
        is_emblem=False,
        token_name_refs=(),
        related_names=(),
    )


# ---------------------------------------------------------------------------
# Hand-built expected trees, derived from the oracle clauses rather than from
# the builders in templates_b6.
# ---------------------------------------------------------------------------

_KICKED = FAtom(pred=FAtomPred.WAS_KICKED)


def _etb_event() -> ZoneChangeEvent:
    return ZoneChangeEvent(
        from_zone=Zone(ZoneKind.ANY, ControllerRef.ANY),
        to_zone=Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU),
        subject=FAtom(pred=FAtomPred.IS_SOURCE),
    )


def _tap_up_to_two() -> Atom:
    return Atom(
        verb=Verb.TAP,
        args=AtomArgs(
            pairs=(
                (
                    "target",
                    Selector(
                        QAtMost(2),
                        SelectorMode.TARGET,
                        FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                        zones=(Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),),
                    ),
                ),
            )
        ),
    )


def _drake_token(count: int) -> Atom:
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
                        colors=("U",),
                    ),
                ),
                ("count", QConst(count)),
            )
        ),
    )


def _draw(amount: int) -> Atom:
    return Atom(
        verb=Verb.DRAW,
        args=AtomArgs(
            pairs=(
                ("controller", ControllerRef.YOU),
                ("amount", QConst(amount)),
            )
        ),
    )


def _destroy_cw_pw(mv_le: int | None) -> Atom:
    def arm(type_name: str) -> FAnd | FAtom:
        type_atom = FAtom(pred=FAtomPred.TYPE_EQ, string_value=type_name)
        if mv_le is None:
            return type_atom  # a bare FAtom when there is no mana value bound
        return FAnd(
            children=(
                type_atom,
                FAtom(pred=FAtomPred.CMC_LE, count=QConst(mv_le)),
            )
        )

    return Atom(
        verb=Verb.DESTROY,
        args=AtomArgs(
            pairs=(
                (
                    "target",
                    Selector(
                        QConst(1),
                        SelectorMode.TARGET,
                        FOr(children=(arm("Creature"), arm("Planeswalker"))),
                        zones=(Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),),
                    ),
                ),
            )
        ),
    )


# ===========================================================================
# 1. Kicker heads
# ===========================================================================


class TestKickerHead(unittest.TestCase):
    def test_head_parenthetical(self) -> None:
        m = _b6_m(
            "B6-kicker-head",
            "Kicker {2}{W} (You may pay an additional {2}{W} as you cast this spell.)",
        )
        out = _build_kicker_head(m)
        self.assertEqual(
            _as_ability(out).ability,
            KickerAbility(cost=_cost("{2}{W}")),
        )

    def test_head_bare(self) -> None:
        m = _b6_m("B6-kicker-head", "Kicker {3}")
        self.assertEqual(
            _as_ability(_build_kicker_head(m)).ability,
            KickerAbility(cost=_cost("{3}")),
        )

    def test_head_x_adversarial(self) -> None:
        """X-cost kicker (Thieving Skydiver): the head must carry QX."""
        m = _b6_m("B6-kicker-head", "Kicker {X}.")
        head = _as_kicker(_as_ability(_build_kicker_head(m)).ability)
        self.assertEqual(head.cost, Cost(parts=(_X_PART,)))
        # round-trip through the serializer
        d = to_dict(head)
        self.assertEqual(
            canonical_json(from_dict(d["tag"], d)),
            canonical_json(head),
        )

    def test_head_nonmirroring_paren_never_matches(self) -> None:
        """A reminder that does not repeat the cost leaves the sentence unmatched, never
        mis-parsed."""
        self.assertIsNone(
            _b6_match(
                "B6-kicker-head",
                "Kicker {W} (You may pay an additional {U} as you cast this spell.)",
            )
        )
        self.assertIsNone(
            _any_b6_match(
                "Kicker {W} (You may pay an additional {U} as you cast this spell.)"
            )
        )

    def test_head_other_b6_templates_claim_nothing(self) -> None:
        self.assertEqual(
            _any_b6_match(
                "Kicker {2}{U} (You may pay an additional {2}{U} as you cast this spell.)"
            ),
            "B6-kicker-head",
        )


_X_PART = CostManaGeneric(QX())


# ===========================================================================
# 2. Gated entering state (conditional EtBState)
# ===========================================================================


class TestKickerEtbCounters(unittest.TestCase):
    def test_word_counts(self) -> None:
        for word, n in (("a", 1), ("one", 1), ("two", 2), ("three", 3), ("four", 4)):
            m = _b6_match(
                "B6-kicker-etb-counters",
                f"If this creature was kicked, it enters with {word} +1/+1 "
                "counters on it."
                if word != "a" and word != "one"
                else f"If this creature was kicked, it enters with {word} "
                "+1/+1 counter on it.",
            )
            self.assertIsNotNone(m, word)

    def test_two_counters_shape(self) -> None:
        m = _b6_m(
            "B6-kicker-etb-counters",
            "If this creature was kicked, it enters with two +1/+1 counters on it.",
        )
        out = _template("B6-kicker-etb-counters").build(m)
        self.assertEqual(
            _as_ability(out).ability,
            EtBState(
                initial_counters=((CounterKind.PLUS_1_PLUS_1, QConst(2)),),
                condition=_KICKED,
            ),
        )

    def test_ungated_etb_bytes_unchanged(self) -> None:
        """An EtBState without a condition serializes with no 'condition' key."""
        d = to_dict(
            EtBState(initial_counters=((CounterKind.PLUS_1_PLUS_1, QConst(1)),))
        )
        self.assertNotIn("condition", d)

    def test_gated_roundtrip(self) -> None:
        node = EtBState(
            initial_counters=((CounterKind.PLUS_1_PLUS_1, QConst(2)),),
            condition=_KICKED,
        )
        d = to_dict(node)
        self.assertIn("condition", d)
        self.assertEqual(canonical_json(from_dict(d["tag"], d)), canonical_json(node))


# ===========================================================================
# 3. Kicker-gated triggers
# ===========================================================================


class TestKickerTriggers(unittest.TestCase):
    def test_etb_kicked_trigger(self) -> None:
        m = _b6_m(
            "B6-etb-kicked-trigger",
            "When this creature enters, if it was kicked, tap up to two target "
            "creatures.",
        )
        out = _template("B6-etb-kicked-trigger").build(m)
        self.assertEqual(
            _as_ability(out).ability,
            TriggeredAbility(
                event=_etb_event(),
                condition=_KICKED,
                effect=_tap_up_to_two(),
            ),
        )

    def test_cast_kicked_trigger(self) -> None:
        m = _b6_m(
            "B6-cast-kicked-trigger",
            "Whenever you cast a kicked spell, create a 2/2 blue Drake "
            "creature token with flying.",
        )
        out = _template("B6-cast-kicked-trigger").build(m)
        ab = _as_trigger(_as_ability(out).ability)
        self.assertEqual(
            ab.event,
            CastSpellEvent(
                filter=_KICKED,
                actor=FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
            ),
        )
        self.assertIsNone(ab.condition)  # the filter carries the gate
        self.assertEqual(ab.effect, _drake_token(1))

    def test_enchantment_etb_variant(self) -> None:
        m = _b6_match(
            "B6-etb-kicked-trigger",
            "When this enchantment enters, if it was kicked, create a 2/2 "
            "blue Drake creature token with flying.",
        )
        self.assertIsNotNone(m)


# ===========================================================================
# 4. Tail builders — every mapped tail constructs without error
# ===========================================================================


class TestTailBuilders(unittest.TestCase):
    def test_every_tail_builder_builds(self) -> None:
        for tail, fn in _TAIL_BUILDERS.items():
            with self.subTest(tail=tail):
                fn()


# ===========================================================================
# 5. Compiler fold — additive and replacement arms
# ===========================================================================


class TestInsteadFoldFailurePaths(unittest.TestCase):
    """An "instead" arm is never silently dropped and never folded onto a base that does not
    exist."""

    def test_orphan_instead_arm_raises(self) -> None:
        """An instead arm that is the card's first effect (the kicker head is not an effect),
        with no unparsed sentence before it, raises StateCorruptionError instead of folding
        standalone."""
        raw = _raw(
            "Test Orphan Instead",
            (
                _KICKER_HEAD,
                (
                    "If this spell was kicked, instead destroy "
                    "target creature or planeswalker."
                ),
            ),
        )
        with self.assertRaises(StateCorruptionError):
            compile_card(raw, REGISTRY)

    def test_instead_arm_with_unparsed_base_stays_residue(self) -> None:
        """A replacement arm whose base sentence is unparsed stays unparsed too, and no
        WAS_KICKED Conditional is built: a standalone fold would mean "un-kicked → no effect"
        (an un-kicked Roil Eruption still deals 3 damage)."""
        raw = _raw(
            "Test Unparsed Base Instead",
            (
                _KICKER_HEAD,
                "Fizzle the fizzwig for each kicker you paid.",  # unmatched
                (
                    "If this spell was kicked, instead destroy "
                    "target creature or planeswalker."
                ),
            ),
        )
        res = compile_card(raw, REGISTRY)
        # Both clauses are unparsed, in sentence order.
        self.assertEqual(len(res.unparsed), 2, f"register: {res.unparsed}")
        self.assertIn("Fizzle", res.unparsed[0][0])
        self.assertIn("was kicked", res.unparsed[1][0])
        # No conditional was built: no gated arm and no DESTROY on the card.
        text = repr(res.card)
        self.assertNotIn("WAS_KICKED", text)
        self.assertNotIn("DESTROY", text)

    def test_instead_arm_does_not_attach_across_residue(self) -> None:
        """The backward fold search stops at the unparsed slot, which is the arm's base: the arm
        never merges onto an unrelated earlier effect ("You gain 3 life." must not become the
        else_effect)."""
        raw = _raw(
            "Test Kicker Misfold Repro",
            (
                _KICKER_HEAD,
                "You gain 3 life.",  # compiles: an unrelated earlier effect
                "Fizzle the fizzwig for each kicker you paid.",  # residue
                (
                    "If this spell was kicked, instead destroy "
                    "target creature or planeswalker."
                ),
            ),
        )
        res = compile_card(raw, REGISTRY)
        text = repr(res.card)
        # No fold at all: no WAS_KICKED node, so GAIN_LIFE cannot be an else_effect.
        self.assertNotIn("WAS_KICKED", text)
        # The unrelated effect survived on its own (not swallowed).
        self.assertIn("GAIN_LIFE", text)
        # Both uncovered clauses are unparsed.
        self.assertEqual(len(res.unparsed), 2, f"register: {res.unparsed}")
        self.assertIn("Fizzle", res.unparsed[0][0])
        self.assertIn("was kicked", res.unparsed[1][0])

    def test_instead_arm_with_compiled_base_still_folds(self) -> None:
        """Positive control: an arm after a compiled base folds to
        Conditional(then=arm, else=base)."""
        raw = _raw(
            "Test Positive Control Fold",
            (
                _KICKER_HEAD,
                "Destroy target creature or planeswalker with mana value 2 or less.",
                (
                    "If this spell was kicked, instead destroy "
                    "target creature or planeswalker."
                ),
            ),
        )
        res = compile_card(raw, REGISTRY)
        self.assertEqual(res.unparsed, ())
        spell = next(a for a in res.card.abilities if isinstance(a, SpellAbility))
        cond = _as_conditional(spell.effect)
        self.assertEqual(cond.pred, _KICKED)
        self.assertEqual(cond.then_effect, _destroy_cw_pw(None))
        self.assertEqual(cond.else_effect, _destroy_cw_pw(2))


_KICKER_HEAD = (
    "Kicker {2}{G} (You may pay an additional {2}{G} as you cast this spell.)"
)
_KICKER_HEAD_U = (
    "Kicker {2}{U} (You may pay an additional {2}{U} as you cast this spell.)"
)
_KICKER_HEAD_B = (
    "Kicker {2}{B} (You may pay an additional {2}{B} as you cast this spell.)"
)


class TestKickerFold(unittest.TestCase):
    def test_additive_fold_appends_gated_arm(self) -> None:
        """An additive arm folds onto the previous effect-bearing slot: here an ETB trigger,
        rebuilt with the merged Seq."""
        raw = _raw(
            "Test Additive Kicker",
            (
                _KICKER_HEAD,
                "When this creature enters, draw a card.",
                "If this spell was kicked, draw a card.",
            ),
            types=("Creature",),
            subtypes=("Bird",),
            colors=("W",),
            mana_cost_raw="{1}{W}",
            mana_value=2,
            power_raw="1",
            toughness_raw="1",
        )
        res = compile_card(raw, REGISTRY)
        self.assertEqual(res.unparsed, (), f"residue: {res.unparsed}")
        trig = _as_trigger(
            next(
                ab.ability if isinstance(ab, AbilityOutcome) else ab
                for ab in res.card.abilities
                if isinstance(ab, TriggeredAbility)
            )
        )
        seq = _as_seq(trig.effect)
        self.assertEqual(len(seq.steps), 2)
        arm = _as_conditional(seq.steps[1])
        self.assertEqual(arm.pred, _KICKED)
        self.assertEqual(arm.then_effect, _draw(1))
        self.assertIsNone(arm.else_effect)

    def test_replaces_fold_conditional_with_else(self) -> None:
        raw = _raw(
            "Test Replaces Kicker",
            (
                _KICKER_HEAD_B,
                "Destroy target creature or planeswalker with mana value 2 or less.",
                (
                    "If this spell was kicked, instead destroy target creature "
                    "or planeswalker."
                ),
            ),
            types=("Sorcery",),
            colors=("B",),
            mana_cost_raw="{B}",
            mana_value=1,
        )
        res = compile_card(raw, REGISTRY)
        self.assertEqual(res.unparsed, ())
        spell = next(a for a in res.card.abilities if isinstance(a, SpellAbility))
        cond = _as_conditional(spell.effect)
        self.assertEqual(cond.pred, _KICKED)
        self.assertEqual(cond.then_effect, _destroy_cw_pw(None))
        self.assertEqual(cond.else_effect, _destroy_cw_pw(2))

    def test_instead_suffix_fold(self) -> None:
        """The suffix idiom ('If it was kicked, X instead.') folds onto a compiled base."""
        raw = _raw(
            "Test Suffix Kicker",
            (
                "Kicker {R} (You may pay an additional {R} as you cast this spell.)",
                "Destroy target creature or planeswalker with mana value 2 or less.",
                "If it was kicked, draw three cards instead.",
            ),
            types=("Sorcery",),
            colors=("R",),
            mana_cost_raw="{1}{R}",
            mana_value=2,
        )
        res = compile_card(raw, REGISTRY)
        kicker_rows = [u for u in res.unparsed if "kicked" in u[0]]
        self.assertEqual(kicker_rows, [], f"kicker row left unparsed: {kicker_rows}")
        spell = next(a for a in res.card.abilities if isinstance(a, SpellAbility))
        self.assertEqual(
            spell.effect,
            Conditional(
                pred=_KICKED,
                then_effect=_draw(3),
                else_effect=_destroy_cw_pw(2),
            ),
        )

    def test_instead_arm_without_base_is_honest_residue(self) -> None:
        """An 'instead' arm whose base failed to compile stays unparsed: never silently
        dropped, never a crash."""
        raw = _raw(
            "Test Orphan Instead",
            (
                _KICKER_HEAD_B,
                "Test Orphan Instead destroys target creature or planeswalker.",
                (
                    "If this spell was kicked, instead destroy target creature or "
                    "planeswalker."
                ),
            ),
            types=("Sorcery",),
            colors=("B",),
            mana_cost_raw="{B}",
            mana_value=1,
        )
        res = compile_card(raw, REGISTRY)
        # With the base unparsed, a standalone fold would mean "un-kicked → no
        # effect", so both clauses stay unparsed and no WAS_KICKED node is built.
        self.assertEqual(len(res.unparsed), 2, f"register: {res.unparsed}")
        self.assertIn("kicked", res.unparsed[-1][0])
        self.assertNotIn("WAS_KICKED", repr(res.card))

    def test_fold_helpers_are_template_facing(self) -> None:
        """The three build functions the registry entries call."""
        m = _b6_m("B6-kicker-additive", "If this spell was kicked, draw a card.")
        out = _build_kicker_additive(m)
        self.assertEqual(out, KickerEffectOutcome(effect=_draw(1), replaces=False))
        m2 = _b6_m(
            "B6-kicker-instead-prefix",
            "If this spell was kicked, instead destroy target creature or "
            "planeswalker.",
        )
        self.assertEqual(
            _build_kicker_replaces(m2),
            KickerEffectOutcome(effect=_destroy_cw_pw(None), replaces=True),
        )


# ===========================================================================
# 6. Hand-certified goldens (trees derived from oracle-text clauses)
# ===========================================================================


class TestHandCertifiedGoldens(unittest.TestCase):
    def test_kitesail_cleric(self) -> None:
        """'Kicker {2}{W} (…)' / 'Flying' / 'When this creature enters, if
        it was kicked, tap up to two target creatures.' — head + Flying +
        gated ETB trigger."""
        raw = _raw(
            "Kitesail Cleric",
            (
                (
                    "Kicker {2}{W} (You may pay an additional {2}{W} as you cast "
                    "this spell.)"
                ),
                "Flying",
                (
                    "When this creature enters, if it was kicked, tap up to two "
                    "target creatures."
                ),
            ),
            types=("Creature",),
            subtypes=("Kor", "Cleric"),
            colors=("W",),
            mana_cost_raw="{W}",
            mana_value=1,
            power_raw="1",
            toughness_raw="1",
            keywords=("Flying",),
        )
        res = compile_card(raw, REGISTRY)
        self.assertEqual(res.unparsed, ())
        expected = (
            KickerAbility(cost=_cost("{2}{W}")),
            TriggeredAbility(
                event=_etb_event(),
                condition=_KICKED,
                effect=_tap_up_to_two(),
            ),
        )
        got = tuple(a for a in res.card.abilities if not isinstance(a, SpellAbility))
        self.assertEqual(canonical_json(got), canonical_json(expected))

    def test_roost_of_drakes(self) -> None:
        """Head + gated ETB trigger (drake) + cast trigger (drake), plus the effect-less
        SpellAbility carrier: a card with no effect sentence needs it to be castable at all
        (legality.py spell_castable)."""
        raw = _raw(
            "Roost of Drakes",
            (
                (
                    "Kicker {2}{U} (You may pay an additional {2}{U} as you cast "
                    "this spell.)"
                ),
                (
                    "When this enchantment enters, if it was kicked, create a 2/2 "
                    "blue Drake creature token with flying."
                ),
                (
                    "Whenever you cast a kicked spell, create a 2/2 blue Drake "
                    "creature token with flying."
                ),
            ),
            types=("Enchantment",),
            colors=("U",),
            mana_cost_raw="{U}",
            mana_value=1,
        )
        res = compile_card(raw, REGISTRY)
        self.assertEqual(res.unparsed, ())
        expected = (
            KickerAbility(cost=_cost("{2}{U}")),
            TriggeredAbility(
                event=_etb_event(),
                condition=_KICKED,
                effect=_drake_token(1),
            ),
            TriggeredAbility(
                event=CastSpellEvent(
                    filter=_KICKED,
                    actor=FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
                ),
                condition=None,
                effect=_drake_token(1),
            ),
            SpellAbility(kind=SpellKind.ENCHANTMENT),
        )
        self.assertEqual(
            canonical_json(tuple(res.card.abilities)), canonical_json(expected)
        )

    def test_bloodchiefs_thirst(self) -> None:
        """Base arm MV≤2 destroy; kicked arm unbounded destroy INSTEAD."""
        raw = _raw(
            "Bloodchief's Thirst",
            (
                (
                    "Kicker {2}{B} (You may pay an additional {2}{B} as you cast "
                    "this spell.)"
                ),
                "Destroy target creature or planeswalker with mana value 2 or less.",
                (
                    "If this spell was kicked, instead destroy target creature "
                    "or planeswalker."
                ),
            ),
            types=("Sorcery",),
            colors=("B",),
            mana_cost_raw="{B}",
            mana_value=1,
        )
        res = compile_card(raw, REGISTRY)
        self.assertEqual(res.unparsed, ())
        spell = next(a for a in res.card.abilities if isinstance(a, SpellAbility))
        self.assertEqual(
            spell.effect,
            Conditional(
                pred=_KICKED,
                then_effect=_destroy_cw_pw(None),
                else_effect=_destroy_cw_pw(2),
            ),
        )


# ===========================================================================
# 7. Unmapped tails never match
# ===========================================================================


class TestHonestResidue(unittest.TestCase):
    def test_arbormage_block_tail_unmatched(self) -> None:
        self.assertIsNone(
            _any_b6_match(
                "When this creature enters, if it was kicked, all creatures "
                "able to block target creature this turn do so."
            )
        )

    def test_skydiver_full_text_unit_level(self) -> None:
        """Thieving Skydiver's 'Kicker {X}. X can't be 0. (…)': the splitter emits
        'Kicker {X}.' on its own, which the head template claims; 'X can't be 0.' stays
        unparsed."""
        m = _b6_match("B6-kicker-head", "Kicker {X}.")
        self.assertIsNotNone(m)
        self.assertIsNone(_b6_match("B6-kicker-head", "X can't be 0."))

    def test_m21_pool_sentences_never_match_b6(self) -> None:
        import json
        import os

        m21 = os.path.join(os.path.dirname(__file__), "..", "..", "data", "M21.json")
        if not os.path.exists(m21):
            self.skipTest("M21.json not present")
        with open(m21) as f:
            cards = json.load(f)["data"]["cards"]

        from MTG_bot.core.compiler.ingest import split_sentences

        for c in cards:
            for s in split_sentences(c.get("text")):
                hits = [t.tid for t in TEMPLATES if t.pattern.fullmatch(s)]
                self.assertEqual(hits, [], f"M21 sentence matched B6: {s!r}")


if __name__ == "__main__":
    unittest.main()
