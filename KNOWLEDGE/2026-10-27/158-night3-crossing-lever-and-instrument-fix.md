# 158 — Instrument fix (phantom F4 axis removed), multi-step trainer, and the CROSSING lever for night-3: lr 1e-2 × 1 step; /157 grid proven infeasible by measurement
Date: 2026-10-27 morning. Binding for the night-3 window (23:59 / 07:00, `--gpu-train`).

## Why this entry exists
/157 pre-registered night-3 at lr 1e-4 (single update) with branch 4: "NOT MOVED at lr 1e-4 ⇒ escalate to owner with the grid {lr ∈ 1e-4, 3e-4, 1e-3} × {steps ∈ 1, 10, 20} — regime choice is owner-level". The real-mode smoke at lr 1e-4 on the actual 1000g episodes returned, and it carries two findings that change the picture:

## Finding 1 — the MOVED discriminator had a phantom axis (measurement-layer bug, fixed)
`mean_abs_dlogp_chosen` (line: `abs(lp_i - recorded_logp)`) is a **PRE-update consistency check** — it measures whether the loaded model reproduces the recorded logπ. It is **bit-identical across lr values**: 1.6939604285741257e-06 at BOTH lr 1e-5 (night-2) and lr 1e-4 (smoke), on the same episodes. It can therefore NEVER evidence that the update moved the policy, and `share_dlogp_gt_0p1` (built on it) can never fire on learning. Only `kl_mean_per_game_post` — a fresh forward of the POST-update weights vs the frozen anchor — measures movement: 2.43e-9 (lr 1e-5) → 1.23e-7 (lr 1e-4). Ratio **50.9 per 10× lr ⇒ KL ∝ lr^1.707** (measured, not assumed).
Fix (implemented + tested): `mean_abs_dlogp_chosen_post` and `share_dlogp_gt_0p1_post` — per-ask chosen-action |Δlogp| of the update itself (post model vs anchor), computed in the existing post-KL loop; `None` when the post-check is skipped. Corrected MOVED definition for night-3: **share_dlogp_gt_0p1_post > 0 OR kl_mean_per_game_post ≥ 1e-4**. (The pre keys remain as identity/consistency checks; `share_dlogp_gt_0p1_pre > 0` is now an IDENTITY-FAILURE signal, not a movement signal.)

## Finding 2 — the /157 grid was set too low (my pre-registration assumed pure-quadratic scaling p=2; measured p=1.707) and is infeasible as written
KL_post(L) ≈ 1.23e-7 × (L/1e-4)^1.707, single step:
- 1e-4 → 1.2e-7 (measured: sub-threshold)
- 3e-4 → 8.0e-7; 1e-3 → 6.3e-6 (sub-threshold)
- **1e-2 → ≈ 3.2e-4** (crosses: 3.2× over the 1e-4 threshold, 150× under the 0.05 KL ceiling)
Multi-step within the pre-registered grid (drift accumulates ~linearly in step count): 1e-3 × 20 ≈ 1.3e-4 — the ONLY crossing point in the grid — but 20 steps ≈ 8 h GPU > the ~5.3 h P2 slot. 1e-3 × 10 ≈ 6.3e-5 and 3e-4 × 20 ≈ 1.6e-5: sub-threshold. ⇒ **The grid as pre-registered cannot produce a MOVED night; the crossing regime is {larger single step} or {many steps at 1e-3} (window-infeasible).**

## Fix 2 — multi-step support (the other axis of the lever, ready)
`train(..., steps=N)`: successive REINFORCE passes, each re-forwarding with the CURRENT weights (the forward model IS the loss reference — no importance ratio; repeated passes are successive updates, not replays). Per-step: zero_grad → full pass → clip (norm ≤ 1.0) → SGD step. Brakes unchanged (grad clip, KL ceiling vs frozen anchor). `step_grad_norms` reported; anchor menu cached on first pass only. Default steps=1 (bit-identical behaviour for all existing tests). Trainer: `--steps` CLI.

## Tests (suite 13/13, 781 s)
- new: `test_post_update_dlogp_responds_to_update` — post-dlogp strictly larger at lr 0.01 than 1e-5 on the same owned batch (the property the old key lacked); consistency key asserted lr-blind.
- new: `test_multi_step_moves_more_than_single` — steps=3 moves more than steps=1 (KL_post and post-dlogp both), step count + per-step grad norms reported.
- all 11 prior tests unchanged and passing.

