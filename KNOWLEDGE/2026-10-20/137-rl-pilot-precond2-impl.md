# 137 — /134 RL-pilot PRECONDITION 2: sampling collection + off-policy logprob audit (SHIPPED 2026-10-20)

## Decision (design B, smaller diff)
Collection rides the gameplay_eval_v2 rig (`--rl-collect F.jsonl --sample
--rl-seed N`), NOT gen_games: rig `book()` already sees every net ask with
(seat, menu, site, idx, obs) and `run_v2_game` is one self-contained
process; gen_games' net goes through the mcts rollout machinery whose
episode extras (pi/value/net_idx/heur_idx) are entangled with search stats.
gen_games untouched ⇒ legacy gates byte-identical.

## Shipped pieces
- `BcAsk.menu_logprobs` (one shared `_forward_menu`, digit-lane env swap
  intact) + `BcAsk.sample_ask(ctx, rng)` -> `(idx, logπ(idx))`; pure-python
  scaled-CDF draw, never touches torch RNG. Argmax lane unchanged.
- `_SamplingSeat` proxy in the rig (only under `--rl-collect`): decide =
  sample + remember (idx,logp) for the ADJACENT book() (pairing ASSERTED);
  every live call site (provider/take_acts/select_targets) pairs
  decide->book; `PolicyActDriver.ask` (:277) has no callers.
- Row contract (jsonl, one row per sampled seat per game):
  `{kind, game_seed, swap, seat, policy, rng_seed, asks:[{what, vocab, idx,
  logp, obs, choose}]}`; rng_seed = rl_seed*1_000_003 + seed*2 + seat.
  Eval `--out` schema byte-identical (rl keys POPPED before summarize).
- `tools/training/rl_logprob_audit.py`: replays each owned episode through
  a FRESH `BcAsk` of the checkpoint from the row ALONE; reports
  max|Δ|/mean|Δ|/share|Δ|>tol; RAISES naming the /83 pi_mix trap on
  tampered/deleted logp, contract-key drift, idx outside menu, foreign-
  checkpoint-only files, zero asks, or any |Δ|>tol (default 1e-3).

## THE TRAP FOUND BY THE AUDIT ITSELF (PITFALLS)
Cross-process audit MISMATCHED 31/100 asks on choose sites while the
in-process pytest roundtrip was GREEN. Cause: v2 candidate grounding for
`choose:<source>:<digest>` asks comes from `bc_data_v2._STASH`, a
PROCESS-GLOBAL, FIFO-CAPPED (STASH_CAP=32) memo filled by the live engine;
a file+checkpoint replay cannot re-derive it ⇒ choose candidates silently
re-ground differently. Fix: every ask row pins the collector's stash entry
(`choose` field, null = blind stays blind); `bc_data_v2.stash_put` re-
enters it during replay. Warm-memo state masquerading as encoding purity.

## Numbers (2026-10-20)
- Deterministic 2-game collect (bsh_S3a_s1_best vs teacher, engine pool,
  seeds 1-2, rl-seed 7): 100 asks / 2 owned episodes.
- Audit GREEN cross-process: max|Δ|=0, mean|Δ|=0 (same weights).
- RED demos: +0.5 logp tamper -> RuntimeError (exit 1, 1/100 breach,
  max|Δ|=0.5); deleted logp -> RuntimeError (contract); deleted choose key
  -> RuntimeError (contract).
- Sampler determinism: two in-process collections -> identical (idx,logp)
  sequences (test_sampler_determinism).

Commands: see module docstrings; tests
`tools/training/test_rl_collect.py` (8 tests).
