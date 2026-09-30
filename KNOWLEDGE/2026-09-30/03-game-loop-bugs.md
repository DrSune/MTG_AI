# 2026-09-30 · 03 — Round 14a: random-policy full-M21 games, PC-7 v1, and the game-loop bug ledger

Deliverables: `MTG_bot/core/executor/games.py` (harness) + `MTG_bot/core/test_executor_games.py`
(15 tests: determinism pin, deck rules, C15 decision-surface assertions, one repro per ledger row).
Core suite **1986 passed / 0 failed** (1971 + 15). Three executor fixes landed here (F-1..F-3);
the rest are ledger rows. Severity per r11: **P0** crash/misexec, **P1** silent-wrong or a
measured ceiling, **P2** cosmetic/harness-side.

## PC-7 v1 — 10 seeds × 3 pools, turn cap 60, deck-pairs-seed 1409

cmd: `.venv/bin/python -m MTG_bot.core.executor.games --seeds 10 --pool {all,engine,castable}`
(reports `/tmp/opencode/h_<pool>.json`; `--repro <seed>` re-runs one game and re-raises)

| pool | deckable | survived | mean turns | max | acts | cards that FIRED ≥1 ability | infeasible-target skips |
|---|---|---|---|---|---|---|---|
| `all` (305 goldens, flags ignored) | 285 | **0/10 (0%)** | 9.0 | 44 | 92 | 14 (5.2% of 286) | 12 |
| `engine` (286 engine-supported) | 267 | **1/10 (10%)** | 17.4 | **60 = cap** | 229 | 21 (7.9% of 286) | 9 |
| `castable` (76 spell-node + lands) | 91 | 0/10 (0%) | 2.0 | 8 | 38 | 9 (3.4% of 286) | 7 |

Read this as **the engine dies, not the policy**: 30/30 games ended in an exception except one
engine-pool game that reached the turn cap. `engine` outlives `all` because a flagged card raises
loudly at cast and is never reached, while an engine-supported card gets cast and then raises
deeper. `castable` dies *fastest* because concentrating the spells concentrates the check-land
ETB cycle that carries B-4. Coverage is deliberately a separate number: 5-8% of the engine cards
fired an ability in 10 games, which is a **harness reach** number, not an engine correctness one.

## F-1..F-3 — executor fixes landed in this round (repro-first, tests flipped to green)

- **F-1 turn draw (CR 504.5).** `begin_turn` opened upkeep with **no draw at all** — a game loop
  could never be played. Added the journalled `_TURN_DRAW` atom (module-level frozen `Atom`,
  DRAW controller=YOU amount=1) run inline between the UPKEEP and FIRST_MAIN markers so the
  `CARD_DRAWN` event keeps its clock position *after* upkeep triggers. `test_executor_binding.py::
  _replay_chain` amended in place (hand 2→3, gy stays 2: the third mill hits a 5-card library).
