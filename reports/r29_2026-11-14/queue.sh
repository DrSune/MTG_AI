#!/bin/bash
# r29's unattended queue (KNOWLEDGE/2026-11-14/208 §4), from the worktree pinned at its launch commit:
# 1. both arms' pre-flight, on the CPU, while r28 still trains;
# 2. r28 stops at its next save, with its guard, and ends there (199 §9);
# 3. arm A (--p-self 0, --iters 120), then arm B (--p-self 0.55), each from r28's v2 (start.sh)
#    for BUDGET machine-seconds, counted from the arm's own iter rows (208 §1). The first save
#    past 70, 80, 90 and 100% of it is kept as $O/<arm><pct>.pt, and the arm stops with its guard
#    right after its 100% one. An arm with no new iter row for 30 minutes while its unit is
#    active, restarted more than twice, or stopped (its guard) ends there with the snapshots it
#    has, and the queue goes on (208 §3);
# 4. the reads (208 §2): B1, b<k> against a<k>; B2, the init and every snapshot rated on L;
# 5. decide.py applies 208 §5, and the arm it names goes on as the main run.
# Before each arm and each read it waits while another learner runs, and after an hour stops
# without starting anything (208 §6 row 15). load.log takes the machine's load every 5 minutes.
# A finished step is skipped on a restart, and a restarted queue picks an unfinished arm up where
# its iter rows are.
#   systemd-run --user --unit mtg-r29 /bin/bash /home/sune/Desktop/MTG_AI-r29/reports/r29_2026-11-14/queue.sh
# A CPU smoke overrides W, R, O, INIT, BUDGET, GAMES, DEALS, R28_UNIT, R28_RUN and UNIT_PREFIX, the
# learners it waits for (LEARNERS, a pgrep -f pattern, so that a real run beside it does not count),
# STALL (the 30 minutes) and start.sh's knobs. PAUSE=0 leaves r28 alone and resumes nothing.
set -u
M=/home/sune/Desktop/MTG_AI
W=${W:-$M-r29}
R=${R:-$M/runs/selfplay}
O=${O:-$M/runs/r29_ab}
INIT=${INIT:-$M/runs/r28_looks/r28_v2.pt}
BUDGET=${BUDGET:-19800}  # 5.5 machine-hours per arm
PAUSE=${PAUSE:-1}
R28_UNIT=${R28_UNIT:-mtg-r28}
R28_RUN=${R28_RUN:-$R/r28_stratified_ppo}
UNIT_PREFIX=${UNIT_PREFIX:-mtg-r29}
LEARNERS=${LEARNERS:-tools[.]selfplay[.]learner}
STALL=${STALL:-1800}
PY=$W/.venv/bin/python
R27V1=$M/runs/selfplay/r27_priority_ppo/v1.pt  # L's members, by the paths pool_L.json names them
U1000=$M/runs/selfplay/r26_outcome_ppo/u1000.pt
export W R INIT UNIT_PREFIX
export PYTHONDONTWRITEBYTECODE=1 PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
mkdir -p "$O"
cd "$W" || exit 1
exec 9> "$O/lock"
flock -n 9 || { echo "another queue holds $O" >&2; exit 1; }
say() { echo "$(date -Is) $*" >> "$O/queue.log"; }
[ -x "$PY" ] || { say "$PY is not executable: nothing done"; exit 1; }
say "queue start at $(git rev-parse --short HEAD); BUDGET $BUDGET, PAUSE $PAUSE"

# the machine's load every 5 minutes: the arms share it one after the other (208 §5's confounds)
while :; do
  { date -Is; cat /proc/loadavg; ps -eo pid,pcpu,rss,comm --sort=-pcpu | head -6; } >> "$O/load.log"
  sleep 300
done 9>&- &  # without the lock: a loop left behind must not hold the queue's directory
loadpid=$!
trap 'kill $loadpid $(pgrep -P $loadpid) 2>/dev/null' EXIT  # the loop and its sleep

rundir() { case $1 in a) echo "$R/r29a_pself0" ;; b) echo "$R/r29b_pself055" ;; esac; }  # as start.sh
saved() {  # the run's saved update; -1 before its first save
  "$PY" -c "import pickle, sys; print(pickle.load(open(sys.argv[1], 'rb'))['it'])" "$1/state.pkl" \
    2>/dev/null || echo -1
}
mtime() { stat -c %Y "$1/state.pkl" 2>/dev/null || echo 0; }
next_save() {  # wait for the run's next save while its unit is active
  local m0; m0=$(mtime "$1")
  while [ "$(mtime "$1")" = "$m0" ] && systemctl --user is-active -q "$2"; do sleep 10; done
  sleep 10  # the save finishes writing
}
alone() {  # alone WHAT: wait while another learner runs, logging every 10 minutes; after an hour, stop
  local i
  for i in $(seq 0 360); do
    pgrep -f "$LEARNERS" > /dev/null || return 0
    [ "$i" = 360 ] && break
    [ $((i % 60)) = 0 ] && say "$1 waits: another learner runs: $(pgrep -af "$LEARNERS" | cut -c1-160 | paste -sd ';')"
    sleep 10
  done
  say "$1: another learner still runs after an hour: nothing started, the queue stops"
  exit 1
}
start_arm() {  # start_arm ARM ITERS: start.sh, once no other learner runs (unless the arm already does)
  systemctl --user is-active -q "$UNIT_PREFIX$1" || alone "arm $1"
  ITERS=$2 "$W/reports/r29_2026-11-14/start.sh" "$1" >> "$O/queue.log" 2>&1
}

