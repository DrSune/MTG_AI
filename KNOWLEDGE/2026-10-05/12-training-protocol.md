# 2026-10-05 · 12 — Training relaunch protocol & full-memory procedure (HEAD 67dca46)

Roles: watchdog batch (tools-only: `tools/training/run_train.py`,
`tools/training/run_full_memory.sh`, this doc). Engine untouched by this batch;
engine steps below were studied READ-ONLY (`engine-guard --help`/`status`).

## 0. engine-guard subcommands (exact, measured 2026-10-05 via `--help`)

| Subcommand | Effect | Safe for scripts? |
|---|---|---|
| `engine-guard status [--json]` | read-only: memory, resident engine, gateway state | YES |
| `engine-guard events [--json] [-n N]` | read-only event log | YES |
| `engine-guard preflight --engine NAME --need GIB [--replacing C]` | read-only admission check | YES |
| `engine-guard watch` | systemd daemon (the running `spark-memory-guard.service`) | NO — never spawn |
| `engine-guard switch {27b\|flash-next} [--yes]` | **the only mutating subcommand**: stops the current engine, launches target via background systemd unit; refuses if a launch is in progress | the sanctioned bring-back |

**There is NO engine-guard `stop`/`off` subcommand.** The engine container
`qwen-nvfp4` is managed by `~/models/start_*.sh`, whose own stop path is
`docker rm -f qwen-nvfp4` before re-running. `run_full_memory.sh` mirrors that
sanctioned stop to free memory (then verifies via `docker ps` that the
container is DOWN and via `free -b` that memory actually appeared — kernel
`MemAvailable` in /proc/meminfo reads ~0 on this box under the vLLM sysctl
reserve; always use `free`'s *available* column, which is what engine-guard
counts too). Bring-back = `engine-guard switch <target> --yes`, then bounded
health-polls of `http://127.0.0.1:8000/health` (engine load measured ~10–12
min; default bound 1800 s).

## 1. The relaunch law (standing protocol — binding before EVERY training relaunch)

**Stop-review before start.** `run_train.py` ENFORCES this by printing a
STOP REVIEW block (last cause + wall_s + phase) at every start; read it and
answer "was this stop correct?" before walking away.

Two adjustment knobs ONLY:
1. **`--timeout` value** — stalled-but-healthy (real progress, just slow,
   e.g. cause=timeout but loss was still falling): raise the timeout for that
   phase. Default 3600 s/phase; batch-1 BC measured 239 s wall (/10), so the
   default is 15x slack.
2. **Phase split** — one phase doing too much: split record / train / eval
   into separate `--phase` invocations so each gets its own watchdog budget
   and its own review line.

Don'ts:
- **Repeated crash with the identical signature → STOP ADJUSTING, FIX CODE.**
  Timeout/config tweaks on a deterministic bug just farm identical jsonl entries.
- **cause=oom → shrink batch or model** (never raise timeout; the entry
  carries a `free -h` snapshot; GPU peak is logged as `gpu_peak_mib`, null on
  Spark where host nvidia-smi answers `[N/A]` — torch's own peak stats in the
  trainer are the GPU figure there).
- **Unfinished last entry** (start with no final: machine died mid-run) →
  run_train **refuses to start (exit 2)**. Confirm the recorded pid is dead,
  then re-run with `--ignore-prev`. Silent continuation is impossible.

## 2. Files written

- `reports/training_runs.jsonl` — append-only heartbeat. `{"event":"start",
  ts,pid,cmd,phase,timeout_s}` then `{"event":"final", ...,cause,wall_s,
  exit_code,last_checkpoint,gpu_peak_mib,free_mem}` (+`free_h` on oom,
  +`traceback_tail` on crash/oom). **Causes: `complete` | `crash` | `oom` |
  `timeout`.** Wrapper exit: 124=timeout, 2=refusal, else child's code.
- `reports/TRAINING_STATUS.md` — the owner-facing board, written by
  `run_full_memory.sh`: `LIVE` (pid, what, ETA) → `RESTARTING-ENGINE` →
  `COMPLETE`/`FAILED` with the stop-cause pulled from the jsonl.
- `reports/training_ops.log` — every step of the shell sequence, timestamped.

## 3. Owner one-liners

```bash
# supervised single phase (keeps engine up — S1 coexist shape, doc /09):
.venv/bin/python tools/training/run_train.py --phase s1-bc --timeout 3600 \
    -- .venv/bin/python -m tools.training.train_bc --device cuda

# full-memory run (S3): frees the machine, trains, GUARANTEES the coding
# engine comes back (trap-EXIT) even if you kill it or it OOMs:
tools/training/run_full_memory.sh --phase s3-full --timeout 7200 -- \
    .venv/bin/python -m tools.training.train_bc --device cuda

# controlled dry-run (training step = sleep 20; --no-engine skips all engine
# touches for trap testing):
tools/training/run_full_memory.sh --dry-run --no-engine

# "what happened last night?"
head -8 reports/TRAINING_STATUS.md; tail -2 reports/training_runs.jsonl; tail reports/training_ops.log

# last stop was my fault / that entry is stale:
... run_train.py --ignore-prev -- <cmd>
```

## 4. Notes & verified behaviour (this batch's gates)

