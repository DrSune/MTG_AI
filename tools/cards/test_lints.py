"""The static lints of gate G0 (tools/cards/lints.py): silent on every verified card, and each one
flags real defects of the onboarding waves, rebuilt from git or from the reports that found them,
and the planted faults of the commonest classes (KNOWLEDGE/2026-11-14/207)."""

from __future__ import annotations

import dataclasses
import json
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
import lints
from irpy import A

from MTG_bot.core.ability_tree import (
    Conditional,
    ControllerRef,
    FAtom,
    FAtomPred,
    QConst,
    SpellAbility,
    SpellKind,
    Verb,
    from_dict,
)
from MTG_bot.core.compiler import card_records

HISTORY = json.loads((HERE / "testdata" / "lint_history.json").read_text())


@cache
def _set(code: str) -> Any:
    return corpus.compile_set(code)


def _card(code: str, name: str) -> tuple[Any, Any]:
    sc = _set(code)
    oid = sc.by_name(name)
    return sc.raw[oid], sc.results[oid].card


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
