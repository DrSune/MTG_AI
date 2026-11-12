"""Gates G0 and G3: the keyword-action and ability-word reading of G0, and the equivalent-mutant
rules of G3. Each G3 rule is proven twice: ``gates.mutants`` does not offer the mutant (while
its observable neighbours stay), and the engine plays the real tree and the would-be mutant to
the same game on a board built to expose the field if anything read it."""

from __future__ import annotations

import dataclasses
import sys
from functools import cache
from pathlib import Path
from typing import Any

import pytest

HERE = Path(__file__).resolve().parent
for _p in (HERE.parents[1], HERE, HERE.parent):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import gates
from irpy import A
from run_scenarios import ScenarioRunner

from MTG_bot.core.ability_tree import (
    ActivatedAbility,
    AtomArgs,
    ControllerRef,
    Cost,
    DurationPermanent,
    FAnd,
    Keyword,
    OptionalEffect,
    QConst,
    QUnbounded,
    Selector,
    SelectorMode,
    StaticAbility,
    TargetingEvent,
    TriggeredAbility,
    Verb,
    Zone,
    ZoneKind,
)
from MTG_bot.core.compiler.ingest import ingest_pool
from MTG_bot.core.executor.binding import _required_target_keys
from MTG_bot.core.executor.games import compile_supply

DATA = HERE.parents[1] / "MTG_bot" / "data"


@cache
def _compiled(code: str) -> Any:
    return compile_supply("all", code, require_verified=False)


def _supply(code: str = "M21") -> Any:
    """One supply per set (a mutant swapped into it is what every helper sees)."""
    return _compiled(code)


@cache
def _raw() -> dict:
    return ingest_pool(DATA / "M21.json")


def _oid(name: str, code: str = "M21") -> str:
    return next(o for o, m in _supply(code).metas.items() if m.name == name)


def _card(name: str, code: str = "M21") -> Any:
    return _supply(code).pool.results[_oid(name, code)].card


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


def _game(pack: dict, card: Any = None, setup: Any = None, inspect: Any = None) -> tuple:
    """The whole observable game after the pack's steps, on the supply of the pack's set, with
    ``card`` (a mutant) swapped in; ``setup`` may adjust the world before the steps run, and
    ``inspect(runner)`` adds what it returns to the game."""
    sup = _supply(pack["set"])
    with gates.swapped(sup, _oid(card.name, pack["set"]), card) if card is not None else _Null():
        r = ScenarioRunner(pack, sup)
        if setup is not None:
            setup(r)
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
        game = (objs, seats, ex.journal.dump(), refused)
        return game if inspect is None else (*game, inspect(r))


class _Null:
    def __enter__(self) -> None:
        return None

    def __exit__(self, *exc: object) -> None:
        return None


def _library(seat: int, prefix: str, n: int = 6) -> list[dict]:
    return [{"key": f"{prefix}{i}", "name": f"{prefix} {i}", "type": "Creature", "power": "1",
             "toughness": "1", "zone": "library", "controller": seat} for i in range(n)]


def _pack(cards: list[dict], steps: list[dict], mana: dict | None = None, code: str = "M21") -> dict:
    return {"set": code, "world": {"life": 20, "seed": 7, "library_top": True}, "cards": cards,
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
                  {"key": "opener", "name": "Opener", "type": "Sorcery", "zone": "hand", "controller": 0}],
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
                  {"key": "opener", "name": "Opener", "type": "Sorcery", "zone": "hand", "controller": 0}],
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
    # packs, because activate() validates no targets and an ALL selector without a binding
    # acts on its whole population
    ability = ActivatedAbility(cost=Cost(parts=()), effect=strike.abilities[0].effect)
    assert gates._twin_targets(ability, (1, 0)) == set()
    assert gates._twin_targets(strike.abilities[0], (1, 0)) == {(1, 0, "effect", "steps", i, "args", "target")
                                                                for i in (0, 1)}


# ------------------------------------------- owner zones, discards, statics, replacements
def test_owner_zone_destination_controller_is_dead() -> None:
    """A card moved to a hand, library, graveyard or exile goes to its OWNER's zone (CR 400.3,
    selectors.move_destination): a SEARCH to hand, a targeted return to hand, and a ONE_OF/REST
    partition to hand and graveyard all play the same game with the destination naming the
    opponent. A battlefield destination names a controller and stays live."""
    tutor, rebirth, waker = _card("Grim Tutor"), _card("Fungal Rebirth"), _card("Waker of Waves")
    t_dest, r_dest = "1/0/effect/steps/0/steps/0/args/destination", "1/0/effect/steps/0/args/destination"
    w_hand, w_grave = "1/1/effect/steps/1/steps/0/args/destination", "1/1/effect/steps/1/steps/1/args/destination"
    for card, where in ((tutor, t_dest), (rebirth, r_dest), (waker, w_hand), (waker, w_grave)):
        assert ("controller YOU->OPPONENT", f"{where}/controller") not in _where(card), where
    cultivate = _card("Cultivate")
    assert ("controller YOU->OPPONENT", "1/0/effect/steps/2/args/destination/controller") in _where(cultivate)
    tutor_pack = _pack([{"key": "gt", "real": "Grim Tutor", "zone": "hand", "controller": 0},
                        {"key": "prize", "name": "Prize", "type": "Instant", "zone": "library", "controller": 0},
                        *_library(0, "Yours", 2), *_library(1, "Theirs", 2)],
                       [{"op": "cast", "key": "gt", "decisions": ["prize"]}], {"0": {"B": 1, "C": 2}})
    rebirth_pack = _pack([{"key": "fr", "real": "Fungal Rebirth", "zone": "hand", "controller": 0},
                          {"key": "relic", "name": "Old Relic", "type": "Artifact", "zone": "graveyard", "controller": 0}],
                         [{"op": "cast", "key": "fr", "targets": ["relic"]}], {"0": {"G": 1, "C": 1}})
    waker_pack = _pack([{"key": "waker", "real": "Waker of Waves", "zone": "hand", "controller": 0},
                        {"key": "b", "name": "Second", "type": "Instant", "zone": "library", "controller": 0},
                        {"key": "a", "name": "First", "type": "Instant", "zone": "library", "controller": 0},
                        {"key": "opener", "name": "Opener", "type": "Sorcery", "zone": "hand", "controller": 0}],
                       [{"op": "activate", "key": "waker", "idx": 1, "seat": 0, "decisions": ["b"]}],
                       {"0": {"U": 1, "C": 1}})
    for card, where, pack, moved in ((tutor, t_dest, tutor_pack, "Prize"), (rebirth, r_dest, rebirth_pack, "Old Relic"),
                                     (waker, w_hand, waker_pack, "Second"), (waker, w_grave, waker_pack, "First")):
        real = _game(pack)
        assert next(o for o in real[0].values() if o[0] == moved)[2] == "player:0"  # its owner's zone
        dest = _at(card, where)
        assert _game(pack, _mutant(card, where, dataclasses.replace(dest, controller=ControllerRef.OPPONENT))) == real


