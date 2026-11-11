# From fast opponents to the ceiling: search, the simulator and the league

**Status: draft for the owner, 2026-11-11 (Claude).** Nothing here is built until the owner
approves it. One exception: r27, DESIGN_PRIORITY's stage 5 (approved 2026-11-10), is step 0 of
this plan either way.

Builds on:
- OWNER_VISION_LEARNING §9-§11, the owner's words;
- PLAN_LEARNING §5 (the league) and §8 (the simulator);
- DECISIONS D20 and D21;
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
| **Searcher F0** | a frozen network (the learner's or F1's) plus search at play time | that network's, raised by its search | 5-20x a plain game, measured in step 1 |
| **Search-trained network F1** | expert iteration: the network is trained toward what its search chose | lower | cheap to play against, costly to train |
| **Simulator** | predicts the opponent's hidden cards from what a player can see | (serves the search) | — |

**Why F1's ceiling is lower and the learner's higher.**
- F1's targets are the search's choices, which inherit the value network's errors and the
  simulator's belief errors.
- A search that maximises against a model of its own play settles on fixed answers. A stronger
  opponent can read those. Magic rewards mixed play, such as holding a trick up only some of the
  time.
- Outcome PPO has none of these biases. It is slow because one game's result is a noisy signal
  spread over a hundred decisions.

**Steps and gates.**

| Step | What runs or is built | What decides | Machine time |
|---|---|---|---|
| 0 | **r27**: outcome PPO on the new game from r26's newest network | its pre-registration (stage 5) | continuous; paused only for measurement windows |
| 1 | the **search family**, every setting a flag; the simulator recaptured on the new game | **the n-curve**: strength against the number of simulations n | ~1 day of windows |
| 2 | the **simulator at every level of the search**: truth lines, consequence | E0 again on the new game; belief regret | inside step 1's and 3's windows |
| 3 | **F1, trained high first** (owner, 2026-11-11), only if step 1 shows the search well above its own network and a cheap distillation probe moves the network. A checkpoint every ~50 Elo builds the opponents' ladder | at 48 h: faster per machine-hour than r27, or stop. Then on to its plateau or the owner's target (§6.4) | days, up to 2 weeks |
| 4 | **H1**: the learner trains against F1's ladder and its searched versions; it starts only when F1's best is at least +200 Elo above the learner | the **ceiling read** (§7) | 1-2 weeks |
| 5 | **H2**: explorative self-play from the beginning | your call after the ceiling read | weeks |

**Three earlier attempts at training from search failed. The difference this time** (§6.2):
- the search's strength is measured against n first, so we no longer train on a weak search;
- a cheap probe shows whether the network can learn the search's corrections at all before any
  long run;
- Gumbel targets carry the value of every searched move, not only the winner;
- the replay buffer is in RAM, so labels pile up over many generations;
- if F1 still stalls, we know within days, before the learner is trained against it (§6.4).

**Your "consequence x probability"** (§5).
- The simulator's probabilities stay honest (calibrated).
- Consequence decides two things: where the simulator spends its capacity (the positions whose
  decision depends on the hidden cards), and which futures the search looks at (rare devastating
  hands sampled more often, then weighted down exactly).
- It learns from every branch the search explores. The probabilities learn from the true hidden
  cards at every level of the real game's possible lines. The consequence learns from the search's
  own per-world results.

**Decisions for you: §11.**

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
| "shouldnt we train the F1 and F0 models to some high ELO? Like 1000 ELO and then start training? If we just play it like it is but plus search, is that really good enough to test what we want to find out?" | §6.4 |
| "after which we can do the cieling-striving training run that is explorative self-play from the beginning" | §8 |
| "Only challenge is whether enemy deck is coherent, or completely random" | §5.5 |

## 1. Where we are (measured)

- **The learner learns.** r26 (outcome PPO, gamma = lambda = 1, 98k decisions per update) froze v1
  at update 202 and v2 at 378. v2 is 76 Elo above v0 and scores 0.684 against the old heuristic
  (KNOWLEDGE 2026-11-10/189 §10). Its gates against v2 since then:
  - 0.542 at 801, 0.524 at 827, 0.519 at 852, 0.508 at 877;
  - none passed (the gate needs 0.55).
