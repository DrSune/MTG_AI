# 72 — AZ-v2 chain: search-only distill 0.223 vs teacher (best seed); one-shot distillation CONFIRMED dead-end; seed-lottery diagnosis

Date: 2026-10-12. Chain: 96-game wave (1,509 eps) -> search-only S3a x3 (GPU, 50 ep, 2min/ep) -> WR-select -> final duels.
- C (100g vs teacher): s1 0.122 | s2 0.196 | s3 0.021 — seed lottery, 10x spread. D (200g, s2): teacher 0.2234 CI[.171,.287]; mirror vs bc10_S4_s2 (pruner net) 0.3089 — still loses to its own data generator.
- Behavior autopsy: s1 attack-declines 75% (frozen-aggression) vs s3 attacks 84%… opposing pathologies from SAME data recipe => pi targets are noise-dominated, training fits noise differently per seed.
- vs earlier one-shots: bc9 0.3927 / bc10_S4_s3 0.3105 — BOTH distillation variants (mixed 0.179 /71, search-only 0.223 /72) WORSE than plain one-shot BC. Puzzle-acc: 0.19-0.45 (anti-puzzle by design for search-only).
Verdict: ONE-SHOT search distillation from k=3/N=6 cheap-rollout visits is a confirmed dead-end (two independent variants). Root causes: (a) no iterative generation loop (AlphaZero's essence), (b) visit noise hardened by CE + hard zeros on unexpanded options, (c) random-driver rollouts contaminate values, (d) 96 games single-generation.
Mandate remaining untried: ITERATIVE self-play (gen_g+1 from net_g), teacher-only rollouts, pi-mix (0.75 visits + 0.25 net), warm-start train, WR-gate per generation. AZ-v3 launches tonight; honest stop-rule: if 4 generations fail to beat the one-shot 0.39 line, report and park the line.
Wins of the day: cost solved (58 CPU-s/game gen; 2 min/epoch GPU train); GPU-vs-CPU lesson re-learned the hard way (see PITFALLS); outcome-based model selection worked as designed (caught s3 0.021 that acc-metrics would have shipped as 0.9-tier).
