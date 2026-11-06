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

## 5. Round one merged: integration/2026-11-05
Branches: fix/selfplay-cleanup, fix/rules-objects, fix/selfplay-slim, fix/menu-mana,
fix/rules-turn-combat. Merge fixes made on the way:
- fix/rules-objects renamed `query.inert_free_row` to `inert_row`; the router still imported the
  old name (a semantic conflict no textual merge shows).
- The engine now ends a game by raising `GameOver` at the loss check. The search applied a
  candidate act outside `_play`, so a candidate that won at once was counted as a crashed
  simulation (Bad Deal at 2 life). Caught there now; test red without it.
- X rows (`cast:<card>[:k][:x<N>]`) reached the network as casts of no card with X 0: the option
  parser now reads the suffix.
- The engine's new `replace` ask (CR 616.1) got its own embedding row; the test that every engine
  ask kind has a row caught it.
- The teacher sanity test (8 of 10 wins vs random) failed a working teacher 9% of the time once
  random play no longer needed TAP_ALL_MANA; now 14 of 20 (p = 0.005).

Measured on the branches (fixers' own runs, same seeds before/after):
- Rules: 0 tapped attacks in 7,639 attacks, 0 first-turn draws, 0 loss-invariant hits in 600
  games (audit baseline: 1,097 / 4,243 / 141 hits in 4,243 games); seat 0 wins 55.5% of
  heuristic mirrors (59.8% before the CR 103.8a fix); 0 crashes in 2,000 games (3 B-69 crashes).
- Menu, heuristic vs heuristic over 300 deals: creature mana tapped in main phases 301 -> 31,
  Prismite loops 703 -> 0, counterspell asks 0 -> 27, X spells cast at X = 0 29/29 -> 1/36 (mean
  X 2.75); teacher vs random 0.907 -> 0.887 (random no longer pays TAP_ALL_MANA first).
- Not a bug, contrary to the exploit audit: Drowsing Tyrannodon may enable itself (no "another"
  in its text; 2020-06-23 ruling). Checking that claim found a real one: the "<name> deals N
  damage" template swallowed activation costs (Elite Headhunter, Chandra Bold Pyromancer).

## 6. Information hygiene and measurement audit (fresh-context agent)
- **The search foresaw the real game's coin flips**: a fork copied the engine seed and the
  engine's randomness is sha256(master_seed:op_seq:tag), so 2,360/2,360 simulated flips equalled
  the real one, and the search activated Tavern Swindler on 9/16 winning flips vs 1/15 losing ones
  (Fisher p = 0.006). Each simulated world now draws its own seed.
- Clean: determinized hands and libraries (673 searches replayed with the opponent's hidden cards
  rewritten: identical choices and scores; a deliberately leaky determinize changed 14/28, so the
  test can see a leak), the encoder (15,126 decisions), the heuristic (15,134), Elo (matches an
  independent Bradley-Terry fit to 0.1), seed disjointness, both seatings per deal, voids
  dropping the pair.
- **Gates were too strict**: Wilson over games treats a deal's two seat-swapped games as
  independent, but they are anti-correlated (-0.40 to -0.87); the deal-level interval is 0.55x
  as wide (r15 median). Corrections to /183: §31's "none significant" is wrong for it95 (0.5396,
  deal-level [0.516, 0.564]); 43 of r15's 159 gates were significant at the deal level, 7 by
  Wilson. And teacher gates drew the ladder's fixed deals, so §32's "unselected" label for r15's
  frozen versions is wrong (v2-v6 froze on gates covering all 150 ladder deals). Gates now use
  per-deal intervals on fresh deal blocks, teacher gates included.

## 7. Round two: red-team of round one, a second fix wave, and its red-team
**Red-team of round one** (read-only agents, 2,000 games before and after each, plus adversarial
scenarios): all 11 rules fixes SOLID; every original failure reproduced on 8c8100e and was gone
on the integration branch; every rules invariant at 0. The player-loss fix exposed one older hole:
simultaneous triggers resolved in fixed seat order, so a mutual-lethal trigger race always went to
seat 0 (now reverse APNAP, CR 603.3b). Interface and learning: payment never missed a payment in
~97,000 brute-force checks; name asks changed 0/200 under hidden-card rewrites (200/200 before);
the void bootstrap leaves no escape; the bf16 acting / fp32 training ratio is unbiased (mean
0.9996). Follow-ups fixed: crashed search worlds are scored neutrally (they were dropped: a move
was scored only on the worlds it survived), the KL early stop acts per minibatch (it ran only
between epochs, so never at --epochs 1), X rows in combat windows, Goblin Arsonist's may.

