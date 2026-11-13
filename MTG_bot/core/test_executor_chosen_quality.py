"""A quality chosen as a permanent enters (2026-11-13, ontology round R9, gate round 9 pending):
"As this creature enters, choose a color." (M20 Diamond Knight, FDN Diamond Mare) and "As this
artifact enters, choose a creature type." (M20 Icon of Ancestry). DESIGN_ATOM_ONTOLOGY §13.

- ``Verb.CHOOSE_NAME`` takes an optional closed-vocabulary role ``quality`` (COLOR or
  CREATURE_TYPE; absent, a card name, so Runed Halo's bytes do not change), and only as an
  EtBState's effect: the choice is made before the permanent enters (CR 614.12a) and lasts as
  long as it. ``FAtomPred.NAME_CHOSEN`` reads it back with the same vocabulary in its
  ``string_value``.
- CR 607.2d: "choose a [value]" and "the chosen [value]" on one object are linked, and the read
  refers only to that object's choice. A read with no choice of its quality on its own object (a
  token's, an emblem's, a granted ability's) is refused when the tree is built.
- The executor keys a choice by (source, quality). A colour is one of the five, in WUBRG order
  (CR 105.1); a creature type one of the format pool's (cards and the creature tokens they make).
  Every choice is made before the entering counters are counted.

Every test here but one fails on the base, dafdd5ff: the role, the slot, the checks and the
creature-type pool do not exist there, it built a card-name choice nothing reads, and its entering
counters were counted before a choice printed after them (``reports/chosen_quality_2026-11-13/base_runs.txt``). The exception,
``test_runed_halo_keeps_its_bytes_and_its_verification``, pins that the optional role leaves Runed
Halo's tree and stamp as they were, true on both.
"""

from __future__ import annotations

import pytest

from MTG_bot.core import ability_tree as at
from MTG_bot.core.ability_tree import (
    Atom,
    AtomArgs,
    ControllerRef,
    CounterKind,
    EtBState,
    FAnd,
    FAtom,
    FAtomPred,
    Keyword,
    KeywordAbility,
    QConst,
    QCount,
    QUnbounded,
    Selector,
    SelectorMode,
    StaticAbility,
    Verb,
    Zone,
    ZoneKind,
)
from MTG_bot.core.compiler import card_records
from MTG_bot.core.executor.games import _setup_game, get_supply
from MTG_bot.core.executor.legality import ctx_for
from MTG_bot.core.executor.quantity import eval_filter
from MTG_bot.core.test_executor_binding import record_of
from tools.run_scenarios import ScenarioRunner

BF = Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY)


def _atom(verb: Verb, **roles) -> Atom:
    return Atom(verb, AtomArgs(pairs=tuple(roles.items())))


def _choose(quality: str | None) -> Atom:
    return _atom(Verb.CHOOSE_NAME) if quality is None else _atom(Verb.CHOOSE_NAME, quality=quality)


def _chosen(quality: str | None) -> FAtom:
    return FAtom(FAtomPred.NAME_CHOSEN, string_value=quality)


def _anthem(quality: str | None) -> StaticAbility:
    """Creatures of the chosen quality get +1/+1 (Icon of Ancestry's shape)."""
    creatures = Selector(QUnbounded(), SelectorMode.ALL, _chosen(quality), zones=(BF,))
    return StaticAbility(
        effect=_atom(
            Verb.MODIFY_PT,
            target=creatures,
            power=at.PtDelta(at.PtDirection.INCREASE, QConst(1)),
            toughness=at.PtDelta(at.PtDirection.INCREASE, QConst(1)),
        )
    )


def _runner(code: str, cards: list[dict]) -> ScenarioRunner:
    pack = {"set": code, "world": {"life": 20, "seed": 7}, "cards": cards, "steps": []}
    return ScenarioRunner(pack, get_supply("all", code))


def _card(key: str, name: str, seat: int = 0, zone: str = "battlefield", **synthetic) -> dict:
    if synthetic:
        return {"key": key, "name": name, "zone": zone, "controller": seat, **synthetic}
    return {"key": key, "real": name, "zone": zone, "controller": seat}


# ------------------------------------------------------------------------------ the IR


