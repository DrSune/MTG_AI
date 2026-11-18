"""The readout runner on a small untrained network: what it reads at a puzzle's root, and how a
category's twin-consistent pass rate is counted."""

from __future__ import annotations

import pytest

from MTG_bot.core.executor.games import get_supply
from tools.puzzles import puzzle as P
from tools.puzzles import runner as R
from tools.selfplay import features as FT
from tools.selfplay import model as M


@pytest.fixture(scope="module")
def slot_table():
    supply = get_supply("verified", "M21")
    table = FT.CardTable.from_records({oid: r.card for oid, r in supply.pool.results.items()})
    net = M.build(table, d=16, layers=1, heads=2, ff=32).eval()
    return M.LocalSlot({R.SPEC: net}), table


def test_the_root_is_read_as_a_game_asks_it(slot_table) -> None:
    slot, table = slot_table
    pz = P.load(P.SUITE / "b1_counter_the_answer_lethal.json")
    row = R.read(slot, table, pz, search_seeds=1)
    assert row["kind"] == "priority" and row["options"] == ["PASS", "cast:cancel"]
    assert sum(row["probs"]) == pytest.approx(1.0, abs=1e-3)
    assert row["p_right"] == row["probs"][1]
    assert row["pass"] == (row["greedy"] == "cast:cancel")
    assert row["unknown_cards"] == 0
    assert len(row["searched"]) == 1 and row["searched"][0] in row["options"]


def test_a_category_passes_only_when_both_twins_do() -> None:
    puzzles = {n: {"category": "X", "twin": t} for n, t in (("a", "b"), ("b", "a"), ("c", "d"), ("d", "c"))}

    def row(name, ok, value, solver):
        return {"puzzle": name, "pass": ok, "p_right": 1.0 if ok else 0.0, "value": value,
                "solver_value": solver}

    rows = [row("a", True, 0.9, 1.0), row("b", True, 0.4, 0.5),   # both right, values in order
            row("c", True, 0.2, 1.0), row("d", False, 0.6, 0.5)]  # one twin wrong, values reversed
    s = R.summarise(rows, puzzles)["X"]
    assert s["pairs"] == 2 and s["twin_consistent"] == 0.5 and s["single_pass"] == 0.75
    assert s["value_order"] == 0.5 and s["searched_pass"] is None
