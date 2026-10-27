#!/usr/bin/env bash
# rl_pilot_phases.sh — /134 RL-pilot NIGHT-1 phase driver.
# Called INSIDE the window by tools/ops/rl_window.sh (cwd = clean export).
# Not meant to run outside a window: it assumes engine state is the parent's
# business (swap/restore + traps live in rl_window.sh; this driver only runs
# the payload). Env contract from the parent: VENV SRC ART LEDGER RUNLOG DRY
# RESTART_E MARGIN TRAIN_DEV ANCHOR_REL CANCEL_FILE.
# Exit codes: 5 owner opt-out | 6 audit RED | 7 F4 diag keys missing |
#             8 hard step failure/timeout | 0 full chain done.
# Any nonzero exit here propagates to the parent's ERR/EXIT trap => engine
# restore is guaranteed. Failure is never papered over.
set -Eeuo pipefail

: "${VENV:?}" "${SRC:?}" "${ART:?}" "${LEDGER:?}" "${RUNLOG:?}"
: "${DRY:?}" "${RESTART_E:?}" "${MARGIN:?}" "${TRAIN_DEV:?}"
: "${ANCHOR_REL:?}" "${CANCEL_FILE:?}"

cd "$SRC"
mkdir -p "$ART"

# counts: NIGHT-1 calibration spec = smoke 2 | calib 50 | iteration-1 1000.
# DRY forces 2/2/2 everywhere (incl. probes) but skips NOTHING structurally —
# the whole chain must be proven end-to-end (r1 precedent: dry trained real S0).
if [[ $DRY -eq 1 ]]; then
  TAGP="dry_"
  G_SMOKE=2; G_CALIB=2; G_ITER1=2
  P1_GAMES=2; P2_GAMES=2
  WORKERS=2
else
  TAGP=""
  G_SMOKE=2; G_CALIB=50; G_ITER1=1000
  P1_GAMES=60; P2_GAMES=200
  WORKERS=6
fi

log() { echo "[$(date '+%F %T')] [phases] $*" >&2; }   # stderr: step json stays clean
now() { date +%s; }
ledger_row() { local IFS='|'; echo "| $* |" >> "$LEDGER"; }   # $* joins fields with IFS[0]

check_cancel() {   # v2 morning opt-out: re-checked before EVERY phase
  if [[ -e $CANCEL_FILE ]]; then
    log "OWNER OPT-OUT: $CANCEL_FILE exists mid-window — aborting chain NOW (parent trap restores engine; overrun rule: restore NOW, resume next window)"
    exit 5
  fi
}

# guard_to DESIRED_S FLOOR_S -> prints usable timeout (desired clamped to the
# RESTART_AT-minus-margin budget) or returns 1 when the budget is too small.
guard_to() {
  local desired=$1 floor=$2
  local left=$(( RESTART_E - $(now) - MARGIN ))
  local t=$desired
  [[ $t -gt $left ]] && t=$left
  if (( t < floor )); then
    log "budget guard: only ${left}s left before RESTART-minus-${MARGIN}s margin (< ${floor}s floor) — step skipped honestly"
    return 1
  fi
  echo "$t"
}

# run_hard DESC TIMEOUT -- python args... : every python call is timeout-guarded;
# nonzero rc (incl. timeout=124) STOPS the chain — parent trap restores engine.
HARD_RC=0
run_hard() {
  local desc=$1 to=$2; shift 2
  log "RUN (timeout ${to}s): $*"
  HARD_RC=0
  set +e
  timeout "$to" "$@"
  HARD_RC=$?
  set -e
  if [[ $HARD_RC -ne 0 ]]; then
    ledger_row "FAIL" "$desc" "-" "-" "-" "-" "rc=$HARD_RC" "chain stopped"
    log "$desc: FAILED rc=$HARD_RC (timeout ${to}s) — phase chain STOPS; parent trap restores engine NOW"
    exit 8
  fi
}

# collect TAG GAMES SEED_BASE DECK_PAIRS_SEED RL_SEED -> sets WALL_S
WALL_S=0
collect() {
  local tag=$1 games=$2 sb=$3 dps=$4 rlseed=$5 to
  to=$(guard_to 18000 120) || return 1
  local t0=$(now)
  run_hard "collect/$tag" "$to" "$VENV" -m tools.eval.gameplay_eval_v2 \
    --policy-a "$ANCHOR_REL" --matchups teacher --games "$games" \
    --workers "$WORKERS" --pool engine --device cpu \
    --sample --rl-collect "$ART/${TAGP}episodes_${tag}.jsonl" --rl-seed "$rlseed" \
    --seed-base "$sb" --deck-pairs-seed "$dps" \
    --out "$ART/${TAGP}collect_${tag}.json"
  WALL_S=$(( $(now) - t0 ))
  local rate
  rate=$(awk -v g="$games" -v w="$WALL_S" 'BEGIN{printf "%.4f", (w>0? g/w : 0)}')
  log "collect/$tag: $games games in ${WALL_S}s wall = ${rate} g/s net (device cpu, $WORKERS workers, rl-seed $rlseed, seed-base $sb, dps $dps)"
  ledger_row "collect" "$tag" "$tag" "$games" "$WALL_S" "$rate" "rc=0" "cpu x$WORKERS sample+rl-collect"
  local rows=0
  [[ -f $ART/${TAGP}episodes_${tag}.jsonl ]] && rows=$(wc -l < "$ART/${TAGP}episodes_${tag}.jsonl")
  log "collect/$tag: $rows episode rows -> $ART/${TAGP}episodes_${tag}.jsonl"
  return 0
}

