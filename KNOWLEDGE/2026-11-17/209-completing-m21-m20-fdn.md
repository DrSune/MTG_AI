# 209 — Completing M21, M20 and FDN: the census, the packages, the batches and the order

**Context.** The owner (2026-11-17): "Fix the remaining cards/label them so we have full sets of
cards to play on. This would be much more interesting than training on a handful of incomplete
sets. ... The remaining cards are likely complex, so optimizing their sharing of existing
components is beneficial both for the components count and learning."

This note is the census and the plan the playbook's step 5 asks for before any IR work
(`docs/PLAN_CARD_ONBOARDING.md`, KNOWLEDGE/2026-11-14/207). Nothing was changed: no record, no
code, no IR. A parallel review of component sharing is note 210; §7 here is what it needs.

**State on 2026-11-17** (`cardtool status M21 M20 FDN`): M21 275 of 285 verified, M20 277 of 329,
FDN 190 of 517 (6 of them reprint stamps). 389 cards are unverified.

Evidence: `reports/completion_2026-11-17/`.
- `census.py` builds everything; `classes.py` holds the judgments (each card's need class, the
  missing pieces with their patterns, the labels, the order of work).
- `worklist.json`: one entry per card (set, name, oracle id, state, need class, packages or batch,
  the step that completes it, notes), every sentence with its parse, plus the packages and the
  order.
- `census.txt`: the numbers below.

## 1. The numbers first

| Set | Unverified | (a) review only | (b) map from existing atoms | (c) new component | (d) engine fault | (e) refused |
|---|---|---|---|---|---|---|
| M21 | 10 | 1 | 0 | 8 | 1 | 0 |
| M20 | 52 | 2 | 3 | 47 | 0 | 0 |
| FDN | 327 | 4 | 199 | 121 | 3 | 0 |
| **All** | **389** | **7** | **202** | **176** | **4** | **0** |

| Measure | Value |
|---|---|
| Unparsed sentences of the 389 cards | 639 |
| ... that the compiler parses alone | 13 (9 on cards the compiler refuses whole, 4 continuations of an unparsed sentence) |
| ... with a verified analog word for word / by slot (207 §4) | 42 / 24 |
| (b) cards whose every unparsed sentence has a verified analog | 13 |
| (c) and (d) cards needing 1 / 2 / 3+ missing pieces | 144 / 32 / 4 |
| Missing pieces (packages): new components (c), engine faults (d), rulings (r) | 59, 4, 3 |
| ... used by 4 printings or fewer in the 19 sets | 20 |
| Gate rounds in the plan | 19 (rounds 12-30) |
| Printings of these 389 cards in the other 16 sets with the same text | 115 (87 of (b) cards): reprint stamps once the home stamp exists |
| Castable today, though unverified | 311 (137 of them (c): dealt in the castable and all pools with a piece missing) |

**Readings.**
- **FDN is a mapping job; M20 and M21 are the IR tail.** 199 of FDN's 327 unverified cards need
  only a record from existing atoms. 47 of M20's 52 and 8 of M21's 10 wait on a component.
- **The grammar is word-exact, so most of FDN never compiled.** "Destroy all creatures.",
  "Counter target creature spell.", "Draw three cards." and "Create a Food token." parse in no
  context. Only 13 of the 639 unparsed sentences parse alone, each unparsed only because its card
  is refused whole or its antecedent did not parse.
