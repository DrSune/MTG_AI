#!/usr/bin/env python3
"""Owner-facing visual progress tracker for MTG_AI.

Stdlib-only, idempotent, READ-ONLY on all data sources. Every number on the
page is parsed live from disk at render time — nothing is hardcoded.

  python3 tools/board/make_progress.py      -> writes tools/board/progress.html
  render_html(repo)                         -> page string (used by
                                               tools/training/monitor.py at
                                               /progress.html, rendered fresh)

Panels:
  1. HEADLINE      — batch-6 eval acc (3 seeds x 5 arms) + historical curves
  2. CORPUS        — puzzle corpus summary + episodes/gold-line counts
  3. GATES         — last 8 final events from reports/training_runs.jsonl
  4. FAIL-CORE     — cards failing in EVERY bc6 S0..S3 run (recomputed here)
  5. KNOWLEDGE     — KNOWLEDGE/2026-*/NN-*.md pulse + NUMBERS.md size
  6. RUNNING NOW   — reports/TRAINING_STATUS.md
"""

from __future__ import annotations

import html
import json
import re
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

CSS = """
:root{color-scheme:dark}
*{box-sizing:border-box}
body{background:#0d1117;color:#e6edf3;margin:0;padding:12px 16px 40px;
 font:15px/1.5 system-ui,'Segoe UI',Roboto,sans-serif;max-width:1100px}
h1{font-size:1.35rem;margin:4px 0 2px}
h1 small{color:#8b949e;font-weight:400;font-size:.75rem}
h2{font-size:1.05rem;margin:22px 0 8px;color:#79c0ff;border-bottom:1px solid #21262d;
 padding-bottom:4px}
table{border-collapse:collapse;width:100%;font-size:.8rem;margin:6px 0}
th,td{border-bottom:1px solid #21262d;padding:4px 8px;text-align:left;
 font-variant-numeric:tabular-nums}
th{color:#8b949e;font-weight:600}
tr.sum td{background:#161b22;font-weight:600}
.ok{color:#3fb950}.bad{color:#f85149}.warn{color:#d29922}
.note{color:#8b949e;font-size:.72rem;margin:4px 0}
.kv td:first-child{color:#8b949e;width:240px}
.err{background:#161b22;border:1px solid #f85149;border-radius:8px;padding:8px 10px;
 color:#f85149;font-size:.8rem}
.cards li{margin:1px 0}
.badge{display:inline-block;padding:1px 8px;border-radius:10px;font-weight:700;
 font-size:.8rem}
.badge.g{background:#1a2f23;color:#3fb950;border:1px solid #3fb950}
.badge.r{background:#2d1215;color:#f85149;border:1px solid #f85149}
.badge.a{background:#2b2007;color:#d29922;border:1px solid #d29922}
"""


def esc(x: Any) -> str:
    return html.escape(str(x), quote=True)


def _read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except json.JSONDecodeError:
        return None


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
            if isinstance(rec, dict):
                out.append(rec)
        except json.JSONDecodeError:
            continue
    return out


def _acc(x: Any) -> str:
    try:
        return f"{float(x):.4f}"
    except (TypeError, ValueError):
        return esc(x)


def _verdict(v: Any) -> str:
    v = str(v or "")
    if "PASS" in v.upper():
        return f"<span class='badge g'>{esc(v)}</span>"
    if "FAIL" in v.upper():
        return f"<span class='badge r'>{esc(v)}</span>"
    return esc(v)


