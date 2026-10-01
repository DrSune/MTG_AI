# 05 — Wave 2 fix-batch 19a (engine editable, authoring closed)

Scope: the six wave-2a suspects. **Five root causes fixed in the executor;
one confirmed STOP** (frozen golden). Authoring respected: suspect packs
changed ONLY by promotion (strip `status`/`finding`) plus the two documented
exceptions below. Regression suite: `MTG_bot/core/test_executor_r19a.py`
(22 tests).

## The six verdicts

1. **Basri's Solidarity — P/T counters were invisible to the P/T fold.**
   `DurationLedger.effective_pt` folded only recorded MODIFY_PT changes;
   the counters map (`world.cards[h].counters`) never entered the fold.
   Fix: optional `counters` param on `effective_pt`/`_effective`; the
   PLUS_1_PLUS_1 − MINUS_1_MINUS_1 sum folds AFTER the timestamp stack
   (CR 613.3b), `*` P/T stays undefined (CR 613.3a caveat 406.4-era rule:
   a counter never materializes `*`). Call sites updated: ctx.effective_pt,
   SBA toughness, lethal_of, combat power, CREATURE_DIES was-snapshot,
   both run_scenarios pt assertion lanes. Passing no map stays byte-exact.

2. **Fungal Rebirth — IS_PERMANENT read the ZONE, not the CARD.**
   The old predicate asked "is this handle on the battlefield", so a
   creature CARD in a graveyard failed "creature card in a graveyard".
   Fix (`quantity._eval_atom`): CR 110.1 type-line test via
   `_PERMANENT_TYPE_WORDS` (Artifact/Creature/Enchantment/Land/
   Planeswalker/Battle), zone-independent; handles not in `world.cards`
   (players) answer False. Battlefield behaviour byte-identical (Unsub-
  stantiate's Instant target still non-permanent).

3. **Life Goes On (shared pred) — DIED_THIS_TURN was handle-blind-dead.**
   A Conditional judged over the resolving SPELL or a player could never
   match a CREATURE_DIES subject, so "if a creature died this turn" was
   silently False. Fix: handle-scoped read first; else EXISTENTIAL (any
   dies this turn) iff the judged handle could never itself be the dead
   creature (player namespace, or printed type line names no Creature).
   Creature-typed handles keep the strict read — Gadrak/Standard Bearer
   censuses unchanged.

4. **Life Goes On — the life-gained replacement lane did not exist.**
   A resolving instant's ReplacementAbility node was registered nowhere
   (the lifecycle attaches permanents only). Fix: `register_ephemeral_
   replacements` (Eot tag + DurationEot, registered from BOTH stack resolve
   lanes before the effect runs, so the spell replaces its own +4),
   `replacement_for_life_gained` interceptor in `_v_gain_life` (YOU gate
   raises for non-YOU — flag not guess; consumes the event, action drains
   as a nested journalled effect), CR 614.4a loop guard via `ExecCtx.
   replaced_seq` (the replacement's own +8 is never re-replaced),
   `sweep_at_eot` now also expires "Eot"-tagged replacements.

5. **Chandra, Heart of Fire — printed loyalty was dropped at identity.**
   `games.identity_of()` silently omitted `record.loyalty`, so the binder's
   LOYALTY seed (which reads `identity.loyalty`) never ran: every cast
   planeswalker entered with an empty counters map. Fix: one field.
   (Seed itself and cast lane were verified fine.)

6. **Cultivate — SEARCH delivered to a placeholder destination and the
   partition never asked.** The compiled Seq is SEARCH(dest BF, placeholder)
   → REVEAL → MOVE_ZONE ONE_OF(BF, tapped) → MOVE_ZONE REST(hand) →
   SHUFFLE; `_v_search` moved both lands to BF untapped, emptying the zone
   the ONE_OF/REST atoms re-search, so the ask never fired and the tapped
   stamp was lost. Fix: the Seq walker pre-scans for MOVE_ZONE siblings
   carrying ONE_OF/REST selectors (`search_partition`); in that mode SEARCH
   DESIGNATES ONLY (found cards stay in the zone, `result` register +
   SEARCH/designated rows). A lone SEARCH (Solemn Simulacrum shape) still
   delivers — pinned.

## Decision-lane discovery (binding for future authoring)

`ExecCtx.take_decision` lanes: (1) per-op POOL validated RAW against the
vocabulary — NO key/name mapping; (2) stream; (3) provider, which maps
PACK KEY→handle (run_scenarios.py:223-229). Consequences, all pinned:
- designation-ask answers in a cast effect's POOL must be the handle
  strings themselves (`"card:1"`), not pack keys — cultivate.json ships
  `decisions: ["card:1"]` (exception #1 below);
- bad_deal's `['c1','c2']` never reach take_decision (its designation goes
  through the key-mapped `_search_designation` bindings lane) — surplus
  pool words are unused, not wrong;
- grim_tutor's `"Cardinal"` is a NAME-declaration ask (vocab = card names,
  verbs.py `_v_name`); names are legal there.

## Exception #2 — trufflesnout.json assertion corrected (green pack)

Scryfall m21/212 prints **2/2**; the ETB counter makes it 3/3. The pack
asserted 2/2 — i.e. it encoded the pre-19a counters bug (it was only ever
green because the fold ignored counters). The counter fix necessarily made
it red; expected power/toughness corrected 2→3 with the Scryfall evidence
in `notes`. This is the documented pattern: a green pack that was green on
a silent bug must be corrected to the printed truth, never reverted.

## STOP — Destructive Tampering (remains in suspects)

Golden e6ae536a compiles "creatures without flying can't block this turn"
to a pure `PtDelta INCREASE QConst(0)` MODIFY_PT Eot entry — ZERO semantic
payload; the frozen IR has no can't-block marker and the executor has no
blocking-restriction layer (the grammar flag for this construct is an
open compiler-batch item). Fabricating an IR marker would violate both the
frozen-golden law and flag-not-degrade. Post-fix the pack's failure
signature SHARPENED (proof the engine now runs the rest faithfully):
`blocked[atk]: expected [], got ['wall']`, `life[1]: expected 18, got 20`
— the Wall legally blocks a flier-less attacker because nothing says it
can't. Leave suspect; route to the compiler campaign.

## Gates (2026-10-01, HEAD 0ff4d7f + this batch)

- `tools/run_scenarios.py` → **131/131** (126 baseline −1 trufflesnout-red
  mid-batch +5 promotions; final clean).
- `pytest MTG_bot/core -q` → **2134 passed + 4 subtests, 0 failed**
  (2112 baseline + 22 r19a).
- `tools/measure_grammar.py --with-engine-flags` → PC-1 **301/305**,
  PC-2 **634/639**, PC-3 **0**, PC-4 **0 diffs** — all EXACT vs baseline
  (compiler untouched). PC-6/PC-8 unchanged pre-existing FAILs (values
  byte-identical to the 2026-10-01 T5 rows).
- `tools/traces/catalog.py compare` → 5/10 seeds diverged, every diff
  attributed (LOYALTY COUNTER_PLACED rows on planeswalker casts; SEARCH
  designate rows; downstream clock shift). `repin` → compare **0/10**.
- `pyright` on the 8 touched engine files + the new test → **0 errors**.
  `tools/run_scenarios.py` keeps its **6 pre-existing** Counter-inference
  errors (verified pre-existing at HEAD via `git stash`).

Touched engine files: executor/{games,durations,quantity,events,
replacements,verbs,__init__,stack}.py + tools/run_scenarios.py (assertion
lanes pass counters). No state.py, no compiler, no golden, no git commits.
