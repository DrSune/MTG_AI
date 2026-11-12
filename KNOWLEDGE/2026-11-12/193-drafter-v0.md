# 193 — The drafter v0: the deck critic and drafted decks (pre-registration)

**Context.** `docs/PLAN_DRAFTER.md`, written and red-teamed on 2026-11-12 at the owner's request
("getting started on the drafter based on value function and opponent simulator"). This note
records what was measured while building it (§1, exploratory), then registers the gates before any
new-game critic is fitted or any drafted-deck game is played (§2). Results are appended below and
never edit §2.

## 1. Built, and measured on the way (2026-11-12 night; exploratory)

**Built:**
- `tools/selfplay/decks.py`: `rebuild`, `check-capture`, `fit`, `swap`, `drafted_decks`.
- `learner.py` writes every training game's deal and result to `train_rows.jsonl`. r27 has this
  from its launch commit d6dcdff.
- Evaluation deck modes `versus:K` and `drafted:K` (`--eval-decks`, `--draft-critic`). The mode
  names the critic's hash.

**The rebuild:**
- Window 1's 300 deals, rebuilt at e462628 by the worker on that commit's extracted engine, equal a
  direct deal of the same seeds, deck for deck, all legal.
- r26's 40,500 deals were rebuilt at 4409527.
- The capture check (every captured position's opponent hidden plus public cards against the
  rebuilt deck, all 40 shards) is running; its result goes in §3.

**G1 on the old game** (r26's coherent games between networks, 40,911 games, 20,244 deals; the red
team had fitted it first, so this is not a test):

| Model | Held-out log-loss | Penalty | Calibration error (expected / largest bin) |
|---|---|---|---|
| Baseline: colour pair, seat, pilots, 12 deck summaries | 0.6792 | 0.001 | 0.0097 / 0.028 |
| Card values | 0.6720 | 0.01 | 0.0068 / 0.031 |

- The gain is 0.0072 ± 0.0009 per game.
- The top cards are Baneslayer Angel, Terror of the Peaks and Elder Gargaroth. The bottom ones are
  Heroic Intervention, Return to Nature and Tormod's Crypt.
- The critic's band for M21 (coherent decks, 1st-99th percentile): mean spell mana value 2.56-4.08,
  13-28 creatures, at most 4 copies.

**Construction on that critic** (1,000 M21 deals each):

| k | Distinct decks | Spells in at least 1% of decks | Predicted gain (logits) | Mean spell mana value | Creatures | Decks with a 4-of |
|---|---|---|---|---|---|---|
| 0 | 1,000 | 237 | 0.00 | 3.26 | 20.7 | 5% |
| 4 | 1,000 | 229 | +0.82 | 3.56 | 24.3 | 98% |
| 8 | 1,000 | 212 | +1.38 | 3.76 | 26.4 | 99% |
| 16 | 1,000 | 172 | +2.09 | 3.95 | 27.3 | 99% |

**One change from the plan.**
- PLAN_DRAFTER §4 fits the new game as a penalised deviation from r26's values. With r27's training
  games logged (about 1,600 coherent games between networks per update), the new game has tens of
  thousands of games within hours.
- So it is fitted alone, and r26's values are reported beside it.

## 2. Pre-registered (2026-11-12, before any new-game fit or drafted game)

**The critic.**
- Data: `decks fit` on r27's `train_rows.jsonl`. These are coherent games between networks: the
  learner against frozen versions, with the heuristic's games left out (`decks.games`).
- The decks are rebuilt at d6dcdff.
- The penalty grid is 1e-4, 1e-3, 3e-3, 1e-2, 3e-2 and 1e-1.
- It is fitted once r27 has 50,000 such games, about 30 updates.
- The G2 and G4 runs use this critic, named by its hash.

