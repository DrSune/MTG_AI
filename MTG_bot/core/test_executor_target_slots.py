"""CR 601.2c: a spell or ability with several instances of the word "target" announces the
targets of each one, in turn, each from its own legal set.

An "up to" instance may be given no target (601.2c: the player announces how many), one object
cannot be chosen twice for one instance but may be for two different ones (CR 115.3), unless
the text says "another". As the spell or ability resolves each target is checked again against
its own instance, and an illegal one is not affected (CR 608.2b).

``stack.designate_slots`` reads a designation per slot (one tuple of handles per slot, or one
handle per slot), for the cast and the activation lanes alike. The drivers ask one target
question per slot from ``stack.slot_options``
(MTG_bot/bench/test_router.py has the dealt-game side).
"""

from __future__ import annotations

from MTG_bot.core.ability_tree import (
    ActivatedAbility,
    CastSpellEvent,
    ControllerRef,
    Cost,
    DurationEot,
    FAnd,
    FAtom,
    FAtomPred,
    PtDelta,
    PtDirection,
    QAtMost,
    QConst,
    Selector,
    SelectorMode,
    Seq,
    SpellKind,
    TriggeredAbility,
    Verb,
    Zone,
    ZoneKind,
)
from MTG_bot.core.executor.legality import activate
from MTG_bot.core.executor.query import activation_target_slots
from MTG_bot.core.executor.stack import cast
from MTG_bot.core.state import ZONE_BATTLEFIELD, ZONE_GRAVEYARD
from MTG_bot.core.test_executor_binding import card_id, record_of
from MTG_bot.core.test_executor_stack import StackCase
from MTG_bot.core.test_executor_verbs import atom

CREATURE = FAtom(FAtomPred.TYPE_EQ, string_value="Creature")
ANOTHER = FAtom(FAtomPred.IS_ANY_TARGET)  # the compiled "another target" mark


def target(count, who=ControllerRef.ANY, *extra) -> Selector:
    """ "target creature" on the battlefield; ``who``: YOU = "you control", OPPONENT = "you
    don't control"; ``extra``: more conjuncts of its filter."""
    filter_ = FAnd((CREATURE, *extra)) if extra else CREATURE
    return Selector(count, SelectorMode.TARGET, filter_, zones=(Zone(ZoneKind.BATTLEFIELD, who),))


def damage(selector: Selector, n: int):
    return atom(Verb.DEAL_DAMAGE, target=selector, amount=QConst(n))


def pump(selector: Selector, n: int):
    return atom(
        Verb.MODIFY_PT,
        target=selector,
        power=PtDelta(PtDirection.INCREASE, QConst(n)),
        duration=DurationEot(),
    )


UP_TO_ONE_THEIRS = target(QAtMost(1), ControllerRef.OPPONENT)
ONE_MINE = target(QConst(1), ControllerRef.YOU)


class TargetSlotsCase(StackCase):
    def setUp(self):
        super().setUp()
        self.mine = self.world.add_card(card_id("Mine", "2", "2"), self.p0, ZONE_BATTLEFIELD)
        self.theirs = self.world.add_card(card_id("Theirs", "2", "4"), self.p1, ZONE_BATTLEFIELD)
        self.theirs2 = self.world.add_card(card_id("Theirs Two", "1", "4"), self.p1, ZONE_BATTLEFIELD)

    def spell(self, name, *steps):
        return self.give(name, SpellKind.INSTANT, effect=Seq(steps))

    def power(self, handle) -> int:
        card = self.world.cards[handle]
        return int(self.ex.ledger.effective_pt(card.identity, handle, card.counters)[0])

    def swipe(self, name="Swipe"):
        """ "Up to one target creature you don't control is dealt 3 damage. Target creature you
        control gets +1/+0." The optional instance comes FIRST, so one handle per slot cannot
        leave it empty."""
        return self.spell(name, damage(UP_TO_ONE_THEIRS, 3), pump(ONE_MINE, 1))

    def destroy_on_cast(self, name: str) -> None:
        """A permanent of p0's whose cast trigger destroys the creature ``name``: the trigger
        resolves above the spell (CR 601.2i, 603.3), so that target is gone when the spell
        resolves."""
        named = Selector(
            QConst(1),
            SelectorMode.CHOOSE,
            FAtom(FAtomPred.NAME_EQ, string_value=name),
            zones=(Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),),
        )
        trig = TriggeredAbility(
            event=CastSpellEvent(
                FAtom(FAtomPred.TYPE_EQ, string_value="Instant"),
                actor=FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
            ),
            condition=None,
            effect=atom(Verb.DESTROY, target=named),
        )
        watcher = self.world.add_card(card_id("Watcher", "0", "1"), self.p0, ZONE_BATTLEFIELD)
        self.ex.attach_card(watcher, record_of([trig], oid=self.world.cards[watcher].identity.oracle_id))


