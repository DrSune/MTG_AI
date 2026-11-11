"""Responses on the stack (CR 117, 405, 601.2, 608, 701.6): a spell waits there while the
players hold priority, and a spell cast in response resolves first.

  * a counterspell cast while the spell waits counters it: the spell's effect never runs, its
    card goes to its owner's graveyard (CR 400.7) and a COUNTER row lands (CR 701.6a);
  * with no response the spell resolves, the counter stays in hand and nobody is asked;
  * the menu of a player with priority offers a counterspell only when it can be cast at a
    spell on the stack: payable, and with a legal target (an instant-only counter has none in
    a creature spell);
  * a counter can itself be countered (LIFO, CR 405.5);
  * a spell an effect casts waits on the stack too, and can be countered (CR 601.2i, 117.3c);
  * the ``unless`` kickback is an honest ask: PAY runs the plan through the payment lane and
    the spell lives; PASS counters; an unpayable payer is never asked (the KICKBACK row carries
    "UNPAYABLE");
  * replay identity holds across a response.
"""

from __future__ import annotations

from MTG_bot.core.ability_tree import (
    ControllerRef,
    Cost,
    CostManaColor,
    CostManaGeneric,
    OptionalEffect,
    QConst,
    Selector,
    SelectorMode,
    SpellKind,
    Verb,
    Zone,
    ZoneKind,
)
from MTG_bot.core.executor.events import KIND_COUNTER
from MTG_bot.core.executor.menu import menu
from MTG_bot.core.executor.stack import cast
from MTG_bot.core.state import ZONE_BATTLEFIELD, ZONE_EXILE, ZONE_GRAVEYARD, ZONE_HAND
from MTG_bot.core.test_executor_binding import UNIV, card_id
from MTG_bot.core.test_executor_stack import (
    ANY_ZONE,
    INSTANT_OR_SORCERY,
    StackCase,
    atom,
)

STACK_TARGET = Selector(
    QConst(1), SelectorMode.TARGET, UNIV, zones=(Zone(ZoneKind.STACK, ControllerRef.ANY),)
)



def was_countered(ex, frame) -> bool:
    """CR 701.6a: a countered spell left the stack, with a COUNTER row."""
    return any(e.kind == KIND_COUNTER and e.subject == frame.handle for e in ex.journal.events)

class Rung1Case(StackCase):
    """StackCase + scripted provider + the counter-card idiom."""

    def setUp(self):
        super().setUp()
        self.asks: list[tuple[tuple[str, ...], str]] = []
        self._script: list = []

    def ex_cast(self, seat, handle, **kw):
        """The stack module's folded cast against THIS executor."""
        return cast(self.ex, seat, handle, **kw)

    def script(self, *answers):
        """Prime a scripted provider: each ask consumes the next answer
        (a literal token, or a callable vocab,what -> token) and is
        recorded in self.asks."""
        self._script = list(answers)

        def prov(vocab, what) -> str:
            self.asks.append((tuple(vocab), what))
            if not self._script:
                raise AssertionError(f"unexpected ask: {what} {vocab}")
            answer = self._script.pop(0)
            return str(answer(vocab, what) if callable(answer) else answer)

        self.ex.decisions.provider = prov

    def counterspell(self, name, seat, *, generic=0, colored=("U", 1), unless=0):
        parts = []
        if generic:
            parts.append(CostManaGeneric(QConst(generic)))
        if colored:
            color, n = colored
            parts.append(CostManaColor(color, QConst(n)))
        cost = Cost(tuple(parts)) if parts else None
        effect = atom(Verb.COUNTER_SPELL, target=STACK_TARGET)
        if unless:
            effect = atom(
                Verb.COUNTER_SPELL,
                target=STACK_TARGET,
                unless=Cost((CostManaGeneric(QConst(unless)),)),
            )
        return self.give(
            name,
            SpellKind.INSTANT,
            cost=cost,
            effect=effect,
            seat=seat,
        )

    def zone_kind(self, handle):
        return self.world.zone_of(handle).kind

    def hold_shock(self, r=2):
        """P0 casts a Shock at P1 and keeps priority: it waits on the stack."""
        shock = self.shock()
        self.mana(self.p0, R=r)
        with self.ex.holding_priority():
            frame = self.ex_cast(self.p0, shock, targets=(self.p1,))
        self.assertEqual(self.ex.stack.frames, [frame])
        return shock, frame

    def menu_tokens(self, seat):
        return [row.token for row in menu(self.ex, seat)]

    def countered_by(self, counter, seat, spell, *, targets=(), answers=()):
        """``seat`` casts ``spell`` and keeps priority; the other player casts ``counter`` at it
        in response, ``answers`` scripting the asks after that (an unless payment); then both
        players pass."""
        with self.ex.holding_priority():
            frame = self.ex_cast(seat, spell, targets=targets)
        self.script(*answers)
        self.ex_cast(self.p1 if seat == self.p0 else self.p0, counter, targets=(spell,))
        return frame


