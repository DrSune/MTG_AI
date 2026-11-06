"""Rules checks through a DEALT game (games._setup_game), the way training deals them: no card in a
hand or library has a bound record until it is cast, played or enters. The scenario-pack runner
binds every placed card, so packs cannot see this path."""

from __future__ import annotations

import dataclasses

from MTG_bot.core.ability_tree import (
    Atom, AtomArgs, ControllerRef, FAnd, QConst, Selector, SelectorMode, TokenSpec, Verb, Zone, ZoneKind, walk,
)
from MTG_bot.core.executor.games import DECK_SIZE, _setup_game, get_supply
from MTG_bot.core.executor.legality import spell_castable
from MTG_bot.core.executor.stack import cast
from MTG_bot.core.state import ZONE_BATTLEFIELD, ZONE_GRAVEYARD, ZONE_HAND, ZONE_LIBRARY

UNIV = FAnd(())


def atom(verb, **roles):
    return Atom(verb=verb, args=AtomArgs(pairs=tuple(roles.items())))


class G:
    """One dealt game: deck0/deck1 are card names (filled with ``filler``)."""

    def __init__(self, set_code, deck0, deck1=(), seed=7, filler="Island", filler1=None, mode="verified"):
        self.sup = get_supply(mode, set_code)
        self.oid = {m.name: o for o, m in self.sup.metas.items()}
        d0 = tuple(self.oid[n] for n in deck0)
        d1 = tuple(self.oid[n] for n in deck1)
        f0 = self.oid[filler]
        f1 = self.oid[filler1 or filler]
        self.game = _setup_game(seed, self.sup, (d0 + (f0,) * (DECK_SIZE - len(d0)),
                                                 d1 + (f1,) * (DECK_SIZE - len(d1))))
        self.world, self.ex = self.game.world, self.game.executor
        self.p0, self.p1 = self.world.player_order
        self.asks = []
        self.answers = {}
        self.ex.decisions.provider = self._answer

    def _answer(self, vocab, what):
        self.asks.append((what, vocab))
        for key, ans in self.answers.items():
            if key in what:
                if callable(ans):
                    return ans(vocab, what)
                if ans in vocab:
                    return ans
        # default: decline optional / first word
        for w in ("skip", "DECLINE", "NONE", "no"):
            if w in vocab:
                return w
        return vocab[0]

    def cards(self, seat, name, zone=None):
        out = [h for h in sorted(self.world.cards, key=lambda h: h.index)
               if self.world.controller_of(h) == seat and self.world.cards[h].identity.name == name
               and (zone is None or self.world.zone_of(h).kind == zone)]
        return out

    def one(self, seat, name, zone=None, skip=()):
        for h in self.cards(seat, name, zone):
            if h not in skip:
                return h
        raise KeyError((seat, name, zone))

    def to_hand(self, h):
        seat = self.world.controller_of(h)
        self.world.move_to_zone(h, seat, ZONE_HAND)  # dealt into hand: unbound, as in a game

    def to_library_top(self, h):
        seat = self.world.controller_of(h)
        lib = self.world.players[seat].zone(ZONE_LIBRARY).entries
        if h in lib:
            lib.remove(h)
            lib.append(h)  # library[-1] is the top (router reads library[-1 - k])
        else:
            self.world.move_to_zone(h, seat, ZONE_LIBRARY)

    def enter(self, h, seat=None):
        """Put onto the battlefield by an effect (journalled MOVE_ZONE; binds on entry)."""
        seat = seat or self.world.controller_of(h)
        self.ex.apply_effect(
            atom(Verb.MOVE_ZONE,
                 target=Selector(QConst(1), SelectorMode.CHOOSE, UNIV,
                                 zones=(Zone(ZoneKind.ANY, ControllerRef.ANY),), referent="result"),
                 destination=Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU)),
            source=seat, controller=seat, bindings={"result": [h]})

    def zone(self, h):
        return self.world.zone_of(h).kind

    def hand(self, seat):
        return list(self.world.players[seat].zone(ZONE_HAND).entries)


def _pool(g, seat, **mana):
    g.world.players[seat].mana_pool.clear()
    g.world.players[seat].mana_pool.update(mana)


