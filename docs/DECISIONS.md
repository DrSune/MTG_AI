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

## D8 — Train small first, then scale, and inherit representations rather than policy
**2026-09-10. Owner proposed; agent agrees with one significant qualification.**

The owner: *"we train a small model, fast, then we scale up, and can even use it to 'distill'
knowledge using it as a teacher, to kickstart the bigger models learning (unless we are afraid it
will teach it wrong things that makes it go permanently down the wrong track)."*

Train small first: **yes, unambiguously.** Throughput scales inversely with size, and until the
engine is correct and the evaluation is honest, games are worth more than capacity.

The worry about teaching the wrong things is **well founded, and it has a specific mechanism.**
Distillation produces low-entropy outputs, because the student is trained to reproduce a
distribution the teacher was already confident about. Low entropy means little exploration. Little
exploration means the teacher's errors are never visited, never punished, and never corrected. The
student ends up confidently wrong in exactly the places the teacher was wrong, and reinforcement
learning afterwards does not fix it because the policy no longer generates the experience that
would. That is the "permanently down the wrong track" failure, and it is real.

**The qualification: what you transfer decides whether the risk applies.**

| what is transferred | risk | why |
|---|---|---|
| **Representations** (board encoder, card and ability-tree encoding) | **low** | Close to a perception problem with a right answer. What a card does and what is on the table are not opinions. A weak player still sees the board correctly. |
| Value function | medium | Encodes the teacher's evaluation errors, but is continuously corrected by real outcomes during RL. |
| **Policy** (the action distribution) | **high** | This is exactly where the teacher's strategic errors and exploration blind spots live. Copying it is copying its ceiling. |

The two-tier architecture in [`COST_MODEL.md`](COST_MODEL.md) makes this boundary **architectural
rather than a matter of judgement**, which is a genuine piece of luck. Tier A is board
understanding and is safe to inherit. Tier C is where the strategy lives and should be
reinitialised. So the plan is:

1. Train the small model to a decent standard.
2. Scale up by **inheriting tier A weights** and reinitialising the decision head, rather than by
   distilling the policy.
3. Keep the small model **in the opponent league**, so the large model is rewarded for beating it
   rather than for imitating it. That signal actively punishes copying, which pure distillation
   cannot do.
4. If policy distillation is used at all, use it as a short initialisation with an **entropy floor
   afterwards**, never as a converged target.

**The gate that makes this checkable:** the student must exceed the teacher's Elo within a stated
number of generations. If it plateaus *at* the teacher's level, the transfer became a cap rather
than a kickstart, and the run should be restarted without it. Log the gap every evaluation.

## D9 — Decision count is monitored, not estimated
**2026-09-10. Owner redirected an in-flight analysis.**

The owner: *"decision count is easier to estimate once we actually have built the game engine, and
have some complex scenarios actually play out. I think we monitor it during some of our trainings,
and try to use those numbers for having some proof on it."*

Right, and it kills a piece of speculative work. An upfront combinatorial bound on the adversarial
worst case would have been an argument, not evidence, and the current engine cannot produce
evidence because its action space is degenerate (median 1 legal action). So:

- **Decisions per game per seat becomes a tier-1 monitored metric**, tracked every training run,
  reported at median, p99 and max, broken down by phase and action class.
- The adversarial question stays live as a **regression gate** rather than an analysis: if the
  measured p99 climbs past the clock budget, that is the alarm.
- The one structural finding that motivated it stands on its own and does not need the analysis:
  block declaration currently emits one action per attacker-blocker pair, so a combinatorial
  assignment becomes N sequential model calls. Collapsing that into one structured decision is
  already required by [`DESIGN_ACTION_SPACE.md`](DESIGN_ACTION_SPACE.md).

## D10 — Train against a hard-loss clock
**2026-09-10. RULED by the owner: "Hard loss clock is fine."**

Full reasoning in [`CLOCK_TARGETS.md`](CLOCK_TARGETS.md). A policy trained under a hard-loss
per-player chess clock is safe under every more forgiving environment; the reverse is not true,
because a policy trained where timing out yields a draw learns that stalling when behind is
correct, and that loses outright elsewhere. Adopting the harsh contract means the deployment-target
question does not have to be answered now.

## D11 — Two halting decisions, both learned, neither scheduled
**2026-09-10. Owner instruction.**

