"""The latent-fault guard (KNOWLEDGE/2026-11-18/215 §5 W0, §7): which cards of the three verified
deal pools hold the shape of each open engine fault (``fault_shapes``), as assertions.

- **LATENT**: no dealt card holds the shape, so the fault cannot reach a training game. A wave that
  stamps a card holding it turns this red, and that fault's fix becomes the wave's merge condition.
- **PINNED**: the cards that hold the shape today, by pool: the carriers of a reachable fault (the
  entry goes when its wave closes the fault), or a latent fault's carriers that 215 judged unable
  to reach it (a new carrier must be judged again). A card joining or leaving turns it red: update
  the pin, with the reason in the commit.

One entry per fault, named by its 215 id, so a wave that closes a fault deletes its entry.
Assumes one set per game (``tools/selfplay/learner.py`` deals ``job["set_code"]``): mixed-set
games would need the union of the pools. A shape the functions do not encode is not guarded
(215 §3: the text census, the packs, the verifiers and the soak are the other nets).
"""

from __future__ import annotations

import dataclasses
import sys
from functools import cache
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import fault_shapes as fs

from MTG_bot.core import ability_tree as at
from MTG_bot.core.executor.games import get_supply

POOLS = ("M21", "M20", "FDN")


@cache
def pools() -> dict[str, tuple]:
    """The compiled cards each verified deal pool deals, compiled once per run."""
    out = {}
    for code in POOLS:
        supply = get_supply("verified", code)
        out[code] = tuple(supply.pool.results[oid].card for oid in supply.deckable)
    return out


def holders(shape: fs.Shape, cards: tuple | list) -> set[str]:
    return set(shape(list(cards)))


#: No dealt card holds these shapes.
LATENT: dict[str, fs.Shape] = {
    "F04": fs.each(fs.f04),
    "F10d": fs.each(fs.f10d),
    "F11": fs.each(fs.f11),
    "F17": fs.each(fs.f17),
    "F18d": fs.each(lambda c: fs.multi_slot_trigger(c, with_choose=True)),
    "F29": fs.f29_shape,
    "F35": fs.f35_life,
    "F38": fs.each(fs.f38_carrier),
    "F46": fs.each(fs.f46),
    "F53": fs.each(fs.f53),
    "F56": fs.each(fs.f56),
    "F57": fs.each(fs.f57),
    "F61": fs.each(fs.f61),
}

#: The cards holding these shapes today, per pool (M21, M20, FDN).
PINNED: dict[str, tuple[fs.Shape, tuple[set[str], set[str], set[str]]]] = {
    # reachable and wrong today (215 §4 R rows), or reaching the network
    "F13": (fs.each(fs.f13_carrier), ({"Enthralling Hold"}, set(), set())),
    "F18b": (fs.each(fs.multi_slot_trigger), (set(), {"Drakuseth, Maw of Flames"}, {"Drakuseth, Maw of Flames"})),
    "F19": (fs.each(fs.f19_carrier), ({"Runed Halo"}, {"Veil of Summer"}, set())),
    "F27 self-damage": (fs.each(fs.f27_self_damage), (
        {"Chandra's Magmutt", "Chandra, Flame's Catalyst", "Keral Keep Disciples", "Leafkin Avenger", "Storm Caller",
         "Turret Ogre"},
        {"Cavalier of Flame", "Chandra's Outrage", "Chandra, Flame's Fury", "Pyroclastic Elemental"},
        {"Boltwave", "Boros Charm", "Firebrand Archer", "Firespitter Whelp", "Guttersnipe", "Impact Tremors",
         "Midnight Reaper", "Mindsparker", "Slagstorm", "Spitfire Lagac"})),
    "F27 lifelink": (fs.each(fs.f27_lifelink), (
        {"Alchemist's Gift", "Anointed Chorister", "Archfiend's Vessel", "Baneslayer Angel", "Basri's Acolyte",
         "Blood Glutton", "Indulging Patrician", "Mangara, the Diplomat", "Sigiled Contender", "Speaker of the Heavens",
         "Vito, Thorn of the Dusk Rose"},
        {"Blood Burglar", "Cavalier of Night", "Daybreak Chaplain", "Moment of Heroism", "Sorin, Imperious Bloodlord",
         "Tomebound Lich", "Vampire of the Dire Moon"},
        {"Bishop's Soldier", "Crossway Troublemakers", "Drogskol Reaver", "Felidar Savior", "Guarded Heir",
         "Healer's Hawk", "Nullpriest of Oblivion", "Regal Caracal", "Unflinching Courage", "Vampire Nighthawk"})),
    "F43": (fs.each(fs.f43_carrier), (
        {"Chandra, Flame's Catalyst", "Crypt Lurker", "Dire Fleet Warmonger", "Experimental Overload",
         "Ghostly Pilferer", "Liliana's Devotee", "Niambi, Esteemed Speaker", "Tolarian Kraken"},
        {"Boneclad Necromancer", "Cavalier of Night", "Cavalier of Thorns", "Gravedigger", "Keldon Raider",
         "Riddlemaster Sphinx", "Risen Reef", "Sorin, Imperious Bloodlord",
         "Chandra's Regulator"},  # its "you may pay {1}" (verified 2026-11-18, wave 7)
        {"Crossway Troublemakers", "High-Society Hunter", "Incinerating Blast", "Spinner of Souls"})),
    # latent: the carriers 215 judged unable to reach the fault (§4's reasons)
    # F14c's residue after W1: an Aura flickered in one resolution loses its new attachment
    "F14c": (fs.each(fs.f14c_carrier), ({"Transmogrify"}, set(), set())),  # returns another card, not the exiled one
    "F31": (fs.each(fs.f31_carrier), ({"Idol of Endurance"}, {"Bag of Holding"}, set())),
    # See the Truth: a resolving look, so the window it writes names cards its player does look at
    "F36": (fs.each(fs.f36_carrier), ({"Radha, Heart of Keld", "See the Truth"},
                                      {"Diviner's Lockbox", "Goblin Ringleader", "Mystic Forge"}, set())),
    "F37": (fs.each(fs.f37_carrier), ({"Chandra, Heart of Fire", "Necromentia", "Siege Striker"},
                                      {"Cavalier of Flame"}, set())),
    "F41": (fs.each(fs.f41_carrier), ({"Teferi, Timeless Voyager"}, {"Cavalier of Gales", "Eternal Isolation"}, set())),
    "F47": (fs.each(fs.f47_carrier), (set(), set(), {"Faebloom Trick"})),  # its Conditional reads MAY_DONE
}


