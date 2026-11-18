"""B21 templates (DESIGN_ATOM_ONTOLOGY §19): the opening hand, the prohibitions and the game's end,
every wording of the 19 sets each reads, and the cards they complete. Each test fails on the base
(eaedfc1b), where none of these sentences parsed."""

from __future__ import annotations

import unittest
from functools import cache
from pathlib import Path

from MTG_bot.core.ability_tree import (
    CastSpellEvent,
    ControllerRef,
    DurationEot,
    DurationUntilEndOfNextTurn,
    FAnd,
    FAtom,
    FAtomPred,
    FNot,
    FOr,
    GameOutcomeEvent,
    LifeGainedEvent,
    OpeningHandAbility,
    QAtLeast,
    Seq,
    StaticAbility,
    Verb,
    Zone,
    ZoneChangeEvent,
    ZoneKind,
    begin_on_battlefield,
)
from MTG_bot.core.compiler.compiler import compile_card
from MTG_bot.core.compiler.coverage import build_full_registry
from MTG_bot.core.compiler.ingest import ingest_pool
from MTG_bot.core.compiler.templates import AbilityOutcome, EffectOutcome
from MTG_bot.core.compiler.templates_b21 import game_result, prohibit

REPO = Path(__file__).resolve().parents[3]
CREATURE = FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature")
YOU = FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU)
OPPONENTS = FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.OPPONENT)
GRAVEYARDS = Zone(ZoneKind.GRAVEYARD, ControllerRef.ANY)
LIBRARIES = Zone(ZoneKind.LIBRARY, ControllerRef.ANY)
BATTLEFIELD = Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY)


@cache
def _registry():
    return build_full_registry()


def _only(sentence: str):
    matches = _registry().match(sentence)
    assert len(matches) == 1 and matches[0].template.tid.startswith("B21-"), matches
    outcome = matches[0].outcome
    return outcome.ability if isinstance(outcome, AbilityOutcome) else outcome


def _static(*atoms) -> StaticAbility:
    return StaticAbility(effect=atoms[0] if len(atoms) == 1 else Seq(steps=atoms))


def _card(code: str, name: str):
    raw = next(rc for rc in ingest_pool(REPO / "MTG_bot" / "data" / f"{code}.json").values()
               if rc.identity.name == name)
    return compile_card(raw, _registry())


class TestOpeningHand(unittest.TestCase):
    def test_the_leylines_sentence(self) -> None:
        self.assertEqual(
            _only("If this card is in your opening hand, you may begin the game with it on the "
                  "battlefield."),
            OpeningHandAbility(begin_on_battlefield()))

    def test_every_leyline_of_the_19_sets_reads_it(self) -> None:
        """M11 and M20's ten Leylines and FDN Leyline Axe: the opening-hand ability first."""
        for code, name in (("M20", "Leyline of Sanctity"), ("M20", "Leyline of the Void"),
                           ("M20", "Leyline of Anticipation"), ("M20", "Leyline of Combustion"),
                           ("M20", "Leyline of Abundance"), ("M11", "Leyline of Punishment"),
                           ("M11", "Leyline of Vitality"), ("FDN", "Leyline Axe")):
            with self.subTest(name=name):
                self.assertEqual(_card(code, name).card.abilities[0],
                                 OpeningHandAbility(begin_on_battlefield()))


