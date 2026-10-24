"""R3b phantom-fold battery (binding spec /145, KNOWLEDGE/2026-10-20).

The fold: an engine-resolved (L-A) CHOOSE Selector whose menu is a forced
singleton compiles to mode=ALL (no-decision). Classes (all pins below are
the committed audit reports/r3b_sortdelta.json arithmetic):

    self  107  filter self-referential (IS_SOURCE, conjunctive-positive)
    top     3  single LIBRARY/YOU/TOP zone, universal filter
    seat    2  single PLAYER/YOU zone, universal filter
    total 112 nodes; corpus CHOOSE 193 -> 81 (M21 145->70, ZNR 48->11);
    ALL census M21 93->168, ZNR 49->86.

FIX-2 hazard: a POSITIVE IS_SOURCE leaf in DISJUNCTIVE position (FOr) does
NOT denote a forced singleton — classify AND the ledger flattener RAISE
StateCorruptionError (a shape gap, never a silent mis-fold).
FIX-1: the TARGET+IS_SOURCE quintet (Barrin, Tolarian Archmage / Basri's
Acolyte / Experimental Overload / Hobblefiend / Niambi, Esteemed Speaker)
is a DESIGNATION lane and must survive as TARGET.
FIX (r20c re-key): the executor self-designation lane keys on
mode in (CHOOSE, ALL) — the folded nodes resolve silently through it.
Warmonger guard: FNot(IS_SOURCE) ("another") is self-NEGATED: never folds,
stays a CHOOSE multi-candidate ask, and the ledger re-keys it L-C/sacask.

RED-FIRST: the pre-change battery (this file + the two re-pin sites at
test_ontology_r3.py LedgerGroundTruth and test_pick_ask_promotion.py) is
recorded at reports/r3b_red_prechange.txt — expect exactly that RED set to
flip GREEN at landing; anything else is a FINDING. (The original record at
/tmp/r3b_red_prechange.log was lost to /tmp cleanup; re-recorded 2026-10-24.)

Marked ``red_first`` (2026-10-24): excluded from the default run so the
suite's red means a regression, runnable with ``pytest -m red_first``.
Remove the marker at landing.
"""

from __future__ import annotations

import copy
import dataclasses
import json
import unittest
from pathlib import Path

import pytest

from MTG_bot.core.ability_tree import (
    Atom,
    ControllerRef,
    CostSacrifice,
    FAnd,
    FAtom,
    FAtomPred,
    FNot,
    FOr,
    OptionalEffect,
    QConst,
    QUnbounded,
    Seq,
    Selector,
    SelectorMode,
    Verb,
    Zone,
    ZoneKind,
)
from MTG_bot.core.errors import StateCorruptionError
from MTG_bot.core.executor.legality import build_payment_plan, ctx_for, pay_costs
from MTG_bot.core.executor.query import MAY_VOCAB, optional_offer
from MTG_bot.core.executor.selectors import _filter_is_self_referential, role_handles
from MTG_bot.core.state import (
    ZONE_BATTLEFIELD,
    ZONE_GRAVEYARD,
    ZONE_LIBRARY,
)
from MTG_bot.core.test_executor_binding import (
    CREATURE,
    IS_SOURCE,
    UNIV,
    atom,
    reset_oracle_ids,
)
from MTG_bot.core.test_executor_legality import LegalityCase, cost
from MTG_bot.core.test_executor_r22a import SacrificeVocabulary
from MTG_bot.core.test_executor_query import QueryCase
from MTG_bot.core.test_ontology_r3 import _pool, _record


pytestmark = pytest.mark.red_first

REPO = Path(__file__).resolve().parents[2]

BF_YOU = (Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU),)
LIB_YOU = (Zone(ZoneKind.LIBRARY, ControllerRef.YOU),)
GRAVE_YOU = Zone(ZoneKind.GRAVEYARD, ControllerRef.YOU)

QUINTET = (
    "Barrin, Tolarian Archmage",
    "Basri's Acolyte",
    "Experimental Overload",
    "Hobblefiend",
    "Niambi, Esteemed Speaker",
)

# classes whose fold is a no-decision replacement (fold-only classes)
FOLD_CLASSES = ("self", "top", "seat")


