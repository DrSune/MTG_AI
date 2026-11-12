"""The line-value instrument (tools/selfplay/linevalue.py, PLAN_CEILING §14.2): a null line reads
exactly 0 on shared futures, the same seeds give the same numbers on distinct futures, forcing
changes the move, a line never legal gives no states, and the two families pick their steps."""

from __future__ import annotations

import json
from types import SimpleNamespace

import numpy as np
import pytest
import torch

from MTG_bot.bench.protocol import Ask, Option
from MTG_bot.core.executor.games import get_supply
from MTG_bot.core.executor.menu import menu
from tools.selfplay import features as FT
from tools.selfplay import linevalue as LV
from tools.selfplay import model as M
from tools.selfplay import search as S


class _KeepSlot(M.LocalSlot):
    """A small random network that keeps every opening hand: untrained, it mulligans to zero
    greedily, 34 decisions, and the playouts here hand over to the heuristic after 8."""

    def infer(self, req: tuple):
        feats = req[5]
        if int(feats["ask_i"][0]) != FT.ASK_INDEX["mulligan"]:
            return super().infer(req)
        keep = int(np.flatnonzero(feats["opts_i"][:, 0] == FT.OPT_INDEX["keep"])[0])
        want = req[6] if len(req) > 6 else 0
        return keep if want == 0 else (keep, 0.0) if want == 1 else (
            keep, 0.0, [float(i == keep) for i in range(len(feats["opts_i"]))])


@pytest.fixture(scope="module")
def table() -> FT.CardTable:
    supply = get_supply("castable")
    return FT.CardTable.from_records({oid: r.card for oid, r in supply.pool.results.items()})


@pytest.fixture(scope="module")
def slot(table) -> _KeepSlot:
    torch.manual_seed(0)
    net = M.build(table, d=32, layers=1, heads=4, ff=64)
    for p in net.parameters():  # a fresh network's policy head is zero: every option would tie
        p.data.normal_(0, 0.1)
    return _KeepSlot({LV.SPEC: net.eval()})


@pytest.fixture(autouse=True)
def _short(monkeypatch):
    monkeypatch.setattr(S, "MAX_SIM_DECISIONS", 8)  # then the heuristic plays on: fast


def _run(slot, table, line, greedy: bool, states: int = 2, futures: int = 2) -> dict:
    probe = LV.Probe(slot, table, line, pool_mode="castable", greedy=greedy, tops=2)
    return LV.run(probe, states=states, per_game=2, games=4, deal0=5, futures=futures)


def _ranked(slot, table, worst: bool = False) -> LV.Line:
    """The line "the policy's top choice" (``worst``: its least preferred option) at every
    decision."""
    def step(ask, obs):
        feats = FT.encode(obs.executor, ask.seat, ask, table, obs.ctx)
        _, _, probs = slot.infer((0, ask.seat, LV.SPEC, True, False, feats, 2))
        return [(min if worst else max)(range(len(probs)), key=probs.__getitem__)]

    return LV.Line("worst" if worst else "top", step)


@pytest.mark.parametrize("greedy", [True, False])
def test_the_null_line_reads_zero_on_shared_futures(slot, table, greedy) -> None:
    """Forcing what the policy plays anyway changes nothing: greedily its top choice; in sampled
    play any option (the forced move is then the policy's own draw). In every future the three
    branches end alike and the value head reads them alike at each turn top."""
    line = _ranked(slot, table) if greedy else LV.Line("any", lambda ask, obs: list(range(len(ask.options))))
    rep = _run(slot, table, line, greedy)
    assert rep["measured"] == 2 and rep["crashes"] == {}
    for r in rep["per_state"]:
        assert r["futures"] == 2 and r["z"]["first"] == r["z"]["through"] == r["z"]["policy"]
        assert len(r["reads"]) == 2
        assert all(x["first"] == x["through"] == x["policy"] for x in r["reads"])
    assert rep["value"]["first"]["mean"] == rep["value"]["through"]["mean"] == 0.0
    assert rep["follow"]["through"]["forced"] > 0  # the null line was forced, and still read 0