# ---------------------------------------------------------------------------
# PANEL 1 — HEADLINE: eval accuracy, batch 6 (3 seeds), + historical curves
# ---------------------------------------------------------------------------
def panel_headline(repo: Path) -> str:
    out = ["<h2>1 · HEADLINE — eval accuracy (batch 6, 3 seeds)</h2>"]
    curve = _read_json(repo / "tools" / "training" / "batch6_curve.json")
    runs = curve.get("runs") if isinstance(curve, dict) else None
    if runs:
        out.append(
            "<table><tr><th>arm</th><th>seed</th><th>params</th><th>acc</th>"
            "<th>iid SE&times;</th><th>boot SE&times;</th><th>verdict</th></tr>"
        )
        for r in runs:
            out.append(
                f"<tr><td>{esc(r.get('arm'))}</td><td>{esc(r.get('seed'))}</td>"
                f"<td>{esc(r.get('params'))}</td><td>{_acc(r.get('acc'))}</td>"
                f"<td>{esc(r.get('iid'))}</td><td>{esc(r.get('boot'))}</td>"
                f"<td>{_verdict(r.get('verdict'))}</td></tr>"
            )
        summary = curve.get("summary") or {}
        for arm in sorted(summary):
            s = summary[arm]
            out.append(
                f"<tr class='sum'><td>{esc(arm)} mean</td><td>n={esc(s.get('n'))}"
                f"</td><td></td><td>{_acc(s.get('acc_mean'))}</td>"
                f"<td colspan='2'>range {_acc(s.get('acc_range'))} · boot mean "
                f"{esc(s.get('boot_mean'))}</td>"
                f"<td>{esc(s.get('pass_count'))}/{esc(s.get('n'))} pass</td></tr>"
            )
        out.append("</table>")
    else:
        # Fallback: rebuild the same shape from the per-run report files.
        reports = sorted((repo / "tools" / "training").glob("bc6_*_report.json"))
        if reports:
            out.append(
                "<table><tr><th>report</th><th>arm</th><th>acc</th>"
                "<th>verdict</th></tr>"
            )
            for p in reports:
                r = _read_json(p) or {}
                gv = r.get("gate_verdict") or {}
                verdict = gv.get("verdict") if isinstance(gv, dict) else gv
                gates = r.get("gates") or {}
                acc = (gates.get("gold_lines_all") or {}).get("acc")
                out.append(
                    f"<tr><td>{esc(p.name)}</td><td>{esc(r.get('arm'))}</td>"
                    f"<td>{_acc(acc)}</td><td>{_verdict(verdict)}</td></tr>"
                )
            out.append("</table>")
        else:
            out.append("<div class='note'>batch6_curve.json unavailable.</div>")

    # Historical curves (archive dirs).
    hist_rows: list[str] = []
    for arch in ("archive_batch5", "archive_v4_baseline"):
        data = _read_json(repo / "tools" / "training" / arch / "batch5_curve.json")
        if not isinstance(data, dict):
            continue
        arms = data.get("arms")
        if not isinstance(arms, list):
            continue
        for a in arms:
            if not isinstance(a, dict):
                continue
            gp = a.get("gate_pass")
            gate = (
                "<span class='badge g'>PASS</span>"
                if gp is True
                else ("<span class='badge r'>FAIL</span>" if gp is False else esc(gp))
            )
            hist_rows.append(
                f"<tr><td>{esc(arch)}</td><td>{esc(a.get('arm'))}</td>"
                f"<td>{esc(a.get('params'))}</td><td>{_acc(a.get('eval_acc'))}</td>"
                f"<td>{esc(a.get('margin_se'))}</td><td>{gate}</td></tr>"
            )
    if hist_rows:
        out.append(
            "<div class='note'>historical curves (batch-5 archives):</div>"
            "<table><tr><th>source</th><th>arm</th><th>params</th><th>acc</th>"
            "<th>margin SE&times;</th><th>gate</th></tr>"
            + "".join(hist_rows)
            + "</table>"
        )
    return "".join(out)


# ---------------------------------------------------------------------------
# PANEL 2 — CORPUS
# ---------------------------------------------------------------------------
def panel_corpus(repo: Path) -> str:
    out = ["<h2>2 · CORPUS</h2>"]
    data = _read_json(repo / "tools" / "audit" / "puzzle_corpus.json")
    rows: list[tuple[str, str]] = []
    if isinstance(data, dict) and isinstance(data.get("summary"), dict):
        s = data["summary"]

        def g(key: str) -> str:
            return esc(s.get(key, "—"))

        rows = [
            ("packs scanned", g("packs_scanned")),
            ("packs with decisions", g("packs_with_decisions")),
            ("puzzle items", g("items")),
            ("punish-inaction items", g("punish_inaction")),
            ("l1_ready", g("l1_ready")),
            ("no discrimination", g("no_discrimination")),
            ("fail registered", g("fail_registered")),
        ]
        by = s.get("fail_registered_by_verdict")
        if isinstance(by, dict):
            rows.append(
                (
                    "fail verdicts",
                    esc(", ".join(f"{k}: {v}" for k, v in sorted(by.items()))),
                )
            )
    else:
        rows = [("puzzle_corpus.json", "unavailable")]

    n_ep = n_gold = None
    ep_path = repo / "tools" / "training" / "episodes_v2.jsonl"
    if ep_path.exists():
        n_ep, n_gold = 0, 0
        for rec in _read_jsonl(ep_path):
            n_ep += 1
            asks = rec.get("asks")
            if isinstance(asks, list):
                n_gold += sum(1 for r in asks if isinstance(r, dict) and r.get("gold"))
        rows.append(("episodes (episodes_v2.jsonl)", esc(n_ep)))
        rows.append(("gold asks", esc(n_gold)))
    else:
        rows.append(("episodes (episodes_v2.jsonl)", "unavailable"))

    out.append(
        "<table class='kv'>"
        + "".join(f"<tr><td>{k}</td><td>{v}</td></tr>" for k, v in rows)
        + "</table>"
    )
    return "".join(out)


