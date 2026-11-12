# From fast opponents to the ceiling: search, the simulator and the league

**Status: approved by the owner on 2026-11-11** ("You get the main point, go ahead"; DECISIONS
D22), after two changes of theirs:
- F1 trained high before the learner meets it (§6.4);
- decks chosen for learning by the Teacher and the drafter (§9).

Written by Claude the same day, and amended the same day by a fresh-eyes red team (§13). The
amendment changed decisions 3-5 and 9 of §12, which the owner is told about.

Builds on:
- OWNER_VISION_LEARNING §9-§11, the owner's words;
- PLAN_LEARNING §5 (the league) and §8 (the simulator);
- DECISIONS D8 (inherit representations, not policy), D20, D21 and D22;
- DESIGN_PRIORITY stage 5.

Bound by OWNER_PREFERENCES #1 (no hidden information in play) and #6 (full credit), and by the
owner's rulings:
- the reward is +1/-1 only;
- no privileged critic, ever;
- nothing hand-built about opponents;
- no memorisation.

## Summary for the owner

**Your plan, in four steps:**
1. Fast learners with a lower ceiling make difficult opponents.
2. The high-ceiling learner trains against them, so it gets strong fast.
3. Where it stops rising is a read of its ceiling.
4. Then the ceiling-striving run: explorative self-play from the beginning.

**The players.**

| Name | What it is | Ceiling | Cost |
|---|---|---|---|
| **Learner** (r27, then H1, later H2) | outcome PPO, gamma = lambda = 1, reward +1/-1 | high | cheap games, slow learning |
| **Searcher F0** | a frozen network plus search at play time | that network's, raised by its search | about 1 + 2.3n plain games each (24x measured at n = 6) |
| **Search-trained network F1** | expert iteration: the network is trained toward what its search chose | lower | cheap to play against, costly to train |
| **Simulator** | predicts the opponent's hidden cards from what a player can see | (serves the search) | — |

**Why F1's ceiling is lower.**
- F1's targets are the search's choices, so they inherit the value network's errors and the
  simulator's belief errors. Outcome PPO's credit, the game's result, has neither.
- PPO has biases of its own: the value term moves the shared trunk, and the entropy bonus pulls
  (189 §8).
- Both can settle on fixed answers against their own versions. The league and an exploiter are
  there for both.
- PPO is slow because one game's result is a noisy signal spread over a hundred decisions.

**Steps and gates.**

| Step | What runs or is built | What decides | Machine time |
|---|---|---|---|
| 0 | **r27**: outcome PPO on the new game from r26's newest network | its pre-registration (stage 5) | continuous; paused for measurement windows and F1 |
| 1 | the **search family**, every setting a flag; the simulator recaptured on the new game | **the n-curve**: strength against log n, fitted over all points | one or two windows of ~12 h |
| 2 | **F1, trained high first**, only through gate A (the search well above its own network, confirmed on fresh deals) and gate B (at least 300k targets move the network on unseen deals). It keeps a ladder of checkpoints | at 48 h: faster per machine-hour than r27, with a confidence bound. Then on to its plateau or the owner's target (§6.4) | ~15 h for gate B; days, up to 2 weeks |
| 3 | **H1**: the learner from r27's network (D8) trains against F1's ladder, beside a control arm on r27's league for the same machine time | the **ceiling read** (§7), on a held-out pool | 1-2 weeks per arm |
| 4 | **H2**: explorative self-play from the beginning | your call after the ceiling read | weeks |
| after 3 | **Decks chosen for learning** (§9): the Teacher, then the drafter, trained for learning | at least 1.3x the Elo per machine-day of uniform deals | own runs, for H2 |

**Three earlier attempts at training from search failed. What is honestly different** (§6.2):
- The earlier stalls were the network failing to generalise the search's corrections. The labels
  were reproducible (183 §15-16), and E3 saw no growth from 100k to 300k labels. Nothing here
  removes that by construction.
- What may differ:
  - a stronger search at larger n gives more clear corrections per game (the n-curve counts them);
  - the instant-speed decisions are untrained (grown from `cw`), and the search's corrections there
    may be easier to learn;
  - targets scaled by their standard error, so a comparison where both moves led to the same
    result does not move the network. That was 92% of E3's comparisons. A tie here is not a drawn
    game: 99.7% of r26's 81,000 evaluation games had a winner. It is two candidate moves that,
    played on the same futures, both won or both lost, because most single moves do not decide a
    game of Magic.
- Gate B tests exactly this, at 300k targets on unseen deals, before any long run.
- If it fails, F1 does not run, and the difficult opponents are the learner's own versions plus
  searched anchors.

**Your "consequence x probability"** (§5).
- The simulator's probabilities stay honest (calibrated).
- Consequence decides two things: where the simulator spends its capacity (the positions whose
  decision depends on the hidden cards), and which futures the search looks at. Rare devastating
  hands are sampled more often, then weighted down to their probability.
- The consequence is learned from the search's own per-world results, at every searched decision.
- Labels from deeper levels of the search ("truth lines") wait until something reads the simulator
  there (§5.2).

**Decisions: §12.**

---

## 0. The owner's words and where they go

| The owner (2026-11-11) | Section |
|---|---|
| "Search-improved training sounds good, especially for improving value function and opponent simulator." | §5, §6 |
| "Why does it plan as if I know later cards? ... is it even bad?" Answer: OWNER_VISION_LEARNING §10 | §3.2 |
| "For n, we should test the trendline ... Save all of the search options so we can revisit later as well." | §3 |
| "We should utilize the massive RAM for the replay buffer in search training phase." | §6.3 |
| "As little as possible unrealistic knowledge integrated" | §2 |
| "opponent simulator can be trained for every branching/deeper level of the search, making it really good at predicting the cards we care about (consequence * proability)" | §5 |
| "utilizes lower cieling but faster improvement models to get our high-cieling model up to speed fast by playing difficult opponents" | §6, §7 |
| "That will help assess the cieling" | §7.3 |
| "after which we can do the cieling-striving training run that is explorative self-play from the beginning" | §8 |
| "shouldnt we train the F1 and F0 models to some high ELO? Like 1000 ELO and then start training? If we just play it like it is but plus search, is that really good enough to test what we want to find out?" | §6.4 |
| "If we train the search, opponent predictor and value function, in a more fast/compute efficient way, but lower cieling, then that might improve more, faster. If lowering gamma and lambda doesnt help with this at all, I guess it doesnt make sense. We just need them to improve." | §6.3 |
| "Making the drafter, and training that for maximizing learning, would also be really great (learning is probably winrate agains frozen opponents from a very varied pool, weighted based on ELO)." | §7.2, §9 |
| "You get the main point, go ahead" | status; DECISIONS D22 |
| "Only challenge is whether enemy deck is coherent, or completely random" | §5.5 |
| 2026-11-12, on N5 (simulator worlds no better than uniform at n = 16): "Uniform is just better? Not sure if I trust that" | KNOWLEDGE 192 §7; §5 |
| 2026-11-12: "checking in on the initial run of r27 to see how fast it improves, test network sizes for it, and assume something is going to break or not work, though your plan sounds nice on paper" | §4 |
| 2026-11-12: "Also consider getting started on the drafter based on value function and opponent simulator, getting that working and up to speed would be a nice tool to have or knob to turn on when things get hard or we get stuck" | §9.2, §10 |
| 2026-11-12: "otherwise just continue executing, no need for me in the loop tbh" | §10: the choices this plan left to the owner are made by the agent, with the reasons written down |

