#!/usr/bin/env bash
# AlphaZero chain v2 (owner mandate /67; after negative /71). Phases, each logged:
#  A gen 96 self-play games (cheap-rollout, cap25, k3/N6) -> episodes_search_v2.jsonl
#  B distill bsd_v2_S3a x3 seeds on CPU, ANCHOR-UP-WEIGHTED mix (v2 kept strong)
#  C model SELECT by outcome meter: each seed plays 100 games vs greedy teacher
#  D final: best-seed 200g vs teacher + 200g mirror vs bc10_S4_s2
# Engine-ON, CPU, coexists with other sessions. NO training on GPU here.
set -uo pipefail
cd /home/sune/Desktop/MTG_AI || exit 8
L=/tmp/opencode/night_az.log
say(){ echo "[$(date +%H:%M:%S)] $*" | tee -a "$L"; }
say "AZ-CHAIN START (engine on, cpu)"

# ---- A: generation wave v2 (96 games) ----
EP=tools/training/episodes_search_v2.jsonl
if [ ! -s "$EP" ]; then
  timeout 9000 .venv/bin/python tools/search/gen_games.py --games 96 --seeds 9200 \
    --workers 8 --out-stats tools/search/gen_stats_v2.json >>"$L" 2>&1 \
    && say "A gen done: $(wc -l < "$EP" 2>/dev/null || echo 0) eps" \
    || say "A gen FAILED/partial (guard may have cut) eps=$(wc -l < "$EP" 2>/dev/null || echo 0)"
else say "A skip (episodes exist)"; fi
EPN=$(wc -l < "$EP" 2>/dev/null || echo 0); say "A: episodes=$EPN"
[ "$EPN" -lt 40 ] && { say "ABORT: too few episodes for distill"; exit 9; }

# ---- B: distill arms (anchor up-weighted via search-weight 0.5 => v2 rows 2x) ----
for s in 1 2 3; do
  p="bsd_v2_S3a_s${s}"
  [ -f "tools/training/${p}_report.json" ] && { say "B skip $p"; continue; }
  timeout 5400 .venv/bin/python -m tools.training.train_bc_v3 --arm S3a --seed "$s" \
    --prefix "$p" --mix "search+v2" --search-weight 0.5 --device cpu >>"$L" 2>&1 \
    && say "B ok $p $(.venv/bin/python -c "import json;d=json.load(open('tools/training/${p}_report.json'));print(round(d['gates']['gold_lines_all']['acc'],3))" 2>/dev/null || echo no-report)" \
    || say "B FAIL $p"
done

# ---- C: select by OUTCOME: 100g vs teacher per seed ----
say "C selection duels start"
for s in 1 2 3; do
  ck="tools/training/bsd_v2_S3a_s${s}_best.pt"
  [ -f "$ck" ] || { say "C no ckpt s$s"; continue; }
  timeout 3600 .venv/bin/python tools/eval/gameplay_eval_v2.py --policy-a "$ck" \
    --matchups teacher --games 100 --workers 6 --device cpu --seed-base $((1000+s*100)) \
    --out "tools/eval/gameplay_azsel_s${s}.json" >>"$L" 2>&1 \
    && say "C s$s wr=$(.venv/bin/python -c "import json;m=json.load(open('tools/eval/gameplay_azsel_s${s}.json'))['matchups'];print(list(m.values())[0].get('winrate_decisive'))" 2>/dev/null || echo '?')" \
    || say "C FAIL s$s"
done
BEST=$(ls tools/eval/gameplay_azsel_s*.json 2>/dev/null | head -20 | .venv/bin/python -c "
import json,sys
best=(None,-1)
for f in sys.stdin.read().split():
    try:
        m=list(json.load(open(f))['matchups'].values())[0]
        w=m.get('winrate_decisive') or 0
        if w>best[1]: best=(f,w)
    except Exception: pass
print(best[0] or '')")
say "C best sel file: $BEST"
BS=$(basename "$BEST" 2>/dev/null | sed -n 's/gameplay_azsel_s\([0-9]\).json/\1/p'); say "C best seed: $BS"
[ -z "$BS" ] && { say "ABORT D: no selection"; exit 9; }

# ---- D: final duels on selected seed ----
CK="tools/training/bsd_v2_S3a_s${BS}_best.pt"
timeout 7200 .venv/bin/python tools/eval/gameplay_eval_v2.py --policy-a "$CK" \
  --policy-b tools/training/bc10_S4_s2_best.pt --matchups mirror,teacher --games 200 \
  --workers 6 --device cpu --out tools/eval/gameplay_az_final.json >>"$L" 2>&1 \
  && say "D FINAL done" || say "D FINAL failed"
say "AZ-CHAIN COMPLETE"
