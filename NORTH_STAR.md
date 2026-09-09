# NORTH STAR — the King Goal and the priority ladder

**Read this before doing anything else in this repository. It outranks every other document,
every backlog item, and every idea raised mid-session — including ideas raised by the project owner.**

---

## 0. The King Goal

> **Build a genuinely strong Magic: The Gathering bot for the sets it has been trained on.**

Strong means: it beats good human play with the card pool it has seen. Not "runs without crashing",
not "has an impressive architecture", not "supports many sets". Strength on the trained pool is the
only thing that counts as success. Everything else is instrumental.

## 1. The priority ladder

Work is ranked. A lower rank never displaces a higher one.

| Rank | Goal | Test of success |
|---|---|---|
| **1 — King** | Play the trained sets *really well* | Beats strong baselines and human play on the trained pool |
| **1 — King (tied)** | Auto-extend to new cards built from known primitives | A card never seen before, whose text is composed of already-practised primitives, is played competently on day one with **zero code changes** |
| 2 | Fast inference, near real-time | Single-decision latency low enough to feel instant in the spectator tool |
| 3 | Extend to all sets | One shared-knowledge model (or MoE/conditioning) covering the full card pool |

Rank 1 has two entries and that is deliberate. The owner stated the atomic/modular ability
composition — so that new sets are playable immediately except for genuinely new keywords — is
"part of the highest priorities too". Treat compositional card understanding as load-bearing for the
King Goal, not as a nice-to-have that comes later. A design that gets strong play by memorising
specific cards has **failed rank 1**, because it cannot satisfy the second entry.

**Format priority: Commander.** If a design decision trades off between formats, Commander wins.
That implies: multiplayer-capable state, a command zone, 100-card singleton decks, very large
boards, very long games, and a card pool where effectively everything is legal.

## 2. The overrule clause

The owner has explicitly granted this authority, in their own words:

> *"If I ever get a quick n smart idea that doesn't move us in that direction, you are greenlit to
> overrule me, and keep focus. Local ideas I get on the fly or during sessions can NEVER be more
> important than this, and you should treat them accordingly."*

So: when a mid-session idea does not advance the ladder above, **say so plainly, decline to build it
now, and write it to [`docs/BACKLOG.md`](docs/BACKLOG.md) instead.** Do not silently comply, and do
not silently ignore. Name the conflict, name the rank it would displace, and offer the version of the
idea that *would* serve rank 1 if one exists.

This clause is not a licence to refuse work. It applies to scope drift, not to the owner's
considered decisions. If the owner hears the objection and repeats the instruction, that is their
call — build it.

## 3. The learnability principle

> **Prefer learned behaviour over authored behaviour. Shape with incentives, not with rules.**

Default to *no*:

- no hardcoded strategic heuristics ("always play a land first", "never chump-block")
- no hand-tuned caps, clamps, or thresholds on what the agent may do
- no hand-authored curricula or schedules where a learned/adaptive one is possible
- no reward terms that encode a specific play pattern rather than a genuine objective

Default to *yes*:

- railed, contained self-play where the environment makes bad play lose
- incentives and objectives; let the policy discover the tactic
- adaptive opposition (self-play league, learned opponent sampling) over fixed difficulty tiers
- learned representations over hand-engineered features

This is a **strong preference, not an absolute rule.** Hard constraints are still legitimate where
they are (a) genuine rules of Magic, (b) safety rails that prevent a rollout from never terminating,
or (c) a temporary scaffold with a written plan to remove it. When you do add one, say out loud that
you are adding it, why, and what would let it be removed later. Never add a cap silently.

Corollary: **the MTG rules are not heuristics.** Implementing rule 613 layers exactly is not a
"hardcoding" — it is the environment being correct. The line is between *how the game works*
(hardcode it, precisely) and *how to play well* (learn it, always).

## 4. What "done" looks like for a piece of work

Before calling anything finished, check it against the ladder:

1. Does this make the bot stronger on the trained pool, or unblock something that will?
2. Does it preserve the zero-code-change path for new cards made of known primitives?
3. Did it add a hardcoded strategic assumption? If yes, is that written down and justified?
4. Can the owner *see* the effect in the spectator tool, or measure it in a benchmark?

If the answer to 1 is no, it probably should not have been built yet.

---

## Standing open problems

These are unsolved and must be reasoned about before infrastructure is committed. Do not
quietly pick an answer — they are architectural forks with long shadows.

- **Infinities.** Infinite mana, tokens, power, draw, ETB triggers. Representation *and* the
  training question: if the engine auto-shortcuts a loop, the agent never learns the combo; if it
  does not, rollouts hang. See [`docs/DESIGN_INFINITIES.md`](docs/DESIGN_INFINITIES.md).
- **Loop detection and resolution.** Mandatory loops draw the game (CR 104.4b); optional loops are a
  player choice. Both need engine support and an agent-facing action.
- **Card-pool conditioning.** The bot must know which cards are *enabled*, because that changes what
  it plays around. MoE-per-set, format conditioning vector, or compositional text embeddings over
  the legal pool. See [`docs/DESIGN_CARD_POOL.md`](docs/DESIGN_CARD_POOL.md).
- **Full-game BPTT.** Desirable for combo and long-scaling decks. Feasibility is a memory question,
  not a wish. See [`docs/DESIGN_TRAINING.md`](docs/DESIGN_TRAINING.md).

---

## Hardware reality

Training happens on an **NVIDIA DGX Spark** (GB10 Grace-Blackwell, 128 GB unified LPDDR5X,
~273 GB/s, ARM64, CUDA 13, compute capability sm_121). The Windows machine this repo lives on is an
**Intel Arc XPU** box and is for development, tooling, and the spectator app only — it is not the
training target. Two consequences that bite:

- Unified memory means capacity is enormous but **bandwidth is modest** (~273 GB/s, roughly a
  mid-range consumer GPU). Being greedy with parameters is cheap; being greedy with *memory traffic
  per decision* is not.
- Small-batch RL rollouts on this machine are bound by Python and kernel-launch overhead, not FLOPs.
  Throughput work belongs in the environment and the batching layer, not in shrinking the model.

See [`docs/HARDWARE_DGX_SPARK.md`](docs/HARDWARE_DGX_SPARK.md).