def test_owner_zone_rule_leaves_the_top_n_draw_idiom_live() -> None:
    """The draw idiom ("put the top card of your library into your hand") is the one move lane
    whose destination names a player (zone_owner picks whose library is drawn), so the rule leaves
    it out; no M21 card carries it, so a bare atom shows the field is live there."""
    draw = A(Verb.MOVE_ZONE, {
        "cards": Selector(count=QConst(value=1), mode=SelectorMode.CHOOSE, filter=FAnd(children=()),
                          zones=(Zone(kind=ZoneKind.LIBRARY, controller=ControllerRef.YOU),)),
        "destination": Zone(kind=ZoneKind.HAND, controller=ControllerRef.YOU)})
    assert gates._draw_idiom(draw)
    tutor = _card("Grim Tutor")
    assert not gates._draw_idiom(tutor.abilities[0].effect.steps[0].steps[0])
    outcomes = []
    for who in (ControllerRef.YOU, ControllerRef.OPPONENT):
        atom = A(Verb.MOVE_ZONE, {"cards": draw.args.get("cards"),
                                  "destination": Zone(kind=ZoneKind.HAND, controller=who)})
        r = ScenarioRunner(_pack([{"key": "bear", "name": "Bear", "type": "Creature", "power": "2",
                                   "toughness": "2", "zone": "battlefield", "controller": 0}], []), _supply())
        try:
            r.ex.execute(atom, source=r.handles["bear"], controller=r.p0, bindings={})
            outcomes.append(tuple(len(r.world.players[p].zone("hand").entries) for p in r.world.player_order))
        except NotImplementedError as exc:  # zone_owner reads the destination's player
            outcomes.append(str(exc))
    assert outcomes[0] == (1, 0)  # you draw the top card
    assert outcomes[1] == "executor: zone controller ref OPPONENT needs multiple owners (12b)"


AUGUR_DISCARD = "1/1/effect/steps/0/args/cards/zones/0/controller"


def test_discard_selector_zones_are_dead_outside_a_may() -> None:
    """A CHOOSE/RANDOM/ALL discard takes its picks from the discarding player's own hand
    (verbs.py _discard_picks reads filter, mode and count): Kinetic Augur's discard plays the same
    with its cards selector naming the opponent's hand. Under a "you may" the offer enumerates
    those zones (query.optional_offer), so Crypt Lurker's stays live."""
    augur = _card("Kinetic Augur")
    assert ("controller YOU->OPPONENT", AUGUR_DISCARD) not in _where(augur)
    lurker = "1/0/effect/steps/0/inner/options/1/args/cards/zones/0/controller"
    assert ("controller YOU->OPPONENT", lurker) in _where(_card("Crypt Lurker"))
    pack = _pack([{"key": "aug", "real": "Kinetic Augur", "zone": "hand", "controller": 0},
                  {"key": "junk", "name": "Junk", "type": "Sorcery", "zone": "hand", "controller": 0},
                  {"key": "keep", "name": "Keep", "type": "Instant", "zone": "hand", "controller": 0},
                  {"key": "ojunk", "name": "Opp Junk", "type": "Sorcery", "zone": "hand", "controller": 1},
                  *_library(0, "Yours", 3), *_library(1, "Theirs", 3)],
                 [{"op": "cast", "key": "aug", "decisions": ["junk", "NONE"]}], {"0": {"R": 1, "C": 3}})
    real = _game(pack)
    assert next(o for o in real[0].values() if o[0] == "Junk")[1] == "graveyard"
    assert next(o for o in real[0].values() if o[0] == "Opp Junk")[1] == "hand"
    assert _game(pack, _mutant(augur, AUGUR_DISCARD, ControllerRef.OPPONENT)) == real


