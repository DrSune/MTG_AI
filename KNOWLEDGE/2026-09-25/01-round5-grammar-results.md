# 2026-09-25 · 01 — Grammar round 5 (replacement/"instead"): grammar-phase results

Status: DONE — grammar phase implemented 2026-09-25; binding spec in
`2026-09-24/07-round5-replacement-decision.md`. The template-batch phase
(9 rows / 8 cards via `AbilityOutcome`) is NOT yet started — a separate
follow-up per doc-07.

## What landed (ability_tree.py, additive-only; omit-if-None ⇒ pre-batch
goldens byte-stable)

Four items, per doc-07:
1. **R5-1** `FAtomPred.WAS_CAST_THIS_TURN` — slots `{who}` (required).
   Used negated: Containment Priest `FNot(FAtom(WAS_CAST_THIS_TURN,
   who=ANY))`. Distinct predicate from R4-4 `CAST_THIS_TURN_FROM` (no zone
   slot) — PITFALLS: one predicate = one rule concept, no duplicates.
2. **R5-2** `CounterPlacedEvent.count: Quantity | None = None` + `_SPECS`
   row (`"opt:quantity"`) + `_OMIT_IF_EMPTY["CounterPlacedEvent"]={count}`
   + validation (Quantity-or-None, mirror `CastSpellEvent.ordinal`).
   **New `QPropField.COUNTER_COUNT`** member — event-only; `QProp.__post_init__`
   now requires `referent == "event"` for BOTH `AMOUNT` and `COUNTER_COUNT`.
   "that many" = `QProp(referent="event", field=COUNTER_COUNT)`.
3. **R5-3** `CostModifier.controller_ref: ControllerRef` →
   `ControllerRef | Selector`. `_SPECS` conv → dual `controller_ref_or_selector`
   (tagged Selector dict → `Selector`; else enum decode). Convention C7
   (binding): a Selector ref means *the controller of the selected object*;
   the modifier applies to costs that controller pays for the filtered
   object, **including `unless` payments** (Lofty Denial s2).
4. **R5-4** `FAtomPred.NOT_FIRST_DRAW_THIS_STEP` — slots `{who}` (required).
   Teferi's Ageless Insight `FAtom(NOT_FIRST_DRAW_THIS_STEP, who=YOU)`.

`_FATOM_RULES`: both new predicates get a row with `who` required.
Module docstring updated with the round-5 bullet.

## Verification (orchestrator-repeated)

- core suite: post-round-4 1217 → **1269** (`test_ability_tree_r6.py`,
  +52 cases).
- golden refresh (`--set M21 --refresh-goldens`): PC-4 golden_stability
  **0 diffs** (305 refreshed); `git status --short MTG_bot/core/golden/ |
  grep -c '^ M'` = **0** (byte-stable).
- PC-3 ambiguity 0; PC-9 determinism stable; PC-5 latency p99 0.189 ms
  (pass < 50); PC-10 null-test pass.
- **ruff delta vs HEAD = 0** (gate: non-increasing). ability_tree.py
  53 → 53 with identical per-rule breakdown (49 TRY004 / 2 F541 / 1 SIM114 /
  1 RUF100) at both HEAD and working tree (measured via
  `git show HEAD:...` + `ruff check --statistics`). The one SIM101 the
  R5-3 union-widening transiently introduced (two `isinstance` calls) was
  merged to `isinstance(x, (ControllerRef, Selector))`. Every remaining
  non-TRY004 finding pre-dates round 5 (`git blame` → 7204ff36, 2026-09-16).
  New `test_ability_tree_r6.py`: **0** findings.
- report `reports/grammar_2026-09-25.json`; `NUMBERS.md` row appended.

failed_targets unchanged from post-round-4: PC-1, PC-2, PC-6, PC-8
(stretch/owner-tracked coverage — not grammar-phase-gated).

## Byte-stability trap (learned + hit during validation)

`FAtom.to_dict` omits ONLY `zone`/`from_zone`/`to_zone` when `None`
(`_OMIT_IF_EMPTY`). The other slots (`who`, `count`, `string_value`,
`color`, `colors`, `counter_kind`, `keyword`, `inner_filter`) serialize
their null/empty defaults. So a bare
`FAtom(WAS_CAST_THIS_TURN, who=ControllerRef.ANY)` serializes with
`"count": None` PRESENT. The r6 pin therefore asserts
`d["who"] == {"tag": "ControllerRef", "name": "ANY"}`, `"zone" not in d`,
`d["count"] is None`. (The first draft asserted `"count" not in d` — wrong,
and failed 2 cases.) Future FAtom pins should assert presence-with-null for
the non-zone slots, absence for the zone slots.

## Residual queue / next

Grammar phase done; all four doc-07 grammar items verified. Next is the
doc-07 **template batch** (9 rows / 8 cards, conventions C6/C8), then the
round-6 queue (conditional statics, anaphora, flip-follow-on, recursive
text, singletons).
