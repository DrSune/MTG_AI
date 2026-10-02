# 2026-10-02/06 — Compiler campaign C4: the creature cast lane opens (AUDITED ADDITIVE-EMISSION)

HEAD at start: `80b717b` (post-C3). Scope per `/02-compiler-roadmap.md` batch 4: every plain
creature gets a `SpellAbility(kind=SpellKind.CREATURE)` node so `legality.cast` has a lane —
the B-1 "not-castable creatures" status quo ends here.

## The emission change (compiler.py creature branch, ~:1516)

- Creature branch **always** emits one `SpellAbility(CREATURE)`, last in the list.
  - With `effect_outcomes` (a folded effect sentence existed): effect folds in as before.
  - Plain creature: **effect-less carrier** (`effect=None`, precedent: additional-costs
    cards), `ability_srcs.append(len(raw.sentences) - 1)` (synthetic-carrier rule: never
    masquerades as a "preceding ability" when anchoring activation gates).
- Tokens (`is_token` branch, checked first) are excluded — they never enter a library.
- Additional-costs attach path: byte-identical output for Goremand / Sparkhunter Masticore.
  **Roadmap falsification:** `/02` called them "EffectOutcome path" carriers — wrong; they
  are the additional-costs shape (effect None + Cost parts). They already carried exactly
  one SpellAbility, so C4's guard (`any(isinstance(ab, SpellAbility))`) adds none. Pinned:
  `test_compiler_c4.py::test_additional_cost_carrier_not_duplicated`.

## Audit (gate 1) — PASS

`/tmp/opencode/c4_inventory_audit.py`, pre-snapshot `/tmp/golden_pre_c4/` (305), fresh
compile `/tmp/golden_new_c4/M21`, delta table `/tmp/opencode/c4_delta_table.txt`:

- **147 goldens moved** — NOT the roadmap's "163": the grep count included **16 token
  creatures** (Angel, Beast, Bird×? … Zombie) which correctly stay byte-identical.
  147 movers + 16 tokens + 2 additional-cost carriers + 140 non-creatures = 305.
- Every mover: `keys == {"abilities"}`, abilities = pre-list + **exactly one appended**
  `SpellAbility(kind=CREATURE)`; effect-less unless the card had a foldable effect sentence.
- 158 byte-identical; FAtom/Verb multiset set-equality proven per card; zero movers had
  additional_costs variants. Spot-verified 5 lanes incl. Masked Blackguard (FLASH),
  Walking Corpse (0→1 node), Adherent/Houndmaster (trigger + carrier order).

## Grammar (gate 2)

`tools/measure_grammar.py --set M21 --refresh-goldens --with-engine-flags`:
PC-3 **0**, PC-4 **0** (305 refreshed; golden tree byte-equal to the audited fresh compile),
PC-1 303/305, PC-2 637/639 (both Δ0). **PC-8 stays 0.3213 (98/305) — honest record: the
effect-less carrier carries no targets, so the targeting histogram does not rise.**

## Scenarios & suspects (gate 3)

- `creature_spell_nodes_systematic.json` **promoted** green: `tools/scenarios/` → **293/293**.
- `tools/audit/suspects/` now **9, 0/9 pass** (all red-as-intended). Two updates:
  - **NEW** `flash_window_engine_gap.json` — compiler half done (Masked Blackguard carries
    `SpellAbility(CREATURE)`); the **engine half is a real gap**: `spell_window_reason`
    (legality.py:1101-1118) consults only SpellKind — CREATURE ∈ `_SORCERY_WINDOW_KINDS`
    and no keyword lookup — so a Flash creature cast on an opponent's turn raises
    `window:not_your_turn` instead of honouring flash (CR 702.9a). Next engine batch.
  - `wildwood_scourge.json` finding extended: the cast lane OPENS (x=2 + {C:4,G:1} now
    passes not_a_spell/window/601.2f); the raise moved to the **engine** EtBState
    `QX has no declared X` (CR 614.1c initial-counters half). Not promoted.

## Suite (gate 4)

**2290 passed + 3 subtests, 0 failed** (= C3 baseline 2284 + 6 new C4 pins). 18 honest
falsifications amended, all one root: creature fixtures trail the carrier —
test_compiler.py ×10, c2 ×2, b5a ×2, b5b ×1 (Gnarled Sage: 0→1 nodes), executor ×2:
- `test_executor_library` Tavern Swindler: golden rows now
  `['ActivatedAbility','SpellAbility']`, second row asserted **effect-less** (the 13a
  two-row tail miscompile stays GONE).
- `test_executor_games` B-9 pin: the hand-cast raise MOVED `not_a_spell` →
  `cost:mana:W:0<1` — the test had been witnessing the fixed B-1 bug; now it witnesses
  the opened lane stopping at the mana gate instead.

## Traces & games (gate 5)

- `catalog.py compare`: **10/10 seeds diverged** → attributed → `repin` → **0/10**.
  Attribution: every first-divergence is a NEW `ZONE_CHANGE/CAST` entry where the old
  trace only advanced turn/tap; outcomes flip from "turn cap 60 (no loser)" to
  "game over: life<=0". This is the intended blast radius of "creatures now cast", not a
  regression.
- `games --seeds 100 --pool all`: 100 games, **83 decisive game-overs** (vs 86 cap-
  survivals + 17 endings at baseline — first campaign where most games END by winning;
  mean_turns 31.05 vs 57.69), **17 crash games / 7 classes**, all absent at baseline
  (0 classes, C3 row). Full attribution, executor half ONLY (frozen, zero edits):
  | n | raise | attempted | verdict |
  |---|---|---|---|
  | 5 | `TARGETS_SOURCE not implemented` (quantity.py:1398) | `cast:Pursued Whale` | 12c query gap, newly reachable via creature cast |
  | 3 | `TARGET_PLAYER needs a bound target` (selectors.py:90) | `act:Liliana's Steward#0` | 12c target-prompt gap; reachability shift |
  | 3 | `QX has no declared X` (quantity.py:328) | `cast:Wildwood Scourge` | = wildwood suspect engine half |
  | 2 | trigger-loop tripwire (binding.py:1061) | `cast:Turn to Slag` | deliberate guard: flags, never runs |
  | 2 | `GAIN_LIFE not layer-parseable` (layers.py:492) | `cast:Rin and Seri` | documented 12e static-payload gap |
  | 1 | selector `referent 'event' has no register` (selectors.py:275) | `land:Plains` (landfall on surviving creature) | register-convention gap |
  | 1 | `CAST Island: no SpellAbility` (stack.py:726) | `act:Radha, Heart of Keld#1` | policy proposed a land cast; legality guard raised loudly (working as designed) |
  No class is a compiler-emission defect; every one is an executor cast-consumer gap the
  lane newly exposes. reports/games_2026-10-02.json.

## Lints (gate 6)

pyright **0 errors** on all 8 touched files; ruff **Δ0** (per-file multisets identical to
HEAD: test_compiler 7=7, b5a 9=9, b5b 7=7, rest 0); ruff-format clean. Note for future
deltas: ruff rule sets differ outside the repo root — copy HEAD files into the tree to compare.

## Batch ledger impact

- B-1 "creature cast lane missing": **closed** (compiler half); successor gaps are the
  FLASH window keyword, X-binding at cast, and the target/query prompts above.
- Engine batch candidates now queued (all executor half): spell_window flash consult,
  EtBState X / CR 614.1c, TARGETS_SOURCE + TARGET_PLAYER prompt lanes, GAIN_LIFE static
  layer payload, Radha land-cast enumeration.
