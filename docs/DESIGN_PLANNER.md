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

## 8. Do the borrowed methods transfer? Assumptions, and what they change (the owner, 2026-11-18)

The owner asked whether the literature's assumptions hold here, and that every assumption, theirs
or the coordinator's, be named with its effect on the conclusions. Each borrowed method:
- its own assumptions;
- which fail here;
- what the design does about it.

| Method | Its assumptions | Here | What it changes |
|---|---|---|---|
| Hindsight relabelling (HER, Andrychowicz et al. 2017; the "upside-down" goal-conditioned family) | Goals are states the agent can reach, and the reward is defined by the goal, so a relabelled transition is a valid sample for its new goal and can train the policy with its reward | Our goal is winning against an opponent who adapts. A plan is not a reward-defining goal, so relabelling cannot create valid PPO samples (the behaviour log-probabilities were for the plan as played). | Plan-following is a **supervised side loss** only (self-imitation given the realized plan). It makes plan inputs causal; it claims none of HER's sample-efficiency gains. The train/test gap (realized plans in the side loss, forecasts at play) is a known risk, read in the A/B |
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