## 1. Where we are (measured)

- **The learner learns.** r26 (outcome PPO, gamma = lambda = 1, 98k decisions per update):
  - it froze v1 at update 202 and v2 at 378;
  - v2 is 76 Elo above v0 and scores 0.684 against the old heuristic (KNOWLEDGE 2026-11-10/189
    §10);
  - its gates against v2 since then: 0.542 at 801, 0.524 at 827, 0.519 at 852, 0.508 at 877, none
    passed (0.55 needed);
  - the coherent half of those gates is 0.53-0.57.
- **Search at play time adds a little.** On the old game, the old network plus search (k = 3
  candidates, d = 2 worlds, one turn deep) raised its score against the heuristic by +0.045 to
  +0.060 over the raw network, paired (NUMBERS, 2026-11-04). The gain shrank as the network
  improved (183 §28). Head to head against its raw network it was never measured.
- **Training from search stalled three times:**
  - October, on the old stack: one-shot distillation and search labels were negative (NUMBERS
    2026-10-12, 2026-10-15).
  - r5-r14, November 4:
    - the raw network gained +0.07 over its start in two generations, then stopped;
    - the search corrected about one move per game clearly;
    - its corrections were reproducible, but the network could not predict them on new positions
      and learned the generating network's style instead (183 §15-16);
    - a separate value network did not change that (183 §12-13).
  - E3 (D21): one round of distillation of playout labels changed ~3% of choices and gained
    nothing in games, with no growth from 100k to 300k labels (NUMBERS, "E3 LABEL SCALING").
    - In 92% of its comparisons the two moves had the same result on the same future: both won or
      both lost (186-phase0-labels).
    - Games themselves almost always have a winner: 99.7% of r26's 81,000 evaluation games did;
      0.26% hit the turn cap.
    - What ties a comparison is that one move rarely decides a game.
    - The remedies make each comparison graded, not the games decisive: more futures per
      comparison, the value network at a horizon, effort spent on close decisions, and steps
      scaled by the standard error (§3.2, §6.2).
- **The simulator works on hands.** Its NLL on hidden hands is below a deck-aware yardstick's: 11%
  overall, 12% mid-game, 18% late. Its probabilities are honest. On library contents it is no
  better than the prior (D21; NUMBERS, "E0").
- **The new game.** r26's network transfers to the game with priority: 35/40 greedy and 30/40
  sampled against the new heuristic. A seat makes 74.3 recorded decisions per game, against 52.8
  on the old game (note 191).

## 2. What each piece may know ("as little unrealistic knowledge as possible")

