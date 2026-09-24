# 2026-09-22 — PHASE_IN gap closed: compiler built-in + mandatory continuation merge

Git head at measurement: (pre-phase-in work, uncommitted) · Python 3.12.3 ·
producing command: `python tools/measure_grammar.py --set M21` ·
pool: real M21.json (pinned 305 entries / 639 sentences / 510 unique).

## The gap
`Teferi, Timeless Voyager` (oracle `7240037f-ddea-425e-9824-866e2bb0dc84`,
Planeswalker) [−8] prints two sentences:

1. "Each creature target opponent controls phases out." — covered by the B5c
   loyalty phase-out template.
2. "Until the end of your next turn, they can't phase in." — NO template
   matched (B5c SHAPES row stays UNCOV at template level, mirroring the B5b
   search-shuffle convention). The parenthetical rule reminder
   "(Treat them and anything attached to them as though they don't exist.)"
   is consumed by `_is_rule_reminder` and is not a blocker.

This was the **sole** remaining Teferi blocker in `unparsed_queue` and the only
card whose single blocking sentence was a pure boilerplate fragment.

## Decision (resolving T7 item 5, `02-t7-semantic-spot-check.md` line 93)
- **Compiler built-in, NOT a B5c template.** The sentence is a generic
  boilerplate fragment identical to the search-shuffle built-in: no template
  should own it. The B5c `UNCOVERED` register row stays (reason updated to
  "Phase-in prevention (compiler built-in; merged into preceding loyalty
  activation)") so template counts remain honest (73 templates / 74 covered /
  17 uncovered — unchanged).
- **Grammar fully supported — NO new grammar needed.** All constructs existed
  from T3 round 2: `DurationUntilNextTurn`, `ZoneChangeEvent`,
  `FAtom(FAtomPred.CONTROLLER_IS)`, `Verb.PREVENT_EFFECT` role
  (condition+event required; controller+duration optional), `CostLoyalty`.
  The canonical composition (from `test_ability_tree_t3r2.py:194-225`) is:
  `PREVENT_EFFECT(condition=FAtom(CONTROLLER_IS, who=OPPONENT),
  event=ZoneChangeEvent(COMMAND→BATTLEFIELD, controller=OPPONENT),
  duration=DurationUntilNextTurn())`.

## Why a mandatory merge (the key design choice)
Three options were rejected/kept:
- **Standalone `EffectOutcome`** → wrong container: assembly folds a lone
  effect into a `SpellAbility(PLANESWALKER)` as an *inherent* planeswalker
  effect, not part of the [−8] activation. Rejected.
- **Default continuation merge** (`_append_optional_to_seq`) → wrong semantics:
  wraps the mandatory effect in `OptionalEffect`, mis-modelling a guaranteed
  effect as optional. Rejected.
- **Mandatory-append** (`_append_mandatory_to_seq`, NEW) → correct IR: appends
  the effect bare (no `OptionalEffect` wrap) into the previous effect's `Seq`.
  This mirrors the existing `_merge_search_shuffle` special-case precedent
  (a second compiler-built-in with non-default merge semantics). **Kept.**

## Implementation (`compiler.py`)
- Imports: added `DurationUntilNextTurn`, `FAtom`, `FAtomPred`,
  `ZoneChangeEvent` from `ability_tree`.
- `_PHASE_IN_PREVENT_RE` — anchors the exact boilerplate sentence.
- `_phase_in_prevention_effect()` — returns the canonical PREVENT_EFFECT atom.
- Sentence loop **Step 1c** (after search-shuffle Step 1b): emits
  `EffectOutcome(effect=_phase_in_prevention_effect())`.
- Continuation pass guard: `if not _is_continuation(sentence) and not
  _PHASE_IN_PREVENT_RE.match(sentence): continue` — the phase-in sentence is
  NOT a continuation prefix ("Until" is not in `_CONTINUATION_PREFIXES`), so
  it is forced through the merge path.
- Merge selection: `elif _PHASE_IN_PREVENT_RE.match(sentence): merge =
  _append_mandatory_to_seq`.
- Orphan fallback (no previous effect): appended **bare** (no
  `OptionalEffect` wrap) — a phase-in prevention is mandatory even in
  isolation.
- `_append_mandatory_to_seq(effect, inner)` — appends `inner` to `effect`'s
  `Seq.steps`, or wraps a non-`Seq` into a two-step `Seq`. Sibling of
  `_append_optional_to_seq` but without the `OptionalEffect` wrap.

## Verification
- **Pyright** on `compiler.py` and `test_compiler.py`: 0 errors / 0 warnings /
  0 informations.
- **4 new tests** in `TestContinuation` (`test_compiler.py`):
  1. `test_phase_in_merges_into_activated_ability` — the real Teferi [−8]
     shape: a `CostLoyalty(-8)` `ActivatedAbility` whose effect becomes
     `Seq(steps=(phase_out, phase_in))`. (Requires `loyalty_raw="8"` on the
     synthetic Planeswalker or `CardRecord.__post_init__` raises.)
  2. `test_phase_in_merges_into_spell_effect` — Instant predecessor →
     `Seq(steps=(phase_out, phase_in))`.
  3. `test_phase_in_appends_to_existing_seq` — predecessor already a `Seq` →
     phase-in lands as the final step.
  4. `test_phase_in_without_previous_effect` — orphan → effect is the bare
     `_phase_in_atom()` (NOT wrapped in `OptionalEffect`/`Seq`).
- **Compiler suite:** 58 → 62 passed (4 new).
- **Core suite:** 987 → **991 passed** (no regressions).
- **`templates_b5c.py`:** only the `UNCOVERED` reason string changed; template
  counts / SHAPES unchanged. **`test_templates_b5c.py`:** NO changes needed
  (phase-in key stays in `UNCOVERED`; the 3rd tuple element is the template id,
  not the reason; `len(UNCOVERED)` still pinned at 17).

## Measured delta — see NUMBERS.md row `2026-09-22 (phase-in)`
- **PC-1 card_coverage: 185/305 → 186/305 (0.6098)** — Teferi, Timeless
  Voyager flips to fully covered. Still FAIL vs ≥0.90.
- **PC-2 sentence_coverage: 485/639 → 486/639 (0.7606)** — the phase-in
  sentence is now parsed. Still FAIL vs ≥0.95.
- **PC-4 golden_stability: 0 diffs (305 files) PASS** — the [−8] golden was
  regenerated with the merged `Seq`; self-healed as designed.
- PC-3 / PC-5 / PC-6 / PC-8 / PC-9 / PC-10 unchanged
  (PC-6 orphans=1, max share ADD_MANA 0.1137; PC-8 0.2689; PC-5 0.165
  ms/card).
- Remaining FAILED TARGETS: PC-1, PC-2, PC-6, PC-8.

## Next (b2b/b5b/b5c sweep continues)
The next unparsed_queue blockers are *not* boilerplate fragments — they are
genuine grammar gaps (additional-cast-cost, cost-reduction, "this turn"
triggers, keyword rule-reminder lines, "instead" conditionals, math
fragments). The three remaining "Teferi" queue entries are **different cards**
(`Teferi's Ageless Insight`, `Historian of Zhalfir`, `Teferi, Master of
Time`) with their own distinct blockers — not part of this task.
