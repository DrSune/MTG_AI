#!/usr/bin/env bash
# r1_window.sh — R1 GPU window, OWNER-AUTHORIZED (KNOWLEDGE/2026-10-19/130 §2):
# owner 2026-10-19: "Yes use the GPU... swap out and swap in, in one script, since you
# cannot fix it while you are away... or hand this off to a tmux session you give the
# responsibility to deal with it." AGENTS.md engine-law DEVIATION RECORD: this detached
# tmux script (NOT any live agent session) runs docker stop/start of qwen-nvfp4 tonight;
# engine restart is trap-guaranteed on EXIT/ERR/INT/TERM. Spec: /130 §2 + /85 + /87 + /80.
set -Eeuo pipefail

# ------------------------------------------------------------------ config
REPO=/home/sune/Desktop/MTG_AI
VENV="$REPO/.venv/bin/python"
ENGINE=qwen-nvfp4
GATEWAY=http://127.0.0.1:8000/v1/models   # gateway process (host python3, survives stop)
PLUGIN_LOG="$HOME/.local/share/opencode/log/opencode.log"
SRC=/tmp/opencode/r1_train_src            # clean git-archive export
LANE=/tmp/opencode/r1_window              # this window's /tmp working dir
LANE128=/tmp/opencode/znr_eval_lane       # /128 meter lane (cert2/episodes_znr)
RUNLOG="$REPO/reports/r1_window_run.log"
EPISODES_BIG="$REPO/tools/training/episodes_champ_big.jsonl"   # 29M, /130 spec
DUEL_REF="$REPO/tools/training/bsh_S3a_s3_best.pt"             # frozen frontier (/80)
SEED_FILE="$REPO/reports/monitoring/duel_seeds.json"           # D9 bank, live repo
SEEDS=(1 2 3)
ARM_TIMEOUT=7200            # per-arm watchdog (run_train --timeout), /130 2h/arm guard
DUEL_RATE_TENTHS=4          # games/min per WORKER x10 (=0.4): conservative CPU-duel
                            # estimate. ASSUMPTION logged in ledger — no measured CPU
                            # BC-duel throughput on record (/83's ~10min/game was search).
DUEL_WORKERS=4              # spec cap
DUEL_MIN_GAMES=24
DUEL_MAX_GAMES=200

START_AT=23:59
RESTART_AT=07:00
DRY=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --start-at)   START_AT=$2; shift 2 ;;
    --restart-at) RESTART_AT=$2; shift 2 ;;
    --dry-run)    DRY=1; shift ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

TODAY=$(date +%F)
if [[ $DRY -eq 1 ]]; then
  LEDGER="$REPO/reports/r1_window_dryrun.md"   # SCRATCH: never the real ledger/NUMBERS
else
  LEDGER="$REPO/reports/r1_window_${TODAY}.md"
fi

START_E=$(date -d "today $START_AT" +%s)
RESTART_E=$(date -d "today $RESTART_AT" +%s)
[[ $RESTART_E -le $START_E ]] && RESTART_E=$((RESTART_E + 86400))

ENGINE_STOPPED=0
RESTORED=0
ARMS_DONE=()

log() { echo "[$(date '+%F %T')] $*" | tee -a "$RUNLOG"; }
avail_mib() { awk '/MemAvailable/{print $2}' /proc/meminfo; }
gw_code() {   # HTTP code of the gateway models endpoint; 000 = connection refused/gone
  local c
  c=$(curl -s -m 3 -o /dev/null -w '%{http_code}' "$GATEWAY" 2>/dev/null) || true
  echo "${c:-000}"
}

# ------------------------------------------------- engine swap (dry-guarded)
swap_out() {
  local before after code=000
  before=$(avail_mib)
  if [[ $DRY -eq 1 ]]; then
    log "[DRY] would: docker stop -t 30 $ENGINE (engine left running — live agents need it)"
    ENGINE_STOPPED=1   # exercise the trap path; the restore branch echoes in dry mode
    return 0
  fi
  log "docker stop -t 30 $ENGINE ..."
  ENGINE_STOPPED=1     # set BEFORE the stop: any crash mid-swap still triggers restore
  docker stop -t 30 "$ENGINE" >>"$RUNLOG" 2>&1
  for _ in $(seq 1 30); do
    code=$(gw_code)
    [[ $code != 200 ]] && break
    sleep 2
  done
  after=$(avail_mib)
  log "engine-down verified: gateway /v1/models http=$code (expected !=200); MemAvailable ${before}->${after} KiB (delta $(( (after-before)/1024 )) MiB). /87: GPU alloc IS system memory — freeing ~100GiB is the swap's whole purpose."
}

