"""M21 engine-smoke fuzz fixes (reports/m21_engine_smoke_2026-10-19.md,
/109 addendum; KNOWLEDGE/2026-10-19 note). Three pinned signatures in
executor/quantity.py, one test class each:

S1  AssertionError@quantity.py:880 (_eval_atom HAS_COUNTER). Tempered
    Veteran's "put a +1/+1 counter on target creature WITH a +1/+1 counter
    on it" folds to FAtom(HAS_COUNTER, counter_kind=PLUS_1_PLUS_1,
    count=None) — _FATOM_RULES requires count but FAtom.__post_init__'s
    required-slot list omits "count", so the shape validates and reached
    the 12c query lane, where the raw assert killed the game (5 fuzz
    seeds). Fixed reading: unbound count = the existence reading ("with a
    K counter" ⇔ >= 1, NOT the vacuous 0-default phantom-counter trap);
    unbound counter_kind = typed named refusal.

S2  NotImplementedError@quantity.py:373 (QThisTurn NONCOMBAT_DAMAGE).
    Chandra's Incinerator's cost reducer resolves the turn ledger from
    the journal's DAMAGE rows: data ``(amount,)`` noncombat vs
    ``(amount, True)`` combat (the 16c scope flag), subject = the actual
    recipient (a planeswalker row is NOT damage to an opponent, CR 118.5).

S3  ValueError@quantity.py:417 (_prop_value POWER on card:61 = Kinetic
    Augur, printed P/T "*4" → compiled undefined, the /99 shape-gap
    family) read by Carrion Grub's static "greatest power among creature
    cards in your graveyard" (QProp POWER MAX over a selector). Fixed
    reading: an undefined characteristic is skipped by SELECTOR
    AGGREGATIONS (characteristic absent = not a member of the value set —
    the POWER_LE/GE convention); the SCALAR read keeps the strict raise.
"""

import unittest
from pathlib import Path

from MTG_bot.core.ability_tree import (
    ActivatedAbility,
    Atom,
    ControllerRef,
    CostDeltaReduceGeneric,
    CostModifier,
    CounterKind,
    FAnd,
    FAtom,
    FAtomPred,
    QAgg,
    QConst,
    QProp,
    QPropField,
    QThisTurn,
    Selector,
    SelectorMode,
    ThisTurnKind,
    Zone,
    ZoneKind,
)
from MTG_bot.core.compiler.compiler import compile_card
from MTG_bot.core.compiler.coverage import build_full_registry
from MTG_bot.core.compiler.ingest import ingest_pool
from MTG_bot.core.executor.events import KIND_DAMAGE
from MTG_bot.core.executor.quantity import _eval_atom, eval_filter, resolve
from MTG_bot.core.state import ZONE_BATTLEFIELD, ZONE_GRAVEYARD
from MTG_bot.core.test_executor_binding import (
    CREATURE,
    BindingCase,
    card_id,
)

_M21_PATH = Path(__file__).resolve().parents[1] / "data" / "M21.json"
_POOL_CACHE: dict = {}


def _compiled(name: str):
    """Compile one M21 card by printed name through the compiler's public
    entry (compile_card) — the SAME pipeline the supply harness runs."""
    if "pool" not in _POOL_CACHE:
        _POOL_CACHE["pool"] = ingest_pool(_M21_PATH)
        _POOL_CACHE["registry"] = build_full_registry()
    pool, registry = _POOL_CACHE["pool"], _POOL_CACHE["registry"]
    for raw in pool.values():
        if raw.identity.name == name:
            return compile_card(raw, registry).card
    raise AssertionError(f"{name!r} not in the M21 pool")


def _has_counter_atoms(card) -> list[FAtom]:
    found = []

    def walk(node):
        if isinstance(node, FAtom):
            if node.pred is FAtomPred.HAS_COUNTER:
                found.append(node)
        elif isinstance(node, FAnd):
            for child in node.children:
                walk(child)

    def walk_effect(effect):
        if isinstance(effect, Atom):
            for _role, value in effect.args.pairs:
                if isinstance(value, Selector):
                    walk(value.filter)
                if isinstance(value, (FAtom, FAnd)):
                    walk(value)

    for ability in card.abilities:
        if isinstance(ability, ActivatedAbility) and ability.effect is not None:
            walk_effect(ability.effect)
    return found