The owner: *"we should do like with LLM training, where we dont force it to reason. If it is sure
of its plan the first round it can just simply act the steps it had planned for that turn.
Thinking should be discovered with logic to reason about next turns, missed risks, alternative
plans, critique its own plan etc etc."*

That names **two separate halting decisions**, and they have different shapes. Both are learned;
neither is a fixed count.

| | Question | Granularity | Mechanism |
|---|---|---|---|
| **Within a decision** | think again, or commit? | one priority window | Interruptible. The halting head in [`DESIGN_LATENCY.md`](DESIGN_LATENCY.md) §3.3, trained as a sampled policy action. |
| **Across decisions** | is the plan I already made still good, or do I re-plan? | several priority windows | A contract. The agent commits to executing the next steps of an existing plan without a fresh trunk forward. |

The second one is new, and it is the more valuable of the two. It is simultaneously the owner's
cognitive framing ("if it is sure of its plan, just act the steps") and the compute amortiser in
[`DESIGN_LATENCY.md`](DESIGN_LATENCY.md) §2.4. Executing K planned steps from one expensive forward
pass divides the trunk cost by K. **The thing that makes the agent feel decisive is the same thing
that makes it fast**, which is a rare alignment and should be exploited rather than treated as two
features.

Three constraints on the commitment mechanism:

- **It must be verified, not trusted.** A plan made before the opponent responds can be invalidated
  by anything that changes the board. Cheap check first: if the legal-action set or the board hash
  changed materially, the plan is void and the trunk re-runs. That check costs almost nothing
  against a trunk forward.
- **Committing must be a learned action with a real cost, not a heuristic.** The agent chooses to
  commit; it is not committed for it. If the plan turns out wrong, the loss it causes is the
  penalty, exactly as with the clock bank. No authored penalty term.
- **Never let commitment hide a mistake.** Log plan-abandonment rate and executed-plan length.
  A rising commitment rate with a falling win rate is a policy trading correctness for speed, and
  that pair belongs in the review protocol's precedence table.

**What a reasoning pass should do** is the owner's other point, and the answer is not to schedule
it. Do not hardcode "pass one is critique, pass two is alternatives". Give the pass what it needs
to play any of those roles, which is attention over its own current plan, the board, and its own
uncertainty, and let the role be learned. A pass that can see its own draft plan can learn to
critique it; a pass that cannot see it can only re-derive it.

## D12 — Build the small, fast configuration first
**2026-09-10. Owner instruction, consistent with D5 and D8.**

The owner: *"Moving the bulk of the information to board encoder and making planner focus on just
acting and reasoning sounds good. We do this first to have fast iteration speed and we see how good
it becomes."*

Confirms the budget rule in [`COST_MODEL.md`](COST_MODEL.md): depth goes in the board encoder where
it is read once and cached; the plan and reasoning loops stay narrow because everything inside them
is charged once per iteration. Start at the v0.5 shape, roughly 150M parameters, and scale only when
the win-rate curve against the league flattens.

## D13 — Time pressure is a feature, and its absence is the ablation
**2026-09-10. Owner idea, adopted.**

The owner: *"I wonder if we could have a better model if it isnt forced to think quickly, but I
guess we could simulate that by letting it know it has max time at every decision it must take, or
by having some token representing it isnt under time pressure EVER in that game."*

Adopt the second form. The clock enters the observation as a feature, and **a distinguished
no-time-pressure value is part of its range**. That gives three things for one mechanism:

1. Training under a real clock, which is the deployment condition.
2. An **unlimited-time evaluation mode**, by setting the feature to its no-pressure value. The gap
   between clocked and unclocked play is then a directly measured number: *the price of the clock*.
   Nothing in the repo can currently measure that.
3. A guard against the clock becoming a crutch. If unclocked play is not better than clocked play,
   the agent is not actually using extra thinking time and the whole adaptive-compute programme is
   not paying for itself.

Track it as a tier-2 metric. The owner's first suggestion, exposing a per-decision maximum, is the
weaker version: it is a rail rather than a feature, and it cannot express "no pressure at all".

## D14 — Niche-deck strength is part of rank 1, not a refinement
**2026-09-10. Owner instruction.**

The owner: *"I mainly care that it makes our model better at normal AND niche decks, and maybe even
can draft/create new niche decks."*

