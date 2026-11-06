""""Can't be countered": a PREVENT_EFFECT over ``CounteredEvent``.

CR 701.6a: to counter a spell is to remove it from the stack without resolving. CR 101.2: when an
effect says something can't happen, it can't. So a counterspell may still be cast at a spell that
can't be countered (the target is legal) and it resolves, its other instructions happen, an
"unless its controller pays" is still offered, but the spell is not countered and resolves.

Three carriers, one consult (``ReplacementRegistry.prevents_countering``):
* the spell's own static ability, which functions on the stack (CR 113.6g): "This spell can't be
  countered." (Shifting Ceratops, Thought Distortion);
* a resolved effect with a duration: "Spells you control can't be countered this turn." (Veil of
  Summer); it modifies the rules, so it also covers spells cast after it resolved (CR 611.2c);
* a permanent's static ability: "Creature spells can't be countered." (Gaea's Herald).
"""

from __future__ import annotations

from MTG_bot.core.ability_tree import (
    Atom,
    AtomArgs,
    ControllerRef,
    Cost,
    CostManaColor,
    CounteredEvent,
    DurationEot,
    FAnd,
    FAtom,
    FAtomPred,
    QConst,
    Seq,
    SpellKind,
    StaticAbility,
    Verb,
)
from MTG_bot.core.state import ZONE_BATTLEFIELD, ZONE_GRAVEYARD, ZONE_HAND
from MTG_bot.core.test_executor_rung1 import STACK_TARGET, Rung1Case
from MTG_bot.core.test_executor_stack import any_target, atom

IS_SOURCE = FAtom(FAtomPred.IS_SOURCE)
SPELL = FAtom(FAtomPred.STACK_KIND_EQ, string_value="SPELL")
YOURS = FAtom(FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU)
CREATURE = FAtom(FAtomPred.TYPE_EQ, string_value="Creature")


def cant_be_countered(subject) -> Atom:
    return Atom(
        verb=Verb.PREVENT_EFFECT,
        args=AtomArgs(pairs=(("condition", subject), ("event", CounteredEvent(subject)))),
    )


THIS_SPELL_CANT_BE_COUNTERED = StaticAbility(effect=cant_be_countered(IS_SOURCE))


class UncounterableCase(Rung1Case):
    def uncounterable_shock(self, name="Ceratops Bolt"):
        """{R}: 2 damage to any target; "This spell can't be countered.\""""
        return self.give(
            name,
            SpellKind.INSTANT,
            cost=Cost((CostManaColor("R", QConst(1)),)),
            effect=atom(Verb.DEAL_DAMAGE, target=any_target(), amount=QConst(2)),
            extra_abilities=(THIS_SPELL_CANT_BE_COUNTERED,),
        )

    def creature_spell(self, name, seat=None):
        return self.give(
            name,
            SpellKind.CREATURE,
            cost=Cost((CostManaColor("G", QConst(1)),)),
            seat=seat,
            type_line="Creature",
            types=("Creature",),
            power="2",
            toughness="2",
        )

    def counters_rows(self):
        return self.journal_events("COUNTER")


