"""Ontology round R3 — silent-CHOOSE ask-lift battery (spec /141 §6 law).

The 14 LIFT-NOW nodes (reports/r3_blindness.json L-B rows surviving the
/141 §6 three-rule gate) stop collapsing their real choice into the
Handle-sorted ``ordered[:k]`` stand-in and go through the 14b decision
channel — the same lane r22a opened for sacrifice costs:

* cost lanes: ``legality.build_payment_plan`` records the FULL candidate
  pool per CostDiscard/CostTap segment (``discard_options`` /
  ``tap_options``, mirroring ``sacrifice_options``) and ``pay_costs``
  re-opens the choice with seat-in ask keys
  ``discard:<seat>:<source>:<digest>`` / ``tap:<seat>:<source>:<digest>``
  when a segment really offers a choice (len(pool) > need);
* effect lane: the finite-CHOOSE fold in
  ``selectors.resolve_selector`` asks over the Handle-sorted menu when
  the EFFECT-role lanes resolve it (ask-gated; the CAST-lane ``ok``
  clamp, quantity/count and query callers stay silent BY CONSTRUCTION).

Anti-lift pins (GREEN both sides, the guard law): QUnbounded CHOOSE
stays silent (scope fold), ONE_OF over QUnbounded RAISES
(NotImplementedError — the lane refuses to guess), forced segments
(len(pool) == need) auto-fill without asking, IS_SOURCE self-costs stay
silent, hand-built plans pay the frozen witness path, and the merged
multi-seat / opponent-chooser classes (Bad Deal, Waker, Mind Rot,
Goremand, Run Afoul → ZND-7(a)/ZND-9) never ask.

RED-FIRST: every test whose name says ASKS FAILS before the wiring
lands (silence is the pre-R3 behaviour); the pre-change log lives at
/tmp/opencode/r3_red_prechange.log — expect exactly that RED set to flip.
"""

from __future__ import annotations

import dataclasses
import json
import unittest
from pathlib import Path

from MTG_bot.core.ability_tree import (
    ControllerRef,
    CostDiscard,
    CostTap,
    FAnd,
    QConst,
    QUnbounded,
    Selector,
    SelectorMode,
    Verb,
    Zone,
    ZoneKind,
)
from MTG_bot.core.compiler.coverage import _compile_pool_tolerant, build_full_registry
from MTG_bot.core.compiler.ingest import ingest_pool
from MTG_bot.core.executor import selectors
from MTG_bot.core.executor import Executor
from MTG_bot.core.executor.legality import (
    PaymentPlan,
    build_payment_plan,
    ctx_for,
    pay_costs,
)
from MTG_bot.core.executor.selectors import resolve_selector
from MTG_bot.core.state import (
    ZONE_BATTLEFIELD,
    ZONE_GRAVEYARD,
    ZONE_HAND,
    ZONE_LIBRARY,
    GameWorld,
)
from MTG_bot.core.test_executor_binding import (
    BF_ANY,
    CREATURE,
    IS_SOURCE,
    UNIV,
    atom,
    card_id,
    reset_oracle_ids,
)
from MTG_bot.core.test_executor_legality import cost

REPO = Path(__file__).resolve().parents[2]
LEDGER = REPO / "reports" / "r3_blindness.json"

# The /141 §6 rule-derived LIFT-NOW law (14 cards / 14 nodes). Zones and
# counts are re-verified against the committed ledger AND the live
# compiled IR below; this table carries the NAMES.
LIFT_CARDS = {
    ("M21", "Alpine Houndmaster"),
    ("M21", "Cultivate"),
    ("M21", "Kinetic Augur"),
    ("M21", "Rewind"),
    ("M21", "Ugin, the Spirit Dragon"),
    ("M21", "Demonic Embrace"),
    ("M21", "Ghostly Pilferer"),
    ("M21", "Niambi, Esteemed Speaker"),
    ("M21", "Sanctum of Shattered Heights"),
    ("M21", "Seasoned Hallowblade"),
    ("M21", "Sparkhunter Masticore"),
    ("M21", "Thrill of Possibility"),
    ("M21", "Shacklegeist"),
    ("ZNR", "Tormenting Voice"),
}

HAND_YOU = (Zone(ZoneKind.HAND, ControllerRef.YOU),)

_POOLS: dict[str, dict] = {}


