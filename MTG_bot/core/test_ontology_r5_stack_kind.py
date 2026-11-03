"""Ontology R5-10 (docs/DESIGN_ATOM_ONTOLOGY.md §10, gate round 3 GO):
``FAtom(STACK_KIND_EQ, string_value ∈ {SPELL, ACTIVATED, TRIGGERED})``, the
closed per-predicate ``string_value`` vocabulary, "counter target spell" =
SPELL, and the counter window's visible mode ask for a Choose-based
counterspell (CR 601.2b: modes, then 601.2c: targets; 700.2a: a mode that
can't choose legal targets can't be chosen).
"""

from __future__ import annotations

import pytest

from MTG_bot.core.ability_tree import (
    Choose,
    ControllerRef,
    Cost,
    CostManaColor,
    FAnd,
    FAtom,
    FAtomPred,
    FNot,
    FOr,
    QAtLeast,
    QConst,
    Selector,
    SelectorMode,
    SpellKind,
    Verb,
    Zone,
    ZoneKind,
    from_dict,
    to_dict,
)
from MTG_bot.core.compiler.coverage import build_full_registry
from MTG_bot.core.compiler.templates import EffectOutcome
from MTG_bot.core.compiler.templates_b5a import (
    SPELL_ON_STACK,
    target_spell,
    target_stack_ability,
)
from MTG_bot.core.executor.legality import ctx_for
from MTG_bot.core.executor.quantity import eval_filter
from MTG_bot.core.executor.stack import cast
from MTG_bot.core.state import ZONE_BATTLEFIELD, ZONE_GRAVEYARD, ZONE_HAND, ZONE_LIBRARY
from MTG_bot.core.test_executor_rung1 import Rung1Case
from MTG_bot.core.test_executor_stack import atom

ABILITY_ON_STACK = FOr(
    children=(
        FAtom(FAtomPred.STACK_KIND_EQ, string_value="ACTIVATED"),
        FAtom(FAtomPred.STACK_KIND_EQ, string_value="TRIGGERED"),
    )
)
BF_ANY = Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY)


# ------------------------------------------------------------------- IR


def test_stack_kind_vocabulary_is_closed() -> None:
    for word in ("SPELL", "ACTIVATED", "TRIGGERED"):
        node = FAtom(FAtomPred.STACK_KIND_EQ, string_value=word)
        assert from_dict("FAtom", to_dict(node)) == node
    with pytest.raises(ValueError, match="must be one of"):
        FAtom(FAtomPred.STACK_KIND_EQ, string_value="spell")
    with pytest.raises(ValueError, match="requires slot 'string_value'"):
        FAtom(FAtomPred.STACK_KIND_EQ)
    # the open-data predicates keep free strings (type, subtype, name data)
    assert FAtom(FAtomPred.SUBTYPE_EQ, string_value="Kraken").string_value == "Kraken"


def test_target_spell_shapes() -> None:
    assert target_spell().filter == SPELL_ON_STACK  # bare, never a 1-child FAnd
    noncreature = FNot(FAtom(FAtomPred.TYPE_EQ, string_value="Creature"))
    assert target_spell(noncreature).filter == FAnd((SPELL_ON_STACK, noncreature))
    assert target_stack_ability("ACTIVATED", "TRIGGERED").filter == ABILITY_ON_STACK
    assert target_spell().zones == (Zone(ZoneKind.STACK, ControllerRef.ANY),)


@pytest.mark.parametrize(
    "sentence,expected",
    [
        ("Counter target spell.", SPELL_ON_STACK),
        (
            "Counter target noncreature spell.",
            FAnd((SPELL_ON_STACK, FNot(FAtom(FAtomPred.TYPE_EQ, string_value="Creature")))),
        ),
        ("• Counter target spell.", SPELL_ON_STACK),
        ("• Counter target activated or triggered ability.", ABILITY_ON_STACK),
    ],
)
def test_compiled_counter_targets(sentence: str, expected) -> None:
    matches = build_full_registry().match(sentence)
    assert len(matches) == 1, sentence
    outcome = matches[0].outcome
    assert isinstance(outcome, EffectOutcome)
    assert outcome.effect.verb is Verb.COUNTER_SPELL
    assert outcome.effect.args.get("target").filter == expected


# ------------------------------------------------------------- engine


