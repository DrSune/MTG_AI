"""Showcase replay gallery for the games_2026-10-05 all-pool run.

VIEWER batch (2026-10-05): make the visual part usable NOW. Reads a games
report (default ``reports/games_2026-10-05.json``: pool all, 100 seeds),
re-plays every seed traced at the current HEAD (play_game is fully seeded
and the traced fingerprint equals the untraced one, so each replay is
VERIFIED against the report row's fingerprint), counts the response-
window-arc journal kinds per game, selects up to six showcase games by
fixed category rules, rebuilds their HTML through tools/make_replay.py
and writes ``reports/replays/index.md`` with one WHY line per file.

Categories (fixed order, deterministic tie-break ``(metric desc, seed
asc)``, a seed is claimed by at most one category — earlier letters win):

  a  any seed with a counter CAST          (most COUNTER rows)
  b  kickback PAID                         (most KICKBACK PAY answers)
  c  most windows in one game              (most WINDOW_OPEN rows)
  d  closest finish                        (smallest |life delta|)
  e  longest decisive                      (most turns, non-survivor)
  f  cap survivor                          (survived the turn cap)

Selection is deterministic: same report in, same six seeds out, twice.

Run::

    .venv/bin/python tools/audit/game_gallery.py              # scan + build
    .venv/bin/python tools/audit/game_gallery.py --select     # pick only
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

import make_replay  # tools/make_replay.py, the shared replay builder

from MTG_bot.core.executor.games import get_supply, play_game

DEFAULT_REPORT = REPO / "reports" / "games_2026-10-05.json"
# The window-arc kinds counted per game, matched BY KIND STRING (the
# STALL_BREAK emitter landed concurrently in this same worktree, 2026-10-05/11).
WINDOW_KINDS = (
    "WINDOW_OPEN",
    "WINDOW_PASS",
    "COUNTER",
    "KICKBACK",
    "LIFE_LOST",
    "TARGETING",
    "STALL_BREAK",
)


def scan_seed(
    seed: int, pool: str, turns: int, supply: Any, tmp_dir: Path
) -> dict[str, Any]:
    """One traced replay of ``seed`` -> the stats the selection reads."""
    trace_path = tmp_dir / f"scan_s{seed}.json"
    outcome = play_game(seed, pool, 1409, turns, supply=supply, trace_path=trace_path)
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    trace_path.unlink(missing_ok=True)
    counts: collections.Counter = collections.Counter(
        str(e.get("kind"))
        for e in trace["entries"]
        if e.get("type") == "event" and str(e.get("kind")) in WINDOW_KINDS
    )
    kickback_paid = sum(
        1
        for e in trace["entries"]
        if e.get("kind") == "KICKBACK" and "'PAY'" in str(e.get("data"))
    )
    first_counter = next(
        (
            f"{e['subject']} countered by {e['cause']}"
            for e in trace["entries"]
            if e.get("kind") == "COUNTER"
        ),
        "",
    )
    first_pay = next(
        (
            str(e["subject"])
            for e in trace["entries"]
            if e.get("kind") == "KICKBACK" and "'PAY'" in str(e.get("data"))
        ),
        "",
    )
    life = [p["life"] for p in trace["final_snapshot"]["players"]]
    return {
        "seed": seed,
        "fingerprint": outcome.fingerprint,
        "turns": outcome.turns if hasattr(outcome, "turns") else trace.get("turns"),
        "survived": bool(outcome.survived),
        "reason": outcome.reason,
        "life": life,
        "margin": abs(life[0] - life[1]) if len(life) == 2 else 999,
        "counters": counts["COUNTER"],
        "kickbacks_paid": kickback_paid,
        "windows": counts["WINDOW_OPEN"],
        "kind_counts": {k: v for k, v in counts.items() if v},
        "first_counter": first_counter,
        "first_pay": first_pay,
        "_trace": trace,  # kept for the featured-card asset check
    }


def select(stats: list[dict[str, Any]]) -> list[tuple[str, dict[str, Any], str]]:
    """Fixed-order category picks; deterministic tie-breaks, no repeats."""

    def best(cands: list[dict], key, why) -> tuple[int, dict, str] | None:
        pool = sorted(cands, key=lambda s: (-key(s), s["seed"]))
        return (pool[0]["seed"], pool[0], why(pool[0])) if pool else None

    taken: set[int] = set()
    picks: list[tuple[str, dict, str]] = []

    def take(letter: str, cands: list[dict], key, why) -> None:
        pick = best([s for s in cands if s["seed"] not in taken], key, why)
        if pick:
            taken.add(pick[0])
            picks.append((letter, pick[1], pick[2]))

    decisive = [s for s in stats if not s["survived"]]
    take(
        "a",
        [s for s in stats if s["counters"] > 0],
        lambda s: s["counters"],
        lambda s: f"counter CAST in-game: {s['first_counter']}",
    )
    take(
        "b",
        [s for s in stats if s["kickbacks_paid"] > 0],
        lambda s: s["kickbacks_paid"],
        lambda s: f"kickback PAID — unless-cost paid to save {s['first_pay']}",
    )
    take(
        "c",
        [s for s in stats if s["windows"] > 0],
        lambda s: s["windows"],
        lambda s: f"most response windows in one game ({s['windows']} WINDOW_OPEN)",
    )
    take(
        "d",
        [s for s in stats if s["margin"] < 999],
        lambda s: -s["margin"],
        lambda s: (
            f"closest finish: life {s['life'][0]}-{s['life'][1]} "
            f"(margin {s['margin']}, {s['turns']} turns)"
        ),
    )
    take(
        "e",
        decisive,
        lambda s: s["turns"],
        lambda s: (
            f"longest decisive game ({s['turns']} turns, "
            f"{s['reason'].split('(')[0].strip()})"
        ),
    )
    take(
        "f",
        [s for s in stats if s["survived"]],
        lambda s: s["turns"],
        lambda s: f"turn-cap survivor ({s['turns']} turns, still alive: {s['reason']})",
    )
    return picks


def featured_card_ok(trace: dict, names: dict[str, str]) -> tuple[int, list[str]]:
    """Do the featured cards (window subjects / held chips / counters /
    kickback parties) resolve to real asset JPGs? tag->oracle_id comes from
    the snapshot cards + action entries; name->oracle_id from the decklists.
    Returns (checked, missing-labels)."""
    tag_oid: dict[str, str] = {}
    for snap_player in trace["final_snapshot"]["players"]:
        for zone in ("battlefield", "hand"):
            for c in snap_player.get(zone, []):
                if c.get("handle") and c.get("oracle_id"):
                    tag_oid[str(c["handle"])] = c["oracle_id"]
    for e in trace["entries"]:
        if e.get("type") == "action" and e.get("handle") and e.get("oracle_id"):
            tag_oid.setdefault(str(e["handle"]), e["oracle_id"])
    oids = {
        **{c["name"]: c["oracle_id"] for dl in trace["decklists"] for c in dl["cards"]},
        **names,
    }
    tag_name = {
        m.group(2): m.group(1)
        for e in trace["entries"]
        for f in ("subject", "cause")
        if (m := re.match(r"^(.*) \((card:\d+)\)$", str(e.get(f) or "")))
    }
    missing: list[str] = []
    checked: set[str] = set()

    def check(label: str) -> None:
        tag = re.search(r"\((card:\d+)\)$", label)
        name = re.sub(r" \(card:\d+\)$", "", label)
        if name == "held" and tag:
            name = tag_name.get(tag.group(1), "")
        oid = (tag_oid.get(tag.group(1)) if tag else None) or oids.get(name)
        if not oid:
            return
        tag_txt = tag.group(1) if tag else label
        if tag_txt in checked:
            return
        checked.add(tag_txt)
        if not (make_replay.ASSET_DIR / f"{oid}.jpg").exists():
            missing.append(label)

    for e in trace["entries"]:
        if e.get("kind") not in ("WINDOW_OPEN", "COUNTER", "KICKBACK"):
            continue
        for field in ("subject", "cause"):
            label = str(e.get(field) or "")
            if not label.startswith("player") and label != "None":
                check(label)
        for tag in re.findall(r"card:\d+", str(e.get("data") or "")):
            check(f"held ({tag})")
    return len(checked), missing


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Select + regenerate showcase replays from a games report"
    )
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--out-dir", default=str(make_replay.DEFAULT_OUT))
    parser.add_argument(
        "--select", action="store_true", help="print the selection; build nothing"
    )
    args = parser.parse_args(argv)

    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    pool = report["pool_mode"]
    turns = report["turn_cap"]
    rows = {int(r["seed"]): r for r in report["rows"]}
    supply = get_supply(pool)

    stats: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="gallery_") as tmp:
        for seed in sorted(rows):
            stats.append(scan_seed(seed, pool, turns, supply, Path(tmp)))
    fp_ok = sum(1 for s in stats if s["fingerprint"] == rows[s["seed"]]["fingerprint"])

    picks = select(stats)
    if args.select:
        print(json.dumps([letter for letter, _, _ in picks]))
        print(json.dumps([s["seed"] for _, s, _ in picks]))
        return 0

    out_dir = Path(args.out_dir)
    lines = [
        f"# Replay gallery — {Path(args.report).stem} ({pool} pool, {len(rows)} seeds)",
        "",
        "Generated by `tools/audit/game_gallery.py` — open any HTML below",
        "directly (double-click / `file://`). Windows render as highlighted",
        "response panels; counters/kickbacks as inline event cards.",
        f"Traced replays reproduce {fp_ok}/{len(rows)} report fingerprints.",
        "",
        "| pick | replay | seed | why |",
        "|---|---|---|---|",
    ]
    for letter, stat, why in picks:
        make_replay.main(
            [
                "--seed",
                str(stat["seed"]),
                "--pool",
                pool,
                "--turns",
                str(turns),
                "--out-dir",
                str(out_dir),
            ]
        )
        html_path = out_dir / f"replay_s{stat['seed']}.html"
        text = html_path.read_text(encoding="utf-8")
        size_kb = html_path.stat().st_size // 1024
        kinds = sorted(stat["kind_counts"])
        has_kinds = all(f'"{k}"' in text for k in kinds)
        by_name = {
            c["name"]: c["oracle_id"]
            for dl in stat["_trace"]["decklists"]
            for c in dl["cards"]
        }
        checked, missing = featured_card_ok(stat["_trace"], by_name)
        ok = size_kb > 100 and has_kinds and not missing
        note = f"{size_kb} KB; kinds {', '.join(kinds)}; featured imgs {checked} ok" + (
            f", MISSING {missing}" if missing else ""
        )
        rel = html_path.relative_to(REPO)
        lines.append(
            f"| {letter} | `{rel}` | {stat['seed']} | {why} — "
            f"{'PASS' if ok else 'CHECK: ' + note} |"
        )
        lines.append(f"| | | | <sub>{note}</sub> |")
    index = out_dir / "index.md"
    index.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"index: {index}")
    for letter, stat, why in picks:
        print(f"  {letter}: seed {stat['seed']} — {why}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