**Second fix wave** (bugs the M20 mappers found, each checked first against the verified pool):
- Effects: CR 400.7 new objects (43 verified cards kept effects after a bounce and replay),
  last-known controller (Massacre Wurm on a stolen creature), effects outliving their source
  (B-50, CR 611.2a), Frost Breath per controller (B-113), sacrifice choice, condition subject,
  counter prevention, draw replacement.
- Stack: CR 608.2b target recheck (88 verified cards have targets; Heartfire Immolator targeting
  itself damaged itself in the graveyard), permission-cast timing (Idol of Endurance), APNAP,
  modal triggers, no state-based actions mid-resolution (CR 704.3), dies-trigger binding,
  "a spell that targets this", and compiler templates (a free player target in ZNR's Synchronized
  Spellcraft; an orphaned "If you do" drawing a card on cast for 23 partly compiled cards).

**Red-team of the second wave**: stack family six SOLID, two PARTIAL (triggers still pick targets
at resolution; one player's simultaneous triggers are not ordered by the player: both deferred to
docs/BACKLOG.md, weaker or rare); effects family seven SOLID, two PARTIAL and one regression, all
from CR 400.7 being cut at two moments: granted deathtouch/lifelink lost by a source that left
(regression; Heartfire Immolator, Pitchburn Devils, Goblin Arsonist), a dead card keeping its P/T
boosts until end of turn (Carrion Grub read a pumped corpse as 6/5: stronger, steerable), and a
stolen creature's dies trigger going to its owner (older). Being fixed with one departure cut and
one last-known-information snapshot. Measured over 2,000 games each: 0 crashes, mean turns 24.27,
seat 0 50.8%, 99.0% decisive, before and after.

Not reproducible as filed, by the red-teams' account: the round-one claim that Idol of Endurance's
timing bug was live in training (only the active player gets an activation window in the rig);
the Mystic Forge and Cavalier packs needed corrections to show their bugs.

## 8. r18: pre-registration (written before launch, 2026-11-05)
Epoch: 2026-11-05 integration: the corrected rules (tapped attackers, player-loss SBAs, first draw, upkeep order, CR 400.7, CR 608.2b, APNAP), automatic payment instead of TAP_ALL_MANA, X rows, the verified pool (263 M21 cards). Earlier runs played a different game: no number before this epoch is comparable.

Hypothesis: PPO continued from r17's weights on the corrected game and the verified pool first recovers against the heuristic (itself stronger now: no tap-out, X spells, fixed targeting) and then improves in self-play, and the strength it shows is now strength at Magic, not at engine bugs.

Predictions (metric: magnitude; falsifier):
- v0 (r17 last.pt) vs heuristic, opening ladder: 0.45-0.58; falsified by below 0.40 (the network is broken by the new action space) or above 0.62 (the fixes did not change the game it learned).
- teacher eval at update 20: at least v0 + 0.05; falsified by no gain beyond the deal-level interval by update 20.
- training void rate: below 0.05% of games; falsified by above 0.2% (an engine crash source is live).
- network X > 0 share of its X casts by update 20: above 0.5; falsified by X = 0 in most of its X casts (it does not read the X rows).
- self-play gates after the teacher stage: deal-level lower bound > 0.5; falsified by no freeze in 50 self-play updates.

Kill criteria: K1: an engine error whose cause is a rules bug (crash rows in eval or training beyond 0.2%); K4: explained variance below 0 for 3 consecutive updates; K5: no confirmatory metric moves beyond its interval over two review windows past 30% of the budget; K7: throughput below 10 training games/s (r17 ran ~21) with no fix in sight; memory floor trips twice.
Pre-flight (tools/selfplay/preflight.py, main 0dec22f): clean tree; 200 verified-pool games, 0 engine
errors; 200/200 ended by a loss; byte-identical replay. Init runs/selfplay/r17_ppo/last.pt, --refresh-table.

