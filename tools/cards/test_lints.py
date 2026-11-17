"""The static lints of gate G0 (tools/cards/lints.py): silent on every verified card, and each one
flags real defects of the onboarding waves, rebuilt from git or from the reports that found them,
and the planted faults of the commonest classes (KNOWLEDGE/2026-11-14/207)."""

from __future__ import annotations

import dataclasses
import json
import re
import sys
from functools import cache
from pathlib import Path
from typing import Any

import pytest

HERE = Path(__file__).resolve().parent
for _p in (HERE.parents[1], HERE):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import corpus
import gates
import irpy
import lints
from irpy import A

from MTG_bot.core.ability_tree import (
    Conditional,
    ControllerRef,
    DamageDealtEvent,
    DeclareAttackersEvent,
    DeclareBlockersEvent,
    EachPlayer,
    FAnd,
    FAtom,
    FAtomPred,
    Keyword,
    QConst,
    QProp,
    QPropField,
    QUnbounded,
    Selector,
    SelectorMode,
    Seq,
    SpellAbility,
    SpellKind,
    TriggeredAbility,
    Verb,
    Zone,
    ZoneChangeEvent,
    ZoneKind,
    from_dict,
)
from MTG_bot.core.compiler import card_records
from MTG_bot.core.compiler.coverage import build_full_registry
from MTG_bot.core.compiler.frames import compose
from MTG_bot.core.compiler.templates import food_token

HISTORY = json.loads((HERE / "testdata" / "lint_history.json").read_text())


@cache
def _set(code: str) -> Any:
    return corpus.compile_set(code)


def _card(code: str, name: str) -> tuple[Any, Any]:
    sc = _set(code)
    oid = sc.by_name(name)
    return sc.raw[oid], sc.results[oid].card


def _printed(code: str, name: str) -> tuple[Any, Any]:
    """The card's printed facts with none of its text compiled (a permanent keeps its cast
    carrier): the base of a tree a test writes itself, which the card's record cannot change."""
    raw = _set(code).raw[_set(code).by_name(name)]
    return raw, corpus.printed_only(raw).card


def test_no_lint_finding_on_any_verified_card() -> None:
    # 736 verified cards on 2026-11-14 (M21 275, M20 277, FDN 184): every finding here is a false
    # positive, or a verified card that is wrong.
    checked = 0
    for code in ("M21", "M20", "FDN"):
        sc = _set(code)
        for oid, rec in sc.records.items():
            res = sc.results.get(oid)
            if res is None or not card_records.is_verified(res, rec):
                continue
            assert lints.lint(sc.raw[oid], res.card) == [], (code, sc.raw[oid].identity.name)
            checked += 1
    assert checked >= 700


@pytest.mark.parametrize("case", HISTORY, ids=[c["name"] for c in HISTORY])
def test_each_lint_flags_a_real_defect_of_the_waves(case: dict) -> None:
    # The tree as it was before its fix (the source says where in git), and the tree today.
    raw, today = _card(case["set"], case["name"])
    then = dataclasses.replace(
        today, keywords=tuple(from_dict("KeywordAbility", k) for k in case["keywords"]),
        abilities=tuple(from_dict(a["tag"], a) for a in case["abilities"]))
    assert any(f.startswith(case["lint"] + ":") for f in lints.lint(raw, then)), case["note"]
    assert lints.lint(raw, today) == []


def test_carrier_flags_an_orphaned_clause_on_a_permanent_spell() -> None:
    # M20 Keldon Raider as the compiler built it on 2026-11-05 (its mapper's report, round_m20 m9):
    # "you may discard a card" unparsed, so "If you do, draw a card." hung on the creature spell
    # itself and casting it drew a card (23 partly compiled cards, fixed in the second wave, 184 §7).
    raw, card = _card("M20", "Keldon Raider")
    orphan = SpellAbility(kind=SpellKind.CREATURE, effect=Conditional(
        pred=FAtom(pred=FAtomPred.MAY_DONE),
        then_effect=A(Verb.DRAW, {"amount": QConst(value=1), "controller": ControllerRef.YOU})))
    then = dataclasses.replace(card, abilities=(orphan,))
    assert any(f.startswith("carrier:") for f in lints.lint(raw, then))
    # The one accepted carrier effect: an Aura's "You control enchanted creature." (verified).
    raw, hold = _card("M21", "Enthralling Hold")
    assert any(isinstance(a, SpellAbility) and a.effect is not None for a in hold.abilities)
    assert lints.carrier(raw, hold) == []


