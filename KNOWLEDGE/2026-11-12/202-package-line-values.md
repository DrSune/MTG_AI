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

## 2. Results

(Pending.)
