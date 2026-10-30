"""Tests for the round-12c QUERY SURFACE (/06 §12c, executor/query.py).

Three handcrafted fixtures are the C15-contract examples (§1.4 Slate,
C15/C17 enumerations), and the golden-driven class compiles three REAL M21
cards (Llanowar Visionary {T}, Tormod's Crypt {T}+sac, Bloodfell Caves
{T} Choose-one) onto a handcrafted world with counts derived by hand:

(a) "up to two target creatures get -1/-1" — TARGET + QAtMost(2): the
    legal DESIGNATION sizes are {1, 2} — NEVER 0 (C17: still targeted);
(b) "You may discard a card: draw a card" — the may-offer is BOTH
    ("fire","skip") with a card in hand, narrowed to ("skip",) with an
    empty hand (CR 117.3: no resources — the offer stays enumerable);
(c) "Choose one — draw a card; gain 2 life" — exactly TWO options;
    QAtMost(1) on the same Choose admits the EMPTY option-set (sizes
    0..n) — the resolution-side zero the C17 TARGET pin forbids.
Every enumeration is Handle-sorted / index-lex (the §5.5 canonical
bijection), and queries are pure: two runs are equal and the world
fingerprint never moves under a query (P12).
"""

import itertools
import json
import unittest
from collections.abc import Sequence
from pathlib import Path

from MTG_bot.core.ability_tree import (
    ActivatedAbility,
    Atom,
    AtomArgs,
    CardRecord,
    Choose,
    ControllerRef,
    FAtom,
    FAtomPred,
    OptionalEffect,
    QAtLeast,
    QAtMost,
    QConst,
    QUnbounded,
    Selector,
    SelectorMode,
    Verb,
    Zone,
    ZoneKind,
    from_dict,
)
from MTG_bot.core.executor import Executor
from MTG_bot.core.executor.query import (
    MAY_VOCAB,
    choose_options,
    legal_activations,
    legal_targets,
    optional_offer,
    rest_of,
    validate_target_selection,
)
from MTG_bot.core.identity import CardIdentity, Handle
from MTG_bot.core.state import (
    ZONE_BATTLEFIELD,
    ZONE_EXILE,
    ZONE_GRAVEYARD,
    ZONE_HAND,
    ZONE_LIBRARY,
    GameWorld,
)
from MTG_bot.core.test_executor_binding import (
    BF_ANY,
    BF_YOU,
    HAND_YOU,
    LIB_YOU,
    UNIV,
    card_id,
    reset_oracle_ids,
)

_GOLDEN_DIR = Path(__file__).parent / "golden" / "M21"
_GOLDENS: dict[str, dict] = {}


def golden(name: str) -> dict:
    """The committed golden IR dict for a card name (PC-4 stable file)."""
    if not _GOLDENS:
        for path in _GOLDEN_DIR.glob("*.json"):
            d = json.loads(path.read_text(encoding="utf-8"))
            _GOLDENS[d["name"]] = d
    return _GOLDENS[name]


def record(name: str) -> CardRecord:
    return from_dict("CardRecord", golden(name))


CREATURE = FAtom(FAtomPred.TYPE_EQ, string_value="Creature")


def atom(verb: Verb, **roles) -> Atom:
    return Atom(verb=verb, args=AtomArgs(pairs=tuple(roles.items())))


def draw_one() -> Atom:
    return atom(
        Verb.MOVE_ZONE,
        cards=Selector(QConst(1), SelectorMode.ALL, UNIV, zones=(LIB_YOU,)),
        destination=Zone(ZoneKind.HAND, ControllerRef.YOU),
    )


def gain_two() -> Atom:
    return atom(Verb.GAIN_LIFE, controller=ControllerRef.YOU, amount=QConst(2))


class QueryCase(unittest.TestCase):
    """p0: creatures A<B<C + one noncreature; p1: one creature D."""

    def setUp(self):
        reset_oracle_ids()
        self.world = GameWorld(num_players=2, start_life=20, master_seed=29)
        self.p0, self.p1 = self.world.player_order[0], self.world.player_order[1]
        self.a = self.world.add_card(card_id("A", "1", "1"), self.p0, ZONE_BATTLEFIELD)
        self.b = self.world.add_card(card_id("B", "1", "1"), self.p0, ZONE_BATTLEFIELD)
        self.c = self.world.add_card(card_id("C", "1", "1"), self.p0, ZONE_BATTLEFIELD)
        self.d = self.world.add_card(card_id("D", "1", "1"), self.p1, ZONE_BATTLEFIELD)
        self.non = self.world.add_card(
            card_id("Urn", type_line="Artifact"), self.p0, ZONE_BATTLEFIELD
        )
        self.ex = Executor(self.world)

    def subsets(self, handles: Sequence, sizes) -> list[list]:
        out: list[list] = []
        for k in sizes:
            out.extend(list(h) for h in itertools.combinations(sorted(handles), k))
        return out


