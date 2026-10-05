"""Training watchdog wrapper: run ANY training command under a per-phase
timeout, with relaunch stop-review, crash capture, OOM hints and a jsonl
heartbeat. Protocol (KNOWLEDGE/2026-10-05/12-training-protocol.md):

1. NEVER hang: the child runs in its own process group; on --timeout breach
   it is SIGTERM'd, then SIGKILL'd after a grace period (cause=timeout).
2. STOP-REVIEW BEFORE START: the previous entry in the runs jsonl is
   printed as a review block ("was this stop correct?") before anything is
   launched. If the last entry is UNFINISHED (a start with no matching
   final: the previous run died mid-flight), we REFUSE to start — verify
   the stale pid yourself, then re-run with --ignore-prev.
3. HONEST EXIT: wrapper exits 124 on timeout, 2 on refusal, else the
   child's exit code. The final jsonl entry carries
   {cause, wall_s, last_checkpoint, gpu_peak_mib, free_mem, exit_code}.

Causes: complete | crash | oom | timeout.
oom = child stderr matched torch.cuda.OutOfMemoryError / "CUDA out of
memory"; the final entry then carries a `free -h` snapshot. Fix for oom is
shrink batch/model, NOT raise the timeout.

Default --timeout is 3600 s PER PHASE (one invocation = one phase).
Batch-1 BC measured 239 s wall (doc /10), so this is 15x slack. When a
phase legitimately needs more, prefer SPLITTING the phase over raising the
timeout (a smaller phase gives finer stop-review granularity).

Usage::

    python tools/training/run_train.py [--phase NAME] [--timeout SEC]
        [--runs-file PATH] [--checkpoint-glob GLOB] [--ignore-prev]
        -- <command> [args...]

    python tools/training/run_train.py --phase record -- .venv/bin/python -m tools.training.collector ...
    python tools/training/run_train.py --phase s1-bc   -- .venv/bin/python -m tools.training.train_bc
"""

from __future__ import annotations

import argparse
import glob as globmod
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
DEFAULT_RUNS = REPO / "reports" / "training_runs.jsonl"
DEFAULT_TIMEOUT_S = 3600.0  # per-phase; batch-1 BC measured 239 s wall
KILL_GRACE_S = 10.0
OOM_PATTERNS = (
    re.compile(r"torch\.cuda\.OutOfMemoryError"),
    re.compile(r"CUDA out of memory", re.IGNORECASE),
)
STDERR_TAIL = 40  # lines kept for traceback capture

REVIEW_HELP = """\
Was this stop correct? Adjust BEFORE relaunching — two knobs only:
  (1) --timeout value : stalled-but-healthy (progress was real, just slow)
                        -> raise it for this phase.
  (2) phase split     : one phase doing too much -> split into smaller
                        phases so each gets its own watchdog + review.
If the last cause was a crash with the SAME signature repeating: do NOT
adjust anything — fix the code. If cause=oom: shrink batch/model.
"""


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _append(jsonl: Path, rec: dict[str, Any]) -> None:
    jsonl.parent.mkdir(parents=True, exist_ok=True)
    with jsonl.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")


def read_last_entry(jsonl: Path) -> dict[str, Any] | None:
    if not jsonl.exists():
        return None
    last: dict[str, Any] | None = None
    for line in jsonl.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            last = json.loads(line)
        except json.JSONDecodeError:
            continue  # tolerate torn write, keep scanning
    return last


def stop_review(jsonl: Path, ignore_prev: bool) -> tuple[int, list[str]]:
    """Print the STOP REVIEW block. Returns (refusal_code, lines_printed)."""
    lines: list[str] = []
    last = read_last_entry(jsonl)
    lines.append("== STOP REVIEW (previous run) ==")
    unfinished = False
    if last is None:
        lines.append(
            "no previous entry in " + str(jsonl) + " — first launch, nothing to review."
        )
    elif last.get("event") == "final":
        lines.append(
            f"cause={last.get('cause')} wall_s={last.get('wall_s')} "
            f"phase={last.get('phase')} ts={last.get('ts')}"
        )
    else:
        unfinished = True
        alive = _pid_alive(int(last.get("pid", -1)))
        state = "STILL RUNNING" if alive else "STALE (pid dead)"
        lines.append(
            f"last entry UNFINISHED: phase={last.get('phase')} pid={last.get('pid')} "
            f"started ts={last.get('ts')} -> {state}"
        )
    lines.append(REVIEW_HELP.rstrip())
    lines.append("=" + "=" * (len("== STOP REVIEW (previous run) ==") - 2))
    refusal = 0
    if unfinished and not ignore_prev:
        lines.append(
            "REFUSING TO START: previous entry is unfinished. Confirm the pid is "
            "truly gone, then re-run with --ignore-prev if the loss of that entry "
            "is acceptable."
        )
        refusal = 2
    for ln in lines:
        print(ln, flush=True)
    return refusal, lines


def _mem_available_gib() -> float:
    """`free -b` available column, NOT /proc/meminfo MemAvailable: on this
    Spark the vLLM sysctl reserve makes kernel MemAvailable read ~0 while
    reclaimable page cache is real (engine-guard counts it too)."""
    try:
        out = subprocess.run(
            ["free", "-b"], capture_output=True, text=True, timeout=5, check=False
        )
        return int(out.stdout.splitlines()[1].split()[6]) / 1024**3
    except Exception:  # noqa: BLE001
        return -1.0


