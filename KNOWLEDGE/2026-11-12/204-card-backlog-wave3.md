# 204 — The card backlog, wave 3: emblems and "any number" (gate round 7), an ungated engine track, verification wave 1c

**Context.** It continues 203 (2026-11-13 01:10-03:50).
- A read-only census of M20's 55 castable-unverified cards set the order: the BACKLOG entry
  "Card backlog wave 3: the plan".
- Each fix ran in a worktree. IR changes went through an adversarial gate round, and `tools/check.sh`
  ran on each merged tree.
- Verification was blind, with two plants per batch.

## 1. What was fixed

**Gate round 7: wave 2C** (merged 8f7b3774). The fixes:
- **"Any number" is asked**, pick by pick with a stop (CR 107.1c). Before, it took everything.
  - Covers Battalion Foot Soldier, Cavalier of Flame, and the verified Necromentia and Siege
    Striker.
- **"All X revealed this way"** reads the look window (Goblin Ringleader).
- **A put from hand that is not a discard** is asked as `choose:` (Cavalier of Gales).
- **Emblems carry their own abilities:** `GET_EMBLEM` takes an `emblem` EmblemSpec and a
  `controller` recipient.
  - `CardRecord.emblem`, `EmblemAbility` and the attach-by-name are gone.
  - Each GET_EMBLEM makes a new emblem: a second copy used to do nothing. That follows CR 114 and
    the ruling for Chandra, Awakened Inferno.

The gate's four MAJOR findings, all fixed:
- An EachPlayer around GET_EMBLEM was a second encoding. It is now refused.
- The recipient vocabulary was open. It is now YOU, ALL_OPPONENTS or TARGET_OPPONENT.
- An emblem's replacement ability crashed and never applied. It now works (CR 114.4), for
  DOM Jaya Ballard.
- The round's own recipient rule was false for the corpus. It is restated, with the divergence
  registered as D21 and the fold scheduled.
- **Also:** Siege Striker's phantom "may" is dropped.

**The ungated engine track** (merged c4370250), with no IR change:
- Player hexproof now vetoes targets: Leyline of Sanctity, Veil of Summer.
- An instruction whose actor is an absent antecedent does not happen, and an empty "up to"
  designation is bound (Cavalier of Dawn).
- A triggered ability with several target slots designates each slot (Drakuseth). M21 Sublime
  Epiphany drew for the wrong player before.
- "Reveal until" writes the window "the rest" reads (Vivien, Nature's Avenger; FDN Spinner of Souls).
- Two encoding rulings were proposed:
  - Chandra, Flame's Fury's "its controller" form is canonical, once the last-known controller is
    read (CR 608.2h).
  - Discards get a DiscardEvent (B-48).

**Gate round 8: the life family** (`LIFE_TOTAL_GE`, life-event ordinals, the replaced gain's
amount). FIX-THEN-GO: its `who` slot closes to YOU, and the fixes are being applied. One engine
fault was found on the way and confirmed on main:
- Lifelink damage to several recipients at once makes one gain event per recipient. The rules
  make it one event per source (CR 702.15e).
- In 1,500 seeded games on the verified pools it changed 2 games.
- It is being fixed next. Until then, no card that inherits it is stamped verified.

## 2. Verification wave 1c

**Calibration.** Two blind verifiers (Sonnet) judged 20 packets: batch A was 7 M21/FDN cards
and batch B 9 M20 cards, each with 2 plants. Each batch caught both of its plants:
- Runed Halo's protection given to the opponent;
- Cultivate shuffling the opponent's library;
- Wolfrider's Saddle's equip cost missing;
- Chandra's Embercat's mana going to the opponent.

**Verified: 14 cards**, after the verifiers wrote mutant-killing packs on request:
- **M21:** Basri Ket, Liliana, Waker of the Dead and Siege Striker.
- **M20:** Goblin Ringleader, Battalion Foot Soldier, Cavalier of Flame, Octoprophet, Drakuseth,
  Veil of Summer, Cavalier of Dawn and Vivien, Nature's Avenger.
- **FDN:** Vivien Reid, Drakuseth and Spinner of Souls.

**Still blocked:**
- Garruk, Unleashed and Mu Yanling: twin-target G3 survivors on "up to one" targets in an
  activated ability. They survived even a pack that chooses no target. That is a G3 rule
  question, with an agent.
- Mangara and See the Truth, as in 203.

**Verified pools (deckable), 2026-11-13 03:47:**

| Pool | Before 203 (2026-11-12 evening) | Now |
|---|---|---|
| M21 | 270 | 274 (of 280 castable) |
| M20 | 257 | 269 |
| FDN | 175 | 180 |

## 3. Lessons

- **A gate catches what a fixer's green suite cannot:** second encodings the validator accepts,
  silent no-ops (an emblem given to nobody), and laws the corpus contradicts. Rounds 4-8 each
  found MAJOR items in green branches.
- **A verified card can still be WRONG under a new engine fact.** Cavalier of Gales, Necromentia
  and Siege Striker play differently with unchanged trees. Re-reviewing the cards a merge touches
  keeps the stamps honest.
