"""Watchdog gates for run_train.py: stop-review block, stale-pid refusal,
causes (complete/timeout/oom/crash), honest exit codes, jsonl schema."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from tools.training import run_train

RUNS_KEYS_FINAL = {
    "event",
    "ts",
    "pid",
    "cmd",
    "phase",
    "cause",
    "wall_s",
    "exit_code",
    "timeout_s",
    "last_checkpoint",
    "gpu_peak_mib",
    "free_mem",
}


def _entries(runs: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in runs.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _run(runs: Path, *argv: str) -> int:
    return run_train.main(
        [
            "--runs-file",
            str(runs),
            *argv,
        ]
    )


# --------------------------------------------------------------- heartbeats
def test_complete_run_lands_final_entry(tmp_path: Path, capsys) -> None:
    runs = tmp_path / "runs.jsonl"
    rc = _run(
        runs, "--phase", "echo", "--timeout", "10", "--", "echo", "hello-from-phase"
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "hello-from-phase" in out  # stdout is tee'd through
    entries = _entries(runs)
    assert entries[0]["event"] == "start"
    assert entries[0]["cmd"] == ["echo", "hello-from-phase"]
    assert entries[0]["pid"] == os.getpid()
    final = entries[-1]
    assert final["cause"] == "complete"
    assert final["wall_s"] >= 0
    assert RUNS_KEYS_FINAL <= set(final)


def test_timeout_kills_and_exits_124(tmp_path: Path) -> None:
    runs = tmp_path / "runs.jsonl"
    rc = _run(runs, "--timeout", "2", "--", "sleep", "30")
    assert rc == 124  # honest timeout exit code
    final = _entries(runs)[-1]
    assert final["cause"] == "timeout"
    assert final["wall_s"] < 10  # watchdog actually fired


def test_crash_captures_traceback_tail(tmp_path: Path) -> None:
    runs = tmp_path / "runs.jsonl"
    code = "import sys; sys.stderr.write('Traceback (most recent call last)\\n'); raise SystemExit(3)"
    rc = _run(runs, "--timeout", "10", "--", sys.executable, "-c", code)
    assert rc == 3  # child's honest code
    final = _entries(runs)[-1]
    assert final["cause"] == "crash"
    assert "Traceback" in final.get("traceback_tail", "")


def test_oom_detected_with_free_snapshot(tmp_path: Path) -> None:
    runs = tmp_path / "runs.jsonl"
    code = "import sys; sys.stderr.write('torch.cuda.OutOfMemoryError: GPU 0 out of memory\\n'); raise SystemExit(1)"
    rc = _run(runs, "--timeout", "10", "--", sys.executable, "-c", code)
    assert rc == 1
    final = _entries(runs)[-1]
    assert final["cause"] == "oom"
    assert "free_h" in final  # free -h snapshot recorded


# ------------------------------------------------------------- stop-review
def test_stop_review_block_printed(tmp_path: Path, capsys) -> None:
    runs = tmp_path / "runs.jsonl"
    _run(runs, "--", "true")
    capsys.readouterr()
    _run(runs, "--", "true")
    out = capsys.readouterr().out
    assert "STOP REVIEW" in out
    assert "cause=complete" in out
    assert "--timeout value" in out  # adjustment knob 1
    assert "split" in out  # adjustment knob 2


def test_stale_unfinished_entry_refuses_start(tmp_path: Path, capsys) -> None:
    runs = tmp_path / "runs.jsonl"
    dead_pid = 999999  # practically never alive; checked with os.kill anyway
    runs.write_text(
        json.dumps(
            {
                "event": "start",
                "pid": dead_pid,
                "cmd": ["ghost"],
                "phase": "ghost-phase",
                "ts": "x",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    rc = _run(runs, "--", "true")
    assert rc == 2
    out = capsys.readouterr().out
    assert "REFUSING TO START" in out
    assert "STALE" in out
    assert len(_entries(runs)) == 1  # refused: nothing appended


def test_ignore_prev_overrides_refusal(tmp_path: Path, capsys) -> None:
    runs = tmp_path / "runs.jsonl"
    runs.write_text(
        json.dumps(
            {
                "event": "start",
                "pid": 999999,
                "cmd": ["ghost"],
                "phase": "ghost-phase",
                "ts": "x",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    rc = _run(runs, "--ignore-prev", "--", "true")
    assert rc == 0
    assert _entries(runs)[-1]["cause"] == "complete"


def test_no_previous_entry_is_first_launch(tmp_path: Path, capsys) -> None:
    runs = tmp_path / "nested" / "runs.jsonl"
    rc = _run(runs, "--", "true")
    assert rc == 0
    assert "first launch" in capsys.readouterr().out


def test_no_command_is_usage_error(tmp_path: Path) -> None:
    import pytest

    with pytest.raises(SystemExit) as excinfo:
        _run(tmp_path / "runs.jsonl")
    assert excinfo.value.code != 0
