"""The player life-total quantity ``QProp("controller", QPropField.LIFE)``, the amount in Peer
into the Abyss's "loses half their life. Round up".

It is a plain, order-free attribute read of the referent player's current total, scoped by
``ctx.controller`` like the CARDS_IN_* fields; ``LOSE_LIFE`` reads it through ``resolve`` end to
end; a non-player referent is rejected at construction.
"""

import unittest

from MTG_bot.core.ability_tree import (
    ControllerRef,
    QBin,
    QBinOp,
    QConst,
    QProp,
    QPropField,
    Verb,
)
from MTG_bot.core.executor import Executor
from MTG_bot.core.executor.durations import DurationLedger
from MTG_bot.core.executor.quantity import ExecCtx, resolve
from MTG_bot.core.state import GameWorld
from MTG_bot.core.test_executor_binding import atom, card_id, reset_oracle_ids


def half_life() -> QBin:
    """Half the controller's life rounded up, in the (n + 1) // 2 idiom (QBinOp.DIV floors)."""
    return QBin(
        QBinOp.DIV,
        QBin(QBinOp.ADD, QProp("controller", QPropField.LIFE), QConst(1)),
        QConst(2),
    )


class R24ACase(unittest.TestCase):
    def setUp(self) -> None:
        reset_oracle_ids()
        self.world = GameWorld(num_players=2, start_life=20, master_seed=24)
        self.p0, self.p1 = self.world.player_order[0], self.world.player_order[1]
        self.peer = self.world.add_card(card_id("Peer into the Abyss"), self.p0)
        self.ex = Executor(self.world)

    def _ctx(self, controller) -> ExecCtx:
        return ExecCtx(
            world=self.world,
            ledger=DurationLedger(),
            controller=controller,
            source=self.peer,
            bindings={},
            decisions=(),
        )


class TestLifePropRead(R24ACase):
    def test_controller_life_reads_current_total(self):
        ctx = self._ctx(self.p0)
        self.assertEqual(resolve(QProp("controller", QPropField.LIFE), ctx), 20)
        self.world.players[self.p0].life = 13
        self.assertEqual(resolve(QProp("controller", QPropField.LIFE), ctx), 13)

    def test_lane_is_controller_scoped(self):
        # The "controller" referent resolves through ctx.controller, like
        # the CARDS_IN_* twins — p1's ctx reads p1's total, never p0's.
        self.world.players[self.p1].life = 7
        self.assertEqual(
            resolve(QProp("controller", QPropField.LIFE), self._ctx(self.p1)), 7
        )
        self.assertEqual(
            resolve(QProp("controller", QPropField.LIFE), self._ctx(self.p0)), 20
        )

    def test_read_is_order_free(self):
        # Determinism contract: repeated reads never drift and do not
        # depend on any iteration (it is a plain attribute read; pinned so
        # a future replacement must preserve it).
        ctx = self._ctx(self.p0)
        q = QProp("controller", QPropField.LIFE)
        self.assertEqual([resolve(q, ctx) for _ in range(3)], [20, 20, 20])


class TestRoundUpHalfExpression(R24ACase):
    def test_even_half_is_exact(self):
        self.assertEqual(resolve(half_life(), self._ctx(self.p0)), 10)  # 20

    def test_odd_half_rounds_up(self):
        self.world.players[self.p0].life = 13
        self.assertEqual(resolve(half_life(), self._ctx(self.p0)), 7)

    def test_one_rounds_up_to_one_not_zero(self):
        # Rounding up: (1 + 1) // 2 = 1, so a player at 1 life still loses life.
        self.world.players[self.p0].life = 1
        self.assertEqual(resolve(half_life(), self._ctx(self.p0)), 1)


class TestLoseLifeEndToEnd(R24ACase):
    def test_you_lose_half_your_life(self):
        # End to end through Executor.execute (settle and triggers ride along).
        self.ex.execute(
            atom(Verb.LOSE_LIFE, controller=ControllerRef.YOU, amount=half_life()),
            source=self.peer,
            controller=self.p0,
        )
        self.assertEqual(self.world.players[self.p0].life, 10)
        self.assertEqual(self.world.players[self.p1].life, 20)

    def test_opponent_halves_in_their_own_coordinates(self):
        # "each opponent loses half their life" is EachPlayer(controller)
        # in the tree; the per-fire coordinate pin: p1 firing the same
        # atom loses HALF OF 13 ROUNDED UP (7), leaving 6 — not p0.
        self.world.players[self.p1].life = 13
        self.ex.execute(
            atom(Verb.LOSE_LIFE, controller=ControllerRef.YOU, amount=half_life()),
            source=self.peer,
            controller=self.p1,
        )
        self.assertEqual(self.world.players[self.p1].life, 6)
        self.assertEqual(self.world.players[self.p0].life, 20)


class TestLifeReferentValidation(R24ACase):
    def test_source_referent_rejected(self):
        # A life TOTAL is a player property; a non-player referent must
        # raise at construction (never silently re-scope to the controller).
        with self.assertRaises(ValueError):
            QProp("source", QPropField.LIFE)

    def test_target_referent_rejected(self):
        with self.assertRaises(ValueError):
            QProp("target", QPropField.LIFE)


if __name__ == "__main__":
    unittest.main()
