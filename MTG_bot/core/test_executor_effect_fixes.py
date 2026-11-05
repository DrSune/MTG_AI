"""Second-wave engine fixes, family "effects, objects and conditions" (2026-11-05): one test
class per finding (KNOWLEDGE/2026-11-05/184, tools/scenarios/known_bugs/2026-11-05).

CR 400.7  An object that leaves the battlefield and comes back is a new object: no effect a
          resolved spell or ability applied to the old one applies to it (a pump, a granted
          ability or type, a "doesn't untap"), while a static ability applies to it afresh.
CR 701.21a A player sacrifices a permanent of their own choice as the instruction resolves: the
          menu never takes the ability's target designation (Sorin, Imperious Bloodlord's +1,
          known_bugs sacrifice_takes_the_target).
V11 follow-up  "If it's a Vampire" / "If a Dinosaur is dealt damage this way" / "If that
          creature was an Elemental": a characteristics-only condition is judged on the object
          the previous sentence acted on (damage and ability grants name it too), and after a
          sentence that names no object, on the object the trigger's event names, never on
          the ability's source (known_bugs if_its_reads_the_source, conditional_judged_on_source).
"""

from __future__ import annotations

import unittest

from MTG_bot.core.ability_tree import (
    Atom,
    AtomArgs,
    Conditional,
    ControllerRef,
    CounterKind,
    DurationEot,
    FAnd,
    FAtom,
    FAtomPred,
    Keyword,
    KeywordAbility,
    PtDelta,
    PtDirection,
    QConst,
    Selector,
    SelectorMode,
    Seq,
    Verb,
    Zone,
    ZoneKind,
)
from MTG_bot.core.executor.events import KIND_ZONE_CHANGE
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



BF_ANY = Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY)