@pytest.mark.parametrize("code,name,op,where,lint", [
    # verification wave 1's and 1d's plants, each at the path its answer key names
    ("M21", "Warded Battlements", "controller YOU->OPPONENT", "1/0/effect/args/target/filter/children/0/who", "players"),
    ("M20", "Epicure of Blood", "controller ALL_OPPONENTS->YOU", "1/0/effect/args/controller", "players"),
    ("M20", "Spectral Sailor", "drop cost part 0 (CostManaColor)", "1/0/cost", "costs"),
    ("M20", "Ancestral Blade", "amount+1", "1/0/effect/steps/0/args/count", "amounts"),
])
def test_the_planted_shapes_of_the_commonest_classes_are_flagged(code: str, name: str, op: str, where: str,
                                                                  lint: str) -> None:
    raw, card = _card(code, name)
    plant = next(m for o, w, m in gates.mutants(card) if (o, w) == (op, where))
    assert any(f.startswith(lint + ":") for f in lints.lint(raw, plant))


def test_a_free_activation_is_flagged_and_an_equip_cost_is_read() -> None:
    raw, saddle = _card("M20", "Wolfrider's Saddle")
    assert lints.costs(raw, saddle) == []
    bare = [m for o, _w, m in gates.mutants(saddle) if o.startswith("drop cost part")]
    assert bare and all(lints.costs(raw, m) for m in bare)


def test_the_costs_lint_reads_exile_and_remove_counter_costs() -> None:
    """Ontology round R11's cost items are read part for part: the round's trees pass, and a tree
    that drops the exile or the removal, or removes two counters where one is printed (a mutant
    the probe cannot see: its board Troll holds no counter), is flagged."""
    assert lints.printed_cost("{1}, Remove a +1/+1 counter from this creature") == {
        "generic": 1, "remove:PLUS_1_PLUS_1:1": 1}
    assert lints.printed_cost("{T}, Remove three charge counters from this artifact") == {
        "tap": 1, "remove:CHARGE:3": 1}
    assert lints.printed_cost("{1}{G}, Exile a creature card from your graveyard") == {
        "generic": 1, "G": 1, "exile:1": 1}
    assert lints.printed_cost("{4}{B}{B}, Exile this card from your graveyard") == {
        "generic": 4, "B": 2, "exile:self": 1}
    # Hellion Crucible's "... and sacrifice it" is two parts in one item: not read
    assert lints.printed_cost("{1}{R}, {T}, Remove two pressure counters from this land and sacrifice it") is None
    for code, name in (("M20", "Hanged Executioner"), ("M20", "Barkhide Troll"), ("FDN", "Suspicious Shambler")):
        raw, card = _card(code, name)
        assert lints.costs(raw, card) == [], name
        wrong = [m for op, _w, m in gates.mutants(card)
                 if op.startswith(("drop cost part", "amount+1")) and "/cost/" in _w + "/"]
        assert wrong and all(lints.costs(raw, m) for m in wrong), name


def test_a_quoted_ability_and_a_trigger_event_are_no_instructions() -> None:
    # Light of Promise: 'Enchanted creature has "Whenever you gain life, put that many +1/+1
    # counters on this creature."' names no gain of life.
    assert lints.subject_verbs('Enchanted creature has "Whenever you gain life, put that many '
                               '+1/+1 counters on this creature."') == []
    assert lints.subject_verbs("Target player draws two cards and loses 2 life.") == [
        ("target player", "draw", "Target player draws"),
        ("target player", "lose", "Target player draws two cards and loses")]


def test_g0_fails_a_card_a_lint_flags() -> None:
    raw, card = _card("M21", "Warded Battlements")
    mutant = next(m for o, _w, m in gates.mutants(card) if o == "controller YOU->OPPONENT")
    fails, _warns = gates.g0(raw, card, mutant, clauses=None, known_signatures=None)
    assert any(f.startswith("lint players:") for f in fails)
    assert not any(f.startswith("lint ") for f in gates.g0(raw, card, card, clauses=None, known_signatures=None)[0])


def test_every_exception_names_its_reason() -> None:
    for (lint, oid), why in lints.EXCEPTIONS.items():
        assert lint in lints.LINTS and len(oid) == 36 and len(why) > 40


