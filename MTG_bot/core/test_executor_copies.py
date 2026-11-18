"""Copies in the engine (DESIGN_ATOM_ONTOLOGY §18, CR 707; executor/copies.py): token copies,
permanents that become copies (layer 1), copies of spells and abilities put onto the stack, and
what the network reads of a copy.

CR 707.2: a copy takes the copiable values (what is printed, as modified by other copy effects),
never counters, status or other effects; 707.3: a copy of a copy copies the copy; 707.9: the
exceptions become copiable values; 707.10: a copy of a spell or ability is put onto the stack, not
cast, with the original's choices, its copier's, and 707.10c: new targets may be chosen.

Every test fails on the round's base (70e63ee7): there ``CopyOf`` does not exist, COPY has no
handler, and the cards' records were needs-atom.
"""

from __future__ import annotations

import dataclasses
from functools import cache

import numpy as np
import pytest

from MTG_bot.core.executor.events import KIND_CAST
from MTG_bot.core.executor.games import compile_supply
from MTG_bot.core.executor.legality import spell_record
from MTG_bot.core.state import ZONE_BATTLEFIELD
from tools.run_scenarios import ScenarioRunner


@cache
def _supply(code: str):
    return compile_supply("all", code, require_verified=False)


def _runner(code: str, cards: list[dict], mana: dict | None = None) -> ScenarioRunner:
    pack = {"set": code, "world": {"life": 20, "seed": 7, "library_top": True}, "cards": cards,
            "steps": []}
    if mana:
        pack["mana"] = mana
    return ScenarioRunner(pack, _supply(code))


def _real(key, name, seat=0, zone="battlefield", **more) -> dict:
    return {"key": key, "real": name, "zone": zone, "controller": seat, **more}


def _synthetic(key, name, type_line, power, toughness, seat=0, **more) -> dict:
    return {"key": key, "name": name, "type": type_line, "power": power, "toughness": toughness,
            "zone": "battlefield", "controller": seat, **more}


def _tokens(r: ScenarioRunner, name: str) -> list:
    return [h for h in r.world.players[r.p0].zone(ZONE_BATTLEFIELD).entries
            if r.world.cards[h].identity.is_token and r.world.cards[h].identity.name == name]


# ------------------------------------------------------------------------------ token copies


def test_a_token_copy_takes_copiable_values_only() -> None:
    """Self-Reflection on a tapped Healer's Hawk with two +1/+1 counters and a pump: the token is
    a Healer's Hawk, its own oracle id and abilities, untapped, with no counter and no pump (CR
    707.2), a token (CR 707.5)."""
    r = _runner("FDN", [
        _real("sr", "Self-Reflection", zone="hand"),
        _real("hawk", "Healer's Hawk", start_tapped=True, counters={"PLUS_1_PLUS_1": 2}),
    ], mana={"0": {"U": 2, "C": 4}})
    hawk = r.handles["hawk"]
    r.run_step({"op": "cast", "key": "sr", "real": "Self-Reflection", "targets": ["hawk"]})
    [token] = _tokens(r, "Healer's Hawk")
    state, original = r.world.cards[token], r.world.cards[hawk]
    assert state.identity.oracle_id == original.identity.oracle_id
    assert state.identity.is_token and not original.identity.is_token
    assert not state.tapped and not state.counters
    assert r.ex.ledger.effective_pt(state.identity, token, state.counters) == (1, 1)
    assert spell_record(r.ex, token).abilities == spell_record(r.ex, hawk).abilities
    assert r.ex.layers.keyword_of(token, "FLYING") and r.ex.layers.keyword_of(token, "LIFELINK")


def test_a_copy_of_a_copy_keeps_its_exceptions() -> None:
    """Electroduplicate's token copy of a Hawk has haste and the end-step sacrifice (CR 707.9a);
    Self-Reflection copying that token copies them too (CR 707.3, 707.9a: they are its copiable
    values), and the copy of the copy is sacrificed at the end step."""
    r = _runner("FDN", [
        _real("ed", "Electroduplicate", zone="hand"),
        _real("sr", "Self-Reflection", zone="hand"),
        _real("hawk", "Healer's Hawk"),
    ], mana={"0": {"R": 1, "U": 2, "C": 6}})
    r.run_step({"op": "cast", "key": "ed", "real": "Electroduplicate", "targets": ["hawk"]})
    [first] = _tokens(r, "Healer's Hawk")
    r.handles["first"] = first
    r.run_step({"op": "cast", "key": "sr", "real": "Self-Reflection", "targets": ["first"]})
    second = next(h for h in _tokens(r, "Healer's Hawk") if h != first)
    assert r.ex.layers.keyword_of(second, "HASTE")
    assert spell_record(r.ex, second).abilities == spell_record(r.ex, first).abilities
    assert len(spell_record(r.ex, second).abilities) == len(spell_record(r.ex, r.handles["hawk"]).abilities) + 1
    r.run_step({"op": "combat", "seat": 0, "attack": {}})
    # two sacrifice triggers at the end step: their controller orders them (CR 603.3b)
    r.run_step({"op": "to_step", "step": "END_TURN", "decisions": ["first-legal"]})
    r.run_step({"op": "pass"})
    assert _tokens(r, "Healer's Hawk") == []
    assert r.world.zone_of(r.handles["hawk"]).kind == ZONE_BATTLEFIELD


