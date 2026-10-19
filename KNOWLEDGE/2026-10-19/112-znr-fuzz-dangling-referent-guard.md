# 112 — ZNR fuzz crashes root-caused: dangling-anaphora template folds + engine lane guard (r24)

Date: 2026-10-19. Wave: /109 fuzz follow-up. Files touched:
`MTG_bot/core/executor/{__init__,selectors,stack,binding}.py` +
`MTG_bot/core/test_executor_dangling_referent.py` (new). NO compiler/
ability_tree edits (sibling wave owns those; root causes below are
PROPOSALS for that wave).

## Headline numbers (executed)
- Baseline (/109): `--games 40` → 3 crashes / 7.5% / 2 signatures
  (`NotImplementedError@selectors.py:364` 'result' ×2, `ValueError@
  selectors.py:347` 'target' ×1).
- After fix: `--games 60` → **crashed=1 (1.7%), signatures=1**; BOTH
  original signatures gone. Repro seeds 5/23/28 all print
  `no crash — … game over`. Command:
  `.venv/bin/python tools/eval/znr_engine_smoke.py --games 60`
  (json `reports/znr_engine_smoke_2026-10-19.json`).
- Remaining crash (seed 10) is a DIFFERENT class, previously masked:
  `NotImplementedError@quantity.py:1585` —
  `filter pred HAS_KICKER not implemented (12c query surface)` raised in
  `legality.enumerate_candidates` → `eval_filter`. Producer card:
  **Murasa Sproutling** ("return target card with a kicker ability from
  your graveyard to your hand" — compiler
  `templates_b6._return_kicker_card_hand` emits `FAtom(HAS_KICKER)` as a
  TARGET-selector identity filter; the quantity/query surface has no
  evaluator for it). Honest ledger: fuzz crash-rate is 1/60 until the
  query surface implements HAS_KICKER (candidate has a KickerAbility in
  its CardRecord — mechanical, one `_eval_atom` arm).
- Tests: `test_executor_dangling_referent.py` 9/9; full
  `pytest MTG_bot/core -q` → **2660 passed, 36 subtests**; packs
  **405/405**; ruff Δ0 vs HEAD (executor files byte-equal violation
  sets; test file clean); pyright 0 new (binding.py:737 event-union
  noise pre-exists at HEAD).

## Crash 1 — Acquisitions Expert (2 fuzz hits, seeds 5/28)
- Text: s1 "When ~ enters, reveal the top three cards of your library.
  You may put an instant or permanent card revealed this way into your
  hand." s2 "If you control four or more Landwalk…, put … into your
  hand instead" (party qty), s3 "That player discards that card."
- Fold: `templates_b5b.py` tid `B5b-that-player-discards` (table ~3256,
  builder `_build_that_player_discards_that_card` ~1543) compiles s3 as
  MOVE_ZONE `cards = Selector(referent='result')` — a register READ whose
  producers (s1 reveal / s2 put) are UNPARSED sentences → no producer
  atom ever writes 'result' → `resolve_selector` raise (selectors.py,
  "selector referent 'result' has no register").
- Should fold: the whole trigger only when an antecedent producer
  sentence compiled; else refuse (stamp unsupported). Proposal for the
  compiler wave: one-line precondition in the builder — fold only if the
  card's parsed-sentence set contains the 'result' producer, i.e. gate
  `B5b-that-player-discards` on the same `saw_unparsed` ledger as r23a
  statics. Expected tree after gate: card is coverage-visible
  `engine_supported=False`, no dangling MOVE_ZONE compiled.

## Crash 2 — Shell Shield (1 fuzz hit, seed 23)
- Text: "Target creature you control gets +0/+3 until end of turn.
  Kicker {1} — Target creature you control gets +0/+3 …" (s2 = kicker arm
  STANDALONE; s1 base UNPARSED at fold time).
