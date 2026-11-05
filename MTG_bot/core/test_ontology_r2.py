"""R2 F4 damage-fold battery (KNOWLEDGE/2026-10-20/140-r2-binding-spec, BINDING).

Pins the CDE -> DDE fold of the three combat-damage-event cards
(Jeskai Elder, Feline Sovereign [M21]; Nimble Trapfinder [ZNR]):

* fold SHAPE pins — each card's compiled damage-event node is exactly
  ``DamageDealtEvent{amount:QUnbounded, filter:FAnd(()) [universal
  recipient marker, executor _is_universal binding.py:177], source:<per-card
  dealer filter>, combat:True}`` (the F4 shell; the dealer filter moves
  VERBATIM from the old CDE filter, byte-identical per
  tools/audit/atom_sortdelta_r2.py);
* convergence — post-fold Jeskai Elder event bytes == Garruk's Harbinger's
  event bytes VERBATIM (independent compiles; the §9 merge proof);
* D9 fire-parity — the folded encoding fires EXACTLY where the CDE lane
  fired: (a) combat damage fires, (b) non-combat damage does not,
  (c) Feline: non-Cat combat damage does not;
* SPLIT over-fire (D13, ACCEPTED divergence, spec §6 BREAK-1): a split
  assignment journals one DAMAGE row per (amount, recipient), so a
  multi-blocker split 1+2 fires the folded trigger TWICE where the CDE
  fired once (one COMBAT_DAMAGE row per dealer). CR 603.2 says one "deals
  combat damage" event per dealer -> this is a known DDE-lane over-fire
  that ships TODAY on the ten existing DDE{combat:true} cards. ORCHESTRATOR
  RULING (a): ACCEPT — the pin asserts the OVER-FIRE COUNT (2), it is not
  a fix; the recipient-SET journal-row redesign is engine-lane ticket
  ZND-8;
* population zero — no compiled ``CombatDamageEvent`` node survives in
  either pool (the dead-vocabulary deletion census assert).

Red-first law: the shape/convergence/census/split legs are RED pre-fold and
GREEN post-fold; the fire-parity legs pin behavioral equivalence and hold
across the fold by construction.

B-57 (2026-10-29) ended the fold's one lossy drop: the recipient is no
longer the universal ``FAnd(())`` marker but "a player" (``FNot(
IS_PERMANENT)``; Harbinger: "a player or planeswalker"), because under the
marker a blocked creature fired off its blocker (stronger than printed).
So the shape pins name the new recipient, the convergence proof compares
the shell without the recipient, the three cards' split legs (damage to
two creature blockers) now fire ZERO times, and the D13 lane over-fire is
pinned on a recipient-universal node instead. ``TestRecipientFidelity``
judges the compiled recipients over every kind of damage recipient.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

from MTG_bot.core.ability_tree import (
    ControllerRef,
    DamageDealtEvent,
    DelayedTrigger,
    FAnd,
    FAtom,
    FAtomPred,
    FNot,
    FOr,
    QConst,
    QUnbounded,
    Seq,
    TriggeredAbility,
    Verb,
    canonical_json,
)
from MTG_bot.core.compiler.coverage import _compile_pool_tolerant, build_full_registry
from MTG_bot.core.compiler.ingest import ingest_pool
from MTG_bot.core.executor.events import KIND_DAMAGE, GameEvent
from MTG_bot.core.state import ZONE_BATTLEFIELD, ZONE_GRAVEYARD
from MTG_bot.core.test_executor_binding import gain, record_of
from MTG_bot.core.test_executor_blockers import BlockerCase
from MTG_bot.core.test_executor_combat import _supply
from MTG_bot.core.test_executor_verbs import atom, card_id, target_sel

QCONST1 = QConst(1)

REPO = Path(__file__).resolve().parents[2]

# Type names, not class imports: the battery must survive the deletion of
# the CombatDamageEvent class itself (dead-vocabulary round).
DAMAGE_EVENT_NAMES = frozenset({"CombatDamageEvent", "DamageDealtEvent"})

_ZNR: dict | None = None


def _znr_results() -> dict:
    global _ZNR
    if _ZNR is None:
        pool = ingest_pool(REPO / "MTG_bot" / "data" / "ZNR.json")
        _ZNR, _ = _compile_pool_tolerant(pool, build_full_registry())
    return _ZNR


def _m21_record(name: str):
    supply = _supply()
    for oid, meta in supply.metas.items():
        if meta.name == name:
            return supply.pool.results[oid].card
    raise KeyError(name)


def _znr_record(name: str):
    for oid, r in sorted(_znr_results().items()):
        if r.card.name == name:
            return r.card
    raise KeyError(name)


def _damage_events(root) -> list:
    """Every damage-event IR node reachable from ``root`` (walks dataclass
    fields and containers; keyed by type NAME so it works both pre- and
    post-deletion of the CDE class)."""

    out: list = []

    def walk(x) -> None:
        if isinstance(x, (list, tuple)):
            for y in x:
                walk(y)
            return
        if isinstance(x, dict):
            for v in x.values():
                walk(v)
            return
        if dataclasses.is_dataclass(x) and not isinstance(x, type):
            if type(x).__name__ in DAMAGE_EVENT_NAMES:
                out.append(x)
            for f in dataclasses.fields(x):
                walk(getattr(x, f.name))

    walk(root)
    return out


# --- the fold-law source filters (spec /140 §2(1)) -----------------------
IS_SOURCE = FAtom(pred=FAtomPred.IS_SOURCE)
UNIV_FAND = FAnd(())
# B-57: the recipient filters. "A player" = not a permanent (CR 120.1: only
# players, creatures, planeswalkers and battles can be dealt damage).
TO_A_PLAYER = FNot(FAtom(pred=FAtomPred.IS_PERMANENT))
TO_A_PLAYER_OR_PW = FOr(
    (TO_A_PLAYER, FAtom(pred=FAtomPred.TYPE_EQ, string_value="Planeswalker"))
)
# Feline's dealer filter: the printed cats FAnd moves VERBATIM into
# DDE.source (sortdelta content law); host shape = the Subira precedent
# FAnd[TYPE_EQ Creature, ..., CONTROLLER_IS YOU] over the source slot.
FELINE_CATS = FAnd(
    children=(
        FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
        FAtom(pred=FAtomPred.SUBTYPE_EQ, string_value="Cat"),
        FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
    )
)


class R2FoldCase(BlockerCase):
    """CombatCase rig + a node-attach helper: pull the card's compiled
    damage-event node out of its record, park it on a synthetic dealer with
    a GAIN_LIFE(1) effect, and count fires through p0's life."""

    def arm(self, dealer, node, effect=None) -> None:
        ability = TriggeredAbility(
            node if effect is None else node.event,
            None,
            gain(1) if effect is None else effect,
        )
        rec = record_of(
            [ability],
            name="R2Rig",
            oid=self.world.cards[dealer].identity.oracle_id,
        )
        self.ex.attach_card(dealer, rec)

    def assert_folded(self, node, source_filter, card_name: str) -> None:
        self.assertEqual(
            type(node).__name__,
            "DamageDealtEvent",
            f"{card_name}: damage node not folded to DamageDealtEvent "
            f"(still {type(node).__name__})",
        )
        self.assertIsInstance(node.amount, QUnbounded)
        # re-pinned 2026-10-29: B-57 fix changes the recipient from the
        # universal FAnd(()) marker to "a player" (all three cards say so).
        self.assertEqual(node.filter, TO_A_PLAYER)
        self.assertIs(node.combat, True)
        self.assertEqual(node.source, source_filter)

    def folded_event(self, record, source_filter, card_name: str):
        node = self.event_of(record, card_name)
        self.assert_folded(node, source_filter, card_name)
        return node

    def event_of(self, record, card_name: str):
        """The card's single damage-event node, UNFOLDED-tolerant: the
        fire-parity legs run it as-is on both sides of the fold, so the
        CDE path's behavior is recorded pre-change and the DDE path's
        post-fold by the SAME assertions."""
        events = _damage_events(record)
        self.assertEqual(len(events), 1, f"{card_name}: damage-event count")
        return events[0]

    # -- scenario drivers -------------------------------------------------
    def attack_unblocked(self, dealer) -> None:
        self.begin()
        self.ex.begin_turn(self.p0)
        self.ex.combat_step(self.p0)

    def deal_noncombat(self, dealer, victim) -> None:
        self.begin()
        self.ex.begin_turn(self.p0)
        self.ex.execute(
            atom(Verb.DEAL_DAMAGE, target=target_sel(), amount=QCONST1),
            source=dealer,
            controller=self.p0,
            bindings={"target": victim},
        )

    def split_attack(self, dealer, b1, b2) -> None:
        self.answers[f"block:{b1}"] = str(dealer)
        self.answers[f"block:{b2}"] = str(dealer)
        self.begin()
        self.ex.begin_turn(self.p0)
        self.ex.combat_step(self.p0)

    def damage_rows_for(self, dealer):
        return [e for e in self.rows("DAMAGE") if e.cause == dealer]

    def life_gain(self) -> int:
        return self.world.players[self.p0].life - 20


