# How the network should learn, and where it is going (the owner's vision)

Recorded 2026-11-06 from the owner's own words; Claude's technical notes are marked **Note**.
Read this before changing how the network is trained, what it sees, or how games are chosen.
Binding principles are in `KNOWLEDGE/OWNER_PREFERENCES.md` (#1 no hidden information in play,
#6 full credit). Open questions are listed in each section.

## 1. Full credit for every decision: gamma = 1 and lambda = 1

Owner: Magic is enormously complex and long-horizon: a huge state and action space, many decisions
per game, consequences that land many turns later. Every decision must be credited with the game's
final result, or the representation of these phenomena "will vanish and get watered down to nothing
meaningful in terms of gradients". So the only reward is winning (+1) or losing (-1), gamma and
lambda are both 1.0 so the full result reaches every decision, and the network plays very many games
so that each lesson is hammered home. Larger batches per update are welcome: more decisions per
gradient step means each step carries signal, and the machine's RAM should buy update quality as long
as the GPU stays busy.

The value network belongs in this picture. Every state of the game is saved and used: a board the
value network called good that was lost five turns later is corrected. A new card whose components
the network does not yet understand is punished on average through what happens around it: the
synergies it did not see coming, the counterplay it did not expect.

**Note.** With gamma = lambda = 1, GAE reduces to the Monte-Carlo advantage `z - V(s_t)`: the full
result minus what the value network expected at that moment. The subtraction removes no credit; it
removes only what was already predictable, so a decision is not rewarded for a position it did not
create. Lambda below 1 replaces most of the result with the value network's own guesses: at 0.95 a
decision 60 moves from the end takes ~5% of its credit from the result itself, and early in a game
the value network explains only ~3% of who wins (KNOWLEDGE 2026-11-05/184 §25). The owner's word for
this was "full rollout BPTT"; the standard term is Monte-Carlo credit. BPTT (backpropagation through
time) is training a network with memory, which is section 3.

**How it is realised (DECISIONS D20, 2026-11-06).** Outcome-only credit measured too noisy to learn
from on this machine (~2.2M decisions per useful step; lambda = 1 alone even noisier). So each
compared decision is played out to the end of the game (gamma = lambda = 1) against its alternatives
on identical sampled futures: luck cancels in the comparison but stays in the problem the policy
solves. Futures come from the player's beliefs, never the true hidden state.

## 2. Generalise through components; never memorise

Owner: the network learns what card components do and how they relate to the board and to other
cards. Memorising anything more specific than components would need an impossibly large model.
Memorisation must be avoided, including through how decks are dealt.

**Note.** Status 2026-11-06: every training game deals fresh decks from its own seed (no fixed deck
list). Card names are visible 90% of the time, and the network reads whether a targeted effect helps
or hurts mostly from names (184 §16), so more name masking is planned.

## 3. Memory across decisions (open)

Owner: should the network know what it decided earlier? A carried-over representation of what it
fears, expects and plans may matter, because an early move can point at a danger much later, when
the danger is no longer visible on the board. Or the value function and the board encoding may learn
this anyway.

**Note.** The network has no memory today: each decision reads only the current state. In a game with
hidden cards the history itself is evidence (what the opponent held mana up for, declined to block,
drew and kept), so strong play depends on it. Options, cheapest first: explicit history features; an
encoder over the game's event history (attention over the journal, or a recurrent state trained
through time, which is real BPTT). This overlaps with section 5: the opponent simulator is a learned
function of the same history.

## 4. What each player may know: the inputs

Owner: the networks need the action history, your own hand, what is in your own deck (but not where,
since you cannot know), and the location of any card, yours or the opponent's, that an effect put
somewhere known (on top, on the bottom). A shuffle erases that knowledge. How long a drawn card has
been in hand matters for reading the opponent.

