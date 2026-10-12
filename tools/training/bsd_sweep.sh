#!/usr/bin/env bash
# bsd sweep: search-distill arms x seeds on CPU (engine-ON safe, small/mid arms).
# mix variants: sv2 = search+v2 (anchor), so = search-only (ablation).
set -uo pipefail
cd "$(dirname "$0")/../.." || exit 8
echo "bsd sweep alive $(date +%H:%M:%S)"
run() { # arm seed prefix mix weight
  local arm=$1 seed=$2 pref=$3 mix=$4 w=$5
  [ -f "tools/training/${pref}_report.json" ] && { echo "skip $pref"; return; }
  timeout 7200 .venv/bin/python -m tools.training.train_bc_v3 --arm "$arm" --seed "$seed" \
    --prefix "$pref" --mix "$mix" --search-weight "$w" --device cpu \
    && echo "OK $pref $(date +%H:%M:%S)" || echo "FAIL $pref rc=$? $(date +%H:%M:%S)"
}
for seed in 1 3; do  # s2 exists as mid-train only; re-run fresh for comparability
  run S3a "$seed" "bsd_sv2_S3a_s${seed}" "search+v2" 1.0
done
for seed in 1 2 3; do
  run S3a "$seed" "bsd_so_S3a_s${seed}" "search" inf
done
run S0 1 bsd_sv2_S0_s1 "search+v2" 1.0
run S0 2 bsd_sv2_S0_s2 "search+v2" 1.0
run S0 3 bsd_sv2_S0_s3 "search+v2" 1.0
echo BSD_SWEEP_DONE
