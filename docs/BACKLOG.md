# Backlog

Everything parked, with the reason it is parked. Two rules for this file.

1. **When an idea does not move the ladder in [`NORTH_STAR.md`](../NORTH_STAR.md), it lands
   here rather than being built.** Say so out loud when you park something.
2. **Every hard limit, cap, or schedule added anywhere in the codebase gets an entry under
   "Scaffolds to remove", with the condition that would let it go.** Never add one silently.

---

## Scaffolds to remove

Things currently hardcoded that the learnability principle says should not be. None of these
are neutral; each one is teaching the agent something.

| Scaffold | Where | Removal condition |
|---|---|---|
| **Thirteen shaping reward terms** — damage, life, board presence, board delta, cards, action discovery, mana generation, proactivity, penalties | `strategic_brain/environment.py:164-211` | Replace with outcome plus at most a couple of defensible terms. A 200-step game currently accrues about +20 of shaping against ±10 for the actual result, so the agent is optimising the shaping. Remove once the engine is correct enough that winning is learnable directly. |
| **Proactivity bias** — subtracts up to 10 nats from every pass action's logit | `strategic_brain/student.py:126-129` | Delete. It is applied at collection but not at training, which pins the PPO ratio to e^±10 on every pass action. It exists to fight "the agent passes", which is a symptom of the reward and the dead action space, not of the policy. |
| **`MAX_MOVES_PER_STEP = 500`** | `rule_engine/engine.py` | Replace with the loop detection in [`DESIGN_INFINITIES.md`](DESIGN_INFINITIES.md) plus a wall-clock truncate-and-bootstrap. Currently it pays −10 to whoever found a combo. |
| **Five-repeat action block** | `strategic_brain/train.py:169` | Same. A combo body executed five times is exactly this pattern, so the anti-stall heuristic is a combo filter. |
| **100-step stall detector and forced mana stripping** | `strategic_brain/train.py:160,180-183` | Same. It dismantles a combo's mana engine mid-assembly. |
| **Epsilon-greedy exploration with a 0.15 floor** | `strategic_brain/train.py:94` | Replace with an entropy bonus in the loss. At 0.31, a third of all actions are uniform random and the policy is decoration. |
| **Four `1 - games/10000` difficulty ramps, a CMC step function, and a permanent SQL ban on every life-gain card** | `strategic_brain/teacher.py` | Replace with a self-play league. The "teacher" itself takes no optimizer step, so it is a frozen random MLP blended 50/50 with `random.random()`. |
| **Seven cards special-cased by literal name string** | `rule_engine/card_data_loader.py:86-119`, `rule_engine/engine.py:216,326,89` | Directly violates this project's own `EFFECT_SYSTEM_MANDATES.md`. Remove when the ability tree in [`DESIGN_CARD_POOL.md`](DESIGN_CARD_POOL.md) can express them. |
| **Hardcoded `torch.device("cuda")`** | `strategic_brain/student.py:34`, `teacher.py:37` | Route through `MTG_bot/utils/device.py`. On the dev box these silently fall back to CPU. |

---

## Your own recorded ideas that were never built

These are worth keeping because you wrote them down and the reasoning was good. Sorted by how
much they serve the King Goal.

**The complete index of your ideas, with the ones that were lost or distorted, is
[`OWNER_IDEAS.md`](OWNER_IDEAS.md).** This section holds only the ones that belong on the path.
Entries tagged `L1`..`L9` below were recovered in the 2026-09-10 notes audit and had reached no
live document at all.

### Directly serves rank 1

- **Self-play league / opponent pool.** Removed from the task list in commit `d29a1d6` without
  ever being built. What exists instead is a single frozen self-copy refreshed every twenty
  games, which pins win rate near 50% by construction and carries no information about absolute
  strength. The charter now names adaptive opposition as a default yes. **This is the single
  highest-value item on this list.**
