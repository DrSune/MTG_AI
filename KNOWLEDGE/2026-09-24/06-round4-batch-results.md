# 2026-09-24 · 06 — Grammar round 4 + template batch: results and state

Status: DONE (implemented 2026-09-25; binding spec and owner decisions in 05).
Both phases verified by the orchestrator (own-suite reruns, golden audit,
live PC re-measurement).

## What landed

### Grammar round 4 (ability_tree.py, additive-only) — see 05 for the binding spec
Five items, all omit-if-None so every pre-round-4 tree serializes
byte-identically:
1. R4-1 `CardDrawnEvent.ordinal: int | None = None` (validated `>= 1`)
2. R4-2 new event `LoyaltyActivatedEvent(controller, filter)` + union member
   + serialization tag `loyalty_activated`
3. R4-3 `CastSpellEvent.from_zone_not: Zone | None = None` (mutually
   exclusive with `from_zone`)
4. R4-4 three new `FAtomPred`s: `ENTERED_THIS_TURN_FROM {zone}`,
   `CAST_THIS_TURN_FROM {zone, who}`, `MOVED_TO_ZONE_THIS_TURN {from_zone,
   to_zone, who}`
5. R4-5 object anaphora: `Selector.referent: str | None` (closed vocabulary
   `source/controller/target/event`, convention C1), `_ROLE_TYPES["controller"]`
   widened to `(ControllerRef, Selector)`, `CONTROLLER_IS.who` widened to
   `ControllerRef | Selector`; referent selectors must be
   `mode=CHOOSE, count=QConst(1), zone=(ANY, ANY)` (C2, validated in
   `__post_init__`).

Conventions C3–C5 (GRANT_ABILITY+DurationEot for time-scoped triggers;
LOOK_AT = top of controller's library; loyalty triggers as the effect of the
activated ability with the loyalty cost) implemented as decided.

Verification (orchestrator-repeated): core suite 1128 → **1181** (+53
`test_ability_tree_r5.py`); pre-refresh gate: golden refresh → **0 of 305
worktree-modified** (byte-stable), PC-3 0, PC-4 0.

### Template batch (19 templates: b2b 15, b2a 3, b5c 1)
- `templates_b2b.py` (42 → **57 templates**; UNCOVERED 18 → **4 rows**):
  warden-of-the-woods, jeskai-elder, chandras-incinerator,
  chandras-pyreling, pack-leader, gloom-sower, hooded-blightfang-pw,
  feline-sovereign, ghostly-pilferer-cast, double-vision-copy,
  double-vision-new-targets, garruks-harbinger, jolrael-cat-token,
  mystic-skyfish, keral-keep-disciples. Module-local helper
  `_event_reference()`; Double Vision s1 = `COPY.source` event referent (C1),
  s2 = `RuleReminderOutcome(reason="anaphoric_continuation")` (owner ruling).
- `templates_b2a.py` (54 → **57 templates**; UNCOVERED 8 → **5 rows**):
  archfiends-vessel (ETB + R4-4 conditions → EXILE self),
  lilianas-scrounger (TurnPhaseEvent END_TURN + DIED_THIS_TURN +
  OptionalEffect PUT_COUNTER on a Liliana), barrin-end-step (TurnPhaseEvent
  END_TURN + MOVED_TO_ZONE_THIS_TURN → DRAW 1).
- `templates_b5c.py` (73 → **74 templates**; UNCOVERED → **16 rows**):
  `B5c-loyalty-basri-attack-counter` — C3: GRANT_ABILITY + DurationEot
  wrapping a TriggeredAbility; "it" = the attacker via the event referent.
  No lossy encoding (docstring: "Lossy: none").

Doc-05's 20-row table maps to 19 templates: row #3 (Snarespinner s2) stayed
UNCOVERED per owner ruling (see below).

