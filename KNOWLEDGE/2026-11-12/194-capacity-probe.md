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