**Note.** OWNER_PREFERENCES #1 holds throughout: play never reads a hidden zone. Open question: the
rules let a player arrange their hand in any order, so in tournament paper Magic the age of a
specific card in the opponent's hand is not public; some digital clients show cards in draw order.
The fair target decides whether that feature exists.

## 5. The opponent simulator (a belief model)

Owner: guess the opponent's hand and deck from their history of actions against your board: when
they played things, whether they played a newly drawn card at once, and similar tells. Weigh how
likely each card is against how severe its consequences would be. For each hidden card, predict a
vector in the card-encoding space and take the nearest real card; done incrementally, it could
simulate the opponent's whole deck every turn. Play can then proceed on simulated perfect
information, which is legitimate in competitive play because it uses only what a player can see.

Pre-game mode: given a deck or a matchup, "which cards would hurt this deck most". That is a
counter-this-deck engine that can help the Teacher draft, or draft by itself (auto-completing decks).

Open questions: how often to update it (every decision, every turn); how to train it; whether the
policy reads its output or only the search uses it.

Owner refinements (2026-11-06):
- **Nothing hardcoded about opponents.** Learn the simulator by standard supervised learning from
  finished games; it learns land ratios, colours and everything else from the data. No hand-built
  prior of what an opponent's deck looks like.
- **Both accuracy and consequence.** 99.9% accuracy on the opponent's cards is very useful, but if
  the 0.1% is a devastating card that loses the game, that is a very big punishment. The most useful
  simulation combines what the opponent actually had with what you needed to play around to win.
- **Several candidates, not one.** Knowing the top 3-5 candidates tells you what to play around.
  If the counterplay to candidates 2 and 3 is (almost) the same, playing around both (30% + 25% = 55%
  of the consequence) can beat playing around the single most punishing card (45%). The same holds
  for combinations of cards.
- **Start with the foreseeable future:** the opponent's hand plus the next 3-5 cards of their library.

**Note.** These fit together without biasing the probabilities: the simulator predicts honest,
calibrated probabilities of whole hands (sampled jointly, so combinations are represented), plus
the remaining library's contents (its top cards are then random draws from them, since nobody
knows the order). The search makes sure rare devastating cards are seen by sampling futures in
proportion to likelihood x consequence (importance sampling), then weighting each result by
likelihood / sampling-probability, so the estimate of the win probability stays exact. That plays
around a 0.1% disaster exactly as much as it costs, neither ignoring it nor fearing it. The
consequence of a candidate card can itself be learned from the playouts (how much its presence
changed the result). Averaging each move over the sampled hands is what finds the 55% play: the
move that does best across all likely hands wins, not the one that answers the single worst card.

