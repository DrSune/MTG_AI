#!/usr/bin/env bash
# Seed variance for the v5 S0-vs-S4 question (owner law: no single-seed claims).
set -uo pipefail
cd "$(dirname "$0")/../.."
LOCK=/tmp/opencode/seedvar.lock
if ! mkdir "$LOCK" 2>/dev/null; then
  echo "seedvar: ANOTHER driver holds $LOCK — refusing to race. Exit 9."
  exit 9
fi
trap 'rmdir "$LOCK" 2>/dev/null' EXIT
PY=(.venv/bin/python -m)
RUN=(.venv/bin/python tools/training/run_train.py)
for spec in "S0 2" "S0 3" "S4 2" "S4 3"; do
  set -- $spec; arm=$1; seed=$2
  pref="bc5v5_${arm}_s${seed}"
  [ -f "tools/training/${pref}_report.json" ] && { echo "skip $pref"; continue; }
  "${RUN[@]}" --phase "seedvar-${pref}" --timeout 3600 -- \
    "${PY[@]}" tools.training.train_bc_v3 --arm "$arm" --seed "$seed" --prefix "$pref" \
    || { echo "FAIL $pref"; }
done
echo "=== seedvar complete ==="
