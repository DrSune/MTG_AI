"""Round B12's engine (DESIGN_ATOM_ONTOLOGY §19): the opening-hand actions (CR 103.6), the
prohibitions (CR 101.2: casting, CR 601.3; entering the battlefield; gaining life; losing or
winning the game) and LOSE_GAME / WIN_GAME naming their player (CR 104.2b, 104.3e).

Every test fails on the base (eaedfc1b): the cards' sentences did not compile there (Rule of Law,
Grafdigger's Cage, Giant Cindermaw, Platinum Angel and the Leylines were bare carriers), and the
opening-hand step, the prohibition consumers, WIN_GAME and the player of LOSE_GAME did not exist.
"""

from __future__ import annotations

from functools import cache

import pytest

from MTG_bot.core.ability_tree import (
    Atom,
    AtomArgs,
    CardRecord,
    CastSpellEvent,
    ControllerRef,
    DamageDealtEvent,
    FAnd,
    FAtom,
    FAtomPred,
    OpeningHandAbility,
    QConst,
    QUnbounded,
    StaticAbility,
    TriggeredAbility,
    Verb,
    Zone,
    ZoneChangeEvent,
    ZoneKind,
    begin_on_battlefield,
    event_player,
)
from MTG_bot.core.compiler.templates_b21 import game_result, prohibit
from MTG_bot.core.executor import Executor, GameOver, games
from MTG_bot.core.executor.events import KIND_GAME_LOST, KIND_TURN_PHASE
from MTG_bot.core.executor.games import compile_supply, opening_hand_actions
from MTG_bot.core.executor.legality import spell_castable
from MTG_bot.core.executor.menu import menu
from MTG_bot.core.state import (
    ZONE_BATTLEFIELD,
    ZONE_GRAVEYARD,
    ZONE_HAND,
    ZONE_LIBRARY,
    GameWorld,
)
from MTG_bot.core.test_executor_binding import card_id, reset_oracle_ids
from tools.run_scenarios import ScenarioRunner

YOU = ControllerRef.YOU


@cache
def _supply(code: str):
    return compile_supply("all", code, require_verified=False)


def _runner(code: str, cards: list[dict], mana: dict | None = None) -> ScenarioRunner:
    pack = {"set": code, "world": {"life": 20, "seed": 7}, "cards": cards, "steps": []}
    if mana:
        pack["mana"] = mana
    return ScenarioRunner(pack, _supply(code))


def _real(key: str, name: str, seat: int = 0, zone: str = "battlefield") -> dict:
    return {"key": key, "real": name, "zone": zone, "controller": seat}


def _zone(r: ScenarioRunner, key: str) -> str:
    return r.world.zone_of(r.handles[key]).kind


def _cast(r: ScenarioRunner, key: str, seat: int = 0, targets: tuple[str, ...] = ()) -> None:
    r.run_step({"op": "cast", "key": key, "real": r.world.cards[r.handles[key]].identity.name,
                "controller": seat, "targets": list(targets)})


def _reason(r: ScenarioRunner, key: str, seat: int = 0) -> str | None:
    return spell_castable(r.ex, r.seats[seat], r.handles[key])[0]


# ------------------------------------------------------------------ the opening hand (CR 103.6)


def _record(oid: str, *abilities: object, creature: bool = False) -> CardRecord:
    """A minimal record: an enchantment, or a 4/5 creature."""
    return CardRecord(
        oracle_id=oid, name="Rec", type_line="Creature" if creature else "Enchantment",
        types=("Creature",) if creature else ("Enchantment",), subtypes=(), supertypes=(),
        colors=(), color_identity=frozenset(), mana_cost=None, mana_value=4,
        power=QConst(4) if creature else None, toughness=QConst(5) if creature else None,
        loyalty=None, keywords=(), abilities=tuple(abilities), is_token=False,
    )


def _menu_words(r: ScenarioRunner, seat: int = 0) -> set[str]:
    return {row.token for row in menu(r.ex, r.seats[seat])}


def _ruled(r: ScenarioRunner, seat: int, *abilities: object, creature: bool = False):
    """A permanent of ``seat`` carrying ``abilities`` (a rule a test needs no printed card for)."""
    handle = r.world.add_card(card_id("Rule", type_line="Creature" if creature else "Enchantment"),
                              r.seats[seat], ZONE_BATTLEFIELD)
    r.ex.attach_card(handle, _record(r.world.cards[handle].identity.oracle_id, *abilities,
                                     creature=creature))
    return handle