def test_warden_in_a_dealt_hand_pays_full_cost_and_a_battlefield_warden_discounts_once() -> None:
    g = G("M20", ("Warden of Evos Isle", "Warden of Evos Isle"), mode="compiled")
    w1, w2 = g.cards(g.p0, "Warden of Evos Isle", ZONE_LIBRARY)[:2]
    g.to_hand(w2)
    g.ex.begin_turn(g.p0)
    _pool(g, g.p0, U=1, C=1)
    reason = spell_castable(g.ex, g.p0, w2)[0]
    assert reason is not None, "a Warden in hand must not discount itself ({2}{U} with two mana)"
    g.enter(w1)
    _pool(g, g.p0, U=1, C=1)
    assert spell_castable(g.ex, g.p0, w2)[0] is None, "one Warden on the battlefield: {1}{U}"
    _pool(g, g.p0, U=1)
    assert spell_castable(g.ex, g.p0, w2)[0] is not None, "never a double discount ({U} alone)"


def test_stormwing_entity_in_a_dealt_hand_after_an_instant() -> None:
    from MTG_bot.core.executor.stack import cast
    g = G("M21", ("Stormwing Entity", "Shock"), filler="Island", filler1="Mountain")
    st = g.one(g.p0, "Stormwing Entity", ZONE_LIBRARY)
    shock = g.one(g.p0, "Shock", ZONE_LIBRARY)
    g.to_hand(st)
    g.to_hand(shock)
    g.ex.begin_turn(g.p0)
    _pool(g, g.p0, U=1, C=1)
    assert spell_castable(g.ex, g.p0, st)[0] is not None, "no instant cast yet: {3}{U}{U}"
    _pool(g, g.p0, R=1)
    cast(g.ex, g.p0, shock, targets=(g.p1,))
    _pool(g, g.p0, U=1, C=1)
    assert spell_castable(g.ex, g.p0, st)[0] is None, "after an instant: {1}{U}"


def test_chandras_incinerator_in_a_dealt_hand_after_noncombat_damage() -> None:
    from MTG_bot.core.executor.stack import cast
    g = G("M21", ("Chandra's Incinerator", "Shock"), filler="Mountain")
    inc = g.one(g.p0, "Chandra's Incinerator", ZONE_LIBRARY)
    shock = g.one(g.p0, "Shock", ZONE_LIBRARY)
    g.to_hand(inc)
    g.to_hand(shock)
    g.ex.begin_turn(g.p0)
    _pool(g, g.p0, R=1)
    cast(g.ex, g.p0, shock, targets=(g.p1,))
    _pool(g, g.p0, R=1, C=3)
    assert spell_castable(g.ex, g.p0, inc)[0] is None, "{5}{R} minus 2 noncombat damage = {3}{R}"
    _pool(g, g.p0, R=1, C=2)
    assert spell_castable(g.ex, g.p0, inc)[0] is not None, "never more than X less"


def test_gain_land_from_library_enters_tapped_and_gains_life() -> None:
    g = G("M21", ("Bloodfell Caves",))
    caves = g.one(g.p0, "Bloodfell Caves", ZONE_LIBRARY)
    g.ex.begin_turn(g.p0)
    life = g.world.players[g.p0].life
    g.enter(caves)
    assert g.zone(caves) == ZONE_BATTLEFIELD
    assert g.world.cards[caves].tapped, "enters tapped (EtBState)"
    assert g.world.players[g.p0].life == life + 1, "its ETB 'you gain 1 life' must trigger"


def test_temple_from_library_scries() -> None:
    g = G("M21", ("Temple of Triumph",))
    temple = g.one(g.p0, "Temple of Triumph", ZONE_LIBRARY)
    g.ex.begin_turn(g.p0)
    g.enter(temple)
    assert g.world.cards[temple].tapped
    assert any("scry" in what for what, _ in g.asks), g.asks


