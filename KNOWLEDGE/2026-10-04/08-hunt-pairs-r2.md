# 08 — HUNT H3: pair hunt round 2 (10 heat pairs, opposing-seat packs)

Date: 2026-10-05 (run of 2026-10-04 batch, HEAD 10d53c6). Scope: `tools/` + `KNOWLEDGE/` only — engine, goldens, traces untouched. Method per `06-hunt-pairs.md` (H2): next 10 untested pairs by heat from `tools/audit/pair_coverage.json`, each lit as ONE scenario pack asserting BOTH printed promises across opposing seats, expectations derived from the CR first, engine asked only at the falsifiers.

## Verdict table (heat order)

| # | Pair (heat) | Pack | Verdict | Lit promises / falsifiers |
|---|---|---|---|---|
| 1 | Conclave Mentor × Garruk, Unleashed (2281) | `conclave_mentor_x_garruk_unleashed.json` | **GREEN** | mentor deathrider puts the deferred +1/+1 on the Garruk-created Beast; -2 census TRUE branch loyalty 5 |
| 2 | Gadrak, the Crown-Scourge × Malefic Scythe (2258) | `gadrak_crown_scourge_x_malefic_scythe.json` | **GREEN (after fix)** | soul-folded Brute (13/13 soul… printed 1/1+SOUL statics) survives to end step → Treasure 2; a soul-BLIND wall would die — survival lane IS the fold proof; damage ledger emptied by end_turn |
| 3 | Alpine Houndmaster × Garruk, Unleashed (2214) | `alpine_houndmaster_x_garruk_unleashed.json` | **GREEN (pack fixed)** | post-creation census order (CR 603.4) TRUE→loyalty 5; attack census X=2. **Engine data fact: Houndmaster printed base is 2/2** (H2 layering note + life observation) → face = 4+1+1 = 6 → life 14; my CR note assumed 1/1→life 15: pack wrong, engine right |
| 4 | Basri, Devoted Paladin × Malefic Scythe (2201) | `basri_devoted_paladin_x_malefic_scythe.json` | **GREEN** | +1 counter × soul static × counter layer stack = 5/5; VIGILANCE lane (EoT expiry via dance) |
| 5 | Garruk, Unleashed × Rin & Seri, Inseparable (2187) | `garruk_unleashed_x_rin_and_seri_inseparable.json` | **GREEN** | -2 census FALSE branch loyalty 4; tokens lane seat-merge: Cat+Dog (Rin EtB) + Beast |
| 6 | Malefic Scythe × Wildwood Scourge (2156) | `suspects/malefic_scythe_x_wildwood_scourge.json` | **SUSPECT** | see §Suspect below |
| 7 | Conclave Mentor × Gadrak, the Crown-Scourge (2145) | `conclave_mentor_x_gadrak_crown_scourge.json` | **GREEN** | mentor's replacement-reassignment of a dying creature's counters: 1→2 |
| 8 | Basri, Devoted Paladin × Conclave Mentor (2120) | `basri_devoted_paladin_x_conclave_mentor.json` | **GREEN** | granted-counter folds through mentor layering |
| 9 | Elder Gargaroth × Garruk, Unleashed (2052) | `elder_gargaroth_x_garruk_unleashed.json` | **GREEN (after rig learn)** | trample partition: 5 lethal + excess ask; attack choose-trigger Beast (default mode); FALSE-census loyalty 4. **New semantics: map value = excess PINNED to that blocker slot, player takes the rest** — [0] routes 1 face (life 19); [1] pins it (life 20) |
| 10 | Experimental Overload × Garruk, Unleashed (2031) | `experimental_overload_x_garruk_unleashed.json` | **GREEN** | overload alternate-cost cast via `decisions:["Jolt"]` (X auto-derived from 2 synthetic Instants); first battlefield_pt lighting (Weird [2,2]); Jolt → hand lane, `eo` → exile lane |

Counts: **9 GREEN gate packs + 1 SUSPECT** (held out of the gate, red-as-intended CR pin).

## Suspect — pair 6: EtB-placed +1/+1 counters absent from the P/T layer

`tools/audit/suspects/malefic_scythe_x_wildwood_scourge.json` (status `suspect`). Wildwood Scourge cast `x:1` → counters lane reads `{PLUS_1_PLUS_1: 1}` (EtBState placement) but **power lane reports printed 1**, and a sickness-free probe attack (cast → full turn dance → unblocked) **deals 1, not 2** (`h3dbg p6c`: life[1] 19) — the counter is missing from P/T evaluation AND from combat damage, not just a stale reporting lane. CR 122.1c / 613.3d expectation: 2/2. Contrast: effect-GRANTED +1/+1 counters fold everywhere (H2 `alpine_houndmaster_x_basri_ket` power 4; H3 packs 4/8 wolf 5/5). Every other lane of the pair passes: negative lane (Scourge trigger stays silent through soul-equip + dies: SOUL ≠ +1/+1, Equipment ≠ creature, enemy-owned — CR 122.1b/603.2), SOUL 2 dies-rider (CR 603.3d), soul-folded Hound marks Prey 2. Suspect pack pins the CR values so the divergence fails loudly until adjudicated; pair coverage +10 for the B4b matrix at next regeneration.

## New rig laws (→ PITFALLS.md)

1. **Auto damage ledger**: the runner asserts the final damage-marks ledger even when `damage` is omitted from `expect` — omission = "expect EMPTY". Packs ending mid-combat with marks on survivors must assert or dance (P6/P9 probes exposed this).
2. **Trample map polarity**: `combat.trample` answers ask `trample:<card>:<slot>:<turn>` (executor ~1720–1834) AFTER lethal coverage is reserved; the value is the EXCESS pinned to that blocker slot, the defending player takes the remainder. Re-read of precedent `trample_excess_partition` confirms (Dreadmaw 6, Corpse 2/2 lethal 2, [1] → 3 face → life 17).
3. **Summoning sickness silently skips attacks**: cast→combat in one window = no attack, no error (first p6c "passed" vacuously). Probe attacks need a full `end_turn/advance_turn` dance first.
4. **X-cast without `"x"`** on a variable-spell card is an illegal cast — spell wastes to graveyard (p6b zone lane).
5. **Suspect staging**: divergent pairs move to `tools/audit/suspects/` as scenario-shaped JSON + `status`/`finding` (H2 precedent `basri_ket_x_siege_striker.json`); gate default scans only `tools/scenarios`.

## Gates (2026-10-05, this working tree)

- Scenario packs: **336/336 green** — `.venv/bin/python tools/run_scenarios.py` (327 baseline + 9 H3 packs; suspect excluded).
- Engine suite: **2354 passed + 3 subtests, 0 failed** — `.venv/bin/python -m pytest MTG_bot/core -q` (Δ+4 vs recorded 2350 from a parallel session's tests; MTG_bot untouched by H3).
- Files added: 9 packs in `tools/scenarios/`, 1 suspect, this doc, NUMBERS/PITFALLS/INDEX rows. No file modified elsewhere.