- **Belief vector over hidden information.** From the 272 lines of `RL_ARCHITECTURE.md` that a
  doc rewrite destroyed in `db5e024`; recover with
  `git show db5e024^:MTG_bot/docs/RL_ARCHITECTURE.md`. It contained a recurrent belief net over
  history tokens, three named encodings for multi-opponent scenarios with a pros-and-cons table,
  deterministic bookkeeping of exact opponent card counts, optional particle sampling of
  plausible opponent states, and supervised pre-training of the belief net from self-play logs
  before end-to-end fine-tuning. It also contained the rule *"do not embed the belief vector
  into every entity token"*, which is right and which
  [`DESIGN_CARD_POOL.md`](DESIGN_CARD_POOL.md) reuses for pool tokens.
  - **`L4`: when that head is finally trained, weight its loss by the impact of the state.**
    `ideas.md:66` and `:76-95`, never recorded anywhere until now. Your words: *"It should be more
    important to predict a lower-probability high-impact scenario, than the opposite. So how do we
    teach it this if we dont impact that head with the result of the games?"*, answered with
    `L_weighted = W(s) * L_aux` where `W(s)` is proportional to `abs(V(s))`. This matters because an
    unweighted cross-entropy over a sparse label learns the base rate, which is exactly the null
    `METRICS.md` `CLS-3` is built to expose. **Free diagnostic: report `CLS-3` split by `abs(V(s))`
    quantile.** Uniform accuracy across quantiles means the head learned the prior; accuracy
    concentrated in the high-swing tail means it learned inference.
  - **`L6`: opponent strategy as a continuous latent, never a discrete archetype class.**
    `notes.txt:20-22` proposed archetype detection then hand inference conditioned on it;
    `ideas.md:25` sharpened it to *"dont predict discrete strategies, use RGB approach maybe"*. The
    sharpened version is the right one and an authored archetype taxonomy is refused by
    `NORTH_STAR.md` §3 anyway. **Name the tension when this is designed:** `METRICS.md` `VAR-10` is
    an alarm against encoding *who* the opponent is; this encodes *what they are doing*, and a
    design that does not distinguish them will trip an alarm meant for something else.
  - **`L7`: the second encoding.** `project_specific_gemini_context.md:15-18`: encode the visible
    state, run the opponent-hidden predictor, then **encode again including the prediction**. The
    Tier A / Tier B split is not this: there, belief is an auxiliary head that never re-enters the
    encoder. The cheap version already exists in D11's rethink loop, where a later pass can see the
    earlier pass's output at no structural cost, so `b_t` could be visible there for free.

- **`L1`: the composite / super-token encoding, and the hierarchical action space.** The whole of
  `MTG_bot/mtg_token_encoding.md`, 124 lines, cited by no document in this repository. It proposes
  one composite entity per token type per player carrying aggregate stats, an internal per-token
  record for exact simulation, **max/min/median or attention pooling over the individual token
  vectors** so the aggregate is sensitive to extremes rather than to a mean, and a two-level action
  space where the policy says "attack with 3 tokens" and a deterministic layer picks which three.
  **This is a written answer to the open question at
  [`DESIGN_ACTION_SPACE.md`](DESIGN_ACTION_SPACE.md) §10.3**, which asks whether canonical ordering
  of `ATTACK_SET` and `BLOCK_ASSIGN` survives at 8 blockers against 5 attackers and warns the
  failure would present as *"the bot blocks adequately but never finds the good multi-block"*.
  Commander token floods are the case that breaks the token budget, so this is rank 1.
  **Recommended split when it is resolved: refuse the deterministic Level-2 mapper** (choosing
  *which* tokens is a strategy decision and hiding it in the engine hides it from learning, which
  `NORTH_STAR.md` §3 defaults to no) **and adopt the pooling**, which is a representation choice
  costing one op. Whichever way it goes, write it down.

