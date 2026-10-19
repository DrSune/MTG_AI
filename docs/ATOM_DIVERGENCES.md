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