def test_a_nightmare_token_copy_is_a_nightmare_and_exiles_the_other_ones() -> None:
    """Abyssal Harvester: the token copy of the exiled card is a Nightmare in addition to its
    types (CR 707.9b), and the other Nightmare tokens its controller controls are exiled."""
    r = _runner("FDN", [
        _real("ah", "Abyssal Harvester"),
        _real("hawk", "Healer's Hawk", seat=1),
        _synthetic("old", "Old Nightmare", "Creature — Nightmare", "1", "1", token=True),
    ])
    r.run_step({"op": "move", "key": "hawk", "to": "graveyard"})
    r.run_step({"op": "activate", "key": "ah", "idx": 0, "seat": 0, "targets": ["hawk"]})
    [token] = _tokens(r, "Healer's Hawk")
    assert "Nightmare" in r.world.cards[token].identity.type_line.split()
    assert r.handles["old"] not in r.world.cards  # exiled, so it ceased to exist (CR 704.5d)
    assert r.world.zone_of(r.handles["hawk"]).kind == "exile"


# ------------------------------------------------------------------------- layer 1 (613.2a)


def _replication(beta: dict) -> ScenarioRunner:
    return _runner("M20", [
        _real("mr", "Masterful Replication", zone="hand"),
        _synthetic("alpha", "Alpha Golem", "Artifact Creature — Golem", "4", "4"),
        beta,
    ], mana={"0": {"U": 6}})


def test_becoming_a_copy_until_end_of_turn_swaps_the_values_and_gives_them_back() -> None:
    """Masterful Replication: Steel Overseer becomes a copy of the Golem: its name, P/T and
    abilities are the Golem's (no "{T}: Put a +1/+1 counter ..."), its counter stays (CR 707.2);
    at the cleanup step it is itself again with its ability (CR 613.2a, 514.2)."""
    r = _replication(_real("beta", "Steel Overseer", counters={"PLUS_1_PLUS_1": 1}))
    beta = r.handles["beta"]
    own = spell_record(r.ex, beta)
    r.run_step({"op": "cast", "key": "mr", "real": "Masterful Replication", "targets": ["alpha"],
                "decisions": ["1"]})
    state = r.world.cards[beta]
    assert state.identity.name == "Alpha Golem" and not state.identity.is_token
    assert r.ex.ledger.effective_pt(state.identity, beta, state.counters) == (5, 5)
    assert spell_record(r.ex, beta) is None  # the Golem has no ability
    r.run_step({"op": "advance_turn"})
    state = r.world.cards[beta]
    assert state.identity.name == "Steel Overseer"
    assert spell_record(r.ex, beta) is own
    assert r.ex.ledger.effective_pt(state.identity, beta, state.counters) == (2, 2)


def test_an_equipment_that_becomes_a_copy_of_a_creature_is_unattached_for_good() -> None:
    """Masterful Replication makes the equipped Colossus Hammer an Alpha Golem: no longer an
    Equipment, it becomes unattached (CR 704.5p); when the copy effect ends it is an Equipment
    again, still unattached, and the Bear stays 2/2 (no free re-equip)."""
    r = _runner("M20", [
        _real("mr", "Masterful Replication", zone="hand"),
        _real("hammer", "Colossus Hammer"),
        _synthetic("alpha", "Alpha Golem", "Artifact Creature — Golem", "4", "4"),
        _synthetic("bear", "Bear", "Creature — Bear", "2", "2"),
    ], mana={"0": {"U": 6}})
    r.run_step({"op": "enchant", "aura": "hammer", "host": "bear"})
    bear = r.handles["bear"]

    def bear_pt() -> tuple:
        state = r.world.cards[bear]
        return r.ex.ledger.effective_pt(state.identity, bear, state.counters)

    assert bear_pt() == (12, 12)
    r.run_step({"op": "cast", "key": "mr", "real": "Masterful Replication", "targets": ["alpha"],
                "decisions": ["1"]})
    assert r.handles["hammer"] not in r.ex.attachments and bear_pt() == (2, 2)
    r.run_step({"op": "advance_turn"})
    assert r.world.cards[r.handles["hammer"]].identity.name == "Colossus Hammer"
    assert r.handles["hammer"] not in r.ex.attachments and bear_pt() == (2, 2)


