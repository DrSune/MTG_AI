# The drafter: a controllable generative deckbuilder

Implements [`NORTH_STAR.md`](../NORTH_STAR.md) §4a and [`DECISIONS.md`](DECISIONS.md) D14, D15, D16.
Sits on top of [`DESIGN_TEACHER.md`](DESIGN_TEACHER.md) §3 (the critic) and §4 (1-by-1 drafting);
that document specifies the pick head, this one specifies the **control surface** around it and the
measurement that proves the controls are real.

Scope note, from `DESIGN_TEACHER.md` §4.1:481. Commander has no draft. "Drafting" here means
**deck construction**, a `T = 100` sequential MDP producing a 100-card singleton deck inside a
commander's colour identity. The 8-seat Limited loop is the smaller, later case (§8 stage 5).

---

## 0. The position, in one paragraph

**Nicheness and randomness are measured properties of the decks the drafter produces, not internal
sampling parameters, and the map from knob to internal parameter is fit by calibration against those
measurements.** Mechanically: **sample a deck-intent once, then draft near-greedily conditional on
it.** Nicheness selects *which region of intent space* the draw comes from. Randomness selects *how
widely* it draws inside that region, and how much predicted deck quality the pick chain is allowed
to spend. Because a controller solves for both measured targets jointly, turning randomness up
**cannot** raise measured nicheness: independence is enforced, not merely audited afterwards. The
moment nicheness becomes a weight inside the sampler, the trap in D16:274 re-opens and no metric
notices.

---

## 1. Two axes, and why one knob cannot be both

### 1.1 The picture, because the owner must not be able to misread this

Deck space has peaks. The tallest peak is the standard deck. There are other peaks, lower but real,
that are coherent decks of an unusual kind.

- **Temperature moves you off your peak in a random direction.** You get a different deck each time,
  and every one of them is a *damaged* version of the deck you asked for. Turn it up on a
  standard-deck request and you get a **worse standard deck**. You never arrive at another peak,
  because a peak is a specific place and noise has no destination.
- **Nicheness walks you to a different peak, then climbs it.** The result is unusual *and* good,
  because once the destination is chosen the drafter still maximises quality all the way there.

> **Temperature re-rolls the answer to the same question. Nicheness changes the question.**
> If a proposal ever answers "make it weirder" by adding noise, it has failed this goal.

### 1.2 The two axes, side by side

| | **N, nicheness** | **T, randomness** |
|---|---|---|
| what it is | a *directed* displacement of the intent | *undirected* spread at fixed intent |
| what it changes | which distribution is decoded | how widely intent space is sampled, and how much quality the chain may spend |
| where it enters the code | **inside the network**, as a conditioning input, before any logit exists | **outside the network**, in the sampler and the budget ledger. It is never an input to the model |
| measured as | `n_hat = F(log p_ref(E(deck)))`, a quantile (§2) | `t_hat` = mean pairwise intent distance between decks produced from *the same* request under re-rolled seeds |
| at 0 | the modal deck for the request | deterministic: the same deck every time |
| at 1 | the rarest coherent intent the corpus supports | the widest spread the level set allows |
| effect on deck quality | a measured price, `DFT-10`, published, never assumed | a measured price, same instrument |
| effect on sample-to-sample variety | small by construction | large by construction |
| the owner's sentence it answers | *"how niche/non-standard your deck is supposed to be"* | *"we dont want it to just choose THE best deck it can make every time"* |

### 1.3 The structural reason they cannot collapse into one knob

They act at different points of the pipeline, on different objects.

```
N  ->  select intent z* inside a density level set  ->  [ NETWORK: pick head conditioned on z* ]  ->  deck
T  ->  the spread of the z* draw, and the size of the Phi budget the pick chain may spend
```

`N` is an argument to the forward pass. `T` never touches a weight. A single knob wired to both would
have to be simultaneously a conditioning input and a sampler parameter, which cannot happen by
accident: it can only happen if somebody deletes the intent and calls the temperature "nicheness".
That is the failure the register row `conflation_alarm` (§7.2) exists to catch.

### 1.4 The falsifiable claim, and the control that must be run against it

> Raising `T` at fixed `N` must raise `t_hat` and leave `n_hat` flat. Raising `N` at fixed `T` must
> raise `n_hat` and leave `t_hat` flat.

A **temperature-only drafter** (one knob, wired to per-pick sampling temperature, `N` mapped onto it)
is a **mandatory pre-registered control** per `METRICS.md` Rail F:169. It will score a high slope on
`n_hat`, because noise does raise measured surprise. It will fail on `conflation_alarm` and on
`DFT-10`. **A slope alone cannot distinguish this design from the trap; only the pair can.** If the
control matches this design on both numbers, the intent machinery is buying nothing and should be
deleted rather than shipped.

---

## 2. What nicheness is measured against

### 2.1 The intent latent

Add one head to the deck encoder that `DESIGN_TEACHER.md` §3.2:380 already specifies (6 layers,
d = 256, full pairwise attention over at most 203 role-tagged card tokens, **no positional
embedding**):

```
E(deck or prefix)  ->  ( mu, log_sigma )   over  z in R^32
```

Trained by the objective already scheduled at `DESIGN_TEACHER.md` §4.5:563: take a complete deck,
sample `k ~ U(0,99)`, hide a random subset, encode the visible subset, predict the held-out cards
conditioned on `z`. That is a conditional masked-set autoencoder. It costs **zero additional games**,
supplies about 10^6 targets from about 10^4 decks (§6.4:720), and enforces order invariance by
construction because the encoder carries no positional embedding. `q(z | prefix)` therefore exists at
every prefix size, which is what makes §3.6's three modes one definition rather than three.

### 2.2 The reference population, and the one population deliberately excluded

```
n_hat(D) = F( log p_ref( mu(D) ) )      F = the empirical CDF over the reference population,
                                            oriented so that low density -> high n_hat, in [0,1]
```

`p_ref` is a **diagonal-covariance GMM over z**, component count `K` selected by BIC on held-out
decks, never typed in. At `K = 16` that is `16 * (32 + 32 + 1) = 1,040` parameters. Naming the
estimator and sizing it by a held-out criterion is the whole answer to "fit a density on the corpus":
nothing here is left as a black box.

| population | in `p_ref`? | role |
|---|---|---|
| the teacher's archive decks | **yes** | the bulk of the corpus |
| decks actually played in the league | **yes** | keeps the corpus on the distribution the critic was fit on |
| the human deck-level corpus (§6.3 source 4) | **yes, weighted up** | the only non-self-referential mass in the reference |
| **the permanent uniform-random-legal outgroup** (`DESIGN_TEACHER.md` §2.5:307, `TCH-5`) | **NO** | it stays the **external null** it already is, per `METRICS.md` Rail B:82 |

That last row is load-bearing and it is the easiest mistake in this design to make. The outgroup is,
by construction, the lowest-density population available. Put it in `p_ref` and it **owns the tail
that `N = 1` addresses**, so the top of the nicheness scale becomes a pile of random legal cards,
which is exactly the object `METRICS.md` §17:838 records as scoring maximally on every diversity
metric in the catalogue. Keep it out of the corpus and it does two better jobs: the null in every
`DFT-*` row below, and the anchor for `TCH-5`'s calibration alarm.

### 2.3 The measuring instrument is frozen, and versioned separately from the model

`E_ref` and `p_ref` are a **frozen snapshot**, `reference_vN`, never the live model's own encoder.
If nicheness were measured by the live network, the drafter could satisfy a nicheness request by
moving its own reference, which is `METRICS.md` §18.2:889's self-reference problem with a shorter
feedback loop. Every reference bump is an `environment_contract_epoch` stamp under Rail H:190 and
prints `DFT-18 reference_drift_on_refit` over a frozen 200-deck panel.

### 2.4 Nicheness is always *conditional* nicheness

`N` indexes a level set of the **posterior** `q(z | prefix, commander, format)`, never of the global
prior:

```
L(N) = { z : F(log p_ref(z)) in [N - w, N + w] }     w = the CV / Silverman bandwidth of a KDE
                                                         fitted to the corpus's own n_hat histogram.
                                                         MEASURED and published, not authored
z* = argmax over L(N) intersect support(q(. | prefix))  of  q(z | prefix)      at T = 0
z* ~ dispersion rho(T) over the same intersection                              at T > 0
```

On an empty prefix the posterior equals the prior and the two coincide, so this is **one definition,
correct in all three modes**. If `N` indexed the global prior instead, a niche request on a human's
66-card prefix would return cards that contradict the prefix, and the completer is the mode where
that breaks visibly.

Drawing `z*` is cheap: sample `M` candidates from `N(mu(prefix), rho(T)^2 diag sigma(prefix)^2)`,
keep those whose `F(log p_ref(z))` falls in the band, then select (T = 0) or sample (T > 0) among the
survivors. GMM density evaluations are microseconds and need no network forward beyond the single
encode of the prefix.

### 2.5 Why a garbage deck cannot satisfy a nicheness request

Six independent blocks, none of them a hand-set threshold.

| the cheat | why it fails |
|---|---|
| emit 100 random legal cards, which are maximally unusual | `n_hat` is a quantile against a corpus that **excludes** the random-legal population (§2.2). A random deck is not in the tail of the corpus, it is **off the corpus manifold**, and `DFT-12 intent_recoverability` measures exactly that: `\|\|mu(D) - z*\|\|` in posterior-sd units is large, so the deck is reported as **broken**, not as niche |
| satisfy `N` and let quality fall | quality is **always maximised conditional on** `(N, T)`. There is no strength knob to turn down (§9). The price is published as `DFT-10` and paid, never hidden |
| game the statistic by optimising it | `n_hat` is **never a reward**. It is a conditioning input and a published measurement. Same treatment `DESIGN_TEACHER.md` §4.4:546 gives `DFT-5`'s target curve, "a measuring ruler exposed to the analyst and never to the agent", and one step safer: **an input creates no incentive at all** |
| hit the band with unplayable cards during training | the objective is advantage-weighted (§6.1). A bad deck carries weight ~ 0, so band compliance is only ever paid on decks that were good |
| ask for a band nobody has ever built in | the product **refuses** a request whose level set holds fewer than `n_min` corpus decks, prints the reachable range, and says so. The limit is **data, not code**: it moves as the corpus widens. `n_min` is a `[guess]` until Rail K:230 calibrates it |
| claim the win on a coverage number | every nicheness number is published null-zeroed **per band** against best-of-m outgroup decks landing in the same band (`DFT-15`), so a random drafter scores **0** on the headline while scoring maximal on the raw level (§7) |

