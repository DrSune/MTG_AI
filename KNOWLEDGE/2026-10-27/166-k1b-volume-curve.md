# 166 — K1b: does more real-card volume make atom encoders transfer better? Yes. (2026-10-27)

Owner, after /165: "If volume is what we need, then try to give it volume." No GPU, no 27B. So
this is K1's task again (predict the engine's board change of a cast from the card), trained on
pools of 1, 4, 10 and 16 real sets. CPU only, 7.7 minutes of fitting in total.

Reading rules: `reports/k1b_2026-10-27_preregistration.md`, written 21:45 before any result.
Amendment 1 was added at 21:49, after only a 1-epoch pipeline smoke had been run.

## Setup
- **Sets.** 15 more MTGJSON sets downloaded (`reports/set_sources_k1b_2026-10-27.tsv`). 600
  RandomPolicy games each (`tools/k1/gen.py`, with a new 20 s per-game timeout), on branch
  `sets/onboarding`.
  - WAR needed ingest fix 9ee6966.
  - M14 cannot be dealt: its castable pool has 9 mana-capable cards, and `build_deck` needs
    `MIN_MANA_SOURCES` = 10 (`core/executor/games.py:133`). It was dropped before training.
- **Steps.**

  | Step | Sets |
  |---|---|
  | 1 set | M21 |
  | 4 sets | + ZNR, M19, 10E |
  | 10 sets | + M10, M11, M12, M13, M15, ORI |
  | 16 sets | + DOM, WAR, FDN, ELD, THB, IKO |

  At most 60 rows per card per set.
- **Tests,** fixed and unseen at every step:
  - held-out: 20% of the pool's oracle ids, removed from training at every step;
  - M20 and KHM cards that appear in no training set.
- **New metric: per-card skill.** 1 − MSE(model)/MSE(state floor) on the effect lanes, per test
  card. The headline is the median over **effect cards**, whose IR has a verb atom.
  - Intervals are paired, resampling test cards (1000 draws).
  - Code: `tools/k1/curve.py`; exploratory split `tools/k1/k1b_explore.py`.

## Finding before any result: old sets are dealt mostly blank (B-46)
The 14 new castable pools deal 2,482 cards. Only **683 (27.5%) are fully compiled**, for example
IKO 17/165 and M19 72/201. KHM, a test set here, is 12/171. The engine plays the rest with their
unparsed sentences blank.

For those cards the IR is exactly what the engine does, so their rows are valid for IR encoders.
Their printed text is not. Hence Amendment 1:
- **run A** keeps all rows;
- **run B** keeps only fully compiled cards and decides atoms-vs-text.

| | Run A (all rows) | Run B (fully compiled) |
|---|---|---|
| Training cards, 1 → 16 sets | 169 → 1,829 | 169 → 556 |
| of which effect cards | 157 → 614 | 157 → 382 |

## Results (median per-card skill, effect cards; run B unless marked)

| Test (effect cards) | Encoder | 1 set | 4 sets | 10 sets | 16 sets | 16 − 1, paired 95% |
|---|---|---|---|---|---|---|
| held-out (89) | ir-bag | 0.316 | 0.412 | 0.433 | **0.521** | **+0.205 [+0.120, +0.300]** |
| held-out (89) | text-bag | 0.212 | 0.356 | 0.427 | 0.462 | +0.250 [+0.147, +0.350] |
| M20 (16) | ir-bag | 0.302 | 0.532 | 0.488 | 0.538 | +0.236 [+0.139, +0.443] |
| held-out, run A (148) | ir-bag | 0.325 | 0.436 | 0.494 | 0.578 | +0.253 [+0.167, +0.378] |
| KHM, run A (39) | ir-bag | 0.253 | 0.435 | 0.504 | 0.678 | +0.424 [+0.290, +0.525] |

The share of effect cards above 0.1 skill rises too: held-out run B goes from 0.685 to 0.854.

## Reading, by the pre-registered rules
1. **Sanity: run A fails by the letter, run B passes.**
   - Run A, M20: name sits at +0.084 [−0.055, +0.353] on 16 cards, against a threshold of 0.02.
     By the rule, run A is void, so its numbers above are context only.
   - Identity is not the cause. Every unseen card maps to name index 0 (`tools/k1/train.py:358`),
     which no training row carries. A 16-card median of a no-information model simply moves that
     much.
   - Run B passes everywhere: held-out −0.028, M20 −0.061, KHM −0.046.
   - Run A being void, every reading below rests on run B. Run A agrees on each one.
2. **Volume helps, also across sets.** ir-bag 16 − 1: held-out **+0.205 [+0.120, +0.300]**, M20
   +0.236 [+0.139, +0.443].
3. **Shape: not flat by 16 sets.**
   - 1 → 4: +0.095 [+0.047, +0.206].
   - 4 → 10: +0.022 [−0.036, +0.073]. This step was mostly core-set reprints: +108 cards, +52
     effect cards.
   - 10 → 16: **+0.088 [+0.031, +0.133]**: six non-core sets, +115 cards, +67 effect cards.
   - Distinct effects, not rows, seem to carry it (descriptive).
