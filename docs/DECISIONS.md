# Decisions

Settled calls, with the reasoning and the date. Do not re-litigate an entry here without new
evidence. If you overturn one, edit it in place and say what changed.

Also holds the register of questions marked as **needing deeper reasoning** than the agent that
hit them could reliably provide.

---

## D1 — Rebuild the environment and the card representation
**2026-09-10. Owner approved.**

The audit found the engine simulates something that is not Magic in the ways that decide games:
targeted spells are silent no-ops, only one player ever holds priority, no evasion, layers 1
through 6 absent, all enters-the-battlefield triggers dead, two players maximum in a
Commander-first project. There is no incremental path from that to strength, because making the
interaction real *is* the rewrite. Priority changes the turn loop, targeting changes the action
space, layers change the state model, and multiplayer changes every consumer.

Cheap wins do exist and two have already been taken, but a faster wrong simulation is still wrong.

## D2 — The ability tree is the foundation
**2026-09-10. Owner approved.**

Cards compile to a typed tree over a closed primitive vocabulary. The engine executes that tree
and the network reads that same tree. One representation, two consumers.

The owner's reason, and it is the right one: *"It is the important foundation for the
transferrability of what the model has learned, to new sets."*

Adding a **node type** is a code change. Adding a **card** is not. Design in
[`DESIGN_CARD_POOL.md`](DESIGN_CARD_POOL.md).

## D3 — Three things survive the rebuild
**2026-09-10. Owner instruction, binding.**

1. **The action tokenizer.** Keep the structure where network output decomposes into actions, and
   build a real tokenizer for it.
2. **Multi-step planning with every step trained.** In the owner's words, *"train all the actions
   irregardless of how far down a plan it is before it is chosen (planning is important to keep)"*.
3. **Transferable learning of abilities, traits, stats, and origins** through learned encodings.

**This overturns an earlier audit recommendation.** The audit proposed deleting the
`ActionSequenceDecoder` on the grounds that 50.4M of its parameters receive zero gradient, since
only plan step 0 reaches the loss. The owner's answer is better and is adopted: the head is not
worthless, it is *untrained*. Keep it and train every step. Design in
[`DESIGN_ACTION_SPACE.md`](DESIGN_ACTION_SPACE.md).

## D4 — Latency is part of the King Goal, and the standard is a championship final
**2026-09-10. Owner instruction.**

Promoted from rank 2 to a tied rank 1. A decision that arrives too late is worth zero regardless
of its quality. Optimise the tail, not the mean. See [`NORTH_STAR.md`](../NORTH_STAR.md) §1a and
[`DESIGN_LATENCY.md`](DESIGN_LATENCY.md).

## D5 — Measure before sizing
**2026-09-10. Owner instruction.**

*"I think the model can be bigger, but you dont need to do it already, we should make some tests
of latency first. And then decide on whether we go for a bigger model, based on whether it works
well for playing under real/live circumstances."*

So: no model-size commitment until [`tools/latency/bench.py`](../tools/latency/bench.py) has run
on the DGX Spark. First-pass numbers from the dev box are in `reports/`.

## D6 — Full-game BPTT is a hypothesis, not a requirement
**2026-09-10.**

The owner: *"I want BPTT just because it is cool, but of course we need to test both."* Honest and
correct. Step-level gradient checkpointing makes full-game BPTT cost about 141 KB per decision, so
memory does not decide it. Serial wall-clock does, at roughly 10× truncated. Implement checkpointing
unconditionally, default to K=256 with carried state, and run full-game as a periodic ablation.

## D7 — Not mixture-of-experts per set
**2026-09-09. Agent overruled the owner's suggestion; owner did not object.**

Scored worst of five options. Sets are a printing concept, not a mechanical one. A Commander deck
spans about 30 sets and a pod about 200, so the gate fires nearly every expert on every decision:
full dense bandwidth, zero specialisation, on a machine whose binding constraint is bandwidth per
decision. A new set's expert starts at random initialisation, which fails the tied-rank-1 goal
outright. Parked in [`BACKLOG.md`](BACKLOG.md).

If experts are ever wanted, the correct axis is mechanical function, and that falls out of the
ability tree via attention without needing to be declared.

---

## Measurements that decisions rest on

Everything here was measured, not estimated. Re-measure rather than trusting these once the engine
is rebuilt.

| What | Value | Where |
|---|---|---|
| Engine step, Commander, after the 2026-09-09 fixes | 7.7 ms, from 41 ms | `tools/latency/positions.py` |
| Legal actions per decision, current engine | median **1**, p99 **5**, max **6** | measured over 2,400 decisions |
| Spell casts in 2,400 decisions | **25** | same run |
| Visible entities per position | median 37, max 60 | same run |
| Total graph entities | constant **214** | libraries never leave the graph |
| Weight-byte cost model versus measured latency | predicted 1.16×, measured 1.21× at 1-in-6 board cadence; predicted 1.97×, measured 2.27× at every-decision | `tools/latency/bench.py` |
| Effective achieved bandwidth, Intel Arc 140V, batch 1 | 20 to 48 GB/s | same |

The action-count figure is the important one and it is damning. **A median of one legal action is
not Magic.** It is the direct symptom of broken targeting and absent priority. Any latency or
strength number taken on the current engine is measuring a degenerate game, which is why the
benchmark sweeps a projected action-count range instead of the measured one.

---

## Needs deeper reasoning

