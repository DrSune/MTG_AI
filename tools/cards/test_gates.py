"""Gates G0 and G3: the keyword-action and ability-word reading of G0, and the equivalent-mutant
rules of G3. Each G3 rule is proven twice: ``gates.mutants`` does not offer the mutant (while
its observable neighbours stay), and the engine plays the real tree and the would-be mutant to
the same game on a board built to expose the field if anything read it."""

from __future__ import annotations

import dataclasses
import json
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
from run_scenarios import ScenarioRunner, run_pack

from MTG_bot.core.ability_tree import (
    ActivatedAbility,
    AtomArgs,
    ControllerRef,
    Cost,
    DurationPermanent,
    EtBState,
    FAnd,
    FAtom,
    FAtomPred,
    Keyword,
    OptionalEffect,
    QAtMost,
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
    reveal_hand,
)
from MTG_bot.core.compiler.ingest import ingest_pool
from MTG_bot.core.executor.binding import _required_target_keys
from MTG_bot.core.executor.games import compile_supply

DATA = HERE.parents[1] / "MTG_bot" / "data"
SCENARIOS = HERE.parent / "scenarios"


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
    # an ability word (CR 207.2c), with no Keyword member since ontology round R12
    assert "BATTALION" not in Keyword.__members__ and "BATTALION" in gates.ABILITY_WORDS
    fails, warns = gates.g0(raw, bat, bat, clauses=None, known_signatures=None)
    assert not fails and not any("BATTALION" in w for w in warns)
    # a real keyword dropped from a tree still fails
    flier = _card("Shacklegeist")
    raw = _raw()[_oid("Shacklegeist")]
    fails, _w = gates.g0(raw, flier, dataclasses.replace(flier, keywords=()), clauses=None, known_signatures=None)
    assert fails == ["MTGJSON keywords missing from the tree: ['FLYING']"]


def test_the_clause_trace_takes_a_tree_path_or_the_label_its_sentence_takes() -> None:
    """MAPPER_GUIDE "Labelled sentences": each clause names an abilities[i] or keywords[i] the
    draft has, or the label its sentence takes, "deck rule" for a card's own deck-construction rule
    (FDN Hare Apparent, CR 100.2a) and "inert" for a sentence lints.INERT lists (M20 Vivien, Arkbow
    Ranger's -5), each label there only. A clause of reminder text alone needs no trace."""
    import corpus

    def card(code: str, name: str) -> tuple[Any, Any]:
        # the printed facts and the cast carrier alone, not the card's record: one ability
        raw = next(r for r in ingest_pool(DATA / f"{code}.json").values() if r.identity.name == name)
        return raw, corpus.printed_only(raw).card

    raw, hare = card("FDN", "Hare Apparent")
    etb, rule = raw.sentences
    assert gates.clause_trace_faults(raw, hare, [{"clause": etb, "ir": "abilities[0]"},
                                                 {"clause": rule, "ir": "deck rule (CR 100.2a)"},
                                                 {"clause": "(Reminder text.)", "ir": ""}]) == []
    for clause, ir in ((rule, "abilities[0]"),  # the deck rule has no tree
                       (etb, "deck rule"),      # the label on another sentence
                       (etb, "inert"),
                       (etb, "abilities[1]"),   # no such ability
                       (etb, "the trigger")):   # no path at all
        assert gates.clause_trace_faults(raw, hare, [{"clause": clause, "ir": ir}]), (clause, ir)
    fails, _w = gates.g0(raw, hare, hare, clauses=[{"clause": rule, "ir": "abilities[0]"}],
                         known_signatures=None)
    assert any("trace it as 'deck rule'" in f for f in fails)
    raw, vivien = card("M20", "Vivien, Arkbow Ranger")
    plus_one, _they, minus_three, minus_five = raw.sentences
    assert gates.clause_trace_faults(raw, vivien, [{"clause": minus_five, "ir": "inert"}]) == []
    assert gates.clause_trace_faults(raw, vivien, [{"clause": minus_five, "ir": "abilities[0]"}])
    assert gates.clause_trace_faults(raw, vivien, [{"clause": plus_one, "ir": "inert"}])
    assert gates.clause_trace_faults(raw, vivien, [{"clause": minus_three, "ir": "deck rule"}])


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


WHO_NONE = "controller who OPPONENT->none (your own zone)"


