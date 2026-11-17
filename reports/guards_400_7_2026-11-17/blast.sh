#!/bin/bash
# Blast radius of the branch's engine change: 200 seeded heuristic games per dealt pool on each
# side (E1's replay_abg.py), compared game by game. CPU-only, capped.
#   blast.sh <base checkout> <tag>
# Run against c80f45f7 (before main was merged, branch at a5df0852) and against main a7b7ac35
# (the branch after the merge, the review fixes included).
S=/tmp/claude-1000/-home-sune/53a867d9-979e-400a-9ce1-caf029cc7b16/scratchpad/guards
W=/home/sune/Desktop/MTG_AI/.claude/worktrees/agent-aee2edc561a82da47
R=$W/reports/hunt_e1_2026-11-17
PY=/home/sune/Desktop/MTG_AI/.venv/bin/python
BASE=$1
TAG=$2
export CUDA_VISIBLE_DEVICES=
export OMP_NUM_THREADS=1
cap() { systemd-run --user --scope -q -p MemoryMax=8G -p MemorySwapMax=0 nice -n 19 "$@"; }
cap "$PY" "$R/replay_abg.py" "$BASE" 200 "$S/replay_${TAG}_base.json" > "$S/replay_${TAG}_base.log" 2>&1 &
cap "$PY" "$R/replay_abg.py" "$W" 200 "$S/replay_${TAG}_branch.json" > "$S/replay_${TAG}_branch.log" 2>&1 &
wait
"$PY" "$R/replay_compare_abg.py" "$S/replay_${TAG}_base.json" "$S/replay_${TAG}_branch.json" > "$S/replay_compare_${TAG}.txt" 2>&1
echo done