def modal_counter_effect() -> Choose:
    """Sublime Epiphany's shape with handled verbs only (no COPY): counter
    target spell / counter target ability / bounce / target player draws."""
    bounce = atom(
        Verb.MOVE_ZONE,
        cards=Selector(
            QConst(1),
            SelectorMode.TARGET,
            FNot(FAtom(FAtomPred.TYPE_EQ, string_value="Land")),
            zones=(BF_ANY,),
        ),
        destination=Zone(ZoneKind.HAND, ControllerRef.OWNER),
    )
    draw = atom(Verb.DRAW, controller=ControllerRef.TARGET_PLAYER, amount=QConst(1))
    return Choose(
        count=QAtLeast(1),
        options=(
            atom(Verb.COUNTER_SPELL, target=target_spell()),
            atom(Verb.COUNTER_SPELL, target=target_stack_ability("ACTIVATED", "TRIGGERED")),
            bounce,
            draw,
        ),
    )


class ModalWindowCase(Rung1Case):
    def setUp(self) -> None:
        super().setUp()
        self.shock_card = self.shock()
        self.mana(self.p0, R=1)
        self.bear = self.give(
            "Bear", SpellKind.CREATURE, zone=ZONE_BATTLEFIELD, seat=self.p0,
            type_line="Creature — Bear", types=("Creature",), power="2", toughness="2",
        )
        self.giant = self.give(
            "Giant", SpellKind.CREATURE, zone=ZONE_BATTLEFIELD, seat=self.p0,
            type_line="Creature — Giant", types=("Creature",), power="4", toughness="4",
        )
        self.epiphany = self.give(
            "Epiphany Test",
            SpellKind.INSTANT,
            cost=Cost((CostManaColor("U", QConst(1)),)),
            effect=modal_counter_effect(),
            seat=self.p1,
        )
        self.mana(self.p1, U=1)

    def option_sets(self):
        from MTG_bot.core.executor.query import choose_options

        return [
            o.option_idxs
            for o in choose_options(
                self.ex, modal_counter_effect(), source=self.epiphany, controller=self.p1
            )
        ]

    def set_token(self, modes: tuple[int, ...]) -> str:
        return str(self.option_sets().index(modes))


class TestStackKindEvaluation(ModalWindowCase):
    def test_only_a_spell_on_the_stack_is_a_spell(self) -> None:
        ctx = ctx_for(self.ex, source=self.epiphany, controller=self.p1)
        self.assertFalse(eval_filter(SPELL_ON_STACK, self.shock_card, ctx))  # in hand
        self.script("PASS")
        frame = cast(self.ex, self.p0, self.shock_card, targets=(self.p1,))
        self.assertFalse(frame.countered)
        # while the Shock was on the stack the window asked p1 (the vocab
        # offered the modal counter): the spell was a legal SPELL target
        (vocab, what), = self.asks
        self.assertEqual(vocab, ("PASS", str(self.epiphany)))
        self.assertTrue(what.startswith(f"counter:{self.p1}:"))

    def test_abilities_are_never_on_the_stack(self) -> None:
        ctx = ctx_for(self.ex, source=self.epiphany, controller=self.p1)
        for handle in (self.shock_card, self.bear, self.p0):
            self.assertFalse(eval_filter(ABILITY_ON_STACK, handle, ctx), handle)


