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


# ------------------------------------------------- batch-5 size ladder law
def test_size_ladder_is_the_pre_registered_table():
    # Knob sets exactly as pre-registered (KNOWLEDGE/2026-10-06/21 dispatch);
    # S0 is batch-3 arm B exactly, S4 is batch-3 arm A exactly.
    assert v3.SIZE_LADDER == ("S0", "S1", "S2", "S3", "S3a", "S3b", "S4")
    ladder = {
        "S0": {"d": 64, "layers": 2, "heads": 4, "ff": 128},
        "S1": {"d": 128, "layers": 3, "heads": 4, "ff": 256},
        "S2": {"d": 192, "layers": 4, "heads": 6, "ff": 512},
        "S3": {"d": 256, "layers": 6, "heads": 8, "ff": 1024},
        "S3a": {"d": 320, "layers": 7, "heads": 8, "ff": 1408},
        "S3b": {"d": 384, "layers": 8, "heads": 8, "ff": 2816},
        "S4": {"d": 512, "layers": 8, "heads": 8, "ff": 3072},
    }
    for name, knobs in ladder.items():
        cfg = v3.ARMS[name]
        assert {k: cfg[k] for k in knobs} == knobs, name
        assert cfg["dropout"] == (0.0 if name == "S4" else 0.1), name
        assert v3.arm_config(name, "B") == cfg  # ladder arms bypass base-arm
        assert v3.ARM_DATA[name] is v3.EPISODES  # identical data, no exceptions
    assert v3.ARMS["S0"] == v3.ARMS["B"]
    assert v3.ARMS["S4"] == v3.ARMS["A"]


def test_size_ladder_computed_params_monotonic_exact_endpoints():
    # Nominal labels {0.17M, 0.66M, 2.5M, 10M, 35M} are the owner's rough
    # estimates (vocab 380 makes S2/S3 land lower); the computed ladder must
    # be strictly increasing and the endpoints bit-exact with batch 3.
    counts = []
    for name in v3.SIZE_LADDER:
        model = PointerBC(380, **v3.ARMS[name])
        counts.append(sum(p.numel() for p in model.parameters()))
    assert counts[0] == 169_474 and counts[-1] == 35_124_226  # == batch-3 B/A
    assert counts == sorted(counts) and len(set(counts)) == 7
    assert 500_000 < counts[1] < 800_000  # ~0.66M nominal
    assert 1_500_000 < counts[2] < 2_000_000  # ~2.5M nominal (actual 1.77M)
    assert 4_500_000 < counts[3] < 6_000_000  # ~10M nominal (actual 5.3M)
    assert 9_000_000 < counts[4] < 11_000_000  # S3a ~10M (actual 9.96M @ 380)
    assert 22_000_000 < counts[5] < 24_000_000  # S3b ~23M (actual 23.05M @ 380)


def test_ratio_block_carries_the_trio_and_survives_zero_lines():
    # Owner law /21: params : gold lines : median seq_len in every report.
    rb = v3.ratio_block(169_474, {"v2": 75, "dagger": 0}, {"median": 111})
    assert rb == {
        "params": 169_474,
        "gold_lines_train": 75,
        "median_seq_len": 111,
        "params_per_gold_line": 2259.7,  # the batch3-B 2.3k number from /21
    }
    edge = v3.ratio_block(1000, {"v2": 0}, {"median": 10})
    assert edge["params_per_gold_line"] == 1000.0  # no ZeroDivisionError


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
                    "admissible": True,
                }
            ],
            "headline_claims": [],
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
    trio = rep["ratio"]
    assert trio["params"] == rep["train"]["params"]
    assert trio["gold_lines_train"] > 0 and trio["median_seq_len"] > 0


def test_ladder_arm_smoke_writes_bc5_prefix_with_ratio_block(tmp_path):
    # An S-arm runs end-to-end and defaults to the bc5_/b5smoke namespace.
    rc = v3.main(
        ["--arm", "S1", "--smoke", "--device", "cpu", "--out-dir", str(tmp_path)]
    )
    assert rc == 0
    rep = json.loads((tmp_path / "bc5_S1_report.json").read_text())
    assert rep["arm"] == "S1" and rep["model"]["d"] == 128
    rb = rep["ratio"]
    assert rb["params_per_gold_line"] == round(
        rb["params"] / max(rb["gold_lines_train"], 1), 1
    )
    rebuilt = PointerBC(rep["vocab_size"], **v3.ARMS["S1"])
    assert rb["params"] == sum(p.numel() for p in rebuilt.parameters())