wait_healthy() {
  local deadline=$(( $(date +%s) + 2400 ))   # 40 min cap
  while [[ $(date +%s) -lt $deadline ]]; do
    [[ $(gw_code) == 200 ]] && return 0
    sleep 10
  done
  return 1
}

plugin_log_check() {
  if [[ -f $PLUGIN_LOG ]]; then
    local n
    n=$(tail -n 5000 "$PLUGIN_LOG" | grep -c "failed to load plugin" || true)
    log "/94 plugin-log-check: 'failed to load plugin' in last 5000 log lines: $n"
  else
    log "/94 plugin-log-check: $PLUGIN_LOG absent — check skipped, noted"
  fi
}

restore_engine() {
  if [[ $DRY -eq 1 ]]; then
    log "[DRY] would: docker start $ENGINE + wait-healthy(<=40min) + plugin-log-check"
    RESTORED=1
    return 0
  fi
  log "docker start $ENGINE ..."
  docker start "$ENGINE" >>"$RUNLOG" 2>&1 || log "WARN: docker start returned nonzero"
  if wait_healthy; then
    log "gateway healthy again: $GATEWAY -> 200"
  else
    log "CRITICAL: gateway not 200 within 40 min of docker start — inspect: docker logs $ENGINE"
  fi
  plugin_log_check
  RESTORED=1
}

cleanup() {
  set +e
  if [[ $ENGINE_STOPPED -eq 1 ]]; then
    ENGINE_STOPPED=0
    log "=== RESTORE TRAP FIRED (abnormal exit path) — restoring engine ==="
    restore_engine
  fi
  if [[ $RESTORED -eq 1 ]]; then
    log "=== engine restored — attach tmux -r -t r1window to read ledger ($LEDGER) ==="
  else
    log "=== window ended WITHOUT any engine swap (nothing to restore) ==="
  fi
}
trap cleanup EXIT
trap 'log "ERR: command failed at line $LINENO (rc=$?)"; exit 1' ERR
trap 'log "SIGINT received"; exit 1' INT
trap 'log "SIGTERM received"; exit 143' TERM

# ------------------------------------- preflight: fail => abort, restart-NOTHING
preflight() {
  log "--- preflight ---"
  log "HEAD: $(git -C "$REPO" rev-parse --short HEAD)  dirty-porcelain-lines: $(git -C "$REPO" status --porcelain | wc -l)  (dirty is LOGGED not aborted: training runs from a clean git-archive export)"
  local missing=0 f
  for f in tools/training/train_bc_v3.py tools/training/run_train.py \
           tools/training/ab_duel.py tools/training/eval_ckpt.py \
           tools/eval/holdout_report.py tools/ops/r1_ledger.py \
           tools/training/bsh_S3a_s3_best.pt reports/monitoring/duel_seeds.json \
           tools/training/episodes_v2.jsonl tools/audit/puzzle_corpus.json; do
    [[ -f "$REPO/$f" ]] || { log "MISSING required file: $f"; missing=1; }
  done
  [[ -s $EPISODES_BIG ]] || { log "MISSING episodes file: $EPISODES_BIG"; missing=1; }
  log "episodes_champ_big.jsonl size: $(du -h "$EPISODES_BIG" 2>/dev/null | cut -f1) (expect ~29M)"
  docker inspect "$ENGINE" --format 'container: {{.Name}} state={{.State.Status}}' \
    >>"$RUNLOG" 2>&1 || { log "MISSING container $ENGINE"; missing=1; }
  log "free -m: $(free -m | awk '/^Mem:/{print "total="$2"M used="$3"M available="$7"M"}')  (/87 unified-memory reality: engine footprint ~100GiB charges system memory)"
  log "gateway now: http=$(gw_code) (expected 200 — engine currently serving agents)"
  [[ $missing -eq 0 ]] || { log "PREFLIGHT FAIL — aborting; nothing touched (restart-nothing per /130 §2)"; exit 3; }
  log "preflight PASS"
}

