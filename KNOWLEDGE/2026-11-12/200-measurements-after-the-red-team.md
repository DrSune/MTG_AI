# 200 — Two measurements the red team asked for: the own decklist, and skill headroom per card

**Context.** PLAN_CEILING §14-§15 (the plan revised after a red team, 2026-11-12 evening). Both
are CPU measurements on data already on disk, made before any design leans on them.

## 1. Does the network's own decklist carry outcome information its value lacks? No, for coherent decks

**The question** (the red team's M6).
- The features give the library's size only (`features.py:668`). A player knows their own
  decklist, so its contents would be a legitimate input.
- 184 §26 found that deal features predict 24% of single-game outcome variance, against the value
  head's 5% early in a game. But those features included both opening hands and the next draws,
  which are hidden information.

**The measurement** (`reports/info_lever_2026-11-12/own_deck.py`).
- **Data:** window 2's collect (v0 under r27's flags, 19,173 games). The decks were rebuilt at
  the collect's commit (98a48e9).
- **At the learner's first decision of each game:** the value v and the result z.
- **The regression:** the residual z - v on deck features: the counts of lands and creatures,
  spells by mana value 0 to 6+, spells per colour, the mean spell mana value, the critic's
  card-value sum, the seat and the set. Ridge, 5 folds over games.

| Features | Cross-validated R² of the residual | Of the result, with the value as a feature |
|---|---|---|
| The value alone | — | +0.0329 |
| Own deck (legitimate) | **−0.0010** | +0.0319 |
| Both decks (an upper bound: includes the opponent's hidden deck) | −0.0013 | +0.0317 |

**Reading.**
- At the first decision the value explains 3.3% of the result (184: 3%).
- What the decks contain adds nothing, even the opponent's. 184's 24% came from the hidden order
  of the draws and the opponent's hand.
- Two-colour coherent decks vary too little in composition to matter, and the opening hand
  already shows the deck.
- So own-library inputs are not supported for these decks, and PLAN_CEILING §14.4's change is
  not made.
- Ask again once package decks exist (§14.3). There, knowing what is left to draw (the missing
  piece of a combo) can matter where composition does not.

## 2. Where does the search clearly overrule the network? Too rare to rank cards at window 1's scale

**The question** (the red team's M1b). Cards whose decisions the search corrects most are where
the skill to learn lies, and decks rich in them would have a higher ceiling.

**The measurement** (`reports/info_lever_2026-11-12/card_headroom.py`).
- **Data:** window 1's n = 16 records, 11,740 searched decisions (`runs/window1/n16`,
  `confirm16`).
- **A clear correction:** the search's pick differs from the network's top option, and its mean
  result beats the top's by more than two standard errors. Each mean is over ±1 results, so
  var = 1 - q².

**Result.**
- 14 clear corrections in 11,740 decisions (0.1%), all on act asks. No card had more than 2.
- The rank correlation of a card's correction rate with its critic rank over 156 cards is −0.22.
  That is the predicted direction (the critic ranks low the cards the search corrects), but on
  counts this small it is not evidence.

**What it shows instead: the search's per-decision corrections at n = 16 are rarely clear.**
- With 16 simulations over the candidates, a candidate gets 1-4 visits.
- The search's own "clear" (`search.py:108`) needs only a 0.1 margin in mean result, with no error
  term. So window 1's "0.5 clear corrections a game" is mostly within noise.
- This is why gate B scales each target by its standard error (196).
- Per-card headroom needs gate B's 300k targets, or a run at larger n aimed at chosen cards.
