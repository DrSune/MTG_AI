# 2026-09-29 · 11 — Round 13 BINDING plan: executor arc 2 (library → stack/cast → permissions)

Basis: analyst draft (ses_f12320a7cffeOp0q8ASaxE61XI) MEASURED at 57d3fc1 (99 flagged reproduced;
cluster attribution via per-card offender probe — trust the measured table, not the arc-1 guesses;
my H1 "50-60 stack cards" was WRONG: DRAW/SEARCH dominates at 58). Docs 06/09/10 rulings ALL still
in force (state.py frozen, rule_engine frozen, PC-1/2/3/4 invariant, flag-don't-degrade, C15 query
surface obligation, determinism + fingerprint dumps).

## Orchestrator rulings on the analyst's open items
(i) HEAD discrepancy = orchestrator's stale pre-compaction id; git history verified consistent. No action.
(ii) GAIN_CONTROL: **STAY FLAGGED this round.** 2 cards don't justify touching frozen controller_of
     (read broadly by verbs — ripple risk > reward). Arc-3 may propose a measured additive hook.
(iii) PC-7 SEMANTICS NOTE (binding, 13a writes it to NUMBERS): engine_supported currently measures
     VERB-DISPATCHABILITY, not full playability — 46 SpellAbility cards read True while casting is
     unimplemented (fold sees their atoms only). After 13b, True ≈ actually playable (minus combat).
     No compiler change; honest documentation is the fix.

## Measured clusters (D1) → decomposition (each = one bounded delegation)
| Phase | Role | Scope | Flip | engine_supported after |
|---|---|---|---|---|
| 13a | coder | handlers: DRAW, SEARCH (seeded pick-from-library via decisions), FLIP_COIN (seeded), END_TURN, EXTRA_TURN, LOSE_GAME + loyalty ledger (counters["LOYALTY"] on battlefield entry from CardIdentity.loyalty; CostLoyalty legality+payment flip; once-per-turn gate; 0→death) + phase tick (executor-side self.phase: UPKEEP/FIRST_MAIN/COMBAT/END_TURN markers; sorcery/PW/land windows = own turn ∧ FIRST_MAIN ∧ stack-empty; ability_playable(stack_empty) pin byte-identical) | **+58** | 264/305 |
| 13b | ultra | stack.py SpellObject frames (park cards via per-player ZONE_STACK ZoneState — zero state.py edits, analyst verified L41-47 + fingerprint loop untouched); legal_casts() FIRST (C15: hand × SpellAbility × land-drop, Handle-sorted, payment plan reuse); cast() folded CR 601.2 sketch (modes/targets consumed from query surface BEFORE payment; X_VALUE: cast param x → ExecCtx.x_value → quantity.resolve QX (L188) + payable-legality folds X; CHOOSE modes via 12d ORDER contract); PAY/CAST atoms live; ManaLedger segments (color, amount, tags) — spend-validator consulted ONLY when tags non-empty (12a/12b totals path untouched) → MANA_POLICY (THIS_MANA/ALL_YOURS) dispatch with LIVE consumer; no-interaction LIFO documented vs CR 608.2; COUNTER_SPELL (4 pure cards) STAYS raise — response window = arc 3 | **+15** | 279/305 |
| 13c | coder | GET_EMBLEM (synthetic handle + attach_card reuse; PoolCompile.emblems bridge; orphan_emblems==0 test), GRANT_ACTIVATION→ability_playable consult (C25 pattern), GRANT_TYPE→layers TypeOverlay, ADD_LAND_PLAY turn-ledger | **+9** | **288/305 (94.4%)** |
| 13d | none | honest remainder 17: combat 7 (arc 3), counter-only 4 (response API arc 3), deep 6 (PHASE_OUT/COPY/ATTACH + mixed) | 0 | — |

PC-1 301/305 · PC-2 634/639 · PC-3 0 · PC-4 0 **invariant all round** (V2 feed grows via HANDLERS
derivation automatically — 12e mechanism; goldens frozen). Engine count verified via
--with-engine-flags each phase; NUMBERS rows via tool.

## Proof cards (compiled shapes analyst-verified)
13a: Cultivate + Bad Deal (end-to-end), Chandra's Firemaw, Catalyst −2 via loyalty ledger.
13b: Shock cast→resolve→GY end-to-end, Titanic Growth, Duress (X-free modes) — Cancel MUST raise.
13c: Basri Ket emblem run (arc-1 already ran its +1; now emblem), Riddleform (GRANT_TYPE), Azusa.

## Risks (analyst D6, mitigations binding)
1. 601.2 declaration collapse debt → SpellObject stores 601.2b–e data; raise keeps gap loud.
2. Mana-tag churn vs 12a/12b pins → side-ledger consulted only-when-tagged; replay pins.
3. Emblem C19 runtime drift → reuse attach_card; 3-emblem replay test; orphan assert.
4. (orchestrator) PC-7 semantics drift → ruling (iii) note + this doc.
