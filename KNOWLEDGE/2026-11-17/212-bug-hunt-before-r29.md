# 212 — The bug hunt before r29: the faults by cause, their fixes, and why the tests missed them

**Why.**
- The owner (2026-11-17): no long self-play until a hunt has ruled out exploitable faults. The hunt
  includes a scan for suspicious win rates by card and card combination, and for odd scenarios.
  r29 (208) waits for this hunt's fixes (209 §9).
- The hunt fixes causes, not symptoms. Faults are grouped by the mechanism that produced them, and
  the mechanism is fixed. Every fix comes with a test that fails on the old code.

**Severity.**
- EXPLOITABLE: a line that real Magic forbids, that wins, and that the network can find.
- STRONGER / WEAKER: a card does more / less than printed.
- WRONG: it differs from the rules with no clear side.

## 1. The hunt
Five hunters ran in parallel on 2026-11-17. Each was given an area and no suspect. Their scratch
work is in the session scratchpad; the synthesis is this note.

| # | Area | Method | Faults |
|---|---|---|---|
| 1 | Network play | `tools/audit/exploit_scan.py` on r28's 3,254,323 training games (`reports/exploit_scan_2026-11-17/`): per-card and per-pair lift (Mantel-Haenszel in set × colour pair × seat × opponent strata), the odd-game tails, and 181 replays judged | none. The twelve strongest cards are the sets' bombs and lift either seat alike (the learner's gap is under 1 point), the 7 significant pairs are printed tutors, and the odd games are legal |
| 2 | Core rules | rules areas read against the CR, repro scripts, 750 random games under invariants | 4 (1 exploitable). Sound: priority and the stack, timing, the turn, combat legality, SBAs, mana, mulligans, losing. 0 invariant violations |
| 3 | Events and continuous effects | the same, plus random-game soaks with trace detectors | 5 (3 exploitable) |
| 4 | The training harness | `learner.py`, gates, resume, the features | 7 |
| 5 | The verified pool | each verified card's path in real games; the payer's view of mana | 2 (both weaker) |

Hunters 2 and 3 found two of the same faults independently: the dead token and the loyalty clock.
The mappers of 209's batches reported the engine faults their cards met (M2-M5), and those went
to the same fix waves. The exploitability probe (211) ran beside the hunt as its active search.

## 2. The faults by cause
Fix waves: **E1** (engine: objects and events), **E2** (engine: layers, costs, combat, mana) and
**T1** (harness).

**A. A dead token stayed a live object while a trigger named it** (BACKLOG B-112, closed).
- *The fault.* `Executor._cease_tokens` skipped any token that a waiting trigger referenced, so the
  token sat in a graveyard while players held priority (CR 704.5d, 111.7-8).
- *What it allowed.* Scavenging Ooze exiled it for a counter and life. Cavalier of Night, Brought
  Back and Gravewaker returned it to the battlefield. **EXPLOITABLE.**
- *How often.* 14 of 900 random games had a token in a graveyard at a priority point.
- *The fix* (E1, 7c5598f8, 0218c584).
  - Every token off the battlefield ceases at the state-based check, and `pending_references` is
    gone.
  - Waiting triggers read the token's last known information (CR 608.2h). Every read that met a
    ceased token goes through it: identity, P/T, keywords, "that player", protection and tapped
    state.
  - A selector never acts on a ceased token (CR 111.8).
- *Tests.*
  - The packs `scavenging_ooze_cannot_eat_a_dead_token_while_a_trigger_waits` and
    `cavalier_of_night_cannot_return_a_dead_token`.
  - `TestV35TokensCeaseOffTheBattlefield`.

**B. Per-object state keyed on a handle outlived a zone change** (CR 400.7: a card that changes
zones is a new object). Three tables:
- **The loyalty clock** (hunters 2, 3; WEAKER). A planeswalker that left and came back could not
  activate loyalty that turn (CR 606.3). E1 clears the clock as the planeswalker leaves.
- **detach_lki** (hunter 3; **EXPLOITABLE**). The table was never cleared, so Malefic Scythe got a
  soul counter when a creature it had equipped long before died (CR 603.10a). E1 removes the
  table: what was attached as a permanent left is now `LastKnown.attached`, dropped when the card
  re-enters.
- **"Exiled with"** (mapper M3; STRONGER). It counted the cards exiled by every life of a card. A
  Bag of Holding (verified) or Hoarding Dragon that left and came back returned its earlier
  life's cards too (CR 607.2a). E1 (1f2410b9) ties the link to the object's current life.
- *Tests.* One pack for each table, each failing on main.
- **The stack frame** (found after the hunt by gate 13's reviewer; **EXPLOITABLE**; identical on
  fdd1a021).
  - Unsubstantiate (M21, verified, dealt) returned a spell to its owner's hand but left its stack
    frame, so the spell still resolved. Shock plus Unsubstantiate on your own Shock dealt 2 damage
    and kept Shock in hand.
  - The same move skips flashback's exile, which should fire whenever the spell would leave the
    stack (CR 702.34a), not only when it resolves, fizzles or is countered.
  - Round 13's author fixes it at the cause: every move of a spell off the stack ends its frame
    and applies the leave-the-stack replacements.

**C. Layers ordered by registration, not by the rules** (CR 613; hunter 3).
- **Printed keywords** were layer records, stamped when the creature entered and folded in the
  order they were registered. **Attaching** an Equipment gave its effect no new timestamp (CR
  613.7e). Together: a creature with printed flying that entered after Colossus Hammer kept
  flying when equipped, a +10/+10 flier. **EXPLOITABLE.**
- **P/T-setting effects** were ordered on two clocks, and a characteristic-defining P/T was not
  applied first (CR 613.4a-b). M21 Kinetic Augur under Jolrael's X/X was 3/7, not 7/7. WRONG.
- *The fix* (E2, f901cc24).
  - A permanent's own keywords are its printed values, applied before every timestamped effect.
  - Attaching restamps the Aura or Equipment (CR 701.3c, 613.7e).
  - Layer 7a is applied before 7b, on one clock.
- *Tests.* `TestTimestamps` (4) and three packs.

**D. Costs read ownership where the rules say control** (hunter 2; WEAKER).
- *The fault.* `build_payment_plan` filtered sacrifice and tap costs on the player whose zone holds
  the card, which is its owner.
- *What it broke.* After Traitorous Greed, the thief could not sacrifice the stolen creature to
  Village Rites or Witch's Cauldron (CR 701.21a).
- *The fix* (E2, c3e3a28a). Both costs read the effective controller. No other cost lane reads
  ownership.

**E. Combat damage among blockers followed a rule that no longer exists** (hunter 2; WRONG).
- *The fault.* The engine asked for a damage assignment order, forced lethal damage first and put
  the excess on the last blocker. CR 510.1c (since 2024) lets the attacker divide damage freely.
- *What it cost.* The defender gained. A 5/5 blocked by Brash Taunter and a 2/2 had to damage the
  Taunter, which dealt that damage back.
- *The fix* (E2, caa4e63d, e5f2c687).
  - One "divide" ask per blocker. Trample still needs lethal damage on every blocker (702.19b),
    and lethal damage already marked needs none more.
  - The "order" and "trample" asks are gone.
  - The network gets "divide" as an appended ask kind, so r28's v2 computes bitwise what it did on
    every other ask. On a divide ask the network sees the attacker as the source and the blocker
    as the option.
  - The heuristic divides sensibly, and the 17 packs with order or trample lanes were converted
    with the same outcomes.

**F. The game's path differed from the tests' path.**
- **Conditional mana** (hunter 5; WEAKER).
  - Mana abilities have not been menu rows since 2026-11-11. Mana is made by the automatic payer,
    which priced only a plain add or a choice between adds.
  - M20 Leafkin Druid's "add {G}{G} instead" was never priced, so it never made mana in a real
    game. Its packs activated it directly, a path real games no longer take.
  - E2 (5826b09e) prices the branch the state picks. A new test requires every mana ability in
    the verified deal pools to be one the payer prices, or one of the scaffold's two listed
    exceptions (Prismite's filter, Kykar's sacrifice).
- **A refused row was taken as a pass** (hunter 2; WRONG).
  - Each target was priced alone, so two taxed targets could together cost more than the player
    could pay (Frost Breath at two Pursued Whales). The menu refused the designation, and the game
    loop took that as a pass, so the player lost its main phase.
  - E2 (a6bebbcc) prices targets together: asks and rows offer only designations the player can
    pay.

**G. An event left out of the journal** (hunter 5; WEAKER).
- *The fault.* Counters a permanent enters with were added with no journal row.
- *What it broke.* Wildwood Scourge never saw a creature enter with +1/+1 counters (CR 122.6).
- *The fix* (E1). The placement is an atom boundary of its own, with COUNTER_PLACED rows.
- *Tests.* Two Wildwood Scourge packs.

**H. The training harness** (hunter 4; T1, d7d2e108).
1. **A failed gate re-ran after a resume**, on the same deals with a later snapshot. r28's gate at
   100 read 0.5445, then 0.5413. That means selection on freezes, and duplicate gate rows, which
   r29's B8 reads. *Cause:* 197 C1's commit point did not cover a gate that failed. *Fix:* a
   finished evaluation is committed as ended before it is logged.
2. **A resume rebuilt the card table** from `--init` and the compile of the moment, and kept only
   last.pt's weights (197 C4's class). *Fix:* the network and its table travel together.
