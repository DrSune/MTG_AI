# 198 — r27's mulligan ran away: length-sorted minibatches were optimizer steps

**Context.** Found while scoring window 2 (2026-11-12 15:10-16:40). r27 was paused at 15:24
during update 170; its last save is update 165's. The fix is f83f4db. Evidence:
`reports/mulligan_runaway_2026-11-12/` (scripts) and `runs/diag_mull_2026-11-12/` (outputs).
NUMBERS has the commands.

## 1. What happened

**r27's mulligan asks per game** (the learner's declarations; every ask after a game's first is a
mulligan; means per block of updates, the last row per update):

| 1-10 | 41-52 | 71-80 | 101-110 | 131-140 | 151-165 | 167 | 168 | 169 |
|---|---|---|---|---|---|---|---|---|
| 1.32 | 1.31 | 1.30 | 1.45 | 1.34 | 1.70 | 1.90 | 2.30 | 2.57 |

- Updates 166-169 ran after window 2's resume. At 169 the learner bottomed 3.8 cards a game.
- Its training win rates fell from 0.734 against the heuristic and 0.515 against v1 (means over
  151-165) to 0.652 and 0.472 at 169.
- The mulligan's KL per update was the largest of any kind from update 3 (0.089), and reached
  0.153 at 168. No other kind with more than 100 decisions an update went above 0.048 (target, at
  update 19); the median update's mulligan KL was 6.8 times act's.
- **The pause.** I stopped r27 at 15:24 and gave the reason in the log: the runaway was
  accelerating, and every further save would overwrite update 165's weights with worse ones.
  The registered reads go by update count, so a pause changes nothing in them. Updates 166-169
  were never saved.

**The mulligan read** (191 §7, registered before its data; window 2's collect, 26,294 of v0's
declarations in 19,173 games):
- **M1 met:** v0's p(mulligan) at 7 cards with 3-4 lands is 0.062 [0.058, 0.065].
- **M2 met:** at 0-1 land it is 0.971 [0.967, 0.975].
- **M3 met:** the ROC-AUC of p(keep) against the result is 0.579 [0.571, 0.587].
- v0 reads the hand.
- On the same declarations, r27's network at update 165 mulligans every hand far more:

| 7 cards: 2 lands | 3 lands | 4 lands | 5 lands | 6 cards | 5 cards | 4 or fewer |
|---|---|---|---|---|---|---|
| 0.403 → 0.802 | 0.085 → 0.345 | 0.024 → 0.140 | 0.016 → 0.098 | 0.239 → 0.422 | 0.235 → 0.420 | 0.277 → 0.492 |

**When it drifted.** v0, v1 (update 75), `best.pt` (update 77) and update 165 were scored on
update 165's 3,857 declarations (`timeline.py`). p(mulligan) at 7 cards with 3-4 lands was 0.068,
0.081, 0.063 and 0.264. v1 mulligans as v0 does; the drift came after update 77, most of it after
140.

## 2. Not the learning signal

- **Crediting is right.** Each seat's decisions get that seat's result
  (`learner.py:_finish_train`), and with γ = λ = 1 the advantage is the result less the value
  (`gae`).
- **Name masking is ruled out:** r27 never used the flag.
- **The resume did not shock the network.** It restarts Adam's moments: the trainer builds a fresh
  AdamW at every start, and `learner.py` says so. But the overall KL of updates 166-169 was
  normal (0.0037-0.0086).
- **The policy gradient on the mulligan, measured on on-policy data.**
  - Measured as Σ A·(1[mulligan] − p) per declaration, with PPO's normalised advantages
    (scratch `mulligan_signal.py`).
  - On v0's collect: +0.0010 ± 0.0016 overall. It is slightly positive on 7-card hands, where v0
    mulligans only the hands its value rates poorly, and negative on smaller hands.
  - On update 165's own batch (`collect165.sh`, 139,304 decisions): **−0.0207 ± 0.0050**,
    negative in every cell that matters.
  - Mulliganing a 3-land hand cost 22 points there (wins 0.626 after keep, 0.400 after
    mulligan).
  - The signal pulled toward keep, and the policy went the other way.

## 3. The cause: a length stratum is an ask-kind stratum

- **How `ppo.chunks` cut a batch.** It sorted rows by length (tokens: cards plus options), cut
  them into minibatches under `mb` and `tok_budget`, and each minibatch was one optimizer step.
  The padding budget forces length-sorted micro-batches, because activation memory is system
  memory on the Spark. Using them as steps was the defect.
- **Where the mulligan rows landed.** A mulligan declaration is 4-9 tokens; the batch's median is
  26 (1st-99th percentile 8-59). In update 165's batch, all 3,857 declarations sat in 2 of 48
  minibatches, one of them 2,758 of 4,096 rows.
- **The ablation.** One update from update 165 on its own batch: r27's settings, a fresh AdamW,
  the change in the mulligan's logit (mulligan minus keep), averaged over the 3,857 declarations
  (`ablate.py`):

