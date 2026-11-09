# The learning plan: Student, opponent simulator, memory and Teacher

Owner-approved 2026-11-06 (plan v3, after a red team and the owner's rulings; the critique is
KNOWLEDGE/2026-11-06/185-learning-plan-redteam.md). The decisions it rests on: DECISIONS D6, D15, D20.

2026-11-06. This plan supersedes PLAN_v2.md. It applies:
- the owner's rulings on v2's questions, including his clarification of ruling 3 (§0);
- the red team's review (REDTEAM.md, measurements in `plan_v1/rt_work/`);
- DECISIONS D20.

It is bound by OWNER_PREFERENCES #1 (no hidden information in play), #2 (lean code) and #6 (full
credit). The exact amended texts of D6 and D20 are in the appendix, and the change log is §15. [n]
refers to the reference list.

---

## Summary for the owner (one page)

**What we build.** The learning signal is one comparison:
1. At a decision where the Student is unsure, fork the game and try 2-4 alternative moves.
2. Each alternative is played to the end of the game, with the Student on both seats, every seat
   reading only its own masked view.
3. **In training**, the alternatives share the *real* future: the true hidden cards and library
   orders. That is common random numbers on the true future, under five guards (§1.2):
   - no network ever reads that future;
   - the target stays nearly linear;
   - nothing carries over between rollouts;
   - labels come only from fresh deals;
   - a leak test runs.
4. The policy is nudged toward the moves that did better, by a small, unrescaled mirror-descent
   step.

**At play time**, search uses beliefs: futures sampled from the **opponent simulator**, a network
trained only by supervision on finished games. Rare devastating hands are importance-sampled, so
they are seen but count only by their probability.

**Moves, not cards, are compared.** If threats sit at 45%, 30% and 25% and one counterplay answers
the last two, that counterplay is right 55% of the time and it wins. In search this happens
directly; in training it happens across many labels (§1.4).

**Supporting pieces.** The policy also reads the simulator's whole belief as tokens, and the value
head learns from final results.

**What the owner's clarification buys.** Training labels need no belief model, so the futures can
no longer be crippled (B1) and the labels carry no belief error.

**The honest expectation.** The correlation of shared futures was measured at 0.94-0.96 with greedy
playouts and 0.58-0.72 with sampled ones. On those numbers, labels give:
- about 1.7-4.5x outcome PPO's gradient signal per forward pass with greedy playouts;
- 0.3-0.6x with sampled ones.

**E1 can kill the label path.** The fallback is slow outcome PPO plus throughput work.

| Step | Builds | Its gate decides (powered; §12) | Machine time | Code |
|---|---|---|---|---|
| E1 | true-future labels, greedy and sampled | **Labels pay:** a signal = noise step costs at most half of PPO's lambda-1 bound, and the placebo is silent. Otherwise, slow PPO plus throughput | ~5 h | ~170 |
| E3 | distillation from 10k, 30k and 100k labels | The apprentice learns: regret at most 0.8x the generator's, and a gain of at least +0.015 over 450 pairs of unseen deals. Otherwise search runs at play time only | ~5 h | scratch |
| E0 (in parallel) | the opponent simulator | It beats the hand-built yardstick: NLL at least 5% lower by mid-game, calibration error under 0.05. Otherwise it trains longer | ~5 h | ~300, plus a 45-line yardstick |
| Phase 1 | labeller and trainer, then inputs one at a time | It learns to beat a fixed opponent: at least +0.025, paired, on held-out deals; raw Student at least +0.035 against its start; leak tests green | 1-2 weeks | ~+1,000, then -200 |
| Phase 2 | league, exploiter, niche set, Teacher v0, play-time search (E2) | At least +0.035 against Phase 1's final; held-out and niche decks no worse; exploiter flat | 2-3 weeks | ~+300-450 |
| Phase 3 | Teacher v1 (curator plus critic) | At least 1.3x the Elo per day of uniform deals, 3 seeds per arm | 1-2 weeks | ~+200 |
| Phase 4 | drafter | D16's knob tests and R8's blinded human panel | open | ~+250 |

**Cost of Phase 0:** about 15 machine-hours and a day and a half of code, so roughly three days.
Two-player only; Commander later.

**Still open for you (§14):**
- greedy playouts, if only they pay;
- the target setting;
- three small rulings.

---

