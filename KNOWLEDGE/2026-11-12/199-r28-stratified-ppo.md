# 199 — r28: r27 on the fixed trainer, from r27's v1 (pre-registration, before any r28 game)

**Context.** r27's optimizer steps were length strata, and its mulligan ran away (198). r27 ended
at update 165 (191 §8). r28 asks two questions:
- does the fix keep the mulligan where v1 had it?
- does it let the network learn past v1, where r27 stalled for 90 updates?

Results are appended below and never edit §1-§4.

## 1. Configuration

- **Code:** main at the launch commit (in `preregistration.json`), run from the worktree
  `/home/sune/Desktop/MTG_AI-r28`. Against r27's d6dcdff, two things change:
  - **the fix (f83f4db):** every optimizer step is a stratified sample of the batch;
  - **the bug hunt's fixes (197):** among them the engine's END_TURN, the trigger-loop tripwire
    in the game loop, and an empty COUNTER_SPELL resolving as a no-op. They are rare rules
    situations, recorded as a confound.
- **Init:** r27's `v1.pt` (update 75, the gate's snapshot; sha256 ceb19ed0…).
- **Flags:** r27's (191 §2), except `--seed 28` (fresh deals)
  and the run directory `runs/selfplay/r28_stratified_ppo`.
  - lr 2e-5, entropy bonus 0.004, 139,264 decisions per update, one epoch, clip 0.2;
  - the heuristic and past versions at 0.15 each, M20 mixed at 0.25, the verified pool;
  - gates every 25 updates on 1,000 deals at 0.55.
- **Opponents.** r28's v0 is v1's weights, so its frozen opponent starts as r27's was from update
  77. One difference: r27 also met u1000 as a past version, and r28 has no past version until
  it freezes one.

## 2. Predictions

| # | Metric | Prediction | Falsifier |
|---|---|---|---|
| R1 | The learner's mulligan declarations per game, mean of each block of 25 updates to 150 (r27 after v1: 1.38, 1.39, 1.38, then 1.70 over 151-165) | 1.25-1.45 in every block | any block above 1.50: the forgetting (198 §4) still drives the mulligan, and a remedy aimed at it is the next registered change |
| R1b | p(mulligan) at 7 cards with 3-4 lands on update 165's 3,857 declarations (`timeline.py`), r28 at update 100 (v1 0.081, r27 at 165 0.264) | 0.05-0.12 | 0.18 or more |
| R2 | The mulligan's KL per update over act's, median over updates 1-100 (r27: 6.8) | 1.5-3.5: the impulse is gone (one update from r27's 165 on stratified steps: 2.0-2.6) | 5 or more: the mulligan still moves in impulses |
| R3 | Gates against r28's v0 (= r27's v1) at updates 25, 50 and 75, their mean minus r27's gates against v1 at 100, 125 and 150 (0.511; the difference's SE ~0.006) | +0.01 to +0.04: r27's stall after v1 was the defect's, at least in part | below +0.01: the fix does not speed learning beyond the mulligan |
| R4 | The cost, over updates 2-50: the update's own time (`train_s`, r27 110 s), the median interval between updates with gate intervals left out (r27 172 s), the share of a batch played by the previous weights (r27 0.40) | `train_s` 130-175 s; interval 165-210 s; previous weights 0.6-0.95 | interval above 250 s |
| R5 | `kl` per update (r27 after v1: 0.0054) | 0.003-0.009 | below 0.0015 or above 0.02 |
| R6 | Minimum MemAvailable | above 35 GiB | below 30 GiB |

**Why R3 may fail even though the fix is right.** The defect hit kinds confined to narrow
length bands: the mulligan, the bottom choices, the first turns and the longest late-game
positions. Most decisions span many lengths, and those spread over most minibatches even before
the fix. If r27's stall had other causes (the opponent pool, the noise of one-result credit), R3
fails while R1 and R2 hold.

## 3. Kill criteria

- As r27's (191 §5):
  - K1, an engine crash;
  - K4, `ev` below 0 for 3 updates;
  - K7, games per second below half of the first hour's;
  - the memory floor (15 GiB);
  - non-finite steps in 3 consecutive updates;
  - the training win rate against the heuristic, over any 50-update window, more than 0.05 below
    its mean over updates 1-50.
