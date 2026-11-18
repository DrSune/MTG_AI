"""Rounding policy (``QBin.rounding``) and additional triggers (``AbilityTriggerEvent``).

Rounding-policy (Peer "Round up each time.") and additional-trigger-count
(Sanctum of All's s2) are orthogonal axes, not card-shaped kludges:

* ``Rounding`` rides ``QBin`` as an OPTIONAL policy field (valid on DIV
  only; CEIL = -(-a//b), FLOOR/NONE = the standing floor). At the default
  None the key is OMITTED from serialization (``_OMIT_IF_EMPTY``), so a
  tree without it keeps its golden bytes.
* "That ability triggers an additional time" is a static ability (CR 603.2d,
  DESIGN_ATOM_ONTOLOGY §20): ``TRIGGER_ADDITIONAL`` with the reusable {count}
  axis and its ``event``, an ``AbilityTriggerEvent`` whose filter is read over
  the triggering ability's SOURCE ("another Shrine you control" = SUBTYPE_EQ
  Shrine + CONTROLLER_IS YOU + FNot(IS_SOURCE)); "while you control six or more
  Shrines" is the static's condition. The binder counts the live statics as an
  ability triggers and queues the copies with it; copies are not counted again
  (the effect "doesn't invoke itself repeatedly"), so two statics add one each.
"""

import unittest

from MTG_bot.core.ability_tree import (
    AbilityTriggerEvent,
    Atom,
    AtomArgs,
    ControllerRef,
    FAnd,
    FAtom,
    FAtomPred,
    FNot,
    Phase,
    QBin,
    QBinOp,
    QConst,
    Rounding,
    Seq,
    StaticAbility,
    TriggeredAbility,
    TurnPhaseEvent,
    Verb,
    at_least,
    canonical_json,
    from_dict,
    number_you_control,
    to_dict,
)
from MTG_bot.core.executor import Executor
from MTG_bot.core.executor.decisions import in_trigger_order
from MTG_bot.core.executor.durations import DurationLedger
from MTG_bot.core.executor.quantity import ExecCtx, resolve
from MTG_bot.core.state import ZONE_BATTLEFIELD, GameWorld
from MTG_bot.core.test_executor_binding import (
    atom,
    card_id,
    record_of,
    reset_oracle_ids,
)
from MTG_bot.core.test_executor_verbs import stock_libraries


def shrine_filter() -> FAtom:
    return FAtom(pred=FAtomPred.SUBTYPE_EQ, string_value="Shrine")


def another_shrine_of_yours() -> AbilityTriggerEvent:
    return AbilityTriggerEvent(
        filter=FAnd(
            children=(
                shrine_filter(),
                FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
                FNot(inner=FAtom(pred=FAtomPred.IS_SOURCE)),
            )
        )
    )


def sanctum_multiplier(count=1) -> StaticAbility:
    """Sanctum of All s2, the compiler's shape: the abilities of "another Shrine you control"
    trigger ``count`` additional times while you control six or more Shrines."""
    return StaticAbility(
        effect=Atom(
            verb=Verb.TRIGGER_ADDITIONAL,
            args=AtomArgs(pairs=(("count", QConst(count)), ("event", another_shrine_of_yours()))),
        ),
        condition=at_least(6, quantity=number_you_control(shrine_filter())),
    )


def fangs_trigger() -> TriggeredAbility:
    """Sanctum of Stone Fangs, life-numbers flattened to 1 so the
    multiplier's arithmetic is the only variable under test."""
    return TriggeredAbility(
        event=TurnPhaseEvent(Phase.UPKEEP, actor=FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU)),
        condition=None,
        effect=Seq(
            steps=(
                atom(
                    Verb.LOSE_LIFE,
                    controller=ControllerRef.ALL_OPPONENTS,
                    amount=QConst(1),
                ),
                atom(Verb.GAIN_LIFE, controller=ControllerRef.YOU, amount=QConst(1)),
            )
        ),
    )


