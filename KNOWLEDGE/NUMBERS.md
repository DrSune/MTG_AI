# NUMBERS — dated measurement log

Latest entry first. Every row: date, number, producing command, notes. A number must have all three
to be admissible (METRICS.md rail: the instrument must be reproducible).

---

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
