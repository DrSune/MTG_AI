# 108 — ZND-2f BackFace compile half LANDED (spec: /106 SPEC-AMENDED)

Date: 2026-10-18 late / verified 2026-10-19. All gates below EXECUTED.

## What landed
- `BackFace(face_name, abilities)` Ability node (ability_tree.py): tag-only
  serializer visibility, `_OMIT_IF_EMPTY` (empty face = `{"tag","face_name"}`),
  `__post_init__` validation, added to `Ability` union + all tag/spec tables.
  No prompt-lane change, no play-lane change (spec §4 loud-no-op withdrawn).
- `walk(node, *, skip=())`: yields the skipped node, never descends — the
  single exclusion primitive for every verdict fold.
- Compiler face lane: `compile_card` folds `RawCard.back_face` via
  `_as_single_faced` + recursive `compile_card` (same registry, tolerant
  machinery); BackFace appended LAST in `abilities`; face residue goes to
  the NEW additive `CompileResult.back_face_unparsed` (front `unparsed`
  stays front-only → PC-1 formula untouched, /96 law).
- Phantom defenses (all pin-tested): `games.compile_supply` produces_mana
  fold, `compiler.compile_card` engine_support fold use `skip=BackFace`;
  `coverage.measure_pool` verb/target folds are front-only, face verbs are
  TAGGED in `backface_summary["verb_histogram"]` + `cards_face_whole`.

## Numbers (cmds: tools/measure_grammar.py --set ZNR / --set M21; 2026-10-18 23:52)
- ZNR PC-2 **278/726 → 339/726** (exactly +61: 25 enters-tapped + 36
  add-mana, TRUTH LAW honored). PC-1 **68/282 unchanged**; PC-3 0;
  PC-6 orphans=30 share 0.1667 unchanged (face ADD_MANA tagged, NOT merged);
  PC-8 29/282 unchanged; PC-9 stable; double-run diff = timestamp + PC-5 only.
- ZNR face census: **36** faces, **71** sentences, **61** covered,
  **10** residual (pay-3-life pair ×5 → BFACE register rows visible),
  **31** faces compile whole; face-whole AND front-clean cards = 12.
- M21 FULL INVARIANCE: PC-1 305/305, PC-2 639/639, PC-4 0 diffs,
  PC-6 orphans=4 share 0.1265, PC-8 98/305, PC-9 stable; report
  byte-identical to pre-wave copy except timestamp + moved git HEAD;
  no `backface` key (M21 census 0).
- Corpus re-encode identity: **diff 0** across all 19 episode/eps corpora
  (v1+v2 lanes) — /tmp/opencode corpus_before.txt vs after.
- `pytest MTG_bot/core tools -q` = **2877 passed, 0 failed** (+36 subtests).
- New file `MTG_bot/core/compiler/test_backface.py`: **17 tests** (node
  shapes, TRUTH-LAW residual, serializer round-trip/omit/validation,
  walk-skip, both-direction invariance of both folds, source pins
  `skip=BackFace` ×4, coverage tagging, ZNR census pins 36/61/10/31).
- ruff per-file delta ≤ 0 everywhere touched; pyright **0 errors** on all
  six touched files; new test file ruff-clean.

## Deviations / discoveries (all verified)
1. **Gap-card honesty regression, caught by the stale /93 tests**: my first
   measure_pool rewrite ran the face census inside the `results` loop, so a
   shape-gap card (no compile result) silently lost ALL its face sentences
   from the denominator and register — violating the /93 honesty law the
   docstring still promised. Fixed: gap cards contribute every face sentence
   as a BFACE residue row. ZNR/M21 numbers unaffected (both have 0 face-gap
   cards); test_gap_card_backface_still_counted re-passed unchanged.
2. Three /93 TestBackFaceCensus expectations were superseded-by-/106 and
   updated (compiler now READS faces: a template-matchable face sentence is
   covered, no longer a forced row; summary dict carries the tagged keys).
3. `compile_pool` is strict-lane (raises on star-P/T front cards — ZNR:
   Archpriest of Nighthawk-class fronts; ZNR *faces* carry no star P/T,
   verified against the pool file); counterfactual test replays via
   tolerant per-card compile.
4. Removed a needless `# noqa: TRY004` from my BackFace `__post_init__`
   (RUF100: rule doesn't fire there) — ability_tree ruff count now BELOW
   its pre-wave baseline.

## Files touched
ability_tree.py, compiler/compiler.py, compiler/coverage.py,
executor/games.py, compiler/test_backface.py (new),
compiler/test_coverage.py (3 stale /93 tests → /106 semantics).

## Residual (next waves)
- 10 pay-3-life sentences → ZND-2f2 (register BFACE rows).
- Face playability (engine reading BackFace) — owner-gated Type-1 wave;
  every skip=BackFace fold is the documented re-entry point.