class TestResponses(Rung1Case):
    def test_a_counterspell_cast_in_response_counters_the_spell(self):
        cancel = self.counterspell("Cancel", self.p1)
        self.mana(self.p1, U=1)
        shock, frame = self.hold_shock()
        self.ex_cast(self.p1, cancel, targets=(shock,))
        # the effect never ran; the card went to its graveyard (CR 400.7).
        self.assertEqual(self.world.players[self.p1].life, 20)
        self.assertEqual(self.zone_kind(shock), ZONE_GRAVEYARD)
        self.assertTrue(was_countered(self.ex, frame))
        self.assertEqual(self.zone_kind(cancel), ZONE_GRAVEYARD)
        self.assertEqual(self.ex.stack.frames, [])
        self.assertFalse(self.world.players[self.p1].mana_pool.get("U"))
        counters = self.journal_events("COUNTER")
        self.assertEqual([(e.subject, e.cause) for e in counters], [(shock, cancel)])

    def test_with_no_response_the_spell_resolves_and_nobody_is_asked(self):
        cancel = self.counterspell("Cancel", self.p1)
        self.mana(self.p1, U=1)
        shock = self.shock()
        self.mana(self.p0, R=2)

        def prov(vocab, what):
            raise AssertionError(f"asked {what}")

        self.ex.decisions.provider = prov
        self.ex_cast(self.p0, shock, targets=(self.p1,))
        self.assertEqual(self.world.players[self.p1].life, 18)
        self.assertEqual(self.zone_kind(cancel), ZONE_HAND)
        self.assertEqual(len(self.journal_rows("COUNTER")), 0)

    def test_the_menu_offers_a_counterspell_only_when_it_can_be_paid(self):
        cancel = self.counterspell("Cancel", self.p1)
        self.hold_shock()
        self.assertNotIn(f"cast:{cancel}", self.menu_tokens(self.p1))  # nothing pays {U}
        self.mana(self.p1, U=1)
        self.assertIn(f"cast:{cancel}", self.menu_tokens(self.p1))

    def test_an_instant_only_counter_has_no_target_in_a_creature_spell(self):
        # Miscast's FOr(Instant, Sorcery) target: a creature spell on the stack is
        # no legal target (selection:off_population), so the row is not offered.
        pup = self.give(
            "Pup",
            SpellKind.CREATURE,
            cost=Cost((CostManaColor("R", QConst(1)),)),
            types=("Creature",),
            type_line="Creature",
            power="1",
            toughness="1",
        )
        self.mana(self.p0, R=1)
        miscast = self.give(
            "Miscast",
            SpellKind.INSTANT,
            cost=Cost((CostManaColor("U", QConst(1)),)),
            effect=atom(
                Verb.COUNTER_SPELL,
                target=Selector(
                    QConst(1),
                    SelectorMode.TARGET,
                    INSTANT_OR_SORCERY,
                    zones=(Zone(ZoneKind.STACK, ControllerRef.ANY),),
                ),
            ),
            seat=self.p1,
        )
        self.mana(self.p1, U=1)
        with self.ex.holding_priority():
            self.ex_cast(self.p0, pup)
        self.assertNotIn(f"cast:{miscast}", self.menu_tokens(self.p1))
        self.ex.fire_triggers()  # both players pass
        self.assertEqual(self.zone_kind(pup), ZONE_BATTLEFIELD)

    def test_a_counter_can_be_countered(self):
        # P0 Shock <- P1 Cancel <- P0 Counteria: the Shock survives, its would-be
        # counter having been countered (LIFO, CR 405.5).
        cancel = self.counterspell("Cancel", self.p1)
        counteria = self.counterspell("Counteria", self.p0)
        self.mana(self.p1, U=2)
        self.mana(self.p0, U=2)
        shock, _frame = self.hold_shock()
        with self.ex.holding_priority():
            self.ex_cast(self.p1, cancel, targets=(shock,))
        self.ex_cast(self.p0, counteria, targets=(cancel,))
        self.assertEqual(self.world.players[self.p1].life, 18)
        for card in (shock, cancel, counteria):
            self.assertEqual(self.zone_kind(card), ZONE_GRAVEYARD)
        self.assertEqual([e.subject for e in self.journal_events("COUNTER")], [cancel])
        self.assertEqual(self.ex.stack.frames, [])


