# 2026-09-23 · 03 — SpellAbility.effect optional (effect-less additional-cost carriers)

**Fact:** `SpellAbility.effect` is now `Effect | None = None`, and the
compiler builds an effect-less `SpellAbility` purely to carry additional
costs for castable cards whose only relevant sentence is "As an additional
cost to cast this spell, …". The 02 orphan invariant (unconditional
`StateCorruptionError`) is superseded: it now raises only for land / token /
emblem cards; any other castable card with no `SpellAbility` gets an
effect-less carrier appended. Implemented 2026-09-23; core suite
**1039 passed**, exactly **4** of 305 goldens content-changed (re-baselined,
PC-4 **0 diffs** verified), pyright clean, ruff: no new findings.

## Why

The B5a `ac-discard` / `ac-sacrifice` templates (registered at
`templates_b5a.py` ~1223–1267; do NOT modify that file per the standing
no-touch rule) emit `AdditionalCostOutcome` for the two canonical sentences.
Four M21 cards carry them:

| Card | oracle_id | Type | Sentence | Round-3 result |
|---|---|---|---|---|
| Goremand | `0f80f061-6304-4c7b-ab53-f406385e39df` | Creature — Demon (Flying, Trample) | …sacrifice a creature. | **effect-less** `SpellAbility(CREATURE)` + `CostSacrifice` |
| Sparkhunter Masticore | `1306c72f-fc6b-470b-a95e-0364e0e30ac7` | Artifact Creature — Masticore (Protection) | …discard a card. | **effect-less** `SpellAbility(CREATURE)` + `CostDiscard` |
| Thrill of Possibility | `1cb0610b-a731-42c2-b93f-0a29f63cebf4` | Instant | …discard a card. Draw two cards. | existing `SpellAbility(INSTANT, draw 2)` gains `CostDiscard` |
| Village Rites | `365548fb-5acc-4a8a-b20b-26d28b7d029f` | Instant | …sacrifice a creature. Draw two cards. | existing `SpellAbility(INSTANT, draw 2)` gains `CostSacrifice` |

Goremand and Masticore have **no resolvable effect sentence of their own**,
so under 02's invariant they compiled without any `SpellAbility` and the
orphan check raised `StateCorruptionError`. Magic-wise both are castable
creatures: the additional cost is real, the effect is simply "enter the
battlefield as a creature" (which the grammar does not model as an `Effect`).

## Design decisions

- **Effect-optional, not a new carrier class.** `effect: Effect | None = None`
  with a guarded `__post_init__` (validate only when non-None). A separate
  `CostCarrierAbility` type would have added a new `tag` to the grammar,
  executor/encoder surface area, and fingerprint churn for zero expressive
  gain — a `SpellAbility` with `effect=None` *is* the carrier.
- **Serialization is the byte-stability proof.** `_SPECS["SpellAbility"]`
  declares the slot `opt:effect`; `_OMIT_IF_EMPTY["SpellAbility"]` covers
  `{"effect", "additional_costs"}`. `to_dict` omits an optional field when
  `None`/empty and `_decode` maps a missing `opt:` key to `None`
  (ability_tree.py ~2795–2802). Every one of the 305 pre-round-3 trees
  carries a non-None effect, so all pre-existing goldens stay byte-identical
  — confirmed by the re-baseline touching exactly 4 files.
