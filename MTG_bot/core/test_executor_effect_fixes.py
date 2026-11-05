"""Second-wave engine fixes, family "effects, objects and conditions" (2026-11-05): one test
class per finding (KNOWLEDGE/2026-11-05/184, tools/scenarios/known_bugs/2026-11-05).

CR 400.7  An object that leaves the battlefield is a new object in its new zone: no effect a
          resolved spell or ability applied to the old one applies to it (a pump, a granted
          ability or type, a "doesn't untap"), neither in the graveyard (Carrion Grub reads a
          dead creature card's printed power) nor if it comes back, while a static ability
          applies afresh to an object that returns.
LKI       What needs the object as it last existed reads one snapshot taken as it left (CR
          608.2h, 113.7a, 603.10a, 603.3a): a sacrificed or dead source deals damage with the
          deathtouch or lifelink it had been granted, a stolen creature's own dies trigger is
          controlled by the player who controlled it, and a later read of a card in a graveyard
          sees no controller but its owner (CR 108.4a).
CR 701.21a A player sacrifices a permanent of their own choice as the instruction resolves: the
          menu never takes the ability's target designation (Sorin, Imperious Bloodlord's +1,
          known_bugs sacrifice_takes_the_target).
V11 follow-up  "If it's a Vampire" / "If a Dinosaur is dealt damage this way" / "If that
          creature was an Elemental": a characteristics-only condition is judged on the object
          the previous sentence acted on (damage and ability grants name it too), and after a
          sentence that names no object, on the object the trigger's event names, never on
          the ability's source (known_bugs if_its_reads_the_source, conditional_judged_on_source).
CR 608.2h "Its controller" after the object left the battlefield is the controller it last had
          there, not its owner (Angelic Ascension, Secure the Scene, Liliana, Death Mage's -3
          on a creature Traitorous Greed took). CR 603.10a: a dies trigger looks back in time,
          so Massacre Wurm's "a creature an opponent controls dies, that player loses 2 life"
          reads the controller at death.
CR 611.2a An effect a resolved spell or ability created lasts as long as its duration says,
          whatever happens to its source (B-50: Keen Glidemaster's flying, Pack Leader's damage
          prevention, Subira's "can't be blocked", Mu Yanling's "loses flying until your next
          turn" ended when the source left), and a "can't block" with no end or "until your next
          turn" applies at all (known_bugs cant_block_needs_until_end_of_turn). "Gain control of
          target creature" with no duration lasts the game, not as long as the permanent whose
          ability it was (known_bugs cr611_2a_control_ends_with_granter).
"""

from __future__ import annotations

import unittest

from MTG_bot.core.ability_tree import (
    Atom,
    AtomArgs,
    CardRecord,
    Conditional,
    ControllerRef,
    CounterKind,
    CounterPlacedEvent,
    DamageDealtEvent,
    DeclareBlockersEvent,
    DurationEot,
    DurationUntilNextTurn,
    EtBState,
    FAnd,
    FAtom,
    FAtomPred,
    FNot,
    Keyword,
    KeywordAbility,
    PtDelta,
    PtDirection,
    QConst,
    QUnbounded,
    Selector,
    SelectorMode,
    Seq,
    StaticAbility,
    TriggeredAbility,
    Verb,
    Zone,
    ZoneKind,
)
from MTG_bot.core.executor.events import KIND_ZONE_CHANGE
from MTG_bot.core.executor.games import get_supply
from MTG_bot.core.identity import CardIdentity
from tools.run_scenarios import ScenarioRunner

