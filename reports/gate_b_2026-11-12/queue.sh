#!/bin/bash
# Gate B (KNOWLEDGE/2026-11-12/196): r27 pauses right after a save, away from its gates; its
# last.pt is the generator G. Chunks of searched games record targets until 300k exist; chunk 0
# is gate A on G. Then four distillation arms; each arm's epoch is chosen by play on deals
# 970,000+; the tests run on deals 980,000+; GB2's agreement; 192 §7.6's H1' (fp32 and bf16 on
# window 1's heur_raw deals); then r27 resumes. Runs from a worktree pinned at the commit that
# holds this file; one GPU job at a time; every step has a time cap.
#   systemd-run --user --unit mtg-gateb /bin/bash \
#     /home/sune/Desktop/MTG_AI-gateb/reports/gate_b_2026-11-12/queue.sh
#
# Restarts (KNOWLEDGE/2026-11-12/197's fixes):
# - $O/identity holds the commit that began the run; a queue from another commit refuses it.
# - r27 is paused whenever it is running when the queue (re)starts; G is copied once.
# - A_G is its own saved verdict ($O/A_G). An interrupted chunk 0 is set aside unread and played
#   again; no other chunk runs before A_G is read and passes; below AG_MIN the gate stops for good
#   ($O/stopped).
# - A finished step (its .done file) is skipped; a generation chunk once started is never
#   replayed (its .tried file); a required step that fails stops the queue ($O/failed, r27
#   resumed), and a restart tries it again.
# A CPU smoke overrides the sizes and sets PAUSE=0, which neither stops nor starts r27 and takes
# G from GEN_FROM.
set -u
W=${W:-/home/sune/Desktop/MTG_AI-gateb}
R=/home/sune/Desktop/MTG_AI/runs
O=${O:-$R/gateb}
R27=$R/selfplay/r27_priority_ppo
G=$O/gen.pt
V0=$R27/v0.pt
U1000=$R/selfplay/r26_outcome_ppo/u1000.pt
PAUSE=${PAUSE:-1}
TARGETS=${TARGETS:-300000}
SIZES=${SIZES:-100000,300000}
CHUNK=${CHUNK:-1875}
MAX_CHUNKS=${MAX_CHUNKS:-14}
SEL=${SEL:-500}
TEST=${TEST:-1000}
H1_DEALS=${H1_DEALS:-300}
AG_MIN=${AG_MIN:-0.54}
GEN_CAP=${GEN_CAP:-4h}
SEARCH="--search-root gumbel --search-m 16 --search-n ${SEARCH_N:-16}"
# --groups 4 as every run before (a knob named GROUPS would read bash's own GROUPS: 197)
GAME="--pool verified --infer-bf16 --eval-set M21 --workers ${WORKERS:-18} --slots ${SLOTS:-16}
  --groups 4"
cd "$W" || exit 1
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
mkdir -p "$O"
exec 9> "$O/lock"  # one queue per run directory: a second one would replay its steps
flock -n 9 || { echo "another queue holds $O" >&2; exit 1; }
log() { echo "{\"t\": $(date +%s), \"step\": \"$1\", \"what\": \"$2\"}" >> "$O/queue.log"; }
step() {  # step NAME CAP COMMAND... ; returns the command's exit code
  local name=$1 cap=$2; shift 2
  [ -f "$O/$name.done" ] && return 0
  log "$name" start
  timeout "$cap" "$@" > "$O/$name.out" 2>&1
  local rc=$?
  [ $rc -eq 0 ] && touch "$O/$name.done"
  log "$name" "exit $rc"
  return $rc
}
resume() { [ "$PAUSE" = 1 ] && systemctl --user start mtg-r27 && log r27 resumed; return 0; }
fail() {  # a required step failed: stop here, give the GPU back to r27, say so
  echo "$1" > "$O/failed"
  log gateb "failed: $1"
  resume
  exit 1
}
L=".venv/bin/python -m tools.selfplay.learner"
D="env PYTHONPATH=. .venv/bin/python -m tools.selfplay.distill"
score() {  # the evaluated seat's score in an eval-only run's last summary ("" if none)
  .venv/bin/python - "$1/metrics.jsonl" <<'PY'
import json, os, sys
path = sys.argv[1]
rows = [json.loads(x) for x in open(path)] if os.path.exists(path) else []
ev = [r for r in rows if r.get("event") == "eval"]
print(ev[-1]["snap:opp"]["score"] if ev and "snap:opp" in ev[-1] else "")
PY
}