- **F-2 = B-2 fixed.** `legality._zone_handles` raised `NotImplementedError("Zone(STACK)
  enumeration needs the stack (queue shapes are OUT of round 12)")` — round-12 truth made stale by
  13b, which grew a real stack (`stack.stack_zone` mirrors cards into each seat's `ZONE_STACK`).
  It now answers (OWNER-scoped, else `players_for_ref` × stack zone). Why it mattered: M21
  **Unsubstantiate** prints a `BATTLEFIELD + STACK` TARGET selector, so `legal_casts` folded its
  cost and called it castable, and the *very next public query* (`spell_target_slots`) raised —
  the query surface disagreed with itself. No test pinned the raise (`ZONE_STACK ∉ PLAYER_ZONES`
  at `test_executor_stack.py:1098` is the parking fold, unaffected); `Zone(ANY)` keeps its 12a
  meaning because the stack stays out of `PLAYER_ZONES`.
- **F-3 = B-8a fixed.** `_v_choose` called its own query as
  `verb_choose_options(executor, atom, source=ctx.source, controller=ctx.controller)` — **dropping
  `ctx.bindings`**, and the query then rebuilt a context from scratch. So a CHOOSE atom whose pool
  is scoped to the spell's target (Duress/Kitesail: `Zone(HAND, TARGET_PLAYER)`) raised
  `TARGET_PLAYER needs a bound target` **inside the runtime handler that was holding the binding**.
  Additive `bindings=` kwarg on the query + forwarded at the handler; every pre-14a caller is
  byte-identical. Test: Duress now casts with a designated opponent and that opponent discards.

Harness-side (not engine claims, all documented at the use site): multi-target rows are a counted
skip (`stack._validate_spell_targets` raises on >1 TARGET selector → B-3); `TARGET_PLAYER`
designation mirrors the CR rule the engine itself re-checks (an opponent seat); the trigger tail
is seeded `fire`/`skip`; CR 121.3 draw-from-empty loss is a harness state check (the 13a
"state check, not a verb" ruling); the `{"target": sorted(targets)}` binding dict mirrors
`stack.cast`'s own write so pre-cast enumeration sees the population the runtime will.

## The ledger (open rows, in kill-count order)

**B-4 · P0 · DESIGN · the trigger decision channel is positional across a queue that grows
mid-drain.** 7/10 (`all`), 7/10 (`engine`), 8/10 (`castable`) — the dominant cause of death, and
the reason PC-7 v1 is ~0%. Every public op auto-`_settle`s with the `trigger_decisions` the caller
passed *before* the op, but a land drop **arms** that land's own ETB trigger inside the op, so the
drain demands a decision the caller could not enumerate. Repro (seed-pinned, in
`test_executor_games.py::CrashLedgerTest`): drop **Temple of Epiphany** — its ETB is "scry 1", and
`take_decision` rejects the only token a may-offer policy can legally have supplied:
`SCRY decision 'skip' not in ('top', 'bottom')`. Ten M21 check/fix lands carry this shape (Temple
of Epiphany/Mystery/Malady/Silence/Triumph, Tranquil Cove, Dismal Backwater, Scoured Barrens,
Wind-Scarred Crag, Jungle Hollow), so it is not an edge card. The harness cannot fix it without
replicating `TriggerBinder`'s event matcher (that would be reaching into internals, and C15
forbids it); the ledger asks for the channel to stop being positional — `ExecCtx.take_decision`
already holds the exact vocabulary at the call site, so a `decisions.take(vocab, what)` shape
gives the policy the same enumeration the query surface exposes, with zero prediction and zero
mirror vocabularies (it also retires B-5). Do NOT "fix" it with an engine-side default on
exhaustion: `_v_choose_name` already refuses a seeded-random fallback, and a hidden default is the
exact thing C15/C16 forbid. **Owner ruling needed.**

**B-11 · P0 · COMPILER · a trigger's effect is decomposed across two abilities.** **FIXED
2026-09-30 (round 14b)** — trigger-tailing mechanism in `compiler.py`
(`_trigger_trailing_idx` + capture branch, mirroring `_loyalty_trailing_idx`'s
boundary discipline); full-corpus sweep: 4 cards captured (the 3 below + Liliana,
Waker of the Dead Emblem "It gains haste."), goldens re-baselined audited
(5 files moved: 4 keys={abilities} + Liliana, Waker of the Dead keys={emblem}
transitive attach only), PC-1/2/3/4 EXACT; results in /04. Row text kept as filed.
The trigger keeps
its FIRST sentence and the rest of the same sentence is attached to the card's **SpellAbility**, so
the remainder runs at CAST time. Confirmed 3/3 on the cards that show the signature (all 6
creatures carrying a cast-time effect were checked):