def test_every_inert_label_is_a_printed_sentence_with_its_reason() -> None:
    for (oid, sentence), why in lints.INERT.items():
        raw = next(sc.raw[oid] for sc in map(_set, corpus.SETS) if oid in sc.raw)
        assert sentence in lints.rules_text(raw) and len(why) > 40


# ------------------------------------------------- the 209 rulings (docs/MAPPER_GUIDE.md "Rulings")
def _guide_blocks() -> dict[str, dict]:
    """Each ruling's Python block of MAPPER_GUIDE, run as a draft runs (irpy's namespace), by its
    first line ("# R_FOOD")."""
    text = (HERE.parents[1] / "docs" / "MAPPER_GUIDE.md").read_text()
    out = {}
    for tag, body in re.findall(r"```python\n# (R_\w+)\n(.*?)```", text, re.DOTALL):
        ns = irpy.namespace()
        ns.update(compiled=[], effect=A(Verb.DRAW, {"amount": QConst(1), "controller": ControllerRef.YOU}))
        exec(compile(body, tag, "exec"), ns)  # noqa: S102 — the guide's own drafts
        out[tag] = ns
    return out


def test_the_guide_writes_each_ruling_as_the_lints_read_it() -> None:
    """The exact Python MAPPER_GUIDE gives a mapper is the one form its lint accepts."""
    blocks = _guide_blocks()
    assert blocks["R_FOOD"]["FOOD"] == food_token() == lints.FOOD
    assert blocks["R_FOOD"]["create_food"].args.get("tokens") == lints.FOOD
    two = blocks["R_TWOEVENTS"]
    assert (two["enters"].event, two["dies"].event) == (lints.SELF_EVENTS["enters"], lints.SELF_EVENTS["dies"])
    assert two["abilities"] == [two["enters"], two["dies"]]
    assert blocks["R_ITSCONTROLLER"]["its_controller"] == lints.controller_of_referent("target")


def test_the_two_events_are_the_compilers_own() -> None:
    """Each half's event is what the compiler builds for the one-event wording (canonical by
    construction), and M21 Elder Gargaroth's verified "attacks or blocks" is the pair form."""
    registry = build_full_registry()
    for word, sentence in (("enters", "When this creature enters, draw a card."),
                           ("dies", "When this creature dies, draw a card."),
                           ("attacks", "Whenever this creature attacks, draw a card.")):
        match = next(iter(registry.match(sentence)), None) or next(iter(compose(sentence, registry)))
        assert match.outcome.ability.event == lints.SELF_EVENTS[word], word
    raw, gargaroth = _card("M21", "Elder Gargaroth")
    assert [type(a.event) for a in gargaroth.abilities[:2]] == [DeclareAttackersEvent, DeclareBlockersEvent]
    assert lints.two_events(raw, gargaroth) == []


def test_food_has_one_token() -> None:
    # Bake into a Pie's text over trees written here, so its own record (the one Food) is not read
    raw, card = _printed("FDN", "Bake into a Pie")
    creature = Selector(QConst(1), SelectorMode.TARGET, FAtom(FAtomPred.TYPE_EQ, string_value="Creature"),
                        zones=(Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),))
    destroy = A(Verb.DESTROY, {"target": creature})  # the compiler's "Destroy target creature."

    def spell(*steps: Any) -> Any:
        return dataclasses.replace(card, abilities=(SpellAbility(kind=SpellKind.INSTANT, effect=Seq(steps=steps)),))

    assert lints.lint(raw, spell(destroy, A(Verb.CREATE_TOKEN, {"count": QConst(1), "tokens": lints.FOOD}))) == []
    assert lints.food(raw, spell(destroy))  # "Create a Food token." with no Food in the tree
    treasure_like = dataclasses.replace(lints.FOOD, type_line="Artifact", subtypes=(), keywords=(Keyword.TREASURE,))
    gains_four = dataclasses.replace(lints.FOOD, abilities=(dataclasses.replace(
        lints.FOOD.abilities[0], effect=A(Verb.GAIN_LIFE, {"amount": QConst(4), "controller": ControllerRef.YOU})),))
    for odd in (treasure_like, gains_four):
        found = lints.food(raw, spell(destroy, A(Verb.CREATE_TOKEN, {"count": QConst(1), "tokens": odd})))
        assert len(found) == 2 and "differ from the one Food" in found[0], odd


