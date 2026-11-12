# 191 — r27: outcome PPO on the game with priority (pre-registration, before any r27 game)

**Frozen at launch (2026-11-11), after r26's read at update 1,000.** Not edited after r27's
launch commit, which the run's `preregistration.json` and manifest record. The run's worktree
`/home/sune/Desktop/MTG_AI-r27` is pinned there.

**Sources.**
- DESIGN_PRIORITY stage 5. Decisions 3 and 4 of its §7 were approved on 2026-11-10: start from
  r26's newest network, and keep r26 running until this is ready.
- Step 0 of `docs/PLAN_CEILING.md` (approved, DECISIONS D22).
- Template: note 189 §9 (r26). This section is written before launch and is never edited.
  Results are appended below it.

## 1. Why this run

**The game changed.**
- Stage 1 gave both players priority in every step: instants, flash, activated abilities, the
  stack and trigger order.
- Stage 2 changed the yardstick: the heuristic now plays at instant speed.
- So r26's numbers are history, not a baseline (DESIGN_PRIORITY §6).

**r27 is the learner of PLAN_CEILING.**
- Its frozen versions are the networks the search amplifies.
- Its start network recaptures the opponent simulator (window 1, note 192).
- It is the start of the high-ceiling track.

**The start transfers** (NUMBERS, "PRIORITY STAGES 1-4"):
- r26's network on the new game: 35/40 greedy and 30/40 sampled against the new heuristic.
- It passes at 0.78-0.94 of its `priority` asks.
- Its new input columns start at zero, so it computes what it did before: the same logits and
  values to 0.0 on 400 decisions.

## 2. Configuration

**Init.**
- r26's `last.pt` when r26 stops after its registered read at update 1,000, copied to
  `runs/selfplay/r26_outcome_ppo/u1000.pt` so that a later resume of r26 cannot change it.
- Its sha256 is pinned in `reports/LARGE_FILES.sha256` and goes into `preregistration.json`.
- The learner freezes it as v0.

**Code.** `main` at the launch commit, from the pinned worktree `/home/sune/Desktop/MTG_AI-r27`.
It has:
- the game with priority;
- the new heuristic, as the 15% opponent;
- evaluations and gates on coherent decks only, as training deals;
- per-kind statistics (METRICS PH-9).

**Command.** r26's command (189 §9) with three changes:

```
tools/selfplay/launch.sh /home/sune/Desktop/MTG_AI/runs/selfplay/r27_priority_ppo \
  --init /home/sune/Desktop/MTG_AI/runs/selfplay/r26_outcome_ppo/u1000.pt --seed 27 --workers 18 \
  --slots 16 --groups 4 --gamma 1.0 --lam 1.0 --steps 139264 --epochs 1 --lr 2e-5 --wd 0.01 \
  --clip 0.2 --vclip 0.5 --vcoef 0.5 --ent 0.004 --max-grad 1.0 --target-kl 0 --mb 4096 \
  --tok-budget 98304 --infer-bf16 --teacher-iters 0 --gate-every 25 --gate-deals 1000 \
  --gate-score 0.55 --ladder-deals 500 --p-heuristic 0.15 --p-past 0.15 --coherent-share 1.0 \
  --mix-sets M20 --mix-share 0.25 --extend-sets M20 --refresh-table --pool verified \
  --save-every 5 --progress-every 300 --mem-floor-gib 15.0 --iters 6000
```

**The changes, each with its reason:**

1. **`--seed 27`**: fresh training deals.
2. **`--ent 0.004`** (r26: 0.0075).
   - At 0.0075 r26's entropy rose to 0.43, where §9 of note 189 had called anything above 0.40
     too strong (189 §10).
   - At 0.004, an action that costs 0.3 points of win probability keeps about 15% of the best
     action's weight at equilibrium, instead of about 37% (189 §9's arithmetic: 0.0032 per e-fold
     on the +-1 scale instead of 0.0059).
   - The new asks are the reason to lower it. Most `priority` asks are a pass whose alternatives
     rarely matter. A strong bonus flattens exactly those, and fills training games with instants
     cast at random.