class _Table:
    """Two players, each holding cards whose records the binder knows (as a dealt pool's are)."""

    def __init__(self, *abilities: object) -> None:
        reset_oracle_ids()
        self.world = GameWorld(num_players=2, start_life=20, master_seed=3)
        self.p0, self.p1 = self.world.player_order
        self.ex = Executor(self.world)
        self.asks: list[tuple[str, tuple[str, ...]]] = []
        self.answers: dict[str, str] = {}
        self.ex.decisions.provider = self._answer
        self.cards = {}
        for seat, key in ((self.p0, "a"), (self.p1, "b")):
            handle = self.world.add_card(card_id(f"Leyline {key}", type_line="Enchantment"),
                                         seat, ZONE_HAND)
            oid = self.world.cards[handle].identity.oracle_id
            self.ex.binder.records[oid] = _record(oid, OpeningHandAbility(begin_on_battlefield()),
                                                  *abilities)
            self.cards[key] = handle
        for seat in (self.p0, self.p1):
            for i in range(10):
                self.world.add_card(card_id(f"Card {i}", type_line="Sorcery"), seat, ZONE_LIBRARY)

    def _answer(self, vocab: tuple[str, ...], what: str) -> str:
        self.asks.append((what, vocab))
        return self.answers.get(what.split(":")[1] + ":" + what.split(":")[2], "fire")

    def run(self) -> None:
        opening_hand_actions(self.ex, [self.p0, self.p1])


def test_the_starting_player_takes_their_actions_first_then_each_other_player() -> None:
    """The Leylines' ruling: the starting player takes all such actions first, then each other
    player in turn order. Each is a may ask whose source is the card in hand (``may:<card>``), a
    fired one moves the card onto the battlefield (CR 103.6a), a declined one stays in hand."""
    t = _Table()
    t.answers[str(t.cards["b"])] = "skip"
    t.run()
    assert [what.split(":")[0] for what, _ in t.asks] == ["may", "may"]
    assert [what.split(":", 1)[1].rsplit(":", 1)[0] for what, _ in t.asks] == [
        str(t.cards["a"]), str(t.cards["b"])]
    assert all(vocab == ("fire", "skip") for _, vocab in t.asks)
    assert t.world.zone_of(t.cards["a"]).kind == ZONE_BATTLEFIELD
    assert t.world.zone_of(t.cards["b"]).kind == ZONE_HAND


def test_an_ability_the_move_triggers_waits_for_the_first_upkeep() -> None:
    """Nobody has priority before the first turn (CR 117), so an ability the card's entering
    triggers is put on the stack the next time a player would receive priority, in the first
    turn's upkeep (CR 603.3): its "When this enters, you gain 1 life" has not happened when the
    first turn begins, and has by its upkeep."""
    etb = TriggeredAbility(
        ZoneChangeEvent(Zone(ZoneKind.ANY, ControllerRef.ANY), Zone(ZoneKind.BATTLEFIELD, YOU),
                        subject=FAtom(pred=FAtomPred.IS_SOURCE)),
        None, Atom(Verb.GAIN_LIFE, AtomArgs(pairs=(("amount", QConst(1)), ("controller", YOU)))))
    t = _Table(etb)
    t.answers[str(t.cards["b"])] = "skip"
    t.run()
    assert t.world.zone_of(t.cards["a"]).kind == ZONE_BATTLEFIELD
    assert t.world.players[t.p0].life == 20 and not t.ex.stack.frames
    t.ex.begin_turn(t.p0)
    assert t.world.players[t.p0].life == 21
    rows = t.ex.journal.events
    upkeep = next(i for i, e in enumerate(rows) if e.kind == KIND_TURN_PHASE)
    gained = next(i for i, e in enumerate(rows) if e.kind == "LIFE_GAINED")
    assert upkeep < gained


def test_a_card_out_of_the_opening_hand_takes_no_action() -> None:
    """Only the opening hand (the hand after the mulligans) acts: a card in the library is asked
    nothing, and a card in the hand of a later turn never (the step runs once, before turn 1)."""
    t = _Table()
    for key in ("a", "b"):
        t.world.move_to_zone(t.cards[key], t.world.controller_of(t.cards[key]), ZONE_LIBRARY)
    t.run()
    assert t.asks == []


