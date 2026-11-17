#!/bin/bash
# r29, the A/B of --p-self (KNOWLEDGE/2026-11-14/208), from the worktree pinned at its launch commit:
# 1. r28 stops at its next save and ends there (199 §9);
# 2. arm A (--p-self 0), then arm B (--p-self 0.55), each from r28's save at 685. Both arms'
#    pre-flight runs first, before r28 stops. Each arm runs BUDGET machine-seconds (while its unit
#    is active; a restart's wait is not counted), then stops at its first save after that, kept
#    as $O/<arm>.pt;
# 3. the reads: B1 (B against A) and B2's two runs (each against the init on the same deals);
# 4. B resumes as the main run.
# A finished step (its .done file) is skipped on a restart; an arm that ends early (its guard, a
# crash past its restarts) is logged and the queue goes on (208 §3).
#   systemd-run --user --unit mtg-r29 /bin/bash /home/sune/Desktop/MTG_AI-r29/reports/r29_2026-11-14/queue.sh
# A CPU smoke overrides W, R, O, INIT, BUDGET, PAUSE=0 (r28 untouched), GAMES, DEALS and start.sh's knobs.
set -u
W=${W:-/home/sune/Desktop/MTG_AI-r29}
M=/home/sune/Desktop/MTG_AI
R=${R:-$M/runs/selfplay}
O=${O:-$M/runs/r29_ab}
INIT=${INIT:-$M/runs/r28_looks/r28_u685.pt}
BUDGET=${BUDGET:-19800}  # 5.5 machine-hours per arm
PAUSE=${PAUSE:-1}
PY=$M/.venv/bin/python
export W R INIT
export PYTHONDONTWRITEBYTECODE=1 PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
mkdir -p "$O"
cd "$W" || exit 1
exec 9> "$O/lock"
flock -n 9 || { echo "another queue holds $O" >&2; exit 1; }
say() { echo "$(date -Is) $*" >> "$O/queue.log"; }
saved() { $PY -c "import pickle; print(pickle.load(open('$1/state.pkl', 'rb'))['it'])" 2>/dev/null || echo -1; }
mtime() { stat -c %Y "$1/state.pkl" 2>/dev/null || echo 0; }
next_save() {  # wait for the run's next save while its unit is active
  local m0; m0=$(mtime "$1")
  while [ "$(mtime "$1")" = "$m0" ] && systemctl --user is-active -q "$2"; do sleep 10; done
  sleep 10  # the save finishes writing
}

# both arms' pre-flight first, on the CPU, while r28 still trains (208 §4)
for a in a b; do
  case $a in a) run=$R/r29a_pself0 ;; b) run=$R/r29b_pself055 ;; esac
  [ -f "$run/preregistration.json" ] || { say "arm $a: no preregistration.json in $run: stopped"; exit 1; }
  if [ ! -f "$run/preflight.json" ]; then
    CUDA_VISIBLE_DEVICES= $PY -m tools.selfplay.preflight "$run" --games "${GAMES:-200}" > "$O/preflight_$a.out" 2>&1 \
      || { say "arm $a: pre-flight failed (preflight_$a.out): stopped"; exit 1; }
    say "arm $a: pre-flight passed"
  fi
done

if [ "$PAUSE" = 1 ] && systemctl --user is-active -q mtg-r28; then
  next_save "$R/r28_stratified_ppo" mtg-r28
  systemctl --user stop mtg-r28 mtg-r28-guard
  say "r28 stopped after its save at $(saved "$R/r28_stratified_ppo"): it ends here (199 §9)"
fi

arm() {  # arm a|b
  local a=$1 p run unit secs state
  case $a in a) p=0 ;; b) p=0.55 ;; esac
  run=$R/r29${a}_pself${p/./}; unit=mtg-r29$a
  [ -f "$O/arm_$a.done" ] && return 0
  "$W/reports/r29_2026-11-14/start.sh" "$a" >> "$O/queue.log" 2>&1
  say "arm $a running (--p-self $p) from $(git -C "$W" rev-parse --short HEAD)"
  secs=$(cat "$O/arm_$a.secs" 2>/dev/null || echo 0)
  while [ "$secs" -lt "$BUDGET" ]; do
    sleep 30
    state=$(systemctl --user is-active "$unit")
    case $state in
      active) secs=$((secs + 30)); echo "$secs" > "$O/arm_$a.secs" ;;
      activating) ;;  # waiting to restart
      *) say "arm $a ended early: $unit is $state after $secs machine-seconds (see $run/guard.log)"; break ;;
    esac
  done
  [ "$(systemctl --user is-active "$unit")" = active ] && next_save "$run" "$unit"
  systemctl --user stop "$unit" "$unit-guard" 2>/dev/null
  cp "$run/last.pt" "$O/$a.pt"
  say "arm $a stopped after its save at $(saved "$run"), $secs machine-seconds; kept as $a.pt $(sha256sum "$O/$a.pt" | cut -c1-16)"
  touch "$O/arm_$a.done"
}
arm a
arm b

# the reads (208 §2), fresh deals, both seats, greedy, the verified pool
step() {  # step NAME COMMAND...
  local name=$1; shift
  [ -f "$O/$name.done" ] && return 0
  say "$name start"
  timeout 45m "$@" > "$O/$name.out" 2>&1
  local rc=$?
  [ $rc -eq 0 ] && touch "$O/$name.done"
  say "$name exit $rc"
}
L="$PY -m tools.selfplay.learner"
EVAL="--refresh-table --extend-sets M20 --pool verified --coherent-share 1.0 --infer-bf16
  --workers ${WORKERS:-18} --slots ${SLOTS:-16} --groups 4 --eval-only --eval-seat eval
  --eval-opponents snap:opp --eval-set M21 --eval-deals ${DEALS:-1000}"
step b1 $L --run "$O/b1_b_vs_a" --init "$O/b.pt" $EVAL --opp-ckpt "$O/a.pt" --eval-seed0 950000
step b2_a $L --run "$O/b2_a_vs_init" --init "$O/a.pt" $EVAL --opp-ckpt "$INIT" --eval-seed0 951000
step b2_b $L --run "$O/b2_b_vs_init" --init "$O/b.pt" $EVAL --opp-ckpt "$INIT" --eval-seed0 951000

[ "$PAUSE" = 1 ] && "$W/reports/r29_2026-11-14/start.sh" b >> "$O/queue.log" 2>&1 && say "B resumed as the main run"
say "queue done"