def drift(shape: fs.Shape, want: tuple[set[str], ...], cards_by_pool: dict) -> list[str]:
    """Each pool whose holders differ from ``want``, with the cards that joined or left."""
    out = []
    for code, expected in zip(POOLS, want, strict=True):
        got = holders(shape, cards_by_pool[code])
        if got != expected:
            out.append(f"{code}: joined {sorted(got - expected)}, left {sorted(expected - got)}")
    return out


@pytest.mark.parametrize("fault", sorted(LATENT))
def test_no_dealt_card_holds_a_latent_fault(fault: str) -> None:
    held = {code: sorted(holders(LATENT[fault], cards)) for code, cards in pools().items()}
    assert not any(held.values()), (
        f"{fault} (KNOWLEDGE/2026-11-18/215 §4) is latent, but dealt cards hold its shape: {held}. "
        "Fix the fault before the stamp, or judge the cards and pin them")


@pytest.mark.parametrize("fault", sorted(PINNED))
def test_the_carriers_of_a_fault_are_the_ones_judged(fault: str) -> None:
    shape, want = PINNED[fault]
    moved = drift(shape, want, pools())
    assert not moved, f"{fault} (KNOWLEDGE/2026-11-18/215 §4): its carriers changed: {moved}"


def test_f46_is_the_draw_lane_naming_another_players_library() -> None:
    """F46 is MOVE_ZONE's draw lane (``verbs._v_move_zone`` takes the cards from the destination's
    player's library), so "put the top two cards of target opponent's library into its owner's
    hand" holds it and "of your library into your hand" does not (the W0 review: the shape keyed
    on the mill lane, which names its library itself, and could never turn red)."""
    def mover(library: at.ControllerRef, hand: at.ControllerRef, name: str) -> at.CardRecord:
        cards = at.Selector(at.QConst(2), at.SelectorMode.CHOOSE, at.FAnd(()),
                            zones=(at.Zone(at.ZoneKind.LIBRARY, library),))
        move = at.Atom(verb=at.Verb.MOVE_ZONE, args=at.AtomArgs(pairs=(
            ("cards", cards), ("destination", at.Zone(at.ZoneKind.HAND, hand)))))
        return dataclasses.replace(pools()["M21"][0], name=name,
                                   abilities=(at.SpellAbility(kind=at.SpellKind.SORCERY, effect=move),))
    cards = [mover(at.ControllerRef.OPPONENT, at.ControllerRef.OWNER, "Synthetic Theft"),
             mover(at.ControllerRef.YOU, at.ControllerRef.YOU, "Synthetic Draw")]
    assert holders(LATENT["F46"], cards) == {"Synthetic Theft"}


def test_the_guard_turns_red_on_a_card_holding_a_latent_shape() -> None:
    """A synthetic card in the M21 pool, a Saga (F61: lore counters are not modelled), fails the
    latent entry it holds."""
    m21 = list(pools()["M21"])
    base = m21[0]
    saga = dataclasses.replace(base, name="Synthetic Saga", subtypes=(*base.subtypes, "Saga"))
    pooled = [*m21, saga]
    assert holders(LATENT["F61"], pooled) == {"Synthetic Saga"}
    # and a pinned set that gains a card says which
    assert drift(PINNED["F19"][0], PINNED["F19"][1], {"M21": pooled, "M20": pools()["M20"], "FDN": pools()["FDN"]}) == []
    halo = next(c for c in m21 if c.name == "Runed Halo")
    second = dataclasses.replace(halo, name="Synthetic Halo")
    moved = drift(PINNED["F19"][0], PINNED["F19"][1], {"M21": [*m21, second], "M20": pools()["M20"],
                                                       "FDN": pools()["FDN"]})
    assert moved == ["M21: joined ['Synthetic Halo'], left []"]
