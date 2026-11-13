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

## 4. After the wave (2026-11-13 03:50-04:15)

**Gate round 8 (the life family) is merged** (84c33953). Its fixes:
- LIFE_TOTAL_GE's `who` is YOU only. The target forms never designated a target.
- PREVENT_EFFECT refuses an event with an ordinal.
- New divergence rows: D22, "as long as" on the atom in 5 verified trees, and D23, grant
  order.

**The lifelink fix is in the same merge.**
- One lifelink source's damage dealt at once is one life-gain event, whatever the number of
  recipients (CR 702.15e). It was one per recipient, in combat and with a life-gain replacement
  out of combat.
- In 1,500 seeded games, 3 played differently, with the same winners.

**G3: "up to one" twin targets on an activated ability are dead** (7ba36f23).
- An empty designation is bound and handed to the ALL mutant as itself, so it acts on nothing.
- No verified card's mutant set changes.
- Garruk, Unleashed and Mu Yanling, Sky Dancer are verified.

**Verification wave 1d.** One blind verifier (Sonnet) judged two batches of 3 cards and 2 plants
each, and caught all 4 plants:
- Epicure of Blood's loss went to its own controller;
- Thicket Crasher's trample went to the opponent's Elementals;
- Spectral Sailor's cost was missing its {U};
- Ajani's Pridemate got two counters.

Verified: M20 and FDN Angel of Vitality and Twinblade Paladin, M20 Vengeful Warchief, and FDN
Drogskol Reaver.

**Verified pools (deckable), 2026-11-13 04:15:** M21 275, M20 273, FDN 183. When the owner asked
(2026-11-12 evening) they were M21 270, M20 257, FDN 175.

## 5. Gate rounds 9 and 10, verification wave 1e (2026-11-13 04:15-08:25)

**Gate round 9: a quality chosen as a permanent enters.** Verdict GO, merged c164cd34.
- **The IR:** CHOOSE_NAME takes an optional closed `quality` (COLOR, CREATURE_TYPE).
  NAME_CHOSEN reads it back, refused on any object but its own (CR 607.2d).
- **The engine:**
  - the choice is made before any gate or entering counter (CR 614.12a);
  - it is kept in last-known information when the source leaves;
  - the creature-type menu is the format pool's, plus the granted types. That menu is a
    scaffold in BACKLOG.
- **The network** sees the chosen value and the menu's values. Both are masked at 0, so old
  checkpoints compute bitwise what they did.
- **Fixed with it:** `simulator.load` now grows an old simulator. Gate B's `--search-sim
  runs/window1/sim.pt` would not have loaded on current main.
- **The rename is deferred** (ledger F12), and `string_value` is NAME_CHOSEN's quality slot for
  good.

**Gate round 10: gathered "one or more" zone-change events.** Verdict FIX-THEN-GO, merged
be9e1981.
- **The change:** `once_per_event` on a ZoneChangeEvent, and one atom boundary is one event. The
  `gathered` register replaces `declare_attackers`.
- **The MAJOR finding, fixed:** a plural read of a gathered leave event crashed when tokens left.
- **Also fixed on the way:** "exile them" moved only the first object.
- **The 20 verified trees' new "each occurrence" G3 mutant:** their stamps stand, and a
  re-verification needs a pack that moves two objects at once.

**DESTROY spares an indestructible permanent** (8db1834f; CR 702.12b). Before, every destroy
effect killed indestructible permanents. It was found while building round 10.

**Verification wave 1e.** Blind (Sonnet); all 4 plants were caught:
- Meteor Golem's and Sleep Paralysis's enters triggers ran under the wrong controller;
- Dauntless Veteran pumped the opponent's creatures;
- Cathar Commando's sacrifice was missing.

Verified: M20 Diamond Knight, Icon of Ancestry, Woodland Champion and Angelic Guardian, and FDN
Diamond Mare. Angelic Guardian's one trigger per declaration is pinned by Tale's End countering
it while two attackers wait.

**Verified pools, 2026-11-13 08:23:** M21 275, M20 277, FDN 184. When the owner asked they were
270, 257 and 175.