def test_enters_or_dies_is_two_abilities_with_one_effect() -> None:
    raw, card = _printed("FDN", "Crow of Dark Tidings")  # its cast carrier alone, whatever its record holds
    mill = A(Verb.MOVE_ZONE, {"amount": QConst(2), "controller": ControllerRef.YOU,
                              "destination": Zone(ZoneKind.GRAVEYARD, ControllerRef.YOU),
                              "from": Zone(ZoneKind.LIBRARY, ControllerRef.YOU),
                              "journal_kind": "MILL", "pop_order": "TOP"})
    ev = lints.SELF_EVENTS

    def crow(*pairs: Any) -> Any:
        return dataclasses.replace(card, abilities=(
            *(TriggeredAbility(event=e, condition=None, effect=x) for e, x in pairs), *card.abilities))

    assert lints.lint(raw, crow((ev["enters"], mill), (ev["dies"], mill))) == []
    leaves = ZoneChangeEvent(from_zone=Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),
                             to_zone=Zone(ZoneKind.ANY, ControllerRef.ANY), subject=FAtom(FAtomPred.IS_SOURCE))
    mill_three = A(Verb.MOVE_ZONE, {**dict(mill.args.pairs), "amount": QConst(3)})
    for wrong in ([(ev["enters"], mill)],                             # a half dropped
                  [(ev["enters"], mill), (leaves, mill)],             # "leaves" for "dies": a bounce mills
                  [(ev["dies"], mill), (ev["enters"], mill)],         # not printed order
                  [(ev["enters"], mill), (ev["dies"], mill_three)]):  # two effects
        assert lints.two_events(raw, crow(*wrong)), wrong


def test_damage_to_its_controller_has_one_form() -> None:
    raw, card = _card("M20", "Chandra's Outrage")
    creature = Selector(QConst(1), SelectorMode.TARGET, FAtom(FAtomPred.TYPE_EQ, string_value="Creature"),
                        zones=(Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),))
    four = A(Verb.DEAL_DAMAGE, {"amount": QConst(4), "target": creature})

    def outrage(second: Any) -> Any:
        return dataclasses.replace(card, abilities=(SpellAbility(kind=SpellKind.INSTANT, effect=Seq(steps=(four, second))),))

    good = A(Verb.DEAL_DAMAGE, {"amount": QConst(2), "target": lints.controller_of_referent("target")})
    assert lints.lint(raw, outrage(good)) == []
    player_slot = Selector(QConst(1), SelectorMode.TARGET, FAnd(()), zones=(Zone(ZoneKind.PLAYER, ControllerRef.ANY),))
    you = Selector(QUnbounded(), SelectorMode.ALL, FAnd(()), zones=(Zone(ZoneKind.PLAYER, ControllerRef.YOU),))
    ref = lints.controller_of_referent("target").filter.who
    for wrong in (A(Verb.DEAL_DAMAGE, {"amount": QConst(2), "target": player_slot}),  # the caster chooses
                  A(Verb.DEAL_DAMAGE, {"amount": QConst(2), "target": ref}),          # the creature again
                  EachPlayer(ref=ref, effect=A(Verb.DEAL_DAMAGE, {"amount": QConst(2), "target": you}))):
        assert lints.its_controller(raw, outrage(wrong)), wrong


def test_its_controller_names_a_target_only_where_its_ability_chooses_one() -> None:
    """M12 Belltower Sphinx's "Whenever a source deals damage to this creature, that source's
    controller mills that many cards": a damage trigger's dealer stands for "target" only in a
    TARGET_PLAYER read with no printed target (KNOWLEDGE 203), so a 'target' referent there names
    nobody: the card has no form yet (needs-atom)."""
    raw, card = _card("M20", "Chandra's Outrage")  # any card: this check reads the tree alone
    mill = A(Verb.MOVE_ZONE, {"amount": QProp("event", QPropField.AMOUNT),
                              "controller": lints.controller_of_referent("target").filter.who,
                              "destination": Zone(ZoneKind.GRAVEYARD, ControllerRef.OWNER),
                              "from": Zone(ZoneKind.LIBRARY, ControllerRef.ANY),
                              "journal_kind": "MILL", "pop_order": "TOP"})
    trigger = TriggeredAbility(event=DamageDealtEvent(amount=QUnbounded(), filter=FAtom(FAtomPred.IS_SOURCE)),
                               condition=None, effect=mill)
    assert any("never chooses" in f for f in lints.its_controller(raw, dataclasses.replace(card, abilities=(trigger,))))
