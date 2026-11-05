# 184: Bug hunt on the merged engine, the unverified cards training dealt, and the first cleanup (2026-11-05)

Owner, 2026-11-05: "Do another pass looking for bugs we are training on, this is the worst thing in
the world to deal with when doing RL, since it exploits every single one easily, and its hard to
identify." And: "keep code quality high ... I dont want this project to be cluttered and bloated,
or slop-infected ... doing a 'cleanup' once in a while ... is a good practice for a long-horizon
project." Previous note: /183 (§37 starts this era: cards/integration merged, r17).

## 1. Method
Three fresh-context agents, read-only, each with its own lens, on main 8c8100e:
- **Rule invariants over whole games** (4,243 rig games, heuristic and uniform seats, coherent and
  stress decks; state checked after every top-level operation and at every SBA point).
- **The engine-to-network interface** (~3,300 games plus replays of r17 checkpoints; hidden-information
  metamorphic test over 77,594 asks).
- **Exploits mined from the network's own play** (r16 `last.pt` on the current engine, 1,700 games;
  per-card presence lift, repeated activations, outliers read as traces).

The M20 card mappers (/173 pipeline, round M20) were a fourth source: building G1 traces and spec
packs for new cards exercises engine paths the M21 pool never reached. Their evidence is in
`tools/scenarios/known_bugs/2026-11-05/` (README says how to run each).

r17 was stopped at update 27 (it was training on the bugs below; its numbers are void for strength).

## 2. Findings (rates per the auditor's own games)
| Bug | Rule | Rate | Policy can steer into it | Fix branch |
|---|---|---|---|---|
| Tapped creatures can attack (a design choice of /2026-09-30/13 §3) | CR 508.1a | 5.5% of attacks, 259/1,000 games | trivially: every {T} ability is free before combat; tap effects never stop an attack | fix/rules-turn-combat |
| No player-loss SBA: a player at <= 0 life still gets combat; lifelink wins from -1 | CR 704.5a, 704.3 | 41/1,000 games | yes: pay life you don't have before a lethal lifelink attack; mutual lethal turns -1 into 0 | fix/rules-turn-combat |
| Decking one draw early; draws from an empty library noticed only at the next draw step | CR 704.5b | 1.6/1,000 | mill wins a turn early | fix/rules-turn-combat |
| The starting player draws on turn 1 | CR 103.8a | every game; seat 0 wins 59.8% vs 55.3% without the draw (400 deals) | no, but it biases every game | fix/rules-turn-combat |
| Summoning sickness skipped after a control change | CR 302.6 | 2/1,700 | weakly | fix/rules-turn-combat |
| An attacker that left the battlefield stays in combat (KeyError, void) | CR 506.4 | 2/1,700 | via the void escape below | fix/rules-turn-combat |
| A crash voids the game and voided games were dropped from training: an escape from a lost position | RL | r17 voided 68 of 31,193 training games; the network cast a second Fiery Emancipation at 1 life into the B-69 crash (eval deal 900137) | yes, observed | voids now bootstrap (fix/selfplay-cleanup 638a5d0); crash sources on fix/rules-objects and fix/menu-mana |
| Two damage replacements on one event raise (B-69) | CR 616.1 | 1.2/1,000 | see above | fix/rules-objects |
| Demonic Embrace's graveyard cast is a costed no-op on the battlefield; the network chose it at p 0.94-0.99 and paid 237 life in 79 activations over 18 games | CR 601.2 | 8/1,000 uniform games | yes (a free discard outlet; it hurts the network) | fix/rules-objects |
| Drowsing Tyrannodon counts itself as "another creature" | template convention | 11 illegal attacks in 300 targeted deals | yes, rare | fix/rules-objects |
| Equipment stays on a permanent that stopped being a creature | CR 704.5n | 0.2/1,000 | weakly | fix/rules-objects |
| Intervening "if" checked only at resolution | CR 603.4 | rare | rare | fix/rules-objects |
| `TAP_ALL_MANA` taps creature mana sources before combat (298 of 300 games), sacrifices every Treasure, re-offers Prismite's filter (752 x 2-for-1); every cast taps out (0 counterspell asks in 600 heuristic games vs 141 for random) | interface scaffold | as stated | no; it caps play quality | fix/menu-mana |
| X spells only at X = 0 (Volcanic Geyser deals 0, Wildwood Scourge dies) | interface | every X spell | no | fix/menu-mana |
| A taxed targeted cast (Pursued Whale, Terror of the Peaks) offered though unpayable, then crashes | CR 601.2f-h, 119.4 | 0.3-0.5% of games had it available | yes (void) | fix/menu-mana |
| Name asks list cards from the game's hidden zones; the fallback named a hidden card 14 times in 51 asks | OWNER_PREFERENCES #1 | 51 asks | through the fallback only | fix/menu-mana |
| Counter features always zero since the merge (engine keys PLUS_1_PLUS_1, encoder read "+1/+1") | interface | 3,955/3,955 asks | no; the network was blind to counters | fix/selfplay-cleanup 638a5d0 |
| legend, enchant and x asks encoded as "other"; attackers at a planeswalker missing from the declared set (26 of 977) | interface | as stated | no | fix/selfplay-cleanup 638a5d0 |

