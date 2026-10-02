# 24. Wave-5 fix-b (r22b): damage/draw/counter replacement consumers (2026-10-01 session, closed 2026-10-02)

## Scope
The three wave5a suspect packs had no engine consumer — the replacement
registered at attach but the apply pipeline raised or ignored it. This fix
lands the three consumers, promotes the packs, and adjusts the harness.

| Card | Event | Doctrine | Idiom |
|---|---|---|---|
| Fiery Emancipation | DamageDealtEvent(QX, univ, source=CONTROLLER_IS YOU) | **MODIFY** | action `Atom(DEAL_DAMAGE, amount=QBin(MUL, 3, QProp(event, AMOUNT)))` rewrites the event quantity in place |
| Teferi's Ageless Insight | CardDrawnEvent(YOU) + NOT_FIRST_DRAW_THIS_STEP(YOU) | **REPLACE** | original draw never happens (CR 614.3a, library untouched); action DRAW(2) runs in the drain |
| Conclave Mentor | CounterPlacedEvent(PLUS_1_PLUS_1, univ) | **REPLACE→chain** | queued 4-tuple (rec, card, kind, n); drain binds `{"event":[card]}` + `inner.event_counter_count=n` so `ADD(QProp(event,COUNTER_COUNT),1)` reads 1 → lands 2 |

## IR ground truth vs mission brief (both corrections documented here)
- **Fiery is TRIPLE, not double** — frozen golden `QBin(MUL, QConst(3), …)`.
- **Teferi's golden has NO discard atom** — the printed "exile the top card"
  half never reached the IR; the engine implements what the golden says:
  replaced draw → DRAW(2), nothing exiled.
- **Grammar deviation (deliberate)**: `NOT_FIRST_DRAW_THIS_STEP` is
  STEP-scoped (the frozen grammar's own name). Real MTG rules are
  TURN-scoped ("first card each turn"): a upkeep draw BEFORE the draw step
  is not replaced by the real card but IS doubled here. Flag-level, logged.

## Implementation map
- `replacements.py`: `replacement_for_damage(ctx, victim, dealer, amount, combat)`
  (both lanes; consume vs modify decided by action verb; `_is_player_only_filter`
  gates the player idiom "to you" OFF the card lane — Nine Lives never vetoes
  creature damage), `replacement_for_card_draw`, `replacement_for_counter_placement`;
  old `replacement_for_player_damage` deleted (verbs.py was its only caller).
- `verbs.py`: `_v_deal_damage` consults per victim (DAMAGE_MODIFIED row arity 6,
  `DAMAGE_REPLACED` kept byte-identical for the Nine Lives consume);
  `_deal_damage_to_card` consults (card-damage CONSUME has no consumer → loud
  NotImplementedError, flag-not-degrade); `_v_draw` consult + `DRAW_REPLACED`
  row + draw-step ordinal stamp; `_v_put_counter` consult + `COUNTER_REPLACED`
  row + 4-tuple queue.
- `__init__.py`: Executor gains `_draw_step_open` / `draw_step_ordinal`
  (transient like `_combat_wave_open`, never fingerprinted); `_turn_draw`
  sets/clears the window; drain unpacks entry by length: bare=life/damage/
  draw consume lane, 2-tuple=zone lane, 4-tuple=counter lane.
- `quantity.py`: `ExecCtx.event_counter_count` register (COUNTER_COUNT prop
  reads it inside the counter-replacement action, else the old sum-of-counters);
  `NOT_FIRST_DRAW_THIS_STEP` atom evaluation (outside any draw-step window →
  True = "not first"; inside → ordinal>0).
- `tools/run_scenarios.py`: cast lane lifts `player:N` decision tokens into
  explicit targets (CAST-time multi-candidate targeting stays loud by policy;
  the pack says WHO, seat-indexed).

## Duplicate-carrier policy (asymmetry by design)
- Damage: TWO live matching records → **raise** (CR 616.1 choice belongs to
  the damaged player, unmodeled).
- Draw/counter: **first match**; the drain's CR 614.4a `replaced_seq` union
  guard makes the duplicate CHAIN on the replacement's own event — two
  Teferis draw 4, two Mentors make +1 → +3. Both CR-correct chainings.

## Pack promotion (3: 278 → 281)
- `git mv` suspects → `tools/scenarios/`, `status`/`finding` stripped.
- **One setup fix**: fiery pack's brute 2/2 → 2/**3**. Damage marks vanish
  with the corpse (standing harness convention, see shock.json note), so the
  2/2 negative case asserting `damage: brute 2` could never observe anything;
  2/3 survives the non-tripled 2 (observable ledger entry) and would still
  die to a wrong 6 — the lane keeps its discriminating power.

## Gates (all green, 2026-10-02)
| gate | result | command |
|---|---|---|
| scenarios | **281/281** | `.venv/bin/python tools/run_scenarios.py` |
| core suite | **2261 passed + 3 subtests, 0 failed** (2249 baseline + 12 new r22b) | `pytest MTG_bot/core -q` |
| grammar | PC-1 301/305 · PC-2 634/639 · PC-3 0 · PC-4 0 — exact baseline | `tools/measure_grammar.py --with-engine-flags` |
| fingerprints | **0/10 seeds diverging, no repin** (new consults inert without matching records) | `tools/traces/catalog.py compare` |
| games | **100/100 games, 0 crashes** (61 667 journal entries) | `tools/traces/catalog.py build --pool all --seeds 100 --catalog /tmp/…` |
| lints | pyright **0 errors** on all touched files; ruff **Δ0** (2 I001 self-fixed) | `pyright …` / `ruff check` |
