#!/usr/bin/env bash
# batch6 remaining runs, plain no-ceremony (wrapper lesson law 2026-10-08). Longest first.
set -uo pipefail
cd "$(dirname "$0")/../.." || exit 8
echo "B6P alive $(date +%H:%M:%S)"
run() { # arm seed timeout
  local pref="bc6_$1_s$2"
  [ -f "tools/training/${pref}_report.json" ] && { echo "skip $pref"; return; }
  echo "== $pref start $(date +%H:%M:%S)"
  timeout "$3" .venv/bin/python -m tools.training.train_bc_v3 --arm "$1" --seed "$2" --prefix "$pref" \
    && echo "OK $pref $(date +%H:%M:%S)" || echo "FAIL $pref rc=$? $(date +%H:%M:%S)"
}
run S4 3 4800; run S4 1 4800; run S4 2 4800
run S3 1 1800; run S3 2 1800; run S3 3 1800
run S2 1 1800; run S2 2 1800; run S2 3 1800
run S1 1 1200; run S1 2 1200; run S1 3 1200
run S0 3 1200
echo B6P_DONE $(date +%H:%M:%S)
