"""r28's registered quantities at a look (KNOWLEDGE/2026-11-12/199 §2, §5), from the last row per update.

    .venv/bin/python reports/r28_2026-11-12/look.py [RUN_DIR] [UPTO]

R1: the learner's mulligan declarations per game, pooled per block of 25 updates. R2: the
mulligan's KL over act's, median over updates 1..min(UPTO, 100). R4: train_s, the interval
between updates (gate updates left out) and the share of a batch played by the previous
weights, over updates 2-50. R5: kl. R6: the lowest MemAvailable. Then the gates, and the
training win rates and entropy per block (sampled play: not a strength measure).
"""
import json
import statistics as st
import sys
from pathlib import Path

run = Path(sys.argv[1] if len(sys.argv) > 1 else "runs/selfplay/r28_stratified_ppo")
rows = [json.loads(line) for line in (run / "metrics.jsonl").open()]
last = {}
for r in rows:
    if r.get("event") == "iter":
        last[r["it"]] = r  # a resume replays updates after the last save: the last row counts
upto = int(sys.argv[2]) if len(sys.argv) > 2 else max(last)
its = [i for i in sorted(last) if i <= upto]
gated = {r["it"] for r in rows if r.get("event") == "gate"}
blocks = [(a, min(a + 24, upto)) for a in range(1, upto + 1, 25)]


def sel(a, b):
    return [last[i] for i in its if a <= i <= b]


print(f"updates {its[0]}-{its[-1]} ({len(its)})")
for a, b in blocks:
    s = sel(a, b)
    mull = sum(r["kinds"].get("mulligan", {}).get("n", 0) for r in s) / sum(r["games"] for r in s)
    win = {k: st.mean(r["win"][k] for r in s) for k in ("heuristic", "frozen")}
    print(f"block {a}-{b}: R1 mulligan/game {mull:.3f}; win heuristic {win['heuristic']:.3f} "
          f"frozen {win['frozen']:.3f}; ent {st.mean(r['ent'] for r in s):.4f}")
ratio = [last[i]["kinds"]["mulligan"]["kl"] / last[i]["kinds"]["act"]["kl"] for i in its
         if i <= 100 and "mulligan" in last[i]["kinds"]]
q = st.quantiles(ratio, n=4)
print(f"R2 mulligan KL / act KL over 1-{min(upto, 100)}: median {st.median(ratio):.2f} "
      f"(q1 {q[0]:.2f}, q3 {q[2]:.2f}, max {max(ratio):.2f})")
s = sel(2, 50)
iv = [last[i]["t"] - last[i - 1]["t"] for i in its if 2 <= i <= 50 and i - 1 in last
      and not {i, i - 1} & gated]
share = {r["it"]: r["overlap_steps"] / r["steps"] for r in s}
low = min(share, key=lambda i: share[i])
print(f"R4 over 2-50: train_s median {st.median(r['train_s'] for r in s):.0f} "
      f"({min(r['train_s'] for r in s):.0f}-{max(r['train_s'] for r in s):.0f}); interval median "
      f"{st.median(iv):.0f} s ({len(iv)}); previous weights' share median {st.median(share.values()):.2f} "
      f"(lowest {share[low]:.2f} at update {low})")
kl = [last[i]["kl"] for i in its]
print(f"R5 kl: median {st.median(kl):.4f} ({min(kl):.4f}-{max(kl):.4f})")
print(f"R6 lowest MemAvailable {min(last[i]['mem_min_gib'] for i in its):.1f} GiB; voids "
      f"{sum(last[i]['voids'] for i in its)}; non-finite {sum(last[i]['nonfinite'] for i in its)}; "
      f"KL stops {sum(bool(last[i]['kl_stop']) for i in its)}")
for r in rows:
    if r.get("event") == "gate" and r["it"] <= upto + 2:
        print(f"gate at {r['it']} vs {r['vs']}: {r['score']} {r['ci95']}")
