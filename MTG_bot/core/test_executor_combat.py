"""Round-16b pins: the COMBAT skeleton (doc /11 §16b, BINDING).

The declare-ask contract, the whole-set legality check, the summoning-
sickness / defender / haste / vigilance consumers, the first/double-
strike damage split through the 16a marked-damage funnel, the
DeclareAttackersEvent / CombatDamageEvent feeds (per-attacker rows,
CR 603.2 group dedup), the MANDATE_ATTACK narrowing (C15) and the
end-of-combat bookkeeping — every one exercised through the REAL
executor against compiled pool cards, not fixtures.

v1 limits pinned AS DESIGNED (16c scope, doc /11): no blockers (all
attackers unblocked, damage to the defending player), the compiler-side
enters_attacking drop (Falconer's Bird enters plain — the IR spec flags
are None; the executor honors the flag when present, pinned by the
Basri-Ket-spec rule, not simulated).
"""

from __future__ import annotations

import unittest

from MTG_bot.core.ability_tree import (
    ControllerRef,
    DurationEot,
    DurationUntilNextTurn,
    Keyword,
    KeywordAbility,
    QConst,
    Verb,
    Zone,
    ZoneKind,
)
from MTG_bot.core.executor import Executor
from MTG_bot.core.executor.games import get_supply, identity_of
from MTG_bot.core.executor.legality import mandated_attackers
from MTG_bot.core.state import (
    ZONE_BATTLEFIELD,
    ZONE_HAND,
    ZONE_LIBRARY,
    GameWorld,
)
from MTG_bot.core.test_executor_verbs import (
    HAND_YOU,
    UNIV,
    atom,
    card_id,
    target_sel,
)

POOL = None  # compiled once per process by setUpClass below


def _supply():
    global POOL
    if POOL is None:
        POOL = get_supply("all")
    return POOL


class CombatCase(unittest.TestCase):
    """p0/p1 seats; ``real`` places a compiled pool card (identity bridge,
    attach_pool registers its triggers); ``synth`` a keyword-less
    CardIdentity creature. The ask provider records every (vocab, site)
    the engine actually asks with and answers per ``self.answers``."""

    def setUp(self) -> None:
        self.supply = _supply()
        self.world = GameWorld(num_players=2, start_life=20, master_seed=7)
        self.p0, self.p1 = self.world.player_order
        self.ex = Executor(self.world)  # attach/provider arm in begin()
        self.seen_asks: list[tuple[tuple[str, ...], str]] = []
        self.answers: dict[str, str] = {}  # site-tag -> forced answer
        self.default_answer = "ATTACK"

    # -- rig -------------------------------------------------------------
    def real(self, name: str, seat, zone=ZONE_BATTLEFIELD):
        for oid, meta in self.supply.metas.items():
            if meta.name == name:
                record = self.supply.pool.results[oid].card
                return self.world.add_card(identity_of(record), seat, zone)
        raise KeyError(name)

    def synth(self, name, power, toughness, seat, zone=ZONE_BATTLEFIELD):
        return self.world.add_card(
            card_id(name, str(power), str(toughness)), seat, zone
        )

    def begin(self) -> None:
        """Register every battlefield card of the pool (real cards only
        carry triggers; synth handles find no record and bind nothing —
        keyword_of reads False, the honest no-abilities permanent), and
        arm the ask provider."""
        self.ex.attach_pool(self.supply.pool)
        self.ex.decisions.provider = self.provider

    def provider(self, vocab, what):
        self.seen_asks.append((tuple(vocab), what))
        # Site tags are PREFIX-matched (run_scenarios/blockers convention):
        # T5-F1 may-offers carry a per-offer digest suffix on the site key,
        # so the pack-side answer is keyed by its handle prefix.
        answer = self.default_answer
        for key, value in self.answers.items():
            if what == key or what.startswith(key + ":"):
                answer = value
                break
        if answer in vocab:
            return answer
        # An answer the site does not offer: may-offers default to the
        # conservative skip, everything else takes the first legal word.
        return "skip" if "skip" in vocab else vocab[0]

    def attack_sites(self):
        """The handles the engine asked about, in ask order."""
        return [
            what.split(":", 2)[1] + ":" + what.split(":", 2)[2].rsplit(":", 1)[0]
            for _vocab, what in self.seen_asks
            if what.startswith("attack:")
        ]

    def asks_for(self, handle) -> list[tuple[tuple[str, ...], str]]:
        tag = f"attack:{handle}:"
        return [a for a in self.seen_asks if a[1].startswith(tag)]

    def forced_attack(self, handle) -> str:
        """T5-F1 (§10): a mandated attacker's one-word ATTACK surface is
        auto-picked and journalled by the phantom gate — no ask reaches a
        provider (the old narrowed-vocab ASK pins live here now)."""
        tag = f"attack:{handle}:"
        self.assertEqual(
            [a for a in self.seen_asks if a[1].startswith(tag)],
            [],
            f"{handle} was ASKED, though its surface was forced",
        )
        hits = [a for what, a in self.ex.decisions.journal if what.startswith(tag)]
        self.assertEqual(
            hits, ["ATTACK"], f"expected one journalled forced ATTACK, got {hits}"
        )
        return hits[0]

    def enter_battlefield(self, handle, seat, tapped=False) -> None:
        """The scenario move a real game does with a resolution: a
        JOURNALLED MOVE_ZONE — the sickness logic must see the entry row."""
        self.ex.execute(
            atom(
                Verb.MOVE_ZONE,
                cards=target_sel(UNIV, HAND_YOU),
                destination=Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU),
                tapped_on_enter=tapped,
            ),
            source=handle,
            controller=seat,
            bindings={"cards": handle},
        )

    def rows(self, kind: str):
        return [e for e in self.ex.journal.events if e.kind == kind]

    def hand(self, seat) -> int:
        return len(self.world.players[seat].zone(ZONE_HAND).entries)


