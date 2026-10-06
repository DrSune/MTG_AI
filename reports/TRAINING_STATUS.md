# TRAINING STATUS — COMPLETE (verdict NULL)

- updated: 2026-10-06 13:45
- state: **COMPLETE** — batch-2 BC retrain bc_s2 finished: run8 `cause=complete`
  exit 0 (ledger reports/training_runs.jsonl), full 250 epochs, best train
  loss 0.17172 @ ep191. Artifacts: tools/training/bc_s2.pt + bc2_report.json
  (13:04:41), tools/training/elo_s2_sanity.json.
- verdict: **NULL** — eval_families 0.5909 vs random floor 0.4205 = +2.29 SE
  (<3 SE gate, p=0.017). Batch1→2 delta +3.82 SE (schema fix real, gate not
  cleared). Closed-loop Elo sanity −6.8 [−58.3, 44.8] ≈ random. Per the
  pre-registered null-meaning rule (doc 12): do NOT scale; re-diagnose before
  batch 3 (leads in doc 16).
- path taken: 9 launch segments under the run_train wrapper; two silent
  SIGKILLs under vLLM swap-thrash were recovered by the new `--resume`
  checkpointing; every ledger segment has an honest start+final.
- report card: KNOWLEDGE/2026-10-06/16-batch2-bc.md; numbers in
  KNOWLEDGE/NUMBERS.md (2026-10-06 section).

Ops log: reports/training_ops.log | Runs jsonl: reports/training_runs.jsonl
