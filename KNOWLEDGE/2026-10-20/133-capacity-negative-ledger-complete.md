# 133 — Capacity lever NEGATIVE (S4×3, 35M, engine-off window): plateau ledger COMPLETE — all four cheap escalations dead; label information is the binding constraint

Date: 2026-10-20. Window: owner-authorized (rulings /130) detached script, engine OUT 23:59→restored early after 03:09 completion (verified GW-OK + model list at 06:13, zero contention training — clean compute by construction).

## Result (all executed, files cited)
- Arms: S4 = 35.4M params (d=512, L8, H8, ff=3072) × 3 seeds on episodes_champ_big (4,564 eps / 13,966 v2 rows), long-epoch; `r1c_S4_s{1,2,3}*.pt` on disk (VCS law: `.pt` gitignored, bc3-era tracked only).
- Puzzle meter: **eval_acc FROZEN at 0.707 from epoch 0 through epoch 11** while train_loss fell 0.31→0.005 = pure memorization of the 199-row joined eval. PASS margin gate (6.39 se) but zero generalization signal.
- Duels (200g/seed, v2 rig, `tools/eval/gameplay_r1_s{1,2,3}.json`):
  - mirror vs frontier bsh_S3a_s1: **0.426 / 0.418 / 0.426** (CIs cross-or-below parity) — 3.5× params do NOT beat the 10M clone.
  - vs teacher bc9_S3_s1: 0.332 / 0.325 / 0.330.
- CONFOUNDER LAW applied: the teacher row rides engine drift (post-ZND//125 engine vs bsh_s1's Oct-13 anchor) → NOT the valid comparison. The MIRROR duel is engine-controlled (both nets play the same current engine) and says: S4 ≈ (slightly below) S3a clone. 3-seed law satisfied; seed spread ±0.004.

## Ledger COMPLETE — the four cheap escalations, all with numbers
1. **Tokens** (/78): digit-tokenized numeric lanes — no premium.
2. **Volume** (/80): 5.9× shadow data — no lift (0.359 band).
3. **Labels** (/83): cheap search-improvement (cap15/N8) — WORSE than expert labels; raw-UCB concentration superseded-part.
4. **Capacity** (this): 3.5× params, clean GPU, long epochs — at/below clone parity, puzzle meter frozen.

**Honest statement: the imitation regime is capped at the greedy-teacher class (~0.33–0.43 from clone view). Binding constraint = LABEL INFORMATION (teacher-level), not model class, data quantity, tokenization, or search-shallow improvement. Corroborates owner end-game criterion (commit 295733c): "new set = atomics + few RL".**

## Fork (Type-1 → owner ruling; RL direction already blessed in spirit by T-G backlog)
- DOOR A (only upward door short of outcome-RL): better teacher — e.g. deeper-budget AZ re-arm at champion anchors; /74 diagnosed greedy-rollout; /83 says shallow search labels are noise. Expensive, uncertain.
- DOOR B (blessed direction): **few RL** — outcome-driven fine-tune of BC clone on self-play vs frozen teacher opponents, WR-meter gated every iteration, legality-gated action space already engine-enforced. Needs: advantage/reward plumbing on the existing gen_games + gameplay_eval_v2 rigs; GPU window pattern proven by R1.
- DOOR C: accept clone ≈ teacher-class agent as the shipping policy; spend next effort on ontology/atomics (sibling lane: R1b/R2/R3, /131 faces) which raise the CEILING for any later RL.

Recommended: B as pilot (tiny: 1 seed, WR-gate, hard stop rules), C continues in parallel regardless. A stays parked (AZ arc closed /67–/74 — do not re-litigate without B failing).
