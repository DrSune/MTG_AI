# 2026-09-24 · 02 — Grammar round 3 decision (T3-pattern; binding spec)

**Rule applied** (T3 decision protocol, 2026-09-16/01 §2): additive-only
grammar; each addition justified by pool shapes and/or a named cross-set
mechanic; optional fields serialize omit-if-None so **all 305 goldens stay
byte-identical** (the SpellAbility.effect precedent, 2026-09-23/03, is the
pattern to copy).

Residual queue input: 133 live-unparsed shapes / 135 occ (01, dump at
/tmp/opencode/unparsed_queue_2026-09-24.txt). Round 3 takes the six
smallest justified items; the larger families (conditional triggers —
B2b's 18 shapes; replacement/"instead" effects; emblem-with-text; anaphoric
"It/that" continuations) are the **round-4 design queue** and are NOT
decided here.

## R3-1 — `StaticAbility.condition: Filter | None = None`

- **Pool shapes (4):** "As long as an opponent has eight or more cards in
  their graveyard, this creature gets +2/+1 and has deathtouch." (Thieves'
  Guild Enforcer); "As long as the top card of your library is a Goblin
  card, …" (Conspicuous Snoop); "As long as you control a creature with
  power 4 or greater, …" (Drowsing Tyrannodon); "As long as you've drawn
  two or more cards this turn, this creature gets +0/+2 and has
  vigilance." (Gnarled Sage).
- **Cross-set:** conditional continuous effects are a core mechanic in
  every set.
- **Serialization:** `_SPECS["StaticAbility"]` gains `("condition",
  "opt:filter")`. None → key omitted → goldens byte-stable.
- **Semantics:** state predicate (who-scoped / IS_SOURCE-scoped); no event
  subject — same convention as `CostModifier.condition`
  (ability_tree.py ~1907-1945).
- **Round-3 templates unblocked:** Gnarled Sage only (condition
  `CARDS_DRAWN_THIS_TURN_GE(count=2, who=YOU)`; effect
  MODIFY_PT +0/+2 + GRANT_ABILITY(vigilance)). The other 3 shapes still
  need predicates/effects (graveyard-count, library-top, "as though"
  defence override) → stay UNCOVERED with updated reasons.

## R3-2 — `ActivatedAbility.condition: Filter | None = None`

- **Pool shapes (2):** "Activate only if a creature died this turn."
  (Caged Zombie); "Activate only if you control a creature with flying."
  (Celestial Enforcer).