class TemperedVeteranShapeTest(BindingCase):
    """S1: the compiled atom shape + the existence-count eval lane."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.card = _compiled("Tempered Veteran")
        cls.atoms = _has_counter_atoms(cls.card)

    def _counter_filter(self):
        self.assertTrue(self.atoms, "the fold lost its HAS_COUNTER filter atom")
        # The fuzz-repro shape: the atom arrives with count UNBOUND.
        self.assertTrue(
            any(a.count is None for a in self.atoms),
            "no unbound-count HAS_COUNTER atom — the fold changed; re-audit S1",
        )
        unbound = next(a for a in self.atoms if a.count is None)
        for ability in self.card.abilities:
            if not isinstance(ability, ActivatedAbility) or ability.effect is None:
                continue
            effect = ability.effect
            if not isinstance(effect, Atom):
                continue
            for _role, value in effect.args.pairs:
                if not isinstance(value, Selector):
                    continue
                filter_ = value.filter
                if isinstance(filter_, FAnd) and unbound in filter_.children:
                    return filter_
        raise AssertionError("unbound HAS_COUNTER atom is not a target filter")

    def test_unbound_count_is_existence_not_phantom(self):
        """The exact fuzz filter (FAnd(TYPE_EQ Creature, HAS_COUNTER[K,
        count=None])): True iff the creature carries at least ONE K
        counter — never the vacuous threshold-0 reading."""
        ctx = self.ex._ctx(
            source=self.watch, controller=self.p0, bindings={}, decisions=()
        )
        filter_ = self._counter_filter()
        with_counter = self.world.add_card(
            card_id("Carrier", "1", "1"), self.p0, ZONE_BATTLEFIELD
        )
        without = self.world.add_card(
            card_id("Bare", "1", "1"), self.p0, ZONE_BATTLEFIELD
        )
        self.world.cards[with_counter].counters[CounterKind.PLUS_1_PLUS_1.name] = 1
        self.assertTrue(eval_filter(filter_, with_counter, ctx))
        self.assertFalse(
            eval_filter(filter_, without, ctx),
            "phantom-counter trap: the count-less atom must NOT pass a "
            "counter-less creature (that is the zero-default the assert hid)",
        )

    def test_wrong_kind_does_not_count(self):
        """Existence is per-kind: an ice counter is not 'a +1/+1 counter'."""
        ctx = self.ex._ctx(
            source=self.watch, controller=self.p0, bindings={}, decisions=()
        )
        filter_ = self._counter_filter()
        iced = self.world.add_card(card_id("Iced", "1", "1"), self.p0, ZONE_BATTLEFIELD)
        self.world.cards[iced].counters[CounterKind.MINUS_1_MINUS_1.name] = 2
        self.assertFalse(eval_filter(filter_, iced, ctx))

    def test_hand_built_unbound_count_matches_compiled_atom(self):
        """Unit-level twin: the hand-built atom shape == the compiled one
        (both lanes share the one evaluator — parity)."""
        ctx = self.ex._ctx(
            source=self.watch, controller=self.p0, bindings={}, decisions=()
        )
        atom = FAtom(pred=FAtomPred.HAS_COUNTER, counter_kind=CounterKind.PLUS_1_PLUS_1)
        carrier = self.world.add_card(
            card_id("C2", "1", "1"), self.p0, ZONE_BATTLEFIELD
        )
        self.world.cards[carrier].counters[CounterKind.PLUS_1_PLUS_1.name] = 1
        self.assertTrue(_eval_atom(atom, carrier, ctx))
        self.assertFalse(_eval_atom(atom, self.watch, ctx))

    def test_bound_count_still_resolves_through_the_quantity_lane(self):
        """A BOUND threshold keeps the ordinary resolve path (>= N)."""
        ctx = self.ex._ctx(
            source=self.watch, controller=self.p0, bindings={}, decisions=()
        )
        atom = FAtom(
            pred=FAtomPred.HAS_COUNTER,
            counter_kind=CounterKind.PLUS_1_PLUS_1,
            count=QConst(2),
        )
        one = self.world.add_card(card_id("One", "1", "1"), self.p0, ZONE_BATTLEFIELD)
        self.world.cards[one].counters[CounterKind.PLUS_1_PLUS_1.name] = 1
        self.assertFalse(_eval_atom(atom, one, ctx))
        self.world.cards[one].counters[CounterKind.PLUS_1_PLUS_1.name] = 2
        self.assertTrue(_eval_atom(atom, one, ctx))

    def test_unbound_kind_is_a_typed_named_refusal(self):
        """counter_kind None is inanswerable ('a counter' — WHICH one?):
        NotImplementedError naming the slot, never the old AssertionError
        and never a any-kind zero reading. (The grammar enforces this slot
        on real FAtoms, so the stand-in atom pins the defensive branch.)"""
        ctx = self.ex._ctx(
            source=self.watch, controller=self.p0, bindings={}, decisions=()
        )
        # Build the grammar-illegal shape BEYOND __post_init__ (the slot
        # is enforced on real FAtoms — this pins the defensive branch):
        stand_in = FAtom.__new__(FAtom)
        object.__setattr__(stand_in, "pred", FAtomPred.HAS_COUNTER)
        object.__setattr__(stand_in, "counter_kind", None)
        object.__setattr__(stand_in, "count", None)
        with self.assertRaises(NotImplementedError) as caught:
            _eval_atom(stand_in, self.watch, ctx)
        self.assertIn("counter_kind", str(caught.exception))

    def test_non_card_handle_is_characteristic_absent(self):
        """A player seat has no counters (the KEYWORD_HAS absent-absent
        convention), instead of the KeyError the bare dict read gave."""
        ctx = self.ex._ctx(
            source=self.watch, controller=self.p0, bindings={}, decisions=()
        )
        atom = FAtom(pred=FAtomPred.HAS_COUNTER, counter_kind=CounterKind.PLUS_1_PLUS_1)
        self.assertFalse(_eval_atom(atom, self.p1, ctx))


class ThisTurnNoncombatDamageTest(BindingCase):
    """S2: QThisTurn(NONCOMBAT_DAMAGE) over the journalled DAMAGE feed."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.incinerator = _compiled("Chandra's Incinerator")

    def _qty(self, referent=ControllerRef.ALL_OPPONENTS):
        return QThisTurn(kind=ThisTurnKind.NONCOMBAT_DAMAGE, referent=referent)

    def _ctx(self):
        return self.ex._ctx(
            source=self.watch, controller=self.p0, bindings={}, decisions=()
        )

    def test_compiled_cost_reducer_shape(self):
        """The fuzz-repro quantity, pinned at unit level: Chandra's
        Incinerator folds the cost reducer to exactly QThisTurn(
        NONCOMBAT_DAMAGE, ALL_OPPONENTS)."""
        amounts = [
            ab.delta.amount
            for ab in self.incinerator.abilities
            if isinstance(ab, CostModifier)
            and isinstance(ab.delta, CostDeltaReduceGeneric)
        ]
        self.assertTrue(amounts, "the cost-reducer fold is gone")
        self.assertIn(self._qty(), amounts)

    def test_sum_scopes_noncombat_and_opponent_seats(self):
        ctx = self._ctx()
        walker = self.world.add_card(
            card_id("Walker", type_line="Planeswalker"), self.p1, ZONE_BATTLEFIELD
        )
        jrn = self.ex.journal
        jrn.emit(KIND_DAMAGE, self.p1, self.watch, "DAMAGE", (3,))  # count
        jrn.emit(KIND_DAMAGE, self.p1, self.watch, "DAMAGE", (2,))  # count
        jrn.emit(KIND_DAMAGE, self.p1, self.watch, "DAMAGE", (5, True))  # combat
        jrn.emit(KIND_DAMAGE, self.p0, self.watch, "DAMAGE", (4,))  # own seat
        jrn.emit(KIND_DAMAGE, walker, self.watch, "DAMAGE", (7,))  # CR 118.5
        self.assertEqual(resolve(self._qty(), ctx), 5)
        # referent YOU: only the row seated on the controller answers.
        self.assertEqual(resolve(self._qty(ControllerRef.YOU), ctx), 4)

    def test_empty_history_is_zero_not_a_refusal(self):
        """The quantity IS resolvable this turn — nothing happened, so 0
        (the cost reducer honestly reads no reduction)."""
        self.assertEqual(resolve(self._qty(), self._ctx()), 0)

    def test_bare_ctx_refuses_by_name(self):
        ctx = self._ctx()
        ctx.journal = None
        with self.assertRaises(NotImplementedError) as caught:
            resolve(self._qty(), ctx)
        self.assertIn("journal", str(caught.exception))

    def test_other_turn_kinds_stay_flagged(self):
        qty = QThisTurn(kind=ThisTurnKind.LIFE_GAINED, referent=ControllerRef.YOU)
        with self.assertRaises(NotImplementedError) as caught:
            resolve(qty, self._ctx())
        self.assertIn("LIFE_GAINED", str(caught.exception))


