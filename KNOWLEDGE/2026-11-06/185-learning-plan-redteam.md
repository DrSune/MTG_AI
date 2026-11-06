# 185 — Red team of the learning plan v1 (2026-11-06)

A fresh agent attacked plan v1 (the core: per-decision playout comparison, DECISIONS D20) before
any code. Its blockers and majors were fixed in plan v3 (docs/PLAN_LEARNING.md, change log). Kept as
the evidence behind those changes.

# Red team of plan v1 (Student, opponent simulator, memory, Teacher)

2026-11-06. A fresh-context review; I did not write the plan.

**What I read.** PLAN.md; docs/OWNER_VISION_LEARNING.md (including today's D20 note);
KNOWLEDGE/OWNER_PREFERENCES.md; NORTH_STAR.md; DECISIONS D6, D14, D15, D16 and D20, plus R3 and R8;
184 §15-26 and 183 §2-28.

I read the code at the lines the plan cites, and around them:
- tools/selfplay: search.py, model.py, features.py, ppo.py, rig.py, actor.py, the serving loop in
  learner.py;
- tools/search/fork.py;
- MTG_bot/bench/view.py;
- in games.py: the deal, coherent decks and mulligans; legality.spell_record;
- docs/DESIGN_LATENCY.md §1.

I also checked the cited papers in the PDFs already in the scratchpad: [26] 2511.07312, [28]
2304.13138, [29] 2605.14379, [27] 2502.08938, LBS 2106.09086 and [13] 1812.06162.

## 0. What I ran (OWNER_PREFERENCES #3)

The scripts are in `plan_v1/rt_work/` (scratch only, not for the repo):
- `fork_bench.py`, `crn_bench.py` and `crn_bench2.py`, analysed by `crn_analyse.py` and
  `crn2_analyse.py`;
- `gpu_bench.py`.

The setup was the working tree, the M21 verified pool and coherent decks, with the heuristic on
both seats standing in for the network. **No network playouts were run**, so the variances below
are a proxy. The machine was idle (no training run; 90 GB available), and everything ran at nice
15.

| Quantity | Measured |
|---|---|
| fork / determinize / `features.encode` | 5.9-6.2 ms / 0.05-0.11 ms / 0.10 ms per decision |
| playout from turn 5-7 to the end | mean 47.5-55 decisions (median 44-49, max 135). 0.15-0.18 s in one process (3.3-3.7 ms per decision, fork included); 0.22-0.27 s with 16 processes at once, so the CPU ceiling is about 2,800-3,400 decisions/s |
| r20 v2 forward pass, bf16, GB10 | 27.2M parameters, 25.2M of them in the d512 L8 encoder; a mean of 27 tokens per decision. 6.1 ms per 64 decisions (10.5k/s), 15.0 ms per 128 (8.5k/s), 29.1 ms per 256 (8.8k/s) |
| public sampler (`search.py:63`) on 12 coherent deals, turn 7 | the opponent's hidden cards are **6-10% lands (true 37-40%)**, and **54-61% of its non-lands are outside its colours (true 0%)** |
| what that does to playout values (32 positions, turns 5-12, 12 futures, deterministic play) | the searching seat's mean result: **+0.68** with the public sampler, +0.14 with the true cards (libraries reshuffled), +0.15 with a deck-generator prior. The value of playing the turn against passing it: **+0.17** / +0.31 / +0.30. Sign agreement with the true-card comparison on the 14 clear positions: **8/14** / - / 11/14 |
| common random numbers (CRN): correlation of two alternatives' results over shared futures | **0.94-0.96** with deterministic playouts; **0.58-0.72** with 10% random moves whose seed is shared per future; **0.40-0.45** when that seed is not shared. Var(zA - zB) per future: 0.03-0.08 / 0.22-0.51 / 0.37-0.79. So the standard error (SE) of a Q difference at d = 8 is **0.06-0.10 / 0.16-0.25 / 0.21-0.32**, in ±1 outcome units |
| ties | with a weak alternative (pass the first main phase), **29 of 32** positions had exactly zero effect under deterministic playouts |
| crashes / draws | 0 crashes in about 9,300 playouts; 2 draws |

## Verdict

**The core idea is sound as an estimator.** The design compares alternatives on shared futures,
plays them to the end of the game, and makes every later move with the policy reading its own
masked view. That gives an improvement direction with full credit and no strategy fusion. §2.1's
answer on luck is also correct: averaging over futures the player cannot tell apart teaches it to
play to its outs.

**As written, the plan's first experiments would test something else.** Three design errors cause
this:
- the sampler gives the opponent in the futures a crippled hand (B1);
- the target turns playout noise into confident labels (B2);
- the opponent's private state leaks into the labels (B3).

**The plan states its efficiency case without the arithmetic** (M1). With the CRN variances
measured above, labels come out at roughly 0.3-5x outcome PPO's gradient signal per forward pass,
not the ≥ 10x that E1 requires. E1 can settle the question, but only if it is measured on the same
footing for both methods, and only once B2 is fixed (as written, the E1 gate can pass on a biased
target).

Fixing B1-B3 is about a day of plan edits plus roughly 60-100 lines of code before E1. After that,
and with E1-E3's gates rewritten (M1, M4), the plan is ready to take to the owner. M3 (self-play or
mixture inside playouts), M5 (the Commander path) and the D6/D14 amendments should go to him with
it.