| Piece | Reads | Learns from |
|---|---|---|
| Policy and value, in play and in every search | its own seat's view only (OWNER_PREFERENCES #1) | game results (+1/-1), and search targets computed on belief worlds |
| The search, at play and in training | worlds sampled from the simulator's beliefs, never the true hidden cards | — |
| The simulator | its own seat's view only | the true hidden cards, as labels (D20: supervised on finished games), released only after their game ends (§5.2) |
| The belief-regret yardstick (§5.4) | the true hidden cards: an omniscient mode for measurement only (OWNER_PREFERENCES #1) | nothing; it never plays or trains, and writes only its numbers |

What this plan does **not** do:
- **No policy or value target from a search on the true state.** It would teach the network to
  play as if it knew the opponent's hand.
- **No privileged critic.**
- **No opponents who see hidden cards.**
- **D20's true-future labels stay parked** (D21).

## 3. The search: one family, every setting kept

### 3.1 Today's search

`tools/selfplay/search.py`, before 2026-11-11:
- The network's top k options were tried (`Searcher.choose`). Each was tried in d worlds: copies of
  the game whose hidden cards are re-drawn uniformly from the pool (`draw_worlds`, `determinize`).
- The network plays both seats, each from its own view, to the start of the searcher's next turn
  (`simulate`), where the value head scores the position (`leaf_value`).
- Searched decisions: the act menu, whole attack plans and (opt-in) whole block plans.
- Any seat named `<version>+search` is a searcher (`actor.py`), so a searcher can already sit at a
  training game's table.

### 3.2 The settings

Every row is a flag. Each measured setting and its result goes into NUMBERS.md, so any setting can
be revisited (owner: "Save all of the search options").

| Setting | Values | Default |
|---|---|---|
| **root** (`--search-root`) | `topk`: top k by the network, each on the same d worlds; `gumbel`: Gumbel top-m, then sequential halving over n simulations [1] | `topk`, k 4, d 2 |
| **n** (`--search-n`), simulations per searched decision | 2 to 256 | 16 |
| **m** (`--search-m`), candidates at most | m = min(this, n, options) | 16 |
| **worlds** | `uniform` (built); `sim`: samples from the simulator's joint decoder, h + l decoder steps each (`simulator.py`), costed in the pilot; `sim-is`: the same, tilted toward consequential hands and weighted back (§5.3) | `uniform` |
| **continuation** (`--search-continuation`) | the policy plays both seats from their own views, `greedy` or `sampled` (each seat's draws seeded by the world, so every candidate of a world meets the same draws); later `tree`: the searcher's own later choices in one tree over its information sets (information-set MCTS [2]) | `greedy` |
| **horizon** (`--search-horizon`) | the start of the searcher's N-th next turn; 0 = the end of the game | 1 |
| **leaf** | the value head, or the result when the game ends inside the horizon | value |
| **searched asks** (`--search-kinds`, `--search-blocks`) | act, attack plan, block plan; priority (built 2026-11-11). Target asks happen inside an engine call, where a copy cannot be taken (DESIGN_PRIORITY §2.1); the network answers them inside each simulation | act, attack |
| **skip** (`--search-skip-p`) | search only where the network's top option is below p | 0.97 |

**Why the continuation is policy-only by default.** Inside one sampled world, a tree that chooses
the searcher's later moves knows that world's cards: strategy fusion (OWNER_VISION_LEARNING §10).
- The policy reads only its own view, so a policy continuation has no strategy fusion.
- An information-set tree avoids it differently: it shares one node across all worlds the
  searcher cannot tell apart. It keeps a second flaw, non-locality: what the opponent's earlier
  play revealed is not reflected in the worlds.
- `tree` is a setting to measure against the default, not the default.

**Gumbel at the root** [1]:
- Sample m candidates without replacement from the network's logits plus Gumbel noise. The noise
  is off in greedy (evaluation) play, which takes the top m.
- Split n simulations over ceil(log2 m) rounds. In each round every remaining candidate is played
  on the same worlds (common random numbers), and the better half survives.
- In play, take the survivor with the highest logit + σ(q), with the paper's constants: σ(q) =
  (50 + the most simulations any candidate had) x (q + 1) / 2 for q in [-1, 1].
- The training target (F1) is π' = softmax(logits + step x completed q). Unvisited options get a
  value estimate mixed from the value head and the visited ones.
  - The step is scaled by the standard error of the means, as `mmd_target` does: one standard
    error moves the log-odds by at most 0.5.
  - With the paper's fixed constants a target moves ~25 logits per unit of score, whether the
    difference is evidence or noise. That is r12's soft target again (20 per unit; 183 §13-16).
- It improves the policy whenever its value estimates are right, from n = 2 on. It replaces the
  k x d grid's equal effort on hopeless and close candidates.

### 3.3 The n-curve (pre-registered, before anything is trained on search)

- **Network**: r27's newest frozen version at the time, fixed for the whole curve.
- **Match**: the searcher against the same network raw, both greedy, head to head.
  - 300 fixed deals, each played twice with seats swapped; coherent M21 decks from the verified
    pool.
  - The score's standard error is about 0.011: a pair's mean has 0.15 of one game's variance
    (KNOWLEDGE 184 §26, 185).
- **Grid**:
  - n ∈ {2, 4, 8, 16, 32, 64}, with `gumbel` and the best available worlds (`sim` if the simulator
    passes E0 on the new game, else `uniform`);
  - at n = 16, one change at a time: `topk` instead of `gumbel`; `uniform` instead of `sim`;
    priority asks searched or not; horizon 1 or 2;
  - against the heuristic, at n = 0 and at the best n.
- **The read is a fit, not a knee read pointwise.**
  - Each doubling of n gains perhaps 0.01, under one standard error.
  - So strength is regressed on log2 n over all the points, and the slope and its interval are the
    result.
  - n = 128 runs only if that slope's lower bound is above 0 at 64.
- **Gate A's confirmation**: the n chosen for F1 is measured again on 300 fresh deals. The best of
  several n on one set of deals overstates: a true +0.03 would pass a +0.04 bar 20-25% of the time.
- **Reported per point**:
  - paired score and its Elo equivalent;
  - milliseconds per searched decision, p50, p90 and p99 (`search.ms_percentiles`);
  - searched decisions per game, by kind;
  - share of moves the search changes;
  - clear corrections (margin ≥ 0.1) per game.
- **Latency for the clock is measured apart.** The batched timing under 18 workers includes the
  queue. The clock (NORTH_STAR §1a) needs a single game's p99 on an idle machine, measured at the
  chosen n.
- **Cost**:
  - a pilot first measures the seconds per simulation;
  - a heuristic game asks 155 decisions of both seats, twice the old game's (DESIGN_PRIORITY
    §11), so simulations are about twice as long as the old ones;
  - the grid may need two windows of ~12 hours;
  - r27 pauses during a window ("one run at a time"), and its log records the pause.
- **What the owner chooses on these numbers**: n for training targets (F1), n for the searched
  anchor, and n for play under a clock.

## 4. Step 0: r27, the learner on the new game

- DESIGN_PRIORITY stage 5, as approved: outcome PPO from r26's network at update 1,000, its
  `priority` row grown from `cw`.
- Pre-registered in note 191 before launch, with r26's protocol (189 §9):
  - seed 27;
  - entropy bonus 0.004;
  - 139,264 decisions per update, which keeps r26's ~1,875 games per update.
- r27 is the learner of this plan, and its frozen versions are the networks the search amplifies.
- **Launch**: after r26's registered read at update 1,000 (about 18:00 on 2026-11-11), r26 stops
  and r27 starts.

### 4.1 Does another network size help? (owner, 2026-11-12)

The owner asked to watch how fast r27 improves at first, and to test network sizes for it.

**The first design, and why it was dropped (red team, 2026-11-12).**
- It grew u1000 to 16 layers and ran r27's command from it for 8 hours, against r27's first 8.
- The growth itself is sound. The new layers, with every output weight and bias zeroed, leave the
  network's outputs bitwise equal on 96 real decisions, in fp32, in the bf16 inference copy and
  under PPO's autocast.
- But the arm measures update count, not size:
  - PPO at r27's learning rate moves weights slowly. r26's attention and feed-forward output
    weights moved 1.2e-3 RMS by update 202 and 2.5e-3 by update 1,000, against trained weights of
    about 0.02.
  - New layers start at zero and would reach about 4% of a trained layer in 8 hours. Their inner
    weights see gradients near AdamW's eps.
  - The grown arm makes about half the updates per hour, which alone puts it 0.01-0.02 behind.
- Any outcome would have said nothing about size.

**The test instead: does a bigger network fit what r27 has to learn?** It takes one GPU window of
about 1.5 hours, pre-registered in a KNOWLEDGE note first.
- **Data:** about 1M decisions of r27's v0 playing itself on the new game, with each game's result
  and the behaviour probabilities. Every 25th game is held out.
- **Three networks from u1000.** Each is fine-tuned on the same data for the same steps with a
  supervised loss: the value to the result, the policy to the behaviour probabilities.
  - u1000 as it is: 8 layers.
  - u1000 grown to 16 layers. The new layers start as the identity; distinct random inner weights
    and zeroed outputs and biases.
  - u1000 with the feed-forward width doubled. The new units start as the identity (zeroed
    outgoing weights), and it adds no sequential depth.
- **Read:**
  - held-out value explained variance, by game phase. The value's accuracy limits the search: in
    PPO's audit it explained 5% of the outcome's variance early in a game, 28% mid-game and 88%
    late;
  - held-out policy NLL, against steps;
  - the peak memory of one training step at each size. 16 layers add about 16 GiB at r27's token
    budget;
  - the inference cost per decision.
- **What it means:**
  - If a bigger network fits the held-out value clearly better (the bar is set in the
    pre-registration, about +0.02 explained variance mid-game), capacity limits the value
    function. A run from that network is then pre-registered as r28. It is compared with r27 at
    matched update counts, and its gain is priced against the search's latency: twice the depth
    halves the n that fits a clock (search.py:321), and doubles F0/F1's costs.
  - If not, size is not the lever at this stage.

**r27's early speed** is read from its own logs and saved networks, without pausing it:
- its gates against v0 at updates 25, 50, 75 and 100 (paired over 1,000 deals, a standard error of
  about 0.006);
- `win.heuristic` per 10 updates;
- how far its weights move per update.

## 5. The simulator, trained at every level of the search (owner §5, §10, 2026-11-11)

### 5.1 On the new game

- The capture of E0 is repeated on the game with priority, from r27's start network against
  itself and the new heuristic: 40k games, about an hour.
- The simulator trains in about 2 hours.
- E0's gates are scored again: hand NLL at most the yardstick's overall and 5% lower mid-game,
  calibration error under 0.05.
- Until it passes, the search's worlds stay `uniform`.

### 5.2 Every level: truth lines, deferred until something reads them

**Where the simulator is asked:**
- The search samples worlds once per simulation, at the real position. So today the simulator is
  asked only at real positions, and real positions with their true hidden cards (both seats, every
  decision) are matched training data, and plentiful.
- Positions the real game never reached are asked about only once the network reads the
  simulator's belief at every decision (PLAN_LEARNING §8, ruling 6), and then at every decision of
  every simulated line.
- r27 and H1 do not have that input.

**The owner's deeper levels, made honest, when that input exists.** In a training game the engine
knows the truth:
- At a share of searched decisions, the lines the search explored are replayed from the real
  position without re-sampling: the candidate move, then the policy for both seats, to the horizon.
- At every decision along such a line, the simulator gets one example: the deciding seat's view,
  and the true hidden cards at that point.
- They are kept only if they lower the held-out NLL at the positions the belief input asks about:
  an A/B on E0's metrics.

**The release rule, for all simulator data, now:**
- A copy carries the real game's random stream (`fork.py`: the engine's randomness is
  sha256(master seed, operation count, tag)). So a truth line's later draws are the real game's
  future.
