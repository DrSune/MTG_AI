# 01. Compiler campaign C1: full-corpus NAME_EQ idiom sweep + sanctum promotions (2026-10-02)

Baseline HEAD **d0d11cf** (wave-5 close, uncommitted tree). Mission: sweep all 305 M21 goldens
for the `NAME_EQ` idiom misuse found in r22c (/25), fix the compiler templates, re-pin PC-4
under set-equality evidence, promote the sanctum family. No commits; executor/state.py untouched.

## 1. The sweep (305 goldens, programmatic inventory)

13 `NAME_EQ` atoms live in 11 cards. **6 are the idiom** — `string_value` is not a card name —
across 4 sancta (printed clause → compiled predicate):

| Card (oracle_id) | Printed clause | Atoms |
|---|---|---|
| Sanctum of Fruitful Harvest (132859dd…) | "add X mana of any one color, where X is the number of **Shrines** you control" | 1 × QCount(ADD_MANA) |
| Sanctum of Calm Waters (1cd1e3a8…) | "you may draw X cards, where X is the number of **Shrines** you control" | 1 × QCount(DRAW, inside OptionalEffect) |
| Sanctum of Stone Fangs (a1d8fcb9…) | "each opponent loses X life and you gain X life, where X is the number of **Shrines** you control" | 2 × QCount(LOSE_LIFE, GAIN_LIFE) |
| Sanctum of Tranquil Light (1818b0b1…) | "This ability costs {1} less to activate for each **Shrine** you control" | 1 × CostModifier delta QBin MUL |

The remaining **7 are legitimate** exact-name filters (printed "named X"): Liliana's Scorn,
Chandra's Firemaw, Alpine Houndmaster ×2, Basri's Aegis, Frantic Inventory, Teferi's
Wavecaster, Garruk's Warsteed — untouched.

## 2. Predicate adjudication: TYPE_EQ, not NAME_EQ, not SUBTYPE_EQ

Frozen executor (`quantity.py`): :586 — TYPE_EQ/SUBTYPE_EQ/SUPERTYPE_EQ share one **type-line
word** test; :684 — NAME_EQ is exact `identity.name` equality. "Shrine" is a word of
"Legendary Enchantment — Shrine" but never a card name, so NAME_EQ counts 0. TYPE_EQ chosen
over SUBTYPE_EQ because (a) it matches the already-pinned reference shape of the green
sanctum_of_all_search_fire golden, (b) it is the idiom used by r22c executor pins — SUBTYPE_EQ
would evaluate identically here but split the corpus convention.

## 3. Fix + B-11/B-17/B-22 set-evidence (goldens move ONLY via this)

Templates: `templates_b2a.py::_shrine_count()` and `templates_b5c.py::
_build_shrine_activation_cost_reduction()` — `FAtom(NAME_EQ,"Shrine")` → `FAtom(TYPE_EQ,
"Shrine")` (+ docstrings; b5c supersedes its own stale rationale). Pre-snapshot taken BEFORE
edits (`/tmp/golden_pre_c1`, 305 files). Audit `/tmp/opencode/c1_inventory_audit.py`
fresh-compiles to `/tmp/golden_new_c1` and proves:

- exactly **4 files moved**, changed keys = `{abilities}` only; **301/305 byte-identical**;
- per-card old→new FAtom multisets **set-equal** after {NAME_EQ→TYPE_EQ on Shrine args};
  exactly **5 atoms renamed** (1+1+2+1);
- post-sweep scan: non-name-argument NAME_EQ atoms across all 305 = **NONE**.

PC-4 re-pinned via `tools/measure_grammar.py --set M21 --refresh-goldens --with-engine-flags`
→ PC-4 **0**, PC-3 0. Full PC before = after: PC-1 301/305 · PC-2 634/639 · engine 297/305 ·
PC-6 FAIL (orphan, pre-existing) · **PC-8 0.3213 (98/305) Δ0 — no move, recorded honestly**.

## 4. Stay-suspect rulings + one flag

- **adherent_of_hope** stays suspect: its census uses `NAME_CONTAINS "Basri"` — a *different*
  predicate; the 22c loss is the dropped "you control" quantifier, untouched by this fix.
  chandras_pyreling likewise unaffected.
- **secure_the_scene** (suspects/) PASSes at HEAD — stash-verified it was the ONLY passing
  suspect in the 17 pre-fix (1/17, post-fix 5/17 = the 4 sancta). Its CREATE_TOKEN
  controller-role loss is not exercised by its asserts → flag for orchestrator, NOT promoted
  (outside mission scope).

## 5. Promotions & gates

4 sanctum packs MOVE+strip suspects→scenarios: **scenarios 286/286 green** (282→286),
suspects 17→13. Suite **2272 passed + 3 subtests 0 failed** (2271 + 1 new pin
`test_shrine_cost_reduction_census_is_type_eq_not_name_eq`; 2 b2a pins AMENDED to TYPE_EQ;
the r22c honest-0 NAME_EQ executor pin KEPT as falsifiability witness). Catalog **0/10
diverge** (no repin). Games `--seeds 100 --pool all`: **86/100 survived, 0 crash classes**
(= 22c baseline). pyright **0** on 4 touched files; ruff **Δ0** (1 I001 in test_templates_b5c
imports is HEAD-preexisting at the same line).

## 6. Passing-suspect sweep (2026-10-02, HEAD df53003)

The C1-flagged five passers: the 4 sancta were already PROMOTED in §5; the sweep re-ran the
suspect lane (`tools/run_scenarios.py --dir tools/audit/suspects`) over the 13 survivors —
**1 passer remained: secure_the_scene**. Verdict **RE-SHARPENED-FAILS**, not promote: the
engine bug it documents is real (`_v_create_token` mints at `ctx.controller`; no anaphoric
controller-role lane) and its asserts never touched it — the green-on-a-silent-bug trap.

Printed-promise diff + resolution:
- "Exile target nonland permanent" — asserted (zone lane); exile **owner** dimension NOT
  observable (lane reads zone KIND only) — recorded, not asserted.
- "creates a 1/1 … Soldier token" — name-count was asserted; **P/T was unasserted** → added
  `battlefield_pt {Soldier:[1,1]}` (passes honestly under the bug — name-keyed lane).
  **Color "white" not observable** in the expect schema — recorded.
- "ITS CONTROLLER creates" — the token has no pack key, so no lane reads its owner directly;
  but an owner ACTS with it. Pack extended: cycle to P1's turn (`end_turn`+`advance_turn`),
  run seat-1 `combat` carrying the r22a decisions script `["ATTACK"]` (unmapped attack sites
  pop script words; a site that never exists never consumes one), assert `life {0:19, 1:20}`.
  Printed-faithful engine → Soldier is P1's, asked, attacks unblocked, P0 at 19. Current
  engine → token stuck to caster P0, P1 has zero creatures, zero asks, life[0]=20 →
  **pack FAILS on exactly the documented line**: `life[0]: expected 19, got 20`. Logged
  assumption: the future green path also presumes the sickness/untap clocks are clean by
  P1's turn 2 (whale_pirate_token proves the seat-1 combat-damage flow itself).

Gates after: suspects **0/13 pass** (every survivor fails on its documented line), scenarios
**286/286**, `pytest MTG_bot/core -q` **2272 + 3 subtests, 0 failed**. No engine/runner/golden
touched; no commits.
