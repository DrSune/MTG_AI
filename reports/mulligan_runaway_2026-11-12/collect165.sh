#!/bin/bash
# One on-policy batch of r27's update 165 (runs/window2/r27_latest.pt, sha256 1f5051cf…), with
# r27's own flags, written by learner --collect: the data for ablate.py (KNOWLEDGE 198).
set -euo pipefail
cd /home/sune/Desktop/MTG_AI
O=runs/diag_mull_2026-11-12
exec nice -n 5 .venv/bin/python -m tools.selfplay.learner --run "$O/collect165" \
  --init runs/window2/r27_latest.pt --seed 16501 --workers 18 --slots 16 --groups 4 \
  --gamma 1.0 --lam 1.0 --steps 139264 --epochs 1 --lr 2e-5 --wd 0.01 --clip 0.2 --vclip 0.5 \
  --vcoef 0.5 --ent 0.004 --max-grad 1.0 --target-kl 0 --mb 4096 --tok-budget 98304 \
  --infer-bf16 --teacher-iters 0 --gate-every 25 --gate-deals 1000 --gate-score 0.55 \
  --ladder-deals 500 --p-heuristic 0.15 --p-past 0.15 --coherent-share 1.0 --mix-sets M20 \
  --mix-share 0.25 --extend-sets M20 --pool verified --save-every 5 --progress-every 300 \
  --mem-floor-gib 15.0 --iters 6000 --collect "$O/collect165.pkl"
