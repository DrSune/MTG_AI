"""Round-16c pins: blockers, damage assignment, the blocked-side feeds
(doc /11 §16c, BINDING).

Every one of these runs the REAL executor against compiled pool cards:
the per-blocker ask contract (site ``block:<card>:<turn>``, vocabulary =
the attackers that permanent may legally block + NONE, C15 narrowing for
the must-be-blocked mandate and the menace repair), the CR 509.1 pair
legality consumers (tapped, defender, flying/reach, two-sided protection,
static AND runtime PREVENT_EFFECT records, the live draw clock), the
DECLARE_BLOCKERS pair-row feed (DeclareBlockersEvent slots over
blocker/attacker; the anchored BecomesBlockedEvent — Gloom Sower's life
swap through the referent-fold), CR 510 assignment (positional order
asks, trample excess partitions, deathtouch lethal, the Herald's
AS_UNBLOCKED policy ask that reroutes the ASSIGNMENT while the creature
stays blocked), the token-record binder registration (Pursued Whale's
Pirate binds its own "can't block" static) and the combat-scoped DAMAGE
rows (Harbinger's ``combat`` flag consumed).
"""

from __future__ import annotations

import unittest

from MTG_bot.core.ability_tree import (
    ControllerRef,
    DeclareBlockersEvent,
    DurationEot,
    FAtom,
    FAtomPred,
    QConst,
    Verb,
)
from MTG_bot.core.executor.games import identity_of
from MTG_bot.core.executor.legality import activate
from MTG_bot.core.state import ZONE_BATTLEFIELD, ZONE_GRAVEYARD, ZONE_LIBRARY
from MTG_bot.core.test_executor_combat import CombatCase, _supply
from MTG_bot.core.test_executor_verbs import UNIV, atom, card_id


class BlockerCase(CombatCase):
    """CombatCase with the 16c ask-answer contract: answers are keyed by
    SITE PREFIX (handle tags carry a turn suffix), block sites default to
    NONE, order/trample sites to 0, policy sites to AS_BLOCKED."""

    def provider(self, vocab, what):
        self.seen_asks.append((tuple(vocab), what))
        for key, value in self.answers.items():
            if what == key or what.startswith(key + ":"):
                return value if value in vocab else vocab[0]
        if what.startswith("may:"):
            return "skip" if "skip" in vocab else vocab[0]
        if what.startswith("block:"):
            return "NONE" if "NONE" in vocab else vocab[0]
        if what.startswith(("order:", "trample:")):
            return "0"
        if what.startswith("policy:"):
            return "AS_BLOCKED"
        return self.default_answer if self.default_answer in vocab else vocab[0]

    # -- probes ----------------------------------------------------------
    def vocab_for(self, handle) -> tuple[str, ...]:
        tag = f"block:{handle}:"
        seen = [v for v, what in self.seen_asks if what.startswith(tag)]
        assert len(seen) == 1, f"expected one block ask for {handle}, got {seen}"
        return seen[0]

    def blocked_map(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for row in self.rows("DECLARE_BLOCKERS"):
            attacker = row.declare_blockers[0]
            out.setdefault(str(attacker), []).append(str(row.subject))
        return out

    def damage_plan(self, dealer):
        """One dealer's announced assignment from its COMBAT_DAMAGE row."""
        for row in self.rows("COMBAT_DAMAGE"):
            if row.subject == dealer:
                return row.combat_damage[0]
        return None

    def draw_for(self, player, n):
        # the bare test world's libraries are empty (the deck supply is
        # the games harness); deal the cards to draw INTO the library
        for k in range(n):
            self.world.add_card(card_id(f"Lib{k}", None, None), player, ZONE_LIBRARY)
        self.ex.execute(
            atom(Verb.DRAW, controller=ControllerRef.YOU, amount=QConst(n)),
            source=player,
            controller=player,
        )


class TestBlockBasics(BlockerCase):
    def test_block_saves_the_player_and_the_pair_row(self):
        alpha = self.synth("Alpha", 2, 2, self.p0)
        beta = self.synth("Beta", 2, 2, self.p1)
        self.begin()
        self.answers[f"block:{beta}"] = str(alpha)
        self.ex.begin_turn(self.p0)
        self.ex.combat_step(self.p0)
        # the pair row: subject = the BLOCKER, data = (attacker, group)
        rows = self.rows("DECLARE_BLOCKERS")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].subject, beta)
        self.assertEqual(rows[0].declare_blockers[0], alpha)
        # nobody's life moved; both dealers announced 2 at the other
        self.assertEqual(self.world.players[self.p1].life, 20)
        self.assertEqual(self.damage_plan(alpha), ((2, beta),))
        self.assertEqual(self.damage_plan(beta), ((2, alpha),))
        # 2 marked on a 2/2: the settle's SBA buries both (16a ledger)
        self.assertEqual(self.world.zone_of(alpha).kind, ZONE_GRAVEYARD)
        self.assertEqual(self.world.zone_of(beta).kind, ZONE_GRAVEYARD)
        # end-of-combat bookkeeping: the block record closes with the phase
        self.assertEqual(self.ex.blocked_by, {})

    def test_tapped_blockers_are_never_asked(self):
        self.synth("Alpha", 2, 2, self.p0)  # the lone attacker
        beta = self.synth("Beta", 2, 2, self.p1)
        self.begin()
        self.world.cards[beta].tapped = True
        self.ex.begin_turn(self.p0)
        self.ex.combat_step(self.p0)
        # CR 509.1a: a tapped creature cannot block - not even asked (C15)
        self.assertEqual([a for a in self.seen_asks if a[1].startswith("block:")], [])
        self.assertEqual(self.rows("DECLARE_BLOCKERS"), [])
        self.assertEqual(self.world.players[self.p1].life, 18)

    def test_unblocked_attacker_still_announces_to_the_defender(self):
        alpha = self.synth("Alpha", 3, 3, self.p0)
        self.begin()
        self.ex.begin_turn(self.p0)
        self.ex.combat_step(self.p0)
        self.assertEqual(self.damage_plan(alpha), ((3, self.p1),))
        self.assertEqual(self.world.players[self.p1].life, 17)


