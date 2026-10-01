# NUMBERS — dated measurement log

Latest entry first. Every row: date, number, producing command, notes. A number must have all three
to be admissible (METRICS.md rail: the instrument must be reproducible).

---

## 2026-10-01 (round 18b — designation channel; supersedes 18a pack/core rows)

| Number | Value | Command | Notes |
|---|---|---|---|
| Scenario packs | **84/84** | `python tools/run_scenarios.py` | 63 + 21 repatriated by the 18b designation channel |
| Suspects | **0/2** | `python tools/run_scenarios.py --dir tools/audit/suspects` | capture_sphere (cast-lane permanence) + wildwood_scourge (cast-lane QX→ETB-state) stay loud BY DESIGN |
| Core suite | **2112 passed** | `pytest MTG_bot/core -q` | 2096 + 16 pins (test_executor_designation.py) + 1 amended legality probe |
| Trace catalog | **0 diverging of 10 seeds** | `python tools/traces/catalog.py compare --pool engine --seeds 10 --deck-pairs-seed 1409 --turns 60` | byte-identical journals — NO re-pin (engine-batch cards never hit designation paths) |
| PC-8 targetable | **0.3213 (98/305) UNCHANGED** | `python tools/measure_grammar.py --set M21` | compiler-side pool property (coverage.py TARGET-mode selector count) — executor designation CANNOT move it; the 12-card executor lane (crash→run) is the real gain, honestly reported |
| PC-1..5/9/10 | EXACT baseline | `python tools/measure_grammar.py --set M21` | PC-4 0 diffs = goldens frozen |
| Engine flags | **297/305 · 45 verbs UNCHANGED** | `python tools/measure_grammar.py --set M21 --with-engine-flags` | static dispatch census, designation-blind |

---

## 2026-10-01 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.9869** (301/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **0.9922** (634/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.242 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.0934** (DRAW) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |
| PC-7 engine_supported_cards | **297/305** (0.9738) | `python tools/measure_grammar.py --with-engine-flags` | T6 executor dispatch over 45 verbs (SUPPORTED_VERBS_V2) — honest flag, not a target |


## 2026-10-01 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.9869** (301/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **0.9922** (634/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.24 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.0934** (DRAW) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-10-01 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.9869** (301/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **0.9922** (634/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.268 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.0934** (DRAW) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |
| PC-7 engine_supported_cards | **297/305** (0.9738) | `python tools/measure_grammar.py --with-engine-flags` | T6 executor dispatch over 45 verbs (SUPPORTED_VERBS_V2) — honest flag, not a target |


## 2026-10-01 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.9869** (301/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **0.9922** (634/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.273 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.0934** (DRAW) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-10-01 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.9869** (301/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **0.9922** (634/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.268 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.0934** (DRAW) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |
| PC-7 engine_supported_cards | **297/305** (0.9738) | `python tools/measure_grammar.py --with-engine-flags` | T6 executor dispatch over 45 verbs (SUPPORTED_VERBS_V2) — honest flag, not a target |


## 2026-10-01 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.9869** (301/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **0.9922** (634/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.274 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.0934** (DRAW) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-09-30 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.9869** (301/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **0.9922** (634/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.243 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.0934** (DRAW) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-09-30 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.9869** (301/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **0.9922** (634/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.267 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.0934** (DRAW) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |
| PC-7 engine_supported_cards | **297/305** (0.9738) | `python tools/measure_grammar.py --with-engine-flags` | T6 executor dispatch over 45 verbs (SUPPORTED_VERBS_V2) — honest flag, not a target |


## 2026-09-30 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.9869** (301/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **0.9922** (634/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.237 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.0934** (DRAW) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |
| PC-7 engine_supported_cards | **297/305** (0.9738) | `python tools/measure_grammar.py --with-engine-flags` | T6 executor dispatch over 45 verbs (SUPPORTED_VERBS_V2) — honest flag, not a target |


## 2026-09-30 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.9869** (301/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **0.9922** (634/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.24 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.0934** (DRAW) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |
| PC-7 engine_supported_cards | **297/305** (0.9738) | `python tools/measure_grammar.py --with-engine-flags` | T6 executor dispatch over 45 verbs (SUPPORTED_VERBS_V2) — honest flag, not a target |


## 2026-09-30 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.9869** (301/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **0.9922** (634/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.24 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.0934** (DRAW) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |
| PC-7 engine_supported_cards | **297/305** (0.9738) | `python tools/measure_grammar.py --with-engine-flags` | T6 executor dispatch over 45 verbs (SUPPORTED_VERBS_V2) — honest flag, not a target |


## 2026-09-30 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.9869** (301/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **0.9922** (634/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.235 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.0934** (DRAW) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |
| PC-7 engine_supported_cards | **297/305** (0.9738) | `python tools/measure_grammar.py --with-engine-flags` | T6 executor dispatch over 45 verbs (SUPPORTED_VERBS_V2) — honest flag, not a target |


## 2026-09-30 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.9869** (301/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **0.9922** (634/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.242 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.0934** (DRAW) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-09-30 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.9869** (301/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **0.9922** (634/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.262 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.0934** (DRAW) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |
| PC-7 engine_supported_cards | **293/305** (0.9607) | `python tools/measure_grammar.py --with-engine-flags` | T6 executor dispatch over 43 verbs (SUPPORTED_VERBS_V2) — honest flag, not a target |


## 2026-09-30 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.9869** (301/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **0.9922** (634/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.282 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.0934** (DRAW) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |
| PC-7 engine_supported_cards | **293/305** (0.9607) | `python tools/measure_grammar.py --with-engine-flags` | T6 executor dispatch over 43 verbs (SUPPORTED_VERBS_V2) — honest flag, not a target |


## 2026-09-30 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.9869** (301/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **0.9922** (634/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.314 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.0934** (DRAW) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |
| PC-7 engine_supported_cards | **293/305** (0.9607) | `python tools/measure_grammar.py --with-engine-flags` | T6 executor dispatch over 43 verbs (SUPPORTED_VERBS_V2) — honest flag, not a target |


## 2026-09-30 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.9869** (301/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **0.9922** (634/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.277 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.0934** (DRAW) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |
| PC-7 engine_supported_cards | **293/305** (0.9607) | `python tools/measure_grammar.py --with-engine-flags` | T6 executor dispatch over 43 verbs (SUPPORTED_VERBS_V2) — honest flag, not a target |


## 2026-09-30 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.9869** (301/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **0.9922** (634/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.282 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.0934** (DRAW) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |
| PC-7 engine_supported_cards | **291/305** (0.9541) | `python tools/measure_grammar.py --with-engine-flags` | T6 executor dispatch over 41 verbs (SUPPORTED_VERBS_V2) — honest flag, not a target |


## 2026-09-30 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.9869** (301/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **0.9922** (634/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.278 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.0934** (DRAW) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |
| PC-7 engine_supported_cards | **291/305** (0.9541) | `python tools/measure_grammar.py --with-engine-flags` | T6 executor dispatch over 41 verbs (SUPPORTED_VERBS_V2) — honest flag, not a target |


## 2026-09-30 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.9869** (301/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **0.9922** (634/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.274 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.0934** (DRAW) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |
| PC-7 engine_supported_cards | **291/305** (0.9541) | `python tools/measure_grammar.py --with-engine-flags` | T6 executor dispatch over 41 verbs (SUPPORTED_VERBS_V2) — honest flag, not a target |


## 2026-09-30 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.9869** (301/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **0.9922** (634/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.287 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.0934** (DRAW) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |
| PC-7 engine_supported_cards | **288/305** (0.9443) | `python tools/measure_grammar.py --with-engine-flags` | T6 executor dispatch over 40 verbs (SUPPORTED_VERBS_V2) — honest flag, not a target |


## 2026-09-30 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.9869** (301/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **0.9922** (634/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.246 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.0934** (DRAW) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-09-30 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.9869** (301/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **0.9922** (634/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.294 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.0934** (DRAW) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-09-30 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.9869** (301/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **0.9922** (634/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.281 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.0934** (DRAW) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |
| PC-7 engine_supported_cards | **286/305** (0.9377) | `python tools/measure_grammar.py --with-engine-flags` | T6 executor dispatch over 39 verbs (SUPPORTED_VERBS_V2) — honest flag, not a target |


## 2026-09-30 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.9869** (301/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **0.9922** (634/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.277 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.0934** (DRAW) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |
| PC-7 engine_supported_cards | **286/305** (0.9377) | `python tools/measure_grammar.py --with-engine-flags` | T6 executor dispatch over 39 verbs (SUPPORTED_VERBS_V2) — honest flag, not a target |


## 2026-09-30 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.9869** (301/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **0.9922** (634/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.278 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.0934** (DRAW) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |
| PC-7 engine_supported_cards | **286/305** (0.9377) | `python tools/measure_grammar.py --with-engine-flags` | T6 executor dispatch over 39 verbs (SUPPORTED_VERBS_V2) — honest flag, not a target |


## 2026-09-30 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.9869** (301/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **0.9922** (634/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.239 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.0934** (DRAW) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-09-30 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.9869** (301/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **0.9922** (634/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.234 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.0934** (DRAW) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-09-30 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.9869** (301/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **0.9922** (634/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.243 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.0934** (DRAW) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-09-30 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.9869** (301/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **0.9922** (634/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.24 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.0934** (DRAW) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-09-30 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.9869** (301/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **0.9922** (634/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.238 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.0934** (DRAW) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-09-30 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.9869** (301/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **0.9922** (634/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.24 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.0934** (DRAW) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-09-30 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.9869** (301/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **0.9922** (634/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.239 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.0934** (DRAW) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-09-30 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.9869** (301/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **0.9922** (634/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, refreshed) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.243 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.0934** (DRAW) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-09-30 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.9869** (301/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **0.9922** (634/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.242 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.0934** (DRAW) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-09-30 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.9869** (301/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **0.9922** (634/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.24 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.0934** (DRAW) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |
| PC-7 engine_supported_cards | **286/305** (0.9377) | `python tools/measure_grammar.py --with-engine-flags` | T6 executor dispatch over 39 verbs (SUPPORTED_VERBS_V2) — honest flag, not a target |


## 2026-09-30 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.9869** (301/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **0.9922** (634/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.24 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.0934** (DRAW) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |
| PC-7 engine_supported_cards | **286/305** (0.9377) | `python tools/measure_grammar.py --with-engine-flags` | T6 executor dispatch over 39 verbs (SUPPORTED_VERBS_V2) — honest flag, not a target |


## 2026-09-29 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.9869** (301/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **0.9922** (634/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.269 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.0934** (DRAW) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |
| PC-7 engine_supported_cards | **279/305** (0.9148) | `python tools/measure_grammar.py --with-engine-flags` | T6 executor dispatch over 35 verbs (SUPPORTED_VERBS_V2) — honest flag, not a target |