def test_static_permission_may_is_dead() -> None:
    """A static permission's "you may" is the use: layers._new_static strips the OptionalEffect
    before parsing the payload. Azusa's three land drops play the same with the wrapper gone, and
    a trigger's "you may" (an ask) stays live."""
    azusa = _card("Azusa, Lost but Seeking")
    assert ("optional->mandatory", "1/0/effect") not in _where(azusa)
    assert ("optional->mandatory", "1/0/effect") not in _where(_card("Chromatic Orrery"))
    assert ("optional->mandatory", "1/0/effect") not in _where(_card("Teferi, Master of Time"))
    assert ("optional->mandatory", "1/0/effect") in _where(_card("Solemn Simulacrum"))  # a trigger's may
    lands = [{"key": f"l{i}", "real": "Forest", "zone": "hand", "controller": 0} for i in range(4)]
    pack = _pack([{"key": "az", "real": "Azusa, Lost but Seeking", "zone": "battlefield", "controller": 0},
                  *lands], [{"op": "play", "key": f"l{i}"} for i in range(3)])
    real = _game(pack)
    assert sum(o[0] == "Forest" and o[1] == "battlefield" for o in real[0].values()) == 3
    assert _game(pack, _mutant(azusa, "1/0/effect", azusa.abilities[0].effect.inner)) == real
    fourth = _pack(pack["cards"], [*pack["steps"], {"op": "play", "key": "l3"}])
    assert _game(fourth)[3] == _game(fourth, _mutant(azusa, "1/0/effect", azusa.abilities[0].effect.inner))[3]


def test_damage_replacement_action_dealer_is_dead() -> None:
    """Fiery Emancipation's action is a DEAL_DAMAGE whose amount rewrites the event's; the lane
    never runs the action (replacements.replacements_for_damage), so its dealer is never read."""
    fiery = _card("Fiery Emancipation")
    assert ("controller YOU->OPPONENT", "1/0/action/args/dealer/who") not in _where(fiery)
    pack = _pack([{"key": "fe", "real": "Fiery Emancipation", "zone": "battlefield", "controller": 0},
                  {"key": "bear", "name": "Bear", "type": "Creature", "power": "2", "toughness": "2",
                   "zone": "battlefield", "controller": 0},
                  {"key": "giant", "name": "Opp Giant", "type": "Creature", "power": "7", "toughness": "7",
                   "zone": "battlefield", "controller": 1}],
                 [{"op": "deal_damage", "source": "bear", "target": "giant", "amount": 2},
                  {"op": "deal_damage", "source": "giant", "target": "bear", "amount": 1, "controller": 1}])
    real = _game(pack)
    assert {o[0]: o[7] for o in real[0].values() if o[0] in ("Bear", "Opp Giant")} == {"Bear": 1, "Opp Giant": 6}
    who = _at(fiery, "1/0/action/args/dealer")
    assert _game(pack, _mutant(fiery, "1/0/action/args/dealer", dataclasses.replace(
        who, who=ControllerRef.OPPONENT))) == real


LOFTY = "1/0/effect/{}/args/target"


def test_target_to_all_on_a_twin_stack_designation_is_dead() -> None:
    """Lofty Denial's two branches counter the same designated spell; COUNTER_SPELL reads it
    through role_handles, so an ALL selector over the stack in either branch counters exactly the
    designated spell (with and without the flier that picks the {4} branch)."""
    lofty = _card("Lofty Denial")
    assert not {w for op, w in _where(lofty) if op == "target->all"}
    for flier in (False, True):
        cards = [{"key": "mate", "real": "Staunch Shieldmate", "zone": "hand", "controller": 0},
                 {"key": "lofty", "real": "Lofty Denial", "zone": "hand", "controller": 1}]
        if flier:
            cards.append({"key": "bird", "name": "Sky Bird", "type": "Creature — Bird", "power": "1",
                          "toughness": "1", "keywords": ["FLYING"], "zone": "battlefield", "controller": 1})
        # the Shieldmate waits on the stack; Lofty Denial is cast at it, and its controller pays
        pack = _pack(cards, [{"op": "cast", "key": "mate", "hold": True},
                             {"op": "cast", "key": "lofty", "real": "Lofty Denial", "controller": 1,
                              "targets": ["mate"], "decisions": ["PAY"]}],
                     {"0": {"W": 1, "R": 2}, "1": {"U": 2}})
        real = _game(pack)
        assert next(o for o in real[0].values() if o[0] == "Staunch Shieldmate")[1] == (
            "graveyard" if flier else "battlefield")
        for branch in ("then_effect", "else_effect"):
            sel = _at(lofty, LOFTY.format(branch))
            everyone = dataclasses.replace(sel, mode=SelectorMode.ALL, count=QUnbounded())
            assert _game(pack, _mutant(lofty, LOFTY.format(branch), everyone)) == real, (flier, branch)


HARBINGER_REVEAL = "1/0/effect/steps/1/inner/steps/0/args"