UNIV = FAnd(())
BF_ANY = Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY)


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

    def test_a_granted_type_ends_as_the_permanent_leaves(self):
        # Riddleform: "... you may have Riddleform become a 3/3 Sphinx creature with flying in
        # addition to its other types until end of turn." Dead in combat, it is an enchantment
        # card in the graveyard, not a creature card a "return target creature card" could take.
        r = runner([{"key": "riddle", "name": "Riddle", "type": "Enchantment",
                     "zone": "battlefield", "controller": 0}])
        riddle = r.handles["riddle"]
        r.ex.execute(
            Atom(Verb.GRANT_TYPE, AtomArgs((
                ("duration", DurationEot()),
                ("target", Selector(QConst(1), SelectorMode.CHOOSE, FAtom(FAtomPred.IS_SOURCE),
                                    zones=(BF_ANY,))),
                ("types", ("Creature", "Sphinx")),
            ))),
            source=riddle, controller=r.p0,
        )
        self.assertEqual(r.ex.layers.type_overlay(riddle), ("Creature", "Sphinx"))
        r.run_step({"op": "move", "key": "riddle", "to": "graveyard"})
        self.assertEqual(r.ex.layers.type_overlay(riddle), ())

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

    def test_a_dead_creature_card_has_its_printed_power(self):
        # Carrion Grub: "+X/+0, where X is the greatest power among creature cards in your
        # graveyard." A Titanic Growth'd 2/2 that died is a 2/2 card in the graveyard (the Grub
        # read it as 6/5); a 3/3 killed by Grasp of Darkness is a 3/3 card (it read -1/5).
        r = runner([{"key": "grub", "real": "Carrion Grub", "zone": "battlefield", "controller": 0},
                    {"key": "tg", "real": "Titanic Growth", "zone": "hand", "controller": 0},
                    bear("mine", 0), bear("killer", 1, name="Killer")], mana={"0": {"G": 2}})
        r.run_step({"op": "cast", "key": "tg", "controller": 0, "targets": ["mine"]})
        r.run_step({"op": "deal_damage", "source": "killer", "target": "mine", "amount": 9,
                    "controller": 1})
        self.assertEqual(r.world.zone_of(r.handles["mine"]).kind, "graveyard")
        self.assertEqual((pt(r, "mine"), pt(r, "grub")), ((2, 2), (2, 5)))
        r = runner([{"key": "grub", "real": "Carrion Grub", "zone": "battlefield", "controller": 0},
                    {"key": "gd", "real": "Grasp of Darkness", "zone": "hand", "controller": 1},
                    {"key": "mine", "name": "Mine", "type": "Creature — Bear", "power": "3",
                     "toughness": "3", "zone": "battlefield", "controller": 0}],
                   mana={"1": {"B": 2}})
        r.run_step({"op": "cast", "key": "gd", "controller": 1, "targets": ["mine"]})
        self.assertEqual(pt(r, "grub"), (3, 5))




def answering(r, step, choose):
    """Run ``step`` answering every ask with ``choose(what, vocab)``; returns the asks seen."""
    seen = []

    def provider(vocab, what):
        word = choose(what, vocab)
        seen.append((what, tuple(vocab), word))
        return word

    r.ex.decisions.provider = provider
    try:
        r._dispatch(step)
    finally:
        r.ex.decisions.provider = None
    return seen


def steal(r, thief, key):
    """Traitorous Greed (in ``thief``'s hand under key "greed") takes ``key``."""
    r.run_step({"op": "mana", "seat": thief, "add": {"R": 4}})
    answering(r, {"op": "cast", "key": "greed", "controller": thief, "targets": [key]},
              lambda what, vocab: "R" if "R" in vocab else vocab[0])
    assert r.ex.controller_of(r.handles[key]) == r.seats[thief]


