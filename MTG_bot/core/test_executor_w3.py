"""Ontology gate round W3 (DESIGN_ATOM_ONTOLOGY §19) in the engine: state triggers (CR 603.8),
"that ability triggers an additional time" as a static (CR 603.2d), and the records of what a
reveal, a look and a scry showed (CR 701.20a, 701.22a). Each test fails on main 0b7f9c22 (the
note on each says how)."""

from __future__ import annotations

import unittest
from functools import cache

from MTG_bot.core.ability_tree import (
    AbilityTriggerEvent,
    Atom,
    AtomArgs,
    ControllerRef,
    FAtom,
    FAtomPred,
    Phase,
    QConst,
    Seq,
    StaticAbility,
    TriggeredAbility,
    TurnPhaseEvent,
    Verb,
    Zone,
    ZoneChangeEvent,
    ZoneKind,
)
from MTG_bot.core.compiler.compiler import compile_pool
from MTG_bot.core.compiler.coverage import build_full_registry
from MTG_bot.core.compiler.templates_b5a import target_stack_ability
from MTG_bot.core.compiler.test_compiler import _oid, _raw_card
from MTG_bot.core.executor import Executor
from MTG_bot.core.executor.games import compile_supply, get_supply
from MTG_bot.core.state import ZONE_BATTLEFIELD, ZONE_EXILE, ZONE_HAND, ZONE_LIBRARY, GameWorld
from MTG_bot.core.test_executor_binding import record_of
from MTG_bot.core.test_executor_durations import atom, card_id, target_sel
from MTG_bot.core.test_executor_verbs import stock_libraries
from tools.run_scenarios import ScenarioRunner

ME = FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU)
GAIN_1 = atom(Verb.GAIN_LIFE, controller=ControllerRef.YOU, amount=QConst(1))
ENTERS = ZoneChangeEvent(
    from_zone=Zone(ZoneKind.ANY, ControllerRef.ANY),
    to_zone=Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU),
    subject=FAtom(pred=FAtomPred.IS_SOURCE),
)


@cache
def _records(code: str):
    return compile_supply("all", code, require_verified=False)


def _runner(cards: list[dict], *, code: str = "M21", records: bool = False,
            mana: dict | None = None) -> ScenarioRunner:
    pack = {"set": code, "world": {"life": 20, "seed": 7}, "cards": cards, "steps": [], "mana": mana or {}}
    return ScenarioRunner(pack, _records(code) if records else get_supply("all", code))


def _card(key: str, seat: int, zone: str = "battlefield", real: str | None = None, **kw) -> dict:
    if real is not None:
        return {"key": key, "real": real, "zone": zone, "controller": seat, **kw}
    return {"key": key, "name": key.title(), "type": "Creature — Bear", "power": "2",
            "toughness": "2", "zone": zone, "controller": seat, **kw}


def _rows(r: ScenarioRunner, kind: str) -> list[tuple]:
    """The ``kind`` rows of the event log as (owner, cards, zone, viewers), one per group of a
    row (verbs._seen: one row per atom, ((owner, zone, cards), ...), viewers)."""
    return [(owner, cards, zone, e[3]) for e in r.ex.events if e[1] == kind for owner, zone, cards in e[2]]


# ---------------------------------------------------------------------------- state triggers


class NineLivesCase(unittest.TestCase):
    """M21 Nine Lives' replacement and state trigger, compiled from their printed sentences (its
    third, "you lose the game", left out so an exile ends nothing), as
    test_executor_durations.TestNineLivesReplacement builds it."""

    def setUp(self) -> None:
        self.world = GameWorld(num_players=2, start_life=20, master_seed=14)
        self.p0, self.p1 = self.world.player_order[0], self.world.player_order[1]
        stock_libraries(self.world)
        pool = {_oid(9): _raw_card(
            "Nine Lives", 9, types=("Enchantment",), colors=("W",), mana_cost_raw="{1}{W}{W}",
            mana_value=3,
            sentences=(
                "If a source would deal damage to you, prevent that damage and put an incarnation "
                "counter on this enchantment.",
                "When there are nine or more incarnation counters on this enchantment, exile it.",
            ),
        )}
        record = compile_pool(pool, build_full_registry()).results[_oid(9)].card
        self.nine = self.world.add_card(
            card_id("Nine Lives", type_line="Enchantment", oid=record.oracle_id), self.p0, ZONE_BATTLEFIELD
        )
        self.ex = Executor(self.world)
        self.ex.attach_card(self.nine, record)

    def counters(self, n: int) -> None:
        self.world.cards[self.nine].counters["INCARNATION"] = n

    def hit(self, *amounts: int) -> None:
        """One resolution of the opponent's dealing each amount to you, one damage event each."""
        steps = tuple(atom(Verb.DEAL_DAMAGE, target=target_sel(), amount=QConst(n)) for n in amounts)
        self.ex.apply_effect(steps[0] if len(steps) == 1 else Seq(steps=steps), source=self.p1,
                             controller=self.p1, bindings={"target": self.p0})

    def waiting(self) -> list:
        """The exile triggers on the stack once a player would receive priority (CR 117.5)."""
        self.ex._priority_check()
        return [o for o in self.ex.stack.frames if o.spell_kind == "TRIGGERED" and o.source == self.nine]

    def counter_the_exile(self, obj) -> None:
        """Sublime Epiphany's "counter target activated or triggered ability" (CR 701.6b)."""
        self.ex.execute(atom(Verb.COUNTER_SPELL, target=target_stack_ability("ACTIVATED", "TRIGGERED")),
                        source=self.p1, controller=self.p1, bindings={"target": obj.handle})


