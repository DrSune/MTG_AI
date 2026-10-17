# STATUS (auto, 2026-10-15 17:5x)

## Frontier (unchanged, admitted)
bsh_S3a_s1: teacher WR 0.4256, champion-PARITY at 400g (0.4649 [.416,.515]), live-UNK 0.0007. Ledger: reports/FRONTIER.md.

## Falsified today-class levers (each in KNOWLEDGE/2026-10-15/85)
volume x5.9 / digit-token cure / search-improvement labels (after adversarial-caught invalid-pipeline fix + legit re-test = neutral). Plateau 0.36-0.43 = expert-class cap.

## Owner decisions pending (all Type-1)
- FORK: R1 capacity-window (2-3h engine-down; also fixes 55M-arm testability) | R2 RL-from-outcome (3-5 days, needs memory headroom below) | R3 freeze+pivot to generalization program. REC: R3 + opportunistic R1.
- ZNR verified source -> first-ever set-level generalization score (meter armed: --split set --fresh-sets ZNR) + §8 atomics re-eval.
- MEMORY: box is at MemAvailable 0.2 GiB idle, swap 73% used, CUDA-pinned ~100 GiB non-reclaimable and creeping with job churn (/87). No safe job can launch right now. A REBOOT (or long engine-down = R1 window) is the only headroom reset.

## Gate-open items (COMPLETED)
- Second-opinion frontier battle 400g bsh_s1 vs champ, fresh seed-base: COMPLETED (/89, OP2 0.4858 @400g replicated).
- Order-dependent test flake fix (tools/eval/test_dagger_wave): COMPLETED (fixed package attribute monkeypatch isolation; 94/94 passed).
- Ruff fixes on arc files (tools/search, numlane, eval_ckpt, holdout_report): COMPLETED.
