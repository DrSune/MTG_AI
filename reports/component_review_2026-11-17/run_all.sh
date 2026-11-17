#!/usr/bin/env bash
# Regenerates every output of KNOWLEDGE/2026-11-17/210 from the repository root, CPU only and
# gently. The checkpoint (argument 1, default r28's v2) is read only, on the CPU.
set -euo pipefail
cd "$(dirname "$0")/../.."
ck="${1:-/home/sune/Desktop/MTG_AI/runs/r28_looks/r28_v2.pt}"
d=reports/component_review_2026-11-17
run() { CUDA_VISIBLE_DEVICES= OMP_NUM_THREADS=2 nice -n 19 .venv/bin/python "$@"; }
run "$d/dump.py"
for s in vocab inventory network rare_classify duplicates remaining proposals; do
  run "$d/$s.py" > "$d/$s.txt"
done
run "$d/checkpoint_table.py" "$ck" > "$d/checkpoint_table.txt"
run "$d/pool_check.py" "$ck" > "$d/pool_check.txt"