def test_an_opponents_graveyard_count_and_its_likely_misreading() -> None:
    # "an opponent has eight or more cards in their graveyard" (ontology round R12): the count of
    # "your" graveyard read for each opponent in turn. who YOU and an opponent's zone are refused (a
    # second "you", a count no player owns), so no flip reaches the likely mapping error, `who`
    # dropped ("you have eight ..."): G3 offers it as a critical mutant of its own (gate round 12,
    # MAJOR-3), and a board with eight cards in one graveyard only tells the two apart.
    tge = _card("Thieves' Guild Enforcer")
    offered = {(op, where) for op, where in _where(tge) if where.startswith("1/1/condition")}
    assert offered == {("amount+1", "1/1/condition/count"), ("amount-1", "1/1/condition/count"),
                       (WHO_NONE, "1/1/condition")}
    assert gates.is_critical(WHO_NONE)
    for where, new in (("1/1/condition/who", ControllerRef.YOU),
                       ("1/1/condition/quantity/selector/zones/0/controller", ControllerRef.OPPONENT)):
        with pytest.raises(ValueError, match="who"):
            _mutant(tge, where, new)
    yours = _mutant(tge, "1/1/condition", dataclasses.replace(_at(tge, "1/1/condition"), who=None))
    for full in (0, 1):  # eight cards in your graveyard only, then in the opponent's only
        gy = [{"key": f"g{i}", "name": f"Dead {i}", "type": "Sorcery", "zone": "graveyard", "controller": full}
              for i in range(8)]
        pack = _pack([{"key": "tge", "real": "Thieves' Guild Enforcer", "zone": "battlefield", "controller": 0},
                      *gy], [])
        real = _game(pack)
        enforcer = next(o for o in real[0].values() if o[0] == "Thieves' Guild Enforcer")
        assert enforcer[5] == ((3, 2) if full == 1 else (1, 1))
        assert _game(pack, yours) != real  # the misreading reads the other graveyard


def test_more_than_is_not_at_least_as_many() -> None:
    # Garruk, Unleashed's -2: "if an opponent controls more creatures than you" is the comparison
    # at <your creatures> + 1; G3 offers the bare measure ("at least as many"), critical, since
    # amount-1 cannot reach it (N + 0 is refused).
    garruk = _card("Garruk, Unleashed")
    found = [(op, where) for op, where in _where(garruk) if op == "amount: more than -> at least as many"]
    assert len(found) == 1 and gates.is_critical(found[0][0])
    node = _at(garruk, found[0][1])
    assert node.count.right == QConst(1)


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


PIE_FOOD = "1/0/effect/steps/1/args/tokens/"
FOOD_PACKS = ("bake_into_a_pie_destroys_and_bakes_a_food.json", "bake_into_a_pie_a_tapped_food_cannot_be_eaten.json")


def test_the_one_food_is_a_token_proven_by_two_packs(monkeypatch) -> None:
    """The one Food (lints.FOOD, the R_FOOD ruling) is a token G3 counts proven, so a Food maker
    keeps no survivor inside its Food spec: wave 3's FDN Eager Trufflesnout, Bake into a Pie and
    Cat Collector each kept "drop cost part 2 (CostTap)", which only a tapped Food shows and no
    pack could build until the tap op. The proof: every critical mutant of the spec, taken with
    the rule off, fails one of the two Bake into a Pie packs that pin the Food. A golden token
    record proves nothing here: FDN's own Food record compiles to no ability at all."""
    for maker in ("Eager Trufflesnout", "Bake into a Pie", "Cat Collector"):
        assert not [w for _op, w in _where(_card(maker, "FDN")) if "/abilities/" in w and "/tokens/" in w], maker
    pie = _card("Bake into a Pie", "FDN")
    monkeypatch.setattr(gates, "_verified_tokens", lambda: [])
    food = [(op, w, m) for op, w, m in gates.mutants(pie) if w.startswith(PIE_FOOD) and gates.is_critical(op)]
    assert ("drop cost part 2 (CostTap)", PIE_FOOD + "abilities/0/cost") in [(op, w) for op, w, _m in food]
    sup = _supply("FDN")
    packs = [HERE.parent / "scenarios" / "mapped" / "FDN" / name for name in FOOD_PACKS]
    assert not any(run_pack(p, sup) for p in packs)
    for op, where, mutant in food:
        with gates.swapped(sup, _oid("Bake into a Pie", "FDN"), mutant):
            assert any(run_pack(p, sup) for p in packs), (op, where)
    golden = next(r.card for r in sup.pool.results.values() if r.card.is_token and r.card.name == "Food")
    assert golden.abilities == ()


GUIDE_PICK = "1/0/effect/inner/steps/3/args/cards/count"


def test_one_of_count_after_a_one_card_search_is_dead() -> None:
    """FDN Campus Guide: "you may search your library for a basic land card, reveal it, then
    shuffle and put that card on top." The last step's ONE_OF picks among the cards the search
    found (ctx.search_found), one at most, so a count of 2 or 3 picks the same card; the search's
    own count stays live. Two basic lands in the library: the search's choice is the one that
    goes on top, whatever the ONE_OF's count."""
    guide = _card("Campus Guide", "FDN")
    assert ("amount+1", GUIDE_PICK) not in _where(guide)
    assert ("amount+1", GUIDE_PICK.replace("steps/3", "steps/0")) in _where(guide)  # the search's
    pack = _pack([{"key": "g", "real": "Campus Guide", "zone": "hand", "controller": 0},
                  {"key": "f", "real": "Forest", "zone": "library", "controller": 0},
                  {"key": "p", "real": "Plains", "zone": "library", "controller": 0}],
                 [{"op": "enter", "key": "g", "decisions": ["fire", "p"]}], code="FDN")
    real = _game(pack)
    seat0 = next(iter(real[1].values()))
    assert real[0][seat0[1][-1]][0] == "Plains"  # the found card is on top
    for n in (2, 3):
        assert _game(pack, _mutant(guide, GUIDE_PICK, QConst(n))) == real


BARRICADE_TARGET = "1/0/effect/args/target/count"


