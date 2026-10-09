# 58 — batch8: post-T5/F1/F2 re-anchor, 7 arms x 3 seeds (21/21 PASS)
Curve on CURRENT pipeline (386 packs, phantom-free asks, k-of-n canonical, mana taught):
S0 0.776|0.000 b+5.44 | S1 0.764|0.017 | S2 0.764|0.017 | S3 0.759|0.000 b+5.27
S3a 0.764|0.069 | S3b 0.718|0.052 | S4 0.730|0.052.
Read: plateau unchanged (0.17M still ties top); stability degrades with params (ranges
0.000-0.017 <=5.3M vs 0.052-0.069 above). Corpus/pipeline changes raised small arms
(+0.009 S0 vs batch7) — teaching+repair loop keeps paying. Next: ZNR integration (§8).