class _Firing(games.RandomPolicy):
    """The harness policy, but every may ask fired."""

    def answer(self, vocab: tuple[str, ...], what: str) -> str:
        return "fire" if "fire" in vocab else super().answer(vocab, what)


def test_a_dealt_game_runs_the_opening_hand_actions_before_its_first_turn() -> None:
    """The game loop (games._play_turns): the mulligans, then the opening-hand actions, then turn
    1. Decks of Leyline of Sanctity (M20) and Plains: every Leyline in a kept hand begins the
    game on the battlefield, so the first turn begins with them there."""
    supply = compile_supply("all", "M20", require_verified=False)
    oid = next(o for o in supply.deckable if supply.metas[o].name == "Leyline of Sanctity")
    plains = next(o for o in supply.deckable if supply.metas[o].name == "Plains")
    deck = (oid,) * 20 + (plains,) * 40
    game = games._setup_game(5, supply, (deck, deck))
    seen = {}

    def stop(g, boundary: str) -> bool:
        if boundary == "turn_top":
            for seat in g.world.player_order:
                seen[seat] = [g.world.cards[h].identity.name
                              for h in g.world.players[seat].zone(ZONE_BATTLEFIELD).entries]
                seen[seat, "hand"] = [g.world.cards[h].identity.name
                                      for h in g.world.players[seat].zone(ZONE_HAND).entries]
            return True
        return False

    games._play(game, _Firing(5), game.world.player_order, 3, stop_after=stop)
    for seat in game.world.player_order:
        assert "Leyline of Sanctity" not in seen[seat, "hand"]
        assert seen[seat].count("Leyline of Sanctity") >= 1


# ------------------------------------------------------------------ casting (CR 601.3)


def test_rule_of_law_lets_each_player_cast_one_spell_a_turn() -> None:
    """M20 Rule of Law: "Each player can't cast more than one spell each turn." Each player's
    second cast is refused, the other player's first is not (CR 101.2: the "can't" wins)."""
    r = _runner("M20", [_real("law", "Rule of Law"), _real("shock", "Shock", zone="hand"),
                        _real("unsummon", "Unsummon", zone="hand"),
                        _real("bolt", "Shock", seat=1, zone="hand"),
                        _real("disfigure", "Disfigure", seat=1, zone="hand")],
                {"0": {"R": 1, "U": 1}, "1": {"R": 1, "B": 1}})
    _cast(r, "shock", targets=("p1",))
    assert _reason(r, "unsummon") == f"prohibited:cast:{r.handles['unsummon']}"
    _cast(r, "bolt", seat=1, targets=("p0",))
    assert _reason(r, "disfigure", seat=1) == f"prohibited:cast:{r.handles['disfigure']}"
    r.run_step({"op": "advance_turn"})
    r.run_step({"op": "mana", "seat": 1, "add": {"B": 1}})
    assert _reason(r, "disfigure", seat=1) is None  # a new turn


def test_rule_of_law_counts_the_spells_cast_before_it_arrived() -> None:
    """Rule of Law's rulings: it "looks at the entire turn", and a countered spell counts. A Shock,
    then Rule of Law itself (the second spell, cast before the rule existed): the third is refused,
    which an exact ordinal of 2 would have let through (QAtLeast(2): the second or later)."""
    r = _runner("M20", [_real("law", "Rule of Law", zone="hand"),
                        _real("shock", "Shock", zone="hand"),
                        _real("unsummon", "Unsummon", zone="hand")],
                {"0": {"R": 1, "W": 3, "U": 1}})
    _cast(r, "shock", targets=("p1",))
    _cast(r, "law")
    assert _zone(r, "law") == ZONE_BATTLEFIELD
    assert _reason(r, "unsummon") == f"prohibited:cast:{r.handles['unsummon']}"


