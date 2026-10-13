# 77 — SHADOW-1: champion-distribution distillation sets a NEW frontier (0.4256 vs teacher; mirror 0.529 vs champ) — DAgger law confirms; drift loop closed (0.3355 -> 0.0007)

Date: 2026-10-13. Recipe (Option A of /75): 48 games of bc9_S3_s1 vs {teacher,random,self} -> 778 live episodes (778 asks 2,424) -> S3a clone x3 (60 ep, vocab rebuilt from LIVE data = numeric-lane UNK hole closed by construction).
Results (200g, engine pool, CI95):
- bsh_S3a_s1: vs teacher 0.4256 [0.358,0.496]; vs champion head-to-head 0.5288 [0.458,0.598]. Puzzle acc 0.643.
- bsh_S3a_s2: vs teacher 0.3660 [0.301,0.436]; mirror 0.4521 — seed pair brackets the champion's 0.3927 (selection by WR still picks s1).
Calibration honesty: s1 vs the old frontier line 0.3927 — CIs overlap => NOT yet a decisive improvement over the CHAMPION, but DECISIVE over every batch9-era net (0.22-0.34, non-overlapping CIs) and mirror >= champ.
Mechanism: the exposure-gap cure (train on the distribution the policy will visit), exactly the DAgger motivation named in wave-1 (/61) — curated puzzle lines don't transfer; live-distribution cloning does, even when the expert is only 0.39-class.
Drift law closes: live-UNK for the clone 0.0007 (480x better than the champion-era 0.3355) — vocab-from-live-data containment works; §76 cure (digit-tokenization) still open for the next era.
Two-meter law, final form: puzzle acc 0.643 + WR 0.426 beats acc 0.766/0.827/0.905 nets — accuracy alone is unadmissible for gameplay claims (WR probe standing policy, /75).
Next: shadow2 (self-distill from clone, 990 eps, training now) + s3 duel pending + finals vs bc10 line + bc9_S3_s1 direct re-run at higher N if owner wants decisive champ-surpass claim.