## 0. The owner's rulings (2026-11-06) and what the plan does with them

1. **Memory (D6).** Start with the per-turn public table, adding the event window if the simulator's
   gate earns it. Learned memory stays an open line of work: a fork-compatible form is to be found
   and trained (§7; appendix A).
2. **Guard 3.** The Student plays both seats inside playouts. What that gives up, and how the
   league, simulator and exploiter compensate, is in §5.
3. **Hidden information, as clarified.**
   - There will never be a privileged critic, meaning a network that learns from hidden
     information.
   - Training labels may compare alternatives on the real game's hidden state, cards and library
     orders, under guards (a)-(e) in §1.2: "reduce luck, increase signal ... as long as this info
     doesn't leak between rollouts ... we don't want it memorizing what the opponent has".
   - Play-time search uses beliefs.
   - If E1 or E3 kills the label path, the fallback is slow outcome PPO plus throughput work.
4. **Two-player only for now; Commander later.** §10 keeps the plug-in points.
5. **Nothing hand-built about opponents.**
   - The simulator is trained by supervision on finished games.
   - The deck-consistent sampler is only a yardstick the simulator must beat (§8).
   - Today's evaluation-only search keeps its uniform sampler until the simulator replaces it.
6. **The simulator's design** (§8):
   - calibrated joint probabilities of whole hands and of the unknown library contents;
   - importance-sampled futures;
   - the whole belief, read by the policy as detached tokens, while the simulator keeps its
     supervised loss.
7. **Accumulation over shared responses.** Moves are compared across all hands, never against one
   hypothesis (§1.4).

## 1. The label and the search

### 1.1 Shared machinery

**Alternatives.** k = 2 by default, chosen by Gumbel-top-k without replacement from the policy. For
attack and block plans, a plan's log-probability is the sum of its per-ask log-probabilities, and
the target is distilled per ask (m1).

**Playouts.** Every alternative is played to the end of the game, gamma = lambda = 1, with no value
leaf. The Student plays both seats (§5), and each seat reads only its own masked view of the fork.
E1 measures two modes:
- **Greedy:** lower noise. It improves the greedy policy that the gates and deployment use: rollout
  policy iteration [30, 31]. Tesauro and Galperin played the same base policy for both sides to the
  end of backgammon games and cut its error rate by up to 5x.
- **Sampled,** with random numbers shared across alternatives. This keeps the update-equivalence
  argument [28].

A crashed future is dropped for every alternative (m2).

**Target.**
- Q̂(a) is the (weighted) mean result over the futures, in outcome units (±1), with no rescaling.
- For the alternatives in S: π'(a) = π(S)·u(a) / Σ_{b∈S} u(b), where
  u(a) = [π(a)·exp(η·Q̂(a))·ρ(a)^{ηα}]^{1/(1+ηα)}. This is the MMD step of [28], with ρ a uniform
  magnet.
- Moves outside S keep their probability. No value-head completion is used, so there is no
  bootstrap (B2).
- η is set so that a one-SE error moves the log-odds by at most 0.5, which keeps the step nearly
  linear in Q̂.
- **Placebo:** permute Q̂ among each label's alternatives and rerun the gradient test. A sound
  target shows no signal (z < 2).

### 1.2 Training labels: the true future, under guards (ruling 3)

**Futures.** d = 2 by default:
- future 1 is the real future: the true hands and the true library orders;
- future 2 keeps the true cards and every known position, and reshuffles the unknown parts of both
  libraries;
- each future has its own engine seed, shared by all alternatives.

Both futures are unbiased. Given what anyone can know, the unknown library order is uniformly
random, and the real game is itself a draw from the hidden states consistent with the player's
view.

**The guards:**
- **(a) No network ever reads the true future.** Both seats play every playout from their own
  masked view. The searcher's seat sees what it would see in the real game. The opponent's seat
  sees its own true hand, as the real opponent does. The label is the only product.
- **(b) The target is nearly linear in the playout results** (§1.1). So each label is an unbiased
  sample of the decision's value under the player's information, exactly as the real result is in
  outcome RL. The policy, which never sees the hidden state, learns the expected target given its
  view.
- **(c) Nothing carries over** between rollouts or decisions. Every fork is discarded after its
  playout, and only the scalar results return. Caches hold static card properties only, never game
  state or hidden identities.
