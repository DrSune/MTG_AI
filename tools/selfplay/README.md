# tools/selfplay — per-seat entity transformer, BC warm start, PPO self-play

Started 2026-11-03 (Claude, taking over from the local agent; KNOWLEDGE/2026-11-03/182).

## Why a new stack

The `PointerBC` this stack replaced (`tools/training/bc_model.py`, deleted 2026-11-05;
`git show dbd6e9d:<path>`) could not become a strong player as built:

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
| `features.py` | One decision -> arrays: card entities (vocab id, zone, controller, owner, flags, types, colours, keywords, live P/T, damage, counters), two player rows, global row, the ask kind (the second main phase's act menu is its own kind, `act_second_main`; the mulligan before the first turn asks `mulligan`, keep or mulligan, and `mulligan_bottom`, a card of the hand), one row per option (type + the entities it points at). Only what the seat may know: own hand, public zones, counts, cards offered or revealed to it. |
| `heuristic.py` | Rule-based player for the bench protocol: the anchor opponent and the BC teacher (rules in its docstring). Beats uniform random ~96%. |
| `rig.py` | `SeatRouter` subclass adding the per-ask context the engine has not applied yet (scried card, attackers and blockers declared so far this combat); `play_game`. |
| `search.py` | Decision-time search: determinised forks, candidate acts, attack plans, block plans, leaf value. |
| `model.py` | Transformer over [global, me, opponent, cards..., options...]; pointer logits per option, tanh value from the global token. Card token = name embedding + mean component-token embedding (`ir_tokens` of the compiled tree) + live state. Name dropout makes it read components too. `load` grows an older checkpoint's ask and option-type embeddings: an appended row starts as what it was encoded as before (`features.ASK_GROWN_FROM`: `act_second_main` from `act`; the mulligan kinds and the `keep`/`mulligan` options from `other`, so an old network playing greedily keeps). |
| `actor.py` | Worker processes. Each runs N game threads with baton passing (one runs at a time, so no engine races); network decisions of one slot group go to the learner in one message while the other group runs. Workers do no torch work (spawn still imports torch in them: it re-imports `learner.py` as each worker's main module). |
| `learner.py` | GPU inference server (batches all workers' asks), the curriculum (teacher inter-play BC for a network trained from scratch, then PPO against the teacher and gated frozen self-play), duplicate-format evaluation on fixed deals, Elo, resume, run manifest. |
| `ppo.py`, `trainer.py` | The PPO update (GAE advantages from the learner; clipped policy and value loss, entropy bonus, KL early stop) and the process it runs in, so the workers keep playing during an update. |
| `trace.py`, `report.py`, `paired.py` | Read one game decision by decision; one-screen status of a run; paired comparison of two evaluations on the same deals. |

## Training: the curriculum (the owner's plan of 2026-11-03)

1. *Teacher inter-play* (only for a network trained from scratch: `--bc-games`, no `--init`):
   heuristic-vs-heuristic games, behaviour cloning on both seats' moves and the outcomes
   (`--bc-*`). A run started with `--init` skips it.
2. *Against the teacher*: PPO with the heuristic as the only opponent until a frozen copy of the
   learner scores `--teacher-gate` against it (Wilson lower bound above 0.5) or
   `--teacher-iters` pass. The evaluated weights become the next version.
3. *Gated frozen self-play*: PPO against the newest frozen version, plus older versions
   (`--p-past`) and the heuristic (`--p-heuristic`) so it does not forget how to beat them.
   Every `--gate-every` iterations the learner plays a gate match on `--gate-deals` fresh deals;
   `--gate-score` with the lower bound above 0.5 freezes the evaluated weights as the next
   version (/183 §27: freeze on significance).

The network the run starts from is frozen as `v0`. PPO (/183 §19, §22) is what improves the raw
network; expert iteration (search distillation) stalled at this data scale and was removed, as
were the separate value network, the rollout network and the KL anchor to the frozen version
(/183 §16-§17, §10-§13, §23). Each update runs in `trainer.py`'s process while the learner keeps
serving the workers on the current weights; no new training game is issued while a full next
batch waits (`throttled`). Serve with `--infer-bf16` (KL to the trainer's numerics ~1e-5, §20).

**Card pool (`--pool`, default `verified`).** Every game, training, mixed-set and evaluation,
deals from one pool mode of `MTG_bot/core/executor/games.py` `compile_supply`: `verified` (cards
whose current compiled tree passed play-time verification; M21: 263 cards), `compiled` (whole
text compiled; M21: 281) or `castable` (also partly parsed cards; equal to compiled on M21).
The learner stops at start when a dealt set has no card in the pool, and a resume refuses a
pool other than the one its run dealt from. `--mix-sets` deals a `--mix-share` of training
games from other sets (they must also be in `--extend-sets`, which gives their cards table
rows; it applies to a run started with `--init`); `--eval-set` picks the evaluation set.

**Ratings.** Elo by Bradley-Terry over the ladder games of frozen players (`fit_elo`), with
**uniform random = 0** (a seat choosing uniformly among the offered options at every ask). One
virtual draw per pair keeps lopsided results finite. Each new version plays random, the
heuristic and its predecessor on the fixed ladder deals; gate games never enter the ratings (a
freeze is selected on them). Read gaps between neighbours on the ladder as the precise part.

**Decision-time search (`eval+search`; `search.py`).** The deployed model (/183 §25). At
main-phase asks (both main phases), at the pre-combat boundary (whole attack plans) and, with `--search-blocks`, at
the engine's opt-in pre-blocks boundary (whole block assignments), the top candidates are
played forward in copies of the game whose hidden zones were re-sampled from public
information, through the opponent's next turn, and scored by the outcome or the network's own
value head; candidates share sampled worlds. v1 + search: 0.651 vs the heuristic, +0.060 over
raw v1 (§25).

**Resuming (`--resume DIR`).** `state.pkl` (iteration, stage, versions, rating games, job ids,
the opponent-draw RNG, gate count, queued evaluations, pool) is saved with `last.pt` and every
`v<k>.pt`; resume into the same directory to keep one metrics history. A resume skips the
teacher inter-play stage and must use the run's `--pool` (state files from before 2026-11-05:
`castable`). PPO's AdamW moments restart; an evaluation still running when the run stopped is
not resumed (queued ones are).

**Run manifest.** Each start of the learner, a resume included, appends an entry to
`<run>/manifest.json`: the parsed arguments, the git commit and whether the tree is dirty (with
`git status --porcelain`; untracked files count, since card records on disk change the pools),
host, Python and torch versions, start time.

## Run

```
# the canonical run (r17)
.venv/bin/python -m tools.selfplay.learner --run runs/selfplay/r17_ppo \
    --init runs/selfplay/r16_ppo/last.pt --refresh-table --infer-bf16 --workers 18 --slots 16 \
    --groups 4 --steps 98304 --mb 4096 --tok-budget 98304 --epochs 1 --lr 5e-5 --target-kl 0.03 \
    --ent 0.002 --teacher-iters 20 --teacher-gate 0.65 --eval-every 5 --eval-deals 200 \
    --gate-every 5 --gate-deals 300 --gate-score 0.5 --ladder-deals 150 --p-heuristic 0.15 \
    --p-past 0.15 --iters 3000 --save-every 1 --mem-floor-gib 12
# continue it: the same command plus --resume runs/selfplay/r17_ppo --pool castable (r17 dealt
# castable cards; a run on the verified pool starts from its weights: --init .../r17_ppo/last.pt)
# from scratch: teacher inter-play first
.venv/bin/python -m tools.selfplay.learner --run runs/selfplay/NAME --workers 18 --slots 16 \
    --groups 4 --d 512 --layers 8 --heads 8 --ff 2048 --bc-games 16000 --teacher-iters 40 \
    --steps 98304 --mb 4096 --tok-budget 98304 --epochs 1 --lr 1e-4 --ent 0.002 --infer-bf16
# evaluate a checkpoint with decision-time search (the deployed model, /183 §25)
.venv/bin/python -m tools.selfplay.learner --run runs/selfplay/EVAL --init CKPT --eval-only \
    --eval-seat eval+search --eval-opponents heuristic --eval-deals 150 --search-k 3 \
    --search-d 2 --search-skip-p 0.99 --infer-bf16
.venv/bin/python -m tools.selfplay.paired A/eval_rows.jsonl B/eval_rows.jsonl
.venv/bin/python -m tools.selfplay.report runs/selfplay/NAME
.venv/bin/python -m tools.selfplay.trace --net CKPT --opp heuristic --seed 900007 --out /tmp/t.txt
```

Before 2026-11-05 the training command also carried `--curriculum --adapt ppo --trainer-proc
--kl-anchor 0`; those flags selected what is now the only behaviour and are gone. Runs before
then dealt `castable` cards (`--pool castable` reproduces that).

`runs/` is gitignored. Metrics: `runs/selfplay/NAME/metrics.jsonl` (events `iter`, `eval`,
`teacher_gate`, `stage`, `gate`, `freeze`, `elo`, `bc_gen`, `bc_data`, `bc_epoch`, `progress`
every `--progress-every` s, `init`, `refresh_table`, `resume`, `mem_floor`). Checkpoints:
`bc.pt`, `last.pt`, `best.pt` (last gate passed), `v<k>.pt` (frozen versions); `state.pkl`,
`manifest.json`, `eval_rows.jsonl` (one row per evaluation game).

Evaluation: `--eval-deals` fixed deals (seeds 900000+), half stress and half coherent decks, each
played twice with seats swapped; greedy play; a crash or a leaky ask (CHOOSE_NAME lists hidden
cards) voids the pair. Score = (wins + draws/2) / games, Wilson 95% interval. A deal is (set,
pool, seed, deck mode): `paired.py` pairs only rows with all four equal.

An engine optimisation must leave seeded games identical (/183 §21, §24; the checkers
`games_hash.py` and `zone_identity.py` are at commit 2dd34a3).

Memory: workers ~0.55 GB RSS each, learner ~1-3 GB plus GPU. Never run the full worker count
while the vLLM engine is resident (AGENTS.md §1).

## Tests

`.venv/bin/python -m pytest tools/selfplay -q` (39 tests, about 32 s under the r19 training load on 2026-11-06): hidden-information
metamorphic test (rewriting the opponent's hand and both libraries leaves the encoding
byte-identical), encoding consistency over whole games, heuristic vs uniform random,
option-permutation equivariance, batch-padding invariance and save/load round-trip, packed
collation, block plans made and answered at the pre-blocks boundary, that boundary being
opt-in, bounded feature caches, scry context, card-table extension and refresh, counters and
ask kinds reaching the encoding, the two main phases' act menus encoding apart, combat planned
once per turn before combat, GAE bootstrap of a cut-off game, the run manifest, and the
heuristic's rules on arranged boards (a raid creature cast after its attack among them), and the
mulligan: the network and the heuristic both answer it, and a checkpoint from before it loads and
plays.
