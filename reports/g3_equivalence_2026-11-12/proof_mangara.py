"""M21 Mangara, the Diplomat: are its two surviving G3 mutants equivalent?

  M1 = controller YOU->OPPONENT at 1/0/event/attacked/children/0/children/0/who
  M2 = controller YOU->OPPONENT at 1/0/condition/inner_filter/children/0/children/0/who

Plays the real tree and each mutant (gates.swapped, as cardtool verify does) to the whole
observable game (test_gates._game's observation: every object, both/all seats' life, library order
and mana pool, the journal dump) over the scenarios that exercise the attacked object:

  2-seat (ScenarioRunner, the pack world):
    S1  the opponent attacks you with two creatures                       printed: draw
    S2  one attacks you, one attacks your planeswalker                    printed: draw
    S3  both attack your planeswalker                                     printed: draw
    S4  one attacks your planeswalker only                                printed: no draw
    S5  S2, and the attacked planeswalker changes control to the opponent
        while the trigger waits (CR 506.4: it leaves combat)               printed: draw
    S6  S1, and one attacker leaves the battlefield while the trigger waits printed: draw
  3-seat (GameWorld(num_players=3), driven directly; packs are 2-seat):
    T1  Mangara at p2; p1 attacks p0's planeswalker with two               printed: no draw
    T2  Mangara at p2; p1 attacks p0 with two                              printed: no draw
    T3  Mangara at p0; p1 attacks p0 with one and p0's planeswalker with one printed: draw

Sensitivity: the double mutant M1+M2 in T1 and the offered neighbour
"controller YOU->OPPONENT at 1/0/event/attacked/children/1/who" in S1 must differ from the card,
so the scenarios do reach the role.

Run from the repo root: .venv/bin/python reports/g3_equivalence_2026-11-12/proof_mangara.py
(exit 0 = every assertion held)
"""

from __future__ import annotations

import dataclasses
import sys
from contextlib import nullcontext
from pathlib import Path

