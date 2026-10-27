"""The ``compiled`` deal pool holds only cards whose whole text is in the tree (B-28, /159)."""

from __future__ import annotations

import pytest

from MTG_bot.core.executor.games import compile_supply


def _partial(supply, oid: str) -> bool:
    result = supply.pool.results[oid]
    return bool(result.unparsed or result.ambiguities or result.back_face_unparsed)


def test_on_m21_every_castable_card_is_fully_compiled() -> None:
    assert compile_supply("compiled", "M21").deckable == compile_supply("castable", "M21").deckable


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