class TestSkeleton(CombatCase):
    def test_combat_marker_clock_and_second_main(self):
        self.synth("Alpha", 2, 2, self.p0)
        self.begin()
        self.ex.begin_turn(self.p0)
        fired = self.ex.combat_step(self.p0)
        phases = [e.phase for e in self.rows("TURN_PHASE")]
        self.assertEqual([p[0] for p in phases], ["UPKEEP", "FIRST_MAIN", "COMBAT"])
        self.assertEqual(self.ex.phase, "SECOND_MAIN")
        self.assertEqual(self.ex.attackers, [])  # end-of-combat cleared
        self.assertEqual(self.ex.attacked, {})
        self.assertIsNone(self.ex.defending_player)
        self.assertEqual(fired, 0)  # no triggers in this fixture
        self.assertEqual(self.world.players[self.p1].life, 18)  # 2 damage
        # the full turn still closes normally after combat
        self.ex.end_turn()
        self.assertEqual([e.phase[0] for e in self.rows("TURN_PHASE")][-1], "END_TURN")

    def test_guards_on_closed_turn_and_inactive_seat(self):
        self.synth("Alpha", 2, 2, self.p0)
        self.begin()
        self.ex.begin_turn(self.p0)
        with self.assertRaises(ValueError):
            self.ex.combat_step(self.p1)  # not the active player
        self.ex.combat_step(self.p0)
        self.ex.end_turn()
        with self.assertRaises(ValueError):
            self.ex.combat_step(self.p0)  # turn already closed


