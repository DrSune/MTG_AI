# 192 — Window 1: the simulator on the new game and the n-curve (pre-registration)

**Context.** `docs/PLAN_CEILING.md` step 1 (§3.3, §5.1). Written before any of these games or
trainings, at the commit that holds it. Results are appended below and never edit this section.

**Machine.** The window runs after r26 stops at its registered read (update 1,000), and before r27
starts. Nothing else is on the GPU. The network is r26's network at update 1,000
(`runs/selfplay/r26_outcome_ppo/u1000.pt`, r27's v0), loaded as r27 will load it: `--refresh-table
--extend-sets M20`. Every run uses the verified pool on M21 coherent decks.

## 1. The simulator on the game with priority

**Capture.** E0's design, on the new game:
- 40,000 games: half the network against itself, half against the new heuristic, seats at random;
- coherent decks, M20 in 25% of games, each seat recording 40% of its real decisions;
- fresh seeds (capture seed 27).

`learner.py --capture 40000 --capture-p 0.4 --coherent-share 1.0 --mix-sets M20 --mix-share 0.25`
(with the init's flags; 18 workers).

**Training.** `simulator train` with E0's settings: d 256, 4 layers, 4 epochs, lr 3e-4, every 25th
game held out.

**Scored, on the held-out positions:**

| # | Measure | Prediction | Falsifier |
|---|---|---|---|
| S1 | Hand NLL against the uniform pool prior (what the search's `uniform` worlds assume) | ratio 0.55-0.80. E0's simulator was 0.889 of a deck-aware yardstick, which itself far beats uniform | above 0.90: the simulator does not beat what it replaces |
| S2 | Calibration: ECE of the marginal head's P(card in hand), 15 equal-mass bins | under 0.01 (E0: 0.0004) | 0.05 or more |

The deck-aware yardstick of E0 was removed after E0 passed (186 §4), so it is not re-scored. The
decisive test of the simulator for the search is point N5 below: simulator worlds against uniform
worlds at the same n.

## 2. The n-curve

**The match.** The searcher (`--eval-seat eval+search`) against the same network raw
(`--eval-opponents snap:opp --opp-ckpt` the same file), both greedy.
- 300 deals (seeds 900,000+), each played twice with the seats swapped.
- `--search-root gumbel`, `--search-m 16`, act decisions and attack plans searched, horizon 1,
  uniform worlds, greedy continuation, skip at 0.97 unless named.
- Every run records its targets (`--search-record`).

**Points:**
- N1, the grid: n = 2, 4, 8, 16, 32, 64.
- N2: n = 16 with `--search-root topk --search-k 4 --search-d 4` (16 simulations).
- N3: n = 16 with `--search-kinds act,priority`.
- N4: n = 16 with `--search-horizon 2`.
- N5: n = 16 with `--search-worlds sim` and the simulator of §1, if S1 and S2 pass.
- N6: against the heuristic, raw (n = 0) and at n = 16.
- **Gate A's confirmation:** n = 16, 300 fresh deals (`--eval-seed0 950000`).
- A pilot first (n = 4 and n = 16, 50 deals each) measures the time per game, and sets which of
  these fit the window. Points left out run in a later window.

**Predictions** (score = the searcher's paired score against the raw network; the standard error
of a point is about 0.011):

| # | Measure | Prediction | Falsifier |
|---|---|---|---|
| P1 | Slope of score on log2 n over N1 | +0.005 to +0.02 per doubling | 95% upper bound below +0.005: the search does not scale with n here |
| P2 | Score at n = 16 | 0.54-0.59 (+0.04 to +0.09). The old search at 6 simulations raised the score against the heuristic by +0.045-0.060 | below 0.52 |
| P3 | Gate A: n = 16 on fresh deals | +0.04 or more: passes | below +0.04: F1 does not run (PLAN_CEILING §6.2) |
| P4 | N2: gumbel minus topk at 16 simulations | -0.01 to +0.03 | below -0.02: halving loses to the plain grid here |
| P5 | N3: act and priority minus act only | 0.00 to +0.02, at about twice the searched decisions | below -0.01 |
| P6 | N4: horizon 2 minus horizon 1 | -0.01 to +0.03, at about twice the time | — (cost-benefit only) |
| P7 | N5: simulator worlds minus uniform | 0.00 to +0.03 | below -0.01: beliefs hurt the search (calibration, or a bug) |
| P8 | Clear corrections (margin 0.1 or more) per game at n = 16 | 0.5-3 (r12 at 6 simulations: about 1) | — |
| P9 | Share of recorded comparisons with no difference in result at n = 16 | 0.30-0.70 (E3's true-future playouts to the end: 0.92; the value leaf grades a result) | above 0.85 |
| P10 | A searched decision's time at n = 16, p50 under the window's load | 1-5 s | — (the clock's latency is measured apart) |
| P11 | Simulation errors | 0 | any: a bug to fix before reading anything |

**What each outcome means:**
- P1 and P3 met: gate A passes, and gate B's generation follows at n = 16 (~15 h, 300k targets).
- P3 falsified: F1 does not run. The difficult opponents come from the learner's own league, and the
  levers are the value function (its accuracy limits the search) and the simulator.
- P7 met: simulator worlds become the default for the search and for gate B's generation.

## 3. Before the points: the pilot, one fix, one correction (2026-11-11, 18:03-18:40)

**The pilot** (`reports/window1_2026-11-11/queue.sh` with `PILOT=1`, network `u1000.pt`, deals
900,000-900,049; nothing else on the GPU):

| | n = 4 | n = 16 |
|---|---|---|
| Score against the raw network (50 deals) | 0.62 (SE 0.031) | 0.60 (SE 0.032) |
| Wall time, 100 games | 297 s | 922 s |
| Searched decisions per game | 11.8 (act 9.3, attack plans 2.5) | 11.9 |
| Changed by the search | 17% | 19% |
| Clear corrections per game | 0.70 | 0.67 |
| Time per searched decision, p50 / p90 | 6.3 / 15.8 s | 20.0 / 50.1 s |
| Simulations / failed | 6,250 / 20 | 17,299 / 22 |

The scores are not read: 50 deals, and simulations that failed. The n = 16 timing ran beside a CPU
reproduction, so it is high. The 927 recorded targets of n = 4 are complete (encoding,
probabilities, value, options with mean, worlds and variance, result, seed). 20% of them had no
difference in result among the compared options.

**P11 falsified by the pilot, and the cause.** Every failure was one engine refusal:
`attach_card: card:N already carries 'X'; detach before swapping a permanent's compiled record`
(`MTG_bot/core/executor/binding.py:474`).
- A card that is cast or played is bound to its compiled record, and nothing unbinds it when it
  leaves the battlefield.
- When a bounce returned such a card to the opponent's hand, `determinize` re-drew it like any
  hidden card. The binding kept the old identity, and the copy's engine refused the new one when it
  played it.
- A CPU reproduction found the same error, and only it: 48 failures in 5,020 simulations. They fell
  in 3 of 43 games, every simulation after the bounce (cards: Kinetic Augur, Stormwing Entity,
  Chrome Replicator, Wall of Runes, Selfless Savior).

The fix: `determinize` unbinds each re-drawn card, as a dealt card is unbound. The regression test is
`test_a_redrawn_card_that_was_played_before_binds_its_new_identity`, which fails without the fix with
the pilot's error. Replayed on CPU, the failing games now run the same simulations with no failure:
seed 900140 (82 simulations, 17 failures before), 900180 (93, 29 before) and 900201 (141, 2
before). A failed simulation
now also logs its error and source line in the evaluation's summary (`sim_error:...`). So any
further failure shows what to fix.

**One correction, before any simulator training.** §1 gives E0's settings with lr 3e-4. E0 chose
1e-3 on its pilot (186 §2). 3e-4 was the command-line default it rejected. The default is now 1e-3,
so the queue's `simulator train` uses E0's setting.

**The order.** While the fix was under way, the capture ran on its own (`ONLY=`) for 7 minutes. It
was stopped at 5,000 games and set aside (`runs/window1/capture_stopped_1832`). The queue then runs
in §2's order from the commit holding this section: N1, gate A's confirmation, the capture, the
simulator, N5, N2-N4, N6. At 300 deals the pilot puts the whole window at 10-13 hours.

## 4. The n-curve and gate A (2026-11-11, 18:34-22:11)

**How it was run and scored.**
- Run from the worktree at e462628 (§3's fix), in §3's order, with nothing else on the GPU.
- Scored with `.venv/bin/python -m tools.selfplay.ncurve runs/window1/{n2,n4,n8,n16,n32,n64,confirm16}`.
- "No difference in result" counts the recorded targets by `distill.describe`'s rule, using a
  scratch script. Only act decisions are recorded. Attack plans are searched but not recorded:
  `Searcher.choose` records and `plan_attacks` does not (`search.py:369-371`).
- Times are the upper edges of buckets a tenth of a decade wide (`search.ms_percentiles`), so they
  are within 26%.

| n | Score, 300 deals | Elo | Moves changed by the search | Clear corrections per game | Decisions with no difference in result | Time per searched decision, p50 / p99 | Wall time |
|---|---|---|---|---|---|---|---|
| 2 | 0.532 ± 0.010 | +22 | 10% | 0.52 | 52% | 2.0 / 10 s | 5 min |
| 4 | 0.556 ± 0.012 | +39 | 14% | 0.71 | 21% | 6.3 / 25 s | 9 min |
| 8 | 0.568 ± 0.012 | +47 | 14% | 0.64 | 19% | 10 / 50 s | 16 min |
| 16 | 0.583 ± 0.012 | +58 | 15% | 0.64 | 16% | 16 / 79 s | 27 min |
| 32 | 0.568 ± 0.011 | +47 | 18% | 0.60 | 15% | 40 / 158 s | 44 min |
| 64 | 0.578 ± 0.012 | +55 | 19% | 0.56 | 13% | 79 / 316 s | 93 min |
| 16, fresh deals 950,000+ | **0.555 ± 0.012** | +38 | 18% | 0.68 | 16% | 16 / 79 s | 22 min |

Every point searched 12.2-12.7 decisions per game, and 11.6 on the fresh deals. Of each point's 600
games, 597-599 had a winner. The rest were 1-3 games at the turn cap, plus one mutual loss on the
fresh deals.

**Scored:**

| # | Result | Verdict |
|---|---|---|
| P1 | +0.0085 per doubling, 95% [+0.0033, +0.0137] (ncurve's fit, which treats the points as independent). The six points share their deals, and a deal's scores correlate 0.43-0.74 between points. Paired by deal: +0.0081 [+0.0038, +0.0124] | met |
| P2 | 0.5825 ± 0.012 | met |
| P3 | 0.555 ± 0.012 on fresh deals: +0.055, about 38 Elo | met: **gate A passes** |
| P8 | 0.64 per game (0.68 on the fresh deals) | met |
| P9 | 0.160 (0.156 on the fresh deals) | below the predicted 0.30-0.70. Not falsified (the falsifier is above 0.85). The value leaf grades almost every comparison: 84% of searched decisions show a difference in result, against 8% in E3 |
| P10 | p50 12.6-15.8 s, mean 19.1 s | missed (predicted 1-5 s) |
| P11 | 0 failures in 1,019,729 simulations over the seven runs | met |

P4-P7, S1 and S2 are scored when the window ends.

**The shape.** This is exploratory, not pre-registered.
- Per deal, the slope over n = 2-8 is +0.018 ± 0.006 per doubling.
- Over n = 8, 32 and 64 it is +0.003 ± 0.004. n = 16 is left out because it scored high on its own
  deals: 0.583 there against 0.555 on fresh deals.
- So most of the gain arrives by n = 8-16. Above that, a doubling adds at most about +0.01.
- One straight line in log2 n still fits every point within 1.3 standard errors. So a slow rise
  cannot be told apart from a plateau.

**The time.**
- Every point costs about 1.3 s per simulation: the mean time per searched decision divided by the
  simulations per decision is 1.26 s at n = 2, 1.30 s at 16 and 1.28 s at 64.
- The simulations of one decision run one after another (`search.py:321`). Each one waits in the
  batched inference queue of 288 concurrent games.
- P10's 1-5 s assumed unloaded inference.
- The clock's latency, one game on an idle machine, is measured separately (PLAN_CEILING §3.3).

**What it means (§2).**
- P1 and P3 are met, so gate A passes at n = 16.
- By PLAN_CEILING §10, gate B's generation (300k targets at the chosen n) comes after r27 has run,
  on days 4-6. The owner chooses the three n on the full window's numbers.
- n = 128: PLAN_CEILING §3.3 allows it, because the slope's lower bound at 64 is above 0. It is not
  in window 1's queue:
  - it would take about 3 hours at n = 64's rate;
  - none of the three uses of n could afford it, since n = 64 already takes 79 s per searched
    decision at p50.

## 5. The simulator (2026-11-11 22:11 - 2026-11-12 00:01)

**How it ran.**
- The capture: 40,000 games in 28 minutes, 2,291,252 positions. The 1,600 held-out games (seed
  % 25 = 0) hold 91,910 positions. Training used the other 2,199,342.
- Training: 4 epochs in 81 minutes. The training loss by epoch was 143.6, 132.6, 129.3 and 124.9,
  so it was still falling at the fourth, as E0's was.
- The learning rate was 1e-3. §1 says "E0's settings" and gives lr 3e-4, but 3e-4 was E0's
  pre-registered value. E0 changed to 1e-3 after its pilot (186 §2), and 1e-3 is the simulator's
  default (`tools/selfplay/simulator.py:429`). So the run used E0's settings and §1's text was wrong.
- Scored with `simulator eval` on the held-out positions (`tools/selfplay/simulator.py:363-396`,
  40 s).

**Scored:**

| # | Result | Verdict |
|---|---|---|
| S1 | Hand NLL 11.23, against 15.77 for the uniform pool prior: ratio 0.712, 95% [0.705, 0.720] by bootstrap over the 1,600 games | met (predicted 0.55-0.80) |
| S2 | ECE 0.0015 over 23.9M (position, card) pairs in 15 equal-mass bins. The largest bin error is 0.011 | met (predicted under 0.01) |

**Context.** This is exploratory, not pre-registered.
- By game phase the ratio is 0.658 at turns 0-6, 0.705 at turns 7-12 and 0.756 at turns 13+. E0's
  ratio against the deck-aware yardstick went the other way (0.975 early, 0.821 late). Against
  uniform, much of the gain is probably what a coherent deck implies, and that matters most while
  the hand is large.
- By set: M20 0.713, M21 0.712.
- By who plays:
  - the network predicting the network: 0.698;
  - the heuristic predicting the network: 0.731;
  - the network predicting the heuristic: 0.709.
- Over each position's 24 likeliest cards the ECE is 0.0093 (E0: 0.0025).
- Library NLL is 70.15 per position. It is not compared with a prior here; in E0 the library was
  no better than the prior's.

**What it means.** S1 and S2 are met, so N5 runs: simulator worlds against uniform worlds at
n = 16, started 00:01. P7 then decides whether simulator worlds become the default (§2).

## 6. The clock's latency, after the window (pre-registered 2026-11-12 00:12, before it runs)

**Why now.** Choosing n for play under a clock (PLAN_CEILING §3.3, NORTH_STAR §1a) needs a single
game's latency on an idle machine. The window's timings carry the load of 288 games. The machine is
next idle only between the window and r27, so the measurement runs there and r27 starts after it.
That is about 30 minutes later, and at most 1 h 45 min, because each point has a time cap.

**How.**
- `reports/window1_2026-11-11/clock.sh` runs as the transient unit `mtg-clock1`.
- It runs from the window's worktree at e462628. Its search code is the same at r27's commit
  f473c44.
- One game at a time (`--workers 1 --slots 1 --groups 1`). Otherwise the settings are those of the
  n-curve's points: gumbel, m 16, horizon 1, uniform worlds, deals 900,000+.
- The points:
  - clock_n16: n = 16, 10 deals (20 games), capped at 40 minutes;
  - clock_n4: n = 4, 5 deals, capped at 20 minutes;
  - clock_n64: n = 64, 5 deals, capped at 45 minutes.
- A CPU smoke test of these flags passed (n = 2, one deal, one throttled thread: 0.93 s per
  simulation).

**Predictions:**

| # | Measure | Prediction | Falsifier |
|---|---|---|---|
| C1 | Seconds per simulation at n = 16 (mean ms per searched decision over simulations per searched decision) | 0.05-0.30 (under the window's load: 1.30) | above 0.6: the load was not the main cost |
| C2 | A searched decision's p99 at n = 16 | 2-15 s | — |
| C3 | The searching seat's search time per game at n = 16 | 10-90 s | — |
| C4 | Seconds per simulation at n = 4 and at n = 64, against n = 16 | within 30% | — (it decides whether a decision's time can be read as proportional to n) |

**What it means.**
- The clock to fit is the hard-loss one of `docs/CLOCK_TARGETS.md`. On Magic Online that is 25
  minutes per player per match, ticking only while the player has priority: about 500 s per game
  over three games.
- The owner reads n for play from C1-C4.
- A decision's simulations run one after another (`search.py:321`). Running them in parallel would
  cut the latency, and is not measured here.

## 7. The variants at n = 16 (scored as each finishes)

Every variant is paired by deal with the uniform n = 16 point of §4 (deals 900,000-900,299), as
§2 registered. That point is the high one of the curve: it sits +0.015 ± 0.008 above the mean of
n = 8 and n = 32 on the same deals, and scored 0.555 on fresh deals. So each verdict is also read
against the uniform points around n = 16 (exploratory). Scripts: `variants.py` and
`neighbours.py`, scratch, reading `eval_rows.jsonl` and the recorded targets.

### 7.1 N5: simulator worlds (2026-11-12 00:01-00:25)

| | uniform, n = 16 | simulator, n = 16 |
|---|---|---|
| Score, 300 deals | 0.5825 ± 0.012 | 0.5625 ± 0.0115 |
| Searched decisions per game | 12.59 | 12.48 |
| Moves changed | 15.4% | 15.0% |
| Clear corrections per game | 0.64 | 0.61 |
| No difference in result | 16% | 17% |
| Seconds per simulation | 1.30 | 1.56 |
| Simulation errors | 0 | 0 |

**P7** (simulator minus uniform, predicted 0.00 to +0.03, falsified below -0.01): -0.020 ± 0.011,
95% [-0.042, +0.002]. **Falsified on the point estimate; the interval straddles -0.01.** By §2,
simulator worlds do not become the default, for the search or for gate B's generation.

**What the result does not say.** The owner asked whether uniform worlds are simply better
(2026-11-12). The data do not show that:
- Against the uniform points around n = 16 on the same deals, the simulator's worlds score
  -0.005 ± 0.011 (n = 8), -0.005 ± 0.010 (n = 32), -0.016 ± 0.010 (n = 64), and -0.009 ± 0.009
  against the mean of 8, 32 and 64: 95% [-0.026, +0.009].
- So about half of the -0.020 is the uniform point's own high draw. What remains is "no gain
  detected", with a loss of up to 0.026 or a gain of up to 0.009 still possible.

**Checks made after the result** (exploratory):
- **No bug found in the path.**
  - The worlds are drawn from the view of the decision being searched: `root_pos` is set at every
    act decision, attack plan and block plan (`search.py:362`, `:405`, `:467`).
  - The hand and library lengths come from that view, and `determinize` fills the opponent's real
    zones from them (`search.py:111-142`).
  - There were 0 simulation errors.
- **The simulator's worlds are realistic; uniform worlds are not.** On 1,000 held-out positions of
  the capture's first shard, with 8 worlds each (the search's own sampler,
  `Simulator.sample_worlds`):

  | | True | Simulator | Uniform |
  |---|---|---|---|
  | Lands in the opponent's hand | 15.0% | 15.7% | 8.7% |
  | Lands in the opponent's library | 39.1% | 39.3% | 8.9% |
  | Hand cards that are among the opponent's real hidden cards | — | 37.0% | 11.4% |
  | Mean mana value of the hand's spells | 3.85 | 3.87 | 3.24 |

  Uniform worlds give the opponent's library 9% lands instead of 39%, so in a simulation the
  opponent mostly misses its land drops. By turn the simulator's share of real cards is 42% at
  turns 0-6, 41% at 7-12 and 33% at 13+, against 13%, 12% and 10% for uniform.
- **Not variance.**
  - Recorded targets: a candidate's results across its worlds vary 17% more with the simulator's
    worlds (variance 0.0352 against 0.0302).
  - The spread between candidates is the same (0.0595 against 0.0597).
  - 17% more variance is worth about 15% of the simulations, which by §4's slope costs about 0.002.

**Why better beliefs gained nothing here.** This is a reading, not a measurement.
- A simulation is scored by the network's value from the searcher's own view
  (`search.py:521-529`), which never sees the opponent's hand. The hidden cards change the score
  only through the opponent's play until the searcher's next turn (horizon 1).
- At n = 16 the candidates' mean results differ by about one standard error of a mean: the median
  ratio is 0.83 with uniform worlds and 0.81 with the simulator's. At n = 64 it is 0.90.
- So most searched decisions are close calls that the search cannot resolve. Its gain comes from
  about 0.6 clear corrections a game, and better beliefs have little room to show there.

**The test that would decide it** (a later window, pre-registered when built).
- Score the same positions' candidates three ways: uniform worlds, simulator worlds, and the true
  hidden cards.
- Count how often each world type picks the move the true cards pick.
- Pairing by position removes the deal noise that a 300-deal match cannot get past. Horizon 2,
  where the opponent's replies weigh more, is the second test.

### 7.2 N3: priority asks searched as well (2026-11-12 00:26-01:57)

| | act only, n = 16 | act and priority, n = 16 |
|---|---|---|
| Score, 300 deals | 0.5825 ± 0.012 | 0.5908 ± 0.0123 |
| Searched decisions per game | 12.59 | 22.32 (act 9.94, priority 9.97, attack 2.41) |
| Moves changed | 15.4% | 10.6% (act 15.3%, priority 4.8%, attack 15.3%) |
| Clear corrections per game | 0.64 | 0.89 |
| No difference in result | 16% | 18% |
| Seconds per simulation | 1.30 | 1.24 |
| Wall time | 27 min | 91 min |

**P5** (act and priority minus act only, predicted 0.00 to +0.02 at about twice the searched
decisions, falsified below -0.01): +0.0083 ± 0.0079, 95% [-0.0072, +0.0238], at 1.8 times the
searched decisions. **Met.**

**Exploratory.**
- Against the uniform points around n = 16, act only: +0.023 ± 0.011 (n = 8), +0.023 ± 0.011
  (n = 32), +0.013 ± 0.011 (n = 64), and +0.020 ± 0.009 against the mean of the three, 95%
  [+0.002, +0.038].
- So searching the priority stops adds about +0.01 to +0.02 at n = 16.
- The wall time is 3.3 times the act-only point's for 1.8 times the searched decisions: one
  searched game with many priority stops ran long at the end.

### 7.3 N2: the plain grid, top 4 in 4 worlds each (2026-11-12 01:57-02:16)

| | gumbel, n = 16 | topk 4 x 4 |
|---|---|---|
| Score, 300 deals | 0.5825 ± 0.012 | 0.5742 ± 0.014 |
| Searched decisions per game | 12.59 | 12.88 |
| Moves changed | 15.4% | 40.0% (act 41.2%, attack 34.5%) |
| Clear corrections per game | 0.64 | 0.78 |
| No difference in result | 16% | 20% |
| Seconds per simulation | 1.30 | 1.42 |
| Wall time | 27 min | 19 min |

**P4** (gumbel minus topk at 16 simulations, predicted -0.01 to +0.03, falsified below -0.02):
+0.0083 ± 0.0144, 95% [-0.020, +0.037]. **Met.**

**Exploratory.**
- Against the uniform gumbel points around n = 16: +0.007 (n = 8), +0.007 (n = 32), -0.004 (n = 64),
  and +0.003 ± 0.0125 against their mean. The two roots are not told apart.
- The grid changes 40% of the network's moves, against gumbel's 15%, for the same score.
  - It compares four candidates on four worlds each, without the network's prior.
  - So most of its extra changes are noise that neither helps nor hurts.
  - Gumbel's halving keeps the prior in the comparison.
- The two runs' deal scores correlate only 0.39 (against 0.56-0.79 for the other variants). The
  different moves take the games down different paths.

### 7.4 N4: horizon 2 (2026-11-12 02:16-03:18)

| | horizon 1, n = 16 | horizon 2, n = 16 |
|---|---|---|
| Score, 300 deals | 0.5825 ± 0.012 | 0.5767 ± 0.0126 |
| Searched decisions per game | 12.59 | 12.77 |
| Moves changed | 15.4% | 16.2% (act 15.6%, attack 18.7%) |
| Clear corrections per game | 0.64 | 0.82 |
| No difference in result | 16% | 23% |
| Seconds per searched decision, mean | 19.1 | 35.9 |
| Seconds per simulation | 1.30 | 2.45 |
| Wall time | 27 min | 62 min |

**P6** (horizon 2 minus horizon 1, predicted -0.01 to +0.03 at about twice the time; no falsifier,
cost-benefit only): -0.0058 ± 0.0111, 95% [-0.028, +0.016], deal correlation 0.60, at 1.88 times
the time per searched decision. Inside the predicted range. **The cost-benefit says no:** twice
the time for no measurable gain.

**Exploratory.**
- Against the uniform horizon-1 points around n = 16: +0.009 (n = 8), +0.009 (n = 32), -0.002
  (n = 64), and +0.006 ± 0.010 against their mean. Horizon 2 is not better at any n here.
- Its extra ties are finished games. In 20.4% of its searched decisions, every simulation of
  every candidate reached the game's end with the same result, against 13.2% at horizon 1. That
  accounts for nearly all ties at both horizons (20.3 of 22.7 points; 13.2 of 16.0).
- So 13% of the decisions searched at horizon 1 are already decided either way. Their time is
  spent for nothing.
- Horizon 2 plays the opponent's whole turn from worlds whose hidden cards are uniform (§7.1:
  9% lands in a uniform library). That may be why the second turn adds noise rather than signal,
  but nothing here tests it. The belief audit (KNOWLEDGE/2026-11-12/195) measures what the
  worlds cost at horizon 1.

### 7.5 N6: against the heuristic (2026-11-12 03:18-03:37)

| | raw (n = 0) | searched, n = 16 |
|---|---|---|
| Score against the new heuristic, 300 deals | 0.6917 ± 0.0171 | 0.7283 ± 0.0164 |
| Elo over the heuristic | +140 | +171 |
| Searched decisions per game | — | 11.04 (act 8.89, attack 2.14) |
| Moves changed | — | 16.7% (act 17.6%, attack 13.1%) |
| Clear corrections per game | — | 0.50 |
| No difference in result | — | 18% |
| Seconds per simulation | — | 1.42 |
| Wall time | 34 s | 17.5 min |

N6 had no numbered prediction (§2). Search minus raw: **+0.0367 ± 0.0121**, 95% [+0.013, +0.060],
deal correlation 0.74, or **+31 Elo** [+11, +51].

**Exploratory.**
- **The search's gain carries to an opponent it does not model.**
  - Its simulations play the opponent as the network. Against the raw network, that is the
    opponent's exact policy; against the heuristic, it is not.
  - Its gain is +31 Elo against the heuristic. Against its own network it is +38 Elo on fresh
    deals (gate A, 0.555), and +47-58 Elo on these deals (the n = 16 point and its neighbours'
    mean).
  - The difference is within the noise. At this precision, most of the gain does not come from
    knowing the opponent's policy.
- The old search at 6 simulations raised the score against the old heuristic by +0.045-0.060
  (§2, P2). This one raises it by +0.037.
- **A warning for r27's prediction 9** (191 §4: v0 against the new heuristic, 500 deals, greedy,
  0.80-0.90).
  - v0 is this network (u1000), and the code is the same: e462628 and r27's d6dcdff differ only
    in the training-game log and PPO's minibatch order.
  - Here it scores 0.692 ± 0.017 over 600 games, on M21 coherent decks.
  - The 0.80-0.90 rested on 35 of 40 games, by r26 at update ~830, on the CPU in fp32. This run
    used u1000 on the GPU in bf16.
  - The start ladder will likely falsify prediction 9.
  - Whether the precision explains the gap is checked next: the same 300 deals on the CPU in fp32
    (§7.6).

### 7.6 Why does u1000 score 0.69 against the heuristic, not 0.875? (pre-registered 2026-11-12 04:00, before either check runs)

**The two numbers.**
- Window 1's `heur_raw`: u1000, GPU, bf16 inference, the verified pool, deals 900,000-900,299
  with both seats each: 0.692 ± 0.017.
- The 35/40 behind r27's prediction 9 (scratch `grown_row.py`, 2026-11-11 11:50) differs in:
  - the network: r26 at update ~830;
  - the device and precision: CPU, fp32;
  - the cards: the **castable** pool (`get_supply("castable")`);
  - the deals: seeds 0-39, one seat each.
- 35/40 is 0.875 ± 0.052. If the two measured the same thing, a gap this size would come up
  less than 1% of the time.

**Two checks, in window 2 on the GPU** (`reports/window2_2026-11-12/queue.sh`). The CPU is r27's
until then, so they do not run there.

| # | Check | Prediction | Falsifier |
|---|---|---|---|
| H1 | `heur_raw_fp32`: as `heur_raw` with fp32 inference, the same 300 deals; fp32 minus bf16, paired by deal | within ±0.03 (183 measured bf16 copies against fp32 autocast on the old game: the same argmax, values within 8.8e-4) | +0.04 or more with the lower bound above 0: bf16 inference costs strength, a fault to fix before any further evaluation |
| H2 | `heur_raw_castable`: as `heur_raw` on the castable pool (other decks, so not paired) | 0.74-0.88: the castable pool's extra cards favour the network, or play badly for the heuristic | at or below 0.72: the pool does not explain the gap, which then lies with the update (~830 against 1,000) or the 40 games' noise |

**What each outcome means.**
- **H1 met, H2 met:** nothing is broken. Prediction 9 was set on another pool's number.
- **H1 met, H2 falsified:** nothing is broken in precision. The remaining causes are harmless (the
  update, or noise).
- **H1 falsified:** every bf16 evaluation since 183 understates the network against outside
  opponents. Self-play pairs are unaffected, because both seats are bf16. The fix and a re-check
  come before window 2's other numbers are read.