- **Raise narrows to land/token/emblem.** Those card kinds cannot be cast,
  so an additional-cost sentence on one is genuinely corrupt oracle
  text (message: "compiled as a non-castable card (land, token, or emblem)
  with no SpellAbility to attach it to"). Any other castable card with no
  `SpellAbility` gets one appended via module-level
  `_spell_kind_from_types(types, is_creature)` (ability_tree.py convention:
  `CREATURE` when `is_creature`, else `INSTANT`-family from types).
- **Continuation-merge guards (the pyright narrowing trap).** Making
  `effect` optional invalidated a latent non-None assumption in the
  compiler's continuation merge:
  1. the **backward merge-target search** now skips effect-less
     `SpellAbility` (a pure cost carrier has nothing to merge into) — it
     only stops on Static/Activated/Triggered or a `SpellAbility` with
     `effect is not None`;
  2. the **merge branch** guards `if ab.effect is None: continue` (marked
     unreachable by a comment — the search cannot select it) before
     `merge(ab.effect, outcome.effect)`.
  No `assert` is used anywhere in production code (zero production asserts
  in the codebase — checked compiler.py and ability_tree.py); the guard is a
  plain branch matching the existing non-mergeable fall-through.
- **Test helpers widened, not special-cased.** `_seq` / `_choose` / `_atom`
  in test_compiler.py now accept `Effect | None`; their runtime
  `isinstance` guards raise `AssertionError` on `None` (correct: a test
  expecting a `Seq`/`Choose`/`Atom` must fail when handed an effect-less
  ability). One signature edit per helper fixed all 9 `ab.effect`
  call-site pyright errors at once.

## What changed (4 files)

- `ability_tree.py` — `SpellAbility.effect: Effect | None = None`;
  guarded `__post_init__`; `_SPECS` slot `("effect", "opt:effect")`;
  `_OMIT_IF_EMPTY["SpellAbility"] = frozenset({"effect",
  "additional_costs"})`.
- `compiler/compiler.py` — module-level `_spell_kind_from_types`;
  rewritten additional-cost block (land/token/emblem raise; else append
  effect-less `SpellAbility`); continuation-merge search + merge-branch
  guards above.
- `test_ability_tree_r3.py` (**new**) — 15 tests: 4 pre-round-3 pinned
  fingerprints byte-stable; 3 new effect-less round-trip pins
  (`to_dict` omits `"effect"`, keeps `"additional_costs"`; bare carrier =
  `{"tag","kind"}` only); explicit-`None` == default; `from_dict` with
  missing `opt:` key → `None` and missing `tup:` key → `()`; 4 rejection
  cases (str effect, `Cost` as effect, wrong tag `{"tag":"Cost"}`,
  non-dict payload). Imports the t3r2 builders (`T2._spell_base`,
  `T2._draw_one`, `T2._spell_additional_sacrifice`,
  `T2._spell_additional_discard_life`) so pins share one construction
  source. Note: module-level `at.from_dict(tag, d)` takes **two** args.
- `compiler/test_compiler.py` — `_seq`/`_choose`/`_atom` signatures
  widened to `Effect | None`; `TestAdditionalCost.
  test_creature_discard_additional_cost_no_effect` (synthetic Creature/Demon:
  Flying + discard additional cost → exactly one `SpellAbility`,
  `CREATURE`, `effect is None`, one discard cost); new
  `TestAdditionalCostM21` (5 tests over the real pool: the 4 cards present;
  exactly one `SpellAbility` with one additional cost each; the 2 creatures
  effect-less; the 2 instants keep their draw effect; no
  "As an additional cost" sentence left unparsed).

## Pinned fingerprints (repo .venv, round 3)

| Tree | Value |
|---|---|
| `spell_instant_draw_nocost` (pre-r3, `T2._spell_base()`) | `e4d6897f8542141dc66d4d2ca1356746d99bf5587535a78019b952619570905d` |
| `spell_creature_draw_nocost` (pre-r3) | `47279b0494954e142776afb42e40ea65bf078ea145345c15d8f07417c502eb99` |
| `spell_sacrifice_cost` (pre-r3, `T2._spell_additional_sacrifice()`) | `c41e8d568c43c3d202294180e53778cf4a2c1b40a4af5b833229df09c8c41467` |
| `spell_discard_life_costs` (pre-r3, `T2._spell_additional_discard_life()`) | `59fb3edab4318e2dfd21018f41fd0212da75c1de8b80f31a50519379ae13962e` |
| `spell_effectless_sacrifice` (**new**, `SpellAbility(CREATURE, None, Cost(CostSacrifice creature))`) | `29429f3da989de31a9cf1a32e7a7b8ed2dd5b9681ff8ee5ce336a633f025ef27` |
| `spell_effectless_discard` (**new**, discard-from-hand cost) | `92d0ef7eeeb74f1bcee6d465c511f42c1f3d4d11dde94c1c435d4537478e52d2` |
| `spell_effectless_bare` (**new**, `SpellAbility(CREATURE, None)` == `SpellAbility(CREATURE)`) | `4ab74b3cff39541af5ef554a5ffefdc68e1a506645aeb726b800c03eadb120b8` |

Effect-less round-trips verified: dict keys `["additional_costs","kind","tag"]`
(cost carrier) / `["kind","tag"]` (bare).

## Verification (2026-09-23, repo .venv)

- `pytest MTG_bot/core -q` → **1039 passed / 0 failed** (was 1038/1 pre-
  re-baseline; the single failure was the stale golden baseline, now
  refreshed)
- `pytest MTG_bot/core/compiler/test_compiler.py MTG_bot/core/
  test_ability_tree_r3.py -q` → **104 passed** (89 + 15)
- `python tools/measure_grammar.py --set M21` → **PC-4 0 diffs (305 files,
  verified)**; PC-1 0.6492, PC-2 0.7793, PC-6 orphans=1, PC-8 0.2689
  (unchanged — coverage measures sentence matching, which the B5a patterns
  already provided; the hook only changes card assembly)
- Golden diff audit (staged baseline vs working tree, structural compare):
  exactly 4 files differ, each in the `abilities` key ONLY — every other
  top-level key byte-identical; pre-existing abilities inside each file
  byte-identical (Goremand's misparsed `TriggeredAbility` preserved — see
  Known follow-ups)
- pyright (background LSP): 0 errors on all 4 touched files (no pyright CLI
  in this environment — diagnostics arrive via the LSP on edit)
- `ruff format --check` on the 4 files → already formatted; `ruff check`
  → 59 findings, **all pre-existing** (ability_tree.py 52 incl. 5 TRY004
  `ValueError`-on-`isinstance` lines adjacent to `SpellAbility` — the
  new guard's `raise` at the compound `is not None and not _is_effect(...)`
  condition is NOT flagged; test_compiler.py 7 = the documented intentional
  `AssertionError` narrowing helpers). New file `test_ability_tree_r3.py`
  and `compiler.py`: 0 findings each.

## Known follow-ups

1. **Goremand retains a pre-existing misparsed `TriggeredAbility`**
   (byte-identical across the re-baseline): a trigger on
   `ZoneChangeEvent(ANY→BATTLEFIELD-YOU)` whose effect is
   `EachPlayer(ALL_OPPONENTS) → SACRIFICE 1 creature you control`. It
   predates round 3 (it is in the committed baseline; PC-4 verified zero
   diff against it). With the B5a template registered, the same sentence
   now feeds BOTH that (wrong) trigger and the correct `CostSacrifice`.
   Fixing it is a separate template-priority/shape task — out of scope
   here; do not let the double-parse silence the trigger fix.
2. Two of the four B5a additional-cost queue entries flagged in 01 remain
   unregistered (only `ac-discard` / `ac-sacrifice` landed); they follow
   the same pattern now that the effect-less carrier exists.
3. Executor: an effect-less `SpellAbility` has nothing to resolve — T6
   executor design should treat `effect is None` as "cast = enter the
   battlefield / resolve as a no-op spell with extra costs paid".