- Fold: `compiler.py` kicker fold (~1547–1600, the `saw_unparsed_base`
  law) legitimately keeps the kicker arm when the base is unparsed, and
  the arm's Selector compiles mode=CHOOSE referent='target'. But
  `query.spell_target_slots` (~859) harvests designation slots only from
  TARGET-mode selectors → policy offers NO designation, cast proceeds,
  the kicked branch reads `bindings['target']` → ValueError ("'target'
  referent has no target binding").
- Fix NOT taken: deriving a designation slot from the anaphora read
  would populate zone ANY / no "you control" — degradation, not
  flagging. Compiler-wave proposal: in the kicker fold, if the arm reads
  referent 'target' and NO TARGET-mode selector survived into the record
  (base unparsed), refuse the standalone fold (stamp unsupported) rather
  than compiling an unclosable anaphora.

## Engine lane change (this wave — "make the lane honest"; r24a REVISED by adversarial gate, see below)
- Convention mirrors r23a unparseable-statics: raw `_run_effect` KEEPS
  raising (unit contract, C15 "unset reads RAISE" byte-identical);
  LIVE-GAME lanes route through `Executor._run_guarded_effect(effect,
  ctx, lane)`. Guarded lanes: stack.py `cast` effect + aura (2),
  `cast_card` effect + aura (2), and — found by the 60-game rerun, added
  after the first pass — the TRIGGER-firing lane `binding._fire`
  (binding.py:~1266). The execute() op lane and `_run_effect` internals
  stay raw on purpose.

## r24a — COMMIT-NO-GO fixes (adversarial gate, executed 2026-10-19)
1. **BLOCKER 1 (substring matching).** `/111` caught by `mark in
   str(exc)`: any unrelated error merely CONTAINING a mark was silenced
   into the ledger, and mark #1 co-matched `quantity._referent_handle`'s
   QProp refusal (quantity.py:396) — the "exactly two" claim was false
   as coded. Now: dedicated types `ReferentAbsentBindingError
   (ReferentAbsentError, ValueError)` / `ReferentAbsentRegisterError
   (ReferentAbsentError, NotImplementedError)` raised ONLY at the two
   `resolve_selector` sites; predicate = isinstance AND BYTE-EXACT site
   message. QProp and every look-alike PROPAGATE (pinned E2E: patched
   HANDLERS raise containing both marks kills the cast, sink empty;
   QProp CMC-amount cast kills too).
2. **MAJOR 2 (mid-step sibling loss).** Guard now runs a TOP-LEVEL `Seq`
   step-by-step (CR 609.7 do-as-much-as-possible): Seq(TAP, dangling
   MOVE_ZONE, DAMAGE) keeps the damage. Honest boundary pinned:
   granularity is TOP-level only — a nested inner Seq failing mid-way
   is skipped AT WHOLE-STEP granularity (inner tail lost with it); moot
   once the fold gates land. The `search_partition` (r19a) context is
   reproduced in the guarded loop via shared `_partition_step` helper.
3. **MAJOR 3 (honesty of wording).** The ledger is **queryable,
   surfacing PENDING** — zero consumers; cards stay
   `engine_supported=True` (fold-gate follow-up below, not papered).
   All docstrings/note reworded from "coverage-visible".
4. **MINOR (dedupe collapse).** `unresolved_effect_counts: dict[str,
   int]` per key — two distinct same-message dangling atoms now read as
   one key × count 2 (pinned).

## r24a numbers (executed, same commands as above)
- `pytest MTG_bot/core -q`: **2665 passed + 36 subtests** (test file
  now 14 pins: predicate typed+exact, look-alike E2E propagation, QProp
  propagation, mid-step tail executes, nested-Seq boundary, per-key
  counts).
- Packs **408/408** (sibling party packs tracked clean, no flake split).
- Fuzz `--games 60`: crashed=1 (1.7%), **1 signature =
  HAS_KICKER@quantity.py:1585 (residual, different class, follow-up #1);
  the original two signatures: 0.**
- ruff: violation set ⊆ HEAD's (`__init__.py` N999+TRY004×3; its HEAD
  I001 also auto-fixed away) — Δ0 new. pyright 0 new.
- Tests pin: cast completes with mis-shaped half skipped (zone/damage
  untouched), dedupe, kicked-vs-unkicked gating (unkicked never flags),
  producer-PRESENT Seq(TAP→MOVE_ZONE 'result') still resolves through
  the guarded lane (no degradation), non-marker refusals stay loud
  (PLAYER-zone MOVE_ZONE), predicate matches only the two marks, and the
  trigger-lane twin (BindingCase ETB fires, enter stands, one flag).

## Follow-ups (ledger)
1. quantity `_eval_atom`: implement `HAS_KICKER` (12c query surface) —
   last fuzz crash, Murasa Sproutling.
2. Compiler wave: the two fold gates above make `unresolved_effects`
   stay EMPTY in fuzz; the guard is the safety net, not the fix.
3. Surface `executor.unresolved_effects` in coverage reports / eval
   telemetry so skipped effects count as engine gaps, not silence.
4. Both cards still stamp `engine_supported=True` — the fold gates should
   flip them; census numbers belong with that wave.