audit() {   # RED (nonzero) = logprob plumbing broken => halt (v2 F4 discriminator)
  local tag=$1 to rc
  # cuda: inside the window the engine container is stopped, so the GPU is
  # free and the audit is minutes, not hours. The CPU audit measured ~4.8 s/game
  # (night-1 /151): 50g calib GREEN in ~4 min, but 1000g iter-1 needed ~80 min >
  # the 3600 s guard -> rc=124 AUDIT RED, chain stopped honestly. Cross-device
  # delta vs the CPU-recorded logπ is measured in the real-mode smoke (/151)
  # and stays far under --tol 1e-3; device cannot fake an off-policy match.
  to=$(guard_to 3600 60) || { log "audit/$tag: budget too small — cannot certify plumbing — chain STOPS honestly"; exit 8; }
  log "RUN (timeout ${to}s): $VENV -m tools.training.rl_logprob_audit --episodes $ART/${TAGP}episodes_${tag}.jsonl --policy $ANCHOR_REL --device cuda (json -> ${TAGP}audit_${tag}.json)"
  set +e
  timeout "$to" "$VENV" -m tools.training.rl_logprob_audit \
      --episodes "$ART/${TAGP}episodes_${tag}.jsonl" --policy "$ANCHOR_REL" \
      --device cuda > "$ART/${TAGP}audit_${tag}.json" 2>>"$ART/${TAGP}audit_${tag}.err"
  rc=$?
  set -e
  if [[ $rc -ne 0 ]]; then
    log "AUDIT RED for $tag (rc=$rc; see $ART/${TAGP}audit_${tag}.err): recorded logπ does NOT come from the collecting net — the whole RL payload is invalid. Chain ABORTS; parent trap restores engine."
    ledger_row "FAIL" "audit/$tag" "$tag" "-" "-" "-" "rc=$rc" "audit RED -> halt"
    exit 6
  fi
  log "audit/$tag: GREEN (max|Δ| report -> $ART/${TAGP}audit_${tag}.json)"
  ledger_row "audit" "$tag" "$tag" "-" "-" "-" "GREEN" "off-policy discriminator"
}

# train TAG EPISODES -> saves $ART/${TAGP}${TAG}.pt + _diag.json; device=TRAIN_DEV
# LR is the night-3 lever (/157): 1e-4 = 10x the 1e-5 of nights 1-2, whose single
# SGD update moved the policy sub-threshold (MIRROR-FLAT, /156: weight step ~1e-5,
# mean|dlogp| 1.7e-6, share|dlogp|>0.1 = 0). One lever value per night, documented
# in the KNOWLEDGE entry that arms it; changing it is a payload change => re-smoke
# (real mode) + explicit re-pin before the window.
train() {
  local tag=$1 ep=$2 to
  to=$(guard_to 7200 120) || { log "train/$tag: budget too small — chain stops honestly (never start an update that can be cut off mid-save)"; exit 8; }
  run_hard "train/$tag" "$to" "$VENV" -m tools.training.train_rl_v1 \
    --episodes "$ep" --policy "$ANCHOR_REL" --anchor "$ANCHOR_REL" \
    --device "$TRAIN_DEV" --tag "${TAGP}${tag}" --out-dir "$ART" \
    --lr 1e-4
  ledger_row "train" "$tag" "$tag" "-" "-" "-" "rc=0" "device=$TRAIN_DEV 1 update"
  diag_ok "$tag"
}

diag_ok() {   # F4 no-op-vs-collapse discriminator keys MUST be present
  local f="$ART/${TAGP}${1}_diag.json" k
  [[ -f $f ]] || { log "F4 diag MISSING: $f — trainer did not verify; chain STOPS"; exit 7; }
  for k in grad_norm_preclip kl_mean_per_game mean_abs_dlogp_chosen reward_var kl_ceiling_breach; do
    grep -q "\"$k\"" "$f" || { log "F4 diag key MISSING: $k in $f — chain STOPS"; exit 7; }
  done
  log "F4 diag OK: $f ($(tr -d ' \n' < "$f" | cut -c1-200)...)"
}

