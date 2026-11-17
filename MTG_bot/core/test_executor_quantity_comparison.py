"""Ontology round R12 (KNOWLEDGE/2026-11-17/210 I1 + I9 + I0): the one quantity comparison, and
TARGETS, QDistinct and the zone counts made general.

``FAtomPred.QTY_GE`` holds when a measured quantity, or the judged object's characteristic, is at
least ``count``; "N or less" is its negation at N + 1 (CR 107.1: integers). It replaced eleven
threshold predicates. Each test below fails on the code before the round and passes after:

1. Refusals: the old forms, a comparison of quantities that are not comparable, "or less" written
   any way but the negation, TARGETS without its filter, a second encoding of a zone count.
2. Readings: "an opponent has" over the opponents of a three-player game, the starting life total
   of a Commander game (CR 103.4, ledger F11), the power a creature had as it died (CR 603.10a),
   the different colours, names and mana values among permanents (CR 105.2, 201.2, 202.3), and
   the targets of a cast spell judged against a filter (CR 115.1, 601.2c).
"""

from __future__ import annotations

import unittest

import pytest

from MTG_bot.core import ability_tree as at
from MTG_bot.core.ability_tree import (
    CastSpellEvent,
    ControllerRef,
    CreatureDiesEvent,
    FAnd,
    FAtom,
    FAtomPred,
    FNot,
    PtDelta,
    PtDirection,
    QAtLeast,
    QAtMost,
    QBin,
    QBinOp,
    QConst,
    QDistinct,
    QProp,
    QPropField,
    QX,
    Zone,
    ZoneKind,
    at_least,
    at_most,
    number_in,
    number_you_control,
)
from MTG_bot.core.compiler.conditions import LIFE, condition, life_over_start
from MTG_bot.core.executor import Executor
from MTG_bot.core.executor.legality import ctx_for
from MTG_bot.core.executor.quantity import eval_filter, resolve
from MTG_bot.core.executor.stack import cast
from MTG_bot.core.state import ZONE_BATTLEFIELD, ZONE_GRAVEYARD, GameWorld
from MTG_bot.core.test_executor_binding import (
    CREATURE,
    UNIV,
    BindingCase,
    all_bf,
    atom,
    card_id,
    gain,
    referent_sel,
    reset_oracle_ids,
)
from MTG_bot.core.test_executor_stack import StackCase

GRAVEYARD_YOU = Zone(ZoneKind.GRAVEYARD, ControllerRef.YOU)
YOURS = FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU)


# ------------------------------------------------------------------------------- 1. refusals
OLD_PREDS = ("POWER_GE", "POWER_LE", "CMC_GE", "CMC_LE", "PT_GE", "PT_LE", "COLOR_COUNT_GE",
             "CONTROLLER_COUNT_GE", "CONTROLLER_COUNT_GT", "CONTROLLER_COUNT_LE", "ZONE_COUNT_GE",
             "LIFE_TOTAL_GE", "LIFE_LEAD_OVER_START_GE", "NAME_PARTITION_COUNT_GE", "TARGETS_SOURCE")


@pytest.mark.parametrize("name", OLD_PREDS)
def test_an_old_comparator_does_not_decode(name: str) -> None:
    old = at.to_dict(at_least(2, field=QPropField.POWER))
    old["pred"]["name"] = name
    del old["field"]
    with pytest.raises(ValueError, match=f"unknown member '{name}'"):
        at.from_dict("FAtom", old)


@pytest.mark.parametrize(("enum", "names"), [
    (QPropField, ("CMC", "CARDS_IN_HAND", "CARDS_IN_LIBRARY", "CARDS_IN_GRAVEYARD")),
    (at.Keyword, ("SCRY", "MILL", "BATTALION")),
    (at.Verb, ("EXILE", "MILL")),
    (at.ThisTurnKind, ("LIFE_GAINED", "CARDS_DRAWN")),
])
def test_the_duplicate_members_are_gone(enum, names) -> None:
    # I0: second encodings no tree used (MANA_VALUE, the zone counts, keyword actions and an
    # ability word, MOVE_ZONE's mill and exile, the turn-history atoms).
    assert not set(names) & set(enum.__members__)


def test_the_old_colour_count_does_not_decode() -> None:
    hand = number_in(Zone(ZoneKind.HAND, ControllerRef.YOU)).selector
    with pytest.raises(ValueError, match="unknown tag 'QDistinctColorCount'"):
        at.from_dict("QDistinctColorCount", {"tag": "QDistinctColorCount", "selector": at.to_dict(hand)})


