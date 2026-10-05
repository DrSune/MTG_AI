# 2026-10-05 — 13 · Monitoring batch: status board + metric stream (shipped)

**What shipped** (owner charge: structured progress panels from PC & phone):

- `tools/training/monitor.py` — stdlib-only ThreadingHTTPServer on 0.0.0.0:8788,
  one dark responsive page, files re-read FRESH per request (only engine-guard
  + run_scenarios cached 60 s; run_scenarios measured 0.62 s so packs green/total
  is LIVE). Panels: **1 NOW** (LIVE banner w/ heartbeat age + pid-alive probe of
  last training_runs.jsonl start, phase, step/loss SVG sparkline from
  metrics.jsonl, engine-guard tile, STOP-REVIEW reminder block),
  **2 PROJECT SCOREBOARD** (packs, suite passes, PC-1/3/4/7, PC-11..14, suspects,
  puzzles l1_ready, games decisive/crash/mean-turns, ELO table iff
  reports/monitoring/elo.json exists), **3 DETAILS** (`<details>`: latest
  NUMBERS.md section verbatim, gpu/free-mem at last stop, last-10 runs table,
  replay gallery). `/health` JSON. meta-refresh 30 s, no JS.
- `tools/training/monitor_start.sh` — setsid+nohup restart via
  reports/monitoring/monitor.pid (verified: new SID == PID, survives shell).
- `tools/training/wandb_log.py` + `log_metric.py` — **metrics.jsonl append
  format**: one JSON/line `{"ts","step","loss"?,"phase"?,extras…}`. Single
  source: always appended to reports/monitoring/metrics.jsonl; mirrored to
  wandb (project mtg-training, group=phase) ONLY when WANDB_API_KEY set; every
  wandb path guarded so monitoring can never crash a trainer (tested with
  poisoned wandb import). Enable later with one command: `export WANDB_API_KEY=…`.
- `tools/training/test_monitor.py` — 7 tests: jsonl format, CLI coercion,
  wandb no-op + failure-guard, hermetic render_page(live=False) all 3 panels
  incl. torn-line tolerance, elo placeholder→table, health JSON.

**Gate evidence** (see NUMBERS.md row, same date): page curl-renders all 3
panel heads + live run content (LIVE banner + "heartbeat 4 s ago · phase
live-smoke" observed mid run_train sleep; returns to IDLE after); kill/restart
clean via pidfile; ruff Δ0 on the four new files (4 pre-parallel-batch findings
in ab_duel.py untouched — ELO batch file); pytest tools/training 33 passed.

**Not touched**: MTG_bot/**, tools/audit/, run_train.py (read-only — its
jsonl is the board's heartbeat source; no instrument call was trivially
warranted, trainers call log_metric.py themselves). No engine operations.
