"""The suite's puzzles stay well formed and keep their proven answers.

Every puzzle names a twin that names it back, whose right move is a different one. Its stored
solver record (``solver.py --write``) gives the answer as the best options, and the cheap ones are
solved again here: an engine or card change that moves a value fails this test, and the puzzle is
read again before its answer is trusted.
"""

from __future__ import annotations

import pytest

from tools.puzzles import puzzle as P

PATHS = sorted(P.SUITE.glob("*.json"))
NAMES = {p.stem for p in PATHS}
#: Puzzles whose recorded solve took longer are checked from their record only.
RESOLVE_SECONDS = 5.0


def test_the_first_wave_has_eight_twin_pairs() -> None:
    # PLAN_PLANNING §4's first wave: A 2 pairs, B1, B2, B3 one each, C 2 pairs, D one.
    cats = sorted(P.load(p)["category"] for p in PATHS)
    assert cats == sorted(["A"] * 4 + ["B1"] * 2 + ["B2"] * 2 + ["B3"] * 2 + ["C"] * 4 + ["D"] * 2)


@pytest.mark.parametrize("path", PATHS, ids=[p.stem for p in PATHS])
def test_a_puzzle_is_proven_and_has_its_twin(path) -> None:
    pz = P.load(path)
    assert pz["name"] == path.stem
    P.check_cards(pz)
    twin = P.load(P.SUITE / f"{pz['twin']}.json")
    assert twin["twin"] == pz["name"] and twin["category"] == pz["category"]
    assert not set(twin["answer"]) & set(pz["answer"]), "the twin's right move must change"
    assert pz["grade"] in ("proven", "dominant")
    rec = pz["solver"]
    assert sorted(rec["best"]) == sorted(pz["answer"])
    assert set(pz["answer"]) <= set(rec["values"])
    if rec["seconds"] <= RESOLVE_SECONDS:
        again = P.solver_record(pz, P.solve(pz))
        assert again["values"] == rec["values"]