## 2026-09-29 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.9869** (301/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **0.9922** (634/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.262 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.0934** (DRAW) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |
| PC-7 engine_supported_cards | **279/305** (0.9148) | `python tools/measure_grammar.py --with-engine-flags` | T6 executor dispatch over 35 verbs (SUPPORTED_VERBS_V2) — honest flag, not a target |


## 2026-09-29 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.9869** (301/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **0.9922** (634/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.272 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.0934** (DRAW) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |
| PC-7 engine_supported_cards | **279/305** (0.9148) | `python tools/measure_grammar.py --with-engine-flags` | T6 executor dispatch over 35 verbs (SUPPORTED_VERBS_V2) — honest flag, not a target |


## 2026-09-29 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.9869** (301/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **0.9922** (634/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.241 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.0934** (DRAW) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |
| PC-7 engine_supported_cards | **279/305** (0.9148) | `python tools/measure_grammar.py --with-engine-flags` | T6 executor dispatch over 35 verbs (SUPPORTED_VERBS_V2) — honest flag, not a target |


## 2026-09-29 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.9869** (301/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **0.9922** (634/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.249 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.0934** (DRAW) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |
| PC-7 engine_supported_cards | **264/305** (0.8656) | `python tools/measure_grammar.py --with-engine-flags` | T6 executor dispatch over 30 verbs (SUPPORTED_VERBS_V2) — honest flag, not a target |


## 2026-09-29 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.9869** (301/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **0.9922** (634/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.257 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.0934** (DRAW) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |
| PC-7 engine_supported_cards | **264/305** (0.8656) | `python tools/measure_grammar.py --with-engine-flags` | T6 executor dispatch over 30 verbs (SUPPORTED_VERBS_V2) — honest flag, not a target |
| PC-7 semantics (ruling iii) | **verb-dispatchability, not playability**: 46 SpellAbility cards read True while casting is unimplemented (fold sees their atoms only); after 13b True ≈ actually playable minus combat | `python tools/measure_grammar.py --with-engine-flags` | orchestrator ruling 2026-09-29 §11(iii) — no compiler change; honest documentation is the fix |


## 2026-09-29 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.9869** (301/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **0.9922** (634/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.284 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.0934** (DRAW) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |
| PC-7 engine_supported_cards | **206/305** (0.6754) | `python tools/measure_grammar.py --with-engine-flags` | T6 executor dispatch over 24 verbs (SUPPORTED_VERBS_V2) — honest flag, not a target |


## 2026-09-29 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.9869** (301/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **0.9922** (634/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.29 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.0934** (DRAW) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |
| PC-7 engine_supported_cards | **206/305** (0.6754) | `python tools/measure_grammar.py --with-engine-flags` | T6 executor dispatch over 24 verbs (SUPPORTED_VERBS_V2) — honest flag, not a target |


## 2026-09-29 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.9869** (301/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **0.9922** (634/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.295 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.0934** (DRAW) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |
| PC-7 engine_supported_cards | **206/305** (0.6754) | `python tools/measure_grammar.py --with-engine-flags` | T6 executor dispatch over 24 verbs (SUPPORTED_VERBS_V2) — honest flag, not a target |


