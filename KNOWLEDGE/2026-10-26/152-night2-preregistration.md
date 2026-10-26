# 152 — Night-2 pre-registration: reading protocol for the iter-1 mirror probe (written BEFORE the window, binding)
Date: 2026-10-26 10:40 CEST. Window: 2026-10-26 23:59 / 07:00, `--gpu-train`, frozen export (PIN 7bda5549…, export reuse expected).

## Expected chain
P0 smoke → P1 calib 50g (deterministic seed ⇒ same data as night-1) → P2: collect 1000g (deterministic seed 510201, frozen export ⇒ byte-identical to night-1's `episodes_iter1.jsonl` — verifiable by sha256 if needed), **cuda audit (minutes, expected GREEN)** → train (single REINFORCE update over 46941 asks, lr 1e-5, batch-mean baseline, frozen-anchor KL beta 0.1) → **probe 200g mirror** (rld_i1 vs frozen pre-RL anchor `bsh_S3a_s1_b`) + 200g teacher lane (descriptive only, era-drift law).

## Statistics
200 mirror games: at p=0.5, CI95 ≈ ±0.10. The probe reports `winrate_decisive` + ci95 (rig convention). Era caveat: all numbers era-local (post-R3 engine, silent-CHOOSE ask-lift); the MIRROR axis is drift-proof (both arms same era/export).

## Pre-registered readings (F4 no-op discriminator + /134 v2 verdict axis)
Let M = mirror WR point estimate, MOVED = policy actually moved (trainer diag: share|dlogp|>0.1 > 0 OR KL_post ≥ 1e-4 — the night-1 calib sat at 0.0 / 3.1e-9 = NOT MOVED).
1. **MIRROR-POSITIVE**: M ≥ 0.53 AND MOVED ⇒ learning occurred at iteration scale. ⇒ 3-seed × 400g rotated-seed confirmation BEFORE any wave-2 funding (success rule, /134 v2). The 3-seed confirmation is the gate to any strength claim.
2. **MIRROR-FLAT**: M ∈ [0.47, 0.53) AND NOT MOVED ⇒ "no learning occurred" at iteration scale — the instrument works but the lever is too weak. ⇒ wave-2 LEVER discussion (lr↑, multiple updates per iteration, lower KL beta, larger batch), NOT an "RL is negative" verdict. This is the expected-most outcome for one conservative update.
3. **MIRROR-NEGATIVE**: M < 0.47 AND MOVED ⇒ the update is actively harmful. ⇒ root-cause (baseline sign, reward mapping, crash-row handling, audit tolerance) before further funding.
4. **MIRROR-DIVERGENT**: MOVED AND reward/WR diverge (reward up + mirror WR down, or the inverse) ⇒ HALT per the /134 divergence gate: the reward is not measuring game strength.
5. **AUDIT-RED**: chain halts before training ⇒ the /151 identity/device fixes did not hold; audit root-cause is the next morning's first task. A fresh RED after the SHA fix points at real plumbing (not the cross-path artifact).
6. **Honest-skip/timeout**: any phase cut by the budget guard ⇒ record the timing ledger, re-arm; not a signal about the science.

## What does NOT count
- Teacher-lane numbers (era-drift: anchor-vs-teacher compares eras, not learning).
- Any single-run mirror point estimate without the 3-seed confirmation for a strength claim.
- The n=200 CI is exploratory for decision routing, not publishable (the design doc's statistics section sizes the confirmation).

## Timing expectation
P2 ≈ 43 min (collect) + ~10 min (cuda audit) + 10–30 min (train) + ~31 min (200g probe) ≈ 95–120 min, inside ≈ 6 h remaining at that point.
