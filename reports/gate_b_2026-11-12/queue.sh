#!/bin/bash
# Gate B (KNOWLEDGE/2026-11-12/196): r27 pauses right after a save, away from its gates; its
# last.pt is the generator G. Chunks of searched games record targets until 300k exist; chunk 0
# is gate A on G. Then four distillation arms; each arm's epoch is chosen by play on deals
# 970,000+; the tests run on deals 980,000+; GB2's agreement; then r27 resumes. Runs from a
# worktree pinned at the note's commit; one GPU job at a time; every step has a time cap; a
# finished step (its .done file) is skipped on a restart, and a chunk once started is never
# replayed (its .tried file).
#   systemd-run --user --unit mtg-gateb /bin/bash \
#     /home/sune/Desktop/MTG_AI-gateb/reports/gate_b_2026-11-12/queue.sh
# A CPU smoke overrides the sizes and sets PAUSE=0, which neither stops nor starts r27 and takes
# G from GEN_FROM.
set -u
W=${W:-/home/sune/Desktop/MTG_AI-gateb}
R=/home/sune/Desktop/MTG_AI/runs
O=${O:-$R/gateb}
R27=$R/selfplay/r27_priority_ppo
G=$O/gen.pt
V0=$R27/v0.pt
PAUSE=${PAUSE:-1}
TARGETS=${TARGETS:-300000}
SIZES=${SIZES:-100000,300000}
CHUNK=${CHUNK:-1875}
MAX_CHUNKS=${MAX_CHUNKS:-14}
SEL=${SEL:-500}
TEST=${TEST:-1000}
AG_MIN=${AG_MIN:-0.54}
SEARCH="--search-root gumbel --search-m 16 --search-n ${SEARCH_N:-16}"
GAME="--pool verified --infer-bf16 --eval-set M21 --workers ${WORKERS:-18} --slots ${SLOTS:-16}
  --groups ${GROUPS:-4}"
cd "$W" || exit 1
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
mkdir -p "$O"
log() { echo "{\"t\": $(date +%s), \"step\": \"$1\", \"what\": \"$2\"}" >> "$O/queue.log"; }
step() {  # step NAME CAP COMMAND...
  local name=$1 cap=$2; shift 2
  [ -f "$O/$name.done" ] && return 0
  log "$name" start
  timeout "$cap" "$@" > "$O/$name.out" 2>&1
  local rc=$?
  [ $rc -eq 0 ] && touch "$O/$name.done"
  log "$name" "exit $rc"
}
L=".venv/bin/python -m tools.selfplay.learner"
D="env PYTHONPATH=. .venv/bin/python -m tools.selfplay.distill"
score() {  # the evaluated seat's score in an eval-only run's summary
  .venv/bin/python - "$1/metrics.jsonl" <<'PY'
import json, sys
rows = [json.loads(x) for x in open(sys.argv[1]) if '"event": "eval"' in x]
print(rows[-1]["snap:opp"]["score"] if rows and "snap:opp" in rows[-1] else "")
PY
}
resume() { [ "$PAUSE" = 1 ] && systemctl --user start mtg-r27 && log r27 resumed; }

# r27 pauses at its first save whose update is 10, 15 or 20 past a gate (as window 2's queue)
if [ ! -f "$O/pause.done" ]; then
  if [ "$PAUSE" = 1 ]; then
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
    cp "$R27/last.pt" "$G"
    log r27 "paused after update $(it); G $(sha256sum "$G" | cut -c1-16)"
  else
    cp "$GEN_FROM" "$G"
    log smoke "G from $GEN_FROM $(sha256sum "$G" | cut -c1-16)"
  fi
  touch "$O/pause.done"
fi

if [ -f "$O/stopped" ]; then  # gate A on G failed before: a restart must not generate
  log gateb "stopped earlier: $(cat "$O/stopped")"
  resume
  exit 0
fi

