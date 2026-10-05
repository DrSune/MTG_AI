"""Single-source metric logger: every dict goes to BOTH the local board
stream (reports/monitoring/metrics.jsonl, read by tools/training/monitor.py)
and — only when WANDB_API_KEY is set — Weights & Biases.

THE APPEND FORMAT (metrics.jsonl, one JSON object per line):

    {"ts": "2026-10-05T21:00:00+0200", "step": 120, "loss": 0.42,
     "phase": "s1-bc", ...any extra numeric/string keys...}

Required-ish: ``step`` (x-axis of the board sparkline). ``ts`` is filled
automatically. ``loss`` optional (the board plots it when present).
``phase`` optional label; also used as the wandb group.

WANDB IS NEVER ALLOWED TO CRASH A TRAINER: the import, init and log are all
guarded; any wandb failure disables wandb for the process with one stderr
note and the jsonl append keeps working.

TO ENABLE WANDB LATER (one command — nothing else changes):

    export WANDB_API_KEY=<your key>      # then just keep training as usual

CLI for any trainer / shell step::

    .venv/bin/python tools/training/log_metric.py --step 10 --loss 0.53 --phase s1-bc
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
WANDB_PROJECT = "mtg-training"

_state: dict[str, Any] = {"run": None, "disabled": False, "warned": False}


def metrics_path() -> Path:
    """Board stream path; MTG_METRICS_PATH overrides (tests / alt runs)."""
    return Path(
        os.environ.get(
            "MTG_METRICS_PATH", str(REPO / "reports" / "monitoring" / "metrics.jsonl")
        )
    )


def _now_ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def _append_jsonl(path: Path, rec: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")
        fh.flush()


def _wandb_note(msg: str) -> None:
    if not _state["warned"]:
        _state["warned"] = True
        print(f"[wandb_log] wandb disabled for this process: {msg}", file=sys.stderr)


def _wandb_log(rec: dict[str, Any], group: str | None) -> None:
    """Best-effort wandb path. Never raises, never crashes the caller."""
    if _state["disabled"] or not os.environ.get("WANDB_API_KEY"):
        return
    try:
        if _state["run"] is None:
            import wandb  # lazy: no import cost when no key / no wandb

            _state["run"] = wandb.init(
                project=WANDB_PROJECT, group=group or rec.get("phase"), reinit=True
            )
        step = rec.get("step")
        _state["run"].log(dict(rec), step=step if isinstance(step, int) else None)
    except Exception as exc:  # noqa: BLE001 — monitoring must never break training
        _state["disabled"] = True
        _wandb_note(f"{type(exc).__name__}: {exc}")


def log_metric(
    data: dict[str, Any], phase: str | None = None, group: str | None = None
) -> dict[str, Any]:
    """Append ``data`` (+auto ts) to metrics.jsonl, mirror to wandb if keyed.

    Always returns the record that was written to the board stream.
    """
    rec = dict(data)
    rec.setdefault("ts", _now_ts())
    if phase is not None:
        rec.setdefault("phase", phase)
    _append_jsonl(metrics_path(), rec)
    _wandb_log(rec, group)
    return rec


def _coerce(value: str) -> Any:
    for cast in (int, float):
        try:
            return cast(value)
        except ValueError:
            pass
    return value


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Append one metric record to the board stream (+wandb if keyed)."
    )
    ap.add_argument("--step", type=int, default=None)
    ap.add_argument("--loss", type=float, default=None)
    ap.add_argument("--phase", default=None, help="run phase label (wandb group too)")
    ap.add_argument("--group", default=None, help="override wandb group")
    ap.add_argument(
        "extras",
        nargs="*",
        metavar="KEY=VALUE",
        help="extra fields, e.g. lr=3e-4 epoch=3",
    )
    args = ap.parse_args(argv)

    rec: dict[str, Any] = {}
    if args.step is not None:
        rec["step"] = args.step
    if args.loss is not None:
        rec["loss"] = args.loss
    for kv in args.extras:
        if "=" not in kv:
            ap.error(f"extra field {kv!r} is not KEY=VALUE")
        key, _, val = kv.partition("=")
        rec[key] = _coerce(val)
    written = log_metric(rec, phase=args.phase, group=args.group)
    print(f"log_metric -> {metrics_path()}: {json.dumps(written)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
