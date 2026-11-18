# 208 — r29: training both seats, an A/B from r28's v2 and a plateau test (pre-registration, before any r29 game)

**Context.**
- r28 learned +39 Elo over its init (+27 by update 350, +13 more by 1000), then went flat. Its 32
  gates against v2 at updates 1027-1802 average 0.4979 (sd 0.0105, se 0.0019; 199 §9).
- Its rate per machine-hour (red team, §6, row 1):
  - 1.31 Elo/h over updates 1-352;
  - 0.34 over 352-1000;
  - 0.00 over 1000-1825.
- Its per-kind split at 685 shows every kind still moving along its own advantages, with nothing
  drifting (199 §8). So the signal each update carries is too small to move greedy play.

The registered next lever (PLAN_CEILING §14.4; 205 §10) is more on-policy data per game: train
both seats of learner-against-learner games. That is `--p-self`, merged in 2651bad3 and smoked in
`reports/pself_smoke_2026-11-14/`. A self game gives about twice the trained decisions of a game
against a frozen version, for the same inference.

**Revised before any data (2026-11-17) after its red team (§6).** The first draft (86b9dc4e) read
the lever's effect from 5.5 machine-hours per arm and one snapshot per arm. At r28's best rate
that buys about +7 Elo, and the snapshot noise alone is about 5 Elo.

Results are appended below and never edit §1-§6.

## 1. Design

- **Init: r28's v2** (update 1000, frozen by its gate): its best certified network, with a known
  flat history of 800 updates against it. It is pinned as `runs/r28_looks/r28_v2.pt` (sha256
  d9f75295…, `reports/LARGE_FILES.sha256`) and is both arms' v0. It is not stronger than u685;
  the reason to use it is its certified, flat history.
- **Code:** one commit for both arms, the worktree `/home/sune/Desktop/MTG_AI-r29`.
  - It includes `--refresh-table` over every dealt set (5609b24b). From v2 that rebuilds 56 rows
    (13 of M21, 43 of M20 that were stale) and adds 22 component tokens, in both arms alike.
- **Flags:** r28's (199 §1), `--seed 29`, and per arm:
  - **A (control):** `--p-self 0`, with `--iters 120` as a backstop. A never goes on past the A/B
    unless §5 says so.
  - **B (treatment):** `--p-self 0.55`. That leaves the newest frozen version 0.15 of the jobs,
    and self games carry about 71% of B's trained decisions.