# generation: chunks of fresh deals until the shards hold $TARGETS targets
targets() { cat "$O"/gen_*/metrics.jsonl 2>/dev/null | .venv/bin/python -c "
import json, sys
print(sum(json.loads(x)['targets'] for x in sys.stdin if '\"event\": \"targets\"' in x))"; }
for k in $(seq 0 $((MAX_CHUNKS - 1))); do
  [ "$(targets)" -ge "$TARGETS" ] && break
  [ -f "$O/gen_$k.tried" ] && continue
  touch "$O/gen_$k.tried"
  step "gen_$k" 4h $L --run "$O/gen_$k" --init "$G" $GAME --eval-only --eval-seat eval+search \
    --eval-opponents snap:opp --opp-ckpt "$G" $SEARCH --search-record --eval-deals "$CHUNK" \
    --eval-seed0 $((1000000 + CHUNK * k))
  log "gen_$k" "targets so far $(targets)"
  if [ "$k" = 0 ]; then  # gate A on G (196 A_G)
    ag=$(score "$O/gen_0")
    log A_G "searched G against G: ${ag:-none}"
    if [ -z "$ag" ] || .venv/bin/python -c "import sys; sys.exit(0 if float('$ag') < $AG_MIN else 1)"; then
      echo "A_G ${ag:-not read}, below $AG_MIN" > "$O/stopped"
      log A_G "below $AG_MIN or not read: gate B stops"
      resume
      log gateb done
      exit 0
    fi
  fi
done
RUNS=$(for k in $(seq 0 $((MAX_CHUNKS - 1))); do [ -d "$O/gen_$k" ] && echo "$O/gen_$k"; done)
RUNS=$(echo $RUNS)
log gen "$(targets) targets in: $RUNS"

# distillation: four arms over the same records (196 §1)
step distill_se 4h $D --init "$G" --out "$O/distill_se" --sizes "$SIZES" --rule se --seed 0 \
  --save-epochs $RUNS
for arm in placebo se1 sigma; do
  rule=$arm; extra=""
  [ "$arm" = placebo ] && rule=se && extra=--placebo
  step "distill_$arm" 3h $D --init "$G" --out "$O/distill_$arm" --sizes "${SIZES##*,}" \
    --rule "$rule" $extra --seed 0 --save-epochs $RUNS
done

# each arm's network: the best of its trained epochs against G on the selection deals
N1=${SIZES%%,*}; N3=${SIZES##*,}
ARMS="se:$N1 se:$N3 placebo:$N3 se1:$N3 sigma:$N3"
for a in $ARMS; do
  arm=${a%%:*}; n=${a##*:}
  for e in 1 2 3 4; do
    step "sel_${arm}_${n}_e$e" 30m $L --run "$O/sel_${arm}_${n}_e$e" \
      --init "$O/distill_$arm/distilled_${n}_e$e.pt" $GAME --eval-only --eval-seat eval \
      --eval-opponents snap:opp --opp-ckpt "$G" --eval-deals "$SEL" --eval-seed0 970000
  done
done
.venv/bin/python - "$O" $ARMS > "$O/chosen.out" 2>&1 <<'PY'
import json, sys
o, arms = sys.argv[1], sys.argv[2:]
chosen = {}
for a in arms:
    arm, n = a.split(":")
    scores = {}
    for e in (1, 2, 3, 4):
        try:
            rows = [json.loads(x) for x in open(f"{o}/sel_{arm}_{n}_e{e}/metrics.jsonl")
                    if '"event": "eval"' in x]
            scores[e] = rows[-1]["snap:opp"]["score"]
        except (OSError, IndexError, KeyError):
            continue
    if scores:
        e = max(sorted(scores), key=lambda k: scores[k])  # a tie goes to the earlier epoch
        chosen[f"{arm}_{n}"] = {"epoch": e, "scores": scores,
                                "path": f"{o}/distill_{arm}/distilled_{n}_e{e}.pt"}
json.dump(chosen, open(f"{o}/chosen.json", "w"), indent=1)
print(json.dumps(chosen))
PY
log chosen "each arm's epoch in chosen.json"
pick() { .venv/bin/python -c "import json; print(json.load(open('$O/chosen.json')).get('$1', {}).get('path', ''))"; }

# the tests on fresh deals (196 §1): each arm against G; G and se's 300k network against v0
for a in $ARMS; do
  arm=${a%%:*}; n=${a##*:}; net=$(pick "${arm}_$n")
  [ -n "$net" ] && step "test_${arm}_$n" 30m $L --run "$O/test_${arm}_$n" --init "$net" $GAME \
    --eval-only --eval-seat eval --eval-opponents snap:opp --opp-ckpt "$G" --eval-deals "$TEST" \
    --eval-seed0 980000
done
for who in G "se_$N3"; do
  net=$G; [ "$who" != G ] && net=$(pick "$who")
  [ -n "$net" ] && step "test_${who}_v0" 30m $L --run "$O/test_${who}_v0" --init "$net" $GAME \
    --eval-only --eval-seat eval --eval-opponents snap:opp --opp-ckpt "$V0" --eval-deals "$TEST" \
    --eval-seed0 980000
done

# GB2: agreement with the search's pick on the held-out targets
n100=$(pick "se_$N1"); n300=$(pick "se_$N3")
[ -n "$n100" ] && [ -n "$n300" ] && step agreement 1h env PYTHONPATH=. .venv/bin/python \
  reports/gate_b_2026-11-12/agreement.py "$O/gb2.json" "$G" "$n100" "$n300" $RUNS

resume
log gateb done
