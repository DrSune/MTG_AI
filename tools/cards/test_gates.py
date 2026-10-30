"""Gates G0 and G3: the keyword-action and ability-word reading of G0, and the equivalent-mutant
rules of G3. Each G3 rule is proven twice: ``gates.mutants`` no longer offers the mutant (while
its observable neighbours stay), and the engine plays the real tree and the would-be mutant to
the same game on a board built to expose the field if anything read it."""

from __future__ import annotations

import dataclasses
import sys
from functools import cache
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
for _p in (HERE.parents[1], HERE, HERE.parent):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import gates
from run_scenarios import ScenarioRunner

from MTG_bot.core.ability_tree import (
    ActivatedAbility,
    AtomArgs,
    ControllerRef,
    Cost,
    Keyword,
    QConst,
    QUnbounded,
    SelectorMode,
)
from MTG_bot.core.compiler.ingest import ingest_pool
from MTG_bot.core.executor.games import compile_supply

DATA = HERE.parents[1] / "MTG_bot" / "data"


@cache
def _supply() -> Any:
    return compile_supply("all", "M21", require_verified=False)


@cache
def _raw() -> dict:
    return ingest_pool(DATA / "M21.json")


def _oid(name: str) -> str:
    return next(o for o, m in _supply().metas.items() if m.name == name)


def _card(name: str) -> Any:
    return _supply().pool.results[_oid(name)].card


def _where(card: Any) -> set[tuple[str, str]]:
    return {(op, where) for op, where, _m in gates.mutants(card)}


def _mutant(card: Any, where: str, new: Any) -> Any:
    path = tuple(int(p) if p.isdigit() else p for p in where.split("/"))
    kws, abilities = gates._rebuild((card.keywords, card.abilities), path, new)
    return dataclasses.replace(card, keywords=kws, abilities=abilities)


def _at(card: Any, where: str) -> Any:
    """The node at a mutation path (the path grammar of ``gates._paths``)."""
    node: Any = (card.keywords, card.abilities)
    for p in where.split("/"):
        if isinstance(node, AtomArgs):
            node = node.get(p)
        elif isinstance(node, tuple):
            node = node[int(p)]
        else:
            node = getattr(node, p)
    return node


def _game(pack: dict, card: Any = None) -> tuple:
    """The whole observable game after the pack's steps, with ``card`` (a mutant) swapped in."""
    sup = _supply()
    with gates.swapped(sup, _oid(card.name), card) if card is not None else _Null():
        r = ScenarioRunner(pack, sup)
        refused = None
        for step in pack["steps"]:
            try:
                r.run_step(step)
            except ValueError as exc:  # an illegal action: the refusal is part of the game
                refused = f"{step['op']}: {exc}"
                break
        w, ex = r.world, r.ex
        objs = {}
        for h, c in w.cards.items():
            zone = w.zone_of(h).kind
            pt = kws = None
            if zone == "battlefield" and "Creature" in c.identity.type_line:
                pt = tuple(ex.ledger.effective_pt(c.identity, h, c.counters))
                kws = tuple(k.name for k in Keyword if ex.layers.keyword_of(h, k))
            objs[str(h)] = (c.identity.name, zone, str(w.controller_of(h)), c.tapped,
                            tuple(sorted(c.counters.items())), pt, kws, ex.damage.get(h, 0))
        seats = {str(p): (w.players[p].life, tuple(str(x) for x in w.players[p].zone("library").entries),
                          tuple(sorted((k, v) for k, v in w.players[p].mana_pool.items() if v)))
                 for p in w.player_order}
        return objs, seats, ex.journal.dump(), refused


class _Null:
    def __enter__(self) -> None:
        return None

    def __exit__(self, *exc: object) -> None:
        return None


def _library(seat: int, prefix: str, n: int = 6) -> list[dict]:
    return [{"key": f"{prefix}{i}", "name": f"{prefix} {i}", "type": "Creature", "power": "1",
             "toughness": "1", "zone": "library", "controller": seat} for i in range(n)]


