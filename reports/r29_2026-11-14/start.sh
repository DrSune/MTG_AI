#!/bin/bash
# Start or resume one arm of r29 (KNOWLEDGE/2026-11-14/208) as the transient user unit mtg-r29<arm>,
# with its guard mtg-r29<arm>-guard, from the worktree pinned at the launch commit; the learner
# resumes from its last save (launch.sh) and runs to the --iters given now (ITERS: the queue runs
# A with 120 during the A/B, and the arm that goes on with 6000). A transient unit leaves no file
# behind and does not come back after a reboot: run this again then. Pausing is
# `systemctl --user stop mtg-r29<arm> mtg-r29<arm>-guard`.
#   start.sh a|b
# A CPU smoke sets W, R, INIT, ITERS, SAVE_EVERY, UNIT_PREFIX (another unit name), WORKERS, SLOTS,
# STEPS and MB, and CUDA_VISIBLE_DEVICES, OMP_NUM_THREADS and NEED_GIB (launch.sh's memory wait,
# which would hold a smoke beside a training run), which pass into the unit. The units run at the
# caller's niceness, so a smoke's nice -n 19 reaches them.
set -euo pipefail
arm=${1:?a or b}
case $arm in a) p=0 ;; b) p=0.55 ;; *) echo "arm a or b" >&2; exit 2 ;; esac
W=${W:-/home/sune/Desktop/MTG_AI-r29}
R=${R:-/home/sune/Desktop/MTG_AI/runs/selfplay}
INIT=${INIT:-/home/sune/Desktop/MTG_AI/runs/r28_looks/r28_v2.pt}
run=$R/r29${arm}_pself${p/./}
unit=${UNIT_PREFIX:-mtg-r29}$arm
# launch.sh runs the worktree's own .venv: without it the unit would fail and restart all night
[ -x "$W/.venv/bin/python" ] || {
  echo "$W/.venv/bin/python is not executable (ln -s /home/sune/Desktop/MTG_AI/.venv $W/.venv): nothing started" >&2
  exit 1
}
loaded() {  # loaded UNIT: whether UNIT runs this arm (or waits to restart it); another run refuses
  case $(systemctl --user is-active "$1") in
    inactive|failed) systemctl --user reset-failed "$1" 2>/dev/null || true; return 1 ;;
  esac
  # a unit of this name may run a smoke's run or the other arm's: never take it for this arm
  [[ $(systemctl --user show -p ExecStart --value "$1") == *" $run "* ]] && return 0
  echo "$1 is active but does not run $run: nothing started" >&2
  exit 1
}
env=()
for v in CUDA_VISIBLE_DEVICES OMP_NUM_THREADS NEED_GIB; do
  [ -z "${!v+set}" ] || env+=("--setenv=$v=${!v}")
done
niceness=$(nice)
if loaded "$unit"; then
  echo "$unit already runs $run"
else
  # r28's flags (199 §1), --seed 29 and the arm's self share
  systemd-run --user --unit "$unit" --working-directory="$W" "${env[@]}" -p Nice="$niceness" \
    -p Restart=on-failure -p RestartSec=300 -p SuccessExitStatus=143 \
    -p StandardOutput=append:"$run.out" -p StandardError=inherit \
    "$W/tools/selfplay/launch.sh" "$run" \
    --init "$INIT" --seed 29 --workers "${WORKERS:-18}" --slots "${SLOTS:-16}" --groups 4 \
    --gamma 1.0 --lam 1.0 --steps "${STEPS:-139264}" --epochs 1 --lr 2e-5 --wd 0.01 --clip 0.2 \
    --vclip 0.5 --vcoef 0.5 --ent 0.004 --max-grad 1.0 --target-kl 0 --mb "${MB:-4096}" \
    --tok-budget 98304 --infer-bf16 --teacher-iters 0 --gate-every 25 --gate-deals 1000 \
    --gate-score 0.55 --ladder-deals 500 --p-heuristic 0.15 --p-past 0.15 --p-self "$p" \
    --coherent-share 1.0 --mix-sets M20 --mix-share 0.25 --extend-sets M20 --refresh-table \
    --pool verified --save-every "${SAVE_EVERY:-5}" --progress-every 300 --mem-floor-gib 15.0 \
    --iters "${ITERS:-6000}"
fi
loaded "$unit-guard" || systemd-run --user --unit "$unit-guard" --working-directory="$W" \
  -p Nice="$niceness" "$W/.venv/bin/python" -m tools.selfplay.guard "$run" "$unit"
