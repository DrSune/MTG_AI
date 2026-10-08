# 57 — T5-G Gameplay eval v1: per-ask accuracy does NOT translate to gameplay wins

Date: 2026-10-08 (run 20:5x, 5m25s wall, 4 CPU workers, engine-off lanes, GPU free)
Command: `.venv/bin/python tools/eval/gameplay_eval.py --games 120 --workers 4 --device cpu --seed-base 0`
Gate: `.venv/bin/python -m pytest tools/eval -q` → 4 passed
Output: `tools/eval/gameplay_eval_v1.json` (240 games, per-game records)

## Denominator truth (finding #1)
- **0/386** scenario packs in `tools/scenarios/*.json` support 2-seat full games — all are
  scripted `cards/steps/expect` puzzle rigs. No pack-vs-pack gameplay universe exists.
- Authorized fallback used: the `games.py` deck-supply campaign rig (same runner as batch-6/7
  ELO). Universe: pool_mode=engine (285 cards), seeds 1..120, deck_pairs_seed 1409, TURN_CAP 60,
  seat-swap alternating (E7), both matchups share identical seeds/deals (paired design).

## Result table (policy = bc7_S3_s1_best.pt, plays both seats)
| matchup | G | W | D | L | crash | wr(decisive) | ci95 | avg turns | v0 pol | v0 base |
|---|---|---|---|---|---|---|---|---|---|---|
| vs RANDOM (uniform legal) | 120 | 58 | 4 (all turn-cap) | 57 | 1 | **0.504** | [0.414, 0.594] | 31.5 | 0.458 | 0.507 |
| vs TEACHER (golden script: first action, never passes) | 120 | 61 | 0 | 58 | 1 | **0.513** | [0.424, 0.601] | 26.8 | 0.488 | 0.980 |

- Illegal-action attempts: **0 / 4,970 provider answers** (engine re-validation gate, C15 — verified, not assumed).
- Engine exceptions: 2/240 games = **one unique deal** (seed 9, swap-off): deterministic engine
  `AssertionError` (no message), identical in both matchups → engine bug to file, NOT policy-caused
  (model_errors 0, illegal 0). 0.8% same order as batch-7's 5/2400 (0.2%) crash scatter.
- Asks: presented 10,179 / answered via provider 10,017 / auto-resolved forced 162 (1.6%, T5-F1).
- Model ask-truncations: 2,388/2,848 (84%) vs random matchup — full-game world snapshots routinely
  exceed the sequence budget (known collector regime, in-distribution, but worth a census).
- Policy pass-rate on answered asks: 0.2% (ask-lane surfaces are mostly non-declinable choices).

## Structural caveats (reported, not hidden)
- **Provider lane = asks lane** (finding #2): the seat policy answers engine ask-sites (may/scry/
  choose/PASS); WHICH spell/attack remains on the shared seeded `RandomPolicy` act driver —
  identical skeleton both seats, both matchups. Winrates measure ask-decision contribution inside
  a shared random skeleton; the skeleton + deck pairing dominates the outcome.
- Greedy TEACHER (take-first-action, zero game knowledge) is itself ≈ 0.51 vs random → in this
  rig ask decisions carry near-zero outcome leverage; BC ≈ TEACHER ≈ RANDOM within ±0.09.

## Interpretation (bounded by measurement power)
- At n=119-120 decisive/matchup, ci half-width ≈ ±0.09: any ask-lane win-rate effect below ~9pts
  is undetectable at 240 games. To resolve a 3-pt gameplay effect needs ~3,600 games/matchup
  (~2.7h at measured 1.35 games/s CPU) — OR a higher-leverage decision surface (act-side policy
  hook, full-agency seats). Gameplay at THIS scale cannot confirm nor deny a per-ask edge.
- This does NOT retract per-ask accuracy results (different, more sensitive measurement); it
  retracts nothing from batch-7 (that rig measured policy-vs-policy on identical rules; here the
  shared random skeleton is the point). It says: game winrate is a low-SNR readout of ask quality
  in the current rig. Next lever candidates: act-side policy interface, or outcome-attributed
  ask-subset metrics instead of raw winrate.
