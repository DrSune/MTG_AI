# 186 — Phase 0, labels: the generator, E1 (true-future label signal) and E3 (distillation)

2026-11-06. Branch `phase0/labels`. The plan is docs/PLAN_LEARNING.md §1.1-1.4, §2, §3, §12, §13.
Each section below is written and committed before the run it describes; results are appended
under it, and every number goes to NUMBERS.md with its command and commit.

## 1. The generator: a short PPO stage teaches r20 v2 the mulligan (pre-registration)

**Why.** runs/selfplay/r20_ppo/v2.pt predates the London mulligan: its `keep` and `mulligan` rows
were grown from "other", so it samples them 50/50 (NUMBERS 2026-11-06: p(keep) = p(mulligan)
exactly). E1's generator should not mulligan at random. It learns the decision by PPO, not by a
rule: the PPO audit measured a strong gradient on this ask (/184 §25: group cosine 0.55 at 4k
decisions, half signal at ~3.4k rows).

**Run.** `r23_mulligan`: the learner from current main's code (a pinned run worktree at this
note's commit; no code change), `--init runs/selfplay/r20_ppo/v2.pt`, the teacher stage only
(the heuristic is the only opponent: `--teacher-gate 2.0` never passes), r22's settings otherwise
(`--refresh-table --extend-sets M20 --mix-sets M20 --mix-share 0.25 --coherent-share 1.0 --pool
verified --lr 1.5e-4 --ent 0.002 --target-kl 0.03 --epochs 1 --mb 4096 --tok-budget 98304
--infer-bf16`), `--steps 32768` per update, `--lam 1.0` (OWNER_PREFERENCES #6: the full result
reaches every decision), 10 workers, `--save-every 1`, `--mem-floor-gib 15`, nice 10, at most 40
updates.

**Metric.** The mulligan rate: mean p(mulligan) at the first declaration, over 2,000 fixed opening
hands (1,000 coherent M21 verified deals, seeds 7,000,000+, both seats), read from every update's
`last.pt` (scratch `labels/mull_probe.py`); also the greedy share (p(mulligan) > 0.5).

**Stop rule ("until stable").** Stop after the first update t >= 6 at which the last four probes
(t-3..t) span less than 0.02. That update's `last.pt` becomes the E1 generator (copied to
`runs/selfplay/r23_mulligan/gen.pt` and pinned in reports/LARGE_FILES.sha256). No stability by
update 40: stop there, record it, and use update 40.

**Predictions.**
- The rate moves off 0.50 within 3 updates and settles between 0.05 and 0.35 (the heuristic's
  rule mulligans 12 of 66 coherent seats, /NUMBERS 2026-11-06).
- Training win rate against the heuristic (sampled play) rises from about 0.56 (the audit's first
  update) to at least 0.62.
- No damage: on the same 300 evaluation deals against the heuristic (greedy, seeds 900,000+, half
  coherent, half stress), the generator scores at least r20 v2's score on this code minus 0.03
  (paired, `tools/selfplay/paired.py`). Falsified by a drop below that.

**Pre-flight.** `tools.selfplay.preflight` (P1, P8, P9, P12) on the run worktree before launch.

### Result (2026-11-06, run worktree at 923ec3f, pre-flight passed)

- **Mulligan rate** (mean p(mulligan), 2,000 fixed hands), updates 1-31: 0.50, 0.50, 0.45, 0.34, 0.39,
  0.40, 0.42, 0.29, 0.29, 0.23, 0.22, 0.15, 0.16, 0.11, 0.11, 0.08, 0.035, 0.050, 0.040, 0.019,
  0.058, 0.038, 0.023, 0.147, 0.024, 0.0028, 0.0021, 0.0008, 0.0026, 0.0056, 0.0083. The greedy
  share stayed 0 throughout: the network learned to keep, nearly regardless of the hand
  (update 31: q10 / q50 / q90 = 0.0005 / 0.0049 / 0.0205).
