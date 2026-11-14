# 208 — r29: training both seats, an A/B from r28's update 685 (pre-registration, before any r29 game)

**Context.** r28 has been flat since v1. Its gates against v1 have stood at about 0.52 for 330
updates (199 §8). Its per-kind split at 685 shows every kind still moving along its own
advantages, with nothing drifting. So the signal each update carries is too small to move greedy
play.

The registered next lever (PLAN_CEILING §14.4; 205 §10) is more on-policy data per game: train
both seats of learner-against-learner games. That is `--p-self`, merged in 2651bad3 and smoked in
`reports/pself_smoke_2026-11-14/`. In the smoke, a self game gave 1.96× the trained decisions of a
game against a frozen version, for the same inference. Inference per trained decision fell by 41%.

Results are appended below and never edit §1-§5.

## 1. Design

- **Two arms, one init, one commit.** Only `--p-self` differs.
  - **r29a (control):** r28's flags, with `--p-self 0`.
  - **r29b (treatment):** the same flags, with `--p-self 0.55`.
- **Why a control arm, not r28's own trajectory.** Main differs from r28's pin 44a62d9 in several
  ways:
  - the engine wave on events (206) and gate rounds 5-10;
  - the verified pools, which grew: M21 from 263 to 275 records, M20 from 254 to 277.
  - Cards the init has never played could let any network gain against it, for reasons other
    than the lever.
- **Init:** r28's save at 685 (`runs/r28_looks/r28_u685.pt`, sha256 ed308ff2…), the latest
  network and flat since 350. It is both arms' v0.
