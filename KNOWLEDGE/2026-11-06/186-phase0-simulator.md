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

## 3. State at hand-over (2026-11-06 21:37; the gate is NOT scored yet)

**Built and tested** (branch `phase0/simulator`): capture (`actor.Capture`, `learner --capture`),
`features.sim_view` (+ event window), `simulator.py` (network, decoders, marginal head, train,
eval, yardstick). `pytest tools/selfplay/test_simulator.py` 5 passed (red before: module absent;
the leak test fails on two injected leaks, `experiments/e0_mutation_check.py window|public`).
Gates at 284906c: `pytest MTG_bot -q` 5091 passed / 39 deselected / 71 subtests; `pytest tools
-q` 144 passed (at 1d54ea8); `tools/run_scenarios.py` 738/738.

**Data** (done): `runs/simulator/e0_capture/capture` (40 shards, 5.6 GB, at 89e00a0): 40,000 games,
0 void, 1,388,124 positions, 54,886 held out (1,600 games); every opponent card accounted for at
every position, 0 held-out labels outside the masks (`experiments/e0_check_full.py`). Yardstick on
the held-out positions alone: hand NLL 12.81, library 63.63, finite everywhere.

**Running** (nohup, from the pinned worktree `../MTG_AI-sim-run` at 284906c; lr 1e-3, 4 epochs):
- PID 1993685, no window: `runs/simulator/e0_sim_nowin.pt`, log `e0_sim_nowin.out`; epoch losses
  154.76, 138.18; expected end ~22:30.
- PID 1993686, window: `e0_sim_win.pt`, log `e0_sim_win.out`; 155.47, 138.18; end ~22:45.
- Each epoch overwrites the .pt; snapshots `e0_sim_{nowin,win}_ep{0,1}.pt` exist (the copying
  loop lived in the agent's session and may have stopped).
Progress: `grep -h epoch runs/simulator/e0_sim_{nowin,win}.out | tail -4; ps -p 1993685,1993686`.

**To score E0 as pre-registered** (from `../MTG_AI-sim-run`, repo root paths):
```
for a in nowin win; do .venv/bin/python -m tools.selfplay.simulator eval --data runs/simulator/e0_capture/capture --ckpt runs/simulator/e0_sim_$a.pt --out runs/simulator/e0_eval_$a.npz; done
PYTHONPATH=. python tools/selfplay/experiments/e0_score_e0.py runs/simulator/e0_eval_nowin.npz runs/simulator/e0_eval_win.npz   # G1-G3 + window rule
PYTHONPATH=. python tools/selfplay/experiments/e0_consistency.py runs/simulator/e0_sim_<kept>.pt 2000 64 runs/simulator/e0_capture/capture
PYTHONPATH=. python tools/selfplay/experiments/e0_next_card.py runs/simulator/e0_sim_<kept>.pt runs/simulator/e0_capture/capture
PYTHONPATH=. python tools/selfplay/experiments/e0_epoch_curve.py runs/simulator/e0_capture/capture runs/simulator/e0_sim_nowin_ep{0,1}.pt runs/simulator/e0_sim_nowin.pt
PYTHONPATH=. python tools/selfplay/experiments/e0_bench_cost.py runs/simulator/e0_sim_<kept>.pt runs/simulator/e0_capture/capture   # on a quiet GPU
```
Retrain: `experiments/e0_launch_train.sh <commit>`. After the verdict: `git apply
experiments/remove_window.patch` if the window is rejected, then `remove_yardstick.patch` once
the simulator beats the yardstick and NUMBERS records it (both tested: 5 then 4 tests pass). On a
gate failure: capture with `--seed 2` (fresh deals) up to 4M positions and retrain on both dirs.

**Timings so far.** Capture: 435 positions/s at 10 workers over the run (12.5 games/s, 3,191 s),
532/s over the last 20 shards; `features.sim_view` 0.21 ms per decision (p90 0.28). Training:
33.2 min/epoch without the window, 37.2 with it (0.76 / 0.85 s per step of ≤512 positions, both
arms on one shared GPU); RSS 12.1 GB peak (loading), 8.0 GB steady; GPU peak per training step
3.7 GB. Inference, measured only on the untrained smoke model under heavy GPU contention (upper
bounds, re-measure): one belief 23 ms (batch 1), 47 ms (128 decisions); one hand 98 ms, 32 hands
108 ms; hand + library contents + next 3 or 5 cards 1.25 s (1 world), 1.75 s (32 worlds): the
library decoder emits the whole contents (~47 sequential steps, no KV cache), so the next 3 and
the next 5 cost the same.

**Known problems.** Gate unscored. Library sampling costs ~l decoder steps (KV caching would cut
it). Hand + next 3/5 quality needs the library order, which capture does not record (BACKLOG
study); the k = 1 next-card NLL is `e0_next_card.py`.

## 4. Result (2026-11-08, scored as pre-registered)

Scored by the unattended queue (`runs/phase0/sim.log`; code 75ae5aa; `simulator eval` on both arms,
`e0_score_e0.py`, then the context scripts; outputs `runs/phase0/e0_*.json`) on the 54,886 held-out
positions (1,600 games).
- **Window:** mid-game hand NLL with / without 0.9986 [0.9973, 0.9999] (all positions 0.9967): not
  kept (the rule needs 0.95). The no-window arm is scored. Prediction (§2, not kept): hit.
- **G1** R_all 0.889 [0.886, 0.892] <= 1: pass. **G2** R_mid (turns 7-12) 0.883 [0.879, 0.886] <= 0.95:
  pass. **G3** ECE 0.0004 < 0.05: pass (max bin error 0.0019; over each position's 24 likeliest cards
  0.0025, the yardstick's 0.027). **E0 passes.**
- Context: hand NLL ratio early (turns 0-6) 0.975, late (13+) 0.821; M20 0.892, M21 0.888; against
  network opponents 0.877, the heuristic 0.930. Library NLL given the true hand 1.012x the yardstick's
  and next-card NLL 1.0008x: no better than the prior. The marginal head against 64 sampled hands per
  position (2,000 positions): corr 0.91, mean |difference| 0.017 against a sampling floor of 0.014.
  Hand NLL by epoch 11.71, 11.52, 11.42, 11.38: still falling at the fourth.
- **Costs** (the trained model, a quiet GPU; `e0_bench_cost.py`): belief 4.3 ms at batch 1, 10.8 ms
  for 128 decisions; one hand 22 ms, 32 hands 26 ms; hand + library contents + next 3 or 5 cards
  241 ms (1 world), 403 ms (32 worlds); hand + next 3-5 from the marginal head's counts 26-31 ms; a
  training step 266 ms per 512 positions, 3.8 GB peak.
- Then, as §3 planned, `remove_window.patch` and `remove_yardstick.patch` (the yardstick existed only
  to score E0; the BACKLOG study can restore it from this commit's parent). test_simulator: 4 passed.

What it means: the simulator reads the opponent's hand clearly better than the deck-consistent
prior, more so as the game goes on (the history is evidence), with honest probabilities. Its picture
of the remaining library is no better than the prior's, so the next 3-5 cards add nothing yet (the
BACKLOG study "How far to take the opponent simulator"; capture records no library order).
