# 2026-09-29 · 06 — Round 12 BINDING plan: T6 executor (phases 12a-12e)

Basis: analyst draft (ses_f13c19b21ffeEomWPCXotbrVpj) grounded at 8b32326 + orchestrator rulings.
T6 definition per 2026-09-16/01 §2 (core/executor.py dispatch on IR node tag vs Phase-0 GameWorld;
SUPPORTED_VERBS → compile_pool → engine_supported; flag-don't-degrade North Star). Probe facts
(trust, re-run to verify): 578 Atoms / 48 verbs; top shares MODIFY_PT 52, ADD_MANA 49,
GRANT_ABILITY 47, MOVE_ZONE 35 (DRAW is a MOVE_ZONE idiom — no DRAW verb), PUT_COUNTER 33,
GAIN_LIFE 33, DEAL_DAMAGE 31; 151 TriggeredAbility / 129 ActivatedAbility / 76 SpellAbility /
45 Static / 8 Replacement / 1 DelayedTrigger. state.py (300 lines) ALREADY HAS mana_pool,
counters, tapped, draw/move ops, master_seed; MISSING: PT-mod records, RNG usage, stack.

## Binding rulings (orchestrator)
1. state.py is FROZEN in 12a-12c; 12d may only propose an additive fingerprint hook, default =
   executor-side DurationLedger is replayed state (no edit).
2. Legacy boundary (binding): MTG_bot/rule_engine/ (3030 lines, 15 known-red tests) + strategic_
   brain (8 red) are FROZEN — executor imports nothing from them, fixes nothing in them, shares no
   symbols; replacement only once PC-7 runs on executor games. Their failures are NOT round-12
   regressions (HEAD-parity check = stash-compare like r11).
3. SUPPORTED_VERBS is NOT fed to compile_pool until 12e. Through 12a-12d all PC numbers must stay
   EXACTLY as at 8b32326 (PC-1 301/305, PC-2 634/639, PC-3 0, PC-4 0, goldens byte-identical —
   executor is additive, no grammar/template/golden edits AT ALL).
4. At 12e, feeding SUPPORTED_VERBS v2 will legitimately flip engine_supported=False on cards
   (no stack ⇒ SpellAbility-heavy cards flagged). That is the honest signal, NOT a failure;
   expected consequence: PC-1/PC-2 UNCHANGED (coverage = parse), new honest number = engine-
   supported card count (report it; add to NUMBERS).
5. Choice surface reuses DESIGN_ACTION_SPACE vocabulary (Slate, roles TARGET/MODE/OPTION/
   CHOICE_OPTION, decision_slate) — executor consumes the SAME typed IR objects (no DTOs);
   lists canonically Handle-sorted except designated order-preserving slots.
6. C-contract carried: C15 enumerable decisions, C17 QAtMost legal 1..n / resolve 0..n clamp,
   C18 was-snapshots, C22 DelayedTrigger scheduler, C24 nesting, replacement-before-apply,
   OptionalEffect = may-fire offer. The 5 queue shapes + CAST/COUNTER_SPELL/PHASE_OUT/FIGHT/
   COPY/MANDATE_*/GET_EMBLEM-mark internals are OUT (flagged territory, never faked).

## Phases (each = one bounded delegation; gate before next)
- 12a: core/executor/{__init__,verbs,durations_min}.py — execute_atom for state-visible verbs:
  MOVE_ZONE(+draw idiom)/EXILE/SACRIFICE/DESTROY/DISCARD/MILL, GAIN/LOSE_LIFE, DEAL_DAMAGE
  (lethal→graveyard), TAP/UNTAP, {PUT,REMOVE}_COUNTER, {MODIFY,SET}_PT + Eot-min expiry hook,
  CREATE_TOKEN (TokenSpec→CardIdentity synthetic id), ADD_MANA (existing mana_pool), SCRY/SHUFFLE
  (seeded Random derived from master_seed), LOOK_AT/REVEAL (no-op record for action-history later).
  SUPPORTED_VERBS v1 frozenset declared (NOT fed yet). Gates: new test_executor_verbs green;
  test_state/test_core suite still 1724; goldens untouched (git diff empty outside executor/).
- 12b: executor/binding.py — compiled abilities attach to Handles; executor wraps world mutations,
  emits events; TriggeredAbility→TriggerInstance via queue_trigger + side-table (instance id →
  compiled node); determinism replay test.
- 12c: executor/{legality,query}.py — activation legality (cost payable incl CostTap/CostSacrifice,
  timing C20), payment fold, D3 query API (legal_activations/legal_targets/choose_options/
  optional_offer), QAtMost/C15/C17 fixtures.
- 12d: durations.py full Duration vocab + static/keyword layers + DurationLedger; fingerprint
  decision per ruling 1.
- 12e: feed SUPPORTED_VERBS v2; measure run; honest engine-supported count; close-out doc.
Sequencing note (analyst amendment honored): Eot-min scheduler joins 12a (top verb MODIFY_PT).

## Delegation map (context economy)
12a/12c/12d → coder (128k) with pre-loaded state.py slice; 12b → ultra (binding/event semantics
cross compiler+state); 12e → orchestrator-inline measure + tiny edit.

## §12e FINAL (executed at f6b0134+12e, 2026-09-29)
- SUPPORTED_VERBS_V2 defined in executor/__init__.py, derived `frozenset(HANDLERS)` (V1 kept —
  test_executor_verbs imports it). Cross-checked all 48 corpus verbs: V2 == V1 == **24** verbs
  (12d's GRANT_ABILITY/LOSE_ABILITY/PREVENT_EFFECT already entered HANDLERS; no verb gained a
  handler since 12a). A verb is in V2 iff run_atom dispatches a real handler; the 25 enum-only
  verbs stay out — CAST, COUNTER_SPELL, PHASE_OUT/PHASE_IN, FIGHT, COPY, MANDATE_ATTACK,
  MANDATE_BLOCK, GET_EMBLEM (ruling-6 internals), plus DRAW, PAY, SEARCH, ATTACH, GAIN_CONTROL,
  CHOOSE, CHOOSE_NAME, GRANT_TYPE, GRANT_ACTIVATION, ADD_LAND_PLAY, END_TURN, EXTRA_TURN,
  FLIP_COIN, LOSE_GAME, MANA_POLICY, DAMAGE_ASSIGN_POLICY.
- Fold citation (compiler.py): lines 1459-1472 — `supported_verbs is None` ⇒ engine_supported=True
  (template stamp, L1460-1461); else AND-fold over walk(card): first Atom whose verb ∉ set ⇒
  False (L1463-1467), written into LegalityFlags(engine_supported=…) (L1469-1472). No other
  writer of engine_supported exists; templates never stamp False.
- measure_grammar.py `--with-engine-flags`: second compile_pool pass gated on V2; report JSON
  gains `"engine_support"` {engine_supported_cards, of_total, supported_verbs, flip_proof};
  NUMBERS.md gains a PC-7 row; without the flag output is byte-identical.
- Honest count: **engine_supported_cards = 206/305 (0.6754)**. Flip-offender shares over the 99
  flipped entries: DRAW 49, SEARCH 16, CAST 7, COUNTER_SPELL 5, GET_EMBLEM 3, GRANT_TYPE 3,
  MANDATE_ATTACK 3, PAY 3, FIGHT 2, MANA_POLICY 2, COPY 2, CHOOSE 2, GAIN_CONTROL 2, ATTACH 2,
  CHOOSE_NAME 2, PHASE_OUT 2, singles ADD_LAND_PLAY/END_TURN/MANDATE_BLOCK/DAMAGE_ASSIGN_POLICY/
  LOSE_GAME/FLIP_COIN/EXTRA_TURN/GRANT_ACTIVATION. Flip proof (fold load-bearing):
  "Chandra, Flame's Catalyst" True→False via CAST+DRAW atoms. No SpellAbility-only card carries a
  CAST atom in M21; spell-only flips come from DRAW/SEARCH/COUNTER_SPELL/CHOOSE idioms.
- Gates at this commit: pytest MTG_bot/core 1876 passed; PC-1 301/305, PC-2 634/639, PC-3 0,
  PC-4 0 diffs (goldens untouched, flag never refreshes); PC-6 (DRAW orphan) + PC-8 (0.3213)
  FAIL at HEAD too — pre-existing, not 12e regressions. pyright 0 errors on both touched files;
  ruff delta 0.
