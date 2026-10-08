# 46 — Volume wave: mana-color TRAIN twins + Harbinger/Gift-shape ladders (2026-10-08)

Target = stable fail-core of /45 (6 items: mana-color atom eval-side-only +
Harbinger a2 + Gift a1 thin twins). 7 new packs, 9 new items, ALL on frozen
TRAIN families (`new assigned: []`, no new families).

## M21 mana-ask census (DB mode=ro, oracle text = evidence)
`%mana of any color%|%any one color%|%color of your choice%|%Add%any%` = 11 rows:
Prismite/Meteorite/Traitorous Greed/Palladium Myr (EVAL-side, OFF-LIMITS),
Feat of Resistance (EVAL, protection-color not mana anyway), Chromatic Orrery
(spend-as-any = no ask, /44 phantom law), Terror of the Peaks (match artifact,
no ask), Gadrak (ask lives in the Treasure token, no pack address — r24a
keyless-mint limitation), Sanctum of Fruitful Harvest (TRAIN ✓). <3 distinct
train-side NEW cards ⇒ sanctioned fallback: variants of existing train-side
mana-ask families (Treasure/Sanctum).

## Authored (pack → family → side → ask)
- `treasure_pay_r_chain` → Treasure TRAIN: {T},Sac ask gold **R**, empty seed,
  Shock {R} payable ONLY with asked color (null W → cast illegal).
- `treasure_pay_g_chain` → Treasure TRAIN: gold **G**, {C:1} seed, Snarespinner
  {1}{G} chain-proof.
- `sanctum_harvest_b_not_w` → Sanctum TRAIN: add-X (X=1) gold **B**, Eliminate
  {1}{B} chain; null W+C illegal. (Prior train golds W/U/B/U + sanctum U;
  atom now taught across W,U,B,R,G golds with 6-vocab menus.)
- `empath_ladder_take_big` / `empath_ladder_real_dreadmaw` → Fierce Empath TRAIN
  (Harbinger-shape: MV>=6 typed-library ONE_OF). TWO legal creatures ⇒ engine
  asks; vocab order = PACK CARD ORDER; vocab[0] = first-listed legal creature =
  null pick. Gold = second-listed. Last pack card = Small Two (cmc 2, illegal)
  = the decision-independent begin_turn draw (library_top knob).
  item2 uses a REAL printed candidate (Colossal Dreadmaw MV6).
- `trufflesnout_doomed_take_life` / `trufflesnout_last_life_line` →
  Trufflesnout TRAIN (Gift-shape choose-one, mode vocab '0'/'1', null='0'):
  gold '1' (life) both. L1: doomed snout + own Shock — counter is pure waste,
  life lane falsifies (24 vs 20). L2: life 3, unblocked 3/3 hit — gold banks +4
  (lands at 4), counter-lane dies at 0; falsifies on life AND power lanes.
  NOTE: runner `world.life` sets BOTH seats' life (first-pass FAIL life[1]
  20≠3 → expect 3). Seat-1 combat needs end_turn+advance_turn first.

## Corpus/split delta (cert chain FINAL-STATE)
items 168→**177** (+9, every new item null=0.0 punish-inaction),
no_discrimination **0**, fail_registered 11, punish_inaction 157→166,
l1_ready 18, mean_random 0.3285. TRAIN mana-ask lines **7→10**.
Split: families 80 unchanged, eval 33 fam/58 items unchanged,
train 47 fam / 110→**119** items, new assigned [].
last_life_line's ATTACK/block asks are runner-plan-lane (not extracted as
items) — 3 scripted words, 1 corpus item.

## Gates (final-state chain puzzle_cert→make_eval_split→packrec_v2 then)
core **2491 +2st** | scenarios **384/384** | tools **153**
(pins re-pinned dated: join 168→177, hs 174/206→178/210 = 84.5→84.8%,
ch 67/70→71/74, ground rows 84→88; test renamed test_joins_..._at_177).
