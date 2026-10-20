#!/usr/bin/env bash
# rl_window.sh — /134 RL-pilot GPU window, OWNER-AUTHORIZED (GO 2026-10-20;
# spec KNOWLEDGE/2026-10-20/134-rl-pilot-design-draft.md v2 governs).
# Plumbing is a copy of r1_window.sh's PROVEN structure (KNOWLEDGE/2026-10-19/130 §2):
# engine swap is dry-guarded, restore is trap-guaranteed on EXIT/ERR/INT/TERM,
# dirty tree is logged not aborted (payload runs from a CLEAN EXPORT git archive
# HEAD -> /tmp/opencode/rl_n1_train_src). NO docker command ever executes in
# dry-run mode. AGENTS.md engine-law DEVIATION RECORD: this detached script
# (NOT any live agent session) runs docker stop/start of qwen-nvfp4 in the real
# window; /130 §2 precedent. Payload: tools/ops/rl_pilot_phases.sh (phase driver).
# NEW vs r1: --cancel-file (owner morning opt-out, re-checked before each phase),
# --gpu-train (trainer device), ledger reports/rl_window_run.log (distinct from r1).
set -Eeuo pipefail

# ------------------------------------------------------------------ config
REPO=/home/sune/Desktop/MTG_AI
VENV="$REPO/.venv/bin/python"
ENGINE=qwen-nvfp4
GATEWAY=http://127.0.0.1:8000/v1/models   # gateway process (host python3, survives stop)
PLUGIN_LOG="$HOME/.local/share/opencode/log/opencode.log"
SRC=/tmp/opencode/rl_n1_train_src         # clean git-archive export (+ hashed overlay)
LANE=/tmp/opencode/rl_n1_window           # this window's /tmp working dir
ART=/tmp/opencode/rld_n1                  # NIGHT-1 artifacts (harvested next morning; NOT the repo)
RUNLOG="$REPO/reports/rl_window_run.log"
ANCHOR_REL="tools/training/bsh_S3a_s1_best.pt"   # frozen pre-RL anchor (frontier clone)
DRIVER_REL="tools/ops/rl_pilot_phases.sh"
MARGIN=2700                               # 45-min restore margin (r1 convention)

START_AT=23:59
RESTART_AT=07:00
DRY=0
GPU_TRAIN=0
CANCEL_FILE=/tmp/opencode/RL_WINDOW_CANCEL
while [[ $# -gt 0 ]]; do
  case "$1" in
    --start-at)    START_AT=$2; shift 2 ;;
    --restart-at)  RESTART_AT=$2; shift 2 ;;
    --dry-run)     DRY=1; shift ;;
    --gpu-train)   GPU_TRAIN=1; shift ;;
    --cancel-file) CANCEL_FILE=$2; shift 2 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

TODAY=$(date +%F)
if [[ $DRY -eq 1 ]]; then
  LEDGER="$REPO/reports/rl_window_dryrun.md"    # SCRATCH: never the real ledger/NUMBERS
  TRAIN_DEV=cpu                                # dry-run FORCES cpu regardless of --gpu-train
else
  LEDGER="$REPO/reports/rl_window_${TODAY}.md"
  if [[ $GPU_TRAIN -eq 1 ]]; then TRAIN_DEV=cuda; else TRAIN_DEV=cpu; fi
fi

START_E=$(date -d "today $START_AT" +%s)
RESTART_E=$(date -d "today $RESTART_AT" +%s)
[[ $RESTART_E -le $START_E ]] && RESTART_E=$((RESTART_E + 86400))

ENGINE_STOPPED=0
RESTORED=0
PHASES_RC=-1

log() { echo "[$(date '+%F %T')] $*" | tee -a "$RUNLOG"; }
avail_mib() { awk '/MemAvailable/{print $2}' /proc/meminfo; }
gw_code() {   # HTTP code of the gateway models endpoint; 000 = connection refused/gone
  local c
  c=$(curl -s -m 3 -o /dev/null -w '%{http_code}' "$GATEWAY" 2>/dev/null) || true
  echo "${c:-000}"
}