def test_one_of_over_your_player_zone_count_is_dead() -> None:
    """FDN Crystal Barricade's "You have hexproof" is a ONE_OF over your one player (gate round 12,
    from mapper M6): every count >= 1 picks you, so G3 offers no count change there, and the
    card's survivors (no pack) leave nothing critical."""
    barricade = _card("Crystal Barricade", "FDN")
    assert ("amount+1", BARRICADE_TARGET) not in _where(barricade)
    pack = _pack([{"key": "b", "real": "Crystal Barricade", "zone": "battlefield", "controller": 0},
                  {"key": "bolt", "real": "Burst Lightning", "zone": "hand", "controller": 1}],
                 [{"op": "end_turn"}, {"op": "advance_turn"},
                  {"op": "cast", "key": "bolt", "controller": 1, "decisions": ["player:0"],
                   "expect_raise": "target"}],
                 {"1": {"R": 1}}, code="FDN")
    real = _game(pack)
    for n in (2, 3):
        assert _game(pack, _mutant(barricade, BARRICADE_TARGET, QConst(n))) == real
    sup = _supply("FDN")
    report = gates.g3(sup, "FDN", _oid("Crystal Barricade", "FDN"))
    assert [s for s in report["survived"] if gates.is_critical(s[0])] == []


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


RADHA_LOOK = "1/1/effect/steps/0/args"
FORGE_LOOK = "1/0/effect/args"
FORGE_EXILE_COUNT = "1/2/effect/args/target/count"


def test_a_statics_own_look_is_dead() -> None:
    """"You may look at the top card of your library any time" (M21 Radha, Heart of Keld; M20
    Mystic Forge) is a disclosure record nothing reads (layers' static lane runs no look): its
    controller and count are dead, while its permission beside it stays live."""
    radha = _card("Radha, Heart of Keld")
    forge = _card("Mystic Forge", "M20")
    assert not {w for _op, w in _where(radha) if w.startswith(RADHA_LOOK)}
    assert not {w for _op, w in _where(forge) if w.startswith(FORGE_LOOK)}
    assert ("amount+1", "1/1/effect/args/source/filter/children/1/inner/count") in _where(forge)
    pack = _pack([{"key": "radha", "real": "Radha, Heart of Keld", "zone": "battlefield", "controller": 0},
                  {"key": "mtn", "real": "Mountain", "zone": "library", "controller": 0},
                  *_library(1, "Theirs", 3)],
                 [{"op": "play", "key": "mtn"}])
    real = _game(pack)
    assert next(o for o in real[0].values() if o[0] == "Mountain")[1] == "battlefield"
    assert _game(pack, _mutant(radha, f"{RADHA_LOOK}/controller", ControllerRef.OPPONENT)) == real
    assert _game(pack, _mutant(radha, f"{RADHA_LOOK}/count", QConst(2))) == real


def test_a_pick_from_the_one_top_card_has_a_dead_count() -> None:
    """Mystic Forge's "Exile the top card of your library" picks from a zone holding one card, so
    every count of 1 or more exiles that card; a pick from a look window keeps its count (See
    the Truth's "Put one of those cards into your hand")."""
    forge = _card("Mystic Forge", "M20")
    assert ("amount+1", FORGE_EXILE_COUNT) not in _where(forge)
    truth = _card("See the Truth")
    assert any(op == "amount+1" and w.endswith("cards/count") for op, w in _where(truth))
    every_top = _mutant(forge, "1/2/effect/args/target/zones/0/controller", ControllerRef.ANY)
    assert ("amount+1", FORGE_EXILE_COUNT) in _where(every_top)  # each player's top card: two
    pack = _pack([{"key": "forge", "real": "Mystic Forge", "zone": "battlefield", "controller": 0},
                  *_library(0, "Yours", 3), *_library(1, "Theirs", 3)],
                 [{"op": "activate", "key": "forge", "idx": 2, "seat": 0}], code="M20")
    real = _game(pack)
    assert [o[1] for o in real[0].values() if o[0].startswith("Yours")].count("exile") == 1
    assert _game(pack, _mutant(forge, FORGE_EXILE_COUNT, QConst(2))) == real


