# 45 — batch6: first fully 3-seed curve on repaired v6 corpus (10:20, 15/15 clean)

| arm | acc_mean | range | boot_mean | pass |
|---|---|---|---|---|
| S0 0.17M | 0.747 | 0.017 | +4.84 | 3/3 |
| S1 0.63M | 0.747 | 0.017 | +4.84 | 3/3 |
| S2 1.77M | 0.736 | 0.017 | +4.79 | 3/3 |
| S3 5.3M | 0.747 | 0.017 | +5.11 | 3/3 |
| S4 35.1M | 0.672 | 0.121 | +4.23 | 3/3 |

- Corpus repair PAID: v5 small arms 0.704/+4.2 -> v6 0.747/+4.8 — removing broken golds
  raised every model (garbage targets were costing real accuracy, not just eval hygiene).
- ALL 15 RUNS PASS the honest double-stat gate. First sweep with zero failed arms.
- Capacity claim (seed-grade evidence): 0.17M-5.3M INDISTINGUISHABLE (identical means,
  0.017 ranges); 35M LOWER mean + 7x variance (0.121 range) = instability at this volume,
  passes anyway 3/3 but no capacity gain. DATA IS THE ONLY LEVER.
- Wrapper self-refusal root cause (8th law): run_full_memory's own phase-1 start-line
  poisons the ledger for run_train calls inside the wrapped driver -> drivers invoked
  through the wrapper MUST pass --ignore-prev on inner calls (batch6 fix; explains
  batch6b/c deaths; seedvar8 survived only via accidental --ignore-prev).
- S4 engine-on law confirmed: 80-min timeouts twice; engine-off 5 min. 35M = engine-off only.
- NEW STABLE FAIL-CORE (all 12 small-model runs): 6 items = Feat/Palladium/Prismite/
  Traitorous Greed (MANA-COLOR atom — eval-side only, ZERO train lines: the model is
  being tested on an atom it was never taught) + Harbinger a2 + Gift a1 (freshly repaired,
  thin twins). Volume-wave target = mana-color TRAIN-side twins + repaired-shape ladders.
