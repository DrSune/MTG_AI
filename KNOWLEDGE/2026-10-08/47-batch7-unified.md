# 47 — batch7: unified 180-item corpus, 7 arms x 3 seeds (14:35, 21/21 PASS, 3105 s)

acc_mean|range|boot: 0.17M 0.776|0.000|+5.44 · 0.63M 0.770|0.017|+5.39 · 1.77M 0.764|0.017|+5.32
5.3M 0.759|0.000|+5.56 · 10M 0.764|0.017|+5.33 · 23M 0.753|0.017|+4.94 · 35M 0.736|0.069|+5.05
1. Wave payoff: +0.029 vs batch6 era at equal-or-better gates; the repair+teach loop WORKS.
2. /46 onset-10M RETRACTED as era confound: seed-stability uniform <=0.017 through 23M;
   only 35M wobbles (0.069). Capacity: flat 0.17-10M, mild decline 23-35M, zero gains.
3. Cross-card mana generalization PARTIAL: Palladium OK, Prismite 1/3 seeds, Traitorous ~1/2,
   Feat 0/3, Gift a1 + Harbinger a2 still fail (thin train lines: 10-13 total). More twin
   volume = next lever; also new-set integration per AGENTS §8.
Best-model-per-item note: 0.17M ties/wins overall at every era so far -> default model.
