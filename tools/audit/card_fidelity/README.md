# Card fidelity labels

Does a card's compiled ability tree mean what its printed text says? The compiler marks a card
"fully compiled" when no sentence is left unparsed and nothing is ambiguous; that says nothing
about whether the parse is right. A wrong tree teaches the self-play network a different game,
so cards are labelled before they join a training pool (`tools/selfplay/learner.py
--mix-allow`).

## M20_M19_new.jsonl (2026-11-05)

The 147 cards of M20 and M19 that compile fully (`get_supply("compiled", code).deckable`) and are
not in the M21 pool. Three agents each read 49 cards: printed text against the compiled tree
(`to_dict`), checked against the closest hand-verified M21 golden (`MTG_bot/core/golden/M21/`)
and, where the tree alone was ambiguous, against the executor code. One row per card:

- `verdict`: FAITHFUL (every rules sentence represented with the right effect, amounts,
  targets and restrictions, trigger, duration, controller), UNFAITHFUL (anything missing,
  extra or wrong), UNSURE.
- `complexity_tier`: 1 vanilla or keywords only; 2 one simple ability; 3 two or more abilities,
  or conditional/modal/optional; 4 complex interactions (control change, X, replacement, copy).
- `issues`, `notes`: the discrepancies and what a curator should know.

Result: **142 FAITHFUL, 5 UNFAITHFUL**; tiers 55 / 68 / 23 / 1.

| UNFAITHFUL | defect | same defect in the M21 pool |
|---|---|---|
| Goblin Smuggler | the activation has no target selector: no creature ever becomes unblockable (restrictions checked at block time) | Subira (golden has the same shape; BACKLOG lists the gap) |
| Ethereal Elk, Yanling's Harbinger, Sorin's Guide, Goldmane Griffin | "search your library and/or graveyard": one merged search, so the library is always shuffled and the graveyard cannot be searched alone; "reveal it" reveals the top card; "put it into your hand" is a second, inert move of the source | Chandra's Firemaw, Garruk's Warsteed, Teferi's Wavecaster, Liliana's Scorn, Basri's Aegis; Sanctum of All always shuffles |

The M21 goldens are therefore not all correct: matching a golden does not prove a card. The
search defect is fixed on the unmerged branch `cards/integration` (B-78, "a visible zone
choice"; 178 commits ahead of main on 2026-11-05).

`tools/selfplay/mix_allow_m20_m19_t12.json` = FAITHFUL, tier <= 2, non-land: 71 M20 + 51 M19
cards, the first batch for mixed-set training.
