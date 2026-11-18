#!/bin/bash
# lki-off against the new last-known-information test, on the scratch copy.
W=/home/sune/Desktop/MTG_AI/.claude/worktrees/agent-a875029fa86089517
M=/tmp/claude-1000/-home-sune/53a867d9-979e-400a-9ce1-caf029cc7b16/scratchpad/b3/mutcopy
export CUDA_VISIBLE_DEVICES= OMP_NUM_THREADS=2 TORCH_DISABLE_NATIVE_JIT=1
cp "$W/MTG_bot/core/test_executor_copies.py" "$M/MTG_bot/core/"
cp "$M/MTG_bot/core/executor/copies.py" "$M/copies.py.orig"
sed -i 's/    if lki is not None and lki.identity is not None and (state is None or (on_battlefield and not here)):/    if False:/' "$M/MTG_bot/core/executor/copies.py"
/usr/bin/grep -c 'if False:' "$M/MTG_bot/core/executor/copies.py"
(cd "$M" && nice -n 19 "$W/.venv/bin/python" -m pytest -q --no-header -p no:cacheprovider MTG_bot/core/test_executor_copies.py 2>&1 | tail -2)
cp "$M/copies.py.orig" "$M/MTG_bot/core/executor/copies.py"
