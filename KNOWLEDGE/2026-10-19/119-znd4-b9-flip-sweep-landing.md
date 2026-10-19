# 119 — ZND-4 flip-sweep landing (b9 + Batch-A widen): numbers, findings, defers (2026-10-19)

## Grammar measurement (tree with b9; command: `.venv/bin/python tools/measure_grammar.py --set ZNR`, baseline `/tmp/opencode/znr_baseline_committed.json`)
- Register: 353 -> 333 unparsed shapes. Flip diff vs committed baseline = EXACTLY 20 flips, 0 regressions:
  17 b9 tids + 2 B5a-equip (`{2}{R}`, `{2}{G}`) + 1 B5b "target card" (Bala Ged). Attribution 100% inside the /115 named union.
- PC-1 0.3688 (104/282), PC-2 0.5413 (393/726), PC-3 0, PC-9 stable (two-run determinism), PC-10 exact.
- M21 PC-4: 305/305, 639/639, queue 0->0, DIFF 0 (baseline `/tmp/opencode/m21_pre_znd4.json`).

## Verification gates
- `pytest MTG_bot/core -q`: 2748 passed, 36 subtests, 0 failed. `test_templates_b9.py`: 49/49 (IR pins incl. G-FM2, compile E2E, ~15 executor falsifiers on REAL engine behavior — no build-only falsifiers).
- Scenario packs: 413/413 (`tools/run_scenarios.py`). New pack `tools/scenarios/beyeen_veil_anthem_direction.json` pins anthem DIRECTION (PtDirection.DECREASE, foe 3/3->1/3) + SCOPE (ally untouched) + COST DRAIN: the compiled Beyeen Veil front face carries the printed {1}{U} — mana_pool seeded U:2 drains to U:0. Correction to /117 B2 wording: the shipped "Beyeen free-cast" is NOT mana-free; it is the normal-cost SpellAbility lane.
- G-FM7 fuzz (flipped pool): `.venv/bin/python tools/eval/znr_engine_smoke.py --games 40` -> 40/40, 0 crashes, 0 signatures.
- gen_buckets: all 8 pinned M21 Phase-1 bucket files regenerate additive ("all pinned constraints hold").
- pyright 0 errors on all three touched .py files; ruff clean.

## FINDING 1 (engine, OFF-LIMITS here — for the executor sibling)
`executor/layers.py` attached-static registration (~line 514) carries ONLY `StaticAbility.condition` into the LayerRecord and silently DROPS the atom `duration`-role `DurationWhileCondition` -> while-statics become EVER-LIVE. b9 while-templates re-encoded per b2a precedent (`StaticAbility(atom, condition=CONTROLLER_COUNT_GE(...))`). Committed B4-modify-pt-while-garruk / B4-grant-lifelink-while-counter were "executor-executed" claims that were IR-only; their while-gates do not actually gate in the engine until layers.py carries the duration-role.

## FINDING 2 (VCS hygiene)
Sibling add-A sweeps (686e879/bbcddb0) involuntarily committed my bucket files MID-EDIT: `test_templates_b9.py@HEAD` does not parse (SyntaxError @97). Tree copy fixes it; current ZND-4 changes stay UNSTAGED/uncommitted per shared-index law.

## FINDING 3 (register, not regression)
Blood Beckoning singular "Return target creature card from your graveyard to your hand." was NEVER in the B5b carrier ("target permanent card" | "up to two target creature cards"); one alternation from the widen, OUTSIDE the named union => stays unparsed, no silent partial. Probe pinned in TestRegistryShape.

## Defers (per /115 G-FM revisions)
- ZND-4a: T2 keyword-list rows ("Flying, vigilance." et al.).
- ZND-4b: Taunting Arbormage. ZND-4c: Ondu Inversion.
- **ZND-4d (NEW, engine item from FINDING 1, gate-confirmed by execution)**: `layers.py` attached-static
  registration drops the atom duration-role ⇒ named repro: b4 duration-shape gave **4/4 PT with no
  planeswalker on board** (gate probe); honors only `StaticAbility.condition`/`layer.duration`. Fix =
  carry duration-role (or fold into condition) at registration + executor falsifiers for ALL b4
  while-carriers before any "executor-verified" claim touches those cards. b9 and the Expedition
  T4 flips are UNAFFECTED (condition-lane, gate-probed 2/2→4/2→2/2 across ally arrive/leave).

## ATTRIBUTION SPLIT (the /113 pattern, second occurrence — shared-index law v2)
The body of this wave (templates_b9 682 lines, test_templates_b9 944, b5a/b5b widens, coverage reg,
beyeen pack) was swept into SIBLING commits `686e879`/`bbcddb0`/`fd622ca` by an `add -A`-style
sweep while my files were mid-edit — `test_templates_b9.py@HEAD` shipped a SyntaxError (@97) that
BROKE HEAD test collection until this commit (gate FINDING: "commit immediately, repair HEAD").
No history rewrite (law); this commit carries: tree repairs (b9 pair + test_coverage b9 set),
landing /119, ledger. ORCHESTRATOR battery on the repaired tree: `pytest MTG_bot/core tools -q`
**3003 passed + 36 subtests, exit 0**; packs **413/413** (numbers include sibling tree content —
attribution-clean re-run owed after their lane settles, per /113 precedent).

## DIFF GATE (fresh-eyes, ses_eacf0472…): **COMMIT-GO**
Independent tid-sweep diff (git archive 65af59c vs tree): 20 flips EXACT (17 B9 + 2 equip + Bala
Ged), 0 tid churn, 0 out-of-union; falsifiers audited REAL (zone-move while-gates, three-way
anthem direction, lethal/survive damage pair); zero-consumer census 15/15 b9 tids ≥1 row; defers
all verifiably still unparsed; M21 only PC-5 moved (0.31→0.304 ms — latency noise, both PASS);
fuzz 40/40 0-signatures on the flipped pool.