- **New:** the learner's mulligan declarations per game above 1.80 in a 10-update mean. That is
  r27's runaway level (198 §1).
- **Enforced while nobody watches:**
  - the memory floor, by the learner;
  - the mulligan, by the guard unit `mtg-r28-guard`, which reads the last row per update every
    10 minutes and stops `mtg-r28` with a logged reason. It is a safety rail, not a tuning
    knob, and it ends with the run.

## 4. Pre-flight, unit, looks

- **Pre-flight**, from the worktree at the launch commit:
  - `tools.selfplay.preflight runs/selfplay/r28_stratified_ppo --games 200` (P1, P8, P9, P12);
  - `tools/check.sh` green at that commit;
  - `preregistration.json` written into the run directory before the first game.
- **Unit `mtg-r28`:** r27's unit text with the worktree, the init, the seed, the run directory
  and the log `runs/selfplay/r28_stratified_ppo.out`.
- **Looks:**
  - at update 3: memory, speed, `kl`, the per-kind rows, R2's ratio so far;
  - at 25, 50 and 75: the gates; R3 is read at 75;
  - at 100: R1b and R2;
  - at 150: R1;
  - registered reads at 400 and 1,000 (windows 301-400 and 901-1000 against 1-100, and the gates
    ending there).
- **Gate B** starts after the read at 400 (196 §8). Reads go by update count, so its pause
  changes nothing in them.

## 5. Results

