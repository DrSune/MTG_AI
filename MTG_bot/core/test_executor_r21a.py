"""Round-21a regression tests: the wave-4 prevention-condition, planeswalker
damage, and player-or-PW designation batch.

Each test pins one r21a root cause and the machinery that fixed it:

1. PREVENTION CONDITION SIDES (Ghostly Pilferer): the block consult judges
   ``rec.condition`` over BOTH sides of a declaration pair — the GP shape's
   IS_SOURCE condition names the BLOCKED side (the old subject-only reading
   evaluated it against the BLOCKER, silently disabling the veto), while a
   hypothetical "this creature can't block" activation names the BLOCKER
   side; either way the pair vetoes, and the blocker/blocked slot filters
   still gate which pairs are affected. The attack consult keeps the
   attacker-side-only reading (it has no other side).
2. PLANESWALKER DAMAGE (Chandra's Magmutt / Leafkin Avenger, CR 120.4d):
   card-side damage to an identity with a printed loyalty decrements the
   LOYALTY counter instead of marking damage; an unseeded ledger falls back
   to the PRINTED loyalty (missing key is not zero).
3. ZERO-LOYALTY STATE CHECK (CR 704.5h): a walker at loyalty 0 is buried by
   the settle sweep and the LOYALTY counter KEY is dropped, so battlefield
   re-entry can never ride a stale zero into an instant second death.
4. PLAYER-OR-PW DESIGNATION (selectors.role_handles): the self-resolve
   exemption for PLAYER-zone selectors is narrowed to PURE player
   selectors; the compiled "target player or planeswalker" shape carries
   zones=(BATTLEFIELD,) and a designated walker handle must survive the
   binding-first path instead of being re-pointed at the player.
"""

from __future__ import annotations

import unittest

from MTG_bot.core.ability_tree import (
    ControllerRef,
    DeclareAttackersEvent,
    DeclareBlockersEvent,
    DurationEot,
    FAtom,
    FAtomPred,
    FNot,
    FOr,
    Keyword,
    QConst,
    Selector,
    SelectorMode,
    Verb,
    Zone,
    ZoneKind,
)
from MTG_bot.core.executor import Executor
from MTG_bot.core.identity import CardIdentity
from MTG_bot.core.state import (
    ZONE_BATTLEFIELD,
    ZONE_GRAVEYARD,
    GameWorld,
)
from MTG_bot.core.test_executor_verbs import (
    CREATURE,
    UNIV,
    atom,
    card_id,
    reset_oracle_ids,
    target_sel,
)

PW_SHAPE = FOr(
    (FNot(FAtom(FAtomPred.IS_PERMANENT)), FAtom(FAtomPred.TYPE_EQ, "Planeswalker"))
)


class R21aCase(unittest.TestCase):
    """Shared rig: p0 Alpha (2/2), p1 Beta (1/1), p0 Gamma (3/3)."""

    def setUp(self):
        reset_oracle_ids()
        self.world = GameWorld(num_players=2, start_life=20, master_seed=11)
        self.p0, self.p1 = self.world.player_order[0], self.world.player_order[1]
        self.alpha = self.world.add_card(
            card_id("Alpha", "2", "2"), self.p0, ZONE_BATTLEFIELD
        )
        self.beta = self.world.add_card(
            card_id("Beta", "1", "1"), self.p1, ZONE_BATTLEFIELD
        )
        self.gamma = self.world.add_card(
            card_id("Gamma", "3", "3"), self.p0, ZONE_BATTLEFIELD
        )
        self.ex = Executor(self.world)

    def _walker(self, seat, loyalty="4", name="Walky"):
        ident = CardIdentity(
            oracle_id=card_id(name).oracle_id,
            name=name,
            type_line="Planeswalker",
            loyalty=loyalty,
            cmc=3,
        )
        return self.world.add_card(ident, seat, ZONE_BATTLEFIELD)