class TestStateTriggers(NineLivesCase):
    def test_two_damage_events_at_eight_counters_trigger_once(self) -> None:
        """CR 603.8 and the card's ruling: once the first instance is on the stack, more counters
        trigger nothing. On main each counter placed at nine or more queued another instance
        (two exile triggers)."""
        self.counters(8)
        with self.ex.holding_priority():
            self.hit(1, 1)
            self.assertEqual(self.world.cards[self.nine].counters["INCARNATION"], 10)
            self.assertEqual(len(self.waiting()), 1)
            self.hit(1)  # an eleventh while it waits: still one
            self.assertEqual(len(self.waiting()), 1)
        self.ex._settle()
        self.assertEqual(self.world.zone_of(self.nine).kind, ZONE_EXILE)

    def test_a_countered_state_trigger_triggers_again_at_once(self) -> None:
        """CR 603.8: countered while nine counters remain, it triggers again at the next check
        (the card's ruling). On main the countered trigger was gone for good and Nine Lives stayed
        on the battlefield: stronger than printed once Sublime Epiphany is stamped."""
        self.counters(8)
        with self.ex.holding_priority():
            self.hit(1)
            (first,) = self.waiting()
            self.counter_the_exile(first)
            self.assertNotIn(first, self.ex.stack.frames)
            (again,) = self.waiting()
            self.assertIsNot(again, first)
        self.ex._settle()
        self.assertEqual(self.world.zone_of(self.nine).kind, ZONE_EXILE)

    def test_it_does_not_trigger_while_the_state_does_not_hold(self) -> None:
        self.counters(7)
        with self.ex.holding_priority():
            self.hit(1)
            self.assertEqual(self.waiting(), [])  # eight: no state
        self.ex._settle()
        self.assertEqual(self.world.zone_of(self.nine).kind, ZONE_BATTLEFIELD)

    def test_a_new_object_triggers_on_its_own(self) -> None:
        """CR 603.8 with 400.7: an instance blocks the object it triggered for; Nine Lives that
        left and came back is a new object, which triggers for itself while the old instance
        waits (that instance then finds no "it" to exile: the new object is not it)."""
        self.counters(9)
        with self.ex.holding_priority():
            (old,) = self.waiting()
            for where in (ZoneKind.HAND, ZoneKind.BATTLEFIELD):  # journalled moves
                self.ex.execute(atom(Verb.MOVE_ZONE, target=target_sel(), destination=Zone(where, ControllerRef.OWNER)),
                                source=self.p1, controller=self.p1, bindings={"target": self.nine})
            self.counters(9)
            mine = self.waiting()
            self.assertEqual(len(mine), 2)
            self.assertIn(old, mine)


class TestMazemindTome(unittest.TestCase):
    """M21 and FDN Mazemind Tome: the fourth page counter, paid as a cost, triggers the state; it
    exiles the Tome and you gain 4 life, once."""

    def test_the_fourth_page_counter_exiles_it_once(self) -> None:
        r = _runner([_card("tome", 0, real="Mazemind Tome", counters={"PAGE": 3})])
        r.run_step({"op": "activate", "key": "tome", "ability": 0, "decisions": ["top"]})
        self.assertEqual(r.world.zone_of(r.handles["tome"]).kind, ZONE_EXILE)
        self.assertEqual(r.world.players[r.p0].life, 24)


# ---------------------------------------------------------------------------- extra triggers


def _doubler(event: AbilityTriggerEvent) -> StaticAbility:
    return StaticAbility(effect=Atom(Verb.TRIGGER_ADDITIONAL, AtomArgs(pairs=(
        ("count", QConst(1)), ("event", event)))))


