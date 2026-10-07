#!/usr/bin/env python3
"""selfwake.py — wake the orchestrator session after a full-memory training run.

Problem solved: the engine reload after run_full_memory.sh brings ME back online,
but nothing wakes me — the session is event-driven, so the machine sat idle 45 min
after the 2026-10-05 blink while the owner watched a 'dead' board. This script
polls the gateway until the engine answers, then injects one prompt into the
opencode session via the local server API (:4096). Verified mechanism: smoke test
delivered end-to-end 2026-10-05 22:55.

Loop-safety: a marker file records the last wake; --arm refuses to double-arm the
same run id; the injected prompt is a REVIEW prompt (no automatic re-launch of
training) — a runaway loop would need the flag flipped twice deliberately.

Usage:
  selfwake.py --arm --run-id ID [--delay-after-up 30] [--text "..."]   # detached poller
  selfwake.py --check                                                  # config + reachability
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MARKER = REPO / "reports" / "monitoring" / "selfwake.json"
SERVER = "http://localhost:4096"
GATEWAY = "http://127.0.0.1:8000/health"
DIRECTORY = "/home/sune/Desktop/MTG_AI"
DEFAULT_TEXT = (
    "selfwake: the full-memory training run finished and the engine was restored. "
    "Read reports/TRAINING_STATUS.md + the last training_runs.jsonl entries, perform "
    "the STOP-REVIEW per the training protocol, then report the verdict to the owner "
    "and queue (do not auto-start) the next batch."
)


def log(msg: str) -> None:
    print(f"[selfwake] {time.strftime('%T')} {msg}", flush=True)


def gateway_up() -> bool:
    try:
        with urllib.request.urlopen(GATEWAY, timeout=4) as r:
            return r.status == 200
    except Exception:  # noqa: BLE001 — any failure = not up yet
        return False


def find_session() -> tuple[str | None, str]:
    """MTG_AI directory sessions, checking active tmux first, then freshest non-subagent from server."""
    # Fast path: check if opencode is actively running in a tmux pane
    try:
        res = subprocess.run(
            ["tmux", "list-panes", "-a", "-F", "#{pane_id}|#{session_name}:#{window_index}.#{pane_index}|#{pane_tty}|#{pane_current_path}"],
            capture_output=True, text=True, timeout=3
        )
        if res.returncode == 0:
            for line in res.stdout.strip().splitlines():
                parts = line.split("|")
                if len(parts) == 4:
                    pane_id, target, tty, cwd = parts
                    if str(DIRECTORY) in cwd or target.startswith("MTG:"):
                        ps = subprocess.run(["ps", "-t", tty.replace("/dev/", ""), "-o", "args="], capture_output=True, text=True)
                        for pline in ps.stdout.splitlines():
                            tokens = pline.strip().split()
                            if "opencode" in tokens and "-s" in tokens:
                                idx = tokens.index("-s")
                                if idx + 1 < len(tokens):
                                    sid = tokens[idx + 1]
                                    return sid, f"picked active tmux pane {target} ({sid})"
    except Exception as exc:  # noqa: BLE001
        log(f"tmux session check error: {exc}")

    # Fallback: query server
    url = f"{SERVER}/session?directory={urllib.parse.quote(str(DIRECTORY))}&limit=20"
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            sessions = json.load(r)
    except Exception as exc:  # noqa: BLE001
        return None, f"session list failed: {exc}"

    def updated(s: dict) -> int:
        t = s.get("time")
        return int(t.get("updated", 0)) if isinstance(t, dict) else 0

    ranked = sorted(sessions, key=updated, reverse=True)
    for s in ranked:
        title = s.get("title") or ""
        if "(@" in title:  # subagent sessions must never be woken
            continue
        return s["id"], f"picked {s['id']} ({title[:48]!r})"
    return None, "no orchestrator session found (all candidates are subagents)"


def wake_tmux(sid: str) -> bool:
    """If the session is running in an interactive tmux pane, check if it is stuck on offline engine error and recover it."""
    try:
        res = subprocess.run(
            ["tmux", "list-panes", "-a", "-F", "#{pane_id}|#{session_name}:#{window_index}.#{pane_index}|#{pane_tty}|#{pane_current_path}"],
            capture_output=True, text=True, timeout=5
        )
        if res.returncode != 0:
            return False
        for line in res.stdout.strip().splitlines():
            parts = line.split("|")
            if len(parts) == 4:
                pane_id, target, tty, cwd = parts
                if str(DIRECTORY) in cwd or target.startswith("MTG:"):
                    pane_out = subprocess.run(["tmux", "capture-pane", "-pt", pane_id, "-S", "-30"], capture_output=True, text=True).stdout
                    if "Upstream vLLM engine is offline" in pane_out or "Upstream connection error" in pane_out or "All connection attempts failed" in pane_out:
                        log(f"tmux pane {target} has offline engine error; restarting pane cleanly...")
                        ps = subprocess.run(["ps", "-t", tty.replace("/dev/", ""), "-o", "pid,args"], capture_output=True, text=True)
                        for pline in ps.stdout.splitlines()[1:]:
                            if "opencode" in pline and "supervisor" not in pline and "serve" not in pline:
                                pid = int(pline.split()[0])
                                subprocess.run(["kill", "-15", str(pid)])
                                time.sleep(1.0)
                        subprocess.run(["tmux", "send-keys", "-t", pane_id, "stty sane; clear", "Enter"])
                        time.sleep(0.5)
                        subprocess.run(["tmux", "send-keys", "-t", pane_id, f"opencode -s {sid}", "Enter"])
                        log(f"restarted opencode in tmux pane {target}")
                        return True
    except Exception as exc:  # noqa: BLE001
        log(f"wake_tmux error: {exc}")
    return False


def inject(sid: str, text: str) -> bool:
    wake_tmux(sid)
    body = json.dumps({"parts": [{"type": "text", "text": text}]}).encode()
    for ep in ("prompt_async", "message"):  # try async endpoint first, then message
        req = urllib.request.Request(
            f"{SERVER}/session/{sid}/{ep}",
            data=body,
            headers={"content-type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                if r.status in (200, 204):
                    log(f"injected via /{ep} into {sid}")
                    return True
        except Exception as exc:  # noqa: BLE001
            log(f"/{ep} failed: {exc}")
    return False


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--arm", action="store_true", help="start detached-style poller + wake"
    )
    ap.add_argument("--run-id", default="", help="idempotence key (training run)")
    ap.add_argument("--delay-after-up", type=int, default=30)
    ap.add_argument("--timeout", type=int, default=3600)
    ap.add_argument("--text", default=DEFAULT_TEXT)
    ap.add_argument("--check", action="store_true", help="print config + reachability")
    args = ap.parse_args(argv)

    if args.check:
        sid, why = find_session()
        print(
            json.dumps(
                {"gateway_up": gateway_up(), "session": sid, "why": why}, indent=1
            )
        )
        return 0 if sid else 1

    if args.arm:
        MARKER.parent.mkdir(parents=True, exist_ok=True)
        prior = {}
        if MARKER.exists():
            try:
                prior = json.loads(MARKER.read_text())
            except json.JSONDecodeError:
                pass
        if args.run_id and prior.get("run_id") == args.run_id:
            log(f"already armed for run {args.run_id} — refusing to double-wake")
            return 2
        MARKER.write_text(
            json.dumps({"run_id": args.run_id, "armed_at": time.strftime("%F %T")})
        )
        waited = 0
        while not gateway_up() and waited < args.timeout:
            time.sleep(10)
            waited += 10
        if waited:
            log(f"gateway answered after {waited}s")
        if not gateway_up():
            log(f"gateway never answered within {args.timeout}s — NOT waking")
            return 1
        time.sleep(args.delay_after_up)  # let the engine warm before a giant turn
        sid, why = find_session()
        log(why)
        if not sid:
            return 1
        return 0 if inject(sid, args.text) else 1

    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
