"""SeatRouter: per-seat agents inside the engine's own loop, every ask on the right seat."""

from __future__ import annotations

import pytest

from MTG_bot.bench.agents import PassAgent, UniformRandomAgent
from MTG_bot.bench.protocol import AskRoutingError, UnknownAskSite, resolve_ask_seat
from MTG_bot.bench.router import SeatRouter
from MTG_bot.bench.view import OracleIndex, SeatLens
from MTG_bot.core.ability_tree import Atom, AtomArgs, Verb
from MTG_bot.core.executor.games import (
    RandomPolicy,
    _play,
    _setup_game,
    deal_decks,
    get_supply,
    identity_of,
    play_game,
)
from MTG_bot.core.identity import Handle
from MTG_bot.core.state import ZONE_BATTLEFIELD, ZONE_HAND, ZONE_LIBRARY
from MTG_bot.utils import rng

ORACLE = OracleIndex.for_sets("M21", "ZNR")
P0, P1 = Handle("player", 0), Handle("player", 1)


def _game(seed: int, set_code: str = "M21"):
    supply = get_supply("castable", set_code)
    return _setup_game(seed, supply, deal_decks(seed, 1409, supply)), supply


def _lenses():
    return [SeatLens(0, ORACLE), SeatLens(1, ORACLE)]


def test_routing_rejects_unknown_kinds_and_disagreeing_tags() -> None:
    assert resolve_ask_seat("attack:card:3:7", P1) == P1
    assert resolve_ask_seat("scry:player:0:1", P0) == P0
    with pytest.raises(AskRoutingError):
        resolve_ask_seat("scry:player:0:1", P1)  # tag and engine disagree
    with pytest.raises(AskRoutingError):
        resolve_ask_seat("may:card:9:abc", None)  # engine named no seat
    with pytest.raises(UnknownAskSite):
        resolve_ask_seat("brand_new_site:card:1", P0)


def test_a_raw_policy_behind_the_router_reproduces_play_game() -> None:
    # The router consumes no randomness and adds no engine calls, so the engine's own random
    # policy routed through it plays the identical game.
    expected = play_game(3, "castable", 1409, turn_cap=10)
    game, supply = _game(3)
    policy = RandomPolicy(3)
    _play(game, SeatRouter(game, [policy, policy], _lenses(), supply=supply), game.world.player_order, 10)
    assert game.digest == expected.digest


@pytest.mark.parametrize("set_code", ["M21", "ZNR"])
def test_uniform_agents_play_whole_games_with_every_ask_routed(set_code: str) -> None:
    rng.seed_all(11, seed_frameworks=False)
    for seed in (1, 2, 3):
        game, supply = _game(seed, set_code)
        agents = [UniformRandomAgent(rng.substream("bench", seed, s)) for s in (0, 1)]
        router = SeatRouter(game, agents, _lenses(), supply=supply, strict=True)
        _play(game, router, game.world.player_order, turn_cap=30)  # strict: a misroute raises
        assert game.reason
        assert all(st["asks"] > 0 for st in router.stats)


def test_pass_agent_never_acts() -> None:
    game, supply = _game(4)
    _play(game, SeatRouter(game, [PassAgent(), PassAgent()], _lenses(), supply=supply), game.world.player_order, 12)
    assert game.acts == 0
    assert game.reason.startswith("turn cap")


def test_tap_effects_are_not_mana_abilities() -> None:
    # Regression (2026-10-24): "Tap target creature" counted as a mana ability, went out as a
    # mana activation with no target, and crashed the engine. Seed 6 reached that position.
    rng.seed_all(1, seed_frameworks=False)
    game, supply = _game(6)
    agents = [UniformRandomAgent(rng.substream("bench", 6, 0)), PassAgent()]
    _play(game, SeatRouter(game, agents, _lenses(), supply=supply), game.world.player_order, 40)
    assert game.reason