# ------------------------------------------------- engine swap (dry-guarded)
swap_out() {
  local before after code=000
  before=$(avail_mib)
  if [[ $DRY -eq 1 ]]; then
    log "[DRY] would: docker stop -t 30 $ENGINE (engine left running — live agents need it)"
    ENGINE_STOPPED=1   # exercise the trap path; the restore branch echoes in dry mode
    return 0
  fi
  log "docker stop -t 30 $ENGINE ..."
  ENGINE_STOPPED=1     # set BEFORE the stop: any crash mid-swap still triggers restore
  docker stop -t 30 "$ENGINE" >>"$RUNLOG" 2>&1
  for _ in $(seq 1 30); do
    code=$(gw_code)
    [[ $code != 200 ]] && break
    sleep 2
  done
  after=$(avail_mib)
  log "engine-down verified: gateway /v1/models http=$code (expected !=200); MemAvailable ${before}->${after} KiB (delta $(( (after-before)/1024 )) MiB). /87: GPU alloc IS system memory — freeing ~100GiB is the swap's whole purpose."
}

wait_healthy() {
  local deadline=$(( $(date +%s) + 2400 ))   # 40 min cap
  while [[ $(date +%s) -lt $deadline ]]; do
    [[ $(gw_code) == 200 ]] && return 0
    sleep 10
  done
  return 1
}

plugin_log_check() {
  if [[ -f $PLUGIN_LOG ]]; then
    local n
    n=$(tail -n 5000 "$PLUGIN_LOG" | grep -c "failed to load plugin" || true)
    log "/94 plugin-log-check: 'failed to load plugin' in last 5000 log lines: $n"
  else
    log "/94 plugin-log-check: $PLUGIN_LOG absent — check skipped, noted"
  fi
}

restore_engine() {
  if [[ $DRY -eq 1 ]]; then
    log "[DRY] would: docker start $ENGINE + wait-healthy(<=40min) + plugin-log-check"
    log "[DRY] gateway http=$(gw_code) (expected 200 — engine was NEVER touched in dry mode)"
    RESTORED=1
    return 0
  fi
  log "docker start $ENGINE ..."
  docker start "$ENGINE" >>"$RUNLOG" 2>&1 || log "WARN: docker start returned nonzero"
  if wait_healthy; then
    log "gateway healthy again: $GATEWAY -> 200"
  else
    log "CRITICAL: gateway not 200 within 40 min of docker start — inspect: docker logs $ENGINE"
  fi
  plugin_log_check
  RESTORED=1
}

cleanup() {
  set +e
  if [[ $ENGINE_STOPPED -eq 1 ]]; then
    ENGINE_STOPPED=0
    log "=== RESTORE TRAP FIRED (abnormal exit path) — restoring engine ==="
    restore_engine
  fi
  if [[ $RESTORED -eq 1 ]]; then
    log "=== engine restored — attach tmux -r -t rlwindow to read ledger ($LEDGER) ==="
  else
    log "=== window ended WITHOUT any engine swap (nothing to restore) ==="
  fi
}
trap cleanup EXIT
trap 'log "ERR: command failed at line $LINENO (rc=$?)"; exit 1' ERR
trap 'log "SIGINT received"; exit 1' INT
trap 'log "SIGTERM received"; exit 143' TERM

# ------------------------------------- preflight: fail => abort, restart-NOTHING
preflight() {
  log "--- preflight ---"
  log "HEAD: $(git -C "$REPO" rev-parse --short HEAD)  dirty-porcelain-lines: $(git -C "$REPO" status --porcelain | wc -l)  (dirty is LOGGED not aborted: payload runs from a clean git-archive export + hashed overlay)"
  local missing=0 f
  for f in tools/training/train_rl_v1.py tools/training/rl_logprob_audit.py \
           tools/eval/gameplay_eval_v2.py tools/ops/rl_pilot_phases.sh \
           tools/training/bsh_S3a_s1_best.pt; do
    [[ -f "$REPO/$f" ]] || { log "MISSING required file: $f"; missing=1; }
  done
  docker inspect "$ENGINE" --format 'container: {{.Name}} state={{.State.Status}}' \
    >>"$RUNLOG" 2>&1 || { log "MISSING container $ENGINE"; missing=1; }
  log "free -m: $(free -m | awk '/^Mem:/{print "total="$2"M used="$3"M available="$7"M"}')  (/87 unified-memory reality: engine footprint ~100GiB charges system memory)"
  log "gateway now: http=$(gw_code) (expected 200 — engine currently serving agents)"
  [[ $missing -eq 0 ]] || { log "PREFLIGHT FAIL — aborting; nothing touched (restart-nothing per /130 §2)"; exit 3; }
  log "preflight PASS"
}

