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
| **Coherent-deck recipe (B-45)**: 2 seeded colours, 24 basics, 36 cards uniform within the colour pair | `core/executor/games.py` `build_coherent_deck` / `COHERENT_LANDS` (branch `sets/onboarding` 36adf48) | It chooses colours and land count, never which spells. Remove when decks come from a learned deckbuilder (draft/sealed or constructed), or replace the land count with a learned or sampled quantity. Opt-in only; the default stays the stress pile. |
| **K1 kill-test tooling limits** (offline tools, not the engine or the policy): 20 s wall clock per game, at most 60 rows per card per set, target scale clamped at 1e-3 | `tools/k1/gen.py` `--game-timeout`, `tools/k1/curve.py` `--cap`, `tools/k1/train.py` `y_std` clamp | The timeout drops straggling games, biasing data toward short games: remove once straggling games are understood (an engine stall rule or a perf fix). The row cap stands in for per-card loss weighting: replace it with weighting. The clamp lets a lane with no training variance dominate pooled R² (/166): take scales from the union pool, or drop such lanes from pooled R². |
| **Thirteen shaping reward terms** — damage, life, board presence, board delta, cards, action discovery, mana generation, proactivity, penalties | `strategic_brain/environment.py:164-211` | Replace with outcome plus at most a couple of defensible terms. A 200-step game currently accrues about +20 of shaping against ±10 for the actual result, so the agent is optimising the shaping. Remove once the engine is correct enough that winning is learnable directly. |
| **Proactivity bias** — subtracts up to 10 nats from every pass action's logit | `strategic_brain/student.py:126-129` | Delete. It is applied at collection but not at training, which pins the PPO ratio to e^±10 on every pass action. It exists to fight "the agent passes", which is a symptom of the reward and the dead action space, not of the policy. |
| **`MAX_MOVES_PER_STEP = 500`** | `rule_engine/engine.py` | Replace with the loop detection in [`DESIGN_INFINITIES.md`](DESIGN_INFINITIES.md) plus a wall-clock truncate-and-bootstrap. Currently it pays −10 to whoever found a combo. |
| **Five-repeat action block** | `strategic_brain/train.py:169` | Same. A combo body executed five times is exactly this pattern, so the anti-stall heuristic is a combo filter. |
| **100-step stall detector and forced mana stripping** | `strategic_brain/train.py:160,180-183` | Same. It dismantles a combo's mana engine mid-assembly. |
| **Epsilon-greedy exploration with a 0.15 floor** | `strategic_brain/train.py:94` | Replace with an entropy bonus in the loss. At 0.31, a third of all actions are uniform random and the policy is decoration. |
| **Four `1 - games/10000` difficulty ramps, a CMC step function, and a permanent SQL ban on every life-gain card** | `strategic_brain/teacher.py` | Replace with a self-play league. The "teacher" itself takes no optimizer step, so it is a frozen random MLP blended 50/50 with `random.random()`. |
| **Seven cards special-cased by literal name string** | `rule_engine/card_data_loader.py:86-119`, `rule_engine/engine.py:216,326,89` | Directly violates this project's own `EFFECT_SYSTEM_MANDATES.md`. Remove when the ability tree in [`DESIGN_CARD_POOL.md`](DESIGN_CARD_POOL.md) can express them. |
| **Hardcoded `torch.device("cuda")`** | `strategic_brain/student.py:34`, `teacher.py:37` | Route through `MTG_bot/utils/device.py`. On the dev box these silently fall back to CPU. |
| **Trigger quarantine after `MAX_TRIGGER_FIRES = 200`** (registered 2026-10-24) | `core/executor/binding.py:29-30,132,1137` | A rules deviation: the runaway source's trigger is switched off for the rest of the game, so combos silently die. Replace with the loop shortcut and CR 104.4b handling in [`DESIGN_INFINITIES.md`](DESIGN_INFINITIES.md). |
| **`TURN_CAP = 60` scored as a draw** (registered 2026-10-24) | `core/executor/games.py:131,1405-1407`; `tools/training/train_rl_v1.py:53` | A non-rules safety rail, and with draw = 0 > loss = -1 it pays a losing policy to stall (D10). Score it as a loss for both seats in training, report it separately in eval; remove once a real match clock exists. |
| **Stall rule = draw after 3 identical rounds** (registered 2026-10-24) | `core/executor/games.py:150,1370-1379` | Same incentive problem as the cap. Keep it as a progress probe, score it like the cap until optional-loop actions exist. |
| **10 acts per main phase, one main phase per turn** (registered 2026-10-24) | `core/executor/games.py:134,638-686` | Engine has no priority system; remove with the priority rung. |
| **Auto-tap-all mana before every act** (registered 2026-10-24) | `tools/eval/gameplay_eval_v2.py:314,336-353` | The tap amount is not an engine ask. Remove when payment folds into the cast (DESIGN_ACTION_SPACE §1.3) and mana empties per step (CR 500.5; done by V2 on branch `engine/verify-fixes`, 2026-10-29). |
| **The engine taps mana abilities for a payment asked outside the act window** (2026-10-29, B-90 option (a)) | `core/executor/legality.py` `plan_mana_taps` / `tap_for_payment`; callers `stack._window_taps` (counter and combat windows), `verbs._v_pay` with `query.optional_offer`, the `unless` lane of `verbs._v_counter_spell` | CR 601.2g / 605.3a let the payer activate mana abilities while paying; the engine picks a minimal set of the payer's untapped {T}-only mana abilities that the payment planner proves sufficient. The engine chooses the payment sources, a decision hidden from the player (AGENTS §10). Remove with the PAYMENT asks of DESIGN_ACTION_SPACE §1.3. |
| **Pack `mana` op** (2026-10-29, V2) | `tools/run_scenarios.py` | Mana empties as each step and phase ends (CR 500.5), so a pack that pays in a later act window adds the mana at that step, standing in for the lands the player taps there (the act window does not tap for the player). Remove with the act window's explicit taps, when payment folds into the move (DESIGN_ACTION_SPACE §1.3). |
| **Observation zone caps 6/8/12 and a 1024-token window** (registered 2026-10-24) | `tools/training/bc_data_v2.py:67-69`; `ab_duel.py:270-278` | 15,407 of 17,270 asks were truncated in the anchor run. Remove with the IR card tokenizer and a measured context budget. |
| **Benchmark: 3 strikes per decision, then the do-nothing choice** (2026-10-24) | `MTG_bot/bench/llm.py` | Bounds a non-answering model. Remove when tool mode gives structured answers; until then forfeits are always reported. |
| **Benchmark: `TAP_ALL_MANA`, X always 0, multi-slot rows hidden, one act window, stateless prompts, conservative hidden-card labels** (2026-10-24) | `MTG_bot/bench/router.py`, `protocol.py`, `llm.py` | Each mirrors an engine limit or is a harness simplification. Remove with the corresponding engine rung (payment, X asks, multi-slot designation, priority) and with tool mode (`notes` memory). |
| **Teferi, Master of Time's instant-speed window has no window to use** (registered 2026-10-29, branch `engine/phasing`) | `core/executor/legality.py` `ability_playable` (CR 606.3 loyalty window; the GRANT_ACTIVATION relaxation); `core/executor/games.py` and `MTG_bot/bench/router.py` (one act window per turn) | The legality oracle honours "You may activate loyalty abilities of Teferi on any player's turn any time you could cast an instant" (for Teferi itself only, CR 201.5c). The drivers ask for activations only in the active player's first main phase, so the opponent's-turn half and the own-turn combat half never get a window, and Teferi plays as a sorcery-speed planeswalker: weaker than printed (its [−3] can never remove an attacker or a blocker). Remove with the priority rung: an activation window for the non-active seat and inside each step. |

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
  *Clarification 2026-10-24:* that harness was an LM-Studio coding assistant. It is unrelated to
  the LLM benchmark the owner approved on 2026-10-24 as rank-1 instrumentation
  ([`DESIGN_BENCHMARK.md`](DESIGN_BENCHMARK.md)); only its public-leaderboard half is parked, below.

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

## Revealed by seeding the suite — 2026-09-11

Three tests were passing on a lucky roll and now fail consistently under
[`../MTG_bot/conftest.py`](../MTG_bot/conftest.py)'s fixed seed. They are **real failures that were
hidden**, not regressions, and they need fixing before P7 can be green:

- `rule_engine/test_dynamic_choices.py::test_runed_halo_choice_flow`
- `rule_engine/test_engine.py::test_play_land`
- `rule_engine/test_game_state.py::test_game_initialization`

All three assume a seat order or an opening hand that `initialize_game_state` assigns at random
(`game_initializer.py:45` picks the starting player, `:91` shuffles the library). Measured over six
consecutive runs before seeding, their pass count was 1, 1, 1, 2, 0, 1 out of 3. **The correct fix is
to make each test state the seat it means rather than to hunt for a seed that makes it pass.**

**Scaffold to remove:** `conftest.py`'s single fixed `TEST_MASTER_SEED`. It is the right default now,
but a conformance suite should eventually run over k seeds and assert the result is seed-independent,
which is what P13's seed band is for. **Removal condition:** once P13 exists, replace the constant
with a parametrised seed sweep.

## Parked, with the reason — added 2026-09-10 from the Spark session

**NeMo-RL (`nvcr.io/nvidia/nemo-rl`).** NVIDIA's RL toolkit, multi-arch on NGC. Parked rather than adopted:
it is shaped around LLM post-training (GRPO/DPO over HuggingFace models with vLLM rollouts), and this
project's rollout is a Magic rules engine with a command zone and four-player boards, not token generation.
The ladder is served by the environment and by batching inference across concurrent games, not by adopting
someone else's trainer. **Would unpark if:** the rollout ever becomes a generic vectorised env and the
bottleneck is the trainer rather than the simulator.

