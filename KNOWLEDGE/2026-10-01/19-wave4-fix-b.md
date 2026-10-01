# 19 — Wave-4 fix-b (r21b): activation-lane cost fold, dual-count pred, dies narrowing, graveyard sweep

Batch: fix-batch **21b** of the wave-4 suspect backlog (engine editing
authorized). HEAD at start: `8d4bbe7`. Eight suspects in scope. Card truth
from the local dump + printed IR, never memory. NO commits, NO /02-doc or
golden-IR or `state.py` edits.

## Verdicts (8 suspects)

| Suspect | Verdict | Root cause / disposition |
|---|---|---|
| Basri Ket −2 ("that many" life) | **FIXED → promoted, expectation CORRECTED 8→11** | `THAT_MANY_COUNT` had no producer register on a TRIGGER antecedent (declaration is the antecedent; no preceding producer atom). `_fire` now journals the whole declaration group into `ctx.bindings["declare_attackers"]` and the prop falls back to it when `result` is ABSENT (result keeps strict precedence — Kinetic Augur untouched). The pack's `life: 8` was an author misprint written during a crash: printed math = tiger 5 + wolf 2 + 2 tapped-attacking Soldiers ×1 = 9 → 20−9 = **11**; soldiers=2 + loyalty=1 assertions unaffected (DA trigger dedups per declaration group → one firing; tokens excluded from the census by IS_TOKEN). |
| Garruk, Unleashed −2 | **FIXED → promoted** | `CONTROLLER_COUNT_GT` unimplemented → now the dual-filter battlefield census: TRUE iff count(inner over battlefield) > count(right_inner over battlefield); each side carries its OWN CONTROLLER_IS atoms. Grammar-doc wording is polarity-sloppy — the PACK's printed direction is ground truth (3 opponent Thrulls > 1 your Beast → TRUE → loyalty 4−2+1=3). Two-player reading documented. |
| Caged Zombie (activation gate) | **FIXED → promoted, damage assertion added** | `DIED_THIS_TURN` strict-per-handle reading wrongly applied to a creature-typed handle SITTING ON THE BATTLEFIELD (it can never be the dead one) → the strict reading now ALSO requires OFF-battlefield; battlefield-living creature = existential reading. Second gate after the fix: the harness asserts `ex.damage == expect["damage"]` EXACTLY — Skyscanner's 1 mark persists on the tiger until end-turn cleanup (CR 514.2; `damage.clear()` only in `end_turn`, pop-on-death) → pack now pins `{"tiger": 1}`. |
| Epitaph (golem to library bottom) | **FIXED → promoted** | `_v_move_zone`: `bottom_dest` now also when `position is None and dest_kind == LIBRARY` (corpus scan: Epitaph is the ONLY LIBRARY+None atom; explicit TOP/BOTTOM readings byte-unchanged). |
| Tormod's Crypt (sweep vs binding) | **FIXED → promoted** | `role_handles` binding-first silently swallowed the TARGET_PLAYER designation into ONE card (binding-first lane exiled just the designated card — sweep never ran, legality green). Five-condition corpus-pinned exemption: ALL mode + EXILE verb + universal EMPTY-FAnd filter + GRAVEYARD zone + TARGET_PLAYER controller (scan: ONLY Tormod matches all five) → falls through to `resolve_selector`; `players_for_ref` TARGET_PLAYER folds a card designation via `controller_of`. |
| Sanctum of Tranquil Light | **STAYS SUSPECT (compiler STOP, 2nd cause)** | 21a's "activation lanes never fold CostModifier" was REAL but lane-dead: fixed — `build_payment_plan` takes `activation=` and folds ONLY an exactly-`FAtom(IS_SOURCE)` modifier when judge==source (leak-proof: golden audit — IS_SOURCE CostModifier hosts = Chandra's Incinerator / Discontinuity / Sanctum / Sanguine Indulgence / Stormwing Entity / Volcanic Salvo; ONLY Sanctum also carries an ActivatedAbility). Residual failure `cost:mana_generic:4<5` is now purely the COMPILER defect: amount compiled as `1 * QCount(NAME_EQ 'Shrine')` — NAME_EQ is exact-name and matches nothing; the printed clause is a SHRINE **subtype** census (SUBTYPE_EQ) → fold computes 1×0=0. Fail-only witness; finding amended in place. |
| Fabled Passage (enters tapped) | **STAYS SUSPECT (compiler STOP) + falsifiability PIN** | Engine applies no `tapped_on_enter` and UNTAP no-ops without the compiler's TRUE branch (no-lands) — the suspect asserts enters UNTAPPED where printed logic says tapped for <4 lands. GREEN pack `fabled_passage.json` restructured: now asserts `"tapped": {"s1": false}` — green today ONLY via the STOP; after the compiler fix the UNTAP must fire or the pack goes red. The pin makes the STOP falsifiable. |
| Furious Rise (activation) | **STAYS SUSPECT (compiler STOP)** | Phantom `ActivatedAbility(cost=(), OptionalEffect(CAST referent='result'))` — compiler mis-split of the trigger tail. Runtime flag-not-degrade raise is CORRECT; finding amended. |