| # | Gate | Pass | Prediction |
|---|---|---|---|
| G1 | New game: held-out log-loss, 5 folds grouped by seed, cards against the baseline | the gain per game with its 95% lower bound above 0, and the cards' calibration error below 0.02 | gain 0.004-0.010 |
| G2 | `versus:K` for K = 0, 4, 8, 16: 1,000 deals each, M21, r27's latest network on both seats (`--eval-seat eval --eval-opponents snap:opp --opp-ckpt` the same file), greedy. The drafted deck's score, paired by deal | the slope of observed on predicted score has its 95% lower bound above 0 (regressed per deal over the four arms), **and** K = 8's score has its lower bound above 0.5 | K = 0: 0.47-0.53; K = 4: 0.55-0.65; K = 8: 0.58-0.70; K = 16: 0.60-0.75. Slope 0.3-1.0: the critic overstates its gains, because the swaps select its noise |
| G3 | 1,000 decks per K from the new-game critic, no games | at every K: 990 or more distinct, 150 or more spells in at least 1% of decks, every deck's statistics inside the band unless its deal started outside | met at K up to 16 |
| G4 | `drafted:8` against coherent: 1,000 deals each, r27's latest network against its v0, pilots swapped within a deal. The share of deals whose winner changes when the pilots swap | 10,000 or more drafted-deck games over G2 and G4 without an engine error. The share is reported for both | drafted within ±5 points of coherent. Neither direction is predicted with confidence: stronger decks can make a game more the deck's or more the pilot's |

**What each outcome means:**
- G1 fails: the cards add nothing over the summaries on the new game, and construction stays at
  K = 0.
- G2 fails on the slope: the critic's values do not carry to play, and the loop (§6) cannot start
  on them. It fails at K = 8 alone: the values carry but are too small to matter at that dose.
- G3 fails: construction collapses, and its guard needs work before any use.
- G4 is the purpose. A drafted share 3 points or more above coherent, with its lower bound above
  0, means drafted decks give more skill-decided games: the knob may help a stalled run.
  Otherwise the knob's value is realism (the simulator, the held-out pool), not signal.

**Deferred:** the simulator's NLL on drafted-deck positions needs a capture with drafted decks,
which `--capture` does not deal yet. It comes with the first loop round.

**Cost.** G2 is 8,000 games and G4 4,000, at about 15 games a second: under 20 minutes of a GPU
window.

## 3. Results

**The capture check** (§1's last item; exploratory). It finished 2026-11-12 02:36 and passed.
- It compared window 1's capture, all 40 shards: 2,291,252 positions from 40,000 games.
- At every position, the opponent's hidden cards (true hand and library) plus its public cards
  must equal the deck rebuilt from the game's seed at e462628 (`decks._check_capture_here`,
  `tools/selfplay/decks.py:118`).
- 0 mismatches. The rebuilt decks are the decks those games were played with, so a critic or a
  simulator can be fitted on rebuilt decks without storing them.
- It took 123 minutes on one core at nice 19, beside window 1's N3 to N4 steps.