WT = Path(__file__).resolve().parents[2]
for p in (WT, WT / "tools" / "cards", WT / "tools"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import gates
import test_gates as tg
from run_scenarios import ScenarioRunner

from MTG_bot.core.ability_tree import (
    Atom,
    AtomArgs,
    ControllerRef,
    FAnd,
    Keyword,
    QConst,
    Selector,
    SelectorMode,
    Verb,
    Zone,
    ZoneKind,
)
from MTG_bot.core.executor import Executor
from MTG_bot.core.executor.games import identity_of
from MTG_bot.core.identity import CardIdentity
from MTG_bot.core.state import ZONE_BATTLEFIELD, ZONE_LIBRARY, GameWorld
from MTG_bot.utils import rng

rng.seed_all(20261029)

NAME = "Mangara, the Diplomat"
M1 = "1/0/event/attacked/children/0/children/0/who"
M2 = "1/0/condition/inner_filter/children/0/children/0/who"
NEIGHBOUR = "1/0/event/attacked/children/1/who"

CARD = tg._card(NAME)
OID = tg._oid(NAME)
offered = tg._where(CARD)
for where in (M1, M2, NEIGHBOUR):
    assert ("controller YOU->OPPONENT", where) in offered, where
MUT1 = tg._mutant(CARD, M1, ControllerRef.OPPONENT)
MUT2 = tg._mutant(CARD, M2, ControllerRef.OPPONENT)
MUT12 = tg._mutant(MUT1, M2, ControllerRef.OPPONENT)
MUTN = tg._mutant(CARD, NEIGHBOUR, ControllerRef.OPPONENT)
# the generated mutants are exactly these trees
gen = {(op, w): m for op, w, m in gates.mutants(CARD)}
assert gen[("controller YOU->OPPONENT", M1)] == MUT1
assert gen[("controller YOU->OPPONENT", M2)] == MUT2


def observe(world, ex) -> tuple:
    """test_gates._game's observation of a finished game."""
    objs = {}
    for h, c in world.cards.items():
        zone = world.zone_of(h).kind
        pt = kws = None
        if zone == "battlefield" and "Creature" in c.identity.type_line:
            pt = tuple(ex.ledger.effective_pt(c.identity, h, c.counters))
            kws = tuple(k.name for k in Keyword if ex.layers.keyword_of(h, k))
        objs[str(h)] = (c.identity.name, zone, str(world.controller_of(h)), c.tapped,
                        tuple(sorted(c.counters.items())), pt, kws, ex.damage.get(h, 0))
    seats = {str(p): (world.players[p].life, tuple(str(x) for x in world.players[p].zone("library").entries),
                      tuple(sorted((k, v) for k, v in world.players[p].mana_pool.items() if v)))
             for p in world.player_order}
    return objs, seats, ex.journal.dump()


def hands(world) -> tuple[int, ...]:
    return tuple(len(world.players[p].zone("hand").entries) for p in world.player_order)


# ----------------------------------------------------------------------------- 2-seat
def creature(key: str, seat: int) -> dict:
    return {"key": key, "name": key.upper(), "type": "Creature", "power": "1", "toughness": "1",
            "zone": "battlefield", "controller": seat}


WALKER = {"key": "pw", "name": "Walker", "type": "Legendary Planeswalker — Test", "loyalty": "5",
          "counters": {"LOYALTY": 5}, "zone": "battlefield", "controller": 0}
LIBS = [{"key": f"l{i}", "name": f"L{i}", "type": "Creature", "power": "1", "toughness": "1",
         "zone": "library", "controller": 0} for i in range(3)]


def two_seat(card, attack: dict, interfere=None) -> tuple:
    """Seat 0 controls Mangara (and the planeswalker); seat 1's turn; its creatures a, b attack
    per ``attack`` (True = seat 0, "pw" = the planeswalker). ``interfere(r)`` runs while
    Mangara's trigger waits (binder.hold: queued after its trigger-time check, not yet on the
    stack), then the trigger goes on the stack and resolves (its CR 603.4 re-check), and the
    combat ends. Returns (observation, hands)."""
    sup = tg._supply()
    pack = tg._pack([{"key": "m", "real": NAME, "zone": "battlefield", "controller": 0}, WALKER,
                     creature("a", 1), creature("b", 1), *LIBS], [])
    with gates.swapped(sup, OID, card) if card is not None else nullcontext():
        r = ScenarioRunner(pack, sup)
        r.run_step({"op": "advance_turn"})
        words = {f"attack:{r.handles[k]}": ("ATTACK" if v is True else str(r.handles[v]))
                 for k, v in attack.items()}

        def answer(vocab, what):
            got = next((v for k, v in words.items() if what.startswith(k + ":")), None)
            if got is None:
                got = "DECLINE" if what.startswith("attack:") else ("NONE" if what.startswith("block:") else vocab[0])
            assert got in vocab, (what, got, vocab)
            return got

        ex = r.ex
        ex.decisions.provider = answer
        try:
            ex.binder.hold = interfere is not None
            ex.combat_attacks(r.p1)
            if interfere is not None:
                waiting = len(r.world.triggers)
                interfere(r)
                ex.binder.hold = False
                ex.fire_triggers()
            else:
                waiting = None
            ex.combat_blocks(r.p1)
        finally:
            ex.decisions.provider = None
            ex.binder.hold = False
        return observe(r.world, ex), hands(r.world), waiting


def steal_walker(r) -> None:
    """The opponent gains control of the attacked planeswalker (GAIN_CONTROL, the verb Traitorous
    Greed and Enthralling Hold compile to) while Mangara's trigger waits."""
    atom = Atom(verb=Verb.GAIN_CONTROL, args=AtomArgs(pairs=(
        ("target", Selector(QConst(1), SelectorMode.TARGET, FAnd(()),
                            zones=(Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),))),
        ("controller", ControllerRef.YOU))))
    r.ex.execute(atom, source=r.handles["a"], controller=r.p1, bindings={"target": r.handles["pw"]})
    assert r.world.controller_of(r.handles["pw"]) == r.p1 or r.ex.controller_of(r.handles["pw"]) == r.p1


