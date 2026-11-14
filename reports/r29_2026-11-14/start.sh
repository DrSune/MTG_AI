#!/bin/bash
# Start or resume one arm of r29 (KNOWLEDGE/2026-11-14/208) as the transient user unit mtg-r29<arm>,
# with its guard mtg-r29<arm>-guard, from the worktree pinned at the launch commit; the learner
# resumes from its last save. A transient unit leaves no file behind and does not come back after a
# reboot: run this again then. Pausing is `systemctl --user stop mtg-r29<arm> mtg-r29<arm>-guard`.
#   start.sh a|b
set -euo pipefail
arm=${1:?a or b}
case $arm in a) p=0 ;; b) p=0.55 ;; *) echo "arm a or b" >&2; exit 2 ;; esac
W=${W:-/home/sune/Desktop/MTG_AI-r29}
R=${R:-/home/sune/Desktop/MTG_AI/runs/selfplay}
INIT=${INIT:-/home/sune/Desktop/MTG_AI/runs/r28_looks/r28_u685.pt}
run=$R/r29${arm}_pself${p/./}
unit=mtg-r29$arm
systemctl --user is-active -q "$unit" && { echo "$unit already active"; exit 0; }
# r28's flags (199 §1), --seed 29 and the arm's self share. A CPU smoke sets CUDA_VISIBLE_DEVICES
# and OMP_NUM_THREADS (passed into the unit) and WORKERS, SLOTS, STEPS and MB
systemd-run --user --unit "$unit" --working-directory="$W" \
  ${CUDA_VISIBLE_DEVICES+--setenv=CUDA_VISIBLE_DEVICES=$CUDA_VISIBLE_DEVICES} \
  ${OMP_NUM_THREADS+--setenv=OMP_NUM_THREADS=$OMP_NUM_THREADS} \
  -p Restart=on-failure -p RestartSec=300 -p SuccessExitStatus=143 \
  -p StandardOutput=append:"$run.out" -p StandardError=inherit \
  "$W/tools/selfplay/launch.sh" "$run" \
  --init "$INIT" --seed 29 --workers "${WORKERS:-18}" --slots "${SLOTS:-16}" --groups 4 \
  --gamma 1.0 --lam 1.0 --steps "${STEPS:-139264}" --epochs 1 --lr 2e-5 --wd 0.01 --clip 0.2 \
  --vclip 0.5 --vcoef 0.5 --ent 0.004 --max-grad 1.0 --target-kl 0 --mb "${MB:-4096}" \
  --tok-budget 98304 --infer-bf16 --teacher-iters 0 --gate-every 25 --gate-deals 1000 \
  --gate-score 0.55 --ladder-deals 500 --p-heuristic 0.15 --p-past 0.15 --p-self "$p" \
  --coherent-share 1.0 --mix-sets M20 --mix-share 0.25 --extend-sets M20 --refresh-table \
  --pool verified --save-every 5 --progress-every 300 --mem-floor-gib 15.0 --iters 6000
systemctl --user is-active -q "$unit-guard" || systemd-run --user --unit "$unit-guard" \
  --working-directory="$W" "$W/.venv/bin/python" -m tools.selfplay.guard "$run" "$unit"