def test_a_copy_that_leaves_the_battlefield_is_the_printed_card_and_died_as_the_copy() -> None:
    """A permanent that is a copy and dies: its last known information is the copy (CR 608.2h,
    603.10a), the card in the graveyard is the printed one (CR 400.7)."""
    r = _replication(_real("beta", "Steel Overseer"))
    beta = r.handles["beta"]
    r.run_step({"op": "cast", "key": "mr", "real": "Masterful Replication", "targets": ["alpha"],
                "decisions": ["1"]})
    r.run_step({"op": "move", "key": "beta", "to": "graveyard"})
    assert r.world.cards[beta].identity.name == "Steel Overseer"
    assert r.ex.departed_lki[beta].identity.name == "Alpha Golem"
    assert r.ex.layers._copy_base == {}


# ------------------------------------------------------------------- the stack (CR 707.10)


def test_a_copied_spell_is_not_cast_and_ceases_off_the_stack() -> None:
    """Double Vision copies the first instant: one CAST row (the copy is not cast, so nothing
    counting casts sees it), the copy gone from the game once it resolved (CR 707.10a)."""
    r = _runner("M21", [
        _real("dv", "Double Vision"),
        _real("shock", "Shock", zone="hand"),
    ], mana={"0": {"R": 1}})
    before = set(r.world.cards)
    r.run_step({"op": "cast", "key": "shock", "real": "Shock", "targets": ["p1"],
                "decisions": ["first-legal"]})
    assert r.world.players[r.p1].life == 16
    assert sum(1 for e in r.ex.journal.events if e.kind == KIND_CAST) == 1
    assert set(r.world.cards) == before  # the copy ceased to exist


def test_a_copied_spell_keeps_its_kick_and_a_countered_one_is_still_copied() -> None:
    """Thousand-Year Storm's trigger waits while the kicked Burst Lightning is countered: it still
    copies the spell as it last existed on the stack (CR 608.2h), kicked (CR 707.10)."""
    r = _runner("FDN", [
        _real("storm", "Thousand-Year Storm"),
        _real("tt", "Think Twice", zone="hand"),
        _real("bl", "Burst Lightning", zone="hand"),
        _real("cancel", "Cancel", seat=1, zone="hand"),
    ], mana={"0": {"U": 2, "R": 1, "C": 4}, "1": {"U": 3}})
    r.run_step({"op": "cast", "key": "tt", "real": "Think Twice"})
    r.run_step({"op": "cast", "key": "bl", "real": "Burst Lightning", "targets": ["p1"],
                "kicked": True, "hold": True})
    r.run_step({"op": "cast", "key": "cancel", "real": "Cancel", "controller": 1,
                "targets": ["bl"], "hold": True})
    r.run_step({"op": "resolve"})  # Cancel counters Burst Lightning
    r.run_step({"op": "pass", "decisions": ["first-legal"]})
    assert r.world.players[r.p1].life == 16  # only the copy, 4 damage: kicked


def test_storm_counts_only_the_spells_cast_before_it() -> None:
    """Thousand-Year Storm: a spell cast in response to the second spell's trigger is not "cast
    before it", so that trigger copies once, the third's twice (CR 707.10, the ordinal fixed as
    the trigger goes on the stack)."""
    r = _runner("FDN", [
        _real("storm", "Thousand-Year Storm"),
        _real("tt", "Think Twice", zone="hand"),
        _real("bl2", "Burst Lightning", zone="hand"),
        _real("bl3", "Burst Lightning", zone="hand"),
    ], mana={"0": {"U": 2, "R": 2}})
    r.run_step({"op": "cast", "key": "tt", "real": "Think Twice"})
    r.run_step({"op": "cast", "key": "bl2", "real": "Burst Lightning", "targets": ["p1"],
                "hold": True})
    r.run_step({"op": "cast", "key": "bl3", "real": "Burst Lightning", "targets": ["p1"],
                "decisions": ["first-legal"] * 3})
    # the second, 2, and its one copy, 2; the third, 2, and its two copies, 4: 10 (12 if the
    # second's trigger had counted the third, cast after it)
    assert r.world.players[r.p1].life == 10


def test_a_copied_loyalty_ability_removes_no_loyalty() -> None:
    """Chandra's Regulator copies Chandra, Novice Pyromancer's [-2] for {1}: the copy is not
    activated, so pays no loyalty (CR 606.4, 707.10), and its new target is the Bear."""
    r = _runner("M20", [
        _real("reg", "Chandra's Regulator"),
        _real("chandra", "Chandra, Novice Pyromancer", zone="hand"),
        _synthetic("bear", "Bear", "Creature — Bear", "2", "2", seat=1),
    ], mana={"0": {"R": 4, "C": 1}})
    r.run_step({"op": "enter", "key": "chandra"})
    r.run_step({"op": "activate", "key": "chandra", "idx": 2, "seat": 0, "targets": ["p1"],
                "decisions": ["fire", "bear"]})
    assert r.world.cards[r.handles["chandra"]].counters["LOYALTY"] == 3
    assert r.world.players[r.p1].life == 18
    assert r.world.zone_of(r.handles["bear"]).kind == "graveyard"


