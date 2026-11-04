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
| `search.py` | Decision-time search: determinised forks, candidate acts, attack plans, block plans, leaf value. |
| `model.py` | Transformer over [global, me, opponent, cards..., options...]; pointer logits per option, tanh value from the global token. Card token = name embedding + mean component-token embedding (`ir_tokens` of the compiled tree) + live state. Name dropout makes it read components too. |
| `actor.py` | Worker processes. Each runs N game threads with baton passing (one runs at a time, so no engine races); network decisions of one slot group go to the learner in one message while the other group runs. No torch in workers. |
| `learner.py` | GPU inference server (batches all workers' asks), BC, PPO (GAE, clipped policy + value, entropy, KL stop; `trainer.py` + `ppo.py` with `--trainer-proc`), expert iteration, curricula with gates and frozen versions, Elo, duplicate-format evaluation on fixed deals. |

## Training paths

**Curriculum (`--curriculum`, the owner's plan of 2026-11-03).**
1. *Teacher inter-play*: heuristic-vs-heuristic games, behaviour cloning (`--bc-games`). The
   result is frozen as `v0`.
2. *Against the teacher*: PPO with the heuristic as the only opponent until a frozen copy of the
   learner scores `--teacher-gate` against it (Wilson lower bound above 0.5) or
   `--teacher-iters` pass. The evaluated weights become `v1`.
3. *Gated frozen self-play*: PPO against the newest frozen version (plus a few games against
   older versions and the heuristic). Every `--gate-every` iterations the learner plays a gate
   match on `--gate-deals` fixed deals; `--gate-score` with the lower bound above 0.5 freezes the
   evaluated weights as the next version. `--kl-anchor` pulls the learner toward the newest
   frozen version.

**Ratings.** Elo by Bradley-Terry over every game between frozen players (`fit_elo`), with
**uniform random = 0** (a seat choosing uniformly among the offered options at every ask). One
virtual draw per pair keeps lopsided results finite. Far from random, a 100% score only bounds a
gap from below, so each new version is placed through its neighbours (previous version, the
heuristic) and the chain carries the anchor; read gaps between neighbours as the precise part.

**Decision-time search (`eval+search`, `learner+search`; `search.py`).** At main-phase asks, at
the pre-combat boundary (whole attack plans) and, with `--search-blocks`, at the engine's opt-in
pre-blocks boundary (whole block assignments), the top candidates are played forward in copies
of the game whose hidden zones were re-sampled from public information, through the opponent's
next turn, and scored by the outcome or the value head; candidates share sampled worlds. v1 +
search: 0.651 vs the heuristic, +0.060 over raw v1 (KNOWLEDGE/2026-11-03/183 §25).

**Expert iteration (`--adapt exit`).** The searching network plays; its played moves (soft
targets, `--search-tau`) and the outcomes are distilled into the network; repeat. Stalls at this
data scale (~1.6K clear search corrections per generation, half the changes are ties; /183 §16).
**PPO (`--adapt ppo`, the default)** is what improves the raw network (/183 §19, §22).

**Resuming (`--resume DIR`).** Both curricula save `state.pkl` (iteration, stage, versions, rating
games, ExIt data windows) with `last.pt` and every `v<k>.pt`; resume into the same directory to
keep one metrics history. PPO's AdamW moments restart.

## Run

```
.venv/bin/python -m tools.selfplay.learner --run runs/selfplay/NAME --curriculum \
    --workers 18 --slots 8 --d 512 --layers 8 --heads 8 --ff 2048 --bc-games 16000 \
    --teacher-iters 40 --steps 98304 --mb 4096 --tok-budget 131072 --lr 1e-4 --kl-anchor 0.01
.venv/bin/python -m tools.selfplay.learner --run runs/selfplay/EVAL --init CKPT --eval-only \
    --eval-seat eval+search --eval-opponents heuristic,random
.venv/bin/python -m tools.selfplay.paired A/eval_rows.jsonl B/eval_rows.jsonl
.venv/bin/python -m tools.selfplay.vs_legacy --new CKPT --old teacher
```

`runs/` is gitignored. Metrics: `runs/selfplay/NAME/metrics.jsonl` (events `bc_gen`,
`bc_epoch`, `iter`, `eval`, `gate`, `freeze`, `elo`, `progress` every `--progress-every` s).
Checkpoints: `bc.pt`, `last.pt`, `best.pt` (last gate passed), `v<k>.pt` (frozen versions).

PPO throughput: workers play during an update and no new training game is issued while a full
next batch waits (`throttled`); serve with `--infer-bf16` (KL to the trainer's numerics ~1e-5,
`bf16_logp.py`). Engine changes must keep `games_hash.py` unchanged.

Diagnostics: `distill_probe.py` / `distill_lab.py` (does distillation absorb the search?),
`label_noise.py` (search-label reproducibility), `clear_changes.py` (what the search corrects),
`games_hash.py` / `zone_identity.py` (an engine optimisation leaves games identical).

Evaluation: `--eval-deals` fixed deals (seeds 900000+), half stress and half coherent decks, each
played twice with seats swapped; greedy play; a crash or a leaky ask (CHOOSE_NAME lists hidden
cards) voids the pair. Score = (wins + draws/2) / games, Wilson 95% interval.

Memory: workers ~0.55 GB RSS each, learner ~1-3 GB plus GPU. Never run the full worker count
while the vLLM engine is resident (AGENTS.md §1).

## Tests

`.venv/bin/python -m pytest tools/selfplay -q` (about 15 s): hidden-information metamorphic
test (rewriting the opponent's hand and both libraries leaves the encoding byte-identical),
encoding consistency over whole games, heuristic vs uniform random, option-permutation
equivariance, batch-padding invariance and save/load round-trip, packed collation, block plans
made and answered at the pre-blocks boundary, and that boundary being opt-in.
