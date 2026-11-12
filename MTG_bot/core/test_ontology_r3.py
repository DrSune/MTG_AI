"""CHOOSE asks: a real choice goes to the decider instead of collapsing into
the Handle-sorted ``ordered[:k]`` slice.

* cost lanes: ``legality.build_payment_plan`` records the FULL candidate
  pool per CostDiscard/CostTap segment (``discard_options`` /
  ``tap_options``, mirroring ``sacrifice_options``) and ``pay_costs``
  asks with seat-in keys ``discard:<seat>:<source>:<digest>`` /
  ``tap:<seat>:<source>:<digest>`` when a segment really offers a choice
  (len(pool) > need);
* effect lane: the finite-CHOOSE fold in ``selectors.resolve_selector``
  asks over the Handle-sorted menu when an EFFECT-role lane resolves it
  (the CAST-lane ``ok`` clamp, quantity/count and query callers stay
  silent BY CONSTRUCTION).

An effect's QUnbounded CHOOSE ("any number", CR 107.1c) asks pick by pick
with a NONE stop, as "up to N" does (2026-11-12, the /141 deferral closed);
a population read of it takes the whole population.

Silent by rule: ONE_OF over
QUnbounded is refused, forced segments (len(pool) == need) auto-fill without
asking, IS_SOURCE self-costs have no choice, hand-built plans pay their
frozen path, and a PLAYER-zone CHOOSE never asks (whose choice it is is not
encoded). The committed ledger reports/r3_blindness.json (the 14 lifted
cards, the deferred classes) is held against the live compiled IR, and a
sacrifice menu asks the player who controls it.
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
    QAtMost,
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

# The lifted cards (14 cards / 14 nodes). Zones and counts are re-verified
# against the committed ledger AND the live compiled IR below; this table
# carries the NAMES.
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
    """The committed ledger and the live compiled IR agree on the lifted cards."""

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
            if key == ("M21", "Alpine Houndmaster"):
                # The ledger row is one up-to-two CHOOSE ("a card named Alpine Watchdog
                # and/or a card named Igneous Cur"); the IR has one pick over the row's zones
                # per name, as many picks as the row's count. Each pick is QAtMost(1) (CR
                # 701.23b, a hidden-zone search may fail to find), asked through the
                # resolve-time QAtMost lane with a NONE stop.
                picks = [
                    s for s in shapes if s[2] == tuple(n["zones"]) and s[3] == repr(QAtMost(1))
                ]
                self.assertEqual(len(picks), want_count["value"], (key, picks))
                continue
            if key == ("M21", "Demonic Embrace"):
                # The ledger row is the discard cost of the activated row the graveyard-cast
                # permission compiled to. That row is refused (CR 601.3: an activated ability
                # cannot cast the card from its graveyard; there is no permission lane), so
                # the live IR carries no such choice and the card is engine-unsupported.
                self.assertEqual([s for s in shapes if s[2] == tuple(n["zones"])], [], key)
                continue
            want = want_count["value"]
            if key == ("M21", "Kinetic Augur"):
                # "discard up to two" is QAtMost(2) in the IR (the player's
                # 0..2); the ledger row says QConst(2).
                want = repr(QAtMost(2))
            if key == ("M21", "Ugin, the Spirit Dragon"):
                # Ugin's [-10] "put up to seven permanent cards" is QAtMost(7) in the IR
                # (0..7, asked pick by pick with a NONE stop); the ledger row says QConst(7).
                want = repr(QAtMost(7))
            hits = [s for s in shapes if s[2] == tuple(n["zones"]) and s[3] == want]
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
        # The merged multi-seat HAND:ANY L-B rows (Bad Deal; Liliana, Waker
        # of the Dead) are outside the lift set; their compiled HAND:ANY
        # CHOOSE selector must still be present.
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
        answers; the default first word EQUALS the silent slice's pick, so
        the tests always supply a differing answer."""
        asks: list[tuple[str, tuple[str, ...]]] = []

        def prov(vocab, what):
            asks.append((what, tuple(vocab)))
            return vocab[0] if chooser is None else chooser(vocab)

        self.ex.decisions.provider = prov
        return asks