**Moving the project into the NGC container now.** Parked with a dated trigger rather than rejected. The
usual argument for it is false here (the pip wheel has 475 `sm_120` cubins and zero PTX, so there is no
PTX JIT to avoid; the container's own arch list stops at `sm_120` too). **Would unpark when:** the first
training number intended for publication or cross-month comparison is about to be produced, at which point
the job moves into the container pinned **by digest** and the digest is recorded beside the run. Detail in
[`HARDWARE_DGX_SPARK.md`](HARDWARE_DGX_SPARK.md).

**Generative card invention.** Already parked under D18; restated here only because the Spark session
confirmed the demand-ranked worklist half is cheap and the generative half is not.

## Corrections owed to the docs

Contradictions found in the 2026-09-10 notes audit. These are not decisions; they are files that
disagree with a decision already taken.

| # | where | what is wrong | what it should say |
|---|---|---|---|
| ~~**1**~~ **FIXED 2026-09-10** | [`DESIGN_TRAINING.md`](DESIGN_TRAINING.md) | ~~Both still order the **plan decoder deleted** (*"Delete the plan decoder; it gets no gradient anyway"*, and a `deleted \| -50M dead weight` row in the architecture table). [`DECISIONS.md`](DECISIONS.md) **D3 is a binding owner instruction to keep it and train every step**, and it explicitly overturns the earlier audit that proposed the deletion. `DESIGN_ACTION_SPACE.md` §4 implements D3 correctly; this file was never updated | the row becomes the trained multi-step decoder D3 requires, and `:344`'s graph-capture blocker gets the real fix (the `.item()` sync inside the plan loop) instead of a deletion. **Highest priority in this table: an agent following the architecture table would delete the head the owner ordered kept, and would believe it was following the design**~~ **Done:** the architecture row now reads "kept, and every step trained (D3)", the graph-capture blocker now says remove the `.item()` sync rather than the head, the ordering item now names only the 52.2M genuinely unreachable parameters, and a standing note at the top of §1 records that the earlier recommendation was superseded and why |
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

## Tickets 2026-10-07 (from T4 P1b review, PRE-EXISTING — not campaign-gated)
- B-19: rule_engine test_keywords::test_flying REAL logic failure (no-flying blocker can
  block a flyer; can_be_blocked_by=True). Legacy module outside campaign gates — decide:
  fix or deprecate rule_engine (duplicate engine surface?).
- B-20: test_model::test_reasoning_loop_can_actually_iterate fails (passes_taken={1} of 8)
  -> ALL historical multi-pass latency numbers rest on a broken loop. Re-validate or mark
  legacy before any latency claim.
- B-21: strategic_brain + test_full_system: 21 further failures, legacy.
- B-22: campaign gate scope decision: does M21 campaign ever run repo-wide pytest, or is
  core+tools the permanent contract? (Owner; affects §7 review completeness claims.)

## Tickets 2026-10-19 (OWNER DIRECTIVE — generalization & training program; model lane, parked until the atom-ontology lane closes its R-rounds)
- T-G1 FAIR generalization measurement: the random-choice baseline is too weak to be
  trusted (owner). Protocol to design: solid-volume self-play training PER SET
  (~100k-game scale or whatever is demonstrably converged — volume unknown until T-G3),
  then cross-play: M21-dedicated vs ZNR-dedicated models on the ZNR-only pool (and
  reverse). Reuses the /123 era-parity control machinery (frozen bsh_S3a_s3 2×2 grid).
- T-G2 multi-set fairness design: with 3+ sets, per-set dedicated models AND a combined
  main model at BALANCED per-set training volume; acceptance law = the more sets the
  main model trained on, the higher its ELO vs a one-set dedicated model.
- T-G3 set-mastery cost curve: measure compute-per-set-to-mastery (vs good opponents,
  full complexity) once a couple of sets ARE mastered; only then can time-saved from
  atomization be quantified.
- T-G4 keep per-set SPECIALIZED models as first-class artifacts (may be optimal for
  set-restricted games).
- T-G5 ELO/puzzle-system audit for set-transfer fairness (opponent control, pool
  separation, no era confounders) — decide before running the T-G1 matrix.
- T-G6 owner question, needs an answered audit: do our implementations use the 128 GB
  unified memory + compute throughput optimally? Is there any current size class where
  NVFP4 GEMM implementations pay off for speedup?
- T-G7 parallel training on the 128 GB box (multiple runs at once) — feasibility +
  throughput measurement; likely speedup for the T-G1 matrix.
- T-G8 capability-ceiling probes: CONTINUALLY train longer runs to find where ELO
  plateaus; when more complex play styles/techniques stop being learnable, that is the
  parameter-scaling signal (recurring law, not a one-off).
- T-G9 drafting + niche-deck play: still untouched by design (basics first) — stays queued.
- OWNER'S END-GAME CRITERION (context for the atom program): when a NEW set needs only
  atomized-subcomponent implementation + one-or-a-few keyword/mechanic adds + a little
  RL to master, the model is GENUINELY general — that is what the ontology R-rounds are
  building toward (§8 tokenizer law).

## Tickets 2026-10-24 (external adversarial review, [`REVIEW_2026-10-24.md`](REVIEW_2026-10-24.md))

- **B-23 Do not resume the RL pilot on the omniscient net.** Every admitted net encodes both hands
  and both library tops (`ab_duel.py:548-614`). Rebuild the observation on `MTG_bot/bench/view.py`'s
  per-seat projection first. REVIEW §3.1.1.
- **B-24 Rig misroutes asks.** `gameplay_eval_v2.py:150-157` sends asks it cannot attribute to the
  active player, and the handle list is built once (`:531`), so blocks by later tokens are answered
  by the attacker. Route by `DecisionStream.asking_seat` (added 2026-10-24); re-collect affected data.
- **B-25 Win rate drops draws and crashes from the denominator** (`gameplay_eval_v2.py:849-861`).
  Report W/L/draws-by-cause/crashes, and score draws as 0.5 in the headline.
- **B-26 MCTS values crashes and unfinished games at 0.5 / life-diff** (`tools/search/mcts.py:121-131`);
  the search fork is clairvoyant (`tools/search/fork.py`). Value crashes as losses for the searcher;
  determinize hidden state.
- **B-27 The RL update cannot move the policy**: one SGD step per 1000-game iteration at lr 1e-5,
  clip 1.0 (`train_rl_v1.py:131-132,253-255`; `rl_pilot_phases.sh:31`).
- **B-28 [opt-in fix on branch, /160: pool mode `compiled`; defaults unchanged] Partly compiled cards are dealt**: `engine_supported` ignores sentences that produced no
  atoms (`core/compiler/compiler.py:2259-2302`), against `DESIGN_CARD_POOL.md:219`.
- **B-29 CHOOSE_NAME leaks hidden zones**: the vocabulary lists every non-token card in the world
  (`core/executor/verbs.py:1543-1556`). Restrict to the legal pool, not the world.
- **B-30 `identity_of` drops oracle text and stamps `set_code="M21"` on every card**
  (`core/executor/games.py:326-348`).
- **B-31 Eval default `--out` is the tracked record** (`gameplay_eval_v2.py:107`, the PITFALL that
  struck again on 2026-10-19). Default to a timestamped path.
- **B-32 Fuzz with the model, not only RandomPolicy**: model play crashes the engine in about 5% of
  games (10/200, 12/200, 9/200 in the bc10 evals) while RandomPolicy fuzz reported 0/4000.
- **B-33 Legacy quarantine decision (owner)**: `rule_engine/` and `strategic_brain/` are dead.
  Their 21 failing tests now run as strict expected failures (`MTG_bot/known_failures.txt`); the two
  D3/D11 gates still fail visibly. Decide whether to move both packages to `attic/`.
- **B-34 `RandomPolicy.is_mana_activation` counts pure-TAP effects as mana abilities**
  (`core/executor/games.py:509-516`): "Tap target creature you don't control" (Shacklegeist) is
  classified as tapping for mana. RandomPolicy survives because it still designates targets; the
  bench router's tap-all crashed on it until `SeatRouter._is_mana` required ADD_MANA and no target.
  It also skews RandomPolicy's own act weighting. Fix the predicate.
- **B-35 Training modules monkeypatch the engine process-wide at import time**:
  `tools/training/packrec.py:149-150`, `packrec_v2.py:120`, `dagger_rollout_v3.py:169` and
  `puzzle_cert` replace `ExecCtx.take_decision` the moment they are imported. So any process, a
  test run included, that imports one of them plays every later game through a wrapper with the
  old `(self, vocab, what)` signature. Found 2026-10-24 when an engine call passing `seat=` was
  green in `pytest MTG_bot` and crashed 3 collector games in `pytest tools` (order-dependent).
  Patch inside a context manager scoped to the run, or give the engine a recorder hook instead.
  Until then `test_no_engine_call_site_passes_seat_to_take_decision` guards the signature.
- **B-36 [fixed on branch `sets/onboarding`, /160] A template pattern accepts words its builder cannot map**: the `B3-grant-kw-*` patterns
  (`core/compiler/templates_b3.py:989-1017`) take any lowercase word, `_KW_MAP` (`:90`) holds
  four keywords, so "…gains haste until end of turn" raises `KeyError`. It is not an honest
  refusal, so it takes down the whole set's compile and deal pool. M19 and KHM (2026-10-27,
  KNOWLEDGE /159). Build the alternation from the map. Then a pattern cannot outrun its builder.
- **B-37 [fixed on branch, /160] Vehicles crash the compiler**: printed P/T on a non-creature raises `ValueError`
  "non-creatures cannot have P/T" from `CardRecord` (`core/compiler/compiler.py:2205`). Five KHM
  vehicles and one THB. Refuse honestly (`StateCorruptionError`, a shape gap) until crew exists.
- **B-38 [fixed on branch, /160] Emblem attachment raises when the planeswalker is a back face**
  (`core/compiler/coverage.py:363` → `ability_tree.py:3361` "only a Planeswalker may carry an
  emblem"): KHM Valki, God of Lies // Tibalt, Cosmic Impostor.
- **B-39 [fixed on branch, /160] Ingest refuses ELD and IKO** (`core/compiler/ingest.py:652`): printings of one token (ELD
  Food ×4, IKO Human Soldier) differ only in `relatedCards.reverseRelated`, which lists the
  *other* cards that create the token. Merge those printings instead of calling it corruption.
- **B-40 PC-2 counts a shape-gap card's front sentences as matched**: `measure_pool` puts them in
  `sentence_total` but never in the unparsed queue (`core/compiler/coverage.py:368-531`), while PC-1
  counts the same card against coverage. One card in ZNR, two in M20, three in KHM.
- **B-41 The grammar does not generalize to unseen text**: at first touch PC-2 on sentence shapes
  absent from M21/ZNR is 0.080 (M20) and 0.111 (KHM), against 0.89 on seen shapes. On cards with
  new text, PC-1 is 0.11 (M20) and 0.03 (KHM) (KNOWLEDGE /159). Tied rank 1 needs compositional
  mechanisms over sentence shapes. The cheapest first are keyword lines carrying reminder text, and
  keyword lists (ZND-4a). Measure every grammar round on a sealed split
  (`tools/audit/new_set.py`).
- **B-42 MOVE_ZONE has two spellings for one meaning**: the moved object is `cards` in 67 uses and
  `target` in 20 (the exile family), and "its owner's hand" is `Zone(HAND, OWNER)` on three M21
  cards and `Zone(HAND, ANY)` on three others (KNOWLEDGE /163). That violates the identity law
  (DESIGN_ATOM_ONTOLOGY §6). Settle it in a gated ontology round, re-baking goldens.
- **B-43 A bounced card goes to seat 0's hand, whoever owns it** (live in M21):
  `executor/selectors.py:162-175` `zone_owner` resolves `Zone(HAND, ANY)` to the first seat. Barrin,
  Tolarian Archmage; Niambi, Esteemed Speaker; and Roaming Ghostlight compile to that. The OWNER
  branch also uses `controller_of` (the World has no owner), which is wrong after GAIN_CONTROL.
  Fix: the three builders → `Zone(HAND, OWNER)`, three goldens re-baked, a pack that bounces an
  opponent's creature, and an owner field if GAIN_CONTROL cards are dealt. Schedule it at an RL
  pilot era boundary: it changes M21 episodes.
  - **Engine half FIXED on branch `engine/verify-fixes-3` (V24, 2026-10-29).** A moving card lands
    in its owner's hand, library, graveyard or exile whatever player the destination names (CR
    400.3; `selectors.move_destination`), and `zone_owner` resolves ANY to the owner. A permanent
    put onto the battlefield under another player's control stays in its owner's zone with a
    control entry (CR 110.2a), so the World's zone owner is the card's owner even after
    GAIN_CONTROL: no owner field is needed. `cast_card` refuses a card the caster does not own
    (no dealt card does that). The template half landed separately on `cards/m21-fidelity`
    (`Zone(HAND, OWNER)` for Barrin, Niambi and Roaming Ghostlight); both halves meet at the
    integration merge (2026-10-30). B-42's identity fold is still open.