def selectors_of(root) -> list[Selector]:
    """Every Selector reachable from a dataclass/serde root (card-root
    law, never walk())."""
    out: list[Selector] = []

    def w(x):
        if isinstance(x, (list, tuple)):
            for y in x:
                w(y)
            return
        if isinstance(x, dict):
            for v in x.values():
                w(v)
            return
        if not (dataclasses.is_dataclass(x) and not isinstance(x, type)):
            return
        if isinstance(x, Selector):
            out.append(x)
            return
        for f in dataclasses.fields(x):
            w(getattr(x, f.name))

    w(root)
    return out


def is_pure_self(s: Selector) -> bool:
    return isinstance(s.filter, FAtom) and s.filter.pred is FAtomPred.IS_SOURCE


def has_mode(pool: dict, pred) -> int:
    return sum(1 for _, r in pool.items() for s in selectors_of(r.card) if pred(s))


class TestFoldShape(unittest.TestCase):
    """Landing shape: the engine-resolved CHOOSE nodes compile to ALL."""

    @classmethod
    def setUpClass(cls):
        cls.m21 = _pool("M21")
        cls.znr = _pool("ZNR")

    def test_self_designation_nodes_land_all(self):
        # CHOOSE+IS_SOURCE was the ask-shape; the fold replaces it with the
        # no-decision ALL shape (spec §2(1): "take what exists").
        for name in ("Selfless Savior", "Obsessive Stitcher", "Hobblefiend"):
            card = _record("M21", name)
            self.assertTrue(
                any(
                    s.mode is SelectorMode.ALL and is_pure_self(s)
                    for s in selectors_of(card)
                ),
                f"{name}: no ALL self-designation node at landing",
            )

    def test_corpus_census_at_landing(self):
        # r3b_sortdelta.json: CHOOSE 193 -> 81; ALL +112.
        self.assertEqual(
            has_mode(self.m21, lambda s: s.mode is SelectorMode.CHOOSE), 70
        )
        self.assertEqual(
            has_mode(self.znr, lambda s: s.mode is SelectorMode.CHOOSE), 11
        )
        self.assertEqual(has_mode(self.m21, lambda s: s.mode is SelectorMode.ALL), 168)
        self.assertEqual(has_mode(self.znr, lambda s: s.mode is SelectorMode.ALL), 86)

    def test_no_pure_self_choose_survives(self):
        # Every CHOOSE ∧ pure-IS_SOURCE node folds (Warmonger's cost is
        # FAnd-negated, NOT pure): corpus-wide zero at landing.
        for pool in (self.m21, self.znr):
            self.assertEqual(
                has_mode(
                    pool, lambda s: s.mode is SelectorMode.CHOOSE and is_pure_self(s)
                ),
                0,
            )

    def test_furious_rise_top_node_lands_all(self):
        card = _record("M21", "Furious Rise")
        moves = [
            s
            for s in selectors_of(card)
            if any(z.kind is ZoneKind.LIBRARY for z in s.zones)
        ]
        self.assertTrue(moves, "Furious Rise: library node vanished")
        self.assertTrue(all(s.mode is SelectorMode.ALL for s in moves))

    def test_snoop_cast_source_lands_all(self):
        card = _record("M21", "Conspicuous Snoop")
        casts = [
            s
            for a in card.abilities
            for s in selectors_of(a)
            if any(isinstance(n, Atom) and n.verb is Verb.CAST for n in _atoms(a))
            and any(z.kind is ZoneKind.LIBRARY for z in s.zones)
        ]
        self.assertTrue(casts, "Snoop: CAST top-card lane vanished")
        self.assertTrue(
            all(s.mode is SelectorMode.ALL for s in casts),
            "Snoop CAST source must land ALL (QUnbounded gate-invariant)",
        )

    def test_seat_nodes_land_all(self):
        for name in ("Runed Halo", "Keral Keep Disciples"):
            card = _record("M21", name)
            self.assertTrue(
                any(
                    s.mode is SelectorMode.ALL
                    and len(s.zones) == 1
                    and s.zones[0].kind is ZoneKind.PLAYER
                    for s in selectors_of(card)
                ),
                f"{name}: no ALL seat node at landing",
            )

    def test_every_landed_fold_is_reexplainable(self):
        # Nothing may fold that classify() cannot re-explain with the
        # SAME predicate (FIX-4: one shared function object).
        from MTG_bot.core.compiler.phantom_fold import classify

        for pool in (self.m21, self.znr):
            for _, r in pool.items():
                for s in selectors_of(r.card):
                    if s.mode is not SelectorMode.ALL:
                        continue
                    probe = copy.deepcopy(s.to_dict())
                    probe["mode"] = "CHOOSE"
                    if classify(probe) not in FOLD_CLASSES:
                        continue
                    self.fail(
                        f"{r.card.name}: ALL node re-explains as foldable "
                        "but was ALREADY ALL pre-fold? census drift"
                    )

    def test_fold_is_idempotent_at_compile(self):
        # compile_card folds once; a second fold pass over the landed
        # abilities must fire zero times.
        from MTG_bot.core.compiler.phantom_fold import fold_phantom_selectors

        for pool in (self.m21, self.znr):
            for _, r in pool.items():
                _, fired = fold_phantom_selectors(list(r.card.abilities), r.card.name)
                self.assertEqual(
                    sum(fired.values()), 0, f"{r.card.name}: fold not idempotent"
                )


