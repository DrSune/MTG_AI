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
    "F40": fs.f40_shape,
    "F46": fs.each(fs.f46),
    "F53": fs.each(fs.f53),
    "F56": fs.each(fs.f56),
    "F57": fs.each(fs.f57),
    "F60": fs.each(fs.copies),
    "F61": fs.each(fs.f61),
}

#: The cards holding these shapes today, per pool (M21, M20, FDN).
PINNED: dict[str, tuple[fs.Shape, tuple[set[str], set[str], set[str]]]] = {
    # reachable and wrong today (215 §4 R rows), or reaching the network
    "F13": (fs.each(fs.f13_carrier), ({"Enthralling Hold"}, set(), set())),
    "F18b": (fs.each(fs.multi_slot_trigger), (set(), {"Drakuseth, Maw of Flames"}, {"Drakuseth, Maw of Flames"})),
    "F19": (fs.each(fs.f19_carrier), ({"Runed Halo"}, {"Veil of Summer"}, set())),
    "F23": (fs.each(fs.f23_carrier), ({"Mazemind Tome", "Nine Lives"}, set(), {"Mazemind Tome"})),
    "F24": (fs.each(lambda c: any(True for _ in fs.atoms(c, at.Verb.TRIGGER_ADDITIONAL))),
            ({"Sanctum of All"}, set(), set())),
    "F27 self-damage": (fs.each(fs.f27_self_damage), (
        {"Chandra's Magmutt", "Chandra, Flame's Catalyst", "Keral Keep Disciples", "Leafkin Avenger", "Storm Caller",
         "Turret Ogre"},
        {"Cavalier of Flame", "Chandra's Flame Wave", "Chandra's Outrage", "Chandra, Flame's Fury", "Pyroclastic Elemental"},
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
         "Garruk's Harbinger", "Ghostly Pilferer", "Liliana's Devotee", "Niambi, Esteemed Speaker", "Tolarian Kraken"},
        {"Boneclad Necromancer", "Brightwood Tracker", "Cavalier of Night", "Cavalier of Thorns", "Gravedigger",
         "Icon of Ancestry", "Keldon Raider", "Riddlemaster Sphinx", "Risen Reef", "Sorin, Imperious Bloodlord"},
        {"Crossway Troublemakers", "High-Society Hunter", "Incinerating Blast", "Spinner of Souls", "Vivien Reid"})),
    "F63": (fs.each(fs.f63_carrier), (
        {"Alpine Houndmaster", "Basri's Aegis", "Chandra's Firemaw", "Cultivate", "Duress", "Fierce Empath",
         "Garruk's Harbinger", "Garruk's Warsteed", "Garruk, Savage Herald", "Kitesail Freebooter", "Liliana's Scorn",
         "Teferi's Wavecaster", "Track Down", "Transmogrify"},
        {"Battalion Foot Soldier", "Brightwood Tracker", "Cavalier of Thorns", "Chandra's Flame Wave",
         "Diviner's Lockbox", "Duress", "Ethereal Elk", "Goblin Ringleader", "Goldmane Griffin", "Icon of Ancestry",
         "Sorin's Guide", "Thought Distortion", "Vivien, Nature's Avenger", "Yanling's Harbinger"},
        {"Duress", "Fierce Empath", "Pilfer", "Spinner of Souls", "Vivien Reid"})),
    # latent: the carriers 215 judged unable to reach the fault (§4's reasons)
    # F14c's residue after W1: an Aura flickered in one resolution loses its new attachment
    "F14c": (fs.each(fs.f14c_carrier), ({"Transmogrify"}, set(), set())),  # returns another card, not the exiled one
    "F31": (fs.each(fs.f31_carrier), ({"Idol of Endurance"}, {"Bag of Holding"}, set())),
    "F36": (fs.each(fs.f36_carrier), ({"Radha, Heart of Keld"}, {"Diviner's Lockbox", "Goblin Ringleader", "Mystic Forge"},
                                      set())),
    "F37": (fs.each(fs.f37_carrier), ({"Chandra, Heart of Fire", "Necromentia", "Siege Striker"},
                                      {"Battalion Foot Soldier", "Cavalier of Flame"}, set())),
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


def test_the_guard_turns_red_on_a_card_holding_a_latent_shape() -> None:
    """A synthetic card in the M21 pool: a Saga (F61, lore counters are not modelled) and a copy
    effect beside a card that chooses as it enters (F60, F40). Each latent entry it holds fails."""
    m21 = list(pools()["M21"])
    base = m21[0]
    saga = dataclasses.replace(base, name="Synthetic Saga", subtypes=(*base.subtypes, "Saga"))
    permanent = at.Selector(at.QConst(1), at.SelectorMode.TARGET, at.FAnd(()),
                            zones=(at.Zone(at.ZoneKind.BATTLEFIELD, at.ControllerRef.ANY),))
    copy = at.Atom(verb=at.Verb.CREATE_TOKEN,  # "create a token that's a copy of target permanent"
                   args=at.AtomArgs(pairs=(("count", at.QConst(1)), ("tokens", at.CopyOf(permanent)))))
    copier = dataclasses.replace(base, name="Synthetic Copier",
                                 abilities=(at.SpellAbility(kind=at.SpellKind.SORCERY, effect=copy),))
    pooled = [*m21, saga, copier]
    assert holders(LATENT["F61"], pooled) == {"Synthetic Saga"}
    assert holders(LATENT["F60"], pooled) == {"Synthetic Copier"}
    assert "Synthetic Copier" in holders(LATENT["F40"], pooled) and "Runed Halo" in holders(LATENT["F40"], pooled)
    # and a pinned set that gains a card says which
    assert drift(PINNED["F19"][0], PINNED["F19"][1], {"M21": pooled, "M20": pools()["M20"], "FDN": pools()["FDN"]}) == []
    halo = next(c for c in m21 if c.name == "Runed Halo")
    second = dataclasses.replace(halo, name="Synthetic Halo")
    moved = drift(PINNED["F19"][0], PINNED["F19"][1], {"M21": [*m21, second], "M20": pools()["M20"],
                                                       "FDN": pools()["FDN"]})
    assert moved == ["M21: joined ['Synthetic Halo'], left []"]
