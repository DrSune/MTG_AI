#!/bin/bash
# After window 1 (KNOWLEDGE/2026-11-11/192 §6): the clock's latency (PLAN_CEILING §3.3), one game
# at a time on the otherwise idle machine, at n = 16, 4 and 64; then r27 starts, whatever the
# points did. Waits for the unit mtg-window1 to end. Each point has a time cap; a finished point
# (its .done file) is skipped on a rerun.
#   systemd-run --user --unit mtg-clock1 /bin/bash \
#     /home/sune/Desktop/MTG_AI/reports/window1_2026-11-11/clock.sh
set -u
W=/home/sune/Desktop/MTG_AI-w1
R=/home/sune/Desktop/MTG_AI/runs
O=$R/window1
NET=$R/selfplay/r26_outcome_ppo/u1000.pt
log() { echo "{\"t\": $(date +%s), \"step\": \"$1\", \"what\": \"$2\"}" >> "$O/clock.log"; }
while systemctl --user is-active -q mtg-window1; do sleep 30; done
cd "$W" || exit 1
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
clock() {  # clock NAME N DEALS CAP
  local name=$1 n=$2 deals=$3 cap=$4
  [ -f "$O/$name.done" ] && return 0
  log "$name" start
  timeout "$cap" .venv/bin/python -m tools.selfplay.learner --run "$O/$name" --init "$NET" \
    --refresh-table --extend-sets M20 --pool verified --coherent-share 1.0 --infer-bf16 \
    --workers 1 --slots 1 --groups 1 --eval-only --eval-seat eval+search \
    --eval-opponents snap:opp --opp-ckpt "$NET" --eval-set M21 --search-root gumbel \
    --search-m 16 --search-n "$n" --eval-deals "$deals" > "$O/$name.out" 2>&1
  local rc=$?
  [ $rc -eq 0 ] && touch "$O/$name.done"
  log "$name" "exit $rc"
}
clock clock_n16 16 10 40m
clock clock_n4 4 5 20m
clock clock_n64 64 5 45m
systemctl --user start mtg-r27
log r27 "start: $(systemctl --user is-active mtg-r27)"
