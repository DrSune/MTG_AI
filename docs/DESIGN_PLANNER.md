# Design: the per-object planner, and search over plans

Status: **v1 built (2026-11-18, §7), behind `--planner` (off by default); its A/B not run.**
Steps 2-4 of §5 are design.
- The owner settled the form in four rounds (OWNER_VISION_LEARNING §12, PLAN_PLANNING §5).
- The owner asked for its logic to be checked against the project's goals before any building.
  §3 is that check. It found three problems in the first proposal, each fixed below.
- This takes the place of PLAN_PLANNING §5's plan slots. DESIGN_ACTION_SPACE's decoder stays
  parked.

## 1. What it is

**Which objects carry an intention.** Every visible object its player can make a choice with
(the owner: "Everything that can be made a choice with, that is also visible, should be planned
with"):
- the hand;
- the player's permanents, tokens included ("Token creatures spawned can attack, so they can
  technically be planned with");
- the player's cards in other zones that a permission lets them use (a graveyard, exile, a known
  library top).

Not planned:
- Unknown future draws. A known next draw (scried, looked at) is visible and could be planned, but
  that is later ("complex mechanics to code together").
- The opponent's objects. They are targets, not plans.

**What an intention says (readable, all observable after the fact; settled for v1, 2026-11-18):**
- *when*: the turn-counted bucket of the object's next use, from this decision on:
  - A1, A2, A3, A4+: this sequence's uses, in order;
  - later this turn;
  - the opponent's next turn;
  - my next turn;
  - the two turns after;
  - later;
  - never (the game ends first).

  A sequence is the seat's run of decisions in one step of one turn with no action of the
  opponent in between. A held Cancel reads "the opponent's next turn". A sweeper kept back reads
  "my next turn" or later.
- *verb* of the next use: cast, play a land, activate, attack, block, a cost (sacrifice, discard,
  exile), or none.
- *window* of the next use: sorcery speed in my main phase, my combat, in response to their spell,
  in response to their ability, their combat, or another instant-speed point. It is read off the
  decision's own context (the ask, the step, the stack's top), so "Cancel, their next turn, in
  response to their spell" is the plan the owner's example describes.
- *target* of the next use: a pointer to an entity, as the policy's options point; none when its
  target is not an entity at forecast time.

**What counts as a use.** A use is mechanical: the object is the subject of one of its player's
own decisions, with the verb read off the ask and its option:
- a cast, land or activation row;
- an attack ask answered with an attack;
- a block ask answered with an attacker;
- a cost choice that picks it.

A target ask's answer is the target of the use before it.

**How it is carried:**
- Heads on each object's token write its intention at every decision, for the uses from that
  decision on (its own action included).
- The next decision reads it back as columns of that token. The actor stores them in the
  observation, so samples stay independent and there is no BPTT.
- An object that changes zones is a new object (CR 400.7) and starts blank.
- A hidden vector per object (the owner's "both") comes after v1, measured (§3.4).

**One round style per player.** A label of the round as a whole, on the global token (§3.2).

## 2. What trains it

| Signal | What it gives | What it cannot do |
|---|---|---|
| **Hindsight**: each label is what actually happened to its object; the style is the round's measured statistics | Memory of intent across decisions and turns; a dense task (forecasting one's own future use) that shapes the trunk toward multi-step structure | Improve play by itself: it predicts the policy, not the best play |
| **Plan-following** (§3.1) | The policy acts on its plan: a plan given as input is executed | Choose good plans |
| **Outcome PPO** (unchanged: ±1, γ = λ = 1) | What improves play | Credit a line it never tries |
| **The style critic** V(state, style), from results under each style | Choosing the style with the best value is a policy-improvement step at the round's level | Value a style never played |
| **The search's best plan** (P3, §4) | The "should" target: labels from the line the search found best, so planning is learned from lookahead | Exceed the search's own horizon and worlds |

## 3. The logic check (the owner asked; three problems found)

**3.1. A plan read as input is not a plan followed.**
- **The problem.** PPO trains the policy on its actions given its inputs. Nothing in it makes the
  policy act on its plan input, so a sampled or searched plan could be ignored.
