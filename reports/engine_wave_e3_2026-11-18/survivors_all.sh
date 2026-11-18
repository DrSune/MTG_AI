#!/bin/bash
# survivors_all.sh <worktree> <out.txt>: G3's uncovered critical survivors of the item-8 cards (and
# wave 5's Radha and Mystic Forge with their verdicts), CPU-only and niced.
W=$1
OUT=$2
S=/tmp/claude-1000/-home-sune/53a867d9-979e-400a-9ce1-caf029cc7b16/scratchpad/e3
export CUDA_VISIBLE_DEVICES=
export OMP_NUM_THREADS=2
cd "$W" || exit 1
PY=/home/sune/Desktop/MTG_AI/.venv/bin/python
{
  echo "== Radha, Heart of Keld (A06)"
  nice -n 19 $PY tools/cards/cardtool.py survivors M21 "Radha, Heart of Keld" --verdict $S/wave5/verdicts/A/A06.json
  echo "== Mystic Forge (A07)"
  nice -n 19 $PY tools/cards/cardtool.py survivors M20 "Mystic Forge" --verdict $S/wave5/verdicts/A/A07.json
  echo "== Mangara, the Diplomat"
  nice -n 19 $PY $S/survivors.py "$W" M21 "Mangara, the Diplomat" tools/scenarios/mangara_*.json
  echo "== Watcher of the Spheres"
  nice -n 19 $PY $S/survivors.py "$W" M21 "Watcher of the Spheres" tools/scenarios/cards/M21/watcher_of_the_spheres_*.json
  echo "== Watcher of the Spheres, with the pack of two fliers at once"
  nice -n 19 $PY $S/survivors.py "$W" M21 "Watcher of the Spheres" tools/scenarios/cards/M21/watcher_of_the_spheres_*.json tools/scenarios/watcher_of_the_spheres_two_fliers_entering_at_once.json
} 2>&1 | grep -v "shape-gap" > "$OUT"
echo done