## 9. r18 teacher stage: predicted vs observed
| Prediction (§8) | Observed | Hit |
|---|---|---|
| v0 (r17 last.pt) vs heuristic 0.45-0.58 on the corrected game | 0.6233 (ladder, 300 games); heuristic vs random 0.873 (Elo heuristic 324, v0 406) | **miss**: above the 0.62 falsifier. The skill transferred; the heuristic is relatively weaker in the new game (0.928 vs random before) |
| teacher eval at update 20 >= v0 + 0.05 | it5 0.595 [0.564, 0.626], it10 0.605 [0.571, 0.639], it15 0.590 [0.558, 0.622], it20 0.6238 [0.589, 0.659] (fresh deals each, deal-level intervals) | **miss**: flat, as in r15-r17's teacher stages |
| training void rate < 0.05% | 0 crashes in the pre-flight's 200 games; no crash rows in r18 so far | hit so far |

Training health over updates 1-22: KL 0.006-0.034, explained variance ~0.72, entropy ~0.24, gradient
norm < 0.8, 24-39 games/s (r17: ~21; casts no longer need a TAP_ALL_MANA step). The per-minibatch
KL stop fired on updates 10 and 13 (it could never fire before, at --epochs 1). Stage forced to
self-play at update 22 (gate 0.65 not reached); v1 frozen.

Eyes on glass (tools/selfplay/trace.py, r18 at ~update 12, deal 900011): the starting player keeps
7 cards on turn 1; casts tap exactly the lands they need; the network declines losing blocks (a
2/2 into a 2/3) and attacks with everything when the opponent's only creature is tapped from its
own attack. The heuristic cast Grim Tutor at 2 life and lost at once (CR 704.5a; the old engine
let it play on until after combat): a teacher weakness, not an engine bug.

## 10. M20 verification round: 109 cards verified
Gate G2 by four fresh-context verifiers (none mapped these cards): 150 blind packets, 129 real
and 21 planted with deliberate faults. **Planted faults caught: 21/21** (95% CI 0.85-1.00; the
plan's bar is 0.9). `round.py apply` re-ran every gate per card and stamped 108 records; Drawn from
Dreams followed once the B-81 ruling was applied at clause level: **109 of 129 mapped M20 cards
verified**, 137 spec packs kept in tools/scenarios/cards/M20/ (pytest MTG_bot: 4823 passed).
- Not verified, review WRONG (engine gaps; trees correct): Tale's End (abilities never on the
  stack, B-110), Mu Yanling Sky Dancer (empty emblem), Cavalier of Flame and Battalion Foot Soldier
  ("any number" never asked), Sanitarium Skeleton (graveyard abilities), Anticipate, Cavalier of
  Gales and Goblin Ringleader ("any order" never asked).
- Not verified by G3 (12): a critical mutant the evidence could not tell apart from the card. An
  agent is writing one mutant-killing pack per card.
- Ruling applied alike to all five order cards: B-81 (significant = alters legal options or state
  outcomes): a fixed "random order" is information only (OK); a fixed "any order" removes a choice.

## 11. r18 self-play: freezes without anchor gains; mixed sets blocked on M20's compiled cards
| Version | Frozen at | Gate (deal-level 95%) | Ladder vs heuristic | Elo (random 0) |
|---|---|---|---|---|
| v1 | 22 (forced, end of teacher stage) | - | 0.637 | 400 |
| v2 | 46 | 0.5217 [0.5025, 0.5409] vs v1 | 0.653 | 411 |
| v3 | 66 | 0.5267 [0.5096, 0.5437] vs v2 | 0.647 | 411.5 |
| v4 | 71 | 0.5200 [0.5055, 0.5345] vs v3 | 0.653 | 416 |
(heuristic 307, v0 389; Elo standard error ~25.) Pre-registered "first freeze within 30 self-play
updates": hit (24). With the old Wilson interval the update-45 gate ([0.482, 0.561]) would not have
passed. One gate showed the learner significantly below the just-frozen version (update 50: 0.4767
[0.4596, 0.4938]) and the next was even: update-to-update jitter of the greedy policy, which
freezing on a passed gate then selects at a high point (a remedy: freeze an exponential moving
average of the weights).

