# 156 — Night-2 harvest: FIRST FULL PILOT NIGHT (rc=0, 114 min); MIRROR-FLAT per /152 (policy not yet moved: step-size arithmetic); lever for night-3 = lr 10×, re-smoked, re-pinned
Date: 2026-10-27 morning. Window 2026-10-26 23:59 → 2026-10-27 01:54 (full chain rc=0, engine restored 01:54:15). Export: **reused** (fingerprint match at 23:59:05 — the /151 guard proven in production; payload == night-1's frozen export).

## Chain (all GREEN)
| phase | wall | notes |
|---|---|---|
| P0 smoke (2g) | 13 s | audit GREEN, train OK |
| P1 collect 50g | 155 s | 0.323 g/s net (cpu, 6 workers) |
| P1 audit 50g (cuda) | 18 s | GREEN |
| P1 train 50g (cuda) | ~75 s | grad 12.8→1.0, KL_post ~3e-9 (not moved) |
| P1 probe 60g | ~540 s | mirror 0.5xx vs frozen anchor (instrument warm-up) |
| **P1 wall** | **814 s** | budget guard: have 24359 > need 17352 (=814×18+2700) ⇒ P2 proceeds |
| P2 collect 1000g | 2600 s | **0.385 g/s net**; deterministic seed ⇒ same 1000 episodes as night-1 (incl. 15 crash rows, below) |
| P2 audit 1000g (cuda) | 330 s | **GREEN; max\|Δ\| = 5.507469177246094e-4 — BIT-IDENTICAL to the day-before smoke** (cuda audit is deterministic across runs on the same export) |
| P2 train 1000g (cuda) | 1438 s | 1 SGD update over 46941 asks, lr 1e-5 |
| P2 probe 200g | 1625 s | the verdict axis |

## The numbers
- **iter-1 train diag (rld_i1)**: grad_norm 2.526→clip 1.0; mean|dlogp_chosen| = **1.69e-6**; KL_post = **2.4e-9**; share|dlogp|>0.1 = **0.0**; reward_var 0.962; 15 crashes (crash = loss reward, /134); entropy 0.064; kl_ceiling_breach false.
- **Mirror (200g, verdict axis)**: `rld_i1 vs frozen pre-RL anchor = 0.523 [0.453, 0.592]` (102W 5D 93L, 23.1 turns, ill 0, dmgdiff +0.94, lead@7 0.390).
- **Teacher (descriptive only, era-local)**: 0.343 [0.281, 0.412].
- **Crash datum**: 15/1000 (1.5%) engine crashes during anchor-driven collection (X column of the collect matchup; probe 200g: X=0). Engine-error rate on model-driven play — feeds the benchmark release gate "engine-error rate below an agreed bound on a model-driven soak" (DESIGN §10).

## /152 verdict — **MIRROR-FLAT** (branch 2, the expected-most outcome)
M = 0.523 ∈ [0.47, 0.53) AND NOT MOVED (share|dlogp|>0.1 = 0, KL_post 2.4e-9 < 1e-4) ⇒ **"no learning occurred at iteration scale — the instrument works, but the lever is too weak"** ⇒ wave-2 lever discussion, NOT an "RL is negative" verdict. The 0.523 mirror point estimate is consistent with game-noise around a functionally identical net (KL 2.4e-9 ⇒ the two nets are interchangeable; expected mirror WR = 0.5 ± sampling noise, CI covers 0.5).

### Step-size arithmetic (why)
SGD (raw, no adaptive scaling — train_rl_v1 line 275), lr 1e-5, grad clip 1.0, one update ⇒ weight step ≈ 1e-5 in norm ⇒ observed mean|dlogp| 1.7e-6, KL 2.4e-9 — exactly the sub-threshold regime the MOVED discriminator is built to catch. The reward signal is non-degenerate (reward_var 0.962, grad norm 2.5 before clip); the update is being applied; it is just invisible per iteration.

## Lever for night-3 (pre-registered in /157)
**lr 1e-4 (10×), same single update, same frozen episodes, same KL beta/clip/probe.** One-number change (phase-script `train()` line, documented); the changed dimension is re-smoked in real mode (trainer on the real 1000g episodes, cuda, under session contention) before re-arming. Expected: MOVED becomes true (share|dlogp|>0.1 > 0 and/or KL ≥ 1e-4); if the 200g mirror then reads ≥ 0.53 ⇒ /152 branch 1 (3-seed × 400g confirmation gate); if MOVED but mirror flat ⇒ "movement not yet converting to strength at 1 iteration" ⇒ one more iteration at the same lever (iter-2 on the same episodes, ratio starts at ≈1, clip protects); if lr 10× STILL not MOVED ⇒ escalate to owner with the {lr} × {steps} grid evidence. Re-pin is explicit + provenanced (payload tree changed).

## PIN
First full-chain success occurred; the window's self-pin correctly did NOT overwrite the pre-existing PIN (guard: only writes when absent). Provenance line appended manually (fingerprint unchanged: payload identical).
