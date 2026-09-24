# 2026-09-17 · 02 — B2a bucket test (`test_templates_b2a.py`)

**Context:** the 2026-09-16 handoff (T-tasks) left B2a as the only template bucket
without a test file (B1/B3/B4/B5a all had one). This session built and verified it.

## What was built
`MTG_bot/core/compiler/test_templates_b2a.py` (≈1,400 lines, new file only — no
source modified). Layout mirrors `test_templates_b3.py`:
- `TestB2aCoverage` (12 tests): 62 shapes / 66 occurrences from the bucket JSON,
  public API (45 TEMPLATES / 17 UNCOVERED), bucket labels, `_PRIORITY`, tid
  uniqueness, covered/matched counts, UNCOVERED == unmatched-set, pinned
  45-row `EXPECTED` table, PC-3 ambiguity (no sentence matches >1 template),
  fingerprint stability.
- `TestB2aTriggerEvents` (8 tests): exact event IR per trigger family
  (TurnPhaseEvent phases, ZoneChangeEvent from/to, CounterPlacedEvent,
  CreatureDiesEvent).
- `TestB2aEffectStructure` (41 tests): per-template effect IR driven end-to-end
  through the registry with concrete oracle sentences (Atom args, Selectors,
  Zones, Filters, Quantities, PtDelta, TokenSpec, Seq/OptionalEffect/Choose).

Total: **61 tests**.

## Verification method
- Ground truth: every template's IR dumped by fullmatching the bucket's concrete
  sentences against the live registry (consistent package imports), then each
  assertion in the test file was checked against that dump before writing.
- All 45 covered sentences match **exactly one** template (verified programmatically),
  so `_single_match` is safe everywhere.
- `template.build({})` is NOT a valid probe: builders read `group.group(...)`,
  so a bare dict raises `AttributeError`. Registry match with a real sentence is
  the only faithful driver (see PITFALLS).

## Findings
- **`_PRIORITY` is 50, not the 100 the spec stated.** B2a (with B5a) use 50;
  B1/B3/B4 use 100. Pinned by `test_priority_is_50_not_100`; the spec mismatch
  was reported to the owner, not "fixed" in the module.
- **`OptionalEffect.inner` is a 3-way union in B2a:** Atom (Dire Fleet, Sanctum
  of Calm Waters, Solemn Simulacrum, Goblin Arsonist, Niambi), Seq (Garruk
  emblem: SEARCH+SHUFFLE), Choose (Crypt Lurker: SACRIFICE|DISCARD).
- Kitesail Freebooter REVEAL = `Atom(REVEAL, controller=TARGET_PLAYER,
  count=QUnbounded())` — no selector (corrects an earlier note that claimed an
  "ANY-pred LIBRARY selector"; `FAtomPred` has no ANY member).
- "any one color" → `ADD_MANA(color="C")` (plain string); "up to N target" →
  `SelectorMode.TARGET + QConst(N)`; self-referential target → bare
  `FAtom(IS_SOURCE)` (not wrapped in FAnd); token color is dropped
  (`TokenSpec` has no color field — documented lossy).

## Verification
- `python -m pytest MTG_bot/core/compiler/test_templates_b2a.py -q` → **61 passed / 0 failed**.
- `pyright MTG_bot/core/compiler/test_templates_b2a.py` → **0 errors, 0 warnings**.
- `python -m pytest MTG_bot/core -q` → **571 passed** (510 baseline + 61).
- Full repo `python -m pytest -q` → 598 passed / **23 pre-existing failures**,
  all in `rule_engine` + `strategic_brain` + `test_full_system` — proven
  pre-existing by re-running with the new file removed (identical 23 failed /
  537 passed). None in `core`.

## Traps found (recorded in PITFALLS.md)
1. `assertIs` on freshly constructed frozen dataclasses (`DurationEot()`,
   `FAtom(...)`) — identity never holds; use `assertEqual`.
2. `template.build({})` group-reading builders — registry match is the only driver.
3. Mixed import paths (top-level vs package) split class identity → `KeyError`
   in `canonical_json`/`to_dict` `_TAG`.