# both arms' pre-flight first, on the CPU, while r28 still trains (208 §4)
for a in a b; do
  run=$(rundir $a)
  [ -f "$O/preflight_$a.done" ] && continue
  [ -f "$run/preregistration.json" ] || { say "arm $a: no preregistration.json in $run: stopped"; exit 1; }
  CUDA_VISIBLE_DEVICES= "$PY" -m tools.selfplay.preflight "$run" --games "${GAMES:-200}" > "$O/preflight_$a.out" 2>&1 \
    || { say "arm $a: pre-flight failed ($O/preflight_$a.out): stopped"; exit 1; }
  touch "$O/preflight_$a.done"
  say "arm $a: pre-flight passed"
done

# r28 ends at its next save (or now, while it waits to restart)
if [ "$PAUSE" = 1 ] && [ "$(systemctl --user is-active "$R28_UNIT")" != inactive ]; then
  systemctl --user is-active -q "$R28_UNIT" && next_save "$R28_RUN" "$R28_UNIT"
  systemctl --user stop "$R28_UNIT" "$R28_UNIT-guard"
  say "r28 stopped after its save at $(saved "$R28_RUN"): it ends here (199 §9)"
fi

# an arm's machine time (208 §1): from its unit's start (T0) to its first iter row, plus each
# interval between consecutive iter rows under 1,200 s. Prints the machine-seconds, the last
# row's time, then for 70, 80, 90 and 100% of BUDGET the update whose row passed it (- not yet).
machine() {  # machine RUN T0 (T0 empty: no start-up term)
  grep -h '"event": "iter"' "$1/metrics.jsonl" 2>/dev/null \
    | sed -nE 's/^\{"t": ([0-9.]+), "event": "iter", "it": ([0-9]+)[,}].*/\1 \2/p' \
    | awk -v t0="$2" -v b="$BUDGET" '
        NR == 1 { m = t0 == "" ? 0 : $1 - t0 }
        NR > 1 && $1 - p < 1200 { m += $1 - p }
        { p = $1; for (k = 7; k <= 10; k++) if (!(k in at) && m >= b * k / 10) at[k] = $2 }
        END { printf "%d %d", m, p; for (k = 7; k <= 10; k++) printf " %s", (k in at) ? at[k] : "-"; print "" }'
}
end_arm() {  # end_arm ARM WHY MACHINE-SECONDS: the arm stops with its guard, keeping its snapshots
  systemctl --user stop "$UNIT_PREFIX$1" "$UNIT_PREFIX$1-guard"
  echo "$2" > "$O/arm_$1.done"
  say "arm $1 ended ($2) after $3 machine-seconds, its last save at $(saved "$(rundir "$1")"); kept: $(cd "$O" && ls "$1"[0-9]*.pt 2>/dev/null | paste -sd ' ')"
}
arm() {  # arm a|b ITERS
  local a=$1 run unit started x pct k s state n ref
  run=$(rundir "$a"); unit=$UNIT_PREFIX$a
  [ -f "$O/arm_$a.done" ] && return 0
  # T0: machine time counts from the start of the unit whose learner writes the first iter row
  systemctl --user is-active -q "$unit" || grep -qs '"event": "iter"' "$run/metrics.jsonl" \
    || date +%s > "$O/arm_$a.t0"
  start_arm "$a" "$2" || { say "arm $a: start.sh refused (above): the queue stops"; exit 1; }
  started=$(date +%s)
  say "arm $a running as $unit (--iters $2) from $(git rev-parse --short HEAD)"
  while :; do
    sleep 15
    read -ra x <<< "$(machine "$run" "$(cat "$O/arm_$a.t0" 2>/dev/null)")"
    s=$(saved "$run")
    k=2
    for pct in 70 80 90 100; do  # the first save at or after the row that passed the mark
      if [ ! -f "$O/$a$pct.pt" ] && [ "${x[k]}" != - ] && [ "$s" -ge "${x[k]}" ]; then
        cp "$run/last.pt" "$O/$a$pct.tmp" && mv "$O/$a$pct.tmp" "$O/$a$pct.pt"
        say "arm $a: $a$pct.pt kept, update $s, sha256 $(sha256sum "$O/$a$pct.pt" | cut -c1-16), at ${x[0]} machine-seconds"
      fi
      k=$((k + 1))
    done
    [ -f "$O/${a}100.pt" ] && { end_arm "$a" budget "${x[0]}"; return; }
    # the progress check (208 §3)
    state=$(systemctl --user is-active "$unit")
    case $state in
      inactive|failed)
        if [ -s "$run/guard.log" ]; then
          say "arm $a: $unit is $state, stopped by its guard: $(tail -1 "$run/guard.log")"
          end_arm "$a" guard "${x[0]}"
        else
          say "arm $a: $unit is $state, with no guard.log"
          end_arm "$a" inactive "${x[0]}"
        fi
        return ;;
    esac
    n=$(systemctl --user show -p NRestarts --value "$unit")
    if [ "${n:-0}" -gt 2 ]; then
      say "arm $a: $unit restarted $n times"
      end_arm "$a" restarts "${x[0]}"; return
    fi
    ref=$(( x[1] > started ? x[1] : started ))  # the last iter row, or this queue's start of the arm
    if [ "$state" = active ] && [ $(( $(date +%s) - ref )) -gt "$STALL" ]; then
      say "arm $a: no new iter row for $STALL s while $unit is active (since $(date -d "@$ref" -Is))"
      end_arm "$a" stall "${x[0]}"; return
    fi
  done
}
arm a 120
arm b 6000

