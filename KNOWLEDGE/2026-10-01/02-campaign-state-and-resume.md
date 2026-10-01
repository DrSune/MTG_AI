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

## Session numbers so far (all NUMBERS-backed)
Combat arc: engine 288→297/305, all-pool crashes 1→0, suite 2022→2112, packs 3→84, catalog 5504
→re-pinned 4× always 0-unexplained. Viewer live at reports/replays/ (s7 pre-combat · s19/s24 first
combat deaths · s37 control-steal · + per-wave showcases).
