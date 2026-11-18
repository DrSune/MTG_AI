# 214. Planning puzzles, P0: the exact solver, the first wave and the first readout (2026-11-18)

P0 of [`docs/PLAN_PLANNING.md`](../../docs/PLAN_PLANNING.md) (§4, §5): a planning puzzle suite
whose answers come from the rules and exhaustive play in our own engine, a runner that reads any
network on it, and the first readout. The owner's point (2026-11-18, OWNER_VISION_LEARNING §12): a
ceiling cannot be measured with a model that is not good at the skill, so no answer here is read
from a network.

Built in `tools/puzzles/`: `solver.py` (the solver), `puzzle.py` (the format, building the worlds),
`runner.py` (the readout), the tests, and the suite (`suite/`, 16 puzzles). CPU only; no engine or
self-play code changed.

## 1. The solver

**Definition.** A puzzle is an arranged game at a decision of one seat, the decider, plus
`world_prior`: the hidden cards of each world (the opponent's hand; a library's top where a draw
falls inside the horizon), with probabilities. The value of a root option is

> the maximum, over the decider's pure strategies that begin with it (one action per decider
> information set), of the prior-weighted value when, in each world, the opponent best-responds.

- **The decider's information set** is its seat's view (`SeatLens.view`: the public game and its
  own hand; objects named by view ids assigned in the view's own order, so no engine handle of a
  hidden card can tell two worlds apart), whether the other player just passed, the ask, its
  options, and the decider's own earlier decisions (perfect recall). Two positions with the same
  information set get the same action in every world: the decider never acts on a card it cannot
  see (no strategy fusion).
- **The opponent** is given the whole world and the decider's strategy, and plays its best reply
  in each world. With the decider's own cards fixed that is the brief's definition; where a prior
  varies the decider's library (A1), the opponent knowing it can only lower the decider's values.
  The decider commits, the opponent is perfect: a sound, conservative value. Puzzles that need
  mixing or bluffing are out of scope.
- **Values.** The game's result inside the horizon (the decider wins 1; it loses, or both lose, 0).
  A game still running after the puzzle's last turn scores the puzzle's `objective`: `win` 0,
  `survive` 1, `result` 0.5 (undecided: worth less than a win, more than a loss). Never a
  network's value.