- **(d) No memorisation of what an opponent holds.**
  - True-future labels are generated only on fresh natural deals: new decks and new shuffles.
  - Anything that deliberately reuses a deck gets belief-sampled labels (§1.3) or no labels: matchup
    blocks, prioritised replays, specialists' fixed decks and Teacher pools.
  - Generalisation is always measured on unseen deals.
- **(e) Leak tests.** The policy's outputs, and its belief tokens, must be byte-identical when any of
  these is rewritten:
  - the opponent's hidden cards;
  - which of its hand cards entered when;
  - its private knowledge;
  - our own unknown library order.

  Labelling a position must leave the real game's state digest unchanged, and the policy's next
  decision must be byte-identical with and without labelling having run.

What this gives over belief futures: no belief error, no crippled futures (B1 no longer touches
training), no non-locality in labels, and no belief model on the critical path. Per forward pass
the efficiency is the same to first order: d cancels (§2).

### 1.3 Belief futures: play-time search, and labels on reused decks

Play-time search, and labels on deals that reuse decks, take their futures from the simulator (§8):
1. Draw M = 32 candidate worlds: the opponent's whole hand jointly, then its unknown library
   contents. Known cards stay fixed, and the opponent's whole private state is resampled (B3, §3).
2. Score each candidate's consequence, c_i = ε + max(0, V_opp(i) - V̄_opp). V_opp(i) is the value
   head read from the opponent's own view in world i, which is not privileged: it is what the
   opponent itself would see.
3. Pick d futures with probability proportional to c_i, and weight each by w_i = Σ_j c_j/(M·c_i).
   The weighted mean is unbiased for the simulator's expected result: rare devastating hands are
   seen more often but count by their probability.

At play time the budget is k = 2, d = 2, greedy (§10).

### 1.4 Moves are compared across all hands; shared answers accumulate (ruling 7)

**The owner's example.** The opponent holds threat A (45%), B (30%) or C (25%). Response R1 beats A,
and response R2 beats both B and C.

**In play-time search.** Q̂(a) is one number per move, a weighted average over every sampled world.
R2 wins 55% of the weight and R1 45%, so R2 is chosen, although A is the single likeliest threat.
Importance sampling over-samples dangerous worlds but reweights them back. Nothing collapses to a
most-likely or most-dangerous hand, and no per-world optimisation happens (guard 2: strategy
fusion).

**In training, accumulation happens across labels.**
- Each true-future label credits whichever move worked in that world.
- Over the many positions the policy cannot tell apart, R2 is credited in 55% of them and R1 in 45%.
- Because the target is linear (guard b), the expected update moves the policy toward the move
  with the higher *average*, so it converges on R2.
- A hard label (argmax per label) would instead teach a 55/45 mixture of R2 and R1. That is why
  guard (b) is a guard.

**In what the policy reads.** It sees all candidate cards with their weights (§8), never an argmax
hand. So it can represent "B and C together outweigh A", summing the mass of threats that its card
embeddings mark as sharing an answer.

**Regression tests:**
- the search, on the owner's example as a scenario with an injected 45/30/25 belief: it must choose
  R2, and still choose R2 when importance sampling over-samples A;
- the target, on a synthetic view with hidden worlds at 45/30/25: distillation from per-world labels
  converges to R2 with the linear target, and to the 55/45 mixture with hard labels.

**What cancels.** The measured correlation of shared futures is 0.94-0.96 with greedy playouts,
0.58-0.72 with sampled playouts and shared seeds, and 0.40-0.45 without shared seeds. Luck cancels in
the comparison to that degree. It stays in the problem, because the policy learns the expectation
over what it cannot see.

## 2. Signal per compute, honestly (M1)

Compare one label with one PPO sample at a two-option decision (p = 0.8), at the same expected
gradient. The label's noise is p(1-p)·Var(zA - zB) / (d·Var(z - V)) of a PPO sample's. The table
assumes:
- Var(z - V) = 0.7 mid-game;
- a label costs k·d·47 forward passes, 47 being the measured mean playout length;
- PPO spends ~5 forward passes per signal-carrying decision.

The true-card futures the red team measured ("true ids") had per-future variances like the deck
prior's: 0.070 against 0.080 in greedy play.

