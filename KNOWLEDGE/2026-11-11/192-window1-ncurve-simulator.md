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
