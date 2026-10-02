# 2026-10-01 · 02 — Validation campaign STATE + resume protocol (waves 2+ proceduralized)

## Where we are (all committed, HEAD 225baa4)
Arc 3 combat SHIPPED (round 16) → all-305 pool plays ZERO-crash; engine 297/305 · 45 verbs.
Validation campaign (round 17a/17b/18a/18b, the owner's card-by-card mandate) — wave 1 (ETB
family, 66 cards — the largest shared-builder cohort) COMPLETE: 84/84 packs green in
tools/scenarios/, every assertion authored from PRINTED text (live-Scryfall when doubtful), 2
by-design suspects remain (capture_sphere permanence, wildwood_scourge QX→ETB-state — cast-lane
machinery, next lever).
**16 real semantic bugs found + fixed + pinned before they could compound** — the class the owner
predicted: EtBState never executed; "if you do" clause type free-riding corpus-wide (MAY_DONE now
exists); C15 choice-theft in narrowing; post-SEARCH branch erasure; threshold/count template
conflation; scry-bottom no-op; unfireable trigger; protection repr-mismatch; +8 (16c/17a/18b).
Machinery now standard: tools/audit/ (wave_builder w/ drift-lint, verify_wave 3-stage),
tools/traces/ catalog (first-divergence locator; every semantic move reconciled + repinned),
suspect-law (pack asserts the PRINTED PROMISE; engine frozen during authoring; findings file →
orchestrator adjudication), viewer replays (reports/replays/*.html — open in a browser: card art,
tapped state, stack, micro-decision log with candidates).

## The loop, one page (proceduralized — any session can run a wave)
1. Derive wave: extend tools/audit/wave_builder.py filters (wave 2 = SPELL-resolution family
   [SpellAbility cast paths incl the 2 cast-lane suspects], wave 3 = static/keyword layer cohort,
   wave 4 = mana/activation + costs; each ~40-66 cards) → wave<N>.json (--lint stays green).
2. Author packs, 2 parallel batch agents, engine FROZEN (protocol + style anchor + suspect-law:
   see evidence patterns in doc 18 + 10-01/01; batch-disjoint rows; findings file per wave).
3. Adjudicate: silent-classes → fix batch (rules cites; catalog reconcile; golden moves ONLY via
   set-equal inventory audits); loud-gap machinery → design batch; pack-bugs → author batch.
4. Gates every phase: run_scenarios all green · pytest MTG_bot/core · PC-1/2/3/4 EXACT (+PC-8
   watched: it is compiler-side, moves only with IR audits) · catalog 0-diverge-or-located+repinned
   · engine count honest-report · pyright 0 · ruff delta 0 · orchestrator independently re-runs ALL
   before committing (subagent prose unreliable; once a briefing itself was phantom-contaminated —
   PITFALLS 09-30).
5. Owner-inspect per wave: 2-3 showcase replays + ledger table (card | printed promise | asserts
   | verdict) → owner findings become ledger rows (P0/P1 conventions).

## Known-standing items (not blocking waves)
- Omniscient-v1 hidden-info gap (candidate lists see hidden zones) — DOCUMENTED model gap, decide
  at model-facing-API era; multi-slot designation (arc-3 family); Kinetic Augur may-clause lost at
  frozen-IR boundary (reported-not-patched, IR-audit candidate); search-shuffle tail unconditional
  on fire (residual, doc 19); "Ornery" builder latent conflation (no corpus hit); PHASE_IN orphan +
  HAS_COUNTER_GE (09-29/04 §P2); legacy rule_engine/strategic_brain 23-failure set = untouched debt.
- PC-8 real move needs compiler-side TARGET-selector work (executor designation changed zero IR
  bytes — honest note in 10-01/01).

## Wave-2 derivation (loop step 1, 2026-10-01 · `wave_builder.py --wave2`)
- Cohort rule: any non-token card with a compiled **SpellAbility** node, gated engine-supported exactly as wave 1 (derive-from-IR, zero hand-list). 70 SpellAbility cards found → **65 gate-clean + 2 carry-over = 67 rows** frozen in `tools/audit/wave2.json`; `--wave2 --lint` green, wave-1 `--lint` still green (byte-identical).
- **Excluded-by-flag 5**: Cancel / Lofty Denial / Miscast / Rewind (each sole-cause COUNTER_SPELL) + Sublime Epiphany (COPY+COUNTER_SPELL) — recorded with reasons in `meta.excluded_by_flag`; re-admit when those atoms land.
- **Carry-over suspects verified OUT of the natural cohort**: Capture Sphere + Wildwood Scourge compile with **zero SpellAbility nodes** (the cast-lane gap is the suspect itself); appended as explicit `carry_over: true` rows, both whole-card engine_supported=True, art present.
- Verb histogram (67-row cohort, mechanics ∩ spell effects): DRAW 12 · MODIFY_PT 11 · MOVE_ZONE 8 · DESTROY 8 · GRANT_ABILITY 7 · DEAL_DAMAGE 7 (then CREATE_TOKEN 6, EXILE 6, PUT_COUNTER 5, DISCARD 4).
- Command: `.venv/bin/python tools/audit/wave_builder.py --wave2 [--lint]` · gates: pytest core 2112+4subtests unchanged (builder tools-only), pyright 0, ruff Δ0 on builder. Pack authoring = next task (loop step 2).

## Addendum — stale-briefing re-dispatch caught by ground truth (2026-10-01, 13a re-issue probe)

A delegation arrived re-issuing **round-13 phase 13a** (DRAW/SEARCH/FLIP_COIN/END_TURN/EXTRA_TURN/
LOSE_GAME + loyalty + phase tick) as pending work at "HEAD f50e335, suite 1876, engine 206→+58".
Ground truth: **13a shipped 2026-09-29 in 9120e2d** (+58 EXACT as the /11 plan predicted; the 58
CONTAINING cards were exactly the 58 sole-offender flips), and 13b/13c/14/16/17/18 are all com-
mitted above it — the briefing was the pre-compaction round-13 plan re-dispatched (the resume
protocol's own warning: "once a briefing itself was phantom-contaminated — PITFALLS 09-30" fired a
second time, caught by verifying against code/git before any edit). All 13a deliverables verified
present: `_v_draw…_v_lose_game` (verbs.py HANDLERS), CostLoyalty branch + CR 606.3 clock (legality
.py 619/774/1170), attach-time loyalty seed (binding.py 358-367), Executor.phase tick, and the CR
121.2→121.3 empty-library loss VERDICT (games.py harness-side loser scan, since 14a). No code was
written. Independent re-measure at HEAD f50e335 confirms the campaign record:
`.venv/bin/python tools/measure_grammar.py --with-engine-flags` → **engine 297/305 · V2 45 verbs,
PC-1 301/305 · PC-2 634/639 · PC-3 0 · PC-4 0 EXACT**; `pytest MTG_bot/core -q` → **2112 + 4 sub-
tests, 0 failed** (4.85 s). Working tree after re-measure: only the tool's own NUMBERS row +
reports/grammar_2026-10-01.json. Next action stays loop step 2: **wave-2 pack authoring** (67 rows
frozen in tools/audit/wave2.json), engine frozen. NOTE for the orchestrator: commit f50e335 carries
the *wrong message* — it says "round-13 binding plan" but commits the wave-2 resume note + builder;
the real 13a plan doc is c820fc9.

## Session numbers so far (all NUMBERS-backed)
Combat arc: engine 288→297/305, all-pool crashes 1→0, suite 2022→2112, packs 3→84, catalog 5504
→re-pinned 4× always 0-unexplained. Viewer live at reports/replays/ (s7 pre-combat · s19/s24 first
combat deaths · s37 control-steal · + per-wave showcases).

## Addendum — wave 2 CLOSED (2026-10-01)
Full loop executed; see /08-wave2-closeout.md. Packs 148, suite 2168, suspects 5 (all
compiler-limited STOPs, routed). Resume point now: wave-3 derivation (statics/keywords).

## Addendum — wave 3 CLOSED (2026-10-01)
Full loop; see /14-wave3-closeout.md. Packs 204, suite 2213, ledger 8 (compiler backlog, incl.
creature-spell-node systemic question). Promotion law hardened (MOVE+STRIP, one dir per card).
Resume point now: wave-4 derivation (mana/activation cohort).

## Addendum — wave 4 CLOSED (2026-10-01)
See /20-wave4-closeout.md. Packs 248, suite 2239, ledger 12 = ALL compiler-campaign routed;
zero open engine-side suspects. Next: whole-corpus coverage audit (which cards belong to no
family and lack a pack) to decide wave 5 or corpus-complete declaration.

## Addendum — wave 5 CLOSED → CORPUS ADJUDICATION-COMPLETE (2026-10-02)
Five waves consumed: 66+67+55+43+31 rows. Packs 282, suite 2271, 305/305 cards accounted for
(/26-wave5-closeout.md). All 17 suspects compiler-routed. Next arc: compiler campaign (golden
inventory protocol) + 2 logged micro-gaps (Treasure activation, Forgotten Sentinel).

## Addendum — phase-3 compiler campaign state (2026-10-02, session end)
C1-C5 + 23a + 24a landed: 302 green packs, suite 2322, games 100/100 DECISIVE & 0 crash
(33.5 mean turns), all PC Δ0 except honest compiler-side shifts (PC-1 303/305, PC-2 637/639).
Ledger: 2 suspects, BOTH owner-blocked (grammar round-11: damage destination [pyreling] +
CREATE_TOKEN.controller [secure_the_scene]). Ratifications on record: C1-form audited golden
moves (C2 note), additive QPropField.LIFE (this doc), PC-8 re-baseline accepted.
Peer's life clause still dropped compiler-side (emit batch 2 residue, documented in its pack).
Owner replays: s8/s12/s21/s30. Next when owner rules grammar round: batch 6, then response-
window arc (R16-1 unlock, COUNTER_SPELL family ×5).
