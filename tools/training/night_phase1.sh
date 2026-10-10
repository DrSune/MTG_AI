#!/usr/bin/env bash
# night phase 1: act-sense-trained checkpoints (small arms x3 seeds) then immediate
# gameplay v2 re-eval: NEW (bc9_S3_s1) vs greedy TEACHER + mirror vs OLD (bc7_S3_s1).
set -uo pipefail
cd "$(dirname "$0")/../.." || exit 8
echo "PH1 alive $(date +%H:%M:%S)"
for spec in "S0 1" "S0 2" "S0 3" "S3 1" "S3 2" "S3 3"; do
  set -- $spec; pref="bc9_${1}_s${2}"
  [ -f "tools/training/${pref}_report.json" ] && { echo "skip $pref"; continue; }
  timeout 900 .venv/bin/python -m tools.training.train_bc_v3 --arm "$1" --seed "$2" --prefix "$pref" \
    && echo "OK $pref $(date +%H:%M:%S)" || echo "FAIL $pref rc=$? $(date +%H:%M:%S)"
done
echo "PH1 training done $(date +%H:%M:%S)"
timeout 5400 .venv/bin/python tools/eval/gameplay_eval_v2.py --policy-a tools/training/bc9_S3_s1_best.pt --policy-b tools/training/bc7_S3_s1_best.pt --matchups mirror,teacher --games 200 --workers 4 --device cpu \
  --out tools/eval/gameplay_eval_v3_actsense.json \
  && echo "EVAL-TEACHER DONE $(date +%H:%M:%S)" || echo "EVAL-TEACHER FAILED rc=$? $(date +%H:%M:%S)"
echo PH1_ALL_DONE