---

## BLOCKERS

### B1. E1 and E3 would measure an expert playing against a crippled opponent

**Evidence.**
- PLAN §2.1 step 1 and §7 E1 take futures from "today's public-information sampler
  (`search.py:63`)".
- `search.py:72-79` redraws every card in the opponent's hand and library uniformly from
  `supply.deckable`. Its own docstring says: "coherent two-colour decks are sampled as five-colour
  piles".
- Training has dealt only coherent decks since r21: 24 basic lands in 60, two colours
  (`games.py:1648-1684`).

In the measured futures, the opponent holds 6-10% lands instead of 37-40%, and most of its spells
are off-colour. It can neither make land drops nor cast most of its hand. The consequences, all
measured:
- the searching seat's playout value inflates from +0.14 to +0.68;
- the measured value of developing rather than passing a turn falls from 0.31 to 0.17;
- the sign of that comparison disagrees with the true-card comparison on 6 of 14 clear positions,
  against 3 of 14 for a generator-consistent prior.

A search scored against this opponent learns to ignore interaction. E1's +0.04 gate and E3's labels
would test that search, so a kill would be the sampler's fault, not the idea's.

**Fix (before E1, about 30 lines).** Sample consistently with the deck generator:
1. Draw the opponent's colour pair from the pairs consistent with its public cards.
2. Build a deck with `build_coherent_deck`'s composition: 24 basics split between the two colours,
   at most `MAX_COPIES` of each spell.
3. Remove the opponent's public cards and any cards the searcher legitimately knows about.
4. Deal the hand and library from what remains.
5. Shuffle the searcher's own library except its known positions (m4).

I prototyped this as `resample_coherent` in `rt_work/crn_bench.py` (25 lines). It reproduces the
true-card control: a level of +0.15 against +0.14, and a ΔQ of +0.30 against +0.31. Keep it
permanently as the prior that the belief model later reweights (M7), so the sampler is built once.

### B2. The target formula turns playout noise into confident labels

**Evidence.**
- §2.1 step 4 uses Gumbel MuZero's pi' = softmax(logits + σ(completed Q)) [14]. In [14], and in
  its reference implementation (mctx `qtransform_completed_by_mix_value`), completed Q is rescaled
  to [0, 1] by min and max at each decision, then multiplied by (c_visit + max N)·c_scale. At d = 8
  that is 5.8 to 58 nats between the best and worst alternative.
- When alternatives tie, the rescaling stretches pure noise to the full range. Ties are common:
  29 of 32 positions above, and half of the search's changes in /183 §16 (median margin 0.021).
- With sampled playouts, the measured SE of a Q difference at d = 8 is 0.16-0.32. A tie then flips
  a policy at 0.9 to about 0.03 on noise alone (logits −2.3 + 5.8 against −0.1). This is /183
  §14-16's failure (labels that would not generalise) rebuilt into the target.
