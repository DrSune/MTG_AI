# R1b sortdelta — Cost.parts / additional_costs / hybrid colors (2026-10-20)

Method: N-R1b simulation on `to_dict()` trees of the live compile (script
`/tmp/opencode/mk_sortdelta_r1b.py`, r0 pattern; JSON `/tmp/opencode/r1b_sortdelta.json`).
Rules: sort `Cost.parts` by canonical_json; sort `CostManaHybrid.colors`. Idempotence
0 refires, parts-multiset invariant 0 losses, 0 exceptions, M21 goldens baseline fresh (0/305 stale).

**Brief hypothesis ("all IR Costs single-part, Δ0") REFUTED by measurement.**

- Changed cards: **M21 226/305, ZNR 216/281** — every cause is `cost_parts_sort`
  (printed cost order ≠ canonical; e.g. {1}{U} folds Color-before-Generic).
  M21 wave ⇒ **226 golden re-baselines** (golden store is M21-only).
- Population: multi-part `mana_cost` **221 (M21) / 213 (ZNR)**; multi-part
  `ActivatedAbility.cost` **42 / 4**; `KickerAbility.cost` 38 (22 multi);
  `SpellAbility.additional_costs` 4 / 2; 9 Cost nodes ride `AtomArgs.pairs` (PAY payloads).
- **`CostManaHybrid` population = 0 in BOTH pools** → colors-sort is corpus-Δ0,
  dormant vocabulary, testable ONLY via constructed IR.
- Runtime exposure TODAY: `spell_cost` printed++kicker fold already builds multi-part
  planner costs — **34/40 ZNR kicker cards + M21 Goremand/Thrill reorder under canonical
  sort**: failure-string precedence and discount-consumption order for those cards are
  already printed-order functions.

Planner audit (file:line in report): production consumers only test `plan is None` —
failure vocab is diagnostic + test-pinned; payable flips ONLY through greedy
hybrid_demands (constructed {W/B}+{W/U}, pool W1B1); per-color min-clamp and generic
clamp are payable-invariant; `CostModifier.extra_deltas` (legality.py:698) is pure
additive accumulation — **commutative, SET-reclass cleared**; sacrifice ask-keys use
sorted-vocab `site_digest` (decisions.py:61, replay-fingerprint pins).

**RECOMMENDATION (decisive):** R1b is a **byte-WAVE round (226+216, 226 goldens) whose
entry-sort determinization must land IN THE SAME WAVE**, not a Δ0 hardening round —
the brief's Δ0 premise is factually dead. One wave: planner entry-sort +
construction-sort + colors-sort (they collapse into one canonicalization), with the
red-first constructed probes (failure-precedence, greedy-hybrid payable flip, {U}{X}
discount trace, sacrifice ask-order) as the falsifier battery; greedy-hybrid
payer-choice unsoundness goes to DIVERGENCES, not R1b.