class TestLastKnownInformation(unittest.TestCase):
    def gifted_immolator(self, word):
        """Alchemist's Gift on Heartfire Immolator (word "0": deathtouch, "1": lifelink): a 4/4
        with prowess; then "{R}, Sacrifice: It deals damage equal to its power" at a 5/5."""
        r = runner([{"key": "gift", "real": "Alchemist's Gift", "zone": "hand", "controller": 0},
                    {"key": "imm", "real": "Heartfire Immolator", "zone": "battlefield",
                     "controller": 0},
                    {"key": "big", "name": "Big", "type": "Creature — Beast", "power": "5",
                     "toughness": "5", "zone": "battlefield", "controller": 1}],
                   mana={"0": {"B": 2}})
        answering(r, {"op": "cast", "key": "gift", "controller": 0, "targets": ["imm"]},
                  lambda what, vocab: word if word in vocab else vocab[0])
        self.assertEqual(pt(r, "imm"), (4, 4))
        r.run_step({"op": "mana", "seat": 0, "add": {"R": 1}})
        r.run_step({"op": "activate", "key": "imm", "idx": 0, "seat": 0, "targets": ["big"]})
        self.assertEqual(r.world.zone_of(r.handles["imm"]).kind, "graveyard")
        return r

    def test_a_sacrificed_source_deals_damage_with_its_granted_deathtouch(self):
        # CR 113.7a, 608.2h: the Immolator left the battlefield, so the damage uses its last
        # known information: 4 damage (its power) with the deathtouch it was granted.
        r = self.gifted_immolator("0")
        self.assertEqual(r.world.zone_of(r.handles["big"]).kind, "graveyard")

    def test_a_sacrificed_source_deals_damage_with_its_granted_lifelink(self):
        r = self.gifted_immolator("1")
        self.assertEqual(r.world.players[r.p0].life, 24)

    def test_a_dead_creatures_trigger_deals_damage_with_its_granted_deathtouch(self):
        # Pitchburn Devils: "When this creature dies, it deals 3 damage to any target."
        r = runner([{"key": "gift", "real": "Alchemist's Gift", "zone": "hand", "controller": 0},
                    {"key": "dev", "real": "Pitchburn Devils", "zone": "battlefield",
                     "controller": 0},
                    {"key": "big", "name": "Big", "type": "Creature — Beast", "power": "5",
                     "toughness": "5", "zone": "battlefield", "controller": 1},
                    bear("killer", 1, name="Killer")], mana={"0": {"B": 2}})
        answering(r, {"op": "cast", "key": "gift", "controller": 0, "targets": ["dev"]},
                  lambda what, vocab: "0" if "0" in vocab else vocab[0])
        big = str(r.handles["big"])
        answering(r, {"op": "deal_damage", "source": "killer", "target": "dev", "amount": 9,
                      "controller": 1},
                  lambda what, vocab: big if big in vocab else vocab[0])
        self.assertEqual(r.world.zone_of(r.handles["big"]).kind, "graveyard")

    def test_a_sacrificed_source_deals_damage_equal_to_its_last_known_power(self):
        # Heartfire Immolator pumped by Titanic Growth (a 6/6, with prowess 7/7) and sacrificed:
        # "damage equal to its power" is 7, not the printed 2.
        r = runner([{"key": "tg", "real": "Titanic Growth", "zone": "hand", "controller": 0},
                    {"key": "imm", "real": "Heartfire Immolator", "zone": "battlefield",
                     "controller": 0},
                    {"key": "big", "name": "Big", "type": "Creature — Beast", "power": "8",
                     "toughness": "8", "zone": "battlefield", "controller": 1}],
                   mana={"0": {"G": 2}})
        r.run_step({"op": "cast", "key": "tg", "controller": 0, "targets": ["imm"]})
        self.assertEqual(pt(r, "imm"), (7, 7))
        r.run_step({"op": "mana", "seat": 0, "add": {"R": 1}})
        r.run_step({"op": "activate", "key": "imm", "idx": 0, "seat": 0, "targets": ["big"]})
        self.assertEqual(r.ex.damage.get(r.handles["big"]), 7)

    def test_a_stolen_creatures_dies_trigger_is_controlled_by_the_thief(self):
        # Spirit of Malevolence: "When this creature dies, each opponent loses 1 life and you
        # gain 1 life." Seat 0 took it with Traitorous Greed and it died under seat 0 (CR
        # 603.3a, 603.10a): seat 0 is "you".
        r = runner([{"key": "greed", "real": "Traitorous Greed", "zone": "hand", "controller": 0},
                    {"key": "sp", "real": "Spirit of Malevolence", "zone": "battlefield",
                     "controller": 1}, bear("killer", 0, name="Killer")])
        steal(r, 0, "sp")
        r.run_step({"op": "deal_damage", "source": "killer", "target": "sp", "amount": 9})
        self.assertEqual((r.world.players[r.p0].life, r.world.players[r.p1].life), (21, 19))

    def test_a_dies_trigger_reads_its_controller_after_the_card_moved_on(self):
        # Massacre Wurm's trigger for a creature the opponent took from you waits; the dead card
        # moves on (graveyard to hand) before it resolves. "That player" is still the opponent,
        # who controlled it as it died.
        r = runner([{"key": "wurm", "real": "Massacre Wurm", "zone": "battlefield", "controller": 0},
                    {"key": "greed", "real": "Traitorous Greed", "zone": "hand", "controller": 1},
                    bear("mine", 0)])
        r.run_step({"op": "advance_turn"})
        steal(r, 1, "mine")
        r.ex.binder.hold = True
        try:
            r.ex.execute(Atom(Verb.DEAL_DAMAGE, AtomArgs((
                ("amount", QConst(2)),
                ("target", Selector(QConst(1), SelectorMode.TARGET, UNIV, zones=(BF_ANY,))),
            ))), source=r.handles["wurm"], controller=r.p0, bindings={"target": r.handles["mine"]})
        finally:
            r.ex.binder.hold = False
        r.run_step({"op": "move", "key": "mine", "to": "hand"})
        self.assertEqual((r.world.players[r.p0].life, r.world.players[r.p1].life), (20, 18))

    def test_a_card_in_a_graveyard_has_no_controller_but_its_owner_later(self):
        # CR 108.4a: two turns after a stolen Bear died, "its controller" of the card in its
        # owner's graveyard is its owner.
        from MTG_bot.core.executor.selectors import last_known_controller

        r = runner([{"key": "greed", "real": "Traitorous Greed", "zone": "hand", "controller": 0},
                    bear("ob", 1), bear("killer", 0, name="Killer")])
        steal(r, 0, "ob")
        r.run_step({"op": "deal_damage", "source": "killer", "target": "ob", "amount": 5})
        r.run_step({"op": "advance_turn"})
        r.run_step({"op": "advance_turn"})
        ctx = r.ex._ctx(source=r.handles["killer"], controller=r.p0, bindings={}, decisions=())
        self.assertEqual(last_known_controller(ctx, r.handles["ob"]), r.p1)


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



