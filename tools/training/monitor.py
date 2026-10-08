"""MTG_AI status board: dependency-light (stdlib only) HTTP server on
0.0.0.0:8788 serving ONE responsive dark page, re-reading files FRESH on
every request (zero server state except two 60 s subprocess caches).

Panels (owner-facing structure — headline first, details folded away):
  1. NOW               — training LIVE banner (heartbeat age from
                         reports/training_runs.jsonl), phase, step/loss
                         sparkline from reports/monitoring/metrics.jsonl
                         (format: see tools/training/wandb_log.py), engine
                         state (engine-guard status --json, cached 60 s),
                         last STOP-REVIEW block.
  2. PROJECT SCOREBOARD— packs green/total (run_scenarios, cached 60 s),
                         suite passes (latest NUMBERS.md row), PC-1/3/4/7
                         (latest reports/grammar_*.json), PC-11..14 (latest
                         reports/bugcatch_*.json), suspect count, puzzles
                         l1_ready, latest games decisive/crash/mean-turns,
                         ELO table if reports/monitoring/elo.json exists.
  3. DETAILS (<details>)— latest NUMBERS.md section verbatim, gpu/free-mem,
                         recent runs table, replay gallery.

Endpoints:  /            the page (meta-refresh 30 s, no JS frameworks)
            /health      JSON smoke-test endpoint

Start:  tools/training/monitor_start.sh   (pidfile reports/monitoring/monitor.pid)
Self-test without a server:  python tools/training/monitor.py --render
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
DEFAULT_PORT = 8788
REFRESH_S = 30
CACHE_TTL_S = 60.0
RUNS_TAIL = 12
SPARK_MAX = 240

_cache_lock = threading.Lock()
_cache: dict[str, tuple[float, Any]] = {}


# --------------------------------------------------------------------------
# Paths (a dataclass so tests can point render_page() at a tmp repo)
# --------------------------------------------------------------------------
@dataclass
class Paths:
    repo: Path = REPO

    @property
    def runs(self) -> Path:
        return self.repo / "reports" / "training_runs.jsonl"

    @property
    def metrics(self) -> Path:
        return self.repo / "reports" / "monitoring" / "metrics.jsonl"

    @property
    def elo(self) -> Path:
        return self.repo / "reports" / "monitoring" / "elo.json"

    @property
    def numbers(self) -> Path:
        return self.repo / "KNOWLEDGE" / "NUMBERS.md"

    @property
    def replays(self) -> Path:
        return self.repo / "reports" / "replays" / "index.md"

    @property
    def puzzles(self) -> Path:
        return self.repo / "tools" / "audit" / "puzzle_corpus.json"

    @property
    def suspects(self) -> Path:
        return self.repo / "tools" / "audit" / "suspects"

    def _latest(self, pattern: str) -> Path | None:
        hits = sorted((self.repo / "reports").glob(pattern))
        return hits[-1] if hits else None

    @property
    def grammar(self) -> Path | None:
        return self._latest("grammar_*.json")

    @property
    def bugcatch(self) -> Path | None:
        return self._latest("bugcatch_*.json")

    @property
    def games(self) -> Path | None:
        return self._latest("games_*.json")


# --------------------------------------------------------------------------
# Fresh readers (tolerant: torn lines skipped, missing files -> None)
# --------------------------------------------------------------------------
def read_jsonl(path: Path, tail: int = 0) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    recs: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            recs.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return recs[-tail:] if tail else recs


def read_json(path: Path | None) -> Any:
    if path is None or not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except json.JSONDecodeError:
        return None


def _parse_ts(ts: str | None) -> float | None:
    if not ts:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S"):
        try:
            return time.mktime(time.strptime(ts, fmt))
        except ValueError:
            continue
    return None


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def human_age(secs: float) -> str:
    secs = max(0.0, secs)
    if secs < 90:
        return f"{secs:.0f} s"
    if secs < 5400:
        return f"{secs / 60:.0f} min"
    if secs < 172800:
        return f"{secs / 3600:.1f} h"
    return f"{secs / 86400:.1f} d"


def training_state(paths: Paths) -> dict[str, Any]:
    """LIVE iff last jsonl entry is a start whose pid is alive."""
    entries = read_jsonl(paths.runs)
    st: dict[str, Any] = {
        "live": False,
        "entries": entries,
        "last": entries[-1] if entries else None,
        "last_final": next(
            (e for e in reversed(entries) if e.get("event") == "final"), None
        ),
        "heartbeat_age_s": None,
    }
    last = st["last"]
    if last and last.get("event") == "start":
        ts = _parse_ts(last.get("ts"))
        if ts is not None:
            st["heartbeat_age_s"] = time.time() - ts
        st["live"] = _pid_alive(int(last.get("pid", -1)))
    return st


# ------------------------------------------------ subprocess sources, 60 s cache
def _cached(key: str, fn: Any) -> Any:
    now = time.time()
    with _cache_lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < CACHE_TTL_S:
            return hit[1]
    val = fn()
    with _cache_lock:
        _cache[key] = (time.time(), val)
    return val


def _engine_info(repo: Path) -> dict[str, Any]:
    try:
        out = subprocess.run(
            ["engine-guard", "status", "--json"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
            cwd=repo,
        )
        return json.loads(out.stdout)
    except Exception:  # noqa: BLE001
        return {}


def engine_info(paths: Paths) -> dict[str, Any]:
    return _cached("engine", lambda: _engine_info(paths.repo))


def _packs_info(repo: Path) -> dict[str, Any]:
    try:
        out = subprocess.run(
            [sys.executable, "tools/run_scenarios.py"],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
            cwd=repo,
        )
        m = re.search(r"(\d+)/(\d+) packs passed", out.stdout)
        if m:
            return {"green": int(m.group(1)), "total": int(m.group(2))}
    except Exception:  # noqa: BLE001
        return {}
    return {}


def packs_info(paths: Paths) -> dict[str, Any]:
    return _cached("packs", lambda: _packs_info(paths.repo))


def suite_passes(paths: Paths) -> str:
    """Latest '... <n> passed' recorded in KNOWLEDGE/NUMBERS.md headline rows."""
    if not paths.numbers.exists():
        return "—"
    hits = re.findall(
        r"(\d[\d,]{2,})\s+passed",
        paths.numbers.read_text(encoding="utf-8", errors="replace"),
    )
    return hits[-1] if hits else "—"


def latest_numbers_section(paths: Paths) -> str:
    if not paths.numbers.exists():
        return "(no KNOWLEDGE/NUMBERS.md)"
    text = paths.numbers.read_text(encoding="utf-8", errors="replace")
    sections = re.split(r"(?m)^## ", text)
    return ("## " + sections[-1].strip()) if len(sections) > 1 else text.strip()


def scoreboard(
    paths: Paths, packs: dict[str, Any] | None = None
) -> list[dict[str, str]]:
    """Tiles for PANEL 2. Each tile: {label, value, sub, tone}.
    ``packs=None`` -> run_scenarios live (cached); {} -> skip (tests)."""
    tiles: list[dict[str, str]] = []

    def add(label: str, value: str, sub: str = "", tone: str = "") -> None:
        tiles.append({"label": label, "value": value, "sub": sub, "tone": tone})

    if packs is None:
        packs = packs_info(paths)
    if packs:
        ok = packs["green"] == packs["total"]
        add(
            "scenario packs",
            f"{packs['green']}/{packs['total']}",
            "run_scenarios live",
            "ok" if ok else "bad",
        )
    else:
        add("scenario packs", "—", "run_scenarios failed")

    add("suite passes", suite_passes(paths), "last recorded (NUMBERS.md)")

    gram = read_json(paths.grammar)
    date = paths.grammar.name.rsplit("_", 1)[-1].split(".")[0] if paths.grammar else ""
    if gram and "pcs" in gram:
        pcs = gram["pcs"]

        def pc(key: str) -> None:
            p = pcs.get(key, {})
            if p.get("status") == "pending_executor":
                add(key, "pending", "executor lane", "warn")
                return
            val = p.get("value")
            if isinstance(val, float):
                val = f"{val:.3f}" if val > 0.01 else f"{val:g}"
            tone = (
                "ok" if p.get("pass") else ("bad" if p.get("pass") is False else "warn")
            )
            add(key, str(val), f"grammar {date}", tone)

        for key in ("PC-1", "PC-3", "PC-4", "PC-7"):
            pc(key)
    else:
        for key in ("PC-1", "PC-3", "PC-4", "PC-7"):
            add(key, "—", "no grammar report")

    bug = read_json(paths.bugcatch)
    if bug and "pcs" in bug:
        for key in ("PC-11", "PC-12", "PC-13", "PC-14"):
            p = bug["pcs"].get(key, {})
            val = p.get("value")
            if isinstance(val, float):
                val = f"{val:.2f}"
            gated = bool(p.get("gated"))
            tone = "ok" if p.get("pass") else ("bad" if gated else "warn")
            add(key, str(val), f"bugcatch {'gated' if gated else 'report-only'}", tone)
    else:
        for key in ("PC-11", "PC-12", "PC-13", "PC-14"):
            add(key, "—", "no bugcatch report")

    n_susp = len(list(paths.suspects.glob("*.json"))) if paths.suspects.is_dir() else 0
    add(
        "suspects open",
        str(n_susp),
        "tools/audit/suspects/",
        "ok" if n_susp == 0 else "warn",
    )

    puz = read_json(paths.puzzles)
    if puz and "summary" in puz:
        s = puz["summary"]
        add(
            "puzzles certified",
            str(s.get("l1_ready", "—")),
            f"of {s.get('items', '?')} items (l1_ready)",
            "ok",
        )
    else:
        add("puzzles certified", "—", "no puzzle_corpus summary")

    games = read_json(paths.games)
    if games and paths.games is not None:
        gdate = paths.games.name.rsplit("_", 1)[-1].split(".")[0]
        n = games.get("n_games", 0)
        surv = games.get("survived", 0)
        decisive = n - surv
        crashes = games.get("crash_games", games.get("crashes", "?"))
        if isinstance(crashes, list):
            crashes = len(crashes)
        add("games decisive", f"{decisive}/{n}", f"games {gdate}", "ok")
        add(
            "game crashes",
            str(crashes),
            "latest 100-seed run",
            "ok" if crashes == 0 else "bad",
        )
        add("mean turns", str(games.get("mean_turns", "—")), f"games {gdate}")
    else:
        add("games", "—", "no games report")
    return tiles


def elo_rows(paths: Paths) -> list[dict[str, Any]] | None:
    """Normalise reports/monitoring/elo.json into [{name, elo}] or None."""
    data = read_json(paths.elo)
    if data is None:
        return None
    rows: list[dict[str, Any]] = []
    if isinstance(data, dict):
        players = data.get("players", data.get("elo", data))
        if isinstance(players, dict):
            rows = [{"name": k, "elo": v} for k, v in players.items()]
        elif isinstance(players, list):
            rows = players
    elif isinstance(data, list):
        rows = data

    def elo_of(r: dict[str, Any]) -> float:
        try:
            return float(r.get("elo", r.get("rating", 0)))
        except (TypeError, ValueError):
            return 0.0

    if not rows:
        return None
    return sorted(rows, key=elo_of, reverse=True)


# --------------------------------------------------------------------------
# Rendering (pure functions — render_page() needs no server)
# --------------------------------------------------------------------------
CSS = """
:root{color-scheme:dark}
*{box-sizing:border-box}
body{background:#0d1117;color:#e6edf3;margin:0;padding:12px 16px 40px;
 font:15px/1.5 system-ui,'Segoe UI',Roboto,sans-serif}
