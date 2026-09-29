# 2026-09-30 · 02 — Round 13 close-out (arc 2 done) + ROUND 14 BINDING: real PC-7 (game loop)

## Round 13 final (commits 9120e2d 13a · 4cdfa8b 13b · 01069f9 13c)
engine_supported **206 → 286/305 (93.8%, 39 verbs)**; core suite 1876→**1971**; PC-1 301/305,
PC-2 634/639, PC-3 0, PC-4 0 **EXACT all five phases** (invariants held since arc-1 start: 12a-12e +
13a-13c = 10 consecutive phases, state.py/grammar/goldens never touched). Honest remainder **19
flagged**: combat-dependent 7 (MANDATE_*, FIGHT, DAMAGE_ASSIGN_POLICY), response-needed 4
(COUNTER_SPELL family — no-interaction v1 can't legally have counters, loud raises pinned), deep
9 (PHASE_OUT×2, COPY×2, ATTACH×2, GAIN_CONTROL×2 + Teferi MoT double-flag). Arc 3 (combat skeleton
→ response window → deep mechanics) remains planned but UNBND — round 14 comes first because
game-survival doesn't require combat to be OPTIONAL-legal in MTG terms… it IS required (phases
exist), but a game can survive turns without attackers.

## ROUND 14 (BINDING) — the executor's own verification: random-policy full-M21 games
Why now: casting+triggers+layers live; T10's PC-7 ("game_turn_survival") was always the Phase-2
gate and the systemic successor to the r11/T8 audit — games find cross-cutting bugs unit tests
structurally can't (like 12d's two engine bugs found by proof-cards, scaled up).

### Phase 14a (ultra): harness
Files: new MTG_bot/core/executor/games.py + test_executor_games.py. Design:
- Deck supply: 305 compiled goldens → construct legal-ish random 60-card decks from the card pool
  (duplicates allowed; lands = the 10-ish basic/fix lands present in M21 + zero-land decks OK —
  honestly: this is a STRESS TEST of compiled cards, not a format tournament; document).
- Random policy: consume ONLY the query surface (legal_casts/legal_activations/legal_targets/
  choose_options/optional_offer/legal_search/coin decisions) — uniform-random legal choice +
  seed; NEVER reach into engine internals (C15 contract proof: the query surface must be
  sufficient for full play — if policy hits a decision point NOT enumerable, that is a P0 finding).
- Turn loop: begin_turn → draw → land drop → casts/activations (any legal moment the API allows;
  no priority simulation — batch style, documented) → end_turn; fire_triggers drain built-in;
  loss from life≤0/LOSE_GAME; game ends at turn cap (default 60) or loss.
- Metric: per-seed record (game completed? turns survived, crash exception+frame, cards exercised
  set). PC-7 v1 = % of (seed,deck-pair) games surviving full cap + cards-touched coverage
  (how many of 286 engine cards actually FIRED their abilities in >=1 game — separate number,
  expected <100%: passive cards don't "fire").
- Scale: start 10 seeds × 2 decks; expand to 100 if crash-free (measure tool gets --with-games
  flag later; 14a reports via its own script + NUMBERS row hand-added with command).
- CRASH TRIAGE: every crash → minimal repro test in test_executor_games.py + fix if
  executor-side small; grammar/state-side or design-level → KNOWLEDGE/2026-09-30/03 bug ledger
  row (severity per r11 conventions: P0 crash/misexec, P1 silent wrong-state, P2 cosmetic).
  DO NOT suppress or skip cards ("no silent skips": every flagged crash either fixed or in the
  ledger with a card name).
Gate: 10-seed smoke green (survival % + bug list with repros); suite 1971+M; PC invariants.
### Phase 14b+ (per bug ledger, coder batches): fix P0/P1, re-run 100-seed, PC-7 number
lands in NUMBERS as first REAL engine evidence; docs /04+ ledger per bug, INDEX rows.

### Invariants (unchanged, re-check every fix): PC-1/2/3/4 EXACT; goldens frozen unless a fix
requires a RE-BASELINE — then r11-style set-equal audit (that path exists and is trusted);
state.py frozen unless measured additive hook (14 proposals go through me as rulings).
