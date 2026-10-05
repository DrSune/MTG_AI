"""RUNG-1 (response-window arc): the counter window on the cast pipeline.

Coverage contract (mission arc, ruling A of 2026-10-05):
  * the window ASKS each opponent holding a payable counter (C15: a seat
    with nothing to offer is never asked, and gets no journal row);
  * PASS resolves the spell untouched (WINDOW_PASS audit row); a counter
    answer casts LIFO and INTERRUPTS the resolution (CR 601.4): effect
    never runs, card still goes to its graveyard (CR 400.7), a COUNTER
    row lands;
  * the ``unless`` kickback is an honest ask — PAY runs the plan through
    the payment lane and the spell LIVES; PASS counters; an unpayable
    payer is NEVER ASKED (the KICKBACK row carries "UNPAYABLE");
  * the window answers through ``executor.decisions.take`` DIRECTLY —
    the cast's per-op decisions POOL stays reserved for the spell's own
    declaration (contamination pin);
  * a counter can itself be countered (nested windows, LIFO);
  * replay identity holds across the window fold.
"""

from __future__ import annotations

from MTG_bot.core.ability_tree import (
    ControllerRef,
    Cost,
    CostManaColor,
    CostManaGeneric,
    QConst,
    Selector,
    SelectorMode,
    Seq,
    SpellKind,
    Verb,
    Zone,
    ZoneKind,
)
from MTG_bot.core.executor.stack import cast
from MTG_bot.core.state import ZONE_BATTLEFIELD, ZONE_GRAVEYARD, ZONE_HAND
from MTG_bot.core.test_executor_binding import UNIV
from MTG_bot.core.test_executor_stack import (
    INSTANT_OR_SORCERY,
    StackCase,
    any_target,
    atom,
)

STACK_TARGET = Selector(
    QConst(1), SelectorMode.TARGET, UNIV, Zone(ZoneKind.STACK, ControllerRef.ANY)
)


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