class T5DEngineCase(unittest.TestCase):
    """Battlefield rig: p0's shrines (plain + Fangs + carrier), p1 plain."""

    def setUp(self) -> None:
        reset_oracle_ids()
        self.world = GameWorld(num_players=2, start_life=20, master_seed=54)
        self.p0, self.p1 = self.world.player_order[0], self.world.player_order[1]
        stock_libraries(self.world)  # turns advance: no deck-out (CR 704.5b)
        self.ex = Executor(self.world)
        # A Shrine's trigger and its copies go on the stack together; their order
        # (CR 603.3b) does not change the life totals these tests read.
        self.ex.decisions.provider = in_trigger_order

    def shrine(self, owner, name="Shrine"):
        return self.world.add_card(
            card_id(name, type_line="Land — Shrine"), owner, ZONE_BATTLEFIELD
        )

    def attach(self, handle, abilities, name="Rec"):
        rec = record_of(
            abilities, name=name, oid=self.world.cards[handle].identity.oracle_id
        )
        self.ex.attach_card(handle, rec)

    def fangs(self, owner):
        h = self.shrine(owner, "Sanctum of Stone Fangs")
        self.attach(h, [fangs_trigger()], name="Fangs")
        return h

    def carrier(self, owner, count=1, extra_ability=None):
        h = self.shrine(owner, "Sanctum of All")
        abilities = [sanctum_multiplier(count)]
        if extra_ability is not None:
            abilities.append(extra_ability)
        self.attach(h, abilities, name="Carrier")
        return h

    def life(self, player):
        return self.world.players[player].life


class TestMultiplierEngine(T5DEngineCase):
    def test_gate_met_doubles_the_shrine_trigger(self):
        # 4 plain + Fangs + carrier = exactly six Shrines.
        for i in range(4):
            self.shrine(self.p0, f"Shrine{i}")
        self.fangs(self.p0)
        self.carrier(self.p0)
        self.ex.begin_turn(self.p0)
        self.assertEqual(self.life(self.p1), 18)  # -1 twice
        self.assertEqual(self.life(self.p0), 22)  # +1 twice

    def test_gate_unmet_fires_once(self):
        for i in range(3):  # 3 plain + Fangs + carrier = five
            self.shrine(self.p0, f"Shrine{i}")
        self.fangs(self.p0)
        self.carrier(self.p0)
        self.ex.begin_turn(self.p0)
        self.assertEqual(self.life(self.p1), 19)
        self.assertEqual(self.life(self.p0), 21)

    def test_carrier_never_doubles_its_own_ability(self):
        for i in range(4):
            self.shrine(self.p0, f"Shrine{i}")
        self.fangs(self.p0)
        self.carrier(
            self.p0,
            extra_ability=TriggeredAbility(
                event=TurnPhaseEvent(Phase.UPKEEP, actor=FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU)),
                condition=None,
                effect=atom(
                    Verb.GAIN_LIFE, controller=ControllerRef.YOU, amount=QConst(1)
                ),
            ),
        )
        self.ex.begin_turn(self.p0)
        # Fangs doubled (22 from it) but the carrier's own gain fired ONCE
        # — FNot(IS_SOURCE) reads the SOURCE permanent, not the controller.
        self.assertEqual(self.life(self.p0), 23)
        self.assertEqual(self.life(self.p1), 18)

    def test_count_axis_is_reusable(self):
        # Same verb, count=2 ("twice additional") — orthogonality proof:
        # nothing else in the encoding changes.
        for i in range(4):
            self.shrine(self.p0, f"Shrine{i}")
        self.fangs(self.p0)
        self.carrier(self.p0, count=2)
        self.ex.begin_turn(self.p0)
        self.assertEqual(self.life(self.p1), 17)
        self.assertEqual(self.life(self.p0), 23)

    def test_two_carriers_additive_and_terminating(self):
        # CR 603.2d: extra triggers carry no triggering event, so each
        # carrier adds exactly one per ORIGINAL firing; the extras never
        # re-arm each other. 5 plain + Fangs + 2 carriers: Fangs fires 3.
        for i in range(5):
            self.shrine(self.p0, f"Shrine{i}")
        self.fangs(self.p0)
        self.carrier(self.p0)
        self.carrier(self.p0)
        self.ex.begin_turn(self.p0)
        self.assertEqual(self.life(self.p1), 17)  # 1 original + 1 per carrier
        self.assertEqual(self.life(self.p0), 23)
        self.assertEqual(self.ex.binder.quarantined, set())  # no loop guard hit

    def test_foreign_shrine_trigger_not_multiplied(self):
        # p1's Fangs triggers on p1's upkeep: p0's carrier sees a source it
        # does not control — CONTROLLER_IS YOU fails on the FILTER.
        for i in range(4):
            self.shrine(self.p0, f"Shrine{i}")
        self.fangs(self.p0)
        self.carrier(self.p0)
        self.fangs(self.p1)
        self.ex.begin_turn(self.p0)  # p0 upkeep: doubled
        self.assertEqual(self.life(self.p1), 18)
        self.ex.begin_turn(self.p1)  # p1 upkeep: p1 has ONE shrine, gate fails
        self.assertEqual(self.life(self.p0), 21)  # single hit, not doubled

    def test_non_shrine_trigger_not_multiplied(self):
        # A plain Creature's upkeep trigger shares the battlefield but not
        # the Shrine subtype: SUBTYPE_EQ fails on the filter.
        for i in range(4):
            self.shrine(self.p0, f"Shrine{i}")
        self.fangs(self.p0)
        self.carrier(self.p0)
        beast = self.world.add_card(card_id("Beast"), self.p0, ZONE_BATTLEFIELD)
        self.attach(
            beast,
            [
                TriggeredAbility(
                    event=TurnPhaseEvent(Phase.UPKEEP, actor=FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU)),
                    condition=None,
                    effect=atom(
                        Verb.GAIN_LIFE, controller=ControllerRef.YOU, amount=QConst(5)
                    ),
                )
            ],
            name="Beast",
        )
        self.ex.begin_turn(self.p0)
        self.assertEqual(self.life(self.p0), 27)  # 2 (Fangs x2) + 5 (Beast x1)
        self.assertEqual(self.life(self.p1), 18)


