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