# ---------------------------------------------------------------------------
# PANEL 3 — GATES (recent final run events)
# ---------------------------------------------------------------------------
def panel_gates(repo: Path) -> str:
    out = ["<h2>3 · GATES — recent training runs (final events)</h2>"]
    entries = _read_jsonl(repo / "reports" / "training_runs.jsonl")
    finals = [e for e in entries if e.get("event") == "final"][-8:]
    if not finals:
        return "".join(out) + "<div class='note'>no final events recorded.</div>"
    out.append(
        "<table><tr><th>ts</th><th>phase</th><th>cause</th><th>wall_s</th>"
        "<th>exit</th></tr>"
    )
    for e in finals:
        good = e.get("cause") == "complete" and e.get("exit_code") == 0
        cls = "ok" if good else "bad"
        out.append(
            f"<tr><td>{esc(e.get('ts', ''))}</td><td>{esc(e.get('phase', ''))}</td>"
            f"<td class='{cls}'>{esc(e.get('cause', ''))}</td>"
            f"<td>{esc(e.get('wall_s', ''))}</td>"
            f"<td class='{cls}'>{esc(e.get('exit_code', ''))}</td></tr>"
        )
    out.append("</table>")
    return "".join(out)


# ---------------------------------------------------------------------------
# PANEL 4 — FAIL-CORE (recomputed live: cards failing in every S0..S3 run)
# ---------------------------------------------------------------------------
def panel_fail_core(repo: Path) -> str:
    out = ["<h2>4 · FAIL-CORE — eval-family cards failing in every run</h2>"]
    reports = sorted((repo / "tools" / "training").glob("bc6_S[0123]_s*_report.json"))
    if not reports:
        return "".join(out) + "<div class='note'>no bc6 S0–S3 reports found.</div>"
    core: set[str] | None = None
    per_run: dict[str, list[int]] = {}  # arm -> fail counts
    n_files = 0
    for p in reports:
        r = _read_json(p)
        if not isinstance(r, dict):
            continue
        fails = {
            str(e.get("card"))
            for e in (r.get("eval_rows") or [])
            if isinstance(e, dict)
            and e.get("eval_family")
            and not e.get("correct")
            and e.get("card") is not None
        }
        n_files += 1
        core = fails if core is None else (core & fails)
        arm = str(r.get("arm") or p.name)
        per_run.setdefault(arm, []).append(len(fails))
    out.append(
        f"<div class='note'>intersection across {n_files} report file(s) "
        f"(bc6_S[0123]_s*_report.json):</div>"
    )
    names = sorted(core or set())
    out.append(
        "<ul class='cards'>"
        + "".join(f"<li class='bad'>{esc(n)}</li>" for n in names)
        + "</ul>"
        if names
        else "<div class='note'>no common failures.</div>"
    )
    out.append("<table><tr><th>arm</th><th>family fails per run</th><th>mean</th></tr>")
    for arm in sorted(per_run):
        counts = per_run[arm]
        mean = sum(counts) / len(counts)
        out.append(
            f"<tr><td>{esc(arm)}</td><td>{esc(', '.join(str(c) for c in counts))}</td>"
            f"<td>{mean:.1f}</td></tr>"
        )
    out.append("</table>")
    out.append(
        "<div class='note'>canonical list in "
        "KNOWLEDGE/2026-10-08/45-batch6-three-seed.md</div>"
    )
    return "".join(out)


# ---------------------------------------------------------------------------
# PANEL 5 — KNOWLEDGE PULSE
# ---------------------------------------------------------------------------
_FILE_RE = re.compile(r"^(\d+)-.*\.md$")