class TestPairLegality(BlockerCase):
    def test_flying_rejects_a_reachless_blocker(self):
        # Shacklegeist attacks as a plain 2/2 flyer; its own "blocks only
        # flyers" clause is a BLOCKER-side restriction (pinned below).
        flyer = self.real("Shacklegeist", self.p0)
        blocky = self.synth("Blocky", 2, 2, self.p1)
        spider = self.real("Snarespinner", self.p1)
        self.begin()
        self.answers[f"block:{spider}"] = str(flyer)
        self.ex.begin_turn(self.p0)
        self.ex.combat_step(self.p0)
        # a creature legal against NOTHING is never asked at all (C15:
        # no empty offer - the flying pair was the only candidate)
        self.assertEqual(
            [a for a in self.seen_asks if a[1].startswith(f"block:{blocky}")], []
        )
        # the reach carrier may take the flyer (CR 509.1b flying/reach)
        self.assertEqual(self.blocked_map(), {str(flyer): [str(spider)]})
        # the block trigger ran BEFORE damage: Snarespinner's "blocks a
        # creature with flying" +2/+0 is in the announced power (1 -> 3)
        self.assertEqual(self.damage_plan(spider), ((3, flyer),))
        self.assertEqual(self.world.zone_of(flyer).kind, ZONE_GRAVEYARD)  # 3 on a 2/2

    def test_two_sided_protection_rejects_the_matching_blocker(self):
        # Baneslayer Angel's printed quality pair (Demons/Dragons) reads
        # through the KeywordAbility params; a Demon blocker is vetoed.
        attacker = self.world.add_card(
            card_id("Test Demon", "2", "2", type_line="Creature — Demon"),
            self.p0,
            ZONE_BATTLEFIELD,
        )
        baneslayer = self.real("Baneslayer Angel", self.p1)
        vanilla = self.synth("Vanilla", 2, 2, self.p1)
        self.begin()
        self.answers[f"block:{vanilla}"] = str(attacker)
        self.ex.begin_turn(self.p0)
        self.ex.combat_step(self.p0)
        # protection was the ONLY pair for Baneslayer: legal against
        # nothing, the engine honestly does not ask at all (C15)
        self.assertEqual(
            [a for a in self.seen_asks if a[1].startswith(f"block:{baneslayer}")], []
        )
        self.assertEqual(self.blocked_map(), {str(attacker): [str(vanilla)]})
        self.assertEqual(self.world.players[self.p1].life, 20)

    def test_static_prevention_draw_clock_tome_anima(self):
        # Tome Anima (attacking for P0): "can't be blocked as long as
        # you've drawn two or more" - YOU is the record's controller, and
        # the blocked=IS_SOURCE slot names the ANIMA side of each pair.
        grog = self.synth("Grog", 2, 2, self.p0)
        anima = self.real("Tome Anima", self.p0)
        blocky = self.synth("Blocky", 2, 2, self.p1)
        self.begin()
        self.answers[f"block:{blocky}"] = str(grog)
        self.ex.begin_turn(self.p0)
        # CR mid-turn arithmetic: Anima's controller draws two DURING
        # this turn's window - the static gate opens for the whole turn
        self.draw_for(self.p0, 2)
        self.ex.combat_step(self.p0)
        # the block ask offered Blocky exactly Grog (Anima vetoed, C15)
        self.assertEqual(self.vocab_for(blocky), (str(grog), "NONE"))
        self.assertEqual(self.blocked_map(), {str(grog): [str(blocky)]})
        # Anima lands its 3 unblocked
        self.assertEqual(self.world.players[self.p1].life, 17)
        # the turn window is the horizon: after the marker resets, the
        # gate CLOSES and Anima is blockable again
        self.ex.end_turn()
        self.ex.advance_turn()
        helper = self.synth("Block2", 2, 2, self.p1)
        self.ex.begin_turn(self.p0)
        self.answers[f"block:{helper}"] = str(anima)
        self.ex.combat_step(self.p0)
        self.assertIn(str(anima), self.vocab_for(helper))
        self.assertEqual(self.blocked_map().get(str(anima)), [str(helper)])

    def test_runtime_prevention_shape_ghostly_pilferer(self):
        # The runtime carrier (GP's discard activation shape): a live
        # DurationEot DeclareBlockersEvent record with blocked = IS_SOURCE
        # vetoes PAIRS against its source, and only this turn.
        alpha = self.synth("Alpha", 2, 2, self.p0)
        beta = self.synth("Beta", 2, 2, self.p0)
        blocky = self.synth("Blocky", 2, 2, self.p1)
        self.begin()
        self.ex.replacements.register_prevention(
            source=alpha,
            controller=self.p0,
            condition=None,
            event=DeclareBlockersEvent(filter=UNIV, blocked=FAtom(FAtomPred.IS_SOURCE)),
            step=None,
            duration=DurationEot(),
            targets=(),
        )
        self.answers[f"block:{blocky}"] = str(beta)
        self.ex.begin_turn(self.p0)
        self.ex.combat_step(self.p0)
        # Alpha is off the vocabulary; Beta remains; Alpha gets through
        vocab = self.vocab_for(blocky)
        self.assertNotIn(str(alpha), vocab)
        self.assertIn(str(beta), vocab)
        self.assertEqual(self.blocked_map(), {str(beta): [str(blocky)]})
        self.assertEqual(self.world.players[self.p1].life, 18)

    def test_shacklegeist_blocks_only_creatures_with_flying(self):
        # the reverse orientation: Shacklegeist as BLOCKER; the blocked-
        # side slot of the static prevention record excludes ground prey
        alpha = self.synth("Alpha", 2, 2, self.p0)
        # a PRINTED flyer (a synth carries no keywords at all)
        flyer = self.real("Fetid Imp", self.p0)  # 1/2 flying
        shack = self.real("Shacklegeist", self.p1)  # attached by begin()
        self.begin()
        self.ex.begin_turn(self.p0)
        self.answers[f"block:{shack}"] = "NONE"
        self.ex.combat_step(self.p0)
        vocab = self.vocab_for(shack)
        # the flyer is on the list (as a blocker, flying does not restrict
        # the blocker), the ground attacker is NOT
        self.assertIn(str(flyer), vocab)
        self.assertNotIn(str(alpha), vocab)
        self.assertEqual(self.blocked_map(), {})  # answered NONE
        # both attackers walk in: Alpha's 2 + the Imp's 1
        self.assertEqual(self.world.players[self.p1].life, 17)