- **Seed:** `--seed 29` in both arms.
- **Code:** the worktree `/home/sune/Desktop/MTG_AI-r29`, pinned at the launch commit (recorded in
  each run's `preregistration.json`).
- **Length: 5.5 machine-hours per arm.** Each arm is stopped at its first save after 5.5 hours
  running. A runs first, then B.
  - The lever's claim is learning per machine-hour, the unit 196 §9 used. B trains more decisions
    per hour, because less of its time goes to inference.
  - Per update the arms differ by design: about 2,200 games against about 1,300.
- **The flags (r28's, 199 §1):**
  - lr 2e-5, entropy bonus 0.004, `--steps 139264`, one epoch, clip 0.2, mb 4096;
  - the heuristic and past versions at 0.15 each, M20 mixed at 0.25, the verified pool;
  - gates every 25 updates on 1,000 deals at 0.55, `--save-every 5`, `--refresh-table`,
    `--extend-sets M20`.
- **Why the self share is 0.55.** With the heuristic at 0.15 and the past at 0.15, a self share of
  0.55 leaves the newest frozen version 0.15 of the jobs. At 0.7 it would get none after the first
  freeze. Self games then carry about 71% of B's trained decisions (1.10 of 1.55 seat-shares).
- **Why `--steps` stays 139,264.** The trainer's per-update settings stay r28's: decisions,
  minibatches, the learning rate per step. Throughput is set by the trainer either way. The cost
  is fewer independent outcomes per update in B.

## 2. Predictions

| # | Metric | Prediction | Falsifier |
|---|---|---|---|
| B1 | **Primary.** B's final save against A's, head to head: 1,000 deals 950,000-950,999, both seats, greedy, coherent decks, the verified pool | 0.53-0.58 | 95% upper bound below 0.50: self games make the network weaker |
| B2 | Each arm's final save against the init on deals 951,000-951,999, both seats; B − A paired by deal (`tools.selfplay.paired`) | +0.02 to +0.07 | B − A below 0, with its upper bound below +0.01 |
| B3 | Control: A's gates against its v0 | 0.47-0.54 each | any gate at 0.55 or more (A freezes v1): the code or the pool moves the network by itself, reported as its own finding |
| B4 | Cost, over each arm's updates 2-50 (gates left out) | A: interval 180-230 s, 1,900-2,500 games per update. B: train-bound, its interval within 15% of its `train_s`, 1,100-1,700 games per update | B trains fewer decisions per second than A |
| B5 | The mulligan per learner seat, pooled per block of 25 updates, both arms | 1.25-1.50 | any block above 1.60 |
| B6 | `win["self"]` in B's iter rows | 0.5 in every update | any other value: a bookkeeping fault |
| B7 | `kl` per update, median | A: 0.003-0.009 (r28's). B: at most 1.7× A's, since its batches may run over `--steps` | A outside 0.0015-0.02, or B above 2× A's |

**Why B1 may fail even if both seats help.** Two seats of one game share one result. B's updates
hold about 40% fewer independent outcomes than A's. If an update's signal is limited by outcome
noise, not by decisions, fewer games per update can cancel the extra decisions. Then B2 reads
the same, and per-update quantities show it: the explained variance `ev` and the advantages'
spread.

## 3. Kill criteria

Per arm, as r28's (199 §3), with three changes:
- **The mulligan is judged per learner seat:** above 1.80 in a 10-update mean. The guard runs from
  main at 2651bad3 or later, where it reads `learner_seats`.
- **K7 uses trained decisions per second:** below half of the arm's first hour. B plays fewer
  games per second by design.
- **A killed arm** ends that arm. The queue goes on to the next step, and the decision is made by
  hand.

Enforced while nobody watches:
- the memory floor (15 GiB), by the learner;
- the mulligan and the heuristic win rate, by the guards `mtg-r29a-guard` and `mtg-r29b-guard`.

## 4. Pre-flight, units, looks

- **Before each arm's first game,** from the pinned worktree:
  - `tools.selfplay.preflight <run> --games 200` (P1, P8, P9, P12);
  - `tools/check.sh` green at the launch commit;
  - `preregistration.json` written into the run directory.
- **One queue,** `reports/r29_2026-11-14/queue.sh`, as the transient unit `mtg-r29`:
  1. r28 stops at its next save. It ends there, before its read at 1,000 (199 §9).
  2. Arm A, then arm B, each as its own transient unit (`mtg-r29a`, `mtg-r29b`) with its guard.
  3. The reads: B1, then the two runs B2 pairs.
  4. B resumes as the main run.
- **Looks:**
  - update 3 of each arm: memory, speed, `kl`, the rows per batch against `--steps`,
    `throttled`, the share played by the previous weights, and learner seats per game (B: about
    1.55);
  - each arm's gates;
  - the reads at the end.

## 5. What each outcome means

- **B1 met:** training both seats makes the network learn faster per machine-hour. B goes on as
  the main run, and `--p-self 0.55` is part of every later run.
- **B1 neither met nor falsified:**
  - The lever is not shown at this length. B goes on anyway: it costs no more per decision and
    41% less inference.
  - The next lever is prepared: the own-decklist inputs, asked again on package decks (205 §10).
  - B's read at its update 300 (its window 201-300 against 1-100, as r28's) says whether it
    stalls too.
- **B1 falsified:** A goes on as the main run, and self games are not used. Then look for why,
  starting with forgetting against a moving opponent: the past and heuristic shares' training win
  rates in B against A.
- **B3 falsified:** the control learns by itself on the new code and pools. That is reported as
  its own finding: the init has not seen the cards added since 44a62d9. B1 and B2 still read as
  registered.

**Confounds, recorded before the data.**
- The arms run one after the other on a shared machine, so CPU load from other jobs differs. The
  load per arm is logged, and the reads are per machine-hour of each arm.
- Both arms start from a network trained on r28's code and pools. On main, `--refresh-table`
  changes 13 rows of its card table and adds 12 component tokens: gate rounds 5-10's
  `@once_per_event`, `role:arrange`, `EmblemSpec`, `PhasingEvent` and others. They start
  untrained, in both arms alike (seen in the start script's CPU smoke, 2026-11-14).
- B's batches may run over `--steps` when it is train-bound. Per decision, the optimizer steps
  are the same (one epoch, mb 4096). B training more decisions per hour is the lever itself.