**Note.** It can be trained by supervision: when a game ends, the opponent's hidden cards become the
labels for every earlier moment, while at play time it reads public information only. That is far
more signal per game than the win/loss reward. The decision-time search re-samples hidden zones today
(uniformly from public information); it would sample from these beliefs instead. Sample several
hypotheses weighted by likelihood rather than only the nearest card, and treat severity as a separate
risk term. Related work: opponent modelling, belief states (ReBeL's public belief states),
information-set search.

## 6. The Teacher: scenario designer and drafter

Owner: training on random scenarios will not be efficient in the long run. A Teacher chooses what the
Student plays: decks and matchups that teach what the Student is weak at, niche decks and meta decks,
which frozen version it faces, and deliberate unfair advantages (a stronger deal for the frozen copy),
balanced against both players' strength to maximise learning. It could also train specialists for
niche decks to play against. Train the Teacher by the Student's learning; fine-tune it as a drafter
to maximise win rate against given decks, or against any opponent within a format (sets, cards,
modes). Perhaps the Teacher is the opponent simulator's pre-game mode (section 5): build the deck
that does best when you cannot choose the order you draw it in. The project may not be mature enough
yet; on the long horizon it is likely the right move, and it teaches deck-building too.

**Note.** Established forms: automatic curriculum learning and environment design (Prioritized Level
Replay, PAIRED, ACCEL). A cheap first step before a Teacher network: replay the deals the Student
learns most from, for example those with the largest value error.

## 7. Deals and matchups

A deal is one game's random setup: both decks and both library orders, fixed by the game's seed. The
owner: seeds can control matchups (decks, draws, opening hands) and can force specific lessons. Play
one matchup many times (~1,000 games, both sides); if learning works, the later win rate beats the
earlier one.

**Note.** Duplicate pairs (the same deal with the seats swapped) cancel the deal's luck. Matchup
blocks (the same decks with fresh shuffles) let the Student learn a matchup and are a direct test that
learning works. Guard against memorising the block by measuring on matchups it has not played.

## 8. Order of work (2026-11-06)

Superseded in detail by docs/PLAN_LEARNING.md (owner-approved); kept as the first sketch.

1. Signal: gamma = lambda = 1; duplicate deals; at least B* decisions per optimizer step (the audit
   is measuring B*); the KL-stop fix (b03c3ac).
2. Learning test: the Student must beat a fixed opponent, or learn a matchup over a block.
3. Inputs: knowledge tracking (section 4), history (section 3), more name masking.
4. The opponent simulator (section 5); then exploration and a league; then the Teacher (section 6).

## 9. Raise the baseline first (2026-11-11, open)

The owner: "Even if the end-goal is the VERY data hungry full BPTT rollouts with gamma and lambda
1.0, it might make sense to use less data hungry models earlier, to raise baseline, so we can train
the final network against better opponents from the beginning. I am unsure whether this destroys the
effect of exploration-heavy starting for better end results (which is only relevant anyways once we
have proved our model is really good and far from its cieling)." And: "How much does it matter
whether we do exploration from the beginning, or only after it learns some basic skills, in terms of
cieling and playing above-human level?"

What the field reports (checked 2026-11-11):
- AlphaGo Zero (Silver et al., Nature 2017): a network trained on human games "achieved better
  initial performance", but the self-play player, learning by tree search from scratch, "performed
  much better overall, defeating the human-trained player within the first 24 hours". The compared
  player was supervised only, not supervised then reinforced, and the from-scratch learner improved
  its policy by search (4.9 million games, 1,600 simulations a move), not by outcome gradients alone.
- AlphaStar (Vinyals et al., Nature 2019) started from imitation because the action space left
  "almost no chance" otherwise, kept human strategies in play during training against forgetting,
  and needed a league of exploiters against strategy cycles.
- Kickstarting (Schmitt et al. 2018): a student pulled toward teachers by a weight that fades
  matched a from-scratch agent in about 10x fewer steps and finished 42% higher; it can surpass its
  teachers. Reincarnating RL (Agarwal et al. 2022) argues for reusing prior policies over tabula rasa.
- What early training can cost: deep RL agents overfit their early data and lose the ability to
  learn later (primacy bias, Nikishin et al. 2022; loss of plasticity, Dohare et al., Nature 2024);
  a fine-tuned pretrained policy forgets what it did well in states it stops visiting (Wolczyk et al.
  2024). Remedies: partial resets, plasticity-keeping updates, a retention term toward the start.
- KataGo (Wu 2019): about 50x less compute than earlier AlphaZero-style runs, partly from
  auxiliary prediction targets that densify the learning signal without changing the reward.
- Imperfect information: DeepNash (Stratego, 2022) reached expert level from scratch with
  regularised self-play dynamics; in card games, RL agents lead Legends of Code and Magic, and no
  superhuman Magic agent is reported.

## 10. Search-improved training (2026-11-11, open)

The owner, on training with search before the gamma = lambda = 1 learner: "Search-iimproved
training sounds good, especially for improving value function and opponent simulator. Why does it
plan as if I know later cards? I actually see it, but is it even bad? It will train opponent
simulator and value function really hard. If it gets good, it will play well around opponents
deck. Only challenge is whether enemy deck is coherent, or completely random. For that we need the
drafting network to work well, or steal decks that are human-made from the web." And: "For n, we
should test the trendline of how well it performs at different. Save all of the search options so
we can revisit later as well." And: "We should utilize the massive RAM for the replay buffer in
search training phase."

Notes (2026-11-11):
- Sampling the hidden cards and searching each sample as if all were visible has two known flaws.
  Strategy fusion: inside one sample the search's later choices know that sample's cards, so a
  line that needs a guess later is valued as if the guess were free. And sampling hands without
  what the opponent's play revealed; the opponent simulator (section 5) fixes that one. Strategy
  fusion matters when playing around tricks and counters, when gathering information (Opt before
  choosing: each sample already knows the top card) and when bluffing. Today's search and
  labeller play each sample out with the network on both seats, each seeing only its own view,
  which has no strategy fusion; a tree built inside each sample has it, and Information Set MCTS
  (one tree over all the samples) avoids it.
- Value targets that are real game results are unbiased whatever the search does.
- The opponent simulator learns the decks it meets. The "coherent" decks are two colours with an
  even land split and a uniform sample of the pool in those colours (`games.build_coherent_deck`):
  coherent in colour, random in everything else. Human decks: 17lands publishes per-game data of
  Arena drafts with each deck under CC BY 4.0, but only from Kaldheim (2021) on, not for M20 or
  M21 (checked 2026-11-12, PLAN_CEILING §5.5); the drafter of section 6 is the long-term source.
- The strength-against-n curve is measured, and every search setting stays selectable with its
  measured results recorded, so any setting can be revisited.
- The replay buffer of the search phase lives in RAM (121 GiB on this box, shared with the GPU).


## 11. Fast opponents, the ceiling read, then the ceiling-striving run (2026-11-11, open)

The owner, after §10's answers: "It sounds good with the sampling and searching. As little as
possible unrealistic knowledge integrated, opponent simulator can be trained for every
branching/deeper level of the search, making it really good at predicting the cards we care about
(consequence * proability). Go ahead with a plan that goes along with this, and utilizes lower
cieling but faster improvement models to get our high-cieling model up to speed fast by playing
difficult opponents. That will help assess the cieling, after which we can do the cieling-striving
training run that is explorative self-play from the beginning."

The plan that follows this, with its gates and the owner's decisions: `docs/PLAN_CEILING.md`
(draft 2026-11-11). Notes:
- The simulator's probabilities stay calibrated; consequence decides where it spends capacity (the
  positions whose decision depends on the hidden cards) and which futures the search samples
  (importance sampling, weighted back exactly). Weighting each card's loss by its danger would make
  the search fear rare cards more than they cost.