wait_start() {
  log "window armed: START=$START_AT  HARD-RESTART=$RESTART_AT  dry-run=$DRY"
  while [[ $(date +%s) -lt $START_E ]]; do
    local rem
    rem=$(( START_E - $(date +%s) ))
    log "HEARTBEAT: waiting for start, ${rem}s remaining (engine up, agents live)"
    sleep $(( rem < 300 ? rem : 300 ))
  done
  log "START_AT reached"
}

clean_export() {
  rm -rf "$SRC"
  mkdir -p "$SRC"
  git -C "$REPO" archive HEAD | tar -x -C "$SRC"
  log "clean export: git archive HEAD ($(git -C "$REPO" rev-parse --short HEAD)) -> $SRC"
}

# ------------------------------------------------------------- training arms
train_arms() {
  local seed rc f base
  for seed in "${SEEDS[@]}"; do
    if [[ -f "$REPO/tools/training/r1_S4_s${seed}_report.json" ]]; then
      log "seed $seed: r1_S4_s${seed}_report.json already in repo — SKIP (idempotent re-run)"
      ARMS_DONE+=("$seed")
      continue
    fi
    local margin
    margin=$(( RESTART_E - $(date +%s) ))
    if [[ $margin -lt $(( ARM_TIMEOUT + 2700 )) ]]; then
      log "RESTART_AT deadline guard: only ${margin}s to hard restart (< ${ARM_TIMEOUT}s arm guard + 45min eval/restore margin) — ABORTING remaining arms honestly"
      return 0
    fi
    log "=== ARM r1_S4_s${seed}: run_train watchdog ${ARM_TIMEOUT}s, device auto -> cuda (engine down), default long epochs (250/patience60), owner: see how far it goes ==="
    set +e
    ( cd "$SRC" && "$VENV" run_train.py \
        --phase "r1-r1_S4_s${seed}" --timeout "$ARM_TIMEOUT" --ignore-prev \
        -- "$VENV" -m tools.training.train_bc_v3 \
             --arm S4 --seed "$seed" --prefix "r1_S4_s${seed}" \
             --episodes "$EPISODES_BIG" --fresh ) >>"$RUNLOG" 2>&1
    rc=$?
    set -e
    case $rc in
      0)   log "seed $seed: complete rc=0" ;;
      124) log "seed $seed: TIMEOUT at ${ARM_TIMEOUT}s guard (best.pt = pre-final); long-run respected" ;;
      *)   log "seed $seed: run_train rc=$rc (cause recorded in export reports/training_runs.jsonl)" ;;
    esac
    for f in "r1_S4_s${seed}.pt" "r1_S4_s${seed}_best.pt" "r1_S4_s${seed}_report.json"; do
      base=$SRC/tools/training/$f
      if [[ -f $base ]]; then
        cp "$base" "$REPO/tools/training/" && log "copied back $f"
      else
        log "seed $seed: no $f produced"
      fi
    done
    [[ -f $REPO/tools/training/r1_S4_s${seed}_best.pt ]] && ARMS_DONE+=("$seed")
  done
  cp -f "$SRC/reports/training_runs.jsonl" "$REPO/reports/r1_window_training_runs.jsonl" \
    2>/dev/null || log "no export training_runs.jsonl to copy"
}