### 2.6 Measured, published, never rewarded

`DFT-13 deck_sharpness = mean over c of [ Phi(D) - Phi(D - c + best legal replacement) ]`, free from
the leave-one-out sweep of `DESIGN_TEACHER.md` §4.6:571. This is `ideas.md:1`'s own definition of a
niche deck ("very few changes to the deck completely ruins the deck's performance"), and it is kept
as a **coordinate, not an objective**. Optimising for sharpness selects for fragility, and fragile
decks lose to a league, which fights the King Goal directly. Publish it beside `n_hat`; never put it
in a loss.

---

## 3. The control surface

### 3.1 The knobs

| knob | range | default | what it moves | learned during training? |
|---|---|---|---|---|
| **`N` nicheness** | `[0, 1]`, a quantile | **fit**, §3.5 | which level set `z*` is drawn from | yes: the training-time knob distribution is chosen by the curator's own priority (§6.4) |
| **`T` randomness** | `[0, 1]`, mapped by calibration to `(rho, B)` | **fit**, §3.5 | the dispersion of the `z*` draw, and the size of the Phi budget the pick chain may spend | same |
| **`S` specialisation** | `[0, 1]`, **counter-draft mode only** | 1.0 | the maximised scalar: `Phi_S = (1-S) * Phi_league + S * Phi_h2h` | same |

`S` is deliberately **mode-local**, not a third global knob. "How typical is this deck" is a property
of deck space; "how hard does it target that opponent" is a property of a matchup. Keeping them apart
is what makes `N = 0.7` mean the same thing against every opponent.

### 3.2 What is a constraint, not a knob

Commander choice, forced includes, a banned subset, the format, the enabled pool. These are expressed
through the **hard legality mask** of `DESIGN_TEACHER.md` §4.4:525 plus a user-supplied prefix, which
is exact and costs microseconds. Sampled rather than user-supplied, they are also the training-time
source of directed deviation (§6.3). A user who wants a direction gives a commander or gives cards.
There is no archetype dropdown (§9).

### 3.3 The extremes, across all three modes

| `(N, T)` | build from empty | complete a partial 66-card deck | counter-draft |
|---|---|---|---|
| `(0, 0)` | THE best deck it can make, identical every time. The corner the owner explicitly said must not be the default | the most orthodox completion of their cards | the sharpest available answer to that decklist |
| `(0, 1)` | many *different strong standard* decks. This is the answer to "don't give me the same deck twice" | many orthodox completions | many good answers, spread over lines of attack |
| `(1, 0)` | the single weirdest **coherent** intent the corpus supports. Warns when the level set holds fewer than `n_min` decks: below that it is reproducing a memorised oddity, not generalising | the weirdest reading of their 66 cards that is still consistent with them | a niche deck that may simply be bad into that opponent. `S` mediates and `DFT-10` prices it |
| `(1, 1)` | the widest spread inside a thin set. The achievable `T` is **clamped by measurement** and the clamp is shown | usually near-inert: the range collapse is reported, not hidden | as build-from-empty |

### 3.4 The achievable region is not a rectangle, and it is published

Two real interactions. Both are correct behaviour and both must be surfaced rather than smoothed over.

- **The `T` ceiling falls as `N` rises.** A high-`N` level set has less volume and fewer distinct
  modes. There genuinely are fewer weird-but-coherent decks than normal ones. Publish the measured
  feasibility map and clamp the UI to it.
- **The completer's range collapses with prefix size.** With 97 cards fixed, `q(z | prefix)` is
  nearly a point mass and both knobs are nearly inert. Good product behaviour is to say so:
  *"with 97 cards fixed your achievable nicheness range is [0.61, 0.74]. You have already chosen a
  niche deck."*

### 3.5 Defaults are fit, not chosen

The shipped default `(N, T)` is the pair whose **output distribution is closest to the corpus
distribution** under a two-sample test on `(n_hat, t_hat)`. That is a measurement, refit per
checkpoint, not a number somebody liked. It satisfies the owner's "not THE best deck every time"
without anybody authoring a taste.

### 3.6 Three modes, one model

Extends `DESIGN_TEACHER.md` §4.5:551 with two columns. **No new rows and no second network.**

| use | prefix | candidates | slots | scalar maximised | `N` | `T` |
|---|---|---|---|---|---|---|
| build from empty | empty | retrieved top-256 | 100 | `Phi_wr` vs the league | yes | yes |
| complete a partial deck | the human's k cards | retrieved top-256 | 100 - k | same | yes, conditional on the prefix | yes, range collapses with k |
| counter-draft | empty or partial | retrieved top-256 | 100 - k | `Phi_S` (§3.1) | yes | yes |
| teacher | empty | retrieved top-256 | 100 | `R`, the probe delta (§2.2:232) | sampled by the curator | sampled by the curator |
| Limited pick | the pool so far | the pack | - | eventual deck strength | later (§8 stage 5) | later |

Why one model covers all of it: the encoder is **order invariant** (§3.2:392), so "complete this
human's 66 cards" is the same forward pass as "continue my own construction"; the head is a
**pointer** (§4.3:501), so the candidate supply may change without reshaping a layer and a never-seen
card is pickable on day one; and the opponent enters as a role-tagged token block (§4.2:486), which
is why counter-draft is free.

**The opponent's decklist never enters the intent prior.** It enters the state and the maximised
scalar only. That is what keeps `N` matchup-independent.

---

## 4. How compounding over ~100 sequential picks is avoided

### 4.1 The failure being avoided

Per-pick temperature over 100 picks injects 100 independent perturbations. Aggregate deviation grows
like the square root of the pick count, in an unbounded direction, and the output is an incoherent
pile: the **opposite** of a niche deck. D16:274 already rules on this. Five layers follow, in
descending weight. The first is the whole answer.

### 4.2 Layer 1: one draw, not one hundred

`z*` is committed **before pick 0** (the commander, §4.2:496, the highest-leverage pick in the deck
because it sets the colour-identity mask for the other 99). All 100 picks share it. One perturbation
with 100 correlated consequences is a coherent unusual deck; 100 independent perturbations is a
random deck. This is `DECISIONS.md` D11:160's plan-commitment contract applied to deckbuilding:
**commit to a direction once, then execute it well.**

### 4.3 Layer 2: per-pick temperature is exactly zero by default

Not low. Zero. Argmax under the mask. Per-pick stochasticity is opt-in and, when opted into, is
governed by layer 3 rather than by a temperature.

### 4.4 Layer 3: a Phi-budget ledger, denominated in quality, not in logits

```
eps_remaining = B(T)                                # units: predicted Phi, calibrated to Elo
for t in 1..100:
    s[c]  = Phi_hat(prefix + c | z*)   for c in the masked candidate set
    best  = max(s)
    A     = { c : best - s[c] <= eps_remaining }
    pick c ~ Uniform(A)
    eps_remaining -= (best - s[c])
```

Total predicted quality sacrificed over the entire construction is **bounded by `B(T)` by
construction**. There is no per-pick temperature to compound, and there is no spend schedule: any
pick may spend the whole remaining budget, and the empirical spend profile across pick index is a
**published measurement, not a setting**, which is what `NORTH_STAR.md` §3:94 asks for. `B(T)` comes
from a measured regression of `Phi_wr` on realised Elo against the anchor ladder, so the knob reads
*"spend 15 Elo for variety"*. **A budget denominated in Elo is a priced knob; a temperature
denominated in logits is a wish.**

### 4.5 Layer 4: the conditioning is negative feedback, and it is order invariant

An unconditional sampler is a random walk. A conditioned one self-corrects. Feed the pick head the
**intent residual** as a FiLM input alongside `z*`:

```
b_t = z* - mu( prefix_so_far )
```

If picks 1 to 20 drifted, `b_t` grows and picks 21 to 100 compensate. Variance in intent space is
`O(1)`, not `O(100)`.

One subtlety, stated because a neighbouring proposal got it wrong: a running "surprisal-to-go"
computed over a *sequence* is order-dependent, so it would be trained under random prefix orders and
deployed under the policy's own left-to-right order, putting the controller signal off-distribution.
**`b_t` here is a function of the prefix as a set**, because the encoder has no positional embedding
(§3.2:392). Training and inference see the same object and the mismatch does not exist.

### 4.6 Layer 5: refinement must be a **projected** ascent, and this is the likeliest silent failure

`DESIGN_TEACHER.md` §4.6:571's leave-one-out sweep (100 forward passes, microseconds) is where the
quality is. Run it unconstrained and **it hill-climbs the deck straight back to the mode and silently
erases the entire feature**. The knob still calibrates, the metrics still move, and every returned
deck is the standard deck.

```
maximise Phi_wr(D)  subject to  F(log p_ref(mu(D))) still in [N - w, N + w]
```

Re-encode after each accepted swap (one forward pass) and reject any move that leaves the level set.
Refinement then repairs incoherence **without repairing weirdness**, which is precisely the
difference between niche and noisy. Write the constraint into the code with a comment pointing at
this paragraph.

There is a second, quieter payoff: this asymmetry is **why `T` can be raised without paying the full
sampling loss.** Noise that produced something interesting survives the sweep; noise that produced
something bad is undone. The realised cost of `T` is only the loss the critic cannot see.

### 4.7 The falsifier, which is free and runs at stage 4

`DFT-16 coherence_at_matched_variety`. Run the budgeted sampler and a naive per-pick-temperature
sampler **at equal measured `t_hat`**, and publish the fraction of decks clearing `DFT-5` plus the
corpus quality floor. No engine, no games, critic forwards only.

Pre-registered prediction (Rail F:169): the per-pick sampler's pass rate collapses as variety rises;
the budgeted sampler stays flat, because the budget bounds total loss by construction. **If the
experiment does not separate them, the compounding argument above is wrong and must be published as
wrong.**

