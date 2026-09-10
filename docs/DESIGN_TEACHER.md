# DESIGN_TEACHER.md: the teacher, the critic, and the 1-by-1 drafter

**Status:** design, not implementation. Written 2026-09-10 against HEAD `45047cd`.
**Scope:** what the teacher is trained on, what stops it gaming that signal, what it is
architecturally, how it drafts one card at a time, how a deck's outcome reaches an individual pick,
what it costs in games, and the order the pieces get built in.

Companions: [`NORTH_STAR.md`](../NORTH_STAR.md) §1 §3, [`docs/METRICS.md`](METRICS.md) §15 §17,
[`docs/COST_MODEL.md`](COST_MODEL.md), [`docs/DESIGN_CARD_POOL.md`](DESIGN_CARD_POOL.md),
[`docs/DESIGN_TRAINING.md`](DESIGN_TRAINING.md) §4,
[`docs/TRAINING_REVIEW_PROTOCOL.md`](TRAINING_REVIEW_PROTOCOL.md) §8.3,
[`reports/TEACHER_REWARD_FINDINGS.md`](../reports/TEACHER_REWARD_FINDINGS.md) and its correction in
§1.3 below.

The engine is being rebuilt (`docs/DECISIONS.md` D1). Every section names what it needs from the
rebuild, using the `E-*` requirement ids from `docs/METRICS.md` §15.

---

## 1. The crux, and the answer

### 1.1 The crux, stated as arithmetic

The proposal was: build a matchup, play a block of N games, reward the teacher for the increase in
the student's win rate across the block. The owner identified the problem before anyone else did.
Here is the arithmetic in full.

A game is one bit. At p = 0.5 the per-game standard deviation is 0.5, so:

| quantity | formula | N = 20 | N = 100 | N = 1000 |
|---|---|---|---|---|
| SE of a single win rate | `0.5/sqrt(N)` | 0.112 | 0.050 | 0.016 |
| SE of the halves difference | `1/sqrt(N)` | 0.224 | 0.100 | 0.032 |
| same, rescaled to a per-block change | `2/sqrt(N)` | 0.447 | 0.200 | 0.063 |

Against that, the true quantity. A single card swap in a 100-card deck is worth on the order of
0.1 to 0.5 win-rate points. Within-block student learning on one matchup over 100 games, under a
saturating curve with a time constant of order 10^3 to 10^4 games, is of the same order. **The
estimator's noise is 0.20 and the signal is 0.005 to 0.05.**

Two clean facts sit underneath, both exact and both worth knowing:

- **Fit the slope, never the two halves.** `Var(slope) = 12 sigma^2 / N` against
  `Var(halves, rescaled) = 16 sigma^2 / N`. The slope is 4/3 as efficient, for one line of code.
- **Getting from SNR 0.19 to SNR 3 needs a 250x variance reduction**, i.e. roughly 25,000 games per
  teacher update. No stacking of slope-fitting, seat mirroring and common random numbers gets
  within two orders of magnitude of that. **The win-rate family is not rescuable by variance
  reduction. It needs a different observable.**

### 1.2 The measured estimator ladder

`tools/teacher/reward_variance.py`, 4,000 trials per cell, five decks with known teaching value,
results in `reports/teacher_reward_variance.json`. SNR = between-deck spread of the estimator over
within-deck spread across repeats. `rank rho` = Spearman between the estimator's expectation and
true teaching value. `nuisance payout` = how much the estimator moves when board width and decision
count change while teaching value is held fixed, i.e. what a reward hacker is paid.

| | estimator | N=20 | N=100 | N=400 | rank rho | nuisance payout |
|---|---|---|---|---|---|---|
| A | win-rate halves, **as proposed** | 0.09 | 0.19 | 0.38 | 1.00 | 0.086 |
| B | win-rate slope over the block | 0.10 | 0.21 | 0.44 | 1.00 | 0.074 |
| C | slope + seat-mirrored, **equal game budget** | 0.06 | 0.14 | 0.28 | 0.90 | 0.150 |
| D | closeness to 50% | 2.67 | **5.92** | 11.34 | **0.50** | 0.001 |
| E | per-decision proxy slope, **clustered** | 0.16 | 0.35 | 0.70 | 1.00 | 0.030 |
| F | per-decision proxy slope, naive (the published 78x) | 1.76 | 3.88 | 7.86 | 1.00 | 0.005 |
| G | **frozen-probe paired delta** | 0.66 | **1.44** | 2.87 | 1.00 | **0.003** |
| H | raw gradient magnitude | 2.61 | 5.75 | 11.43 | 1.00 | **0.566** |

Row D is the term currently in the code at `teacher.py:147`
(`reward = (0.7 * improvement) - (0.3 * winrate_penalty)`). It has the best SNR of any win-rate
derived quantity and it ranks "even but dull" above "very instructive"
(`reports/teacher_reward_variance.json`, `ladder`). **A high SNR with a low rank rho is a precise
measurement of the wrong thing.** Row H is the noisy-TV failure of curiosity-driven RL: noise has
magnitude, so a chaos deck is paid 0.566.

### 1.3 Two corrections to `reports/TEACHER_REWARD_FINDINGS.md`

These must land before anything is built on that report.

**Correction 1: the per-decision proxy is worth about 2x, not 78x.**
`tools/teacher/reward_noise.py:141` draws `n_games * 250` proxy observations and treats every one as
independent. `docs/METRICS.md:118-122` forbids exactly this, in this repo, about this quantity, and
`docs/TRAINING_REVIEW_PROTOCOL.md:804-809` makes it a hard rule. With a per-game random effect
ICC = 0.05 and within-game AR(1) rho = 0.9 at the measured p50 of 2,173 decisions per game
(`reports/decision_counts_devbox.json`):

```
effective independent decisions per game = 2173 * (1-0.9)/(1+0.9)  = 114
variance of the game mean                = 0.05 + 0.95/114          = 0.0583
design effect                            = 0.0583 / (1/2173)        = 126.7
a game is worth 17 independent decisions, not 2173
naive per-decision SNR is inflated by sqrt(126.7) = 11.3x
```

13.22 / 11.3 = 1.17. The clustered simulation gives 0.35 at N = 100 (row E), lower still because the
slope over game means loses further efficiency. The correction moves the conclusion from "solved"
to "not solved".

**Correction 2: seat mirroring buys nothing as variance reduction, and the reported gain is a
doubled game budget.** `tools/teacher/reward_noise.py:78` returns `(a+b)/2` for each of `n_games`
entries, so the paired arm plays `2n` games against the unpaired arm's `n`. The reported 0.17 to
0.25 is sqrt(2) = 1.41, and 0.17 x 1.41 = 0.24. At equal game budget the effect on a *delta*
estimator is 1.00x, and the theory says why: **deck and seat advantage are constant within a block,
so they difference out of any within-block delta already.** Mirroring removes a confound the delta
estimator never had.

Mirroring is still worth having. It is a bias-control device for *level* comparisons, it is the
right way to detect a broken deck ("student wins from side A only", `ideas.md:171-179`), and it
belongs in the league and the auditor. It is not variance reduction for a learning delta, and it
constrains which games may be played.

### 1.4 The answer: what the teacher is actually trained on

> **The teacher is scored by the drop in loss on a frozen, global, teacher-inaccessible probe bank,
> caused by training the student on this block's trajectories, residualised on the compute the block
> consumed. That per-block score is then pooled into a learned critic over decks, and the teacher
> optimises against the critic, never against a single block.**

Formally, with a fixed probe set `P` of K decision records and `theta' = update(theta, traj(block))`:

```
dL         = L(theta; P) - L(theta'; P)
R(block)   = dL + lambda_ret * dL_retained(after M later blocks)
             - f_hat(decisions_consumed, passes_consumed, game_length)
             gated to 0 if the deck fails DFT-5 pre-flight
```

To first order in the learning rate this is exactly