# ------------------------------------------- meter lane (/128 §3 patched recipe)
write_lane_scripts() {
  # Parameterized copies of /tmp/opencode/znr_eval_lane/{cert_run,record_znr,meter_patched}.py
  # (R1_REPO env picks the frozen-corpus root = clean export; used only if lane
  #  artifacts are missing — otherwise /128's cert2.json + episodes_znr.jsonl reused).
  mkdir -p "$LANE"
  cat > "$LANE/cert_r1.py" <<'PY'
"""Re-certify ZNR eval packs -> /128 lane cert2.json (recipe: /128 cert_run.py)."""
import json, os, sys
from pathlib import Path
REPO = Path(os.environ["R1_REPO"]); sys.path.insert(0, str(REPO))
LANE = Path("/tmp/opencode/znr_eval_lane")
from tools.audit import puzzle_cert as pc
from MTG_bot.core.executor.games import get_supply
supply = get_supply("all", "ZNR")
rows = []
for path in sorted((REPO / "tools/scenarios").glob("znr_eval_*.json")):
    pack = json.loads(path.read_text())
    items = pc.certify_pack(path, pack, supply, rollouts=200)
    for it in items:
        it = dict(it); it["label"] = f"{path.stem}:step{it['step']}:{it['ask_kind']}"
        rows.append(it)
    print(path.stem, "->", len(items), "items", flush=True)
json.dump(rows, open(LANE / "cert2.json", "w"), indent=1)
print("TOTAL ITEMS", len(rows))
PY
  cat > "$LANE/record_r1.py" <<'PY'
"""Record packrec ZNR eval-pack episodes -> /128 lane (recipe: /128 record_znr.py)."""
import json, os, shutil, sys
from pathlib import Path
REPO = Path(os.environ["R1_REPO"]); sys.path.insert(0, str(REPO))
LANE = Path("/tmp/opencode/znr_eval_lane")
import tools.training.packrec as packrec
from MTG_bot.core.executor.games import get_supply
shutil.copytree(REPO / "tools/scenarios", LANE / "packs", dirs_exist_ok=True)
supply = get_supply("all", "ZNR")
eps = packrec.record_dir(LANE / "packs", supply)
with (LANE / "episodes_znr.jsonl").open("w", encoding="utf-8") as fh:
    for ep in eps:
        fh.write(json.dumps(ep, sort_keys=True) + "\n")
print("recorded episodes:", len(eps))
PY
  cat > "$LANE/meter_r1.py" <<'PY'
"""Patched /128 set-split meter on checkpoints argv[1:]. fresh=ZNR.
Exact /128 §3 recipe: frozen 199-item corpus + ZNR cert items joined via /tmp
copies of puzzle_corpus.json / episodes_v2.jsonl; card_sets() extended with the
ZNR names; score()/bootstrap UNCHANGED. Checkpoints never saw ZNR -> the fresh
side is TRUE set-level generalization (n=10: direction, not magnitude)."""
import json, os, sys
from pathlib import Path
REPO = Path(os.environ["R1_REPO"]); sys.path.insert(0, str(REPO))
LANE = Path("/tmp/opencode/znr_eval_lane")
frozen = json.loads((REPO / "tools/audit/puzzle_corpus.json").read_text())
cert = json.loads((LANE / "cert2.json").read_text())
znr_items = [{k: v for k, v in it.items() if k != "label"} for it in cert]
patched = dict(frozen)
patched["items"] = frozen["items"] + znr_items
patched["header"] = dict(frozen.get("header", {}))
patched["header"]["lane_note"] = ("PATCHED LANE (R1 window, /128 §3 recipe): frozen "
    "199 M21 items + ZNR cert items on /tmp copies; shared corpus untouched.")
(LANE / "corpus_patched.json").write_text(json.dumps(patched, indent=1))
znr_names = sorted({it["card"] for it in znr_items})
(LANE / "episodes_patched.jsonl").write_text(
    (REPO / "tools/training/episodes_v2.jsonl").read_text()
    + (LANE / "episodes_znr.jsonl").read_text())
import tools.training.train_bc_v3 as t3
from tools.eval import holdout_report as hr
t3.CORPUS = LANE / "corpus_patched.json"
t3.EPISODES = LANE / "episodes_patched.jsonl"
_orig = hr.card_sets
def card_sets_patched():
    out = _orig()
    for n in znr_names:
        out[n] = "ZNR"
    return out
hr.card_sets = card_sets_patched
hr.__dict__["card_sets"] = card_sets_patched
rc = hr.main(["--ckpts", ",".join(sys.argv[1:]), "--split", "set",
              "--fresh-sets", "ZNR", "--out", str(LANE / "holdout_r1.json")])
rep = json.loads((LANE / "holdout_r1.json").read_text())
rep["lane_note"] = ("PATCHED LANE /128 §3 (regenerated R1 window): fresh side = TRUE "
    "set-level generalization; n=10 fresh items — direction, not magnitude.")
(LANE / "holdout_r1.json").write_text(json.dumps(rep, indent=1))
for r in rep["results"]:
    print(r["ckpt"], "seen", r["seen"]["acc"], "fresh", r["fresh"]["acc"],
          "GAP", r["gap"], "+-", r["gap_boot_se"], "CI", r["gap_ci95"])
sys.exit(rc)
PY
}

