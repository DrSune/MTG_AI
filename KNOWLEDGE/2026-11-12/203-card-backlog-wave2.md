# 203 — The card backlog, wave 2: engine faults from verification wave 1, gate rounds 5 and 6, verification wave 1b

**Context.** The owner (2026-11-12): "Fix the backlog of cards please."
- Verification wave 1 (201 §6) judged 8 cards WRONG and blocked 8 more at G3.
- This note covers what followed, 2026-11-12 20:30 to 2026-11-13 00:40.
  - Fixer agents ran in worktrees, one fault family each.
  - IR changes went through an adversarial gate round (`docs/DESIGN_ATOM_ONTOLOGY.md` §9).
  - Each merge ran `tools/check.sh` on the merged tree.
  - The re-verification was blind, with planted decoys.

## 1. What was wrong, and the fix

| Fault | Cause | Fix | Gate |
|---|---|---|---|
| Feline Sovereign "chose its target without asking" (201 §6) | The engine did ask (CR 603.3d). The pack runner's combat op answered every combat-time ask itself, so the probe never showed it | The combat op hands the asks it does not own to the caller's answerer | none (4ddefed1) |
| Brash Taunter's "target opponent" (verified) | A damage trigger's printed TARGET slot let the damage source stand in for the designation. With three players it hit the wrong one, unasked | A printed TARGET slot is always designated | none (4ddefed1) |
| "In any order" never asked; scry's groups in a fixed order; "random order" fixed | "Any order" and "random order" compiled to the same tree. The executor placed groups in handle order | MOVE_ZONE `arrange`: absent, the owner arranges (CR 401.4); RANDOM is shuffled on its own stream; asked top-first, identical cards merged, owners in APNAP order; the network sees the end (G_TOP) | round 5, FIX-THEN-GO (848cc02b) |
| Reflexive triggers chose their targets too early (Sorin, Imperious Bloodlord; Tolarian Kraken; Cavalier of Night) | No reflexive form in the IR: "When you do, Y" sat inside the payment's optional effect, and every designation walker descended into nested abilities | A DelayedTrigger with no duration and no event, as the then-branch of Conditional(MAY_DONE). It triggers at the gate and designates when it goes on the stack (CR 603.12). Designation reads an ability's own nodes | round 6, FIX-THEN-GO (4d0061cd) |
| Event qualifiers re-checked like intervening "if"s (Tide Skimmer, Makeshift Battalion, Mazemind Tome, Nine Lives, Sanctum of All, Brineborn Cutthroat) | Templates wrote them into `condition` | They are conjuncts of the event filter; `condition` is only an intervening "if" (CR 603.4); a conformance check both ways | round 6 |
| Sorin, Vampire Lord's −8 (verified) granted to one targeted creature | The same walker descent | Grants to each Vampire, no target | round 6 |
| Mangara's departed attacker | Its "if two or more" is a true intervening "if"; a departed attacker counted by its live record | Counted by its last attack (`LastKnown.attacking`) | round 6 |
| A stolen permanent kept its old controller in its own records (Blightbeetle and a class of 53 verified cards once stolen) | `_recompute_control` refreshed no record | Statics, replacements, layer records and "as long as" entries follow the controller (CR 613.7, 611.2c) | none (e9528e31) |
| "Shuffle it into its owner's library" shuffled the controller's (Cavalier of Gales) | `_v_shuffle` passed the controller as the owner | The owner of each moved card (CR 108.3, 701.24c) | none |
| Sanitarium Skeleton's graveyard ability worked on the battlefield | Activation zones were hardcoded | Read off the tree (CR 113.6m, 602.2) | none |
| `cardtool verify` duplicated packs on a re-verification | It always wrote new numbered copies | It reuses a pack with the same text and lists the dropped ones | none (f2d4c107) |

**Gate round 5** (MOVE_ZONE `arrange`) found four MAJOR problems, all fixed before the merge:
- **Validator:** it accepted `arrange` where it orders nothing. It is now one predicate, `orders_a_library`.
- **G3:** it lost the "library → graveyard" mutant on random moves.
- **The suite:** one pack went red, because Brightwood Tracker left the pool. Tale's End's pack was rewritten on Soulmender.
- **The network:** it could not see which end it arranges. A G_TOP column now shows it.

