# 109 — ZNR engine-robustness smoke fuzz (first random-walk crash ledger)

Date: 2026-10-19. Tool: `tools/eval/znr_engine_smoke.py` (new this wave;
grouping logic unit-tested by `tools/eval/test_znr_engine_smoke.py`, 5 passed).
Ledger: `reports/znr_engine_smoke_2026-10-19.json` + `.md`.
Producing command:
`python tools/eval/znr_engine_smoke.py --games 40 --workers 4 --recheck 5 --probe-games 6`
(pool `get_supply("engine","ZNR")`, turn cap 150, deck-pairs seed 201019 —
separate stream from the game seed; per-game 45 s wall-clock alarm; workers 4).
Reports crashes; fixes are separate waves (none made here).

## Headline numbers
- games completed: **40/40**, wall 5.7 s (workers=4); crashes **3 → 7.5 %**
  crash rate; **2 distinct signatures**.
- exploration depth: median **52 acts / 31 turns** per game — random
  legality-narrowed walks (existing RandomPolicy); coverage is
  legality-adjacent states only, not a state-space proof.
- determinism: seeds 0–4 rerun → **identical rows (PASS)**.
- BackFace reach probe: **PASS** — 4,364 intercepted `walk` calls over 6
  probe games, **0** walks descended a BackFace subtree without
  `skip=BackFace`, **0** BackFace/face-inner objects in executor+binder
  registries; 13 battlefield permanents legitimately CARRY a BackFace node
  (the /106 encoding). Caveat, honest: at run time all observed engine walks
  are effect-scoped, so no run-time walk even yielded a face node
  (`face_yields_skipped_ok=0` is a scoping artifact, not evidence).
- Known supply precondition (pre-existing, /108-adjacent): ZNR compile emits
  one shape-gap exclusion, `Nighthawk Scavenger` (`parse_pt '1+*'`, see
  2026-10-18/99) — 267 deckable / 279 engine-supported.

## Crash signatures (report, not fix)
1. `NotImplementedError@selectors.py:364 in resolve_selector` — **2 hits**,
   seeds **[5, 28]** (turn 30 / 7-ish). Message: selector referent `'result'`
   has no register — no trigger-firing bound one and no producer atom wrote
   one. Seed-5 in-flight: casting `Acquisitions Expert`; frames
   `play_cast → stack.cast → _run_effect → verbs.run_atom → _v_move_zone →
   resolve_selector`. Repro:
   `python tools/eval/znr_engine_smoke.py --repro 5`  (verified: reruns the
   exact raise + both 60-card lists).
2. `ValueError@selectors.py:347 in resolve_selector` — **1 hit**, seed **[23]**
   (turn 7, 17 acts), in-flight: cast `Shell Shield`; `'target' referent has
   no target binding`. Repro: `python tools/eval/znr_engine_smoke.py --repro 23`.

Both are selector-referent registers: a `result`/`target` referent is read
where nothing wrote it. Minimal repro is seed+acts (step index); full
tracebacks stored under `full_tracebacks` in the ledger JSON.

## Repro surface note (why not games.py --repro)
`games.py main --repro` hardcodes SET_CODE (M21) — it would silently rerun the
wrong pool. The smoke tool's `--repro SEED` is the ZNR repro surface.

---

# 109 addendum — --set parameterization, M21 era (500) + ZNR deep (2000)

Same day, follow-up wave. Tool now takes `--set SET_CODE` (default ZNR;
`get_supply("engine", SET)`; ledger stems `znr_engine_smoke_*` / `m21_engine_smoke_*`,
schema identical; `--repro` honors `--set`; repro strings now embed `--set`).
Tests: 7 passed (`tools/eval/test_znr_engine_smoke.py`, +2 tests for
`report_prefix` naming and `--set` pass-through). Report-only; NO engine fixes.

## M21 (FROZEN era) — 500 games — crashes DO exist here
`python tools/eval/znr_engine_smoke.py --set M21 --games 500 --workers 4 --recheck 5 --deadline 1500`
500/500 completed, wall 92 s, **7 crashes = 1.4 %**, 3 signatures; median
**72 acts / 34 turns**; determinism PASS; BackFace probe PASS (0 carriers —
M21 is faceless, probe still ran). Ledger: `reports/m21_engine_smoke_2026-10-19.{json,md}`.
All three repros **verified by rerun** (full tracebacks in ledger JSON):
1. `AssertionError@quantity.py:880 in _eval_atom` — **5 hits**, seeds
   **[27, 95, 239, 274, 412]**: `assert atom.count is not None and
   atom.counter_kind is not None` during `eval_filter` while acting with
   `Tempered Veteran` — a counter/count filter atom reaches atom evaluation
   with BOTH fields None (malformed filter shape at eval time, not a None-
   guard the query layer can serve). Highest-volume signature in the frozen
   era. Repro: `python tools/eval/znr_engine_smoke.py --repro 27 --set M21 --deck-pairs-seed 201019 --turn-cap 150`
2. `NotImplementedError@quantity.py:373 in resolve` — seed **384** (turn 51):
   `QThisTurn(NONCOMBAT_DAMAGE) not implemented (12b turn ledger)`, in-flight
   cast *Fungal Rebirth*. Unimplemented quantity in the turn ledger.
   Repro: `--repro 384 --set M21`.
3. `ValueError@quantity.py:417 in _prop_value` — seed **490** (turn 45):
   `POWER undefined on handle card:61`, in-flight cast *Carrion Grub* — a
   POWER property read on a handle whose P/T is undefined (zero-power/
   undefined-P/T shape). Repro: `--repro 490 --set M21`.

## ZNR deep — 2000 games — 0.1 %
`python tools/eval/znr_engine_smoke.py --games 2000 --workers 4 --recheck 5 --deadline 1500`
2000/2000 completed, wall 325 s, **2 crashes = 0.1 %**, 2 signatures; median
**60 acts / 32 turns**; determinism PASS; probe PASS (0 violations / 0 registry
hits; 12 legitimate battlefield BackFace carriers). This run OVERWROTE
`reports/znr_engine_smoke_2026-10-19.{json,md}` (same canonical stem; the
40-game numbers above live in this file, the JSON is now the 2000-game ledger).
Morning's selectors.py signatures (seeds 5/23/28) did NOT recur in 2000 games —
consistent with the intervening aura fix. Both new signatures verified by rerun:
1. `RuntimeError@__init__.py:1721 in _declare_blockers` — seed **1269**
   (turn 26, 50 acts): menace attacker blocked by exactly ONE creature —
   the blocker-ask narrowing served an illegal assignment (CR 702.113);
   legality-surface hole, the engine's own tripwire caught it.
   Repro: `python tools/eval/znr_engine_smoke.py --repro 1269 --set ZNR --deck-pairs-seed 201019 --turn-cap 150`
2. `ValueError@stack.py:1040 in cast_card` — seed **1715** (turn 21):
   `CAST Beyeen Veil // Beyeen Coast: no SpellAbility on the card` — the
   query/legality surface offered a cast row for a two-faced card whose
   routed ability is not a SpellAbility (DFC-cast shape; adjacent to the
   /97 unaskable audit, and the only face-flavored crash seen — the BackFace
   node itself stayed sealed). Repro: `--repro 1715 --set ZNR`.

Era comparison, honest: M21 (500, 1.4 %) vs ZNR (2000, 0.1 %) is NOT a
controlled comparison — different pools, sizes and depths; but M21's
signature 1 at 1 % alone (5/500) makes the frozen era the louder bug report
of this wave.
