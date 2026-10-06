#!/usr/bin/env bash
# Batch-5 driver: the pre-registered model-size ladder S0..S4 (KNOWLEDGE/
# 2026-10-06/21) on identical data/seed/gates — the deliverable is the curve
# of eval-families margin vs params, with the ratio trio in every row.
#
# Production launch (engine off, container stopped first — that is the
# wrapper's job, this script assumes the GPU is its own):
#   bash tools/training/run_full_memory.sh -- bash tools/training/batch5_sweep.sh
# Dry law (--smoke): ALL 5 arms, 2 epochs, 8+8 episodes, CPU device, every
# artefact AND the runs ledger under /tmp/opencode/b5smoke — never
# tools/training (dry-test-clobbers law, PITFALLS 2026-10-06).
#
# If any arm dies on the over_limit BPTT abort: the driver STOPS (fail).
# The fix is lengthening max_len per the owner law — never shrinking data
# or raising the cap silently; that decision belongs to the owner.
set -uo pipefail
cd "$(dirname "$0")/../.." || exit 1

# One driver at a time (batch-3 driver-race incident, KNOWLEDGE/2026-10-06/20).
# Stale lock after a hard crash: rmdir the dir (nothing else owns it).
LOCK=/tmp/opencode/batch5_sweep.lock
if ! mkdir "$LOCK" 2>/dev/null; then
  echo "batch5_sweep: ANOTHER driver holds $LOCK — refusing to race. Exit 9."
  exit 9
fi
trap 'rmdir "$LOCK" 2>/dev/null' EXIT

RT="tools/training/run_train.py"
PY=(".venv/bin/python" -u)
SMOKE=0
[[ "${1:-}" == "--smoke" ]] && SMOKE=1

if [[ $SMOKE -eq 1 ]]; then
  OUTDIR=/tmp/opencode/b5smoke
  mkdir -p "$OUTDIR"
  LEDGER=(--runs-file "$OUTDIR/training_runs.jsonl")
  TRAIN=(--smoke --out-dir "$OUTDIR" --device cpu)
else
  OUTDIR=tools/training
  LEDGER=()
  TRAIN=()
fi

stage() {  # stage <name> <timeout-s> <cmd...>
  local name=$1 tmo=$2
  shift 2
  echo "=== [$(date +%H:%M:%S)] stage: $name ==="
  "${PY[@]}" "$RT" --phase "batch5-$name" --timeout "$tmo" --ignore-prev \
    "${LEDGER[@]}" -- "$@"
  local rc=$?
  [[ $rc -eq 0 ]] && echo "=== stage $name OK ===" || echo "=== stage $name FAILED rc=$rc ==="
  return $rc
}

fail() { echo "batch5 aborted: $1"; exit 1; }

# Resume guards (batch-3 law): a process-tree kill mid-run is expected; a
# stage whose report exists is done. Idempotent relaunch, never redo
# finished work.
have_report() { # <stage> <file-in-OUTDIR>
  if [[ -f "$OUTDIR/$2" ]]; then skip "$1"; return 0; else return 1; fi
}
skip() { echo "=== [$(date +%H:%M:%S)] skip: $1 (artefact present) ==="; }

# --- the ladder: pre-registered configs, seed 1, 250 epochs, patience 60. ---
# Watchdog timeouts per arm: S0/S1 1800, S2 3600, S3 7200, S4 14400 seconds.
TMO=(1800 1800 3600 7200 14400)
for i in 0 1 2 3 4; do
  arm="S$i"
  if have_report "$arm" "bc5_${arm}_report.json"; then :; else
    stage "$arm" "${TMO[$i]}" "${PY[@]}" -m tools.training.train_bc_v3 \
      --arm "$arm" --prefix "bc5_${arm}" "${TRAIN[@]}" || fail "arm $arm"
  fi
done

# --- curve: eval margin vs params, ratio trio in every row, batch-3 A/B as ---
# --- reference rows (read-only from tools/training; smoke never writes it). ---
echo "=== [$(date +%H:%M:%S)] stage: curve ==="
"${PY[@]}" - "$OUTDIR" <<'EOF' || fail "curve"
import json, sys

out = sys.argv[1]
REPO = "."


def row(rep, arm):
    gates = rep["gates"]["eval_families"]
    seq = rep["seq_len"]
    ratio = rep.get("ratio") or {  # batch-3 reports predate the ratio block
        "params": rep["train"]["params"],
        "gold_lines_train": sum(rep["counts"]["data_mix"].values()),
        "median_seq_len": seq["median"],
    }
    lines = ratio["gold_lines_train"]
    return {
        "arm": arm,
        "params": rep["train"]["params"],
        "params_per_gold_line": round(rep["train"]["params"] / max(lines, 1), 1),
        "eval_acc": gates.get("acc"),
        "margin_se": rep["eval_margin_se"],
        "gate_pass": rep["gate_verdict"]["beats_random_floor_by_3SE"],
        "best_loss": rep["train"]["best_train_loss"],
        "median_seq_len": seq["median"],
        "gold_lines_train": lines,
        "cap_headroom": seq.get("cap_headroom"),  # None on pre-/21 reports
    }


arms = []
for i in range(5):
    with open(f"{out}/bc5_S{i}_report.json") as f:
        arms.append(row(json.load(f), f"S{i}"))
arms.sort(key=lambda r: r["params"])

refs = []
for arm in ("A", "B"):
    try:
        with open(f"{REPO}/tools/training/bc3_{arm}_report.json") as f:
            refs.append(row(json.load(f), f"batch3-{arm}"))
    except (OSError, KeyError):
        print(f"WARNING: batch3 {arm} reference unavailable")

curve = {
    "produced_by": "tools/training/batch5_sweep.sh",
    "law": "KNOWLEDGE/2026-10-06/21 — every row carries params : gold lines : median seq_len",
    "gate": "eval_families acc vs random floor, >3 SE one-sided",
    "arms": arms,
    "reference_batch3": refs,
}
with open(f"{out}/batch5_curve.json", "w") as f:
    json.dump(curve, f, indent=1)
    f.write("\n")
for r in arms + refs:
    print(
        f"{r['arm']:>10}: params={r['params']:>10,} "
        f"p/line={r['params_per_gold_line']:>9,.1f} acc={r['eval_acc']} "
        f"margin={r['margin_se']} pass={r['gate_pass']}"
    )
EOF

echo "=== batch5 complete: curve in $OUTDIR/batch5_curve.json ==="