def _atoms(root):
    out = []

    def w(x):
        if isinstance(x, (list, tuple)):
            for y in x:
                w(y)
            return
        if isinstance(x, dict):
            for v in x.values():
                w(v)
            return
        if not (dataclasses.is_dataclass(x) and not isinstance(x, type)):
            return
        if isinstance(x, Atom):
            out.append(x)
        for f in dataclasses.fields(x):
            w(getattr(x, f.name))

    w(root)
    return out


class TestFix2Hazard(unittest.TestCase):
    """FIX-2: a positive IS_SOURCE leaf in disjunctive position is NOT a
    forced singleton — the predicate RAISES, it never mis-folds."""

    def disjunctive_sel(self) -> Selector:
        return Selector(
            QConst(1), SelectorMode.CHOOSE, FOr((IS_SOURCE, FAnd(()))), zones=BF_YOU
        )

    def test_classify_raises_on_disjunctive_is_source(self):
        from MTG_bot.core.compiler.phantom_fold import classify

        with self.assertRaises(StateCorruptionError):
            classify(self.disjunctive_sel().to_dict())

    def test_ledger_flattener_raises_on_disjunctive_is_source(self):
        from tools.audit.r3_lane_ledger import fpreds

        with self.assertRaises(StateCorruptionError):
            fpreds(FOr((IS_SOURCE, FAnd(()))))

    def test_negated_is_source_is_self_negated_not_self(self):
        from MTG_bot.core.compiler.phantom_fold import classify

        sel = Selector(
            QConst(1),
            SelectorMode.CHOOSE,
            FAnd((CREATURE, FNot(IS_SOURCE))),
            zones=BF_YOU,
        )
        self.assertEqual(classify(sel.to_dict()), "self-negated")

    def test_target_mode_never_reaches_the_hazard(self):
        # mode gate: TARGET nodes are not fold candidates at all.
        from MTG_bot.core.compiler.phantom_fold import classify

        sel = Selector(
            QConst(1), SelectorMode.TARGET, FOr((IS_SOURCE, FAnd(()))), zones=BF_YOU
        )
        self.assertIsNone(classify(sel.to_dict()))


class TestLedgerLanding(unittest.TestCase):
    """FIX-5: the ledger re-pins at landing (fresh build + committed
    reports/r3_blindness.json): population 193 -> 81, lanes
    {L-A:48, L-B:27, L-C:6}; Warmonger's sac cost re-keys L-A -> L-C with
    polarity-aware NOT(IS_SOURCE) emission (the /145 §2(3) mis-lane fix)."""

    @classmethod
    def setUpClass(cls):
        from tools.audit import r3_lane_ledger

        cls.nodes = r3_lane_ledger.build_nodes()

    def _lanes(self) -> dict:
        out: dict[str, int] = {}
        for n in self.nodes:
            out[n["lane"]] = out.get(n["lane"], 0) + 1
        return out

    def test_population_and_lanes(self):
        self.assertEqual(len(self.nodes), 81)
        self.assertEqual(self._lanes(), {"L-A": 48, "L-B": 27, "L-C": 6})

    def test_warmonger_cost_lane(self):
        rows = [n for n in self.nodes if "Warmonger" in n["card"]]
        self.assertEqual(len(rows), 1, "the two pure-self rows must be folded away")
        row = rows[0]
        self.assertEqual(row["lane"], "L-C")
        self.assertIn("NOT(IS_SOURCE)", row["filter"])
        self.assertNotIn("IS_SOURCE", row["filter"])

    def test_self_negated_population_is_exactly_one(self):
        negated = [n for n in self.nodes if "NOT(IS_SOURCE)" in n["filter"]]
        self.assertEqual(len(negated), 1, "exactly one self-negated CHOOSE corpus-wide")

    def test_committed_ledger_matches_landing(self):
        j = json.loads((REPO / "reports" / "r3_blindness.json").read_text())
        self.assertEqual(j["population"], 81)
        self.assertEqual(
            {k: v for k, v in j["lane_counts"].items()},
            {"L-A": 48, "L-B": 27, "L-C": 6},
        )


