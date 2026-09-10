# Owner ideas: the preserved index

## 1. What this file is

**Every idea the owner has written down, where it came from, what happened to it, and why.** It
exists because commit `db5e024` rewrote `MTG_bot/docs/RL_ARCHITECTURE.md` from **237 lines to 48**
and destroyed the owner's own architecture reasoning in the process, keeping the conclusions and
throwing away the arguments. A `--numstat` sweep of the whole repository history confirms `db5e024`
is the only doc-shrinking commit in the project's life, so this is one wound rather than a pattern,
but it cost the belief-vector design, the frozen-board cross-attention argument, the rethink
compute penalty, and the Teacher's query-vector-plus-vector-search mechanism, every one of which
had to be independently re-derived months later at real cost.

The audit behind this file read `MTG_bot/notes.txt` (246 lines), `ideas.md` (180), `notes.txt`
(29), `thought_checkpoint.md`, `engine_map.md`, `MTG_bot/mtg_token_encoding.md` (124),
`MTG_bot/INDEX.md`, `MTG_bot/TODO.txt`, `MTG_bot/tasklist.md`, all twelve `MTG_bot/docs/*.md`,
`project_goals.md`, `project_specific_gemini_context.md`, `attic/README.md`, all sixteen
`docs/*.md`, and `git show db5e024^:MTG_bot/docs/RL_ARCHITECTURE.md`.

**Score: 62 on-the-path, 24 parked-with-reason, 8 superseded upward with the owner's version cited,
2 implemented, 6 captured-but-distorted, 9 headline LOST plus 8 minor.**

| section | contents |
|---|---|
| §2 | the idea on the table today (2026-09-10, vector retrieval), verbatim, and what it actually is |
| §3 | the complete inventory: idea, source, status, where it is now |
| §4 | every LOST idea, in the owner's own words, with what should happen to it |
| §5 | every DISTORTED or self-contradictory capture, which is more dangerous than a loss |
| §6 | the recovered `RL_ARCHITECTURE.md`, quoted, because it exists only in git |
| §7 | the rule that stops this happening again |

**Recovery to disk is not capture.** `docs/recovered/RL_ARCHITECTURE_pre_db5e024.md` restores the
deleted file, and that is good, but an idea sitting in `docs/recovered/` is archived, not on the
path. Everything below is scored on whether it reached `NORTH_STAR.md`, `docs/DECISIONS.md`,
`docs/BACKLOG.md` or a `docs/DESIGN_*.md`.

**Status vocabulary used throughout.**

| status | meaning |
|---|---|
| **on-path** | in a live doc, doing work |
| **parked** | in `BACKLOG.md` with the reason it is parked |
| **superseded** | replaced by something strictly better, with the owner's version cited in the replacement |
| **refused** | argued down in a live doc, with reasons, in the style of `DESIGN_CARD_POOL.md` Step 3 |
| **DISTORTED** | present in a live doc as a different idea wearing the same name. See §5 |
| **LOST** | present in no live doc, adopted or refused, at all |

---

## 2. The idea on the table today: retrieval

**2026-09-10, the owner, verbatim:**

> *"Also remember to use the encodings. My idea was some vector thingy, where it has a prediction
> of the card it wants to add to a deck, and then searches it up in the vector database with the
> encoded values from the ability tree, and it can choose the card that comes the closest to what
> card it thinks is ideal. Maybe we can use that to filter depending on sets too when drafting, or
> even eventually extend it to 'invent' new cards in the gaps"*

**This is the owner's own idea returning.** It was written down before, in the file `db5e024`
destroyed, `RL_ARCHITECTURE.md` §5.1:

> *"The Teacher builds decks card-by-card using a **Transformer-based Matchup Analyzer**. For each
> slot, the model generates a **Query Vector** based on the current deck's synergy and the
> opponent's strategy. It performs a **Vector Search** against the card embedding pool to find the
> optimal card to add."*

### 2.1 It is not an alternative to the pointer head. It is the pointer head.

The drafter's pick head is already exactly this operator (`DESIGN_TEACHER.md` §4.3:506):

```
score(c | s)  =  q(s) . k(c)     where  k(c) = W_k v_card(c),  q(s) = W_q deck_encoder(s)
pi(c | s)     =  softmax over the candidate set, after the hard legality mask
```

`q(s)` **is** "a prediction of the card it wants to add": a point in card-embedding space that need
not correspond to any printed card. `k(c)` **is** "the encoded values from the ability tree", the
`v_card` of `DESIGN_CARD_POOL.md` Steps 1 to 3. And taking the argmax of an inner product over a
set is, definitionally, nearest-neighbour search under that inner product.

**So the owner's "predict the ideal card, then look it up" and the pointer head are the same
operator written two ways. Retrieval is not a different architecture. It is the scalable
implementation of the one already chosen.** `DESIGN_DRAFTER.md` §5.1:577 already states that the
drafter and the in-game `retrieve_topk(query(board, belief), legal_pool)` of
`DESIGN_CARD_POOL.md:184` are one network used twice. This makes it three uses of one operator, not
three mechanisms.

Say that plainly, because the wrong reading is expensive: **nobody should build a second system.**

### 2.2 What genuinely changes when you implement it as retrieval

Seven things, and only the first is the obvious one.

| # | what changes | why it is not free |
|---|---|---|
| **1** | **Cost goes from linear in the pool to sublinear.** An exact softmax over the legal pool is `O(pool x d)` per pick. At `d = 256` under a full-pool Commander mask that is millions of MACs per pick, times 100 picks per deck, times thousands of decks, and in-game it recurs per decision under the championship clock | this is the entire reason retrieval matters, and it makes retrieval a **rank-1 concern** (`NORTH_STAR.md` §1a), not an optimisation |
| **2** | **The legality mask stops being free.** Today it is exact and costs microseconds because it is applied to the logits before the softmax (`DESIGN_DRAFTER.md` §4.4:527) | an ANN index returns neighbours, not *legal* neighbours. It must become **filtered ANN**: either one index per mask bucket (§4.4 already precomputes exactly these, 18 colour-identity buckets in M21 and 32 in the full pool) or over-fetch plus post-filter with a proven recall floor. Get this wrong and legality becomes approximate, which `NORTH_STAR.md` §3's corollary forbids outright: legality is a **rule of Magic**, and rules are exact |
| **3** | **Approximation error becomes policy error, and must be measured.** Exact argmax has recall 1 by construction; ANN does not, and the candidates it drops are by construction the ones nearest the decision boundary | needs a new register row: top-k recall against the exact scorer on a sample, plus the total-variation distance between the exact and the retrieved policy. Without it a silent policy change is indistinguishable from ordinary weakness, the same failure shape `DESIGN_ACTION_SPACE.md` §10.3:1096 names for canonical ordering |
| **4** | **Quantisation is a representation change, not an implementation detail.** TurboQuant (`ideas.md:162-164`) and every product-quantisation scheme distorts inner products | the same `v_card` vectors carry the tied-rank-1 generalisation claim, *"the composition **is** the card"* (`DESIGN_CARD_POOL.md` Step 3). A quantised index must therefore be validated against the **residual-norm diagnostic** defined there, not only against retrieval recall |
| **5** | **The index goes stale.** `v_card` is learned and moves on every update | rebuild cadence becomes a real cost line. `DESIGN_CARD_POOL.md` already refreshes pool tokens *"once per turn, not per decision"*; the index needs its own cadence and its own staleness number. The cheap alternative is a frozen key projection `W_k` with a learned query, trading capacity for a static index. That is a design fork, not a detail |
| **6** | **Set filtering falls out for free.** The owner's second clause | a set filter is a mask over the index, the same machinery as colour identity. Nothing new is required, and it is one more argument for bucketed indexes over one monolithic one |
| **7** | **"Invent new cards in the gaps" is a different operation and must be named as one** | retrieval finds the nearest **existing** card to `q(s)`. The gap case is when the nearest existing card is **far** from `q(s)`. See §2.3 |

### 2.3 The gap idea, split into the free half and the parked half

`gap(s) = || q(s) - k(c*) ||`, where `c*` is the retrieved argmax, is **computable the day the
pointer head exists**, needs no decoder, and is the honest definition of *"the pool has no card for
what I want here"*. Logged per pick across a run it is a coverage map of the card pool against what
the drafter actually asks for, and it is the same kind of instrument as the residual-norm gauge:
one number that says whether the representation and the pool agree. That half is nearly free and
serves rank 1 now.

