"""RUNG-2 (response-window arc): the combat-instant window in combat_step.

Coverage contract (mission arc, ruling of 2026-10-05):
  * after blockers are declared and BEFORE the damage step, each seat that
    holds a payable, designable, combat-relevant instant (DEAL_DAMAGE /
    MODIFY_PT / SET_PT in the tree) is ASKED once, in player order;
  * a seat with nothing to offer is never asked and gets no row (C15),
    and with no attackers at all the window never opens;
  * the vocab token is the composite ``<card handle>@<target handle>`` —
    the target rides INSIDE the word, and the second seat's vocabulary is
    computed on the state the first seat's cast left behind (a dead
    creature vanishes from the target list);
  * burn before the damage step kills the attacker (it deals nothing), a
    pump raises a blocker over the lethality threshold (it survives
    marked); PASS writes the WINDOW_PASS audit row and combat proceeds;
  * the audit rows reuse WINDOW_OPEN/WINDOW_PASS with cause_verb
    "COMBAT_WINDOW" and the ``cw:<seat>:<digest>`` site tag;
  * documented narrowing: ONE priority round, no re-asks.
"""

from __future__ import annotations

from unittest import mock

import MTG_bot.core.executor as executor_module
from MTG_bot.core.state import ZONE_BATTLEFIELD, ZONE_GRAVEYARD, ZONE_HAND
from MTG_bot.core.test_executor_blockers import BlockerCase


class Rung2Case(BlockerCase):
    """BlockerCase + the cw: ask probes and a window-mana helper.

    Re-pinned 2026-10-29 (V2): mana empties as each step and phase ends
    (CR 500.5), so mana put in the pool before the turn is gone by the combat
    window, and the engine cannot yet activate mana abilities while casting
    there (CR 605.3a, 601.2g). :meth:`mana` therefore adds the seat's mana as
    the window opens, standing in for the lands it would tap in the window."""

    def setUp(self):
        super().setUp()
        self._window_mana: dict = {}
        real_window = executor_module.open_combat_window

        def window(executor):
            for seat, keys in self._window_mana.items():
                pool = self.world.players[seat].mana_pool
                for key, amount in keys.items():
                    pool[key] = pool.get(key, 0) + amount
            return real_window(executor)

        patcher = mock.patch.object(executor_module, "open_combat_window", window)
        patcher.start()
        self.addCleanup(patcher.stop)

    def mana(self, seat, **keys):
        bucket = self._window_mana.setdefault(seat, {})
        for key, amount in keys.items():
            bucket[key] = bucket.get(key, 0) + amount

    def cw_asks(self):
        """The (vocab, tag) pairs of the cw: window, in ask order."""
        return [(v, w) for (v, w) in self.seen_asks if w.startswith("cw:")]

    def window_rows(self, kind):
        return [
            e
            for e in self.rows(kind)
            if getattr(e, "cause_verb", None) == "COMBAT_WINDOW"
        ]


