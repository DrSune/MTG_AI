#!/usr/bin/env bash
# Seed variance S0/S4 x seeds {2,3}, engine-ON (small runs, contention-tolerant).
set -uo pipefail
cd "$(dirname "$0")/../.."
for spec in "S0 2" "S0 3" "S4 2" "S4 3"; do
  set -- $spec; arm=$1; seed=$2
  pref="bc5v5_${arm}_s${seed}"
  [ -f "tools/training/${pref}_report.json" ] && { echo "skip $pref"; continue; }
  .venv/bin/python tools/training/run_train.py --phase "seedvar-${pref}" --timeout 2400 -- \
    .venv/bin/python -m tools.training.train_bc_v3 --arm "$arm" --seed "$seed" --prefix "$pref" \
    && echo "OK $pref" || echo "FAIL $pref"
done
echo SEEDVAR_DIRECT_DONE
