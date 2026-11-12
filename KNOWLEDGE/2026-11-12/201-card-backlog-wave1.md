# 201 — The card backlog, wave 1: engine faults fixed under ontology gate round 4

**Context.** The owner (2026-11-12): "Fix the backlog of cards please."
- For the trained sets that backlog is:
  - M21's 18 castable cards that were never verified (KNOWLEDGE/2026-10-30/177: engine gaps,
    probe limits, and two crashes found by window 2, 192 §7.6);
  - M20's 11 mapped cards, 2 refused and 61 waiting on atoms.
- Wave 1 took the engine faults behind M21's cards:
  - three agents in parallel, each in its own worktree;
  - one adversarial reviewer for the IR changes, as `docs/DESIGN_ATOM_ONTOLOGY.md` binds;
  - the merges in the reviewer's order, `tools/check.sh` after each.
- Main after the wave: 0a26977.

## 1. What was wrong, and the fix (each with packs that fail before and pass after)

| Card(s) | Fault | Fix | Commit |
|---|---|---|---|
| Runed Halo | "As this enters, choose a card name" compiled as a trigger. While it waited on the stack, the Halo's protection was live with no name: three of window 2's four castable crashes | `EtBState.effect`, the choice made as the permanent enters (CR 614.1c, 614.12a), dropped when it leaves (CR 400.7). CHOOSE_NAME only, until another card brings tests | deaba91, e6f9358 |
| Vito and every "target player/opponent" trigger | A Halo naming Vito left Vito's "target opponent" with no legal choice. The trigger stayed with an empty target: the fourth crash | The trigger is removed (CR 603.3d), and the player is re-checked on resolution (CR 608.2b) | deaba91 |
| Garruk, Savage Herald's -2; Rookie Mistake | Already right in the engine. The G1 probe tried target pairs that break "another", so they read as engine errors (177's "probe limits") | The probe filters such pairs with the engine's own rule | deaba91 |
| Drowsing Tyrannodon | Compiled as losing defender, so Portcullis Vine could not sacrifice it (B-80) | `Verb.ATTACK_POLICY(AS_NO_DEFENDER)`: an "as though" permission (CR 609.4) the attack check consults; the keyword stays | 1cac720 |
| Teferi, Timeless Voyager's -8 | "They can't phase in" compiled as a zone-change prevention, which phasing never triggers (divergence D16) | `PhasingEvent`, `IS_RESULT`, `DurationUntilEndOfNextTurn`, in the Frost Breath family's shape | 1cac720, 844c315 |
| Transmogrify | Took the library's top card; a noncreature put nothing onto the battlefield; it asked a player target it does not print | `REVEAL.until` (round 3's redesign of FIRST_MATCH) and the referent Selector for "that creature's controller" | 1cac720, 844c315 |
| Hooded Blightfang, Basri, Devoted Paladin, Leeching Sliver | "Whenever a creature attacks" fired once per declaration (B-103) | `once_per_event`: absent means once per occurrence (CR 603.2c); set means once per declaration or per damage step | 6f020b8, 3ece400 |
| Feline Sovereign | "One or more Cats deal combat damage" fired once per Cat, so it played stronger than printed | The same flag: once per damage step and recipient (CR 510.2) | 6f020b8 |
| (any) | A creature put onto the battlefield attacking counted as declared (B-102); this was hidden until B-103 was fixed | No declare row for it (CR 508.4) | 6f020b8 |

**Not fixed: Furious Rise.**
- It needs the permission lane: play from exile, and a window that ends on an event. Neither
  exists (R5-2, R5-8).
- Its pack `known_bugs/furious_rise_play_the_exiled_card.json` pins the gap.
- It stays out of the verified pool, so training never deals it. It stays in the castable and
  compiled pools by the 2026-10-02 decision, which wave 1 did not reverse.
- Conspicuous Snoop and Radha wait on the same lane.

## 2. Gate round 4 (`DESIGN_ATOM_ONTOLOGY.md` §9)

**Verdict: FIX-THEN-GO, no FATAL.** The reviewer checked by running, not only reading:
- it compiled all 19 sets on the base and on each branch, and diffed every tree;
- it ran the suites on each branch;
- it ran every new pack against the base, to confirm it failed there;
- it merged the three branches in memory: 1,702 of 1,702 packs and 3,366 unit tests passed.

**The ruled fixes, all applied before the merge:**
- `once_per_event` is refused where it is a second encoding, or where nothing groups it. A
  flagged trigger is checked as it queues, and both mutant directions are critical.
- IS_RESULT is allowed only where it cannot duplicate a referent Selector, and raises without a
  register. GAIN_CONTROL refuses a duration it cannot expire. REVEAL.until refuses its two
  second forms. 24 refusal tests were added.
- **R5-9 / D16 is superseded, accepted on four arguments.** The old tree was a phantom
  prevention, and "can't untap" and "can't phase in" now share atoms. The other two arguments
  are in §9.
- **D18 stays open:** "its controller" still has two encodings.
  - A MAPPER_GUIDE rule, and a conformance check that flags exactly Massacre Wurm.
  - B-114 schedules its fold.

## 3. The cards, the pools, and the tests

**The verified pools fell for now:** M21 262 → 260, M20 254, FDN 175 → 174.
- M21 Basri Ket and Tide Skimmer and FDN Ancestor Dragon gained the flag, so their trees changed.
- All three are re-verified before any run pins this code. r28 is pinned at 44a62d9 and is
  unaffected.