- **The A/B, matched by machine time.**
  - Each arm runs 5.5 machine-hours: A first, then B.
  - An arm's machine time is the sum of the intervals between its consecutive iter rows under
    1,200 s, plus the time from its unit's start to its first row.
  - The first save past 70%, 80%, 90% and 100% of the budget is kept as a snapshot (a70-a100,
    b70-b100), and the arm stops at the 100% snapshot.
  - Several snapshots, because a run's strength varies from save to save beyond the deals' noise
    (r28's snapshot sd, 0.0070 in score, registered here).
- **Then B goes on, alone.** It is the plateau test (B8) to its update 300, and the main run after,
  unless §5 decides otherwise.
- **What the lever can do.**
  - **Throughput:** B is train-bound at about 826 trained rows per second; A is collect-bound at
    about 639. So B trains about 1.29× A's decisions per machine-hour, on about 0.85× A's games.
    At r28's best rate that is worth at most about +2 Elo in 5.5 h, so B1 is a harm screen, not
    the plateau test.
  - **Signal quality:** a plateau breaks only if the signal changes. Self games sit at 50% against
    an equal opponent, and both the winner's and the loser's decisions are trained. B8 reads that,
    over 200 updates.
  - **Batch size is part of the lever:** B's batches run over `--steps` (1.3-1.65×), and its rows
    are one update stale (A's about 55%).

## 2. Predictions

**Confirmatory (three, with Holm's correction):**

| # | Metric | Prediction | Falsifier |
|---|---|---|---|
| B1 | **Harm screen.** B against A head to head: the mean of the 4 pairs (b_k against a_k), 1,000 fresh deals each (952,000-955,999), both seats, greedy, coherent decks, the verified pool, M21. Interval: ±1.96 × √(mean deal se² / 4 + 2 × 0.0070² / 4) | 0.49-0.52 | upper bound below 0.50: self games make the network weaker |
| B2 | **On L**, the plan's yardstick (PLAN_CEILING §14.4). v2, a70-a100 and b70-b100 are each rated against L's r27 v1 and r26 u1000, 1,000 fresh deals per opponent (1,130,000+), coherent decks (`tools.selfplay.rate rate reports/ceiling_window/pool_L.json`). B − A is the mean of B's 4 ratings minus A's. Each side's se is √(mean rating se² / 4 + 4.9² / 4) Elo | −7 to +14 Elo | upper bound below 0: B is weaker against the pool (a veto in §5) |
| B8 | **The plateau test.** B's mean gate against v2 over its updates 101-300 (8 gates), minus r28's 32 gates against v2 (0.4979 ± 0.0019) | +0.01 to +0.04, or B freezes a version before update 300 | upper bound of the difference below +0.01, with no freeze: training both seats does not break the plateau |

- B8's se is about 0.0042: √((0.0080² + 0.0070²) / 8) for B, with r28's 0.0019.
- A return to r28's rate over updates 1-352 would give about +0.027.

**Checks (not confirmatory):**

| # | Metric | Expected | Fails if |
|---|---|---|---|
| B3 | Control: A's mean over its 3 gates against v2 | 0.48-0.515 | lower bound above 0.498: the code or the pool moves v2 by itself. B8's comparator then becomes A's mean |
| B4 | Cost over each arm's updates 2-50 (gates left out). A: games per update and the interval. B: rows per batch, games per update, the interval. The ratio of B's to A's trained rows per machine-hour | A: 1,500-1,950 games per update, interval 200-235 s. B: 1.3-1.65× `--steps` rows, 1,000-1,900 games, interval within 5% of `upd_s`. Ratio 1.15-1.40 | the ratio below 1.05 |
| B5 | The mulligan per learner seat, pooled per block of 25 updates | 1.25-1.50 | any block above 1.60 |
| B7 | `kl` per update, median | A 0.0025-0.006 (r28 after v2: 0.0034-0.0046). B 1.8-3.5× A's (staler, larger batches) | B above 5× A's, or any update above 0.05 |
| S | Self games, from `train_rows.jsonl` | every self game has two learner seats, whose results are +1 and −1, or a draw | any other |

- `win["self"]` is not a prediction. It counts a draw (cap or stall, −1 for both seats) as no win,
  so it reads slightly under 0.5.

## 3. Kill criteria

Per arm, as r28's (199 §3), with these changes:
- **The mulligan is judged per learner seat** (above 1.80 in a 10-update mean), by the guard from
  the pinned worktree, which reads `learner_seats`.
- **The guard's heuristic win-rate criterion is off during the A/B.** It needs 100 updates, and
  the arms reach about 89 (A) and 76 (B). It arms in B's continuation.
- **K7 is replaced by a progress check in the queue:**
  - an arm with no new iter row for 30 minutes ends;
  - so does one restarted more than twice.
  - The queue logs it and goes on.
- **The memory floor** (15 GiB) is enforced by the learner.

## 4. Pre-flight, the queue, looks

- **Before the first game,** from the pinned worktree:
  - `tools/check.sh` green at the launch commit;
  - each arm's `tools.selfplay.preflight <run> --games 200` (P1, P8, P9, P12), run on the CPU
    before r28 stops;
  - `preregistration.json` written into each run directory.
- **The queue,** `reports/r29_2026-11-14/queue.sh`, as the transient unit `mtg-r29`:
  1. **r28 stops** at its next save and ends there (199 §9).
  2. **Arm A, then arm B**, each as its own unit with its guard (`start.sh`). The queue keeps the
     snapshots, counts machine time from the iter rows, runs the progress check, and logs
     `/proc/loadavg` and the busiest processes every 5 minutes (`load.log`).
     - Before each arm and each read, it refuses to go on while another learner process runs.
  3. **The reads:** B1's 4 pairs, then B2's ratings on L.
  4. **The decision** (§5), applied mechanically by `decide.py`, which logs why. A, B or nothing
     resumes as the main run.
- **No CPU-heavy agent work runs during the arms.**
- **Looks:**
  - update 3 of each arm: memory, speed, `kl`, rows per batch against `--steps`, `throttled`,
    the stale share, learner seats per game (B about 1.55), and S;
  - each arm's gates;
  - the A/B reads;
  - B's update 300 (B8), then 500 if B8 is undecided.

## 5. What each outcome means (decide.py applies the first two)

- **B1 falsified, or B2's veto:** self games are not used. A goes on as the main run, with
  `--p-self 0`.
- **Otherwise B goes on, provisionally.**
- **At B's update 300, by B8:**
  - **met, or a freeze:** training both seats breaks the plateau, and `--p-self 0.55` stays in
    later runs.
  - **falsified:** it does not, and the next run uses `--p-self 0`. The next lever is gate B, whose
    reopening rule is met:
    - r28's rate from launch to v2 is 38.7 Elo over 59.7 machine-hours, 0.65 Elo/h, so s* is 0.528
      (196 §9-§10; BACKLOG).
    - After gate B comes more decisions per optimizer step. The owner's "big batches" (D20) found
      no signal up to 2.65M decisions per step, against r28's about 2,700.
  - **neither:** B goes on, and B8 is read again at 500.
- **Why r29 runs before gate B.**
  - Its A/B costs about 11 hours, against gate B's 34.
  - B's continuation is itself the main run, so the GPU trains while the lever is read.
- **B3 falsified:** the code or the pools move v2 by themselves. That is reported as its own
  finding, and B8 compares against A's mean.

**Confounds, recorded before the data.**
- The arms run one after the other on a shared machine. Load is logged every 5 minutes. Gates and
  ladders cost A about 3% of its time, which B's idle workers absorb: a small edge to B.
- B's rows are staler and its batches larger. A shortfall in B could come from them rather than
  from the shared result.
- v2 has not seen 35 verified records added since r28's pin, the 56 rebuilt rows or the 22 new
  tokens. B trains 1.29× the decisions per hour on them. An exploratory read splits B1 and B2 by
  deals with and without a new card.

## 6. Red team (2026-11-17, one reviewer, on 86b9dc4e and the scripts at 4da972f1)

| # | Finding | Severity | Disposition |
|---|---|---|---|
| 1 | 5.5 h per arm cannot answer the question; B1's band (+21 to +56 Elo) is 3-8× r28's best rate | BLOCKER | Accepted. B1 is a harm screen (0.49-0.52). B8, B's gates against v2 over 101-300 against r28's 32, is the plateau test. The arms are matched by machine time from iter rows |
| 2 | One snapshot per arm, with intervals over deals only: 9% false "harm" at equal arms | BLOCKER | Accepted. 4 snapshots per arm (70-100% of the budget), and r28's snapshot sd of 0.0070 enters B1's interval (se 0.0068, MDE80 13 Elo). B2 is averaged the same way |
| 3 | The reads are not on L; B2's opponent, the init, is one A trains against (85% of its games) | MAJOR | Accepted. B2 is rated on L against r27 v1 and u1000 |
| 4 | B6 (`win["self"]` 0.5 in every update) cannot pass: draws count as no win | MAJOR | Accepted. Dropped as a prediction; S checks self games from `train_rows.jsonl` |
| 5 | B7's band for B cannot hold: B's rows are staler and its batches larger | MAJOR | Accepted. B 1.8-3.5× A's median; staleness and batch size are named confounds |
| 6 | §5 was predetermined, and "41% less inference" was P = 0.7's number (35% at 0.55, and idle when train-bound) | MAJOR | Accepted. §5 follows the intervals; B2 has a veto; the inference argument is deleted |
| 7 | The queue resumed B whatever happened; the smoke never ran r28's stop or the resume | MAJOR | Accepted. `decide.py` applies §5. Re-smoked with PAUSE=1 against a stand-in r28 unit |
| 8 | Machine time counted from the unit's state; no progress check; no `.venv` check | MAJOR | Accepted. Time from iter rows, the progress check, `--iters 120` for A, the `.venv` check |
| 9 | The next lever (own-decklist on package decks) made no sense; gate B's reopening rule is met | MAJOR | Accepted. Gate B is next if B8 fails, then more decisions per optimizer step |
| 10 | B4's bands were wrong for v2's era; its falsifier could not fire | MINOR | Accepted. Bands from r28's updates 1001-1825; the throughput ratio added |
| 11 | B3's falsifier needed +35 Elo | MINOR | Accepted. A's mean over its gates, against r28's 0.498 |
| 12 | The guard's heuristic criterion never arms in 89 updates; K7 is not in the guard | MINOR | Accepted. Said in §3; the progress check stands in for K7 |
| 13 | "Load is logged" was not implemented | MINOR | Accepted. `load.log` every 5 minutes; no CPU-heavy agent work during the arms |
| 14 | New cards are a confound in B1 | MINOR | Accepted as an exploratory split |
| 15 | Smoke and production unit names collide; another learner could share the GPU | MINOR | Accepted. Smokes use other names; `start.sh` checks the active unit's command; the queue refuses while another learner runs |
| 16 | 950,000-950,299 were already played (window 1's confirm16) | MINOR | Accepted. B1 at 952,000+, L at 1,130,000+ |
| 17 | "Big batches" happen by accident | MINOR | Accepted. B's batch size is part of the lever; more decisions per optimizer step is a registered candidate (§5) |
| 18 | Seven predictions, none named confirmatory; text predates 199 §9 | MINOR | Accepted. B1, B2 and B8 are confirmatory (Holm); the rest are checks; v2 throughout |

The reviewer agreed to the switch from u685 to v2 on four conditions. All four are met:
- the copy is pinned;
- INIT is changed everywhere;
- the bands are re-derived from v2's era;
- r28's 32 gates against v2 serve as B8's long control.

## 7. Added before any data (2026-11-17): a cycle check

The owner asked whether strategy cycles would show up as Elo gain.

**On the run's own measures, they would.**
- A gate plays only the newest frozen version.
- The run's ladder rates each new version only against random, the heuristic and its
  predecessor (`learner.py:1072-1073`). So it is a chain: v2 > v1 > v0 reads as steady gain even
  when v2 loses to v0.
- Self games make a cycle more likely than r28's mix did. That mix was 70% against one frozen
  version; B's is 55% against itself.
- The anchors stay: 15% each against older versions, the heuristic and the newest frozen
  version.

**B9 (a check, not confirmatory), read at each of B's reads (the A/B's end, 300, 500):**
1. **B's latest save is rated on L**, as B2. A cycle shows as gates rising while L stays flat.
2. **A round robin among all of B's frozen versions and v2**, 500 fixed deals per pair (deals
   1,140,000 onward). A later version scoring below 0.50 against an earlier one, beyond 2 se, is
   flagged as non-transitive.

**If B9 flags a cycle:** the remedy is prioritized past opponents (BACKLOG), registered as a
change before it is used.

## 8. Added before any data (2026-11-17): how the queue reads §3 and §5

- **An arm ended by the progress check counts as killed, like a guard stop.** That covers 30
  minutes with no new iter row, or more than 2 restarts. The check stands in for K7, a kill
  criterion (§3). Otherwise a B that crash-loops would leave no snapshot, no read could veto it,
  and it would still resume as the main run. In `decide.py` this is `KILLED`.
- **The decision starts the main run once** (`resume.done`). A later run of the queue does not
  restart a main run its guard has since stopped. After a reboot, `start.sh` resumes it by hand.
- **The scripts were smoked end to end with PAUSE=1** (2026-11-17), against a stand-in r28: both
  pre-flights, r28's stop, both arms' snapshots and stops, B1's pairs, B2's ratings on L, the
  decision and the resume. Two more smokes: an arm that cannot start, which ended by its restart
  count, and a queue restarted mid-arm, which kept its machine time. The learner's resume fix
  (d8f00365) came out of this work.
- **Before launch:**
  - the worktree `/home/sune/Desktop/MTG_AI-r29`, pinned at the launch commit, with its `.venv`
    link;
  - each arm's `preregistration.json`;
  - `tools/check.sh` green at that commit.

## 9. Before launch (2026-11-17, before any r29 game)

r29 waited from 2026-11-17 on the owner's order: the sets completed and a bug hunt first (209, 211,
212). Everything below changed after the red team. It is the same for both arms and was recorded
before any r29 game.

**What changed.**
- **The engine.** The bug hunt's fixes (212), merged as E2 68d59bf2, E1 c80f45f7, round 13
  bb9932fa, G1 72ef87d2 and G2's merge:
  - dead tokens cease;
  - per-object state ends at a zone change;
  - entering counters are journalled;
  - the layer order and timestamps;
  - costs read control;
  - the attacker divides combat damage, through a new "divide" ask;
  - conditional mana is priced, and each mana ability of a permanent pays;
  - targets are priced together;
  - a negative number counts as 0;
  - a prevention is scoped to what it names;
  - a spell moved off the stack leaves it;
  - "exiled with" reads the life the exile arrived in.
- **The IR.** Round 12 (one quantity comparison, 8d0bf62e) and round 13 (PERMIT and REPLACE).
  Verification wave 4 re-verified the M21 and M20 stamps round 12 changed.
- **The network's inputs.**
  - N1/N2 (210 §8): every token pooled, no card name a token. v2 reads bitwise as saved.
  - T1's option encodings: an ability as a target, and a source's several triggers. v2 is bitwise
    on every other ask.
- **The harness (T1, 5411f386).**
  - A failed gate is committed before it is logged.
  - A resume keeps the run's own table.
  - Gate blocks move with `--seed`, so r29's gate deals are not r28's.
  - A batch takes games in the order they were issued.
  - A hung game is voided after 600 s.
- **The heuristic (T1).** It aims each target by what the effect does to it, and scores
  0.533-0.540 against the old heuristic. It is 15% of the training mix and the rating anchor.
- **The pool.** The verified cards at the launch commit:
  - M21: 274 of 285;
  - M20: 283 of 329;
  - FDN: 261 of 517, not dealt.
  The table refresh at start rebuilds rows and adds tokens, logged in the run's `refresh_table` row.

**Known open faults at launch.** Both are rare in M21/M20 games. Both are fixed before the FDN
segment below:
- **Counters on a card off the battlefield.** A counter put on a card that has already left the
  battlefield stays on it when it returns to the battlefield (CR 122.2, 400.7; stronger). The soak
  flags the placement in about 5% of random M20 games; the return needs Brought Back, Gravewaker or
  Cavalier of Night after it.
- **Battlefield endpoints read the zone owner.** A ZoneChangeEvent endpoint on the battlefield
  scoped to a player reads the zone owner, not the controller (`binding._zone_matches`; weaker):
  - a stolen enchantment leaving gives Starfield Mystic no counter;
  - a card entering under a non-owner's control misses its own enters trigger.

**What it means.**
- **B1 and B2 are clean.** B1 (A against B) and B2 (both on L) compare arms on the same code.
- **B8 is exposed.** It compares B's gates against v2 with r28's 32, which were played on the old
  engine, pool and gate deals.
  - v2 never trained on the divide ask or the changed cards. A network trained on the new code may
    beat v2 a little for that alone.
  - B3 is the registered guard. With A's 3 gates (se about 0.0046) it trips only on a shift of
    about 0.009, while B8's threshold is +0.01.
- **Amendment, before any data.** B8's comparator is the larger of two numbers: r28's 0.4979, and
  A's mean over its gates against v2. B must clear both.
  - The shift a new ask and changed cards give should be learned early, so A's gates carry most of
    it.
  - Taking the larger only makes B8 harder to meet.
  - The cost is power: B8's se rises to about 0.0062 when A's mean is the larger.
  - `decide.py` does not read B8, which comes at B's update 300, so no script changes.
- **FDN joins after B8.** The A/B and B8 deal M21 and M20, as r28 did and as registered. When B8
  is read (update 300, or 500), the main run goes on as its own segment, under a short
  registration of its own:
  - FDN is added (`--extend-sets FDN`, `--refresh-table`);
  - the engine fixes merged by then come in, the two open faults above among them.
  This keeps B8 readable, and puts FDN, the third set the owner wants played, into training within
  about a day.
- **No CPU-heavy agent work runs during the arms** (§4). FDN's remaining verification (waves 3 and
  4, nine batches) resumes after the A/B.