class TestPreventionConditionSides(R21aCase):
    def _register(self, **kw):
        return self.ex.replacements.register_prevention(
            step=None,
            duration=DurationEot(),
            targets=(),
            **kw,
        )

    def test_blocked_side_condition_vetoes_ghostly_pilferer_shape(self):
        # GP's runtime shape: the condition's IS_SOURCE names the BLOCKED
        # (protected) side. The old subject-only (blocker) evaluation read
        # this as never-matching and the forced block sailed through.
        self._register(
            source=self.alpha,
            controller=self.p0,
            condition=FAtom(FAtomPred.IS_SOURCE),
            event=DeclareBlockersEvent(filter=UNIV, blocked=FAtom(FAtomPred.IS_SOURCE)),
        )
        # Beta vs Alpha: the pair vetoes (condition matches the blocked side)
        self.assertTrue(
            self.ex.replacements.prevents_block_declaration(self.beta, self.alpha)
        )
        # Beta vs Gamma: no match on either side, the pair is legal
        self.assertFalse(
            self.ex.replacements.prevents_block_declaration(self.beta, self.gamma)
        )

    def test_blocker_side_condition_vetoes_the_blocker_pairs(self):
        # The r21a both-sides reading: a condition naming the BLOCKER (a
        # future "this creature can't block" activation) vetoes too — the
        # old code judged it against the attacker only and never vetoed.
        # Directionality is carried by the event slots: the blocker-side
        # filter (IS_SOURCE over the BLOCKER) keeps the record OFF any pair
        # where the source only shows up as the BLOCKED side.
        self._register(
            source=self.beta,  # beta is the BLOCKER (p1, defending)
            controller=self.p1,
            condition=FAtom(FAtomPred.IS_SOURCE),
            event=DeclareBlockersEvent(filter=FAtom(FAtomPred.IS_SOURCE), blocked=None),
        )
        self.assertTrue(
            self.ex.replacements.prevents_block_declaration(self.beta, self.alpha)
        )
        # Alpha blocking BETA: the blocked side matches the condition, but
        # the blocker-side filter excludes alpha, so this pair is legal
        self.assertFalse(
            self.ex.replacements.prevents_block_declaration(self.alpha, self.beta)
        )

    def test_attack_consult_keeps_condition_on_the_attacker_side(self):
        # The attack branch never both-sides: the condition names the
        # attacker, and a record sourced elsewhere vetoes nothing.
        self._register(
            source=self.gamma,
            controller=self.p0,
            condition=FAtom(FAtomPred.IS_SOURCE),
            event=DeclareAttackersEvent(filter=UNIV),
        )
        self.assertTrue(self.ex.replacements.prevents_attack_declaration(self.gamma))
        self.assertFalse(self.ex.replacements.prevents_attack_declaration(self.alpha))


class TestPlaneswalkerDamage(R21aCase):
    def _hit(self, pw, n):
        self.ex.execute(
            atom(Verb.DEAL_DAMAGE, target=target_sel(UNIV), amount=QConst(n)),
            source=self.alpha,
            controller=self.p0,
            bindings={"target": pw},
        )

    def test_damage_to_walker_decrements_loyalty_not_marks(self):
        pw = self._walker(self.p1, "4")
        self._hit(pw, 1)
        card = self.world.cards[pw]
        self.assertEqual(dict(card.counters), {"LOYALTY": 3})
        self.assertNotIn(pw, self.ex.damage)  # the walker lane never MARKS
        self.assertEqual(self.world.zone_of(pw).kind, ZONE_BATTLEFIELD)

    def test_unseeded_ledger_falls_back_to_printed_loyalty(self):
        # The rig never seeds counters: missing LOYALTY key means PRINTED
        # loyalty, never zero (the 13a printed-value twin).
        pw = self._walker(self.p1, "5")
        self._hit(pw, 2)
        self.assertEqual(dict(self.world.cards[pw].counters), {"LOYALTY": 3})

    def test_zero_loyalty_is_buried_and_the_key_is_dropped(self):
        pw = self._walker(self.p1, "2")
        self._hit(pw, 2)
        # CR 704.5h: the settle-tail state check buries the walker...
        self.assertEqual(self.world.zone_of(pw).kind, ZONE_GRAVEYARD)
        # ...and the LOYALTY key rides out with it, so a battlefield re-entry
        # can never inherit a stale zero (the binding setdefault re-seed).
        self.assertEqual(dict(self.world.cards[pw].counters), {})
        self.assertNotIn(pw, self.ex.damage)

    def test_reentry_with_dropped_key_damages_from_printed(self):
        pw = self._walker(self.p1, "4")
        self._hit(pw, 4)  # dies, key dropped
        self.assertEqual(dict(self.world.cards[pw].counters), {})
        self.ex.execute(
            atom(
                Verb.MOVE_ZONE,
                cards=target_sel(UNIV, Zone(ZoneKind.GRAVEYARD, ControllerRef.ANY)),
                destination=Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),
            ),
            source=self.alpha,
            controller=self.p1,
            bindings={"cards": [pw]},
        )
        # back on the battlefield with an EMPTY counter table: the next hit
        # restarts from the printed loyalty, not from a stale 0.
        self._hit(pw, 1)
        self.assertEqual(dict(self.world.cards[pw].counters), {"LOYALTY": 3})
        self.assertEqual(self.world.zone_of(pw).kind, ZONE_BATTLEFIELD)


