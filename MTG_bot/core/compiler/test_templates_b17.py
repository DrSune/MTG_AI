"""The printed wordings of a colour or a creature type chosen as a permanent enters (templates_b17,
ontology round R9).

Pinned:
1. every sentence of the 19 sets in the family is read, the two the module names excepted: the
   choice "As this <permanent> enters, choose a color|creature type." (18 sentences), the cast
   trigger, the anthem, the reveal;
2. the trees: the choice is Runed Halo's EtBState CHOOSE_NAME with the ``quality`` role; the reads
   are NAME_CHOSEN of that quality in the spell's description, the anthem's selector (with "Other"
   the source left out, without it not) and Garruk's Harbinger's reveal;
3. the frame B13-cast-chosen composes any clause that parses alone with the template's own head;
4. whole cards: M20 Diamond Knight and Icon of Ancestry, FDN and M19 Diamond Mare, ORI Prism Ring
   and KHM Rally the Ranks compile whole;
5. a read whose choice did not compile, and a choice whose reader did not, is a shape gap of its
   card, never a ValueError that would stop a whole-set compile (CR 607.2d,
   ability_tree.chosen_quality_fault).
"""

from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path

import pytest

from MTG_bot.core.ability_tree import (
    CastSpellEvent,
    ControllerRef,
    EtBState,
    FAnd,
    FAtom,
    FAtomPred,
    FNot,
    OptionalEffect,
    SelectorMode,
    StaticAbility,
    TriggeredAbility,
    Verb,
)
from MTG_bot.core.compiler import frames, templates_b17
from MTG_bot.core.compiler.compiler import compile_card
from MTG_bot.core.compiler.coverage import build_full_registry
from MTG_bot.core.compiler.ingest import ingest_pool
from MTG_bot.core.compiler.templates import (
    AbilityOutcome,
    TemplateRegistry,
)
from MTG_bot.core.errors import StateCorruptionError

DATA = Path(__file__).resolve().parents[2] / "data"
SETS = ("M21", "ZNR", "M20", "KHM", "10E", "M10", "M11", "M12", "M13", "M14", "M15", "ORI", "M19",
        "DOM", "WAR", "FDN", "ELD", "THB", "IKO")
YOU = FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU)
CREATURE = FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature")
COLOR = FAtom(pred=FAtomPred.NAME_CHOSEN, string_value="COLOR")
TYPE = FAtom(pred=FAtomPred.NAME_CHOSEN, string_value="CREATURE_TYPE")
#: The family's wordings, broader than the templates: what the census looks for.
FAMILY = re.compile(r"\bAs .+ enters, choose a (?:color|creature type)\b|\bof the chosen (?:color|type)\b")
NOT_READ = {
    "As it enters, choose a color.",  # Uncharted Haven: no context to tell "it" is the card
    "As The Ringhart Crest enters, choose a creature type.",  # a face named in full
}


@pytest.fixture(scope="module")
def registry() -> TemplateRegistry:
    return build_full_registry()


def only(registry: TemplateRegistry, sentence: str):
    matches = registry.match(sentence)
    assert len(matches) == 1, [m.template.tid for m in matches]
    return matches[0]


def card(code: str, name: str):
    (raw,) = [r for r in ingest_pool(DATA / f"{code}.json").values() if r.identity.name == name]
    return raw


# --------------------------------------------------------------------- 1 the family's sentences


def test_every_sentence_of_the_family_is_read(registry) -> None:
    read: dict[str, set[str]] = {}
    unread: set[str] = set()
    for code in SETS:
        for raw in ingest_pool(DATA / f"{code}.json").values():
            faces = [raw.sentences, raw.back_face.sentences if raw.back_face else ()]
            for sentence in (s for face in faces for s in face):
                if not FAMILY.search(sentence):
                    continue
                matches = registry.match(sentence) or frames.compose(sentence, registry)
                if matches:
                    tid = matches[0].template.tid.split("+")[0]
                    read.setdefault(tid, set()).add(f"{code} {raw.identity.name}")
                else:
                    unread.add(sentence)
    # 20 printings of 17 cards; Uncharted Haven's "As it enters" and the Crest are not read
    assert len(read["B17-etb-choose-quality"]) == 20
    assert read["B17-cast-chosen-counter"] == {"M20 Diamond Knight"}
    assert read["B13-cast-chosen"] == {"M19 Diamond Mare", "FDN Diamond Mare", "ORI Prism Ring"}
    assert read["B17-chosen-anthem"] == {
        "M20 Icon of Ancestry", "KHM Rally the Ranks", "M15 Obelisk of Urd", "ELD Heraldic Banner",
        "FDN Heraldic Banner", "M12 Adaptive Automaton", "FDN Adaptive Automaton"}
    assert read["B17-reveal-chosen-type"] == {"M20 Icon of Ancestry"}
    # the rest need a piece no component expresses yet (BACKLOG, "a quality chosen as a
    # permanent enters"): mana of the chosen colour, "is the chosen type", a spend restriction,
    # a counter-scaled anthem, copying a permanent spell, a prevention shield
    assert NOT_READ <= unread
    assert all(not s.startswith("As this ") for s in unread)


# ------------------------------------------------------------------------------ 2 the trees


