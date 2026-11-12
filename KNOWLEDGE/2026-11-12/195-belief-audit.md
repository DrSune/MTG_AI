# 195 — Do the simulator's worlds bring the search's comparisons closer to the truth? (pre-registration)

**Context.**
- Window 1's N5 found no gain from simulator worlds at n = 16 (192 §7.1): -0.009 ± 0.009
  against the uniform points around it.
- The owner doubted the first reading ("Uniform is just better? Not sure if I trust that",
  2026-11-12).
- 192 §7.1 showed the simulator's worlds are realistic and found no bug. What it could not show
  is whether those worlds change which candidate the search prefers, toward the move the true
  hidden cards prefer. A 300-deal match cannot see that through the deal noise.
- This test pairs by position instead. Written before any audit runs; results are appended below
  and never edit this section.

**The tool.**
- `learner.py --search-audit W` (commits 7475928, 92e3160) scores the network's top 4 candidates
  at every searched act decision in W worlds of each of four kinds:
  - `uniform`;
  - `sim` (the simulator's);
  - `true`: the real hidden cards, with only what no player knows reshuffled;
  - `true2`: a second, independent set of true worlds.
- The audit draws from its own stream and never chooses: the game is played by the search's own
  uniform worlds, as at window 1's n = 16.
- Test: true worlds play the real hand, uniform ones re-draw it, and the search's random state is
  unchanged.

## 1. The run (a GPU window, about 30 minutes)

`learner.py --eval-only` with:
- r27's v0 (`--init runs/selfplay/r26_outcome_ppo/u1000.pt --refresh-table --extend-sets M20`)
  against itself (`--eval-opponents snap:opp --opp-ckpt` the same file), both greedy;
- `--eval-seat eval+search --search-root gumbel --search-m 16 --search-n 16`, uniform worlds;
- `--search-audit 8 --search-sim runs/window1/sim.pt`;
- `--eval-deals 100 --eval-seed0 960000` (fresh deals), M21, coherent decks, verified pool;
- 18 workers.

## 2. Measures

Over audited decisions with at least two candidates and all four kinds scored:
- **A(kind):** the share of decisions where the kind's best candidate is the `true` worlds' best.
  Ties go to the candidate the network ranks higher: candidates are kept in its order and the
  first maximum is taken.
- **The ceiling:** A(`true2`), that is, how far two samples of the truth agree at 8 worlds.
- **Per decision:** the rank correlation of the kind's means with `true`'s, averaged over
  decisions.
- **Primary:** A(`sim`) - A(`uniform`), paired by decision, with a 95% interval from 2,000
  bootstrap resamples of the deals.

## 3. Predictions

| # | Measure | Prediction | Falsifier |
|---|---|---|---|
| B1 | A(`true2`), the ceiling | 0.55-0.80 | — (it scales the others) |
| B2 | A(`sim`) - A(`uniform`) | +0.02 to +0.08: worlds whose opponents hold the right kind of cards should pick more like the truth | at or below 0, with the upper bound under +0.02 |
| B3 | A(`uniform`) | 0.40-0.70, below the ceiling | above the ceiling: then the true worlds are too noisy to judge anything, and B2 is not read |

## 4. What each outcome means

- **B2 met** (the simulator's worlds compare candidates more truly):
  - the null of N5 in play comes from the play, not from the beliefs: the noise of 300 deals, or
    halving on a few worlds;
  - next, simulator worlds at n = 64 and at horizon 2, where the comparisons are less noisy and
    the opponent's replies weigh more.
- **B2 falsified** (no closer to the truth):
  - at horizon 1, with a leaf that cannot see the hidden cards, the opponent's real cards barely
    change which candidate wins;
  - beliefs can then pay only at a longer horizon or with a leaf that reads beliefs. That is a
    design question for the search, not a fault of the simulator.

## 5. Amendment, 2026-11-12 ~13:15: the true worlds keep some unseen cards in place (before any audit number was read)

The bug hunt (KNOWLEDGE/2026-11-12/197) found the following while the audit was running. No
audit number had been read yet.

**The defect.** `reshuffle_unknown` (search.py at 98a48e9, the code this run uses) is meant to
reshuffle only what no player knows. It works out what is known from the engine's journal, which
was never built to record that. It wrongly keeps three kinds of unseen card at their real
library positions:
- **After a scry:** the journal records only how many cards were scried, so that many positions
  stay fixed at both ends of the library until the next shuffle.
- **After "target opponent reveals their hand"** (Duress, Kitesail Freebooter): the REVEAL atom
  has no zone role, and its unbounded count is the library idiom. So the journal records the
  target's whole library as revealed.
- **After a graveyard-only search's reveal:** the reveal records the library's top card.

**How often.** With heuristic play on this run's own deals (960,000-960,099), 620 of 3,564 act
decisions (17%) keep an unseen card in place:
- in 516 of them the pinned card is the top one, i.e. the next draw;
- in 120 a whole library is pinned.

**What it does to the measures.** In those decisions, the `true` and `true2` worlds share part
of the real future:
- A(`true2`) (B1, the ceiling) overstates how far two samples of the truth agree;
- `true` is partly the realized future, not the real cards in an unknown order;
- B2 compares `sim` and `uniform` against the same reference, so it is hit less directly, but
  its reference no longer means what §2 says.

**How it is read.**
- This run's B1-B3 are scored as registered and reported, marked confounded.
- They decide nothing.
- The confirming run decides: the §1 command on fixed code, where the true worlds keep the real
  hidden cards (the opponent's hand exactly) and reshuffle both libraries completely. The
  search's uniform worlds already ignore position knowledge: they reshuffle the searcher's own
  library whole. So every kind is then compared without it.
- B1-B3 keep their predictions and falsifiers, and §4's readings apply to the confirming run.
- It runs at r27's next pause.