class TestFoldShape(R2FoldCase):
    """The F4 shell: compiled bytes are the sortdelta-predicted DDE."""

    def test_jeskai_elder_compiles_folded_dde(self):
        rec = _m21_record("Jeskai Elder")
        self.folded_event(rec, IS_SOURCE, "Jeskai Elder")

    def test_feline_sovereign_compiles_folded_dde(self):
        rec = _m21_record("Feline Sovereign")
        self.folded_event(rec, FELINE_CATS, "Feline Sovereign")

    def test_nimble_trapfinder_compiles_folded_dde(self):
        # ZNR has no golden store: this compile-side pin + the guards and
        # fuzz cover the third card (spec §6 evidence caveat).
        rec = _znr_record("Nimble Trapfinder")
        self.folded_event(rec, IS_SOURCE, "Nimble Trapfinder")

    def test_cde_population_zero_both_pools(self):
        """Dead-vocabulary census: no compiled CombatDamageEvent node
        survives anywhere in either pool."""
        supply = _supply()
        m21 = [
            oid
            for oid, r in supply.pool.results.items()
            if any(
                type(n).__name__ == "CombatDamageEvent" for n in _damage_events(r.card)
            )
        ]
        znr = [
            oid
            for oid, r in sorted(_znr_results().items())
            if any(
                type(n).__name__ == "CombatDamageEvent" for n in _damage_events(r.card)
            )
        ]
        self.assertEqual((m21, znr), ([], []))