| Variant | Length-sorted (r27) | Stratified (the fix) |
|---|---|---|
| A: r27's loss, minibatch order 0 / 1 / 2 | +0.51 / +0.08 / −1.98 | −0.50 / +0.06 / −0.50 |
| B: the policy term only | −2.67 | −0.54 |
| C: the value term only | −0.30 | — |
| E: r27's loss without the mulligan rows (order 0; order 1) | +0.35 | +0.41; +0.19 |
| E4: E without the priority asks; E5: E without the bottom choices | — | +0.35; +0.24 |
| F: the policy term, mulligan advantages permuted among themselves | −0.14 | — |
| Seconds per update (idle GPU) | 90 | 126 (96 micro-batches against 48) |

**Reading.**
- **The order decided.** The same data and loss moved the mulligan between +0.51 and −1.98.
  In order 2 the two mulligan minibatches came last (steps 46 and 47) and the update pulled
  toward keep. In order 0 they came at steps 0 and 20, and the steps after undid them and
  more. The other kinds hardly moved with the order: priority's KL was 0.0027-0.0030 across
  the three.
- **The mulligan's own signal is real.** Alone it moves the logit −2.67 in one impulse. With its
  advantages permuted it moves −0.14.
- **The rest of the update pushes the mulligan up.** E (+0.19 to +0.41 in both schemes, with or
  without the priority asks or the bottom choices) is the shared network forgetting how to read a
  hand while it learns the rest of the game. It lowers the mulligan on the worst hands (−0.35 to
  −0.55 at 0-1 land) and raises it on decent ones, so the hand-dependence flattens.
- **Why it ran away instead of averaging out.**
  - The forgetting acts in every step. The re-learning came in one impulse per update, at a
    random place in the order.
  - Per-update swings of one or two logits, and a steady push upward between them, make a creep
    and then an excursion.
  - The creep matches the record: r26's 1,000 updates took the mulligan from 1.1% of hands to 27%
    of declarations (191 §7).

## 4. The fix (f83f4db) and what it does not fix

- **`ppo.steps`.** It deals the length-sorted rows into as many steps as `chunks` would cut, one
  row per step from each block. So every step holds every length, and every ask kind in its share
  of the batch. A step's rows are cut into length-homogeneous micro-batches under the same caps.
- **`ppo.backward_step`.** It accumulates a step's gradient as the mean over its rows.
- **Where it applies.** PPO, BC, the simulator and distillation train on `steps`. `chunks` stays
  for passes whose order does not matter.
- **Tests.** A short-only kind is in every step in its share (`chunks` held it in at most 2); a
  step's accumulated gradient equals one pass over its rows.
- **What it does.** On the same batch, r27's loss now moves the mulligan −0.50 / +0.06 / −0.50
  across the three orders. The policy term alone moves it −0.54, every update, not as an
  impulse. The spread over orders fell from 2.5 logits to 0.56.
- **What it does not fix: the forgetting (E).**
  - The mulligan's own gradient now acts in every step. At update 165's rates it wins, a net
    −0.3 per update.
  - At v1's lower rates the pull back is weaker (v0's data: +0.001 per declaration), so the
    mulligan may settle above v1's.
  - r28 registers a prediction with a falsifier for this (199). If it is falsified, a remedy
    aimed at the mulligan is the next registered change.
- **The cost.** An update took 126 s against 90 on the idle GPU. Live, beside the workers,
  r27's took ~110 s, so expect ~150 s. That is under the ~170 s it takes to collect a batch, so
  the interval should hold. But more of each batch will have been played by the previous weights.

## 5. Where else it reached

- **Every PPO run since ppo.py was created** (16805b3, 2026-11-03), r26 and r27 included.
  Whether it slowed their other learning is untested. r27's gates against v1 stayed at 0.508,
  0.518 and 0.506 for 75 updates while its mulligan drifted; r28 (199) measures it.
- **The teacher stage's BC, the simulator and distillation.** Window 1's `sim.pt` and every
  distilled network were trained on length-stratum steps.
- **Gate B's queue** at b73d562 distils with the old `ce_epoch`. It must be re-pinned before it
  runs (196 §8).
- **194's capacity probe** (`reports/capacity_probe_2026-11-12/probe.py`) fitted every arm on the
  same length-sorted minibatches in the same order, so its comparison stands. But each arm's
  absolute fit may be lower than it could be. The low early-game explained variance (0.07) may
  partly be this.

## 6. Decisions (the agent's, 2026-11-12; the owner: "no need for me in the loop")

- **r27 ends at update 165** (191 §8). Its reads at 500, 1,000 and 2,000 will not be made:
  resuming it on the old trainer would train on the defect, and on the new one it would be
  another run.
- **r28 (199): r27's configuration on the fixed code, from r27's v1.** v1 is update 75's
  gate-checked snapshot, and it mulligans as v0 does. r28's first 90 updates are then a direct
  comparison with r27's updates 76-165 from the same weights: same reference, same update
  count, the defect fixed. The bug hunt's engine fixes ride along (197). They are rare rules
  situations, recorded as a confound.
- **Gate B** waits for r28 and is re-pinned to the fixed code before any data (196 §8).
