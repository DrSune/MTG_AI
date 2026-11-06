
## 5. E3, distillation (pre-registration)

**Question** (PLAN §12 E3). Does a network distilled from true-future labels learn: regret at most
0.8x its generator's, and a gain of at least +0.015 over 450 pairs on unseen deals?

**Labels.** Configuration A (k 2, d 2, greedy; the plan's default and the cheapest label), which
passed E1: its E1 labels (seeds 30,000,001+) and more from the same label job on seeds 33,000,001+, in game order, until 100k exist.
The distillation sets are the first 10k, 30k and 100k labels (whole games); every 20th game of a
set is held out to choose the epoch.

**Target.** Per label pi' = `search.mmd_target(pi, S, q, se)`: pi the generator's probabilities on
the label's encoding, q the mean results over its surviving futures, se = sqrt(V / d) with V the
per-future variance of result differences that E1's instrument measured on CONFIG's labels
(V = VVAL) and d the label's surviving futures; so eta = 0.5 / se = ETA at d = 2 (the plan's
rule, read with the pooled variance because two futures cannot estimate a label's own; §3 says
what that step does to the owner's example).

**Apprentice.** From the generator: cross-entropy to pi' over every option of the decision, AdamW
(lr 3e-5, weight decay 0.01), minibatches of up to 512 labels, up to 4 epochs, the epoch with the
lowest held-out KL kept (scratch `labels/e3_distill.py`).

**Regret.** 2,000 held-out positions from fresh deals (seeds 34,000,001+), from the same label job
with k = 8 (every option of a menu of at most 8, Gumbel-top-8 otherwise) and d = 4 fresh futures,
CONFIG's playout mode. A network's regret at a position is the best compared option's mean result
minus its greedy option's (the bf16 network, as served); positions where any compared network's
greedy option was not compared are left out. Gate: the 100k apprentice's mean regret at most 0.8x
the generator's, read on the one-sided 95% upper bound of the ratio (bootstrap over games, 2,000
resamples) (scratch `labels/e3_regret.py`; the 10k and 30k apprentices reported beside it).

**Gain.** The 100k apprentice against the generator, greedy, on the 450 standard evaluation deals
(seeds 900,000-900,449: half stress, half coherent, M21), each deal played with the seats swapped
(900 games; `tools.selfplay.learner --eval-only --init APP --opp-ckpt GEN --eval-opponents
snap:opp --eval-deals 450`). Gain = score - 0.5. Gate as written: at least +0.015 (the decision
point between 0 and +0.03 at 450 pairs, §12).

**E3 passes** when both hold. **Kill** (§12): search at play time only, and PPO as the learner.

**Predictions.** PREDICTIONS
