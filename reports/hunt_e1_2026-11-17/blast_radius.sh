#!/bin/bash
# Final blast radius against current main: main e32e0b88 (main3) and the branch head aa92974a
# (final2). 600 seeded heuristic games each (200 per set), the differing games' journals
# classified, then the card trees of the 19 sets; CPU-only, each run under an 8G cap.
F=/tmp/claude-1000/-home-sune/53a867d9-979e-400a-9ce1-caf029cc7b16/scratchpad/fixabg
W=/home/sune/Desktop/MTG_AI/.claude/worktrees/agent-a4c23a5ab23580d48
PY=$W/.venv/bin/python
R=$W/reports/cost_twins_2026-11-14
export CUDA_VISIBLE_DEVICES=
export OMP_NUM_THREADS=2
cap() { systemd-run --user --scope -q -p MemoryMax=8G -p MemorySwapMax=0 nice -n 19 "$@"; }
cap "$PY" "$F/replay_abg.py" "$F/main3" 200 "$F/replay_main3.json" > "$F/replay_main3.log" 2>&1 &
cap "$PY" "$F/replay_abg.py" "$F/final2" 200 "$F/replay_final2.json" > "$F/replay_final2.log" 2>&1 &
wait
"$PY" "$F/replay_compare_abg.py" "$F/replay_main3.json" "$F/replay_final2.json" > "$F/replay_compare_final2.txt" 2>&1
grep -oE "^  (M21|M20|FDN):[0-9]+" "$F/replay_compare_final2.txt" | tr -d ' ' > "$F/differing_final2.txt"
cap "$PY" "$F/dump_journals.py" "$F/main3" "$F/differing_final2.txt" "$F/journals_main3.json" > "$F/journals_main3.log" 2>&1 &
cap "$PY" "$F/dump_journals.py" "$F/final2" "$F/differing_final2.txt" "$F/journals_final2.json" > "$F/journals_final2.log" 2>&1 &
wait
"$PY" "$F/first_diff.py" "$F/journals_main3.json" "$F/journals_final2.json" > "$F/first_diff_final2.txt" 2>&1
"$PY" "$F/tally_extra.py" "$F/journals_main3.json" "$F/journals_final2.json" > "$F/tally_final2.txt" 2>&1
cap "$PY" "$R/tree_dump.py" "$F/main3" "$F/trees_main3.json" > "$F/trees_main3.log" 2>&1 &
cap "$PY" "$R/tree_dump.py" "$F/final2" "$F/trees_final2.json" > "$F/trees_final2.log" 2>&1 &
wait
"$PY" "$R/tree_diff.py" "$F/trees_main3.json" "$F/trees_final2.json" > "$F/tree_diff_final2.txt" 2>&1
echo done