class CostDiscardLift(unittest.TestCase, _RecorderMixin):
    """Cost lane: 'discard N cards' is the payer's decision, not an
    accident of Handle order (as for sacrifice costs)."""

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
        # EXCLUDES the first answer.
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
        # No lane can answer -> the ask RAISES, never a silent pick.
        plan = self.plan_for(1)
        with self.assertRaises(ValueError) as cm:
            pay_costs(self.ex, plan, source=self.source, controller=self.p0)
        self.assertIn("discard:", str(cm.exception))

    def test_forced_hand_stays_silent_and_witness_identical(self):
        # len(pool) == need -> auto-fill: NO provider needed at all.
        self.world.move_to_zone(self.h3, self.p0, ZONE_LIBRARY)
        plan = self.plan_for(2)
        pay_costs(self.ex, plan, source=self.source, controller=self.p0)
        for h in (self.h1, self.h2):
            self.assertEqual(self.world.zone_of(h).kind, ZONE_GRAVEYARD)

    def test_self_referential_discard_never_asks(self):
        # IS_SOURCE printed self-cost: forced single-candidate, no
        # decision, no ask.
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
        # Cultivate shape.
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

    def test_qunbounded_choose_asks_with_a_stop(self):
        # "Tap any number of ...": every number from zero to all of them (CR 107.1c), so
        # each pick may stop (the /141 deferral, closed 2026-11-12).
        answers = iter([str(self.b), "NONE"])
        asks = self.recorder(chooser=lambda v: next(answers))
        sel = Selector(QUnbounded(), SelectorMode.CHOOSE, UNIV, zones=(BF_ANY,))
        self.ex.execute(
            atom(Verb.TAP, target=sel), source=self.source, controller=self.p0
        )
        self.assertEqual([vocab[-1] for _, vocab in asks], ["NONE", "NONE"])
        self.assertEqual(_tapped_handles(self.world), {self.b})

    def test_one_of_qunbounded_raises_never_guesses(self):
        # The Selector TYPE refuses ONE_OF x QUnbounded at construction
        # (ValueError); resolve_selector's ONE_OF branch raises
        # NotImplementedError on any count but QConst/QAtMost. No lane ever
        # guesses an unbounded partition pick.
        with self.assertRaises(ValueError):
            Selector(QUnbounded(), SelectorMode.ONE_OF, UNIV, zones=(BF_ANY,))

    def test_cast_ok_lane_never_asks_positional_law_kept(self):
        # The CAST positional slice is NOT an effect decision: with ``ok``
        # supplied the fold never asks, whatever the population.
        ctx = ctx_for(self.ex, source=self.source, controller=self.p0)
        asks = self.recorder()
        sel = Selector(QConst(1), SelectorMode.CHOOSE, UNIV, zones=(BF_ANY,))
        out = resolve_selector(sel, ctx, ok=lambda h: True)
        self.assertEqual(asks, [])
        self.assertEqual(out, [min((self.a, self.b, self.c))])

    def test_seat_zone_choose_stays_silent(self):
        # A PLAYER-zone CHOOSE is not lifted: the chooser's seat is
        # unencoded, asking would be blind.
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
# The deferral law, pinned by tests: the reason-class map for every
# non-lifted L-B row, and the Run Afoul behavior.
# ---------------------------------------------------------------------------
RUN_AFOUL_ORACLE = "5462cb38-7cd7-46e8-a273-35d0d1af45b4"


class DeferredDeferralTable(unittest.TestCase):
    """Every deferred L-B row and the GATE RULE that defers its class (so
    deleting one mechanism cannot silently reclassify the others)."""

    @classmethod
    def setUpClass(cls):
        cls.ledger = json.loads(LEDGER.read_text())

    def test_uuid_is_the_compiled_m21_run_afoul(self):
        rec = _pool("M21").get(RUN_AFOUL_ORACLE)
        self.assertIsNotNone(rec, "deferred UUID must be a real compiled M21 oracle_id")
        self.assertEqual(rec.card.name, "Run Afoul")

    def test_reason_class_map_covers_every_deferred_lb_row(self):
        merged, unbounded, opponent = set(), set(), set()
        for n in self.ledger["nodes"]:
            if n["lane"] != "L-B":
                continue
            key = (n["set"], n["card"])
            if key in LIFT_CARDS:
                continue
            if n["zones"] == ["HAND:ANY"]:
                merged.add(key)
            elif json.loads(n["count"])["tag"] != "QConst":
                unbounded.add(key)
            else:
                opponent.add(key)
        # ledger class: merged multi-seat menu — the menu cannot say WHICH seat chooses:
        self.assertEqual(
            merged, {("M21", "Bad Deal"), ("M21", "Liliana, Waker of the Dead")}
        )
        # QUnbounded — deferred by the /141 gate (the ONE_OF lane raised on
        # it); asked since 2026-11-12 with a NONE stop ("any number"):
        self.assertEqual(
            unbounded,
            {
                ("M21", "Chandra, Flame's Catalyst"),
                ("M21", "Chandra, Heart of Fire"),
                ("M21", "Necromentia"),
                ("M21", "Siege Striker"),
            },
        )
        # opponent-chooser / direction-unencoded (gate rule: chooser ==
        # card controller):
        self.assertEqual(
            opponent,
            {
                ("M21", "Goremand"),
                ("M21", "Liliana's Steward"),
                ("M21", "Mind Rot"),
                ("M21", "Run Afoul"),
            },
        )
        # Every deferred card is OUTSIDE the lift set (the ledger rows above
        # are the committed classification).
        deferred_cards = merged | unbounded | opponent
        self.assertFalse(deferred_cards & LIFT_CARDS)


class RunAfoulDeferralBehavior(unittest.TestCase, _RecorderMixin):
    """Asking the caster would let the CASTER pick the opponent's
    sacrifice. Run Afoul's tree says whose fliers (CONTROLLER_IS
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
