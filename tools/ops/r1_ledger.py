"""Ledger row-writer for tools/ops/r1_window.sh (R1 GPU window, /130 §2).

Modes (each prints markdown/NUMBERS lines to stdout; MISSING rows are printed
honestly when an artifact is absent or unreadable — never fabricated):

  table-train  <report.json> <cause>      one row: arm run outcome + gate acc
  table-gate   <gate.json>...             eval_ckpt.py JSON -> acc/verdict row
  table-meter  <meter.json>               /128 set-split meter -> seen/fresh/gap
  table-duel   <duel.json>...             ab_duel summary -> WR + Wilson CI row
  numbers      <meter.json> <duel.json>...  KNOWLEDGE/NUMBERS.md style lines
                                          (number + date + producing command)
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any


def _load(path: str) -> dict[str, Any] | list[Any] | None:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def table_train(argv: list[str]) -> None:
    report, cause = argv[0], argv[1]
    d = _load(report)
    if not isinstance(d, dict):
        print(
            f"| train | {Path(report).name} | MISSING/UNREADABLE | cause={cause} | - | - |"
        )
        return
    acc = ((d.get("gates") or {}).get("eval_families") or {}).get("acc")
    verdict = (d.get("gate_verdict") or {}).get("verdict", "?")
    best_ep = (d.get("train") or {}).get("best_epoch", "?")
    print(
        f"| train | {d.get('arm', '?')} ({Path(report).name}) "
        f"| cause={cause} best_epoch={best_ep} wall_s={d.get('wall_seconds', '?')} "
        f"device={d.get('device', '?')} | acc(eval-fam)={acc} "
        f"| gate={verdict} margin_SE={d.get('eval_margin_se')} "
        f"| vocab={d.get('vocab_size', '?')} head={d.get('head', '?')} |"
    )


def table_gate(argv: list[str]) -> None:
    for p in argv:
        d = _load(p)
        if not isinstance(d, dict):
            print(f"| gate | {Path(p).name} | MISSING | - | - | - |")
            continue
        print(
            f"| gate | {Path(str(d.get('ckpt', p))).name} | acc={d.get('acc')} "
            f"| verdict={d.get('verdict')} | beat_SE={d.get('beat_se')} "
            f"| n_cert={d.get('n_cert')} note={d.get('note', '')} |"
        )


def table_meter(argv: list[str]) -> None:
    d = _load(argv[0])
    if not isinstance(d, dict):
        print("| meter | r1 checkpoints | MISSING | - | - | - | - |")
        return
    for r in d.get("results", []):
        seen = r.get("seen") or {}
        fresh = r.get("fresh") or {}
        print(
            f"| meter(set-split) | {Path(str(r.get('ckpt', '?'))).name} "
            f"| seen={seen.get('acc')} (n={seen.get('n_items')}) "
            f"| fresh-ZNR={fresh.get('acc')} (n={fresh.get('n_items')}) "
            f"| GAP={r.get('gap')} +-{r.get('gap_boot_se')} "
            f"| CI95={r.get('gap_ci95')} |"
        )


def table_duel(argv: list[str]) -> None:
    for p in argv:
        d = _load(p)
        if not isinstance(d, dict) or "a" not in d:
            print(f"| duel | {Path(p).name} | MISSING | - | - | - |")
            continue
        a = d.get("a", {})
        print(
            f"| duel A-vs-B | {Path(str(d.get('spec_a', p))).name} "
            f"| games={d.get('games')} | WR(A)={a.get('winrate')} "
            f"score={a.get('score')} CI={a.get('ci')} "
            f"| g/s={d.get('games_per_sec')} |"
        )


def numbers(argv: list[str]) -> None:
    meter, duels = argv[0], argv[1:]
    date = time.strftime("%Y-%m-%d")
    parts: list[str] = []
    d = _load(meter)
    if isinstance(d, dict):
        for r in d.get("results", []):
            parts.append(
                f"{Path(str(r.get('ckpt', '?'))).name} seen="
                f"{(r.get('seen') or {}).get('acc')}(n={(r.get('seen') or {}).get('n_items')}) "
                f"fresh-ZNR={(r.get('fresh') or {}).get('acc')}(n={(r.get('fresh') or {}).get('n_items')}) "
                f"GAP={r.get('gap')}+-{r.get('gap_boot_se')}"
            )
    wrs: list[str] = []
    for p in duels:
        dd = _load(p)
        if isinstance(dd, dict) and "a" in dd:
            a = dd["a"]
            wrs.append(
                f"{Path(str(dd.get('spec_a', p))).name} WR="
                f"{a.get('winrate')}{a.get('ci')}@{dd.get('games')}g"
            )
    cmd = (
        "cmds: tools/ops/r1_window.sh --start-at 23:59 (tmux r1window; "
        "run_train.py --timeout 7200 -- train_bc_v3 --arm S4; eval_ckpt.py; "
        "/128 patched meter lane; ab_duel.py --workers 4 --device cpu)"
    )
    if not parts and not wrs:
        print(
            f"- R1 WINDOW (date {date}, /130 §2): ZERO arms completed or artifacts "
            f"missing — honest nil. {cmd}"
        )
        return
    if wrs:
        print(
            f"- R1 S4x3 DUEL vs bsh_S3a_s3 ({date}, /130 §2 window): "
            + "; ".join(wrs)
            + f" — teacher-class band reference 0.39-0.43 (KNOWLEDGE/2026-10-15/83). {cmd}"
        )
    if parts:
        print(
            f"- R1 S4 SET-SPLIT GENERALIZATION fresh=ZNR ({date}, /130 §2 window): "
            + "; ".join(parts)
            + " — /128 patched lane (frozen 199-item gate + 10 ZNR cert items, n=10 fresh: direction not magnitude). "
            + cmd
        )


MODES = {
    "table-train": table_train,
    "table-gate": table_gate,
    "table-meter": table_meter,
    "table-duel": table_duel,
    "numbers": numbers,
}


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in MODES or len(argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    MODES[argv[0]](argv[1:])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
