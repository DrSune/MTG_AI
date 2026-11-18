#!/bin/bash
# soak.sh: W0's soak baseline (KNOWLEDGE 215 §8 e) with the fixed detectors: the anomaly detectors
# D1-D6 and invariant I1 over the three deal pools as games deal them (verified mode), 300 seeded
# random games each (stress decks; seeds 1-300), as reports/engine_fault_triage_2026-11-18/soak.sh
# ran them. CPU-only, niced, under an 8G cap, two workers. W1's baseline.
W=$(cd "$(dirname "$0")/../.." && pwd)
OUT=$W/reports/engine_wave_w0_2026-11-18
PY=/home/sune/Desktop/MTG_AI/.venv/bin/python
export CUDA_VISIBLE_DEVICES=
export OMP_NUM_THREADS=2
cd "$W" || exit 1
for code in M21 M20 FDN; do
  systemd-run --user --scope -q -p MemoryMax=8G -p MemorySwapMax=0 nice -n 19 \
    $PY tools/cards/soak.py $code --games 300 --mode verified --workers 2 \
    --out $OUT/soak_$code.json > $OUT/soak_$code.log 2>&1
done
echo done