def test_a_replacement_choice_is_routed_to_the_damaged_player() -> None:
    # B-69 (2026-11-05), CR 616.1: two Nine Lives apply to damage to seat 0, so seat 0 chooses
    # which one applies; the ask is the engine's replace:<seat>:<digest> site, routed strictly.
    from MTG_bot.core.ability_tree import (
        Atom,
        AtomArgs,
        ControllerRef,
        FAnd,
        QConst,
        Selector,
        SelectorMode,
        Verb,
        Zone,
        ZoneKind,
    )
    from MTG_bot.core.executor.games import identity_of
    from MTG_bot.core.state import ZONE_BATTLEFIELD

    class Recorder:
        name = "recorder"

        def __init__(self) -> None:
            self.asks: list = []

        def decide(self, ask, obs) -> int:
            self.asks.append((ask.seat, ask.kind, [o.label for o in ask.options]))
            return len(ask.options) - 1

    game, supply = _game(3)
    world, ex = game.world, game.executor
    lives = next(r.card for r in supply.pool.results.values() if r.card.name == "Nine Lives")
    first, second = (world.add_card(identity_of(lives), P0, ZONE_BATTLEFIELD) for _ in range(2))
    for handle in (first, second):
        ex.attach_card(handle, lives)
    dealer = world.add_card(identity_of(lives), P1, ZONE_BATTLEFIELD)
    drivers = [Recorder(), Recorder()]
    router = SeatRouter(game, drivers, _lenses(), supply=supply, strict=True)
    ex.decisions.provider = router.answer
    target = Selector(
        QConst(1), SelectorMode.TARGET, FAnd(()), zones=(Zone(ZoneKind.ANY, ControllerRef.ANY),)
    )
    ex.execute(
        Atom(verb=Verb.DEAL_DAMAGE, args=AtomArgs(pairs=(("amount", QConst(3)), ("target", target)))),
        source=dealer,
        controller=P1,
        bindings={"target": P0},
    )
    assert drivers[1].asks == []
    assert [(seat, kind) for seat, kind, _labels in drivers[0].asks] == [(0, "replace")]
    assert all("Nine Lives" in label for label in drivers[0].asks[0][2])
    assert world.players[P0].life == 20
    assert world.cards[first].counters == {} and world.cards[second].counters == {"INCARNATION": 1}


# --------------------------------------------------------------- arranged boards (2026-11-05)


class _Picker:
    """Answers every ask with the first of its ``prefer`` tokens that is offered, else option 0."""

    name = "picker"

    def __init__(self, *prefer: object) -> None:
        self.prefer = [str(p) for p in prefer]
        self.asks: list = []

    def decide(self, ask, obs) -> int:
        self.asks.append(ask)
        tokens = [o.token for o in ask.options]
        return next((tokens.index(p) for p in self.prefer if p in tokens), 0)


def _arranged(hand0=(), field0=(), field1=(), *, life0=20, tokens0=(), pool0=None, set_code="M21"):
    """Seat 0's first main phase with exactly the named cards of ``set_code`` in hand and on the
    battlefields (``tokens0``: token names, e.g. Treasure, on seat 0's battlefield; ``pool0``:
    floating mana). Libraries hold Islands."""
    supply = get_supply("castable", set_code)
    oid = {m.name: o for o, m in supply.metas.items()}
    decks = tuple(
        tuple(oid[n] for n in (*hand, *field)) + (oid["Island"],) * 20
        for hand, field in ((hand0, field0), ((), field1))
    )
    game = _setup_game(1, supply, decks)
    world = game.world
    for seat, hand, field in ((P0, hand0, field0), (P1, (), field1)):
        for h in list(world.players[seat].zone(ZONE_HAND).entries):
            world.move_to_zone(h, seat, ZONE_LIBRARY)
        for zone, names in ((ZONE_HAND, hand), (ZONE_BATTLEFIELD, field)):
            for name in names:
                h = next(c for c in world.players[seat].zone(ZONE_LIBRARY).entries
                         if world.cards[c].identity.name == name)
                world.move_to_zone(h, seat, zone)
    for name in tokens0:
        record = next(r.card for r in supply.pool.results.values() if r.card.is_token and r.card.name == name)
        world.add_card(identity_of(record), P0, ZONE_BATTLEFIELD)
    game.executor.attach_pool(supply.pool)  # registers the placed permanents, as the pack runner does
    world.players[P0].life = life0
    hand = set(world.players[P0].zone(ZONE_HAND).entries)
    game.executor.begin_turn(P0)
    for h in [c for c in world.players[P0].zone(ZONE_HAND).entries if c not in hand]:
        world.move_to_zone(h, P0, ZONE_LIBRARY)  # the turn's draw goes back: the hand is hand0
    world.players[P0].mana_pool.update(pool0 or {})
    return game, supply


