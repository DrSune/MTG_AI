#!/bin/bash
# r28's read at update 400, made late (KNOWLEDGE/2026-11-12/199 §8), and the GPU window gate B
# leaves (196 §10: generation does not run; H1' and 195's confirming audit take this window).
# - r28 pauses at its first save 10, 15 or 20 updates past a gate (as gate B's queue); that save
#   is kept as runs/r28_looks/r28_u<it>.pt.
# - The per-kind split's batch is collected on it (seed 2840) and split with r28's pinned code:
#   main's features.py and model.py have moved since 44a62d9.
# - H1' (bf16, then fp32) and 195's confirming audit run with gate B's queue's own commands, from
#   its worktree at 8aabbc8, into runs/read400/.
# - Every step has a cap; a failed step is logged and the window goes on; r28 resumes however
#   the window ends.
#   systemd-run --user --unit mtg-read400 /bin/bash \
#     /home/sune/Desktop/MTG_AI/reports/r28_2026-11-12/at400.sh
set -u
M=/home/sune/Desktop/MTG_AI
R=$M/runs
RUN=$R/selfplay/r28_stratified_ppo
LOOKS=$R/r28_looks
O=$R/read400
GW=/home/sune/Desktop/MTG_AI-gateb
RW=/home/sune/Desktop/MTG_AI-r28
PY=$M/.venv/bin/python
U1000=$R/selfplay/r26_outcome_ppo/u1000.pt
mkdir -p "$LOOKS" "$O"
export PYTHONDONTWRITEBYTECODE=1 PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
say() { echo "$(date -Is) $*" >> "$O/window.log"; }
step() {  # step NAME CAP DIR COMMAND... ; a finished step (its .done file) is skipped
  local name=$1 cap=$2 dir=$3; shift 3
  [ -f "$O/$name.done" ] && return 0
  say "$name start"
  (cd "$dir" && timeout "$cap" "$@") > "$O/$name.out" 2>&1
  local rc=$?
  [ $rc -eq 0 ] && touch "$O/$name.done"
  say "$name exit $rc"
}
it() {  # the saved update; -1 while the save is still being written
  $PY -c "import pickle; print(pickle.load(open('$RUN/state.pkl', 'rb'))['it'])" 2>/dev/null || echo -1
}

[ "$(git -C "$GW" rev-parse HEAD)" = 8aabbc898be183655b141bf47db3761434b59ed8 ] \
  || { say "gate B's worktree is not at 8aabbc8: nothing done"; exit 1; }
say "waiting for a save 10-20 updates past a gate"
last=$(stat -c %Y "$RUN/state.pkl")
while true; do
  systemctl --user is-active -q mtg-r28 || { say "r28 is not running: nothing done"; exit 1; }
  now=$(stat -c %Y "$RUN/state.pkl")
  if [ "$now" != "$last" ]; then
    last=$now
    case $(( $(it) % 25 )) in 10|15|20) break ;; esac
  fi
  sleep 15
done
sleep 10  # the save finishes writing
systemctl --user stop mtg-r28
trap '"$M/reports/r28_2026-11-12/start.sh" >> "$O/window.log" 2>&1; say "r28 resumed"' EXIT
n=$(it)
cp "$RUN/last.pt" "$LOOKS/r28_u$n.pt"
say "r28 paused after its save at $n; kept as r28_u$n.pt $(sha256sum "$LOOKS/r28_u$n.pt" | cut -c1-16)"

# the per-kind split (199 §7-§8)
step "collect$n" 45m "$M" "$M/reports/r28_2026-11-12/collect.sh" "$LOOKS/r28_u$n.pt" \
  "$LOOKS/c$n" 2840
[ -f "$O/collect$n.done" ] && step "split$n" 30m "$RW" env PYTHONPATH=. "$PY" \
  "$M/reports/r28_2026-11-12/kinds_split.py" "$LOOKS/r28_u$n.pt" "$LOOKS/c$n/batch.pkl"

# 192 §7.6's H1' and 195 §5's confirming audit, as gate B's queue would have run them
L="$PY -m tools.selfplay.learner"
H1="--init $U1000 --refresh-table --extend-sets M20 --pool verified --coherent-share 1.0
  --workers 18 --slots 16 --groups 4 --eval-only --eval-seat eval --eval-opponents heuristic
  --eval-set M21 --eval-deals 300 --eval-seed0 900000"
step h1_bf16 20m "$GW" $L --run "$O/h1_bf16" $H1 --infer-bf16
step h1_fp32 40m "$GW" $L --run "$O/h1_fp32" $H1
step audit195 180m "$GW" $L --run "$O/audit195" --init "$U1000" --refresh-table \
  --extend-sets M20 --pool verified --coherent-share 1.0 --infer-bf16 --workers 18 --slots 16 \
  --groups 4 --eval-only --eval-seat eval+search --eval-opponents snap:opp --opp-ckpt "$U1000" \
  --eval-set M21 --search-root gumbel --search-m 16 --search-n 16 --search-audit 8 \
  --search-sim "$R/window1/sim.pt" --eval-deals 100 --eval-seed0 965000
say "window done"
