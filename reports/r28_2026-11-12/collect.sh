#!/bin/bash
# One on-policy batch of a checkpoint under r28's flags, from r28's worktree (44a62d9), for the
# looks' probes (199 §4, PLAN_CEILING §14.4):  collect.sh CKPT OUT_DIR SEED
# r28 must be paused first (one job on the GPU).
set -euo pipefail
systemctl --user is-active -q mtg-r28 && { echo "pause r28 first: systemctl --user stop mtg-r28"; exit 1; }
ckpt=$1 out=$2 seed=$3
mkdir -p "$out"
cd /home/sune/Desktop/MTG_AI-r28
export PYTHONDONTWRITEBYTECODE=1 PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
exec .venv/bin/python -m tools.selfplay.learner --run "$out/run" --init "$ckpt" --seed "$seed" \
  --workers 18 --slots 16 --groups 4 --gamma 1.0 --lam 1.0 --steps 139264 --epochs 1 --lr 2e-5 \
  --wd 0.01 --clip 0.2 --vclip 0.5 --vcoef 0.5 --ent 0.004 --max-grad 1.0 --target-kl 0 --mb 4096 \
  --tok-budget 98304 --infer-bf16 --teacher-iters 0 --gate-every 25 --gate-deals 1000 \
  --gate-score 0.55 --ladder-deals 500 --p-heuristic 0.15 --p-past 0.15 --coherent-share 1.0 \
  --mix-sets M20 --mix-share 0.25 --extend-sets M20 --pool verified --save-every 5 \
  --progress-every 300 --mem-floor-gib 15.0 --iters 6000 --collect "$out/batch.pkl"