class TestRoundingAxis(unittest.TestCase):
    def setUp(self) -> None:
        reset_oracle_ids()
        self.world = GameWorld(num_players=2, start_life=20, master_seed=55)
        self.p0 = self.world.player_order[0]
        self.card = self.world.add_card(card_id("Rig"), self.p0)
        self.ctx = ExecCtx(
            world=self.world,
            ledger=DurationLedger(),
            controller=self.p0,
            source=self.card,
            bindings={},
            decisions=(),
        )

    def test_ceil_floor_and_default_on_div(self):
        def div(r):
            return QBin(QBinOp.DIV, QConst(7), QConst(2), rounding=r)
        self.assertEqual(resolve(div(Rounding.CEIL), self.ctx), 4)
        self.assertEqual(resolve(div(Rounding.FLOOR), self.ctx), 3)
        self.assertEqual(resolve(div(None), self.ctx), 3)  # standing floor
        self.assertEqual(resolve(div(Rounding.NONE), self.ctx), 3)

    def test_rounding_rejected_off_div(self):
        with self.assertRaises(ValueError):
            QBin(QBinOp.ADD, QConst(7), QConst(2), rounding=Rounding.CEIL)

    def test_serialization_is_byte_stable_at_default(self):
        plain = canonical_json(QBin(QBinOp.DIV, QConst(7), QConst(2)))
        self.assertNotIn("rounding", plain)  # omitted at the default: golden bytes hold
        ceil = canonical_json(
            QBin(QBinOp.DIV, QConst(7), QConst(2), rounding=Rounding.CEIL)
        )
        self.assertIn("CEIL", ceil)
        self.assertIn("rounding", ceil)

    def test_roundtrip_decodes_policy(self):
        node = QBin(QBinOp.DIV, QConst(7), QConst(2), rounding=Rounding.CEIL)
        d = to_dict(node)
        self.assertIs(from_dict("QBin", d).rounding, Rounding.CEIL)
        # omitted key decodes back to the None default
        plain = to_dict(QBin(QBinOp.DIV, QConst(7), QConst(2)))
        self.assertNotIn("rounding", plain)
        self.assertIsNone(from_dict("QBin", plain).rounding)

    def test_ability_trigger_event_roundtrip(self):
        event = another_shrine_of_yours()
        d = to_dict(event)
        self.assertEqual(d["tag"], "AbilityTriggerEvent")
        self.assertEqual(from_dict("AbilityTriggerEvent", d), event)
        ability = sanctum_multiplier()
        self.assertEqual(from_dict("StaticAbility", to_dict(ability)), ability)


if __name__ == "__main__":
    unittest.main()