## 2026-09-29 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.9869** (301/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **0.9922** (634/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.239 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.0936** (DRAW) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-09-29 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.9869** (301/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **0.9922** (634/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, refreshed) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.242 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.0936** (DRAW) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-09-29 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.9869** (301/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **0.9922** (634/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **4 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — FAIL |
| PC-5 compile_latency p99 | **0.244 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.0936** (DRAW) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-09-29 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.9738** (297/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **0.9859** (630/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.237 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **2** / max share **0.0925** (DRAW) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-09-29 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.9738** (297/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **0.9859** (630/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.239 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.0925** (DRAW) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-09-29 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.9738** (297/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **0.9859** (630/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, refreshed) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.238 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.0925** (DRAW) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-09-29 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.9738** (297/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **0.9859** (630/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **11 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — FAIL |
| PC-5 compile_latency p99 | **0.239 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.0925** (DRAW) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-09-29 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.9410** (287/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **0.9671** (618/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.232 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **3** / max share **0.0930** (MODIFY_PT) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3180** (97/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-09-29 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.9410** (287/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **0.9671** (618/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.233 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **3** / max share **0.0930** (MODIFY_PT) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3180** (97/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-09-28 — round-8-C cap (hand-written; supersedes reading the auto-blocks below in isolation)

Pre-batch → post-batch (`python tools/measure_grammar.py --set M21`, 3 runs:
PRE-verify / refresh / POST-verify — the auto-blocks below are per-run snapshots):
PC-1 **274→287/305**, PC-2 **599→618/639** (+19 = exactly the 19 landed rows),
PC-3 **0**, PC-4 **0 verified** (14 goldens re-baselined, diff-keys = {abilities}
only), PC-6 orphans **3→1** (GET_EMBLEM + ADD_LAND_PLAY consumed; PHASE_IN stands;
max-share FAIL is standing, MODIFY_PT 0.0930 — untouched by 8-C), PC-8 **96→97/305**
(new TARGET selectors; standing FAIL), queue **40→21**. Suite 1521 passed;
gen_buckets pins B3 46→47, B4 38→43, JSONs byte-identical. Details:
`2026-09-28/10-round8c-results.md`.

## 2026-09-28 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.9410** (287/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **0.9671** (618/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, refreshed) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.231 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.0930** (MODIFY_PT) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3180** (97/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-09-28 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.9410** (287/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **0.9671** (618/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **14 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — FAIL |
| PC-5 compile_latency p99 | **0.229 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.0930** (MODIFY_PT) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3180** (97/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-09-28 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.8984** (274/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — FAIL |
| PC-2 sentence_coverage | **0.9374** (599/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — FAIL |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.222 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **3** / max share **0.0963** (MODIFY_PT) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3148** (96/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-09-28 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.8984** (274/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — FAIL |
| PC-2 sentence_coverage | **0.9374** (599/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — FAIL |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, refreshed) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.222 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **3** / max share **0.0963** (MODIFY_PT) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3148** (96/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-09-28 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.8984** (274/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — FAIL |
| PC-2 sentence_coverage | **0.9374** (599/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — FAIL |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **38 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — FAIL |
| PC-5 compile_latency p99 | **0.224 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **3** / max share **0.0963** (MODIFY_PT) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3148** (96/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-09-28 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.8984** (274/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — FAIL |
| PC-2 sentence_coverage | **0.9374** (599/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — FAIL |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.224 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **3** / max share **0.0963** (MODIFY_PT) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.2885** (88/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-09-28 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.8984** (274/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — FAIL |
| PC-2 sentence_coverage | **0.9374** (599/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — FAIL |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.223 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **3** / max share **0.0963** (MODIFY_PT) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.2885** (88/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-09-28 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.8984** (274/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — FAIL |
| PC-2 sentence_coverage | **0.9374** (599/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — FAIL |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.223 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **3** / max share **0.0963** (MODIFY_PT) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.2885** (88/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-09-28 (round 7-B — R7-B no-grammar top-ups; round summary)

| Number | Value | Command | Notes |
|---|---|---|---|
| core test state after round 7-B | **1448 passed / 0 failed** (`MTG_bot/core`) | `python -m pytest MTG_bot/core -q` | 1434 → 1448 (batch +14 tests across 3 bucket test files; golden verify zero-diff) |
| PC-1 card coverage round delta | **262 → 274 / 305** (0.8590 → 0.8984) | `python tools/measure_grammar.py --set M21` | +12 full cards from the 13-sentence batch (Tavern Swindler carries 2 rows); prediction 274 HIT |
| PC-2 sentence coverage round delta | **586 → 599 / 639** (0.9171 → 0.9374) | same | **+13 = exactly the batch**, zero overshoot |
| residual unparsed queue | **53/53 → 40 shapes / 40 occ** | `python tools/dump_unparsed_queue.py --set M21` | −13 shapes / −13 occ, **0 new shapes** (set-diff regression check); `/tmp/opencode/r7b/queue_post_r7b.txt` |
| goldens re-baselined | **exactly 12 files** | `--refresh-goldens` + per-file audit vs `/tmp/golden_pre_r7b_2026-09-28/` | 293 byte-identical; 10 abilities-key, **2 keywords-key** (Baneslayer/Sporeweb KeywordOutcome rows fold into `card.keywords` — audit rule now "abilities/emblem/keywords payload only") |
| PC-6 orphans | **2 → 1** (PHASE_IN) | `python tools/measure_grammar.py --set M21` | FLIP_COIN consumed by `B5c-flip-cost` the round it became template-usable; standing 1 = executor-deferred |
| PC-8 targetable | **87 → 88 / 305** | same | +1 (Hunter's Edge s2 TARGET selector) |
| bucket pins after round 7-B | **unchanged** (B2a 59/3, B3 46/2, B4 38/9) | `python tools/gen_buckets.py` | R7-B modules (b2b/b5b/b5c) do not feed the partition; all 8 JSONs **byte-identical** (cmp vs `/tmp/opencode/phase1_buckets_pre_r7b/`); UNCOVERED prunes b5b 21→12, b5c 14→11, b2b 4→3 are test-pinned |
| pyright / ruff on 7 touched files | 0 errors / **delta 0** | `pyright <files>`; `ruff check --output-format=concise` vs HEAD copies | one self-introduced I001 fixed via `ruff --fix` in-session; 7 TRY004 residual = HEAD's pre-existing b5b helper pattern; `ruff format` clean |

NOTE: the two identical-header blocks below (dated 2026-09-28, PC-2 599/639) are **per-run tool
auto-appends**, newest first: post-refresh final (PC-4 0 refreshed), pre-refresh verify (PC-4 12
diffs — expected, drift reported not repaired). Full write-up:
`KNOWLEDGE/2026-09-28/07-grammar-round7b-results.md`.

## 2026-09-28 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.8984** (274/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — FAIL |
| PC-2 sentence_coverage | **0.9374** (599/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — FAIL |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, refreshed) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.223 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.0963** (MODIFY_PT) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.2885** (88/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-09-28 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.8984** (274/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — FAIL |
| PC-2 sentence_coverage | **0.9374** (599/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — FAIL |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **12 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — FAIL |
| PC-5 compile_latency p99 | **0.222 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.0963** (MODIFY_PT) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.2885** (88/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-09-28 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.8590** (262/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — FAIL |
| PC-2 sentence_coverage | **0.9171** (586/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — FAIL |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.217 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **2** / max share **0.0949** (MODIFY_PT) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.2852** (87/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-09-28 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.8590** (262/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — FAIL |
| PC-2 sentence_coverage | **0.9171** (586/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — FAIL |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.214 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **2** / max share **0.0949** (MODIFY_PT) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.2852** (87/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-09-28 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.8590** (262/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — FAIL |
| PC-2 sentence_coverage | **0.9171** (586/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — FAIL |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, refreshed) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.215 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **2** / max share **0.0949** (MODIFY_PT) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.2852** (87/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-09-28 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.8590** (262/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — FAIL |
| PC-2 sentence_coverage | **0.9171** (586/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — FAIL |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **25 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — FAIL |
| PC-5 compile_latency p99 | **0.214 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **2** / max share **0.0949** (MODIFY_PT) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.2852** (87/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-09-28 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.8590** (262/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — FAIL |
| PC-2 sentence_coverage | **0.9171** (586/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — FAIL |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **25 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — FAIL |
| PC-5 compile_latency p99 | **0.215 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **2** / max share **0.0949** (MODIFY_PT) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.2852** (87/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-09-28 (round 7 — R7-A anaphora batch; round summary)

| Number | Value | Command | Notes |
|---|---|---|---|
| core test state after round 7 | **1434 passed / 0 failed** (`MTG_bot/core`) | `python -m pytest MTG_bot/core -q` | 1333 → 1420 (grammar phase +87 `test_ability_tree_r8.py`/regression pins) → 1434 (batch +114 bucket tests incl. pyright-narrowing fixes) |
| PC-1 card coverage round delta | **241 → 262 / 305** (0.7902 → 0.8590) | `python tools/measure_grammar.py --set M21` | +21 full cards from the 29-row batch; prediction band 260–263 HIT |
| PC-2 sentence coverage round delta | **552 → 586 / 639** (0.8639 → 0.9171) | same | **+34 = exactly the batch**, zero overshoot |
| residual unparsed queue | **85/87 → 53 shapes / 53 occ** | `python tools/dump_unparsed_queue.py` | −34 occ / −32 shapes (two shapes carried 2 occ each); **0 new shapes** (set-diff regression check); `/tmp/queue_r7_post.txt` |
| goldens re-baselined | **exactly 25 files**, abilities-payload-only | `--refresh-goldens` + per-file audit vs `/tmp/golden_pre_r7_2026-09-28/` | 280 byte-identical; the one `emblem` key change is the Liliana emblem's `abilities` gaining "It gains haste." |
| PC-6 orphans | **2** (PHASE_IN, FLIP_COIN) | `python tools/measure_grammar.py --set M21` | FIGHT consumed by `B3-fights-target` + `B5c-then-it-fights` the round it was first template-usable |
| bucket pins after round 7 | B2a 59 patterns/3 unc, B3 46/2, B4 38/9 | `python tools/gen_buckets.py` | all 8 bucket JSONs **byte-identical** vs `/tmp/opencode/phase1_buckets_pre_r6/` (cmp) — pattern↔UNCOVERED swap preserved membership |
| pyright / ruff on 13 touched files | 0 errors / **ruff delta 0 (net −9)** | `pyright <files>`; `ruff check --output-format=concise` (default rules) vs HEAD worktree `/tmp/r7_wt` | HEAD {F401:5,I001:8,ISC004:3,TRY004:28,UP035:1,UP037:1} → {F401:3,I001:2,ISC004:1,TRY004:28,UP035:1,UP037:1}; `ruff format` clean |

NOTE: the four identical-header blocks above (dated 2026-09-28, PC-2 586/639) are **per-run tool
auto-appends**, newest first: post-format re-verify (PC-4 0), post-refresh verify (PC-4 0),
post-refresh run (PC-4 refreshed), pre-refresh verify (PC-4 25 diffs — expected, drift reported not
repaired). The tool's header label is fixed regardless of round (see PITFALLS 2026-09-28).
Full write-up: `KNOWLEDGE/2026-09-28/06-grammar-round7-batch-results.md`.

## 2026-09-28 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.7902** (241/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — FAIL |
| PC-2 sentence_coverage | **0.8639** (552/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — FAIL |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.196 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **6** / max share **0.1004** (MODIFY_PT) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.2820** (86/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-09-28 (round 6 — conditional statics + restriction semantics; round summary)

| Number | Value | Command | Notes |
|---|---|---|---|
| core test state after round 6 | **1333 passed / 0 failed** (`MTG_bot/core`) | `python -m pytest MTG_bot/core -q` | 1278 → 1320 (grammar +42 `test_ability_tree_r7.py`) → 1333 (batch +13 bucket tests) |
| PC-1 card coverage round delta | **231 → 241 / 305** (0.7574 → 0.7902) | `python tools/measure_grammar.py --set M21` | +10 full cards from 13 batch rows; prediction band 240–243 HIT |
| PC-2 sentence coverage round delta | **539 → 552 / 639** (0.8435 → 0.8639) | same | +13 = exactly the batch (all rows 1-occurrence) |
| residual unparsed queue | **98/100 → 85 shapes / 87 occ** | `python tools/dump_unparsed_queue.py` | all 13 batch sentences absent |
| goldens re-baselined | **exactly 13 files**, abilities-key-only | `--refresh-goldens` + per-file audit vs `/tmp/golden_pre_r6_2026-09-27/` | 292 byte-identical; grammar phase itself 0 diffs |
| PC-6 orphans | **2** (PHASE_IN, FLIP_COIN — owner-ratified) | `python tools/measure_grammar.py --set M21` | MANDATE_BLOCK consumed by `B4-must-block` same round it was added |

NOTE: the three identical-header blocks below ("T5 — Phase-1 grammar measurement harness", all dated
2026-09-28) are **per-run tool auto-appends**, newest first: post-refresh final (PC-4 0), mid-batch
verify (PC-4 13 diffs pre-rebaseline — expected), grammar-phase baseline (231/539, orphans 3 incl.
pre-use MANDATE_BLOCK). The tool's header label is fixed regardless of round (see PITFALLS 2026-09-28).

## 2026-09-28 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.7902** (241/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — FAIL |
| PC-2 sentence_coverage | **0.8639** (552/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — FAIL |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, refreshed) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.2 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **2** / max share **0.1004** (MODIFY_PT) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.2820** (86/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-09-28 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.7902** (241/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — FAIL |
| PC-2 sentence_coverage | **0.8639** (552/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — FAIL |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **13 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — FAIL |
| PC-5 compile_latency p99 | **0.195 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **2** / max share **0.1004** (MODIFY_PT) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.2820** (86/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-09-28 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.7574** (231/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — FAIL |
| PC-2 sentence_coverage | **0.8435** (539/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — FAIL |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.188 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **3** / max share **0.1034** (DRAW) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.2820** (86/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-09-27 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.7574** (231/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — FAIL |
| PC-2 sentence_coverage | **0.8435** (539/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — FAIL |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, refreshed) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.196 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **2** / max share **0.1034** (DRAW) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.2820** (86/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-09-25 (T5 — Phase-1 grammar measurement harness) — superseded by 2026-09-27 section (post-round-5-batch)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.7344** (224/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — FAIL |
| PC-2 sentence_coverage | **0.8310** (531/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — FAIL |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, refreshed) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.189 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **2** / max share **0.1050** (ADD_MANA) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.2820** (86/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-09-25 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.7344** (224/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — FAIL |
| PC-2 sentence_coverage | **0.8310** (531/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — FAIL |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, refreshed) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.191 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **2** / max share **0.1050** (ADD_MANA) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.2820** (86/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-09-25 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.7344** (224/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — FAIL |
| PC-2 sentence_coverage | **0.8310** (531/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — FAIL |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.18 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **2** / max share **0.1050** (ADD_MANA) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.2820** (86/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-09-25 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.7344** (224/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — FAIL |
| PC-2 sentence_coverage | **0.8310** (531/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — FAIL |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, refreshed) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.239 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **2** / max share **0.1050** (ADD_MANA) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.2820** (86/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-09-25 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.7344** (224/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — FAIL |
| PC-2 sentence_coverage | **0.8310** (531/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — FAIL |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **18 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — FAIL |
| PC-5 compile_latency p99 | **0.187 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **2** / max share **0.1050** (ADD_MANA) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.2820** (86/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-09-24 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.6885** (210/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — FAIL |
| PC-2 sentence_coverage | **0.8013** (512/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — FAIL |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, refreshed) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.225 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **2** / max share **0.1101** (ADD_MANA) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.2754** (84/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-09-24 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.6885** (210/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — FAIL |
| PC-2 sentence_coverage | **0.8013** (512/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — FAIL |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.183 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **2** / max share **0.1101** (ADD_MANA) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.2754** (84/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-09-24 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.6885** (210/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — FAIL |
| PC-2 sentence_coverage | **0.8013** (512/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — FAIL |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.168 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **2** / max share **0.1101** (ADD_MANA) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.2754** (84/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-09-24 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.6885** (210/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — FAIL |
| PC-2 sentence_coverage | **0.8013** (512/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — FAIL |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.177 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **2** / max share **0.1101** (ADD_MANA) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.2754** (84/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-09-24 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.6885** (210/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — FAIL |
| PC-2 sentence_coverage | **0.8013** (512/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — FAIL |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, refreshed) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.179 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **2** / max share **0.1101** (ADD_MANA) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.2754** (84/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-09-24 (T5 — Phase-1 grammar measurement harness) — superseded by the later same-day entry (final: PC-1 0.6885 / PC-2 0.8013)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.6689** (204/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — FAIL |
| PC-2 sentence_coverage | **0.7887** (504/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — FAIL |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.167 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **2** / max share **0.1111** (ADD_MANA) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.2689** (82/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-09-24 (T5 — Phase-1 grammar measurement harness) — superseded by the later same-day entry (final: PC-1 0.6885 / PC-2 0.8013)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.6689** (204/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — FAIL |
| PC-2 sentence_coverage | **0.7887** (504/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — FAIL |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, refreshed) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.172 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **2** / max share **0.1111** (ADD_MANA) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.2689** (82/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-09-24 (T5 — Phase-1 grammar measurement harness) — superseded by the later same-day entry (final: PC-1 0.6885 / PC-2 0.8013)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.6689** (204/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — FAIL |
| PC-2 sentence_coverage | **0.7887** (504/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — FAIL |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.175 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **2** / max share **0.1111** (ADD_MANA) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.2689** (82/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-09-24 (T5 — Phase-1 grammar measurement harness) — superseded by the later same-day entry (final: PC-1 0.6885 / PC-2 0.8013)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.6689** (204/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — FAIL |
| PC-2 sentence_coverage | **0.7887** (504/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — FAIL |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, refreshed) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.174 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **2** / max share **0.1111** (ADD_MANA) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.2689** (82/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-09-23 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.6492** (198/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — FAIL |
| PC-2 sentence_coverage | **0.7793** (498/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — FAIL |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.166 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.1129** (ADD_MANA) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.2689** (82/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-09-23 (round 3 — SpellAbility.effect optional + effect-less additional-cost carriers; see 2026-09-23/03)

| Number | Value | Command | Notes |
|---|---|---|---|
| core test state | **1039 passed / 0 failed** | `python -m pytest MTG_bot/core -q` | was 1038/1 pre-re-baseline (sole failure = stale golden baseline) |
| compiler + r3 test files | **104 passed** (89 + 15) | `python -m pytest MTG_bot/core/compiler/test_compiler.py MTG_bot/core/test_ability_tree_r3.py -q` | +6 vs 02-session's 83 compiler tests |
| golden content changes | **4 of 305** | `python tools/measure_grammar.py --refresh-goldens`; structural audit vs staged baseline | only the `abilities` key per file; pre-existing abilities byte-identical |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | after re-baseline — PASS |
| PC-1 / PC-2 | 0.6492 (198/305) / 0.7793 (498/639) | same | unchanged — coverage counts sentence matching (B5a already matched); the carrier changes assembly only |
| pinned pre-r3 fingerprints | 4 (hex values in 03) | `MTG_bot/core/test_ability_tree_r3.py::_PINNED` | byte-stable across the `Effect \| None` change |
| new effect-less fingerprints | 3 (hex values in 03) | same (`_NEW_PINS`) | round-trip verified; `to_dict` omits `"effect"`, keeps `"additional_costs"` |

## 2026-09-23 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.6492** (198/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — FAIL |
| PC-2 sentence_coverage | **0.7793** (498/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — FAIL |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.164 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.1129** (ADD_MANA) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.2689** (82/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-09-23 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.6492** (198/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — FAIL |
| PC-2 sentence_coverage | **0.7793** (498/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — FAIL |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, refreshed) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.166 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.1129** (ADD_MANA) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.2689** (82/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-09-23 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.6361** (194/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — FAIL |
| PC-2 sentence_coverage | **0.7731** (494/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — FAIL |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.161 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.1129** (ADD_MANA) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.2689** (82/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-09-23 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.6361** (194/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — FAIL |
| PC-2 sentence_coverage | **0.7731** (494/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — FAIL |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.164 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.1129** (ADD_MANA) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.2689** (82/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-09-23 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.6361** (194/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — FAIL |
| PC-2 sentence_coverage | **0.7731** (494/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — FAIL |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, refreshed) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.194 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.1129** (ADD_MANA) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.2689** (82/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-09-23 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.6328** (193/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — FAIL |
| PC-2 sentence_coverage | **0.7715** (493/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — FAIL |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.163 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.1129** (ADD_MANA) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.2689** (82/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-09-23 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.6328** (193/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — FAIL |
| PC-2 sentence_coverage | **0.7715** (493/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — FAIL |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, refreshed) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.201 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.1129** (ADD_MANA) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.2689** (82/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-09-23 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.6328** (193/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — FAIL |
| PC-2 sentence_coverage | **0.7715** (493/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — FAIL |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.162 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.1129** (ADD_MANA) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.2689** (82/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-09-23 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.6328** (193/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — FAIL |
| PC-2 sentence_coverage | **0.7715** (493/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — FAIL |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.167 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.1129** (ADD_MANA) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.2689** (82/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-09-22 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.6328** (193/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — FAIL |
| PC-2 sentence_coverage | **0.7715** (493/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — FAIL |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.167 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.1129** (ADD_MANA) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.2689** (82/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-09-22 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.6098** (186/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — FAIL |
| PC-2 sentence_coverage | **0.7606** (486/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — FAIL |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.165 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.1137** (ADD_MANA) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.2689** (82/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-09-22 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.6066** (185/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — FAIL |
| PC-2 sentence_coverage | **0.7590** (485/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — FAIL |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.167 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.1140** (ADD_MANA) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.2689** (82/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-09-22 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.5869** (179/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — FAIL |
| PC-2 sentence_coverage | **0.7480** (478/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — FAIL |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.205 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.1159** (ADD_MANA) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.2689** (82/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-09-22 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.5770** (176/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — FAIL |
| PC-2 sentence_coverage | **0.7433** (475/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — FAIL |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.163 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.1168** (ADD_MANA) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.2689** (82/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-09-21 (B2b round 2 — 20-shape expansion via T3 grammar)

| Number | Value | Command | Notes |
|---|---|---|---|
| B2b bucket test state | **73 passed / 0 failed** | `python -m pytest MTG_bot/core/compiler/test_templates_b2b.py -q` | pins 62 shapes / 76 occ / **38 covered shapes / 52 matched occ / 24 UNCOVERED** / 36 TEMPLATES / 38 EXPECTED rows; PC-3 zero ambiguity incl. one negative `ValueError` pin (`+2/+2` counter unbuildable) |
| B2b coverage partition | 62 shapes / 76 occ, **38 covered / 52 matched**, **24 uncovered / 24 unmatched** | `python -m pytest MTG_bot/core/compiler/test_templates_b2b.py -q -k "test_covered_shape_and_occurrence_counts or test_uncovered_shapes_are_exactly_the_unmatched_shapes"` | **supersedes** the 2026-09-18 partition (18/32/44); ground truth: `/tmp/opencode/phase1_buckets/B2b.json` (unchanged) |
| B2b pyright state | **0 errors / 0 warnings / 0 informations** | `pyright MTG_bot/core/compiler/templates_b2b.py MTG_bot/core/compiler/test_templates_b2b.py` | |
| B2b ruff format state | **2 files already formatted** | `ruff format --check MTG_bot/core/compiler/templates_b2b.py MTG_bot/core/compiler/test_templates_b2b.py` | `ruff check`: 21 ISC004 in `templates_b2b.py` — same pre-existing house style as `templates_b2a.py` (14); not a gate violation per PITFALLS 2026-09-19 interpretation |
| core suite after B2b round 2 | **899 passed / 0 failed** (`MTG_bot/core`) | `python -m pytest MTG_bot/core -q` | **833** (2026-09-19 post-T3) + **33** (B2b 40→73) + **33** (unrecorded post-baseline growth: b2a 61→73, b5a 53→64, b4 34→42, b5b 54→56 — per-file `--collect-only`; see 2026-09-21/01 §reconciliation) |

## 2026-09-19 (T3 round 1 — grammar additions A–N)

| Number | Value | Command | Notes |
|---|---|---|---|
| core suite after T3 round 1 | **833 passed / 0 failed** (`MTG_bot/core`) | `python -m pytest MTG_bot/core -q` | 724 (pre-T3) + **109** new (`MTG_bot/core/test_ability_tree_t3.py`) |
| T3 test file state | **109 passed / 0 failed** | `python -m pytest MTG_bot/core/test_ability_tree_t3.py -q` | 14 pinned pre-T3 fingerprints + omit-key walker · 45 round-trip catalogue entries (A–N) · 41 rejection cases (≥2 per construct) · verb-role/FAtom-rule pins · omit present/absent · fingerprint sensitivity · walk |
| pinned fingerprint stability | **14/14 byte-identical** pre- vs post-T3 | `test_ability_tree_t3.py::test_pinned_pre_t3_fingerprint` (parametrized) | captures pre-change canonical-JSON SHAs; also asserts no T3 omittable key appears in any pre-T3 tree's `to_dict` |
| pyright (both files) | **0 errors / 0 warnings / 0 informations** | `/home/sune/.local/bin/pyright MTG_bot/core/ability_tree.py MTG_bot/core/test_ability_tree_t3.py` | |
| ruff format (both files) | **1 file already formatted ×2** | `ruff format --check MTG_bot/core/ability_tree.py MTG_bot/core/test_ability_tree_t3.py` | |
| ruff check (test file) | **All checks passed** | `ruff check MTG_bot/core/test_ability_tree_t3.py` | `SLF001` is NOT in the resolved ruleset — `# noqa: SLF001` trips RUF100 (unused noqa); see PITFALLS 2026-09-19 |
| ruff check (ability_tree.py) | **50 pre-existing-style findings** (46 TRY004 + 2 F541 + 1 SIM114 + 1 RUF100) | `ruff check MTG_bot/core/ability_tree.py` | HEAD had 40 (36 TRY004 + same others) — delta is +10 TRY004 from new `__post_init__` type checks, same `ValueError` convention the pinned tests assert; full repo ruff-clean is unachievable without breaking the pinned ValueError API (see PITFALLS) |
| full-repo suite | 860 passed / **23 pre-existing failed** | `python -m pytest MTG_bot -q` | identical 23-failure set as 2026-09-17 (rule_engine + strategic_brain + test_full_system); verified unrelated: zero failing module imports `ability_tree`, and the failures reproduce with `ability_tree.py` stashed to HEAD |
| grammar vocabulary after T3 | Verb **38** (35+CAST/PAY/LOSE_GAME) · FAtomPred **29** (26+POWER_LE/POWER_GE/NAME_CONTAINS) · EventSpec **16** (13+CardDrawn/LifeGained/Sacrifice) · Ability **9** (+CostModifier/EtBState/EmblemAbility) · CostDelta **5** | `len(...)` on the closed enums/unions | |

## 2026-09-19 (B5b bucket module + test)

| Number | Value | Command | Notes |
|---|---|---|---|
| B5b bucket test state | **54 passed / 0 failed** | `.venv/bin/python -m pytest MTG_bot/core/compiler/test_templates_b5b.py -q` | new file; pins 90 shapes / 112 occ / 91 concrete sentences / 40 covered rows (39 shapes, 35 tids) / 51 UNCOVERED; PC-3 zero ambiguity; PC-4 canonical stable |
| B5b pyright state | **0 errors / 0 warnings / 0 informations** | `pyright MTG_bot/core/compiler/templates_b5b.py MTG_bot/core/compiler/test_templates_b5b.py` | |
| core suite after B5b | **724 passed / 0 failed** (`MTG_bot/core`) | `.venv/bin/python -m pytest MTG_bot/core -q` | **611** (2026-09-18 post-B2b) + **54** (B5b) + **59** (B5c — landed after 2026-09-18, never recorded in NUMBERS before; verified via `pytest MTG_bot/core/compiler/test_templates_b5c.py --collect-only`) |

## 2026-09-18 (B2b bucket module + test)

| Number | Value | Command | Notes |
|---|---|---|---|
| B2b bucket test state | **40 passed / 0 failed** | `python -m pytest MTG_bot/core/compiler/test_templates_b2b.py -q` | pins 62 shapes / 76 occ / 18 covered shapes / 32 matched occ / 44 UNCOVERED; covered concrete sentences are single-match |
| B2b coverage partition | 62 shapes / 76 occ, **18 covered / 32 matched**, **44 uncovered / 44 unmatched** | `python -m pytest MTG_bot/core/compiler/test_templates_b2b.py -q -k "test_bucket_file_has_62_shapes_and_76_occurrences or test_covered_shape_and_occurrence_counts or test_uncovered_shapes_are_exactly_the_unmatched_shapes"` | ground truth: `/tmp/opencode/phase1_buckets/B2b.json` |
| B2b pyright state | **0 errors / 0 warnings / 0 informations** | `/home/sune/.local/bin/pyright MTG_bot/core/compiler/test_templates_b2b.py MTG_bot/core/compiler/templates_b2b.py` | |
| B2b ruff format state | **2 files left unchanged** | `ruff format MTG_bot/core/compiler/test_templates_b2b.py MTG_bot/core/compiler/templates_b2b.py` | |
| core suite after B2b test | **611 passed / 0 failed** (`MTG_bot/core`) | `python -m pytest MTG_bot/core -q` | 571 (2026-09-17 B2a baseline) + 40 |

## 2026-09-17 (session 8 — B2a bucket test)

| Number | Value | Command | Notes |
|---|---|---|---|
| B2a bucket test state | **61 passed / 0 failed** | `python -m pytest MTG_bot/core/compiler/test_templates_b2a.py -q` | new file; pins 62 shapes / 66 occ / 45 covered / 49 matched / 17 UNCOVERED; all 45 sentences single-match |
| B2a pyright state | **0 errors / 0 warnings** | `pyright MTG_bot/core/compiler/test_templates_b2a.py` | |
| core suite after B2a test | **571 passed / 0 failed** | `python -m pytest MTG_bot/core -q` | 510 (session 7 baseline) + 61 |
| full-repo suite | 598 passed / **23 pre-existing failed** (537/23 with the new file removed — identical set) | `python -m pytest -q` | failures only in `rule_engine` + `strategic_brain` + `test_full_system` (e.g. `test_engine.py::test_cast_creature` StopIteration — no legal land-play move generated); zero in `core` |
| B2a `_PRIORITY` | **50** (B2a/B5a) vs 100 (B1/B3/B4) | read `templates_b2a.py` line 94 | spec stated 100 — documented mismatch, pinned by `test_priority_is_50_not_100`, not changed |

## 2026-09-17 (session 7 — bucket work-input regeneration)

| Number | Value | Command | Notes |
|---|---|---|---|
| core test state after regeneration | **510 passed / 0 failed** (`MTG_bot/core`) | `python -m pytest MTG_bot/core -q` | restores 2026-09-16 stop baseline after /tmp wipe; B5a JSON cross-check now runs (was 2 skipped) |
| bucket shape/occurrence table | B1 15/49 · B2a 62/66 · B2b 62/76 · B3 48/55 · B4 47/63 · B5a 90/118 · B5b 90/112 · B5c 90/100 (total 504/639) | `python tools/gen_buckets.py` | total occurrences 639 = pool-level sentence baseline (pinned by test_ingest.py); see 2026-09-17/01-bucket-regeneration.md |

## 2026-09-16 (session 6 — template bucket wave; session STOP at owner's request)

| Number | Value | Command | Notes |
|---|---|---|---|
| core test state at stop | **510 passed / 0 failed** (`MTG_bot/core`) | `python -m pytest MTG_bot/core -q` | +144 vs session 5 (366): b1 (31), b3 (26), b4 (34), b5a (53) suites |
| bucket coverage at stop | B1 15/15 · B2a 45/45 decl.-covered (17 UNCOVERED) · B3 41/48 · B4 18/47 (29 UNCOVERED) · B5a 38 covered + 23 pre-consumed (29 UNCOVERED, in test docstring) | per-bucket parametrized tests + /tmp probe | 5 of 8 bucket modules landed; **B2b, B5b, B5c missing**; B2a test file missing |
| UNCOVERED shapes so far | **~62** (B2a 17 + B3 7 + B4 29 + B5a 29, dedup not yet applied across buckets) | `/tmp/opencode/phase1_buckets/UNCOVERED_ALL.md` | ranked families for the grammar-addition decision: see 2026-09-16/01-handoff-continuation.md §2 T3 |
| templates shipped | **135** (15 + 45 + 23 + 18 + 34) | grep `Template(` per module | PC-6 vocabulary health (orphan verbs) measurable once harness lands (T5) |

## 2026-09-15 (session 5 — ability_tree grammar review fixes: player referents, Quantity count, duration role)

| Number | Value | Command | Notes |
|---|---|---|---|
| core test state | **366 passed / 0 failed** (`MTG_bot/core`) | `python -m pytest MTG_bot/core -q` | +8 vs session 4 (358): 7 new round-trip catalog entries (Selector-target-player, FAtom-CONTROLLER_IS-target-player, FAtom-CMC_LE-dynamic-count, Atom-TAP/UNTAP/MANDATE_ATTACK-duration, auto Zone-PLAYER) + 1 validation case (CONTROLLER_IS with ALL_OPPONENTS rejected) |
| pyright ability tree | **0 errors, 0 warnings** | `/home/sune/.local/bin/pyright MTG_bot/core/ability_tree.py MTG_bot/core/test_ability_tree.py` | IDE-LSP "Import pytest could not be resolved" is environmental (no venv context); CLI pyright resolves it — see 2026-09-15/03-grammar-review-fixes.md |

## 2026-09-15 (session 4 — compiler steps 2/3: template registry + card/pool compile)

| Number | Value | Command | Notes |
|---|---|---|---|
| core test state | **358 passed / 0 failed** (`MTG_bot/core`) | `python -m pytest MTG_bot/core -q` | +70 vs session 3 (288): `templates.py`/`compiler.py` suites (template registry, mana-cost/P-T parsing, continuations, meta-filters, assembly, emblem attachment, engine-support, M21 smoke) |
| pyright compiler package | **0 errors, 0 warnings** | `/home/sune/.local/bin/pyright MTG_bot/core/compiler/compiler.py MTG_bot/core/compiler/templates.py MTG_bot/core/compiler/test_compiler.py MTG_bot/core/compiler/test_templates.py` | union narrowing via explicit `isinstance` helpers (see PITFALLS) |
| M21 emblem attachment | **3 emblems, 0 orphans, 3 attached** | `pytest MTG_bot/core -q` (`TestM21Smoke.test_emblems_attached`) | requires two-pass `compile_pool` (see PITFALLS) |
| M21 star P/T | Weird + Kinetic Augur → `star P/T` known gap, P/T stay `None`, no exception | same (`test_star_pt_cards_report_gap_not_exception`) | gap, not corruption |
| M21 summary consistency | total = **302** (305 − 3 emblems), fully+partially = total, unparsed > 0, known_gap ≥ 2 | same (`test_summary_consistency`) | compiled with empty registry, so unparsed = all text; this is the instrument's null-test baseline |

## 2026-09-15 (session 3 — ingest review fixes: split, validation, dedup)

### Re-measured M21 sentence baselines
| Number | Value | Command | Notes |
|---|---|---|---|
| file-level sentences | **927 total, 503 unique** | `python -m pytest MTG_bot/core -q` (`TestSmokeRealM21Pool.test_file_level_baselines`) | 397 card records, 391 with text; paren-depth-aware `split_sentences`; **supersedes** 952/509 |
| pool-level sentences | **639 total, 510 unique** | same (`TestSmokeRealM21Pool.test_pool_entries_and_keying`) | 305 oracle-keyed entries, 291 with text; **supersedes** 655/516 |
| delta from old flat split | **25 sentence boundaries** inside parentheses no longer split | inline probe comparing `re.compile(r'(?<=[.?!])\s+\|\n')` with `split_sentences` | 23 card records changed; 0 token records changed |
| affected card records | **23 of 397** | same | 5 Temple cards ×2 printings (5→4 each); Speaker of the Heavens ×2 (4→3); Discontinuity ×2 (5→3 each); Mazemind Tome ×2 (6→5); Opt, Riddleform, Spined Megalodon, Wall of Runes, Alchemist's Gift, Malefic Scythe, Short Sword ×1 each (−1 sentence) |
| emblems | **3** with owners | same | `56c1893f…fcdb`: Liliana, Waker of the Dead; `8a908da7…5d36`: Garruk, Unleashed; `ab67e4ec…5c1`: Basri Ket + Soldier |
| pool layouts | normal 285 / token 17 / emblem 3 | same | no record is both token and emblem |
| pool keywords / mana value | 24 distinct, **119 total** / 0:44, 1:30, 2:63, 3:68, 4:43, 5+:57 | same | unchanged by split/dedup fixes |
| core test state | **288 passed / 0 failed** (`MTG_bot/core`) | `python -m pytest MTG_bot/core -q` | includes new split, validation, dedup, emblem, and real-pool tests |

## 2026-09-15 (session 2 — compiler step 1: structured ingest)

### M21 pool reality: reprint duplicates (see 2026-09-15/01-ingest-dedup-decision.md)
| Number | Value | Command | Notes |
|---|---|---|---|
| duplicate oracle ids in card records | **112 of 397** (0 conflicting) | inline probe grouping `data.cards` by `scryfallOracleId`; pinned by `pytest MTG_bot/core/compiler -q` | every duplicate structurally identical, only `number`/`uuid` differ |
| oracle-id-keyed pool entries | **305** (285 cards + 20 tokens) | `ingest_pool` post-dedup; pinned by `TestSmokeRealM21Pool` | file still has 397+20 records; "the pool" as a key space is 305 |
| pool with text | **291** | same | |
| pool sentences | **655 total, 516 unique** | same | file-level was 952/509 over the 397 records; **superseded by session 3** (639/510 pool, 927/503 file) |
| pool layouts | normal 285 / token 17 / emblem 3 | same | |
| pool keywords | 24 distinct, **119 total** | `pool_stats` | file-level total was 166 (dupes counted twice) |
| pool mana value | 0:44, 1:30, 2:63, 3:68, 4:43, 5+:57 | `pool_stats` | |
| **correction**: no-text card records | 6, all **creatures** (Staunch Shieldmate, Wishcoin Crab, Walking Corpse, Onakke Ogre, Garruk's Gorehorn ×2) | inspect `text` field | **supersedes** 2026-09-14 "6 blank = basic lands" — basic lands here have reminder text `({T}: Add {W}.)` |
| core test state | **80 passed** (`MTG_bot/core`), 34 in `MTG_bot/core/compiler` | `pytest MTG_bot/core -q` | 46 pre-existing + 34 new ingest tests |

## 2026-09-14 (session 1, evening)

### Baseline test state
| Number | Value | Command | Notes |
|---|---|---|---|
| core (Phase 0) tests | **46 passed / 0 failed** | `pytest MTG_bot/core -q` | Phase 0 (identity/state/errors) green |
| full suite | **72 passed / 24 failed / 2 xfailed** | `pytest MTG_bot -q` | all 24 failures in legacy `rule_engine` (16) + `strategic_brain` (8); expected — legacy is attic'd at cutover, not fixed |
| failure cluster | 8 of 24 in rule_engine around zone/keyword bookkeeping (StopIteration, KeyError 'effects'/'zone_id') | same | confirms ARCHITECTURE.md verdict; do not chase in legacy code |

### Card pool (M21.json — the Phase 1 compilation target)
| Number | Value | Command | Notes |
|---|---|---|---|
| cards / tokens | **397 / 20** | `python3 -c json.load('MTG_bot/data/M21.json')['data']` | all 397+20 carry `identifiers.scryfallOracleId` |
| cards with oracle text | **391/397** (6 blank = basic lands) | inspect `text` field | field is **`text`**, NOT `oracleText` (see PITFALLS) |
| oracle sentences | **952 total, 509 unique, 486 unique shapes** (numbers→N, mana→C) | sentence split on `(?<=[.?!])\s+\|\n` | **superseded by 2026-09-15 session 3** for M21 sentence counts (927/503 under paren-depth-aware split); shape count not re-measured |
| trigger-shaped sentences | **189 total, 124 unique** (`When/Whenever/At start/As ~ enters`) | regex `^(When\|Whenever\|At (the )?(start\|beginning)\|As ~\|When ~ )` | |
| keywords | **24 distinct, 166 total** (Flying 28, Scry 19, Vigilance 12, Lifelink 12, Flash 11, Enchant 11, Trample 9, Prowess 8, Reach 8, Hexproof 7, Protection 6, Mill 5, Defender 4, Haste 4, Fight 4) | counter over `keywords` | |
| mana cost strings | **79 distinct**, incl. X costs (`{X}{R}{R}`, `{X}{G}`) | counter over `manaCost` | Quantity-as-expression is mandatory (DESIGN_CARD_POOL: no `*`, real expressions) |
| loyalty cards | 29 planeswalkers | counter over `loyalty` | loyalty = ability, not P/T |
| P/T cards | 194 | counter | |
| subtypes (top) | Human 49, Cleric 16, Wizard 13, Dog 12, Aura 11, Elemental 11, Teferi 10, Rogue 9 | counter over `subtypes` | Filter vocabulary must cover these |

### Phase 1 targets (pre-registered, see 02-phase1-plan.md)
PC-1 parse coverage ≥ 90% of pool cards fully compiled (stretch 95%) · PC-2 sentence coverage ≥ 95% ·
PC-3 ambiguity 0 · PC-4 golden stability 0 diffs · PC-5 compile p99 < 50 ms · PC-6 vocabulary health
(no orphan verb; no verb > 20% of atoms) · PC-7 executor: all top-25 frequent verbs have executors,
≥ 70% of cards fully executable · PC-8 targetable_card_fraction (EC-7): true value, expect big jump
from legacy 7/397 · PC-9 determinism: identical fingerprints across runs · PC-10 instrument null test.

### Environment
Python 3.12.3 (repo .venv), torch 2.14.0+cu130 importable, 20 cores, ~10 GB RAM headroom
(121 GB total, vLLM pool resident — keep 5-10 GB buffer; max 2 concurrent subagents, serialize below 5 GB).

### Round-11-A semantic fixes (2026-09-29, uncommitted; cmd: measure_pool + full pytest, see KNOWLEDGE/2026-09-29/04 §ROUND-11-A RESULTS)
PC-1 301/305 · PC-2 634/639 (0.992175) · PC-3 0 — all EXACTLY unchanged vs pre-fix baseline.
Golden re-baseline: 27/305 files changed, `abilities` key only (18 predicted + 9 R11-1 fallout).
Full suite: 23 failed / 1748 passed / 1 deselected / 2 xfailed — identical failure set to clean HEAD (23 pre-existing).

### Round-11-B ETB-subject sweep (2026-09-29, uncommitted; cmd: measure_pool + write/verify_goldens + full pytest, see KNOWLEDGE/2026-09-29/04 §ROUND-11-B RESULTS)
PC-1 301/305 · PC-2 634/639 (0.992175) · PC-3 0 — EXACT pre- and post-refresh (IR-content-only fix).
ETB triggers with subject=None: 62 → 0 (41 construction sites: 40 templates class A + 1 compiler built-in; class B/C offenders 0).
Golden re-baseline: 62/305 files changed, `abilities` key only in all 62; PC-4 62 diffs → 0 after refresh.
Core suite 1724 passed (1721 + 3 new guard tests in test_etb_subject_guard.py, allow-list empty).
Repo-wide 23 failed / 1751 passed — failure set byte-identical to clean HEAD a24d03e.

### Round-12b trigger binding (2026-09-29, uncommitted; see KNOWLEDGE/2026-09-29/07-round12b-trigger-binding.md)
Core suite **1788 passed / 0 failed** = 1772 (12a HEAD 2a2c96f) + **16 new** binding tests — cmd: `python -m pytest MTG_bot/core -q`.
New: `executor/events.py` EventJournal (8 kinds, C18 dies was-snapshot) + `executor/binding.py` TriggerBinder (APNAP = frozen order_key seat-first; MAX_TRIGGER_FIRES=200 → RuntimeError; unsupported event kinds raise at BIND). pyright 0; ruff delta 0 (new files clean).

### Round-12c legality + query surface (2026-09-29, uncommitted; see KNOWLEDGE/2026-09-29/08-round12c-legality-query.md)
Full suite **1864 passed / 23 failed** = 1815 (12b HEAD f08e490) + **49 new** (24 legality + 25 query); 23 == HEAD failure set byte-identical (strategic_brain/full_system legacy) — cmd: `python -m pytest MTG_bot -q` + stash baseline diff.
New: `executor/legality.py` (ability_playable gates CR 602.3/C20/condition/CR 117.3 costs; mana fold W-U-B-R-G-C keys; CR 119.4 life floor — pay-to-exactly-0 LEGAL; pay_costs through journalled verbs; folded activate) + `executor/query.py` (legal_activations / legal_targets+validate / choose_options / optional_offer / ONE_OF-REST rest_of — §5.5 Handle-sort, C17 two zeros pinned, C15 completeness). pyright 0 errors (5 scope files); ruff new files 0, __init__ delta 0 (21==21).

### Round-12d durations + layers + replacements (2026-09-29, uncommitted; see KNOWLEDGE/2026-09-29/09-round12d-durations-layers.md)
Core suite **1876 passed / 0 failed** = 1837 (12c HEAD 3c443f7) + **39 new** (22 durations + 16 layers + 1 Choose-in-verbs pin) — cmd: `.venv/bin/python -m pytest MTG_bot/core -q`.
`SUPPORTED_VERBS_V1` 21 → **24** (GRANT_ABILITY/LOSE_ABILITY/PREVENT_EFFECT live; DRAW stays out). pyright 0 errors scope (executor pkg + 3 test files, == HEAD 0); ruff repo 815 → **776** (all touched files ≤ HEAD; durations_min & verbs → 0). Compiled-card pins: Frost Breath (b5b+b5c Seq(TAP,PREVENT)) freeze = exactly ONE untap tick; Nine Lives (b5b+b2a) prevent+counter chain, 9th-counter exile trigger, detach ends protection.

### Round-13b spell stack + cast feed (2026-09-29, uncommitted; see KNOWLEDGE/2026-09-29/12-round13b-spell-stack.md)
Core suite **1948 passed / 0 failed** = 1906 (measured mid-session: all 13b executor edits, before the new test file) + **42 new** (`test_executor_stack.py`) — cmd: `.venv/bin/python -m pytest MTG_bot/core -q`.
PC-7 engine_supported **264 → 279/305** (SUPPORTED_VERBS_V2 30 → **35**: +PAY/CAST/CHOOSE/CHOOSE_NAME/MANA_POLICY) — cmd: `.venv/bin/python tools/measure_grammar.py --with-engine-flags`. Flip set EXACTLY +15 (probe: gated `compile_pool` at 35 vs 30 verbs): CAST×6 (Chandra Flame's Catalyst, Chandra Heart of Fire, Conspicuous Snoop, Furious Rise, Idol of Endurance, Radha Heart of Keld) + PAY×3 (Tolarian Kraken, Liliana's Devotee, Ghostly Pilferer) + MANA_POLICY×2 (Chromatic Orrery, Vodalian Arcanist) + CHOOSE×2 (Duress, Kitesail Freebooter) + CHOOSE_NAME×2 (Necromentia, Runed Halo). Cancel/Lofty Denial/Miscast/Rewind (COUNTER_SPELL raise STAYS) + Demonic Embrace (CAST+GRANT_TYPE) verified still unsupported.
Stack completeness: world fingerprint iterates PLAYER_ZONES (skips ZONE_STACK, state.py frozen) → `Executor.state_fingerprint` folds stack dump + land ledger + extra_land_plays + mana-segment dump + name_choices (pinned: same world, frame x=3 vs x=4 → different fingerprints). Loyalty CR 606.1b quirk fixed symmetric (both signs → `cost:loyalty:not_planeswalker`; 4 test pins amended with AMENDED notes). pyright 0 errors; ruff delta 0 (only pre-existing quantity.py 18 / selectors.py 12 remain).

### Round-13c permissions: emblems + grants + windows + land plays (2026-09-30, uncommitted; see KNOWLEDGE/2026-09-30/01-round13c-permissions.md)
Core suite **1971 passed / 0 failed** = 1948 (13b) + **23 new** (`test_executor_permissions.py`) — cmd: `.venv/bin/python -m pytest MTG_bot/core -q`.
PC-7 engine_supported **279 → 286/305** (SUPPORTED_VERBS_V2 35 → **39**: +GET_EMBLEM/GRANT_TYPE/GRANT_ACTIVATION/ADD_LAND_PLAY) — cmd: `.venv/bin/python tools/measure_grammar.py --with-engine-flags`. Flip set EXACTLY +7: Azusa Lost but Seeking (ADD_LAND_PLAY) + Basri Ket/Garruk Unleashed/Liliana Waker (GET_EMBLEM) + Demonic Embrace/Dub/Riddleform (GRANT_TYPE). Doc /11 projected +9→288; honest delta **+7** — Teferi stays double-flagged (its GRANT_ACTIVATION handler shipped but PHASE_OUT ships in 13d). PC-1..5/9/10 PASS, PC-4 EXACT (305 files 0 diffs); PC-6/PC-8 unchanged pre-existing FAILs. pyright 0 errors (executor pkg + 4 test files); ruff delta 0 (layers.py's 2 new findings fixed in place; quantity 18 / selectors 12 / `__init__` 4 identical to HEAD).

### Round-14a random-policy full-M21 games — PC-7 v1, the first GAME number (2026-09-30, uncommitted; see KNOWLEDGE/2026-09-30/03-game-loop-bugs.md)
Core suite **1986 passed / 0 failed** = 1971 (13c) + **15 new** (`test_executor_games.py`) — cmd: `.venv/bin/python -m pytest MTG_bot/core -q`.
**PC-7 v1 (game survival, 10 seeds, turn cap 60, deck-pairs-seed 1409)** — cmd: `.venv/bin/python -m MTG_bot.core.executor.games --seeds 10 --pool {all,engine,castable}`:
`all` 285 deckable → **0/10 survived**, mean 9.0 turns, max 44, 92 acts, 14 cards fired an ability (5.2% of 286);
`engine` 267 deckable → **1/10 survived (10%)**, mean 17.4, **max 60 = cap**, 229 acts, 21 fired (7.9% of 286);
`castable` 91 deckable (`playable_engine=91` vs 286 engine-supported = **B-1 the real ceiling**) → 0/10, mean 2.0, max 8, 9 fired (3.4%).
29/30 games ended in an exception. Kill census: **B-4 22/30** (`take_decision` "SCRY decision … not in ('top','bottom')" — the positional trigger-decision channel, P0 DESIGN, owner ruling requested); B-7 3/30 (CONTROLLER_COUNT_GE raises from the QUERY, Fabled Passage); B-9/B-11 3/30 (`result`/`event` referent + TARGET_PLAYER outside a trigger = the ETB-effect-split-across-abilities compiler bug, 3/3 confirmed: Kitesail Freebooter, Garruk's Harbinger, Siege Striker); B-2 1/30 pre-fix, 0 post-fix.
**3 executor fixes** (repro-first, tests green): F-1 `begin_turn` had NO turn draw (CR 504.5) → journalled `_TURN_DRAW` (1 existing test amended); F-2 `legality._zone_handles` Zone(STACK) raise was round-12-stale (13b grew a stack) → now answers (Unsubstantiate's BATTLEFIELD+STACK selector made `legal_casts` and `spell_target_slots` disagree); F-3 `_v_choose` dropped `ctx.bindings` when calling its own query → `verb_choose_options` gained an additive `bindings=` (Duress family now casts + the designated opponent discards).
PC-1 **301/305 (0.9869)**, PC-2 **634/639 (0.9922)**, PC-3 **0**, PC-4 **0 diffs / 305 files** — cmd: `.venv/bin/python tools/measure_grammar.py --set M21` — **EXACT through 11 consecutive phases**; grammar/goldens/state.py untouched. PC-6 (1 orphan) / PC-8 (0.3213) unchanged pre-existing FAILs. pyright **0 errors** (executor pkg + 2 test files); ruff delta **0** (games.py + test_executor_games.py clean on the ALL ruleset; `__init__` 4 == HEAD).

### Round-14b-2 decision-channel rebuild — PC-7 rerun (2026-09-30, uncommitted; see KNOWLEDGE/2026-09-30/05-round14b-2-decision-channel.md)

**PC-7 game survival (10 seeds, cap 60, deck-pairs 1409, post-B-4/B-5)** — cmd: `.venv/bin/python -m MTG_bot.core.executor.games --seeds 10 --pool {all,engine,castable}`:
survival all **1/10** mean 28.7 max 60 (was 0/10, 9.0, 44); engine **3/10** mean 38.8 max 60×3 (was 1/10, 17.4, 60); castable 0/10 mean 14.0 max 34 (was 0/10, 2.0, 8). coverage fired: all 34, engine 39, castable 33 cards. B-4 scry-rejection class gone from all pools; 30-seed trigger (engine ≥5/10) not met. Core suite **1996** (`pytest MTG_bot/core -q`), PC-1 301/305 · PC-2 634/639 · PC-3 0 · PC-4 0 diffs (`tools/measure_grammar.py`), engine_supported 286 pinned, pyright 0, ruff delta 0 (34=34).

### Round-14c six-class close-out (2026-09-30, uncommitted; see KNOWLEDGE/2026-09-30/06-round14c-six-classes.md)

**PC-7 v1.1 (14c)** — cmd: `.venv/bin/python -m MTG_bot.core.executor.games --seeds 10 --pool {all,engine,castable}` + `--seeds 30 --pool engine`:
10-seed: all **2/10** (was 1/10) mean 35.9 max 60 cov41; engine **6/10** (was 3/10) mean 46.2 max 60×4 cov44; castable 0/10 (was 0/10) mean 18.3 (was 14.0) cov39.
**Engine 30 seeds: 10/30 survived (33.3%), mean 34.9t, 2021 acts, 51 cards fired = 19.1% of engine_supported=286.**
Crash census 10-pools (22): B-7-family preds 13 (CONTROLLER_COUNT_GE 6, CAST_THIS_TURN_FROM 4, MOVED_TO_ZONE_THIS_TURN 6 — frames quantity.py:512), B-9 3, B-17 3, B-19 STACK-KeyError 2, FIGHT-no-handler 1. Classes FIXED this round: B-13, B-14/QX-at-cast, B-15, B-16, B-18; B-17 = design-level (golden miscompiles; frozen scope).
Core **2001** (`pytest MTG_bot/core -q`), PC-1 301/305 · PC-2 634/639 · PC-3 0 · PC-4 0 diffs (`tools/measure_grammar.py --set M21`) EXACT, pyright 0, ruff delta 0 (34=34 executor stats).

### Round-14d journal-pred family + B-19 — PC-7 v1.2 (2026-09-30, uncommitted; see KNOWLEDGE/2026-09-30/07-round14d-journal-preds.md)

**PC-7 game survival** — cmd: `.venv/bin/python -m MTG_bot.core.executor.games --seeds 10 --pool {all,engine,castable}` + `--seeds 30 --pool engine` (deck-pairs 1409, cap 60):
10-seed: all 2→**8/10** (mean 52.6, cov 46, 970 acts); engine 6→**7/10** (53.5, cov 46, 1045 acts); castable 0→**1/10** (30.6, cov 43, 907 acts).
**Engine 30 seeds: 10/30 → 18/30 (60.0%), mean 48.5t, 3004 acts, 60 cards fired = 22.5% of the 267 playable-engine (convention of 14c's 19.1%).**
Crash census 10-pools 22→11; engine30 11: B-7-family (13/22) + B-19 (2/22) GONE. Wall = B-9 `result`-referent-at-cast 8/11 (new face: Feat of Resistance) + B-17 FLIP_WON 2 (SCOPE-STOP, inventory in /07 + ledger) + POWER_GE/CMC_LE 3 + FIGHT 1.
Core **2007** (`pytest MTG_bot/core -q`), PC-1 301/305 · PC-2 634/639 · PC-3 0 · PC-4 0 diffs (`tools/measure_grammar.py --set M21`) EXACT — goldens untouched (B-17 STOP), pyright 0 (edited scope; repo 524→524), ruff delta 0, replay determinism green.

### Round-14e result-register + tail-capture + world-preds — PC-7 v1.3 (2026-09-30, uncommitted; see KNOWLEDGE/2026-09-30/08-round14e-result-register-and-tail-capture.md)

**PC-7 game survival** — cmd: `.venv/bin/python -m MTG_bot.core.executor.games --seeds 10 --pool {all,engine,castable}` + `--seeds 30 --pool engine` (deck-pairs 1409, cap 60):
10-seed: all 8→**9/10** (mean 55.1, cov 45, 1027 acts, 1 crash FIGHT); engine 7→**9/10** (59.9, cov 48, 1212 acts, **0 crashes** — first natural game-overs); castable 1→**5/10** (53.6, cov 57, 1637 acts, 3 crashes: EachPlayer×2 Goremand, KEYWORD_HAS×1 Run Afoul).
**Engine 30 seeds: 18/30 → 26/30 (86.7%), mean 58.6t, 3753 acts, 61 cards fired = 22.8% of the 267 dealt (playable_engine 88→86: Swindler+Hallowblade moved to B-1 by capture).**
Engine30 wall 11→3 crashes, ONE class: B-9 residual **Chandra, Heart of Fire #4** — the B4 permission row's `referent='result'` is a CROSS-resolution anaphora (fix = B4-template fidelity emitting `IS_EXILED_WITH_SOURCE`, golden-moving class, own audit — deliberately not forced). Engine pool is NOT flagged-verb/combat-bound: combat (arc-3) UNREACHED at mean 58.6/60t; flagged deaths live in `all` (FIGHT) and `castable` (12e EachPlayer node + KEYWORD_HAS pred — new census faces).
Closed this round: **B-9** producer register (SEARCH/CHOOSE + TAP/UNTAP/PUT_COUNTER/MOVE_ZONE write `ctx.bindings["result"]` per effect execution; unset read still loud); **B-17** activation-tail capture with the empty-cost OPT(CAST) permission idiom EXEMPTED as a transparent boundary (3 captures Swindler/Hallowblade/Waker, golden audit diff==inventory set-equal, keys={abilities}); **POWER_GE/CMC_LE** world/identity preds (token mv 0 = the QProp convention, QX-capable).
Core **2013** (`pytest MTG_bot/core -q`; +6 pins, 3 frozen AMENDED), PC-1 301/305 · PC-2 634/639 · PC-3 0 · PC-4 0 diffs (`tools/measure_grammar.py --set M21`) EXACT — goldens moved ONLY via the audited capture; engine_supported **286/305** EXACT; pyright 0 (edited scope; repo 524→524), ruff delta 0, replay determinism green.

### Round-14f final convergence — PC-7 v1 CONVERGED 96.7% (2026-09-30, uncommitted; see KNOWLEDGE/2026-09-30/09-round14-closeout-pc7-v1-converged.md)
`.venv/bin/python -m MTG_bot.core.executor.games --seeds 10 --pool {all,engine,castable}` + `--seeds 30 --pool engine` (deck-pairs 1409, cap 60): all 9/10 (55.1t, cov 43, 1010 acts, 1 crash = FIGHT, all-pool by construction); engine 9/10 (59.9t, cov 44, 1187 acts, **0 crashes**); castable 5→**8/10** (57.4t, cov 48, 1809 acts, **0 crashes**, 2 natural CR-121.3 draw-losses).
**Engine 30 seeds: 26/30 → 29/30 (96.7%), mean 60.0t, 3843 acts, cov 58 = 21.7%, 0 crashes** — the only non-survivor is a natural draw-from-empty LOSS (seed 0, turn 59). PC-7 v1 CONVERGED: the engine pool plays to the cap with zero exceptions; remaining wall = SCOPE (flagged-verb family 18 deckable, arc-3 combat UNREACHED, B-1 castability 192 non-land deckable without SpellAbility).
Closed this round: **B-9 fully** (Chandra #4 cross-resolution residual → B4-row fidelity emits `IS_EXILED_WITH_SOURCE` population, [+1]-row shape), **B-20 EachPlayer** (controller rotation, pool-cursor forwarding, documented CR 800.2 seat-order), **B-21 KEYWORD_HAS** (live `keyword_of` oracle, one branch all positions, bare-ctx loud), **B-22 static-anthem outlier** (Waker of Waves, family's lone raw-EffectOutcome row → StaticAbility; playable_engine 86→85, the 14e ruled precedent).
Core **2022** (`pytest MTG_bot/core -q`; +9 pins, 3 frozen AMENDED), PC-1 301/305 · PC-2 634/639 · PC-3 0 · PC-4 0 diffs EXACT, engine_supported **286/305 EXACT**; goldens moved ONLY via the two audited inventories (diff == {Chandra, Waker}, keys={abilities}); pyright 0 (edited scope; repo 524→524), ruff delta 0, replay determinism green; the three 14e crash seeds (castable 5/7/9, engine 23) replay crash-free to the cap.

### Round-16a marked damage + SBA + FIGHT — arc-3 breached (2026-09-30, uncommitted; see KNOWLEDGE/2026-09-30/12-round16a-marked-damage-sba-fight.md)

**Engine counts + survival** — cmd: `.venv/bin/python -m MTG_bot.core.executor.games --seeds {10,30} --pool engine --out …` (deck-pairs 1409, cap 60):
deckable 267→**269**, engine_supported 286→**288** (gained = exactly Brash Taunter + Primal Might, FIGHT dispatch — `_gated` flip pin), playable_engine 85→**86**.
engine10: 9/10 survived, mean 59.6t, 1277 acts, cov 40, **0 crashes**; two runs byte-identical except the `argv` echo (determinism holds).
**Engine 30 seeds: 29/30 (96.7%), mean 59.87t, 3917 acts, cov 53 = 19.7%, 0 crashes** — FIGHT fired in real games; the 14f "arc-3 combat UNREACHED" wall is breached with zero regression.
all10: crash set UNCHANGED — sole crash = `NotImplementedError: GAIN_CONTROL` (verbs.py:1316, seed 2, Enthralling Hold) = documented 16e boundary.
Validation packs: `.venv/bin/python tools/run_scenarios.py` → **3/3 PASS** (brash_echo, primal_might_fight, nonlethal_skirmish).
Trace catalog: pre-change compare 10/10 seeds diverging (first divergence ~entry 4, PLAY_LAND index shift = deal-shift cascade from deckable 267→269 at fixed deck-pairs seed 1409); `repin` → **5641 entries / 10 games** (was 5504); post-repin compare **0 diverging of 10**.
Core **2034** passed + 5 subtests (`pytest MTG_bot/core -q`, +12 `test_executor_damage_sba.py`), PC-1 301/305 · PC-2 634/639 · PC-3 0 · PC-4 0 EXACT (executor-only change, goldens never moved), pyright 0 (edited scope), ruff delta 0 (selectors.py keeps HEAD's 12 legacy errors).

## 2026-10-01 — Round 16b: COMBAT skeleton (BINDING /11)

Core **2054** passed + 5 subtests (`python -m pytest MTG_bot/core -q`; +20 `test_executor_combat.py`, pins amended: V2 41, engine 291, IS_ATTACKING answers/IS_BLOCKING raises, DeclareBlockers keeps raising).
Capability gate EXACT flips (`python -` with/without-MANDATE gated-compile diff): V2 **40→41**, engine **288→291** = {Furor of the Bitten, Pursued Whale, Pirate token}, deckable **271 unchanged**.
Validation packs `python tools/run_scenarios.py` → **9/9 PASS** (3×16a + 6 new combat: sickness+haste, vigilance+defender, double-strike split, ready-next-turn, Furor mandate+narrowing, Falconer attack trigger).
Engine 30 seeds `python -m MTG_bot.core.executor.games --seeds 30 --pool engine`: **0 crashes**, 28/30 survived (93.3%), **2 games END BY COMBAT** (seeds 19 t56, 24 t46; `combat_losses` field, counted apart from crashes); engine10 ⊂ this run; determinism double-run diff empty.
all10 `--pool all`: crash set UNCHANGED — sole crash GAIN_CONTROL (Enthralling Hold); 1 combat death.
Trace catalog: compare **10/10 diverge at the first COMBAT boundary**, all new outcomes clean non-crash → repin **6343 entries/10 games**, post-repin compare **0 of 10**.
PC-1..5,7,9,10 hold (PC-7 `--with-engine-flags`: **291/305, 41 verbs**); PC-6/PC-8 unchanged pre-existing FAILs — PC-8 stayed **0.3213** (its combat fraction needs 16c blockers, contrary to note 10's hope).
Pyright 0 on edited scope; ruff 0 on new files (legacy baseline untouched); replays `reports/replays/replay_s19.html`, `replay_s24.html` carry DECLARE/COMBAT_DAMAGE feeds.
Fixes that the IR forced (docs 13): CONTROLLER_IS player-handle branch; QProp THIS_WAY_COUNT tap-register; Whale mandate = TokenSpec static behind the token-registration gap (no dispatch carrier in M21); Falconer enters-tapped/attacking compiler DROP (Basri-only); compiled Historian 3/3.

## 2026-09-30 round-16c (CR 509 blockers + CR 510 assignment + Herald policy + token binder) — doc 14
| metric | value | command | note |
|---|---|---|---|
| core suite | **2076 passed + 4 subtests** | `.venv/bin/python -m pytest MTG_bot/core -q` | +22 in test_executor_blockers.py |
| validation packs | **16/16** (7 new) | `.venv/bin/python tools/run_scenarios.py` | blockers lanes + loyalty/activate ops |
| engine gate | **293/305** (V2 **43** verbs) | `tools/measure_grammar.py --with-engine-flags` | flip −2 verbs loses exactly {Canopy Stalker, Garruk, Savage Herald} |
| engine30 | survived **28/30 (93.3%)**, crash classes **0**, 3 combat deaths | `python -m MTG_bot.core.executor.games --seeds 30 --pool engine --out …` | mean 58.7t; double-run semantically byte-identical |
| all10 | 8/10, sole crash GAIN_CONTROL | `--seeds 10 --pool all` | baseline crash set unchanged |
| engine10 / castable10 | 9/10 / 8/10, 0 crash classes | `--seeds 10 --pool {engine,castable}` | |
| catalog | repin **6676 entries/10 games**, post **0/10 diverge** | `tools/traces/catalog.py repin && … compare` | pre-fix pin diverged on seed 2 entry 597 (blocker damage now lands → life-zero finish, located clean) |
| replay | seed 2 ×2 HTML **byte-identical** | `tools/make_replay.py --seed 2 --pool engine` | carries DECLARE_BLOCKERS + both-side COMBAT_DAMAGE |
| PC gates | PC-1 0.9869 · PC-2 0.9922 · PC-3 0 · PC-4 0 · PC-5 0.282ms PASS | `tools/measure_grammar.py --with-engine-flags` | PC-6 (1/0.0934), PC-8 0.3213 unchanged baseline FAILs |

## 2026-09-30 round-16e (GAIN_CONTROL overlay + ATTACH/aura lifecycle + close-out) — doc 15
| metric | value | command | note |
|---|---|---|---|
| core suite | **2079 passed + 4 subtests** | `.venv/bin/python -m pytest MTG_bot/core -q` | +3 `Round16eControlTest` (test_executor_games.py) |
| validation packs | **16/16** | `.venv/bin/python tools/run_scenarios.py` | `enchant` op rebuilt: journalled move + canonical `attach_aura` (setup CR 704.5q sweep buries battlefield-declared auras; expired layers NEVER revive from recompute — only fresh `attach_source` via journalled re-entry) |
| engine gate | **297/305** (V2 **45** verbs) | `tools/measure_grammar.py --with-engine-flags` | flip +{GAIN_CONTROL, ATTACH} gains EXACTLY {Malefic Scythe, Enthralling Hold, Traitorous Greed, Short Sword}, zero losses |
| engine30 | survived **26/30 (86.7%)**, crash classes **0** | `python -m MTG_bot.core.executor.games --seeds 30 --pool engine` | 4 non-survivors are REAL game-overs (combat/draw), counted apart |
| all10 | **9/10 (90.0%)**, crash classes **0** | `--seeds 10 --pool all` | the ALL10 GAIN_CONTROL baseline crash (Enthralling Hold) is GONE |
| catalog | repin **6138 entries/10 games**, post **0/10 diverge** | `tools/traces/catalog.py repin && … compare` | |
| replay | seed 2 ×2 HTML **byte-identical** (825 entries/120 actions) | `tools/make_replay.py --seed 2 --pool engine` | showcase `replay_s37`: Hold→Masticore takeover, host dies, aura UNATTACHED sweep (events 198/286/287) |
| PC gates | PC-1 301/305 · PC-2 0.9922 · PC-3 0 · PC-4 0 · PC-5 0.242ms · PC-9 stable · PC-10 exact PASS | `tools/measure_grammar.py --with-engine-flags` | PC-6 (1/0.0934), PC-8 0.3213 unchanged baseline FAILs |
| pyright / ruff | 0 on touched scope; ruff **Δ0** vs HEAD | — | 6 legacy errors in touched files pre-existing (earlier "5" was a miscount) |
| wave1 family (r17a) | **66 ETB cards**, 66/66 engine-supported, 66/66 with art (assets 321 files) | `tools/audit/wave_builder.py && … --lint` | 2026-09-30 |
| audit chain (r17a) | IR 66/66 **0 mismatch** · packs **21/21** (6 wave cards covered, 60 gaps) · seed-7 game **29/66** wave cards live | `tools/audit/verify_wave.py --replay --with-replay --seed 7 --max-verify 40` | 2026-09-30 |
| wave1b batch A (r17b) | validation packs **34/34** (13 new ETB packs green) · suspects **0/18 fail-only** in `tools/audit/suspects/` · core suite **2081 passed + 4 subtests** | `.venv/bin/python tools/run_scenarios.py` / `… --dir tools/audit/suspects` / `-m pytest MTG_bot/core -q` | engine FROZEN — 0 code changes; findings in KNOWLEDGE/2026-09-30/18-wave1b-findings.md §batch A |
| PC gate re-check (r17b) | engine gate **297/305** (45 verbs) · PC-8 **0.3213** · PC-9 stable · PC-10 exact — all unchanged | `tools/measure_grammar.py --with-engine-flags` | 2026-09-30, after batch A; reports/grammar_2026-09-30.json |
| wave1b batch B (r17b) | validation packs **55/55** full scenarios dir (21 new ETB/checkland packs green; batch B slice 21/21) · suspects **0/31 fail-only** (batch B slice 0/13) · core suite **2081 passed + 4 subtests** · PC-1 **0.9869** (301/305) · PC-2 **0.9922** (634/639) · PC-3 **0** · PC-4 **0 diffs** (305 files) | `.venv/bin/python tools/run_scenarios.py` / `… --dir tools/audit/suspects` / `-m pytest MTG_bot/core -q` / `tools/measure_grammar.py --set M21` | 2026-09-30; engine FROZEN — 0 code changes; findings §batch B (B-1…B-10: Zone(ANY), self-false IS_SOURCE-if, TARGET-no-designation ×5, TARGET_PLAYER, ZONE_COUNT_GE, QX, may-offer gate vs result register, scry-bottom no-op) |
| round 18a silent-semantic fixes | scenarios **63/63** (55 + 8 repatriated: lurker, houndmaster, firemaw, warsteed, uprising, scry, turret, wavecaster) · suspects **0/23 fail-only** · core **2096 + 4 subtests** (+15 new r18a pins, 4 AMENDED) · goldens **9 lines moved, keys {abilities}, PC-4 0 post-refresh** · PC-1 **301/305** PC-2 **634/639** PC-3 **0** · engine gate **297/305 · V2 45 UNCHANGED** · catalog repin **6138→6174, 0/10 diverge** · replay + determinism byte-clean · pyright 0 scope · ruff Δ0 | `.venv/bin/python tools/run_scenarios.py` / `--dir tools/audit/suspects` / `-m pytest MTG_bot/core -q` / `tools/measure_grammar.py --set M21 [--with-engine-flags]` / `tools/traces/catalog.py repin && … compare` | 2026-10-01; doc 19; MAY_DONE + optional_offer gate rules + CR 701.1 scry + CR 603.4 turret + uprising count=1 |