def test_the_regulator_copies_the_ability_of_a_chandra_cast_this_turn() -> None:
    """Chandra cast this turn left her spell's frame among the objects that left the stack: "copy
    that ability" is still the [-2] her activation put there, never her spell (which put a second
    Chandra onto the battlefield, the legend rule then offering a fresh one)."""
    r = _runner("M20", [
        _real("reg", "Chandra's Regulator"),
        _real("chandra", "Chandra, Novice Pyromancer", zone="hand"),
        _synthetic("bear", "Bear", "Creature — Bear", "2", "2", seat=1),
    ], mana={"0": {"R": 5, "C": 1}})
    r.run_step({"op": "cast", "key": "chandra", "real": "Chandra, Novice Pyromancer"})
    r.run_step({"op": "activate", "key": "chandra", "idx": 2, "seat": 0, "targets": ["p1"],
                "decisions": ["fire", "bear"]})
    assert r.world.players[r.p1].life == 18
    assert r.world.zone_of(r.handles["bear"]).kind == "graveyard"
    assert r.world.cards[r.handles["chandra"]].counters["LOYALTY"] == 3
    assert _tokens(r, "Chandra, Novice Pyromancer") == []


def _asks(monkeypatch) -> list:
    """Every target ask of the game, (site, vocabulary)."""
    from MTG_bot.core.executor import quantity

    seen: list = []
    take = quantity.ExecCtx.take_decision_of

    def spy(self, seat, vocab, site, *args, **kwargs):
        if site.startswith("target:"):
            seen.append((site, tuple(vocab)))
        return take(self, seat, vocab, site, *args, **kwargs)

    monkeypatch.setattr(quantity.ExecCtx, "take_decision_of", spy)
    return seen


def test_a_copy_is_never_its_own_new_target(monkeypatch) -> None:
    """Double Vision copies Sublime Epiphany's "Counter target spell": the copy's new target may
    be Shock or the Epiphany itself, never the copy (CR 115.5)."""
    seen = _asks(monkeypatch)
    r = _runner("M21", [
        _real("dv", "Double Vision"),
        _real("se", "Sublime Epiphany", zone="hand"),
        _real("shock", "Shock", seat=1, zone="hand"),
    ], mana={"0": {"U": 6}, "1": {"R": 1}})
    r.run_step({"op": "cast", "key": "shock", "real": "Shock", "controller": 1, "targets": ["p0"],
                "hold": True})
    before = set(r.world.cards)
    r.run_step({"op": "cast", "key": "se", "real": "Sublime Epiphany", "controller": 0,
                "targets": ["shock"], "decisions": ["0", "first-legal"], "hold": True})
    # Double Vision's trigger: the copy, its target kept
    r.run_step({"op": "resolve", "decisions": ["first-legal"]})
    [copy] = set(r.world.cards) - before
    [(_, vocab)] = [ask for ask in seen if ask[0].startswith(f"target:{r.p0}:{copy}:")]
    assert str(copy) not in vocab and str(r.handles["shock"]) in vocab


def test_a_kept_target_that_changed_zones_is_no_target_of_the_copy() -> None:
    """Shock at the opponent's Bear; with Double Vision's trigger waiting the Bear is bounced and
    put back: a new object (CR 400.7). The copy keeps its target, the old Bear: it does not
    resolve, nor does Shock, and the new Bear is untouched (the copy keeps the original's
    declaration, CR 707.10)."""
    r = _runner("M21", [
        _real("dv", "Double Vision"),
        _real("shock", "Shock", zone="hand"),
        _synthetic("bear", "Bear", "Creature — Bear", "2", "2", seat=1),
    ], mana={"0": {"R": 1}})
    r.run_step({"op": "cast", "key": "shock", "real": "Shock", "targets": ["bear"], "hold": True})
    r.run_step({"op": "move", "key": "bear", "to": "hand", "hold": True})
    r.run_step({"op": "enter", "key": "bear", "hold": True})
    assert len(r.ex.stack.frames) == 2  # Shock and Double Vision's trigger wait
    r.run_step({"op": "pass", "decisions": ["first-legal"]})
    assert r.world.zone_of(r.handles["bear"]).kind == "battlefield"
    assert r.ex.damage.get(r.handles["bear"], 0) == 0