- **`L3`: relational bias in the board encoder's attention.** `notes.txt:63`: *"The game state is a
  graph (a counter is on a creature; an aura is attached to a creature). We will encode these
  relationships by adding a **Relational Bias** to the Transformer's attention mechanism."*
  [`DESIGN_CARD_POOL.md`](DESIGN_CARD_POOL.md) rejects a tree GNN, but that is about the **card
  ability tree**; the **board** encoder in [`DESIGN_TRAINING.md`](DESIGN_TRAINING.md) is flat
  self-attention with **no edge encoding at all**, while `ARCHITECTURE.md:33` measures 214 entities
  and **412 relationships** at a Commander start. The proposal is an additive `b_ij` over a small
  typed edge vocabulary (attached-to, controlled-by, counter-on, blocking, targeting, in-zone).
  **The measurement that decides it:** an `N x N` bias tensor per layer is memory traffic, and the
  GB10 is bandwidth-bound, so price it against the same latency harness that sizes the model before
  adopting or refusing.

- **`L8`: the retrieval index does not exist.** `ideas.md:162-164` asks to *"investigate
  **TurboQuant** methods to accelerate similarity searches and retrievals from the card embedding
  vector database"*, and it is recorded nowhere. Meanwhile `DESIGN_CARD_POOL.md:184` specifies
  `retrieve_topk(query(board, belief), legal_pool)` with `k = 64..256` **per decision** and names no
  ANN method, no quantisation scheme, no recall bound and no rebuild cadence. Rank 1 because the
  clock is rank 1 (`NORTH_STAR.md` §1a). Four constraints the index must satisfy, from
  [`OWNER_IDEAS.md`](OWNER_IDEAS.md) §2.2: **filtered** ANN, because legality is a rule of Magic and
  cannot become approximate; a **recall number** against the exact scorer plus the TV distance
  between exact and retrieved policies, because dropped candidates are the ones nearest the
  decision boundary; **quantisation validated against the residual-norm diagnostic**, not only
  against recall, because the same vectors carry the generalisation claim; and a **rebuild cadence**,
  because `v_card` moves every update.
- **Frozen board cross-attention** — encode the board once per phase and have every reasoning
  pass cross-attend to it without re-encoding. Also from the destroyed doc. On the DGX this is
  not an optimisation, it is a requirement; it is the Tier A / Tier B split in
  [`DESIGN_TRAINING.md`](DESIGN_TRAINING.md).
- **Rethink compute penalty**, so the model learns the optimal stopping point rather than being
  given a fixed pass count. Exactly the right instinct — the reward pays for thinking, and the
  model learns when deeper thought is worth it.
- **Puzzle-ladder levels 3 and 4** from `progression_playbook.md`: stack interaction (responding,
  end-of-turn timing, combat tricks) and second-order thinking (playing around sweepers, bluff
  attacks, baiting counterspells). Only levels 1 and 2 exist. Levels 3 and 4 are unreachable
  until the engine has real priority.
  - **`H12`: concept-tag every puzzle so its cards can be hot-swapped across sets.**
    `progression_playbook.md:62-69`, not carried into `METRICS.md` §10's PZL rebuild. A puzzle
    tagged with the *concept* it tests rather than the cards it uses is the tied-rank-1 goal
    expressed as a test corpus: it is how you check that a never-seen card built from practised
    primitives is played competently. Cheap, and it has to happen before the corpus is authored,
    not after.
