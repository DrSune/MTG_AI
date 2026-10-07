#!/usr/bin/env bash
# S4 seed variance, ZERO ceremony (6 wrapper deaths 2026-10-07/08: every failure was
# ledger/guard machinery; train_bc_v3 itself never failed when called directly).
# Engine-on runs: 35M under KV contention ~35-45 min => timeout 3300 per run.
set -uo pipefail
cd "$(dirname "$0")/../.."
for seed in 2 3; do
  pref="bc5v5_S4_s${seed}"
  [ -f "tools/training/${pref}_report.json" ] && { echo "skip $pref"; continue; }
  echo "== $pref start $(date +%H:%M:%S)"
  timeout 3300 .venv/bin/python -m tools.training.train_bc_v3 --arm S4 --seed "$seed" --prefix "$pref" \
    && echo "OK $pref $(date +%H:%M:%S)" || echo "FAIL $pref rc=$? $(date +%H:%M:%S)"
done
echo SEEDVAR_PLAIN_DONE