id=$(git -C "$W" rev-parse HEAD 2>/dev/null)
if [ -f "$O/identity" ] && [ "$(cat "$O/identity")" != "$id" ]; then
  log gateb "refused: $O began at $(cat "$O/identity"), this queue is $id"
  exit 1
fi
echo "$id" > "$O/identity"
[ -f "$O/failed" ] && log gateb "restart after: $(cat "$O/failed")" && rm -f "$O/failed"
if [ -f "$O/stopped" ]; then  # gate A on G failed before: a restart must not generate
  log gateb "stopped earlier: $(cat "$O/stopped")"
  resume
  exit 0
fi

# r27 pauses at its first save whose update is 10, 15 or 20 past a gate (as window 2's queue),
# at every (re)start that finds it running: nothing else shares the GPU with a step
if [ "$PAUSE" = 1 ] && systemctl --user is-active -q mtg-r27; then
  it() { .venv/bin/python -c "import pickle; print(pickle.load(open('$R27/state.pkl', 'rb'))['it'])"; }
  last=$(stat -c %Y "$R27/state.pkl")
  while systemctl --user is-active -q mtg-r27; do
    now=$(stat -c %Y "$R27/state.pkl")
    if [ "$now" != "$last" ]; then
      last=$now
      case $(( $(it) % 25 )) in 10|15|20) break ;; esac
    fi
    sleep 15
  done
  sleep 10
  systemctl --user stop mtg-r27
  log r27 "paused after update $(it)"
fi
if [ ! -f "$G" ]; then  # G is fixed once, at the first pause
  if [ "$PAUSE" = 1 ]; then cp "$R27/last.pt" "$G"; else cp "$GEN_FROM" "$G"; fi
  log G "$(sha256sum "$G" | cut -c1-16)"
fi