class TestAssignment(BlockerCase):
    def test_order_ask_positional_choice_decides_survival(self):
        attacker = self.synth("Smash", 3, 3, self.p0)
        small = self.synth("Small", 2, 2, self.p1)
        big = self.synth("Big", 4, 4, self.p1)
        self.begin()
        self.answers[f"block:{small}"] = str(attacker)
        self.answers[f"block:{big}"] = str(attacker)
        # take the Handle-sorted slot 1 (the 4/4) first: all 3 into it
        self.answers[f"order:{attacker}:0"] = "1"
        self.ex.begin_turn(self.p0)
        self.ex.combat_step(self.p0)
        plan = self.damage_plan(attacker)
        self.assertEqual(plan, ((3, big),))  # 2 lethal short of the 4/4
        self.assertEqual(self.world.zone_of(big).kind, ZONE_BATTLEFIELD)
        self.assertEqual(self.ex.damage.get(big, 0), 3)  # scarred, alive
        self.assertEqual(self.ex.damage.get(small, 0), 0)  # never reached

    def test_trample_excess_ask_routes_to_the_player(self):
        dino = self.real("Colossal Dreadmaw", self.p0)  # 6/6 trample
        blocker = self.synth("Small", 2, 2, self.p1)
        self.begin()
        self.answers[f"block:{blocker}"] = str(dino)
        self.answers[f"trample:{dino}:0"] = "1"  # give 1 EXTRA to blocker
        self.ex.begin_turn(self.p0)
        self.ex.combat_step(self.p0)
        plan = self.damage_plan(dino) or ()
        # 2 lethal + 1 extra at the blocker, the remaining 3 to the player
        self.assertEqual(sorted(plan), sorted(((3, blocker), (3, self.p1))))
        self.assertEqual(self.world.players[self.p1].life, 17)
        # the blocker still answers for the attack: 2 at the 6/6
        self.assertEqual(self.damage_plan(blocker), ((2, dino),))

    def test_trample_excess_ask_opens_only_above_total_lethal(self):
        # Dire Fleet Warmonger carries +2/+0 while attacking ALONE (a
        # live static) - 5 total against a 0/3 wall: 3 lethal, the 2
        # excess are ASKED (default answer 0 -> the player takes them)
        dino = self.real("Dire Fleet Warmonger", self.p0)  # 3/3 trample
        wall = self.synth("Wall", 0, 3, self.p1)
        self.begin()
        self.answers[f"block:{wall}"] = str(dino)
        self.ex.begin_turn(self.p0)
        self.ex.combat_step(self.p0)
        self.assertEqual(self.damage_plan(dino), ((3, wall), (2, self.p1)))
        self.assertEqual(self.world.players[self.p1].life, 18)
        self.assertEqual(self.world.zone_of(wall).kind, ZONE_GRAVEYARD)

    def test_deathtouch_grant_buries_the_bigger_blocker(self):
        # Hooded Blightfang's deathtouch is a live while-condition layer
        # (your turn); CR 702.2b makes ONE damage lethal at the consult
        fang = self.real("Hooded Blightfang", self.p0)  # 1/4
        blocker = self.synth("BigBody", 3, 3, self.p1)
        self.begin()
        self.answers[f"block:{blocker}"] = str(fang)
        self.ex.begin_turn(self.p0)
        self.ex.combat_step(self.p0)
        self.assertEqual(self.damage_plan(fang), ((1, blocker),))
        self.assertEqual(self.world.zone_of(blocker).kind, ZONE_GRAVEYARD)
        self.assertEqual(self.world.zone_of(fang).kind, ZONE_BATTLEFIELD)
        self.assertEqual(self.ex.damage.get(fang, 0), 3)  # survived the 3

    def test_herald_policy_ask_routes_the_assignment_and_stays_blocked(self):
        # Garruk, Savage Herald [-7]: granted AS_UNBLOCKED on the creature
        herald = self.real("Garruk, Savage Herald", self.p0)
        alpha = self.synth("Alpha", 2, 2, self.p0)
        blocker = self.synth("Blocky", 3, 3, self.p1)
        self.begin()
        self.world.cards[herald].counters["LOYALTY"] = 7
        activate(self.ex, herald, 2, seat=self.p0)  # the -7 grant
        self.answers[f"block:{blocker}"] = str(alpha)
        self.answers[f"policy:{alpha}"] = "UNBLOCKED"
        self.ex.begin_turn(self.p0)
        self.ex.combat_step(self.p0)
        # rerouted assignment...
        self.assertEqual(self.damage_plan(alpha), ((2, self.p1),))
        self.assertEqual(self.world.players[self.p1].life, 18)
        self.assertEqual(self.ex.damage.get(blocker, 0), 0)
        # ...but the BLOCKED STATUS stands: the blocker still hits it (2
        # on a 2/2 buries Alpha - the CR-true "as though unblocked")
        self.assertEqual(self.damage_plan(blocker), ((3, alpha),))
        self.assertEqual(self.world.zone_of(alpha).kind, ZONE_GRAVEYARD)
        self.assertEqual(self.world.zone_of(blocker).kind, ZONE_BATTLEFIELD)

    def test_herald_policy_as_blocked_keeps_the_normal_order(self):
        herald = self.real("Garruk, Savage Herald", self.p0)
        alpha = self.synth("Alpha", 2, 2, self.p0)
        blocker = self.synth("Blocky", 3, 3, self.p1)
        self.begin()
        self.world.cards[herald].counters["LOYALTY"] = 7
        activate(self.ex, herald, 2, seat=self.p0)
        self.answers[f"block:{blocker}"] = str(alpha)
        self.ex.begin_turn(self.p0)
        self.ex.combat_step(self.p0)
        # default provider answer AS_BLOCKED: the policy asked, the CR
        # order (2 at the blocker) stands
        self.assertEqual(self.damage_plan(alpha), ((2, blocker),))
        self.assertEqual(self.world.players[self.p1].life, 20)

    def test_dispatched_policy_verb_records_the_ledger(self):
        alpha = self.synth("Alpha", 2, 2, self.p0)
        self.begin()
        self.ex.execute(
            atom(Verb.DAMAGE_ASSIGN_POLICY, scope="AS_UNBLOCKED"),
            source=alpha,
            controller=self.p0,
        )
        self.assertEqual(self.ex.damage_policies[alpha], "AS_UNBLOCKED")
        # the closed scope vocabulary validates at CONSTRUCTION (AtomArgs,
        # ability_tree.py) before any handler runs; the handler's own
        # NotImplementedError is the second-line guard
        with self.assertRaises(ValueError):
            atom(Verb.DAMAGE_ASSIGN_POLICY, scope="SOMETHING_ELSE")