def _pool(set_name: str) -> dict:
    if set_name not in _POOLS:
        pool = ingest_pool(REPO / "MTG_bot" / "data" / f"{set_name}.json")
        _POOLS[set_name] = _compile_pool_tolerant(pool, build_full_registry())[0]
    return _POOLS[set_name]


def _record(set_name: str, card_name: str):
    for oid, r in sorted(_pool(set_name).items()):
        if r.card.name == card_name:
            return r.card
    raise KeyError((set_name, card_name))


def _choose_selectors(root):
    """(holder_class_name, verb-name-or-None, zones-spec, count-value) for
    every CHOOSE-mode Selector reachable from ``root``."""
    out: list = []

    def walk(x, holder):
        if isinstance(x, (list, tuple)):
            for y in x:
                walk(y, holder)
            return
        if isinstance(x, dict):
            for v in x.values():
                walk(v, holder)
            return
        if not (dataclasses.is_dataclass(x) and not isinstance(x, type)):
            return
        if isinstance(x, Selector):
            if x.mode is SelectorMode.CHOOSE:
                zones = tuple(
                    f"{z.kind.name}:{z.controller.name if z.controller else None}"
                    for z in x.zones
                )
                count = x.count.value if isinstance(x.count, QConst) else repr(x.count)
                out.append((*holder, zones, count))
            return
        verb_name = getattr(getattr(x, "verb", None), "name", None) or holder[1]
        holder = (type(x).__name__, verb_name)
        for f in dataclasses.fields(x):
            walk(getattr(x, f.name), holder)

    walk(root, (None, None))
    return out


def _tapped_handles(world):
    return {h for h, cs in world.cards.items() if cs.tapped}


class LedgerGroundTruth(unittest.TestCase):
    """Committed ledger + live compiled IR agree with the LIFT-NOW law."""

    @classmethod
    def setUpClass(cls):
        cls.ledger = json.loads(LEDGER.read_text())

    def test_lane_counts_and_population_frozen(self):
        self.assertEqual(self.ledger["lane_counts"], {"L-A": 161, "L-B": 27, "L-C": 5})
        self.assertEqual(self.ledger["population"]["nodes"], 193)

    def test_lift_rows_match_compiled_ir(self):
        seen = set()
        for n in self.ledger["nodes"]:
            if n["lane"] != "L-B":
                continue
            key = (n["set"], n["card"])
            if key not in LIFT_CARDS:
                continue
            seen.add(key)
            rec = _record(*key)
            shapes = _choose_selectors(rec)
            want_count = json.loads(n["count"])
            self.assertEqual(want_count["tag"], "QConst")
            hits = [
                s
                for s in shapes
                if s[2] == tuple(n["zones"]) and s[3] == want_count["value"]
            ]
            self.assertTrue(hits, (key, n["zones"], want_count, shapes))
            holder = hits[0][0]
            if n["rule_key"] == "firstn":
                self.assertIn(holder, ("Atom", "AtomArgs"))
                self.assertEqual(hits[0][1], n["verb"])
            elif n["rule_key"] == "disco":
                self.assertEqual(holder, "CostDiscard")
            elif n["rule_key"] == "saptap":
                self.assertEqual(holder, "CostTap")
        self.assertEqual(seen, LIFT_CARDS)

    def test_deferred_classes_keep_their_silent_bytes(self):
        # ZND-7(a): the merged multi-seat HAND:ANY L-B rows are NOT lifted
        # (Bad Deal, Liliana, Waker of the Dead — the merged menu cannot
        # say WHICH seat chooses, so asking would be blindness). Their
        # compiled shape must stay byte-present (the ledger lane map is
        # the adjudicator; this pins the IR did not move).
        lb_merged = {
            (n["set"], n["card"])
            for n in self.ledger["nodes"]
            if n["lane"] == "L-B" and n["zones"] == ["HAND:ANY"]
        }
        self.assertEqual(
            lb_merged, {("M21", "Bad Deal"), ("M21", "Liliana, Waker of the Dead")}
        )
        for set_name, card_name in lb_merged:
            rec = _record(set_name, card_name)
            shapes = _choose_selectors(rec)
            self.assertTrue(
                any("HAND:ANY" in s[2] for s in shapes),
                (card_name, "merged-zone CHOOSE selector vanished", shapes),
            )