class TestConvergence(R2FoldCase):
    def test_post_fold_jeskai_bytes_equal_harbinger(self):
        """§9 merge proof: the folded wording-variant compiles byte-
        identical to the DDE it merges into (independent compiles)."""
        jes = self.folded_event(_m21_record("Jeskai Elder"), IS_SOURCE, "Jeskai Elder")
        harb_events = _damage_events(_m21_record("Garruk's Harbinger"))
        self.assertEqual(len(harb_events), 1)
        # re-pinned 2026-10-29: B-57 fix changes the recipients, which the
        # two cards print differently ("a player" vs "a player or
        # planeswalker"), so the bytes now differ there and ONLY there: the
        # shell (amount, source, combat) is still byte-identical.
        self.assertEqual(jes.filter, TO_A_PLAYER)
        self.assertEqual(harb_events[0].filter, TO_A_PLAYER_OR_PW)
        self.assertEqual(
            canonical_json(dataclasses.replace(jes, filter=UNIV_FAND)),
            canonical_json(dataclasses.replace(harb_events[0], filter=UNIV_FAND)),
        )


class TestFireParity(R2FoldCase):
    """D9 precondition: the CHOSEN encoding fires exactly where the CDE
    lane fired — (a) combat fires, (b) non-combat silent, (c) Feline
    non-Cat silent."""

    def test_jeskai_node_fires_on_combat_damage(self):
        node = self.event_of(_m21_record("Jeskai Elder"), "Jeskai Elder")
        dealer = self.synth("Dealer", 3, 3, self.p0)
        self.arm(dealer, node)
        self.attack_unblocked(dealer)
        self.assertEqual(self.world.players[self.p1].life, 17)  # 3 dealt
        self.assertEqual(self.life_gain(), 1)  # exactly one fire

    def test_jeskai_node_silent_on_noncombat_damage(self):
        node = self.event_of(_m21_record("Jeskai Elder"), "Jeskai Elder")
        dealer = self.synth("Dealer", 3, 3, self.p0)
        victim = self.synth("Victim", 0, 5, self.p1)
        self.arm(dealer, node)
        self.deal_noncombat(dealer, victim)
        rows = self.damage_rows_for(dealer)
        self.assertEqual(len(rows), 1)  # the non-combat row IS journaled
        self.assertFalse(rows[0].is_combat)
        self.assertEqual(self.life_gain(), 0)  # but it must NOT fire

    def test_nimble_node_fires_on_combat_damage(self):
        node = self.event_of(_znr_record("Nimble Trapfinder"), "Nimble Trapfinder")
        dealer = self.synth("Dealer", 3, 3, self.p0)
        self.arm(dealer, node)
        self.attack_unblocked(dealer)
        self.assertEqual(self.life_gain(), 1)

    def test_nimble_node_silent_on_noncombat_damage(self):
        node = self.event_of(_znr_record("Nimble Trapfinder"), "Nimble Trapfinder")
        dealer = self.synth("Dealer", 3, 3, self.p0)
        victim = self.synth("Victim", 0, 5, self.p1)
        self.arm(dealer, node)
        self.deal_noncombat(dealer, victim)
        self.assertEqual(len(self.damage_rows_for(dealer)), 1)
        self.assertEqual(self.life_gain(), 0)

    def test_feline_node_fires_on_cat_combat_damage(self):
        node = self.event_of(_m21_record("Feline Sovereign"), "Feline Sovereign")
        dealer = self.world.add_card(
            card_id("Kit", "3", "3", type_line="Creature — Cat"),
            self.p0,
            ZONE_BATTLEFIELD,
        )
        self.arm(dealer, node)
        self.attack_unblocked(dealer)
        self.assertEqual(self.life_gain(), 1)

    def test_feline_node_silent_on_noncat_combat_damage(self):
        node = self.event_of(_m21_record("Feline Sovereign"), "Feline Sovereign")
        dealer = self.synth("NotACat", 3, 3, self.p0)  # Creature, no Cat
        self.arm(dealer, node)
        self.attack_unblocked(dealer)
        self.assertEqual(self.world.players[self.p1].life, 17)  # dealt
        self.assertEqual(self.life_gain(), 0)  # dealer filter rejected

    def test_feline_real_card_end_to_end(self):
        """Compiled record -> attach_pool -> binder -> DESTROY ask: the
        real card fires once on combat damage and its effect lands.

        RED pre-fold BY LANE MECHANICS: the CDE lane fired on the
        COMBAT_DAMAGE row (subject = the DEALER), so the DESTROY target's
        CONTROLLER_IS who=event-reference resolved to the dealer handle —
        no permanent is controlled BY A CREATURE and the effect could
        never find a candidate. The folded DDE lane fires on the DAMAGE
        row (subject = the damaged recipient), so "that player" finally
        binds the rules-faithful damaged player (CR 603.2 referent, the
        anaphora round-4 row #9 always meant)."""
        self.real("Feline Sovereign", self.p0)  # the trigger-carrier
        trophy = self.world.add_card(
            card_id("Trophy", None, None, type_line="Artifact"),
            self.p1,
            ZONE_BATTLEFIELD,
        )
        self.begin()
        self.ex.begin_turn(self.p0)
        self.ex.combat_step(self.p0)
        targeting = [e for e in self.rows("TARGETING") if e.subject == trophy]
        self.assertEqual(len(targeting), 1)  # exactly one fire

    def life_gain(self) -> int:
        return self.world.players[self.p0].life - 20