class TestMenaceAndMandate(BlockerCase):
    def test_menace_blocks_alone_never(self):
        self.real("Bone Pit Brute", self.p0)  # 4/5 menace
        solo = self.synth("Solo", 2, 2, self.p1)
        self.begin()
        self.ex.begin_turn(self.p0)
        self.ex.combat_step(self.p0)
        # one blocker in front of menace: CR 702.113 - the pair alone is
        # illegal (the inclusion rule needs a second blocker), and the
        # honest vocabulary collapses to NONE (C15 - only the emptiness
        # is legal here)
        self.assertEqual(self.vocab_for(solo), ("NONE",))
        self.assertEqual(self.world.players[self.p1].life, 16)

    def test_menace_repairs_to_two_blockers_and_the_order_decides(self):
        brute = self.real("Bone Pit Brute", self.p0)  # 4/5 menace
        first = self.synth("First", 2, 2, self.p1)
        second = self.synth("Second", 2, 2, self.p1)
        self.begin()
        self.answers[f"block:{first}"] = str(brute)
        # the LAST unasked blocker in front of a menace attacker stuck at
        # one gets no NONE word (C15: the legal space is just the attacker)
        self.ex.begin_turn(self.p0)
        self.ex.combat_step(self.p0)
        vocab = self.vocab_for(second)
        self.assertNotIn("NONE", vocab)
        self.assertEqual(self.blocked_map(), {str(brute): [str(first), str(second)]})
        # 4 damage in Handle order: 2 lethal each - both blockers die, the
        # brute takes 4 and survives on 1
        self.assertEqual(self.damage_plan(brute), ((2, first), (2, second)))
        self.assertEqual(self.world.zone_of(first).kind, ZONE_GRAVEYARD)
        self.assertEqual(self.world.zone_of(second).kind, ZONE_GRAVEYARD)
        self.assertEqual(self.world.zone_of(brute).kind, ZONE_BATTLEFIELD)

    def test_canopy_stalker_must_be_blocked_narrows_the_choice(self):
        # CR 509.1h: "This creature must be blocked if able" - the MANDATE
        # _BLOCK static narrows the single blocker's vocabulary to exactly
        # the stalker, and the other attacker walks in unopposed.
        stalker = self.real("Canopy Stalker", self.p0)  # 4/2
        self.synth("Alpha", 2, 2, self.p0)  # walks in unopposed
        blocker = self.synth("Blocky", 2, 2, self.p1)
        self.begin()
        self.ex.begin_turn(self.p0)
        self.ex.combat_step(self.p0)
        vocab = self.vocab_for(blocker)
        self.assertEqual(vocab, (str(stalker),))
        self.assertEqual(self.blocked_map(), {str(stalker): [str(blocker)]})
        # stalker (4) buries the 2/2, the blocker's 2 bury the stalker;
        # Alpha lands 2 on the player
        self.assertEqual(self.world.players[self.p1].life, 18)
        self.assertEqual(self.world.zone_of(stalker).kind, ZONE_GRAVEYARD)
        self.assertEqual(self.world.zone_of(blocker).kind, ZONE_GRAVEYARD)


