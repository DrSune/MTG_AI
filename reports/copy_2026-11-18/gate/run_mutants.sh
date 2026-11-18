#!/bin/bash
# A scratch copy of the worktree (MTG_bot, tools, pyproject), then the mutants against its copy tests.
W=/home/sune/Desktop/MTG_AI/.claude/worktrees/agent-a875029fa86089517
S=/tmp/claude-1000/-home-sune/53a867d9-979e-400a-9ce1-caf029cc7b16/scratchpad/b3
M=$S/mutcopy
export CUDA_VISIBLE_DEVICES= OMP_NUM_THREADS=2 TORCH_DISABLE_NATIVE_JIT=1
rm -rf "$M" && mkdir -p "$M"
cp -r "$W/MTG_bot" "$W/tools" "$W/pyproject.toml" "$M/"
/usr/bin/find "$M" -name __pycache__ -type d -prune -exec rm -rf {} +
nice -n 19 "$W/.venv/bin/python" "$S/mutants.py" "$M" "$W/.venv/bin/python" > "$S/mutants.txt" 2>&1
cat "$S/mutants.txt"
