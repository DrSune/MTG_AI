# 2026-09-30 · 04 — Round 14b-1: B-11 trigger-tailing (mechanism fix + audited golden re-baseline)

Scope: compiler assembly only (`compiler.py` + tests + goldens). No executor edits. B-4/B-5/B-7/B-12 untouched.

## The mechanism

B-11 (ledger /03): a triggered ability's effect text continues across sentence boundaries, but
the plain sentences printed under a trigger ("You choose … from it." / "Exile that card …")
compiled to bare `EffectOutcome`s, survived the continuation pass untouched (they carry no
continuation prefix), and were folded by the assembly branches into the card's **SpellAbility** —
running at CAST time. Continuation-prefixed tails already merged into the trigger (the r7/r9/r11
merge chain searches back through `AbilityOutcome(TriggeredAbility)`); only the *bare* tail
channel was missing.

Fix (`compiler.py`, mirrors the r11-A loyalty trailing exactly):
- `_trigger_trailing_idx(processed)` — scans back from the list tail; skips **only** unparsed
  slots and rule reminders; returns the index iff the first meaningful entry found is an
  `AbilityOutcome(TriggeredAbility)`, else None at the first other outcome.
- Capture branch in the continuation pass (runs AFTER the loyalty check): a bare, non-`[`-bullet
  `EffectOutcome` whose anchor is a TriggeredAbility is appended INTO `trigger.effect` and
  consumed (never appended to `processed`).

**Capture-boundary rules** (all pinned by `test_compiler.py::TestTriggerTrailing`, 7 tests):
1. Sentence must be a bare `EffectOutcome` — an independently-matched sentence (its own
   Triggered/Activated/Static/keyword/gate/meta outcome) is its own ability and also a **group
   boundary**: a tail printed after an activated bullet is NOT pulled back into an earlier
   trigger (mirror of `_loyalty_trailing_idx` discipline).
2. A sentence starting with `[` is another ability bullet — never trailing, even when it parses
   to a bare effect.
3. Unparsed slots and parenthetical/keyword rule reminders are skipped, they do not break the chain.
4. May-rule (r11-1): a tail sentence containing "may" is `OptionalEffect`-wrapped **exactly
   once** — if the tail's template ALREADY produced an OptionalEffect (Garruk's Harbinger
   "You may reveal … and put it into your hand"), no phantom second wrap (de-dup guard, the one
   deliberate refinement over the loyalty branch, which never met an already-optional tail).
5. Prefix continuations keep their merge paths INSIDE the trigger effect ("Otherwise" attaches
   as the `else_effect` of the trigger's own Conditional; test-pinned).

## Sweep inventory (pre-fix, set-equal to the golden diff — r11 protocol)

4 cards / 6 sentences captured (all semantically adjudicated against printed text):

| card | captured tail(s) | trigger effect after |
|---|---|---|
| Kitesail Freebooter | "You choose a noncreature, nonland card from it." / "Exile that card until this creature leaves the battlefield." | `Seq(REVEAL, CHOOSE, EXILE)` |
| Garruk's Harbinger | "You may reveal … and put it into your hand." / "Put the rest on the bottom of your library in a random order." | `Seq(LOOK_AT, OPT(Seq(REVEAL, MOVE_ZONE)), MOVE_ZONE)` |
| Siege Striker | "This creature gets +1/+1 until end of turn for each creature tapped this way." | `Seq(OPT(TAP), MODIFY_PT)` |
| Liliana, Waker of the Dead Emblem | "It gains haste." | `Seq(MOVE_ZONE, GRANT_ABILITY)` |

The 5th moved golden — **Liliana, Waker of the Dead** (the planeswalker) — is NOT a capture: the
emblem card's record is attached into its `emblem` field (`compile_pool` two-pass), so it changes
transitively; everything outside `emblem` is byte-identical (verified). 300/305 untouched.

## Audited re-baseline (r11 protocol)

- Pre-refresh PC-4 diff list: the 4 inventory cards + the 1 transitive attachment = 5, set-equal
  to the changed-file list after `--refresh-goldens` (snapshot `/tmp/golden_pre_r14b_2026-09-30`).
- Changed-file key audit: 4 × keys ⊆ {`abilities`}; 1 × keys = {`emblem`} (transitive only).
- Post-refresh EXACT: **PC-1 301/305 · PC-2 634/639 · PC-3 0 · PC-4 0 diffs/305 files** (phase 12).
  PC-5 0.243 ms · PC-9 stable · PC-10 100%/0%. PC-6 (1 orphan) / PC-8 (0.3213) unchanged
  pre-existing FAILs. cmd: `.venv/bin/python tools/measure_grammar.py --set M21 [--refresh-goldens]`.
  Coverage did not move (parse unchanged — sentences match the same templates, only the assembly
  owner changed).

## 10-seed game rerun after the fix (deck-pairs-seed 1409, cmd `.venv/bin/python -m MTG_bot.core.executor.games --seeds 10 --pool {all,engine,castable}`)

| pool | survived | mean turns | crash-class deltas |
|---|---|---|---|
| all | 0/10 → **0/10** | 9.0 → 9.1 | B-4 scry 7/10 UNCHANGED (still the wall); B-7 2/10 unchanged; **Kitesail's cast-time `TARGET_PLAYER needs a bound target` (seed 2) GONE** — seed 2 now reaches turn 10+ and dies on a NEW deeper gap: `QX has no declared X` on `cast:Primal Might` (new ledger candidate, B-1/12c family) |
| engine | 1/10 → **1/10** | 17.4 → **18.2** | B-4 7/10 unchanged (same seeds); B-7 1/10 unchanged; seed 6's crash MOVED from `cast:Siege Striker` (`QProp referent 'event'`, B-11-rooted) to `cast:Seasoned Hallowblade` (`selector referent 'result'`, the documented B-9 residual) |
| castable | 0/10 → 0/10 | 2.0 → **3.9** (max 8→22) | fired-cards 9 → 18; **B-9 referent class no longer appears in pool runs** (seed 7 now dies earlier on B-4 scry; Hallowblade is not reached by the random policy); B-4 8/10, B-7 1→2/10 |

**B-9 / TARGET_PLAYER residual verdict:** the Kitesail `TARGET_PLAYER` symptom (a cast executing a
trigger's target-coordinate atom) was pure B-11 and is gone; the CR-601.2i "targets remembered for
the ETB trigger" modelling gap it exposed never fires for these cards anymore and stays folded into
B-11's closure rather than its own row. The B-9 residual is exactly one card — Seasoned Hallowblade
(static-ish GRANT_ABILITY on a SpellAbility, no trigger — out of trigger-tailing's reach by design,
row boundary rule 1) — stays OPEN in the ledger, now pinned by a deterministic direct-cast repro
(`test_b9_result_referent_only_resolves_inside_a_trigger`, seed-independent).

## Gates

- Core suite **1993 passed / 0 failed** (1986 + 7 `TestTriggerTrailing`); the B-9 repro test
  flipped from a seed-policy crash pin to the direct-cast residual pin.
- Golden baseline: 5 files re-baselined (audited above); `test_golden.py` verify 0 diffs.
- pyright 0 errors (CLI); ruff delta 0; git scope: compiler.py, test_compiler.py,
  test_executor_games.py, 5 goldens, ledger /03 status flips, this doc, INDEX (+ NUMBERS/reports
  side-effects of the measurement run). No executor edits. No commit.