def test_reveal_from_a_look_window_is_dead() -> None:
    """Garruk's Harbinger: "look at that many cards ... You may reveal a creature card ... from
    among them and put it into your hand. Put the rest on the bottom." The REVEAL right after the
    LOOK_AT reads that window (verbs.py _look, prior-window branch): with cards in the library the
    controller and count change nothing; with an empty library the mutant reveals the opponent's
    top card, and the library-top partitions, which keep only cards in your library, ignore it."""
    harb = _card("Garruk's Harbinger")
    offered = _where(harb)
    assert not {w for _op, w in offered if w.startswith(HARBINGER_REVEAL)}
    assert ("amount+1", "1/0/effect/steps/1/inner/steps/1/args/cards/count") in offered  # the pick stays live
    pack = _pack([{"key": "gh", "real": "Garruk's Harbinger", "zone": "battlefield", "controller": 0},
                  {"key": "beast", "name": "Beast", "type": "Creature", "power": "3", "toughness": "3",
                   "zone": "library", "controller": 0},
                  {"key": "spell", "name": "Spell", "type": "Instant", "zone": "library", "controller": 0},
                  {"key": "opener", "name": "Opener", "type": "Sorcery", "zone": "hand", "controller": 0},
                  *_library(1, "Theirs", 2)],
                 [{"op": "combat", "seat": 0, "attack": {"gh": True}, "may": {"gh": True}, "decisions": ["beast"]}])

    def empty_library(r: ScenarioRunner) -> None:
        for h in list(r.world.players[r.p0].zone("library").entries):
            r.world.move_to_zone(h, r.p0, "exile")

    mutants = (_mutant(harb, f"{HARBINGER_REVEAL}/controller", ControllerRef.OPPONENT),
               _mutant(harb, f"{HARBINGER_REVEAL}/count", QConst(2)))
    real = _game(pack)
    assert next(o for o in real[0].values() if o[0] == "Beast")[1] == "hand"  # the pick from the window
    assert real[1]["player:1"][0] == 16  # 4 combat damage
    for mutant in mutants:
        assert _game(pack, mutant) == real
    real_empty = _game(pack, setup=empty_library)
    for mutant in mutants:
        assert _game(pack, mutant, setup=empty_library) == real_empty


# ---------------------------------------------- the "library and/or graveyard" zone choice
WARSTEED_OPTION = "1/0/effect/inner/options/{}/steps/{}/args"


def test_reveal_per_option_of_a_zone_choice_is_dead() -> None:
    """"Search your library and/or graveyard" is a choose-one of three searches, each with
    its own REVEAL. Exactly one option runs, so at most one REVEAL does, and nothing reads it:
    every option plays the same game with its REVEAL naming the opponent or revealing two."""
    ws = _card("Garruk's Warsteed")
    offered = _where(ws)
    for option in (0, 1, 2):
        assert not {w for _op, w in offered if w.startswith(WARSTEED_OPTION.format(option, 1))}
    assert ("amount+1", WARSTEED_OPTION.format(1, 0) + "/cards/count") in offered  # each search stays live
    for option in (0, 1, 2):
        pack = _pack([{"key": "ws", "real": "Garruk's Warsteed", "zone": "hand", "controller": 0},
                      {"key": "g_gy", "real": "Garruk, Savage Herald", "zone": "graveyard", "controller": 0},
                      {"key": "g_lib", "real": "Garruk, Savage Herald", "zone": "library", "controller": 0},
                      {"key": "opener", "name": "Opener", "type": "Instant", "zone": "hand", "controller": 0},
                      *_library(1, "Theirs", 2)],
                     [{"op": "enter", "key": "ws", "decisions": ["fire", str(option), "g_gy" if option != 1 else "g_lib"]}])
        real = _game(pack)
        found = "Garruk, Savage Herald"
        assert sum(o[0] == found and o[1] == "hand" for o in real[0].values()) == 1, option
        reveal = WARSTEED_OPTION.format(option, 1)
        assert _game(pack, _mutant(ws, f"{reveal}/controller", ControllerRef.OPPONENT)) == real, option
        assert _game(pack, _mutant(ws, f"{reveal}/count", QConst(2))) == real, option
    # not one per option: a "choose two" could run two REVEALs in a row, so the rule stays off
    choose = ws.abilities[0].effect.inner
    two = dataclasses.replace(ws.abilities[0], effect=dataclasses.replace(
        ws.abilities[0].effect, inner=dataclasses.replace(choose, count=QConst(value=2))))
    assert gates._reveal_dead_roles(two) == set()
    assert gates._reveal_dead_roles(ws.abilities[0]) == {"controller", "count"}


CULTIVATE_SEARCH = "1/0/effect/steps/0/args/destination"


def test_partitioned_search_destination_is_a_placeholder() -> None:
    """Cultivate's SEARCH sits in a Seq with a ONE_OF/REST partition, so it only designates the
    found cards (ctx.search_partition; verbs._v_search moves nothing): its destination is never
    used. A SEARCH that delivers (Solemn Simulacrum's) keeps its destination mutants."""
    cult = _card("Cultivate")
    offered = _where(cult)
    assert not {w for _op, w in offered if w.startswith(CULTIVATE_SEARCH)}
    assert ("amount+1", "1/0/effect/steps/0/args/cards/count") in offered  # the search count stays live
    assert ("zone BATTLEFIELD->HAND", "1/0/effect/inner/steps/0/args/destination") in _where(_card("Solemn Simulacrum"))
    basics = [{"key": k, "real": n, "zone": "library", "controller": 0}
              for k, n in (("forest", "Forest"), ("swamp", "Swamp"), ("island", "Island"))]
    pack = _pack([{"key": "cv", "real": "Cultivate", "zone": "hand", "controller": 0}, *basics,
                  {"key": "opener", "name": "Opener", "type": "Instant", "zone": "hand", "controller": 0}],
                 [{"op": "cast", "key": "cv", "decisions": ["card:1", "card:2", "card:1"]}], {"0": {"G": 1, "C": 2}})
    real = _game(pack)
    zones = {o[0]: o[1] for o in real[0].values() if o[0] in ("Forest", "Swamp", "Island")}
    assert zones == {"Forest": "battlefield", "Swamp": "hand", "Island": "library"}
    dest = _at(cult, CULTIVATE_SEARCH)
    for new in (dataclasses.replace(dest, kind=ZoneKind.HAND), dataclasses.replace(dest, controller=ControllerRef.OPPONENT)):
        assert _game(pack, _mutant(cult, CULTIVATE_SEARCH, new)) == real


