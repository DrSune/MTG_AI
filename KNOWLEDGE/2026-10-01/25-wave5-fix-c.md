# 25. Wave-5 fix-c (r22c): loyalty feed + the three compiler-side STOPs (2026-10-02)

## Scope
Close-out of the last six wave-5 suspects: the shrine census-X family
(sanctum_of_fruitful_harvest_add_x / sanctum_of_calm_waters_draw_x /
sanctum_of_stone_fangs_life_x), adherent_of_hope,
chandras_pyreling_opponent_filter, keral_keep_disciples.
**One engine fix (keral, promoted → 282 packs); five STOPs — three of them
contradicting the mission brief, all pinned falsifiably.**

| Suspect | Disposition | Root cause (side) |
|---|---|---|
| keral_keep_disciples | **FIX → promoted** | executor had no LoyaltyActivatedEvent feed (12c whitelist raise at attach) |
| sanctum_of_fruitful_harvest_add_x | **STOP** | compiler bakes the shrine census as `NAME_EQ "Shrine"` (compiler-side, IR frozen) |
| sanctum_of_calm_waters_draw_x | **STOP** | same |
| sanctum_of_stone_fangs_life_x | **STOP** | same |
| adherent_of_hope | **STOP** | compiler dropped the "you control" quantifier; condition can't discriminate (compiler-side, precedent 19a Tampering) |
| chandras_pyreling_opponent_filter | **STOP** | "to an opponent" destination clause unexpressible: DamageDealtEvent filter vocabulary has no destination role (grammar/compiler-side) |

## IR ground truth vs mission brief
- The mission premise was "a single census fix clears all three sancti".
  Probe-dump (`/tmp/opencode/probe22c.py`) says all three compile the
  census to `QCount(Selector(QUnbounded(), ALL, FAtom(NAME_EQ, "Shrine",
  zone=BF/YOU)))`. The frozen grammar (`FAtomPred` docstring) reads
  NAME_EQ as the **exact card name** ("cards named Frantic Inventory") —
  no card is named "Shrine", so the executor's honest answer is 0, and
  every pack witness follows (pool {R:0} → loud illegal-cast; fangs 20/20;
  calm-waters draw 0). The idiom is **baked** at
  `compiler/templates_b2a.py:197-202` (+ bogus "supertype name in
  NAME_EQ position" rationale in `templates_b5c.py:2490`) and pinned by
  the compiler's OWN goldens (`test_templates_b2a.py:1196,1648`) —
  while `templates_b2a.py:1672` already uses the WORKING
  `TYPE_EQ "Shrine"` (green pack sanctum_of_all_search_fire). IR/goldens
  are FROZEN by campaign law → compiler STOP, identical root cause to
  the sanctum_tranquil_light residual already STOPped by 19b.
- adherent: condition compiles to `FAnd(NAME_CONTAINS 'Basri', TYPE_EQ
  'Planeswalker', CONTROLLER_IS YOU)` evaluated against the ONE trigger
  subject (Adherent itself) — True/False by the IR's literal ask.
  `CONTROLLER_COUNT_GE` existed in the grammar; the compiler never used
  it.
- pyreling: `DamageDealtEvent(amount=QUnbounded(), filter=FAnd(()), …)` —
  the universal filter matches ANY damage (own creatures included → the
  witness [2,3]); the DAMAGE row vocabulary is subject=victim /
  cause=dealer / data=(amount,) with no destination slot to filter on.

## Implementation map (keral fix)
- `events.py`: `KIND_LOYALTY_ACTIVATED` + `GameEvent.loyalty` typed view +
  `EventJournal.emit_loyalty_activation(permanent, actor, delta)` — one
  row per activation that PAID a loyalty symbol (CR 606.2b); subject =
  the permanent (the filter's slot), cause = the activating player (the
  controller scope), data = (signed delta,).
- `legality.py activate()`: emits the row at the `if plan.loyalty:`
  payment point (after payment, before effects — the documented
  one-call compromise shared with the r20b targeting rows).
- `binding.py`: LoyaltyActivatedEvent LEFT `_UNSUPPORTED_EVENTS` (only
  StepEvent remains); `_match_node` branch = `controller_matches(node.
  controller, event.cause)` + `eval_filter(node.filter, event.subject)`
  (the 12b TargetingEvent precedent shape). `_fire` needs no pre-bind
  routing: subject already IS the planeswalker.
- Pack promoted by MOVE + strip (status/finding dropped, notes kept) →
  **282 packs, 282/282 green**; suspects dir 18 → 17.

## Falsifiability pins (`test_executor_r22c.py`, 10 tests)
- census TYPE_EQ "Shrine" on a 2-shrine world → life +2 (executor lane
  sound — fix belongs to the compiler); census NAME_EQ "Shrine" → honest
  +0 (the STOP's exact witness, reproduced from hand-built IR).
- adherent condition → True vs a Basri PW subject, False vs Adherent
  (honest single-subject evaluation).
- DAMAGE row subject/cause/amount-only + UNIV filter overmatches
  honestly (the [2,3] witness reproduced from hand-built IR).
- loyalty lane: row shape, Chandra trigger fires (+1 life), Basri row
  journals but never matches, tap activation emits no row.

## Journal/catalog impact
New row kind lands in every loyalty-activation trace: 2 of 10 catalog
seeds diverged by PURE INSERTION (+2/+1 rows, outcomes identical, only
LOYALTY_ACTIVATED diffs) → **repinned** (12b/r20b precedent); compare
then 0/10 diverging. PC line untouched (no IR touched).

## Gates (2026-10-02, HEAD a1f5c69 + this batch)
- run_scenarios **282/282** · pytest core **2271 + 3 subtests, 0 failed**
- measure_grammar **PC-1 301/305 · PC-2 634/639 · PC-3 0 · PC-4 0** EXACT
- catalog compare **0/10 diverging (post-repin)** · games --seeds 100
  --pool all **86 survived, 0 crash classes**
- pyright **0 errors** on the 4 touched files · ruff **Δ0**
  (legality.py:1428 TRY004 is a HEAD-documented exemption)