- **Smoke.** `start.sh`'s start and resume were smoked on main's code at 1fb4463f: CPU, 2 updates,
  then a resume to 3, with no refusal.

## 10. Launch 1 failed (2026-11-17 20:21-22:25): no update in either arm

**What happened.** The queue started at c13165e9, and both pre-flights passed. Neither arm then
wrote an iter row.
- **Arm A.** The learner refreshed its table (155 rows, 36 tokens) and froze v0. After that its
  progress rows read `buffer 0 of 139264` for 30 minutes.
- **The games.** 3,905 training games finished and were logged (`train_rows.jsonl`), but none of
  their rows reached the buffer. Game ids ran to 35,068, against 3,905 finished.
  - That is 2.2 games per second, against r28's about 8.
  - The unit used 8h50m of CPU in those 30 minutes.
- **The stops.** The progress check (§3, §8) ended arm A, then arm B, which did the same. The queue
  went on to the reads with no snapshots. It was stopped by hand at 22:25, during B2's rating of
  the init.

**What it means.**
- No r29 training update happened, so no r29 result exists. The registration stands, and the
  relaunch is still before any data.
- The failed attempt's directories are kept for the diagnosis, renamed with `_failed1`.
- The cause is under investigation. The suspect is the release of finished games in issue order
  (T1, 5411f386): a CPU smoke at small scale passed, and the GPU probe before T1 ran.