class TestEffectCast(Rung1Case):
    """CR 601.2i, 117.3c, 608.1: a spell the CAST atom casts (an effect's "you may cast", and the
    permission rows of Idol of Endurance and Conspicuous Snoop) is on the stack like a spell cast
    from hand."""

    def cast_from_exile(self):
        """Run "you may cast it without paying its mana cost" on an exiled instant that gains
        its caster 3 life; the pool answers the may-offer."""
        exiled = self.give(
            "Exiled Spell",
            SpellKind.INSTANT,
            cost=Cost((CostManaGeneric(QConst(4)),)),
            effect=atom(Verb.GAIN_LIFE, controller=ControllerRef.YOU, amount=QConst(3)),
            zone=ZONE_EXILE,
        )
        sel = Selector(QConst(1), SelectorMode.CHOOSE, UNIV, zones=(ANY_ZONE,))
        self.ex.apply_effect(
            OptionalEffect(atom(Verb.CAST, source=sel, cost=Cost(()))),
            source=self.world.add_card(card_id("Caster", "1", "1"), self.p0, ZONE_BATTLEFIELD),
            controller=self.p0,
            bindings={"source": exiled},
            decisions=("fire",),
        )
        return exiled

    def test_it_waits_on_the_stack_and_can_be_countered(self):
        cancel = self.counterspell("Cancel", self.p1)
        self.mana(self.p1, U=1)
        with self.ex.holding_priority():
            exiled = self.cast_from_exile()
        self.assertEqual([f.handle for f in self.ex.stack.frames], [exiled])
        self.ex_cast(self.p1, cancel, targets=(exiled,))
        self.assertEqual(self.world.players[self.p0].life, 20)  # its effect never ran
        self.assertEqual(self.zone_kind(exiled), ZONE_GRAVEYARD)  # CR 400.7
        self.assertEqual(self.zone_kind(cancel), ZONE_GRAVEYARD)
        self.assertEqual([e.subject for e in self.journal_events("COUNTER")], [exiled])
        self.assertEqual(self.ex.stack.frames, [])

    def test_outside_a_game_loop_it_resolves_inside_the_effect(self):
        exiled = self.cast_from_exile()
        self.assertEqual(self.world.players[self.p0].life, 23)
        self.assertEqual(self.zone_kind(exiled), ZONE_GRAVEYARD)  # an instant resolved
        self.assertEqual(self.ex.stack.frames, [])


