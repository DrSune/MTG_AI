#!/bin/bash
# soak_seeds.sh: the seeds of soak.sh's detector hits in the two pools that had any (M21, FDN).
W=/home/sune/Desktop/MTG_AI/.claude/worktrees/agent-af166858a9ce5175f
OUT=$W/reports/engine_fault_triage_2026-11-18
PY=/home/sune/Desktop/MTG_AI/.venv/bin/python
export CUDA_VISIBLE_DEVICES=
export OMP_NUM_THREADS=2
cd "$W" || exit 1
: > $OUT/soak_seeds.txt
for code in M21 FDN; do
  nice -n 19 $PY $OUT/soak_seeds.py "$W" $code 300 >> $OUT/soak_seeds.txt 2>/dev/null
done
echo done
