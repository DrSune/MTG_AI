#!/bin/bash
# The ceiling-read window (docs/PLAN_CEILING.md §14.1, §14.4, §14.5 as amended 2026-11-13; its
# registration: reports/ceiling_window/REGISTRATION_DRAFT.md, then a KNOWLEDGE note), as a pause
# in r28. Every deal is played twice with the seats swapped, greedy, M21, the verified pool.
# 1. The skill spread per deck distribution of NET, r28's latest network: coherent, package
#    (--package-share 1.0) and critic-drafted (drafted:8 on 193's critic). (a) NET searched at
#    n = 4 (192 §9's anchor n, window 1's search) against NET raw; (b) NET against the heuristic.
# 2. The held-out pool L (§7.2, §14.4): its members' games, every pairing on every deal shape,
#    for its frozen ratings (rate.py fit).
# 3. NET against two of L's members, to rate it on L (rate.py rate).
# One GPU job at a time, in the order below; every job has a time cap; a finished job (its .done
# file) is skipped on a restart; a job that fails or hits its cap is logged and the queue goes on.
# It refuses to start while mtg-r28 is active or a process holds the GPU, never starts r28 itself,
# and ends by printing how to resume it. Runs from a worktree pinned at the commit that holds this
# file, with the main checkout's .venv linked in:
#   git worktree add --detach /home/sune/Desktop/MTG_AI-cw <commit>
#   ln -s /home/sune/Desktop/MTG_AI/.venv /home/sune/Desktop/MTG_AI-cw/.venv
#   systemctl --user stop mtg-r28  # right after a save (state.pkl's mtime): no update is lost
#   mkdir -p /home/sune/Desktop/MTG_AI/runs/ceiling_window
#   cp /home/sune/Desktop/MTG_AI/runs/selfplay/r28_stratified_ppo/last.pt \
#     /home/sune/Desktop/MTG_AI/runs/ceiling_window/r28_latest.pt
#   systemd-run --user --unit mtg-ceiling /bin/bash \
#     /home/sune/Desktop/MTG_AI-cw/reports/ceiling_window/queue.sh
# NET overrides the network's path. SMOKE=1 plays every job on the CPU with 2 deals and 2
# workers into $O, beside a running r28 (W, O and NET set by the caller).
set -u
W=${W:-/home/sune/Desktop/MTG_AI-cw}
ROOT=/home/sune/Desktop/MTG_AI
R=$ROOT/runs
O=${O:-$R/ceiling_window}
NET=${NET:-$O/r28_latest.pt}
SMOKE=${SMOKE:-0}
CRITIC=$R/window2/critic_r27.json  # 193's v0 critic, content sha256 6b8014ae…
R26V0=$R/selfplay/r26_outcome_ppo/v0.pt     # also r23's network (r23_mulligan/gen.pt, same weights)
R26V1=$R/selfplay/r26_outcome_ppo/v1.pt
R26V2=$R/selfplay/r26_outcome_ppo/v2.pt
U1000=$R/selfplay/r26_outcome_ppo/u1000.pt  # also r27's v0 (the same network once loaded)
R27V1=$R/selfplay/r27_priority_ppo/v1.pt    # also r28's v0 (the same weights)
B_MIN=0.65  # NET against the heuristic below this on coherent decks: the setup is broken, stop
CR0=1100000  # the ceiling read's deals, every shape: (a) the first A or A_DRAFTED, (b) the first B
L0=1110000   # L's deals, every pairing and shape
N0=1120000   # NET's games against L's members
if [ "$SMOKE" = 1 ]; then
  A=2 A_DRAFTED=2 B=2 LD=2 LD_SV=2 ND=2 B_MIN=0
  HW="--device cpu --workers 2 --slots 2 --groups 1"
  export CUDA_VISIBLE_DEVICES=
else
  A=1500 A_DRAFTED=1000 B=2000 LD=300 LD_SV=200 ND=300
  HW="--workers 18 --slots 16 --groups 4"