def _pack(cards: list[dict], steps: list[dict], mana: dict | None = None) -> dict:
    return {"set": "M21", "world": {"life": 20, "seed": 7, "library_top": True}, "cards": cards,
            "steps": steps, "mana": mana or {}}


# ----------------------------------------------------------------------------- G0
def test_g0_accepts_the_mill_keyword_action_the_tree_performs() -> None:
    grub = _card("Carrion Grub")
    raw = _raw()[_oid("Carrion Grub")]
    assert "Mill" in raw.keywords
    fails, _w = gates.g0(raw, grub, grub, clauses=None, known_signatures=None)
    assert not fails
    # no mill move in the tree: the printed keyword action is missing, and G0 still says so
    no_mill = dataclasses.replace(grub, abilities=(grub.abilities[0], grub.abilities[2]))
    fails, _w = gates.g0(raw, grub, no_mill, clauses=None, known_signatures=None)
    assert fails == ["MTGJSON keywords missing from the tree: ['MILL']"]


def test_g0_ignores_ability_words_but_not_keywords() -> None:
    bat = _card("Makeshift Battalion")
    raw = _raw()[_oid("Makeshift Battalion")]
    assert raw.keywords == ("Battalion",) or list(raw.keywords) == ["Battalion"]
    assert "BATTALION" in Keyword.__members__ and "BATTALION" in gates.ABILITY_WORDS
    fails, warns = gates.g0(raw, bat, bat, clauses=None, known_signatures=None)
    assert not fails and not any("BATTALION" in w for w in warns)
    # a real keyword dropped from a tree still fails
    flier = _card("Shacklegeist")
    raw = _raw()[_oid("Shacklegeist")]
    fails, _w = gates.g0(raw, flier, dataclasses.replace(flier, keywords=()), clauses=None, known_signatures=None)
    assert fails == ["MTGJSON keywords missing from the tree: ['FLYING']"]


# ----------------------------------------------------------------------------- G3
GRUB_MILL = "1/1/effect/args"


def test_mill_shape_from_and_destination_controllers_are_dead() -> None:
    grub = _card("Carrion Grub")
    offered = _where(grub)
    assert ("controller YOU->OPPONENT", f"{GRUB_MILL}/from/controller") not in offered
    assert ("controller YOU->OPPONENT", f"{GRUB_MILL}/destination/controller") not in offered
    assert ("controller YOU->OPPONENT", f"{GRUB_MILL}/controller") in offered  # whose library: live
    pack = _pack([{"key": "grub", "real": "Carrion Grub", "zone": "hand", "controller": 0},
                  *_library(0, "Yours"), *_library(1, "Theirs")], [{"op": "cast", "key": "grub"}],
                 {"0": {"B": 1, "C": 3}})
    real = _game(pack)
    milled = [o for o in real[0].values() if o[1] == "graveyard" and o[0].startswith("Yours")]
    assert len(milled) == 4  # the real tree mills four of your cards
    for where in (f"{GRUB_MILL}/from/controller", f"{GRUB_MILL}/destination/controller"):
        assert _game(pack, _mutant(grub, where, ControllerRef.OPPONENT)) == real, where
    both = _mutant(_mutant(grub, f"{GRUB_MILL}/from/controller", ControllerRef.OPPONENT),
                   f"{GRUB_MILL}/destination/controller", ControllerRef.OPPONENT)
    assert _game(pack, both) == real
    # the live neighbour is observable on the same board
    assert _game(pack, _mutant(grub, f"{GRUB_MILL}/controller", ControllerRef.OPPONENT)) != real


RAIN_DISCARD = "1/0/effect/steps/1/args"


