# The Teacher's reward signal: measured, not argued

You raised the crux yourself:

> *"I just think its quite a few games and it will be a noisy estimate that will then be noisy
> reward for the teacher."*

You were right. Reproduce with [`tools/teacher/reward_noise.py`](../tools/teacher/reward_noise.py).

> **Corrected 2026-09-10.** The first version of this document claimed the per-decision proxy was
> **78 times** better than the win-rate delta, and that mirrored play improved the delta from 0.17
> to 0.25. Both were artefacts of bugs in my own simulation, found in adversarial review. The real
> figure is **8.3 times**, and mirrored play at a matched game budget is roughly **neutral**. The
> bugs and the corrected numbers are in §4. The qualitative conclusions survive; the margin does
> not. Do not build on the earlier figures.

## Method

Five decks with known teaching value, from unwinnable to very instructive, where teaching value is
how much the Student's win rate genuinely rises over a block of games against that deck. Each
candidate estimator is run 1,500 times per deck, and judged on two things:

1. **Precision.** Signal-to-noise: spread across genuinely different decks over spread across
   repeats of the same deck. Below 1.0 the noise between repeats of one deck exceeds the real
   difference between decks, so the Teacher is training on coin flips.
2. **Accuracy.** Does it rank the decks correctly? An estimator can be precise and still point the
   wrong way.

## Result

| estimator | N=20 | N=100 | N=400 | ranks correctly |
|---|---|---|---|---|
| **win-rate delta, as proposed** | 0.07 | **0.18** | 0.39 | yes |
| win-rate delta, mirrored, matched budget | 0.09 | 0.17 | 0.35 | yes |
| regression slope instead of two halves | 0.09 | 0.21 | 0.44 | yes |
| slope, mirrored | 0.10 | 0.20 | 0.41 | yes |
| closeness to a 50% win rate | 2.66 | **5.95** | 11.28 | **no** |
| **per-decision proxy slope** | 0.68 | **1.52** | **3.01** | yes |

Ranking check at N=100:

| deck | true teaching value | closeness to 50% | per-decision proxy |
|---|---|---|---|
| unwinnable | 0.005 | 0.104 | low |
| too easy | 0.005 | 0.095 | low |
| **even but dull** | 0.010 | **0.920 (top)** | low |
| instructive | 0.040 | 0.866 | mid |
| **very instructive** | **0.080** | 0.832 | **top** |

## What this says

**The literal proposal does not work.** 0.18 at 100 games. The Teacher cannot distinguish an
unwinnable deck from a very instructive one. It is unbiased, the means order correctly, but a
single block is dominated by noise and a single block is what the Teacher gets per update.

**Rewarding closeness to a 50% win rate is precise and wrong.** Signal-to-noise 5.95, and it
picks *"even but dull"* as the best deck available. It is a level, not a change, so it cannot
separate an instructive even matchup from a boring one and actively prefers the boring one for
sitting exactly at 50%. This is [`METRICS.md`](../docs/METRICS.md) §17 exactly: a metric a
degenerate strategy scores well on. **Do not make it the objective.** A Teacher optimising it
converges on mirror durdle decks forever. Keep it as a cheap filter to reject unplayable matchups,
which is what you originally wanted it for.

**Your fallback idea is still the best trend estimator, by 8.3x.** Reasoning passes, confidence and
action speed are emitted at every decision rather than once per game, so the same games carry more
information about difficulty. But the margin is far smaller than I first reported, and the reason
is the correction in §4: decisions inside a game are not independent observations.

**It needs about 400 games per block, not 100.** At N=100 the proxy reaches 1.52, which is
trainable in principle and very slow. At N=400 it reaches 3.01, which is usable. That is a real
cost and it should be planned for rather than discovered.

## §4. The two bugs, and why they mattered

**Bug 1: I treated clustered observations as independent.** The proxy estimator drew independent
noise for each of `n_games * 250` decisions. Decisions inside one game are massively correlated
through the recurrent state, the deck, the draw and the opponent, so they are nothing like
independent samples. At an intra-class correlation of 0.3 the design effect is 76, meaning **one
game's 250 decisions are worth about 3.3 independent observations, not 250.**

