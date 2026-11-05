"""The printed wordings of turn history and "can't be countered" (2026-11-05).

Pinned:
1. conditions.py: every phrase of the grammar builds its Filter, and the shapes M21 already
   compiles build the atoms its templates use, byte for byte;
2. B14: "can't be countered" in its three carriers, bloodthirst, and the statics that take a
   turn-history condition, as printed in the corpus;
3. frames: an intervening "if" in a trigger frame (CR 603.4), a trailing "if"/"unless", an
   ability word dropped (CR 207.2c), a condition outside the grammar refused;
4. B11: "target <noun phrase> that was dealt damage this turn";
5. fallback only: on M21, ZNR, M20 and KHM, a card whose sentences all parsed before keeps its
   tree, and M21 changes nowhere.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from MTG_bot.core.ability_tree import (
    Atom,
    AtomArgs,
    CastSpellEvent,
    Conditional,
    ControllerRef,
    CounteredEvent,
    CounterKind,
    DamageDealtEvent,
    DeclareAttackersEvent,
    DeclareBlockersEvent,
    DurationEot,
    EtBState,
    FAnd,
    FAtom,
    FAtomPred,
    FNot,
    FOr,
    LifeLostEvent,
    QConst,
    QUnbounded,
    StaticAbility,
    TriggeredAbility,
    Verb,
)
from MTG_bot.core.compiler import conditions, frames, templates_b2a, templates_b14
from MTG_bot.core.compiler.compiler import compile_card
from MTG_bot.core.compiler.coverage import build_full_registry
from MTG_bot.core.compiler.ingest import ingest_pool
from MTG_bot.core.compiler.templates import (
    AbilityOutcome,
    EffectOutcome,
    TemplateRegistry,
)

DATA = Path(__file__).resolve().parents[2] / "data"
YOU = FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU)
OPPONENT = FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.OPPONENT)
IS_SOURCE = FAtom(pred=FAtomPred.IS_SOURCE)
SPELL = FAtom(pred=FAtomPred.STACK_KIND_EQ, string_value="SPELL")


def happened(event, count=1) -> FAtom:
    return FAtom(pred=FAtomPred.EVENT_THIS_TURN, event=event, count=QConst(count))


YOU_ATTACKED = FAnd(
    (FAtom(pred=FAtomPred.TURN_OF, who=ControllerRef.YOU), happened(DeclareAttackersEvent(FAnd(()))))
)
OPPONENT_DEALT_DAMAGE = happened(
    DamageDealtEvent(amount=QUnbounded(), filter=FAtom(pred=FAtomPred.OPPONENT_OF, who=ControllerRef.YOU))
)


@pytest.fixture(scope="module")
def registry() -> TemplateRegistry:
    return build_full_registry()


def only(registry: TemplateRegistry, sentence: str):
    matches = registry.match(sentence)
    assert len(matches) == 1, [m.template.tid for m in matches]
    return matches[0].outcome


# ------------------------------------------------------------------------ 1 conditions


@pytest.mark.parametrize(
    ("phrase", "expected"),
    [
        ("an opponent lost life this turn", happened(LifeLostEvent(actor=OPPONENT))),
        ("a player lost 4 or more life this turn", happened(LifeLostEvent(), count=4)),
        ("you lost three or more life this turn", happened(LifeLostEvent(actor=YOU), count=3)),
        ("you didn't cast a spell this turn",
         FNot(happened(CastSpellEvent(filter=FAnd(()), actor=YOU)))),
        ("an opponent has cast a blue or black spell this turn",
         happened(CastSpellEvent(
             filter=FOr((FAtom(pred=FAtomPred.COLOR_HAS, color="U"),
                         FAtom(pred=FAtomPred.COLOR_HAS, color="B"))),
             actor=OPPONENT))),
        ("you've cast a historic spell this turn",
         happened(CastSpellEvent(
             filter=FOr((FAtom(pred=FAtomPred.TYPE_EQ, string_value="Artifact"),
                         FAtom(pred=FAtomPred.SUPERTYPE_EQ, string_value="Legendary"),
                         FAtom(pred=FAtomPred.SUBTYPE_EQ, string_value="Saga"))),
             actor=YOU))),
        ("you attacked this turn", YOU_ATTACKED),
        ("an opponent was dealt damage this turn", OPPONENT_DEALT_DAMAGE),
        ("an opponent has been dealt damage this turn", OPPONENT_DEALT_DAMAGE),
        # the shapes M21 already compiles keep their atoms
        ("a creature died this turn", FAtom(pred=FAtomPred.DIED_THIS_TURN)),
        ("you gained 3 or more life this turn", templates_b2a._life_gained_this_turn_ge(3)),
        ("you've gained life this turn", templates_b2a._life_gained_this_turn_ge(1)),
        ("you've cast an instant or sorcery spell this turn",
         FAtom(pred=FAtomPred.INSTANT_OR_SORCERY_CAST_THIS_TURN, who=ControllerRef.YOU)),
    ],
)
def test_condition_phrases(phrase, expected) -> None:
    assert conditions.condition(phrase) == expected


@pytest.mark.parametrize(
    "phrase",
    ["you control a Wizard", "a player lost life last turn", "you've cast another spell this turn"],
)
def test_phrases_outside_the_grammar(phrase) -> None:
    assert conditions.condition(phrase) is None


# ----------------------------------------------------------------------------- 2 B14


def cant_be_countered(subject, **roles) -> Atom:
    pairs = (("condition", subject), ("event", CounteredEvent(subject)), *roles.items())
    return Atom(verb=Verb.PREVENT_EFFECT, args=AtomArgs(pairs=pairs))


def test_this_spell_cant_be_countered(registry) -> None:
    assert only(registry, "This spell can't be countered.") == AbilityOutcome(
        StaticAbility(effect=cant_be_countered(IS_SOURCE))
    )


@pytest.mark.parametrize(
    ("sentence", "subject"),
    [
        ("Creature spells can't be countered.",  # Gaea's Herald
         FAnd((SPELL, FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature")))),
        ("Instant and sorcery spells you control can't be countered.",  # Sphinx of the Final Word
         FAnd((SPELL, YOU, FOr((FAtom(pred=FAtomPred.TYPE_EQ, string_value="Instant"),
                                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Sorcery")))))),
    ],
)
def test_spells_cant_be_countered(registry, sentence, subject) -> None:
    assert only(registry, sentence) == AbilityOutcome(StaticAbility(effect=cant_be_countered(subject)))


def test_spells_you_control_cant_be_countered_this_turn(registry) -> None:
    assert only(registry, "Spells you control can't be countered this turn.") == EffectOutcome(
        cant_be_countered(FAnd((SPELL, YOU)), duration=DurationEot())
    )


def test_bloodthirst(registry) -> None:
    sentence = ("Bloodthirst 3 (If an opponent was dealt damage this turn, this creature enters "
                "with three +1/+1 counters on it.)")
    assert only(registry, sentence) == AbilityOutcome(
        EtBState(initial_counters=((CounterKind.PLUS_1_PLUS_1, QConst(3)),),
                 condition=OPPONENT_DEALT_DAMAGE)
    )


def test_statics_with_a_turn_history_condition(registry) -> None:
    attack = only(registry, "This creature can't attack unless an opponent has been dealt damage "
                            "this turn.")
    assert attack.ability.condition == FNot(OPPONENT_DEALT_DAMAGE)
    assert attack.ability.effect.args.get("event") == DeclareAttackersEvent(filter=IS_SOURCE)
    block = only(registry, "This creature can't be blocked if you've cast a historic spell this turn.")
    assert block.ability.effect.args.get("event") == DeclareBlockersEvent(FAnd(()), blocked=IS_SOURCE)
    enters = only(registry, "Raid — This creature enters with a +1/+1 counter on it if you attacked "
                            "this turn.")
    assert enters == AbilityOutcome(
        EtBState(initial_counters=((CounterKind.PLUS_1_PLUS_1, QConst(1)),), condition=YOU_ATTACKED)
    )


# --------------------------------------------------------------------------- 3 frames


def test_intervening_if_in_a_trigger(registry) -> None:
    sentence = ("At the beginning of your end step, if an opponent lost life this turn, create a "
                "1/1 red Goblin creature token.")
    (match,) = frames.compose(sentence, registry)
    assert match.template.tid == "B13-end-step+if+B11-create-tokens"
    ability = match.outcome.ability
    assert isinstance(ability, TriggeredAbility)
    assert ability.condition == happened(LifeLostEvent(actor=OPPONENT))
    alone = registry.match("Create a 1/1 red Goblin creature token.")[0].outcome.effect
    assert ability.effect == alone


def test_an_ability_word_is_dropped(registry) -> None:
    raid = frames.compose("Raid — When this creature enters, if you attacked this turn, draw a card.",
                          registry)
    plain = frames.compose("When this creature enters, if you attacked this turn, draw a card.",
                           registry)
    assert raid[0].outcome == plain[0].outcome
    assert raid[0].outcome.ability.condition == YOU_ATTACKED


def test_trailing_condition(registry) -> None:
    (match,) = frames.compose("Draw a card if an opponent lost life this turn.", registry)
    draw = registry.match("Draw a card.")[0].outcome.effect
    assert match.outcome == EffectOutcome(
        Conditional(pred=happened(LifeLostEvent(actor=OPPONENT)), then_effect=draw)
    )
    (unless,) = frames.compose("Draw a card unless an opponent lost life this turn.", registry)
    assert unless.outcome.effect.pred == FNot(happened(LifeLostEvent(actor=OPPONENT)))


def test_a_condition_the_grammar_cannot_read_is_refused(registry) -> None:
    assert frames.compose("At the beginning of your end step, if you control a Wizard, draw a card.",
                          registry) == ()
    assert frames.compose("Draw a card if you control a Wizard.", registry) == ()


# ------------------------------------------------------------------------------ 4 B11


def test_target_that_was_dealt_damage_this_turn(registry) -> None:
    outcome = only(registry, "Destroy target creature an opponent controls that was dealt damage "
                             "this turn.")
    target = outcome.effect.args.get("target")
    assert conditions.WAS_DEALT_DAMAGE_THIS_TURN in target.filter.children
    assert OPPONENT in target.filter.children
    # the relative "that" is not a pronoun: the activated frame composes it (Ogre Siegebreaker)
    (ogre,) = frames.compose("{2}{B}{R}: Destroy target creature that was dealt damage this turn.",
                             registry)
    assert ogre.template.tid == "B13-activated+B11-destroy-np"


# ------------------------------------------------------------------------- 5 fallback


@pytest.mark.parametrize("set_code", ["M21", "ZNR", "M20", "KHM"])
def test_cards_that_compiled_before_are_untouched(registry, set_code) -> None:
    without = TemplateRegistry()
    for template in registry.all():
        if template.bucket != "B14":
            without.register(template)
    changed = []
    for raw in ingest_pool(DATA / f"{set_code}.json").values():
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


def test_b14_registers_its_templates() -> None:
    assert {t.tid for t in templates_b14.TEMPLATES} == {
        "B14-this-spell-cant-be-countered",
        "B14-spells-cant-be-countered",
        "B14-spells-cant-be-countered-this-turn",
        "B14-bloodthirst",
        "B14-cant-attack-unless",
        "B14-cant-be-blocked-if",
        "B14-enters-with-counters-if",
    }