def test_a_countered_spell_counts_toward_rule_of_law() -> None:
    r = _runner("M20", [_real("law", "Rule of Law"), _real("shock", "Shock", zone="hand"),
                        _real("unsummon", "Unsummon", zone="hand"),
                        _real("negate", "Negate", seat=1, zone="hand")],
                {"0": {"R": 1, "U": 1}, "1": {"U": 2}})
    r.run_step({"op": "cast", "key": "shock", "real": "Shock", "controller": 0,
                "targets": ["p1"], "hold": True})
    r.run_step({"op": "cast", "key": "negate", "real": "Negate", "controller": 1,
                "targets": ["shock"], "hold": True})
    r.run_step({"op": "pass"})
    assert _zone(r, "shock") == ZONE_GRAVEYARD and r.world.players[r.seats[1]].life == 20
    assert _reason(r, "unsummon") == f"prohibited:cast:{r.handles['unsummon']}"


def test_deafening_silence_allows_creature_spells_and_one_noncreature_spell() -> None:
    """ELD Deafening Silence: "Each player can't cast more than one noncreature spell each turn."
    (Its ruling: any number of creature spells plus one noncreature spell.)"""
    r = _runner("ELD", [_real("ds", "Deafening Silence"), _real("bear1", "Garenbrig Paladin", zone="hand"),
                        _real("bolt", "Searing Barrage", zone="hand"),
                        _real("opt", "Opt", zone="hand")],
                {"0": {"G": 5, "R": 5, "U": 1}})
    _cast(r, "bear1")
    assert _reason(r, "bolt") is None  # a creature spell used up nothing
    _cast(r, "bolt", targets=("bear1",))
    assert _reason(r, "opt") == f"prohibited:cast:{r.handles['opt']}"


def test_grafdiggers_cage_stops_casting_from_the_top_of_a_library() -> None:
    """M20 Grafdigger's Cage: "Players can't cast spells from graveyards or libraries." Mystic
    Forge's permission to cast from the top of the library is overruled (CR 101.2)."""
    r = _runner("M20", [_real("forge", "Mystic Forge"), _real("vial", "Vial of Dragonfire", zone="library"),
                        _real("cage", "Grafdigger's Cage", zone="hand")],
                {"0": {"C": 2}})
    r.world.players[r.seats[0]].zone(ZONE_LIBRARY).entries.remove(r.handles["vial"])
    r.world.players[r.seats[0]].zone(ZONE_LIBRARY).entries.append(r.handles["vial"])  # on top
    assert f"cast:{r.handles['vial']}" in _menu_words(r)
    r.run_step({"op": "move", "key": "cage", "to": "battlefield"})
    assert f"cast:{r.handles['vial']}" not in _menu_words(r)


def test_a_cast_effect_is_prohibited_too() -> None:
    """CR 601.3 holds for a spell an effect casts (Chandra, Flame's Catalyst's [-2], "You may cast
    target red instant or sorcery card from your graveyard"): under "Players can't cast spells from
    graveyards" the card is no castable designee, so the effect has nothing to cast."""
    from MTG_bot.core.executor.query import cast_designee_ok

    r = _runner("M21", [_real("shock", "Shock", zone="graveyard")], {"0": {"R": 1}})
    ctx = r.ex._ctx(source=r.handles["shock"], controller=r.seats[0], bindings=None, decisions=())
    assert cast_designee_ok(r.ex, ctx, r.handles["shock"])
    graveyards = Zone(ZoneKind.GRAVEYARD, ControllerRef.ANY)
    _ruled(r, 1, StaticAbility(prohibit(CastSpellEvent(filter=FAnd(()), from_zone=graveyards))))
    assert not cast_designee_ok(r.ex, ctx, r.handles["shock"])


def test_silence_lasts_its_turn() -> None:
    """M11 Silence: "Your opponents can't cast spells this turn." A resolving prohibition (CR
    611.2c): the opponent casts nothing this turn, and again the next; its caster may."""
    r = _runner("M11", [_real("silence", "Silence", zone="hand"),
                        _real("bolt", "Lightning Bolt", zone="hand"),
                        _real("sting", "Hornet Sting", seat=1, zone="hand")],
                {"0": {"W": 1, "R": 1}, "1": {"G": 1}})
    _cast(r, "silence")
    assert _reason(r, "sting", seat=1) == f"prohibited:cast:{r.handles['sting']}"
    assert _reason(r, "bolt") is None
    r.run_step({"op": "advance_turn"})
    r.run_step({"op": "mana", "seat": 1, "add": {"G": 1}})
    assert _reason(r, "sting", seat=1) is None


# ------------------------------------------------------------------ entering the battlefield