Clean: the encoder reads no hidden card (0 diffs in 77,594 rewritten asks); no stall or turn-cap
escape (both score -1 for both seats); ask routing to seats (62,885 asks); combat damage
assignment, trample, deathtouch, lifelink, menace, protection, hand size and damage at cleanup,
mana emptying at every step, one land per turn, loyalty once per turn, no trigger loops.

What the network had learned to exploit before the merge (already closed by it): free activated
"permission" abilities used up to 9 times a turn (Azusa's +2 land plays per free activation;
Chandra, Heart of Fire casting for free and adding six red mana). The habit of repeating cheap
activations survives (Short Sword equipped 8 times in a turn), which is how it walks into
Demonic Embrace.

## 3. Training dealt 18 cards that never passed verification
The M21 campaign (/177) verified 263 of the 281 castable M21 cards (card records with
`verified.tree_sha`). The learner deals the `castable` pool, so the other 18 were in every
training game: Archfiend's Vessel, Basri Devoted Paladin, Conspicuous Snoop, **Demonic Embrace**,
**Drowsing Tyrannodon**, Feline Sovereign, Furious Rise, Garruk Savage Herald, Hooded Blightfang,
Mangara, Radha, Rookie Mistake, Runed Halo, See the Truth, Teferi's Ageless Insight, Teferi
Timeless Voyager, Tolarian Kraken, Transmogrify. Two of the bugs above live on these cards, and
three more (Runed Halo's name ask, Rookie Mistake's and Transmogrify's two-target spells) are on
the list too. The verification gate existed and training bypassed it. From now on training and
evaluation deal the `verified` pool (fix/selfplay-slim), and a new card enters play only through
verification (docs/PLAN_CARD_ONBOARDING.md).

## 4. Cleanup (OWNER_PREFERENCES #2, reaffirmed today)
- Pack runner: a pack fails when its expect block holds a lane the runner never reads (all 1,161
  packs pass under the check; a mistyped lane used to pass silently).
- Removed eight one-off measurement scripts from tools/selfplay (pointer in NUMBERS.md);
  tools/selfplay 5,458 -> 4,759 lines (the commit message of dbef80f says 4,610; that was wrong).
- Learner slimming in progress on fix/selfplay-slim: expert-iteration targets, the separate value
  network, the KL anchor and the card allow-list go; a run manifest comes in.
- Branches: the two unmerged local-agent branches (rl/rl-v2-offline-core, era/dryrun-2026-11-03)
  were pushed to origin so nothing is lost. With the owner's go-ahead, the 21 local and 17 remote
  branches whose tips are ancestors of main were deleted (`git merge-base --is-ancestor` checked
  each; names and SHAs were recorded before deletion).
- Checkpoints (owner's go-ahead): runs/selfplay 6.7 GB -> 439 MB. Kept every metrics, eval-row
  and log file, and the four checkpoints still referenced: r15_ppo/v1.pt (the deployed search
  model, /183 §25), r15_ppo/v6.pt (generalisation, §35), r16_ppo/last.pt and r17_ppo/last.pt.
- Pack runner, second check: a decision word written by the pack that its ask does not offer
  fails the pack (it used to fall back to the first word silently). 14 of 1,162 packs fail: queues
  shifted by asks the merge added (B-78's zone choice, may-asks), keys that never resolve, a
  negative assertion that rode on the fallback, and Necromentia naming a card the leaky name
  vocabulary did not list. "first-legal" (5 packs, undocumented) is now an explicit word.
