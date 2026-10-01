# Wave 4b findings — activated/mana/loyalty/equip/sac cohort, second half (2026-10-01)

Engine frozen. Batch = last 21 names of `tools/audit/wave4.json` (Obsessive Stitcher →
Witch's Cauldron); sibling batch took the first 22. Deliverables: 18 packs promoted to
`tools/scenarios/` (**204 → 222, 222/222 green**), 2 suspects filed, gates **222/222 + 2213
pytest + 3 subtests** unchanged.

## Green packs (18)
obsessive_stitcher · palladium_myr · prismite · riddleform_scry · sanctum_shattered_heights ·
scavenging_ooze · seasoned_hallowblade · selfless_savior · silent_dart · silversmote_ghoul ·
swamp_add_b · tavern_swindler · teferis_protege · tempered_veteran · thrashing_brontodon ·
ugin_spirit_dragon · vito_thorn_lifegain · witchs_cauldron

## Suspects (2, in `tools/audit/suspects/`)
1. **sanctum_tranquil_light** — RIGID. Printed `{5}{W}: Tap target creature. This ability costs
   {1} less for each Shrine you control` (the Sanctum is itself a Shrine → printed total
   {4}{W}). Engine demands undiscounted {5}{W}: `cost:mana_generic:4<5`. Root cause:
   `build_payment_plan` (legality.py ~486) folds CostModifier only when
   `mana_use is not None and mana_use == ctx.source` — the r19b spell-lane gate; `activate()`
   passes `mana_use=None` so the discount branch never runs. SECONDARY: the modifier's count
   filter compiles to NAME_EQ `'Shrine'` not SUBTYPE_EQ Shrine.
2. **tormods_crypt** — SILENT. Printed: exile target player's graveyard (ENTIRE gy). With two
   cards in the opponent's gy and one designated, only the designated card exiles. CONTROL
   probe: designating BOTH cards exiles both → per-card binding, no sweep. Root cause: the
   ALL-mode TARGET_PLAYER filter is UNIV (FAnd children=()), `_filter_has_referent` fails, so
   `role_handles` (selectors.py ~461) takes the binding-first lane instead of the
   population-lane whole-graveyard sweep.

## Rig laws learned this wave
- **Hand baseline is 0.** Library fillers (0..5) are added after begin_turn; the opening draw
  pops Library[5] first. A discard cost needs a deliberately seeded `zone:"hand"` card —
  `syn()`-style rig cards DEFAULT to battlefield; passing `zone:"hand"` explicitly is mandatory
  (cost of one debugging cycle: seasoned_hallowblade).
- **Summoning sickness**: creatures placed via `enter` are never offered attack THIS turn, but
  tap/mana abilities ARE legal — attack assertions need `advance_turn`.
- **Activation `idx` counts static abilities too** — Riddleform idx1=scry, Silversmote idx1=
  drawing, Vito idx1=lifelink. Always dump the compiled abilities list before writing idx.
- **Refusal controls are impossible in the pack DSL**: `activate` raises ValueError on illegal
  cost/tapped/loyalty-gate and the runner converts ANY step exception into pack failure.
  Negative controls (insufficient mana, tapped-source, loyalty-gate) are documented as rig
  constraint, not packed.
- **X-cost activations** need QX in the compiled cost (Ugin `-X`); there is no x lane in the
  frozen `activate` op — Ugin -X is un-packable, +2 verified via loyalty op, -10 probed by
  auto-resolve (6 fillers auto-played to battlefield, 7th draw on empty library, life 27).
- **Generic mana** draws from leftover pool keys in canonical order W U B R G C (`_COLORS_VOCAB`);
  scry words are `("top","bottom")`.
- **Lifelink chain** (20a handler) verified end-to-end through `deal_damage`: granted LIFELINK →
  life 22 after 2 damage (vito_thorn_lifegain).
- **Indestructible** sits outside the runner's 10-key `battlefield_keywords` vocab and no
  destroy op exists in the harness — Hallowblade's grant is verified only as cost+tap; the
  immunity itself is documented unobservable, not a silent-pass claim.

## Gate numbers
`tools/run_scenarios.py` → **222/222**; `pytest MTG_bot/core -q` → **2213 passed + 3 subtests**
(engine untouched; findings are documentation + packs only).
