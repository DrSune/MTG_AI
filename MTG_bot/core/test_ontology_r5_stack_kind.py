"""Stack objects say what they are (docs/DESIGN_ATOM_ONTOLOGY.md §10):
``FAtom(STACK_KIND_EQ, string_value ∈ {SPELL, ACTIVATED, TRIGGERED})``, the
closed per-predicate ``string_value`` vocabulary, "counter target spell" =
SPELL, and a Choose-based counterspell cast at a spell waiting on the stack
(CR 601.2b: modes, then 601.2c: targets; 700.2a: a mode that can't choose
legal targets can't be chosen).
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
    SpellAbility,
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
from MTG_bot.core.executor.events import KIND_COUNTER
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



def was_countered(ex, frame) -> bool:
    """CR 701.6a: a countered spell left the stack, with a COUNTER row."""
    return any(e.kind == KIND_COUNTER and e.subject == frame.handle for e in ex.journal.events)


class ModalCounterCase(Rung1Case):
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

    def hold_the_shock(self):
        """P0's Shock at P1 waits on the stack (P0 keeps priority)."""
        with self.ex.holding_priority():
            return cast(self.ex, self.p0, self.shock_card, targets=(self.p1,))

    def legal_sets(self, card):
        from MTG_bot.core.executor.query import cast_mode_options
        from MTG_bot.core.executor.stack import spell_record

        node = next(a for a in spell_record(self.ex, card).abilities if isinstance(a, SpellAbility))
        return sorted(idxs for _token, idxs in cast_mode_options(self.ex, node, spell_handle=card, seat=self.p1))


class TestStackKindEvaluation(ModalCounterCase):
    def test_only_a_spell_on_the_stack_is_a_spell(self) -> None:
        ctx = ctx_for(self.ex, source=self.epiphany, controller=self.p1)
        self.assertFalse(eval_filter(SPELL_ON_STACK, self.shock_card, ctx))  # in hand
        self.hold_the_shock()
        self.assertTrue(eval_filter(SPELL_ON_STACK, self.shock_card, ctx))  # waiting
        self.ex.fire_triggers()  # both players pass: it resolves
        self.assertFalse(eval_filter(SPELL_ON_STACK, self.shock_card, ctx))  # graveyard

    def test_no_card_or_player_is_an_ability_on_the_stack(self) -> None:
        ctx = ctx_for(self.ex, source=self.epiphany, controller=self.p1)
        for handle in (self.shock_card, self.bear, self.p0):
            self.assertFalse(eval_filter(ABILITY_ON_STACK, handle, ctx), handle)


class TestModalCounter(ModalCounterCase):
    """Cast at a waiting spell, a modal counterspell announces its modes (601.2b) before its
    targets (601.2c), and only modes with legal targets can be chosen (700.2a)."""

    def test_mode_set_then_targets_then_resolution(self) -> None:
        frame = self.hold_the_shock()
        # CR 700.2a: no legal set holds mode 1 (no ability is on the stack).
        self.assertEqual(
            self.legal_sets(self.epiphany),
            sorted([(0,), (2,), (3,), (0, 2), (0, 3), (2, 3), (0, 2, 3)]),
        )
        self.script(lambda vocab, what: self.set_token((0, 2, 3)))
        book = self.give("Book", SpellKind.SORCERY, zone=ZONE_LIBRARY, seat=self.p0)
        # counter the Shock, bounce the Giant, P0 draws ("target player" is any player,
        # CR 115.1): the modes are asked, the targets declared slot by slot.
        cast(self.ex, self.p1, self.epiphany, targets=(self.shock_card, self.giant, self.p0))
        self.assertEqual([what.split(":", 1)[0] for _vocab, what in self.asks], ["choose"])
        self.assertTrue(was_countered(self.ex, frame))
        self.assertEqual(self.world.players[self.p1].life, 20)
        self.assertEqual(self.world.zone_of(self.shock_card).kind, ZONE_GRAVEYARD)
        self.assertEqual(self.world.zone_of(self.giant).kind, ZONE_HAND)
        self.assertEqual(self.world.zone_of(self.bear).kind, ZONE_BATTLEFIELD)
        self.assertEqual(self.world.zone_of(book).kind, ZONE_HAND)
        # the runtime Choose honoured the declaration: no resolution re-ask
        self.assertEqual(len(self.asks), 1)

    def test_a_mode_without_legal_targets_is_not_offered(self) -> None:
        # CR 700.2a: with no nonland permanent, the bounce mode can't be chosen.
        for h in (self.bear, self.giant):
            self.world.move_to_zone(h, self.p0, ZONE_GRAVEYARD)
        frame = self.hold_the_shock()
        self.assertEqual(self.legal_sets(self.epiphany), [(0,), (0, 3), (3,)])
        cast(self.ex, self.p1, self.epiphany, mode_choices=(0,), targets=(self.shock_card,))
        self.assertTrue(was_countered(self.ex, frame))

    def test_a_forced_mode_set_is_journalled_not_asked(self) -> None:
        # Counter / counter-ability / bounce with nothing to bounce: the one
        # legal set {counter} is forced, so it is journalled and never asked
        # (a one-option ask is a phantom, AGENTS.md §10); its one target too.
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
        frame = self.hold_the_shock()
        self.script()
        cast(self.ex, self.p1, card)
        self.assertTrue(was_countered(self.ex, frame))
        self.assertEqual(self.asks, [])
        forced = [(w, a) for w, a in self.ex.decisions.journal if w.startswith(f"choose:{card}:")]
        self.assertEqual(forced, [(forced[0][0], "0")])  # the set (0,) is index 0

    def test_a_counter_mode_with_no_legal_spell_cannot_be_chosen(self) -> None:
        # The counter mode narrowed to creature spells has no legal target in a
        # Shock (CR 700.2a): the card can still be cast for its other modes.
        creature_only = target_spell(FAtom(FAtomPred.TYPE_EQ, string_value="Creature"))
        effect = modal_counter_effect()
        narrowed = Choose(
            count=effect.count,
            options=(atom(Verb.COUNTER_SPELL, target=creature_only), *effect.options[1:]),
        )
        self.world.move_to_zone(self.epiphany, self.p1, ZONE_GRAVEYARD)
        card = self.give(
            "Narrow Epiphany",
            SpellKind.INSTANT,
            cost=Cost((CostManaColor("U", QConst(1)),)),
            effect=narrowed,
            seat=self.p1,
        )
        self.hold_the_shock()
        self.assertTrue(all(0 not in s for s in self.legal_sets(card)))
        self.assertIn((2,), self.legal_sets(card))

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
        with pytest.raises(ValueError, match="not a legal choice"):
            cast(self.ex, self.p1, card, mode_choices=(0, 2), targets=(self.bear, self.giant))
