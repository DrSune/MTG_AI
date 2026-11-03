# tools/selfplay — per-seat entity transformer, BC warm start, PPO self-play

Started 2026-11-03 (Claude, taking over from the local agent; KNOWLEDGE/2026-11-03/182).

## Why a new stack

The live `PointerBC` (`tools/training/bc_model.py`) cannot become a strong player as built:

- **It sees hidden information.** Its observation (`ab_duel.snapshot_obs`, `bc_data_v2`) holds
  both hands and the top of both libraries. OWNER_PREFERENCES #1 forbids play built on that.
- **Train/play mismatch.** The docstring says causal, but `TransformerEncoderLayer` runs with no
  mask, so in training every decision attends to the observations that follow it (which reveal
  the action taken), while at play time only the past exists. Measured: changing only tokens
  30-39 moves the hidden state at position 10 by 1.31 (max abs), and full-stream vs prefix-only
  differs by 1.99 (KNOWLEDGE/2026-11-03/182).
- **Throughput.** One un-batched CPU forward per decision: 0.25 games/s on 6 workers (/147).

This stack replaces the observation, the network and the training loop. The engine, the bench
protocol (`MTG_bot/bench`) and its seat router are reused unchanged.

## Pieces

| File | What |
|---|---|
| `features.py` | One decision -> arrays: card entities (vocab id, zone, controller, owner, flags, types, colours, keywords, live P/T, damage, counters), two player rows, global row, the ask kind, one row per option (type + the entities it points at). Only what the seat may know: own hand, public zones, counts, cards offered or revealed to it. |
| `heuristic.py` | Rule-based player for the bench protocol: the anchor opponent and the BC teacher (rules in its docstring). Beats uniform random ~96%. |
| `rig.py` | `SeatRouter` subclass adding the per-ask context the engine has not applied yet (scried card, attackers and blockers declared so far this combat); `play_game`. |
| `model.py` | Transformer over [global, me, opponent, cards..., options...]; pointer logits per option, tanh value from the global token. Card token = name embedding + mean component-token embedding (`ir_tokens` of the compiled tree) + live state. Name dropout makes it read components too. |
| `actor.py` | Worker processes. Each runs N game threads with baton passing (one runs at a time, so no engine races); network decisions of one slot group go to the learner in one message while the other group runs. No torch in workers. |
| `learner.py` | GPU inference server (batches all workers' asks), BC, PPO (GAE, clipped policy + value, entropy, KL stop), league of frozen snapshots, duplicate-format evaluation vs the heuristic on fixed deals. |

## Run

```
.venv/bin/python -m tools.selfplay.learner --run runs/selfplay/NAME --workers 18 --slots 8 \
    --bc-games 20000 --iters 300 --steps 65536
```

`runs/` is gitignored. Metrics: `runs/selfplay/NAME/metrics.jsonl` (events `bc_gen`,
`bc_epoch`, `iter`, `eval`). Checkpoints: `bc.pt`, `last.pt`, `best.pt` (best eval vs heuristic).

Evaluation: `--eval-deals` fixed deals (seeds 900000+), half stress and half coherent decks, each
played twice with seats swapped; greedy play; a crash or a leaky ask (CHOOSE_NAME lists hidden
cards) voids the pair. Score = (wins + draws/2) / games, Wilson 95% interval.

Memory: workers ~0.55 GB RSS each, learner ~1-3 GB plus GPU. Never run the full worker count
while the vLLM engine is resident (AGENTS.md §1).

## Tests

`.venv/bin/python -m pytest tools/selfplay -q` (about 10 s): hidden-information metamorphic
test (rewriting the opponent's hand and both libraries leaves the encoding byte-identical),
encoding consistency over whole games, heuristic vs uniform random, option-permutation
equivariance, batch-padding invariance and save/load round-trip.