class TestWarmongerTripwire(SacrificeVocabulary):
    """The mis-lane guard: folding Warmonger's "sacrifice ANOTHER creature"
    cost would silently sacrifice a FORCED creature (wrong semantics —
    it is a genuine multi-candidate ask)."""

    def warmonger_cost(self) -> Selector:
        card = _record("M21", "Dire Fleet Warmonger")
        sacs = []

        def w(x):
            if isinstance(x, (list, tuple)):
                for y in x:
                    w(y)
                return
            if not (dataclasses.is_dataclass(x) and not isinstance(x, type)):
                return
            if isinstance(x, CostSacrifice):
                sacs.append(x.target)
                return
            for f in dataclasses.fields(x):
                w(getattr(x, f.name))

        w(card.abilities)
        self.assertEqual(len(sacs), 1)
        return sacs[0]

    def test_sacrifice_cost_stays_choose(self):
        sel = self.warmonger_cost()
        self.assertIs(sel.mode, SelectorMode.CHOOSE)
        self.assertTrue(
            any(
                isinstance(c, FNot) if c is not None else False
                for c in (getattr(sel.filter, "children", ()) or ())
            )
            or isinstance(sel.filter, FNot),
            "Warmonger cost filter must carry the negated IS_SOURCE",
        )

    def test_sacrifice_cost_ask_is_multi_candidate(self):
        sel = self.warmonger_cost()
        plan = self.plan_for(sel)
        # source alpha is excluded ("another"); the OTHER creatures pool
        # stays a DECISION: ask vocabulary == {gamma, delta}.
        opts = plan.sacrifice_options
        self.assertEqual(opts, ((tuple(sorted((self.gamma, self.delta))), 1),))
        asks = self.recorder(answer=str(self.delta))
        pay_costs(self.ex, plan, source=self.alpha, controller=self.p0)
        self.assertEqual(len(asks), 1)
        self.assertEqual(
            asks[0][1], tuple(str(h) for h in sorted((self.gamma, self.delta)))
        )
        self.assertEqual(self.world.zone_of(self.delta).kind, ZONE_GRAVEYARD)


class TestReKeyRoleLane(LegalityCase):
    """Executor re-key (spec §2(2)): the self-designation lane keys on
    {CHOOSE, ALL} — folded ALL nodes resolve to the source, while TARGET
    stays the designation lane (the FIX-1 quintet)."""

    def put_counter_atom(self, sel: Selector) -> Atom:
        return Atom(
            verb=Verb.PUT_COUNTER,
            args=__import__(
                "MTG_bot.core.ability_tree", fromlist=["AtomArgs"]
            ).AtomArgs(
                pairs=(
                    ("target", sel),
                    (
                        "counter_kind",
                        __import__(
                            "MTG_bot.core.ability_tree", fromlist=["CounterKind"]
                        ).CounterKind.PAGE,
                    ),
                    ("count", QConst(1)),
                )
            ),
        )

    def test_folded_all_self_designation_resolves_to_source(self):
        ctx = ctx_for(
            self.ex,
            source=self.alpha,
            controller=self.p0,
            bindings={"target": [self.beta]},
        )
        sel = Selector(QConst(1), SelectorMode.ALL, IS_SOURCE, zones=(BF_YOU,))
        self.assertEqual(
            role_handles(ctx, self.put_counter_atom(sel), "target"), [self.alpha]
        )

    def test_target_self_designation_stays_designation_lane(self):
        # FIX-1 guard: TARGET+IS_SOURCE keeps the binding-first convention
        # (the quintet's referent register; never a self-fold).
        ctx = ctx_for(
            self.ex,
            source=self.alpha,
            controller=self.p0,
            bindings={"target": [self.beta]},
        )
        sel = Selector(QConst(1), SelectorMode.TARGET, IS_SOURCE, zones=(BF_YOU,))
        self.assertEqual(
            role_handles(ctx, self.put_counter_atom(sel), "target"), [self.beta]
        )

    def test_all_mode_universal_stays_binding_first(self):
        ctx = ctx_for(
            self.ex,
            source=self.alpha,
            controller=self.p0,
            bindings={"target": [self.beta]},
        )
        sel = Selector(QConst(1), SelectorMode.ALL, UNIV, zones=(BF_YOU,))
        self.assertEqual(
            role_handles(ctx, self.put_counter_atom(sel), "target"), [self.beta]
        )