class TestCR6082hLastKnownController(unittest.TestCase):
    """Seat 0 takes the opponent's Bear with Traitorous Greed, then removes it."""

    def stolen(self, extra, mana):
        r = runner([{"key": "greed", "real": "Traitorous Greed", "zone": "hand", "controller": 0},
                    bear("obear", 1), *extra], mana=mana)
        r.run_step({"op": "cast", "key": "greed", "controller": 0, "targets": ["obear"],
                    "decisions": ["R"]})
        self.assertEqual(r.ex.controller_of(r.handles["obear"]), r.p0)
        return r

    def token_seats(self, r, name):
        return [r.seats.index(r.ex.controller_of(h)) for h, c in r.world.cards.items()
                if c.identity.name == name and r.world.zone_of(h).kind == "battlefield"]

    def test_exiled_creatures_controller_gets_the_token(self):
        for spell, token in (("Angelic Ascension", "Angel"), ("Secure the Scene", "Soldier")):
            r = self.stolen([{"key": "x", "real": spell, "zone": "hand", "controller": 0}],
                            {"0": {"R": 4, "W": 5, "C": 5}})
            r.run_step({"op": "cast", "key": "x", "controller": 0, "targets": ["obear"]})
            self.assertEqual(r.world.zone_of(r.handles["obear"]).kind, "exile")
            self.assertEqual(self.token_seats(r, token), [0], spell)

    def test_destroyed_creatures_controller_loses_the_life(self):
        r = self.stolen([{"key": "lili", "real": "Liliana, Death Mage", "zone": "battlefield",
                          "controller": 0}], {"0": {"R": 4}})
        r.run_step({"op": "loyalty", "key": "lili", "set": 4})
        r.run_step({"op": "activate", "key": "lili", "idx": 1, "seat": 0, "targets": ["obear"]})
        self.assertEqual((r.world.players[r.p0].life, r.world.players[r.p1].life), (18, 20))

    def wurm_sees(self, thief):
        """Seat ``thief`` steals the other seat's Bear with Traitorous Greed on its own turn;
        seat 0's Massacre Wurm is on the battlefield; the Bear dies under the thief."""
        owner = 1 - thief
        r = runner([{"key": "wurm", "real": "Massacre Wurm", "zone": "battlefield", "controller": 0},
                    {"key": "greed", "real": "Traitorous Greed", "zone": "hand", "controller": thief},
                    bear("bear", owner)])
        if thief == 1:
            r.run_step({"op": "advance_turn"})
        r.run_step({"op": "mana", "seat": thief, "add": {"R": 4}})
        r.run_step({"op": "cast", "key": "greed", "controller": thief, "targets": ["bear"],
                    "decisions": ["R"]})
        self.assertEqual(r.ex.controller_of(r.handles["bear"]), r.seats[thief])
        r.run_step({"op": "deal_damage", "source": "wurm", "target": "bear", "amount": 2})
        self.assertEqual(r.world.zone_of(r.handles["bear"]).kind, "graveyard")
        return r.world.players[r.p0].life, r.world.players[r.p1].life

    def test_dies_trigger_reads_the_controller_at_death(self):
        # The opponent took your Bear and it died under them: "a creature an opponent controls
        # died", and that player (the opponent) loses 2.
        self.assertEqual(self.wurm_sees(thief=1), (20, 18))
        # You took the opponent's Bear and it died under you: not an opponent's creature.
        self.assertEqual(self.wurm_sees(thief=0), (20, 20))

    def test_an_unstolen_creatures_controller_is_its_owner(self):
        r = runner([{"key": "x", "real": "Angelic Ascension", "zone": "hand", "controller": 0},
                    bear("obear", 1)], mana={"0": {"W": 2}})
        r.run_step({"op": "cast", "key": "x", "controller": 0, "targets": ["obear"]})
        self.assertEqual(self.token_seats(r, "Angel"), [1])