@pytest.mark.parametrize("bad", ["NAME", "color", "LAND_TYPE", "CARD_TYPE", "W", ""])
def test_a_quality_outside_the_vocabulary_is_refused(bad: str) -> None:
    with pytest.raises(ValueError, match="role 'quality' must be one of"):
        _choose(bad)
    if bad:  # FAtom refuses an empty string_value before the vocabulary
        with pytest.raises(ValueError, match="NAME_CHOSEN string_value must be one of"):
            _chosen(bad)
    # the two values the vocabulary holds build; absent is the card name
    assert _choose("COLOR").args.get("quality") == "COLOR"
    assert _chosen("CREATURE_TYPE").string_value == "CREATURE_TYPE"


def test_a_quality_belongs_to_choose_name_alone() -> None:
    you = ControllerRef.YOU
    for verb, roles in (
        (Verb.ADD_MANA, {"controller": you, "amount": QConst(1)}),
        (Verb.CHOOSE, {"target": Selector(QConst(1), SelectorMode.CHOOSE, FAnd(()), zones=(BF,))}),
        (Verb.GRANT_TYPE, {"target": Selector(QConst(1), SelectorMode.CHOOSE,
                                              FAtom(FAtomPred.IS_SOURCE), zones=(BF,)),
                           "types": ("Elf",)}),
    ):
        with pytest.raises(ValueError, match=r"does not take roles \['quality'\]"):
            _atom(verb, quality="COLOR", **roles)
    # a name filter judges card names: beside a quality it judges nothing
    with pytest.raises(ValueError, match="a quality choice takes none"):
        _atom(Verb.CHOOSE_NAME, quality="CREATURE_TYPE", name_filter=FAtom(FAtomPred.IS_TOKEN))


def test_a_read_needs_a_choice_of_its_quality_on_its_own_object() -> None:
    enters = EtBState(effect=_choose("COLOR"))
    assert record_of([enters, _anthem("COLOR")])  # linked: builds
    for abilities in (
        [_anthem("COLOR")],  # no choice at all
        [EtBState(effect=_choose("CREATURE_TYPE")), _anthem("COLOR")],  # another quality
        [EtBState(effect=_choose(None)), _anthem("COLOR")],  # a name is not a colour
        [_anthem(None)],  # a card name read with no name chosen (CR 607.2d holds for names too)
    ):
        with pytest.raises(ValueError, match="that no CHOOSE_NAME of the same object chooses"):
            record_of(abilities)
    with pytest.raises(ValueError, match="chooses a COLOR twice"):
        record_of([enters, EtBState(effect=_choose("COLOR")), _anthem("COLOR")])


def test_a_read_outside_the_card_that_chose_is_refused() -> None:
    enters = EtBState(effect=_choose("COLOR"))
    you_creature = Selector(QConst(1), SelectorMode.CHOOSE, FAtom(FAtomPred.IS_SOURCE), zones=(BF,))
    token = at.TokenSpec(
        name="Spirit", type_line="Creature — Spirit", types=("Creature",), subtypes=("Spirit",),
        power=QConst(1), toughness=QConst(1), keywords=(), abilities=(_anthem("COLOR"),),
    )
    makes_token = at.ActivatedAbility(
        cost=at.Cost(parts=(at.CostTap(),)),
        effect=_atom(Verb.CREATE_TOKEN, tokens=token),
    )
    emblem = at.ActivatedAbility(
        cost=at.Cost(parts=(at.CostTap(),)),
        effect=_atom(Verb.GET_EMBLEM, controller=ControllerRef.YOU,
                     emblem=at.EmblemSpec(abilities=(_anthem("COLOR"),))),
    )
    granted_trigger = StaticAbility(
        effect=_atom(Verb.GRANT_ABILITY, target=you_creature, ability=_anthem("COLOR"))
    )
    granted_hexproof = StaticAbility(
        effect=_atom(Verb.GRANT_ABILITY, target=you_creature,
                     ability=KeywordAbility(keyword=Keyword.HEXPROOF, params=(_chosen("COLOR"),)))
    )
    for foreign in (makes_token, emblem, granted_trigger, granted_hexproof):
        with pytest.raises(ValueError, match="that no CHOOSE_NAME of the same object chooses"):
            record_of([enters, foreign])
    # protection's quality is judged in the coordinates of the ability that gives it
    # (legality.protected_from: Runed Halo's), so a granted PROTECTION reads its granter's choice
    granted_protection = StaticAbility(
        effect=_atom(Verb.GRANT_ABILITY, target=you_creature,
                     ability=KeywordAbility(keyword=Keyword.PROTECTION, params=(_chosen("COLOR"),)))
    )
    assert record_of([enters, granted_protection])