class TestQuintetFix1(unittest.TestCase):
    """FIX-1: TARGET+IS_SOURCE is a DESIGNATION (a real target that may be
    the source), never an engine-resolved singleton — it must survive the
    fold as TARGET, exactly the five measured cards."""

    def test_quintet_keeps_target_self_selectors(self):
        for name in QUINTET:
            card = _record("M21", name)
            sels = [
                s
                for s in selectors_of(card)
                if s.mode is SelectorMode.TARGET
                and _filter_is_self_referential(s.filter)
            ]
            self.assertTrue(sels, f"{name}: designation lane lost")

    def test_corpus_target_self_count_is_five(self):
        n = 0
        for set_name in ("M21", "ZNR"):
            pool = _pool(set_name)
            n += has_mode(
                pool,
                lambda s: (
                    s.mode is SelectorMode.TARGET
                    and _filter_is_self_referential(s.filter)
                ),
            )
        self.assertEqual(n, 5)

    def test_no_role_mixes_target_designation_and_folded_self(self):
        # A folded ALL-self node must never share a ROLE name with a
        # TARGET self-designation on the same card (hijack ambiguity).
        for set_name in ("M21", "ZNR"):
            pool = _pool(set_name)
            for _, r in pool.items():
                roles_t: set[str] = set()
                roles_a: set[str] = set()

                def scan(obj):
                    if isinstance(obj, (list, tuple)):
                        for y in obj:
                            scan(y)
                        return
                    if not (
                        dataclasses.is_dataclass(obj) and not isinstance(obj, type)
                    ):
                        return
                    pairs = getattr(getattr(obj, "args", None), "pairs", None)
                    if pairs:
                        for key, val in pairs:
                            if isinstance(val, Selector) and val.referent is None:
                                if (
                                    val.mode is SelectorMode.TARGET
                                    and _filter_is_self_referential(val.filter)
                                ):
                                    roles_t.add(key)
                                if (
                                    val.mode is SelectorMode.ALL
                                    and _filter_is_self_referential(val.filter)
                                ):
                                    roles_a.add(key)
                    for f in dataclasses.fields(obj):
                        scan(getattr(obj, f.name))

                scan(r.card.abilities)
                self.assertEqual(
                    roles_t & roles_a,
                    set(),
                    f"{r.card.name}: TARGET designation shares role {roles_t & roles_a} "
                    "with a folded ALL self-node",
                )


class TestEmptyLibrarySemantics(QueryCase):
    """The chosen empty-menu semantics (spec: ALL = take what exists):
    the pre-fold CHOOSE node gated the may-offer to skip on an empty
    library; the folded ALL node offers fire and resolves empty."""

    def may_top(self, mode: SelectorMode) -> OptionalEffect:
        return OptionalEffect(
            Seq(
                (
                    atom(
                        Verb.MOVE_ZONE,
                        cards=Selector(QConst(1), mode, UNIV, zones=LIB_YOU),
                        controller=ControllerRef.YOU,
                        **{"destination": GRAVE_YOU, "from": LIB_YOU},
                    ),
                )
            )
        )

    def offer(self, mode: SelectorMode):
        return optional_offer(
            self.ex, self.may_top(mode), source=self.a, controller=self.p0
        )

    def test_empty_library_choose_shape_gated_to_skip(self):
        # pre-fold shape (documents WHY the fold changes the gate outcome)
        self.world.move_all_library_to_graveyard if False else None
        self.assertEqual(self.offer(SelectorMode.CHOOSE), MAY_VOCAB[1:])

    def test_empty_library_folded_all_offers_fire(self):
        # folded shape: ALL is not an exact-count gate; fire resolves empty
        self.assertEqual(self.offer(SelectorMode.ALL), MAY_VOCAB)

    def test_real_card_with_cards_still_offers_both(self):
        self.world.add_card(
            __import__(
                "MTG_bot.core.test_executor_binding", fromlist=["card_id"]
            ).card_id("Top"),
            self.p0,
            ZONE_LIBRARY,
        )
        self.assertEqual(self.offer(SelectorMode.CHOOSE), MAY_VOCAB)
        self.assertEqual(self.offer(SelectorMode.ALL), MAY_VOCAB)


if __name__ == "__main__":
    unittest.main()