**Decoding `q(s)` back into a card is a generative problem over the typed grammar of
`DESIGN_CARD_POOL.md` Step 1, not a retrieval problem.** It needs a tree decoder, the compiler
running in reverse, and an engine that has never been tested against the cards it emits. Park it,
record it, and keep the measurement half, which is the version that serves the King Goal today.

### 2.4 What is missing, everywhere

The retrieval **operator** is specified in three places (`DESIGN_CARD_POOL.md:184`,
`DESIGN_TEACHER.md` §4.3:506-517, `DESIGN_DRAFTER.md` §5.1:577). The retrieval **index** is
specified in none of them: no ANN method, no quantisation scheme, no recall bound, no rebuild
cadence. `DESIGN_CARD_POOL.md:184` asks for `k = 64..256` on every decision and names no way to get
it. **The owner flagged this exact gap in `ideas.md:162-164` and it was never recorded anywhere.**
That is L8 in §4, and it is now an entry in `BACKLOG.md`.

---

## 3. The complete inventory

### 3.1 `MTG_bot/notes.txt`, 246 lines

The richest design document in the repository. It is indexed by nothing, including
`MTG_bot/INDEX.md`.

| # | idea | source | status | where it is now |
|---|---|---|---|---|
| A1 | Hybrid "Judge" rule engine that is *"not intelligent"* plus a "Player" brain that chooses | `notes.txt:4-5` | on-path | `NORTH_STAR.md` §3 corollary; `DECISIONS.md` D1, D2 |
| A2 | State vector from card embeddings across **all known zones**, both players, plus life and turn | `notes.txt:10-11` | on-path, narrowed | `DESIGN_TRAINING.md:105,123,287`. Libraries and opponent hands deliberately dropped as a clairvoyance fix |
| A3 | Multi-headed Synergy / Impact / Threat / Potential scores | `notes.txt:14-18` | self-retired | superseded by the owner at `notes.txt:43` |
| A4 | **Potential score**: *"the likelihood of drawing synergistic or high-impact cards from the remaining deck"* | `notes.txt:18` | LOST (minor) | no successor named. The critic subsumes it in principle and no doc says so |
| A5 | Opponent archetype detection, then hand inference conditioned on the archetype | `notes.txt:21-22` | **LOST (L6)** | nowhere |
| A6 | Evaluation scores as an MCTS pruning heuristic | `notes.txt:25-26` | parked | `BACKLOG.md:75`; arithmetic at `DESIGN_TRAINING.md:352-363` |
| A7 | "Hail Mary" logic: maximise `P(drawing an out)` instead of EV when desperate | `notes.txt:28-30` | parked, improved | `BACKLOG.md:92-95`, with the objection added that it needs a distributional value head |
| A8 | Phase plan 0 to 3 | `notes.txt:32-37` | superseded | `DECISIONS.md` D1, D12 |
| A9 | *"Don't feed the model the answers"*: no hand-crafted score inputs | `notes.txt:43-45` | on-path | `NORTH_STAR.md` §3. Derivation uncited, see §5.7 |
| A10 | `GameState -> Transformer -> Actor + Critic`, self-play PPO | `notes.txt:47,55` | on-path | `DESIGN_TRAINING.md:64-90`; `DESIGN_ACTION_SPACE.md` §4 |
| A11 | The critic's `V(state)` **is** the learned representation of impact and urgency | `notes.txt:51` | on-path | implicit throughout; `METRICS.md` `PH-4` |
| A12 | Actor head as a learned goal-oriented effect search | `notes.txt:53` | on-path | `DESIGN_ACTION_SPACE.md` §3.1 pointer over masked candidates |
| A13 | Entity-Component model; *"New keywords or counter types are just new entities; the model architecture does not change"* | `notes.txt:59-61` | on-path | `DESIGN_CARD_POOL.md` Step 1; `DESIGN_TRAINING.md` object tokens; `NORTH_STAR.md` tied rank 1 |
| A14 | **Relational bias added to the transformer's attention** to encode the state graph | `notes.txt:63` | **LOST (L3)** | nowhere. The board encoder is flat self-attention with no edge encoding |
| A15 | Vocabulary: Tokenization, Embedding, Encoding, where encodings are *contextualised* vectors | `notes.txt:67-70` | on-path | used consistently in `DESIGN_CARD_POOL.md` and `DESIGN_TRAINING.md` |
| A16 | Hybrid card representation: atomic id **plus** components | `notes.txt:74-77` | on-path, improved | `DESIGN_CARD_POOL.md` Steps 2-3: `v_composed(tree) + gate * E_atomic[oracle_id]`, zero-init, 15% dropout |
| A17 | The Tarmogoyf / Maro argument for a unique atomic id | `notes.txt:79` | refused, openly | `DESIGN_CARD_POOL.md` Step 3 quotes it and overrules it. **The model of how to do this.** See §5.3 |
| A18 | Structured `target_filter` objects | `notes.txt:85-107` | superseded | `DESIGN_CARD_POOL.md` `Selector` / `Filter`, strictly richer |
| A19 | Structured `condition` objects for card-name references | `notes.txt:109-130` | superseded | same, plus `DESIGN_ACTION_SPACE.md` §6.4 naming a card as a pointer |
| A20 | Parsing strategy: keywords, params, objects, resolve `~` | `notes.txt:132-140` | superseded | `DESIGN_CARD_POOL.md` "The compiler", offline and versioned, *"never a runtime regex"* |
| A21 | Compositional primitives instead of one token per effect | `notes.txt:146-149` | on-path | `DESIGN_CARD_POOL.md` Step 1, 60 verbs / 40 filters / 10 combinators |
| A22 | The **binding problem** and the relational graph as its solution | `notes.txt:150` | on-path, cited | `DESIGN_CARD_POOL.md` Step 2 answers it with open/close plus depth and role |
| A23 | Parameterized action space: decouple *what* from *how* | `notes.txt:156` | on-path | `DESIGN_ACTION_SPACE.md` §1.3 |
| A24 | `ChoiceRequiredAction` carrying choice metadata | `notes.txt:159` | superseded | `DESIGN_ACTION_SPACE.md` §1.4 `Slate` / `Field` |
| A25 | Parameter heads **conditioned on the base action** | `notes.txt:162-164` | on-path | `DESIGN_ACTION_SPACE.md` §3.1 autoregressive prefix-conditioned masked softmax |
| A26 | Iterate top-k base actions, build complete candidates, re-rank with a **final Q-value head** | `notes.txt:163,165` | LOST (minor) | no candidate re-ranking stage anywhere. §4.5's per-plan-step critic is a training-time critic, not an inference-time re-ranker, and no doc says whether that is deliberate |
| A27 | Three-layer parsing: ingest, semantic extraction, ambiguity handling | `notes.txt:176-195` | superseded | `DESIGN_CARD_POOL.md` "The compiler" |
| A28 | **Unparsed-text queue** with manual review | `notes.txt:193-194` | on-path, cited | `DESIGN_CARD_POOL.md:228` cites `notes.txt` and records that no such queue exists yet |
| A29 | Unified action representation with `source_type` | `notes.txt:197-231` | superseded | `DESIGN_CARD_POOL.md` `Ability` union, which adds Replacement that Commander needs |
| A30 | Ordering comes from **the stack**, not a numeric field; AP-NAP for simultaneous triggers | `notes.txt:235-238` | on-path | `DESIGN_ACTION_SPACE.md:843` exempts `ORDER_TRIGGERS` *"because there the order is the decision"* |
| A31 | Parser extracts structure; engine owns order, stack, priority | `notes.txt:240-244` | on-path | `DESIGN_CARD_POOL.md` compiler offline, plus D1 |

### 3.2 `ideas.md`, 180 lines

Niche decks and imperfect information. `MTG_bot/ideas.md` is byte-identical to `ideas.md:1-151`;
B24 to B29 exist only in the root copy. **Keep one file. Two copies will drift.**