def test_every_proven_equivalent_mutant_holds_for_the_tree_it_was_proven_on() -> None:
    """A survivor a proof shows to play exactly like the card (tools/cards/equivalent_mutants.json:
    M21 Mangara, the Diplomat's widened attack event, which its intervening "if" cuts back) is
    honoured by G3 only for the tree it was proven on: each entry names a mutant G3 still makes
    from the card's tree, with its reason and a proof that still holds on this engine (it is
    run: the equivalence can rest on how the engine plays, Mangara's on the intervening "if"
    read again), and a changed tree drops it."""
    import json
    import subprocess

    import cardtool

    from MTG_bot.core.compiler import card_records

    entries = json.loads(cardtool.EQUIVALENT.read_text())
    assert entries
    for oid, entry in entries.items():
        card = _supply(entry["set"]).pool.results[oid].card
        assert card_records.tree_sha(card) == entry["tree_sha"], f"{entry['name']}: prove it again"
        made = {f"{op} at {where}": mutant for op, where, mutant in gates.mutants(card)}
        for m in entry["mutants"]:
            assert m["mutant"] in made and m["reason"], m["mutant"]
            proof = HERE.parents[1] / m["proof"].split(":")[0]
            done = subprocess.run([sys.executable, str(proof)], cwd=HERE.parents[1], capture_output=True,
                                  text=True, timeout=600)
            assert done.returncode == 0, done.stdout[-2000:] + done.stderr[-2000:]
        assert cardtool.equivalent_mutants(oid, card) == {m["mutant"] for m in entry["mutants"]}
        changed = made[entry["mutants"][0]["mutant"]]
        assert cardtool.equivalent_mutants(oid, changed) == set()


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
                 # all three stay on top, in the order asked top first (verbs._arrange): the Spell
                 # (card:3) on top, then Beast One (card:2)
                 [{"op": "cast", "key": "td", "decisions": ["top", "top", "top", "card:3", "card:2"]}],
                 {"0": {"G": 2}})
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
    # the same twin designation on an activated ability is dead too, now that activate() refuses
    # an empty designation (test_target_to_all_on_twins_in_an_activation_is_dead)
    twins = {(1, 0, "effect", "steps", i, "args", "target") for i in (0, 1)}
    ability = ActivatedAbility(cost=Cost(parts=()), effect=strike.abilities[0].effect)
    assert gates._twin_targets(ability, (1, 0)) == twins == gates._twin_targets(strike.abilities[0], (1, 0))


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


def test_an_all_over_a_library_top_is_a_partition_not_the_draw_idiom() -> None:
    """See the Truth, cast from anywhere other than your hand: "put all cards looked at this way
    into your hand" is an ALL over the library's top, which the executor moves as a partition
    (verbs.py ``partition``: the looked-at cards as resolved, each into its owner's hand); only the
    draw idiom reads the destination's player. So the destination-controller mutant is dead, and
    both trees play the same game: the three cards reach the caster's hand whichever player the
    destination names (verification wave 6's lone survivor, BACKLOG G1)."""
    stt = _card("See the Truth")
    move = "1/0/effect/steps/1/then_effect"
    assert not gates._draw_idiom(_at(stt, move))
    assert ("controller YOU->OPPONENT", f"{move}/args/destination/controller") not in _where(stt)
    pack = _pack([{"key": "stt", "real": "See the Truth", "zone": "graveyard", "controller": 0},
                  *_library(0, "Yours", 3), *_library(1, "Theirs", 3)],
                 [{"op": "test_permission_cast", "key": "stt", "from": "graveyard"}], {"0": {"U": 1, "C": 1}})
    real = _game(pack)
    assert sorted(o[0] for o in real[0].values() if o[1] == "hand") == ["Yours 0", "Yours 1", "Yours 2"]
    dest = _at(stt, f"{move}/args/destination")
    theirs = _mutant(stt, f"{move}/args/destination", dataclasses.replace(dest, controller=ControllerRef.OPPONENT))
    assert _game(pack, theirs) == real


AUGUR_DISCARD = "1/1/effect/steps/0/args/cards/zones/0/controller"


