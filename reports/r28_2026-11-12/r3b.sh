#!/bin/bash
# R3b (KNOWLEDGE/2026-11-12/199 §6): r28 at update 75 against r27 at update 165, head to head,
# 1,000 deals 930,000-930,999, both seats, greedy, coherent, the verified pool, from r28's worktree
# (44a62d9), as window 2's G4 runs were played. r28 must be paused first (one job on the GPU).
set -euo pipefail
systemctl --user is-active -q mtg-r28 && { echo "pause r28 first: systemctl --user stop mtg-r28"; exit 1; }
R=/home/sune/Desktop/MTG_AI/runs
cd /home/sune/Desktop/MTG_AI-r28
export PYTHONDONTWRITEBYTECODE=1 PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
exec .venv/bin/python -m tools.selfplay.learner --run "$R/r28_looks/r3b" --init "$R/r28_looks/r28_u75.pt" \
  --pool verified --coherent-share 1.0 --infer-bf16 --workers 18 --slots 16 --groups 4 --eval-only \
  --eval-seat eval --eval-opponents snap:opp --opp-ckpt "$R/window2/r27_latest.pt" --eval-set M21 \
  --eval-deals 1000 --eval-seed0 930000
