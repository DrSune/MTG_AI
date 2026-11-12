"""A01 Archfiend's Vessel and A08 Teferi's Ageless Insight (M21): their surviving G3 mutants are
live in the engine, in games no 2-seat M21 pack can build. Not equivalent, so no gates rule.

A01: the effect-cast lane (stack.cast_card, the CAST verb's engine) casts a card from any zone.
Cast from your graveyard, the card exiles itself and makes the Demon. Each mutant (the `who` or
the zone controller of CAST_THIS_TURN_FROM flipped; quantity.py tests both against the caster)
makes that child unsatisfiable, so the Vessel stays and no Demon comes. No card in the 19 sets
casts a creature card from a graveyard, and the pack runner casts from hand only.

A08: NOT_FIRST_DRAW_THIS_STEP reads `who` (quantity.py) only inside the turn-draw window
(Executor._turn_draw), at consults for the replacement controller's own draws
(replacements.replacement_for_card_draw), each made before its draw is stamped (verbs._v_draw).
In every 2-seat game of today's pool the one consult in the window sees an empty ordinal map,
whatever `who` says. Two ways it is live:
 (a) a second draw replacement that fires on the turn draw draws inside the window (the 19 sets
     have none: only Teferi's Ageless Insight and Alhammarret's Archive, both NOT_FIRST-gated);
 (b) with three seats the mutant's OPPONENT names two seats and the predicate raises.

Run from the repo root: .venv/bin/python reports/g3_equivalence_2026-11-12/proof_vessel_teferi.py
(exit 0 = every claim held)
"""

import dataclasses
import sys
from pathlib import Path

WT = Path(__file__).resolve().parents[2]
for p in (WT, WT / "tools" / "cards", WT / "tools"):
    sys.path.insert(0, str(p))

import gates
import test_gates as tg
from irpy import A
from run_scenarios import ScenarioRunner

from MTG_bot.core.ability_tree import (
    CardDrawnEvent,
    ControllerRef,
    FAtom,
    FAtomPred,
    QConst,
    ReplacementAbility,
    Verb,
)
from MTG_bot.core.executor import Executor
from MTG_bot.core.executor.games import identity_of
from MTG_bot.core.executor.stack import cast, cast_card
from MTG_bot.core.identity import CardIdentity
from MTG_bot.core.state import ZONE_BATTLEFIELD, ZONE_HAND, ZONE_LIBRARY, GameWorld
from MTG_bot.utils import rng

rng.seed_all(7)
fails = []