def test_rite_of_replication_kicked_makes_five_tokens_its_caster_controls() -> None:
    """Kicked at the opponent's Hawk: five token copies, the caster's (the pack's token lane
    counts every battlefield)."""
    r = _runner("FDN", [
        _real("rite", "Rite of Replication", zone="hand"),
        _real("hawk", "Healer's Hawk", seat=1),
    ], mana={"0": {"U": 2, "C": 7}})
    r.run_step({"op": "cast", "key": "rite", "real": "Rite of Replication", "targets": ["hawk"],
                "kicked": True})
    assert len(_tokens(r, "Healer's Hawk")) == 5


def test_a_token_copy_of_an_aura_enters_attached_to_what_its_controller_chooses() -> None:
    """Extravagant Replication copies Pacifism (on the opponent's Bear) at the upkeep: the token
    enters attached to the creature its controller chooses (CR 303.4f), not unattached and put
    into the graveyard."""
    r = _runner("FDN", [
        _real("er", "Extravagant Replication"),
        _real("pac", "Pacifism"),
        _synthetic("bear", "Bear", "Creature — Bear", "2", "2", seat=1),
        _synthetic("bear2", "Bear Two", "Creature — Bear", "3", "3", seat=1),
    ])
    r.run_step({"op": "enchant", "aura": "pac", "host": "bear"})
    r.run_step({"op": "advance_turn"})
    r.run_step({"op": "advance_turn", "decisions": ["bear2"]})  # the target is the one legal
    [token] = _tokens(r, "Pacifism")
    assert r.ex.attachments[token] == r.handles["bear2"]


# ------------------------------------------------- the gate round's findings (B3, KNOWLEDGE 215)


def _pt(r: ScenarioRunner, key: str) -> tuple:
    handle = r.handles[key]
    state = r.world.cards[handle]
    return r.ex.ledger.effective_pt(state.identity, handle, state.counters)


def test_a_permanent_that_becomes_a_diamond_knight_chose_no_colour() -> None:
    """M1 (215's F40): Prismite becomes a copy of Diamond Knight (which chose red): it did not
    enter (CR 707.4) and the Knight's choice is not copied (707.6), so its copied trigger reads
    no colour and never triggers (the card's ruling). Shock gives the Knight a counter, the copy
    none; before the fix the copy's trigger raised (no CHOOSE_NAME record)."""
    r = _runner("M20", [
        _real("mr", "Masterful Replication", zone="hand"),
        _real("knight", "Diamond Knight", zone="hand"),
        _real("prismite", "Prismite"),
        _real("shock", "Shock", zone="hand"),
    ], mana={"0": {"U": 6, "R": 1, "C": 3}})
    r.run_step({"op": "enter", "key": "knight", "decisions": ["R"]})
    r.run_step({"op": "cast", "key": "mr", "real": "Masterful Replication", "targets": ["knight"],
                "decisions": ["1"]})
    assert r.world.cards[r.handles["prismite"]].identity.name == "Diamond Knight"
    r.run_step({"op": "cast", "key": "shock", "real": "Shock", "targets": ["p1"]})
    assert r.world.cards[r.handles["knight"]].counters.get("PLUS_1_PLUS_1", 0) == 1
    assert r.world.cards[r.handles["prismite"]].counters.get("PLUS_1_PLUS_1", 0) == 0


def test_a_permanent_that_becomes_an_icon_of_ancestry_chose_no_type_and_gets_its_own_back() -> None:
    """M1: a Diamond Knight that chose red becomes a copy of Icon of Ancestry (which chose Elf):
    the copy's anthem reads no creature type (the Elf is 2/2, one Icon), and as the copy effect
    ends at cleanup the Knight has its own red again (CR 707.6: the copy's choices were never its
    own), so the next Shock gives it a counter."""
    r = _runner("M20", [
        _real("mr", "Masterful Replication", zone="hand"),
        _real("icon", "Icon of Ancestry", zone="hand"),
        _real("knight", "Diamond Knight", zone="hand"),
        _real("shock", "Shock", zone="hand"),
        _synthetic("elf", "Elf Scout", "Creature — Elf Scout", "1", "1"),
    ], mana={"0": {"U": 6}})
    r.run_step({"op": "enter", "key": "icon", "decisions": ["Elf"]})
    r.run_step({"op": "enter", "key": "knight", "decisions": ["R"]})
    r.run_step({"op": "cast", "key": "mr", "real": "Masterful Replication", "targets": ["icon"],
                "decisions": ["1"]})
    assert r.world.cards[r.handles["knight"]].identity.name == "Icon of Ancestry"
    assert _pt(r, "elf") == (2, 2)
    r.run_step({"op": "advance_turn"})
    r.run_step({"op": "advance_turn"})
    assert r.world.cards[r.handles["knight"]].identity.name == "Diamond Knight"
    r.run_step({"op": "mana", "seat": 0, "add": {"R": 1}})
    r.run_step({"op": "cast", "key": "shock", "real": "Shock", "targets": ["p1"]})
    assert r.world.cards[r.handles["knight"]].counters.get("PLUS_1_PLUS_1", 0) == 1


