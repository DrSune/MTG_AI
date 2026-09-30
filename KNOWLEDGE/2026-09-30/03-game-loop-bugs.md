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