class TestYarok(unittest.TestCase):
    """M20 Yarok, the Desecrated (its record: the compiler's tree since this round): "If a
    permanent entering causes a triggered ability of a permanent you control to trigger, that
    ability triggers an additional time." On main its record was a needs-atom note: no Yarok to
    play."""

    def runner(self, *cards: dict) -> ScenarioRunner:
        r = _runner([_card("yarok", 0, real="Yarok, the Desecrated"), *cards], code="M20", records=True)
        for key in ("bear", "foe"):
            if key in r.handles:
                h = r.handles[key]
                r.ex.attach_card(h, record_of([TriggeredAbility(event=ENTERS, condition=None, effect=GAIN_1)],
                                              name=key, oid=r.world.cards[h].identity.oracle_id))
        return r

    def life(self, r: ScenarioRunner, seat: int) -> int:
        return r.world.players[r.seats[seat]].life

    def test_an_entering_creatures_trigger_triggers_twice(self) -> None:
        r = self.runner(_card("bear", 0, zone="hand"))
        r.run_step({"op": "enter", "key": "bear"})
        self.assertEqual(self.life(r, 0), 22)

    def test_an_opponents_permanents_trigger_once(self) -> None:
        r = self.runner(_card("foe", 1, zone="hand"))
        r.run_step({"op": "enter", "key": "foe"})
        self.assertEqual(self.life(r, 1), 21)

    def test_a_trigger_no_entering_caused_triggers_once(self) -> None:
        r = self.runner(_card("bear", 0))
        bear = r.handles["bear"]
        upkeep = TriggeredAbility(event=TurnPhaseEvent(Phase.UPKEEP, actor=ME), condition=None, effect=GAIN_1)
        r.ex.attach_card(bear, record_of([upkeep], name="Upkeep Bear", oid=r.world.cards[bear].identity.oracle_id))
        r.ex.end_turn()
        r.ex.begin_turn(r.p1)
        r.ex.end_turn()
        before = self.life(r, 0)
        r.ex.begin_turn(r.p0)
        self.assertEqual(self.life(r, 0), before + 1)

    def test_yarok_entering_with_a_creature_doubles_its_trigger(self) -> None:
        """CR 603.6a, 603.10: an enters trigger is checked after the event, Yarok's static then
        applying (Panharmonicon's ruling)."""
        r = self.runner(_card("bear", 0, zone="hand"))
        r.world.move_to_zone(r.handles["yarok"], r.p0, ZONE_HAND)
        r.ex.binder.detach(r.handles["yarok"])
        r.run_step({"op": "move", "keys": ["yarok", "bear"], "to": "battlefield"})
        self.assertEqual(self.life(r, 0), 22)


class TestTheCopiesGoWithTheOriginal(unittest.TestCase):
    """CR 603.2d: the copies are counted as the ability triggers and go on the stack with it; no
    trigger of the static's own goes there. On main a carrier trigger went on the stack beside the
    original (its controller asked which resolved first) and the copy was queued only when it
    resolved."""

    def test_one_order_option_for_the_ability_and_its_copy(self) -> None:
        world = GameWorld(num_players=2, start_life=20, master_seed=54)
        p0 = world.player_order[0]
        stock_libraries(world)
        ex = Executor(world)
        doubler = world.add_card(card_id("Doubler", type_line="Artifact"), p0, ZONE_BATTLEFIELD)
        ex.attach_card(doubler, record_of([_doubler(AbilityTriggerEvent(filter=ME))], name="Doubler",
                                          oid=world.cards[doubler].identity.oracle_id))
        bear = world.add_card(card_id("Bear"), p0, ZONE_BATTLEFIELD)
        upkeep = TriggeredAbility(event=TurnPhaseEvent(Phase.UPKEEP, actor=ME), condition=None, effect=GAIN_1)
        ex.attach_card(bear, record_of([upkeep], name="Bear", oid=world.cards[bear].identity.oracle_id))
        asks: list[str] = []

        def provider(vocab, what):
            asks.append(what)
            return vocab[0]

        ex.decisions.provider = provider
        ex.begin_turn(p0)
        self.assertEqual(world.players[p0].life, 22)
        self.assertEqual([a for a in asks if a.startswith("trigger:")], [])


# ---------------------------------------------------------------------------- reveal, look, scry


