#!/bin/bash
# One arm of the --p-self CPU smoke (2026-11-14): r28's flags from r28's v0, tiny, on the CPU,
# beside a training run. Run from the repository root:  smoke.sh P_SELF RUN_DIR
# The arms ran at 0.7 (runs/pself_smoke_2026-11-14/self70) and 0 (.../self0), side by side;
# read.py RUN_DIR prints their numbers.
set -euo pipefail
p=$1 run=$2
export CUDA_VISIBLE_DEVICES= OMP_NUM_THREADS=2 PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1
exec systemd-run --user --scope -q -p MemoryMax=16G -p MemorySwapMax=0 nice -n 19 \
  .venv/bin/python reports/pself_smoke_2026-11-14/counted.py --run "$run" \
  --init /home/sune/Desktop/MTG_AI/runs/selfplay/r28_stratified_ppo/v0.pt --device cpu \
  --seed 2914 --workers 2 --slots 8 --groups 2 --gamma 1.0 --lam 1.0 --steps 1024 --epochs 1 \
  --lr 2e-5 --wd 0.01 --clip 0.2 --vclip 0.5 --vcoef 0.5 --ent 0.004 --max-grad 1.0 \
  --target-kl 0 --mb 256 --tok-budget 16384 --teacher-iters 0 --gate-every 1000 \
  --ladder-deals 1 --p-heuristic 0.15 --p-past 0.15 --p-self "$p" --coherent-share 1.0 \
  --mix-sets M20 --mix-share 0.25 --extend-sets M20 --refresh-table --pool verified \
  --save-every 1000 --progress-every 120 --mem-floor-gib 20 --iters 10