- **The fix: hindsight relabelling,** as goal-conditioned RL does (Andrychowicz et al. 2017,
  "Hindsight Experience Replay"). In a supervised side loss, the plan input is replaced by the
  plan the round actually followed (its realized labels), and the policy is trained to take the
  action it took. The policy then learns "given this plan, act like rounds that carried it out".
- **Why a side loss.** PPO keeps the inputs as they were played, because a relabelled input
  would make PPO's importance ratio wrong.
- **What follows.** Without plan-following, the search's plans (§4) could not be played out
  faithfully, and its continuation would not follow through: the failure the puzzles found
  (KNOWLEDGE/2026-11-18/214).
- **What v1's plan-following is: commitment without exploration** (KNOWLEDGE/2026-11-18/216 P2).
  - In v1 no plan is sampled: forecasts are never sampled, and styles arrive in v2 (3.3).
  - At play time the read-back is the argmax forecast. Hindsight trains that forecast to predict
    the policy's own most frequent use. Plan-following then trains the policy to execute the
    read-back.
  - So the loop is: the forecast predicts the habit; the policy learns to follow the forecast; the
    forecast is the habit. It sharpens habits by construction, and the puzzles found one habit per
    decision kind (214 §5).
  - The owner's "exploration by commitment" has two halves. v1 builds the commitment half only;
    the exploration half arrives with v2's sampled styles or v3's search.
  - So v1's arms are read for what plan-following **costs** (entropy, the harm screens), not for
    whether it helps (§5).

**3.2. A free "mode" collapses.**
- **The problem.** A learned mode token with no meaning of its own is a known failure of latent
  options. If the policy ignores it, the mode changes nothing, its advantage is zero, and nothing
  ever gives it meaning.
- **The fix: the round style is a hindsight label of observable statistics of the round,** in a
  few classes:
  - the share of creatures that attacked;
  - cards used against cards held;
  - damage dealt against damage taken;
  - mana left open on the opponent's turn.
- **How it is used.**
  - At a round's first decision the style is sampled from its forecast with probability ε,
    otherwise taken greedily.
  - Plan-following (3.1) makes the policy play the style it is given, so a sampled style is real
    strategic exploration: "go all in this round" is actually tried.
  - The style critic learns what each style is worth there. Choosing by it is the owner's
    survive-or-all-in decision, learned from results.
- **Flagged.** These statistics are a hand-chosen summary, an observation design and not a
  policy rule. They can be replaced by a learned clustering of rounds if they bind.

**3.3. Per-object labels are forecasts, never sampled.** Sampling each object's label on its own
can produce two A1s. So the labels are the network's best forecast, and exploration happens at
the style (3.2) and in the search (§4).

**3.4. The hidden vector is staged.**
- **The risk.** A vector the network writes and reads back can drift with the weights and amplify
  its own noise.
- **The response.** v1 carries labels only. The vector is then added (normalised, with dropout
  in training) and kept only if the puzzles or the value's error show it pays.

**3.5. Against the project's goals.**
- **The King goal.** Improvement comes from PPO, the style critic and the search. The planner adds
  memory, commitment and plan-level exploration, aimed at exactly the multi-step skills 214 found
  missing.
- **Learnable over hardcoded.** Every label is an observable fact of the game (its asks and its
  journal), learned from play. The policy is never constrained, and no plan or strategy is written
  by hand. The label vocabularies are small discretizations, said aloud in §6.
- **Generalisation through components.** Intentions sit on objects, read through their
  components. Nothing is card-specific. These are plan-level components, as the owner put it.
- **The match clock.** The forecasts cost one pass. The search over plans is optional at play
  time.
- **Commander.**
  - The cost grows with the number of objects, one head per token.
  - Targets include players, and a style is per player.
