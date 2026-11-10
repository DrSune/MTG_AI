# 190 — Fresh-eyes audit: bugs, weak spots, and what works against general learning

2026-11-10, main at fb0e5eb. The owner asked: "Look through this project ... and note down what you
think is suboptimal, a bug, poorly incentived for generalized learning etc, and progress this
project." This note is that list. Every item says how it was checked. Measured numbers are in §9
and §10 (commands in NUMBERS). Items BACKLOG already holds are named, not repeated.

## 0. The short version

1. **The deal decides most games, so the win/loss signal is thin.** Two near-equal networks play
   each deal twice with seats swapped. The same seat wins both games in 84% of two-colour deals and
   93% of random-pile deals (§9.1). Only the rest says anything about who plays better. This is the
   structural reason a PPO step needs millions of decisions (B*, note 184).
2. **Every PPO run since r19 was a walk, not a climb.** r20 to r23 changed the top choice in 6-26%
   of decisions and gained nothing measurable (§9.2, 189 §2). The steps were far larger than the
   signal in them.
3. **Nothing in PPO makes the network read a card's parts.** Name dropout is off during PPO
   (§1.3), so about 250 updates have tuned card-name embeddings alone. An unseen card has no name
   embedding. King goal 2 rests on a skill training stopped rewarding.
4. **The game it practises is not quite Magic.** A player acts only in their own main phases, plus
   two narrow windows. About 30% of M21's nonland cards play weaker than printed, and instants are
   learned as sorceries (§4.1).
5. **The yardstick is soft.** Half of every gate and ladder is played on decks the network never
   trains on, where it is no better than the heuristic (0.501). The heuristic never activates an
   ability. The gate re-tested until it passed (§1.4, §3).
6. **This learner removes its own exploration.** With no entropy bonus r25's policy lost 0.003 of
   entropy per update, at a step small enough to hold a signal (§2.4). Sharper play wins more
   sampled games without one better decision, so the training win rate alone cannot show
   learning. The bonus of 0.002 that r20 to r23 carried does nothing against it (one update
   measured term by term, §10.5). r26 runs with 0.0075.
7. **A second GPU process is very expensive.** Seven small probe processes cut r25 to a fifth of
   its speed (§2.7). Evaluations must go through the batched learner, one at a time.

## 1. Bugs

Fixed in fb0e5eb:

1. **Training deals were the same in every run.** The deal seed was `TRAIN_SEED0 + game number`
   whatever `--seed` said, so r17 to r23 each trained again on the decks and shuffles their
   ancestors saw. Now `learner.py:474` adds `1_000_000_000 * seed`. The owner's worry about
   memorised deals was justified.
2. **The KL stop's extra forward pass ran even with the stop off** (24% of an update). Skipped now.

Open:

3. **Name dropout never applies in PPO.** `ppo.py:58` calls `model.eval()`; `model.py:94` drops
   names only `if self.training`. Only behaviour cloning ever dropped names (10%). See §5.1.
4. **The gate is a repeated test with no correction.** `learner.py:969` passes a gate when
   `score >= gate_score and ci95[0] > 0.5`. With `--gate-score 0.5` and a gate every update, the
   first lucky gate freezes a version. r20's v2 passed on its 13th try at 0.5192 (+1.94 SE; the
   chance of one false pass in 13 is 28%) and measured 0.5217 [0.499, 0.544] on fresh deals. The
   README's canonical command still uses 0.5. r25 uses 0.55 over 1,000 deals (about +9 SE).
5. **Gate deal blocks overlap above 1,000 deals** (`learner.py:913`: `GATE_SEED0 + 1000 * n`).
6. **The PPO update is not reproducible from the run's seed.** `ppo.py:34` uses the global
   `np.random.rand` and `ppo.py:45,84` the global `random.shuffle`, both unseeded. The rest of the
   stack uses seeded `random.Random` instances per purpose.
7. **The encoder truncates silently.** `features.py:493` cuts entities at `MAX_CARDS + 8` with no
   counter, and an option that points at a dropped entity gets reference 0. Option overflow is
   counted (r20: 1,699 asks in 8.56M decisions, all handed to the heuristic); entity overflow is not.
8. **The first buffer after any start holds the shortest games.** Rows are appended when a game
   ends. r25's update 1 had 2,854 games against about 1,950 later. Update 1's win rates and
   entropy are biased; so is the first update after every `--resume`.