- **M21's ten "compiled" cards are not ten reviews.** Only Mangara needs a review alone. Six
  wait on the permission lane and two on copies; five of the eight are engine-unsupported and
  never dealt (a suppressed permission, or COPY with no executor handler). Conspicuous Snoop's
  third ability compiles as a placeholder (a granted reveal, not "all activated abilities of that
  card"). See the Truth's other branch compiles wrong.
- **One needs-atom note of 55 is stale:** M20 Chandra's Outrage (the BACKLOG's "two answers, one
  of them stale"). Mystic Forge's "re-map it" in the BACKLOG no longer holds: its permission is a
  free activation, which G0's costs lint refuses (MAPPER_GUIDE mistake 9).
- **Nothing is refused whole.** Two sentences take a label (§5).

**Expected totals** (207's rates: 15% of mapped cards end needs-atom or WRONG, 10% of package
cards, 5% of compiled ones; all-pass in brackets):

| After | M21 | M20 | FDN |
|---|---|---|---|
| today | 275 | 277 | 190 |
| the reviews and the two mapping waves (A0-A3), no code | 276 (276) | 281 (282) | 363 (393) |
| then the engine wave and rounds 12-16 (permissions, becomes, copies, counters, surveil and ward) | 283 (284) | 288 (289) | 406 (441) |
| all 19 rounds | 284 (285) | 324 (329) | 475 (517) |

## 2. How it was counted

- **Computed** (`census.py`): states as `cardtool status` gives them, sentences and their parse
  (template id, or UNPARSED with what `cardtool parse` makes of it alone), the verified analog of
  each unparsed sentence (207's slot normalisation, over every verified record of the 19 sets),
  the nearest parsed sentence (`cardtool similar`, with the components its tree uses), the
  printings elsewhere, the reach, the batches, and the totals per step.
- **Judged** (`classes.py`): every card that is not a plain mapping, by reading its unparsed
  sentences against the IR (`ability_tree.py`: 51 verbs, 57 filter predicates, 20 event classes,
  23 keywords, 7 counter kinds, the cost parts) and the engine. The 55 needs-atom notes were
  re-read against rounds 8-11 and the engine waves since 2026-11-05. Where a card looked
  mappable but no verified card has its shape, it is (b) with a risk note: the mapper's trace
  decides (Angelic Destiny returning itself, Hoarding
  Dragon's linked exile after its death, Good-Fortune Unicorn's counter, Scrawling Crawler's
  drawer).
- **The reach is a pattern count, checked by hand.** Each package has regexes over unparsed
  sentences (reminder text removed). Every match in the other 16 sets was printed and read; the
  patterns that over-matched were narrowed (a capitalised word must stay capitalised; "unless
  they're mana abilities" is no punisher; "becomes the target of a spell or ability an opponent
  controls" is round R5-6's existing event). Over the three sets the patterns agree with the hand
  assignment except one known case (Chandra, Acolyte of Flame's -2 cast is the existing one-shot
  CAST; its rider is REPLACE).
- **"Only" means only the piece the patterns detect.** A printing elsewhere whose one detected
  piece is P is counted as unlocked by P; its other unparsed sentences still need mapping, and a
  piece no pattern names is not seen. So the other-16 numbers are an upper bound on cards made
  whole and a fair rank between packages.

## 3. The packages, by reach

Reach = cards here that need only this piece + printings of the other 16 sets whose only detected
piece it is. Every (c) package is an IR change, so it needs a gate round.

| Package | Kind | Here (only) | Other 16: touched (only) | Reach | What is missing |
|---|---|---|---|---|---|
| PERMIT | c | 28 (19) | 100 (79) | 98 | cast or play from another zone: flashback, impulse draw, casting from a graveyard or the library top, free casts (R5-2, R5-3, R5-8, designed in §10, never built) |
| BECOMES | c | 9 (6) | 60 (51) | 57 | "becomes" effects: a noncreature becomes a creature (creature lands, crew), set colour and creature types, "loses all other card types" |
| COPY_PERM | c | 9 (6) | 31 (23) | 29 | token copies, "becomes a copy" (R5-5 CopyOf; Verb.COPY has no executor handler) |
| COUNTERKIND | c | 11 (6) | 29 (22) | 28 | counter kinds the IR lacks (stun with its rule, incubation, divinity, wish, revival, bait, fellowship, stash), a count of one kind, doubling |
| R_FOOD | r | 4 (4) | 26 (24) | 28 | the one Food TokenSpec (no card has one yet) |
| TARGETS | c | 5 (4) | 21 (16) | 20 | a predicate over what a spell targets ("a spell that targets you", "becomes the target of a spell", "costs less if it targets") |
| COUNTS | c | 9 (8) | 14 (11) | 19 | what an instruction did ("destroyed this way", "life lost this way": DESTROY, SACRIFICE and the mill write no `result`), and a quantity threshold ("total power 8 or greater") |
| DELAYED_MEMORY | c | 6 (3) | 21 (16) | 19 | a delayed trigger that remembers its objects, one-shot at "the next end step" |
| ENTERS_WITH | c | 8 (6) | 17 (10) | 16 | a moved object entering with counters or attacking; others entering tapped or with extra counters |
| R_TWOEVENTS | r | 3 (2) | 18 (12) | 14 | "When this enters or dies" (no tree has the shape) |
| OTHERCHOOSER | c | 6 (5) | 11 (8) | 13 | a choice another player makes: "unless they discard", "any opponent may", the owner's top or bottom, piles |
| COSTREF | c | 1 (1) | 13 (12) | 13 | "the sacrificed creature's power": the objects a cost moved |
| MANARIDER | c | 8 (3) | 16 (9) | 12 | spend on activations, "when that mana is spent", any type, mana kept across steps |
| GAMEEND | c | 3 (1) | 12 (11) | 12 | "you win the game", "can't lose the game", "that player loses the game" |
| PROHIBIT | c | 3 (3) | 10 (9) | 12 | can't gain life, can't cast more than one spell, can't cast from or enter from zones |
| SHUFFLEIN, DISCARD, SAMENAME, SPLIT | c | 4, 3, 3, 3 | 16, 10, 8, 17 | 11 each | D19's fold; a discard event (B-48); a name equal to another's; division among targets |
| WARD, CHANGELING, LURE, R_ITSCONTROLLER | c, c, c, r | 6, 3, 1, 1 | 6, 14, 9, 10 | 10 each | |
| ALTCOST, DOUBLING | c | 3, 3 | 9, 6 | 9 each | |
| ANYTARGETS, FLASHPERM, DAMAGEDBY, DURCONTROL | c | 3, 3, 2, 1 | 17, 10, 7, 7 | 8 each | |
| COPY_SPELL, ONCE, SURVEIL, CHOSEN, HANDSIZE | c | 6, 6, 6, 5, 2 | 11, 6, 2, 4, 8 | 7 each | |
| DISTINCT, TOUGHCMP, ALONE, DRAWSTEP, REDIRECT | c | 6, 2, 1, 1, 1 | 7, 6, 5, 5, 6 | 6 each | |
| 27 more | c, d | 1-6 each | 0-9 each | 0-8 | GIVECONTROL (d: GAIN_CONTROL's executor refuses any recipient but you), NAMEDLOCK, SETLIFE, LEYLINE, DAMAGEASSIGN, EXCESS, TOKENLEGEND, TARGETLINK, EXTRACOMBAT, PAYX, EACHTYPE, MODEMEMORY, PARTITION, POISON, RESOLVEDCOUNT, TRIGGERCAUSE, ZONEREPLACE (d), REPLACE, DELAYEDNEXT, OWNER, ATTACKED, EACHPLAYERTARGET (d), LIFEOTHER, SACSUBJECT, SEETHETRUTH (d), ABILITIESOF, GRANTOR |

`census.txt` §2 names each package's cards, its CR rules, its nearest existing atoms and its
examples in the other sets.

**Readings.**
- **The permission lane is the widest piece by far**: 28 cards here (M21's six, M20's three, 19
  FDN), 79 printings elsewhere. It was designed in gate rounds 1-3 (§10 R5-2) and never built.
- **Eight pieces reach 19 or more**, one of them a ruling: PERMIT, BECOMES, COPY_PERM,
  COUNTERKIND, the Food ruling, TARGETS, COUNTS and DELAYED_MEMORY.
- **Three are rulings, not components**: Food, "enters or dies" and "that creature's controller".
  Made before the mapping waves, they unlock 45 printings elsewhere at no IR cost.
- **SURVEIL and WARD are narrow elsewhere but wide here**: 11 FDN cards for two small pieces.
  Ward first appears in sets newer than the 16 others, so its reach grows with every new set.

## 4. The mapping batches ((b), 202 cards)

Eight batches of 25-26, cut in a fixed order of shapes so a batch holds one shape or two
neighbouring ones; one mapper and one brief (`docs/CARD_AGENT_BRIEFS.md` §2) each. 207's rates:
mapping 1.75 agent-minutes a card (24 cards in about 40 minutes), blind review about 1.1 with the
G3 follow-ups.

| Batch | Cards | Shapes | Rulings, risks | Mapping, review (agent-min) |
|---|---|---|---|---|
| M1 | 26 FDN | modal spells 11, instants and sorceries 15 | Food 1; orphaned cast carriers 2 | 46, 29 |
| M2 | 26 FDN | instants and sorceries | Elspeth's Smite and Fiery Annihilation take Scorching Dragonfire's verified form | 46, 29 |
| M3 | 24 FDN, 1 M20 | enters and dies triggers 23, instants 2 | its-controller (Chandra's Outrage), Food, two events; Hare Apparent's label; Hoarding Dragon | 44, 28 |
| M4 | 25 FDN | enters and dies 13, other triggers 12 | Angelic Destiny; Prayer of Binding's carrier | 44, 28 |
| M5 | 25 FDN | other triggers | two events, Food; Good-Fortune Unicorn | 44, 28 |
| M6 | 25 FDN | other triggers 18, statics 7 | Scrawling Crawler | 44, 28 |
| M7 | 25 FDN | statics (anthems, Auras, Equipment, conditions, costs) 17, activated 8 | none | 44, 28 |
| M8 | 23 FDN, 2 M20 | activated abilities 23, planeswalkers 2 | Food; M20 Bloodsoaked Altar and Diviner's Lockbox, FDN Ravenous Amulet (refused by the compiler's sorcery-gate fault, mapped whole) | 44, 28 |

Total: about 355 agent-minutes of mapping and 225 of review; two waves (M1-M5 five mappers at
once, then M6-M8 with wave 1's lessons and faults, as 207 §3 found pays).

What the brief adds this time:
- The three rulings, in MAPPER_GUIDE before the first wave.
- The grammar is word-exact: `parse` fails on every slot variant, so read `similar`'s nearest
  sentence (the worklist names it per sentence: "Double target creature's power" is M21 Unleash
  Fury's verified "Double the power of target creature"), and the verified analogs
  (13 cards are covered whole: Beast-Kin Ranger, Dazzling Angel, Driver of the Dead, Essence
  Scatter, Gilded Lotus, Hedron Archive, Hinterland Sanctifier, Icewind Elemental, Lyra
  Dawnbringer, New Horizons, Overrun, Refute, Rogue's Passage).
- Four FDN cards hold an orphaned cast carrier (BACKLOG): the record replaces the whole tree.
- A (b) card that turns out to need a piece goes to `needs-atom` with the piece named, as
  always; the census expects about one in ten.

## 5. Labels

No card is refused whole. Two sentences take a label:
- **M20 Vivien, Arkbow Ranger, the -5** ("reveal a creature card you own from outside the
  game"). The engine has no outside-the-game zone (CR 400.11). In self-play and Commander games a
  player has no sideboard, so the ability reveals nothing; labelled for good if the owner rules
  so. The card still needs SPLIT for its +1.
- **FDN Hare Apparent**, "A deck can have any number of cards named Hare Apparent." A
  deck-construction rule (CR 100.2a; Commander 903.5b): no in-game tree, and the drafter and
  `build_deck` must honour it. Labelled for good; G0's clause trace needs an accepted
  "deck rule" path for it.

Considered and not labelled: the Leylines (CR 103.6a is an in-game rule, LEYLINE), Herald of
Eternal Dawn and Maze's End (game results, GAMEEND), Curator of Destinies' piles
(OTHERCHOOSER). Every one is inside the engine's scope.

## 6. The order of work

Track A is card work with no code (records, verdicts, rulings; the coordinator commits). Track B
is the gate rounds, one merge each; their lanes may be built in parallel worktrees where the
files differ. Track C is the engine wave (no IR change: a fresh-eyes review, no gate). A runs
beside B and C throughout.

| Step | Track | What | Cards done | Agent-min | M21 / M20 / FDN after (all pass) |
|---|---|---|---|---|---|
| A0 | A | blind review of the 7 (a) cards | 7 | 8 | 276 / 279 / 194 |
| A1 | A | the three rulings | 0 | 30 | (45 printings elsewhere unlocked) |
| A2 | A | mapping wave 1 (M1-M5) and its review | 127 | 362 | 276 / 280 / 320 |
| A3 | A | mapping wave 2 (M6-M8) and its review | 75 | 214 | 276 / 282 / 393 |
| C1 | C | See the Truth's branch, a trigger's "target player sacrifices", replacements from anywhere, control given to another player; Mangara's runner op | 4 | 247 | 277 / 282 / 396 |
| B1 | B | round 12: PERMIT and REPLACE (3 lanes) | 21 | 474 | 282 / 286 / 408 |
| B2 | B | round 13: BECOMES and CHANGELING | 9 | 322 | 282 / 287 / 416 |
| B3 | B | round 14: COPY_PERM and COPY_SPELL | 11 | 327 | 284 / 289 / 423 |
| B4 | B | round 15: COUNTERKIND and POISON | 7 | 198 | 284 / 289 / 430 |
| B5 | B | round 16: SURVEIL and WARD | 11 | 327 | 284 / 289 / 441 |
| B6 | B | round 17: TARGETS, ANYTARGETS, TARGETLINK, SPLIT, REDIRECT | 12 | 330 | 284 / 295 / 447 |
| B7 | B | round 18: OTHERCHOOSER | 6 | 195 | 284 / 296 / 452 |
| B8 | B | round 19: DELAYED_MEMORY and DELAYEDNEXT | 6 | 195 | 284 / 299 / 455 |
| B9 | B | round 20: COUNTS and COSTREF | 10 | 206 | 284 / 301 / 463 |
| B10 | B | round 21: ENTERS_WITH | 7 | 198 | 284 / 302 / 469 |
| B11 | B | round 22: MANARIDER and CHOSEN | 10 | 206 | 284 / 303 / 478 |
| B12 | B | round 23: GAMEEND, PROHIBIT, HANDSIZE, LEYLINE | 10 | 324 | 284 / 309 / 482 |
| B13 | B | round 24: SHUFFLEIN, SAMENAME, DISTINCT | 13 | 215 | 284 / 315 / 489 |
| B14 | B | round 25: LURE, ALONE, DAMAGEDBY, EXTRACOMBAT, ATTACKED, DAMAGEASSIGN | 6 | 313 | 284 / 319 / 491 |
| B15 | B | round 26: ALTCOST and FLASHPERM (ledger F9's POLICY first) | 6 | 195 | 284 / 321 / 495 |
| B16 | B | round 27: DISCARD (B-48's fold) and DOUBLING | 5 | 310 | 284 / 322 / 499 |
| B17 | B | round 28: ONCE, RESOLVEDCOUNT, TRIGGERCAUSE | 8 | 201 | 284 / 324 / 505 |
| B18 | B | round 29: ten small vocabulary pieces | 13 | 333 | 284 / 328 / 514 |
| B19 | B | round 30: the one-card components (the owner's call) | 5 | 310 | 285 / 329 / 517 |

**What runs beside what, and what conflicts.**
- A0-A3 conflict with nothing: records and verdicts only.
- C1 runs beside A and B1. Its replacement fix touches `replacements.py`, which B10 and B16 also
  touch: merge C1 first.
- B1 touches `legality.py` and `stack.py`, which B6 (the cost after targets, 601.2f), B9
  (`pay_costs`), B11 (payment) and B15 (the cast lane) touch too: those merge after it.
- B2 and B3 both touch `layers.py` (layers 4-5 and layer 1): build them side by side, merge B2
  first. B10's types on entering objects follow B2.
- B6, B8 and B17 share `binding.py` (designation, delayed triggers, ability identity): in that order.
- B4 and B12 share the state-based actions (poison, can't lose): B4 first.
- B16's discard fold re-bakes 27 compiled discard trees (B-48), many verified: the widest blast
  radius in the plan, so late.
- Every B round re-maps its cards (the needs-atom records through `cardtool write`, the partly
  compiled ones through a record) and sends them to blind review right after its merge; any
  verified tree it changes is re-verified, as 207 §3 requires.

**Time.** Track A about 610 agent-minutes. Tracks B and C: about 5,400 bottom-up (118 a lane,
40 a gate round, 20 for G3 rule work, 2.85 a card), or about 8,800 at 207's measured tail of 49
a card waiting on IR. At rounds 4-11's pace (eight rounds in five days) the 19 rounds take two to
three weeks; the mapping waves take two days.

**Beside A0:** the 27 home stamps whose packs no longer kill a critical G3 mutant (BACKLOG,
"Records to map or re-verify") are cards already in the pools. They do not change these counts,
but each needs a pack before its next re-verification, and their reprints wait on the same packs;
they fit A0's verifier batch.

## 7. Component sharing (for note 210 and the gate rounds)

**The (b) batches reuse only existing components.** The components of the nearest parsed sentences
(`census.txt` §3, per batch) are the common ones: TriggeredAbility, StaticAbility,
ActivatedAbility, MOVE_ZONE, MODIFY_PT, GRANT_ABILITY, DRAW, DEAL_DAMAGE, CREATE_TOKEN with
TokenSpec, PUT_COUNTER, ZoneChangeEvent, CostTap and CostSacrifice. No (b) card adds a component;
the three rulings fix one encoding each where a mapper would otherwise invent one.

**The 59 (c) pieces share more than their names say.** Built as separate components they would
add about 59 node types, predicates, verbs or slots. Grouped by mechanism they are about 19:
- **One cast-permission verb** (PERMIT): R5-2's PERMIT_CAST with its `alternative` role also
  carries ALTCOST's alternative costs and Omniscience's free casts; a timing role (or ledger F9's
  single POLICY verb) carries FLASHPERM. Three packages, one component.
- **One characteristic-setting atom** (BECOMES): set or add types, set colours, the creature-ness
  of a noncreature. It also carries CHANGELING ("every creature type"), CHOSEN's "is the chosen
  type" and ENTERS_WITH's "is an Angel in addition". Keep GRANT_TYPE's add mode, not a second verb.
- **One CopyOf value** (R5-5) for COPY_PERM and COPY_SPELL.
- **One comparison predicate** (a quantity against a quantity) carries COUNTS' thresholds
  ("total power 8 or greater", "at least one ... this way", "four or more"), TOUGHCMP
  ("toughness 4 or greater", Thunderkin's toughness against its own), LIFEOTHER ("exactly 10
  life") and DISTINCT's thresholds (seven lands with different names). It could also absorb the
  five comparators BACKLOG B-44 would fold into one property comparison (CMC_GE, COLOR_COUNT_GE,
  CONTROLLER_COUNT_GT, LIFE_LEAD_OVER_START_GE, NAME_PARTITION_COUNT_GE). That is the widest
  sharing gain in the plan: one predicate in place of four new ones and five old.
- **One register mechanism**: COUNTS' `result` from DESTROY, SACRIFICE and the mill, and
  COSTREF's paid objects.
- **One DelayedTrigger extension**: DELAYED_MEMORY and DELAYEDNEXT.
- **One counter vocabulary**: COUNTERKIND and POISON (poison as a player's counter kind).
- **One ability-identity slot**: ONCE, RESOLVEDCOUNT and TRIGGERCAUSE.
- **One chooser role**: OTHERCHOOSER for punishers, piles and the owner's choice. Ward's "unless
  its controller pays" stays COUNTER_SPELL's existing `unless`.
- **Events already in the IR, given a slot each:** SACSUBJECT (SacrificeEvent gains the `filter`
  every other event has), DRAWSTEP (a DRAW value), TARGETS (TargetingEvent's targeting object).

**Flagged: a natural encoding would add a component used by 1-2 cards** (≤ 4 printings in the 19
sets; `census.txt` §2 marks the ≤ 2 ones LOW):

| Piece | Cards (19 sets) | Fold it into |
|---|---|---|
| EACHTYPE | WAR and FDN Liliana, Dreadhorde General (-9) | none found: a choice per permanent type, then "the rest" |
| PARTITION | M20 Kaalia, THB Relentless Pursuit | a per-kind count on ONE_OF |
| POISON | KHM and FDN Fynn, the Fangbearer | COUNTERKIND (player counters); later sets bring infect and toxic |
| RESOLVEDCOUNT | FDN Venom Connoisseur, ZNR Omnath, Locus of Creation | ONCE's ability identity |
| OWNER | M20 Agent of Treachery, FDN Tinybones | an owner twin of CONTROLLER_IS |
| ATTACKED | M20 Scorch Spitter | a referent over DeclareAttackersEvent.attacked |
| LIFEOTHER | FDN Hidetsugu's Second Rite | the comparison predicate |
| SACSUBJECT | FDN Ordeal of Nylea | SacrificeEvent's `filter` |
| GRANTOR | FDN Fishing Pole | none: a referent to the granting object inside a granted ability |
| ABILITIESOF | M21 Conspicuous Snoop | none |
| MODEMEMORY | FDN Demonic Pact, ZNR Kargan Intimidator | a per-object record of chosen modes |
| TRIGGERCAUSE | M20 Yarok, ZNR Ancient Greenwarden, DOM Naban | ONCE's ability identity on AbilityTriggerEvent |
| EXTRACOMBAT | FDN Aurelia, ZNR Moraug, 10E Relentless Assault | EXTRA_TURN's sibling |
| PAYX, EXCESS, TOKENLEGEND, DAMAGEASSIGN | 3-4 printings each | PAY's X; a QProp field; a TokenSpec field; a scope value |
| REPLACE | 3 here, 0 elsewhere by pattern | not low-use: R5-12 retires the card-level replacement of 11 resolving spells |

These are the decisions for note 210 and the gate rounds: build the shared mechanisms above; for
the flagged pieces either fold them as the table says or accept a one-card component (B19, the
owner's call). Building every one of them is what "full sets" costs; folding them is what keeps
the component count, and the network's vocabulary, small.

## 8. What this census does not know

- A mapper may find a piece the census missed; 207 measured 35% needs-atom without a census.
  The plan assumes about 10%.
- The engine may play a mapped tree wrong (14 of the 26 WRONG verdicts since 11-05 were engine
  faults). The risk notes name the likely ones. The executor also refuses some shapes only at run
  time (about 60 guarded `NotImplementedError` sites); reading them found one here (GAIN_CONTROL
  for another player, now GIVECONTROL), and a mapper's `cardtool try` shows any other.
- The reach in the other 16 sets counts detected pieces only, so it ranks packages; it does not
  promise whole cards there.
- The time per gate round assumes rounds 4-11's sizes. PERMIT, BECOMES and COPY are larger than
  any of those rounds (three and two lanes in the estimate).

## 9. The combined order (coordinator, 2026-11-17)

This merges 209 §6 with 210 §7. 210's folds come first so the remaining cards are mapped once. The
census's rounds follow, renumbered.

| Order | What | Notes |
|---|---|---|
| now, in parallel | N1 + N2 (network inputs, 210); round 12 = I1 + I9 + I0 (one quantity comparison, general TARGETS / QDistinct / zone counts); round 13 = PERMIT + REPLACE (209's B1, the widest reach); C1, the engine wave; the three rulings and two labels; A0, blind review of 5 (a) cards | merge order: C1, 12, 13, rulings; N1 + N2 when ready (no file overlap) |
| next | round 14 = I2 + I5 + I6; round 15 = I3 + I4; each round's re-baked stamps re-verified before the next | 210 §7 |
| then | mapping waves A2 (M1-M5) and A3 (M6-M8), with blind review | the 202 (b) cards, mapped once onto the folded forms |
| beside them | the 27 under-packed stamps, Mangara (after C1's runner op) and Stromkirk Bloodthief (after round 14) in the next verifier batches | their trees settle first |
| after | 209's rounds B2-B19 as rounds 16-33 | in 209 §6's order and file-conflict rules |
| then | the bug hunt: parallel unanchored hunters, the network-play exploit scan (per card and per card pair), the exploitability probe (PLAN_CEILING §9.1); then r29 | the owner's order, 2026-11-17 |

**Labels decided (the coordinator, under the owner's autonomy rule):**
- **Vivien, Arkbow Ranger's −5 is inert in our formats.** The engine has no outside-the-game
  zone, and neither self-play nor Commander gives a player a sideboard (CR 400.11).
- **Hare Apparent's deck rule is honoured by the deck builders** (CR 100.2a). The rulings agent
  applies both labels.

**Amended 2026-11-18 (coordinator).** The folds of round 14 (I2 + I5 + I6) and round 15 (I3 + I4)
now ride with the rounds whose cards need them. The rounds that complete M21 and M20 cards come
first: B3, then B6, B4 + B12, B13 with I5, and on. Why, and at what cost:
`docs/PLAN_PLANNING.md` §6.

**Amended 2026-11-18 (owner).** When every card of M21 and M20 is finished, the new components
those cards added get a redundancy review before FDN's rounds build on them. The review asks
whether any new component breaks down into existing ones, folding it in from the start, as 210's
review did for the components then.
