# 138 — /134 RL-pilot TASK B: REINFORCE trainer `train_rl_v1.py` (SHIPPED 2026-10-20)

## Shipped
- `tools/training/train_rl_v1.py`: one REINFORCE update per iterations-file
  (batch-1 law: no best-loss selection; save `<tag>.pt` + `<tag>_diag.json`).
  Objective exactly per /134 v2: batch-mean outcome baseline (win +1 / loss
  −1 / draw 0 / **crash = loss**, rig convention), + β·mean-KL vs FROZEN
  anchor (default β=0.1, ceiling 0.05 reported + LOUD on breach), −0.001·
  entropy, SGD lr 1e-5, grad-clip 1.0. Later iterations: `--policy rld_iN.pt
  --anchor <base>` keeps the KL anchor the PRE-RL clone (cumulative-KL gate).
- Recompute purity: logπ via `BcAsk._forward_menu(grad=True)` — the SAME
  encoding forward as collection/audit; ab_duel hook is `grad=False` default
  selecting `nullcontext()` vs `no_grad()` only (2 sites, inference path
  byte-identical). Choose-stash re-entry identical to rl_logprob_audit.
- Rig: `rl_episode_rows` now emits per-seat `outcome` (win/loss/draw/crash,
  collecting-seat view; only under `--rl-collect`, legacy lanes untouched).
- F4 no-op-discriminator keys in every sidecar: `mean_abs_dlogp_chosen`,
  `kl_mean_per_game` (+`_post` re-forward), `entropy_mean`,
  `grad_norm_preclip`, `share_dlogp_gt_0p1`, `reward_var` (+ loss
  decomposition pg/kl/entropy summing to total).

## Documented notes (not objective deviations)
- **NOTE-1 optimizer = plain SGD** (pre-registration named LR+clip only):
  Adam-style `lr·g/(√v+ε)` amplifies the zero/noise gradient floor ~1/ε and
  would destroy the F4 zero-variance discriminator. SGD preserves it.
- **NOTE-2 `--max-asks` guard is TEST-ONLY**: caps each game to a leading
  PREFIX of its owned causal stream (prefixes replay byte-identically) so
  small batches keep per-game outcomes — whole-episode drops would silently
  collapse a win/loss batch to one outcome. Never used in pilot runs.
- **Pitfall found while testing**: the entropy bonus (and float32 Σp≠1
  residue in KL) has a NONZERO gradient at the anchor point (~6e-4 grad-norm
  at 48 asks) — the zero-variance guard must isolate the PG component
  (β=0, entropy_coef=0 ⇒ grad EXACTLY 0) with a win/loss positive control,
  else the guard passes by being deaf, not by the baseline working.
- `kl_mean_per_game_post` can read ~1e-10 NEGATIVE (float32) — KL≥0 is
  mathematical, the float sum of `p·(lp−lp_a)` is not; ceiling gate uses
  magnitude, do not clamp (hides truth).

## Numbers (instrument-scale, NOT verdict-bearing)
- Deterministic 2-game collect (bsh_S3a_s1 vs teacher, seeds 1-2, rl-seed 13):
  outcomes win/win (Rvar=0), 42+58 asks; 1 update on 48 guarded asks:
  grad_norm 6.2e-4 (pure regularizers), |Δlogp|=2.3e-9, KL 5.4e-10,
  entropy 0.0242 — flat PG exactly as the baseline law requires at Rvar=0.
- Tests `tools/training/test_rl_train.py` (6): smoke+outcome contract, one
  update (weights change, anchor file sha-identical, F4 keys), zero-variance
  guard + positive control (grad 0 vs >1e-4), bit-determinism (grad-norm and
  loss `==` across runs), fail-loud missing-outcome / shape-drift; legacy
  pre-outcome file RAISES naming the outcome gap (verified on the /137 demo).

## Commands
    .venv/bin/python tools/eval/gameplay_eval_v2.py --games 2 --workers 1 \
      --matchups teacher --pool engine --policy-a <base.pt> --device cpu \
      --rl-collect eps.jsonl --sample --rl-seed 13 --out eval.json
    .venv/bin/python tools/training/train_rl_v1.py --episodes eps.jsonl \
      --policy <base.pt> [--anchor <base.pt>] --tag rld_i1 [--max-asks N]
  Files: tools/training/train_rl_v1.py, test_rl_train.py; hooks: ab_duel.py
  `_forward_menu(grad=...)`, gameplay_eval_v2.rl_episode_rows outcome field.