9. **Search forgets what the searcher knows about its own library.** `search.py:80` (`determinize`)
   reshuffles the searcher's whole library, losing scry results and mulligan bottoms.
   `reshuffle_unknown` (`search.py:426`) does this correctly, but only the labeller calls it.
10. **Lint is not gated for the training code.** `tools/check.sh:33-35` runs ruff on
    `MTG_bot/bench` only. `tools/selfplay` has five errors (`learner.py:157`, `preflight.py:32`,
    `model.py:17`, `model.py:88`, `test_simulator.py:5`).
11. **The allocator setting lived in the launch command.** Without
    `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True` torch reserves 54.5 GiB for a 21.4 GiB need
    (189 §1), and a run started without it dies as r24 did. `tools/selfplay/launch.sh` now sets
    it for every registered run; a learner started by hand still needs it.
12. **Two errors of mine in note 189**, corrected in its §8: the gate standard error was
    overstated twofold (games treated as independent; the deal is the unit), and the "300-deal
    figure 0.595" for gen.pt was r20 v2's 100-deal ladder under the mulligan engine. Note 186 has
    gen.pt at 0.5875 [0.555, 0.620], which r25's start ladder confirms (0.590 [0.564, 0.616]).

Already in BACKLOG ("Self-play stack"): optimizer moments lost on `--resume`; an evaluation running
at a resume is lost; workers importing torch (about 9.5 GB for 18).

## 2. Suboptimal: the learner

1. **Step size against signal.** r20 to r23 took steps whose gradient was about 99% noise, at
   learning rates 5e-5 to 1.5e-4. The policy moved a long way (KL 0.27 to 0.51 from its parent,
   §9.2) for no gain. r25 sets the learning rate so the policy moves KL 0.01-0.02 per B* of data.
2. **Only one seat learns.** In a training game both seats sample, but only the learner's seat is
   recorded. Half of all inference serves the frozen opponent. A learner-against-learner share
   `s` gives `(1 + s)` times the data per game: about 1.29x at `s = 0.5`. `_finish_train`
   (`learner.py:673`) already accepts two recorded seats. Not built yet; r26 runs as r25 did.
3. **The opponent is one frozen network.** 85% of r25's games are against v0, 15% against the
   heuristic. That trains a best response to one fixed policy. BACKLOG has the league idea.
4. **Entropy.** r20 to r23 ran with a bonus of 0.002 and entropy stayed between 0.21 and 0.33 with
   no trend. r25 has no bonus and its entropy fell by 0.0029 per update: 0.238, 0.232, 0.232,
   0.226, 0.229, 0.222, 0.217, 0.212, 0.219 (updates 2 to 10). The cause is real but trivial
   learning: a sampled off-choice loses more often than the top choice (§10.1), so the policy
   gradient says "sharpen". One update measured term by term (§10.5) confirms it: the policy term
   lowers entropy, and does not when the outcomes are shuffled over the decisions; the value term
   raises it. Two costs: exploration dies, and the sampled win rate against v0 rises without any
   decision changing. A bonus of 0.002 offsets about a tenth of r25's fall, so it is not what held
   r20 to r23 level. Their steps were 2.5 to 7.5 times larger; what did hold them is not known.
   I chose `--ent 0.0` for r25 on the owner's "win/loss and nothing else" rule and stopped it
   after ten updates. r26 runs with 0.0075, the size whose measured push balances the fall
   (189 §8-§9). BACKLOG lists it as a scaffold to remove.
5. **The value loss shares the 27M trunk** (`vcoef 0.5`), and through it moves the policy. A
   value-only update at v0 moves the policy by KL 0.0021 and changes the top choice in 0.9% of
   decisions; the full update does 0.0026 and 1.0% (§10.5). On the trunk the value term's
   gradient is 8.6 times the policy term's (§10.4). That is drift with no evidence behind it. With
   the coefficient at 0.05 the value head learns as well (Adam rescales each parameter).
   Candidates for the run after r26: coefficient 0.05, no value gradient into the trunk, or a
   separate value phase (phasic policy gradient). BACKLOG has the item.
6. **Small things.** Value clipping (`vclip 0.5`) is inert at these learning rates. AdamW has no
   parameter groups (`trainer.py:42`: decay on embeddings, norms and biases; negligible at
   lr 2e-5). Advantages are normalised over the whole buffer (`ppo.py:56`), which is sound.