def test_a_token_copy_of_diamond_mare_chooses_its_own_colour() -> None:
    """215's F40, the token half: a token copy enters, so its "as this enters" choice is made anew
    (CR 707.5): Self-Reflection's copy of a Diamond Mare that chose blue chooses red, and only the
    token gains life from a red spell."""
    r = _runner("FDN", [
        _real("sr", "Self-Reflection", zone="hand"),
        _real("mare", "Diamond Mare", zone="hand"),
        _real("bolt", "Burst Lightning", zone="hand"),
    ], mana={"0": {"U": 2, "C": 4, "R": 1}})
    r.run_step({"op": "enter", "key": "mare", "decisions": ["U"]})
    r.run_step({"op": "cast", "key": "sr", "real": "Self-Reflection", "targets": ["mare"],
                "decisions": ["R"]})
    life = r.world.players[r.p0].life
    r.run_step({"op": "cast", "key": "bolt", "real": "Burst Lightning", "targets": ["p1"]})
    assert r.world.players[r.p0].life == life + 1


def test_a_copy_may_trade_its_two_targets() -> None:
    """m1: Double Vision copies Rookie Mistake (+0/+2 to A, -2/-0 to another target B). Only the
    final set of targets is judged (CR 707.10c, 115.7d-e), so the copy may give B the +0/+2 and
    A the -2/-0; asked slot by slot against the unchanged second slot, B was never offered."""
    r = _runner("M21", [
        _real("dv", "Double Vision"),
        _real("rm", "Rookie Mistake", zone="hand"),
        _synthetic("a", "Alpha Bear", "Creature — Bear", "2", "2"),
        _synthetic("b", "Beta Bear", "Creature — Bear", "3", "3"),
    ], mana={"0": {"U": 1}})
    r.run_step({"op": "cast", "key": "rm", "real": "Rookie Mistake", "targets": ["a", "b"],
                "decisions": ["b"]})
    assert _pt(r, "a") == (0, 4) and _pt(r, "b") == (1, 5)


def test_a_changed_target_moves_the_copys_clock_and_drops_a_kept_one_that_moved() -> None:
    """m2: Rookie Mistake at A (+0/+2) and B (-2/-0); with Double Vision's trigger waiting, A is
    bounced and put back (a new object, CR 400.7) and C enters. The copy keeps A and changes B to
    C: A is no target of the copy (dropped: not pumped), and C, which entered after the original
    chose its targets, is a legal new target judged from now (it gets -2/-0)."""
    r = _runner("M21", [
        _real("dv", "Double Vision"),
        _real("rm", "Rookie Mistake", zone="hand"),
        _synthetic("a", "Alpha Bear", "Creature — Bear", "2", "2"),
        _synthetic("b", "Beta Bear", "Creature — Bear", "3", "3"),
        _synthetic("c", "Gamma Bear", "Creature — Bear", "4", "4", zone="hand"),
    ], mana={"0": {"U": 1}})
    r.run_step({"op": "cast", "key": "rm", "real": "Rookie Mistake", "targets": ["a", "b"],
                "hold": True})
    r.run_step({"op": "move", "key": "a", "to": "hand", "hold": True})
    r.run_step({"op": "enter", "key": "a", "hold": True})
    r.run_step({"op": "enter", "key": "c", "hold": True})
    r.run_step({"op": "pass", "decisions": ["first-legal", "c"]})
    assert _pt(r, "a") == (2, 2) and _pt(r, "b") == (1, 3) and _pt(r, "c") == (2, 4)


def test_double_vision_copies_the_first_cast_not_a_later_cast_of_the_same_card() -> None:
    """m2 (review fix 9a): Shock at the opponent triggers Double Vision; before the trigger
    resolves Shock is returned to hand (Unsubstantiate) and cast again at a Bear. "Copy that
    spell" is the first Shock as it last existed (CR 608.2h), so the copy hits the opponent."""
    r = _runner("M21", [
        _real("dv", "Double Vision"),
        _real("shock", "Shock", zone="hand"),
        _real("un", "Unsubstantiate", zone="hand"),
        _synthetic("bear", "Bear", "Creature — Bear", "2", "2", seat=1),
    ], mana={"0": {"R": 2, "U": 1, "C": 1}})
    r.run_step({"op": "cast", "key": "shock", "real": "Shock", "targets": ["p1"], "hold": True})
    r.run_step({"op": "cast", "key": "un", "real": "Unsubstantiate", "targets": ["shock"],
                "hold": True})
    r.run_step({"op": "resolve", "hold": True})
    r.run_step({"op": "cast", "key": "shock", "real": "Shock", "targets": ["bear"], "hold": True})
    r.run_step({"op": "pass", "decisions": ["first-legal"]})
    assert r.world.zone_of(r.handles["bear"]).kind == "graveyard"
    assert r.world.players[r.p1].life == 18