class TestKickback(Rung1Case):
    def kicked_shock(self, answers, r=2, **payer_mana):
        """P1 answers P0's waiting Shock with a Miscast-shaped counter: "counter target spell
        unless its controller pays {3}"."""
        miscast = self.counterspell("Miscast", self.p1, colored=("U", 1), unless=3)
        self.mana(self.p1, U=2)
        shock, frame = self.hold_shock(r)
        if payer_mana:
            self.mana(self.p0, **payer_mana)  # the kickback comes from the payer's pool
        self.script(*answers)
        self.ex_cast(self.p1, miscast, targets=(shock,))
        return shock

    def test_pay_lane_keeps_the_spell_alive(self):
        shock = self.kicked_shock(("PAY",), G=5)
        self.assertEqual(self.world.players[self.p1].life, 18)  # lived
        # {3} generic on top of the shock's R: four mana paid from the
        # seeded R2+G5, so exactly three mana remain in the payer's pool.
        self.assertEqual(sum(self.world.players[self.p0].mana_pool.values()), 3)
        self.assertEqual(self.zone_kind(shock), ZONE_GRAVEYARD)  # normal put
        kick = self.journal_events("KICKBACK")
        self.assertEqual([(k.data, k.subject) for k in kick], [(("PAY",), shock)])
        self.assertEqual(len(self.journal_rows("COUNTER")), 0)
        # the ask: pay:<payer seat>:<digest>, vocab PASS/PAY.
        ((vocab, what),) = self.asks
        self.assertEqual(vocab, ("PASS", "PAY"))
        self.assertTrue(what.startswith(f"pay:{self.p0}:"))

    def test_pass_on_kickback_counters(self):
        self.kicked_shock(("PASS",), G=5)
        self.assertEqual(self.world.players[self.p1].life, 20)  # countered
        self.assertEqual(self.world.players[self.p0].mana_pool.get("G"), 5)
        self.assertEqual(self.journal_events("KICKBACK")[0].data, ("PASS",))
        self.assertEqual(len(self.journal_rows("COUNTER")), 1)

    def test_unpayable_payer_is_never_asked(self):
        # P0's pool: the Shock costs R1, so after casting it P0 holds nothing and
        # the {3} kickback is unpayable: no ask, the KICKBACK row says so.
        self.kicked_shock((), r=1)
        self.assertEqual(self.asks, [])
        self.assertEqual(self.world.players[self.p1].life, 20)
        kick = self.journal_events("KICKBACK")
        self.assertEqual([k.data for k in kick], [("UNPAYABLE",)])
        self.assertEqual(len(self.journal_rows("COUNTER")), 1)


class TestReplay(Rung1Case):
    def test_replay_identity_across_a_response(self):
        # same play, two fresh worlds: byte-identical fingerprints.
        fps = []
        for _ in range(2):
            import itertools

            from MTG_bot.core import test_executor_stack as stack_fixtures
            from MTG_bot.core.executor import Executor
            from MTG_bot.core.state import GameWorld
            from MTG_bot.core.test_executor_binding import reset_oracle_ids

            reset_oracle_ids()
            stack_fixtures._OID = itertools.count(9000)  # card ids too
            world = GameWorld(num_players=2, start_life=20, master_seed=7)
            p0, p1 = world.player_order
            ex = Executor(world)
            ex.begin_turn(p0)
            case = TestReplay("test_replay_identity_across_a_response")
            case.world, case.p0, case.p1, case.ex = world, p0, p1, ex
            shock = case.shock()
            case.mana(p0, R=2)
            cancel = case.counterspell("Cancel", p1)
            case.mana(p1, U=2)
            with ex.holding_priority():
                case.ex_cast(p0, shock, targets=(p1,))
            case.ex_cast(p1, cancel, targets=(shock,))
            fps.append(ex.state_fingerprint())
        self.assertEqual(fps[0], fps[1])
