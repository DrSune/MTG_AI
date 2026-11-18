# Design: the per-object planner, and search over plans

Status: **design, not built** (2026-11-18).
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

**What an intention says (readable, all observable after the fact):**
- *use*: one of
  - A1 to Ak, the order of this action sequence's uses;
  - the next sequence;
  - within two rounds;
  - later;
  - never.
- *verb* of its next use: cast or play, activate, attack, block, a cost (sacrifice, discard,
  exile), or hold.
- *after*: the journal's event kind just before its use, such as the opponent's cast or attack,
  or one's own turn.
- *target* of its next use: a pointer to an entity, as the policy's options point.

A "use" is mechanical: the object is the subject of one of its player's own decisions (an option
that points at it).

**How it is carried:**
- Heads on each object's token write its intention at every decision.
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

## 5. Build steps (each read on its puzzles, KNOWLEDGE/2026-11-18/214)
1. **v1:** use, verb, after and target labels on every plannable object; hindsight heads; the
   label columns read back; plan-following. A registered A/B against the control on puzzles A and
   C and on L.
2. **v2:** the two-round horizon and holds; puzzles B and D.
3. **v3:** round styles, the style critic, styles sampled at ε; the combo and sweeper puzzles.
4. **v4:** search over plans, multi-turn (P3).
5. **Then:** the hidden vector, measured (3.4).

## 6. Choices said aloud (the learnable-over-hardcoded rule)
- **The use buckets.** The maximum A-index k, and "within two rounds" as the last bounded bucket.
  Removable: a learned distribution over the number of turns to use.
- **The style statistics** (3.2). Removable: a learned clustering of rounds.
- **The side losses' weights** (hindsight, plan-following). Read on an A/B; a weight that is too
  high pulls the trunk from winning.