def test_homunculus_horde_that_left_still_makes_its_copy() -> None:
    """m2: if Homunculus Horde leaves before its trigger resolves, the token is a copy of it as it
    last existed (CR 608.2h; the card's ruling)."""
    r = _runner("FDN", [
        _real("horde", "Homunculus Horde"),
        _real("tt1", "Think Twice", zone="hand"),
        _real("tt2", "Think Twice", zone="hand"),
    ], mana={"0": {"U": 2, "C": 2}})
    r.run_step({"op": "cast", "key": "tt1", "real": "Think Twice"})
    r.run_step({"op": "cast", "key": "tt2", "real": "Think Twice", "hold": True})
    r.run_step({"op": "resolve", "hold": True})  # the second card drawn: the trigger waits
    r.run_step({"op": "move", "key": "horde", "to": "graveyard", "hold": True})
    r.run_step({"op": "pass"})
    assert len(_tokens(r, "Homunculus Horde")) == 1


def test_a_token_horde_gone_before_its_trigger_still_makes_its_copy() -> None:
    """m2 (copying from last known information): a token copy of Homunculus Horde triggers on the
    second card drawn, then leaves and ceases to exist before its trigger resolves; "a copy of
    this creature" is then read from its last known information (CR 608.2h), so both triggers
    make a token. Without it the token's trigger found nothing to copy."""
    r = _runner("FDN", [
        _real("horde", "Homunculus Horde"),
        _real("sr", "Self-Reflection", zone="hand"),
        _real("tt1", "Think Twice", zone="hand"),
        _real("tt2", "Think Twice", zone="hand"),
    ], mana={"0": {"U": 4, "C": 6}})
    r.run_step({"op": "cast", "key": "sr", "real": "Self-Reflection", "targets": ["horde"]})
    [first] = _tokens(r, "Homunculus Horde")
    r.handles["first"] = first
    r.run_step({"op": "cast", "key": "tt1", "real": "Think Twice"})
    r.run_step({"op": "cast", "key": "tt2", "real": "Think Twice", "hold": True})
    r.run_step({"op": "resolve", "hold": True, "decisions": ["first-legal"]})  # two triggers wait
    r.run_step({"op": "move", "key": "first", "to": "graveyard", "hold": True})
    r.run_step({"op": "pass", "decisions": ["first-legal"]})
    assert first not in r.world.cards
    assert len(_tokens(r, "Homunculus Horde")) == 2


def test_a_permanent_that_becomes_a_copy_of_a_token_is_no_token() -> None:
    """m2: Prismite becomes a copy of a Thopter token: being a token is no copiable value (CR
    707.2; Masterful Replication's ruling), so Prismite stays a card."""
    r = _runner("M20", [
        _real("mr", "Masterful Replication", zone="hand"),
        _synthetic("thopter", "Thopter", "Artifact Creature — Thopter", "1", "1", token=True),
        _real("prismite", "Prismite"),
    ], mana={"0": {"U": 6}})
    r.run_step({"op": "cast", "key": "mr", "real": "Masterful Replication", "targets": ["thopter"],
                "decisions": ["1"]})
    state = r.world.cards[r.handles["prismite"]]
    assert state.identity.name == "Thopter" and not state.identity.is_token


@pytest.mark.parametrize("excepted_first", [True, False])
def test_each_token_copy_keeps_its_own_exceptions(excepted_first) -> None:
    """m4 (215's F29): Electroduplicate's copy of a Hawk has haste and the end-step sacrifice,
    Self-Reflection's copy of the same Hawk neither, whichever comes first: a copy's record is its
    handle's (CR 707.9a: the exceptions are one copy effect's)."""
    r = _runner("FDN", [
        _real("ed", "Electroduplicate", zone="hand"),
        _real("sr", "Self-Reflection", zone="hand"),
        _real("hawk", "Healer's Hawk"),
    ], mana={"0": {"R": 1, "U": 2, "C": 6}})
    order = [("ed", "Electroduplicate"), ("sr", "Self-Reflection")]
    for key, name in order if excepted_first else order[::-1]:
        r.run_step({"op": "cast", "key": key, "real": name, "targets": ["hawk"]})
    hasty = [h for h in _tokens(r, "Healer's Hawk") if r.ex.layers.keyword_of(h, "HASTE")]
    [plain] = [h for h in _tokens(r, "Healer's Hawk") if h not in hasty]
    assert len(hasty) == 1
    assert len(spell_record(r.ex, plain).abilities) == len(spell_record(r.ex, r.handles["hawk"]).abilities)
    r.run_step({"op": "combat", "seat": 0, "attack": {}})
    r.run_step({"op": "to_step", "step": "END_TURN", "decisions": ["first-legal"]})
    r.run_step({"op": "pass"})
    assert _tokens(r, "Healer's Hawk") == [plain]


