# Design: the playing network reads components, not names (2026-10-28)

**Owner, 2026-10-27/28.**
- "The main thing for me is that the network that places the card knows what the atomiser
  components mean."
- "The bottleneck is making the model generalise. It's playing level."
- "In the long run we use local agents for it."

This page is written for whoever implements it, a local agent included.

## Evidence
| Test | What it shows | Note |
|---|---|---|
| K2 (choices) | A chooser that reads the source card's components picks the engine-best option on **unseen** cards at 0.861; one that reads its name, 0.709; one that reads nothing, 0.733. components − name is +0.152 [+0.090, +0.235], and all seeds are positive. Names memorize trained cards and give nothing on unseen ones. | /169 |
| K1b (effects) | A component bag predicts unseen cards' board effects better the more real sets it trains on (+0.205 from 1 to 16 sets). | /166 |
| K1c (structure) | At up to 556 clean cards, a transformer over a card's IR sequence is below the bag (−0.083). Use the bag per card; leave relations between cards to the board-level transformer. | /166 |
| Sharing | 48 of 193 component types cover 90% of uses, and 26% of types are used by two cards or fewer (B-44). The fewer and more general the components, the more each one is trained. | /169, B-44 |

## Today
- **Input.** A card is `[handle, name, tapped, counters]` (`tools/training/ab_duel.py:572-578`).
  `bc_data.tokenize` turns the name into words, and an unseen word is `<unk>`
  (`tools/training/bc_data.py:22-23`, `:174-188`). `PointerBC` embeds those words
  (`tools/training/bc_model.py:45`) and scores candidates by pointer.
- **Teacher.** `HeuristicTeacher` (`tools/eval/gameplay_eval_v2.py:168-269`) takes the first option
  at every target, sacrifice and mode ask, and the minimum number. So BC from it teaches nothing
  about what a card's components mean in a choice, whatever the input.

## The change
1. **One card token per card,** embedded from components.
   - In the observation, a card row keeps its handle and adds its oracle id. The name is dropped.
   - The token's embedding is `card_encoder(bag)`. The bag is the card's IR tokens plus its printed
     face (types, P/T, mana value, colours), as in `tools/k1/train.py` `card_inputs`.
   - `card_encoder` is a small MLP, the K1/K2 bag. It replaces the name-word embeddings at that
     position. The sequence gets shorter, not longer.
2. **Candidates that are cards** (targets, attackers, sacrifices; `bc_data_v2.card_row_lookup`,
   `ground_with`) take their key from the same `card_encoder`. So the pointer scores options by
   what the cards are and do.
3. **Engine-supervised heads before and beside RL:**
   - K1's effect head: predict the board change of casting the card;
   - K2's choice head: score each option against the engine's replay label.
   Both are free and exact, and cover what the teacher cannot. RL then trains the act window and
   long-horizon play on top.
4. **A stable component vocabulary** (F9): types and buckets, versioned with the ontology. An
   ontology change re-bakes the vocabulary, at an era boundary.

## Gates, in order, before it replaces anything
1. **Name-permutation invariance.** Swap all card names in an episode: logits must be
   byte-identical. Names no longer enter the model.
2. **K2 on unseen source cards.** At least as good as the standalone chooser (0.861 on run-2
   data). Run with `tools/k2/train.py` (data `tools/k2/gen.py`; repair is not needed with the fixed
   gen).
3. **Duplicate-duel swap test** (`MTG_bot/bench`, `play_duplicate`). Take decks the policy trained
   on and swap cards for unseen cards built from known components:
   - functional twins first (same IR, other name, across the 19 sets);
   - then cards with new combinations.
   Win rate against the heuristic must stay inside the original decks' interval. The name-reading
   policy is the control and should drop.

## Constraints
- **The RL payload is pinned.** `tools/training`, `tools/eval` and `MTG_bot` are fingerprinted
  (`tools/ops/rl_window.sh`). Build next to it (for example `tools/policy_c/`) and adopt at an era
  boundary with an explicit re-pin.
- **GPU.** CED holds it until about 14:45 on 2026-10-28; after that it is the owner's call.
  Everything up to gate 2 runs on CPU at small scale.
- **Ownership.** Claude prototypes. The training and evaluation pipelines are run by local agents
  (owner, 2026-10-28), so every step is a CLI with a pre-registration file.

## Open items this design does not solve
- **"Which volumes" (X).** The bench fixes X at 0 (a registered scaffold). An X-choice site in
  `SeatRouter` is needed before K2 can label X.
- **Discard choices.** K2's board summary cannot tell which card was discarded. Labelling them
  needs a card-aware value.
- **Sharing.** The B-44 fold (eight "this turn" predicates and five comparators into general atoms)
  and B-48 (discard has two encodings) make the bag smaller and better trained.
- **Mapping new cards by agents.** The IR already round-trips as data (`ability_tree.to_dict` and
  `from_dict`; the goldens are stored this way). A supply-level loader that prefers a mapped record
  over the compiler is what the local agents need. Each mapped card gets an engine check.
