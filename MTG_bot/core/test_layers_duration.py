"""ZND-4d pins: attached-static registration MUST carry the atom's
``duration``-role :class:`DurationWhileCondition` into the LayerRecord.

The b4-era while-templates encode the "as long as" gate INSIDE the atom's
duration role (b2a precedent reserved ``StaticAbility.condition`` for the
plain lane). Registration used to carry ONLY ``StaticAbility.condition``,
so the duration-shape statics were EVER-LIVE (gate-confirmed: 4/4 Predatory
Wurm reading 6/6 with NO Garruk planeswalker on the battlefield).

Every census card (compiled-pool census, both eras, 2026-10-19):
  * Predatory Wurm    — MODIFY_PT while (your Garruk planeswalker) [affected]
  * Sigiled Contender — GRANT_ABILITY LIFELINK while (+1/+1 counter) [affected]
  * Drowsing Tyrannodon — LOSE_ABILITY DEFENDER while (creature with power
    >= 4); mirrors the gate in StaticAbility.condition too — UNAFFECTED,
    pinned here as the double-gate regression guard.
ZNR: zero duration-role statics (census-verified, both sets, "all" mode).
"""

from __future__ import annotations

import unittest

from MTG_bot.core.ability_tree import (
    Atom,
    AtomArgs,
    CardRecord,
    ControllerRef,
    CounterKind,
    DurationEot,
    DurationPermanent,
    DurationWhileCondition,
    FAtom,
    FAtomPred,
    Keyword,
    PtDelta,
    PtDirection,
    QConst,
    Selector,
    SelectorMode,
    Seq,
    StaticAbility,
    Verb,
    Zone,
    ZoneKind,
)
from MTG_bot.core.executor import Executor
from MTG_bot.core.executor.games import get_supply, identity_of
from MTG_bot.core.identity import CardIdentity
from MTG_bot.core.state import ZONE_BATTLEFIELD, ZONE_EXILE, GameWorld

_ORACLE = iter(range(1, 1 << 16))


def synth_id(name: str, power=None, toughness=None, type_line="Creature"):
    return CardIdentity(
        oracle_id=f"00000000-0000-0000-0002-{next(_ORACLE):012d}",
        name=name,
        power=power,
        toughness=toughness,
        type_line=type_line,
        cmc=2,
    )


def synth_record(abilities, name: str, oid: str) -> CardRecord:
    return CardRecord(
        oracle_id=oid,
        name=name,
        type_line="Creature",
        types=("Creature",),
        subtypes=(),
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


def atom(verb, **roles) -> Atom:
    return Atom(verb=verb, args=AtomArgs(pairs=tuple(roles.items())))


BF_ANY = Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY)
IS_SELF = FAtom(FAtomPred.IS_SOURCE)


def self_pump(**roles) -> Atom:
    """A compiled-shape "+1/+1 of self" MODIFY_PT atom (b4 self-target
    selector), with any extra roles (the duration lane) bolted on."""
    return atom(
        Verb.MODIFY_PT,
        target=Selector(QConst(1), SelectorMode.CHOOSE, IS_SELF, zones=(BF_ANY,)),
        power=PtDelta(PtDirection.INCREASE, QConst(1)),
        **roles,
    )


def while_(pred: FAtomPred) -> DurationWhileCondition:
    return DurationWhileCondition(FAtom(pred))