class _RecorderMixin:
    def recorder(self, chooser=None):
        """Attach a provider recording (site, vocab) per ask. chooser(vocab)
        answers; the default first word EQUALS the old silent pick, so the
        falsifier tests always supply a differing answer."""
        asks: list[tuple[str, tuple[str, ...]]] = []

        def prov(vocab, what):
            asks.append((what, tuple(vocab)))
            return vocab[0] if chooser is None else chooser(vocab)

        self.ex.decisions.provider = prov
        return asks


class CostDiscardLift(unittest.TestCase, _RecorderMixin):
    """Cost lane (8 disco nodes): 'discard N cards' is the payer's
    decision, not an accident of Handle order (r22a law, extended)."""

    def setUp(self):
        reset_oracle_ids()
        self.world = GameWorld(num_players=2, start_life=20, master_seed=31)
        self.p0, self.p1 = self.world.player_order[0], self.world.player_order[1]
        self.source = self.world.add_card(
            card_id("Source", "2", "2"), self.p0, ZONE_BATTLEFIELD
        )
        self.h1 = self.world.add_card(card_id("H1", "1", "1"), self.p0, ZONE_HAND)
        self.h2 = self.world.add_card(card_id("H2", "1", "1"), self.p0, ZONE_HAND)
        self.h3 = self.world.add_card(card_id("H3", "1", "1"), self.p0, ZONE_HAND)
        self.ex = Executor(self.world)

    def plan_for(self, n: int, sel_filter=None):
        sel = Selector(
            QConst(n),
            SelectorMode.CHOOSE,
            sel_filter if sel_filter is not None else FAnd(()),
            zones=HAND_YOU,
        )
        ctx = ctx_for(self.ex, source=self.source, controller=self.p0)
        plan, reason = build_payment_plan(self.world, ctx, cost(CostDiscard(sel)))
        assert plan is not None, reason
        return plan

    def test_discard_cost_asks_and_the_answer_is_the_card(self):
        # RED pre-R3: silent first-need pick.
        plan = self.plan_for(1)
        self.assertIsNotNone(
            getattr(plan, "discard_options", None),
            "plan must record the FULL discard pool (RED pre-R3)",
        )
        self.assertEqual(
            plan.discard_options, ((tuple(sorted((self.h1, self.h2, self.h3))), 1),)
        )
        asks = self.recorder(chooser=lambda v: str(self.h3))
        pay_costs(self.ex, plan, source=self.source, controller=self.p0)
        self.assertEqual(len(asks), 1)
        site, vocab = asks[0]
        self.assertTrue(site.startswith(f"discard:{self.p0}:{self.source}"), site)
        self.assertEqual(
            vocab, tuple(str(h) for h in sorted((self.h1, self.h2, self.h3)))
        )
        self.assertEqual(self.world.zone_of(self.h3).kind, ZONE_GRAVEYARD)
        self.assertEqual(self.world.zone_of(self.h1).kind, ZONE_HAND)

    def test_k_of_n_discard_asks_shrinking_menu(self):
        # Thrill of Possibility shape (k=2): two asks, the second menu
        # EXCLUDES the first answer (RED pre-R3: two silent picks).
        plan = self.plan_for(2)
        answers = [str(self.h3), str(self.h1)]
        state = {"n": 0}

        def chooser(vocab):
            state["n"] += 1
            return answers[state["n"] - 1]

        asks = self.recorder(chooser=chooser)
        pay_costs(self.ex, plan, source=self.source, controller=self.p0)
        self.assertEqual([len(v) for _s, v in asks], [3, 2])
        self.assertNotIn(str(self.h3), asks[1][1])
        for h in (self.h1, self.h3):
            self.assertEqual(self.world.zone_of(h).kind, ZONE_GRAVEYARD)
        self.assertEqual(self.world.zone_of(self.h2).kind, ZONE_HAND)

    def test_unanswered_discard_cost_raises_never_a_silent_pick(self):
        # C15: no lane can answer -> the ask RAISES (RED pre-R3: silence).
        plan = self.plan_for(1)
        with self.assertRaises(ValueError) as cm:
            pay_costs(self.ex, plan, source=self.source, controller=self.p0)
        self.assertIn("discard:", str(cm.exception))

    def test_forced_hand_stays_silent_and_witness_identical(self):
        # len(pool) == need -> §1.4 auto-fill: NO provider needed at all.
        self.world.move_to_zone(self.h3, self.p0, ZONE_LIBRARY)
        plan = self.plan_for(2)
        pay_costs(self.ex, plan, source=self.source, controller=self.p0)
        for h in (self.h1, self.h2):
            self.assertEqual(self.world.zone_of(h).kind, ZONE_GRAVEYARD)

    def test_self_referential_discard_never_asks(self):
        # IS_SOURCE printed self-cost (r20c carve-back): forced
        # single-candidate, no decision, no ask (GREEN both sides).
        self.h1_src = self.world.add_card(
            card_id("Selfie", "1", "1"), self.p0, ZONE_HAND
        )
        sel = Selector(QConst(1), SelectorMode.CHOOSE, IS_SOURCE, zones=HAND_YOU)
        ctx = ctx_for(self.ex, source=self.h1_src, controller=self.p0)
        plan, reason = build_payment_plan(self.world, ctx, cost(CostDiscard(sel)))
        assert plan is not None, reason
        pay_costs(self.ex, plan, source=self.h1_src, controller=self.p0)
        self.assertEqual(self.world.zone_of(self.h1_src).kind, ZONE_GRAVEYARD)

    def test_hand_built_plan_pays_the_frozen_path(self):
        plan = PaymentPlan(discard=(self.h2,))
        pay_costs(self.ex, plan, source=self.source, controller=self.p0)
        self.assertEqual(self.world.zone_of(self.h2).kind, ZONE_GRAVEYARD)
        self.assertEqual(self.world.zone_of(self.h1).kind, ZONE_HAND)


