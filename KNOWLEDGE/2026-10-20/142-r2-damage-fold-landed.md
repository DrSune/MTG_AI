# 142 — R2 F4 damage fold LANDED (CombatDamageEvent deleted)

Spec: /140. Scope: Jeskai Elder + Feline Sovereign [M21], Nimble Trapfinder [ZNR]
emissions folded to `DamageDealtEvent{amount:QUnbounded, filter:FAnd(()), source:<old
CDE filter VERBATIM>, combat:True}` per the law in tools/audit/atom_sortdelta_r2.py.

## Landed
- Emission folds: templates_b2b.py (Jeskai, Feline), templates_b8.py (Nimble grant).
- CombatDamageEvent DELETED from the vocabulary: class + EventSpec union + _EV_CLASSES
  + _DATACLASSES + _TAG_FIELDS + _EVENT_TAGS (ability_tree.py); binding.py matcher
  branch; replacements.py import + _COMBAT_EVENTS. BREAK-2 honored: the
  KIND_COMBAT_DAMAGE journal EMISSION (executor/__init__.py, per-dealer whole-assignment
  row) SURVIVES as an audit feed — emitted, never subscribed (binding.py:103 noqa-pinned).
- Convergence (§9): post-fold Jeskai event canonical_json == Garruk's Harbinger's
  VERBATIM (test_ontology_r2 TestConvergence).
- D13 split over-fire ACCEPTED (orchestrator ruling (a), spec §6 BREAK-1): split 1+2
  journals 2 DAMAGE rows -> 2 fires; pinned at count 2 with CR-603.2 comments.
  Recipient-SET row redesign stays ticket ZND-8.
- Population zero: reports/r2_census.json rerun byte-identical + battery census leg;
  post-fold 13 damage nodes across pools, 12 DDE M21 + 1 DDE ZNR, CDE 0.
- Goldens re-baked TARGETED, changed set EXACTLY the 2 predicted M21 oids
  (dfbd5ad1 Jeskai, 05f0feb6 Feline), all other 303 byte-identical. COMMIT LAW: the two
  golden files MUST land in the SAME commit as the code (PITFALLS 2026-10-19 R1a).

