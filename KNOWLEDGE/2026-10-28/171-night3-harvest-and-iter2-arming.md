# /171 — NIGHT-3 HARVEST (branch 2) + ITER-2 ARMING (smoke-caught wiring)

Date: 2026-10-28 (harvest ~17:00–20:40; window #4 armed 20:36, fires 23:59).
Status: **BINDING** — iter-2 window armed; pre-registered iter-2 decision table below.

## 1. Night-3 harvest (per the binding /158 table)

Window ran 23:59:00 → 02:02:39 (123 min), full chain **rc=0**, engine restored on the
normal path (gateway 200, plugin-log-check clean).

| Invariant | Result |
|---|---|
| Export | REUSE at 23:59:05 — payload fingerprint `07fd1a6e…` == working tree (third production reuse; no re-archive) |
| Episodes (1000g, seed-base 510201 / dps 1412 / rl-seed 4244) | **BYTE-IDENTICAL** to nights 1–2: SHA-256 `2e09d72b5f0caaf1540688f1180a2024c05f1741409e424a6da552d79206ab30` == `reports/episodes_iter1.jsonl` (1000 rows, 375 MB — evidence by SHA per /162, never committed) |
| audit_iter1 | GREEN: 46941 asks / 1000 episodes, **max\|Δ\| = 5.507469177246094e-4 — bit-identical to night-2's cuda audit** (share\|Δ\|>0.001 = 0.0, foreign 0) |
| audit_calib | GREEN: 2411 asks / 50 episodes, max\|Δ\| 2.52e-4 |
| Outcome rows | 403 W / 581 L / 1 D / **15 crashes** (crash-row pin from /152 holds exactly) |
| Train (lr 1e-2 × 1 step, ~24 min, GPU exclusive) | **MOVED** — `share_dlogp_gt_0p1_post` = 0.012206812807566947, `kl_mean_per_game_post` = 8.424085258158404e-4, \|Δlogp\|_post 5.193e-3, grad 2.526 (preclip, clip 1.0), KL ceiling 0.05 NOT breached; pre-key lr-blind (1.6939604285741257e-06 — bit-identical to the /158 day-smoke: **GPU training is bit-deterministic, second production datum**) |
| Probe rld_i1 (200g, seed-base 512002 / dps 1413) | **mirror M = 0.5279 [0.458, 0.596]** (104W/3D/93L decisive); teacher 0.3434 (era-local, not adjudicating); draws 3/200 (2 cap + 1 other), stall 0, 0 probe crashes |

Cross-night: night-2 mirror on the SAME probe seeds was 0.5231 — but that "rld_i1" was
the lr-1e-5 net, effectively bit-identical to the anchor (NOT MOVED, KL_post 2.4e-9).
ΔM = +0.0048 between the two is deep inside the ±0.10 noise at n=200: the instrument
works, one crossing step has not converted to strength yet.

P1 calib (diagnostic only): rld_cal (50g) mirror 0.5424 [0.417, 0.663] @60g.

## 2. Gate evaluation

- AUDIT GREEN (smoke + calib + iter1) → not /158 branch 6.
- MOVED on both keys → not branch 4 (NOT MOVED).
- MIRROR-DIVERGENT (reward/WR divergence): N/A — single iteration, no trend; mirror is
  above the anchor-field baseline (anchor vs teacher ≈ 0.44 era-local).
- Draw-detector (/134 F5, halt ≥5/200): 3 < 5 ✓.
- eval_acc F5 tripwire (drop >3pts vs pre-RL ⇒ halt): **NOT RUN in the window chain**
  (probe lanes = mirror/teacher only) — recorded gap, and it mechanistically cannot fire
  at this movement: TV(π‖anchor) ≤ √(KL·ln2) ≈ 1.1e-2, so worst-case puzzle-acc shift
  ≲ 1.1pt < the 3pt gate at KL 8.4e-4. Add the puzzle meter to the chain at the
  confirmation phase, where it is a standing gate per /134 F5.

## 3. /158 table application — VERDICT: BRANCH 2

M = 0.5279 ∈ [0.47, 0.53) AND MOVED ⇒ **"movement not yet converting in 1 iteration" ⇒
iter-2 same lever, same episodes.** (Point estimate is 0.002 under the 0.53 confirmation
line; the table is the binding pre-registration — no post-hoc boundary fudging.)

## 4. Iter-2 design — the wiring the smoke CAUGHT (PITFALL /146 vindicated)

The trainer docstring claimed "later iterations pass `--policy rld_iN.pt --anchor
<base>`". **The episode guard forbids that usage**: `load_episodes` requires
`--policy` == the COLLECTING checkpoint (SHA-256 identity; "an update over nothing
proves nothing"). Real-mode GPU smoke proved both directions:

- `--policy rld_smoke_i1.pt` on anchor-collected episodes → **correctly REJECTED**
  (RuntimeError, fail-loud).
- Correct wiring: **iteration N = ONE run `--policy <base> --anchor <base> --steps N`**.
  Pass k re-forwards the moved weights on the same recorded actions/advantages (no
  importance ratio by /134 design; grad-clip + cumulative-KL vs the frozen PRE-RL
  anchor are the stability brakes).

**Bit-equivalence proof** (not just an argument): the 2-step run's
`step_grad_norms[0]` = **50.3505744934082 — bit-identical** to the standalone 1-step
run's gradient → pass-1 ≡ the standalone run → the 2-step net **is** "rld_i1 + one more
lr-1e-2 step". Smoke numbers (2g, cuda): 1-step KL_post 7.77e-5 → 2-step KL_post
3.3550483495358536e-4 (cumulative), |Δlogp|_post 5.136e-3 → 1.1071738269161740e-2,
share_post 0.0282, grad pass-2 48.85175323486328, no ceiling breach, 39MB checkpoints.
Trainer suite 21/21 (796s). The stale docstring line is FIXED in
`tools/training/train_rl_v1.py` (PIN set — carried in the re-pin below).

Phase script (`tools/ops/rl_pilot_phases.sh`, OUT of the PIN set): `train()` gains a
`steps` arg (default 1); P2 = `train rld_i1 ep 1` + `train rld_i2 ep 2` (same episodes)
+ `probe p2 rld_i2` on seed 512002/1413 — **held** for cross-iteration comparability
(rotated-seed law is honored at the 3-seed confirmation gate, /134 v2). The rld_i1
training run is kept so the window produces both checkpoints fresh, each
independently guard-checked and bit-consistent.

Also caught during arming (dry-run value): (a) my `steps=${2:-1}` positional bug —
dry-run failed fast with `--steps: invalid int value: <episode path>`; fixed to
`${3:-1}`; (b) stale export — tools/ops changes require `rm .export_fp` to force
rebuild+overlay (documented in /154; re-verified, the 2nd dry-run at 20:18 still ran
the buggy script from the payload until the forced rebuild at 20:25).

## 5. Post-merge tree state (sibling merge `6674753`, sets/onboarding)

- **M21 byte-invariance PROVEN on the post-merge tree**: 2-game re-collect at the exact
  P2 seeds (510202/510203, seed-base 510201 / dps 1412 / rl-seed 4244) is
  **semantically byte-identical** to night-3 episodes (field-diff NONE beyond the
  cwd-dependent policy path); audit GREEN 213 asks max|Δ| 3.142356872558594e-4. The
  sets wave (S-1/S-2/S-3a/S-3b + B-45 + WAR + 15 sets) did not touch M21 simulation.
- Suite: **3505/3507** pass; the 2 fails are `MTG_bot/strategic_brain/test_model.py`
  (LLM-lane architecture tests: orphan-parameter + reasoning-loop) — game engine fully
  green. Flagged to the sibling lane; NOT fixed here (not my lane, minimal-diff law).
- **B-43 confirmed ALIVE on main**: `_build_roaming_ghostlight` destination =
  `Zone(ZoneKind.HAND, ControllerRef.ANY)` (correct: `OWNER` per /163). The
  era-boundary bundle item stays open.
- Fingerprint drift: PIN `07fd1a6e…` (pre-merge) → tree `297f66c4…` (post-merge,
  pre-docstring-fix) → **explicit re-pin `31b3b78c97d9177f2d8207715187837271a6d2bf8bc78dd2a798aa6014876f06`**
  (provenance: `/tmp/opencode/RL_PILOT_PIN` line 2 — merge + byte-check + suite +
  both smoke directions + trainer suite + docstring fix).
- Dry-run full chain **rc=0** (20:25, CPU, PIN match, rebuild+overlay of the corrected
  phase script, engine never touched, trap-chain proof fired by design).
- Old driver (pid 86345) sat in `sleep infinity` after the chain with the flock held;
  session killed — cleanup trap verified idempotent (ENGINE_STOPPED=0/RESTORED=1 after
  the normal restore), lock released, engine untouched.

## 6. Window #4 armed (iter-2 night)

20:36:41, tmux `rlwindow`, pid 4134208: `bash tools/ops/rl_window.sh --gpu-train`,
START=23:59, HARD-RESTART=07:00, preflight PASS, no cancel file, payload ready
(fingerprint == pin ⇒ 23:59 export REUSE, no rebuild). Expected chain ~150 min
(collect byte-identical ~43m + audit ~5m + train rld_i1 ~24m + **train rld_i2 ~24m** +
probe 200g ~31m + P0/P1). **Risk note**: if the sibling lane lands a PIN-set commit
(engine/compiler .py or .pt) between arming and 23:59, the pin wire aborts the window
honestly at pre-engine (payload fp ≠ pin); re-smoke + re-pin then follows their merge
note (gates as pre-merge baseline).

## 7. PRE-REGISTERED iter-2 decision table (tomorrow's probe: rld_i2 vs anchor, 200g, seed 512002/1413)

MOVED2 = `share_dlogp_gt_0p1_post` > 0 OR `kl_mean_per_game_post` ≥ 1e-4 (expectation:
yes — same deterministic pass, KL_post2 ≈ 1.7e-3 cumulative).

1. **M2 ≥ 0.53 AND MOVED2** ⇒ **3-seed × 400g rotated-seed confirmation** — the gate to
   any strength claim (/134 v2; /152).
2. **M2 ∈ [0.47, 0.53) AND MOVED2** ⇒ movement still not converting after 2 iterations
   ⇒ **lever step-up night: `--lr 1e-2 --steps 3` from the base** (a measured grid point
   on the STEPS axis — /157 lesson: measured beats extrapolated; per-pass KL increment
   under re-forwarding is unmeasured; total KL ≈ 2.5e-3, 20× under the 0.05 ceiling;
   fits the slot: ~72m train + collect + probe < 5.3h). Real-mode smoke + re-pin before
   arming. If iter-3 is ALSO flat ⇒ owner-level regime decision (the /157 branch-4
   spirit: label-information ceiling, or pivot to the era-boundary bundle).
3. **M2 < 0.47 AND MOVED2** ⇒ fallback B (lr 3e-3 × 3 steps) + root-cause
   (same as /158 branch 3).
4. **NOT MOVED2** ⇒ recalibrate the scaling law (expectation: impossible — identical
   deterministic pass over the same episodes).
5. **DIVERGENT2 / AUDIT-RED2** ⇒ HALT / root-cause (pin/pairing or plumbing failure).

## 8. Next

- 23:59 → 07:00: window #4 runs; this session may be discontinued at engine-down.
- Tomorrow: harvest per §7 (verify ARTIFACTS in `/tmp/opencode/rld_n1/`, not logs:
  `audit_iter1.json`, `rld_i1_diag.json`, `rld_i2_diag.json`, `probe_p2.json` = rld_i2;
  episodes by SHA only); commit small artifacts to `reports/` under explicit paths.
- Era-boundary bundle (§3.1.4 seat-rig fix + B-43 OWNER fix + goldens re-bake +
  re-collect scope + re-baseline + re-pin): scheduled AFTER the 3-seed confirmation
  decision or the next plateau — NOT mid-iteration-chain (cross-iteration
  comparability depends on the frozen episode baseline + frozen export).
- Legacy re-collect scope and ZNR/M20/KHM sign-offs: still owner decisions.

## 9. Reports/ convention (harvest discipline, /162)

`reports/` copies are the LATEST window's artifacts (this commit updates
`probe_p2.json`, `rld_i1_diag.json`, `timing.env` to night-3 content; adds
`audit_calib.json`, `collect_calib.json`, `collect_iter1.json`, `probe_p1.json`,
`rld_cal_diag.json`, `audit_iter1.json`, and the night ledger
`rl_window_2026-10-27.md`). Previous content remains in git history (night-2 probe =
commit `7e0ba44`). Episodes (375 MB) are NEVER committed — SHA-256 only.