@pytest.mark.parametrize("build", [
    lambda: at_least(2, field=QPropField.NAME),  # a name is no number
    lambda: at_least(2, field=QPropField.LIFE),  # a player's, never the judged object's
    lambda: QDistinct(number_you_control(CREATURE).selector, QPropField.POWER),
    lambda: QProp(referent="source", field=QPropField.COLOR),  # the comparison's or QDistinct's
    lambda: QProp(referent="source", field=QPropField.NAME),
    lambda: at_least(2, quantity=QConst(3)),  # a number is no measure of the game
    lambda: at_least(2, quantity=QX()),
    lambda: at_least(2, quantity=QProp(referent="source", field=QPropField.POWER)),  # field=POWER
    lambda: at_least(2, quantity=QBin(QBinOp.SUB, QConst(0), LIFE)),  # a negated life
])
def test_a_comparison_of_incomparable_quantities_is_refused(build) -> None:
    with pytest.raises(ValueError, match="FAtom: QTY_GE|QProp:|QDistinct"):
        build()


@pytest.mark.parametrize("build", [
    lambda: FAtom(pred=FAtomPred.QTY_GE, count=QAtMost(3), field=QPropField.POWER),
    lambda: FAtom(pred=FAtomPred.QTY_GE, count=QAtLeast(3), field=QPropField.POWER),
    lambda: FAtom(pred=FAtomPred.QTY_GE, count=QBin(QBinOp.ADD, QAtMost(2), QConst(1)),
                  field=QPropField.POWER),
    # the measured side a literal, the number on the right: "3 >= the count"
    lambda: FAtom(pred=FAtomPred.QTY_GE, count=number_you_control(CREATURE), quantity=QConst(3)),
])
def test_or_less_has_no_form_but_the_negation(build) -> None:
    with pytest.raises(ValueError):
        build()
    assert at_most(2, field=QPropField.POWER) == FNot(at_least(3, field=QPropField.POWER))


def test_one_compared_side_and_a_count() -> None:
    with pytest.raises(ValueError, match="exactly one of"):
        FAtom(pred=FAtomPred.QTY_GE, count=QConst(2))
    with pytest.raises(ValueError, match="exactly one of"):
        FAtom(pred=FAtomPred.QTY_GE, count=QConst(2), field=QPropField.POWER, quantity=LIFE)
    with pytest.raises(ValueError, match="count"):
        FAtom(pred=FAtomPred.QTY_GE, field=QPropField.POWER)


def test_targets_needs_its_filter() -> None:
    with pytest.raises(ValueError, match="inner_filter"):
        FAtom(pred=FAtomPred.TARGETS)


@pytest.mark.parametrize("build", [
    # "an opponent has eight cards in their graveyard" is your graveyard read for each opponent:
    # the opponent's zone is a second spelling of it, "who YOU" a second "you"
    lambda: at_least(8, quantity=number_in(Zone(ZoneKind.GRAVEYARD, ControllerRef.OPPONENT)),
                     who=ControllerRef.OPPONENT),
    lambda: at_least(8, quantity=number_in(GRAVEYARD_YOU), who=ControllerRef.YOU),
    lambda: at_least(2, field=QPropField.POWER, who=ControllerRef.OPPONENT),
    lambda: at_least(10, quantity=LIFE, who=ControllerRef.OPPONENT),
])
def test_a_zone_count_has_one_encoding(build) -> None:
    with pytest.raises(ValueError, match="who"):
        build()


THEIRS = number_in(Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),
                   FAnd((CREATURE, FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.OPPONENT))))
MINE = number_you_control(CREATURE)
START = QProp(referent="controller", field=QPropField.STARTING_LIFE)


