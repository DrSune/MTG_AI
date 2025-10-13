Consider optimizer for finding 'sharp' minima, that will correspond to niche decks. These decks are niche because very few changes to the deck completely ruins the decks performance, as seen in the sharp rise of loss when moving slightly in any direction
Find a way to not 'forget' niche decks, they should be used in the experience buffer, but eventually there will be too many niche decks and normal decks to represent them all in this buffer
It is important for niche deck performance to revisit these and re-evaluate whether they are still viable, better or worse than when it was first tested. This in principle also goes for common decks, however they will more naturally be represented as they look more like eachother than niche decks (I think)

Use mutation (evolutionary strageties), under-confidence sampling, novelty reward

Elite Pool/Experience Buffer of Niche decks?
Advesarial training (vs an opponent constantly adapting to beat your deck)
Test robusteness of deck (train with same deck with 1 or few cards change, and include results in reward/winrate)

R_final =R(D)+λ⋅Robustness(D) - Annealing of robustness. High λ punishes sharp minima/niche decks (good in the beginning), lower later to find niche decks. Can potentially be modified depending on what the model should attempt to improve at?


How do we avoid that the model predicts the opponent to have the worst case possible deck, and that we then play against that strategy, in scenarios where playing optimally against the hardest possible opponent-state combination results in exposing us to some of the also likely, but less consequential oppontent-state combinations?
Is this learned implicitly in win-rate and rewards, or do we need to handle that we dont expose us to scenario 2,3,4 by playing optimally aginst scenario 1, if they are all somewhat equally likely?



That is an excellent and highly insightful question. You have hit on the fundamental challenge of applying AlphaZero's MCTS (designed for Perfect Information games like Chess and Go) to Imperfect Information (II) games like card games.

The core principle you mentioned is correct: in a card game, the MCTS simulation cannot know the opponent's cards in the same way it knows the position of a chess piece.

The AI solutions for card games combine MCTS with techniques to handle the hidden information. The most common and successful approach is Information Set Monte Carlo Tree Search (ISMCTS), which works by using a concept called Determinization

Separate NN to predict opponent hand and deck and strategy (dont predict discrete strategies, use RGB approach maybe)?
Assume/predict enemy hand and deck, play with this simulated perfect information game, model will be punished by wrong predictions as it can lead to poor strategies
By performing hundreds or thousands of simulations, each with a different sampled/weighted determinization, the MCTS averages out the uncertainty, converging on a policy that is robust across all likely opponent hands.

Simulating the Opponent (Player 2)
During the MCTS simulation on a chosen determinization (where all cards are temporarily visible):

Player 1's Turn (Maximizer): Player 1 chooses the move that maximizes the MCTS's UCT score, guided by the network's policy P.

Player 2's Turn (Minimizer): Player 2 is simulated using the exact same MCTS logic and neural network, but from their canonical perspective (i.e., they are trying to maximize their value, which is maximizing the negative of Player 1's value).

Crucially, the opponent's neural network evaluation f θ(s ′) still only sees the canonical board state s ′ (the board from their perspective + the public history), which is consistent with the current determinization in the simulation.

What if they play a card we didn't expect?
Your final question—"what we do if they then play a card we didnt expect them to posess"—is the entire mechanism of the AI's adaptation:

The Real Game: The opponent plays a real card, a real .

Belief Update: This real action discards all previous determinizations that made that action impossible. For example, if your belief system thought the opponent had a 90% chance of not having the Ace of Spades, and they play it, that 90% is now impossible. Your belief model for their remaining hand and deck is immediately and dramatically updated.

MCTS Reset: The MCTS search tree is largely discarded. When the game moves to the new state, the AI starts a new MCTS search from that new root node, incorporating the new, real information (the Ace of Spades is now public) into the next set of determinizations.

This continuous process of observing a real action, updating the belief, and re-searching based on that new information is how AI agents deal with imperfect information in a dynamic environment.
