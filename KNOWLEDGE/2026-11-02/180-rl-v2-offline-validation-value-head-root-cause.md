# /180 — RL v2 offline validation: value head root cause (measured), fix, re-run

Date: 2026-11-02 (~14:00–23:5x; re-run + debug loop numbers in the addendum).
Status: validation record. Builds on /179 (state after the reboot).
Worktree: `/home/sune/.local/share/opencode/worktree/30c75f/rl-v2`.

## 1. Episode baseline regeneration (measured, complete)

- Background collect of the pinned 1000-game baseline (pinned tree +
  seeds 510201/1412/4244, 6 CPU workers, engine pool, `--device cpu`):
  1000 games, outcome profile **403W / 581L / 1D / 15X** — identical to
  the five-night baseline. Wall 4839 s (~80 min; the engine was busy
  with other session traffic for most of the run).
- File SHA `2bbdad3d…` ≠ pinned `2e09d72b…`. **Root cause of the
  difference (verified, not assumed): the `policy` field records the
  path as given** — this regeneration ran from the main tree
  (`/home/sune/Desktop/MTG_AI/tools/training/bsh_S3a_s1_best.pt`), the
  nightly windows ran from the export
  (`/tmp/opencode/rl_n1_train_src/...`). Every row carries that string.
- **Content identity proven by the logprob audit (cpu-to-cpu):
  46941/46941 asks re-derived, max|Δ| = 0.0, mean|Δ| = 0.0** (the
  nightly audits ran cuda-vs-cpu and measured 5.507469177246094e-4).
  All seeds/outcomes/asks/obs are bit-identical; only the path string
  differs. The pinned SHA is a property of the export cwd; for v2
  work, content identity is the invariant, and it holds.

## 2. Unit test suite (measured, complete)

`pytest tools/training/test_rl_v2.py -q` with vLLM resident (~14–22 GiB
free < the 30 GiB `needs_safe_cuda` threshold → memory-law fallback to
CPU, 3 cuda-only tests skip):

- **Before the value-head fix: 14 passed, 3 skipped in 113.91 s.**
- **After the fix: 14 passed, 3 skipped in 57.28 s** — including the
  load-bearing `test_bit_identity_wrapper_vs_anchor` on the real
  anchor checkpoint (policy path untouched by the value-head change).
- The 3 skipped tests (warm-start EV on real data, PPO update on real
  data, one more cuda-parametrized) are the memory-law correct
  behaviour; they run in the next engine-down window.
- Test-design gap found (recorded, not fixed): the warm-start EV>0
  test is `needs_safe_cuda`-only, so the CPU path that the memory law
  forces today never exercises it — which is exactly how the value
  head failure below went undetected by the suite. A CPU-runnable
  warm-start/EV test should exist (the offline CLI run is currently
  the only CPU coverage; item for the next worktree pass).

## 3. The value head explains nothing (measured) — root cause

First offline end-to-end run (`train_rl_v2.py`, 50g, 1 iteration,
cpu) hit the pre-registered triage gate #1:

    warm-start value head explained variance -0.0002 <= 0 on 200
    held-out games — triage rule #1

Diagnosed with controlled experiments (throwaway
`_diag_valuehead.py`, `_diag_valuehead2.py`; numbers below are all
measured on the regenerated episodes):

| Experiment | Holdout EV |
|---|---|
| Value head at init (random) | -0.0824 |
| Trainer warm-start, 3 epochs (40g train / 20g hold, 60g diag) | -0.0008 (ev_train 0.0133, last MSE 0.9642 ≈ Var(target) 0.9530, ‖W‖ 0.5880→0.5846) |
| Independent linear probe on STATIC h, 3 epochs (same data) | -0.0019 / -0.0135 / -0.0012 |
| Independent linear probe on STATIC h, 10 epochs (200g train / 100g hold) | -0.0017 … -0.0019 (all epochs), last-third -0.004…+0.001 |
| **Raw obs features [life_diff, turn, board_diff, hand] alone, 700g train / 300g hold** | **0.2562 (all decisions)** |
| same, turn≥5 / turn≥10 / last-third subsets | 0.2731 / 0.3117 / **0.4989** |

**Conclusion (evidence, not hypothesis):** the BC encoder's decision-
tuned SEP state `h` discards the outcome signal (an independent probe
excludes trainer plumbing), while the raw board state carries it
(0.26–0.50 EV). The value head as first built — "linear on h" — could
therefore never pass triage rule #1; it was an over-narrowing of the
spec.

## 4. Fix (committed `7bad492`; pre-registration amendment A1 `fb878ce`)

- `value_head` is now `Linear(d + STATE_FEAT_DIM, 1)` with 5 raw state
  features (learner perspective, fixed normalization, deterministic):
  `[life_diff/20, turn/20, board_diff/5, hand_size/8, is_active]`.