class TestUpToTwoTargets(QueryCase):
    """FIXTURE (a): 'up to two target creatures get -1/-1' — TARGET +
    QAtMost(2) designation legality (C17)."""

    def setUp(self):
        super().setUp()
        self.selector = Selector(QAtMost(2), SelectorMode.TARGET, CREATURE, zones=(BF_ANY,))
        self.slot = legal_targets(
            self.world, self.ex, self.selector, source=self.a, controller=self.p0
        )

    def test_candidates_are_all_creatures_in_handle_sort(self):
        # CONTROLLER/zone unrestricted + TYPE filter: D (opponent) counts,
        # the Urn does not. C15: the candidate list is EXACTLY this.
        self.assertEqual(
            self.slot.candidates, tuple(sorted([self.a, self.b, self.c, self.d]))
        )
        # re-pinned 2026-10-29: V15 makes "up to two" 0..2 (CR 601.2c, 115.6).
        self.assertEqual((self.slot.min_count, self.slot.max_count), (0, 2))
        self.assertFalse(self.slot.forced)

    def test_zone_and_controller_restrict_candidates(self):
        own = Selector(QAtMost(2), SelectorMode.TARGET, CREATURE, zones=(BF_YOU,))
        slot = legal_targets(
            self.world, self.ex, own, source=self.a, controller=self.p0
        )
        self.assertEqual(slot.candidates, tuple(sorted([self.a, self.b, self.c])))

    def test_legal_selections_are_sizes_one_and_two_never_zero(self):
        # re-pinned 2026-10-29: V15 changes the C17 pin. At DECLARATION the
        # range is 0..n (CR 601.2c, 115.6): the EMPTY selection is legal (the
        # spell is then not targeted), every size-{1,2} subset validates
        # (C(4,1)+C(4,2) = 10 completions), size 3 is over.
        legal = self.subsets(self.slot.candidates, (1, 2))
        self.assertEqual(len(legal), 10)
        for chosen in legal:
            self.assertIsNone(validate_target_selection(self.slot, chosen))
        self.assertIsNone(validate_target_selection(self.slot, []))
        reason = validate_target_selection(self.slot, [self.a, self.b, self.c])
        assert reason is not None
        self.assertIn("count_above_max", reason)

    def test_whole_legality_rejects_off_population_and_unsorted(self):
        reason = validate_target_selection(self.slot, [self.non])
        assert reason is not None
        self.assertIn("off_population", reason)
        reason = validate_target_selection(self.slot, [self.b, self.a])
        assert reason is not None
        self.assertIn("not_canonically_sorted", reason)  # §5.5
        reason = validate_target_selection(self.slot, [self.a, self.a])
        assert reason is not None
        self.assertIn("duplicate_handles", reason)

    def test_empty_population_slot_is_infeasible(self):
        self.selector = Selector(
            QAtMost(2),
            SelectorMode.TARGET,
            CREATURE,
            zones=(Zone(ZoneKind.EXILE, ControllerRef.ANY),),
        )
        slot = legal_targets(
            self.world, self.ex, self.selector, source=self.a, controller=self.p0
        )
        # re-pinned 2026-10-29: V15: an empty population is no longer
        # infeasible for "up to": zero targets is the one legal choice.
        self.assertEqual((slot.min_count, slot.max_count), (0, 0))
        self.assertIsNone(validate_target_selection(slot, []))


