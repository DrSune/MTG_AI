# 12 — Round 13b: spell stack, casting pipeline, cast feed, mana policies (2026-09-29)

Phase 13b of `11-round13-arc2-plan.md`. Scope was executor-only (`executor/**` +
tests + knowledge); `state.py` / `ability_tree.py` / compiler / goldens untouched.
**Result: PC-7 engine_supported 264 → 279/305 (EXACT target), core suite 1906 → 1948.**

## What shipped

- **`executor/stack.py` (new)**: `SpellObject` (the CR 601.2b–e declaration record:
  node, locked X, sorted declared_targets, mode_choices, locked PaymentPlan,
  from_zone, declared_clock), `SpellStack` (LIFO frames + deterministic `dump()`),
  `stack_zone`/`park` (per-player `ZONE_STACK` ZoneState via `zones.setdefault` —
  zero state.py edits), `land_playable`/`play_land` (CR 305.1 special action,
  `land_ledger` once-per-turn + `extra_land_plays` 13c hook), `cast` (folded
  601.2→601.4: spell_castable → `_validate_spell_targets` → pay → park+record →
  push+`emit_cast` → settle (cast triggers resolve ABOVE the spell, CR 603.2) →
  pop → resolve → put (GY/permanent battlefield + auto re-attach so ETB is live
  before the settle matches) → settle), `cast_card` (effect-side: `cost_override`
  None = printed cost / empty `Cost` = waiver CR 498.2; `targets` param validates +
  binds — the ATOM role table has no target channel, so effect-cast spells WITH
  targets are only castable through the direct API; corpus cast-from-effect cards
  designate targetless creatures, gap flagged in the docstring, never silent).
- **`legality.py`**: `spell_record` / `spell_cost` (printed + additional fold) /
  `spell_window_reason` (no timing slot on SpellAbility → window from SpellKind:
  INSTANT ungated at this API — priority is outside v1; the rest sorcery-timed:
  active player, phase ∈ (None, FIRST_MAIN), stack empty) / `spell_castable`
  (hand gate, record, node, window, QX: `x=None` enumerates the documented X=0
  witness, too-big X = ordinary shortage reason, never a raise);
  `ManaLedger`/`ManaSegment` beside the frozen pool (ADD_MANA tags segments from
  the source's live THIS_MANA policy; `restricted_amounts` removes non-matching
  tagged mana from the plan's usable totals; `consume` untagged-first; empty
  tags ⇒ byte-identical totals path — the 12a/12b replay pins stay green).
- **`layers.py`**: StaticAbility MANA_POLICY branch (`kind="mana_policy"`, the
  Vodalian/Orrery statics previously CRASHED `_new_static`), `register_mana_policy`
  (handler-dispatch shape), `this_mana_filter`, `all_yours_live`.
- **`verbs.py`**: `_v_pay` (payer = ctx.controller — role table has no payer role,
  third-party "that player may pay" is a documented coordinate gap; unpayable fire
  RAISES, CR 117.3), `_v_cast` → `cast_card`, `_v_choose` (decision `str(i)` into
  `verb_choose_options` order = the 12d ORDER contract; binds `result`; multi-pick
  = loud flag, corpus is count=1 only; empty pool consumes NO token),
  `_v_choose_name` (records `executor.name_choices[source]`; candidate vocabulary =
  world card names — seeded-random NOT offered, player decisions own their channel),
  `_v_mana_policy` (register + recompute); ADD_MANA segment mirror; LOSE_GAME now
  emits a `GAME_LOST` journal row (13a audit-only quirk fixed). `HANDLERS` +5.
