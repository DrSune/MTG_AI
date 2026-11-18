"""The copy wordings (templates_b20, DESIGN_ATOM_ONTOLOGY §18): each fails on the code before the
copy round, which has no CopyOf and no template for them.

- "Create a token that's a copy of <object>[, except ...]." (CREATE_TOKEN of a CopyOf), and as a
  clause under a trigger frame ("that's a copy" and "except it" are the clause's own words);
- "Copy target instant or sorcery spell[ you control]." (a COPY put onto the stack);
- Thousand-Year Storm's trigger (the count is the cast's ORDINAL less one);
- "You may choose new targets for the copy|copies.", folded into the COPY before it;
- "Whenever you draw your second card each turn, <clause>" (the frame Homunculus Horde needs).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from MTG_bot.core.ability_tree import (
    Atom,
    CardDrawnEvent,
    CopyOf,
    FAtom,
    FAtomPred,
    FNot,
    Keyword,
    QBin,
    QProp,
    QPropField,
    SelectorMode,
    SpellAbility,
    TriggeredAbility,
    TurnPhaseEvent,
    Verb,
    ZoneKind,
    canonical_json,
    walk,
)
from MTG_bot.core.compiler.compiler import compile_card
from MTG_bot.core.compiler.coverage import build_full_registry
from MTG_bot.core.compiler.ingest import ingest_pool
from MTG_bot.core.compiler.templates import (
    EffectOutcome,
    NewTargetsOutcome,
    TemplateRegistry,
)

DATA = Path(__file__).resolve().parents[2] / "data"


@pytest.fixture(scope="module")
def registry() -> TemplateRegistry:
    return build_full_registry()


def _effect(registry: TemplateRegistry, sentence: str):
    [match] = registry.match(sentence)
    assert isinstance(match.outcome, EffectOutcome), match
    return match.outcome.effect


def _card(code: str, name: str, registry: TemplateRegistry):
    raw = next(rc for rc in ingest_pool(DATA / f"{code}.json").values() if rc.identity.name == name)
    return compile_card(raw, registry)


@pytest.mark.parametrize(
    ("words", "mode", "filter_has"),
    [
        ("target creature you control", SelectorMode.TARGET, {"Creature", "CONTROLLER_IS"}),
        ("target creature", SelectorMode.TARGET, {"Creature"}),
        ("target permanent", SelectorMode.TARGET, {"IS_PERMANENT"}),
        ("another target nonland permanent you control", SelectorMode.TARGET,
         {"IS_PERMANENT", "Land", "CONTROLLER_IS", "IS_SOURCE"}),
        ("this creature", SelectorMode.CHOOSE, {"IS_SOURCE"}),
    ],
)
def test_a_token_copy_of_an_object(registry, words, mode, filter_has) -> None:
    atom = _effect(registry, f"Create a token that's a copy of {words}.")
    assert atom.verb is Verb.CREATE_TOKEN
    copy = atom.args.get("tokens")
    assert isinstance(copy, CopyOf) and not copy.has_exceptions
    assert copy.source.mode is mode
    seen = {getattr(n, "string_value", None) or n.pred.name
            for n in walk(copy.source.filter)
            if isinstance(n, FAtom)}
    assert filter_has <= seen


def test_the_exceptions_a_token_copy_carries(registry) -> None:
    nightmare = _effect(registry, "Create a token that's a copy of target creature you control, "
                                  "except it's a Nightmare in addition to its other types."
                        ).args.get("tokens")
    assert nightmare.subtypes == ("Nightmare",) and nightmare.source.mode is SelectorMode.TARGET
    # "it" is a record's: a sentence alone cannot tell that the instruction before it moved or
    # made the object (gate round B3, M3a)
    assert registry.match("Create a token that's a copy of it, except it's a Nightmare in "
                          "addition to its other types.") == ()
    assert registry.match("Create a token that's a copy of it.") == ()
    hasty = _effect(registry, "Create a token that's a copy of target creature you control, except "
                              "it has haste and \"At the beginning of the end step, sacrifice this "
                              "token.\"").args.get("tokens")
    assert hasty.keywords == (Keyword.HASTE,)
    [sacrifice] = hasty.abilities
    assert isinstance(sacrifice, TriggeredAbility) and sacrifice.event == TurnPhaseEvent(
        phase=sacrifice.event.phase)  # each end step: no actor
    assert sacrifice.effect.verb is Verb.SACRIFICE
    # an exception the value does not carry leaves the sentence unparsed
    assert registry.match("Create a token that's a copy of target creature you control, except "
                          "it's 1/1.") == ()


def test_sublime_epiphanys_mode_is_the_same_tree(registry) -> None:
    [bullet] = registry.match("• Create a token that's a copy of target creature you control.")
    assert bullet.outcome.effect == _effect(
        registry, "Create a token that's a copy of target creature you control.")


def test_a_copy_of_target_spell(registry) -> None:
    for sentence, yours in (("Copy target instant or sorcery spell.", False),
                            ("Copy target instant or sorcery spell you control.", True)):
        atom = _effect(registry, sentence)
        assert atom.verb is Verb.COPY and atom.args.get("cards") is None
        source = atom.args.get("source").source
        assert source.mode is SelectorMode.TARGET
        assert all(z.kind is ZoneKind.STACK for z in source.zones)
        assert any(isinstance(n, FAtom) and n.pred is FAtomPred.CONTROLLER_IS
                   for n in walk(source.filter)) is yours


def test_target_instant_or_sorcery_spell_is_the_counterspells_selector(registry) -> None:
    """"Copy target instant or sorcery spell." targets with M21 Miscast's bytes (a verified
    counterspell, the same noun phrase): one encoding of "target instant or sorcery spell" (the
    gate's M2: the copy built a bare FOr of the types, without STACK_KIND_EQ SPELL)."""
    miscast = _card("M21", "Miscast", registry).card
    [counter] = [n for n in walk(miscast) if isinstance(n, Atom) and n.verb is Verb.COUNTER_SPELL]
    copy = _effect(registry, "Copy target instant or sorcery spell.")
    assert canonical_json(copy.args.get("source").source) == canonical_json(counter.args.get("target"))


def test_new_targets_fold_into_the_copy_before_them(registry) -> None:
    [match] = registry.match("You may choose new targets for the copies.")
    assert isinstance(match.outcome, NewTargetsOutcome)
    twincast = _card("10E", "Twincast", registry)
    assert not twincast.unparsed
    [spell] = twincast.card.abilities
    assert isinstance(spell, SpellAbility) and spell.effect.args.get("new_targets") is True
    storm = _card("FDN", "Thousand-Year Storm", registry)
    assert not storm.unparsed
    copy = storm.card.abilities[0].effect
    assert copy.args.get("new_targets") is True
    count = copy.args.get("count")
    assert isinstance(count, QBin) and count.left == QProp("event", QPropField.ORDINAL)


def test_new_targets_with_no_copy_before_them_stay_unparsed(registry) -> None:
    # Lithoform Engine: the copy of a triggered ability does not compile, so its "You may choose
    # new targets for the copy." has no COPY to fold into (the instant-or-sorcery one has one).
    engine = _card("ZNR", "Lithoform Engine", registry)
    assert [s for s, _ in engine.unparsed].count("You may choose new targets for the copy.") == 1
    copies = [n for n in walk(engine.card)
              if isinstance(n, Atom) and n.verb is Verb.COPY]
    assert [c.args.get("new_targets") for c in copies] == [True]


def test_trigger_frames_compose_a_copy_clause(registry) -> None:
    """Extravagant Replication (upkeep) and Homunculus Horde (second card drawn) compile whole;
    a clause whose copied object is a pronoun ("a copy of it", "of that creature") stays out."""
    replication = _card("FDN", "Extravagant Replication", registry)
    horde = _card("FDN", "Homunculus Horde", registry)
    assert not replication.unparsed and not horde.unparsed
    [trigger] = [a for a in horde.card.abilities if isinstance(a, TriggeredAbility)]
    assert trigger.event == CardDrawnEvent(
        actor=FAtom(pred=FAtomPred.CONTROLLER_IS, who=trigger.event.actor.who), ordinal=2)
    copy = trigger.effect.args.get("tokens")
    assert copy.source.filter == FAtom(pred=FAtomPred.IS_SOURCE)
    another = replication.card.abilities[0].effect.args.get("tokens").source.filter
    assert FNot(inner=FAtom(pred=FAtomPred.IS_SOURCE)) in another.children
    from MTG_bot.core.compiler.frames import compose

    assert compose("At the beginning of your upkeep, create a token that's a copy of it.",
                   registry) == ()
