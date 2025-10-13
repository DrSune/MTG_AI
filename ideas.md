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
