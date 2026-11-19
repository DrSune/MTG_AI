# 217 — r30: the main line's long self-play on the corrected code (registered 2026-11-20, before any r30 data)

**The owner, 2026-11-20:** "I want a longer self-play to run, without too much hassle before you
start it. It should be set up well, but dont overfocus on finishing sets first etc. ... make sure
training is on the right track or steer it."

## 1. Where r29 stands (read 2026-11-20 00:30)

- **B8 at update 500**, re-read as 208 §12 registered: B − A = −0.0007, 95% [−0.0124, +0.0109],
  over B's 16 gates against v2 (101-500) and A's mean of 0.5054.
  - Undecided again, so by the rule registered before this data: **not met**. Training both seats
    does not break the plateau within 500 updates.
  - `--p-self 0.55` stays: B1 and B2 showed no harm, and B trains more rows per machine-hour.
- **Since then:**
  - B ran to update 943, about 36 machine-hours past the A/B.
  - Its 18 gates against v2 over 503-928 average 0.508. A's mean was 0.5054 on the same deals.
  - It has frozen nothing.
  - Its training win rate against the heuristic is 0.67-0.68 per 200-update block, flat.
  - It is healthy: 0 voids, `kl` 0.004-0.005, entropy rising slowly from 0.22 to 0.25, no guard
    trip.
- **On its pinned code** (60f0913f), B still forces about 63 answers an update through the option
  fallback (KNOWLEDGE/2026-11-18/213), and plays the engine faults E3, W1 and W3 have since fixed.

**The steer.**
- Continue the main line, on main's corrected code, as a new segment. Same flags, same pools.
- 208 §12 registered gate B as the next GPU job. The owner chose a long self-play run instead, so
  gate B stays the registered lever that §4's 48-hour read can call.

## 2. What r30 is, and is not

- **It is:** the main line continued: init r29 arm B's save at update 945
  (`runs/r29_looks/r29b_u945.pt`, pinned in `reports/LARGE_FILES.sha256`). It is the M21+M20
  segment 208 §9 registered for after B8. FDN waits, by the owner's order of 2026-11-18.
- **It is not** PLAN_LONG_RUN's P1 run. The planner's A/B, memory, the value package and the league
  are not built yet. Their builds and the cleanup plan (docs/PLAN_CLEANUP.md) go on beside r30, and
  their multi-arm A/B starts from r30's checkpoint when ready.

**What changes against r29 B: the code only, every change a fix, none a tuning.**
- Zero fallback (213): every option is offered, and no answer is forced.
- Every public card is an entity: no entity caps.
- The turn-so-far columns (69b3f5ad). They start at zero weight, so the init computes what it did
  (`test_r28s_v2_computes_bitwise_what_it_did_where_no_option_changed`).