- **Deck-space evolution to find niche decks** (`ideas.md`). **Promoted 2026-09-10 by D14: this is
  now on the path, not parked.** Niche-deck strength is part of rank 1, so the mechanism for
  finding niche decks is too. Original note follows: an elite pool of niche decks,
  periodic re-evaluation, mutation, under-confidence sampling, a novelty reward, robustness
  testing by perturbing one card, and `R_final = R(D) + λ·Robustness(D)` with **λ annealed from
  high to low** so that early training punishes sharp minima and late training goes looking for
  them. This is the mechanism for the stated goal of being good at weird decks.
  **Correction, 2026-09-10: D14 promoted deck-space evolution, not every mechanism in that
  sentence.** Three of them were subsequently refused with reasons in
  [`DESIGN_DRAFTER.md`](DESIGN_DRAFTER.md) §9, and this entry used to contradict that file.
  The refusals stand: the **annealed λ** is a hand-authored schedule on a reward term, which
  `NORTH_STAR.md` §3 refuses, and it is replaced by the curator's learned knob distribution; the
  **sharp-minimum-seeking optimiser** confuses deck-space sharpness with weight-space sharpness and
  would select for fragility, and is replaced by `DFT-13 deck_sharpness` as a measured coordinate;
  a **novelty term in any reward** is what uniform random maximises, and is replaced by
  conditioning on a measured statistic. What is genuinely on the path from that sentence: the elite
  pool (the capped archive), the single-card-swap mutation, and the leave-one-out robustness sweep
  (`DESIGN_TEACHER.md:376`, which quotes you). **Still parked and not yet answered:** the archive
  refresh. Your `ideas.md:3` asks to revisit niche decks and *"re-evaluate whether they are still
  viable, better or worse than when it was first tested"*; `lambda_ret` re-evaluates the *student's
  retention*, which is a different object, so an archived deck's stored score still ages against a
  league that has moved. See [`OWNER_IDEAS.md`](OWNER_IDEAS.md) §5.1.

### Serves ranks 2 and 3

- **Information-set Monte Carlo tree search** with determinization. Explicitly parked in
  `tasklist.md`. Blocked on make/unmake in the engine — see
  [`DESIGN_TRAINING.md`](DESIGN_TRAINING.md) §5. **Two mechanisms you wrote down for it were never
  recorded until now, and both are load-bearing:**
  - **`L9a`: fix the opponent prediction for the whole simulation.** `ideas.md:52`: *"keep this
    opponent prediction fixed for the remainder of the simulation... avoid risking to have to
    re-run the opponent prediction NN"*. This is what makes ISMCTS affordable at all on this
    hardware. It is also what creates the strategy-fusion problem in the open question below, so
    the two must be answered together.
  - **`L9b`: punish the prediction head by severity, not by accuracy.** `ideas.md:55`: *"scale
    based on severity of wrongful predictions, based on the value-function analysis of how severe
    the wrongness was"*. This is `L4` again, in the search loop instead of the loss. **The same
    idea appears three times in your notes from three directions and had been recorded zero times.**
- **KV cache of board analysis across an action sequence.** Same idea as the Tier A cache.
- **Synthetic board-state dataset for pre-training the board encoder.**
- **`C23`: the four untaken options from the deleted `RL_ARCHITECTURE.md`'s efficiency ladder**
  (§8, `:189-193`): zone-local dense attention with inter-zone traffic via summary tokens, top-K
  learned-focus attention, low-rank factorised attention, and incremental belief updates along an
  MCTS path. Only the fifth, hierarchical pooling of large zones, survived into
  [`DESIGN_TRAINING.md`](DESIGN_TRAINING.md). They are the latency ladder and the clock is rank 1,
  so they should be priced rather than forgotten.
- **`A26`: inference-time candidate re-ranking.** `notes.txt:163,165` proposed iterating the top-k
  base actions, building complete candidates, and scoring each with a **final Q-value head**.
  [`DESIGN_ACTION_SPACE.md`](DESIGN_ACTION_SPACE.md) commits to a single autoregressive decode with
  no re-ranking stage; §4.5's per-plan-step critic is a **training-time** critic, not an
  inference-time re-ranker. That is probably the right call on the clock, but no document says it
  is a call, so it reads as an oversight.

### Product goals beyond the King Goal

- **Stockfish-style top-3 move suggestion** with a move line, so a human can set up a position
  and ask what is best. Also for drafting, both from empty and completing a partial deck.
- **Teacher by vector search** — build decks card by card via a matchup analyser emitting a query
  vector, then vector search against the card embedding pool, with matchup history and a
  diversity bonus to avoid rock-paper-scissors cycles. Every proposed matchup validated by the
  engine, illegal proposals penalised.
  **No longer parked as a mechanism: it is on the path and it is already built into three designs.**
  `score(c|s) = q(s).k(c)` at `DESIGN_TEACHER.md` §4.3:506 **is** this idea, because the argmax of
  an inner product over a set is nearest-neighbour search under that inner product. What remains
  parked is only the **index** that makes it sublinear, which is `L8` above. See
  [`OWNER_IDEAS.md`](OWNER_IDEAS.md) §2. The illegal-proposal penalty was refused with a reason at
  `DESIGN_TEACHER.md` §8: legality is a rule of Magic, so it is a hard mask, not a reward term.