**Gate round 6** (reflexive triggers, qualifiers) found three MAJOR problems:
- **Validator:** it accepted reflexive forms that mean nothing. Under "each player" one handed the life gain to the opponent. 15 refusal cases now cover the misplaced forms.
- **Checks:** the timing check ran one way only.
- **Encoding:** a qualifier that reads no subject had two possible slots. There is now one slot per event class, with a check.

**One semantic merge conflict.** Wave 2B's stolen-Cavalier pack predated `arrange`. Its scry's order went unanswered, so it read as the thief's library changing. The pack now answers the order.

## 2. Verification wave 1b

**Calibration.** Two blind verifiers (Sonnet) judged 28 packets. Batch A was 14 M21/FDN cards and batch B 10 M20 cards, each with 2 plants. Each batch caught both of its plants:
- Peer into the Abyss losing the whole life total;
- Tormod's Crypt unable to sacrifice itself;
- Leafkin Druid's mana going to the opponent;
- Natural End's life going to the opponent.

**Verified: 21 cards**, by G0-G4 with the verifiers' spec packs. Earlier packs that still pass stay listed in the records.
- **M20:** Drawn from Dreams, Brightwood Tracker, Anticipate, Cavalier of Gales, Cavalier of Night, Brineborn Cutthroat, Sanitarium Skeleton, Blightbeetle and Sorin, Vampire Lord.
- **M21:** Feline Sovereign, Garruk's Harbinger, Tide Skimmer, Makeshift Battalion, Nine Lives, Mazemind Tome, Sanctum of All and Garruk, Savage Herald.
- **FDN:** Brineborn Cutthroat, Searslicer Goblin, Mazemind Tome and Battlesong Berserker.
- **Also verified tonight, before the wave:** Tale's End (re-verified on Soulmender) and Gods Willing (G3's dead-role rules).

**Verified pools (deckable), 2026-11-13 00:35:**

| Pool | Before tonight's merges (evening) | Low point, after wave 2A's merge | Now |
|---|---|---|---|
| M21 | 270 | 264 | 272 |
| M20 | 257 | 253 | 260 |
| FDN | 175 | 173 | 177 |

**Still blocked:**

| Card | Why | Next |
|---|---|---|
| Sorin, Imperious Bloodlord; Tolarian Kraken | Twin-target G3 mutants that a separating pack does not kill: probably equivalent on activated abilities and in a reflexive Choose | G3 rule question, with an agent |
| See the Truth | Its "cast from anywhere other than your hand" branch compiles as a sequential one-card move, not "instead, all three". Unreachable today | A compiler fix, and a runner op that casts from other zones (BACKLOG) |
| Mangara; Archfiend's Vessel; Teferi's Ageless Insight | Survivors observable only by responding while a combat trigger waits, by casting from the graveyard, or with three players | Runner ops, with an agent |
| Battalion Foot Soldier, Cavalier of Flame, Goblin Ringleader, Mu Yanling | Wave 2C: "any number" choices, the emblem's abilities, a one-of mapping | With an agent |

## 3. Lessons

- **A green verifier is still not proof of rightness.** See the Truth's verdict was OK with one clause unjudged. Reading the tree found the branch wrong.
- **Merges can conflict in meaning, not only in text.** Two correct fixes (arrange, and the owner's library) turned a pack red together. The full check on the merged tree caught it.
- **Packs need verified supporting cards.** The suite plays verified cards only. Tale's End's first packs used Sorin and Battalion Foot Soldier.

## 4. After the wave (2026-11-13 00:40-01:15)

- **Sorin, Imperious Bloodlord is verified** (mutation score 0.81, 6 packs).
  - Its first +1's twin-target mutants are equivalent. The proof found one engine fault first:
    `activate()` accepted a targeted ability with no targets. It paid the cost, then failed at
    resolution (CR 602.2b, 601.2c).
  - `legality.activation_target_reason` now refuses an empty designation before anything is paid.
    An "up to" slot may stay empty.
  - G3's twin rule covers activated abilities (6ac1354e). No verified card's mutant set changes.
  - Celestial Enforcer's spec pack had pinned the old crash. It now expects the refusal, with the
    mana unspent.
- **Tolarian Kraken is verified** (0.83, 5 packs).
  - Its twin mutants are observable. With no legal target the printed card's reflexive trigger is
    removed (CR 603.3d), and a mutant's goes on the stack.
  - A pack by another agent, reviewed and adopted by the blind verifier, shows it: the opponent
    finds nothing on the stack to counter.
- **Verified pools:** M21 273 (of 280 castable), M20 261, FDN 177.