- **Honesty.** Only visible objects are planned (OWNER_PREFERENCES #1).
- **The ceiling.** Plans are inputs and targets, never a mask, so no move is taken away.

## 4. Search over plans, multi-turn (the owner: "improving search to work multi-turn along with the planner ... will make both better")

**Today** (`tools/selfplay/search.py`):
- candidates are single moves at an act or priority decision;
- the network plays the continuation on both seats;
- the horizon is about one turn.

The puzzles found the search adds only tactics that pay within one turn, because the continuation
does not follow through on a plan (214 §4).

**With the planner:**
- **Candidates are plans**: the forecast's top plans and a few sampled styles.
- **Each candidate is played out with the continuation conditioned on its plan.** Plan-following
  (3.1) makes it follow through, so the horizon can grow to one or two rounds (BACKLOG, the
  horizon question).
- **The leaves** are valued by the style critic, and the worlds are drawn by the opponent
  simulator.
- **Selection** is by Gumbel sequential halving over plans (already built for moves).
- **Branching** is that of a few plans, not that of every move.

**Each makes the other better:**
- the search's best plan is the target of the forecast heads, which amortises the search;
- the planner makes the search's playouts coherent and its branching small.

**When.** At a round's first decision only, with small n, as part of P3 under PLAN_CEILING's gates
A and B.

## 5. Build steps (each read on every puzzle category, KNOWLEDGE/2026-11-18/214)
1. **v1** covers the old v1 and v2: the turn-counted *when* holds the horizon and the holds.
   - It has: when, verb, window and target labels on every plannable object; hindsight heads;
     the label columns read back; plan-following.
   - It is a registered A/B against the control on every category and on L.
   - **The hypothesis** (216 P3: a hypothesis, not a prediction): holds and coherence might move
     B (counters), D (overextension) and A (sequencing).
     - The red team found no mechanism for it at a puzzle root. The holds the puzzles test are
       decided by visible facts (open Islands, the land count) that the policy already sees, and
       v1 adds no input about them and no better value.
     - The C failures (attacking into a lethal crack-back, not chumping) are a missing trunk
       feature, "incoming damage ≥ my life", which both heads lack (PLAN_NETWORK_READINESS §1.2).
       v1 reaches them only through the forecasting task, so no prediction favours them.
   - **The registered A/B** (216 P1-P4, N3). Its arms run inside PLAN_LONG_RUN's multi-arm A/B,
     from its one init:
     - **C**, the control;
     - **P**, `--planner` (hindsight and plan-following at their defaults);
     - **P0**, `--planner --follow-coef 0` (hindsight only).

     Reading P and P0 apart separates the forecasting task from the following term.
   - **Prerequisites** (§7, "Before the A/B"):
     - the puzzle runner carries a tracker;
     - the iter row reports each head's per-class recall.
   - **The reads.** The multi-arm A/B's shared reads:
     - R1 (harm) and R2 (L);
     - entropy per kind of decision;
     - the whole suite's twin-consistent pair count and the mean probability on the right options,
       bootstrapped over puzzles;
     - throughput.

     Plus each head's macro-averaged recall. A category falling is reported, never a falsifier
     (216 N3).
   - **Kill an arm** (216 P2) when either holds:
     - the per-kind `ent` of `priority` or `act` falls below the control's by more than 0.03 over 10
       updates (189 §8: 0.003 a update is already a near-deterministic day);
     - `kinds.priority.pass` rises above 0.99 (0.974 today; 198 §3's collapse).
   - **The falsifier, per arm** (216 P3). If the arm does not beat C on the suite's
     twin-consistent pair count by at least 2 pairs of 8, at both the 90% and the 100% snapshots,
     and L is within noise:
     - v1's side losses in that form are dropped from the long run;
     - v2 is not built on v1's evidence.

     Once PLAN_PLANNING P2's generator gives variants, the same rule is read on their pair counts.
     If P0 passes and P does not, the hindsight-only form is the one carried.
   - **What a null result ends:** v1's side losses in the long run, nothing more. The per-object
     plan as the interface of v3's search (§4) is its own registration.
2. **v2:** round styles, the style critic, styles sampled at ε; the combo and sweeper puzzles.
3. **v3:** search over plans, multi-turn (P3).
4. **Then:** the hidden vector, measured (3.4).

## 6. Choices said aloud (the learnable-over-hardcoded rule)
- **The when buckets.** A4+ as the last ordered index, and "the two turns after" as the last
  bounded bucket; also the window kinds. Removable: a learned distribution over the number of
  turns to use.
- **The style statistics** (3.2). Removable: a learned clustering of rounds.
- **The side losses' weights** (hindsight, plan-following). Read on an A/B; a weight that is too
  high pulls the trunk from winning.
- **v1's flags at their defaults:**
  - `--plan-coef 0.05`;
  - `--follow-coef 0.1`;
  - `--follow-share 0.25`, the share of rows the following loss sees, weighted 1/share.

  They are docs/BACKLOG.md scaffolds since the A/B's registration (216 C8). Removable: the arms'
  reads, then a schedule learned from the entropy and harm reads.

## 7. Built: v1 (2026-11-18)

Behind the learner's `--planner` (default off; the flags in `tools/selfplay/README.md`). Off,
nothing of it runs (checked below).

**The pieces** (file:line at the commit that built them):
- *The read-back*, four card columns appended: `features.py:191` (`C_PLAN_WHEN`, `_VERB`,
  `_WINDOW` as the vocabulary's index + 1, `C_PLAN_TARGET` an entity pointer + 1; 0 none). `encode`
  leaves them 0; `encode_entities` (`:614`) also returns the entities' handles in encode order.
- *`tools/selfplay/planner.py`* (numpy only: the workers run it):
  - the vocabularies `:68-81`; the window of a decision `:92`; the uses an answer makes `:107`;
    the plannable objects `:130`;
  - one object `:224` (a handle and the journal clock of its latest zone change, read
    incrementally `:213`; the mulligan's unjournalled moves renewed `:228`);
  - the `Tracker` a planning seat carries `:191`: `begin` (turn, step, sequence, window) `:239`,
    `encode` (the read-back) `:256`, `forecast` `:269`, `end` (the uses; a pick's target `:301`),
    `result` (labels and plan-following's read-back) `:308`;
  - the hindsight labels `:323` with the when bucket `:354`; a forecast or labels by object
    `:144`, and back onto a decision's rows `:156`; a training row's arrays `:364`.
- *The network*, `model.py`: a planner network has `"planner"` in its config, and its layers are
  built after `_init` (`:87-89`, `_add_planner` `:102`): the read-back's embeddings (`:175`,
  added at `:204`) and target pointer (`:213`); the forecast heads (`forward(b, plan=True)` `:230`,
  `forecast` `:246`: when, verb and window logits per card token, the target a "none" logit and a
  bilinear pointer to every entity); argmax forecasts `:465`. `load(..., planner=True)` `:567`
  makes an older network a planner network whose planner layers are zero (`upgraded` `:562`).
  `Packed` carries a planner run's arrays (`:352`, `:425`).
- *The actor*, `actor.py`: `NetAgent` carries a tracker when its job says its network plans
  (`:107`); `decide` `:118`; the network's answer with its forecast (want 4) `:150`; a recorded
  seat's labels come back in the result `:400`.
- *The learner*, `learner.py`: the flags `:1469-1480`; a run's network is a planner exactly when
  `--planner` is on `:343`; a job's seats plan when their networks are planners `:573`; the
  forecast in the inference's answer `:738`, `:771`; the rows' arrays `:880` (a count that does
  not match the rows: `plan_misaligned` `:874`, `:1288`).
- *The losses*, `ppo.py`: plan-following's decisions drawn once per update `:140`; the terms
  `:189`, `planner_terms` `:265`; the iter row's `plan` `:257`.
- *The puzzle runner*, `tools/puzzles/runner.py`: a planner network's root forecast per plannable
  object, by pack key `:94`, `:125`, printed per checkpoint `:189`.
- *Tests*: `tools/selfplay/test_planner.py` (12; each fails on 1daae58e, where the planner does not
  exist; the review's two also fail with their fix taken out) and
  `tools/puzzles/test_runner.py::test_a_planner_network_reports_its_forecast_at_the_root`.

**Why each choice:**
- *Labels, not a hidden vector* (§3.4): readable, observable after the fact, nothing that drifts
  with the weights.
- *One object = a handle and its latest zone-change clock* (CR 400.7). The engine reads 400.7 the
  same way (`returns.moved_since`) but scans the journal back at every call; the tracker reads each
  journal row once.
- *A sequence's boundary from `Executor.step_actions`*: the engine's own count of each player's
  priority actions in the step (CR 117.3c), public and reset each step, so no new bookkeeping.
- *Plannable cards from `permits.playable`*: the engine's own answer, whatever the timing or the
  mana now; about 15 µs a decision (the whole tracker adds 10-20 µs to `encode`'s 140).
- *A planner network is its own kind (`"planner"` in the config only when on)*, not a layer every
  network carries: a network without it keeps the parameters, the config and the computation it
  had, and an older checkpoint becomes a planner only when asked.
- *The planner's layers built after `_init`*: so a seeded build draws every older layer's weights
  as before. `named_ptr`'s comment claimed this for being registered last, but its construction
  draw, before `_init`, had moved every older layer's seeded weights (measured; comment corrected).
- *Linear heads*: an older network's planner layers start at zero, and a zero linear layer learns
  where a zero two-layer head never moves.
- *A bilinear target pointer*: as the policy's options point at entities, with no card vocabulary.
- *Forecasts are each head's argmax*, never sampled (§3.3).
- *The latest forecast replaces the last one whole*: the seat's latest forecast is its latest
  decision's, and plan-following's read-back is built the same way from that decision's labels.
- *Labels computed in the worker at the game's end*: the per-object work stays off the learner's
  serving thread (3-8 ms a game).
- *A void game trains no side loss*: its future is unknown, and "never" would be a false label.
- *The hindsight loss per decision is the mean over its plannable objects*: a decision weighs the
  same whatever its board's size, as in PPO's terms.
- *Plan-following weighted 1/share*: the term's expectation is the mean over every eligible
  decision whatever `--follow-share` is, so the share buys compute and `--follow-coef` alone sets
  the weight.
- *PPO stays on the inputs as played* (§3.1): a relabelled input would break its ratio.
- *A run's network and `--planner` must agree* (refused otherwise): a planner network trained
  without its read-back or its losses, or the reverse, would change silently.

**Where it departs from this design or the brief:**
- *when has 10 classes*, the ten §1 lists (the brief said 11 and listed the same ten).
- *The read-back is blank* in the search's simulations, the labeller's path, `linevalue.py` and
  `trace.py`, which encode with `features.encode`; a searched decision writes no forecast, so the
  last one stands. v1's training games do not search; search over plans is v3.
- *Uses*: `tap` and `remove_counter` cost choices are none (§1 names sacrifice, discard and exile);
  every sacrifice, discard or exile choice of an object is a "cost" use, an edict's or the
  cleanup's discard too; an "up to" choice answered NONE picks no object and is no use.
- *A use's target* is the first pick of the first target slot of its own cast or activation
  (`pick:<source>:0:0`). A trigger's targets aim no use; a slot with one legal target is filled by
  the router without asking, so that use has no target.

**Assumptions, and what each would do if wrong:**
- *A use is one of the seat's own decisions* (a land, cast or activation row; an attack; a block;
  a sacrifice, discard or exile choice). A land that only pays mana is never used, since the engine
  pays (BACKLOG "Automatic payment"). If payment, triggers' choices or forced answers should count,
  the labels say "never" for objects that were in fact used (60-80% of the smoke games' labels are
  "never"), and a forecast cannot express a plan that works through payment. When the network pays
  its own mana, mana rows become uses.
- *A sequence ends at a new turn, a new step, or an action of the opponent* (a cast, an activation
  or a land: `step_actions`). The opponent's blocks and triggers' choices do not end one: blocks
  come in a step whose first decision of mine starts a sequence anyway, but a trigger's choice
  between two of my decisions in one step would join them. If that is wrong, A1-A4+ claim an order
  across the opponent's interjection, and "later this turn" is under-used.
- *One object is a handle with no zone-change row since*, and the engine journals every move made
  in play. One path does not: the London mulligan edits the zones itself (`games.mulligans`), so
  the tracker renews the cards it moves (the hand on "mulligan", each card a bottom ask picks; the
  review found this). Every other direct zone edit in the executor was read: a token ceasing to
  exist, a position within a zone after a journalled move; setup's draws come before any
  decision. Another unjournalled move would keep a plan across it and join two objects' uses
  under one label; a ZONE_CHANGE row with no real move would drop a plan early. A control change
  keeps the object (CR 400.7 is about zones), as intended.
- *Plannable objects*: the seat's hand, its permanents, its own cards a permission reaches. A card
  in the opponent's zone the seat may cast (`permits` names only the seat's own zones) and a
  commander in the command zone are not plannable: their uses still count in the A-order of
  others, but they get no forecast and no label.
- *"never" needs the game's end*: labels come only from games played to their end (a turn-cap draw
  included: there "never" means not before the cap).
- *The window is the use's decision's own context*: a cost paid while casting a sorcery-speed
  spell reads "my main phase" (the spell is not on the stack yet; measured in the cost test).
- *The four heads are separate*: each is its own argmax, so a forecast may pair "never" with a
  verb; the read-back carries what the heads said.
- *Plan-following's input is the previous sample's realized labels*: the decision whose forecast
  the read-back carried, read back by object as the forecast was. It holds the round's exploration
  as played (as hindsight relabelling does: "act like the rounds that carried this plan out"). If
  the plans the policy meets at play time (forecasts) differ in kind from these labels, for
  instance in how often they say "never", plan-following teaches it to read plans it will not be
  given; the A/B reads that.

**Checked:**
- *Without `--planner`, bitwise what 1daae58e computes* (at the final commit): one seeded learner
  path run on both codes (a fresh build, six training games through the learner's sampled
  inference, their rows, one PPO update): the same weights at the start, games, 541 rows'
  encodings (the new columns 0), actions, log-probs, values, advantages, every PPO statistic, and
  the weights after the update. Single-threaded CPU: with two threads main differs from itself
  after an update.
- *The CPU smoke* at the final commit (2 workers, d 32, 1 layer, 512 steps; 2 updates, then a
  resume to 3; no void game, no misaligned row), the iter rows' `plan`. The heads start uniform,
  so the hindsight loss starts near ln 10 + 2 ln 7 + ln(3 + E); three updates of fresh games show
  the plumbing works, not a learning curve:

| update | decisions | hindsight loss | when | verb | window | target | plan-following NLL | objects | rows |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 552 | 9.39 | 0.40 | 0.56 | 0.56 | 0.91 | 0.99 | 6,128 | 145 |
| 2 | 597 | 9.49 | 0.62 | 0.66 | 0.66 | 0.88 | 0.94 | 6,437 | 158 |
| 3 (resumed) | 554 | 9.07 | 0.64 | 0.64 | 0.63 | 0.92 | 1.04 | 5,863 | 147 |

**The fresh-eyes review** (one reviewer, from the diff; it changed nothing). It checked the
hindsight labels against a brute-force reference on 2,000 random records (all equal), the index
conventions, the alignment of labels with rows, the off path and every network rebuild. Two real
faults, both fixed with a test that fails without the fix:
- *The mulligan joined objects across its unjournalled moves*: in 10 sampled games, 13 of 16
  mulligans' old-hand cards came back as the same object, and 4 of those labels were a later use
  instead of "never". Now 0 (`Tracker._renew`).
- *An "up to" sacrifice or discard answered NONE was a "cost" use of no object*, which took an
  A-slot from every later use in its sequence (Kinetic Augur: the land after it read A3). Now no
  use (`uses_of`).
Two nits were taken (`begin` lost an unused argument); the per-micro-batch syncs of the planner's
counts were left (a few a micro-batch, beside PPO's own).

**Engine helpers, proposed and not built** (the engine was not touched):
- CR 400.7's object identity kept by the engine: a clock per handle written where each ZONE_CHANGE
  row is journalled (one dict write), so every reader (`returns.moved_since`, permissions, the
  planner) asks in O(1) instead of scanning or tracking the journal.
- The mulligan's moves journalled as one atom boundary (BACKLOG "To triage"), after which the
  tracker's renewal goes.

**Next:** the registered A/B against the control on every puzzle category and on L (§5). The
choices this v1 made by hand are BACKLOG scaffolds: the vocabularies, and the side losses'
coefficients and share.

**Before the A/B: the red team's fixes to the code** (KNOWLEDGE/2026-11-18/216; the code may stay
merged behind its flag as it is). One agent builds them, after item 6, the optimizer state.
- **P1. The puzzle runner reads a planner network with a blank read-back.**
  - Why it matters: in training, every decision after a seat's first reads back its last
    forecast. So the A/B's puzzle read would measure the planner off its own distribution.
  - The fix: `runner.root` gives the decider's scripted prelude driver a
    `planner.Tracker(seat, keep=False)`. At each of its asks:
    1. `begin`;
    2. encode through the tracker;
    3. ask the network for its forecast and pass it to `forecast`;
    4. answer the scripted word;
    5. `end`.

    The root is encoded through the same tracker.
  - Report both roots, blank and carried, for one checkpoint, so the size of the difference is on
    record.
  - L's reads through the learner's `--eval-only` already set `job["plan"]` per seat: no change
    there.
- **P4.** The iter row's `plan` reports each head's per-class recall (macro-averaged), not the
  overall accuracy. 60-80% of "when" labels are "never", which "always never" already scores.
- **P5.** The following mask is drawn from the trainer's rng, which also deals the minibatch order
  (`ppo.py:132`, `:140`). The order is drawn first, so an update's own order is unchanged. But the
  mask's draws move the rng, so every later update's order differs from the control's at the same
  seed. Draw the mask from its own substream (`rng.py`), so the arms share their minibatch orders.
- **P6.** `_aim` relies on the cast's hand-to-stack ZONE_CHANGE row being journalled after the
  target asks (`stack.py:838-840`).
  - Add tests for a creature target and for an activated ability's target.
  - Add a comment in `Tracker.end` naming that engine fact, so a change in the park's boundary turns
    a test red.
- **P2, item 3 (a choice to measure, not yet made).** A flag that shifts the following loss's
  read-back to uses strictly after the current decision.
  - Why: today the read-back row of an object used now names this very action, so the loss can
    learn "copy the row" rather than "act consistently with what you will do later".
  - Measure both forms on the CPU smoke before choosing. v3's search needs the unshifted form, so
    the flag stays.
- **P7, on v3's build list.** The searcher's simulated seats carry a tracker. That must hold before
  any L read of a planner network with search, since the deployment target is search at play time.

## 8. Do the borrowed methods transfer? Assumptions, and what they change (the owner, 2026-11-18)

The owner asked whether the literature's assumptions hold here, and that every assumption, theirs
or the coordinator's, be named with its effect on the conclusions. Each borrowed method:
- its own assumptions;
- which fail here;
- what the design does about it.

| Method | Its assumptions | Here | What it changes |
|---|---|---|---|
| Hindsight relabelling (HER, Andrychowicz et al. 2017; the "upside-down" goal-conditioned family) | Goals are states the agent can reach, and the reward is defined by the goal, so a relabelled transition is a valid sample for its new goal and can train the policy with its reward | Our goal is winning against an opponent who adapts. A plan is not a reward-defining goal, so relabelling cannot create valid PPO samples (the behaviour log-probabilities were for the plan as played). | Plan-following is a **supervised side loss** only (self-imitation given the realized plan). It makes plan inputs causal for the realized plan; it claims none of HER's sample-efficiency gains. The train/test gap (realized plans in the side loss, forecasts at play) is a known risk, read in the A/B. **If wrong, also** (216 P8): at play the read-back is the argmax forecast of the policy's own habit, so it is causal only as far as the forecast-habit loop of §3.1 allows. That loop sharpens habits; the entropy kill of §5 reads it |
| Options and intra-option learning (Sutton, Precup & Singh 1999; option-critic) for the round style | Options are temporally extended behaviours with their own termination. Their values can be learned from any experience under the option. Option discovery tends to collapse without an incentive | The style is a label, not a sub-policy. Its "termination" is the round's end. Collapse is real (§3.2) | Styles are hindsight labels of observable round statistics, so they carry meaning by construction. The style critic V(state, style) is learned on-policy from rounds played in that style. Choosing by it is an approximate improvement step, only as good as each style's coverage (ε) |
| Gumbel AlphaZero / MuZero policy improvement (Danihelka et al. 2022) and expert iteration (Anthony et al. 2017), for search over plans | A perfect-information model or a learned one, and a value accurate enough at the leaves. The improvement guarantee is relative to the value used | The game has hidden cards. Worlds are sampled from the opponent simulator (PIMC with per-seat views in the playouts, no fusion inside a playout). The value is weak where the puzzles fail (C) | The search's targets inherit the simulator's and the value's errors, so its pull on the planner anneals (PLAN_CEILING's own caveat). Information-set MCTS comes in if the puzzles show strategy fusion. The guarantee does not carry over; only measured improvement on the puzzles and on L counts |
| Reverse curriculum (Florensa et al. 2017; Salimans & Chen 2018), for puzzle starts (PLAN_PLANNING P2) | The environment resets to chosen states near the goal; the task is goal-reaching with a sparse reward; a demonstration to roll back along | Resets: yes (the pack world arranges any position). The opponent is a learner or the league, not a fixed environment. The positions are arranged, not natural (a shift of the state distribution). The demonstrations are the solver's proven lines | Starts are generated variants, not the evaluation puzzles. Their share anneals, and a skill that fades when they are removed is read as a habit (PLAN_PLANNING P2). That no goal is fixed under an adapting opponent is accepted: the reward stays the game's result |
| Prioritized Level Replay (Jiang et al. 2021), for replaying deals | A level is a seed that replays exactly. A scoring proxy (value error) tracks learning potential. Its theory (minimax regret) is for single-agent environment design | Deals are seed-replayable. The learning potential also depends on the opponent (two-player zero-sum), so the score is noisier and moves with the league | Used as a heuristic prioritizer, not for its guarantees. Its score is the value error in the learner's own games, decayed so a deal's score does not outlive the opponent it was earned against |

**The coordinator's assumptions behind the planner, and what follows if each is wrong:**
- **"Forecasting one's own uses helps play."** A hypothesis.
  - If wrong: v1's A/B shows no gain on the puzzles or on L, and the side losses are dropped.
  - The stake is small, because the planner is off by default.
- **"The flat r29 means the learning signal is the limit, not capacity or the deals."** Supported:
  - the capacity probe (194) found no gain from size;
  - the puzzles show habits;
  - deals were not tested.

  If wrong (the deals are the limit), the Teacher and drafter matter more than the planner. Both
  are being planned.
- **"Proven puzzles measure planning in real games."** The puzzles are small, two-turn positions.
  A network can pass them and still plan badly over a whole game.
  - The puzzles are a necessary signal, not a sufficient one; L and the long run's play decide.
  - The suite grows with harder and larger positions as the solver allows.
- **"A sequence is the seat's run in one step with no opponent action between."** If this splits
  real sequences wrongly (an opponent's mana ability, a trigger), the A-order labels get noisy. The
  build's tests pin the boundary on real games.
- **"The when buckets and window kinds are fine enough."** If too coarse, the forecasts carry less;
  if too fine, they are noisy. Hand-set and said aloud in §6, and read through the forecasts'
  accuracy per head.

**The owner's assumptions, as the coordinator understands them, and their effect:**
- **"A plan for every card is more useful than a few slots."** Adopted; tested by v1's A/B.
- **"Multi-turn search with the planner makes both better."** Plausible by the mechanism in §4,
  but not yet measured. It is v3's question, and it gets its own registration.
- **"TURN_CAP 125 almost always gives the full signal."** True for any game without an effect that
  returns cards to a library (the decking rule). The `turn_caps` count per update says whether
  that assumption holds in play.