class TestDeclareAsks(CombatCase):
    def test_binary_ask_vocab_site_and_commit(self):
        alpha = self.synth("Alpha", 2, 2, self.p0)
        beta = self.synth("Beta", 1, 1, self.p0)
        self.begin()
        self.ex.begin_turn(self.p0)
        self.answers[f"attack:{beta}:{self.world.turn}"] = "DECLINE"
        self.ex.combat_step(self.p0)
        self.assertEqual(
            self.asks_for(alpha), [(("ATTACK", "DECLINE"), f"attack:{alpha}:1")]
        )
        self.assertEqual(
            self.asks_for(beta), [(("ATTACK", "DECLINE"), f"attack:{beta}:1")]
        )
        self.assertTrue(self.world.cards[alpha].tapped)  # declared: taps
        self.assertFalse(self.world.cards[beta].tapped)  # declined: stays
        self.assertEqual(self.world.players[self.p1].life, 18)
        declared = [e.subject for e in self.rows("DECLARE_ATTACKERS")]
        self.assertEqual(declared, [alpha])  # one row, the attacker only
        # the group id is shared per declaration:
        self.assertEqual(
            {e.declare_group for e in self.rows("DECLARE_ATTACKERS")}, {1 + 1}
        )  # op_seq: begin_turn's draw atom was op 1, declare is op 2

    def test_decline_is_respected_and_no_ask_without_creatures(self):
        alpha = self.synth("Alpha", 2, 2, self.p0)
        self.begin()
        self.ex.begin_turn(self.p0)
        self.default_answer = "DECLINE"
        self.ex.combat_step(self.p0)
        self.assertEqual(self.world.players[self.p1].life, 20)
        self.assertFalse(self.world.cards[alpha].tapped)
        self.assertEqual(self.rows("DECLARE_ATTACKERS"), [])
        # p1 (no creatures) never gets an attack step of interest
        self.seen_asks.clear()
        self.ex.end_turn()
        self.ex.advance_turn()
        self.ex.combat_step(self.p1)
        self.assertEqual(self.seen_asks, [])  # honest emptiness: no ask

    def test_vigilance_attacker_declares_untapped(self):
        watchdog = self.real("Alpine Watchdog", self.p0)
        self.begin()
        self.ex.begin_turn(self.p0)
        self.ex.combat_step(self.p0)
        self.assertFalse(self.world.cards[watchdog].tapped)
        # first strike, no FS partner: single wave, 2 damage once
        self.assertEqual(self.world.players[self.p1].life, 18)
        self.assertEqual(len(self.rows("COMBAT_DAMAGE")), 1)

    def test_defender_is_never_asked(self):
        wall = self.real("Wall of Runes", self.p0)
        alpha = self.synth("Alpha", 2, 2, self.p0)
        self.begin()
        self.ex.begin_turn(self.p0)
        self.ex.combat_step(self.p0)
        self.assertEqual(self.asks_for(wall), [])  # filtered before asking
        self.assertEqual(len(self.asks_for(alpha)), 1)
        self.assertEqual(self.world.players[self.p1].life, 18)  # only alpha

    def test_sick_creature_not_asked_clean_next_turn(self):
        zhalafir = self.real("Historian of Zhalfir", self.p0, ZONE_HAND)
        self.begin()
        self.ex.begin_turn(self.p0)
        self.enter_battlefield(zhalafir, self.p0)  # enters THIS turn
        self.ex.combat_step(self.p0)
        self.assertEqual(self.asks_for(zhalafir), [])  # CR 302.6
        self.assertEqual(self.world.players[self.p1].life, 20)
        # own NEXT turn: the same permanent, still never left, is ready
        self.ex.end_turn()
        self.ex.advance_turn()
        self.ex.end_turn()
        self.ex.advance_turn()
        self.assertEqual(self.world.turn, 3)
        self.ex.combat_step(self.p0)
        self.assertEqual(len(self.asks_for(zhalafir)), 1)
        self.assertTrue(self.world.cards[zhalafir].tapped)

    def test_haste_ignores_summoning_sickness(self):
        hound = self.real("Bolt Hound", self.p0, ZONE_HAND)
        self.begin()
        self.ex.begin_turn(self.p0)
        self.enter_battlefield(hound, self.p0)
        self.ex.combat_step(self.p0)
        self.assertEqual(len(self.asks_for(hound)), 1)  # haste: asked
        self.assertTrue(self.world.cards[hound].tapped)
        # its own attack trigger buffs "other creatures" — alone here,
        # so the observable is exactly the hound's 2 damage
        self.assertEqual(self.world.players[self.p1].life, 18)