```
dL  ~  eta * <  grad_theta L(theta; block) ,  grad_theta L(theta; P)  >
```

which is the whole design in one line: **the teacher is paid for the alignment between the gradient
its matchup produces and the gradient of the thing we actually care about.**

### 1.5 Why that one, and the credit that is owed

The owner's own escape hatch was: *"maybe measurements like speed of action / confidence / reasoning
passes can be proxies for how well it plays"*. **That instinct is correct and it is the load-bearing
idea in this document.** The insight is that the signal must come from quantities available
thousands of times per game rather than once, and it was named as a teacher input in the deleted
`RL_ARCHITECTURE.md` §5.1 (*"win rate, 'confidence' gap, or reasoning depth used"*) eleven months
before this design.

The probe delta *is* that idea, done with the one piece of statistical discipline the naive version
lacks: **pairing on identical states**. The probe bank is K per-decision records. The before and
after evaluations run on the same K records, so all state-sampling variance cancels **by
construction, not in expectation.** That is what defeats the 126.7x design effect that quietly
destroys the unpaired version (row E, 0.35) and produces row G at 1.44 from the same underlying
per-decision quantities.

Four properties follow from the formula rather than from patches bolted on:

1. **Paired.** State-sampling variance cancels exactly.
2. **An inner product, not a norm.** A gradient made of pure noise has large magnitude and zero
   expected alignment. Chaos is paid nothing: measured nuisance payout 0.003 for G against 0.566 for
   H.
3. **Not a proxy for improvement, it is improvement**, measured on the right set, one update at a
   time, before noise accumulates.
4. **The probe is global and the teacher never sees or influences it.** So the teacher cannot be
   paid for making the student overfit the teacher's own matchup. This single property kills a whole
   family of exploits at once.

Per-decision proxies do not disappear. They enter in three places, all of them appropriate:

| use | which quantities | why here |
|---|---|---|
| the probe records themselves | full probability vector, value, chosen index, terminal outcome | the probe loss *is* a per-decision loss |
| features for the critic | value error, value spread, policy entropy, top-1 margin, legal-action count, decisions consumed | dense and free, and the critic may use biased features because the reward it predicts is unbiased |
| the fallback estimator | the clustered proxy slope, row E | if the gamma experiment (§9 Q1) comes back small, this plus the win-rate slope is what the design degrades to |

**What per-decision proxies are not**: the reward. Row E measures 0.35 at N = 100 once clustering is
put back, which is below the 1.0 at which the teacher can distinguish an unwinnable deck from an
instructive one.

### 1.6 The second half of the answer: stop consuming the reward one block at a time

Everything above assumes the teacher needs a per-block SNR near 3. It does not, because it is not
doing REINFORCE on a per-block scalar. Fit a critic across a replay buffer of blocks and let the
teacher rank against the critic.

A card in a 100-card deck drawn from a legal pool of P non-lands appears in roughly `100 B / P`
blocks. At P = 350:

| blocks in buffer B | blocks containing a given card | SNR multiplier | required per-block SNR |
|---|---|---|---|
| 100 | 29 | 5.3x | 0.561 |
| 500 | 143 | 12.0x | 0.251 |
| **2,000** | **571** | **23.9x** | **0.125** |
| 10,000 | 2,857 | 53.5x | 0.056 |

At B = 2,000 a per-block SNR of 0.125 gives per-card SNR 3. **The win-rate slope (row B, 0.21 at
N = 100, 0.10 at N = 20) already clears that.** The probe delta clears it by an order of magnitude
and leaves headroom for pairwise interactions: a specific pair of cards co-occurs in
`(100/350)^2 * B = 163` blocks at B = 2,000, a triple in 47.

Three conditions on that claim, stated because they are load-bearing and because one of them
degrades exactly where the teacher is working:

- The per-block reward must be **unbiased**. Rows D and H are not, and are therefore excluded.
- The deck-to-value map must be approximately decomposable into card effects plus low-order
  interactions. This is why the critic is a set-transformer over card tokens and not a black box
  over a deck hash.
- **The sqrt(571) multiplier is an upper bound, not an estimate.** It assumes decks are near
  independent draws so card coefficients are near orthogonal. A teacher doing its job concentrates
  the deck distribution and the design matrix goes collinear precisely in the region of interest.
  Mitigations: the diversity cap in §2.3 and the outgroup in §2.5. The alarm is a falling held-out
  R^2. See §9 Q4.

**The reframe to hold onto: the reward does not need to be precise per block. It needs to be
unbiased, and it needs to be pooled.** The crux is real, the numbers make it worse than feared
(0.19 rather than 0.17, and both proposed mitigations are worth 1.33x and 1.00x respectively), and
it is the wrong problem to solve. Do not hunt for a low-variance per-block reward. Build an unbiased
one and average it properly.

---

## 2. The objective, precisely

### 2.1 Definitions

| symbol | meaning |
|---|---|
| `d` | a matchup: two (or four) decklists plus declared commanders, persisted per `E-DECK` |
| block | N consecutive games on a fixed `d`, seats rotated, seeds separated per `E-SEED` |
| `P` | the probe bank: K frozen `(observation, legal menu, action, target, outcome)` tuples, versioned, sampled across the league, **never chosen or influenced by the teacher** |
| `R(d, w)` | the per-block score in §1.4, computed in window `w` |
| `Phi(d)` | the learned critic's prediction of `R`, plus a predicted log-variance |
| gate | `DFT-5 finished_deck_quality` (`docs/METRICS.md`, family DFT) run as a pure function of the decklist |

### 2.2 The full score

```
1.  gate:     DFT-5 fails                                ->  R = 0, deck evicted, no games played
2.  band:     student win rate outside [0.10, 0.90]      ->  R = 0   (POET minimal criterion)
3.  paired:   dL  = L(theta; P) - L(theta'; P)               on identical records
4.  retain:   + lambda_ret * ( L(theta; P) - L(theta_{+M}; P) )   re-evaluated M blocks later
5.  residual: - f_hat(decisions, passes, mean legal-action count, game length)
6.  rescale:  quantile-rank R against the last 200 scores        (Graves 2017)
```

Step 5 is a **residual, not a ratio**. Dividing by decisions rewards short games; regressing them
out prices them.

Step 6 makes the teacher scale-free, which matters because the probe loss scale drifts as the
student improves. It is the highest-value 30 lines in the whole objective if the teacher is ever run
as a policy-gradient agent (measured elsewhere at 0.849 rising to 0.966 of oracle).

