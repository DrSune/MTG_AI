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
   - **What it should move.** Memory, holds and coherence should move B (counters), D
     (overextension) and A (sequencing). The C failures (attacking into a lethal crack-back, not
     chumping) are value errors that v1 reaches only through the forecasting task, so no
     prediction favours them.
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

## 7. Built: v1 (2026-11-18)

Behind the learner's `--planner` (default off; the flags in `tools/selfplay/README.md`). Off,
nothing of it runs (checked below).

**The pieces** (file:line at the commit that built them):
- *The read-back*, four card columns appended: `features.py:191` (`C_PLAN_WHEN`, `_VERB`,
  `_WINDOW` as the vocabulary's index + 1, `C_PLAN_TARGET` an entity pointer + 1; 0 none). `encode`
  leaves them 0; `encode_entities` (`:614`) also returns the entities' handles in encode order.
- *`tools/selfplay/planner.py`* (numpy only: the workers run it):
  - the vocabularies `:67-80`; the window of a decision `:91`; the uses an answer makes `:106`;
    the plannable objects `:128`;
  - one object `:221` (a handle and the journal clock of its latest zone change, read
    incrementally `:210`);
  - the `Tracker` a planning seat carries `:189`: `begin` (turn, step, sequence, window) `:225`,
    `encode` (the read-back) `:242`, `forecast` `:255`, `end` (the uses; a pick's target `:281`),
    `result` (labels and plan-following's read-back) `:288`;
  - the hindsight labels `:303` with the when bucket `:334`; a forecast or labels by object
    `:142`, and back onto a decision's rows `:154`; a training row's arrays `:344`.
- *The network*, `model.py`: a planner network has `"planner"` in its config, and its layers are
  built after `_init` (`:87-89`, `_add_planner` `:102`): the read-back's embeddings (`:175`,
  added at `:203`) and target pointer (`:212`); the forecast heads (`forward(b, plan=True)` `:230`,
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
- *Tests*: `tools/selfplay/test_planner.py` (10; each fails on 1daae58e, where the planner does not
  exist) and `tools/puzzles/test_runner.py::test_a_planner_network_reports_its_forecast_at_the_root`.

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
  every sacrifice, discard or exile choice is a "cost" use, an edict's or the cleanup's discard too.
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
- *One object is a handle with no zone-change row since*. A move the journal does not record as a
  ZONE_CHANGE (none known; setup placements come before the tracker reads) would keep a plan across
  the move and join two objects' uses under one label; a ZONE_CHANGE row with no real move would
  drop a plan early. A control change keeps the object (CR 400.7 is about zones), as intended.
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
- *Without `--planner`, bitwise what 1daae58e computes*: one seeded learner path run on both codes
  (a fresh build, six training games through the learner's sampled inference, their rows, one PPO
  update): the same weights at the start, games, 541 rows' encodings (the new columns 0), actions,
  log-probs, values, advantages, every PPO statistic, and weights after the update. Single-threaded
  CPU: with two threads main differs from itself after an update.
- *The CPU smoke* (2 workers, d 32, 1 layer, 512 steps; 2 updates, then a resume to 3), the iter
  rows' `plan` (at the start the heads forecast uniformly; the hindsight loss starts near
  ln 10 + 2 ln 7 + ln(3 + E)):

| update | hindsight loss | when | verb | window | target | plan-following NLL | objects | rows |
|---|---|---|---|---|---|---|---|---|
| 1 | 9.47 | 0.47 | 0.61 | 0.60 | 0.89 | 0.91 | 6,565 | 155 |
| 2 | 9.26 | 0.56 | 0.60 | 0.61 | 0.87 | 1.00 | 5,945 | 144 |
| 3 (resumed) | 8.97 | 0.59 | 0.62 | 0.56 | 0.92 | 1.06 | 5,415 | 140 |

**An engine helper, proposed and not built** (the engine was not touched): CR 400.7's object
identity kept by the engine, a clock per handle written where each ZONE_CHANGE row is journalled
(one dict write), so every reader (`returns.moved_since`, permissions, the planner) asks it in O(1)
instead of scanning or tracking the journal.

**Next:** the registered A/B against the control on every puzzle category and on L (§5). The
choices this v1 made by hand are BACKLOG scaffolds: the vocabularies, and the side losses'
coefficients and share.