3. **Gate deals ignored `--seed`**, so a run started from v2 re-tested v2 on the very block that
   selected it. *Fix:* gate blocks move with `--seed`.
4. **A batch took games in the order they ended.** That skews the sample after a start, after a
   resume and after every gate (the cause of 190 §1.8). *Fix:* games are taken in the order they
   were issued.
5. **Options the network could not tell apart**: an ability as a target (Tale's End), and a
   source's several waiting triggers. *Fix:* both now encode apart. v2 is bitwise on every other
   ask: 4,573 of 4,576 decisions are unchanged, and the 3 that change are these asks.
6. **No watchdog.** A hung game stopped the gates silently. *Fix:* a void after 600 s.
7. **Cosmetic:** counters and a false comment.

Also from hunter 1, in T1: the heuristic's targeting blunders. It put Furor of the Bitten on the
opponent's creature, Pacifism on its own, and Return to Nature on its own Nine Lives, and the
learner profited from them. A beneficial effect now targets the heuristic's own side and a
harmful one the opponent's.

**From the mappers, same waves.**
- **Angelic Destiny's dies trigger never fired** (M4; WEAKER). CR 113.6m's Aura exception was
  missing. Fixed in E1.
- **Another player's discard was put to the caster** (M3; STRONGER, in no verified tree; CR
  701.9b). Fixed in E2, 31df1054.
