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