def _router(game, supply, driver=None):
    router = SeatRouter(game, [driver or _Picker(), PassAgent()], _lenses(), supply=supply)
    game.executor.decisions.provider = router.answer
    return router


def _handle(game, name, seat=P0, zone=None) -> Handle:
    return next(h for h, c in game.world.cards.items()
                if c.identity.name == name and game.world.controller_of(h) == seat
                and (zone is None or game.world.zone_of(h).kind == zone))


def _menu(router, game) -> dict:
    return {option.token: (option, payload) for option, payload in router._act_menu(game, P0, 0)}


def _play_row(router, game, token) -> None:
    option, payload = _menu(router, game)[token]
    router._execute(game, P0, 0, option, payload)


def test_a_cast_taps_only_the_lands_it_needs() -> None:
    # 2026-11-05: casting paid only from the pool, so the menu offered TAP_ALL_MANA, which tapped
    # every mana ability, creatures included (they could then not attack or block). Now a cast is
    # offered when the pool plus untapped free sources pay it, and choosing it taps what it needs.
    game, supply = _arranged(
        hand0=("Rousing Read",),
        field0=("Island", "Island", "Island", "Mountain", "Walking Corpse", "Llanowar Visionary"),
    )
    corpse, visionary = _handle(game, "Walking Corpse"), _handle(game, "Llanowar Visionary")
    router = _router(game, supply, _Picker(corpse))
    menu = _menu(router, game)
    read = _handle(game, "Rousing Read")
    assert "TAP_ALL_MANA" not in menu
    assert f"cast:{read}" in menu
    assert f"act:{visionary}:1" in menu  # a creature's mana ability is its own row
    assert not any(t.startswith("act:") and t != f"act:{visionary}:1" for t in menu)  # lands: none
    _play_row(router, game, f"cast:{read}")
    world = game.world
    lands = [h for h in world.players[P0].zone(ZONE_BATTLEFIELD).entries if "Land" in world.cards[h].identity.type_line]
    assert sum(world.cards[h].tapped for h in lands) == 3
    assert not world.cards[visionary].tapped
    assert world.players[P0].mana_pool == {}


def test_creature_treasure_and_filter_mana_are_rows_never_paid_automatically() -> None:
    game, supply = _arranged(
        hand0=("Fierce Empath",),
        field0=("Forest", "Forest", "Forest", "Llanowar Visionary", "Prismite"),
        tokens0=("Treasure",),
    )
    visionary, prismite = _handle(game, "Llanowar Visionary"), _handle(game, "Prismite")
    treasure = _handle(game, "Treasure")
    router = _router(game, supply)
    menu = _menu(router, game)
    assert {f"act:{visionary}:1", f"act:{prismite}:0", f"act:{treasure}:0"} <= set(menu)
    _play_row(router, game, f"cast:{_handle(game, 'Fierce Empath')}")
    world = game.world
    assert world.zone_of(treasure).kind == ZONE_BATTLEFIELD  # not sacrificed to pay
    assert not world.cards[visionary].tapped
    # the Treasure's row adds its mana to the pool when chosen
    _play_row(router, game, f"act:{treasure}:0")
    assert sum(world.players[P0].mana_pool.values()) == 1


