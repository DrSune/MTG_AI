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
