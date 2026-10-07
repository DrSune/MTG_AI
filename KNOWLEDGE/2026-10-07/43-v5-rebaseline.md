# 43 — v5 re-baseline post-P1 (2026-10-07 21:50, complete 484.4)

New vocab (19 site kinds incl. one_of/sacrifice), T4 tokenizer (MOVE merge, structural
PICK promotion), hexproof-enforced engine, 164-item corpus / 54 eval items:
S0 0.17M 0.704 boot+4.22 | S1 0.63M 0.704 +4.22 | S2 0.685 +4.07 | S3 5.3M 0.704 +4.44
| S4 35.1M **0.574 +2.88 NULL**.
Small arms IMPROVED (v4 boot 3.09-3.46 -> 4.07-4.44): the ask-visibility vocab made the
task more legible at small scale. S4 REGRESSED from v4 best (0.725/+4.56) to NULL: 19 fails
vs S0's 12, 7 big-specific (Crypt Lurker/Heartfire/Skeleton Archer/Solemn Sim. etc.), train
loss lowest (0.180) = overfit signature resurfacing under richer inputs. Single-seed caveat:
seedvar batch launched (S0/S4 x seeds 2,3) — claims pending variance.
Interim: at 164 lines the efficient frontier is 0.17M-5.3M; 35M pays the overfit tax again.