def test_trigger_count_mutants_only_where_one_event_holds_several_occurrences() -> None:
    """once_per_event (CR 603.2c), both directions critical: dropping it (Tide Skimmer would draw
    for each flyer) and forgetting it (Hooded Blightfang's drain fires per deathtouch attacker, so
    the flagged mutant drains once). Adding it is offered only where one declaration or combat
    damage step can hold several occurrences the trigger matches (ability_tree.gathers_occurrences):
    never on "this creature" (Falconer Adept, Garruk's Harbinger) or noncombat damage (Chandra's
    Incinerator), where the IR refuses the flag as a second encoding of the same trigger."""
    assert ("trigger count: once per event -> each occurrence", "1/0") in _where(_card("Tide Skimmer"))
    assert ("each occurrence -> once per event", "1/0") in _where(_card("Hooded Blightfang"))
    assert gates.is_critical("trigger count: once per event -> each occurrence")
    assert gates.is_critical("each occurrence -> once per event")
    for name in ("Falconer Adept", "Garruk's Harbinger", "Chandra's Incinerator"):
        assert not {op for op, _w in _where(_card(name)) if "occurrence" in op}, name
    adept = _card("Falconer Adept")
    trigger = next(ab for ab in adept.abilities if hasattr(ab, "once_per_event"))
    with pytest.raises(ValueError, match="gathers occurrences"):
        dataclasses.replace(trigger, once_per_event=True)


# ------------------------------------- verification wave 1's equivalent mutants (KNOWLEDGE 201)
def _everyone(card: Any, where: str) -> Any:
    """The "target->all" mutant at ``where``, as gates.mutants builds it."""
    sel = _at(card, where)
    return _mutant(card, where, dataclasses.replace(sel, mode=SelectorMode.ALL, count=QUnbounded()))


def _wall(key: str, name: str, seat: int) -> dict:
    return {"key": key, "name": name, "type": "Creature — Wall", "power": "0", "toughness": "3",
            "zone": "battlefield", "controller": seat}


GODS = "1/0/effect/steps/0/options/{}/args/target"


def test_target_to_all_on_twins_in_a_resolution_choice_is_dead() -> None:
    """Gods Willing (M20): "Target creature you control gains protection from the color of your
    choice until end of turn. Scry 1." The colour is a Choose made as the spell resolves, and
    each of its five options carries the same TARGET selector: the cast lane walks them all to one
    slot (query.spell_target_slots) and refuses a cast that does not designate it, so a mutant
    whose chosen colour holds the ALL selector protects the designated creature only
    (role_handles). Where the printed "target" matters: two creatures you control, one
    targeted, a source of each colour dealing damage to both; a fizzle; no legal target."""
    gw = _card("Gods Willing", "M20")
    offered = _where(gw)
    assert not {w for op, w in offered if op == "target->all"}
    assert ("amount+1", GODS.format(0) + "/count") in offered  # the designation's count stays live
    assert ("controller YOU->OPPONENT", GODS.format(0) + "/filter/children/0/who") in offered
    mutants = [_everyone(gw, GODS.format(j)) for j in range(5)]
    spell = {"key": "gw", "real": "Gods Willing", "zone": "hand", "controller": 0}
    for i, colour in enumerate("WUBRG"):
        source = {"key": "src", "name": "Source", "type": "Creature", "power": "3", "toughness": "3",
                  "colors": [colour], "zone": "battlefield", "controller": 1}
        hits = [{"op": "deal_damage", "source": "src", "target": k, "amount": 3, "controller": 1}
                for k in ("w1", "w2", "ow")]
        pack = _pack([spell, _wall("w1", "Wall One", 0), _wall("w2", "Wall Two", 0), _wall("ow", "Opp Wall", 1), source],
                     [{"op": "cast", "key": "gw", "targets": ["w1"], "decisions": [str(i), "top"]}, *hits],
                     {"0": {"W": 1}}, "M20")
        real = _game(pack)
        assert {o[0]: o[1] for o in real[0].values() if "Wall" in o[0]} == {
            "Wall One": "battlefield", "Wall Two": "graveyard", "Opp Wall": "graveyard"}, colour
        for j, mutant in enumerate(mutants):
            assert _game(pack, mutant) == real, (colour, j)
    # the target leaves while the spell waits: both fizzle and ask nothing (no colour, no scry)
    fizzle = _pack([spell, _wall("w1", "Wall One", 0), _wall("w2", "Wall Two", 0)],
                   [{"op": "cast", "key": "gw", "targets": ["w1"], "hold": True}, {"op": "move", "key": "w1", "to": "hand"}],
                   {"0": {"W": 1}}, "M20")
    # no creature you control: both refuse the cast
    alone = _pack([spell, _wall("ow", "Opp Wall", 1)], [{"op": "cast", "key": "gw", "decisions": ["0", "top"]}],
                  {"0": {"W": 1}}, "M20")
    assert _game(fizzle)[3] is None and _game(alone)[3] is not None
    for pack in (fizzle, alone):
        real = _game(pack)
        for j, mutant in enumerate(mutants):
            assert _game(pack, mutant) == real, j
    # the near shape: the same five grants as a modal spell (a top-level Choose, CR 700.2), whose
    # announced mode alone has targets (query.with_modes); a mutant's mode holds no slot
    modal = dataclasses.replace(gw, abilities=(dataclasses.replace(gw.abilities[0], effect=gw.abilities[0].effect.steps[0]),))
    assert gates._twin_targets(modal.abilities[0], (1, 0)) == set()
    assert ("target->all", "1/0/effect/options/3/args/target") in _where(modal)
    red = {"key": "src", "name": "Source", "type": "Creature", "power": "3", "toughness": "3", "colors": ["R"],
           "zone": "battlefield", "controller": 1}
    hits = [{"op": "deal_damage", "source": "src", "target": k, "amount": 3, "controller": 1} for k in ("w1", "w2")]
    pack = _pack([spell, _wall("w1", "Wall One", 0), _wall("w2", "Wall Two", 0), red],
                 [{"op": "cast", "key": "gw", "decisions": ["3"]}, *hits], {"0": {"W": 1}}, "M20")
    walls = {o[0]: o[1] for o in _game(pack, _everyone(modal, "1/0/effect/options/3/args/target"))[0].values()
             if "Wall" in o[0]}
    assert walls == {"Wall One": "battlefield", "Wall Two": "battlefield"}  # every creature you control
    assert _game(pack, modal)[3] is not None  # the card's mode needs its target