# probe TAG POLICY GAMES SEED_BASE DECK_PAIRS_SEED : mirrors vs frozen pre-RL
# anchor + teacher rows; nonzero = logged, chain continues (r1 duel leniency).
probe() {
  local tag=$1 policy=$2 games=$3 sb=$4 dps=$5 to
  to=$(guard_to 10800 120) || { log "probe/$tag: budget too small — SKIPPED honestly"; ledger_row "probe" "$tag" "$tag" "$games" "-" "-" "SKIPPED" "budget"; return 0; }
  log "probe/$tag: policy=$policy games=$games/matchup lanes=mirror,teacher mirror-b=$ANCHOR_REL (frozen pre-RL anchor) seed-base=$sb dps=$dps"
  set +e
  timeout "$to" "$VENV" -m tools.eval.gameplay_eval_v2 \
    --policy-a "$policy" --policy-b "$ANCHOR_REL" --matchups mirror,teacher \
    --games "$games" --workers "$WORKERS" --pool engine --device cpu \
    --seed-base "$sb" --deck-pairs-seed "$dps" \
    --out "$ART/${TAGP}probe_${tag}.json"
  local rc=$?
  set -e
  if [[ $rc -ne 0 ]]; then
    log "probe/$tag: rc=$rc (partial json as-is, descriptive rows only per v2 F1)"
    ledger_row "probe" "$tag" "$tag" "$games" "-" "-" "rc=$rc" "partial/descriptive"
  else
    ledger_row "probe" "$tag" "$tag" "$games" "-" "-" "rc=0" "mirror,teacher -> ${TAGP}probe_${tag}.json"
  fi
}

# ----------------------------------------------------------------- phases
log "=== /134 NIGHT-1 driver start: dry=$DRY device=$TRAIN_DEV counts=${G_SMOKE}/${G_CALIB}/${G_ITER1} probes=${P1_GAMES}/${P2_GAMES} workers=$WORKERS RESTART_E=$RESTART_E ==="

# PHASE 0 — smoke (any mode): proves collect->audit->train plumbing end-to-end
check_cancel
log "--- PHASE 0 (smoke) ---"
collect smoke "$G_SMOKE" 511001 1409 4242 || { log "phase0 collect skipped on budget — nothing can follow; honest abort"; exit 8; }
audit smoke
train rld_smoke "$ART/${TAGP}episodes_smoke.jsonl"

# PHASE 1 — calibration (THE calibration output: per-game collection rates)
check_cancel
log "--- PHASE 1 (calibration): ${G_CALIB}g + probe ${P1_GAMES}g ---"
P1_T0=$(now)
if collect calib "$G_CALIB" 510101 1410 4243; then
  audit calib
  train rld_cal "$ART/${TAGP}episodes_calib.jsonl"
  probe p1 "$ART/${TAGP}rld_cal.pt" "$P1_GAMES" 512001 1411
else
  log "PHASE 1 collect SKIPPED on budget guard — calibration wall unavailable; phase 2 cannot be sized -> honest end of chain"
  log "=== driver done: phase-1 never ran; parent restores engine on schedule ==="
  exit 0
fi
PHASE1_WALL=$(( $(now) - P1_T0 ))
{
  echo "PHASE1_WALL_S=$PHASE1_WALL"
  echo "DRY=$DRY"
  echo "CALIB_GAMES=$G_CALIB"
} > "$ART/${TAGP}timing.env"
log "PHASE 1 wall_s=$PHASE1_WALL (calibration record: $ART/${TAGP}timing.env)"
ledger_row "calib" "phase1-wall" "total" "$G_CALIB" "$PHASE1_WALL" "-" "done" "budget input for phase 2"

# PHASE 2 — iteration-1, ONLY if the honest budget formula clears:
#   (RESTART_E - now) > measured_phase1_wall * 18 + 45-min margin.
# 18 = owner-specified extrapolation factor (1000g collection is 20x the 50g
# calibration, tempered for audit/train/probe steps) — applied LITERALLY to the
# full measured phase-1 wall, not just its collect step.
check_cancel
NEED=$(( PHASE1_WALL * 18 + MARGIN ))
HAVE=$(( RESTART_E - $(now) ))
if (( HAVE > NEED )); then
  log "--- PHASE 2 (iteration-1): ${G_ITER1}g + probe ${P2_GAMES}g | have ${HAVE}s > need ${NEED}s (=${PHASE1_WALL}*18+${MARGIN}) ---"
  collect iter1 "$G_ITER1" 510201 1412 4244 || { log "phase2 collect skipped on budget — honest stop"; exit 0; }
  audit iter1
  train rld_i1 "$ART/${TAGP}episodes_iter1.jsonl"
  probe p2 "$ART/${TAGP}rld_i1.pt" "$P2_GAMES" 512002 1413
else
  log "PHASE 2 SKIPPED honestly: only ${HAVE}s to RESTART (need ${NEED}s = phase1_wall ${PHASE1_WALL}s x18 + ${MARGIN}s margin) — restore on schedule, resume next window (v2 overrun law)"
  ledger_row "budget" "phase2-skip" "iter1" "$G_ITER1" "-" "-" "SKIPPED" "have=${HAVE}s need=${NEED}s"
fi

log "=== /134 NIGHT-1 driver done: full chain complete — parent restores engine on the normal path ==="
exit 0