| # | idea | source | status | where it is now |
|---|---|---|---|---|
| B1 | Optimiser seeking **sharp minima**, because *"very few changes to the deck completely ruins the deck's performance"* | `ideas.md:1` | refused, openly | `DESIGN_DRAFTER.md` §9:628, replaced by `DFT-13 deck_sharpness` as a measured coordinate |
| B2 | Do not **forget** niche decks; the buffer cannot hold both | `ideas.md:2` | on-path | `METRICS.md` `ST-4`, `DFT-7/8`; `DESIGN_TEACHER.md:270` keeps MAP-Elites as a separate niche archive citing `ideas.md:1-11` |
| B3 | **Revisit** niche decks and re-evaluate viability over time | `ideas.md:3` | **DISTORTED (S1)** | `DESIGN_TEACHER.md:123,238` `lambda_ret` measures the *student's retention*, not a *deck's viability*. See §5.1 |
| B4 | Mutation and evolutionary strategies | `ideas.md:5` | on-path, partly refused | `DESIGN_DRAFTER.md` §9:636 refuses deck crossover with a reason, adopts the single-card swap |
| B5 | Under-confidence sampling | `ideas.md:5` | parked | `BACKLOG.md:66`; measured at `METRICS.md:465` but not used to sample |
| B6 | Novelty reward | `ideas.md:5` | on-path, then refused as a reward | `DECISIONS.md` D14 promoted it; `DESIGN_DRAFTER.md` §9 refuses a novelty *term* and keeps conditioning on a measured statistic |
| B7 | Elite pool of niche decks | `ideas.md:7` | on-path | `DECISIONS.md` D14; `DESIGN_TEACHER.md:270` capped archive |
| B8 | Adversarial training against a constantly adapting opponent | `ideas.md:8` | on-path | `NORTH_STAR.md` §3; `BACKLOG.md:38` names the league the highest-value item; `METRICS.md` `ST-7` |
| B9 | Robustness test by changing one or a few cards | `ideas.md:9` | on-path, cited | `DESIGN_TEACHER.md:376` quotes it verbatim as the leave-one-out sweep |
| B10 | `R_final = R(D) + lambda * Robustness(D)`, **lambda annealed high to low** | `ideas.md:11` | **CONFLICT (S5)** | `BACKLOG.md` listed it as promoted; `DESIGN_DRAFTER.md` §9 refuses it as a hand-authored schedule. Resolved in this pass, see §5.5 |
| B11 | The **worst-case-opponent trap** | `ideas.md:14-15` | **LOST (L5)** | nowhere. An open architectural question the owner posed and nobody answered |
| B12 | ISMCTS with determinization | `ideas.md:19-27` | parked | `BACKLOG.md:73-75`; `METRICS.md:888` gives the determinized-oracle gap as the honest bound |
| B13 | Separate NN for opponent hand, deck and strategy; *"dont predict discrete strategies, use RGB approach maybe"* | `ideas.md:25` | partly LOST | belief vector parked at `BACKLOG.md:44`. **The continuous-not-discrete point is recorded nowhere.** Folded into L6 |
| B14 | Simulate the perfect-information game under the prediction; wrong predictions punish themselves | `ideas.md:26` | parked | inside the ISMCTS entry only |
| B15 | Belief update on a surprising card: discard inconsistent determinizations, reset the tree | `ideas.md:38-47` | parked | with ISMCTS |
| B16 | **Fix the opponent prediction for the whole simulation** | `ideas.md:52` | **LOST (L9a)** | nowhere |
| B17 | Discount reward by how early in the game the decision was | `ideas.md:53` | partly LOST | plain discounting exists (`DESIGN_INFINITIES.md:185`, gamma 0.99); the owner's asymmetric framing does not |
| B18 | Punish the prediction head **scaled by severity**, judged by the value function | `ideas.md:55` | **LOST (L9b)** | nowhere |
| B19 | Opponent prediction as an **auxiliary task on objective truth**, not on game reward | `ideas.md:60-63` | parked | `METRICS.md` `E-HEAD` calls for the decoder and records that the belief vector *"has no supervision anywhere"*. Measured, never designed |
| B20 | *"It should be more important to predict a lower-probability high-impact scenario"* | `ideas.md:66` | **LOST (L4)** | nowhere. The best unrecorded reasoning in the notes |
| B21 | Cost-sensitive weighting `L_weighted = W(s) * L_aux`, `W(s)` proportional to `abs(V(s))` | `ideas.md:76-95` | **LOST (L4)** | nowhere |
| B22 | Weighted rollouts: sample hands from `P(hand given s)`, let UCB stress the rare-but-lethal | `ideas.md:104-121` | parked | adjacent to ISMCTS |
| B23 | Opponent **policy** head as the blueprint policy inside MCTS; best-response training | `ideas.md:128-149` | LOST as a design | `METRICS.md` `ST-7` measures best-response exploitability. Nothing trains toward it |
| B24 | KV-cache board states across an action sequence | `ideas.md:154-156` | on-path | `BACKLOG.md:76`; `DESIGN_LATENCY.md` §2.4; `DESIGN_TRAINING.md` Tier A |
| B25 | Optimise the ability "vocabulary" as a first-class efficiency lever | `ideas.md:159` | on-path | `DESIGN_CARD_POOL.md` Step 1; `DESIGN_ACTION_SPACE.md` §6.5 |
| B26 | Refine the **context window** | `ideas.md:160` | on-path | `DESIGN_TRAINING.md:123`, T 428 to 256 |
| B27 | **TurboQuant** for the card-embedding vector database | `ideas.md:162-164` | **LOST (L8)** | zero hits anywhere. Directly blocks §2 |
| B28 | Teacher reward as matchup **win-rate delta** | `ideas.md:166-169` | on-path, improved | `DESIGN_TEACHER.md` §1, §1.6 corrects the within-block form to a revisit form with measured SNR |
| B29 | **Mirror matchup mastery**, 50 games each side | `ideas.md:171-179` | on-path, cited, partly refused with numbers | `DESIGN_TEACHER.md:108,860` keeps it as a bias control and broken-deck detector, refuses it as variance reduction at a measured 1.00x |

### 3.3 The 237 lines destroyed in `db5e024`

Now at `docs/recovered/RL_ARCHITECTURE_pre_db5e024.md`. Line numbers are the original file's.

| # | idea | line | status | where it is now |
|---|---|---|---|---|
| C1 | DB lookups happen **once at card load**, not per rollout | `:17` | on-path | `DESIGN_TRAINING.md:74-78` |
| C2 | Dynamic entity tokens: component embedding, stats, zone, controller | `:28-35` | on-path | `DESIGN_TRAINING.md:70,105` |
| C3 | **Global summary tokens** over zone counts and deck composition | `:37-39` | on-path | `DESIGN_CARD_POOL.md:180-184`; `DESIGN_TRAINING.md:59` |
| C4 | **Short history tokens**: last K actions | `:41-49` | parked | `BACKLOG.md:44` only |
| C5 | Belief vector `b_t` from a small RNN/GRU/MLP | `:59-63` | parked | `BACKLOG.md:44`; `DESIGN_TRAINING.md:105` lists the head, never specifies it |
| C6 | **Three encodings for multiple opponent scenarios**, with a pros/cons table | `:64-66`, `:163-171` | parked | `BACKLOG.md` names them; **no design doc adopts one** |
| C7 | Deterministic bookkeeping of exact opponent card counts, *"maintains mass conservation"* | `:68-71` | parked | `BACKLOG.md:44`; `METRICS.md` `CLS-3` uses the counting null as the **ruler** rather than as an input |
| C8 | Optional particle sampling of M plausible opponent states | `:73-75` | parked | `BACKLOG.md:44` |
| C9 | **Supervised pre-training of the belief net from self-play logs** | `:77-79` | parked | `BACKLOG.md:48` |
| C10 | `rethink_counter` as an integer token in the observation | `:90` | on-path | `DESIGN_LATENCY.md` §3.4 |
| C11 | **Frozen board cross-attention** | `:95-98` | on-path, cited by commit hash | `DESIGN_TRAINING.md:66-67`; `COST_MODEL.md` |
| C12 | **Iterative memory and action memory**, so a pass can critique its own plan | `:100-103` | on-path | `DECISIONS.md` D11 |
| C13 | **Rethink compute penalty**, so the model learns its own stopping point | `:105-107` | on-path | `DECISIONS.md` D11; `DESIGN_LATENCY.md` §3.2-3.3 |
| C14 | Only the **latest** iteration reaches policy and value | `:110` | on-path | `DESIGN_LATENCY.md` §3.5 |
| C15 | **Dynamic action sequences with reward only at the end of the phase sequence** | `:113-117` | **LOST as a recorded alternative** | `DESIGN_ACTION_SPACE.md` §4.3 gives every step its own advantage and §4.7 makes ending a plan cost something. Better, and **no doc records that the owner's version was considered**. See §4.10 |
| C16 | Teacher builds decks card by card via a **Query Vector** plus **Vector Search** | `:136-138` | on-path | `BACKLOG.md:83`; `DESIGN_TEACHER.md` §4.3; `DESIGN_CARD_POOL.md:184`. **This is §2** |
| C17 | Teacher input: *"win rate, 'confidence' gap, or reasoning depth used"* | `:139` | on-path, credited | `DESIGN_TEACHER.md` §1.4; `recovered/README.md` credits it for anticipating the noise study |
| C18 | Teacher reward is the **Student's Learning Progress** | `:140-142` | on-path | `DESIGN_TEACHER.md` §1.4, §2.2 |
| C19 | **Matchup history and diversity bonus** to break A beats B beats C beats A | `:145-147` | on-path, reshaped | `DESIGN_TEACHER.md` §2.3: *"diversity is a constraint, not an objective"* |
| C20 | Deck rotation as **generalisation pressure** on the board encoder | `:148` | on-path | `DECISIONS.md` D14; `METRICS.md` GEN family |
| C21 | Illegal Teacher proposals **penalised** | `:151-153` | refused, openly | `DESIGN_TEACHER.md` §8: legality is a rule of Magic, so it is a hard mask, never a reward term |
| C22 | *"history is only directly used to generate the belief vector... do not embed into every entity token"* | `:180,183` | on-path | `BACKLOG.md:49-51`; reused by `DESIGN_CARD_POOL.md` for pool tokens |
| C23 | Efficiency ladder: zone-local dense attention, top-K attention, low-rank attention, hierarchical pooling, incremental belief updates | `:189-193` | mostly LOST (minor) | **only hierarchical pooling survives** (`DESIGN_TRAINING.md:59`). Four of five options unrecorded |
| C24 | *"Scalable representation for up to 300 entities"* | `:234` | on-path | `DESIGN_TRAINING.md:123` T = 256; `ARCHITECTURE.md:33` measures 214 entities at a Commander start |