BATTLESONG = "1/0/effect/steps/{}/args/target"


def test_target_to_all_on_twins_in_a_trigger_is_dead() -> None:
    """Battlesong Berserker (FDN): "Whenever you attack, target creature you control gets +1/+0
    and gains menace until end of turn." Both steps carry the same TARGET selector: the trigger
    designates the one slot as it goes on the stack (binding.TriggerBinder._designate), and the
    slot outside any Choose stays required in each mutant (binding._required_target_keys), so the
    ALL step acts on the designation (role_handles). Three creatures you control, two attack."""
    bb = _card("Battlesong Berserker", "FDN")
    offered = _where(bb)
    assert not {w for op, w in offered if op == "target->all"}
    assert ("amount+1", BATTLESONG.format(0) + "/count") in offered
    sel = _at(bb, BATTLESONG.format(0))
    mutants = [_everyone(bb, BATTLESONG.format(step)) for step in (0, 1)]
    for mutant in mutants:  # CR 603.3d removes the card and the mutant alike
        assert repr(sel) in _required_target_keys(mutant.abilities[0].effect)
    creature = {"type": "Creature", "zone": "battlefield"}
    cards = [{"key": "bb", "real": "Battlesong Berserker", "zone": "battlefield", "controller": 0},
             {**creature, "key": "bear", "name": "Bear", "power": "2", "toughness": "2", "controller": 0},
             {**creature, "key": "elf", "name": "Elf", "power": "1", "toughness": "1", "controller": 0},
             {**creature, "key": "ox", "name": "Opp Ox", "power": "3", "toughness": "3", "controller": 1}]
    for target, pumped in (("bear", "Bear"), ("bb", "Battlesong Berserker")):
        pack = _pack(cards, [{"op": "combat", "seat": 0, "attack": {"bb": True, "bear": True, "elf": False},
                              "decisions": [target]}], code="FDN")
        real = _game(pack)
        assert {o[0] for o in real[0].values() if o[6] and "MENACE" in o[6]} == {pumped}
        for mutant in mutants:
            assert _game(pack, mutant) == real, target


KRAKEN = "1/0/effect/inner/steps/1/inner/options/{}/args/target"


def test_target_to_all_on_twins_in_a_trigger_choice_stays_live() -> None:
    """The near shape: Tolarian Kraken's "you may tap or untap target creature" puts the twins in
    the two options of a Choose, so the card's slot is required (every option carries it) and
    each mutant's is not (binding._required_target_keys). With no legal target (the Kraken alone,
    with protection from blue from Feat of Resistance) the card's trigger is removed as it goes
    on the stack (CR 603.3d) and the mutant's waits there. (CR 603.12 would put the draw trigger
    on the stack too; the reflexive trigger is the BACKLOG item "Reflexive triggers choose their
    targets too early".)"""
    kraken = _card("Tolarian Kraken")
    assert gates._twin_targets(kraken.abilities[0], (1, 0)) == set()
    sel = _at(kraken, KRAKEN.format(0))
    assert repr(sel) in _required_target_keys(kraken.abilities[0].effect)
    for option in (0, 1):
        assert ("target->all", KRAKEN.format(option)) in _where(kraken)
        assert repr(sel) not in _required_target_keys(_everyone(kraken, KRAKEN.format(option)).abilities[0].effect)
    pack = _pack([{"key": "k", "real": "Tolarian Kraken", "zone": "battlefield", "controller": 0},
                  {"key": "feat", "real": "Feat of Resistance", "zone": "hand", "controller": 0},
                  {"key": "ct", "real": "Crash Through", "zone": "hand", "controller": 0}],
                 [{"op": "cast", "key": "feat", "targets": ["k"], "decisions": ["1"]},
                  {"op": "cast", "key": "ct", "hold": True}, {"op": "resolve"},
                  {"op": "mana", "seat": 0, "add": {"C": 1}, "hold": True}],
                 {"0": {"W": 1, "R": 1, "C": 1}})

    def stack(r: ScenarioRunner) -> tuple:
        return tuple(frame.spell_kind for frame in r.ex.stack.frames)

    assert _game(pack, inspect=stack)[4] == ()
    for option in (0, 1):
        assert _game(pack, _everyone(kraken, KRAKEN.format(option)), inspect=stack)[4] == ("TRIGGERED",)