So a bot that plays the three strongest archetypes at a high level and collapses against a weird
combo pile **has not met the King Goal**. Three consequences that are now rank-1 concerns rather
than nice-to-haves:

- The self-play league must actively keep unusual decks alive. A league that converges on the
  current best archetype trains a bot that has never seen the decks it will lose to.
- Combo discovery in [`DESIGN_INFINITIES.md`](DESIGN_INFINITIES.md) is load-bearing, because combo
  decks are the sharpest case of "niche but strong".
- The deck-space evolution ideas parked in [`BACKLOG.md`](BACKLOG.md), the elite pool and novelty
  reward and the annealed robustness weight, move from "recorded but never built" to on the path.

## D15 — The Teacher is a curator; the drafter is a generative policy; they share the critic
**2026-09-10. Owner delegated this: "About curator plus critic vs RL its your call. Do it according
to project goals and what I want."**

**The call: both, and they are different components.** The owner's instinct that the two overlap is
right, but the overlap is the critic, not the whole agent.

| | job | shape | why |
|---|---|---|---|
| **Teacher** | choose which matchup the Student trains on next | **curator + critic**, selecting among proposals | It is a selection problem, and selection measured better than a trained generator at it: curator 0.893 of oracle against REINFORCE 0.849 and a linear bandit 0.751, which is worse than uniform random at 0.815 |
| **Drafter** | produce a deck, pick by pick, on demand | **generative policy** | It has to be. A curator picks among things that already exist; build-from-empty, complete-a-partial-deck and counter-draft all require *generating* a deck that does not exist yet |

**What they share:** the critic that scores a deck, and the card and deck encoders under it. That
shared critic is the load-bearing piece, because it is what lets the drafter be trained without a
human reference corpus of good decks. Nothing else in the project can supply that signal.

Why this serves the stated goals better than either pure option. A pure RL teacher was measured
worse than curation at the teaching job and needs volume the machine does not have. A pure curator
cannot deliver [`NORTH_STAR.md`](../NORTH_STAR.md) §4a's three drafting modes at all. Splitting them
gets the measured-best teacher and the product the owner asked for, at the cost of one extra
component, and that component reuses the encoders rather than adding a per-decision cost.

## D16 — Nicheness and randomness are two knobs, never one
**2026-09-10. Owner requirement, with the design constraint made explicit.**

The owner asked for a drafter tunable on how non-standard a deck is and how random it is. These are
independent axes and the most likely way to get this wrong is to ship one control for both.

- **Nicheness** is a *directed* deviation toward a different local optimum. A niche deck is
  coherent and unusual.
- **Randomness** is *undirected* variety at a fixed nicheness. It is what stops an identical
  request returning an identical deck.

**Raising randomness on a standard-deck request produces a worse standard deck, not a niche one.**
Sampling noise moves you away from the mode in every direction at once, which is damage, not
character.

Two further constraints, both of which a naive implementation fails:

1. **Randomness must not compound over the ~100 sequential picks of a Commander deck.** Small noise
   at every pick gives an aggregate that is random and incoherent, which is the opposite of niche.
   The fix mirrors D11's plan commitment: sample a deck-intent once, then draft near-greedily
   conditional on it. Commit to a direction, then execute it well.
2. **Nicheness must be measured, not authored, and must not be satisfiable by garbage.** A deck of
   100 random bad cards is maximally unusual. Whatever statistic defines nicheness has to be paired
   with the critic's quality score, per [`METRICS.md`](METRICS.md) §17.

Design in [`DESIGN_DRAFTER.md`](DESIGN_DRAFTER.md).

## D17 — Retrieval is the pointer head, not an alternative to it
**2026-09-10. Owner idea, and it turns out to be their own earlier one.**

The owner: *"it has a prediction of the card it wants to add to a deck, and then searches it up in
the vector database with the encoded values from the ability tree, and it can choose the card that
comes the closest to what card it thinks is ideal."*

This is the same idea as the deleted `RL_ARCHITECTURE.md` §5.1, recovered at
[`recovered/`](recovered/RL_ARCHITECTURE_pre_db5e024.md): *"the model generates a Query Vector...
It performs a Vector Search against the card embedding pool."* Written months earlier and lost to a
doc rewrite.

