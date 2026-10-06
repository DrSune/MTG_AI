"""Batch-3 laws: arm configs, checkpoint config round-trip through the
ab_duel loader shape, the join_corpus pack-uniqueness trap the dagger mix
must never cross, hook-level DAgger filtering, D9 seed-start wiring, and a
CPU smoke of the trainer. Run::

    pytest tools/training/test_bc_v3.py -q
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import torch

from tools.training import bc_data, packrec, packrec_v2
from tools.training import bc_data_v2 as v2
from tools.training import dagger_rollout_v3 as dag
from tools.training import train_bc_v3 as v3
from tools.training.bc_model import PointerBC

REPO = Path(__file__).resolve().parents[2]
EPISODES = REPO / "tools" / "training" / "episodes_v2.jsonl"
CORPUS = REPO / "tools" / "audit" / "puzzle_corpus.json"


@pytest.fixture(scope="module")
def episodes():
    return v2.load_episodes(EPISODES)


# ------------------------------------------------------------------ arm law
def test_arm_configs_are_the_pre_registered_ones():
    assert v3.ARMS["A"] == {
        "d": 512,
        "layers": 8,
        "heads": 8,
        "ff": 3072,
        "dropout": 0.0,
        "grad_checkpoint": True,
    }
    assert v3.ARMS["B"] == {
        "d": 64,
        "layers": 2,
        "heads": 4,
        "ff": 128,
        "dropout": 0.1,
        "grad_checkpoint": False,
    }
    assert v3.arm_config("dagger", "B") == v3.ARMS["B"]


def test_dropout_param_reaches_blocks_and_state_dict_is_stable():
    a, b = (
        PointerBC(50, d=16, layers=1, heads=2, ff=16, dropout=0.0),
        PointerBC(50, d=16, layers=1, heads=2, ff=16, dropout=0.1),
    )
    assert a.blocks[0].dropout1.p == 0.0  # type: ignore[attr-defined]
    assert b.blocks[0].dropout1.p == pytest.approx(0.1)  # type: ignore[attr-defined]
    # batch-2 checkpoints must still load: adding the param changed NO key
    legacy = {k: torch.zeros_like(x) for k, x in PointerBC(50).state_dict().items()}
    PointerBC(50, dropout=0.1).load_state_dict(legacy, strict=False)


def test_ckpt_config_roundtrips_through_the_ab_duel_shape(tmp_path):
    vocab = {"<bos>": 0, "<pad>": 1, "<sep>": 2, "<ask>": 3, "<unk>": 4, "a": 5}
    model = PointerBC(len(vocab), **v3.ARMS["B"])
    cfg = v3.ckpt_config(model, len(vocab), v3.ARMS["B"])
    path = tmp_path / "x.pt"
    v3.save_ckpt(path, model.state_dict(), vocab, cfg, 1, {"note": "t"})
    blob = torch.load(path, map_location="cpu", weights_only=False)
    assert blob["schema"] == "v2"  # ab_duel's v2 encoder switch
    rebuilt = PointerBC(**blob["config"])  # exactly BcAsk.fresh's construction
    rebuilt.load_state_dict(blob["state"])


# ------------------------------------------------------- dagger data laws
def test_data_mix_counts_gold_rows_by_source(episodes):
    vocab = v2.build_vocab_v2(episodes[:4])
    ds = v2.build_dataset_v2(episodes[:4], vocab)
    eval_fams = {episodes[0]["card"]}
    mix = v3.data_mix([{**ds[0], "source": "dagger"}] + ds[1:], eval_fams)
    assert mix["dagger"] >= 0 and mix["v2"] + mix["dagger"] > 0
    assert set(mix) >= {"v2", "dagger"}


def test_join_corpus_refuses_a_diverged_dagger_copy(episodes):
    """THE trap: the dagger mix file reuses pack names, and a diverged
    rollout keeps only the teacher-labelled gold lines — join_corpus (the
    cert attach) must therefore NEVER see the mix file; eval datasets are
    built from episodes_v2.jsonl ONLY (pinned in train_bc_v3.load_side)."""
    ep = episodes[0]
    assert sum(1 for r in ep["asks"] if r.get("gold")) >= 2
    thin, kept = [], False
    for r in ep["asks"]:
        if r.get("gold") and not kept:
            kept = True
            thin.append(r)
        else:
            thin.append({**r, "gold": False})
    vocab = v2.build_vocab_v2([ep])
    dup = v2.build_dataset_v2([ep, {**ep, "asks": thin, "source": "dagger"}], vocab)
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    with pytest.raises(AssertionError):
        v2.join_corpus(dup, corpus["items"])


# ------------------------------------------------------------------ hook law
class _Ctx:
    def __init__(self, decisions, idx=0):
        self.decisions, self.decision_idx = decisions, idx
        self.stream, self.world = None, None


@pytest.fixture()
def hook_state():
    vocab = {w: i for i, w in enumerate(bc_data.SPECIALS + ["a", "b"])}
    model = PointerBC(len(vocab), d=16, layers=1, heads=2, ff=16, grad_checkpoint=False)
    model.eval()
    st = {
        "model": model,
        "vocab": vocab,
        "max_len": 1024,
        "device": torch.device("cpu"),
        "asks": 0,
        "points": 0,
        "applied": 0,
        "correct": 0,
        "illegal_skips": 0,
        "truncations": 0,
    }
    packrec._records = []
    dag._ST = st
    yield st
    dag._ST, packrec._records = None, None


def test_scripted_point_consumes_pool_and_labels_gold(hook_state, monkeypatch):
    monkeypatch.setattr(v2, "ground_candidates", lambda w, what, c: [[] for _ in c])
    ctx = _Ctx(["a"])
    ans = dag._take_dagger(ctx, ("a", "b"), "choose:x")  # type: ignore[arg-type]
    assert ctx.decision_idx == 1, "scripted pool word must be CONSUMED"
    assert hook_state["applied"] == 1 and hook_state["points"] == 1
    assert packrec._records is not None
    row = packrec._records[-1]
    assert row["gold"] and row["gold_idx"] == 0  # teacher = scripted 'a'
    assert row["answer"] == str(ans) and row["dagger"]["gold"] == "a"


def test_illegal_gold_is_skipped_and_counted(hook_state, monkeypatch):
    calls = []
    monkeypatch.setattr(
        packrec_v2,
        "_take_recorded_v2",
        lambda self, vocab, what: calls.append(what) or "a",
    )
    ctx = _Ctx(["card:9"])  # scripted word not in this vocab
    ans = dag._take_dagger(ctx, ("a", "b"), "choose:x")  # type: ignore[arg-type]
    assert ans == "a" and ctx.decision_idx == 0, "must NOT consume"
    assert hook_state["illegal_skips"] == 1 and hook_state["applied"] == 0
    assert calls == ["choose:x"], "delegated to the untouched v2 chain"


# --------------------------------------------------------------- elo seeds
def test_elo_seed_start_builds_fresh_block(monkeypatch):
    from tools.training import elo

    captured = {}

    def fake_ladder(specs, games, **kw):
        captured.update(kw, games=games)
        return {
            "anchor": "random",
            "games_per_pair": games,
            "games_total": 0,
            "ratings": [
                {
                    "policy": "random",
                    "elo": 0.0,
                    "ci_lo": 0.0,
                    "ci_hi": 0.0,
                    "vs_field_wr": 0.5,
                }
            ],
        }

    monkeypatch.setattr(elo, "run_ladder", fake_ladder)
    monkeypatch.setattr(elo, "emit", lambda doc, out: None)
    elo.main(
        [
            "random",
            "bc:tools/training/bc_s2.pt",
            "--games",
            "3",
            "--seed-start",
            "90001",
            "--out",
            "/tmp/opencode/elo_x.json",
        ]
    )
    assert captured["seeds"] == [90001, 90002, 90003]
    assert not ({90001, 90002, 90003} & {1, 3, 4, 7, 41, 53, 61, 73})


# --------------------------------------------------------------- smoke E2E
def test_trainer_smoke_end_to_end_on_cpu(tmp_path):
    rc = v3.main(
        [
            "--arm",
            "B",
            "--smoke",
            "--device",
            "cpu",
            "--out-dir",
            str(tmp_path),
            "--prefix",
            "bc3_B",
        ]
    )
    assert rc == 0
    rep = json.loads((tmp_path / "bc3_B_report.json").read_text())
    assert rep["arm"] == "B" and rep["model"]["d"] == 64
    assert rep["train"]["curve_eval"], "per-epoch eval curve missing"
    assert set(rep["gates"]) >= {"eval_families", "train_families"}
    blob = torch.load(tmp_path / "bc3_B.pt", map_location="cpu", weights_only=False)
    assert blob["config"]["dropout"] == 0.1 and blob["schema"] == "v2"