class TestPerSlotDesignation(TargetSlotsCase):
    def test_an_up_to_slot_before_a_required_one_may_stay_empty(self):
        cast(self.ex, self.p0, self.swipe(), targets=((), (self.mine,)))
        self.assertEqual(self.ex.damage, {})
        self.assertEqual(self.power(self.mine), 3)
        cast(self.ex, self.p0, self.swipe("Swipe Two"), targets=((self.theirs,), (self.mine,)))
        self.assertEqual(self.ex.damage, {self.theirs: 3})
        self.assertEqual(self.power(self.mine), 4)

    def test_a_slot_of_two_targets_beside_a_slot_of_one(self):
        # "Two target creatures you don't control are each dealt 1 damage. Target creature you
        # control gets +2/+0."
        spell = self.spell(
            "Volley", damage(target(QConst(2), ControllerRef.OPPONENT), 1), pump(ONE_MINE, 2)
        )
        frame = cast(self.ex, self.p0, spell, targets=((self.theirs, self.theirs2), (self.mine,)))
        self.assertEqual(frame.declared_targets, tuple(sorted((self.mine, self.theirs, self.theirs2))))
        self.assertEqual(self.ex.damage, {self.theirs: 1, self.theirs2: 1})
        self.assertEqual(self.power(self.mine), 4)

    def test_an_illegal_designation_is_refused_and_a_legal_one_resolves(self):
        refused = {
            "a required slot left empty": ((self.theirs,), ()),
            "a target in the other slot's place": ((self.mine,), (self.theirs,)),
            "one object twice for one 'target'": ((self.theirs, self.theirs), (self.mine,)),
            "one slot short": ((self.theirs, self.theirs2),),
            "both spellings at once": (self.theirs2, (self.mine,)),
        }
        for why, targets in refused.items():
            spell = self.spell(
                f"Volley {why}", damage(target(QConst(2), ControllerRef.OPPONENT), 1), pump(ONE_MINE, 2)
            )
            with self.subTest(why), self.assertRaises(ValueError):
                cast(self.ex, self.p0, spell, targets=targets)
        self.assertEqual(self.ex.damage, {})
        spell = self.spell("Volley", damage(target(QConst(2), ControllerRef.OPPONENT), 1), pump(ONE_MINE, 2))
        cast(self.ex, self.p0, spell, targets=((self.theirs, self.theirs2), (self.mine,)))
        self.assertEqual(self.ex.damage, {self.theirs: 1, self.theirs2: 1})

    def test_one_object_may_fill_two_targets_unless_one_says_another(self):
        # CR 115.3: "Target creature gets +1/+0. Target creature you don't control is dealt 1
        # damage." (Two instances with the same words share one slot, keyed by the selector.)
        theirs_one = target(QConst(1), ControllerRef.OPPONENT)
        cast(
            self.ex, self.p0, self.spell("Two Words", pump(target(QConst(1)), 1), damage(theirs_one, 1)),
            targets=((self.theirs,), (self.theirs,)),
        )
        self.assertEqual((self.power(self.theirs), self.ex.damage), (3, {self.theirs: 1}))
        # "... Another target creature you don't control is dealt 1 damage." (Rookie Mistake)
        spell = self.spell(
            "Another", pump(target(QConst(1)), 1),
            damage(target(QConst(1), ControllerRef.OPPONENT, ANOTHER), 1),
        )
        with self.assertRaises(ValueError) as cm:
            cast(self.ex, self.p0, spell, targets=((self.theirs,), (self.theirs,)))
        self.assertIn("another_target", str(cm.exception))

    def test_a_target_made_illegal_before_resolution_is_not_affected(self):
        # CR 608.2b: the destroyed creature's slot does nothing; the other slot still acts.
        self.destroy_on_cast("Theirs")
        cast(self.ex, self.p0, self.swipe(), targets=((self.theirs,), (self.mine,)))
        self.assertEqual(self.world.zone_of(self.theirs).kind, ZONE_GRAVEYARD)
        self.assertEqual(self.ex.damage, {})
        self.assertEqual(self.power(self.mine), 3)

    def test_the_other_slot_made_illegal_leaves_this_one_acting(self):
        self.destroy_on_cast("Mine")
        cast(self.ex, self.p0, self.swipe(), targets=((self.theirs,), (self.mine,)))
        self.assertEqual(self.world.zone_of(self.mine).kind, ZONE_GRAVEYARD)
        self.assertEqual(self.ex.damage, {self.theirs: 3})