class TestSplitOverFire(R2FoldCase):
    """D13 ACCEPTED over-fire pin (spec §6 BREAK-1, orchestrator ruling
    (a)). CR 603.2: one "deals combat damage" event per dealer however the
    assignment splits — the CDE lane journaled exactly that (ONE
    COMBAT_DAMAGE row per dealer, which KEEPS emitting per BREAK-2). The
    DDE lane matches the per-(amount, recipient) DAMAGE rows instead, so a
    1+2 split into two blockers fires TWICE. That deficiency is DDE-LANE-
    WIDE and ships TODAY on the ten existing DDE{combat:true} cards
    (Harbinger over-fires on splits now); the fold extends it 10 -> 13.
    This test PINS the accepted count 2 — it is NOT a fix; the correct
    recipient-SET journal-row design is engine-lane ticket ZND-8.

    re-pinned 2026-10-29: B-57 fix changes the three cards' recipient to "a
    player", and a split between two blockers deals no damage to a player,
    so their legs now fire ZERO times (the old count 2 was the B-57 bug on
    top of D13). The D13 lane over-fire itself is unchanged and is pinned on
    a recipient-universal node ("whenever this creature deals combat
    damage", no recipient), where it still fires twice."""

    def split_fires(self, node, cat_dealer: bool) -> tuple:
        dealer = self.world.add_card(
            card_id(
                "Splitdealer",
                "3",
                "3",
                type_line="Creature — Cat" if cat_dealer else "Creature",
            ),
            self.p0,
            ZONE_BATTLEFIELD,
        )
        b1 = self.synth("Tiny", 0, 1, self.p1)  # takes 1
        b2 = self.synth("Brute", 0, 2, self.p1)  # takes 2
        self.arm(dealer, node)
        self.split_attack(dealer, b1, b2)
        plan = self.damage_plan(dealer)
        self.assertIsNotNone(plan)
        self.assertEqual(
            sorted(amount for amount, _ in plan), [1, 2]
        )  # the announced 1+2 split
        return plan

    def test_split_fires_twice_on_a_recipient_universal_node(self):
        # D13 ACCEPTED: 2 fires for one CR-603.2 event (over-fire, pinned).
        node = DamageDealtEvent(
            amount=QUnbounded(), filter=UNIV_FAND, source=IS_SOURCE, combat=True
        )
        self.split_fires(node, cat_dealer=False)
        self.assertEqual(self.life_gain(), 2)

    def test_split_into_two_blockers_fires_zero_jeskai(self):
        # re-pinned 2026-10-29: B-57 fix changes 2 -> 0 (no player was dealt
        # damage; the old 2 fired off the two blockers).
        node = self.event_of(_m21_record("Jeskai Elder"), "Jeskai Elder")
        self.split_fires(node, cat_dealer=False)
        self.assertEqual(self.life_gain(), 0)

    def test_split_into_two_blockers_fires_zero_nimble(self):
        # re-pinned 2026-10-29: B-57 fix changes 2 -> 0 (see jeskai).
        node = self.event_of(_znr_record("Nimble Trapfinder"), "Nimble Trapfinder")
        self.split_fires(node, cat_dealer=False)
        self.assertEqual(self.life_gain(), 0)

    def test_split_into_two_blockers_fires_zero_feline(self):
        # Feline = max exposure (wide cats + double-block lines, spec §6).
        # re-pinned 2026-10-29: B-57 fix changes 2 -> 0 (see jeskai).
        node = self.event_of(_m21_record("Feline Sovereign"), "Feline Sovereign")
        self.split_fires(node, cat_dealer=True)
        self.assertEqual(self.life_gain(), 0)


