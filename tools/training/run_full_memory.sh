#!/usr/bin/env bash
# run_full_memory.sh — full-memory training launcher with a TRAP-EXIT guarantee.
#
# Sequence: status board LIVE -> free the machine (stop engine container) ->
# run_train.py "$@" -> ALWAYS bring the coding engine back (trap-EXIT, even
# on kill/OOM) -> health-poll the gateway (bounded) -> status COMPLETE/FAILED.
#
# engine-guard findings (studied via --help / status ONLY, 2026-10-05):
#   read-only : engine-guard status [--json] | events [--json] [-n N]
#               engine-guard preflight --engine NAME --need GIB [--replacing C]
#   daemon    : engine-guard watch            (do NOT run from here)
#   MUTATES   : engine-guard switch {27b|flash-next} [--yes]  <- the ONLY
#               state-changing subcommand; it stops the current engine and
#               starts the target via a background systemd unit.
#   There is NO engine-guard stop/off subcommand. The qwen-nvfp4 container is
#   managed by ~/models/start_*.sh, which stop it with `docker rm -f` before
#   re-running. We mirror that sanctioned stop for memory-free, verify the
#   container is down, and use `engine-guard switch <target> --yes` for the
#   guaranteed bring-back (it runs preflight + logging for us).
#
# Flags:
#   --dry-run       same sequence, but the training step is `sleep 20`
#   --no-engine     skip docker-stop AND engine restart/health-poll (trap-path
#                   testing WITHOUT touching the engine)
#   --engine-target NAME  switch target for bring-back (default: flash-next)
# Everything after -- (or all unrecognised args) goes to run_train.py.
#
# Never deletes anything. Every step is logged to reports/training_ops.log.

set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
REPORTS="$REPO/reports"
STATUS="$REPORTS/TRAINING_STATUS.md"
OPSLOG="$REPORTS/training_ops.log"
RUNS="$REPORTS/training_runs.jsonl"
RUNNER="$REPO/tools/training/run_train.py"
PY="$REPO/.venv/bin/python"
[ -x "$PY" ] || PY="$(command -v python3)"

CONTAINER=qwen-nvfp4
GATEWAY_HEALTH="${GATEWAY_HEALTH:-http://127.0.0.1:8000/health}"
MIN_FREE_GIB="${MIN_FREE_GIB:-60}"     # MemAvailable target after container stop
FREE_WAIT_S="${FREE_WAIT_S:-120}"      # bound for memory to actually free
HEALTH_WAIT_S="${HEALTH_WAIT_S:-1800}" # engine load takes ~10-12 min
HEALTH_POLL_S="${HEALTH_POLL_S:-15}"

DRY_RUN=0 NO_ENGINE=0 TARGET=flash-next
RT_ARGS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    --no-engine) NO_ENGINE=1; shift ;;
    --engine-target) TARGET="$2"; shift 2 ;;
    --) shift; RT_ARGS=("$@"); break ;;
    *) RT_ARGS+=("$1"); shift ;;
  esac
done

op() { echo "$(date '+%F %T') [run_full_memory] $*" | tee -a "$OPSLOG"; }
mem_avail() { free -b | awk 'NR==2{printf "%.1f", $7/1073741824}'; }  # free's available col, not kernel MemAvailable (reads ~0 under the vLLM reserve)
container_up() { [ -n "$(docker ps --filter "name=^${CONTAINER}$" --format '{{.Names}}' 2>/dev/null)" ]; }

write_status() { # $1=STATE $2=detail
  {
    echo "# TRAINING STATUS — $1"
    echo ""
    echo "- updated: $(date '+%F %T')"
    echo "- shell pid: $$"
    echo "- state: **$1**"
    echo "- what: ${RT_ARGS[*]:-<none>}$([ "$DRY_RUN" = 1 ] && echo '   (dry-run: sleep 20)')"
    echo "- engine target on exit: $([ "$NO_ENGINE" = 1 ] && echo '<skipped --no-engine>' || echo "$TARGET")"
    echo "- detail: $2"
    echo ""
    echo "Ops log: reports/training_ops.log | Runs jsonl: reports/training_runs.jsonl"
  } > "$STATUS"
}