def test_trigger_scope_of_an_end_step_raid_is_dead() -> None:
    """Searslicer Goblin (FDN): "Raid — At the beginning of your end step, if you attacked this
    turn, create a 1/1 red Goblin creature token." The condition already requires TURN_OF YOU, so
    on the opponent's turn the scope mutant's event matches and its intervening "if" fails at once
    (TriggerBinder._queue): nothing is queued. Both players attack, each end step passes. The
    near shape, Barrin, Tolarian Archmage (M21), has no TURN_OF in its condition: its scope mutant
    stays and draws on the opponent's end step."""
    gob = _card("Searslicer Goblin", "FDN")
    offered = _where(gob)
    assert not {op for op, _w in offered if op.startswith("trigger scope")}
    assert ("controller YOU->OPPONENT", "1/0/event/actor/who") in offered  # whose end step: live
    assert ("controller YOU->OPPONENT", "1/0/condition/children/0/who") in offered
    every_turn = _mutant(gob, "1/0/event", dataclasses.replace(gob.abilities[0].event, actor=None))
    creature = {"type": "Creature", "zone": "battlefield"}
    pack = _pack([{"key": "sg", "real": "Searslicer Goblin", "zone": "battlefield", "controller": 0},
                  {**creature, "key": "bear", "name": "Bear", "power": "2", "toughness": "2", "controller": 0},
                  {**creature, "key": "ox", "name": "Opp Ox", "power": "3", "toughness": "3", "controller": 1}],
                 [{"op": "combat", "seat": 0, "attack": {"bear": True}}, {"op": "end_turn"}, {"op": "advance_turn"},
                  {"op": "combat", "seat": 1, "attack": {"ox": True}}, {"op": "end_turn"}, {"op": "advance_turn"}],
                 code="FDN")
    real = _game(pack)
    assert sum(o[0] == "Goblin" for o in real[0].values()) == 1  # your end step only
    assert _game(pack, every_turn) == real
    barrin = _card("Barrin, Tolarian Archmage")
    assert ("trigger scope: your turn -> each turn", "1/1/event") in _where(barrin)
    pack = _pack([{"key": "ba", "real": "Barrin, Tolarian Archmage", "zone": "battlefield", "controller": 0},
                  {**creature, "key": "bear", "name": "Bear", "power": "2", "toughness": "2", "controller": 0}],
                 [{"op": "end_turn"}, {"op": "advance_turn"}, {"op": "move", "key": "bear", "to": "hand"},
                  {"op": "end_turn"}])

    def hand(game: tuple) -> int:
        return sum(o[1] == "hand" for o in game[0].values())

    every_turn = _mutant(barrin, "1/1/event", dataclasses.replace(barrin.abilities[1].event, actor=None))
    assert (hand(_game(pack)), hand(_game(pack, every_turn))) == (2, 3)


BEETLE = "1/0/effect/args/condition"


def test_static_prevention_condition_is_dead() -> None:
    """Blightbeetle (M20): "Creatures your opponents control can't have +1/+1 counters put on
    them." layers._new_static registers the PREVENT_EFFECT with the StaticAbility's own condition;
    the atom's ``condition`` is never read (only the resolved lane, verbs._v_prevent, and a
    TargetingEvent static, legality._own_targeting_restrictions, read it). A read condition
    "creatures you control" beside the event's "creatures your opponents control" would prevent
    nothing: Sorin's +1 on each side's Vampire, Squad Captain entering with counters on each side.
    The near shape, Pack Leader's resolved prevention (M21), keeps its condition live."""
    beetle = _card("Blightbeetle", "M20")
    offered = _where(beetle)
    assert not {w for _op, w in offered if w.startswith(BEETLE)}
    assert ("controller OPPONENT->YOU", "1/0/effect/args/event/filter/children/0/who") in offered
    flipped = _mutant(beetle, f"{BEETLE}/children/0/who", ControllerRef.YOU)
    dropped = _mutant(beetle, BEETLE, FAnd(children=()))
    bb = {"key": "bb", "real": "Blightbeetle", "zone": "battlefield", "controller": 0}

    def vampire(key: str, seat: int) -> dict:
        return {"key": key, "name": f"Vampire {seat}", "type": "Creature — Vampire", "power": "2", "toughness": "2",
                "zone": "battlefield", "controller": seat}

    def sorin(key: str, seat: int) -> dict:
        return {"key": key, "real": "Sorin, Imperious Bloodlord", "zone": "battlefield", "controller": seat}

    packs = {  # the vampire or captain, and whether the printed card lets its counter land
        ("ov", False): _pack([bb, sorin("s1", 1), vampire("ov", 1)],
                             [{"op": "advance_turn"}, {"op": "loyalty", "key": "s1", "set": 4},
                              {"op": "activate", "key": "s1", "idx": 0, "seat": 1, "targets": ["ov"]}], code="M20"),
        ("mv", True): _pack([bb, sorin("s0", 0), vampire("mv", 0)],
                            [{"op": "loyalty", "key": "s0", "set": 4},
                             {"op": "activate", "key": "s0", "idx": 0, "seat": 0, "targets": ["mv"]}], code="M20"),
        ("cap", False): _pack([bb, vampire("ov", 1), {"key": "cap", "real": "Squad Captain", "zone": "hand", "controller": 1}],
                              [{"op": "enter", "key": "cap"}], code="M20"),
        ("cap", True): _pack([bb, vampire("mv", 0), {"key": "cap", "real": "Squad Captain", "zone": "hand", "controller": 0}],
                             [{"op": "enter", "key": "cap"}], code="M20"),
    }
    for (key, lands), pack in packs.items():
        real = _game(pack)
        handle = str(ScenarioRunner(pack, _supply("M20")).handles[key])
        assert bool(dict(real[0][handle][4]).get("PLUS_1_PLUS_1")) is lands, key
        assert _game(pack, flipped) == real == _game(pack, dropped), key
    leader = _card("Pack Leader")
    where = "1/1/effect/args/condition/children/0/who"
    assert ("controller YOU->OPPONENT", where) in _where(leader)
    pack = _pack([{"key": "pl", "real": "Pack Leader", "zone": "battlefield", "controller": 0},
                  {"key": "ox", "name": "Opp Ox", "type": "Creature", "power": "3", "toughness": "3",
                   "zone": "battlefield", "controller": 1}],
                 [{"op": "combat", "seat": 0, "attack": {"pl": True}, "block": {"ox": "pl"}}])

    def leader_zone(game: tuple) -> str:
        return next(o[1] for o in game[0].values() if o[0] == "Pack Leader")

    assert leader_zone(_game(pack)) == "battlefield"  # the damage to it is prevented
    assert leader_zone(_game(pack, _mutant(leader, where, ControllerRef.OPPONENT))) == "graveyard"
    # a static over a TargetingEvent reads its atom's condition (Enthralling Hold's restriction)
    atom = beetle.abilities[0].effect
    event = TargetingEvent(filter=atom.args.get("event").filter)
    targeting = StaticAbility(effect=dataclasses.replace(atom, args=AtomArgs(pairs=tuple(
        (role, event if role == "event" else value) for role, value in atom.args.pairs))))
    assert gates._static_prevention_conditions(targeting, (1, 0)) == set()
    assert gates._static_prevention_conditions(beetle.abilities[0], (1, 0)) == {(1, 0, "effect", "args", "condition")}