- So is every label of library contents.
- So no simulator data from a game is trained on before that game ends.
- Each game keeps one simulator snapshot from its deal to its end.
- A byte-identical test with a frozen simulator cannot see a leak through retrained weights; this
  rule closes it.

**Further guards:**
- truth lines' results are never read;
- the real game's decision is made before them, from belief worlds, and a guard test checks that
  every decision is byte-identical with truth lines on and off;
- fresh deals only (D20 guard d).

### 5.3 Consequence x probability

**The rule.** A probability weighted by consequence is no longer a probability.
- If the simulator's loss weighted each card by its danger, it would over-predict dangerous cards,
  and the search would fear them more than they cost.
- So consequence enters in two places where it changes the work done but not the probabilities.

**1. Where the simulator spends its capacity.**
- Each training position is weighted by how much the search's decision there depends on the hidden
  cards: how much the gap between the top two candidates varies across the sampled worlds.
- The weight is a function of the position, not of the answer, so the conditional probabilities
  stay calibrated. The training set's mix of positions changes, but not what the right answer is
  at any one of them.
- The weights come from the simulator's own samples, so they are floored, and calibration is
  reported per weight band.
- This borrows the "value-aware" idea of [7, 8]. There it replaces the likelihood; here it only
  reweights positions, so the likelihood stays.

**2. Which futures the search looks at** (`sim-is`; PLAN_LEARNING §8, approved):
- Every searched decision's worlds give data on consequence. In each world, the gap between the
  candidates' values against the hands in that world shows which cards decide the move.
- A small consequence head learns this per position and card.
- The hand decoder's sampling is tilted by it, and every world is weighted back by p/q:
  - the proposal's normaliser is known, so plain weights are used, not `mean_scores`'
    self-normalised ones, which are biased at a handful of worlds;
  - the estimate is unbiased with respect to the simulator's beliefs: sampling changes which worlds
    are looked at, not what they are worth;
  - errors in the beliefs themselves remain.
- Result: a 0.1% disaster is seen often enough to be weighed, and counts at 0.1% of the
  simulator's belief.
- Hands are sampled whole, so threats that share an answer add up (D20: 30% + 25% beats 45%).

### 5.4 The measure that matches the goal: belief regret

At a sample of searched decisions:
- the search runs twice on the same seeds: once on the simulator's worlds, once on the true
  hidden cards (the omniscient yardstick);
- belief regret is the win probability given up by the belief search's choice, valued by the
  omniscient search.

**Isolation.** The omniscient search runs in its own measurement process and writes only its
numbers. It never touches a snapshot, buffer or label.

It measures exactly "predicting the cards we care about". It is reported for the `uniform`, `sim`
and `sim-is` worlds. E0's NLL and calibration stay as the simulator's own gates.

### 5.5 Decks

- The simulator learns the decks it meets.
- Today's coherent decks are two colours with an even land split and uniform spells
  (`games.build_coherent_deck`): coherent in colour, random in everything else.
- Realistic decks change what is worth playing around, so they are a parallel item, not on this
  plan's critical path:
  - 17lands' public game data carries each game's deck (card counts), per the `spells` tool's
    documentation. The public datasets are under CC BY 4.0 unless noted: credit 17Lands, without
    implying its endorsement. The usage guidelines leave them out of their scope and discourage
    scraping the site's API. The game data starts at Kaldheim (2021): the M21 and M20 files are
    not available (HTTP 403, where KHM and DSK return 200), so it holds no decks of this game.
    All of this was read on 2026-11-12;
  - "decks with a shape" (DESIGN_PRIORITY §9);
  - the drafter (§9) is the long-term source.
- The held-out niche set (D14) shows how far beliefs carry to decks unlike the training decks.

## 6. The fast models

### 6.1 F0: the searcher

- F0 is a frozen network plus the search.
- It needs no training, gets stronger whenever its network does, and can sit at a training table
  today (`actor.py`).
- **Its price.** With s seconds per simulation and about 20 searched decisions per game, a game
  costs about 1 + 2.3n plain games. Measured on the old stack at n = 6: 24x (0.96 searched games/s
  in 183 §14, against 22-24 plain games/s in 183 §6).
- So as a training opponent it is affordable only at small n and in a small share of games (§7.1).
  Its main roles are the searched anchor and the play-time player.

### 6.2 F1: search-improved training (expert iteration), gated

**Gate A, from the n-curve.**
- The search at some n beats its own network head to head by at least +0.04 paired: about 28 Elo,
  3.5 standard errors.
- That n is confirmed on 300 fresh deals (§3.3).
- If not, F1 is not run.

**Gate B, the distillation probe, at a scale that can answer.**
- Its own generation: searched self-play at the chosen n until 300k full-search targets exist,
  about 15k games, roughly 12-15 machine-hours at n = 16. *Measured in window 1 (KNOWLEDGE 192
  §4): about 29,400 games and 22 machine-hours, because only act decisions are recorded,
  10.2 per game, and 600 searched games take 27 minutes.* E3 saw no growth from 100k to 300k, so
  less cannot answer the question.
