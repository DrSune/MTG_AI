# 2026-10-05 / 02 — RESPONSE-WINDOW ARC: v1 DESIGN (supersedes R16-1 option (iii))

Status: **DESIGN ONLY — engine untouched.** Baseline HEAD 348681e: packs
**339/339**, core **2360+3**, catalog **3848 entries/10 games, 0/10 diverge**,
games **0 crash classes** (47/53 decisive, mean 33.48 t), PC Δ0, PC-11 residue
1 (Sublime Epiphany, ruled-deferred). Cross-refs `01-exploit-transfer-audit.md`
and the puzzle-ladder `/03` are **absent at authoring time** — no numbers from
them are cited; Batch 2 writes the missing measurement.

## 0. What changes vs R16-1, and why the ruling is fulfilled, not reversed

R16-1 deferred the window as option (iii) on an explicit premise: "our
instants are own-turn-only **by construction**, so nothing illegal is
claimed". That premise is now FALSE. `legality.spell_window_reason`
(legality.py:1102) already gates INSTANT to "any time its controller would
have priority" — the test-pinned permissive reading **includes opponent
turns** ("a future phase/priority ledger may narrow it, the cast() surface
will not change"), and FLASH landed in 23a (CR 702.9a). What the deferral
left standing is not a semantic commitment but an **unbuilt ask-site**. R16-1
itself promised the cure: "additive DecisionStream vocab later, proven by
trace-diff pins" (R16-2 mandate). This design delivers exactly that.

Cost of the deferral today: the COUNTER_SPELL family ×5 (Cancel, Miscast,
Rewind, Lofty Denial, Sublime Epiphany) sits `excluded_by_flag` from wave-2
derivation; Sublime Epiphany is the **sole PC-11 residue** and the B5 exit
gate (`measure_bugcatch.py`) is pinned to this arc. The IR was built for it
rounds ago (round-3 added the `unless` role); the engine verb handler is the
only missing lane.

## A. The ladder — three rungs, each shippable and catalog-provable alone

**Rung 1 — COUNTER WINDOW ON THE STACK (v1).** One response round per stack
push, in the exact no-interaction gap the stack docstring names: after
`executor._settle()` (cast triggers above the spell, stack.py:571) and before
`executor.stack.pop()` (resolution, stack.py:578). Mechanics:
- **Who is asked:** each opponent of the spell's controller, in `player_order`
  order, ONE pass (controller-self-counter is a v1-documented simplification).
- **The ask:** vocab = `("PASS",)` plus one word per legal counter card held;
  C15 narrowing — **zero legal holders ⇒ never asked**. Tag
  `counter:<seat>:<frame-digest>`, the 18b `target:`-tag shape (handle-safe,
  longest-prefix matchable by the rig).
- **Answer = a counter:** the response is cast **through the same `cast()`
  pipeline**, so it pushes its own frame and opens its own window — LIFO
  handles counters-on-counters; recursion depth is bounded by counters in
  hand (≤4 in this corpus); pop drains unconditionally, the window NEVER
  blocks resolution. `_v_counter_spell` moves the frame's card STACK→GRAVEYARD
  and flags the frame countered; the popper skips resolution for flagged
  frames.
- **v1 limits (documented, per R16-1 mandate):** no mana abilities during the
  window (CR 608.2a — the responder has mana up or passes); one pass, no
  multi-round priority rotation; `unless` kickback raises loud (zero M21
  carriers — falsifiability pin).
- **Journal:** new `WINDOW_OPEN` / `WINDOW_PASS` / `COUNTER` row kinds →
  full re-pin certain; B3a LIFE_LOST is the attribution template (pure row
  insertion, first-diff is the new row, outcomes identical where counters
  don't bite).

**Rung 2 — INSTANT WINDOW IN COMBAT (v1.5).** Open the SAME window hook at
`combat_step`'s post-declare-blockers settle (`__init__.py:1409`, before
`_combat_damage` at 1410) — one defender pass, then one attacker pass, per
combat. This is the rung that reverses threat-free combat (the H3 exploit
class: attackers currently commit with zero interaction). Rung 1 must land
first; the delta is one call-site plus packs.

**Rung 3 — FULL PRIORITY (CR 117).** Every step boundary, every settle point,
mana-ability responses. **STAYS DEFERRED** — per-turn ask volume multiplies
before we know the puzzle-ladder reward; decide it only after Batch 2
re-measures exploit transfer.

## B. Vocabulary & the C15 sufficiency proof — shape unchanged, facts added

IR needs **zero changes**: `Verb.COUNTER_SPELL` (ability_tree.py:204), roles
`{target:True, unless:False}` (3327), `ZoneKind.STACK` (323), compiler
templates b5a/b5c already emit it. The query surface already answers every
fact a responder needs: Zone(STACK) enumerates per-seat entries
(legality.py:387-413, the 14a F-2 fix), stack-zone selectors read LIFO
top/bottom (selectors.py:172-199), and `SpellObject` carries the complete CR
601.2b–e public frame — modes, targets, X, total cost (the 13b design debt,
paid: "a future window reads a complete frame instead of re-deriving one").
The 14a C15-sufficiency measurement re-runs unchanged in shape; the new fact
(STACK contents) is already enumerable, and §8.3 query/legality identity
holds because the window routes through the same `legal_casts`-checked
`cast()`. No new legality gates: INSTANT is never turn-gated
(legality.py:1112 "never the instant baseline"); sorcery gates stand; FLASH
stays decorative until a non-instant flash carrier exists.

## C. Engine lane (Batch-1 diff shape)

1. `verbs.py`: `_v_counter_spell` + HANDLERS registration — V2 **45→46**,
   engine gate **297→301/305** expected (the four pure counters; Sublime
   Epiphany stays COPY-gated, §E).
2. `stack.py`: window hook between 571 and 578; countered-frame flag;
   pop-side resolution skip; response recursion via `cast()`.
3. `__init__.py`: the Rung-2 call-site at 1409 — **Batch 2 only**.
4. `decisions.py`: **NO CHANGE** — pool → FIFO → provider with raise-on-
   exhaustion (14b) is already the right contract; the window is one more
   `take_decision` caller.
5. Determinism: ask order = `player_order`; vocab order = PASS first, then
   Handle-sorted cards (fingerprint-stable, existing convention).
   `state_fingerprint` already folds the stack dump (13b pin) — no change.
6. `games.py`: the RandomPolicy provider answers window asks, so RNG
   consumption shifts at every window → **all pinned seeds diverge** (C4's
   10/10 precedent) → the full re-pin and outcome re-measure ARE Batch 1's
   exploit-transfer evidence. Viewer replay gains WINDOW/PASS/COUNTER rows
   (owner-inspection duty).

## D. Training / reward effects

- **Branching estimate (design-time; measurement is a Batch gate):** windows
  fire once per opponent stack-push. Catalog scale: ~385 journal rows/game;
  opponent casts/game ≈ 4–8. The counter supply is **5 cards / 305**
  (≈1.6% of pool, deckable-instant share low), so random games expect
  **0–2 windows/game, median 0** — games prove determinism, not branch cover;
  the branch is lit by SCRIPTED packs. Worst-case nesting ≤ counters in hand.
- **R16-1 side-effect reversal:** go-wide dominance (attackers unthreatened
  since 16b) is a property of the uninterrupted phase; Rung 2 restores
  pre-damage threat and must decay the attacker edge. Quantification is
  blocked on the absent 01 audit — Batch 2 writes it.
- **Puzzles:** counter-aware threat-assessment micro-puzzles (go-wide vs
  open counter) become expressible at Batch 2; the absent ladder `/03` doc
  is fed afterwards.
- **PC-12:** counter-vs-pass is a PACK-level decision, not an IR branch
  (zero `unless` carriers) — the 97-branch denominator does NOT move; pair
  classes `counter×attack` do (PC-13 feed).

## E. Validation

- **wave-7 derivation** (`wave_builder.py --wave7`): expect **4/5 admit**
  (Cancel, Miscast, Rewind, Lofty Denial — engine-supported at Batch 1).
  **Sublime Epiphany stays OUT**: it needs COPY too, and COPY is still not
  in HANDLERS (verified: zero `Verb.COPY` hits in verbs.py). Its
  `deferrals.json` cite must be AMENDED to "counter window AND COPY" so the
  B5 PC-11 gate stays honestly green (ungated == 0).
- **New packs:** 4 counter packs on the 18b lanes — attacker `cast` step,
  defender word scripted (`PASS` or the pack key of the counter); needs a
  small rig lane for response scripts (`respond:` keyed map or a decisions
  queue that spans the window — rig work in Batch 1).
- **The 339-pack regression law:** packs stay byte-identical IF unscripted
  window asks hit a harness fallback. Today `run_step` installs a provider
  ONLY for steps carrying `decisions` (run_scenarios.py:239-264) — a window
  ask inside a plain cast step would hit all three exhausted lanes and
  RAISE. Fix: **always-install provider** with a window-tag-aware fallback
  (`counter:*` → `PASS`), mirroring the combat fallbacks (DECLINE / NONE /
  skip, run_scenarios.py:450-458). ⇒ This is §G.
- **Catalog:** full re-pin expected Batch 1 (WINDOW rows + RandomPolicy RNG
  shift); `compare` must attribute first-divergence to a WINDOW_OPEN pure
  insertion; outcome flips where a scripted counter bites are the intended
  blast radius (C4 precedent).
- **Per-batch gates:** scenarios 339+new, suite +N pins (r25a lane), PC-1..4
  EXACT (IR frozen), engine gate +4 verbs, 0 crash classes, post-repin
  0/10 diverge, pyright 0 / ruff Δ0, PC-11 ungated 0 with amended deferral.

## F. Batches (3)

1. **Rung 1 counter window** (engine+rig): `_v_counter_spell`, stack hook,
   journal kinds, always-provider harness lane, wave-7 4 packs, full re-pin,
   all gates. One session.
2. **Rung 2 combat instant window** (engine 1 call-site; rig+audit medium):
   bolt/removal-before-damage packs, H3-pair re-adjudication (malefic_scythe
   × wildwood_scourge era premise re-check), exploit-transfer re-measure —
   writes the missing 01 numbers.
3. **Training re-baseline** (tools-only): policy-RNG stats, games-report
   window counter, `counter×attack` pair feed, puzzle seeds. Rung 3
   explicitly stays deferred pending Batch 2 data.

## G. The ONE owner ruling

**Unscripted response asks — rig-side default-PASS or pack versioning?**
Engine-side defaulting is NOT on the table (14b exhaustion law, C15 "never
silently default a decision"). Options:
- (a) **Rig always-install provider, fallback `PASS`** — precedent: combat
  provider already answers unscripted asks (DECLINE/NONE/skip) and the
  vocab[0]-narrowing law; all 339 packs byte-identical; the engine still
  asks loudly on every push; policy answers. Sets precedent for every future
  ask-site.
- (b) **Pack versioning** — add an explicit opt-out/response field across the
  339 corpus: honest per pack, but a 339-file churn for a decision that is
  always PASS in packs that never script a counter.

**Recommendation: (a).** It preserves the 14b law's intent (loud ask, policy
supplies the answer) while keeping the corpus byte-stable, and it is the same
harness convention every prior ask-site (may/block/order/trample) already
lives by.
