"""Does one lifelink creature dealing combat damage to two recipients make one gain event (its
rulings: Ajani's Pridemate, Angel of Vitality) or two (one per recipient atom)? A trampling 5/5
lifelinker blocked by a 0/2 assigns 2 to it and 3 to the player; with and without Angel of
Vitality. Output: lifelink_probe.txt (docs/BACKLOG.md, Triggers: two rows, 27 life with the Angel
where the rules give 26). Run from the repo root:

    .venv/bin/python reports/life_family_2026-11-13/lifelink_probe.py
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
import MTG_bot

assert MTG_bot.__file__.startswith(str(REPO)), MTG_bot.__file__

from MTG_bot.core.executor.events import KIND_LIFE_GAINED
from MTG_bot.core.executor.games import get_supply
from tools.run_scenarios import ScenarioRunner

for angel in (False, True):
    cards = [
        {"key": "lt", "name": "Trampler", "type": "Creature — Beast", "power": "5",
         "toughness": "5", "keywords": ["LIFELINK", "TRAMPLE"], "zone": "battlefield",
         "controller": 0},
        {"key": "blk", "name": "Wall", "type": "Creature — Wall", "power": "0", "toughness": "2",
         "zone": "battlefield", "controller": 1},
    ]
    if angel:
        cards.append({"key": "angel", "real": "Angel of Vitality", "zone": "battlefield",
                      "controller": 0})
    pack = {"set": "M20", "world": {"life": 20, "seed": 7}, "cards": cards, "steps": []}
    r = ScenarioRunner(pack, get_supply("all", "M20"))
    r.run_step({"op": "combat", "seat": 0, "attack": {"lt": True}, "block": {"blk": "lt"},
                "trample": {"lt": [0]}})
    gains = [(e.amount, e.cause_verb) for e in r.ex.journal.turn_window()
             if e.kind == KIND_LIFE_GAINED]
    print("angel" if angel else "plain", "life p0", r.world.players[r.p0].life,
          "p1", r.world.players[r.p1].life, "gain rows", gains)
