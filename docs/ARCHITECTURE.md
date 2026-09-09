# What actually exists today — verified audit, 2026-09-09

Written after a full read of every file at commit `96f92a6`, with claims checked by running
the code. **Where a doc in this repo disagrees with this file, this file is right** — several
of the older docs describe a system that was planned and never built.

Read this before changing anything. It exists so nobody has to rediscover it.

## The one-paragraph verdict

The rule engine runs full games end to end, but **the game it simulates is not Magic in the
ways that decide games.** Targeted spells resolve as silent no-ops. Only one player ever has
priority except in one step per turn, so there is no interaction at all — no counterspells, no
combat tricks, no instant-speed removal. Flying does not restrict blocking. One blocker blocks
every attacker and only the first one deals or takes damage. Rules layers 1 through 6 do not
exist. Activated abilities and loyalty abilities are unreachable. Every enters-the-battlefield
trigger in the set is dead. Two players maximum, in a project whose stated priority format is
Commander. A policy trained to convergence here learns a different game.

## Verified measurements

Taken on the Windows dev box, Commander, two 100-card decks, random policy.

| Metric | Before the 2026-09-09 fixes | After |
|---|---|---|
| Engine step, recorder on (the training default) | ~41 ms | — |
| Engine step, recorder off | 24.9 ms | **7.7 ms** |
| SQLite connections per step | ~70 | **0** |
| `copy.deepcopy(graph)` | 6.0 ms | unchanged |
| `get_legal_moves()` | 6.2 ms | faster, not re-measured |
| Rule-engine test suite | 1 pass, 18 errors, 3 failures of 22 | unchanged |

Graph size at a Commander start: 214 entities, 412 relationships.

## The traps

These are the things that cost hours if you do not know them.

**The card-id and vocabulary-id namespaces collide.** `game_vocabulary.id` runs 0–424 and
`cards.card_id` runs 1–397, and they share one integer axis. `Entity.type_id` holds a
`card_id` for cards and a `game_vocabulary.id` for zones and players. Card 101 "Goremand" is
literally the same integer as the Battlefield zone. It only works today because zone
relationships happen to be inserted before card relationships and lookups use `next()` over an
order-preserving list. Change the insertion order and a player's battlefield becomes a
creature. The model's card-identity embedding is scrambled with its entity-type embedding by
the same collision.

**`card_id` is an autoincrement rowid that is dropped and rebuilt on every re-ingest.** So
re-ingesting the card data renumbers every card and silently invalidates every learned
embedding row, every replay file, and every checkpoint. There is no version check. The stable
identity is MTGJSON's `identifiers.scryfallOracleId`, which is present in
`MTG_bot/data/M21.json` for all 397 cards and all 20 tokens but was discarded at ingest.

**Every targeted spell is a no-op.** The text parser emits `{"type": "selector", ...}` as a
sibling node; both consumers read `effect.get("target")`. 117 cards carry a selector, 10 carry
a `target`. So `get_spell_potential_targets` returns an empty list for every card in the set,
every targeted spell is cast with `target=None`, resolves to nothing, and goes to the
graveyard. This is why removal and burn are invisible and why the documented benchmark scores
zero. It is one key name.

**All enters-the-battlefield triggers are dead, and nothing logs it.** MTGJSON re-templated
Oracle text: **zero of 397 cards contain the string "enters the battlefield"**, and four
independent code paths test for that substring. Forty triggers silently never fire. This is
the canonical demonstration that English substrings cannot be the intermediate representation.

**The model sees hidden information.** `state_converter` iterates every entity in the graph,
which includes both players' libraries in order and both players' hands. `controller_ids` is
computed and then discarded, so the model also cannot tell its own permanents from the
opponent's. Any strength the current model shows is partly clairvoyance.

**Card data dicts are shared and mutated.** `CardDataLoader.get_card_data_by_id` returns *the
same dict object* on every call, and `Entity.properties.update()` copies only the top level.
So nested `effects` and `abilities` are shared by every instance of a card in every game in
the process, and an effect handler that appends to one contaminates every future episode.

**Lifelink never gains life.** The controller lookup at `combat_handlers.py:112` reads the
relationship in the wrong direction, so the attacker's controller is always `None`.

**Nothing is seeded and replays are not reproducible.** There is no `random.seed`,
`np.random.seed`, or `torch.manual_seed` call anywhere. Even with a seed, entity ids come from
`uuid.uuid4()`, and zone-change triggers are computed by iterating `set` differences of UUIDs,
so enters/leaves trigger ordering is non-deterministic across runs under a fixed seed.