class TestModalCounterWindow(ModalWindowCase):
    """The window's mode ask (601.2b) precedes the target asks (601.2c)."""

    def test_mode_set_then_targets_then_resolution(self) -> None:
        chosen = (0, 2, 3)  # counter the Shock, bounce, target player draws
        seen: dict[str, tuple[str, ...]] = {}

        def mode_answer(vocab, what):
            seen["modes"] = tuple(vocab)
            return self.set_token(chosen)

        # re-pinned 2026-10-30: V21 (merged from engine/verify-fixes-2) makes "target
        # player" any player, the caster included (CR 115.1), so mode 3's player is
        # now a real target ask (it was the lone opponent, forced). It names p0, the
        # pin's drawer.
        self.script(str(self.epiphany), mode_answer, str(self.giant), str(self.p0))
        book = self.give("Book", SpellKind.SORCERY, zone=ZONE_LIBRARY, seat=self.p0)
        frame = cast(self.ex, self.p0, self.shock_card, targets=(self.p1,))
        kinds = [what.split(":", 1)[0] for _vocab, what in self.asks]
        self.assertEqual(kinds, ["counter", "choose", "target", "target"])
        self.assertEqual(self.asks[3][0], tuple(sorted((str(self.p0), str(self.p1)))))
        # CR 700.2a: no offered set holds mode 1 (no ability is on the stack),
        # and every offered set counters the frame (mode 0) — no phantom.
        offered = [self.option_sets()[int(t)] for t in seen["modes"]]
        self.assertTrue(offered)
        self.assertTrue(all(0 in s and 1 not in s for s in offered), offered)
        self.assertEqual(
            sorted(offered), sorted([(0,), (0, 2), (0, 3), (0, 2, 3)])
        )
        # the bounce ask offered both nonland permanents
        self.assertEqual(self.asks[2][0], tuple(sorted((str(self.bear), str(self.giant)))))
        # resolution: the Shock is countered, the Giant bounced, p0 drew
        # (designated above; before V21 the engine's "target player" was an
        # opponent seat only, B-53)
        self.assertTrue(frame.countered)
        self.assertEqual(self.world.players[self.p1].life, 20)
        self.assertEqual(self.world.zone_of(self.shock_card).kind, ZONE_GRAVEYARD)
        self.assertEqual(self.world.zone_of(self.giant).kind, ZONE_HAND)
        self.assertEqual(self.world.zone_of(self.bear).kind, ZONE_BATTLEFIELD)
        self.assertEqual(self.world.zone_of(book).kind, ZONE_HAND)
        # the runtime Choose honoured the declaration: no resolution re-ask
        self.assertEqual(len(self.asks), 4)

    def test_a_mode_without_legal_targets_is_not_offered(self) -> None:
        # CR 700.2a: with no nonland permanent, the bounce mode can't be chosen.
        for h in (self.bear, self.giant):
            self.world.move_to_zone(h, self.p0, ZONE_GRAVEYARD)
        self.script(str(self.epiphany), lambda vocab, what: self.set_token((0,)))
        frame = cast(self.ex, self.p0, self.shock_card, targets=(self.p1,))
        self.assertTrue(frame.countered)
        kinds = [what.split(":", 1)[0] for _vocab, what in self.asks]
        self.assertEqual(kinds, ["counter", "choose"])
        offered = [self.option_sets()[int(t)] for t in self.asks[1][0]]
        self.assertEqual(sorted(offered), [(0,), (0, 3)])

    def test_a_forced_mode_set_is_journalled_not_asked(self) -> None:
        # Counter / counter-ability / bounce with nothing to bounce: the one
        # legal set {counter} is forced, so it is journalled and never asked
        # (a one-option ask is a phantom, AGENTS §10).
        three = Choose(count=QAtLeast(1), options=modal_counter_effect().options[:3])
        for h, owner in ((self.bear, self.p0), (self.giant, self.p0), (self.epiphany, self.p1)):
            self.world.move_to_zone(h, owner, ZONE_GRAVEYARD)
        card = self.give(
            "Three Epiphany",
            SpellKind.INSTANT,
            cost=Cost((CostManaColor("U", QConst(1)),)),
            effect=three,
            seat=self.p1,
        )
        self.script(str(card))
        frame = cast(self.ex, self.p0, self.shock_card, targets=(self.p1,))
        self.assertTrue(frame.countered)
        self.assertEqual([what.split(":", 1)[0] for _v, what in self.asks], ["counter"])
        forced = [(w, a) for w, a in self.ex.decisions.journal if w.startswith(f"choose:{card}:")]
        self.assertEqual(forced, [(forced[0][0], "0")])  # the set (0,) is index 0

    def test_no_counterable_frame_means_no_offer(self) -> None:
        # A mode set must counter THIS frame: with the counter mode narrowed
        # to creature spells, a Shock gets no window at all (C15: a seat
        # with nothing to offer is never asked).
        creature_only = target_spell(FAtom(FAtomPred.TYPE_EQ, string_value="Creature"))
        effect = modal_counter_effect()
        narrowed = Choose(
            count=effect.count,
            options=(atom(Verb.COUNTER_SPELL, target=creature_only), *effect.options[1:]),
        )
        self.world.move_to_zone(self.epiphany, self.p1, ZONE_GRAVEYARD)
        self.give(
            "Narrow Epiphany",
            SpellKind.INSTANT,
            cost=Cost((CostManaColor("U", QConst(1)),)),
            effect=narrowed,
            seat=self.p1,
        )
        self.script()
        frame = cast(self.ex, self.p0, self.shock_card, targets=(self.p1,))
        self.assertFalse(frame.countered)
        self.assertEqual(self.asks, [])
        self.assertEqual(self.world.players[self.p1].life, 18)

    def test_cast_lane_refuses_an_illegal_mode_set(self) -> None:
        # a "choose one" spell declared with two modes (CR 700.2: the count)
        one = Choose(count=QConst(1), options=modal_counter_effect().options)
        self.world.move_to_zone(self.epiphany, self.p1, ZONE_GRAVEYARD)
        card = self.give(
            "One Epiphany",
            SpellKind.INSTANT,
            cost=Cost((CostManaColor("U", QConst(1)),)),
            effect=one,
            seat=self.p1,
        )
        self.script("PASS")
        with pytest.raises(ValueError, match="not a legal choice"):
            cast(self.ex, self.p1, card, mode_choices=(0, 2), targets=(self.bear, self.giant))
