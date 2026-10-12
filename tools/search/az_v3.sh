#!/usr/bin/env bash
# AZ-v3 iterative self-play chain (/72 mandate): gen(64g, greedy rollouts,
# k4/n10/cap40, pi_mix rows) -> warm-start S3a search-only train (+15 ep)
# -> 100g WR-gate vs teacher (tolerance 0.02, one seed+7 retry) -> next gen.
# 4 gens, stop-rule per /72: judge vs the one-shot bar 0.3927 (bc9_S3_s1).
# Logs to /tmp/opencode/az_v3.log. NEVER dead-stops: a failed phase keeps
# the last adopted net and moves on.
set -uo pipefail
cd /home/sune/Desktop/MTG_AI || exit 8
L=/tmp/opencode/az_v3.log
say(){ echo "[$(date '+%m-%d %H:%M:%S')] $*" | tee -a "$L"; }
PY=.venv/bin/python
T=tools/training
E=tools/eval
SEED_NET=$T/bc10_S3a_s2_best.pt   # S3a arm, vocab 455 — the warm-start chain head
GAMES=64; WORKERS=10; K=4; N=10; CAP=40; TOL=0.02; EXTRA_EPOCHS=15

wr(){ $PY -c "import json,sys;m=json.load(open(sys.argv[1]))['matchups'];print(list(m.values())[0].get('winrate_decisive'))" "$1" 2>/dev/null; }
wp(){ $PY -c "import torch,sys;print(torch.load(sys.argv[1],map_location='cpu',weights_only=False)['train_info']['written_at_epoch'])" "$1" 2>/dev/null; }

# gate(ckpt, out-json, seed-base) -> echoes WR, "None" on failure
gate(){ local ck=$1 out=$2 sb=$3
  timeout 5400 $PY $E/gameplay_eval_v2.py --policy-a "$ck" --matchups teacher \
    --games 100 --workers 5 --device cpu --seed-base "$sb" --out "$out" >>"$L" 2>&1 \
    || { say "gate eval FAILED ($ck sb=$sb)"; return 1; }
  wr "$out"; }

[ -f "$SEED_NET" ] || { say "ABORT: no chain seed $SEED_NET"; exit 9; }
ADOPT=$SEED_NET; BEST=$(gate "$ADOPT" $E/gameplay_azv3_g0.json 3000)
[ "$BEST" = "None" ] && BEST=0
say "G0 gate on ${ADOPT##*/}: WR=$BEST (chain head)"

for g in 1 2 3 4; do
  say "=== GEN $g: 64g k$K/n$N/cap$CAP greedy-mix net=${ADOPT##*/} ==="
  rm -f $T/eps_g$g.jsonl
  timeout 108000 $PY tools/search/gen_games.py --games $GAMES \
    --seeds $((20000+g*100)) --workers $WORKERS --k $K --n $N --cap $CAP \
    --rollout-mix greedy --net "$ADOPT" \
    --out-episodes $T/eps_g$g.jsonl --out-stats tools/search/gen_stats_g$g.json \
    >>"$L" 2>&1 || say "GEN $g FAILED (partial eps kept)"
  NR=$(wc -l < "$T/eps_g$g.jsonl" 2>/dev/null || echo 0)
  if [ "$NR" -lt 8 ]; then say "GEN $g only $NR eps -> skip train, keep ${ADOPT##*/}"; continue; fi
  PREV=$(wp "$ADOPT"); PREV=${PREV:-250}
  cp "$ADOPT" $T/azg${g}_best.pt   # resume head for this gen's prefix
  say "TRAIN azg$g: $NR eps, resume @ep$PREV -> $((PREV+EXTRA_EPOCHS)) (+$EXTRA_EPOCHS)"
  timeout 32400 $PY -m tools.training.train_bc_v3 --arm S3a --mix search \
    --search-data $T/eps_g$g.jsonl --prefix azg$g --epochs $((PREV+EXTRA_EPOCHS)) \
    --device auto >>"$L" 2>&1 || { say "TRAIN azg$g FAILED, keep ${ADOPT##*/}"; continue; }
  W=$(gate $T/azg${g}_best.pt $E/gameplay_azv3_g${g}.json $((3000+g*100)))
  say "GATE $g: azg$g WR=$W (best $BEST, bar $BEST minus $TOL)"
  if python3 - "$W" "$BEST" <<'PY'
import sys
try: sys.exit(0 if float(sys.argv[1]) >= float(sys.argv[2]) - 0.02 else 1)
except Exception: sys.exit(1)
PY
  then
    ADOPT=$T/azg${g}_best.pt; BEST=$(python3 -c "print(max(float('$W'),float('$BEST')))")
    say "ADOPT azg$g (WR=$W)"
  else
    say "retry $g once on seed $((3000+g*100+7))"
    W=$(gate $T/azg${g}_best.pt $E/gameplay_azv3_g${g}r.json $((3000+g*100+7)))
    if python3 -c "import sys;sys.exit(0 if float(sys.argv[1]) >= float(sys.argv[2]) - 0.02 else 1)" "$W" "$BEST" 2>/dev/null; then
      ADOPT=$T/azg${g}_best.pt; BEST=$(python3 -c "print(max(float('$W'),float('$BEST')))")
      say "ADOPT azg$g on retry (WR=$W)"
    else
      say "KEEP ${ADOPT##*/} (azg$g WR=$W below bar)"
    fi
  fi
done

say "FINAL 200g: ${ADOPT##*/} vs teacher / bc10_S4_s2 / bc9_S3_s1"
timeout 10800 $PY $E/gameplay_eval_v2.py --policy-a "$ADOPT" --matchups teacher \
  --games 200 --workers 6 --device cpu --seed-base 9100 \
  --out $E/gameplay_azv3_f1.json >>"$L" 2>&1 || say "FINAL teacher FAIL"
for pair in "bc10_S4_s2 $T/bc10_S4_s2_best.pt f2" "bc9_S3_s1 $T/bc9_S3_s1_best.pt f3"; do
  set -- $pair
  [ -f "$2" ] || { say "FINAL skip $1 (no ckpt)"; continue; }
  timeout 10800 $PY $E/gameplay_eval_v2.py --policy-a "$ADOPT" --policy-b "$2" \
    --matchups mirror --games 200 --workers 6 --device cpu --seed-base 9300 \
    --out $E/gameplay_azv3_$3.json >>"$L" 2>&1 || say "FINAL $1 FAIL"
done
$PY - <<PY >>"$L" 2>&1
import json, glob
parts = {}
for f in sorted(glob.glob("$E/gameplay_azv3_f[123].json")):
    d = json.load(open(f))
    parts.update(d["matchups"])
json.dump({"chain": "$ADOPT", "matchups": parts},
          open("$E/gameplay_azv3_final.json", "w"), indent=1)
print("FINAL merged:", {k: v.get("winrate_decisive") for k, v in parts.items()})
PY
say "AZ-v3 CHAIN COMPLETE. adopted=${ADOPT##*/} best_gate_WR=$BEST (one-shot bar 0.3927)"