def check(cond, msg):
    print(("ok   " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)


# ------------------------------------------------------------------ A01 Archfiend's Vessel
vessel = tg._card("Archfiend's Vessel")
WHO, ZONE = "1/0/condition/children/0/who", "1/0/condition/children/0/zone/controller"
mutants = {"who": tg._mutant(vessel, WHO, ControllerRef.OPPONENT),
           "zone": tg._mutant(vessel, ZONE, ControllerRef.OPPONENT)}
offered = tg._where(vessel)
check(("controller YOU->OPPONENT", WHO) in offered and ("controller YOU->OPPONENT", ZONE) in offered,
      "A01: both mutants are offered")


def cast_from_graveyard(r: ScenarioRunner) -> None:
    cast_card(r.ex, r.p0, r.handles["v"], cost_override=None)


def vessel_and_demon(game):
    return {o[0]: o[1] for o in game[0].values() if o[0] in ("Archfiend's Vessel", "Demon")}


pack = tg._pack([{"key": "v", "real": "Archfiend's Vessel", "zone": "graveyard", "controller": 0}], [],
                {"0": {"B": 1}})
real = tg._game(pack, setup=cast_from_graveyard)
check(vessel_and_demon(real) == {"Archfiend's Vessel": "exile", "Demon": "battlefield"},
      f"A01 card, cast from your graveyard: exiled, a Demon {vessel_and_demon(real)}")
for name, m in mutants.items():
    got = tg._game(pack, m, setup=cast_from_graveyard)
    check(vessel_and_demon(got) == {"Archfiend's Vessel": "battlefield"},
          f"A01 mutant {name}: the Vessel stays, no Demon {vessel_and_demon(got)}")
for label, steps, zone in (("put from graveyard", [{"op": "move", "key": "v", "to": "battlefield"}], "graveyard"),
                           ("entered from hand", [{"op": "enter", "key": "v"}], "hand")):
    p = tg._pack([{"key": "v", "real": "Archfiend's Vessel", "zone": zone, "controller": 0}], steps)
    r0 = tg._game(p)
    check(all(tg._game(p, m) == r0 for m in mutants.values()),
          f"A01 {label} (what the verifier's packs did): the mutants equal the card {vessel_and_demon(r0)}")

# ------------------------------------------------------------------ A08 Teferi's Ageless Insight
tai = tg._card("Teferi's Ageless Insight")
COND = "1/0/condition/who"
mutant = tg._mutant(tai, COND, ControllerRef.OPPONENT)
check(("controller YOU->OPPONENT", COND) in tg._where(tai), "A08: the mutant is offered")
lib = tg._library(0, "Yours", 8) + tg._library(1, "Theirs", 8)
ench = {"key": "t", "real": "Teferi's Ageless Insight", "zone": "battlefield", "controller": 0}
ct = {"key": "ct", "real": "Crash Through", "zone": "hand", "controller": 0}
scenarios = {
    "your turn draw (not replaced), then a main-phase draw (replaced)": tg._pack(
        [ench, ct, *lib], [{"op": "end_turn"}, {"op": "advance_turn"}, {"op": "end_turn"}, {"op": "advance_turn"},
                           {"op": "mana", "seat": 0, "add": {"R": 1}}, {"op": "cast", "key": "ct"}]),
    "the opponent's turn draw (not yours: never consulted)": tg._pack(
        [ench, *lib], [{"op": "end_turn"}, {"op": "advance_turn"}]),
}
for label, p in scenarios.items():
    r0 = tg._game(p)
    check(tg._game(p, mutant) == r0, f"A08 2 seats: {label}: identical")


def three_seats(card):
    """Three seats; seat 0 holds the enchantment, draws its turn draw (CR 103.8c: nobody skips it
    with three players), then casts Crash Through."""
    sup = tg._supply()
    oid = tg._oid("Teferi's Ageless Insight")
    with gates.swapped(sup, oid, card) if card is not None else tg._Null():
        world = GameWorld(num_players=3, start_life=20, master_seed=7)
        ex = Executor(world)
        p0 = world.player_order[0]
        for seat in world.player_order:
            for i in range(8):
                world.add_card(CardIdentity(oracle_id=f"9e00000{i}-0000-0000-0000-00000000000{seat.index}",
                                            name=f"Lib {seat.index}.{i}", type_line="Creature", power="1",
                                            toughness="1", cmc=1), seat, ZONE_LIBRARY)
        world.add_card(identity_of(sup.pool.results[oid].card), p0, ZONE_BATTLEFIELD)
        crash = world.add_card(identity_of(sup.pool.results[tg._oid("Crash Through")].card), p0, ZONE_HAND)
        ex.attach_pool(sup.pool)
        try:
            ex.begin_turn(p0)
            before = len(world.players[p0].zone(ZONE_HAND).entries)
            world.players[p0].mana_pool["R"] = 1
            cast(ex, p0, crash)
        except NotImplementedError as exc:
            return f"raised: {exc}"
        return f"hand after the turn draw {before}, after Crash Through {len(world.players[p0].zone(ZONE_HAND).entries)}"


card3, mutant3 = three_seats(None), three_seats(mutant)
print("   3 seats, card:", card3, "| mutant:", mutant3)
check(card3.startswith("hand") and mutant3.startswith("raised"), "A08 (b) 3 seats: the card plays, the mutant raises")

# (a) an unconditional "If you would draw a card, draw two cards instead" (no such card in the 19
# sets) beside it, on a swapped Alpine Watchdog: printed, the turn draw becomes two draws, the
# second of which Teferi's Ageless Insight doubles (3 cards); the mutant leaves it (2 cards)
reflection = ReplacementAbility(
    event=CardDrawnEvent(actor=FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU)), condition=None,
    action=A(Verb.DRAW, {"amount": QConst(value=2), "controller": ControllerRef.YOU}))
dog = tg._card("Alpine Watchdog")
p = tg._pack([ench, {"key": "x", "real": "Alpine Watchdog", "zone": "battlefield", "controller": 0}, *lib],
             [{"op": "end_turn"}, {"op": "advance_turn"}, {"op": "end_turn"}, {"op": "advance_turn"}])


def your_hand(game):
    return sum(1 for o in game[0].values() if o[1] == "hand" and o[2] == "player:0")


with gates.swapped(tg._supply(), tg._oid("Alpine Watchdog"), dataclasses.replace(dog, abilities=(reflection, *dog.abilities))):
    r_card, r_mutant = tg._game(p), tg._game(p, mutant)
print("   with a 'draw two instead' card, your turn draw gives", your_hand(r_card), "cards (card),",
      your_hand(r_mutant), "(mutant)")
check((your_hand(r_card), your_hand(r_mutant)) == (3, 2), "A08 (a): a draw replacement on the turn draw tells them apart")
print("ALL HELD" if not fails else f"{len(fails)} FAILED")
sys.exit(1 if fails else 0)