The owner asked that work beyond the current agent's reliable reasoning be marked rather than
guessed at, so a stronger model can take it. Entries must name the specific question, what was
tried, and why a wrong answer is expensive. **Do not add entries to look careful.** An empty
section is a fine outcome.

### R1 — Layer-system dependency ordering (CR 613.8)

The rules require that when two continuous effects are in the same layer and one changes what the
other applies to, the dependent one applies later, and that dependency is re-evaluated as the
sequence is applied. This is mutually recursive with timestamp ordering and can cycle, in which
case timestamps break the tie.

Tried: sketched a topological sort over effects keyed by `(layer, sublayer, timestamp)` with a
dependency pass. It is not obviously correct in the presence of effects that gain and lose
applicability during the same application sequence.

Why it matters: it is load-bearing for correct power/toughness and type-changing, it is invisible
when wrong (the game just resolves differently), and getting it wrong after the training corpus is
built means every learned value estimate is calibrated against a subtly different game.

### R2 — Loop classification in a multiplayer pod

CR 104.4b makes a mandatory loop a draw. In a four-player pod, a loop may involve two players while
the other two are not participating. Whether the game is a draw for everyone, a draw for the
looping players only, or something else, and how that interacts with a player who could break the
loop but is not in it, is not resolved in
[`DESIGN_INFINITIES.md`](DESIGN_INFINITIES.md) beyond "v1: draw the whole game, log it".

Tried: read the rule and the design; the conservative fallback is implemented in the design but is
known to be wrong in some cases.

Why it matters: Commander is the priority format, so the multiplayer case is the main case, not an
edge case. Drawing a whole pod when one player had a winning line is a large strategic distortion
that self-play will learn to exploit.

### R3 — Credit assignment through a recurrent state under PPO with a shared engine

The plan is PPO plus a recurrent carrier plus BPTT plus an experience buffer. The interaction of
importance-sampling ratios with a hidden state that was produced by an older policy is genuinely
subtle, and the existing code gets it wrong in at least three ways (stale buffer, shared
undetached state, collection-time logit bias not reproduced at training time).

Tried: identified the three concrete bugs. What is not resolved is the principled formulation:
whether to recompute the hidden state under the current policy during the update, store it and
accept the staleness, or move to a formulation that does not have the problem.

Why it matters: it is silent. The training will run and produce curves either way.

### R4 — Importance-ratio granularity for a variable-length structured action

Raised by [`DESIGN_ACTION_SPACE.md`](DESIGN_ACTION_SPACE.md) §10.1. A move is emitted as a sequence
of up to 16 typed fields. Should PPO's ratio be taken once at the move level, or per field?

Move level is type-correct, but the ratio is a product over fields, so its log-variance grows with
field count and the trust region is systematically tighter on complex moves. A fourteen-field modal
X spell leaves the clip band while a two-field land drop does not, which starves exactly the actions
that matter. Field level bounds each field but is no longer the PPO estimator for the move, and the
sign and magnitude of that bias were not characterised.

Why it matters: the failure is misdiagnosable. The symptom is "the bot stopped casting spells and
just plays lands and passes", and this repository has already met that symptom once and answered it
with a 10-nat proactivity bias applied at collection and not at training. The wrong reflex is
available and will be tempting again.

### R5 — Whether halting credit assignment resolves under PPO at all

Raised by [`DESIGN_LATENCY.md`](DESIGN_LATENCY.md) §9.1. The learned time allocator treats "think
again" as a sampled policy action whose cost is paid through a clock bank in the environment, so no
shaping term is needed. That argument depends on the value function becoming accurate in the bank
dimension. Early in training the gradient of value with respect to bank is near zero, so the
continue-thinking advantage is noise for an unknown number of generations. A forfeit-probability
head is meant to bootstrap it.

That is a bet, not a proof. How long it takes to pay off, or whether it pays off, is unresolved.

### R6 — Whether the clock can live in the value function without being reward-hacked

Raised by [`DESIGN_LATENCY.md`](DESIGN_LATENCY.md) §9.4. Under tournament rules an unfinished game
is a draw, worth half a win. If the value function learns that a low clock means low value, the
policy may prefer lines that *end* the game over lines that *win* it, because ending it stops the
bleeding and the draw pays. Detection is straightforward: ablate the clock input at evaluation and
compare win rate at matched bank levels, and if win rate rises with it ablated the input is being
exploited. Whether the hack is avoidable in principle rather than merely detectable is unresolved.

### R7 — Flat versus scaled environment cost in the clock

Raised by [`DESIGN_LATENCY.md`](DESIGN_LATENCY.md) §9.3. Tokenisation genuinely costs more on big
boards. Charging that cost honestly teaches the agent that big boards are expensive, in the format
whose entire identity is big boards. Charging it flat hides a real cost and will make the agent too
slow on exactly the positions Commander produces. The two errors point in opposite directions and
choosing between them needs a training run long enough for the clock to bind, which does not happen
at current model sizes. Circular.

---

## Deferred pending information

**The deployment target's clock is unknown**, and it changes the arithmetic. Everything in
[`DESIGN_LATENCY.md`](DESIGN_LATENCY.md) §1 assumes paper tournament rules. A bot on Arena faces a
per-priority rope plus a match reserve. A bot on Magic Online faces a per-player chess clock with
**no five-additional-turns mercy**, which is materially harsher and removes the draw-versus-loss
structure the incentive design rests on. If the target is a digital client, the budget and the
return structure must both be re-derived. Not guessed at.