def kill_b(r) -> None:
    """One attacker leaves the battlefield (the pack runner's "move" stand-in for a destroy)."""
    h = r.handles["b"]
    r.ex.execute(Atom(verb=Verb.MOVE_ZONE, args=AtomArgs(pairs=(
        ("cards", Selector(QConst(1), SelectorMode.TARGET, FAnd(()), zones=(Zone(ZoneKind.ANY, ControllerRef.ANY),))),
        ("destination", Zone(ZoneKind.GRAVEYARD, ControllerRef.OWNER))))),
        source=h, controller=r.world.controller_of(h), bindings={"cards": h})


# ----------------------------------------------------------------------------- 3-seat
def three_seat(card, mangara_seat: int, walker_seat: int, attack: dict) -> tuple:
    """GameWorld(num_players=3). p1's turn; p1's creatures a, b attack per ``attack`` (True = the
    defending player, which the engine fixes as the first non-active seat, p0; "pw" = the
    planeswalker, controlled by ``walker_seat``). Mangara is controlled by ``mangara_seat``."""
    sup = tg._supply()
    with gates.swapped(sup, OID, card) if card is not None else nullcontext():
        world = GameWorld(num_players=3, start_life=20, master_seed=7)
        ex = Executor(world)
        seats = list(world.player_order)
        for seat in seats:
            for i in range(6):
                world.add_card(CardIdentity(oracle_id=f"9f0000{seat.index}{i}-0000-0000-0000-000000000000",
                                            name=f"Lib {seat.index}.{i}", type_line="Creature", power="1",
                                            toughness="1", cmc=1), seat, ZONE_LIBRARY)
        world.add_card(identity_of(sup.pool.results[OID].card), seats[mangara_seat], ZONE_BATTLEFIELD)
        pw = world.add_card(CardIdentity(oracle_id="9a000001-1111-2222-3333-444444444444", name="Walker",
                                         type_line="Legendary Planeswalker — Test", cmc=3, loyalty="5"),
                            seats[walker_seat], ZONE_BATTLEFIELD)
        world.cards[pw].counters["LOYALTY"] = 5
        att = {}
        for i, key in enumerate(("a", "b")):
            att[key] = world.add_card(CardIdentity(oracle_id=f"9b00000{i}-1111-2222-3333-444444444444",
                                                   name=key.upper(), type_line="Creature", power="1",
                                                   toughness="1", cmc=1), seats[1], ZONE_BATTLEFIELD)
        ex.attach_pool(sup.pool)
        ex.decisions.provider = lambda vocab, what: vocab[0]
        ex.begin_turn(seats[0])
        words = {f"attack:{att[k]}": ("ATTACK" if v is True else str(pw)) for k, v in attack.items()}

        def answer(vocab, what):
            got = next((v for k, v in words.items() if what.startswith(k + ":")), None)
            if got is None:
                got = "DECLINE" if what.startswith("attack:") else ("NONE" if what.startswith("block:") else vocab[0])
            assert got in vocab, (what, got, vocab)
            return got

        ex.decisions.provider = answer
        ex.advance_turn()
        assert world.active_player == seats[1]
        ex.combat_step(seats[1])
        ex.decisions.provider = None
        return observe(world, ex), hands(world), None


# ----------------------------------------------------------------------------- run
fails: list[str] = []


def check(label: str, play, expect_hands, differ: dict) -> None:
    """``differ`` maps a tree label to True when that tree must play differently from the card."""
    real = play(None)
    print(f"{label}: card hands {real[1]}" + (f" (trigger waiting: {real[2]})" if real[2] is not None else ""))
    if real[1] != expect_hands:
        fails.append(f"{label}: card hands {real[1]}, expected {expect_hands}")
    for tag, tree in (("M1", MUT1), ("M2", MUT2), ("M1+M2", MUT12), ("neighbour", MUTN)):
        if tag not in differ:
            continue
        got = play(tree)
        same = got[0] == real[0]
        print(f"   {tag:9s}: {'IDENTICAL' if same else 'DIFFERENT'} game, hands {got[1]}")
        if same == differ[tag]:
            fails.append(f"{label} {tag}: expected {'a different' if differ[tag] else 'an identical'} game")