class TestCR70121SacrificeIsTheControllersChoice(unittest.TestCase):
    """Sorin, Imperious Bloodlord's +1 as the M20 mapper drew it: "You may sacrifice a Vampire.
    When you do, Sorin deals 3 damage to any target and you gain 3 life." The sacrifice menu is a
    one-of pick (the compiler promotes a count-1 CHOOSE to ONE_OF); the damage is the ability's
    only TARGET."""

    def effect(self):
        vampire_you_control = FAnd((
            FAtom(FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
            FAtom(FAtomPred.SUBTYPE_EQ, string_value="Vampire"),
            FAtom(FAtomPred.TYPE_EQ, string_value="Creature"),
        ))
        return Seq((
            Atom(Verb.SACRIFICE, AtomArgs((
                ("target", Selector(QConst(1), SelectorMode.ONE_OF, vampire_you_control,
                                    zones=(BF_ANY,))),
            ))),
            Atom(Verb.DEAL_DAMAGE, AtomArgs((
                ("amount", QConst(3)),
                ("target", Selector(QConst(1), SelectorMode.TARGET, UNIV, zones=(BF_ANY,))),
            ))),
        ))

    def vampire(self, key, seat):
        return {"key": key, "name": key.title(), "type": "Creature — Vampire", "power": "2",
                "toughness": "2", "zone": "battlefield", "controller": seat}

    def test_the_target_is_not_sacrificed_when_it_is_not_a_choice(self):
        # No Vampire to sacrifice: the targeted opposing Bear is not sacrificed in its place.
        r = runner([bear("sorin", 0), bear("mybear", 0), bear("obear", 1)])
        obear = r.handles["obear"]
        r.ex.apply_effect(self.effect(), source=r.handles["sorin"], controller=r.p0,
                          bindings={"target": [obear]})
        self.assertEqual(r.world.zone_of(r.handles["mybear"]).kind, "battlefield")
        self.assertEqual(r.ex.damage.get(obear), None)  # 3 damage killed it: it died, not sacrificed
        self.assertEqual(r.world.zone_of(obear).kind, "graveyard")
        sacrificed = [e.subject for e in r.ex.journal.events
                      if e.kind == KIND_ZONE_CHANGE and e.cause_verb == "SACRIFICE"]
        self.assertEqual(sacrificed, [])

    def test_the_controller_picks_even_when_the_target_could_be_sacrificed(self):
        # The target is one of your Vampires; you sacrifice the other one, and the target is
        # dealt the 3 damage.
        r = runner([bear("sorin", 0), self.vampire("vtarget", 0), self.vampire("vother", 0)])
        asks = []

        def answer(vocab, what):
            asks.append((what, vocab))
            return str(r.handles["vother"])

        r.ex.decisions.provider = answer
        r.ex.apply_effect(self.effect(), source=r.handles["sorin"], controller=r.p0,
                          bindings={"target": [r.handles["vtarget"]]})
        self.assertEqual(r.world.zone_of(r.handles["vother"]).kind, "graveyard")
        self.assertEqual(r.world.zone_of(r.handles["vtarget"]).kind, "graveyard")  # 3 damage
        self.assertEqual(len(asks), 1)
        self.assertEqual(set(asks[0][1]), {str(r.handles["vtarget"]), str(r.handles["vother"])})



def creature(key, seat, subtype, power="2", toughness="2"):
    return {"key": key, "name": key.title(), "type": f"Creature — {subtype}", "power": power,
            "toughness": toughness, "zone": "battlefield", "controller": seat}


def is_a(subtype):
    return FAnd((FAtom(FAtomPred.SUBTYPE_EQ, string_value=subtype),
                 FAtom(FAtomPred.TYPE_EQ, string_value="Creature")))


SELF = Selector(QConst(1), SelectorMode.CHOOSE, FAtom(FAtomPred.IS_SOURCE), zones=(BF_ANY,))


def referent(name):
    return Selector(QConst(1), SelectorMode.CHOOSE, UNIV,
                    zones=(Zone(ZoneKind.ANY, ControllerRef.ANY),), referent=name)


def counter_on(sel):
    return Atom(Verb.PUT_COUNTER, AtomArgs((
        ("count", QConst(1)), ("counter_kind", CounterKind.PLUS_1_PLUS_1), ("target", sel))))


class TestConditionalSubject(unittest.TestCase):
    def raptor_trigger(self):
        # Marauding Raptor: "... this creature deals 2 damage to it. If a Dinosaur is dealt damage
        # this way, this creature gets +2/+0 until end of turn."
        return Seq((
            Atom(Verb.DEAL_DAMAGE, AtomArgs((("amount", QConst(2)), ("target", referent("event"))))),
            Conditional(pred=is_a("Dinosaur"), then_effect=Atom(Verb.MODIFY_PT, AtomArgs((
                ("duration", DurationEot()),
                ("power", PtDelta(PtDirection.INCREASE, QConst(2))),
                ("target", SELF),
                ("toughness", PtDelta(PtDirection.INCREASE, QConst(0))),
            )))),
        ))

    def test_damage_names_the_object_it_was_dealt_to(self):
        r = runner([creature("raptor", 0, "Dinosaur"), creature("elf", 0, "Elf", "1", "3"),
                    creature("dino", 0, "Dinosaur", "3", "3")])
        raptor = r.handles["raptor"]
        r.ex.apply_effect(self.raptor_trigger(), source=raptor, controller=r.p0,
                          bindings={"event": [r.handles["elf"]]})
        self.assertEqual(pt(r, "raptor"), (2, 2))  # an Elf was dealt the damage
        r.ex.apply_effect(self.raptor_trigger(), source=raptor, controller=r.p0,
                          bindings={"event": [r.handles["dino"]]})
        self.assertEqual(pt(r, "raptor"), (4, 2))  # a Dinosaur was

    def sorin_plus_one(self):
        # Sorin, Imperious Bloodlord's first +1: "Target creature you control gains deathtouch and
        # lifelink until end of turn. If it's a Vampire, put a +1/+1 counter on it."
        target = Selector(QConst(1), SelectorMode.TARGET,
                          FAnd((FAtom(FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
                                FAtom(FAtomPred.TYPE_EQ, string_value="Creature"))),
                          zones=(BF_ANY,))

        def grant(keyword, sel):
            return Atom(Verb.GRANT_ABILITY, AtomArgs((
                ("ability", KeywordAbility(keyword)), ("duration", DurationEot()), ("target", sel))))

        return Seq((
            grant(Keyword.DEATHTOUCH, target),
            grant(Keyword.LIFELINK, referent("target")),
            Conditional(pred=is_a("Vampire"), then_effect=counter_on(referent("target"))),
        ))

    def test_ability_grant_names_the_object_it_was_granted_to(self):
        r = runner([{"key": "sorin", "name": "Sorin", "type": "Legendary Planeswalker — Sorin",
                     "zone": "battlefield", "controller": 0},
                    creature("vamp", 0, "Vampire"), creature("bear", 0, "Bear")])
        for key, want in (("vamp", {"PLUS_1_PLUS_1": 1}), ("bear", {})):
            r.ex.apply_effect(self.sorin_plus_one(), source=r.handles["sorin"], controller=r.p0,
                              bindings={"target": [r.handles[key]]})
            self.assertEqual(dict(r.world.cards[r.handles[key]].counters), want, key)

    def overgrowth_trigger(self):
        # Overgrowth Elemental: "Whenever another creature you control dies, you gain 1 life. If
        # that creature was an Elemental, put a +1/+1 counter on this creature."
        return Seq((
            Atom(Verb.GAIN_LIFE, AtomArgs((("amount", QConst(1)), ("controller", ControllerRef.YOU)))),
            Conditional(pred=is_a("Elemental"), then_effect=counter_on(SELF)),
        ))

    def test_after_a_sentence_naming_no_object_the_event_object_is_judged(self):
        r = runner([creature("og", 0, "Elemental", "3", "2"), creature("bear", 0, "Bear"),
                    creature("elem", 0, "Elemental", "1", "1")])
        og = r.handles["og"]
        for key, want in (("bear", {}), ("elem", {"PLUS_1_PLUS_1": 1})):
            r.run_step({"op": "move", "key": key, "to": "graveyard"})
            r.ex.apply_effect(self.overgrowth_trigger(), source=og, controller=r.p0,
                              bindings={"event": [r.handles[key]]})
            self.assertEqual(dict(r.world.cards[og].counters), want, key)


if __name__ == "__main__":
    unittest.main()