- Trap-EXIT guarantee tested WITHOUT engine touches: `--dry-run --no-engine`,
  SIGTERM mid-run → status went LIVE→FAILED, exit 143, ops log complete,
  stop-cause recorded. Bash defers the EXIT trap until the foreground child
  exits — the bring-back still always runs; that ordering is the safe one
  (never restores the engine while training might still hold memory).
- `exec` was deliberately NOT used for the training step in the script:
  `exec` replaces the shell and would destroy the EXIT trap. Foreground run
  + trap gives both honest rc and the guarantee.
- Wrapper kills the whole child process group (own session via
  `start_new_session`), SIGTERM → 10 s grace → SIGKILL.
- `shellcheck` is not installed on the box; gates used `bash -n` (clean).
- Tests: `tools/training/test_run_train.py` (9 tests: schema, complete,
  timeout/124, crash tail, oom+free-h, stop-review, stale-pid refusal,
  --ignore-prev, first-launch).

## Memory-gate law (appended 2026-10-05 21:4x — after 2/3 parallel dispatches died at the
## gateway circuit-breaker with avail RAM 1.6 GB; engine RSS grows while a ~239K-token session
## is served, avail can sit <1 GiB for long stretches)
1. Before ANY subagent dispatch: `free` avail ≥ 3 GiB; under 2 GiB dispatch NOTHING, queue the
   work as a brief file instead (see /14 pattern — spec on disk beats a lost context window).
2. At avail < 6 GiB: max ONE agent at a time (never batches of 2+).
3. New heavy Python deps go in tools/training/.venv-train (or another isolated venv) — NEVER
   in .venv (the engine-critical env; disk bloat there also slows every test run).
4. Before declaring any batch "failed": check what it actually left on disk — both "dead"
   2026-10-05 batches had completed most work (ab_duel/elo fully green, monitor live); the
   breaker kills the REPORT, not always the work.

## Self-wake law (appended 2026-10-05 23:2x — closes the blink gap: engine restore ≠ session
## wake; the 21:55–22:50 blink sat idle 43 min AFTER a COMPLETE run because the session is
## event-driven and nothing called it)
- `tools/training/selfwake.py --arm --run-id ID` = detached poller: waits for gateway health
  (engine up = my turns can execute; +30 s warm delay), discovers the MTG_AI orchestrator
  session via the opencode server (`:4096/session?directory=…`, freshest NON-subagent title —
  subagent sessions must never be woken), POSTs one prompt to `/session/{sid}/prompt`.
- VERIFIED end-to-end twice: 22:55:38 smoke (manual POST) and 23:20:06 wiring test
  (`--arm --delay-after-up 15`, fired at +16 s). Endpoint quirk: the server answers only
  after the turn completes, so a sender timeout does NOT mean failure — marker/log decide.
- `run_full_memory.sh --selfwake` (default ON; `--no-engine` still wakes — engine never
  stopped there) arms it from the EXIT trap with run-id `fm-<epoch>`; marker
  `reports/monitoring/selfwake.json` refuses double-wake of the same run-id.
- Loop safety: the injected prompt is a REVIEW prompt — it forbids auto-starting new
  training; a runaway requires deliberately flipping --selfwake twice. Exit 1 + ops-log
  line when wake fails (never silent).

## Coexistence budget law (appended 2026-10-06 — owner OOM warning after batch-2 thrash)
1. Heavy jobs declare a HARD cap and a measured peak (bc2: cap 4 GiB, peak 1.67 GiB — the
   trainer was NEVER the balloon). The balloons are: (a) this orchestrator session's KV
   (~239K tokens; gateway RAM_usable shrank 5.5->4.8 GB within one hour), (b) idle/zombie
   agent node-children accumulating across the day, (c) parallel collectors/duel workers.
2. DEFAULT for the NEXT training batch: run_full_memory.sh (engine-off). Coexisting beside
   the ~100 GiB driver pin is the regime that swap-thrashed this box for 10 h and got an
   opencode child OOM-killed (13:18). The selfwake loop now closes that path end-to-end.
3. Duel/collector parallelism scales with `free` avail: workers = max(1, avail_GiB/2 - 1)
   at LAUNCH time, re-checked before each stage (not the old fixed 6-10).
4. Session hygiene: a >200K-token orchestrator session is itself a RAM load — after each
   batch lands, prefer a fresh window; the knowledge tree + wake protocol make restart
   cost ~zero. Zombie subagent children of THIS session's dispatches get reaped
   (pkill -P) once their parent dispatch is confirmed dead.

## Coexistence law reconciled (appended 2026-10-06 — owner flagged swap-thrash + 13:18 kernel
## OOM kill of a worker child; batch-2 was trained at 8-9 GiB avail beside vLLM's ~100 GiB pin)
- Batch-1 standing law "no big PyTorch beside vLLM unless avail > 40 GB" OVERNOTES the 3-GiB
  dispatch gate: 3 GiB is for gateway/subagent DISPATCH; CUDA training is a different class.
  I dispatched batch-2 training under the wrong law. It completed (9 resume segments) but the
  box swap-thrashed (13/15 GiB) and the kernel eventually killed an opencode child.
- STANDING RULE from now on: any job that may exceed ~4 GiB RSS runs via run_full_memory.sh
  (engine-off) — that path exists for exactly this and self-wakes when done. Coexist training
  only for measured-small jobs (bc2 peak was 1.67 GiB — the cap held; the THRASH came from
  everything else on the box, which the pin leaves no room for).
- Elo/collector worker counts scale with avail: workers <= floor((avail_GiB - 2) / 1.5).
