"""Ontology gate round W3 (DESIGN_ATOM_ONTOLOGY §19) in the engine: state triggers (CR 603.8),
"that ability triggers an additional time" as a static (CR 603.2d), and the records of what a
reveal, a look and a scry showed (CR 701.20a, 701.22a). Each test fails on main 0b7f9c22 (the
note on each says how), except the controls, which pass on both and say so: a state that does
not hold, the Tome's one exile, and Yarok's two triggers that no entering of his caused. The
tests of the fresh review's fixes fail at the round's first commit, 62cd34d8, and say so."""

from __future__ import annotations

import unittest
from functools import cache

from MTG_bot.core.ability_tree import (
    AbilityTriggerEvent,
    Atom,
    AtomArgs,
    Conditional,
    ControllerRef,
    EachPlayer,
    FAtom,
    FAtomPred,
    Phase,
    QConst,
    Selector,
    SelectorMode,
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
from MTG_bot.core.executor.legality import TURN_ENDED
from MTG_bot.core.state import (
    ZONE_BATTLEFIELD,
    ZONE_EXILE,
    ZONE_GRAVEYARD,
    ZONE_HAND,
    ZONE_LIBRARY,
    GameWorld,
)
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
    """The ``kind`` rows of the event log as (owner, cards, zone, viewers, form), one per group of
    a row (verbs._seen: one row per atom, ((owner, zone, cards), ...), viewers, form)."""
    return [(owner, cards, zone, e[3], e[4]) for e in r.ex.events if e[1] == kind for owner, zone, cards in e[2]]


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
                ("If a source would deal damage to you, prevent that damage and put an incarnation "
                 "counter on this enchantment."),
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
        """A control: eight counters are no state (it passes on main too)."""
        self.counters(7)
        with self.ex.holding_priority():
            self.hit(1)
            self.assertEqual(self.waiting(), [])  # eight: no state
        self.ex._settle()
        self.assertEqual(self.world.zone_of(self.nine).kind, ZONE_BATTLEFIELD)

    def test_a_new_object_triggers_on_its_own(self) -> None:
        """CR 603.8 with 400.7: an instance blocks the object it triggered for; Nine Lives that
        left and came back is a new object, which triggers for itself while the old instance
        waits. Once engine wave W1 fixes F14 the old instance finds no "it" to exile (the new
        object is not it); until then it exiles the new object (gate round W3's review, MINOR-1),
        which this test does not pin."""
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

    def test_an_instance_the_turn_ending_exiled_triggers_again_in_the_cleanup(self) -> None:
        """CR 724.1b with 603.8: an effect ending the turn exiles the waiting instance from the
        stack, and what triggers is held until the cleanup step (CR 724.1c); there the state
        still holds, so it triggers again and resolves (CR 514.3a). On main the exiled trigger
        was gone for good and Nine Lives stayed."""
        self.ex.begin_turn(self.p0)
        self.counters(8)
        with self.ex.holding_priority():
            self.hit(1)
            (first,) = self.waiting()
            self.ex.execute(atom(Verb.END_TURN), source=self.p1, controller=self.p1)
            self.assertNotIn(first, self.ex.stack.frames)
            self.assertEqual(self.world.zone_of(self.nine).kind, ZONE_BATTLEFIELD)
        self.ex.pass_until(TURN_ENDED)
        self.assertEqual(self.world.zone_of(self.nine).kind, ZONE_EXILE)


class TestMazemindTome(unittest.TestCase):
    """M21 and FDN Mazemind Tome: the fourth page counter, paid as a cost, triggers the state; it
    exiles the Tome and you gain 4 life, once."""

    def test_the_fourth_page_counter_exiles_it_once(self) -> None:
        """A control on the re-baked record (it passes on main too)."""
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
        """A control: Yarok's static reads his controller's permanents (it passes on main too)."""
        r = self.runner(_card("foe", 1, zone="hand"))
        r.run_step({"op": "enter", "key": "foe"})
        self.assertEqual(self.life(r, 1), 21)

    def test_a_trigger_no_entering_caused_triggers_once(self) -> None:
        """A control: no entering caused an upkeep trigger (it passes on main too)."""
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


class TestCauses(unittest.TestCase):
    def test_every_object_a_gathered_trigger_gathered_caused_it(self) -> None:
        """CR 603.2c-d: "whenever one or more creatures you control enter" triggered on the Human
        and the Wizard alike, so a Wizard entering caused it (Naban, Dean of Iteration), whichever
        row the binder matched first. At 62cd34d8 the cause was matched against that first row
        alone, the Human's, and the ability triggered once."""
        r = _runner([
            _card("naban", 0), _card("watcher", 0),
            _card("human", 0, zone="hand", type="Creature — Human"),
            _card("wizard", 0, zone="hand", type="Creature — Human Wizard"),
        ])
        anywhere = Zone(ZoneKind.ANY, ControllerRef.ANY)
        yours = Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU)
        wizard_enters = ZoneChangeEvent(anywhere, yours, FAtom(pred=FAtomPred.SUBTYPE_EQ, string_value="Wizard"))
        creatures_enter = ZoneChangeEvent(anywhere, yours, FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"))
        gathered = TriggeredAbility(event=creatures_enter, condition=None, effect=GAIN_1, once_per_event=True)
        for key, ability in (("naban", _doubler(AbilityTriggerEvent(filter=ME, cause=wizard_enters))),
                             ("watcher", gathered)):
            h = r.handles[key]
            r.ex.attach_card(h, record_of([ability], name=key, oid=r.world.cards[h].identity.oracle_id))
        r.run_step({"op": "move", "keys": ["human", "wizard"], "to": "battlefield"})
        self.assertEqual(r.world.players[r.p0].life, 22)


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
        self.assertEqual(_rows(r, "REVEAL"), [(str(r.p1), hand, ZONE_HAND, "ALL", "hand")])
        self.assertEqual(r.world.zone_of(r.handles["shock"]).kind, "graveyard")

    def test_an_empty_hand_is_revealed_as_nothing(self) -> None:
        """M21 Duress at an empty hand: one row that names nothing, to all (one row per atom: a
        later random order is seeded by the event count). On main it listed the library."""
        r = _runner([_card("duress", 0, zone="hand", real="Duress"), _card("deep", 1, zone="library")])
        r.world.players[r.p0].mana_pool["B"] = 1
        r.run_step({"op": "cast", "key": "duress", "targets": ["p1"]})
        self.assertEqual([e[2:] for e in r.ex.events if e[1] == "REVEAL"], [((), "ALL", "hand")])

    def test_a_reveal_names_each_owners_zone(self) -> None:
        """A reveal's cards are grouped by the zone holding them, its owner named (CR 400.3)."""
        # not on main: imported here, so the module imports there and its other tests run
        # (reports/w3_2026-11-18/engine_tests_on_main.txt)
        from MTG_bot.core.ability_tree import reveal_result

        r = _runner([_card("mine", 0, zone="hand"), _card("theirs", 1, zone="graveyard")])
        mine, theirs = r.handles["mine"], r.handles["theirs"]
        r.ex.execute(reveal_result(), source=r.p0, controller=r.p0, bindings={"result": [mine, theirs]})
        self.assertEqual(_rows(r, "REVEAL"), [(str(r.p0), (str(mine),), ZONE_HAND, "ALL", "result"),
                                              (str(r.p1), (str(theirs),), ZONE_GRAVEYARD, "ALL", "result")])

    def test_each_player_reveals_their_own_hand_and_looks_alone(self) -> None:
        """Under EachPlayer the reveal runs once per player, each row that player's hand; a look
        there is each looker's alone (the rotated controller)."""
        from MTG_bot.core.ability_tree import reveal_hand  # not on main (above)

        r = _runner([_card("mine", 0, zone="hand"), _card("theirs", 1, zone="hand"),
                     _card("a", 0, zone="library"), _card("b", 1, zone="library")])
        each = ControllerRef.ANY
        r.ex.apply_effect(EachPlayer(ref=each, effect=reveal_hand(ControllerRef.YOU)), source=r.p0, controller=r.p0)
        self.assertEqual(_rows(r, "REVEAL"), [(str(r.p0), (str(r.handles["mine"]),), ZONE_HAND, "ALL", "hand"),
                                              (str(r.p1), (str(r.handles["theirs"]),), ZONE_HAND, "ALL", "hand")])
        look = atom(Verb.LOOK_AT, controller=ControllerRef.YOU, count=QConst(1))
        r.ex.apply_effect(EachPlayer(ref=each, effect=look), source=r.p0, controller=r.p0)
        self.assertEqual([(owner, viewers, form) for owner, _cards, _zone, viewers, form in _rows(r, "LOOK_AT")],
                         [(str(r.p0), str(r.p0), "top"), (str(r.p1), str(r.p1), "top")])

    def test_the_card_revealed_is_the_next_sentences_it(self) -> None:
        """"Search your library for a card, reveal it. If it's a creature card, ...": the card
        found stays the fresh ``result`` through its reveal (run_atom's ``result_fresh``), as the
        old top-card reveal left it, so the bare Conditional judges it, not the source (a Shock).
        At 62cd34d8 the reveal left the register stale and the Conditional judged the Shock."""
        from MTG_bot.core.ability_tree import reveal_result  # not on main (above)

        r = _runner([_card("shock", 0, zone="hand", real="Shock"), _card("bear", 0, zone="library")])
        creature = FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature")
        search = atom(Verb.SEARCH, cards=Selector(QConst(1), SelectorMode.CHOOSE, creature,
                                                  zones=(Zone(ZoneKind.LIBRARY, ControllerRef.YOU),)),
                      destination=Zone(ZoneKind.HAND, ControllerRef.YOU))
        r.ex.apply_effect(Seq(steps=(search, reveal_result(), Conditional(pred=creature, then_effect=GAIN_1))),
                          source=r.handles["shock"], controller=r.p0, bindings={"cards": [r.handles["bear"]]})
        self.assertEqual(r.world.zone_of(r.handles["bear"]).kind, ZONE_HAND)
        self.assertEqual(r.world.players[r.p0].life, 21)

    def test_fierce_empath_reveals_the_card_found(self) -> None:
        """M21 Fierce Empath: "reveal it" names the card the search found, now in the hand. On
        main the row named the library's new top card, which nobody saw."""
        r = _runner([
            _card("empath", 0, zone="hand", real="Fierce Empath"),
            _card("big", 0, zone="library", real="Pursued Whale"),
            _card("top", 0, zone="library", real="Llanowar Visionary"),
        ])
        r.run_step({"op": "enter", "key": "empath", "decisions": ["fire", "big"]})
        self.assertEqual(_rows(r, "REVEAL"), [(str(r.p0), (str(r.handles["big"]),), ZONE_HAND, "ALL", "result")])

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
        self.assertEqual(_rows(r, "REVEAL"), [(str(r.p0), (str(r.handles["basri"]),), ZONE_HAND, "ALL", "result")])

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
        self.assertEqual(_rows(r, "REVEAL"), [(str(r.p0), (str(r.handles["bear"]),), ZONE_HAND, "ALL", "result")])

    def test_a_scry_names_each_card_and_its_end_for_the_scryer(self) -> None:
        """CR 701.22a: the scryer sees the cards, and the table how many went to each end; main's
        row held only how many were scried."""
        r = _runner([_card("a", 0, zone="library", real="Forest")])
        library = r.world.players[r.p0].zone(ZONE_LIBRARY).entries
        top, second = str(library[-1]), str(library[-2])
        r.ex.execute(atom(Verb.SCRY, controller=ControllerRef.YOU, count=QConst(2)), source=r.p0,
                     controller=r.p0, decisions=("top", "bottom"))
        self.assertEqual(_rows(r, "SCRY"),
                         [(str(r.p0), ((top, "TOP"), (second, "BOTTOM")), ZONE_LIBRARY, str(r.p0), "top")])
        # the public part, everyone's: one card went back on top, one to the bottom
        self.assertEqual([e[5] for e in r.ex.events if e[1] == "SCRY"], [(1, 1)])

    def test_a_look_is_the_lookers_alone(self) -> None:
        r = _runner([_card("a", 0, zone="library", real="Forest")])
        top = str(r.world.players[r.p0].zone(ZONE_LIBRARY).entries[-1])
        r.ex.execute(atom(Verb.LOOK_AT, controller=ControllerRef.YOU, count=QConst(1)), source=r.p0,
                     controller=r.p0)
        self.assertEqual(_rows(r, "LOOK_AT"), [(str(r.p0), (top,), ZONE_LIBRARY, str(r.p0), "top")])


class TestSeenRows(unittest.TestCase):
    """The gate's MINOR-5: the rows a memory may read (``verbs.SEEN_VERBS``) each say who saw their
    cards and what the cards are; the other rows that name hidden cards (a SEARCH's, a MOVE's)
    say neither and are no one's knowledge (DESIGN_ATOM_ONTOLOGY §19). Four seeded random games
    of the "all" pools write every form today (M21 0: a scry and a found card's reveal; M21 3: a
    reveal of the top; M20 0: a hand; M20 3: a look). At 5a310010 the rows carried no form, on
    main no viewers either."""

    def test_every_seen_row_names_its_viewers_and_what_its_cards_are(self) -> None:
        # not on main (TestReveals' note)
        from MTG_bot.core.executor import games
        from MTG_bot.core.executor.verbs import SEEN_FORMS, SEEN_VERBS

        rows = []
        for code, seed in (("M21", 0), ("M21", 3), ("M20", 0), ("M20", 3)):
            supply = games.get_supply("all", code)
            game = games._setup_game(seed, supply, games.deal_decks(seed, 1409, supply, "stress"))
            games._play(game, games.RandomPolicy(seed), game.world.player_order, games.TURN_CAP)
            players = {str(p) for p in game.world.player_order}
            rows += [(e, players) for e in game.executor.events if e[1] in SEEN_VERBS]
        self.assertTrue(rows)
        for e, players in rows:
            with self.subTest(row=e):
                scry = e[1] == "SCRY"
                self.assertEqual(len(e), 6 if scry else 5)
                self.assertIn(e[3], {"ALL"} if e[1] == "REVEAL" else players)
                self.assertIn(e[4], SEEN_FORMS)
                named = 0
                for owner, zone, cards in e[2]:
                    self.assertIn(owner, players)
                    for card in cards:
                        handle = card[0] if scry else card
                        self.assertTrue(handle.startswith("card:"), handle)
                        named += 1
                    self.assertIsInstance(zone, str)
                if scry:  # the public part: how many went to each end, the cards' count
                    self.assertEqual(sum(e[5]), named)


if __name__ == "__main__":
    unittest.main()
