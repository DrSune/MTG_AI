"""Bucket B8 (party family) — ZND-3 verification (spec /107 gates).

Sections:

1. Registry shape: 23 templates, unique tids, bucket "B8".
2. VERBATIM law: every one of the 35 clearing rows fullmatches EXACTLY
   ONE b8 template and builds; the three named-defer rows match NOTHING
   in b8 and NOTHING in the full registry (the register stays honest).
3. Evaluator pins (spec /107 gates): two-Clerics-one-Wizard = 2 (the
   at-most-one-each law); classless creatures = 0; opponent creatures
   never count (direction); the GRANT_TYPE overlay MOVES the census
   (§11 golden); the full-party FAnd is false at 3 classes / true at 4.
4. The discount PRICE is visible on legal_casts (§10 menu-visibility):
   {4}{B} with party 2 prices at 2G+1B; the boundary falsifies both the
   always-full-price and the always-discounted encodings.
5. The QPartyCount node's grammar registration (union + tags + specs).
"""

from __future__ import annotations

import itertools
import unittest

from MTG_bot.core.ability_tree import (
    Atom,
    AtomArgs,
    CardRecord,
    ControllerRef,
    Cost,
    CostManaColor,
    CostManaGeneric,
    FAnd,
    FAtom,
    FAtomPred,
    QConst,
    Quantity,
    SelectorMode,
    SpellKind,
    Verb,
    ZoneKind,
)
from MTG_bot.core.ability_tree import (
    QPartyCount as AT_QPartyCount,
)
from MTG_bot.core.compiler.coverage import build_full_registry
from MTG_bot.core.compiler.ingest import CardIdentity
from MTG_bot.core.compiler.templates import AbilityOutcome
from MTG_bot.core.compiler.templates_b8 import (
    TEMPLATES,
    _full_party,
    _party_count,
)
from MTG_bot.core.executor import Executor
from MTG_bot.core.executor.legality import ctx_for
from MTG_bot.core.executor.quantity import eval_filter, resolve
from MTG_bot.core.executor.query import legal_casts
from MTG_bot.core.state import ZONE_BATTLEFIELD, ZONE_HAND, GameWorld
from MTG_bot.core.test_executor_stack import spell_rec

_ORACLE_SEQ = itertools.count(2_500)


def _build(text: str):
    """Fullmatch ``text`` against the b8 templates (asserting exactly one
    hit) and run the builder."""
    hits = [t for t in TEMPLATES if t.pattern.fullmatch(text)]
    assert len(hits) == 1, f"{len(hits)} b8 matches for {text[:70]!r}"
    match = hits[0].pattern.fullmatch(text)
    assert match is not None
    return hits[0], hits[0].build(match)


# ---------------------------------------------------------------------------
# The 35 clearing rows (verbatim from reports/grammar_2026-10-19_ZNR.json,
# attribution /tmp/opencode/znd3_attribution.json) + the 3 named defers.
# ---------------------------------------------------------------------------

_CLEAR_ROWS: tuple[str, ...] = (
    # T1 (11 rows; 10 identical spell rows + 1 ability row)
    *(
        "This spell costs {1} less to cast for each creature in your party."
        for _ in range(10)
    ),
    "This ability costs {1} less to activate for each creature in your party.",
    # T2 (8)
    "When this creature enters, create a 1/1 white Kor Warrior creature token for each creature in your party.",
    "When this creature enters, put a +1/+1 counter on it for each creature in your party.",
    "Whenever this creature attacks, it gets +1/+0 until end of turn for each creature in your party.",
    "When this creature enters, add {R} for each creature in your party.",
    "Practiced Tactics deals damage to that creature equal to twice the number of creatures in your party.",
    "When this creature enters, target creature gets +1/+1 until end of turn for each creature in your party.",
    "When this creature enters, you gain 2 life for each creature in your party.",
    "Put a +1/+1 counter on it for each creature in your party.",
    # T3 (5)
    "At the beginning of combat on your turn, if you have a full party, creatures you control get +1/+0 and gain indestructible until end of turn.",
    "If you have a full party, you may cast a spell with mana value 4 or less from your hand without paying its mana cost.",
    "At the beginning of combat on your turn, if you have a full party, target creature gets +1/+1 and gains flying until end of turn.",
    "At the beginning of combat on your turn, if you have a full party, choose target nonland permanent an opponent controls.",
    'At the beginning of combat on your turn, if you have a full party, creatures you control gain "Whenever this creature deals combat damage to a player, draw a card" until end of turn.',
    # T4 (7)
    "When this creature enters, scry X, where X is the number of creatures in your party.",
    "Up to two target creatures each get +X/+X until end of turn, where X is the number of creatures in your party.",
    "When this creature enters, each opponent loses X life and you gain X life, where X is the number of creatures in your party.",
    "When this creature enters, target creature an opponent controls gets -X/-X until end of turn, where X is the number of creatures in your party.",
    "When this creature enters, it deals X damage to target creature or planeswalker, where X is the number of creatures in your party.",
    "Synchronized Spellcraft deals 4 damage to target creature and X damage to that creature's controller, where X is the number of creatures in your party.",
    "Look at the top X cards of your library, where X is three plus the number of creatures in your party.",
    # T5 (3)
    "Stonework Packbeast is also a Cleric, Rogue, Warrior, and Wizard.",
    "Tajuru Paragon is also a Cleric, Rogue, Warrior, and Wizard.",
    "Veteran Adventurer is also a Cleric, Rogue, Warrior, and Wizard.",
    # T6 (1)
    "When this creature enters, target opponent reveals a number of cards from their hand equal to the number of creatures in your party.",
)