Each version beats the previous head to head, but the anchors do not move: v2-v4 sit within one
standard error and at 0.65 against the heuristic, as v1 did. Self-play here improves against
itself, not in general. Rule fixed before the v4 ladder: if v4 is flat too, the next run changes one
thing, mixed-set training on new verified cards (the owner's lever for a plateau, 2026-11-05).

Blocked: M20's verified pool held 119 mapped cards but only 2 lands, and the G5 soak could not build
decks ("only 8 mana-capable cards, need 10"). The first round verified the cards mappers wrote; the
127 cards the compiler translates on its own, basics and dual lands among them, had no verification.
A second round (142 packets, 15 planted) is verifying them; approximating with unverified compiled
cards is not an option (the M21 campaign found 29% of compiled trees wrong). r18 keeps training.

## 12. r19: pre-registration (written before launch, 2026-11-06)
Change vs r18 (one): one: --extend-sets M20 --mix-sets M20 --mix-share 0.25 (25% of training games dealt from the verified M20 pool, 232 cards; G5 soak 300 games: 0 crashes, 0 detector hits, 0 loops, no positive outlier). Everything else as r18.

Hypothesis: r18's self-play improved head to head (v1 -> v4) but not against fixed anchors (Elo 405 -> 416, heuristic 0.65 throughout). New verified cards force play from components rather than card identities, which should lift the anchors (the owner's lever for a plateau, 2026-11-05).

Predictions:
- r18 last.pt on M20 vs heuristic (eval-only, before training): 0.55-0.65 (v6 of r15 scored 0.628 on compiled M20); falsified by below 0.50.
- M21 Elo of r19's frozen versions: one version >= 441 (r18 v4 416 + one standard error) within 60 self-play updates; falsified by none above 441 by self-play update 80.
- M21 ladder score vs heuristic: stays >= 0.62 (mixing does not dilute M21 play); falsified by two consecutive ladder evals below 0.60.

M20 for training: two blind verification rounds (36/36 planted faults caught), 232 verified cards
with 23 lands; G5 soak 300 games, 0 crashes, 0 detector hits, 0 loops; the two value-per-mana outliers
are weak, not strong (Moment of Heroism z -3.6, Colossus Hammer z -3.2).

## 13. r19 launched; prediction 1; the engine gains turn history and "can't be countered"
- r18 ended at update 98 (v4 the last freeze, at 71). Prediction 1 of §12, measured before any M20
  training: r18 last.pt on M20 vs heuristic **0.6033 [0.567, 0.640]** (300 games, 0 voids; coherent
  0.66, stress 0.547): **hit** (0.55-0.65). On M21 the same network scores 0.65: most of its strength
  carries over through the components.
- r19 = r18 last.pt + `--extend-sets M20 --mix-sets M20 --mix-share 0.25`, everything else as r18.
  The table refresh changed 0 M21 rows; the extension added 306 M20 rows, 99.7% of their component
  tokens already trained. Pre-flight: pass.
- Merged before the launch (49f10ca): one turn-history predicate family (EVENT_THIS_TURN,
  SUBJECT_OF_EVENT_THIS_TURN over the turn's journal, read by the trigger binder's own matcher) and
  "can't be countered" as a prevention of a CounteredEvent (the counterspell still targets and
  resolves). 51 sentences newly parse, 25 cards newly fully compiled across the 19 sets; no compiled
  tree changed; 100 seeded M21 games identical before and after. Gates: 5014 / 127 / 709.
- Relaunched (2026-11-06): the first r19 start ran from the main checkout and was stopped at update
  5 (renamed `runs/selfplay/r19_ppo_aborted`, nothing from it used) so main can take engine fixes
  during the run. r19 now runs from a detached worktree pinned at 449bd0f (`../MTG_AI-run`), the
  same commit and arguments as pre-registered; its manifest records git_commit 449bd0f. Rule added
  to TRAINING_REVIEW_PROTOCOL §1. The aborted start's opening ladder: v0 (r18 last.pt) 428 Elo,
  heuristic 326, random 0; v0 vs heuristic 0.648 (300 games).

## 14. Own-cast cost modifiers; tokens and the verified pool (2026-11-06)
- Fixed (e17ae22): a permanent spell read all its own CostModifiers while being cast; a permanent's
  static functions only on the battlefield (CR 113.6), so now only "this spell costs" (IS_SOURCE)
  applies. Warden of Evos Isle was cast for {1}{U} instead of {2}{U}. Not live in training: 100
  seeded heuristic games each on the M21 and M20 verified pools digest identically before and after.
