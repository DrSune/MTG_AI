#!/bin/bash
# r28's read at update 400 (KNOWLEDGE/2026-11-12/199 §4, §7) and gate B's decision (196 §9-§10).
# Once the gate at 400 is logged, r28 pauses at its next save. That save is kept as
# runs/r28_looks/r28_u<it>.pt, and the per-kind split's batch is collected on it (199 §7: the read
# at 400 repeats the split). Then 196 §9's rule decides gate B:
# - with no version frozen after v0, r28's rate is 0, so s* = 0.5 <= 0.53 and generation runs:
#   gate B's queue starts from its worktree, if that worktree is at PIN (re-pinned and re-smoked,
#   196 §10). The queue finds r28 paused, so G is that same save.
# - otherwise (a later freeze needs the ladder's fit, or the worktree is not at PIN) r28 resumes
#   and the decision is made by hand.
#   systemd-run --user --unit mtg-at400 /bin/bash \
#     /home/sune/Desktop/MTG_AI/reports/r28_2026-11-12/at400.sh PIN
set -u
PIN=${1:?the commit gate B's worktree must be at}
M=/home/sune/Desktop/MTG_AI
RUN=$M/runs/selfplay/r28_stratified_ppo
LOOKS=$M/runs/r28_looks
GW=/home/sune/Desktop/MTG_AI-gateb
PY=$M/.venv/bin/python
LOG=$LOOKS/at400.log
mkdir -p "$LOOKS"
say() { echo "$(date -Is) $*" >> "$LOG"; }
row() {  # row gate|save|freeze: the newest gate's update, the newest saved update, later freezes
  $PY - "$RUN/metrics.jsonl" "$1" <<'PY'
import json, sys
rows = [json.loads(x) for x in open(sys.argv[1])]
if sys.argv[2] == "gate":
    print(max([r["it"] for r in rows if r.get("event") == "gate"], default=0))
elif sys.argv[2] == "save":  # saves follow the iter rows of updates divisible by 5 (--save-every 5)
    print(max([r["it"] for r in rows if r.get("event") == "iter" and r["it"] % 5 == 0], default=0))
else:
    print(" ".join(r["version"] for r in rows if r.get("event") == "freeze" and r["version"] != "v0"))
PY
}
resume() { "$M/reports/r28_2026-11-12/start.sh" >> "$LOG" 2>&1; say "r28 resumed: $1"; }

say "watching for the gate at 400 (PIN $PIN)"
until [ "$(row gate)" -ge 400 ]; do
  systemctl --user is-active -q mtg-r28 || { say "r28 is not running before its gate at 400: nothing done"; exit 1; }
  sleep 60
done
m0=$(stat -c %Y "$RUN/last.pt")
say "gate at 400 logged (row $(row gate)); waiting for the next save"
while [ "$(stat -c %Y "$RUN/last.pt")" = "$m0" ]; do
  systemctl --user is-active -q mtg-r28 || { say "r28 stopped before its next save: nothing done"; exit 1; }
  sleep 10
done
sleep 10  # the save finishes writing
systemctl --user stop mtg-r28
it=$(row save)
cp "$RUN/last.pt" "$LOOKS/r28_u$it.pt"
say "r28 paused after its save at $it; kept as r28_u$it.pt $(sha256sum "$LOOKS/r28_u$it.pt" | cut -c1-16)"

# the per-kind split's batch (199 §7), fresh deals (seed 2840; the look at 100 used 2800)
timeout 45m "$M/reports/r28_2026-11-12/collect.sh" "$LOOKS/r28_u$it.pt" "$LOOKS/c400" 2840 \
  > "$LOOKS/c400.out" 2>&1
say "collect exit $?"

later=$(row freeze)
if [ -n "$later" ]; then
  resume "versions frozen after v0 ($later): the rate needs the ladder's fit, decided by hand"
  exit 0
fi
head=$(git -C "$GW" rev-parse HEAD)
if [ "$head" != "$PIN" ]; then
  resume "gate B's worktree is at $head, not $PIN: not started"
  exit 0
fi
say "no version frozen after v0: rate 0, s* 0.5 <= 0.53, generation runs (196 §9); starting gate B"
systemd-run --user --unit mtg-gateb --setenv=PYTHONDONTWRITEBYTECODE=1 /bin/bash \
  "$GW/reports/gate_b_2026-11-12/queue.sh" >> "$LOG" 2>&1
say "mtg-gateb start exit $?"