class TestFeeds(BlockerCase):
    def test_becomes_blocked_gloom_sower_swaps_life(self):
        # the anchored BecomesBlockedEvent: the BLOCKED side must be the
        # trigger's source; the referent=event controller folds the
        # BLOCKER handle to its controller (LOSE_LIFE / GAIN_LIFE lanes)
        sower = self.real("Gloom Sower", self.p0)  # 8/6
        blocker = self.synth("Blocky", 2, 2, self.p1)
        bystander = self.synth("Bystand", 2, 2, self.p1)
        self.begin()
        self.answers[f"block:{blocker}"] = str(sower)
        # the SECOND blocker also blocks the sower: PER-BLOCKER event
        # granularity - the life swap happens twice
        self.answers[f"block:{bystander}"] = str(sower)
        self.ex.begin_turn(self.p0)
        self.ex.combat_step(self.p0)
        self.assertEqual(self.world.players[self.p1].life, 16)  # -2 twice
        self.assertEqual(self.world.players[self.p0].life, 24)  # +2 twice

    def test_gloom_sower_only_moves_life_when_actually_blocked(self):
        self.real("Gloom Sower", self.p0)
        self.begin()
        self.ex.begin_turn(self.p0)
        self.ex.combat_step(self.p0)
        self.assertEqual(self.world.players[self.p1].life, 12)  # 8 damage
        self.assertEqual(self.world.players[self.p0].life, 20)  # no swap

    def test_damage_rows_carry_the_combat_flag_and_scope_binds(self):
        # the 16c DAMAGE row shape: data (amount, True) under the wave
        # flag, consumed by a DamageDealtEvent node carrying combat=true
        alpha = self.synth("Alpha", 2, 2, self.p0)
        self.begin()
        record = None
        for oid, meta in _supply().metas.items():
            if meta.name == "Garruk's Harbinger":
                record = _supply().pool.results[oid].card
        if record is None:
            self.fail("Harbinger missing from the compiled pool")
        harbinger = self.world.add_card(identity_of(record), self.p0, ZONE_BATTLEFIELD)
        self.ex.attach_card(harbinger, record)
        self.ex.begin_turn(self.p0)
        self.ex.combat_step(self.p0)
        damage_rows = [e for e in self.rows("DAMAGE") if e.subject == alpha]
        self.assertTrue(all(r.is_combat for r in damage_rows))


