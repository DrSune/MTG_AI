# 2026-09-29 · 04 — T8 semantic spot-check: r6-r10 output — FINDINGS (all orchestrator-confirmed)

Adversarial audit (ses_f14f4a0faffeOQaYlolaKFuknI) walked ~40 cards' goldens vs oracle text clause-
by-clause. Every P0/P1 below was then re-confirmed by orchestrator probes against code/goldens at
HEAD ba67a4e — the auditor's report is TRUE (rare: prior reports had naming noise; findings here
survived independent verification). Round 11 = semantic-correctness fix round; all fixes are
golden-VISIBLE (authorized re-baseline with per-file audit) and must NOT move PC-1/PC-2/PC-3
(coverage and patterns unchanged; only IR content).

- **P0-1 orphan-continuation misattachment (CONFIRMED code-level)**: compiler.py ~1081 wraps ANY
  unattachable continuation in OptionalEffect unconditionally — phantom "may" for mandatory
  sentences (Ooze, Fabled Passage, Garruk Unleashed −2, Basri Ket, Herald +1; loyalty-trailing
  sentences also attached to card-level SpellAbility instead of the loyalty row's effect). FIX
  R11-1: shared handler — loyalty-trailing prefers the loyalty ability's effect; OptionalEffect
  wrap only when source sentence contains "may".
- **P0-2 ETB trigger subject=None corpus bug (CONFIRMED, BIGGER than reported)**: my probe at
  ba67a4e: **62 ETB-as-trigger ZoneChangeEvents (to BATTLEFIELD, from None/ANY) have NO subject,
  vs 4 with IS_SOURCE** (+1 legitimate non-self: Garruk's Uprising). subject=None = "whenever ANY
  permanent enters" — wrong for "When ~ enters". Legacy r1-r2 helper origin (b2a/b2b _etb_event).
  FIX R11-2 sweep: "~ enters" ⇒ subject=FAtom(IS_SOURCE); "a/the <class> enters (under your
  control)" ⇒ subject = matching FAtom filters — per-template decision from pattern semantics,
  never blanket.
- **P0-3 target-legality widening (CONFIRMED code-level)**: templates_b3.py `_sel_target_creature`
  and `_sel_target_creature_flying` use Zone(ANY, ANY) (helper file, sibling helpers correctly
  BATTLEFIELD/ANY); "target creature" ≠ "any target" (the 11 literal-any-target cards use a
  different, correct helper — auditor verified CLEAN). ~6 cards (Animal Sanctuary, Celestial
  Enforcer, Keen Glidemaster, Sanctum of Tranquil Light, Skyway Sniper, Tempered Veteran). FIX
  R11-3: zone → BATTLEFIELD/ANY for the creature helpers; sweep other modules for the same shape.
- **P0-4 Necromentia count scoping (CONFIRMED via card walk)**: THIS_WAY_COUNT tallies ALL exiles;
  the hand-origin scoping of the counted exile is lost ⇒ token-count fidelity. FIX R11-4a:
  count-filter must carry the exile-origin clause (real M21 text governs).
- **P1-1 Gadrak Treasure clause silently dropped (CONFIRMED: 'TREASURE' absent from golden)** —
  C11 violation (no verbatim note). FIX R11-4b: encode Treasure creation via C23 literal
  (TokenSpec artifact colorless + tap-sac-ADD_MANA-ANY ability), else verbatim lossy note —
  encoding preferred (Whale precedent).
- **P1-2 Subira "another target" lacks not-self (CONFIRMED: no IS_SOURCE in that block)**:
  FAnd(IS_ANY_TARGET, POWER_LE(2)) needs FNot(FAtom(IS_SOURCE)) ("another" convention per b2a
  docstring — shipped convention, this row predates/missed it). FIX R11-4c.
- P2 (RECORDED, not fixed): Nine Lives uses HAS_COUNTER (no _GE variant — executor-risk note);
  Teferi OptionalEffect inside permission static (harmless noise); Mangara ordinal=2 per-caster
  reading = executor interpretation (record).
- Non-findings verified correct: literal-"any target" cards, Catalyst/HoF waiver-duration (C11
  documented), Herald −7 C28 idiom (b5c:2618-2635), Kraken PAY-do merge, Vodalian THIS_MANA,
  Enthralling IS_UNTAPPED/IS_ATTACHED_TO_SOURCE, Chrome NAME_PARTITION_COUNT_GE(2), Whale
  ALL_OPPONENTS, Speaker gate, Peer rounding, Mangara ordinal (auditor self-corrected 2 suspects
  to PASS via raw-JSON probes — good adversarial hygiene).

PROBE PITFALLS (for future audits): golden schema = event key 'event' (not 'trigger'); enum
values are wrapped dicts {'name':…,'tag':…} — string-compare .kind.name, never .kind; top-level
name key is 'name'.

Round-11 gate plan: 11-A (R11-1 compiler handler + R11-3 helpers + R11-4 cards; ~20-25 goldens)
→ 11-B (R11-2 ETB subject sweep; ~60 goldens) → measure: PC-1 301/305, PC-2 634/639, PC-3 0 ALL
EXACTLY unchanged + per-family golden-diff attribution. If a subject fix reveals a card was
covered by a WRONG pattern (shouldn't have matched), coverage may legitimately move — explain,
don't suppress.
