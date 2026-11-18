# Plan: planning — how options reach the network, planning puzzles, and a ceiling-raising ladder

Status: **adopted 2026-11-18 by the coordinator under the owner's autonomy rule** (the owner asked
for it the same day; the owner may overrule any step). It sits beside
[`PLAN_CEILING.md`](PLAN_CEILING.md) (search, F1, the league, H2), which it does not replace, and
it takes [`DESIGN_ACTION_SPACE.md`](DESIGN_ACTION_SPACE.md) (the plan decoder, proposed and not
built) as a later option.

The owner, 2026-11-18:
> "How should we present options the best for our network? Do we present only legal options NOW,
> meaning it has to tap lands before seeing anything else? It can only see its legal targets once
> it chose to attack etc? ... It will not have that high of a ceiling though, since we need complex
> planning per-turn, and multi-turn planning even, or at least take value function etc into
> account when choosing what to do this turn ... Global reward maximization."
>
> "Do we have good puzzles for testing whether it can do planning like this? ... it should save its
> counterspell ... to make sure its own devastating plan pays off. One that shows option to
> instantly end the game if it counterspells well, but also ones where it is just the optimal thing
> to do, though it doesn't end the game too fast."
>
> "Use expert methods ... maximally high ceiling ... intermediate steps that make sure
> planning-gradient is sufficient at all times, by nudging it towards more/better planning before
> doing the no-ceiling scenario where we likely have to remove direct incentives, hardcodings and
> rules ... Then make a plan ... how and when we implement this alongside the other stuff."

## Summary for the owner

**How a turn reaches the network today.** One decision at a time, each from a menu of only the
legal options (§1).
- At a priority point the menu holds every legal action at once: land drops, every castable
  spell (one row per X), every activation.
- The network never taps lands: the engine pays every cost by a fixed rule.
- Targets, modes and costs come as the next decisions, after it picks the spell.
- Attackers and blockers are declared one creature at a time.
- At every decision the network sees the whole visible game, so it can weigh the targets before
  it commits to the spell.
- There is no lookahead in training, and no memory of earlier turns.

**Is that the ceiling? Mostly no.**
- Choosing in sequence can express any joint choice (the chain rule of probability), as long as
  the network sees its partial choices, and it does. AlphaStar and OpenAI Five act the same way.
- The objective is already global: γ = λ = 1 and a ±1 result, so every decision is scored by the
  final outcome.
- Four things limit planning (§2):
  1. **The learning signal.** A plan of several coordinated moves is rarely tried at random, and
     one game result is spread over about 84 decisions.
  2. **No lookahead in training.** Lookahead pays: searched at n = 4, the network beat its raw
     self 0.566, +46 Elo (KNOWLEDGE/2026-11-13/205 §9). The policy has not absorbed what the search
     finds.
  3. **No memory.** "They held mana up last turn" or "they revealed a Negate" is invisible.
  4. **Decisions the engine makes for it.** Mana payment, so it cannot keep its Islands open for a
     counterspell by paying with Mountains.

**Do we have puzzles for planning? No.**
- The 764 scenario packs test the rules, not decisions.
- The line-value tool (`tools/selfplay/linevalue.py`) can force "cast C" lines, but not a hold, a
  target or an attack.
- §4 specifies a planning puzzle suite. It has counterfactual twins (same board, one piece of
  evidence changed, the right move changes), and every answer is verified by forced-line playouts
  in our own engine.

**The ladder** (§5). Each rung has a gate and a readout. The nudges change what the learner meets,
never what it is paid for, so none caps the ceiling. The last rung removes them.

