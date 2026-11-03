# 182: takeover review of the RL pilot, and the new self-play stack (2026-11-03)

Author: Claude (Opus 5.5), taking over from the local agent at the owner's request: "review its
work on MTG ... try bigger runs, more steps, and see how good you can make the model ... it
should probably be through the NN/transformer."

## 1. Review of the local agent's model work (what blocks strength)

What is good and stays: the measurement discipline (duplicate deals, Wilson/bootstrap CIs,
pre-registration, determinism audits), the bench (`MTG_bot/bench`: per-seat view, exact ask
routing, floors), the engine and card work (M21 campaign 263/281 castable verified, /177).

What blocked a strong model:

1. **Scale.** The RL pilot ran from /134 (2026-10-20) to /181 (2026-11-03) at 50-game
   iterations and 400-game probes: M1 0.5279 [0.458, 0.596], M2 0.523 [0.453, 0.592], M3 0.518
   [0.448, 0.587] (/171, /173, /174): no measurable change from the anchor. Most of the two weeks
   went to byte-identity pins, nightly windows and decision tables around a few hundred games.
2. **The live model is trained on information it does not have at play time.**
   `tools/training/bc_model.py` says "causal" but runs `TransformerEncoderLayer` with no mask;
   training encodes the whole episode stream, so each gold `<sep>` attends to the observations
   after it (which show the action taken), while `BcAsk` plays on the prefix only. Measured with
   a random-init PointerBC(d=64, L=2): changing only tokens 30-39 moves the hidden state at
   position 10 by **1.31** (max abs); full stream vs prefix-only at position 10 differs by
   **1.99**. Command: the 15-line probe in this session (`PointerBC.encode` on `x` vs `x` with
   `x[0, 30:]` resampled, and vs `x[:, :11]`).
3. **Omniscient observation.** `ab_duel.snapshot_obs` / `bc_data_v2` serialize both hands and
   the library tops, against OWNER_PREFERENCES #1.
4. **CPU, un-batched inference**: 0.25 games/s on 6 workers (/147).
5. The anchor plays the old HeuristicTeacher at **0.394** [0.347, 0.442] (/134 precondition):
   imitation is capped below its teacher, consistent with (2).

## 2. The new stack: `tools/selfplay` (README there)

Per-seat features (own hand, public zones, counts, offered/revealed cards; handles never reach
the network), a rule-based heuristic for the bench protocol (anchor + BC teacher), an entity
transformer with pointer logits over options and a value head, worker processes with
baton-passed game threads batching every network decision to one GPU server, BC warm start, PPO
with a snapshot league, and duplicate-format evaluation on fixed deals.

## 3. Numbers (2026-11-03, M21 castable, main 0bc541c)

| Number | Value | Command / source |
|---|---|---|
| tests | 4 passed | `pytest tools/selfplay -q` |
| heuristic vs uniform random | 77/80 games | 2x40 rig games, seats both ways, ad hoc |
| heuristic vs heuristic, seat 0 | 27/40 wins | first-player edge is large: always swap seats |
| encode cost | 0.074 ms/decision | 8,327 decisions, ad hoc timing |
| rig crashes | 0 in 120 games; 3 in 3,000 BC games (`POWER undefined on handle`) | m1 `bc_gen_done` |
| leaky games (CHOOSE_NAME) | 123/3,000 (4.1%) | kept for training, voided in eval |
| BC data rate | 10.6 games/s, 6 workers x 8 slots (99 decisions/game) | m1 `bc_gen` |
| BC 5.3M params (d256 L6), 3 epochs, 282k samples | held-out action agreement **0.943**; value MSE rises 0.633 -> 0.860 (overfits: BC value weight lowered to 0.25) | `runs/selfplay/m1_medium/metrics.jsonl` |
