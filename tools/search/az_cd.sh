#!/usr/bin/env bash
set -uo pipefail; cd /home/sune/Desktop/MTG_AI || exit 8
L=/tmp/opencode/night_az.log
say(){ echo "[$(date +%H:%M:%S)] $*" | tee -a "$L"; }
say "C selection duels (bsz seeds, 100g vs teacher) start"
for s in 1 2 3; do
  ck="tools/training/bsz_S3a_s${s}_best.pt"
  [ -f "$ck" ] || { say "C no ckpt s$s"; continue; }
  timeout 5400 .venv/bin/python tools/eval/gameplay_eval_v2.py --policy-a "$ck" \
    --matchups teacher --games 100 --workers 5 --device cpu --seed-base $((1200+s*100)) \
    --out "tools/eval/gameplay_azsel_s${s}.json" >>"$L" 2>&1 \
    && say "C s$s wr=$( .venv/bin/python -c "import json;m=json.load(open('tools/eval/gameplay_azsel_s${s}.json'))['matchups'];print(list(m.values())[0].get('winrate_decisive'))" 2>/dev/null || echo '?')" \
    || say "C FAIL s$s"
done
BEST=$(.venv/bin/python - <<'PY'
import json,glob
best=(None,-1)
for f in glob.glob('tools/eval/gameplay_azsel_s*.json'):
    try:
        w=list(json.load(open(f))['matchups'].values())[0].get('winrate_decisive') or 0
        if w>best[1]: best=(f,w)
    except Exception: pass
print(best[0] or '')
PY
)
BS=$(basename "${BEST:-none}" | sed -n 's/gameplay_azsel_s\([0-9]\).json/\1/p')
say "C best: ${BEST:-none} seed=${BS:-none}"
[ -z "$BS" ] && { say "ABORT D"; exit 9; }
CK="tools/training/bsz_S3a_s${BS}_best.pt"
timeout 10800 .venv/bin/python tools/eval/gameplay_eval_v2.py --policy-a "$CK" \
  --policy-b tools/training/bc10_S4_s2_best.pt --matchups mirror,teacher --games 200 \
  --workers 6 --device cpu --out tools/eval/gameplay_az_final.json >>"$L" 2>&1 \
  && say "D FINAL done" || say "D FINAL failed"
say "AZ-CHAIN COMPLETE"
