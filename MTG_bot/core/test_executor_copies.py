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

from functools import cache

import numpy as np

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