ENGINE_STOPPED=0
bring_engine_back() { # runs inside trap; never clobbers the original rc
  op "bring-engine-back: switching to $TARGET via engine-guard"
  if ! engine-guard switch "$TARGET" --yes >>"$OPSLOG" 2>&1; then
    op "ENGINE GUARD REFUSED the switch — OWNER ACTION NEEDED: engine-guard switch $TARGET --yes"
    return 1
  fi
  local waited=0
  while [ "$waited" -lt "$HEALTH_WAIT_S" ]; do
    if curl -fsS -m 5 "$GATEWAY_HEALTH" >/dev/null 2>&1; then
      op "gateway healthy after ${waited}s"
      return 0
    fi
    sleep "$HEALTH_POLL_S"; waited=$((waited + HEALTH_POLL_S))
    op "health poll: not up yet (${waited}s / ${HEALTH_WAIT_S}s)"
  done
  op "ENGINE DID NOT ANSWER within ${HEALTH_WAIT_S}s — OWNER ACTION NEEDED: check $OPSLOG and 'engine-guard status'"
  return 1
}

on_exit() {
  local rc=$?
  trap - EXIT
  local state="FAILED" detail="run_train exit $rc"
  [ "$rc" = 0 ] && state="COMPLETE" && detail="run_train completed"
  if [ "$ENGINE_STOPPED" = 1 ] && [ "$NO_ENGINE" = 0 ]; then
    write_status "RESTARTING-ENGINE" "training ended (rc=$rc); bringing $TARGET back + health-polling"
    if bring_engine_back; then
      detail="$detail; engine $TARGET restored and gateway healthy"
    else
      detail="$detail; ENGINE RESTORE FAILED — see ops log for owner action"
    fi
  fi
  # honest stop-cause from the jsonl final entry, if run_train wrote one
  local cause
  cause=$("$PY" - "$RUNS" <<'PYEOF' 2>/dev/null || true
import json, sys
last = None
for line in open(sys.argv[1], encoding="utf-8"):
    line = line.strip()
    if line:
        try: r = json.loads(line)
        except json.JSONDecodeError: continue
        if r.get("event") == "final": last = r
if last: print(last.get("cause", "?"), last.get("wall_s", "?"))
PYEOF
)
  [ -n "$cause" ] && detail="$detail; stop-cause: $cause"
  write_status "$state" "$detail"
  op "exit rc=$rc state=$state detail: $detail"
  exit "$rc"
}

mkdir -p "$REPORTS"
trap on_exit EXIT
trap 'exit 143' TERM
trap 'exit 130' INT

op "start dry_run=$DRY_RUN no_engine=$NO_ENGINE target=$TARGET cmd=[${RT_ARGS[*]:-}]"

write_status "LIVE" "starting; MemAvailable $(mem_avail) GiB; ETA: per-phase --timeout of run_train (default 3600s)"

# ---- step 1: free memory ----------------------------------------------------
if [ "$NO_ENGINE" = 0 ]; then
  engine-guard status 2>&1 | tee -a "$OPSLOG"
  if container_up; then
    op "stopping engine container $CONTAINER (mirrors ~/models/start_*.sh stop path)"
    docker stop -t 20 "$CONTAINER" >>"$OPSLOG" 2>&1 && docker rm "$CONTAINER" >>"$OPSLOG" 2>&1
    ENGINE_STOPPED=1
    # verify the container is actually DOWN (bounded)
    for _ in $(seq 1 12); do container_up && sleep 5 || break; done
    container_up && { op "container still up — aborting BEFORE training (refusing to OOM-collide)"; write_status FAILED "container $CONTAINER would not stop"; exit 1; }
    op "container $CONTAINER confirmed down"
    # wait for memory to actually appear (page-cache reclaim is not instant)
    waited=0
    while [ "$(mem_avail | awk '{print ($1 < m) ? 1 : 0}' m="$MIN_FREE_GIB")" = 1 ] && [ "$waited" -lt "$FREE_WAIT_S" ]; do
      sleep 5; waited=$((waited + 5))
    done
    op "MemAvailable now $(mem_avail) GiB (target ${MIN_FREE_GIB})"
  else
    op "container $CONTAINER not running — nothing to stop; MemAvailable $(mem_avail) GiB"
  fi
  engine-guard status 2>&1 | tee -a "$OPSLOG"
else
  op "--no-engine: skipping docker stop and engine restart (trap path is still armed)"
fi

# ---- step 2: train (NOT exec: exec would wipe the EXIT trap; foreground so
#      the trap sees the real rc and Ctrl-C/kill still route through it) ------
if [ "$DRY_RUN" = 1 ]; then
  op "dry-run: training step = sleep 20 (wrapped in run_train to exercise the full path)"
  write_status "LIVE" "dry-run training (sleep 20)"
  "$PY" "$RUNNER" --phase dry-run --timeout 60 -- sleep 20
else
  write_status "LIVE" "training phase under watchdog; cmd=${RT_ARGS[*]}"
  "$PY" "$RUNNER" "${RT_ARGS[@]}"
fi
rc=$?
op "training step finished rc=$rc"
exit "$rc"