class TestRecipientFidelity(R2FoldCase):
    """B-57: the compiled recipients, judged by the binder's own damage
    matcher over every kind of combat-damage recipient: a player, a live
    creature, a creature the damage already killed (IS_PERMANENT is the
    type-line test, so it still answers "not a player"), and a planeswalker
    (only Harbinger's "player or planeswalker" admits it). The engine's
    attack ask names no planeswalker, so this leg feeds the matcher a DAMAGE
    row directly instead of running combat."""

    def matches(self, node, subject) -> bool:
        dealer = self.synth("Dealer", 3, 3, self.p0)
        event = GameEvent(
            clock=0,
            kind=KIND_DAMAGE,
            subject=subject,
            cause=dealer,
            cause_verb="COMBAT_DAMAGE",
            data=(3, True),
        )
        return self.ex.binder._match_damage(node, event, dealer, self.p0)

    def recipients(self) -> dict:
        dead = self.synth("Dead Blocker", 0, 1, self.p1)
        self.world.move_to_zone(dead, self.p1, ZONE_GRAVEYARD)
        walker = self.world.add_card(
            card_id("Walker", None, None, type_line="Legendary Planeswalker — Test"),
            self.p1,
            ZONE_BATTLEFIELD,
        )
        return {
            "player": self.p1,
            "creature": self.synth("Blocker", 0, 4, self.p1),
            "dead creature": dead,
            "planeswalker": walker,
        }

    def verdicts(self, node) -> dict:
        return {k: self.matches(node, h) for k, h in self.recipients().items()}

    def test_compiled_recipients(self):
        for name in ("Jeskai Elder", "Feline Sovereign"):
            self.assertEqual(self.event_of(_m21_record(name), name).filter, TO_A_PLAYER)
        self.assertEqual(
            self.event_of(_znr_record("Nimble Trapfinder"), "Nimble Trapfinder").filter,
            TO_A_PLAYER,
        )
        self.assertEqual(
            self.event_of(_m21_record("Garruk's Harbinger"), "Garruk's Harbinger").filter,
            TO_A_PLAYER_OR_PW,
        )
        (subira,) = [
            n
            for n in _damage_events(_m21_record("Subira, Tulzidi Caravanner"))
            if isinstance(n, DamageDealtEvent)
        ]
        self.assertEqual(subira.filter, TO_A_PLAYER)
        self.assertTrue(
            any(
                isinstance(ab.effect, DelayedTrigger) and ab.effect.event == subira
                for ab in _m21_record("Subira, Tulzidi Caravanner").abilities
            )
        )

    def test_to_a_player_matches_only_the_player(self):
        node = self.event_of(_m21_record("Jeskai Elder"), "Jeskai Elder")
        self.assertEqual(
            self.verdicts(node),
            {"player": True, "creature": False, "dead creature": False, "planeswalker": False},
        )

    def test_to_a_player_or_planeswalker_admits_the_planeswalker(self):
        node = self.event_of(_m21_record("Garruk's Harbinger"), "Garruk's Harbinger")
        self.assertEqual(
            self.verdicts(node),
            {"player": True, "creature": False, "dead creature": False, "planeswalker": True},
        )