3. **`--steps 139264`** (r26: 98,304; 34 minibatches of 4,096): keep r26's ~1,850 games per
   update.
   - One game's result is the signal, and every decision of that game shares it. So games per
     update, not decisions, set how much signal an update carries.
   - The new game asks more per game: 74.3 recorded decisions per seat and game, against r26's
     52.8 over updates 801-900. So 139,264 decisions is about 1,875 games.

**Unchanged:**
- gamma = lambda = 1, lr 2e-5, one epoch;
- clip, value clip, value coefficient, no KL stop;
- gates every 25 updates on 1,000 seat-swapped deals at 0.55;
- 15% heuristic and 15% older versions;
- coherent decks, M20 in 25% of games, the verified pool;
- the memory floor.

**Not in r27**, named so nobody wonders. Each would confound the first read of the new game:
- both seats of a self-play game to the learner (189 §5's next step after a gain);
- a lower value coefficient (BACKLOG);
- search;
- the simulator's beliefs as input.

## 3. Instruments

As note 189 §4, plus PH-9's row per ask kind on every update: decisions, pass share, mean
advantage, normalised entropy and KL.

Every evaluation now deals coherent decks only (`learner.py:800`, since decad93; r26's pinned code
dealt half stress decks). So a gate's standard error of ~0.011 is all on the distribution trained
on. r26's read at 1,000 shows why it matters: its coherent halves rose to 0.546 against v2 while
its five-colour halves fell to 0.476, and the pooled gate froze nothing after update 378
(189 §11).

**Start values** (CPU census of r26's `last.pt` against itself, both seats sampled, 30 games;
scratch script `selfplay_census.py`, numbers in NUMBERS):
- 20.7 turns per game;
- 74.3 recorded decisions per seat and game: `priority` 28.6, act 20.8, attack 12.2,
  block 3.6, target 3.1, the rest under 1.3 each;
- entropy of all asks 0.267 nats (normalised 0.268);
- `priority`: entropy 0.171, normalised 0.208, pass share 0.851;
- act: 0.370, normalised 0.306, pass 0.241;
- attack: 0.187, normalised 0.261, pass 0.425.

The network passes most `priority` asks and has its least spread there, so a bonus pushes those
hardest.

## 4. Predictions (written before any r27 game)

| # | Metric | Prediction | Falsifier |
|---|---|---|---|
| 1 | A freeze: a gate against v0 at 0.55 with the lower bound above 0.5 | v1 frozen by update 500. I put it at 60%: the new asks are learnable gains the start never trained on, but the instant-speed heuristic beat the old one by only 0.52 +- 0.05 | no freeze by update 500 |
| 2 | Training win rate against the heuristic: mean of updates 401-500 less mean of updates 1-100 (~280 heuristic games per update; SE of the difference ~0.004) | +0.02 to +0.05, of which up to ~0.01 can be temperature (the entropy falls) | below +0.01: no learning against the fixed anchor |
| 3 | Movement | `kl` 0.004-0.009 per update: r26 moved 0.0046-0.0057 at the same lr, and a 1.42x batch takes 1.42x the optimizer steps per update (minibatches are cut by the token budget). With noisy gradients, KL grows about in proportion | below 0.0015: moved too little to test anything; above 0.02: too far per update |
| 4 | Entropy (`ent`, nats, all asks; ~0.27 at the start by the census) | least-squares slope over updates 2-50 between -0.002 and -0.0003 per update. r26's 0.0075 was sized to balance r25's fall of -0.0029, so half of it leaves about half that fall. Mean of 401-500 within 0.15-0.26 | a slope at or above 0 (the bonus pushes more than that arithmetic says); 401-500 below 0.12 (collapse) or above 0.30 |
| 5 | PH-9, `priority`: pass share in training games | between 0.70 and 0.96 in every 100-update window to 500 | above 0.97 (learning to do nothing there) or below 0.65 (acting at random) |
| 6 | Value fit (`ev`), mean of 401-500 | 0.35-0.50 | below 0.25, or below 0 for 3 updates (K4) |
| 7 | Memory | minimum MemAvailable above 35 GiB (r26: 46-50 at 98k decisions; the update's batch is 1.42x); updates 401-500 within 3 GiB of updates 11-100 | below 30 GiB, or a steady fall: a leak |
| 8 | Median seconds between updates, gate intervals left out | 175-230 (r26: 138 s at 98k; the update and the collection both scale with the 1.42x batch, and the new game's engine costs more per decision) | above 250 |
| 9 | Start ladder: v0 against the new heuristic, 500 deals, greedy | 0.80-0.90 (CPU: 35/40) | outside |

**What each outcome means:**
- **1 or 2 met**: outcome PPO learns the game with priority from r26's network. The run goes on
  as PLAN_CEILING's learner.
- **1 and 2 falsified with 3 met**: the new decisions are not learned at this noise scale. The
  per-kind rows say which, and the learner needs a denser signal there (PLAN_CEILING §6).
- **3 falsified**: rerun at a higher learning rate before concluding anything.

## 5. Kill criteria

- **K1**: any engine crash or unhandled exception. The new engine's priority paths have never run
  at this scale: P8 in pre-flight; the interleaving soak found one crash in 600 games, fixed.
- **K4**: `ev` below 0 for 3 updates.
- **K7**: games per second below half of the first hour's, sustained.
- The memory floor once.
- Non-finite steps in 3 consecutive updates.
- Training win rate against the heuristic, over any 50-update window, more than 0.05 below its
  mean over updates 1-50.

While nobody watches, only the memory floor is enforced. The rest is read on the last row per
update: a resume replays up to 4 updates.

## 6. Pre-flight, unit, looks

**Pre-flight**, from the pinned worktree at the launch commit:
- `tools.selfplay.preflight runs/selfplay/r27_priority_ppo --games 200` (P1, P8, P9, P12);
- the suites green at that commit;
- `preregistration.json` (this section) written into the run directory before the first game.

**Unit** `mtg-r27`: r26's unit text (189 §9) with:
- the worktree `/home/sune/Desktop/MTG_AI-r27`;
- the run directory `runs/selfplay/r27_priority_ppo`;
- the command above;
- the log `runs/selfplay/r27_priority_ppo.out`.

**Looks:**
- once at update 3: memory, speed, `kl`, `ev`, PH-9 rows present;
- then reads at updates 500, 1,000 and 2,000 (windows 401-500, 901-1000 and 1901-2000 against
  1-100, and the gates ending there).

PLAN_CEILING's measurement windows pause the run with `systemctl --user stop mtg-r27`, which loses
at most 4 updates. The reads go by update count, so a pause changes nothing in them.

## 7. Launch and the first look (2026-11-12)

**Launch.**
- `mtg-clock1` started r27 at 03:56:38, after window 1 and the clock's latency
  (KNOWLEDGE/2026-11-11/192 §8).
- The launch commit is d6dcdff. It moved twice before launch, and both moves are in
  `preregistration.json`; neither changes training:
  - a85403f to f473c44: a flaky PPO test (unseeded minibatch order) was fixed;
  - f473c44 to d6dcdff: every training game's deal and result goes to `train_rows.jsonl`, the
    deck critic's data (`docs/PLAN_DRAFTER.md`).
- The init is u1000.pt, sha256 d71e2b25… The table refresh changed 1 row, M20 added none, and
  v0 was frozen at 03:56:52.

**The start ladder** (500 deals, both seats, greedy, coherent decks from the verified pool):

| Match | Score | 95% |
|---|---|---|
| heuristic against random | 0.916 | [0.900, 0.932] |
| v0 against random | 0.9695 | [0.959, 0.980] |
| v0 against the heuristic | **0.6995** | [0.674, 0.725] |

- Elo: random 0, heuristic 424, v0 574.
- **Prediction 9 is falsified** (0.80-0.90). 192 §7.5 had warned of this before the ladder ran:
  window 1 measured 0.692 for the same network and code.
- 192 §7.6 checks the cause in window 2: fp32 against bf16, and the castable pool behind the
  35/40.
- No other number in §4 rests on it.

**The look at update 3** (the last row per update):

| Update | 1 | 2 | 3 | Prediction |
|---|---|---|---|---|
| `kl` | 0.0048 | 0.0075 | 0.0087 | 3: 0.004-0.009, falsified above 0.02 |
| `ev` | 0.355 | 0.343 | 0.332 | 6: 401-500 in 0.35-0.50 |
| `ent` | 0.344 | 0.324 | 0.358 | 4: slope over 2-50, read at 50 |
| `priority` pass share (PH-9) | 0.779 | 0.792 | 0.782 | 5: 0.70-0.96 |
| Lowest MemAvailable | 51.0 GiB | 53.2 | 53.9 | 7: above 35 |
| Update's own time | 113 s | 114 s | 115 s | — |
| Games | 3,234 | 2,152 | 2,187 | — |
| Training win rate against the heuristic / frozen v0 | 0.608 / 0.508 | 0.640 / 0.504 | 0.658 / 0.498 | 2: read at 500 |

- The interval between updates was 192 s and 240 s while the start ladders also ran.
  Prediction 8 (a median of 175-230 s, gate intervals left out) is read once the ladders are out
  of the window.
- No non-finite steps and no void games. PH-9 rows are present for every kind of decision.
- The census's ~0.27 entropy at the start was measured differently: the run's own `ent` starts at
  0.32-0.36. Prediction 4's slope and level are read against the run's start.
- **One to watch: the mulligan.**
  - Its KL from the behaviour policy was 0.006, 0.022 and 0.089 over the first three updates, on
    about 3,000 decisions per update. That is the largest of any kind.
  - A mulligan's advantage is the whole game's result less a value that knows little at the
    start, so its gradient is the noisiest.
  - r26 logged no rows per kind to compare against.
- **The critic's data are logging.** `train_rows.jsonl` held 8,567 games by update 3, 84% of them
  between networks. The decks rebuilt at d6dcdff equal a direct deal (30 of 30 deals checked).
  The critic's 50,000 games (KNOWLEDGE/2026-11-12/193 G1) arrive at about update 27.

**The look at update 50** (2026-11-12 06:30; the last row per update, means over blocks of
updates; 109,559 training games):

| | 1-10 | 21-30 | 41-52 | Prediction |
|---|---|---|---|---|
| Gate against v0 (1,000 deals, both seats, greedy) | — | 0.517 [0.503, 0.531] at 25 | 0.536 [0.522, 0.550] at 50 | 1: a freeze at 0.55. r26 scored 0.522 and 0.531 at the same updates |
| `kl` | 0.0066 | 0.0063 | 0.0055 | 3: 0.004-0.009 |
| `ent` | 0.336 | 0.311 | 0.306 | 4: slope over 2-50 in -0.002 to -0.0003 |
| `ev` | 0.372 | 0.373 | 0.371 | 6: 401-500 in 0.35-0.50 |
| `priority` pass share | 0.794 | 0.833 | 0.852 | 5: 0.70-0.96 |
| `act_second_main` pass share | 0.813 | 0.851 | 0.860 | — |
| Training win rate against the heuristic / frozen v0 | 0.655 / 0.507 | 0.681 / 0.522 | 0.699 / 0.544 | 2: read at 500 |
| Lowest MemAvailable (GiB) | 52.1 | 53.1 | 52.8 | 7: above 35 |

- **Prediction 4 is met**:
  - the slope over updates 2-50 is -0.00056 per update (SE 0.00016);
  - `ent` went from 0.324 at update 2 to 0.301 at 50.
- **Prediction 8 is outside its range, on the fast side.**
  - The median interval is 169.8 s over 45 intervals, against 175-230. Left out are the
    intervals that held the start ladders (updates 2-3) or a gate (26-27, 51-52).
  - The falsifier is above 250.
- **No kill criterion is near:**
  - no crash, no non-finite step, no void game;
  - `ev` never below 0.33;
  - the lowest MemAvailable of any update was 48.4 GiB.
- **Two counters climb, and both are harmless:**
  - `overflow` counts decisions with more than 64 options, which the heuristic answers and
    which are never trained on: 1,680 in 109,559 games, 0.015 a game, flat;
  - `throttled` counts training games refused because a full batch was waiting: 7 times.
- **The pass shares are still rising, but more slowly.**
  - `priority` went 0.794, 0.824, 0.833, 0.836, 0.852 over blocks of 10 updates, and its
    entropy from 0.225 to 0.197. `act_second_main` moved the same way.
  - Both training win rates rose meanwhile. That reads as learning to hold instant-speed play
    rather than learning to do nothing, but the rise has not stopped: +0.0013 per update since
    update 25.
  - At that pace the share reaches 0.96 near update 130. Window 2's pause, at about update 165,
    reads it again.
- **The mulligan.**
  - Its KL is still the largest of any kind: 0.060, 0.024, 0.035, 0.050 and 0.022 per block of
    10 updates, where every other kind with more than 100 decisions an update stays at or below
    0.013.
  - Its entropy went 0.218, 0.143, 0.126, 0.136, 0.170.
  - The learner's asks per game went 1.33, 1.28, 1.25, 1.32, 1.31: no trend. The engine takes
    CR 103.5 literally: a mulligan's cards go to the bottom before the next declaration, so the
    k-th ask shows 7 - k cards and the network sees how many it has taken. Every ask after a
    game's first is a mulligan.
  - So the learner mulligans about 0.31 times a game, 24% of its declarations. That inherits
    r26's rate:
    - r25's and r26's v0 (gen.pt) mulliganed 16 of 1,516 hands, 1.1% (190 §10.4);
    - the heuristic's rule mulligans about 12% of 7-card hands from a 40-card deck with 17
      lands.
  - r26's bonus raised the overall entropy from 0.24 (updates 1-25) to 0.45 (901-1000; 189 §11).
    r26 logged no rows per kind, so its 1,000 updates may have pushed the mulligan up the same
    way, or taught it which hands to throw back. The read below, registered before its data,
    tells which.

**The mulligan read** (registered 2026-11-12 06:50, before its data).

- **Data.** Window 2's collect (194 §1) writes about 23,000 of v0's mulligan declarations under
  r27's flags. Each comes with its features, the action, the action's log-probability and the
  game's result.
- **What is read.**
  - The hand at each declaration: the own-hand entities in `cards_i`, and their Land flag in
    `cards_f`.
  - v0's p(mulligan) for each hand.
  - The same declarations scored by r27's network at the pause (`runs/window2/r27_latest.pt`).
- **Cells.** Hand size 7, by land count, plus hand sizes 6 and 5. Intervals come from a
  bootstrap over games.

| # | Measure | Prediction | Falsifier |
|---|---|---|---|
| M1 | v0's mean p(mulligan) at 7-card declarations holding 3 or 4 lands | below 0.10 | 0.20 or more: the mulligan is not read from the hand |
| M2 | the same, holding 0 or 1 land | above 0.60 | below 0.40 |
| M3 | ROC-AUC of v0's p(keep) against the game's result, 7-card declarations (METRICS MUL-2) | 0.52-0.58 | below 0.51: the keep decision carries no information about the game |

- **M1 falsified:** the mulligan rate is noise that r26's bonus put there, not a policy.
  - r27 runs on unchanged.
  - The fix belongs to the next run: a smaller bonus for the mulligan, or the search deciding it.
- **M1 and M2 met:** the mulligan reads the hand. Whether 24% is too cautious is MUL-3's
  question, which needs per-game mulligan records that no run writes yet.
