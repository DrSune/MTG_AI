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

### 7.2 Second re-run: PASSED end-to-end (2026-11-03 02:05 → 03:47, wall ~102 min, rc=0)

- **Warm-start** (500g / 23910 decisions / 3 epochs, value-lr 1e-3):
  last-epoch MSE **0.84546** (target Var ≈ 0.953), train EV **0.17771**.
- **Holdout EV (200g) = 0.18656** — triage rule #1 satisfied; within the
  0.1–0.3 predicted by the §3 raw-feature probe at this budget.
- **PPO update (iter 1, 50g: 21W/27L/0D/2X, 2439 asks)**:
  policy_loss 0.01014 · value_loss 0.59997 · EV(V0 vs batch) 0.16145 ·
  advantage mean/std -0.00118/0.38966 · entropy 0.03669 ·
  **KL 0.010561/update → early-stop after 1/3 epochs (5 minibatches)**
  at the 0.01 budget · grad norm 9.298 pre-clip (max 14.793, clip binds
  80%) · **chosen_dlogp_post 0.03652** (the update genuinely moved the
  policy, v1 /158 no-op check) · epoch loss 0.59094.
- Artifacts: `rlv2_off50.pt` (full, 39 MB) + `rlv2_off50_policy.pt`
  (sidecar, 39 MB) + `_diag.json` + `_updates.jsonl`.
- **Verification (executed)**: `BcAsk.fresh` strict-loads the real
  sidecar as plain PointerBC (the collection path); full checkpoint
  round-trips through `load_policy` (value head (1, 325) finite, all
  policy keys finite).
- The loop's per-iteration wiring was re-verified against this run's
  artifacts: `ckpt_collect = anchor` at iter 1 (mirror), then each
  iteration's `<tag>_policy.pt` sidecar for the next; per-iteration
  tags `rlv2dbg_i1..i5`.

### 7.3 5-iteration on-policy debug loop (attempt 1 FAILED on a third bug; retry in flight)