| card | printed | compiled `SpellAbility` (cast) | compiled `TriggeredAbility` |
|---|---|---|---|
| Kitesail Freebooter | "When this creature enters, target opponent reveals their hand. You choose a noncreature, nonland card from it. Exile that card until this creature leaves the battlefield." | `CHOOSE, EXILE` | `REVEAL` |
| Garruk's Harbinger | "Whenever this creature deals combat damage…, look at that many cards…. Reveal them, then you may put a land card…" | `REVEAL, MOVE_ZONE, MOVE_ZONE` | `LOOK_AT` |
| Siege Striker | "Whenever this creature attacks, …" | `MODIFY_PT` | `TAP` |

Silent misexecution **and** two crash symptoms: B-9's `referent 'result' … no event register`
(castable seed 7, Seasoned Hallowblade; engine seed 6, Siege Striker) and the surviving
`TARGET_PLAYER needs a bound target` (all pool seed 2, **Kitesail Freebooter** — the `target`
coordinate lives in the *trigger*, the cast has no slot for it, and the firing context never
inherits the spell's designation, so CR 601.2i's "targets are remembered for its ETB trigger" is
unmodelled). Compiler-side, needs a golden re-baseline ⇒ r11 set-equal audit. Not harness-fixable.

**B-7 · P1 · the QUERY raises for an engine-supported card.** `CONTROLLER_COUNT_GE` is unimplemented
in the predicate evaluator and is reached from `legal_activations → legal_targets →
enumerate_candidates`, so *asking* about **Fabled Passage**'s land-swap costs a
`NotImplementedError` (1/10 in every pool; seed-pinned). Grammar/legality work, not harness.

**B-9 · P1 · C2 referents have no resolution context outside a trigger firing.**
**RESIDUATED 2026-09-30 (round 14b, after B-11)** — the two B-11-rooted instances are
gone: Siege Striker's engine-seed-6 cast crash (`QProp referent 'event'`) and the
castable-pool referent class no longer reproduce in the 10-seed reruns; Kitesail's
cast-time `TARGET_PLAYER needs a bound target` (all pool seed 2) also vanished with
B-11. The residual is Seasoned Hallowblade — no trigger at all; a static-ish
GRANT_ABILITY sits on its SpellAbility and reads `result` (pinned directly in
`test_executor_games.py::CrashLedgerTest`; still OPEN).
`_referent_handle`/`resolve_selector` raise for `event`/`result` on a *cast* (Siege Striker,
Seasoned Hallowblade). Root cause for two of the three cards is B-11; the residual is a static-ish
effect parked on a SpellAbility (Hallowblade has no trigger at all) — triage after B-11.

**B-3 · P1 · measured designation ceiling.** One designation tuple per op ⇒ a spell with 2+ TARGET
selectors cannot be cast (`NotImplementedError`, arc-3 note in stack.py). Counted per run
(`multi-target=0/1/1`) and learned-once-filtered, never silently skipped.

**B-1 · P0 · COMPILER (inherited, now measured in play).** 206 non-land deckable cards (157
creatures + 49 planeswalkers/enchantments/artifacts) carry **no `SpellAbility` node**, so
`spell_castable` answers `cast:not_a_spell` and no random policy can ever play them: the harness
reports `playable_engine=91` against 286 engine-supported cards, and 14 of the 305 goldens are
emblems/tokens excluded from decks. This is the 13b "PC-7 reads True while uncastable" note scaled
up: **casting, not verb dispatch, is the real ceiling.** Compiler + golden re-baseline ⇒ r11 audit.

**B-12 · P2 · fidelity of the harness's world.** The executor never empties the mana pool between
steps (no CR 305.2 rule exists in the package), so mana accumulates and survival is **optimistic**.
Not emulated in the harness (writing `world.players[].mana_pool` directly would be an
internal-reach); ledger note for whoever lands the real turn-structure work.