GARRUK_MAY = "1/2/effect/args/ability/effect"


def test_granted_damage_policy_may_is_dead() -> None:
    """Garruk, Savage Herald's -7: "Until end of turn, creatures you control gain 'You may have
    this creature assign its combat damage as though it weren't blocked.'" The granted static is
    never parsed as a layer; layers.policy_as_unblocked unwraps its OptionalEffect, and the combat
    damage step asks the policy question of every blocked creature that carries it. The mandatory
    mutant plays every answer the same, asks included. Its duration stays live: a permanent grant
    asks again on a later turn."""
    garruk = _card("Garruk, Savage Herald")
    offered = _where(garruk)
    assert ("optional->mandatory", GARRUK_MAY) not in offered
    assert ("until-end-of-turn->permanent", "1/2/effect/args/duration") in offered
    assert gates._granted_policy_may(_at(garruk, "1/2/effect"))
    mandatory = _mutant(garruk, GARRUK_MAY, _at(garruk, GARRUK_MAY).inner)
    creature = {"type": "Creature", "zone": "battlefield"}
    cards = [{"key": "g", "real": "Garruk, Savage Herald", "zone": "battlefield", "controller": 0},
             {**creature, "key": "bear", "name": "Bear", "power": "2", "toughness": "2", "controller": 0},
             {**creature, "key": "elf", "name": "Elf", "power": "1", "toughness": "1", "controller": 0},
             {**creature, "key": "blk", "name": "Wall", "power": "0", "toughness": "5", "controller": 1},
             {**creature, "key": "blk2", "name": "Wall Two", "power": "0", "toughness": "5", "controller": 1}]
    minus7 = [{"op": "loyalty", "key": "g", "set": 7}, {"op": "activate", "key": "g", "idx": 2, "seat": 0}]

    def asks(r: ScenarioRunner) -> tuple:
        return tuple(r.asks_seen)

    for policy in ({"bear": "UNBLOCKED"}, {"bear": "AS_BLOCKED"}, {}, {"bear": "UNBLOCKED", "elf": "AS_BLOCKED"}):
        combat = {"op": "combat", "seat": 0, "attack": {"bear": True, "elf": True},
                  "block": {"blk": "bear", "blk2": "elf"}, "policy": policy}
        pack = _pack(cards, [*minus7, combat])
        real = _game(pack, inspect=asks)
        assert sum(what.startswith("policy:") for what, _v in real[4]) == 2  # each blocked creature is asked
        assert _game(pack, mandatory, inspect=asks) == real, policy
    later = {"op": "combat", "seat": 0, "attack": {"bear": True, "elf": False}, "block": {"blk": "bear"},
             "policy": {"bear": "UNBLOCKED"}}
    pack = _pack(cards, [*minus7, {"op": "advance_turn"}, {"op": "advance_turn"}, later])
    permanent = _mutant(garruk, "1/2/effect/args/duration", DurationPermanent())
    assert (_game(pack)[1]["player:1"][0], _game(pack, permanent)[1]["player:1"][0]) == (20, 18)
    # the near shapes: a granted trigger's "may" is an ask of its own, and only the policy verb
    # is unwrapped by its reader
    grant = _at(garruk, "1/2/effect")
    end_step = _card("Barrin, Tolarian Archmage").abilities[1].event
    land_drop = _at(_card("Azusa, Lost but Seeking"), "1/0/effect").inner
    for ability in (TriggeredAbility(event=end_step, condition=None, effect=_at(garruk, GARRUK_MAY)),
                    StaticAbility(effect=OptionalEffect(inner=land_drop))):
        other = dataclasses.replace(grant, args=AtomArgs(pairs=tuple(
            (role, ability if role == "ability" else value) for role, value in grant.args.pairs)))
        assert not gates._granted_policy_may(other)
