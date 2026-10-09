"""Tests for gameplay eval v2 (full-agent seats).

Fast lane: pure-python checks for the seat resolver, the heuristic agent's
attack/block/act/number decisions and the summarizer's per-kind + leverage
math; one end-to-end game (BC vs HEURISTIC, tiny turn cap) asserts the
v2 JSON contract and the 0-illegal engine gate."""

from __future__ import annotations

import json
from types import SimpleNamespace

from MTG_bot.core.identity import Handle
from tools.eval.gameplay_eval_v2 import (
    HeuristicTeacher,
    main,
    resolve_seat,
    site_kind,
    summarize_matchup,
)
from tools.training.collector import AskContext

HANDLE_WORDS = {"card:0", "card:3", "card:9", "player:0", "player:1"}


class _StubExec:
    def controller_of(self, handle: Handle) -> Handle:
        return Handle("player", 1) if str(handle) == "card:3" else Handle("player", 0)


_GAME = SimpleNamespace(executor=_StubExec())
_SEATS = ["player:0", "player:1"]


def test_resolve_seat_handles_inside_tags() -> None:
    # handles carry colons: attack:card:3:12 -> controller of card:3 = seat 1
    assert resolve_seat("attack:card:3:12", _GAME, _SEATS, 0, HANDLE_WORDS) == 1
    # trample:card:0:2:12 -> card:0 is controlled by seat 0
    assert resolve_seat("trample:card:0:2:12", _GAME, _SEATS, 1, HANDLE_WORDS) == 0
    # cw:player:1:<digest> -> the asked seat itself
    assert resolve_seat("cw:player:1:abc123", _GAME, _SEATS, 0, HANDLE_WORDS) == 1
    # generic site, no handle -> active-player fallback (v1 semantics)
    assert resolve_seat("may:draw:7", _GAME, _SEATS, 1, HANDLE_WORDS) == 1


def test_site_kind() -> None:
    assert site_kind("attack:card:0:3") == "attack"
    assert site_kind("block:card:0:3") == "block"
    assert site_kind("cw:player:0:ab") == "cw"
    assert site_kind("act:main") == "act"
    assert site_kind("target:select") == "target"
    assert site_kind("may:foo") == "may"


def _w(**extra) -> dict:
    base = {"battlefield": [[], []], "lives": [20, 20], "_seat": 0, "_pt": {}}
    base.update(extra)
    return base


def test_heuristic_attack_declines_only_pure_loss() -> None:
    t = HeuristicTeacher()
    # blocker 3/3 vs my 2/2: it survives, I die -> DECLINE
    ctx = AskContext(
        vocab="attack:card:0:5",
        candidates=("ATTACK", "DECLINE"),
        world=_w(
            _pt={"card:0": [2, 2], "card:9": [3, 3]},
            battlefield=[[], [["card:9"]]],
        ),
    )
    assert t.decide(ctx) == 1
    # blocker 0/1 trades away -> ATTACK
    ctx2 = AskContext(
        vocab="attack:card:0:5",
        candidates=("ATTACK", "DECLINE"),
        world=_w(
            _pt={"card:0": [2, 2], "card:9": [0, 1]},
            battlefield=[[], [["card:9"]]],
        ),
    )
    assert t.decide(ctx2) == 0
    # tapped blocker cannot answer -> ATTACK
    ctx3 = AskContext(
        vocab="attack:card:0:5",
        candidates=("ATTACK", "DECLINE"),
        world=_w(
            _pt={"card:0": [2, 2], "card:9": [3, 3]},
            battlefield=[[], [["card:9", "tapped"]]],
        ),
    )
    assert t.decide(ctx3) == 0


def test_heuristic_block_rules() -> None:
    t = HeuristicTeacher()
    # free kill: my 3/3 vs 2/2 attacker -> block it
    ctx = AskContext(
        vocab="block:card:0:5",
        candidates=("card:7", "NONE"),
        world=_w(_pt={"card:0": [3, 3], "card:7": [2, 2]}),
    )
    assert t.decide(ctx) == 0
    # suicide (1/1 into 5/5, no lethal) -> NONE
    ctx2 = AskContext(
        vocab="block:card:0:5",
        candidates=("card:7", "NONE"),
        world=_w(_pt={"card:0": [1, 1], "card:7": [5, 5]}),
    )
    assert t.decide(ctx2) == 1
    # lethal incoming: 2 life vs a 4-power attacker -> block to survive
    ctx3 = AskContext(
        vocab="block:card:0:5",
        candidates=("card:7", "NONE"),
        world=_w(
            _pt={"card:0": [1, 1], "card:7": [4, 4]},
            lives=[2, 20],
        ),
    )
    assert t.decide(ctx3) == 0


