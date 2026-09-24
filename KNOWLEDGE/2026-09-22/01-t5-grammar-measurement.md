# 2026-09-22 — T5: Phase-1 grammar measurement harness (shipped + measured state)

Git head at measurement: `e1c5a43b4610e1ff6c8766bfc0bfff1684ad7cdc` · Python 3.12.3 ·
generated 2026-09-22T07:04:34+02:00 · pool: real M21.json (pinned 305 entries / 639 sentences / 510 unique).

## What shipped (new files only — no existing source modified)
- `MTG_bot/core/compiler/coverage.py` — pinned denominators (fail-loud `ValueError` on drift),
  `build_full_registry()` (all 8 buckets), `measure_pool()` single-pass measurement
  (PC-1/2/3/6/8), `UnparsedEntry` / `AmbiguityEntry` / `CoverageReport` (frozen, `to_json()`).
- `MTG_bot/core/compiler/golden.py` — PC-4 golden write/verify (one `<oracle_id>.json` per
  entry, exact `canonical_json` bytes, no trailing newline) and PC-9 `fingerprint_multiset`.
- `tools/measure_grammar.py` — CLI (`--set`, `--runs`): p99 latency via nearest-rank over ≥3
  runs (PC-5), determinism reused from the latency runs (PC-9), PC-7 reported as
  `pending_executor` (deferred to T6, `pass: null`, excluded from exit code), PC-10
  bidirectional null test on in-memory synthetic cards only ("Draw a card." → 100%,
  planted "Nobody understands this." → 0% with exact queue), writes
  `reports/grammar_<date>.json`, appends the `NUMBERS.md` row, exits 0/1 on failed targets.
- `MTG_bot/core/compiler/test_coverage.py` + `test_golden.py` — 18 tests; core suite 908 → 926 passed.

## Measured state — see NUMBERS.md row `2026-09-22 (T5)` for the dated table
- PASS: PC-3 ambiguity (0), PC-4 golden stability (0 diffs, 305 files), PC-5 latency
  (**0.163 ms/card** p99, ~300× under the <50 target), PC-9 determinism, PC-10 null test.
- FAIL: PC-1 card_coverage **0.577** (176/305, target ≥0.90) · PC-2 sentence_coverage
  **0.743** (475/639, target ≥0.95) · PC-6 vocabulary (orphan verb **PHASE_IN** — defined,
  used by no M21 template; max share 0.1168 ADD_MANA passes <0.20) · PC-8 targetable
  **0.269** (82/305, target ≥0.40).
- DEFERRED: PC-7 executor coverage → T6 (`core/executor.py`).

## Interpretation — failures are genuine grammar gaps, verified not instrument artifacts
- The 164 unparsed sentences / 129 affected entries split by bucket hint:
  122 spell-effect, 35 triggered, 6 activated, 1 static. Dominant gap families (from the
  report's `unparsed_queue`): additional-cast-cost sentences ("As an additional cost to
  cast this spell, …", repeated sacrifice/discard variants), cost reduction, triggers
  referencing "this turn", loyalty activation costs, whole keyword rule-reminder lines
  (no internal periods → one unparseable "sentence", e.g. "Flying, first strike,
  lifelink, protection from Demons and from Dragons"), "instead" conditional effects,
  "Round up each time." math fragments.
- PC-8 82/305 was independently re-verified with a direct `Selector`/`SelectorMode.TARGET`
  walk over the compiled pool (exact match; textless cards correctly have none).
  Note: PC-8 is *depressed by* the PC-1 gap — targeting sentences that fail to parse
  produce no tree, so those cards don't count. Re-measure after gap closure before
  concluding the pre-registered ≥0.40 target is unachievable.

## Artifacts
- `MTG_bot/core/golden/M21/` — 305 golden files (PC-4 baseline; refresh only via the tool).
- `reports/grammar_2026-09-22.json` — full report incl. complete unparsed queue + pool_stats.
- `NUMBERS.md` — row appended at top by the tool (headline numbers).

## Handoff to next tasks
1. Gap closure to lift PC-1/PC-2: the additional-cast-cost family is the largest
   single addressable chunk (B5 hint family); rule-reminder line handling is the next
   decision point (strip vs. per-ability templates).
2. PC-6: wire a PHASE_IN template (e.g. B5 "comes into play tapped" family) or mark the
   verb deprecated in the vocabulary ledger.
3. Re-run `python tools/measure_grammar.py` after every template change — the pinned
   denominators make silent rescaling impossible.