_DEFER_ROWS = (
    "Counter target noncreature spell unless its controller pays {1} plus an additional {1} for each creature in your party.",
    "Archpriest of Iona's power is equal to the number of creatures in your party.",
    "Equipped creature gets +1/+0 for each creature in your party and has menace.",
)


class TestB8Registry(unittest.TestCase):
    def test_registry_shape(self) -> None:
        self.assertEqual(len(TEMPLATES), 23)
        self.assertEqual(len({t.tid for t in TEMPLATES}), 23)
        for t in TEMPLATES:
            self.assertEqual(t.bucket, "B8")
            self.assertEqual(t.priority, 114)

    def test_registered_in_full_registry(self) -> None:
        full = build_full_registry()
        tids = {t.tid for t in full.all()}
        self.assertTrue({t.tid for t in TEMPLATES} <= tids)


class TestB8VerbatimRows(unittest.TestCase):
    def test_every_clearing_row_matches_one_template(self) -> None:
        self.assertEqual(len(_CLEAR_ROWS), 35)
        for text in _CLEAR_ROWS:
            tid, outcome = _build(text)
            self.assertIsNotNone(outcome, tid)

    def test_defer_rows_match_nothing(self) -> None:
        full = build_full_registry()
        for text in _DEFER_ROWS:
            self.assertEqual(
                [t.tid for t in TEMPLATES if t.pattern.fullmatch(text)], []
            )
            self.assertEqual(
                [t.tid for t in full.all() if t.pattern.fullmatch(text)],
                [],
                f"defer row was swept by another bucket: {text[:60]!r}",
            )

    def test_templates_are_pairwise_disjoint(self) -> None:
        # PC-3 convention on the b8 clearing set: no row matches two.
        for text in set(_CLEAR_ROWS):
            hits = [t.tid for t in TEMPLATES if t.pattern.fullmatch(text)]
            self.assertEqual(len(hits), 1, (text[:60], hits))


# ---------------------------------------------------------------------------
# Evaluator harness (b7 section-6 convention: GameWorld + Executor +
# attach_card, judging the LIVE census, not the pattern).
# ---------------------------------------------------------------------------


def _card_id(name: str, type_line: str) -> CardIdentity:
    n = next(_ORACLE_SEQ)
    return CardIdentity(
        oracle_id=f"{n:08x}-aaaa-bbbb-cccc-888888888888",
        name=name,
        type_line=type_line,
        power="2" if "Creature" in type_line else None,
        toughness="2" if "Creature" in type_line else None,
        cmc=2,
        colors=(),
    )


def _record_of(name: str, oid: str, type_line: str, abilities=()) -> CardRecord:
    return CardRecord(
        oracle_id=oid,
        name=name,
        type_line=type_line,
        types=tuple(w for w in type_line.split(" — ")[0].split()),
        subtypes=tuple(type_line.split(" — ")[1].split()) if " — " in type_line else (),
        supertypes=(),
        colors=(),
        color_identity=frozenset(),
        mana_cost=None,
        mana_value=2,
        power=QConst(2),
        toughness=QConst(2),
        loyalty=None,
        keywords=(),
        abilities=tuple(abilities),
        is_token=False,
    )