h1{font-size:1.35rem;margin:4px 0 14px}
h1 small{color:#8b949e;font-weight:400;font-size:.75rem}
h2{font-size:1.05rem;margin:22px 0 8px;color:#79c0ff;border-bottom:1px solid #21262d;
 padding-bottom:4px}
.grid{display:grid;gap:10px;grid-template-columns:repeat(auto-fit,minmax(150px,1fr))}
.tile{background:#161b22;border:1px solid #21262d;border-radius:10px;padding:10px 12px}
.tile .lab{color:#8b949e;font-size:.72rem;text-transform:uppercase;letter-spacing:.06em}
.tile .val{font-size:1.7rem;font-weight:700;font-variant-numeric:tabular-nums}
.tile .val.small{font-size:1.05rem}
.tile .sub{color:#8b949e;font-size:.68rem}
.ok .val{color:#3fb950}.bad .val{color:#f85149}.warn .val{color:#d29922}
.banner{display:inline-block;padding:6px 16px;border-radius:8px;font-weight:800;
 font-size:1.15rem;letter-spacing:.08em}
.live{background:#1a2f23;color:#3fb950;border:1px solid #3fb950;animation:pl 2s infinite}
.idle{background:#1c2128;color:#8b949e;border:1px solid #30363d}
@keyframes pl{50%{opacity:.55}}
.now{display:flex;flex-wrap:wrap;gap:10px;align-items:stretch}
.now .tile{flex:1 1 200px}
svg.spark{background:#161b22;border:1px solid #21262d;border-radius:10px;width:100%;height:90px}
pre{background:#161b22;border:1px solid #21262d;border-radius:8px;padding:10px;
 overflow:auto;font-size:.72rem;white-space:pre-wrap}
table{border-collapse:collapse;width:100%;font-size:.8rem}
th,td{border-bottom:1px solid #21262d;padding:4px 8px;text-align:left;
 font-variant-numeric:tabular-nums}
th{color:#8b949e;font-weight:600}
details{margin-top:8px}
summary{cursor:pointer;color:#79c0ff;font-size:.9rem}
.note{color:#8b949e;font-size:.72rem;margin-top:14px}
.review{background:#161b22;border:1px solid #d2992255;border-radius:10px;padding:10px 12px;
 flex:1 1 320px;font-size:.8rem}
.review b{color:#d29922}
@media(max-width:600px){.tile .val{font-size:1.35rem}body{padding:8px 8px 30px}}
"""


def esc(x: Any) -> str:
    return html.escape(str(x), quote=True)


def sparkline_svg(metrics: list[dict[str, Any]]) -> str:
    pts = [
        (m["step"], m["loss"])
        for m in metrics[-SPARK_MAX:]
        if isinstance(m.get("step"), int | float)
        and isinstance(m.get("loss"), int | float)
    ]
    if len(pts) < 2:
        return (
            '<div class="tile"><div class="lab">loss curve</div>'
            '<div class="val small">waiting for ≥2 loss points</div>'
            '<div class="sub">tools/training/log_metric.py --step N --loss X</div></div>'
        )
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    xr = (x1 - x0) or 1.0
    yr = (y1 - y0) or 1.0
    w, h, pad = 600.0, 80.0, 8.0
    poly = " ".join(
        f"{pad + (x - x0) / xr * (w - 2 * pad):.1f},{h - pad - (y - y0) / yr * (h - 2 * pad):.1f}"
        for x, y in pts
    )
    return (
        f'<svg class="spark" viewBox="0 0 {w:.0f} {h:.0f}" preserveAspectRatio="none">'
        f'<polyline fill="none" stroke="#58a6ff" stroke-width="2" points="{poly}"/></svg>'
        f'<div class="sub">steps {x0:g}→{x1:g} · loss {pts[0][1]:.4f}→{pts[-1][1]:.4f} · '
        f"{len(pts)} pts · last {esc(metrics[-1].get('phase', '?'))} @ "
        f"{esc(metrics[-1].get('ts', ''))}</div>"
    )


def render_page(paths: Paths, now: float | None = None, live: bool = True) -> str:
    """Build the full page. ``live=False`` skips the subprocess sources
    (engine-guard, run_scenarios) so tests can render hermetically."""
    now = now if now is not None else time.time()
    st = training_state(paths)
    metrics = read_jsonl(paths.metrics)
    eng = engine_info(paths) if live else {}
    out: list[str] = []
    out.append(
        "<!doctype html><html><head><meta charset='utf-8'>"
        f'<meta http-equiv="refresh" content="{REFRESH_S}">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        "<title>MTG_AI status</title><style>" + CSS + "</style></head><body>"
    )
    out.append(
        f"<h1>MTG_AI status board <small>refresh {REFRESH_S}s · "
        f"{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(now))}</small></h1>"
    )
    out.append(
        "<div style='margin:-8px 0 10px'>"
        "<a href='/progress.html' style='color:#79c0ff'>Progress board &rarr;</a>"
        "</div>"
    )

    # ---------------------------------------------------------- PANEL 1: NOW
    out.append("<h2>1 · NOW</h2><div class='now'>")
    if st["live"]:
        age = st["heartbeat_age_s"]
        out.append(
            "<div class='tile'><span class='banner live'>● LIVE</span>"
            "<div class='sub'>heartbeat "
            + esc(human_age(age) if age is not None else "?")
            + " ago · phase "
            + esc((st["last"] or {}).get("phase", "?"))
            + " · pid "
            + esc((st["last"] or {}).get("pid", "?"))
            + "</div></div>"
        )
    else:
        why = "no runs recorded" if not st["entries"] else "no live start entry"
        out.append(
            f"<div class='tile'><span class='banner idle'>○ IDLE</span>"
            f"<div class='sub'>{esc(why)}</div></div>"
        )
    lf = st["last_final"]
    if lf:
        tone = "ok" if lf.get("cause") == "complete" else "bad"
        out.append(
            f"<div class='tile {tone}'><div class='lab'>last run finished</div>"
            f"<div class='val small'>{esc(lf.get('cause', '?'))} · {esc(lf.get('wall_s', '?'))}s</div>"
            f"<div class='sub'>phase {esc(lf.get('phase', '?'))} · {esc(str(lf.get('ts', '')))}</div></div>"
        )
    mem = eng.get("memory", {}) if isinstance(eng, dict) else {}
    eng_name = esc(eng.get("active_engine", "n/a")) if eng else "n/a"
    gw = esc("ok" if eng.get("gateway_ok") else "?") if eng else "n/a"
    out.append(
        f"<div class='tile'><div class='lab'>engine</div><div class='val small'>{eng_name}</div>"
        f"<div class='sub'>gateway {gw} · {mem.get('used_gib', -1):.1f}/"
        f"{mem.get('total_gib', -1):.1f} GiB used · swap {mem.get('swap_used_gib', -1):.1f}</div></div>"
    )
    out.append("</div>")
    out.append("<div style='margin-top:10px'>" + sparkline_svg(metrics) + "</div>")
    out.append(
        "<div class='now' style='margin-top:10px'><div class='review'>"
        "<b>STOP REVIEW — was the last stop correct?</b><br>"
        + (
            f"cause=<b>{esc(lf.get('cause'))}</b> wall_s={esc(lf.get('wall_s'))} "
            f"phase={esc(lf.get('phase'))} checkpoint={esc(lf.get('last_checkpoint') or '—')}"
            f"<br><span class='sub'>{esc(lf.get('free_mem') or '')}</span>"
            if lf
            else "no final entry yet"
        )
        + "<br><span class='sub'>Two knobs only: (1) raise --timeout if progress was "
        "real-but-slow; (2) split the phase. Same crash signature twice → fix code, "
        "don't tune. cause=oom → shrink batch/model.</span></div></div>"
    )

    # --------------------------------------------- PANEL 2: PROJECT SCOREBOARD
    out.append("<h2>2 · PROJECT SCOREBOARD</h2><div class='grid'>")
    for t in scoreboard(paths, packs=({} if not live else None)):
        cls = f"tile {t['tone']}" if t["tone"] else "tile"
        small = " small" if len(t["value"]) > 7 else ""
        out.append(
            f"<div class='{cls}'><div class='lab'>{esc(t['label'])}</div>"
            f"<div class='val{small}'>{esc(t['value'])}</div>"
            f"<div class='sub'>{esc(t['sub'])}</div></div>"
        )
    out.append("</div>")
    rows = elo_rows(paths)
    if rows:
        out.append("<h3>ELO</h3><table><tr><th>#</th><th>player</th><th>elo</th></tr>")
        for i, r in enumerate(rows, 1):
            out.append(
                f"<tr><td>{i}</td><td>{esc(r.get('name', r.get('player', '?')))}</td>"
                f"<td>{esc(r.get('elo', r.get('rating', '?')))}</td></tr>"
            )
        out.append("</table>")
    else:
        out.append(
            "<div class='tile' style='margin-top:10px'><div class='lab'>ELO table</div>"
            "<div class='val small'>awaiting reports/monitoring/elo.json</div>"
            "<div class='sub'>written by the ELO batch — appears here automatically</div></div>"
        )

    # ------------------------------------------------------- PANEL 3: DETAILS
    out.append("<h2>3 · DETAILS</h2><details><summary>open details</summary>")
    out.append(
        "<h4>latest NUMBERS.md section (verbatim)</h4><pre>"
        + esc(latest_numbers_section(paths))
        + "</pre>"
    )
    if lf and (lf.get("gpu_peak_mib") or lf.get("free_mem")):
        out.append(
            "<h4>gpu / memory at last stop</h4><pre>gpu_peak_mib: "
            + esc(lf.get("gpu_peak_mib", "n/a"))
            + "\n"
            + esc(lf.get("free_mem", ""))
            + "</pre>"
        )
    out.append(
        "<h4>recent training runs</h4><table><tr><th>event</th><th>ts</th>"
        "<th>phase</th><th>cause</th><th>wall_s</th><th>exit</th></tr>"
    )
    for e in st["entries"][-10:]:
        cells = "".join(
            f"<td>{esc(e.get(k, ''))}</td>"
            for k in ("event", "ts", "phase", "cause", "wall_s", "exit_code")
        )
        out.append(f"<tr>{cells}</tr>")
    out.append("</table>")
    if paths.replays.exists():
        out.append(
            "<h4>replay gallery (reports/replays/index.md)</h4><pre>"
            + esc(paths.replays.read_text(encoding="utf-8", errors="replace"))
            + "</pre>"
        )
    out.append("</details>")
    out.append(
        "<div class='note'>metrics: reports/monitoring/metrics.jsonl (log_metric.py) "
        "· wandb mirrors automatically when WANDB_API_KEY is set · runs: "
        "reports/training_runs.jsonl</div>"
    )
    out.append("</body></html>")
    return "".join(out)


def health_json(paths: Paths) -> dict[str, Any]:
    st = training_state(paths)
    return {
        "ok": True,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "training_live": st["live"],
        "heartbeat_age_s": (
            round(st["heartbeat_age_s"], 1)
            if st["heartbeat_age_s"] is not None
            else None
        ),
        "metrics_lines": len(read_jsonl(paths.metrics)),
        "runs_entries": len(st["entries"]),
        "grammar_report": paths.grammar.name if paths.grammar else None,
        "bugcatch_report": paths.bugcatch.name if paths.bugcatch else None,
        "elo_present": paths.elo.exists(),
    }


# --------------------------------------------------------------------------
# Home Assistant endpoints  (GET /ha.json for REST sensors, GET /ha compact view)
# --------------------------------------------------------------------------


def ha_state(paths: Paths) -> dict[str, Any]:
    """Compact machine-readable snapshot for Home Assistant REST sensors.
    Field names are STABLE (HA yaml binds them); values always present."""
    st = training_state(paths)
    eng = engine_info(paths)
    final = next((e for e in reversed(st["entries"]) if e.get("event") == "final"), {})
    elo_top: list[dict[str, Any]] = []
    if paths.elo.exists():
        try:
            elo = json.loads(paths.elo.read_text(encoding="utf-8"))
            elo_top = [
                {
                    "policy": r["policy"].split("/")[-1].removesuffix(".pt"),
                    "elo": round(r["elo"]),
                }
                for r in elo.get("ratings", [])[:4]
            ]
        except (json.JSONDecodeError, KeyError):
            pass
    state = "training" if st["live"] else "idle"
    if eng.get("gateway_ok") is False and not st["live"]:
        state = "engine-down"  # e.g. mid full-memory restart
    mem = eng.get("memory") or {}
    return {
        "ok": True,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "state": state,
        "phase": st.get("phase") or "",
        "engine_up": bool(eng.get("gateway_ok")),
        "engine": eng.get("active_engine") or "",
        "mem_used_gib": mem.get("used_gib"),
        "mem_total_gib": mem.get("total_gib"),
        "last_stop_cause": final.get("cause", ""),
        "last_stop_wall_s": final.get("wall_s"),
        "metrics": len(read_jsonl(paths.metrics)),
        "elo_top": elo_top,
    }


def _ha_html(d: dict[str, Any]) -> str:
    """Ultra-compact dark card for the HA app (iframe/picture card)."""
    tone = {"training": "#22c55e", "idle": "#64748b", "engine-down": "#f59e0b"}[
        d["state"]
    ]
    rows = [
        ("STATE", d["state"].upper()),
        ("PHASE", d["phase"] or "—"),
        ("ENGINE", "up" if d["engine_up"] else "DOWN"),
        ("MEM", f"{d['mem_used_gib'] or '?'} / {d['mem_total_gib'] or '?'} GiB"),
        ("LAST STOP", d["last_stop_cause"] or "—"),
    ]
    if d["elo_top"]:
        rows.append(
            ("ELO", ", ".join(f"{e['policy']}={e['elo']}" for e in d["elo_top"]))
        )
    lines = "".join(
        f'<div style="display:flex;justify-content:space-between;padding:6px 0;'
        f'border-bottom:1px solid #1e293b"><span style="color:#94a3b8">{k}</span>'
        f"<b>{v}</b></div>"
        for k, v in rows
    )
    return (
        '<!doctype html><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta http-equiv="refresh" content="30">'
        '<div style="font:15px/1.5 system-ui;background:#0f172a;color:#e2e8f0;'
        "max-width:420px;margin:12px auto;padding:16px;border-radius:12px;"
        "border-left:6px solid " + tone + '">'
        '<div style="font-size:18px;font-weight:700;margin-bottom:8px">MTG Training</div>'
        + lines
        + "</div>"
    )


# --------------------------------------------------------------------------
# Server
# --------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    paths = Paths()
    started = time.time()

    def log_message(self, format: str, *args: Any) -> None:
        del format, args  # silence BaseHTTPRequestHandler stderr logging

    def _send(self, code: int, ctype: str, body: bytes) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        try:
            if self.path in ("/", "/index.html"):
                self._send(
                    200, "text/html; charset=utf-8", render_page(self.paths).encode()
                )
            elif self.path == "/health":
                payload = dict(
                    health_json(self.paths),
                    uptime_s=round(time.time() - self.started, 1),
                )
                self._send(200, "application/json", json.dumps(payload).encode())
            elif self.path in ("/progress", "/progress.html"):
                sys.path.insert(0, str(self.paths.repo / "tools" / "board"))
                import make_progress

                self._send(
                    200,
                    "text/html; charset=utf-8",
                    make_progress.render_html(self.paths.repo).encode(),
                )
            elif self.path in ("/ha", "/ha.json"):
                payload = ha_state(self.paths)
                if self.path == "/ha":
                    self._send(
                        200, "text/html; charset=utf-8", _ha_html(payload).encode()
                    )
                else:
                    self._send(200, "application/json", json.dumps(payload).encode())
            else:
                self._send(404, "text/plain", b"not found")
        except Exception as exc:  # noqa: BLE001 — never kill the handler thread
            self._send(500, "text/plain", f"render error: {exc}".encode())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="MTG_AI status board (stdlib http.server)."
    )
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--render", action="store_true", help="print page once, no server")
    ap.add_argument("--health", action="store_true", help="print health JSON once")
    args = ap.parse_args(argv)

    if args.render:
        print(render_page(Paths()))
        return 0
    if args.health:
        print(json.dumps(health_json(Paths()), indent=1))
        return 0

    Handler.paths = Paths()
    srv = ThreadingHTTPServer(("0.0.0.0", args.port), Handler)
    print(
        f"[monitor] serving http://0.0.0.0:{args.port}/ pid={os.getpid()}", flush=True
    )
    srv.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