- Ancestor Dragon's pack waits in `known_bugs` until then.

**Cards that play differently with unchanged bytes:**
- The Falconer Adept and Skyknight Vanguard tokens and Basri Ket's Soldiers are no longer
  "declared" (CR 508.4).
- Vito, Kitesail Freebooter, Teferi's Tutelage and Sage's Row Denizen fall under the 603.3d
  removal.
- Replay fingerprints of games with those tokens shift.
- Each author replayed 300 seeded heuristic games of still-verified cards before and after. All
  were identical, with 0 crashes. The 691 verified cards' probe traces are identical too.

**Window 2's castable run, replayed on the fixed engine** (CPU, u1000 against the heuristic,
deals 900,000-900,299): 600 games, 0 voids, 0.6917 [0.659, 0.724]. Before: 4 deals voided.

**`tools/check.sh` at 0a26977:** MTG_bot 5,176 passed / 39 deselected / 71 subtests (B6 was
5,116); `pytest tools` 192; packs 756/756; ruff clean.

## 4. Next: verification wave 1

- **Packets:** blind G2 packets (`reports/verify_wave1_2026-11-12/packets.py`), one per card.
  The answer key stays with the coordinator.
- **The cards** (29):
  - the M21 cards fixed here: Runed Halo, Garruk, Rookie Mistake, Drowsing Tyrannodon, Teferi,
    Transmogrify, Hooded Blightfang, Basri, Devoted Paladin, Feline Sovereign and Mangara;
  - the M21 tooling-limited four (Archfiend's Vessel, See the Truth, Teferi's Ageless Insight,
    Tolarian Kraken), and Unsubstantiate;
  - re-verification: Basri Ket, Tide Skimmer and Ancestor Dragon;
  - M20's 11 mapped cards.
- **Calibration:** two planted decoys per batch, on already-verified cards that appear nowhere
  else in it. A batch that misses either is redone.
- **Verifiers:** another model family than the fixers (PLAN_CARD_ONBOARDING).
- **Then:** `cardtool verify` runs G0-G4 on each card that passes.

## 5. Found, not fixed (in BACKLOG)

- **The heuristic** activates only a planeswalker's first ability row (`heuristic.py` `_act`).
  That weakens the training and evaluation baseline, not the rules.
- **The G1 probe** raises `GameOver` on M21 Sanctum of Calm Waters, identically before and after.
- **Tide Skimmer's "two or more"** is re-checked on resolution as though it were an intervening
  "if" (CR 603.4).
- **Two "one or more" shapes have no encoding:** per attacked object, and gathering the damaged
  creatures. They are needs-atom.
- **11 "reveal … until" cards** and 5 "as though it didn't have defender" cards remain
  unparsed. The new components cover their wording; the templates do not yet.

## 6. Verification wave 1: results (2026-11-12 19:35-20:05)

**Calibration.** Two blind verifiers on another model family (Sonnet) judged 33 packets: batch A
was 18 M21/FDN cards and 2 plants, batch B 11 M20 cards and 2 plants. Each batch caught both of
its planted mutants, so both batches count. The plants were:
- Rousing Read discarding two cards;
- Warded Battlements pumping the opponent's attackers;
- Spectral Sailor's cost missing its {U};
- Ancestral Blade making two tokens.

**Verified: 13 cards** (cardtool G0-G4, with the verifiers' spec packs in the suite):
- M21: Runed Halo, Rookie Mistake, Transmogrify, Drowsing Tyrannodon, Teferi, Timeless Voyager,
  Unsubstantiate, Hooded Blightfang, Basri, Devoted Paladin;
- re-verified: M21 Basri Ket and Tide Skimmer, FDN Ancestor Dragon;
- M20: Anticipate, Tale's End.
- **Verified pools:** M21 262 → 270, M20 254 → 256, FDN 175 (174 between the merge and its
  re-verification).

**Judged WRONG: 8 real cards.**
- **M21 See the Truth:** "the rest on the bottom in any order" is never asked.
- **M21 Feline Sovereign:** its trigger chooses its target without asking.
- Both are being fixed (an engine agent).
- **Correction (2026-11-13, 203 §1):** Feline Sovereign's engine was right. The pack runner's combat op answered the ask unseen, so the probe hid it. See the Truth's order is now asked (MOVE_ZONE `arrange`). Both are verified or blocked as 203 §2 says.
- **Six M20 mapped records** (BACKLOG): Battalion Foot Soldier, Sanitarium Skeleton, Sorin,
  Imperious Bloodlord, Goblin Ringleader, Mu Yanling, Sky Dancer and Cavalier of Flame. Among
  them is an engine-wide issue: reflexive triggers choose their targets too early (CR 603.12).

**Blocked by G3: 8 cards judged OK.**
- The cards: Archfiend's Vessel, Mangara, Tolarian Kraken, Garruk, Savage Herald, Teferi's Ageless
  Insight, Gods Willing, Cavalier of Gales and Blightbeetle.
- Critical mutants survive packs that pin the printed behaviour.
- Gods Willing and Blightbeetle are BACKLOG's documented equivalent mutants: the engine never
  reads the changed role, so no game can tell the mutant from the card. The others likely are
  too.
- The fix is the dead-role rule in `gates.mutants`, not more packs.

**A tool fault found and fixed.** `cardtool verify` named a card's kept packs from index 1, so
re-verifying Basri Ket, Tide Skimmer and Unsubstantiate overwrote their earlier verified packs.
They are restored, and new packs take the next free index (`next_pack_path`, tested).
