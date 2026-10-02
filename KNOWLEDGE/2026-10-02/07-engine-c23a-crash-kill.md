# 07 — Engine batch 23a: kill the seven crash classes + FLASH window (2026-10-02)

Target: the C4 games report (17 crash games / 7 classes over 100 seeds, baseline
0 → 0). Compiler + goldens stayed FROZEN all batch; every class was attributed
executor-side by the C4 notes table (06-compiler-c4 §"attribution"), so every fix
here is engine code. HEAD at start: `cd975cb`.

## The classes and their fixes

| # | Crash (12c/12e query surface) | Seeds | Fix | Pin |
|---|---|---|---|---|
| 1 | `filter pred TARGETS_SOURCE not implemented` (quantity `_eval_atom`) | 4,26,31,33,95 | Fold reads the judge's designation union (mirror of IS_ANY_TARGET), falls back to `bindings["target"]`, bare ctx = conservative False (pre-601.2d honest printed cost) | r23a ×4 + promoted pack `targets_source_cost_fold` (Titanic Growth costs {C:4}{G} targeting the enemy 8/8) |
| 2 | `TARGET_PLAYER needs a bound target` (selectors `players_for_ref`) | 15,65,92 | `query.activation_target_slots` synthesizes the opponent player-slot for TARGET-coordinate activations; games `play_activation` routes the designation through it | r23a ×2 |
| 3 | `QX has no declared X` on journaled ETB (Wildwood Scourge, enters-with-X) | 16,18,20 | **etb_x ledger**: cast-declared X is carried to ETB resolution (CR 614.1c/601.2f) — the engine half of the r19c/C4 split | promoted pack `wildwood_scourge` (cast x=2, pays {C:2}{G:1} → 2 counters) |
| 4 | `trigger-loop tripwire` (binding `fire_all`, MAX_TRIGGER_FIRES=200) | 17,50 | Guard redesigned from raise to **quarantine**: on tripwire `fire_all` permanently quarantines the most-fired non-quarantined source (drops its queued instances, `_queue` gate drops it forever), records loudly in `executor.trigger_loops`, resets the drain counter and CONTINUES; re-raises only if no culprit or ≥8 quarantines in one game. Quarantine rides `state_fingerprint` via `binder.dump()`'s `("quarantined", …)`; the ledger itself is coverage-visible, not fingerprinted (like `unparseable_statics`) | amended `test_trigger_loop_tripwire_quarantines_the_loop_source` + games 17/50 (Chandra's Incinerator flagged + quarantined, game ends clean) |
| 5 | `StaticAbility payload verb GAIN_LIFE is not layer-parseable` (Rin and Seri) | 42,79 | `layers.attach_source` GUARDS registration: the unparseable half is flagged into `unparseable_statics`, the permanent still enters, only the parseable lane is skipped | amended r20b `test_gain_life_static_is_guarded_and_flagged` + promoted pack `rin_seri_static_guard` |
| 6 | `selector referent 'event' has no register` (landfall prompts at designation) | 5 | `binding._designate` passes the firing's bindings into `legal_targets`, so referent-"event" selectors enumerate their bound object | r23a ×2 |
| 7 | `CAST Island: no SpellAbility on the card` (Radha may-offer) | 90 | `optional_offer` CAST gate: a `Selector`-sourced CAST whose enumerable candidates carry NO `SpellAbility` narrows the may-offer to skip. Three correctness rules learned: referent-"event"/"result" sources are NEVER gated (r18a: nothing enumerable pre-execution); a 12a `bindings["source"]` routing is read FIRST (`ctx.binding_handles("source")`, zone enumeration is the fallback) so query/runtime identity holds; pyright needed a walrus to narrow the comprehension | r23a ×3 + amended `test_cast_land_designation_raises` |
| 8 | **(exposed mid-batch)** `filter pred COLOR_COUNT_GE not implemented` | 26,33,95 | After class 1 died, the same three seeds survived further and died one query later: Basri's Lieutenant "protection from multicolored" read by `block_pair_blocked_reason` (count=2) and Ugin's "-X: each permanent that's one or more colors" (count=1, goldens 57d0c688/eecb3047). `_eval_atom` implements it as subject-color-count off IDENTITY data — the engine carries no color-changing continuous effects (layers.py never writes color), same convention as the COLOR_HAS/COLOR_IN twin | r23a ×4 (2-color meets 2, monocolored fails 2, colorless fails 1, 3-color meets 3/fails 4) |

Class 4 attribution note: Chandra's Incinerator's compiled IR (empty subject
filter + CONTROLLER_IS-YOU, no instant/sorcery restriction — it self-retriggers
on noncombat damage) looks like a compiler misparse, but the C4 notes table
lists the tripwire under "deliberate guard: flags, never runs" — an executor
guard contract — so the engine guard is the shipped fix; the IR oddity stays
documented for the compiler campaign.

## Tripwire behavior in the field

Games 17/50 replay clean: `trigger_loops = ['card:102 ("Chandra\'s Incinerator"):
self-retriggering after 200 drain fires — quarantined, 1 queued firings dropped']`
and the game ends decisively. The 100-seed report schema is unchanged (per-game
`trigger_loops` is not a row column; verification is via `--repro`).

## Stale pins amended to the new contract (never silently deleted)

- `test_executor_binding.py::test_trigger_loop_tripwire_caps_and_raises` →
  `…_quarantines_the_loop_source` (no-raise + flag + quarantine + drained).
- `test_executor_r20b.py::test_gain_life_static_still_raises` →
  `test_gain_life_static_is_guarded_and_flagged`.
- `test_executor_stack.py::TestEffectCast::test_cast_land_designation_raises` →
  may-lane narrows to skip (a "fire" decision is rejected "not in" the offer);
  the direct-CAST half now routes a land through `bindings={"source": land}`
  (AtomArgs requires a Selector value in the CAST source role) and still
  raises `SpellAbility`.
- `test_executor_games.py` bare-ctx TARGETS_SOURCE assertFalse.

## Scenarios

293 → **297/297 green**: promoted `targets_source_cost_fold`,
`rin_seri_static_guard`, and the two former suspects `wildwood_scourge` +
`flash_window_engine_gap` (de-suspected, notes rewritten to record the
compiler-half/engine-half split). Suspects now **7** (all compiler-attributed:
chandras_pyreling, furious_rise, peer_into_the_abyss, rin_and_seri_inseparable
[misparse evidence], secure_the_scene, tampering_no_block,
treasure_token_activation).

## Gates (all 2026-10-02, this batch)

- suite: **2306 passed + 3 subtests, 0 failed** (`pytest MTG_bot/core -q`;
  batch net: r23a +16 tests, 4 amended pins)
- games: **0 crash classes / 100 seeds**, 100 decisive endings (48/52),
  mean_turns 33.49, coverage 230 cards fired
- grammar: PC-1 303/305 · PC-2 637/639 · PC-3 0 · PC-4 0 · engine 297/305
  (45 verbs) — ALL Δ0 vs the C4 baseline; PC-6/PC-8 standing FAILs unchanged
- catalog: 1/10 diverged (the GAIN_LIFE-crash seed flips NotImplementedError →
  decisive kill = intended blast radius) → repin → **0/10**; after the
  COLOR_COUNT_GE addition the pins stayed byte-identical (pure raise-replacement)
- lints: pyright **0 errors** on all 13 touched files; ruff Δ0 NEW (one
  pre-existing `I001` in query.py additionally cleaned)
