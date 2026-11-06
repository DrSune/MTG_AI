"""The created token as a referent: CREATE_TOKEN writes the ``result`` register.

The ``result`` referent is "the object(s) the previous instruction acted on" (Selector docs);
the object verbs (TAP, MOVE_ZONE, SEARCH, ...) write it, and so does creating a token, so
"create a 1/1 white Soldier creature token, then attach this Equipment to it" (Ancestral Blade)
attaches to the token. CR 701.3b: an Equipment that can't be attached doesn't move, so when the
Equipment has left the battlefield before the instruction, the token is still made and nothing is
attached. The Kaldheim Equipment pay first: "you may pay {2}. If you
do, ..." makes the token only when the payment was made (CR 118.12).
"""

from __future__ import annotations

from MTG_bot.core.ability_tree import (
    Atom,
    AtomArgs,
    Conditional,
    ControllerRef,
    Cost,
    CostManaGeneric,
    CounterKind,
    FAnd,
    FAtom,
    FAtomPred,
    OptionalEffect,
    QConst,
    Selector,
    SelectorMode,
    Seq,
    TokenSpec,
    TriggeredAbility,
    Verb,
    Zone,
    ZoneChangeEvent,
    ZoneKind,
)
from MTG_bot.core.state import ZONE_BATTLEFIELD, ZONE_GRAVEYARD, ZONE_HAND
from MTG_bot.core.test_executor_blocker_limit import IS_SOURCE, SELF, LimitCase

IT = Selector(QConst(1), SelectorMode.CHOOSE, FAnd(()), zones=(Zone(ZoneKind.ANY, ControllerRef.ANY),),
              referent="result")
SOLDIER = TokenSpec(
    name="Soldier", type_line="Creature — Soldier", types=("Creature",), subtypes=("Soldier",),
    power=QConst(1), toughness=QConst(1), keywords=(), abilities=(), colors=("W",),
)
CREATE = Atom(Verb.CREATE_TOKEN, AtomArgs(pairs=(("count", QConst(1)), ("tokens", SOLDIER))))
ATTACH = Atom(Verb.ATTACH, AtomArgs(pairs=(("equipment", SELF), ("target", IT))))
ENTERS = ZoneChangeEvent(
    from_zone=Zone(ZoneKind.ANY, ControllerRef.ANY),
    to_zone=Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU),
    subject=IS_SOURCE,
)
PAY_2 = OptionalEffect(inner=Atom(Verb.PAY, AtomArgs(pairs=(("cost", Cost((CostManaGeneric(QConst(2)),))),))))


class TokenCase(LimitCase):
    def equipment(self, effect, zone=ZONE_BATTLEFIELD):
        """An Equipment whose enters trigger is ``effect`` (Ancestral Blade's shape)."""
        trigger = TriggeredAbility(event=ENTERS, condition=None, effect=effect)
        handle = self.custom("Blade", None, None, self.p0, (trigger,), types=("Artifact",))
        if zone != ZONE_BATTLEFIELD:
            self.world.move_to_zone(handle, self.p0, zone)
        return handle

    def soldiers(self):
        return [h for h, c in self.world.cards.items()
                if c.identity.name == "Soldier" and self.world.zone_of(h).kind == ZONE_BATTLEFIELD]

    def resolve(self, effect, source) -> object:
        ctx = self.ex._ctx(source=source, controller=self.p0, bindings=None, decisions=())
        self.ex._run_resolution(effect, ctx)
        return ctx


class TestTheCreatedTokenIsTheResult(TokenCase):
    def test_create_writes_the_tokens_as_the_result(self) -> None:
        self.begin()
        self.ex.begin_turn(self.p0)
        two = Atom(Verb.CREATE_TOKEN, AtomArgs(pairs=(("count", QConst(2)), ("tokens", SOLDIER))))
        ctx = self.resolve(two, self.p0)
        self.assertEqual(sorted(ctx.binding_handles("result")), sorted(self.soldiers()))
        self.assertEqual(len(self.soldiers()), 2)

    def test_the_next_instruction_acts_on_the_token(self) -> None:
        self.begin()
        self.ex.begin_turn(self.p0)
        counter = Atom(Verb.PUT_COUNTER, AtomArgs(pairs=(
            ("target", IT), ("counter_kind", CounterKind.PLUS_1_PLUS_1), ("count", QConst(1)))))
        self.resolve(Seq((CREATE, counter)), self.p0)
        (soldier,) = self.soldiers()
        self.assertEqual(self.world.cards[soldier].counters, {"PLUS_1_PLUS_1": 1})

    def test_then_attach_this_equipment_to_it(self) -> None:
        blade = self.equipment(Seq((CREATE, ATTACH)), zone=ZONE_HAND)
        self.begin()
        self.ex.begin_turn(self.p0)
        self.enter_battlefield(blade, self.p0)
        (soldier,) = self.soldiers()
        self.assertEqual(self.ex.attachments.get(blade), soldier)

    def test_an_equipment_that_left_is_not_attached_but_the_token_is_made(self) -> None:
        blade = self.equipment(Seq((CREATE, ATTACH)), zone=ZONE_GRAVEYARD)
        self.begin()
        self.ex.begin_turn(self.p0)
        self.resolve(Seq((CREATE, ATTACH)), blade)  # the trigger resolving after the Blade died
        self.assertEqual(len(self.soldiers()), 1)
        self.assertNotIn(blade, self.ex.attachments)
        self.assertEqual(self.world.zone_of(blade).kind, ZONE_GRAVEYARD)


class TestIfYouDo(TokenCase):
    GATED = Seq((PAY_2, Conditional(pred=FAtom(FAtomPred.MAY_DONE), then_effect=Seq((CREATE, ATTACH)))))

    def test_paid(self) -> None:
        blade = self.equipment(self.GATED, zone=ZONE_HAND)
        self.begin()
        self.ex.begin_turn(self.p0)
        self.answers[f"may:{blade}"] = "fire"
        self.world.players[self.p0].mana_pool["G"] = 2
        self.enter_battlefield(blade, self.p0)
        (soldier,) = self.soldiers()
        self.assertEqual(self.ex.attachments.get(blade), soldier)
        self.assertFalse(self.world.players[self.p0].mana_pool.get("G"))

    def test_declined(self) -> None:
        blade = self.equipment(self.GATED, zone=ZONE_HAND)
        self.begin()
        self.ex.begin_turn(self.p0)
        self.answers[f"may:{blade}"] = "skip"
        self.world.players[self.p0].mana_pool["G"] = 2
        self.enter_battlefield(blade, self.p0)
        self.assertEqual(self.soldiers(), [])
        self.assertNotIn(blade, self.ex.attachments)
        self.assertEqual(self.world.players[self.p0].mana_pool.get("G"), 2)
