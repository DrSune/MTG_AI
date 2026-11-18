#!/bin/bash
# The gate fixes' evidence: red tests on the merge before the fixes (498faa66), tree dumps of
# main (13b57121), that merge and the fixed worktree, their diffs, the census, and 300 replays
# of main against the fixed worktree (read-only on the repository).
W=/home/sune/Desktop/MTG_AI/.claude/worktrees/agent-a875029fa86089517
S=/tmp/claude-1000/-home-sune/53a867d9-979e-400a-9ce1-caf029cc7b16/scratchpad/b3
G=$S/gatefix
export CUDA_VISIBLE_DEVICES= OMP_NUM_THREADS=2 TORCH_DISABLE_NATIVE_JIT=1
rm -rf "$G" && mkdir -p "$G/main" "$G/prefix"
cd "$W" || exit 1
git archive 13b57121 MTG_bot tools pyproject.toml | tar -x -C "$G/main"
git archive 498faa66 MTG_bot tools pyproject.toml | tar -x -C "$G/prefix"
ls "$G/main/MTG_bot" "$G/prefix/MTG_bot" > /dev/null || exit 1
# 1. the new tests on the merge before the fixes
cp MTG_bot/core/test_executor_copies.py MTG_bot/core/test_ability_tree_copies.py "$G/prefix/MTG_bot/core/"
cp MTG_bot/core/compiler/test_templates_b20.py "$G/prefix/MTG_bot/core/compiler/"
(cd "$G/prefix" && nice -n 19 "$W/.venv/bin/python" -m pytest -q --no-header -p no:cacheprovider \
  MTG_bot/core/test_executor_copies.py MTG_bot/core/test_ability_tree_copies.py \
  MTG_bot/core/compiler/test_templates_b20.py 2>&1 | /usr/bin/grep -E '^(FAILED|ERROR)|passed|failed' \
  | sed 's/ - .*//') > "$G/red_prefix.txt"
# 2. tree dumps, diffs, census
for side in main prefix; do
  systemd-run --user --scope -q -p MemoryMax=8G -p MemorySwapMax=0 nice -n 19 "$W/.venv/bin/python" \
    reports/copy_2026-11-18/tree_dump.py "$G/$side" "$G/trees_$side.json" > "$G/dump_$side.log" 2>&1
done
systemd-run --user --scope -q -p MemoryMax=8G -p MemorySwapMax=0 nice -n 19 "$W/.venv/bin/python" \
  reports/copy_2026-11-18/tree_dump.py "$W" "$G/trees_final.json" > "$G/dump_final.log" 2>&1
"$W/.venv/bin/python" reports/copy_2026-11-18/tree_diff.py "$G/trees_main.json" "$G/trees_final.json" > "$G/tree_diff_main.txt" 2>&1
"$W/.venv/bin/python" reports/copy_2026-11-18/tree_diff.py "$G/trees_prefix.json" "$G/trees_final.json" > "$G/tree_diff_gate.txt" 2>&1
"$W/.venv/bin/python" reports/copy_2026-11-18/census.py "$G/trees_final.json" > "$G/census.txt" 2>&1
# 3. 300 replays, main against the fixed worktree
cp reports/copy_2026-11-18/replay.py "$G/replay_copy.py"
(cd "$G/main" && systemd-run --user --scope -q -p MemoryMax=8G -p MemorySwapMax=0 nice -n 19 \
  "$W/.venv/bin/python" "$G/replay_copy.py" "$G/main" "$G/trees_main.json" "$G/trees_final.json" 100 \
  "$G/replay_main.json" > "$G/replay_main.log" 2>&1)
systemd-run --user --scope -q -p MemoryMax=8G -p MemorySwapMax=0 nice -n 19 "$W/.venv/bin/python" \
  "$G/replay_copy.py" "$W" "$G/trees_main.json" "$G/trees_final.json" 100 "$G/replay_final.json" \
  > "$G/replay_final.log" 2>&1
"$W/.venv/bin/python" reports/copy_2026-11-18/replay_compare.py "$G/replay_main.json" "$G/replay_final.json" > "$G/replay_compare.txt" 2>&1
cat "$G/red_prefix.txt"; head -3 "$G/tree_diff_gate.txt"; tail -2 "$G/replay_compare.txt"
