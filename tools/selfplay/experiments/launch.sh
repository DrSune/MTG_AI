#!/bin/bash
# launch.sh NAME K D GREEDY SEED0 FP_BUDGET WORKERS [LOOKS]  (from the pinned run worktree)
# A label job of the generator plus, when LOOKS is given, E1's look watcher on it.
set -e
NAME=$1; K=$2; D=$3; G=$4; SEED0=$5; FP=$6; W=$7; LOOKS=$8
S=$(cd "$(dirname "$0")" && pwd)
R=/home/sune/Desktop/MTG_AI/runs/labels/$NAME
GEN=/home/sune/Desktop/MTG_AI/runs/selfplay/r23_mulligan/gen.pt
cd /home/sune/Desktop/MTG_AI-labels-run
export PYTHONPATH=/home/sune/Desktop/MTG_AI-labels-run
nohup nice -n 10 /home/sune/Desktop/MTG_AI/.venv/bin/python $S/label_run.py --run $R --init $GEN \
  --refresh-table --extend-sets M20 --mix-sets M20 --mix-share 0.25 --pool verified --infer-bf16 \
  --workers $W --slots 32 --groups 2 --bucket-ratio 100 --serve-wait 5 --mem-floor-gib 15 \
  --progress-every 120 --label-k $K --label-d $D --label-greedy $G --label-fp $FP --seed0 $SEED0 \
  > $R.out 2>&1 &
if [ -n "$LOOKS" ]; then
  sleep 2
  nohup nice -n 10 /home/sune/Desktop/MTG_AI/.venv/bin/python $S/e1_looks.py $GEN $R $LOOKS > $R.looks 2>&1 &
fi
echo "launched $NAME at $(git -C /home/sune/Desktop/MTG_AI-labels-run rev-parse --short HEAD)"