@pytest.mark.parametrize(("build", "says"), [
    # the judged object's own property read through a referent: `field` is its one form
    (lambda: at_least(4, quantity=QProp(referent=referent_sel("source"), field=QPropField.POWER,
                                        agg=at.QAgg.SUM)), "no referent"),
    (lambda: at_least(2, quantity=QDistinct(referent_sel("source"), QPropField.COLOR)), "no referent"),
    # with `who` the threshold is read for the opponent too: only a number may stand there
    (lambda: at_least(QBin(QBinOp.ADD, number_in(Zone(ZoneKind.HAND, ControllerRef.YOU)), QConst(1)),
                      quantity=number_in(Zone(ZoneKind.HAND, ControllerRef.YOU)),
                      who=ControllerRef.OPPONENT), "a literal or X"),
    # a threshold of 0 always holds
    (lambda: at_least(0, field=QPropField.COLOR), "count 0"),
    (lambda: at_most(-1, quantity=MINE), "count 0"),
    # a target player anywhere in a side designates nothing
    (lambda: at_least(at.QThisTurn(kind=at.ThisTurnKind.NONCOMBAT_DAMAGE,
                                   referent=ControllerRef.TARGET_PLAYER), field=QPropField.POWER),
     "target player"),
    # two measures compared have one orientation: "fewer than theirs" is "theirs at least mine + 1"
    (lambda: FNot(at_least(THEIRS, quantity=MINE)), "never negated"),
    # a sum's literal is its last operand
    (lambda: at_least(QBin(QBinOp.ADD, QConst(1), MINE), quantity=THEIRS), "canonical order"),
    (lambda: at_least(QBin(QBinOp.ADD, QConst(7), START), quantity=LIFE), "canonical order"),
    # gate round 12: a population's greatest or least value is a second form of a count ("you
    # control a creature with power 4 or greater"); only its total (SUM) is a measure
    (lambda: at_least(4, quantity=QProp(referent=MINE.selector, field=QPropField.POWER, agg=at.QAgg.MAX)),
     "no measure"),
    (lambda: at_least(1, quantity=QProp(referent=MINE.selector, field=QPropField.POWER, agg=at.QAgg.MIN)),
     "no measure"),
    # gate round 12: control is an overlay, the battlefield one zone: Zone(BATTLEFIELD, YOU) as a
    # counted population would be a second (and wrong) "you control", on either side and under who
    (lambda: at_least(2, quantity=number_in(Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU), CREATURE)),
     "BATTLEFIELD, ANY"),
    (lambda: at_least(2, quantity=number_in(Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU), CREATURE),
                      who=ControllerRef.OPPONENT), "BATTLEFIELD, ANY"),
    (lambda: at_least(QBin(QBinOp.ADD, number_in(Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU), CREATURE),
                           QConst(1)), quantity=THEIRS), "BATTLEFIELD, ANY"),
    # the negation of two measures compared, through an FAnd or FOr (De Morgan)
    (lambda: FNot(FAnd((at_least(THEIRS, quantity=MINE), FAtom(pred=FAtomPred.IS_TOKEN)))), "never negated"),
    (lambda: FNot(at.FOr((at_least(THEIRS, quantity=MINE), FAtom(pred=FAtomPred.IS_TOKEN)))), "never negated"),
    # N + 0, a double negation, an ALL selector's count
    (lambda: at_least(QBin(QBinOp.ADD, MINE, QConst(0)), quantity=THEIRS), r"N \+ 0"),
    (lambda: FNot(FNot(FAtom(pred=FAtomPred.IS_TOKEN))), "double negation"),
    (lambda: at_least(2, quantity=at.QCount(at.Selector(QConst(3), at.SelectorMode.ALL, CREATURE,
                                                        zones=(Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),)))),
     "QUnbounded"),
])
def test_one_form_per_comparison(build, says) -> None:
    with pytest.raises(ValueError, match=says):
        build()
    # the forms they stand for
    at_least(QBin(QBinOp.ADD, MINE, QConst(1)), quantity=THEIRS)
    at_least(QBin(QBinOp.ADD, START, QConst(7)), quantity=LIFE)
    FNot(at_least(START, quantity=LIFE))  # "less than your starting life": the start is no measure


# ------------------------------------------------------------------------------- 2. readings
class AnOpponentHasTest(unittest.TestCase):
    """"An opponent has N or more cards in their graveyard" over three players: true when one of
    the opponents has them (Thieves' Guild Enforcer), never counting yours."""

    def setUp(self) -> None:
        reset_oracle_ids()
        self.world = GameWorld(num_players=3, start_life=20, master_seed=5)
        self.p0, self.p1, self.p2 = self.world.player_order
        self.anchor = self.world.add_card(card_id("Anchor", "1", "1"), self.p0, ZONE_BATTLEFIELD)
        self.ex = Executor(self.world)
        self.gate = at_least(2, quantity=number_in(GRAVEYARD_YOU), who=ControllerRef.OPPONENT)

    def holds(self, filter_) -> bool:
        return eval_filter(filter_, self.anchor, ctx_for(self.ex, source=self.anchor, controller=self.p0))

    def bury(self, seat, n) -> None:
        for i in range(n):
            self.world.add_card(card_id(f"Dead {seat} {i}"), seat, ZONE_GRAVEYARD)

    def test_yours_never_count(self) -> None:
        self.bury(self.p0, 5)
        self.assertFalse(self.holds(self.gate))
        self.assertTrue(self.holds(FNot(self.gate)))  # "no opponent has"

    def test_one_opponent_is_enough(self) -> None:
        self.bury(self.p1, 1)
        self.assertFalse(self.holds(self.gate))  # one card each is not two in one graveyard
        self.bury(self.p2, 1)
        self.assertFalse(self.holds(self.gate))
        self.bury(self.p2, 1)
        self.assertTrue(self.holds(self.gate))


