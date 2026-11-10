# 189 — r25: outcome PPO at the noise scale B* asks for (pre-registration; supersedes 188)

2026-11-10, main. Written before launch. r24 (note 188) died twice on the memory floor inside its
first update and is not resumed: its optimiser settings could not have tested D21 either (§1).
r25 is the same experiment, the PPO audit's confirmation run (184 §27), in a form that can run.

## 1. What was wrong with r24

1. **Memory: the CUDA allocator, not the buffer.** On 99,499 real positions (idle GPU) one update
   allocates 21.4 GiB at its peak, but torch reserves 54.5 GiB: every minibatch has its own padded
   shape and the allocator keeps a block per shape. `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`
   holds the reserve at 22.3 GiB at the same speed (1,881 against 1,895 decisions/s). Releasing the
   cache every step instead costs 35% of the speed. r24 added a 2.65M-decision buffer on top, and
   the streaming fix (ad23f73) did not touch the reserve, so the second start died like the first.
2. **Optimiser: an update was hundreds of large Adam steps, cut short.** `--steps 2650000` with
   `--lr 1.5e-4 --target-kl 0.03` takes ~1,000 minibatch steps per update at the learning rate at
   which r22 and r23 hit the KL stop on 90% of their 98k updates (after ~13-37 steps). Each r24
   update would have stopped after a few dozen minibatches and thrown the rest of an hour's play
   away (gemini_analysis.md §1 is right about this), while the workers waited for it.
3. **Gate: a selection effect.** `--gate-score 0.5 --gate-deals 300 --gate-every 1` freezes a new
   reference the first time a noisy re-test has its interval above 0.5. r20's v2 was made that way
   (12 flat gates, then 0.5192) and measured 0.5217 [0.499, 0.544] on fresh deals.

## 2. What "each update at least B*" needs, and how r25 gives it

The audit's point (184 §25-26): a step's gradient is half signal only when it averages B* decisions
(lambda 1: at least 2.65M); a step on 98k decisions is 99% noise, so large steps on them are a walk.
What that constrains is **how far the policy moves per decision consumed**, not how many decisions
sit in memory at once. For Adam the two forms are the same step:

- k minibatch steps at learning rate eta move the weights by eta * sum(g_i / sigma). Noise adds as
  sqrt(k), a consistent direction adds as k: after k = B*/b minibatches of b decisions the sum is the
  B*-batch gradient direction, with displacement eta * sqrt(k). One accumulated step at learning
  rate sqrt(k) * eta is the same vector, as long as the policy barely moves inside the window.
- So the knob is eta. Minibatch steps keep everything else better: the acting policy is never more
  than ~98k decisions old, memory stays at one 98k buffer, Adam's second moment is estimated from
  ~1,000 gradients per B* instead of one, and the workers never wait.

