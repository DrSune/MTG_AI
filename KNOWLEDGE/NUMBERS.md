# NUMBERS — dated measurement log

Latest entry first. Every row: date, number, producing command, notes. A number must have all three
to be admissible (METRICS.md rail: the instrument must be reproducible).

---

## 2026-10-24 (external review — benchmark core MTG_bot/bench, exploratory, M21 castable pool)

| Number | Value | Command | Notes |
|---|---|---|---|
| uniform vs pass, duplicate pair score | **0.995** [0.985, 1.0], 50 pairs (99 W, 1 cap draw) | `python -m MTG_bot.bench duel --a uniform --b pass --deals 50` | the floors are far apart: the instrument discriminates |
| pass vs pass pair score | **0.5000** exactly, all cap draws | `python -m MTG_bot.bench duel --a pass --b pass --deals 5 --turn-cap 20` | instrument null test |
| uniform vs RandomPolicy pair score | **0.4875** [0.40, 0.575], 40 pairs (39-41) | `python -m MTG_bot.bench duel --a uniform --b random-policy --deals 40` | hand-weighted RandomPolicy indistinguishable from uniform at this n |
| track R items | **312** of 428 packs; 0 reader mismatches | `python -m MTG_bot.bench rules --answerer oracle` | excluded: 58 unmappable ability index, 44 opaque decision words, 6 no lane, 5 order/trample, 3 expect-raise |
| track R null answerer | **0.274** [0.245, 0.305] all keys; **0.0** changed keys | `python -m MTG_bot.bench rules --answerer null` | §17: all-keys is null-favourable; changed-keys is the headline |
| primer exercised share | **0.9992** (174/178 components; 5,967 uses) | `python -m MTG_bot.bench primer --json` | NOT verified coverage (needs mutation testing); gaps COPY x2, GRANT_ACTIVATION, EXTRA_TURN, DISCARD |
| router stress | **0 crashes, 0 misroutes** in 50 uniform-vs-uniform games (M21+ZNR, strict routing) | ad hoc (see commit daf9bd0) | after the B-34 mana-classification fix; before it, 2/12 games crashed |

## 2026-10-20 (ZNR — T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.3830** (108/282) | `python tools/measure_grammar.py --set ZNR` | target >= 0.90 / stretch >= 0.95 — FAIL |
| PC-2 sentence_coverage | **0.5496** (399/726) | `python tools/measure_grammar.py --set ZNR` | target >= 0.95 / stretch >= 0.98 — FAIL |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set ZNR` | target 0 — PASS |
| PC-4 golden_stability | **N/A** (no golden trees for set ZNR) | `python tools/measure_grammar.py --set ZNR` | target 0 — N/A (not evaluated) |
| PC-5 compile_latency p99 | **0.317 ms/card** (3 runs) | `python tools/measure_grammar.py --set ZNR` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **26** / max share **0.1547** (MODIFY_PT) | `python tools/measure_grammar.py --set ZNR` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set ZNR` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.1560** (44/282) | `python tools/measure_grammar.py --set ZNR` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set ZNR` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set ZNR` | synthetic in-memory cards — PASS |


## 2026-10-20 (M21 — T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **1.0000** (305/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **1.0000** (639/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.332 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **4** / max share **0.1265** (MOVE_ZONE) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-10-19 (M21 — T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **1.0000** (305/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **1.0000** (639/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.326 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **4** / max share **0.1265** (MOVE_ZONE) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-10-19 (ZNR — T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.3830** (108/282) | `python tools/measure_grammar.py --set ZNR` | target >= 0.90 / stretch >= 0.95 — FAIL |
| PC-2 sentence_coverage | **0.5496** (399/726) | `python tools/measure_grammar.py --set ZNR` | target >= 0.95 / stretch >= 0.98 — FAIL |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set ZNR` | target 0 — PASS |
| PC-4 golden_stability | **N/A** (no golden trees for set ZNR) | `python tools/measure_grammar.py --set ZNR` | target 0 — N/A (not evaluated) |
| PC-5 compile_latency p99 | **0.308 ms/card** (3 runs) | `python tools/measure_grammar.py --set ZNR` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **26** / max share **0.1547** (MODIFY_PT) | `python tools/measure_grammar.py --set ZNR` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set ZNR` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.1560** (44/282) | `python tools/measure_grammar.py --set ZNR` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set ZNR` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set ZNR` | synthetic in-memory cards — PASS |


## 2026-10-18 (ZNR — T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.2411** (68/282) | `python tools/measure_grammar.py --set ZNR` | target >= 0.90 / stretch >= 0.95 — FAIL |
| PC-2 sentence_coverage | **0.4669** (339/726) | `python tools/measure_grammar.py --set ZNR` | target >= 0.95 / stretch >= 0.98 — FAIL |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set ZNR` | target 0 — PASS |
| PC-4 golden_stability | **N/A** (no golden trees for set ZNR) | `python tools/measure_grammar.py --set ZNR` | target 0 — N/A (not evaluated) |
| PC-5 compile_latency p99 | **0.278 ms/card** (3 runs) | `python tools/measure_grammar.py --set ZNR` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **30** / max share **0.1667** (ADD_MANA) | `python tools/measure_grammar.py --set ZNR` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set ZNR` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.1028** (29/282) | `python tools/measure_grammar.py --set ZNR` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set ZNR` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set ZNR` | synthetic in-memory cards — PASS |