### 3.4 `MTG_bot/mtg_token_encoding.md`, 124 lines, referenced by nothing

**The single highest-value recovery on this list.** See §4.1.

| # | idea | line | status |
|---|---|---|---|
| D1 | The problem: unbounded token creation, per-token counters, combinatorial action explosion, and pre-allocated slots being wasteful | `:7-19` | **LOST (L1)** |
| D2 | **Composite entity** per token type per player, aggregate stats in one encoder slot | `:29-36` | **LOST (L1)**. `DESIGN_CARD_POOL.md` stores identical tokens as a multiset with a count, which is *storage*. Nothing says what the *network* sees |
| D3 | **Internal token JSON** preserving per-token attributes for exact simulation | `:38-43` | **LOST (L1)** |
| D4 | **Hierarchical action space**: policy emits "attack with 3 tokens", a deterministic layer maps it to individuals | `:45-51` | **LOST (L1), and the live design goes the other way** |
| D5 | **Mini entity-encoding**: attention or max/min/median **pooling** over individual token vectors | `:113-118` | **LOST (L1)** |
| D6 | The honest trade-off table: fixed size yes, full information internally only, individual treatment partial | `:4` | **LOST (L1)** |
| D7 | Edge case: 20 tokens with different `+1/+1` counters need weighted averages or sub-grouping | `:81-84` | **LOST (L1)** |

### 3.5 `docs/card_embedding_architecture_sketch.png`, committed in `000e37c`, referenced by nothing

| # | idea | status | note |
|---|---|---|---|
| E1 | Card embedding from a name query through three parallel channels, concatenated to **2346 dims** | **LOST (L2)** | the whole architecture the owner drew |
| E2 | Channel 1a: **numeric encoding** from Scryfall | on-path | `DESIGN_TRAINING.md:105`, 96-dim component MLP |
| E3 | Channel 1b: **NLP encoding of the rules text box** (1306 dims jointly with 1a) | **LOST (L2)** | zero hits for `NLP`, `text embedding`, `language model` across `docs/`. `DESIGN_CARD_POOL.md` rejects English substrings as an *intermediate representation*, which is a different claim |
| E4 | Channel 2: **17Lands meta-information**, 16 dims, as a *card feature* | **LOST (L2)** | 17Lands appears twice in `docs/` and both times only as a candidate *evaluation corpus* |
| E5 | Channel 3: **card art RGB into an autoencoder**, 1024 dims | **LOST (L2)** | card *recognition* from photos is correctly killed in `attic/`. That is vision-as-input-device. This is **art as a signal about the card**, and killing one does not address the other |

### 3.6 `project_goals.md`, `project_specific_gemini_context.md`

| # | idea | source | status | where it is now |
|---|---|---|---|---|
| F1 | Dual purpose: Teacher RL for training **and** a real player utility | `project_goals.md:12-14` | on-path | `NORTH_STAR.md` §4a; `DECISIONS.md` D15 |
| F2 | **Stockfish-style top-3 moves** with a move line | `:15` | parked | `BACKLOG.md:81` |
| F3 | Draft from empty **or** complete a partial deck | `:15` | on-path | `NORTH_STAR.md` §4a; `DESIGN_DRAFTER.md` §3.6 |
| F4 | Deck synergy analysis for humans | `:14` | parked | `BACKLOG.md:91` |
| F5 | Card recognition, scraping, OCR, image vector DB, hard-negative mining | `:19-60`, `notes.txt:1-29` | parked, explicitly | `attic/README.md`; `BACKLOG.md` *"Abandoned, do not revive"* |
| F6 | *"NO BACKGROUND in vector database"* / *"INCLUDE background in training samples"* | `notes.txt:12-13` | parked | same |
| G1 | `effects_json` components are *"essential for... generalization to new or unseen cards"* | `gemini:8` | on-path | `DECISIONS.md` D2 quotes the equivalent reasoning verbatim |
| G2 | **Encode, predict opponent, encode again with the prediction** | `gemini:15-18` | **LOST (L7)** | nowhere. The Tier A / Tier B split is a *caching* two-tier, structurally different |
| G3 | Value network refined by **PUCT MCTS on N leaf nodes** | `gemini:19-20` | parked | search parked generally; PUCT never named |
| G4 | Decoder emits **K action tokens**, each a sub-choice | `gemini:21` | on-path | `DESIGN_ACTION_SPACE.md` §1.3, up to 16 typed fields |
| G5 | *"The logic for determining the number of actions in a round (when to 'pass') is not yet decided"* | `gemini:22` | on-path, **closed** | `DESIGN_ACTION_SPACE.md` §4.7; `DECISIONS.md` D11 |
| G6 | Sequence length must allow *"a low probability of requiring future re-construction to support new cards"* | `gemini:23` | on-path | `DESIGN_ACTION_SPACE.md` §6.3, §6.5, §1.5 |
| G7 | Full rollouts plus BPTT | `gemini:27` | on-path, downgraded with consent | `DECISIONS.md` D6. Owner: *"I want BPTT just because it is cool, but of course we need to test both"* |
| G8 | Embedding sizes *"sufficiently complex to handle the scope of MTG, both current and future"* | `gemini:29` | on-path | `COST_MODEL.md`; `DECISIONS.md` D5 |
| G9 | *"Testing and logging everything is of utmost importance at all times"* | `gemini:34` | on-path | `TRAINING_REVIEW_PROTOCOL.md`; `METRICS.md` §15 |

### 3.7 `thought_checkpoint.md`, tasklists, `MTG_bot/docs/`

