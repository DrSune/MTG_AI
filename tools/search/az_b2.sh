#!/usr/bin/env bash
# Phase B2: search-only distill, epochs=50, 3 parallel CPU arms (owner-clean test:
# one variable vs v6's mixed collapse). C/D follow via az_cd.sh.
set -uo pipefail; cd /home/sune/Desktop/MTG_AI || exit 8
L=/tmp/opencode/night_az.log
for s in 1 2 3; do
  p="bsz_S3a_s${s}"
  [ -f "tools/training/${p}_report.json" ] && continue
  OMP_NUM_THREADS=3 timeout 18000 .venv/bin/python -m tools.training.train_bc_v3 \
    --arm S3a --seed "$s" --prefix "$p" --mix search --epochs 50 --device cpu \
    >>"$L" 2>&1 && echo "[$(date +%H:%M:%S)] B2 ok $p" >>"$L" || echo "[$(date +%H:%M:%S)] B2 FAIL $p" >>"$L" &
done
wait
echo "[$(date +%H:%M:%S)] B2 ALL DONE" >>"$L"
nohup setsid bash tools/search/az_cd.sh >/tmp/opencode/az_cd.log 2>&1 </dev/null &