## 2026-10-18 (M21 — T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **1.0000** (305/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **1.0000** (639/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.343 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **4** / max share **0.1265** (MOVE_ZONE) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-10-18 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **1.0000** (305/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **1.0000** (639/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.315 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **4** / max share **0.1265** (MOVE_ZONE) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-10-18 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **1.0000** (305/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **1.0000** (639/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.302 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **4** / max share **0.1265** (MOVE_ZONE) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-10-18 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.1879** (53/282) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — FAIL |
| PC-2 sentence_coverage | **0.3416** (248/726) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — FAIL |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **N/A** (no golden trees for set ZNR) | `python tools/measure_grammar.py --set M21` | target 0 — N/A (not evaluated) |
| PC-5 compile_latency p99 | **0.215 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **30** / max share **0.2062** (ADD_MANA) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.0745** (21/282) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-10-18 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **1.0000** (305/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **1.0000** (639/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.293 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **4** / max share **0.1265** (MOVE_ZONE) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-10-18 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.1879** (53/282) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — FAIL |
| PC-2 sentence_coverage | **0.3457** (251/726) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — FAIL |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **N/A** (no golden trees for set ZNR) | `python tools/measure_grammar.py --set M21` | target 0 — N/A (not evaluated) |
| PC-5 compile_latency p99 | **0.225 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **30** / max share **0.2000** (ADD_MANA) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.0816** (23/282) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-10-18 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.1879** (53/282) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — FAIL |
| PC-2 sentence_coverage | **0.3457** (251/726) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — FAIL |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **N/A** (no golden trees for set ZNR) | `python tools/measure_grammar.py --set M21` | target 0 — N/A (not evaluated) |
| PC-5 compile_latency p99 | **0.221 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **30** / max share **0.2000** (ADD_MANA) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.0816** (23/282) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-10-18 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **1.0000** (305/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **1.0000** (639/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.292 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **4** / max share **0.1265** (MOVE_ZONE) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-10-18 (un-askable audit — KNOWLEDGE/2026-10-18/97)

| Number | Value | Command | Notes |
|---|---|---|---|
| eval-side un-askable items | **0/58** (all askable, dynamic) | `python tools/eval/unaskable_audit.py --out tools/eval/unaskable_audit.json` | 44 packs replayed, 0 fail, 0 gold drift; /24 named backlog all live |
| corpus fail-registered residue | **11/199** (may 6/choose 3/name 1/target 1) | same | all train-side; true-no-decision 7, null-degenerate 3, semantics-gap 1 |

---

## 2026-10-18 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.1879** (53/282) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — FAIL |
| PC-2 sentence_coverage | **0.3457** (251/726) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — FAIL |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **N/A** (no golden trees for set ZNR) | `python tools/measure_grammar.py --set M21` | target 0 — N/A (not evaluated) |
| PC-5 compile_latency p99 | **0.223 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **30** / max share **0.2000** (ADD_MANA) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.0816** (23/282) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-10-18 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.1879** (53/282) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — FAIL |
| PC-2 sentence_coverage | **0.3457** (251/726) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — FAIL |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **N/A** (no golden trees for set ZNR) | `python tools/measure_grammar.py --set M21` | target 0 — N/A (not evaluated) |
| PC-5 compile_latency p99 | **0.242 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **30** / max share **0.2000** (ADD_MANA) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.0816** (23/282) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-10-18 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **1.0000** (305/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **1.0000** (639/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.314 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **4** / max share **0.1265** (MOVE_ZONE) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-10-18 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.1879** (53/282) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — FAIL |
| PC-2 sentence_coverage | **0.3457** (251/726) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — FAIL |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **N/A** (no golden trees for set ZNR) | `python tools/measure_grammar.py --set M21` | target 0 — N/A (not evaluated) |
| PC-5 compile_latency p99 | **0.231 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **30** / max share **0.2000** (ADD_MANA) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.0816** (23/282) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-10-18 (blindspot (a) closure — KNOWLEDGE/2026-10-18/96)

| Number | Value | Command | Notes |
|---|---|---|---|
| ZNR sentence denominator (front+back) | **726** (655+71, 36 faces) | `python tools/measure_grammar.py --set ZNR` | PC-2 honest |
| ZNR PC-2 sentence_coverage | **0.253444** (184/726) | `python tools/measure_grammar.py --set ZNR` | was 0.2809 (184/655) optimistic |
| ZNR BFACE register rows / distinct shapes | **71 / 8** | `python tools/measure_grammar.py --set ZNR` | bucket_hint "BFACE", name "<card> [face B]" |
| M21 report after back-face census | **content byte-identical** (timestamp+PC-5 exempt), no `backface` key | `python tools/measure_grammar.py --set M21` | OMIT-IF-EMPTY holds |


## 2026-10-18 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.1418** (40/282) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — FAIL |
| PC-2 sentence_coverage | **0.2534** (184/726) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — FAIL |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **N/A** (no golden trees for set ZNR) | `python tools/measure_grammar.py --set M21` | target 0 — N/A (not evaluated) |
| PC-5 compile_latency p99 | **0.213 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **33** / max share **0.2597** (ADD_MANA) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.0603** (17/282) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-10-18 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **1.0000** (305/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **1.0000** (639/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.308 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **4** / max share **0.1265** (MOVE_ZONE) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-10-18 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **1.0000** (305/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **1.0000** (639/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.349 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **4** / max share **0.1265** (MOVE_ZONE) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-10-18 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **1.0000** (305/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **1.0000** (639/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.331 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **4** / max share **0.1265** (MOVE_ZONE) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-10-18 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.1418** (40/282) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — FAIL |
| PC-2 sentence_coverage | **0.2809** (184/655) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — FAIL |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **N/A** (no golden trees for set ZNR) | `python tools/measure_grammar.py --set M21` | target 0 — N/A (not evaluated) |
| PC-5 compile_latency p99 | **0.212 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **33** / max share **0.2597** (ADD_MANA) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.0603** (17/282) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-10-18 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **1.0000** (305/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **1.0000** (639/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.289 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **4** / max share **0.1265** (MOVE_ZONE) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-10-18 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **1.0000** (305/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **1.0000** (639/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.333 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **4** / max share **0.1265** (MOVE_ZONE) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-10-18 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **1.0000** (305/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **1.0000** (639/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.327 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **4** / max share **0.1265** (MOVE_ZONE) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-10-18 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **1.0000** (305/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **1.0000** (639/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.327 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **4** / max share **0.1265** (MOVE_ZONE) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-10-10 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **1.0000** (305/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **1.0000** (639/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, refreshed) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.327 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **4** / max share **0.1265** (MOVE_ZONE) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-10-10 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **1.0000** (305/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **1.0000** (639/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, refreshed) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.334 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **4** / max share **0.1265** (MOVE_ZONE) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-10-07 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.9934** (303/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **0.9969** (637/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, refreshed) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.29 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **4** / max share **0.1276** (MOVE_ZONE) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-10-05 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.9934** (303/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **0.9969** (637/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.292 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.0931** (DRAW) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-10-05 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.9934** (303/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **0.9969** (637/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.303 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.0931** (DRAW) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-10-05 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.9934** (303/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **0.9969** (637/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.25 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.0931** (DRAW) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |
| PC-7 engine_supported_cards | **301/305** (0.9869) | `python tools/measure_grammar.py --with-engine-flags` | T6 executor dispatch over 46 verbs (SUPPORTED_VERBS_V2) — honest flag, not a target |


## 2026-10-05 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.9934** (303/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **0.9969** (637/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.247 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.0931** (DRAW) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |
| PC-7 engine_supported_cards | **301/305** (0.9869) | `python tools/measure_grammar.py --with-engine-flags` | T6 executor dispatch over 46 verbs (SUPPORTED_VERBS_V2) — honest flag, not a target |


## 2026-10-05 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.9934** (303/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **0.9969** (637/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.296 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.0931** (DRAW) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |
| PC-7 engine_supported_cards | **297/305** (0.9738) | `python tools/measure_grammar.py --with-engine-flags` | T6 executor dispatch over 45 verbs (SUPPORTED_VERBS_V2) — honest flag, not a target |


## 2026-10-05 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.9934** (303/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **0.9969** (637/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, refreshed) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.292 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.0931** (DRAW) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-10-05 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.9934** (303/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **0.9969** (637/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.241 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.0931** (DRAW) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |
| PC-7 engine_supported_cards | **297/305** (0.9738) | `python tools/measure_grammar.py --with-engine-flags` | T6 executor dispatch over 45 verbs (SUPPORTED_VERBS_V2) — honest flag, not a target |


## 2026-10-05 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.9934** (303/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **0.9969** (637/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, refreshed) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.244 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.0931** (DRAW) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-10-05 (B5 — BUGCATCH campaign metrics PC-11..PC-14)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-11 residue @ BCS>=20 | **1 (0 ungated)** | `python tools/audit/measure_bugcatch.py` | 66 cards at/above T; 65 in packs/suspects; deferred-by-rule: Sublime Epiphany — PASS (GATED) |
| PC-12 branch litness | **0.3814** (37/97 LIT; 13 DARK) | `python tools/audit/measure_bugcatch.py` | target >= 0.90 — FAIL (report-only); 6 DARK on BCS>=T cards |
| PC-13 pair coverage | **0.2820** (2419/8577) | `python tools/audit/measure_bugcatch.py` | 7 collision classes; 0 zero-tested classes; report-only until B4 splices land |
| PC-14 anomalies | **0** over catalog lane(s) | `python tools/audit/measure_bugcatch.py` | D1–D6; target 0 — PASS (GATED) |


## 2026-10-05 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.9934** (303/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **0.9969** (637/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.249 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.0931** (DRAW) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-10-05 (B5 — BUGCATCH campaign metrics PC-11..PC-14)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-11 residue @ BCS>=20 | **1 (0 ungated)** | `python tools/audit/measure_bugcatch.py` | 66 cards at/above T; 65 in packs/suspects; deferred-by-rule: Sublime Epiphany — PASS (GATED) |
| PC-12 branch litness | **0.3814** (37/97 LIT; 13 DARK) | `python tools/audit/measure_bugcatch.py` | target >= 0.90 — FAIL (report-only); 6 DARK on BCS>=T cards |
| PC-13 pair coverage | **0.2820** (2419/8577) | `python tools/audit/measure_bugcatch.py` | 7 collision classes; 0 zero-tested classes; report-only until B4 splices land |
| PC-14 anomalies | **0** over catalog lane(s) | `python tools/audit/measure_bugcatch.py` | D1–D6; target 0 — PASS (GATED) |


## 2026-10-05 (HUNT H4 — suspect fixes + `ONE_OF`/`REST` partition journaling; HEAD `10d53c6`, uncommitted)

| Item | Number | Command | Note |
|---|---|---|---|
| scenario packs | **336/336 green** | `.venv/bin/python tools/run_scenarios.py --dir tools/scenarios` | Gadrak × Malefic Scythe now uses the new additive historical `damage_received` lane while preserving the live `damage` ledger law. |
| suspect packs | **2/3 green** | `.venv/bin/python tools/run_scenarios.py --dir tools/audit/suspects` | Basri × Siege Striker and Garruk’s Harbinger are green; Malefic Scythe × Wildwood Scourge remains red-as-intended for the H3 EtB counters/P/T-layer bug. |
| core suite | **2354 passed + 3 subtests** | `.venv/bin/python -m pytest MTG_bot/core -q --no-header -rf` | Includes `MTG_bot/core/test_executor_h4.py` partition-journal pins. |
| audit suite | **62 passed** | `.venv/bin/python -m pytest tools/audit -q --no-header -rf` | Includes mode-aware `ONE_OF`/`REST` branch matcher tests. |
| grammar | **PC-1 303/305 · PC-2 637/639 · PC-3 0 · PC-4 0 · PC-5 0.295 ms/card · PC-9 stable · PC-10 pass** | `.venv/bin/python tools/measure_grammar.py` | Δ0 vs `reports/grammar_2026-10-04.json` except PC-5 timing noise. PC-6 and PC-8 remain standing FAILs. |
| catalog | **0/10 diverging seeds after attribution** | `.venv/bin/python tools/traces/catalog.py compare` | First compare showed seed 5 only: partition audit-row insertion at entries 201+, game length 225→230, outcome unchanged. Catalog repinned after attribution. |
| random games | **0 crash classes**, endings **47/53**, mean **33.52** turns | `.venv/bin/python -m MTG_bot.core.executor.games --seeds 100 --pool all --deck-pairs-seed 1409 --turns 60` | Report `reports/games_2026-10-04.json` modified by the games tool. |
| branch coverage | **97 branches: 37 LIT / 13 DARK / 47 UNMATCHABLE** | `.venv/bin/python tools/audit/branch_coverage.py --quiet` | Nine branches moved `DARK -> LIT` with the new scenario corpus and mode-aware partition evidence. |
| pair coverage | **8577 candidate pairs: 2419 tested / 6158 untested**, **33** designed packs | `.venv/bin/python tools/audit/pair_coverage.py --quiet` | No collision class has zero tested coverage. |
| lints | pyright **0 new**, ruff **Δ0** on touched files | `pyright` + `ruff check` on touched Python files | `tools/run_scenarios.py` retains six pre-existing `Counter` type errors and one pre-existing `BLE001`. |

## 2026-10-05 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.9934** (303/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **0.9969** (637/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.295 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.0931** (DRAW) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-10-04 (BUGCATCH B4a correction + B4b pair coverage — tools-only, no engine/scenario edits; supersedes membership/heat portions of the B4a section below)

| Item | Number | Command | Note |
|---|---|---|---|
| corrected branch coverage | **97 branches: 28 LIT / 22 DARK / 47 UNMATCHABLE** | `.venv/bin/python tools/audit/branch_coverage.py --quiet` | Heat now uses §E calibration: DARK × BCS × collision-class weight × anomaly hits. Branch totals remain unchanged. Artifact `tools/audit/branch_coverage.json`. |
| disk membership | **in_pack 267→276, in_suspect 22→0, flags changed 22** | `.venv/bin/python tools/audit/membership.py --t 20 --write` | Derived recursively from printed names in `"real"` card values under `tools/scenarios/` and `tools/audit/suspects/`; handles never confer membership. |
| PC-11 residue | **1 at T=20 — `Sublime Epiphany`** | `.venv/bin/python tools/audit/membership.py --t 20 --write` | 66 cards at or above BCS 20; 65 covered; stale suspect flags are fully covered by green packs. |
| heat card rollup | **Garruk's Harbinger 96, Chandra, Heart of Fire 74, Chandra, Flame's Catalyst 68** | `.venv/bin/python tools/audit/branch_coverage.py --quiet` | Card heat = dark branch count × mean branch heat. |
| B4b pair matrix | **8577 candidate pairs: 2399 tested / 6178 untested; 13 designed; 0 classes with zero tested coverage** | `.venv/bin/python tools/audit/pair_coverage.py --quiet` | Per-class coverage 22.68–31.24%; top untested pair `Basri Ket + Siege Striker`, heat 3710.0. Artifact `tools/audit/pair_coverage.json`. |
| gates | tools/audit **60 passed**, core **2350 passed + 3 subtests**, pyright **0 errors / 0 warnings / 0 informations**, ruff **0 findings** | `.venv/bin/pytest tools/audit -q`; `.venv/bin/pytest MTG_bot/core -q`; `pyright tools/audit/b4_journal.py tools/audit/branch_coverage.py tools/audit/membership.py tools/audit/pair_coverage.py tools/audit/test_branch_coverage.py tools/audit/test_pair_coverage.py`; `ruff check tools/audit/b4_journal.py tools/audit/branch_coverage.py tools/audit/membership.py tools/audit/pair_coverage.py tools/audit/test_branch_coverage.py tools/audit/test_pair_coverage.py` | Final tool state; no commits, no engine or `run_scenarios.py` edits. |

---

## 2026-10-04 (BUGCATCH batch B4a — branch coverage over journal evidence; tools-only, no engine/scenario edits)

| Item | Number | Command | Note |
|---|---|---|---|
| branch coverage | **97 branches: 28 LIT / 22 DARK / 47 UNMATCHABLE** | `.venv/bin/python tools/audit/branch_coverage.py` | Evidence lanes: 304 green pack journals + 20 corpus replays (`--pool all`, deck-pair seed 1409, 60 turns). Artifact `tools/audit/branch_coverage.json`. |
| precedent sanity | Fabled Passage conditional **OK**; Life Goes On died precedent **NOT-DECLARED** | `.venv/bin/python tools/audit/branch_coverage.py` | B1 declares 0 Life Goes On branches; attributed LIFE_GAINED evidence is present in the lanes. |
| CAST attribution | **8 verb-CAST branches remain DARK** | `python3 - <<PY` matcher inspection + production JSON | 13b `KIND_CAST` row lacks a source-permanent field; own casting is excluded as the may-cast side. Future positive controls need attributable world-diff rows or a new cast-source journal contract. |
| tests | **14 new branch matcher tests**, `tools/audit` **48 passed**, core **2350 passed + 3 subtests** | `.venv/bin/pytest tools/audit/test_branch_coverage.py -q`; `.venv/bin/pytest tools/audit -q`; `.venv/bin/pytest MTG_bot/core -q` | Synthetic hermetic matcher pins; no engine behavior change. |
| lints | pyright **0 errors, 0 warnings, 0 informations**; ruff **0 findings** | `pyright tools/audit/b4_journal.py tools/audit/branch_coverage.py tools/audit/test_branch_coverage.py`; `ruff check tools/audit/b4_journal.py tools/audit/branch_coverage.py tools/audit/test_branch_coverage.py` | Final tool state. |

---

## 2026-10-04 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.9934** (303/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **0.9969** (637/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.247 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.0931** (DRAW) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-10-04 (BUGCATCH batch B1 — BCS instrument + branch inventory; tools-only, HEAD 8b4506e)

| Item | Number | Command | Note |
|---|---|---|---|
| BCS | 305 cards, mean **14.1**, max **70** (Basri Ket); buckets 0:24 / 1–9:89 / 10–29:161 / 30+:31 | `python3 tools/audit/bcs.py` | 9 IR primitives, integer weights {1,3,2,6,3,5,2,4,3} = documented silent-semantic ledger-bug counts; artifact `tools/audit/bcs.json` |
| calib | silent-semantic gate **19/27** pass (≥2 of p4–p9); vanilla-identity **14/14** all-zero | `python3 tools/audit/bcs.py` | 8 exceptions all risk-prims=1, classified score **blind spots** (branch-entanglement / keyword×consumer / replacement×ordering / single-fold) per design §C — weights NOT curve-fit; machinery (3) + crash-only (10) excluded by class |
| branches | **97 declared** on 74 cards (Cond 16, Choose 27, Optional 41, EachPlayer 5, Selector ONE_OF/REST 8); lit-so-far **deferred to B3** | `python3 tools/audit/bcs.py` | each branch = ID + falsifiable signature (journal_kind × data_predicate); branch serialiser fields documented (EachPlayer uses `effect`, not `inner`) |
| suite | **2345 passed + 3 subtests, 0 failed** — unchanged | `.venv/bin/python -m pytest MTG_bot/core -q` | tools-only batch, no engine edits, no commits |
| lints | pyright **0 errors** · ruff **Δ0** on `tools/audit/bcs.py` | `pyright tools/audit/bcs.py` / `ruff check tools/audit/bcs.py` | new file 0 findings; `datetime.now(UTC)` convention matched |

## 2026-10-04 (grammar batch B6 — OPPONENT_OF destination predicate + CREATE_TOKEN controller role; last 2 suspects closed per /10 ruling)

| Item | Number | Command | Note |
|---|---|---|---|
| scenarios | **304/304 passed** (302→304); suspects 2→**0** — folder EMPTY | `tools/run_scenarios.py` | promoted chandras_pyreling_opponent_filter + secure_the_scene (MOVE+strip; strip law corrected: `mana` is functional per-seat input, only `finding`/`status` stripped); FAIL-at-HEAD signatures proven pre-promotion |
| suite | **2345 passed + 3 subtests, 0 failed** (was 2322+3; +23) | `.venv/bin/python -m pytest MTG_bot/core -q` | +12 test_ability_tree_r12 (rules tables, legality both carriers, rejection lanes) + 11 test_executor_r25 (player/card/referent eval lanes, fire/no-fire discriminators incl. card-subject + self-damage, controller-role mint + no-role regression); b2b/b5b template tests amended with filter + controller-role pins |
| grammar | PC-1 303/305 · PC-2 637/639 · PC-3 0 · PC-4 **0 (305 refreshed → 305 verified)** · engine 297/305 (45 verbs) · PC-5 0.293 ms · PC-9 stable — **ALL Δ0** vs 24a | `tools/measure_grammar.py --set M21 --refresh-goldens --with-engine-flags` | goldens moved **exactly 4** (C1-form: only `abilities` key — Pyreling+Incinerator trigger filter empty-FAnd → FAtom(OPPONENT_OF,YOU); STS+AA additive controller-role pair); PC-6/PC-8 standing FAILs byte-identical; two 2026-10-04 T5 sections above = refresh+verify auto-appends of this run |
| catalog | **0/10 diverge — NO repin** | `tools/traces/catalog.py compare` | new predicate + referent-selector never fire on the 10 trace seeds |
| games | **0 crash classes**, 100 decisive 47/53, mean_turns **33.48** (vs 48/52 / 33.49) | `.venv/bin/python -m MTG_bot.core.executor.games --seeds 100 --pool all --deck-pairs-seed 1409 --turns 60` | one outcome flipped — EXPECTED: empty trigger filter removed, Incinerator self-damage landfall loop now dead |
| lints | ruff **Δ0** (path-scoped stash in-repo baseline: 8 tracked files identical 65-finding multiset at HEAD; 2 new files 0 findings after 1×I001 fix) · pyright **0 errors 0 warnings** on all 10 touched files | `ruff check --output-format=concise` per file / `pyright --outputjson` | no repo ruff/pyright config exists — defaults everywhere; in-repo stash is the reliable Δ0 baseline, not /tmp copies |

## 2026-10-04 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.9934** (303/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **0.9969** (637/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, refreshed) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.293 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.0931** (DRAW) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |
| PC-7 engine_supported_cards | **297/305** (0.9738) | `python tools/measure_grammar.py --with-engine-flags` | T6 executor dispatch over 45 verbs (SUPPORTED_VERBS_V2) — honest flag, not a target |


## 2026-10-04 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.9934** (303/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **0.9969** (637/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.287 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.0931** (DRAW) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |
| PC-7 engine_supported_cards | **297/305** (0.9738) | `python tools/measure_grammar.py --with-engine-flags` | T6 executor dispatch over 45 verbs (SUPPORTED_VERBS_V2) — honest flag, not a target |


## 2026-10-02 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.9934** (303/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **0.9969** (637/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.244 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.0931** (DRAW) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |
| PC-7 engine_supported_cards | **297/305** (0.9738) | `python tools/measure_grammar.py --with-engine-flags` | T6 executor dispatch over 45 verbs (SUPPORTED_VERBS_V2) — honest flag, not a target |


## 2026-10-02 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.9934** (303/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **0.9969** (637/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.244 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.0931** (DRAW) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |
| PC-7 engine_supported_cards | **297/305** (0.9738) | `python tools/measure_grammar.py --with-engine-flags` | T6 executor dispatch over 45 verbs (SUPPORTED_VERBS_V2) — honest flag, not a target |


## 2026-10-02 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.9934** (303/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **0.9969** (637/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.244 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.0931** (DRAW) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-10-02 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.9934** (303/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **0.9969** (637/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.247 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.0931** (DRAW) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |
| PC-7 engine_supported_cards | **297/305** (0.9738) | `python tools/measure_grammar.py --with-engine-flags` | T6 executor dispatch over 45 verbs (SUPPORTED_VERBS_V2) — honest flag, not a target |


## 2026-10-02 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.9934** (303/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **0.9969** (637/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, refreshed) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.247 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.0931** (DRAW) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-10-02 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.9934** (303/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **0.9969** (637/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.249 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.0929** (DRAW) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |
| PC-7 engine_supported_cards | **297/305** (0.9738) | `python tools/measure_grammar.py --with-engine-flags` | T6 executor dispatch over 45 verbs (SUPPORTED_VERBS_V2) — honest flag, not a target |


## 2026-10-02 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.9934** (303/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **0.9969** (637/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.242 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.0929** (DRAW) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |


## 2026-10-02 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.9934** (303/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **0.9969** (637/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, refreshed) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.248 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.0929** (DRAW) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |
| PC-7 engine_supported_cards | **297/305** (0.9738) | `python tools/measure_grammar.py --with-engine-flags` | T6 executor dispatch over 45 verbs (SUPPORTED_VERBS_V2) — honest flag, not a target |


## 2026-10-02 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.9934** (303/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **0.9969** (637/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.244 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.0929** (DRAW) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |
| PC-7 engine_supported_cards | **297/305** (0.9738) | `python tools/measure_grammar.py --with-engine-flags` | T6 executor dispatch over 45 verbs (SUPPORTED_VERBS_V2) — honest flag, not a target |


## 2026-10-02 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.9869** (301/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **0.9922** (634/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, refreshed) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.244 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.0934** (DRAW) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |
| PC-7 engine_supported_cards | **297/305** (0.9738) | `python tools/measure_grammar.py --with-engine-flags` | T6 executor dispatch over 45 verbs (SUPPORTED_VERBS_V2) — honest flag, not a target |


## 2026-10-02 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.9869** (301/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **0.9922** (634/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.263 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.0934** (DRAW) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |
| PC-7 engine_supported_cards | **297/305** (0.9738) | `python tools/measure_grammar.py --with-engine-flags` | T6 executor dispatch over 45 verbs (SUPPORTED_VERBS_V2) — honest flag, not a target |


## 2026-10-02 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.9869** (301/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **0.9922** (634/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, refreshed) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.242 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.0934** (DRAW) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |
| PC-7 engine_supported_cards | **297/305** (0.9738) | `python tools/measure_grammar.py --with-engine-flags` | T6 executor dispatch over 45 verbs (SUPPORTED_VERBS_V2) — honest flag, not a target |


## 2026-10-02 (T5 — Phase-1 grammar measurement harness)

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
| PC-7 engine_supported_cards | **297/305** (0.9738) | `python tools/measure_grammar.py --with-engine-flags` | T6 executor dispatch over 45 verbs (SUPPORTED_VERBS_V2) — honest flag, not a target |


## 2026-10-02 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.9869** (301/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **0.9922** (634/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.247 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.0934** (DRAW) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |
| PC-7 engine_supported_cards | **297/305** (0.9738) | `python tools/measure_grammar.py --with-engine-flags` | T6 executor dispatch over 45 verbs (SUPPORTED_VERBS_V2) — honest flag, not a target |


## 2026-10-02 (T5 — Phase-1 grammar measurement harness)

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
| PC-7 engine_supported_cards | **297/305** (0.9738) | `python tools/measure_grammar.py --with-engine-flags` | T6 executor dispatch over 45 verbs (SUPPORTED_VERBS_V2) — honest flag, not a target |


## 2026-10-02 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.9869** (301/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **0.9922** (634/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.244 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.0934** (DRAW) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |
| PC-7 engine_supported_cards | **297/305** (0.9738) | `python tools/measure_grammar.py --with-engine-flags` | T6 executor dispatch over 45 verbs (SUPPORTED_VERBS_V2) — honest flag, not a target |


## 2026-10-02 (wave-5 fix batch A / r22a — own-dies law, sacrifice-vocab, designation gate)

| Number | Value | Command | Notes |
|---|---|---|---|
| scenarios | **278/278** (274 + 4 promotions; havoc_jester + spellgorger re-scripted, asserts byte-unchanged) | `.venv/bin/python tools/run_scenarios.py` | own-dies law + sac-victim ask channel |
| suspects | **1/21** fail-only as expected | `.venv/bin/python tools/run_scenarios.py --dir tools/audit/suspects` | conclave_mentor now fails ONLY the CounterPlacedEvent leg (22b) |
| suite | **2249 passed + 3 subtests, 0 failed** (2239 + 10 new r22a pins) | `pytest MTG_bot/core -q` | pyright Δ0 (6 pre-existing), ruff Δ0 (2 pre-existing) |
| CR 701.14a | sacrifice pool **controller-filtered** — was ANY-controller (opponent creatures sacrificable) | pinned: `test_executor_r22a.SacrificeVocabulary` | latent since bridge; masked by lowest-handle witness |
| traces | **0/10 diverge — NO repin** | `.venv/bin/python tools/traces/catalog.py compare` | fixes never fire on the 10 trace seeds |
| games | **0 crash classes / 100 seeds**; 86 survived, mean 57.69 turns | `.venv/bin/python -m MTG_bot.core.executor.games --seeds 100 --pool all` | baseline band 85/57.4 — unchanged |
| PC invariants | PC-1 301/305 · PC-2 634/639 · PC-3 0 · PC-4 0 **EXACT** | `.venv/bin/python tools/measure_grammar.py` | engine edits compile-neutral; see 2026-10-02 T5 section |

## 2026-10-02 (T5 — Phase-1 grammar measurement harness)

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


## 2026-10-01 (T5 — Phase-1 grammar measurement harness)

| Number | Value | Command | Notes |
|---|---|---|---|
| PC-1 card_coverage | **0.9869** (301/305) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — PASS |
| PC-2 sentence_coverage | **0.9922** (634/639) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — PASS |
| PC-3 ambiguity | **0** entries | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-4 golden_stability | **0 diffs** (305 files, verified) | `python tools/measure_grammar.py --set M21` | target 0 — PASS |
| PC-5 compile_latency p99 | **0.245 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
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
| PC-5 compile_latency p99 | **0.243 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
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
| PC-5 compile_latency p99 | **0.246 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
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
| PC-5 compile_latency p99 | **0.246 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
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
| PC-5 compile_latency p99 | **0.271 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
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
| PC-5 compile_latency p99 | **0.241 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.0934** (DRAW) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |
| PC-7 engine_supported_cards | **297/305** (0.9738) | `python tools/measure_grammar.py --with-engine-flags` | T6 executor dispatch over 45 verbs (SUPPORTED_VERBS_V2) — honest flag, not a target |


## 2026-10-01 (r19b — wave-2 fix-B gates)

| Number | Value | Command | Notes |
|---|---|---|---|
| scenario suite | **140/140** | `.venv/bin/python tools/run_scenarios.py` | 131 at fix-A close + 9 wave-2b promotions (turn_to_slag, sparkhunter_masticore, thrill_of_possibility, scorching_dragonfire, discontinuity, sanguine_indulgence, volcanic_salvo, track_down, see_the_truth) |
| core unit tests | **2152 passed + 4 subtests, 0 failed** | `.venv/bin/python -m pytest MTG_bot/core -q` | 2134 baseline + 18 new `test_executor_r19b.py` |
| suspects ledger | **13 remain** (12 FAIL + 1 PASS) | `.venv/bin/python tools/run_scenarios.py --dir tools/audit/suspects` | 9 fixed+promoted this batch; 4 STOP (secure_the_scene, tampering_no_block, transmogrify, capture_sphere); 9 DEFER-19c cast-lane |
| trace divergence | **0/10 seeds** | `.venv/bin/python tools/traces/catalog.py compare` | after r19b repin (3 seeds diverged pre-repin, all attributed: 2× Discontinuity END_TURN-exile digest, 1× bottom-put reorder surfacing at a later draw) |
| PC-1…PC-4 | **301/305 · 634/639 · 0 · 0** | `.venv/bin/python tools/measure_grammar.py --with-engine-flags` | byte-identical to T5/fix-A rows (compiler untouched); PC-6/PC-8 pre-existing FAILs unchanged |
| pyright (touched files) | **0 errors** | `pyright MTG_bot/core/executor/{__init__,legality,quantity,replacements,selectors,stack,verbs}.py MTG_bot/core/test_executor_r19b.py` | executor fix surface clean |

## 2026-10-01 (T5 — Phase-1 grammar measurement harness)

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
| PC-7 engine_supported_cards | **297/305** (0.9738) | `python tools/measure_grammar.py --with-engine-flags` | T6 executor dispatch over 45 verbs (SUPPORTED_VERBS_V2) — honest flag, not a target |


## 2026-10-01 (r19a — wave-2 fix-A gates)

| Number | Value | Command | Notes |
|---|---|---|---|
| scenario suite | **131/131** | `.venv/bin/python tools/run_scenarios.py` | 126 at authoring-close HEAD 0ff4d7f + 5 wave-2 promotions |
| core unit tests | **2134 passed + 4 subtests, 0 failed** | `.venv/bin/python -m pytest MTG_bot/core -q` | 2112 baseline + 22 new `test_executor_r19a.py` |
| suspects ledger | **3/22 pass** | `.venv/bin/python tools/run_scenarios.py --dir tools/audit/suspects` | was 7/27 pre-cleanup; the 3 greens (`sanguine_indulgence`, `secure_the_scene`, `volcanic_salvo`) are untouched out-of-scope packs |
| trace divergence | **0/10 seeds** | `.venv/bin/python tools/traces/catalog.py compare` | after r19a repin (5 seeds diverged pre-repin, all attributed) |
| PC-1…PC-4 | **301/305 · 634/639 · 0 · 0** | `.venv/bin/python tools/measure_grammar.py --with-engine-flags` | byte-identical to T5 rows (compiler untouched); PC-6/PC-8 pre-existing FAILs unchanged |

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
| PC-5 compile_latency p99 | **0.247 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
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
| PC-5 compile_latency p99 | **0.247 ms/card** (3 runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — PASS |
| PC-6 vocabulary_health | orphans **1** / max share **0.0934** (DRAW) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — FAIL |
| PC-7 executor_coverage | **pending_executor** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |
| PC-8 targetable_fraction | **0.3213** (98/305) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — FAIL |
| PC-9 determinism | **stable** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |
| PC-10 null_test | **100% / 0%**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — PASS |
| PC-7 engine_supported_cards | **297/305** (0.9738) | `python tools/measure_grammar.py --with-engine-flags` | T6 executor dispatch over 45 verbs (SUPPORTED_VERBS_V2) — honest flag, not a target |


## 2026-10-01 (wave-2 derivation — loop step 1)

| Number | Value | Command | Notes |
|---|---|---|---|
| wave2 cohort (r17 loop step 1) | **67 rows** = 70 SpellAbility cards − 5 gate-excluded + 2 carry-over; 67/67 engine-supported & with art | `.venv/bin/python tools/audit/wave_builder.py --wave2 && … --wave2 --lint` | 5 excluded all COUNTER_SPELL-caused (Cancel, Lofty Denial, Miscast, Rewind, Sublime Epiphany +COPY); carry-overs Capture Sphere + Wildwood Scourge verified zero SpellAbility nodes; wave-1 lint still green; core 2112+4 unchanged |

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

## 2026-10-01 (wave-2 authoring — campaign loop step 2)

| Number | Value | Command | Notes |
|---|---|---|---|
| Packs green | **126/126** (84 old + 42 new: 24 batch-A + 18 batch-B) | `python tools/run_scenarios.py` | orchestrator re-ran; engine untouched by authoring |
| Wave-2 suspects | **27 files** (25 new + 2 carry-overs re-confirmed) | `ls tools/audit/suspects/` | ~10 silent-bug root causes; rest harness/designation/cast-lane |
| Core suite | **2112 + 4 subtests** unchanged | `python -m pytest MTG_bot/core -q` | authoring was tools/docs-only |

## 2026-10-01 (wave-2 fix-batch 19c — cast declaration lane)

| Number | Value | Command | Notes |
|---|---|---|---|
| scenarios | **148/148** | `.venv/bin/python tools/run_scenarios.py` | 140 + 8 promotions (duress, mind_rot, necromentia, hunters_edge, experimental_overload, return_to_nature, rookie_mistake, capture_sphere) |
| suspects | **1/5 fail-only** | `… --dir tools/audit/suspects` | secure_the_scene PASS-as-STOP; peer+wildwood STOPPED-COMPILER (golden has 0 LOSE_LIFE atoms / 0 SpellAbility+QX); tampering+transmogrify fix-B STOPs |
| core suite | **2168 passed + 4 subtests, 0 failed** | `.venv/bin/python -m pytest MTG_bot/core -q` | 2152 + 16 r19c pins; 1 AMENDED multi-target pin in test_executor_stack.py |
| PC gate | PC-1 **301/305** · PC-2 **634/639** · PC-3 **0** · PC-4 **0**; engine **297/305, V2 45** UNCHANGED | `.venv/bin/python tools/measure_grammar.py --with-engine-flags` | EXACT vs T5/fix-A/fix-B; PC-6/PC-8 standing FAILs unchanged |
| catalog | repin **6144 entries/10 games**, post **0/10 diverge** | `tools/traces/catalog.py repin && … compare` | seed-8 diff attributed to RandomPolicy's uniform choose over the +alias CHOOSE vocab (games.py:383-403) |
| pyright / ruff | **0 new** (6 pre-existing Counter errors in run_scenarios.py); ruff **Δ0** | `pyright` / `ruff check` | 2 lints introduced mid-batch (UP037, I001) auto-fixed + re-greened |

## 2026-10-01 (wave-3 derivation — static/keyword cohort)

| Number | Value | Command | Notes |
|---|---|---|---|
| wave-3 cohort | **55 cards** (all engine-supported, all with art) | `.venv/bin/python tools/audit/wave_builder.py --wave3 [--lint]` | top-level StaticAbility+KeywordAbility nodes, derive-from-IR |
| coverage arithmetic | **100 = 44 + 1 + 55** | same | 100 static-family cards = 44 pack/suspect-covered (name) + 1 gate-flagged + 55 cohort |
| gate-flagged | **1**: Teferi, Master of Time — **PHASE_OUT** | `meta.excluded_by_flag` | static nodes themselves verb-clean (GRANT_ACTIVATION is supported); whole-card gate fails on PHASE_OUT elsewhere |
| top-5 verb families | MODIFY_PT **13** · FLYING **9** · GRANT_ABILITY **8** · LIFELINK **5** · REACH **5** | mechanics ∩ static nodes in wave3.json | 25 distinct verbs over the 55-row cohort |
| gates | wave1+wave2+wave3 lint **OK byte-identical**; core suite **2168 + 4 subtests** unchanged; pyright **0**; ruff **Δ0** | `.venv/bin/python tools/audit/wave_builder.py --lint` / `--wave2 --lint` / `--wave3 --lint` · `pytest MTG_bot/core -q` · `pyright tools/audit/wave_builder.py` | tools-only change; MTG_bot/** untouched |

## 2026-10-01 (wave-3a batch A validation — 28 static/keyword cards)

| Number | Value | Command | Notes |
|---|---|---|---|
| wave-3a batch A | **28 cards → 16 green + 12 suspect** | `.venv/bin/python tools/run_scenarios.py --dir /tmp/opencode/staging` | all 12 divergences root-caused; see 09-wave3a-findings.md |
| runner gate | **164/164** (148 baseline + 16 new) | `.venv/bin/python tools/run_scenarios.py` | zero regressions |
| suite gate | **2168 + 4 subtests** unchanged | `.venv/bin/python -m pytest MTG_bot/core -q` | engine frozen, untouched |
| dead keywords | LIFELINK **0** · PROWESS **0** · BATTALION **0** handler hits | `grep -rn "LIFELINK\|PROWESS\|BATTALION" MTG_bot/core/executor/` | compiled+layered but no runtime teeth; 7 of 12 suspects |

## 2026-10-01 (wave-3b batch B validation — 27 static/keyword cards)

| Number | Value | Command | Notes |
|---|---|---|---|
| wave-3b batch B | **27 cards → 22 green + 9 suspect files** | `.venv/bin/python tools/run_scenarios.py --dir /tmp/opencode/b3b_ship` | 5 card-level + 4 systemic root-caused; see 10-wave3b-findings.md |
| runner gate | **186/186** (164 baseline + 22 new) | `.venv/bin/python tools/run_scenarios.py` | zero regressions |
| suite gate | **2168 + 4 subtests** unchanged | `.venv/bin/python -m pytest MTG_bot/core -q` | engine frozen, untouched |
| creature cast gap | **163/165** creature goldens lack SpellAbility | golden-pool scan (`abilities` node tags) | `cast:not_a_spell` = systematic silent lane-gap |

## 2026-10-01 (wave-3 fix batch A / r20a — dead keywords given runtime teeth)

| Number | Value | Command | Notes |
|---|---|---|---|
| r20a batch | **10/10 suspect packs green & promoted** (LIFELINK·PROWESS·BATTALION·granted-drain·prevention) | `.venv/bin/python tools/run_scenarios.py` | engine editing authorized; see 11-wave3-fix-a.md |
| runner gate | **196/196** (186 baseline + 10) | `tools/run_scenarios.py` | zero regressions |
| suite gate | **2182 + 4 subtests** (2168 + 14 new) | `.venv/bin/python -m pytest MTG_bot/core -q` | `test_executor_r20a.py` new |
| grammar gate | PC-1 **301/305** · PC-2 **634/639** · PC-3 0 · PC-4 **exact-unchanged** | `tools/measure_grammar.py` | PC-6/PC-8 pre-existing fails; PC-7 deferred |
| traces | **10/10 seeds IDENTICAL — 0 diverging, no repin** | `tools/traces/catalog.py compare` | new drains never fire in sim corpus |
| games | **0 crash classes / 100 seeds**; 85 survived, mean 57.4 turns | `python -m MTG_bot.core.executor.games --seeds 100 --pool all` | `reports/games_2026-10-01.json` |
| lint/type | pyright **0** · ruff **Δ0 vs HEAD** (all 5 changed files) | `pyright <files>` · `ruff check --stdin-filename …` | one self-introduced I001 fixed |

## 2026-10-01 (wave-3 fix batch B / r20b — trigger-feed, replacement & disclosure lanes)

| Number | Value | Command | Notes |
|---|---|---|---|
| r20b batch | **4/5 suspects fixed & promoted; 1 compiler-STOP** (warden/targeting, hooded/player-subject, priest/zone-replacement, snoop/disclosure; rin mis-split → backlog) | `.venv/bin/python tools/run_scenarios.py --dir tools/scenarios` | see 12-wave3-fix-b.md |
| runner gate | **200/200** (196 baseline + 4) | `tools/run_scenarios.py --dir tools/scenarios` | rin stays a suspect (registers loud; not promotable) |
| suite gate | **2196 passed** (2182 + 14 new) | `.venv/bin/python -m pytest MTG_bot/core -q` | `test_executor_r20b.py` new; full-tree 23 fails == HEAD pre-existing (rule_engine/strategic_brain, verified in HEAD worktree) |
| grammar gate | PC-1 **301/305** · PC-2 **634/639** · PC-3 0 · PC-4 **exact** | `tools/measure_grammar.py --with-engine-flags` | PC-6/PC-8 pre-existing fails; PC-7 deferred |
| traces | 9/10 diverge (pure TARGETING insertions @ designation) → **repin 6162 entries → 0/10** | `tools/traces/catalog.py repin && … compare` | reconcile evidence: first diff per seed = TARGETING row above CAST row |
| games | **0 crash classes / 100 seeds**; 85 survived, mean 57.4 turns | `python -m MTG_bot.core.executor.games --seeds 100 --pool all` | identical to r20a baseline |
| lint/type | pyright **0 errors** · ruff **Δ0 vs HEAD** | `pyright MTG_bot/core/executor …` · `ruff check` vs HEAD worktree | 4 self-introduced lint items fixed |

## 2026-10-01 (wave-3 fix batch C / r20c — cast/cost/attach lanes, batch close)

| Number | Value | Command | Notes |
|---|---|---|---|
| r20c batch | **4/6 suspects fixed & promoted; 2 compiler-STOPs** (hobblefiend/self-designation, scythe/LKI, waker/hand-activation, speaker/life-lead; ornery count-misread + creature-SpellAbility-gap → backlog) | `.venv/bin/python tools/run_scenarios.py --dir tools/scenarios` | see 13-wave3-fix-c.md |
| runner gate | **204/204** (200 baseline + 4) | `tools/run_scenarios.py --dir tools/scenarios` | suspects retained as audit trail |
| suite gate | **2213 passed** (2196 + 17 new), 0 failed | `.venv/bin/python -m pytest MTG_bot/core -q` | `test_executor_r20c.py` new; probe rotated to CONTROLLER_COUNT_GT |
| grammar gate | PC-1 **301/305** · PC-2 **634/639** · PC-3 0 · PC-4 **exact (0 diffs)** | `tools/measure_grammar.py --with-engine-flags` | detach_lki/starting_life fingerprint-excluded |
| traces | **0/10 diverge — NO repin** (first batch-closed campaign-wide) | `tools/traces/catalog.py compare` | fixes never fire on the 10 trace seeds |
| games | **0 crash classes / 100 seeds** (83 caps, 17 game-overs) | `python -m MTG_bot.core.executor.games --seeds 100 --pool all` | |
| lint/type | pyright **6 == HEAD baseline 6** (pre-existing Counter noise) · ruff **Δ0 vs HEAD** | `pyright …` · `ruff check --no-cache` vs HEAD worktree | 1 self-introduced SIM102 fixed |

## 2026-10-01 (wave-4 derivation — mana/activated cohort)

| Number | Value | Command | Notes |
|---|---|---|---|
| wave-4 cohort | **43 cards** (all engine-supported, all with art) | `.venv/bin/python tools/audit/wave_builder.py --wave4 [--lint]` | ActivatedAbility nodes via walk(), derive-from-IR; 93/94 top-level, sole nested (Gadrak TokenSpec) pack-covered anyway |
| coverage arithmetic | **94 = 49 + 2 + 43** | same | 94 activated-family cards = 49 pack/suspect-covered (name, 203-name union) + 2 gate-flagged + 43 cohort |
| gate-flagged | **2**: Teferi, Master of Time + Teferi, Timeless Voyager — **PHASE_OUT** | `meta.excluded_by_flag` | same offenders as wave-3 flag; re-admit when phase-out lands |
| cycling lane | **0 cards** | golden-dump text scan | M21 goldens carry zero cycling text — lane named in meta as verified no-op |
| top-5 verb families | ADD_MANA **8** · GRANT_ABILITY **7** · PUT_COUNTER **6** · DRAW **6** · DEAL_DAMAGE **5** | mechanics ∩ activated effects in wave4.json | cost mix: CostTap 24 · CostManaGeneric 21 · CostManaColor 20 · CostLoyalty 18 · CostSacrifice 9 |
| gates | wave4 lint **OK**; wave1/2 files lint **byte-identical**; wave3.json file byte-identical but **lint pre-drifted at HEAD** (55 wave-3 packs promoted post-freeze, not re-frozen at closeout) | `--lint` / `--wave2 --lint` · `md5sum` | suite **2213 + 3 subtests** unchanged; pyright **0**; ruff **Δ0**; tools-only |
| wave-4b packs | **18 promoted** (204 -> **222**, all green) | `.venv/bin/python tools/run_scenarios.py` -> `222/222 packs passed` | 21 batch names: 18 green, 2 suspects |
| wave-4b suspects | **2**: sanctum_tranquil_light (activation lane never folds CostModifier - rigid `cost:mana_generic:4<5`) + tormods_crypt (TARGET_PLAYER UNIV filter -> binding-first per-card exile, no gy sweep - silent) | `.venv/bin/python tools/run_scenarios.py --dir /tmp/opencode/staging4b` + both-designate control probe | NAME_EQ 'Shrine' vs SUBTYPE_EQ secondary defect in STL modifier |
| wave-4b gates | scenarios **222/222**; pytest **2213 passed + 3 subtests** (engine frozen, unchanged) | `tools/run_scenarios.py` / `pytest MTG_bot/core -q` | 2026-10-01 |

## 2026-10-01 (wave-4a adjudication — mana/activated cohort, first half)

| Number | Value | Command | Notes |
|---|---|---|---|
| wave-4a batch | **22 cards** (Animal Sanctuary → Mazemind Tome), engine frozen | tools/audit/wave4.json first half | sibling batch = wave4b (file 17) |
| wave-4a packs | **17 green promoted** (222 -> **239**, all green) | `.venv/bin/python tools/run_scenarios.py` -> `239/239 packs passed` | 5 cards suspect-only (Caged Zombie, Magmutt, Epitaph Golem, Furious Rise, Ghostly Pilferer) |
| wave-4a suspects | **11 files / 10 cards**, 0/11 fail-only as designed | `tools/run_scenarios.py --dir tools/audit/suspects` | loud: THAT_MANY_COUNT (Basri Ket −2), CONTROLLER_COUNT_GT (Garruk −2), 'result' register (Furious Rise phantom activation), condition:false (Caged Zombie); silent: +1/+1 counter has no INDESTRUCTIBLE (Basri Ket +1), searched land enters UNTAPPED <4 lands (Fabled Passage), Chaff draw-through not BOTTOM (Epitaph Golem), loyalty never decremented (Magmutt/Leafkin bolt), can't-be-blocked never applied (Ghostly Pilferer), no opponent-life-loss clause (Waker +1), CREATURE_DIES row not consulted (Caged Zombie) |
| gates | scenarios **239/239**; pytest **2213 passed + 3 subtests** (engine frozen, unchanged) | `tools/run_scenarios.py` / `pytest MTG_bot/core -q` | 2026-10-01 |

## 2026-10-01 (wave-4 fix-a r21a — planeswalker damage / prevention-condition sides / zero-loyalty SBA)

| Number | Value | Command | Notes |
|---|---|---|---|
| r21a suspects dispositioned | **4 FIXED+promoted, 1 STOP** (liliana +1: golden e0df8e2a ability[0] is a single DISCARD atom — can't-discard life clause never compiled) | tools/audit/suspects/ + file 18 | 21 -> **17 suspect files** |
| packs | **239 -> 243 green** (+4 promotions: Ghostly Pilferer, Magmutt, Leafkin bolt [corrected to walker-death truth], Basri Ket +1 [LOYALTY 4, INDESTRUCTIBLE]) | `.venv/bin/python tools/run_scenarios.py` -> `243/243 packs passed` | 2026-10-01 |
| suite | **2222 passed + 3 subtests, 0 failed** (2213 + 9 new r21a) | `pytest MTG_bot/core -q` | new MTG_bot/core/test_executor_r21a.py |
| PC line | **PC-1 301/305 · PC-2 634/639 · PC-3 0 · PC-4 0** (unchanged) | `tools/measure_grammar.py --with-engine-flags` | 2026-10-01 |
| traces | seeds 3+7 diverged by design (STATE_CHECK walker-death rows) -> repinned; compare **0/10**; games **100/100, 0 crash classes** | `tools/traces/catalog.py repin` / `build --seeds 100 --pool all --catalog /tmp` | outcome classes unchanged |

## 2026-10-01 (wave-4 fix-b r21b — activation fold / dual-count pred / dies narrowing / graveyard sweep)

| Number | Value | Command | Notes |
|---|---|---|---|
| r21b suspects dispositioned | **5 FIXED+promoted, 3 STOP-witnesses stand** (Sanctum = compiler NAME_EQ-instead-of-SUBTYPE census; Fabled = no tapped_on_enter TRUE branch; Furious Rise = phantom activation) | tools/audit/suspects/ + file 19 | 8 in scope; suspects dir 17 -> 12 files (two double-state suspect JSONs deleted in orchestrator audit) |
| packs | **243 -> 248 green** (+5: basri_ket [life 11 — author 8 was misprint], caged_zombie [+damage-mark assertion], epitaph, garruk, tormods) | `.venv/bin/python tools/run_scenarios.py` -> `248/248 packs passed` | fabled_passage.json restructured with falsifiability pin `"tapped": {"s1": false}`, still green |
| suite | **2239 passed + 3 subtests, 0 failed** (2222 + 17 new r21b; r19a DIED battlefield pin AMENDED) | `pytest MTG_bot/core -q` | new MTG_bot/core/test_executor_r21b.py |
| games | **0 crash classes**, survived 86/100, coverage 84 cards | `.venv/bin/python -m MTG_bot.core.executor.games --seeds 100 --pool all` | reports/games_2026-10-01.json |
| traces | **0/10 diverging — NO repin** (all 7 fixes narrowly gated, traces byte-stable) | `.venv/bin/python tools/traces/catalog.py compare` | contrast r21a (2 seeds repinned) |
| wave-4 lint | **43/43 covered, consumed** | `.venv/bin/python tools/audit/wave_builder.py --wave4 --lint` | ruff Δ0 vs HEAD on every touched file |
| PC line | **PC-1 301/305 · PC-2 634/639 · PC-3 0 · PC-4 0** (unchanged, no IR touched) | `tools/measure_grammar.py` | 2026-10-01 (tool auto-appended its own row) |

## 2026-10-01 (wave-5 derivation — TRIGGER/REPLACEMENT residue cohort)

| Number | Value | Command | Notes |
|---|---|---|---|
| wave-5 cohort | **31 rows** = 136 trigger/replacement-family cards − 104 pack/suspect-covered (name) − 1 gate-flagged | `.venv/bin/python tools/audit/wave_builder.py --wave5 [--lint]` | names-split: 25 trigger-only (incl. 4 Sanctum lands) + 3 PW-emblem records + 2 replacement-only + 1 hybrid (Conclave Mentor); Forgotten Sentinel out (top-level EtBState, zero trigger/replacement nodes — residue doc, meta.residue_note) |
| gate exclusion | **Double Vision** sole-cause COPY | `meta.excluded_by_flag` | re-admit when COPY lands; 31/31 engine-supported + art |
| verb histogram (mechanics) | **PUT_COUNTER 8 · DEAL_DAMAGE 5 · MODIFY_PT 4 · GRANT_ABILITY 4 · DRAW 4** (then CREATE_TOKEN 3, GAIN_LIFE 3, SEARCH 2) | tools/audit/wave5.json | wave-5 effect payloads only |
| lints | **--wave5 lint OK (31, IR current)**; w1 66/66 · w2 67/67 · w3 55/55 · w4 43/43 consumed; --coverage byte-identical | `.venv/bin/python tools/audit/wave_builder.py {--lint,--waveN --lint,--coverage}` | meta.status unset (open wave) |
| suite | **2239 passed + 3 subtests, 0 failed** (unchanged; tools-only) | `pytest MTG_bot/core -q` | pyright 0, ruff Δ0 on builder |

## 2026-10-02 (wave-5 fix-b r22b — damage/draw/counter replacement consumers)

| metric | value | producing command | notes |
|---|---|---|---|
| scenarios | **281/281 passed** | `.venv/bin/python tools/run_scenarios.py` | 278 + 3 promoted (fiery/teferi/conclave); fiery brute 2/2→2/3 setup fix |
| core suite | **2261 passed + 3 subtests, 0 failed** | `pytest MTG_bot/core -q` | 2249 baseline + 12 new `test_executor_r22b.py` |
| grammar | **PC-1 301/305 · PC-2 634/639 · PC-3 0 · PC-4 0** EXACT baseline | `tools/measure_grammar.py --with-engine-flags` | unchanged (engine-side only) |
| fingerprints | **0/10 seeds diverging, NO repin** | `tools/traces/catalog.py compare` | new consults inert without matching replacement records |
| games | **100/100, 0 crashes** (61 667 journal entries) | `tools/traces/catalog.py build --pool all --seeds 100 --catalog /tmp/...` | probe catalog outside the pinned one |
| lints | pyright **0** on touched files; ruff **Δ0** | `pyright <files>` / `ruff check` | 2 I001 in new code self-fixed |

## 2026-10-02 (wave-5 fix-c r22c — loyalty feed + 5 compiler-side STOPs)

| Item | Number | Command | Note |
|---|---|---|---|
| scenarios | **282/282 passed** | `.venv/bin/python tools/run_scenarios.py` | 281 + keral promoted (MOVE+strip); suspects 18→17 |
| core suite | **2271 passed + 3 subtests, 0 failed** | `pytest MTG_bot/core -q` | 2261 + 10 new `test_executor_r22c.py` |
| grammar | **PC-1 301/305 · PC-2 634/639 · PC-3 0 · PC-4 0** EXACT baseline | `tools/measure_grammar.py --with-engine-flags` | unchanged (no IR touched) |
| fingerprints | **2/10 seeds diverged by pure LOYALTY_ACTIVATED insertion → repinned → 0/10** | `tools/traces/catalog.py compare / repin` | outcomes identical; 12b/r20b precedent |
| games | **100 seeds, 86 survived, 0 crash classes** | `python -m MTG_bot.core.executor.games --seeds 100 --pool all` | reports/games_2026-10-02.json |
| lints | pyright **0** on 4 touched files; ruff **Δ0** | `pyright <files>` / `ruff check` | legality TRY004 is HEAD-documented |
| stops | **5**: sancti×3 (compiler NAME_EQ "Shrine" idiom, goldens pin it), adherent (quantifier loss, 19a precedent), pyreling (no destination pred) | `KNOWLEDGE/2026-10-01/25-wave5-fix-c.md` | falsifiability pins reproduce every witness from hand-built IR |

## 2026-10-02 (compiler campaign C1 — NAME_EQ idiom sweep + sanctum promotions)

| Item | Number | Command | Note |
|---|---|---|---|
| sweep | **13 NAME_EQ atoms / 11 cards → 6 idiom (4 sancta, 5 atoms) fixed, 7 legit kept** | inventory audit over 305 goldens (HEAD d0d11cf) | post-sweep non-name NAME_EQ args: NONE |
| golden set-equality | **4 files moved, keys={abilities} only, 301/305 byte-identical, multisets set-equal after {NAME_EQ→TYPE_EQ on Shrine}** | `/tmp/opencode/c1_inventory_audit.py` vs `/tmp/golden_pre_c1` | B-11/B-17/B-22 protocol; PC-4 refresh-goldened → **0** |
| scenarios | **286/286 passed** | `.venv/bin/python tools/run_scenarios.py` | 282 + 4 sancta promoted (MOVE+strip); suspects 17→13 |
| core suite | **2272 passed + 3 subtests, 0 failed** | `pytest MTG_bot/core -q` | 2271 + 1 new b5c pin; 2 b2a pins AMENDED; r22c honest-0 pin KEPT |
| grammar | PC EXCEPT: PC-1 301/305 · PC-2 634/639 · PC-3 0 · PC-4 0 (refreshed) · **PC-8 0.3213 Δ0 no-move** | `tools/measure_grammar.py --set M21 --refresh-goldens --with-engine-flags` | engine 297/305; PC-6 orphan pre-existing FAIL |
| catalog | **0/10 diverge, no repin** | `tools/traces/catalog.py compare` | seeds 0–9 incl. 605-entry seed 7 |
| games | **100 seeds, 86 survived, 0 crash classes** | `.venv/bin/python MTG_bot/core/executor/games.py --seeds 100 --pool all` | = 22c baseline; reports/games_2026-10-02.json |
| lints | pyright **0** on 4 touched files; ruff **Δ0** | `pyright <files>` / `ruff check` | b5c test I001 is HEAD-preexisting same line |
| stays suspect | adherent_of_hope (NAME_CONTAINS, quantifier loss ≠ this idiom), chandras_pyreling; **flag**: secure_the_scene PASSes at HEAD (asserts don't exercise its loss) | stash-verified 1/17 pre → 5/17 post (4 sancta) | `KNOWLEDGE/2026-10-02/01-compiler-c1-name-eq-idiom.md` |

## 2026-10-02 (wave-6 residue wave — two /26 gaps closed)

| Item | Number | Command | Note |
|---|---|---|---|
| scenarios | **287/287 passed** | `.venv/bin/python tools/run_scenarios.py` | 286 + forgotten_sentinel (EtBState via enter op, first-try green) |
| suspects | **14 files, 0/14 red-as-intended**; new treasure_token_activation red at `pool has no card 'Treasure'` | `.venv/bin/python tools/run_scenarios.py --dir tools/audit/suspects` | HARNESS routing, not compiler; mint-half probe green |
| census | **305 = 267 pack + 9 suspect + 29 uncovered** (31→29; +5 stale rows legitimately promoted by disk-derived refresh) | `.venv/bin/python tools/audit/wave_builder.py --coverage` | Treasure→suspect, Forgotten Sentinel→pack |
| five-wave lint | 66/66 · 67/67 · 55/55 · 43/43 · 31/31 (+3 waived) all "closed: consumed" | `wave_builder.py --waveN --lint` | unchanged |
| core suite | **2272 + 3 subtests, unchanged** | `pytest MTG_bot/core -q` | engine frozen, zero edits outside tools/ |

## 2026-10-02 (compiler campaign C2 — existential quantifiers + Fabled tapped_on_enter)

| Item | Number | Command | Note |
|---|---|---|---|
| golden set-equality | **3 files moved, keys={abilities} only, 302/305 byte-identical, per-card multiset set-equal** (FP +tapped_on_enter pair; adherent +1 COUNT_GE(count=1), 3 filter atoms verbatim; ornery count 4→1, filter EQUAL) | `/tmp/opencode/c2_inventory_audit.py` vs `/tmp/golden_pre_c2` | C1 protocol on HEAD cb98a7c; B5c row verified Fabled-only in M21 via data `text` grep |
| scenarios | **290/290 passed** | `.venv/bin/python tools/run_scenarios.py` | 287 + 3 promoted (MOVE+strip), all 3 green under fixed IR pre-promotion; suspects 14→11 |
| suite | **2277 passed + 3 subtests, 0 failed** | `pytest MTG_bot/core -q` | 2272 + 5 new test_compiler_c2.py pins; 2 pins AMENDED (b2a adherent, b2b ornery) |
| grammar | PC EXCEPT: PC-1 301/305 · PC-2 634/639 · PC-3 0 · PC-4 0 (refreshed) · **PC-8 0.3213 Δ0 no-move** | `tools/measure_grammar.py --set M21 --refresh-goldens --with-engine-flags` | engine 297/305; PC-6 orphan pre-existing FAIL; all Δ0 vs C1 baseline — honest no-coverage-gain report |
| catalog | **6/10 diverged → repin → 0/10** | `tools/traces/catalog.py compare` / `repin` | attribution clean: each diverging seed +2 entries incl. one new TAP_STATE·SEARCH (Fabled flag); outcomes identical per seed |
| games | **100 seeds, 86 survived, 0 crash classes** | `.venv/bin/python -m MTG_bot.core.executor.games --seeds 100 --pool all` | mean_turns 57.69, coverage fired 84; = baseline; reports/games_2026-10-02.json |
| lints | pyright **0 errors** on 6 touched files; ruff **all pass** | `pyright` / `ruff check` | engine untouched |

## 2026-10-02 (compiler campaign C3 — clause restores: Waker +1 tail, Transmogrify reveal-until; Peer STOP)

| Item | Number | Command | Note |
|---|---|---|---|
| golden set-equality | **2 files moved, keys={abilities} only, 303/305 byte-identical, lanes proven per-card** (Waker +1 LOSE_LIFE pair, +1 ZONE_COUNT_GE/QConst(1) gate atom; Transmogrify +1 SEARCH triple pair +1 SHUFFLE pair, +1 TYPE_EQ Creature atom; Peer BYTE-IDENTICAL = STOP honored) | `/tmp/opencode/c3_inventory_audit.py` vs `/tmp/golden_pre_c3` | C1 protocol on HEAD 9e26ba2; uniqueness of all 3 shapes proven by bucket-wide grep (single occurrence each) |
| scenarios | **292/292 passed** | `.venv/bin/python tools/run_scenarios.py` | 290 + 2 promoted; transmogrify pack FIXED to dual positional designation `decisions:["player:1"]` (14b synthesized slot); suspects 11→9, peer stays red-as-intended (`expected 10, got 20`) |
| suite | **2284 passed + 3 subtests, 0 failed** | `.venv/bin/python -m pytest MTG_bot/core -q` | 2277 + 7 test_compiler_c3.py + pins updates in b5a/b5b suites (185 bucket tests) |
| grammar | PC-1 **303/305** · PC-2 **637/639** · PC-3 0 · PC-4 0 (305 verified) · **PC-8 98/305 Δ0**; UNPARSED queue 5→3 | `tools/measure_grammar.py --with-engine-flags` | PC-6/PC-8 FAIL vs targets pre-existing (10-01 same list); histogram Δ = exactly the batch (LOSE_LIFE+1, SEARCH+1, SHUFFLE+1) |
| catalog | **2/10 diverged → repin → 0/10** | `tools/traces/catalog.py compare` / `build` | attribution clean: seed 1 = Transmogrify in deck, seed 7 = Waker+Transmogrify; other 8 seeds byte-identical |
| games | **100 seeds, 86 survived, 0 crash classes** | `.venv/bin/python -m MTG_bot.core.executor.games --seeds 100 --pool all` | = baseline; mean_turns 57.69; reports/games_2026-10-02.json |
| lints | pyright **0 errors** on touched files; ruff **Δ0** (68 = baseline incl. new file) | `pyright` / `ruff check` | engine frozen, zero engine edits |

## 2026-10-02 (compiler campaign C4 — creature cast lane: SpellAbility(CREATURE) for all 147 plain creatures)

| Item | Number | Command | Note |
|---|---|---|---|
| golden set-equality | **147 goldens moved, keys={abilities} only, 158 byte-identical** (each mover = pre-list + exactly ONE appended effect-less `SpellAbility(CREATURE)`; src=len(sentences)-1) | `/tmp/opencode/c4_inventory_audit.py` vs `/tmp/golden_pre_c4` | roadmap "163" was a grep count incl. **16 token creatures** (correctly untouched); Goremand/Sparkhunter falsified as additional-costs carriers — byte-identical, no duplicate node |
| grammar | PC-3 **0** · PC-4 **0** (305 refreshed) · PC-1 303/305 · PC-2 637/639 Δ0 · **PC-8 0.3213 Δ0** (honest: effect-less carrier has no targets) | `tools/measure_grammar.py --set M21 --refresh-goldens --with-engine-flags` | refreshed tree byte-equal to audited compile (`diff -r` clean) |
| scenarios | **293/293 passed**; suspects **0/9** | `tools/run_scenarios.py` [+ `--dir tools/audit/suspects`] | `creature_spell_nodes_systematic` promoted; NEW red `flash_window_engine_gap` (legality.py:1101 no keyword consult, CR 702.9a); wildwood finding extended (lane opens, QX=engine EtBState half) |
| suite | **2290 passed + 3 subtests, 0 failed** | `.venv/bin/python -m pytest MTG_bot/core -q` | 2284 + 6 test_compiler_c4.py pins; 18 honest falsifications amended (carrier append); B9 pin: raise MOVED `not_a_spell`→`cost:mana` |
| catalog | **10/10 diverged → repin → 0/10** | `tools/traces/catalog.py compare` / `repin` | every first-divergence = new CAST entry; outcomes flip cap→decisive kill = intended blast radius |
| games | **83 decisive game-overs (first campaign games END; mean_turns 31.05 vs 57.69), 17 crash games / 7 classes** (baseline 0) | `.venv/bin/python -m MTG_bot.core.executor.games --seeds 100 --pool all` | ALL 7 attributed executor-half (TARGETS_SOURCE×5, target-prompt×3, QX×3 = wildwood, tripwire×2 guard, GAIN_LIFE layer×2, event-register×1, Radha land-cast×1 legality guard); zero compiler-emission defects; engine frozen |
| lints | pyright **0 errors** (8 touched files); ruff **Δ0** (per-file multisets = HEAD) | `pyright` / `ruff check` | ruff compares MUST copy HEAD copies inside the repo (config differs outside root) |

## 2026-10-02 (engine batch 23a — seven crash classes killed + FLASH; class 8 exposed & killed)

| Item | Number | Command | Note |
|---|---|---|---|
| games | **0 crash classes / 100 seeds** (was 17 games/7 classes), 100 decisive endings 48/52, mean_turns 33.49, coverage 230 fired | `.venv/bin/python -m MTG_bot.core.executor.games --seeds 100 --pool all --deck-pairs-seed 1409 --turns 60` | 8th class COLOR_COUNT_GE EXPOSED by the TARGETS_SOURCE fix (seeds 26/33/95 survived further) and killed same batch — identity color-count, Basri protection gate + Ugin exile filter |
| tripwire | quarantine guard: fires once, games 17/50 end clean, ledger `trigger_loops=['card:102 (Chandra\'s Incinerator)…quarantined']` | `…games … --repro 17` | permanent per-source quarantine folded into fingerprint via binder.dump(); re-raise only at ≥8 quarantines/game |
| suite | **2306 passed + 3 subtests, 0 failed** | `.venv/bin/python -m pytest MTG_bot/core -q` | new test_executor_r23a.py 16 pins; 4 stale pins amended to the guard contract (tripwire/GAIN_LIFE/land-cast/bare-ctx TARGETS_SOURCE) |
| scenarios | **297/297 passed**; suspects 9→**7** | `tools/run_scenarios.py` | promoted targets_source_cost_fold, rin_seri_static_guard + de-suspected wildwood_scourge, flash_window_engine_gap (engine halves landed) |
| grammar | PC-1 303/305 · PC-2 637/639 · PC-3 0 · PC-4 0 · engine 297/305 (45 verbs) — **ALL Δ0** vs C4 | `tools/measure_grammar.py --with-engine-flags` | PC-6/PC-8 standing FAILs unchanged; engine verbs untouched (filter preds aren't verbs) |
| catalog | 1/10 diverged → repin → **0/10**; COLOR_COUNT_GE add stayed **byte-identical** | `tools/traces/catalog.py compare` / `repin` | sole divergence = GAIN_LIFE-crash seed NotImplementedError → decisive kill (intended); pure raise-replacements can't move pins |
| lints | pyright **0 errors** (13 touched files); ruff **Δ0 NEW**, −1 pre-existing | pyright CLI / ruff vs HEAD-worktree | ruff multiset deltas via `--stdin-filename` are INVALID (per-file ignores lost, phantom codes counted line numbers); copy HEAD inside repo or use a worktree |

## 2026-10-02 (compiler campaign C5 — phantom play-permission suppression + PREVENT_EFFECT; Rin STOP-spec)

| Item | Number | Command | Note |
|---|---|---|---|
| golden set-equality | **2 movers of 305** — `52b3a979` Furious Rise (phantom −52 lines) + `e6ae536a` Tampering (junk→PREVENT_EFFECT), C1-form audited vs /tmp/golden_pre_c5 | `tools/measure_grammar.py --set M21 --refresh-goldens` | PC-4 re-verify **0 diffs** (305 verified); assembly-drop carries explicit KNOWN-GAP (play permission) note (compiler.py:1477) |
| scenarios | **300/300 passed**; suspects 7→**4** files, **0/4** | `tools/run_scenarios.py` [+ `--dir tools/audit/suspects`] | promoted tampering_no_block, furious_rise_activation (NEGATIVE: not_activated / no-ability-idx refusals; hand 0:1 covers upkeep draw), rin_and_seri_cast_triggers; harness gained `expect_raise` step key (run_scenarios.py:665) |
| suite | **2312 passed + 3 subtests, 0 failed** | `.venv/bin/python -m pytest MTG_bot/core -q` | +6: TestC5FuriousRisePlayPermissionSuppression ×2 (test_templates_b2a.py:2142) + TestDurationEotSourceExemption ×4 (test_executor_r21a.py:260); b5c pin retargeted to PREVENT_EFFECT |
| grammar | PC-1 303/305 · PC-2 637/639 · PC-3 0 · PC-4 0 · engine 297/305 (45 verbs) · PC-8 0.3213 — **Δ0** vs 23a; PC-6 max share 0.092943→**0.093103** honest | `tools/measure_grammar.py --set M21 --with-engine-flags` | PC-6 drift = suppressed atoms shrank the atom denominator; orphans unchanged {PHASE_IN}; PC-5 jitter only |
| catalog | **0/10 diverge — NO repin** | `tools/traces/catalog.py compare` | batch fixes never fire on the 10 trace seeds |
| games | **0 crash classes**, 100 decisive 48/52, mean_turns **33.49 — exact Δ0** vs 23a | `.venv/bin/python -m MTG_bot.core.executor.games --seeds 100 --pool all --deck-pairs-seed 1409 --turns 60` | Eot-exemption + suppression blast-radius-free on the field |
| lints | pyright **Δ0 new** (6 pre-existing Counter FPs, run_scenarios.py untouched lines); ruff **Δ0 NEW** | pyright CLI / ruff vs HEAD-worktree-inside-repo | HEAD already carries BLE001 (run_scenarios.py) + I001 (test_templates_b5c.py) — identical multisets; /tmp worktree silently loses ruff config (empty output ≠ clean) |

## 2026-10-02 (engine batch 24a — LIFE quantity lane + harness token lane; last two non-owner suspects closed)

| Item | Number | Command | Note |
|---|---|---|---|
| scenarios | **302/302 passed**; suspects 4→**2** files (chandras_pyreling + secure_the_scene, owner-blocked signatures unchanged), **0/2** | `tools/run_scenarios.py` [+ `--dir tools/audit/suspects`] | promoted peer_into_the_abyss (life-half = documented compiler gap, expect.life records print-drop) + treasure_token_activation (harness token-golden fallback + NEW expect.mana_pool lane; keyless-mint law stands) |
| suite | **2322 passed + 3 subtests, 0 failed** | `.venv/bin/python -m pytest MTG_bot/core -q` | +10 test_executor_r24a: QProp(controller,LIFE) read + controller-scope + order-free; (LIFE+1)//2 rounds up 20→10/13→7-lost/1→1; LOSE_LIFE end-to-end 20→10, p1-13→6; referent raises ×2 |
| grammar | PC-1 303/305 · PC-2 637/639 · PC-3 0 · PC-4 **0 (305 verified — LIFE field byte-stable)** · engine 297/305 (45 verbs) · PC-9 stable — **ALL Δ0** vs C5 | `tools/measure_grammar.py --set M21 --with-engine-flags` | PC-6/PC-8 standing FAILs unchanged |
| catalog | **0/10 diverge — NO repin** | `tools/traces/catalog.py compare` | engine additions never fire on the 10 trace seeds |
| games | **0 crash classes**, 100 decisive 48/52, mean_turns **33.49 — exact Δ0** vs C5 | `.venv/bin/python -m MTG_bot.core.executor.games --seeds 100 --pool all --deck-pairs-seed 1409 --turns 60` | additive lane invisible to games (no golden emits LIFE) |
| lints | pyright **Δ0** (6 pre-existing Counter FPs in run_scenarios.py — HEAD copy of the file reproduces exactly 6); ruff **Δ0 NEW** (identical per-file multisets, stdin-vs-HEAD) | pyright CLI / `ruff check` per file | scope flag: ability_tree.py touched OUTSIDE authorized list (additive QPropField.LIFE per C3 roadmap; needs ratification) |

## 2026-10-04 (BUGCATCH B3a — LOSE_LIFE journalled (LIFE_LOST); 3 D6 suspects falsified; §C flags)

| area | number | command | note |
| --- | --- | --- | --- |
| detectors | **0 hits / 20 seeds** (was 4 D1 HITs + 3 D6 suspects) | `.venv/bin/python tools/audit/detectors.py --seeds 20 --pool all --deck-pairs-seed 1409 --turns 60` | D1 fold synced to new LIFE_LOST kind (CR 118.5 own-kind law); seed 12: `20+0−0−3=17 final=17`; D6 repl=live-only (CR 614.3 ghost proof: attach_source self-detaches) + grant/lose source-side exempt (CR 611.2a); faults still fire |
| engine | **2350 passed + 3 subtests, 0 failed** (baseline 2345 + exactly 5 new pins) | `.venv/bin/python -m pytest MTG_bot/core -q` | pins in new test_executor_b3a_life_journal.py (row shape/clamp-delta/gain/damage-not-loss/fold); GAIN_LIFE was never silent — no gain row added |
| catalog | **0/10 — RE-PINNED** (was 3/10 diverge) | `tools/traces/catalog.py compare → repin → compare` | seeds 2/3/4 each = PURE insertion of one LIFE_LOST row: identical endings, n+1, first-diff is the new row; md5 372a5fd3007cb12b3428effcbca6fd1d |
| games | **0 crash classes**, 100 decisive 53/47, mean_turns 33.48 | `.venv/bin/python -m MTG_bot.core.executor.games --seeds 100 --pool all --deck-pairs-seed 1409 --turns 60` | A/B vs stashed-HEAD events.py byte-identical 53/47 — C6's 48/52 row is environment/historical drift, NOT B3a (journal lane flips zero outcomes) |
| grammar | PC-1 303/305 · PC-2 637/639 · PC-3 0 · PC-4 0 verified · PC-8 0.3213 — **Δ0** vs C6 | `tools/measure_grammar.py` | PC-6/PC-8 standing FAILs unchanged; compile lane untouched |
| bcs | 305 cards, scores **zero drift**; **8 collision_flags** set; 2 Liliana signatures remapped LOSE_LIFE→LIFE_LOST feed | `.venv/bin/python tools/audit/bcs.py` | branch_entanglement×2, keyword_x_consumer×2, replacement_x_ordering×2, single_fold×2 (design §C); B1's "LOSE_LIFE maps to LIFE_GAINED (B3 to falsify)" falsified — engine emitted NO row |
| lints | pyright **0 errors** 4 touched files; ruff **Δ0** | pyright CLI / `ruff check` per file vs HEAD worktree | audit suite 28→**34** tests (2 D1 fold + 4 D6 falsification) |

| packs | **327/327 green** (H1 hunt +14: 12-branch verdict packs + twins; working tree also carries parallel basri_ket_x_* pair packs) | `.venv/bin/python tools/run_scenarios.py` | 2026-10-04 H1 (HEAD 88b1966): 9 GREEN, 1 SUSPECT (`suspects/garruk_s_harbinger_branch01.json` red-as-intended on its library lane), 2 FALSIFIED (Radha TOP-only land-cast + auto-filler law; Demonic Embrace r20c CR 602.3 window) — engine/goldens untouched |
| engine | **2350 passed + 3 subtests, 0 failed** (unchanged) | `.venv/bin/python -m pytest MTG_bot/core -q` | 2026-10-04 H1 round, tools+knowledge-only diff |
| packs | **336/336 green** (H3 hunt +9; 10th pair SUSPECT held in `suspects/malefic_scythe_x_wildwood_scourge.json`) | `.venv/bin/python tools/run_scenarios.py` | 2026-10-05 H3 (HEAD 10d53c6): 9 GREEN + 1 SUSPECT — EtB X-counters on Wildwood Scourge visible to counters lane but ABSENT from P/T layer AND combat (probe deals 1 not 2; CR 122.1c/613.3d); 2 pack bugs falsified (Houndmaster printed 2/2; trample map = excess-PINNED-to-blocker polarity); `KNOWLEDGE/2026-10-04/08-hunt-pairs-r2.md` |
| engine | **2354 passed + 3 subtests, 0 failed** | `.venv/bin/python -m pytest MTG_bot/core -q` | 2026-10-05 H3 round: Δ+4 vs 2350 from a parallel session's tests; MTG_bot untouched by H3 |
| packs | **339/339 green** (H5: suspect `malefic_scythe_x_wildwood_scourge` adjudicated & promoted with corrected expectations power/toughness 1) | `.venv/bin/python tools/run_scenarios.py` | 2026-10-05 H5 (HEAD 68f9c85): hunt premise WRONG — Scourge printed 0/0 (corpus+golden+Scryfall); observed power 1 IS the EtB counter fold (supersedes H3 row's "absent from P/T layer" claim). BUT real bug fixed underneath: `cast()`/`cast_card()` never called `_on_zone_changes(entered)` → EtBState never stamped on CAST path (CR 614.1c); `KNOWLEDGE/2026-10-04/09-h5-etb-counter-fold.md` |
| engine | **2360 passed + 3 subtests, 0 failed** (2354 + 6 new H5 pins) | `.venv/bin/python -m pytest MTG_bot/core -q` | TestEtBSeedPTFold in test_executor_stack.py: X-seed/EtBState-seed fold, tapped-cast stamp, no double-count, X=0 dies, layer stacking |
| catalog | seed-3 attributed (Forgotten Sentinel now enters tapped when CAST — the bug, 1 new UNTAP_STEP TAP_STATE row, outcome same) → **repin 3848 entries/10 games**, post **0/10 diverge** | `.venv/bin/python tools/traces/catalog.py repin && … compare` | other 9 seeds byte-identical |
| games | **0 crash classes**, 100 decisive 47/53, mean_turns **33.48** | `.venv/bin/python -m MTG_bot.core.executor.games --seeds 100 --pool all --deck-pairs-seed 1409 --turns 60` | band-identical to baseline |
| grammar + lints | PC **Δ0** vs 2026-10-04 (only PC-5 jitter); pyright **0 errors** 2 touched files; ruff **Δ0** | `tools/measure_grammar.py` / pyright CLI / `ruff check` | engine fix is executor-lane only; compile lane untouched |

## 2026-10-05 (exploit / transfer audit — D8-D11 PoC)

| area | number | command | note |
| --- | --- | --- | --- |
| D8 opponent-error curve | WR vs pure-random **0.820**, robust **0.590**, exploit_gap **0.230**, curve A slope **-0.314**, curve B slope **+0.281** | `.venv/bin/python tools/audit/exploit/noisy_policy.py 25` | `eps=0` random, `eps=1` script; no production change |
| D9 seed rotation | fixed-seed WR **0.900**, unseen WR **0.500**, seed-keyed divergence **+0.400**, unseen-script control **0.875**, transfer-adjusted gap **+0.025** | `.venv/bin/python tools/audit/exploit/seed_probe.py 20` | seed-keyed lookup policy branch demonstrates the eval hazard |
| D10 hidden target source | opponent-hidden target candidates **58/12 games**, all `Volcanic Geyser` | `.venv/bin/python tools/audit/exploit/source_probe.py 12` | engine offers hand/library cards under `Zone(kind=ANY, controller=ANY)` for “any target” |
| D10 masked target ablation | opponent-hidden candidates masked **234/48 games**; scripted full-vs-masked WR delta **0.000**; hidden-biased full-vs-masked WR delta **0.000**; hidden choices **2** | `.venv/bin/python tools/audit/exploit/masked_target_probe.py 24` | current scripted floor does not monetize the leak, but trained policies must be gated |
| D11 blocker-model probe | model gain vs deterministic blocker **+0.031**, model gain vs random blocker **+0.000**, specificity **+0.031** | `.venv/bin/python tools/audit/exploit/blocker_model.py 16` | weak below recommended detector gate |
| D10 hidden target candidates (host, 12 seeds) | **leak_opp_hidden 116** /24 games (public 114), masked WR Δ +0.000 | `.venv/bin/python3 tools/audit/exploit/masked_target_probe.py 12` | pre-fix @4dbe864; post-fix gate = 0 (`2026-10-05/05-geyser-sweep.md` §0) |

## 2026-10-05 (R17-2 "any target" fix — post-fix gate)

| area | number | command | note |
| --- | --- | --- | --- |
| D10 post-fix | leak_opp_hidden **0** /24 games (was 116 pre-fix); candidates player_or_public 8, public 92, hidden 0 in all 4 lanes | `.venv/bin/python3 tools/audit/exploit/masked_target_probe.py 12` | 3-branch idiom FOr(Creature,Planeswalker,TYPE_EQ Player) over BATTLEFIELD/ANY; Player branch = IR-only discriminator |
| Goldens moved | **exactly 11** cards (all predicted ids), 294/305 byte-identical; 3 leaf diffs/card, all inside `.abilities` | `MTG_bot/core/compiler/refresh_goldens.py` + C1-form structural audit | snapshot `/tmp/golden_pre_geyser/` |
| Suites | core **2367 passed + 3 subtests** (2360 + 7 new pins); scenarios **339/339**; tools/audit **62** | `pytest MTG_bot/core -q` / `run_scenarios` / `pytest tools/audit -q` | pin file `test_geyser_any_target_pins.py` |
| Games 100 seeds | **0 crash classes**, 100 decisive, endings **56/44**, mean_turns **33.4** (max 55) | `.venv/bin/python tools/run_games.py --seeds 100 --pool all --deck-pairs-seed 1409 --turns 60` | mid-fix 2-branch widening crashed 10 seeds (Finishing Blow KeyError); 3-atom fix clears it |
| Grammar flags | PC-3 **0**, PC-4 **0**; PC-1/2/6/7/8/9/10 bit-identical to HEAD (PC-6/8 pre-existing FAILs unchanged); PC-5 jitter 0.249→0.296 ms | `tools/measure_grammar.py --with-engine-flags` | engine_supported 297/305 unchanged |
| Catalog seeds | after attribution **0/10** diverge; seeds 0/2 = hidden-target designations fixed, seed 7 policy re-selection reverted to original pre-fix journal | `tools/traces/catalog.py compare` | repinned post-fix |

## 2026-10-05 (Rung-1 counter window — post-fix gate)

| area | number | command | note |
| --- | --- | --- | --- |
| Scenarios | **347/347** (339 → +8 wave-7 counter packs) | `.venv/bin/python tools/run_scenarios.py` | zero regressions; 8 packs cancel×3/miscast×3/lofty/rewind |
| Core suite | **2379 passed + 2 subtests** | `pytest MTG_bot/core -q` | +2 vocab-gate pins in test_executor_rung1.py (file 12/12) |
| PC-7 honesty | **301/305, 46 verbs** unchanged | `tools/measure_grammar.py --with-engine-flags` | window adds no census inflation; Sublime stays excluded |
| Wave-7 census | 5 counter cards = **4 covered + 1 gate (Sublime, COPY) + 0 cohort** | `.venv/bin/python tools/audit/wave_builder.py --wave7 --lint` | `tools/audit/wave7.json` |
| Games 100 seeds | **0 crash classes**, 97 decisive + 2 cap + 1 draw, mean_turns **33.93** | `.venv/bin/python -m MTG_bot.core.executor.games --seeds 100 --pool all` | pre-fix run had 2 NEW crashes (seeds 16/96) — vocab gate fixes both |
| Window live stats | **19 WINDOW_OPEN / 10 PASS / 7 COUNTER / 2 KICKBACK (both PAY)** over the 100 seeds; offer vocab mean 2.11 max 3 | journal replay probe (same seeds, `journal.events` kinds) | arithmetic exact 19=10+7+2; random policy paid both kickbacks |

## 2026-10-05 (Rung-2 combat-instant window — gate battery)

| area | number | command | note |
| --- | --- | --- | --- |
| Scenarios | **355/355** (347 → +8 cw packs) | `.venv/bin/python tools/run_scenarios.py` | 347 pre-existing packs byte-identical via rig-side PASS fallback |
| Core suite | **2386 passed + 2 subtests** | `pytest MTG_bot/core -q` | +7 pins in new test_executor_rung2.py incl. Carrion Grub negative-power pin |
| Grammar flags | PC-1 **0.9934** / PC-2 **0.9969** / PC-3 **0** / PC-4 **0 diffs** — all Δ0 | `tools/measure_grammar.py --set M21` | no golden moved; compiler untouched |
| Games 100 seeds | **0 crash classes**, 98 decisive (51/47) + 2 cap, mean_turns **34.07** (was 33.93) | `.venv/bin/python -m MTG_bot.core.executor.games --seeds 100 --pool all` | first post-window run crashed seeds 10/73 `QConst:-1` — Carrion Grub's own -4/-4 blocked-trigger pushed effective power negative pre-damage; damage lane now skips the whole non-positive half-line (pre-existing latent bug, surfaced by window rng drift) |
| Window live stats | **84 WINDOW_OPEN / 28 PASS → 56 instants cast in combat windows**; Rung-1 counter lane 14 opens/7 PASS over the same 100 seeds | journal emit-probe wrapper, `games --seeds 100 --pool all` rerun | combat lane 6× the counter lane; determinism cross-checked (identical endings) |
| Catalog | repinned **4136 entries / 10 games**, post **0/10 diverge**, md5 `8b76978758164fddaf87fb2afdf7137c` | `tools/traces/catalog.py repin && … compare` | 10/10 diverged pre-repin as expected (window rng consumption) |
| E1 re-measure | vs-random **0.860** (was 0.820), robust band **0.590** UNCHANGED, exploit gap **0.270** (was 0.230) | `.venv/bin/python tools/audit/exploit/noisy_policy.py 25` | window WIDENS the gap — scripted window answers convert, random policy wastes opens; ledger correction row in 01 doc |

## 2026-10-05 — Training batch 0: executor env throughput (command: `.venv/bin/python -m tools.training.collector --bench --games 20 --pool all --workers 10`)
- workers=1: 1.28 games/s, ~101 decisions/s | workers=10: 7.0 games/s, 552 decisions/s (5.5x scaling)
- => 500k-decision curriculum pool ≈ 15 min wall-clock at 10 workers; episodes record-once/replay-forever.
- Memory at measure time: 9.1 GiB free (vLLM coding-engine reservation ~100 GiB held) — training S1 coexist window; S2/S3 need owner's engine-budget change. (2026-10-05 18:0x)

## 2026-10-05 — Training batch 1: BC floor verdict PASS (command: `.venv/bin/python -m tools.training.train_bc --device cuda`)
- gold_lines_all 119 rows acc **0.8235** — **+7.10 SE** vs random floor 0.4979, **+8.50 SE** vs null floor 0.437 (gate: >3 SE both) — p_one_sided ~2e-11. Doc 10.
- l1_certified **4/4**; train_items 0.9388; **holdout_items 0.2857 BELOW floor (−1.53 SE)** — memorization, not generalization; batch-2 volume is the fix.
- PointerBC 35,086,338 params (d512 L8), GPU peak **1.37 GiB** < 4 GiB budget, wall 239 s, best train loss 0.2254 @ ep204 (lr 3e-4, 250-epoch cosine, seed 1).
- Corpus join **119/119** gold lines; measured counts 133 scripted / 96 menu-ask / 119 gold (supersedes "121"). Handle-candidate↔obs binding 80.1%; unbound = library/hand-zone asks only.

## 2026-10-05 — STALL rule (CR 104.4b) in games loop (command: `.venv/bin/python -m pytest MTG_bot/core -q` ; `.venv/bin/python -m MTG_bot.core.executor.games --seeds 100 --pool all`)
- Synthetic ETB-shuffle-back loop: terminates turn **5** (vs cap 60), REPEAT_ROUNDS=**3**, lives [20,20], 1 STALL_BREAK journal row, determinism 3/3.
- Corpus pool=all 100 seeds: endings **identical** before/after ({p1: 51, p0: 47, cap-60: 2}) — cap games (seeds 53/91) are genuine grinds, fingerprint never repeats; 0 crash classes.
- Gates: pytest **2391** passed (+5 new pins); scenarios **355/355**; catalog compare **0/10 diverging** (no repin); PC-9 stable. Doc 11-stall-rule.md.

## 2026-10-05 — Monitoring batch: status board (commands: `bash tools/training/monitor_start.sh` ; `curl -s localhost:8788/health` ; `.venv/bin/pytest tools/training -q`)
- Board LIVE at http://192.168.1.108:8788/ — 3 panels (NOW / PROJECT SCOREBOARD / DETAILS), fresh-file reads per request, 30 s refresh; engine-guard + run_scenarios (0.62 s measured, packs tile live) cached 60 s.
- Gates: /health ok=true; page curl-renders 3 panel heads + LIVE banner mid-run ("heartbeat 4 s ago · phase live-smoke", pid-alive probe) → IDLE after; pidfile kill/restart clean (setsid, SID==PID); ruff Δ0 on 4 new files; pytest tools/training **33 passed** (7 new test_monitor.py).
- metrics.jsonl = single source (wandb_log.py always appends; wandb mirror iff WANDB_API_KEY; failure-guarded, never crashes trainer). Doc 13-monitoring-board.md.

## 2026-10-05 — Eval granularity: corpus v2 (commands: `.venv/bin/python tools/audit/puzzle_cert.py --dir tools/scenarios --out tools/audit/puzzle_corpus.json` ; `.venv/bin/python tools/run_scenarios.py` ; `.venv/bin/python -m pytest tools/audit -q`)
- **no_discrimination 52 → 0**; punish_inaction 67 → **104**; mean_random 0.4979 → **0.409**; items held at **119** (v1 backup `puzzle_corpus.v1.json`); broken_packs 0.
- **E_active** (null==0 ∧ oracle==1 ∧ 0.02≤random≤0.9 ∧ not reclassified, recomputed identically both corpora): **66 → 103**; SE(p=.5)=√(.25/E): 0.0615 → **0.0493** (3SE band 0.185 → 0.148). l1_ready stays **4** by construction (binary vocab floors random ≥ ~0.5; ≥40 needs chained-ask ladders — backlog A3).
- Reclassified (harness `eval_reclassification`, now incl. item-level `by_ask_kind`): **15 items / 14 packs** with mandatory reasons. Family split `eval_split.json`: 74 card families / 30 eval / 75 train + 44 eval items (sorted-index %5<2, no RNG).
- Gates: packs **355/355**, tools/audit **74 passed** (+2 reclass pins), core **2391+2** (engine untouched). Doc 15-eval-granularity.md; traps → PITFALLS.

## 2026-10-06 — Batch 2 v2-schema BC (commands: `.venv/bin/python -m tools.training.train_bc_v2 --device cuda --epochs 250 --resume tools/training/bc_s2_best.pt` ; `.venv/bin/python -m tools.training.elo random pass-floor tools/training/bc_s2.pt --games 120 --workers 6 --out tools/training/elo_s2_sanity.json`)
- gold_lines_all **0.7815** (119, +8.27 SE vs random floor 0.409); train_families **0.8933** (75, +8.67 SE); **eval_families 0.5909 (44) = +2.29 SE vs random floor 0.4205 → FAILS the 3-SE gate (p=0.017)**; verdict **NULL** (bc2_report.json gate_verdict); l1_certified 4/4.
- Batch1→2 delta **+3.82 SE** (holdout −1.53 → eval_families +2.29, each vs own floor): v2 schema measurably improves unseen-family generalization but not past gate.
- Closed-loop Elo sanity (120 games/pair): bc_s2 **−6.8 [−58.3, 44.8]** ≈ random; pass-floor +34.4 [−20.2, 83.8]. Teacher-forced accuracy does not compose → batch-3 re-diagnosis lead.
- best train loss 0.17172 @ ep191 of 250; vocab **380**; GPU peak 1.67 GiB < 4.0 budget; ~8.2 h wall across 9 segments under vLLM swap-thrash coexistence. Doc 16-batch2-bc.md.

## 2026-10-06 — Batch 3 (commands: tools/training/batch3_full.sh stage logs; eval = bc3_*_report.json gates.eval_families vs_random; Elo = tools/training/elo_s3_sanity.json seed-start 90001)
- arm A 35.1M params: eval_families 0.6136, +2.60 SE (FAIL gate)
- arm B 169,474 params: 0.6591, **+3.21 SE — first policy over the pre-registered 3-SE gate**
- dagger arm: 0.6591, +3.21 SE — NULL vs B (rollout never diverged from script; not off-policy)
- Elo: bc3_dagger_best +59.3 CI [6.8, 111.8] (first CI excluding random); pass-floor +42.5 CI [-9.4, 90.9]; 120 g/pair fresh seeds
- gates: tools/training 66 passed; core+audit 2465+2; engine untouched (0 files)
- BPTT cap audit 2026-10-06: max seq 1008 vs cap 1024 across batch2/3/dagger; encode() raises (never truncates); over_limit field live (command: pytest tools/training -q -> 67 passed)
- Batch 5 range sweep (command: run_full_memory -- batch5_sweep.sh; cause complete 315.44): margin PLATEAU 0.6591/+3.21SE at 0.17M..1.77M params, DEGRADES to 0.6136/+2.60 at 5.3M+; crossover ~2-5M at 75 gold lines; S0/S1/S2 fail IDENTICAL 12-item eval set (data-limited); S4 reproduces batch3-A exactly (0.6136, loss 0.18425)

## 2026-10-07 — Corpus v3: volume blindspot batch (commands: `.venv/bin/python tools/audit/puzzle_cert.py --rollouts 200` ; `.venv/bin/python -m tools.training.packrec_v2` ; `.venv/bin/python tools/run_scenarios.py` ; `.venv/bin/python -m pytest tools/training tools/audit -q`)
- 16 new packs (11 mechanics + 5 ladders, compiled-pool twins of the 12 blindspot mechanics) → items **119 → 153**; **E_active 103 → 133** (SE 0.0493 → 0.0434); **l1_ready 4 → 15**; punish_inaction **138/153**; no_discrimination 0; offenders 0; mean_random 0.359 (v2 backup `puzzle_corpus.v2.json`).
- eval_split v3: 74 families frozen + 3 new (Havoc Jester EVAL, Hobblefiend train, Spined Megalodon EVAL) = **77 fam / 32 eval / 45 train**, items 103 train + 50 eval.
- episodes_v2.jsonl rebuilt: **111 eps / 177 asks / 153 gold lines**; grounding 157/189 handle + 59/62 choose-digit; test_bc_v2 pins updated (153 / 157,189 / 59,62 / 76). BPTT max seq **1008 ≤ 1024** unchanged.
- Gates: packs **371/371**; core **2391+2**; audit **74**; training **71**. Engine untouched. Ask-kind grammar law + null=vocab[0] trap → doc 23 + PITFALLS.
- Sweep rerun 153 lines (run_full_memory -- batch5_sweep.sh; complete 469.69): ALL arms PASS incl 5.3M & 35.1M (0.68/0.70, +4.22/+4.51 SE, 50 eval items); big-model penalty gone; 10-item fail-core shared by all arms = 9 old blind spots + Havoc Jester #1 -> ceiling moved from data to ask-grammar observability
- Audit batch 2026-10-07: cluster-bootstrap gate margins 3.0-3.5 SE (all PASS still, iid inflated ~30%); FoR engine bug CONFIRMED (golden lacks PREVENT; 14 reclassification packs = suspects); ask census CHOOSE 172 vs ONE_OF 4 in 305 goldens (commands in /26)
- FoR triage batch 2026-10-07 (docs/27): FoR "engine bug CONFIRMED" SUPERSEDED (printed text = +1/+1 & protection, golden correct). Un-reclassified 4 packs (FoR, basri_x_FoR, waker_of_waves, spellgorger — old no-lane/no-ask reasons false); 14 reclass packs -> FAIL-REGISTERED 11 items {true-no-decision 7, null-degenerate-observable 3, engine-semantics-gap 1}; executor PROTECTION = block facet only (legality.py:1634-1686). Gates: packs 373/373, core 2391+2st, audit 76, training 77; corpus 155 items, l1_ready 16, punish_inaction 144, offenders 0, mean_random 0.3447 (tools/audit/puzzle_cert.py, 200 rollouts, 25.5s).
- CORRECTION 2026-10-07: FoR "engine bug" was a FALSE premise (printed text = protection keyword; DB cards.text verified) — real gap = PROTECTION keyword facets CR 702.16c (engine-semantics, owner class). Re-scored: bc3_B/dagger PASS->NULL (bootstrap 2.56); bc5 arms PASS both stats (3.09-3.46, p>=.9993); corpus v4: 155 items eval 51/train 104, fail_registered 11 {7 no-decision,3 null-degenerate,1 engine-gap}; tools/audit+training 153 passed
- v4 baseline (run_full_memory -- batch5_sweep.sh, complete 442.6): ALL arms PASS both stats; S4 35.1M LEADS (37/51, iid +5.75, boot +4.56); eval 51 items; margin trio + params/line in batch5_curve.json
- Component algebra 2026-10-07 (/30): 17 decision surfaces; silent sel-CHOOSE 170 vs asking ONE_OF 4; volume tiers may42/choose30/scry29/target34/one_of9/attack2/name2/ZERO for order-trample-policy-cw-counter-pay; k-of-n via ONE_OF loop + progress-token spec verified against frozen-vocab law

## 2026-10-07 — Tokenizer modal-asks batch (doc /29; commands: `.venv/bin/python tools/audit/puzzle_cert.py --rollouts 200` ; `.venv/bin/python tools/audit/make_eval_split.py` ; `.venv/bin/python -m tools.training.packrec_v2` ; `.venv/bin/python tools/run_scenarios.py` ; `.venv/bin/python -m pytest tools/training tools/audit -q` ; `.venv/bin/python -m pytest MTG_bot/core -q`)
- Search-pick CHOOSE->ONE_OF compiler pass (13 of 18 search-pick selectors; survivors 2xQConst(2) + 3xQUnbounded = registered k-of-n gap). Golden SelectorMode census CHOOSE **170 -> 157**, ONE_OF **4 -> 17**; 13 golden files, mode-only diffs verified 13/13. Modal "Choose two/three" openers landed with 0 pool hits (readiness).
- Corpus v5: items **155 -> 156** (new empath_big_game_pick.json), l1_ready 16, punish_inaction 144, fail_registered 11 unchanged, mean_random 0.3489; eval_split 77 fam / eval 51 / train **105**; episodes_v2 **114 eps / 185 asks / 156 gold lines**; test_bc_v2 pin 155->156.
- Gates: core **2393+2st** (2 new ① tests); packs **373/373** (grep upper bound 23 packs = pure overcount, 0 scripted answers needed); tools audit+training **153**.
- Event algebra (/32): 17 event kinds; direction encoded 2 ways (fields on 7 vs CONTROLLER_IS on 10); StepEvent 0 emits; HEXPROOF 6 goldens/0 enforcement; keywords 15/23 multi-consumer

## 2026-10-07 — k-of-n lands (T2; doc /31; commands: `.venv/bin/python -m pytest MTG_bot/core -q` ; `.venv/bin/python tools/run_scenarios.py` ; `.venv/bin/python -m pytest tools/audit tools/training -q` ; chain = `.venv/bin/python -m tools.audit.puzzle_cert --dir tools/scenarios --out tools/audit/puzzle_corpus.json` + `tools.audit.make_eval_split` + `tools.training.packrec_v2`)
- ONE_OF partition now asks `want` times over the shrinking menu (QConst exact clamped / QAtMost NONE-stop after mandatory pick1 / else raise); want>1 tag `one_of:<src>:<i>of<k>:<digest>` AFTER frozen kind prefix — bc_data site-kind law untouched, no new SITE_KINDS. `ExecCtx.one_of_picks` tuple; REST subtracts every pick; query legal_targets mirrors the loop.
- Byte-freeze PROVEN at episode level: re-cert chain rerun -> puzzle_corpus.json md5 f42aceb5… and episodes_v2.jsonl md5 d6228c7b… **identical to pre-change** (114 eps / 185 asks / 156 gold lines; corpus 156 items, mean_random 0.3489).
- Volume: pool census both sources = **0 castable k-of-n cards** (branch-opener 0, entity "choose two" 0, "choose one or more" 1 = Sublime Epiphany, engine_supported=False) -> `grep '2of2|1of2' episodes_v2.jsonl` = **0 lines**; /30's "k-of-n at volume 0" prediction confirmed. Seed = 27 new unit tests (test_executor_kofn.py 27/27).
- Gates: core **2420 + 2st** (= doc-29's 2393 + 27 new, zero fallout); packs **373/373**; tools audit+training **153**. Adversarial spawn blocked (depth limit) -> diff self-review only, flagged for review queue. T3 prerequisites registered in /31 (sel-CHOOSE merge incl. entity opener; flip 2xQConst(2) search-pick skip; QUnbounded until-quit shape).
- CORRECTION+audit 2026-10-07 (/34): corpus truth = 156 items, no_discrimination 1 (Fierce Empath), NOT 0 as /29 claimed; Garruk emblem dead-ask gold:false confirmed; legality triad divergence confirmed (binding/selectors/query 3 answers to one shape); commit e1ba62a message claim-scope error (md5 claim vs joint /29+/31 diff)

## 2026-10-07 — T3 household fixes (doc /36; commands: `.venv/bin/python -m pytest MTG_bot/core -q` ; `.venv/bin/python tools/run_scenarios.py` ; `.venv/bin/python tools/audit/puzzle_cert.py` ; `.venv/bin/python -m pytest tools/audit tools/training -q`)
- Legality triad ONE helper `ability_tree.count_semantics` (QConst exact n>=N never-clamped / QAtMost n>=1 k=min(N,n) / QAtLeast n>=N k=n / QUnbounded always; unresolved -> raise); binding TARGET unannounceable -> designate NOTHING (603.4; old crash path gone), selectors keeps documented 608.2c resolve-time lane, query ONE_OF QConst>1 min=max=N (INFEASIBLE past population — old min(want,n) clamp dead). +21 kofn tests, 2 stale pins re-grounded.
- Corpus: items **156 -> 157**, no_discrimination **1 -> 0** (empath_big_game_pick lanes fixed: begin_turn draw had eaten the decision — pack reorder + zone/hand lanes now falsify under skip), punish_inaction 144 -> 146, fail_registered **11 unchanged**, mean_random 0.3489 -> **0.3414**; garruk emblem dead-ask gold:false row GONE (honest scripted pick card:3 + battlefield_pt["Library 2"][1,1]; probed null/skip/random all fail).
- PT fold CHARACTERIZED order-dependent: [+1/+1,SET_PT 3/3]=3/3 vs [SET_PT 3/3,+1/+1]=4/4 (CR fixed-layer oracle = 4/4 both); pinned test_current_pt_timestamp_behavior; T4 layer-model owns the fix.
- Gates: core **2453+2st** (baseline 2420+2, +33 net, zero fallout); packs **373/373**; tools audit+training **153** (pins 156->157, grounding 157/189->163/195, rows_with_ground 78->79).

## 2026-10-07 — T4 P0 spec (docs /37 + docs/T4_*.md; commands: `.venv/bin/python tools/dump_unparsed_queue.py` ; `_VERB_ROLES`/event-slot extraction via `.venv/bin/python -c "from MTG_bot.core import ability_tree"` ; golden IR `MTG_bot/core/golden/M21/*.json`; oracle texts sqlite `file:MTG_bot/data/mtg_bot.db?mode=ro`)
- Verb partition: OPERATION 6 / POLICY 7 / EFFECT 36 (49); canonical slots = closed `_VERB_ROLES` table; zone-verb MOVE merge churn **39/305 goldens** (MILL 3 + EXILE 19 + DISCARD 17; DESTROY/PHASE_* excluded by ruling).
- Blindness audit: **BLIND 10 / PHANTOM 4** rows over 49 verbs+17 events+23 keywords+6 modes+17 sites; GAP LEDGER **26 rows = MIS-ENCODE 11 / COVERAGE-HOLE 13 (4 ask-channel) / ENFORCEMENT-ABSENT 1 (HEXPROOF) / OPEN 1 (PT timestamp)**.
- Significance criterion, 10 pool cards (Opt, Duress, Fabled Passage, Cultivate, Sublime Epiphany, Conspicuous Snoop, Teferi MoT, Basri Ket, Elder Gargaroth, Malefic Scythe): **30/31 clauses mapped = 96.8%**, 1 UNCOVERED (Snoop DERIVED-from-object ability menu, L-21); DB pool scan: 397 M21 cards, 0 sagas/adventures (L-25).
- Verdict: P1 proceeds without current-code fixes; PT-timestamp + E1 direction merges gated to T4 layer-model/P2.
- P0/T4-review 2026-10-07: 31 clauses/30 mapped (96.8%) 10 cards; gap ledger 26; 16 asks site:? fixed via SITE_KINDS+2 (kinds 17->19); tools 153 green

## 2026-10-07 — T4 P1a MOVE merge executed (commands: `.venv/bin/python -m pytest MTG_bot/core -q`; `tools/run_scenarios.py`; `tools/measure_grammar.py --set M21 --refresh-goldens`; KNOWLEDGE/2026-10-07/39)
- Verb partition shipped: OPERATION 6 / POLICY 7 / EFFECT 36 (= 49). Live dispatch set 46→43 (MILL/DISCARD/EXILE retired; V1 contract frozen untouched).
- Golden churn: **36/305 files × 1 line** (predicted 39 records/36 files — hit); full diff audited verb+slot-only.
- Gates: core pytest **2460 passed / 0 failed**; scenarios **373/373**; journal/replay 47; tools audit+training 153; episodes items **157 / no_discrimination 0**; eval split families 77 unchanged.

## 2026-10-07 — T4 P1b pick-enumeration + ask-pilot (commands: `/tmp/opencode/p1b/enumerate.py`; `tools/run_scenarios.py`; `pytest MTG_bot/core -q`; `tools/audit/puzzle_cert.py --dir tools/scenarios --rollouts 200`; HEAD-worktree baseline diff)
- CHOOSE census: **155 surfaces / 113 cards**; liftable core **22** (21 pack-mentioned); IS_SOURCE self-ref 69; cost-victim 26; anaphoric 37; k>1/search 31.
- Pilot allowlist 8 cards → honest runtime blast radius **5 packs, 0 silent changes**; goldens 8 files re-generated (verify diff 0).
- Gates: scenarios **373/373**; core pytest **2466 passed + 2 subtests** (5 new pins); tools **153**.
- Eval loop: items **157→164** (+7), families **77→80**, eval items **51→54**, gold_rows_with_ground **79→84**, candidate_ground **246/495** (was 229/474); no_discrimination **0**; fail_registered 11 unchanged.

## 2026-10-07 — T4 P1b stage-2 structural promotion rule (commands: `pytest MTG_bot/core/compiler/test_promotion_predicate.py -q`; `tools/run_scenarios.py`; take_decision probe predicate-off-vs-on; `tools/audit/puzzle_cert.py --rollouts 200`; `make_eval_split.py`; `packrec_v2`)
- Distinct CHOOSE surfaces **154** (stage-1 155 = emblem double-count); disjoint partition core 22 / self-ref 55 / referent 36 / cost 26 / k≠1 15.
- Structural rule promotes 22−8 = **14 live surfaces / 13 cards**; 8 FORCE_SILENT (L-27/28/29). Scripted-lane asks: still exactly **5 packs**; items/families/grounding **unchanged** (164/80/84/246-of-495), no_discrimination **0**.
- Goldens 305 full regen, verify 0-diff, 6 cards drifted. Gates (final): core **2471 +2st**, scenarios **373/373**, tools **153**.

## 2026-10-07 — T4 P1c hexproof enforcement (L-4) + fresh-eyes stack fix (commands: `pytest MTG_bot/core -q`; `tools/run_scenarios.py`; `pytest tools/audit tools/training -q`)
- L-4 CLOSED: `layers.hexproof_of` row oracle (None=bare | Filter=quality rows) + ONE `SelectorMode.TARGET` chokepoint in `enumerate_candidates`; direction CR 702.11b via `controller_of`, zone CR 113.10 battlefield/stack guard in legality.
- Stack MAJOR fixed (`_printed_stack_rows`): stacked spell sources rows from `binder.records[oracle_id]` — "hexproof from blue" no longer collapses to bare on the stack (pool cards: Sporeweb Weaver, Garruk's Harbinger — DB `text LIKE '%hexproof from%'` = 2 cards).
- Hexproof pins **13→18** (+5 stack tests, incl. falsified: fallback monkeypatched off ⇒ exactly red-target pin fails). Gates: core **2491 +2st**, scenarios **373/373**, tools **153**. TREASURE keyword stays decorative (token type-line word, zero executor consumers — decision).
- v5 re-baseline (complete 484.4, 54 eval): S0-S3 0.685-0.704 boot +4.07..+4.44 PASS; S4 35M 0.574 +2.88 NULL (overfit signature; seedvar batch running); v4->v5 small arms +1 SE (ask-visibility vocab)
- seedvar S0 (2026-10-07 23:4x, train_bc_v3 --arm S0 --seed {2,3} + main seed1): acc 0.704/0.704/0.704, boot +4.22/+4.19/+4.18 — small-arm variance ZERO at 110 train lines; S4 seeds pending (engine-off run armed 23:53, timeout law: 35M needs ~300s engine-off vs >2400s engine-on contention)
- v5 seedvar COMPLETE (2026-10-08 03:20, seedvar_sweep engine-off + main runs): S4 = 0.574/0.667/0.685 (2/3 PASS honest gate, spread 0.111); S0 = 0.704x3 (zero var); capacity claim: 0.17M-35M INDISTINGUISHABLE at 164 lines — data is the sole lever; 3-seed law binding for all model claims. STABLE fail-core (6 runs intersection): 10 items: Alchemist's Gift/Duress/Feat of Resistance/Garruk's Harbinger(a2)/Havoc Jester(a1)/Palladium Myr/Prismite/Solemn Simulacrum/Track Down/Traitorous Greed

## 2026-10-08 — Part 1 blindness repairs + Part 2 mana-color set (commands: `tools/run_scenarios.py`; `python -m tools.audit.puzzle_cert --dir tools/scenarios --out tools/audit/puzzle_corpus.json`; `pytest MTG_bot/core -q`; `pytest tools/audit tools/training -q`)
- Corpus v2 POST-repair: packs **373→377** (4 new mana-color packs), items **164→168** (+4 any-color asks, all on frozen EVAL sides; Prismite/Traitorous Greed/Meteorite), `no_discrimination=0`, `null_gt0_offenders=[]`, fail_registered 11 (1 engine-semantics-gap / 3 null-degenerate-observable / 7 true-no-decision), punish_inaction 153→157, l1_ready 18, mean_random 0.3306. eval 33 fam/58 items | train 47/110. Gates: core **2491 +2st**, scenarios **377/377**, tools **153** (pins moved 164→168, hs 180/212→174/206 = 84.9→84.5%, ch 66/69→67/70).
- **Harbinger ONE_OF filtering law**: the reveal-clause ONE_OF IS filtered by the printed clause (creature/Garruk-PW); single legal candidate ⇒ AUTO-RESOLVES with NO ask (phantom closed); menu = legal cards only. Old packs' 4-fake menus were pre-typed artifacts.
- batch6 (2026-10-08 10:20, wrapper sweep engine-off, 15/15 clean): S0/S1/S3 0.747, S2 0.736, S4 0.672 (range 0.121); boot +4.2..+5.1; 15/15 PASS honest gates; repair-gain +0.043 acc / +0.6 SE vs v5; stable fail-core now 6 items (4 = mana-color atom w/ zero train lines)

## 2026-10-08 — Volume wave: mana-color TRAIN twins + Harbinger/Gift-shape ladders (commands: `python -m tools.audit.puzzle_cert --dir tools/scenarios --out tools/audit/puzzle_corpus.json`; `python -m tools.audit.make_eval_split`; `python -m tools.training.packrec_v2`; `pytest MTG_bot/core -q`; `python tools/run_scenarios.py`; `pytest tools/audit tools/training -q`)
- Corpus v2 POST-volume-wave: packs **377→384** (+7 packs), items **168→177** (+9, all on frozen TRAIN sides; new assigned []), `no_discrimination=0`, `null_gt0_offenders=[]`, fail_registered 11, punish_inaction 157→166, l1_ready 18, mean_random 0.3285. eval 33 fam/58 items | train 47 fam/110→119 items. Gates: core **2491 +2st**, scenarios **384/384**, tools **153** (pins: join 168→177, hs 174/206→178/210 = 84.5→84.8%, ch 67/70→71/74, ground rows 84→88). TRAIN mana-ask lines **7→10** (atom now taught across W/U/B/R/G golds).
- Mana-atom TRAIN cards: Treasure (any-color {T},Sac golds W/U/B/U/**R/G**), Sanctum of Fruitful Harvest (add-X golds U/**B**), Temple of Malady (B|G). Empath ONE_OF: vocab order = pack card order; null picks vocab[0]. Trufflesnout Gift-shape: gold '1' (life), null '0' (counter); two falsifying lanes per item (life+power). Runner law: `world.life` sets BOTH seats; seat-1 combat needs `end_turn`+`advance_turn` first.
- Corpus v2 POST mana-atom closure (2026-10-08b, note 47): packs **384→386** (+2), items **177→180** (+3 train; Sanctum X=2 gold-G twin x1, Treasure two-source G-then-R pair x2), `no_discrimination=0`, null_score 0 all new, eval frozen 33/58, `new assigned []`. episodes_v2 **131 eps / 180 gold lines**. TRAIN mana-ask lines **10→13** (golds now B/R/U/G, never W). Gates: core **2491 +2st**, scenarios **386/386**, tools **153** (join pin 177→180 dated). Un-askable fail-register: fixed-color land mana offers (Temple {B} or {G}) raise no ask; M21 Gift keyword-choice has no train twin. Command: `.venv/bin/python tools/audit/puzzle_cert.py && tools/audit/make_eval_split.py && tools/training/packrec_v2.py`.

## 2026-10-08 — Batch-6 pairwise honest winrate (command: `.venv/bin/python tools/training/elo_batch6_run.py --games-per-pair 200 --workers 6 --device cuda` ; out tools/training/elo_batch6.json, doc 48)
- S3 vs S0: 0.554 [0.514,0.594] n=599 → ADMISSIBLE "bigger better" (d64→d256 pays)
- S4 vs S0: 0.492 [0.453,0.532] ; S4 vs S3: 0.489 [0.450,0.530] → INADMISSIBLE (d512 flat: eval-acc collapse = data-starved overfit, not capacity)
- 2400 games total, swap-paired, draws=0.5, seed=cluster bootstrap + pooled Wilson
- densified ladder (2026-10-08 13:00, 21/21 PASS): instability onset ~10M (range 0.017 -> 0.052-0.121), mean plateau 0.747 from 0.17M; era-confounded (168 vs 180 corpus) -> batch7 unified re-baseline queued
- batch7 unified (2026-10-08 14:35, 21/21 PASS, wall 3105s): 0.17M 0.776|0.000, plateau ~0.76-0.78 all sizes, 35M 0.736|0.069 only unstable; wave-gain +0.029; onset-10M (from /46) retracted as era confound

## 2026-10-08 — Batch-7 CI-grade pairwise winrates vs S0 baseline (command: `.venv/bin/python tools/training/elo_batch7_run.py --games-per-pair 200` ; out tools/training/elo_batch7.json; schema batch7-cluster-bootstrap-v1)
- 4 pairs x 3 training seeds x 200 swap-paired duels = 2400 games on the frozen unified 180-item corpus (eval_file binding episodes_v2.jsonl, no data regenerated). Law: admissible iff 95% CI excludes 0.5 (/26).
- Pooled (decisive Wilson + swap-paired-score cluster bootstrap, all agree):
  - S3a vs S0: 0.5426 [0.5025,0.5821] boot=[0.5325,0.555] n=600 -> ADMISSIBLE (S3a > S0)
  - S3  vs S0: 0.5442 [0.5042,0.5837] boot=[0.5375,0.550] n=600 -> ADMISSIBLE (S3 > S0)
  - S3b vs S0: 0.5417 [0.5017,0.5811] boot=[0.5350,0.545] n=600 -> ADMISSIBLE (S3b > S0)
  - S4  vs S0: 0.5453 [0.5052,0.5849] boot=[0.5275,0.5575] n=600 -> ADMISSIBLE (S4 > S0)
- Per-seed decisive winrates all 0.528-0.558 (no seed outlier); crashes<=3/200, draws<=1/200, seat_balance_ok all true.
- Read: on the unified 180-item corpus ALL four capacity arms beat S0 with CIs excluding 0.5, but the arms are INDISTINGUISHABLE from each other (~0.542-0.545 spread) — capacity 9.98M(S3a)->35M(S4) is flat vs baseline uplift; consistent with batch6 "plateau ~0.76-0.78 all sizes" (unified re-baseline, /48+). Note batch6's S4-vs-S0 0.492 (era-confounded corpus) is superseded by this unified measurement.
- OWNER POSITION 2026-10-08 (binding): capacity conclusions are REGIME-scoped to current complexity floor (80 cards/180 items/naive teacher); production line >=5.3M, 10-35M arms stay live in ladder; re-test larger nets at each corpus/atomics/eval escalation (owner expects required capacity to RISE with atomics depth, self-play, harder puzzles). The "35M pays nothing" reading is only true at THIS volume, complexity, and dropout=0.1 fixed (regularization confound logged, retest when data grows).
- REPLICATION 2026-10-08 18:20 (command: `.venv/bin/python tools/training/elo_batch7_run.py --games-per-pair 200` full 4-pair rerun after my /tmp-adapted variant contradicted the record): 2400 fresh games reproduce the 14:35 line EXACTLY on decisive scores — S3a 0.5426 [0.5025,0.5821] ADMISSIBLE, S3 0.5442 [0.5042,0.5837] ADMISSIBLE, S3b 0.5417 [0.5017,0.5811] ADMISSIBLE, S4 0.5453 [0.5052,0.5849] ADMISSIBLE; seat_balance_ok all true. Pitfall found: the official script's decisive-Wilson (wins/(wins+losses), draws/crashes excluded) vs my score-based Wilson (crash=pip loss, draws at 0.5) moved S3a 0.5426->0.4708 across 0.5 (5 crashes vs 280 wins flips the verdict direction) — record-keeping MUST state which CI is the law (decisive Wilson per /26); do not mix.

## 2026-10-08 — T5-F1 phantom-ask elimination (§10 charter F1; details /51)
- Ask-vocab census over the full pack corpus (command: `.venv/bin/python /tmp/opencode/phantom_census.py`, wraps DecisionStream.take; script is throwaway — recreate from /51 before reuse): PRE 1-candidate asks presented = 5 (attack x3, order x1, block x1) / POST **1-candidate = 0**, multi=315, silent autopicks=5; packs 386/386 green.
- Gates after fix: `pytest MTG_bot/core -q` = 2502 passed +2 subtests 0 failed (was 2491; +11 in test_executor_phantoms.py); `tools/run_scenarios.py` = 386/386; `pytest tools/audit tools/training -q` = 154 passed; ruff zero new findings.
- BC snapshot episodes_v2.jsonl: 214 ask rows, 0 single-candidate — post-F1 regenerations cannot mint phantom rows. Seed-73 corpus game re-pinned 56->50 turns (forced attackers no longer consume policy RNG draws; same loser, not STALL).
- [OWNER CORRECTION 2026-10-08 18:35] ALL batch6/batch7 Elo elapsed+winrates RETRACTED AS PROVISIONAL: duels ran with engine loading/active (GPU contention; logged 3-5 crashes/200 games; crash-convention even flipped S3a verdict between methods). Clean re-run required engine-off (CUDA ~15 min idle GPU) BEFORE any capacity-vs-data claim uses them. Accuracy-table findings (acc, gates, spreads) UNAFFECTED (sweeps ran engine-off).

## 2026-10-08 — Batch7 ADJUDICATED: clean re-run not required; plateau confirmed (command: adjudication of tools/training/elo_batch7.json -> tools/training/elo_batch7_adjudicated.json; stats re-executed via Wilson+exact binomial this session 19:2x)
- Integrity (executed): 2400 games = 2394 decisive / 1 draw / 5 crashes (0.2%, scattered S3a_s3×1 S4_s1×1 S4_s2×3); seat_balance_ok 12/12; engine-log exception hits 0.
- Vs S0 (n=600 decisive/pair, decisive-Wilson per /26 law): S3a 0.5426 [0.5025,0.5821] p=.041 | S3 0.5442 [0.5042,0.5837] p=.034 | S3b 0.5417 [0.5017,0.5811] p=.045 | S4 0.5453 [0.5052,0.5849] p=.030 — ALL ADMISSIBLE.
- Arm-vs-arm: max |z| = 0.13 (threshold 1.96) across all 6 pairwise tests; INDISTINGUISHABLE. Per-seed spreads 0.010-0.031, all 12 seed-runs same direction.
- Contamination worst-case: even adjudicating all 5 crashes as decisive S0 wins moves pooled wr ≤0.005; shared-baseline contention enters all arms identically and cancels in arm-vs-arm contrasts.
- Decision: /54 engine-ON retraction does NOT overturn 49; plateau at ≥5.3M CONFIRMED; clean rerun deprioritised (max shift <0.005). Supersedes: 49-blocked note, 3356 OWNER CORRECTION for the capacity conclusion (accuracy-table lines remain valid).

## 2026-10-08 — T5-B clause audit v1 (command: `python tools/audit/clause_audit.py`; gates: `.venv/bin/python -m pytest tools/audit -q` = 87 passed)
- 305 golden trees / 589 oracle clauses / 584 mapped = **99.15% zero-loss**, 5 residuals (NOT-ENCODED 3: Conspicuous Snoop conditional GRANT_ABILITY, Makeshift Battalion phantom KW:BATTALION w/o PUT_COUNTER leg, Transmogrify reveal-until loop; MISSING-EXPRESSIVENESS 2: rounding-policy "Round up each time", additional-trigger-count "triggers an additional time"; MISSING-ENCODING 0, BOILERPLATE 0).
- Ground truths executed: 5/5 add-any-mana clauses map; two-leg-removal-shape detector finds exactly {Angelic Ascension, Liliana Death Mage, Secure the Scene, Transmogrify}; keyword reminder lines map to Keyword atoms; Gadrak Treasure parenthetical stripped. Detail: 2026-10-08/56-clause-audit-v1.md

## 2026-10-08 — T5-G Gameplay eval v1: BC gameplay ≈ scripted baselines; ask lane has near-zero outcome leverage in the current rig (command: `.venv/bin/python tools/eval/gameplay_eval.py --games 120 --workers 4 --device cpu` -> tools/eval/gameplay_eval_v1.json; gate `pytest tools/eval -q` = 4 passed)
- Denominator truth: **0/386 scenario packs** run 2-seat full games (all steps/expect puzzle rigs) -> authorized fallback: games.py campaign rig, pool=engine (285 cards), paired seeds 1..120, seat-swap. Detail: 2026-10-08/57-gameplay-eval-v1.md
- bc7_S3_s1 vs RANDOM: 58W/4D(turn-cap)/57L/1crash, wr(dec) **0.504 [0.414,0.594]**; vs TEACHER(golden-script greedy): 61W/58L/1crash, wr **0.513 [0.424,0.601]** — both indistinguishable from 0.5 AND from each other; greedy never-pass script itself ≈0.51 vs random.
- Engine gate verified: illegal actions **0/4,970** provider answers; crashes 2/240 = ONE unique deal (seed 9, deterministic engine AssertionError, not policy-caused); auto-resolved asks 162/10,179 (1.6%).
- Caveats: provider lane = ASKS only (act side = shared seeded random driver, symmetric paired); 84% of full-game asks hit model sequence-truncation. Measurement power: ±0.09 at n≈120 decisive — a 3-pt ask-lane effect needs ~3,600 games/matchup (~2.7h CPU at measured 0.74 games/s). Per-ask accuracy results NOT retracted; winrate is a low-SNR readout of them in this rig.
- batch8 (2026-10-08 22:0x-23:0x engine-off, 21/21 PASS, driver batch8_sweep.sh): current-pipeline re-anchored curve S0 0.776|0.000 b+5.44 · S1 0.764 · S2 0.764 · S3 0.759|0.000 · S3a 0.764|r0.069 · S3b 0.718 · S4 0.730; plateau + variance-only-growth CONFIRMED post T5/F1/F2; supersedes batch7 numbers (corpus+pipeline moved since).

## 2026-10-09 — T5-G Gameplay eval v2 (full-agent): v1 null partly artifact; BC S3_s1 LOSES to greedy heuristic wr 0.391 [0.324,0.461]; dmgdiff@7 predicts win 79-85% (command: `.venv/bin/python tools/eval/gameplay_eval_v2.py --games 200 --workers 4 --device cpu` -> tools/eval/gameplay_eval_v2.json; gate `pytest tools/eval -q` = 11 passed)
- Mechanism: engine DOES ask attack/block/cw/damage-split decisions via provider (executor/__init__.py:1452/1514/1678, stack.py:652); v1's active_player attribution answered DEFENDER asks with the ATTACKER's policy (gameplay_eval.py:139) -> v1 null partly ARTIFACT. Real scripted layer = rig `RandomPolicy.take_acts` (games.py:586); named gap `query.legal_casts has no ask-site producer` fixed rig-side (PolicyActDriver menu asks).
- S3_s1 vs TEACHER-v2 (deterministic greedy, both seats full agents incl act layer): 75W/0D/117L/8crash, wr(dec) **0.391 [0.324,0.461]** (loses from both seats 35-61/40-56); mirror S3_s1 vs S3_s3: 86W/2D/103L/9crash, **0.455 [0.386,0.526]** ≈ twins indistinguishable over now-REAL combat. 0 illegal / 39,303 answers; 1,979 s / 400 games / 4 CPU workers.
- Leverage measured (was null in v1): final out-damage-diff **-3.71** vs teacher / -1.14 mirror (sign matches wr); round-7 damage-lead -> eventual-winner agreement **0.849/0.788** (metric sensitivity; largely structural). BC profile: attack DECLINE 0%, block NONE 0% (vs heuristic 52%), cw PASS 69-83%, act PASS 9%.
- Caveat: **90.5% of BC-lane asks hit obs sequence-truncation** (max_len=1024) -> C2 is a CURRENT-PIPELINE verdict (interface ceiling + policy), not proof policy-learning is bad; full adversarial gate on that conclusion DEFERRED (subagent depth limit — orchestrator must re-gate). Crashes 17/400 all engine/encoding defects (quantity.py:839 HAS_COUNTER x13, :331/:341 QX/QThisTurn x3, stack.py:1016 legal_casts-offers-unpayable x1; 5 deals crash both lanes). Detail: 2026-10-09/60-gameplay-eval-v2.md

## 2026-10-09 — T5-G DAgger wave v1: 60 BC-vs-BC games, 5,950 asks, pack lane 77/77 AGREEMENT (0 certified new labels), heuristic-only harvest 3,265 rows kept separate, choose 99.6% divergence exposes teacher blindness (command: `.venv/bin/python tools/eval/dagger_wave.py --games 60 --workers 4` -> tools/eval/dagger_wave_v1.json; gate `pytest tools/eval -q` = 16 passed)
- Teacher = DUAL (pack-lane scenario gold for (card,kind)∈{may,scry,attack} w/ null0 evidence only; heuristic probe always computed as demotion fallback + label-loss on agreement). Divergences 3,597/5,950 (60.5%) are HEURISTIC-class by construction; 332 eval-family asks leak-dropped; accounting exact (3,597−332=3,265 emitted).
- Pack lane transfer worked but found nothing to correct: 77 site-backed asks (may-fires), policy already matched the certified gold 77/77 -> episodes_dagger.jsonl stays the 131 original lines. Heuristic file (1,337 eps) is analysis material ONLY — merging it teaches the heuristic's biases (choose div 99.6%, block 60% vs BC block-NONE 0%).
- Emission law verified on the real output: 1,337/1,337 eps encode ≤1024, n_tokens == encoder seq len EXACTLY every episode, 0 overflows, 0 model errors, 3/60 engine-bare-AssertionError crashes (known class, 60), pre-crash asks harvested. 416 s / 4 CPU workers. Detail: 2026-10-09/61-dagger-wave-v1.md

## 2026-10-10 — Act-sense wave: scenario packs 386->398 ALL PASS; puzzle corpus 180->199 items (19 new, all null=0.00, no_discrimination=0, punish_inaction=True, 17/19 l1_ready); handle grounding 178/210->196/230 (84.8->85.2%), choose-digit 71/74->75/78, gold-rows-with-ground 88->98; eval split unchanged (frozen 47 train/33 eval families, new assigned []) (commands: `.venv/bin/python tools/run_scenarios.py --dir tools/scenarios` -> 398/398; `.venv/bin/python tools/audit/puzzle_cert.py` (200 rollouts/item) -> items=199 l1_ready=36 fail_registered=11 mean_random=0.2977; `.venv/bin/python tools/audit/make_eval_split.py`; `.venv/bin/python tools/training/packrec_v2.py` -> episodes=143 gold_lines=199; `pytest MTG_bot/core -q` = 2502+2st; `pytest tools/audit tools/training -q` = 164 after 3 snapshot re-pins; detail: 2026-10-10/62-act-sense-wave.md)
- batch8 overnight re-anchor (planned tonight, bc9_*: 7 arms x 3 seeds on 199-item act-sense corpus) supersedes batch8 once complete; batch8 = post-T5/F1/F2 anchor.

## 2026-10-10 — T5-E clause closure: residuals 3->0, clause audit 589/589 mapped = 100.0% zero-loss, all four classes 0 (commands: `.venv/bin/python tools/audit/clause_audit.py`; `pytest MTG_bot/core -q` = 2516+2st; `.venv/bin/python tools/run_scenarios.py` = 398/398; `pytest tools/audit tools/training -q` = 164; goldens verify_goldens=[] with 3 T5-E rewrites Battalion/Snoop/Transmogrify + 2 pre-existing T5-D Peer/Sanctum; correction: T5-C's "fixed" claim for the 3 residuals was runtime-only — commit 0daa6c2 touched no compiler code; detail: 2026-10-10/63-t5e-clause-closure.md)
- Snoop gate = ZONE_COUNT_GE with Zone.position=TOP + count=1 — quantity.py evaluator now honors position (pre-T5-E positioned zones silently counted whole zones; unpositioned corpus users byte-identical, 19 lane tests unchanged). Payload registered-inert StaticAbility mirror: 0 observable delta (398/398 byte-stable asks); dynamic card->ability-set grant stays in the gap ledger.
- Audit vacuity tripwire rewritten (n>0 impossible at legit zero): mapped_total==589 AND distinct-evidence vocabulary >40 (measured 73). Promotion census selfref 55->57, total 154->156 — attributed to exactly Battalion PUT_COUNTER + Snoop GRANT self-selectors, both stay CHOOSE in live.

## 2026-10-10 — E1 controller-direction merge lands: census event_direction_field 42/41 trees -> 0 (tripwire), both_styles 10 -> 0, controllers_is 89/63 -> 173/121 (sole direction encoding), zone seats reclassified zone_container_seat 376/165 -> 302/128, NEW battlefield_zone_seat_drift tripwire 0; gates `pytest MTG_bot/core tools/audit tools/training -q` = 2685+2st, run_scenarios = 398/398 (traitorous_greed trio byte-stable), clause_audit = 589/589 zero-loss; 91 goldens + 7 fingerprint pins re-pinned via builder recompute; corpus re-encode required (vocab unchanged); detail: 2026-10-10/65-e1-merge.md
- batch9 (2026-10-10, engine-off sweep bc10_*, 21/21 PASS): S0 0.759 | S3 0.764 | S3a 0.766 | S3b 0.757 | S4 35M 0.827 (spread 0.075) — first arm separation on the universal gate (S4-S0 +0.068, ~2.6 SE, suggestive); producer: batch9_sweep.sh over 199-line E1 corpus.
- E1 merged 2026-10-10 (commit 230def7): CONTROLLER_IS sole direction axis; census tripwires 0; clause audit 589/589 100%; act-sense wave 199 items/398 packs (commit 928e2fd); T5 zero-loss closed (0588ad9).
- v5 (2026-10-10, bc10_S4_s3, 200g): vs teacher 0.3105 CI[.249,.380], vs random 0.4737 CI[.404,.545] — puzzle-acc/gameplay DIVERGENCE proven; outcome meter now first-class gate. Producer: gameplay_eval_v5_bc10S4.json.
- search substrate (2026-10-10): fork 5.95ms | expand 61.4ms/option | rollout 536.8ms | 1.86/s/core, 37/s x20 cores (tools/search/rollout.py bench).

## 2026-10-10 — Search-data gen wave: mcts walk lands; 32-game run INFEASIBLE at full knobs in 90 min (commands: `.venv/bin/python tools/search/gen_games.py --games 32 --workers 16 --budget-min 90 --seeds 9100` -> 0 games finished (worker got 43% core at system load 24; ~60-100+ min CPU/game measured); mini k=1/N=1/cap3 = ~8 min CPU (probes/setup dominate, not k/N); RSS ~250-330 MB/worker; gates: tools/training 77p, tools/search 21p (after @timeout(1800) e2e markers - pytest-timeout SIGALRM lands in gen_game crash bucket under load), MTG_bot/core 2521+2st, scenarios 398/398; STALL-inside-probe walk-spin fixed; detail: 2026-10-10/69-search-gen-wave.md)
- search cheap-fleet (2026-10-10): 233.7 s CPU/game median (62.7-527.6) vs 60-100 CPU-MIN before; 16 games 12 workers 530 s wall -> 219 eps, 715 asks, 4290 rollouts, 0 crashes; rollout 73% / net_fwd 24% / probe 0.2% of CPU (probe cache hits 309/715=43% of asks, ~zero CPU saved - honest); top1_visit_share 0.475, mean|v-.5| 0.337, decided 90.3%, net_disagree overall 0.667 (choose 86% act 70% attack 13%); 7/16 STALL draws; all 219 eps re-pass verify_episode; pi round(x,6) verify-law bug + mid_act probe-cache stall race fixed (_resume_stalls mirrors engine); commands: `python tools/search/gen_games.py --games 16 --workers 12 --budget-min 60 --seeds 9100` (setsid!); detail: 2026-10-10/70-search-gen-cheap-fleet.md
- AZ-v2 (2026-10-12): C seeds 0.122/0.196/0.021 (100g vs T); D best s2: teacher 0.2234 CI[.171,.287], mirror-vs-pruner 0.3089 — one-shot distill dead-end confirmed (both variants < one-shot BC 0.31-0.39). Files: gameplay_azsel_s*, gameplay_az_final.json, episodes_search_v2.jsonl (1509 eps).

## 2026-10-12 — AZ-v3 build + smoke (detail: 2026-10-12/73-az-v3-built.md)
- AZ-v3 gen cost (v3 knobs k4/n10/cap40 greedy, net bc10_S3a_s2, 2 workers, cmd: gen_games.py --games 2 --seeds 20100 --workers 2 ...): 822.5 / 1050.4 s/game -> ~1.8 h/gen (64g/10w); ~2.4-2.7 h/gen total incl +15ep train + 100g gate -> under 3.5 h budget, no knob cuts.
- Resume-law smoke proof (cmd: train_bc_v3 --arm S3a --mix search --search-data eps_smoke --prefix azr --epochs 251 --device cpu): ckpt vocab 455 kept (stream rebuild 555, 338 -> <unk>), epoch 250 ran, best re-based 0.74047@250, gate PASS eval_acc 0.810, wall 743 s on 218 eps.
- Checkpoint probe layer (2026-10-12): bc10_S3a_s2 WR 0.0 (100g) vs s1 0.342 (40g), same batch, accs equal — probe law; az-v3 head = s2(0.0) by design-of-record, final bar 0.3927 (bc9_S3_s1).
- AZ-v3 FINAL (2026-10-13 02:47, azg1 200g): teacher 0.3093, vs S4_s2 0.5294, vs one-shot bar net 0.4346 — iterative AZ parked per stop-rule; one-shot BC 0.3927 remains gameplay frontier. Producer: az_v3 log + FINAL merged line.
- Era audit (2026-10-13): bc10_S3a_s1 vs bc9_S3_s1 mirror 0.349 (engine pool) / 0.438 (castable); era-arm (pre-actsense corpus today) 0.2591 vs teacher; FINAL-weights control 0.2947 — batch9-era gameplay regression CONFIRMED, act-sense exonerated; champion remains bc9_S3_s1 (0.3927). Producer: gameplay_probe_{bc9vbc10,poolctrl,finalw,era}.json.
- WR dashboard batch9 (2026-10-13 04:38, 100g vs teacher): S0 .283|S1 .313|S2 .240|S3 .220|S3a .000(collapsed-acc-seed)|S3b .343|S4 .232 — no capacity signal on outcome meter; gameplay frontier remains bc9_S3_s1 0.3927. Files gameplay_dash_*.json.
- DRIFT PROBE (2026-10-13, drift_probe.py): bc9_S3_s1 live-UNK 0.3355 vs train-era 0.0000 (every live ask >=1 UNK; OOV: new-era world-lane NUMBERS + expanded-pool card names). Era suspect (ii) CONFIRMED as input hole. Champion in-shadow form: 8-7-1 vs teacher, 8-8 vs random (48g) — champion is partly rig-era luck. episodes_champ.jsonl: 778 eps (2,424 asks).
- SHADOW-1 FRONTIER (2026-10-13, 200g): bsh_S3a_s1 teacher 0.4256 CI[.358,.496], champ-mirror 0.5288; s2 0.3660/0.4521; puzzle acc 0.643; live-UNK 0.0007 (vs 0.3355 champ-era). Frontier = bsh_S3a_s1. Files gameplay_shadow_s{1,2}.json.
- Digit-cure finals (2026-10-14 harvest): ntk_scratch 0.4308 teacher / 0.5053 mirror; transplant 0.3814/0.4946; frontier 400g bsh vs champ 0.4649 = parity. PLATEAU 0.37-0.43 declared sample-bound -> gen-big (256 games) launched. /78.
- NET-ROLLOUT COST GATE (2026-10-14, /79): on-policy root-net rollouts CPU = 90.9 s/searched-ask (k4 N12 cap40, bsh_S3a_s1, 1 thread, clean load) -> ~100 min/game (65.8 asks x 90.9s); 32-game IMPROVEMENT pilot STOPPED at gate, cold-feet-values map unmeasured. Cmd: root_search probe, /79 repro line.
- Volume law NEGATIVE (2026-10-14, /80): 5.9x shadow data -> teacher 0.3594 / mirror 0.4821 (within/below plateau band). Plateau binding constraint: capacity-or-labels, not volume/tokens.
- Improvement-labels NEGATIVE (2026-10-15, /83): bsi_S3a_s2 (512 search-label eps) mirror 0.3886 / teacher 0.3144 vs net-label clone parity 0.505 at 131 eps; mean_adv 0.10->0.034 with volume. Cheap levers exhausted (volume/tokens/labels); fork = capacity-window / RL / big-search / freeze-at-ceiling.
- Wave3 dose test (2026-10-15, /84): value-gold at 9.2% dose -> mirror 0.4872 / teacher 0.4051 = NEUTRAL. Improvement line legitimately closed at this budget. Plateau fork (R1 capacity-window / R2 RL / R3 freeze-pivot) = owner memo /85; recommendation R3+opportunistic R1.
- GENERALIZATION METER v1 (2026-10-15, /86): card-seetiness split of the 199-gate -> era gaps (fresh-held58 minus train141): bc9_S3_s1 +0.041 CI[-.23,+.31], bc10_S3a_s1 +0.024 CI[-.26,+.30] = NO detectable unseen-card penalty (resolution +-0.28 at n_fresh=58). Set-level split EMPTY: only M21 integrated (ZNR pending verified source). Contamination VERIFIED: 141/199 gate items are the era ckpts' own train rows; family filter is a no-op on live rollout files (bsh saw 77/80 gate cards in train obs; fresh half n=6 invalid). Cmd: python -m tools.eval.holdout_report --split card (json tools/eval/holdout_report.json).
- Frontier parity REPLICATED (2026-10-17, /89): OP2 0.4858 [.436,.536] @400g fresh seeds; pooled 800g ~0.475 vs champ. Expert-CLASS admission, surpass NOT claimed. Autonomy pattern: armed watcher fired nightly by itself.
- ZNR FIRST CENSUS (2026-10-18, /93): pool ingests 282 (270 cards + 12 tokens; 36 modal-DFC folded w/ back_face). Grammar first-touch (tools/measure_grammar.py --set ZNR): PC-1 0.1418 (40/282) / PC-2 0.2809 (184/655) / PC-3 0 / PC-4 N/A (no goldens) / PC-6 orphans 33 max ADD_MANA 0.26 / PC-8 0.0603 / PC-9,10 PASS; shape_gaps 1 (Nighthawk Scavenger power '1+*', class exhausted — pool's only non-digit P/T); UNPARSED 471 sentences / 241 cards / 311 distinct shapes — top: landfall-triggers 25, kicker-cluster ~57, enters-if 18+. BLINDSPOT registered: 71 modal-DFC BACK-FACE sentences sit OUTSIDE the 655 denominator (compiler never reads back_face). File verified authentic vs api.scryfall.com (/92); M21 unchanged (PC-4 0 diffs, report byte-ident, pool 305).
- ZND-1e KICKER PLAYABLE (2026-10-18, /100): CAST journal row 6-tuple w/ kicked column; WAS_KICKED reads turn-window CAST row (no row=False); legal_casts enumerates kick BOTH ways (CR 601.2b); honest gate flips EXACTLY Thieving Skydiver: ZNR engine-supported 268->267, deckable 268->267; packs 402/402 (4 real-ZNR kicker packs incl. CR-603.2 self-cast probe + Kitesail designation ask); core 2579 passed; M21 pins 301/281/285 + PC-4 0 diffs (305 files) hold. Cmds: tools/run_scenarios.py; pytest MTG_bot/core -q; tools/measure_grammar.py --set M21. Deferred: ask-lane kick? presentation; blink window caveat.
- ZND-2 LANDFALL (2026-10-18, /104): TEMPLATE-ONLY round per /101, grammar+engine frozen ⇒ M21 byte-safe by construction; b7 10th bucket (landfall head ZoneChangeEvent∧TYPE_EQ Land∧CONTROLLER_IS YOU + equip-EtB ×8; b4 enters-tapped artifact/enchantment widening, M21 census 0); register 478→**448** (−30: 20 landfall/20 cards + 8 equip + Murasa HAS_KICKER + Spare Supplies; 0 new, PC-3 0); PC-1 **0.2411** (68/282, +15 flips) PC-2 **0.3829** (278/726) PC-6 share 0.2062→0.1667 PC-8 0.0745→0.1028 — all 3 pre-registered bands HIT; pre-commit gate withdrew a §10 PHANTOM the implementer shipped (zero-consumer named kicker head + its defending test — /98 T4 precedent); FM5 origin-independence probe (GY/exile→BF fire, exits silent) now 6 executor tests; measure_grammar dedup guard fixed (returned early while printing "row appended" ⇒ stale 0.1879 headline; now replaces the day's set section — a skipped write must not report the write). Cmds: tools/measure_grammar.py --set ZNR; pytest MTG_bot/core -q; tools/run_scenarios.py. Residual 448: party 35 → ZND-3, BFACE 71 → face Type-1, + /101 defers.
- ZND-1f KICK MODEL-VISIBLE (2026-10-18, /103): candidate token `card:N+kick` additive on menus/spans/recordings; kicked span = referent row + kick + KickerAbility cost words (static tree); menus present BOTH priced rows base-first (un-kicked dedupe regression dies); M21 corpus double-encode diff = 0 (11,032 eps, vocab 1,094, cmp on build_vocab_v2+encode_episode_v2 before/after); packs 403/403 = 402 HEAD + sibling b7 untracked landfall pack; suites 1955 passed (core+tools excl. compiler) + 896 passed (compiler, sibling-live) = 0 failed; rig double-run byte-ident; pyright 0, ruff 0 new. Cmds: pytest tools/eval/test_znd1f_kick_visibility.py -q; tools/run_scenarios.py; pytest "MTG_bot/core tools -q --ignore=MTG_bot/core/compiler"; /tmp/opencode/znd1f_reencode.py+cmp. RandomPolicy needed NO edit (ZND-1e already casts row.kicked — map item (d) stale).
- ZND-1g X-KICKER PAYABLE (2026-10-18, /105): X-valued kicker priced — spell_castable folds kicker {X} at the cast's x (CR 107.4a ONE announcement: Skydiver's kicker-X IS its spell-X; printed cost {1}{U} has no X); adopted X-law = engine's standing CR 107.1 zero-floor, X=0 kick LEGAL+pays-zero+marks-kicked (printed "X can't be 0." UNPARSED → unenforceable, registered not side-channeled); frame/CAST row journal the declared X (kicker-aware 14c zero-floor); legal_casts X-kicker both rows at base price (X=0 witness), priced row vanishes on too-big x (shortage, never raise); WAS_KICKED window read proven on the X-kicked row; flip verdict NO — 3 unparsed sentences = the effect gap (X-bound atom; gated-ETB TARGET menu with mana-value≤X (QX-in-filter: the blocker); subtype-conditional attach tail); ZNR engine-supported UNCHANGED 267 (compiler frozen); packs **404/404** (+znr_thieving_skydiver_xkick, double-run identical); core+tools **2860 + 36st** (full run, no split); M21 PC-4 0 diffs (305 files, report delta timing/git_head only); pyright 0 new, ruff delta 0. Cmds: pytest MTG_bot/core/test_executor_games.py::XKickerLaneTest -q; tools/run_scenarios.py; pytest MTG_bot/core tools -q; tools/measure_grammar.py --set M21.
- ZND-2f BACKFACE COMPILE HALF (2026-10-18, /106 spec, /108 landed): BackFace Ability node + tolerant compiler face lane (recursive `_as_single_faced` compile, face appended last, residue in new `back_face_unparsed` — front register & PC-1 formula untouched /96); uplift EXACTLY +61 (25 enters-tapped + 36 add-mana): PC-2 **339/726** (0.4669), PC-1 68/282 unchanged, PC-6 share 0.1667 / PC-8 0.1028 unchanged (face verbs TAGGED in backface_summary, never merged), 10 pay-3 sentences = BFACE register rows (ZND-2f2), census 36 faces/71 sentences/61 covered/31 whole; phantom defenses skip=BackFace in games produces_mana + engine_support folds (both-direction tests + source pins); M21 byte-identical (0 non-volatile diffs, no backface key); corpus re-encode diff 0 (19 corpora v1+v2); `pytest MTG_bot/core tools -q` **2877 passed 0 failed**; new test_backface.py 17 tests; pyright 0 / ruff delta ≤0 all touched. Caught+fixed: gap-card face census honesty regression (shape-gap faces now contribute all sentences as BFACE rows — /93 honesty law). Cmds: tools/measure_grammar.py --set ZNR/--set M21; pytest. Residual: pay-3 ×10 → ZND-2f2; face PLAYABILITY owner-gated (folds = re-entry points).
- ZNR FUZZ B1+B2 LANDED (2026-10-19, /117): blocker asks gated on Kuhn-CR-completability (seed 1269 menace-stranding: word offered iff pair-legal AND whole-assignment completable; NONE same test; silent skip + mandate salvage; menace-aware MANDATE check; final 702.113 raise stays as invariant) + MDFC face-cast typed refusal FaceCastAbsentError + guard waiver w/ ledger (seed 1715 Beyeen Veil via Coveted Prize free-cast; front SpellAbility gap = sibling compiler proposal, /106 class). Fuzz 500/500 **crashed=0 sigs=0**; repros 1269/1715 zero-raise; core **2698 passed** (+1 fail = sibling WIP B9 registry, compiler-owned); packs 410/410; blockers pins 23/23, dfc pins 6/6 (new file); pyright 0, ruff Δ0. Cmds: tools/eval/znr_engine_smoke.py --set ZNR --games 500 --deck-pairs-seed 201019; --repro 1269|1715; pytest MTG_bot/core -q; tools/run_scenarios.py.
- CAST PAYABILITY LEGALITY FIX (2026-10-19, /125): optional_offer CAST gate now folds the SAME build_payment_plan as stack.py:1093 (offer/runtime identity; CHOOSE prices stand-in slice sorted[:count], bindings all(); TARGET/ONE_OF any-payable r18a; EMPTY Cost role = CR 498.2 waiver always-payable; real Cost REPLACES printed; unpayable ⇒ skip-only, never phantom ask; raise@1093 stays LOUD). Trigger: M21 eval seed 777003, Conspicuous Snoop CHOOSE∞ LIB-TOP named Battle-Rattle Shaman {3}{R} on pool {R:3}. Audit: engine M21 pool 8 CAST atoms = 4 EMPTY-Cost waivers (Chandra ×3, Idol) + 4 printed-cost; no hidden riders; Snoop compiler cost-role question registered. Gates: 11 new pins; repro seeds 777002–3 crash=None; gate eval 40g seeds 777002–41 workers 4 **0 crashes**; core **2793 passed + 36st**; packs **415/415**; fuzz M21 300g deck-pairs-seed 201019 **0 sigs** (55.8s); pyright 0, ruff Δ0. Cmds: pytest MTG_bot/core -q; tools/run_scenarios.py; tools/eval/znr_engine_smoke.py --set M21 --games 300 --workers 4 --deck-pairs-seed 201019 --recheck 5; tools/eval/gameplay_eval_v2.py --set M21 --policy-a tools/training/bsh_S3a_s3_best.pt --matchups teacher --games 40 --device cpu --pool engine --workers 4 --seed-base 777001.
- ATOM ONTOLOGY CENSUS (2026-10-19, /126): 546 cards (M21 293/305 w/ abilities 0 gaps; ZNR 253/282 1 gap), 1168 abilities, 469 STRUCT sigs, 21 fusion-candidate clusters (enum-only STRICT variance = GOOD generalization), Selector 40 branchings (CHOOSE 174 / TARGET 141 / ALL 132 / ONE_OF 25 / REST 10), Seq>=2=126 Seq[1]=0, 31 verbs w/ target/filter roles (MODIFY_PT 79, MOVE_ZONE 66, GRANT_ABILITY 61), FAnd order-divergent groups 2, single-child FAnd anomalies 2 (Dauntless Survivor, Negate). Gate rounds 1-2 (adversarial): N5 zone∪zones alphabetical fold REJECTED — primary-zone-keyed lanes verified (selectors.py:428/484/705/754, verbs.py:247) -> gated R0 schema fold to single zones-set field; Cost.parts sort gated R1b behind planning determinization (legality.py:721/755 order-keyed); E1-merge (2026-10-10 /65) already unified direction — spec F1 corrected to RESOLVED+residual re-audit. Cmd: .venv/bin/python tools/audit/ontology_shape_census.py -> reports/ontology_census_2026-10-19.json.
- ATOM ONTOLOGY R1a EVIDENCE (2026-10-19, /126): N-v4 byte-delta M21 122/305 + ZNR 80/281 records (fand_order 117+72, or_order 9+6, flatten_single 0+2, kwds_sort 2+0, colors_sort 1+0), 122 M21 goldens flagged, idempotence+content-preservation PASS, 0 exceptions; V1′ single-source CLASSIFY = 25 container fields (24 tuple + 1 frozenset), exit 0. Cmds: .venv/bin/python tools/audit/atom_sortdelta.py; .venv/bin/python tools/audit/atom_field_table.py.
- CAST PAYABILITY GATE ROUND (2026-10-19, /125 round-2): COMMIT-NO-GO blockers B1/B2/B3 fixed at ONE choke point — selectors.role_handles CAST branch threads query.cast_designee_ok (carrier∧payable ∨ typed /115 face-gap) INTO resolve_selector pre-slice (offer gate + runtime = SAME predicate, §10 menu==acceptance); TARGET/ONE_OF slot clamps (min/max untouched); ∞/population lanes CLAMP lands (HoF/Catalyst repros complete: spell cast, lands stay, no raise); finite CHOOSE stays POSITIONAL (land-first = skip, no re-pick); zero-carrier + filter-omission CAST gaps register LOUD (dedupe/count ledger, 2 compiler handoffs: Radha PLAY_LAND→CAST, Catalyst FAnd(()) admits non-spells); BackFace-only = cast_run_gap NOT a clamp member (typed FaceCastAbsentError keeps its guard-ledger contract — this round's caught-and-fixed silencing regression). Gates: B1/B2 verbatim repros /tmp/opencode/b1_repro.py ALL-COMPLETE; M21 teacher 40g seed-base 777001 **crashes=0**; NEW ZNR teacher 40g same seed-base (269-card pool) **crashes=0**; core **2800 passed + 36st 0 failed** (F3 annotation, round 3: 2800 was the COLLECTED count of the 4-file-scope clean-tree simulation; the delivered dirty tree collects 2819 with sibling tests — annotation, not renumbering); packs **415/415** golds unchanged; fuzz M21 300g seed 201019 recheck5 **0 sigs** (55.3s); pyright **0**, ruff **Δ0**; pins 18 (+dfc/r23a = 40 green). Cmds: pytest MTG_bot/core -q; tools/run_scenarios.py; tools/eval/znr_engine_smoke.py --set M21 --games 300 --workers 4 --deck-pairs-seed 201019 --recheck 5; tools/eval/gameplay_eval_v2.py [--set ZNR] --matchups teacher --games 40 --workers 4 --seed-base 777001.
- CAST PAYABILITY RE-GATE ROUND 3 (2026-10-19, /125 F2): finite-CHOOSE CAST made POSITIONALLY HONEST at runtime — slice RAW first, check the HEAD (gate's p1_probe falsified round 2's population pre-slice clamp: it silently RE-PICKED the next payable spell, violating the "first count of Handle-sorted candidates" laws in verbs.py/query.py docstrings which are TRUE again); failing head = refusal (no cast, no pool spend, ledger row "finite CAST head cannot execute: <Name> (<cannot be paid | not a SpellAbility carrier>)", never raise, never re-pick, mirrors _clamp_cast_target_slot include_zero = CR 601.2e rules answer); ∞/ALL/ONE_OF/RANDOM population clamps KEPT (legal-set menus; RANDOM draw-bias over the clamped pool documented on the branch + pinned); TARGET-bound clamp-drop now LEDGERED ("CAST TARGET designation left the legal set", was silent contrary to its own comment; CR 603.3-mode drop unchanged). New public lane: register_cast_gap(executor, host, note) + cast_refusal_note (names+reasons via cast_carrier). Pins 18→23 (positional refusal + land-head carrier refusal + clean-head cast + TARGET ledger + random-bias); p1_probe prints "NO divergence: runtime refused too". Gates (fresh, pycache-clean): pytest MTG_bot/core -q **2824 passed + 36st 0 failed** (round 2's 2800 was the 4-file-scope sim; delivered tree collects 2819 + 5 new pins); M21 teacher 40g seed-base 777001 **crashes=0**; ZNR teacher 40g same seed-base **crashes=0**; packs **415/415**; fuzz M21 300g seed 201019 recheck5 **0 sigs** (57.4s); pyright **0**, ruff **Δ0**. The re-gate's red regate_core.txt battery (27 failed) was the stale-__pycache__ F1 incident — clean-slate rerun green. F3: /125 headline "NO selectors edits" corrected to the truth (~150 lines in selectors.py); round-2 NUMBERS line annotated (2800 = sim scope), not renumbered.
- R0 ZONE-FOLD PRE-REG (2026-10-19, /129): consumers 395 prod sites (263 CONSTRUCTIONS: 239 positional-slot-4, + KEYED-LOSS compiler.py:1050 silently drops zones) + 172 test sites (163 selector asserts/16 files re-pin); KEYED lanes 6 — NEW L6 legality.py:947 CostDiscard-HAND gate pop 10; L3/L5 singleton-predicates (∃ resurrects r21a); corpus 549 selectors, twins 10 (M21), neutral 48; byte-delta MEASURED M21 219/305 + ZNR 108/281 (zone_key_removed universal; ZNR-0 hypothesis REFUTED), content-preservation PASS 0 fails, 11-item falsifier battery. Cmds: tools/audit/r0/{r0_scan,r0_arg4,r0_type_tests,r0_build_inventory,r0_corpus,mk_sortdelta_r0}.py -> reports/r0_{consumer_inventory,sortdelta}.json.
- R0 ZONE-FOLD LANDED (2026-10-19, /129 execution): Selector zone+zones -> ONE zones set field (non-empty, deduped, canonical-JSON-sorted; C2 referent=(ANY,ANY); from_dict fails LOUD naming "R0 zone-fold" on stale zone-key bytes — no silent migration). Mechanical AST migration 572 constructions, residual 0 positional-4/zone-kw; 6 KEYED lanes rewritten (L1 matched-zone extraction, L2 ∃-PLAYER kept-correct, L3/L5/L6 SINGLETON predicates, L4 one-zone BOTH-conjuncts via production graveyard_sweep_shape()); compiler.py:1050 rebuild carries zones+referent. Goldens re-baked EXACTLY 219/219 (git shows 219 files; 86 untouched byte-identical; verify_goldens 0 diffs; zone-leaf multiset preserved 305/305). Falsifier battery MTG_bot/core/test_ontology_r0.py: 23 tests + 17 subtests, executor-observed (ONE_OF graveyard answer, trio no-blind-draw, Magmutt designation stands, Waker window, Unsub STACK+BATTLEFIELD ask) with naive-∃ red-first divergence pins on every lane. Gates: core 2853 passed 0 failed; tools 294 passed (V5′ census test re-pinned to merged R0 census); packs 428/428; fuzz ZNR 40/40 0 sigs; conformance errors=0 warns=7; census 469 clusters Δ0, zone twins B 2->0 (reports/ontology_census_2026-10-19_r0_post_full.json new; baseline regenerated); scenarios double-run BYTE-IDENTICAL; PC anchors Δ0 — M21 PC-4 0, PC-6 4/.1265, PC-8 .3213, PC-5 .359->.326 ms; ZNR PC-1 .3830/.5496, PC-6 26/.1547, PC-9 stable. Deviations: 6 twin asserts needed hand set-membership re-pins (canonical order), test_ontology_conformance R0-census merge added, r3b fingerprint 856e64->64d3fa re-baked. Cmds: pytest MTG_bot/core tools -q; tools/run_scenarios.py; tools/eval/znr_engine_smoke.py --games 40 --out /tmp/opencode/r0_fuzz_znr40.json; tools/measure_grammar.py --set M21|ZNR; tools/audit/ontology_shape_census.py --cap 4000 --out reports/ontology_census_2026-10-19_r0_post_full.json.
- R1 CAPACITY NEGATIVE + LEDGER COMPLETE (2026-10-20, /133): S4 35M x3 seeds, engine-off window, champ_big long-epoch — mirror vs S3a clone 0.426/0.418/0.426 (engine-controlled law), vs teacher 0.332/0.325/0.330 (drift-riding, not adjudicating); eval_acc frozen 0.707 epoch0->11 (train_loss 0.005 = memorization). Files: tools/eval/gameplay_r1_s{1,2,3}.json, r1c_S4_s*_report.json, /tmp/opencode/r1_window.log. Four-axis ledger: tokens /78 + volume /80 + labels /83 + capacity /133 ALL NEGATIVE => imitation capped at greedy-teacher class; binding constraint = label information; RL fork memo in /133.
- T-G5 AUDIT (2026-10-20, /135): cross-set ELO ladder NOT hostable (M21-locked supply plumbing, vocab-relative puzzle meter => WR is the only cross-set verdict meter); gameplay_eval_v2 hosts T-G1 matrix today (mirror lane + --set + rotated seeds, /123 recipe); minimal fix ladder 5 steps.
- T-G7 DATUM-1 (2026-10-20, /135): 3x S4 cuda trainings in parallel engine-off = wall_s 3015.8/3016.0/3016.0 — parallel factor ~3.0 (perfect scaling); constraint was never GPU compute at this size class, engine-off windows are the throughput key.
- CURRENT-ENGINE ANCHOR (2026-10-20, /134 precond): bsh_S3a_s1 vs teacher 400g seed-base 991001 = 0.394 [0.347,0.442], 0 ill, 1 draw (draw-detector baseline updated 1/400). Era drift: -3pts vs Oct-13 0.4256 anchor (inside old CI, point moved) — reconfirms cross-era anchors never adjudicate; pilot verdict axis is the mirror. File: tools/eval/gameplay_anchor_bsh_cur_engine.json.
- RL-PILOT PRECOND 2 SHIPPED (2026-10-20, /134): sampling collect (gameplay_eval_v2 --rl-collect/--sample/--rl-seed, BcAsk.sample_ask) + off-policy audit tools/training/rl_logprob_audit.py; deterministic 2g demo (bsh_S3a_s1 vs teacher, rl-seed 7) = 100 asks/2 episodes, cross-process audit max|Δ|=0 mean|Δ|=0; tampered/deleted logp RAISES naming /83 trap; found+fixed the choose-digest-stash cross-process trap (pre-fix 31/100 asks mismatched). Commands: module docstrings; tests tools/training/test_rl_collect.py. KNOWLEDGE/2026-10-20/137.
- RL-PILOT TASK B SHIPPED (2026-10-20, /134): REINFORCE trainer tools/training/train_rl_v1.py — batch-mean outcome baseline (crash=loss), frozen-anchor KL (β=0.1, ceiling 0.05 reported), entropy 0.001, SGD lr 1e-5 clip 1.0 (NOTE-1: Adam would amplify the noise floor and break the zero-variance discriminator); episode rows now carry per-seat outcome; F4 sidecar keys shipped. Instrument smoke (2g win/win rl-seed 13, 48 guarded asks): grad 6.2e-4 regularizer-only, |Δlogp| 2.3e-9, Rvar 0 ⇒ flat PG exactly as baseline law requires; zero-variance grad EXACTLY 0 + win/loss positive control >1e-4. Cmds: tools/training/train_rl_v1.py --help; pytest tools/training/test_rl_train.py -q (6 tests). KNOWLEDGE/2026-10-20/138.
- R2 DAMAGE-FOLD LANDED (2026-10-20, /140 exec /142): CombatDamageEvent DELETED (class+6 tables+matcher branch+_COMBAT_EVENTS); 3 cards folded (Jeskai Elder, Feline Sovereign [M21], Nimble Trapfinder [ZNR]) to DDE{QUnbounded, FAnd(()), source=old-filter VERBATIM, combat=True}; convergence Jeskai==Harbinger bytes VERBATIM; D13 split over-fire ACCEPTED (pin=2 fires, ZND-8 open); KIND_COMBAT_DAMAGE journal emission survives unsubscribed (BREAK-2). NEW gate binding.py _damage_designation_is_event_borne: DAMAGE-row 16a target pre-bind lifts ONLY for event-borne TARGET populations (Feline/Incinerator; Brash echo keeps dealer read). Census: 13 damage nodes post-fold, CDE 0. Goldens changed EXACTLY 2/305 oids. Gates: battery 15/15 (9 red-first); core 2878 + tools 285, 0 fail; packs 428/428 double-run byte-identical; fuzz ZNR 40/40 0 sigs; conformance errors=0. Cmds: pytest MTG_bot/core tools -q; tools/run_scenarios.py; tools/eval/znr_engine_smoke.py --games 40 --out /tmp/opencode/r2/fuzz. COMMIT LAW: 2 re-baked goldens MUST land same commit as code.
- R3 LANE LEDGER + LIFT DERIVATION (2026-10-20, /141 phase 1): committed generator tools/audit/r3_lane_ledger.py regenerates reports/r3_blindness.json BYTE-IDENTICAL (cmp PASS). CHOOSE-node lanes: L-Silent 161 / L-B 27 / L-Other 5. LIFT-NOW per /141 §6 three rules = **14 cards / 14 nodes** (5 atom-pair CHOOSE via selectors fold: Alpine Houndmaster LIB, Cultivate LIB, Kinetic Augur HAND, Rewind BF-ANY, Ugin the Spirit Dragon HAND; 8 CostDiscard(HAND:YOU): Demonic Embrace, Ghostly Pilferer, Niambi Esteemed Speaker, Sanctum of Shattered Heights, Seasoned Hallowblade, Sparkhunter Masticore, Thrill of Possibility, Tormenting Voice [ZNR]; 1 CostTap(BF ANY + CONTROLLER_IS YOU): Shacklegeist). FINDING vs spec's "15 cards / 17 nodes": spec arithmetic double-counts Bad Deal + Waker +1 which its own exclusion sentence removes, and Run Afoul is excluded on executor ground truth (its own text_excerpt names the OPPOSED player as chooser). Deferred: 7 QUnbounded (ONE_OF lane raises NotImplementedError on them), 3 opponent-chooser (Goremand/Liliana's Steward/Mind Rot) + Run Afoul → ZND-9/ZND-7 lane, Bad Deal + Waker +1 merged-hand → ZND-7(a). Node-holder ground truth: 8x CostDiscard(HAND:YOU QConst) + 1x CostTap(BATTLEFIELD ANY + CONTROLLER_IS YOU) + 5x atom-pair CHOOSE (SEARCH/UNTAP/etc roles). Cmds: python3 tools/audit/r3_lane_ledger.py --out /tmp/opencode/r3_rerun.json (+--lift-out /tmp/opencode/r3_lift.json); cmp /tmp/opencode/r3_rerun.json reports/r3_blindness.json.
- R3 CHOOSE-LIFT LANDED (2026-10-20, /141 spec, lands /144): silent-CHOOSE ask-lift LIVE for 14 cards/14 nodes (5 atom-pair CHOOSE via resolve_selector opt-in ask_choose fold at 3 resolver sites + 8 CostDiscard + 1 CostTap via build_payment_plan tap_options/discard_options; gate _choose_lift_allowed = QConst-only / public-or-owner zones / chooser==controller / oracle-deferred table). COMPILED IR Δ0 both pools (plain-rehash M21 52ae7619… ZNR e8965a74…, gaps 0/1 — ask wiring is runtime-only). Ledger rerun BYTE-IDENTICAL (shas 4059273d…). V4′ upgraded count-only→per-node shape-hash (sha256-16: node tag+field+index-path+canonical selector); baseline v2 = 146 cards/193 nodes (population-identical to frozen law; first upgrade draft had a container-traversal hole — pairs[i][1] leaves invisible, 31/193 nodes — caught by ledger rerun, fixed via recursive _container_leaves). Gates: battery 17/17 (6 red-first); full pytest MTG_bot/core+tools 3186 tests 0 fail (incl. 66 games lane); conformance errors=0 warns=7 rc=0; audit probes 20/20; atom_field_table rc=0; packs 428/428 double-run BYTE-IDENTICAL; fuzz ZNR 40/40 crashed=0 signatures=0, same-seed double-run outcome-identical (timing fields only). Pack ask-surface: 13 packs / 17 CHOOSE asks (QOneOf(QConst(handles)) target lists now visible; vocab-clamped FIFO absorbs; predicted drift). Deviations: LIFT-NOW 14 not 15/17 (spec double-count; Run Afoul→ZND-9); corpus game re-anchored turns 50→30 (same loser, double-run verified). Cmds: .venv/bin/python -m pytest MTG_bot/core tools -q --timeout=600; python3 tools/audit/r3_lane_ledger.py --out … + cmp; tools/audit/ontology_conformance.py (rc=0); tools/run_scenarios.py; tools/eval/znr_engine_smoke.py --games 40 --out /tmp/opencode/r3_fuzz.json.
- R3 Δ0 REPRO CMD (2026-10-20, diff-gate follow-up; makes the plain-rehash headline above admissible — re-executed same day, both shas re-printed exactly): `.venv/bin/python -c "import hashlib,sys; sys.path[:0]=['.','tools/audit']; from MTG_bot.core.ability_tree import canonical_json; import ontology_conformance as oc; [print(s, hashlib.sha256(''.join(canonical_json(v['cards'][o]) for o in sorted(v['cards'])).encode()).hexdigest()) for s,v in sorted(oc.compile_pools().items())]"` → M21 52ae76190c335a48… ZNR e8965a74529821d4… Evidence copies (pre-change RED log, fuzz double-run, Δ0 snapshot, FIX-1 extinction red/green chain) committed under KNOWLEDGE/2026-10-20/artifacts/.

- NIGHT-1 OUTCOME (2026-10-21, /146): plumbing production-proven (audit GREEN real path; rc=8 honest halt; engine down 2 min total); device bug fixed 7403155 + cuda regression test; collection 0.25 g/s engine-off CPU 6w (n=2 provisional); night-1b armed 23:59.

- NIGHT-1 OUTCOME (2026-10-21, /146): plumbing production-proven (audit GREEN real path; rc=8 honest halt; engine down 2 min total); device bug fixed 7403155 + cuda regression test; collection 0.25 g/s engine-off CPU 6w (n=2 provisional); night-1b armed 23:59.
- BENCH ADVERSARIAL + LIVE-RUN ATTEMPTS (2026-10-25, /150): 2 FATAL (name-ask CHOOSE_NAME hidden-zone leak -> refused-leaky neutralization enforced; manifest model identity now recorded — verified live) + A3/A4 fixed; 70/0 bench tests incl 2 new transient-retry tests. RUN-L1 4/4 void (120s timeout too short at 6.4 tok/s measured; usage counts reasoning tokens: 1428 vs max_tokens 512). RUN-L1b (masked, 600s) 4/4 void HTTP 503; isolation: gateway hangs new completions (300s -> 000) while orchestrator session active; engine healthy direct (8002 200, vLLM 0.0 decode) => OPS LAW: live LLM bench runs need a quiet engine (owner scheduling call: quiet slot / idle-session probe / hosted-last).
- RL PILOT NIGHT-1 (2026-10-25/26 window, /151): P0/P1 GREEN — calib 50g audit bit-exact (max|Δ|=0.0 cpu); F4: plumbing alive, policy NOT moved after 1 step (mean|dlogp|=1.9e-6, KL_post=3.1e-9); mirror probe 60g = 0.552 [0.424,0.672] vs frozen pre-RL anchor (instrument noise, not strength); P2 collect 1000g = 2601s = 0.384 g/s net; P2 CPU audit rc=124 TIMEOUT (3600s guard, ~4.8 s/game measured) → honest stop rc=6, no rld_i1.pt. Fix smokes (real mode): CUDA audit of real 1000g episodes GREEN 369s (max|Δ|=5.5e-4 < tol 1e-3, 46941 asks); audit SHA-identity (mirror of trainer _ckpt_key /149) + 2 tests → test_rl_train 11/11; PIN/export-freeze guard: dry#1 rebuild rc=0, dry#2 reuse rc=0, tampered-PIN exit 3 pre-engine. PIN = 7bda5549… (pre-night-2, documented deviation; export HEAD b308cf5, payload==e36ae62). Cmds: window reports/rl_window_run.log; dry reports/rl_window_dryrun.md; /tmp/opencode/rld_n1/{audit_*,rld_cal_diag.json,probe_p1.json}; /tmp/opencode/smoke_audit_cuda_iter1.json.
- BENCH FIRST LIVE-LLM NUMBER (2026-10-26, /153): track R masked, 12 scorable items, model nvidia/Qwen3.8-27B-NVFP4-low (same 27B weights, low-reasoning preset), prompt mode temp 0, detached tmux, ~21 min wall: all-keys 0.518 [0.278,0.758]; delta vs null 0.411 [0.189,0.650] (CI excl. 0) — first live-LLM number; exploratory n=12. Exclusions: 116 by reason; 1 shape-gap logged (ZNR '1+*' pt). RUN-L3 duel (deals=2, 4 h) zero-settled = work-volume arithmetic (engine healthy: 125 POSTs all 200, ~16 tok/s; ~1.8 min/ask under contention; 1 game = 1-5 h). OPS refinement: session KV slows completions, does not wall them → detached runs work while engine up (resolves /150 owner-scheduling item). RUN-L3d (duel deals=1) running detached since 15:38. Cmds: /tmp/opencode/bench_rules_l3.sh, bench_duel_l3.sh; reports/bench_rules_l3_2026-10-26.json (+_items).
- BENCH FIRST LIVE DUEL (2026-10-26, /155): llm (nvidia/Qwen3.8-27B-NVFP4-low, masked, prompt mode, temp 0) vs uniform floor, 1 pair (2 games, same deal seat-swapped, setup_fp 7091e657 identical): 2/2 WINS, decisive 1.0, pair_score 1.0 [1.0,1.0] (n=1 pair, degenerate CI), elo inf (no losses — degenerate, honestly labeled); refused_leaky 0, usage_missing 0, token_stats ok. Cost/clock (BEN-T1 first live): game1 92 calls/198.2k prompt/162.7k completion tok, 14478s wall (4.0h); game2 78 calls/98.6k/97.5k, 8264s (2.3h); ~2.3k tok/call, ~2.6 min/call under session contention. Plumbing+cost measurement only — floor is the bottom rung, not a strength bar (bot adapter B-23 gates LLM-vs-bot). Cmds: /tmp/opencode/bench_duel_l3.sh; reports/bench_duel_l3d_2026-10-26.jsonl (+_summary).
- RL PILOT NIGHT-2 (window 2026-10-26 23:59→01:54, /156): FIRST FULL CHAIN rc=0 (114 min); export reuse fired (fingerprint match, production proof); cuda audit 1000g/46941 asks GREEN 330s, max|Δ|=5.507469177246094e-4 BIT-IDENTICAL to day-before smoke (deterministic); iter-1 train (SGD lr 1e-5, 1 update): grad 2.526→1.0, mean|dlogp|=1.69e-6, KL_post 2.4e-9, share|dlogp|>0.1=0.0, reward_var 0.962, crashes 15 (1.5% engine crashes on anchor-driven collect; probe 200g X=0). PROBE 200g: MIRROR 0.523 [0.453,0.592] vs frozen pre-RL anchor; teacher 0.343 (descriptive). /152 verdict: MIRROR-FLAT (expected-most) ⇒ lever too weak (SGD lr 1e-5 x clip 1.0 = weight step ~1e-5), not "RL negative". Night-3 lever: lr 1e-4 (real-mode smoke in flight; re-pin after). Timing: P1 814s; P2 collect 2600s/0.385 g/s, audit 330s, train 1438s, probe 1625s. Cmds: reports/rl_window_run.log; /tmp/opencode/rld_n1/{probe_p2.json,rld_i1_diag.json,audit_iter1.json,timing.env}.
- RL PILOT /158 (2026-10-27): INSTRUMENT FIX — trainer mean_abs_dlogp_chosen proven a PRE-update consistency check (BIT-IDENTICAL across lr 1e-5/1e-4/1e-2 = 1.6939604285741257e-06 on the same 1000g episodes) — it never measured movement; added post-update movement keys mean_abs_dlogp_chosen_post / share_dlogp_gt_0p1_post (+ multi-step: steps, step_grad_norms, --steps); corrected MOVED = share_dlogp_gt_0p1_post > 0 OR kl_post >= 1e-4; suite 13/13 (781s, 2 new tests: lr-monotonicity of post-dlogp + multi-step>single-step). MEASURED KL SCALING (real 1000g, cuda): KL_post(1e-5)=2.43e-9, (1e-4)=1.235e-7, (1e-2)=8.424e-4 — p~1.707 fit from the first two points is CONSERVATIVE at the top (measured 2.6x above extrapolation); lr 1e-2 = 8.4x over MOVED threshold, 59x under the 0.05 KL ceiling, no breach; share_dlogp_gt_0p1_post(1e-2)=0.0122 (BOTH MOVED conditions fire). /157 grid {lr<=1e-3}x{steps<=20} proven INFEASIBLE (only crossing point 1e-3x20 needs ~8h GPU > ~5.3h P2 slot). NIGHT-3 ARMED: lr 1e-2 x steps 1 (smoke 42m16s under contention; in-window GPU exclusive ~24min expected); fallback B pre-registered: lr 3e-3 x steps 3 if A reads MOVED+M<0.47. Deviation from /157 branch 4 (owner-level regime choice) recorded in /158: standing GO + autonomous instruction + grid infeasibility => minimal-risk crossing point; revocable via /tmp/opencode/RL_WINDOW_CANCEL (checked before every phase). Explicit re-pin 8ef64d61c446bddad907a174389510441269118b2d957fc4c69ee73895e31f2c (supersedes 7bda5549...; provenance + smokes on line 2). Dry-run post re-pin: PIN match, rebuild from pinned payload (trainer sha256=145b1715f887, driver sha256=76f2e96aa029e overlaid), FULL CHAIN rc=0, lever path verified (dry train diag: lr 0.01, steps 1, post keys live). Cmds: smokes rld_smoke_postkey_diag.json / rld_smoke_lr1e2_diag.json (/tmp/opencode/rld_n1/); bash tools/ops/rl_window.sh --dry-run (2026-10-27 09:20, rc=1 forced trap).
