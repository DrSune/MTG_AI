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

**Settled with the owner, second round (2026-11-18; OWNER_VISION_LEARNING §12):**
- **Payment stays the engine's for now; O1 is dropped.** The owner: "making the network
  high-quality and mature is the priority, realism-of-play is a later learning point, and not our
  current bottleneck". The end state is the network paying for itself with no auto-pay option
  (BACKLOG "Automatic payment"). The deferral covers mana activation only. Every other choice the
  rules give a player stays the network's now (the owner, same day).
- **The plan module joins P1** (§5):
  - a carried plan that runs through the opponent's turn;
  - trained by hindsight and by the search's lines;
  - explored by committing to a sampled plan;
  - tested in two scopes: this action sequence, and one or two sequences ahead, revised at
    execution.
- **Repeated reasoning ("think again") and a game clock are BACKLOG.** They come before network
  size limits quality.
- **Puzzle answers are proven by exact solving wherever the puzzle is small enough** (§4). The
  owner's point: a ceiling cannot be measured with a model that is not good at the skill.
- **The order is the coordinator's**, for the best information first: P0 first.
- **Readable plus hidden plan slots** (the owner, third round). The owner: "We can have implicit
  knowledge like cards being kept in hand might be saved for later. If it is part of the planned
  sequence for next action sequence we can assume it is being held with some objective in mind."
  So "hold" is a verb of the readable plan (§5).
- **BACKLOG: the plan's horizon** (how many action sequences ahead). It is tested once the
  simplest case works. The owner's cases:
  - a combo deck balancing survival until the combo is assembled against an all-in before losing;
  - a sweeper kept for as long as the opponent keeps back, and used when they commit.
