# 64 — Context row-budget for closed-loop BcAsk (gameplay_eval v4)

## STEP 1: trunc semantics + dominant overflow class (measured)
- `trunc` (gameplay_eval_v2 seat_stats) = **per-ASK context-cut counter** in
  `BcAsk._decide` (tools/training/ab_duel.py): the seat's stream is BOS + every
  past ask's `[ASK]+site+snapshot+[SEP]` block; over `max_len=1024` the legacy
  rule kept `BOS + last 1023 TOKENS` — a mid-row blind cut. Menu candidates ride
  a separate tensor and were never affected. Teacher has no stream ⇒ 0.
- Diagnostic (`.venv/bin/python /tmp/opencode/diag_ctx.py`, 5 replayed v3-lane
  games, bc9 vs teacher, engine supply, seeds 1-5): 184 asks, 159 trunc events
  (**86.4%**), mean block **245.6 tokens** (hand 109.1 + lib 64.6 + bf 37.3 =
  89% of a block), mean 252.1 tokens dropped/event: **hand 45.1%, lib 26.5%,
  bf 14.6%**. 0/159 events cut the CURRENT ask's own block — the victim is
  history: the policy plays full games on the last ~3 board snapshots, while
  every training episode (puzzles) fit <1024 intact. Exposure gap CONFIRMED as
  a history-stream distribution break, not menu blindness.

## STEP 2: relevance-first row budget (context builder only)
- `bc_data.obs_groups` + `bc_data_v2.obs_groups_v2/zone_groups_v2`: row-grouped
  serialization with `flatten_groups(...) == obs_words(_v2)(...)` — provably
  identical (unit test + 42 live snapshots, 0 violations). No tokenizer/encoder
  change: same vocab, same words, `encode_episode(_v2)` untouched ⇒ scenario
  packs byte-stable by construction (398/398).
- `BcAsk` keeps `self.blocks` and assembles deterministically (no RNG):
  zero drops ⇒ seq identical to legacy (byte-stability asserted over the
  fit-only prefix, 0 mismatches); under pressure: (A) byte-duplicate history
  blocks (combat declaration repeats — 3 hits/game), (B) oldest history block
  ("old journal"), then severity variants on the CURRENT block only:
  (C) zone lanes → `[tag, seat, count]` + menu-referenced rows (handle
  substring, over-inclusion safe), (D) unreferenced opponent-hand rows;
  stage E legacy tail window — never fired in-game (`tail_fallbacks==0`,
  asserted per smoke game). Current ask's block ALWAYS survives intact
  (suffix assertion in `test_bcask_budget_byte_stable_intact_and_honest`).
- Truncations keep legacy per-ask semantics (any drop ⇒ +1, so
  `test_bcask_plumbing_toy_model` still holds); `ctx_stats` breaks drops down
  by stage and is surfaced as `seat_stats[seat].ctx` in the v2 JSON.

## Verification
- New tests (tools/eval/test_gameplay_eval_v2.py): flatten-equality,
  byte-stability + ladder invariants (stub model), zone-collapse menu-keep,
  3-game trunc regression (tail_fallbacks 0, trunc ≤ recorded drops,
  model_errors 0, overflow exercised).
- Gates: `pytest tools/eval -q` 20 passed · `pytest tools/training` 77 ·
  `MTG_bot/core` 2516+2st · scenarios 398/398 · `tools/audit` 87.
- KNOWN PRE-EXISTING (reproduced on clean tree @0588ad9, NOT this change):
  `test_certify_backings_demotes_with_heuristic_fallback` fails only in the
  combined `pytest tools/eval tools/training` batch (collection-import
  interaction); green in `tools/eval` alone and `tools/eval tools/training`
  predates this work.
- v4 full eval (200 games, mirror + teacher, bc9/bc7, cpu, workers 4) →
  `tools/eval/gameplay_eval_v4_fullctx.json`: PENDING (numbers appended on
  completion; v3 baselines: teacher WR 0.3927 [0.326,0.463] trunc 7441/8360,
  mirror 0.492 [0.421,0.563]).
