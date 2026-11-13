"""An instruction whose acting player is named through an antecedent ("Its controller creates a
3/3 Golem", Cavalier of Dawn; "Its controller mills two cards", Zulaport Duelist) does nothing
when the antecedent names no object (CR 608.2b: the part of the effect that needs information
about it does not happen), in each lane a designation is made in: a triggered ability, an
activated ability and a spell, each with "up to one target" designating none (CR 115.6).

Each test fails on the code before the fix: CREATE_TOKEN and the one-player role reader raised
on a referent naming no player, and the spell and activation lanes bound no designation at all
for an "up to" slot left empty, so the antecedent read was the dangling-referent refusal (a
crash in the activation lane, a template-fault flag in the spell lane)."""

from __future__ import annotations

from MTG_bot.core.ability_tree import (
    ActivatedAbility,
    ControllerRef,
    Cost,
    CostTap,
    FAnd,
    FAtom,
    FAtomPred,
    FNot,
    QAtMost,
    QConst,
    Selector,
    SelectorMode,
    Seq,
    SpellKind,
    TokenSpec,
    Verb,
    Zone,
    ZoneKind,
)
from MTG_bot.core.executor.legality import activate
from MTG_bot.core.executor.stack import cast
from MTG_bot.core.identity import CardIdentity
from MTG_bot.core.state import ZONE_BATTLEFIELD, ZONE_GRAVEYARD, ZONE_HAND, ZONE_LIBRARY
from MTG_bot.core.test_executor_binding import etb_trigger
from MTG_bot.core.test_executor_layers import BF_ANY, UNIV, LayerCase, atom, card_id
from MTG_bot.core.test_executor_stack import spell_rec

#: "it" / "its controller": the designated object, read back (the B5b-its-controller-token
#: referent Selector).
ITS = Selector(QConst(1), SelectorMode.CHOOSE, UNIV, zones=(Zone(ZoneKind.ANY, ControllerRef.ANY),),
               referent="target")
NONLAND_PERMANENT = FAnd((FAtom(FAtomPred.IS_PERMANENT),
                          FNot(FAtom(FAtomPred.TYPE_EQ, string_value="Land"))))
UP_TO_ONE = Selector(QAtMost(1), SelectorMode.TARGET, NONLAND_PERMANENT, zones=(BF_ANY,))
GOLEM = TokenSpec(name="Golem", type_line="Artifact Creature — Golem", types=("Artifact", "Creature"),
                  subtypes=("Golem",), power=QConst(3), toughness=QConst(3), keywords=(), abilities=())
DESTROY_UP_TO_ONE = atom(Verb.DESTROY, target=UP_TO_ONE)
ITS_CONTROLLER_GOLEM = atom(Verb.CREATE_TOKEN, controller=ITS, tokens=GOLEM)
ITS_CONTROLLER_DRAWS = atom(Verb.DRAW, controller=ITS, amount=QConst(1))
ITS_CONTROLLER_MILLS = atom(
    Verb.MOVE_ZONE, controller=ITS, amount=QConst(2), pop_order="TOP", journal_kind="MILL",
    **{"from": Zone(ZoneKind.LIBRARY, ControllerRef.ANY)},
    destination=Zone(ZoneKind.GRAVEYARD, ControllerRef.ANY),
)


class AbsentAntecedentCase(LayerCase):
    def setUp(self) -> None:
        super().setUp()
        self.ex.begin_turn(self.p0)
        self.answers: list[str] = []
        self.asks: list[tuple[str, tuple[str, ...]]] = []

        def provider(vocab: tuple[str, ...], what: str) -> str:
            self.asks.append((what, tuple(vocab)))
            return self.answers.pop(0) if self.answers else vocab[0]

        self.ex.decisions.provider = provider
        for seat in (self.p0, self.p1):
            for i in range(3):
                self.world.add_card(card_id(f"Library {seat} {i}"), seat, ZONE_LIBRARY)

    def tearDown(self) -> None:
        self.ex.decisions.provider = None

    def golems(self, seat) -> int:
        return sum(
            1
            for h in self.world.players[seat].zone(ZONE_BATTLEFIELD).entries
            if self.world.cards[h].identity.name == "Golem"
        )

    def enter_with(self, effect) -> None:
        """A creature whose ETB trigger is ``effect`` enters from p0's hand."""
        cavalier = self.world.add_card(card_id("Cavalier", "4", "5"), self.p0, ZONE_HAND)
        self.attach(cavalier, [etb_trigger(effect)])
        self.ex.execute(
            atom(Verb.MOVE_ZONE,
                 cards=Selector(QConst(1), SelectorMode.ALL, UNIV,
                                zones=(Zone(ZoneKind.HAND, ControllerRef.YOU),)),
                 destination=Zone(ZoneKind.BATTLEFIELD, ControllerRef.OWNER)),
            source=cavalier,
            controller=self.p0,
            bindings={"cards": cavalier},
        )


