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