| # | idea | source | status | where it is now |
|---|---|---|---|---|
| H1 | **Semantic Pointer Network**: intent-descriptor matching, not menu indices | `thought_checkpoint.md:4-5` | implemented, now instrumented | `DESIGN_ACTION_SPACE.md` §3.1; `METRICS.md` `DQ-13` adds the invariance probe |
| H2 | Efficiency/urgency penalty of -0.005 per step | `thought_checkpoint.md:12` | implemented, scheduled for removal | `BACKLOG.md` scaffolds table |
| H3 | Conditional win-length penalty applied **only on wins**, *"to avoid premature surrender behaviours"* | `bptt_implementation_notes.md:5-9` | partly LOST | the term is in the scaffolds table; **the premature-surrender reasoning is not recorded** |
| H4 | Analyse the Teacher's deck bias for **independent discovery** of the 40/60 ratio | `thought_checkpoint.md:24` | **DISTORTED (S2)** | `METRICS.md` `DFT-5` tests conformity to a declared heuristic. Opposite epistemics. See §5.2 |
| H5 | Fine-tune pointer matching if card classes are ignored | `thought_checkpoint.md:25` | on-path, improved | `METRICS.md` `DQ-11 class_coverage_gap`, *"the cheapest high-value instrument in the catalogue"* |
| H6 | M21 synthetic dataset, 100k board states, to pre-train the encoder | `MTG_bot/docs/TASKLIST.md:33` | parked | `BACKLOG.md:77` |
| H7 | ISMCTS; weighted auxiliary loss for mid-game win probability; dynamic RL Teacher | `MTG_bot/tasklist.md:46-48` | parked / on-path / settled | `METRICS.md` `E-HEAD`; `DECISIONS.md` D15 with measured numbers |
| H8 | Architecture search, 4 layers versus 8 | `MTG_bot/docs/TASKLIST.md:39` | on-path | `DESIGN_LATENCY.md` §5.4; `DECISIONS.md` D5 |
| H9 | GUI visualizer for the GameGraph | `MTG_bot/docs/TASKLIST.md:41` | on-path | `DESIGN_SPECTATOR.md` |
| H10 | Puzzle ladder **levels 3 and 4** | `progression_playbook.md:36-56` | parked, cited | `BACKLOG.md:59-62`, *"unreachable until the engine has real priority"* |
| H11 | *"A bot's success must be measured by its ability to navigate heuristics, not to brute-force a game tree"* | `progression_playbook.md:6` | partly LOST | the evaluation philosophy is not restated anywhere |
| H12 | Puzzles scored on **incremental advantage**, and every puzzle **concept-tagged** so cards hot-swap across sets | `progression_playbook.md:62-69` | partly LOST | `METRICS.md` §10 rebuilds PZL. **The concept-tagging scheme for cross-set transfer is not carried over**, and it is the half that serves tied-rank-1 |
| H13 | Effect-system mandates plus a **Chaos Test suite**: illegal target mid-resolution, zero and negative values, empty pools, circular dependencies | `EFFECT_SYSTEM_MANDATES.md` | partly LOST | `BACKLOG.md` carries the anti-hardcoding mandate. **The stress-test catalogue is in no metric or protocol** |
| H14 | Logged engine gaps: stack LIFO, multi-step choices, **replacement effects do not exist** | `EFFECT_SYSTEM_MANDATES.md` §4 | on-path, cited | `BACKLOG.md` reproduces all three and adds seven more |
| H15 | Benchmark metrics including `avg_mana_efficiency` | `MTG_bot/docs/BENCHMARKS.md` | on-path, gap named | `METRICS.md:788` records that neither numerator nor denominator exists |
| H16 | Set-first scenario hierarchy and set-isolated generation | `PROCEDURAL_SCENARIOS.md` | on-path | `METRICS.md` §10 |
| H17 | *"Update the tasklist with things out of scope or for the future, so we can come back to them without disturbing you"* | `MTG_bot/tasklist.md:8` | on-path | the ancestor of `BACKLOG.md`'s two rules and `NORTH_STAR.md` §2 |

### 3.8 Navigation debt

| # | issue |
|---|---|
| I1 | `MTG_bot/INDEX.md` points agents at the **48-line remnant** `MTG_bot/docs/RL_ARCHITECTURE.md` as the primary RL doc, and at `project_goals.md` as the vision rather than `NORTH_STAR.md`. It names no file under `docs/` |
| I2 | `MTG_bot/notes.txt`, `MTG_bot/mtg_token_encoding.md`, `MTG_bot/TODO.txt`, `thought_checkpoint.md`, `engine_map.md`, `project_specific_gemini_context.md` and the sketch PNG appear in **no index anywhere**. This file is now that index |
| I3 | `MTG_bot/docs/AGENT_GUIDELINES.md` tells every agent to read `INDEX.md` and `MTG_bot/docs/TASKLIST.md` first, which contradicts `CLAUDE.md` and routes new sessions into the stale tree |

---

## 4. The LOST ideas, in the owner's words

Nine headline items. Each one gets the owner's own text, then a position on what should happen.

### 4.1 L1: the composite / super-token encoding, and the hierarchical action space

**Source: `MTG_bot/mtg_token_encoding.md`, 124 lines, cited by nothing.** The owner:

> *"Represent multiple identical tokens of the same type as a single **composite entity**, while
> maintaining **internal structure** for individuality."*

> *"**Level 1 (Policy Output):** The policy network outputs actions for the Composite Entity (e.g.,
> 'Attack with 3 tokens,' 'Put a counter on 1 token,' 'Block with 2 tokens'). **Level 2 (Action
> Mapping):** A separate, deterministic system uses the full individual state (internal JSON) to
> select the optimal individual tokens to execute the policy's chosen action. This offloads the
> combinatorial token-selection problem from the neural network to the game engine."*

> *"use a pooling mechanism (e.g. attention or max/min/median pooling) over the individual token
> feature vectors to generate the composite entity embedding. This makes the fixed-size aggregate
> vector much more sensitive to the distribution and extremes of individual token properties (like
> the highest P/T token or the median number of counters)."*

And the owner's own honest accounting of the cost, which is the part that makes it a design rather
than a wish:

> *"Treat Tokens as Individual: **PARTIALLY**. The policy network only reasons over the aggregate
> stats. An action that requires choosing specific individual tokens (e.g. 'block this 3/3
> attacker with tokens 1 and 7, but not 2') cannot be output directly by the policy head."*

**Why this is the highest-value recovery.** `DESIGN_ACTION_SPACE.md` §10.3:1096 is an open question
marked "needs deeper reasoning" which says, of `ATTACK_SET` and `BLOCK_ASSIGN` canonicalisation:

> *"8 blockers against 5 attackers with a d=256 decoder is not obviously in the regime where the
> sort is learnable for free... a representational ceiling there would present as 'the bot blocks
> adequately but never finds the good multi-block', which is indistinguishable from ordinary
> weakness."*

**The owner wrote a 124-line answer to that exact question, and it is uncited.** D4's hierarchical
split is precisely a proposal to remove the combinatorial surface §5.5 currently canonicalises over.
`DESIGN_CARD_POOL.md`'s multiset-with-a-count handles **storage**; it says nothing about what the
**network** sees, and D2 and D5 are about exactly that.

**What should happen.** Adopt or refuse, in a live doc, in the style of the Tarmogoyf overrule.
Both are defensible. The case against D4 is that the deterministic Level 2 mapper is authored
strategy in disguise, which `NORTH_STAR.md` §3 defaults to no: "select the optimal individual
tokens" is a policy decision, and hiding it in the engine hides it from learning. The case for D5
is much stronger and nearly free: max/median pooling over identical tokens is a **representation**
choice, not a strategy choice, and it costs one pooling op. **My position: refuse D4, adopt D5, and
say both out loud with the reasons.** Now in `BACKLOG.md`.

### 4.2 L2: the card-embedding architecture the owner drew

**Source: `docs/card_embedding_architecture_sketch.png`, committed in `000e37c`, referenced by zero
files.** It specifies a 2346-dimension card vector assembled from a name query through three
parallel channels:

| channel | dims | status in `docs/` |
|---|---|---|
| numeric encoding from Scryfall (pips, type line, subtype, P/T, rarity) **plus NLP encoding of the rules text** | 1306 | numeric half on-path; **NLP half absent** |
| 17Lands API meta-information | 16 | absent as a card feature |
| card art RGB into an autoencoder | 1024 | absent |

`DESIGN_CARD_POOL.md` builds `v_card` from the ability tree, component features and the atomic
residual. **All three of the owner's other channels are missing and no document says why.**

**What should happen.** Each channel needs one paragraph, adopted or refused.

- **Rules-text NLP as a side channel.** `DESIGN_CARD_POOL.md` rejects English substrings as an
  *intermediate representation*, which is a rejection of regex parsing, not of a learned text
  encoder running alongside the tree. These are different claims and only one has been argued. A
  frozen sentence encoder over oracle text is a legitimate **residual** in exactly the sense the
  atomic-id residual is legitimate, and it has the same diagnostic: the ratio of its norm to the
  composed vector's norm. My position: refuse it for v1 on the grounds that it competes with the
  compiler for the same signal and weakens the coverage pressure that makes the unparsed-text queue
  work, but **say so**, because silence here is what `db5e024` was.
- **17Lands.** Refuse for Commander with the reason already written at `METRICS.md:634` (Limited
  only), and note the general principle: real-world play statistics are exactly the "printed rate
  versus format" signal the atomic residual is there to absorb, so adding them as a channel is
  double-counting.
- **Card art.** Refuse, and give a reason that is not the reason given for card recognition. Art
  correlates with card identity, which is the thing the tied-rank-1 goal wants the model **not** to
  key on: a model that recognises a card by its art has memorised, and memorised embeddings are
  hardcoding by gradient descent (`METRICS.md` `GEN-3`). That is a real argument. "We killed OCR"
  is not.

### 4.3 L3: relational bias in the attention mechanism

**Source: `MTG_bot/notes.txt:63`.** The owner:

> *"**Encoding Relationships:** The game state is a graph (a counter is *on* a creature; an aura is
> *attached to* a creature). We will encode these relationships by adding a **Relational Bias** to
> the Transformer's attention mechanism. This forces the model to learn the structure of the game
> rules by biasing its attention towards linked entities."*

