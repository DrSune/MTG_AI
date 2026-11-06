# 186 — Phase 0, E0: the opponent simulator (2026-11-06)

Plan: docs/PLAN_LEARNING.md §8 (the simulator), §12 (E0's gate), §13 (footprint and scaffolds).
Branch `phase0/simulator`. Section 1 is the pre-registration, committed before the capture and the
training runs; results are appended below it and never edit it.

## 1. Pre-registration (written before any run)

**Hypothesis.** A separate network trained only by supervision on finished games, reading what one
seat may know, predicts the opponent's whole hand better than the hand-built deck-consistent
yardstick: the yardstick knows the deck generator exactly but not how the opponent played, so the
gain must come from play (lands it did not play, spells it held, what it cast and when).

**Code.** `tools/selfplay/simulator.py` (network, hand and library decoders, marginal head,
training, evaluation, the yardstick), `actor.Capture` and `learner.py --capture` (position capture),
`features.sim_view` (the simulator's public input, with the event window). Tests:
`tools/selfplay/test_simulator.py` (red before the code: the module did not exist).

**Data.**
- Players: r20 v2 (`runs/selfplay/r20_ppo/v2.pt`, loaded as r21-r23 load it: `--refresh-table
  --extend-sets M20`), sampling at temperature 1 like training games, and the heuristic. Half the
  games v2 against v2, half v2 against the heuristic, seats at random.
- Deals as current training (r21, r22): coherent decks only (`--coherent-share 1.0`), M21 with M20
  in 25% of games (`--mix-sets M20 --mix-share 0.25`), the verified pool. Fresh seeds:
  31,000,000 + i.
- 40,000 games; each seat records a share p = 0.4 of its real decisions (more than one option).
  The pilot (40 games) gave 38.7 positions per game, so about 1.55M positions.
- Held out: every game whose seed is a multiple of 25 (about 1,600 games and 62,000 positions, at
  least the plan's 50k). They are never trained on and never used for tuning.

**The yardstick** (`simulator.Yardstick`, a registered scaffold, measurement only). The coherent
generator's prior given the opponent's public cards: every colour pair those cards allow, weighted
by how likely the pair makes them; 12 basics of each colour and 36 spells drawn uniformly from the
pair's spells (independent draws: the copy limit is ignored); the hand dealt uniformly from the
cards not yet seen, the library the rest. It reads public cards only.

**Metrics** (held-out positions only).
- Hand NLL: −log P(the opponent's whole hand), in nats per position: the simulator's hand decoder,
  the yardstick's formula. Mean per position, overall and by turn.
- Mid-game: game turns 7-12 (`world.turn` counts both players' turns; in the pilot the median game
  lasts 18 turns, so this is its middle third).
- R_mid: mean simulator hand NLL / mean yardstick hand NLL over mid-game positions, with a 95%
  interval from a bootstrap over games (2,000 resamples). R_all likewise over all positions.
- Per-card calibration error: the expected calibration error (ECE) of the marginal head's P(card in
  hand) over all held-out (position, pool card) pairs, 15 equal-mass bins
  (TRAINING_REVIEW_PROTOCOL §8.4). Beside it, because with about 3 cards in hand out of ~260 pool
  cards most predictions are near zero and dilute the ECE (protocol I4): the maximum bin error, the
  ECE over each position's 24 likeliest cards (what the belief tokens will read), the Brier
  reliability and resolution, and the yardstick's ECE.
- Event window: mid-game hand NLL with the window / without it.
- Context, not gated: library NLL given the true hand; per set; per kind of opponent (network or
  heuristic); the marginal head against frequencies sampled from the hand decoder (2,000 positions,
  64 hands each).

**The gate** (§12, scored exactly as written).
- G1, "hand NLL on 50k held-out positions is at most the yardstick's": R_all ≤ 1.
- G2, "at least 5% lower by mid-game": R_mid ≤ 0.95.
- G3, "per-card calibration error is below 0.05": ECE < 0.05.
- Window, "kept if it adds at least 5%": mid-game hand NLL with the window ≤ 0.95 × without.
G1-G3 are scored on the arm the window rule keeps; both arms are reported. Each verdict is on the
point estimate; an interval that straddles its threshold is reported as such.
- On failure (any of G1-G3): capture 2.5M more positions (`--seed 2`, fresh deals) and train on
  4M (§12: "On failure: train on 4M positions"), rescored on the same held-out games. The plan
  names no kill; a second failure is reported as one.

**Training** (both arms identical except `--window`). d 256, 4 layers, 8 heads, ff 1024 (4.38M
parameters with the window); AdamW, lr 3e-4, weight decay 0.01, 200 warm-up steps then cosine to
5%; minibatches of at most 512 positions and 131k tokens; bf16 autocast; gradient clip 1.0; seed 1;
4 epochs. Loss: the joint NLL of hand and library plus the marginal head's. Allowed before the
evaluation, and recorded in §2 before it runs: changing lr and the epoch count after a pilot on at
most 150k positions of training games.

**Predictions.** G1 passes. R_mid 0.85-0.93 (G2 passes). ECE about 0.002 (G3 passes, diluted);
top-24 ECE under 0.03. The window adds under 5% (not kept): with coherent decks the red team
expected tells to be small (185, M7). Falsifier of the hypothesis: R_mid > 0.95.

**Known limits, stated before the result.**
- The per-turn table and the ledger are Phase 1 (§7), so the window is compared against no history
  at all: a pass overstates what it adds over the table; a fail is the stronger reading.
- The yardstick gets every public card; the simulator's view keeps only the newest 16 graveyard and
  10 exile cards (`features.GRAVE_KEEP`, `EXILE_KEEP`), so the comparison slightly favours the
  yardstick.
- The opponent predicted is v2 in about 75% of positions and the heuristic in the rest: the
  simulator learns these players' habits, as §5 intends.

**Resources.** Capture about 2.5 h (10 workers, nice 10, beside the E1 agent's run); training about
1 h per arm; evaluation under 30 min. Memory: the run floor is 15 GB available, the jobs stay under
15 GB.

## 2. Tuning, recorded before the held-out evaluation (2026-11-06, 19:55)

The pilot (§1's allowance; scratch `pilot.py`): the capture's first four shards, trained on the
125,112 positions of games with seed % 25 not in {0, 1} and validated on the 5,429 positions of
games with seed % 25 == 1. The held-out games (seed % 25 == 0) were never loaded. 4 epochs each:

| Config | val hand NLL | mid-game | library NLL |
|---|---|---|---|
| lr 3e-4, no window | 12.03 | 14.42 | 67.35 |
| lr 1e-3, no window | 11.89 | 14.32 | 66.86 |
| lr 1e-3, window | 11.91 | 14.29 | 67.59 |
| the yardstick, same positions (orientation only) | 12.51 | 15.06 | 63.72 |

All three were still improving at the last epoch, with no instability. **Decision: lr 1e-3 for both
arms**; 4 epochs, everything else as §1. Seen in passing: on the pilot the window adds 0.2% in
mid-game, so the prediction that it will not be kept stands.

The capture ran at 89e00a0 from a pinned worktree: 40,000 games, about 33-35k positions per
1,000 games (§1 estimated 38.7 from the 40-game pilot), so about 1.37M positions and about 54k
held-out, above the plan's 50k.