def test_the_same_seeds_give_the_same_numbers_on_distinct_futures(slot, table) -> None:
    """Two runs from one master seed agree to the last digit (sampled play: collection, the
    reservoir, the futures and the moves all draw). A future replayed is the same game; two
    futures of a state are different games."""
    line = _ranked(slot, table, worst=True)
    reps = []
    for _ in range(2):
        rep = _run(slot, table, line, False, states=1)
        rep.pop("cost")
        reps.append(json.dumps(rep, sort_keys=True))
    assert reps[0] == reps[1]
    probe = LV.Probe(slot, table, line, pool_mode="castable", greedy=False, tops=2)
    st = probe.collect(1, 1, 4, 5)[0][0]
    a, b, c = (probe.branch(st, "policy", f) for f in (0, 0, 1))
    assert a == b and a["reads"] != c["reads"]


def test_forcing_plays_the_step_where_the_policy_would_not(slot, table) -> None:
    """The line "the policy's least preferred option", greedy: the forced branches answer the kept
    decision with it and the policy's branch with its top choice; A* forces every later step,
    A1 none."""
    rep = _run(slot, table, _ranked(slot, table, worst=True), True, futures=1)
    assert rep["measured"] == 2 and rep["root_changed"] == 1.0
    for r in rep["per_state"]:
        assert r["top"] not in r["step"]
        assert r["root"]["first"] == r["root"]["through"] == r["step"]
        assert r["root"]["policy"] == [r["top"]]
    fo = rep["follow"]
    assert fo["through"]["forced"] == fo["through"]["steps"] > 0
    assert fo["first"]["forced"] == fo["policy"]["forced"] == 0


@pytest.mark.parametrize("line", [LV.Line("never legal", lambda ask, obs: []),
                                  LV.Line("never begun", lambda ask, obs: [0], lambda ask, obs: False)])
def test_a_line_never_legal_yields_no_states(slot, table, line) -> None:
    """No step, or steps that never begin the line (only follow-through): no state, no crash."""
    rep = _run(slot, table, line, False, states=3)
    assert rep["states"] == 0 and rep["unforced"]["games"] == 4 and rep["unforced"]["eligible"] == 0
    assert rep["value"]["first"] == {"mean": None, "se": None, "n": 0} and rep["critic"] == []
    assert LV.table(rep)


def test_the_two_families_pick_their_steps() -> None:
    """cast_line takes the card's cast rows. order_line casts a consumer while a producer could be
    cast instead (the line begins there), the producers once a consumer is out (its
    follow-through), and nothing while the order is not at stake."""
    from MTG_bot.bench.test_router import _arranged

    vito, revitalize, lands = "Vito, Thorn of the Dusk Rose", "Revitalize", ("Swamp",) * 3 + ("Plains",) * 2
    ids = {m.name: o for o, m in get_supply("castable").metas.items()}
    order = LV.order_line(frozenset({ids[vito]}), frozenset({ids[revitalize]}), "vito first")
    cast = LV.cast_line(frozenset({ids[revitalize]}), revitalize)

    def steps(line, hand, field):
        game, _ = _arranged(hand0=hand, field0=field)
        ex = game.executor
        options = (Option("PASS", "PASS"),) + tuple(
            Option(r.token, r.token) for r in menu(ex, game.world.player_order[0]))
        ask, obs = Ask(seat=0, kind="act", site="act", prompt="", options=options), SimpleNamespace(executor=ex)
        names = [game.name_of(FT._handle(options[i].token[5:])) for i in line.step(ask, obs)]
        return names, line.begins is None or line.begins(ask, obs)

    assert steps(order, (vito, revitalize), lands) == ([vito], True)
    assert steps(cast, (vito, revitalize), lands) == ([revitalize], True)
    assert steps(order, (revitalize,), lands + (vito,)) == ([revitalize], False)
    assert steps(order, (vito,), lands) == ([], True)