def test_discard_selector_zones_are_dead_outside_a_may() -> None:
    """A CHOOSE/RANDOM/ALL discard takes its picks from the discarding player's own hand
    (verbs.py _hand_picks reads filter, mode and count): Kinetic Augur's discard plays the same
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


HARBINGER_REVEAL = "1/0/effect/steps/1/inner/steps/1/args"
#: Another hand to reveal in place of the cards found: one player's, as the IR requires (a hand of
#: no one player, OPPONENT's, is refused since gate round W3's review).
YOUR_HAND = reveal_hand(ControllerRef.YOU).args.get("cards")


def test_a_reveal_of_the_card_picked_is_dead() -> None:
    """Garruk's Harbinger: "look at that many cards ... You may reveal a creature card ... from
    among them and put it into your hand. Put the rest on the bottom." The reveal follows the
    pick's move and shows its ``result`` (DESIGN_ATOM_ONTOLOGY §19): it opens no window and writes
    ``result`` again with the same cards, which no Conditional here reads, so nothing that plays
    reads it, and its ``cards`` offers no mutant; revealing your hand instead plays the same
    game."""
    harb = _card("Garruk's Harbinger")
    offered = _where(harb)
    assert not {w for _op, w in offered if w.startswith(HARBINGER_REVEAL)}
    assert ("amount+1", "1/0/effect/steps/1/inner/steps/0/args/cards/count") in offered  # the pick stays live
    pack = _pack([{"key": "gh", "real": "Garruk's Harbinger", "zone": "battlefield", "controller": 0},
                  {"key": "beast", "name": "Beast", "type": "Creature", "power": "3", "toughness": "3",
                   "zone": "library", "controller": 0},
                  {"key": "spell", "name": "Spell", "type": "Instant", "zone": "library", "controller": 0},
                  {"key": "opener", "name": "Opener", "type": "Sorcery", "zone": "hand", "controller": 0},
                  *_library(1, "Theirs", 2)],
                 [{"op": "combat", "seat": 0, "attack": {"gh": True}, "may": {"gh": True}, "decisions": ["beast"]}])
    real = _game(pack)
    assert next(o for o in real[0].values() if o[0] == "Beast")[1] == "hand"  # the pick from the window
    assert real[1]["player:1"][0] == 16  # 4 combat damage
    assert _game(pack, _mutant(harb, f"{HARBINGER_REVEAL}/cards", YOUR_HAND)) == real


# ---------------------------------------------- the "library and/or graveyard" zone choice
WARSTEED_OPTION = "1/0/effect/inner/options/{}/steps/{}/args"


def test_a_reveal_of_the_card_found_is_dead() -> None:
    """"Search your library and/or graveyard ... reveal it": each of the three searches is followed
    by the reveal of its ``result`` (DESIGN_ATOM_ONTOLOGY §19), which no game state reads: no
    mutant of its ``cards``, and every option plays the same game when it reveals your hand
    instead. Each search stays live. No top-of-library reveal is left in the ability."""
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
        assert _game(pack, _mutant(ws, f"{reveal}/cards", YOUR_HAND)) == real, option
    assert gates._reveal_dead_roles(ws.abilities[0]) == set()


YAROK_EVENT = "1/0/effect/args/event"


def test_an_extra_triggers_cause_is_mutated_and_the_cast_pack_kills_its_drop() -> None:
    """The gate's MINOR-6: Yarok with his cause dropped doubles every trigger of his
    controller's permanents (stronger than printed) and passed both entering packs, for G3 had
    no operator on the cause. Now it drops the cause (and widens a cause's subject, Naban's
    Wizard), and the cast pack, a Kykar trigger no entering caused, kills the drop."""
    yarok = _card("Yarok, the Desecrated", "M20")
    assert ("extra-trigger cause dropped", YAROK_EVENT) in _where(yarok)
    event = _at(yarok, YAROK_EVENT)
    dropped = _mutant(yarok, YAROK_EVENT, dataclasses.replace(event, cause=None))
    pack = json.loads((SCENARIOS / "mapped/M20/yarok_leaves_a_cast_trigger_single.json").read_text())
    real = _game(pack)
    assert sum(o[0] == "Spirit" for o in real[0].values()) == 1
    assert _game(pack, dropped) != real
    naban = _card("Naban, Dean of Iteration", "DOM")
    assert ("extra-trigger cause widened", YAROK_EVENT) in _where(naban)


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


SEE_THE_TRUTH_REST = "1/0/effect/steps/1/else_effect/steps/1"  # the split, the else of its "instead"


def test_library_order_mutants_only_where_several_cards_go_to_a_library() -> None:
    """MOVE_ZONE arrange (CR 401.4), both directions critical: dropping RANDOM would let Garruk's
    Harbinger's controller choose the order of the rest, and adding it would take See the Truth's
    choice away. Offered where ability_tree.orders_a_library says a move can hold an order, the
    validator's own predicate, so an anaphor's move ("put them on the bottom") gets one too:
    the executor orders whatever it binds. Never on a move of one card (Teferi, Timeless
    Voyager's -3), nor on Garruk, Savage Herald's +1, whose "it" is a one-card look's result
    (gates._one_card_result_moves): no order there, so that mutant would be equivalent."""
    assert "library order: random -> the owner's" in {op for op, _w in _where(_card("Garruk's Harbinger"))}
    truth = _card("See the Truth")
    assert ("library order: the owner's -> random", SEE_THE_TRUTH_REST) in _where(truth)
    assert gates.is_critical("library order: random -> the owner's")
    assert gates.is_critical("library order: the owner's -> random")
    for name in ("Teferi, Timeless Voyager", "Garruk, Savage Herald"):
        assert not {op for op, _w in _where(_card(name)) if op.startswith("library order")}, name
    them = Selector(QConst(1), SelectorMode.CHOOSE, FAnd(children=()),
                    zones=(Zone(ZoneKind.ANY, ControllerRef.ANY),), referent="result")
    anaphor = _mutant(truth, f"{SEE_THE_TRUTH_REST}/args/cards", them)
    assert ("library order: the owner's -> random", SEE_THE_TRUTH_REST) in _where(anaphor)


def test_a_random_order_keeps_its_zone_mutant() -> None:
    """"zone LIBRARY->GRAVEYARD" stays critical on a move "in a random order": the swap drops
    arrange with the library (the validator refuses arrange off a library), so the mutant is not
    stillborn. Garruk's Harbinger, Drawn from Dreams and Brightwood Tracker kept it before the
    role existed."""
    assert ("zone LIBRARY->GRAVEYARD", "1/0/effect/steps/2/args/destination") in _where(_card("Garruk's Harbinger"))


def test_a_widened_chosen_quality_read_drops_its_choice() -> None:
    """"Creatures you control of the chosen color get +1/+0" widened to every creature you
    control is a card that chooses nothing: the IR refuses a choice nothing reads
    (DESIGN_ATOM_ONTOLOGY §13), so the mutant drops the "As this enters" choice with its last read
    (gates._without_unread_choices), as the zone swap drops arrange; else it would be stillborn
    and the fault untested. A choice another read still needs stays (Icon of Ancestry's look reads
    the type its anthem no longer does). Red on 92aca048: FDN Heraldic Banner had no such mutant."""
    where = "1/1/effect/args/target/filter"
    for name, code, reads_left in (("Heraldic Banner", "FDN", 0), ("Icon of Ancestry", "M20", 1)):
        card = _card(name, code)
        part = next(i for i, c in enumerate(_at(card, where).children)
                    if isinstance(c, FAtom) and c.pred is FAtomPred.NAME_CHOSEN)
        mutant = {(op, w): m for op, w, m in gates.mutants(card)}[
            (f"widen filter (drop part {part})", where)]
        reads = [n for _p, n in gates._paths((mutant.keywords, mutant.abilities))
                 if isinstance(n, FAtom) and n.pred is FAtomPred.NAME_CHOSEN]
        assert len(reads) == reads_left, name
        assert any(isinstance(a, EtBState) for a in mutant.abilities) is bool(reads_left), name


def test_a_card_that_enters_tapped_or_with_counters_has_mutants() -> None:
    """An "As this enters" node that only taps or puts counters (no effect) stays in every mutant:
    ``_without_unread_choices`` compared it with ``EtBState(effect=None)``, which the IR refuses
    (a no-op state), so every mutant of such a card was stillborn and G3 had nothing to test (found
    by ontology round R11 on M20 Barkhide Troll: 0 mutants; red on 1d5e4164). M21 Malefic
    Scythe's soul counter and a tapped land keep their EtBState and get their amount mutants."""
    for name, code in (("Barkhide Troll", "M20"), ("Malefic Scythe", "M21"), ("Temple of Malady", "M21")):
        card = _card(name, code)
        found = list(gates.mutants(card))
        assert found, name
        assert all(any(isinstance(a, EtBState) for a in m.abilities) for _op, _w, m in found), name
    troll = {op for op, _w, _m in gates.mutants(_card("Barkhide Troll", "M20"))}
    assert {"amount+1", "drop cost part 1 (CostRemoveCounter)", "until-end-of-turn->permanent"} <= troll


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


def test_a_zone_change_trigger_gets_the_once_per_event_mutant_where_it_lives() -> None:
    """Ontology round R10: a zone change of several objects is one event (CR 603.2c), so a
    per-object "whenever a creature you control enters" trigger gets the critical "each
    occurrence -> once per event" mutant (Garruk's Uprising), and the gathered one (Woodland
    Champion) its reverse. Where the effect reads one object of the event (Terror of the Peaks'
    "that creature's power") the IR refuses the flag: the mutant is stillborn, never a crash."""
    assert ("each occurrence -> once per event", "1/2") in _where(_card("Garruk's Uprising"))
    assert ("trigger count: once per event -> each occurrence", "1/0") in _where(
        _card("Woodland Champion", "M20"))
    assert not {op for op, _w in _where(_card("Terror of the Peaks")) if "occurrence" in op}


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


SORIN = "1/0/effect/steps/{}/args/target"


def test_target_to_all_on_twins_in_an_activation_is_dead() -> None:
    """Sorin, Imperious Bloodlord's first +1 (M20): "Target creature you control gains deathtouch
    and lifelink until end of turn. If it's a Vampire, put a +1/+1 counter on it." Both grants
    carry the same TARGET selector: activate() designates the one slot of
    query.activation_target_slots, refuses an empty designation before paying
    (legality.activation_target_reason, CR 602.2b, 601.2c), and resolve_activated re-checks the
    slot and binds it, so the ALL grant acts on the designation (role_handles). Two creatures of
    the same kind you control, one targeted; the target gone in response; the act menu; no
    designation; no creature you control. The near shape, Celestial Enforcer's lone TARGET
    (M21), loses its slot in the mutant, which is activated with no target and taps every
    creature."""
    sorin = _card("Sorin, Imperious Bloodlord", "M20")
    offered = _where(sorin)
    assert not {w for op, w in offered if op == "target->all" and w.startswith("1/0/")}
    assert ("amount+1", SORIN.format(0) + "/count") in offered  # the designation's count stays live
    assert ("target->all", "1/1/effect/steps/1/then_effect/effect/steps/0/args/target") in offered  # the reflexive's
    mutants = [_everyone(sorin, SORIN.format(step)) for step in (0, 1)]
    bear = {"type": "Creature — Bear", "power": "2", "toughness": "2", "zone": "battlefield"}
    vampire = {"type": "Creature — Vampire", "power": "2", "toughness": "2", "zone": "battlefield"}
    base = [{"key": "s", "real": "Sorin, Imperious Bloodlord", "zone": "battlefield", "controller": 0}]
    bears = [*base, {**bear, "key": "ba", "name": "BA", "controller": 0}, {**bear, "key": "bb", "name": "BB", "controller": 0}]
    activate = {"op": "activate", "key": "s", "idx": 0, "seat": 0}
    packs = {
        "a bear": _pack([*bears, {**vampire, "key": "ov", "name": "Opp Vamp", "controller": 1}],
                        [{**activate, "targets": ["ba"]}], code="M20"),
        "a vampire": _pack([*base, {**vampire, "key": "va", "name": "VA", "controller": 0},
                            {**vampire, "key": "vb", "name": "VB", "controller": 0}],
                           [{**activate, "targets": ["va"]}], code="M20"),
        "the target gone in response": _pack(bears, [{**activate, "targets": ["ba"], "hold": True},
                                                     {"op": "move", "key": "ba", "to": "hand"}], code="M20"),
        "the act menu": _pack(bears, [{"op": "act", "seat": 0, "words": ["act:s:0", "ba"]}], code="M20"),
        "no designation": _pack(bears, [activate], code="M20"),
        "no creature you control": _pack([*base, {**bear, "key": "ob", "name": "Opp Bear", "controller": 1}],
                                         [activate], code="M20"),
    }

    def layers(r: ScenarioRunner) -> tuple:  # what a refusal mid-resolution would leave behind
        return tuple(r.ex.events), tuple((rec.kind, rec.targets) for rec in r.ex.layers.records)

    for label, pack in packs.items():
        real = _game(pack, inspect=layers)
        for step, mutant in enumerate(mutants):
            assert _game(pack, mutant, inspect=layers) == real, (label, step)
    keywords = {o[0]: o[6] for o in _game(packs["a bear"])[0].values() if o[0] in ("BA", "BB")}
    assert keywords == {"BA": ("DEATHTOUCH", "LIFELINK"), "BB": ()} or keywords == {"BA": ("LIFELINK", "DEATHTOUCH"), "BB": ()}
    for label in ("no designation", "no creature you control"):
        refused = _game(packs[label])[3]
        assert refused is not None and "count_below_min" in refused, label  # before the +1 is paid
    enforcer = _card("Celestial Enforcer")
    assert gates._twin_targets(enforcer.abilities[0], (1, 0)) == set()
    assert ("target->all", "1/0/effect/args/target") in _where(enforcer)
    creature = {"type": "Creature", "power": "2", "toughness": "2", "zone": "battlefield"}
    pack = _pack([{"key": "ce", "real": "Celestial Enforcer", "zone": "battlefield", "controller": 0},
                  {**creature, "key": "bird", "name": "My Bird", "keywords": ["FLYING"], "controller": 0},
                  {**creature, "key": "ox", "name": "Opp Ox", "controller": 1}],
                 [{"op": "activate", "key": "ce", "idx": 0, "seat": 0}], {"0": {"W": 1, "C": 1}})

    def tapped(game: tuple) -> dict:
        return {o[0]: o[3] for o in game[0].values() if o[0] in ("My Bird", "Opp Ox")}

    real = _game(pack)
    assert real[3] is not None and tapped(real) == {"My Bird": False, "Opp Ox": False}
    got = _game(pack, _everyone(enforcer, "1/0/effect/args/target"))
    assert got[3] is None and tapped(got) == {"My Bird": True, "Opp Ox": True}


def test_target_to_all_on_up_to_one_twins_in_an_activation_is_dead() -> None:
    """Garruk, Unleashed's +1 (M21, "Up to one target creature gets +3/+3 and gains trample until
    end of turn") and Mu Yanling, Sky Dancer's +2 (M20, "Until your next turn, up to one target
    creature gets -2/-0 and loses flying"): twins with an "up to one" count. A designation that
    chose nothing is bound as the empty designation (resolve_activated, query.designates: the
    remaining twin keeps the slot), so the ALL twin acts on nothing; a target gone before the
    ability resolves stops it whole (CR 608.2b). One target among three creatures, none chosen,
    the target gone in response, no creature at all, the act menu with a target and without.
    The near shape, the same grant with its lone "up to" TARGET, has no slot left in the mutant:
    nothing is bound, and with no target chosen it reaches every creature."""
    def layers(r: ScenarioRunner) -> tuple:
        return tuple(r.ex.events), tuple((rec.kind, rec.targets) for rec in r.ex.layers.records)

    for code, name, key, kws in (("M21", "Garruk, Unleashed", "ga", []), ("M20", "Mu Yanling, Sky Dancer", "mu", ["FLYING"])):
        card = _card(name, code)
        offered = _where(card)
        assert not {w for op, w in offered if op == "target->all" and w.startswith("1/0/")}, name
        assert _at(card, SORIN.format(0)).count == QAtMost(n=1)
        mutants = [_everyone(card, SORIN.format(step)) for step in (0, 1)]
        creature = {"type": "Creature", "power": "2", "toughness": "2", "zone": "battlefield", "keywords": kws}
        pw = {"key": key, "real": name, "zone": "battlefield", "controller": 0}
        board = [pw, {**creature, "key": "a", "name": "A", "controller": 0}, {**creature, "key": "b", "name": "B", "controller": 0},
                 {**creature, "key": "o", "name": "O", "controller": 1}]
        activate = {"op": "activate", "key": key, "idx": 0, "seat": 0}
        packs = [_pack(board, [{**activate, "targets": ["a"]}], code=code),
                 _pack(board, [{**activate, "targets": []}], code=code),
                 _pack(board, [{**activate, "targets": ["a"], "hold": True}, {"op": "move", "key": "a", "to": "hand"}], code=code),
                 _pack([pw], [activate], code=code),
                 _pack(board, [{"op": "act", "seat": 0, "words": [f"act:{key}:0", "a"]}], code=code),
                 _pack(board, [{"op": "act", "seat": 0, "words": [f"act:{key}:0", "DONE"]}], code=code)]
        for i, pack in enumerate(packs):
            real = _game(pack, inspect=layers)
            assert real[3] is None, (name, i)
            for step, mutant in enumerate(mutants):
                assert _game(pack, mutant, inspect=layers) == real, (name, i, step)
        untouched = {o[0]: o[5] for o in _game(packs[1])[0].values() if o[0] in ("A", "B", "O")}
        assert untouched == {"A": (2, 2), "B": (2, 2), "O": (2, 2)}, name
        lone = dataclasses.replace(card, abilities=(
            dataclasses.replace(card.abilities[0], effect=card.abilities[0].effect.steps[0]), *card.abilities[1:]))
        assert gates._twin_targets(lone.abilities[0], (1, 0)) == set()
        reached = {o[0]: o[5] for o in _game(packs[1], _everyone(lone, "1/0/effect/args/target"))[0].values()
                   if o[0] in ("A", "B", "O")}
        assert reached != untouched and len(set(reached.values())) == 1, name  # every creature, alike
    # the same "up to one" twins in a trigger or a spell keep their mutants: no card has them
    effect = _card("Garruk, Unleashed").abilities[0].effect
    end_step = _card("Barrin, Tolarian Archmage").abilities[1].event
    assert gates._twin_targets(TriggeredAbility(event=end_step, condition=None, effect=effect), (1, 0)) == set()
    assert gates._twin_targets(dataclasses.replace(_card("Sure Strike").abilities[0], effect=effect), (1, 0)) == set()


KRAKEN = "1/0/effect/steps/1/then_effect/effect/inner/options/{}/args/target"


def test_target_to_all_on_twins_in_a_reflexive_trigger_choice_stays_live() -> None:
    """The near shape: Tolarian Kraken's "When you do, you may tap or untap target creature" is a
    reflexive trigger (CR 603.12) whose Choose holds the twins, so its slot is required (every
    option carries it) and each mutant's is not (binding._required_target_keys). The draw trigger
    designates nothing. With no legal target (the Kraken alone, with protection from blue from
    Feat of Resistance) the {1} is paid, and then the card's reflexive trigger is removed as it
    goes on the stack (CR 603.3d) while each mutant's waits there."""
    kraken = _card("Tolarian Kraken")
    assert gates._twin_targets(kraken.abilities[0], (1, 0)) == set()
    reflexive = _at(kraken, "1/0/effect/steps/1/then_effect")
    assert reflexive.reflexive
    assert not _required_target_keys(kraken.abilities[0].effect)  # the draw trigger's own: none
    sel = _at(kraken, KRAKEN.format(0))
    assert repr(sel) in _required_target_keys(reflexive.effect)
    for option in (0, 1):
        assert ("target->all", KRAKEN.format(option)) in _where(kraken)
        mutant = _everyone(kraken, KRAKEN.format(option))
        assert repr(sel) not in _required_target_keys(_at(mutant, "1/0/effect/steps/1/then_effect").effect)
    pack = _pack([{"key": "k", "real": "Tolarian Kraken", "zone": "battlefield", "controller": 0},
                  {"key": "feat", "real": "Feat of Resistance", "zone": "hand", "controller": 0},
                  {"key": "ct", "real": "Crash Through", "zone": "hand", "controller": 0}],
                 [{"op": "cast", "key": "feat", "targets": ["k"], "decisions": ["1"]},
                  {"op": "cast", "key": "ct", "hold": True}, {"op": "resolve"},
                  {"op": "mana", "seat": 0, "add": {"C": 1}, "hold": True},
                  {"op": "resolve", "hold": True, "decisions": ["fire"]}],
                 {"0": {"W": 1, "R": 1, "C": 1}})

    def stack(r: ScenarioRunner) -> tuple:
        return tuple(frame.spell_kind for frame in r.ex.stack.frames)

    real = _game(pack, inspect=stack)
    assert real[4] == () and not real[1]["player:0"][2]  # the {1} was paid; nothing waits
    for option in (0, 1):
        assert _game(pack, _everyone(kraken, KRAKEN.format(option)), inspect=stack)[4] == ("TRIGGERED",)


def test_a_reflexive_trigger_written_inline_is_a_critical_mutant_a_pack_kills() -> None:
    """G3's operator for "When you do" written as "If you do" (Sorin, Imperious Bloodlord's
    first mapping): the reflexive trigger's effect inline, its targets chosen with the
    ability's own. Critical; on the Kraken, the no-legal-target game tells it from the card:
    the card offers the {1}, the mutant's draw trigger is removed before it can."""
    kraken = _card("Tolarian Kraken")
    where = "1/0/effect/steps/1/then_effect"
    op = "trigger timing: when you do -> if you do"
    assert (op, where) in _where(kraken) and gates.is_critical(op)
    mutant = _mutant(kraken, where, _at(kraken, where).effect)
    pack = _pack([{"key": "k", "real": "Tolarian Kraken", "zone": "battlefield", "controller": 0},
                  {"key": "feat", "real": "Feat of Resistance", "zone": "hand", "controller": 0},
                  {"key": "ct", "real": "Crash Through", "zone": "hand", "controller": 0}],
                 [{"op": "cast", "key": "feat", "targets": ["k"], "decisions": ["1"]},
                  {"op": "cast", "key": "ct", "hold": True}, {"op": "resolve"},
                  {"op": "mana", "seat": 0, "add": {"C": 1}, "hold": True},
                  {"op": "pass", "decisions": ["fire"]}],
                 {"0": {"W": 1, "R": 1, "C": 1}})
    real, inline = _game(pack), _game(pack, mutant)
    assert real[1]["player:0"][2] == () and inline[1]["player:0"][2] == (("C", 1),)  # paid / never offered


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