**Calibrating eta** to the audit's "KL 0.01-0.02 per B* step", on realised movement. r20 is the
measurement: 70 updates x ~37 minibatches at lr 5e-5 moved the policy by KL 0.2675 on 60,000 fresh
positions (table below). Scaling that to lr 2e-5 and the ~1,000 minibatches of 2.65M decisions gives
0.006 (if r20's movement was one consistent drift) to 0.017 (if it was a random walk) per B*.
lr 1e-5 gives 0.002-0.004, lr 3e-5 gives 0.014-0.037. **r25 uses lr 2e-5**, with the KL stop off
(per update the in-batch KL will be ~0.002-0.004; r20's was 0.01 at lr 5e-5 and never needed it).
In 12 hours (~31M decisions) the policy should move about as far as r20 did in its whole run.

How far earlier runs moved the policy (60,000 positions of `runs/labels/bank_A.2`, gen.pt's own
state distribution; KL(a||b), top choice compared on decisions with more than one option):

| From -> to | Between them | KL | TV | Same top choice | mean abs dV |
|---|---|---|---|---|---|
| r19 v3 -> r20 v2 | 70 updates x 98k, lr 5e-5, lambda 0.95 | 0.2675 | 0.1388 | 0.8685 | 0.082 |
| r20 v2 -> r21 v1 | r21's teacher stage | 0.0518 | 0.0648 | 0.9422 | 0.215 |
| r20 v2 -> gen.pt | r23: 31 updates x 32k, lr 1.5e-4, lambda 1 | 0.5111 | 0.2478 | 0.7363 | 0.155 |

r20 changed the top choice in 13% of decisions for a gain of at most 0.02; r23 changed 26% (it fixed
the mulligan ask) and plays 0.0475 worse against the heuristic. Past runs were large walks.

## 3. Configuration

Init `runs/selfplay/r23_mulligan/gen.pt` (27.25M parameters), frozen as v0 and kept as the
reference. Launched from `../MTG_AI-run` at this commit with
`PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`:

```
.venv/bin/python -m tools.selfplay.learner --run runs/selfplay/r25_outcome_ppo \
  --init runs/selfplay/r23_mulligan/gen.pt --seed 25 --workers 18 --slots 16 --groups 4 \
  --gamma 1.0 --lam 1.0 --steps 98304 --epochs 1 --lr 2e-5 --wd 0.01 --clip 0.2 --vclip 0.5 \
  --vcoef 0.5 --ent 0.0 --max-grad 1.0 --target-kl 0 --mb 4096 --tok-budget 98304 --infer-bf16 \
  --teacher-iters 0 --gate-every 25 --gate-deals 1000 --gate-score 0.55 --ladder-deals 500 \
  --p-heuristic 0.15 --p-past 0.15 --coherent-share 1.0 --mix-sets M20 --mix-share 0.25 \
  --extend-sets M20 --refresh-table --pool verified --save-every 5 --progress-every 300 \
  --mem-floor-gib 15.0 --iters 3000
```

Changes against r24 and r20-r23, each with its reason:
- `--steps 98304 --lr 2e-5 --target-kl 0`: §2. The no-grad pass that only the KL stop reads (24% of
  an update: 16.4 s of 68.9 s) is now skipped when the stop is off (`ppo.py`).
- `--teacher-iters 0`: self-play from the first update, 85% of games against v0, 15% against the
  heuristic. v0 stays the opponent and the gate's reference until a gate passes.
- `--gate-score 0.55 --gate-deals 1000 --gate-every 25`: 2,000 greedy games per gate (SE ~0.011),
  so a false pass needs +4.5 SE and the reference only moves on a real 0.55. 1,000 is also the
  most deals a gate can have before two gates' deal blocks overlap (`GATE_SEED0 + 1000 * n`).
- `--ent 0.0`: the owner's rule is win/loss and nothing else. At 0.002 the bonus costs nothing at
  equilibrium, but its gradient points the same way on every sample (flatten the policy) while the
  outcome gradient is 99% noise, so along that direction it accumulates like a signal. Entropy is
  logged every update; §5 names the level at which it would be put back.
- `--seed 25`, which now moves the training deals (`learner.py` `curriculum_job`). Before this
  commit every run dealt `TRAIN_SEED0 + game number` whatever its seed, so each run of the lineage
  r17 -> ... -> r23 trained again on the decks and shuffles its ancestors trained on.
- `--ladder-deals 500`: v0's level against the heuristic and random at SE ~0.014 (gen.pt has only
  the 300-deal figure 0.595 [0.538, 0.652] under the new mulligan ask).

Unchanged: gamma = lambda = 1 (OWNER_PREFERENCES #6), one epoch, clip 0.2, vclip 0.5, vcoef 0.5,
coherent decks only, M20 mixed in at 25%, verified pool, draw reward -1.

## 4. Instruments

1. **Training win rate against v0** (`win.frozen` in each `iter` event: the share of games won, a
   draw counts as not won; both seats sample, the learner's seat is random). ~2,000 games per
   update, so a 100-update window has SE ~0.0011 and the difference of two windows SE ~0.0016: the
   run resolves a change of 0.004 overnight. Before the first update the two seats are the same
   network, so the level starts at 0.5 x (1 - draw share); r20 and r21 held 0.501 and 0.506
   against their frozen versions over 80 updates each.
2. **Greedy gates against v0**, 1,000 seat-swapped deals every 25 updates (SE ~0.011 each; half
   stress decks, half coherent; `by_mode` splits them).
3. **Training win rate against the heuristic** (~350 games per update): the anchor. r23, the run
   that made gen.pt, averaged 0.636 on it.
4. Movement: `kl` per update; entropy; and, after the run, KL of the learner against v0 on the
   bank positions (the measure of §2).

## 5. Predictions (written before any r25 game)

The audit's test: the paired win rate against the fixed reference rises by at least 2 SE within 16
B*-steps; if it stays flat, outcome PPO is exhausted at this policy. 16 x 2.65M decisions is 431
updates, about 16 hours. The read is the window of updates 401-500 (15 to 18.5 B*).

| # | Metric | Prediction | Falsifier |
|---|---|---|---|
| 1 | Training win rate against v0: mean of updates 401-500 less mean of updates 1-100 (SE ~0.0016) | Most likely within +-0.005: no detectable gain. I give a real gain (>= +0.01, 6 SE) about one chance in four | >= +0.01 falsifies "exhausted"; <= -0.01 says the run harms the policy |
| 2 | Greedy gates against v0, pooled over updates 300-500 (9 gates, 18,000 games, SE ~0.004) | 0.50 +- 0.008 | pooled lower 95% bound above 0.5 |
| 3 | Movement | `kl` 0.002-0.004 per update; after 500 updates KL against v0 on bank positions 0.1-0.6 | KL against v0 below 0.03: the run moved too little to test anything |
| 4 | Entropy (`ent`) | stays within 0.25-0.40 | below 0.20: put the bonus back at 0.002 in a successor |
| 5 | Value fit (`ev`) | 0.25-0.45, as in r23 | below 0 for 3 updates (K4) |
| 6 | Memory | minimum MemAvailable above 45 GiB | below 30 GiB: the allocator finding is wrong |
| 7 | Throughput | 120-135 s per update (r20, r21: 140 s with the extra pass), 730-820 learner decisions/s | slower than 145 s |
| 8 | v0 against the heuristic (500 deals, greedy) | 0.60-0.66 overall | below 0.55 or above 0.70 |

Why I expect no gain: r20 consumed 6.9M decisions (lambda 0.95, where B* is 2.2M) at 2.5 times
this learning rate, should by the same arithmetic have moved mostly along a consistent direction,
and gained at most 0.02. The likeliest reading is that the consistent part of the gradient was not
the outcome signal (GAE bias at lambda 0.95, the value loss moving the shared trunk, the entropy
bonus). At lambda 1 the outcome signal is unbiased but at or below what the audit could detect.
The run is still the decisive measurement for D21's learner, and it costs nothing in opportunity:
play-time search (E2) is the next build either way and needs no GPU while it is written.

**What each outcome means.**
- Gain (1 or 2 falsified upward): the PPO learner is alive at this noise scale. Next: double the
  learner's data per GPU-second (both seats of a self-play game are the learner's; today half of all
  inference serves the frozen opponent), then raise the learning rate in steps.
- No gain by update 500 with prediction 3 met: outcome PPO is exhausted at this policy on this
  hardware. The learner then needs a denser signal than the game result. That is the owner's
  parked question (D21: the distillation "at a later point"); search at play time is unaffected.
- Prediction 3 falsified: rerun at lr 5e-5 before concluding anything.

The run is not stopped at update 500 unless a kill criterion fires or a better use of the machine
is ready: more updates only sharpen the read.

## 6. Kill criteria

K1 any engine crash or unhandled exception. K4 `ev` below 0 for 3 updates. K7 below 10 games/s
sustained. The memory floor once (prediction 6 says it is 30 GiB away). Non-finite steps in 3
consecutive updates. Training win rate against the heuristic, over any 50-update window (SE
~0.004), more than 0.05 below its mean over updates 1-50.

## 7. Pre-flight and launch

`tools.selfplay.preflight` (P1, P8, P9, P12) from the pinned worktree at the launch commit; the run
directory holds `preregistration.json`, `preflight.json`, `manifest.json`. Results are appended
below, the numbers to NUMBERS.

## 8. r25 as it ran: ten updates, then superseded (2026-11-10, 00:26-01:10)

Start ladders (500 deals each, greedy): v0 against the heuristic 0.590 [0.564, 0.616] (stress
decks 0.501, coherent 0.679); v0 against random 0.878 [0.859, 0.897]; heuristic against random
0.865 [0.845, 0.885]; Elo heuristic 306, v0 361.

| Update | ent | kl | ev | win.frozen | win.heuristic | update + collection, s | min MemAvailable, GiB |
|---|---|---|---|---|---|---|---|
| 1 | 0.2458 | 0.0021 | 0.377 | 0.484 | 0.683 | 84 + 88 | 55.3 |
| 2 | 0.2380 | 0.0023 | 0.368 | 0.501 | 0.656 | 88 + 71 | 54.7 |
| 3 | 0.2321 | 0.0022 | 0.391 | 0.524 | 0.686 | 89 + 106 | 52.7 |
| 4 | 0.2325 | 0.0021 | 0.408 | 0.483 | 0.671 | 84 + 47 | 52.3 |
| 5 | 0.2265 | 0.0018 | 0.409 | 0.513 | 0.664 | 86 + 47 | 51.6 |
| 6 | 0.2286 | 0.0024 | 0.404 | 0.497 | 0.671 | 89 + 47 | 51.1 |
| 7 | 0.2219 | 0.0023 | 0.391 | 0.491 | 0.658 | 87 + 47 | 52.9 |
| 8 | 0.2165 | 0.0025 | 0.406 | 0.506 | 0.694 | 387 + 249 | 37.5 |
| 9 | 0.2118 | 0.0023 | 0.423 | 0.522 | 0.689 | 244 + 474 | 41.6 |
| 10 | 0.2192 | 0.0024 | 0.421 | 0.498 | 0.649 | 85 + 51 | 51.9 |

**Updates 8 and 9 were slowed fivefold by me.** I started seven small evaluation processes on the
GPU beside the run (the probes of note 190 §10). The GPU time-slices between processes, so seven
batch-1 clients took most of it: games/s fell from 14.6 to 2.9. K7 (below 10 games/s) describes
those two updates and the cause was the probe, not the run. Rule from now on: nothing else on the
GPU beside a registered run; a side evaluation goes through the batched learner (`--eval-only`)
while no run is training.

**The predictions, as far as ten updates score them.**
- 3 (movement): `kl` 0.0018-0.0025 per update, at the band's lower edge.
- 4 (entropy): started at 0.246, under the band, and fell in seven of nine steps, by 0.003 per
  update. The falsifier line (0.20) was not crossed; the low was 0.212.
- 5 (`ev`): 0.37-0.42, inside. 6 (memory): 51-55 GiB undisturbed, inside.
- 7 (throughput): 132 s per undisturbed update, inside. The reason I gave for the band was wrong:
  r20 and r21 took 140 s because they ran a gate after every update, not because of the extra pass.
- 8 (v0 against the heuristic): 0.590, 0.01 under the band. The band rested on a figure I
  mis-attributed in §3: 0.595 [0.538, 0.652] was r20's v2 on 100 ladder deals under the mulligan
  engine. gen.pt's own 300-deal figure (note 186) is 0.5875 [0.555, 0.620], which 0.590 repeats.
- 1 and 2 need hundreds of updates. `win.frozen` averaged 0.502 over the ten.

**Two more corrections to this note.**
- *The gates are twice as sharp as §3, §4 and prediction 2 say.* A deal's two seat-swapped games
  are won by the same seat in 93% of stress deals and 84% of coherent ones (r20-r23's gates, note
  190 §9.1), so a deal's score has SD 0.131 (stress) and 0.203 (coherent), not the 0.35 of
  independent games. A 1,000-deal gate has SE 0.0054 (its coherent half 0.0091), nine gates pooled
  0.0018 (coherent half 0.0030).
- *`win.frozen` can rise without the policy learning anything.* In that number both seats sample.
  On 600 fresh coherent deals v0 playing its top choice scores 0.518 (SE 0.0085) against v0
  sampling (note 190 §10.1). A policy that only sharpens can therefore gain up to about 0.018 on
  `win.frozen` and nothing on the greedy gates. Prediction 1's falsifier (+0.01) is inside that.

**Why I stopped r25 before its entropy line was crossed.** Without the bonus the entropy fell
steadily, and the mechanism is plausible from two sides: off-choice samples do slightly worse
than the top choice (the probe above), which is the same message in every decision, and the value
loss moves the shared trunk in a direction that lowers entropy (note 190 §10.4; the measurement
below shows this second half was wrong). Nothing pulls the other way. A run meant to go unattended for days would, at 0.003 per update, be near-deterministic
within a day, and a deterministic policy gives PPO nothing to compare. The registered consequence
of low entropy was "put the bonus back at 0.002 in a successor"; I took it at 0.212 instead of
waiting for 0.20. Cost: 43 minutes of compute. r25's later rows (update 11 on) are the launcher's
resume test of §9, not part of the experiment.

**Which term lowers it: one update, term by term (rule written before the result).** The logged
`ent` is a poor instrument for this: it is a mean over minibatches, on a different buffer each
update, and the first buffers after a start hold shorter games (17-20 games/s against 14.6), so
part of the fall may be composition. The clean measurement: from v0, one real update (`ppo_train`,
r25's settings, fresh AdamW) on 52k of v0's own decisions (500 self-play games), and the policy
compared before and after on fixed states: 26k decisions from 250 games the update never saw.
This update has 22 steps where a run's has 39. Variants: **A** r25's loss; **A2** the same in
another minibatch order (the noise gauge); **B** bonus 0.002; **C** the policy term alone;
**D** the value term alone (advantages set to zero); **E** value coefficient 0.05; **F** bonus
0.02. I expect A to lower the held-out entropy by about 0.001, D to carry most of that, C to
carry none, and B to differ little from A.

The rule for the successor:
- A's fall is no larger than the gap between A and A2: the trend in r25's log was composition.
  r26 runs as first drafted, with the bonus at 0.002.
- B removes at least half of A's fall: the bonus works. Same.
- Otherwise, and D carries at least half of the fall: the value loss moves the policy through the
  shared trunk, and the fix is to shrink that pull, not to add a reward for randomness. r26 runs
  with value coefficient 0.05 if E removes at least half of the fall. (Adam rescales each
  parameter, so the value head learns as fast as before; only its share of the trunk's gradient
  shrinks tenfold.) If E does not, bonus 0.02 if F does.
- Otherwise (C carries it): the policy gradient itself sharpens the policy, which is the learner
  following its data; the bonus is the counterweight, at the smaller of 0.002 and 0.02 that
  halves the fall.
- If no variant halves the fall, r26 runs as first drafted and the decline is the open problem
  the return review starts with.

**Result (01:37).** Before the update the held-out decisions had entropy 0.2275, and the value
head a bias of +0.134 and explained variance 0.431.

| Variant | Entropy change, held-out | Same, train rows | KL(before, after), held-out | Top choice changed | Value bias after | Value ev after |
|---|---|---|---|---|---|---|
| A r25's loss | -0.0038 | -0.0033 | 0.0026 | 1.00% | +0.030 | 0.442 |
| A2 the same, other minibatch order | -0.0069 | -0.0067 | 0.0021 | 0.84% | +0.008 | 0.444 |
| B bonus 0.002 | -0.0036 | -0.0032 | 0.0025 | 1.01% | +0.030 | 0.442 |
| C policy term alone | -0.0047 | -0.0048 | 0.0029 | 1.14% | +0.115 | 0.432 |
| D value term alone | **+0.0029** | +0.0030 | 0.0021 | 0.92% | +0.038 | 0.443 |
| E value coefficient 0.05 | -0.0053 | -0.0051 | 0.0029 | 1.11% | -0.032 | 0.439 |
| F bonus 0.02 | **+0.0008** | +0.0013 | 0.0025 | 1.02% | +0.030 | 0.442 |

**Controls, run after I had applied the rule (01:51).** They changed the decision.

| Variant | Entropy change, held-out | Same, train rows | KL(before, after), held-out | Top choice changed |
|---|---|---|---|---|
| G policy term alone, advantages shuffled over the rows | +0.0010 | +0.0007 | 0.0021 | 1.04% |
| H5 bonus 0.005 | -0.0028 | -0.0023 | 0.0025 | 0.96% |
| H10 bonus 0.01 | -0.0016 | -0.0012 | 0.0025 | 1.01% |
| W r25's loss on the first 250 games only (12 steps) | **-0.0068** | -0.0066 | 0.0024 | 0.98% |
| W, then on the second 250 (11 steps, same optimizer) | **+0.0040** | +0.0042 | 0.0013 | 0.73% |
| W2 the second 250 first (11 steps) | +0.0019 | +0.0023 | 0.0032 | 1.27% |
| W2, then the first 250 (12 steps) | -0.0069 | -0.0073 | 0.0023 | 1.12% |

- **Which term.** On these 500 games the policy term lowers entropy (C) and the value term raises
  it (D). With the advantages shuffled the policy term does not lower it (G), so the fall comes
  through the outcomes of the sampled actions, not from the mechanics of the update. I had
  expected the value term to carry the fall and the policy term none. Wrong on both.
- **One batch is mostly noise.** The first 250 games lower entropy by 0.007 whether they come
  first or second; the second 250 raise it by 0.002 to 0.004. All four arrangements of r25's loss
  on the 500 (A, A2, W, W2) end between -0.003 and -0.007, but that is one sample of games, and
  the size of the systematic fall cannot be read from it. r25's log can give it: nine buffers of
  about 1,950 games each, a least-squares slope of -0.0029 per update over updates 2-10
  (SE 0.0004; the same over 4-10).
- **The bonus's push is the clean number.** Same games, same order, only the coefficient differs:
  +0.0002 at 0.002, +0.0010 at 0.005, +0.0022 at 0.01, +0.0045 at 0.02, per 22 steps. From 0.005
  up that is a line: 0.236 times the coefficient, less 0.0002. A step pushes as hard late in an
  optimizer's life as early (the first 250 games: -0.0068 fresh, -0.0069 warm), and a run's
  update has 39 steps, so per run update the push is about 0.42 times the coefficient, less 0.0004.

**Decision.** By the letter of the rule its fourth bullet applies (the policy term carries the
fall, and of the two sizes only 0.02 halves A's), and r26 would run at 0.02. I do not follow it.
The rule took A's fall on 500 games for the fall to be halved, and the controls show that figure
is mostly one batch's noise. Against r25's fall of 0.0029 per update a bonus of 0.02 pushes 0.008
the other way: it would flatten the policy, which confounds the run as much as the sharpening
did. The size whose push balances r25's fall, by the line above, is 0.0075 (0.006 to 0.009 over
two standard errors of the slope). One correction is in that figure: the logged entropy is a mean
over minibatches, the minibatches are sorted by length, and so long decisions weigh more than in
a per-row mean; by the by-kind figures that overstates the fall by about 5% (`weight_check.py`
in `reports/v0_probes_2026-11-10/`, where the scripts and outputs of this section are). **r26 runs with
`--ent 0.0075`**: under four times the bonus of r20-r23, under half of what the rule gave.

Two more things in the tables, outside the decision:
- **The value loss moves the policy as much as the whole update does.** With no policy gradient
  at all (D) the policy still moves by KL 0.0021 and changes its top choice in 0.9% of decisions,
  against 0.0026 and 1.0% for the full update. That is the shared trunk. Adam fixes the size of
  the step, so the terms compete for its direction: with the value coefficient at 0.05 (E) the
  value head learns as well as before (ev 0.439 against 0.442). A lower value coefficient, or a
  value head that does not move the trunk, is a candidate for the run after r26 (BACKLOG); r26
  changes one thing.
- **The value head's bias is gone after one update** (+0.134 to +0.03).

The trunk-gradient cosines of note 190 §10.4 predicted the opposite sign for both terms. They
describe plain gradient descent on the trunk; the update is Adam on every parameter. What an
update does has to be measured on the update, and on more than one batch.

## 9. r26: the same experiment with an entropy bonus of 0.0075 (pre-registration, before any r26 game)

**Configuration.** r25's command with three changes: `--ent 0.0075` (§8: the size whose measured
push balances r25's fall; the 0.002 of r20-r23 does nothing at this step size), `--seed 26` (fresh
training deals),
`--iters 6000` (about ten days; the run is stopped by hand, not by this number). Same init
(gen.pt, frozen as v0), same learning rate, gates and deals. It is started fresh, not resumed from
r25, so every update is under one setting.

**The bonus against the owner's rule that only winning pays.** It pays for no event in a game. It
is a pull toward keeping more than one option alive at a decision, and without it this learner
removes its own exploration (§8). Its size in outcome terms: the loss divides advantages by their
standard deviation (0.79), so at 0.0075 an action that costs 0.3 points of win probability keeps
about a third of the best action's weight at equilibrium (0.0075 x 0.79 = 0.0059 on the +-1
scale per e-fold). At 0.002 that was 0.08 points. Strength is read on the greedy gates, where the top
choice plays and this randomness is absent. It is a counterweight I would rather not need; whether
a learner that needs it is the right learner is a question for the review (note 190 §2).

**Unattended operation.** The run is the user unit `mtg-r26`
(`~/.config/systemd/user/mtg-r26.service`), which runs `tools/selfplay/launch.sh` from the pinned
worktree with `Restart=on-failure`, `RestartSec=300`, at most 6 starts an hour. The launcher
waits for 60 GiB of available memory, adds `--resume` when the run has saved state, and sets the
allocator option of §1. So a run that dies (memory floor, crash, kill) continues from its last
save, at most 4 updates back, and logs a `resume` event; tested on r25 with a `kill -9`.
`systemctl --user stop mtg-r26` stops it for good; `systemctl --user start mtg-r26` continues it.
The unit is not enabled at boot. This box's engine guard will refuse to start an LLM engine while
the run holds its 35 GiB: stop the run first, start it again afterwards.

```
[Unit]
Description=MTG_AI r26 outcome PPO (KNOWLEDGE/2026-11-10/189 §9); resumes itself
StartLimitIntervalSec=3600
StartLimitBurst=6

[Service]
WorkingDirectory=/home/sune/Desktop/MTG_AI-run
ExecStart=/home/sune/Desktop/MTG_AI-run/tools/selfplay/launch.sh /home/sune/Desktop/MTG_AI/runs/selfplay/r26_outcome_ppo \
  --init /home/sune/Desktop/MTG_AI/runs/selfplay/r23_mulligan/gen.pt --seed 26 --workers 18 --slots 16 --groups 4 \
  --gamma 1.0 --lam 1.0 --steps 98304 --epochs 1 --lr 2e-5 --wd 0.01 --clip 0.2 --vclip 0.5 \
  --vcoef 0.5 --ent 0.0075 --max-grad 1.0 --target-kl 0 --mb 4096 --tok-budget 98304 --infer-bf16 \
  --teacher-iters 0 --gate-every 25 --gate-deals 1000 --gate-score 0.55 --ladder-deals 500 \
  --p-heuristic 0.15 --p-past 0.15 --coherent-share 1.0 --mix-sets M20 --mix-share 0.25 \
  --extend-sets M20 --refresh-table --pool verified --save-every 5 --progress-every 300 \
  --mem-floor-gib 15.0 --iters 6000
StandardOutput=append:/home/sune/Desktop/MTG_AI/runs/selfplay/r26_outcome_ppo.out
StandardError=inherit
Restart=on-failure
RestartSec=300
SuccessExitStatus=143
```

While nobody watches, only the memory floor is enforced. The other kill criteria of §6 are read
at the return review, on the last row per update (a resume replays the updates after its save).

**Instruments.** As §4, with the corrected gate errors. The primary gate read is the **coherent
half** (`by_mode.coherent`): training deals are coherent, and a stress deal carries a fifth of the
information.

| # | Metric | Prediction | Falsifier |
|---|---|---|---|
| 1 | `win.frozen`, mean of updates 401-500 less mean of updates 1-100 (SE 0.0017) | within +-0.005; a real gain about one chance in five | >= +0.01 falsifies "exhausted"; <= -0.01 says the run harms the policy |
| 2 | Greedy gates against v0, coherent half, pooled over the nine gates of updates 300-500 (SE 0.0030) | 0.494-0.506 | above 0.506: a gain; below 0.494: harm |
| 3 | Movement | `kl` 0.0018-0.0030 per update; KL against v0 on bank positions after 500 updates 0.1-0.6 | below 0.03: moved too little to test anything; rerun at lr 5e-5 |
| 4a | Entropy, least-squares slope over updates 2-10 | -0.0012 to +0.0012 per update (r25 without the bonus: -0.0029; slope SE about 0.0005) | below -0.0020: the bonus pushes less in the run than on the one update of §8; above +0.0020: it pushes more, and flattens the policy |
| 4b | Entropy, mean of updates 401-500 | 0.18-0.30 | below 0.14: the bonus is too weak; above 0.40: too strong. Either way a successor changes it |
| 5 | `ev`, mean of updates 401-500 | 0.38-0.50 | below 0.25, or below 0 for 3 updates (K4) |
| 6 | Minimum MemAvailable with nothing else large on the box | above 45 GiB, and updates 401-500 within 3 GiB of updates 11-100 | a steady fall: a leak (no run has yet gone past 100 updates) |
| 7 | Median time between updates, gate intervals left out | 125-140 s | above 150 s |
| 8 | Start ladder, v0 against the heuristic (r25's deals again) | 0.575-0.605 | outside: the evaluation does not repeat to within inference noise |

Update 1 is left out of 4a: the first buffer after any start holds the games that ended soonest
(17.0 games/s against 14.6), and their decisions are less settled. r25's resumed update 11 logged
0.233 after update 10's 0.219 for that reason alone.

I look once, at update 3, to see that the run trains (memory, speed, `kl`, `ev`). After that
nobody watches. If the bonus is off in either direction the entropy settles where the bonus and
the policy gradient balance, so a wrong size costs information, not the run.

Later reads, since the run goes on: the same two statistics at updates 1,000 and 2,000 (windows
901-1000 and 1901-2000 against 1-100; the nine gates ending there). With three looks a gain on
the gates needs 0.508 (2.4 SE). If the entropy of the late window differs from the early one by
0.02, up to 0.002 of a `win.frozen` difference is temperature (0.018 over the whole 0.22).

**What each outcome means** is unchanged from §5: a gain says outcome PPO is alive at this noise
scale (next: both seats' decisions to the learner, then a larger step); no gain with prediction 3
met says it is exhausted at this policy on this hardware, and the learner needs a denser signal
than the game result (the owner's parked question, D21); prediction 3 falsified says rerun larger.

## 10. r26 at update 500: the first registered read (2026-11-10 23:30, at update 536)

Numbers in NUMBERS ("r26 AT UPDATE 500"). The run passed two gates, which §9 treated as unlikely,
and that changed what predictions 1 and 2 measure: after v1 froze at 202 the gates and
`win.frozen` compare with v1, and after 378 with v2.

| # | Read | Verdict |
|---|---|---|
| 1 | `win.frozen` 0.530 -> 0.4995, but against v0 then v2 | not comparable; the freezes answer it: falsified toward a gain |
| 2 | gates against v0 stopped at 202; v1 passed at 202, v2 at 378 | falsified: a gain |
| 3 | `kl` 0.0057 | above the range: twice the movement per update predicted; not the falsifier (moving too little) |
| 4a | entropy slope +0.00056 | met |
| 4b | entropy 0.4275 | falsified: the bonus is too strong; a successor changes it |
| 5 | `ev` 0.416 | met |
| 6 | 50.3 GiB minimum, 49.4 early | met |
| 7 | 138 s | met |
| 8 | 0.590 at the start | met |

Kill criteria: K1 fired once, at update 173 (an input overflow at inference, fixed in main as
`features._squash`; the pinned run keeps the old code and restarts itself if it recurs). None
other.

**What it means**, by §9: a gain. Outcome PPO at gamma = lambda = 1 with this batch learns: v2 is
76 Elo above v0 after 378 updates and scores 0.684 against the heuristic where v0 scored 0.590.
Since v2 the gates sit at 0.46-0.53 and the next pass is not in sight at 536; the dip at 425-475
is in the stress half, decks the run does not train on. The gain is not attributed to the bonus
alone: r26 differs from r20-r23 in learning rate, gamma and lambda, batch and gates. For the
successor, which is the first run on the game with priority (`docs/DESIGN_PRIORITY.md` stage 5):
a smaller bonus, read per decision kind. Next looks: update 1,000 (about 18:00 on 2026-11-11)
and 2,000 (about 10:00 on 2026-11-13).