## Lossy encodings (documented in builder docstrings, owner-ratified)
- Warden (row #1): "Lossy: 'an opponent controls' is dropped —
  TargetingEvent constrains only the targeted object (IS_SOURCE), never the
  spell's controller (doc-05 row #1)."
- Jeskai (row #2): "Lossy: 'to a player' is dropped —
  CombatDamageEvent.filter is over the damage-dealing creature and exposes
  no recipient field (doc-05 row #2)."
- Incinerator / Pyreling (rows #4–5): "a player" dropped from the
  damaged-recipient filter (no opponent predicate); "a source" read as any
  source you control (CONTROLLER_IS, no type); `combat=False`.
- Garruk (row #13): "Lossy: the 'a player or planeswalker' recipient filter
  is dropped (no recipient predicate)."
- Jolrael (row #14): "Lossy: the token's green color is omitted —
  TokenSpec has no color field (bucket convention)."
- b2a header: "lossy: the grammar cannot distinguish 'any one color' from
  colorless."
- Barrin s2 (row #20): "a permanent" left unconstrained.
- **Archfiend's Vessel s2 / Jeskai Elder s2 ("If you do, …" continuations) —
  orchestrator-noted 2026-09-25, NOT a new batch decision**: both follow-on
  clauses are merged by the STANDING continuation convention ("default
  continuation: a sibling optional step" — compiler.py L886), so the
  mandatory "If you do, create a token" / "If you do, discard a card"
  dependencies are under-encoded as plain `OptionalEffect` steps (the
  follow-on becomes optional rather than conditional — conservative; no
  incorrect forced behaviour is learned). The same convention applies to
  all previously parsed "If you do, …" cards; this batch merely surfaced
  two more instances. Known grammar gap: no sequential conditional
  ("if the previous step succeeded, do X") node — round-5 item, see queue.

## UNCOVERED end-states
- b2b: 4 rows — "When you do, you may tap or untap target creature."
  (anaphoric "When you do"); the "two or more of those creatures are
  attacking" set-level condition; "Whenever this creature attacks or blocks,
  choose one —" (choose-opener consumed by the `compiler.py` built-in
  `_CHOOSE_ETB_RE` — kept with "handled by built-in" reason); Snarespinner
  s2 kept **verbatim** per owner ruling: "blocked-creature (attacked-creature)
  filter gap — DeclareBlockersEvent.filter/subject are both over the
  blocker; 'blocks a creature with flying' constrains the blocked creature.
  Round-5 grammar item: `DeclareBlockersEvent.blocked: Filter | None`."
- b2a: 5 rows — duration-until-source-leaves ("exile ... until this artifact
  leaves"); ETB choose-opener (built-in); anaphoric "that many"
  discard-then-draw; per-opponent nested-ability Pirate tokens; pairwise
  name-equality Construct condition.
- b5c: 16 rows — anaphoric targets, conditional Then-continuations, cost
  reduction, turn-scoped triggers, emblems, coin-flip. (The old "18
  normalized-key rows" header comment was stale; actual 16 rows / 16 keys,
  header corrected.)

## Headline numbers (post-batch, `python tools/measure_grammar.py --set M21`,
report `reports/grammar_2026-09-25.json`, 2026-09-25T05:23+02:00)

| Metric | Pre-batch (09-24 report) | Post-batch | Δ |
|---|---|---|---|
| PC-1 card_coverage | 0.6885 (210/305) | **0.734426 (224/305)** | +14 cards |
| PC-2 sentence_coverage | 0.8013 (512/639) | **0.830986 (531/639)** | +19 sentences |
| PC-3 ambiguity | 0 | 0 | — |
| PC-4 golden_stability | 0 diffs | 0 diffs (305 refreshed) | — |
| PC-5 latency p99 | 0.168 ms | 0.239 ms | pass (< 50) |
| PC-6 orphans | 2 | 2 (FLIP_COIN, PHASE_IN — owner-ratified) | max_verb_share 0.105 pass |
| PC-7 executor | pending | pending | — |
| PC-8 targetable | 0.2754 (84/305) | **0.281967 (86/305)** | +2 |
| PC-9 determinism | True | True | — |
| PC-10 instrument null-test | pass | pass ("Nobody understands this.") | — |
| core suite | 1128 | 1181 (grammar) → **1217** (batch +36) | +89 |

failed_targets unchanged: PC-1, PC-2, PC-6, PC-8 (stretch/owner-tracked).

Fully parsed (14 = the +14 on PC-1): Warden of the Woods, Jeskai Elder,
Chandra's Pyreling, Pack Leader, Gloom Sower, Hooded Blightfang, Feline
Sovereign, Double Vision, Jolrael, Mystic Skyfish, Keral Keep Disciples,
Archfiend's Vessel, Liliana's Scrounger, Barrin, Tolarian Archmage. Partial
residuals: Snarespinner (s2 — owner ruling, round-5 grammar item),
Chandra's Incinerator (cost-modifier sentence), Ghostly Pilferer (AC-discard
sentence), Garruk's Harbinger (two anaphoric continuations), Basri, Devoted
Paladin ("It gains vigilance until end of turn.").

## Goldens
Exactly **18 files** re-baselined (19 sentences / 18 cards — Double Vision
contributes 2 sentences to 1 card), staged. Pre-state captured at
`/tmp/golden_pre_r4_1790306591` **before** refresh (PITFALLS 2026-09-24
rule); structural audit passed: the `abilities` key is the only changed
top-level key in each file. PC-4 = 0 after refresh.

## Residual queue post-batch
**106 shapes / 108 occurrences** (was 125/127 pre-batch). Exactly the 19
assigned rows removed; 0 added, 0 partially consumed. Dump:
`/tmp/opencode/unparsed_queue_post_r4.txt` (via
`python tools/dump_unparsed_queue.py --set M21`).

## Deviations from the pre-batch plan (all verified benign)
1. **Naming**: code labels this batch "Round 5" in per-bucket headers
   (b2b had rounds 1/2/4) while builder docstrings cite "Round 4 row #N"
   per doc 05. Doc-05 row numbers are canonical.
2. **b2b end-state 58 covered + 4 uncovered (57 templates)**, not the
   planned 59 + 3: the original 18th row "Whenever this creature attacks or
   blocks, choose one —" is consumed by the `compiler.py` choose-opener
   built-in and can never be template-covered.
3. **Double Vision s2** ("You may choose new targets for the copy.") buckets
   in `phase1_buckets/B4.json`, not B2b — the b2b template covers it
   set-level; the compiler dispatches by bucket, so PC-3 = 0 confirms the
   mapping.
4. **b5c UNCOVERED header** was stale (claimed 18 rows; actual 16) —
   corrected.
5. `reports/grammar_2026-09-24.json` was regenerated during the STEP-A
   session (2026-09-24T21:32, HEAD `3bafd33`) — only PC-5 run noise
   (0.168 → 0.225) and the goldens field "verified" → "refreshed";
   baseline numbers unchanged.

## Round-5 queue (from 05's registered queue, plus)
0. **`DeclareBlockersEvent.blocked: Filter | None`** — the Snarespinner
   grammar item, now the top candidate (owner ruling 2026-09-24).
1. Conditional statics (~8 shapes).
2. Replacement / "instead" effects (~10).
3. Anaphoric continuations (~7) — incl. "It gains ... until end of turn."
4. **Sequential "if you do" conditional** (orchestrator-added 2026-09-25):
   an effect node expressing "if the previous step succeeded, do X"
   (e.g. `ThenIfPrevious(Effect)`) — the standing continuation convention
   under-encodes these as optional sibling steps (see lossy list above;
   instances: Archfiend's Vessel s2, Jeskai Elder s2, and the pre-existing
   b5b "If you do, …" family).
5. Recursive embedded text (4 shapes: emblems ×3 + token-with-text).
6. Singletons (~18).