## Real-mode smokes (PITFALL law: the changed dimensions smoked in real mode, not just dry)
1. lr 1e-4 × 1 step, real 1000g episodes, cuda (under session contention): rc=0, post-dlogp mean **5.196e-5** (30× the pre key — the new key is live and responding), share_post 0.0, KL_post 1.235e-7 — confirms lr 1e-4 does NOT cross.
2. lr 1e-2 × 1 step (the armed point), real 1000g, cuda (under session contention, 42m16s): rc=0; post-dlogp mean **5.193e-3** (100× the lr 1e-4 value — linear in the step, as predicted); **share_dlogp_gt_0p1_post = 0.0122** (1.22% of the 46941 asks moved > 0.1 nats — BOTH MOVED conditions fire for the first time); **KL_post = 8.424e-4** (measured 2.6× ABOVE the p=1.707 extrapolation of 3.2e-4 — the fit is conservative at this scale; 8.4× over threshold, 59× under the 0.05 ceiling, no breach); consistency key bit-identical across all three lr values (1.6939604285741257e-06 at 1e-5 / 1e-4 / 1e-2 — identity semantics confirmed).
3. Phase-chain dry run (after the explicit re-pin: rebuild from the pinned payload, new trainer sha256=145b1715f887 + new driver sha256=76f2e96aa029e overlaid): FULL CHAIN rc=0; the dry train diag shows lr 0.01, steps 1, post keys live — the lever path is proven through the phase chain, not just the direct CLI.

## Night-3 arming — Point A, with explicit deviation from /157 branch 4
**Armed lever: `--lr 1e-2 --steps 1`** (phase-script `train()`, one documented line change; expected ~24 min GPU, fits with margin).
- **Rationale**: cheapest crossing of the MOVED threshold; single BOUNDED step (clipped step norm exactly 1e-2 — no accumulation risk); measured smoke margin: 8.4× over threshold, 59× under the KL ceiling; mirror probe + branch-3 halt + 3-seed gate protect against "moved but worse"; frozen anchor + deterministic re-collectible episodes ⇒ the night is fully reversible (worst case: one window spent, root-cause branch fires).
- **Fallback B** (if A reads MOVED + M < 0.47, i.e. actively harmful — the step overshot the batch-noise limit): lr 3e-3 × steps 3 (~72 min; expected KL_post ≈ 1.4–2e-4). Pre-registered here, not discovered later.
- **Deviation record (binding transparency)**: /157 branch 4 assigned the regime choice to owner level. Owner's standing GO (2026-10-25: "continue the RL pilot") + today's standing instruction ("continue work autonomously, without waiting for manual confirmation") + the measured infeasibility of the pre-registered grid ⇒ I take the minimal-risk crossing point. Revocation: `/tmp/opencode/RL_WINDOW_CANCEL` (owner morning opt-out, re-checked before EVERY phase; engine never touched if present). If the owner objects, the cancel file stops the night before the engine goes down.

## Decision table for night-3 (200g mirror probe, same rig/axis as /152; corrected MOVED definition above)
1. **M ≥ 0.53 AND MOVED** ⇒ learning visible AND converting ⇒ **3-seed × 400g rotated-seed confirmation** (/134 v2 gate to any strength claim).
2. **M ∈ [0.47, 0.53) AND MOVED** ⇒ "movement not yet converting at 1 iteration" ⇒ **iter-2 at the same lever** on the same episodes (importance ratio starts ≈1 — the shift is ~1e-3–1e-2 logp-scale, clip protects; off-policy recording is the ANCHOR's, so iter-2 trains on the same anchor-recorded logπ with the moved net as starting policy).
3. **M < 0.47 AND MOVED** ⇒ actively harmful ⇒ **fallback B next night** (pre-registered above) + root-cause (reward mapping; 15 crash-loss rows = 1.5% of batch, same as nights 1-2).
4. **NOT MOVED at lr 1e-2** (should be impossible: 8.4× smoke margin) ⇒ the extrapolation is wrong or the measurement changed ⇒ recalibrate the scaling law with a second measured point before any further funding.
5. **MIRROR-DIVERGENT** (reward/WR divergence) ⇒ HALT per /134.
6. **AUDIT-RED** ⇒ pin/episode pairing failure (should be impossible — audit is bit-deterministic on a frozen export) ⇒ root-cause before training.

## Invariants (violation = data invalid)
- Same frozen anchor `bsh_S3a_s1_b` as nights 1-2 (verdict axis comparable only if the anchor never changes).
- Episodes byte-identical (deterministic seed 510201 + frozen export; 3399238 bytes, 15 crash rows).
- Export reuse by fingerprint; **PIN re-pinned explicitly** (payload tree changed: trainer + tests) — old fingerprint 7bda5549… superseded with provenance; the /151 guard must show "PIN match" at arming, never "PIN DRIFT".

## What does NOT count (same as /152)
Teacher lane (era-local); single-run mirror without 3-seed confirmation for strength claims; n=200 CI as publishable.