wait_start() {
  log "window armed: START=$START_AT  HARD-RESTART=$RESTART_AT  dry-run=$DRY  gpu-train=$GPU_TRAIN(train-device=$TRAIN_DEV)  cancel-file=$CANCEL_FILE"
  while [[ $(date +%s) -lt $START_E ]]; do
    local rem
    rem=$(( START_E - $(date +%s) ))
    log "HEARTBEAT: waiting for start, ${rem}s remaining (engine up, agents live)"
    sleep $(( rem < 300 ? rem : 300 ))
  done
  log "START_AT reached"
}

owner_optout() {   # cancel-file exists -> honest exit, engine NEVER touched
  if [[ -e $CANCEL_FILE ]]; then
    log "OWNER OPT-OUT: $CANCEL_FILE exists — exiting window, engine UNTOUCHED (v2 morning opt-out law)"
    return 0
  fi
  return 1
}

clean_export() {
  rm -rf "$SRC"
  mkdir -p "$SRC"
  git -C "$REPO" archive HEAD | tar -x -C "$SRC"
  log "clean export: git archive HEAD ($(git -C "$REPO" rev-parse --short HEAD)) -> $SRC"
  # DEVIATION (logged, /134 NIGHT-1): the payload does not run on HEAD. Three
  # payload files are untracked/working-tree-only and the owner said do-NOT-
  # commit: train_rl_v1.py + bsh_S3a_s1_best.pt (untracked), gameplay_eval_v2.py
  # (HEAD lacks the TASK B per-seat `outcome` field the trainer hard-requires)
  # and ab_duel.py (HEAD's BcAsk._forward_menu lacks the grad= kwarg — dry-run
  # TypeError proved it, 2026-10-20). General deterministic rule instead of a
  # hand-list: EVERY dirty/untracked non-test .py under MTG_bot/ and tools/ is
  # copied over the export, each sha256-logged — the export then runs the SAME
  # code the dry-run exercised. Plus the payload .pt and the driver.
  local files=() f seen=""
  mapfile -t files < <(
    git -C "$REPO" status --porcelain \
      | awk '{print $NF}' \
      | grep -E '^(MTG_bot|tools)/.*\.py$' \
      | grep -vE '(^|/)test_[^/]*\.py$' || true
    echo tools/training/bsh_S3a_s1_best.pt
    echo tools/ops/rl_pilot_phases.sh
  )
  for f in "${files[@]}"; do
    case "$seen" in *"|$f|"*) continue ;; esac
    seen+="|$f|"
    [[ -f "$REPO/$f" ]] && { mkdir -p "$SRC/$(dirname "$f")"; cp "$REPO/$f" "$SRC/$f"; } \
      || { log "WARN: $f is git-dirty but absent from working tree — HEAD version stays in export"; continue; }
    log "overlay-pinned (working-tree code diff): $f sha256=$(sha256sum "$REPO/$f" | cut -c1-16)"
  done
  grep -q -- "--rl-collect" "$SRC/tools/eval/gameplay_eval_v2.py" \
    || { log "EXPORT SANITY FAIL: overlay gameplay_eval_v2.py lacks --rl-collect"; exit 3; }
  grep -q "def _forward_menu(self, torch: Any, ctx: AskContext, grad" "$SRC/tools/training/ab_duel.py" \
    || { log "EXPORT SANITY FAIL: overlay ab_duel.py lacks BcAsk grad kwarg"; exit 3; }
  grep -q "outcome" "$SRC/tools/training/train_rl_v1.py" \
    || { log "EXPORT SANITY FAIL: overlay train_rl_v1.py lacks outcome reward"; exit 3; }
}