class TestProhibitions(unittest.TestCase):
    def test_the_cast_limits(self) -> None:
        """Rule of Law, Archon of Emeria; Deafening Silence's noncreature spells."""
        self.assertEqual(_only("Each player can't cast more than one spell each turn."),
                         _static(prohibit(CastSpellEvent(filter=FAnd(()), ordinal=QAtLeast(2)))))
        self.assertEqual(
            _only("Each player can't cast more than one noncreature spell each turn."),
            _static(prohibit(CastSpellEvent(filter=FNot(CREATURE), ordinal=QAtLeast(2)))))

    def test_casting_from_zones_one_prohibition_per_zone(self) -> None:
        """Grafdigger's Cage, Weathered Runestone; Kunoros; Drannith Magistrate."""
        self.assertEqual(
            _only("Players can't cast spells from graveyards or libraries."),
            _static(prohibit(CastSpellEvent(filter=FAnd(()), from_zone=GRAVEYARDS)),
                    prohibit(CastSpellEvent(filter=FAnd(()), from_zone=LIBRARIES))))
        self.assertEqual(_only("Players can't cast spells from graveyards."),
                         _static(prohibit(CastSpellEvent(filter=FAnd(()), from_zone=GRAVEYARDS))))
        self.assertEqual(
            _only("Your opponents can't cast spells from anywhere other than their hands."),
            _static(prohibit(CastSpellEvent(
                filter=FAnd(()), actor=OPPONENTS,
                from_zone_not=Zone(ZoneKind.HAND, ControllerRef.OPPONENT)))))

    def test_who_cant_cast_what_and_for_how_long(self) -> None:
        """Steel Golem's static; Silence and Single Combat, effects with their duration."""
        self.assertEqual(_only("You can't cast creature spells."),
                         _static(prohibit(CastSpellEvent(filter=CREATURE, actor=YOU))))
        self.assertEqual(
            _only("Your opponents can't cast spells this turn."),
            EffectOutcome(prohibit(CastSpellEvent(filter=FAnd(()), actor=OPPONENTS),
                                   duration=DurationEot())))
        both = FOr(children=(CREATURE, FAtom(pred=FAtomPred.TYPE_EQ, string_value="Planeswalker")))
        self.assertEqual(
            _only("Players can't cast creature or planeswalker spells until the end of your next "
                  "turn."),
            EffectOutcome(prohibit(CastSpellEvent(filter=both),
                                   duration=DurationUntilEndOfNextTurn())))

    def test_entering_from_graveyards_and_libraries(self) -> None:
        """Grafdigger's Cage, Weathered Runestone's nonland permanent cards, Kunoros."""
        def entering(zone, cards):
            return prohibit(ZoneChangeEvent(zone, BATTLEFIELD, subject=cards))

        self.assertEqual(
            _only("Creature cards in graveyards and libraries can't enter the battlefield."),
            _static(entering(GRAVEYARDS, CREATURE), entering(LIBRARIES, CREATURE)))
        nonland = FAnd(children=(FAtom(pred=FAtomPred.IS_PERMANENT),
                                 FNot(FAtom(pred=FAtomPred.TYPE_EQ, string_value="Land"))))
        self.assertEqual(
            _only("Nonland permanent cards in graveyards and libraries can't enter the "
                  "battlefield."),
            _static(entering(GRAVEYARDS, nonland), entering(LIBRARIES, nonland)))
        self.assertEqual(_only("Creature cards in graveyards can't enter the battlefield."),
                         _static(entering(GRAVEYARDS, CREATURE)))

    def test_gaining_life(self) -> None:
        """Giant Cindermaw, Leyline of Punishment; Quakebringer, Tibalt; Roiling Vortex's turn."""
        self.assertEqual(_only("Players can't gain life."), _static(prohibit(LifeGainedEvent())))
        self.assertEqual(_only("Your opponents can't gain life."),
                         _static(prohibit(LifeGainedEvent(actor=OPPONENTS))))
        self.assertEqual(
            _only("Your opponents can't gain life this turn."),
            EffectOutcome(prohibit(LifeGainedEvent(actor=OPPONENTS), duration=DurationEot())))


class TestTheGamesEnd(unittest.TestCase):
    def test_cant_lose_and_cant_win(self) -> None:
        """Platinum Angel and Herald of Eternal Dawn; Lich's Mastery's first half alone."""
        lose = prohibit(GameOutcomeEvent(won=False, actor=YOU))
        self.assertEqual(
            _only("You can't lose the game and your opponents can't win the game."),
            _static(lose, prohibit(GameOutcomeEvent(won=True, actor=OPPONENTS))))
        self.assertEqual(_only("You can't lose the game."), _static(lose))

    def test_who_loses_and_who_wins(self) -> None:
        """Demonic Pact's mode, Door to Nothingness's target; the win of the upkeep cards."""
        self.assertEqual(_only("You lose the game."),
                         EffectOutcome(game_result(Verb.LOSE_GAME, ControllerRef.YOU)))
        self.assertEqual(_only("Target player loses the game."),
                         EffectOutcome(game_result(Verb.LOSE_GAME, ControllerRef.TARGET_PLAYER)))
        self.assertEqual(_only("You win the game."),
                         EffectOutcome(game_result(Verb.WIN_GAME, ControllerRef.YOU)))

    def test_nine_lives_names_who_loses(self) -> None:
        """B2b's Nine Lives sentence writes the same atom: the loser is "you"."""
        card = _card("M21", "Nine Lives").card
        self.assertIn(game_result(Verb.LOSE_GAME, ControllerRef.YOU),
                      [a.effect for a in card.abilities if hasattr(a, "effect")])


class TestCardsNowWhole(unittest.TestCase):
    def test_the_round_completes_these_compiled_cards(self) -> None:
        for code, name in (("M20", "Rule of Law"), ("M20", "Grafdigger's Cage"),
                           ("M20", "Leyline of Sanctity"),
                           ("ELD", "Deafening Silence"), ("M11", "Platinum Angel"),
                           ("FDN", "Herald of Eternal Dawn"), ("FDN", "Giant Cindermaw")):
            with self.subTest(name=name):
                result = _card(code, name)
                self.assertEqual((tuple(result.unparsed), tuple(result.back_face_unparsed)), ((), ()))


if __name__ == "__main__":
    unittest.main()
