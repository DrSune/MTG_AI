# 194 — Does a bigger network fit what r27 has to learn? (pre-registration)

**Context.** `docs/PLAN_CEILING.md` §4.1. The owner asked to test network sizes for r27
(2026-11-12). The red team dropped the first design: an 8-hour RL arm from a grown network
measures update count, not size, because PPO at r27's learning rate barely moves the new layers.
This probe asks the capacity question directly, with supervised fitting. Written before any of its
data are collected. Results are appended below and never edit this section.

**Tools** (commits b83ef33, e5c9289):
- `learner.py --collect`;
- `model.grow`, whose test shows depth bitwise equal and width equal to rounding, through save
  and load;
- `reports/capacity_probe_2026-11-12/probe.py`.

A CPU smoke on 301 collected rows had all arms starting equal (policy NLL 0.41937).

## 1. The protocol

The window is about 2 hours. r27 is paused and the pause is logged; nothing else is on the GPU.

1. **Collect** 1.2M learner decisions with r27's own flags (its unit text), from r27's v0, as
   r27's first updates were played. This takes about 15 minutes.
   - The command is r27's unit text with `--run runs/probe/collect --seed 2712 --steps 1200000
     --collect runs/probe/collect.pkl`.
   - Seed 2712 gives fresh deals, apart from r27's.
2. **Fit**, for lr in 3e-5 and 1e-4, and for each arm `base`, `deep` (16 layers) and `wide`
   (feed-forward 4,096):
   - one epoch over the training rows;
   - minibatches as PPO cuts them (4,096 decisions, 98,304 tokens), the same ones in the same order
     for every arm;
   - loss: cross-entropy on the action taken plus 0.5 x the value's squared error against the
     return (gamma = lambda = 1: the game's result);
   - AdamW (betas 0.9/0.99, weight decay 0.01), clip 1.0, bf16 autocast;
   - an evaluation every 50 steps and at the end;
   - every 25th game held out.
3. **Read at the end of the epoch, at the lr where `base` has the higher held-out mid-game
   explained variance:**
   - the held-out explained variance of the value, early, mid and late in a game (each decision's
     third of its game), and over all;
   - the held-out policy NLL;
   - seconds per step and peak memory per arm;
   - the differences `deep - base` and `wide - base`, with 95% intervals from 2,000 bootstrap
     resamples of the held-out games (paired: the same resampled games for both arms).

## 2. Predictions

| # | Measure | Prediction | Falsifier |
|---|---|---|---|
| K1 | `deep - base`, held-out mid-game explained variance | -0.01 to +0.01 | +0.02 or more, with its lower bound above 0: capacity limits the value function |
| K2 | `wide - base`, the same | -0.01 to +0.01 | as K1 |
| K3 | `base` at the end against step 0, mid-game explained variance (u1000 learned on the old game; the data are the new game's) | 0.00 to +0.04 | below -0.01 at both lrs: the fitting itself is broken, and K1-K2 are not read |
| K4 | Peak memory of a step, `deep` against `base` | +10 to +20 GiB | — |

**Why the expectation is null.**
- The PPO audit found gradient noise, not capacity, limiting r27's kind of learning.
- In PPO's audit the value explained 28% of the outcome's variance mid-game. Most of the rest is
  what the deal hides: the opponent's hand and both libraries. No network size sees that.

## 3. What each outcome means

- **K1 or K2 falsified** (a bigger arm fits clearly better): capacity limits the value function.
  - A run from that network is pre-registered as r28.
  - It is compared with r27 at matched update counts.
  - Its gain is priced against the search's latency: twice the depth halves the n that fits a
    clock, and doubles F0/F1's costs.
- **Both met:** size is not the lever at this stage; r27 stays at 8 layers. The value function's
  limits are the hidden information and the noise, which are the simulator's and the search's
  work.
- **K3 falsified:** the probe is broken. Nothing is read from it until it is fixed.

## 4. Before the window: two fits dropped, no read changed (2026-11-12 04:30, before any data)

- §3's read uses one learning rate: the one where `base` has the higher held-out mid-game
  explained variance. So `deep` and `wide` at the other rate would never be read.
- Each costs about 30 and 21 minutes. Estimate: r27's update runs 2.2 s per minibatch of the same
  size, and one epoch is about 410 minibatches.
- So the window runs `base` at both rates first, then `deep` and `wide` only at the rate the read
  uses (`reports/window2_2026-11-12/queue.sh`).
- K1-K4 and §3 are unchanged. K3 still reads `base` at both rates.
- The checkpoint is r27's `v0.pt`: u1000 with the table refreshed at r27's start (one row), which
  is the network that plays the collected games.

## 5. Results (window 2, 2026-11-12 13:42-14:57)

**The run.**
- The collect wrote 1,200,029 decisions of v0 under r27's flags (1,152,060 to train on, 47,969
  held out: every 25th game). It took 15 minutes.
- The fits ran as §1 and §4: `base` at both rates, then `deep` and `wide` at 3e-5. Every arm
  started equal: at step 0 the policy NLL was 0.28969 and the mid-game explained variance 0.33418.
- **The read is at lr 3e-5.** There `base` ended at a mid-game explained variance of 0.3476,
  against 0.3314 at 1e-4.

| At the end of the epoch | `base` | `deep` | `wide` |
|---|---|---|---|
| Parameters | 27.8M | 53.0M | 44.6M |
| Held-out explained variance: early / mid / late / all | 0.067 / 0.348 / 0.703 / 0.368 | 0.066 / 0.346 / 0.703 / 0.367 | 0.065 / 0.345 / 0.702 / 0.366 |
| Held-out policy NLL | 0.2962 | 0.2969 | 0.2970 |
| Seconds per step | 1.50 | 2.80 | 1.84 |
| Peak memory of a step | 22.5 GiB | 42.9 GiB | 31.6 GiB |

| # | Measure | Result | Prediction |
|---|---|---|---|
| K1 | `deep - base`, mid-game explained variance | −0.0014, 95% [−0.0061, +0.0021] | −0.01 to +0.01: met |
| K2 | `wide - base`, the same | −0.0023, 95% [−0.0065, +0.0010] | met |
| K3 | `base` at the end against step 0, mid-game | +0.0134 at 3e-5, −0.0028 at 1e-4 | 0.00 to +0.04: met at 3e-5. Not falsified: that needs both rates below −0.01 |
| K4 | Peak memory, `deep` against `base` | +20.4 GiB | +10 to +20: just above |

- **The choice of rate cannot rescue K1 or K2.** It was made on the same held-out games, so
  `base` at 3e-5 is the larger of two noisy estimates, and that leans `deep - base` and
  `wide - base` toward the null. The size of that lean is bounded by the gap between the two
  rates: `base` at 3e-5 minus `base` at 1e-4, paired by game, is +0.016, 95% [−0.003, +0.036].
  So the lean is a few thousandths at most. Both upper bounds (+0.002 and +0.001) are far from the
  +0.02 falsifier.
- **Outcome (§3): both met.** Size is not the lever at this stage, and r27 stays at 8 layers. The
  value function is limited by the hidden information and the noise: the simulator's and the
  search's work.

**What the probe cannot see (found while scoring).**
- The held-out policy NLL can only rise in this probe. The actions were sampled from v0 itself,
  and the sampling distribution minimises the expected NLL of its own samples. Every arm starts
  at v0, so the rise (0.2897 to 0.2962 for `base`) measures drift from the behaviour policy, not
  fit.
- For the same reason, the policy term's gradient is zero in expectation at the start, and
  afterwards it pulls back toward v0. It adds noise to the shared trunk and anchors the policy,
  but it never tests the policy's capacity.
- At 1e-4 that noise cost the value: `base`'s early-game explained variance fell from 0.075 to
  0.029.
- So the probe answers the value's capacity question only. The policy's needs targets other than
  the network's own samples, such as the search's choices.