def test_discard_shape_from_and_destination_controllers_are_dead() -> None:
    rain = _card("Rain of Revelation")
    offered = _where(rain)
    assert ("controller YOU->OPPONENT", f"{RAIN_DISCARD}/from/controller") not in offered
    assert ("controller YOU->OPPONENT", f"{RAIN_DISCARD}/destination/controller") not in offered
    assert ("zone GRAVEYARD->EXILE", f"{RAIN_DISCARD}/destination") in offered  # the kind stays live
    pack = _pack([{"key": "rain", "real": "Rain of Revelation", "zone": "hand", "controller": 0},
                  {"key": "keep", "name": "Keep", "type": "Instant", "zone": "hand", "controller": 0},
                  {"key": "junk", "name": "Junk", "type": "Sorcery", "zone": "hand", "controller": 0},
                  {"key": "ojunk", "name": "Opp Junk", "type": "Sorcery", "zone": "hand", "controller": 1},
                  *_library(0, "Yours"), *_library(1, "Theirs")],
                 [{"op": "cast", "key": "rain", "decisions": ["junk"]}], {"0": {"U": 1, "C": 3}})
    real = _game(pack)
    assert next(o for o in real[0].values() if o[0] == "Junk")[1:3] == ("graveyard", "player:0")
    for where in (f"{RAIN_DISCARD}/from/controller", f"{RAIN_DISCARD}/destination/controller"):
        assert _game(pack, _mutant(rain, where, ControllerRef.OPPONENT)) == real, where


def test_zone_count_ge_zone_controller_is_dead() -> None:
    tge = _card("Thieves' Guild Enforcer")
    where = "1/1/condition/zone/controller"
    assert ("controller OPPONENT->YOU", where) not in _where(tge)
    assert ("controller OPPONENT->YOU", "1/1/condition/who") in _where(tge)  # whose graveyard: live
    mutant = _mutant(tge, where, ControllerRef.YOU)
    for full in (0, 1):  # eight cards in your graveyard only, then in the opponent's only
        gy = [{"key": f"g{i}", "name": f"Dead {i}", "type": "Sorcery", "zone": "graveyard", "controller": full}
              for i in range(8)]
        pack = _pack([{"key": "tge", "real": "Thieves' Guild Enforcer", "zone": "battlefield", "controller": 0},
                      *gy], [])
        real = _game(pack)
        enforcer = next(o for o in real[0].values() if o[0] == "Thieves' Guild Enforcer")
        assert enforcer[5] == ((3, 2) if full == 1 else (1, 1))
        assert _game(pack, mutant) == real


WAKER_REST = "1/1/effect/steps/1/steps/1/args/cards/count"


def test_rest_partition_count_is_dead() -> None:
    waker = _card("Waker of Waves")
    assert ("amount+1", WAKER_REST) not in _where(waker)
    assert ("amount+1", WAKER_REST.replace("steps/1/args", "steps/0/args")) in _where(waker)  # the ONE_OF's
    pack = _pack([{"key": "waker", "real": "Waker of Waves", "zone": "hand", "controller": 0},
                  {"key": "c", "name": "Third", "type": "Instant", "zone": "library", "controller": 0},
                  {"key": "b", "name": "Second", "type": "Instant", "zone": "library", "controller": 0},
                  {"key": "a", "name": "First", "type": "Instant", "zone": "library", "controller": 0},
                  {"key": "opener", "name": "Opener", "type": "Sorcery", "zone": "library", "controller": 0}],
                 [{"op": "activate", "key": "waker", "idx": 1, "seat": 0, "decisions": ["b"]}],
                 {"0": {"U": 1, "C": 1}})
    real = _game(pack)
    assert {o[0]: o[1] for o in real[0].values() if o[0] in ("First", "Second", "Third")} == {
        "Second": "hand", "First": "graveyard", "Third": "library"}
    for n in (2, 3):
        assert _game(pack, _mutant(waker, WAKER_REST, QConst(n))) == real


