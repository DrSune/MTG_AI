# 15 — Wave-4 derivation (mana/activated cohort, loop step 1, 2026-10-01)

## IR reality first (no invented family)
- Vocabulary check: `ActivatedAbility` (ability_tree.py:2497) IS the "cost: effect" node — mana/tap/loyalty/equip all compile to it. **Cycling is a naming artifact: the golden M21 dump carries ZERO cycling-text cards** (verified by text scan), so the lane is recorded as a verified no-op in meta.family.
- Family = any non-token/non-emblem card with an ActivatedAbility node via `walk(record)` (same instrument as waves 1-2). 94 cards; 93 carry it top-level in `record.abilities`; the one nested-only card (Gadrak — node lives inside its TokenSpec, i.e. the token's ability) is pack-covered by name, so the frozen row set is identical under a top-level-only reading. Noted in the builder docstring.

## Cohort
- Rule: family ∩ engine-supported gate − covered-by-name (union of tools/scenarios/*.json real names + suspects = 203 names). **94 = 49 covered + 2 gate-flagged + 43 rows**, all supported, all with art. Flags: Teferi, Master of Time + Teferi, Timeless Voyager, both sole-reason PHASE_OUT (same pair as wave-3's flag — re-admit when phase-out atoms land).
- Verb histogram (mechanics, per-card unique, 43 rows): ADD_MANA 8 · GRANT_ABILITY 7 · PUT_COUNTER 6 · DRAW 6 · DEAL_DAMAGE 5 (then MODIFY_PT/MOVE_ZONE/DISCARD 4). Cost-part mix: CostTap 24, CostManaGeneric 21, CostManaColor 20, CostLoyalty 18, CostSacrifice 9, CostDiscard 3, CostPutCounter 2, CostLife 1 — a genuine activation-lane spread.
- 43 rows is inside the wave-size norm (55/67); honest cohort, not padded.

## Pre-existing drift discovered (NOT caused here)
`--wave3 --lint` **drifts at HEAD**: wave3.json was frozen at 24abfe4 before the 55 wave-3 packs were authored/promoted (148→204 scenarios), and the closeout never re-frozen it. The 55 "dropped" names are exactly the wave-3 cohort. wave1/wave2 have no name-exclusion rule so their lints stay green by construction. Left wave3.json untouched (LAW: earlier wave files byte-identical) — orchestrator decision: re-freeze wave3.json or mark the lint wave-coverage-immune at next engine-touching commit.

## Gates
`--wave4` write + `--wave4 --lint` OK · wave1/2 lint OK + all three wave files md5-verified byte-identical · `pytest MTG_bot/core -q` → **2213 + 3 subtests** unchanged · pyright 0 · ruff Δ0 on builder. Tools-only; no MTG_bot/** edits; no commits. Next: loop step 2 — wave-4 pack authoring (43 rows, engine frozen).