- **A negative number was applied as negative** (M5; CR 107.1b).
  - Halana and Alena at power -2 removed counters, a negative life gain lost life, and "gets
    -X/-X" with X = -2 gave +2/+2.
  - E2 (1dfe55ac) adds one clamp for every verb.
- **Frenzied Goblin's combat-slot target was never designated** (M7; WEAKER). Fixed in E2,
  11575276.
- **A prevention was locked onto the spell's targets even when it did not name them** (M2; CR
  611.2c). Fixed in E2, ed4c0572.
- **Angel of Finality** was already fixed by engine wave C1. A test in E1 pins it.

**From hunter 1's replays, not engine faults.**
- The cap-draw versus mutual-loss reward asymmetry: legal play; in BACKLOG.
- A D5 false positive.
- The network's no-op re-equips.
- An emblem label.

## 3. Why the tests missed them
The faults fall into seven patterns. Each pattern hid a class, not one card, so each gets a guard.

| Pattern | Faults it hid | Guard |
|---|---|---|
| **One life per card.** Every pack and test put a card onto the battlefield once. CR 400.7 was tested on the object map (206), never on side tables keyed by a handle | B (three tables and the stack frame) and A | A 400.7 audit: every handle-keyed table or read declares its behaviour (cleared on departure, or read through `LastKnown`), and a test lists them. E1's review already found two more reads (`CAST_THIS_TURN_FROM`, the 704.5n Equipment lane). Second-life packs for cards that link to their past |
| **A fixture that is not the real thing.** The "loses flying" packs used a creature given flying by an effect, never printed flying. Leafkin's packs activated a mana ability, which real games stopped doing on 2026-11-11. No pack can set up a permanent controlled by a non-owner | C, F(a), D | Packs take the game's own paths: a lint rejects a pack step real games never take. E2's test that every verified mana ability is priced. The pack vocabulary gains control by a non-owner |
| **State checked, not events.** Tests of entering with counters checked the counters, never the journal row a watcher needs | G | An effect's test checks its journal rows. A G3 mutant that drops a row must be killed by a watcher |
| **The engine and its tests shared one reading of the rules.** The damage order was written to the pre-2024 rule, and its tests pinned the same reading | E | Rules areas are re-read against the pinned CR text. A rules change since an area was written is a hunt item |
| **A shortcut outlived its reason.** B-112 kept a dead token alive for its waiting triggers, and sat in BACKLOG from 2026-10-30. Nobody asked what a player could do with it | A | A shortcut's BACKLOG entry states what a player could do with it, and hunts start from those entries. A random-game invariant: no token off the battlefield at a priority point. The 750-game suite had none |
| **One candidate at a time.** Each target was priced alone, and the tests had one taxed target | F(b) | Pricing is of the whole designation (E2) |
| **The happy path of a resume.** Resume tests stopped after a passed gate, compared weights rather than the table, and never varied the gate seed | H1-H3 | T1's tests stop at each commit point and compare the run's state |

**What the statistics can see.** The exploit scan finds a card lift of 0.55 points or more at 80%
power. None of the three exploitable faults (the dead token, the Scythe, the Hammer) showed in it:
each fires in few games. Win-rate scans are a screen for frequent faults only. Rare faults are
found by invariants, detectors, reading the rules, and the probe. This hunt used all of them, and
the next one should too.

## 4. Left open (BACKLOG)
- From E1's review:
  - B-112's residue: CR 111.8 inside one resolution.
  - The network's view of an ability whose source ceased.
  - A planeswalker's entering loyalty, journalled on the cast lane only.
  - The two handle-keyed reads above. These go to the 400.7 audit.