class TestThisSpellCantBeCountered(UncounterableCase):
    def test_the_counterspell_targets_and_resolves_but_does_not_counter(self) -> None:
        bolt = self.uncounterable_shock()
        self.mana(self.p0, R=1)
        cancel = self.counterspell("Cancel", self.p1)
        self.mana(self.p1, U=1)
        self.script(str(cancel))
        self.ex_cast(self.p0, bolt, targets=(self.p1,))
        # the window offered Cancel (a legal target), and Cancel was cast and resolved
        ((vocab, _what),) = self.asks
        self.assertEqual(vocab, ("PASS", str(cancel)))
        self.assertEqual(self.zone_kind(cancel), ZONE_GRAVEYARD)
        self.assertFalse(self.world.players[self.p1].mana_pool.get("U"))
        # the bolt was not countered: it resolved
        self.assertEqual(self.world.players[self.p1].life, 18)
        self.assertEqual(self.zone_kind(bolt), ZONE_GRAVEYARD)
        self.assertEqual(self.counters_rows(), [])
        self.assertEqual(self.ex.stack.frames, [])

    def test_unless_is_still_offered_and_never_counters(self) -> None:
        bolt = self.uncounterable_shock()
        self.mana(self.p0, R=1, G=2)
        leak = self.counterspell("Leak", self.p1, unless=2)
        self.mana(self.p1, U=1)
        self.script(str(leak), "PASS")  # the window, then the payer declines to pay
        self.ex_cast(self.p0, bolt, targets=(self.p1,))
        self.assertEqual([what.split(":")[0] for _v, what in self.asks], ["counter", "pay"])
        self.assertEqual(self.world.players[self.p1].life, 18)
        self.assertEqual(self.world.players[self.p0].mana_pool.get("G"), 2)  # nothing paid
        self.assertEqual(self.counters_rows(), [])

    def test_the_counterspells_other_instructions_happen(self) -> None:
        bolt = self.uncounterable_shock()
        self.mana(self.p0, R=1)
        dig = self.give(
            "Counter and Draw",
            SpellKind.INSTANT,
            cost=Cost((CostManaColor("U", QConst(1)),)),
            seat=self.p1,
            effect=Seq(
                (
                    atom(Verb.COUNTER_SPELL, target=STACK_TARGET),
                    atom(Verb.DRAW, controller=ControllerRef.YOU, amount=QConst(1)),
                )
            ),
        )
        self.mana(self.p1, U=1)
        hand = self.world.players[self.p1].zone(ZONE_HAND).entries
        self.assertEqual(hand, [dig])
        self.script(str(dig))
        self.ex_cast(self.p0, bolt, targets=(self.p1,))
        self.assertEqual(self.world.players[self.p1].life, 18)
        # the counterspell left the hand and its draw happened
        self.assertEqual(self.zone_kind(dig), ZONE_GRAVEYARD)
        self.assertEqual(len(hand), 1)
        self.assertNotIn(dig, hand)

    def test_an_ordinary_spell_is_still_countered(self) -> None:
        shock = self.shock()
        self.mana(self.p0, R=1)
        cancel = self.counterspell("Cancel", self.p1)
        self.mana(self.p1, U=1)
        self.script(str(cancel))
        self.ex_cast(self.p0, shock, targets=(self.p1,))
        self.assertEqual(self.world.players[self.p1].life, 20)
        self.assertEqual(len(self.counters_rows()), 1)


class TestSpellsYouControlThisTurn(UncounterableCase):
    def veil(self):
        """{G}: "Spells you control can't be countered this turn.\""""
        subject = FAnd((SPELL, YOURS))
        prevent = Atom(
            verb=Verb.PREVENT_EFFECT,
            args=AtomArgs(
                pairs=(
                    ("condition", subject),
                    ("event", CounteredEvent(subject)),
                    ("duration", DurationEot()),
                )
            ),
        )
        return self.give(
            "Veil", SpellKind.INSTANT, cost=Cost((CostManaColor("G", QConst(1)),)), effect=prevent
        )

    def test_a_spell_cast_after_the_veil(self) -> None:
        veil = self.veil()
        self.mana(self.p0, G=1)
        self.script("PASS")  # p1 holds no counter yet; the veil resolves
        self.ex_cast(self.p0, veil)
        shock = self.shock()
        self.mana(self.p0, R=1)
        cancel = self.counterspell("Cancel", self.p1)
        self.mana(self.p1, U=1)
        self.script(str(cancel))
        self.ex_cast(self.p0, shock, targets=(self.p1,))
        self.assertEqual(self.world.players[self.p1].life, 18)  # not countered (CR 611.2c)
        self.assertEqual(self.counters_rows(), [])

    def test_only_your_spells_and_only_this_turn(self) -> None:
        veil = self.veil()
        self.mana(self.p0, G=1)
        self.ex_cast(self.p0, veil)
        self.ex.advance_turn()  # p1's turn: the veil has ended
        self.ex.advance_turn()
        shock = self.shock()
        self.mana(self.p0, R=1)
        cancel = self.counterspell("Cancel", self.p1)
        self.mana(self.p1, U=1)
        self.script(str(cancel))
        self.ex_cast(self.p0, shock, targets=(self.p1,))
        self.assertEqual(self.world.players[self.p1].life, 20)  # countered next turn
        self.assertEqual(len(self.counters_rows()), 1)

    def test_an_opponents_spell_is_not_yours(self) -> None:
        self.ex.advance_turn()  # p1's turn
        veil = self.veil()
        self.mana(self.p0, G=1)
        self.ex_cast(self.p0, veil)  # an instant, on the opponent's turn
        bear = self.creature_spell("Bear", seat=self.p1)
        self.mana(self.p1, G=1)
        cancel = self.counterspell("Cancel", self.p0)
        self.mana(self.p0, U=1)
        self.script(str(cancel))
        self.ex_cast(self.p1, bear)
        self.assertEqual(self.zone_kind(bear), ZONE_GRAVEYARD)  # p0's veil covers p0's spells
        self.assertEqual(len(self.counters_rows()), 1)


