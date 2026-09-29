# Round-12b — trigger binding, event journal, compiled-ability attachment (2026-09-29)

## What landed (uncommitted; scope `MTG_bot/core/executor/**` + one test file)

- **`executor/events.py` (new)** — `GameEvent(clock, kind, subject, cause, cause_verb, data)`
  + `EventJournal`. The journal snapshots the world at every Atom boundary inside
  `Executor._run_effect` and diffs zones/tapped/counters/life → structured events
  `ZONE_CHANGE / CREATURE_DIES / COUNTER_PLACED / TAP_STATE / CARD_DRAWN / DAMAGE /
  LIFE_GAINED / TURN_PHASE`. verbs.py untouched (diff-inspect design; the handlers'
  12a DAMAGE tuples ride in as the "returned info" for non-lethal card damage).
  C18: CREATURE_DIES carries the was-snapshot `(from, owner, type_line, was_power,
  was_toughness)` computed through the DurationLedger. Turn trackers (per-controller
  draw ordinals) live here, reset at `begin_turn`.
- **`executor/binding.py` (new)** — `TriggerBinder`: oracle-id registry (the game
  `CardIdentity` ↔ compiled `CardRecord` bridge, identity-CHECKED on attach),
  `(handle, idx)` trigger table with battlefield lifecycle (attach-before-match on
  entry so IS_SOURCE ETB triggers see themselves; detach-after-match on leave so the
  permanent's own dies trigger fires), event matchers per EventSpec kind, APNAP fire
  loop = `world.order_key` `(controller_seat, clock)` + `str(source)` + bind-seq
  tie-break, decisions consumed across the drain in fire order (C15 may-offers),
  C22 `DelayedTrigger` scheduling with turn-window expiry (`Eot`/`UntilNextTurn`
  swept by `end_turn`; other tags raise as 12d). `MAX_TRIGGER_FIRES = 200` per drain
  → `RuntimeError` (self-retrigger loop is flagged, never run).
  **Flag-don't-degrade at BIND time**: CastSpell/DeclareAttackers/DeclareBlockers/
  CombatDamage/BecomesBlocked/LoyaltyActivated/Step/Targeting event nodes, plus
  DamageDealtEvent with `source` filter or `combat=True`, raise `NotImplementedError`
  naming the owning phase.
- **`executor/__init__.py`** — journal + binder wiring; `attach_card/attach_pool/
  fire_triggers`; auto-drain (`_settle`) at the end of every public op with optional
  `trigger_decisions`; turn skeleton `begin_turn` (UPKEEP+FIRST_MAIN markers, turn
  clock, NO untap — 12d) / `end_turn` (END_TURN marker, drain, then ledger
  `sweep_at_eot` + delayed expiry) / `advance_turn`; `state_fingerprint()` extended
  with journal dump + binder dump. `_run_effect` gains the journalled Atom boundary +
  the DelayedTrigger scheduling branch (test_unsupported_effect_nodes_raise never
  listed DelayedTrigger, so 12a stays green).
- **`quantity.py`** — `ExecCtx.event`/`event_amount`; `event`/`result` QProp+selector
  referents (bound only inside firings — raise otherwise); `QPropField.AMOUNT`;
  `FAtomPred.IS_TOKEN`.
- **`selectors.py`** — `event`/`result` referent selectors; `CONTROLLER_IS` with a
  referent `Selector` (resolved, player-compared) instead of raising.
- **`test_executor_binding.py` (new, 16 tests)** — attachment + identity-bridge
  ValueError, detach/re-register lifecycle, REAL compiled mini pool (b2a Carrion-Grub
  row via `compile_pool(pool, build_full_registry())` → ETB mill fires), C18 dies
  (`QProp("event", POWER)` pays the LEDGER power 4, not printed 2), draw ordinal=2,
  TapState, CounterPlaced(QAtLeast), LifeGained (one-way — its effect mills; a
  life-gaining effect would feed its own event), DamageDealt + Sacrifice (cause verb),
  turn-phase UPKEEP/END_TURN + Eot sweep after firing, APNAP simultaneous dual ETB
  (SET_PT fold: p0's resolves first, p1's 5/5 last wins), Subira delayed window
  expiry, combat/cast/targeting/step bind raises + damage-scope raises, 200-fire
  tripwire RuntimeError (Looper gy→bf self-chain), may-offer fire/skip in fire order,
  and the P12 two-replay fingerprint-equality test over the ETB-draw→draw-trigger→
  mill chain.

## Discoveries / rulings made here

1. **`MOVE_ZONE` requires the `cards` role ARG even when objects arrive via
   `bindings={"cards": …}`** (Atom role validation). Convention: placeholder
   `Selector(QConst(9), ALL, UNIV, ANY/ANY)` in the atom; bindings win at runtime.
2. **One permanent = one compiled record.** `attach_card` with a DIFFERENT oracle id
   on an already-attached handle RAISES `ValueError` (the `(handle, idx)` key would
   silently clobber otherwise). Same-record re-attach is an idempotent refresh.
   Check-then-commit: `_check_event` runs for every ability BEFORE any binding
   mutates, so an unsupported event kind never leaves partial state.
3. **World counter keys are `CounterKind.name`** (`"PLUS_1_PLUS_1"`), not the
   cosmetic `"+1/+1"` — assertion/lookup sites must use the enum name.
4. **`TemplateRegistry()` is EMPTY** — tests need `coverage.build_full_registry()`
   to get the B1–B5c template rows (test_compiler's M21 smoke does the same).
5. **The frozen `state.py` `order_key` is seat-first, active-blind** — `(controller_
   seat, clock)`. 12b's APNAP drain uses exactly that (the mission's "world
   order_key"); a true active-player-first rotation would need a state.py change →
   later phase note, not 12b's license.
6. **LifeGained triggers feed themselves**: a "whenever you gain life, gain life"
   binding is an instant 200-fire RuntimeError. 12b's tests pin the honest shape —
   LifeGained feeds use non-life effects (mill); the tripwire catches loops loudly.
7. `Phase` IR has no COMBAT-step granularity beyond UPKEEP/FIRST_MAIN/END_TURN/COMBAT;
   the 12b skeleton emits only the first three (no untap, no combat — 12d).

## Measurements

| metric | value | command |
|---|---|---|
| new binding tests | **16 passed** (+4 subtests) | `pytest MTG_bot/core/test_executor_binding.py -q` |
| core suite | **1788 passed, 0 failed** (1772 baseline + 16) | `pytest MTG_bot/core -q` |
| pyright (executor pkg + both executor tests) | **0 errors** | `pyright MTG_bot/core/executor MTG_bot/core/test_executor_binding.py MTG_bot/core/test_executor_verbs.py` |
| ruff | new files **0 findings**; existing edited files **delta 0** vs HEAD (in-place, incl. the N999 path artifact) | `ruff check --output-format=concise …` + `git stash push -- <file>` baseline trick |