class TestMayOffer(QueryCase):
    """FIXTURE (b): 'You may discard a card: draw a card'."""

    def setUp(self):
        super().setUp()
        self.may = OptionalEffect(
            inner=__import__("MTG_bot.core.ability_tree", fromlist=["Seq"]).Seq(
                (
                    atom(
                        Verb.MOVE_ZONE,
                        cards=Selector(QConst(1), SelectorMode.CHOOSE, UNIV, zones=(HAND_YOU,)),
                        controller=ControllerRef.YOU,
                        **{
                            "destination": Zone(ZoneKind.GRAVEYARD, ControllerRef.YOU),
                            "from": HAND_YOU,
                        },
                    ),
                    draw_one(),
                )
            )
        )

    def offer(self):
        return optional_offer(self.ex, self.may, source=self.a, controller=self.p0)

    def test_discardable_hand_offers_both_ways(self):
        self.world.add_card(card_id("Fuel"), self.p0, ZONE_HAND)
        self.assertEqual(self.offer(), MAY_VOCAB)  # ("fire","skip") §1.2

    def test_empty_hand_narrows_the_offer_to_skip(self):
        # CR 117.3 — can't perform the action: the C15 enumeration stays
        # complete by SHRINKING, one legal option, never a fake branch.
        self.assertEqual(self.offer(), ("skip",))

    def test_firing_consumes_one_decision_and_runs_the_plan(self):
        fuel = self.world.add_card(card_id("Fuel"), self.p0, ZONE_HAND)
        lib = self.world.add_card(card_id("Top"), self.p0, ZONE_LIBRARY)
        # NO bindings: the 12a "cards" binding is tree-wide and would
        # hijack the draw atom too — here the CHOOSE discard designation
        # rides the deterministic 12a stand-in (the only hand card).
        events = self.ex.apply_effect(
            self.may,
            source=self.a,
            controller=self.p0,
            decisions=("fire",),
        )
        self.assertTrue(events)
        self.assertEqual(self.world.zone_of(fuel).kind, ZONE_GRAVEYARD)
        self.assertEqual(self.world.zone_of(lib).kind, ZONE_HAND)

    def test_skipping_moves_nothing(self):
        self.world.add_card(card_id("Fuel"), self.p0, ZONE_HAND)
        fp = self.world.fingerprint()
        self.ex.apply_effect(
            self.may, source=self.a, controller=self.p0, decisions=("skip",)
        )
        self.assertEqual(self.world.fingerprint(), fp)

    def test_offer_validates_only_optionals(self):
        with self.assertRaises(ValueError):
            optional_offer(
                self.ex,
                draw_one(),  # type: ignore[arg-type]
                source=self.a,
                controller=self.p0,
            )


class TestChooseOptions(QueryCase):
    """FIXTURE (c): 'Choose one — draw a card; gain 2 life' and the
    up-to variant — resolution-side enumeration cardinalities."""

    def choose(self, count, options):
        return Choose(count=count, options=options)

    def query(self, node):
        return choose_options(self.ex, node, source=self.a, controller=self.p0)

    def test_choose_one_two_options_exactly(self):
        node = self.choose(QConst(1), (draw_one(), gain_two()))
        opts = self.query(node)
        self.assertEqual([o.option_idxs for o in opts], [(0,), (1,)])
        # typed refs are the SAME IR objects the executor dispatches (§8.3)
        self.assertIs(opts[1].options[0], node.options[1])

    def test_up_to_one_choose_admits_the_empty_set(self):
        # CONTRAST the fixture-(a) C17 pin: resolution-time CHOOSE-side
        # up-to includes 0 .. n — the empty option-set IS a legal choice.
        node = self.choose(QAtMost(1), (draw_one(), gain_two()))
        opts = self.query(node)
        self.assertEqual([o.option_idxs for o in opts], [(), (0,), (1,)])

    def test_unbounded_and_exact_two_canonical_order(self):
        two = self.choose(QUnbounded(), (draw_one(), gain_two()))
        self.assertEqual(
            [o.option_idxs for o in self.query(two)], [(), (0,), (1,), (0, 1)]
        )  # sizes ascending then index-lex (§5.5 bijection)
        three = self.choose(QConst(2), (draw_one(), gain_two(), draw_one()))
        self.assertEqual(
            [o.option_idxs for o in self.query(three)], [(0, 1), (0, 2), (1, 2)]
        )

    def test_at_least_floor(self):
        node = self.choose(QAtLeast(2), (draw_one(), gain_two(), draw_one()))
        idxs = [o.option_idxs for o in self.query(node)]
        self.assertEqual(idxs, [(0, 1), (0, 2), (1, 2), (0, 1, 2)])