The sharp part: [`METRICS.md`](../docs/METRICS.md) §1.4 Rail D, which I wrote and committed hours
earlier, says exactly this and forbids exactly this. My own tool violated my own rail. That is the
"instrument that cannot detect its own no-op" failure the protocol warns about, and it is the
argument for the A/A test on the measurement pipeline that the protocol already mandates.

Fixed by modelling it as a random-effects design: a shared latent per game moving all its decisions
together, plus independent per-decision noise, with the estimator regressing per-game means.

**Bug 2: the mirrored condition silently spent twice the games.** It built `n_games` mirrored
*pairs*, so two games each, and compared that against `n_games` unmirrored games. The apparent gain
was a doubled budget worth about sqrt(2), not a pairing effect.

Fixed by matching the budget. At matched budget, **mirroring is roughly neutral for this
estimator** (0.17 against 0.18). That is not an argument against mirrored play, which is still
right for other reasons and reduces variance for *level* estimates. It is an argument that
mirroring does not rescue a *trend* estimate, because halving the number of time points costs about
what the variance reduction gains.

## The idea that beats all of them: stop looking inside the block

The best result did not come from a better estimator. It came from questioning the premise.

Every estimator above tries to see the Student learn *during* a block of 100 or 400 games. Learning
over 100 games is tiny, which is why they all struggle. The alternative is to not look there at
all: **replay the same deck with a much later checkpoint, and difference two block means.**

Measured with [`tools/teacher/proxy_clustering.py`](../tools/teacher/proxy_clustering.py), with a
Student whose competence on a deck saturates over about 8,000 games of training:

| estimator | SNR | versus the within-block slope |
|---|---|---|
| within-block slope, as proposed | 0.04 | 1.0x |
| revisit after 200 games | 0.11 | 3.0x |
| revisit after 1,000 games | 0.53 | 14.8x |
| **revisit after 5,000 games** | **2.12** | **59.5x** |
| revisit after 20,000 games | 4.22 | 118.2x |

The signal was never too small. It was being measured over the wrong interval. A difference of two
well-estimated means separated by thousands of games of training is far easier to see than a trend
inside a few hundred.

**Pick the gap deliberately, around 5,000 games.** Too short and there is no signal. Too long and
the estimator degenerates: once the Student has fully saturated on a deck, "how much better is it
now than then" collapses into "how good is it now", which is a level, and levels are how
closeness-to-50% went wrong. At a 20,000-game gap against an 8,000-game time constant, about 92% of
the learning has already happened and the estimator is mostly measuring the current level. The
5,000-game row keeps a genuine difference and still reaches a usable 2.12.

The cost is real and should be stated: it requires **keeping decks and replaying them later**, so
the Teacher's reward for a deck arrives thousands of games after it built it. That is fine for a
critic fitted over a buffer, which is what the design uses, and fatal for a policy gradient
consuming one scalar per update, which is one more reason the design does not use one.

## What follows for the design

1. **Train on per-decision difficulty proxies**, not win-rate delta. Reasoning passes is the most
   direct one and comes free from the halting head, which is another reason that head must be
   trained.
2. **Budget about 400 games per block**, not 100.
3. **Keep win-rate delta as a slow auditor** over accumulated blocks. Unbiased and it is what we
   actually care about, so it is the right auditor and the wrong trainer.
4. **Never use closeness to 50% as the objective.** Filter only.
5. **Guard against gaming.** A Teacher rewarded for making the Student think hard could build decks
   that are merely confusing. If proxy difficulty rises while the win-rate audit does not, the
   Teacher is gaming the proxy. That contradiction pair belongs in the review protocol's precedence
   table.
6. **Pool across blocks rather than consuming one noisy scalar per update.** This is the strongest
   idea to come out of review and it partly dissolves the crux: fitting a critic across a buffer of
   many blocks needs far less per-block precision than a per-block policy-gradient step does.

## Caveats

This is a statistical model of the estimators, not a simulation of Magic. That is the right level
for a question about estimator variance, but it means two numbers are assumptions rather than
measurements, and both are load-bearing:

- **the intra-class correlation, set to 0.3.** If decisions within a game are more correlated than
  that, the proxy advantage shrinks further. Measurable on the first real run.
- **that per-decision difficulty proxies track learning at all.** Testable cheaply: log reasoning
  passes per decision alongside win rate per block and measure the correlation. If it is weak, this
  conclusion weakens with it.
