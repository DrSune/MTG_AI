# 2026-09-24 · 04 — Owner decisions (recorded at session end)

Three decisions captured via the owner prompt:

1. **Commit the working tree — APPROVED.** The full ~10-day uncommitted
   Phase-1 work (grammar rounds through round 3, the 8-template batch,
   knowledge tree, tools, goldens) is committed at session end. One
   logical commit per coherent unit where cleanly separable; otherwise a
   single Phase-1 commit is acceptable (the working tree is a single
   verified state).

2. **PC-6 orphans — both RATIFIED.**
   - `PHASE_IN` — pending since 2026-09-22; no M21 pool shape, but a
     standard MTG mechanic (phase in/out). Ratified as a documented
     cross-set verb, not a bug.
   - `FLIP_COIN` — cross-set coin-flip mechanic; currently orphan because
     the B5c shape "{T}, Pay N life: Flip a coin." (Tavern Swindler) is not
     yet templated. Ratified now; it becomes non-orphan automatically when
     that shape is registered (no further action).

3. **Next session — round-4 grammar: conditional triggers.** The largest
   residual family (~18 B2b shapes). Trigger events need cast-from-zone
   scoping, first/second-this-turn ordinals, damage-source attributes, and
   "when you do" anaphora. Follow the round-3 process: dated binding
   decision doc (pool-shape + cross-set justification per item) → coder
   implementation (additive, byte-stable, omit-if-None) → orchestrator
   verification → template batch → NUMBERS/KNOWLEDGE update.

Still open (not decided): JOURNAL tooling status (open since 2026-09-23).