- **History** (§5, P1): what is certain is built, and the rest is measured first.
  - The turn so far is built (2026-11-18): per player, life gained and lost, their events, draws
    and casts.
  - What a player has legitimately seen in hidden zones is next.
  - Card ages, previous zones, summaries of the opponent's actions and an event encoder are
    measured before any is built.

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
| P1 | **Remove the representational limits**: memory v1 (explicit history features); the plan module (a carried plan through the round, trained by hindsight and later by the search's lines, explored by commitment) | adds information and a carried intention; the reward is unchanged |
| P2 | **Frequency nudges**: puzzle states as training starts (a reverse curriculum), replayed by their learning value; frozen specialists in the league | the reward stays ±1; only the starting positions and opponents change |
| P3 | **Planning as policy improvement**: search-improved training (expert iteration with Gumbel search over sampled worlds), PLAN_CEILING's F1 and gates A/B | value targets stay real results; the search's pull anneals |
| P4 | **The no-ceiling run** (PLAN_CEILING's H2): every nudge annealed to zero; outcome self-play with a league, exploiters and search at play time | nothing hand-made left in training; puzzles and L guard against regression |

**When** (§6). This week: the puzzle suite (CPU, mine), beside the card work and r29. At r29's
FDN segment: the zero-fallback fix and the engine fixes. Next week, after the budget reset:
memory v1 and the plan module as registered A/B arms (the plan in its two scopes), then the
curriculum arm, then P3's gates.

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
     That gap is planning the policy has not absorbed. It is a lower bound: it counts only what a
     one-turn lookahead over today's network finds. The same holds for every "headroom" read in 205.
     A skill neither the network nor its search plays cannot show up in it.
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
- **Payment stays the engine's for now (owner, 2026-11-18).** The first draft's O1 (outcome-level
  payment options) is dropped.
  - **The end state** (BACKLOG "Automatic payment"): the network activates its own mana abilities,
    one at a time as CR 601.2g has it, at any priority point too. There is no auto-pay option.
  - It covers what O1 could not: tap triggers (M20's Leyline of Abundance; Manabarbs), convoke,
    and spend restrictions.
  - **When:** when realism of play becomes the bottleneck, not before. The owner: network quality
    and maturity first.
- **O2, consequence previews (measure first, do not ship blind).** Each act row could carry what
  it leaves:
  - mana left after paying;
  - how many other rows stay affordable.

  That is a one-step lookahead read from the menu's own pricing. Built only if the puzzle suite
  shows within-turn sequencing failures that training does not fix. It is an input change,
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

**How a puzzle's answer is known (before it counts).** A ceiling cannot be measured with a
model that is not good at the skill (the owner, 2026-11-18). So the answer must not come from our
networks. Three grades, recorded with each puzzle:
1. **Proven.** The puzzle is small enough to solve exactly in our engine:
   - every line for both players is played (`tools/search/fork.py`, about 6 ms a fork, NUMBERS
     2026-10-10), as a chess endgame table is built;
   - the opponent's hidden cards are enumerated over `world_prior`;
   - our own choices are fixed per information set, so the solver never uses knowledge we lack
     (no strategy fusion).

   A first-wave puzzle has a few cards a side and a horizon of one or two turns: about 10^5 lines,
   minutes on one core.
2. **Dominant.** Too big to solve, but built so the right move is at least as good in every world
   of the prior and strictly better in one, each world solved as above.
3. **Model-verified.** The right line beats every alternative in forced-line playouts against the
   heuristic and the searched network (the labeller's machinery, horizon 0, as in `linevalue.py`).
   This is weaker evidence: a continuation that fails to follow through undervalues a deep line.
   The suite reports grade 3 separately and never counts it toward a gate.

**Twins.** Every puzzle has a counterfactual twin: the same board, one piece of evidence changed,
the right move changed. A network that holds Cancel by habit passes one twin and fails the other.
The headline number is the twin-consistent pass rate.

**Categories, first wave (16 puzzles, 8 twin pairs, M21/M20 verified cards).**

| Cat. | Skill | Example (one twin pair) |
|---|---|---|
| A | Within-turn sequencing | Draw first, then pick the land (an Opt-like draw before the land drop) / the land first when the draw cannot change it. Removal before combat to clear the blocker / after combat when the attack is safe either way |
| A-pay (later, with the network paying: BACKLOG) | Colours kept open | Pay the creature with Mountains so Cancel stays castable on their turn / with Islands when no counter is held |
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

**P1, remove the representational limits (build next; registered A/B arms at a run boundary).**
- **The plan module** (the owner's idea, settled 2026-11-18). A few plan slots ride in the input
  beside the board.
  - **What a decision does with them.** Every decision reads the slots and writes them anew: the
    plan is revised at every new event, a counter, a trigger or a draw.
  - **Scope, both tested:** (a) the current action sequence; (b) one or two sequences ahead,
    through the opponent's turn. Holding Cancel, or letting the opponent act more before the stack
    resolves, is a plan that spans their turn. Variant (b) is revised when it is executed, since the
    state can change a lot during the opponent's turn.
  - **What trains it:**
    - *hindsight*: the slots learn to predict what the seat actually did later in the plan's scope,
      so the plan becomes a commitment the policy follows;
    - *the search's best line* wherever the search ran (P3), so the plan becomes a cheap stand-in
      for the search, which also serves the match clock;
    - and, through the decisions that read it, the game's result.
  - **Exploration by commitment.** At a plan's first decision the plan is sampled, and the moves
    follow it. A whole line is tried consistently instead of one decision at a time: holding Cancel
    takes the right pass at many priority decisions, which are 42% of the learner's decisions and
    are passed 97% of the time.
  - **Readable heads (settled with the owner: hidden plus readable).** Each slot also states one
    intended action:
    - a verb from the closed vocabulary the network already chooses from: cast, activate, attack,
      block, target, pass or hold;
    - up to two pointers into the current decision's tokens (the card in hand, the creature on the
      board), the same pointer mechanism the policy uses for its options.

    No lookup table and no language model is needed:
    - printing a step is the engine's own label for that verb and those cards ("cast Shock:
      Grizzly Bears");
    - matching a planned step against what was executed, or against the search's line, is exact by
      verb and card handle;
    - what a step would resolve to is the engine's to compute, not the plan's to explain.

    An intended action on an object that does not exist yet, such as "counter their next big
    spell", points at what exists (Cancel in hand). The rest stays in the hidden part.
  - **Conditional intentions: "hold X until ..." (proposed; in discussion).** The owner's cases
    are a sweeper held while the opponent holds back and a combo held until it is complete. A hold
    step points at the held card. Two more readable heads say when and on what it will be used:
    - *time to use*: this sequence, the next, within two rounds, later, or never;
    - *the event before its use*: one of the engine's own event kinds (their cast, their attack, my
      turn's start), a closed vocabulary.

    Both are trained by hindsight from what actually happened to the card, so a plan reads, for
    example, "Planar Cleansing: hold; use within two rounds; after their creature casts". There
    is no hand-written condition grammar. The release itself is the policy's, which reads the
    plan and the board at every decision.
  - **Strategic modes and a plan critic (proposed; in discussion).** Survive versus go all-in is a
    choice between whole plans. A small learned "mode" token, sampled each round, is explored by
    commitment. A value read with the plan as input, V(state, plan), scores candidate plans. The
    learner can then compare "assemble and survive" with "all in now" without simulating, and the
    search refines it where it runs.
  - **The owner's per-card form (2026-11-18, fourth round; proposed to replace the slots).**
    - **What it is.** Every card the player could use carries its own intention instead of K plan
      slots: the hand, permanents with choices, and cards in other zones a permission reaches.
      - this sequence's actions as A1, A2, ..., each with its planned target, a pointer from the
        card's token;
      - "hold" with its time to use and the event before its use;
      - and so on.
    - **It feeds back.** The intention is written by a head on the card's own token at every
      decision. It is read back as a column of the card's token at the next decision, so the
      network knows what it meant to do with each card, as `C_CHOSEN` carries a chosen colour.
    - **Why it beats the slots:**
      - every card is covered and no slot count is set;
      - a held card always states it is held;
      - it costs one head and one input column per card token, not new tokens;
      - it reads as plan-level components.
    - **What stays from the slots:**
      - hindsight trains every label from the card's actual fate, and the search's line where it
        ran;
      - a card that changes zones starts a new intention (CR 400.7);
      - one global mode token covers what no single card owns (survive or all in).
    - **Open with the owner:**
      - the labels' vocabulary: observable buckets with a hidden vector, or named intents such as
        "play when the tempo is good";
      - which cards carry one;
      - whether exploration samples the labels or only the mode. Labels sampled card by card can
        clash, for example two A1s.
  - **Built in steps** (the owner: make the simplest case work, then test):
    - v1: this action sequence only; readable next actions; hindsight; commitment.
    - v2: one or two sequences ahead, revised at execution; hold steps with their two heads.
    - v3: modes and the plan critic.

    Each step is read on the puzzles: A and C for v1, B and D for v2, and the combo and sweeper
    puzzles for v3.
  - **Not in this step: repeated reasoning ("think again") and its game clock** (BACKLOG). The
    capacity probe (194) found a deeper or wider network fits r27's value no better, so more
    passes per decision wait until network size limits quality.
- **History, in two parts: what is certain is built, the rest is measured first.**
  - **Built (2026-11-18): the turn so far.** Per player: life gained and lost (damage included,
    CR 120.3a), the gain and loss events, cards drawn, spells cast (`features.P_GAINED` to
    `P_CAST`). These are the states the rules' turn-history atoms read: "the first time each turn",
    "if you gained life this turn". It joins at the FDN segment as an observation fix, with zero
    weights on load.
  - **Next, certain: what a player has legitimately seen in hidden zones** (`bench/view.py`'s known
    limit):
    - a revealed hand card, until it leaves the hand;
    - a card returned to a hand from a public zone;
    - a card an effect put at a known place in a library, until a shuffle;
    - one's own scried cards left on top.

    Counted by name, so a known Shock stops being known once a Shock leaves that hand.
  - **Measured first:**
    - each card's age in its zone and the zone it came from;
    - summaries of the opponent's actions: mana left open when passing, instant-speed casts, cards
      held for many turns, spells by type last turn;
    - an event encoder: tokens for the opponent's public actions since one's last turn.

    The instruments are three: the value-residual regression of KNOWLEDGE/2026-11-12/200 §1 (does
    a history feature explain the value's error?), the E puzzles, and the tokens each feature
    costs a decision.
  - **The owner's call:** whether the ages of the opponent's unknown hand cards are fair. In paper
    play a hand can be reordered, so they are not knowable; some digital clients show draw order
    (OWNER_VISION_LEARNING §4).
- **Memory v1's explicit features**, cheapest first, as OWNER_VISION_LEARNING §3 and §4 order
  them:
  - the opponent's untapped mana at each of their last two end steps and passes;
  - spells cast this game by type;
  - cards they revealed and that have not left their hand since (the engine records reveals as
    events, `verbs.py:1642`);
  - cards an effect put somewhere known (the top or bottom of a library) until a shuffle.

  Card-level facts go in zero-initialised columns, so an older network computes what it did.
- **Memory v2** comes later: an encoder over the event journal (attention over recent events), to
  share with the opponent simulator. It goes in only if E-category puzzles still fail with v1.
- **Gate.** Each arm raises the twin-consistent pass rates of the categories it targets above
  the control's (memory v1: E; the plan module: B and D), and holds or beats the control on L (no
  regression).

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
| ~11-20 | B8 read; the **FDN segment** registered and launched: FDN, the engine fixes, zero fallback, every public card, wave 5's cards | FDN's last verification batches; B3's gate review | the exact solver and the first proven puzzles; memory v1's columns listed; the plan module's design note (slots, both scopes, the hindsight target) |
| 11-21 to 22 | the FDN segment | B6 (5 M20: Cerulean Drake, Gargos, Loaming Shaman, Scheming Symmetry, Vivien), then B4 and B12 (B4 first: they share the state-based actions; B12 has 6 M20: the Leylines, Grafdigger's Cage, Rule of Law) | memory v1 and the plan module built behind flags, CPU-smoked and GPU-smoked with the real flags; the E-category puzzles |
| from 11-23 (budget reset) | **the planning A/B arms** (memory v1; the plan module in its two scopes; against control, from the FDN segment's checkpoint), registered | the remaining M20 rounds, by M20 cards completed and 209 §6's file-conflict rules (B13 with I5's names fold, B14, B18, B8, B9, B15, B17 with I2, B11 with I6, B2, B7, B10, B16, B19) | P2's generator; puzzle starts as the next arm |
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
- **E puzzles wait on memory v1; A-pay waits on the network paying (BACKLOG).**
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
