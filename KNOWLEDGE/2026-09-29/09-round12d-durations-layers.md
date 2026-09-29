# Round-12d — full Duration vocab, continuous layers, replacements, runtime Choose (2026-09-29, uncommitted)

Plan `/06` §12d implemented against the frozen grammar; **core suite
1837 → 1876 passed / 0 failed** (cmd: `.venv/bin/python -m pytest
MTG_bot/core -q`; +39 = 22 durations + 16 layers + 1 amended-verbs Choose
pin). pyright 0 errors on the scope (executor pkg + 3 test files; HEAD
baseline also 0). ruff: repo 815 → 776 (every touched file ≤ HEAD;
durations_min/verbs → 0). No commit (12e lands the feed).

## New / rewritten modules

* `executor/durations.py` (supersedes `durations_min`, now a shim): the
  full `duration_tag` vocab — Eot (physical sweep, 12a byte-identical),
  Permanent, UntilNextTurn (owner begin_turn), WhileCondition (settle
  cycle, status `while_off`), UntilNextStep(UNTAP, owner|active) and
  UntilLeaves (tombstone `expire()`; audit rows kept in `dump()` with a
  status column; `record_id` per entry).
* `executor/layers.py`: `LayerRegistry` — StaticAbility/KeywordAbility
  continuous layers. Derived maps rebuilt in layer-seq order on EVERY
  settle (`recompute()`): `keyword_of` (printed ∪ granted − lost),
  `granted_abilities`, `granted_activated`. Static PT payloads
  **materialize as ordinary ledger entries** (one shared fold
  base→created_clock→record_id); scope selector re-resolved per recompute
  (anthem set membership: enters/leaves handled; stale entries terminal).
  Static payloads beyond Atom/Seq of MODIFY_PT|SET_PT|GRANT_ABILITY|
  LOSE_ABILITY RAISE (12e).
* `executor/replacements.py`: `ReplacementRecord` (compiled
  ReplacementAbility nodes, battlefield-lifetime) + `PreventionRecord`
  (PREVENT_EFFECT: affected set MATERIALIZED from the designated targets
  at cast time — IS_ANY_TARGET is only decidable there). Damage-to-a-
  player interception in `_v_deal_damage` BEFORE any life mutation (C24):
  the event is consumed (journal sees no damage), the carried action runs
  as its own journalled atom after the boundary (no double-emit). The
  UNTAP-step consumer `prevents_untap` is LIVE; combat/mana prevents are
  EXPOSED-BUT-UNUSED (`combat_preventions()`, post-12e consumer).

## Verbs + turn skeleton

* `GRANT_ABILITY` / `LOSE_ABILITY` / `PREVENT_EFFECT` join HANDLERS →
  `SUPPORTED_VERBS_V1` **21 → 24** (test pin amended with dated comment;
  DRAW still deliberately outside; Repeat/EachPlayer still raise; the
  12a `Choose` raise pin amended per the 12c ruling — Choose is now
  runtime-consumed: ONE decision token = index into
  `query.choose_options` order, ORDER contract pinned).
* `begin_turn` gained the **UNTAP STEP** between the turn-clock start and
  the UPKEEP marker: active player's tapped permanents untap unless a
  live prevention vetoes, each untap journalled as a TapStateEvent
  (triggers fire from the tick — pinned); AFTER the tick the
  UNTIL_NEXT_STEP(UNTAP) records terminal-expire ⇒ **a freeze survives
  exactly one untap tick** (pinned). Then UNTIL_NEXT_TURN expiry for the
  beginning player. `end_turn` sweeps Eot ledger + layers + preventions.
  `state_fingerprint` folds both registry dumps.
* UNTIL_LEAVES zone interception: the executor scans every atom's
  journalled ZONE_CHANGEs; battlefield-leaving anchors terminal-expire
  ledger/layer/prevention records (re-entry does NOT restore, r5).

## Rulings (binding, this round)

1. **PT resolution order**: printed BASE first, then ALL modifiers (verb
   + materialized layer entries) folded by (created_clock, record_id) —
   layers are ordinary ledger rows, no second stack. Consequence pinned:
   a SET that expires at Eot leaves permanent deltas folding onto base.
2. **C18 was-snapshot** keeps base-first-fold-at-application semantics
   (journal `effective_pt` at death time — unchanged readout).
3. **Granted-ability CONTROLLER RULE**: source = the GRANTED permanent,
   every "you" = the GRANTEE (`seat`); granted rows ride
   `legal_activations`/`activate`/`ability_playable` at **negative index
   `-k-1`** (entry k of `granted_activated`, layer-seq order); no compiled
   record needed (tokens activate what they're granted — pinned).
4. Replacement filters judge the EVENT in the REPLACEMENT's coordinates
   (`replace(ctx, source, controller)`), not the damage-dealer's — the
   Nine-Lives "to you" is p0 even though the atom runs in p1's context.
5. Damage replacements only match **QUnbounded** amounts, no `source`, no
   `combat` flags — bounded caps/first-N RAISE (C-4 surface, 12e).
6. `UntilNextTurn` on LEDGER/records gets its precise next-turn-start
   expiry; the binder's DELAYED windows keep their documented Eot
   stand-in (delayed windows beyond the turn = 12e).
7. StepEvent subscription stays 12e (combat steps); the untap tick is an
   executor step emitting TapStateEvents, not StepEvents.

## Compiled-card proof (not hand-tuned IR)

* **Frost Breath** (`Tap up to two target creatures.` + `Those creatures
  don't untap during their controller's next untap step.` → b5b/b5c
  templates, Seq(TAP, PREVENT)): tap ✓, frozen across ONE owner untap
  tick ✓, free on the following ✓, only designated targets ✓, non-target
  creature comes free ✓.
* **Nine Lives** (`If a source would deal damage to you, …` + `When there
  are nine or more incarnation counters … exile it.` → b5b/b2a): damage-
  to-you consumed with NO life mutation, INCARNATION counter carried ✓,
  opponent damage unaffected ✓, detach stops protection ✓, 9th counter
  exile trigger fires ✓, subsequent damage lands ✓.

## New traps (see PITFALLS.md entries dated 2026-09-29)

* Ledger `expire()` tombstones THROUGH `_meta` — every recorded entry must
  carry a meta row (Eot/Permanent included) or detach-expiry LEAKS live
  P/T (bug found + fixed + pinned this round).
* `PREVENT_EFFECT` carries NO target role (grammar table: condition+event
  + optional controller/duration/step); the designated set rides via
  bindings/IS_ANY_TARGET.
* Raw `world.move_to_zone` is NOT journalled — trigger-visible moves must
  ride an atom (12b convention re-confirmed the hard way).
* Module-global oracle-id counters make two same-process replays differ —
  fingerprint scenarios need explicit oids (or reset).

## Still unsupported (honest list → 12e)

Repeat/EachPlayer nodes; StepEvent subscription; delayed windows beyond
the turn; combat/mana-side prevention consumers; bounded damage caps +
damage `source`/`combat` filters; PREVENT controller-scoping; static
payload shapes beyond the four verbs; keyword combat readouts (trample/
vigilance/deathtouch semantics — combat phase); GAIN_CONTROL/TAP-with-
duration semantics (frozen 12a pins kept).