class TestResponseWindow(Rung1Case):
    def test_counter_answer_interrupts_the_resolution(self):
        shock = self.shock()
        self.mana(self.p0, R=2)
        cancel = self.counterspell("Cancel", self.p1)
        self.mana(self.p1, U=1)
        self.script(str(cancel))
        cast_frame = self.ex_cast(self.p0, shock, targets=(self.p1,))
        # the interruption: effect never ran, card in the graveyard.
        self.assertEqual(self.world.players[self.p1].life, 20)
        self.assertEqual(self.zone_kind(shock), ZONE_GRAVEYARD)
        self.assertFalse(cast_frame.countered is False)
        # counter paid, moved to its own graveyard, stack popped clean.
        self.assertEqual(self.zone_kind(cancel), ZONE_GRAVEYARD)
        self.assertEqual(self.ex.stack.frames, [])
        # Cancel costs {U}: the pool key is drained to nothing.
        self.assertFalse(self.world.players[self.p1].mana_pool.get("U"))
        # journal audit: one OPEN (the ask), one COUNTER, zero PASS rows.
        self.assertEqual(len(self.journal_rows("WINDOW_OPEN")), 1)
        self.assertEqual(len(self.journal_rows("WINDOW_PASS")), 0)
        counters = self.journal_events("COUNTER")
        self.assertEqual(len(counters), 1)
        self.assertEqual(counters[0].subject, shock)
        self.assertEqual(counters[0].cause, cancel)
        # the ask itself: vocab PASS+cancel, tag counter:<p1>:<digest>.
        ((vocab, what),) = self.asks
        self.assertEqual(vocab, ("PASS", str(cancel)))
        self.assertTrue(what.startswith(f"counter:{self.p1}:"))

    def test_pass_resolves_the_spell_untouched(self):
        shock = self.shock()
        self.mana(self.p0, R=2)
        cancel = self.counterspell("Cancel", self.p1)
        self.mana(self.p1, U=2)
        self.script("PASS")
        self.ex_cast(self.p0, shock, targets=(self.p1,))
        self.assertEqual(self.world.players[self.p1].life, 18)
        self.assertEqual(len(self.journal_rows("WINDOW_OPEN")), 1)
        self.assertEqual(len(self.journal_rows("WINDOW_PASS")), 1)
        self.assertEqual(len(self.journal_rows("COUNTER")), 0)
        # a PASSing counter stays in hand, untouched.
        self.assertEqual(self.zone_kind(cancel), ZONE_HAND)

    def test_nothing_to_offer_never_asks(self):
        # C15: an empty choice set is never offered — P1 has no counter,
        # so no provider call, no window rows, spell resolves normally.
        shock = self.shock()
        self.mana(self.p0, R=2)
        self.script()  # any ask trips the AssertionError

        def prov(vocab, what):  # must never be consulted
            raise AssertionError(f"C15 violation: asked {what}")

        self.ex.decisions.provider = prov
        self.ex_cast(self.p0, shock, targets=(self.p1,))
        self.assertEqual(self.world.players[self.p1].life, 18)
        self.assertEqual(len(self.journal_rows("WINDOW_OPEN")), 0)

    def test_unpayable_counter_not_in_vocab(self):
        # C15 on the vocab side: a counter the seat cannot PAY is not
        # offered (window skips the seat, no ask at all).
        shock = self.shock()
        self.mana(self.p0, R=2)
        self.counterspell("Cancel", self.p1)  # cost U1, empty pool

        def prov(vocab, what):
            raise AssertionError(f"C15 violation: asked {what}")

        self.ex.decisions.provider = prov
        self.ex_cast(self.p0, shock, targets=(self.p1,))
        self.assertEqual(self.world.players[self.p1].life, 18)
        self.assertEqual(len(self.journal_rows("WINDOW_OPEN")), 0)

    def test_frame_filter_excludes_the_offer(self):
        # Vocab gate, designability lane (games smoke seed 16): an
        # instant-only counter (Miscast's FOr(Instant,Sorcery) shape) is
        # NOT offered against a CREATURE spell frame. spell_castable is
        # target-blind; the window must consult the frame itself or it
        # promises an answer the designation planner then rejects
        # (selection:off_population). The creature resolves into play.
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
        self.give(
            "Miscast",
            SpellKind.INSTANT,
            cost=Cost((CostManaColor("U", QConst(1)),)),
            effect=atom(
                Verb.COUNTER_SPELL,
                target=Selector(
                    QConst(1),
                    SelectorMode.TARGET,
                    INSTANT_OR_SORCERY,
                    Zone(ZoneKind.STACK, ControllerRef.ANY),
                ),
            ),
            seat=self.p1,
        )
        self.mana(self.p1, U=1)

        def prov(vocab, what):
            raise AssertionError(f"gate violation: asked {what} {vocab}")

        self.ex.decisions.provider = prov
        self.ex_cast(self.p0, pup)
        self.assertEqual(self.zone_kind(pup), ZONE_BATTLEFIELD)
        self.assertEqual(len(self.journal_rows("WINDOW_OPEN")), 0)

    def test_unsupported_closure_excludes_the_offer(self):
        # Vocab gate, verb-closure lane (games smoke seed 96): a card
        # that counts AND executes COPY (Sublime Epiphany's shape) is
        # engine-unsupported — the window offers only what the runtime
        # can execute, so the closure of EVERY atom in the spell node
        # must lie in HANDLERS. A COPY-bearing counter in a payable
        # hand against a counterable instant still produces NO ask.
        shock = self.shock()
        self.mana(self.p0, R=2)
        self.give(
            "Sublime",
            SpellKind.INSTANT,
            cost=Cost((CostManaColor("U", QConst(1)),)),
            effect=Seq(
                steps=(
                    atom(Verb.COUNTER_SPELL, target=STACK_TARGET),
                    atom(Verb.COPY, source=any_target()),
                )
            ),
            seat=self.p1,
        )
        self.mana(self.p1, U=1)

        def prov(vocab, what):
            raise AssertionError(f"gate violation: asked {what} {vocab}")

        self.ex.decisions.provider = prov
        self.ex_cast(self.p0, shock, targets=(self.p1,))
        self.assertEqual(self.world.players[self.p1].life, 18)
        self.assertEqual(len(self.journal_rows("WINDOW_OPEN")), 0)

    def test_counter_on_counter_nests_lifo(self):
        # P0 Shock <- P1 Cancel <- P0 Counteria. The outer frame survives
        # (its would-be counter was itself countered).
        shock = self.shock()
        self.mana(self.p0, R=2)
        cancel = self.counterspell("Cancel", self.p1)
        counteria = self.counterspell("Counteria", self.p0)
        self.mana(self.p1, U=2)
        self.mana(self.p0, R=2, U=2)
        self.script(str(cancel), str(counteria))
        self.ex_cast(self.p0, shock, targets=(self.p1,))
        self.assertEqual(self.world.players[self.p1].life, 18)  # shock lived
        for card in (shock, cancel, counteria):
            self.assertEqual(self.zone_kind(card), ZONE_GRAVEYARD)
        # exactly ONE COUNTER row — for cancel, not for shock.
        counters = self.journal_events("COUNTER")
        self.assertEqual([e.subject for e in counters], [cancel])
        # two windows opened: p1 asked about shock, p0 asked about cancel.
        self.assertEqual(len(self.journal_rows("WINDOW_OPEN")), 2)
        self.assertEqual(self.ex.stack.frames, [])


