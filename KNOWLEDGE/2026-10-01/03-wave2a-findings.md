# 03 — Wave 2a findings (spell/casting cohort, engine FROZEN)

Cohort = the 34 spell cards "Alchemist's Gift"→"Opt" of `wave2a_rows.json`.
Result: **24 green packs** → `tools/scenarios/` (gate now **108/108**),
**12 suspect packs** → `tools/audit/suspects/` (gate **0/14** — every suspect
FAILs with its documented symptom, none passes silently). Suite unchanged:
core **2112 passed + 4 subtests**, engine + `run_scenarios.py` untouched.
Life Goes On and Destructive Tampering each contribute TWO files: their green
branch lives in scenarios, their diverging branch in suspects. 22 cards fully
green, 12 cards suspects.

### Printed-promise passes (24 files / 22 clean cards)

- Counters/statics that DO read out through the PT lanes: alchemists_gift
  (+1/+1 + lifelink branch via decision '0'… deathtouch-or-lifelink ask vocab
  `('0','1')`; PT lane passes because the compiled buff is a MODIFY_PT ledger
  entry, NOT a counter — see the counter gap below), defiant_strike (+1/+0 +
  draw), burn_bright (+2/+0 sweep), grasp_darkness (-4/-4 buries a 1/3, SBA),
  crash_through (trample static + draw), heroic_intervention (hexproof+
  indestructible until a giant kill is declined).
- Zone/assembly: eliminate (Mv≤3 gate: 3/3 dies, 4/4 survives), finishing_blow,
  lilianas_scorn (destroy + search tail), legions_judgment (P≥4 gate),
  enthralling_hold (see control proof below), frost_breath (freeze survives
  opponent untap: PREVENT_EFFECT UNTIL_NEXT_STEP; after advance_turn both
  targets still tapped).
- Draw/filter engines: opt (scry-top then draw; library lane `"*"` wildcard),
  frantic_inventory (draws 1 + N copies in GY), bad_deal (hand[0]=2 after
  begin_turn draw minus 2 forced discards; both players −2), alchemists-family
  tutor tails: grim_tutor (cardinal to hand, life 17), goblin_wizardry
  (2× 1/1 Goblin Wizard tokens; token PT 1/1 probe-verified only — no
  token-PT lane), goremand_sacrifice_cast (sac-as-additional-cost via
  `decisions:["fodder"]`, ETB forces OPPONENT sac, FLYING+TRAMPLE keywords).
- Search tails on **basris_aegis** and **lilianas_scorn** EXIST and AUTO-FIRE
  (named card lands in hand, NO ask) — the wave-planning IR reading "missing
  search tails" was WRONG; no IR gap, so no suspect filed.
- life_goes_on (plain branch +4, life 20→24) and tampering_destroy_artifact
  (branch 0 destroys the artifact; see suspect twin).
- enthralling_hold control proof: after cast, `executor.controller_of` overlay
  flips card:1→player:0 (probe); packed law = the stolen creature cannot
  attack the turn it's gained (legit CR 302.6 sickness — pack asserts NO
  attack), then 2× advance_turn OFFERS `attack:card:1:3` and the combat lane
  lands damage (life 1:17). "Can't choose an untapped creature" is a negative
  legality with no pack lane — probe evidence only.

### Suspects (12 packs; exact engine strings inside each file)

- **Designation-dead family (5 cards, LOUD — the spell cannot be cast at
  all)** `ValueError: executor: cast: illegal target selection:
  selection:count_below_min:0<1` (stack.py:244):
  duress / mind_rot / necromentia — TARGET_PLAYER validated against a CARD
  population that never contains players, min-count 1 unsatisfiable;
  experimental_overload — compiled "Exile Experimental Overload" (exile SELF)
  as TARGET/BATTLEFIELD/IS_SOURCE: battlefield population empty at
  designation; hunters_edge — 2×TARGET raises `NotImplementedError: …
  more than one TARGET selector needs per-slot designation (arc 3)`.
  These cannot silent-no-op: the error IS the audit signal.
- **Counter→PT fold is MISSING ENGINE-WIDE** — basris_solidarity (canonical):
  counters dict writes fine (`{PLUS_1_PLUS_1:1}` lanes PASS) but
  `power[a]: expected 2, got 1`. `_v_put_counter` (verbs.py:412) only writes
  counters; `durations.effective_pt` (durations.py:267) folds ONLY MODIFY_PT/
  SET_PT ledger rows. No counter→PT consumer exists; trufflesnout.json's green
  PT asserts are coincidence (that token compiles at base 2/2). Every
  "put a +1/+1 counter" card's PT promise rides on this one gap.
- **IS_PERMANENT = on-battlefield** — fungal_rebirth: targeting a permanent
  card IN THE GY raises `selection:off_population:card:1`; the predicate
  (quantity.py:457) is `zone_of(h)=="battlefield"`, so "permanent card from
  your graveyard" is unsatisfiable exactly where the printed text needs it.
- **Silent semantics (5)**: life_goes_on_if_died — died-this-turn branch never
  fires (`life[0]: expected 28, got 24`; plain branch green); discontinuity —
  END_TURN machinery WORKS (buff reverts 1/1, life fine) but self goes
  `expected exile, got graveyard` (printed "…including this card") AND the
  {2}{U}{U} cost reduction never applies (seed U:3 raises
  `cost:mana_generic:0<3`; U:5 `cost:mana_generic:2<3` — full generic
  charged; green run needed U:7/W:1); cultivate — BOTH searched lands enter
  battlefield UNTAPPED (`zone[pl]: expected hand, got battlefield`,
  `tapped[fo]: expected True, got False`; SEARCH destination hardcoded
  BATTLEFIELD, no ONE_OF ask); tampering_no_block — branch 1 only selectable
  if an artifact is ALSO designated (branch choice entangled with target),
  and "creatures without flying can't block" is DEAD: ask
  `block:card:3:1 => (card:2, NONE)` offered to a non-flying blocker, forced
  block lands (`blocked[atk]: expected [], got ['wall']`, life 20 not 18);
  chandra_heart_of_fire — entering planeswalker seeded NO loyalty counters
  (`counters[ch]: expected {LOYALTY:5}, got {}`); probe dump: seed R:5, cost
  {3}{R}{R} paid exactly → pool {R:6} (−9 ADD_MANA spillover; no mana-pool
  lane to pack).

### Harness facts established this wave
- Every pack card MUST carry `"key"` (runner KeyErrors otherwise).
- `begin_turn(p0)` DRAWS the top library card when library non-empty (raw
  library order is bottom→top).
- Color-choice ask vocab = digits `('0'..'4')`; branch asks `('0','1')` =
  branch index; sacrifice-additional-cost = `decisions:["<card-key>"]`.
- No lanes exist for: mana pool, controller, token PT, chosen-color
  protection, negative legality. Evidence for those promises is probe dumps
  only (runed_halo precedent); documented rather than silently dropped.

Verification: `tools/run_scenarios.py` → **108/108**;
`tools/run_scenarios.py --dir tools/audit/suspects` → **0/14** (all fail,
each on its documented line); `pytest MTG_bot/core -q` → **2112 + 4 subtests,
0 failed**. Engine, runner, and pre-existing 84 packs byte-identical.