**Status: silently dropped.** `DESIGN_CARD_POOL.md` Step 2 rejects a tree GNN, but that is about
the **card ability tree**, a different object. The **board** encoder at `DESIGN_TRAINING.md:64-90`
is plain self-attention over flat `[pool][seat][zone][object]` tokens with **no edge encoding at
all**. `ARCHITECTURE.md:33` measures 214 entities and **412 relationships** at a Commander start,
so the edges outnumber the nodes two to one and the current design encodes none of them.

**What should happen.** This is not a small idea and it is not the same as the tree question. An
additive attention bias `b_ij` keyed on a small typed edge vocabulary (attached-to, controlled-by,
counter-on, blocking, targeting, in-zone) is cheap, is stock, and is the standard fix for exactly
the binding problem the owner named at `notes.txt:150`. The counter-argument is bandwidth: on a
GB10 an `N x N` bias tensor per layer is memory traffic, and `NORTH_STAR.md`'s hardware note says
memory traffic per decision is the scarce resource. That is a measurable trade, not a reason for
silence. **Position: put it on the backlog with the measurement that would decide it.** Done.

### 4.4 L4: cost-sensitive auxiliary loss, weighted by the impact of the state

**The single best piece of unrecorded reasoning in the notes.** `ideas.md:66`, the owner's own
question:

> *"But then lets say the H_opp starts to perform well, but it is not predicting the things that
> result in the highest win-rate, but rather the most probable scenarios. It should be more
> important to predict a lower-probability high-impact scenario, than the opposite. So how do we
> teach it this if we dont impact that head with the result of the games?"*

And the answer the owner recorded at `ideas.md:76-95`:

> *"The solution is not to directly tie the auxiliary loss to the reward, but to influence the
> auxiliary loss itself to be **cost-sensitive to high-impact scenarios**... `L_Weighted = W(s) *
> L_Auxiliary`... **Weighting by Value/Exploitability**: The weight could be proportional to the
> absolute value difference `|V(s) - 0|` for zero-sum games... A state that leads to a huge swing
> (a V(s) close to +1 or -1) is more salient than a neutral state. By using this weighted loss, the
> auxiliary head is trained to be more accurate on the situations that matter most for the final
> game outcome, even if those situations are rare."*

**Why it is load-bearing and not a detail.** `METRICS.md` `CLS-3` measures belief AP and goes to
considerable trouble over the candidate set and the counting null, precisely because the naive
metric flatters a head that has learned the base rate. The owner's insight is the **training-side**
version of the same observation: a head trained on unweighted cross-entropy over a sparse label
will learn the base rate, because that is what minimises the loss. `METRICS.md` `E-HEAD` records
that the belief vector *"has no supervision anywhere"*. When that supervision is finally written,
**this is the form it should take**, and today nothing in the repository says so.

**What should happen.** It is a one-line change to a loss that does not exist yet, with a real
failure mode if omitted, and it has a free diagnostic already specified: report `CLS-3` split by
`abs(V(s))` quantile. If the head is uniformly accurate across quantiles it has learned the prior;
if it is better in the high-swing tail it has learned inference. Recorded in `BACKLOG.md` attached
to the belief-vector entry.

### 4.5 L5: the worst-case-opponent trap

**`ideas.md:14-15`, an open architectural question the owner asked and nobody answered:**

> *"How do we avoid that the model predicts the opponent to have the worst case possible deck, and
> that we then play against that strategy, in scenarios where playing optimally against the hardest
> possible opponent-state combination results in exposing us to some of the also likely, but less
> consequential opponent-state combinations?"*

> *"Is this learned implicitly in win-rate and rewards, or do we need to handle that we dont expose
> us to scenario 2,3,4 by playing optimally aginst scenario 1, if they are all somewhat equally
> likely?"*

**This is a real question with a real answer and the answer is not obvious.** It is the difference
between a maximin policy and a Bayes-optimal policy under the belief. Determinized search with
per-determinization optimal play is known to produce exactly this pathology (strategy fusion and
non-locality). The honest answer is: **it is learned implicitly only if the belief is calibrated
and the search averages over it correctly, and both of those are things this project has parked.**
L4's impact weighting pulls in the opposite direction, toward paranoia, which is precisely why the
two must be reasoned about together rather than adopted separately.

**What should happen.** It belongs in `BACKLOG.md` under open questions, phrased as the owner
phrased it, so that whoever writes the belief and search design has to answer it before shipping.
Added.

### 4.6 L6: opponent archetype detection, and continuous strategy

**`MTG_bot/notes.txt:20-22`:**

> *"Opponent archetype detection, then probabilistic inference of their hand conditioned on the
> archetype."*

**`ideas.md:25`, refining it:**

> *"Separate NN to predict opponent hand and deck and strategy (dont predict discrete strategies,
> use RGB approach maybe)?"*

**The second quote is the important one and it is recorded nowhere.** "RGB approach" means a
continuous strategy space rather than a set of archetype classes: a point in a low-dimensional
space, the way a colour is a point rather than a label. That is a genuine architectural position,
it is the right one, and it is the difference between a softmax over authored archetypes (which
`NORTH_STAR.md` §3 would refuse as hand-authored taxonomy) and a learned latent.

There is a live tension to name: `METRICS.md` `VAR-10 opponent_identity_probe` is an **alarm
against** encoding opponent identity, on the grounds that the only use of it is exploiting a
metagame that does not exist. That alarm is about **who** the opponent is. The owner's idea is
about **what they are doing**. Those are different, and a design must distinguish them or `VAR-10`
will fire on the feature it was never meant to catch.

**What should happen.** Recorded in `BACKLOG.md` with the continuous-not-discrete constraint and
the `VAR-10` tension both stated.

### 4.7 L7: two-pass encoding

**`project_specific_gemini_context.md:15-18`:**

> *"**First Encoding**: The game state is encoded based on the *visible game-state*. **Opponent
> Hidden Prediction**: An 'opponent-hidden-predictor' is run... **Second Encoding**: The game state
> is encoded *again*. This second encoding incorporates the visible game-state *and* the latest
> output from the 'opponent-hidden-predictor'."*

**Not captured, and easy to mistake for something that is.** `DESIGN_TRAINING.md`'s Tier A / Tier B
split is a **caching** two-tier: Tier A encodes the board once and Tier B cross-attends per
decision. In it, belief is an auxiliary head hanging off Tier B and is **never fed back into the
encoder**. The owner's version is a genuine feedback loop, and it is the same shape as C12's
iterative memory, which **was** adopted (`DECISIONS.md` D11).

**What should happen.** Note that D11's rethink loop already provides the mechanism: a second
reasoning pass that sees the first pass's output could see `b_t` at no structural cost, since the
loop exists and is paid for. That is the cheap version of L7 and it should be recorded as such
rather than rediscovered. Added.

### 4.8 L8: TurboQuant, and the missing index

**`ideas.md:162-164`:**

> *"**Vector Database Optimization (TurboQuant)**: If using card embeddings rather than just atomic
> encodings, investigate **TurboQuant** methods to accelerate similarity searches and retrievals
> from the card embedding vector database. This is particularly relevant for scaling the number of
> cards the bot can recognize and reason about efficiently."*

**Zero hits anywhere in the repository.** And it is not a future concern: `DESIGN_CARD_POOL.md:184`
specifies `retrieve_topk(query(board, belief), legal_pool)` with `k = 64..256` **on every decision**
and names no ANN method, no quantisation scheme, no recall bound and no rebuild cadence. The owner
had already flagged the exact problem. See §2.2 for what the index actually has to satisfy.
Recorded in `BACKLOG.md` as a rank-1 item, because the clock is rank 1.

### 4.9 L9: two mechanisms for the opponent-prediction head inside search

**(a) `ideas.md:52`:**

> *"keep this opponent prediction fixed for the remainder of the simulation... avoid risking to have
> to re-run the opponent prediction NN"*

**(b) `ideas.md:55`:**

> *"After each MCTS, reward/punish the prediction head, scaled based on severity of wrongful
> predictions, based on the value-function analysis of how severe the wrongness was."*

Both are absent. `BACKLOG.md` parks ISMCTS generically and neither mechanism is recorded.