class CostTapLift(unittest.TestCase, _RecorderMixin):
    """CostTap target branch (Shacklegeist shape): WHICH permanent taps is
    a decision when the pool offers one."""

    def setUp(self):
        reset_oracle_ids()
        self.world = GameWorld(num_players=2, start_life=20, master_seed=37)
        self.p0, self.p1 = self.world.player_order[0], self.world.player_order[1]
        self.source = self.world.add_card(
            card_id("Source", "2", "2"), self.p0, ZONE_HAND
        )
        self.t1 = self.world.add_card(
            card_id("T1", "1", "1"), self.p0, ZONE_BATTLEFIELD
        )
        self.t2 = self.world.add_card(
            card_id("T2", "1", "1"), self.p0, ZONE_BATTLEFIELD
        )
        self.theirs = self.world.add_card(
            card_id("Theirs", "1", "1"), self.p1, ZONE_BATTLEFIELD
        )
        self.ex = Executor(self.world)

    def plan_for(self):
        sel = Selector(
            QConst(1),
            SelectorMode.CHOOSE,
            CREATURE,
            zones=(Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),),
        )
        ctx = ctx_for(self.ex, source=self.source, controller=self.p0)
        plan, reason = build_payment_plan(self.world, ctx, cost(CostTap(sel)))
        assert plan is not None, reason
        return plan

    def test_tap_cost_asks_and_the_answer_is_the_permanent(self):
        # RED pre-R3: cands[:1] silent witness.
        plan = self.plan_for()
        self.assertIsNotNone(
            getattr(plan, "tap_options", None),
            "plan must record the FULL tap pool (RED pre-R3)",
        )
        asks = self.recorder(chooser=lambda v: str(self.t2))
        pay_costs(self.ex, plan, source=self.source, controller=self.p0)
        self.assertEqual(len(asks), 1)
        site, vocab = asks[0]
        self.assertTrue(site.startswith(f"tap:{self.p0}:{self.source}"), site)
        self.assertEqual(vocab, tuple(str(h) for h in sorted((self.t1, self.t2))))
        tapped = _tapped_handles(self.world)
        self.assertEqual(tapped, {self.t2})