class TestDamageSteps(CombatCase):
    def grant(self, source, target_handle, keyword) -> None:
        self.ex.execute(
            atom(
                Verb.GRANT_ABILITY,
                target=target_sel(),
                ability=KeywordAbility(keyword=keyword),
            ),
            source=source,
            controller=self.p0,
            bindings={"target": target_handle},
        )

    def test_double_strike_deals_both_steps_others_once(self):
        striker = self.real("Siege Striker", self.p0)  # 1/1 double strike
        grog = self.synth("Grog", 2, 2, self.p0)
        self.begin()
        self.ex.begin_turn(self.p0)
        self.answers[f"may:{striker}"] = "skip"  # its own tap-any trigger
        self.ex.combat_step(self.p0)
        # step 1: striker 1 (its trigger resolved +0/+0, tap declined);
        # step 2: striker 1 + grog 2 -> 4 total
        self.assertEqual(self.world.players[self.p1].life, 16)
        dealers = [e.subject for e in self.rows("COMBAT_DAMAGE")]
        self.assertEqual(dealers.count(striker), 2)
        self.assertEqual(dealers.count(grog), 1)

    def test_first_striker_deals_once_before_the_normal_step(self):
        watchdog = self.real("Alpine Watchdog", self.p0)  # 2/2 first strike
        grog = self.synth("Grog", 2, 2, self.p0)
        self.begin()
        self.ex.begin_turn(self.p0)
        self.ex.combat_step(self.p0)
        # watchdog ONLY in the first wave (2), grog only in the normal (2)
        self.assertEqual(self.world.players[self.p1].life, 16)
        dealers = [e.subject for e in self.rows("COMBAT_DAMAGE")]
        self.assertEqual(dealers.count(watchdog), 1)
        self.assertEqual(dealers.count(grog), 1)
        # the split order: watchdog's row precedes grog's
        self.assertLess(dealers.index(watchdog), dealers.index(grog))

    def test_zero_power_deals_no_damage_at_all(self):
        keeper = self.synth("Keeper", 0, 2, self.p0)  # CR 120.7
        self.begin()
        self.ex.begin_turn(self.p0)
        self.ex.combat_step(self.p0)
        self.assertEqual(len(self.asks_for(keeper)), 1)  # legal attacker
        self.assertEqual(len(self.rows("DECLARE_ATTACKERS")), 1)
        self.assertEqual(self.rows("COMBAT_DAMAGE"), [])  # no damage row
        self.assertEqual(self.world.players[self.p1].life, 20)  # no life

    def test_buffed_attack_trigger_moves_the_damage_number(self):
        # Bolt Hound's "other creatures you control get +1/+0" lands in
        # the post-declare settle BEFORE the damage step: Grog attacks at
        # 3, not 2. End-to-end proof the trigger sits under the damage.
        self.real("Bolt Hound", self.p0)
        self.synth("Grog", 2, 2, self.p0)
        self.begin()
        self.ex.begin_turn(self.p0)
        self.ex.combat_step(self.p0)
        self.assertEqual(self.world.players[self.p1].life, 20 - (2 + 3))
        rows = self.rows("COMBAT_DAMAGE")
        # 16c note: the COMBAT_DAMAGE row now carries the dealer's whole
        # assignment ((amount, recipient) pairs); these dealers are un-
        # blocked so each row is the single-pair case.
        amounts = [a for r in rows for a, _recip in r.combat_damage[0]]
        self.assertEqual(amounts, sorted(amounts))
        self.assertEqual(sorted(amounts), [2, 3])


