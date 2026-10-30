"""Frames (sets round S-3b, KNOWLEDGE /168): trigger or cost + an effect clause that parses alone.

Pinned:
1. identity law, as a differential: over every sentence of M21, ZNR, M20 and KHM that a specific
   template parses as a triggered or activated ability and that a frame also composes, the two
   abilities are byte-identical, except for B-47 (one token carrier's type line);
2. fallback only: a card whose sentences all parsed before is untouched (M21: no card changes);
3. a clause with a pronoun is refused, because its referent lies outside the clause.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from MTG_bot.core.ability_tree import ActivatedAbility, CostLoyalty, TriggeredAbility
from MTG_bot.core.compiler import frames
from MTG_bot.core.compiler.compiler import compile_card
from MTG_bot.core.compiler.coverage import build_full_registry
from MTG_bot.core.compiler.ingest import ingest_pool
from MTG_bot.core.compiler.templates import AbilityOutcome

DATA = Path(__file__).resolve().parents[2] / "data"
SETS = ("M21", "ZNR", "M20", "KHM")
#: B-47 was the one known difference: B3 wrote the Angel token's type line as "Angel" where B11
#: and every other carrier write "Creature — Angel".
# re-pinned 2026-10-30: m21-fidelity wave 4 fixes B-47 in B3 (the executor mints a token from its
# type line, so Speaker of the Heavens' Angel was not a creature); frames and templates now agree
# on every framed ability, so no difference is allowed.
B47: set[str] = set()


@pytest.fixture(scope="module")
def registry():
    return build_full_registry()


def test_frames_rebuild_every_existing_framed_ability(registry) -> None:
    agree, differ = 0, set()
    for code in SETS:
        for raw in ingest_pool(DATA / f"{code}.json").values():
            for sentence in raw.sentences:
                matches = registry.match(sentence)
                if not matches or not isinstance(matches[0].outcome, AbilityOutcome):
                    continue
                composed = frames.compose(sentence, registry)
                if not composed:
                    continue
                if repr(composed[0].outcome) == repr(matches[0].outcome):
                    agree += 1
                else:
                    differ.add(sentence)
    assert differ == B47
    assert agree >= 70  # 73 when this test was written: the comparison must stay meaningful


def test_a_pronoun_keeps_the_sentence_out(registry) -> None:
    assert frames.compose("When this creature enters, put a +1/+1 counter on it.", registry) == ()
    assert frames.compose("When this creature dies, return it to its owner's hand.", registry) == ()
    assert frames.compose("{T}: Tap target creature. It doesn't untap.", registry) == ()
    # "its owner" names an object inside the clause, so it stays
    assert frames.compose("When this creature enters, return target creature to its owner's hand.",
                          registry)


def test_composed_abilities_have_the_frames_shape(registry) -> None:
    etb = frames.compose("When this creature enters, you gain 2 life.", registry)[0].outcome
    assert isinstance(etb.ability, TriggeredAbility)
    alone = registry.match("You gain 2 life.")[0].outcome.effect
    assert repr(etb.ability.effect) == repr(alone)
    loyalty = frames.compose("[−2]: Draw a card.", registry)[0].outcome.ability
    assert isinstance(loyalty, ActivatedAbility)
    assert loyalty.cost.parts == (CostLoyalty(-2),)
    activated = frames.compose("{2}, {T}: Draw a card.", registry)[0].outcome.ability
    assert isinstance(activated, ActivatedAbility) and len(activated.cost.parts) == 2


@pytest.mark.parametrize("set_code", SETS)
def test_cards_that_compiled_before_are_untouched(registry, set_code, monkeypatch) -> None:
    real = frames.compose
    changed = []
    for raw in ingest_pool(DATA / f"{set_code}.json").values():
        monkeypatch.setattr(frames, "compose", lambda _sentence, _registry: ())
        try:
            before = compile_card(raw, registry)
        except Exception:  # noqa: BLE001, S112 - a card that cannot compile is outside this property
            continue
        finally:
            monkeypatch.setattr(frames, "compose", real)
        after = compile_card(raw, registry)
        if repr(after.card) == repr(before.card) and after.unparsed == before.unparsed:
            continue
        changed.append(raw.identity.name)
        # Step 2d only reads a sentence that nothing parsed before, on either face
        unparsed = (*before.unparsed, *before.back_face_unparsed)
        assert any(real(s, registry) for s, _ in unparsed), raw.identity.name
    if set_code == "M21":
        assert changed == []
