# 191 — r27: outcome PPO on the game with priority (pre-registration, before any r27 game)

**Draft (2026-11-11 14:00): the census numbers (STEPS, CENSUS, SECONDS) are filled in before launch; the section is frozen at the launch commit.**

**Sources.**
- DESIGN_PRIORITY stage 5. Decisions 3 and 4 of its §7 were approved on 2026-11-10: start from
  r26's newest network, and keep r26 running until this is ready.
- Step 0 of `docs/PLAN_CEILING.md` (draft).
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
- It recaptures the opponent simulator.
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
  --slots 16 --groups 4 --gamma 1.0 --lam 1.0 --steps STEPS --epochs 1 --lr 2e-5 --wd 0.01 \
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
3. **`--steps STEPS`** (r26: 98,304): keep r26's ~1,850 games per update.
   - One game's result is the signal, and every decision of that game shares it. So games per
     update, not decisions, set how much signal an update carries.
   - The new game asks more per game: CENSUS.

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

The gates now deal coherent decks only (`learner.py:863` with `--coherent-share 1.0`). r26's
pinned code dealt half stress decks. So a gate's standard error of ~0.011 is all on the
distribution trained on.

**Start values** (CPU census of r26's `last.pt` against itself, both seats sampled, 30 games;
scratch script `selfplay_census.py`, numbers in NUMBERS): CENSUS-KINDS.

## 4. Predictions (written before any r27 game)

| # | Metric | Prediction | Falsifier |
|---|---|---|---|
| 1 | A freeze: a gate against v0 at 0.55 with the lower bound above 0.5 | v1 frozen by update 500. I put it at 60%: the new asks are learnable gains the start never trained on, but the instant-speed heuristic beat the old one by only 0.52 +- 0.05 | no freeze by update 500 |
| 2 | Training win rate against the heuristic: mean of updates 401-500 less mean of updates 1-100 (~280 heuristic games per update; SE of the difference ~0.004) | +0.02 to +0.05, of which up to ~0.01 can be temperature (the entropy falls) | below +0.01: no learning against the fixed anchor |
| 3 | Movement | `kl` 0.003-0.006 per update (r26 at the same lr: 0.0046-0.0057) | below 0.0015: moved too little to test anything |
| 4 | Entropy (`ent`, nats, all asks) | falls over updates 2-50 from its update-1 value; mean of 401-500 within 0.22-0.36 | rising over 2-50; or 401-500 below 0.15 (collapse) or above 0.40 |
| 5 | PH-9, `priority`: pass share in training games | between 0.70 and 0.96 in every 100-update window to 500 | above 0.97 (learning to do nothing there) or below 0.65 (acting at random) |
| 6 | Value fit (`ev`), mean of 401-500 | 0.35-0.50 | below 0.25, or below 0 for 3 updates (K4) |
| 7 | Memory | minimum MemAvailable above 40 GiB; updates 401-500 within 3 GiB of updates 11-100 | a steady fall: a leak |
| 8 | Median seconds between updates, gate intervals left out | SECONDS | above SECONDS_FALSIFIER |
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