4. **Atoms vs text: no evidence either way.** ir-bag − text-bag at 16 sets: +0.059 [−0.016, +0.137]
   held-out, −0.054 [−0.206, +0.065] M20.
   - Run A's +0.134 [+0.054, +0.234] is the confound Amendment 1 was written for: its text
     includes sentences the engine never runs.
5. **Structure: no evidence.** ir-pairs (parent>child pairs) − ir-bag: −0.024 [−0.059, +0.033]
   held-out.
6. **Fixed floor: holds.** Against the 1-set floor in board units: held-out +0.293
   [+0.188, +0.350], M20 +0.264 [+0.133, +0.456]. The gain is not an artifact of each step's floor.

## Exploratory (not pre-registered)
- **Where the gain comes from (run B held-out).**
  - "Covered" cards, every atom already on some 1-set training card (69): ir-bag **+0.241
    [+0.150, +0.335]**. More cards taught better encodings of atoms the model had seen. That is the
    owner's "nuance" hypothesis.
  - Cards with an atom new at 1 set (20): +0.248 [−0.076, +0.821], too few to read.
  - Caveat: the covered gain may partly be near-duplicate cards in other sets, i.e. more neighbours
    rather than finer atoms. M21's own held-out cards (38) gain less: +0.168 [−0.013, +0.302]
    (run B), +0.031 [−0.132, +0.215] (run A).
- **Pooled R² is ~0.001 at 1 set for every encoder (held-out and KHM).** This is an artifact.
  - The cause: no M21 training row changes `opp.lands`, so its target scale clamps to 1e-3, and any
    test card that touches an opponent's land dominates the pool.
  - Per-card medians are robust to it, and rule 6 uses board units.
  - K1's published numbers are unaffected: no K1 test row touches `opp.lands`.
- **K1 (/165) re-read.** Its "no transfer to unique effects" came from pooled R², which a few
  big-effect cards dominate. On the median card, M21's held-out effect cards already score 0.285
  per-card skill at 1 set (ir-bag).

## What this means
- **The owner's bet survives its first volume test.** With more real cards, IR encoders transfer
  better to cards they never saw, on held-out cards and on whole unseen sets. The curve is still
  rising at 16 sets.
- **The compiler is the volume tap.** Clean volume (run B) is 556 cards out of 1,829 dealt.
  - Each grammar round on these 14 sets adds training cards with labels that match their text.
  - The sets lane and the learning lane are the same lane.
  - The sets have not been through sealed first touch, and no unparsed sentence of theirs has been
    read. So run `tools/audit/new_set.py` on them before any grammar round.
- **Synthetic cards:** not needed to show transfer. They stay the clean test for genuinely new
  compositions, after real-set volume, as the owner prefers.
- **Caveats.**
  - RandomPolicy labels, and a 24-number board summary, as in K1.
  - Test M20 is 16 effect cards. KHM in run B is 2 cards and is not read.
  - Effect prediction is not play. K2 (value transfer) is next and needs no GPU.

Data: `~/mtg_ai_evidence/k1_2026-10-27/` (`k1_*.jsonl`, `run_k1b.sh`, logs). Results:
`reports/k1b_2026-10-27_{curve,explore}_{A,B}.json`; the per-card errors are in
`reports/k1b_2026-10-27_curve_{A,B}.cards.json`.

## K1c: does structure catch up at volume? Not yet (GPU slot, 23:34; pre-registered)
Reading rules: `reports/k1c_2026-10-27_preregistration.md`. The setting is K1b's run B exactly,
with K1b's compiler (9ee6966). The difference is that ir-seq (a small transformer over the IR token
sequence) now runs on the GPU at the bags' batch of 256, so K1's batch-1024 handicap is gone. Three
minutes in total. Results: `reports/k1c_2026-10-27_curve_B.json`.

| Held-out effect cards (89) | 1 set | 4 sets | 10 sets | 16 sets |
|---|---|---|---|---|
| ir-bag, K1c GPU | 0.317 | 0.506 | 0.450 | 0.531 |
| ir-bag, K1b CPU | 0.316 | 0.412 | 0.433 | 0.521 |
| ir-seq, K1c GPU | 0.260 | 0.282 | 0.475 | 0.448 |

- **Rule 2, structure at volume: the bag is still better.** ir-seq − ir-bag at 16 sets: **−0.083
  [−0.132, −0.007]** held-out, −0.020 [−0.161, +0.162] on M20 (no evidence).
- **Rule 3, trend: no sign the gap closes.** Median d(16) − median d(1) is −0.013 [−0.070, +0.012].
- **Rule 1, device: single fits vary.** The same fit on GPU and CPU gives 0.317 and 0.316 at 1 set,
  but 0.506 and 0.412 at 4 sets.
  - A single fit moves by up to about 0.1 with device or initialization. The card-resampling
    intervals above do not capture this.
  - The 1 → 16 volume gain is about twice that and replicates on the GPU: +0.214, against K1b's
    +0.205.
  - Step-to-step wiggles, like the 4 → 10 dip, are within it.
- **For the bet.** Up to 556 fully compiled training cards, a flat sequence model over atoms does not
  beat the bag of atoms, and its gap does not shrink. Two things are untested here:
  - a tree- or graph-structured encoder (message passing over the ability tree, the "relational
    network" proper);
  - larger clean volume, which the compiler gates (/167).
  So K1c does not justify a transformer on the card side yet. The bag carries the transfer.