class TestReveals(unittest.TestCase):
    def test_duress_reveals_the_hand_only(self) -> None:
        """M21 Duress: the row names the target's hand, to all, never its library. On main it
        listed the target's whole library."""
        r = _runner([
            _card("duress", 0, zone="hand", real="Duress"),
            _card("shock", 1, zone="hand", real="Shock"),
            _card("bear", 1, zone="hand"),
            _card("deep", 1, zone="library"),
        ])
        r.world.players[r.p0].mana_pool["B"] = 1
        r.run_step({"op": "cast", "key": "duress", "targets": ["p1"], "decisions": ["shock"]})
        hand = (str(r.handles["shock"]), str(r.handles["bear"]))
        self.assertEqual(_rows(r, "REVEAL"), [(str(r.p1), hand, ZONE_HAND, "ALL")])
        self.assertEqual(r.world.zone_of(r.handles["shock"]).kind, "graveyard")

    def test_fierce_empath_reveals_the_card_found(self) -> None:
        """M21 Fierce Empath: "reveal it" names the card the search found, now in the hand. On
        main the row named the library's new top card, which nobody saw."""
        r = _runner([
            _card("empath", 0, zone="hand", real="Fierce Empath"),
            _card("big", 0, zone="library", real="Pursued Whale"),
            _card("top", 0, zone="library", real="Llanowar Visionary"),
        ])
        r.run_step({"op": "enter", "key": "empath", "decisions": ["fire", "big"]})
        self.assertEqual(_rows(r, "REVEAL"), [(str(r.p0), (str(r.handles["big"]),), ZONE_HAND, "ALL")])

    def test_a_graveyard_search_reveals_the_card_found_not_the_library_top(self) -> None:
        """M21 Basri's Aegis, "search your library and/or graveyard ... reveal it", the graveyard
        alone: no shuffle follows, so main's row (the library's top card) told the opponent the
        next draw."""
        r = _runner([
            _card("aegis", 0, zone="hand", real="Basri's Aegis"),
            _card("basri", 0, zone="graveyard", real="Basri, Devoted Paladin"),
            _card("bear", 1),
        ], mana={"0": {"W": 2, "G": 2}})
        r.run_step({"op": "cast", "key": "aegis", "targets": ["bear"], "decisions": ["fire", "2", "basri"]})
        self.assertEqual(r.world.zone_of(r.handles["basri"]).kind, ZONE_HAND)
        self.assertEqual(_rows(r, "REVEAL"), [(str(r.p0), (str(r.handles["basri"]),), ZONE_HAND, "ALL")])

    def test_a_card_picked_from_a_look_is_the_card_revealed(self) -> None:
        """M20 Brightwood Tracker (its record): "reveal a creature card from among them and put
        it into your hand" names the card picked. On main it named the look's first card, here a
        land that went to the bottom."""
        r = _runner([
            _card("tracker", 0, real="Brightwood Tracker"),
            _card("bear", 0, zone="library", real="Elvish Reclaimer"),
            _card("land", 0, zone="library", real="Forest"),
        ], code="M20", records=True, mana={"0": {"G": 6}})
        library = r.world.players[r.p0].zone(ZONE_LIBRARY).entries
        for key in ("bear", "land"):  # the top two: the land first, the creature under it
            library.remove(r.handles[key])
            library.append(r.handles[key])
        r.run_step({"op": "activate", "key": "tracker", "idx": 0, "decisions": ["fire", "bear"]})
        self.assertEqual(r.world.zone_of(r.handles["bear"]).kind, ZONE_HAND)
        self.assertEqual(_rows(r, "REVEAL"), [(str(r.p0), (str(r.handles["bear"]),), ZONE_HAND, "ALL")])

    def test_a_scry_names_each_card_and_its_end_for_the_scryer(self) -> None:
        """CR 701.22a: the scryer sees the cards; main's row held only how many."""
        r = _runner([_card("a", 0, zone="library", real="Forest")])
        library = r.world.players[r.p0].zone(ZONE_LIBRARY).entries
        top, second = str(library[-1]), str(library[-2])
        r.ex.execute(atom(Verb.SCRY, controller=ControllerRef.YOU, count=QConst(2)), source=r.p0,
                     controller=r.p0, decisions=("top", "bottom"))
        self.assertEqual(_rows(r, "SCRY"),
                         [(str(r.p0), ((top, "TOP"), (second, "BOTTOM")), ZONE_LIBRARY, str(r.p0))])

    def test_a_look_is_the_lookers_alone(self) -> None:
        r = _runner([_card("a", 0, zone="library", real="Forest")])
        top = str(r.world.players[r.p0].zone(ZONE_LIBRARY).entries[-1])
        r.ex.execute(atom(Verb.LOOK_AT, controller=ControllerRef.YOU, count=QConst(1)), source=r.p0,
                     controller=r.p0)
        self.assertEqual(_rows(r, "LOOK_AT"), [(str(r.p0), (top,), ZONE_LIBRARY, str(r.p0))])


if __name__ == "__main__":
    unittest.main()