class TestDesignationValidation(R2FoldCase):
    """BREAK-3 (R2 diff-gate, probe4 Variant A port): the 16a DAMAGE
    dealer pre-bind may only stand as a TARGET slot's FROZEN DESIGNATION
    when it PASSES that slot's filter. Pre-fix, resolve_selector took the
    bound handle with ZERO validation, so a non-event filter (here
    CONTROLLER_IS OPPONENT) misfired: no ask, no TARGETING journal row,
    and the dealer destroyed ITSELF while the trophy lived. The fix
    (binding.py ``_prebind_legal_for_targets``) validates the designation
    through the SAME ``query.legal_targets`` population the ask lane uses
    and lifts on failure — CR 603.1 then designates properly."""

    def test_non_event_filter_target_asks_not_the_dealer(self):
        """Ported probe4 Variant A: damage trigger whose DESTROY targets
        an OPPONENT's artifact. Correct behavior: the trophy dies and the
        dealer lives (single legal filler -> auto-designated by §1.4, the
        TARGETING row journalled either way)."""
        destroy = atom(
            Verb.DESTROY,
            target=target_sel(
                FAnd(
                    (
                        FAtom(pred=FAtomPred.TYPE_EQ, string_value="Artifact"),
                        FAtom(
                            pred=FAtomPred.CONTROLLER_IS,
                            who=ControllerRef.OPPONENT,
                        ),
                    )
                )
            ),
        )
        event = DamageDealtEvent(
            amount=QUnbounded(),
            filter=UNIV_FAND,
            source=IS_SOURCE,
            combat=True,
        )
        node = TriggeredAbility(event, None, Seq(steps=(gain(1), destroy)))
        dealer = self.synth("Break3Dealer", "1", "5", self.p0)
        self.arm(dealer, node, node.effect)
        trophy = self.world.add_card(
            card_id("Trophy", None, None, type_line="Artifact"),
            self.p1,
            ZONE_BATTLEFIELD,
        )
        self.begin()
        self.ex.begin_turn(self.p0)
        self.ex.combat_step(self.p0)
        # Precondition: the trigger fired (GAIN_LIFE ran).
        self.assertEqual(self.world.players[self.p0].life, 21)
        # CORRECT outcome: the trophy died, the dealer lived. Pre-fix the
        # dealer destroyed itself and the trophy lived (red recorded in
        # /tmp/r2_break3_red.log).
        self.assertEqual(
            self.world.zone_of(trophy).kind,
            "graveyard",
            "BREAK-3 regression: the opponent's artifact was NOT destroyed"
            " — the unvalidated dealer pre-bind swallowed the TARGET slot",
        )
        self.assertEqual(
            self.world.zone_of(dealer).kind,
            "battlefield",
            "BREAK-3 regression: the DEALER self-destroyed — the frozen "
            "designation bypassed the selector's filter",
        )
        targeting = [e for e in self.rows("TARGETING") if e.subject == trophy]
        self.assertEqual(len(targeting), 1)  # the designation IS an event

    def test_target_player_reader_keeps_the_16a_prebind(self):
        """Variant B (pinned PRESERVATION, Brash Taunter's lane): a node
        that READS TARGET_PLAYER keeps the dealer pre-bind exactly as 16a
        bound it — no ask lane, the echo folds dealer -> controller (p0
        here)."""
        echo = atom(
            Verb.DEAL_DAMAGE,
            target=target_sel(
                FAnd(
                    (
                        FAtom(
                            pred=FAtomPred.CONTROLLER_IS,
                            who=ControllerRef.TARGET_PLAYER,
                        ),
                    )
                )
            ),
            amount=QCONST1,
        )
        event = DamageDealtEvent(
            amount=QUnbounded(),
            filter=UNIV_FAND,
            source=IS_SOURCE,
            combat=True,
        )
        node = TriggeredAbility(event, None, Seq(steps=(gain(1), echo)))
        dealer = self.synth("EchoDealer", "1", "5", self.p1)
        self.arm(dealer, node, node.effect)
        self.begin()
        self.ex.begin_turn(self.p0)
        self.ex.combat_step(self.p0)
        self.assertEqual(self.world.players[self.p0].life, 20)
        self.assertEqual(
            [e for e in self.rows("TARGETING")], []
        )  # no ask lane opened
