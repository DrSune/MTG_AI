# K1b reading rules, written 2026-10-27 21:45:28 CET BEFORE any K1b result was seen

Question (owner, 2026-10-27): "If volume is what we need, then try to give it volume." Does effect
prediction on unseen cards improve when training covers more real sets? The task, labels and
encoders are the same as K1 (tools/k1/train.py). The script is tools/k1/curve.py.

## Training pools
M14 was dropped before any training. Its castable pool has only 9 mana-capable cards, under the
stress deck builder's MIN_MANA_SOURCES = 10, so no M14 game could be dealt.

| Step | Sets |
|---|---|
| 1 set | M21 |
| 4 sets | M21, ZNR, M19, 10E |
| 10 sets | the above plus M10, M11, M12, M13, M15, ORI |
| 16 sets | the above plus DOM, WAR, FDN, ELD, THB, IKO |

Rows are capped at 60 per card per set (stable hash), so reprints and often-cast cards do not swamp
the pool.

## Test sets
These are fixed, and unseen at every step:
- **heldout:** 20% of the 16-set pool's oracle ids (sha256 "k1b:<oid>" < 0.2), removed from
  training at every step;
- **M20, KHM:** their cards that appear in none of the 16 training sets.

## Metric
- **Per-card skill on effect lanes** = 1 − MSE(model) / MSE(state floor of the same step), for each
  test card.
- **Primary population: effect cards.** These are test cards whose compiled IR has at least one
  verb atom. Vanilla and keyword-only cards change no effect lane at resolution. All cards are
  reported too.
- Also reported: the median, the share of cards above 0.1, and pooled effect-lane R².
- **Intervals:** paired, resampling test cards (1000 draws), for differences of medians.

## Rules
1. **Sanity.** The name encoder (16 sets) must have median skill <= 0.02 on M20 and KHM effect
   cards. If not, identity leaks and the run is void.
2. **Volume helps.** This is the owner's hypothesis.
   - The test: ir-bag's median skill on heldout effect cards at 16 sets, minus at 1 set, has a
     paired 95% interval above 0.
   - "Also across sets" if the same holds on M20 or KHM.
   - If the interval contains 0 or sits below it, volume from real sets did not improve transfer
     at this scale.
3. **Shape (descriptive).** Does the 10 -> 16 step still add, or does it flatten?
4. **Atoms vs text at 16 sets.** ir-bag minus text-bag, paired, on heldout effect cards. An interval
   that excludes 0 is evidence for one side. Otherwise there is no evidence either way.
5. **Structure.** ir-pairs minus ir-bag at 16 sets, paired. Read as in rule 4.
6. **Fixed-floor check.** Each step's floor is retrained, so also score against the 1-set floor:
   1 − MSE(model, step) / MSE(state, 1 set). If rule 2 holds on one floor but not the other, report
   both and claim neither.

## Amendment 1, written 2026-10-27 21:49:36 CET, BEFORE any K1b result
The only K1b output seen so far is a 1-epoch smoke run with 2 encoders, used to check the pipeline.

**What the smoke run showed.** Castable pools deal cards that are only partly compiled, and the
engine plays their unparsed sentences as blank (`engine_supported` ignores them; REVIEW_2026-10-24
A-5). For these cards:
- the IR is exactly what the engine executes, so their rows are valid labels for the IR encoders;
- the printed text includes sentences the labels never reflect, which handicaps the text encoders
  in training and in testing.

| Set | Cards dealt | Fully compiled | IR has a verb | Both |
|---|---|---|---|---|
| M21 | 209 | 209 | 195 | 195 |
| M19 | 201 | 72 | 62 | 38 |
| 10E | 212 | 79 | 50 | 39 |
| FDN | 340 | 79 | 90 | 55 |
| IKO | 165 | 17 | 43 | 10 |
| KHM | 171 | 12 | 44 | 6 |

M20 and ZNR were generated from the `compiled` pool, so all their dealt cards are fully compiled.

**Change to the reading.**
- **Run A** (all rows, as registered) decides rules 1, 2, 3, 5 and 6 for the IR encoders. Its
  text-bag and hybrid numbers are reported, not read.
- **Run B** (`--fully-compiled`) restricts train and test rows to cards with nothing unparsed, no
  ambiguity and no unparsed back face. Run B decides rule 4. It also reports rules 2 and 6 as a
  robustness check. Its KHM test has 6 effect cards and is not read.
