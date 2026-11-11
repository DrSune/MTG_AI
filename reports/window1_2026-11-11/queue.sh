#!/bin/bash
# Window 1 (KNOWLEDGE/2026-11-11/192): the n-curve, gate A's confirmation, the simulator on the new
# game, and the n = 16 variants. Runs from the pinned worktree; one GPU job at a time; a step that
# finished (its .done file) is skipped on a restart. DEALS sets the n-curve points' deals; PILOT=1
# plays only the pilot (n = 4 and 16, 50 deals each), which times a searched game.
#   systemd-run --user --unit mtg-window1 --setenv=DEALS=300 /bin/bash \
#     /home/sune/Desktop/MTG_AI-w1/reports/window1_2026-11-11/queue.sh
set -u
W=/home/sune/Desktop/MTG_AI-w1
R=/home/sune/Desktop/MTG_AI/runs
O=$R/window1
NET=$R/selfplay/r26_outcome_ppo/u1000.pt
DEALS=${DEALS:-300}
COMMON="--init $NET --refresh-table --extend-sets M20 --pool verified --coherent-share 1.0 --infer-bf16 --workers 18 --slots 16 --groups 4"
EVAL="--eval-only --eval-seat eval+search --eval-opponents snap:opp --opp-ckpt $NET --eval-set M21 --search-root gumbel --search-m 16 --search-record"
cd "$W" || exit 1
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
mkdir -p "$O"
log() { echo "{\"t\": $(date +%s), \"step\": \"$1\", \"what\": \"$2\"}" >> "$O/queue.log"; }
step() {
  local name=$1; shift
  [ -f "$O/$name.done" ] && return 0
  log "$name" start
  "$@" > "$O/$name.out" 2>&1
  local rc=$?
  [ $rc -eq 0 ] && touch "$O/$name.done"
  log "$name" "exit $rc"
}
point() {  # point NAME N DEALS [extra flags...]
  local name=$1 n=$2 deals=$3; shift 3
  step "$name" .venv/bin/python -m tools.selfplay.learner --run "$O/$name" $COMMON $EVAL \
    --search-n "$n" --eval-deals "$deals" "$@"
}
if [ "${PILOT:-0}" = 1 ]; then
  point pilot_n4 4 50
  point pilot_n16 16 50
  log pilot done
  exit 0
fi
point n16 16 "$DEALS"
point n4 4 "$DEALS"
point n64 64 "$DEALS"
point n2 2 "$DEALS"
point n8 8 "$DEALS"
point n32 32 "$DEALS"
point confirm16 16 300 --eval-seed0 950000
step capture .venv/bin/python -m tools.selfplay.learner --run "$O/capture" $COMMON \
  --mix-sets M20 --mix-share 0.25 --capture 40000 --capture-p 0.4 --seed 27
step sim_train .venv/bin/python -m tools.selfplay.simulator train --data "$O/capture/capture" \
  --out "$O/sim.pt"
step sim_eval .venv/bin/python -m tools.selfplay.simulator eval --data "$O/capture/capture" \
  --ckpt "$O/sim.pt" --out "$O/sim_eval.npz"
# N5 only if the simulator beats uniform draws (S1) and is calibrated (S2)
if .venv/bin/python -c "import json,sys; r=json.loads(open('$O/sim_eval.out').read().strip().splitlines()[-1]); sys.exit(0 if r['hand_vs_uniform'] <= 0.90 and r['ece'] < 0.05 else 1)"; then
  point n16_sim 16 "$DEALS" --search-worlds sim --search-sim "$O/sim.pt"
else
  log n16_sim "skipped: S1 or S2 failed"
fi
point n16_priority 16 "$DEALS" --search-kinds act,priority
point n16_topk 16 "$DEALS" --search-root topk --search-k 4 --search-d 4
point n16_h2 16 "$DEALS" --search-horizon 2
step heur_raw .venv/bin/python -m tools.selfplay.learner --run "$O/heur_raw" $COMMON --eval-only \
  --eval-seat eval --eval-opponents heuristic --eval-set M21 --eval-deals "$DEALS"
point heur_n16 16 "$DEALS" --eval-opponents heuristic
log window done