class PartyCase(unittest.TestCase):
    def setUp(self) -> None:
        self.world = GameWorld(num_players=2, start_life=20, master_seed=17)
        self.p0, self.p1 = self.world.player_order[0], self.world.player_order[1]
        self.ex = Executor(self.world)

    def place(self, name: str, seat, type_line: str, abilities=()):
        cid = _card_id(name, type_line)
        handle = self.world.add_card(cid, seat, ZONE_BATTLEFIELD)
        self.ex.attach_card(
            handle, _record_of(name, cid.oracle_id, type_line, abilities)
        )
        return handle

    def settle(self) -> None:
        self.ex.layers.recompute()

    def party(self, source_seat_player, source=None):
        ctx = ctx_for(
            self.ex,
            source=source or self.world.player_order[0],
            controller=source_seat_player,
        )
        return resolve(_party_count(), ctx)

    def full_party(self, source) -> bool:
        ctx = ctx_for(self.ex, source=source, controller=self.p0)
        return eval_filter(_full_party(), source, ctx)


class TestPartyCensus(PartyCase):
    def test_two_clerics_one_wizard_is_two(self) -> None:
        """The at-most-one-each law (ZNR reminder text): distinct classes,
        never a creature count."""
        self.place("Cleric A", self.p0, "Creature — Human Cleric")
        self.place("Cleric B", self.p0, "Creature — Cleric")
        self.place("Wizard", self.p0, "Creature — Human Wizard")
        self.settle()
        self.assertEqual(self.party(self.p0), 2)

    def test_classless_and_token_shapes_contribute_zero(self) -> None:
        self.place("Vanilla", self.p0, "Creature")
        self.place("Beast", self.p0, "Creature — Beast")
        self.settle()
        self.assertEqual(self.party(self.p0), 0)

    def test_opponent_creatures_never_count(self) -> None:
        """Direction (E1 single encoding): the population selector pins
        CONTROLLER_IS YOU; the opponent's full party is not my party."""
        self.place("Foe Cleric", self.p1, "Creature — Cleric")
        self.place("Foe Rogue", self.p1, "Creature — Rogue")
        self.settle()
        self.assertEqual(self.party(self.p0), 0)
        # ... and YOU only get what YOU have:
        self.place("My Wizard", self.p0, "Creature — Wizard")
        self.settle()
        self.assertEqual(self.party(self.p0), 1)

    def test_class_grant_moves_the_census(self) -> None:
        """§11 golden (spec /107 T5): the compiled class signature MOVES
        the census for every consumer through the layers overlay — the
        granted card's identity type line is NEVER rewritten."""
        # Board: one Cleric => party 1.
        cleric = self.place("Cleric", self.p0, "Creature — Human Cleric")
        self.settle()
        self.assertEqual(self.party(self.p0, source=cleric), 1)
        # Tajuru Paragon enters with the COMPILED T5 static.
        _, outcome = _build(
            "Tajuru Paragon is also a Cleric, Rogue, Warrior, and Wizard."
        )
        assert isinstance(outcome, AbilityOutcome)
        paragon = self.place(
            "Tajuru Paragon",
            self.p0,
            "Creature — Elf Warrior",
            abilities=(outcome.ability,),
        )
        self.settle()
        # Overlay: Paragon now carries all four classes => party 4.
        self.assertEqual(self.party(self.p0, source=paragon), 4)
        # The identity type line is untouched (board-separation law).
        self.assertEqual(
            self.world.cards[paragon].identity.type_line, "Creature — Elf Warrior"
        )
        # Full-party now TRUE at four classes (spec gate, same board):
        self.assertTrue(self.full_party(paragon))

    def test_full_party_false_at_three_true_at_four(self) -> None:
        a = self.place("C", self.p0, "Creature — Cleric")
        self.place("R", self.p0, "Creature — Rogue")
        self.place("W", self.p0, "Creature — Warrior")
        self.settle()
        self.assertFalse(self.full_party(a))
        d = self.place("Wz", self.p0, "Creature — Wizard")
        self.settle()
        self.assertTrue(self.full_party(d))

    def test_census_is_board_live(self) -> None:
        """The quantity resolves at every read — no frozen bake (the r22c
        shrine-count lesson): dropping a class from the board lowers the
        party between two resolves."""
        cleric = self.place("Cleric", self.p0, "Creature — Cleric")
        wizard = self.place("Wizard", self.p0, "Creature — Wizard")
        self.settle()
        self.assertEqual(self.party(self.p0, source=cleric), 2)
        self.world.move_to_zone(wizard, self.p0, "graveyard")
        self.assertEqual(self.party(self.p0, source=cleric), 1)