class UndefinedPowerAggregationTest(BindingCase):
    """S3: QProp(POWER/TOUGHNESS) over a selector skips undefined-P/T
    objects; the scalar read keeps its strict raise."""

    def _ctx(self):
        return self.ex._ctx(
            source=self.watch, controller=self.p0, bindings={}, decisions=()
        )

    def _gy_sel(self):
        return Selector(
            QConst(9),
            SelectorMode.ALL,
            CREATURE,
            zones=(Zone(ZoneKind.GRAVEYARD, ControllerRef.YOU),),
        )

    def _populate(self):
        """Kinetic Augur's exact world shape: a creature card whose printed
        power is undefined (identity power None — the '*' / /99 shape gap)
        beside a printed 2/2, both in p0's graveyard."""
        star = self.world.add_card(card_id("Star", None, "4"), self.p0)
        brawler = self.world.add_card(card_id("Brawler", "2", "2"), self.p0)
        self.world.move_to_zone(star, self.p0, ZONE_GRAVEYARD)
        self.world.move_to_zone(brawler, self.p0, ZONE_GRAVEYARD)
        return star, brawler

    def _qty(self, field, agg):
        return QProp(referent=self._gy_sel(), field=field, agg=agg)

    def test_max_skips_the_undefined_power(self):
        self._populate()
        self.assertEqual(resolve(self._qty(QPropField.POWER, QAgg.MAX), self._ctx()), 2)

    def test_sum_skips_the_undefined_power(self):
        self._populate()
        # brawler 2 + (star: undefined, skipped) — NOT a zero-guess about
        # the Augur's unmodelled CDA.
        self.assertEqual(resolve(self._qty(QPropField.POWER, QAgg.SUM), self._ctx()), 2)

    def test_toughness_defined_everywhere_still_sums(self):
        self._populate()
        self.assertEqual(
            resolve(self._qty(QPropField.TOUGHNESS, QAgg.SUM), self._ctx()), 6
        )

    def test_all_undefined_aggregates_to_the_empty_set_zero(self):
        star = self.world.add_card(card_id("Star2", None, "4"), self.p0)
        self.world.move_to_zone(star, self.p0, ZONE_GRAVEYARD)
        self.assertEqual(resolve(self._qty(QPropField.POWER, QAgg.MAX), self._ctx()), 0)

    def test_scalar_undefined_power_still_raises_strictly(self):
        """The S3 fix is aggregation-scoped: a SCALAR read of an
        undefined power remains the named ValueError (unresolvable
        quantity — CR: no power, not power zero)."""
        star = self.world.add_card(card_id("Star3", None, "4"), self.p0)
        ctx = self.ex._ctx(source=star, controller=self.p0, bindings={}, decisions=())
        with self.assertRaises(ValueError) as caught:
            resolve(QProp(referent="source", field=QPropField.POWER), ctx)
        self.assertIn("POWER undefined", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
