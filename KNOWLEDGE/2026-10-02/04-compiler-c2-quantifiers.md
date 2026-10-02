# 04 — Compiler campaign C2: existential quantifiers + Fabled tapped_on_enter (2026-10-02)

Roadmap batches 0+1 landed in one campaign (HEAD cb98a7c). Compiler/templates + goldens
only; engine FROZEN. Three goldens moved — every one under the C1-form inventory audit
(`/tmp/opencode/c2_inventory_audit.py`, pre-snapshot `/tmp/golden_pre_c2/`, fresh compile
`/tmp/golden_new_c2/`): **moved=3, keys={abilities} only, 302/305 byte-identical**, and
per-card printed-vs-compiled multiset set-equality. Scope was verified first: M21 `text`
grep proves the `B5c-cost-sacrifice-search` regex fires ONLY on Fabled Passage, so no
fourth golden could legitimately move.

## Verdicts

1. **Fabled Passage — FIXED, GREEN** (`tools/scenarios/fabled_passage_enters_tapped.json`).
   Golden `0c85b8f7`: the <4-lands branch of the sacrifice ability enters the searched
   land **tapped as printed**, but `_build_cost_sacrifice_search` (templates_b5c.py:1729)
   emitted a SEARCH atom without the flag. Fix: one pair `("tapped_on_enter", True)` on
   the SEARCH atom. Set-evidence: pair-set +tapped_on_enter, FAtom set otherwise EQUAL.
   The >=4-lands conditional untap tail (`_build_then_if_lands_untap`, :2163,
   `Conditional(lands>=4 → UNTAP)`) is untouched and stays falsifiable — the flag makes
   the printed condition real, not aspirational. Executor `._v_search` already honours
   `tapped_on_enter`; zero engine change.

2. **Adherent of Hope — FIXED, GREEN** (`tools/scenarios/adherent_of_hope.json`).
   Golden `b5f5400e`: printed "When you cast a Basri planeswalker spell…" was compiled as
   a bare AND of NAME_CONTAINS "Basri" + TYPE_EQ Planeswalker + CONTROLLER_IS YOU with the
   existential **quantifier dropped** (wave-5 stop: "quantifier loss, 19a precedent").
   Fix (templates_b2a.py `_build_adherent_of_hope`): wrap in
   `FAtom(CONTROLLER_COUNT_GE, inner_filter=FAnd(same 3 atoms), count=QConst(1))`.
   Set-evidence: the 3 filter atoms preserved VERBATIM inside inner_filter; delta = +1
   COUNT_GE(count=1) quantifier, −0 atoms. `CONTROLLER_COUNT_GE` is a handle-free world
   census (quantity.py:883, YOU-scoped) — no new executor surface.

3. **Ornery Dilophosaur — FIXED, GREEN** (`tools/scenarios/ornery_dilophosaur.json`).
   Golden `8291bc2e`: "_ creatures you control with power 4 or greater get +1/+1" had the
   gate compiled as `CONTROLLER_COUNT_GE count=4` — the **threshold value stolen into the
   count slot** (printed gate is "at least one such creature"). Fix (templates_b2b.py
   :1551): `_you_control_at_least(_creature_power_ge_filter(n), n)` → count literal `1`.
   Set-evidence: multiset {COUNT_GE count=4} → {COUNT_GE count=1}, inner POWER_GE filter
   set EQUAL. Sibling precedent already correct: Garruk's Uprising row (b2b:1497, count=1,
   green pack); historian-Teferi row count=1 likewise (Teferi's Protégé green).

Pins: NEW `test_compiler_c2.py` (5 falsifiability pins — flag stamp, falsifiable
conditional tail, adherent census, ornery count=1-vs-power=4 separation, and a synthetic
power-6/+1/+1 sentence proving count decouples from the printed threshold); AMENDED 2
old pins that had witnessed the miscompiles (`test_adherent_of_hope_is_combat_turn_phase`,
`test_ornery_attack_power_condition`).

## Gate numbers (all after landing)

| Gate | Result | Command | Note |
|---|---|---|---|
| golden audit | **3 files moved, keys={abilities}, 302/305 byte-identical, set-equal evidence** | `/tmp/opencode/c2_inventory_audit.py` vs `/tmp/golden_pre_c2` | C1 protocol; production goldens == fresh tree post-refresh |
| scenarios | **290/290** (287 + 3 promoted MOVE+strip) | `.venv/bin/python tools/run_scenarios.py` | 3/3 green under fixed IR BEFORE promotion |
| suspects | **11 files, 0/11 pass** (law holds) | `.venv/bin/python tools/run_scenarios.py --dir tools/audit/suspects` | 14 on disk at HEAD (roadmap's "13" stale); 3 promoted |
| suite | **2277 + 3 subtests, 0 failed** | `pytest MTG_bot/core -q` | 2272 + 5 new pins |
| grammar | PC EXCEPT: PC-1 301/305 · PC-2 634/639 · PC-3 0 · PC-4 0 (refreshed) · **PC-8 0.3213 Δ0 no-move** | `tools/measure_grammar.py --set M21 --refresh-goldens --with-engine-flags` | engine 297/305; PC-6 orphan pre-existing FAIL; all Δ0 vs baseline |
| catalog | **6/10 diverged → repin → 0/10** | `tools/traces/catalog.py compare` / `repin` | attribution: every diverging seed gains exactly +2 entries incl. one new `TAP_STATE·SEARCH` (Fabled flag); outcomes identical per seed |
| games | **100 seeds, 86 survived, 0 crash classes** | `.venv/bin/python -m MTG_bot.core.executor.games --seeds 100 --pool all` | mean_turns 57.69; reports/games_2026-10-02.json |
| lints | pyright **0 errors** on 6 touched files; ruff **all pass** | `pyright` / `ruff check` | engine untouched → suite count honest |

## Rig laws learned (candidate PITFALLS rows)

- **Threshold-vs-count law**: a printed "_ creatures with power N or greater" gate is
  `CONTROLLER_COUNT_GE count=1` with `POWER_GE N` as inner filter — the printed number N
  is a filter operand, NEVER the quantifier count. Any `_you_control_at_least(pred, n)`
  call site where n doubles as both is suspect; grep for it on future batches.
- **Insertion-shift law (catalog)**: an audited ADDITIVE emission (new journal event)
  makes positional compare show cascading diffs (TAP/UNTAP/TURN_PHASE re-hashes) on every
  seed whose games touch the card. Attribution test = entry-count delta + the new
  event-type + identical outcomes, THEN repin. 6 seeds × +2 entries here, all Fabled.
- **Falsifiable-conditional law**: an unconditional flag (tapped_on_enter) plus a printed
  conditional correction (untap-if-lands≥4) is the CORRECT compile — the condition lives
  in the tail, not in suppression of the flag. Suppressing the flag would make the ≥4
  branch unfalsifiable.