## Engine changes (6 files, uncommitted)

1. `binding.py::_fire` — DECLARE_ATTACKERS firings write the whole
   journalled declaration group (rows sharing `event.declare_group`, read
   via `journal.turn_window()`) to `ctx.bindings["declare_attackers"]`.
2. `quantity.py::THAT_MANY_COUNT` — `result` first (Kinetic precedence),
   `declare_attackers` fallback, both absent still RAISES (flag never
   guess). NOTE: the prop lives BEHIND the `"event"`/`"result"` referent
   binding (`_referent_handle`) — the registers are read only inside a
   trigger firing; unit tests must bind `{"event": h}`.
3. `quantity.py::CONTROLLER_COUNT_GT` — dual-filter WORLD census (after
   the GE block); asserts both filter slots present.
4. `quantity.py::DIED_THIS_TURN` — `creature_typed` now additionally
   requires `world.zone_of(handle).kind != ZONE_BATTLEFIELD`; subject-
   match row still wins; graveyard/exile/hand creature handles keep the
   strict census (Gadrak, Standard Bearer).
5. `selectors.py::role_handles` — the five-condition `graveyard_sweep`
   exemption (see verdict table); `Verb` added to the ability_tree import.
6. `legality.py::build_payment_plan` — `activation: Handle | None = None`
   kwarg; fold judge `judge = mana_use if mana_use is not None else
   activation` (gate: judge==ctx.source, namespace card); `activation_lane
   = mana_use is None` and on that lane ONLY `isinstance(mod.filter,
   FAtom) and mod.filter.pred IS IS_SOURCE` folds; `mod.condition` now
   evaluated against `judge` (pyright: `assert judge is not None`). Call
   sites pass `activation=handle`: legality `ability_playable` (~960) +
   `activate` (~1343), query activation enumerations (~250/~273).
   query.py:522 PAY atoms, stack.py and verbs.py:1160 deliberately NOT —
   a PAY atom is not an activation.
7. `verbs.py::_v_move_zone` — `bottom_dest` includes LIBRARY+None.

## Unit fence: `MTG_bot/core/test_executor_r21b.py` (17 tests)

5 classes, one per fix, hand-built IR (Sanctum fold + 3 negative controls:
universal-filter no-fold on the activation lane, legacy no-kwarg caller
byte-identical, foreign IS_SOURCE host discounted nobody; GT tie/majority/
per-side-filters/e2e-condition-gate; THAT precedence/fallback/single/
raise; DIED battlefield-existential vs graveyard-strict with the dies row
proven journalled; Tormod ALL-sweep vs CHOOSE-binding-first).
`test_executor_r19a.py::test_other_creature_still_answers_false` AMENDED
(the narrowing flips its battlefield case to existential True; the strict
False moved to a graveyard handle in the same test — the census lives on).

## Gate results (2026-10-01, all green)

| Gate | Number | Command |
|---|---|---|
| pytest core | **2239 passed + 3 subtests** (2222 baseline +17 r21b, 1 AMENDED, 0 regressed) | `pytest MTG_bot/core -q` |
| games | **0 crash classes**, survived 86/100 | `python -m MTG_bot.core.executor.games --seeds 100 --pool all` |
| catalog | **0/10 diverging — no repin** (every fix narrowly gated; traces byte-stable) | `python tools/traces/catalog.py compare` |
| wave-4 lint | **43/43 covered, consumed** | `python tools/audit/wave_builder.py --wave4 --lint` |
| scenarios | **248/248** (243→248: five promotions; fabled_passage restructured, still green) | `python tools/run_scenarios.py` |
| grammar PC | PC-1 301/305 · PC-2 634/639 · PC-3 0 · PC-4 0 — **unchanged** (no IR touched) | `tools/measure_grammar.py` |
| lint hygiene | ruff Δ0 vs HEAD on every touched file; new file clean | `ruff check --output-format concise` |

Promotions MOVE packs into `tools/scenarios/` stripping `status`/`finding`
(keep `notes`): basri_ket_minus_two, caged_zombie_died_condition,
epitaph_golem_bottom, garruk_minus_two, tormods_crypt. Suspects dir: 12
files left, incl. the three 21b STOP witnesses with amended findings.
(Orchestrator audit 2026-10-01: basri + caged initially promotion-COPIED —
suspect JSON left alongside the new scenario file = double-state; both
stale suspect JSONs deleted, count corrected 14→12.)