- A relaunch needs:
  - the fix, with a GPU smoke at r29's real flags that reaches 2 iter rows;
  - fresh run directories.

**The cause** (found 2026-11-17 23:10):
- **The fault.** T1 wrote a worker slot's last line as `outbox.append(self._play(job))`, and
  Python reads the outbox before the game runs. The worker sends and replaces its outbox whenever
  any game ends, so the result of every game that outlived such a send was lost.
- **Its size.** About nine in ten results were lost (3,317 played, 395 received). The lost games
  held `_release` behind them for good.
- **What it spared.** Only the short games survived, so a batch that had filled would have been a
  biased sample.
- **Evaluations.** The same fault made any evaluation with more than one slot per worker unable to
  finish. That is why the queue's B2 runs hung.
- **The fix** computes the result before appending it (`tools/selfplay/actor.py`). The test
  `test_every_game_a_worker_plays_comes_back_once` fails on c13165e9.
- **The smokes.** A GPU smoke with arm A's real flags wrote two iter rows: 206.7 s an update,
  about 1,650 games, 12.5 games a second (r28's median 213.8 s, 1,751). An arm B smoke wrote two as
  well.
- **The 2.2 games a second** of launch 1 were the survivors of about 19.8 played.
- **Why the CPU smoke missed it.** It ran two slots and 2,048-row batches, so a long game rarely
  outlived a send.
- **One number to watch in launch 2:** the learner's asks answered by the fallback (`overflow`) ran
  at about 0.08 a game in the smoke, against r28's 0.01.

**Launch 2:** from the commit that adds this paragraph, with fresh run directories. The rest of the
registration is unchanged.

## 11. The A/B's reads (2026-11-18 10:31-11:27, by decide.py; appended, §1-§10 unedited)

- **The arms:**
  - **A:** 103 updates, ended by its budget at 04:50. Its gates against v2: 0.5048, 0.4978,
    0.5195, 0.4995.
  - **B:** about 125 updates, ended by its budget at 10:31. Its gates against v2: 0.4973, 0.5082,
    0.5333, 0.4993.
- **B1, the harm screen** (B against A, 4 snapshot pairs, 1,000 deals each): 0.4946 [0.4823,
  0.5069], se 0.0063. Not falsified.
- **B2 on L:** B minus A is −3.9 Elo [−13.0, +5.1], se 4.6. No veto.

  | Network | Elo on L |
  |---|---|
  | init (r28's v2) | 633.2 |
  | a70, a80, a90, a100 | 634.2, 638.5, 635.7, 642.4 |
  | b70, b80, b90, b100 | 632.5, 635.5, 630.8, 636.3 |

- **Decision (§5):** B goes on as the main run (`--iters 6000`), resumed at 11:27. B8 is read at
  its update 300.
- **What it says beyond the registration:** neither arm moved off its init within 5.5
  machine-hours (A's mean 637.7, B's 633.8, the init 633.2, every se about 4). r28's plateau
  (199 §9) holds under both seats' training.
- **The planning readout of the same snapshots** (KNOWLEDGE/2026-11-18/214): no network passes
  both twins of any proven puzzle pair. Each plays one habit per kind of decision. Arm B moved
  from never countering to always countering.