def test_a_quality_is_chosen_only_as_a_permanent_enters() -> None:
    tap = at.Cost(parts=(at.CostTap(),))
    for elsewhere in (
        at.ActivatedAbility(cost=tap, effect=_choose("COLOR")),
        at.SpellAbility(kind=at.SpellKind.CREATURE, effect=_choose("CREATURE_TYPE")),
        EtBState(effect=at.Seq(steps=(_choose("COLOR"), _atom(Verb.SHUFFLE, zone=Zone(
            ZoneKind.LIBRARY, ControllerRef.YOU))))),
    ):
        with pytest.raises(ValueError, match=r"stands only as the effect of an EtBState"):
            record_of([elsewhere, _anthem("COLOR"), _anthem("CREATURE_TYPE")])
    assert record_of([EtBState(effect=_choose("CREATURE_TYPE")), _anthem("CREATURE_TYPE")])
    # a card name is still chosen anywhere (Necromentia's spell)
    assert record_of([at.ActivatedAbility(cost=tap, effect=_choose(None)), _anthem(None)])


@pytest.mark.parametrize("quality", [None, "COLOR", "CREATURE_TYPE"])
def test_a_choice_nothing_reads_is_refused(quality) -> None:
    """A choice with no consequence is a phantom ask (AGENTS §10): a card whose reading sentence
    did not compile (10E Voice of All's "protection from the chosen color") is a shape gap, not a
    card that asks a colour for nothing. On the base the card-name case built."""
    enters = EtBState(effect=_choose(quality))
    with pytest.raises(ValueError, match="that nothing on its object reads"):
        record_of([enters])
    assert record_of([enters, _anthem(quality)])


def test_runed_halo_keeps_its_bytes_and_its_verification() -> None:
    supply = get_supply("all", "M21")
    oid = next(o for o, m in supply.metas.items() if m.name == "Runed Halo")
    result = supply.pool.results[oid]
    assert card_records.is_verified(result, card_records.load_records("M21").get(oid))
    choose = result.card.abilities[0]
    assert isinstance(choose, EtBState) and choose.effect == _choose(None)


# ------------------------------------------------------------------------------ the engine


def test_a_colour_is_one_of_the_five_and_the_cast_trigger_reads_it() -> None:
    runner = _runner("FDN", [
        _card("mare", "Diamond Mare", zone="hand"),
        _card("red", "Red Thing", type="Creature", colors=["R"], power=1, toughness=1),
        _card("blue", "Blue Thing", type="Creature", colors=["U"], power=1, toughness=1),
    ])
    runner.run_step({"op": "enter", "key": "mare", "decisions": ["R"]})
    mare = runner.handles["mare"]
    assert runner.ex.name_choices[(mare, "COLOR")] == "R"
    ctx = ctx_for(runner.ex, source=mare, controller=runner.p0)
    assert eval_filter(_chosen("COLOR"), runner.handles["red"], ctx)
    assert not eval_filter(_chosen("COLOR"), runner.handles["blue"], ctx)
    # the menu: the five colours in WUBRG order, colourless no colour (CR 105.1, 105.2c)
    asked: list[tuple[tuple[str, ...], str]] = []
    runner.ex.decisions.provider = lambda vocab, what: asked.append((vocab, what)) or "W"
    runner.ex.apply_effect(_choose("COLOR"), source=mare, controller=runner.p0)
    assert asked == [(("W", "U", "B", "R", "G"), f"quality:{mare}:COLOR")]


