"""The ``compiled`` deal pool holds only cards whose whole text is in the tree."""

from __future__ import annotations

import pytest

from MTG_bot.core.executor.games import compile_supply


def _partial(supply, oid: str) -> bool:
    result = supply.pool.results[oid]
    return bool(result.unparsed or result.ambiguities or result.back_face_unparsed)


def test_on_m21_every_castable_card_but_furious_rise_is_fully_compiled() -> None:
    """Furious Rise's "You may play that card until you exile another card with this enchantment."
    is unparsed (ontology round R13: a window that ends on an event no duration carries), so the
    card is castable with that sentence missing and stays out of the ``compiled`` pool."""
    castable = compile_supply("castable", "M21")
    compiled = compile_supply("compiled", "M21")
    left_out = {castable.metas[oid].name for oid in set(castable.deckable) - set(compiled.deckable)}
    assert left_out == {"Furious Rise"}
    assert set(compiled.deckable) <= set(castable.deckable)


@pytest.mark.parametrize("set_code", ["ZNR", "M20"])
def test_on_a_partly_compiled_set_the_pool_drops_exactly_the_partial_cards(set_code: str) -> None:
    castable = compile_supply("castable", set_code)
    compiled = compile_supply("compiled", set_code)
    assert set(compiled.deckable) == {
        oid for oid in castable.deckable if not _partial(castable, oid)
    }
    assert 0 < len(compiled.deckable) < len(castable.deckable)


def test_an_unknown_mode_still_raises() -> None:
    with pytest.raises(ValueError, match="compiled"):
        compile_supply("fully", "M21")
