#!/usr/bin/env bash
# Batch-3 full driver: A/B capacity arms, base selection, filtered DAgger
# rollout (+ bc_s2 control), retrain on the 50/50 mix, Elo sanity.
#
# Production launch (engine off, container stopped first — that is the
# wrapper's job, this script assumes the GPU is its own):
#   bash tools/training/run_full_memory.sh -- bash tools/training/batch3_full.sh
# Dry law (--smoke): 2 epochs, 8+8 episodes, first 4 packs, 2 games/pair,
# every artefact under /tmp/opencode/b3smoke, ledger redirected there too.
set -uo pipefail
cd "$(dirname "$0")/../.." || exit 1

RT="tools/training/run_train.py"
PY=(".venv/bin/python" -u)
SMOKE=0
[[ "${1:-}" == "--smoke" ]] && SMOKE=1

if [[ $SMOKE -eq 1 ]]; then
  OUTDIR=/tmp/opencode/b3smoke
  mkdir -p "$OUTDIR"
  LEDGER=(--runs-file "$OUTDIR/training_runs.jsonl")
  TRAIN=(--smoke --out-dir "$OUTDIR")
  ROLL=(--limit 4)
  MIX="$OUTDIR/episodes_dagger.jsonl"
  GAMES=2
  SEEDFILE=(--seed-file "$OUTDIR/duel_seeds.json")
  D9=90001
else
  OUTDIR=tools/training
  LEDGER=()
  TRAIN=()
  ROLL=()
  MIX=tools/training/episodes_dagger.jsonl
  GAMES=120
  SEEDFILE=()
  D9=90001  # fresh block, disjoint from every bank-used seed so far
fi

stage() {  # stage <name> <timeout-s> <cmd...>
  local name=$1 tmo=$2
  shift 2
  echo "=== [$(date +%H:%M:%S)] stage: $name ==="
  "${PY[@]}" "$RT" --phase "batch3-$name" --timeout "$tmo" --ignore-prev \
    "${LEDGER[@]}" -- "$@"
  local rc=$?
  [[ $rc -eq 0 ]] && echo "=== stage $name OK ===" || echo "=== stage $name FAILED rc=$rc ==="
  return $rc
}

pick_winner() {  # eval_families beat-vs-random margin; ties go to B (cheaper)
  "${PY[@]}" - "$OUTDIR" <<'EOF'
import json, sys
out = sys.argv[1]
def m(arm):
    try:
        rep = json.load(open(f"{out}/bc3_{arm}_report.json"))
        v = rep["gates"]["eval_families"]["vs_random"]["beat_margin_se"]
        return v if isinstance(v, (int, float)) else -99.0
    except Exception:
        return -1e9
a, b = m("A"), m("B")
if max(a, b) <= -98:
    sys.exit("no usable A/B eval margin in reports")
print("A" if a > b else "B")
EOF
}

fail() { echo "batch3 aborted: $1"; exit 1; }

# Resume guards (2026-10-06): a process-tree kill mid-run is expected; a stage
# whose artefact exists is done. Idempotent relaunch, never redo finished work.
have_report() { # <stage> <file-in-OUTDIR>
  if [[ -f "$OUTDIR/$2" ]]; then skip "$1"; return 0; else return 1; fi
}
skip() { echo "=== [$(date +%H:%M:%S)] skip: $1 (artefact present) ==="; }

# --- 1. capacity arms, pre-registered configs, seed 1, 250 epochs ----------
if have_report armA bc3_A_report.json; then :; else
stage armA 72000 "${PY[@]}" -m tools.training.train_bc_v3 --arm A --prefix bc3_A \
  "${TRAIN[@]}" || fail "arm A"
fi
if have_report armB bc3_B_report.json; then :; else
stage armB 14400 "${PY[@]}" -m tools.training.train_bc_v3 --arm B --prefix bc3_B \
  "${TRAIN[@]}" || fail "arm B"
fi

WINNER=$(pick_winner) || fail "winner selection"
echo "=== base arm winner: $WINNER ==="

# --- 2. filtered DAgger rollout on the winner + bc_s2 control (stats only) -
if have_report rollout bc3_rollout_stats.json; then :; else
stage rollout 14400 "${PY[@]}" -m tools.training.dagger_rollout_v3 \
  --ckpt "$OUTDIR/bc3_${WINNER}.pt" --out "$MIX" \
  --stats "$OUTDIR/bc3_rollout_stats.json" "${ROLL[@]}" || fail "dagger rollout"
fi
if have_report control bc3_rollout_base.json; then :; else
stage control 14400 "${PY[@]}" -m tools.training.dagger_rollout_v3 \
  --ckpt tools/training/bc_s2.pt --stats "$OUTDIR/bc3_rollout_base.json" \
  "${ROLL[@]}" || echo "WARNING: bc_s2 control failed; continuing without it"
fi

# --- 3. retrain winner architecture on the 50/50 mix ------------------------
if [[ $WINNER == A ]]; then RTMO=72000; else RTMO=14400; fi
if have_report retrain bc3_dagger_report.json; then :; else
stage retrain "$RTMO" "${PY[@]}" -m tools.training.train_bc_v3 \
  --arm dagger --base-arm "$WINNER" --prefix bc3_dagger --episodes "$MIX" \
  "${TRAIN[@]}" || fail "dagger retrain"
fi
cp "$OUTDIR/bc3_dagger_report.json" "$OUTDIR/dagger_report.json"

# --- 4. Elo sanity: final policy vs random and pass-floor -------------------
if have_report elo elo_s3_sanity.json; then
  echo "=== batch3 complete (all stages already on disk): winner=$WINNER ==="; exit 0
fi
FINAL="$OUTDIR/bc3_dagger_best.pt"
[[ -f $FINAL ]] || FINAL="$OUTDIR/bc3_${WINNER}_best.pt"
stage elo 7200 "${PY[@]}" -m tools.training.elo random pass-floor "$FINAL" \
  --games "$GAMES" --workers 6 --device cuda --seed-start "$D9" \
  "${SEEDFILE[@]}" --out "$OUTDIR/elo_s3_sanity.json" || fail "elo sanity"

echo "=== batch3 complete: winner=$WINNER, artefacts in $OUTDIR ==="
