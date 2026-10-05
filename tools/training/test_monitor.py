"""Tests for the monitoring batch: metrics.jsonl format, wandb_log no-op
behaviour, log_metric CLI, and monitor page/health rendering via direct
function calls (no server, no engine, no network)."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import monitor
import wandb_log


@pytest.fixture
def metrics_file(tmp_path, monkeypatch):
    p = tmp_path / "metrics.jsonl"
    monkeypatch.setenv("MTG_METRICS_PATH", str(p))
    monkeypatch.delenv("WANDB_API_KEY", raising=False)
    return p


# ------------------------------------------------------- metrics.jsonl format
def test_log_metric_appends_valid_jsonl(metrics_file):
    rec = wandb_log.log_metric({"step": 1, "loss": 0.5}, phase="t-phase")
    lines = metrics_file.read_text().splitlines()
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["step"] == 1 and parsed["loss"] == 0.5
    assert parsed["phase"] == "t-phase"
    assert "ts" in parsed and parsed["ts"] == rec["ts"]


def test_log_metric_coerce_and_extras(metrics_file, capsys):
    assert wandb_log._coerce("3e-4") == 3e-4
    assert wandb_log._coerce("10") == 10
    assert wandb_log._coerce("abc") == "abc"
    wandb_log.main(["--step", "2", "--loss", "0.25", "--phase", "p", "lr=3e-4"])
    parsed = json.loads(metrics_file.read_text().splitlines()[-1])
    assert parsed == {
        "step": 2,
        "loss": 0.25,
        "lr": 3e-4,
        "phase": "p",
        "ts": parsed["ts"],
    }


def test_wandb_noop_without_key(metrics_file, monkeypatch):
    monkeypatch.delenv("WANDB_API_KEY", raising=False)
    rec = wandb_log.log_metric({"step": 1, "loss": 0.9})  # must not raise
    assert json.loads(metrics_file.read_text().strip())["step"] == rec["step"]


def test_wandb_failure_never_crashes(metrics_file, monkeypatch):
    monkeypatch.setenv("WANDB_API_KEY", "bogus")
    monkeypatch.setitem(sys.modules, "wandb", None)  # import wandb -> TypeError
    rec = wandb_log.log_metric({"step": 7, "loss": 0.1})
    assert rec["step"] == 7  # board write survived the wandb import failure
    assert json.loads(metrics_file.read_text().strip())["step"] == 7
    assert wandb_log._state["disabled"] is True
    wandb_log._state.update({"disabled": False, "warned": False, "run": None})


# ------------------------------------------------------------- page rendering
@pytest.fixture
def fake_repo(tmp_path):
    repo = tmp_path
    (repo / "reports" / "monitoring").mkdir(parents=True)
    (repo / "KNOWLEDGE").mkdir()
    (repo / "tools" / "audit").mkdir(parents=True)
    now = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    runs = repo / "reports" / "training_runs.jsonl"
    runs.write_text(
        json.dumps({"event": "start", "ts": now, "pid": 999999, "phase": "s2-killme"})
        + "\n"
        + json.dumps(
            {
                "event": "final",
                "ts": now,
                "pid": 999998,
                "phase": "s1-bc",
                "cause": "complete",
                "wall_s": 239.0,
                "exit_code": 0,
                "last_checkpoint": "tools/training/bc_s1.pt",
                "gpu_peak_mib": 1403,
                "free_mem": "MemAvailable 9.1 GiB",
            }
        )
        + "\nGARBAGE TORN LINE\n"
    )
    (repo / "reports" / "monitoring" / "metrics.jsonl").write_text(
        "\n".join(
            json.dumps({"ts": now, "step": s, "loss": 1.0 / (s + 1), "phase": "s1-bc"})
            for s in range(6)
        )
        + "\n"
    )
    (repo / "reports" / "grammar_2026-10-05.json").write_text(
        json.dumps(
            {
                "pcs": {
                    "PC-1": {"value": 0.9934, "pass": True},
                    "PC-3": {"value": 0, "pass": True},
                    "PC-4": {"value": 0, "pass": True},
                    "PC-7": {"status": "pending_executor", "pass": None},
                }
            }
        )
    )
    (repo / "reports" / "bugcatch_2026-10-05.json").write_text(
        json.dumps(
            {
                "pcs": {
                    "PC-11": {"value": 1, "pass": True, "gated": True},
                    "PC-12": {"value": 0.38, "pass": False, "gated": False},
                    "PC-13": {"value": 0.28, "pass": False, "gated": False},
                    "PC-14": {"value": 0, "pass": True, "gated": True},
                }
            }
        )
    )
    (repo / "reports" / "games_2026-10-05.json").write_text(
        json.dumps(
            {"n_games": 100, "survived": 2, "crash_games": 0, "mean_turns": 34.07}
        )
    )
    (repo / "tools" / "audit" / "puzzle_corpus.json").write_text(
        json.dumps({"summary": {"items": 119, "l1_ready": 4}})
    )
    (repo / "KNOWLEDGE" / "NUMBERS.md").write_text(
        "## 2026-01-01 old\ncore **100 passed**\n\n## 2026-10-05 newest\n"
        "GATE-SENTINEL core **2391 passed + 5 subtests**\n"
    )
    (repo / "reports" / "replays").mkdir()
    (repo / "reports" / "replays" / "index.md").write_text("REPLAY-GALLERY-MARKER\n")
    return repo


def test_render_page_all_panels(fake_repo):
    paths = monitor.Paths(repo=fake_repo)
    page = monitor.render_page(paths, live=False)
    # panel headings
    for marker in ("1 · NOW", "2 · PROJECT SCOREBOARD", "3 · DETAILS"):
        assert marker in page
    # live jsonl content visible (final entry cause/phase, torn line tolerated)
    assert "s1-bc" in page and "complete" in page and "239.0" in page
    # scoreboard tiles fed by the report files
    assert "0.993" in page  # PC-1
    assert "pending" in page  # PC-7
    assert "34.07" in page  # mean turns
    assert "GATE-SENTINEL" in page  # latest NUMBERS section verbatim
    assert "REPLAY-GALLERY-MARKER" in page
    # sparkline built from metrics.jsonl points
    assert "<svg" in page and "polyline" in page
    # elo placeholder when the file is absent, table when present
    assert "awaiting reports/monitoring/elo.json" in page
    (fake_repo / "reports" / "monitoring" / "elo.json").write_text(
        json.dumps(
            {
                "players": [
                    {"name": "bot_v1", "elo": 1520},
                    {"name": "random", "elo": 1200},
                ]
            }
        )
    )
    page2 = monitor.render_page(paths, live=False)
    assert "bot_v1" in page2 and "1520" in page2
    assert "awaiting" not in page2


def test_health_json(fake_repo):
    paths = monitor.Paths(repo=fake_repo)
    h = monitor.health_json(paths)
    assert h["ok"] is True
    assert h["metrics_lines"] == 6
    assert h["runs_entries"] == 2
    assert h["training_live"] is False  # pid 999999 not ours
    assert h["grammar_report"] == "grammar_2026-10-05.json"
    assert h["elo_present"] is False


def test_training_state_idle_on_missing_file(tmp_path):
    paths = monitor.Paths(repo=tmp_path)
    st = monitor.training_state(paths)
    assert st["live"] is False and st["last"] is None