**The unification.** The drafter's pointer head already computes `score(c|s) = q(s) . k(c)`, where
`q(s)` is the predicted ideal card and `k(c)` is the encoded ability tree. The argmax of an inner
product over a set **is** nearest-neighbour search under that inner product. So retrieval is the
*implementation* of the pointer head at scale, not a competing design. Same operator, used three
times: the drafter, the in-game pool conditioning, and this.

Four consequences that are not obvious from that equivalence:

- **Similarity metric is a real decision.** Raw inner product rewards high-norm vectors, which in a
  learned card space means generically strong cards, so "closest" would silently mean "best". That
  makes the nicheness knob a strength slider by construction. Use cosine for *kind* plus a separate
  learned impact scalar for *strength*.
- **A single query averages modes.** When the right pick is either a removal spell or a threat, the
  mean of the two embeddings is neither and can retrieve something incoherent. Fixed with four
  query heads, which cost nothing extra on the scan because the keys are read once regardless.
- **Set filtering falls out for free**, as a mask over scores. It is a third flag beside
  `format_legal` and `engine_supported`. Masking scores rather than the index keeps legality exact,
  which approximate search would not.
- **Do not build an approximate index.** An exact scan of 25,000 cards costs about 47 microseconds,
  and the drafter is off the per-decision path entirely. Approximate search would trade exact
  legality for speed we do not need.

## D18 — Card invention: keep the free half, park the rest
**2026-09-10. Owner idea, partially adopted.**

The owner: *"or even eventually extend it to 'invent' new cards in the gaps"*.

**The free half is worth building now.** The distance between the query and its nearest real card is
an unmet-need signal, available the day retrieval works and costing nothing. Aggregated over many
drafts it maps what the pool lacks. One slice of it is immediately useful: needs that fall on cards
we have marked `engine_supported = false` give a **demand-ranked worklist for the ability-tree
compiler**, so the next primitive implemented is the one the drafter most wants and cannot have.
Publish it normalised, since a null drafter's queries also have nearest neighbours.

**The generative half is parked**, with the reason. Decoding an embedding back into an ability tree
has one genuinely strong property: a tree decoded from the grammar is **executable by
construction**, so an invented card is playable rather than merely describable. Against that:
balance is a far harder problem than legality; the critic that says a card would be good here is
trained on real cards and is badly miscalibrated off distribution, so its argmax over invented
cards is not trustworthy; and it does not serve the King Goal. Park it.

**One thing must not be deferred:** the per-pick logging that would let this be studied later has to
land when the drafter is first built. It is unrecoverable afterwards.

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

### R8 - "Niche" may only ever mean "unlike what we ourselves built"

Raised by [`DESIGN_DRAFTER.md`](DESIGN_DRAFTER.md) §10 Q2, and mirrored here at that document's own
request.

Nicheness is measured as low likelihood under a reference distribution of decks. Early on, that
reference is dominated by our own archive, which the curator has been actively shaping toward
teaching value. So "niche" collapses into "unusual relative to what our own teacher happened to
build", which is circular, and it drifts as the drafter itself changes the archive.

The dangerous part is that **it will look like it is working.** Every instrument in the drafter's
metric set except the human panel is measured against the same reference, so a self-referential
nicheness axis produces a high knob-response diagonal, a near-zero conflation alarm, and green
gates, while returning decks no player would call unusual.

Tried: card-level popularity ranks, which are external but too coarse, and roughly 150 published
preconstructed deck lists, which are deck-level and external but thin for a 32-dimensional density
estimate. Both help. Neither settles it.

Why it matters: the failure is invisible to the entire instrument panel. The only thing that
catches it is a blinded human weirdness panel, which is why that check is not optional. Either
acquire a larger deck-level human corpus, or state the circularity out loud rather than shipping
the self-referential version quietly.

---

## Deferred pending information

**The deployment target's clock is unknown**, and it changes the arithmetic. **Superseded in
practice by D10**, which makes the choice unnecessary for now. Kept here because it returns if
paper Commander becomes the deployment target. Everything in
[`DESIGN_LATENCY.md`](DESIGN_LATENCY.md) §1 assumes paper tournament rules. A bot on Arena faces a
per-priority rope plus a match reserve. A bot on Magic Online faces a per-player chess clock with
**no five-additional-turns mercy**, which is materially harsher and removes the draw-versus-loss
structure the incentive design rests on. If the target is a digital client, the budget and the
return structure must both be re-derived. Not guessed at.