def test_lotus_field_from_library_sacrifices_two_lands() -> None:
    g = G("M20", ("Lotus Field", "Island", "Island", "Island"))
    lotus = g.one(g.p0, "Lotus Field", ZONE_LIBRARY)
    islands = [h for h in g.cards(g.p0, "Island", ZONE_LIBRARY)][:3]
    g.ex.begin_turn(g.p0)
    for h in islands:
        g.enter(h)
    # 'sacrifice two lands' (current Oracle): answer with Islands, never Lotus Field itself
    g.answers["sacrifice"] = lambda vocab, what: next(w for w in vocab if w != str(lotus))
    g.enter(lotus)
    on_bf = [h for h in islands if g.zone(h) == ZONE_BATTLEFIELD]
    assert len(on_bf) == 1, f"Lotus Field's ETB must sacrifice two lands: {len(on_bf)} Islands left"
    assert g.zone(lotus) == ZONE_BATTLEFIELD and g.world.cards[lotus].tapped


def test_discarded_creature_reanimated_has_its_abilities() -> None:
    # A creature that was never cast (discarded / milled), returned by an effect.
    g = G("M21", ("Sporeweb Weaver",))
    w = g.one(g.p0, "Sporeweb Weaver", ZONE_LIBRARY)
    g.world.move_to_zone(w, g.p0, ZONE_GRAVEYARD)  # milled: unbound
    g.ex.begin_turn(g.p0)
    g.enter(w)
    assert w in g.ex.binder.handle_record
    # reach + hexproof-from-blue rows live
    from MTG_bot.core.ability_tree import Keyword
    assert g.ex.layers.keyword_of(w, Keyword.REACH)


def test_weaver_cast_from_a_dealt_hand_keeps_hexproof_from_blue() -> None:
    g = G("M21", ("Unsubstantiate", "Shock"), ("Sporeweb Weaver",), filler="Island", filler1="Forest")
    weaver = g.one(g.p1, "Sporeweb Weaver", ZONE_LIBRARY)
    g.to_hand(weaver)
    uns = g.one(g.p0, "Unsubstantiate", ZONE_LIBRARY)
    shock = g.one(g.p0, "Shock", ZONE_LIBRARY)
    g.to_hand(uns)
    g.to_hand(shock)
    g.ex.begin_turn(g.p1)
    _pool(g, g.p1, G=1, C=2)
    cast(g.ex, g.p1, weaver)
    assert g.zone(weaver) == ZONE_BATTLEFIELD
    g.ex.end_turn()
    g.ex.advance_turn()
    assert g.world.active_player == g.p0
    _pool(g, g.p0, U=1, C=1)
    with __import__("pytest").raises(Exception):
        cast(g.ex, g.p0, uns, targets=(weaver,))  # blue: hexproof from blue
    assert g.zone(weaver) == ZONE_BATTLEFIELD
    _pool(g, g.p0, R=1)
    cast(g.ex, g.p0, shock, targets=(weaver,))  # red: legal target
    assert g.ex.damage.get(weaver, 0) == 2 or g.zone(weaver) != ZONE_BATTLEFIELD


def _whale_pirate(g):
    rec = g.sup.pool.cards[g.oid["Pursued Whale"]]
    return next(n for n in walk(rec) if isinstance(n, TokenSpec))


def test_vanilla_token_does_not_inherit_a_same_named_tokens_abilities() -> None:
    g = G("M21", ())
    g.ex.begin_turn(g.p0)
    pirate = _whale_pirate(g)
    assert pirate.abilities, "the Whale's Pirate has 'can't block' and the attack mandate"
    vanilla = dataclasses.replace(pirate, abilities=())  # e.g. another card's plain 1/1 Pirate
    g.ex.apply_effect(atom(Verb.CREATE_TOKEN, tokens=pirate, count=QConst(1)), source=g.p1, controller=g.p1)
    g.ex.apply_effect(atom(Verb.CREATE_TOKEN, tokens=vanilla, count=QConst(1)), source=g.p0, controller=g.p0)
    mine = g.cards(g.p0, "Pirate")
    assert len(mine) == 1
    rec = g.ex.binder.handle_record.get(mine[0])
    assert rec is None or not rec.abilities, (
        f"the vanilla Pirate picked up {len(rec.abilities)} abilities of the Whale's Pirate")