- "Every level of the search" is made honest with truth lines: in training games the explored lines
  are replayed on the true state for the simulator's labels only, never for a decision.
- The fast models are the searcher (a frozen network plus search at play time, no training needed)
  and, through two gates, a network trained by its search (expert iteration). Their ceiling is lower
  because their targets inherit the value network's and the simulator's errors and settle on fixed
  answers; outcome PPO has neither bias.
- The owner, on the draft: "shouldnt we train the F1 and F0 models to some high ELO? Like 1000 ELO
  and then start training? If we just play it like it is but plus search, is that really good
  enough to test what we want to find out?" Agreed: today's network plus search is about one gate
  stronger (+30-40 Elo), too close to test the learner's ceiling. F1 trains first, as high as it
  climbs (a ladder of checkpoints every ~50 Elo), and the learner meets it only once F1 is at least
  +200 Elo above the learner's start (PLAN_CEILING §6.4). On this project's scale (random 0, the
  heuristic ~300, today's best ~450-465 on the old game), 1000 would win about 96% against today's
  best: the direction, not a gate.
- The owner, approving the plan: "If we train the search, opponent predictor and value function, in
  a more fast/compute efficient way, but lower cieling, then that might improve more, faster. If
  lowering gamma and lambda doesnt help with this at all, I guess it doesnt make sense. We just
  need them to improve. Making the drafter, and training that for maximizing learning, would also be
  really great (learning is probably winrate agains frozen opponents from a very varied pool,
  weighted based on ELO). You get the main point, go ahead" (DECISIONS D22). Notes: for the
  learner, lambda 0.95 bought only 2.2M against 2.65M decisions per useful update (D20), so it keeps
  gamma = lambda = 1. F1 may use faster value targets (auxiliary short-term search values, or a
  result-and-search mix) where they measure faster (PLAN_CEILING §6.3). The learning score is the
  learner's Elo against a very varied frozen pool: an Elo fit weights a win by the opponent's
  strength. The Teacher picks deck families by measured progress, and the drafter is trained for it
  later (PLAN_CEILING §9).


## 12. The network pays its own mana, and plans its turn (2026-11-18, open)

The owner, on PLAN_PLANNING's first draft: "the model should handle land-tapping at some point too.
I am sure some cards interact like 'when a/your/opponent land is tapped...'. If not in these sets,
then in others. We cant just ignore those/their functionality." And: "It must make a full plan for
the turn, and possibly revise/critique it before moving on, no? Having it attend between its
finalized plan and everything on the board seems smart. I am thinking something like a plan-input
and a reasoning-turn-counter. The plan is empty at the start of a turn, and the reasoning-turn-counter
is zero. When reasoning turn counter increments to one, is when the model thinks once more, now with
its plan as input too, as part of the 'board'. I think this could use the weights better/increase
information density. And then give it some option to reason again, revise plan, or execute plan."
"Dont rush to conclusions, spar with me and make sure we get the best plans before we start any
meaningful work."

**Notes (in discussion; nothing built).**
- **Paying.**
  - Cards that care which source pays exist in our own sets. M20's Leyline of Abundance: "Whenever
    you tap a creature for mana, add an additional {G}"; it waits on round B12.
  - The ingested sets hold more:
    - 11 printings that trigger on a permanent tapped for mana: Manabarbs, Overgrowth, Verdant
      Haven, Wolfwillow Haven, Nyxbloom Ancient, Burning Earth, Glittering Frost;
    - 22 convoke cards in M15, where paying taps your own creatures, which then cannot block;
    - 27 mana-spend restrictions.
  - Commander is full of them. The engine's payer (BACKLOG "Automatic payment") picks the sources
    by a fixed rule, so these choices are not the network's. PLAN_PLANNING §3's O1 (outcome-level
    options for which colours stay open) does not cover them.
- **Plans.**
  - The network carries nothing from one decision to the next. AlphaStar and OpenAI Five carry an
    LSTM state, where their intentions live, so the comparison drawn in PLAN_PLANNING §2 holds for
    what a sequence of choices can express, not for deliberation or commitment.
  - D3's binding "multi-step planning with every step trained" (2026-09-10) is not in today's
    network. DESIGN_ACTION_SPACE's decoder was never built.

**The owner's answers (2026-11-18, second round).**
- **Payment.** The owner: "I dont like 'auto-pay' that much, so mark it as backlog fix item, because
  I think it is right now, but at a later point we want the network to actually know how to use
  lands too. For now making the network high-quality and mature is the priority, realism-of-play is
  a later learning point, and not our current bottleneck." The engine keeps paying, and the
  network's own payment is BACKLOG ("Automatic payment").
- **Plans.**
  - The plan runs through the opponent's turn (saving Cancel for the instant round, or letting the
    opponent act more before the stack resolves). Both scopes are tested: "this action sequence
    just now, or ... one or two action sequences in the future, but revise them when you actually
    need to execute since state can have changed significantly during opponents turn".
  - The owner agrees "very very much" with what trains the plan: hindsight, and the search's lines.