- **Stop.** The rule fired at update 29 (probes 26-29 span 0.0020). The watcher kept no copy per
  update, so update 29's weights were overwritten before the run was stopped; the run was stopped
  at update 31, which also meets the rule (probes 28-31 span 0.0075). Its `last.pt` is the
  generator: `runs/selfplay/r23_mulligan/gen.pt`, sha256 3dddae50..., pinned. A deviation in
  the letter of the rule (2 extra updates), recorded here.
- Predictions: (1) the rate settles between 0.05 and 0.35: **miss** (it went to ~0.003: keep
  almost always); (2) training win rate against the heuristic rises to at least 0.62: **hit**
  (mean of the first 5 updates 0.581, of the last 5 0.649; sampled play, where r20 v2's 50/50
  mulligans cost games); (3) no damage: **falsified**. Greedy, the same 300 deals against the
  heuristic: generator **0.5875** [0.555, 0.620], r20 v2 on this code **0.635** [0.601, 0.670];
  paired, r20 v2 minus generator **+0.0475** [0.0217, 0.0742] (45 deals better for r20 v2, 16
  worse). In greedy play both keep every hand, so the drop is the drift of the other decisions:
  31 updates of mostly-noise gradient (/184 §25-26: at 32k decisions an update is a few percent
  signal), ~0.011 KL each.
- It is E1's generator as the brief says; its greedy strength is 0.05 below r20 v2's against the
  heuristic. E1 measures label signal for this network; E3 compares its apprentice with it.

## 2. E1, the label signal (pre-registration)

**Question** (PLAN §12 E1). Does a true-future label buy a useful gradient step for at most half of
outcome PPO's lambda-1 cost per forward pass?

**Code and network.** `search.Labeller` at af9efb4 (tests green), run from a pinned worktree at this
section's commit. Generator `runs/selfplay/r23_mulligan/gen.pt` (sha256 3dddae50..., §1).

**Deals and games.** Fresh natural deals as the generator trained on: coherent decks, verified
pool, M21 with a 25% M20 share; seeds 30,000,001+ (A), 31,000,001+ (B), 32,000,001+ (C), used by
nothing else. The generator plays both seats at temperature 1.

**Labels.** Every act decision (both main phases, both seats) whose top option is below 0.95 is
eligible, and 10% of the confident ones; at most 4 per game, uniform among the eligible. k
alternatives by Gumbel-top-k; d = 2 futures (the real one; the true cards with the unknown parts of
both libraries reshuffled), each with its own engine seed shared by the alternatives; playouts to
the end of the game, the generator on both seats from its own views.
- A: k 2, d 2, greedy playouts.
- B: k 2, d 2, sampled playouts (one draw per decision from the future's per-seat stream, shared
  by the alternatives).
- C: k 4, d 2, greedy playouts.
Job: scratch `labels/label_run.py` (a learner subclass issuing label jobs), 10 workers, 32 slots,
2 groups, `--serve-wait 5 --bucket-ratio 100` (inference batching only), nice 10.