**B-5 · P2 · mirror vocabularies.** SCRY `('top','bottom')`, `MANA_COLOR_VOCAB`, the `str(i)`
CHOOSE index and the opponent-seat rule are static rules the harness re-declares because the engine
hands the policy a *slot* rather than a vocabulary. Every one is re-validated by the engine's own
`take_decision`/`_validate_spell_targets` (a wrong mirror raises). B-4's proposal deletes all four.

## C15 verdict from this round

The query surface is **sufficient for choosing** and **not yet sufficient for sequencing**: every
value the policy played with came from a query, and every death came from a *shape* the surface
cannot answer (which triggers this op arms: B-4; which population a target-scoped atom draws from
once bindings exist: B-8a, now fixed in the engine; which cards are castable at all: B-1). That is
the C15 sufficiency claim measured, honestly, with a number attached.

## Repro discipline

`--repro <seed>` re-derives decks from the same seed and re-raises the original exception; the
crash row carries `attempted` (the act in flight — `cast:Kitesail Freebooter`,
`act:Fabled Passage#0`), the last three completed act digests, and the stack contents, because the
raise usually happens before the act is logged. Determinism is pinned by
`ReplayDeterminismTest`: same seed → same `state_fingerprint`, digest, turn count and coverage.

## Next (14b, per the /02 plan)

Owner ruling on B-4's channel shape (blocks everything else); B-11 compiler fix + audited
re-baseline; B-1 castability; then re-run at 100 seeds — PC-7 stops being a verb-dispatch proxy
and becomes a game-survival number.

---

## 14b-2 STATUS UPDATE (2026-09-30, decision-channel rebuild)