- **B-44 One-card predicates**: `LIFE_LEAD_OVER_START_GE`, `NAME_PARTITION_COUNT_GE`,
  `ATTACK_AGAINST_COUNT_GE`, `NOT_FIRST_DRAW_THIS_STEP`, `INSTANT_OR_SORCERY_CAST_THIS_TURN` read as
  single cards. Decompose them into general atoms (e.g. a QThisTurn count of CastSpell events with
  an FOr filter) in a gated ontology round ("as few subcomponents as possible", owner 2026-10-19).
  - **Measured 2026-10-28 over 19 sets (4,486 compiled cards).** There are 193 component types. 48
    of them cover 90% of uses, and 50 (26%) are used by two cards or fewer.
  - The tail folds into a few general shapes:
    - eight "this turn" predicates are one counted-event atom with a filter and N: `CARDS_DRAWN_`,
      `CAST_THIS_TURN_FROM`, `ENTERED_THIS_TURN_FROM`, `MOVED_TO_ZONE_THIS_TURN`,
      `WAS_CAST_THIS_TURN`, `INSTANT_OR_SORCERY_CAST_`, `NOT_FIRST_DRAW_THIS_STEP` and
      `ATTACK_AGAINST_COUNT_GE`;
    - five comparators are one property comparison: `CMC_GE`, `COLOR_COUNT_GE`,
      `CONTROLLER_COUNT_GT`, `LIFE_LEAD_OVER_START_GE` and `NAME_PARTITION_COUNT_GE`;
    - `FIGHT` is two damage atoms.
  - Owner, 2026-10-27: components that "capture a lot of [the cards'] functionality, such that our
    model needs to learn less atomised components", so the network shares structure. Track it with
    the reuse numbers above.
- **B-48 [2026-10-28] Discard has two encodings.**
  - 27 compiled discard effects are `MOVE_ZONE` from hand to graveyard: Jeskai Elder, Liliana's
    Steward, Duress, Bad Deal and others. One card (Coralhelm Chronicler) uses `Verb.DISCARD`.
  - Same meaning, different bytes: this breaks the identity law and splits the network's training
    signal for one concept.
  - Discard is a keyword action (CR 701.8), and "whenever a player discards" triggers and madness
    key off it. So pick one encoding in the ontology round, probably `DISCARD`, and re-bake
    the affected goldens at an era boundary.
- **B-45 [opt-in mode on branch `sets/onboarding` 36adf48, /164] Every dealt deck is a five-colour stress pile**: `build_deck` (`core/executor/games.py:360-401`)
  takes one basic of each colour plus other mana sources up to 10, then 50 cards uniformly from the
  whole pool. Measured on 400 M21 decks: 13.4 lands of 60 on average (range 7–23), 16.6 mana sources,
  five colours. Real decks run about 40% lands in two colours. Every BC, RL and benchmark number was
  measured on this distribution (REVIEW_ARCHITECTURE_2026-10-27 F3). Under random play a land gap of
  1–5 is a coin flip, and only gaps of 6 or more decide games (K3-lite). Add an opt-in coherent
  mode (2 colours, about 40% lands, a curve, still seeded). Keep the default so existing
  measurements stay comparable. Train and evaluate on both.
- **B-46 [/166; first touch done + round S-3a, /167] Fourteen older sets are dealt mostly partly blank.** The castable pools of M19,
  10E, M10–M13, M15, ORI, DOM, WAR, FDN, ELD, THB and IKO deal 2,482 cards. Only 683 of them
  (27.5%) are fully compiled; the engine plays the rest with their unparsed sentences blank.
  - Their IR matches what the engine does, so K1b could train IR encoders on them. But clean
    volume (fully compiled only) is 556 training cards against 1,829 dealt.
  - Every grammar round on these sets adds clean training cards, and the K1b curve was still
    rising at 16 sets.
  - M14 cannot be dealt at all: 9 mana-capable castable cards, and `build_deck` needs
    `MIN_MANA_SOURCES` = 10.
  - Sealed first touch is done for all 15 (with M14), with baselines and an S-3a round-end read
    (/167). Their dev registers may now be read by grammar rounds; the test groups stay
    sealed, read once per round.
  - Synthetic cards (atoms composed with sampled parameters) come after real-set volume, as the
    clean test of genuinely new compositions (owner, 2026-10-27).
- **B-47 [/167, S-3b differential] One token carrier writes a different type line.** Speaker of
  the Heavens' Angel token is `type_line="Angel"` (`core/compiler/templates_b3.py:842`); every
  other token carrier, and B11, writes "Creature — <subtypes>". Same meaning, different bytes,
  so it breaks the identity law. `types` and `subtypes` agree. Fixing it re-bakes one M21 golden,
  so schedule it at a pilot era boundary with B-43.
- **B-49 [2026-10-29, found by the G1 probe] Noncreature permanents with no spell effect cannot be **[FIXED on branch `cards/integration` 2026-10-29, pending the era-boundary merge]**
  cast** (live in M21).
  - An enchantment, artifact or planeswalker whose text is all static, triggered or activated
    abilities compiles with no `SpellAbility`. `spell_castable` answers `cast:not_a_spell`, and
    the `castable` supply mode drops the card.
  - Uncastable today: 44 M21 cards (25 enchantments, 9 artifacts, 10 planeswalkers), 63 in FDN and
    47 in M19. The RL pilot has never cast an anthem, an equipment or a planeswalker.
  - Creatures got their carrier in C4 batch 4; kicker heads got theirs in ZND-1e. Noncreature
    permanents never did (ZNR /128 noted Skyclave Pick-Axe).
  - Artifacts also had no `SpellKind`: one with an effect sentence compiled as `SORCERY` and
    resolved to the graveyard.
  - **Fix.** `SpellKind.ARTIFACT` is on branch `cards/mapping`; it is M21-invariant. The carrier is
    on branch `cards/castable-permanents`. It changes M21's goldens, its castable pool and every
    replay pin, so adopt it at an RL-pilot era boundary with a re-smoke and a re-pin, with B-43
    and B-47.
  - **Follow-up #4 (Ugin's [−X] gated) FIXED on branch `engine/phasing` 2026-10-29.** An
    activation whose cost carries X announces it before paying (CR 602.2b -> 601.2b, 107.3a):
    `legality.activate` takes `x=` or asks it through the decision channel over `0..x_max`
    (tag `x:<seat>:<source>:<digest>`; the bench registers the kind), with `x_max` the loyalty
    counters (CR 606.6). The query row (`ActivationOption.x_max`) carries the live bound and its
    payment is the X = 0 witness. The effect reads the announced X, and a [−0] still uses the
    turn's loyalty activation (CR 606.3). The compiler gate now keeps only a non-bare X delta
    unsupported. M21 castable 278 -> 279. Packs: `ugin_minus_x_*`, `ugin_minus_ten`.