class TestCR6112aResolvedEffectsOutliveTheirSource(unittest.TestCase):
    def test_granted_flying_stays_when_the_granter_leaves(self):
        r = runner([{"key": "kg", "real": "Keen Glidemaster", "zone": "battlefield", "controller": 0},
                    bear("bear", 0)], mana={"0": {"U": 3}})
        r.run_step({"op": "activate", "key": "kg", "idx": 0, "seat": 0, "targets": ["bear"]})
        r.run_step({"op": "move", "key": "kg", "to": "graveyard"})
        self.assertTrue(r.ex.layers.keyword_of(r.handles["bear"], "FLYING"))
        r.run_step({"op": "end_turn"})
        self.assertFalse(r.ex.layers.keyword_of(r.handles["bear"], "FLYING"))  # until end of turn

    def test_a_grant_stays_when_its_token_source_ceases_to_exist(self):
        # A token's ability granted flying; the token died and ceased to exist (CR 704.5d).
        r = runner([{"key": "tok", "name": "Spirit", "type": "Creature — Spirit", "power": "1",
                     "toughness": "1", "token": True, "zone": "battlefield", "controller": 0},
                    bear("bear", 0)])
        tok, bear_h = r.handles["tok"], r.handles["bear"]
        r.ex.execute(Atom(Verb.GRANT_ABILITY, AtomArgs((
            ("ability", KeywordAbility(Keyword.FLYING)), ("duration", DurationEot()),
            ("target", Selector(QConst(1), SelectorMode.TARGET, UNIV, zones=(BF_ANY,))),
        ))), source=tok, controller=r.p0, bindings={"target": [bear_h]})
        r.run_step({"op": "move", "key": "tok", "to": "graveyard"})
        self.assertNotIn(tok, r.world.cards)
        self.assertTrue(r.ex.layers.keyword_of(bear_h, "FLYING"))

    def test_cant_be_blocked_stays_when_subira_leaves(self):
        r = runner([{"key": "sub", "real": "Subira, Tulzidi Caravanner", "zone": "battlefield",
                     "controller": 0}, bear("runner", 0), bear("obear", 1)], mana={"0": {"C": 1}})
        r.run_step({"op": "activate", "key": "sub", "idx": 0, "seat": 0, "targets": ["runner"]})
        r.run_step({"op": "move", "key": "sub", "to": "graveyard"})
        self.assertTrue(r.ex.replacements.prevents_block_declaration(
            r.handles["obear"], r.handles["runner"]))

    def test_damage_prevention_stays_when_pack_leader_leaves(self):
        r = runner([{"key": "pl", "real": "Pack Leader", "zone": "battlefield", "controller": 0},
                    {"key": "dog", "name": "Dog", "type": "Creature — Dog", "power": "2",
                     "toughness": "2", "zone": "battlefield", "controller": 0}])
        pl, dog = r.handles["pl"], r.handles["dog"]
        trigger = r.ex.binder.handle_record[pl].abilities[1]
        r.ex.apply_effect(trigger.effect, source=pl, controller=r.p0)
        r.run_step({"op": "move", "key": "pl", "to": "graveyard"})
        ctx = r.ex._ctx(source=pl, controller=r.p1, bindings=None, decisions=())
        self.assertIsNotNone(r.ex.replacements.prevented_card_damage(ctx, dog, combat=True))

    def test_a_resolved_effect_about_its_source_ends_with_that_object(self):
        # Ghostly Pilferer: "Discard a card: Ghostly Pilferer can't be blocked this turn." The
        # effect outlives the Pilferer's leaving, but it is about that object: a Pilferer that
        # comes back the same turn is a new object, and can be blocked (CR 400.7).
        r = runner([{"key": "gp", "real": "Ghostly Pilferer", "zone": "battlefield", "controller": 0},
                    {"key": "card", "name": "Card", "type": "Sorcery", "zone": "hand", "controller": 0},
                    bear("obear", 1)])
        r.run_step({"op": "activate", "key": "gp", "idx": 2, "seat": 0, "decisions": ["card"]})
        gp, obear = r.handles["gp"], r.handles["obear"]
        self.assertTrue(r.ex.replacements.prevents_block_declaration(obear, gp))
        leave_and_return(r, "gp")
        self.assertFalse(r.ex.replacements.prevents_block_declaration(obear, gp))

    def test_lost_flying_stays_lost_until_the_next_turn_when_the_source_leaves(self):
        # Mu Yanling, Sky Dancer's +2 (known_bugs b50_grant_ends_with_source): "Until your next
        # turn, up to one target creature ... loses flying."
        r = runner([bear("mu", 0), {"key": "drake", "name": "Drake", "type": "Creature — Drake",
                                    "power": "3", "toughness": "3", "keywords": ["FLYING"],
                                    "zone": "battlefield", "controller": 1}])
        drake = r.handles["drake"]
        r.ex.execute(Atom(Verb.LOSE_ABILITY, AtomArgs((
            ("ability", KeywordAbility(Keyword.FLYING)), ("duration", DurationUntilNextTurn()),
            ("target", Selector(QConst(1), SelectorMode.TARGET, UNIV, zones=(BF_ANY,))),
        ))), source=r.handles["mu"], controller=r.p0, bindings={"target": [drake]})
        r.run_step({"op": "advance_turn"})  # the opponent's turn
        r.run_step({"op": "move", "key": "mu", "to": "graveyard"})
        self.assertFalse(r.ex.layers.keyword_of(drake, "FLYING"))
        r.run_step({"op": "advance_turn"})  # your next turn: it ends
        self.assertTrue(r.ex.layers.keyword_of(drake, "FLYING"))

    def test_control_with_no_duration_lasts_after_the_source_leaves(self):
        # Sorin, Vampire Lord's -8 grants Vampires "{T}: Gain control of target creature." The
        # control has no duration: it lasts the game, not as long as the Vampire (known_bugs
        # cr611_2a_control_ends_with_granter).
        r = runner([bear("vamp", 0), bear("ogiant", 1)])
        ogiant = r.handles["ogiant"]
        r.ex.execute(Atom(Verb.GAIN_CONTROL, AtomArgs((
            ("controller", ControllerRef.YOU),
            ("target", Selector(QConst(1), SelectorMode.TARGET, UNIV, zones=(BF_ANY,))),
        ))), source=r.handles["vamp"], controller=r.p0, bindings={"target": [ogiant]})
        r.run_step({"op": "move", "key": "vamp", "to": "graveyard"})
        r.run_step({"op": "advance_turn"})
        r.run_step({"op": "advance_turn"})
        self.assertEqual(r.ex.controller_of(ogiant), r.p0)

    def cant_block(self, duration):
        """A resolved sorcery's "Creatures without flying can't block" (Tectonic Rift's second
        sentence) with the given duration; the sorcery is in the graveyard."""
        r = runner([{"key": "rift", "name": "Rift", "type": "Sorcery", "zone": "graveyard",
                     "controller": 0}, bear("bear", 0), bear("giant", 1)])
        nonflyer = FAnd((FAtom(FAtomPred.TYPE_EQ, string_value="Creature"),
                         FNot(FAtom(FAtomPred.KEYWORD_HAS, keyword=Keyword.FLYING))))
        roles = [("condition", UNIV), ("event", DeclareBlockersEvent(filter=nonflyer))]
        if duration is not None:
            roles.append(("duration", duration))
        r.ex.execute(Atom(Verb.PREVENT_EFFECT, AtomArgs(tuple(roles))),
                     source=r.handles["rift"], controller=r.p0)
        return r, lambda: r.ex.replacements.prevents_block_declaration(
            r.handles["giant"], r.handles["bear"])

    def test_a_resolved_cant_block_with_no_end_applies(self):
        r, vetoed = self.cant_block(None)
        self.assertTrue(vetoed())
        r.run_step({"op": "advance_turn"})
        self.assertTrue(vetoed())

    def test_a_resolved_cant_block_until_your_next_turn_applies(self):
        r, vetoed = self.cant_block(DurationUntilNextTurn())
        self.assertTrue(vetoed())
        r.run_step({"op": "advance_turn"})  # the opponent's turn: still on
        self.assertTrue(vetoed())
        r.run_step({"op": "advance_turn"})  # your next turn: over
        self.assertFalse(vetoed())



