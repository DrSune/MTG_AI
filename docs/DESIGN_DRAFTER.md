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