KERAL_TARGET = "1/0/effect/effect/args/target/count"


def test_choose_over_your_player_zone_count_is_dead() -> None:
    keral = _card("Keral Keep Disciples")
    assert ("amount+1", KERAL_TARGET) not in _where(keral)
    assert ("amount+1", "1/0/effect/effect/args/amount") in _where(keral)  # the damage stays live
    pack = _pack([{"key": "ke", "real": "Keral Keep Disciples", "zone": "battlefield", "controller": 0},
                  {"key": "cat", "real": "Chandra, Flame's Catalyst", "zone": "battlefield", "controller": 0}],
                 [{"op": "loyalty", "key": "cat", "set": 5},
                  {"op": "activate", "key": "cat", "idx": 0, "seat": 0, "decisions": ["player:1"]}])
    real = _game(pack)
    assert [s[0] for s in real[1].values()] == [20, 16]  # Chandra's 3 and the Disciples' 1
    for n in (2, 3):
        assert _game(pack, _mutant(keral, KERAL_TARGET, QConst(n))) == real


HALO_TARGET = "1/1/effect/args/target/count"


def test_choose_over_your_player_zone_count_is_dead_in_a_static() -> None:
    """The same rule on a static's selector (Runed Halo's "You have protection ..."): the layer
    population is enumerate_candidates, which reads no count."""
    halo = _card("Runed Halo")
    assert ("amount+1", HALO_TARGET) not in _where(halo)
    pack = _pack([{"key": "h", "real": "Runed Halo", "zone": "hand", "controller": 0},
                  {"key": "oshock", "real": "Shock", "zone": "hand", "controller": 1},
                  {"key": "oshock2", "real": "Shock", "zone": "hand", "controller": 1},
                  {"key": "bear", "name": "Bear", "type": "Creature", "power": "2", "toughness": "2",
                   "zone": "battlefield", "controller": 0}],
                 [{"op": "enter", "key": "h", "decisions": ["Shock"]}, {"op": "end_turn"}, {"op": "advance_turn"},
                  {"op": "cast", "key": "oshock2", "controller": 1, "targets": ["bear"]},
                  {"op": "cast", "key": "oshock", "controller": 1, "decisions": ["player:0"]}],
                 {"1": {"R": 2}})
    real = _game(pack)
    for n in (2, 3):
        assert _game(pack, _mutant(halo, HALO_TARGET, QConst(n))) == real


EMPATH_REVEAL = "1/0/effect/inner/steps/1/args"
TRACK_REVEAL = "1/0/effect/steps/0/steps/1/args"


def test_reveal_nothing_reads_is_dead() -> None:
    empath = _card("Fierce Empath")
    offered = _where(empath)
    assert not {w for _op, w in offered if w.startswith(EMPATH_REVEAL)}
    assert ("amount+1", "1/0/effect/inner/steps/0/args/cards/count") in offered  # the search stays live
    pack = _pack([{"key": "emp", "real": "Fierce Empath", "zone": "hand", "controller": 0},
                  {"key": "big", "name": "Big Seven", "type": "Creature", "power": "7", "toughness": "7",
                   "cmc": 7, "zone": "library", "controller": 0},
                  *_library(0, "Yours", 3), *_library(1, "Theirs", 3)],
                 [{"op": "enter", "key": "emp", "decisions": ["fire", "big"]}])
    real = _game(pack)
    assert next(o for o in real[0].values() if o[0] == "Big Seven")[1] == "hand"
    assert _game(pack, _mutant(empath, f"{EMPATH_REVEAL}/controller", ControllerRef.OPPONENT)) == real
    assert _game(pack, _mutant(empath, f"{EMPATH_REVEAL}/count", QConst(2))) == real