- **Cross-set:** activation gates ("Activate only if …", "This ability
  can't be activated more than once each turn") are ubiquitous.
- **Serialization:** `_SPECS["ActivatedAbility"]` gains
  `("condition", "opt:filter")`; omit-if-None.
- **Round-3 templates unblocked:** both shapes
  (conditions `DIED_THIS_TURN()`;
  `CONTROLLER_COUNT_GE(inner_filter=creature∧flying, count=1)` — copy the
  B2b usage idiom, templates_b2b.py ~287).
- **NOT unblocked:** "Activate only as a sorcery." (Liliana's Steward) and
  "…and only as a sorcery." (Speaker of the Heavens) — sorcery-mode
  restriction is not a state predicate; no grammar slot added this round
  (avoid inventing a mode flag); per-card translation (T8) candidates.

## R3-3 — `Verb.COUNTER_SPELL` gains optional role `unless` (Cost)

- **Pool shapes (2):** "Counter target instant or sorcery spell unless its
  controller pays {3}." (Miscast); "Counter target spell unless its
  controller pays {1}." (Lofty Denial, first sentence).
- **Cross-set:** "counter … unless its controller pays X" is a standard
  clause across sets.
- **Mechanism:** `_VERB_ROLES[Verb.COUNTER_SPELL]` =
  `{"target": True, "unless": False}`; the `cost` role value type
  (`Cost`) already exists in `_ROLE_TYPES` (~2306) — the PAY verb uses it.
  Atom role validation is role-table-driven (Atom.__post_init__, ~1598):
  zero other code paths touched.
- **Serialization:** optional roles simply absent from the `pairs` list
  (precedent: MOVE_ZONE/SEARCH `tapped_on_enter`) → goldens byte-stable.
- **NOT unblocked:** Lofty Denial's second sentence ("If you control a
  creature with flying, counter that spell unless its controller pays {4}
  instead.") — cross-sentence "that spell" anaphora + "instead" semantics
  → per-card translation.

## R3-4 — `FAtomPred.INSTANT_OR_SORCERY_CAST_THIS_TURN` (slots {who})

- **Pool shape (1):** "This spell costs {2}{U} less to cast if you've cast
  an instant or sorcery spell this turn." (Stormwing Entity).
- **Cross-set:** turn-scoped cast tracking is a named, recurring mechanic.
- **Mechanism:** enum member + `_FATOM_RULES` row
  `(frozenset({"who"}), frozenset({"who"}))` (precedent:
  LIFE_GAINED_THIS_TURN_GE, ~2272).
- **Fingerprint churn:** none (predicates are referenced by name in
  existing trees).

## R3-5 — `CostModifier.extra_deltas: tuple[CostDelta, ...] = ()`

- **Pool shapes (2):** Stormwing Entity ({2}{U} = generic 2 + 1 blue) and
  Discontinuity ({2}{U}{U} = generic 2 + 2 blue) — both exceed the
  single-`delta` slot.
- **Cross-set:** compound cost deltas (mixed generic + coloured
  reductions/increases) are universal; the single-delta restriction is a
  structural wart that will bite every future set.
- **Design:** keep `delta: CostDelta` (required, first delta) and add
  `extra_deltas` (the rest, omitted when empty) — the additive-slot
  pattern of `Selector.zone`/`Selector.zones` (Zone spec, _SPECS ~2528).
  `_SPECS["CostModifier"]` gains `("extra_deltas", "tup:cost_delta")`;
  `_OMIT_IF_EMPTY["CostModifier"]` gains `"extra_deltas"`.
- **Serialization:** empty tuple omitted → every pre-round-3 CostModifier
  (Watcher, Total Power, conditional-life, …) byte-identical.
- **Validation:** each element must be a CostDelta; no cross-constraint
  with `delta`.
- **Round-3 template unblocked:** Stormwing Entity
  (delta=CostDeltaReduceGeneric(2), extra_deltas=(CostDeltaReduceMana(
  "U", QConst(1)),), condition=R3-4 predicate).
- **NOT unblocked:** Discontinuity — still needs a "During your turn"
  condition (no predicate this round) → per-card translation.

## R3-6 — `FAtomPred.TARGETS_SOURCE` (slots {})

- **Pool shapes (2):** "Spells your opponents cast that target this
  creature cost an additional 3 life to cast." (Terror of the Peaks);
  "Spells your opponents cast that target this creature cost {3} more to
  cast." (Pursued Whale).
- **Cross-set:** "spells … that target this creature cost X more/less" is
  a named, recurring static mechanic.
- **Mechanism:** enum member + `_FATOM_RULES` row
  `(frozenset(), frozenset())` (precedent: IS_SOURCE, ~2257).
- **Template shape:** `CostModifier(filter=FAtom(TARGETS_SOURCE),
  controller_ref=ControllerRef.OPPONENT, delta=IncreaseLife(3) /
  IncreaseGeneric(3))` — filter selects the affected spells,
  controller_ref scopes whose (same split as the Watcher template).

## Items explicitly NOT in round 3 (round-4 design queue)

**Queue item 1 superseded by `05-grammar-round4-decision.md`** (2026-09-24
grounding: `CastSpellEvent.from_zone`/`.ordinal`, `DamageDealtEvent.source`/
`.combat`, and `TriggeredAbility.condition` already exist; the true gaps are
`CardDrawnEvent.ordinal`, `LoyaltyActivatedEvent`, `from_zone_not`, three
condition predicates, and object-anaphora `Selector.referent`).

- Conditional triggers (B2b's 18 shapes) — largest residual family.
- Replacement/"instead" effects (~10 shapes in B5b).
- Emblem-with-text loyalty sentences (4 shapes) — emblem pool entries'
  inner text needs recursive compilation.
- Anaphoric "It gains …" / "That player discards that card." continuations
  (~7 shapes) — needs the anaphora convention decision.
- Sorcery-mode activation restriction (2 shapes).
- "During your turn" time-scope condition (1 shape).
- Graveyard/library-top count predicates for the other 3 "As long as"
  shapes.
- Coin flips, half-counts, per-color counts, "must be blocked",
  "can block only X", restricted mana, gain-control, double-counter,
  until-reveal searches, ~20 singleton shapes.

## Verification bar (for the implementation)

1. `python -m pytest MTG_bot/core -q` → all pass (≥1086 pre-existing, plus
   new round-3 tests).
2. **All 305 goldens byte-identical** (no re-baseline; every new field is
   omit-if-None/empty) — verify with the staged-baseline structural
   compare (PITFALLS 2026-09-23: single-line goldens defeat `git diff`;
   parse `git show :path` vs worktree and diff key-wise), or
   `python tools/measure_grammar.py --set M21` PC-4 after a
   verify-only run.
3. Pinned fingerprints in `test_ability_tree_r3.py` stay byte-stable
   (add new round-3 pins in a new `test_ability_tree_r4.py`, importing
   round-3 builders where shared).
4. pyright 0 errors on touched files; ruff: no new finding kinds
   (PITFALLS 2026-09-19: repo-wide ruff-clean is unachievable by design).
5. `tools/measure_grammar.py --set M21` → PC-1/PC-2 unchanged by the
   grammar-only step (coverage counts sentence matching; templates come
   next) — recorded in NUMBERS.md.
