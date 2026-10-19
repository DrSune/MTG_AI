# 114 — Aura-target legality hole fixed (effectless-aura SpellAbility, ZNR fuzz 21/500 → 0/500)

- Date: 2026-10-19. Lane: engine (executor/query + test + scenario pack). NO compiler/templates touched.

## Root cause (verified, not hypothesized)
- `spell_target_slots` (executor/query.py) EARLY-RETURNED `[]` when the
  SpellAbility carried `effect=None` — *before* the 16e `aura_enchant_slot`
  synthesis at the function's tail. Bubble Snare (and every ZNR aura whose
  rules body compiles to sibling ETB/static abilities: `SpellAbility(kind=
  ENCHANTMENT, effect=None)`) therefore harvested ZERO slots, so
  `_validate_spell_targets` saw "targetless spell — the common case" and
  passed the zero-target cast; `stack.py:910`'s resolution invariant (kept
  loud, untouched) then raised. The Enthralling Hold golden never hit the
  hole because its SpellAbility carries a real GAIN_CONTROL effect.
- `spell_castable`'s `cast:aura_no_legal_target` gate calls
  `aura_enchant_slot` DIRECTLY, so it worked even pre-fix — the hole was
  specifically the slot-harvest lane the RandomPolicy designates from
  (games.py `play_cast` → `select_targets(slots)` with slots=[] → cast
  with no targets while candidates existed e.g. lands, since the fuzz
  battlefield was never empty — the fallback enchant population is
  any-permanent for effectless auras, v1 documented).

## Fix (minimal diff, query lane)
- `query.py::spell_target_slots`: the `effect is None` early return now
  routes through `aura_enchant_slot` and returns `[slot]` for auras, `[]`
  otherwise (non-aura effectless casts byte-unchanged).
- Refusal-consistency verified end to end: no legal designee ⇒
  `spell_castable` = `cast:aura_no_legal_target`, `RandomPolicy.select_targets`
  = None (infeasible skip), and a direct `cast()` raises ValueError
  (`illegal cast: cast:aura_no_legal_target:...`) BEFORE the stack push.
  With a designee the ask answers pre-cast and resolution attaches (CR
  303.4a). stack.py:910 not weakened.

## Numbers (all EXECUTED, this session)
- Repro seed 73 (`znr_engine_smoke.py --repro 73 --deck-pairs-seed 201019
  --turn-cap 150`): was ValueError@stack.py:910 → now "no crash — 37 turns,
  55 acts".
- FUZZ rerun `--games 500` (default deck-pairs-seed 201019): **500/500,
  crashed=0 (0.0%), signatures=0** — aura class GONE, no new class
  (wall 74.9s).
- `pytest MTG_bot/core -q`: **2676 passed** (+2 new pins; ≥2672 gate met).
- Packs: **410/410** incl. NEW `tools/scenarios/znr_aura_no_enchant_target.json`
  (negative pack: Bubble Snare vs empty battlefield, `expect_raise:
  aura_no_legal_target`, snare stays in HAND) — rig CAN express the refusal.
- New pins in `test_executor_games.py::AuraEffectlessLegalityTest`
  (synthetic effectless ENCHANT aura): harvest returns 1 synthetic
  min=1/max=1 slot; refusal never casts (zone stays HAND, stack.frames
  empty); designee path resolves attached.
- pyright: 0 errors on the two touched py files; ruff: all checks passed
  (Δ0).

## Known-gap ledger (registered, NOT fixed here)
- Enchant-filter fidelity: effectless auras fall back to "any permanent"
  enchant population (v1 documented fallback in `aura_enchant_slot`) —
  "Enchant creature" auras could designate a land. Compiler-side enchant
  metadata would close it; legality-when-empty and the 910 invariant are
  unaffected.
- Sibling eval-lane bug (NOTED ONLY per task law, untouched):
  `tools/eval/gameplay_eval_v2.py` breaks with workers>1 (missing pool
  initializer). Owned by the eval lane.