Step 2 deserves a line of its own. **Closeness to 50% survives only as a filter band, never as a
score.** That is what the owner originally wanted it for ("to make sure it isn't just completely
destroyed by impossible deck matchups"), and as a filter it is free and correct. As a score it is
row D: SNR 5.92, rank rho 0.50, and it prefers a boring mirror to an instructive matchup.

### 2.3 Diversity is a constraint, not an objective

The archive holds a **per behaviour cell cap of 2** (cells defined on colour identity, mean mana
value bucket, creature share, interaction share). Simulation against a flat priority archive at the
achievable SNR, as a fraction of an oracle teacher:

| ZPD width | uniform | flat top-B archive | MAP-Elites | capped archive |
|---|---|---|---|---|
| 0.60 | 0.814 | 0.911 | 0.837 | - |
| 0.40 | 0.773 | 0.915 | 0.766 | 0.902 |
| 0.25 | 0.321 | 0.734 | 0.415 | 0.675 |

MAP-Elites buys about +2 behaviour cells of coverage in 300 blocks and loses up to 32 points of
teaching value. It optimises coverage, and coverage is not the objective. The capped archive costs
1 to 6 points and keeps the diversity. **Recommendation: flat priority archive with a per-cell cap.**
Keep MAP-Elites as a separate archive for the niche-deck goal in `ideas.md:1-11`, where coverage
genuinely is the objective.

### 2.4 What a degenerate teacher produces, and why the reward does not pay it

Checked against `docs/METRICS.md` §17. The register's rule: *any metric whose numerator can be
satisfied by not acting must be published paired with one whose numerator can only be satisfied by
acting well.*

| degenerate teacher | what it produces | does the reward pay it? |
|---|---|---|
| **the current one** (frozen random MLP, `teacher.py:60` `torch.no_grad()`, no `backward()` anywhere in `train_teacher`) | 300/300 sampled decks 5-colour, 54.6 lands per 100, 65.2 distinct cards, max mana value 3, commander a uniformly random card and 60.7% a basic land (`game_initializer.py:82` pops index 0 of a list `deck_generator.py:196` already shuffled) | **No.** `DFT-5` fails it on land count, colour count, singleton and curve simultaneously, before a single game. Cost: microseconds. This is the cheapest and strongest null defence in the design |
| **always the same good matchup** | one deck forever | **No, self-limiting.** `dL -> 0` as the student masters it, and the archive's staleness decay evicts it. This is the standard argument for a *change*-based reward over a *level*-based one |
| **maximally chaotic decks** (token swarms, many activated abilities) | huge TD error, huge gradient norm, high entropy, many passes, high latency | **No, twice over.** (i) alignment not magnitude: payout 0.003 for G against 0.566 for H. (ii) `f_hat` residualises out legal-action count and decisions consumed, so branching factor pays exactly zero by construction. This exploit directly attacks the King Goal's clock entry (`NORTH_STAR.md` §1a, `DECISIONS.md` D4) and must be closed structurally, not by a threshold |
| **long-game decks** | more decisions, therefore more gradient | **No.** `game_length` is a residualised feature |
| **impossible decks** | student loses every game | **No.** `dL ~ 0` and the minimal-criterion band rejects it before it enters the archive |
| **overfit-then-forget decks** | transient probe gain | **No.** `lambda_ret` re-evaluates M blocks later. One forward pass |
| **decks that damage the student** | catastrophic update | **Correctly punished.** Global probe loss rises, `R` goes negative |
| **a teacher that never varies its decks** | critic unidentifiable | **This is the one the reward cannot catch.** Handled by the per-cell cap (§2.3) and the outgroup alarm (§2.5) |
| **the reward currently in the code** | anything at all | pays a hard constant **+0.1667**. `select_archetypes` (`teacher.py:129`) and `train_teacher` (`teacher.py:152`) write `last_benchmark_score` under different contracts, and with `deck_refresh_freq = 1` (`config_rl.py:10`) the refresh fires first every episode, so `improvement` at `teacher.py:140` is not a delta but the raw solve rate |

### 2.5 The auditor, and the two contradiction alarms

The auditor is **win-rate delta accumulated over the whole archive**, never per block. It is
unbiased and hopeless as a trainer, which makes it exactly the right auditor.

The auditor's own null is "approximately 0", which a lazy teacher also achieves, so it is not a
scoreboard. It is a **contradiction detector**:

> **Alarm 1: probe reward rising while the accumulated win-rate delta over the archive stays flat.
> That is the teacher gaming the proxy.**

> **Alarm 2: the critic's calibration error on a permanently maintained population of uniform
> random *legal* decks rising while its error on policy decks falls. That is deck-space collapse.**

Alarm 2 exists because the drafter's errors get baked into the *decks*, which are the training data
for every strategy metric in `docs/METRICS.md`. Win rate looks fine throughout, because everyone is
playing the same decks. The random-legal outgroup is not a phase; it stays in the league forever.

New rows for the `docs/METRICS.md` §17 register:

| ID | metric | null (always pass) | uniform random | mandatory pairing |
|---|---|---|---|---|
| `TCH-1` | probe-delta reward | 0 (a null teacher's decks are gated to 0) | small positive early, decaying | with `TCH-4` and `DFT-5` |
| `TCH-2` | block gradient norm | - | **large** | never alone; only as the denominator of alignment |
| `TCH-3` | mean reasoning passes / latency | measures an untrained argmax hitting class 9 | - | **deleted** until `DQ-9` shows non-zero cross-pass churn |
| `TCH-4` | accumulated win-rate delta | 0 | 0 | the auditor. Never the trainer |
| `TCH-5` | critic calibration on the random-legal outgroup | - | - | published beside every deck metric |

### 2.6 The uncomfortable finding that must not be edited out

Simulation of teacher strategies against an oracle that sees the true teaching value of every
candidate (1.00 = oracle, 300 blocks, 100 runs):

| ZPD width | P(random deck is useful) | uniform random teacher | curator | headroom |
|---|---|---|---|---|
| 1.20 | 0.134 | 0.818 | 0.872 | 0.063 |
| 0.60 | 0.043 | 0.812 | 0.914 | 0.102 |
| 0.25 | 0.015 | 0.321 | 0.719 | 0.398 |
| 0.15 | 0.009 | 0.046 | 0.240 | 0.194 |

**A uniform random teacher already scores 0.815 of oracle at moderate width.** The teacher's
headroom is entirely a function of how rare a well-targeted deck is. Today's measured
`P(random deck is even legal) = 0/300` puts the project in the right-hand regime, but for a
*legality* reason and not a *teaching-value* reason.

**The first 10x of "teacher value" available here is a constraint filter, not a learned agent.** That
is deflating for the teacher-as-hero framing and it is why `DFT-5` and the legality mask are stage 0
and the teacher itself is stage 3. It is also fully consistent with `NORTH_STAR.md` §3: legality is a
rule of Magic, not a strategy heuristic.

---

## 3. What the teacher is, architecturally

### 3.1 Bandit, RL agent, or curator: the position

**Not a policy-gradient RL agent over a per-block scalar.** A 30-game block is 13 to 22 minutes at
`docs/DESIGN_TRAINING.md` §4 rates, so a REINFORCE teacher gets on the order of 60 to 100 gradient
steps per day, each dominated by noise. Simulated at the achievable estimator quality, REINFORCE
scores 0.849 of oracle against a uniform random teacher's 0.815 and a curator's 0.893. A linear
Thompson bandit scores 0.751, **worse than uniform**, because a model that generalises across deck
space amplifies a biased signal instead of averaging it away. That last number is a standing warning
about the "big relational network" ambition and it is why §3.3 sizes the critic against the data.

The literature agrees and this is not a close call. Matiisen 2017 frames the teacher's problem as a
POMDP and then solves it as a non-stationary bandit. Graves 2017 uses EXP3.S over tasks. Portelas
2019 (ALP-GMM) fits a GMM over task space. Jiang 2021 (PLR) and Parker-Holder 2022 (ACCEL) use a
priority queue with an edit operator and train no generator at all. Nobody trains a teacher with
REINFORCE on a block-level scalar, because nobody has the samples.

**The teacher is therefore three objects, and only the middle one is a network:**

```
  archive       ranks candidates by Phi, samples by staleness-aware priority,
  (curator)     evolves survivors by single-card edits, caps per behaviour cell
       |
       v
  critic Phi    learned. set-transformer over card tokens. predicts R and log-variance
       |
       v
  proposer      the 1-by-1 pick head of §4, trained by distillation from the archive
                and by hill-climbing Phi. Zero additional games.
```

The edit operator is **swap one card**, which is simultaneously the ACCEL mutation, the owner's
1-by-1 draft primitive, and `ideas.md`'s *"train with same deck with 1 or few cards change"*. A
one-card swap evaluated by paired both-sides play with common random numbers is the lowest-variance
deck experiment available, because the two decks share 99 of 100 cards.

### 3.2 What the critic sees, and how card interactions are represented

```
critic input =
    [ v_card(c) for c in deck A ]                    role tag A         up to 100
  + [ v_card(commander_A) ]                          role tag CMD_A             1
  + [ v_card(c) for c in deck B ]                    role tag B         up to 100
  + [ v_card(commander_B) ]                          role tag CMD_B             1
  + [ FORMAT_TOKEN(format_id, pool_hash_bucket) ]                               1
  + student profile vector, injected by FiLM, not as a token                   64
```

**No positional embedding on deck tokens.** A deck is a set. Order invariance is not a nicety: it is
what makes `DFT-3`'s order-invariance check structurally satisfied rather than merely measured, and
it is what makes "complete this human's 66 cards" the same forward pass as "continue my own
construction".

**Card interactions are represented by full pairwise attention over the at most 203 tokens.** A
mean-pooled deck summary is permutation invariant *and linear*: it can express "how many creatures"
and it structurally cannot express "has both A and B", which is what synergy is. 203 tokens is about
41,000 pairs, which is free: `docs/COST_MODEL.md` §1 shows arithmetic is oversupplied by 458x at
batch 1. This is the "big relational network" the owner asked for, and it is right in kind.

Because `v_card` is a composed ability-tree vector (`docs/DESIGN_CARD_POOL.md` steps 1 to 3), the
attention matches on **atoms, not identities**: a sacrifice outlet is
`Activated(Cost{SACRIFICE ...}, ...)` and a recursion spell is
`Atom(MOVE_ZONE, graveyard -> battlefield)`, and the pair is recognisable in a set the model has
never seen. **This is why the compositional card encoder is a hard gate on the teacher, not a
nice-to-have.** Today the only thing the network ever sees about a card is a 65-float action
descriptor that `docs/ARCHITECTURE.md` records as carrying no card identity at all, so there is
literally nothing to attend over.

**On "one part to encode how the student performs":** encode a *profile vector* of about 64 to 128
floats of **measured behaviour** over a recent window (mean value error, value spread, policy
entropy, top-1 margin, per-phase blunder proxies, recent Elo), never the student's weights and never
a learned embedding table over checkpoint ids. A hypernetwork over a 315M-parameter student puts a
300M read inside the teacher's forward pass for no payoff. A checkpoint-id embedding can only
memorise and starts at random initialisation on every new checkpoint, which is a §17 trap.

### 3.3 Shapes and parameter counts

| block | shape | params |
|---|---|---|
| `v_card` card vectors | `DESIGN_CARD_POOL` steps 1-3, d = 256, computed offline and cached as a tensor | **0 marginal** (shared with the play model) |
| deck encoder | 6 layers, d = 256, self-attention over <= 203 tokens. Per layer `4d^2 + 2*d*4d = 786k` | 4.72 M |
| candidate scorer | 2 cross-attention layers (candidates attend to the deck) + bilinear pointer | 1.64 M |
| critic heads | MLP 256 -> 512 -> 1 for `R`, second head for log-variance | 0.26 M |
| student-profile FiLM | 64 -> 512 -> 512 | 0.33 M |
| auxiliary heads | card-realisation, cast-together, curve reconstruction | 0.20 M |
| | **total new parameters** | **~7.2 M** |

**Size it against the data, not against the intuition that deck interactions are complicated.** At
B = 2,000 deck labels a 7 M-parameter model is already over-parameterised; run it with strong weight
decay. The growth rule is explicit and published: **hold out 10% of blocks, print out-of-sample R^2
in every review, and grow the deck encoder one step (d = 256 -> 384 -> 512, or 6 -> 8 layers) only
when held-out R^2 has been flat-topped for two consecutive windows.**

### 3.4 Cost model check

The teacher is **outside the decision loop entirely**, which is the whole reason this is affordable.
`docs/COST_MODEL.md` §2: a parameter is charged once per read.

| | value | source |
|---|---|---|
| teacher weight bytes | 7.2 M x 2 = 14.4 MB | §3.3 |
| forward passes per deck | 100 picks + 3 refinement sweeps ~ 103 | §4.6 |
| bytes per deck built | ~1.5 GB, plus retrieval | |
| at 273 GB/s | ~5.4 ms; launch-bound in practice, so ~0.2 to 0.4 s per deck | `HARDWARE_DGX_SPARK.md` |
| games that deck then plays | N = 30 x ~2,173 decisions = 65,190 decisions | `reports/decision_counts_devbox.json` |
| **amortised teacher traffic per game decision** | **~23 KB** | |
| board encoder traffic per decision, current arch | **800 MB** | `reports/latency_devbox.json`, `bytes_per_decision` |
| **teacher share of the decision budget** | **~0.003%** | |

Critic read once per block: 6.6 MB over 65,190 decisions = 101 bytes per decision.

Probe evaluation, K = 2,048 records, forward only, one static batch, at 0.4 compute efficiency on
125 TFLOPS:

| model | GFLOP/decision | one probe eval | the before/after pair | overhead on an N=30 block (~780 s) |
|---|---|---|---|---|
| v0.5 | 19.7 | 0.8 s | 1.6 s | **0.2%** |
| current arch | 84.0 | 3.4 s | 6.9 s | **0.9%** |

(`reports/latency_devbox.json`, `flops_per_decision`.) Both sit inside the 5% measurement budget of
`docs/METRICS.md` Rail I and should be booked against it as `SYS-5`.

**Zero new parameters in the per-decision path.** That is the design constraint held throughout and
it is what makes the teacher free.

The honest answer to *"I imagine this teacher would need to be quite a large network"*: **you can
afford an enormous one.** The teacher is **not on the per-decision path at all**, so it is not
tier A and not any tier: `COST_MODEL.md` §4 tier A means the board encoder at about 0.15 reads per
decision, and the teacher runs roughly 103 forwards per deck against about 65,190 decisions, which
is 0.0016. Even 200 M parameters would stay under 1% of the decision budget and would build a deck
in about 140 ms. **The binding constraint is deck labels, not parameters.** Start at 7 M and grow by the
rule. The one failure mode to avoid absolutely: never let the teacher run inside the game loop,
which would move it to tier C and charge it 40 reads per decision.

---

## 4. 1-by-1 drafting

### 4.1 Framing

Commander has no draft (`docs/METRICS.md`, family DFT preamble). For this project **"drafting" means
deck construction plus colour and archetype preference**, and the 8-seat booster loop is the
secondary case. The primary object is a T = 100 sequential construction MDP.

### 4.2 State

| component | contents | tokens |
|---|---|---|
| prefix | cards chosen so far, as an **unordered set** of `v_card` | 0-100 |
| commander | the declared commander, role-tagged | 0-1 |
| opponent | the opposing decklist (counter-draft), or its commander only (partial information) | 0-100 |
| globals | format token, slots remaining (log-bucketed), singleton flag, deck-size target, seat count | 4-6 |
| student profile | teacher use only, FiLM-injected | 1 |

**Pick 0 is the commander**, drawn from `leadershipSkills.commander` under the format mask. It is the
highest-leverage decision in the deck because it sets the colour-identity mask for the other 99, and
making it a real decision is the root fix for `game_initializer.py:82`. M21 carries 21 rows with
`leadershipSkills.commander == True` and all of them are discarded at ingest.

### 4.3 Action: a pointer, never a per-card softmax

```
score(c | s)  =  q(s) . k(c)     where  k(c) = W_k v_card(c),  q(s) = W_q deck_encoder(s)
pi(c | s)     =  softmax over the candidate set, after the hard legality mask
```

A `|pool| x d` output softmax would be a 6.4 M-parameter layer that must be reshaped for every new
set, keyed on `cards.card_id`, which `docs/METRICS.md` `E-ID` records as an autoincrement rowid that
collides with `game_vocabulary.id` on 60 of 86 values and is renumbered on re-ingest. **The pointer
formulation makes a never-seen card pickable on day one**, which is the tied-rank-1 auto-extension
goal (`NORTH_STAR.md` §1) applied to deckbuilding. It is also the same operator as
`retrieve_topk(query(board, belief), legal_pool)` in `docs/DESIGN_CARD_POOL.md` ("Pool conditioning,
concretely"): **the drafter and the in-game pool-conditioning mechanism are one network used twice**,
exactly as the deleted `RL_ARCHITECTURE.md` §5.1 said. Do not build two.

Candidate supply differs by use, the head does not:

| use | candidates |
|---|---|
| Commander construction | the enabled pool narrowed by mask, two-stage retrieved to top-k = 256 |
| Limited pick | the up-to-14 cards in the pack |
| Limited deckbuild | the 45-card pool |

### 4.4 The legality mask, and what is deliberately not masked

```
legal(c | s) =  format_legal(c) AND engine_supported(c)
            AND colorIdentity(c) subset-of colorIdentity(commander)
            AND ( name(c) not in names(prefix) OR basic_land(c) OR any_number(c) )
            AND slots_remaining >= 1
```

Singleton, colour identity, deck size and commander eligibility are **rules of Magic**, and
`NORTH_STAR.md` §3's corollary is explicit that rules are hardcoded precisely. Applied to the logits
**before** the softmax, with the masked-out set and its reason logged per pick (`E-SLATE`). Cost: a
precomputed candidate list per colour-identity bucket (18 buckets in M21, 32 in the full pool) and a
bitset over already-picked names. Microseconds.

**Never teach legality by penalty.** The recovered `RL_ARCHITECTURE.md` §5.3 proposed exactly that
("If the Teacher proposes an illegal state, it receives a penalty") and it is the one part of that
document not adopted here. A penalty is a sample-waster and a hack surface; masking is free and
exact.

**Not masked, deliberately:** land count, curve, creature count, interaction count, colour balance.
Those are strategy. `DFT-5`'s declared target curve is a **measuring ruler** exposed to the analyst
and never to the agent, the same treatment `docs/METRICS.md` `CMD-3` gives its threat function.

### 4.5 One model, three products

| use | prefix | candidates | slots | scalar being maximised |
|---|---|---|---|---|
| build from empty | empty | retrieved top-256 | 100 | `Phi` (deck strength vs the league) |
| **complete a partial deck** | the human's 66 cards | retrieved top-256 | 34 | same |
| **counter-draft a named opponent** | empty or partial | retrieved top-256 | 100 | head-to-head `Phi` against that decklist |
| teacher | empty | retrieved top-256 | 100 | `R` from §2, the probe delta |
| Limited pick | the pool so far | the pack | - | eventual deck strength |

**The teacher and the counter-draft product are the same network with the same inputs. Only the
scalar differs.** Both condition on the opponent through the same role-tagged token block. Building
one builds the other, which is the honest answer to the owner's proposed extension: it is free.

**What makes "any prefix of any size" work is a training decision, not an inference decision.** A
policy trained only on its own left-to-right trajectories is off-distribution on a human's 66 cards.
Train on **random prefixes**: take any complete deck, sample `k ~ U(0, 99)`, hide a random subset,
predict the held-out cards. That single objective (a) trains the "complete my deck" use case exactly,
(b) enforces order invariance by construction, (c) supplies about 10^6 targets from about 10^4 decks,
and (d) is where synergy is learned. An RL-only teacher cannot do this: its policy is valid only on
the trajectory distribution it generated.

### 4.6 Refinement, which is where the quality is

A 99-step greedy chain cannot fix an early mistake made when the deck was empty. After the chain,
run leave-one-out sweeps: score `Phi(deck) - Phi(deck \ {c})` for all 100 cards (100 forward passes,
microseconds), evict the worst, re-pick under the mask, repeat until `Phi` stops rising or a budget
is hit.

This gives three things at once: an **anytime** deckbuilder (stop after any sweep), the **top-3
suggestion with a leave-one-out explanation** that `docs/BACKLOG.md` already asks for, and the
**paired one-card A/B** that is the lowest-variance deck experiment available.

Leave-one-out is an explanation and a diagnostic, **never a reward**. It is the critic's own opinion
about the critic's own input, and rewarding it is self-referential.

### 4.7 What survives `draft_simulator.py`

113 lines, imported by nothing. **Keep about 40, rewrite the rest.**

| keep | why |
|---|---|
| `generate_pack` (`:36-55`) | 1 rare/mythic with mythic at 1/8 (`:41`), 3 uncommons, 10 commons, 1 basic. Correct M21 composition |
| the pass loop (`:72`) | `(i + (pick_num if pack_num % 2 == 0 else -pick_num)) % 8` is a bijection at every pick across all 3 packs, packs 1 and 3 one way and pack 2 the other. This is the part that is usually got wrong, and it is right |
| `:25` | the only place in the entire codebase that reads the `rarity` column |

| delete | why |
|---|---|
| `:77` `random.choice(current_pack)` | the pick policy is uniform random |
| `:100` `deck = playable_pool[:23]` | the first 23 non-lands in pick order |
| `:106` | basics drawn uniformly over all five types, so a mono-red deck gets ~3.4 Mountains |
| `:101`, `:111` | `print("DEBUG: ...")` |
| `:94` | one SQL round-trip per card inside the loop, 45 per deck build |

Add before it is useful: duplicate-name suppression in collation (397 rows for 285 names, so one pack
can hold two printings of one card), wheel tracking (`DFT-2` needs it), and the `E-DRAFT` event,
which does not exist in the catalogue at all.

---

## 5. Credit assignment: how a deck's outcome reaches one pick

### 5.1 The problem, stated with numbers

The teacher gets one noisy scalar per matchup. The drafter makes 99 sequential picks and receives
that same scalar. **That is 99:1 credit dilution stacked on an already low-SNR reward.**

```
value of one card swap                      ~ 0.003 win rate
per-block sigma at N = 20 (binomial alone)  = sqrt(0.25/20) = 0.112
per-pick SNR from one deck evaluation       = 0.003 / 0.112 = 0.027
evaluations needed to resolve ONE pick      ~ 1,400, of a state that never recurs
```

On-policy RL over decks cannot see individual picks. It can only see the policy's average, and the
averaging is done by generalisation across `99N` samples. **The binding quantity is N, the number of
independent deck labels, not the number of picks.**

### 5.2 Four mechanisms, in the order they carry weight

**Tier 1: advantage-weighted masked deck modelling.** Self-supervised, zero extra games.

```
L_mask   = - sum over held-out cards   w(deck) * log pi(c_held | prefix_visible, globals)
w(deck)  = clip( exp( (R(deck) - Phi(s_0)) / beta ), 0, w_max )
```

This is AWR, and it is the direct answer to "how does credit reach a pick 100 picks earlier":
**it does not have to travel.** AWR assigns the deck's advantage to all 99 picks uniformly and lets
the critic sharpen it. Estimator variance is controlled by the number of decks, not by the horizon.
It is off-policy, so every deck ever built stays in the replay buffer permanently.

**Be precise about what this multiplies.** Resampling masks turns 10^4 decks into 10^6 gradient
targets, but that is a multiplier on **imitation**, not on information: the directional content is
still bounded by the 10^4 noisy scalars in `w(deck)`. Without the AWR weights the objective is
circular, because the corpus is the bot's own decks. The weights break the circle and the outgroup
alarm in §2.5 is what checks that they did.

**Tier 2: critic-baselined telescoping residuals.** With gamma = 1 and no intermediate reward,
`A_t = Phi(s_{t+1}) - Phi(s_t)`, and these telescope: `sum_t A_t = Phi(s_T) - Phi(s_0)`. So this is a
**decomposition** of the deck's value change, not an authored shaping term, which is what makes it
charter-compliant under `NORTH_STAR.md` §3. Honest caveat: only the last residual
`R - Phi(s_{T-1})` carries new information. The other 98 are the critic's learned interpolation of
that one scalar. **The critic is a generaliser and a variance reducer; it invents nothing.**

**Tier 3: pooling across blocks.** §1.6. This is the mechanism that carries the most weight and it
operates on the critic rather than on the policy: at B = 2,000 a card's coefficient is estimated from
571 blocks, a 23.9x SNR multiplier over any single block.

**Tier 4: per-card play-log observables, as critic auxiliary targets only.** From `E-DEC` + `E-DECK`
+ `E-MANA`, per N = 30 paired block (60 game-seats, ~20 draws and ~30 casts per seat):

| observable | count per block | what it detects |
|---|---|---|
| `P(cast \| drawn)` per card | ~1,200 draw events, ~12 per card | uncastable curve, colour screw |
| `stranded_turns(c)` | same | cards too expensive for the mana base |
| `value_delta_on_cast(c)` | ~1,800 casts | cards that do nothing when they resolve |
| `cast_together(c, c')` | ~1,800 | synergy, **causally** rather than by deck co-occurrence |

That is roughly 12 direct observations per card against 0.01 (one scalar shared across 99 cards).
`cast_together` is the one not to lose: deck co-occurrence learned from your own decks teaches the
model what it already builds, whereas "these two were cast on the same turn and the value estimate
jumped" is a fact about the game.

**These are auxiliary regression targets for `Phi`, never reward terms.** They are biased in a
specific and dangerous direction: `P(cast | drawn)` and `stranded_turns` are both maximised by the
55-land, max-mana-value-3 pile the current generator already produces. Any weight on them in a
*reward* re-creates the pathology from the other direction. As auxiliary targets under a
`DFT-5`-gated deck distribution they are safe, and `TCH-4` is what audits the bias.

---

## 6. Volume

### 6.1 The rate

`docs/DESIGN_TRAINING.md` §4: after the applied fixes the GPU is the limit at 450 to 1,200 games per
hour, i.e. **11k to 29k games per day**, rising to 20k-50k at v0.5 with the four stacked levers. Use
11k-29k as the planning figure. The same section states plainly that this is far below
AlphaZero-class budgets and that every FLOP must count.

### 6.2 The point that makes this affordable

**The block games are not extra games. The student plays them anyway.** Today `config_rl.py:10` sets
`deck_refresh_freq = 1`, so decks change every episode; setting N = 30 changes *when* decks change,
not *how many games are played*. The teacher's marginal cost is:

| marginal cost | size |
|---|---|
| probe evaluations | 0.2% to 0.9% of a block (§3.4) |
| deck construction | ~0.2 to 0.4 s per deck, about 0.05% of a block |
| the opportunity cost of holding a deck fixed for N games | the real one, and it is a curriculum choice rather than an overhead |

### 6.3 Games to a usable critic

| target | blocks B | N | games | days at 11k | days at 29k |
|---|---|---|---|---|---|
| teacher distinguishable from a random teacher | 50 | 30 | 1,500 | 0.14 | 0.05 |
| teacher clearly ahead of random | 100 | 30 | 3,000 | 0.27 | 0.10 |
| per-card coefficients at SNR 3 | 2,000 | 30 | **60,000** | **5.5** | **2.1** |
| pairwise interactions estimable (163 blocks per pair) | 2,000 | 30 | 60,000 | 5.5 | 2.1 |
| triples marginal (47 blocks per triple) | 10,000 | 30 | 300,000 | 27 | 10 |

N = 30 is chosen, not inherited. At B = 2,000 the required per-block SNR is 0.125 (§1.6); the probe
delta measures 0.66 at N = 20 and the win-rate slope measures 0.10, so **N = 20 to 30 clears the bar
with the probe delta and is marginal without it.** Small blocks buy deck *count*, which is what the
critic and the pick policy are starved of, so bias small.

**Below about 50 blocks the teacher is indistinguishable from picking at random.** That is the honest
volume statement for the search process and it should not be read as failure at block 20.

### 6.4 Picks, and why the drafter is cheap

| signal | volume needed | source | extra games |
|---|---|---|---|
| masked deck modelling | 10^4 decks minimum, 10^5 to be good; masks resampled each epoch gives ~10^6 targets | the archive | **zero** |
| critic `Phi`, Bradley-Terry over `(deckA, deckB, result)` | ~10^4 triples for a coarse `Phi` | **one triple per game ever played** | zero |
| pick head against `Phi` (hill-climbing + refinement) | unlimited | `Phi` | **zero** |
| pick head RL finetune, if wanted | ~10^4 independent deck labels | N = 30 blocks | 300,000 games, 10 to 27 days |

At B = 2,000 the archive holds 200,000 base `(prefix, next-card)` targets, effectively unlimited with
order randomisation. **The same 60,000 games that buy a handful of usable REINFORCE gradient steps
buy a fully trained pick head.** That ratio is the argument for distillation, stated as a number.

### 6.5 Expectations to set now

Human-supervised draft bots train on 10^7 picks with strong labels. This project will have about
10^6 picks of much weaker supervision. **Expect "builds a legal, curved, on-colour, coherent deck
that beats a uniform random legal deck 80%+ of the time" long before "picks the right 99th card".**
Ten thousand deck labels is roughly Elo +/- 35 territory for the critic
(`docs/METRICS.md:148-150`): enough to rank archetypes, not enough to rank individual cards. State
that now so the first evaluation is not read as a failure.

### 6.6 The lever that actually matters

2,173 decisions per game is the dominant cost and it is mostly noise: 34.24% are already flagged
forced, 55.0% are `PassPriorityAction`, 37.1% are `ActivateManaAbilityAction`
(`reports/decision_counts_devbox.json`). Auto-resolving forced fields and solving mana taps
(`E-ACT`, `E-SLATE`, `docs/DESIGN_ACTION_SPACE.md`) plausibly takes decisions per game to about 400.
**That is a 5x cut in block cost and it brings B = 10,000 inside a week.**

It also invalidates every per-decision series across the boundary (`docs/METRICS.md` Rail H), so it
must land **before** the teacher's block buffer is accumulated, not after. Sequencing matters here,
and it is why the teacher is staged after the action-space work.

---

## 7. Staging

Cheap first. The first stage plays zero games.

### Stage 0: the constraint filter. No games, no engine, no network. Hours to days.

This is the stage that captures the first 10x (§2.6).

| item | gate | evidence it is needed |
|---|---|---|
| re-ingest `colorIdentity`, `manaValue`, `types`, `subtypes`, `keywords`, `legalities`, `leadershipSkills`, `identifiers.scryfallOracleId`, `edhrecRank`; fix loyalty misfiled into `toughness` | **none.** One offline script; the `(setCode, number)` join back to `M21.json` is 397/397 clean (`E-CARD`) | 43 MTGJSON fields discarded at ingest. `colorIdentity` is **not** recoverable from any stored column: the 45 lands have `mana_cost = ''`. `leadershipSkills.commander` is true on 21 rows and is stored nowhere |
| `deck_cards` join table keyed on oracle id, with a declared commander | none | `E-DECK`: the DB has `cards`, `game_vocabulary`, `users`, `decks` and nowhere to put a list. Without it no deck can be persisted, replayed, or evaluated twice, which kills every estimator in §1 |
| separate the `card_id` / `game_vocabulary.id` namespaces | none | `E-ID`: 60 of 86 vocabulary ids fall inside the 1-397 card range. Any per-card weight built today is scrambled and dies on re-ingest |
| `format_legal` / `engine_supported` flags | none | `DESIGN_CARD_POOL`, "Two independent flags". No query filters on `set_code` today |
| **the legality mask** (§4.4) | needs the rows above | fixes "the commander is a Swamp" at the source |
| **`DFT-5` pre-flight gate** | needs the rows above | microseconds, zero games, fails 300/300 current decks on four criteria simultaneously |
| the §17 register rows `TCH-1..5` and the two contradiction alarms | none | |
| **the interim card vector** (§7 stage 4) | needs the rows above | de-risks the whole drafter against the ability-tree schedule |

**Stage 0 alone deletes the 5-colour, 54.6-land, max-mana-value-3, random-commander regime in which
every strategy metric in `docs/METRICS.md` is currently being measured.**

### Stage 1: the one experiment that decides the design. ~2 GPU-hours. Runnable today.

**Experiment gamma** (§9 Q1). It runs against the current 315 M model and the current broken engine:
the game it measures is not really Magic, but the machinery and the order of magnitude of gamma
transfer. Pre-register the decision rule before running it.

In parallel, and on the critical path for everything downstream: **`E-DEC` per-decision logging must
land in the rebuild's logging contract, not be bolted on afterwards.** The quantities exist and are
discarded three lines later:

| quantity | computed at | destroyed at |
|---|---|---|
| full probability vector | `student.py:131` | `student.py:138` keeps only the scalar `log_prob` |
| pre-bias logits | | `student.py:129` overwrites in place |
| `rethink_prob` | `model.py:255` | not in the tuple `student.py:139` returns |
| wall-clock ms | | no `time.perf_counter` anywhere in `strategic_brain/` |

### Stage 2: an opponent worth measuring against, and blocks. Days.

| item | gate |
|---|---|
| **self-play league + PFSP over a checkpoint archive** (`E-LEAGUE`) | `docs/BACKLOG.md` already calls this "the single highest-value item on this list" |
| `deck_refresh_freq` 1 -> N, seat rotation, `E-SEED` separated streams | `config_rl.py:10`. `main_train.py:94-101` already has the right shape and dies at `:119` on a 1-arg call to a 2-arg method |
| the probe bank as a versioned tensor file of `(obs, menu, action, target)` tuples | `E-DEC`. **Deliberately needs neither `E-SNAP` nor `E-MU`**, which keeps the whole design off the most expensive gate in the project (`DESIGN_TRAINING.md` §5 puts one O2 evaluation at ~20 hours) |
| the permanent uniform-random-legal outgroup population | `TCH-5` |

**The league is a precondition, not a nice-to-have.** The teacher's entire reward is a function of the
student's performance against a deck. With the opponent a `copy.deepcopy` of the student's own
weights from at most 20 games ago (`train.py:50, 88-90`), every matchup is near-mirror, the dynamic
range of every estimator in §1.2 is compressed toward zero, and `ST-8 win rate vs self` is deleted in
`docs/METRICS.md` §17 for exactly that reason. **The teacher's SNR is upper-bounded by the diversity
of the opponent pool, and today that pool has one member.**

### Stage 3: the teacher. Days to weeks.

Archive with staleness-aware priority and a per-cell cap; single-card edit operator; the score of
§2.2; the 7 M critic of §3.3 with a held-out 10% and published out-of-sample R^2. The archive can be
built and unit-tested against a placeholder scoring function before the reward exists, which makes it
parallelisable with stage 2.

### Stage 4: the pick head.

Gate: **a card vector to run a query against.** Two options, and the de-risking one is the point:

- **Real**: `DESIGN_CARD_POOL` steps 1 to 3 (ability tree, transformer over the linearised tree,
  zero-init gated atomic residual). This is what makes synergy generalise to unseen cards.
- **Interim, buildable at stage 0**: `colorIdentity` (32) + log-bucketed mana value + type/subtype
  multi-hot + keyword multi-hot (24 distinct in M21) + P/T + rarity, through a 2-layer MLP to 128d.

The interim vector is a **strict subset** of what the tree encoder will emit, and the interface is
frozen as "one vector per oracle id", so the encoder swaps in later without touching the drafter.
**The drafter is gated on the ability-tree compiler for quality, not for existence.**

### Stage 5: the products, then Limited.

Complete-a-partial-deck and counter-draft fall out of stage 4 with no new training (§4.5). Limited is
last, for the reasons in §8.

### Ordering summary

```
0. card attributes + deck_cards + E-ID + legality mask + DFT-5   no games        <- cheap, first
1. gamma experiment + E-DEC in the logging contract              ~2 GPU-hours
2. league + PFSP + N-game blocks + probe bank + outgroup         days
3. archive + critic + probe-delta score                          days to weeks
4. pick head (interim card vector, then the real one)            weeks
5. products, then Limited                                        later
```

---

## 8. What we are not building, and why

Including the owner's own ideas. Each is parked with the reason, per `docs/BACKLOG.md` rule 1.

| not building | why | what survives |
|---|---|---|
| **Win-rate delta as the teacher's reward**, as specified | SNR 0.19 at N = 100, and 0.21 for the strictly-better slope form. SNR 3 needs roughly 18,000 to 25,000 games per teacher update. No combination of tricks closes a 250x variance gap | **kept permanently as `TCH-4`, the auditor. Never the trainer** |
| **Relative Elo change as the reward** | Elo is a monotone transform of win rate, so it inherits the binomial noise exactly and adds K-factor lag, deflation and anchor drift on top. `docs/METRICS.md:148`: 400 games per pairing gives +/- 35 Elo, and this reward must resolve differences far smaller than 35. It is the same crux in units that hide it | **Elo stays in the league, in matchmaking, and in the report header** |
| **Reward for pushing win rate toward 50%** | row D. SNR 5.92, which looks excellent, and rank rho 0.50: it ranks "even but dull" as the best possible deck. It is a level, not a change, so it cannot separate an instructive even matchup from a boring one and actively prefers the boring one. Textbook `docs/METRICS.md` §17 | **survives as the minimal-criterion filter band in §2.2 step 2**, which is what it was originally wanted for |
| **"Play both sides 100 times" as variance reduction** for the learning delta | 1.00x at equal game budget. `reward_noise.py:78` doubles the budget and the reported gain is exactly sqrt(2) | **kept as a bias-control device** for level comparisons, for the "wins from side A only" broken-deck detector (`ideas.md:171-179`), and in the auditor |
| **Reasoning passes / speed of action as the headline proxy** | `model.py:243-244` halts on a hard `argmax == 9` over a head that receives no gradient, so `passes_taken` is a near-constant integer. `docs/METRICS.md` §17 already deletes `thinking/*_avg_passes` as "measures an untrained argmax hitting class 9". Wall-clock adds scheduling noise from a shared box | **deferred to D11's learned halting head plus `DQ-9` showing non-zero cross-pass churn.** Use value error, value spread and policy entropy instead: computed today and discarded at `student.py:138` |
| **Raw gradient magnitude or TD-error magnitude as a reward** | nuisance payout 0.566. Noise is maximally surprising; this is the noisy-TV failure | **log them. Excellent critic features. Never a reward** |
| **A policy-gradient teacher on a per-block scalar** | 60 to 100 gradient steps per day, each dominated by noise. 0.849 of oracle against a curator's 0.893 and uniform's 0.815 | **replaced by the curator plus critic of §3.1** |
| **A large teacher network up front** | the constraint is deck labels (10^3 to 10^4), not parameters. A linear bandit that generalises across deck space measured **worse than uniform** (0.751 against 0.815), because generalisation amplifies a biased signal instead of averaging it away | **7 M with a published growth rule (§3.3). The tier-A ceiling of 200 M+ remains available and is genuinely free** |
| **A hypernetwork over the student's weights, or a checkpoint-id embedding** | a 300 M read inside the teacher's forward pass; an embedding table over checkpoint ids can only memorise and random-inits on every new checkpoint | **replaced by the 64-float measured-behaviour profile (§3.2)** |
| **MAP-Elites over deck space** | buys +2 behaviour cells in 300 blocks and loses up to 32 points of teaching value. Coverage is not the objective | **a per-cell cap on a flat priority archive instead. MAP-Elites kept as a separate archive for the niche-deck goal in `ideas.md:1-11`, where coverage *is* the objective** |
| **PAIRED, i.e. a trained antagonist** | a third trained agent and roughly 3x rollout cost, and the same authors' successor (Robust PLR) reported that random generation plus curation beats it on zero-shot transfer | **the regret objective is kept, approximated by the student's own positive value loss, which is free** |
| **POET** | a population of paired agent-environments plus O(N^2) transfer evaluation. At ~26 s per game a single 30x30 transfer sweep is 900 games, about 6.5 hours, per sweep | **the minimal criterion is kept (five lines). Everything else dropped** |
| **A penalty for proposing illegal decks** (from the recovered `RL_ARCHITECTURE.md` §5.3) | legality is a rule of Magic, not a strategy heuristic. A penalty wastes samples and creates a hack surface | **replaced by the hard mask (§4.4), which is free and exact** |
| **A bandit over hand-authored archetypes** as a cheap stand-in | this is `deck_generator.py:23-31` with a bigger dictionary: seven archetypes seeded by 21 literal card-name strings, of which `BURN` and `STOMPY` (`:12-13`) are unreachable at `:38`, and whose `LIFE_GAIN` seeds are fetched by name at `:115-120` **bypassing the ban at `:98`**. `NORTH_STAR.md` §3 defaults to no | **not built** |
| **A mana-base solver** | land selection is picks like any other. Hardcoding it would author the single most important deckbuilding skill. Honest caveat: this will be the slowest thing to learn and the temptation will recur | **`MANA-5` source deficit published as a metric, never as a reward or a constraint** |
| **The 8-seat Limited draft training loop, now** | signal reading is only a real skill if the other seven seats are non-random (`DFT-2`'s own note), so the loop needs seven drafter policies, which needs a drafter. And Commander is the format priority (`NORTH_STAR.md` §1a) | **deferred to stage 5.** `DFT-1 colour_commitment_curve` is still the best null-resistant drafting metric available without a human reference corpus, so build the instrument even while the loop waits |
| **Anything gated on `E-MU` or the O2 oracle ladder** | `DESIGN_TRAINING.md` §5 puts one O2 evaluation at about 20 hours at the current 6.0 ms `copy.deepcopy` | **the probe bank is deliberately a saved tensor file, so it needs neither snapshot/restore nor make/unmake** |
| **Repairing the existing `teacher.py`** | three independent dead ends stacked: no `optimizer.step()`; `torch.no_grad()` at `:60` so no graph exists to differentiate; and a reward that is a hard constant +0.1667 for reasons unrelated to either. Fixing any one changes nothing. Also 3 of 7 model outputs are computed and discarded at `:106`, and the network supplies 0.01% to 0.14% of the variance in the weights it nominally controls | **rebuilt, not repaired.** The four `1 - games/10000` ramps, the CMC step function and the life-gain SQL ban are deleted, per `docs/BACKLOG.md` "Scaffolds to remove" |

---

## 9. Open questions

Marked per `NORTH_STAR.md` §6. These are genuinely unresolved and a wrong answer is expensive to
discover late. They are not manufactured to look careful and they are not an excuse to defer work.

### Q1. gamma, the per-game gradient-alignment SNR. `[guess] = 0.15`. Blocking. Measure first.

This is the one number the headline estimator rests on, and it swings row G from 0.48 to 2.89 at
N = 100.

**Experiment.** Freeze theta. Build a probe bank of K = 2,048 `(observation, action, return)` tuples
sampled across the league. Compute `g_P = grad L(theta; P)` once. Play 200 games across at least 20
distinct deck pairs; for each game compute `a_g = cos(grad L(theta; traj_g), g_P)`. Then

```
gamma = sd_over_deckpairs( mean_g a_g ) / sd_over_games_within_deckpair( a_g )
```

Cost: 200 games plus 200 backward passes, about 2 GPU-hours. **Pre-registered decision rule:**

| gamma | consequence |
|---|---|
| >= 0.15 | probe delta reaches SNR ~2.9 at 400 games per block. Build the full design |
| 0.05 to 0.15 | probe delta needs 400 to 4,000 games per block. Build it, lean on pooling, accept a per-block SNR near 0.5 |
| < 0.05 | the probe delta is not materially better than the win-rate slope. **Fall back to row B plus pooling, put every hour into the critic and the buffer, and say so out loud rather than shipping the probe machinery anyway** |

### Q2. Does the competence proxy actually track learning? Not blocking, but the biggest silent risk.

The escape hatch assumes value error, entropy and value spread fall as the student masters a matchup.
That is plausible, it is what `RL_ARCHITECTURE.md` §5.1 assumed eleven months ago, and it is
**untested**. Worse, it is partly circular: `passes_taken` comes from a halting head that
`docs/METRICS.md` `DQ-9` shows has provably zero cross-pass churn today, and `DQ-10
allocation_efficiency` is approximately zero by construction. A teacher trained on a proxy emitted by
an untrained head is optimising a random function very precisely, which is the failure the current
teacher already has, rebuilt at higher resolution.

**Hard gate, not a nice-to-have.** On the first real run, log per-decision proxies alongside per-block
win rate and publish `Spearman(proxy_slope, winrate_delta)` over the archive. **Below about 0.4 the
per-decision half of this design is invalid**, and the honest fallback is a curator ranked on the
win-rate slope at 400-game blocks: SNR 0.44, slow but real.

### Q3. Intra-game ICC and AR(1) rho for each candidate proxy. `[guess] ICC = 0.05, rho = 0.9`.

Costs zero extra games. From `E-DEC` logs, fit a one-way random-effects model of each proxy on game
id; report ICC and lag-1 autocorrelation per proxy, clustered per `docs/METRICS.md` Rail D. If the
design effect exceeds 50, row E is worth at most 20 equivalent decisions per game and is formally
demoted below row G in the register. If it is under 10, row E is much better than 0.35 and the
fallback in Q1 is stronger than stated.

### Q4. Does the pooling orthogonality assumption survive a working teacher?

The 23.9x multiplier at B = 2,000 assumes near-independent decks. A working teacher destroys that
assumption exactly where it is working. **Falsifier:** publish the condition number of the card design
matrix over the buffer, and out-of-sample R^2 on held-out blocks, in every review. A rising condition
number with a falling held-out R^2 means the multiplier is fictional and either B must grow or the
per-cell cap must tighten. **I could not resolve analytically how fast this degrades**, because it
depends on the teacher's own behaviour, which does not exist yet.

### Q5. Does the frozen global probe bank bias the teacher toward probe-typical board states?

The reward is a drop in loss on a fixed set. It structurally cannot pay for teaching the student about
situations that are rare in `P`, and it exerts a mild pull toward the modal deck. Refreshing `P` on a
slow schedule with an overlap window for rescaling is the intended mitigation, and every row must be
stamped `environment_contract_epoch` per `docs/METRICS.md` Rail H, but **the size of the bias is
unknown**. Candidate check: hold out a second probe bank stratified toward rare board states and
publish the two deltas side by side.

### Q6. N, the block size, and whether it should adapt.

N = 30 is argued from §1.6 and §6.3, not measured. A learned or bandit-selected N (spend more games on
decks whose predicted variance is high, using the critic's log-variance head) is the
`NORTH_STAR.md` §3-compliant version and is strictly better than a constant, but it adds a second
adaptive loop on top of one that is not yet validated. **Ship constant N = 30 first, with the
log-variance head trained but not yet used for allocation.**

### Q7. Where does the Limited pick head's supervision come from?

`DFT-4 pick_prauc_vs_reference` needs an external corpus, and `docs/METRICS.md` §18.1 is explicit that
no public per-decision Commander corpus exists. 17lands covers Limited only. Either acquire a Limited
reference and accept that it does not transfer to Commander construction, or drop the ask and satisfy
the drafting metrics from `DFT-1` (slope-based, null-resistant, needs no reference) and `DFT-5`.
**Not resolved. Do not compute an AUC against a self-generated label; that is theatre.**

---

## 10. The two sentences that matter most

**Most important:** pair on identical states, and pool across blocks. Pairing on a frozen global probe
removes state-sampling variance by construction rather than in expectation, which is what defeats the
126.7x design effect that quietly destroys the naive per-decision proxy. Pooling across a buffer
removes the requirement that any single block be informative at all, which dissolves the crux rather
than fighting it. Everything else in this document is bookkeeping around those two ideas.

**Biggest risk:** the first 10x of teacher value is a legality filter and not a learned agent (§2.6),
and the whole design is one unmeasured number (§9 Q1) away from degrading to the win-rate slope.
Build stage 0, run the gamma experiment, and let those two results decide how much teacher gets built
at all.
