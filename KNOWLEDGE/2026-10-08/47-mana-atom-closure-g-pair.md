# 47 — Mana-atom closure: G-at-X=2 twin + two-source treasure pair (2026-10-08b)

Closes the mana-color-choice TRAIN coverage after 46's volume wave. Eval fail-core
(Prismite / Palladium Myr / Traitorous Greed / Feat of Resistance) stays un-packed by
rule; TRAIN twins now span W? no — golds U,B,R,G taught, never W (vocab[0] = null-word).

## Added (2 packs, 3 corpus items, all on frozen TRAIN families)
- `sanctum_harvest_g_dryad.json` — Sanctum X=2 gold **G**, chain-proved same-window by
  paying {1}{G} Quirion Dryad; null {W:2} -> Dryad unpayable -> raise. (46 covered R,U,B
  at X; G was the missing color gold.)
- `treasure_chain_g_then_r.json` — TWO independent per-tap color decisions on one board:
  t1 gold G -> Portcullis Vine, t2 gold R -> Shock-kill. 2 items, each null falsified
  separately. Teaches per-source choice, not one memorized answer.

## Numbers (`.venv/bin/python tools/audit/puzzle_cert.py` ; `make_eval_split.py` ; 2026-10-08)
- packs 384->**386**; scenarios **386/386**; corpus items 177->**180** (+3 train);
  `no_discrimination=0`, every new item null_score=0.0, gold position != vocab[0];
  eval side frozen 33 fam/58 items, `new assigned: []`; episodes_v2 131 eps / 180 gold
  lines; TRAIN mana-ask lines 10->**13**. Gates: core 2491+2st, tools **153**
  (test_bc_v2 join pin 177->180, dated comment).

## Engine mechanics discovered (probe-verified, useful for future packs)
- Turn-start base draw takes the **last-declared** library card in pack order (both with
  and without `library_top`); put a fodder card last in declaration to absorb it.
- `See the Truth` / search windows present candidates in the ask vocab sorted by card
  index ascending -> to keep gold off vocab[0], declare the weak/other candidate first.
- `Temple of Malady` {T}: Add {B} or {G} is **un-askable**: no activated-ability slot
  (idx0 = ETB trigger, not_activated:TriggeredAbility). Fixed-or-fixed mana offers raise
  no color ask -> fail-registered; the corpus "Temple mana" item is the ladder pack's
  Sanctum ask. Any-color adds (Meteorite, Treasure, Prismite) DO ask.
- M21 Gift-shape (Alchemist's Gift keyword choice, "%your choice of%"/"%either%") has no
  train-side expressible twin -> closest analogs shipped: Trufflesnout modes ladders.
- Dedup law applied: 6 of 8 freshly authored probes exactly duplicated 46's wave (same
  gold+spell+falsification lane) and were deleted before cert; corpus stays undiluted.
