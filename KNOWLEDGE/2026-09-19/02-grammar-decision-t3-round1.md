# 2026-09-19 · 02 — Grammar-addition decision (T3), round 1

**Input:** the complete UNCOVERED register — 201 shapes (172 machine-readable
across `templates_b{2a,2b,3,4,5b,5c}.py` + 29 still in the B5a test docstring,
T4), dumped to `/tmp/opencode/UNCOVERED_FULL_2026-09-19.txt` — plus a catalog
probe of `ability_tree.py` (70 node types, 35 verbs, 34 FAtomPreds, 13 events,
9 Quantity types).

**Decision rule (standing, 2026-09-16 + owner directive 2026-09-19):** a new
verb/predicate/node is justified by **≥3 pool shapes OR a named cross-set
mechanic**; solutions must be generalized (learnable, not hardcoded);
truly one-off weird cards go to the **per-card translator** (T8), not the grammar.

## Catalog probe results (verified, not assumed)
- `GAIN_CONTROL` **exists** as a verb → B5b's "Gain control of target creature
  until end of turn" (UNCOVERED reason "No GAIN_CONTROL verb") is a **false
  UNCOVERED** — template bug, not grammar gap. (T7 must re-verify all 201.)
- `CostLoyalty(delta) ∈ CostPart` — verified constructible:
  `ActivatedAbility(Cost(parts=(CostLoyalty(-2),)), effect=...)` validates and
  fingerprints. Loyalty *costs* need no grammar work; the compiler must route
  loyalty lines to `ActivatedAbility` (compiler task, not grammar task).
- `CounterKind` already has LOYALTY, SOUL, PAGE, CHARGE, INCARNATION.
- `Selector` is single-zone (`zone: Zone`); `Zone` = (kind, controller).
- `DamageDealtEvent` = (amount, filter) — no source, no combat flag.
- `ZoneChangeEvent` = (from_zone, to_zone) — no subject filter.
- `CastSpellEvent` = (filter) — no controller, no source zone, no ordinal.
- `ControllerRef` = {YOU, OPPONENT, TARGET_PLAYER, ANY, ALL_OPPONENTS} — no OWNER.

## ADD (additive only; no renames, no semantic changes to existing fields)

### A. Power-only comparison predicates — `FAtomPred.POWER_LE`, `POWER_GE`
9 shapes: B2a #10/#32, B2b #45/#53/#75, B3 #128/#136, B5c #344. Cross-set:
"power N or less/greater" targeting and conditions are ubiquitous. (PT_LE/PT_GE
compare combined P/T and stay as-is.)

