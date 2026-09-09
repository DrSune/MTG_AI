# Backlog

Everything parked, with the reason it is parked. Two rules for this file.

1. **When an idea does not move the ladder in [`NORTH_STAR.md`](../NORTH_STAR.md), it lands
   here rather than being built.** Say so out loud when you park something.
2. **Every hard limit, cap, or schedule added anywhere in the codebase gets an entry under
   "Scaffolds to remove", with the condition that would let it go.** Never add one silently.

---

## Scaffolds to remove

Things currently hardcoded that the learnability principle says should not be. None of these
are neutral; each one is teaching the agent something.

| Scaffold | Where | Removal condition |
|---|---|---|
| **Thirteen shaping reward terms** — damage, life, board presence, board delta, cards, action discovery, mana generation, proactivity, penalties | `strategic_brain/environment.py:164-211` | Replace with outcome plus at most a couple of defensible terms. A 200-step game currently accrues about +20 of shaping against ±10 for the actual result, so the agent is optimising the shaping. Remove once the engine is correct enough that winning is learnable directly. |
| **Proactivity bias** — subtracts up to 10 nats from every pass action's logit | `strategic_brain/student.py:126-129` | Delete. It is applied at collection but not at training, which pins the PPO ratio to e^±10 on every pass action. It exists to fight "the agent passes", which is a symptom of the reward and the dead action space, not of the policy. |
| **`MAX_MOVES_PER_STEP = 500`** | `rule_engine/engine.py` | Replace with the loop detection in [`DESIGN_INFINITIES.md`](DESIGN_INFINITIES.md) plus a wall-clock truncate-and-bootstrap. Currently it pays −10 to whoever found a combo. |
| **Five-repeat action block** | `strategic_brain/train.py:169` | Same. A combo body executed five times is exactly this pattern, so the anti-stall heuristic is a combo filter. |
| **100-step stall detector and forced mana stripping** | `strategic_brain/train.py:160,180-183` | Same. It dismantles a combo's mana engine mid-assembly. |
| **Epsilon-greedy exploration with a 0.15 floor** | `strategic_brain/train.py:94` | Replace with an entropy bonus in the loss. At 0.31, a third of all actions are uniform random and the policy is decoration. |
| **Four `1 - games/10000` difficulty ramps, a CMC step function, and a permanent SQL ban on every life-gain card** | `strategic_brain/teacher.py` | Replace with a self-play league. The "teacher" itself takes no optimizer step, so it is a frozen random MLP blended 50/50 with `random.random()`. |
| **Seven cards special-cased by literal name string** | `rule_engine/card_data_loader.py:86-119`, `rule_engine/engine.py:216,326,89` | Directly violates this project's own `EFFECT_SYSTEM_MANDATES.md`. Remove when the ability tree in [`DESIGN_CARD_POOL.md`](DESIGN_CARD_POOL.md) can express them. |
| **Hardcoded `torch.device("cuda")`** | `strategic_brain/student.py:34`, `teacher.py:37` | Route through `MTG_bot/utils/device.py`. On the dev box these silently fall back to CPU. |

---

## Your own recorded ideas that were never built

These are worth keeping because you wrote them down and the reasoning was good. Sorted by how
much they serve the King Goal.

### Directly serves rank 1

- **Self-play league / opponent pool.** Removed from the task list in commit `d29a1d6` without
  ever being built. What exists instead is a single frozen self-copy refreshed every twenty
  games, which pins win rate near 50% by construction and carries no information about absolute
  strength. The charter now names adaptive opposition as a default yes. **This is the single
  highest-value item on this list.**
- **Belief vector over hidden information.** From the 272 lines of `RL_ARCHITECTURE.md` that a
  doc rewrite destroyed in `db5e024`; recover with
  `git show db5e024^:MTG_bot/docs/RL_ARCHITECTURE.md`. It contained a recurrent belief net over
  history tokens, three named encodings for multi-opponent scenarios with a pros-and-cons table,
  deterministic bookkeeping of exact opponent card counts, optional particle sampling of
  plausible opponent states, and supervised pre-training of the belief net from self-play logs
  before end-to-end fine-tuning. It also contained the rule *"do not embed the belief vector
  into every entity token"*, which is right and which
  [`DESIGN_CARD_POOL.md`](DESIGN_CARD_POOL.md) reuses for pool tokens.
