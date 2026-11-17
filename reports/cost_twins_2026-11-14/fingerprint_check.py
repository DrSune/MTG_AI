"""Executor.state_fingerprint on states that hold a stack object, per checkout: the stack's row
folds repr(PaymentPlan) (stack.SpellStack.dump), and the plan gained three fields this round
(exile, exile_options, remove_counters), kept out of its repr. Each line: a state and its
fingerprint; the two checkouts' outputs must be identical.

    fingerprint_check.py <checkout>
"""
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT))
import MTG_bot

assert MTG_bot.__file__.startswith(str(ROOT)), MTG_bot.__file__
from MTG_bot.core.executor.games import get_supply
from tools.run_scenarios import ScenarioRunner

STATES = {
    # a spell held on the stack (a cast's PaymentPlan: mana)
    "Shock held": ({"set": "M21", "cards": [
        {"key": "shock", "real": "Shock", "zone": "hand", "controller": 0},
        {"key": "ox", "name": "Ox", "type": "Creature", "power": "3", "toughness": "3",
         "zone": "battlefield", "controller": 1}], "mana": {"0": {"R": 1}}},
        [{"op": "cast", "key": "shock", "real": "Shock", "targets": ["ox"], "hold": True}]),
    # an activated ability held on the stack (its PaymentPlan: mana and a sacrifice)
    "Heartfire Immolator's ability held": ({"set": "M21", "cards": [
        {"key": "imm", "real": "Heartfire Immolator", "zone": "battlefield", "controller": 0},
        {"key": "ox", "name": "Ox", "type": "Creature", "power": "3", "toughness": "3",
         "zone": "battlefield", "controller": 1}], "mana": {"0": {"R": 1}}},
        [{"op": "activate", "key": "imm", "idx": 0, "seat": 0, "targets": ["ox"], "hold": True}]),
}
for name, (pack, steps) in STATES.items():
    pack = {"world": {"life": 20, "seed": 7}, "steps": [], **pack}
    r = ScenarioRunner(pack, get_supply("all", pack["set"]))
    for step in steps:
        r.run_step(step)
    print(name, "| stack", len(r.ex.stack.frames), "|", r.ex.state_fingerprint())