def test_grafdiggers_cage_keeps_creature_cards_in_graveyards_and_libraries() -> None:
    """"Creature cards in graveyards and libraries can't enter the battlefield": Gravewaker's
    "Return target creature card from your graveyard to the battlefield tapped" finds its target
    and does nothing (the card stays); a creature card from a library stays too, a noncreature
    card from a graveyard enters."""
    cards = [_real("cage", "Grafdigger's Cage"), _real("waker", "Gravewaker"),
             _real("dead", "Vampire of the Dire Moon", zone="graveyard"),
             _real("deep", "Vampire of the Dire Moon", zone="library"),
             _real("forge", "Mystic Forge", zone="graveyard")]
    r = _runner("M20", cards, {"0": {"B": 7}})
    r.run_step({"op": "activate", "key": "waker", "idx": 0, "seat": 0, "targets": ["dead"]})
    assert _zone(r, "dead") == ZONE_GRAVEYARD
    for key in ("deep", "forge"):
        r.run_step({"op": "move", "key": key, "to": "battlefield"})
    assert _zone(r, "deep") == ZONE_LIBRARY
    assert _zone(r, "forge") == ZONE_BATTLEFIELD
    assert any(e[1] == "MOVE_PROHIBITED" for e in r.ex.events)


# ------------------------------------------------------------------ life (CR 119)


def test_giant_cindermaw_stops_every_life_gain_and_its_replacement() -> None:
    """FDN Giant Cindermaw: "Players can't gain life." Moment of Triumph's "You gain 2 life"
    gains nothing while its pump happens (the ruling), and Angel of Vitality's "If you would gain
    life, you gain that much life plus 1 instead" has no gain to replace (Leyline of Punishment's
    ruling)."""
    r = _runner("FDN", [_real("maw", "Giant Cindermaw"), _real("angel", "Angel of Vitality"),
                        _real("moment", "Moment of Triumph", zone="hand")], {"0": {"W": 1}})
    _cast(r, "moment", targets=("angel",))
    assert r.world.players[r.seats[0]].life == 20
    assert r.ex.ledger.effective_pt(r.world.cards[r.handles["angel"]].identity, r.handles["angel"],
                                    r.world.cards[r.handles["angel"]].counters)[0] >= 4
    assert not any(e[1] == "LIFE_REPLACED" for e in r.ex.events)
    assert any(e[1] == "GAIN_PROHIBITED" for e in r.ex.events)


def test_your_opponents_cant_gain_life_spares_you() -> None:
    from MTG_bot.core.ability_tree import LifeGainedEvent

    r = _runner("FDN", [_real("moment", "Moment of Triumph", zone="hand"),
                        _real("bear", "Angel of Vitality")], {"0": {"W": 1}})
    opponents = FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.OPPONENT)
    _ruled(r, 1, StaticAbility(prohibit(LifeGainedEvent(actor=opponents))))
    _cast(r, "moment", targets=("bear",))
    assert r.world.players[r.seats[0]].life == 20  # seat 1's opponent gains nothing
    r2 = _runner("FDN", [_real("moment", "Moment of Triumph", zone="hand"),
                         _real("bear", "Angel of Vitality")], {"0": {"W": 1}})
    _ruled(r2, 0, StaticAbility(prohibit(LifeGainedEvent(actor=opponents))))
    _cast(r2, "moment", targets=("bear",))
    assert r2.world.players[r2.seats[0]].life == 23  # its controller gains (2, Angel's + 1)


# ------------------------------------------------------------------ the game's end (CR 104)


def test_platinum_angel_keeps_you_in_at_zero_life_until_it_leaves() -> None:
    """M11 Platinum Angel: "You can't lose the game and your opponents can't win the game." At 0
    or less life its controller keeps playing; once it leaves, they lose at the next check (the
    ruling)."""
    r = _runner("M11", [_real("angel", "Platinum Angel"),
                        _real("bolt", "Lightning Bolt", seat=1, zone="hand")], {"1": {"R": 1}})
    r.run_step({"op": "life", "seat": 0, "set": 2})
    _cast(r, "bolt", seat=1, targets=("p0",))
    assert r.world.players[r.seats[0]].life == -1 and r.ex.lost_players == []
    with pytest.raises(GameOver):
        r.run_step({"op": "move", "key": "angel", "to": "graveyard"})  # destroyed
    assert r.ex.lost_players == [r.seats[0]]


