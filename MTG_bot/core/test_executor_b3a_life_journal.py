"""B3a (BUGCATCH D1): the life-loss journal feed (LIFE_LOST).

Pins the events.py fix: a non-damage life DECREASE (Verb.LOSE_LIFE —
"you lose 3 life", the corpus' life-as-cost lane) emits exactly one
LIFE_LOST row carrying the ACTUAL clamped delta, while damage losses
keep emitting DAMAGE rows ONLY (CR 118.5: losing life is not dealt
damage) and gains keep emitting LIFE_GAINED (binding.py dispatches
LifeGainedEvent by kind, so a loss must never borrow either kind).
The fold invariant the audit detector relies on:
    final_life == start + ΣLIFE_GAINED − ΣDAMAGE − ΣLIFE_LOST
"""

import itertools
import unittest

from MTG_bot.core.ability_tree import (
    Atom,
    AtomArgs,
    ControllerRef,
    FAnd,
    Filter,
    QConst,
    Selector,
    SelectorMode,
    Verb,
    Zone,
    ZoneKind,
)
from MTG_bot.core.executor import Executor
from MTG_bot.core.identity import CardIdentity
from MTG_bot.core.state import ZONE_BATTLEFIELD, GameWorld

_ORACLE_SEQ = itertools.count(1)


def card_id(name="Source", power="2", toughness="2"):
    n = next(_ORACLE_SEQ)
    return CardIdentity(
        oracle_id=f"{n:08x}-1111-2222-3333-444444444444",
        name=name,
        type_line="Creature",
        power=power,
        toughness=toughness,
        cmc=2,
    )


def atom(verb, **roles):
    return Atom(verb=verb, args=AtomArgs(pairs=tuple(roles.items())))


UNIV: Filter = FAnd(())


def player_sel() -> Selector:
    return Selector(
        QConst(1), SelectorMode.TARGET, UNIV, Zone(ZoneKind.PLAYER, ControllerRef.ANY)
    )


class LifeJournalCase(unittest.TestCase):
    """p0 owns a battlefield source card; both players at 20 life."""

    def setUp(self):
        self.world = GameWorld(num_players=2, start_life=20, master_seed=11)
        self.p0, self.p1 = self.world.player_order[0], self.world.player_order[1]
        self.source = self.world.add_card(card_id(), self.p0, ZONE_BATTLEFIELD)
        self.ex = Executor(self.world)

    def rows(self, kind):
        return [e for e in self.ex.journal.events if e.kind == kind]

    def life(self, player):
        return self.world.players[player].life


class TestLifeLostFeed(LifeJournalCase):
    def test_lose_life_emits_one_life_lost_row(self):
        self.ex.execute(
            atom(Verb.LOSE_LIFE, controller=ControllerRef.YOU, amount=QConst(3)),
            source=self.source,
            controller=self.p0,
        )
        self.assertEqual(self.life(self.p0), 17)
        lost = self.rows("LIFE_LOST")
        self.assertEqual(len(lost), 1)
        self.assertEqual(lost[0].subject, self.p0)
        self.assertEqual(lost[0].data, (3,))
        self.assertEqual(lost[0].cause_verb, "LOSE_LIFE")
        # The loss must not masquerade as damage or as a (negative) gain.
        self.assertEqual(self.rows("DAMAGE"), [])
        self.assertEqual(self.rows("LIFE_GAINED"), [])

    def test_lose_life_clamp_amount_is_the_actual_delta(self):
        # The verb 0-clamps (CR 118.5.2a: life can't go negative); the
        # journalled amount is the REAL delta, so the fold reconstructs.
        self.ex.execute(
            atom(Verb.LOSE_LIFE, controller=ControllerRef.YOU, amount=QConst(30)),
            source=self.source,
            controller=self.p0,
        )
        self.assertEqual(self.life(self.p0), 0)
        lost = self.rows("LIFE_LOST")
        self.assertEqual([e.data for e in lost], [(20,)])

    def test_gain_life_still_journals_gain_not_loss(self):
        self.ex.execute(
            atom(Verb.GAIN_LIFE, controller=ControllerRef.YOU, amount=QConst(3)),
            source=self.source,
            controller=self.p0,
        )
        self.assertEqual(self.life(self.p0), 23)
        self.assertEqual([e.data for e in self.rows("LIFE_GAINED")], [(3,)])
        self.assertEqual(self.rows("LIFE_LOST"), [])

    def test_deal_damage_to_player_is_damage_only(self):
        self.ex.execute(
            atom(Verb.DEAL_DAMAGE, target=player_sel(), amount=QConst(5)),
            source=self.source,
            controller=self.p0,
            bindings={"target": self.p1},
        )
        self.assertEqual(self.life(self.p1), 15)
        self.assertEqual([e.data for e in self.rows("DAMAGE")], [(5,)])
        # CR 118.5: dealt damage is journalled as DAMAGE, never LIFE_LOST
        # (DamageDealtEvent must not double-count a loss).
        self.assertEqual(self.rows("LIFE_LOST"), [])

    def test_fold_reconstructs_mixed_history(self):
        for act in (
            atom(Verb.LOSE_LIFE, controller=ControllerRef.YOU, amount=QConst(3)),
            atom(Verb.GAIN_LIFE, controller=ControllerRef.YOU, amount=QConst(2)),
            atom(Verb.LOSE_LIFE, controller=ControllerRef.YOU, amount=QConst(4)),
        ):
            self.ex.execute(act, source=self.source, controller=self.p0)
        self.ex.execute(
            atom(Verb.DEAL_DAMAGE, target=player_sel(), amount=QConst(6)),
            source=self.source,
            controller=self.p0,
            bindings={"target": self.p0},
        )
        gains = sum(e.amount for e in self.rows("LIFE_GAINED"))
        losses = sum(e.amount for e in self.rows("LIFE_LOST"))
        dmg = sum(e.amount for e in self.rows("DAMAGE"))
        self.assertEqual(self.life(self.p0), 20 + gains - losses - dmg)
        self.assertEqual(self.life(self.p0), 9)


if __name__ == "__main__":
    unittest.main()