class TestTriggerFeeds(CombatCase):
    def test_group_dedup_one_fire_per_ability_per_declaration(self):
        # Tide Skimmer: "Whenever you attack with two or more creatures
        # with flying" — grant Grog flying, attack with both; the two
        # declare rows BOTH match the filter, the group dedup collapses
        # them to ONE trigger instance -> exactly one card drawn.
        skimmer = self.real("Tide Skimmer", self.p0)
        grog = self.synth("Grog", 2, 2, self.p0)
        self.world.add_card(card_id("Lib1"), self.p0, ZONE_LIBRARY)
        self.begin()
        self.ex.begin_turn(self.p0)  # the skeleton draw consumes Lib1
        self.world.add_card(card_id("Lib2"), self.p0, ZONE_LIBRARY)
        self.ex.execute(
            atom(
                Verb.GRANT_ABILITY,
                target=target_sel(),
                ability=KeywordAbility(keyword=Keyword.FLYING),
            ),
            source=skimmer,
            controller=self.p0,
            bindings={"target": grog},
        )
        before = self.hand(self.p0)
        self.ex.combat_step(self.p0)
        self.assertEqual(len(self.rows("DECLARE_ATTACKERS")), 2)
        self.assertEqual(self.hand(self.p0), before + 1)  # ONCE, not twice

    def test_per_source_triggers_fire_once_each_same_group(self):
        # Two Falconer Adepts: same ability node CLASS, different sources
        # -> different dedup keys -> each attack trigger fires once.
        f1 = self.real("Falconer Adept", self.p0)
        f2 = self.real("Falconer Adept", self.p0)
        self.begin()
        self.ex.begin_turn(self.p0)
        self.ex.combat_step(self.p0)
        birds = [
            h for h in self.world.cards if self.world.cards[h].identity.name == "Bird"
        ]
        self.assertEqual(len(birds), 2)
        # Compiler-fidelity face (pinned AS IS, report item): the compiled
        # Bird spec drops Falconer's "that's tapped and attacking" (both
        # enters_* flags are None) — the birds enter plain and deal NO
        # phantom combat damage this combat.
        self.assertEqual(self.world.players[self.p1].life, 20 - (2 + 2))
        self.assertEqual(
            sum(1 for e in self.rows("DECLARE_ATTACKERS") if e.subject in birds),
            0,
        )
        del f1, f2

    def test_mangara_condition_counts_the_attack_record(self):
        # Opponent (p1) controls Mangara: "whenever an opponent attacks
        # with creatures, if two or more ... attacking you" -> ONE draw.
        self.real("Mangara, the Diplomat", self.p1)
        a = self.synth("Alpha", 2, 2, self.p0)
        self.synth("Beta", 1, 1, self.p0)
        for i in range(3):
            self.world.add_card(card_id(f"ML{i}"), self.p1, ZONE_LIBRARY)
        self.begin()
        self.ex.begin_turn(self.p0)
        before = self.hand(self.p1)
        self.ex.combat_step(self.p0)
        self.assertEqual(self.hand(self.p1), before + 1)  # once, not per-row
        # one attacker only -> condition false -> no draw
        self.ex.end_turn()
        self.ex.advance_turn()
        self.ex.end_turn()
        self.ex.advance_turn()
        self.default_answer = "DECLINE"
        self.answers[f"attack:{a}:3"] = "ATTACK"
        before = self.hand(self.p1)
        self.ex.combat_step(self.p0)
        self.assertEqual(self.hand(self.p1), before)