def test_a_creature_type_is_one_of_the_format_pools() -> None:
    supply = get_supply("all", "M21")
    game = _setup_game(5, supply, (supply.deckable[:40], supply.deckable[40:80]))
    pool = game.executor.creature_type_pool
    assert pool == tuple(sorted(pool)) and "Elf" in pool
    # a creature token's type no card has (M21 Saproling: Fungal Rebirth, Sporeweb Weaver)
    assert "Saproling" in pool
    assert not {"Creature", "Legendary", "Aura", "Equipment", "Forest", "—"} & set(pool)
    source = game.executor.world.player_order[0]
    offered: list[tuple[str, ...]] = []
    game.executor.decisions.provider = lambda vocab, what: offered.append(vocab) or vocab[0]
    game.executor.apply_effect(_choose("CREATURE_TYPE"), source=source, controller=source)
    assert offered == [pool]


@pytest.mark.parametrize(("quality", "word", "counted"), [
    (None, "Elf One", 1), ("CREATURE_TYPE", "Elf", 2)])
def test_every_choice_is_made_before_the_entering_counters_are_counted(quality, word, counted):
    """CR 614.12a: Banner of Kinship's "enters with a fellowship counter on it for each creature
    you control of the chosen type" counts after the choice, here even printed first. On the base
    the card name's case fails too: the counters were counted node by node, in printed order."""
    runner = _runner("M21", [
        _card("banner", "Banner", zone="hand", type="Artifact"),
        _card("elf1", "Elf One", type="Creature — Elf", power=1, toughness=1),
        _card("elf2", "Elf Two", type="Creature — Elf", power=1, toughness=1),
        _card("orc", "Orc", type="Creature — Orc", power=1, toughness=1),
    ])
    banner = runner.handles["banner"]
    oid = runner.world.cards[banner].identity.oracle_id
    yours_chosen = Selector(
        QUnbounded(), SelectorMode.ALL,
        FAnd(children=(FAtom(FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
                       FAtom(FAtomPred.TYPE_EQ, string_value="Creature"),
                       _chosen(quality))),
        zones=(BF,),
    )
    counters = EtBState(initial_counters=((CounterKind.CHARGE, QCount(yours_chosen)),))
    runner.ex.binder.records[oid] = at.CardRecord(
        oracle_id=oid, name="Banner", type_line="Artifact", types=("Artifact",), subtypes=(),
        supertypes=(), colors=(), color_identity=frozenset(), mana_cost=None, mana_value=3,
        power=None, toughness=None, loyalty=None, keywords=(),
        abilities=(counters, EtBState(effect=_choose(quality))), is_token=False)
    runner.run_step({"op": "enter", "key": "banner", "decisions": [word]})
    assert runner.ex.name_choices[(banner, quality)] == word
    assert runner.world.cards[banner].counters == {"CHARGE": counted}


def test_the_choice_leaves_with_the_permanent_and_a_return_chooses_again() -> None:
    runner = _runner("FDN", [_card("mare", "Diamond Mare", zone="hand")])
    mare = runner.handles["mare"]
    runner.run_step({"op": "enter", "key": "mare", "decisions": ["G"]})
    assert runner.ex.name_choices == {(mare, "COLOR"): "G"}
    runner.run_step({"op": "move", "key": "mare", "to": "hand"})
    assert runner.ex.name_choices == {}  # CR 400.7: a new object
    runner.run_step({"op": "enter", "key": "mare", "decisions": ["B"]})
    assert runner.ex.name_choices == {(mare, "COLOR"): "B"}


def test_a_read_of_what_its_source_did_not_choose_raises() -> None:
    """The run-time half of CR 607.2d: a source that chose a card name (Runed Halo) has no colour,
    and nothing answers for it ("flagged, never guessed")."""
    runner = _runner("M21", [_card("halo", "Runed Halo", zone="hand"),
                             _card("bear", "Bear", type="Creature", colors=["W"], power=2,
                                   toughness=2)])
    runner.run_step({"op": "enter", "key": "halo", "decisions": ["Runed Halo"]})
    halo = runner.handles["halo"]
    ctx = ctx_for(runner.ex, source=halo, controller=runner.p0)
    assert eval_filter(_chosen(None), halo, ctx)  # the Halo named itself
    with pytest.raises(NotImplementedError, match="NAME_CHOSEN of a COLOR needs a CHOOSE_NAME"):
        eval_filter(_chosen("COLOR"), runner.handles["bear"], ctx)