**G1, the new game (2026-11-12 05:22, at r27's update 28): passed.**
- Data: r27's `train_rows.jsonl` as it stood, 61,140 games from updates 1-29, copied to
  `runs/window2/r27_train_rows_g1.jsonl`.
  - 52,036 of them were between networks, and 52,000 of those were decided.
  - The decks were rebuilt at d6dcdff (`runs/window2/r27_decks_g1.npz`; 61,140 deals, 462 cards).

| Model | Held-out log-loss | Penalty | Calibration error (expected / largest bin) |
|---|---|---|---|
| Baseline: colour pair, seat, pilots, 12 deck summaries | 0.67929 | 0.003 | 0.0066 / 0.020 |
| Card values | 0.66933 | 0.003 | 0.0081 / 0.016 |

- The gain is **0.00996 ± 0.00074** per game, 95% lower bound 0.0085, above 0. The cards'
  calibration error is 0.0081, below 0.02. The prediction was 0.004-0.010: met, at its top.
- **The critic** is `runs/window2/critic_r27.json` (content hash 6b8014ae; the file's sha256
  4e2e18ce…).
- The card values correlate 0.76 with r26's on the old game (rank 0.74, 242 shared cards).
- The top cards are Baneslayer Angel, Elder Gargaroth, Rotting Regisaur, Terror of the Peaks and
  Massacre Wurm. The bottom ones are Riddleform, Masked Blackguard, Retributive Wand, Spectral
  Sailor and Idol of Endurance.
  - The values say how these pilots win with a card, not how good it is. Spectral Sailor's flash
    and its draw ability are play the network may not have learned yet.
- Seat 0's edge (on the play) is +0.024 logits.

**G3 (2026-11-12 05:24): passed.** The decks are 1,000 per K, seat 0's dealt deck of the M21
deals 900,000-900,999 (G2's), after K swaps (`decks.drafted_decks`, scratch `drafter_g3.py`):

| K | Distinct decks | Spells in at least 1% of decks | Decks outside the band (all started outside) | Predicted gain over the dealt deck |
|---|---|---|---|---|
| 0 | 1,000 | 237 | 29 | 0 |
| 4 | 1,000 | 228 | 7 | +1.00 logits |
| 8 | 1,000 | 210 | 7 | +1.64 |
| 16 | 1,000 | 170 | 7 | +2.45 |

- The new critic predicts gains about 20% larger than r26's did (+0.82 / +1.38 / +2.09, §1).
- G2 tests whether they are real: its predictions (K = 8: 0.58-0.70) expect the critic to
  overstate them.

**G2 (window 2, 2026-11-12 14:57-15:05): passed.**
- r27's network at update 165 (`runs/window2/r27_latest.pt`, copied at the pause) played both
  seats, greedy, on the M21 deals 900,000-900,999 with the critic 6b8014ae. The table gives the
  drafted deck's score per deal (both games) and the critic's prediction for it (the seat edge
  included, the pilots cancelling):

| K | Score | 95% | Predicted | Prediction |
|---|---|---|---|---|
| 0 | 0.480 | [0.457, 0.502] | 0.498 | 0.47-0.53: met |
| 4 | 0.690 | [0.669, 0.712] | 0.719 | 0.55-0.65: above |
| 8 | 0.747 | [0.727, 0.766] | 0.824 | 0.58-0.70: above |
| 16 | 0.803 | [0.785, 0.820] | 0.909 | 0.60-0.75: above |

- The slope of observed on predicted score, per deal over the four arms, is **0.833, 95%
  [0.776, 0.891]** (bootstrap over the 1,000 deals). Its lower bound is above 0 and K = 8's lower
  bound is above 0.5, so G2 passes. The slope's prediction (0.3-1.0) is met.
- The per-K predictions are falsified upward at K = 4, 8 and 16. 83% of a predicted gain shows up
  in play: the swaps select the critic's noise less than I assumed.
- 0 engine errors in 8,000 games.

**G4 (window 2, 2026-11-12 15:05-15:09): the pass condition is met, and drafted decks give fewer
deals that the pilots decide, not more.**
- r27's network at update 165 played its v0 on the deals 900,000-900,999 (M21, greedy), with the
  pilots swapping seats within a deal.

| Decks | Decided deals | Same pilot won both games (the winning seat changed) | Update 165's score against v0 |
|---|---|---|---|
| `drafted:8` | 998 | 0.294 ± 0.014 | 0.525 [0.508, 0.542] |
| coherent | 999 | 0.338 ± 0.015 | 0.535 [0.517, 0.553] |

- Drafted minus coherent is **−0.045 ± 0.021, 95% [−0.086, −0.004]**, the runs taken as
  independent, as registered. Paired by deal (exploratory) it is −0.046 ± 0.021 over 997 deals.
- The prediction (within ±5 points) is met, at its edge. The share fell: with drafted decks a
  deal is more the decks' and less the pilots'.
- By §2's reading the share is not 3 points above coherent with its lower bound above 0, so the
  knob's value is realism (the simulator, the held-out pool), not learning signal.
- **Engine errors: 0 in the 10,000 drafted-deck games over G2 and G4**, as registered. That count
  includes K = 0's 2,000 games, which deal through the drafted path; the 8,000 games with at
  least 4 swaps alone also had none.
- Not done: the simulator's NLL on drafted-deck positions (deferred in §2).

**What 193 says.**
- The critic's values are real. A deck it rates higher wins more, at 83% of the predicted size,
  so PLAN_DRAFTER §6's loop can start on them.
- At K = 8 the drafted decks make games less skill-decided, not more. So this read does not
  support using the drafter as a knob for a stalled run. It stays a tool for realistic decks,
  for the simulator and the held-out pool, and for deck strength as a variable.
- The gap in the coherent share (0.338 here, 23% on r26's gates, PLAN_DRAFTER §7) is a different
  pilot pair: update 165 against v0.