class EffectChooseLift(unittest.TestCase, _RecorderMixin):
    """Effect lane: the finite-CHOOSE fold in resolve_selector asks when
    an EFFECT-role lane resolves it (Rewind/Cultivate shapes). Source
    sits in HAND so the battlefield menu is exactly a, b, c."""

    def setUp(self):
        reset_oracle_ids()
        self.world = GameWorld(num_players=2, start_life=20, master_seed=41)
        self.p0, self.p1 = self.world.player_order[0], self.world.player_order[1]
        self.source = self.world.add_card(
            card_id("Source", "2", "2"), self.p0, ZONE_HAND
        )
        self.a = self.world.add_card(card_id("A", "1", "1"), self.p0, ZONE_BATTLEFIELD)
        self.b = self.world.add_card(card_id("B", "1", "1"), self.p0, ZONE_BATTLEFIELD)
        self.c = self.world.add_card(card_id("C", "1", "1"), self.p1, ZONE_BATTLEFIELD)
        self.ex = Executor(self.world)

    def test_tap_effect_choose_asks_and_answers_are_the_victims(self):
        # RED pre-R3: ordered[:2] silent stand-in (the 12a law /141 lifts).
        answers = [str(self.c), str(self.a)]
        state = {"n": 0}

        def chooser(vocab):
            state["n"] += 1
            return answers[state["n"] - 1]

        asks = self.recorder(chooser=chooser)
        sel = Selector(QConst(2), SelectorMode.CHOOSE, UNIV, zones=(BF_ANY,))
        self.ex.execute(
            atom(Verb.TAP, target=sel), source=self.source, controller=self.p0
        )
        self.assertEqual(len(asks), 2, asks)
        self.assertEqual(
            asks[0][1], tuple(str(h) for h in sorted((self.a, self.b, self.c)))
        )
        self.assertNotIn(str(self.c), asks[1][1])  # shrinking menu
        self.assertEqual(_tapped_handles(self.world), {self.a, self.c})

    def test_search_choose_asks_and_found_cards_follow_the_answer(self):
        # Cultivate shape (RED pre-R3: blind first-n from the library).
        self.l1 = self.world.add_card(card_id("L1", "1", "1"), self.p0, ZONE_LIBRARY)
        self.l2 = self.world.add_card(card_id("L2", "1", "1"), self.p0, ZONE_LIBRARY)
        self.l3 = self.world.add_card(card_id("L3", "1", "1"), self.p0, ZONE_LIBRARY)
        sel = Selector(
            QConst(1),
            SelectorMode.CHOOSE,
            UNIV,
            zones=(Zone(ZoneKind.LIBRARY, ControllerRef.YOU),),
        )
        asks = self.recorder(chooser=lambda v: str(self.l2))
        self.ex.execute(
            atom(
                Verb.SEARCH,
                cards=sel,
                destination=Zone(ZoneKind.HAND, ControllerRef.YOU),
            ),
            source=self.source,
            controller=self.p0,
        )
        self.assertEqual(len(asks), 1, asks)
        self.assertEqual(
            asks[0][1], tuple(str(h) for h in sorted((self.l1, self.l2, self.l3)))
        )
        self.assertEqual(self.world.zone_of(self.l2).kind, ZONE_HAND)

    def test_forced_effect_choose_stays_silent(self):
        # population == k -> no decision exists, no ask (anti-phantom).
        self.world.move_to_zone(self.c, self.p1, ZONE_GRAVEYARD)
        asks = self.recorder()
        sel = Selector(QConst(2), SelectorMode.CHOOSE, UNIV, zones=(BF_ANY,))
        self.ex.execute(
            atom(Verb.TAP, target=sel), source=self.source, controller=self.p0
        )
        self.assertEqual(asks, [])
        self.assertEqual(_tapped_handles(self.world), {self.a, self.b})


