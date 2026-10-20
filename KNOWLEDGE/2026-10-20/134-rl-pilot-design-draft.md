# 134 — RL-PILOT DESIGN (Door B, "few RL" per owner end-game law 295733c) — v2, adversarial-gated

Status: v2 REVISED per adversarial round 1 (3 FATAL + 2 AMEND, all applied below). Owner GO still required; engine-off window via proven R1 pattern.

## v2 amendments (gate findings → fixes, binding)
- **F1 (FIXED — pre-anchor precondition + verdict moved to engine-controlled axis)**: SUCCESS/NULL verdict is the **mirror CI-lb vs the frozen pre-RL bsh_S3a_s1 (> 0.5 after 400g rotated-seed)**; teacher rows are DESCRIPTIVE ONLY (era-drift law /133). PRECONDITION (already dispatched, model lane, 2026-10-20): fresh 400g bsh_S3a_s1-vs-teacher anchor on the current engine (`gameplay_anchor_bsh_cur_engine.json`, seed-base rotated) — without it the pilot does not start.
- **F2 (FIXED — honest budget, multi-window)**: collection rate re-stated 0.09–0.19 g/s net-rollout (my own 1.5–3h/1000g math; R1 measured 0.133 g/s greedy). Plan = pre-registered **50-game calibration run** on window night 1; the pilot spans MULTIPLE windows; engine stays pinned DOWN across consecutive windows (owner opt-out each morning); overrun rule = restore engine immediately, resume next window; late restore = hard violation.
- **F3 (FIXED — the pilot is re-labelled INSTRUMENT CALIBRATION, not verdict-bearing)**: power math accepted (200g ⇒ ±0.035 1se; cannot separate +0.05 at 80% ⇒ NULL at 200g would be uninformative). Verdict-bearing follow-up = 1,000g/probe (or 3-seed×400g rotated) ONLY if calibration shows gradient actually moves policy (F4 diagnostics). Pilot outputs: does learning happen at all + measured variance components — never "Door B dead" (that claim requires the powered follow-up, /83 budget-honesty law).
- **F4 (FIXED — no-op ≡ collapse discriminator + plumbing precondition)**: PRECONDITION 2: action-logprob RECORDING in the rollout path (gen_games `--net` today is menu-pruning only — verified) + off-policy audit script (recorded vs re-computed logprobs, one net — precedent bug: /83's silently-dropped pi_mix). Gates per iteration: cumulative-KL vs BC anchor (ceiling, not just step-1 tuning), entropy, grad-norm trace, outcome-vs-Δlogπ shift. Flat diagnostics ⇒ verdict is **"no learning occurred"** (pipeline/optimization), never "lever negative."
- **F5 (FIXED)**: all probe duels use ROTATED `--seed-base` + `--deck-pairs-seed` per iteration (D9 law: seed-keyed lookup measured +0.400 divergence); draw-detector = halt at ≥5 draws/200 (binomial p<0.01 vs observed 0/200 pre-RL baseline — well-defined at zero); + eval_acc puzzle-meter gate per iteration (catastrophic-forgetting tripwire: eval_acc drop > 3pts vs pre-RL ⇒ halt).
- **N1 (APPLIED)**: reward/WR divergence halt fires on ANY single iteration (not 2-and-3); crash convention pre-registered: crashes count as losses for WR (existing rig convention, cited r1_window 8/200); SUCCESS auto-triggers 3-seed×400g rotated-seed confirmation before any wave-2 funding.
- **N2 (APPLIED)**: opponent set adds **ε-greedy teacher (ε=0.1) arm** to catch exploit-only gains vs the greedy anchor.

## Why (one line)

> v1 body below kept verbatim (chronology law); where it conflicts with the v2 amendments above, v2 governs.
/133 ledger: tokens/volume/labels/capacity all NEGATIVE — only outcome-driven learning can exceed the greedy-teacher label ceiling.

## Pilot spec (simplest implementable — no new architecture)
- Base net: bsh_S3a_s1 (frontier clone, live vocab, hash-pinned; live-UNK probe per checkpoint — drift law).
- Objective: REINFORCE with batch-mean baseline on OUTCOME reward (+1 win, −1 loss, 0 draw), sum of logπ over the side's OWNED asks per game. No value head, no bootstrapping, no PPO (pilot honesty: with ~1e3 games/iteration the critic would be noise; a baseline is all that is supported).
- Opponents: FROZEN teacher bc9_S3_s1 (greedy) only. No self-play league in pilot (non-stationarity confound; owner law: one lever at a time).
- KL anchor: penalty β·KL(π‖π_BC) against the frozen clone (β tuned so mean-KL/game ≤ 0.05 at step 1; raise if policy collapses).
- Iterations: 3 × 1,000 games collected engine-off (≈ 1.5–3 h/iter at measured ~0.3–0.6 g/s net-rollout rate), LR 1e-5, grad-clip 1.0, entropy bonus 0.001.
- Gates (pre-registered, WR-meter law): after each iteration, WR-probe 200g vs teacher + 200g mirror vs pre-RL bsh_S3a_s1 (v2 rig).
  - HARD STOPS (any): illegality/ill>0; live-UNK > 0.01; draw-rate vs teacher > 2× pre-RL baseline (stall-hack detector); mean game turns shift > +30% (stall detector); train reward rises while WR-probe falls in BOTH iterations 2 and 3 (reward-metric divergence → stop).
  - SUCCESS: after iter 3, WR vs teacher CI lower bound > clone's pre-RL 200g point 0.426 → escalate to proper wave (design round 2: baseline upgrade + opponent league).
  - NULL: CI covers 0.426 with flat trend after iter 3 → Door B declared dead AT PILOT BUDGET (not at RL-in-general — budget honesty per /83 lesson: state what budget the verdict covers).
- Seeds: 1 for pilot (verdict-bearing claims get 3-seed follow-up before NUMBERS promotion, standing law).

## Known traps pre-armed
- Draws/turn-cap stall hack: two detectors above (draw-rate, turn-shift) + teacher is greedy (stalling vs greedy = losses, cheap to detect).
- Vocabulary drift: vocab rebuilt from LIVE RL episodes is FORBIDDEN mid-pilot (pin: hash of bsh vocab); new tokens ⇒ stop (not silently learned).
- VCS law: episodes + checkpoints per iteration, distinct names rld_i{1,2,3}; `--out-episodes` always passed (trap twice bitten).
- Admission: every cited checkpoint passes WR-probe admission before serving any data-gen.

## Explicit non-goals
No MCTS-in-the-loop (mcts net-rollout was /83-noisy — outcome RL is the orthogonal lever); no AZ re-arm (Door A stays parked); no self-play league; no value head; no new atoms.

- **Precondition 1 SATISFIED (2026-10-20)**: fresh current-engine anchor done — bsh_S3a_s1 vs teacher **0.394 [0.347,0.442]** (400g, seed-base 991001, 0 ill, 1 draw). Precondition 2 (logprob recording + off-policy audit) awaits owner GO to build.
- **GO received (owner "Go ahead" 2026-10-20)**; Precondition 2 SHIPPED (commit 140caee, /137 impl note) — sampling collection flag-gated, audit discriminator cross-process-verified; trap caught: FIFO choose-stash pinned into rows.
