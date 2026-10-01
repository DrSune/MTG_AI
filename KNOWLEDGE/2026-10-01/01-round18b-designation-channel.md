# 2026-10-01/01 — Round 18b: the trigger TARGET-designation channel (shipped, uncommitted)

The wave-1b loud-gap family (doc 18): 12+ ETB/dies/draw triggers crashed
"TARGET selector has no designation" because ONLY the cast lane designates
(CR 601.2c). CR 603.1: a triggered ability is put on the stack **with its
targets already chosen** — for the engine's direct-resolution model that
means BEFORE the effect's first verb runs. Round 18b ships that channel.

## The channel (`TriggerBinder._fire` → `_designate`)

Designate-then-apply, mirroring `stack.cast`: candidates come from the
engine's OWN 12c query surface (`query.legal_targets` +
`_widen_any_target` — §8.3, one population), the choice asks the 14b
vocabulary-addressed stream with the Handle-sorted candidate list (the
ONE_OF ask's C15 shape), site tag **`target:<seat>:<source>:<digest>`** —
four segments so the ABILITY CONTROLLER's seat is attributed (CR 603.1
cross-seat ruling; a mirror pair asks two different keys, no collision).
The answer lands in `ctx.bindings["target"]` before `_run_effect`.

**TARGET_PLAYER routing table (event-kind driven, per-card faithful):**
DAMAGE firing → the dealer (16a, pre-existing in `_ctx`); **CREATURE_DIES
firing → the dead creature (18b, in `_fire`)** — `players_for_ref` folds
it to its controller, so Massacre Wurm's "that player" is EVENT-bound, no
ask, exactly the DAMAGE-dealer ruling mirrored; self-origin firings
(your ETB, your draw — Kitesail Freebooter, Teferi's Tutelage) → the
ability controller's OPPONENT seats, duel-size 1 → §1.4 forced auto-fill
(no ask). Multi-slot triggers (two distinct TARGET selectors, or a
selector + TARGET_PLAYER without an event antecedent) keep the loud raise
— per-slot designation is /06 arc 3, never guess-bind the second.

**Honesty rules:** zero candidates → bind EMPTY = CR 603.4 "resolves doing
nothing" (never the 12c crash, never a guess); QConst(1)/single candidate
auto-fill no ask; C17 multi-pick: QAtMost's FIRST pick mandatory (frozen
TARGET+QAtMost designation range 1..n — the query lane's pinned contract),
later picks carry the block-lane `"NONE"` stop token; QAtLeast/QX-in-
TARGET triggers stay flagged (not a frozen-IR shape). Designation asks
fire BEFORE a may-offer (targets at trigger-time precede resolution-time
"may"); a skipped may wastes a designation only — invisible, no state.

## Zone(ANY) at runtime + CR 109.5

`selectors.enumerate_zone(ANY)` (was 12c's raise) = the seat ×
PLAYER_ZONES union — the EXACT loop `legality._zone_handles` answers for
the query lane (§8.3 identity pinned both directions); OWNER+ANY stays
flagged. The TARGET legality set for a UNIVERSAL-filtered ANY selector
joins the seats (CR 109.5 "any target" includes players) —
`_is_any_universal` is `query._widen_any_target`'s twin predicate, shared
so one widening opinion serves both lanes. **OMNISCIENT v1 model gap,
documented (not silently patched):** libraries and the opponent's hidden
hand ride the candidate union — a REAL player could never see a library
card to target it; the hidden-info narrowing for opponent-facing query
answers is deferred (same class of documented simplification as
combat-uninterrupted). A policy CAN legally pick a hidden universal ANY
target via the ask; damage on a hidden card is inert (SBA-invisible) —
flagged for the hidden-info round.

## Query-lane pred parity (one evaluator, both lanes)

`_eval_atom` gains **CMC_GE** (Fierce Empath's CMC-6 search filter — CMC_LE
twin, token cmc-absent = 0 convention), **ZONE_COUNT_GE** (R6-2, Thieves'
Guild Enforcer gate: TRUE iff ANY denoted player's zone reaches the
threshold under inner_filter; WHO-driven, non-card zone flagged never
zero-counted), **NAME_PARTITION_COUNT_GE** (C26/R10-2, Chrome Replicator:
EXACT-name partitions among permanents the ABILITY CONTROLLER controls —
the opponent's twins never count toward mine); `_prop_value` gains
**THAT_MANY_COUNT** reading the 14e `result` register (absent = LOUD —
no zero-reading: the compiler only places it in a mandatory continuation;
contrast 16b THIS_WAY's benign 0 for a declined may), and **DISCARD joins
the result-register producers** (`verbs._v_discard` writes the discarded
set, even when empty — Kinetic Augur's "then draw that many" counts the
action's objects, 14e B-9 ruling). The unsupported-pred probe in
`test_executor_legality.py` migrated CMC_GE → LIFE_LEAD_OVER_START_GE
(the file's own amendment convention).

## Pack surgery (21 repatriated; tools/scenarios now **84/84**)

Harness upgrade: a `decisions` word that names a PACK KEY resolves to that
card's handle before the vocab check (packs say WHO, not numbering).
Authoring fixes found en route (pack bugs, not engine bugs): two packs
spelled the counter key "+1/+1" (grammar enum is PLUS_1_PLUS_1);
**kitesail_freebooter** hid its instant in the CONTROLLER's own hand —
"target opponent reveals" needed the card on seat 1; **niambi** pack's
Bear defaulted cmc 2 against a printed 3 (expect 23 proved the author
arithmetic); **terror** expect hardened with the Walking-Corpse 2-damage
life promise ({} → life {"1":18}); **kinetic_augur**: the golden (and
live compile) is the bare `Seq[DISCARD 2, DRAW THAT_MANY]` — the printed
"may … if you do" never reaches the IR (compiler-side gap, goldens
FROZEN) → expect rewritten to the fire branch, which now verifies the
THAT_MANY wiring; its static SET_PT (layers lane, B-22 family) stays
unasserted/deferred. Forced-designation packs (mutt, ghostlight, dowser,
barrin, acolyte-pair auto path, massacre, tutelage, chrome, enforcer)
need NO decision — no ask happens.

## Gates (all re-run after the final edits)

core **2112** (+16 pins, `test_executor_designation.py`; 1 AMENDED
probe); scenarios **84/84**; suspects **0/2** (capture_sphere: cast-lane
permanent-death gap, out of scope; wildwood_scourge: QX-into-ETB-state
cast lane, out of scope — both stay loud by design); catalog compare
**0 diverging of 10** (byte-identical journals — NO re-pin needed: the
engine-batch cards never hit designation paths, the cleanest possible
reconciliation); `test_replay.py` 1 pass; PC-1..5/9/10 EXACT (PC-4 0-diff
= goldens frozen); **PC-8 UNCHANGED 98/305 = 0.3213 — honestly: PC-8 is a
compiler-side pool property (coverage.py counts entries with a
TARGET-mode selector); executor designation work CANNOT move it. The
executor truth for this round is the 12-card lane: what crashed dispatches
now run. Closing PC-8 is grammar-side.** Engine-flags census unchanged
**297/305 · 45 verbs** (static dispatch count, designation-blind — same
honest statement). pyright 0 on touched files (2 pre-existing harness
diags unchanged); ruff delta 0 (net repo −13).

## Files

`binding.py` (`_fire` routing + `_designate`), `selectors.py` (ANY arm,
`_is_any_universal` TARGET widening), `quantity.py` (3 preds + THAT_MANY),
`verbs.py` (DISCARD register), `tools/run_scenarios.py` (pack-key
answers), `test_executor_designation.py` (16 pins), 21 packs moved,
2 suspects updated, `test_executor_legality.py` probe amended.
