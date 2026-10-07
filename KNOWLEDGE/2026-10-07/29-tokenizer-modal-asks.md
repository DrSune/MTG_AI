# 29 — Tokenizer refinement: modal choose-counts + search-pick ONE_OF asks (2026-10-07)

Owner-approved pair from `/26` + `/27` (silent-choice fail-core: the measured
eval ceiling sat on decisions the tokenizer never exposed as asks). Both land
in `MTG_bot/core/compiler/compiler.py`; executor, query, legality and
ability_tree untouched.

## ① Modal choose-opener counts (readiness, zero pool hits)
- `_CHOOSE_TWO_RE` / `_CHOOSE_THREE_RE` openers compile "Choose two —" /
  "Choose three —" modal folds; `_CHOOSE_SPELL_COUNTS` wires the spell-option
  kind to `QConst(2)` / `QConst(3)` (one ⇒ `QConst(1)`; etb/attack kinds keep
  default 1). 2 new tests in `test_compiler.py::TestChooseOpener`.
- **Measured**: 0 of 397 corpus cards contain "Choose two/three/both" (case-
  insensitive; pool holds only "Choose one —", "Choose one or more —", and
  Necromentia's name-choice). Golden regen = 305 written, 0 diffs. Per AGENTS
  §8 this is tokenizer readiness for the next sets, not a data change.

## ② Search-pick CHOOSE → ONE_OF (the fail-core fix)
- New post-assembly pass `_one_of_search_picks` (before `CardRecord` build):
  any `Atom(Verb.SEARCH)` whose `cards` Selector is `CHOOSE ∧ QConst(1)`
  recompiles to `SelectorMode.ONE_OF` — the EXISTING 14c asking channel.
  Executor already routed ONE_OF through `_search_designation`'s
  `take_decision`; `legal_search`/`enumerate_candidates` are mode-agnostic —
  zero executor/query changes needed.
- Scope law: QConst(2) picks (Cultivate, Alpine Houndmaster) CANNOT express
  count-2 through ONE_OF — **registered grammar gap** (k-of-n ask needs the
  `/30` progress-token design; no grammar extension here). QUnbounded finds
  (Chandra Heart of Fire ×2, Necromentia) are "find all" = no decision; keep
  the stand-in.
- Single-candidate populations auto-fill via the §1.4 ONE_OF lane (identical
  outcome to the old first-of-sort stand-in); ≥2 candidates now ASK;
  exhaustion stays loud (C15).
- Goldens: 13 files changed, verified **mode-only** diffs (byte-compare after
  ONE_OF↔CHOOSE substitution, 13/13). The 13th flip = "Garruk, Unleashed"
  main-card golden (emblem SEARCH nests in the `emblem` field, not
  `abilities` — probe walks must cover CardRecord.emblem too).
- Test pins updated to the new canonical shape: `_search_atom()` helper
  (test_compiler.py), Transmogrify pin (test_compiler_c3.py), corpus-size
  pin 155→156 (test_bc_v2.py).

## Census before → after (305 goldens, `"name":"…","tag":"SelectorMode"`)
- CHOOSE **170 → 157**, ONE_OF **4 → 17** (TARGET 115, ALL 93, REST 4 fixed).
- Search-pick selectors: CHOOSE 18 → 5, ONE_OF 0 → 13; the 5 survivors =
  2×QConst(2) + 3×QUnbounded, exactly the scope law.

## Re-cert + gates (raw, this session)
- `puzzle_cert.py --rollouts 200`: items **155 → 156** (NEW item
  `empath_big_game_pick.json` — Fierce Empath's pick is now a real
  observable decision), l1_ready 16, punish_inaction 144,
  fail_registered **11 unchanged** {true-no-decision 7,
  null-degenerate-observable 3, engine-semantics-gap 1}, offenders 0,
  mean_random 0.3489. **0 changes to the 155 existing items.**
- `make_eval_split.py`: 77 fam / 32 eval / 51 eval items, train 104→**105**
  (empath item joins an existing TRAIN family; no new family assignment).
- `packrec_v2`: 111→**114 eps / 185 asks / 156 gold lines**;
  gold_rows_with_ground 78; candidate_ground 223/468.
- Gates: core **2393 passed + 2 subtests**; scenarios **373/373** (the
  pre-flight grep feared up to 23 packs needing new scripted answers —
  overcount: ZERO broke); `pytest tools/training tools/audit` **153 passed**.

## Commands
- `token-estimate`-sized probe → `.venv/bin/python` one-shots over
  `compile_pool(ingest_pool('MTG_bot/data/M21.json'), build_full_registry())`
- Golden regen: `write_goldens`/`verify_goldens` module calls (avoids
  measure_grammar --refresh-goldens side effects)
- Chain: `puzzle_cert --rollouts 200` → `make_eval_split` → `packrec_v2` →
  `run_scenarios` → `pytest tools/training tools/audit -q` → `pytest MTG_bot/core -q`
