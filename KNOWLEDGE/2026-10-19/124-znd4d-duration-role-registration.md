# 124 — ZND-4d: atom duration-ROLE folded into the layer Duration lane (while-statics no longer ever-live)

Closes /119 FINDING 1 (ZND-4d deferral). Engine-side only; no compiler touches.

## Census (reproducible: /tmp/opencode/census_duration.py, census_nonwhile.py — get_supply('all') compiled pool)
Duration-role (`DurationWhileCondition` in an atom arg of a StaticAbility) exists on
exactly **3 cards, ALL in the M21 pool; ZNR has ZERO**:

| Card | verb | gate | StaticAbility.condition | reading |
| --- | --- | --- | --- | --- |
| Predatory Wurm | MODIFY_PT +2/+2 | FAnd(TYPE_EQ Planeswalker, SUBTYPE_EQ Garruk, CONTROLLER_IS YOU) | None (was ever-live) | existence of a matching permanent under the controller |
| Sigiled Contender | GRANT_ABILITY LIFELINK | FAtom(HAS_COUNTER PLUS_1_PLUS_1 ≥ 1) | None (was ever-live) | of the SOURCE ("as long as IT has a counter") |
| Drowsing Tyrannodon | LOSE_ABILITY DEFENDER | FAtom(…) | **mirrored in condition** | UNAFFECTED by fix (double-gate pin) |

Only non-While duration role in the whole pool: Conspicuous Snoop `DurationPermanent`
(= absence of a window → safe drop, pinned as noop).

## Fix shape (MTG_bot/core/executor/layers.py, +71 lines, registration-only)
New `_static_while_duration(atoms)` folds the role into the record's **existing**
Duration lane ( `_layer_live` re-judges `layer.duration.filter` every recompute;
ledger `settle_while` drives materialization — no parallel mechanism, all
`_new_static` branches threaded):
- bare `FAtom` → kept as-is → judged **of the source** (Sigiled semantics; corpus
  convention: every compiled `StaticAbility.condition` is a handle-free count
  pred or its negation — Gadrak's FNot is plain-lane, outside this fix);
- `FAnd` candidate-shape conjuncts (Wurm) → **re-encoded** into the corpus's own
  existence mechanism: `FAtom(CONTROLLER_COUNT_GE, count=QConst(1), inner_filter=conjunct)`
  — b9's executed reading of the identical conjunct family;
- `FOr`/`FNot` composites → loud `NotImplementedError … not layer-parseable (ZND-4d)`
  riding the r23a `unparseable_statics` sink (survivable + coverage-visible, no guess);
  SINK SEMANTICS (gate axis-5, honest v1 policy): a sink-refused while-static is **inert** —
  the ability is silently OFF (ever-live became never-live, NOT partial), visible in
  unparseable_statics coverage but ABSENT from state_fingerprint. Corpus risk zero today
  (FOr/FNot-while census-zero, gate-reverified); any future set landing a FOr/FNot-while
  static hits this cliff — loud in the sink, silent in play. Never-live is the safer
  wrong-direction (no phantom pump); the fix is a grammar/layer follow-up, not a guess here.
- `DurationPermanent` → None; two DISAGREEING whiles in one record → refuse.

## Gold delta (only packs that encoded the ever-live wrongness)
| pack | field | old → new | CR justification |
| --- | --- | --- | --- |
| tools/scenarios/predatory_wurm.json | pt w | 6 → 4 (×2) | pack's only Garruk is controller 1's synthetic "Garruk Omenbound"; CONTROLLER_IS YOU never holds → gate off → printed 4/4 |
| " | life "1" | 14 → 16 | Wurm deals 4 per attack, not 6 |
| " | notes | rewritten | old gold reachable ONLY through the dropped-gate bug |

sigiled_contender.json unchanged (exercises the ON direction, correct under fix).
Zero other packs changed. NEW pack `m21_predatory_wurm_while_garruk_cycle.json`:
3-swing OFF/ON/OFF cycle (4+6+4 dmg, life 20→6; Garruk enters via "enter", dies via
deal_damage 13 + SBA) pinning flip-back through real battlefield changes.

## Gates (all executed 2026-10-19, post-final-edit)
- Repro-first: MTG_bot/core/test_layers_duration.py — **NEW, 11 tests, 11 failed red → 11 green** (Wurm no-gate 4/4, ON/OFF/flip-back 6/6→4/4→6/6, opponent's Garruk never pumps, LayerRecord duration/status pins; Sigiled counter cycle; Tyrannodon double-gate; Snoop noop; DurationEot + distinct-while refusal via unparseable_statics).
- `pytest MTG_bot/core -q -p no:randomly`: **2793 passed, 36 subtests, 0 failed** (mid-session the sibling's in-flight query.py WIP produced 4 transient failures incl. r23a offer test; attribution: identical failure with my layers.py reverted to HEAD, and the failure sat inside the sibling's dirty `optional_offer` diff — resolved when their edit landed; I fixed nothing there).
- `tools/run_scenarios.py`: **415/415** (414 old + 1 new cycle pack).
- Fuzz, deck-pairs-seed 201019: ZNR `--games 300` → **300/300, 0 crashes, 0 signatures**; M21 `--games 300` → **300/300, 0 crashes, 0 signatures** (both re-run after the final lint fixes; artifacts /tmp/opencode/znd4d_fuzz_{znr,m21}2.json).
- Replay determinism: `test_executor_durations.py::TestReplayFingerprint::test_two_executors_replay_identically` green (plus whole suite).
- pyright layers.py + test file: **0 errors**; ruff: **Δ0 vs HEAD** (HEAD clean → both files clean).