| Rung | What | Why it keeps the ceiling |
|---|---|---|
| P0 | **Measure planning**: the puzzle suite, its runner and a planning dashboard | changes no training |
| P1 | **Remove the representational limits**: payment as a decision where it matters (O1); memory v1, explicit history features | adds choices and information; removes a scaffold |
| P2 | **Frequency nudges**: puzzle states as training starts (a reverse curriculum), replayed by their learning value; frozen specialists in the league | the reward stays ±1; only the starting positions and opponents change |
| P3 | **Planning as policy improvement**: search-improved training (expert iteration with Gumbel search over sampled worlds), PLAN_CEILING's F1 and gates A/B | value targets stay real results; the search's pull anneals |
| P4 | **The no-ceiling run** (PLAN_CEILING's H2): every nudge annealed to zero; outcome self-play with a league, exploiters and search at play time | nothing hand-made left in training; puzzles and L guard against regression |

**When** (§6). This week: the puzzle suite (CPU, mine), beside the card work and r29. At r29's
FDN segment: the zero-fallback fix and the engine fixes. Next week, after the budget reset: O1
and memory v1 as one registered A/B, then the curriculum arm, then P3's gates.

## 1. How options reach the network today (read in the code, 2026-11-18)

| Decision | Menu (engine) | What the network scores |
|---|---|---|
| Priority, sorcery speed (`act`, `act_second_main`) and instant speed (`priority`) | `MTG_bot/core/executor/menu.py` `menu`: every legal action now (CR 117.1), each already priced: land drops; `cast:<card>` once per cost path, kicked and per X from 0 to the largest payable X; non-mana activations. Mana abilities are not rows: the engine pays (`legality.plan_mana_taps`, scaffold "Automatic payment") | one token per row: its type, its card's entity, its X; every token attends to every visible card (`tools/selfplay/model.py` `tokens`, `forward`) |
| Modes, targets, X-dependent and cost choices | the next asks after the row is chosen: `choose`/`one_of` (modes), `target` per slot (the slot in `glob_f`), `sacrifice`/`discard`/`exile`/`remove_counter` cost choices | one token per legal candidate, pointing at its entity |
| Combat | `attack` per creature (player, a planeswalker, or decline), `block` per blocker, `divide` per blocker of a blocked attacker | the declared attackers and blocks so far are card columns |
| Triggers, library, misc | `trigger` order, `scry`/`arrange`, `may`, `name`/`quality`, mulligan | as above; since 2026-11-18 every ask is the network's (KNOWLEDGE/2026-11-18/213) |

The network sees at every decision:
- its hand;
- every public card, with no cut since 213;
- the stack, in order, with sources and first targets;
- players' life, mana pool and untapped lands;
- the step, and whether the other player just passed (DESIGN_PRIORITY §3.2).

It does not see its own decklist (measured not material, 200 §1), the game's history (BACKLOG "The
observation holds no turn history"), or what the opponent revealed earlier.

**The owner's two questions, answered.**
- **"Does it have to tap lands before seeing anything else?"** No. It never taps lands. Every
  affordable action is one row, and the engine pays.
  - The cost of that rule: the payer keeps the most colours open
    (`legality.plan_mana_taps`, BACKLOG "Automatic payment"), not the colours the network's plan
    needs.
- **"It can only see its legal targets once it chose to attack?"** It sees the whole board when it
  chooses. The target menu (and the attack menu for the next creature) comes after the commitment.
  - That is the autoregressive factorization. The value of "cast Shock" must anticipate the best
    target, and the value head learns that.
  - The decision-time search compares whole attack plans (`search.Searcher.plan_attacks`), but the
    search is not part of r29's training.

## 2. What limits planning, ranked by expected impact

1. **The signal for coordinated lines.**
   - PPO's per-decision gradient sees only what the policy tries (198 §2; PLAN_CEILING §14.2).
   - A line such as "pass with Cancel mana open on my turn, counter their bomb on theirs, then
     cast my threat" needs three non-default moves in a row.
   - One ±1 result spread over about 84 learner decisions a game (r29 arm A: 139,284 steps in
     1,654 games) is a weak, noisy credit for any one of them.
2. **No lookahead in training.**
   - The policy is a learned reflex plus a learned value.
   - The search (`tools/selfplay/search.py`) works as follows:
     - it forks the game (`tools/search/fork.py`);
     - it re-samples what the seat cannot see;
     - it plays each candidate out with the network on both seats;
     - it scores by result or value, with a Gumbel root and sequential halving.
   - Searched at n = 4 it wins 0.566 against its own raw network on coherent decks (205 §9).
     That gap is planning the policy has not absorbed.
3. **No memory.** In a game with hidden cards, history is evidence: what they held mana up for,
   declined to block with, or revealed (OWNER_VISION_LEARNING §3). A board-only network cannot
   tell "they surely hold a counter" from "they might".
4. **Decisions made for the network.**
   - Mana payment (which sources tap).
   - A mana ability used for its side effect (a Treasure sacrificed in response to its removal,
     CR 605.3a).
   - Both are registered scaffolds. Payment is the one that blocks within-turn planning: holding
     the right colours open for an instant.
5. **Not limits** (kept, by decision):
   - **The sequential, legal-only menu.** Masked by construction. No illegal action holds any
     probability mass, and DESIGN_ACTION_SPACE §8.1's mask-fidelity risk does not arise.
   - **The pointer policy over option tokens.** It works at any menu size since 213.

## 3. How options should be presented: decisions

- **Keep** the sequential, legal-only menu and the pointer policy (§2.5).
- **O1, payment as a decision where it matters (build now, ship with memory v1).**
  - **When it is asked.** When a chosen row can be paid in ways that leave different things open,
    the engine asks `pay`.
  - **Its options.** The distinct outcomes, not tap orders. An outcome is the set of untapped
    sources left, deduplicated by the mana those sources can still make together. Each option
    points at the sources it taps.
  - **When it is not asked.** If every payment leaves the same, nothing is asked: most casts stay
    one decision.
  - This removes the scaffold's real cost: "pay with Mountains so Cancel's {1}{U}{U} stays open".
    It starts from DESIGN_ACTION_SPACE §1.3's PAYMENT asks.
  - **Kept for now: mana abilities for side effects.** That needs instant-speed mana rows, the
    menu-cost problem of DESIGN_PRIORITY §2.7.
- **O2, consequence previews (measure first, do not ship blind).** Each act row could carry what
  it leaves:
  - mana left after paying;
  - how many other rows stay affordable.

  That is a one-step lookahead read from the menu's own pricing. Built only if the puzzle suite
  shows within-turn sequencing failures that O1 and training do not fix. It is an input change,
  so it gets a registered A/B.
- **Not now: the plan decoder** (DESIGN_ACTION_SPACE: K moves from one forward pass).
  - Its value is latency, actions per forward pass, for the match clock (King, tied).
  - It does not look ahead: a K-move plan is still a reflex.
  - Revisit it when latency is measured against the clock (DESIGN_LATENCY), after P3.
- **Not ever: whole-turn action trees as options.**
  - The number of joint options explodes.
  - Search compares lines better and is already built.

## 4. The planning puzzle suite (P0)

**What a puzzle is.** An arranged game in the scenario packs' world format (`tools/scenarios`):
- both players' cards in every zone, the hidden ones included (hand, library order);
- the deciding seat and the decision point;
- the evidence the seat has: the visible state, and from memory v1 on, the history;
- the set of right first decisions;
- `world_prior`: the distribution of the opponent's hidden cards that the evidence supports, used
  to draw the verification futures.

**How a puzzle is verified (before it counts).** The right line and every plausible alternative
are forced at their decisions and played to the end on shared futures drawn from `world_prior`
(the labeller's machinery, horizon 0, as in `linevalue.py`). Two reference continuations play it:
the heuristic, and the searched network.
- The right line must beat every alternative by a registered margin with its standard error.
- A puzzle whose answer depends on the reference player is labelled so, or dropped.
- This keeps the suite honest: our engine and our cards decide the answer, not the author's
  intuition.

**Twins.** Every puzzle has a counterfactual twin: the same board, one piece of evidence changed,
the right move changed. A network that holds Cancel by habit passes one twin and fails the other.
The headline number is the twin-consistent pass rate.

**Categories, first wave (16 puzzles, 8 twin pairs, M21/M20 verified cards).**

| Cat. | Skill | Example (one twin pair) |
|---|---|---|
| A | Within-turn sequencing | Draw first, then pick the land (an Opt-like draw before the land drop) / the land first when the draw cannot change it. Removal before combat to clear the blocker / after combat when the attack is safe either way |
| A-pay | Colours kept open (needs O1) | Pay the creature with Mountains so Cancel stays castable on their turn / with Islands when no counter is held |
| B1 | **Counter for the immediate win** (the owner's first example) | You attack for lethal; they cast the one spell that stops it (a flash blocker or removal): counter it with Cancel or Rewind and win now / the same spell when your attack is not lethal anyway, where the counter is better kept |
| B2 | **Hold the counter so your plan sticks: slow but best** (the owner's second example) | You hold your bomb and Cancel; their open blue mana and the evidence say they hold a counter. Pass with Cancel up or bait first, and win two turns later / the same board with them tapped out: cast the bomb now |
| B3 | Save the answer for the real threat | Hold Negate or Bone to Ash through a minor spell for the bomb their board demands / counter the minor spell when nothing bigger is possible |
| C | Combat | Don't attack: the crack-back is lethal / attack: it is not. Chump now to live to the sweeper (Planar Cleansing, Flame Sweep) / take it when the life allows |
| D | Multi-turn | Don't overextend into a sweeper they are known to hold / overextend when they cannot have one. Set up the package payoff next turn |
| E | Reading the opponent (needs memory v1) | They held two Islands open through your last turn and passed / they tapped out: play around the counter or not |

**Readouts per checkpoint** (CPU, the network is small enough):
- the raw policy's probability on the right move;
- its greedy pick;
- the twin-consistent pass rate per category;
- the value head's error on the puzzle states, against the verified line values;
- the searched pass rate at n = 4, which gives the search's planning headroom per category.

Every gate checkpoint of every run is read. The evaluation puzzles are never trained on. Training
uses generated variants (§5, P2).

## 5. The ladder in detail

**P0, measure (this week; CPU; no training change).**
- The puzzle format, the runner and the verifier, all on the existing pack world and labeller
  code.
- The first wave of §4.
- Read r28's v2 and r29's snapshots (a70-a100, b70-b100).
- Pair the suite with the line-value tool's barrier list (PLAN_CEILING §14.2): a line with
  positive value and near-zero use is an exploration barrier.

**P1, remove the representational limits (build next; one registered A/B at a run boundary).**
- **O1, payment decisions** (§3).
- **Memory v1, explicit history features**, cheapest first, as OWNER_VISION_LEARNING §3 and §4
  order them:
  - the opponent's untapped mana at each of their last two end steps and passes;
  - spells cast this game by type;
  - cards they revealed and that have not left their hand since (the engine records reveals as
    events, `verbs.py:1642`);
  - cards an effect put somewhere known (the top or bottom of a library) until a shuffle.

  Card-level facts go in zero-initialised columns, so an older network computes what it did.
- **Memory v2** comes later: an encoder over the event journal (attention over recent events), to
  share with the opponent simulator. It goes in only if E-category puzzles still fail with v1.
- **Gate.** The arm with O1 + v1 passes A-pay and E (puzzle readouts), and holds or beats the
  control on L (no regression).

**P2, frequency nudges (the curriculum).**
- **Puzzle starts, a reverse curriculum** (Florensa et al. 2017; Salimans & Chen 2018).
  - A share of training games starts from generated puzzle states: the same skills, other cards
    of the same roles, shifted life totals and boards.
  - It starts near the payoff, so the line's credit is short and strong. As a category's pass
    rate rises, the start moves earlier: more turns before the payoff.
  - **Starts replayed by learning value.** Prioritized Level Replay (Jiang et al. 2021): starts
    with large value error or regret are replayed more. This is the Teacher's first, cheap form
    (OWNER_VISION_LEARNING §6).
- **Specialists** (PLAN_CEILING §14.3).
  - A learner forced on one skill (holding counters, combo lines) by frequency.
  - It is frozen at its best win rate and joins the league as an opponent.
  - The main learner meets the skill without inheriting an incentive.
- **Not used in the main learner: reward bonuses for a held counter or a set-up line.**
  - Under γ = λ = 1 a potential-based bonus telescopes into a baseline and changes nothing in
    expectation.
  - An event bonus changes the objective, and is what gets hacked (PLAN_CEILING §14.3).
- **Gate.** Puzzle pass rates per category rise faster than in a control arm with the same machine
  time, and L does not fall.
- **Fade.** The puzzle-start share anneals on a registered schedule. When the share is
  removed, a category whose pass rate falls was learned as a habit. That category is read and
  retrained, not hidden.

**P3, planning as policy improvement (PLAN_CEILING §6, F1; its gates A and B).**
- **Expert iteration.** The network is trained toward what its own search chose (Anthony et al.
  2017). The search:
  - uses the Gumbel root and sequential halving, which improve the policy even at small n
    (Danihelka et al. 2022; built);
  - draws its worlds from the opponent simulator's beliefs rather than uniform re-samples (PIMC
    with per-seat views in the playouts, which avoids strategy fusion inside the playouts,
    OWNER_VISION_LEARNING §10).
- **Targets.**
  - The policy target is the search's improved policy, mixed with outcome PPO through a KL pull
    toward it (MCTS as regularised policy optimisation, Grill et al. 2020).
  - The value targets stay the real game results: unbiased whatever the search does.
- **The pull anneals.** The search inherits the value's and the simulator's errors, so its
  targets carry them (PLAN_CEILING's summary).
- **Gates.**
  - PLAN_CEILING's gate A: the search is well above its own network on fresh deals. It is
    already +46 Elo at n = 4.
  - Gate B: 300k targets move the network on unseen deals.
  - Now also: puzzle categories B and D rise (the multi-step ones).
- **Information sets later.** Information-set MCTS (one tree over all sampled worlds; Cowling et al.
  2012) only if the twins show strategy fusion: holds and bluffs valued as if the hidden cards were
  known.

**P4, the no-ceiling run (PLAN_CEILING §8, H2).**
- Every nudge anneals to zero: puzzle starts, the specialists' pull, the search targets' KL.
- What stays:
  - ±1, γ = λ = 1;
  - the league: main agents, frozen versions, specialists as opponents, and exploiters, chosen
    by prioritized fictitious self-play (Vinyals et al. 2019);
  - the search at play time only. That is test-time planning, and the match clock is a King-tied
    goal.
- The puzzle suite and L guard every update block. A drop after a nudge is removed is a finding,
  read and registered.

**Planning-gradient monitors, "sufficient at all times"** (on the dashboard from P0).

| Monitor | What it catches | The registered response |
|---|---|---|
| Puzzle pass rate per category, per gate | a skill not learned, or lost | P2 starts for that category (or P1 if its input is missing) |
| Line-value barriers (positive value, near-zero use) | exploration barriers | a specialist, or starts for that line |
| Per-kind movement split (PLAN_CEILING §14.2, instrument 2) | a kind moved only by drift | a retention scheme (rehearsal share or KL anchor) |
| Entropy per ask kind (priority and act) | a collapse to "always tap out" or "always pass" | read the kind's advantage; no entropy bonus by default |
| Searched minus raw, overall and per category | the policy lagging its own search (distil more) vs the value as the limit (memory, value training) | P3's pull up, or P1/P2 on the value |

## 6. Order and timing, beside the rest

The week's agent budget is the constraint: 55% of the weekly limit was used by 2026-11-18 09:45,
and it resets 2026-11-23. So the planning work this week is the coordinator's own CPU work.

| When | Self-play (GPU) | Cards and engine (agents) | Planning (this plan) |
|---|---|---|---|
| 2026-11-18 | r29: arm B ends ~10:20; the reads B1 and B2; decide.py resumes the main run | the engine faults (counters CR 122.2, the class-D audit, C1) and wave 5's mapping of the round-13 cards, running; zero fallback merged (213) | this plan; the puzzle format and runner (P0) |
| 11-19 | the main run toward B8 (update 300) | wave 5's blind verification and stamps; copy round B3 (Double Vision, Sublime Epiphany, Chandra's Regulator, Masterful Replication) | the first 16 puzzles, verified by playouts; r28 v2 and r29's snapshots read |
| ~11-20 | B8 read; the **FDN segment** registered and launched: FDN, the engine fixes, zero fallback, every public card, wave 5's cards | FDN's last verification batches; B3's gate review | O1 designed (a note with the engine's payment code read), memory v1's columns listed |
| 11-21 to 22 | the FDN segment | B6 (5 M20: Cerulean Drake, Gargos, Loaming Shaman, Scheming Symmetry, Vivien), then B4 and B12 (B4 first: they share the state-based actions; B12 has 6 M20: the Leylines, Grafdigger's Cage, Rule of Law) | O1 and memory v1 built behind flags, CPU-smoked and GPU-smoked with the real flags; the E-category puzzles |
| from 11-23 (budget reset) | **the planning A/B** (O1 + memory v1 against control, from the FDN segment's checkpoint), registered | the remaining M20 rounds, by M20 cards completed and 209 §6's file-conflict rules (B13 with I5's names fold, B14, B18, B8, B9, B15, B17 with I2, B11 with I6, B2, B7, B10, B16, B19) | P2's generator; puzzle starts as the next arm |
| then | P3's gate B (the reopening condition is a stalled rate, 196 §10, or the puzzles' B and D categories stalling) | rounds continue to M20's end | P3, then P4 |

**A change to the registered card order (coordinator, 2026-11-18).** 209 §9 put the folds next:
round 14 (I2 + I5 + I6) and round 15 (I3 + I4). They now ride with the rounds whose cards need them:
I5 with B13, I2 with B17, I6 with B11, and I3 + I4 before the FDN templates that print their
wordings.
- **Why:** the owner's order is to finish M20 and M21 first, and the folds complete no card. This
  week's agent budget fits about one round in flight.
- **The cost:** a few trees mapped before their fold are re-baked and re-verified later. The bulk
  re-verification measured about 3 agent-minutes a card (207 §4).

**What waits on what.**
- **E puzzles wait on memory v1, A-pay on O1.**
- **P2's starts wait on P0's generator and verifier.**
- **P3 reuses the search and labeller already built.**
- **M20's completion is the long pole.**
  - 43 cards wait on new components: 17 gate rounds at about 200-330 agent-minutes each
    (209 §6).
  - At this week's budget that is two to three weeks.
  - M21's last card (Conspicuous Snoop) waits on B19.
  - The rest of M21 completes with wave 5, C1 and B3.

## 7. References
- T. Anthony, Z. Tian, D. Barber. Thinking Fast and Slow with Deep Learning and Tree Search (expert iteration). NeurIPS 2017.
- I. Danihelka, A. Guez, J. Schrittwieser, D. Silver. Policy Improvement by Planning with Gumbel. ICLR 2022.
- J.-B. Grill et al. Monte-Carlo Tree Search as Regularized Policy Optimization. ICML 2020.
- P. Cowling, E. Powley, D. Whitehouse. Information Set Monte Carlo Tree Search. IEEE TCIAIG 2012.
- C. Florensa et al. Reverse Curriculum Generation for Reinforcement Learning. CoRL 2017.
- T. Salimans, R. Chen. Learning Montezuma's Revenge from a Single Demonstration. 2018.
- M. Jiang, E. Grefenstette, T. Rocktäschel. Prioritized Level Replay. ICML 2021.
- O. Vinyals et al. Grandmaster level in StarCraft II using multi-agent reinforcement learning (the league, PFSP). Nature 2019.
- A. Ng, D. Harada, S. Russell. Policy invariance under reward transformations (potential-based shaping). ICML 1999.