# printed draw counts: seat 0 (Mangara's controller) starts with 0 cards in hand, seat 1 drew its
# turn's card. In the 3-seat games p0 also drew on turn 1 (the CR 103.8a skip is two-player only).
check("S1 two attack you", lambda t: two_seat(t, {"a": True, "b": True}), (1, 1),
      {"M1": False, "M2": False, "neighbour": True})
check("S2 one at you, one at your walker", lambda t: two_seat(t, {"a": True, "b": "pw"}), (1, 1),
      {"M1": False, "M2": False})
check("S3 both at your walker", lambda t: two_seat(t, {"a": "pw", "b": "pw"}), (1, 1),
      {"M1": False, "M2": False})
check("S4 one at your walker", lambda t: two_seat(t, {"a": "pw"}), (0, 1),
      {"M1": False, "M2": False})
# S5/S6: the CARD's hand is 0 here although the printed card draws (no intervening "if"):
# the engine re-checks the count on resolution (binding.resolve). Expected hands state the
# ENGINE's card so the script pins what happens; the printed answer is (1, 1).
check("S5 walker stolen while the trigger waits", lambda t: two_seat(t, {"a": True, "b": "pw"}, steal_walker),
      (0, 1), {"M1": False, "M2": True})
check("S6 attacker gone while the trigger waits", lambda t: two_seat(t, {"a": True, "b": True}, kill_b),
      (0, 1), {"M1": False, "M2": False})
check("T1 3-seat: p1 attacks p0's walker, Mangara at p2", lambda t: three_seat(t, 2, 0, {"a": "pw", "b": "pw"}),
      (1, 1, 0), {"M1": False, "M2": False, "M1+M2": True})
check("T2 3-seat: p1 attacks p0, Mangara at p2", lambda t: three_seat(t, 2, 0, {"a": True, "b": True}),
      (1, 1, 0), {"M1": False, "M2": False})
check("T3 3-seat: Mangara at p0, p1 attacks p0 and p0's walker", lambda t: three_seat(t, 0, 0, {"a": True, "b": "pw"}),
      (2, 1, 0), {"M1": False, "M2": False})

# Near shape (the rule's negative test): the same trigger WITHOUT its ATTACK_AGAINST_COUNT_GE
# condition. In 2 seats the event's attacker filter (CONTROLLER_IS OPPONENT) still forces the
# defending player to be Mangara's controller, so M1 stays equivalent; in 3 seats (an opponent
# attacking another opponent's planeswalker) the flipped branch now matches and nothing else gates
# it: M1 becomes observable. So a dead-role rule for M1 must require the condition.
BARE = dataclasses.replace(CARD, abilities=(dataclasses.replace(CARD.abilities[0], condition=None),
                                            *CARD.abilities[1:]))
BARE_M1 = tg._mutant(BARE, M1, ControllerRef.OPPONENT)
for label, play, differ in (
        ("N1 no condition, 2-seat S2", lambda t: two_seat(t, {"a": True, "b": "pw"}), False),
        ("N2 no condition, 3-seat T1", lambda t: three_seat(t, 2, 0, {"a": "pw", "b": "pw"}), True)):
    base, mut = play(BARE), play(BARE_M1)
    same = base[0] == mut[0]
    print(f"{label}: base hands {base[1]}, M1 hands {mut[1]}: {'IDENTICAL' if same else 'DIFFERENT'}")
    if same == differ:
        fails.append(f"{label}: expected {'a different' if differ else 'an identical'} game")

print("ALL HELD" if not fails else "FAILURES:\n  " + "\n  ".join(fails))
sys.exit(1 if fails else 0)
