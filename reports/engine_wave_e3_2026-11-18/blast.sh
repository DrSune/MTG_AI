#!/bin/bash
# blast.sh: engine wave E3's final blast radius, main 2c8eca31 (base2) against the branch head
# (the worktree): the 19 sets' trees, then 600 seeded heuristic games each (200 per verified pool),
# then the differing games' journals. CPU-only, niced, each run under an 8G cap.
S=/tmp/claude-1000/-home-sune/53a867d9-979e-400a-9ce1-caf029cc7b16/scratchpad/e3
W=/home/sune/Desktop/MTG_AI/.claude/worktrees/agent-aa826eade9066c90a
B=$S/base2
PY=/home/sune/Desktop/MTG_AI/.venv/bin/python
export CUDA_VISIBLE_DEVICES=
export OMP_NUM_THREADS=2
cap() { systemd-run --user --scope -q -p MemoryMax=8G -p MemorySwapMax=0 nice -n 19 "$@"; }
cap $PY $W/reports/engine_wave_c1_2026-11-17/tree_dump.py $B $S/trees_base2.json > $S/trees_base2.log 2>&1 &
cap $PY $W/reports/engine_wave_c1_2026-11-17/tree_dump.py $W $S/trees_final.json > $S/trees_final.log 2>&1 &
wait
$PY $W/reports/engine_wave_c1_2026-11-17/tree_diff.py $S/trees_base2.json $S/trees_final.json > $S/tree_diff_final.txt 2>&1
cap $PY $S/replay.py $B $S/trees_base2.json $S/trees_final.json 200 $S/replay_base2.json > $S/replay_base2.log 2>&1 &
cap $PY $S/replay.py $W $S/trees_base2.json $S/trees_final.json 200 $S/replay_final.json > $S/replay_final.log 2>&1 &
wait
$PY $S/compare.py $S/replay_base2.json $S/replay_final.json $S/differing_final.txt > $S/replay_compare_final.txt 2>&1
if [ -s $S/differing_final.txt ] && grep -q ":" $S/differing_final.txt; then
  cap $PY $S/replay.py $B $S/trees_base2.json $S/trees_final.json 200 $S/rows_base2.json $S/differing_final.txt > $S/rows_base2.log 2>&1 &
  cap $PY $S/replay.py $W $S/trees_base2.json $S/trees_final.json 200 $S/rows_final.json $S/differing_final.txt > $S/rows_final.log 2>&1 &
  wait
  $PY $S/compare.py --rows $S/rows_base2.json $S/rows_final.json > $S/first_diff_final.txt 2>&1
fi
echo done