def test_reveal_read_by_a_conditional_keeps_controller_live_and_count_dead() -> None:
    track = _card("Track Down")
    offered = _where(track)
    assert ("amount+1", f"{TRACK_REVEAL}/count") not in offered
    assert ("controller YOU->OPPONENT", f"{TRACK_REVEAL}/controller") in offered
    # top card an instant (no draw), the second a creature: a count read past the top would draw
    pack = _pack([{"key": "td", "real": "Track Down", "zone": "hand", "controller": 0},
                  {"key": "x2", "name": "Beast Two", "type": "Creature", "power": "2", "toughness": "2",
                   "zone": "library", "controller": 0},
                  {"key": "x1", "name": "Beast One", "type": "Creature", "power": "2", "toughness": "2",
                   "zone": "library", "controller": 0},
                  {"key": "spell", "name": "Spell", "type": "Instant", "zone": "library", "controller": 0},
                  {"key": "opener", "name": "Opener", "type": "Sorcery", "zone": "library", "controller": 0}],
                 [{"op": "cast", "key": "td", "decisions": ["top", "top", "top"]}], {"0": {"G": 2}})
    real = _game(pack)
    assert next(o for o in real[0].values() if o[0] == "Spell")[1] == "library"  # no draw
    for n in (2, 3):
        assert _game(pack, _mutant(track, f"{TRACK_REVEAL}/count", QConst(n))) == real
    assert _game(pack, _mutant(track, f"{TRACK_REVEAL}/controller", ControllerRef.OPPONENT)) != real


STRIKE = "1/0/effect/steps/{}/args/target"


def test_target_to_all_on_a_twin_designation_is_dead() -> None:
    strike = _card("Sure Strike")
    offered = _where(strike)
    assert not {w for op, w in offered if op == "target->all"}
    assert ("amount+1", STRIKE.format(0) + "/count") in offered  # the designation's count stays live
    pack = _pack([{"key": "ss", "real": "Sure Strike", "zone": "hand", "controller": 0},
                  {"key": "bear", "name": "Bear", "type": "Creature", "power": "2", "toughness": "2",
                   "zone": "battlefield", "controller": 0},
                  {"key": "elf", "name": "Elf", "type": "Creature", "power": "1", "toughness": "1",
                   "zone": "battlefield", "controller": 0},
                  {"key": "ox", "name": "Opp Ox", "type": "Creature", "power": "3", "toughness": "3",
                   "zone": "battlefield", "controller": 1}],
                 [{"op": "cast", "key": "ss", "targets": ["bear"]}], {"0": {"R": 1, "C": 1}})
    real = _game(pack)
    assert {o[0]: o[5:7] for o in real[0].values() if o[5]} == {
        "Bear": ((5, 2), ("FIRST_STRIKE",)), "Elf": ((1, 1), ()), "Opp Ox": ((3, 3), ())}
    alone = _pack([pack["cards"][0], pack["cards"][3]], [{"op": "cast", "key": "ss"}], pack["mana"])
    for step in (0, 1):
        sel = _at(strike, STRIKE.format(step))
        everyone = dataclasses.replace(sel, mode=SelectorMode.ALL, count=QUnbounded())
        mutant = _mutant(strike, STRIKE.format(step), everyone)
        assert _game(pack, mutant) == real, step
        # no target passed: the cast lane designates the one legal creature for both trees
        assert _game(alone, mutant) == _game(alone), step
    # no twin, no rule: a lone TARGET selector still gets the mutant
    assert ("target->all", "1/1/effect/args/target") in _where(_card("Shacklegeist"))
    # spells only: the same twin designation on an activated ability is left to the probe and the
    # packs, because activate() validates no targets (V8) and an ALL selector without a binding
    # acts on its whole population
    ability = ActivatedAbility(cost=Cost(parts=()), effect=strike.abilities[0].effect)
    assert gates._twin_targets(ability, (1, 0)) == set()
    assert gates._twin_targets(strike.abilities[0], (1, 0)) == {(1, 0, "effect", "steps", i, "args", "target")
                                                                for i in (0, 1)}