**Instrument** (scratch `labels/e1_instrument.py`; the PPO audit's estimator, /184 §26). Per label
the linearised target gradient g = sum over S of pi(a) (q(a) - qbar_S) grad log pi(a), pi recomputed
by the generator. K = 16 groups of whole games; signal S = mean cross-group product of mean group
gradients; per-label noise; B*_labels = noise / S; delete-one-group jackknife SE of S.
B*_FP = B*_labels x (forward passes the job served / labels completed): every pass counts (real
games and playouts), and games still in flight make it conservative. Bounds from the signal's
interval: B*_low = noise / (S + 2 SE), B*_high = noise / (S - 2 SE) (infinite if S <= 2 SE).
Placebo: each label's q permuted across its alternatives (search.placebo, seed 5), z = S / SE.
Per-future: Var(z_a - z_b), corr(z_a, z_b) and the share of ties, over every future's pairs.

**Gate (as written, per configuration).** B*_label at most 2.65M forward passes (at least 2x PPO's
lambda-1 bound of 5.3M, /184 §26) and the placebo's z < 2. E1 passes when a configuration passes. If
only greedy ones pass, §14.1 (greedy playouts) goes to the owner.

**Data: at least 4 B*, in looks.** Each configuration runs in looks of 2.65M forward passes, at most
4 (10.6M, four times the gate's bound). At each look, on all its labels so far:
- pass: data >= 4 x B*_FP, B*_high <= 2.65M, placebo z < 2;
- fail: B*_low > 2.65M;
- otherwise continue.
After the fourth look the gate is scored on the point estimate (B*_FP <= 2.65M passes, and then
data >= 4 B*). The one pre-registered extension: a configuration whose [B*_low, B*_high] still holds
2.65M after the fourth look gets 4 more looks (21.2M), then the point estimate decides.

**Kill** (§12): no configuration passes; then slow outcome PPO plus throughput work (ruling 3).

**Predictions** (the plan's §2 table; smoke labels, 520 greedy k2 d2, not part of E1: corr 0.959,
Var(z_a - z_b) 0.081 per future, 98% of futures tie):
- A passes with B*_FP <= 1.6M (the plan's 3.3x); corr 0.94-0.96; Var(z_a - z_b) 0.03-0.08.
- B fails (0.6x: B*_FP about 8.8M); corr 0.58-0.72; Var(z_a - z_b) 0.22-0.51.
- C is borderline (1.7x: about 3.1M).
- Every placebo z < 2; under 1% of playouts on the rail; no crash.

**Cost.** The GPU is shared with E0's training: label jobs measured 550-920 forward passes a second
(smoke runs, 20:00), so a look takes about 50-80 minutes.

## 3. A finding from the regression test: the target's step decides the owner's example

PLAN §1.4: distilling per-world labels converges on R2 "with the linear target". The plan's step,
eta = 0.5 / SE, is linear enough only when SE includes the spread between the hidden worlds the
policy cannot tell apart. Repeated distillation of the 45/30/25 example (each round the policy
becomes the mean of the per-world targets, `search.mmd_target`), R2's share of the pair after 1,000
rounds (scratch `labels/eta_owner_example.py`):

| eta | 0.02 | 0.05 | 0.1 | 0.25 | 0.5 | 1.0 | 2.7 | hard labels |
|---|---|---|---|---|---|---|---|---|
| R2 share | 0.971 | 0.997 | 0.975 | 0.704 | 0.608 | 0.566 | 0.551 | 0.550 |

R2 is the fixed point only while eta is below about 0.1 here (the second-order term of the
exponential step, 2 eta^2, must stay below the first-order advantage, 0.2 eta). Each label's own
futures share its hidden cards, so their spread (the per-future variance) misses exactly this
between-world noise: with it, SE is about 0.2 for greedy playouts (§2's predictions) and eta about
2.5, which behaves like hard labels. With the between-world spread (here about 2), eta = 0.25 still
stops at 70/30. For greedy deployment the argmax is right in all of these (R2 has the larger mean
target); the stochastic policy is not. The regression test pins the linear regime (eta = 0.05);
the step itself is a registered scaffold (BACKLOG) and a Phase 1 question: anneal it, or bound it
by the advantage it must resolve.

## 4. State at hand-over (2026-11-06 ~21:30, stopped on the owner's instruction)

**Built and tested** (branch `phase0/labels`; gates on ff3632e: pytest MTG_bot 5091 / 39 deselected
/ 71 subtests, pytest tools 144, packs 738/738): `search.Labeller` (reservoir of unsure act
decisions, Gumbel-top-k alternatives, d true futures, `reshuffle_unknown` keeping known library
positions, shared engine seeds and sampled-play draws), `mmd_target`, `placebo`, CRN-safe
`mean_scores` and the `draw_worlds` seam; the actor's `label` job; `tools/selfplay/test_labels.py`
(leak tests, labelling leaves the game alone, second future, crashes, both §1.4 regression tests).

**Generator.** `runs/selfplay/r23_mulligan/gen.pt` (sha256 3dddae50..., pinned): r20 v2 plus 31
PPO updates against the heuristic (§1); greedy 0.0475 weaker than r20 v2 against the heuristic.

**Running** (left on; they produce data): E1 configuration A, launched from the run worktree
`../MTG_AI-labels-run` at 1da8c8e with the scratch copies of the scripts now in
`tools/selfplay/experiments/`: label job pid 1954453 (`runs/labels/e1_A/`: labels.pkl, games.jsonl,
summary.json; log `runs/labels/e1_A.out`), look watcher pid 1974332 (`runs/labels/e1_A.looks`,
`runs/labels/e1_A/look<n>.json`). Look 1 (2.67M FP, 8,731 labels): B*_FP 1.52M, bounds
[0.72M, inf), signal z 1.81, placebo z -0.73, data 1.75 B*: continue. Per future: corr 0.905,
Var(z_a - z_b) 0.189, 95% ties; playouts 62 FP each, about 300 FP per label; 0.35% on the rail, 0
crashes. Look 2 (5.3M) was computing at hand-over; looks 3 and 4 at about 22:15 and 23:00 (about
1,000 FP/s, CPU-bound); the watcher ends the job on a pass or fail stop, else at 10.6M FP.
B and C are not started.

**Commands** (from a checkout of the branch; `PY=/home/sune/Desktop/MTG_AI/.venv/bin/python`,
`X=tools/selfplay/experiments`, `export PYTHONPATH=$PWD`):
- progress: `cat runs/labels/e1_A.looks; cat runs/labels/e1_A/summary.json` (under the main checkout).
- score a look by hand (§2's rule is `decide` in `$X/e1_looks.py`): `$PY $X/e1_instrument.py
  runs/selfplay/r23_mulligan/gen.pt runs/labels/e1_A --K 16 --out look.json`.
- B and C (with their watchers): `$X/launch.sh e1_B 2 2 0 31000000 10600000 10 4`, then
  `$X/launch.sh e1_C 4 2 1 32000000 10600000 10 4` (one at a time: 10 workers is the cap).
  E1 passes when any configuration passes; extension only for a gray result after look 4.
- E3 if E1 passes: commit `$X/e3_prereg_draft.md` as §5 of this note first (fill V from the
  passing look's `per_future.var_diff`, eta = 0.5 / sqrt(V / 2), and the predictions); then
  `launch.sh e3_A 2 2 1 33000000 <FP for 100k labels in total> 10` (no watcher), `launch.sh
  e3_regret 8 4 1 34000000 <FP for 2,000 labels> 10`; `$PY $X/e3_distill.py GEN runs/labels/e3_app
  10000,30000,100000 V runs/labels/e1_A runs/labels/e3_A`; `$PY $X/e3_regret.py
  runs/labels/e3_regret GEN runs/labels/e3_app/app_10000.pt ... app_100000.pt --out regret.json`;
  `$PY -m tools.selfplay.learner --run runs/selfplay/e3_gain --init runs/labels/e3_app/app_100000.pt
  --opp-ckpt GEN --eval-only --eval-opponents snap:opp --eval-deals 450 --pool verified --infer-bf16`.

**Known problems.** (1) A label costs about 300 forward passes (whole-game playouts from early
turns average 62, not 47): E3's 100k labels are about 30M FP, some 8 hours at today's rate.
(2) Per-future noise is above the plan's greedy range (0.189 against 0.03-0.08). (3) The plan's
eta rule is too large for linear distillation in the owner's example (§3). (4) The generator is
weaker than r20 v2 in greedy play (§1). (5) NUMBERS.md is not written yet: the numbers are in
§1-§4 and in the run directories; the scripts above are to be deleted once the gates are scored.