def test_a_copy_of_a_creature_spell_resolves_into_a_token_never_created() -> None:
    """m5: a copy of a permanent spell becomes a token as it resolves and is not "created" (CR
    608.3f): Unsubstantiate's tree swapped for "Copy target creature spell." copies Pridemalkin;
    the copy enters as a token Pridemalkin, and no CREATE_TOKEN row is written."""
    from MTG_bot.core.ability_tree import (
        Atom,
        AtomArgs,
        ControllerRef,
        FAtom,
        FAtomPred,
        QConst,
        Selector,
        SelectorMode,
        SpellAbility,
        SpellKind,
        Verb,
        Zone,
        ZoneKind,
    )
    from MTG_bot.core.ability_tree import CopyOf as Copy
    from tools.cards.gates import swapped

    supply = _supply("M21")
    oid = next(o for o, res in supply.pool.results.items()
               if res.card is not None and res.card.name == "Unsubstantiate")
    creature_spell = Selector(QConst(1), SelectorMode.TARGET, FAtom(FAtomPred.TYPE_EQ, string_value="Creature"),
                              zones=(Zone(ZoneKind.STACK, ControllerRef.ANY),))
    effect = Atom(Verb.COPY, AtomArgs(pairs=(("source", Copy(creature_spell)),)))
    card = dataclasses.replace(supply.pool.results[oid].card,
                               abilities=(SpellAbility(kind=SpellKind.INSTANT, effect=effect),))
    with swapped(supply, oid, card):
        r = _runner("M21", [
            _real("un", "Unsubstantiate", zone="hand"),
            _real("cat", "Pridemalkin", zone="hand"),
        ], mana={"0": {"U": 3, "G": 3, "C": 3}})
        r.run_step({"op": "cast", "key": "cat", "real": "Pridemalkin", "hold": True})
        r.run_step({"op": "cast", "key": "un", "real": "Unsubstantiate", "targets": ["cat"],
                    "hold": True})
        r.run_step({"op": "pass", "decisions": ["first-legal"] * 4})
        assert len(_tokens(r, "Pridemalkin")) == 1
        assert r.world.zone_of(r.handles["cat"]).kind == ZONE_BATTLEFIELD
        assert not any(len(e) > 1 and e[1] == "CREATE_TOKEN" for e in r.ex.events)


# ---------------------------------------------------------------- what the network reads


def test_the_network_reads_a_copy_as_the_card_it_copies() -> None:
    """The network's card token is the oracle id's row (tools/selfplay/features.encode): a token
    copy and a permanent that became a copy read as the copied card, the token flag set only on
    the token (AGENTS §10)."""
    from MTG_bot.bench.protocol import Ask
    from tools.selfplay.features import F_TOKEN, CardTable, encode

    def _table(code: str) -> CardTable:  # the pool's card table, as the learner builds it
        return CardTable.from_records({oid: r.card for oid, r in _supply(code).pool.results.items()})

    r = _runner("M20", [
        _real("mr", "Masterful Replication", zone="hand"),
        _real("prismite", "Prismite"),
        _real("overseer", "Steel Overseer"),
    ], mana={"0": {"U": 6}})
    table = _table("M20")
    oid = {key: r.world.cards[r.handles[key]].identity.oracle_id for key in ("prismite", "overseer")}
    r.run_step({"op": "cast", "key": "mr", "real": "Masterful Replication", "targets": ["prismite"],
                "decisions": ["1"]})
    ask = Ask(seat=0, kind="act", site="act", prompt="", options=())
    rows = list(encode(r.ex, 0, ask, table)["cards_i"][:, 0])
    assert rows.count(table.row(oid["prismite"])) == 2  # Prismite and the Overseer copying it
    assert table.row(oid["overseer"]) not in rows
    assert np.all(encode(r.ex, 0, ask, table)["cards_f"][:, F_TOKEN] == 0)
    # a token copy: the copied card's row, the token flag set
    r = _runner("FDN", [_real("sr", "Self-Reflection", zone="hand"), _real("hawk", "Healer's Hawk")],
                mana={"0": {"U": 2, "C": 4}})
    r.run_step({"op": "cast", "key": "sr", "real": "Self-Reflection", "targets": ["hawk"]})
    table = _table("FDN")
    out = encode(r.ex, 0, ask, table)
    hawk_row = table.row(r.world.cards[r.handles["hawk"]].identity.oracle_id)
    hawks = [j for j, row in enumerate(out["cards_i"][:, 0]) if row == hawk_row]
    assert len(hawks) == 2 and sorted(float(out["cards_f"][j, F_TOKEN]) for j in hawks) == [0.0, 1.0]