class StartingLifeTest(unittest.TestCase):
    """CR 103.4: the starting life total is the game's (40 in Commander), not 20."""

    def test_the_lead_is_over_the_games_start(self) -> None:
        reset_oracle_ids()
        world = GameWorld(num_players=2, start_life=40, master_seed=5)
        p0 = world.player_order[0]
        anchor = world.add_card(card_id("Anchor", "1", "1"), p0, ZONE_BATTLEFIELD)
        ex = Executor(world)
        ctx = ctx_for(ex, source=anchor, controller=p0)
        lead = life_over_start(7)  # "at least 7 life more than your starting life total"
        world.players[p0].life = 46
        self.assertFalse(eval_filter(lead, anchor, ctx))
        world.players[p0].life = 47
        self.assertTrue(eval_filter(lead, anchor, ctx))
        below = condition("your life total is less than your starting life total")
        self.assertFalse(eval_filter(below, anchor, ctx))
        world.players[p0].life = 39
        self.assertTrue(eval_filter(below, anchor, ctx))


class DepartedPowerTest(BindingCase):
    """"Whenever a creature with power 4 or greater dies": its power as it last existed on the
    battlefield (CR 603.10a), a pump included, not the card's printed power in the graveyard."""

    def setUp(self) -> None:
        super().setUp()
        big = FAnd((CREATURE, at_least(4, field=QPropField.POWER)))
        self.attach_trigger(self.watch, CreatureDiesEvent(filter=big), gain(1))
        self.victim = self.world.add_card(card_id("Victim", "2", "2"), self.p0, ZONE_BATTLEFIELD)

    def kill(self) -> None:
        self.ex.execute(atom(at.Verb.DESTROY, target=all_bf()), source=self.watch,
                        controller=self.p0, bindings={"target": self.victim})

    def test_a_pumped_creature_dies_big(self) -> None:
        self.ex.execute(
            atom(at.Verb.MODIFY_PT, target=referent_sel("target"),
                 power=PtDelta(PtDirection.INCREASE, QConst(2))),
            source=self.watch, controller=self.p0, bindings={"target": self.victim},
        )
        self.kill()
        self.assertEqual(self.world.zone_of(self.victim).kind, ZONE_GRAVEYARD)
        self.assertEqual(self.life(self.p0), 21)

    def test_an_unpumped_one_does_not(self) -> None:
        self.kill()
        self.assertEqual(self.life(self.p0), 20)


class UndefinedPowerTest(BindingCase):
    """A printed '*' with no number off the battlefield (CR 208.2a) is flagged, never compared:
    "power 2 or less" would hold for it through the negation. An object with no power at all (a
    noncreature) simply fails the comparison."""

    def test_a_star_power_off_the_battlefield_raises(self) -> None:
        star = self.world.add_card(card_id("Starry", "*", "4"), self.p0, ZONE_GRAVEYARD)
        ctx = ctx_for(self.ex, source=self.watch, controller=self.p0)
        with self.assertRaisesRegex(NotImplementedError, "has no value here"):
            eval_filter(at_most(2, field=QPropField.POWER), star, ctx)
        rock = self.world.add_card(card_id("Rock", type_line="Artifact"), self.p0, ZONE_BATTLEFIELD)
        self.assertFalse(eval_filter(at_least(1, field=QPropField.POWER), rock, ctx))


def test_a_measured_comparison_reads_no_subject() -> None:
    # the measured form qualifies an event or an ability without judging an object (MAPPER_GUIDE,
    # one slot per event); the field form judges the object it is asked about
    assert at.reads_no_subject(at_least(2, quantity=MINE))
    assert not at.reads_no_subject(at_least(2, field=QPropField.POWER))


class ColourCountTest(BindingCase):
    """The comparison of COLOR reads the number of the object's colours (CR 105.2), not whether it
    has one: "multicolored" is two or more."""

    def test_two_colours_are_two(self) -> None:
        ctx = ctx_for(self.ex, source=self.watch, controller=self.p0)
        both = self.world.add_card(card_id("Both", "1", "1", colors=("W", "U")), self.p0, ZONE_BATTLEFIELD)
        one = self.world.add_card(card_id("One", "1", "1", colors=("W",)), self.p0, ZONE_BATTLEFIELD)
        self.assertTrue(eval_filter(at_least(2, field=QPropField.COLOR), both, ctx))
        self.assertFalse(eval_filter(at_least(2, field=QPropField.COLOR), one, ctx))
        self.assertFalse(eval_filter(at_least(3, field=QPropField.COLOR), both, ctx))


