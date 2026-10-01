# 06 — Wave 2 fix-batch 19b (engine editable, authoring closed)

Scope: the batch-B silent-semantics suspects in `tools/audit/suspects/` (the 14
FAILs + `secure_the_scene` PASS-as-STOP inherited from fix-A). Every fix is
flag-not-degrade, seed/deterministic-order clean, and pinned by
`MTG_bot/core/test_executor_r19b.py` (18 tests). Nothing committed.

## The seven fixes

1. **IS_ATTACHED_TO + the population exemption** (`quantity.py`, `selectors.py`).
   Turn to Slag's `DESTROY ALL BATTLEFIELD (Equipment AND attached to target)`
   sat under the shared `target` role, so binding-first made it destroy the
   DESIGNATED creature and leave the attached Equipment standing — the exact
   silent shape. Two parts: the pred now resolves (write-direction lookup
   `attachments[attachment] == host`, mirroring how `attach_aura` WRITES the
   table and the leave-sweep pops it; the 13c SOURCE twin keeps its mirrored
   orientation — each is empirically required by the locked lanes), and
   `role_handles` grew a third self-resolving shape: an ALL-mode Selector whose
   filter carries its own `FAtom.referent` anaphora denotes its own population
   (`_filter_has_referent`). The exemption stays narrow: referent-less ALL
   selectors keep binding-first (the 12a `_binding_atom` payment idiom needs it).

2. **Discard-cost self-exclusion** (`legality.py`). The cast fold runs the
   payment plan while the spell is STILL in hand, so the spell was a raw
   HAND-candidate and the Handle-sorted `cands[:need]` silently spent the cast
   on itself (Thrill of Possibility's lowest handle; Sparkhunter's discard).
   CR 601.2h forbids it; the exclusion is lane-agnostic on `ctx.source`, the
   same reading CostTap's no-target branch takes.

3. **The dies-replacement lane** (`replacements.py`, `stack.py`, `__init__.py`).
   Scorching Dragonfire "If that creature would die this turn, exile it
   instead": the Eot record outlives the resolution ExecCtx, so the cast's
   designation snapshot now RIDES the record (`ReplacementRecord.designated`,
   threaded from `cast()`'s `chosen` tuple — the PreventionRecord `_rec_ctx`
   convention extended to replacements). The SBA loop consults
   `replacement_for_death` BEFORE the graveyard move (C24 replacement-before-
   apply, the die-lane twin of the damage/life hooks); a consumed death is not
   moved, its ACTION runs as its own journalled atom with the dead card bound
   as `event`. Documented v1 gap: the consumed death emits no
   BATTLEFIELD->GRAVEYARD diff, so `KIND_CREATURE_DIES` stays silent for it —
   never a fake row; no corpus scenario depends on the pair yet.