fi
cd "$W" || exit 1
export PYTHONDONTWRITEBYTECODE=1 PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
mkdir -p "$O"
exec 9> "$O/lock"  # one queue per output directory: a second one would replay its jobs
flock -n 9 || { echo "another queue holds $O" >&2; exit 1; }
log() { echo "{\"t\": $(date +%s), \"step\": \"$1\", \"what\": \"$2\"}" >> "$O/queue.log"; }
refuse() { echo "$1" >&2; log window "refused: $1"; exit 1; }
resume_note() {
  echo "resume r28: $W/reports/r28_2026-11-12/start.sh"
  log r28 "resume it: $W/reports/r28_2026-11-12/start.sh"
}

if [ "$SMOKE" != 1 ]; then
  systemctl --user is-active -q mtg-r28 && refuse "mtg-r28 is active: systemctl --user stop mtg-r28"
  gpu=$(nvidia-smi --query-compute-apps=pid,process_name --format=csv,noheader 2>&1)
  [ -z "$gpu" ] || refuse "the GPU is not free: $gpu"
  [ -z "$(git -C "$W" status --porcelain)" ] || refuse "$W is not a clean checkout"
fi
id=$(git -C "$W" rev-parse HEAD)
[ -f "$O/identity" ] && [ "$(cat "$O/identity")" != "$id" ] && \
  refuse "$O began at $(cat "$O/identity"), this queue is $id"
echo "$id" > "$O/identity"
[ -f "$NET" ] || refuse "no network at NET=$NET"
net=$(sha256sum < "$NET" | cut -c1-64)
[ -f "$O/net.sha256" ] && [ "$(cat "$O/net.sha256")" != "$net" ] && \
  refuse "NET differs from the network this window began with ($O/net.sha256)"
echo "$net" > "$O/net.sha256"
for f in "$CRITIC" "$R26V0" "$R26V1" "$R26V2" "$U1000" "$R27V1"; do  # pinned: L stays fixed
  want=$(awk -v p="${f#"$ROOT"/}" '$2 == p {print $1; exit}' "$W/reports/LARGE_FILES.sha256")
  [ -n "$want" ] && [ "$(sha256sum < "$f" | cut -c1-64)" = "$want" ] || \
    refuse "$f differs from its pin in reports/LARGE_FILES.sha256"
done
it=$(.venv/bin/python -c "import sys, torch
print(torch.load(sys.argv[1], map_location='cpu', weights_only=False)['extra'].get('it'))" "$NET")
log window "start at $id; NET $NET, update $it, sha256 ${net:0:16}"

step() {  # step NAME CAP COMMAND...
  local name=$1 cap=$2; shift 2
  [ -f "$O/$name.done" ] && return 0
  [ "$SMOKE" = 1 ] && cap=60m
  log "$name" start
  timeout -k 5m "$cap" "$@" > "$O/$name.out" 2>&1
  local rc=$?
  [ $rc -eq 0 ] && touch "$O/$name.done"
  log "$name" "exit $rc"
}
GAME="--refresh-table --extend-sets M20 --pool verified --coherent-share 1.0 --infer-bf16 \
  --eval-set M21 --eval-only $HW"
SEARCH="--search-root gumbel --search-m 16 --search-n 4"
shape_flags() {
  case $1 in
    coherent) ;;
    package) echo "--package-share 1.0" ;;
    drafted) echo "--eval-decks drafted:8 --draft-critic $CRITIC" ;;
  esac
}
play() {  # play NAME SHAPE CAP DEALS SEED0 INIT [learner flags...]: one job, run NAME_SHAPE
  local name=$1 shape=$2 cap=$3 deals=$4 seed0=$5 init=$6; shift 6
  step "${name}_$shape" "$cap" .venv/bin/python -m tools.selfplay.learner \
    --run "$O/${name}_$shape" --init "$init" $GAME $(shape_flags "$shape") \
    --eval-deals "$deals" --eval-seed0 "$seed0" "$@"
}
search_vs_raw() { play a "$1" "$2" "$3" "$CR0" "$NET" --eval-seat eval+search \
  --eval-opponents snap:opp --opp-ckpt "$NET" $SEARCH --search-record; }
