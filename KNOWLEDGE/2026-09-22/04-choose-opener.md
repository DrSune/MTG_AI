# 2026-09-22 — choose-opener gap closed: compiler built-in + `_OptionConsumed` sentinel

Git head at measurement: (pre-choose-opener work, uncommitted) · Python 3.12.3 ·
producing command: `python tools/measure_grammar.py --set M21` ·
pool: real M21.json (pinned 305 entries / 639 sentences / 510 unique).

## The gap
Bare modal openers — `Choose one —`, `Choose one or more —`, and the
trigger-flavoured `When this creature enters, choose one —` /
`Whenever this creature attacks or blocks, choose one —` — matched no
template (B5a / B2a / B2b `UNCOVERED` rows) and left the opener itself
unparsed, blocking 7 M21 cards: `Return to Nature`, `Pestilent Haze`,
`Read the Tides`, `Destructive Tampering` (spell `Choose one —`);
`Sublime Epiphany` (spell `Choose one or more —`); `Trufflesnout`
(ETB `choose one —`); `Elder Gargaroth` (attacks-or-blocks `choose one —`).
The option bullets under each opener ("• ...") continued to compile as
ordinary sentences; only the opener header was stuck.

## Decision
- **Compiler built-in, NOT templates.** The opener is a structural wrapper
  (modal choice container), not a card-specific effect shape: it has no
  effect of its own, it only *groups* the bullets that follow it. A template
  would have to emit an incomplete ability and then have the bullets
  attached by convention — the built-in owns the whole wrap. Same reasoning
  as the phase-in-prevention and search-shuffle built-ins
  (`03-phase-in-prevention.md`).
- **Template `UNCOVERED` rows stay** (template counts remain honest: the
  shapes still match no *template*); only their reason text was updated to
  point at the built-in. The bucket tests pin shape keys, not reasons, so
  pinned counts are unchanged (B2a 8 / B2b 24 / B5a counts unchanged).

## Implementation (`compiler.py`)
- Section with doc comment: `_CHOOSE_ONE_RE` (`Choose one —`),
  `_CHOOSE_ONE_OR_MORE_RE` (`Choose one or more —`), `_CHOOSE_ETB_RE`
  (`When this creature enters, choose one —`), `_CHOOSE_ATTACK_BLOCK_RE`
  (`Whenever this creature attacks or blocks, choose one —`),
  `_OPTION_BULLET_PREFIX = "• "`.
- `_ChooseOpenerOutcome` dataclass (kind + opener sentence);
  `_choose_opener_kind()` dispatch; `_wrap_choose_openers()` runs as
  **Step 2b** in `compile_card` (after the sentence loop, before
  continuation folding): rewrites the opener slot to
  `_ChooseOpenerOutcome` and marks consumed option slots.
- `_expand_choose_opener()` — the separate-step branch in `compile_card`
  that assembles the final ability:
  - spell opener → one `SpellAbility` whose effect is
    `Choose(options=(<bullet effects>...), quantity=...)`;
  - ETB opener → `TriggeredAbility(event=ZoneChangeEvent(...entered...))`
    with the `Choose` as its effect;
  - attacks-or-blocks opener → **two** `TriggeredAbility` nodes
    (`DeclareAttackersEvent` / `DeclareBlockersEvent`) sharing one
    `Choose` (see KNOWN-GAP below).
- `_choose_etb_event()` builds the canonical entered-the-battlefield
  `ZoneChangeEvent` (same shape as the B2a/B2b `_etb_event()` helpers).
- Imports added: `Choose`, `DeclareAttackersEvent`,
  `DeclareBlockersEvent`, `QUnbounded`.

## The `None`-conflation bug (found in verification, fixed)
**Trap:** `_wrap_choose_openers` originally set consumed option slots to
`None` — the same value that means "unparsed". The post-fold `unparsed`
reconstruction (`if outcome is None`) then reported every *consumed option
bullet* as unparsed while the opener vanished from the report. 6 tests
failed (5 synthetic + 1 M21 `test_no_unparsed_opener`).
**Fix:** dedicated sentinel — `class _OptionConsumed` (`__slots__ = ()`)
with module-level `_OPTION_CONSUMED`; `_OutcomeSlot` widened to
`SentenceOutcome | _ChooseOpenerOutcome | _OptionConsumed | None`.
Verified safe pass-through at every downstream site:
- continuation pass (`outcome is None or not isinstance(outcome,
  EffectOutcome)`) → sentinel is appended to `processed` unchanged;