class TestPlayerOrPlaneswalkerDesignation(R21aCase):
    def test_bound_walker_survives_the_player_or_pw_selector(self):
        # The compiled "target player or planeswalker" selector shape:
        # Zone(PLAYER) + zones=(BATTLEFIELD,). The old blanket player-side
        # exemption self-resolved it through the PLAYER zone alone and
        # silently re-pointed the damage at the player.
        pw = self._walker(self.p1, "4")
        sel = Selector(
            QConst(1),
            SelectorMode.TARGET,
            PW_SHAPE,
            zones=(Zone(ZoneKind.PLAYER, ControllerRef.ANY), *(Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),)),
        )
        self.ex.execute(
            atom(Verb.DEAL_DAMAGE, target=sel, amount=QConst(1)),
            source=self.alpha,
            controller=self.p0,
            bindings={"target": pw},
        )
        self.assertEqual(dict(self.world.cards[pw].counters), {"LOYALTY": 3})
        self.assertEqual(self.world.players[self.p1].life, 20)  # player untouched

    def test_pure_player_selector_still_self_resolves(self):
        # The exemption stays for PURE TARGET_PLAYER selectors (no zones):
        # a card handle bound under the role is re-resolved through the
        # selector's own zone (the Brash Taunter 16a convention holds).
        sel = Selector(
            QConst(1),
            SelectorMode.TARGET,
            UNIV,
            zones=(Zone(ZoneKind.PLAYER, ControllerRef.YOU),),
        )
        self.ex.execute(
            atom(Verb.DEAL_DAMAGE, target=sel, amount=QConst(1)),
            source=self.alpha,
            controller=self.p0,
            bindings={"target": self.alpha},  # a CARD on a pure player verb
        )
        self.assertEqual(self.world.players[self.p0].life, 19)
        self.assertNotIn(self.alpha, self.ex.damage)  # never marked the card


class TestDurationEotSourceExemption(R21aCase):
    """C5 (Destructive Tampering): a RESOLVED sorcery's DurationEot
    prevention outlives its source (CR 611.2a — by the declare-blockers
    step the spell is long in the graveyard). ``_pair_vetoed`` exempts
    ONLY the DurationEot shape from the ``_source_alive`` battlefield
    gate; static (duration None) and WHILE-gated records keep it."""

    def _tampering_record(self, duration):
        # The promoted pack's world (tools/scenarios/tampering_no_block.json)
        # in hand-registered shape: the spell has ALREADY resolved into the
        # graveyard by combat time (the pack's own expect.zone pins
        # tb:graveyard BEFORE the block ask), and the Choose-branch '1'
        # registered the block-only restriction.
        spell = self.world.add_card(
            card_id("Tampering", type_line="Sorcery"), self.p0, ZONE_GRAVEYARD
        )
        self.assertEqual(self.world.zone_of(spell).kind, ZONE_GRAVEYARD)
        no_fly = FNot(FAtom(pred=FAtomPred.KEYWORD_HAS, keyword=Keyword.FLYING))
        return self.ex.replacements.register_prevention(
            source=spell,  # NOT on the battlefield at block-ask time
            controller=self.p0,
            condition=None,
            event=DeclareBlockersEvent(filter=CREATURE, blocked=no_fly),
            step=None,
            duration=duration,
            targets=(),
        )

    def _flying_attacker(self):
        sky = self.world.add_card(
            CardIdentity(
                oracle_id=card_id("Skywraith").oracle_id,
                name="Skywraith",
                type_line="Creature",
                power="2",
                toughness="2",
                cmc=3,
                keywords=("FLYING",),
            ),
            self.p0,
            ZONE_BATTLEFIELD,
        )
        # the KEYWORD_HAS oracle reads the LAYER registry, whose printed-
        # keyword map was built at Executor() construction: re-seen.
        self.ex.layers.recompute()
        return sky

    def test_graveyard_sourced_eot_record_vetoes_non_flying_block(self):
        # The promoted pack's core claim, consult-level: the spell sits in
        # the graveyard, yet the Eot record still refuses Beta (no flying)
        # the block on Alpha.
        self._tampering_record(DurationEot())
        self.assertTrue(
            self.ex.replacements.prevents_block_declaration(self.beta, self.alpha)
        )

    def test_eot_exemption_keeps_the_event_slot_filters(self):
        # The exemption widens liveness only, never the pair filters: a
        # FLYING attacker fails the blocked slot (FNot(KEYWORD_HAS
        # FLYING)), so the same graveyard-sourced record vetoes nothing.
        sky = self._flying_attacker()
        self._tampering_record(DurationEot())
        self.assertFalse(
            self.ex.replacements.prevents_block_declaration(self.beta, sky)
        )

    def test_same_record_without_eot_duration_keeps_the_liveness_gate(self):
        # duration=None is the static-carrier shape (battlefield lifecycle):
        # the source-in-graveyard record is dead on arrival — the C5
        # exemption must NOT leak beyond DurationEot.
        self._tampering_record(None)
        self.assertFalse(
            self.ex.replacements.prevents_block_declaration(self.beta, self.alpha)
        )

    def test_none_duration_with_alive_source_still_vetoes(self):
        # The gate's positive side: the same static-shape record sourced on
        # the battlefield vetoes exactly as before C5 (Ghostly Pilferer
        # lifecycle unchanged).
        carrier = self.world.add_card(
            card_id("Carrier", type_line="Enchantment"), self.p0, ZONE_BATTLEFIELD
        )
        no_fly = FNot(FAtom(pred=FAtomPred.KEYWORD_HAS, keyword=Keyword.FLYING))
        self.ex.replacements.register_prevention(
            source=carrier,
            controller=self.p0,
            condition=None,
            event=DeclareBlockersEvent(filter=CREATURE, blocked=no_fly),
            step=None,
            duration=None,
            targets=(),
        )
        self.assertTrue(
            self.ex.replacements.prevents_block_declaration(self.beta, self.alpha)
        )
