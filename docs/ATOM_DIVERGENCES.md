# ATOM DIVERGENCES — known same-function-different-bytes classes (ledger)

Companion to docs/DESIGN_ATOM_ONTOLOGY.md §6: byte-equal canonical IR is a
SUFFICIENT same-function proxy; these classes are NOT necessary-equal — each row is
either a future normalization candidate (with the round that must pre-register it)
or a ruled non-fusion (with the reason). New rows require a card/example citation;
removals require the normalizing round landed + census re-check Δ0.

| # | class | example / evidence | status |
|---|---|---|---|
| D1 | De Morgan / FNot placement | `NOT(A∧B)` vs `FOr(¬A,¬B)` | OPEN — normalization needs a CR-safety ruling; low corpus frequency; not scheduled |
| D2 | QAtLeast(1) ≡ QConst(1)-in-ALL-slot | slot-dependent alias | OPEN — needs executor semantics census before any fold |
| D3 | independent Seq step swaps | `Seq[A,B]` vs `Seq[B,A]` with independent A,B | RULED NON-FUSION (ontology O2): independence is board-dependent, undecidable at compile time; printed order = card identity. 0 swap pairs observed in corpus (logged prior, not exploited) |
| D4 | un-distributed `FOr[FAnd,FAnd]` | distributive-equivalent filter forms | OPEN (gate r2 A2) |
| D5 | zone twin-field bytes (pre-R0) | `zone=GRAVEYARD, zones=(HAND,)` vs `zone=HAND, zones=(GRAVEYARD,)` | CLOSED BY R0 (schema fold to single zones set) — close-check: re-census after R0 shows 0 twin pairs |
| D6 | phantom wrappers | `FAnd([x])` single-child | CLOSED BY R1a (construction flatten; corpus: exactly Dauntless Survivor + Negate) |
| D7 | same-menu/different MENU-order `Choose.options` | none observed (corpus: 29 fixed-options cards, all unique menus) | RULED REVIEW-BY-HAND (printed menu order = identity); WARN-only, no machine matcher until a pair actually occurs |
| D8 | V3′-WARN canonization class | R1a made previously-distinct byte forms identical, surfacing 4 split-seq re-designation WARNs: Garruk Unleashed, Ranger's Guile, Sure Strike, Archpriest of Iona — identical-up-to-order Selectors now byte-identical | REPORT-ONLY (V3′ WARN shipped 2026-10-19; not a defect — the WARN is the encoding correctly admitting "these two steps name the same thing") |
| D9 | empty-`FAnd` universal-truth asymmetry | `eval_filter(FAnd(()))` → `all([])` = TRUE at executor/quantity.py:658 and binding.py:220 (`all(...)` fold) but executor/replacements.py:338 folds `bool(children) and all(...)` = FALSE | OPEN — PRE-EXISTING confound registered by R1a (empty FAnd not constructible via the compiler today; any normalization round that could emit one must first unify the three folds; register-only, no R1a change) |
