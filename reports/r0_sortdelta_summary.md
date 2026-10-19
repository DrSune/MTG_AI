# R0 Zone-Fold Byte-Delta — MEASURED (pre-registration)

Tool: `/tmp/opencode/mk_sortdelta_r0.py` (measurement-only fold simulation on the
`to_dict()` tree); JSON: `/tmp/opencode/r0_sortdelta.json`. 0 exceptions.

## Headline numbers
- **M21: 219/305 changed — EXACTLY the inventory prediction, deviation 0.**
  Changed set == cards-with-selectors (219). All 305 committed goldens byte-fresh
  vs live baseline; every changed card has a golden file; 0 golden-less.
- **ZNR: 108/281 changed (truth).** The prompt's "expect 0" hypothesis is
  REFUTED: the fold deletes the `zone` key on EVERY Selector, so bytes change
  even with 0 twins — neutral-drop + zone-key-removal alone flips all 108.
  Matches inventory `cards_with_selectors: ZNR 108`, deviation 0.
- Per-cause (cards, non-exclusive): zone_key_removed 219+108 (universal);
  twin_fold 10+0; neutral_zone_drop 31+8 (neutral C2 selectors 39+9=48 ✓);
  zone_position_change 9+0 (all twins except Necromentia, whose
  [GRAVEYARD,HAND,LIBRARY]/TARGET_PLAYER concat is already canonical-sorted);
  dedup_collapse 0 — no literal duplicate zone inside any `zones`.
- **Content-preservation: PASS, 0 failures.** Every Selector's folded zone-set
  equals {zone}∪zones exactly — nothing added/lost (no compiler.py:1050-style
  drop observable pre-migration). **Idempotence: PASS** (fold∘fold = fold).

## Twins → KEYED lanes (10 M21 twins)
L1-exposed (ONE_OF ∧ LIBRARY-primary, no TOP → naive ∃-LIBRARY opens the r19b
window lane): Basri's Aegis, Chandra's Firemaw, Garruk's Warsteed, Liliana's
Scorn, Sanctum of All, Teferi's Wavecaster. L2+L3-naive-∃ re-point-exposed:
Chandra's Magmutt, Leafkin Avenger (folded len-2 zones ⇒ SINGLETON rewrite
correctly closed; ∃ re-opens r21a). L4 clause-shape (GRAVEYARD∧TARGET_PLAYER,
mode CHOOSE ≠ ALL): Necromentia. No lane: Unsubstantiate (content control).
**Falsifier battery: 11 named executor-observed items** in the JSON.

## L6 / Waker of Waves
In changed M21 set ✓ (`abilities[1].cost.parts[2]`, zone=HAND singleton →
zones=[HAND]). LOUD census: the HAND-zone CostDiscard shape has population
**10** (M21 9 + ZNR 1: Thrill of Possibility, Demonic Embrace, Ghostly
Pilferer, Seasoned Hallowblade, Sanctum of Shattered Heights, Niambi, Subira,
Sparkhunter Masticore, Tormenting Voice + Waker); only Waker passes the
self-referential-filter gate, so ∃-HAND is behavior-neutral for all 10 — but
all 10 re-bake bytes.