# ------------------------------------------------- search-distillation law
def _logsoftmax(z):
    import math

    m = max(z)
    lse = m + math.log(sum(math.exp(x - m) for x in z))
    return [x - lse for x in z]


def test_soft_target_loss_matches_manual_kl_plus_hard_ce():
    """KL row loss matches manual on a toy: row0 distilled (KL), rows 1-2
    hard CE, mean over rows. Unexpanded options carry pi=0 and are NOT
    smoothed (AlphaZero law)."""
    import math

    logits = torch.tensor([[2.0, 0.0, -1.0], [0.5, 1.5, -2.0], [1.0, 2.0, 3.0]])
    gold_idx = torch.tensor([0, 2, 1])
    pi = torch.tensor([[0.0, 0.7, 0.3], [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]])
    has = torch.tensor([True, False, False])
    lp = _logsoftmax(logits[0].tolist())
    kl0 = sum(p * (math.log(p) - l) for p, l in zip([0.7, 0.3], lp[1:]))
    ce1 = -_logsoftmax(logits[1].tolist())[2]
    ce2 = -_logsoftmax(logits[2].tolist())[1]
    manual = (kl0 + ce1 + ce2) / 3
    got = float(v3.soft_target_loss(logits, gold_idx, pi, has))
    assert abs(got - manual) < 1e-5, (got, manual)


def test_soft_target_loss_respects_masked_slots_and_onehot_equals_ce():
    import math

    # finfo-min slot (invalid candidate) must not produce NaN via 0*log0.
    z = torch.tensor([[1.0, -2.0, torch.finfo(torch.float32).min]])
    pi = torch.tensor([[0.5, 0.5, 0.0]])
    has = torch.tensor([True])
    loss = float(v3.soft_target_loss(z, torch.tensor([0]), pi, has))
    assert math.isfinite(loss)
    # one-hot pi is exactly hard CE on the same row.
    pi1 = torch.tensor([[0.0, 1.0, 0.0]])
    kl = float(v3.soft_target_loss(z, torch.tensor([1]), pi1, torch.tensor([True])))
    ce = float(torch.nn.functional.cross_entropy(z, torch.tensor([1])))
    assert abs(kl - ce) < 1e-5


def _tiny_ep(pack: str, rows: int) -> dict:
    return {
        "pack": pack,
        "card": pack,
        "asks": [
            {
                "ordinal": i,
                "what": "act:main",
                "gold": True,
                "gold_idx": 0,
                "candidates": ["PASS", "X"],
                "obs": {"turn": 1, "lives": [20, 20], "battlefield": [[], []]},
            }
            for i in range(rows)
        ],
    }


def test_mixed_train_eps_balances_streams_by_gold_rows(tmp_path, monkeypatch):
    v2f, sf = tmp_path / "v2.jsonl", tmp_path / "s.jsonl"
    v2f.write_text("".join(json.dumps(_tiny_ep(f"v{i}", 2)) + "\n" for i in range(3)))
    sf.write_text("".join(json.dumps(_tiny_ep(f"s{i}", 3)) + "\n" for i in range(4)))
    monkeypatch.setitem(v3.ARM_DATA, "B", v2f)
    monkeypatch.setitem(v3.ARM_DATA, "search", sf)
    streams = v3.mixed_train_eps("B", "search+v2", 1.0, set())
    by = dict(streams)
    s_rows = sum(len(e["asks"]) for e in by["search"])  # 12
    v_rows = sum(len(e["asks"]) for e in by["v2"])  # 6 x2 reps = 12
    assert s_rows == 12 and v_rows == 12
    # w=inf -> anchor off, search-only, no replication
    only = v3.mixed_train_eps("B", "search+v2", float("inf"), set())
    assert [n for n, _ in only] == ["search"] and len(only[0][1]) == 4
    # stamped source feeds the data_mix report bucket
    vocab = v2.build_vocab_v2([e for _n, eps in streams for e in eps])
    ds = v3.build_mixed_train_ds(streams, vocab)
    assert {e.get("source") for e in ds} == {"search", "v2"}


def test_search_mix_smoke_end_to_end_on_cpu(tmp_path):
    rc = v3.main(
        [
            "--arm",
            "B",
            "--mix",
            "search+v2",
            "--smoke",
            "--device",
            "cpu",
            "--out-dir",
            str(tmp_path),
            "--prefix",
            "bsd_smoke",
        ]
    )
    assert rc == 0
    rep = json.loads((tmp_path / "bsd_smoke_report.json").read_text())
    assert "mix=search+v2" in rep["train_file"]
    assert rep["counts"]["data_mix"].get("search", 0) > 0