**`MAX_MOVES_PER_STEP = 500` punishes combos as hard as a loss.** Tripping it sets
`game_over` with `winner_id = None`, and the reward function then pays **−10.0 to both
players**, while the win-rate metric separately scores the same game as a 0.5 draw. Reward and
metric disagree, and every loop the agent has ever found has been punished.

## Component map

| Path | State | Note |
|---|---|---|
| `rule_engine/game_graph.py` | live | The real state model. UUID-keyed dicts plus a flat relationship list scanned linearly. Not canonicalisable, so no state hashing and no loop detection. |
| `rule_engine/engine.py` | live | Turn loop, legal moves, stack, state-based actions. The stack lives here, not in the graph, so every recorded snapshot is structurally incomplete. |
| `rule_engine/card_data_parser.py` | live | 22 regexes with inconsistent key names. Semantics stored as raw English. |
| `rule_engine/handlers/effect_handlers.py` | live | A closed if/elif covering 9 of the 31 node shapes the parser emits. |
| `rule_engine/layer_system.py` | live, wrong | Layer 7 additive only; layers 1–6 are comments; no sublayers, no timestamps, no dependency pass. Filters match every permanent including the opponent's. |
| `rule_engine/handlers/{activated,graveyard,continuous_effect}_handlers.py` | stubs | `pass` / `return []`. |
| `rule_engine/handlers/card_specific_handlers.py` | dead | Named-card escape hatch, 100% unreachable — but the pattern leaked into the loader and the engine, which special-case seven cards by literal name string. |
| `strategic_brain/model.py` | live | 315.7M params, of which **54.4M receive no gradient, ever**. Batch dimension effectively hardcoded to 1. |
| `strategic_brain/student.py`, `train.py` | live | PPO without GAE, entropy, advantage normalisation, or gradient clipping. The experience buffer is never cleared, so ratios are computed against arbitrarily stale policies. Blocking decisions are attributed to the wrong agent. |
| `strategic_brain/environment.py` | live | Thirteen hand-tuned shaping reward terms. A 200-step game accrues about +20 of shaping against ±10 for the actual outcome. |
| `strategic_brain/teacher.py` | broken | `train_teacher` has no `backward()` and no `optimizer.step()`. The teacher is a frozen random MLP whose output is blended 50/50 with `random.random()`. |
| `strategic_brain/benchmarker.py` | broken | Crashes at HEAD. Repaired in memory, it scores a **do-nothing policy at 0.90 on "Level 2"**. It is the only external evaluation signal. |
| `scenarios/` | thin | 131 files containing 17 distinct setups; three card ids carry the whole corpus. |
| `visualizer/index.html` | dead | All five hardcoded type ids are wrong. Renders an empty board. `fetch()` over `file://` is CORS-blocked and there is no server. |
| `strategic_brain/draft_simulator.py` | keep, parked | A correct self-contained 8-player draft with the right pass direction. Imported by nothing. |
| `attic/` | archived | See `attic/README.md`. |

## The biggest structural risk

Not speed, and not the effect system. Both of those are ordinary engineering with known moves.

> **There is nothing in this repository that can tell you whether a change made the bot
> better, or whether the engine is playing Magic.**

One of 22 engine tests passes. The documented benchmark command scores 0/8, and the failure is
a combat-damage bug rather than an AI-quality signal. The benchmark's scoring function pays a
do-nothing policy 0.90. The only opponent is the agent's own weights from twenty games ago, so
win rate is pinned near 50% by construction. `RandomAgent`, `GreedyAgent`, `RuleBasedAgent`
and Elo are promised in the docs and exist nowhere.

You can see the cost in the git history. The last twelve commits are four independent
mechanisms — discovery rewards, a proactivity bias, a forced-play probability, hard then soft
action masking, a repeat cap, a stall detector — all bolted on to fight one symptom, none of
them measured, one added and reverted the same day. That is what building without a measuring
stick looks like. On a DGX you can now do it a hundred times faster.

## Fixes already applied, 2026-09-09

- `IDToNameMapper` memoised and given a `prewarm()`. Measured 3.2× on the engine loop.
- `Engine(record=...)` — recording is now **off by default** via a `NullRecorder`. Training
  was writing roughly 2,400 JSON files per episode to a shared path.
- `MTG_bot/utils/device.py` restored and extended: CUDA → XPU → MPS → CPU, with an
  `MTG_DEVICE` override. Two call sites still hardcode `torch.device("cuda")` and need fixing.
- Hardcoded Weights & Biases API key removed from the working tree. **Still live in git
  history and still needs revoking.**
- Dead legacy tree moved to `attic/`, including a second rules engine that reads like the real
  one.
- Real `pyproject.toml`, and a `.gitignore` that no longer ignores things that are committed.