@pytest.mark.parametrize(("word", "quality"), [("color", "COLOR"), ("creature type", "CREATURE_TYPE")])
@pytest.mark.parametrize("permanent", ["artifact", "creature", "enchantment", "land"])
def test_the_choice_is_the_halos_entering_state_with_a_quality(registry, word, quality, permanent):
    outcome = only(registry, f"As this {permanent} enters, choose a {word}.").outcome
    assert isinstance(outcome, AbilityOutcome) and isinstance(outcome.ability, EtBState)
    choose = outcome.ability.effect
    assert choose.verb is Verb.CHOOSE_NAME and choose.args.pairs == (("quality", quality),)
    halo = only(registry, "As this enchantment enters, choose a card name.").outcome.ability
    assert halo == EtBState(effect=replace(choose, args=replace(choose.args, pairs=())))


def test_the_cast_trigger_reads_the_spells_colour(registry) -> None:
    ability = only(registry, "Whenever you cast a spell of the chosen color, put a +1/+1 counter "
                             "on this creature.").outcome.ability
    assert isinstance(ability, TriggeredAbility)
    assert ability.event == CastSpellEvent(filter=COLOR, actor=YOU)
    weird = only(registry, "Whenever you cast a noncreature spell, put a +1/+1 counter on this "
                           "creature.").outcome.ability
    assert ability.effect == weird.effect  # Spellgorger Weird's counter on its source


@pytest.mark.parametrize(("other", "word", "chosen"), [
    ("", "type", TYPE), ("Other c", "type", TYPE), ("", "color", COLOR)])
def test_the_anthem_narrows_creatures_you_control_to_the_chosen_quality(registry, other, word,
                                                                        chosen) -> None:
    head = other or "C"
    ability = only(registry, f"{head}reatures you control of the chosen {word} get +1/+1."
                   ).outcome.ability
    assert isinstance(ability, StaticAbility)
    target = ability.effect.args.get("target")
    assert target.mode is SelectorMode.ALL
    children = {CREATURE, YOU, chosen}
    if other:
        children.add(FNot(inner=FAtom(pred=FAtomPred.IS_SOURCE)))  # "other": never the source
    assert set(target.filter.children) == children


def test_the_reveal_is_garruks_harbingers_with_the_chosen_type(registry) -> None:
    effect = only(registry, "You may reveal a creature card of the chosen type from among them and "
                            "put it into your hand.").outcome.effect
    harbinger = only(registry, "You may reveal a creature card or Garruk planeswalker card from "
                               "among them and put it into your hand.").outcome.effect
    assert isinstance(effect, OptionalEffect) and isinstance(harbinger, OptionalEffect)
    (reveal, move), (h_reveal, h_move) = effect.inner.steps, harbinger.inner.steps
    assert reveal == h_reveal
    assert move.args.get("cards").filter == FAnd(children=(CREATURE, TYPE))
    assert move.args.get("destination") == h_move.args.get("destination")


# ------------------------------------------------------------------------------ 3 the frame


def test_the_frame_composes_a_clause_after_the_templates_head(registry) -> None:
    (composed,) = frames.compose("Whenever you cast a spell of the chosen color, you gain 1 life.",
                                 registry)
    assert composed.template.tid == "B13-cast-chosen+B4-gain-life-n"
    ability = composed.outcome.ability
    assert ability.event == CastSpellEvent(filter=COLOR, actor=YOU)
    assert ability.effect == only(registry, "You gain 1 life.").outcome.effect
    # a pronoun's referent is outside the clause (Reflections of Littjara's "copy that spell")
    assert frames.compose("Whenever you cast a spell of the chosen type, copy that spell.",
                          registry) == ()


# ---------------------------------------------------------------------------- 4 whole cards


@pytest.mark.parametrize(("code", "name"), [
    ("M20", "Diamond Knight"), ("M20", "Icon of Ancestry"), ("FDN", "Diamond Mare"),
    ("M19", "Diamond Mare"), ("ORI", "Prism Ring"), ("KHM", "Rally the Ranks")])
def test_whole_cards(registry, code, name) -> None:
    result = compile_card(card(code, name), registry)
    assert not result.unparsed, result.unparsed
    choices = [a for a in result.card.abilities if isinstance(a, EtBState)]
    assert len(choices) == 1 and choices[0].effect.verb is Verb.CHOOSE_NAME


# ------------------------------------------------------------------------- 5 a read alone


def test_a_read_whose_choice_did_not_compile_is_a_shape_gap(registry) -> None:
    raw = card("KHM", "Rally the Ranks")
    alone = replace(raw, sentences=raw.sentences[1:])  # the anthem only
    with pytest.raises(StateCorruptionError, match="no CHOOSE_NAME of the same object chooses"):
        compile_card(alone, registry)


@pytest.mark.parametrize(("code", "name"), [("10E", "Voice of All"), ("FDN", "Secluded Courtyard")])
def test_a_choice_whose_reader_did_not_compile_is_a_shape_gap(registry, code, name) -> None:
    """A choice nothing reads would be a phantom ask: Voice of All's "protection from the chosen
    color" and Secluded Courtyard's spend restriction do not compile, so the cards are refused
    (on the base both were dealt partly, the Courtyard's any-colour mana unrestricted)."""
    with pytest.raises(StateCorruptionError, match="that nothing on its object reads"):
        compile_card(card(code, name), registry)


def test_b17_registers_its_templates() -> None:
    assert {t.tid for t in templates_b17.TEMPLATES} == {
        "B17-etb-choose-quality",
        "B17-cast-chosen-counter",
        "B17-chosen-anthem",
        "B17-reveal-chosen-type",
    }
