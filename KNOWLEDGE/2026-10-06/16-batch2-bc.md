# 16 — Training Batch 2: v2-schema BC retrain (2026-10-06)

Deliverables: `tools/training/{packrec_v2,bc_data_v2,train_bc_v2,test_bc_v2}.py`,
`episodes_v2.jsonl` (96 eps, 119 gold lines), `bc_s2.pt`, `bc2_report.json`,
`elo_s2_sanity.json`. Head 77b78ef. No engine edits. v1 encoder verified
bit-identical (v2 keys ignored by `bc_data.obs_words`).

Produced by: `.venv/bin/python -m tools.training.train_bc_v2 --device cuda
--epochs 250 --resume tools/training/bc_s2_best.pt` (run8, cause=complete,
exit 0; segments 1–8 total ≈ 8.2 h GPU under vLLM coexistence contention).

## Verdict: NULL — do NOT scale; re-diagnose before batch 3

Eval families (family-wise split, `tools/audit/eval_split.json`, 75 train /
44 eval items) fail the pre-registered gate (>3 SE one-sided vs random floor):

| slice | rows | acc | vs random (floor) | vs null (floor) |
|---|---|---|---|---|
| gold_lines_all | 119 | 0.7815 | **+8.27 SE** (0.409) | +21.54 SE (0.1261) |
| train_families | 75 | 0.8933 | +8.67 SE (0.4023) | +17.32 SE |
| **eval_families** | **44** | **0.5909** | **+2.29 SE** (0.4205) — **FAIL <3** (p=0.017) | +13.76 SE (0.0682) |
| l1_certified | 4 | 1.000 | +5.87 SE (0.0287) | +6.05 SE |

Eval quartiles (acc): q1 0.3571, q2 0.7692, q3 0.8750, q4 0.2857.
Batch-1 comparison (`bc2_report.json`): batch-1 holdout was −1.53 SE below its
floor; batch-2 eval families +2.29 SE above theirs → schema-fix delta
**+3.82 SE**: real improvement in unseen-policy generalization, but not past
the gate. Closed-loop Elo sanity (`python -m tools.training.elo random
pass-floor tools/training/bc_s2.pt --games 120 --workers 6`, 635 s):
bc_s2 = **−6.8 Elo [−58.3, 44.8]** — statistically indistinguishable from
random (pass-floor +34.4 [−20.2, 83.8]). The v2 model plays like random even
though its gold lines score 0.59 on unseen families.

Model/config identical to batch 1 (PointerBC d=512 L=8 h=8 ff=3072, dropout 0,
bf16, grad ckpt, max_len 1024). best train loss **0.17172 @ ep191** (full 250
epochs). GPU peak **1.67 GiB < 4.0 GiB** budget. **vocab=380, not the 319 the
mission note expected** — current `build_vocab_v2` version on the 2026-10-05
corpus v2 episodes.

## Operational record (honest)

* 9 launch segments. Two silent SIGKILL deaths (~ep100 each, 04:0x and
  04:47:05, the latter 1 s after a checkpoint write) with no kernel OOM /
  NVRM entries; environment was swap-thrashing (13/15 GiB swap, ~450 MB/s
  swap-in, driver pinned ≈100 GiB for vLLM). PITFALLS law "no big PyTorch
  beside vLLM unless avail > 40 GB" is the standing explanation — this run
  survived only via `--resume` insurance (added this session, now carries the
  curve) + raised watchdog timeouts.
* Own mistakes logged: run4a died on an unwired `--resume` flag (exit 2);
  a dry-test of `train(resume=…)` on an 8-episode subset **overwrote
  bc_s2_best.pt with a toy fit** — recoverable only because the trajectory is
  regenerable from seed 1. Never call `train()` with real CKPT_BEST on disk.
* Ledger `reports/training_runs.jsonl` complete: every segment has start+final
  (2 manual finals for detached/killed wrappers).
* Gates: `pytest tools/training -q` **57 passed**; ruff clean on new code
  (2 pre-existing BLE001 + 1 F401 left untouched); engine untouched.

## Re-diagnosis leads for batch 3 (from the data, not vibes)

1. Closed-loop Elo ≈ random while gold-line acc 0.59: teacher-forced next-ask
   accuracy does not compose over a full game (exposure bias). Candidate
   probes: per-ask-position accuracy decay within an episode; self-play
   rollout divergence depth vs batch 1.
2. q1/q4 (0.36/0.29) are where the eval families lose the 3 SE; q2/q3 pass.
3. l1_ready still 4 (binary-vocab floor, doc 15): the ≥40 ladder backlog A3
   remains the binding constraint on the ladder gate, independent of BC.
