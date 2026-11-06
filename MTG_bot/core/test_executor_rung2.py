"""The combat-instant window in combat_step.

Coverage contract:
  * after blockers are declared and BEFORE the damage step, each seat that
    holds a payable, designable, combat-relevant instant (DEAL_DAMAGE /
    MODIFY_PT / SET_PT in the tree) is ASKED once, in player order;
  * a seat with nothing to offer is never asked and gets no row,
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

from MTG_bot.core.state import ZONE_BATTLEFIELD, ZONE_GRAVEYARD, ZONE_HAND
from MTG_bot.core.test_executor_blockers import BlockerCase

_BASIC = {"W": "Plains", "U": "Island", "B": "Swamp", "R": "Mountain", "G": "Forest"}


class Rung2Case(BlockerCase):
    """BlockerCase + the cw: ask probes and a mana helper.

    Mana empties as each step and phase ends (CR 500.5), so mana put in the
    pool before the turn is gone by the combat window. :meth:`mana` gives the
    seat untapped basic lands instead, which the window taps while paying
    (CR 601.2g, 605.3a)."""

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

    def test_the_window_taps_only_the_lands_the_spell_needs(self):
        # The defender taps one of its three Mountains for the
        # Shock (CR 605.3a), never all of them; the mana is spent, nothing floats.
        brute = self.synth("Brute", 2, 2, self.p0)
        guard = self.synth("Guard", 3, 3, self.p1)
        shock = self.real("Shock", self.p1, zone=ZONE_HAND)
        self.begin()
        self.mana(self.p1, R=3)
        self.answers[f"block:{guard}"] = str(brute)
        self.answers[f"cw:{self.p1}"] = f"{shock}@{brute}"
        self.ex.begin_turn(self.p0)
        self.ex.combat_step(self.p0)
        self.assertEqual(self.world.zone_of(brute).kind, ZONE_GRAVEYARD)
        mountains = [
            h
            for h, c in self.world.cards.items()
            if c.identity.name == "Mountain" and self.world.controller_of(h) == self.p1
        ]
        self.assertEqual(sum(self.world.cards[h].tapped for h in mountains), 1)
        self.assertEqual(self.world.players[self.p1].mana_pool, {})

    def test_a_taxed_target_is_priced_with_the_lands_the_window_taps(self):
        # CR 601.2f-h: Pursued Whale makes the defender's spells that target it cost {3} more.
        # The window prices each target against the lands it can tap, not the pool alone, which
        # is empty in combat.
        whale = self.real("Pursued Whale", self.p0)
        shock = self.real("Shock", self.p1, zone=ZONE_HAND)
        self.begin()
        self.mana(self.p1, R=1)
        self.ex.begin_turn(self.p0)
        self.ex.combat_step(self.p0)
        vocab = self.cw_asks()[0][0]
        self.assertIn(f"{shock}@{self.p0}", vocab)
        self.assertNotIn(f"{shock}@{whale}", vocab)  # {R} + {3}: one Mountain cannot pay

    def test_a_taxed_target_the_lands_pay_is_offered_and_cast(self):
        whale = self.real("Pursued Whale", self.p0)
        shock = self.real("Shock", self.p1, zone=ZONE_HAND)
        self.begin()
        self.mana(self.p1, R=4)
        self.answers[f"cw:{self.p1}"] = f"{shock}@{whale}"
        self.ex.begin_turn(self.p0)
        self.ex.combat_step(self.p0)
        self.assertIn(f"{shock}@{whale}", self.cw_asks()[0][0])
        self.assertEqual(self.world.zone_of(shock).kind, ZONE_GRAVEYARD)  # cast, all four tapped
        mountains = [h for h, c in self.world.cards.items() if c.identity.name == "Mountain"]
        self.assertTrue(all(self.world.cards[h].tapped for h in mountains))

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
        # Nothing to offer, nothing asked, nothing journaled.
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