- Token records are never verified (0 of 20 in M21, 0 of 12 in M20) and need not be: games build a
  token from the TokenSpec in the creating card's tree (verbs.py `_v_create_token`), verified with
  that card, under a synthetic id; the records serve only the scenario runner's by-name lane. The
  nine M20 tokens G0 had refused now fail G1 instead (their reviewers read the pre-fix probe trace,
  which still had the KeyError stimulus): correct, and left for a later round.
- **Mistake, 2026-11-06:** a checkpoint prune deleted the four checkpoints the cleanup above had kept
  because NUMBERS.md commands cite them (r15_ppo/v1.pt, r15_ppo/v6.pt, r16_ppo/last.pt,
  r17_ppo/last.pt); no copy survived. The six NUMBERS rows are annotated. All are numbers of the
  pre-integration game, which no current number is compared with. Remedy: a checkpoint a NUMBERS
  command cites is now pinned in reports/LARGE_FILES.sha256, and nothing pinned is pruned.

## 15. r19 so far: v2 frozen, the anchors flat; most deals decide themselves (2026-11-06)
| Version | Frozen at | Gate vs predecessor (deal-level 95%) | Ladder vs heuristic | Elo (random 0) |
|---|---|---|---|---|
| v0 | init (r18 last.pt) | - | 0.648 | 425 |
| v1 | 12 (teacher gate 0.67 [0.636, 0.704]) | - | 0.643 | 423 |
| v2 | 26 | 0.518 [0.5015, 0.535] vs v1 | 0.660 | 428 |
- The teacher gate passes on the point estimate (>= 0.65, lower bound > 0.5; learner.py:901); v1's
  true level was ~0.645, so its pass ended the stage early; it is not evidence of a gain.
- M20 vs heuristic, the same 150 deals as prediction 1, same code and pool (run from the pinned
  worktree): r19 v2 **0.6233** [0.586, 0.660] vs r18 last 0.6033; paired +0.020 [-0.013, +0.053].
  **124 of 150 deals ended alike for both networks**: the cards decide most deals, so a 150-deal
  comparison only resolves differences of ~0.03 and a +0.02 gain needs several hundred deals.
- By deck mode (same pairs): coherent deals differ between the two networks 24% of the time and
  split 1-1 (deck-decided) 65%; stress deals differ 11% and split 85%. Stress decks are five-colour
  piles with ~13.4 lands of 60 (games.py build_deck), so mana decides them: a coherent deal holds
  about twice the skill signal, and half of training (`--coherent-share 0.5`) and of every gate and
  ladder is stress. Candidate for r20, after r19's falsifier at self-play update 80.

## 16. FDN verified; a game review finds dead lands, and that effect polarity is memorised (2026-11-06)
- **FDN round 1:** 135 blind packets (122 real, 13 planted), four fresh verifiers: planted faults
  caught 13/13. 110 cards stamped; the FDN verified pool is 165 cards with 36 lands. Six real WRONG:
  two records to remap (Pilfer, Blanchwood Armor), three Raid cards dead without a postcombat main
  phase (B-74), and Sphinx of the Final Word, which found the next bug.
- **Hexproof worked on the stack** (since 2026-10-07): an opponent could not target a hexproof
  creature spell, so Sporeweb Weaver could not be countered by a blue Cancel. CR 702.11b defines
  hexproof on a permanent. Fixed (d0200d2); 1 of 100 seeded M21 heuristic games changes.