# generation: chunks of fresh deals until the shards hold $TARGETS targets
targets() { cat "$O"/gen_*/metrics.jsonl 2>/dev/null | .venv/bin/python -c "
import json, sys
print(sum(r['targets'] for r in map(json.loads, sys.stdin) if r.get('event') == 'targets'))"; }
gen() {  # gen K: chunk K's searched games, G against G
  step "gen_$1" "$GEN_CAP" $L --run "$O/gen_$1" --init "$G" $GAME --eval-only \
    --eval-seat eval+search --eval-opponents snap:opp --opp-ckpt "$G" $SEARCH --search-record \
    --eval-deals "$CHUNK" --eval-seed0 $((1000000 + CHUNK * $1))
}
if [ ! -f "$O/A_G" ]; then  # chunk 0 is gate A on G (196 A_G), read whole
  if [ ! -f "$O/gen_0.done" ] && [ -d "$O/gen_0" ]; then  # interrupted: set aside unread
    mv "$O/gen_0" "$O/interrupted_gen_0.$(date +%s)"
    log gen_0 "an interrupted chunk 0 set aside; played again"
  fi
  gen 0
  ag=$(score "$O/gen_0")
  [ -n "$ag" ] || fail "A_G not read: chunk 0 has no evaluation"
  echo "$ag" > "$O/A_G"
  log A_G "searched G against G: $ag"
fi
ag=$(cat "$O/A_G")
if .venv/bin/python -c "import sys; sys.exit(0 if float('$ag') < $AG_MIN else 1)"; then
  echo "A_G $ag, below $AG_MIN" > "$O/stopped"
  log A_G "below $AG_MIN: gate B stops"
  resume
  log gateb done
  exit 0
fi
for k in $(seq 1 $((MAX_CHUNKS - 1))); do
  [ "$(targets)" -ge "$TARGETS" ] && break
  [ -f "$O/gen_$k.tried" ] && continue
  touch "$O/gen_$k.tried"
  gen "$k"  # a capped chunk keeps its finished shards (they are written whole)
  log "gen_$k" "targets so far $(targets)"
done
RUNS=$(for k in $(seq 0 $((MAX_CHUNKS - 1))); do [ -d "$O/gen_$k" ] && echo "$O/gen_$k"; done)
RUNS=$(echo $RUNS)
n=$(targets)
log gen "$n targets in: $RUNS"
[ "$n" -ge "$TARGETS" ] || fail "generation short: $n of $TARGETS targets in $MAX_CHUNKS chunks"

# distillation: four arms over the same records (196 §1)
step distill_se 4h $D --init "$G" --out "$O/distill_se" --sizes "$SIZES" --rule se --seed 0 \
  --save-epochs $RUNS || fail "distill_se"
for arm in placebo se1 sigma; do
  rule=$arm; extra=""
  [ "$arm" = placebo ] && rule=se && extra=--placebo
  step "distill_$arm" 3h $D --init "$G" --out "$O/distill_$arm" --sizes "${SIZES##*,}" \
    --rule "$rule" $extra --seed 0 --save-epochs $RUNS || fail "distill_$arm"
done

# each arm's network: the best of its four trained epochs against G on the selection deals
N1=${SIZES%%,*}; N3=${SIZES##*,}
ARMS="se:$N1 se:$N3 placebo:$N3 se1:$N3 sigma:$N3"
for a in $ARMS; do
  arm=${a%%:*}; n=${a##*:}
  for e in 1 2 3 4; do
    step "sel_${arm}_${n}_e$e" 30m $L --run "$O/sel_${arm}_${n}_e$e" \
      --init "$O/distill_$arm/distilled_${n}_e$e.pt" $GAME --eval-only --eval-seat eval \
      --eval-opponents snap:opp --opp-ckpt "$G" --eval-deals "$SEL" --eval-seed0 970000 \
      || fail "sel_${arm}_${n}_e$e"
  done
done
.venv/bin/python - "$O" $ARMS > "$O/chosen.out" 2>&1 <<'PY' || fail "chosen: an epoch has no score"
import json, sys
o, arms = sys.argv[1], sys.argv[2:]
chosen = {}
for a in arms:
    arm, n = a.split(":")
    scores = {}
    for e in (1, 2, 3, 4):  # every epoch was played (each sel step is required)
        rows = [json.loads(x) for x in open(f"{o}/sel_{arm}_{n}_e{e}/metrics.jsonl")]
        scores[e] = [r for r in rows if r.get("event") == "eval"][-1]["snap:opp"]["score"]
    e = max(sorted(scores), key=lambda k: scores[k])  # a tie goes to the earlier epoch
    chosen[f"{arm}_{n}"] = {"epoch": e, "scores": scores,
                            "path": f"{o}/distill_{arm}/distilled_{n}_e{e}.pt"}
json.dump(chosen, open(f"{o}/chosen.json", "w"), indent=1)
print(json.dumps(chosen))
PY
log chosen "each arm's epoch in chosen.json"
pick() { .venv/bin/python -c "import json; print(json.load(open('$O/chosen.json'))['$1']['path'])"; }

# the tests on fresh deals (196 §1): each arm against G; G and se's 300k network against v0
for a in $ARMS; do
  arm=${a%%:*}; n=${a##*:}
  step "test_${arm}_$n" 30m $L --run "$O/test_${arm}_$n" --init "$(pick "${arm}_$n")" $GAME \
    --eval-only --eval-seat eval --eval-opponents snap:opp --opp-ckpt "$G" --eval-deals "$TEST" \
    --eval-seed0 980000 || fail "test_${arm}_$n"
done
for who in G "se_$N3"; do
  net=$G; [ "$who" != G ] && net=$(pick "$who")
  step "test_${who}_v0" 30m $L --run "$O/test_${who}_v0" --init "$net" $GAME --eval-only \
    --eval-seat eval --eval-opponents snap:opp --opp-ckpt "$V0" --eval-deals "$TEST" \
    --eval-seed0 980000 || fail "test_${who}_v0"
done

# GB2: agreement with the search's pick on the held-out targets of the $N3 distillation
step agreement 1h env PYTHONPATH=. .venv/bin/python reports/gate_b_2026-11-12/agreement.py \
  "$O/gb2.json" "$G" "$(pick "se_$N1")" "$(pick "se_$N3")" "$N3" $RUNS || fail "agreement"

# 192 §7.6's H1': u1000 against the heuristic on window 1's heur_raw deals, in bf16 and in fp32
# (no autocast since 197), at this commit; paired by deal. Not gate B: a failure is logged only.
H1="--init $U1000 --refresh-table --extend-sets M20 --pool verified --coherent-share 1.0
  --workers ${WORKERS:-18} --slots ${SLOTS:-16} --groups 4 --eval-only --eval-seat eval
  --eval-opponents heuristic --eval-set M21 --eval-deals $H1_DEALS --eval-seed0 900000"
step h1_bf16 20m $L --run "$O/h1_bf16" $H1 --infer-bf16
step h1_fp32 40m $L --run "$O/h1_fp32" $H1

resume
log gateb done