(a) is a **cost** decision with a real consequence: a fixed determinization per simulation is what
makes ISMCTS affordable at all on this hardware, and it is also what creates the strategy-fusion
problem L5 asks about. (b) is L4 again, in the search loop rather than the loss: severity-weighted
credit to the belief head, with `V(s)` supplying the severity. **The same idea appears three times
in the owner's notes, from three directions, and is recorded zero times.** That repetition is the
tell that it matters. Attached to the ISMCTS backlog entry.

### 4.10 The minor losses, recorded so they are not re-lost

| id | idea | source | what should happen |
|---|---|---|---|
| A4 | Potential score: probability of drawing synergistic cards from the remaining deck | `notes.txt:18` | one line saying the critic subsumes it. Silence is the problem, not the omission |
| A26 | Top-k candidate re-rank with a final Q-value head at inference | `notes.txt:163,165` | say whether the single autoregressive decode is deliberate. It probably is (it is cheaper and the plan critic is trained), but no doc says so |
| B17 | Discount by how early the decision was, asymmetrically | `ideas.md:53` | plain gamma is not this. Record the difference |
| C15 | Reward only at the **end of the phase sequence**, to force global-turn optimisation | recovered `:113-117` | **`DESIGN_ACTION_SPACE.md` §4.3 does the opposite and is better argued (every step gets its own advantage, §4.7 makes ending cost something), but no doc records that the owner's version was considered and rejected.** This is exactly the shape of reasoning `db5e024` destroyed. Add the paragraph |
| C23 | Zone-local attention, top-K attention, low-rank attention, incremental belief update | recovered `:189-193` | four of five options unrecorded. They are the latency ladder and the clock is rank 1 |
| H11 | *"success must be measured by its ability to navigate heuristics, not to brute-force a game tree"* | `progression_playbook.md:6` | the evaluation philosophy behind the PZL family. Restate it |
| H12 | Concept-tagging every puzzle so cards hot-swap across sets | `progression_playbook.md:62-69` | this is the tied-rank-1 goal expressed as a test corpus. It should be in `METRICS.md` §10 |
| H13 | The Chaos Test catalogue: illegal target mid-resolution, zero and negative values, empty pools, circular dependencies | `EFFECT_SYSTEM_MANDATES.md` | four concrete engine stress tests, written by the owner, in no protocol. Nearly free to adopt |

---

## 5. Captured but different: the dangerous cases

**A distortion is worse than a loss.** A future agent reading a live doc will believe it has the
owner's idea and will never look further.

### 5.1 S1: revisiting niche decks became revisiting the student's retention

| | |
|---|---|
| **owner** | `ideas.md:3`: *"It is important for niche deck performance to revisit these and re-evaluate whether they are still viable, better or worse than when it was first tested."* |
| **docs** | `DESIGN_TEACHER.md:123,238`: `lambda_ret * (L(theta;P) - L(theta_{+M};P))`, revisiting a **matchup** M blocks later to measure whether the student's learning stuck |
| **the gap** | the owner's object is **a deck's viability in the current meta**. The captured object is **the student's retained skill**. Both are good. They are not the same, and only the owner's version keeps a niche archive honest as the league drifts |

`DESIGN_TEACHER.md` §1.6 measured the revisit interval carefully (SNR 0.04 within-block, 2.12 at
5,000 games, a 59x improvement). That is strong work on the **other** question. **What should
happen:** an archive-refresh policy, where an archived niche deck's stored `Phi` is re-estimated on
a schedule because the league it was scored against has moved. Without it the archive slowly fills
with decks that were good against a model that no longer exists.

### 5.2 S2: an emergence test became a compliance test

| | |
|---|---|
| **owner** | `thought_checkpoint.md:24`: *"Analyze Teacher's 'Deck Bias' to see if it discovers the 40/60 land-to-spell meta **independently**"* |
| **docs** | `METRICS.md` `DFT-5 finished_deck_quality`: land count *"against a declared heuristic"*, run as a pre-flight gate |
| **the gap** | the owner proposed **does it find the ratio unaided**. The doc implements **does it match the ratio we declared**. `DFT-5` as written **cannot detect discovery, only conformity** |

Both are legitimate and they are not substitutes. `DFT-5` is correct as a **gate**: if the deck is
broken the games measure nothing, and that is worth microseconds. But it can never answer the
owner's question, and if it is the only land-count metric the answer is unobtainable.

**What should happen:** a second, cheap row. Report the drafter's land ratio **distribution** with
the target curve removed from the loss entirely, against generation index. Convergence toward 40/60
from a model never told about 40/60 is evidence of discovery; convergence when the target is in the
gate is evidence of nothing. This is a `DFT-*` row, not a redesign.

### 5.3 S3: the standard the others fail

`notes.txt:72-79`, the Tarmogoyf/Maro argument, is **overruled correctly** in
`DESIGN_CARD_POOL.md` Step 3. The owner's conclusion is quoted, the counter-argument is given
(`*` is a lossy parse, not a primitive; in a proper tree the two cards are structurally different),
the owner's mechanism is kept anyway in a weaker form, and a diagnostic is shipped:

> *"**This settles the Tarmogoyf-versus-Maro objection from `notes.txt`, and I think that objection
> was wrong.**... **The fix belongs in the primitive vocabulary, not in an escape hatch.**"*

**That is the template.** Quote the owner, disagree in the open, give the reason, keep what is
salvageable, and ship the number that would prove you wrong. Every entry in §4 should be resolved
this way.

### 5.4 S4: a live instruction to violate a binding owner directive

| | |
|---|---|
| **owner, binding** | `NORTH_STAR.md` §5 and `DECISIONS.md` D3: *"train all the actions irregardless of how far down a plan it is before it is chosen (planning is important to keep)"*. D3 explicitly overturns the earlier audit that proposed deleting the plan decoder |
| **docs** | `DESIGN_TRAINING.md:118` still lists `Plan decoder \| 4L, 50.4M, 3 of 4 heads untrained \| **deleted** \| -50M dead weight`, and `:344` still says *"Delete the plan decoder; it gets no gradient anyway"* |

`DESIGN_ACTION_SPACE.md` §4 implements D3 correctly. `DESIGN_TRAINING.md` was never updated. **An
agent reading the architecture table will delete the head the owner explicitly ordered kept, and
will believe it is following the design.** This is the most immediately dangerous row in this
document. Logged in `BACKLOG.md` as a correction owed.

### 5.5 S5: two docs disagreed about the annealed lambda

| | |
|---|---|
| **owner** | `ideas.md:11`: *"`R_final = R(D) + lambda * Robustness(D)` - Annealing of robustness. High lambda punishes sharp minima/niche decks (good in the beginning), lower later to find niche decks."* |
| **`BACKLOG.md`** | listed it under ideas *promoted, now on the path* by D14 |
| **`DESIGN_DRAFTER.md` §9** | **refuses it**: *"a hand-authored schedule on a reward term, refused by `NORTH_STAR.md` §3"*, replaced by the curator's learned knob distribution |

Both cannot be true. **Resolution, applied in this pass: `DESIGN_DRAFTER.md` wins**, because it is
the later and more specific document, because the refusal is correct on the charter (an annealing
schedule is exactly the hand-authored curriculum §3 defaults to no), and because it supplies a
replacement rather than a deletion. D14 promoted *deck-space evolution*; it did not ratify every
mechanism in the bullet. `BACKLOG.md` now records the refusal inline and keeps the owner's original
words.

### 5.6 S6: correctly handled, listed so it is not mistaken for loss

`notes.txt:25-26` (evaluation scores as MCTS pruning) is parked **with a number attached**:
`DESIGN_TRAINING.md:352-363` shows the 1.6 microsecond per step the search needs against the 6
milliseconds `deepcopy` costs. That is the right way to park something. The pruning-by-learned-score
half is implicit in a policy-guided search and does not need separate rescue.

### 5.7 The reasoning at risk, which is the part `db5e024` actually destroyed

`db5e024` kept conclusions and threw away arguments. Four pieces of the owner's reasoning are in
that position now.

| | reasoning | state |
|---|---|---|
| 1 | *"A pure component model would see `id_Power_Star` for both `Tarmogoyf` and `Maro` and would be unable to learn that one `*` depends on graveyards and the other on hand size"* (`notes.txt:79`) | **safe.** Quoted and rebutted in `DESIGN_CARD_POOL.md` |
| 2 | *"Don't feed the model the answers (pre-computed scores); feed it the raw data and let it learn the concepts... by trying to predict the final outcome"* (`notes.txt:43-45`) | **the principle is captured, the derivation is not.** This is the owner **overruling their own earlier design** and it is the intellectual ancestor of `NORTH_STAR.md` §3. It should be cited there, because it shows the learnability principle was **earned** rather than imposed, and a principle with a derivation survives an argument that a principle without one does not |
| 3 | Compositional primitives create ambiguity about which component belongs to which card; the relational graph resolves it (`notes.txt:150`) | **safe.** Cited by name in `DESIGN_CARD_POOL.md` Step 2 |
| 4 | Low-probability high-impact prediction matters more than accuracy (`ideas.md:66`) | **nowhere.** This is L4, and it is the best unrecorded reasoning in the notes |

