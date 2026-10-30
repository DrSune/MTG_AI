"""Ontology R5-11 (docs/DESIGN_ATOM_ONTOLOGY.md §10, gate round 3 GO):
``TokenSpec.colors: tuple[str, ...]`` replaces the one-letter ``color``.
WUBRG letters only, WUBRG order (CR 105.1), omitted when colourless. Fixes
BACKLOG B-82: Experimental Overload's "blue and red Weird" was colourless, so
protection from multicolored did not stop it.
"""

from __future__ import annotations

import pytest

from MTG_bot.core.ability_tree import (
    DurationEot,
    FAtom,
    FAtomPred,
    Keyword,
    KeywordAbility,
    QConst,
    TokenSpec,
    Verb,
    from_dict,
    to_dict,
)
from MTG_bot.core.compiler.coverage import build_full_registry
from MTG_bot.core.executor.games import compile_supply
from MTG_bot.core.executor.legality import block_pair_blocked_reason
from MTG_bot.core.executor.quantity import eval_filter
from MTG_bot.core.state import ZONE_BATTLEFIELD
from MTG_bot.core.test_executor_verbs import ExecutorCase, atom, target_sel


def weird(colors: tuple[str, ...]) -> TokenSpec:
    return TokenSpec(
        name="Weird",
        type_line="Creature — Weird",
        types=("Creature",),
        subtypes=("Weird",),
        power=QConst(2),
        toughness=QConst(2),
        keywords=(),
        abilities=(),
        colors=colors,
    )


# ------------------------------------------------------------------- IR


def test_colors_are_canonical_in_wubrg_order() -> None:
    assert weird(("R", "U")).colors == ("U", "R")
    assert weird(("R", "U")) == weird(("U", "R"))  # same meaning, same bytes
    assert weird(("G", "W", "B")).colors == ("W", "B", "G")


@pytest.mark.parametrize("bad", [("C",), ("W", "W"), ("u",), "UR", (7,)])
def test_colors_are_distinct_wubrg_letters(bad) -> None:
    with pytest.raises(ValueError, match="colors must be"):
        weird(bad)


def test_serialization_omits_the_empty_set_and_is_strict() -> None:
    colourless = to_dict(weird(()))
    assert "colors" not in colourless and "color" not in colourless
    d = to_dict(weird(("U", "R")))
    assert d["colors"] == ["U", "R"]
    assert from_dict("TokenSpec", d) == weird(("U", "R"))
    # stale bytes fail loud (the R0 law: no silent migration)
    legacy = dict(d, color="U")
    del legacy["colors"]
    with pytest.raises(ValueError, match=r"unknown fields \['color'\]"):
        from_dict("TokenSpec", legacy)


def test_the_weird_compiles_blue_and_red() -> None:
    sentence = (
        "Create an X/X blue and red Weird creature token, where X is the number "
        "of instant and sorcery cards in your graveyard."
    )
    (match,) = build_full_registry().match(sentence)
    token = match.outcome.effect.args.get("tokens")
    assert token.colors == ("U", "R")


# ------------------------------------------------------------- engine


class TestMulticolouredToken(ExecutorCase):
    def test_both_colours_reach_filters_and_protection(self) -> None:
        # CR 105.2/111.4: the token is every colour its spec prints. COLOR_HAS
        # sees each, COLOR_COUNT_GE 2 makes it multicoloured, and an attacker
        # with protection from multicolored can't be blocked by it (702.16f).
        before = set(self.world.players[self.p1].zone(ZONE_BATTLEFIELD).entries)
        self.ex.execute(
            atom(Verb.CREATE_TOKEN, tokens=weird(("R", "U")), count=QConst(1)),
            source=self.beta,
            controller=self.p1,
        )
        (token,) = set(self.world.players[self.p1].zone(ZONE_BATTLEFIELD).entries) - before
        self.assertEqual(self.world.cards[token].identity.colors, ("U", "R"))
        ctx = self.ex._ctx(source=self.alpha, controller=self.p0, bindings=None, decisions=())
        for colour, has in (("U", True), ("R", True), ("G", False)):
            self.assertEqual(
                eval_filter(FAtom(FAtomPred.COLOR_HAS, color=colour), token, ctx), has
            )
        multicoloured = FAtom(FAtomPred.COLOR_COUNT_GE, count=QConst(2))
        self.assertTrue(eval_filter(multicoloured, token, ctx))
        self.assertIsNone(block_pair_blocked_reason(self.ex, token, self.alpha))
        self.ex.apply_effect(
            atom(
                Verb.GRANT_ABILITY,
                target=target_sel(),
                ability=KeywordAbility(Keyword.PROTECTION, (multicoloured,)),
                duration=DurationEot(),
            ),
            source=self.alpha,
            controller=self.p0,
            bindings={"target": [self.alpha]},
        )
        self.assertIsNotNone(block_pair_blocked_reason(self.ex, token, self.alpha))


# ----------------------------------------------- FDN records (schema rename)


def test_fdn_supplies_compile_after_the_record_rename() -> None:
    # R5-11 renamed the key inside three FDN records' mapped trees (coordinator
    # ruling 2026-10-30, verified blocks untouched): the strict decoder reads
    # them, so both supplies compile, and the two verified ones are honestly
    # out of the verified supply until they are re-verified.
    castable = compile_supply("castable", "FDN")
    verified = compile_supply("verified", "FDN")
    names = {verified.metas[oid].name for oid in verified.deckable}
    for card in ("Imperious Perfect", "Stroke of Midnight"):
        assert card not in names
        oid = next(o for o, m in castable.metas.items() if m.name == card)
        assert oid not in verified.verified_ids
    caracal = next(o for o, m in castable.metas.items() if m.name == "Regal Caracal")
    assert caracal in castable.metas
