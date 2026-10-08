# 50 — T5 CHARTER: Full-pool atomics re-audit (owner gate 2026-10-08 17:20)

Question (owner): after T2/P1a/P1b/P1c added granular atoms, were ALL encoded cards
(305 golden M21 trees) re-redone under the new atomized structure — do the atoms now
capture ALL card functionality (§11 zero-loss), with no stale/fused/duplicate encodings left?
Status before charter: NO dedicated full-pool re-audit exists. Evidence so far is partial:
clause-mapping probe (/29) = 10 cards/31 clauses; P1a golden churn was byte-minimal by
design (36x1), preserving old shapes where legal; §9 duplicate-CHOOSE merge + E1 direction
split are REGISTERED but NOT executed pool-wide. => T5 = 4 phases:
A CENSUS: machine inventory of every non-canonical/fused/duplicate encoding across the 305
  trees (tools/audit/atomics_census.py) + rewrite ledger with per-pattern tree counts.
B ZERO-LOSS: clause-mapper extended to ALL 305 oracle texts; per-card clause->component
  mapping; every significant clause (significance criterion §11) either mapped or gap-ledger.
C REWRITE: recompile trees where atoms must be rewritten (owner authorizes atomics change
  NOW — supersedes byte-preservation where semantics improve); merge ledger E-rows executed;
  cert chain + lanes + gates hold; fail-register for anything unexpressible (honest §11 gaps).
D PROVE: evidence pack (compile rate, coverage %, census deltas, blind/phantom=0, atom
  census volumes) + ADVERSARIAL GATE before any "all functionality captured" claim (Type-1).
Owner capacity position recorded in NUMBERS (regime-scoped plateau; keep big arms live).

## Phase A + B RESULTS (17:4x, gates mine-run: core 2491+2, 386/386, tools 154)
A census: pool CLEANER than feared — 0 promotable-CHOOSE survivors (P1b persisted on disk),
0 MOVE leftovers, 0 unknown site kinds, tripwires silent. Real residue: EQUIP+TREASURE
decorative keywords (EQUIP = engine-semantics gap, registered), E1 direction has a THIRD
dominant style (Zone.controller x375) — merge must retarget; 8 legacy k>1 CHOOSES (fixed
in F2: now canonical ONE_OF loops, 305 trees byte-verified except the 8 intended).
B clause audit (tools/audit/clause_audit.py, all 305): ZERO-LOSS 97.1% (4678/4809 chars);
131 residual clauses classified: 58 covered-by-different-node, 42 benign (rules boilerplate),
14 token-definition artifacts (FALSE, my initial read), 17 REAL GAPS -> Phase C worklist.
Real-gap 17 = the honest answer to owner's "ALL functionality": NOT yet all — 17 named
gaps + EQUIP enforcement + E1 merge + L-27/28/29 seats are the remaining path to it.

## INTEGRITY RETRACTION (18:5x, Phase-C coder's premise audit)
The "17 gaps" enumerated table circulated in chat + the 'REAL=17' classification are
RETRACTED: cards fabricated by context-assembly (foreign-set names + inventions); the
compiler guard referenced does not exist; blast-radius ~300 impossible (true two-leg-
removal shape count in M21 = 4). DISK TRUTH: clause audit was ad-hoc (/tmp/opencode/clause/),
tool NOT persisted, ~50 residuals UNCLASSIFIED (mostly heuristic false positives),
97.1% figure currently NOT reproducible. Rebuild: persist tools/audit/clause_audit.py,
finish classification with evidence per residual, THEN Phase C from that table only.
Owner's 3-way taxonomy stands as the target schema: {missing-expressiveness |
missing-encoding | clause-not-encoded}.