def test_an_ability_never_taps_its_own_source_for_mana() -> None:
    # Animal Sanctuary: "{T}: Add {C}." and "{2}, {T}: Put a +1/+1 counter on target Bird, Cat,
    # Dog, Goat, Ox, or Snake." The {2} comes from the other lands, never from the Sanctuary.
    game, supply = _arranged(field0=("Animal Sanctuary", "Plains", "Plains", "Alpine Watchdog"))
    sanctuary = _handle(game, "Animal Sanctuary")
    router = _router(game, supply)
    menu = _menu(router, game)
    assert f"act:{sanctuary}:1" in menu
    _play_row(router, game, f"act:{sanctuary}:1")
    assert game.world.cards[_handle(game, "Alpine Watchdog")].counters.get("PLUS_1_PLUS_1") == 1


def test_x_spells_offer_one_row_per_payable_x() -> None:
    # X was always declared 0: Volcanic Geyser dealt 0, Wildwood Scourge died as a 0/0.
    game, supply = _arranged(
        hand0=("Volcanic Geyser",), field0=("Mountain", "Mountain", "Island", "Island", "Island")
    )
    geyser = _handle(game, "Volcanic Geyser")
    router = _router(game, supply, _Picker(P1))
    menu = _menu(router, game)
    assert [t for t in menu if t == f"cast:{geyser}" or t.startswith(f"cast:{geyser}:")] == [
        f"cast:{geyser}", f"cast:{geyser}:x1", f"cast:{geyser}:x2", f"cast:{geyser}:x3"
    ]
    _play_row(router, game, f"cast:{geyser}:x3")
    assert game.world.players[P1].life == 17


def test_an_x_creature_enters_with_the_chosen_x() -> None:
    game, supply = _arranged(hand0=("Wildwood Scourge",), field0=("Forest", "Forest", "Forest"))
    scourge = _handle(game, "Wildwood Scourge")
    router = _router(game, supply)
    assert f"cast:{scourge}:x2" in _menu(router, game)
    _play_row(router, game, f"cast:{scourge}:x2")
    assert game.world.zone_of(scourge).kind == ZONE_BATTLEFIELD
    assert game.world.cards[scourge].counters.get("PLUS_1_PLUS_1") == 2


def test_a_target_whose_cost_increase_is_unpayable_is_never_offered() -> None:
    # CR 601.2f-h: Pursued Whale makes an opponent's spell that targets it cost {3} more. The menu
    # offered the target, the cast raised, and the game was voided (deal 900039 voided every eval).
    game, supply = _arranged(
        hand0=("Rousing Read",), field0=("Walking Corpse",), field1=("Pursued Whale",), pool0={"U": 3}
    )
    whale, corpse = _handle(game, "Pursued Whale", P1), _handle(game, "Walking Corpse")
    picker = _Picker(whale)
    router = _router(game, supply, picker)
    _play_row(router, game, f"cast:{_handle(game, 'Rousing Read')}")
    offered = [o.token for o in picker.asks[0].options] if picker.asks else []
    assert str(whale) not in offered
    assert game.executor.attachments.get(_handle(game, "Rousing Read", zone=ZONE_BATTLEFIELD)) == corpse


def test_a_target_is_offered_when_its_cost_increase_is_payable() -> None:
    game, supply = _arranged(
        hand0=("Rousing Read",), field0=("Walking Corpse",), field1=("Pursued Whale",), pool0={"U": 6}
    )
    whale = _handle(game, "Pursued Whale", P1)
    picker = _Picker(whale)
    router = _router(game, supply, picker)
    _play_row(router, game, f"cast:{_handle(game, 'Rousing Read')}")
    assert str(whale) in [o.token for o in picker.asks[0].options]
    assert game.executor.attachments.get(_handle(game, "Rousing Read", zone=ZONE_BATTLEFIELD)) == whale