vs_heuristic() { play b "$1" 20m "$B" "$CR0" "$NET" --eval-seat eval --eval-opponents heuristic; }

# 1. The ceiling read. (b) on coherent decks first: a sanity check of the setup in 4 minutes.
vs_heuristic coherent
b_score=$(.venv/bin/python - "$O/b_coherent/metrics.jsonl" <<'PY'
import json, os, sys
rows = [json.loads(x) for x in open(sys.argv[1])] if os.path.exists(sys.argv[1]) else []
ev = [r for r in rows if r.get("event") == "eval"]
print(ev[-1]["heuristic"]["score"] if ev else 0)
PY
)
if awk -v s="$b_score" -v m="$B_MIN" 'BEGIN { exit !(s < m) }'; then
  log window "stopped: NET scored $b_score against the heuristic on coherent decks, below $B_MIN"
  resume_note
  exit 1
fi
search_vs_raw coherent 100m "$A"
search_vs_raw package 110m "$A"
vs_heuristic package
search_vs_raw drafted 70m "$A_DRAFTED"
vs_heuristic drafted

# 2. L. Members: random (Elo 0), the heuristic, r26's v0 (r23's network), v1 and v2, u1000
# (r27's v0), u1000 searched at n = 4 (§7.2: r27's v0 plus search at the anchor's n), r27's v1
# (r28's v0). Each job is one init against each of its opponents, on every deal shape.
for shape in coherent package drafted; do
  play L_r26v0 "$shape" 15m "$LD" "$L0" "$R26V0" --eval-opponents heuristic,random
  play L_r26v1 "$shape" 15m "$LD" "$L0" "$R26V1" --eval-opponents snap:opp,heuristic,random \
    --opp-ckpt "$R26V0"
  play L_r26v2 "$shape" 15m "$LD" "$L0" "$R26V2" --eval-opponents snap:opp,heuristic \
    --opp-ckpt "$R26V1"
  play L_r26v2-r26v0 "$shape" 15m "$LD" "$L0" "$R26V2" --eval-opponents snap:opp \
    --opp-ckpt "$R26V0"
  play L_u1000 "$shape" 15m "$LD" "$L0" "$U1000" --eval-opponents snap:opp,heuristic,random \
    --opp-ckpt "$R26V2"
  play L_r27v1 "$shape" 15m "$LD" "$L0" "$R27V1" --eval-opponents snap:opp,heuristic \
    --opp-ckpt "$U1000"
  play L_r27v1-r26v2 "$shape" 15m "$LD" "$L0" "$R27V1" --eval-opponents snap:opp \
    --opp-ckpt "$R26V2"
  # the heuristic against random: the init is loaded, unused
  play L_heuristic "$shape" 15m "$LD" "$L0" "$U1000" --eval-seat heuristic \
    --eval-opponents random
done
for shape in coherent package drafted; do
  play L_u1000s4-u1000 "$shape" 30m "$LD" "$L0" "$U1000" --eval-seat eval+search \
    --eval-opponents snap:opp --opp-ckpt "$U1000" $SEARCH
  play L_u1000s4-r27v1 "$shape" 25m "$LD_SV" "$L0" "$U1000" --eval-seat eval+search \
    --eval-opponents snap:opp --opp-ckpt "$R27V1" $SEARCH
done

# 3. NET on L, against the two members nearest it
for shape in coherent package drafted; do
  play rate_r27v1 "$shape" 10m "$ND" "$N0" "$NET" --eval-opponents snap:opp --opp-ckpt "$R27V1"
  play rate_u1000 "$shape" 10m "$ND" "$N0" "$NET" --eval-opponents snap:opp --opp-ckpt "$U1000"
done

env PYTHONPATH=. .venv/bin/python reports/ceiling_window/score.py "$O" > "$O/score.txt" 2>&1
log score "exit $?: $O/score.txt"
log window done
resume_note
