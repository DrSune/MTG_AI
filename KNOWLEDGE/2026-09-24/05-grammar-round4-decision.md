# 2026-09-24 · 05 — Grammar round 4 binding decision: conditional & filtered triggers + object anaphora

Status: DECIDED (owner chose this family, 2026-09-24 — see 04). Implement in the
round-3 process: additive, byte-stable, omit-if-None; verify goldens byte-identical;
then template batch; then PC re-measurement.

## Grounding (introspected against live grammar 2026-09-24 — supersedes the
round-3 doc's queue description where they differ)

Already present (verified by dataclass introspection):
- `TriggeredAbility.condition: Filter | None` — condition slot exists.
- `CastSpellEvent(filter, controller, from_zone, ordinal)` — zone + ordinal scope exist.
- `DamageDealtEvent(amount, filter, source, combat)` — source/combat attributes exist.
- `ZoneChangeEvent(from_zone, to_zone, subject)`, `TargetingEvent`,
  `DeclareBlockersEvent(filter, subject)`, `BecomesBlockedEvent`, `StepEvent`,
  `TurnPhaseEvent` — the event vocabulary covers all residual trigger kinds.
- `GRANT_ABILITY` roles `{target, ability, duration}` — **time-scoped trigger
  installation needs NO new field**: "[−1]: Whenever a creature attacks this
  turn, ..." = `GRANT_ABILITY(target=YOU, ability=TriggeredAbility(...),
  duration=DurationEot)`. Same for Subira's activated-ability version.
- `COPY`, `FLIP_WON`, `NAME_CONTAINS`, `PREVENT_EFFECT`, `DIED_THIS_TURN`,
  `CONTROLLER_COUNT_GE`, `QThisTurn`, `Conditional`, `DurationWhileCondition`.
- **Quantity anaphora is an established convention**: `QProp(referent="event"|"target"|"source"|"controller", field=AMOUNT/POWER/...)`
  (b2b Vito "that much life" = `QProp("event", AMOUNT)`; header doc names the
  fourth referent "event" for exactly the trigger-event case).

True gaps → five design items + one template batch.

## R4-1 — `CardDrawnEvent.ordinal: int | None = None`
- **Pool shape**: "Whenever you draw your second card each turn, ..."
  (Jolrael, Mwonvuli Recluse; Mystic Skyfish — 2 sentences).
- **Cross-set**: "your first/second card each turn" triggers recur; mirrors the
  existing `CastSpellEvent.ordinal` (documented precedent).
- **Spec**: `int`, validated `>= 1` in `__post_init__` (mirror
  CastSpellEvent.ordinal); `_SPECS` entry; omitted when `None`.
- **Tests**: ordinal 1/2 construct; 0 and -1 raise; serialization omits when
  None; existing CardDrawnEvent trees serialize byte-identical.

## R4-2 — new event `LoyaltyActivatedEvent(controller: ControllerRef, filter: Filter)`
- **Pool shape**: "Whenever you activate a loyalty ability of a Chandra
  planeswalker, this creature deals 1 damage to each opponent."
  (Keral Keep Disciples).
- **Cross-set**: loyalty-activation triggers are a standing planeswalker
  mechanic.
- **Spec**: frozen dataclass; added to the `EventSpec` union + serialization
  tag `loyalty_activated` + validation rules mirroring the other events
  (filter non-None; controller required).
- **Tests**: union membership; construct/serialize round-trip; bad-arg raises.

## R4-3 — `CastSpellEvent.from_zone_not: Zone | None = None`
- **Pool shape**: "Whenever an opponent casts a spell from anywhere other than
  their hand, draw a card." (Ghostly Pilferer).
- **Cross-set**: "from anywhere other than the hand" cast triggers recur.
- **Spec**: mutually exclusive with `from_zone` (both set ⇒
  `ValueError` in `__post_init__`); omitted when `None`.
- **Tests**: construct with only `from_zone_not`; both set raises; omit-if-None
  serialization; existing CastSpellEvent trees byte-identical.

## R4-4 — three new `FAtomPred`s for trigger conditions
All typed slots in `_FATOM_RULES`, closed per predicate:
1. `ENTERED_THIS_TURN_FROM` — slots `{zone: Zone}`
   — "if it entered from your graveyard" (Archfiend's Vessel).
2. `CAST_THIS_TURN_FROM` — slots `{zone: Zone, who: ControllerRef}`
   — "or you cast it from your graveyard" (Archfiend's Vessel).
3. `MOVED_TO_ZONE_THIS_TURN` — slots `{from_zone: Zone, to_zone: Zone, who: ControllerRef}`
   — "if a permanent was put into your hand from the battlefield this turn"
   (Barrin, Tolarian Archmage).
- **Cross-set**: entered-from / cast-from / moved-this-turn conditions are
  standing ETB-trigger condition families.
- **Tests**: slot arity + type enforcement (existing `_FATOM_RULES` test
  pattern), serialization tags, unknown-slot raises.

## R4-5 — object anaphora (the round's central design decision)
Quantity anaphora exists (`QProp` referents); **objects** (spell / creature /
player as a referent of an effect) do not. Three additive extensions, one
closed vocabulary:
- **(a) `Selector.referent: str | None = None`** — vocabulary
  `{"source", "controller", "target", "event"}` (the exact QProp strings;
  one referent convention for quantities AND objects). When set: the
  selector denotes the object bound in the evaluation context under that
  name; `"event"` = the triggering event's subject object
  (cast → the cast spell; damage_dealt → the damaged recipient;
  becomes_blocked → the blocker; declare_attackers → the attacker;
  targeting → the new target). `filter`, if present, acts as a type-check
  on the bound object, not a fresh search.
- **(b) `_ROLE_TYPES["controller"]`**: `(ControllerRef,)` →
  `(ControllerRef, Selector)` — for "that creature's controller loses life"
  (Gloom Sower): the controller role takes
  `Selector(referent="event")`; the executor derives the controller of the
  bound object.
- **(c) `CONTROLLER_IS` slot `who`**: `ControllerRef` →
  `ControllerRef | Selector` — for "that player controls" (Feline Sovereign):
  the filter slot accepts a referent selector.
- **Convention C2 (binding)**: a referent `Selector` must be
  `mode=CHOOSE`, `count=QConst(1)`, `zone=Zone(ANY, ANY)` — validate in
  `__post_init__` (a bound object is not chosen, and its zone is unknown at
  compile time).
- **Tests**: valid referent selectors per vocabulary; invalid mode/count/zone
  raise; unknown referent string raises; role-union + slot-union enforcement;
  omit-if-None serialization; 305 goldens byte-identical.

## Conventions decided (binding, documented in module docstrings)
- **C1**: referent vocabulary = the four QProp strings; "event" binds the
  event subject (per-event subject table above).
- **C3**: time-scoped trigger installation = `GRANT_ABILITY(ability,
  duration)` — no `valid_during` field on `TriggeredAbility`.
- **C4**: `LOOK_AT` implicitly looks at the top of the controller's library
  (no zone role; count carries the quantity, e.g. `QProp("event", AMOUNT)`).
- **C5**: loyalty triggers compile as the **effect** of the
  `ActivatedAbility` whose cost is the loyalty part.

## Template batch (18 sentences — b2b + b2a + b5c loyalty)
| # | Card | sentence | grammar needed |
|---|------|----------|----------------|
| 1 | Warden of the Woods | becomes target of spell/ability an opponent controls → may draw two | none (pure) |
| 2 | Jeskai Elder | deals combat damage to a player → may draw | none |
| 3 | Snarespinner | blocks a flying creature → +2/+0 until EOT | none (DeclareBlockersEvent subject) |
| 4 | Chandra's Incinerator | source you control deals noncombat damage → deals that much damage | none (QProp event) |
| 5 | Chandra's Pyreling | as #4 → +1/+0 + double strike until EOT | none |
| 6 | Pack Leader | attacks → prevent combat damage to Dogs you control this turn | none (PREVENT_EFFECT) |
| 7 | Gloom Sower | becomes blocked by a creature → its controller loses N, you gain N | R4-5(b) |
| 8 | Hooded Blightfang | deathtouch creature you control deals damage to planeswalker → destroy that planeswalker | R4-5(a) |
| 9 | Feline Sovereign | Cats you control deal combat damage to a player → destroy up to one target artifact/enchantment that player controls | R4-5(c) |
| 10 | Ghostly Pilferer | opponent casts from anywhere other than hand → draw | R4-3 |
| 11 | Double Vision | cast your first instant/sorcery each turn → copy that spell | R4-5(a) |
| 12 | Double Vision (s2) | You may choose new targets for the copy. | none |
| 13 | Garruk's Harbinger | deals combat damage to player/planeswalker → look at that many cards | none (C4) |
| 14 | Jolrael | draw your second card each turn → create token | R4-1 |
| 15 | Mystic Skyfish | draw your second card each turn → flying until EOT | R4-1 |
| 16 | Keral Keep Disciples | you activate a loyalty ability of a Chandra planeswalker → deal 1 to each opponent | R4-2 |
| 17 | Basri, Devoted Paladin | [−1]: creature attacks this turn → +1/+1 on it | R4-5(a), C3, C5 |
| 18 | Archfiend's Vessel | enters, if entered from / cast from your graveyard → exile | R4-4(1,2) |
| 19 | Liliana's Scrounger | each end step, if a creature died this turn → may put loyalty counter on a Liliana planeswalker | none (DIED_THIS_TURN) |
| 20 | Barrin, Tolarian Archmage | your end step, if a permanent moved hand-from-battlefield this turn → draw | R4-4(3) |

(20 rows — #12 and the two "s2" cases make it 18 sentences / 20 template
entries; count precisely at implementation.)

**Estimated impact** (verify at measurement): PC-2 512 → ~530/639 (≈0.829);
PC-1 210 → ~224-226/305 (≈0.73) via fully-parsed cards: Warden of the Woods,
Jeskai Elder, Snarespinner, Chandra's Pyreling, Pack Leader, Gloom Sower,
Hooded Blightfang, Feline Sovereign, Double Vision, Basri, Archfiend's
Vessel, Liliana's Scrounger, Barrin, Jolrael, Mystic Skyfish, Keral Keep
Disciples. Partially covered: Ghostly Pilferer (ac-discard sentence),
Chandra's Incinerator (cost-modifier sentence), Garruk's Harbinger (two
anaphoric continuation sentences).

## Verification bar (same as round 3)
1. `python -m pytest MTG_bot/core -q` green (all existing + new tests).
2. `python tools/measure_grammar.py --set M21` → PC-3 0, PC-4 0 diffs
   (305 goldens byte-identical **before** the template batch).
3. After the template batch: exactly the re-baselined files change, and ONLY
   the `abilities` top-level key (capture pre-state copy before re-staging —
   PITFALLS 2026-09-24).
4. `ruff check` + pyright clean on touched files.
5. NUMBERS.md rows + `tools/dump_unparsed_queue.py` re-dump; residual expected
   to fall from 125 shapes / 127 occ to ≈105-107 shapes / ~109 occ.

## Registered queue for round 5 (NOT this round)
1. **Conditional statics** (~8 shapes): "As long as ..." (Thieves' Guild
   Enforcer, Drowsing Tyrannodon, Tome Anima, Conspicuous Snoop, Gadrak),
   "During your turn, ..." time-scoped static (Radha), restriction semantics
   ("can't attack unless", "must be blocked if able", "can block only X",
   "doesn't untap ...").
2. **Replacement / "instead" effects** (~10): Life Goes On, Containment
   Priest, Scavenging Ooze, Track Down, Conclave Mentor, Chandra's Catalyst,
   Lofty Denial s2, Tavern Swindler flip sentences, Scorching Dragonfire,
   Chandra "exile instead".
3. **Anaphoric continuations** (~7): "It gains ..." (emblem texts ×4 — needs
   recursive-text compilation, see #4), "That player discards that card",
   "You choose ... from it" (Duress/Kitesail), "then draw that many"
   (Kinetic Augur), Garruk's Harbinger s2/s3, See the Truth s2/s3,
   Transmogrify s2/s3, Necromentia s2/s3.
4. **Recursive embedded text** (4 shapes): emblems-with-text (Basri Ket [−6],
   Liliana Waker [−7], Garruk Unleashed [−7]) + token-with-text (Pursued
   Whale) — a compiler feature: compile the quoted text through the full
   pipeline with a depth guard.
5. **Singletons** (~18): Cultivate, Vodalian Arcanist, Chromatic Orrery ×2,
   Peer into the Abyss ×2, Idol of Endurance ×2, Subira s1/s2, Mangara
   (anaphoric count over event subjects), Chrome Replicator (same-name
   group predicate), Basri Ket [−2] (event-subject count → QPropField
   extension), Faith's Fetters, Capture Sphere, Runed Halo ×2, Necromentia
   name-choice, Teferi's Ageless Insight, Enthralling Hold, Waker of Waves,
   "Activate only if/at least" shapes, Discontinuity.