---

## 6. The recovered `RL_ARCHITECTURE.md`

Deleted in `db5e024`, 237 lines down to 48. Full text at
[`recovered/RL_ARCHITECTURE_pre_db5e024.md`](recovered/RL_ARCHITECTURE_pre_db5e024.md); recover
independently with `git show db5e024^:MTG_bot/docs/RL_ARCHITECTURE.md`. Quoted here because the
passages below are the ones that keep being re-derived, and because a quotation in a live doc is
found by grep while a file in `recovered/` is found only by luck.

**§4.1, frozen board cross-attention.** Now `DESIGN_TRAINING.md`'s Tier A / Tier B split, where it
is *"not an optimisation, it is a requirement"*:

> *"**Initial Pass:** The transformer encoder processes the raw board state (entities, zones, hand)
> into a fixed tensor: `Z_board`. This embedding is **frozen** for the rest of the phase.
> **Reasoning Passes:** In each iteration (i), the model generates a 'Reasoning Latent'
> `Z_reason_i`. **Connection:** During every reasoning pass, the model uses **Cross-Attention** to
> 'look back' at the frozen `Z_board`. This ensures every 'thought' is grounded in the factual
> state without re-encoding the raw data."*

**§4.2, iterative memory and self-critique.** Now `DECISIONS.md` D11:

> *"**Latent Memory:** The output hidden state of reasoning pass i is fed back into pass i+1 as a
> set of 'Memory Tokens.' **Action Memory:** The **proposed action sequence** from pass i is
> embedded and fed back as input to pass i+1. **Grounding & Critique:** This allows the model to
> 'critique' its own previous strategy. Pass 2 effectively sees: 'The board state is X, and my
> previous plan was Y. Upon further reflection, Y is risky because of Z.'"*

**§4.3, the rethink compute penalty.** Now `DECISIONS.md` D11 and `DESIGN_LATENCY.md` §3:

> *"During RL training, each rethink pass incurs a small 'compute penalty' (negative reward). The
> model will naturally learn the **Optimal Stopping Point**, rethinking only when the expected value
> gain from deeper thought outweighs the compute cost."*

**§4.4, dynamic action sequences.** The one place the current design deliberately departs, and the
departure was never written down. See §4.10 C15:

> *"The model predicts a sequence of actions. **The Value Function** only provides a reward signal
> at the *end* of the phase sequence (when `PassPriority` is chosen). This forces the model to
> evaluate the 'Global State Change' of an entire turn's worth of sequencing rather than individual
> taps or casts."*

**§5.1, the Teacher's query vector and vector search.** This is §2 of this document, written months
before it was proposed again:

> *"**Action Space (Intelligent Sequential Selection):** The Teacher builds decks card-by-card using
> a **Transformer-based Matchup Analyzer**. For each slot, the model generates a **Query Vector**
> based on the current deck's synergy and the opponent's strategy. It performs a **Vector Search**
> against the card embedding pool to find the optimal card to add. **Input:** The Student's
> performance on the previous matchup (e.g., win rate, 'confidence' gap, or reasoning depth used).
> **Reward:** The Teacher receives a reward based on the **Student's Learning Progress**. **High
> Reward:** Matches where the Student was initially wrong but 'learned' (improved value accuracy) or
> matches that were closely contested (High Entropy). **Low Reward:** Matches that were 'stomps' or
> impossible counter-matchups."*

**§5.2, breaking the meta-cycle.** Now `DESIGN_TEACHER.md` §2.3, reshaped into *"diversity is a
constraint, not an objective"*:

> *"**Matchup History:** The Teacher maintains a batch-wise history of recent deck matchups and
> results. **Diversity Bonus:** The Teacher is incentivized to explore 'niche' decks or unusual card
> combinations that the Student hasn't seen recently. **Generalization Pressure:** By strategically
> rotating decks, the Teacher forces the Student's `BoardEncoder` to learn universal MTG principles
> (e.g., 'mana advantage,' 'card parity') rather than just memorizing specific card interactions."*

**§3, the belief vector and the three multi-scenario encodings.** Still parked. The pros-and-cons
table is the part worth keeping, because it is the fork nobody has taken:

> *"**Belief vector (`b_t`)**: Learned via a small network (RNN, GRU, MLP). Input: short history
> tokens + current visible state. Output: fixed-size vector representing **posterior over opponent
> hand/deck and likely plays**."*

| approach | pros | cons |
|---|---|---|
| Top-K scenario embeddings, weighted by likelihood x impact | *"Explicit representation of multiple possibilities"* | *"Vector grows linearly with K"* |
| Aggregated expectation over scenario embeddings | *"Fixed-size vector, scalable"* | *"Potential loss of fine-grained scenario info"* |
| Scenario tokens the policy attends to | *"Rich reasoning over scenarios"* | *"Slightly higher compute; need masking for variable K"* |

**§7, the key principle that `DESIGN_CARD_POOL.md` reuses for pool tokens:**

> *"Key principle: history is only **directly used to generate the belief vector**. The action and
> value heads only see the distilled output (`b_t`), not raw history. This prevents computational
> bloat while preserving strategic inference."*

**§8, the efficiency ladder.** Only hierarchical pooling survives in any live doc (§4.10 C23):

> *"**Zone-local dense attention**: dense attention within battlefield, hand, or graveyard zones;
> inter-zone via summary tokens. **Top-K attention / learned focus**: attend only to most relevant
> entities or scenarios. **Low-rank / factorized attention**: approximate full attention with linear
> cost. **Hierarchical pooling**: represent large zones with summary embeddings; full entity detail
> only for high-impact entities. **Incremental belief updates**: compute `b_t` at root; incrementally
> update for child nodes in MCTS to reduce repeated computation."*

**§5.3, the one place the live design deliberately overrules it**, recorded so the overrule is not
mistaken for an oversight. The deleted doc said every Teacher proposal is engine-validated and
*"If the Teacher proposes an illegal state, it receives a penalty."* `DESIGN_TEACHER.md` §8 rejects
the penalty: legality is a rule of Magic, so it belongs in a hard mask, which is free and exact,
rather than in a reward term, which wastes samples and creates a surface to game.

---

## 7. How not to lose an idea again

Six rules. The first is the one that would have prevented `db5e024`.

1. **Never replace a design document. Append to it, or move the old one to `docs/recovered/`.** A
   rewrite that shortens a doc destroys the reasoning and keeps the conclusions, and the reasoning
   is the part the next session actually needs. If a shrink is genuinely right, the deleted text
   goes to `recovered/` in the same commit.
2. **An owner idea gets one of exactly three fates, and all three are written down: adopted,
   superseded (name the successor), or refused (give the reason).** Silence is not a fate. The
   template is `DESIGN_CARD_POOL.md` Step 3, which quotes the owner, disagrees in the open, and
   ships a diagnostic that would prove the disagreement wrong. **Refusal is fine. Silence is what
   `db5e024` was.**
3. **When you supersede an idea, quote the original by `file:line` inside the replacement.** Then
   grep finds it. Every entry in §3 marked "cited" survived because someone did this.
4. **When a doc uses the owner's word for a different object, rename it or say so.** S1 and S2 are
   both this failure: `revisit` and `deck bias` each mean one thing in `ideas.md` and a different
   thing in a design doc, and nothing warns the reader.
5. **Every new file that is not indexed does not exist.** `mtg_token_encoding.md` was written, was
   good, answered a question that is still open, and was read by nobody for a year because nothing
   pointed at it. New design writing lands in `docs/` and is linked from `NORTH_STAR.md`,
   `BACKLOG.md` or here.
6. **Update this file whenever the owner says something in a session.** It costs a table row. The
   standing instruction is the owner's own: *"keep remembering the important stuff in ideas and
   notes etc."* This file is the answer to that instruction, and it is worthless if it is only ever
   written once.

**Where new ideas go.** An idea that advances the ladder goes into a `DESIGN_*.md` and into
`BACKLOG.md` if it is not being built now. An idea that does not goes into `BACKLOG.md` with the
conflict named, per `NORTH_STAR.md` §2. Either way it gets a row in §3 of this file, with a
`file:line` citation to wherever the owner actually said it.
