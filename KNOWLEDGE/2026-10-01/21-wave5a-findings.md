# 21 — Wave 5a: trigger/replacement cohort (16 cards)

Date: 2026-10-01. Batch rows: `/tmp/opencode/wave5a_rows.json`.
Gates at close: `tools/run_scenarios.py` **258/258** (248 prior + 10 new green);
`pytest MTG_bot/core -q` **2239 passed + 3 subtests** (engine/compiler untouched).

## Green packs (10, tools/scenarios/)
basri_ket_emblem, battle_rattle_shaman, burlfist_oak, chandras_pyreling (positive
lane), dire_fleet_warmonger, garruk_unleashed_emblem, griffin_aerie, havoc_jester,
library_larcenist, lilianas_scrounger.

## Suspects (7, tools/audit/suspects/)
1. **self-dies triggers silent — SYSTEMATIC (silent)**. `events.py` journals
   `KIND_ZONE_CHANGE` **before** `KIND_CREATURE_DIES` in the same diff loop, and
   `binding.on_events._lifecycle(attach=False)` detaches the leaver at the
   ZONE_CHANGE row — the dead card's own "when this creature dies" trigger is
   unregistered before its dies row is matched. Evidence (thallid probe):
   `attached [(card:0,0)]` pre-combat, `[]` after; journal dies rows == 1;
   `fire_all() == 0`; token 0. No test or green pack had ever driven a
   self-dies trigger (r21b tests only the `DIED_THIS_TURN` *condition* lane,
   which reads the journal and works). Repros: deathbloom_thallid.json,
   goblin_arsonist.json (+ conclave_mentor lane B).
2. **conclave_mentor** (silent, two gaps): no CounterPlacedEvent *replacement*
   consumer (registry hooks damage/life/death/zone-change only) — Basri +1 under
   Mentor gives 1 counter, expected 2; plus the self-dies gap (gain-life lane,
   life 20 vs 22).
3. **adherent_of_hope** (silent): condition-quantifier gap. "If you control a
   planeswalker named Basri" compiles to bare `FAnd(NAME_CONTAINS/TYPE_EQ/
   CONTROLLER_IS)` with no zone/quantifier atoms; `binding._fire` evaluates the
   condition against ONE subject = trigger source (TURN_PHASE row, event.subject
   None). Spy probe: `('TURN_PHASE','card:0',False)` with Basri Ket on the
   battlefield. Only true when the Adherent itself is named "Basri".
4. **chandras_pyreling_opponent_filter** (silent, negative control): the
   "to an opponent" clause is lost — DamageDealtEvent has no destination slot
   and the trigger filter compiles `FAnd([])`; Meteorite ETB damage to a
   CREATURE also buffs (expected 1/3, observed 2/3 + DS). Positive lane is
   green via Meteorite→player ETB driver.
5. **fiery_emancipation** (loud): replacement registers at attach, but the first
   damage anywhere raises `NotImplementedError: executor: damage-replacement
   source filter is later phase (C-4 damage surface)`. No observable lane.
6. **keral_keep_disciples** (loud, runner-UNSAFE): `binding.py:147
   _UNSUPPORTED_EVENTS` rejects LoyaltyActivatedEvent at **attach_pool**, which
   `run_pack` does NOT catch at setup → crashes the whole sweep. Kept OUT of
   tools/scenarios. Note: `get_supply("all")` DOES contain Chandra PWs
   (Flame's Catalyst idx0 +1 = 3 dmg each opponent; Heart of Fire idx2 +1) —
   the earlier "no Chandra in pool" claim was wrong; only the binder blocks.

## Rig laws learned this wave
- **Cast at a player is unreachable in the frozen runner**: universal ANY
  selectors enumerate every known card (library+hand fillers = 13+) + both
  seats, so forced auto-designation never fires, and cast `targets` can only
  reference pack cards (`self.handles`). Noncombat player damage must be driven
  through ETB/trigger designation (`decisions:["player:1"]`).
- **Activation sacrifice costs auto-pick `cands[:need]` (Handle-sorted)** —
  legality.py:711; the victim must be the lowest card index among controlled
  creatures (pack card ORDER, not `targets`).
- Decision-channel answers are **pack keys** (`"v"`, resolved via
  `self.handles`), not card names — `"Victim"` silently falls to vocab[0].
- Damage marks are cleared by `end_turn` cleanup — a pack whose finale is an
  end_turn step cannot assert the `damage` lane.
- `run_pack` catches every *step* exception (loud crashes are per-pack FAILs);
  only **setup-phase** (attach_pool) crashes take down the sweep.
- Engine's own dies plumbing works for OTHER cards' triggers (Massacre-Wurm
  style); only the dead card's OWN trigger is structurally silent.
