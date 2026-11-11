"""Instants in combat (CR 117.3, 506-511): after blockers are declared, before the damage step,
the players hold priority in the declare-blockers step, and an instant cast there resolves before
any damage.

  * burn before the damage step kills the attacker (it deals nothing); a pump raises a blocker
    over the lethality threshold (it survives marked); with no response combat goes on;
  * the menu prices a target's cost increase with the lands the player can tap (CR 601.2f-h),
    and paying taps only the lands the spell needs (CR 605.3a);
  * a spell cast after another sees the state the first left behind;
  * with no attackers there is no declare-blockers step (CR 508.8).
"""

from __future__ import annotations

from MTG_bot.core.executor.legality import DECLARE_BLOCKERS, SECOND_MAIN
from MTG_bot.core.executor.menu import menu, perform
from MTG_bot.core.state import ZONE_BATTLEFIELD, ZONE_GRAVEYARD, ZONE_HAND
from MTG_bot.core.test_executor_blockers import BlockerCase

_BASIC = {"W": "Plains", "U": "Island", "B": "Swamp", "R": "Mountain", "G": "Forest"}


class Rung2Case(BlockerCase):
    """BlockerCase + land mana and the declare-blockers priority point.

    Mana empties as each step and phase ends (CR 500.4), so mana put in the
    pool before the turn is gone by combat. :meth:`mana` gives the seat
    untapped basic lands instead, which paying taps (CR 601.2g, 605.3a)."""

    def mana(self, seat, **keys):
        for key, amount in keys.items():
            name = _BASIC[key]
            record = next(
                self.supply.pool.results[oid].card
                for oid, meta in self.supply.metas.items()
                if meta.name == name
            )
            for _ in range(amount):
                self.ex.attach_card(self.real(name, seat), record)

    def to_blocks(self):
        """P0's turn, its attack declared and blocked, players holding priority in the
        declare-blockers step with an empty stack."""
        self.ex.begin_turn(self.p0)
        self.ex.combat_attacks(self.p0)
        self.ex.pass_until(DECLARE_BLOCKERS)
        self.assertEqual(self.ex.phase, DECLARE_BLOCKERS)

    def row(self, seat, spell):
        return next(r for r in menu(self.ex, seat) if r.token == f"cast:{spell}")

    def cast_at(self, seat, spell, target):
        """``seat`` casts ``spell`` at ``target`` from its menu, paying as the menu does."""
        self.assertTrue(perform(self.ex, seat, self.row(seat, spell), (target,)))