- Ataraxos's own ablation (Extended Data Table 1 of [26]): with the KL term to the network, search
  rated 2218 Elo; without it, 1733, below the raw network's 2095, because "the search overfits to
  idiosyncrasies of the move network".
- Completing unvisited actions with v_mix also brings the value head into the target. It is a small
  bootstrap, but it is one the ruling excludes.

**Fix.**
- Use the MMD step from [28] directly, with no rescaling:
  pi' ∝ [pi·exp(η·Q̂)·ρ^(ηα)]^(1/(1+ηα)), with Q̂ in outcome units.
- Unvisited actions keep their prior ratios (no v_mix).
- Choose a fixed η such that a one-SE error moves log-odds by at most about 0.5 (η ≈ 2-3 at SE
  ≈ 0.2). Log each label's SE, estimated from its d paired futures. Anneal η together with the
  magnet, as [26] does.
- At small η the label is linear in Q̂, so noise averages out across labels instead of being
  amplified.
- Add a placebo: rerun the gradient test with Q̂ shuffled across the alternatives of each label. A
  biased target shows "signal" even then.

### B3. Hidden information reaches the labels through the opponent's private state in playouts

**Evidence.**
- `fork` deep-copies the journal and the ledgers (`fork.py:13-14`). `determinize` swaps card
  identities only (`search.py:73-79`), so every handle keeps its true history.
- §3.2 gives each seat "its own hand cards" exact age.
- In a playout, a network plays the opponent's seat while reading its own hand: the identities are
  sampled, but the ages are the true ones. Which cards the opponent has held since when is exactly
  what §3.2 says is not public; only the lower bounds A[n] are.
- So the opponent's behaviour in the playout depends on the true hidden state, and Q(a) and pi'
  depend on it with it. §2.1's "nothing is clairvoyant" and D20 guard 1 both fail.
- The same channel opens:
  - for the stage-3 GRU: copying the opponent's carried state leaks, and resetting it shifts the
    distribution;
  - for any ledger entry stored as an identity rather than a handle;
  - for an "own library bag" computed from the deck list rather than from the zone.
- The planned metamorphic test (§3.5: "rewrite the opponent's hand and both libraries") would not
  catch any of this, because it never changes the private history.

**Fix (small; it must be in place before any new input reaches a playout).**
1. Encode only public hand-age information for both seats. Drop own exact ages: a player needs its
   own ages only to model what the opponent can infer, and that is public.
2. The ledger and the library bag store handles and read zones. They never read identities
   captured at event time, and never the deck list.
3. Define the opponent's private information state: hand identities with their ages, its library,
   its own scry and tutor knowledge, and any carried state. Resample all of it in `determinize`,
   consistent with the public counts.
