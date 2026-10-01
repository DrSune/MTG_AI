# 22 — Wave 5b: draw/life/shrine cohort (15 cards, 16 green + 6 suspect)

Date: 2026-10-01. Batch rows: `/tmp/opencode/wave5b_rows.json`.
Gate at authoring: staging driver `/tmp/opencode/wave5b_staging/verify_staging.py`
→ greens 16/16 pass, suspects 6/6 red with intended witnesses.
Roster correction: batch B is 15 cards — **"Frantic Inventory" does not exist**
in the rows file (prior-session artifact).

## Green packs (16, tools/scenarios/)
liliana_emblem_grave_beast, liliana_emblem_no_activation, lorescale_coatl_draw,
mystic_skyfish_first_draw, mystic_skyfish_second_draw, quirion_dryad_colored_spell,
sabertooth_mauler_end_step_death, sabertooth_mauler_no_death_control,
sanctum_of_all_search_fire, sanctum_of_all_search_skip, spellgorger_weird_noncreature,
tolarian_kraken_tap, tolerian_kraken_untap, tolerian_kraken_skip_payment,
twinblade_assassins_end_step_death, twinblade_assassins_no_death_control.

## Suspects (6, tools/audit/suspects/)
1. **pitchburn_devils_dies_trigger** (silent): the self-dies law of wave 5a —
   IS_SOURCE dies triggers never fire; expected 3 damage marks `{'v': 3}`, got `{}`.
2. **spirit_of_malevolence_dies_trigger** (silent): same law; life 20/20 vs 21/19.
3. **tefeiris_ageless_insight_second_draw** (silent): `replacements.py` has NO
   draw-replacement consumer — the second draw is a plain 1-for-1 (hand 2 vs 3,
   library [Library 3..0] vs [Library 2..0]).
4. **sanctum_of_fruitful_harvest_add_x** (loud): Shrine-census-to-zero X fold —
   the "shrine you control" census folds to 0 after the shrines leave/enter path,
   so `add X` yields an empty pool and the follow-up cast dies with
   `ValueError executor: illegal cast: cost:mana:R:0<1`.
5. **sanctum_of_calm_waters_draw_x** (silent, same X fold): draws 0 (library
   untouched) but the "If you do, discard a card" clause still DISCARDS (Discard
   Me → graveyard) — the do-conditional doesn't gate on the draw happening.
6. **sanctum_of_stone_fangs_life_x** (silent, same X fold): X=0 → life 20/20
   instead of 21/19. Sanctum of All's 6-shrine "pay 6 less" clause is likewise
   uncompiled (fire/skip search lanes work, discount untestable).

## Rig laws learned this wave
- **Setup begin_turn DRAWS**: `ScenarioRunner.__init__` calls `begin_turn(p0)`
  BEFORE the library rig, so a pack that declares its own `zone:"library"` cards
  draws the LAST-declared one into hand during setup. Workaround: declare a
  Creature decoy after the wanted library card — setup pops the decoy, the
  wanted card survives at the library bottom (Sanctum-of-All search packs).
  (Corrects the earlier "setup begin_turn does not pop" claim: it pops whenever
  a library card was declared; the harness's own Library-0..5 fillers are added
  after, so they never draw at setup.)
- **Setup-time asks crash**: a battlefield-at-setup permanent whose FIRST_MAIN
  trigger asks (Harvest color-ask, Calm Waters may, Sanctum of All upkeep
  search) fires inside `__init__`'s begin_turn → "nothing is primed and no
  answerer is registered". Enter via the `enter` op; the ask lands on the
  SECOND `advance_turn` (first advance = the setup turn's own upkeep).
- **Kraken ask order = designation FIRST**: target word, then may-pay
  ('fire','skip'), then inner may, then choose ('0'=tap,'1'=untap). 'skip'
  auto-narrows the step to 2 asks. Payment {1} deducts correctly (W:3 → {}).
- **Revitalize compiles to +3 life in this pool** (life 23 after one cast;
  Lorescale Coatl 26 after two) — pin life lanes to 3, not printed 2.
- **The `damage` lane is ALWAYS compared** — omitting `"damage"` asserts an
  EMPTY ledger; any Shock in a pack must be asserted (`"damage": {"me": 2}`).
- **Additional-cost creature sacrifice is silent, like activation sacrifice
  (5a: `legality.py:711 cands[:need]`)** — Goremand's "sacrifice a creature"
  cost never reaches `decisions.provider` (asks_seen empty) and eats the
  LOWEST-handle controller-0 creature. The frozen green pattern
  `goremand_sacrifice_cast.json` only lands "feed" because feed is the sole
  candidate; adding any lower-handle creature steals the cost.
- **Goremand is the ONLY castable plain creature** (with Masticore, whose
  compiled extra cost = an undeliverable discard) — see
  suspects/creature_spell_nodes_systematic.json. Spellgorger-Weird's
  "noncreature" specificity is therefore only testable through Goremand, and
  the weird pack asserts the honest outcome: Goremand eats Weird itself
  (zone graveyard, its 2 counters ride along), 'me' survives with 2 marks.
- Dryad COLOR_IN ('W','U','B','R') is subset semantics; a gold spell straddling
  green diverges from printed text (noted in the pack, untested — no such
  castable gold in the rig).