- **`query.py`**: `CastOption` (spell rows carry node+plan, land rows
  `land=True/payment=None` — a land has no cost fold, don't fake one),
  `legal_casts` (spells+lands interleaved, Handle-sorted, C15 one-surface),
  `spell_target_slots` (TARGET selectors; ANY+universal-filter widens candidates
  with player seats, CR 109.5; non-universal filters stay card-only; TARGET_PLAYER
  rides the cast player-coordinate rule — grammar gap documented),
  `verb_choose_options` (enumerate_candidates, NOT resolve_selector — the CHOOSE
  resolver clamps to n before any choice exists), `optional_offer` PAY-payability
  narrowing.
- **`binding.py`**: `CastSpellEvent` LEFT the unsupported table — `_match_cast`
  (controller scope, per-caster per-turn ordinal from the journalled feed,
  `from_zone`/`from_zone_not` with the zone ref scoping the CASTER, filter over
  the spell card incl. COLOR_IN/COLOR_HAS, `from_zone_not` corpus: Ghostly
  Pilferer HAND/OPPONENT). Combat/targeting/step raises stay pinned.
- **`quantity.py`**: `ExecCtx.x_value` + QX read; COLOR_IN (non-empty SUBSET —
  grammar), COLOR_HAS (membership), NAME_CHOSEN (reads `name_choices`, raises
  without a record = FLIP_WON convention).
- **`events.py`**: `KIND_CAST` (`emit_cast`, per-caster ordinal in the row,
  `begin_turn` reset), `KIND_GAME_LOST`, `GameEvent.cast`.
- **`__init__.py`**: executor fields `stack/land_ledger/extra_land_plays/
  mana_ledger/name_choices`; `_ctx(x_value=…)`, `_cast_ctx`, `mana_permission`;
  **`state_fingerprint` folds stack dump + land ledger + extra plays + mana-ledger
  dump + name_choices**.

## Key rulings & findings (deltas to the plan, all verified in-code)

1. **The CAST-atom finding held**: all corpus CAST atoms are EFFECT verbs
   ("cast the designated card") under OptionalEffect, `cost` role = waiver
   (empty Cost) or additional — never a permission ledger.
2. **Fingerprint decision**: `GameWorld.fingerprint` iterates PLAYER_ZONES only
   and ZONE_STACK is outside them (state.py frozen) — completeness moved to the
   EXECUTOR fold; pinned: two same-world executors differing only by a pushed
   frame (and by frame x_value 3 vs 4!) differ in `state_fingerprint`.
3. **No-interaction v1**: casts resolve immediately; **COUNTER_SPELL STAYS
   NotImplementedError** (Cancel/Lofty Denial/Miscast/Rewind keep raising —
   pinned in `test_executor_stack.py` + the dispatch-pin amendment).
4. **`CostManaColor` has no "C" member** (colors = WUBR): colorless costs are
   `CostManaGeneric` — the test fixtures hit this; Vodalian pool key "C" itself
   is fine (pool keys ≠ cost members).
5. **ALL_YOURS is read independently of the segment mirror** (direct pool writes
   have no segments but the permission still governs) — plan-fold order fix.
6. **Loyalty quirk fixed symmetric**: CR 606.1b gates the SOURCE not the sign —
   both signs on a non-planeswalker → `"cost:loyalty:not_planeswalker"`; two
   13a pins amended (legality suite + library "KNOWN MISMATCH … 13b flips" pin).
7. **PAY payer coordinate**: v1 pins ctx.controller (the ability's "you");
   third-party payers documented as a gap — never a silent different payer.

## Pins amended (test files, AMENDED comments in place)

`test_executor_library.py`: loyalty non-PW flip, V2 growth-set (30→35);
`test_executor_verbs.py`: COLOR_HAS/COLOR_IN now evaluate (+IS_ATTACKING stays
the raise probe), CAST left the dispatch-raise probe; `test_executor_binding.py`:
CastSpellEvent left the bind-raise list; `test_executor_legality.py`: loyalty
symmetry.

## Gate tails (all re-run after the final edits)

- `.venv/bin/python -m pytest MTG_bot/core -q` → **1948 passed** (1906 + 42 new
  in `test_executor_stack.py`), 0 failed; replay byte-identity & PC-1..4 pins green.
- `python tools/measure_grammar.py --with-engine-flags` → **PC-7 279/305** (35 verbs).
- Flip set EXACTLY +15 (probe: gated compile at 35 vs 30 verbs): CAST×6
  (Catalyst, Chandra HoF, Snoop, Furious Rise, Idol, Radha) + PAY×3 (Kraken,
  Devotee, Pilferer) + MANA_POLICY×2 (Orrery, Vodalian) + CHOOSE×2 (Duress,
  Freebooter) + CHOOSE_NAME×2 (Necromentia, Runed Halo). Cancel/Lofty
  Denial/Miscast/Rewind + Demonic Embrace verified still UNSUPPORTED.
- `pyright` executor pkg + new test file → 0 errors; `ruff` new/modified files →
  delta 0 (only pre-existing quantity.py 18 / selectors.py 12 remain).
- NO commits.

## Deviations / honest gaps (flagged, never degraded)

- Spell windows: SpellKind has no timing slot → INSTANT ungated at the API
  (opponent-turn casts possible); sorcery-family gated. Priority is arc-3.
- Multi-TARGET-selector spells raise NotImplementedError (one tuple can't feed
  two populations); TARGET_PLAYER designation = coordinate rule (grammar gap).
- Verb.CHOOSE multi-pick raises (corpus count=1 only); effect-Cast cannot
  designate targets through the ATOM channel (role table) — direct API only.
- NAME_CHOSEN consumer: Runed Halo's protection needs combat (no executor
  combat yet) — write/read pair + queryable choice shipped (12d EXPOSED-ORACLE
  precedent), the block-side read joins combat.
- THIS_MANA: activations (no use subject) can never spend tagged mana
  (conservative CR 117 reading); restriction rides the mana past the source's
  death (pinned).
