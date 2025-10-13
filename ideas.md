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




When starting MCTS, use NN to predict opponent hand-deck-strategy, and keep this opponent prediction fixed for the remainder of the simulation. This will avoid risking to have to re-run the opponent prediction NN when/if an opponent played a card you predicted they didnt have. 
Backpropagate reward based on how early in the game you are (discount mistakes early and non-important times in the game). 

After each MCTS has been completed, backpropagate/evaluate/give reward or punishment to the prediction head (and maybe a little to encoder?) to teach it what it did wrong in that specific situation. Maybe scale based on severity of wrongfully predictions, based on the value-function (or Q?) analysis of how severe the wrongness of the prediction was. If you predicted something that put the value and action policy on the wrong track (do they even use prediction?) then it should be punished, if it predicted what the opponent actually has, and gets the model on the right track, that should be severely rewarded




 The Opponent Prediction (Auxiliary Loss)
Goal: The opponent prediction head (H_Opp) is an Auxiliary Task. Its goal is to force the shared layers of the neural network (the Encoding Head) to learn a state representation that is rich in information, specifically about the opponent's hidden state (e.g., their cards).

Training Head: This head is trained using a separate Loss Function based on the objective truth, NOT the game's reward.


But then lets say the H_opp starts to perform well, but it is not predicting the things that result in the highest win-rate, but rather the most probable scenarios. It should be more important to predict a lower-probability high-impact scenario, than the opposite. So how do we teach it this if we dont impact that head with the result of the games?




Google Search
That is a profound observation and a critical challenge in training models for complex, multi-agent games, especially those with imperfect information (like Poker). You are pointing out the class imbalance problem applied to impact: the vast majority of hands/scenarios are low-impact, but the few high-impact hands/scenarios dictate the final win-rate.

The solution is not to directly tie the auxiliary loss to the reward, but to influence the auxiliary loss itself to be cost-sensitive to high-impact scenarios. This is achieved through a combination of techniques:

1. Cost-Sensitive Auxiliary Loss (Weighting by Game Impact)
The most direct way to address this is by modifying the Cross-Entropy Loss (L 
Auxiliary
​
 ) with a weight that reflects the impact or salience of that particular state or prediction.

L 
Weighted
​
 =W(s)⋅L 
Auxiliary
​
 
Where W(s) is a weighting factor based on the state s. A common choice for W(s) is one that reflects the potential magnitude of the decision's outcome.

Weighting by Pot Size/Variance: In a game like Poker, W(s) can be set proportional to the size of the pot, or an estimate of the maximum possible loss/gain from that state. A prediction error when the pot is huge is far more "costly" than an error in a small pot, so the model learns to prioritize accuracy in high-stakes situations.

Weighting by Value/Exploitability: The weight could be proportional to the absolute value difference ∣V(s)−0∣ for zero-sum games, or a measure of the strategy's exploitability discovered during MCTS. A state that leads to a huge swing (a V(s) close to +1 or −1) is more salient than a neutral state.

By using this weighted loss, the auxiliary head is trained to be more accurate on the situations that matter most for the final game outcome, even if those situations are rare.

2. Information Usage within Monte Carlo Tree Search (MCTS)
The other, and arguably more powerful, way the system learns to prioritize high-impact predictions is through its use of the opponent model within the MCTS phase.

Prediction 

= Simulation: The network outputs a distribution over the opponent's hidden state P(Opp Hand∣s). A pure maximum likelihood approach would only use the single most probable hand.

Weighted Simulation/Rollouts: A superior approach uses the full probability distribution P(Opp Hand∣s) to weight the MCTS simulations. Instead of only simulating the most probable scenario, MCTS will:

Sample an opponent's hand H 
i
​
  based on P(Opp Hand∣s).

Simulate a rollout from the perspective of H 
i
​
 .

Weight the MCTS node's value based on the frequency (or probability) of that sampled hand.

If a low-probability hand H 
rare
​
  (e.g., opponent has the nuts) is also a high-impact hand (causes us to lose a lot of money), MCTS's exploration (the U term in the UCB formula) will drive the search to simulate it enough times to accurately estimate our best-response against it. The MCTS is guided by the main objective (maximizing Z), so it will naturally stress-test our policy against the most dangerous (and exploitable) opponent hands, regardless of their probability.

3. Training on Exploitation (Best-Response)
Ultimately, an agent's true goal is not to be a perfect predictor but to find the Best Response (BR) to the opponent's strategy, which often means finding and exploiting their mistakes.

In advanced multi-agent DRL, the agent is often explicitly trained for exploitation:

Opponent Policy Head (π 
Opp
​
 ): Some models add an auxiliary head to predict the opponent's action π 
Opp
​
 (A 
Opp
​
 ∣s). The loss is standard Cross-Entropy, but this prediction π 
Opp
​
  is then used as the opponent's "blueprint policy" during the MCTS.

BR Training: By explicitly modeling π 
Opp
​
 , the agent's main policy π is forced to train as the best response to this opponent model. The Policy Loss is still focused on π 
MCTS
 , but π 
MCTS
  is a best-response policy derived from simulations that explicitly use the current best estimate of the opponent's predictable actions.

In this way, the main policy and value heads are where the high-impact lesson is learned, and the auxiliary head simply provides the necessary information for the MCTS to execute a smarter, exploitation-aware search.