4. Extend the metamorphic test to the label itself. With a fixed search seed, rewriting the
   opponent's hidden cards, which hand card entered when, and its private knowledge must leave
   (Q, pi') byte-identical. Run it on the E1 labeller too.

---

## MAJOR

### M1. The efficiency premise is unquantified, and E1's second gate can pass on a biased target

**Evidence.** §0 asserts that decision-level duplicates beat outcome credit, and D20 was approved on
"~100k labels a day". But one label costs k·d·L ≈ 4·8·47 ≈ 1,500 forward passes. Per forward pass,
the comparison with outcome PPO works out as follows.

**Outcome PPO.**
- Var(z − V) is about 0.7 mid-game (184 §26).
- About 18 decisions per game carry signal, at about 90 forwards per game: about 5 forwards per
  useful sample.

**One label, at a binary decision with p = 0.8.** With all alternatives evaluated under CRN, its
noise relative to one PPO sample is

  p(1−p)·Var_diff / (d·Var(z−V)) = 0.16 · 0.4 / (8 · 0.7) ≈ 1/88.

The expected gradient is the same for both methods.

**Net.**
- With sampled playouts: 88 · 5 / 750 ≈ 0.6x at k = 2, and about 0.3x at k = 4.
- With deterministic playouts (Var_diff ≈ 0.07): about 2-3x.
- Folding in what this ignores (PPO's action-sampling noise, and choosing labels at high-|A|
  decisions), the range is about 0.3-5x. That is not the ≥ 10x E1 demands.

**What follows.**
- **The d sweep is at the wrong end.** With a linear target, noise falls as 1/d while cost rises
  as d, so compute per useful step is lowest at the smallest d. E1 sweeps {4, 8, 16}, and the
  plan's reason for rejecting d = 2-4 is an artefact of B2's nonlinear target.
- **The gate compares unlike losses.** E1 compares B_simple across two different losses. For
  distillation, B_simple falls as η grows, because |G| grows the further pi' sits from pi. So B2's
  target passes the gate more easily the more it amplifies noise.
- **"≥ B* per step" is about steps, not correctness.** In McCandlish's analysis [13] the critical
  batch trades optimizer steps against samples. A supervised loss trained below it is more
  sample-efficient, not wrong.

**Fix.**
- In E1, put the linearised label gradient, Σ_a pi(a)(Q̂(a) − Q̄)∇log pi(a), and PPO's gradient
  through the same split-gradient instrument, normalised per forward pass, together with B2's
  placebo.
- Sweep (k, d) over {(2,1), (2,2), (4,2), (4,8)}, each with greedy and with sampled playouts.
- Tell the owner now that E1 has a real chance of triggering its kill.
- Keep the ≥ B* rule for the outcome policy-gradient loss only.

### M2. Luck cancels only in greedy playouts, which change what Q means

**Evidence.**
- §2.1 says Q(a) − Q(b) "carries no ... luck". Measured, the correlation is 0.94-0.96 with
  deterministic playouts, 0.58-0.72 with seeded random moves and 0.40-0.45 unseeded.
- Once two alternatives diverge, the engine's own randomness decorrelates as well:
  sha256(master_seed:op_seq:tag) (`search.py:68-70`), and op_seq differs between branches.
- Today's `SimAgent` plays greedily (`search.py:83`; the greedy flag is True at `search.py:121`),
  and §8 reuses "the existing searcher". Greedy playouts estimate the value of the greedy policy.
- §2.1 step 4 and [28] need returns sampled from pi itself: in [28], Algorithm 1 draws them from
  P_π.

**Fix.** Choose explicitly, and measure both options in E1:
- **(a) Sampled playouts**, seeded per (future, decision index) and shared across alternatives.
  This keeps the citation and costs about 3-6x more label noise.
- **(b) Greedy playouts.** These have lower noise and improve on the greedy policy that gates and
  deployment actually play, but the MMD and update-equivalence claim is then dropped.

### M3. The citations do not support the configuration they are cited for

**Evidence.**
1. **Rollouts.** [28] samples histories and returns under the joint blueprint policy. Ataraxos
   [26] rolls out "using its move network to simulate both players", with a belief network that
   "approximates the posterior distribution of the self-play policy", and notes that "these
   averaged values approximate self-play action values regardless of the policy of the opponent".
   §2.1 step 3 instead plays the other seat with "the real opponent or the league mixture", and D20
   guard 3 says "a mix". That is a best response to a mixture, not an MMD step on the game, so
   §2.5's convergence argument does not apply.
2. **What Ataraxos is.** It trains by self-play RL with λ-returns ("distinct λ values"; Monte Carlo
   returns only for setups). It searches only at test time, with 40-ply rollouts scored by the
   value network, and never distils search into the network. "The pattern behind Ataraxos's
   superhuman Stratego" misdescribes it to an owner who has just ruled on λ. Its search uses the
   very value leaf that §2.2 rules out.
3. **LBS.** Its 4.6-36x saving comes partly from partial rollouts that bootstrap from a value
   function (2106.09086 §1).
4. **Hearthstone.** Bursztein's > 95% prediction leaned on meta decks. The decks dealt here are
   uniform samples (M7).
5. **Small errors.**
   - [13] gives Dota 5v5 as "at least 10 million", not 24M.
   - AlphaZero bounds staleness with a window of games, not "~20 minutes".
   - Its ~5e4 possible opponent hands per known 60-card list (§3.4) is low: 7-card multisets of
     about 20 card types number 10^5-10^6. The conclusion stands either way.

**Fix.**
- State what is borrowed and what is new. Distilling an MMD step computed from full playouts is not
  demonstrated in any of the cited papers at this scale.
- Then choose one of two ways:
  - **Self-play rollouts.** Play the Student on both seats. This keeps [28]; the league then decides
    only which states are visited.
  - **Mixture rollouts.** Drop the MMD claim and rely on PFSP plus the exploiter for robustness.
- Amend D20 guard 3 to match.

### M4. The gates cannot discriminate the effects they are meant to detect

**Basis.** A pair mean has 0.15 of one game's variance (184 §26), so the SE is 0.011 at 300 pairs.

**E1.**
- Passing needs a point estimate of at least +0.04. If the true gain is +0.04 it passes 50% of the
  time; at +0.05, 81%.
- At a true +0.03, about 63% of outcomes fall between +0.02 and +0.04, where no rule applies.
- Picking the best of three d values adds about +0.01 of winner's curse.

**E3.**
- "+0.03 with lower bound > 0" passes 50% of the time at a true +0.03.
- Its other metric, agreement "on the moves search changed", is the one /183 §16 found biased
  toward the network that generated the labels, and changed labels are enriched for noise.

**E2.**
- Its "no-history belief" baseline is undefined. Against today's pool sampler a 25% gain is
  trivial, from colour and land structure alone. Against the generator prior, history tells
  plausibly give 5-15%.
- It has no kill rule.

**Phase 1.**
- It expects +0.05 from at most about 4k labels on one matchup, while E3 asks for +0.03 from 100k.
- It compares before and after on independent shuffles (SE 0.016) rather than on the same held-out
  deals (paired, about 0.009).

**Phase 2.**
- "< 10% intransitive triads" fires on noise when versions are close.
- "The exploiter's win rate does not grow" names no statistic.

**Phase 3.** One 48-hour run per arm, with a ladder SE of about 14 Elo per estimate, cannot
separate a 1.3x Elo rate (30 against 39 Elo).

**Fix.**
- Size each gate for power: separating +0.02 from +0.05 at α = β = 0.05 needs about 450 pairs.
- Gate on lower bounds, not on point estimates equal to the hoped-for effect.
- Pre-register what happens in the gray zone.
- Evaluate before and after on the same held-out deals.
- Score E3 by regret against independent re-labelling.
- Run at least 3 seeds per arm in Phase 3.

### M5. Feasibility: labels per day hold today; deployment latency and Commander do not

**Labels per day.**
- The plan's figures are consistent with today's serving: about 1,700 decisions/s ÷ 1,500 per label
  ≈ 1.2 labels/s.
- §2.2 calls this inference-bound, but the GPU measures 8.5-10.5k decisions/s. The limit is the
  learner's single-threaded serving loop (`learner.py:557-617`; /183 §26).
- The CPU ceiling measures about 3,400 decisions/s, so serving work could roughly double the label
  rate. It is the cheapest lever the core path has, and the plan omits it.

**Latency.**
- The search runs its k·d playouts one after another inside the game's own thread
  (`search.py:191-192`; `actor.py:1-8`). Engine CPU alone is 32 × 0.15-0.27 s ≈ 5-9 s per searched
  decision, before about 1,500 inference round trips.
- "~0.5-1 s" (§2.2) needs at least 16-20 playouts running in parallel processes for every decision,
  which is the whole machine for one game. It also needs a parallel playout executor (shipping
  forked games between processes), which is not in §8.
- At the tail, a single playout here reached 135 decisions (0.47 s on its own).

**Commander (NORTH_STAR's format priority).**
- A mid-game playout of a 4-player, 100-card game is about 10x longer: about 255 substantive
  decisions per seat (DESIGN_LATENCY §1).
- That leaves about 10k labels a day, and no search at play time within 4.2 s.
- The no-value-leaf design has no Commander path (Q6 only resizes the simulator).

**Fix.**
- Add the serving work and the parallel executor to the plan, or drop the play-time latency claim.
- Ask the owner now whether full playouts at λ = 1 are a two-player commitment.

### M6. The training loops' cadence is inconsistent unless B*_distill is small

**Evidence.**
- §4 takes a step per ≥ B*_distill labels, and labels expire after about 20 minutes.
- At about 60k labels a day (about 42 a minute), at most about 830 labels exist for any one step.
- If B*_distill is in the thousands, no step can ever be taken. That is plausible: B_simple for
  supervised losses typically runs 10^3-10^4, and here a 25M-parameter trunk is fitting sparse
  corrections.

**Fix.**
- Train the distillation loss with ordinary minibatches over a label window sized in labels.
  Staleness hurts slowly, because each target is a fixed estimate of Q under the policy that
  generated it.
- Keep B* for the outcome policy-gradient loss only.

### M7. Beliefs and memory assume decks with structure the deal generator does not produce

**Evidence.**
- Decks are uniform samples within two colours (`games.py:1648-1684`). B1's generator prior already
  captures colours, land counts and seen cards exactly.
- Beyond those, history can add only tells: missed land drops, mana held up, spells not cast. They
  are real but small in NLL. There is no card co-occurrence to learn.
- Separate heads for hand and library break joint constraints the futures depend on: exactly 24
  lands, and at most `MAX_COPIES` of a card. B1 shows land composition alone moves the playout
  value by 0.5.
- Train/test shift: the beliefs learn bots' tells and will be miscalibrated against humans. [26]
  added dropout for exactly this.

**Fix.**
- Sample whole decks from the generator prior, conditioned on public information, and let the
  learned belief reweight or resample those samples. They are consistent by construction, and only
  one sampler is ever built.
- Make the beliefs earn their place by paired games (belief-weighted futures against prior
  futures), not by NLL alone.
- Put the event window, if anywhere, on the belief side. [26] found temporal models helped its
  belief network but not its RL.
- Revisit once the Teacher or the drafter brings deck archetypes.

### M8. Simplicity and sequencing (owner #2)

- **One mechanism per job.** The hand-age bounds and the turn history encode the same public hand
  counts twice. Per-turn public counts over 8 turns would subsume A[n] without loss: lands, spells,
  mana spent and left untapped, attacks and blocks declined, cards entering and leaving each hand.
  It would also cover the owner's "held 12 turns", which n = 1..8 cannot (m7).
- **Phase 1 cannot attribute a failure.** It adds the ledger, hand ages, own library, turn history,
  event window, beliefs, belief-sampled labels, distillation and the magnet all at once, behind one
  learning-test gate. Stage it:
  1. sampler fix, labels and distillation (the unit E1-E3 test);
  2. then one input at a time, each with an ablation.
- **The PPO fine-tuner is dead by construction.** Its gate is a signal = noise step in ≤ 15 minutes,
  but B* at λ = 1 is at least 60 minutes. Keep PPO only as the E1/E3 fallback, and delete it once
  they pass.
- **Gumbel-top-k, completed Q and σ** reduce to a 5-line hedge/MMD step (B2).
- **§8's footprint (+780) undercounts.** It leaves out:
  - the generator sampler (B1);
  - private-state resampling (B3);
  - the conversion from plans to per-ask targets (m1);
  - the mulligan fork boundary (m6);
  - a realistic label buffer with expiry and bundles;
  - the parallel executor (M5).
  The expected figure is about +1,200-1,500 lines unless the cuts above are taken.

### M9. Settled decisions (DECISIONS.md)

**D6** ("default to K=256 with carried state").
- The plan demotes the carried state to an optional stage 3 without citing D6.
- The departure is right, but the plan should state the new evidence and amend D6. A carried state
  cannot be forked honestly (B3). Ataraxos reached superhuman play with history as features, and
  found temporal models helped its beliefs but not its RL ([26], "Opportunities for Further
  Improvement"). R3 is still unresolved.

**D14** (niche decks are rank 1).
- The deal generator makes only uniform coherent decks and stress piles.
- Niche specialists arrive in Phase 2 with no source of niche decks, and no gate before Phase 4
  measures niche-deck strength.
- Fix: add a fixed held-out niche set to every gate from E1 on, and keep those decks in the league.
  It needs only a few lines of generator knobs: mono-colour, three-colour, land-light and
  land-heavy, all-creature, high-curve.

**D15** is consistent: a curator plus a critic selecting among proposals. ACCEL-style edits are
proposals, and the matchup critic covers the deck critic.

**D16** is consistent, but Phase 4's gate should include R8's blinded human panel.

**D20** needs amending when the plan is revised:
- Guard 3 conflicts with M3.
- "One playout label: ~0.5-1 s" is latency, not cost; the cost is about 0.9 machine-seconds today.
- Its E1 gate inherits M1.

---

## MINOR

- **m1. Attack and block plans.** Gumbel-top-k and "logits" over joint plans are undefined, because
  the policy acts one creature at a time (`search.py:198-243`). Define a plan's log-probability as
  the sum of its per-ask log-probabilities in the engine's order, and distil pi' into per-ask
  conditionals.
- **m2. Crashed futures.** `mean_scores` (`search.py:134-142`) fills a crashed world with the global
  mean, while the other alternatives keep their real result in that world, which breaks CRN
  pairing. Drop that future for every alternative instead. (I saw no crashes in about 9,300
  heuristic playouts, but networks find crashes the heuristic does not: /183 §29.)
- **m3. Event window cost.** The plan says "~7% FLOPs". The trunk sees a mean of 27 tokens per
  decision at d512 L8, so a 2-layer encoder over 64 events at the same width costs about 60%, and 4
  extra trunk tokens about 15% more. State the encoder's width.
- **m4. Own library.** `determinize` shuffles it whole (`search.py:71`), losing London-mulligan
  bottoms and scry tops. Keep known positions in B1's sampler.
- **m5. The curated flag.**
  - DAGS trained half its episodes from natural starts (β = 0.5, 2605.14379 §4); specify a minimum
    natural share.
  - Blocks shift the deck prior too, so they should carry the flag or stay out of belief training.
  - Simpler for v0: no curation that depends on hidden state (no opening-hand lessons), and then no
    flag at all.
- **m6. Mulligan labels.** The London mulligan's asks are taken inside an engine call
  (`games.py:519-560`). Forking there needs a boundary before the mulligans.
- **m7. Hand-age bounds.** n = 1..8 cannot express "held 12 turns"; M8's per-turn counts cover it,
  and the upper bounds too.
- **m8. Unregistered scaffolds.** Each needs an entry in BACKLOG's "scaffolds to remove"
  (CLAUDE.md): 4 labels per game, the 0.95 threshold, the 10% confident sample, 20-minute expiry,
  the 50% replay cap, and the k and d values.
- **m9. Loss weights.** The plan samples about 10 positions per game against value-head collapse
  (/183 §10), which is good, but sets no loss weights. With hundreds of belief labels per game, the
  belief loss can dominate the shared trunk. Log per-head gradient norms.
- **m10. A question for the owner** (it conflicts with D20 guard 1 as written, so it is his call).
  With a linear target (B2), playing every alternative in the real game's own hidden state gives an
  unbiased future, in the same way the real result does in outcome RL: the policy never reads it,
  and learns E[target | its view]. It would remove belief error and non-locality. Clairvoyant credit
  comes only from optimising per world or from a nonlinear target.

## What holds up

- No strategy fusion: every later move is made by the policy reading its own masked view.
- §2.1's account of luck: averaging over futures the player cannot tell apart teaches it to play to
  its outs.
- The plan's code citations are accurate. Checked:
  - `search.py:63-80`;
  - `features.py:435-642`;
  - `model.py:314-320`;
  - `rig.py:159`;
  - `games.py:1212` and `games.py:1688`;
  - `ppo.py:85-123`;
  - `verbs.py:1464`;
  - `view.py:21`.
- The throughput anchors match measurement: a 6 ms fork, and about 3,400 decisions/s from the CPU.
- These citations are correct as given: [27] (7,000 runs; PPO and MMD against NFSP, PSRO, ESCHER
  and R-NaD), [29] (the flag mitigation), LBS (55-91% of the benefit at 35.8-4.6x less compute),
  and [20] (learnability on binary outcomes).
- Structure: cheapest experiments first, every experiment has a kill rule, and one deal spec serves
  pairs, blocks and evaluation.
