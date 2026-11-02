# RL v2 debug-run pre-registration (DISCARDED runs)

Date: 2026-10-30 (before the first debug run of the v2 loop)
Status: pre-registered — do not edit the success criteria after the first run.

## What is run

Tomorrow's RL v2 loop debug run, exactly as the owner spec
(`docs/PLAN_COMPONENT_TRAINING.md` §"First make RL work", plan item 7)
prescribes:

- **5 iterations × G = 50 fresh games** (2,350 learner decisions per
  iteration at ~47 asks/game) against the **frozen anchor**
  (`bsh_S3a_s1_best.pt`, bit-identical weights, `eval()` mode, never
  trained) as opponent.
- Trainer: `tools/training/train_rl_v2.py`, offline mode on the
  recorded-episode rig for the pipeline mechanics; on-policy
  collection is the loop being debugged.
- Anything trained in this run is **thrown away** (today's engine is
  known-broken: tap ignores summoning sickness, mana banks across
  turns, planeswalkers reset at 0 loyalty, Azusa land plays). The
  corrected engine comes after the era-boundary merge.

## Success = mechanics checklist (ALL must hold, every iteration)

1. Value head explained variance **> 0** (per update and warm-start
   held-out; triage rule #1).
2. KL per update **> 0** (the update is not a no-op; triage rule #2)
   and **< 0.01** (early-stop threshold respected; policy did not
   leave the anchor neighborhood).
3. Entropy **0.02–0.5 nats** per decision (no exploration collapse, no
   divergence blow-up).
4. **No NaNs** in any loss, logp, advantage, or value output.
5. **No crashes** in the loop itself (an episode outcome of `crash` is
   scored as a loss, per v1 convention; a trainer crash is a failure).
6. **Draw rate is logged** every iteration (stalling is a known
   exploit; a rising draw rate is a triage signal even when the other
   five hold).

## Explicitly NOT claimed

- **No strength claim.** This run does not demonstrate that the policy
  improved. The plan's strength pre-registration (mirror win rate vs
  the frozen start ≥ 0.55 with 95% CI above 0.5 at n = 400 paired
  fresh seeds, within 100 iterations / 5,000 games) applies to the
  REAL run on the corrected engine, not to this discarded debug run.
- The games are collected on today's (broken) engine, so even a
  "passing" debug run has no game-theoretic content.
- Pass/fail here answers one question only: **is the v2 loop
  mechanically sound** (value head learns, PPO moves the policy within
  the KL budget, entropy stays healthy, logging is complete)?

## Triage order (same as the plan)

1. Value head explains nothing → fix it before tuning anything else.
2. KL stays near 0 → the update is a no-op; check the pipeline.
3. (Real run only) Mirror below 0.47 → stop and inspect games.

## Amendments (mechanics changes, before the first loop run)

**A1 (2026-11-02, worktree commit 7bad492): value head input is
`[h ⊕ 5 raw state features]`.** Trigger: triage rule #1
fired in the first offline validation — warm-start held-out EV
**-0.0002** ≤ 0. Root cause measured, not assumed:
- linear probe on the encoder's SEP state `h` alone: holdout EV ≈ 0
  (10 epochs, 200g train / 100g hold; independent of the trainer's
  plumbing — the trainer's own warm-start agrees, ev_train 0.013).
- raw obs features `[life_diff, turn, board_diff, hand_size]` alone:
  holdout EV **0.256** (all decisions) / **0.499** (last third),
  700g train / 300g hold.
- Conclusion: the BC encoder's decision-tuned readout discards the
  outcome signal; the raw state carries it. The value head now reads
  `cat([h, life_diff/20, turn/20, board_diff/5, hand_size/8,
  is_active])` (5 normalized features, learner perspective, fixed
  constants). The **policy path is untouched** — bit-identity vs the
  standalone anchor re-passes on the real checkpoint.

Spec note (re-read of plan Step 4 item 2, 2026-11-02): the owner spec
says the value head is "a scalar head on the policy's encoder that
predicts the game's outcome **from the board** at each decision". The
first implementation over-narrowed "from the board" to "from the
encoder's hidden state h" (module docstring: 'one scalar linear layer
on the encoder step state'). A1 restores the spec's actual wording:
the board's raw features are read directly alongside h. This is a
spec-fidelity fix, not a deviation — the success checklist above is
UNCHANGED. For the REAL run post era-merge this design should be
re-examined against the corrected engine's obs (owner call if a
different value architecture is preferred, e.g. an MLP on h).