class TestDamageTriggerPreBind(unittest.TestCase):
    def test_creatures_you_control_get_the_pump_not_the_dealer(self):
        # Wildfire Elemental: "Whenever an opponent is dealt noncombat damage, creatures you
        # control get +1/+0 until end of turn." Your Bear deals 2 to the opponent.
        r = runner([bear("we", 0, name="Wildfire"), bear("bear", 0), bear("obear", 1)])
        we = r.handles["we"]
        mine = Selector(QUnbounded(), SelectorMode.ALL,
                        FAnd((FAtom(FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
                              FAtom(FAtomPred.TYPE_EQ, string_value="Creature"))),
                        zones=(BF_ANY,))
        trigger = TriggeredAbility(
            event=DamageDealtEvent(amount=QUnbounded(),
                                   filter=FAtom(FAtomPred.OPPONENT_OF, who=ControllerRef.YOU),
                                   combat=False),
            condition=None,
            effect=Atom(Verb.MODIFY_PT, AtomArgs((
                ("duration", DurationEot()),
                ("power", PtDelta(PtDirection.INCREASE, QConst(1))),
                ("target", mine),
                ("toughness", PtDelta(PtDirection.INCREASE, QConst(0))),
            ))),
        )
        identity = r.world.cards[we].identity
        r.ex.attach_card(we, CardRecord(
            oracle_id=identity.oracle_id, name=identity.name, type_line=identity.type_line,
            types=("Creature",), subtypes=("Bear",), supertypes=(), colors=(),
            color_identity=frozenset(), mana_cost=None, mana_value=2, power=QConst(2),
            toughness=QConst(2), loyalty=None, keywords=(), abilities=(trigger,), is_token=False))
        r.ex.execute(Atom(Verb.DEAL_DAMAGE, AtomArgs((
            ("amount", QConst(2)),
            ("target", Selector(QConst(1), SelectorMode.TARGET, UNIV,
                                zones=(Zone(ZoneKind.PLAYER, ControllerRef.ANY),))),
        ))), source=r.handles["bear"], controller=r.p0, bindings={"target": [r.p1]})
        self.assertEqual(r.world.players[r.p1].life, 18)
        self.assertEqual((pt(r, "we"), pt(r, "bear"), pt(r, "obear")), ((3, 2), (3, 2), (2, 2)))



def record(r, key, abilities):
    """Attach ``abilities`` to the pack card ``key`` (a synthetic creature)."""
    h = r.handles[key]
    identity = r.world.cards[h].identity
    return r.ex.attach_card(h, CardRecord(
        oracle_id=identity.oracle_id, name=identity.name, type_line=identity.type_line,
        types=("Creature",), subtypes=(), supertypes=(), colors=(),
        color_identity=frozenset(), mana_cost=None, mana_value=2, power=QConst(1),
        toughness=QConst(1), loyalty=None, keywords=(), abilities=tuple(abilities),
        is_token=False))


class TestCounterPlacementPrevention(unittest.TestCase):
    def blightbeetle(self):
        r = runner([bear("beetle", 0), bear("mine", 0), bear("theirs", 1)])
        opp_creatures = FAnd((FAtom(FAtomPred.CONTROLLER_IS, who=ControllerRef.OPPONENT),
                              FAtom(FAtomPred.TYPE_EQ, string_value="Creature")))
        record(r, "beetle", [StaticAbility(effect=Atom(Verb.PREVENT_EFFECT, AtomArgs((
            ("condition", opp_creatures),
            ("event", CounterPlacedEvent(counter_kind=CounterKind.PLUS_1_PLUS_1,
                                         filter=opp_creatures)),
        ))))])
        return r

    def put_counter(self, r, key):
        r.ex.execute(counter_on(Selector(QConst(1), SelectorMode.TARGET, UNIV, zones=(BF_ANY,))),
                     source=r.handles["mine"], controller=r.p0,
                     bindings={"target": [r.handles[key]]})
        return dict(r.world.cards[r.handles[key]].counters)

    def test_an_opponents_creature_gets_no_counter(self):
        r = self.blightbeetle()
        self.assertEqual(self.put_counter(r, "theirs"), {})
        self.assertEqual(self.put_counter(r, "mine"), {"PLUS_1_PLUS_1": 1})
        r.run_step({"op": "move", "key": "beetle", "to": "graveyard"})
        self.assertEqual(self.put_counter(r, "theirs"), {"PLUS_1_PLUS_1": 1})

    def test_an_opponents_creature_enters_without_its_counters(self):
        # CR 122.6: the counters a permanent enters with are put on it, so Blightbeetle stops
        # them too ("enters with two +1/+1 counters" under the opponent).
        r = self.blightbeetle()
        grower = r.world.add_card(CardIdentity(
            oracle_id="99999999-0000-0000-0000-0000000000ee", name="Grower",
            type_line="Creature — Hydra", power="0", toughness="0", cmc=2), r.p1, "hand")
        rec = CardRecord(
            oracle_id="99999999-0000-0000-0000-0000000000ee", name="Grower",
            type_line="Creature — Hydra", types=("Creature",), subtypes=("Hydra",),
            supertypes=(), colors=(), color_identity=frozenset(), mana_cost=None, mana_value=2,
            power=QConst(0), toughness=QConst(0), loyalty=None, keywords=(),
            abilities=(EtBState(initial_counters=((CounterKind.PLUS_1_PLUS_1, QConst(2)),)),),
            is_token=False)
        r.ex.binder.records[rec.oracle_id] = rec
        r.handles["grower"] = grower
        r.run_step({"op": "enter", "key": "grower"})
        self.assertEqual(dict(r.world.cards[grower].counters), {})


if __name__ == "__main__":
    unittest.main()