| Playouts | corr | Var(zA - zB) per future | One label ≈ PPO samples | Signal per forward pass vs PPO (k = 2 / k = 4) |
|---|---|---|---|---|
| greedy | 0.94-0.96 | 0.03-0.08 (use 0.07) | 62·d | **3.3x / 1.7x** |
| sampled, shared seeds | 0.58-0.72 | 0.22-0.51 (use 0.4) | 11·d | 0.6x / 0.3x |
| sampled, unshared | 0.40-0.45 | 0.37-0.79 | 7·d | 0.4x / 0.2x |

What follows from the table:
- **d cancels.** Noise falls as 1/d and cost rises as d, so small d gives the most positions per
  unit of compute.
- **k = 2 suffices** at two-option decisions.
- **Early decisions** lift the greedy row to ~4.5x.
- **E1 compares on one instrument.** The linearised label gradient and PPO's gradient go through the
  same split-gradient instrument, normalised per forward pass.
- **The B* rule ("at least B* decisions per optimizer step")** applies only to the outcome
  policy-gradient loss [13].

## 3. No private-state leak (B3)

These rules matter wherever a network plays a playout:
1. **Public hand information only, for both seats.** No per-card ages are encoded. In a belief fork,
   the opponent's exact ages would be the true ones.
2. **Handles, not identities.** The ledger and the library bag store handles and read zones, never
   identities captured at an event and never a deck list.
3. **Full private-state resampling in belief futures.** `determinize` resamples the opponent's whole
   private state: hand identities, which hand card entered when, its library, and its scry and tutor
   knowledge.
4. **The leak tests of guard (e)**, plus, for play-time search: with a fixed search seed, the
   searched move is byte-invariant to the opponent's private state.

## 4. Training (M6, m9)