class TestMandates(CombatCase):
    def test_dispatched_ledger_narrows_the_ask_vocab(self):
        alpha = self.synth("Alpha", 2, 2, self.p0)
        beta = self.synth("Beta", 3, 3, self.p0)
        self.begin()
        self.ex.begin_turn(self.p0)
        self.ex.mandates.add(alpha)  # the dispatched shape
        self.default_answer = "DECLINE"
        self.ex.combat_step(self.p0)
        self.forced_attack(alpha)  # mandated: consumed, never asked (T5-F1)
        self.assertEqual(self.asks_for(beta)[0][0], ("ATTACK", "DECLINE"))
        self.assertTrue(self.world.cards[alpha].tapped)  # attacked anyway
        self.assertFalse(self.world.cards[beta].tapped)  # declined
        self.assertEqual(self.world.players[self.p1].life, 18)

    def _dispatch_mandate(self, card, source, controller, duration=None):
        roles: dict = {"cards": target_sel()}
        if duration is not None:
            roles["duration"] = duration
        self.ex.execute(
            atom(Verb.MANDATE_ATTACK, **roles),
            source=source,
            controller=controller,
            bindings={"cards": card},
        )

    def _next_own_turn(self):
        self.ex.end_turn()
        self.ex.advance_turn()
        self.ex.end_turn()
        self.ex.advance_turn()
        self.seen_asks.clear()

    def test_dispatched_mandate_this_turn_ends_at_cleanup(self):
        # B-59 (2026-10-29): "target creature attacks this turn if able" is
        # a RESOLVED effect with a duration (CR 611.2a). It forces this
        # turn's declaration and ends in the cleanup step (CR 514.2); the
        # dispatch ledger used to keep it until the creature left play.
        alpha = self.synth("Alpha", 2, 2, self.p0)
        self.begin()
        self.ex.begin_turn(self.p0)
        self._dispatch_mandate(alpha, alpha, self.p0, DurationEot())
        self.default_answer = "DECLINE"
        self.ex.combat_step(self.p0)
        self.forced_attack(alpha)
        self.assertEqual(self.world.players[self.p1].life, 18)
        self._next_own_turn()
        self.ex.combat_step(self.p0)
        self.assertEqual(self.asks_for(alpha)[0][0], ("ATTACK", "DECLINE"))
        self.assertEqual(self.world.players[self.p1].life, 18)  # declined

    def test_dispatched_mandate_until_your_next_turn(self):
        # Goad's duration (CR 701.38a, 611.2b): p0 makes p1's creature
        # attack "until your next turn" — forced on p1's turn, over when
        # p0's next turn begins, so p1's following turn is free again.
        beta = self.synth("Beta", 2, 2, self.p1)
        self.begin()
        self.ex.begin_turn(self.p0)
        self._dispatch_mandate(beta, beta, self.p0, DurationUntilNextTurn())
        self.default_answer = "DECLINE"
        self.ex.end_turn()
        self.ex.advance_turn()  # p1's turn: forced
        self.ex.combat_step(self.p1)
        self.forced_attack(beta)
        self.assertEqual(self.world.players[self.p0].life, 18)
        self._next_own_turn()  # through p0's turn into p1's next one
        self.ex.combat_step(self.p1)
        self.assertEqual(self.asks_for(beta)[0][0], ("ATTACK", "DECLINE"))
        self.assertEqual(self.world.players[self.p0].life, 18)

    def test_dispatched_mandate_without_duration_persists(self):
        # The durationless dispatch keeps its old reading: it lasts until
        # the creature leaves the battlefield.
        alpha = self.synth("Alpha", 2, 2, self.p0)
        self.begin()
        self.ex.begin_turn(self.p0)
        self._dispatch_mandate(alpha, alpha, self.p0)
        self.default_answer = "DECLINE"
        self.ex.combat_step(self.p0)
        self._next_own_turn()
        self.ex.combat_step(self.p0)
        self.assertEqual(self.asks_for(alpha), [])  # still forced, never asked
        self.assertEqual(self.world.players[self.p1].life, 16)

    def test_timed_mandate_outlives_its_source_not_its_creature(self):
        # A resolved effect lasts its duration even after its source leaves
        # the battlefield (CR 611.2a). A creature that leaves and comes
        # back is a new object (CR 400.7): the mandate no longer binds it.
        alpha = self.synth("Alpha", 2, 2, self.p0)
        beta = self.synth("Beta", 2, 2, self.p0)
        source = self.synth("Source", 1, 1, self.p0)
        self.begin()
        self.ex.begin_turn(self.p0)
        for card in (alpha, beta):
            self._dispatch_mandate(card, source, self.p0, DurationEot())
        self.assertEqual(mandated_attackers(self.ex, self.p0), {alpha, beta})
        self.ex.execute(
            atom(Verb.DESTROY, target=target_sel()),
            source=alpha,
            controller=self.p0,
            bindings={"target": source},
        )
        self.ex.execute(
            atom(
                Verb.MOVE_ZONE,
                cards=target_sel(),
                destination=Zone(ZoneKind.EXILE, ControllerRef.OWNER),
            ),
            source=alpha,
            controller=self.p0,
            bindings={"cards": beta},
        )
        self.ex.execute(
            atom(
                Verb.MOVE_ZONE,
                cards=target_sel(UNIV, Zone(ZoneKind.EXILE, ControllerRef.ANY)),
                destination=Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU),
            ),
            source=alpha,
            controller=self.p0,
            bindings={"cards": beta},
        )
        self.assertEqual(self.world.zone_of(source).kind, "graveyard")
        self.assertEqual(self.world.zone_of(beta).kind, ZONE_BATTLEFIELD)
        self.assertEqual(mandated_attackers(self.ex, self.p0), {alpha})

    def test_furor_static_splits_layer_and_mandates_the_host(self):
        furor = self.real("Furor of the Bitten", self.p0)
        host = self.synth("Host", 3, 3, self.p0)
        self.synth("Other", 3, 3, self.p0)
        self.begin()
        self.ex.attachments[furor] = host  # the aura-host edge (13c table)
        self.ex.begin_turn(self.p0)
        self.default_answer = "DECLINE"
        self.ex.combat_step(self.p0)
        # the mandate half: ATTACK is the only word — T5-F1 consumes the
        # forced surface silently (journal evidence), and the host attacks.
        self.forced_attack(host)
        self.assertTrue(self.world.cards[host].tapped)
        # the PT half: +2/+2 materialized -> 5 damage, not 3
        self.assertEqual(self.world.players[self.p1].life, 15)
        # Furor leaves -> BOTH halves die with it (layer liveness)
        self.ex.end_turn()
        self.ex.advance_turn()
        self.ex.end_turn()
        self.ex.advance_turn()
        self.ex.execute(
            atom(Verb.DESTROY, target=target_sel()),
            source=host,
            controller=self.p0,
            bindings={"target": furor},
        )
        self.seen_asks.clear()
        self.ex.combat_step(self.p0)
        self.assertEqual(self.asks_for(host)[0][0], ("ATTACK", "DECLINE"))
        self.assertEqual(self.world.players[self.p1].life, 15)  # declined

    def test_pursued_whale_etb_runs_clean_token_static_gap_pinned(self):
        # The 16a crash class was this trigger; 16b it runs CLEAN. The
        # real compiled shape (verified, doc-claim corrected): the ETB is
        # EachPlayer -> CREATE_TOKEN only; the "can't block / attack if
        # able" rules ride the PIRATE'S TokenSpec.abilities (the token's
        # own statics), and TOKEN handles never get binder records (the
        # pre-existing _lifecycle gap, doc B-class) -> the hoisted rule
        # does NOT mandate anyone yet. 16c scope: token-record
        # registration, then this mandate + the DeclareBlockersEvent
        # half of the same token light up together.
        whale = self.real("Pursued Whale", self.p0, ZONE_HAND)
        alpha = self.synth("Alpha", 2, 2, self.p0)
        self.begin()
        self.ex.begin_turn(self.p0)
        self.enter_battlefield(whale, self.p0)  # no raise: the 16b proof
        pirates = [
            h for h in self.world.cards if self.world.cards[h].identity.name == "Pirate"
        ]
        self.assertEqual(len(pirates), 1)  # EachPlayer: p1 got theirs
        self.assertEqual(self.world.controller_of(pirates[0]), self.p1)
        self.assertEqual(self.ex.mandates, set())  # gap pinned, not hidden
        self.ex.combat_step(self.p0)
        self.assertEqual(self.asks_for(alpha)[0][0], ("ATTACK", "DECLINE"))
        self.assertEqual(self.world.players[self.p1].life, 18)  # only alpha


