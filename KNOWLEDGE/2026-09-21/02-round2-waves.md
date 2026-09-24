# 2026-09-21 · 02 — Round-2 template waves (post-T3 grammar)

**Context:** after the T3 round-1 grammar additions (see 2026-09-19/02 decision +
2026-09-19/03 implementation), per-bucket coders re-triaged every UNCOVERED
shape: cover what the new grammar expresses honestly, refine the rest.
201 UNCOVERED at decision time → **158** at wave completion (43 newly covered).

## Wave results (all verified on disk by the orchestrator)

| Bucket | templates | covered shapes | UNCOVERED (was) | newly covered |
|---|---|---|---|---|
| b1 | 15 | 15 | 0 | — |
| b2a | 51 (was 45) | 51 | 11 (was 17) | 6 |
| b2b | 36 (was 18) | 38 | 24 (was 44) | 20 |
| b3 | 26 (was 23) | 44 | 4 (was 7) | 3 |
| b4 | 26 (was 18) | 26 | 21 (was 29) | 8 |
| b5a | 38 (was 34) | — | 25 (was 29, now machine-readable per T4) | 4 |
| b5b | 37 (was 35) | 41 | 49 (was 51) | 2 |
| b5c | 66 | — | 24 | **round-2 pending** |
| **total** | **295** | — | **158** | **43** |

Core suite at wave completion: **902 passed / 0 failed**
(`python -m pytest MTG_bot/core -q`).

## Operative lessons (new traps, dated)
- **b2b first attempt crashed** (subagent runtime segfault at step 343, during
  the reading phase; no changes landed). Re-dispatched fresh; succeeded.
  → verify on disk after EVERY delegation (transport failures are a standing
  fact, see 2026-09-16 handoff §4).
- **b3 first attempt returned an empty result and made NO changes** (no disk
  footprint at all). Re-dispatched with the same spec; succeeded.
- **b5a T4 agent introduced a pyright regression** in `_build_destroy` /
  `_destroy_target_filter` (parameters typed `object` + `type: ignore` where
  `Filter` is the honest type). HEAD was pyright-clean; the orchestrator fixed
  it (proper `Filter` annotations, ignores removed) — pyright 0 errors, 64
  b5a tests still green. → round-2 agents must run pyright on their modified
  files, not just pytest.
- **GAIN_CONTROL has no duration role**: "Gain control of target creature
  until end of turn." (B5b) is still UNCOVERED despite the verb existing —
  `AtomArgs` validation for GAIN_CONTROL accepts no duration slot. Either a
  T3-round-2 grammar addition (add `duration` role to GAIN_CONTROL — one
  shape now, but gain-control-until-eot is a common cross-set shape) or
  per-card. Decision deferred to the T7/T8 triage (one shape is below the
  ≥3-shape rule; revisit if more appear).
- **B3's "this creature fights another target creature"** remained UNCOVERED:
  MANDATE_ATTACK's roles do not match the fight construction as written.
  Similarly "{N}{W}, {T}: … may cast a creature spell from among cards exiled
  with this artifact…" (companion/exile-with-source + cost waiver) remained
  UNCOVERED despite Verb.CAST existing — the missing sub-construct is the
  "exiled WITH this artifact" grouping, not the cast itself.

## Standing state
- 158 machine-readable UNCOVERED shapes across the 8 modules = the T8
  per-card triage input (cross-sentence anaphora, modal headers,
  per-card weirdness — see the per-module `UNCOVERED` tuples).
- `tools/gen_buckets.py` remains the only sanctioned way to regenerate
  `/tmp/opencode/phase1_buckets/*.json`.
- Round-2 knowledge notes written by agents: 2026-09-21/01 (b2b), plus
  supersession banners on 2026-09-18/01.
