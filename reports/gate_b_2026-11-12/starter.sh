#!/bin/bash
# Starts gate B (KNOWLEDGE/2026-11-12/196 §8) once r28 has passed update 405, after its read at
# 400: the queue then pauses r28 at the next safe save (10-20 past a gate) and takes that save as
# G. Run as a transient unit, so it is lost on a reboot (start it again then):
#   systemd-run --user --unit mtg-gateb-starter /bin/bash \
#     /home/sune/Desktop/MTG_AI-gateb/reports/gate_b_2026-11-12/starter.sh
STATE=/home/sune/Desktop/MTG_AI/runs/selfplay/r28_stratified_ppo/state.pkl
PY=/home/sune/Desktop/MTG_AI/.venv/bin/python
while :; do
  it=$($PY -c "import pickle; print(pickle.load(open('$STATE', 'rb'))['it'])" 2>/dev/null)
  [ -n "$it" ] && [ "$it" -ge 405 ] && break
  sleep 300
done
echo "{\"t\": $(date +%s), \"starter\": \"r28 at update $it: starting gate B\"}"
systemd-run --user --unit mtg-gateb /bin/bash /home/sune/Desktop/MTG_AI-gateb/reports/gate_b_2026-11-12/queue.sh