class TestTokenBinder(BlockerCase):
    def test_whale_etb_pirate_token_binds_its_own_rule_lines(self):
        # the token-record registration (/13 named gap): the Pirate's
        # printed "can't block" PREVENTION must be LIVE (the binder found
        # a record for the token handle when its battlefield row settled)
        whale = self.real("Pursued Whale", self.p0, zone="hand")
        self.begin()
        self.enter_battlefield(whale, self.p0)  # journaled entry: ETB fires
        tokens = [
            h
            for h, c in self.world.cards.items()
            if c.identity.name == "Pirate"
            and self.world.zone_of(h).kind == "battlefield"
        ]
        self.assertEqual(len(tokens), 1)
        token = tokens[0]
        self.assertEqual(self.world.controller_of(token), self.p1)
        self.assertIn(token, self.ex.binder.handle_record)
        # the whale attacks: the pirate is NEVER asked (prevention live,
        # legality answered it through the token's own record)
        self.ex.begin_turn(self.p0)
        self.ex.combat_step(self.p0)
        self.assertEqual(
            [a for a in self.seen_asks if a[1].startswith(f"block:{token}")], []
        )
        self.assertEqual(self.world.players[self.p1].life, 12)  # 8 unblocked
        # the token's OTHER line: "Creatures you control attack each
        # combat if able" - the mandate layer anchored to the TOKEN's
        # controller; P1's next combat must attack with everything
        vanilla = self.synth("Vanilla", 2, 2, self.p1)
        self.ex.end_turn()
        self.ex.advance_turn()
        self.ex.begin_turn(self.p1)
        self.ex.combat_step(self.p1)
        for creature in (token, vanilla):
            sites = [
                v
                for v, what in self.seen_asks
                if what.startswith(f"attack:{creature}:")
            ]
            self.assertEqual(sites, [("ATTACK",)], f"{creature} was not forced")
        self.assertEqual(self.world.players[self.p0].life, 20 - 3)


if __name__ == "__main__":
    unittest.main()