def test_platinum_angel_stops_lose_game_effects_and_an_opponents_win() -> None:
    """No game effect makes you lose or an opponent win while you control it (the ruling): a
    LOSE_GAME of you and a WIN_GAME of the opponent do nothing; a draw from an empty library
    loses nothing either (CR 704.5b, judged once)."""
    r = _runner("M11", [_real("angel", "Platinum Angel")])
    p0, p1 = r.seats
    r.ex.execute(game_result(Verb.LOSE_GAME, YOU), source=r.handles["angel"], controller=p0)
    r.ex.execute(game_result(Verb.WIN_GAME, YOU), source=r.handles["angel"], controller=p1)
    r.world.players[p0].zone(ZONE_LIBRARY).entries.clear()
    r.ex.execute(Atom(Verb.DRAW, AtomArgs(pairs=(("amount", QConst(1)), ("controller", YOU)))),
                 source=r.handles["angel"], controller=p0)
    assert r.ex.lost_players == []


def test_lichs_mastery_does_not_stop_an_opponents_win() -> None:
    """DOM Lich's Mastery: "You can't lose the game." Its ruling: an opponent can still win if an
    effect says so; the game ends with their win (the GAME_LOST row says WIN_GAME)."""
    r = _runner("DOM", [_real("mastery", "Lich's Mastery")])
    p0, p1 = r.seats
    r.ex.execute(game_result(Verb.LOSE_GAME, YOU), source=r.handles["mastery"], controller=p0)
    assert r.ex.lost_players == []
    with pytest.raises(GameOver):
        r.ex.execute(game_result(Verb.WIN_GAME, YOU), source=r.handles["mastery"], controller=p1)
    assert r.ex.lost_players == [p0]
    row = next(e for e in r.ex.journal.events if e.kind == KIND_GAME_LOST)
    assert (row.subject, row.data) == (p0, ("WIN_GAME",))


def test_herald_of_eternal_dawn_is_platinum_angels_tree() -> None:
    """FDN Herald of Eternal Dawn prints Platinum Angel's sentence: one tree for it."""
    def static(code: str, name: str):
        supply = _supply(code)
        card = next(res.card for res in supply.pool.results.values() if res.card.name == name)
        return [a for a in card.abilities if isinstance(a, StaticAbility)]

    assert static("FDN", "Herald of Eternal Dawn") == static("M11", "Platinum Angel")


def test_that_player_of_a_damage_trigger_loses_the_game() -> None:
    """Atemsis's and Phage's "that player loses the game": LOSE_GAME of event_player(), the
    player the trigger's damage was dealt to (CR 104.3e), never the trigger's controller."""
    r = _runner("M20", [_real("shock", "Shock", zone="hand")], {"0": {"R": 1}})
    p0, p1 = r.seats
    trigger = TriggeredAbility(
        DamageDealtEvent(amount=QUnbounded(), filter=FAtom(pred=FAtomPred.OPPONENT_OF, who=YOU),
                         source=FAtom(pred=FAtomPred.IS_SOURCE)),
        None, game_result(Verb.LOSE_GAME, event_player()))
    sphinx = _ruled(r, 0, trigger, creature=True)
    with pytest.raises(GameOver):
        r.ex.execute(Atom(Verb.DEAL_DAMAGE, AtomArgs(pairs=(
            ("amount", QConst(1)),
            ("target", _player_target()),
        ))), source=sphinx, controller=p0, bindings={"target": [p1]})
    assert r.ex.lost_players == [p1]


def _player_target():
    from MTG_bot.core.ability_tree import Selector, SelectorMode

    return Selector(QConst(1), SelectorMode.TARGET, FAnd(()),
                    (Zone(ZoneKind.PLAYER, ControllerRef.ANY),))


def test_target_player_loses_the_game() -> None:
    """Door to Nothingness's "Target player loses the game": the designated player."""
    r = _runner("M20", [])
    p0, p1 = r.seats
    with pytest.raises(GameOver):
        r.ex.execute(game_result(Verb.LOSE_GAME, ControllerRef.TARGET_PLAYER), source=p0,
                     controller=p0, bindings={"target": [p1]})
    assert r.ex.lost_players == [p1]
