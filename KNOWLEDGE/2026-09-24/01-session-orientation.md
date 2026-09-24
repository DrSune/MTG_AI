# 2026-09-24 · 01 — Session orientation: baseline, tooling fix, Goremand follow-up closed

**Status at session start (measured, repo .venv):**

| Number | Value | Command |
|---|---|---|
| core test state | **1086 passed / 0 failed** | `python -m pytest MTG_bot/core -q` (after /tmp bucket regen; pre-regen: 55 failed + 8 errors, all bucket-JSON-missing) |
| PC-1 card_coverage | **0.6689 (204/305)** | `python tools/measure_grammar.py --set M21` (live probe via `coverage.measure_pool`) — up from the last recorded 0.6492 (198/305): working-tree b2b/b4 template additions post-date the last NUMBERS entry |
| PC-2 sentence_coverage | **0.7887 (504/639)** | same — up from recorded 0.7793 (498/639) |
| true residual queue | **133 shapes / 135 unparsed occurrences** | `/tmp/opencode/probe_unparsed.py` → `/tmp/opencode/unparsed_queue_2026-09-24.txt` |

## Tooling fix (this session)

- `tools/gen_buckets.py` had two stale pinned asserts from 2026-09-17
  (`b2a_keys == 51` → now **54**; `b4_keys == 26` → now **27**; `b3_keys == 44`
  still correct). Root cause: the b2a/b4 template modules gained 3/1 covered
  shape keys since the tool was written; the script's asserts predate the
  template growth, and the `/tmp/opencode/phase1_buckets/*.json` work-inputs
  were wiped (PITFALLS: re-generate with `python tools/gen_buckets.py`).
  All other pinned constraints (504 keys, 62/62/48/47/270 partition,
  alphabetical B2 half-split, B5a SHAPES cross-check, 639 occ) verified
  unchanged. Docstring counts refreshed with the 2026-09-24 date.
  Buckets regenerated; all 8 per-bucket test files pass.

## Goremand "double-parse" follow-up (2026-09-23/03 item 1): CLOSED as misdiagnosis

Verified against the live compiler, not the note:

1. Goremand's text has **two distinct clauses**: "As an additional cost to
   cast this spell, sacrifice a creature." (B5a `B5a-addl-cost-sacrifice`
   → `CostSacrifice` on the effect-less `SpellAbility`) and "When this
   creature enters, each opponent sacrifices a creature." (B2a
   `B2a-goremand`, a per-card template present since git HEAD — verified
   `git show HEAD:MTG_bot/core/compiler/templates_b2a.py` line 1944).
2. Each sentence feeds **one** template: `compile_card` reports
   `ambiguities=()` for Goremand (PC-3=0 pool-wide). No sentence is
   double-parsed.
3. The `TriggeredAbility` is **correct** under the binding EachPlayer
   rebinding contract (PITFALLS 2026-09-22, established by T7 with
   Goremand as the canonical example): inner `CONTROLLER_IS(YOU)` inside
   `EachPlayer(ALL_OPPONENTS)` rebinds to the iterated opponent —
   "each opponent sacrifices a creature THEY control."
4. The trigger is byte-identical across the round-3 re-baseline (03 verified
   PC-4 0 diffs vs it), so it also matches the committed baseline.

Conclusion: the 03 follow-up described the trigger as if it were built from
the additional-cost sentence; it was never that. **No code change needed.**
The trigger fix 03 asked to "not let the double-parse silence" was in fact
the T7 rebinding contract, which already governs this tree.

## Residual queue: two queues, one truth

- The static `UNCOVERED` tuples in the template modules (B2a 8 / B2b 18 /
  B3 4 / B4 20 / B5a 23 / B5b 49 / B5c 17 = 139 shapes) are **stale
  bookkeeping**: they still list shapes the compiler's built-ins now consume
  (choose-opener folds in B5a/B2a; search-shuffle in B5b's 6× "If you search
  your library this way, shuffle."). 139 static vs 133 live — the 6-occ
  search-shuffle + choose-opener rows are built-in-covered.
- The **live** queue (compiler's own unparsed fragments, 133 shapes / 135
  occ) is the true work register. Full dump:
  `/tmp/opencode/unparsed_queue_2026-09-24.txt` (regenerate with
  `/tmp/opencode/probe_unparsed.py`).

## Next

`2026-09-24/02-grammar-round3-decision.md` — round-3 grammar additions for
the top residual families (StaticAbility.condition, ActivatedAbility.condition,
COUNTER_SPELL `unless` role, INSTANT_OR_SORCERY_CAST_THIS_TURN,
CostModifier.extra_deltas, TARGETS_SOURCE) → unblocks 8 shapes / 8 occ.
