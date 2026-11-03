# /179 — MACHINE REBOOT: window #6 never fired; ladder closed; v2 core in review

Date: 2026-11-02 (~13:55–15:00, post-reboot recon + review).
Status: planning record + infra event. Supersedes the window-#6 harvest plan
in `/174 §5/§9` (the window did not run).

## 1. The infra event (measured)

- Window #6 (steps-4 FINAL ladder point) was armed Friday 2026-10-30
  12:25:43 (preflight PASS, single driver, no cancel file). `reports/
  rl_window_run.log` ends at that arming line — **the 23:59 fire never
  happened; the phase chain never ran; no GPU time was spent, no artifacts
  produced**.
- The machine **hard-rebooted** between ~23:15 and 23:59 Friday: `/tmp`
  wiped (RL_PILOT_PIN, the export payload `rl_n1_train_src`, the 375 MB
  episode baseline, the rld_i1/i2/i3 checkpoints are all gone), the armed
  tmux `rlwindow` driver died with it.
- Root-cause context (now codified as binding law in both AGENTS.md,
  updated since the crash): DGX Spark unified 128 GB — vLLM `qwen-nvfp4`
  resident at ~73 GiB + host daemons ~25 GiB leaves only 15–25 GiB free;
  a CUDA allocation on top (named in the law: CED 27B recovery or MTG RL
  CUDA batches) exhausted memory → NV_ERR_NO_MEMORY → hard reboot. The
  last GPU-heavy action in my lane before the crash was the Friday-23:15
  `pytest test_rl_v2.py` launch (cuda-parametrized); attribution is not
  provable (the CED lane is equally implicated by the law's text), but the
  operating rule stands regardless: **while vLLM is resident, all ML work
  is CPU-default; GPU training happens only in the engine-down window
  (which is what the nightly windows are for)**. The v2 code already
  enforces this (`assert_cuda_headroom(25.0)`, `@needs_safe_cuda` with
  automatic CPU fallback in the tests; `--device` defaults to cpu).

## 2. Post-reboot state (verified this morning, all on durable disk)

| Item | State |
|---|---|
| Engine | gateway 200, container up (restored) |
| Tree fingerprint | `31b3b78c97d9177f2d8207715187837271a6d2bf8bc78dd2a798aa6014876f06` = **PIN-MATCH** (the old pin; no era-merge happened; the fingerprinted tree is exactly the one all five nights used) |
| Anchor `bsh_S3a_s1_best.pt` | intact (39 MB, untracked working-tree file, main tree) |
| Main tree git | clean except nothing new: the sibling's long-dirty `test_duel.py` was committed by them as `c251d46` (2026-11-01, test file — fingerprint-excluded); no other main commits since my `2c58ee1` |
| v2 worktree | intact at `/home/sune/.local/share/opencode/worktree/30c75f/rl-v2`; subagent work **committed** as `ed95c11` (2026-11-01 22:35): `train_rl_v2.py` (1170 lines), `test_rl_v2.py` (720), `RL_V2_DEBUG_PRE_REGISTRATION.md`, the `ab_duel.prepare_ask` refactor (worktree-only) |
| Episode baseline | **regenerating now** (background collect, pinned tree + seeds 510201/1412/4244, 1000g) — expected byte-identical SHA `2e09d72b5f0caaf1540688f1180a2024c05f1741409e424a6da552d79206ab30` (would be the 6th production determinism datum; result in the addendum) |

## 3. Decision: the steps-4 point is SKIPPED (recorded, justified)

The pre-registration (`/173 §6` branch 2) had armed steps-4 as the FINAL
measured axis point with the ladder ending after it **regardless of M4**
and the regime decision then going to the owner. That decision has since
been made by the owner in `/176` (RL v2; the ladder is replaced, real runs
wait for the era merge). Consequences:
- M4 has **zero decision value** in any pre-registered path: the ladder
  ends after it either way, and no gate reads it.
- Re-arming one full night (~10 h wait + 4 h chain) for a data point no
  decision depends on is not a good use of the slot; the axis record
  stands as {1: 0.5279, 2: 0.523, 3: 0.518} — flat within noise,
  movement-not-converting, as /174 recorded.
- The 4th point remains **regenerable on demand**: the pipeline is
  bit-reproducible (proven 5×), the tree is PIN-MATCH, the episodes
  regenerate byte-identically — one night's window if the owner wants the
  completed axis. Nothing is lost; only a pre-committed completeness
  datum is deferred.
- Recorded as a deviation from `/173 §6`, with cause (machine reboot
  killed the armed driver before fire) and the above justification.

## 4. v2 offline core — review result (code read in full, 1170 + 720 lines)

- **Spec conformance**: value head = one scalar `nn.Linear(d,1)` on the
  same SEP-state `h` the pointer reads; the policy `forward` is inherited
  untouched, so the bit-identity invariant is structural (no new ops on
  the policy path), not just asserted. GAE(γ=1, λ=0.95, terminal 0) pure
  Python, unit-tested against closed forms. PPO clip 0.2, Adam policy
  3e-4 / value 1e-3, 3 epochs, minibatch 256, KL early-stop 0.01 (running
  mean vs the frozen anchor's cached full-menu logp), grad clip 5.0
  (rationale: measured raw norms on the 1000g batch, binds <5%). Padded
  decision batching with mask-invisibility unit tests. Warm-start
  supervises the value head only (policy frozen and restored; fail-loud
  key checks on load; offline guard bypass is loud).
- **Reward semantics verified empirically**: win +1 / loss −1 / draw 0 /
  crash = −1 reproduces v1's recorded `reward_var = 0.961751` exactly from
  the 403W/581L/1D/15X split (a win/loss-as-1/0 scheme would give 0.2406 —
  the discriminator).
- **Memory-law compliance** (post-crash law): `--device` defaults to cpu;
  `assert_cuda_headroom(25.0)` guards every cuda entry; the tests use
  `@needs_safe_cuda` (≥30 GiB headroom) with automatic CPU fallback.
- **Tests not yet run**: the interrupted Friday pytest never completed;
  the episodes input was wiped. Full suite runs once the regeneration
  lands (addendum).
- **Gap (known, pre-registered)**: the on-policy collection loop does not
  exist yet — the module ships the ON-POLY HOOKS (load_policy,
  build_anchor, encode_episode schema, warm_start_value, ppo_update,
  compute_gae) that the loop will call; collection vs the frozen anchor
  (model-vs-model `--rl-collect`) is the next wiring step. The collector's
  seat-routing consumers are still the pre-era version (active_player
  routing) — the era-boundary fix from /177 §2, recorded in /178.

## 5. Plan (in order)

1. Episode regeneration completes → verify SHA `2e09d72b…` (addendum).
2. Full `pytest test_rl_v2.py` (CPU fallback active while vLLM is
   resident) → addendum with the measured numbers (bit-identity, warm-
   start EV, PPO KL/entropy/grad norms).
3. Offline end-to-end CLI run (50g, 1 iteration, cpu) → first v2 log
   lines on the real rig.
4. Wire the on-policy debug loop (verify the eval CLI supports model-vs-
   model `--rl-collect` with policy-a = v2 checkpoint, policy-b =
   anchor); run the 5-iteration DISCARDED debug run per the
   pre-registration (CPU per the memory law; results answer "is the loop
   mechanically sound" only).
5. Era-boundary coordination unchanged: gated on the owner's OK + a gap
   between RL windows + the sibling's `cards/integration` merge; then
   re-smoke, re-pin, re-certify, re-baseline, re-collect, tokenizer
   re-evaluation (law §8), and the v2 REAL runs with the plan's strength
   pre-registration.

## 6. Addendum (post-regeneration + test results)

_(appended below when the background collect and the pytest suite land)_

### 6.1 (2026-11-02 evening — results moved to /180)

- **Episode regeneration: COMPLETE** (1000g, wall 4839 s under engine
  contention; profile 403W/581L/1D/15X — identical to the five-night
  baseline). File SHA `2bbdad3d…` ≠ the pinned `2e09d72b…`: the
  difference is SOLELY the per-row `policy` path string (this run used
  the main-tree anchor path, the nightly windows the export cwd's).
  **Content identity is proven, not assumed**: the cpu-to-cpu logprob
  audit re-derives all 46941 asks, max|Δ| = 0.0, mean|Δ| = 0.0 (the
  nightly cuda-vs-cpu audits measured 5.507e-4). Full record:
  **/180 §1 + NUMBERS**.
- **pytest `test_rl_v2.py` (CPU, vLLM resident → 3 cuda-only tests skip
  per the memory law)**: 14 passed / 3 skipped in 113.91 s (pre-fix).
  Later results (post value-head fix, post chunking fix, post GAE
  fix): 15/3, then **16/3** — all in /180 §2/§7 with the
  commit history.
- Plan §5 progress: item 1–2 done (above); item 3–4 in flight (the
  offline CLI passed end-to-end; the on-policy debug loop is
  retrying — /180 §7.2–7.3); item 5 unchanged.
