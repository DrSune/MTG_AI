#!/bin/bash
# E0: train both arms (KNOWLEDGE 186 §1-2: lr 1e-3, 4 epochs; identical except --window), from the pinned run worktree.
set -e
RUN=/home/sune/Desktop/MTG_AI/runs/simulator
cd /home/sune/Desktop/MTG_AI-sim-run
git checkout -q --detach "$1"
git status --porcelain | head -3
git rev-parse --short HEAD
for arm in nowin win; do
  flag=""; [ "$arm" = win ] && flag="--window"
  nohup nice -n 10 /home/sune/Desktop/MTG_AI/.venv/bin/python -m tools.selfplay.simulator train \
    --data $RUN/e0_capture/capture --out $RUN/e0_sim_$arm.pt --lr 1e-3 --epochs 4 $flag \
    > $RUN/e0_sim_$arm.out 2>&1 &
  echo "$arm $!"
done