- Engine waves E3, W0 and W1 (KNOWLEDGE 215): the reachable stronger-than-printed faults.
- W3: state triggers, extra triggers, honest reveal rows.
- Rounds B3 (copies) and B12 (the opening hand, prohibitions, the game's end).
- The rails, counted every update: TURN_CAP 125, 30 actions a step.
- Stamps through verification wave 7.

**The pools** (`--pool verified`):
- M21 268 and M20 278 cards.
- W3's 36 re-baked cards and Nine Lives are out until a re-verification wave stamps them. Their
  play is unchanged except for Nine Lives, both Mazemind Tomes, Sanctum of All and Alpine
  Houndmaster. They join at a pause with `--refresh-table`, recorded here as a pool change.

**The same as r29 B:**
- every flag of `reports/r29_2026-11-14/start.sh` arm B: PPO at lr 2e-5, γ = λ = 1, ent 0.004,
  139,264 steps, `--p-self 0.55 --p-past 0.15 --p-heuristic 0.15`, coherent decks, M20 at 25%,
  gates every 25 updates against the newest frozen version at 0.55;
- `--seed 30`, so the deals are new;
- `--iters 6000`;
- the planner is off.
- **Why nothing else changes:** the owner asked for no hassle, and each other lever is an A/B of
  its own (PLAN_LONG_RUN's calendar).

## 3. Before launch

- r29 B is stopped right after its save at update 945. Its directory is kept (`runs/selfplay/r29b_pself055`).
- **The init.** The save is copied to `runs/r29_looks/r29b_u945.pt` and pinned.
- **The code.** It runs from the worktree `/home/sune/Desktop/MTG_AI-r30`, pinned at the commit that
  holds this note and `reports/r30_2026-11-20/start.sh`.
- **The smoke is the launch itself,** watched (2026-11-17's lesson: a GPU run with the real flags,
  read to two iter rows). If update 1 fails, the run directory is removed, the cause fixed, and the
  launch repeated.
- **Checks at update 1-2:**
  - `voids` 0;
  - no `overflow` field;
  - `kl` under 0.02;
  - memory above the floor;
  - games and learner seats near r29 B's (1,100-1,200 games, about 1,750 learner seats an update).

## 4. Reads and rules, registered now

**Every update, by the guard:**
- the mulligan per learner seat at most 1.80, over a 10-update mean;
- the heuristic win rate no more than 0.05 under its first 50 updates;
- the rails counted (`turn_caps`, `act_caps`, `quarantines`), target 0;
- voids 0.

**Every 25 updates:** a gate against the newest frozen version (v0 = the init). A freeze at 0.55
with its lower bound above 0.50.

**The 48-machine-hour read**, PLAN_LONG_RUN's stall rule adapted to the owner's choice. Read at the
coordinator's next wake after 48 machine-hours:
- **Measured:**
  - L on coherent decks (`tools.selfplay.rate`, pool L, 208's B2 method): the newest snapshot
    minus the init;
  - the puzzle suite's twin-consistent pair count (`tools/puzzles/runner.py`).
- **Prediction:** L −5 to +15 Elo over the init. The fixes are corrections, not levers. r29 was
  flat for 36 machine-hours on the same flags.
- **Stalled when both hold:** L is below 2 standard errors above the init (about 11 Elo), and the
  pairs have not risen.
- **Then:**
  - the coordinator reports to the owner and proposes the next lever: gate B, the league, or the
    multi-arm A/B if its builds are ready;
  - r30 keeps training until the owner decides, since the owner wants self-play running.

**Stop the run when:**
- any update's `kl` exceeds 0.05;
- a non-finite loss appears;
- the guard trips;
- voids exceed 1% of games;
- `turn_caps` exceed 0.5% of games: a rail binding means a loop the stall rule misses, or a regressed
  engine.

## 5. Confounds, said before the data

- **AdamW's moments restart at the init:** the optimizer state is not saved yet (PLAN_LONG_RUN item
  6). 198 §2 measured no shock at a resume (`kl` 0.0037-0.0086).
- **The pool is smaller by W3's re-bakes until they are re-verified.** That is about 12 M21 and 8
  M20 cards, Duress and Cultivate among them.
- **New inputs start at zero weight.** The init's function is preserved at update 0, and learning
  to use the inputs takes updates. An early dip in the heuristic win rate, within the guard's 0.05,
  is not a fault.
- **The gates' opponent changes:** v0 is now r29 B's save, not r28's v2. Read gates against v0 as
  progress over the init, and L as progress against the frozen pool.

## 6. Launch (2026-11-20 00:35; appended, §1-§5 unedited)

- r29 B stopped right after its save at update 945 (00:35:00). r30 started at 00:35:48 from the
  worktree pinned at 979389a9 with `reports/r30_2026-11-20/start.sh`. Its guard runs as
  `mtg-r30-guard`.
- **The launch checks of §3, all met at updates 1 and 2:**

  | Check | Update 1 | Update 2 |
  |---|---|---|
  | `voids` | 0 | 0 |
  | `overflow` field (zero fallback) | absent | absent |
  | `kl` | 0.0022 | 0.0028 |
  | `ent` | 0.230 | 0.236 |
  | `ev` | 0.326 | 0.333 |
  | Games / learner seats | 1,181 / 1,801 | 1,175 / 1,818 |
  | Seconds an update | 180 | 162 |
  | Lowest memory (floor 15 GiB) | 50.7 GiB | 50.0 GiB |
  | `turn_caps`, `act_caps`, quarantines | 0 | 0 |

  There were no errors in `runs/selfplay/r30_main.out`. The rows of r29 B's last updates were alike:
  1,159 games, 160 s, `kl` 0.005.
- **Training win rates:** against the heuristic 0.72 and 0.66; against v0 (the init) 0.49 and 0.52.
  The heuristic ladder rates the heuristic 506 against random's 0.
