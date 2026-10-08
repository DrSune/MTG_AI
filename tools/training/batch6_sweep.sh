#!/usr/bin/env bash
# batch6: v6 corpus x 5 arms x 3 seeds (3-seed law 2026-10-08). Engine-off (~35 min total).
set -uo pipefail
cd "$(dirname "$0")/../.." || { echo "B6: cd FAILED from $(pwd)"; exit 8; }
echo "B6 driver alive in $(pwd) at $(date +%H:%M:%S)"
LOCK=/tmp/opencode/batch6_sweep.lock
for _try in 1 2; do
  if mkdir "$LOCK" 2>/dev/null; then break; fi
  oldpid=$(cat "$LOCK/pid" 2>/dev/null || echo)
  if [ -n "$oldpid" ] && ! kill -0 "$oldpid" 2>/dev/null; then
    echo "batch6: reclaiming STALE lock (pid $oldpid dead)"; rm -rf "$LOCK"; continue
  fi
  echo "batch6: live driver holds $LOCK (pid $oldpid) — refusing to race. Exit 9."; exit 9
done
echo $$ > "$LOCK/pid"
trap 'rm -rf "$LOCK" 2>/dev/null' EXIT
for arm in S0 S1 S2 S3 S4; do
  for seed in 1 2 3; do
    pref="bc6_${arm}_s${seed}"
    [ -f "tools/training/${pref}_report.json" ] && { echo "skip $pref"; continue; }
    .venv/bin/python tools/training/run_train.py --phase "batch6-${pref}" --timeout 3600 -- \
      .venv/bin/python -m tools.training.train_bc_v3 --arm "$arm" --seed "$seed" --prefix "$pref" \
      || echo "FAIL $pref"
  done
done
.venv/bin/python - <<'PY'
import json, glob, statistics as st
rows = []
for f in sorted(glob.glob("tools/training/bc6_S*_report.json")):
    d = json.load(open(f))
    g = d["gates"]["eval_families"]
    rows.append({"arm": d["arm"], "seed": f.split("_s")[-1].split("_")[0], "params": d.get("model", {}).get("params_total", 0),
                 "acc": g["acc"], "iid": d["eval_margin_se"], "boot": d["eval_margin_bootstrap_se"],
                 "verdict": d["gate_verdict"]["verdict"]})
by = {}
for r in rows: by.setdefault(r["arm"], []).append(r)
summary = {a: {"acc_mean": round(st.mean(x["acc"] for x in v), 4),
               "acc_range": round(max(x["acc"] for x in v) - min(x["acc"] for x in v), 4),
               "boot_mean": round(st.mean(x["boot"] for x in v), 2),
               "pass_count": sum(x["verdict"] == "PASS" for x in v), "n": len(v)} for a, v in by.items()}
json.dump({"runs": rows, "summary": summary}, open("tools/training/batch6_curve.json", "w"), indent=1)
for a in sorted(summary): print(a, summary[a])
PY
echo "=== batch6 complete ==="