class TestEndOfCombat(CombatCase):
    def test_attackers_cleared_marks_survive_to_cleanup(self):
        alpha = self.synth("Alpha", 4, 4, self.p0)
        self.begin()
        self.ex.begin_turn(self.p0)
        # mark Alpha mid-combat-phase through the public funnel: an
        # attacker that DIES to a declare-time state is a 16c shape;
        # here we pin the bookkeeping instead: attackers empty after the
        # phase, damage marks NOT cleared until the cleanup step.
        self.ex.execute(
            atom(Verb.DEAL_DAMAGE, target=target_sel(), amount=QConst(3)),
            source=alpha,
            controller=self.p1,
            bindings={"target": alpha},
        )
        self.assertEqual(self.ex.damage[alpha], 3)  # survives at 3/4
        self.ex.combat_step(self.p0)
        self.assertEqual(self.ex.attackers, [])
        self.assertEqual(self.ex.damage[alpha], 3)  # marks persist (514.2)
        self.ex.end_turn()
        self.assertEqual(self.ex.damage, {})  # cleanup swept them

    def test_fingerprint_folds_the_combat_record(self):
        alpha = self.synth("Alpha", 2, 2, self.p0)
        self.begin()
        self.ex.begin_turn(self.p0)
        base = self.ex.state_fingerprint()
        self.ex.mandates.add(alpha)  # replayed state -> fingerprint moves
        self.assertNotEqual(self.ex.state_fingerprint(), base)