class DistinctTest(BindingCase):
    """QDistinct: the number of different colours (a two-coloured permanent gives two), names and
    mana values (a land's is 0) among the permanents you control; and two of them sharing a name
    (Chrome Replicator) as more permanents than names."""

    def test_colours_names_and_mana_values(self) -> None:
        for name, colors, cmc in (("Twin", ("W",), 2), ("Twin", ("W", "U"), 2), ("Other", (), 3)):
            self.world.add_card(card_id(name, "1", "1", cmc=cmc, colors=colors), self.p0, ZONE_BATTLEFIELD)
        self.world.add_card(card_id("Theirs", "1", "1", cmc=5, colors=("R",)), self.p1, ZONE_BATTLEFIELD)
        self.world.add_card(card_id("Land", type_line="Land", cmc=0), self.p0, ZONE_BATTLEFIELD)
        mine = number_you_control(UNIV)
        ctx = ctx_for(self.ex, source=self.watch, controller=self.p0)
        self.assertEqual(resolve(QDistinct(mine.selector, QPropField.COLOR), ctx), 2)
        # Watchdog, Twin, Other, Land
        self.assertEqual(resolve(QDistinct(mine.selector, QPropField.NAME), ctx), 4)
        self.assertEqual(resolve(QDistinct(mine.selector, QPropField.MANA_VALUE), ctx), 3)  # 2, 3, 0
        names = QDistinct(mine.selector, QPropField.NAME)
        two_share = at_least(QBin(QBinOp.ADD, names, QConst(1)), quantity=mine)
        self.assertTrue(eval_filter(two_share, self.watch, ctx))
        self.assertFalse(eval_filter(two_share, self.watch, ctx_for(self.ex, source=self.watch,
                                                                     controller=self.p1)))


class CastTargetsTest(StackCase):
    """"Whenever you cast a spell that targets a creature you control" (Season of Growth): the
    cast spell's targets judged against the filter, one trigger per spell."""

    def setUp(self) -> None:
        super().setUp()
        event = CastSpellEvent(
            filter=FAtom(pred=FAtomPred.TARGETS, inner_filter=FAnd((CREATURE, YOURS))),
            actor=YOURS,
        )
        self.watcher = self.world.add_card(card_id("Watcher", "1", "1"), self.p0, ZONE_BATTLEFIELD)
        self.ex.attach_card(self.watcher, at.CardRecord(
            oracle_id=self.world.cards[self.watcher].identity.oracle_id, name="Watcher",
            type_line="Creature", types=("Creature",), subtypes=(), supertypes=(), colors=(),
            color_identity=frozenset(), mana_cost=None, mana_value=2, power=QConst(1),
            toughness=QConst(1), loyalty=None, keywords=(),
            abilities=(at.TriggeredAbility(event, None, gain(1)),), is_token=False))
        self.mine = self.world.add_card(card_id("Mine", "5", "5"), self.p0, ZONE_BATTLEFIELD)
        self.theirs = self.world.add_card(card_id("Theirs", "5", "5"), self.p1, ZONE_BATTLEFIELD)

    def shoot(self, target) -> int:
        life = self.world.players[self.p0].life
        self.mana(self.p0, R=1)
        cast(self.ex, self.p0, self.shock(), targets=(target,))
        return self.world.players[self.p0].life - life

    def test_a_spell_at_your_creature_triggers(self) -> None:
        self.assertEqual(self.shoot(self.mine), 1)

    def test_a_spell_at_theirs_or_at_a_player_does_not(self) -> None:
        self.assertEqual(self.shoot(self.theirs), 0)
        self.assertEqual(self.shoot(self.p1), 0)

    def test_one_of_its_targets_is_enough(self) -> None:
        # "a spell that targets a creature you control": one of the spell's targets (CR 115.1)
        twin = self.give("Twin Shock", at.SpellKind.INSTANT,
                         cost=at.Cost((at.CostManaColor("R", QConst(1)),)),
                         effect=atom(at.Verb.DEAL_DAMAGE, amount=QConst(1), target=at.Selector(
                             QConst(2), at.SelectorMode.TARGET, CREATURE,
                             zones=(Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),))))
        life = self.world.players[self.p0].life
        self.mana(self.p0, R=1)
        cast(self.ex, self.p0, twin, targets=(self.mine, self.theirs))
        self.assertEqual(self.world.players[self.p0].life - life, 1)


if __name__ == "__main__":
    unittest.main()