class TestKickback(Rung1Case):
    def test_pay_lane_keeps_the_spell_alive(self):
        # Miscast shape: "counter target instant or sorcery spell unless
        # its controller pays {3}". P0 PAYS — shock resolves.
        shock = self.shock()
        self.mana(self.p0, R=2)
        miscast = self.counterspell("Miscast", self.p1, colored=("U", 1), unless=3)
        self.mana(self.p1, U=2)
        self.mana(self.p0, G=5)  # the kickback comes from the payer's pool
        self.script(str(miscast), "PAY")
        self.ex_cast(self.p0, shock, targets=(self.p1,))
        self.assertEqual(self.world.players[self.p1].life, 18)  # lived
        # {3} generic on top of the shock's R: four mana paid from the
        # seeded R2+G5, so exactly three mana remain in the payer's pool.
        self.assertEqual(sum(self.world.players[self.p0].mana_pool.values()), 3)
        self.assertEqual(self.zone_kind(shock), ZONE_GRAVEYARD)  # normal put
        kick = self.journal_events("KICKBACK")
        self.assertEqual(len(kick), 1)
        self.assertEqual(kick[0].data, ("PAY",))
        self.assertEqual(kick[0].subject, shock)
        self.assertEqual(len(self.journal_rows("COUNTER")), 0)
        # the ask: pay:<payer seat>:<digest>, vocab PASS/PAY.
        pay_asks = [a for a in self.asks if a[1].startswith("pay:")]
        self.assertEqual(pay_asks[0][0], ("PASS", "PAY"))
        self.assertTrue(pay_asks[0][1].startswith(f"pay:{self.p0}:"))

    def test_pass_on_kickback_counters(self):
        shock = self.shock()
        self.mana(self.p0, R=2)
        miscast = self.counterspell("Miscast", self.p1, unless=3)
        self.mana(self.p1, U=2)
        self.mana(self.p0, G=5)
        self.script(str(miscast), "PASS")
        self.ex_cast(self.p0, shock, targets=(self.p1,))
        self.assertEqual(self.world.players[self.p1].life, 20)  # countered
        self.assertEqual(self.world.players[self.p0].mana_pool.get("G"), 5)
        kick = self.journal_events("KICKBACK")
        self.assertEqual(kick[0].data, ("PASS",))
        self.assertEqual(len(self.journal_rows("COUNTER")), 1)

    def test_unpayable_payer_is_never_asked(self):
        # C15: no plan, no ask — the KICKBACK row carries the honest
        # "UNPAYABLE" witness instead of a fabricated PASS.
        shock = self.shock()
        miscast = self.counterspell("Miscast", self.p1, unless=3)
        self.mana(self.p1, U=2)
        # P0's pool: shock costs R1 — after the cast P0 holds nothing,
        # so the {3} kickback is unpayable at resolution time.
        self.mana(self.p0, R=1)
        self.script(str(miscast))  # exactly ONE ask allowed

        def prov(vocab, what):
            if what.startswith("pay:"):
                raise AssertionError(f"C15 violation: asked {what}")
            return self._script.pop(0)

        self.asks = []
        self.ex.decisions.provider = prov
        self.ex_cast(self.p0, shock, targets=(self.p1,))
        self.assertEqual(self.world.players[self.p1].life, 20)
        kick = self.journal_events("KICKBACK")
        self.assertEqual(len(kick), 1)
        self.assertEqual(kick[0].data, ("UNPAYABLE",))
        self.assertEqual(len(self.journal_rows("COUNTER")), 1)


class TestChannelDiscipline(Rung1Case):
    def test_window_bypasses_the_declaration_pool(self):
        # The cast's per-op decisions POOL belongs to the spell's own
        # declaration. A window answer must reach the PROVIDER — had the
        # window consumed the pool lane, the provider would never see the
        # counter: ask (the pool token isn't even in the vocab).
        shock = self.shock()
        self.mana(self.p0, R=2)
        cancel = self.counterspell("Cancel", self.p1)
        self.mana(self.p1, U=2)
        self.script(str(cancel))
        self.ex_cast(self.p0, shock, targets=(self.p1,), decisions=("pool-token",))
        self.assertEqual(len(self.asks), 1)
        self.assertTrue(self.asks[0][1].startswith("counter:"))
        self.assertEqual(self.world.players[self.p1].life, 20)

    def test_replay_identity_across_the_window(self):
        # same script, two fresh worlds: byte-identical fingerprints.
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
            case = TestChannelDiscipline("test_replay_identity_across_the_window")
            case.world, case.p0, case.p1, case.ex = world, p0, p1, ex
            shock = case.shock()
            case.mana(p0, R=2)
            cancel = case.counterspell("Cancel", p1)
            case.mana(p1, U=2)
            case.ex.decisions.provider = lambda vocab, what, _c=cancel: str(_c)
            case.ex_cast(p0, shock, targets=(p1,))
            fps.append(ex.state_fingerprint())
        self.assertEqual(fps[0], fps[1])