- From E2: a blocker of several attackers (CR 510.1d) is unmodelled.
- From mapper M2:
  - MOVE_ZONE with its object under `target` ignores entering tapped and the battlefield
    controller. This is 210's I4, gate round 15.
  - A REVEAL of 0 over the library top.
- REVEAL after SEARCH shows the top card. Information only.

## 5. For r29
- **The fixes change the game for both arms.** B1, A against B head to head, is clean.
- **B8 is not clean.** It compares B's gates against v2 with r28's gates, which r28 played on the
  old engine and pool. These now differ: the divide ask that v2 never trained on, the fixed
  layers and costs, and gate deals moved by the seed.
- **208's B3 is the registered guard.** If A's own gates against v2 rise, B8 compares against A's
  mean. The launch note re-reads B3's power against the shift these changes can cause, and amends
  208 before any r29 game if B3 is too weak to catch it.
- **The heuristic changed (T1).** It is the rating anchor and the behaviour-cloning teacher, and
  the new one scores 0.533-0.540 against the old. No number against the heuristic compares across
  this merge.
- **The confound record at launch** lists these changes beside N1/N2, the table refresh and gate
  rounds 12-13.

## 6. Status (updated at each merge)
| Wave | Branch head | State |
|---|---|---|
| E1 (A, B, G, Angelic Destiny, "exiled with", Garna's last-known attacking) | b96f0652 | **merged** (c80f45f7). Three fresh-eyes reviews. 600 replays: 0 crashes, digests identical, 74 journals differ (72 by the new COUNTER_PLACED rows); no tree changed. Its audit of the handle-keyed tables: three fixed, the rest cleared at departure or safe by design, four latent cases in BACKLOG |
| E2 (C, D, E, F, the mappers' faults) | d3798ad7 | **merged** (68d59bf2). 600 seeded games: 233 differ (124 the division, 22 a trample-over, 14 Leafkin, 1 a negative power, 72 renamed asks only), 0 crashes, 9 winners changed; r28 v2 bitwise on every old ask; 1 of 5,671 trees changed (ORI Liliana, unverified) |
| Round 13 (the stack frame, with its own gate conditions) | b81727f1 | **merged** (bb9932fa). Every move of a spell off the stack ends its frame and passes the leave-the-stack replacement (`verbs._off_the_stack`); the Unsubstantiate pack fails on main 4739cfef. Graded: your own instant or sorcery returned to hand EXPLOITABLE; a spell exiled or put into a library WRONG (only THB Ashiok's Erasure, unparsed); a flashback spell returned to hand STRONGER. Only Unsubstantiate and Ashiok's Erasure move spells in the 19 sets |
| T1 (H, and the heuristic's targeting) | 4670395c | **merged** (5411f386). Two fresh-eyes reviews. r28's v2 is bitwise on 4,573 of 4,576 decisions; the 3 that change are the new option forms. The new heuristic scores 0.533-0.540 against the old one |
| Recurrence guards G1 (§3: the 400.7 registry over real games, the token invariant I1) | d75690de | **merged** (72ef87d2). 47 handle-keyed containers declared. One more fault fixed: "exiled with" counted an exile in the life it arrived in (Bag of Holding returned by Brought Back while its trigger waited; STRONGER, reachable in M20). Soak I1: 6 of 900 games before E1, 0 after |
| Recurrence guards G2 (the probe, the pack runner's game paths, G3's dead sets, verify's supporting cards, the designation lint, control by a non-owner) | e5f14b25 | **merged** (6fc85cf8). One engine fault fixed: only a permanent's first mana ability was priced (Gift of Paradise; WEAKER). 52 packs that activated mana abilities now pay as a game does |
| Confirmation | — | the exploit scan of the probe's games: no flag (211 §4). Two faults found after the hunt by verifiers, open at r29's launch, fixed before its FDN segment (208 §9): counters gained off the battlefield survive a return (CR 122.2; STRONGER, rare); battlefield endpoints read the zone owner (`binding._zone_matches`; WEAKER) |
| E3 (the two faults above, the class-D audit of ownership read where control is meant, G1 dealt from recorded cards, a spell an ability casts paid with mana abilities, G3's equivalent mutants) | 92061a25 | **on its branch** (`worktree-agent-aa826eade9066c90a`; NUMBERS 2026-11-18), for FDN's segment. Two fresh-eyes reviews. Counters cease at every zone change, the entry's own stamps after; a source that changed zones gets no counter from its waiting ability; on the battlefield a side is control (trigger and replacement endpoints, the sacrificer, the "you" of what a permanent enters with, player-scoped selectors). No tree changed; 600 replays identical, 0 crashes. MOVED_TO_ZONE_THIS_TURN's owner reading is an IR question (BACKLOG) |
