#!/bin/bash
# Start or resume r28 (KNOWLEDGE/2026-11-12/199) as the transient user unit mtg-r28, from the
# worktree pinned at its launch commit; the learner resumes from its last save. A transient unit
# leaves no file behind and does not come back after a reboot: run this again then. Pausing is
# `systemctl --user stop mtg-r28` (the unit then goes away; this script brings it back).
set -euo pipefail
systemctl --user is-active -q mtg-r28 && { echo "mtg-r28 already active"; exit 0; }
W=/home/sune/Desktop/MTG_AI-r28
R=/home/sune/Desktop/MTG_AI/runs/selfplay
systemd-run --user --unit mtg-r28 --working-directory="$W" \
  -p Restart=on-failure -p RestartSec=300 -p SuccessExitStatus=143 \
  -p StandardOutput=append:$R/r28_stratified_ppo.out -p StandardError=inherit \
  "$W/tools/selfplay/launch.sh" "$R/r28_stratified_ppo" \
  --init "$R/r27_priority_ppo/v1.pt" --seed 28 --workers 18 --slots 16 --groups 4 \
  --gamma 1.0 --lam 1.0 --steps 139264 --epochs 1 --lr 2e-5 --wd 0.01 --clip 0.2 --vclip 0.5 \
  --vcoef 0.5 --ent 0.004 --max-grad 1.0 --target-kl 0 --mb 4096 --tok-budget 98304 --infer-bf16 \
  --teacher-iters 0 --gate-every 25 --gate-deals 1000 --gate-score 0.55 --ladder-deals 500 \
  --p-heuristic 0.15 --p-past 0.15 --coherent-share 1.0 --mix-sets M20 --mix-share 0.25 \
  --extend-sets M20 --refresh-table --pool verified --save-every 5 --progress-every 300 \
  --mem-floor-gib 15.0 --iters 6000
