# 62 — Act-sense scenario wave (2026-10-10)

## Goal
12 new act-sense packs (ATTACK-SENSE 4, BLOCK-SENSE 3, CAST-PRIORITY 3, MAY-FIRE
realistic-boards 2) certifying 19 new puzzle items so BC gains attack/block/
cast-priority senses through falsifiable content-word golds. NO commits (owner law).

## Deliverables (all EXECUTED, gates green)
- Packs (tools/scenarios/, all PASS): as_free_singer, as_trade_snout,
  as_suicide_charger, as_lethal_push | bs_must_block_wall, bs_bait_decline,
  bs_chump_margin | cp_weird_growth, cp_counter_trample, cp_devil_burn |
  ms_stormwing_realistic, ms_trufflesnout_tempo.
- run_scenarios: **398/398 packs pass** (was 386/386).
- puzzle_cert: **items=199 l1_ready=36 punish_inaction=188 no_discrimination=0**
  fail_registered=11 (1/3/7 classes, unchanged). All 19 new items null=0.00,
  nd=False, punish=True; 17/19 l1_ready (cp_weird one_of + tempo-ladder attack:
  l1=False — multi-ask/handle-menu items).
- make_eval_split: families 80 | eval 33/58 | train 47/141 | new assigned [] (all
  item families already TRAIN-side: Mistral Singer, Daybreak Charger, Tempered
  Veteran, Pridemalkin, Pitchburn Devils, Spellgorger Weird, Stormwing Entity,
  Trufflesnout).
- packrec_v2: episodes=143 asks=267 gold_lines=199 gold_rows_with_ground=98.
- pytest MTG_bot/core -q: **2502 passed + 2 subtests**; pytest tools/audit
  tools/training -q: **164 passed** after re-pinning 3 dated snapshots in
  test_bc_v2.py (180->199 join; handle grounding 178/210 -> 196/230 (85.2%);
  choose-digit 71/74 -> 75/78; gold-rows-with-ground 88 -> 98).

## Engine truths learned (compiled goldens authoritative)
- **Riddleform is an Enchantment (P/T None)**; its cast-trigger SET_PT/GRANT_TYPE
  (Sphinx)/GRANT_ABILITY (FLYING) are ALL IS_SOURCE — it pumps ITSELF, and the
  granted creature type does NOT make it legal to attack (combat legality reads
  base identity.types). Pack cp_riddleform_pump was RETIRED for cp_weird_growth.
- **Spellgorger Weird** (train): "whenever you cast a NONcreature spell, put a
  +1/+1 counter on target" with the target selector IS_SOURCE + CHOOSE mode and
  single candidate -> AUTO-PICK, no ask (F1 law confirmed live).
- **Hobblefiend** burn lane: activation's sacrifice cost is itself an ASK when
  >1 own creature qualifies (r22a vocabulary reopens it via 14b); the death-burn
  TARGET ask follows in the same step's decision stream; "player:1" is a real
  vocab word for any-target asks.
- **Pitchburn Devils / Hobblefiend combat**: trample is compiled onto Hobblefiend
  after activation; damage-MARK ledger clears when the damaged card leaves the
  battlefield (CR 120.6) — dead cards' marks are NOT in the expect damage lane.
- **Trufflesnout** ETB choose option '0' = counter (target IS_SOURCE, auto),
  '1' = gain 4 life; vocab ('0','1') -> null=vocab[0]='0' so the '1'-gold
  discriminates at its own ordinal and the '0'-gold is falsified downstream.
- **Rousing Read** compiled record carries NO SpellAbility (only ETB trigger +
  statics) — aura-cast target lane unproven, avoided.

## Harness laws pinned this wave (add to the pack-authoring checklist)
- combat `block` map values: `null` for "blocks nothing" — the string "NONE"
  raises KeyError (maps resolve through handles; only the ASK vocabulary has the
  word NONE).
- expect `damage` lane defaults to {} — every combat dealing marks MUST be
  pinned (dead cards' marks vanish).
- combat on the init turn works for array-battlefield creatures (no sickness);
  a card ENTERING that turn is sick (needs a full-turn cycle) — Stormwing/
  Trufflesnout ladders need the 2x end_turn/advance_turn spacing.
- Null-replay pass-word law (puzzle_cert:75-85): null answers the ask with the
  first PASS_WORD∈vocab (PASS/NONE/DECLINE/skip), else vocab[0]. Hence: ATTACK
  golds discriminate at their own ordinal; DECLINE/NONE/'0'-gold rows are
  null-equivalent AT THEIR ORDINAL and are honest only because a downstream
  lane falsifies them (honest note kept in pack notes).
- A map-claimed attacker that also has a queued word: the queue word is NOT
  consumed by the map site; keep decisions scripts aligned to the ASK arrival
  order (handle-sorted), not to the map.

## Files
tools/scenarios/{as_*,bs_*,cp_*,ms_*}.json (12), tools/audit/puzzle_corpus.json
(199), tools/audit/eval_split.json, tools/training/episodes_v2.jsonl,
tools/training/test_bc_v2.py (3 snapshot re-pins).
