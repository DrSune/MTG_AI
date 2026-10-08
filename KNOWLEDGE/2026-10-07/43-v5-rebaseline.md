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

## CORRECTION (2026-10-08 03:25) — "S4 NULL" was a seed artifact (n=1 overclaim retracted)
S4 seeds {1,2,3}: 0.574/+2.88 NULL, 0.667/+3.74 PASS, 0.685/+4.01 PASS — spread 0.111,
mean 0.642. s2/s3 fail-sets are STRICT SUBSETS of s1's (0 new items) — seed 1, the
headline run, was the unlucky draw. 35M DOES pass the honest gate 2/3 seeds.
CONTRAST: S0 variance EXACTLY zero (0.704 x3, identical fails) => instability is a
LARGE-MODEL property at 110 train lines, not general seed noise.
HONEST CAPACITY CLAIM (all arms, 3 seeds where multi-run): 0.17M-35M statistically
INDISTINGUISHABLE at 164 lines — data volume is the sole lever; note v4's "35M best
0.725" was ALSO n=1 and is hereby demoted to same-claim status.
SEED LAW (binding): model-comparison claims require >=3 seeds (or boot CI over seeds);
single-seed arms are diagnostics only. Cheap here (5 min engine-off).
STABLE FAIL-CORE (all 6 model x seed runs, 164-item corpus): 12 items — the exact
volume-wave shopping list (names in seedvar record below).
