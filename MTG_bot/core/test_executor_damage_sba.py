"""Round-16a pins: marked damage, the SBA lethal sweep, and Verb.FIGHT.

Replaces the 15-round instant-lethal shortcut (BINDING plan
KNOWLEDGE/2026-09-30/11-round16-combat-plan.md §16a):

* damage LANDS AS A MARK on the executor-side ``Executor.damage`` ledger
  (CR 120.1), cleared when the permanent leaves the battlefield (CR 120.6)
  and again at end of turn (CR 514.2, the cleanup step);
* lethality is a STATE-BASED ACTION (CR 704.3): the settle loop scans the
  battlefield after triggers, kills every marked>=toughness creature that
  is not indestructible and every toughness<=0 creature that IS
  (CR 702.12b), and re-runs until stable; SBA kills carry the journal
  attribution cause=None / cause_verb="STATE_CHECK" — no card gets
  credited for the state check;
* Verb.FIGHT (CR 701.12) is a non-combat simultaneous damage exchange
  riding the SAME marks, so a mutual kill kills both in one atom.
"""

from __future__ import annotations

import unittest

from MTG_bot.core.ability_tree import (
    ControllerRef,
    Keyword,
    KeywordAbility,
    PtDelta,
    PtDirection,
    QConst,
    Verb,
    Zone,
    ZoneKind,
)
from MTG_bot.core.state import ZONE_BATTLEFIELD, ZONE_GRAVEYARD, ZONE_HAND
from MTG_bot.core.test_executor_verbs import (
    BF_ANY,
    HAND_YOU,
    UNIV,
    ExecutorCase,
    atom,
    card_id,
    target_sel,
)


class TestMarkedDamage(ExecutorCase):
    def test_sublethal_damage_is_a_mark_not_a_kill(self):
        self.ex.execute(
            atom(Verb.DEAL_DAMAGE, target=target_sel(), amount=QConst(1)),
            source=self.alpha,
            controller=self.p0,
            bindings={"target": self.alpha},
        )
        self.assertEqual(self.world.zone_of(self.alpha).kind, ZONE_BATTLEFIELD)
        self.assertEqual(self.ex.damage, {self.alpha: 1})

    def test_marks_accumulate_across_atoms_then_the_sba_kills(self):
        one = atom(Verb.DEAL_DAMAGE, target=target_sel(), amount=QConst(1))
        self.ex.execute(
            one, source=self.alpha, controller=self.p0, bindings={"target": self.alpha}
        )
        self.assertEqual(self.ex.damage[self.alpha], 1)  # survives at 1 on a 2/2
        self.ex.execute(
            one, source=self.alpha, controller=self.p0, bindings={"target": self.alpha}
        )
        self.assertEqual(self.world.zone_of(self.alpha).kind, ZONE_GRAVEYARD)
        # CR 120.6: the marks LEFT with the corpse — no stale ledger entry.
        self.assertNotIn(self.alpha, self.ex.damage)

    def test_cleanup_step_clears_all_marks(self):
        self.ex.execute(
            atom(Verb.DEAL_DAMAGE, target=target_sel(), amount=QConst(1)),
            source=self.alpha,
            controller=self.p0,
            bindings={"target": self.alpha},
        )
        self.assertIn(self.alpha, self.ex.damage)
        self.ex.end_turn()  # CR 514.2: the cleanup step removes all damage
        self.assertEqual(self.ex.damage, {})

    def test_zone_change_clears_the_marks(self):
        self.ex.execute(
            atom(Verb.DEAL_DAMAGE, target=target_sel(), amount=QConst(1)),
            source=self.alpha,
            controller=self.p0,
            bindings={"target": self.alpha},
        )
        self.assertEqual(self.ex.damage[self.alpha], 1)
        # The engine only ever moves cards INSIDE an atom (the journal diff
        # runs across one atom boundary), so the bounce rides MOVE_ZONE.
        self.ex.execute(
            atom(
                Verb.MOVE_ZONE,
                cards=target_sel(UNIV, BF_ANY),
                destination=Zone(ZoneKind.HAND, ControllerRef.YOU),
            ),
            source=self.alpha,
            controller=self.p0,
            bindings={"cards": [self.alpha]},
        )
        self.assertEqual(self.world.zone_of(self.alpha).kind, ZONE_HAND)
        self.assertNotIn(self.alpha, self.ex.damage)  # CR 120.6
        # Back on the battlefield it is a FRESH object: one more point is
        # survivable again (the mark did not follow it to hand and back).
        self.ex.execute(
            atom(
                Verb.MOVE_ZONE,
                cards=target_sel(UNIV, HAND_YOU),
                destination=Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU),
            ),
            source=self.alpha,
            controller=self.p0,
            bindings={"cards": [self.alpha]},
        )
        self.ex.execute(
            atom(Verb.DEAL_DAMAGE, target=target_sel(), amount=QConst(1)),
            source=self.alpha,
            controller=self.p0,
            bindings={"target": self.alpha},
        )
        self.assertEqual(self.world.zone_of(self.alpha).kind, ZONE_BATTLEFIELD)


