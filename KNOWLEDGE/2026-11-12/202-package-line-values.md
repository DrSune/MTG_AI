# 202 — Package line values: is there signal in the directions the owner wants to push?

**The question.** The owner (2026-11-12): "If it starts to pick up on longer horizon or more
complex combos (even if we 'cheat' and force/incentivize it) then we can make a frozen version of
that, and iterate. We need to make sure it has some signal in the directions we move, or the
gradient never goes there."

**Why a measurement.**
- The policy gradient sees only what the policy already tries (PLAN_CEILING §14.2), so it cannot
  tell whether a line it never plays is worth playing.
- Instrument 1 (`tools/selfplay/linevalue.py`) measures a line's value directly. It forces the
  line at the decisions where it begins and plays to the end on shared futures against the
  policy as it is.
- The lines measured here are the packages' own (package mode, 2026-11-12): "cast a consumer
  before its producers", on decks built around that package.

## 1. Registered before any data (2026-11-12 22:35)

**The runs.**
- Each run: `linevalue.py runs/r28_looks/r28_u100.pt --package LABEL --set M21 --states 100
  --futures 3 --games 600 --out ...`.
  - Sampled play, the verified M21 pool, decks built around the package, master seed 0.
  - CPU, nice 19, two threads each, beside r28.
- The packages, in order: `life`, `draw`, `counter`, `spell[!Creature]`. These are the four
  M21 families that fire in at least 40% of their decks under the heuristic (NUMBERS 2026-11-12,
  package mode).
- Kill rule: a run with more than 10% crashed futures, or fewer than 50 states within its 600
  games, is reported but not read.

**The readouts per line:**
- A1 − B: the forced first step's value against the policy's own choice, with SE over states;
- p(step): the policy's unforced use at the states where the line begins;
- follow-through;
- the critic's A − B at the next turn top.

**The decision rule.** Each line is put in one of three classes:

| Class | Condition | What follows |
|---|---|---|
| Barrier | A1 − B ≥ +0.03, beyond 2 SE, and p(step) < 0.3 | A candidate for forcing by frequency, and for the first specialist (PLAN_CEILING §14.3) |
| Learnable | A1 − B beyond 2 SE above 0, and p(step) ≥ 0.3 | The gradient already sees the line. Richer deals (package share), not forcing |
| No signal | A1 − B within 2 SE of 0, or below 0 | Forcing this line buys nothing at this policy's level. A specialist would have to find its value elsewhere |

**Prediction** (the owner's hypothesis, as this note reads it):
- At least one of the four lines is a Barrier or Learnable.
- In package decks, the order "consumer first" is worth something.

**Falsifier:** all four are No signal. Then package decks add events the policy can use, but not
an ordering it has to learn. The ceiling read (PLAN_CEILING §14.1, skill spread per deck
distribution) is then the next test of "richer decks, more skill".

## 2. Results (2026-11-12 22:39 to 2026-11-13 01:51)

All four runs completed with 100 states measured, 0 crashed futures and 0 void games.

| Line (M21) | A1 − B | A* − B | p(step), unforced | Critic A1 − B, next turn top | Class |
|---|---|---|---|---|---|
| life | −0.047 ± 0.046 | −0.120 ± 0.057 | 0.325 | −0.038 ± 0.011 | No signal |
| draw | −0.013 ± 0.042 | −0.040 ± 0.062 | 0.400 | −0.007 ± 0.015 | No signal |
| counter | −0.027 ± 0.028 | −0.067 ± 0.041 | 0.295 | −0.035 ± 0.010 | No signal |
| spell[!Creature] | −0.007 ± 0.031 | −0.120 ± 0.054 | 0.529 | +0.028 ± 0.018 | No signal |

**The prediction is falsified:** all four lines are No signal.
- Casting a consumer before its producers is worth nothing against the policy's own choice at
  the states where the order is at stake. Every point estimate is at or below 0.
- Forcing the whole line (A*, every later step forced too) is worse: −0.04 to −0.12, about 2
  SE for life and for noncreature spells. The policy's own sequencing beats the naive "payoff
  first" rule.
- The policy plays the step by itself 30-53% of the time. So these are not unexplored lines: the
  gradient sees them, and they carry little value.
- The critic agrees with the results. Its A1 − B readings at the next turn top are small and
  mostly have the realised sign (life −0.038 ± 0.011, counter −0.035 ± 0.010). The value head
  does see what the order is worth.

**What this does not say.**
- These are ordering lines only. The instrument cannot force activations, targets, attacks or
  holding a card back. So the sacrifice package, the barrier the package mode found (6% firing
  under the heuristic), is not measured.
- The policy is r28 at 100, and the opponent is that same policy.
- The value of a package may lie in its composition, more events for the payoffs, rather than
  in an order the policy must learn.

**As registered, the next test of "richer decks, more skill" is the ceiling read:** the skill
spread per deck distribution (PLAN_CEILING §14.1), in the GPU window at r28's read at 400.
- The forcing loop (§14.3) is not pointed at these ordering lines.
- A line class with measured value must be found first. The candidates are activation lines,
  once the instrument can force an activation (the sacrifice outlets), and longer-horizon lines.

**Commands:** `CUDA_VISIBLE_DEVICES= OMP_NUM_THREADS=2 nice -n 19 .venv/bin/python -m
tools.selfplay.linevalue runs/r28_looks/r28_u100.pt --package LABEL --set M21 --states 100
--futures 3 --games 600 --out runs/linevalue_2026-11-12/<label>.json`, with LABEL life, draw,
counter or 'spell[!Creature]' (the last two under a 4 GiB memory cap). It takes 15-18 s per
state × future on two CPU threads, about 1.5 hours per line.

## 3. Registered before its data (2026-11-13 02:00): the sacrifice package, with activations

**Why this line.**
- §2 left untested the one package where the package mode found an exploration barrier: under
  the heuristic, sacrifice fires in only 6% of its decks, because no rule activates a sacrifice
  outlet.
- `linevalue --activations` (this commit) lets an order line's follow-through also activate a
  producer's abilities, so it can force an outlet.

**The run.** `linevalue.py runs/r28_looks/r28_u100.pt --package sacrifice --activations --set M21
--states 100 --futures 3 --games 600 --out runs/linevalue_2026-11-12/sacrifice_act.json`. Same
settings as §1, CPU under a 4 GiB cap. The kill rule is §1's.

| # | Metric | Prediction | Falsifier |
|---|---|---|---|
| S1 | A* − B: the consumer cast first, then every producer step forced, activations included | ≥ +0.03, beyond 2 SE: activating outlets with the payoff out is worth something, a barrier in the follow-through | within 2 SE of 0, or below |
| S2 | Follow-through in B: the share of later producer steps, activations included, the policy takes by itself | below 0.3 (the barrier) | — (descriptive) |

**What follows.**
- If S1 holds, the sacrifice package is the first line class with measured value. It becomes the
  first candidate for forcing by frequency and for a specialist (PLAN_CEILING §14.3).
- If S1 fails, no measured line has value yet. The ceiling read at 400 decides alone.