- **"Invent new cards in the gaps"** (owner, 2026-09-10). Parked as a **generative** problem: it
  needs a decoder from a query vector back into a typed ability tree, plus the compiler run in
  reverse, and it emits cards no engine has been tested against. **The measurement half is free and
  should be taken now:** `gap(s) = ||q(s) - k(c*)||` for the retrieved argmax `c*` is computable
  the day the pointer head exists, needs no decoder, and is the honest definition of "the pool has
  no card for what I want here". Logged per pick it is a coverage map of the card pool against what
  the drafter actually asks for.
- **Teacher reward by matchup win-rate delta** — reward the teacher when the student's win rate
  improves a lot over a matchup, so it prioritises scenarios where there is room to grow. Plus
  mirror-matchup mastery: fifty games from each side, and if the student only wins from one side
  the matchup is broken and worth teaching.
- **Deck analysis and suggestion for human players.**
- **"Hail Mary" logic** — in desperate positions, shift from maximising expected value to
  maximising the probability of drawing a specific out. Note this is genuinely at odds with a
  pure expected-value critic and needs a distributional value head or an explicit risk parameter
  to express at all.

### Abandoned, do not revive

- Card recognition from photos and video, YouTube frame scraping, OCR, the image vector database,
  the local-LLM agent harness. All in `attic/`. Off the King Goal.

---

## Engine gaps you logged yourself

From `EFFECT_SYSTEM_MANDATES.md`, still true:

- Triggered abilities and responses resolve immediately; last-in-first-out is not enforced.
- Spells requiring choices during resolution are unsupported.
- **Replacement effects do not exist.** These are load-bearing for Commander — the command-zone
  replacement, commander tax, doubling effects, damage prevention.

Plus, found in this audit and not previously logged: no real priority, no evasion enforcement in
blocking, only the first blocker participates in combat damage, layers 1 through 6 absent, no
timestamps or dependency pass in the layer system, activated and loyalty abilities unreachable,
two players maximum.

**`H13`: the Chaos Test catalogue you wrote and nobody carried forward.** `EFFECT_SYSTEM_MANDATES.md`
names four engine stress scenarios: an illegal target discovered mid-resolution, zero and negative
values, empty pools, and circular dependencies. None of them appears in `METRICS.md` or in
[`TRAINING_REVIEW_PROTOCOL.md`](TRAINING_REVIEW_PROTOCOL.md). They are four concrete tests, already
specified, that cost nothing to adopt and belong under the `EC` engine-correctness gate.

---

## Corrections owed to the docs

Contradictions found in the 2026-09-10 notes audit. These are not decisions; they are files that
disagree with a decision already taken.