run_evals() {
  local seed ck
  if [[ ${#ARMS_DONE[@]} -eq 0 ]]; then
    log "evals: ZERO arms completed — nothing to evaluate (ledger records this honestly)"
    return 0
  fi
  # (a) eval_ckpt gates (universal-gate score of best checkpoints, CPU torch)
  for seed in "${ARMS_DONE[@]}"; do
    ck="$REPO/tools/training/r1_S4_s${seed}_best.pt"
    log "gate eval: eval_ckpt $ck --device cpu"
    ( cd "$SRC" && timeout 3600 "$VENV" -m tools.training.eval_ckpt "$ck" --device cpu ) \
      > "$REPO/reports/r1_gate_s${seed}.json" 2>>"$RUNLOG" \
      || log "gate eval seed $seed: nonzero rc / 1h timeout (partial json as-is)"
  done
  # (b) /128 set-split generalization meter (fresh=ZNR), patched lane
  mkdir -p "$LANE128/packs"
  if [[ ! -f $LANE128/cert2.json ]]; then
    log "meter lane: cert2.json absent — regenerating per /128 (certify_pack rollouts=200)"
    ( cd "$SRC" && R1_REPO="$SRC" timeout 5400 "$VENV" "$LANE/cert_r1.py" ) >>"$RUNLOG" 2>&1 \
      || log "meter lane: cert regeneration FAILED — meter will be skipped"
  fi
  if [[ -f $LANE128/cert2.json && ! -f $LANE128/episodes_znr.jsonl ]]; then
    log "meter lane: episodes_znr.jsonl absent — regenerating per /128 (packrec.record_dir)"
    ( cd "$SRC" && R1_REPO="$SRC" timeout 5400 "$VENV" "$LANE/record_r1.py" ) >>"$RUNLOG" 2>&1 \
      || log "meter lane: packrec regeneration FAILED"
  fi
  if [[ -f $LANE128/cert2.json && -f $LANE128/episodes_znr.jsonl ]]; then
    local ck_args=()
    for seed in "${ARMS_DONE[@]}"; do
      ck_args+=("$REPO/tools/training/r1_S4_s${seed}_best.pt")
    done
    log "meter: /128 set-split fresh=ZNR on seeds ${ARMS_DONE[*]}"
    ( cd "$SRC" && R1_REPO="$SRC" timeout 5400 "$VENV" "$LANE/meter_r1.py" "${ck_args[@]}" ) \
      >>"$RUNLOG" 2>&1 || log "meter run: nonzero rc / timeout"
    [[ -f $LANE128/holdout_r1.json ]] \
      && cp "$LANE128/holdout_r1.json" "$REPO/reports/r1_meter_znr_${TODAY}.json" \
      && log "meter JSON copied to reports/r1_meter_znr_${TODAY}.json"
  else
    log "meter lane artifacts unavailable — meter SKIPPED (honest nil)"
  fi
  # (c) duels vs frozen frontier bsh_S3a_s3_best (reference band 0.39-0.43, /83)
  local n=${#ARMS_DONE[@]}
  local budget_min per_min games
  budget_min=$(( (RESTART_E - 2700 - $(date +%s)) / 60 ))   # 45-min restore margin
  if [[ $budget_min -le 0 ]]; then
    log "duels: RESTART_AT minus 45min margin already past — duels SKIPPED honestly"
    return 0
  fi
  per_min=$(( budget_min / (n > 0 ? n : 1) ))
  games=$(( per_min * DUEL_WORKERS * DUEL_RATE_TENTHS / 10 ))
  games=$(( games < DUEL_MIN_GAMES ? DUEL_MIN_GAMES : games ))
  games=$(( games > DUEL_MAX_GAMES ? DUEL_MAX_GAMES : games ))
  log "duel sizing: ${budget_min} budget-min / ${n} duel(s), rate 0.${DUEL_RATE_TENTHS} g/min/worker x ${DUEL_WORKERS} workers (ASSUMPTION, logged) -> ${games} games/duel, device cpu, ref=$DUEL_REF"
  for seed in "${ARMS_DONE[@]}"; do
    ck="$REPO/tools/training/r1_S4_s${seed}_best.pt"
    log "duel: r1_S4_s${seed} vs bsh_S3a_s3 (${games}g, ${DUEL_WORKERS} cpu workers)"
    ( cd "$SRC" && "$VENV" -m tools.training.ab_duel \
        --a "$ck" --b "$DUEL_REF" --games "$games" --workers "$DUEL_WORKERS" \
        --device cpu --seed-file "$SEED_FILE" \
        --out "$REPO/reports/r1_duel_s${seed}.json" ) >>"$RUNLOG" 2>&1 \
      || log "duel seed $seed: nonzero rc (partial results per json)"
    [[ $EPOCHSECONDS -gt $((RESTART_E - 1800)) ]] && { log "duel loop: RESTART margin hit — stopping remaining duels honestly"; break; }
  done
}

write_ledger() {
  local L="$LANE/r1_ledger.py"
  log "ledger append -> $LEDGER"
  {
    echo ""
    echo "## R1 window run — $(date '+%F %T') (dry-run=$DRY, HEAD $(git -C "$REPO" rev-parse --short HEAD))"
    echo ""
    echo "Commands (exact): per seed $VENV run_train.py --phase r1-r1_S4_s<N> --timeout $ARM_TIMEOUT --ignore-prev -- $VENV -m tools.training.train_bc_v3 --arm S4 --seed <N> --prefix r1_S4_s<N> --episodes $EPISODES_BIG --fresh; then eval_ckpt.py <best.pt> --device cpu; /128 patched meter (--split set --fresh-sets ZNR); ab_duel.py --a <best.pt> --b $DUEL_REF --workers $DUEL_WORKERS --device cpu --seed-file $SEED_FILE"
    echo ""
    echo "| lane | subject | result | gate/CI | extra |"
    echo "|---|---|---|---|---|"
  } >> "$LEDGER"
  for seed in "${SEEDS[@]}"; do
    if [[ $DRY -eq 0 && ! -f $REPO/tools/training/r1_S4_s${seed}_best.pt ]]; then
      echo "| train | r1_S4_s${seed} | NO checkpoint/report (arm aborted or failed) | - | - |" >> "$LEDGER"
    fi
  done
  for seed in "${ARMS_DONE[@]}"; do
    $VENV "$L" table-train "$REPO/tools/training/r1_S4_s${seed}_report.json" "see-runlog" \
      >> "$LEDGER" 2>/dev/null || echo "| train | r1_S4_s${seed} | report unreadable | - | - |" >> "$LEDGER"
    [[ -f $REPO/reports/r1_gate_s${seed}.json ]] && \
      $VENV "$L" table-gate "$REPO/reports/r1_gate_s${seed}.json" >> "$LEDGER" 2>/dev/null
    [[ -f $REPO/reports/r1_duel_s${seed}.json ]] && \
      $VENV "$L" table-duel "$REPO/reports/r1_duel_s${seed}.json" >> "$LEDGER" 2>/dev/null
  done
  [[ -f $REPO/reports/r1_meter_znr_${TODAY}.json ]] && \
    $VENV "$L" table-meter "$REPO/reports/r1_meter_znr_${TODAY}.json" >> "$LEDGER" 2>/dev/null
  if [[ $DRY -eq 0 ]]; then
    local duel_args=()
    for seed in "${ARMS_DONE[@]}"; do
      [[ -f $REPO/reports/r1_duel_s${seed}.json ]] && duel_args+=("$REPO/reports/r1_duel_s${seed}.json")
    done
    $VENV "$L" numbers "${REPO}/reports/r1_meter_znr_${TODAY}.json" ${duel_args[@]+"${duel_args[@]}"} \
      >> "$REPO/KNOWLEDGE/NUMBERS.md" 2>/dev/null || \
      echo "- R1 WINDOW $(date +%F) (/130 §2): ledger helper failed — see $LEDGER" >> "$REPO/KNOWLEDGE/NUMBERS.md"
    log "NUMBERS.md appended (knowledge law: number+date+command)"
  else
    log "dry-run: NUMBERS.md NOT touched (scratch ledger only)"
  [[ -f $LANE/smoke/gate_smoke.json ]] && { \
    $VENV "$L" table-gate "$LANE/smoke/gate_smoke.json" >> "$LEDGER" 2>/dev/null \
      || echo "| gate | smoke | dry-run eval_ckpt incomplete | - | - |" >> "$LEDGER"; }
  $VENV "$L" table-train "$LANE/smoke/r1_smoke_report.json" "dry-smoke" \
    >> "$LEDGER" 2>/dev/null || echo "| train | r1_smoke | smoke incomplete | - | - |" >> "$LEDGER"
  fi
}

# ------------------------------------------------------------ dry-run smoke
dry_smoke() {
  local ep
  for ep in episodes_champ.jsonl episodes_champ2.jsonl episodes_champ3.jsonl; do
    [[ -s "$SRC/tools/training/$ep" ]] && break || ep=""
  done
  [[ -n $ep ]] || { log "[DRY] no small episodes file in export — smoke SKIPPED"; return 0; }
  log "[DRY] training REPLACED by one fast CPU smoke: train_bc_v3 S0 2 epochs seed 99 on $ep ($(du -h "$SRC/tools/training/$ep" | cut -f1))"
  mkdir -p "$LANE/smoke" "$LANE/artifacts"
  ( cd "$SRC" && timeout 1500 "$VENV" -m tools.training.train_bc_v3 \
      --arm S0 --epochs 2 --seed 99 --prefix r1_smoke \
      --episodes "$SRC/tools/training/$ep" \
      --fresh --device cpu --out-dir "$LANE/smoke" ) >>"$RUNLOG" 2>&1 \
    || log "[DRY] smoke training nonzero rc/timeout (trail in runlog)"
  cp "$LANE/smoke"/r1_smoke* "$LANE/artifacts/" 2>/dev/null \
    && log "[DRY] copy-back proven -> $LANE/artifacts (SCRATCH: repo tools/training NOT polluted)"
  [[ -f $LANE/smoke/r1_smoke_best.pt ]] && {
    log "[DRY] gate CLI proof: eval_ckpt on smoke best.pt (<=10min)"
    ( cd "$SRC" && timeout 600 "$VENV" -m tools.training.eval_ckpt \
        "$LANE/smoke/r1_smoke_best.pt" --device cpu ) > "$LANE/smoke/gate_smoke.json" 2>>"$RUNLOG" \
      || log "[DRY] eval_ckpt nonzero/timeout (machinery trail in runlog)"
  }
}

# ---------------------------------------------------------------------- main
main() {
  mkdir -p "$(dirname "$RUNLOG")" "$LANE"
  # single-instance lock
  exec 9>/tmp/opencode/r1_window.lock
  flock -n 9 || { echo "another r1_window.sh holds /tmp/opencode/r1_window.lock — refusing to double-run"; exit 4; }
  log "===== r1_window.sh start (dry=$DRY pid=$$) ====="
  cp "$REPO/tools/ops/r1_ledger.py" "$LANE/r1_ledger.py"
  preflight
  wait_start
  write_lane_scripts
  clean_export
  if [[ $DRY -eq 1 ]]; then
    swap_out            # echo-only; sets the trap flag
    dry_smoke           # + gate-CLI proof + ledger writer proof inside
    write_ledger
    restore_engine      # echo-only path through the SAME function the trap uses
    ENGINE_STOPPED=0
    log "[DRY] trap-chain proof: RE-ARMING stop-flag (no docker in dry mode), then FORCING an artificial ERR — the EXIT-cleanup RESTORE branch must fire with echo-only restore"
    ENGINE_STOPPED=1
    sleep 2
    false               # <<< forced ERR: ERR trap -> exit -> cleanup RESTORE branch (echo-only) + banner
  else
    swap_out
    train_arms
    run_evals
    write_ledger
    log "all lanes done — restoring engine on the NORMAL path"
    restore_engine
    ENGINE_STOPPED=0
    log "===== engine restored — attach tmux -r -t r1window to read ledger ($LEDGER) ====="
    sleep infinity      # keep the tmux trail readable until owner kills it
  fi
}
main