- **Game review** (fresh agent, r19 v1, 24 games vs the heuristic, 20 won; 6 masked replays):
  - Engine: a dealt card an effect puts onto the battlefield had no abilities, so **fetched and
    ramped lands made no mana** (6 dead lands in 4 of 24 games; fixed 4b646f3, 8 of 100 M21 games
    change). Sporeweb Weaver triggers once per damage source (stronger than printed); Volcanic
    Salvo's reduction is not seen by the affordability check (never offered); two-target spells are
    never offered (the multi-slot scaffold: Primal Might, Hunter's Edge, Rabid Bite are dead); no
    mulligan. An agent is fixing the first two.
  - Play: found 13 of 13 guaranteed lethals; mana creatures tapped for mana it never spends 13 of 20
    times (one cost lethal); 8 beneficial effects put on opposing creatures; 5 of 59 blocks lost the
    blocker for nothing; passed with a castable spell 9 of 34 times.
  - **Names masked:** 89.5% of decisions unchanged (attacks 96%), curve and removal targets intact,
    but 6 of 10 own-side pumps flip to opposing creatures. Whether a targeted effect helps or hurts
    is mostly read from the card's NAME, not its components: a generalisation gap for the King
    goal's second tier. Training masks names only 10% of the time (`name_dropout` 0.1).
  - The heuristic anchor misdirects too (Pacifism on its own creature, buffs on the network's).

## 17. The next game: postcombat main phase, own-cost discounts, damage batching (2026-11-06)
Merged for r20's epoch (r19 still runs on 449bd0f):
- **"This spell costs less" never applied in real games** (de9fbd6): the cost fold read a card's
  record through its handle, and a dealt card in hand has none, so Volcanic Salvo, Chandra's
  Incinerator, Discontinuity, Sanguine Indulgence, Stormwing Entity, Winged Words and Ghalta paid
  full price (11 of 100 seeded M21 heuristic games change). The same root as the dead fetched lands
  (§16): packs bind every placed card, games do not, so packs could not see either.
- **"Is dealt damage" triggered once per source** (34f7250): now once per combat damage step, with
  the step's total (Sporeweb Weaver, Brash Taunter; 2 of 100 M21 games change).
- **Postcombat main phase** (merge 46c7288, B-74 fixed): sorcery-speed casting, land plays (one per
  turn in total), sorcery-speed and loyalty activations in both main phases; the drivers open an act
  window in each; the network sees the second main as its own ask kind (`act_second_main`, its
  embedding starts as a copy of `act`, so old checkpoints play it as the first); the heuristic casts
  a Raid spell after attacking and everything else before combat. Cost: 61.9 -> 67.6 decisions per
  game, games per second -14%. Preflight 200 games and M21/M20 soaks: 0 engine errors.
- Gates on 46c7288: pytest MTG_bot 5150; pytest tools 131; packs 718/718. A red team is reviewing
  every fix since 449bd0f before r20.
- **Component wave 2** (merge 7a598df): the defending player as a referent (CR 506.2, 508.5), "can't
  be blocked by more than one creature" (509.1b; with menace, unblockable), and the created token as
  a referent ("create a token, then attach this Equipment to it"; 701.3b). Chosen by measured gain
  from seven candidates; 35 sentences newly parse, fully compiled cards across the 19 sets 1,674 ->
  1,690 (M20 +4: Ancestral Blade, Bristling Boar, Heart-Piercer Bow, Wolfrider's Saddle); no
  compiled tree changed; replay digests identical. Gates on 7a598df: 5202 / 131 / 729.

## 18. r19 result: the anchors did not move; mixing in M20 did not dilute M21 (2026-11-06)
| Version | Frozen at | Gate vs predecessor (deal-level 95%) | Ladder vs heuristic | Elo (random 0) |
|---|---|---|---|---|
| v0 | init (r18 last.pt) | - | 0.648 | 424.5 |
| v1 | 12 (teacher gate) | - | 0.643 | 421.7 |
| v2 | 26 | 0.518 [0.5015, 0.535] | 0.660 | 426.3 |
| v3 | 92 | 0.521 [0.5007, 0.541] | 0.665 | 438.3 |
Heuristic 319.1 on this ladder. Stopped at update 93, the pre-registered decision point (self-play
update 80); 13 gates in a row near 0.50 between v2 and v3.
- Prediction 1 (r18 last on M20 vs heuristic 0.55-0.65): **hit**, 0.603.
- Prediction 2 (a version >= 441 Elo by self-play update 80): **falsified**, narrowly: v3 438.3,
  +13.8 over v0, inside one ladder standard error.
- Prediction 3 (M21 vs heuristic stays >= 0.62): **held**, 0.643-0.665 throughout.
- M20 vs heuristic, paired on prediction 1's deals: v2 +0.020 [-0.013, +0.053], not significant.
Reading: 25% M20 games neither helped nor hurt M21 play within 80 self-play updates. The run
played the old game (no postcombat main, dead fetched lands, no "this spell costs" discounts,
hexproof on the stack), so r20 re-baselines on the corrected one.