- **"Think again".** Repeated reasoning paid by a game clock goes to the BACKLOG, "before we are
  limited on quality from network-size".
- **Measurement.** The owner: "Not sure how you are sure the cieling reading works at all. I can
  see how we can use theory for it, cant see how we can measure it without a good model at doing
  it." Agreed. Every headroom read so far (205) is a lower bound: what a one-turn lookahead over
  today's network finds. Puzzle answers are therefore proven by exact solving in our engine where
  the puzzle is small enough, and model-verified puzzles are reported apart (PLAN_PLANNING §4).
- **Order.** Left to the coordinator: P0 first, as the best information.
- **Scope of "later"** (the owner, third round): "realism-of-play later only counts for mana
  activation". Every other choice stays the network's now.
- **Readable plans.** The owner: they are "only possible if we use a large look-up table to match
  actions together properly, or a LLM to explain what the actions would actually resolve to".
  Answered in PLAN_PLANNING §5: a readable step is a verb from the network's own option vocabulary
  plus pointers to cards that exist now. The engine labels it and matching is exact by card
  handle; steps about objects that do not exist yet stay hidden.

**The owner's answers (2026-11-18, third round).**
- **Both, hidden plus readable.** "We can have implicit knowledge like cards being kept in hand
  might be saved for later. If it is part of the planned sequence for next action sequence we can
  assume it is being held with some objective in mind."