**A correction to §2, made before any r28 update (2026-11-12 16:55).** R2's reference was
"one update from r27's 165 on stratified steps: 2.0-2.6". The three orders actually gave the
mulligan's KL over act's as 2.05, 1.53 and 2.60, so the range is 1.5-2.6 (198 §3's ablation).
R2's prediction (1.5-3.5) and falsifier (5 or more) are unchanged.

**Launch** (2026-11-12 16:32:16).
- r28 started as the transient unit `mtg-r28`, because writing a persistent unit file was
  refused here. `reports/r28_2026-11-12/start.sh` holds its command; from `--gamma` on, its flags
  are identical to r27's unit, checked by diff.
- Pre-flight passed at 44a62d9 (P1, P8, P9, P12), and `preregistration.json` was written before
  the first game.
- The init is `v1.pt`, still stamped 77 (its weights are update 75's, 197). The table refresh
  changed 0 rows and M20 added 0 cards. v0 was frozen at 16:32:32.
- The guard runs from main at ff18b5c (a monitor; the training code stays pinned).

**The look at update 3** (16:44; the last row per update):

| Update | 1 | 2 | 3 | Prediction |
|---|---|---|---|---|
| `kl` | 0.0043 | 0.0056 | 0.0056 | R5: 0.003-0.009 |
| The mulligan's KL over act's | 3.22 | 2.08 | 1.80 | R2: median over 1-100 in 1.5-3.5 (r27: 6.8) |
| `train_s` | 156 | 174 | 168 | R4: 130-175 |
| Optimizer steps / micro-batches | 48 / 96 | 50 / 100 | 50 / 100 | — |
| Share of the batch played by the previous weights | 0.58 | 0.64 | 0.26 | R4: 0.6-0.95, read over 2-50 |
| `ent` / `ev` | 0.266 / 0.403 | 0.264 / 0.384 | 0.261 / 0.346 | — |
| Training win rate against the heuristic / frozen (v0 = v1's weights) | 0.697 / 0.513 | 0.710 / 0.508 | 0.709 / 0.488 | — |
| Lowest MemAvailable | 56.4 GiB | 53.3 | 53.0 | R6: above 35 |

- No void game and no non-finite step.
- **The ladders** on the fixed engine (500 deals each, both seats, greedy):
  - the heuristic against random 0.916 [0.900, 0.932], r27's number on the same deals;
  - r28's v0 (r27's v1 weights) against random 0.986 [0.979, 0.993] and against the heuristic
    0.753 [0.729, 0.777]. r27's v1 had 0.986 and 0.752.
  - The bug hunt's engine fixes moved one game in 1,000.
  - Elo: random 0, heuristic 437.8, v0 640.6.
- **The mulligan, pooled:** 8,472 declarations over 6,586 games in updates 1-3, 1.29 a game.
  v1's rate was about 1.3.
- **Per update the ratio swung** 0.90, 1.33 and 2.27, because the games an update counted swung
  at the start (3,280, 2,114 and 1,192).
  - So R1's block means are read pooled: declarations over games in the block.
  - The guard pools too (ff18b5c). Its first version averaged per-update ratios, which inflate
    exactly when games swing. Replayed over r27, the pooled guard still stops at update 169
    (1.850).

**Does the mulligan read whether its lands can cast its spells?** (The owner's question,
2026-11-12; `reports/mulligan_colors_2026-11-12/colors.py` on update 165's batch: 2,028 7-card
hands whose lands are all basic.)
- **Yes, and it reads more than the land count.** Among 3-land hands, v0's p(mulligan) is
  0.032 when every spell is castable by the lands' colours, 0.355 when only some are, and 0.83
  when none are (6 hands). 2- and 4-land hands show the same order.
- **The counterfactual, paired by hand.** 492 3-land hands whose lands cast every spell had only
  their lands' identities changed:
  - "mono": every land becomes the deck colour fewer spells use, a hand the deck can deal. v0's
    p(mulligan) rose 0.032 → 0.461 (+0.43 ± 0.015, raised in 94% of hands).
  - "off": every land becomes a colour no spell uses. It rose to 0.697 (+0.66 ± 0.013, raised in
    every hand).
- **Every network shows it:**
  - v1: +0.43 and +0.67;
  - r27 at 165: +0.65 and +0.73, on its higher base rate;
  - r28 at update 10 (its `last.pt`): +0.38 and +0.59, base 0.023.
- **Open:** v0 throws back 36% of 3-land hands where only some spells are castable. Whether
  that is too eager needs the cost of keeping them, which this check does not measure.

## 6. Registered after launch, before its data (2026-11-12 17:58, r28 at update 20)

The red team (PLAN_CEILING §15) found a bias in R3. `curriculum_job`'s share for past versions
(0.15) falls through to the newest when only one version exists (`learner.py:537-540`). So r28
plays 85% of its games against its v0, the network R3's gates test against. After v1, r27 played
70% against v1, 15% against u1000 and 15% against the heuristic. That favours r28 in R3. R3 is
still read as registered; R3b reads the same question without that bias.

| # | Metric | Prediction | Falsifier |
|---|---|---|---|
| R3b | r28 at update 75 against r27 at update 165 (`runs/window2/r27_latest.pt`), head to head. Both trained from v1's weights, for 75 and 88 updates. 1,000 deals 930,000-930,999, both seats, greedy, coherent, the verified pool, run from r28's worktree (44a62d9) | 0.51-0.56 | 95% upper bound below 0.50: the fixed trainer's network is weaker than the flawed one's at matched training |

- **Where r28's weights come from.** Its `last.pt` at update 75, copied as soon as the save
  lands (`runs/r28_looks/r28_u75.pt`).
- **When it runs.** In a pause of r28 of about 5 minutes, after its gate at 75 is read. A pause
  changes nothing in the reads, which go by update count.
- **What it cannot tell apart.** r27's network carried its mulligan drift (198), so a pass means
  the fixed trainer gave the stronger network. It does not say how much of the gap is the
  mulligan.

**The looks at 25, 50 and 75** (2026-11-12 17:55-21:07; `reports/r28_2026-11-12/look.py`, the
last row per update; each gate 2,000 games against v0 = r27's v1 weights, both seats, greedy):

| Updates | 1-25 | 26-50 | 51-75 | Prediction |
|---|---|---|---|---|
| The mulligan per game, pooled | 1.326 | 1.288 | 1.278 | R1: 1.25-1.45 in every block to 150 |
| Gate against v0, at the block's end | 0.521 [0.507, 0.535] | 0.517 [0.502, 0.532] | 0.5165 [0.501, 0.532] | R3 |
| Training win rate against the heuristic / v0 (sampled play) | 0.715 / 0.506 | 0.728 / 0.515 | 0.730 / 0.520 | — |
| Entropy | 0.255 | 0.248 | 0.243 | — |

- **R2 so far:** the mulligan's KL over act's has a median of 2.36 over updates 1-75 (quartiles
  1.87 and 3.04, highest 4.99). It is read at 100.
- **R4 holds** (updates 2-50):
  - `train_s` median 167 s (160-180);
  - the interval between updates median 205 s (47 intervals, gate updates left out);
  - the previous weights' share of a batch median 0.63 (lowest 0.07, at update 26).
- **R5 holds:** `kl` median 0.0064 (0.0037-0.0080).
- **R6 holds:** lowest MemAvailable 44.2 GiB.
- No void game, no non-finite step, no KL stop.

**R3 is falsified.**
- The three gates' mean is 0.5182. r27's three gates against v1 averaged 0.5107. The difference
  is +0.0075 (SE about 0.006), below the +0.01 floor.
- §6's bias favours r28 (85% of its games against v0), so the true difference is smaller still.
- As §2 allowed: the fix removed the mulligan's impulses (R1 and R2 hold), but r27's stall after
  v1 was not the defect's.
- In both runs the network stands about 0.51-0.52 against its init 25 to 75 updates later, with
  no trend from 25 to 75.
- The training win rate against v0 rises, 0.506 to 0.520. That is sampled play, and it is not a
  strength measure: the learner's entropy fell 0.255 to 0.243, while v0 samples as it always
  did. The greedy gates are the read.

**R3b: inside the band, not decisive.**
- r28 at update 75 against r27 at update 165: 0.513 [0.495, 0.531], 2,000 games (deals
  930,000-930,999, both seats; 21:05-21:07, r28 paused for 3 minutes).
- The falsifier (upper bound below 0.50) is not met, and the estimate lies inside 0.51-0.56.
- The interval holds 0.50. At matched training, the fixed trainer's network is not shown to be
  weaker than the flawed one's, and not shown to be stronger.

**What R3 means for the plan.**
- The question after v1 is the rate of learning, not the mulligan.
- Gate B's break-even rule (196 §9) takes r28's rate at update 400. Its gates at 100-400 are
  that rate's data.
- The per-kind look at 100 (`kinds_split.py`: each kind's own learning against the drift the
  rest of the batch causes on it) reads where an update's signal goes. It is PLAN_CEILING §15's
  "signal before direction" applied to the trainer itself.

## 7. Registered before update 100's data (2026-11-12 21:20, r28 resumed from its save at 75)

**The per-kind split** (PLAN_CEILING §14.2, instrument 2; §14.4, retention).
- `reports/r28_2026-11-12/kinds_split.py` runs on one on-policy batch of r28's update-100 weights
  (`collect.sh runs/r28_looks/r28_u100.pt runs/r28_looks/c100 2800`), in a pause of r28 after
  its gate at 100 is read.
- It measures each kind's alignment twice: after a full update, and after an update without that
  kind's rows (the drift the rest of the batch causes). The alignment is mean(A·Δlog p) over
  mean(A²) on the kind's decisions.
- Each figure carries a bootstrap SE over the kind's decisions. It does not cover an update's own
  randomness: this is one batch and one update.
- Kinds with fewer than 500 probe decisions are reported, not scored.

| # | Metric | Prediction | Falsifier |
|---|---|---|---|
| K1 | Each kind's alignment after the full update | positive beyond 2 SE for every kind | a kind at or below 0: the update does not teach that kind along its own advantages |
| K2 | The mulligan's alignment after an update without its rows | negative beyond 2 SE: the drift found by 198 §3 (variant E) survives stratification, while the mulligan's own rows hold it (R1) | within 2 SE of 0, or positive |
| K3 | The other kinds' alignment without their own rows | none negative beyond 2 SE | one or more negative beyond 2 SE: the drift reaches beyond the narrow kinds |

**Decision.**
- **Trigger:** a kind whose drift is negative beyond 2 SE and at least half the size of its full
  alignment.
- **Action:** that kind gets a retention scheme (a rehearsal share, or a KL anchor on it),
  registered before any push (§14.4).
- **Repeat:** the read at 400 runs the same split.

**R1b's mechanics.**
- R1b is scored with `reports/mulligan_runaway_2026-11-12/timeline.py` on the CPU, from main.
- That is valid because main's `features.py`, `model.py` and `ppo.py` are byte-identical to r28's
  pinned 44a62d9 (`git diff 44a62d9 main` over those three files is empty at 0f96134b).

**The look at 100** (2026-11-12 22:38-23:07; `look.py runs/selfplay/r28_stratified_ppo 100`; r28
paused 22:47:43-23:06:50 for the split):

- **The gate at 100 is 0.5445 [0.529, 0.560]** against v0, logged at update 102. It is the first
  clear rise: 75's was 0.5165, about 2.5 SE below. It is still under the 0.55 that freezes v1.
  r28 is learning, and R3's verdict over 25-75 stands as registered.
- **R1 holds:** the mulligan per game for updates 76-100 is 1.280 (1.25-1.45).
- **R1b holds** (`timeline.py runs/diag_mull_2026-11-12/collect165.pkl runs/r28_looks/r28_u100.pt`,
  CPU, from main at 1e958e36, whose features, model and PPO code still match the pin):
  - p(mulligan) is 0.058 on update 165's 1,043 seven-card hands with 3-4 lands.
  - The prediction was 0.05-0.12; v1 had 0.081 and r27 at 165 had 0.264.
  - The other cells: 0-1 lands 0.951; 2 lands 0.306; 5+ lands 0.101; 6 cards 0.224; 5 or fewer
    cards 0.306.
- **R2 holds:** the mulligan's KL over act's has a median of 2.40 over updates 1-100 (quartiles
  1.89 and 3.00, highest 5.03).
- **R5 holds:** `kl` median 0.0064 (0.0032-0.0080).
- **R6 is falsified as registered:** the lowest MemAvailable was 20.8 GiB, at update 80 (21:28).
  - It was not r28's own growth. The dip spans updates 79-83 (21:24-21:39), when the coordinator
    loaded update 165's whole 532 MB batch to cut a 3,000-row dry-run sample, with no memory cap,
    and four agents started their test suites.
  - r28's floor (15 GiB) throttled its collection once, at update 79. Updates 96-100 read
    50-54 GiB.
  - The fix: heavy side jobs beside a run go under a memory cap (`systemd-run --user --scope -p
    MemoryMax=... -p MemorySwapMax=0`).

**The per-kind split** (`kinds_split.py runs/r28_looks/r28_u100.pt runs/r28_looks/c100/batch.pkl`,
GPU, from main at 1e958e36; the batch from `collect.sh ... 2800`, 139,274 rows; the full update
140 s):

| Kind | Probe decisions | Alignment, full update (SE) | Without its own rows (SE) | Mean abs. Δlog p, full |
|---|---|---|---|---|
| mulligan | 2,467 | +0.0052 (0.0027) | −0.0065 (0.0048) | 0.048 |
| mulligan_bottom | 868 | +0.0207 (0.0037) | +0.0003 (0.0017) | 0.057 |
| priority | 4,000 | +0.0022 (0.0017) | +0.0006 (0.0012) | 0.023 |
| act | 4,000 | +0.0060 (0.0015) | +0.0022 (0.0016) | 0.037 |
| attack | 4,000 | +0.0173 (0.0052) | +0.0045 (0.0029) | 0.040 |
| block | 4,000 | +0.0154 (0.0023) | +0.0007 (0.0021) | 0.055 |
| target | 4,000 | +0.0177 (0.0040) | +0.0010 (0.0026) | 0.054 |

- **K1 is neither met nor falsified.**
  - Every kind moves along its own advantages in point estimate.
  - The mulligan (1.9 SE) and priority (1.3 SE) are not beyond 2 SE, so the prediction ("every
    kind beyond 2 SE") is not met.
  - The falsifier ("a kind at or below 0") is not met either.
- **K2 is falsified.** The drift the rest of the batch causes on the mulligan is −0.0065 ± 0.0048:
  negative in point estimate, but within 2 SE of 0.
- **K3 holds.** No other kind drifts against its own advantages: +0.0003 to +0.0045.
- **The decision rule does not fire.** No kind has a drift negative beyond 2 SE, so no retention
  scheme is registered now. The read at 400 repeats the split.
- **What it says about the slow learning (R3).**
  - The kinds learn from their own rows, with little transfer from the others.
  - Per update the clearest learners are attack, block, target and the bottom choice.
  - Priority, the most frequent decision, moves least along its advantages (+0.0022, the
    smallest Δlog p). That fits its confident passes: the pass share is about 0.9 in r27's later
    updates, and a log-probability near 0 has a small gradient. Whether its slow learning is
    that, or noise in its advantages, is not separated here.

**The look at 150** (2026-11-13 02:13-02:18; `look.py runs/selfplay/r28_stratified_ppo 150`):

- **R1 holds, final.**
  - The mulligan per game, pooled per block of 25 updates: 1.326, 1.288, 1.278, 1.280, 1.255,
    1.317. Every block is inside 1.25-1.45, and none is near the 1.50 falsifier.
  - r27 ran away at 151-165 (1.70). r28 holds for 150 updates on the stratified trainer.
- **R5 holds:** `kl` median 0.0066 (0.0032-0.0109).
- **The gates against v0** (2,000 games each):

| Update | 25 | 50 | 75 | 100 | 125 | 150 |
|---|---|---|---|---|---|---|
| Score | 0.521 | 0.517 | 0.5165 | 0.5445 (0.5413 replayed) | 0.5453 | 0.541 [0.5255, 0.5565] |

- **A plateau at about 0.54 since update 100,** under the 0.55 that freezes v1. That is about
  +28 Elo over the init in 150 updates, most of it between 75 and 100.
- The training win rates (sampled) agree: against the heuristic 0.715 to 0.729, against v0
  0.506 to 0.533.
- Gate B's break-even rule (196 §9) takes r28's rate at 400. At this pace it is small.

## 8. The read at 400, made late (2026-11-14 ~12:00)

**Why late.** The watcher that was to pause r28 after its gate at 400 and keep that save
(`at400.sh`, 21bb2816) was never armed. The coordinating session lost its login on 2026-11-13 at
10:49 (196 §10). r28 ran on unattended, and it stood at update 671 when this was written.

**The split's repeat, registered before its data.**
- Update 400's weights were not kept. r28 keeps only `last.pt` and its frozen versions.
- So the split runs on the save at this window's pause instead: update n, labelled with n. It
  uses §7's scripts, kinds, K1-K3 and decision rule, with the collection seed 2840.
- Why not v1 (update 350), the kept network closest to 400? The decision the split feeds (a
  retention scheme before the next push) is about the trainer as it stands now, and the latest
  weights answer that.
- **Both halves run on r28's pinned code:**
  - `collect.sh` runs from r28's worktree, as before;
  - `kinds_split.py` runs from that worktree with `PYTHONPATH=.`. Main's `features.py` and
    `model.py` have moved since 44a62d9, while `ppo.py` has not.
- The window is `reports/r28_2026-11-12/at400.sh`, which also runs H1′ and 195's confirming
  audit (196 §10).

**The registered read (§4): updates 301-400 against 1-100, and the gates ending there.**
Source: `look.py runs/selfplay/r28_stratified_ppo 400`, the last row per update. Reads go by
update count, so the late reading changes nothing in them.

| Quantity | 1-100 | 301-400 |
|---|---|---|
| The mulligan per game, pooled per block of 25 | 1.326, 1.288, 1.278, 1.280 | 1.401, 1.401, 1.428, 1.398 |
| Entropy, per block | 0.255, 0.248, 0.243, 0.247 | 0.285, 0.284, 0.289, 0.297 |
| Training win rate against the heuristic, per block (sampled) | 0.715-0.730 | 0.723-0.733 |
| `kl`, median | 0.0064 | 0.0060 |
| `ev`, median | 0.371 | 0.362 |

- **The gates ending there:**
  - at 352 against v0, 0.554 [0.537, 0.571], which froze v1;
  - at 377 against v1, 0.515 [0.500, 0.530];
  - at 402 against v1, 0.498 [0.483, 0.513].
- **The ladder at 354:** v0 644.6, v1 671.5, the heuristic 449.4.

**After 400 (not registered; described only, to update 670):**
- The ten gates against v1 at 427-652 average 0.519 (0.505 to 0.538). Each is about ±0.016.
- The mulligan per block stays at 1.27-1.46: no runaway, and the guard's 1.80 is never near.
- Entropy reaches 0.30-0.31.
- The training win rate against the heuristic holds at 0.72-0.74.

**What it means.**
- r28 gained +27 Elo over its init by update 350. In the 320 updates since, it has not moved
  measurably: about 0.52 against v1, or +13 Elo.
- The rate question R3 opened (§5) is answered: on this trainer and these opponents, learning
  after v1 is slow, and after update 350 it is flat.
- Two slow drifts with no registered bound, watched from here on:
  - the mulligan (1.29 in 1-100, 1.41 in 301-400);
  - the entropy (0.25 to 0.30).
  Neither moved the strength reads.
- The next lever is r29's (205 §10): train both seats of learner-against-learner games.