class TestStaticOnAPermanent(UncounterableCase):
    def herald(self, zone=ZONE_BATTLEFIELD, *, yours=False):
        """A permanent with "Creature spells [you control] can't be countered.\""""
        subject = FAnd((SPELL, CREATURE, YOURS)) if yours else FAnd((SPELL, CREATURE))
        return self.give(
            "Herald",
            SpellKind.CREATURE,
            cost=Cost((CostManaColor("G", QConst(1)),)),
            seat=self.p0,
            zone=zone,
            type_line="Creature",
            types=("Creature",),
            power="1",
            toughness="1",
            extra_abilities=(StaticAbility(effect=cant_be_countered(subject)),),
        )

    def test_it_does_not_protect_its_own_spell(self) -> None:
        # CR 113.6: a permanent's static ability works on the battlefield. Only an ability that
        # says the object itself can't be countered works on the stack (CR 113.6g).
        herald = self.herald(zone=ZONE_HAND)
        self.mana(self.p0, G=1)
        cancel = self.counterspell("Cancel", self.p1)
        self.mana(self.p1, U=1)
        self.script(str(cancel))
        self.ex_cast(self.p0, herald)
        self.assertEqual(self.zone_kind(herald), ZONE_GRAVEYARD)
        self.assertEqual(len(self.counters_rows()), 1)

    def test_you_follows_the_permanents_controller(self) -> None:
        # "Creature spells you control can't be countered." (Destiny Spinner's shape): after P1
        # gains control of the permanent, "you" is P1 (CR 109.5, 611.3a).
        herald = self.herald(yours=True)
        self.ex.execute(
            atom(Verb.GAIN_CONTROL, target=any_target(), controller=ControllerRef.YOU),
            source=herald,
            controller=self.p1,
            bindings={"target": herald},
        )
        self.assertEqual(self.ex.controller_of(herald), self.p1)
        bear = self.creature_spell("Bear")
        self.mana(self.p0, G=1)
        cancel = self.counterspell("Cancel", self.p1)
        self.mana(self.p1, U=1)
        self.script(str(cancel))
        self.ex_cast(self.p0, bear)
        self.assertEqual(self.zone_kind(bear), ZONE_GRAVEYARD)  # P0's spell: not protected now
        self.ex.advance_turn()
        cub = self.creature_spell("Cub", seat=self.p1)
        self.mana(self.p1, G=1)
        cancel2 = self.counterspell("Cancel 2", self.p0)
        self.mana(self.p0, U=1)
        self.script(str(cancel2))
        self.ex_cast(self.p1, cub)
        self.assertEqual(self.zone_kind(cub), ZONE_BATTLEFIELD)  # P1's spell: protected

    def test_creature_spells_only_while_it_is_on_the_battlefield(self) -> None:
        herald = self.herald()
        bear = self.creature_spell("Bear")
        self.mana(self.p0, G=1)
        cancel = self.counterspell("Cancel", self.p1)
        self.mana(self.p1, U=1)
        self.script(str(cancel))
        self.ex_cast(self.p0, bear)
        self.assertEqual(self.zone_kind(bear), ZONE_BATTLEFIELD)  # not countered
        shock = self.shock()  # not a creature spell
        self.mana(self.p0, R=1)
        cancel2 = self.counterspell("Cancel 2", self.p1)
        self.mana(self.p1, U=1)
        self.script(str(cancel2))
        self.ex_cast(self.p0, shock, targets=(self.p1,))
        self.assertEqual(self.world.players[self.p1].life, 20)
        # the herald leaves: creature spells can be countered again
        self.ex.execute(
            atom(Verb.DESTROY, target=any_target()),
            source=herald,
            controller=self.p0,
            bindings={"target": herald},
        )
        bear2 = self.creature_spell("Bear 2")
        self.mana(self.p0, G=1)
        cancel3 = self.counterspell("Cancel 3", self.p1)
        self.mana(self.p1, U=1)
        self.script(str(cancel3))
        self.ex_cast(self.p0, bear2)
        self.assertEqual(self.zone_kind(bear2), ZONE_GRAVEYARD)