# the reads (208 §2): fresh deals, both seats, greedy, coherent decks, the verified pool, M21
step() {  # step NAME COMMAND...: one evaluation; a finished one (its .done file) is skipped
  local name=$1 rc; shift
  [ -f "$O/$name.done" ] && return 0
  alone "$name"
  say "$name start"
  timeout -k 5m 45m "$@" > "$O/$name.out" 2>&1
  rc=$?
  [ $rc -eq 0 ] && touch "$O/$name.done"
  say "$name exit $rc"
}
L="$PY -m tools.selfplay.learner"
EVAL="--refresh-table --extend-sets M20 --pool verified --coherent-share 1.0 --infer-bf16
  --workers ${WORKERS:-18} --slots ${SLOTS:-16} --groups 4 --eval-only --eval-seat eval
  --eval-opponents snap:opp --eval-set M21 --eval-deals ${DEALS:-1000}"
# B1: b<k> against a<k>, each pair on its own 1,000 deals from 952,000
seed=952000
for k in 70 80 90 100; do
  if [ -f "$O/a$k.pt" ] && [ -f "$O/b$k.pt" ]; then
    step "b1_$k" $L --run "$O/b1_$k" --init "$O/b$k.pt" $EVAL --opp-ckpt "$O/a$k.pt" --eval-seed0 $seed
  else
    say "b1_$k skipped: a$k.pt or b$k.pt is missing"
  fi
  seed=$((seed + 1000))
done
# B2 on L: every player against r27's v1 (deals from 1,130,000) and u1000 (1,131,000), the same
# deals for each; rate.py then rates it against L's frozen ratings
for p in init a70 a80 a90 a100 b70 b80 b90 b100; do
  ckpt=$O/$p.pt; [ "$p" = init ] && ckpt=$INIT
  [ -f "$ckpt" ] || { say "b2 $p skipped: no $ckpt"; continue; }
  step "b2_${p}_r27v1" $L --run "$O/b2_${p}_r27v1" --init "$ckpt" $EVAL --opp-ckpt "$R27V1" --eval-seed0 1130000
  step "b2_${p}_u1000" $L --run "$O/b2_${p}_u1000" --init "$ckpt" $EVAL --opp-ckpt "$U1000" --eval-seed0 1131000
  if [ ! -f "$O/rate_$p.json" ] && [ -f "$O/b2_${p}_r27v1.done" ] && [ -f "$O/b2_${p}_u1000.done" ]; then
    "$PY" -m tools.selfplay.rate rate reports/ceiling_window/pool_L.json "$O/b2_${p}_r27v1" \
      "$O/b2_${p}_u1000" > "$O/rate_$p.tmp" 2> "$O/rate_$p.err" && mv "$O/rate_$p.tmp" "$O/rate_$p.json"
    say "rate $p: $(cat "$O/rate_$p.json" 2>/dev/null || cat "$O/rate_$p.err")"
  fi
done

# 208 §5, applied by decide.py (a decision left by an earlier run of the queue never counts)
rm -f "$O/decision.json"
say "$("$PY" reports/r29_2026-11-14/decide.py "$O" 2>&1)"
choice=$(sed -nE 's/^ "resume": "([ab])",$/\1/p' "$O/decision.json" 2>/dev/null)
# The decision starts the main run once: a later run of the queue must not restart a main run its
# guard has since stopped. After a reboot, start.sh resumes it by hand, as r28's did.
if [ -f "$O/resume.done" ]; then
  say "the main run was started at $(cat "$O/resume.done"): not again (start.sh $choice resumes it by hand)"
elif [ "$PAUSE" = 1 ] && [ -n "$choice" ]; then
  if start_arm "$choice" 6000; then
    date -Is > "$O/resume.done"
    say "arm $choice goes on as the main run (--iters 6000): $(sed -nE 's/^ "why": "(.*)",$/\1/p' "$O/decision.json")"
  else
    say "arm $choice: start.sh refused (above): nothing resumed"
  fi
fi
say "queue done"