**How** (`solver.EngineTree`, `solver.Solver`).
- Every option of every decision, both seats, is the engine's own ask, routed through
  `bench.router.SeatRouter` as a game routes it. A position is a paused copy of the game plus the
  answers to give after resuming it (`_play(resumed=True)`). A decision at the game loop's priority
  point (an `act` or `priority` ask) is itself a pause point: no engine call is in flight, and a
  copy taken there asks the same decision again on resuming (the search's own mechanism, `search.py`).
  Every other ask (a target, a mode, an attacker, a blocker, Anticipate's pick) is replayed from
  the last pause point.
- The recursion works on groups of positions the decider cannot tell apart, one per world and per
  opponent line that leads there. For each option of a group it follows every opponent line to the
  decider's next decisions, groups those by information set, and solves each group. A group's
  result is the set of Pareto-best value vectors (one entry per member) its strategies reach; a
  member's value is the minimum over the opponent's lines (the opponent chooses, knowing the world);
  the decider picks one option for all of a group's members. A root option's value is the best
  prior-weighted vector it reaches. With one world this is plain minimax.
- Exact cut-offs: a group stops at an option reaching the best value in every member; a member
  stops at an opponent line reaching the worst value.
- No memoization by state: two orders of the same moves leave different journals (which the
  engine's own state fingerprint includes), so merging them needs an argument that no rule reads
  the difference. Not needed at these sizes.

**Tests** (`test_solver.py`). The first four fail on a naive solver; checked by mutating the
solver (`reports/planning_puzzles_2026-11-18/mutate.py`): each of the three mutations below fails
them, and the unmutated solver passes:
- *a tiny real game with hand-computed values* (`testdata/t_two_attackers`): Centaur Courser and
  Goblin Assailant against one Walking Corpse and 2 life: ATTACK 1, DECLINE 0;
- *a strategy-fusion trap*: three worlds; a safe option worth 2/3, and a guess the decider must
  make blind, worth 1/3. Solving each world alone (`Solver.fused`) values the guess 1 and picks it;
  the solver picks the safe option. A variant where the opponent's move reveals one world gives
  the guess 2/3 (the information sets split where the decider can see). Mutation: grouping each
  member alone fails both;
- *an opponent best-response game* (`testdata/t_one_blocker`): 3 life, one blocker, Assailant asked
  first. A passive opponent loses to either attack and a first-option opponent to both; the perfect
  one makes every option 0. Mutation: the opponent taking its first option fails it and the next;
- *the opponent's minimum short of the floor* (undecided against a win). Mutation: the opponent
  maximising fails five of the eight;
- the worlds' roots look the same to the decider (B1's two worlds: one information set);
- a pause point is transparent: from B1's root, each option played on from the paused copy reaches
  the state (`Executor.state_fingerprint`) the same line reaches played straight from the start.

`pytest tools/puzzles` = 27 passed (with the suite's and the runner's tests), 16 s.

The fusion trap is a hand-written tree: none of the 16 puzzles has a later decision the decider
must take blind that changes a value, and `fused` gives the same values as the solver on all 16.
A real-engine trap is a design for the next wave (§6).

**Cost.** A fork at a puzzle's arranged start costs 0.83 ms (mean over the 16 world-0 roots,
0.75-0.91 ms, 18-31 cards; NUMBERS 2026-10-10's 6 ms was a dealt game of 120 cards). An engine run
(a fork, the replay, the observation key) costs 1.9-4.8 ms per puzzle, 3.2 ms over the suite's
12,380 runs (39.2 s). The 16 puzzles take 37 to 7,351 runs and 0.1 to 20.8 s each (§3), on one
core beside r29's reads.

## 2. The format

One JSON file per puzzle in `tools/puzzles/suite/` (`puzzle.py`'s docstring has every key): the
scenario pack's world and cards (real, verified M21 or M20 cards only, `puzzle.check_cards`;
libraries listed top first), `life`, `decider`, `prelude` (the decisions of both seats from the
arranged start, seat 0's first main phase, to the puzzle's decision, as option words with pack keys),
`world_prior` (each world's hidden cards; the same number in every zone in every world, so every
shared object has the same handle everywhere), `horizon` (the last turn played), `objective`,
`answer`, `twin`, `category`, `grade`, and `solver` (written by `solver.py --write`: each root
option's value, the best options, runs, decisions, seconds, worlds). `test_suite.py` checks every
puzzle: its twin names it back and its right move differs, its cards are verified, its record's
best options are its answer, and the ones that solve in 5 s or less are solved again.

## 3. The first wave: 16 puzzles, 8 twin pairs, all proven

| Puzzle | Cat. | Set | Cards (decider / opponent) | Horizon, objective, worlds | Right | Values | Runs | s |
|---|---|---|---|---|---|---|---|---|
| a1_draw_then_pick_the_land | A | M20 | 2 Islands, Corpse, Assailant; Anticipate, Mountain, Island / Corpse; top Unsummon or Infuriate | 1, win, 2 | cast Anticipate | Anticipate 1, either land 0.5, pass 0 | 7,351 | 20.8 |
| a1_land_to_cast_the_draw | A | M20 | as a1 with 2 Mountains | 1, win, 2 | Island | Island 0.5, Mountain 0, pass 0 | 1,844 | 5.9 |
| a2_pump_after_blocks | A | M21 | Corpse, Watchdog attacking; Sure Strike / Corpse, 4 life | 1, win, 1 | pass (pump after blocks) | pass 1, Sure Strike now 0 | 37 | 0.1 |
| a2_bounce_before_blocks | A | M21 | as a2 with Unsubstantiate | 1, win, 1 | Unsubstantiate now | now 1, pass 0 | 38 | 0.1 |
| b1_counter_the_answer_lethal | B1 | M21 | Corpse, Watchdog attacking, 3 Islands, Cancel / Shock on the Corpse, 6 lands, 4 life; Massacre Wurm or a land | 2, result, 2 | Cancel | Cancel 1, pass 0.5 | 46 | 0.2 |
| b1_counter_the_answer_not_lethal | B1 | M21 | as b1, opponent at 10 | 2, result, 2 | pass | pass 0.5, Cancel 0.25 | 58 | 0.2 |
| b2_hold_until_backed | B2 | M21 | 5 lands, Storm Caller, Cancel, a Mountain for next turn / 6 Islands, 2 life; holds and draws Cancel or a land | 3, result, 4 | pass | pass 0.875, Caller 0.75 | 783 | 3.7 |
| b2_cast_into_tapped_out | B2 | M21 | as b2, the Islands tapped | 3, result, 4 | Storm Caller | Caller 1, pass 0.875 | 751 | 3.6 |
| b3_hold_for_the_threat | B3 | M20 | Corpse, Assailant, 2 Islands, Negate, 2 life / Disfigure on the Corpse, 5 Mountains open; Chandra's Flame Wave (2/3) or a land | 2, result, 2 | pass | pass 0.5, Negate 0.333 | 126 | 0.5 |
| b3_counter_the_minor_spell | B3 | M20 | as b3, the Mountains tapped | 2, result, 2 | Negate | Negate 1, pass 0.5 | 66 | 0.3 |
| c1_crackback_lethal | C | M20 | Warden of Evos Isle, 2 life / Corpse, 4 life | 3, result, 1 | do not attack | DECLINE 0.5, ATTACK 0 | 61 | 0.1 |
| c1_crackback_not_lethal | C | M20 | as c1 at 3 life | 3, result, 1 | attack | ATTACK 1, DECLINE 0.5 | 113 | 0.2 |
| c2_chump_to_the_sweeper | C | M20 | Warden, Flame Sweep, lands tapped, 6 life / two 3/2 attackers, 2 life | 2, result, 1 | block either | block 0.5, no block 0 | 112 | 0.3 |
| c2_take_it_to_the_sweeper | C | M20 | as c2 at 7 life | 2, result, 1 | no block | no block 1, block 0.5 | 119 | 0.3 |
| d_do_not_overextend | D | M21 | Corpse (attacked), 3 Mountains, Onakke Ogre, 4 life / 6 Swamps, 8 life; Massacre Wurm (2/3) or a land | 3, result, 2 | pass (hold the Ogre) | pass 0.5, Ogre 0.333 | 513 | 1.8 |
| d_overextend | D | M21 | as d with 3 Swamps | 3, result, 2 | Onakke Ogre | Ogre 1, pass 0.5 | 362 | 1.1 |

Each puzzle's `note` gives the lines behind its values. The evidence each twin changes is visible:
the colours on the battlefield (A1), the trick in hand (A2), the opponent's life (B1), the
opponent's lands tapped or not (B2, B3), the decider's life (C1, C2), the opponent's land count (D).

**No puzzle was dropped; three were redesigned on the solver's word.**
- *The root must be the last moment the choice can be made.* B2's first draft asked in the first
  main phase: passing there still casts Storm Caller in the second, so its tapped-out twin valued
  both options 1. B2 and D now ask in the second main phase, A2 in the declare-attackers step, B1
  with the answer already on the stack.
- *B3's first draft* gave the opponent Chandra's Outrage as a third world; an instant there gives
  the opponent a decision before the decider's in that world only, so the worlds' roots differ.
  Flame Wave (a sorcery) alone replaced it.
- *B3 and D need the threat more likely than not.* Holding against the threat is undecided (1/2)
  in every world; going wins in the safe world and loses in the threat world: 1 - p. With p = 1/2
  they tie exactly; both puzzles put 2/3 on the threat (the opponent kept exactly its mana open
  and one card), and say so in their notes. B1 and B2 hold at 1/2 and 1/4.

## 4. The first readout

`runner.py` reads each checkpoint on CPU (`model.load(path, "cpu")`) at each puzzle's decision,
reached as a game reaches it (`rig.SelfplayRouter` answering the prelude, so the network's
`AskContext` is the one it plays with): the policy's probability on the right options, its greedy
pick, the value head's (v + 1) / 2, and for the 12 puzzles whose decision is an act or priority ask
the searched pick (`search.Searcher` at window 1's anchor setting, 205: Gumbel root, m 16, n 4,
horizon 1, uniform worlds, greedy continuation, skip at 0.97; act and priority asks), 8 seeds each.
C's four decisions are attack and block asks, which the searcher plans at the combat boundaries
instead; they are not searched here. Every visible card is in every checkpoint's card table.

Checkpoints: r28's v2 (`runs/r28_looks/r28_v2.pt`, sha256 d9f75295…) and r29's arm snapshots
(`runs/r29_ab/`; arm A `--p-self 0`: a70-a100 = updates 75, 85, 95, 103; arm B `--p-self 0.55`:
b70-b100 = updates 85, 100, 110, 125; sha256 prefixes in `runs/r29_ab/queue.log`). 9 checkpoints in
5 min 9 s wall (18-60 s each) at 2 threads, nice 19, beside r29's reads. Output `reports/planning_puzzles_2026-11-18/readout.json`,
tables by `reports/planning_puzzles_2026-11-18/table.py`.

**Per category**: twin-consistent pass rate (greedy) / mean probability on the right options /
searched pass rate (8 seeds; "-": not searched). Then the suite: twin-consistent pairs of 8, single
puzzles passed of 16, mean probability on the right options, searched pass rate, searched pairs
right in most seeds in both twins (of 6), and the value head's order (§4.2).

| Checkpoint | A | B1 | B2 | B3 | C | D | pairs | single | p right | searched | searched pairs | value order |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| r28_v2 | 0 / 0.33 / 0.25 | 0 / 0.54 / 0.62 | 0 / 0.53 / 0.50 | 0 / 0.46 / 0.50 | 0 / 0.51 / - | 0 / 0.50 / 0.50 | 0 | 0.44 | 0.46 | 0.44 | 0 | 0.57 |
| a70 | 0 / 0.35 / 0 | 0 / 0.51 / 0.50 | 0 / 0.52 / 0.50 | 0 / 0.50 / 0.50 | 0 / 0.50 / - | 0 / 0.50 / 0.50 | 0 | 0.38 | 0.47 | 0.33 | 0 | 0.43 |
| a80 | 0 / 0.34 / 0 | 0 / 0.52 / 0.81 | 0 / 0.52 / 0.50 | 0 / 0.51 / 0.50 | 0 / 0.50 / - | 0 / 0.50 / 0.50 | 0 | 0.38 | 0.47 | 0.39 | 0.17 | 0.57 |
| a90 | 0 / 0.34 / 0 | 0 / 0.51 / 0.50 | 0 / 0.51 / 0.50 | 0 / 0.51 / 0.50 | 0 / 0.50 / - | 0 / 0.50 / 0.50 | 0 | 0.38 | 0.46 | 0.33 | 0 | 0.71 |
| a100 | 0 / 0.33 / 0.25 | 0 / 0.57 / 0.62 | 0 / 0.52 / 0.50 | 0 / 0.49 / 0.50 | 0 / 0.50 / - | 0 / 0.51 / 0.50 | 0 | 0.44 | 0.47 | 0.44 | 0 | 0.57 |
| b70 | 0 / 0.29 / 0 | **1** / 0.54 / 0.62 | 0 / 0.50 / 0.50 | 0 / 0.49 / 0.50 | 0 / 0.50 / - | 0 / 0.50 / 0.50 | 0.12 | 0.44 | 0.45 | 0.35 | 0 | 0.71 |
| b80 | 0 / 0.32 / 0 | 0 / 0.50 / 0.62 | 0 / 0.50 / 0.50 | 0 / 0.52 / 0.50 | 0 / 0.50 / - | 0 / 0.50 / 0.50 | 0 | 0.44 | 0.46 | 0.35 | 0 | 0.57 |
| b90 | 0 / 0.31 / 0 | 0 / 0.46 / 0.62 | 0 / 0.50 / 0.50 | 0 / 0.50 / 0.50 | 0 / 0.50 / - | 0 / 0.50 / 0.50 | 0 | 0.44 | 0.45 | 0.35 | 0 | 0.71 |
| b100 | 0 / 0.30 / 0 | 0 / 0.47 / 0.62 | 0 / 0.51 / 0.50 | 0 / 0.50 / 0.50 | 0 / 0.50 / - | 0 / 0.50 / 0.50 | 0 | 0.44 | 0.45 | 0.35 | 0 | 0.57 |

**Per puzzle** (the probability on the right options, r28 v2 / a100 / b100, the range over the 9;
the greedy pick of the three; the searched pass rate over the 9):

| Puzzle | p right: v2 / a100 / b100 (range) | Greedy: v2, a100, b100 | Searched |
|---|---|---|---|
| a1_draw_then_pick_the_land | 0.20 / 0.27 / 0.25 (0.20-0.27) | Mountain, Anticipate, pass | 0 (a100: 1) |
| a1_land_to_cast_the_draw | 0.40 / 0.30 / 0.26 (0.26-0.40) | Island, pass, pass | 0 (v2: 1) |
| a2_pump_after_blocks | 0.42 / 0.43 / 0.54 (0.38-0.54) | pump now, pump now, pass | 0 |
| a2_bounce_before_blocks | 0.32 / 0.30 / 0.15 (0.15-0.45) | pass, pass, pass | 0 |
| b1_counter_the_answer_lethal | 0.07 / 0.14 / 0.78 (0.02-0.78) | pass, pass, Cancel | A 0-0.62, B 1 |
| b1_counter_the_answer_not_lethal | 1.00 / 1.00 / 0.17 (0.17-1.00) | pass, pass, Cancel | A 1, B 0.25 |
| b2_hold_until_backed | 0.22 / 0.30 / 0.10 (0.05-0.30) | Caller ×3 | 0 |
| b2_cast_into_tapped_out | 0.83 / 0.73 / 0.92 (0.73-0.95) | Caller ×3 | 1 |
| b3_hold_for_the_threat | 0.79 / 0.54 / 0.26 (0.26-0.91) | pass, pass, Negate | 0 |
| b3_counter_the_minor_spell | 0.14 / 0.45 / 0.75 (0.10-0.75) | pass, pass, Negate | 1 |
| c1_crackback_lethal | 0.00 / 0.00 / 0.00 (0.00-0.00) | attack ×3 | - |
| c1_crackback_not_lethal | 1.00 / 1.00 / 1.00 | attack ×3 | - |
| c2_chump_to_the_sweeper | 0.31 / 0.01 / 0.01 (0.00-0.31) | no block ×3 | - |
| c2_take_it_to_the_sweeper | 0.71 / 1.00 / 1.00 (0.71-1.00) | no block ×3 | - |
| d_do_not_overextend | 0.00 / 0.02 / 0.00 (0.00-0.02) | Ogre ×3 | 0 |
| d_overextend | 1.00 / 0.99 / 1.00 (0.99-1.00) | Ogre ×3 | 1 |

**4.2 The value head.** Its reading at the root, (v + 1) / 2, against the solver's value: the
solver's scale is the puzzle's objective (an undecided game is 0.5 in `result` puzzles), the value
head's is the whole game's, so only the order within a twin pair compares like with like. Of the 7
pairs the solver values differently (A2's twins are both 1), the value head orders, per pair, in how
many of the 9 checkpoints, by how much:
- B1 (seat 1 at 4 or 10): 9 of 9, by 0.14-0.37. It reads the opponent's life.
- C1 (seat 0 at 3 or 2, a lethal crack-back): 9 of 9, by 0.06-0.14.
- C2 (seat 1 at 7 or 6, a lethal attack in progress): 9 of 9, by 0.01-0.03; it reads 0.88-0.98
  in the twin where the network's own move, not blocking, loses on the spot.
- A1 1 of 9, B2 2 of 9, B3 6 of 9, D 2 of 9: differences within ±0.04 (D at b70: -0.11). It does
  not see sequencing, the opponent's open mana, or the opponent's sweeper mana.

## 5. What the readout says

**No checkpoint plays any category twin-consistently** (one pair in 72: B1 at b70). Each network
plays one habit per kind of decision and passes whichever twin the habit fits: single-puzzle pass
rates 0.38-0.44, below the 0.5 a habit earns.

- **It does not read lethal, either way (C).** Every checkpoint attacks with the Warden when the
  crack-back kills it (p = 1.00 on attack in both twins), and declines to block a lethal attack
  (p 0.69-1.00 on no block in both twins; the value head 0.88-0.98 there). This is within-turn
  combat arithmetic, with nothing hidden and no memory needed.
- **It never holds back (B2, D).** Storm Caller is cast into six open Islands (p 0.70-0.95), and
  Onakke Ogre into six open Swamps (p ≥ 0.98), as when the opponent cannot answer.
- **Counters by habit, not by the board (B1, B3).** r28's v2 and arm A pass with Cancel in both B1
  twins (p ≤ 0.14 on countering the lethal answer). Arm B moved to countering in both: from b70 to
  b100 the probability of countering goes 0.51, 0.42, 0.73, 0.78 in the lethal twin and 0.43,
  0.43, 0.81, 0.83 in the not-lethal one (b70's pair is the one pass: both just on the right side
  of 0.5). Training both seats (p_self 0.55) shifted the counter habit; it did not teach its
  condition. B3 sits near 0.5 on both twins and drifts.
- **No sequencing preference (A).** The probability on the right option is near one over the
  number of options (A1 0.20-0.40 of 3-4 options, A2 0.15-0.54 of 2), and the value head reads
  0.98-1.00 at all four A roots: neither head separates the draw-first or the pump-after-blocks
  line from its alternatives.
- **The search at n = 4 adds one-turn tactics only.** It finds the win inside its horizon
  (countering Disfigure keeps next turn's lethal: B3 1 in every checkpoint; B1's counter, 1 in arm
  B), and never fixes a twin pair (searched pairs: one of 6 in a80's B1 seeds, else 0):
  - the holds (B2, B3, D) need a belief about the opponent's hand, and uniform re-samples rarely
    deal the specific threat, so the search takes the same side in both twins;
  - the lines whose payoff needs the network's own follow-through (A2's pump after blocks, A1's
    land after the draw) are scored by the network's continuation, which does not follow through
    (PLAN_PLANNING §4's caveat on grade 3).

**Caveat: two answers rest on their prior.** B3's and D's hold twins are right when the threat is
more likely than not (§3); a network that learned the real deals' odds of Flame Wave or Massacre
Wurm behind open mana could rightly counter, or cast, there. Their failures are the weaker evidence.
Every other answer holds for any prior that gives each world a chance: B1, B2 (with 0 < the odds of
a Cancel in hand, and of drawing one, < 1), the threat-free twins of B3 and D, A1, and the
single-world A2, C1, C2.

**For the ladder** (PLAN_PLANNING §5):
- The C failures are the cleanest, and need neither memory nor a plan: lethal arithmetic at
  attacks and blocks, missed by the policy and the value head alike. Whether the searcher's attack
  and block plans (`plan_attacks`, `plan_blocks`) fix them is the next reading; P2's puzzle starts
  are the training answer.
- The B and D holds are P1's target (the plan module through the opponent's turn) and, for the
  search, a matter of its worlds: the simulator's beliefs (`--search-worlds sim`) instead of
  uniform re-samples.
- A's sequencing is the case for PLAN_PLANNING §3's O2 (consequence previews), built only if
  training does not fix it: this is its first measurement.

## 6. Limits, what blocked nothing, and next

- **Nothing in the engine or self-play code blocked P0, and none was changed.** Two facts the
  solver relies on, both true today: a game stopped by an exception at a priority ask resumes
  there (`SeatRouter.take_priority` builds its menu without changing the state; the pause test
  checks it, and the search relies on the same); and a pack's setup (`ScenarioRunner`) resumes in
  `_play`. The builder sets the executor's name and creature-type pools as `games._setup_game`
  does (the pack runner does not: a `name` ask in a pack lists the world's cards).
- **The search's simulations see the pack's six filler cards per library** ("Library N", synthetic)
  when `determinize` shuffles the searching seat's own library: draws inside a simulation can be
  fillers. It touches the searched readout only, not the solver.
- **Information sets are the decider's view plus its own decisions.** Two opponent lines leaving
  the same view merge (conservative: the decider is held to one action). Hidden opponent actions (a
  scry, a face-down choice) would need more, and the first wave has none.
- **Next:** the runner on every gate checkpoint (PLAN_PLANNING §4); a real-engine strategy-fusion
  puzzle (a blind decision after the root that changes a value); grade 2 (dominant) when a puzzle
  outgrows exact solving (none did: the largest took 7,351 runs); generated variants for P2; E
  waits on memory v1, A-pay on the network paying.