class SilentLanesStaySilent(unittest.TestCase, _RecorderMixin):
    """Anti-lift pins: the deferred classes must NOT acquire an ask."""

    def setUp(self):
        reset_oracle_ids()
        self.world = GameWorld(num_players=2, start_life=20, master_seed=43)
        self.p0, self.p1 = self.world.player_order[0], self.world.player_order[1]
        self.source = self.world.add_card(
            card_id("Source", "2", "2"), self.p0, ZONE_HAND
        )
        self.a = self.world.add_card(card_id("A", "1", "1"), self.p0, ZONE_BATTLEFIELD)
        self.b = self.world.add_card(card_id("B", "1", "1"), self.p0, ZONE_BATTLEFIELD)
        self.c = self.world.add_card(card_id("C", "1", "1"), self.p1, ZONE_BATTLEFIELD)
        self.ex = Executor(self.world)

    def test_qunbounded_choose_folds_whole_population(self):
        asks = self.recorder()
        sel = Selector(QUnbounded(), SelectorMode.CHOOSE, UNIV, zones=(BF_ANY,))
        self.ex.execute(
            atom(Verb.TAP, target=sel), source=self.source, controller=self.p0
        )
        self.assertEqual(asks, [])
        self.assertEqual(_tapped_handles(self.world), {self.a, self.b, self.c})

    def test_one_of_qunbounded_raises_never_guesses(self):
        # /141 §6 QUnbounded deferral, refusal law: the Selector TYPE
        # refuses ONE_OF x QUnbounded at construction (ValueError) — the
        # resolve_selector NotImplementedError lane (:681-685) is
        # defense-in-depth for IR that bypassed the constructor. No lane
        # ever guesses an unbounded partition pick.
        with self.assertRaises(ValueError):
            Selector(QUnbounded(), SelectorMode.ONE_OF, UNIV, zones=(BF_ANY,))

    def test_cast_ok_lane_never_asks_positional_law_kept(self):
        # The CAST positional slice (F2(3)) is NOT an effect decision:
        # with ``ok`` supplied the fold never asks, whatever the
        # population (GREEN both sides; guards the wiring guard).
        ctx = ctx_for(self.ex, source=self.source, controller=self.p0)
        asks = self.recorder()
        sel = Selector(QConst(1), SelectorMode.CHOOSE, UNIV, zones=(BF_ANY,))
        out = resolve_selector(sel, ctx, ok=lambda h: True)
        self.assertEqual(asks, [])
        self.assertEqual(out, [min((self.a, self.b, self.c))])

    def test_seat_zone_choose_stays_silent(self):
        # ZND-9 direction class: a PLAYER-zone CHOOSE is not lifted — the
        # chooser's seat is unencoded, asking would be blind.
        ctx = ctx_for(self.ex, source=self.source, controller=self.p0)
        asks = self.recorder()
        sel = Selector(
            QConst(1),
            SelectorMode.CHOOSE,
            UNIV,
            zones=(Zone(ZoneKind.PLAYER, ControllerRef.YOU),),
        )
        resolve_selector(sel, ctx)
        self.assertEqual(asks, [])


# ---------------------------------------------------------------------------
# FIX-2 (R3 diff-gate follow-up /144 verdict): the deferral law must be
# PINNED by tests, not prose — oracle-table contents, the reason-class map
# for every non-lifted L-B row, and the Run Afoul behavior inversion.
# ---------------------------------------------------------------------------
RUN_AFOUL_ORACLE = "5462cb38-7cd7-46e8-a273-35d0d1af45b4"


class DeferredDeferralTable(unittest.TestCase):
    """(a) table-content pin: who is oracle-deferred, and WHY every other
    deferred class is deferred by a GATE RULE instead (so deleting one
    mechanism cannot silently reclassify the others)."""

    @classmethod
    def setUpClass(cls):
        cls.ledger = json.loads(LEDGER.read_text())

    def test_oracle_table_is_exactly_run_afoul(self):
        # re-pinned 2026-10-29: V10 changes Run Afoul's tree (CONTROLLER_IS
        # TARGET_PLAYER) and asks a sacrifice menu's controller, so the
        # direction is encoded and the table that held Run Afoul is empty.
        self.assertEqual(selectors.R3_CHOOSE_DEFERRED_ORACLES, frozenset())

    def test_uuid_is_the_compiled_m21_run_afoul(self):
        rec = _pool("M21").get(RUN_AFOUL_ORACLE)
        self.assertIsNotNone(rec, "deferred UUID must be a real compiled M21 oracle_id")
        self.assertEqual(rec.card.name, "Run Afoul")

    def test_reason_class_map_covers_every_deferred_lb_row(self):
        merged, unbounded, opponent = set(), set(), set()
        oid_of = {}
        for n in self.ledger["nodes"]:
            if n["lane"] != "L-B":
                continue
            key = (n["set"], n["card"])
            oid_of[key] = n["oracle_id"]
            if key in LIFT_CARDS:
                continue
            if n["zones"] == ["HAND:ANY"]:
                merged.add(key)
            elif json.loads(n["count"])["tag"] != "QConst":
                unbounded.add(key)
            else:
                opponent.add(key)
        # ZND-7(a) merged multi-seat menu — cannot say WHICH seat chooses:
        self.assertEqual(
            merged, {("M21", "Bad Deal"), ("M21", "Liliana, Waker of the Dead")}
        )
        # QUnbounded — the ONE_OF lane RAISES on it; stays folded (gate
        # rule: count must be QConst, selectors._choose_lift_allowed):
        self.assertEqual(
            unbounded,
            {
                ("M21", "Chandra, Flame's Catalyst"),
                ("M21", "Chandra, Heart of Fire"),
                ("M21", "Necromentia"),
                ("M21", "Siege Striker"),
            },
        )
        # opponent-chooser / direction-unencoded (ZND-9 gate rule:
        # chooser == card controller; Run Afoul additionally oracle-tabled):
        self.assertEqual(
            opponent,
            {
                ("M21", "Goremand"),
                ("M21", "Liliana's Steward"),
                ("M21", "Mind Rot"),
                ("M21", "Run Afoul"),
            },
        )
        # Every deferred card is OUTSIDE the lift set.
        # re-pinned 2026-10-29: V10 changes the opponent-chooser and merged-
        # menu classes from silent slices to asks of the deciding player, so
        # no card is oracle-tabled any more (the ledger rows above stay the
        # R3 historical classification).
        deferred_cards = merged | unbounded | opponent
        self.assertFalse(deferred_cards & LIFT_CARDS)
        for set_name, card_name in deferred_cards:
            self.assertNotIn(
                oid_of[(set_name, card_name)],
                selectors.R3_CHOOSE_DEFERRED_ORACLES,
                (card_name, "no card is oracle-tabled after V10"),
            )