class TestTriggerLane(AbsentAntecedentCase):
    def test_no_target_chosen_makes_no_golem(self) -> None:
        self.answers = ["NONE"]  # "up to one": none (CR 115.6)
        self.enter_with(Seq((DESTROY_UP_TO_ONE, ITS_CONTROLLER_GOLEM)))
        self.assertTrue(any("NONE" in vocab for _what, vocab in self.asks))
        self.assertEqual(self.world.zone_of(self.beta).kind, ZONE_BATTLEFIELD)
        self.assertEqual((self.golems(self.p0), self.golems(self.p1)), (0, 0))

    def test_its_controller_creates_the_golem(self) -> None:
        self.answers = [str(self.beta)]
        self.enter_with(Seq((DESTROY_UP_TO_ONE, ITS_CONTROLLER_GOLEM)))
        self.assertEqual(self.world.zone_of(self.beta).kind, ZONE_GRAVEYARD)
        self.assertEqual((self.golems(self.p0), self.golems(self.p1)), (0, 1))

    def test_no_target_chosen_mills_nobody(self) -> None:
        self.answers = ["NONE"]
        self.enter_with(Seq((DESTROY_UP_TO_ONE, ITS_CONTROLLER_MILLS)))
        for seat in (self.p0, self.p1):
            self.assertEqual(len(self.world.players[seat].zone(ZONE_GRAVEYARD).entries), 0)

    def test_its_controller_mills(self) -> None:
        self.answers = [str(self.beta)]
        self.enter_with(Seq((DESTROY_UP_TO_ONE, ITS_CONTROLLER_MILLS)))
        # Beta's controller mills two, beta itself was destroyed: three in that graveyard.
        self.assertEqual(len(self.world.players[self.p1].zone(ZONE_GRAVEYARD).entries), 3)
        self.assertEqual(len(self.world.players[self.p0].zone(ZONE_GRAVEYARD).entries), 0)


class TestActivationLane(AbsentAntecedentCase):
    def relic(self):
        handle = self.world.add_card(card_id("Relic", type_line="Artifact"), self.p0, ZONE_BATTLEFIELD)
        self.attach(handle, [ActivatedAbility(cost=Cost(parts=(CostTap(),)),
                                              effect=Seq((DESTROY_UP_TO_ONE, ITS_CONTROLLER_DRAWS)))])
        return handle

    def hands(self) -> tuple[int, int]:
        return tuple(len(self.world.players[s].zone(ZONE_HAND).entries) for s in (self.p0, self.p1))

    def test_no_target_chosen_draws_nothing(self) -> None:
        relic, before = self.relic(), self.hands()
        activate(self.ex, relic, 0, seat=self.p0)
        self.assertTrue(self.world.cards[relic].tapped)
        self.assertEqual(self.hands(), before)
        self.assertEqual(self.ex.unresolved_effects, [])

    def test_its_controller_draws(self) -> None:
        relic, before = self.relic(), self.hands()
        activate(self.ex, relic, 0, seat=self.p0, targets=(self.beta,))
        self.assertEqual(self.world.zone_of(self.beta).kind, ZONE_GRAVEYARD)
        self.assertEqual(self.hands(), (before[0], before[1] + 1))


class TestSpellLane(AbsentAntecedentCase):
    def spell(self):
        rec = spell_rec("Undo", SpellKind.INSTANT, effect=Seq((DESTROY_UP_TO_ONE, ITS_CONTROLLER_DRAWS)))
        handle = self.world.add_card(
            CardIdentity(oracle_id=rec.oracle_id, name="Undo", type_line="Instant", power=None,
                         toughness=None, cmc=2),
            self.p0,
            ZONE_HAND,
        )
        self.ex.attach_card(handle, rec)
        return handle

    def test_no_target_chosen_draws_nothing_and_flags_nothing(self) -> None:
        undo = self.spell()
        cast(self.ex, self.p0, undo)
        self.assertEqual(self.world.zone_of(undo).kind, ZONE_GRAVEYARD)
        self.assertEqual(len(self.world.players[self.p1].zone(ZONE_HAND).entries), 0)
        # Not the dangling-referent flag of a template fault: the designation was made, empty.
        self.assertEqual(self.ex.unresolved_effects, [])

    def test_its_controller_draws(self) -> None:
        undo = self.spell()
        cast(self.ex, self.p0, undo, targets=(self.beta,))
        self.assertEqual(self.world.zone_of(self.beta).kind, ZONE_GRAVEYARD)
        self.assertEqual(len(self.world.players[self.p1].zone(ZONE_HAND).entries), 1)
