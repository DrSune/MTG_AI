"""The printed wordings of the defending player, the blocker limit and the created token
(2026-11-06).

Pinned:
1. B15 and B11: "can't be blocked by more than one creature" in its three carriers (CR 509.1b);
   "defending player loses N life" and "<noun phrase> defending player controls" (CR 506.2,
   508.5); "this <permanent> deals N damage to <noun phrase>";
2. the created token: "create <token>, then attach this Equipment to it" after the enters
   trigger and after "If you do"; "you may pay <mana>" under a trigger frame;
3. frames: the two attack frames, and a pronoun after them still refused;
4. whole cards: the Kaldheim Equipment's "If you do" is gated on the payment (CR 118.12);
5. fallback only: on M21, ZNR, M20 and KHM, a card whose sentences all parsed before keeps its
   tree, and M21 changes nowhere. "Before" is the compiler as main had it: without B15 and the new
   B11 clause, without the two attack frames, and without any reading of the widened noun phrase
   (no outcome naming the defending player). The compile census over all 19 sets checked the same
   against main itself (NUMBERS.md 2026-11-06).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from MTG_bot.core.ability_tree import (
    Atom,
    AtomArgs,
    Conditional,
    ControllerRef,
    Cost,
    CostManaColor,
    CostManaGeneric,
    DeclareAttackersEvent,
    DeclareBlockersEvent,
    FAnd,
    FAtom,
    FAtomPred,
    OptionalEffect,
    QAtLeast,
    QConst,
    Selector,
    SelectorMode,
    Seq,
    StaticAbility,
    TriggeredAbility,
    Verb,
    Zone,
    ZoneKind,
)
from MTG_bot.core.compiler import templates_b15
from MTG_bot.core.compiler.compiler import compile_card
from MTG_bot.core.compiler.coverage import build_full_registry
from MTG_bot.core.compiler.ingest import ingest_pool
from MTG_bot.core.compiler.templates import AbilityOutcome, EffectOutcome, TemplateRegistry

DATA = Path(__file__).resolve().parents[2] / "data"
YOU = FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU)
DEFENDING = FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.DEFENDING_PLAYER)
CREATURE = FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature")
IS_SOURCE = FAtom(pred=FAtomPred.IS_SOURCE)
EQUIPPED = FAnd((FAtom(pred=FAtomPred.IS_ATTACHED_TO_SOURCE), CREATURE))
BF = (Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),)
NEW = {t.tid for t in templates_b15.TEMPLATES} | {"B11-deal-damage-np"}


@pytest.fixture(scope="module")
def registry() -> TemplateRegistry:
    return build_full_registry()


def only(registry: TemplateRegistry, sentence: str):
    matches = registry.match(sentence)
    assert len(matches) == 1, [m.template.tid for m in matches]
    return matches[0].outcome


def limit(blocked) -> Atom:
    event = DeclareBlockersEvent(FAnd(()), blocked=blocked, count=QAtLeast(2))
    return Atom(Verb.PREVENT_EFFECT, AtomArgs(pairs=(("condition", blocked), ("event", event))))


def target(filter_) -> Selector:
    return Selector(QConst(1), SelectorMode.TARGET, filter_, zones=BF)


# ------------------------------------------------------------------ 1 limit, defending player


def test_this_creature_cant_be_blocked_by_more_than_one(registry) -> None:
    outcome = only(registry, "This creature can't be blocked by more than one creature.")
    assert outcome == AbilityOutcome(ability=StaticAbility(effect=limit(IS_SOURCE)))


def test_each_creature_with_power_n_or_greater(registry) -> None:
    outcome = only(
        registry,
        "Each creature you control with power 4 or greater can't be blocked by more than one "
        "creature.",
    )
    big = FAnd((YOU, FAtom(pred=FAtomPred.POWER_GE, count=QConst(4)), CREATURE))
    assert outcome == AbilityOutcome(ability=StaticAbility(effect=limit(big)))


def test_equipped_creature_gets_and_cant_be_blocked_by_more_than_one(registry) -> None:
    outcome = only(
        registry, "Equipped creature gets +1/+1 and can't be blocked by more than one creature."
    )
    assert isinstance(outcome, AbilityOutcome) and isinstance(outcome.ability, StaticAbility)
    pump, restriction = outcome.ability.effect.steps
    assert pump.verb is Verb.MODIFY_PT and pump.args.get("target").filter == EQUIPPED
    assert restriction == limit(EQUIPPED)


def test_defending_player_loses_life(registry) -> None:
    outcome = only(registry, "Defending player loses 1 life.")
    assert outcome == EffectOutcome(
        effect=Atom(Verb.LOSE_LIFE, AtomArgs(pairs=(
            ("amount", QConst(1)), ("controller", ControllerRef.DEFENDING_PLAYER))))
    )


@pytest.mark.parametrize("verb", ["Tap", "Destroy"])
def test_a_noun_phrase_defending_player_controls(registry, verb) -> None:
    outcome = only(registry, f"{verb} target creature defending player controls.")
    assert outcome.effect.args.get("target") == target(FAnd((DEFENDING, CREATURE)))


def test_this_permanent_deals_damage_to_a_noun_phrase(registry) -> None:
    outcome = only(registry, "This Equipment deals 1 damage to target creature defending player controls.")
    assert outcome == EffectOutcome(
        effect=Atom(Verb.DEAL_DAMAGE, AtomArgs(pairs=(
            ("amount", QConst(1)), ("target", target(FAnd((DEFENDING, CREATURE)))))))
    )


# ------------------------------------------------------------------------ 2 created token


def test_enters_create_a_token_then_attach_this_equipment_to_it(registry) -> None:
    outcome = only(
        registry,
        "When this Equipment enters, create a 1/1 white Soldier creature token, then attach this "
        "Equipment to it.",
    )
    trigger = outcome.ability
    assert isinstance(trigger, TriggeredAbility) and trigger.event.subject == IS_SOURCE
    create, attach = trigger.effect.steps
    assert create.verb is Verb.CREATE_TOKEN and create.args.get("tokens").name == "Soldier"
    assert attach.verb is Verb.ATTACH
    assert attach.args.get("equipment") == Selector(QConst(1), SelectorMode.CHOOSE, IS_SOURCE, zones=BF)
    assert attach.args.get("target").referent == "result"


def test_if_you_do_create_a_token_with_keywords(registry) -> None:
    outcome = only(
        registry,
        "If you do, create a 4/4 white Angel Warrior creature token with flying and vigilance, "
        "then attach this Equipment to it.",
    )
    create, attach = outcome.effect.steps
    spec = create.args.get("tokens")
    assert (spec.name, spec.subtypes, len(spec.keywords)) == ("Angel Warrior", ("Angel", "Warrior"), 2)
    assert attach.args.get("target").referent == "result"


def test_you_may_pay_under_an_enters_frame(registry) -> None:
    from MTG_bot.core.compiler.frames import compose

    sentence = "When this Equipment enters, you may pay {2}{B}."
    assert registry.match(sentence) == ()  # no template of its own: the frame reads it
    (match,) = compose(sentence, registry)
    assert match.template.tid == "B13-etb+B15-you-may-pay"
    paid = Cost((CostManaGeneric(QConst(2)), CostManaColor("B", QConst(1))))
    assert match.outcome.ability.effect == OptionalEffect(
        inner=Atom(Verb.PAY, AtomArgs(pairs=(("cost", paid),)))
    )


# ----------------------------------------------------------------------------- 3 frames


def test_the_attack_frames(registry) -> None:
    from MTG_bot.core.compiler.frames import compose

    (bow,) = compose(
        "Whenever equipped creature attacks, this Equipment deals 1 damage to target creature "
        "defending player controls.",
        registry,
    )
    assert bow.outcome.ability.event == DeclareAttackersEvent(
        filter=FAtom(pred=FAtomPred.IS_ATTACHED_TO_SOURCE)
    )
    (sliver,) = compose("Whenever a Sliver you control attacks, defending player loses 1 life.", registry)
    assert sliver.outcome.ability.event == DeclareAttackersEvent(
        filter=FAnd((YOU, FAtom(pred=FAtomPred.SUBTYPE_EQ, string_value="Sliver"), CREATURE))
    )
    # "it" after a frame may be the source or another object: still refused
    assert compose("Whenever equipped creature attacks, it deals 1 damage to any target.", registry) == ()


# ------------------------------------------------------------------------- 4 whole cards


def test_the_kaldheim_equipment_create_only_if_paid() -> None:
    registry = build_full_registry()
    pool = ingest_pool(DATA / "KHM.json")
    (bow,) = [raw for raw in pool.values() if raw.identity.name == "Elven Bow"]
    result = compile_card(bow, registry)
    assert not result.unparsed
    trigger = result.card.abilities[0]
    pay, gated = trigger.effect.steps
    assert isinstance(pay, OptionalEffect) and pay.inner.verb is Verb.PAY
    assert isinstance(gated, Conditional) and gated.pred == FAtom(pred=FAtomPred.MAY_DONE)
    assert [s.verb for s in gated.then_effect.steps] == [Verb.CREATE_TOKEN, Verb.ATTACH]


# ---------------------------------------------------------------------------- 5 fallback


class _AsOnMain(TemplateRegistry):
    """The templates main had, and no outcome that names the defending player (the only new
    reading the widened B11 noun phrase gives)."""

    def match(self, sentence: str):
        return tuple(m for m in super().match(sentence) if "DEFENDING_PLAYER" not in repr(m.outcome))


@pytest.mark.parametrize("set_code", ["M21", "ZNR", "M20", "KHM"])
def test_cards_that_compiled_before_are_untouched(registry, set_code, monkeypatch) -> None:
    from MTG_bot.core.compiler import frames

    without = _AsOnMain()
    for template in registry.all():
        if template.tid not in NEW:
            without.register(template)
    old_frames = tuple(
        f for f in frames.FRAMES if f[0].tid not in ("B13-equipped-attacks", "B13-subtype-attacks")
    )
    changed = []
    for raw in ingest_pool(DATA / f"{set_code}.json").values():
        with monkeypatch.context() as patch:
            patch.setattr(frames, "FRAMES", old_frames)
            try:
                before = compile_card(raw, without)
            except Exception:  # noqa: BLE001, S112 - a card that cannot compile is outside this property
                continue
        after = compile_card(raw, registry)
        if repr(after.card) == repr(before.card) and after.unparsed == before.unparsed:
            continue
        changed.append(raw.identity.name)
        assert before.unparsed or before.back_face_unparsed, raw.identity.name
    if set_code == "M21":
        assert changed == []
    if set_code == "M20":  # the census's M20 changes, the newly parsed sentences' cards
        assert sorted(changed) == [
            "Ancestral Blade", "Bristling Boar", "Heart-Piercer Bow", "Mask of Immolation",
            "Wolfrider's Saddle",
        ]


def test_b15_registers_its_templates() -> None:
    assert {t.tid for t in templates_b15.TEMPLATES} == {
        "B15-defending-player-loses-life",
        "B15-cant-be-blocked-by-more-than-one",
        "B15-power-class-cant-be-blocked-by-more-than-one",
        "B15-equipped-pt-cant-be-blocked-by-more-than-one",
        "B15-etb-create-attach",
        "B15-if-do-create-attach",
        "B15-you-may-pay",
    }
