# The Teacher's reward signal: measured, not argued

You raised the crux yourself:

> *"I just think its quite a few games and it will be a noisy estimate that will then be noisy
> reward for the teacher."*

You were right, and it is worse than you feared. But your own fallback idea is the answer, and it
is roughly seventy times better. Reproduce with
[`tools/teacher/reward_noise.py`](../tools/teacher/reward_noise.py).

## Method

Simulate five decks with known teaching value, from unwinnable to very instructive, where
"teaching value" is defined as how much the Student's win rate genuinely rises over a block of
games against that deck. Then run each candidate reward estimator 1,500 times per deck and ask two
questions:

1. **Precision.** Can it tell decks apart? Measured as signal-to-noise: the spread of the estimator
   across genuinely different decks, divided by its spread across repeats of the same deck. Below
   1.0 the noise between repeats of one deck exceeds the real difference between decks, so the
   Teacher is learning from coin flips.
2. **Accuracy.** Does it rank the decks correctly? An estimator can be precise and still point the
   wrong way.

## Result

Signal-to-noise by block size:

| estimator | N=20 | N=100 | N=400 |
|---|---|---|---|
| **win-rate delta, as proposed** | 0.10 | **0.17** | 0.39 |
| win-rate delta, paired both-sides play | 0.09 | 0.25 | 0.52 |
| regression slope instead of two halves | 0.12 | 0.19 | 0.44 |
| slope + paired | 0.10 | 0.29 | 0.60 |
| closeness to a 50% win rate | 2.69 | 5.78 | 11.32 |
| **per-decision proxy slope** | **6.02** | **13.22** | **26.65** |

And the ranking check at N=100:

| deck | true teaching value | closeness to 50% | per-decision proxy | win-rate delta |
|---|---|---|---|---|
| unwinnable | 0.005 | 0.104 | 0.005 | 0.003 |
| too easy | 0.005 | 0.095 | 0.005 | 0.002 |
| **even but dull** | 0.010 | **0.920** | 0.010 | 0.007 |
| instructive | 0.040 | 0.866 | 0.040 | 0.021 |
| **very instructive** | **0.080** | 0.832 | **0.080** | 0.037 |

## What this says

**The literal proposal does not work.** Win-rate delta over 100 games scores 0.17. The Teacher
cannot distinguish an unwinnable deck from a very instructive one. It is correct *in expectation*,
the means do order properly, but a single block is dominated by noise and a single block is what
the Teacher gets per update.

**The obvious fixes are not enough.** Your both-sides paired play is genuine variance reduction and
helps, 0.17 to 0.25. Fitting a slope over all games instead of differencing two halves helps too.
Together they reach 0.29 at 100 games. Still far below 1.0. Even 400 games only reaches 0.60. These
are the right techniques and they are worth having, but they do not rescue this signal.

**Rewarding closeness to a 50% win rate is precise and wrong.** Signal-to-noise 5.78, which looks
excellent, and then it picks *"even but dull"* as the best deck the Teacher could possibly build.
It is a level, not a change, so it cannot separate an instructive even matchup from a boring one,
and it actively prefers the boring one because that one sits exactly at 50%. This is textbook
[`METRICS.md`](../docs/METRICS.md) §17: a metric that a degenerate strategy scores well on. **Do not
make this the Teacher's objective.** A Teacher optimising it converges on mirror-ish durdle decks
that produce even, uninformative games forever.

**Your fallback idea is the answer.** You wrote:

> *"Maybe measurments like speed of action/confidence/reasoning passes can be proxies for how well
> it plays"*

That is right, and the reason is structural rather than clever. Win rate yields **one bit per
game**. Reasoning passes, policy confidence, value spread and decision latency are emitted at
**every decision**, which is hundreds per game. Same games, two to three orders of magnitude more
observations about how hard the Student is finding this matchup. Signal-to-noise 13.22 at 100
games, and it recovers the true teaching value almost exactly, 0.080 against a true 0.080. It is
**78 times** the precision of the literal proposal at the same cost in games.

The modelling here is deliberately pessimistic: per-decision noise is set equal to the effect size.
Even so it wins by two orders of magnitude, because the sample count dominates.

## What follows for the design

1. **Train the Teacher on per-decision difficulty proxies**, not on win-rate delta. Reasoning
   passes consumed is the most direct one and it comes free from the halting head, which is another
   reason that head has to be trained.
2. **Keep win-rate delta as a slow validating check**, computed over accumulated blocks, never as
   the per-update reward. It is unbiased and it is the thing we actually care about, so it is the
   right auditor and the wrong trainer.
3. **Keep paired both-sides play.** Your instinct was sound and it is a real variance reduction, it
   just cannot carry this signal alone.
4. **Never use closeness to 50% as the objective.** It can serve as a cheap *filter* to reject
   unplayable matchups, which is what you wanted it for originally, but not as the reward.
5. **A guard against gaming.** A Teacher rewarded for making the Student think hard could learn to
   build decks that are merely confusing rather than instructive. The audit in point 2 is what
   catches that: if proxy difficulty rises while win-rate delta does not, the Teacher is gaming the
   proxy. That contradiction pair belongs in the review protocol's precedence table.

## Caveat

This is a statistical model of the estimators, not a simulation of Magic. It is the right level for
the question, which is about estimator variance and not about card interactions. The one assumption
worth challenging is that per-decision difficulty proxies actually track learning. That is
testable, cheaply, on the first real training run: log reasoning passes per decision alongside
win rate per block and measure the correlation. If it is weak, this conclusion weakens with it.