### B. `FAtomPred.NAME_CONTAINS` (name substring match)
3 shapes (B2a #2/#4 "a Basri/Liliana planeswalker", B2b #73 "a Teferi
planeswalker") + named cross-set mechanic: planeswalker-family triggers exist
in every set with PWs. NAME_EQ stays for exact names.

### C. Multi-zone selectors — `Selector.zones: tuple[Zone, ...] = ()` (additive)
≥10 shapes: "target player or planeswalker" ×3 (B3 #132/#138, B2b #55) needs
PLAYER∪BATTLEFIELD; "library and/or graveyard" search ×6 (B2a #18, B2b #37/39/41,
B4 #193/196) needs LIBRARY∪GRAVEYARD; "target spell or creature" (B5b #277)
needs STACK∪BATTLEFIELD. Semantics: effective zone set = {zone} ∪ zones.
`zones` empty ⇒ canonical JSON omits the key (fingerprint-stable for all
existing trees; zero ripple through the 8 template modules). NOTE:
"creature or planeswalker" is already expressible (one zone + FOr filter) —
do NOT add zone unions for filter-disjunctions.

### D. `Verb.CAST` (cast a spell from a zone)
7 shapes: B3 #134, B4 #177/#180/#181, B5c #318/#320/#340. Roles: source
(Selector over the source zone, incl. top-of-library via H), optional
cost-waiver / additional-cost params. Named mechanic: cast-from-zone is core MTG.

### E. Turn-scoped quantities — `QThisTurn(kind, referent)`
kind ∈ {LIFE_GAINED, CARDS_DRAWN}; referent = ControllerRef. 5 shapes:
B2a #12/#14/#16, B4 #147 (life gained) + B4 #163 (cards drawn) + named
cross-set mechanic. (Generalizes the handoff's "turn-scoped quantities" family.)

### F. Event extensions (additive optional fields, default None)
- `DamageDealtEvent`: + `source: Filter|None`, + `combat: bool|None` — 6 shapes
  (B2b #51/#55/#56/#69/#87/#89: source-vs-damaged-object, combat/noncombat,
  amount-to-effect links).
- `ZoneChangeEvent`: + `subject: Filter|None` ("another creature you control
  enters") — 5 shapes (B2b #53/#65/#67/#91, + B2b #45 partial).
- `CastSpellEvent`: + `controller: ControllerRef|None`, + `from_zone: Zone|None`,
  + `ordinal: int|None` ("your second spell each turn") — 5 shapes (B2b
  #61/#63/#97/#98/#101/#102/#104/#107 — controller-scoped casts).
- New events: `CardDrawnEvent`, `LifeGainedEvent`, `SacrificeEvent` (each with
  controller referent) — 6 shapes (B2b #109/#111/#113/#115, #121, #123) + named
  cross-set mechanics.

### G. `Verb.LOSE_GAME` — 1 shape (B2b #47) + named cross-set mechanic (cheap).

### H. Zone position — `ZonePosition` enum {TOP, BOTTOM} + `Zone.position: ZonePosition|None = None`
"the top card/N cards of your library", "put on top of its owner's library" —
3+ shapes (B5c #324/#326, B4 #185) + named mechanic.

### I. Per-player loop — `EachPlayer(ref: ControllerRef, effect: Effect)` (Effect node)
"each opponent creates/sacrifices…" — 2 shapes (B2a #26/#28) + named mechanic
(per-opponent effects are common).

### J. ETB state — `EtBState(tapped: bool = False, initial_counters: tuple[tuple[CounterKind, Quantity], ...] = ())` (Ability node)
"This creature enters tapped" ×2, "enters with X +1/+1 counters", "This
Equipment enters with a soul counter" — 4 shapes (B4 #155/#157/#159, B5c #310) +
named mechanic (entering tapped/counters is among the most common ETB states).

### K. Cost modification — `CostModifier(filter, controller_ref, delta: CostDelta)` (StaticAbility alternative)
8 shapes (B4 #141–#153, B5b #261). CostDelta ∈ {reduce_generic(N),
increase_generic(N), reduce_mana(color,N), increase_life(N), waive_mana}.
Named mechanic: cost modifiers are among the most common statics in MTG.

### L. Loyalty + emblem
- Compiler routes `[+N]:/[−N]:/[−X]:/•` lines → `ActivatedAbility(Cost(parts=(CostLoyalty(...),)))`
  (grammar verified working; 29 PWs in pool, loyalty in every set).
- `EmblemAbility(embedded: Ability)` — emblems with embedded triggered/static
  abilities — 3 shapes (B5c #334/#336/#338) + named mechanic.
- "put a loyalty counter on X" = `PUT_COUNTER(CounterKind.LOYALTY)` — already expressible.

### M. `Verb.PAY` (pay a cost as an effect)
3 shapes (B2a #6, B2b #83/#115: "you may pay {N}[{B}]" + 'If you do'
continuation). Role: cost: Cost. Named mechanic (pay-as-ability is common).

### N. `ControllerRef.OWNER`
"return to its owner's hand" / "owners' hands" — 2 shapes (B5c #348/#350) +
named mechanic (return-to-owner's-hand recurs in every set).

## DEFER to per-card translation (T8) — one-off or card-specific, not generalizable
- **Cross-sentence anaphora** (~20 shapes, mostly B5b): "it/them/that card/
  those cards/the rest/its controller/that player/round up each time/When you
  do" — resolution needs the whole card text; per-card translator sees it.
- **Modal headers** "choose one —" (2 shapes in pool; the effect-level Choose
  exists; modal ability structure is per-card).
- Coin flip (1), damage-amplification replacement (1), counter-amplification
  replacement (1), half-library/half-life computation (1), set-level "two or
  more" conditions (2), play-with-top-revealed (1), mana restriction (1),
  blocking restrictions (3 — needs a blocking-restriction static; deferred:
  only 3 shapes here and combat-rule-heavy; revisit if frequency grows),
  dynamic protection-from-name (1), cross-card activation — Teferi (1),
  copy-targeting (1), search-until (1), "you may play that card until you
  exile…" (1).

## Explicitly NOT adding (over-engineering guard)
- No per-card tutor constructs (covered: SEARCH + NAME_EQ + multi-zone C).
- No wildcard/ANY-zone beyond the zone-union C.
- No new event for "enters the battlefield" as such — ZoneChangeEvent with
  to_zone=BATTLEFIELD suffices (etb = zone change into BATTLEFIELD).

## Implementation constraints (binding for the implementer)
1. **Additive only.** New fields default to None/empty; existing trees must
   serialize byte-identically (fingerprint stability — PC-4/PC-9 rail).
2. Every new node/enum: frozen dataclass + `__post_init__` validation +
   `_TAG` registration + `to_dict`/`from_dict` + canonical JSON, following the
   file's existing machinery (see the `_TAG`, `_FIELDS`-style tables near the
   end of `ability_tree.py`).
3. Validation tests per new node: construct + round-trip + fingerprint stable +
   ≥2 rejection cases (bad type, bad value).
4. This task changes **grammar only** — no template/compiler edits (those are
   the follow-up wave, after this lands and the full suite is green).
5. Full suite (`pytest MTG_bot/core -q`) must end green (was 724 at decision time).
6. Re-verify the false-UNCOVERED claim (B5b GAIN_CONTROL) and any other
   "reason says construct missing" entry the implementer happens to disprove —
   list them in the report; do NOT add templates in this task.

## After this task (sequencing)
- Wave: per-bucket template coders add templates for newly-coverable shapes,
  move them out of UNCOVERED tuples, update tests (incl. T4: B5a UNCOVERED →
  machine-readable).
- T5 measurement harness → PC-1..PC-10.
- T7 adversarial semantic spot-check vs real card knowledge (internet-verified)
  — re-verifies all remaining UNCOVERED entries + sampled covered trees.