class TestInstantsInCombat(Rung2Case):
    def test_burn_after_blocks_kills_the_attacker(self):
        brute = self.synth("Brute", 2, 2, self.p0)  # 2 toughness: Shock kills
        guard = self.synth("Guard", 3, 3, self.p1)
        shock = self.real("Shock", self.p1, zone=ZONE_HAND)
        self.begin()
        self.mana(self.p1, R=1)
        self.answers[f"block:{guard}"] = str(brute)
        self.to_blocks()
        self.cast_at(self.p1, shock, brute)
        self.ex.combat_blocks(self.p0)
        # the attacker dies BEFORE the damage step and deals nothing.
        self.assertEqual(self.world.zone_of(brute).kind, ZONE_GRAVEYARD)
        self.assertEqual(self.world.zone_of(guard).kind, ZONE_BATTLEFIELD)
        self.assertEqual(self.world.players[self.p1].life, 20)
        self.assertEqual(self.world.players[self.p0].life, 20)

    def test_paying_taps_only_the_lands_the_spell_needs(self):
        brute = self.synth("Brute", 2, 2, self.p0)
        guard = self.synth("Guard", 3, 3, self.p1)
        shock = self.real("Shock", self.p1, zone=ZONE_HAND)
        self.begin()
        self.mana(self.p1, R=3)
        self.answers[f"block:{guard}"] = str(brute)
        self.to_blocks()
        self.cast_at(self.p1, shock, brute)
        self.assertEqual(self.world.zone_of(brute).kind, ZONE_GRAVEYARD)
        mountains = [
            h
            for h, c in self.world.cards.items()
            if c.identity.name == "Mountain" and self.world.controller_of(h) == self.p1
        ]
        self.assertEqual(sum(self.world.cards[h].tapped for h in mountains), 1)
        self.assertEqual(self.world.players[self.p1].mana_pool, {})

    def test_a_taxed_target_is_priced_with_the_lands_that_can_pay(self):
        # CR 601.2f-h: Pursued Whale makes the defender's spells that target it cost {3}
        # more; one Mountain pays {R} at P0, not {R}+{3} at the Whale.
        whale = self.real("Pursued Whale", self.p0)
        shock = self.real("Shock", self.p1, zone=ZONE_HAND)
        self.begin()
        self.mana(self.p1, R=1)
        self.to_blocks()
        (slot,) = self.row(self.p1, shock).slots
        self.assertIn(self.p0, slot.candidates)
        self.assertNotIn(whale, slot.candidates)

    def test_a_taxed_target_the_lands_pay_is_offered_and_cast(self):
        whale = self.real("Pursued Whale", self.p0)
        shock = self.real("Shock", self.p1, zone=ZONE_HAND)
        self.begin()
        self.mana(self.p1, R=4)
        self.to_blocks()
        (slot,) = self.row(self.p1, shock).slots
        self.assertIn(whale, slot.candidates)
        self.cast_at(self.p1, shock, whale)
        self.assertEqual(self.world.zone_of(shock).kind, ZONE_GRAVEYARD)  # cast, all four tapped
        mountains = [h for h, c in self.world.cards.items() if c.identity.name == "Mountain"]
        self.assertTrue(all(self.world.cards[h].tapped for h in mountains))

    def test_with_no_response_combat_goes_on(self):
        brute = self.synth("Brute", 3, 3, self.p0)
        shock = self.real("Shock", self.p0, zone=ZONE_HAND)
        self.begin()
        self.mana(self.p0, R=1)
        self.ex.begin_turn(self.p0)
        self.ex.combat_step(self.p0)
        self.assertEqual(self.world.zone_of(shock).kind, ZONE_HAND)
        self.assertEqual(self.world.zone_of(brute).kind, ZONE_BATTLEFIELD)
        self.assertEqual(self.world.players[self.p1].life, 17)  # unburned

    def test_no_attackers_no_blockers_step(self):
        self.synth("Alpha", 2, 2, self.p0)
        self.synth("Beta", 2, 2, self.p1)
        self.begin()
        self.default_answer = "DECLINE"  # the attack ask declines
        self.ex.begin_turn(self.p0)
        self.ex.combat_step(self.p0)
        self.assertEqual(self.ex.phase, SECOND_MAIN)
        self.assertEqual([w for _v, w in self.seen_asks if w.startswith("block:")], [])
        self.assertEqual(self.rows("DECLARE_BLOCKERS"), [])

    def test_pump_raises_the_blocker_over_the_threshold(self):
        brute = self.synth("Brute", 3, 3, self.p0)
        guard = self.synth("Guard", 3, 3, self.p1)
        growth = self.real("Titanic Growth", self.p1, zone=ZONE_HAND)
        self.begin()
        self.mana(self.p1, G=2)
        self.answers[f"block:{guard}"] = str(brute)
        self.to_blocks()
        self.cast_at(self.p1, growth, guard)
        self.ex.combat_blocks(self.p0)
        # 6/6 Guard reads the ledger: it takes 3 of 6 and out-fights 3/3.
        self.assertEqual(self.world.zone_of(guard).kind, ZONE_BATTLEFIELD)
        self.assertEqual(self.world.zone_of(brute).kind, ZONE_GRAVEYARD)
        self.assertEqual(self.world.players[self.p1].life, 20)
        self.assertEqual(self.ex.damage.get(guard, 0), 3)

    def test_negative_power_dealer_deals_no_damage(self):
        # Carrion Grub (0/5, +X/+0 over an empty graveyard) blocks with no
        # positive power. The damage lane's zero guard reads the whole
        # non-positive half-line: such a dealer deals no combat damage
        # (CR 510.1a), and damage is never negative.
        attacker = self.synth("Attacker", 2, 2, self.p0)
        grub = self.real("Carrion Grub", self.p1)
        self.begin()
        self.answers[f"block:{grub}"] = str(attacker)
        self.ex.begin_turn(self.p0)
        self.ex.combat_step(self.p0)
        dealers = {row.subject for row in self.rows("COMBAT_DAMAGE")}
        self.assertNotIn(grub, dealers)  # the powerless dealer stayed silent
        self.assertEqual(self.world.players[self.p0].life, 20)
        self.assertEqual(self.world.zone_of(attacker).kind, ZONE_BATTLEFIELD)

    def test_a_second_spell_sees_what_the_first_left(self):
        attacker = self.synth("Attacker", 2, 2, self.p0)
        blocker = self.synth("Blocker", 2, 2, self.p1)
        shock_a = self.real("Shock", self.p0, zone=ZONE_HAND)
        shock_b = self.real("Shock", self.p1, zone=ZONE_HAND)
        self.begin()
        self.mana(self.p0, R=1)
        self.mana(self.p1, R=1)
        self.answers[f"block:{blocker}"] = str(attacker)
        self.to_blocks()
        self.cast_at(self.p0, shock_a, blocker)  # kills it
        # the post-death state: the dead blocker is gone from P1's targets.
        (slot,) = self.row(self.p1, shock_b).slots
        self.assertNotIn(blocker, slot.candidates)
        self.assertIn(attacker, slot.candidates)
        self.cast_at(self.p1, shock_b, attacker)
        self.ex.combat_blocks(self.p0)
        # mutual pre-damage burns: zero combat damage, both life untouched.
        self.assertEqual(self.world.zone_of(attacker).kind, ZONE_GRAVEYARD)
        self.assertEqual(self.world.zone_of(blocker).kind, ZONE_GRAVEYARD)
        self.assertEqual(self.world.players[self.p0].life, 20)
        self.assertEqual(self.world.players[self.p1].life, 20)
