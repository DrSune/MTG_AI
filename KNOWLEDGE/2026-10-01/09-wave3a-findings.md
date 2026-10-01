# 09 — Wave 3a findings (static/keyword cohort, batch A: Anointed Chorister → Makeshift Battalion)

28 cards, one scenario pack each, printed-text-as-truth law. Outcome: **16 green**
(`tools/scenarios/`), **12 suspect** (`tools/audit/suspects/`, `status`+`finding` schema).
Gates after landing: runner **164/164** (`tools/run_scenarios.py`), suite **2168 + 4
subtests** unchanged (`pytest MTG_bot/core -q`).

## Two rig laws (binding for every future pack author)
1. **Summoning sickness**: creatures scripted in via the `enter` op (hand→battlefield)
   are NEVER offered an attack this turn. Attackers must be declared
   `"zone":"battlefield"` in `cards` at setup (pattern: `combat_sickness_haste.json`).
   Mis-scripting cost 7 false-positive combat packs before discovery.
2. **Hand baseline is 0, not 1**: `begin_turn(self.p0)` runs in the runner `__init__`
   BEFORE the 6 `Library 0..5` fillers are added, so the draw-step draw is a no-op on
   the empty library. Opt/ETB/activation-draw packs must expect baseline 0 + n draws.
   `end_turn` is only the end-step marker — no further draw without `advance_turn`.

Corollary: **Skyscanner is a 1/1 Thopter WITH flying** — never usable as a
keyword-negative neighbor (assert `["FLYING"]`; negatives must be delta-shaped).

## Compiler/activation indexing trap
Record `abilities[]` includes StaticAbility rows: Chromatic Orrery's draw activation
is **idx 2** (0=static MANA_POLICY, 1={T}: add 5C, 2={5}{T}: draw). `idx 1` silently
"passed" while only ADD_MANA fired. Always enumerate `binder.handle_record[h].abilities`.

## Suspect root causes (grep-verified against `MTG_bot/core/executor/`)
| Gap | Evidence | Suspect packs |
|---|---|---|
| **LIFELINK is a dead keyword** — zero grep hits in executor; `layers.keyword_of` reports it (lane green) but no DEAL_DAMAGE→life-gain leg | life lanes frozen at 20 across 4 packs | anointed_chorister, blood_glutton, indulging_patrician, light_of_promise (downstream) |
| **PROWESS dead keyword** — KeywordAbility compiles (templates_b5b:552), zero executor handler | power unchanged after 2 noncreature casts | heartfire_immolator, jeskai_elder |
| **BATTALION dead keyword** — zero handler; compile GAP "requires params not available from identity alone" | counters {} after 3-attacker group (combat lanes green) | makeshift_battalion |
| **No ZoneChangeEvent replacement hook** — ReplacementRegistry only exposes player-damage / life-gained / death hooks; compiled ReplacementAbility never consulted | entering creatures land, not exiled | containment_priest |
| **Granted triggered abilities never drained** — `layers.granted_abilities(host)` shows the CreatureDies trigger registered; trigger-firing path ignores granted rows | hand 0 after host death | infernal_scarring |
| **Cost-target bleed** — `legality.activate` binds the cost's TARGET-mode sacrifice pick as `bindings["target"]`; effect self-selector resolves through `role_handles('target')` → counter lands on the SACRIFICED card | PUT_COUNTER journalled onto Walking Corpse | hobblefiend |
| **REVEAL verb not layer-parseable (12e)** — card crashes at install/enter | NotImplementedError on enter | conspicuous_snoop |
| **DamageDealtEvent filter over player subject = 12c query surface** — trigger install raises | NotImplementedError on enter | hooded_blightfang |

## Positive confirmations (lanes proven live)
- `QDistinctColorCount` (Orrery draw-per-color), keyword layers (FLYING/TRAMPLE/
  DEATHTOUCH/REACH/VIGILANCE/FIRST_STRIKE/LIFELINK reads), PT statics (anthem,
  Kaervek −1/−1 SBA burials, zombie +1/+0, aura +2/+0 on the combat lane),
  conditional LOSE_ABILITY(DEFENDER) (Tyrannodon attacks with a 4-power friend),
  attack restriction (Gadrak held by <4 artifacts, released by 4), rummage
  bottom-order (Harbinger: survivors `Library 1, Library 0` on top), vigilance
  untap, granted-keyword activation (Fetid Imp deathtouch), ETB-draw statics
  (Chandra's Incinerator 6/6 trampler), while-condition static (Gnarled Sage).

## Numbers
| Number | Value | Command | Notes |
|---|---|---|---|
| wave-3a batch A | **28 cards → 16 green + 12 suspect** | `tools/run_scenarios.py --dir /tmp/opencode/staging` | all 12 divergences root-caused (table above) |
| runner gate | **164/164** (148 baseline + 16 new) | `tools/run_scenarios.py` | zero regressions |
| suite gate | **2168 + 4 subtests** unchanged | `pytest MTG_bot/core -q` | engine untouched (frozen) |