- **B-50 [2026-10-29, found by a mapper's G1 trace] A resolved ability's "until end of turn" grant
  ends when its source leaves the battlefield.**
  - `verbs._v_grant_or_lose` registers every GRANT/LOSE layer with the ability's source
    (`layers.register_grant`). `layers.detach_source` (`core/executor/layers.py:333`) expires every
    layer of a departing permanent.
  - That is right for a static ability (CR 611.3). It is wrong for an effect a resolved triggered
    or activated ability created, which lasts its stated duration whatever happens to its source
    (CR 611.2a).
  - Seen on FDN Battlesong Berserker: when it dies in combat, you_bear keeps its +1/+0 (the P/T
    ledger is separate) but loses the granted menace.
  - The bug makes cards weaker, not stronger.
  - **Fix.** Mark resolution-created layers and leave them out of `detach_source`. Add a pack in
    which the granting creature dies in combat.
  - It changes M21 episodes, so it is an era-boundary fix.
  - Related: D6 (`tools/audit/detectors.py`) found a live end-of-turn grant layer bound to a card
    already in the graveyard (FDN soak, 300 games). Check that a card returning to the battlefield
    in the same turn is a new object (CR 400.7) and does not keep it.
- **B-51 [2026-10-29] `Verb.CHOOSE` always offers choosing nothing.**
  - `query.verb_choose_options` (`core/executor/query.py`) appends the empty pick `()` even when a
    legal candidate exists.
  - So "You choose a nonland card from it" (Duress, Kitesail Freebooter, Pilfer, Elspeth's
    Nightmare; Linvala, Shield of Sea Gate) can resolve as no choice. The ask vocabulary
    `[0, 1, <handle>]` carries an index that means nothing.
  - Today the chooser is always the caster, so it only makes cards weaker. But an "optional"
    escape from a mandatory choice is exactly what a policy learns to use the day a CHOOSE feeds
    its own drawback.
  - **Fix.** Offer the empty row only when the pool is smaller than the count (the C17 clamp it
    mirrors), and re-pin the M21 Duress and Kitesail packs. **[FIXED on branch
    `engine/verify-fixes-2` 2026-10-29 (V19); a lone legal card is taken without an ask. The Duress
    and Kitesail packs needed no re-pin.]**
- **B-52 [2026-10-29, mapper G1 + packs] A counted static P/T bonus freezes at its first value** **[FIXED on branch `cards/integration` 2026-10-29, pending the era-boundary merge]**
  (live in M21).
  - `layers._materialize_static` skips a target that already has a ledger entry, so a bonus that
    counts something is not continuous (CR 611.3a, 613.4).
  - Seen on FDN Enigma Drake: it stays at 2 power after an instant reaches the graveyard. Blanchwood
    Armor stays +4/+4 after you lose Forests. M21 Kinetic Augur fails the same way.
  - Frozen high is **stronger than printed**: exile your own graveyard or sacrifice the lands and
    keep the bonus. An RL policy would find that.
  - Fix at an era boundary, with a pack that changes the count both ways.
- **B-53 [2026-10-29] "Target player" only ever offers opponents, and a player binding takes over
  any role named `target`.**
  - The synthetic target-player slot lists opponents only, so "target player draws two cards" can
    never target yourself. **[FIXED on branch `engine/verify-fixes-2` 2026-10-29 (V21): "target
    opponent" compiles to the new `ControllerRef.TARGET_OPPONENT`; `TARGET_PLAYER` names any player
    (CR 115.1). Unverified FDN records still writing TARGET_PLAYER for "target opponent": Pilfer
    (re-map it); Gatekeeper of Malakir's "target player" is now right.]**
  - A target-player binding overrides an atom's own `target` role: "target player sacrifices a
    creature" raised `KeyError 'unknown card player:1'`. **[FIXED on branch
    `engine/verify-fixes-2` 2026-10-29 (V10): a CHOOSE menu over cards ignores a player-only
    binding (`selectors.role_handles`).]**
  - Related: the deciding player of an edict is always the caster (no chooser role), the L-27
    seat-routing gap. **[FIXED on branch `engine/verify-fixes-2` 2026-10-29 (V10).]** A sacrifice
    menu is asked of the player who controls it (`sacrifice:<seat>:...`), a discard of the
    discarding player (`discard:<seat>:...`, every player the controller role names, APNAP), via
    `ExecCtx.take_decision_of`. Consumers that still attribute asks without
    `DecisionStream.asking_seat`, so they hand a non-active player's choice to the active player's
    policy: `tools/training/ab_duel.py` and `collector.py` (every ask goes to
    `world.active_player`, blocks included) and `tools/eval/gameplay_eval_v2.py`
    (`resolve_seat` parses the tag: right for seat-in-tag kinds, wrong for an EachPlayer-rotated
    `may:`/`choose:`). Each needs to read `executor.decisions.asking_seat` in its provider.
  - [m21-fidelity, 2026-10-29] The engine cannot fix the population alone: "target player" (Peer
    into the Abyss, Mind Rot, Tormod's Crypt, Sublime Epiphany) and "target opponent" (Duress,
    Kitesail Freebooter, Liliana's Steward, Necromentia, Vito) compile to the same bare
    `ControllerRef.TARGET_PLAYER`, so the IR needs one more bit (a design decision: for example a
    `TARGET_OPPONENT` reference, or an explicit player-zone TARGET selector). Repro:
    `tools/scenarios/known_bugs/peer_into_the_abyss_self_target.json`. With Peer's life loss now
    compiled, Peer on an opponent is printed play; the self-target is the weaker-than-printed part.
    **[FIXED on branch `engine/verify-fixes-2` 2026-10-29 (V21): the `TARGET_OPPONENT` reference.
    At the merge of `cards/integration` into that branch (2026-10-30) the repro passes; it moved to
    `tools/scenarios/peer_into_the_abyss_self_target.json`.]**
- **B-54 [2026-10-29] Minor engine findings from the first mapping batch:**
  - `legal_casts` offers a spell whose required target has no legal candidate (CR 601.2c), and casting
    it raises. The bench router hides such rows; the probe now skips them.
  - Damage marked on a non-creature land through a forced binding: only reachable from harness ops,
    but `DEAL_DAMAGE` does not check the recipient's type. **[FIXED on branch
    `engine/verify-fixes-4` 2026-10-30: CR 120.1a, no damage to anything but a battle, a creature or
    a planeswalker.]**
  - M21 Quirion Dryad's trigger uses `COLOR_IN` (a subset test), so a green-white spell would not
    trigger it. The text needs "any of white, blue, black or red" (an FOr of `COLOR_HAS`).
    **[FIXED on branch `engine/verify-fixes-4` 2026-10-29 (V39): the template writes the FOr of
    `COLOR_HAS`; no compiled card writes `COLOR_IN` now.]**

**Engine findings from mapper B's FDN batch and the FDN soak (2026-10-29).**
- Each reproduction is a scenario pack in `tools/scenarios/known_bugs/`. It holds the outcome the
  printed text demands, so it FAILS today and passes once the bug is fixed.
- Run them with `tools/run_scenarios.py --dir tools/scenarios/known_bugs`. They are outside the
  default sweep.
- Every fix below changes M21 episodes unless marked otherwise, so schedule them at an era boundary.

- **B-55 A triggered ability whose only target is gone still resolves, and crashes.** **[FIXED on branch `cards/integration` 2026-10-29, pending the era-boundary merge]**
  - CR 603.3d: a trigger with no legal target is removed from the stack.
  - The engine runs the effect anyway. "Attach it to target creature you control" with no creature
    raises `ATTACH needs exactly one equipment and one host, got 1/0`.
  - In the FDN soak this crashed 37 of 300 games: Pirate's Cutlass, "target Pirate you control".
  - Repro: `kitesail_etb_no_creature.json` (ZNR Cliffhaven Kitesail).
- **B-56 "If a creature died this turn" counts noncreatures (live in M21, stronger than printed).** **[FIXED on branch `cards/integration` 2026-10-29, pending the era-boundary merge]**
  - `CREATURE_DIES` is emitted for every battlefield-to-graveyard move (`executor/events.py` ~522).
  - `DIED_THIS_TURN`'s any-object branch never checks the type.
  - M21 Twinblade Assassins draws after you sacrifice a Treasure.
  - Repro: `died_this_turn_treasure.json`.
- **B-57 "Deals combat damage to a player" also fires on combat damage to a creature (live in M21, **[FIXED on branch `cards/integration` 2026-10-29, pending the era-boundary merge]**
  stronger than printed).**
  - The compiled trigger's recipient filter is universal.
  - M21 Jeskai Elder loots when a wall blocks it. Also affected: Feline Sovereign, Nimble
    Trapfinder and Subira's delayed trigger.
  - Repro: `jeskai_elder_blocked.json`.
- **B-58 A static `Seq` applies every step to the first step's selector** (`layers.py` ~587).
  - A lord that grants and pumps different sets puts both effects on the first set: Death Baron.
  - G3 can never clear such a card.
- **B-59 `MANDATE_BLOCK` / `MANDATE_ATTACK` ignore their duration (stronger than printed).** **[FIXED on branch `cards/integration` 2026-10-29, pending the era-boundary merge]**
  - The dispatch ledgers clear only when the creature leaves the battlefield.
  - So a one-turn lure keeps forcing blocks on later turns (FDN Joraga Invocation, checked by
    mapper B with a pack).
- **B-60 Compiler drops that make M21 cards stronger than printed** (the templates mark them LOSSY, **[equip and Speaker FIXED on `cards/integration` 2026-10-29; Kitesail Freebooter FIXED on branch `engine/r5a-until-leaves` 2026-10-29 by ontology R5-1, see B-60c and B-97]**
  `templates_b5a.py`).
  - Equip has no sorcery timing, so every Equipment can move at instant speed and mid-combat (M21
    Short Sword, Malefic Scythe).
  - Kitesail Freebooter's exile is permanent: "until it leaves the battlefield" is dropped.
  - Speaker of the Heavens loses "Activate only as a sorcery".
  - In the other direction, Faith's Fetters loses its activated-ability lock (weaker).
  - The `ActivatedAbility.timing` slot exists, so the equip and Speaker fixes are compile-only.
- **B-61 [verifier, FDN round 1] A blocked attacker whose blockers all left combat deals its damage **[FIXED on branch `cards/integration` 2026-10-29, pending the era-boundary merge]**
  to the player** (live in M21, stronger than printed).
  - `executor/__init__.py:1974` `_assign_damage` returns `((power, attacked),)` when the blocker
    list is empty.
  - CR 510.1c: a blocked creature with no blockers left assigns no combat damage, unless it has
    trample.
  - So every first or double striker without trample is stronger than printed: kill the blocker in
    the first-strike step, then hit the player. The same goes for any attacker whose blocker is
    removed after blocks.
  - Control test: Drogskol Reaver blocked by Thornweald Archer.
- **B-62 [verifier] "If it would die, exile it instead" never applies to a planeswalker.** **[FIXED on branch `cards/integration` 2026-10-29, pending the era-boundary merge]**
  - The zero-loyalty state-based action (`executor/__init__.py:1259`) moves the walker without
    consulting `replacement_for_death`, which matches `CreatureDiesEvent` only
    (`replacements.py:671`).
  - FDN Obliterating Bolt's exile clause fails on walkers. The verifier's failing pack
    `obliterating_bolt_planeswalker.json` is in its round-1 output.
- **B-63 [2026-10-29] Eight scenario packs declare `"tapped": true` setup cards that the runner
  never taps.**
  - `ScenarioRunner` ignores a `tapped` key on setup cards, so these packs pass with a false
    precondition:
    - block_defender_and_tapped
    - enthralling_hold
    - herald_assigns_unblocked
    - rewind
    - sabertooth_mauler_end_step_death
    - sabertooth_mauler_no_death_control
    - swift_response
    - tolarian_kraken_untap
  - With the key honoured, `rewind.json` FAILS: its three tapped Plains stay tapped. Its own note
    says Rewind "untaps them all", so either Rewind's untap step or the pack's premise is wrong.
    The others still pass.
  - **Settled 2026-10-29 (V28, branch `engine/verify-fixes-3`): the untap step was wrong.**
    `selectors.role_handles` handed the UNTAP's CHOOSE selector the spell's TARGET designation
    (the countered spell). A CHOOSE selector now ignores a designation it could not select
    (packs `rewind_counters_and_untaps`, `rewind_untap_choice`).
  - **Fix.** Honour the key, find out why Rewind does not untap, and re-run the suite.
  - The card tooling uses its own `start_tapped` key meanwhile, so the 429 packs stay byte-identical.
  - **FIXED on branch `engine/verify-fixes-3` (fixer 3, 2026-10-30).** The runner honours `tapped`
    as well as `start_tapped`, and applies both after the opening `begin_turn` (whose untap step
    used to undo `start_tapped` on seat 0). All eight packs pass with the key honoured (Rewind's
    untap was the engine bug, V28).
- **B-64 [verifier, FDN round 2] "You may discard a card. If you do, draw a card" draws with an
  empty hand** (stronger than printed). **[MAY_DONE half FIXED by V12 on `engine/verify-fixes`
  2026-10-29: "if you do" now reads whether the optional action changed anything (CR 118.12), so
  nothing done means no draw. Still open, weaker side only: the may-offer and a Choose inside it
  still offer an action that cannot be done (Crypt Lurker's discard with no creature card), a
  phantom option (AGENTS §10).]**
  - The may-offer is not narrowed when there is nothing to discard. `MAY_DONE`
    (`executor/quantity.py:1081`) only checks that the answer was "fire", so "yes" draws a card and
    discards nothing.
  - Affects FDN Incinerating Blast, and any card worded "you may <cost-like action>. If you do, …"
    with the compiler's usual CHOOSE discard too.
  - A policy would learn to answer yes on an empty hand.
  - **Fix.** Offer the may only when the action can be done (CR 609.3). `MAY_DONE` should read
    whether it was done, not what was answered.
- **B-65 [verifiers, FDN rounds 1-2] An Aura whose text is all static can enchant any permanent, **[host filter FIXED on `cards/integration` (ENCHANT carries the filter); the CR 704.5m SBA is still open]**
  and nothing removes an Aura on an illegal object.**
  - `query.aura_enchant_slot` (`query.py:1383-1419`) reads the host filter from the spell's effect
    only. `KeywordAbility(ENCHANT)` has no filter parameter, so the tree cannot say "creature".
  - No state-based action moves an illegally attached Aura to the graveyard (CR 704.5m).
  - The first half is being fixed on branch `cards/castable-permanents` (B-49 follow-up #2).
- **B-66 [B-49 follow-up sweep] Enthralling Hold's "You can't choose an untapped creature as this
  Aura's target" is not applied to its target slot** (live in M21, stronger than printed): the Aura
  can steal an untapped creature. **[FIXED on branch `engine/verify-fixes-2` 2026-10-29 (V20):
  `legality.enumerate_candidates` applies the source's own TargetingEvent prevention while it is
  cast (CR 113.6e).]**
- **B-67 [same] The journal records any card put from library into hand as a draw (`CARD_DRAWN`).**
  - So a tutor can satisfy "whenever you draw a card" triggers and draw counts.
  - Probably stronger than printed. Write the pack first: a search-to-hand with a draw-trigger card
    on the battlefield.
- **B-68 [same] "Doesn't untap during its controller's untap step" is not applied** (Capture Sphere,
  Bubble Snare; weaker than printed, true before B-49 too). **[FIXED on branch
  `engine/verify-fixes-2` 2026-10-29 (V16): `replacements.prevents_untap` judges a static carrier's
  event filter over the card (CR 502.3).]**
- **B-69 [same] Two damage replacements on one event raise `NotImplementedError`.**
  - `replacements.py:424-425` does not model the affected player's ordering choice (CR 616.1).
  - About 0.25% of coherent M21 games crash on it (seeds 1176, 1356, 1439, 1603, 2230: Fiery
    Emancipation with Nine Lives, or two Fiery Emancipations).
  - Repro script on the B-49 branch: `cr6161_repro.py`.
- **B-60c design decision: Kitesail Freebooter's "until this creature leaves the battlefield".**
  **[DECIDED and BUILT 2026-10-29 as option (1), ontology R5-1 after two adversarial gate rounds,
  branch `engine/r5a-until-leaves`; follow-ups in B-97]**
  - (1) Recommended: an optional `duration` role on MOVE_ZONE/EXILE taking `DurationUntilLeaves`.
    The executor keeps (card, previous zone, anchor) and returns the card when the anchor leaves
    (CR 610.3). If the anchor already left, the exile does not happen (CR 610.3a). The return table
    joins `state_fingerprint`. It also covers Banisher Priest, Stasis Snare and the other
    O-Ring-style cards.
  - (2) An extra compiled "when this leaves, return the exiled cards" trigger: existing atoms only,
    but it deviates from CR 610.3/610.3a.
  - It is an ontology change, so it goes in a gated round.
- **B-70 [fixer B] The P/T fold orders a power-setting effect after a +N applied at the same
  moment.**
  - Kinetic Augur entering under Glorious Anthem loses the anthem's +1.
  - CR 613.4: characteristic-defining and setting effects (7a/7b) apply before modifications (7c),
    so the fold needs sublayers. Weaker than printed.
  - **FIXED on branch `engine/verify-fixes-3` (V27, 2026-10-30)**: `DurationLedger._effective`
    applies every set before every delta (then counters). 7a and 7b are still ordered by
    timestamp between themselves (no dealt card pairs a CDA with a 7b set). Pack
    `glorious_anthem_cda_creature`.
- **B-106 [vfix2, V14, 2026-10-29; numbered B-81 in a6c7740, renumbered 2026-10-30 because the
  m21-fidelity lane's B-81 took the number on `cards/integration`] Per-object attack triggers fire
  once per declaration (weaker than printed; gated as R5-14).**
  - `DeclareAttackersEvent` is (filter, attacked). The same bytes carry "Whenever you attack" / "one
    or more creatures you control attack" (CR 508.3d: once per declaration; MAPPER_GUIDE prescribes
    it, `binding._queue` dedups by (source, node, declare_group)) and "Whenever a creature you control
    [with deathtouch] attacks" (CR 508.3a with 603.2c: once for EACH such attacker, the event subject
    being that attacker). M21 Hooded Blightfang drains once; Basri, Devoted Paladin's −1 grant
    ("Whenever a creature attacks this turn, put a +1/+1 counter on it") counters only the first
    attacker.
  - Options sent to the gate: (1) an optional field (absent = once per event, so existing trees stay
    byte-identical) that the per-object templates set, the binder skipping the dedup for it and
    binding the subject per row; (2) flip the default to per object and mark "one or more"; (3)
    encode "one or more" as a QAtLeast condition. The coordinator recommends a GENERAL form of (1):
    once-per-event vs once-per-object is one trigger axis (dies, enters, damage too), so an
    attack-only field would become a second encoding of it (AGENTS §9).
- **B-107 [vfix2, V15 residue, 2026-10-29; numbered B-80 in 6ec0078, renumbered 2026-10-30 for the
  same reason] Untargeted "up to N" still compiles as an exact count.**
  - V15 made "up to N target ..." 0..N (CR 601.2c, 115.6) and Kinetic Augur's "discard up to two"
    QAtMost(2). Three more M21 untargeted choices are QConst: Rewind "Untap up to four lands",
    Cultivate "Search your library for up to two basic land cards", Ugin −10 "put up to seven
    permanent cards from your hand onto the battlefield". The player must take the full count when
    it is available (weaker than printed; rarely matters).
  - **Fix.** Write QAtMost in those templates and give `selectors.resolve_selector`'s CHOOSE lift a
    QAtMost lane with a NONE stop (the discard lane's shape, `verbs._discard_picks`); today a
    QAtMost CHOOSE is not lifted at all and would fall to the silent slice.
- **B-108 [vfix2, V42, 2026-10-30] Opponent refs with three or more seats: one acting player is
  loud when it would stand for several.**
  - Measured on a three-seat world (`MTG_bot/core/test_executor_multiplayer_opponents.py`, real
    M21 cards). These play as printed: turn rotation; "each opponent discards" (Bad Deal, through
    V10's per-player discard lane; before V10 only the first opponent discarded); damage to each
    opponent (Storm Caller); each opponent mills (Thieves' Guild Enforcer); Massacre Wurm's -2/-2
    and its per-controller life loss; "as long as an opponent has eight or more cards in their
    graveyard", read from the second opponent; "target opponent" offering every opponent and
    "target player" offering every player (V21); and Teferi's Ageless Insight's draw-step
    exception across the other players' turns.
  - The one wrong answer was `selectors.role_player`. It took the FIRST player a ControllerRef
    denotes as the one acting player of DRAW, SCRY, LOOK_AT/REVEAL, ADD_MANA and MOVE
    `pop_order=TOP`. It now raises when the ref denotes several. This is a hard stop where a silent
    pick used to be, not a cap. No M21 tree reaches it: a scan of every castable and refused M21
    tree finds no singular verb that carries OPPONENT, ALL_OPPONENTS or ANY. Two seats never
    denote several opponents. The suite and a 60-game castable soak stay green.
  - **What would remove the raise:**
    - ALL_OPPONENTS ("each opponent") in those verbs should iterate in APNAP order (CR 101.4), as
      `role_players` does.
    - A non-targeted singular OPPONENT ("an opponent") with several candidates needs a chooser
      ask. Who chooses, and under which tag kind, is a design decision. It is not taken here.
  - Two-seat consumers: `games.py:1157` deals `GameWorld(num_players=2)`. tools/training
    `ab_duel.py` and `collector.py` route every ask to `world.active_player`, not
    `executor.decisions.asking_seat`.
- **B-71 [fixer A] A "discard your hand" cost is refused with an empty hand**
  (`cost:discard:insufficient_candidates:0<1`). Weaker than printed: a cost of discarding the whole
  hand is payable with no cards. **FIXED on branch `engine/verify-fixes-3` (V33, 2026-10-29)**: an
  unbounded ALL cost selector demands every candidate and none when there are none, and Subira's
  cost now discards the whole hand instead of one card (packs `subira_discard_whole_hand`,
  `subira_discard_empty_hand_pays`).
- **B-72 [fixer A] DESTROY and other direct graveyard moves never check the dies replacements**
  (`verbs._to_graveyard` → `_move_to`). A creature hit by Scorching Dragonfire, then destroyed later
  the same turn, goes to the graveyard instead of exile. Weaker than printed.
- **B-73 [2026-10-29 soaks] The anomaly detectors flag about 2% of M21 games on `main`.**
  - Measured: 18 flags in 800 castable games (400 stress + 400 coherent), all pre-existing. On
    `cards/integration`: 10.
  - The classes:
    - d1: life moved without a journal row;
    - d3: a +1/+1 counter placed on a card already off the battlefield (CR 400.7);
    - d5: P/T recompute mismatch (Goblin Wizard, Thieves' Guild Enforcer, Quirion Dryad, Palladium
      Myr);
    - d6: an end-of-turn grant or lose layer still bound to a card that left (related to B-50 and
      CR 400.7); two replacement records for one event (B-69); a delayed trigger never drained.
  - BUGCATCH's "scan = 0" was 10 catalog seeds, so the larger sample now finds these. Triage each
    class: detector gap or engine bug.
- **B-74 Sorcery speed means the first main phase only.** No second-main window for casts, land
  drops or sorcery-speed activations.
  - [2026-10-29, branch `engine/phasing`] Loyalty abilities had no window at all in the legality
    oracle: they compile with no `timing`, so `ability_playable` accepted them on any turn, in any
    step, with a non-empty stack. Only the drivers' one main-phase act batch kept them at sorcery
    speed (four packs activated an opponent's planeswalker on the wrong turn). CR 606.3 is now
    enforced there (`window:loyalty:*`: own turn, empty stack, either main phase); the
    first-main-only limit above still holds for casts, land drops and `timing=SORCERY`
    activations.
- **B-75 [2026-10-29, branch `engine/phasing`] Phasing (CR 702.26) is implemented as a status; one
  printed clause still has no ontology.**
  - Done: `Executor.phase_out` / the CR 502.1 step in `_untap_step`, `Executor.phased_out`
    (folded into `state_fingerprint` when non-empty). The card keeps its zone, so there are no
    zone-change events, tokens and counters stay, attachments and control stay (702.26d). The
    readers leave it out: `selectors.enumerate_zone` / `existing` (targets, "each" populations,
    counts, costs, static scopes), `legality._zone_handles`, `role_handles`' bound designations,
    `Executor.battlefield` (the three SBA sweeps), the untap loop, `ability_playable`
    (`window:phased_out`), cost modifiers, attack/block legality, `layers._layer_live` (its own
    statics go dormant, `LayerRecord.from_static`), `binder._queue` (its triggers; delayed
    triggers still fire), `replacements._source_alive`, the quantity census loops. It is removed
    from combat (506.4); Auras/Equipment phase out and in with it (702.26g/h). Packs:
    `teferi_master_of_time_phase*`, `teferi_master_of_time_phased_out_*`,
    `teferi_timeless_voyager_phase_out_all`, `aven_gagglemaster_ignores_phased_out_flyer`,
    `feline_sovereign_*phase*`.
  - **Open, weaker than printed: Teferi, Timeless Voyager's "Until the end of your next turn, they
    can't phase in."** Accepted as divergence D16 by ontology R5-9 (gate round 3 GO,
    2026-10-30; `docs/ATOM_DIVERGENCES.md`). The compiler's built-in `_phase_in_prevention_effect` (`compiler.py` ~206)
    emits `PREVENT_EFFECT(event=ZoneChangeEvent(COMMAND/OPPONENT -> BATTLEFIELD/OPPONENT),
    condition=CONTROLLER_IS OPPONENT, duration=DurationUntilNextTurn)`. Phasing is not a zone
    change, so the record is inert and the creatures phase back in at their controller's next
    untap step. Repro: `tools/scenarios/known_bugs/teferi_timeless_voyager_cant_phase_in.json`.
    What the clause needs, for the next gated ontology round:
    - an event: a phasing event shaped like `TapStateEvent`, e.g. `PhasingEvent(phased_in: bool,
      filter: Filter)`, that the phasing step offers to the prevention registry before each
      phase-in (the consumer: `Executor._phasing_step`);
    - "they": the creatures the preceding PHASE_OUT phased out. PHASE_OUT writes the `result`
      register, so either a filter referent for it or the `_v_prevent` convention of materialising
      the affected set at registration (today it reads the `target` binding, here the targeted
      player). `CONTROLLER_IS OPPONENT` is broader than "they" (it would also hold a creature
      phased out earlier by another effect, stronger than printed);
    - the duration: `DurationUntilNextTurn` ends as your next turn begins, the printed text at
      its end. Phase-ins happen only in their controller's untap step, so no reachable game tells
      them apart today; a PHASE_IN effect during that turn would.
  - Also open: the policy observations (`tools/training/packrec.py`, `ab_duel.py` obs rows) list a
    phased-out permanent as an ordinary battlefield card (AGENTS §10). The menus never offer it;
    the bench seat view marks it. Add a `phased_out` row word (like `tapped`) at the next
    observation-schema change.
  - No carrier: the phasing keyword (702.26a's phase-out half), PHASE_IN (702.26c by an effect),
    a directly phased-out Aura (702.26i), "for as long as" durations tracking a phased-out
    permanent (702.26f; `DurationUntilLeaves` must not end on phasing, R5-1).
- **B-82 [fixer A, m21-fidelity item 3; renumbered from B-75 at the merge, which phasing took] A multicoloured token is colourless** (FIXED 2026-10-30 by ontology R5-11, branch `engine/r5b-go-items`: option (a) below. `TokenSpec.colors` holds WUBRG letters in WUBRG order and is omitted when colourless; the Weird is `("U", "R")`; 22 M21 goldens and 138 compiled entries in the 19 sets re-baked, each proven to be the rename only; test `MTG_bot/core/test_ontology_r5_token_colors.py`.)
  - Experimental Overload's "X/X blue and red Weird" compiles with `TokenSpec.color=None`
    (`templates_b5a.py`, B5a-weird-token): `color` holds one colour letter.
  - Census 2026-10-29: of the 152 TokenSpecs compiled in the 19 sets (and 5 in FDN records), 150
    single-colour tokens carry their printed colour and Gadrak's Treasure is rightly colourless;
    the Weird is the only miss. The executor gives a token its spec colour (pinned in
    `test_executor_verbs.py`: COLOR_HAS, COLOR_COUNT_GE, protection).
  - Effect: Basri's Lieutenant's protection from multicolored and Feat of Resistance's protection
    from blue or red do not stop the Weird (stronger than printed for its controller).
  - Design decision, an ontology change: (a) `TokenSpec.colors: tuple[str, ...]`, WUBRG-sorted
    like `CardRecord.colors` (SET-R1a), replacing `color`, so every token golden is re-baked and
    the model sees each colour as its own token. Recommended. (b) Let `color` hold a WUBRG string
    ("UR") and split it in the executor (`verbs._v_create_token`): no schema change and one golden,
    but "UR" fuses two colours into one token (AGENTS §9) and breaks the IR's `color` (one) /
    `colors` (several) convention that `FAtom` follows.
- **B-76 [fixer A, found 2026-10-29] A creature with defender can never block** (live in M21,
  weaker than printed). **[FIXED on branch `engine/verify-fixes-4` 2026-10-30 (V40): both block-side checks dropped;
  the attack-side reason now cites CR 702.3b.]**
  - `legality.block_pair_blocked_reason` (`executor/legality.py` ~1878) and `blocker_askable`
    (~1925) refuse every blocker with DEFENDER, citing "CR 702.4a". Defender only forbids attacking
    (CR 702.3b), and 702.4 is double strike.
  - So every wall is a dead card: 59 set entries list Defender in the 19 sets; in M21 Drowsing
    Tyrannodon, Portcullis Vine, Wall of Runes and Warded Battlements. The pack
    `block_defender_and_tapped.json` pins the bug (its wall is `not_asked_to_block`).
  - **Fix.** Drop the two DEFENDER checks, re-pin that pack, and re-run the corpus games.
- **B-77 [fixer A, m21-fidelity item 4] A spell's "would die this turn, exile it instead" has no
  duration in the tree** (play is right; the encoding is implicit).
  - Scorching Dragonfire (M21, ELD, FDN), Obliterating Bolt (FDN) and Blitz of the Thunder-Raptor
    (IKO) compile a card-level `ReplacementAbility` with no duration (the IR node has no such
    field). The executor registers a resolving instant's or sorcery's ReplacementAbility until end
    of turn, scoped to the cast's designation (`stack.py`, `replacements.register_ephemeral_
    replacements`), which is the printed "this turn" for all five. Packs
    `scorching_dragonfire_late_damage_creature` and `scorching_dragonfire_expires_next_turn` pin it.
  - So the model's static view of these cards does not show "this turn", and a future spell whose
    replacement has another duration would be played wrong without a compile error.
  - Options: (a) an optional `duration` on `ReplacementAbility` (ontology change, the R5-1 sibling
    for replacements; the Dragonfire family re-bakes with `DurationEot`); (b) keep the executor rule
    and write it into the ontology doc as the meaning of a ReplacementAbility on an instant or
    sorcery (no IR change; the gap stays implicit).
  - The spell-side death replacement is still skipped by DESTROY and other direct graveyard moves
    (B-72).
- **B-78 [fixer A, m21-fidelity] "Search your library and/or graveyard" always searches both.**
  - The named tutors (Basri's Aegis, Liliana's Scorn, Garruk's Warsteed, Chandra's Firemaw and
    their siblings) compile to one SEARCH over Zone(GRAVEYARD) and Zone(LIBRARY), and "If you
    search your library this way, shuffle" joins the same OptionalEffect, so accepting the search
    always shuffles.
  - Printed, "and/or" lets the player search only the graveyard (CR 701.23a: a search looks at
    the zone searched), and then there is no shuffle, keeping a known library order (after a
    scry, say). Slightly weaker than printed, no exploit.
  - Fix needs a way to say "choose which of these zones to search" (a design decision; today
    the zone set is fixed by the selector). Not done.
- **B-79 [fixer A, m21-fidelity] Primal Might's fight partner is not a target and cannot be
  declined** (live in M21 and FDN; stronger and weaker than printed).
  - "Then it fights up to one target creature you don't control" compiles the foe as a
    resolution-time ONE_OF pick (`templates_b5c.py` `_build_then_it_fights_up_to_one`), so a
    hexproof creature can be fought and the fight cannot be skipped. Review packs
    `primal_might_fight_optional` and `primal_might_hexproof_not_fought` (m21v batch A) fail.
  - The tree fix is one line (TARGET with `QAtMost(1)`), but it needs two engine changes first:
    a TARGET "up to N" slot whose minimum is 0 (the C17 clamp below, every "up to N target"
    card), and positional multi-slot designation that accepts an empty trailing optional slot
    (`stack._validate_positional` raises on any non-exactly-one slot). The games policy also
    skips multi-slot casts, so Primal Might would stop being cast in corpus games. Engine lane.
  - Re-checked on `cards/integration` 18afa85 (2026-10-30): tree unchanged in M21 and FDN, both
    review packs still fail the same way, `_validate_positional` still exactly-one only.
- **B-80 [fixer A, m21-fidelity] "Can attack as though it didn't have defender" has no
  component** (Drowsing Tyrannodon, live in M21; slightly weaker than printed).
  - It compiles to LOSE_ABILITY(DEFENDER) while you control a creature with power 4 or more, so
    the Tyrannodon stops having defender (Portcullis Vine cannot sacrifice it as "a creature with
    defender"). Review pack `tyrannodon_still_has_defender_for_portcullis_vine` (batch B) fails.
  - The attack legality reads DEFENDER directly (`legality.py`, "no 'can attack as though it
    didn't' carrier in the corpus"). Options for the gated ontology round: (a) an attack
    permission atom (a "may attack despite defender" policy, the MANA_POLICY/GRANT_ACTIVATION
    family) the attack check consults; (b) a parameter on KeywordAbility(DEFENDER) carrying the
    "as long as" condition. (a) keeps DEFENDER a plain keyword and is reusable for "can block as
    though" cards; recommended.
  - Re-checked on 18afa85 (2026-10-30): tree unchanged; the Portcullis Vine pack still fails, the
    two attack packs pass.
- **B-81 [fixer A, m21-fidelity item 5] Lossy rows judged (2026-10-29).** Significance per
  AGENTS §11 (alters legal options or state outcomes).
  - Fixed: Lofty Denial (the {4} branch never applied; now a conditional arm, pack
    `lofty_denial_with_flier`); Sanctum of Tranquil Light (the activation cost fold counted the
    source twice, one Shrine cut {2}; pack `sanctum_tranquil_light_exact_cost`).
  - Significant, not fixed: See the Truth's "If this spell was cast from anywhere other than your
    hand, put each of those cards into your hand instead" runs as an extra step that returns one
    card, not all three. It is unreachable until something lets you cast it from elsewhere
    (Chandra, Flame's Catalyst's -2, R5). Fix: the conditional "instead" arm (as Life Goes On),
    replacing the one-and-rest split, once a pack can cast it from the graveyard. Re-checked on
    18afa85 (2026-10-30): tree unchanged, still unreachable.
  - Not significant, kept: Garruk's Harbinger "in a random order" (the bottom order is
    information, no option changes); Cultivate's REVEAL count (REVEAL is a recorded no-op);
    Fiery Emancipation's universal recipient (damage only ever goes to permanents or players);
    Malefic Scythe's kind-blind counter count (nothing in M21 puts another counter kind on an
    Equipment); Barrin's unconstrained "a permanent" (anything moving from the battlefield is
    one); Chandra's Incinerator (the engine sums noncombat damage dealt TO opponent seats, as
    printed; only the docstring's reading is off).
  - Stale notes refreshed: Jolrael's token colour, the Sporeweb/Baneslayer keyword-list note.
- **B-90 [vfix V2, 2026-10-29] A payment outside the active player's main phase had no mana** **[option (a) BUILT
  on `engine/verify-fixes` 2026-10-29, owner decision; (b) stays the design target]**
  (weaker than printed, live in M21 until (a)). Since V2 the pool empties as each step and phase ends
  (CR 500.5), and the engine pays only from the pool: it cannot activate mana abilities while a
  payment is asked (CR 601.2g, 605.3a). Before V2 these payments drew on mana banked across turns
  (mean 9.4 / 11.6 floating at game end, max 38 / 43, M21 soak stress / coherent, 200 games).
  - Dead now: counterspells (the rung-1 counter window: 66 / 70 opens per 200 games before, 0
    after), the combat instant window (176 / 209 before, 0 after), flash on the opponent's turn,
    end-step and upkeep "you may pay" triggers (Liliana's Devotee), "unless its controller pays"
    asked of a seat with no floating mana.
  - Options: (a) an engine witness that taps the payer's untapped tap-only mana abilities when a
    payment is asked outside the act window (fast; the engine picks the sources silently, AGENTS
    §10); (b) the `PAYMENT:PTR` asks of `DESIGN_ACTION_SPACE.md` §1.3, payment folded into the move
    with the payer picking the sources (the design target). Needs an owner decision.
  - (a) measured on the same 200 games per deck mode (stress / coherent): combat window opens 336 /
    296 and counter window opens 73 / 69 (before V2 176 / 209 and 66 / 70, after V2 0 / 0). The
    combat window opens more than before V2 because any seat with untapped lands can answer, not
    only a seat with banked mana. It is a scaffold (row above): the engine picks the sources.
  - No compiled card retains mana ("you don't lose this mana as steps and phases end": Upwelling,
    Savage Ventmaw, Leyline Tyrant, Grand Warlord Radha, Birgi, Neheb all compile partly); the first
    one that compiles needs a retention lane in `Executor.empty_mana_pools`.
- **B-91 [vfix V7, 2026-10-29] A dies trigger judges "you control" after the death, not as of it**
  (CR 603.10a). `CreatureDiesEvent` filters run when the binder matches, after the control overlay
  has expired, so a creature stolen with Enthralling Hold that dies triggers its OWNER's "whenever a
  creature you control dies", not the thief's. Since V7 every CREATURE_DIES row carries the
  controller and the token flag as of death (`events.py`, data[5:7]); the matcher can read them, as
  the died-this-turn census does (`quantity._died_this_turn_census`). Rare in M21 (needs a steal).
- **B-92 [vfix V8, 2026-10-29; updated at the d955f67 merge, 2026-10-30] A fight's two DAMAGE
  journal rows both name the fight's source as the cause** (CR 701.12b: each creature deals damage
  equal to its power to the other). **[Half FIXED by V44 (fixer 3, in `cards/integration`
  d955f67): `verbs._v_fight` applies each blow with the fighting creature as `ctx.source`, so
  protection (702.16e), deathtouch, lifelink and source-keyed replacements (Fiery Emancipation)
  read the creature. The rest is B-101's residue (4).]**
  - Still open: the journal's one-cause-per-atom diff (`Journal.record_atom`, called by the
    executor's Atom lane with the atom's cause) names the fight's source as the dealer of both
    rows, so a damage trigger with a dealer filter (`binding._match_damage` reads `event.cause`
    for `DamageDealtEvent.source`) sees the wrong dealer.
  - Latent in M21 (census 2026-10-30): the four dealer-filtered damage nodes are Hooded
    Blightfang, Chandra's Incinerator, Chandra's Pyreling and Fiery Emancipation. The first three
    read damage to players or planeswalkers, which a fight never deals. Fiery Emancipation is a
    replacement and reads the per-blow source since V44.
  - Correction: this entry used to say that Brash Taunter's echo hits its own controller after a
    fight. It does not. The echo's opponent is chosen in the trigger controller's coordinates and
    its filter reads the recipient (`brash_taunter_fight_redirects_to_opponent` passes, with and
    without the decision).
  - Fix: a per-row cause. The V3 dealer lane (`verbs.damage_source`, the Atom lane's DEAL_DAMAGE
    cause) is the one-dealer model; FIGHT needs two.
- **B-96 [fixer 4, 2026-10-29] "You have no maximum hand size" compiles nowhere.** Since V36 the
  cleanup step discards down to seven (CR 514.1, 402.2: `executor.MAX_HAND_SIZE`, read only by
  `Executor._discard_to_hand_size`). The sentence is UNPARSED on Reliquary Tower (M13), Spellbook
  (10E), Niv-Mizzet, Visionary and Finale of Revelation (FDN), Folio of Fancies and The Magic Mirror
  (ELD) and Sea Gate Restoration (ZNR), so these partly compiled cards are now weaker than printed
  in the pool modes that deal partly compiled cards. No M21 card and no FDN record is affected.
  Needs a component for a player's maximum hand size (a static over the player, and "for the rest of
  the game" on a resolving effect): an ontology decision for a gated round.
- **B-97 [2026-10-29, branch `engine/r5a-until-leaves`; renumbered from B-76 at the integration merge] Ontology R5-1: zone moves "until" an event
  (CR 610.3) are built; what is left.**
  - Done: `MOVE_ZONE` takes an optional `duration` (`DurationUntilLeaves`, `DurationEot`,
    `DurationUntilNextTurn` only; any other Duration is refused at construction). The executor's
    return registry (`core/executor/returns.py`, `Executor._run_returns`, folded into
    `state_fingerprint` while non-empty) keeps one row per moved object and returns it through
    the normal MOVE_ZONE path when the duration ends: 610.3a/b (anchor already gone: nothing
    moves), 610.3c (owner's control), 610.3d (one batch), 400.7 by journal provenance, tokens never
    return (704.5d), Containment Priest applies (614), a returning Aura asks its owner for a host
    (303.4f-g, V32 cherry-picked from `engine/verify-fixes-2`). The per-seat view (`returns_to`,
    `returns_when`) and the G1 probe trace show every row. Templates: Kitesail Freebooter, Idol of
    Endurance, and a general `B11-exile-np-until-leaves` clause that, behind the enters frame,
    newly compiles Hieromancer's Cage (M19), Banishing Light (FDN, THB), Stasis Snare (FDN),
    Banisher Priest (M14), Prison Realm (WAR) and Journey to Oblivion (ZNR), all unverified.
  - **The training observation cannot see the rows** (`tools/training`, pinned, so not edited):
    a policy trained on it does not know that killing Banishing Light returns its card (AGENTS
    §10). Add the row (anchor, card, return zone) at the next observation-schema change.
  - **"For as long as ~ remains on the battlefield" (CR 611.2b)** ends when the object phases out
    (702.26f). It must not reuse `DurationUntilLeaves`; it needs its own node or a field.
  - **Calix, Destiny's Hand [−3]** ("until target enchantment you control leaves the
    battlefield"): the anchor is a second target, and `DurationUntilLeaves(source="target")` can
    only name the spell's single target binding. Gap ledger; needs a per-slot referent.
  - **Still unparsed** (each needs a clause the compiler lacks, not a new atom): Prayer of Binding
    ("up to one target", ready for a mapper now), Seal Away ("tapped creature"), Glass Casket
    ("with mana value 3 or less"), Sigrid, Colossal Whale, Glorious Protector, Grasping Giant,
    Hixus, Constricting Sliver, Valki.
  - **A return to a zone other than the battlefield consults no replacement effect.** The move
    path asks `replacement_for_zone_change` only for battlefield entries (`verbs._v_move_zone`), so
    Leyline of the Void would not exile Idol of Endurance's returning cards (B-72 family; general,
    not specific to returns).
  - **Tapped status survives zone changes (CR 110.5b/110.5d).** `CardState.tapped` is never
    cleared when a card leaves the battlefield, so a creature exiled while tapped returns tapped,
    and a tapped creature bounced and recast enters tapped. General engine gap.
  - **Simultaneity is per destination zone.** One MOVE_ZONE per zone, in the fixed order
    battlefield, hand, graveyard, exile; within a zone every object moves at once. V32 chooses
    each entering Aura's host inside the move loop, so an Aura returning in the same batch as a
    creature can pick that creature (strictly, 303.4f sees only objects already on the
    battlefield).
  - Kitesail Freebooter's "You choose ... from it" is still asked when Freebooter left before its
    trigger resolved. CR-correct (the choice is made, nothing is exiled), but the ask has no
    consequence.
- **B-98 [2026-10-29, branch `engine/r5a-until-leaves`; renumbered from B-77 at the integration merge] Ontology R5-6: `TargetingEvent.actor`
  ("becomes the target of a spell or ability an opponent controls") is built; the rest of the
  census needs other pieces.**
  - Done: the optional `actor` Filter over the targeting spell's or ability's controller (the
    TARGETING row's journalled actor), read by `binding._match_node`. Warden of the Woods (M21) no
    longer draws off its controller's own spells; Thorn Lieutenant (M19) compiles through the new
    `B13-targeted` frame. Mapper rule: "can't be the target of spells or abilities your opponents
    control" stays HEXPROOF (MAPPER_GUIDE).
  - Not compiled, each for a reason outside R5-6 (11 cards, 8 sets, by the oracle census):
    - Frost Titan (M11, M12), Diffusion Sliver (M15), Reidane (KHM): "counter that spell or ability
      unless its controller pays": abilities never sit on the stack, so an ability cannot be
      countered (R5 gate round 2).
    - Ward (Cackling Prowler, Tolarian Terror, Zul Ashur; FDN): the IR has no WARD keyword, and
      ward (CR 702.21a) also counters abilities, which cannot be countered here.
    - Battle Mammoth (KHM): its clause "you may draw a card" does not parse on its own.
    - Shield Mare (M19): "When this creature enters or becomes the target ...", a trigger on either
      of two events, which no template composes.
    - Leyline of Combustion (M20): "you and/or at least one permanent you control" triggers once per
      spell, not per targeted object, and "that player" needs a referent for the event's actor.
- **B-99 [fixer 3, 2026-10-29; renumbered from B-75 (phasing took it) and then B-97 (R5-1 took it) at the integration merges] Chandra, Flame's Catalyst's "If that spell would be put into your
  graveyard, exile it instead" is not applied.** Her -2 casts a red instant or sorcery from your
  graveyard through `stack.cast_card`; the rider's replacement (`B5b-repl-graveyard-exile`) is never
  registered for that cast, so the spell resolves into the graveyard and can be recast. Stronger than
  printed, but Chandra, Flame's Catalyst is not castable yet, so nothing exploits it today. Repro:
  `tools/scenarios/chandra_catalyst_recast_draw_journalled_once.json` (its note says where the card
  should land: exile; it lands in the graveyard). Owner of the fix: the ontology round, which is
  redesigning replacements created at resolution (DESIGN_ATOM_ONTOLOGY §10).
- **B-100 [fixer 3, 2026-10-30; renumbered from B-76 (the defender entry took it) and then B-98 (R5-6 took it) at the integration merges] Two permission rows do nothing until the R5 permission lane.**
  Weaker than printed; never a crash and never a phantom option.
  - Radha, Heart of Keld's "you may play lands from the top of your library" compiles to a free
    row whose CAST is filtered to lands. A land is never cast (CR 305.1: playing it is a special
    action), so the row can do nothing: the CAST head refuses with a cast-gap ledger row, the
    may-offer narrows to skip, and `query.legal_activations` no longer offers the row
    (`query.inert_free_row`). R5-3's `play_lands` makes it playable.
  - Demonic Embrace's "You may cast this card from your graveyard ..." row is an activated
    ability, and activations need the source on the battlefield (`window:not_on_battlefield`), so
    the graveyard cast is never available. R5-2's permission lane (a StaticAbility CAST) fixes it.
  - Also: a CAST whose designation is empty (a nonland on top for Radha, a non-Goblin for
    Conspicuous Snoop) used to offer "fire" for a no-op; it now narrows to skip (CR 117.3).
- **B-101 [fixer A, found 2026-10-30; numbered B-82 in 73e41cd (a duplicate of the
  multicoloured-token entry's number), then B-83, renumbered at the integration merge]
  Protection (CR 702.16) works only against blocking.** **[FIXED on branch
  `engine/verify-fixes-3` 2026-10-30 (fixer 3, V44), pending the era-boundary merge]**
  - Fix: one oracle, `legality.protected_from(executor, holder, source)`, over
    `layers.protection_rows` (printed and granted keywords, static grants to cards AND
    players, each quality judged in the coordinates of the ability that gives it, so
    Runed Halo's NAME_CHOSEN reads the Halo's name). Consumers: the TARGET chokepoint
    `enumerate_candidates`, the "any target" player widening, the synthetic
    target-opponent slots of spells, activations and triggers (702.16b); the Aura
    SBA and the enter-without-cast host choice (702.16c, 704.5m); an Equipment SBA
    that unattaches it (702.16d, 704.5n); damage prevention for players and
    permanents with a DAMAGE_PREVENTED row (702.16e); block legality reads only the
    ATTACKER's protection (702.16f), so a protected creature may now block the
    quality (the old blocker-side veto was wrong). A universal quality is
    protection from everything (702.16j). Each fighting creature is now the source
    of its own damage (CR 701.12b), so protection, deathtouch and lifelink read it.
  - The three repros below now pass and live in `tools/scenarios/`, with 11 more
    protection packs (Baneslayer, Basri's Lieutenant, Feat of Resistance, Feline
    Sovereign, Runed Halo, Sparkhunter Masticore). No verified card pack changed.
  - Residues: (1) no CR 608.2b re-check at resolution, for protection or anything
    else (a target that gains protection after it was chosen stays a target);
    reachable only through trigger order today, since the response window offers
    counterspells only. (2) 702.16n/p ("this effect doesn't remove Auras") has no
    IR; no compiled card needs it (M15 Spectra Ward does not compile). (3) The
    compiler has no general "Protection from <quality>" line: only the printed M21
    forms compile, and an unseen "Protection from black" stays unparsed
    (`compiler._is_keyword_line`); 702.16k (from a player) has no compiled shape.
    (4) A fight's DAMAGE journal rows still name the fight's source as the cause (B-92).
  - `layers.protections_of` has one consumer, block legality. Nothing makes a protected
    permanent or player an illegal target for sources of the quality (702.16b), prevents their
    damage (702.16e), or stops their Auras and Equipment (702.16c/d). Repros (failing before
    V44, now moved to `tools/scenarios/`): `feat_of_resistance_protection_targeting.json`,
    `feat_of_resistance_protection_damage.json`, `runed_halo_protects_player.json`.
  - Player protection does not even land: Runed Halo's static GRANT_ABILITY(PROTECTION
    (NAME_CHOSEN)) to Zone(PLAYER, YOU) leaves `protections_of(player)` empty (the layer
    keyword map is built over card handles only), and `protections_of` ignores static-layer
    grants for cards too (it reads keyword/grant layers and `_granted`).
  - Not small, so not done in the template lane. Plan: (1) `protections_of` covers static grants
    and player handles; (2) a targeting veto beside `_hexproof_vetoes_target` (both cards and
    players; quality judged against the targeting source, NAME_CHOSEN in the granting
    permanent's coordinates, i.e. Runed Halo's chosen name); (3) damage prevention in the
    noncombat and combat damage lanes; (4) the 704.5m/n attachment SBAs. Every protection card
    changes play (Baneslayer Angel, Basri's Lieutenant, Feat of Resistance, Runed Halo, other
    sets), so it belongs to an era boundary. Engine lane.
- **B-102 [fixer A, found 2026-10-30; B-84 until the integration merge] Attack triggers can see a creature put onto the battlefield
  attacking** (latent: no M21 card misfires today).
  - `Executor.join_attack` (`executor/__init__.py` ~1915) journals the same DECLARE_ATTACKERS
    row, in the same declare group, as a declared attacker, and `binding._match_node` (~919)
    matches every such row. CR 508.3a and 508.4: a creature put onto the battlefield attacking
    never "attacked", so no "whenever ... attacks" trigger may see it. Falconer Adept's Bird
    (80a895f) and Basri Ket's -2 Soldiers take this path.
  - Hidden today by two accidents. The joined row is journalled before the token's own
    ZONE_CHANGE row, so at match time the token's keywords are not yet in the layer map (a
    flying filter misses the Bird). And the per-declaration dedup (`binding._queue` ~728, one
    instance per ability per declare group) has already queued any trigger the declared
    creature matched. Probes 2026-10-30 (Tide Skimmer + Falconer Adept, and a per-creature
    flying filter with only the Adept declared): no extra trigger. A filter on type, subtype,
    token-ness or controller that the token matches and no declared creature does would fire.
  - Coupling: that dedup is itself wrong for per-creature triggers (B-103). Whoever fixes B-103
    must exclude joined rows in the same change, or the Bird and the Soldiers start
    triggering. `_group_size` (battalion) and the `declare_attackers` register
    (THAT_MANY_COUNT) count joined rows as well.
  - Fix: mark the joined row (its own payload, or an `entered_attacking` set folded into the
    replay hash) and skip it in the DeclareAttackersEvent match, the group size and the
    register. Engine lane.
- **B-103 [fixer A, found 2026-10-30; B-85 until the integration merge] "Whenever a creature ... attacks" fires once per
  declaration, not once per attacker** (live in M21, weaker than printed).
  - `binding._queue` (~728) queues one instance per ability per declare group for every
    DeclareAttackersEvent. That is right for "one or more" and "attack with two or more"
    (Basri Ket's -2, Tide Skimmer, Mangara) and wrong for a per-creature trigger, which
    CR 603.2c fires once per matching attacker. Repro, failing today:
    `tools/scenarios/known_bugs/hooded_blightfang_each_deathtouch_attacker.json` (two
    Blightfangs attack: four triggers are due, two fire, so the life totals end 22/16, not
    24/14).
  - Live in M21: Basri, Devoted Paladin's -1 puts its counter on one attacker per declaration,
    and Hooded Blightfang drains once however many deathtouch creatures attack. Across the 19
    sets these two, Basri Ket, Tide Skimmer and Mangara are the only compiled attack triggers
    not keyed on IS_SOURCE (snapshot 2026-10-30).
  - Design decision, an IR change: `DeclareAttackersEvent` cannot tell "a creature attacks"
    from "one or more creatures attack" (Basri Ket's -2 and the Paladin's -1 differ only in
    their filters). (a) A `batch: bool = False` field, omitted when False so per-creature trees
    stay byte-identical, set by the compiler on "one or more", "attack with N or more" and
    "you attack"; the dedup then applies to batch triggers only. Three goldens re-bake (Basri
    Ket, Tide Skimmer, Mangara). Recommended. (b) Infer batching in the engine from a
    CONTROLLER_COUNT_GE condition: no schema change, but it cannot separate Basri Ket's -2
    from the Paladin's -1, so it is not enough. Either way it lands with B-102's exclusion.
- **B-109 [2026-10-30, branch `engine/r5b-go-items`] Ontology R5-7: `AbilityActivatedEvent` and
  one CR 605.1a classifier.**
  - Done: `AbilityActivatedEvent(source, kind, actor)` replaces `LoyaltyActivatedEvent`; `kind`
    (ANY / NON_MANA / LOYALTY) is required. `ability_tree.is_mana_ability` implements 605.1a's four
    criteria (no target, a reachable ADD_MANA, not a loyalty ability, no card moved to or from a
    library by cost or effect) and is the one classifier the games driver, `bench/router.py`, the
    activation journal row and the NON_MANA lock read. The lock gate is in
    `legality.ability_playable` (`prohibited:activation_lock`, CR 602.5). One `ABILITY_ACTIVATED`
    journal row per activation, mana abilities included. `CostLoyalty(0)` is legal. Faith's
    Fetters' third clause and Keral Keep Disciples re-baked; packs `faiths_fetters_activation_lock`,
    `faiths_fetters_locks_loyalty`.
  - Gap ledger: "whenever you activate a boast ability" (KHM Frenzied Raider) has no kind (boast
    has no IR component). Expressible but not compiled: the trigger users Runic Armasaur and
    Kurkesh (NON_MANA), Sarkhan's Whelp (ANY), Chandra's Regulator (LOYALTY); the locks Bound in
    Gold, Pithing Needle, Sorcerous Spyglass (NON_MANA) and the twelve "can't be activated" cards
    (ANY; `reports/r5_census_2026-10-29.json`). Pithing Needle, Spyglass and Phyrexian Revoker
    also need their named source (`CHOOSE_NAME` + `NAME_CHOSEN`).
  - "[0]:" abilities are expressible now but no template parses them (`frames.py` B13-loyalty and
    the `templates_b5c.py` loyalty patterns take only `+N`/`−N`): 12 cards in 11 sets, none in
    M21.
  - After `engine/verify-fixes` merges: its B-90 payment witness picks mana sources through
    `ability_playable` and taps them through `activate()`, so an ANY lock already skips a locked
    mana source and each tap journals its row. Pin that with a test at the merge.
    **[PINNED at the merge, 2026-10-30: five tests in `test_executor_legality.py`
    `TestManaAbilitiesWhilePaying` (an ANY lock keeps the locked source out of the plan; a
    NON_MANA lock spares it; a window tap and an in-resolution tap each journal one row; an ANY
    trigger sees a tap made while paying). One correction: inside a running atom ("you may
    pay", "unless its controller pays") the witness taps in place, not through `activate()`,
    because a nested activation would settle triggers in the middle of the resolution. That
    path now writes the same `ABILITY_ACTIVATED` row (`legality.tap_for_payment`). The witness
    also asks `is_mana_ability` (605.1a) for every source it considers.]**
- **B-110 [2026-10-30, branch `engine/r5b-go-items`] Ontology R5-10: abilities never sit on the
  stack, so "counter target activated or triggered ability" has no legal target** (engine gap).
  - Done: `FAtom(STACK_KIND_EQ, string_value)` with the closed vocabulary SPELL / ACTIVATED /
    TRIGGERED (validated per predicate, `ability_tree._FATOM_STRING_VOCAB`); every compiled "counter
    target … spell" carries SPELL (26 cards in the 19 sets, 5 M21 goldens); the counter window
    asks a Choose-based counterspell's mode set, then its targets (`stack._declare_modal_counter`).
  - Gap: `activate()` and the trigger drain resolve abilities at once (CR 602.2 and 603.3 put
    them on the stack), so STACK_KIND_EQ ACTIVATED/TRIGGERED holds for nothing. Sublime Epiphany's
    second mode and Tale's End's ability half are never offered (CR 700.2a), which is weaker than
    printed. Remove with the priority and stack rung: abilities as stack objects.
  - Not done (outside R5-10's registered blast radius): M21 Unsubstantiate's "Return target spell
    or creature" compiles the spell half as `FNot(IS_PERMANENT)` over the stack, so it cannot take
    an artifact, enchantment or planeswalker spell (weaker than printed, latent: no window offers it
    with a spell on the stack). Fix: `FOr(STACK_KIND_EQ SPELL, TYPE_EQ Creature)`, one golden.
  - The bench labels a multi-mode `choose` token "choice N" (`bench/protocol.py` maps tokens to
    bullets only when every option set is one mode); it is representable but not described.
- **B-111 [2026-10-30, branch `engine/r5b-go-items`] Verified records to re-verify after the R5
  items** (their tree changed, their `verified` block was not edited, so they are out of the
  verified supply until a verifier passes them again):
  - re-verify after R5-11 (schema rename only, `color` -> `colors`): FDN Imperious Perfect and
    Stroke of Midnight (agent-mapped `ir`, the key renamed in the record by coordinator ruling (a);
    FDN Regal Caracal, unverified, was renamed too), FDN Prideful Parent and Release the Dogs
    (compiler trees). FDN verified 59 -> 55.
  - re-verify after R5-10 (STACK_KIND_EQ SPELL added to the counter target): M21 Cancel and
    Miscast.
  - re-verify after R5-7 (the trigger's event node is AbilityActivatedEvent, kind LOYALTY): M21
    Keral Keep Disciples (stamped by the G3 finisher on `cards/integration`).
  - After the merge of `cards/integration` d955f67: M21 verified 159 -> 156, FDN 59 -> 55; every
    card pack of these cards still passes.
- **Weaker than printed (lower priority):**
  - "Up to N target" cannot be cast with zero targets (the C17 clamp). A library search can never
    fail to find (CR 701.19b).
  - M21 Subira, ZNR Sneaking Guide and FDN Goblin Smuggler's "target creature can't be blocked"
    activations get no target slot (`query.activation_target_slots`), so they do nothing.
    **FIXED on branch `engine/verify-fixes-3` (V34, 2026-10-29)**: a synthesized one-creature slot
    from the IS_ANY_TARGET combat filter, and the targeting restriction is checked at resolution
    and locked in (CR 608.2b).
  - A cast trigger filtered by `TARGETS_SOURCE` never fires, because the CAST match context does not
    bind the spell's targets (FDN Gnarlback Rhino).
  - [2026-10-29, Ugin] Ugin's [−10] "put up to seven permanent cards from your hand onto the
    battlefield" puts min(7, n): the CHOOSE count clamp (C17) never offers fewer, and with more
    than seven it asks which seven. Fewer options than printed, never more.
  - [2026-10-29, Ugin] An Aura put onto the battlefield by an effect (Ugin's [−10]) enters
    unattached and the CR 704.5m sweep buries it. CR 303.4f lets its controller choose what it
    enchants as it enters, and 303.4g keeps it in hand when nothing is legal.
  - [2026-10-29, the activation X lane] The folded `activate` takes its targets before it asks X,
    so X is announced after the designation (CR 601.2b orders X before 601.2c targets). No carrier
    has both: Ugin's [−X] has no target.
- **B-22 resolved provisionally (2026-10-24)**: the contract is `pytest MTG_bot` (default markers)
  plus `tools/check.sh` for `pytest tools` and the packs; baseline B0 in CLAUDE.md. Owner may override.

### Parked 2026-10-24: the public LLM leaderboard

Owner decision: build the benchmark core now as instrumentation; park the product. Release only
when every gate holds: the priority and full-stack rung has landed; the engine-error rate is below
an agreed bound on a model-driven soak; engine, pool and harness hashes are frozen per season; the
W&B key in history is revoked; a private split exists outside the public repo.

