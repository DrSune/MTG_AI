# 2026-09-25 · 07 — Grammar round 5 (replacement/"instead" effects): binding decision

Status: BINDING for the round-5 implementation + template batch.
Grounding: live grammar introspection (2026-09-25) against the post-round-4
residual queue (`tools/dump_unparsed_queue.py --set M21`, 106 shapes /
108 occ). Family chosen by owner 2026-09-25 (triage of doc-06 queue:
replacement/"instead" = 9–10 shapes, ~13 pool cards use "instead";
recommended over conditional statics / anaphora / recursive text).

## Grounding (verified 2026-09-25 — do not re-derive)

- **No compiler mechanism needed.** `AbilityOutcome(ability: Ability)`
  (templates.py L64) is consumed generically by the compiler: any Ability
  node — including `ReplacementAbility(event, condition, action)` — is
  appended to the card's ability list (compiler.py post-assembly
  `ability_outcomes` pass). The continuation-merge pass **explicitly skips
  `ReplacementAbility`** ("ReplacementAbility: skip, keep searching"), so a
  replacement sentence is never mis-merged into a preceding trigger/static.
- `QBinOp` already has **MUL** ("triple that damage"), ADD ("that many plus
  one"). `QAtLeast(n)` exists ("one or more").
- `IS_ANY_TARGET` (no slots) and `FLIP_WON` (who) predicates exist.
- `ReplacementAbility` fields: `event: EventSpec`, `condition: Filter | None`,
  `action: Effect` — full serialization (`_SPECS["ReplacementAbility"]`).
- `CounterPlacedEvent` has **no count field** — "that many" is currently
  inexpressible (the gap R5-2 closes).
- `LifeGainedEvent` has **no amount field** — Life Goes On's replacement
  fires on ANY life gain (documented lossy, see row 1).
- `CostModifier.controller_ref: ControllerRef` cannot express "its
  controller" (the targeted spell's controller) — the gap R5-3 closes
  (same union-widening pattern as R4-5(b)/(c)).
- `_CONTINUATION_PREFIXES` does not include "If you win the flip" → Tavern
  Swindler's follow-on needs a NEW compiler mechanism → **deferred**
  (round 6), see scope below.

## Grammar items (all additive; omit-if-None ⇒ pre-batch goldens byte-stable)

### R5-1: `FAtomPred.WAS_CAST_THIS_TURN` — slots `{who}` (required)
"[the object] was cast this turn (by `who`)". who=ANY = cast by anyone.
Used negated: Containment Priest "a nontoken creature would enter **and it
wasn't cast**" → condition `FNot(FAtom(WAS_CAST_THIS_TURN, who=ANY))`.
Precedent: CAST_THIS_TURN_FROM (R4-4) minus the zone slot; distinct
predicate (no zone constraint) — PITFALLS: no duplicate predicates, each
predicate = one rule concept.

### R5-2: `CounterPlacedEvent.count: Quantity | None = None`
+ `_SPECS` row (`"opt:quantity"`), + `_OMIT_IF_EMPTY["CounterPlacedEvent"] =
frozenset({"count"})`, + validation (Quantity or None — mirror
CastSpellEvent.ordinal style). "one or more" = `QAtLeast(1)`.
**New `QPropField.COUNTER_COUNT` member** — "that many" =
`QProp(referent="event", field=COUNTER_COUNT)` (the event's counter count).
Used by Conclave Mentor: action count =
`QBin(ADD, QProp("event", COUNTER_COUNT), QConst(1))`.

### R5-3: `CostModifier.controller_ref: ControllerRef` → `ControllerRef | Selector`
Union widening only (existing values serialize byte-identically). `_SPECS`
conv: `"enum:ControllerRef"` → new dual conv `controller_ref_or_selector`
(model on the R4-5(c) `controller_ref_or_selector`-style dispatch: tagged
Selector dict → Selector; else enum decode). `__post_init__` accepts either.
**Convention C7 (binding)**: when `controller_ref` is a Selector, it means
*the controller of the selected object*, and the modifier applies to costs
that controller pays FOR the filtered object — **including `unless`
payments** (Lofty Denial s2: the {1} of s1 becomes {4} under the condition).

### R5-4: `FAtomPred.NOT_FIRST_DRAW_THIS_STEP` — slots `{who}` (required)
"[the card] is not the first card `who` draws in their draw step".
Teferi's Ageless Insight: "except the first one you draw in each of your
draw steps" → condition `FAtom(NOT_FIRST_DRAW_THIS_STEP, who=YOU)`
evaluated against the drawn card (CardDrawnEvent subject).

## Template batch — 9 rows / 8 cards (all via `AbilityOutcome`)

**Convention C6 (binding)**: replacement sentences compile to a
**card-level** `ReplacementAbility` (in the card's ability list) regardless
of which sentence they follow; event/subject scoping binds it to the right
action at execution. **Convention C8 (binding)**: "it/that X" in a
replacement action = the event subject → `Selector(referent="event")`.

| # | Card · sentence | Event | Condition | Action | Lossy |
|---|---|---|---|---|---|
| 1 | Life Goes On s2 | `LifeGainedEvent(YOU)` | `FAtom(DIED_THIS_TURN)` (bare, b2a precedent) | `GAIN_LIFE(8)` | event amount scoping dropped (no amount field) — replacement fires on any life gain this turn |
| 2 | Containment Priest s2 | `ZoneChangeEvent(ANY→BATTLEFIELD, subject=FAnd(CREATURE, FNot(IS_TOKEN)))` | `FNot(FAtom(WAS_CAST_THIS_TURN, who=ANY))` | `EXILE(referent event)` | none |
| 3 | Fiery Emancipation s1 | `DamageDealtEvent(amount=QX, source=FAtom(CONTROLLER_IS, who=YOU), filter=FAnd(()))` | none | `DEAL_DAMAGE(target=referent event, amount=QBin(MUL, 3, QProp("event", AMOUNT)))` | recipient "a permanent or player" → universal (no player predicate); the replaced damage's *source* omitted (no source role on DEAL_DAMAGE) |
| 4 | Conclave Mentor s1 | `CounterPlacedEvent(PLUS_1_PLUS_1, FAnd(CREATURE, CONTROLLER_IS YOU), count=QAtLeast(1))` | none | `PUT_COUNTER(target=referent event, PLUS_1_PLUS_1, count=QBin(ADD, QProp("event", COUNTER_COUNT), QConst(1)))` | none |
| 5 | Conclave Mentor s2 (bonus) | `CreatureDiesEvent(filter=FAtom(IS_SOURCE))` | none | `GAIN_LIFE(QProp(referent=Selector(referent="event"), field=POWER))` | none — "equal to its power" via nested referent Selector in QProp (grammar-supported) |
| 6 | Scorching Dragonfire s2 | `CreatureDiesEvent(filter=FAtom(IS_ANY_TARGET))` | none | `EXILE(referent event)` | "this turn" scoping dropped (death is a moment) |
| 7 | Chandra, Flame's Catalyst [−2] s2 | `ZoneChangeEvent(Zone(STACK,ANY)→Zone(GRAVEYARD,YOU), subject=FAtom(IS_ANY_TARGET))` | none | `EXILE(referent event)` | "that spell" = the spell's target (IS_ANY_TARGET) — documented C6/C8 |
| 8 | Lofty Denial s2 | — (CostModifier, not an event) | `FAnd(CREATURE, KEYWORD_HAS FLYING, CONTROLLER_IS YOU)` | `CostModifier(filter=FAtom(IS_ANY_TARGET), controller_ref=Selector(referent="target"), delta=CostDeltaIncreaseGeneric(3), condition=…)` | "{4} instead" = +3 delta (relies on s1's {1}; same card) |
| 9 | Teferi's Ageless Insight s1 | `CardDrawnEvent(YOU)` | `FAtom(NOT_FIRST_DRAW_THIS_STEP, who=YOU)` | `DRAW(2)` | none |

Bucket placement: rows by their existing bucket assignments (b2a/b2b/b5c —
verify each sentence's normalized key in `phase1_buckets/*.json` first;
PITFALLS 2026-09-25: cross-bucket misassignment). Row 8 may live in b5a
(cost-modifier family); decide from the bucket file, not from card
intuition.

## Explicit deferrals (NOT round 5 — registered in round-6 queue)

1. **See the Truth s3** ("If this spell was cast from anywhere other than
   your hand, put each of those cards into your hand instead.") — the
   condition is about the SOURCE spell (needs a source-condition convention
   in `ReplacementAbility.condition`), and "each of those cards" references
   a prior effect's selection (non-event referent). Anaphora family.
2. **Tavern Swindler** ("{T}, Pay 3 life: Flip a coin. If you win the flip,
   you gain 6 life.") — needs a flip-follow-on compiler mechanism (outcome
   type + attach-to-preceding-ActivatedAbility + orphan guard; the
   continuation pass's OptionalEffect wrap is wrong semantics — the follow-
   on is a mandatory conditional). FLIP_COIN orphan stays owner-ratified
   until then.
3. **Chandra, Flame's Catalyst [−8] s3** ("Until end of turn, you may cast
   spells from your hand without paying their mana costs.") —
   cast-without-cost until-EOT; singleton.
4. **Furious Rise s2** ("You may play that card until you exile another
   card…") — anaphoric "that card" + until-EOT playability; anaphora family.

## Expected impact (verify, don't assume)

- +7 fully-parsed cards (Life Goes On, Containment Priest, Fiery
  Emancipation, Conclave Mentor, Scorching Dragonfire, Lofty Denial,
  Teferi's Ageless Insight) → PC-1 ≈ 231/305 (0.7574).
- +9 sentences → PC-2 ≈ 540/639 (0.8451). Residual queue ≈ 97 shapes /
  99 occ (all 9 rows are singleton occurrences).
- Chandra, Flame's Catalyst stays partial ([−8] s3 deferred).

## Verification bar

Grammar phase: `pytest MTG_bot/core -q` green; golden refresh → **0 of 305
worktree-modified** (byte-stable); PC-3 0; PC-4 0; ruff delta vs HEAD
non-increasing.
Batch phase: full suite green; PC re-measurement vs expected; exactly the
expected card goldens change with **abilities-key-only** audit against a
pre-state copy captured BEFORE refresh (PITFALLS 2026-09-24); residual-queue
dump; UNCOVERED lists + docstring coverage counts updated in each touched
bucket module; per-row docstrings name the lossy drops verbatim.

## Round-6 queue (after this batch)

1. Conditional statics (~8 shapes: "As long as …", "During your turn",
   restriction semantics — condition slots now exist on all three ability
   types).
2. Anaphoric continuations (~15 shapes: "That player/creature …",
   "It gains …", See the Truth, Furious Rise s2).
3. Flip-follow-on mechanism (Tavern Swindler; consumes the FLIP_COIN
   orphan).
4. Recursive embedded text (4 shapes: emblems ×3 + token-with-text).
5. Singletons (~50).