- **Search at play time adds a little.** On the old game, the old network plus search (k = 3
  candidates, d = 2 worlds, one turn deep) beat its raw network by +0.045 to +0.060 (NUMBERS,
  2026-11-04). The gain shrank as the network improved (183 §28).
- **Training from search stalled three times:**
  - October, on the old stack: one-shot distillation and search labels were negative (NUMBERS
    2026-10-12, 2026-10-15).
  - r5-r14, November 4:
    - the raw network gained +0.07 over its start in two generations, then stopped;
    - the search corrected about one move per game clearly;
    - the network could not predict those corrections on new positions and learned the
      generating network's style instead (183 §16).
  - E3 (D21): one round of distillation of playout labels changed ~3% of choices and gained
    nothing in games.
- **The simulator works on hands.** Its NLL on hidden hands is 11% below a deck-aware yardstick's
  (18% by mid-game), with honest probabilities. On library contents it is no better than the
  prior (D21).
- **The new game.** r26's network transfers to the game with priority: 35/40 greedy and 30/40
  sampled against the new heuristic (NUMBERS, PRIORITY STAGES 1-4).

## 2. What each piece may know ("as little unrealistic knowledge as possible")

| Piece | Reads | Learns from |
|---|---|---|
| Policy and value, in play and in every search | its own seat's view only (OWNER_PREFERENCES #1) | game results (+1/-1), and search targets computed on belief worlds |
| The search, at play and in training | worlds sampled from the simulator's beliefs, never the true hidden cards | — |
| The simulator | its own seat's view only | the true hidden cards, as labels (D20: supervised on finished games) |
| The belief-regret yardstick (§5.4) | the true hidden cards: an omniscient mode for measurement only (OWNER_PREFERENCES #1) | nothing; it never plays or trains |

What this plan does **not** do:
- **No policy or value target from a search on the true state.** It would teach the network to
  play as if it knew the opponent's hand.
- **No privileged critic.**
- **No opponents who see hidden cards.**
- **D20's true-future labels stay parked** (D21).

## 3. The search: one family, every setting kept

### 3.1 Today's search

`tools/selfplay/search.py`:
- The network's top k options are tried (`Searcher.choose`, `search.py:211`). Each is tried in d
  worlds: copies of the game whose hidden cards are re-drawn uniformly from the pool
  (`draw_worlds`, `:206`; `determinize`, `:81`).
- The network plays both seats, each from its own view, to the start of the searcher's next turn
  (`simulate`, `:342`), where the value head scores the position (`leaf_value`, `:368`).
- Searched decisions: the act menu, whole attack plans and (opt-in) whole block plans.
- Any seat named `<version>+search` is a searcher (`actor.py:85`), so a searcher can already sit at
  a training game's table.

### 3.2 The settings

Every row is a flag. Each measured setting and its result goes into NUMBERS.md, so any setting can
be revisited (owner: "Save all of the search options").

| Setting | Values | Today |
|---|---|---|
| **root** | `topk`: top k by the network, each on the same d worlds; `gumbel`: Gumbel top-m, then sequential halving over n simulations [1] | `topk`, k 3, d 2 |
| **n**, simulations per searched decision | 2 to 256 | 6 |
| **worlds** | `uniform` (today); `sim`: samples from the simulator's joint decoder; `sim-is`: the same, tilted toward consequential hands and reweighted exactly (§5.3) | `uniform` |
| **continuation** | the policy plays both seats from their own views, `greedy` or `sampled`; `tree`: the searcher's own later choices in one tree over its information sets (information-set MCTS [2]) | `greedy` |
| **horizon** | the searcher's next turn (one turn cycle), two cycles, the end of the game | one cycle |
| **leaf** | the value head, or the result when the game ends inside the horizon | value |
| **searched asks** | act, attack plan, block plan (today); priority and target (new) | act, attack; block opt-in |
| **skip** | search only where the network's top option is below p | 0.99 |

**Why the continuation is policy-only by default.** Inside one sampled world, a tree that chooses
the searcher's later moves knows that world's cards: strategy fusion (OWNER_VISION_LEARNING §10).
- The policy reads only its own view, so a policy continuation has no strategy fusion.
- An information-set tree avoids it differently: it shares one node across all worlds the
  searcher cannot tell apart.
- `tree` is a setting to measure against the default, not the default.

**Gumbel at the root** [1]:
- Sample m candidates without replacement from the network's logits plus Gumbel noise. The noise
  is off in evaluation games, which take the top m.
- Split n simulations over log2(m) rounds. In each round every remaining candidate is played on the
  same worlds (common random numbers), and the better half survives.
- Play the survivor with the highest logit + σ(q).
- The training target is π' = softmax(logits + σ(completed q)): unvisited options get a value
  estimate mixed from the value head and the visited ones.
- It improves the policy whenever its value estimates are right, from n = 2 on. It replaces
  today's k x d grid, which spends equal effort on a hopeless candidate and a close one.

### 3.3 The n-curve (pre-registered, before anything is trained on search)

- **Network**: r27's newest frozen version at the time, fixed for the whole curve.
- **Match**: the searcher against the same network raw, greedy. 300 fixed deals, each played
  twice with seats swapped; coherent M21 decks from the verified pool. The score's standard error
  is about 0.011: a pair's mean has 0.15 of one game's variance (KNOWLEDGE 184 §26, 185).
- **Grid**:
  - n ∈ {2, 4, 8, 16, 32, 64}, with `gumbel` and the best available worlds (`sim` if the simulator
    passes E0 on the new game, else `uniform`);
  - at n = 16, one change at a time: `topk` instead of `gumbel`; `uniform` instead of `sim`;
    priority and target asks searched or not; horizon one cycle or two;
  - n = 128 on 150 deals, only if the curve still rises at 64;
  - against the heuristic, at n = 0 and at the two best n.
- **Reported per point**:
  - paired score against the raw network, and its Elo equivalent;
  - milliseconds per searched decision, p50 and p99 (the clock is a rank-1 goal; NORTH_STAR §1a);
  - searched decisions per game;
  - share of moves the search changes;
  - clear corrections (score margin ≥ 0.1) per game.
- **The read**:
  - where strength stops rising with log n;
  - what each doubling costs;
  - three choices of n, made by the owner on these numbers: n for opponents (F0), n for training
    targets (F1), and n for play under a clock.
- **Cost**: a pilot first measures the seconds per simulation. Estimate: about 0.15 s per
  simulation and 20 searched decisions per game, so 600 games at n = 64 take about 2 hours on 18
  workers, and the whole grid 8-12 hours. r27 pauses during the window ("one run at a time"), and
  its log records the pause.

## 4. Step 0: r27, the learner on the new game

- DESIGN_PRIORITY stage 5, as approved: outcome PPO from r26's newest network (`last.pt`), its
  `priority` row grown from `cw`.
- Changes from r26:
  - a fresh `--seed`;
  - main's code (the game with priority, the new heuristic as the anchor opponent);
  - a smaller entropy bonus, read per decision kind (189 §10: 0.0075 was too strong; PH-9).
- Pre-registered in its own note before launch, with r26's protocol (189 §9).
- r27 is the learner of this plan. Steps 1-3 build its difficult opponents while it runs, and its
  frozen versions are the networks the search amplifies.
- **Launch**: after r26's registered read at update 1,000 (about 18:00 today), r26 stops and r27
  starts. Stage 5 was approved on 2026-11-10 to follow once ready.

## 5. The simulator, trained at every level of the search (owner §5, §10, 2026-11-11)

### 5.1 On the new game

- The capture of E0 is repeated on the game with priority, from r27's start network against
  itself and the new heuristic: 40k games, about an hour.
- The simulator trains in about 2 hours.
- E0's gates are scored again: hand NLL at most the yardstick's overall and 5% lower mid-game,
  calibration error under 0.05.
- Until it passes, the search's worlds stay `uniform`.

### 5.2 Every level: truth lines

**Where the simulator is asked:**
- The search samples worlds once per simulation, at the real position, so today the simulator is
  asked only at real positions. Real positions with their true hidden cards (both seats, every
  decision) are therefore matched training data, and plentiful.
- Once the network reads the simulator's belief (PLAN_LEARNING §8, ruling 6), every decision of
  every simulated line asks it, including positions the real game never reached.

**The owner's deeper levels, made honest.** In a training game the engine knows the truth.
- At a share of searched decisions, the lines the search explored are replayed once from the real
  position without resampling: the candidate move, then the policy for both seats, to the horizon.
- At every decision along such a line, the simulator gets one example: the deciding seat's view,
  and the true hidden cards at that point.
- These truth lines are data for the simulator only:
  - their results are never read;
  - the real game's decision is made before them, from belief worlds;
  - a guard test checks that every decision of the real game is byte-identical with truth lines on
    and off (the same kind of test as `test_labels.py`'s).
- Fresh deals only (D20 guard d), so nothing about a deal can be memorised.

### 5.3 Consequence x probability

**The rule.** A probability weighted by consequence is no longer a probability.
- If the simulator's loss weighted each card by its danger, it would over-predict dangerous cards,
  and the search would fear them more than they cost.
- So consequence enters in two places where it changes the work done but not the probabilities.

**1. Where the simulator spends its capacity.**
- Each training position is weighted by how much the search's decision there depends on the hidden
  cards: how much the gap between the top two candidates varies across the sampled worlds.
- The weight is a function of the position, not of the answer, so the probabilities stay
  calibrated. The training set's mix of positions changes, but not what the right answer is at
  any one of them.
- The simulator gets better where it matters.
- This is the model-learning field's "value-aware" idea [7, 8], kept calibrated.

**2. Which futures the search looks at** (`sim-is`; PLAN_LEARNING §8, approved):
- Every searched decision's worlds give data on consequence. In each world, the gap between the
  candidates' values against the hands in that world shows which cards decide the move.
- A small consequence head learns this per position and card.
- The hand decoder's sampling is tilted by it, and every world is weighted back by p/q, so the
  estimate of each move's win probability stays exact.
- Result: a 0.1% disaster is seen often enough to be weighed, and counts at 0.1%.
- Hands are sampled whole, so threats that share an answer add up (D20: 30% + 25% beats 45%).

### 5.4 The measure that matches the goal: belief regret

At a sample of searched decisions:
- the search runs twice on the same seeds: once on the simulator's worlds, once on the true
  hidden cards (the omniscient yardstick);
- belief regret is the win probability given up by the belief search's choice, valued by the
  omniscient search.

It measures exactly "predicting the cards we care about". It is reported for the `uniform`, `sim`
and `sim-is` worlds. E0's NLL and calibration stay as the simulator's own gates.

### 5.5 Decks

- The simulator learns the decks it meets.
- Today's coherent decks are two colours with an even land split and uniform spells
  (`games.build_coherent_deck`): coherent in colour, random in everything else.
- Realistic decks change what is worth playing around, so they are a parallel item, not on this
  plan's critical path:
  - check 17lands' public data for the sets in the pool (M21, M20, ZNR, FDN) and its usage terms;
  - "decks with a shape" (DESIGN_PRIORITY §9);
  - the drafter (PLAN_LEARNING §9, phase 4) is the long-term source.
- The held-out niche set (D14) shows how far beliefs carry to decks unlike the training decks.

## 6. The fast models

### 6.1 F0: the searcher

- F0 is a frozen learner version plus the search at the opponent's n from the n-curve.
- It needs no training, gets stronger whenever the learner does, and can sit at a training table
  today (`actor.py:85`).
- Its price is the search's cost per game. That cost caps its share of the learner's games (§7.1).

### 6.2 F1: search-improved training (expert iteration), gated

**Gate A, from the n-curve.** At an n whose searched game costs at most 20x a plain game, the
search beats its own network by at least +0.04 paired (about 28 Elo, 3.5 standard errors). If not,
F1 is not run.

**Gate B, the distillation probe.**
- Material: the n-curve's full-search targets.
- The network is trained on 25%, 50% and 100% of them.
- It must gain at least +0.015 against its original over 450 paired deals at 100% (E3's bar), and
  its agreement with the search on held-out positions must rise with the amount of data.
- That second condition is the question r5-r14 left open: does generalisation grow with volume?
- If not, F1 is not run, and the difficult opponents are F0 and the league.

**What is different from the three failures:**

| Earlier | Now |
|---|---|
| k x d grid, 6 simulations, equal effort on hopeless candidates | Gumbel sequential halving at the n the curve chose |
| hard or prior-times-exp targets; half the changes were ties (183 §16) | π' from completed q: a tie moves the target by a tie's worth |
| ~1.6K clear labels per generation, 1-4 epochs, then discarded | a replay buffer in RAM over many generations (§6.3) |
| value head damaged by distillation (183 §10) | value trained only on game results at sampled positions (183 §12-13), its own head or network |
| uniform worlds, five-colour piles for two-colour decks (`search.py:21`) | simulator worlds |
| no check that the search was strong enough to learn from | gates A and B first |

### 6.3 The loop

- **Self-play with search on both seats**, with KataGo's playout cap randomisation [3]:
  - a quarter of decisions get the full n, and only those give policy targets;
  - the rest get n/8, enough for play.
- **Value targets**: game results (gamma = 1) at about 10 sampled positions per game and seat.
  Positions of one game share a result and are near copies (183 §12).
- **Simulator data**: every game, both seats, plus the truth lines of §5.2.
- **Replay buffer in RAM**:
  - An encoded decision is about 8-16 KB: up to 112 card entities of 62 floats and 7 ids, plus the
    option rows (`features.py:126-153`).
  - 2-4 million decisions fit in 32 GB, beside a run's ~35 GiB, inside the 15 GiB memory
    floor. A measurement sizes it.
- **Training**:
  - minibatches drawn uniformly from the buffer;
  - loss KL(π' ‖ π_θ) plus the value loss;
  - weights published to the actors every few minutes;
  - every generation scored on the anchors (§7.2).
- **The 48-hour check**: after 48 machine-hours, F1 must have gained at least as much anchor Elo
  per machine-hour as r27 over its latest comparable stretch. If it has not, it is not a fast model,
  and it stops. Otherwise it goes on (§6.4).

### 6.4 Train F1 high before the learner meets it (owner, 2026-11-11)

The owner: "shouldnt we train the F1 and F0 models to some high ELO? Like 1000 ELO and then start
training? If we just play it like it is but plus search, is that really good enough to test what we
want to find out?"

**No, it is not enough.**
- Today's network plus search won by +0.045 to +0.060 (about 30-40 Elo), about one gate.
- Against it the learner would train much as in plain self-play.
- Passing it would say little about the learner's ceiling.
- The read needs opponents far above where the learner starts.

**So F1 trains first, and high:**
- After gates A and B, F1 gets the machine; r27 pauses.
- At 48 machine-hours comes the check of §6.3.
- Then F1 goes on while it climbs, scored daily on the anchors: 300 paired deals, about 8 Elo of
  standard error.
- It stops at its plateau: less than 25 Elo per machine-day over two days. Or it stops at the
  owner's target. After 14 machine-days the owner reviews it either way.
- A checkpoint every ~50 Elo builds a ladder of opponents, and each checkpoint plus search sits
  above it.

**The number.** Our Elo puts uniform random play at 0. On the old game:
- the heuristic is at 302, r26's v2 at 436, and its newest about 450-465;
- +100 Elo wins 64%, +200 wins 76%, +400 wins 91%;
- "1000" is about +535 over today's best, winning about 96%.

The plan takes 1000 as the direction, not a gate: F1 goes as high as it keeps climbing.
- **H1 starts when F1's best is at least +200 Elo above the learner's start**, so the learner wins
  about a quarter of its games against the top.
- Below that the read is weak, and the owner decides.

**Why a ladder, not only the top.**
- With +1/-1 results, a learner that loses 95% of its games gets little signal.
- PFSP plays it mostly against checkpoints near its level, and the top comes up as it wins.

**If F1 stalls low**, as r5-r14 did after +0.07:
- the fast-model premise fails, and we know it within days;
- the strongest opponents are then the learner's own versions, plus search at high n as a measured
  anchor.

## 7. H1: the learner against difficult opponents (the ceiling probe)

### 7.1 The league

- **Start**: r27's newest network. Alternative: F1's network with a fading pull toward it
  (kickstarting [4]), the owner's "3." of 2026-11-11, whichever scores higher on the anchors. The
  pull is an arm only if F1 is the stronger one.
- **The opponent pool**:
  - the learner's frozen versions;
  - F0 (frozen versions plus search);
  - F1's ladder of checkpoints, raw and searched (§6.4);
  - the heuristic, kept against forgetting.
- **Who plays whom: prioritised fictitious self-play** (PFSP [5]; PLAN_LEARNING §5):
  - 35% of games against the newest frozen version;
  - the rest drawn from the pool in proportion to (1 - x)², x being the learner's recent win rate
    against that opponent, so the opponents it loses to come up most ("difficult");
  - x(1 - x), which favours even matches and so carries the most signal per game, is a setting.
- **The searchers' cap**: games against F0 may take at most half the collection time. This is a
  new scaffold, registered in BACKLOG; it goes when searched play is cheap enough or the n-curve
  shows a small n suffices.
- **Learning stays on-policy**: the learner learns only from its own moves, whoever the opponent is.
- **Pre-registration**: H1 is its own pre-registered run (r28 or later), because its league
  differs from r27's.

### 7.2 Anchors

A fixed ladder for this whole plan, never retrained:
- the new heuristic;
- r26's newest network (r27's v0);
- r27's v0 plus search at the opponent's n.

Every frozen version of every track (r27, F1, H1, H2) is placed on it. Paired deals, coherent and
the niche set (D14).

### 7.3 The ceiling read

H1 runs until it plateaus: no gate passed in 300 updates, and the anchor Elo rising by less than
10 per doubling of machine time over the last two doublings. Then it is read:

| Measured | If high | If low |
|---|---|---|
| **search headroom**: Elo of H1's newest plus search, minus H1's newest raw | the network cannot learn what its own search finds: the signal or the optimiser limits it; next levers are search targets, larger batches, the belief input | the network's evaluation limits it: capacity, inputs (memory, deck knowledge, names), the value head |
| **exploiter score**: a fresh learner trained only against H1 for a fixed budget (AlphaStar's main exploiter [5]) | H1 is exploitable: more league diversity, exploration, the magnet (PLAN_LEARNING §5) | robust at its level |
| **H1 against F0 and F1** | the learner climbed past the fast models: its ceiling is genuinely higher | the fast models' biases cost less than the learner's noise at this compute |
| **per-kind entropy** (PH-9) | still exploring | collapsed: a reason to start H2 fresh |

The read is a report to the owner. A capacity probe (a 2x network, the same setup and budget) is
added if the headroom row says capacity.

## 8. H2: the ceiling-striving run (explorative self-play from the beginning)

**Starts after the ceiling read, by the owner's decision.** As designed now:
- **Fresh random weights.** No imitation and no warm start, so nothing early narrows what it can
  find (OWNER_VISION_LEARNING §9: primacy bias, loss of plasticity).
- **Exploration from the first update**: an entropy level per decision kind, not one global
  bonus, and fresh deals.
- **The league from the start**: random play, the heuristic, its own frozen versions, an exploiter,
  and the strong networks of r27, F1 and H1.
  - PFSP keeps the strong ones mostly out until it can win some games against them.
  - It plays them, never copies them, so they shape what it must beat, not how it plays.
- **Kept learning**: partial resets if it stalls (§9's remedies), and the magnet against cycling.
- **The same learner rules**: gamma = lambda = 1, +1/-1, no privileged critic, on-policy.

**A pilot first**, a 6-8 hour window during H1:
- from random weights against random play, the heuristic and its own versions;
- does outcome PPO learn this game from nothing, and how fast?
- The answer sets H2's cost.
- If it does not learn, H2 needs a different start, such as search from the beginning as AlphaZero
  did. That decision is the owner's.

## 9. Order and machine time

| When | Machine | My work |
|---|---|---|
| today ~18:00 | r26's read at 1,000; r26 stops; r27 starts | r27's pre-registration (before 18:00) |
| days 1-3 | r27 | the search family (§3.2), the n-curve harness, simulator capture on the new game, truth lines, tests |
| window 1 (~12 h, r27 paused) | simulator capture and training; the n-curve | — |
| — | r27 | report: the n-curve and E0 on the new game; **the owner chooses the three n** |
| days 4-6 | r27; then F1's gate B probe (~4 h) | the F1 loop, the RAM buffer, PFSP, the consequence head |
| days 6-20 | F1, if gates A and B pass: the 48-hour check, then to its plateau or target (at most 14 machine-days before a review) | PFSP, the exploiter |
| then 1-2 weeks | H1, from when F1 is at least +200 Elo above the learner | H2's pilot window |
| after H1 | — | **the ceiling read**, to the owner |
| after | H2 | — |

These are machine days, not promises: each window may move with what the previous one found.

## 10. Risks

1. **The search gains little at every n**, because the value head's accuracy limits it. Then F0 is
   barely harder than the learner and F1 is gated off. The difficult opponents come from the
   league alone, and the next levers are the value function and the simulator. The n-curve says
   this in a day, before anything is trained.
2. **Searched opponents slow the learner.** Each searched game costs 5-20x. Mitigations: the cap
   (§7.1), Gumbel at small n, F1's cheap networks.
3. **Learning to beat one opponent's quirks.** The anchors and the niche set measure general
   strength, and PFSP spreads the games.
4. **A truth line leaks into a decision.** The byte-identical guard test (§5.2).
5. **Beliefs fit our own decks.** §5.5, and the niche set.
6. **Memory.** The buffer is sized by measurement against the 15 GiB floor.
7. **The clock.** Play-time n must fit a match clock. The n-curve's p99 is the input.
8. **Many comparisons in the n-curve.** The grid is pre-registered and every point reported.

## 11. Decisions for the owner

1. **The order**: r27 now; the n-curve first; F1 only through gates A and B; then H1; then the
   ceiling read; then H2. Recommended.
2. **Distillation un-parked** (D21): F1 is search-improved training. D21 said "we will look at it
   closely at a later point"; gates A and B are that look.
3. **The searchers' cap**: at most half the learner's collection time in games against F0.
   Recommended as a registered scaffold.
4. **PFSP weighting**: (1 - x)² ("difficult") with 35% against the newest version. Recommended,
   with x(1 - x) kept as a setting.
5. **H1's start**: whichever of r27's newest and F1's network is stronger on the anchors, with the
   fading pull only if it is F1's. Recommended.
6. **H2 "from the beginning"** means fresh random weights, no imitation, no warm start. Confirm.
7. **r26 stops** after its 1,000-update read and r27 starts (approved as stage 5 on 2026-11-10).
   Going ahead unless you say otherwise.
8. **F1's target** (§6.4): as high as it climbs, with a review at 14 machine-days. H1 starts once
   F1 is at least +200 Elo above the learner's start. Your "1000" (about +535 over today's best)
   is the direction.

## References

1. Danihelka, Guez, Schrittwieser, Silver. *Policy improvement by planning with Gumbel.* ICLR 2022.
2. Cowling, Powley, Whitehouse. *Information Set Monte Carlo Tree Search.* IEEE TCIAIG 4(2), 2012.
   On Magic itself: Cowling, Ward, Powley, *Ensemble Determinization in Monte Carlo Tree Search for
   the Imperfect Information Card Game Magic: The Gathering*, IEEE TCIAIG 4(4), 2012. On strategy
   fusion: Frank and Basin, *Search in games with incomplete information*, AIJ 1998.
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
