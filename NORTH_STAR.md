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
| **1 — King (tied)** | Play well **within a real match clock** | Wins the match without ever being the reason it goes to time. See §1a. |
| 2 | Extend to all sets | One shared-knowledge model covering the full card pool |

Rank 1 has three entries and that is deliberate.

**"Really well" includes niche decks, not just good decks.** The owner: *"I mainly care that it
makes our model better at normal AND niche decks."* A bot that plays the three strongest archetypes
at a high level and falls apart against a weird combo pile has not met rank 1. This is why full
rollouts and combo discovery are in scope at all, and why a self-play league that keeps unusual
decks alive is a rank-1 concern rather than a refinement.

The **compositional** entry is there because the owner stated the atomic/modular ability
composition — so that new sets are playable immediately except for genuinely new keywords — is
"part of the highest priorities too". Treat compositional card understanding as load-bearing for the
King Goal, not as a nice-to-have. A design that gets strong play by memorising specific cards has
**failed rank 1**, because it cannot satisfy that entry.

### 1a. The championship-final standard

The **clock** entry was promoted from rank 2 by the owner on 2026-09-10, in their words:

> *"The scenario we optimize for in theory is something alike the world championship final. We want
> best quality, but must make decisions in time or we will be greatly punished by skipping turns."*

That reframes latency. It is not "nice if it feels snappy". **A decision that arrives too late is
worth zero, no matter how good it is.** Quality and speed are not being traded against each other
on a smooth curve; there is a deadline, and beyond it the value falls off a cliff.

Two consequences that bind every design decision:

- **Optimise the tail, not the mean.** A median of 3 ms with a 99th percentile of 800 ms is far
  worse in a timed match than a flat 60 ms. Predictability is a feature.
- **The hard part is that difficulty varies.** The owner named it: *"some turns will require more
  reasoning passes than others, due to increased complexity of the board and state or number of
  possible actions to take."* A fixed compute budget per decision is both wasteful on easy turns
  and inadequate on hard ones. **The agent should learn to allocate its own clock**, which is the
  learnability principle applied to compute. See [`docs/DESIGN_LATENCY.md`](docs/DESIGN_LATENCY.md).

**Do not choose a model size before the latency harness has produced numbers.** The owner was
explicit: test first, then decide whether a bigger model is affordable under live conditions.

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

## 4a. The drafter, and why it is tunable

Stated by the owner on 2026-09-10 and recorded here because it is a product goal in its own right,
not a by-product of training.

**Three modes, one model:**

| mode | input | output |
|---|---|---|
| **draft from start** | a format, and optionally a commander or a direction | a complete legal deck |
| **draft completer** | a partial human deck of any size, 3 cards or 97 | the remaining cards |
| **counter-drafter** | a partial or empty deck, plus a named opponent deck | a deck built to beat that one |

**Two knobs, and they are not the same knob.** The owner: *"preferably it should be tunable so you
can set how niche/non-standard your deck is supposed to be, and how random it is (we dont want it
to just choose THE best deck it can make every time we make a standard deck or same situation for a
niche one)."*

Those are two independent axes and a design that offers one control for both is wrong:

- **Nicheness** is a *directed* deviation. A niche deck is coherent but unusual: a different local
  optimum, not a damaged version of the usual one.
- **Randomness** is *undirected* variety at a fixed level of nicheness. It is what stops the
  drafter returning an identical answer to an identical request.

**Turning up randomness on a standard-deck request gives you a worse standard deck, not a niche
one.** Any implementation that conflates them has failed this goal. See
[`docs/DESIGN_DRAFTER.md`](docs/DESIGN_DRAFTER.md).

Both knobs must be settable at inference and learnable during training. Neither may be a
hand-authored schedule.

**Relationship to the Teacher.** The owner: *"It is not strictly required for me that this teacher
is the drafter, I just think they have an overlap."* The overlap is real but narrower than one
shared agent. The Teacher *selects* among candidate matchups; the drafter *generates* a deck pick by
pick, which a selector cannot do. What they share is the **critic** that scores a deck, and the card
and deck encoders underneath it. That shared critic is what makes the drafter trainable without a
human reference corpus. See [`docs/DECISIONS.md`](docs/DECISIONS.md) D15.

## 5. Decisions already taken

These are settled. Do not re-litigate them; build on them. The reasoning is in
[`docs/DECISIONS.md`](docs/DECISIONS.md).

- **Rebuild the environment and the card representation.** Approved 2026-09-10. Making the
  interaction real *is* the rewrite.
- **The ability tree is the foundation.** Cards decompose into typed sub-components and the network
  learns embeddings over those. This is what makes learning transfer to new sets.
- **Three things survive the rebuild, by the owner's explicit instruction.** They are requirements,
  not preferences:
  1. **The action tokenizer.** Keep the structure where network output decomposes into actions, and
     build a real tokenizer for it.
  2. **Multi-step planning, with every step trained.** *"Train all the actions irregardless of how
     far down a plan it is before it is chosen."* This corrects the earlier audit, which proposed
     deleting the plan decoder because only its first step received gradient. The owner's answer is
     better: keep it and train all of it.
  3. **Transferable learning of abilities, traits, stats, and origins** through learned encodings.
- **Full-game BPTT is not assumed.** Test it against truncated BPTT and let the measurement decide.
- **Train against a hard-loss clock.** Ruled 2026-09-10. Running out of time is a loss, never a
  draw, so the incentive is monotone and the deployment target does not have to be chosen now. See
  [`docs/CLOCK_TARGETS.md`](docs/CLOCK_TARGETS.md).
- **The Teacher is a curator plus a critic, not a reinforcement-learning agent. The drafter is a
  generative policy.** They share the critic. See [`docs/DECISIONS.md`](docs/DECISIONS.md) D15.

## 6. When a problem is beyond you

The owner has asked that work requiring deeper reasoning than the current agent can reliably
provide be **marked as such rather than guessed at**. Do not manufacture these to look careful, and
do not use the label to avoid work you can do. Mark a task when you genuinely could not resolve it
and a wrong answer would be expensive to discover later.

Marked items live in [`docs/DECISIONS.md`](docs/DECISIONS.md) under "Needs deeper reasoning", each
with the specific question, what was tried, and why the answer matters.

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