class DurationRoleCase(unittest.TestCase):
    """Real compiled M21 cards through the real executor layers lane."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.supply = get_supply("all", "M21")
        cls.records = {
            res.card.name: res.card for res in cls.supply.pool.results.values()
        }

    def setUp(self) -> None:
        self.world = GameWorld(num_players=2, start_life=20, master_seed=19)
        self.p0, _p1 = self.world.player_order
        self.ex = Executor(self.world)
        self.ex.attach_pool(self.supply.pool)

    def play(self, name: str, seat=None):
        seat = self.p0 if seat is None else seat
        rec = self.records[name]
        handle = self.world.add_card(identity_of(rec), seat, ZONE_BATTLEFIELD)
        self.ex.attach_card(handle, rec)
        self.settle()
        return handle

    def settle(self) -> None:
        # One recompute pass through a no-op public op (the settle idiom
        # of test_executor_layers).
        src = min(self.world.cards, key=lambda h: h.index)
        self.ex.execute(
            atom(Verb.GAIN_LIFE, controller=ControllerRef.YOU, amount=QConst(0)),
            source=src,
            controller=self.p0,
        )

    def pt(self, handle):
        card = self.world.cards[handle]
        return self.ex.ledger.effective_pt(
            card.identity, handle, counters=card.counters
        )

    def kw(self, handle, keyword) -> bool:
        return self.ex.layers.keyword_of(handle, keyword)

    def static_layers(self, handle):
        return [
            layer
            for layer in self.ex.layers.records
            if layer.source == handle and layer.kind == "static"
        ]


class TestPredatoryWurmWhileGarruk(DurationRoleCase):
    """MODIFY_PT +2/+2 while "you control a planeswalker named Garruk"."""

    NAME = "Predatory Wurm"

    def test_named_repro_no_garruk_never_buffs(self) -> None:
        # The gate-confirmed repro (ZND-4d): with the duration role dropped
        # at registration this reads (6, 6) — EVER-LIVE with no Garruk.
        wurm = self.play(self.NAME)
        self.settle()
        self.assertEqual(self.pt(wurm), (4, 4), "no Garruk => no +2/+2")

    def test_condition_on_buffs_off_withdraws_flips_back(self) -> None:
        wurm = self.play(self.NAME)
        self.assertEqual(self.pt(wurm), (4, 4), "starts OFF")
        garruk = self.play("Garruk, Unleashed")
        self.assertEqual(self.pt(wurm), (6, 6), "ON: your Garruk PW is out")
        self.world.move_to_zone(garruk, self.p0, ZONE_EXILE)
        self.settle()
        self.assertEqual(self.pt(wurm), (4, 4), "OFF again: Garruk exiled")
        self.world.move_to_zone(garruk, self.p0, ZONE_BATTLEFIELD)
        self.settle()
        self.assertEqual(self.pt(wurm), (6, 6), "flip-back re-materializes")

    def test_opponent_garruk_never_gates_on(self) -> None:
        # CONTROLLER_IS YOU is part of the gate: the ENEMY Garruk must not
        # pump — the direction the predatory_wurm.json gold collapsed into
        # 6/6-via-opp-Garruk by the ever-live bug.
        wurm = self.play(self.NAME)
        self.play("Garruk, Unleashed", seat=self.world.player_order[1])
        self.assertEqual(self.pt(wurm), (4, 4), "opponent's Garruk is not yours")

    def test_duration_role_carried_into_layer_record(self) -> None:
        wurm = self.play(self.NAME)
        layers = self.static_layers(wurm)
        self.assertEqual(len(layers), 1, "the one while-static")
        self.assertIsInstance(
            layers[0].duration,
            DurationWhileCondition,
            "the atom duration-role must reach the LayerRecord",
        )
        self.assertEqual(layers[0].status, "dormant", "condition false")
        self.play("Garruk, Unleashed")
        self.assertEqual(layers[0].status, "live", "condition true re-read")


class TestSigiledContenderWhileCounter(DurationRoleCase):
    """GRANT_ABILITY LIFELINK while "it has a +1/+1 counter"."""

    NAME = "Sigiled Contender"

    def test_named_repro_no_counter_no_lifelink(self) -> None:
        # Pre-fix this reads True — EVER-LIVE lifelink with no counter.
        contender = self.play(self.NAME)
        self.settle()
        self.assertFalse(
            self.kw(contender, Keyword.LIFELINK), "no counter => no lifelink"
        )

    def test_counter_cycle_on_off_on(self) -> None:
        contender = self.play(self.NAME)
        counters = self.world.cards[contender].counters
        key = CounterKind.PLUS_1_PLUS_1.name
        counters[key] = 1
        self.settle()
        self.assertTrue(self.kw(contender, Keyword.LIFELINK), "ON with counter")
        del counters[key]
        self.settle()
        self.assertFalse(self.kw(contender, Keyword.LIFELINK), "OFF without it")
        counters[key] = 1
        self.settle()
        self.assertTrue(self.kw(contender, Keyword.LIFELINK), "flips back")

    def test_duration_role_carried_into_layer_record(self) -> None:
        contender = self.play(self.NAME)
        (layer,) = self.static_layers(contender)
        self.assertIsInstance(layer.duration, DurationWhileCondition)
        self.assertEqual(layer.status, "dormant")
        self.world.cards[contender].counters[CounterKind.PLUS_1_PLUS_1.name] = 1
        self.settle()
        self.assertEqual(layer.status, "live")


class TestDrowsingTyrannodonDoubleGate(DurationRoleCase):
    """UNAFFECTED card (its gate is mirrored in StaticAbility.condition):
    pinned so the fix cannot break the condition lane, and so the duration
    lane now double-gates consistently."""

    NAME = "Drowsing Tyrannodon"

    def test_defender_cycle_and_double_gate(self) -> None:
        dino = self.play(self.NAME)
        self.assertTrue(self.kw(dino, Keyword.DEFENDER), "starts OFF")
        (layer,) = self.static_layers(dino)
        self.assertIsNotNone(layer.condition, "condition lane intact")
        self.assertIsInstance(
            layer.duration, DurationWhileCondition, "duration lane now carried"
        )
        muscle = self.world.add_card(
            synth_id("Muscle", "4", "4"), self.p0, ZONE_BATTLEFIELD
        )
        self.settle()
        self.assertFalse(self.kw(dino, Keyword.DEFENDER), "ON: a 4-power ally")
        self.world.move_to_zone(muscle, self.p0, ZONE_EXILE)
        self.settle()
        self.assertTrue(self.kw(dino, Keyword.DEFENDER), "OFF again")


class TestDurationRoleRegistrationContract(DurationRoleCase):
    """The registration rule itself: WHILE folds into the record's duration
    lane; PERMANENT is the absence of a window (the Conspicuous Snoop
    shape); every other Duration node is a LOUD refusal riding the r23a
    not-layer-parseable sink (flag, never guess)."""

    def _attach_synth(self, static: StaticAbility, name: str):
        ident = synth_id(name, "2", "2")
        handle = self.world.add_card(ident, self.p0, ZONE_BATTLEFIELD)
        rec = synth_record([static], name, ident.oracle_id)
        self.ex.attach_card(handle, rec)
        self.settle()
        return handle

    def test_permanent_duration_is_no_window(self) -> None:
        handle = self._attach_synth(
            StaticAbility(effect=self_pump(duration=DurationPermanent())),
            "Snoopy",
        )
        self.assertEqual(self.ex.unparseable_statics, [])
        (layer,) = self.static_layers(handle)
        self.assertIsNone(layer.duration, "PERMANENT is the absent window")
        self.assertEqual(self.pt(handle), (3, 2), "the +1/+0 static is live")

    def test_foreign_duration_flags_not_layer_parseable(self) -> None:
        # DurationEot on an ATTACHED static contradicts attachment liveness
        # (step/EoT windows are runtime-dispatch shapes). Loud refusal,
        # survivable sink, NO layer, no PT.
        handle = self._attach_synth(
            StaticAbility(effect=self_pump(duration=DurationEot())), "Eoty"
        )
        self.assertEqual(self.static_layers(handle), [])
        self.assertTrue(
            any("not layer-parseable" in s for s in self.ex.unparseable_statics),
            f"r23a sink must carry the refusal: {self.ex.unparseable_statics}",
        )
        self.assertEqual(self.pt(handle), (2, 2))

    def test_distinct_while_mixtures_flag_not_guess(self) -> None:
        # A Seq whose atoms disagree about the gate cannot become one
        # record on one duration — refusal, not a coin flip.
        static = StaticAbility(
            effect=Seq(
                steps=(
                    self_pump(duration=while_(FAtomPred.IS_TAPPED)),
                    self_pump(duration=while_(FAtomPred.IS_UNTAPPED)),
                )
            )
        )
        handle = self._attach_synth(static, "TwoGate")
        self.assertEqual(self.static_layers(handle), [])
        self.assertTrue(
            any(
                "while-condition" in s and "distinct" in s
                for s in self.ex.unparseable_statics
            ),
            f"mixed distinct while-gates must refuse loudly: "
            f"{self.ex.unparseable_statics}",
        )
        self.assertEqual(self.pt(handle), (2, 2))


if __name__ == "__main__":
    unittest.main()