| # | where | what is wrong | what it should say |
|---|---|---|---|
| **1** | [`DESIGN_TRAINING.md`](DESIGN_TRAINING.md)`:118` and `:344` | Both still order the **plan decoder deleted** (*"Delete the plan decoder; it gets no gradient anyway"*, and a `deleted \| -50M dead weight` row in the architecture table). [`DECISIONS.md`](DECISIONS.md) **D3 is a binding owner instruction to keep it and train every step**, and it explicitly overturns the earlier audit that proposed the deletion. `DESIGN_ACTION_SPACE.md` §4 implements D3 correctly; this file was never updated | the row becomes the trained multi-step decoder D3 requires, and `:344`'s graph-capture blocker gets the real fix (the `.item()` sync inside the plan loop) instead of a deletion. **Highest priority in this table: an agent following the architecture table would delete the head the owner ordered kept, and would believe it was following the design** |
| **2** | `docs/card_embedding_architecture_sketch.png` (committed in `000e37c`) and `MTG_bot/mtg_token_encoding.md` | The only two owner artefacts cited by **no** document. The sketch specifies a 2346-d card vector with three channels beside the numeric one: an **NLP encoding of the rules text**, **17Lands meta-information**, and a **card-art autoencoder**. `DESIGN_CARD_POOL.md` builds `v_card` without any of them and never says why | one paragraph each in `DESIGN_CARD_POOL.md`, adopted or refused, in the style of that file's own Tarmogoyf overrule. Proposed refusals with real reasons, not "we killed OCR", are drafted in [`OWNER_IDEAS.md`](OWNER_IDEAS.md) §4.2 |
| **3** | [`METRICS.md`](METRICS.md) `DFT-5` | It tests land count *"against a declared heuristic"*, i.e. **conformity**. `thought_checkpoint.md:24` asked whether the model discovers the 40/60 ratio **independently**, which is the opposite epistemics. `DFT-5` is correct as a pre-flight gate and cannot answer the owner's question | keep `DFT-5` as the gate, add one cheap row that reports the land-ratio distribution against generation index **with the target curve out of the loss**. See `OWNER_IDEAS.md` §5.2 |
| **4** | `MTG_bot/INDEX.md` and `MTG_bot/docs/AGENT_GUIDELINES.md` | Both route a new agent into the stale tree: `INDEX.md` names the **48-line remnant** `RL_ARCHITECTURE.md` as the primary RL doc and `project_goals.md` as the vision, and lists no file under `docs/`; `AGENT_GUIDELINES.md` tells every agent to read them first, contradicting `CLAUDE.md` | point both at `NORTH_STAR.md`, `docs/`, and `OWNER_IDEAS.md` |
| **5** | [`DESIGN_ACTION_SPACE.md`](DESIGN_ACTION_SPACE.md) §4.3 | §4.3 gives **every executed plan step its own advantage**. The deleted `RL_ARCHITECTURE.md` §4.4 proposed the opposite, a reward only at the **end of the phase sequence**, *"to evaluate the Global State Change of an entire turn's worth of sequencing rather than individual taps or casts"*. The live design is better argued, but no document records that the owner's version was considered | one paragraph naming the alternative and the reason it was not taken. This is exactly the shape of reasoning `db5e024` destroyed |

---

## Open questions needing your decision

These are forks, not tasks. See the report that accompanied this audit.

1. **Rebuild the engine, or evolve it?** The audit's verdict is rebuild, and the reasoning is in
   [`ARCHITECTURE.md`](ARCHITECTURE.md). This is the biggest call.
2. **Ability tree first, or engine first?** The recommendation is the tree first, because it is
   the contract both the engine and the network are written against.
3. **Full-game BPTT or K=256 truncated?** Memory says it is affordable either way; the question
   is whether the 10× serial cost buys anything, and that is measurable.
4. **v0.5 at 150M or straight to v1 at 392M?** Throughput scales inversely with size.
5. **`L5`: the worst-case-opponent trap.** Your question, `ideas.md:14-15`, verbatim, because it
   has never been answered anywhere: *"How do we avoid that the model predicts the opponent to have
   the worst case possible deck, and that we then play against that strategy, in scenarios where
   playing optimally against the hardest possible opponent-state combination results in exposing us
   to some of the also likely, but less consequential opponent-state combinations? Is this learned
   implicitly in win-rate and rewards, or do we need to handle that we dont expose us to scenario
   2,3,4 by playing optimally aginst scenario 1, if they are all somewhat equally likely?"*
   It is the difference between a maximin policy and a Bayes-optimal policy under the belief, and
   determinized search is known to produce exactly this pathology. **The honest answer is that it is
   learned implicitly only if the belief is calibrated and the search averages over it correctly,
   and both of those are parked.** Note also that `L4`'s impact weighting pushes the opposite way,
   toward paranoia, so `L4`, `L5` and `L9a` have to be reasoned about together and not adopted one
   at a time. Whoever writes the belief-and-search design answers this before shipping it.
