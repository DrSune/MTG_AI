# 165 — Kill test K1: do learned card encoders predict what unseen cards do? (2026-10-27)

Owner: "Go ahead" (building K1 from REVIEW_ARCHITECTURE_2026-10-27 §4). This is a CPU-only,
supervised test of F1 and F2, the load-bearing risks of the atoms + learned encodings + relational
transformer bet:
- F1: compositional generalization;
- F2: atom semantics learned from a weak signal.

The reading rules were written before any result:
`~/mtg_ai_evidence/k1_2026-10-27/PREREGISTRATION.md`, 16:46, copied to
`reports/k1_2026-10-27_preregistration.md`.

## Setup
- **Data** (`tools/k1/gen.py`, run on branch `sets/onboarding`). Every cast and non-mana activation
  of RandomPolicy games is recorded: the card, a 24-number board summary from the acting side, and
  the change after resolution, triggers included.
  - M21: 4000 games, 52,641 rows.
  - M20, compiled pool: 2000 games, 25,401 rows.
  - ZNR, compiled pool: 1000 games, 10,919 rows.
  - Spot checks hold. Llanowar Visionary: library −1, hand ±0, +1 creature at +2/+2. Divination
    and Shock are as printed. Under random targeting Shock's damage splits between the two sides.
- **Models** (`tools/k1/train.py`). Six encoders at one budget, all given the same printed-face
  tokens:
  - state only;
  - name embedding;
  - IR bag;
  - IR sequence (a small transformer);
  - Oracle-text bag, with no pretraining;
  - IR + text.
- **Metric:** R² on the **effect lanes**, the changes the card's own entry cannot explain.
- **Ceiling:** the per-card mean on the test rows.
- **Intervals:** 95%, from 200 resamples of test **cards**.

## Results (effect-lane R²)

| Split | Test cards | Ceiling | State | Name | IR bag | IR seq | Text bag | IR+text |
|---|---|---|---|---|---|---|---|---|
| random (seen cards) | 209 | 0.614 | 0.001 | 0.677 | **0.705** | 0.679 | 0.680 | 0.640 |
| held-out M21 cards, draw 1 | 41 | 0.472 | −0.003 | −0.063 | **0.097** [0.02, 0.25] | 0.086 | 0.054 | 0.090 |
| held-out M21 cards, draw 2 | 40 | 0.967 | 0.000 | −0.002 | 0.003 [0.00, 0.27] | — | −0.002 | 0.001 |
| held-out M21 cards, draw 3 | 29 | 0.357 | −0.004 | −0.084 | 0.149 [−0.04, 0.35] | — | 0.093 | 0.152 |
| compound (rare atom pairs) | 41 | 0.699 | −0.007 | −0.098 | 0.116 [−0.21, 0.23] | −0.179 [−0.67, −0.05]† | 0.088 | 0.098 |
| M20 cards M21 lacks | 70 | 0.695 | −0.014 | −0.181 | **0.506** [0.42, 0.57] | 0.122 [0.07, 0.18]† | 0.503 | 0.519 |
| ZNR cards M21 lacks | 84 | 0.535 | −0.011 | −0.192 | 0.236 [0.12, 0.36] | — | 0.223 | 0.298 |

Draw 2 is 96% one card: Peer into the Abyss, which draws half the library and loses half the life.
No other M21 card does anything comparable, so nothing can predict its size. The other draws are
spread out: in draw 1 the largest shares are Chandra, Heart of Fire at 0.30 and Secure the Scene
at 0.22.

## Reading, by the pre-registered rules
1. **Sanity holds.** Name never beats the floor on unseen cards, so no identity leaks. It sits
   below the floor by up to 0.19: an untrained `<unk>` embedding is noise, not leakage.
2. **Transfer is mixed, and it depends on how novel the cards are.** The rule is to keep at least
   60% of the random-split gain over the floor.
   - **Met on M20:** IR bag keeps (0.506+0.014)/(0.705−0.001) = **74%** of its seen-card gain and
     73% of the ceiling.
   - **Missed on held-out M21 cards:** 14%, about 0%, and 21% across the three draws.
   - **ZNR is in between:** about 35%.
   - The interpretation: the encoder transfers to new cards that resemble ones it trained on. M20's
     compiled pool is, by construction, cards made of known patterns. It does not transfer to
     effects that are unique in the set. With 168–209 training cards, atom semantics were not
     learned beyond the families the training set already covered.
3. **No specific compositional gap,** but the test was weak. Compound keeps 17% against the cards
   split's 14%. The greedy split reached only **26% of test atom pairs unseen in training**: 209
   printed cards are too few for a strong compound-divergence split. Synthetic cards would make
   one possible.
4. **Atoms against text, with no pretraining: no evidence either way.** On M20, IR bag beats text
   by +0.003. On compound it is +0.028, inside wide intervals. IR + text is best on ZNR (0.298
   against 0.236).
5. **Structure: no.** IR seq is *worse* than the bag: compound −0.179 against 0.116, M20 0.122
   against 0.506.
   - †These two runs used batch 1024 (about 600 steps) for speed.
   - At batch 256 it was also slightly below the bag, on held-out cards (0.086 against 0.097) and
     on seen cards (0.679 against 0.705).
   - With 168–209 training cards, a transformer over IR tokens overfits token order. The bag's
     weaker inductive bias generalizes better. Structure is not learnable at this data scale.
6. **ZNR is not decisive.** It needs atoms M21 never uses.

## What this means for the bet
- **F1 and F2 are real, and the limiting factor is how many distinct effects training sees, not
  the encoder.** On new cards resembling known ones, atoms transfer well (M20: 74%). On genuinely
  new effects they barely transfer. And an exotic magnitude like Peer into the Abyss is
  unpredictable from 200 cards whatever the encoder.
- **This supports the red-team's strongest form of the bet.** The engine can label unlimited
  synthetic cards, composed from atoms with sampled parameters, so effect diversity in training is
  no longer capped by the printed card pool.
- **Next experiment, K1b:**
  - train on M21 + ZNR + synthetic cards;
  - evaluate held-out cards and KHM with a per-card metric, the median over cards of each card's own
    explained share, which no outlier can dominate;
  - add pretrained text embeddings from the 27B once the engine is back.
- **Caveats.**
  - The labels come from RandomPolicy, which targets at random, so effects split across sides.
    They are a 24-number summary that does not see grants such as hexproof.
  - The M20 test cards are the compiled subset, which is selection bias toward known patterns.
  - These are effect predictions, not play. K2 (value transfer) is the next rung.