**Attempt 1 (2026-11-03 04:05 → 05:50, wall ~1 h 45 min, rc=1)**:
- Warm-start on the recorded 1000g (500g / 23910 decisions / 3 epochs):
  **held-out EV = 0.1660 on 200 games** — gate passed (consistent with
  the offline run's 0.1866 on a different carve).
- Iteration-1 mirror collection (50g, seeds **520002–520051**, dps
  1500, rl-seed 4300, anchor vs anchor): 100 rows → 50 learner rows →
  **2575 learner decisions**.
- **Crash (measured)**: `IndexError` in `compute_gae` via
  `gae_advantages`. The collection contained **4 zero-ask rows** — 2
  learner "loss" games (520003, 520038: a loss before the first ask,
  the seat never decided) and 2 opponent-side rows (520015 crash,
  520022 loss). With `n = 0` decisions, GAE built
  `rewards = [0]*(n-1) + [terminal]` → length 1 against an empty value
  slice. The v1 pilot's 1000g recorded file had no zero-ask games, so
  the offline path never met it; the on-policy mirror collection does.
- **Fix (worktree commit `6c7772d`)**: `gae_advantages` skips `n == 0`
  games (no decisions → no credit; neighbours untouched) — one
  defensive branch covering every consumer (offline `train()`, the
  loop, future real runs). New CPU regression test
  `test_gae_zero_decision_game` (hand-checked neighbours). Suite:
  **16 passed, 3 skipped** (cuda-only).
- Behaviour note for the era boundary: a loss before the first ask is
  a property of this broken-era engine (e.g. library-empty losses in
  the opening phase); the fix makes the loop mechanics robust to it.
  If the corrected engine still produces such games, the real-run spec
  should state this handling explicitly (the game counts in game-level
  stats, contributes no decisions).

**Retry (attempt 2, killed)**: relaunched ~05:5x; killed by an opencode
server restart ~08:00 during warm-start (no iteration artifacts).

**Attempt 3 (2026-11-03 08:10 → 11:15, wall ~3 h 05 min, COMPLETE)** —
same launch, same (deterministic) seed blocks; the GAE fix
(`6c7772d`) was in place throughout.

- Warm-start (500g / 23910 decisions / 3 epochs): last-epoch MSE
  0.84440, train EV 0.17849, **held-out EV 0.18577** (200g) — gate
  passed. (Attempt 1 measured 0.1660 on the same seeded carve: the
  difference is unseeded value-head INIT — the carve is seeded by
  `--seed`, the torch RNG is not; note for the real run: seed the
  torch RNG at start.)
- **All 5 iterations completed the full cycle** (collect → SHA guard +
  seat filter → encode → GAE → PPO w/ KL early-stop → checkpoint +
  sidecar; each iteration's collection strict-loads the previous
  iteration's sidecar via `BcAsk.fresh` — the sidecar chain worked in
  production, i1→i2→i3→i4→i5):

| it | W/L/D/X | decisions | KL/update | entropy | EV(batch) | dlogp_post | grad pre/max | epochs run | early-stop |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 16/30/2/2 | 2575 | 0.01185 | 0.0818 | 0.2535 | 0.0482 | 6.69/28.94 | 2/3 | yes |
| 2 | 21/25/0/4 | 2071 | 0.01148 | 0.0096 | 0.1288 | 0.0313 | 7.76/7.76 | 1/3 | yes |
| 3 | 22/27/0/1 | 2647 | 0.01141 | 0.0148 | −0.0391 | 0.0324 | 7.28/8.28 | 1/3 | yes |
| 4 | 23/23/1/3 | 2657 | 0.01387 | 0.0066 | 0.1121 | 0.0375 | 17.05/17.05 | 1/3 | yes |
| 5 | 18/29/0/3 | 2015 | 0.01114 | 0.0305 | −0.0334 | 0.0374 | 6.05/11.17 | 1/3 | yes |

- **Checklist tally** (pre-registration items 1–6, per iteration):
  item 2 (KL > 1e-6, early-stop respected) **5/5** · item 4 (no NaNs)
  **5/5** · item 5 (no trainer crash) **5/5** · item 6 (draws logged)
  **5/5** · item 1 (EV > 0 per update) **3/5** (fails: iters 3, 5) ·
  item 3 (entropy 0.02–0.5) **2/5** (fails: iters 2, 3, 4). Strict
  pre-registered success (ALL items, every iteration): **NOT MET** —
  two sentinel violations, both diagnostic, neither a mechanical fault:
  - **Entropy collapse** (iter 2: 0.0096 → iter 4: 0.0066): PPO with no
    entropy term (the spec's "no shaping") sharpens an already
    low-entropy BC anchor; iter 1 starts at 0.082 on the on-policy
    mirror distribution and is below the 0.02 sentinel by iter 2. The
    loop behaves exactly as specified — the spec's no-entropy choice is
    what collapses. Real-run spec item for the owner: add an entropy
    bonus or recalibrate the sentinel band.
  - **Value EV negative on iters 3/5** (−0.039, −0.033, modest): the
    value head was warm-started on the ANCHOR's state distribution; the
    policy drifts (cumulative KL ≈ 0.06 over 5 updates) while the value
    head gets few steps per update (early-stop at ~1 epoch) and every
    iteration brings 50 fresh games. Value ≈ mean baseline on those
    batches; GAE still functional. A value-lag effect, not a loop
    fault.
- **Iter-1 determinism + GAE-fix proof**: iter-1's collection
  (seed block 520002–520051) re-collected in attempt 3 is
  **SHA-256 bit-identical** to attempt 1's (`ef905a3c22932dbe83bac60e
  2dcee08a75e4fb20665652f033b9c208e5c43140`) — the on-policy
  `--rl-collect` path is bit-reproducible across process restarts.
  And iter 1's collection contains the same 2 zero-ask learner losses
  that crashed attempt 1's GAE — iter 1 completed this time: the GAE
  fix is proven on the fault data itself.
- Engine crash rate this run: 2/4/1/3/3 per 50 games — consistent with
  the known-broken engine; handled per v1 convention (crash = loss;
  zero-ask rows carry no decisions).
- Artifacts (all DISCARDED per the pre-registration; /tmp, untracked):
  `rlv2dbg_summary.json` (seed blocks + all metrics), per-iteration
  `<tag>.pt` + `<tag>_policy.pt` + `_diag.json` + `_updates.jsonl`,
  `episodes_i1..i5.jsonl` (203 MB total, plus the 45 MB archived
  first-attempt file), `collect_i1..i5.json`.
- **Conclusion**: the v2 loop is **mechanically sound** — the one
  question the pre-registration was designed to answer. Strict success
  not met; the two sentinel violations have measured root causes and
  both feed the real-run spec (entropy: owner call; value-lag:
  documented). Everything trained here is thrown away (broken engine);
  nothing here is a strength claim (mirror win rates 16–23/50 carry no
  game-theoretic content on this era).
