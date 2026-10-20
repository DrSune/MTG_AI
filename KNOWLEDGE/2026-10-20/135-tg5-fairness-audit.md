# 135 — T-G5 fairness audit (analyst-gated evidence): cross-set ELO ladder NOT hostable today (2 FATAL); gameplay_eval_v2 CAN host the T-G1 matrix now; puzzle meter demoted to diagnostic cross-set

Date: 2026-10-20. Method: analyst subagent (128k-xhigh, read-only) over elo_batch7_*/ab_duel/elo.py/gameplay_eval_v2.py/eval_ckpt.py + /123 + /128; orchestrator wrote. Built on Verified Evidence: D9 seed-keying (+0.400), /133 era law, acc/WR anti-correlation.

## Defects (file:line evidence in analyst return; headline)
- **FATAL-1 M21-locked ladder**: ab_duel get_supply() has no set arg (ab_duel.py:624,682,777); elo main lacks --set (elo.py:288-307). The ladder cannot play a ZNR pool at all.
- **FATAL-2 puzzle meter is vocab-relative**: scored vs checkpoint's own vocab joined to M21 corpus (eval_ckpt.py:29-36); cross-set acc = different item populations; fresh-set lane degenerate (n_fresh=0; /128 needed a /tmp monkeypatch). => puzzle acc is DIAGNOSTIC ONLY cross-set (compounds the anti-correlation law).
- AMENDs: admissibility gate surfaces only vs-anchor though per-pair adm[(i,j)] exists (elo.py:208,232); fit_elo FITS INADMISSIBLE PAIRS (elo.py:205 — /26 fabricated-ratings pattern); pool default mismatch (elo default all vs rig default engine; ZNR partial-compile => different supplies); batch7 rig hardcodes pairs/ckpts; table stamps date not engine build.
- Intact levers (keep): deck-keyed deals (gameplay_eval_v2.py:444-448), seat-swap balance, --seed-start replay-identical deal lists; pair-admissibility MATH is pool/vocab-agnostic and survives.

## T-G5 DECISION
Matrix hostable TODAY via gameplay_eval_v2 (mirror lane + --set + rotated seed bases; /123 proved the recipe). ELO ladder needs, in order: (1) set_code plumb (ab_duel/run_ladder/main); (2) per-pair admissibility surfaced + inadmissible excluded from fit; (3) pinned --pool engine, shared --seed-start, ONE engine session per matrix + engine git-stamp on table; (4) frozen bsh_S3a_s3 era-parity SENTINEL cell in every matrix run; (5) puzzle-meter native set-split corpus (owed, non-blocking).

## C — protocol decisions (owner sign-off before T-G1 runs)
Opponent control: bidirectional head-to-head mirrors per pool + random anchor; teacher = diagnostic. Pool separation: one table per pool-cell, report the 2×2, never merged cross-set ELO. Volume: equal games/pair, n sized so CI clears 0.5 at the smallest claimed delta, identical deal lists. Verdict-bearing meter: **WR only**. T-G2 acceptance format: "combined beats each dedicated IN THAT DEDICATED'S HOME POOL, CI excludes 0.5" — home-pool reverse is the fairness core.

## Free datum for T-G7 (parallel training): PERFECT scaling observed
R1 window ran 3× S4 (35M) cuda trainings concurrently: wall_s = 3015.8/3016.0/3016.0 — identical to single-arm expectation (~12 ep × 4.5k eps). GPU compute was NOT the constraint with engine off; parallel factor ≈ 3.0 at 3 arms. (Source: /tmp/opencode/r1_window.log.) Implication for T-G1 matrix: run arms+duels in parallel inside one window; matrix wall-clock ≈ slowest cell.

## Lane status
T-G1 matrix EXECUTION stays parked (owner wording: "until the atom-ontology lane closes its R-rounds" — R1b/R2/R3 queued, /131 W1 in flight today). This audit is its pre-decision (T-G5 explicitly "decide before running the T-G1 matrix") — done, protocol memo above awaits owner initialed choices.