# ---------------------------------------------------------------------------
# Discount price visible on legal_casts (spec /107 §10 gate)
# ---------------------------------------------------------------------------


class TestDiscountPrice(unittest.TestCase):
    def setUp(self) -> None:
        self.world = GameWorld(num_players=2, start_life=20, master_seed=23)
        self.p0 = self.world.player_order[0]
        self.ex = Executor(self.world)
        self.ex.begin_turn(self.p0)
        _, outcome = _build(
            "This spell costs {1} less to cast for each creature in your party."
        )
        assert isinstance(outcome, AbilityOutcome)
        self.discount = outcome.ability
        rec = spell_rec(
            "Prize",
            SpellKind.INSTANT,
            cost=Cost(
                parts=(CostManaGeneric(QConst(4)), CostManaColor("B", QConst(1)))
            ),
            effect=Atom(
                verb=Verb.GAIN_LIFE,
                args=AtomArgs(
                    pairs=(
                        ("controller", ControllerRef.YOU),
                        ("amount", QConst(1)),
                    )
                ),
            ),
            extra_abilities=(self.discount,),
        )
        self.spell = self.world.add_card(
            CardIdentity(
                oracle_id=rec.oracle_id,
                name="Prize",
                type_line=rec.type_line,
                cmc=5,
            ),
            self.p0,
            ZONE_HAND,
        )
        self.ex.attach_card(self.spell, rec)

    def mana(self, **keys):
        pool = self.world.players[self.p0].mana_pool
        for key, amount in keys.items():
            pool[key] = pool.get(key, 0) + amount

    def _row(self):
        return next(
            (
                o
                for o in legal_casts(self.world, self.ex, self.p0)
                if o.handle == self.spell
            ),
            None,
        )

    def test_price_folds_the_party_census(self) -> None:
        """Party of two: {4}{B} PRICES as 2 generic + 1 black on the
        legal_casts surface (menu-visibility law: the ask shows the real
        total, 601.2f)."""
        self.place_party_members()
        self.mana(G=2, B=1)
        row = self._row()
        self.assertIsNotNone(row, "discounted row must be enumerable at 2G+1B")
        assert row is not None and row.payment is not None
        self.assertEqual(dict(row.payment.mana), {"G": 2, "B": 1})

    def test_boundary_falsifies_both_wrong_encodings(self) -> None:
        """Without the party the row needs FULL price: the identical
        2G+1B pool disappears the row (always-discounted encoding would
        still enumerate; always-full-price would fail BOTH legs)."""
        self.mana(G=2, B=1)
        self.assertIsNone(self._row())
        self.mana(G=2)  # now the full 4G+1B is available
        row = self._row()
        self.assertIsNotNone(row)
        assert row is not None and row.payment is not None
        self.assertEqual(dict(row.payment.mana), {"G": 4, "B": 1})

    def place_party_members(self) -> None:
        """A Cleric and a Wizard: the census is a DISTINCT-CLASS union, so
        two creatures of different classes make party 2 (two Clerics would
        be party 1)."""
        for i, cls in enumerate(("Cleric", "Wizard")):
            cid = _card_id(f"{cls} {i}", f"Creature — {cls}")
            h = self.world.add_card(cid, self.p0, ZONE_BATTLEFIELD)
            self.ex.attach_card(
                h, _record_of(f"{cls} {i}", cid.oracle_id, f"Creature — {cls}")
            )
        self.ex.layers.recompute()


# ---------------------------------------------------------------------------
# G1: the QPartyCount node's grammar registration
# ---------------------------------------------------------------------------


class TestQPartyCountNode(unittest.TestCase):
    def test_node_is_a_quantity(self) -> None:
        q = _party_count()
        self.assertIsInstance(q, AT_QPartyCount)
        self.assertIsInstance(q, Quantity)
        self.assertEqual(q.selector.mode, SelectorMode.ALL)
        self.assertEqual(q.selector.zone.kind, ZoneKind.BATTLEFIELD)

    def test_selector_axis_is_the_pinned_population(self) -> None:
        """Spec /107 §3.1: TYPE_EQ Creature ∧ CONTROLLER_IS YOU ∧
        battlefield — the population axis ONLY (the census is the
        evaluator's)."""
        filt = _party_count().selector.filter
        assert isinstance(filt, FAnd)
        preds = [c.pred for c in filt.children if isinstance(c, FAtom)]

        self.assertEqual(preds, [FAtomPred.TYPE_EQ, FAtomPred.CONTROLLER_IS])


if __name__ == "__main__":
    unittest.main()