| Network | Loss | Data |
|---|---|---|
| Student policy | KL(π' ‖ π_θ) | labels |
| Student value head | (V - z)² | ~10 sampled positions per game and seat |
| Simulator | its own supervised NLL only | finished games: natural deals, both seats' views |

The Student reads the simulator's outputs with the gradient stopped, so wins teach the policy how
much to trust the belief and never move the simulator's probabilities. Per-head gradient norms are
logged.

**Cadence.**
- Ordinary minibatches over a label window measured in labels (200k by default).
- The minibatch size comes from E1's measured B*_distill, with McCandlish's learning-rate scaling.
- Weights are published every ~10 min, and each label logs its weights' age.
- The simulator retrains on a sliding window of recent games.

**Outcome PPO** is the fallback if E1 or E3 fails. Its policy-gradient code is deleted once E3
passes.

## 5. Exploration, cycling, and guard 3's price (ruling 2)

**Inside playouts the Student plays both seats.** Update-equivalence search requires it [28], and
Ataraxos does it [26].

**What this gives up:**
- **No adaptation to a specific opponent inside the search.** Playouts assume the opponent plays
  like the Student. The search will not exploit a known opponent's habits, such as one who never
  blocks, and will not guard against that opponent's particular strengths beyond what the Student
  itself would do.
- **Continuation quality is the policy's own.** If the Student misplays a later line, playouts
  undervalue the moves that lead into it. Each label improves the policy relative to its own
  continuation, one step at a time.

**How the rest compensates:**
- **The league** chooses the real games' opponents: prioritised fictitious self-play (PFSP) [5],
  weighted (1-x)^p, over frozen versions, the heuristic and niche specialists. Labelled positions
  therefore come from play against diverse opponents.
- **The simulator** is trained on those games, so the belief tokens and play-time futures carry
  their habits.
- **The value head** learns from real results against them.
- **The exploiter** (AlphaStar's main exploiter [5]) is reset periodically and trained against the
  Student. It finds lines the self-model misses, and its score after a fixed budget measures
  exploitability.
- **The magnet** (MMD [4]) damps cycling.
- **Policy iteration** narrows the continuation gap as the Student improves.

**Exploration** comes from Gumbel alternatives, a 10% sample of confident decisions,
temperature-1 real games, and the specialists. There is no PSRO population; tuned PPO and MMD
match or beat it [27].

## 6. What is borrowed, what is new

**Borrowed:**
- base-policy rollouts to the end of the game [30, 31];
- the mirror-descent step on rollouts under the joint policy [28];
- the magnet [4, 26];
- expert iteration's distillation loop [10, 11];
- determinisation in MTG [15];
- learned beliefs that sample hidden cards for search [9];
- finite-pool importance sampling.

**Corrected from v1:**
- Ataraxos trains with λ-returns and searches only at test time, with value-scored rollouts.
- LBS's savings come partly from bootstrapped rollouts.
- Bursztein's prediction relied on meta decks [23].
- Dota 5v5's noise scale is at least 10M [13].
- AlphaZero bounds staleness with a window of recent games.
- A 60-card list allows ~10^5-10^6 different 7-card hands.

**New at this scale in the cited work:**
- distilling a mirror-descent step computed from full playouts (λ = 1, no value leaf);
- in training, run on the true future with a linear target, so each label is unbiased given the
  player's information.

E1 and E3 test this.

## 7. Inputs and memory (owner §3-4; ruling 1)

Inputs are added one at a time in Phase 1 stage 2. Each gets a paired ablation and is kept unless
it harms (one-sided 95% bound below -0.01):
1. **Belief tokens** from the simulator (§8), once E0 has passed.
2. **The per-turn public table** for both seats: the last 16 turns, plus one folded row for
   everything earlier. It holds lands played, spells cast, mana spent and left untapped, attacks and
   blocks declined, cards entering and leaving the hand, and hand size. The owner's hand-age bounds
   ("at least k cards held since turn t") are a linear function of it.
3. **Our own library** as a bag token read from the zone, plus the **ledger** of known positions,
   erased by a shuffle (CR 701.24a).
4. **The event window:** 64 public events, encoded at d256 and pooled into 4 tokens. It goes to the
   simulator only, if E0 shows it helps.

**Learned memory is an open line of work** (ruling 1; appendix A). Candidate fork-compatible forms,
cheapest first:
- (a) a recurrent state over public events only, identical in the real game and in every fork;
- (b) a private memory sampled by the simulator jointly with the opponent's hand;
- (c) a state recomputed in each fork from the public history and the fork's private history (the
  true one in training futures, the resampled one in belief futures).

Each must pass the leak tests and beat the stateless baseline in a paired ablation; D6's BPTT
question then applies unchanged. Form (a) is first, after Phase 1 stage 2.

## 8. The opponent simulator (owner §5; rulings 5-6)

**What it is for:**
- futures for play-time search, and for labels on reused decks;
- the belief tokens the policy reads.

It is no longer on the critical path to E1 and E3. Its own gate (E0) stays.

**What it is.**
- A separate small transformer (~4M parameters, d256, 4 layers).
- It reads the searching seat's own view: public zones, the per-turn table, the ledger's known cards
  and its own hand, plus the event window if E0 earns it.
- It is trained by supervised NLL only, on finished games. The labels are the opponent's true hand
  and unknown library contents at sampled positions, from both seats.
- It learns land ratios, colours and habits from data. Format deck-building rules, such as the copy
  limit, mask impossible cards: they are rules, not habits.

**What it outputs:**
- **Whole hands, jointly.** An autoregressive decoder over the hand as a sorted multiset, h steps
  (h is public).
  - Each step emits a vector in card-embedding space (name plus components), scored by dot product
    against every candidate card. This is the owner's "vector matched to real cards".
  - The product of the steps is the probability of the whole hand, so combinations are
    represented. Maximum likelihood is a proper scoring rule, so it trains for calibration.
- **Library contents.** A second decoder over (card, count) pairs, conditioned on the hand. The order
  is not modelled: the next draws are random draws from the sampled contents.
- **Marginals.** A cheap head gives P(card in hand) and the expected library count per card. It is
  checked against the decoder's sampled frequencies.

**How the policy reads it (ruling 6).**
- **Tokens.** One belief token per candidate card: the card's embedding from the Student's own
  table, plus a projection of [P(in hand), expected library share]. There are 24 such tokens, for
  the likeliest cards, and one "rest" token.
- **Pooling.** One cross-attention layer pools them into 4 trunk tokens.
- **Detached probabilities.** The policy learns from its own losses how much weight each belief
  deserves, and the simulator stays calibrated by its supervised loss alone.
- **One network, two readers.** The search uses the joint model and the policy reads the marginals,
  both from one calibrated network.

**The yardstick (ruling 5).** The deck-consistent sampler (`resample_coherent`, 45 lines) lives only
in the evaluation harness, as a registered measurement scaffold. It is deleted once the simulator
beats it and the result is recorded in NUMBERS.md.

## 9. Deals, curriculum, niche decks (D14, D15, D16)

**Deal spec.** (set, pool, deck_a, deck_b, shuffle_seed). `_setup_game` already accepts explicit
decks (`games.py:1212`).

**v0.**
- Pairs are measurement.
- **Blocks are measurement only** (guard d): the learning test trains on fresh deals and measures on
  held-out ones.
- Prioritised matchups (learnability p(1-p) [20] plus search gain [19]; fresh shuffles; at most 50%
  of deals) use belief-sampled labels.
- At least 50% of deals are natural (DAGS [29]). True-future labels and the simulator's training
  use natural deals only.
- Deck curation only; opening-hand lessons return in v1 with a curated flag.

**The niche path (D14).** Generator knobs make a fixed, held-out niche set: mono-colour,
three-colour, land-light, land-heavy, all-creature and high-curve.
- It is scored at every gate from E1 on.
- It seeds the Phase 2 specialists.
- The specialists' fixed decks get belief labels (guard d).
- Niche decks also appear among the natural deals, so the simulator and the true-future labels see
  them fresh.

**v1.** The curator plus matchup critic of D15. The opponent is chosen jointly with the decks [21],
and the handicap is set so the predicted score is near 0.5.

**v2.** ACCEL-style edits [22], and the drafter trained against the critic, with D16's two knobs
and R8's blinded human panel (DFT-17, Spearman at least 0.5).

## 10. Throughput, latency, and Commander later (M5; ruling 4)

**Serving.**
- The GPU sustains 8.5-10.5k decisions/s; the serving loop delivers ~1,700/s; the CPU ceiling is
  ~3,400/s.
- Serving work in Phase 1 roughly doubles both labels and games.
- A label at k = 2, d = 2 is ~190 forward passes (0.11 machine-seconds), about 470k a day at a 60%
  share.

**Play time.**
- The deployed model is the distilled network, at ~5 ms per decision.
- Search (k = 2, d = 2, greedy, simulator futures) takes ~1.2-1.6 s per searched decision,
  sequentially, within NORTH_STAR §1a's 4.2 s. Tail playouts are cut at the budget, and that future
  is dropped for all alternatives.
- E2 decides whether search ships (§12). A parallel playout executor (~150 lines) is built only if
  search needs more than this budget.

**Commander, later (ruling 4).** It plugs in at five places:
- the deal spec: 100-card singleton, a public commander, 4 seats;
- the simulator: singleton decks, learned from data;
- playouts: the Student on every seat;
- beliefs: one per opponent;
- cost: playouts about 10x longer.

## 11. Amendments to settled decisions

- **D6 and D20:** the appendix.
- **D14:** the niche path (§9).
- **D15 and D16:** consistent. ACCEL edits are proposals, the matchup critic is the shared critic,
  and Phase 4 adds R8's panel.

## 12. Roadmap with powered gates

**The statistics.**
- A pair mean has σ = 0.194.
- Separating e0 from e1 at α = β = 0.05 takes n = (3.29σ/(e1 - e0))² pairs, deciding at
  c = (e0 + e1)/2.
- 450 pairs separate +0.02 from +0.05, and 0 from +0.03.
- Every gate is decisive.

**E1, label signal (~5 h).**
- Run true-future labels on fresh natural deals from r20 v2 self-play, in three configurations:
  (k 2, d 2) greedy, (k 2, d 2) sampled and (k 4, d 2) greedy.
- The split-gradient instrument runs on at least 4 B* worth of labels, plus the placebo and the
  per-future variances.
- **Gate:** B*_label is at most 2.65M forward passes (at least 2x PPO's lambda-1 bound of 5.3M),
  and the placebo's z < 2. One pre-registered extension is allowed.
- **Kill:** slow outcome PPO plus throughput work (ruling 3).

**E3, distillation (~5 h).**
- Distil from 10k, 30k and 100k labels.
- Score regret against independent re-labelling of 2,000 held-out positions, using fresh true-future
  playouts.
- **Gate:** the 100k model's regret is at most 0.8x the generator's (paired 95% bound), and it
  gains at least +0.015 over 450 pairs on **unseen deals**.
- **Kill:** search at play time only, and PPO as the learner.

**E0, the simulator (~5 h, in parallel).**
- Capture 1-2M labelled positions, then train offline.
- **Gate:** hand NLL on 50k held-out positions is at most the yardstick's, and at least 5% lower by
  mid-game. Per-card calibration error is below 0.05. The event window is kept if it adds at least
  5%.
- **On failure:** train on 4M positions. The yardstick is never used outside measurement.

**Phase 1.**
- **Stage 1:** the labeller on fresh natural deals, the trainer, serving work, and the mulligan fork
  boundary (m6).
  - **The learning test:** train against a fixed frozen version on fresh deals, then score against
    it on the same 300 held-out deals before and after (paired, SE ≈ 0.009). Pass at +0.025 or
    more.
  - **Also required:**
    - held-out matchups and the niche set are no worse;
    - the raw Student scores at least +0.035 against its start, over 450 unseen pairs;
    - the leak tests and both regression tests (§1.4) pass;
    - fewer than 1% of playouts end on the rail.
  - **Kill:** below +0.02 after 500k labels.
- **Stage 2:** the §7 inputs, one at a time.

**Phase 2.**
- **E2, play-time search:** search on simulator futures against the raw network, over 450 pairs.
  It ships at +0.035 or more.
- **Gate:** at least +0.035 against Phase 1's final; held-out and niche decks no worse.
- **Exploitability** is flagged if a fresh 24-hour exploiter's score rises by at least +0.025.
- **Cycles** count only triads whose edges are all significant.
- **Kill:** below +0.02 in 7 days.

**Phase 3.**
- At least 3 seeds per arm, each endpoint over 1,000 pairs.
- **Gate:** a gain ratio of at least 1.3, with a one-sided bound above 0.
- **Kill:** a ratio of 1.0 or less.

**Phase 4.**
- **Gate:** drafted decks score at least 0.60 against random coherent decks.
- **Gate:** counter-drafts score at least 0.60 against the named deck.
- **Gate:** D16's knob tests and DFT-17 pass.

## 13. Code footprint and scaffolds

| Phase | Files and rough lines | Removed |
|---|---|---|
| E1 | `search.py`: true-future labeller (fork; reshuffle of unknown library parts with known positions kept; shared seeds) ~50, MMD target and placebo hook ~20, CRN-safe crash handling ~5; leak tests and both regression tests ~100 | - |
| E0 | `simulator.py` (network, decoders, marginal head, training) ~250; position capture in `actor.py` ~40; yardstick in the evaluation harness ~45 (scaffold) | - |
| Phase 1 | labeller jobs and label window ~150; distillation loss ~50; plan targets ~70; mulligan boundary ~30; serving ~120; belief tokens ~60; `knowledge.py` table and ledger ~210; library bag ~25; event window if earned ~80; tests ~200 | PPO's policy-gradient path after E3 (~-200) |
| Phase 2 | belief futures with importance sampling and private-state resampling ~90; deal spec ~40; niche knobs ~60; PFSP, exploiter, blocks and priorities ~180/-80; report ~30; parallel executor only if needed ~150 | uniform `determinize`; fixed opponent shares; teacher-stage flags |
| 3 / 4 | `teacher.py` ~200 / `drafter.py` ~250 | - |

That is about +1,600-1,800 lines net through Phase 2.

**Scaffolds** go into BACKLOG with removal conditions:
- the yardstick;
- at most 4 labels per game;
- the 0.95 threshold and the 10% confident share;
- k, d, η, α, β, ε and M;
- the 200k label window;
- the 50% replay cap and the 50% natural share;
- the play-time budget.

## 14. Still open for the owner

1. **Greedy playouts.** If only greedy playouts pay, will you accept rollout policy iteration of the
   greedy policy we deploy? The mirror-descent claim would then hold for the sampled mode only.
2. **Target setting.** Are deck lists known (open deck lists)? Will the opponents be humans or bots?
3. **Small rulings:**
   - paper-exact public hand counts (chosen);
   - Teacher handicaps beyond deck and seed choice;
   - a risk term, or plain win probability (the default).

## 15. Change log

**2026-11-09, after Phase 0** (DECISIONS D21): E0 and E1 pass, E3 fails. The owner chose E3's kill
path: outcome PPO learns (lambda = 1, updates at least B*), search plays (Phase 2's E2 is next);
Phase 1 does not run; the distillation is parked (BACKLOG).

Red-team issues (v2), as amended in v3:

| Issue | Verdict | Change |
|---|---|---|
| B1: the public sampler cripples the opponent | accepted | **v3:** training labels use the true future, so B1 no longer touches training. Play-time and reused-deck futures come from the learned simulator, with the deck-consistent sampler as a yardstick only |
| B2: the rescaled target amplifies noise | accepted | Unrescaled MMD step, η from the standard error, no completion, placebo (§1.1) |
| B3: private-state leak | accepted | Public hand counts; handles; full resampling in belief futures; leak tests on policy outputs and on labelling (§1.2e, §3) |
| M1: efficiency without arithmetic | accepted | The 0.3-4.5x table; E1 measured per forward pass, with the placebo (§2) |
| M1: an 8-configuration sweep | partly rejected | d cancels to first order, so E1 runs 3 configurations (§12) |
| M2: luck cancels only in greedy playouts | accepted | Both modes measured; greedy grounded in rollout policy iteration [30, 31] |
| M3: mixture rollouts, citation errors | accepted | The Student plays both seats; citations corrected (§5, §6) |
| M4: underpowered gates | accepted | Powered two-point gates; **v3:** generalisation on unseen deals (§12) |
| M5: serving, latency, Commander | accepted | Serving work; budgeted play-time search (E2); Commander later (§10) |
| M6: training cadence | accepted | Label window counted in labels; the B* rule for the policy gradient only (§4) |
| M7: belief structure | accepted | **v3:** a learned joint simulator, gated against the yardstick, used for play time and belief tokens (§8) |
| M8: duplication, staging, footprint | accepted | One per-turn table; staged Phase 1; PPO deleted after E3 (§7, §13) |
| M9: D6, D14, D15/D16, D20 | accepted | Appendix; niche path; human panel |
| m1-m9 | accepted | As in v2 |
| m10: true-card futures with a linear target | **accepted** (ruling 3 as clarified) | Training labels use the true future under guards (a)-(e); play-time search uses beliefs (§1.2) |

The owner's rulings (v3):

| Ruling | Change |
|---|---|
| 1 Memory | Stateless start; learned memory an open line of work, with three fork-compatible candidates (§7, appendix A) |
| 2 Guard 3 | What self-play playouts give up; how the league, simulator, exploiter and magnet compensate (§5) |
| 3 Hidden information, clarified | No privileged critic ever; true-future training labels under guards (a)-(e); E1 needs no belief model; blocks and reused decks get belief labels or none; generalisation on unseen deals (§1.2, §9, §12) |
| 4 Two-player only | Commander reduced to plug-in points (§10) |
| 5 Nothing hand-built | Simulator learned from finished games; the yardstick is measurement only (§8) |
| 6 Simulator design | Joint hand decoder, library-contents decoder, marginals; importance-sampled futures; detached belief tokens (§1.3, §8) |
| 7 Accumulation | In search, per-move weighted averages; in training, across labels via the linear target; two regression tests (§1.4) |

---

## Appendices A and B

The amended D6 and D20 are applied in docs/DECISIONS.md (2026-11-06).

## References

Numbering is kept from v1, so the gaps are references no longer cited.

- [4] Sokota et al., MMD, ICLR 2023.
- [5] Vinyals et al., AlphaStar, Nature 2019.
- [9] Hu et al., Learned Belief Search, arXiv:2106.09086.
- [10] Anthony et al., Expert Iteration, NeurIPS 2017.
- [11] Silver et al., AlphaGo Zero / AlphaZero.
- [13] McCandlish et al., arXiv:1812.06162.
- [15] Frank and Basin 1998; Cowling, Ward and Powley, TCIAIG 2012.
- [19] Jiang et al., PLR, ICML 2021.
- [20] Rutherford et al., No Regrets, NeurIPS 2024.
- [21] Samvelyan et al., MAESTRO, ICLR 2023.
- [22] Parker-Holder et al., ACCEL, ICML 2022.
- [23] Bursztein, CIG 2016.
- [26] Sokota et al., Ataraxos, arXiv:2511.07312.
- [27] Rudolph et al., ICLR 2026.
- [28] Sokota et al., update-equivalence, ICLR 2024.
- [29] Lanier et al., DAGS, arXiv:2605.14379.
- [30] Tesauro and Galperin, NIPS 1996, arXiv:2501.05407.
- [31] Bertsekas, Tsitsiklis and Wu, J. Heuristics 1997.