def test_heuristic_act_and_number_surfaces() -> None:
    t = HeuristicTeacher()
    # act menu: land first
    ctx = AskContext(
        vocab="act:main",
        candidates=("PASS", "card:0", "card:3"),
        world=_w(
            _cmc={"card:0": 1, "card:3": 5},
            _lands=["card:0"],
            _acts=[],
        ),
    )
    assert t.decide(ctx) == 1
    # no land: highest CMC castable
    ctx2 = AskContext(
        vocab="act:main",
        candidates=("PASS", "card:0", "card:3"),
        world=_w(_cmc={"card:0": 1, "card:3": 5}, _lands=[], _acts=[]),
    )
    assert t.decide(ctx2) == 2
    # numeric surface (trample split): minimum to blockers
    ctx3 = AskContext(
        vocab="trample:card:0:0:5",
        candidates=("2", "3", "4"),
        world=_w(),
    )
    assert t.decide(ctx3) == 0
    # cw window: first non-PASS
    ctx4 = AskContext(
        vocab="cw:player:0:ab",
        candidates=("PASS", "card:0@player:1"),
        world=_w(),
    )
    assert t.decide(ctx4) == 1
    # forced refusal vocab never crashes, stays in bounds
    assert t.decide(_ctx_refuse(("PASS", "NONE"))) == 0
    for cands in (("PASS",), ("NONE",), ("x",)):
        assert 0 <= t.decide(_ctx_refuse(cands)) < len(cands)


def _ctx_refuse(cands: tuple[str, ...]) -> AskContext:
    return AskContext(vocab="may:x", candidates=cands, world=_w())


def _rec(swap: bool, outcome: str) -> dict:
    kinds0 = {"attack": {"asks": 4, "v0": 3, "declines": 1, "agree": 3}}
    return {
        "seed": 1,
        "swap": swap,
        "outcome": outcome,
        "reason": "lose",
        "turns": 12,
        "crash": None,
        "illegal": 0,
        "journal_total": 30,
        "ask_log_total": 20,
        "auto_resolved": 10,
        "lives_end": [0, 12] if outcome in ("a", "b") else [7, 7],
        "life_trace": [
            (1, 0, (20, 20)),
            (1, 1, (18, 20)),
            (2, 0, (18, 15)),
        ],
        "seat_stats": {
            "0": {
                "asks": 4,
                "v0": 3,
                "declines": 1,
                "illegal": 0,
                "model_errors": 0,
                "trunc": 0,
                "kinds": kinds0,
            },
            "1": {
                "asks": 2,
                "v0": 0,
                "declines": 0,
                "illegal": 0,
                "model_errors": 0,
                "trunc": 0,
                "kinds": {},
            },
        },
    }


def test_summarize_per_kind_and_leverage() -> None:
    m = summarize_matchup([_rec(False, "a")], "ckpt.pt", "teacher")
    assert m["policy_wins"] == 1
    pk = m["policy_asks"]["per_kind"]["attack"]
    assert pk["asks"] == 4 and pk["decline_rate"] == 0.25
    assert pk["v0_rate"] == 0.75 and pk["agree_heur_rate"] == 0.75
    # side a is seat 0 (no swap): dealt 20-12 = 8, received 20-0 = 20 -> -12
    lev = m["leverage"]
    assert lev["final_dmg_diff_mean"] == -12.0
    # seat-0 led by round 4 (8 dealt vs 5 at its own records)? trace: a=20-15=5? no:
    # dmg by seat0 = 20 - opp life at seat0's turn starts; by r4 = max = 5
    # dmg by seat1 = 20 - life at seat1 start = 2 by then -> lead
    assert lev["rounds"]["4"]["policy_lead_rate"] == 1.0
    assert lev["rounds"]["4"]["lead_predicts_win_rate"] == 1.0
    # swap=True moves side a to seat 1 -> the mirrored record flips the lead
    m2 = summarize_matchup([_rec(True, "b")], "ckpt.pt", "teacher")
    assert m2["leverage"]["rounds"]["4"]["policy_lead_rate"] == 0.0


def test_one_game_end_to_end(tmp_path) -> None:
    """Gate: a REAL BC-vs-HEURISTIC game runs through the policy act layer
    and the seat-attributed provider; the v2 contract keys are present and
    the illegal-action count is 0."""
    out = tmp_path / "ge2_smoke.json"
    rc = main(
        [
            "--matchups",
            "teacher",
            "--games",
            "1",
            "--workers",
            "1",
            "--device",
            "cpu",
            "--pool",
            "engine",
            "--turn-cap",
            "6",
            "--seed-base",
            "900002",
            "--out",
            str(out),
        ]
    )
    assert rc == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    ((name, m),) = data["matchups"].items()
    assert name.startswith("teacher:")
    for key in (
        "policy_wins",
        "draws",
        "policy_losses",
        "illegal_action_attempts",
        "asks_answered",
        "policy_asks",
        "baseline_asks",
        "leverage",
    ):
        assert key in m, key
    assert m["illegal_action_attempts"] == 0  # engine gate: 0-by-law
    rec = data["records"]["teacher"][0]
    assert rec["outcome"] in (
        "a",
        "b",
        "draw-stall",
        "draw-cap",
        "draw-other",
        "crash",
    )
    assert isinstance(rec["life_trace"], list)
    assert rec["ask_log_total"] > 0  # the engine lane asked real decisions