- **Frozen board cross-attention** — encode the board once per phase and have every reasoning
  pass cross-attend to it without re-encoding. Also from the destroyed doc. On the DGX this is
  not an optimisation, it is a requirement; it is the Tier A / Tier B split in
  [`DESIGN_TRAINING.md`](DESIGN_TRAINING.md).
- **Rethink compute penalty**, so the model learns the optimal stopping point rather than being
  given a fixed pass count. Exactly the right instinct — the reward pays for thinking, and the
  model learns when deeper thought is worth it.
- **Puzzle-ladder levels 3 and 4** from `progression_playbook.md`: stack interaction (responding,
  end-of-turn timing, combat tricks) and second-order thinking (playing around sweepers, bluff
  attacks, baiting counterspells). Only levels 1 and 2 exist. Levels 3 and 4 are unreachable
  until the engine has real priority.
- **Deck-space evolution to find niche decks** (`ideas.md`): an elite pool of niche decks,
  periodic re-evaluation, mutation, under-confidence sampling, a novelty reward, robustness
  testing by perturbing one card, and `R_final = R(D) + λ·Robustness(D)` with **λ annealed from
  high to low** so that early training punishes sharp minima and late training goes looking for
  them. This is the mechanism for the stated goal of being good at weird decks.

### Serves ranks 2 and 3

- **Information-set Monte Carlo tree search** with determinization. Explicitly parked in
  `tasklist.md`. Blocked on make/unmake in the engine — see
  [`DESIGN_TRAINING.md`](DESIGN_TRAINING.md) §5.
- **KV cache of board analysis across an action sequence.** Same idea as the Tier A cache.
- **Synthetic board-state dataset for pre-training the board encoder.**

### Product goals beyond the King Goal

- **Stockfish-style top-3 move suggestion** with a move line, so a human can set up a position
  and ask what is best. Also for drafting, both from empty and completing a partial deck.
- **Teacher by vector search** — build decks card by card via a matchup analyser emitting a query
  vector, then vector search against the card embedding pool, with matchup history and a
  diversity bonus to avoid rock-paper-scissors cycles. Every proposed matchup validated by the
  engine, illegal proposals penalised.
- **Teacher reward by matchup win-rate delta** — reward the teacher when the student's win rate
  improves a lot over a matchup, so it prioritises scenarios where there is room to grow. Plus
  mirror-matchup mastery: fifty games from each side, and if the student only wins from one side
  the matchup is broken and worth teaching.
- **Deck analysis and suggestion for human players.**
- **"Hail Mary" logic** — in desperate positions, shift from maximising expected value to
  maximising the probability of drawing a specific out. Note this is genuinely at odds with a
  pure expected-value critic and needs a distributional value head or an explicit risk parameter
  to express at all.

### Abandoned, do not revive

- Card recognition from photos and video, YouTube frame scraping, OCR, the image vector database,
  the local-LLM agent harness. All in `attic/`. Off the King Goal.

---

## Engine gaps you logged yourself

From `EFFECT_SYSTEM_MANDATES.md`, still true:

- Triggered abilities and responses resolve immediately; last-in-first-out is not enforced.
- Spells requiring choices during resolution are unsupported.
- **Replacement effects do not exist.** These are load-bearing for Commander — the command-zone
  replacement, commander tax, doubling effects, damage prevention.

Plus, found in this audit and not previously logged: no real priority, no evasion enforcement in
blocking, only the first blocker participates in combat damage, layers 1 through 6 absent, no
timestamps or dependency pass in the layer system, activated and loyalty abilities unreachable,
two players maximum.

---

## Open questions needing your decision

These are forks, not tasks. See the report that accompanied this audit.

1. **Rebuild the engine, or evolve it?** The audit's verdict is rebuild, and the reasoning is in
   [`ARCHITECTURE.md`](ARCHITECTURE.md). This is the biggest call.
2. **Ability tree first, or engine first?** The recommendation is the tree first, because it is
   the contract both the engine and the network are written against.
3. **Full-game BPTT or K=256 truncated?** Memory says it is affordable either way; the question
   is whether the 10× serial cost buys anything, and that is measurable.
4. **v0.5 at 150M or straight to v1 at 392M?** Throughput scales inversely with size.