def _countered_through_permission(g, permission, spell, mana) -> None:
    """Activate ``permission``'s cast row (index 1) and fire it; the opponent, holding Cancel and
    {U}{U}{U}, answers the counter window with it. A spell cast through a permission is cast like
    one from hand, so it gets the same window (CR 601.2i, 117.3c, 608.1)."""
    from MTG_bot.core.executor.legality import activate

    cancel = g.one(g.p1, "Cancel", ZONE_LIBRARY)
    g.to_hand(cancel)
    _pool(g, g.p0, **mana)
    _pool(g, g.p1, U=3)
    g.answers = {"may:": "fire", "counter:": str(cancel)}
    activate(g.ex, permission, 1, seat=g.p0)
    assert any(what.startswith(f"counter:{g.p1}:") for what, _ in g.asks), g.asks
    assert g.zone(spell) == ZONE_GRAVEYARD, "countered: into its owner's graveyard (CR 400.7)"
    assert g.zone(cancel) == ZONE_GRAVEYARD


def test_idol_of_endurance_cast_can_be_countered() -> None:
    from MTG_bot.core.state import ZONE_EXILE

    g = G("M21", ("Idol of Endurance", "Walking Corpse"), ("Cancel",), filler="Plains", filler1="Island")
    idol = g.one(g.p0, "Idol of Endurance", ZONE_LIBRARY)
    corpse = g.one(g.p0, "Walking Corpse", ZONE_LIBRARY)
    g.world.move_to_zone(corpse, g.p0, ZONE_GRAVEYARD)
    g.ex.begin_turn(g.p0)
    g.enter(idol)
    assert g.zone(corpse) == ZONE_EXILE, "its enter trigger exiles the Corpse with the Idol"
    _countered_through_permission(g, idol, corpse, {"W": 1, "C": 1})


def test_conspicuous_snoop_cast_from_the_top_can_be_countered() -> None:
    g = G("M21", ("Conspicuous Snoop", "Goblin Arsonist"), ("Cancel",), filler="Mountain",
          filler1="Island")
    snoop = g.one(g.p0, "Conspicuous Snoop", ZONE_LIBRARY)
    goblin = g.one(g.p0, "Goblin Arsonist", ZONE_LIBRARY)
    g.ex.begin_turn(g.p0)
    g.enter(snoop)
    g.to_library_top(goblin)  # unbound, as a dealt library card is
    _countered_through_permission(g, snoop, goblin, {"R": 1})


def test_a_dealt_game_taps_colourless_for_generic_and_keeps_the_swamp() -> None:
    # The router's payment (bench/router.py): plan the free sources, tap them, cast. {1}{B} for
    # Masked Blackguard from two Swamps and Radiant Fountain ({T}: Add {C}) must tap the Fountain
    # for the {1} (colourless pays no coloured symbol, CR 106.1b), so Duress's {B} stays payable.
    from MTG_bot.core.executor.legality import plan_mana_taps, tap_for_payment

    g = G("M21", ("Masked Blackguard", "Duress", "Swamp", "Swamp", "Radiant Fountain"))
    s1, s2 = g.cards(g.p0, "Swamp", ZONE_LIBRARY)
    fountain = g.one(g.p0, "Radiant Fountain", ZONE_LIBRARY)
    assert s1 < s2 < fountain, "the order in which the old tie-break tapped a Swamp for the {1}"
    blackguard = g.one(g.p0, "Masked Blackguard", ZONE_LIBRARY)
    duress = g.one(g.p0, "Duress", ZONE_LIBRARY)
    g.to_hand(blackguard)
    g.to_hand(duress)
    g.ex.begin_turn(g.p0)
    for land in (s1, s2, fountain):
        g.enter(land)
    taps = plan_mana_taps(g.ex, g.p0, lambda: spell_castable(g.ex, g.p0, blackguard)[0])
    assert taps is not None
    tap_for_payment(g.ex, g.p0, taps)
    cast(g.ex, g.p0, blackguard)
    assert g.zone(blackguard) == ZONE_BATTLEFIELD
    assert g.world.cards[fountain].tapped, "the Fountain pays the generic {1}"
    pay = lambda: spell_castable(g.ex, g.p0, duress, targets=(g.p1,))[0]
    assert plan_mana_taps(g.ex, g.p0, pay) is not None, "a Swamp is left for Duress's {B}"