- **The horizon goes to the BACKLOG**: "Maybe it should plan next two, not just next one. Maybe even
  more, I dont know what is optimal". The owner's cases are combo decks ("balance just surviving
  until it has the full combo, or good conditions to execute it with draws, or it just needs to send
  all in before losing soon") and a held sweeper ("As long as they keep it, you should keep your
  card, but it should be the plan to use it when they commit/if they do"). "Not sure how to encode
  this in the plan implementation best possible. Spar with me here."
- **History.** On "history, planner functionality, history encoder (of opponents actions, since
  board history is visible with cards, and how long they have been somewhere, and possibly where
  they were before, though this is a lot of things to attend to, and not sure all of it matters)":
  "Work what you are sure of how to implement for this account. When unsure, dont rush to
  conclusions, spar with me to find the optimal path forward."

**The owner, fourth round (2026-11-18).**
- **The per-card plan.** "What do you think of a plan implementation where it needs to have a plan
  for every single one of it cards? So other than having an action sequence, it plans the other cards
  too. It can assign them 'hold for X', 'play when tempo is good' or something similar ... These
  labels could be part of the card input/encoding for next turn, so it knows what it thought to do
  with the card last turn. This might be more straightforward AND more useful to be honest. And
  action cards can get A1, A2... labels. And then the explicit action sequence with planned targets
  etc can also be a thing."
- **Component understanding at the plan level.** "It is component understanding/encoding, just at
  the planning level instead of the playing level, meaning components are different/more ones."
- **Recorded in** PLAN_PLANNING §5 as the proposed replacement of the plan slots.

**The owner, fifth round (2026-11-18).**
- **Search.** "We should consider improving search to work multi-turn along with the planner
  (similar to what you suggested). This will make both better I think."
- **The first and third answers.** "Probably your recommendation, but check that the logic is
  sound and in line with our project goals before moving forward." And: "We can do your
  recommendation, again check the logic."
- **Which objects.** "Everything that can be made a choice with, that is also visible, should be
  planned with. Cards to be drawn can thus not be planned with, unless we know what card we are
  going to draw (complex mechanics to code together). Token creatures spawned can attack, so they
  can technically be planned with."
- **The sets, then the components.** "Continue finishing the sets yes, when all cards in both sets
  are finished, you should look at the new additions and whether we have any redundant components
  we could break down into our existing ones to optimize that from the start."
- **The logic check** is DESIGN_PLANNER §3. Three problems in the first proposal are fixed:
  plan-following by hindsight relabelling, round styles as hindsight labels, labels as forecasts.