class TestSplitSelections(QueryCase):
    """ONE_OF / REST partition enumeration (12a map closed here, /06)."""

    def setUp(self):
        super().setUp()
        self.p1r = self.world.add_card(card_id("R1"), self.p0, ZONE_EXILE)
        self.p2r = self.world.add_card(card_id("R2"), self.p0, ZONE_EXILE)
        self.p3r = self.world.add_card(card_id("R3"), self.p0, ZONE_EXILE)
        self.exile = Zone(ZoneKind.EXILE, ControllerRef.YOU)

    def slot(self, mode, count):
        return legal_targets(
            self.world,
            self.ex,
            Selector(count, mode, UNIV, zones=(self.exile,)),
            source=self.a,
            controller=self.p0,
        )

    def test_one_of_exactly_one_rest_is_the_forced_complement(self):
        one = self.slot(SelectorMode.ONE_OF, QConst(1))
        self.assertEqual(one.candidates, tuple(sorted([self.p1r, self.p2r, self.p3r])))
        self.assertEqual((one.min_count, one.max_count), (1, 1))
        self.assertFalse(one.forced)  # the model still picks WHICH one
        rest = self.slot(SelectorMode.REST, QUnbounded())
        self.assertEqual((rest.min_count, rest.max_count, rest.forced), (3, 3, True))
        pick = one.candidates[0]
        self.assertEqual(rest_of(one, pick), tuple(sorted(one.candidates)[1:]))
        self.assertIsNone(validate_target_selection(one, [pick]))

    def test_all_is_forced_whole_population(self):
        slot = self.slot(SelectorMode.ALL, QUnbounded())
        self.assertEqual((slot.min_count, slot.max_count, slot.forced), (3, 3, True))

    def test_qat_least_target_one_or_more(self):
        # Sublime-Epiphany-class "one or more": designation sizes 1..n.
        slot = self.slot(SelectorMode.TARGET, QAtLeast(1))
        self.assertEqual((slot.min_count, slot.max_count), (1, 3))
        assert validate_target_selection(slot, []) is not None

    def test_choose_up_to_includes_zero_at_resolution(self):
        slot = self.slot(SelectorMode.CHOOSE, QConst(2))
        self.assertEqual((slot.min_count, slot.max_count), (0, 2))
        self.assertIsNone(validate_target_selection(slot, []))
        assert (
            validate_target_selection(slot, [self.p1r, self.p2r, self.p3r]) is not None
        )