class RunAfoulDeferralBehavior(unittest.TestCase, _RecorderMixin):
    """(b) re-pinned 2026-10-29: V10 changes this class. It pinned that the
    oracle table kept Run Afoul's BF:ANY CHOOSE silent, because asking would
    have let the CASTER pick the opponent's sacrifice (the direction axis was
    unencoded, ZND-9). The tree now says whose fliers (CONTROLLER_IS
    TARGET_PLAYER) and the sacrifice lane asks the player who controls the
    menu (CR 701.21a), so the hazard is closed by structure: a sacrifice menu
    spanning two controllers raises, and a one-player menu is that player's
    ask."""

    def setUp(self):
        reset_oracle_ids()
        self.world = GameWorld(num_players=2, start_life=20, master_seed=47)
        self.p0, self.p1 = self.world.player_order[0], self.world.player_order[1]
        self.source = self.world.add_card(
            card_id("Run Afoul", oid=RUN_AFOUL_ORACLE), self.p0, ZONE_BATTLEFIELD
        )
        self.a = self.world.add_card(card_id("A", "1", "1"), self.p0, ZONE_BATTLEFIELD)
        self.b = self.world.add_card(card_id("B", "1", "1"), self.p1, ZONE_BATTLEFIELD)
        self.c = self.world.add_card(card_id("C", "1", "1"), self.p1, ZONE_BATTLEFIELD)
        self.ex = Executor(self.world)

    def _sacrifice(self, filter_):
        ctx = ctx_for(self.ex, source=self.source, controller=self.p0)
        sel = Selector(QConst(1), SelectorMode.CHOOSE, filter_, zones=(BF_ANY,))
        return resolve_selector(sel, ctx, ask_choose=True, sacrifice=True)

    def test_deferred_oracle_never_asks(self):
        # A menu over both players' creatures does not say who sacrifices.
        asks = self.recorder()
        with self.assertRaises(ValueError):
            self._sacrifice(CREATURE)
        self.assertEqual(asks, [])

    def test_removing_the_deferral_flips_to_an_ask(self):
        # The opponent's own creatures: the opponent is asked, not the caster.
        from MTG_bot.core.ability_tree import FAtom, FAtomPred

        seats: list = []
        asks = self.recorder(chooser=lambda v: str(self.c))
        prov = self.ex.decisions.provider

        def seat_provider(vocab, what):
            seats.append(self.ex.decisions.asking_seat)
            return prov(vocab, what)

        self.ex.decisions.provider = seat_provider
        theirs = FAnd((CREATURE, FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.OPPONENT)))
        out = self._sacrifice(theirs)
        self.assertEqual(out, [self.c])
        self.assertEqual(len(asks), 1, asks)
        self.assertTrue(asks[0][0].startswith(f"sacrifice:{self.p1}:"), asks)
        self.assertEqual(asks[0][1], tuple(str(h) for h in sorted((self.b, self.c))))
        self.assertEqual(seats, [self.p1])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
