"""Second-wave engine fixes, family "effects, objects and conditions" (2026-11-05): one test
class per finding (KNOWLEDGE/2026-11-05/184, tools/scenarios/known_bugs/2026-11-05).

CR 400.7  An object that leaves the battlefield and comes back is a new object: no effect a
          resolved spell or ability applied to the old one applies to it (a pump, a granted
          ability or type, a "doesn't untap"), while a static ability applies to it afresh.
"""

from __future__ import annotations

import unittest

from MTG_bot.core.ability_tree import (
    Atom,
    AtomArgs,
    ControllerRef,
    FAnd,
    QConst,
    Selector,
    SelectorMode,
    Seq,
    Verb,
    Zone,
    ZoneKind,
)
from MTG_bot.core.executor.games import get_supply
from tools.run_scenarios import ScenarioRunner

UNIV = FAnd(())


def runner(cards, mana=None, life=20):
    pack = {"world": {"life": life, "seed": 7}, "cards": cards, "steps": [], "expect": {}}
    if mana:
        pack["mana"] = mana
    return ScenarioRunner(pack, get_supply("all", "M21"))


def bear(key, seat, zone="battlefield", name=None):
    return {"key": key, "name": name or key.title(), "type": "Creature — Bear",
            "power": "2", "toughness": "2", "zone": zone, "controller": seat}


def pt(r, key):
    h = r.handles[key]
    return r.ex.ledger.effective_pt(r.world.cards[h].identity, h, r.world.cards[h].counters)


def leave_and_return(r, key):
    """Bounce the permanent to its owner's hand and put it back onto the battlefield."""
    r.run_step({"op": "move", "key": key, "to": "hand"})
    r.run_step({"op": "enter", "key": key})


class TestCR4007NewObject(unittest.TestCase):
    def test_pump_does_not_follow_the_creature_back(self):
        # Titanic Growth: "Target creature gets +4/+4 until end of turn." Bounced and replayed
        # the same turn, the Bear is a new object: a 2/2.
        r = runner([{"key": "tg", "real": "Titanic Growth", "zone": "hand", "controller": 0},
                    bear("bear", 0)], mana={"0": {"G": 2}})
        r.run_step({"op": "cast", "key": "tg", "controller": 0, "targets": ["bear"]})
        self.assertEqual(pt(r, "bear"), (6, 6))
        leave_and_return(r, "bear")
        self.assertEqual(pt(r, "bear"), (2, 2))

    def test_granted_keyword_does_not_follow_the_creature_back(self):
        # Sure Strike: "+3/+0 and gains first strike until end of turn."
        r = runner([{"key": "ss", "real": "Sure Strike", "zone": "hand", "controller": 0},
                    bear("bear", 0)], mana={"0": {"R": 2}})
        r.run_step({"op": "cast", "key": "ss", "controller": 0, "targets": ["bear"]})
        bear_h = r.handles["bear"]
        self.assertTrue(r.ex.layers.keyword_of(bear_h, "FIRST_STRIKE"))
        leave_and_return(r, "bear")
        self.assertFalse(r.ex.layers.keyword_of(bear_h, "FIRST_STRIKE"))
        self.assertEqual(pt(r, "bear"), (2, 2))

    def test_granted_type_does_not_follow_the_permanent_back(self):
        # A resolved "it becomes an Elemental creature in addition to its other types" with no
        # end (the Wakeroot Elemental shape, known_bugs cr400_7): the land that returns is a
        # plain land.
        r = runner([{"key": "land", "name": "Forest", "type": "Basic Land — Forest",
                     "zone": "battlefield", "controller": 0}, bear("wakeroot", 0)])
        land = r.handles["land"]
        r.ex.execute(
            Atom(Verb.GRANT_TYPE, AtomArgs((
                ("target", Selector(QConst(1), SelectorMode.TARGET, UNIV,
                                    zones=(Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),))),
                ("types", ("Creature", "Elemental")),
            ))),
            source=r.handles["wakeroot"], controller=r.p0, bindings={"target": [land]},
        )
        self.assertEqual(r.ex.layers.type_overlay(land), ("Creature", "Elemental"))
        r.run_step({"op": "move", "key": "land", "to": "hand"})
        r.run_step({"op": "play", "key": "land"})
        self.assertEqual(r.ex.layers.type_overlay(land), ())

    def test_freeze_does_not_follow_the_creature_back(self):
        # Frost Breath on the opponent's Bear, which is then bounced and replayed: the new Bear
        # untaps as usual in its controller's next untap step.
        r = runner([{"key": "fb", "real": "Frost Breath", "zone": "hand", "controller": 0},
                    bear("obear", 1)], mana={"0": {"U": 3}})
        r.run_step({"op": "cast", "key": "fb", "controller": 0, "targets": ["obear"]})
        obear = r.handles["obear"]
        leave_and_return(r, "obear")
        r.world.cards[obear].tapped = True  # tapped again by something else
        r.run_step({"op": "advance_turn"})
        self.assertFalse(r.world.cards[obear].tapped)

    def test_static_bonus_applies_to_the_returned_creature(self):
        # The new object is not cut off from static abilities: Feline Sovereign's "Other Cats
        # you control get +1/+1" covers a Cat that left and came back within one effect.
        r = runner([{"key": "fs", "real": "Feline Sovereign", "zone": "battlefield", "controller": 0},
                    {"key": "cat", "name": "Cat", "type": "Creature — Cat", "power": "2",
                     "toughness": "2", "zone": "battlefield", "controller": 0}])
        cat = r.handles["cat"]
        self.assertEqual(pt(r, "cat"), (3, 3))
        bounce_and_return = (
            Atom(Verb.MOVE_ZONE, AtomArgs((
                ("cards", Selector(QConst(1), SelectorMode.TARGET, UNIV,
                                   zones=(Zone(ZoneKind.ANY, ControllerRef.ANY),))),
                ("destination", Zone(ZoneKind.EXILE, ControllerRef.OWNER)),
            ))),
            Atom(Verb.MOVE_ZONE, AtomArgs((
                ("cards", Selector(QConst(1), SelectorMode.TARGET, UNIV,
                                   zones=(Zone(ZoneKind.ANY, ControllerRef.ANY),))),
                ("destination", Zone(ZoneKind.BATTLEFIELD, ControllerRef.OWNER)),
            ))),
        )
        r.ex.apply_effect(Seq(bounce_and_return), source=cat, controller=r.p0,
                          bindings={"cards": [cat]})
        self.assertEqual(pt(r, "cat"), (3, 3))

    def test_effect_still_answers_for_the_departed_object(self):
        # Last known information is untouched: while the pumped Bear is in the graveyard, a
        # read of its power (Heartfire Immolator's "damage equal to its power" after it was
        # sacrificed) still sees the pump; only a return to the battlefield ends it.
        r = runner([{"key": "tg", "real": "Titanic Growth", "zone": "hand", "controller": 0},
                    bear("bear", 0)], mana={"0": {"G": 2}})
        r.run_step({"op": "cast", "key": "tg", "controller": 0, "targets": ["bear"]})
        r.run_step({"op": "move", "key": "bear", "to": "graveyard"})
        self.assertEqual(pt(r, "bear"), (6, 6))



if __name__ == "__main__":
    unittest.main()
