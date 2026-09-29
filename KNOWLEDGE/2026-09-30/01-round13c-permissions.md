# 01 — Round 13c: emblems, type grants, activation windows, extra land plays (2026-09-30)

Phase 13c of `2026-09-29/11-round13-arc2-plan.md`. Scope was executor-only
(`executor/**` + `test_executor_permissions.py` + knowledge); `state.py` /
`ability_tree.py` / compiler / goldens untouched.
**Result: PC-7 engine_supported 279 → 286/305 (EXACT), core suite 1948 → 1971.**
Doc /11 projected 288 (+9); honest delta is **+7** because Teferi stays
double-flagged (GRANT_ACTIVATION handler shipped, PHASE_OUT deferred to 13d).

## Flip set (probe-verified, exactly +7 cards)

- **ADD_LAND_PLAY**: Azusa, Lost but Seeking.
- **GET_EMBLEM**: Basri Ket, Garruk Unleashed, Liliana Waker.
- **GRANT_TYPE**: Demonic Embrace, Dub, Riddleform.

`SUPPORTED_VERBS_V2` 35 → **39** (derived from HANDLERS; V1 stays frozen at 24).

## What shipped

- **verbs.py**: `_v_get_emblem` (idempotent by `(owner, oracle-oid)`),
  `_v_grant_type` / `_v_add_land_play` / `_v_grant_activation` (runtime layer
  attach paths; static counterparts compile in `layers._new_static`).
- **layers.py**: three layer kinds (`type_grant`, `activation_grant`,
  `land_play`); `_types` overlay computed in `_rebuild_maps`; views
  `type_overlay(h)` / `instant_window_granted(h)` / `land_play_bonus(seat)`;
  `_layer_live` emblem liveness escape; `_new_static` unwraps
  `OptionalEffect`.
- **quantity.py**: TYPE_EQ/SUBTYPE_EQ/SUPERTYPE_EQ UNION the live overlay over
  the printed type-line words; `NAME_CONTAINS` (case-sensitive substring on
  printed name); `IS_ATTACHED_TO_SOURCE` reads the executor attachment table
  (bare ExecCtx → flagged `ValueError`).
- **binding.py**: `bind_emblem` + `emblem_owner` map, `_controller_of`,
  attachment purge on detach, deterministic dump gains an `emblems` row.
- **legality.py**: SORCERY window gate relaxes to INSTANT when
  `instant_window_granted(source)`.
- **stack.py**: land allowance = `1 + extra_land_plays + land_play_bonus(seat)`.
- **`__init__.py`**: `emblems` replay state + `_emblem_seq`, `attachments`
  table, `get_emblem`, `attach_aura` (validation + recompute), fingerprint
  folds for both new tables.
- **test_executor_permissions.py**: 23 tests / 4 classes (land-bonus, type
  overlay, activation window, emblems) — all green.

## Rulings

1. **Emblems are EXECUTOR replay state, not world cards** — frozen CardState
   has no emblem field. Synthetic `Handle("emblem", seq)`; binder anchors an
   emblem's statics at the OWNER (`attach_source(controller=owner)`); liveness
   = `_layer_live` escape into `executor.emblems.values()`.
2. **Attachments are an executor table** (`aura → host`), purged on detach.
   v1 gap: attaching is an explicit `attach_aura` op only — no ETB-triggered
   enchant/equip auto-attach (compiler emits no such atom).
3. **GRANT_TYPE is the single type oracle**: filter TYPE-family words =
   printed ∪ overlay. Union never removes (no REMOVE_TYPE in corpus).
4. **`OptionalEffect` on a static is unwrapped at layer-compile** — "may"
   is a use-side decision (the 12c optional_offer path), not a layer fact.
5. **Teferi's GRANT_ACTIVATION is IR-faithful and global**: the compiled
   filter (`FAnd(TYPE_EQ Planeswalker, NAME_CONTAINS "Teferi")`) matches any
   seat's planeswalker; the ONLY consumer is the `ability_playable`
   SORCERY-gate relaxation (cost/controller gates untouched). Cross-seat
   grant is a fidelity consequence of the compiler's global layers.
6. **Effect-vs-static death split**: a RESOLVED permanent-duration GRANT_TYPE
   outlives its source (not an aura — MTG-correct). `_layer_live` checks only
   `world.cards` membership + the emblem escape — no zone check; static
   grants die with the source only through `binder.detach`. Known v1 gap:
   manual zone moves don't auto-detach.
7. **Azusa quirk**: two untargeted repeatable activations each stack
   `ADD_LAND_PLAY(+2, permanent)` → cumulative bonus; data-driven, documented.
8. **Deferred**: `is_land_card` does NOT consult the overlay (type-changes-to-
   land cards cannot be played as lands) — no corpus card needs it.

## Frozen-surface tests amended (dated AMENDED notes in place)

- `test_executor_verbs.py` dispatch-raise probes: GET_EMBLEM removed (FIGHT/
  PHASE_OUT/COUNTER_SPELL stay — PHASE_OUT is 13d's).
- `test_executor_library.py` V2 growth set: 35 → 39 with the four new verbs.
- `test_executor_legality.py` unsupported-condition-pred probe: NAME_CONTAINS
  is in-vocab now — swapped for `CMC_LE` (still unimplemented).

## Fixture traps baked into the test file

CardRecord: `loyalty` is a POSITIVE INT and set EXACTLY for Planeswalkers;
`emblem` must be an `Emblem`-typed record with `is_token=True`; oracle ids must
be valid hex uuids; same-oid `attach_source`/`attach_card` = idempotent
refresh; replay fingerprints need FIXED oracle ids (global `_ORACLE` iterator
poisoning already pinned in PITFALLS).

## Gates (all green, 2026-09-30)

- `.venv/bin/python -m pytest MTG_bot/core -q` → **1971 passed / 0 failed**
  (+ 8 subtests) = 1948 baseline + 23 new.
- `.venv/bin/python tools/measure_grammar.py --with-engine-flags` →
  **engine_supported 286/305**, PC-1..5/9/10 PASS, PC-4 EXACT (305 files,
  0 diffs); PC-6/PC-8 unchanged pre-existing FAILs.
- `pyright` executor pkg + 4 touched test files → **0 errors / 0 warnings**.
- `ruff` delta **0** vs HEAD: layers.py's two new findings fixed (SIM102
  merged, `TypeError` for the GRANT_TYPE role guard); quantity 18 /
  selectors 12 / `__init__` 4 are byte-identical error sets to HEAD.
- Hygiene note: NUMBERS.md repeats the "## 2026-09-29 (T5 …)" header once per
  appended run — the measure tool's append template; cosmetic, append-only
  history preserved (do not rewrite NUMBERS.md).