def _free_h() -> str:
    try:
        return subprocess.run(
            ["free", "-h"], capture_output=True, text=True, timeout=5, check=False
        ).stdout.strip()
    except Exception:  # noqa: BLE001
        return "unavailable"


def _gpu_peak_mib() -> int | None:
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if out.returncode == 0:
            return int(out.stdout.strip().splitlines()[0])
    except Exception:  # noqa: BLE001 — Spark host nvidia-smi answers [N/A]
        return None
    return None


def _last_checkpoint(pattern: str, started_wall: float) -> str | None:
    hits = [
        p
        for p in globmod.glob(pattern, root_dir=REPO)
        if (REPO / p).exists() and (REPO / p).stat().st_mtime >= started_wall - 1.0
    ]
    if not hits:
        return None
    return str(max(hits, key=lambda p: (REPO / p).stat().st_mtime))


def _spawn_watchdog(cmd: list[str], timeout_s: float) -> tuple[int, bool, bool, str]:
    """Run cmd under the watchdog. Returns (rc, timed_out, oom, stderr_tail)."""
    proc = subprocess.Popen(
        cmd,
        cwd=REPO,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        errors="replace",
        start_new_session=True,  # own process group -> we can kill the tree
    )
    tail: deque[str] = deque(maxlen=STDERR_TAIL)
    tail_lock = threading.Lock()
    oom_seen = threading.Event()

    def pump(pipe: Any, tee: bool) -> None:
        for line in iter(pipe.readline, ""):
            if tee:
                sys.stdout.write(line)
                sys.stdout.flush()
            with tail_lock:
                tail.append(line.rstrip("\n"))
            if not tee and any(p.search(line) for p in OOM_PATTERNS):
                oom_seen.set()
        pipe.close()

    for pipe, tee in ((proc.stdout, True), (proc.stderr, False)):
        threading.Thread(target=pump, args=(pipe, tee), daemon=True).start()

    timed_out = False
    try:
        rc = proc.wait(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        timed_out = True
        try:  # polite first: whole group
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            rc = proc.wait(timeout=KILL_GRACE_S)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except ProcessLookupError:
                pass
            rc = proc.wait()
    with tail_lock:
        stderr_tail = "\n".join(tail)
    if timed_out and rc < 0:
        rc = 124  # report the wrapper's kill, not the signal echo
    return rc, timed_out, oom_seen.is_set(), stderr_tail


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=(__doc__ or "").splitlines()[0],
        epilog="Everything after -- is the training command to supervise.",
    )
    ap.add_argument(
        "--phase", default="phase-1", help="label for this phase (jsonl + review)"
    )
    ap.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_S,
        help=f"per-phase watchdog timeout in seconds (default {DEFAULT_TIMEOUT_S:.0f})",
    )
    ap.add_argument("--runs-file", type=Path, default=DEFAULT_RUNS)
    ap.add_argument(
        "--checkpoint-glob",
        default="tools/training/*.pt",
        help="glob (repo-relative) used to report last_checkpoint",
    )
    ap.add_argument(
        "--ignore-prev",
        action="store_true",
        help="override the refusal to start when the last jsonl entry is unfinished",
    )
    ap.add_argument("cmd", nargs=argparse.REMAINDER, help="command after --")
    args = ap.parse_args(argv)

    cmd = args.cmd
    if cmd and cmd[0] == "--":
        cmd = cmd[1:]
    if not cmd:
        ap.error("no command given; use: run_train.py [flags] -- <command> [args...]")

    refusal, _ = stop_review(args.runs_file, args.ignore_prev)
    if refusal:
        return refusal

    start_rec: dict[str, Any] = {
        "event": "start",
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "pid": os.getpid(),
        "cmd": cmd,
        "phase": args.phase,
        "timeout_s": args.timeout,
    }
    _append(args.runs_file, start_rec)

    started_wall = time.time()
    t0 = time.monotonic()
    rc, timed_out, oom, stderr_tail = _spawn_watchdog(cmd, args.timeout)
    wall = round(time.monotonic() - t0, 2)

    if timed_out:
        cause = "timeout"
    elif oom:
        cause = "oom"
    elif rc == 0:
        cause = "complete"
    else:
        cause = "crash"

    final: dict[str, Any] = {
        "event": "final",
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "pid": os.getpid(),
        "cmd": cmd,
        "phase": args.phase,
        "cause": cause,
        "wall_s": wall,
        "exit_code": rc,
        "timeout_s": args.timeout,
        "last_checkpoint": _last_checkpoint(args.checkpoint_glob, started_wall),
        "gpu_peak_mib": _gpu_peak_mib(),
        "free_mem": f"MemAvailable {_mem_available_gib():.1f} GiB",
    }
    if cause == "oom":
        final["free_h"] = _free_h()
    if cause in ("crash", "oom") and stderr_tail:
        final["traceback_tail"] = stderr_tail[-2000:]
    _append(args.runs_file, final)

    print(
        f"== RUN TRAIN: phase={args.phase} cause={cause} wall_s={wall} "
        f"exit_code={rc} -> {args.runs_file} ==",
        flush=True,
    )
    if cause == "timeout":
        return 124
    return rc


if __name__ == "__main__":
    sys.exit(main())
