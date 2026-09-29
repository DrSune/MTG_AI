# Round-12c — activation legality, cost payment, query surface (2026-09-29)

Files: `MTG_bot/core/executor/legality.py`, `MTG_bot/core/executor/query.py`
(+ exports via `executor/__init__.py`); tests
`MTG_bot/core/test_executor_legality.py` (24) +
`MTG_bot/core/test_executor_query.py` (25). Uncommitted (12c scope:
executor/** + new tests + this note).

## Public API (ruling: typed IR refs, no DTOs, DESIGN_ACTION_SPACE §8.3)

- legality: `ability_playable(world, executor, handle, ability_idx, *, seat,
  stack_empty=True) -> None|reason`; `build_payment_plan -> PaymentPlan|reason`;
  `pay_costs(executor, plan, *, source, controller)`; folded `activate(...)`.
- query (Slate-shaped, §1.3/§1.4/§5.5): `legal_activations -> ActivationOption`
  (`ABILITY:PTR` rows + folded `COST_TARGET/PAYMENT`); `legal_targets ->
  TargetSlot` (per-slot candidates + cardinality + `forced`);
  `validate_target_selection(slot, chosen)`; `choose_options -> OptionChoice`
  (`OPTION:PTR*` sets); `optional_offer -> ("fire","skip")` narrowed when
  unactionable; `rest_of` for the ONE_OF/REST partition.

## Rules encoded (rule-verified findings)

- **Life payment = CR 119.4** (2024+ numbering; legacy 118.4): legal iff
  `life >= amount` — paying to EXACTLY 0 is legal (payment IS life loss;
  death is the CR 119.6/704 check after); 0-life always payable (119.4b).
  Settles the mission's "life > 1?" open question: floor is 0, not 1.
- **CR 117.3** = the general resource floor: already-tapped permanent can't
  tap; every selector cost has a candidate-count floor. CR 602.3 control gate
  added (`window:not_controller`).
- Mana fold on the `_v_add_mana` key convention (W U B R G C): color symbol ←
  own key only (C never pays G); generic ← any key, canonical order; hybrid ←
  first printed colour preferred (CR 118.13a choice, canonical witness).
- **C17 zeros**: TARGET + QAtMost designation sizes 1..n (NEVER 0); CHOOSE-mode
  and `Choose`-node up-to include 0..n. Both pinned (fixtures a/c).
- **C20**: `ActivationWindow.SORCERY` = `world.active_player == seat` (the 12b
  skeleton's own main) + explicit `stack_empty` param (executor has no stack).
- Cost vocabulary is the CLOSED grammar union — the mission's "CostExile"
  does not exist in `ability_tree`; `CostLoyalty` flags notimpl (frozen
  CardState has no loyalty field); summoning sickness CR 302.6 is NOT
  representable in frozen state (no entry timestamp) — documented over-gap.

## 12a map closures delivered (in-scope, query-side only)

ONE_OF (exactly-1) / REST (forced complement) partitions; OWNER referent =
activation source's zone controller; Zone(ANY) population (seat × PLAYER_ZONES
order). Resolution-time raises in `selectors.py` STAY (undesignated TARGET at
resolution is illegal, not guessable); `Choose` node dispatch still RAISES —
12a pin `test_unsupported_effect_nodes_raise` (test_executor_verbs.py:857)
forbids closing it here; Slate answers execute by dispatching the chosen
option subtree (`OptionChoice.options`) directly.

## Design deviations, flagged

- `legal_targets` takes `TargetSlot` into `validate_target_selection` (not the
  bare node) — candidates are computed once, sorted, reusable.
- `activate()` added beyond the mission list: folds legality+payment+effect
  into ONE engine call per §1.3 ("no five micro-decisions to tap five lands").
- Payment order mana→tap→sac→discard→counter→life is a documented simultaneity
  stand-in; sac-trigger mid-payment settle is a stack-phase debt (§1.3 note).
- May-offer actionability gates only exact-count selector roles (ALL-mode and
  numeric actions are legal no-ops on empty populations).

## Measurements

| metric | value | command |
|---|---|---|
| new tests | **49 passed** (24 legality + 25 query) | `pytest MTG_bot/core/test_executor_legality.py MTG_bot/core/test_executor_query.py -q` |
| full suite | **1864 passed / 23 failed**; 23 == HEAD failure set byte-identical (strategic_brain/full_system legacy) | `pytest MTG_bot -q` + `git stash push -u` baseline diff |
| pyright (both modules + `__init__` + both tests) | **0 errors** | `pyright MTG_bot/core/executor/legality.py MTG_bot/core/executor/query.py MTG_bot/core/executor/__init__.py MTG_bot/core/test_executor_legality.py MTG_bot/core/test_executor_query.py` |
| ruff | new files **0 findings**; `executor/__init__.py` **21 == HEAD's 21** (delta 0) | `ruff check --output-format=concise` + stash baseline |
| golden drivers | Visionary idx1 / Crypt idx0 / Caves idx2 (idx = ETB trigger / EtBState offsets); Bloodfell Choose = 2 options | `test_executor_query.py::TestGoldenSurface` |
