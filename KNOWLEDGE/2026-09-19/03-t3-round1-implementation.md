# 2026-09-19 — T3 round 1: grammar additions A–N (ability_tree.py + test_ability_tree_t3.py)

Status: **DONE and verified.** Implements items A–N of the binding decision doc
`KNOWLEDGE/2026-09-19/02-grammar-decision-t3-round1.md`. Grammar task only —
no changes to `compiler/`, templates, or any other module.

## What landed in `MTG_bot/core/ability_tree.py` (additive only)

| Item | Addition |
|---|---|
| A | `FAtomPred.POWER_LE`, `POWER_GE` (count slot; power-only comparisons) |
| B | `FAtomPred.NAME_CONTAINS` (string_value slot) |
| C | `Selector.zones: tuple[Zone, ...] = ()` — additive: effective set {zone} ∪ zones |
| D | `Verb.CAST`, role table `{"source": True, "cost": False}` (cost = extra cost, not the spell's own cost) |
| E | `QThisTurn(kind: ThisTurnKind, referent: ControllerRef)` + `ThisTurnKind{LIFE_GAINED, CARDS_DRAWN}`; added to `Quantity` |
| F | `DamageDealtEvent.source/combat`, `ZoneChangeEvent.subject`, `CastSpellEvent.controller/from_zone/ordinal` (all opt, None = pre-T3 behavior) + new `CardDrawnEvent`, `LifeGainedEvent`, `SacrificeEvent` (each: `controller: ControllerRef` only) |
| G | `Verb.LOSE_GAME`, role table `{}` |
| H | `ZonePosition{TOP, BOTTOM}` + `Zone.position: ZonePosition \| None` |
| I | `EachPlayer(ref: ControllerRef, effect: Effect)` (added to `Effect` union) |
| J | `EtBState(tapped: bool = False, initial_counters: tuple[(CounterKind, Quantity), ...] = ())`; no-op `EtBState()` rejected; added to `Ability` union |
| K | `CostModifier(filter, controller_ref, delta)` + `CostDelta` union of 5: ReduceGeneric, IncreaseGeneric, ReduceMana(color∈{WUBRG}), IncreaseLife, WaiveMana |
| L | `EmblemAbility(embedded: Ability)` — wraps Triggered/Static/Activated (Atom is an Effect, not an Ability → rejected) |
| M | `Verb.PAY`, role table `{"cost": True}`; `"cost"` added to `_ROLE_TYPES` as `Cost` |
| N | `ControllerRef.OWNER` (owner-scoped zones, e.g. `Zone(HAND, OWNER)`) |

## Serialization design (the one new mechanism)

`_OMIT_IF_EMPTY: dict[type, frozenset[str]]` — applied **only to the new
optional fields**: `Selector.zones`, `Zone.position`, `ZoneChangeEvent.subject`,
`CastSpellEvent.{controller,from_zone,ordinal}`, `DamageDealtEvent.{source,combat}`.
`to_dict` omits the key when the value is `None` (opt fields) or `()` (tuple
fields); `from_dict` re-injects `None` / `()` for missing keys. Pre-existing
optional fields keep their old behavior (e.g. `CostTap.target` still
serializes `"target": null`) — pre-T3 byte-stability was verified, not
assumed:

- **14/14 pinned pre-T3 fingerprints byte-identical** (captured before the
  first edit, asserted by `test_pinned_pre_t3_fingerprint` + a recursive
  `_assert_no_t3_keys` walker proving no omittable key leaks into pre-T3
  trees).
- 724 pre-T3 tests still pass untouched; no validation changed (e.g.
  `FAtom(CMC_LE)` without count remains accepted — the pre-T3 quirk is
  preserved).

Other wiring: closed tables `_Q_CLASSES/_E_CLASSES/_A_CLASSES/_EV_CLASSES/
_COST_DELTA_CLASSES` + `_is_cost_delta`; `_FATOM_RULES` rows; `_ENUMS`,
`_DATACLASSES`, `_SPECS` (incl. the new `counter_placement` decode
`[CounterKind, Quantity] → tuple`); `_ATOM_VALUE_TAGS` + `"Cost"`;
`_UNION_CONVS` + `"cost_delta"`; module docstring "Events: 16".

## Verification (2026-09-19)

- `pytest MTG_bot/core -q` → **833 passed** (724 + 109 new).
- `pytest MTG_bot/core/test_ability_tree_t3.py -q` → **109 passed**: 14 pinned
  fingerprints + omit-walker · 45 round-trip catalogue entries (A–N) · 41
  rejection cases (≥2 per new construct) · omit present/absent key tests ·
  verb-role and FAtom-rule table pins · enum membership · fingerprint
  sensitivity · `walk` over EtBState counters.
- pyright both files → **0 errors / 0 warnings / 0 informations**.
- ruff format --check both files → clean; ruff check test file → clean.
  ruff check ability_tree.py → 50 findings, **all pre-existing style**
  (HEAD had 40; delta = +10 TRY004 from new `__post_init__` type checks in
  the module's pinned `ValueError` convention — see PITFALLS 2026-09-19 for
  the environment's config-less ALL-ruleset discovery).
- Full repo: 860 passed / 23 failed — the **identical pre-existing** 23
  (rule_engine + strategic_brain + test_full_system); proven unrelated
  (no failing module imports `ability_tree`; failures reproduce with the
  file stashed to HEAD).

## Counts after T3

Verb **38** · FAtomPred **29** · EventSpec **16** · Effect **7** (6 + EachPlayer)
· Ability **9** (6 + CostModifier/EtBState/EmblemAbility) · Quantity **7**
(6 + QThisTurn) · CostPart **9** · CostDelta **5** · ControllerRef **6**
(incl. OWNER) · ZonePosition **2** · ThisTurnKind **2**.