7. **Throughput.** r25 at steady state: 133 s per update (86 s update, 47 s collecting), 739
   learner decisions/s. During an update the GPU is the limit (91% busy, CPU 56%): inference and
   training time-slice it. Between updates the Python engine is the limit (CPU 94%, GPU 69%):
   about 13 ms per decision per worker. Seven batch-1 probe processes beside the run made update 8
   take 636 s. So: no side jobs on the GPU during a run, and a profile of a worker's time (engine,
   legality and payment planning, `features.encode`) is the cheapest throughput work under D21.
8. **r24's design** could not have tested D21: about 1,000 Adam steps per update at lr 1.5e-4
   under a KL stop that fires after a few dozen (189 §1).

## 3. Suboptimal: evaluation

1. **Half of every gate and ladder is off-distribution.** `learner.py:781` alternates stress and
   coherent decks by `i % 2`; training has been all coherent since r21. A stress deal carries
   about a fifth of the information of a coherent deal for a change trained on coherent decks
   (§9.1), so the mixed gate is about 0.6 as efficient and dilutes any gain. Read gates by mode
   (`by_mode`); the coherent half is the on-distribution test.
2. **On stress decks the network equals the heuristic: 0.501.** That score fell from about 0.60
   exactly when the London mulligan entered the game (§9.3: r23's v0 is r20 v2, the same weights).
   The network keeps almost every hand (r23 learned "keep", mulligan rate 0.003; v0 in self-play
   mulligans 16 of 1,516 hands, §10.4), while the heuristic follows its authored rule
   (`heuristic.py:498-502`). On piles with 13.4 lands in 60
   that rule probably matters most. This is a hypothesis; the test is one evaluation with the
   heuristic's mulligan rule switched to "always keep".
3. **The heuristic is a soft yardstick.** It plays a land, casts the dearest spell, attacks unless
   a blocker would win the fight, and never activates an ability other than a planeswalker's. The
   network was cloned from it first. "0.59 against the heuristic" is strength against a curve-out
   player, and blind spots it shares with the heuristic are invisible on this scale.
4. **Strength on unseen cards is not part of any gate.** What is not measured is not selected
   for. The last masked-name figure was from r15 (0.650 to 0.605). Fresh ones (§10.2, §10.3):
   with card names masked v0 falls from 0.590 to 0.531 against the heuristic, and on FDN, a set
   it never saw, it scores 0.565.
5. **Old run logs are stale.** `reports/training_runs.jsonl`, `training_ops.log` and
   `TRAINING_STATUS.md` describe the deleted October stack.

## 4. The game being learned

1. **No real priority (BACKLOG B-110, "the priority rung"), now measured.** `_play_turns`
   (`games.py:1426`) gives `take_acts` to the active player once per main phase (1504, 1540).
   Besides that there are two windows: counterspells against a spell (`stack.py:1030`) and
   one-target damage or pump instants after blockers (`stack.py:996`, atoms at 934). In 60
   heuristic games every one of 2,216 `act` asks fell in the asker's own turn. Card census:

   | | M21 | M20 |
   |---|---|---|
   | Nonland deckable cards | 240 | 231 |
   | Instants | 37 | 28 |
   | of which counterspells (have a window) | 4 | 3 |
   | of which one-target damage or pump (combat window; counted by verbs) | 12 | 15 |
   | of which playable only in the caster's own main phase | 21 | 10 |
   | Flash permanents (play at sorcery speed) | 7 | 5 |
   | Cards with instant-speed abilities usable only in own main phase | 43 | 36 |

   M21's 21 include Eliminate, Heroic Intervention, Opt, Frost Breath and Unsubstantiate. About
   30% of M21's nonland cards are weaker than printed. A policy trained here learns "instants are
   sorceries", which is wrong for the real game and for Commander most of all.
2. **The step is not an input** beyond first or second main phase (`features.py:405`). It must
   arrive with the priority rung.
3. **The policy does not see its own deck list or what is left in its library.** Scheduled
   (`docs/PLAN_LEARNING.md:351`; the owner's vision, `docs/OWNER_VISION_LEARNING.md:65`). It
   shows in the value head: in the first quarter of a game it explains 3% of the outcome's
   variance (§10.4), although the deal decides most games.
4. **Draws.** A turn-cap or stall draw pays -1 to both seats (`learner.py:625`). It is deliberate
   (D10) and rare: 21 of 12,700 evaluation games in r20. Not a problem.
5. **Training decks have no shape.** A coherent deck is two colours, 24 basics and a uniform sample
   of the pair's nonland cards (`games.py:1595`): no curve, no plan. Deck building is the Teacher's
   job in the owner's vision; until then the network learns to play piles.

## 5. What works against general learning

1. **Names over parts.** A card's vector is its name embedding plus the mean of its component
   tokens (`model.py:82`). PPO never drops names (§1.3), so every PPO update is free to put what it
   learns into the name. A card the network has not seen gets the unknown-name vector
   (`extend_cards`, `model.py:135`): for it, the component path is all there is. Fix for a
   successor: mask names per card per game in self-play, the mask drawn from the job seed and
   written into the features, so acting and updating see the same input.
2. **A card is a bag of parts.** The mean over up to 128 component tokens loses the ability tree's
   structure and order: "when this dies, draw" and "when you draw, this dies" pool to the same
   bag. A limit for King goal 2 once cards get complex.
3. **Mana cost colours are missing from the parts.** `card_tokens` (`features.py:133`) emits type,
   subtype, a mana-value bucket and the tree. `CardRecord.mana_cost` is not tokenised, so a new
   card's colour requirements are invisible. Numbers are bucketed 0-5, 6+ and negative.
4. **Two sets, one opponent, one deck recipe.** Training sees M21 and 25% M20, against one frozen
   network. FDN has 175 verified cards and had never been used, not even to evaluate, before
   §10.3.
5. **The same deals in every run** (fixed, §1.1).
6. **The gate rewards only strength on trained cards** (§3.4).

## 6. Search and the simulator

- `determinize` gives the opponent a hand and library drawn uniformly from the whole deckable pool
  (`search.py:89`): land-poor five-colour piles. E2 replaces it through `draw_worlds`
  (`search.py:205`).
- `Searcher.choose` (`search.py:210`) switches move on the mean of two sampled worlds with no
  significance threshold. A simulation stops at the searcher's next turn and is scored by the
  value head; `MAX_SIM_DECISIONS = 400` (`search.py:67`).
- The simulator (`simulator.py`) builds its own encoder, decodes the hand as a sorted multiset and
  the library given the hand. `sample_hands` (`simulator.py:244`) re-runs the whole encoder at each
  step of the hand: a cost E2 pays at play time. Library order is not modelled.
- `paired.py` pairs on the deal and bootstraps over deals: sound.

## 7. Housekeeping

- Seven loose notes at the top level (`engine_map.md`, `gemini_analysis.md`, `ideas.md`,
  `notes.txt`, `project_goals.md`, `project_specific_gemini_context.md`, `thought_checkpoint.md`)
  and 259 tracked files in `reports/`, most of them October evidence for the deleted stack. A
  cleanup pass should keep what KNOWLEDGE cites and drop the rest.
- Run output is flooded with "supply[M20]: shape-gap exclusion" lines.

## 8. The other agent's analysis (`gemini_analysis.md`), point by point

1. *Minibatches decoupled from B\*, KL stop cutting updates short.* Right about the cut. The remedy
   is not accumulation: small-learning-rate minibatch steps are noise-equivalent and keep the data
   fresh (189 §2).
2. *Pre-collation memory spike.* Its streaming fix (ad23f73) did not prevent r24's second death.
   The cause was the allocator's reserve (§1.11).
3. *Search's opponent sampler is crippled.* Agreed (§6).
4. *Value clipping biases the value.* Right in theory, inert in practice at these step sizes.
5. *Draws pay -1 to both seats.* True and deliberate (§4.4).
6. *The progress log lacks buffer and target.* Already fixed in the code.
7. *Commander caps and the Python engine's ceiling.* Noted; the engine is the CPU-bound half of
   the loop (§2.7).

## 9. Numbers

### 9.1 The deal decides

Pooled over the `eval_rows.jsonl` of r20, r21, r22, r23_mulligan and r25. A deal is two greedy
games on the same decks and shuffles with seats swapped.

| Pairing | Decks | Deals | Same seat wins both | Agent wins both | Agent loses both | Score | Per-deal sd |
|---|---|---|---|---|---|---|---|
| Learner vs its frozen parent (gates) | stress | 5,682 | 0.932 | 0.034 | 0.034 | 0.500 | 0.131 |
| Learner vs its frozen parent (gates) | coherent | 5,697 | 0.835 | 0.082 | 0.084 | 0.499 | 0.203 |
| Network vs heuristic | stress | 1,221 | 0.770 | 0.182 | 0.048 | 0.567 | 0.230 |
| Network vs heuristic | coherent | 1,220 | 0.492 | 0.484 | 0.024 | 0.730 | 0.272 |
| Network vs random | stress | 817 | 0.356 | 0.644 | 0.000 | 0.822 | 0.239 |
| Network vs random | coherent | 825 | 0.104 | 0.896 | 0.000 | 0.948 | 0.153 |
| Heuristic vs random | stress | 523 | 0.424 | 0.574 | 0.002 | 0.786 | 0.249 |
| Heuristic vs random | coherent | 525 | 0.238 | 0.760 | 0.002 | 0.879 | 0.216 |

What follows from it:
- Pairing cuts a gate's variance 7.3 times (stress) and 3.0 times (coherent) against unpaired
  games (unpaired per-deal sd would be 0.354).
- A 1,000-deal mixed gate has SE 0.0054, not the 0.011 written in 189. Its coherent half alone:
  0.0091. Nine gates pooled: 0.0018 (coherent half 0.0030).
- Seat 0 wins 0.489 of gate games on stress decks and 0.504 on coherent decks: no seat advantage.

### 9.2 Runs since r19: movement without gain

Greedy ladder score against the heuristic, by deck mode (95% half-width about 0.045 stress, 0.057
coherent for r19-r22 at 75 deals a mode):

| Version | Stress | Coherent |
|---|---|---|
| r19 v0, v1, v2, v3 | 0.587, 0.573, 0.587, 0.580 | 0.710, 0.713, 0.733, 0.750 |
| r20 v0, v1, v2 | 0.593, 0.587, 0.610 | 0.737, 0.740, 0.767 |
| r21 v0, v1 | 0.610, 0.593 | 0.767, 0.767 |
| r22 v0, v1 | 0.603, 0.587 | 0.773, 0.733 |
| r23 v0 (r20 v2's weights, London mulligan in the game; 50 deals a mode) | 0.500 | 0.690 |
| r25 v0 (gen.pt; 250 deals a mode) | 0.501 | 0.679 |

Policy distances between those versions are in 189 §2.

### 9.3 The mulligan step

r20 v2 scored 0.610 / 0.767 before the London mulligan existed in the game and 0.500 / 0.690 after
(same weights). gen.pt, trained 31 updates with the mulligan ask, scores 0.501 / 0.679. The
network gained nothing from learning the ask, and the heuristic gained about 0.09 from its rule.

### 9.4 What an agent is asked (60 heuristic games on coherent decks, 4,408 decisions)

act 50.3% (mean 3.8 options), attack 23.6% (2.1), block 8.5% (2.8), target 5.1% (4.5), mulligan
3.3%, may 1.9%, choose 1.8%, discard 1.4%, order 1.1%, one_of 1.1% (9.7), all others under 1%.

### 9.5 Throughput

| Run | s per update (update + collect) | Minibatches | Learner decisions/s |
|---|---|---|---|
| r20, r21 (gate every update) | 82 + 58 = 140 | 37 | about 700 |
| r25, updates 4-7 | 86 + 47 = 133 | 37-39 | 739 |
| r25, update 8 (seven probe processes beside it) | 387 + 249 = 636 | | 155 |

GPU and CPU by phase (300 one-second samples): during an update GPU 90.8%, CPU 55.8%; between
updates GPU 68.9%, CPU 94.4%.

## 10. Probes on v0

v0 is gen.pt, the network r25 and r26 start from. The scripts and their outputs are in
`reports/v0_probes_2026-11-10/`; commands in NUMBERS.

### 10.1 Top choice against sampling

v0 against itself on 600 fresh coherent deals, one seat playing its top choice and the other
sampling, seats swapped. The top-choice seat scores 0.518 (SE 0.0085). So a policy that only
sharpens gains up to about 0.018 where both seats sample (`win.frozen`) and nothing on the
greedy gates.

### 10.2 Card names masked

The start ladder's 500 deals against the heuristic, played again with every card's name replaced
by the unknown-name vector (`--mask-names`):

| | All | Stress decks | Coherent decks |
|---|---|---|---|
| With names | 0.590 [0.564, 0.616] | 0.501 | 0.679 |
| Names masked | 0.531 [0.506, 0.556] | 0.463 | 0.599 |

Paired on the deal the loss is 0.059 [0.038, 0.081]: 87 deals got worse and 27 better. Two
thirds of v0's edge over the heuristic (0.090 down to 0.031) rests on recognising cards by name.
On the parts alone it still beats the heuristic on the decks it trains on (0.599).

### 10.3 A set it never saw (FDN)

500 deals against the heuristic with both decks built from FDN's 175 verified cards
(`--extend-sets FDN --eval-set FDN`). No FDN card has a name embedding; 99.4% of their component
tokens are known ones (the unknown: `KickerAbility`, a few subtypes). v0 scores **0.565
[0.541, 0.588]**: stress 0.534, coherent 0.595. The pool differs from M21's, and so may the
heuristic's strength on it, so this is not the same scale as the table above. Still, the coherent
figure equals M21 with names masked (0.599): on cards it has never seen, the network plays about
as it plays known cards without their names. King goal 2 is partly there, at roughly half the
trained-set edge on coherent decks (0.095 against 0.179).

### 10.4 v0's own decisions

78,182 decisions from 750 self-play games (both seats sampling, both recorded).

- **The value head is biased.** Its mean is +0.225 where the mean outcome is +0.079: too hopeful
  by 0.146, and by 0.219 at the first decision of a game. Probably the opponent mix of the run it
  came from. PPO normalises advantages, so the policy term does not see the bias; the value loss
  does. One update removes it (§10.5).
- **The value head knows little early.** Explained variance by quarter of the game: 0.03, 0.21,
  0.49, 0.75.
- **Where the randomness is.** In 11.7% of decisions the sampled choice had less than half the
  weight. Mean entropy by kind (share of decisions): act 0.264 (41.6%), attack 0.136 (27.3%),
  block 0.323 (8.1%), target 0.229 (7.2%), one_of 0.768 (1.0%), discard 0.645 (0.7%), choose
  0.503 (0.9%).
- **What it does at act asks.** It passes in 22.9%. When the option is offered it plays a land
  99.5% of the time, casts 50.5% and activates an ability 29.2%.
- **Mulligans.** 16 of 1,516 hands (1.1%).
- **Gradients at v0 on the shared trunk** (26.7M parameters, 31 minibatches). Policy term: norm
  0.728 per minibatch and 0.117 for the whole buffer, a ratio of 0.161 where pure noise gives
  0.180. In 78k decisions the policy gradient has no direction that can be told from noise.
  Value term (at its weight 0.5): 1.197 per minibatch and 1.007 for the buffer, one consistent
  direction 8.6 times the size of the policy term's. Entropy bonus at 0.002: 0.0012. The value
  term's direction and the entropy bonus's have cosine -0.16, which to first order says that
  descending the value loss lowers the policy's entropy. The measured update says the opposite
  (§10.5). This picture is plain gradient descent on the trunk; the update is Adam on every
  parameter.

### 10.5 One update, term by term

From v0, one real PPO update with r25's settings on 52,875 of the decisions above (500 games);
the policy is compared before and after on the 25,307 decisions of the other 250 games. The full
table, and the rule written before the result, are in 189 §8.

| Update | Entropy change on the held-out decisions |
|---|---|
| r25's loss, in two minibatch orders | -0.0038, -0.0069 |
| Policy term alone | -0.0047 |
| Policy term alone, outcomes shuffled over the decisions | +0.0010 |
| Value term alone | +0.0029 |
| r25's loss with a bonus of 0.002, 0.005, 0.01, 0.02 | -0.0036, -0.0028, -0.0016, +0.0008 |
| r25's loss on the first 250 games alone; on the second 250 alone | -0.0068; +0.0019 |

- The sharpening comes from the policy term and needs the real outcomes. It is the learner
  following its data (§10.1), not an artefact of the update.
- The value term alone pushes the other way, and moves the policy as far as the whole update
  does (§2.5).
- Which 250 games are in the batch decides the sign. One update on 500 games cannot size the
  fall; r25's nine buffers can: 0.0029 per update (SE 0.0004).
- The bonus's push grows in a line with its size: per update of a run, about 0.42 times the
  coefficient, less 0.0004. That balances r25's fall at 0.0075, r26's setting.
- I had predicted from the cosines of §10.4 that the value term carries the fall. Wrong. What an
  update does has to be measured on the update.

## 11. Order of work I recommend

1. Keep one registered run on the machine at all times; read it by the rules in 189.
2. Build, with tests, for the successor run: the learner-against-learner share (§2.2), per-game
   name masking in self-play (§5.1), a coherent-only gate option (§3.1), the value loss off the
   policy's trunk (§2.5), a seeded PPO shuffle (§1.6).
3. Build E2, search on the simulator's futures (D21's next build), and fix `determinize` (§1.9).
4. The priority rung (§4.1). It is the largest gap between this game and Magic, and it changes
   what a third of the cards are worth, so it should land before a long training investment.
5. Profile a worker (§2.7).