---

## 5. Architecture, parameter counts, and what is shared with the teacher's critic

### 5.1 Shared, at zero marginal cost

| shared object | source | why it is the same object |
|---|---|---|
| `v_card` composed ability-tree vectors, d = 256, cached | `DESIGN_CARD_POOL.md` steps 1-3, §3.3:423 | **0 marginal parameters.** Attention matches on atoms, not identities, which is what makes synergy generalise to unseen cards |
| deck encoder, 6 layers, d = 256, no positional embedding | §3.2:380, 4.72 M | order invariance is what makes the completer the same forward pass as build-from-empty |
| candidate scorer plus bilinear pointer | §3.3:425, 1.64 M | one head, three candidate supplies (§4.3:517) |
| the legality mask | §4.4:527 | exact, free, never a penalty |
| the archive | §3.1:364 | the drafter's training corpus and the teacher's working set are one object |
| `Phi`, the critic | D15:252 | **the load-bearing share.** It is what lets the drafter be trained with no human reference corpus of good decks |

`DESIGN_TEACHER.md` §4.3:514 is explicit: the drafter and the in-game `retrieve_topk` pool
conditioning are **one network used twice**. Do not build two.

### 5.2 New parameters, arithmetic shown

| block | shape | params |
|---|---|---|
| intent posterior head | pooled 256 -> 512 -> 64 (`mu` 32, `log_sigma` 32) | `256*512+512 + 512*64+64` = **164,416** |
| intent FiLM into the pick head | `[z* 32, b_t 32, N, prefix frac, slots frac, budget frac]` = 68 -> 256 -> 512 | `68*256+256 + 256*512+512` = **149,248** |
| deck-strength head `Phi_wr` (Bradley-Terry), beside the existing `R` and log-variance heads | 256 -> 512 -> 1 | `256*512+512 + 512+1` = **132,097** |
| reference density `p_ref` | diagonal GMM over z, `K` by BIC; at `K = 16` | **1,040** |
| | **total new** | **~0.45 M** |
| | teacher total, §3.3:429 | 7.2 M |
| | **combined** | **~7.6 M, 15.2 MB in bf16** |

`Phi_wr` is a separate head from `R` on purpose. `R` is **teaching value** for a mid-training student
(§2.2:232), and a deck with high `R` can be a bad deck. Ranking the niche *product* by `R` would hand
a player a pedagogically useful sparring partner, which is a different and worse thing. **The teacher
maximises `R`; the product maximises `Phi_wr`; one encoder, two heads.** Its supervision is free: one
Bradley-Terry triple per game ever played, ~10^4 triples for a coarse `Phi` (§6.4:722).

### 5.3 Cost check, and a citation correction

| | value | source |
|---|---|---|
| weight bytes | 7.6 M x 2 = 15.2 MB | §5.2 |
| forwards per deck | 100 picks plus ~3 refinement sweeps = ~103 | §4.6:574 |
| bytes per deck built | ~1.57 GB | |
| at 273 GB/s | ~5.7 ms, launch-bound in practice, so ~0.2 to 0.4 s per deck | `HARDWARE_DGX_SPARK.md` |
| games that deck then plays | N = 30 x ~2,173 decisions = 65,190 decisions | `reports/decision_counts_devbox.json` |
| amortised traffic per game decision | ~24 KB against the board encoder's 800 MB | `reports/latency_devbox.json` |
| **share of the decision budget** | **~0.003%** | §3.4:452 |
| calibration refit, 750 decks per checkpoint | ~4 minutes, **zero games** | §7.6 |

**Correction, stated because this document leans on file:line precision.** `DESIGN_TEACHER.md`
§3.4:470 calls the teacher "`COST_MODEL.md` §4 tier A at roughly 0.001 reads per decision".
`COST_MODEL.md` §4:89 defines tier A as **~0.15 reads per decision** (one in six or more), and it
describes the board encoder. The drafter is not tier A. It is **off the per-decision path entirely**,
two orders below tier A, and that is the actual reason it is affordable. The conclusion in §3.4
survives intact; the label does not.

**Zero new parameters in the per-decision path.** The one failure mode to avoid absolutely is letting
any of this run inside the game loop, which would move it to tier C and charge it up to 40 reads per
decision (`COST_MODEL.md` §2:44).

### 5.4 Growth rules, published, not scheduled

Mirrors §3.3:433's rule for the encoder.

- **`d_z = 32` grows to 48 or 64** only when held-out **masked-token log-likelihood** has been
  flat-topped for two consecutive review windows.
- **`K`** in `p_ref` is set by BIC on held-out decks at every refit. Never typed in.
- **`w`**, the level-set bandwidth, is the CV or Silverman bandwidth of the corpus `n_hat` histogram.
  Measured, published, refit with the corpus.
- **`B(T)` and `rho(T)`** come from the isotonic calibration of §7.1. A fit is not a schedule.

### 5.5 Capacity honesty

At B = 2,000 deck labels, §3.3:431 already warns that 7 M parameters is over-parameterised. But `z`
and the pick head are **not** trained on the 10^4 noisy block scalars. They are trained on the ~10^6
masked-token targets of §4.5:567, which is a far larger supervision surface. Only the AWR *weights*
carry the 10^4 scalars, and their job is to break the circularity of learning from the bot's own
decks (§5.2:643). The estimator that genuinely is starved is `p_ref`'s **tail**, which is exactly
where `N = 1` lives. That is open question Q3 (§10), and it is stated rather than hidden.

---

## 6. Training, and where niche decks come from before the drafter can make any

### 6.1 The objective

Advantage-weighted, hindsight-relabelled conditional masked deck modelling: §5.2:629's tier 1 with
two extra conditioning inputs.

```
sample deck D from the buffer;  k ~ U(0,99);  hide a random subset H
z*   := mu(D)                                    # hindsight: the deck's OWN realised intent
N*   := F(log p_ref(mu(D)))                      # hindsight: its OWN measured nicheness
L    = - w(D) * sum over c in H of  log pi( c | prefix_visible, globals, FiLM(z*, b_t, N*, ...) )
w(D) = clip( exp( (R(D) - Phi(s_0)) / beta ), 0, w_max )
```

Two consequences worth naming. **The conditioning is a label the deck computes about itself**, so
there is no such thing as a mislabelled training deck, and garbage decks are useful training data
rather than contamination. And **`T` never appears in this loss**, because `T` is not a property of a
deck, it is a property of a *request distribution*. That asymmetry is the clearest possible statement
that the two knobs are different objects: they are not even in the same file.

**Conditioning dropout at ~15%**, the same rate and rationale as the atomic-id dropout at
`DESIGN_CARD_POOL.md:153`. Its purpose here is not classifier-free guidance (§9): it is to keep an
**unconditional decoder** alive as the "ignores the knobs" null control that every `DFT-*` row in §7
is scored against, measured in the same run under the same RNG stream per Rail B:88.

### 6.2 The bootstrap, in one sentence

**You do not need niche decks to start. You need coverage of the `n_hat` axis, and hindsight
relabelling makes coverage a property of the archive rather than of a curated corpus:** every deck
ever built is a labelled training point at its own measured nicheness, including the bad ones.

### 6.3 The four sources of directed deviation, none of them authored

| source | supplies | cost | status |
|---|---|---|---|
| **1. hindsight relabelling of the archive** | the bulk of the `n_hat` range, graded | **zero** | free once §6.1 lands |
| **2. constraint-sampled construction** | *directed* deviation: coherent-but-unusual by construction | **zero extra games** | new, and the one I would bet on |
| **3. k-step random walks under the single-card edit operator** | a graded ladder outward from any elite | zero | the ACCEL mutation already in §3.1:375 |
| **4. a human deck-level reference corpus** | the only non-self-referential mass in `p_ref` | one offline script plus acquisition | **stage 0, and the highest-leverage non-code item in this document** |