def test_a_spell_whose_only_target_is_unpayable_is_not_offered() -> None:
    game, supply = _arranged(hand0=("Rousing Read",), field1=("Pursued Whale",), pool0={"U": 3})
    assert f"cast:{_handle(game, 'Rousing Read')}" not in _menu(_router(game, supply), game)


def test_life_is_paid_only_up_to_the_life_total() -> None:
    # Terror of the Peaks: an opponent's spell that targets it costs an additional 3 life, and a
    # player can pay life only up to their life total (CR 119.4). An aura's enchant target was
    # never priced at all (query.spell_target_slots returned the aura slot early).
    game, supply = _arranged(
        hand0=("Rousing Read",), field0=("Walking Corpse",), field1=("Terror of the Peaks",), life0=2, pool0={"U": 3}
    )
    terror, corpse = _handle(game, "Terror of the Peaks", P1), _handle(game, "Walking Corpse")
    picker = _Picker(terror)
    router = _router(game, supply, picker)
    _play_row(router, game, f"cast:{_handle(game, 'Rousing Read')}")
    assert all(str(terror) not in [o.token for o in ask.options] for ask in picker.asks)
    assert game.executor.attachments.get(_handle(game, "Rousing Read", zone=ZONE_BATTLEFIELD)) == corpse
    assert game.world.players[P0].life == 2


def test_a_modal_spell_keeps_its_targeted_modes_under_a_target_tax() -> None:
    # Review 2026-11-05: a modal spell's mode sets were priced against the pool alone, which is
    # empty when the act window opens, so with a Pursued Whale anywhere on the battlefield every
    # targeted mode was dropped and Return to Nature was not offered at all.
    game, supply = _arranged(hand0=("Return to Nature",), field0=("Forest",) * 3, field1=("Meteorite", "Pursued Whale"))
    rtn = _handle(game, "Return to Nature")
    router = _router(game, supply)
    assert f"cast:{rtn}" in _menu(router, game)
    _play_row(router, game, f"cast:{rtn}")  # the one legal mode: destroy target artifact
    assert game.world.zone_of(_handle(game, "Meteorite", P1)).kind == "graveyard"


def test_a_dealt_game_names_cards_from_its_pool_so_name_asks_are_not_leaky() -> None:
    # B-29: the CHOOSE_NAME vocabulary listed the world's cards, hidden zones included, so the
    # router flagged every name ask leaky. A dealt game now lists the format's card pool.
    game, supply = _game(3)
    picker = _Picker()
    router = _router(game, supply, picker)
    source = game.world.players[P0].zone(ZONE_HAND).entries[0]
    game.executor.apply_effect(Atom(verb=Verb.CHOOSE_NAME, args=AtomArgs(pairs=())), source=source, controller=P0)
    (ask,) = picker.asks
    assert ask.kind == "name" and not ask.leaky
    assert router.stats[0]["leaky_asks"] == 0
    assert [o.token for o in ask.options] == sorted({supply.metas[o].name for o in supply.deckable})


def test_the_second_main_phase_has_its_own_act_window() -> None:
    # B-74 (2026-11-06), CR 505.1, 305.2: after combat the active player gets a second act window,
    # where a land not played before combat can still be played, and the prompt says which main
    # phase it is. On main d0200d2 nothing was offered after combat.
    game, supply = _arranged(hand0=("Forest",), field0=("Walking Corpse",))
    forest = _handle(game, "Forest", zone=ZONE_HAND)
    picker = _Picker("DECLINE", f"land:{forest}")
    router = _router(game, supply, picker)
    assert f"land:{forest}" in _menu(router, game)
    game.executor.combat_step(P0)  # declines the attack: the land is still unplayed
    assert game.executor.phase == "SECOND_MAIN"
    router.take_acts(game, P0)
    assert game.world.zone_of(forest).kind == ZONE_BATTLEFIELD
    act = next(ask for ask in picker.asks if ask.kind == "act")
    assert act.prompt.startswith("Your second main phase")
