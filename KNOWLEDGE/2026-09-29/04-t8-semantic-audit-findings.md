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

## ROUND-11-A RESULTS (executed 2026-09-29, HEAD baseline 3f95fba, NOT committed)
FIXES LANDED:
- R11-1 compiler.py: `_MAY_RE` may-gate — an attachable continuation without "may" merges
  MANDATORY into the previous ability (was: phantom OptionalEffect wrap); "may" sentences and
  the search-shuffle tail (`_SEARCH_SHUFFLE_TAIL_RE`, deliberate never-fires decision) keep the
  wrap. New `_loyalty_trailing_idx`: a trailing "[+X]/[-X] ..." text sentence merges into the
  nearest preceding loyalty ActivatedAbility (guarded: not "[…]" cost-prefixed sentences).
- R11-3 templates_b3.py: `_sel_battlefield_creature_you_control`, `_sel_creature_target_opponent`
  , `_sel_target_creature_you_control`, `_sel_your_creatures` zones ANY → BATTLEFIELD/ANY
  (only `_sel_any_target` legitimately keeps ANY/ANY).
- R11-4a templates_b5b.py Necromentia: `QProp(THIS_WAY_COUNT)` → scoped
  `QCount(Selector(QUnbounded, ALL, FAnd(NAME_CHOSEN, MOVED_TO_ZONE_THIS_TURN[from=HAND,
  to=EXILE, who=TARGET_PLAYER]), EXILE/TARGET_PLAYER))`.
- R11-4b templates_b2a.py `_treasure_token`: printed "(Tap it, sacrifice it: Add one mana of
  any color.)" now a real ActivatedAbility (CostTap+CostSacrifice(IS_SOURCE) →
  Atom ADD_MANA ANY 1) in TokenSpec.abilities (C23 literal-encode precedent).
- R11-4c templates_b3.py `_build_target_cant_be_blocked`: blocked filter FAnd now includes
  FNot(IS_SOURCE) — a creature cannot "block itself" from the source's own block-declaration.

GOLDEN RE-BASELINE: write_goldens → 305 written, verify_goldens → 0 diffs. **27 files changed**
(18 predicted + 9 unanticipated), `abilities` key ONLY in every file (audit: 0 violations vs
allowed ⊆ {abilities}). The 9 unanticipated are all the R11-1 signature (mandatory "If you do, X."
tail losing its phantom OptionalEffect): Sanctum of Calm Waters (1cd1e3a8), Archfiend's Vessel
(62c240ac), Mazemind Tome (800fb917), Niambi Esteemed Speaker (91c9dbd8), Liliana's Devotee
(b3b8c7d0), Jeskai Elder (dfbd5ad1), Dire Fleet Warmonger (ee08435b), Crypt Lurker (f0cbf361),
Ghostly Pilferer (fe168bf1). Pre-refresh snapshot: /tmp/golden_pre_r11a_2026-09-29.

GATES (all EXACT, measured 2026-09-29 via
`.venv/bin/python -c "measure_pool(ingest_pool(MTG_bot/data/M21.json), build_full_registry(), 'M21')"`):
PC-1 301/305 ✓ · PC-2 634/639 (0.992175) ✓ · PC-3 0 ambiguous ✓ · full suite 23 failed /
1748 passed / 1 deselected / 2 xfailed — failure set byte-identical to clean-HEAD baseline
(`comm` empty both directions; /tmp/opencode/head_fails.txt) → zero new failures. ruff on the 8
touched files: 14 TRY004 = HEAD baseline, delta 0 (one new I001 from added imports was --fix
sorted in templates_b2a.py). pyright on all 8 touched files: 0 errors.

API NOTES (for future measurement scripts): `ingest_pool(path)` requires the JSON path;
`measure_pool(pool_dict, registry, set)` — registry from `coverage.build_full_registry()` (NOT
templates.py); report fields `sentences_matched`/`sentence_total`/`pc2_sentence_coverage`,
`cards_zero_unparsed`/`entry_count`, `ambiguous_entries`; `QCount` count field is `.selector`.

## ROUND-11-B RESULTS (executed 2026-09-29, HEAD baseline a24d03e, NOT committed)
FIX LANDED (R11-2 ETB subject sweep). Inventory: 62 offending ETB-as-trigger ZoneChangeEvents
(subject=None) across 62 cards, attributed to 41 construction sites = 40 template tids + 1
compiler built-in. **Classification: ALL 40 templates + built-in are class A (own-ETB "When
this/<name> enters" or "As this enters") ⇒ subject=FAtom(IS_SOURCE). Class B offenders: 0** —
every generic-class ETB trigger in M21 was already correctly built with explicit filters
(Garruk's Uprising s4, Terror of the Peaks, Watcher of the Spheres, Thieves' Guild Enforcer,
Containment Priest replacement). Class C: none — corpus guard allow-list is EMPTY.

Class A per module (cards): b2a 32 tids/36 cards (28 singles + basris-lieutenant, bone-pit-brute,
etb-draw-one, scry-n = 2 each; incl. named tids barrin-etb, niambi-etb); b2b 8 tids/24 cards
(alpine-houndmaster 1, etb-basic-land 1, etb-power-condition-draw 1, fierce-empath 1,
named-card-search 3, teferis-tutelage 1, temple-etb-gain-life 11, temple-etb-scry 5);
b5a 1/1 (etb-choose-name, Runed Halo); compiler `_choose_etb_event` 1/1 (Trufflesnout).
Garruk's Uprising nuance: the probe's "1 legit-other" card is BOTH — its s4 trigger is the
correct class-B exemplar AND its s1 ("When this enchantment enters, if you control a creature
with power 4 or greater, draw a card.") was one of the 62 class-A offenders.

Code: `_etb_event()` in templates_b2a.py + templates_b2b.py gained a REQUIRED `subject: Filter`
parameter (docstring: never None; class-A sites pass IS_SOURCE, hypothetical class-B sites must
pass the described filter) — 32 + 8 call sites updated; compiler.py `_choose_etb_event` and
templates_b5a.py `_build_etb_choose_name` got subject=IS_SOURCE. Pattern strings untouched.
1 test pin updated (test_compiler.py choose-opener shape); NEW
MTG_bot/core/compiler/test_etb_subject_guard.py: compiles the whole pool, asserts no
TriggeredAbility ETB ZoneChangeEvent has subject=None outside the (empty, self-checking)
allow-list, plus a synthetic guard-of-the-guard test.

GATES (all EXACT): core suite 1724 passed (1721 + 3 guard). PC-1 301/305 · PC-2 634/639
(0.992175) · PC-3 0 — EXACT pre- AND post-refresh. PC-4: 62 diffs pre-refresh → write_goldens
305 → 0 post. Golden audit vs /tmp/golden_pre_r11b_2026-09-29: 62/305 files changed, top-level
diff keys ⊆ {abilities} in ALL 62 (0 violations), every changed card traces to the classified
62-event inventory (0 orphans). pyright 0 errors on all 6 touched py files. Ruff delta 0
(post-fix categories byte-identical to HEAD baseline: B5 1, I001 1, TRY004 7, UP035 1, UP037 1
on the 5 pre-existing files; new guard file clean). Repo-wide 23 failed / 1751 passed /
1 deselected / 2 xfailed — failure set byte-identical to clean-HEAD baseline (comm empty both
directions vs /tmp/opencode/head_fails.txt). gen_buckets untouched.