ledger_header() {
  {
    echo ""
    echo "## RL-pilot window run — $(date '+%F %T') (dry-run=$DRY, gpu-train-device=$TRAIN_DEV, HEAD $(git -C "$REPO" rev-parse --short HEAD), artifacts $ART)"
    echo ""
    echo "Commands (exact): phase driver $SRC/tools/ops/rl_pilot_phases.sh; per phase: -m tools.eval.gameplay_eval_v2 --policy-a <net> --matchups teacher --sample --rl-collect ...; -m tools.training.rl_logprob_audit --policy <collecting net>; -m tools.training.train_rl_v1 --policy $ANCHOR_REL --anchor $ANCHOR_REL; probes --matchups mirror,teacher --policy-b $ANCHOR_REL (frozen pre-RL anchor)"
    echo ""
    echo "| kind | phase | tag | games | wall_s | rate_g_per_s | rc/result | extra |"
    echo "|---|---|---|---|---|---|---|---|"
  } >> "$LEDGER"
}

run_phases() {
  local rc=0
  log "=== launching phase driver (cwd=$SRC, artifacts=$ART, ledger=$LEDGER) ==="
  set +e
  # `|| rc=$?` (not bare rc=$?): bash 5.2 fires the inherited ERR trap for a
  # failing AND-list inside (...) even under set +e (verified 2026-10-20) —
  # the OR-list form is the trap-safe capture.
  ( cd "$SRC" && env \
      VENV="$VENV" SRC="$SRC" ART="$ART" LEDGER="$LEDGER" RUNLOG="$RUNLOG" \
      DRY="$DRY" RESTART_E="$RESTART_E" MARGIN="$MARGIN" TRAIN_DEV="$TRAIN_DEV" \
      ANCHOR_REL="$ANCHOR_REL" CANCEL_FILE="$CANCEL_FILE" \
      bash "$SRC/$DRIVER_REL" ) >>"$RUNLOG" 2>&1 || rc=$?
  set -e
  PHASES_RC=$rc
  case $rc in
    0) log "phase driver: FULL CHAIN rc=0" ;;
    5) log "phase driver: OWNER OPT-OUT mid-window — honest abort (restore on the normal path)" ;;
    6) log "phase driver: AUDIT RED — logprob plumbing broken, chain STOPPED honestly" ;;
    7) log "phase driver: F4 diag keys missing — trainer not verifying, chain STOPPED honestly" ;;
    *) log "phase driver: unexpected rc=$rc — cause in runlog above; chain STOPPED honestly" ;;
  esac
}

ledger_footer() {
  {
    echo "| window | summary | rc_phases=$PHASES_RC | - | - | - | phases_rc=$PHASES_RC | artifacts=$ART |"
    echo ""
  } >> "$LEDGER"
}

# ---------------------------------------------------------------------- main
main() {
  mkdir -p "$(dirname "$RUNLOG")" "$LANE" "$ART"
  # single-instance lock
  exec 9>/tmp/opencode/rl_window.lock
  flock -n 9 || { echo "another rl_window.sh holds /tmp/opencode/rl_window.lock — refusing to double-run"; exit 4; }
  log "===== rl_window.sh start (dry=$DRY gpu-train=$GPU_TRAIN pid=$$) ====="
  preflight
  wait_start
  owner_optout && exit 5          # at START: log opt-out, EXIT without touching the engine
  ledger_header
  clean_export
  if [[ $DRY -eq 1 ]]; then
    swap_out            # echo-only; sets the trap flag
    run_phases          # REAL end-to-end chain on CPU tiny counts (r1 precedent: dry-run trained a real S0 model as plumbing proof)
    ledger_footer
    restore_engine      # echo-only path through the SAME function the trap uses
    ENGINE_STOPPED=0
    log "[DRY] trap-chain proof: RE-ARMING stop-flag (no docker in dry mode), then FORCING an artificial ERR — the EXIT-cleanup RESTORE branch must fire with echo-only restore"
    ENGINE_STOPPED=1
    sleep 2
    false               # <<< forced ERR: ERR trap -> exit -> cleanup RESTORE branch (echo-only) + banner
  else
    swap_out
    run_phases
    ledger_footer
    log "phase chain done (rc=$PHASES_RC) — restoring engine on the NORMAL path (overrun rule v2: restore NOW, resume next window)"
    restore_engine
    ENGINE_STOPPED=0
    log "===== engine restored — attach tmux -r -t rlwindow to read ledger ($LEDGER), harvest $ART ====="
    sleep infinity      # keep the tmux trail readable until owner kills it
  fi
}
main