def panel_knowledge(repo: Path) -> str:
    out = ["<h2>5 · KNOWLEDGE PULSE</h2>"]
    files: list[tuple[str, int, Path]] = []
    for d in sorted((repo / "KNOWLEDGE").glob("2026-*")):
        if not d.is_dir():
            continue
        for f in d.glob("*.md"):
            m = _FILE_RE.match(f.name)
            if m:
                files.append((d.name, int(m.group(1)), f))
    if not files:
        return (
            "".join(out) + "<div class='note'>no KNOWLEDGE/2026-*/NN-*.md files.</div>"
        )
    files.sort(key=lambda t: (t[0], t[1]))
    newest = files[-7:][::-1]
    n_lines = 0
    nb = repo / "KNOWLEDGE" / "NUMBERS.md"
    if nb.exists():
        n_lines = len(nb.read_text(encoding="utf-8", errors="replace").splitlines())
    out.append(
        f"<div class='note'>{len(files)} knowledge notes · NUMBERS.md "
        f"{n_lines} lines</div>"
    )
    out.append("<table><tr><th>note</th><th>title</th></tr>")
    for date, nn, f in newest:
        title = ""
        try:
            for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.startswith("# "):
                    title = line[2:].strip()
                    break
        except OSError:
            title = "(unreadable)"
        out.append(f"<tr><td>KNOWLEDGE/{esc(date)}/{nn}</td><td>{esc(title)}</td></tr>")
    out.append("</table>")
    return "".join(out)


# ---------------------------------------------------------------------------
# PANEL 6 — RUNNING NOW
# ---------------------------------------------------------------------------
def panel_running(repo: Path) -> str:
    out = ["<h2>6 · RUNNING NOW</h2>"]
    p = repo / "reports" / "TRAINING_STATUS.md"
    if not p.exists():
        return "".join(out) + "<div class='note'>TRAINING_STATUS.md unavailable.</div>"
    text = p.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    head = lines[0] if lines else ""
    state = ""
    m = re.search(r"state:\s*\*\*(.+?)\*\*", text)
    if m:
        state = m.group(1).strip()
    if not state:
        m = re.search(r"#\s*TRAINING STATUS\s*[—-]\s*(.+)", head)
        state = m.group(1).strip() if m else "?"

    def field(name: str) -> str:
        m = re.search(rf"-\s*{name}:\s*(.+)", text)
        return m.group(1).strip().strip("*") if m else "—"

    if state.upper() in ("COMPLETE", "DONE", "IDLE"):
        badge = f"<span class='badge g'>{esc(state)}</span>"
    else:
        badge = f"<span class='badge a'>{esc(state)}</span>"
    out.append(
        "<table class='kv'>"
        f"<tr><td>headline</td><td>{esc(head.lstrip('#').strip())}</td></tr>"
        f"<tr><td>state</td><td>{badge}</td></tr>"
        f"<tr><td>updated</td><td>{esc(field('updated'))}</td></tr>"
        f"<tr><td>what</td><td>{esc(field('what'))}</td></tr>"
        "</table>"
    )
    return "".join(out)


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------
PANELS: list[Callable[[Path], str]] = [
    panel_headline,
    panel_corpus,
    panel_gates,
    panel_fail_core,
    panel_knowledge,
    panel_running,
]


def _safe(fn: Callable[[Path], str], repo: Path) -> str:
    try:
        return fn(repo)
    except Exception as exc:  # noqa: BLE001 — one bad panel must not kill the page
        return (
            f"<h2>{esc(fn.__name__)}</h2><div class='err'>panel error: "
            f"{esc(type(exc).__name__)}: {esc(exc)}</div>"
        )


def render_html(repo: Path) -> str:
    now = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    parts = [
        "<!doctype html><html><head><meta charset='utf-8'>"
        '<meta http-equiv="refresh" content="60">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        "<title>MTG_AI progress</title><style>" + CSS + "</style></head><body>",
        (
            f"<h1>MTG_AI progress <small>generated at {esc(now)} · all numbers "
            "parsed live from disk</small></h1>"
        ),
    ]
    for fn in PANELS:
        parts.append(_safe(fn, repo))
    parts.append(
        "<div class='note'>generator: tools/board/make_progress.py · served fresh "
        "at /progress.html by tools/training/monitor.py</div></body></html>"
    )
    return "".join(parts)


def main() -> int:
    repo = Path(__file__).resolve().parents[2]
    out_dir = repo / "tools" / "board"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "progress.html"
    out.write_text(render_html(repo), encoding="utf-8")
    print(f"[make_progress] wrote {out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