- The network is trained on 100k and on 300k targets (SE-scaled steps, §3.2) and tested on unseen
  deals:
  - it must gain at least +0.015 over its original over 450 paired deals at 300k (E3's bar);
  - its agreement with the search on held-out positions must rise from 100k to 300k.
- The share of comparisons with no difference in result is reported against E3's 92%.
- If gate B fails, F1 is not run, and the difficult opponents are the learner's own versions plus
  searched anchors.
- *Pre-registered in KNOWLEDGE/2026-11-12/196 after a red team. It changes four things: the
  network is chosen by play among the trained epochs, not by held-out KL, which kept E3's network
  unchanged; the test is 1,000 paired deals; gate A is re-checked on the generator; a placebo
  arm controls for the fine-tuning itself. About 30 machine-hours.*

**What is the same and what differs from the three failures:**

| Earlier | Now |
|---|---|
| k x d grid, 6 simulations | Gumbel sequential halving at the n the curve chose, whose clear corrections per game are counted |
| soft targets with a fixed temperature (r12); in 92% of E3's comparisons both moves had the same result | the step scaled by the standard error of the means, so a comparison with no difference moves the target by nothing; graded leaf values and more worlds per comparison make fewer of them |
| ~1.6K clear labels per generation, then discarded | a replay buffer in RAM over generations (§6.3) |
| value head damaged by distillation; a separate value network did not lift the plateau (183 §10-13) | value trained only on game results at sampled positions; a separate network is a setting, not a fix |
| uniform worlds, five-colour piles for two-colour decks (`search.py`) | simulator worlds once E0 passes on the new game |
| the network failed to generalise the corrections (183 §15-16) | **not removed by construction**: gate B tests it at 300k targets on unseen deals |
| no check that the search was strong enough to learn from | gates A and B first |

### 6.3 The loop

**Self-play with search on both seats**, with KataGo's playout cap randomisation [3]:
- a quarter of decisions get the full n, and only those give policy targets;
- the rest get n/8, enough for play.

**Value targets.**
- Game results (gamma = 1) at about 10 sampled positions per game and seat. Positions of one game
  share a result and are near copies (183 §12).
- **Faster value learning, if it measures faster.** The owner: F1 may trade ceiling for speed, and
  a lower gamma or lambda is worth it only if it helps. Two settings, each kept only if the value
  head predicts held-out results better per machine-hour and the search gets stronger:
  - auxiliary heads that predict the search's own root value a few turns ahead, exponentially
    averaged. These are KataGo's short-term value targets [11]: by its author's partial test,
    slightly faster training and a slightly better main head. The main head keeps the game result;
  - a main target mixing the result with the search's value. This is a lower lambda by another
    name, and it lowers the ceiling.
- **The learner keeps gamma = lambda = 1.** For outcome PPO, lambda below 1 bought little: one
  useful update needed 2.2M decisions at 0.95, against a bound of at least 2.65M at 1 (D20). That
  is not worth the full credit, so r27, H1 and H2 keep gamma = lambda = 1.

**Simulator data**: every game, both seats, under §5.2's release rule.

**Replay buffer in RAM:**
- An encoded decision is at most ~16 KB: up to 112 card entities of 62 floats and 7 ids, plus the
  option rows (`features.py`).
- It lives in shared memory that the trainer reads directly. Today's batches reach the trainer
  through a pipe (`learner.py`, `ppo.py`), which cannot carry gigabytes.
- **Fixed replay ratio.** The trainer could consume ~1,200 decisions/s against 1-5 new targets/s.
  So each target is used a set number of times on average (a setting, 4-8), and the trainer waits
  rather than overfit.
- **Size by measurement.** During F1, r27 is paused, so F1's own workers, trainer and buffer must
  keep MemAvailable well above the 15 GiB floor that stopped r24. Start at 16 GB, about 1M
  decisions; measure, then grow.

**Training:**
- minibatches drawn from the buffer at the replay ratio;
- loss KL(π' ‖ π_θ) plus the value loss;
- weights published to the actors every few minutes.

**The 48-hour check.** After 48 machine-hours, F1's checkpoints are rated jointly with r27's on
the held-out pool (§7.2), mostly near-even games, about 8 Elo standard error. F1 goes on only if:
- it has gained at least +30 Elo, lower 95% bound above 0;
- its Elo per machine-hour exceeds r27's latest measured rate, lower 95% bound of the difference
  above 0.

Otherwise it is not a fast model, and it stops.

### 6.4 Train F1 high before the learner meets it (owner, 2026-11-11)

The owner: "shouldnt we train the F1 and F0 models to some high ELO? Like 1000 ELO and then start
training? If we just play it like it is but plus search, is that really good enough to test what we
want to find out?"

**No, it is not enough.**
- Today's network plus search added +0.045 to +0.060 against the heuristic (about 30-40 Elo),
  about one gate.
- Against it the learner would train much as in plain self-play.
- Passing it would say little about the learner's ceiling.
- The read needs opponents far above where the learner starts.

**So F1 trains first, and high:**
- After gates A and B, F1 gets the machine; r27 pauses.
- At 48 machine-hours comes the check of §6.3.
- Then F1 goes on while it climbs, rated daily in the joint fit.
  - Near-even games give about 8 Elo of standard error.
  - Lopsided ones give 11-19 Elo at a 0.85-0.95 score.
- It stops at its plateau: less than 25 Elo per machine-day over two days, with the upper 95% bound
  below 50. Or it stops at the owner's target. After 14 machine-days the owner reviews it either
  way.
- A checkpoint every ~50 Elo builds a ladder of opponents. Every fourth checkpoint is withheld
  from training and goes to the held-out pool (§7.2).

**The number.** Our Elo puts uniform random play at 0. On the old game:
- the heuristic is at 302, r26's v2 at 436, and its newest about 450-465;
- +100 Elo wins 64%, +200 wins 76%, +400 wins 91%;
- "1000" is about +535 over today's best, winning about 96%.

The plan takes 1000 as the direction, not a gate: F1 goes as high as it keeps climbing.
- **H1 starts when F1's best is at least +200 Elo above r27's newest**, lower 95% bound above
  +150. The learner then wins about a quarter of its games against the top.
- Below that the read is weak, and the owner decides.

**Why a ladder, not only the top.**
- With +1/-1 results, a learner that loses 95% of its games gets little signal.
- PFSP weighted x(1 - x) (§7.1) plays it mostly against checkpoints near its level, and the top
  comes up as it wins.

**If F1 stalls low**, as r5-r14 did after +0.07:
- the fast-model premise fails, and we know it within days;
- the strongest opponents are then the learner's own versions, plus searched anchors.

## 7. H1: the learner against difficult opponents (the ceiling probe)

### 7.1 The league

**Start: r27's newest network.** D8 (the owner's): inherit representations, not policy; keep the
small model in the opponent league, so the large one is rewarded for beating it, not imitating it.
- Starting from F1's network would make the ceiling read a read of F1 plus PPO.
- The owner's earlier "3." (a fading pull toward F1, kickstarting [4]) stays an option only under
  D8's gate: the student exceeds the teacher's Elo within a stated number of updates, or the run
  restarts without it.

**The opponent pool:**
- the learner's frozen versions;
- F1's ladder, raw: the cheap difficult opponents, and the main ones;
- searched opponents (F0), at most 3% of the learner's games, at the smallest n the curve shows
  still clearly stronger. At n = 16 one such game costs ~38 plain ones, so 3% of games already takes
  about half the collection time. This is a registered scaffold that goes when searched play is
  cheap;
- the heuristic, kept against forgetting.

**Who plays whom: prioritised fictitious self-play** (PFSP [5]; PLAN_LEARNING §5):
- 35% of games against the newest frozen version;
- the rest drawn from the pool in proportion to x(1 - x), x being the learner's recent win rate
  against that opponent;
- even matches carry the most signal per game for a +1/-1 learner;
- the hardest opponents take more weight as the learner nears them;
- (1 - x)², which favours the opponents it loses to, is a setting. As a default it would send a
  weak learner mostly into games it cannot win.

**The value baseline cannot see the opponent.** That adds variance, not bias. Advantages centred
per opponent are a setting.

**Learning stays on-policy.** The learner records only its own seat, with its own probabilities,
whoever the opponent is.

**The premise is tested, not assumed.** A control arm runs beside H1:
- the same learner from the same checkpoint, on r27's league (its own versions and the heuristic);
- the same machine time, about a week each;
- both rated on the held-out pool.

If H1 does not climb faster than the control, playing difficult opponents did not speed it up.

**Pre-registration.** H1 and its control are pre-registered runs (r28, r29).

### 7.2 The held-out pool and the learning score L (owner: "a very varied pool, weighted based on ELO")

**What it is.** A fixed, very varied pool of frozen opponents that never appears in any training
league:
- r26's v0-v2 and r23's network;
- every fourth F1 checkpoint;
- r27's v0 plus search at the anchor's n;
- later, specialists and exploiters;
- each with decks of every shape: coherent, the niche set (D14), and later real decklists and the
  drafter's.

**Ratings frozen.** The pool's ratings are fitted once (Bradley-Terry, `fit_elo`) and frozen. A
player is rated against those fixed ratings. A joint refit with a draw prior would move every
number whenever the pool grows.

**L, the learning score**, is a player's Elo against the frozen pool. An Elo weights each result by
the opponent's strength: a win against a strong opponent raises it far more than a win against a
weak one. That is the owner's "weighted based on ELO" without hand-set weights.

**It is the progress measure** of every run from F1 on, and of the ceiling read. The heuristic,
which is in the training leagues, is reported beside it, not in it.

### 7.3 The ceiling read

**When.** H1 runs until it plateaus:
- no gate passed in 300 updates;
- L rising by less than 10 per doubling of machine time over the last two doublings, upper 95%
  bound below 25.

Then it is read:

| Measured | If high | If low |
|---|---|---|
| **H1 against its control** (L per machine-hour) | difficult opponents speed the learner up: the premise holds | they do not; the plan's step 2 is not worth its machine time for the learner |
| **search headroom**: L of H1's newest plus search, minus H1's newest raw | the network cannot learn what its own search finds: the signal or the optimiser limits it. Next levers: search targets, larger batches, the belief input | the network's evaluation limits it: capacity, inputs (memory, deck knowledge, names), the value head |
| **exploiter score**: a learner started from r26's network, trained only against H1's newest for one machine-day (AlphaStar's main exploiter [5]); its score against H1 | H1 is exploitable: more league diversity, exploration, the magnet (PLAN_LEARNING §5) | robust at its level |
| **H1 against the fast models' held-out checkpoints** | the learner climbed past the fast models: its ceiling is genuinely higher | the fast models' biases cost less than the learner's noise at this compute |
| **per-kind entropy** (PH-9) | still exploring | collapsed: a reason to start H2 fresh |

Strength is read greedy (189 §9: greedy beats sampled). The read is a report to the owner. A
capacity probe (a 2x network, the same setup and budget) is added if the headroom row says
capacity.

## 8. H2: the ceiling-striving run (explorative self-play from the beginning)

**Starts after the ceiling read, by the owner's decision.** As designed now:
- **Fresh random weights.** No imitation and no warm start, so nothing early narrows what it can
  find (OWNER_VISION_LEARNING §9: primacy bias, loss of plasticity).
- **Exploration from the first update**: an entropy level per decision kind, not one global
  bonus, and fresh deals.
- **The league from the start**: random play, the heuristic, its own frozen versions, an exploiter,
  and the strong networks of r27, F1 and H1.
  - PFSP weighted x(1 - x) keeps the strong ones mostly out until it can win some games against
    them.
  - It plays them, never copies them, so they shape what it must beat, not how it plays.
- **Kept learning**: partial resets if it stalls (OWNER_VISION_LEARNING §9's remedies), and the
  magnet against cycling.
- **The same learner rules**: gamma = lambda = 1, +1/-1, no privileged critic, on-policy.
- **Decks chosen for learning**, if the Teacher has passed its gate (§9).

**A pilot first**, a 6-8 hour window before H2:
- from random weights against random play, the heuristic and its own versions;
- does outcome PPO learn this game from nothing, and how fast?
- The answer sets H2's cost.
- If it does not learn, H2 needs a different start, such as search from the beginning as AlphaZero
  did. That decision is the owner's.

## 9. Decks chosen for learning: the Teacher and the drafter (owner, 2026-11-11)

The owner: "Making the drafter, and training that for maximizing learning, would also be really
great (learning is probably winrate agains frozen opponents from a very varied pool, weighted based
on ELO)." The measure is §7.2's L.

### 9.1 The Teacher (a curator plus a critic, D15)

**Its job.** It chooses the training deals (both decks, and the opponent) so that L rises fastest
per machine-hour.

**Not inside H1.**
- It would compete with PFSP for the opponent choice and confound the ceiling read.
- It gets its own runs after the read.

**Its signal cannot be per-family Elo progress.**
- r26's late progress was 1-2 Elo per hour in all, far below one rating's 8-19 Elo standard error.
- So v0 uses Prioritized Level Replay's per-game scores [10]: the learnability p(1 - p) of a
  matchup and the learner's value error on its games, both available after every game.
- Families of decks (the generator's settings: colours, curve, land count, D16's niche knob)
  crossed with opponents are sampled by those scores, with a floor of uniform sampling so that
  nothing is forgotten.
- Teacher-Student Curriculum Learning [9] is the frame. No network.

**v1.** The critic of D15 predicts a matchup's result and its learning value.

**Its gate** is PLAN_LEARNING's Phase 3 bar: at least 1.3x the L per machine-day of uniform deals,
3 seeds per arm. That is six runs or more, costed in §10.

### 9.2 The drafter (NORTH_STAR §4a)

**Started 2026-11-12, at the owner's request:** `docs/PLAN_DRAFTER.md`, a v0 on today's 60-card
format (a deck critic fitted on the games already played, then construction on it). The rest of
this section is the long-term shape it grows into.

**What it is.** A generative policy that builds a deck pick by pick, with D16's two knobs
(nicheness, randomness). It is trained against the critic it shares with the Teacher (D15).

**Trained for learning**, as the owner asks: the Teacher asks it for decks in the families it
scores highest, and its fine-tuning reward is the rise of L its decks bring.

**What else its decks feed:**
- the held-out pool;
- the simulator, which needs coherent, realistic decks (§5.5);
- later the product's three modes.

### 9.3 Guards

- The Teacher picks families, not deals: every deal stays fresh, so nothing is memorised
  (OWNER_VISION_LEARNING §2; D20 guard d).
- The held-out pool and its deals never train.

## 10. Order and machine time

| When | Machine | My work |
|---|---|---|
| 2026-11-11 | r26 | built and tested the same day: the search family (§3.2: root, n, m, continuation, horizon, priority asks, simulator worlds, timing, target recording), `ncurve.py`, `distill.py`, `rate.py`; r27's pre-registration (note 191) |
| 2026-11-11 ~18:00 | r26's read at 1,000; r26 stops | — |
| window 1, the night of 2026-11-11 (before r27; KNOWLEDGE 192) | the n-curve pilot and points, gate A's confirmation, the simulator recaptured and trained, the n = 16 variants | — |
| then | r27 | report: the n-curve and the simulator; **the three n, chosen by the agent with its reasons (the owner, 2026-11-12: "no need for me in the loop")**: 16 for F1's targets, 4 for the searched anchor, 16 for play (KNOWLEDGE 192 §9, D23) |
| 2026-11-12 | r27 | its early speed (§4.1); the capacity probe and the drafter v0 (`PLAN_DRAFTER.md`) built and tested on CPU, beside r27 |
| a window of about 2.5 hours, r27 paused (the pause logged) | §4.1's capacity probe; drafted-deck games (PLAN_DRAFTER G2-G4) | — |
| days 3-5 | r27 to its read at update 500; then, gate A having passed, gate B's generation and probe (about 30 h with its controls, KNOWLEDGE 196, moved a day earlier in its §6; `reports/gate_b_2026-11-12/queue.sh`) | if gate B passes: the F1 loop (shared-memory buffer, replay ratio); PFSP |
| days 6-20 | F1, if gates A and B pass: the 48-hour check, then to its plateau or target (review at 14 machine-days) | the exploiter; the held-out pool's ratings |
| then ~2 weeks | H1 and its control, about a week each, from when F1 is at least +200 Elo above r27 | — |
| after H1 | — | **the ceiling read**, to the owner |
| after the read | the H2 pilot (6-8 h); the Teacher's runs (6 or more); then H2 | the Teacher v0; the drafter |

These are machine days, not promises: each window may move with what the previous one found.

## 11. Risks

1. **The search gains little at every n**, because the value head's accuracy limits it. F1 is then
   gated off, and the difficult opponents come from the league alone. The next levers are the
   value function and the simulator. The n-curve says this in a day or two, before anything is
   trained.
2. **F1 stalls again** for the reason r5-r14 did: the corrections do not generalise. Gate B is
   built to find this at 300k targets, before a long run.
3. **Searched opponents slow the learner.** About 1 + 2.3n plain games each. Hence the 3% cap,
   small n, and F1's raw networks as the main opponents.
4. **Learning to beat one opponent's quirks.** The held-out pool measures general strength, and
   PFSP spreads the games.
5. **A leak through retrained weights.** §5.2's release rule: no simulator data before its game
   ends, one snapshot per game.
6. **Beliefs fit our own decks.** §5.5, and the niche set.
7. **Memory.** The buffer starts at 16 GB and grows only by measurement against the 15 GiB floor.
8. **The clock.** Play-time n must fit a match clock, read from a single game's p99 on an idle
   machine.
9. **Noise read as a trend.** Fits over all points, confirmations on fresh deals, confidence bounds
   on every stopping rule.

## 12. Decisions

Approved as recommended on 2026-11-11 (DECISIONS D22). Items 3, 4, 5 and 9 were changed the same
day by the red team (§13), and the owner is told.

1. **The order**: r27 now; the n-curve first; F1 only through gates A and B; then H1 and its
   control; then the ceiling read; then H2.
2. **Distillation un-parked** (D21): F1 is search-improved training. D21 said "we will look at it
   closely at a later point"; gates A and B are that look.
3. **Searched opponents in training**: at most 3% of the learner's games, at small n. They serve
   mainly as anchors. *Was: half the collection time, which would have given them only 5-9% of the
   learner's decisions at ~50% throughput.*
4. **PFSP weighting**: x(1 - x) with 35% against the newest version; (1 - x)² a setting. *Was:
   (1 - x)², which contradicted the ladder's purpose and would have sent a weak learner into games
   it cannot win.*
5. **H1's start**: r27's newest network, with F1 in the league (D8). The fading pull toward F1 only
   under D8's gate. *Was: whichever is stronger, which always meant F1's network and would have
   made the ceiling read a read of F1.*
6. **H2 "from the beginning"** means fresh random weights, no imitation, no warm start.
7. **r26 stops** after its 1,000-update read and r27 starts (stage 5, approved 2026-11-10).
8. **F1's target** (§6.4): as high as it climbs, with a review at 14 machine-days. H1 starts once
   F1 is at least +200 Elo above r27's newest. Your "1000" (about +535 over today's best) is the
   direction.
9. **The learning score and decks** (§7.2, §9): L is a player's Elo against a held-out pool with
   frozen ratings. The Teacher runs after the ceiling read, scored by PLR-style per-game signals;
   the drafter follows. *Was: L's pool included training opponents, and the Teacher ran inside H1.*
10. **H1's control arm** (§7.1): about a week of machine time, to test the premise rather than
    assume it. New.

## 13. Red team (2026-11-11)

A fresh-eyes agent reviewed the approved text against the code, the history and the literature,
with 84 tool uses. Its findings were checked against the cited files before acting on them. Each
row: the finding, the verdict, and what changed.

| # | Finding | Verdict | Change |
|---|---|---|---|
| 1 | (1 - x)² contradicts "plays mostly near its level", and H2 from random weights would mostly play unwinnable games. Searched games cost ~1 + 2.3n plain games (24x measured at n = 6), so a cap by collection time gives them 5-9% of decisions at ~53% throughput | right | x(1 - x) by default; searched opponents at most 3% of games, at small n (§7.1) |
| 2 | "H1 starts when F1 is +200 above" plus "start from whichever is stronger" always picks F1's network: the high-ceiling run inherits F1's policy, which D8 gates | right | H1 starts from r27's network, F1 in the league, the pull only under D8's gate (§7.1) |
| 3 | The premise, that difficult opponents speed the learner up, is never tested | right | a control arm on r27's league, equal machine time (§7.1, §7.3) |
| 4 | §6.2 did not show why F1 would not stall. π' with the paper's constants is r12's soft target again (~25 against 20 logits per unit), the separate value network existed in r9-r14, labels were reproducible but did not generalise, E3 did not grow from 100k to 300k, and gate B's ~12k targets cannot answer | right | an honest table; SE-scaled target steps; gate B at 300k targets on unseen deals with its own generation (§3.2, §6.2) |
| 5 | Gate A picks the best of several n on one deal set (a true +0.03 passes 20-25%); a doubling's gain is under one SE; the 8 Elo SE holds only near 0.5 (11-19 at 0.85-0.95); the 48-hour check had no interval | right | a fresh-deal confirmation; a fit over log n; joint ratings near 0.5; bounds on every stopping rule (§3.3, §6.3, §6.4, §7.3) |
| 6 | Truth lines have no reader yet. A fork carries the real random stream, so if the simulator retrains inside a game's lifetime, its future draws can reach a snapshot the same game uses | right, and it holds for library labels too | truth lines deferred until the belief input exists; the release rule for all simulator data (§5.2) |
| 7 | L's pool included training opponents (Goodhart); per-family progress is below a rating's SE; three seeds per arm is six runs; a Teacher inside H1 confounds the read; `fit_elo` refits jointly | right | a held-out pool with frozen ratings; the Teacher after the read, on PLR-style per-game signals, its runs costed (§7.2, §9, §10) |
| 8 | 32 GB leaves ~16 GiB against the 15 GiB floor; batches reach the trainer through a pipe; no replay ratio | right | shared memory, a fixed replay ratio, a 16 GB start sized by measurement (§6.3) |
| 9 | "Fixed answers" applies to PPO too; play is read greedy; PPO has biases of its own; one row read H1 against its own training opponents; one anchor was also a training opponent | right | the ceiling argument made modest; the held-out pool (summary, §7.2, §7.3) |
| 10 | 155 decisions per heuristic game doubles simulation cost; `sim` worlds cost decoder steps; target asks cannot be forked; m(n) unset; a batched p99 is not deployment latency | right | the cost and m rows; target asks out; latency measured apart (§3.2, §3.3) |
| 11 | `mean_scores` self-normalises (biased at few worlds); "exact" only relative to the simulator's beliefs; position weights feed back; [7, 8] replace the likelihood | right | plain IS weights; the wording; floored weights with ECE per band (§5.3) |
| 12 | +0.045-0.060 was against the heuristic; the simulator's 18% is late, mid-game 12%; 2.65M is a lower bound; the exploiter's start and budget were unset | right | facts fixed; the exploiter starts from r26's network with one machine-day (§1, §6.3, §7.3) |

The red team found sound: §3.1's description of the code, the 0.011 standard error, the gates'
power, the Elo table, the decision size (16.3 KB or less), that no target is computed from the
true state, on-policy learning against any opponent, and the literature claims of [1]-[8] and
[11]. It noted that information-set MCTS keeps non-locality, now in §3.2.

## 14. After r27: realistic decks, signal before direction, and specialists (owner, 2026-11-12)

The owner, on window 2's results:
> "Training more realistic decks sound better though. Realistic decks probably have a higher
> skill cieling than random decks, so figuring out to do that is a path for our model to improve.
> If it only has simple one-turn or two-turn plans and plays, it can obviously never level up. If
> it starts to pick up on longer horizon or more complex combos (even if we 'cheat' and
> force/incentivize it) then we can make a frozen version of that, and iterate. We need to make
> sure it has some signal in the directions we move, or the gradient never goes there."

Also: the critic as the beginning of drafting; decks the model is especially weak against, for
later, "once it needs to learn how to balance niche and meta deck playing skills in the same
model"; and fix the backlog of cards.

### 14.1 Realistic decks move into the learner now, after one measurement

**Before, in §9:** decks chosen for learning came after the ceiling read, through the Teacher.

**The owner's case:** a deck that allows only one- or two-turn plans caps what can be learned.
Realistic decks (curves, the card pool's real cards, synergies) have a higher ceiling.

**The evidence so far cuts the other way for signal per game.**
- G4 (KNOWLEDGE/2026-11-12/193): between r27's update 165 and v0, the same pilot won both games
  of a deal in 0.294 of drafted (K = 8) deals, against 0.338 of coherent ones.
- Two readings:
  - drafted pairs are more lopsided: the critic's swaps widen the strength gap between the two
    decks, so the decks decide more games;
  - or today's networks have not learned what drafted decks reward.
- A balanced pair separates them.

**Step A, one measurement (a 15-minute pause of r28 after its R3 read at update 75).**
- A deck mode `balanced:K`: both decks drafted with K swaps, then the stronger deck's swaps
  undone one at a time, from the last, until the critic's predicted score of the pair is within
  0.5 ± 0.03.
- The share of deals whose winner is the pilot (G4's measure), with r28's network against its
  v0, on 1,000 deals of each:
  - coherent;
  - `drafted:8`, where both decks are drafted but the pair is not balanced;
  - `balanced:8`.
- Pre-registered in 199 before it runs.

**Step B, if `balanced:8` carries at least coherent's share (its 95% lower bound above
coherent's point estimate less 0.02).**
- r28 is amended at update 150, after R1-R3 are read: its training deals become half coherent and
  half `balanced:8`, registered in 199 before update 150.
- Its predictions:
  - the gates on coherent decks do not fall;
  - the mulligan stays (R1);
  - the flip share on `balanced:8` rises with training.
- If step A fails, realistic decks wait for the Teacher (§9), which picks deck families by their
  measured learning value.

**A known limit.** The v0 critic is linear in cards: it rates cards, not their interactions. So
drafted decks are good-stuff decks with better curves, not synergy decks. Synergy and combos need
the v1 critic (a set network, PLAN_DRAFTER §8) or archetype packages. That is §14.3's work.

### 14.2 Signal before direction

Before any push toward a skill (realistic decks, longer plans, combos), measure that the training
signal reaches it:
- the behaviour occurs in the learner's games;
- its advantage points toward it.

The template is 198 §2's measurement on the mulligan: the policy gradient per hand cell on
on-policy data (`reports/mulligan_runaway_2026-11-12/mulligan_signal.py`). It generalises to any
decision kind and cell. A push where the signal is absent or points away is not made until
something supplies the signal.

**For multi-turn plans, the signal is the search's.** It looks ahead and finds plays the policy
does not take. Distillation (F1) carries them into the network, and gate B (196, now on r28)
tests whether 300k such targets move it. The search's horizon is one turn. Horizon 2 is
re-measured after the fixes of 197 (192 §7.4's run was confounded by the replayed root plan),
before anything leans on it.

### 14.3 Forcing a skill, then freezing it: specialists

The owner allows forcing or incentivising a skill, then freezing it and iterating.
- **A specialist** trains with what the main learner never gets:
  - a shaped bonus for a synergy;
  - decks that win only through a combo or a long plan (archetype packages);
  - or search at every decision.
- **It is frozen and joins the league** (§7.1) as an opponent. Under D8's gate it can also be a
  fading pull (kickstarting).
- **The main learner keeps γ = λ = 1 and ±1.** It meets the forced skill as an opponent it must
  beat, and inherits representations, not the incentive.
- **Before a specialist is built,** §14.2's check runs on its target behaviour in its own games,
  so the incentive has something to move.

### 14.4 Later

- **Decks the model is weak against: the exploiter drafter.** The critic with its pilot term,
  refitted on the learner's games, rates decks by the learner's results with them and against
  them, and construction builds counter-learner decks. They join §7.1's exploiter and §7.2's
  held-out pool, after H1, when the learner must balance niche and meta play.
- **The critic as the start of drafting:** PLAN_DRAFTER §8 (the pick head, booster drafting).
- **The card backlog** (the owner: "fix the backlog of cards"):
  - the training sets' unverified cards: M21's 18 castable, M20's 11 mapped, 2 refused and 61
    waiting on atoms (KNOWLEDGE 177, BACKLOG);
  - the engine fixes in waves, then blind verification (PLAN_CARD_ONBOARDING);
  - a larger verified pool is what realistic decks are made of.

### 14.5 Order (machine)

| When | Machine | Work beside it |
|---|---|---|
| now | r28 to update 75 (R3, ~21:00) | card backlog wave 1 (three engine fixes); `balanced:K` built and tested |
| ~21:00 | r28 paused ~15 min: step A | — |
| to ~01:00 | r28 to 150 (R1) | step B registered if step A passes |
| to ~13:00 tomorrow | r28 to its read at 400 (from 151 half `balanced:8` if step B) | card verification; horizon 2's re-measure registered |
| then ~34 h | gate B on r28's network | — |
| after | F1 and H1 per §10, with specialists and later the exploiter drafter in H1's league | — |

## References

1. Danihelka, Guez, Schrittwieser, Silver. *Policy improvement by planning with Gumbel.* ICLR 2022.
2. Cowling, Powley, Whitehouse. *Information Set Monte Carlo Tree Search.* IEEE TCIAIG 4(2), 2012.
   On Magic itself: Cowling, Ward, Powley, *Ensemble Determinization in Monte Carlo Tree Search for
   the Imperfect Information Card Game Magic: The Gathering*, IEEE TCIAIG 4(4), 2012. On strategy
   fusion and non-locality: Frank and Basin, *Search in games with incomplete information*, AIJ
   1998.
3. Wu. *Accelerating Self-Play Learning in Go* (KataGo). arXiv:1902.10565, 2019.
4. Schmitt et al. *Kickstarting Deep Reinforcement Learning.* arXiv:1803.03835, 2018.
5. Vinyals et al. *Grandmaster level in StarCraft II using multi-agent reinforcement learning*
   (AlphaStar: PFSP, exploiters). Nature 2019.
6. Hu, Lerer, Brown, Foerster. *Learned Belief Search.* arXiv:2106.09086, 2021: a belief model
   trained by supervision on the true hidden information, sampled by the search.
7. Farahmand, Barreto, Nikovski. *Value-Aware Loss Function for Model-based Reinforcement
   Learning.* AISTATS 2017.
8. Grimm, Barreto, Singh, Silver. *The Value Equivalence Principle for Model-Based Reinforcement
   Learning.* NeurIPS 2020.
9. Matiisen, Oliver, Cohen, Schulman. *Teacher-Student Curriculum Learning.* arXiv:1707.00183,
   2017 (IEEE TNNLS 2019).
10. Jiang, Grefenstette, Rocktäschel. *Prioritized Level Replay.* ICML 2021. Regret-based
    generators: Dennis et al., *PAIRED*, NeurIPS 2020; Parker-Holder et al., *ACCEL*, ICML 2022.
11. Wu. *KataGo methods*, "Short-term Value and Score Targets"
    (github.com/lightvector/KataGo, docs/KataGoMethods.md): exponentially averaged future root
    values, mean horizons of about 6, 16 and 50 turns.