## NEW discovery — the 16a DAMAGE pre-bind swallowed the 18b designation lane
Pre-fold, Feline's DESTROY rode COMBAT_DAMAGE rows (no pre-bind, _designate ran, but
referent=dealer -> 0 candidates -> honest CR-603.4 nothing). Post-fold the DAMAGE row's
16a TARGET_PLAYER pre-bind (bindings["target"]=cause, Brash Taunter's echo rationale)
made `_fire` skip _designate ENTIRELY — the printed "destroy up to one target ... that
player controls" could never designate. Fixed with a NARROW gate (binding.py
_damage_designation_is_event_borne): lift the pre-bind when EVERY TARGET-mode
referent-free Selector's filter gates on CONTROLLER_IS who=<Selector referent='event'>
(event-subject-parameterized population: Feline Sovereign, Chandra's Incinerator) AND
the node reads TARGET_PLAYER nowhere (Brash Taunter's echo keeps its dealer pre-bind
exactly as 16a bound it; r22a DIES-twin precedent). Gate v2 (diff-gate probe4 follow-up,
same day): the shape check alone was fail-OPEN on the NON-event polarity — a TARGET slot
with e.g. CONTROLLER_IS OPPONENT kept the pre-bind and resolve_selector takes a bound
handle as FROZEN DESIGNATION WITH NO FILTER VALIDATION, so the dealer destroyed ITSELF
(probe4 Variant A: ask never fired, own creature died instead of the totem; the two
silences have DIFFERENT mechanics — a non-event filter resolves the slot TO THE DEALER,
a `who=<selector 'event'>` filter dies at the referent-candidate step and lands on zero).
Fix: `_prebind_legal_for_targets` validates the dealer against every TARGET selector's
filter at the SAME choke point (query.legal_targets population; a CARD designation
legalises a PLAYER-zone slot via the 16a controller mapping, so Brash's lane is
untouched) and lifts on validation failure to the ask lane (RED-first test:
TestDesignationValidation in test_ontology_r2.py; /tmp/r2_break3_red.log). Known-narrow
by design (code comments): the shape scan never reads trigger CONDITIONS, and the
TARGET_PLAYER scan misses bare-role reads (LOSE_LIFE controller=TARGET_PLAYER) — probe4
Variant D proved `_designation`'s broader scan + loud raise is the backstop for those.
Feline E2E now lands rules-faithful:
TARGETING row designates the DAMAGED player's artifact (post-fold referent shift —
loudly-declared deviation from the CDE lane's dealer-read, which never worked anyway).
Blast-radius census (compile-walk M21+ZNR): exactly 3 damage triggers with TARGET slots
— Feline (fixed), Brash Taunter (gate=False, untouched, pins green), Chandra's
Incinerator (gate=True; all its pins incl. r23a tripwire green — event-borne reading is
the rules-faithful one; prior lane resolved dealer-designations, i.e. nothing/wrong).

## Verification (all EXECUTED 2026-10-20)
- Battery MTG_bot/core/test_ontology_r2.py 15/15 (red-first: 9 RED pre-change incl. all
  3 shape legs, convergence, census, 3 split pins, Feline E2E; /tmp/r2_red_prechange.log)
  + TestDesignationValidation added by the diff-gate follow-up (RED-first pre-fix:
  no-ask + dealer self-destroy, /tmp/r2_break3_red.log; GREEN post-fix) = 16 tests.
- Full core+tools suite (post BREAK-3 fix): `pytest MTG_bot/core tools -q` -> 3165
  passed, 53 skipped, 0 failed. Core-only: 2879 passed. Focused
  `-k "r2 or ontology or brash or chandra or taunter or designation"`: 224 passed.
  (Earlier same-day pre-fix figure 2878+285 was core-only-vs-tools split; the full
  core+tools count is the 3163->3165 number.)
- packs 428/428 (tools/run_scenarios.py); double-run stdout BYTE-IDENTICAL.
- fuzz ZNR 40/40, 0 crashes, 0 signatures (znr_engine_smoke.py --out /tmp/opencode/r2/fuzz).
- atom_field_table rc=0; ontology_conformance PASS errors=0 warns=7 (pre-existing set).
- Re-pin inventory done identity-keyed: test_executor_binding (folded DDE pin + R2
  comment), test_templates_b2b (Jeskai/Feline shape legs), test_ability_tree (all-thirteen
  -> twelve, 2 ex-CDE constructions), test_ability_tree_t3 (vector re-pinned
  e7275e24->85758a08, R0-style amendment skips the pre-T3 key assert for the folded
  vector only), clause_audit T:DamageDealtEvent. NO measure_grammar --refresh-goldens.

## BREAK-3 fix (diff-gate FOLLOW-UP, same day — gate verdict FIX-THEN-GO)
- BREAK-3 (blocking, FIXED): the event-borne shape gate was fail-OPEN on the
  NON-event polarity — a TARGET slot with e.g. CONTROLLER_IS OPPONENT kept the
  16a pre-bind and resolve_selector takes a bound handle as frozen designation
  with ZERO filter validation: the dealer destroyed ITSELF, no ask, no journal
  (gate probe4 Variant A, /tmp/opencode/r2gate/probe4.py). Fix: second lift
  condition `_prebind_legal_for_targets` in binding.py — validates the dealer
  against every TARGET selector via query.legal_targets (ONE legality
  opinion, §8.3), card designation legalises a PLAYER-zone slot through its
  controller (16a); fail -> lift to the ask lane. RED-FIRST:
  TestDesignationValidation.test_non_event_filter_target_asks_not_the_dealer
  (probe4 A ported, permanent) — RED pre-fix pinned in /tmp/r2_break3_red.log
  (Variant B = preservation pin, green both sides), GREEN post-fix.
- FIX-2: PITFALLS entry + this note corrected — pre-bind swallowed slots
  resolved TO THE PRE-BOUND DEALER WITHOUT VALIDATION (empirical misfire),
  not "to NOTHING" (that was the referent-candidate path, event-borne filters).
- FIX-3: code comments pin the known-narrow scan (no trigger CONDITIONS;
  TARGET_PLAYER scan misses bare-role reads) with _designation's broader scan
  + loud multi-slot raise as the proven backstop (probe4 D).
- Verification re-EXECUTED post-fix: full `pytest MTG_bot/core tools -q` ->
  3165 passed + 53 subtests, 0 failed; `-k "r2 or ontology or brash or chandra
  or taunter"` -> 292 passed; battery 17/17; packs 428/428 x2 BYTE-IDENTICAL
  (fold surface untouched by the fix — same corpus); ruff clean on touched
  files. NITs: sortdelta --out confirmed committed (17d5fc3); stray
  reports/znr_engine_smoke_2026-10-20.md deleted (copy at /tmp/opencode/r2/).
