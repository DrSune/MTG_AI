# 76 — Tokenizer law violation found with measurement: world-lane NUMBERS are fixed literals in vocab — live value ranges go UNK (33.5% of champion's live tokens)

Date: 2026-10-13. Evidence (drift_probe.py): TRAIN-era UNK 0.0000 (all numbers in 131 curated episodes fit the literal vocab), LIVE UNK 0.3355 — per-ask numeric world fields (library counts, totals: '27','22','118'...) OOV because puzzles were curated with narrow numeric ranges; expanded card-name coverage compounds it.
Laws implicated: §10 menu-visibility (numbers are observable axes — UNK = blindness at resolution time, the same sin class as the heal-what-menu case) and §8 (atomic structure must be re-evaluated per pool — vocab-as-tokenizer caps generalization).
Fix proposals (Type-1, owner decision, with shadow-program evidence attached):
(1) DIGIT-TOKENIZATION of numeric lanes (digits as reusable atoms, e.g. 'n','2','7' composition for 27): unbounded coverage, shared embedding algebra (counts compose), costs: re-encode + retrain everything, vocab shape change.
(2) BUCKETING (magnitude buckets: n_small/n_mid/n_large + sign lanes): cheap, lossy (loses exact count where it matters for threshold plays like "exile top half rounded up"), re-encode + retrain.
(3) STATUS QUO + per-set vocab union (current de-facto): every corpus change silently re-languages the world; era-regressions like /75 are the measurable cost.
Shadow program (in flight): episodes generated from LIVE play cover live numeric ranges by construction — bsh clones get live-complete vocab without any encoding change: a containment strategy, not a cure. Cure candidate is (1). Numbers attached to the decision when shadow duels land.