**Source 2, concretely.** Build the best deck the drafter can **under a randomly sampled hard
constraint**: a commander drawn from the tail of `edhrecRank` (already on the stage-0 re-ingest list,
§7:766, and the only external, non-self-referential popularity signal in the project's data), plus a
sampled forced-include set of 5 to 15 legal cards, plus a sampled banned subset. The result is a
**constrained optimum**: a different local optimum, coherent because it was still maximised. That is
what a niche deck is, and it is exactly what temperature cannot produce. The constraint is *sampled*,
not authored, and the deck is still scored by the unchanged `R` and `Phi_wr`, so this is not the
archetype dictionary §8:871 already refused.

Pick 0 does the heaviest lifting for free: sampling commanders down the `edhrecRank` tail moves the
whole deck to a different region of deck space in one pick, with zero incoherence, because the
colour-identity mask does the rest (§4.2:496).

**Source 4, concretely, with the honest caveat.** `METRICS.md` §18.1:892 and `DFT-4`:634 record that
no public per-decision Commander corpus exists. That is a statement about **per-decision** data.
**Deck lists are a far coarser and far more available object.** MTGJSON's own preconstructed
Commander deck lists (~150 real human-authored 100-card decks) arrive through the same ingest path
stage 0 is already fixing, and `edhrecRank` gives a card-level human-play prior that can
importance-weight the rest. ~150 decks is thin for a density over 32 dimensions and will not carry
`p_ref` alone; its job is to **anchor and to validate**, with `DFT-17`'s blinded panel as the check
that it worked. If the corpus cannot be acquired, say so to the owner in those words rather than
shipping the self-referential version quietly (§10 Q2).

**Explicitly not a source:** a curated niche-archetype dictionary. That is `deck_generator.py:23-31`
with more strings.

### 6.4 The knob distribution during training is learned, not scheduled

At inference `(N, T)` are user inputs. During training they are **sampled per generated deck from a
distribution the curator adapts**, using the staleness-aware priority that already ranks the archive
(§3.1:364). Knob settings that produce decks with high `R` get sampled more. No authored schedule,
and it is the honest test of `NORTH_STAR.md` §1:29's "niche decks count as rank 1": the teacher will
spend games on niche decks only if they pay in probe delta.

This is what replaces `ideas.md:10`'s annealed `lambda` on robustness ("high early, lower later").
Right intuition, wrong implementation: it is a hand-authored curriculum over a reward term, twice
over, and `NORTH_STAR.md` §3:94 defaults to no. If orthodox decks teach better early and niche decks
teach better late, the archive discovers that **and discovers the crossover point**, which no
schedule can.

### 6.5 Expectations, so the first evaluation is not misread

§6.5:733 sets this for the drafter and it applies to the knobs too: expect *"builds a legal, curved,
on-colour, coherent deck that beats a uniform random legal deck 80%+ of the time"* long before
*"picks the right 99th card"*. For the control surface specifically, expect the **`N` axis to
calibrate before the `T` axis prices well**, because `n_hat` is a one-forward measurement while
`t_hat` needs 30 decks per grid cell and `DFT-10` needs games.

---

## 7. The metrics that prove each knob works

### 7.1 Independence is enforced by calibration, then audited by a metric

Fit a 2-D monotone (isotonic) map from internal `(rho, B)` to **measured** `(n_hat, t_hat)`, refit
per checkpoint from ~750 generated decks at zero games, and invert it to serve a request. Because the
controller solves for both measured targets **jointly**, raising `T` cannot move `n_hat`: the solve
holds it. An isotonic fit is a fit, not a hand-authored schedule (`NORTH_STAR.md` §3:94).

The calibration also absorbs **decode error**: the deck the pick head actually emits may re-encode
slightly outside the requested band. Closed loop is the honest response to that. An open-loop map
would silently mis-serve every request and nothing would notice.

### 7.2 Register rows, per `METRICS.md` §17:827

All new rows extend family DFT. `M_null` is the unconditional decoder of §6.1, measured in the same
episode on the same RNG stream (Rail B:88). `M_random` is the permanent uniform-random-legal
outgroup.

| ID | metric | null (ignores the knobs) | uniform random legal | mandatory pairing |
|---|---|---|---|---|
| **`DFT-9`** | `knob_response_jacobian`: 5x5 grid of requested `(N,T)`, M = 30 decks per cell, report `J = [[dn/dN, dn/dT], [dt/dN, dt/dT]]`, normalised | **J = 0** | **J = 0** (pinned at maximum, unresponsive) | with `DFT-10`. Never publish a diagonal without the off-diagonal |
| **`conflation_alarm`** | the off-diagonal `dn_hat/dT`, alone | 0 | 0 | **the trap in the brief, rendered as one scalar.** A temperature-only drafter scores it strongly positive. Never published alone, because a null scores 0 on it too |
| **`DFT-10`** | `price_of_nicheness`: `Phi_wr(N) - Phi_wr(0)`, plus win rate against the anchor ladder at `N` in {0, 0.5, 1.0} | 0, no curve | catastrophic at every `N` | the §17 partner: satisfiable only by acting well |
| **`DFT-11`** | `knob_calibration_error`: `mean of \|n_hat - N\|` and `mean of \|t_hat - T\|` over the grid | maximal | maximal | **the number the user actually experiences** |
| **`DFT-12`** | `intent_recoverability`: `\|\|mu(D) - z*\|\|` in posterior-sd units. **Lower is better** | small only at the single `N` its one deck sits at, large elsewhere | **large everywhere** | separates *niche* from *broken* **without reference to strength**, which nothing else here does |
| **`DFT-13`** | `deck_sharpness` (§2.6), free from the §4.6 sweep | low | low | published beside `n_hat`. **Never rewarded** |
| **`DFT-14`** | `variety_at_fixed_quality`: mean pairwise intent distance **conditioned on every sample clearing the same `Phi_wr` quantile** | 0 | **0 or undefined: it produces no admissible samples** | published with the quality quantile used. This is the recipe for a diversity number uniform random does not win |
| **`DFT-15`** | `niche_premium`: per `n_hat` band, `Phi_wr(drafter deck) - Phi_wr(best-of-m outgroup decks in the same band)` | 0 outside its own band | **~0 by construction: its deck IS the null** | the anti-null companion for any coverage or level number |
| **`DFT-16`** | `coherence_at_matched_variety` (§4.7) | - | - | always published beside the per-pick-temperature ablation |
| **`DFT-17`** | `nicheness_human_agreement`: `Spearman(human weirdness rank, n_hat)` over ~20 blinded decks spanning the range, with outgroup decks included as anchors | - | ranked weird by humans **and** by `n_hat`, so report the correlation with and without the anchors | the only check that the knob means what a player thinks it means. Below ~0.5 on the non-anchor subset, `n_hat` is measuring combinatorics rather than culture |
| **`DFT-18`** | `reference_drift_on_refit`: `mean of \|delta n_hat\|` on a frozen 200-deck panel when `reference_vN` changes | - | - | printed at every reference bump, with the Rail H:190 epoch stamp |

### 7.3 The headline is a triple, and no member of it reads alone

```
( n_hat , DFT-12 distance , DFT-10 price )

uniform random legal        ( maximal , large , catastrophic )      weird, broken, bad
the null / greedy drafter   ( minimal , small at N=0 only , 0 )     normal, coherent, free
a working drafter at N=0.8  ( high    , small , moderate )          weird, coherent, priced
```

### 7.4 What a degenerate drafter produces, checked against §17's rule

| degenerate drafter | produces | does the design pay it? |
|---|---|---|
| **uniform random legal** | maximal `n_hat`, maximal raw diversity | **No.** `DFT-15` null-zeroes per band and its elite *is* the null; `DFT-14` admits none of its samples; `DFT-12` is large; `DFT-5` gates it before a single game, at microsecond cost |
| **the current generator** (5-colour, 54.6 lands, max mana value 3, commander a basic land 60.7% of the time, §2.4:281) | an extreme corner | **No.** `DFT-5` fails it on four criteria simultaneously, before any game |
| **temperature-only** (`N` wired to per-pick temperature) | a high `n_hat` slope | **No, and this is the control that matters.** `conflation_alarm` positive, `DFT-10` strongly negative, `DFT-16` pass rate collapsing |
| **mode collapse** (one excellent deck, always) | high `Phi_wr` | **No.** `DFT-9` J = 0, `DFT-11` maximal, `DFT-14` = 0 |
| **band hacker** (hits the level set with unplayable cards) | `n_hat = N` | **No.** AWR weight ~ 0 in training; `Phi_wr` low so it is never returned; `DFT-12` large |
| **novelty maximiser** (maximise distance between outputs) | random maximises this exactly | **No.** There is no novelty term in any objective anywhere in this design (§9) |
| **sharpness seeker** (`ideas.md:1` taken literally) | maximally fragile decks | **No, and it would be actively harmful.** Sharpness is a coordinate (`DFT-13`), never an objective |

### 7.5 Pre-registered controls, per Rail F:169

Three, all mandatory, all measured in the same run on the same RNG stream:

1. the **unconditional decoder** (the 15% dropout branch), which is "ignores the knobs";
2. the **uniform-random-legal outgroup**, which maximises every level and responds to nothing;
3. the **temperature-only drafter**, which is the trap in executable form.

### 7.6 Budget, against Rail I:207

| item | cost | games |
|---|---|---|
| `DFT-9`, `DFT-11`, `DFT-12`, `DFT-13`, `DFT-14`, `DFT-16`, `DFT-18` | 750 decks x ~0.3 s, about 4 minutes per checkpoint | **zero** |
| `DFT-15` and `DFT-10`'s win-rate half | 3 to 6 anchor cells | ~300 to 600 games, booked as `SYS-5` inside the 5% |
| `DFT-17` | ~20 minutes of human time per generation | zero |

`DFT-17` earns its line: it is an order of magnitude cheaper than the 3-human-hour per-decision
elicitation panel §18.1:892 rules out, for the same reason deck lists are cheaper than plays.

---

## 8. Staging, aligned to `DESIGN_TEACHER.md` §7:756

**Nothing knob-shaped exists before stage 3. A slider demo before that is theatre and should be
called that.**

| stage | drafter deliverable | games |
|---|---|---|
| **0** (constraint filter, hours to days) | `deck_cards` keyed on oracle id (`E-DECK`), the `E-ID` namespace split, `format_legal` / `engine_supported`, the legality mask, `DFT-5`, the `edhrecRank` re-ingest, the interim card vector; **register rows `DFT-9..18` written before anything is built** (Rails F:169, J:217); **acquisition of the human deck-level corpus** (§6.3 source 4) and the `DFT-17` panel protocol | **zero** |
| **1** (gamma experiment, ~2 GPU-hours) | **nothing.** Do not touch it: it decides whether the teacher exists at all. Reserve the `E-DEC` and `E-DECK` fields the drafter will read | zero |
| **2** (league, blocks, outgroup) | the permanent uniform-random-legal outgroup becomes this document's **external null** for every `DFT-*` row, and is kept **out** of `p_ref` (§2.2). Bradley-Terry triples start accumulating for `Phi_wr`, one per game ever played | none marginal |
| **3** (archive plus critic) | the `Phi_wr` head (+0.13 M); the intent posterior head (+0.16 M); the first fit of `p_ref` on archive plus league plus human corpus; `DFT-12`, `DFT-13`, `DFT-15` computable. **The first point at which `n_hat` exists at all** | zero marginal |
| **4** (pick head) | intent FiLM conditioning (+0.15 M) folded into the random-prefix objective already scheduled at §4.5:566; the budgeted sampler; **projected** refinement (§4.6); the isotonic calibration; constraint-sampled construction as a second seeding operator; **`DFT-16` runs here, free** | zero |
| **5** (products) | the three modes of §3.6 become tunable at no extra training cost; the full `DFT-9` and `DFT-11` sweep; `DFT-10`'s game half; the `DFT-17` panel; Limited last | ~300 to 600 |

Nothing here moves the critical path or adds a game before stage 5. The knobs are a rider on work
`DESIGN_TEACHER.md` §7 already schedules: **if the drafter gets built, the knobs are nearly free; if
it does not, they are moot. There is no separate tunability project.**

---

## 9. What we are not building, and why

| not building | why | what survives |
|---|---|---|
| **a user-facing per-pick temperature slider** | the trap of D16:274, rendered as UI | the `T` knob acts on the intent draw and the Phi budget. Per-pick temperature exists **only** as `DFT-16`'s ablation control |
| **a strength slider** | quality is always maximised conditional on `(N, T)`, and shipping "make it worse" is not a product | the price curve `DFT-10`, published. Symmetric with D13:214's price of the clock |
| **a nicheness or novelty term in any reward** | "different" is what uniform random maximises (§17:837), and a novelty bonus is the noisy-TV failure in deck space, priced at 0.566 in §2.4:283 | conditioning on a **measured** statistic. An input creates no incentive |
| **`ideas.md:10`'s annealed `lambda` on robustness** | a hand-authored schedule on a reward term, refused by `NORTH_STAR.md` §3:94 | the curator's learned knob distribution (§6.4) |
| **`ideas.md:1`'s sharp-minimum-seeking optimiser** | right insight, wrong landscape: it confuses deck-space sharpness with weight-space sharpness, and optimising for it selects for fragility | `DFT-13 deck_sharpness`, a measured coordinate, free from the §4.6 sweep |
| **an authored archetype or nicheness dropdown** | `deck_generator.py:23-31` with a bigger dictionary, already refused at §8:871 | direction is expressed by giving a commander or giving cards, through the mask |
| **a separate niche drafter** | two networks means two corpora and the niche one has no data. §4.3:514 says do not build two | one network, plus 0.45 M parameters of conditioning |
| **folding nicheness into the teacher's archive as a fifth cell axis** | §2.3:255 measured MAP-Elites at 0.766 / 0.415 against a capped archive's 0.902 / 0.675 **because adding cells dilutes priority**, and adding an axis walks back down that gradient. `NORTH_STAR.md` §5:165 lists it as settled | the teacher's archive keeps its per-cell cap of 2. A **separate** niche archive stays parked exactly where §2.3:270 and §8:864 put it |
| **the uniform-random-legal outgroup inside `p_ref`** | it owns the low-density tail by construction, so `N = 1` would come to mean "garbage" | it stays the external null (`TCH-5`) and the per-band baseline for `DFT-15` |
| **nicheness measured against the live model's own branch** | self-referential: the model could satisfy a request by moving its own reference | a separately frozen, separately versioned `reference_vN`, audited by `DFT-18` |
| **classifier-free guidance as a third user knob** | it doubles per-pick forwards and adds a knob the owner did not ask for | the 15% conditioning dropout is kept, purely to keep the unconditional **null control** alive (§6.1) |
| **beam search or MCTS over deck construction** | it concentrates the output, destroying `T`, and multiplies cost by the beam width, to buy quality the projected leave-one-out sweep already buys anytime and variance-preservingly | §4.6's refinement |
| **deck crossover** | two 100-card singleton decks of different colour identities do not recombine into anything the mask can repair. The result is legal and incoherent | the single-card swap, which is simultaneously the ACCEL mutation, the owner's 1-by-1 primitive, and `ideas.md:8` |
| **auto-selecting `N` for the user** | the *training-time* distribution is learned; the *inference-time* value is the user's. Conflating them makes the control unpredictable, which is the one thing a control must never be | a **fit** default (§3.5) the user can override |

---

## 10. Open questions, marked per `NORTH_STAR.md` §6:190

Genuinely unresolved. Not manufactured to look careful, and not an excuse to defer work.

### Q1. Does a level set of the intent density actually contain coherent-but-unusual decks?

The whole design assumes the `n_hat` axis runs modal -> unusual-but-good -> bad. It may instead run
modal -> bad, monotonically, in which case the knob is real but it is a **strength slider with a
nicer label** and the owner's ask is unmet.

**Falsifier, and it is `DFT-10`'s own curve:** if the price of nicheness falls monotonically across
the entire trained `N` range and never flattens, the coherent-but-unusual region does not exist in
the corpus. The response is not to tune anything. It is to widen the corpus with constraint-sampled
construction (§6.3 source 2) until a flat shoulder appears, or to report honestly that it does not.
Not blocking before stage 4, and it is the first thing to look at when stage 4 lands.

### Q2. The corpus is largely our own shadow. **Mirror this into `DECISIONS.md` "Needs deeper reasoning".**

At stage 3, `p_ref` is dominated by the archive, which the curator has been actively shaping toward
teaching value. "Niche" then means "unusual relative to what our own teacher happened to build",
which is circular and drifts as the drafter changes. **It will look like it is working**: `DFT-9`
diagonal high, `conflation_alarm` near zero, `DFT-15` positive, every gate green, and the decks it
returns are not the ones a player would call unusual, because every metric in §7 except `DFT-17` is
measured against the same broken reference.

Tried: `edhrecRank` (card-level, external, weak) and the MTGJSON precon lists (deck-level, external,
~150 decks, thin for a 32-dimensional density). Both help; neither settles it. **Acquire a larger
deck-level human corpus at stage 0, or state the circularity out loud. Do not ship the
self-referential version quietly.** A wrong answer is expensive because the failure is invisible to
the whole instrument panel and is detectable only by `DFT-17`'s human panel, which is why that row is
not optional.

### Q3. Tail density estimation, which is exactly where `N = 1` lives

A GMM fit on ~10^4 decks estimates the **mode** well and the **tail** badly, and every high-`N`
request is a query about the tail. The `n_min` level-set population check (§2.5) bounds the damage by
refusing under-populated requests, but the threshold is a `[guess]` until Rail K:230 calibrates it,
and a mis-estimated tail biases `n_hat` itself rather than merely its confidence. Candidate
mitigations, none yet evaluated: a normalising flow instead of a GMM (more capacity, worse
small-sample behaviour), or reporting `n_hat` with a bootstrap interval and clamping requests to the
region where that interval is narrow. Not resolved.

### Q4. Does `S` stay out of `N`?

§3.1 keeps specialisation mode-local, on the argument that typicality is a property of deck space and
targeting is a property of a matchup. Untested. If counter-drafting systematically drags decks into
the tail (plausible, since hard answers to a specific list tend to be unusual cards), then `n_hat`
measured in counter-draft mode means something different from `n_hat` measured from empty, and the
knob stops being matchup-independent. **Check:** publish `DFT-9`'s Jacobian separately per mode.
Cheap, and not scheduled anywhere yet.

### Q5. Is "off the manifold" reliably distinguishable from "in the tail"?

`DFT-12` is the metric that separates niche from broken, and it rests on the assumption that a
garbage deck's posterior mean lands far from any requested `z*` while a genuinely unusual deck's
lands close. That is plausible and it is what an encoder trained by reconstruction should do, but it
is an empirical claim about a representation that does not exist yet. If it fails, the design loses
its one strength-independent integrity check and falls back on `DFT-10` alone.

### Q6. What `n_min` and the two other `[guess]` thresholds should be

`n_min` (the level-set population below which a request is refused), the `DFT-17` acceptance floor
(~0.5), and the `DFT-11` calibration tolerance. All three are `[guess]` and, per Rail K:230, **none
of them is an alarm until it has a measured baseline distribution.**

---

## 11. The one thing that must survive, and the biggest risk

**Must survive.** *Nicheness is a measured property of the produced deck, conditional on what the
user supplied, hit by closed-loop calibration, and never a term in any reward.* Everything else in
this document is replaceable. That one definition is what makes `dn_hat/dT ~ 0` an **enforceable
property** rather than an aspiration, and it is the only thing standing between this feature and a
temperature slider with a nicer label.

**Second, and nearly as important.** Randomness goes in the goal, determinism in the execution: one
intent draw, then near-greedy picks under a bounded budget, with refinement **projected onto the
level set**. That single move is simultaneously the anti-compounding mechanism and the reason
archived niche decks come out good rather than merely different.

**Biggest risk.** Q2: the reference is largely our own shadow, and the failure mode is a design that
passes every gate while returning decks no player would call unusual. The cheap check exists
(`DFT-17`, 20 human-minutes) and the cheap fix exists (a deck-level human corpus at stage 0). Both
are cheap only if they happen **before** the knob ships, which is why they are stage-0 items in §8
and not stage-5 ones.

---

## 12. Query-then-retrieve, and the card index

Implements the owner's request to "use the encodings" for card selection: emit a prediction of the
card the deck wants, then look that prediction up against the encoded ability-tree vectors. This
section says plainly that the mechanism is **already specified** in `DESIGN_TEACHER.md` §4.3:506,
then says what genuinely changes when it is implemented as retrieval rather than as a scoring loop.
It touches §5.1's shared-object table, §5.2's parameter count and §7.2's register, and it
contradicts nothing in §4: the fix recommended in §12.4 is deterministic, so per-pick temperature
stays exactly zero (§4.3:277) and the one-draw structure of §4.2:269 is untouched.

### 12.0 The owner's own earlier statement of this, recovered

This is not a new idea. It is the owner's, written down and then deleted. From
`git show db5e024^:MTG_bot/docs/RL_ARCHITECTURE.md` §5.1:

> **Action Space (Intelligent Sequential Selection):** The Teacher builds decks card-by-card using a
> **Transformer-based Matchup Analyzer**.
> * For each slot, the model generates a **Query Vector** based on the current deck's synergy and the
>   opponent's strategy.
> * It performs a **Vector Search** against the card embedding pool to find the optimal card to add.

Three parts of that document, and their fate here. The **query vector plus vector search** is
adopted, and is what this section specifies. The **illegal-proposal penalty** of its §5.3 is refused,
at `DESIGN_TEACHER.md` §4.4:542, in favour of a hard mask. The **matchup history plus diversity
bonus** survives as the archive with a per-cell cap, `DESIGN_TEACHER.md` §2.3:255. The idea is also
parked in `BACKLOG.md:82-86` under "Product goals beyond the King Goal", and its acceleration half is
`ideas.md:162-164` (TurboQuant). This section promotes the mechanism and keeps TurboQuant parked, for
the measured reason in §12.2.

### 12.1 The unification: the pointer head already **is** the vector search

`DESIGN_TEACHER.md` §4.3:506 specifies

```
score(c | s)  =  q(s) . k(c)     where  k(c) = W_k v_card(c),  q(s) = W_q deck_encoder(s)
pi(c | s)     =  softmax over the candidate set, after the hard legality mask
```

**`argmax` of an inner product over a set is, by definition, maximum-inner-product search over that
set.** "Predict the ideal card, then look it up in a vector database" and "score every candidate with
the pointer head and take the best" are the same arithmetic written two ways. There is no second
algorithm to choose between. `DESIGN_TEACHER.md` §4.3:516 already draws the conclusion ("the drafter
and the in-game pool-conditioning mechanism are **one network used twice**. Do not build two"), and
§5.1:366 of this document repeats it.

So the question is not whether to build retrieval. It is **what changes when the retrieval framing is
taken seriously**. Five things, and the fifth is a cost.

1. **The candidate set becomes a stored, filterable object** rather than a tensor assembled per call.
   Set, colour identity and singleton filters become mask algebra over one index (§12.5).
2. **The query becomes a materialised, loggable object**, emitted *before* any candidate is seen.
   That is the interpretability win (§12.6), and it does not exist in the pointer framing, where the
   query lives and dies inside a matmul.
3. **Scoring decouples from supply.** One query can hit the 25,000-card Commander pool, a 15-card
   pack, or a hypothetical-card index, with no retraining. Invention is only *expressible* because of
   this (§12.8).
4. **Approximation becomes an option.** We then decline it, on arithmetic (§12.2).
5. **A failure mode arrives that the pointer framing did not have.** Scoring an explicit candidate
   set evaluates every mode of a multimodal pick. A single query plus a top-k cut can fail to
   retrieve a whole mode. That is the real risk, and it is quantified in §12.4.

### 12.2 Cost, and why the index is exact and stays exact

The key matrix `K = V W_k^T` is `[|pool| x 256]`, cached exactly as `DESIGN_CARD_POOL.md`:196 caches
`v_card` ("per-decision cost of the card encoder is zero"). Against `COST_MODEL.md`:23, where the
machine's balance point is 458 FLOPs per byte and batch-1 latency is weight bytes over bandwidth:

| | Commander pool | Limited pack |
|---|---|---|
| `M`, candidates | **25,000** (`DESIGN_CARD_POOL.md`:231) | **15** (`DESIGN_TEACHER.md` §4.3:524, up to 14 plus the commander slot) |
| key bytes read, d = 256 bf16 | 12.8 MB | 7.68 kB |
| stage-1 scan at 273 GB/s | **46.9 us** | **28 ns** |
| arithmetic, `2 M d` | 12.8 MFLOP = 0.10 us | 7.7 kFLOP |
| bandwidth : arithmetic | **457 : 1**, matching `COST_MODEL.md`:23 | irrelevant |
| binding constraint | **bandwidth** | **kernel launch**, ~8 us floor (`COST_MODEL.md`:140) |

Two conclusions, and they point opposite ways.

- **Stage 1 never needs approximating.** A full exact scan of the whole Commander-legal pool costs 47
  microseconds. Over the ~103 forwards per deck of §5.3:392 that is 4.8 ms and 1.32 GB of extra
  traffic on top of the 1.57 GB already booked. Amortised over the 65,190 decisions those decks then
  play, it is **20.2 kB per decision against the board encoder's 800 MB, about 0.0025%**. The drafter
  is off the per-decision path entirely (§5.3:401), so this is charged against a budget it barely
  touches.
- **Stage 2 always needs a shortlist.** The 1.64 M-parameter cross-attention rescorer
  (`DESIGN_TEACHER.md` §3.3:425) does per-candidate work, so its cost is linear in `M`. The shortlist
  buys `25,000 / 256 = 98x` **on the rescorer and nothing at all on the scanner.** That is where the
  two-stage structure of `DESIGN_CARD_POOL.md`:204 earns its place, and it is not where anyone
  assumes it is.

**The crossover, and the position.** An HNSW or IVF-PQ query costs roughly 50 to 100 us at these
sizes, near flat in `M`, and returns approximate results. Exact scan is `M x 512 / 273e9` seconds, so
parity sits at `M ~ 2.7e4` to `5.3e4` cards for a single query. Magic has roughly 30,000 oracle cards
(`DESIGN_CARD_POOL.md`:202) and prints 3,000 to 4,000 a year, so on the most ANN-favourable
assumption **we are at parity today and pulling away on three independent axes**:

- **`K = 4` query heads (§12.4) cost one key read, not four.** Four queries against one cached matrix
  is one pass of bandwidth plus `4 x 0.10 us` of arithmetic. An ANN pays per query. Crossover moves
  out by 4x.
- **The filter (§12.5) is free for an exact scan and hostile to an ANN.** Mono-white in Commander is
  roughly 8% of the pool. Filtered approximate search at that selectivity either over-fetches by an
  order of magnitude or falls off a recall cliff, because the graph edges do not respect the filter.
- **An exact scan can assert the Rail L:239 invariant** that zero returned candidates violate the
  mask. An approximate index cannot make that assertion at all.

> **Position: never build an approximate index. The "vector database" is a 12.8 MB tensor plus a
> 3.1 kB bitmask held in the process. Do not add FAISS, hnswlib, or a service.** `ideas.md:162-164`'s
> TurboQuant stays parked, with this arithmetic as the written reason. The instinct about the
> *mechanism* is right; the instinct about the *infrastructure* is wrong, and the second is expensive
> to reverse once training scripts import it.

The falsifier is `SYS-x` in §12.9: if measured `pick_scan_ms` at `|pool| = 25,000` exceeds 1 ms on
the Spark, reopen the question. Not before.

### 12.3 The similarity metric is two decisions, not one

Since `||q - k||^2 = ||q||^2 - 2 q.k + ||k||^2`, the three candidate metrics differ only in how they
treat the card key's norm:

| metric | treats the card norm as | what its argmax means |
|---|---|---|
| inner product | a reward | **"the best card"**: long keys win regardless of direction |
| cosine | noise, discarded | **"the right kind of card"** |
| L2 | a target to match | "as splashy as I asked for, no more and no less" |

In a space trained by a pointer softmax, the key norm absorbs each card's **unconditional pick
prior**. Staples grow long keys. Raw inner product therefore bakes a quality prior into the geometry,
where it is invisible, untunable and unlogged.

**This is not cosmetic, because of §10 Q1.** Q1:645 is this document's most dangerous open question:
the `n_hat` axis may run modal -> bad monotonically, making `N` "a strength slider with a nicer
label". **Raw inner product makes that failure structurally guaranteed**, because in an IP geometry
"unusual direction" and "short key" are correlated by construction, so turning `N` up and turning
quality down are literally the same movement in the metric.

> **Position: split the key. Retrieve on cosine over a direction block, score quality with a separate
> learned scalar, and never let one norm carry both.**

```
k_dir(c)   = normalize(W_dir v_card(c))          # cached, unit norm, the "kind" axis
impact(c)  = w_imp . v_card(c)                   # cached scalar, 257 params, the "quality" axis
score(c|s) = alpha(s) * cos(q_dir(s), k_dir(c))
           + beta(s)  * impact(c)
           + the existing bilinear pointer residual
```

`W_dir` replaces `W_k`, so it is a rename and not a new block. `alpha, beta` come from a 256 -> 2 head
on the deck state, so the model learns for itself when to chase a kind and when to take the strongest
thing available. Keep `log ||W_dir v_card(c)||` as an explicit input feature, so normalisation loses
nothing.

Why it earns its 771 parameters:

- **`N` acts on `q_dir` only.** The intent FiLM of §5.2:374 conditions the direction and must not be
  able to move `beta`. That makes `dn_hat/dT ~ 0` and §9:625's "quality is always maximised
  conditional on `(N, T)`" enforceable **in the geometry**, not only in the calibration of §7.1.
- **`DFT-10 price_of_nicheness` becomes decomposable**: how much of the price was paid in direction
  against how much in impact. Today it is one opaque number.
- **The shortlist stops being pre-biased.** A cosine shortlist retrieves the right *kind* at every
  point of the `N` range. An IP shortlist retrieves staples first and then asks the rescorer to be
  niche among staples, which is the §9:624 trap wearing a hat.

**Reject L2 for retrieval.** Matching the norm would retrieve cards whose unconditional prior equals
the query's magnitude, a semantics nobody asked for. Keep L2 for exactly one job: the invention
residual of §12.7, where "how far away is the nearest real card" is a distance question, not a
ranking question.

This position is falsifiable and must be falsified rather than assumed: `DFT-24` in §12.9 runs
`DFT-10` under cosine-plus-impact against raw inner product. If IP matches, simplify.

### 12.4 Mode averaging: the one failure retrieval genuinely adds

**The failure.** At many picks the right answer is bimodal: cheap interaction **or** a threat, both
fine. A single query trained by softmax MLE lands between the modes. With an explicit candidate set
and a softmax over all of it that is survivable, because both modes are still scored. **With a query
plus a top-k cut it is not**, because cards sitting near the midpoint outrank both modes and fill the
shortlist with things that are neither.

**How much risk.** Let the modes be unit directions separated by `2 theta` about a midpoint `m`. Any
card within angular radius `theta` of `m` beats both modes under cosine. The fraction of a
`d_eff`-dimensional sphere inside that cap is about `sin(theta)^(d_eff - 1)`, where `d_eff` is the
**effective dimensionality** of the cached key matrix, `(sum lambda_i)^2 / sum lambda_i^2` over its
PCA spectrum. At `d_eff = 16` over a 25,000-card pool:

| mode separation `2 theta` | expected decoys beating both modes |
|---|---|
| 30 deg | ~0.00004 |
| 60 deg | **0.8** |
| 90 deg | **138** |
| 120 deg | **2,893** |

Near-synonym modes are safe. **The risk explodes past roughly 80 to 90 degrees of separation, which
is exactly the removal-versus-threat case the concern is about.** At 120 degrees a 256-card shortlist
is composed entirely of decoys and the correct card is never rescored. The failure is silent: the
rescorer only ever sees what retrieval handed it, and `pi` looks confident.

`d_eff` is the parameter this whole estimate hangs on, and it is currently unknown. **Measure it
before building anything on top of it**: one SVD of a `[25,000 x 256]` tensor, seconds, zero games,
at stage 3.

**The three candidate fixes.**

| fix | verdict |
|---|---|
| **sample the query** | **Refused, and not on this section's authority.** `DECISIONS.md` D16:274 and §4.3:277 already set per-pick temperature to exactly zero, and §9:624 deletes the per-pick temperature slider by name. Sampling the query is that slider in a different costume, and it re-opens the compounding problem of §4.1:262 over ~100 picks |
| **shortlist, then rescore exactly** | **Necessary, insufficient.** It is already the design. It fixes precision, not recall: a mode-averaged query's shortlist does not contain the missing mode, so exact rescoring cannot recover it |
| **emit `k` queries** | **Recommended** |

> **Recommendation: `K = 4` query heads, union their top-64 into one shortlist of up to 256, then
> rescore exactly with the existing cross-attention pointer. Deterministic end to end.**

- **The failure is a recall failure, and recall is what extra queries buy.** The union is a superset
  of the single-head shortlist, so `K > 1` is weakly dominant on quality by construction. There is no
  accuracy trade-off to argue about.
- **It costs almost nothing.** `W_q` is one 256x256 map, so four heads is **+0.20 M parameters**
  against §5.2's +0.45 M and the teacher's 7.2 M. Scan cost is **unchanged at 46.9 us**, because four
  queries read the same cached `K` once and add 0.3 us of arithmetic.
- **No new loss term.** The heads need no diversity objective and no EM responsibility assignment.
  The rescorer supplies the gradient, and heads that duplicate each other merely waste capacity,
  which the diagnostic below detects.
- **It makes the multimodality visible.** Four labelled intents per pick is a far better spectator
  artefact than one averaged one: *"it was weighing cheap removal against a four-drop threat."*

**The falsifier for `K > 1` is mandatory:** `DFT-20 mode_gap`, the share of picks whose final winner
was retrieved by a head other than head 0. The null and the single-head ablation both score exactly 0
by construction. If `mode_gap` stays near zero across a checkpoint, `K = 4` is dead weight and drops
to 1. If it is materially positive, single-query retrieval was silently losing those picks. Free,
zero games.

**One trap the shortlist creates.** `DESIGN_TEACHER.md` §4.3:507 defines `pi` as a softmax over the
candidate set. Truncating to 256 makes that a softmax over a **query-dependent** set, so entropy and
`top1_margin` stop being comparable across picks. Because default `T = 0` the argmax is unaffected
*provided recall holds*, and recall is exactly `DFT-19`. So: log the shortlist size and the truncated
probability mass on every `E-DRAFT` record, and never compare entropies across picks with different
shortlist sizes without saying so.

### 12.5 Set and pool filtering falls out as mask algebra

The owner asks to filter by set when drafting. `DESIGN_TEACHER.md` §4.4:530 already writes the mask,
and retrieval changes nothing about it except making the implementation obvious: **the mask is
applied to the scores, not to the index.** One `[25,000]` boolean, additive `-inf`, 3.1 kB,
microseconds. The index is never rebuilt, never sharded per filter, never re-indexed when a set is
toggled.

> **Position: add `set_in_scope BOOLEAN` as a third independent flag beside `format_legal` and
> `engine_supported` (`DESIGN_CARD_POOL.md`:210). Never fold set selection into `format_legal`.**

`format_legal` is external truth from MTGJSON legalities. `set_in_scope` is a training-time or user
choice. Conflating them destroys the ability to tell *"this card is banned"* from *"we chose not to
draft this set"*, which is precisely the coverage instrumentation `DESIGN_CARD_POOL.md`:220 says the
project has never had, and it is what makes §12.7's unmet-need map actionable rather than
decorative. It is also a bug fix: `DESIGN_CARD_POOL.md`:216 records that `cards.set_code` exists and
**no query filters on it**, with the config's card-subset setting dead and pointing at a set that is
not in the database.

| constraint | implementation | cost |
|---|---|---|
| **colour identity** | static bitset per identity bucket, 32 in the full pool (`DESIGN_TEACHER.md` §4.4:539), precomputed once | one AND |
| **singleton** | dynamic bitset over already-picked oracle ids, one bit flipped per pick | one AND |
| **set scope** | static bitset per set, OR-composed for a multi-set request | one OR, one AND |
| **commander eligibility (pick 0)** | static bitset from `leadershipSkills.commander` | one AND |
| **forced includes, the user's prefix** | prefix tokens, not a mask (§3.2:201) | zero |

These are rules of Magic, and `NORTH_STAR.md` §3:109 is explicit that rules are hardcoded precisely.
Masking, never penalty: `DESIGN_TEACHER.md` §4.4:542's refusal of the recovered document's
illegal-state penalty stands unchanged. **Invariant, per Rail L:239, not a scored metric:** the count
of returned candidates violating the mask is **exactly 0**, asserted every pick, logged in `E-SLATE`
with the masked-out set and its reason, as §4.4:538 already requires.

**Same index, in-game.** `DESIGN_CARD_POOL.md`:184 specifies `retrieve_topk(query(board, belief),
legal_pool)` at `k = 64..256`, refreshed **once per turn, not per decision** (:188). Same `K` tensor,
same masks, different query source. The numbers make that a hard contract rather than a preference:

- **per turn**: ~100 refreshes per Commander game x 12.8 MB = 1.28 GB over 65,190 decisions =
  **19.6 kB per decision against 800 MB, 0.0025%**;
- **per decision**: 12.8 MB against 800 MB = **1.6%, a 650x regression**.

Survivable, but ruinous relative to the alternative. Log the refresh count in `SYS`.
`DESIGN_CARD_POOL.md`:187's rule holds unchanged: pool tokens are keys and values only, never
queries.

**§5.1 gains a row.** `K`, the cached key matrix, is the fourth object the teacher, the drafter and
in-game pool conditioning share, at **0 marginal parameters**. It is the concrete form of "one
network used twice".

### 12.6 What a pre-candidate query buys, which a pointer does not

A query emitted *before* the candidate set is seen is a statement of intent that exists independently
of what happened to be available. The pointer framing can only produce a ranking over what was there,
and so cannot express *"it wanted cheap interaction and there was none."* Five uses, in increasing
order of product value.

1. **Nearest-neighbour readout.** Print the top-10 cards by `cos(q_dir, k_dir)` with scores, per
   head. Free, already computed, and it makes every pick an inspectable event.
2. **Atom decoding, without a text decoder.** Because `v_card` is composed from a typed tree over a
   **closed** vocabulary (`DESIGN_CARD_POOL.md`:76: roughly 60 verbs, 40 filter predicates, 10
   combinators), train ~110 linear probes `q_dir -> P(atom present in the picked card)`. That is
   `110 x 256 + 110 = 28,270` parameters, supervised for free off the random-prefix objective of
   `DESIGN_TEACHER.md` §4.5:567. Output: *"wants `DESTROY`, `Selector{mode:TARGET,
   filter:{type:creature}}`, instant, mana value <= 3."* This is the cheap and honest version of
   "decode the query toward an ability tree", and it is a prerequisite for §12.8 in any case.
3. **The residual as a first-class quantity.** `1 - max_c cos(q_dir, k_dir(c))` after masking. Small
   means the pool answered the intent, large means it did not. One float (§12.7).
4. **The spectator, per `NORTH_STAR.md` §4:120** ("can the owner *see* the effect"). Per pick: four
   intent atom bar charts, the shortlist with scores and which head supplied each entry, the mask
   reasons from `E-SLATE`, the chosen card, the residual. The current alternative is a card name.
5. **Explaining a pick to a human.** `DESIGN_TEACHER.md` §4.6:576's leave-one-out sweep gives a *post
   hoc counterfactual*: "the deck is worse without X." The query gives an *ex ante intent*: "at pick
   34 I was looking for cheap white interaction; the best available scored 0.91, the second 0.89, and
   nothing in the pool matched the second head's ask at all." Those are different explanations, and
   the second is the one a player asks for. It is also the missing mechanism under `BACKLOG.md:80`'s
   Stockfish-style top-3 suggestion.

**Do not ship a readout that has not passed its own falsifier.** `DFT-22 query_pick_agreement` is
top-1 agreement between the stage-1 head-0 argmax and the final rescored pick, **restricted to picks
where the unconditional prior's argmax differs**. Unrestricted agreement is `METRICS.md` §17:844's
trap verbatim: a constant query agrees often, because it picks staples and so does the rescorer. The
restriction makes the null exactly 0 by construction. Below the null, the query is decoration and the
spectator panel is lying to the owner.

### 12.7 The unmet-need map

Per pick, over the masked enabled pool:

```
unmet_need(s) = 1 - max_{c : legal(c|s)} cos( q_dir(s), k_dir(c) )
```

Aggregate over many drafts, bucketed by `(colour identity, mana value bucket, top-3 decoded atoms)`
and weighted by how often each bucket is queried. That is a map of what the pool does not contain. It
is one float per pick plus the query vector, and it needs no new machinery at all.

**Split it by the flags of §12.5, which is where it stops being a curiosity:**

| bucket | meaning | action |
|---|---|---|
| high need, no card at all | Magic has not printed this | a genuine design gap, and the only bucket where invention is even the question |
| high need, best match has `engine_supported = false` | **the card exists, our compiler cannot compile it** | a **demand-ranked worklist for the unparsed queue** (`DESIGN_CARD_POOL.md`:226) |
| high need, best match has `format_legal = false` | banned, or out of format | not actionable |
| high need, best match has `set_in_scope = false` | outside the requested sets | the honest answer to "what is this set restriction costing me" |

The second row is a real King-Goal contribution: it turns "which primitive do we implement next" from
a judgement call into a queue priced in decks that wanted it. `DESIGN_CARD_POOL.md`:268 asks for
coverage instrumentation from day one, and this is its demand side.

**And this metric is a §17 trap of exactly the kind Rail B:82 exists for.**

| | raw `unmet_need` | why |
|---|---|---|
| null drafter (constant query) | one fixed value, no map | it asks the same question every pick |
| **uniform-random query** | **near maximal everywhere** | a random direction in high `d` has `cos ~ 0` with every card |
| working drafter | small in dense regions, large in genuine gaps | the map has structure |

An **untrained** query head maximises this metric. So `DFT-23` is published **only** as the difference
against a shuffled-pool permutation control, and only once `DFT-22` has cleared its null. Under that
normalisation the null scores 0 and random scores 0, and a raw number is inadmissible on its own.
This is `METRICS.md` §17:863's rule applied before the metric exists rather than after it embarrasses
someone.

### 12.8 "Invent new cards in the gaps": the honest verdict

**The strong property, stated because it is genuinely strong.** Real invention means decoding an
embedding back into an ability tree, the inverse of `DESIGN_CARD_POOL.md` steps 1 to 2. What makes
that more than a party trick:

> **A tree decoded under the grammar, with type checking at each production, is EXECUTABLE by
> construction.** `DESIGN_CARD_POOL.md`:9 commits to one representation that is simultaneously the
> only thing the engine executes and the only thing the network reads. So any well-typed tree the
> decoder emits **runs**. An invented card would be playable, not merely describable.

Constrained decoding also makes validity free by masking rather than by penalty, the same argument as
§12.5 and the same refusal as `DESIGN_TEACHER.md` §4.4:542. It is strictly stronger than any
text-generation approach: an LLM-written card is a wish, a grammar-decoded tree is a card. That is the
single most interesting property in this section, and it is why invention is **parked rather than
abandoned**.

**The three problems, bluntly.**

1. **Balance is a different problem from legality, and far harder.** Executable says it runs. It says
   nothing about the mana cost being right. The unconstrained argmax over tree space is *"0 mana: you
   win the game"*, and constraining it requires a cost model over trees, which is the hardest open
   problem in Magic design and which Wizards solves by playtesting rather than with a critic. We have
   no cost model and no plan for one.
2. **The critic is badly miscalibrated off distribution, and this is fatal on its own.** `Phi_wr` is
   fit on ~10^4 noisy deck labels over **real** cards (§5.2:384, §5.5:425). An invented card is by construction
   the argmax of `Phi` over a region `Phi` never saw. That is not evaluation, it is
   adversarial-example generation against our own value function. §5.5:428 already names the starved
   estimator as `p_ref`'s tail, and invention lives past the end of that tail. `DESIGN_TEACHER.md`
   §8:862 prices the general shape of this failure at 0.566 nuisance payout, and `DECISIONS.md`
   R8:420 is the same circularity one step less severe. **It will look like it is working.** The
   invented card will score beautifully and mean nothing, and no instrument in `METRICS.md` can tell.
3. **It does not serve the King Goal.** `NORTH_STAR.md` §0:10 is "genuinely strong on the sets it has
   been trained on". Invented cards are in no pool anyone plays, and training on them risks the
   tied-rank-1 auto-extension goal directly, by filling the training distribution with cards whose
   statistics are the critic's blind spots. The one steelman is data augmentation for the
   compositional encoder, a card built from known primitives that was never printed being exactly the
   tied-rank-1 test case. But `DESIGN_CARD_POOL.md`:262 already specifies a **better** version of
   that test, holding out *real* cards, which has ground truth about what the card does and real
   decks that play it. The augmentation argument does not survive contact with the test already
   planned.

> **Verdict: PARK the generator, BUILD the residual map.** Per `NORTH_STAR.md` §2:69, this goes to
> the backlog **with the reason written down**, not into the design.

Parked: the grammar decoder, any balance model, any training on invented cards, any product surface
that shows a generated card. **The cheap piece that must not be lost, and it has to happen at stage 0
or it is unrecoverable:**

> **Log `q_dir(s)` for all `K` heads, the shortlist ids and scores, the truncated probability mass,
> and the residual, in the `E-DRAFT` event.**

`DESIGN_TEACHER.md` §4.7:607 records that `E-DRAFT` **does not exist in the catalogue at all**, so it
is being specified now and this is the moment to specify it correctly. Cost: `4 x 256` bf16 plus 256
ids and scores per pick, about 3.6 kB per pick and 360 kB per deck built. Keep only the top-32 of the
shortlist if even that matters.

The urgency is not aesthetic. It is the identical failure to `student.py:131` computing the full
probability vector and `:138` keeping only the scalar `log_prob`, which `METRICS.md` `DFT-3` records
as making no confidence, entropy, PR-AUC, F1 or calibration metric recoverable post hoc. If the query
is not logged, §12.6 and §12.7 are unreachable retrospectively and every draft ever run has to be
re-run. Log it before anything reads it.

### 12.9 Register rows, per `METRICS.md` §17:827

All rows extend family DFT, continuing §7.2's table, which ends at `DFT-18`. `M_null` is the
unconditional decoder of §6.1, measured in the same episode on the same RNG stream (Rail B:82).
`M_random` is the permanent uniform-random-legal outgroup of `DESIGN_TEACHER.md` §2.5:291.

| ID | metric | null (ignores the knobs) | uniform random legal | mandatory pairing |
|---|---|---|---|---|
| **`DFT-19`** | `shortlist_recall@k`: P(the final rescored winner is in the stage-1 union shortlist), **restricted to picks where the winner is not in the pool's unconditional top-256** | high unrestricted, **0 on the restriction** | `k/\|pool\|` = **1.0%** at k = 256, M = 25,000 | never report unrestricted; the restriction **is** the metric. Publish with `DFT-20` |
| **`DFT-20`** | `mode_gap`: share of picks whose winner came from a head other than head 0 | 0 | ~0 | **the falsifier for `K > 1`.** The single-head ablation scores 0 by construction. Publish with `DFT-19` |
| **`DFT-21`** | `intent_atom_lift`: PR-lift of the ~110 linear atom probes against the picked card's actual atom set, macro-averaged | equals the atom base rate, **lift 0** | lift 0 | report `PR_lift`, never raw PR-AUC (§17:842) |
| **`DFT-22`** | `query_pick_agreement \| non-prior`: stage-1 head-0 argmax against the final pick, restricted as in `DFT-19` | **0 by construction** | ~0 | gates `DFT-23`. Below the null the §12.6 spectator readout does not ship. The unrestricted version is §17:844's trap verbatim |
| **`DFT-23`** | `unmet_need_map`: the residual, normalised against a shuffled-pool permutation control, bucketed and split by the four flags of §12.7 | 0 | **maximal raw, 0 normalised** | **inadmissible raw.** Gated on `DFT-22`. Publish the `engine_supported = false` slice as the compiler worklist |
| **`DFT-24`** | `metric_ablation`: `DFT-10 price_of_nicheness` under cosine-plus-impact against raw inner product | - | - | how §12.3's position gets falsified rather than asserted. If IP matches, simplify |
| **`SYS-x`** | `pick_scan_ms` and `pool_refresh_count_per_game`, measured on the Spark | - | - | falsifies §12.2. If exact scan at `\|pool\| = 25,000` exceeds 1 ms **measured**, reopen the ANN question. Not before |
| **invariant** (Rail L:239) | mask violations among returned candidates | **exactly 0**, asserted every pick | 0 | not a scored metric. An approximate index cannot assert it; an exact one cannot fail it |

Also publish **`d_eff`** (§12.4) at every encoder version bump, with a Rail H:190 epoch stamp. It is
the parameter the whole §12.4 risk estimate rests on, and it is one SVD.

**Budget, against Rail I:207.** `DFT-19` through `DFT-23` all ride the 750-deck calibration run of
§7.6:591, about 4 minutes per checkpoint at **zero games**. `DFT-24` doubles that run. Nothing here
books a game.

### 12.10 Staging, and what §5.2 and §8 become

| stage | deliverable | games |
|---|---|---|
| **0** (constraint filter) | **`set_in_scope` as the third flag** beside `format_legal` / `engine_supported`; **the `E-DRAFT` event specified to carry `query_vector[K]`, `shortlist_ids`, `shortlist_scores`, `truncated_mass`, `residual`, `mask_reason`** (it does not exist yet, so specify it right); register rows `DFT-19..24` written before anything is built (Rails F:169, J:217); the bitset representation for the four masks | **zero** |
| **1** (gamma experiment) | **nothing.** Reserve the `E-DRAFT` fields | zero |
| **2** (league, outgroup) | the uniform-random-legal outgroup becomes the external null for `DFT-19..23` as well | none marginal |
| **3** (archive plus critic) | cache `K = V W_dir^T` and the `impact` scalar as one tensor the moment a `v_card` exists, interim vector included (`DESIGN_TEACHER.md` §7 stage 0 already de-risks this). **Measure `d_eff`.** Train the 110 atom probes off the random-prefix objective. `DFT-21` computable | zero marginal |
| **4** (pick head) | **this is where query-then-retrieve *is* the pick head.** `K = 4` query heads (+0.20 M), the cosine/impact split (+771), the union shortlist, exact rescore. `DFT-19`, `DFT-20`, `DFT-22`, `DFT-24` run here, free. The split lands here because it interacts with the intent FiLM of §5.2:374 | zero |
| **5** (products) | set filtering exposed as a product control; the spectator query panel; the Limited pack as the identical code path at `M = 15`; `DFT-23`'s map published | ~300 to 600, already booked in §8 |
| **parked** | the grammar decoder and card invention (§12.8); any ANN or vector-DB dependency; `ideas.md:162` TurboQuant | - |

**§5.2's arithmetic, revised.** Four query heads **+0.20 M**; the atom probes **+0.03 M**; the impact
head and the `alpha, beta` gate **+771**. `W_dir` renames `W_k` and adds nothing. Against §5.2's
+0.45 M the drafter's new total is **+0.68 M**, and the combined system moves from ~7.6 M to
**~7.9 M, 15.7 MB in bf16**, still entirely off the per-decision path.

**What must survive from this section.** *The pointer head and vector retrieval are one operator, and
retrieval is its scalable implementation. The index is exact, in-process and masked, never
approximate.* Everything else here is replaceable. The two choices that are not merely
implementation, because they decide whether §10 Q1's failure is structurally guaranteed or merely
possible, are **cosine for kind with a separate scalar for quality**, and **more than one query so
that a bimodal pick is not silently averaged away**. Both are falsifiable at zero games, by `DFT-24`
and `DFT-20` respectively, and both should be settled by those numbers rather than by this document.
