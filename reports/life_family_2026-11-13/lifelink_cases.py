"""One lifelink source's damage dealt at once is one life-gain event, whatever the number of
recipients (CR 120.3f, 119.9; the rulings of Ajani's Pridemate and Angel of Vitality); several
lifelink sources are several events. Three cases, with FDN Ajani's Pridemate ("Whenever you gain
life, put a +1/+1 counter on this creature") counting the events:

- trample: a trampling 5/5 lifelinker blocked by a 0/2 assigns 2 to it and 3 to the player;
- two blockers: a 4/4 lifelinker blocked by two 0/2 walls assigns 2 to each;
- noncombat: a lifelinker deals 1 damage to each of two creatures at once (one DEAL_DAMAGE atom),
  with Angel of Vitality ("If you would gain life, you gain that much life plus 1 instead");

and the trample case with the Angel. Prints, per case, p0's life, the LIFE_GAINED rows (amount,
cause verb) and Pridemate's counters, beside what the rules give. Output: lifelink_cases.txt
(before the fix) and lifelink_cases_fixed.txt. Run from the repo root:

    .venv/bin/python reports/life_family_2026-11-13/lifelink_cases.py
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
import MTG_bot

assert MTG_bot.__file__.startswith(str(REPO)), MTG_bot.__file__

from MTG_bot.core import ability_tree as at
from MTG_bot.core.executor.events import KIND_LIFE_GAINED
from MTG_bot.core.executor.games import get_supply
from tools.run_scenarios import ScenarioRunner

CREATURE = at.FAtom(at.FAtomPred.TYPE_EQ, string_value="Creature")


def creature(key, seat, power, toughness, *keywords):
    return {"key": key, "name": key.title(), "type": "Creature — Beast", "power": power,
            "toughness": toughness, "keywords": list(keywords), "zone": "battlefield",
            "controller": seat}


def real(key, name):
    return {"key": key, "real": name, "zone": "battlefield", "controller": 0}


def runner(cards):
    pack = {"set": "FDN", "world": {"life": 20, "seed": 7}, "cards": cards, "steps": []}
    return ScenarioRunner(pack, get_supply("all", "FDN"))


def report(name, r, rules):
    gains = [(e.amount, e.cause_verb) for e in r.ex.journal.turn_window()
             if e.kind == KIND_LIFE_GAINED and e.subject == r.p0]
    counters = r.world.cards[r.handles["pm"]].counters.get("PLUS_1_PLUS_1", 0)
    print(f"{name}: life {r.world.players[r.p0].life}, gain rows {gains}, Pridemate counters "
          f"{counters}  (the rules: {rules})")


def trample(angel: bool):
    cards = [creature("lt", 0, "5", "5", "LIFELINK", "TRAMPLE"), creature("wall", 1, "0", "2"),
             real("pm", "Ajani's Pridemate")]
    if angel:
        cards.append(real("angel", "Angel of Vitality"))
    r = runner(cards)
    r.run_step({"op": "combat", "seat": 0, "attack": {"lt": True}, "block": {"wall": "lt"},
                "trample": {"lt": [0]}})
    return r


def two_blockers():
    r = runner([creature("lt", 0, "4", "4", "LIFELINK"), creature("w1", 1, "0", "2"),
                creature("w2", 1, "0", "2"), real("pm", "Ajani's Pridemate")])
    r.run_step({"op": "combat", "seat": 0, "attack": {"lt": True},
                "block": {"w1": "lt", "w2": "lt"}})
    return r


def noncombat():
    r = runner([creature("lt", 0, "1", "1", "LIFELINK"), creature("b1", 1, "1", "3"),
                creature("b2", 1, "1", "3"), real("pm", "Ajani's Pridemate"),
                real("angel", "Angel of Vitality")])
    ping = at.Atom(at.Verb.DEAL_DAMAGE, at.AtomArgs(pairs=(
        ("amount", at.QConst(1)),
        ("target", at.Selector(at.QConst(2), at.SelectorMode.TARGET, CREATURE,
                               zones=(at.Zone(at.ZoneKind.BATTLEFIELD, at.ControllerRef.ANY),))),
    )))
    # two Pridemate triggers at once (the fault) ask their order: either answer is the same
    r.ex.decisions.provider = lambda vocab, what: vocab[0]
    r.ex.execute(ping, source=r.handles["lt"], controller=r.p0,
                 bindings={"target": [r.handles["b1"], r.handles["b2"]]})
    return r


if __name__ == "__main__":
    report("trample", trample(False), "life 25, one row of 5, 1 counter")
    report("trample with Angel of Vitality", trample(True), "life 26, one row of 6, 1 counter")
    report("two blockers", two_blockers(), "life 24, one row of 4, 1 counter")
    report("noncombat with Angel of Vitality", noncombat(), "life 23, one row of 3, 1 counter")