4. **CostModifier folding** (`legality.py`) + three preds (`quantity.py`).
   Continuous `CostModifier` nodes fold into the total cost before the payment
   arithmetic (CR 601.2f: increases first, reductions second), SPELL-LANE only
   (abilities pay printed costs — with no spell the plan is byte-identical to
   pre-r19b). Each modifier's filter/payer-scope/condition judge the CASTING
   SPELL in the MODIFIER CARD's coordinates. Every component min-clamps at
   zero: no cross-colour spill, over-reduction is WASTED, never a credit.
   `CostDeltaWaiveMana` is skipped BY DESIGN (a waiver is a permission the
   caster may decline). New preds: `TURN_OF` (active-seat column, no journal
   read), `LIFE_GAINED_THIS_TURN_GE` (SUM over 16c LIFE_GAINED rows, not a row
   count), `INSTANT_OR_SORCERY_CAST_THIS_TURN` (13b CAST feed, payload col 3 =
   SpellKind name). This retired four suspects: discontinuity,
   sanguine_indulgence, volcanic_salvo (SUM(POWER) QProp resolves in the
   modifier's coordinates — the reason amounts resolve there), thrill-of-p-
   possibility's twin lane with fix 2.

5. **END_TURN self-exile** (`stack.py`). Discontinuity's card-named exile has
   no IR slot — the compiler folds it into the single `Atom(END_TURN)`. The
   extra-turn REQUEST is the witness: if `end_turn_requested` is set (only
   `_v_end_turn` sets it, from THIS spell's effect step, unconsumed until the
   op closes) the spell's stack→GY put becomes stack→exile (CR 716.4a).

6/7. **The look window** (`quantity.py` `ExecCtx.look_window` +
   `one_of_window`, `verbs.py` `_look`/`run_atom`/`_v_move_zone`,
   `selectors.py`, `__init__.py` Conditional). Track Down's "reveal … IF IT is
   a creature or land, draw" and See the Truth's "put ONE OF THOSE cards into
   your hand, put the rest on the bottom" all died silently because nothing
   carried "the previous sentence's revealed card" (templates_b5b documents
   the compiler's convention). The register rules that survived testing:
   - `_look` publishes the shown handles TOP-FIRST; the event record keeps the
     str view byte-identically.
   - `run_atom` clears the window **AFTER dispatch** for non-look verbs — not
     at entry: the MOVE atom must RESOLVE with the window open (that is the
     whole partition idiom). A look verb keeps/refreshes it, so a window is
     exactly one sentence wide.
   - `Conditional` subject = `ctx.look_window[0]` when open, else `ctx.source`
     (every bare Conditional in the corpus keeps its old answer — See the
     Truth's tail `FNot(CAST_THIS_TURN_FROM hand)` NEEDS the spell-as-subject
     reading, and `CAST_THIS_TURN_FROM` is handle-scoped so a stale window
     would wrongly fire the tail CHOOSE→hand).
   - A `ONE_OF`/`REST` selector on `Zone(LIBRARY, TOP)` with no referent takes
     its candidates from the window ∩ live-library (TOP enumeration answers
     one card, which made ONE_OF auto-fire and REST hoover the pile). Because
     `run_atom` closes the raw window at the ONE_OF's completion, the ONE_OF
     stashes its windowed candidates in `one_of_window` — same lifetime and
     Seq-pairing rule as `one_of_pick` — and the sibling REST consumes the
     stash. Cards that left the library between look and partition drop out.
   - A destination `Zone.position == BOTTOM`: `move_card` appends (and no-ops
     same-zone), so the move loop iterates Handle-DESCENDING and re-inserts
     each card at index 0 — the final bottom run reads ASCENDING (the scry
     canonical rule, doc-18a).

## Catalog attribution (why 3 of 10 seeds diverged, then 0)

Pre-repin `compare` (pool=engine, seeds=10, deck_pairs_seed=1409, turns=60):
seeds 3/4/7, 4 DIFF lines — all attributed, then repinned (10 games, 6145
entries, `tools/traces/catalog.json`):
- seed 3 entry 429 (`card:101`) and seed 7 entry 129 (`card:16`): ZONE_CHANGE
  digest `CAST` change on **Discontinuity** = fix #5's intended stack→exile
  re-route.
- seed 4 entries 454–455: turn-start draw `card:20` (Tolarian Kraken) →
  `card:56` (Feat of Resistance) = the r19b BOTTOM-PUT reorder. Invisible to
  every journal diff while it sits in the library; first observable at the
  NEXT draw. The RandomPolicy's ONE_OF answer coincidentally matched the
  pre-fix auto top-pick, so only the reorder leaked.

## Dispositions (14 batch-B FAILs + secure_the_scene)

- **FIXED + promoted (9)**: turn_to_slag, sparkhunter_masticore,
  thrill_of_possibility, scorching_dragonfire, discontinuity,
  sanguine_indulgence, volcanic_salvo, track_down, see_the_truth →
  `tools/scenarios/` (git mv; promoted packs keep `status: suspect` + finding
  text verbatim, the fix-A convention).
- **STOP (4, stay in suspects)**: capture_sphere — permanent-cast lane is dead
  for auras (records lack SpellAbility → `cast:not_a_spell`; the `enchant` op
  journals no entry MOVE → the ETB trigger never sees its host; the SBA then
  buries the Aura: harness+compile gap, route to the compiler campaign);
  tampering_no_block (no can't-block marker in IR); transmogrify (reveal-until
  tail has no IR shape); secure_the_scene (CREATE_TOKEN controller role —
  PASS-as-STOP).
- **DEFER-19c (9)**: duress, mind_rot, necromentia, hunters_edge,
  experimental_overload, peer_into_the_abyss (`selection:count_below_min:0<1`),
  return_to_nature + rookie_mistake (multi-TARGET designation),
  wildwood_scourge (enter raises `QX has no declared X`; cast route
  `cast:not_a_spell` — permanent-cast-lane + X-binding gap).

## Gates (2026-10-01, HEAD 0ff4d7f + this batch, uncommitted)

- scenarios: **140/140** (`tools/run_scenarios.py`)
- unit: **2152 passed + 4 subtests** (`pytest MTG_bot/core -q`), 18 new in
  `test_executor_r19b.py`
- PC gate: PC-1 301/305 · PC-2 634/639 · PC-3 0 · PC-4 0 — byte-identical to
  T5/fix-A (compiler frozen); PC-6/PC-8 pre-existing FAILs unchanged
- traces: **0/10 diverged** after the r19b repin
- pyright on all 8 touched files: **0 errors**