class TestActivationSlots(TargetSlotsCase):
    def brawler(self):
        """ "{0}: Target creature you control gets +2/+0. Up to one target creature you don't
        control is dealt 2 damage." """
        ability = ActivatedAbility(cost=Cost(()), effect=Seq((pump(ONE_MINE, 2), damage(UP_TO_ONE_THEIRS, 2))))
        brawler = self.world.add_card(card_id("Brawler", "1", "1"), self.p0, ZONE_BATTLEFIELD)
        self.ex.attach_card(brawler, record_of([ability], oid=self.world.cards[brawler].identity.oracle_id))
        return brawler, ability

    def test_an_activation_may_leave_its_up_to_slot_empty(self):
        brawler, ability = self.brawler()
        self.assertEqual(len(activation_target_slots(self.ex, ability.effect, source=brawler, seat=self.p0)), 2)
        activate(self.ex, brawler, 0, seat=self.p0, targets=(self.mine,))
        self.assertEqual((self.power(self.mine), self.ex.damage), (4, {}))
        activate(self.ex, brawler, 0, seat=self.p0, targets=((self.mine,), (self.theirs,)))
        self.assertEqual((self.power(self.mine), self.ex.damage), (6, {self.theirs: 2}))
        with self.assertRaises(ValueError):  # the other slot's creature in this slot's place
            activate(self.ex, brawler, 0, seat=self.p0, targets=((self.theirs,), (self.mine,)))


class TestDriverOracle(TargetSlotsCase):
    def test_a_candidate_that_leaves_a_later_slot_empty_is_not_offered(self):
        # "Target creature gets +1/+0. Another target creature you control is dealt 1 damage."
        # The second slot can only take Mine, so the first must not.
        from MTG_bot.core.ability_tree import SpellAbility
        from MTG_bot.core.executor.query import spell_target_slots
        from MTG_bot.core.executor.stack import can_designate, slot_options

        spell = self.spell(
            "Pair", pump(target(QConst(1)), 1), damage(target(QConst(1), ControllerRef.YOU, ANOTHER), 1)
        )

        node = next(a for a in self.ex.binder.handle_record[spell].abilities if isinstance(a, SpellAbility))

        def slots():
            return spell_target_slots(self.ex, node, spell_handle=spell, seat=self.p0)

        self.assertEqual(slot_options(slots(), ()), (self.theirs, self.theirs2))
        self.assertEqual(slot_options(slots(), ((self.theirs,),)), (self.mine,))
        self.assertTrue(can_designate(slots()))
        for h in (self.theirs, self.theirs2):
            self.world.move_to_zone(h, self.p1, ZONE_GRAVEYARD)
        self.assertFalse(can_designate(slots()))  # Mine cannot be both targets