- Spec re-read (plan Step 4 item 2, the owner's exact words): the
  value head is "a scalar head on the policy's encoder that predicts
  the game's outcome **from the board** at each decision". Reading the
  board's raw features directly alongside `h` is spec-faithful; the
  original module docstring's "one scalar linear layer on the encoder
  step state" was the subagent's over-narrowing, not the owner's
  wording. The success checklist in the pre-registration is unchanged.
- Policy path untouched: bit-identity vs the standalone anchor
  re-passes on the real checkpoint (unit test, cpu).
- Plumbing: `encode_episode` carries `state_feats` per decision;
  `collate_decisions` batches them; every `forward_with_value` call
  site (batch_forward, warm-start ×2, measure_value_ev, PPO minibatch)
  passes them. `load_policy` unchanged (anchor blobs lack the value
  keys by design; v2 checkpoints carry them).

## 5. Offline re-run (first attempt FAILED on a new bug — see §7.1)

Same command as §3, after the fix. Expected: warm-start EV > 0 on the
200-game holdout (the raw-feature probe predicts ~0.1–0.3 at the
trainer's 500-game/3-epoch budget), PPO update with KL > 0 within
budget, checkpoint pair `<tag>.pt` + `<tag>_policy.pt` sidecar
(PointerBC-format, for `BcAsk.fresh` collection).

## 6. Next (addendum when the runs land)

1. Offline CLI numbers (EV gate, KL, entropy, grad norms, movement).
2. Sidecar strict-load check via `BcAsk.fresh` (the on-policy
   collection path).
3. The 5-iteration DISCARDED on-policy debug loop
   (`rl_v2_debug_loop.py`; fresh seed blocks from 520001, D9
   registry) — the mechanics checklist per the pre-registration.
4. Final: era-boundary coordination unchanged (sibling merge gate,
   seat-routing fix, re-smoke, re-pin, re-certify, re-baseline,
   re-collect, tokenizer re-evaluation per law §8), then the REAL
   runs with the plan's strength pre-registration.

## 7. Addendum (offline CLI + debug-loop numbers, appended below)

### 7.1 First re-run: EV gate PASSED, new bug in `ppo_update` (2026-11-02 23:12 → 2026-11-03 01:16, wall 104 min)

- Warm-start (500g, 3 epochs) + holdout EV measurement completed and the
  **EV gate passed** — no triage-rule-#1 error; the run proceeded into
  the PPO update (the value-head fix in §4 works). The gate's numeric
  value is not logged (`train()` prints nothing before the gate);
  passage is proven by the crash occurring after it.
- **New failure (measured)**: `ppo_update` crashed at
  `torch.cat(anchor_parts, 0)` — `RuntimeError: Sizes of tensors must
  match except in dimension 0. Expected size 85 but got size 7`.
  Root cause: the frozen-anchor logp cache assumed one global menu
  width, but each collate chunk pads to its own `C_max` (per-chunk max
  menu size) — chunk widths 85 vs 7 cannot concat. Escaped the suite
  for the same reason as the warm-start bug: the PPO-update test is
  cuda-only.
- **Fix (worktree commit `be11cbe`)**: the anchor cache is now a
  per-row list (row i = global decision i, width = its own chunk's
  `C_max`). The KL minibatch writes each row's real-candidate prefix
  (columns 0..c-1 always align with the policy's collate — same record,
  same candidate order, collate fills from column 0) onto a clone of
  `menu_logp`; padding mass is exactly zero on both sides, so no
  padding columns contribute. The post-update chosen-logp check looks
  up each row directly.
- **Regression test (same commit)**:
  `test_ppo_update_synthetic_cpu_chunked` — random small models, 9 fake
  records with menu sizes 3..11, `minibatch=4` → chunks of widths
  6/10/11; asserts finite metrics, KL vs anchor > 0, and a real policy
  move. Runs on CPU with no anchor blob — this exact fault cannot
  silently skip again. Suite: **15 passed, 3 skipped** (cuda-only), no
  warnings.
- Hygiene (same commit): `detach()` before `float()` on the metric
  tensors in `ppo_update` (pre-existing `UserWarning` on every update).
- In the same window the sidecar mechanism was verified standalone
  (no training needed): `save_ckpt` → 4 artifacts; `BcAsk.fresh`
  strict-loads the `_policy.pt` sidecar as plain PointerBC; full
  checkpoint round-trips through `load_policy` (value head intact);
  sidecar policy is bit-identical to the anchor pre-update.

### 7.2 Second re-run (in flight at writing — numbers appended below)

Same command as §5, after the `be11cbe` fix. Launched 2026-11-03 02:05
(background; expected ~105–115 min wall: warm-start dominates).

### 7.3 5-iteration on-policy debug loop (pending — after 7.2 lands)

Launch: `/tmp/opencode/rlv2_debug_launch.sh` (OMP_NUM_THREADS=8 per the
23:21 encode-peak memory measurement; fresh seed blocks 520002+ per the
D9 registry).