class TestGoldenSurface(unittest.TestCase):
    """Three REAL M21 goldens on one handcrafted world; every count below
    was derived by hand from the printed card (the file cites the card,
    and the golden file pins the IR that produced the count)."""

    def setUp(self):
        reset_oracle_ids()
        self.world = GameWorld(num_players=2, start_life=20, master_seed=7)
        self.p0, self.p1 = self.world.player_order[0], self.world.player_order[1]
        self.visionary_rec = record("Llanowar Visionary")  # {T}: Add {G}
        self.crypt_rec = record(
            "Tormod's Crypt"
        )  # {T}, Sacrifice it: Exile all from target GY
        self.caves_rec = record("Bloodfell Caves")  # {T}: Choose one — {B} or {R}
        self.forest_rec = record("Forest")  # {T}: Add {G}
        self.visionary = self._put(self.visionary_rec, self.p0)
        self.crypt = self._put(self.crypt_rec, self.p0)
        self.caves = self._put(self.caves_rec, self.p0)
        self.opp_forest = self._put(self.forest_rec, self.p1)
        self.gy1 = self.world.add_card(card_id("Grave1"), self.p1, ZONE_GRAVEYARD)
        self.gy2 = self.world.add_card(card_id("Grave2"), self.p1, ZONE_GRAVEYARD)
        self.ex = Executor(self.world)
        for handle, rec in (
            (self.visionary, self.visionary_rec),
            (self.crypt, self.crypt_rec),
            (self.caves, self.caves_rec),
            (self.opp_forest, self.forest_rec),
        ):
            self.ex.attach_card(handle, rec)

    def _put(self, rec: CardRecord, seat: Handle) -> Handle:
        identity = CardIdentity(
            oracle_id=rec.oracle_id,
            name=rec.name,
            type_line=rec.type_line,
            cmc=rec.mana_value,
            colors=tuple(rec.colors),
        )
        return self.world.add_card(identity, seat, ZONE_BATTLEFIELD)

    # ---------------------------------------------------- legal_activations

    def test_three_pips_three_rows_handle_sorted(self):
        opts = legal_activations(self.world, self.ex, self.p0)
        # hand-derived from the goldens: Visionary idx1 (its ETB trigger is
        # idx0), Crypt idx0, Caves idx2 (EtBState + trigger occupy 0/1) —
        # three untapped permanents, one activation each; the opponent's
        # Forest is NOT on this seat's list.
        self.assertEqual(
            [(o.source, o.ability_idx) for o in opts],
            sorted(
                [
                    (self.visionary, 1),
                    (self.crypt, 0),
                    (self.caves, 2),
                ]
            ),
        )
        self.assertEqual(len(legal_activations(self.world, self.ex, self.p1)), 1)

    def test_payment_plans_are_the_typed_cost_fold(self):
        opts = {o.source: o for o in legal_activations(self.world, self.ex, self.p0)}
        v = opts[self.visionary]
        self.assertIsInstance(v.ability, ActivatedAbility)
        self.assertEqual(v.payment.tap, (self.visionary,))  # COST_TARGET: {T}
        self.assertEqual(v.payment.mana, ())  # PAYMENT: none — mana is the EFFECT
        self.assertTrue(v.payment.is_empty() is False)
        c = opts[self.crypt]
        self.assertEqual(c.payment.tap, (self.crypt,))
        self.assertEqual(c.payment.sacrifice, (self.crypt,))  # IS_SOURCE CHOOSE 1

    def test_tapped_caves_drops_out_of_the_slate(self):
        self.world.cards[self.caves].tapped = True
        sources = [o.source for o in legal_activations(self.world, self.ex, self.p0)]
        self.assertNotIn(self.caves, sources)
        self.assertEqual(len(sources), 2)

    # --------------------------------------------------------- choose-one

    def test_bloodfell_choose_exactly_two_options(self):
        # hand-derived from the golden: Choose(QConst(1), (Add {B}, Add {R}))
        # → EXACTLY 2 option-sets (the fixture-(c) count on a real card).
        ability = self.caves_rec.abilities[2]
        assert isinstance(ability, ActivatedAbility)
        node = ability.effect
        assert isinstance(node, Choose)
        self.assertEqual(node.count, QConst(1))
        opts = choose_options(self.ex, node, source=self.caves, controller=self.p0)
        self.assertEqual([o.option_idxs for o in opts], [(0,), (1,)])
        # executing a Slate answer = dispatching the chosen option subtree
        self.ex.apply_effect(opts[0].options[0], source=self.caves, controller=self.p0)
        self.assertEqual(self.world.players[self.p0].mana_pool.get("B"), 1)

    # ------------------------------------------------------- folded moves

    def test_activate_the_crypt_exiles_the_target_graveyard(self):
        # hand-derived: pay {T}+sacrifice-it (tap=(crypt), sac=(crypt)),
        # designate the two p1 graveyard cards as the TARGET: list →
        # both to p1's exile, the crypt in p0's graveyard.
        from MTG_bot.core.executor.events import KIND_TAP_STATE
        from MTG_bot.core.executor.legality import activate

        events_before = len(self.ex.events)
        activate(
            self.ex,
            self.crypt,
            0,
            seat=self.p0,
            targets=[self.gy2, self.gy1],  # activate sorts them (§5.5)
        )
        for gy_card in (self.gy1, self.gy2):
            zone = self.world.zone_of(gy_card)
            self.assertEqual(zone.kind, ZONE_EXILE)
            self.assertEqual(zone.controller, self.p1)
        self.assertEqual(self.world.zone_of(self.crypt).kind, ZONE_GRAVEYARD)
        # re-pinned 2026-10-29: V43 changes the flag the graveyard card carries. CR 110.5d: a
        # card off the battlefield is neither tapped nor untapped; the {T} payment is its row.
        self.assertFalse(self.world.cards[self.crypt].tapped)
        tap_rows = [r for r in self.ex.journal.dump() if r[1] == KIND_TAP_STATE and r[2] == str(self.crypt)]
        self.assertEqual([r[-1] for r in tap_rows], ["(True,)"])
        # costs are journalled: more executor events than we started with
        self.assertGreater(len(self.ex.events), events_before)

    def test_mana_activation_then_illegal_replay(self):
        from MTG_bot.core.executor.legality import activate

        activate(self.ex, self.visionary, 1, seat=self.p0)
        self.assertEqual(self.world.players[self.p0].mana_pool, {"G": 1})
        # second activation: {T} already spent — the slate row is gone
        self.assertNotIn(
            self.visionary,
            [o.source for o in legal_activations(self.world, self.ex, self.p0)],
        )
        with self.assertRaises(ValueError) as caught:
            activate(self.ex, self.visionary, 1, seat=self.p0)
        self.assertIn("source_tapped", str(caught.exception))

    # -------------------------------------------------------- determinism

    def test_queries_are_pure_and_repeatable(self):
        fp = self.world.fingerprint()
        first = legal_activations(self.world, self.ex, self.p0)
        second = legal_activations(self.world, self.ex, self.p0)
        self.assertEqual(first, second)  # replay determinism (P12)
        slot_a = legal_targets(
            self.world,
            self.ex,
            Selector(QAtMost(2), SelectorMode.TARGET, UNIV, zones=(BF_ANY,)),
            source=self.visionary,
            controller=self.p0,
        )
        slot_b = legal_targets(
            self.world,
            self.ex,
            Selector(QAtMost(2), SelectorMode.TARGET, UNIV, zones=(BF_ANY,)),
            source=self.visionary,
            controller=self.p0,
        )
        self.assertEqual(slot_a, slot_b)
        self.assertEqual(self.world.fingerprint(), fp)  # queries mutate nothing


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
