# 44 — Part 1 blindness/null repairs + Part 2 mana-color set (2026-10-08)

## Part 1 — repaired scenario artifacts (all falsify null replay; cert-verified)
- **C1 Duress = scenario bug, NOT engine bug**: filter (noncreature/nonland) works —
  Sheep never offered. Old gold `1` was the ZERO ROW. Fix: added `Shock` to opponent
  hand so `1`=discard Shock, `0`(null)=discard Opt, zero row=`2`. Word-replay verified.
- **Alchemist's Gift**: identical 1/1s → asymmetric board (Leech+lifelink attacks
  unblocked for life; Knife+deathtouch, blocked by 3/3 Foe, both die; life 7→9/5).
  All 3 alternative (0/1)-swap lines falsify distinct lanes. Learned: runner `block`
  map is **blocker→attacker** (site `block:<blocker>`, vocab attackers+NONE).
- **Track Down**: opaque `Library N` scry window + 2/3 asks gold=`top`=vocab[0]
  (no_discrimination). Runner got opt-in `world.library_top` knob (re-raises pack
  library cards above filler after filler creation). New line: 3 typed Chaff instants
  over a Plains; gold `bottom,bottom,bottom` exposes the Plains → draw fires.
- **Garruk's Harbinger branch01/02/03**: typed looked-at four (2 instants + Runt Kit
  1/1 + Snarling Alpha 4/4). **Discovery: engine FILTERS the reveal ONE_OF to the
  printed clause** — with ONE legal creature it auto-resolves with NO ask (closes the
  single-candidate phantom); with two it asks over exactly the two creatures. Gold
  Alpha (vocab[1]) vs null Runt (vocab[0]); random-order bottom → `*` lanes.
- **Ladder Jester double-sac**: identical fodders/victims → Fodder 1/1 vs 2/2, Victim
  Two 5/1 (the burn KILLS it; tanky 5/5 is vocab[0]); all 4 ladder items punish null.
- **Solemn Simulacrum**: old gold taught skipping a free search (twin-symmetric
  arbitrary). v1 rebuild exposed a cert discovery: a may-ask with no land to find
  still FIRES but is outcome-identical → **phantom ask** (`no_discrimination`,
  "expect-insensitive"). v2: Plains+Island under Draw Bait, both golds `fire`, each
  search independently falsifiable (skip → second land stays in library).
- **Havoc Jester** unchanged: sac-vanilla-keep-Jester is already value-asymmetric.

## Part 2 — mana-color-choice set (4 new packs, all PASS + cert items)
- `prismite_g_spinner` (G), `prismite_u_singer` (U), `traitorous_greed_g_spinner`
  (G pair), `meteorite_mana_tap` (U — Meteorite's previously UNtested {T} add head;
  its ability:0 is the ETB TRIGGER, activated add is idx 1). Golds never `W`
  (= vocab[0] of `_COLORS_VOCAB`) → null W makes the chain spell unpayable →
  zone/hand lanes falsify. Chain-proof: seed pool so ONLY the asked color completes
  the follow-up cast (zero extra asks).
- **Chromatic Orrery: no new pack** — spend-as-any-color has no ask and no mana-pool
  expect lane (registered in its pack note); forcing one would be a PHANTOM (§10).
- All 4 items land on FROZEN EVAL family sides (Prismite/Traitorous Greed/Meteorite)
  → `make_eval_split` reports `new assigned: []`, no new straddles.

## Gates (2026-10-08)
core **2491 +2st** | scenarios **377/377** | tools **153**.
Corpus v2: **168 items**, `no_discrimination=0`, `null_gt0_offenders=[]`,
fail_registered 11, punish_inaction 157, l1_ready 18; eval 33 fam / 58 items.
`test_bc_v2` snapshot pins updated 164→168, (180,212)→(174,206) (rate 84.9→84.5%),
(66,69)→(67,70) — comments dated.