- **B-4 · FIXED.** The channel is now vocabulary-addressed: `ExecCtx.take_decision(vocab, what)`
  resolves (1) the explicit per-op pool, (2) a per-`(vocab, what)` FIFO primed through
  `executor.decisions.push`, (3) an ask-time `provider` — module `executor/decisions.py`
  (`DecisionStream`). Trigger firings carry the stream, so a demand from a trigger the op itself
  armed (check-land ETB scry) is answered with ZERO prediction. `trigger_decisions` is DELETED
  from every public op, `_settle`, `fire_triggers`, `begin/end/advance_turn`, the legality
  wrappers and `binding.fire_all`'s cursor machinery. Proof: `CrashLedgerTest.
  test_b4_scry_armed_by_the_land_drop_itself_is_answered` (scripted + replay-fingerprint pinned)
  and the 10-seed rerun (scry-rejection class gone entirely).
- **B-5 · FIXED.** All four mirrors deleted from `games.py`: SCRY_VOCAB, MANA_COLOR_VOCAB, the
  `str(i)` CHOOSE walk (`effect_decisions`/`_atom_decisions`, plus the `_cast_bindings` mirror of
  `stack.cast`'s binding write), and the opponent-seat rule — the last one closed ENGINE-side:
  `spell_target_slots` now synthesizes a `TargetSlot(synthetic=True)` for a tree that reads
  `ControllerRef.TARGET_PLAYER` (candidates = opponent seats, the engine's own CR population;
  `_validate_spell_targets` stays the oracle). The policy registers
  `executor.decisions.provider = policy.answer` and mirrors nothing.
- **B-8 · CLOSED** by the same synthesized slot (designate from the query; mirrored-rule test
  replaced by `test_b8_target_player_coordinate_rides_the_synthesized_slot`).
- Runtime may-asks use the QUERY's narrowed `optional_offer` vocab (CR 117.3 query/runtime
  identity at the ASK: an unpayable `fire` is not even a legal answer anymore — amended
  `test_executor_stack.py::test_fire_on_unpayable_raises`, raise moves one station upstream).

### New crash classes (the 14b rerun; the wall moved, the games run 2–7× deeper)

| class | frame | 10-seed counts (all/engine/castable) | status |
|---|---|---|---|
| **B-13 ONE_OF/REST designation = 12c target prompt** | selectors.py resolve_selector | 3 / 2 / 3 | OPEN, dominant headwall; pinned `test_new_rest_one_of_designation_is_the_12c_gap` |
| **B-7 CONTROLLER_COUNT_GE** (pre-existing, now reachable) | quantity.py _eval_atom | 3 / 2 / 2 | OPEN; pinned DIRECTLY (seed-path pin superseded) |
| **B-14 QX undeclared X on cast** (Primal Might) | quantity.py resolve | 2 / 0 / 0 | OPEN; pinned `test_qx_undeclared_x_raises_loud_on_cast` |
| **B-15 TARGET selector with no designation** | selectors.py resolve_selector | 1 / 1 / 0 | OPEN, un-attributed; repro via `--repro` seeds (all:4, engine:8) |
| **B-16 `zone_of(player:0)` KeyError** (a player handle reaches a card-zone read) | state.py zone_of | 0 / 1 / 0 | OPEN; engine seed 2 |
| **B-9 result referent outside a trigger** (Hallowblade residual) | selectors.py | 0 / 1 / 2 | OPEN as of 14b-1, still kills |
| **B-17 FLIP_WON needs a recorded FLIP_COIN** (Tavern Swindler second row, bare ctx) | quantity.py | 0 / 0 / 2 | OPEN |
| **B-18 DISCARD a card not in hand** (Bad Deal cost-plan staleness) | verbs.py _v_discard | 0 / 0 / 1 | OPEN |

---

## Round 14c close-out (same day) — six classes closed, the wall moved to the B-7 family

All six round-14c targets were root-caused against the compiled IR + live probes BEFORE
fixing; the statuses below SUPERSEDE the 14b-2 table rows (which stay as history).
Evidence files: `/tmp/opencode/c14c_{all,engine,castable}.json|.log`,
`/tmp/opencode/c14c_engine30.json`.

| class | status after 14c | fix / ruling | pinned |
|---|---|---|---|
| **B-13 ONE_OF/REST** | **FIXED** | ONE_OF asks the decision channel with the Handle-sorted candidate list as the EXACT vocabulary (C15 enumerate-then-answer; 1 candidate forced, 0 candidates = C17 nothing, exhaustion = loud ValueError); REST = deterministic complement of `ctx.one_of_pick`, no ask. MOVE_ZONE partition guard (no draw-idiom, no count clamp) | `test_new_rest_one_of_designation_is_the_12c_gap` (AMENDED green) + verbs/library ONE_OF pins amended |
| **B-14/QX effect-side** | **FIXED at cast** | CR 601.2f: X is declared WITH the total cost — `cast()` re-folds the legality X=0 witness (CR 107.1) and binds `x_value`, so effect-side QX reads the SAME declared X. Unbound OUTSIDE a cast still raises (13b pins untouched); direct `cast(x=None)` on a X-spell now resolves at 0, not crashes | `test_qx_undeclared_x_raises_loud_on_cast` (AMENDED: falls past QX to the NEXT class, `verb FIGHT not implemented`) |
| **B-15 TARGET-in-`cards`-role** | **FIXED** | TARGET-mode Selector reads the spell's `target` designation (CR 601.2c one designation) ∩ still-legal population, whatever role it sits in; UNdesignated stays loud | `test_b15_cards_role_target_designation_flows` (Rise Again golden, both legs) |
| **B-16 zone_of(player) KeyError** | **FIXED** | `role_handles`: bindings no longer HIJACK an anaphoric Selector (`referent` set) — Necromentia's EXILE re-read its own SEARCH result instead of the designated opponent; `_v_search` now writes the 13b `result` register | `test_b16_target_binding_does_not_clobber_referent_selector` |
| **B-17 FLIP_WON at cast** | **OPEN — design level** | Scryfall-verified Tavern Swindler = "{T}, Pay 3 life: Flip a coin. If you win the flip, you gain 6 life" — NO cast effect exists; the golden attaches the ACTIVATED tail to the SpellAbility (the B-11-family tail split, one card deeper). A correct executor fix is IMPOSSIBLE (the tree is wrong; fixing = compiler/golden re-baseline = frozen scope). The 13a raise (no inference on a missing flip) stands | eval-side raise pins unchanged |
| **B-18 DISCARD not-in-hand** | **FIXED** | probe-proved NOT staleness: compiled Zone(HAND, ANY) spans BOTH hands and the sorted CHOOSE stand-in took the CASTER'S cards. `_v_discard` re-scopes to the actor's LIVE hand at take time (CR 701.8a); referent/TARGET/partition selectors keep self-resolving | `test_b18_discard_scoped_to_the_actors_live_hand` (+ old `TestBadDeal` still green) |

**14c re-measure (same recipe: 10 seeds × 3 pools, deck-pairs 1409):**
all 1/10 28.7t cov34 → **2/10 35.9t cov41 (15.4%)**; engine 3/10 38.8t cov39 →
**6/10 46.2t cov44 (16.5%)**; castable 0/10 14.0t → **0/10 18.3t cov39**.
Engine pool 6/10 ≥ 5/10 ⇒ **PC-7 v1.1 30-seed run: 10/30 (33.3%), mean 34.9t,
cov 51 cards = 19.1% of engine_supported=286, 2021 actions.**

**Crash map after the fix (10-seed pools, 22 crashes):** B-7-family filter predicates
**13** (CONTROLLER_COUNT_GE 3/3/0 + CAST_THIS_TURN_FROM 0/0/4 + MOVED_TO_ZONE_THIS_TURN
6/0/0 — all `quantity.py:512` "filter pred … not implemented"); B-9 result-referent
outside firing **3** (unchanged, open); B-17 **3** (design-level above); new class **2**.

| NEW class | frame | counts | status |
|---|---|---|---|
| **B-19 Zone(STACK) RUNTIME enumeration KeyError** (B-2's runtime twin: query side fixed 14a, `ZONE_KIND_TO_STATE` has no STACK entry so Unsubstantiate-shape MOVE_ZONE dies on a bare `KeyError(ZoneKind.STACK)`) | selectors.py enumerate_zone:137 | all 1, castable 1, engine30 2 | OPEN — small honest fix next round (enumerate parked stack frames, same source as `legal_targets` STACK); pinned `test_new_zone_stack_runtime_enumeration_raises` |
| **B-7 family growth**: MOVED_TO_ZONE_THIS_TURN (Necromentia CREATE_TOKEN — reachable since B-16 closed) and CAST_THIS_TURN_FROM join CONTROLLER_COUNT_GE as the now-DOMINANT class (13/22) | quantity.py _eval_atom | 6/3/4 | OPEN (journal-backed preds = 12c query surface work); pinned `test_new_moved_to_zone_this_turn_pred_stays_unimplemented` |
| Verb **FIGHT** has no handler (Primal Might's next station once QX closed) | verbs.py run_atom | all 1 | ledger only (unimplemented-verb family) |

Gate: core **2001 passed** (+5 pins vs 1996), PC-1 0.9869 / PC-2 0.9922 / PC-3 0 /
PC-4 0-diff EXACT (grammar untouched), pyright 0, ruff delta 0 (executor statistics
byte-identical to stock).

---

## Round 14d close-out (same day) — the B-7 journal family + B-19 close; PC-7 v1.2 = 60%

**STATUS FLIPS (supersede the 14c rows; details + design note in /07):**

| class | status after 14d | fix | pinned |
|---|---|---|---|
| **B-7 filter-pred family** | **FIXED (as demanded by games)** | `ExecCtx.journal` bound at EVERY ctx site (executor/query/legality/binder/layers — "journal-is-state": purity = determinism, not amnesia; doc /07); CONTROLLER_COUNT_GE (world count), MOVED_TO_ZONE_THIS_TURN (handle-scoped vs gate-existential, discriminated by the handle sitting in the destination zone), ENTERED_THIS_TURN_FROM, CAST_THIS_TURN_FROM (13b CAST rows), DIED_THIS_TURN (C18 rows — NO WAS_* pred exists in the frozen vocab, verified), IS_EXILED_WITH_SOURCE (world half + whole-journal cause read). Bare ctx still raises naming the pred (no half-preds); TURN_OF/ZONE_COUNT_GE/WAS_CAST/etc. stay loud (games never demanded them). **NEW faces of the same raise: POWER_GE (2), CMC_LE (1)** — world-evaluable twins, next round's small fix | `test_b7_controller_count_ge…` (AMENDED green), `test_new_moved_to_zone…` (AMENDED: answers False on empty history; FLIP_WON leg unchanged), `Round14dJournalTest` ×4 positive + bare-ctx pin |
| **B-19 Zone(STACK) runtime** | **FIXED** | `enumerate_zone` STACK branch enumerates parked frames via `stack.stack_zone` (F-2's source, §8.3 identity; TOP = top frame; OWNER keeps the honest 12b raise) | `test_new_zone_stack_runtime_enumeration_raises` (AMENDED green: park→MOVE_ZONE→hand) + OWNER/empty legs |
| **B-17 activation tail** | **OPEN — SCOPE-STOP per ruling** | Inventory (305-card sweep, /tmp/opencode/inventory_r14d_b17.py): Tavern Swindler + Waker of Waves clean tails WOULD fix; **Seasoned Hallowblade ruling-collision** (printed "Discard a card: Tap…It gains indestructible…" IS an activation tail, but capturing it is forbidden by the 14c ruling and does NOT fix it — the GRANT reads the `result` referent = B-9); **Chandra [−9] "Add six {R}." boundary-ambiguous** (the empty-cost OPT(CAST) permission idiom breaks the r11 loyalty chain — the specified matcher mis-captures it). STOP condition fired (ambiguity + collision): compiler/goldens/PC UNTOUCHED, raise pins stand. Next: adjudicate (b)-style exempt-idiom matcher + Hallowblade jointly with B-9 | eval-side raise pins unchanged (2 engine30, 3 castable10) |

**14d re-measure (same recipe):** all 2→**8/10** (52.6t, cov46); engine 6→**7/10** (53.5t,
cov46); castable 0→**1/10** (30.6t, cov43); **engine 30 seeds 10/30→18/30 (60.0%),
mean 48.5t, cov 60 cards, 3004 acts**. PC-7 v1.1→**v1.2 60.0%**. Crash recount
(10-pools 22→**11**; engine30 11): B-7-family + B-19 GONE; wall now **B-9 result-referent
at cast — 8/11 engine30, new face `cast:Feat of Resistance`** + Hallowblade kin;
B-17 2; POWER_GE/CMC_LE 2+1; FIGHT 1.

Gates: core **2007** (+6 pins, 3 frozen AMENDED), PC-1/2/3/4 EXACT (goldens never
moved), pyright 0 (edited scope; repo delta 0 = 524→524), ruff delta 0, replay
determinism green.

---

## Round 14e close-out (same day) — B-9 producer register, B-17 capture (exemption), POWER_GE/CMC_LE; PC-7 v1.3 = 86.7%

**STATUS FLIPS (supersede the 14d rows; design + audit in /08):**

| class | status after 14e | fix | pinned |
|---|---|---|---|
| **B-9 result-referent at cast** | **CLOSED for the in-execution anaphora — ONE residual face named** | The register = `ctx.bindings["result"]`, written by PRODUCER atoms inside one effect execution: SEARCH/CHOOSE (14c) + **TAP/UNTAP/PUT_COUNTER/MOVE_ZONE (14e)**; scope per resolution (fresh bindings dict per ctx); unset read still RAISES (message rewritten — the old "only inside a trigger firing" became false). `event` stays firing-only. RESIDUAL: **Chandra, Heart of Fire #4** — the B4 permission row's `referent='result'` is a CROSS-resolution anaphora ("cast them" = cards exiled by the [−9]'s resolution); fix = B4-template fidelity emitting the 14d `IS_EXILED_WITH_SOURCE` filter (golden-moving fidelity class, own audit — deliberately not forced here) | `CrashLedgerTest.test_b9_result_referent_resolves_from_resolution_producers` (AMENDED green: Feat cast resolves, Hallowblade activation grants, unset read raises, cast = B-1 not_a_spell) |
| **B-17 activation tail** | **CLOSED (capture landed per adjudication)** | compiler `_activation_trailing_idx` + `_is_cast_permission_row` EXEMPTION (the empty-cost OPT(CAST) permission idiom is a TRANSPARENT boundary: never an owner, chain sees through it; loyalty abilities stay R11-1-owned). Inventory-first sweep: **3 captures** (Swindler Seq(FLIP_COIN; IF(FLIP_WON)→GAIN_LIFE), Hallowblade Seq(TAP; GRANT(result)), Waker Seq(LOOK_AT; Seq(MOVE ONE_OF; MOVE REST))); Chandra = 1 transparent skip, NOT captured ("Add six {R}." status quo). Golden audit: pre-snapshot /tmp/golden_pre_r14e_2026-09-30, diff == inventory set-equal, keys={abilities}, PC EXACT. Swindler+Hallowblade lose the accidental SpellAbility → B-1 set (playable_engine 88→86 — the crash MOVED, per ruling); no new ambiguity → no STOP re-fire | `TestActivationTrailing` ×3 (tail ownership / permission transparency / loyalty boundary); library Swindler e2e AMENDED (ONE activation: flip→gate→+6 in-engine); compiler chain-test AMENDED (boundary half holds, ownership half flips) |
| **POWER_GE / CMC_LE** | **CLOSED** | world/identity preds in `_eval_atom`: POWER_GE on the LIVE `effective_pt` (layers folded, absent-power=False convention); CMC_LE = `identity.cmc or 0` (the QProp CMC field's own convention — token mv 0), QX-capable off the declared X | `Round14eWorldPredTest` ×3; legality probe AMENDED (CMC_GE keeps the loud-pred probe now that CMC_LE answers) |
| **new faces (census, no fix this round)** | OPEN, named | **KEYWORD_HAS** (Run Afoul "target creature with flying" — world-evaluable via layers, the same small-fix family, next round); **EachPlayer node** (Goremand — 12e node vocab); **Waker's static −1/−0 MODIFY_PT on its SpellAbility** (pre-existing static-family miscompile visible before/after capture, T8-era family) | ledger rows (crash counts in /08 table) |

**14e re-measure (same recipe):** all 8→**9/10** (55.1t, cov45, 1 crash=FIGHT); engine
7→**9/10** (59.9t, cov48, **0 crashes**, first natural "game over" endings appear);
castable 1→**5/10** (53.6t, cov57, 3 crashes: EachPlayer 2, KEYWORD_HAS 1); **engine 30
seeds 18/30→26/30 (86.7%), mean 58.6t, cov 61 = 22.8%, 3753 acts**. PC-7 v1.2→**v1.3**.
Engine-30 wall = ONLY the Chandra cross-resolution permission face (3/30) — plainly NOT
flagged-verb/combat-only: combat (arc-3) remains UNREACHED at mean 58.6/60t, the flagged
deaths live in `all` (FIGHT) and `castable` stays honestly crash-heavy.

Gates: core **2013** (+6 pins, 3 frozen AMENDED), PC-1/2/3/4 **EXACT** (goldens moved ONLY
via the capture audit), engine_supported 286 EXACT, pyright 0 (repo 524→524), ruff delta 0,
replay determinism green.
