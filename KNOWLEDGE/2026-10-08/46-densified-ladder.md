# 46 — Densified capacity ladder, first read (2026-10-08 13:00, batch6d + S3a/S3b)

21 runs total, 21/21 PASS honest double-stat gate. acc_mean|range by params:
0.17M 0.747|0.017 · 0.63M 0.747|0.017 · 1.77M 0.736|0.017 · 5.3M 0.747|0.017
10M 0.718|0.069 · 23M 0.741|0.052 · 35M 0.672|0.121
=> Seed-instability ONSET ~10M at ~180-line volume; grows monotonically with params;
   mean NEVER exceeds the 0.747 plateau anywhere. Big models buy variance, not accuracy.
CAVEAT (self-declared): S3a/S3b trained on the 180-item waved corpus; S0-S4 arms on 168
(era confound on the variance comparison). Elo also says d64->d256 pays (+0.054 WR,
admissible) then saturates — consistent with plateau-at-5.3M.
Settled by batch7: full 7-arm x 3-seed on unified 180-item corpus (bc7_* prefix).
Complexity baseline banked (complexity_v6.json): menu mean 2.97/p90 6 (mana 6), entropy
load 1.40 bits/ask, coverage holes 0, drafter 0.58 scripted decisions/pack, vocab 404->432.
