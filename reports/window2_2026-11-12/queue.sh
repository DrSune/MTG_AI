#!/bin/bash
# Window 2 (PLAN_CEILING §10): r27 pauses right after a save, away from its gates; the belief
# audit (KNOWLEDGE/2026-11-12/195), the capacity probe (194), the drafter's G2 and G4 (193), and
# two checks of window 1's heuristic match (192 §7.6); then r27 resumes. Runs from the pinned
# worktree; one GPU job at a time; each step has a time cap so the pause is bounded; a finished
# step (its .done file) is skipped on a restart.
#   systemd-run --user --unit mtg-window2 /bin/bash \
#     /home/sune/Desktop/MTG_AI-w2/reports/window2_2026-11-12/queue.sh
set -u
W=/home/sune/Desktop/MTG_AI-w2
R=/home/sune/Desktop/MTG_AI/runs
O=$R/window2
R27=$R/selfplay/r27_priority_ppo
U1000=$R/selfplay/r26_outcome_ppo/u1000.pt
V0=$R27/v0.pt                # r27's v0: u1000 with the table refreshed at r27's start
LATEST=$O/r27_latest.pt      # r27's weights at the pause
CRITIC=$O/critic_r27.json    # 193 G1's critic, fitted on r27's logged games before the window
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
GAME="--pool verified --coherent-share 1.0 --infer-bf16 --workers 18 --slots 16 --groups 4"

# r27 pauses at its first save whose update is 10, 15 or 20 past a gate (a gate is queued at
# every 25th update and finishes within about 2; a freeze's ladders within about 5), so no
# evaluation is in flight. last.pt and state.pkl are written together (learner.save_state).
if [ ! -f "$O/pause.done" ]; then
  it() { .venv/bin/python -c "import pickle; print(pickle.load(open('$R27/state.pkl', 'rb'))['it'])"; }
  last=$(stat -c %Y "$R27/state.pkl")
  while systemctl --user is-active -q mtg-r27; do  # a run that already stopped needs no pause
    now=$(stat -c %Y "$R27/state.pkl")
    if [ "$now" != "$last" ]; then
      last=$now
      case $(( $(it) % 25 )) in 10|15|20) break ;; esac
    fi
    sleep 15
  done
  sleep 10
  systemctl --user stop mtg-r27
  cp "$R27/last.pt" "$LATEST"
  log r27 "paused after update $(it); $(sha256sum "$LATEST" | cut -c1-16) copied"
  touch "$O/pause.done"
fi

# 195: the belief audit, as window 1's n = 16 point on fresh deals
step audit 60m $L --run "$O/audit" --init "$U1000" --refresh-table --extend-sets M20 $GAME \
  --eval-only --eval-seat eval+search --eval-opponents snap:opp --opp-ckpt "$U1000" \
  --eval-set M21 --search-root gumbel --search-m 16 --search-n 16 --search-audit 8 \
  --search-sim "$R/window1/sim.pt" --eval-deals 100 --eval-seed0 960000

# 194: the capacity probe, r27's own flags from its v0 on fresh deals, then the three arms
step collect 40m $L --run "$O/collect" --init "$U1000" --seed 2712 --workers 18 --slots 16 \
  --groups 4 --gamma 1.0 --lam 1.0 --steps 1200000 --epochs 1 --lr 2e-5 --wd 0.01 --clip 0.2 \
  --vclip 0.5 --vcoef 0.5 --ent 0.004 --max-grad 1.0 --target-kl 0 --mb 4096 \
  --tok-budget 98304 --infer-bf16 --teacher-iters 0 --gate-every 25 --gate-deals 1000 \
  --gate-score 0.55 --ladder-deals 500 --p-heuristic 0.15 --p-past 0.15 --coherent-share 1.0 \
  --mix-sets M20 --mix-share 0.25 --extend-sets M20 --refresh-table --pool verified \
  --save-every 5 --progress-every 300 --mem-floor-gib 15.0 --iters 6000 \
  --collect "$O/collect.pkl"
for lr in 3e-5 1e-4; do
  step "probe_lr$lr" 60m env PYTHONPATH=. .venv/bin/python \
    reports/capacity_probe_2026-11-12/probe.py "$O/collect.pkl" "$V0" "$O/probe.jsonl" --lr "$lr"
done

# 193: G2, the drafted deck against the plain one, r27's latest network on both seats
for k in 0 4 8 16; do
  step "g2_versus$k" 20m $L --run "$O/g2_versus$k" --init "$LATEST" $GAME --eval-only \
    --eval-seat eval --eval-opponents snap:opp --opp-ckpt "$LATEST" --eval-set M21 \
    --eval-deals 1000 --eval-decks "versus:$k" --draft-critic "$CRITIC"
done
# 193: G4, r27's latest network against its v0, on drafted decks and on plain ones
step g4_drafted8 20m $L --run "$O/g4_drafted8" --init "$LATEST" $GAME --eval-only \
  --eval-seat eval --eval-opponents snap:opp --opp-ckpt "$V0" --eval-set M21 --eval-deals 1000 \
  --eval-decks drafted:8 --draft-critic "$CRITIC"
step g4_coherent 20m $L --run "$O/g4_coherent" --init "$LATEST" $GAME --eval-only \
  --eval-seat eval --eval-opponents snap:opp --opp-ckpt "$V0" --eval-set M21 --eval-deals 1000

# 192 §7.6: window 1's raw match against the heuristic again, in fp32, and on the castable pool
step heur_raw_fp32 10m $L --run "$O/heur_raw_fp32" --init "$U1000" --refresh-table \
  --extend-sets M20 --pool verified --coherent-share 1.0 --workers 18 --slots 16 --groups 4 \
  --eval-only --eval-seat eval --eval-opponents heuristic --eval-set M21 --eval-deals 300
step heur_raw_castable 10m $L --run "$O/heur_raw_castable" --init "$U1000" --refresh-table \
  --extend-sets M20 --pool castable --coherent-share 1.0 --infer-bf16 --workers 18 --slots 16 \
  --groups 4 --eval-only --eval-seat eval --eval-opponents heuristic --eval-set M21 \
  --eval-deals 300

systemctl --user start mtg-r27
log r27 resumed
log window done