class TestCombatWindow(Rung2Case):
    def test_burn_answers_the_block_and_kills_the_attacker(self):
        brute = self.synth("Brute", 2, 2, self.p0)  # 2 toughness: Shock kills
        guard = self.synth("Guard", 3, 3, self.p1)
        shock = self.real("Shock", self.p1, zone=ZONE_HAND)
        self.begin()
        self.mana(self.p1, R=1)
        self.answers[f"block:{guard}"] = str(brute)
        self.answers[f"cw:{self.p1}"] = f"{shock}@{brute}"
        self.ex.begin_turn(self.p0)
        self.ex.combat_step(self.p0)
        # exactly one ask — P0 holds no instant and is never consulted.
        asks = self.cw_asks()
        self.assertEqual(len(asks), 1)
        vocab, tag = asks[0]
        self.assertTrue(tag.startswith(f"cw:{self.p1}:"))
        self.assertEqual(vocab[0], "PASS")
        self.assertIn(f"{shock}@{brute}", vocab)
        # the answer lands: the attacker dies BEFORE the damage step and
        # deals nothing — the blocked side takes zero.
        self.assertEqual(self.world.zone_of(brute).kind, ZONE_GRAVEYARD)
        self.assertEqual(self.world.zone_of(guard).kind, ZONE_BATTLEFIELD)
        self.assertEqual(self.world.players[self.p1].life, 20)
        self.assertEqual(self.world.players[self.p0].life, 20)
        # audit: one OPEN (vocab payload, no subject, COMBAT_WINDOW verb),
        # zero PASS rows.
        opens = self.window_rows("WINDOW_OPEN")
        self.assertEqual(len(opens), 1)
        self.assertIsNone(opens[0].subject)
        self.assertEqual(opens[0].data[0], vocab)
        self.assertEqual(len(self.window_rows("WINDOW_PASS")), 0)

    def test_pass_writes_the_audit_row_and_combat_continues(self):
        brute = self.synth("Brute", 3, 3, self.p0)
        shock = self.real("Shock", self.p0, zone=ZONE_HAND)
        self.begin()
        self.mana(self.p0, R=1)
        # provider default answers vocab[0] == "PASS" for the cw: site.
        self.ex.begin_turn(self.p0)
        self.ex.combat_step(self.p0)
        asks = self.cw_asks()
        self.assertEqual(len(asks), 1)
        self.assertTrue(asks[0][1].startswith(f"cw:{self.p0}:"))
        self.assertEqual(self.world.zone_of(shock).kind, ZONE_HAND)
        self.assertEqual(self.world.zone_of(brute).kind, ZONE_BATTLEFIELD)
        self.assertEqual(self.world.players[self.p1].life, 17)  # unburned
        self.assertEqual(len(self.window_rows("WINDOW_OPEN")), 1)
        self.assertEqual(len(self.window_rows("WINDOW_PASS")), 1)

    def test_no_combat_instants_is_silent(self):
        alpha = self.synth("Alpha", 2, 2, self.p0)
        beta = self.synth("Beta", 2, 2, self.p1)
        self.begin()
        self.answers[f"block:{beta}"] = str(alpha)
        self.ex.begin_turn(self.p0)
        self.ex.combat_step(self.p0)
        # C15 + no-row law: nothing to offer, nothing asked, nothing journaled.
        self.assertEqual(self.cw_asks(), [])
        self.assertEqual(self.window_rows("WINDOW_OPEN"), [])
        self.assertEqual(self.window_rows("WINDOW_PASS"), [])
        # combat itself is untouched: the mutual 2/2 trade still happens.
        self.assertEqual(self.world.zone_of(alpha).kind, ZONE_GRAVEYARD)
        self.assertEqual(self.world.zone_of(beta).kind, ZONE_GRAVEYARD)

    def test_no_attackers_no_window(self):
        self.synth("Alpha", 2, 2, self.p0)
        self.real("Shock", self.p0, zone=ZONE_HAND)
        self.begin()
        self.mana(self.p0, R=1)
        self.default_answer = "DECLINE"  # the attack ask declines
        self.ex.begin_turn(self.p0)
        self.ex.combat_step(self.p0)
        # the attackers gate: a payable instant alone never opens the window.
        self.assertEqual(self.cw_asks(), [])
        self.assertEqual(self.window_rows("WINDOW_OPEN"), [])

    def test_pump_raises_the_blocker_over_the_threshold(self):
        brute = self.synth("Brute", 3, 3, self.p0)
        guard = self.synth("Guard", 3, 3, self.p1)
        growth = self.real("Titanic Growth", self.p1, zone=ZONE_HAND)
        self.begin()
        self.mana(self.p1, G=2)
        self.answers[f"block:{guard}"] = str(brute)
        self.answers[f"cw:{self.p1}"] = f"{growth}@{guard}"
        self.ex.begin_turn(self.p0)
        self.ex.combat_step(self.p0)
        # 6/6 Guard reads the ledger: it takes 3 of 6 and out-fights 3/3.
        self.assertEqual(self.world.zone_of(guard).kind, ZONE_BATTLEFIELD)
        self.assertEqual(self.world.zone_of(brute).kind, ZONE_GRAVEYARD)
        self.assertEqual(self.world.players[self.p1].life, 20)
        self.assertEqual(self.ex.damage.get(guard, 0), 3)

    def test_negative_power_dealer_deals_no_damage(self):
        # games seeds 10/73 crash witness: Carrion Grub's own BLOCKED
        # trigger records a raw -4/-4 Eot delta, and its low effective
        # power crosses zero BEFORE the damage step. The damage lane's
        # zero guard must read the whole non-positive half-line: a
        # negative-power dealer simply deals nothing (damage is never
        # negative), the game proceeds without a QConst crash.
        attacker = self.synth("Attacker", 2, 2, self.p0)
        grub = self.real("Carrion Grub", self.p1)
        self.begin()
        self.answers[f"block:{grub}"] = str(attacker)
        self.ex.begin_turn(self.p0)
        self.ex.combat_step(self.p0)  # pre-fix: ValueError QConst(-1)
        dealers = {row.subject for row in self.rows("COMBAT_DAMAGE")}
        self.assertNotIn(grub, dealers)  # the -1-power dealer stayed silent
        self.assertEqual(self.world.players[self.p0].life, 20)
        self.assertEqual(self.world.zone_of(attacker).kind, ZONE_BATTLEFIELD)

    def test_vocabulary_is_recomputed_after_the_first_seat_acts(self):
        attacker = self.synth("Attacker", 2, 2, self.p0)
        blocker = self.synth("Blocker", 2, 2, self.p1)
        shock_a = self.real("Shock", self.p0, zone=ZONE_HAND)
        shock_b = self.real("Shock", self.p1, zone=ZONE_HAND)
        self.begin()
        self.mana(self.p0, R=1)
        self.mana(self.p1, R=1)
        self.answers[f"block:{blocker}"] = str(attacker)
        self.answers[f"cw:{self.p0}"] = f"{shock_a}@{blocker}"  # kills it
        self.answers[f"cw:{self.p1}"] = f"{shock_b}@{attacker}"
        self.ex.begin_turn(self.p0)
        self.ex.combat_step(self.p0)
        asks = self.cw_asks()
        self.assertEqual(len(asks), 2)  # one round, player order
        vocab_a, tag_a = asks[0]
        vocab_b, tag_b = asks[1]
        self.assertTrue(tag_a.startswith(f"cw:{self.p0}:"))
        self.assertTrue(tag_b.startswith(f"cw:{self.p1}:"))
        self.assertIn(f"{shock_a}@{blocker}", vocab_a)
        # the post-death state: the dead blocker is GONE from P1's list.
        self.assertNotIn(f"{shock_b}@{blocker}", vocab_b)
        self.assertIn(f"{shock_b}@{attacker}", vocab_b)
        # mutual pre-damage burns: zero combat damage, both life untouched.
        self.assertEqual(self.world.zone_of(attacker).kind, ZONE_GRAVEYARD)
        self.assertEqual(self.world.zone_of(blocker).kind, ZONE_GRAVEYARD)
        self.assertEqual(self.world.players[self.p0].life, 20)
        self.assertEqual(self.world.players[self.p1].life, 20)
        self.assertEqual(len(self.window_rows("WINDOW_OPEN")), 2)