class TestStateBasedActions(ExecutorCase):
    def grant_indestructible(self, *targets):
        self.ex.apply_effect(
            atom(
                Verb.GRANT_ABILITY,
                target=target_sel(),
                ability=KeywordAbility(keyword=Keyword.INDESTRUCTIBLE),
            ),
            source=self.alpha,
            controller=self.p0,
            bindings={"target": list(targets)},
        )

    def test_indestructible_survives_lethal_marks(self):
        self.grant_indestructible(self.alpha)
        self.ex.execute(
            atom(Verb.DEAL_DAMAGE, target=target_sel(), amount=QConst(6)),
            source=self.alpha,
            controller=self.p0,
            bindings={"target": self.alpha},
        )
        self.assertEqual(self.world.zone_of(self.alpha).kind, ZONE_BATTLEFIELD)

    def test_zero_toughness_dies_even_indestructible(self):
        # CR 702.12b: indestructible ignores lethal damage, NOT 0-or-less
        # toughness — the SBA still buries it.
        self.grant_indestructible(self.alpha)
        self.ex.execute(
            atom(
                Verb.MODIFY_PT,
                target=target_sel(),
                toughness=PtDelta(PtDirection.DECREASE, QConst(2)),
            ),
            source=self.alpha,
            controller=self.p0,
            bindings={"target": self.alpha},
        )
        self.assertEqual(self.world.zone_of(self.alpha).kind, ZONE_GRAVEYARD)

    def test_sba_kill_is_attributed_to_the_state_check(self):
        # The catalog reconciliation depends on it: no card owns an SBA kill.
        self.ex.execute(
            atom(Verb.DEAL_DAMAGE, target=target_sel(), amount=QConst(1)),
            source=self.alpha,
            controller=self.p0,
            bindings={"target": self.beta},
        )
        dies = [e for e in self.ex.journal.events if e.kind == "CREATURE_DIES"]
        self.assertEqual(len(dies), 1)
        self.assertIsNone(dies[-1].cause)
        self.assertEqual(dies[-1].cause_verb, "STATE_CHECK")


class TestFight(ExecutorCase):
    def fight(self, attacker, foe, controller=None):
        self.ex.execute(
            atom(Verb.FIGHT, target=target_sel()),
            source=attacker,
            controller=controller or self.p0,
            bindings={"target": foe},
        )

    def test_mutual_kill_kills_both_in_one_atom(self):
        # Alpha 2/2 vs Mirror 2/2: each mark lands inside the SAME atom
        # boundary, one SBA batch buries both (CR 701.12b simultaneity).
        mirror = self.world.add_card(
            card_id("Mirror", "2", "2"), self.p1, ZONE_BATTLEFIELD
        )
        self.fight(self.alpha, mirror)
        self.assertEqual(self.world.zone_of(self.alpha).kind, ZONE_GRAVEYARD)
        self.assertEqual(self.world.zone_of(mirror).kind, ZONE_GRAVEYARD)

    def test_nonlethal_trade_leaves_the_survivor_marked(self):
        delta = self.world.add_card(
            card_id("Delta", "3", "3"), self.p1, ZONE_BATTLEFIELD
        )
        self.fight(self.alpha, delta)  # 2/2 vs 3/3: Alpha dies, Delta 3-on-3
        self.assertEqual(self.world.zone_of(self.alpha).kind, ZONE_GRAVEYARD)
        self.assertEqual(self.world.zone_of(delta).kind, ZONE_BATTLEFIELD)
        self.assertEqual(self.ex.damage[delta], 2)

    def test_attacker_falls_back_to_the_result_register(self):
        # The orphan-verb contract (R7-8): a FIGHT atom carries no attacker
        # role.  A battlefield source wins (Brash's activation); otherwise
        # the last ACTION's result register (Primal Might's +X/+X creature).
        self.ex.execute(
            atom(Verb.FIGHT, target=target_sel()),
            source=self.h1,  # a card in HAND — not a legal fighter
            controller=self.p0,
            bindings={"target": self.beta, "result": [self.gamma]},
        )
        self.assertEqual(self.world.zone_of(self.beta).kind, ZONE_GRAVEYARD)
        self.assertEqual(self.world.zone_of(self.gamma).kind, ZONE_BATTLEFIELD)
        self.assertEqual(self.ex.damage[self.gamma], 1)

    def test_no_legal_foe_is_not_a_fight(self):
        # C17 clamp: an empty designation does not raise and touches nobody.
        before = len(self.ex.journal.events)
        self.ex.execute(
            atom(Verb.FIGHT, target=target_sel()),
            source=self.alpha,
            controller=self.p0,
            bindings={"target": []},
        )
        self.assertEqual(self.world.zone_of(self.beta).kind, ZONE_BATTLEFIELD)
        self.assertEqual(self.ex.damage, {})
        self.assertEqual(len(self.ex.journal.events), before)

    def test_no_attacker_anywhere_stays_loud(self):
        # Flag, don't degrade: a FIGHT with neither a battlefield source nor
        # a result register is a compile/dispatch bug, not a no-op.
        with self.assertRaises(NotImplementedError):
            self.ex.execute(
                atom(Verb.FIGHT, target=target_sel()),
                source=self.h1,
                controller=self.p0,
                bindings={"target": self.beta},
            )


if __name__ == "__main__":
    unittest.main()
