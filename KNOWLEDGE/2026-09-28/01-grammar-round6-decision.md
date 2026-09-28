# 2026-09-28 · 01 — Grammar round 6 BINDING spec (conditional statics + restriction semantics)

Status: BINDING for the round-6 implementation. Grounded from the live residual queue (98 shapes /
100 occurrences at HEAD 4183cd2) by analyst draft + orchestrator independent verification (all
cited lines re-checked at HEAD 4183cd2). Precedents: 2026-09-24/02 (r3), /05 (r4), /07 (r5),
2026-09-25/01, 2026-09-27/01. Conventions C1–C8 remain in force.

## Grammar items (all additive to `ability_tree.py`; omit-if-empty/None serialization)

| ID | Delta | Motivating shapes | Byte-stability argument |
|---|---|---|---|
| R6-1 | `FAtomPred.TURN_OF` + `_FATOM_RULES` row, slots {who: ControllerRef} | "During your turn, …" (Radha, Discontinuity) — no turn-owner predicate existed (Phase enum has no owner) | new enum member only; existing trees unchanged |
| R6-2 | `FAtomPred.ZONE_COUNT_GE` + `_FATOM_RULES` row, slots {who, zone(ZonePosition), inner_filter, count} | "an opponent has 8+ cards in their graveyard" (Thieves' Guild Enforcer) — CONTROLLER_COUNT_GE has no zone/who slots (2492–2495 verified) | new member; CONTROLLER_COUNT_GE rows untouched |
| R6-3 | `_VERB_ROLES[SET_PT]` (2632 verified): power/toughness required True→False; extend the at-least-one-role validation (today MODIFY_PT-only) to SET_PT | "power is equal to the number of …" (Kinetic Augur) — single-component P/T definition | validation-only change; 3 existing SET_PT builds (b5a:484, b3:386, b2b:1238) set both roles → serialization untouched |
| R6-4 | `DeclareBlockersEvent` (1097 verified): new trailing field `blocked: Filter \| None = None` + `_SPECS` entry `("blocked","opt:filter")`, omit-when-None | blocked-side restrictions: "can't be blocked", "can block only creatures with flying" (Tome Anima, Ghostly Pilferer, Subira, Shacklegeist) — event filter+subject are both blocker-side; also closes the standing round-5 Snarespinner item (`DeclareBlockersEvent.blocked`) | opt field omitted-if-None; no pre-batch tree sets it |
| R6-5 | `Verb.MANDATE_BLOCK` + `_VERB_ROLES` row mirroring MANDATE_ATTACK | "must be blocked if able" (Canopy Stalker); attack-side already has MANDATE_ATTACK | new enum; executor deferred per PHASE_IN-orphan precedent (PC-6 unaffected: template uses the verb) |

`CostModifier.condition` (T3 round-2) and `CARDS_DRAWN_THIS_TURN_GE` (verified b5a:292 usage)
already exist — shape 5/10 need NO further grammar beyond R6-1/R6-4.

## Binding conventions (new)

- **C9**: "as long as / unless" conditions on statics go in `StaticAbility.condition` (R3 slot) —
  NEVER a duration approximation. (Corrected the analyst draft's Tome Anima note: cond =
  FAtom(CARDS_DRAWN_THIS_TURN_GE ≥ 2, who=YOU) fits directly.)
- **C10**: restriction atoms = `PREVENT_EFFECT` with pairs ("condition"?, FAtom) + ("event",
  EventSpec), following the landed `_build_cant_block` idiom (templates_b4:396–407). The prevented
  event's filter selects the restricted participant; `blocked` (R6-4) narrows the blocked side.
- **C11 (decision — Faith's Fetters, lossy ACCEPT)**: cover "Enchanted permanent can't attack or
  block" (Seq of two PREVENT atoms on IS_ATTACHED_TO_SOURCE); DROP "its activated abilities can't
  be activated unless they're mana abilities" — needs an ability-activation event class + an
  ability-kind predicate, neither exists (event classes 1010–1360, FAtomPred 291–372 checked) —
  and it belongs to the ability-introspection family. Dropped clause named verbatim in the
  template docstring, per round-5 lossy precedent (07:27, 07:133; 2026-09-27/01:15–20).

## Template batch (13 rows; 13 distinct cards)

| tid | mod | card/sentence | IR sketch |
|---|---|---|---|
| B4-aslong-opp-gy-count | b4 | Thieves' Guild Enforcer | StaticAbility(cond=ZONE_COUNT_GE(opp,GY,card,8), Seq(MODIFY_PT +2/+1, GRANT deathtouch)) |
| B4-during-turn-grant-kw | b4 | Radha, Heart of Keld | StaticAbility(cond=FAtom(TURN_OF,YOU), GRANT FIRST_STRIKE on named referent) |
| B4-during-turn-cost-reduce | b4 | Discontinuity | CostModifier(condition=TURN_OF(YOU), delta −{2}{U}{U}) |
| B4-set-pt-power-equals-count | b4 | Kinetic Augur | SET_PT(power=QCount GY instants+sorceries) — R6-3 single-role |
| B4-enchant-no-untap | b4 | Capture Sphere | PREVENT(IS_ATTACHED_TO_SOURCE, TapStateEvent(tapped=False)); LOSSY: untap-step scope dropped (Step enum has no UNTAP — registered) |
| B4-cant-attack-unless-count | b4 | Gadrak, the Crown-Scourge | StaticAbility(cond=FNot(CONTROLLER_COUNT_GE(artifact,4)), PREVENT(IS_SOURCE, DeclareAttackersEvent(IS_SOURCE))) |
| B4-cant-be-blocked-aslong-drawn | b4 | Tome Anima | StaticAbility(cond=CARDS_DRAWN_THIS_TURN_GE(2,YOU), PREVENT(IS_SOURCE, DeclareBlockersEvent(blocked=IS_SOURCE))) — C9, no duration approximation |
| B4-must-block | b4 | Canopy Stalker | StaticAbility(MANDATE_BLOCK(IS_SOURCE)) |
| B4-block-only-flying | b4 | Shacklegeist | PREVENT(blocker=IS_SOURCE, DeclareBlockersEvent(subject=IS_SOURCE, blocked=FNot(FLYING))) |
| B2a-enters-with-x-counters | b2a | Wildwood Scourge | ETB ZoneChange(IS_SOURCE)+PUT_COUNTER(target referent="event", +1/+1, QX); X semantics per b5c:2222 precedent |
| B5a-enchant-cant-attack-block | b5a | Faith's Fetters | Seq(PREVENT attack, PREVENT block) on enchanted permanent — C11 lossy |
| B5a-discard-cant-be-blocked | b5a | Ghostly Pilferer | Activated(discard)→PREVENT(IS_SOURCE, DeclareBlockersEvent(blocked=IS_SOURCE), EOT) |
| B3-target-cant-be-blocked | b3 | Subira {1} | Activated→PREVENT(DeclareBlockersEvent(blocked=FAtom(IS_ANY_TARGET)), EOT) |

PC-3 double-match checks performed by analyst vs: Garruk-while (b4), Gnarled Sage conditional
(b5a:283–296), Defender/menace reminders (b5a:957), plain cant-attack (b4:396), Subira self/target
pair — disjoint. Acceptance re-gate: PC-3 must measure 0.

## Deferred / registered (round-7 + family queues)

1. Ability-introspection family: Faith's Fetters activated-clause, Conspicuous Snoop ("all
   activated abilities of that card"), Enthralling Hold (target legality) — need ability-activation
   event class + ability-kind predicate.
2. "As though" ability-grant domain (Drowsing Tyrannodon defender-exception; Garruk Savage Herald
   [−7] trample-as-though row) — 3 queue rows, 3 distinct domains.
3. Untap-step scoping: `Step.UNTAP` member + step-scope slot for TapStateEvent/StepEvent
   prevention (would repair the Capture Sphere lossy note; Frost Breath's "Those…" stays in family
   2 anaphora regardless).
4. Family 2 anaphora (next round family): "Those creatures…", "the chosen card name" (Runed Halo),
   "that many" (Kinetic Augur s1, Kinetic ETB), "When you do" (Tolarian Kraken), See-the-Truth
   pair, Furious Rise s2, Waker of Waves "one of them", "the rest" rows.
5. Singletons: Mangara set-quantity + attacked-target relation, Peer-into-Abyss "Round up",
   Chromatic Orrery ×2, Sanctum-of-All additional-trigger, Wildwood… covered above.

## Predictions (measured post-batch; queue is truth)

Grammar phase: suite 1278 → 1278+N (new `test_ability_tree_r7.py` — NOTE file-number offset:
round-5 grammar shipped in the r6 file; r6 grammar → r7 file), **0 golden diffs**, goldens at
HEAD byte-identical. Batch phase: PC-1 231 → ~242/305, PC-2 539 → ~553/639, queue 98/100 → ~85/87,
exactly 13 goldens re-baselined (abilities-key-only audit vs /tmp/golden_pre_r6_2026-09-27).
Not all 13 batch cards full-card-unlock (Radha/Kinetic/Subira keep residual shapes) — PC-1 delta
expected slightly below shape delta; treat analyst ±1 spread as noise, not failure.
