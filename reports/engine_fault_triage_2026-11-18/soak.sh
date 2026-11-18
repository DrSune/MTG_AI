#!/bin/bash
# soak.sh: B-73's re-measure (215, F65): the anomaly detectors D1-D6 and invariant I1 over the
# three deal pools as games deal them (verified mode), 300 seeded random games each (stress decks;
# seeds 1-300), on main 8d85e0a7. CPU-only, niced, under an 8G cap, two workers.
W=/home/sune/Desktop/MTG_AI/.claude/worktrees/agent-af166858a9ce5175f
OUT=$W/reports/engine_fault_triage_2026-11-18
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
