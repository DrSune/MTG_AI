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

