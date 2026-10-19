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
