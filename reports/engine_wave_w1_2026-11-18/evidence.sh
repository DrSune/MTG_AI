#!/bin/bash
# evidence.sh: engine wave W1's registered evidence (KNOWLEDGE/2026-11-18/215 §8 c, d, e, f), CPU
# only, niced, each process under an 8G cap, at most four at a time (a training run holds the GPU).
#   BASE:   the W0 follow-up commit e6ac05c8, exported with `git archive` (the engine before W1)
#   BRANCH: the W1 commit, exported the same way (a fixed snapshot, not the live worktree)
# (c, d, f) tools/audit/blast_radius.py run: the 19 sets' trees on both sides, 200 seeded heuristic
#     replays per verified pool on each, compared, the first differing journal row of each
#     differing game, and games per CPU-second.
# (e) the soak with W0's detectors, 300 verified games per pool (seeds 1-300), on the branch;
#     W0's baseline is reports/engine_wave_w0_2026-11-18/soak_*.json.
S=${S:-/tmp/claude-1000/-home-sune/53a867d9-979e-400a-9ce1-caf029cc7b16/scratchpad}
BASE=$S/base
BRANCH=$S/branch
OUT=$S/w1_evidence
PY=/home/sune/Desktop/MTG_AI/.venv/bin/python
export CUDA_VISIBLE_DEVICES=
export OMP_NUM_THREADS=2
cap() { systemd-run --user --scope -q -p MemoryMax=8G -p MemorySwapMax=0 nice -n 19 "$@"; }
mkdir -p "$OUT"
( cd "$BRANCH" && cap $PY tools/audit/blast_radius.py run --base "$BASE" --branch "$BRANCH" \
    --out "$OUT/blast" --games 200 > "$OUT/blast.log" 2>&1 ) &
( cd "$BRANCH" && for code in M21 M20 FDN; do
    cap $PY tools/cards/soak.py $code --games 300 --mode verified --workers 2 \
      --out "$OUT/soak_$code.json" > "$OUT/soak_$code.log" 2>&1
  done ) &
wait
echo done
