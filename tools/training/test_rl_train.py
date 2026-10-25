"""/134 TASK B gates: the REINFORCE trainer ``train_rl_v1``.

Covers: (a) SMOKE — a real tiny --rl-collect (2 games, S3a net) produces
rows carrying the seat-view ``outcome`` field; (b) one update step: finite
loss, weights CHANGE, the checkpoint on disk (anchor source) is untouched,
and the diagnostics sidecar carries all six F4 no-op-discriminator keys;
(c) the ZERO-VARIANCE guard — an all-equal-reward batch must produce a
policy-gradient grad-norm of ~0 (the batch-mean baseline absorbs it; the
no-op discriminator must not be able to hide inside a flat-looking run);
(d) DETERMINISM — same rows + same weights => bit-identical first-batch
grad-norm/loss; (e) fail-loud on missing outcome and ask-row shape drift;
(f) CUDA device parity — the full path incl. the post-step KL check, run on
GPU when one is visible (skipped otherwise): night-1 crashed there because the
cached anchor log-probs were rebuilt on the CPU.

Real collection through the rig (module fixture reused across tests), no
synthetic rows: the outcome path is exercised end to end.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

import pytest
import torch

from tools.eval.gameplay_eval_v2 import main as eval_main
from tools.training.train_rl_v1 import F4_KEYS, load_episodes, train
from tools._testutil import skip_unless_files

REPO = Path(__file__).resolve().parents[2]
NET = str(REPO / "tools" / "training" / "bsh_S3a_s1_best.pt")

pytestmark = skip_unless_files(NET)
RL_SEED = 11
# train() is CPU-forward-bound (grad fwd + anchor fwd + backward per ask);
# the --max-asks guard bounds the working set, the marker bounds the wall.
TIMEOUT = pytest.mark.timeout(1800)
GUARD = {"max_asks": 24}


def _rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines()]


def _write(tmp: Path, rows: list[dict[str, Any]], name: str = "eps.jsonl") -> Path:
    p = tmp / name
    p.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return p


def _set_outcomes(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """A win/loss split: batch-mean baseline is non-trivial (adv = ±1)."""
    rows = json.loads(json.dumps(rows))
    for i, r in enumerate(rows):
        r["outcome"] = "win" if i % 2 == 0 else "loss"
    return rows


@pytest.fixture(scope="module")
def episodes(tmp_path_factory: pytest.TempPathFactory) -> Path:
    tmp = tmp_path_factory.mktemp("rl_train")
    eps = tmp / "episodes.jsonl"
    rc = eval_main(
        [
            "--games",
            "2",
            "--workers",
            "1",
            "--matchups",
            "teacher",
            "--pool",
            "engine",
            "--policy-a",
            NET,
            "--device",
            "cpu",
            "--rl-collect",
            str(eps),
            "--sample",
            "--rl-seed",
            str(RL_SEED),
            "--out",
            str(tmp / "eval.json"),
        ]
    )
    assert rc == 0
    return eps


# ---------------------------------------------------------------- smoke
@TIMEOUT
def test_smoke_rows_carry_outcome(episodes: Path) -> None:
    rows = _rows(episodes)
    assert len(rows) == 2
    for r in rows:
        assert r["kind"] == "rl_episode"
        assert r["outcome"] in ("win", "loss", "draw", "crash")
        assert r["asks"]
    assert load_episodes(episodes, NET) == rows  # contract passes LOUD-free


# ---------------------------------------------------- identity (SHA > path)
@TIMEOUT
def test_policy_identity_by_sha_not_path(episodes: Path, tmp_path: Path) -> None:
    """Same bytes under a foreign path (export-dir / moved copy) = SAME
    policy: 2026-10-24 checkpoint governance (evidence-by-SHA)."""
    moved = tmp_path / "moved_ckpt.pt"
    moved.write_bytes(Path(NET).read_bytes())
    rows = _set_outcomes(_rows(episodes))
    for r in rows:
        r["policy"] = str(moved)
    eps = _write(tmp_path, rows)
    assert load_episodes(eps, NET) == rows  # bytes match => owned


@TIMEOUT
def test_policy_identity_foreign_bytes_rejected(episodes: Path, tmp_path: Path) -> None:
    """Same path NAME, different bytes = foreign policy => fail-loud."""
    moved = tmp_path / "moved_ckpt.pt"
    moved.write_bytes(Path(NET).read_bytes())
    rows = _set_outcomes(_rows(episodes))
    for r in rows:
        r["policy"] = str(moved)
    eps = _write(tmp_path, rows)
    with moved.open("r+b") as fh:
        fh.seek(100)
        fh.write(b"\x01")  # one byte => different identity
    with pytest.raises(RuntimeError, match="0/2 episodes were collected"):
        load_episodes(eps, NET)


# ------------------------------------------------------------ one update
@TIMEOUT
def test_one_update_changes_weights_fills_f4(episodes: Path, tmp_path: Path) -> None:
    eps = _write(tmp_path, _set_outcomes(_rows(episodes)))
    base_sha = hashlib.sha256(Path(NET).read_bytes()).hexdigest()
    before = torch.load(NET, map_location="cpu", weights_only=False)["state"]
    diag = train(eps, NET, device="cpu", tag="rld_i1", out_dir=tmp_path, **GUARD)
    for k in F4_KEYS:
        assert k in diag
    assert json.loads((tmp_path / "rld_i1_diag.json").read_text()) == diag
    for v in (
        diag["total_loss"],
        diag["grad_norm_preclip"],
        diag["kl_mean_per_game"],
        diag["entropy_mean"],
    ):
        assert math.isfinite(v)  # finite
    # weights CHANGE (pilot law: save the iteration checkpoint, no best-loss)
    after = torch.load(tmp_path / "rld_i1.pt", map_location="cpu", weights_only=False)[
        "state"
    ]
    assert any(not torch.equal(before[k], after[k]) for k in before)
    # anchor source file untouched (anchor = frozen copy built in-process)
    assert hashlib.sha256(Path(NET).read_bytes()).hexdigest() == base_sha
    assert diag["games"] == 2 and 2 <= diag["asks"] <= 24
    assert diag["reward_var"] > 0.0  # win/loss batch


# --------------------------------------------------- zero-variance guard
@TIMEOUT
def test_zero_variance_grad_is_zero(episodes: Path, tmp_path: Path) -> None:
    """All-equal rewards => (R - batchmean) == 0 EXACTLY => the PG component
    contributes an exactly-zero grad even though the KL graph is live. This
    is the baseline's no-op discriminator: a nonzero grad here means the
    baseline is broken and EVERY future 'learning' reading is suspect."""
    rows = json.loads(json.dumps(_rows(episodes)))
    for r in rows:
        r["outcome"] = "loss"
    diag = train(
        _write(tmp_path, rows),
        NET,
        device="cpu",
        save=False,
        kl_post_check=False,
        beta=0.0,  # ISOLATE the policy-gradient component: the KL term has
        entropy_coef=0.0,  # a genuine anchor-point grad and is NOT the guard
        **GUARD,
    )
    assert diag["reward_var"] == 0.0
    assert diag["grad_norm_preclip"] < 1e-6
    assert diag["mean_abs_dlogp_chosen"] == 0.0  # cur == anchor at step 1
    assert diag["share_dlogp_gt_0p1"] == 0.0
    # positive control: the SAME settings on a win/loss batch must produce a
    # clearly nonzero grad — otherwise the guard passes by being deaf.
    pos = train(
        _write(tmp_path, _set_outcomes(rows), "pos.jsonl"),
        NET,
        device="cpu",
        save=False,
        kl_post_check=False,
        beta=0.0,
        entropy_coef=0.0,
        **GUARD,
    )
    assert pos["grad_norm_preclip"] > 100 * 1e-6


# --------------------------------------------------------------- determ.
@TIMEOUT
def test_determinism_grad_norm_identical(episodes: Path, tmp_path: Path) -> None:
    eps = _write(tmp_path, _set_outcomes(_rows(episodes)))
    kw = dict(save=False, kl_post_check=False, **GUARD)
    d1 = train(eps, NET, device="cpu", **kw)
    d2 = train(eps, NET, device="cpu", **kw)
    assert d1["grad_norm_preclip"] == d2["grad_norm_preclip"]
    assert d1["total_loss"] == d2["total_loss"]


# ------------------------------------------------------------- fail-loud
@TIMEOUT
def test_fail_loud_missing_outcome(episodes: Path, tmp_path: Path) -> None:
    rows = _rows(episodes)
    del rows[0]["outcome"]
    with pytest.raises(RuntimeError, match="outcome"):
        load_episodes(_write(tmp_path, rows), NET)


@TIMEOUT
def test_fail_loud_ask_shape_drift(episodes: Path, tmp_path: Path) -> None:
    rows = _rows(episodes)
    del rows[0]["asks"][0]["choose"]
    with pytest.raises(RuntimeError, match="shape drift"):
        load_episodes(_write(tmp_path, rows), NET)
    rows = _rows(episodes)
    rows[0]["asks"][0]["idx"] = len(rows[0]["asks"][0]["vocab"]) + 5
    with pytest.raises(RuntimeError, match="outside"):
        load_episodes(_write(tmp_path, rows, "b.jsonl"), NET)


# ------------------------------------------------------- cuda device parity
# Night-1 CUDA smoke crashed: the post-step KL check rebuilt the cached anchor
# log-probs as a CPU tensor while the live log-softmax sat on cuda:0
# (RuntimeError in `lp.exp() * (lp - t_anc)`). Dry-run forces device=cpu, so no
# CPU-only test could ever see it: this test runs the SAME train() path —
# kl_post_check ON, the crashing line — on a real CUDA device. Skipped when no
# GPU is visible. Tiny S3a net + max_asks=4 keeps it engine-resident-friendly.
CUDA_TIMEOUT = pytest.mark.timeout(1800)


@CUDA_TIMEOUT
@pytest.mark.skipif(not torch.cuda.is_available(), reason="no CUDA device visible")
def test_cuda_device_update_reaches_diag(episodes: Path, tmp_path: Path) -> None:
    eps = _write(tmp_path, _set_outcomes(_rows(episodes)), "cuda.jsonl")
    cpu = train(eps, NET, device="cpu", save=False, max_asks=4)
    diag = train(eps, NET, device="cuda", tag="rld_cuda", out_dir=tmp_path, max_asks=4)
    assert diag["device"] == "cuda"
    for k in F4_KEYS:
        assert k in diag
    for key in (
        "total_loss",
        "grad_norm_preclip",
        "kl_mean_per_game",
        "kl_mean_per_game_post",  # the site that crashed: must be a real number
    ):
        v = diag[key]
        assert v is not None and math.isfinite(v), key
    # post-KL ~ 0 at iteration 1 (lr 1e-5 off the anchor). float32 KL at that
    # magnitude can land a hair BELOW zero, so bound the absolute value.
    assert abs(diag["kl_mean_per_game_post"]) < diag["kl_ceiling"]
    # device parity: same rows/weights => same update, modulo GPU matmul reassociation
    assert diag["grad_norm_preclip"] == pytest.approx(
        cpu["grad_norm_preclip"], rel=0.25, abs=1e-6
    )
    assert json.loads((tmp_path / "rld_cuda_diag.json").read_text()) == diag
    blob = torch.load(tmp_path / "rld_cuda.pt", map_location="cpu", weights_only=False)
    assert all(str(v.device) == "cpu" for v in blob["state"].values())  # saved portable