- backward search → falls through every `isinstance` check, loop advances
  (same net effect as the old `None`);
- separate step → matches no `isinstance` branch, skipped;
- unparsed rebuild → sentinel is not `None`, correctly excluded.
**Rule:** in `compile_card`, `is None` must mean *unparsed* and nothing
else; any "consumed/handled" state needs its own type.
Note: the legacy `_NO_OUTCOME = "__unparsed__"` marker (line ~603) is
defined but never referenced — left as-is.

## KNOWN-GAPs (documented in the section doc comment)
1. `Choose one or more —` → `Choose(quantity=QUnbounded())`: the grammar
   has no `QAtLeast(1)`, so the min-1 bound is lost (upper bound of the
   choice is correct, lower bound silently 0).
2. `attacks or blocks` → two `TriggeredAbility` nodes sharing one `Choose`
   rather than a single trigger on a composite event spec: the grammar has
   no disjunctive EventSpec. Behaviourally equivalent at execution time
   (each declaration fires the same `Choose`), but the tree shape differs
   from the printed "whenever ... attacks or blocks" single trigger.

## Verification
- `pytest MTG_bot/core/compiler/test_compiler.py` → **75 passed**
  (incl. new `TestChooseOpener` 7 synthetic + `TestChooseOpenerM21` 6
  integration, via `build_full_registry()`).
- `pytest MTG_bot/core/` → **1004 passed** (was 1004 before this file's
  tests landed; the choose-opener tests are net-new, no regressions).
- `pyright compiler.py test_compiler.py` → **0 errors, 0 warnings,
  0 informations**. (Pyright narrowing convention: `assertIsInstance`
  does not narrow — use file-local helpers `_spell/_seq/_choose/_triggered/
  _atom` or `assert isinstance(local, X)`.)
- ruff: `compiler.py` fully clean (unused `Quantity` import removed —
  `parse_pt` returns `QConst | QX | None`, `Quantity` was docstring-only);
  `test_compiler.py` retains 7 intentional TRY004 (test helpers raise
  `AssertionError`, pre-existing pattern).
- Measurement: **PC-1 186→193/305 = 0.6328** (was 0.6098),
  **PC-2 486→493/639 = 0.7715** (was 0.7606), PC-3 0 (PASS),
  PC-4 "0 diffs (305 files)" — **see harness caveat below, this is not
  evidence of stability**, PC-5 0.167 ms/card (PASS), PC-6 orphans=1
  (FAIL, pre-existing), PC-8 0.2689 (FAIL, unchanged), PC-9/PC-10 PASS.
- Golden spot-check: all 7 affected cards' goldens now contain the
  `Choose` node (verified by re-reading the rewritten files).

## PC-4 harness caveat (pre-existing, discovered while verifying)
`tools/measure_grammar.py` calls `write_goldens` (line 221) **before**
`verify_goldens` (line 222), and `write_goldens` is a full
regeneration ("Overwrites existing files — a golden refresh is always a
full regenerate, never a merge", golden.py:53). So the harness's PC-4
**cannot fail**: every measurement run silently rewrites all 305 golden
files from the current compilation, and the same-run verify trivially
passes. Additionally `MTG_bot/core/golden/M21/` is **untracked in git**
(`??` on all 305 files), so no cross-run baseline is pinned in VCS.
Consequences: (a) "PC-4 0 diffs" in `NUMBERS.md` rows carries no
information; (b) this measurement run (and the phase-in run before it)
silently refreshed the goldens — the on-disk baseline is now
post-choose-opener. The *real* drift semantics do work in
`test_golden.py` (write → tamper → `verify_goldens` detects
`content mismatch`). Owner decision needed: verify-only by default with
an explicit `--refresh-goldens` flag, and commit the golden directory.
(Discovered 2026-09-22; pre-dates this change, shipped with T5.)
- `UNCOV`/`UNCOVERED` reason text updated in `templates_b5a.py` (2 rows:
  bare spell openers), `templates_b2a.py` (1 row: ETB), `templates_b2b.py`
  (1 row: attacks-or-blocks) to point at the built-in.

## Next steps (still open for the wave)
- PC-1 / PC-2 remain far below target (0.90 / 0.95). Next triage candidates
  from the remaining unparsed queue (153→146 sentences) per
  `reports/grammar_2026-09-22.json`; the T7 honest-gap list
  (`02-t7-semantic-spot-check.md`) remains the triage input.
