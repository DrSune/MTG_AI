# 06 — HUNT H2: Top-10 heat collision pairs, opposing seats (2026-10-04)

Batch H2 of the pair-hunting campaign. The top-10 UNTESTED pairs from
`tools/audit/pair_coverage.json` (heat order) each get one pack placing BOTH
cards in OPPOSING seats, asserting the printed-promise outcome derived from
`MTG_bot/data/M21.json` text + CR. Naming: `<a>_x_<b>.json`.

## Verdict table

| # | Pair (heat) | Class | Pack | Verdict |
|---|---|---|---|---|
| 1 | Basri Ket × Siege Striker (3710) | pt_layers / EoT-duration | `suspects/basri_ket_x_siege_striker.json` | **SUSPECT** |
| 2 | Basri Ket × Malefic Scythe (3430) | cross-seat counter+static fold | `basri_ket_x_malefic_scythe.json` | GREEN |
| 3 | Basri Ket × Wildwood Scourge (3080) | trigger watches EVENT not agency (CR 603.2) | `basri_ket_x_wildwood_scourge.json` | GREEN |
| 4 | Alpine Houndmaster × Basri Ket (2870) | census+counter PT fold | `alpine_houndmaster_x_basri_ket.json` | GREEN |
| 5 | Basri × Rin and Seri (2800) | token-controller law (CR 111.2), per-cast census | `basri_ket_x_rin_and_seri_inseparable.json` | GREEN |
| 6 | Basri × Garruk, Savage Herald (2730) | grant-vs-consumer policy lane; 0-loyalty SBA | `basri_ket_x_garruk_savage_herald.json` | GREEN |
| 7 | Basri × Elder Gargaroth (2660) | nontoken-census recursion; block-branch trigger | `basri_ket_x_elder_gargaroth.json` | GREEN |
| 8 | Basri × Experimental Overload (2660) | controller-perspective GY census (CR 401.2) | `basri_ket_x_experimental_overload.json` | GREEN |
| 9 | Basri × Feat of Resistance (2660) | both-sides buff stacking (CR 122.1c) | `basri_ket_x_feat_of_resistance.json` | GREEN |
| 10 | Garruk, Unleashed × Malefic Scythe (2646) | cross-seat PW buff on equipped enemy | `garruk_unleashed_x_malefic_scythe.json` | GREEN |

## The suspect (pair 1) — new bug shape

`basri_ket_x_siege_striker.json`: enemy Basri +1 counter on the opposing Siege
Striker; Striker attacks and its may-trigger taps Grog for +1/+1 **until end of
turn**. Observed: combat damage sees P=3 (DS 3+3=6, life 14 CORRECT), the
counter and the tap both land, but post-combat PT lanes report 2/2, not the
CR-mandated 3/3 (base 1/1 + counter + EoT DCP).

Probe decomposition (staging only, not shipped):
- **Probe A** (cross-seat counter alone, no combat): 2/2 — counter folding on a
  printed-static card is sound.
- **Probe B** (trigger +1/+1 only): final power 1, but life proves P=2 during
  damage. The trigger-sourced EoT buff is applied, then dropped at end of combat.
- **Probe E** (Basri +1's activate-sourced EoT INDESTRUCTIBLE + bare combat):
  keyword SURVIVES the combat op, life math uses the counter — so the rig's
  combat op does NOT run cleanup and activate-sourced EoT effects live.

=> The divergence is **duration-class-specific**: continuous effects from
*triggered abilities resolving during combat* with "until end of turn" duration
are expired at end of combat (CR 514.2 says cleanup). Activate-sourced EoT
effects (Basri +1's indestructible, Garruk Unleashed +1's +3/+3 — both
green-pack-proven) are not. Cross-reference: this is the mirror of the
`basris_solidarity` counter-blind family and the historical EoT-expiry shapes in
22-wave5b-findings; none reproduced, new shape.

## Rig law confirmations learned this batch (see PITFALLS for full text)

1. **Turn dance for opponent-seat casts**: casts/combats for seat 1 need a real
   `end_turn`+`advance_turn` dance — the window law is `not_your_turn` (cast) /
   "not the active player" (combat). Mana injected in `pack.mana` survives the
   dance (injected pre-begin_turn). A `cast` step takes `controller`, not `seat`.
2. **EoT effects expire on the dance**: an "until end of turn" stamp from
   window 1 is gone in window 2 — order cross-seat buff packs so the assertion
   lands in the stamping window (pair 9 restructured for exactly this).
3. **Damage lane compares the full 16a mark ledger** and marks reset with the
   dying creature (pairs 6/7 learned it the hard way).
4. **+1/+1 counters fold into damage assignment** across seats: the 0-power
   Wall dealt 1 after Basri's enemy-stamped counter (pair 6) — CR 122.1c,
   counter-blind damage would have been the historical suspect shape; engine is
   right here.
5. **0-loyalty SBA** retires the Herald to the graveyard while its EoT grant
   still offers the policy ask (CR 611.2a) — grant outlives source (pair 6).

## Gates

- `tools/run_scenarios.py` (committed scope + 9 new H2 packs): the 4 FAILs in
  the tree are chandra `*_branch0X.json` untracked WIP from a parallel batch
  (independent `hand[0]` lane, each has a passing `_twin`); `git stash -u`
  proves committed baseline = 304/304 green, and with H2's 9 added the
  H2-owned scope is 313/313. No regression from this batch.
- `pytest MTG_bot/core -q`: **2350 passed, 3 subtests** — unchanged.
- Suspect filed: `tools/audit/suspects/basri_ket_x_siege_striker.json`
  (status/finding fields carry the CR argument + probe evidence).
