# 215 — The open engine faults, triaged by reachability and direction, and the waves that fix them

**Why.** The owner (2026-11-18): "Fix all the engine faults as well." PLAN_LONG_RUN tier 3 asked
for the triage first: by reachability in the three deal pools and by direction, stronger than
printed first, since that is what a learner can exploit. This note is the plan (a draft for the red
team, nothing in the engine changed): every entry of `docs/BACKLOG.md` "Open engine faults" and the
three gate entries the brief named, each with its reachability proven by script or pack, its
direction, its CR basis, whether its fix is an IR change, its files and effort; then the waves.

**The answer in five lines.**
- Of the section's 77 rows, **7 faults are reachable with today's verified cards and play wrong**:
  - 3 STRONGER: an ability acting on a source that left and came back (F14, with its chosen-quality
    case F14b); an Aura returned with its creature enchanting it (F45d); an Aura staying on a host
    its enchant no longer allows (F44).
  - 2 WEAKER: a cast-time target restriction re-read at resolution (F13); lifelink damage to its
    own controller journalled as no life gain (F27).
  - 2 WRONG with no outcome change today: a state trigger re-triggering while it waits (F23),
    which turns STRONGER once the copy round verifies Sublime Epiphany; an extra trigger made by a
    trigger of its own (F24).

  Five have packs that fail on main (5 folders, 7 packs); F14b, F23 and F24 rest on census rows.
- **4 more reach the network without being rules faults.** Two observation gaps (F18b, F19) and two
  phantom decisions (F43, F45e) belong to the network-readiness plan's items 7-8. One knowledge
  record (F63) is harmless today but a honesty hazard for memory v1, so it must be fixed first.
- **4 entries are closed on main or are no fault** (F01, F15 for play, F49, F64), shown by passing
  tests or packs. So is one stale known-bug folder (the 2026-11-05 Cavalier of Dawn crash, K1).
- **In 600 heuristic games none of the three STRONGER faults fired** (rule of three: under 0.5% of
  games). A 900-game soak found 0 crashes and no detector hit that changes play.
- **The waves**: W0 the instruments (pack-runner traps, the G3 draw idiom, the soak detectors, a
  latent-fault guard test), W1 STRONGER (CR 400.7 sources, Aura legality), W2 WEAKER (target timing,
  per-event life rows), W3 one gate round (state triggers, extra triggers, REVEAL's zone), W-D the
  phantom decisions, W4 the cheap latent riders, W5 multiplayer and Commander. The latent faults no
  card can reach are fixed with the first card that reaches them, enforced by the guard test.

## 1. The problem in numbers

- **The section** gives 77 rows in §4: its bullets, with sub-items split where their reach differs.
  - By subsection: 9 lean-pass and search, 5 combat, 14 casting and targets, 14 triggers and
    journal, 23 effects and zones, 3 mana, 3 multiplayer, 2 rules not modelled, 4 to triage.
  - Beside them: the 3 gate entries the brief named, and one stale known-bug folder.
- **The deal pools** (main 8d85e0a7, `games.get_supply("verified", set)`): M21 280, M20 286, FDN 261
  deckable cards. A training game deals one set (`tools/selfplay/learner.py`, `job["set_code"]`), so
  a fault is reachable only through cards of one set.
- **The verdicts, by row:**

  | Verdict | Rows |
  |---|---|
  | reachable and wrong today | 8 (7 faults; F14b is F14's case) |
  | reaching the network without a rules fault | 4 |
  | a knowledge hazard for memory v1 | 2 (F63 and F51, one fault) |
  | closed on main, or no fault | 4 |
  | multiplayer only | 4 |
  | not the engine (search, bench, heuristic, a payment scaffold) | 5 |
  | no behaviour difference (F28, F42) | 2 |
  | the detector re-measure (F65) | 1 |
  | latent: no verified card holds the shape | 47 |
  | total | 77 |

  Of the latent rows, 2 become reachable with the copy round's cards (F29, F40).
- **Occurrence under heuristic play** (`reports/engine_fault_triage_2026-11-18/occurrence.py`, 600
  games, E3's replay deals, read-only hooks): 21,568 activated and 4,601 triggered resolutions; a
  source changed zones while its ability waited 10 times, back on the battlefield 0 times. F14, F44
  and F45d fired 0 times: under 0.5% of games at 95% (rule of three).
- **Soak** (`soak.sh`, B-73's re-measure; 300 random games per pool, verified mode): 0 crashes;
  detector hits M20 0, M21 12 rows in 9 games, FDN 7 rows in 5 games, every one traced to a detector
  artefact or a record with no reachable effect (§5, W0).

## 2. Method: what the field does, and what fits here

| Method | What it gives | Use here |
|---|---|---|
| **FMEA** (IEC 60812:2018): severity × occurrence × detection | a risk order that is not just severity | Severity = direction (STRONGER > WRONG > WEAKER > latent; 212's grades). Occurrence = reachability (a legal line with verified cards of one pool) and the measured firing rate. Detection = whether today's instruments see it: 212 §3 measured that the exploit scan cannot see rare faults, so a rare STRONGER fault ranks first |
| **Orthogonal Defect Classification** (Chillarege et al., IEEE TSE 1992) | fix the defect class, not the instance | waves grouped by cause (212's A-H): one rule fixed per wave, its sibling latent cases ride along |
| **Differential testing** (McKeeman 1998) | an independent oracle for "nothing else changed" | E-waves' blast radius: 600 seeded replays old against new, the first differing row of each differing game explained |
| **A failing test first** (Beck, TDD 2002) | the fix is proven against the fault, not a reading of it | every fault gets a pack or test that fails on main; packs from printed text and rulings |
| **Rule of three** (Hanley & Lippman-Hand 1983) | an upper bound from zero events | 0 firings in 600 games bounds the rate below 0.5% |
| **Fitness functions** (Ford, Parsons, Kua 2017) | an automated check that keeps a property true as the system grows | the latent-fault guard (W0): "no verified card holds a latent shape" becomes a test that turns red at the stamping commit |
| **Prior art for CR 400.7**: XMage's `MageObjectReference` (an object id plus its zone-change counter) and Forge's last-known-information copies | an ability names the object its source WAS, never the card | our engine already has the counter (`returns.moved_since` on the journal) and the snapshot (`LastKnown`); F14's fix applies them to every "this object" read, not only to PUT_COUNTER (E3) |

**Why this combination fits this project.** One GPU, outcome PPO with γ = λ = 1: a STRONGER fault is
a line the learner is paid for and real Magic forbids, and full-credit returns mean any such line
it finds is reinforced in every decision before it. The rules are not tunable (NORTH_STAR §3,
corollary), so a fix is not A/B'd for strength; what is registered is the evidence that it is right
and that nothing else moved (§8). The planner and the league will make the network seek multi-step
lines and exploit habits (PLAN_LONG_RUN tier 1), which raises the occurrence of exactly these rare
lines; the exploiter is also a fault finder (PLAN_CEILING §9.1), so STRONGER faults must be gone
before exploiters train.

**No flags.** The generic brief asks for flags defaulting to today's behaviour. Engine rule fixes
carry none, as E1-E3 did: a flag would let a run train on a rule known to be wrong, and the old
engine stays reproducible at its pinned commit (`/home/sune/Desktop/MTG_AI-r29` at 60f0913f). A fix
enters training only at a run boundary, named in that segment's confound record.

## 3. How reachability was decided, and what it assumes

- **Tree census** (`census.py`, output `census_pools.txt`): 52 shape detectors over every compiled
  tree of the three deal pools and of the copy round's 11 cards (209 B3), each named by fault id
  ("F14 carriers" and "F14 enablers" are the two halves of F14's reach).
- **Text census** (`text_census.py`): wordings a tree cannot show (two "target" words in one
  sentence, state triggers, damage to "you", "Enchant creature you control").
- **Packs** on real verified cards for every fault judged reachable and wrong
  (`tools/scenarios/known_bugs/2026-11-18/`, README there), each run on main and failing on exactly
  the predicted lines. Two **closed checks** (`reports/engine_fault_triage_2026-11-18/closed_checks/`,
  a check and its control) and two **probes** of today's behaviour (`probes/`: Crypt Lurker's
  phantom discard, Joraga Invocation not reaching a returned creature) pass on main.
- **Assumptions behind every reachability claim**, and what follows if one is wrong:
  - *Pools.* "Verified today" is main 8d85e0a7's records. A card stamped later can make a latent
    fault reachable. B3's 11 cards were checked by hand (F23, F29, F40, F60 change); FDN's
    remaining batches and the M20 rounds were not, which is why W0's guard test exists.
  - *One set per game.* If games ever mix sets, cross-set lines open (M20's Brought Back with M21's
    Equipment): rerun `census.py` over the union.
  - *Play.* Reachable means a legal line exists with verified cards; the packs prove the lines.
    How often play takes them was measured under the heuristic only. A network seeking a line can
    raise the rate by orders of magnitude; §8's read measures it under network play.
  - *The detectors are hand-written.* A shape they do not encode is missed. The text census, the
    packs, blind verification (G2) and the soak are the other nets.

## 4. The triage table

Reach: **R** reachable and wrong now (pool; proof), **L** latent (no verified card holds the shape;
census row), **C** closed on main, **N** not the engine. Effort in agent-minutes: S ≤ 45, M 60-90,
L ≥ 120 (§9). Waves in §5.

| Id | Entry (BACKLOG) | Reach and proof | Direction | CR | IR? | Files | Effort | Wave |
|---|---|---|---|---|---|---|---|---|
| F01 | target-player slot with no legal player resolves | C: `binding.TriggerBinder._designate` removes it; `test_executor_hexproof::test_a_trigger_targeting_an_opponent_with_hexproof_is_removed`, pack `runed_halo_names_brash_taunter` | — | 603.3d | — | — | — | W0 remove |
| F02 | "an opponent controls more" sums opponents | 3+ seats only (M21 Garruk, Unleashed) | WRONG (MP) | 102.3 | no | quantity.py | S | W5 |
| F03 | party counts a multi-class creature twice | L: no party card is dealt (ZNR) | WRONG | 700.8 | no | quantity.py | S | with the card |
| F04 | `templates_b6` emits Verb.DISCARD (no handler) | L: census F04 0 | crash | — | I8's fold (B-48) | compiler | S | with I8 |
| F05 | b5b put-counter template places +1/+1 | L: census F05, every pool placement prints its kind | WRONG | 122.1 | no (template) | templates_b5b | S | W4 |
| F06 | b4 keyword grant KeyError | L: a loud compile refusal | refusal | — | no | templates_b4 | S | W4 |
| F07 | static condition lost in kicker merges | L: the verified "as long as" statics carry a while-duration | STRONGER if live | 611.3 | no | compiler | S | W4 |
| F08 | search scores a draw −1 whatever `--draw-reward` | N: search; equals today's default | — | — | — | search.py | S | search owner |
| F09 | search deals the opponent impossible hands | N: open (`search.py` docstring: "coherent two-colour decks are sampled as five-colour piles") | biased search | — | — | search.py | M | search owner, before any search A/B or P3 |
| F10a | once-per-event on another event kind | L: refused at bind; none printed | refusal | 603.2c | IR with its card | binding.py | — | with the card |
| F10b | one trigger per attacked object (Oath of Kaya, Akiri) | L: none compiles | — | 603.2c | IR | binding.py | — | with the card (MP) |
| F10c | `combat=None` damage gathering | L: needs-atom | — | 603.2c | IR | — | — | with the card |
| F10d | dealer trigger with no recipient fires per row | L: census F10d 0 | STRONGER if live | 603.2c | no | binding.py | S | with the card |
| F11 | a blocker of several attackers | L: no tree | — | 509.1, 510.1d | IR | `__init__` combat | L | with the card (Commander) |
| F12 | bench labels a multi-mode token "choice N" | N: LLM bench | — | — | — | bench/protocol.py | S | bench items |
| **F13** | cast-time target restriction re-read at resolution | **R M21**: pack `enthralling_hold_resolves_after_its_target_untaps` (Tolarian Kraken untaps the Ox; the Hold goes to the graveyard) | **WEAKER** | 601.2c, 608.2b; the card's ruling | no | stack.py (recheck), query.py | S | **W2** |
| **F14** | an ability acts on its source after it left and came back | **R M20, M21**: packs Griffin Protector 3/4 (Brought Back), Colossus Hammer equips a returned Hammer, Bear 12/12 (Brought Back), Watcher of the Spheres 3/3 (Obsessive Stitcher); **FDN** by census (Fake Your Own Death with Ball Lightning: the old trigger sacrifices the new one) | **STRONGER** (M20, M21), WEAKER (FDN) | 400.7, 113.7a, 608.2h; exceptions 400.7d-e | no | selectors, binding, legality, verbs | L | **W1** |
| F14b | a re-entered source answers its chosen quality from the new object | R M20 by census: Icon of Ancestry, destroyed and Brought Back while its look waits, chooses again | STRONGER | 400.7, 608.2h | no | quantity.py, binding.py | M | W1 |
| F14c | LKI lost on exile-and-return within one resolution | L: no flicker in the pools | WRONG | 400.7, 603.10a | no | `__init__` departed_lki | S | W1 rider |
| F15 | B-54 `legal_casts` offers a spell with no legal target | C for play: games use `menu.menu`, which drops what `stack.can_designate` refuses; `query.legal_casts` is read only by tools/cards (probe, respond) | — | 601.2c | — | tools/cards | S | W0 cleanup |
| F16 | two "target" words with the same text share a slot | L: the one pool card with two target words, M21 Rookie Mistake, has distinct selectors (text census, census F16) | WRONG | 601.2c, 115.3 | IR (a slot id) | compiler, query | M | with the card |
| F17 | activate takes targets before X | L: census F17 0 | WRONG | 601.2b-c, 602.2b | no | legality.activate | S | W2 rider |
| F18a | a target reading the player designated beside it raises | L: none printed | crash | 601.2c | no | binding, query | M | with the card |
| F18b | a multi-slot trigger's ask does not name its slot | R: Drakuseth (M20, FDN): the 4-damage and the 3-damage picks look alike | observation gap | AGENTS §10 | no | binding + rig `AskContext` + features | S | readiness plan |
| F18d | a Choose inside a multi-slot trigger raises | L: Drakuseth has none | crash | 700.2a | no | binding | S | with the card |
| F18e | "up to" with none chosen; a population beside it | L: G0's designation lint refuses the shape | — | 601.2c | — | — | — | keep the lint |
| F18f | a skipped producer leaves an older result | L: none of the 12 atoms is skippable | WRONG | 608.2c | no | verbs `_actor_absent` | S | W4 |
| F19 | a player's keywords are not observed | R: Runed Halo (M21), Veil of Summer (M20) | observation gap | 702.11, 702.16 | no | features.py | S | readiness plan |
| F20 | EachPlayer acts player by player; replacements per player | L in two-player games: every ref is one player or the body one instruction (census F20) | WRONG (MP) | 101.4, 614.6 | no | verbs.py | M | W5 |
| F21 | an effect finds what it moved into a hidden zone | L | STRONGER if live | 400.7 | no | binding `_gone` | S | W4 |
| F22 | a reflexive trigger reads its creator's target | L: unparsed (IKO Back for More) | — | 603.12 | IR (a register) | binding | M | with the card |
| **F23** | a state trigger triggers again while it waits | **R M21** (Nine Lives: two damage events at eight counters queue two exile triggers): extra stack objects, no outcome change; **STRONGER once B3 verifies Sublime Epiphany** (counter the exile trigger and Nine Lives stays; its ruling: it triggers again at once) | WRONG → STRONGER | 603.8; Nine Lives' rulings | **IR** (a state trigger) | ability_tree, compiler, binding | M | **W3, before Sublime Epiphany's stamp** |
| **F24** | an extra trigger made by a trigger of its own | **R M21**: Sanctum of All with six Shrines (very rare; package decks) | WRONG | 603.2d, 603.3b | **IR** (a static) | templates_b5b, binding | M | **W3** |
| F25 | a fight's rows name the fight's source | L: no dealer-filtered reader of creature damage in the pools (census F25d) | WRONG | 701.12b | no | events.py, verbs.py | M | W2 rider |
| F26 | CounteredEvent has no reader | L: refused (a capability) | — | 701.5 | IR | binding, events | M | with the card |
| **F27** | the journal nets a player's life per atom | **R FDN**: pack `midnight_reaper_with_lifelink_feeds_ajanis_pridemate`; M21 (Chandra's Magmutt at its controller, Alchemist's Gift, Vito) and M20 (Pyroclastic Elemental, Moment of Heroism, the lifegain watchers) by census | **WEAKER** | 120.3a, 702.15b, 120.3f | no | events.py, verbs.py, `__init__` combat | M | **W2** |
| F28 | two classifiers for CR 113.6m | no behaviour difference | — | 113.6m | no | binding, legality | S | W4 |
| F29 | a token's record keyed by its name | L now (one ability-bearing spec per name and pool, census F29); **R with B3** (FDN token copies with and without Electroduplicate's exceptions share a name) | WRONG | 111.3, 707.9 | no | verbs `_v_create_token` | S | B3 merge condition (B3 builds token copies there) |
| F30 | entering loyalty journalled on the cast lane only | L (212: the watchers read their own or +1/+1 counters; census F30) | WEAKER | 306.5b, 122.6 | no | `__init__._apply_etb_state`, binding | S | W2 rider |
| F31a-c | three moments of "exiled with" | L: readers Bag of Holding (M20), Idol of Endurance (M21); neither reaches the three | WRONG | 607.2a, 603.7 | no | binding, legality | S | W4 |
| F32 | an Equipment unattached by an SBA misses a creature dying in the same check | L (212) | WEAKER | 704.3, 704.5n, 603.10a | no | `__init__._state_checks` | S | W1 rider |
| F33 | CAST_THIS_TURN_FROM off the stack and battlefield | L (212: Archfiend's Vessel only) | WRONG | 400.7, 608.2h | no | quantity.py | S | W1 rider |
| F34 | a referent over a plural register takes the first | L: Necromentia's exile after its search is a no-op move; a PERMIT reads the whole register (`verbs._v_permit`) | WEAKER if live | 608.2c | no | selectors, verbs | M | W4 (card by card) |
| F35 | replacement order never asked | L: one life-gain replacement per pool (Angel of Vitality's copies commute); zone-change ones never share an event | WRONG | 616.1 | no (a new ask kind) | replacements.py | M | W5 / with the card |
| F36 | an ALL over a library top writes the look window on every read | L: four verified readers (Radha, Mystic Forge, Goblin Ringleader, Diviner's Lockbox), none harmful (a static reads the filter only) | hygiene | — | no | selectors.py | S | W4 |
| F37 | "any number" over an unaskable menu takes all | L: every pool case is asked | STRONGER if live | 107.1c | no | selectors | M | with the card |
| F38 | "as this enters" runs only CHOOSE_NAME | L, a tripwire (raises): census F38 | crash | 614.1c | no | `__init__.run_as_enters` | — | with the card |
| F39 | colours are the printed ones | L, a tripwire | WRONG | 105.3, 613.1d | no | quantity | — | with the card |
| F40 | a copy that entered without choosing raises | **R with B3**: a token copy of Runed Halo, Icon of Ancestry, Diamond Knight or Diamond Mare | crash | 707.2; Icon's ruling | — | quantity | S | **B3 merge condition** |
| F41 | picks from another player's library or hand raise | L, a tripwire (census F41's rows move a battlefield card, not a pick) | crash | 401.4 | no | verbs | — | with the card |
| F42 | B-30 `identity_of` stamps M21, drops oracle text | no reader in play | data | — | no | `games.identity_of` | S | W4 |
| F43 | B-64 a may or a Choose offers an impossible action | R M21: Crypt Lurker with an empty hand asks `('0', '1')`, discard included (probe) | phantom decision | 609.3; AGENTS §10 | no | query `optional_offer` | S | W-D |
| **F44** | B-65 an Aura on a host its enchant no longer allows | **R M21**: pack `dub_falls_off_riddleform_when_its_animation_ends`; Setessan Training with Traitorous Greed by census | **STRONGER** (mostly) | 704.5m, 303.4d | no | `__init__._unattached_auras`, aura_entry | S | **W1** |
| F45a | "for as long as" and phasing | L: only reminder text in the pools; "until leaves" with phasing is pinned (`kitesail_freebooter_phased_out_card_stays_exiled`) | — | 611.2b, 702.26 | IR | — | — | with the card |
| F45b-c | Calix; the unparsed list | not compiled | — | 610.3 | IR | — | — | with the card |
| **F45d** | an Aura returned with a creature enchants it | **R M20**: pack `brought_back_aura_cannot_enchant_the_creature_returning_with_it` (a 5/5 Bear) | **STRONGER** | 303.4f-g; Brought Back's ruling | no | verbs `_v_move_zone`, aura_entry | S | **W1** |
| F45e | Kitesail Freebooter's choice asked after it left | R M21 (pinned by `kitesail_freebooter_leaves_before_its_trigger_resolves`) | phantom decision | the card's ruling | no | binding, verbs | S | W-D |
| F46 | MOVE_ZONE's top-n lane reads the destination's library | L: census F46 0 | WRONG | 108.3, 400.3 | no | verbs `_v_move_zone` | S | W4 |
| F47 | a Conditional after a step that made several tokens | L: FDN Faebloom Trick's is MAY_DONE, not a characteristic test | WEAKER if live | 608.2c | no | `__init__._conditional_subject` | — | with the card |
| F48 | CR 111.8 inside one resolution | L: no tree moves one object twice | STRONGER if live | 111.8 | no | verbs `_v_move_zone` | S | W1 rider |
| F49 | "doesn't untap" blocks every untap | C: only the untap step reads it (`Executor._untap_step`); closed check plus its control pass | — | 502.3 | — | — | — | W0 remove |
| F50 | damage marked on a permanent that left | L: Sorin's reflexive target now follows the sacrifice | WRONG | 120.1, 400.7 | no | verbs `_deal_damage_to_card` | S | W1 rider |
| F51 | "reveals their hand" lists the library | = F63 | | | | | | W3 |
| F52 | moves that ask no replacement; a spell to its caster's graveyard | L: no compiled replacement reads a draw, cast, land drop or token; no pool card casts another's card | WRONG | 614, 400.3 | no | verbs, stack | M | W5 / with the card |
| F53 | a "from anywhere" self-replacement works on the battlefield only | L: Darksteel Colossus and Progenitus are not compiled | STRONGER if live | 614.1, 113.6 | no | replacements `_source_alive` | S | B13 merge condition |
| F54 | B-90 no compiled card keeps mana | L: a capability | — | 500.4, 106.4 | no | `__init__.empty_mana_pools` | S | with the card |
| F55 | the payer's "most colours" is greedy | scaffold-internal; 0 of 7,204 real casts | WEAKER (rare) | 601.2g | no | legality `plan_mana_taps` | — | retired with the learned payment (owner) |
| F56 | hybrid costs | L: census F56 0 | WRONG | 107.4e | no | legality | S | with the card (Commander) |
| F57 | B-108 opponent refs raise at 3+ seats | MP only (two seats never denote several) | crash, loud | 101.4 | a chooser ask (design) | selectors | M | W5 |
| F58 | a loser stays in a game of 3+ | MP only | WRONG | 800.4a | no | `__init__` | M | W5 |
| F59 | multiplayer combat: one defending player | MP only | WRONG | 506.2, 508.1b, 508.5a, 802 | an attack ask (design) | `__init__`, selectors | L | W5 |
| F60 | no copy effects; no layer dependencies; approximate timestamps | copies: B3 builds them; dependencies and timestamps L (no dependent pair, only CDAs) | — | 707, 613.8, 613.7a | IR (B3) | layers.py | L | B3 / with the card |
| F61 | second-main-phase triggers, extra main phases, Saga lore | L: census F61 0 | — | 505.1a, 505.4, 714 | IR | `__init__` | M | with the card |
| F62 | the heuristic activates only a planeswalker's first ability | N: `heuristic._act` still takes the first row | weaker baseline | — | — | heuristic.py | S | league plan |
| **F63** | the journal is not a record of what players know (with F51) | L for play (no reader); **a honesty hazard for memory v1**: a hand reveal is recorded as the whole library (`verbs._look`, `count=QUnbounded`) | WRONG (knowledge) | 701.20, 701.22; OWNER_PREFERENCES #1 | **IR** (REVEAL's zone) | verbs, events, ability_tree | M | **W3, before memory v1** |
| F64 | Teferi, Master of Time's −3 duration | C, not a fault: the printed reminder reads "until its controller's next turn", classic phasing, which its pack pins | — | 702.26 | — | — | — | W0 remove |
| F65 | B-73 the detectors flag games | re-measured (§1): no hit changes play; all are detector artefacts but one bookkeeping residue (W0, W1) | — | — | — | tools/audit/detectors.py | M | W0 |
| G1 | G3's draw-idiom rule is coarser than the draw lane | tooling; it holds See the Truth's stamp (M21 281 of 285) | — | — | — | tools/cards/gates.py | S | W0 |
| G2 | a cast with `"tap": true` says "cannot pay" for any refusal | tooling | — | — | — | tools/run_scenarios.py | S | W0 |
| G3 | pack-runner traps (vacuous pass after a loss; drift past a one-candidate ask; a key shadowing a player word; stale notes) | tooling, under every wave's acceptance packs | — | — | — | tools/run_scenarios.py | M | W0 |
| K1 | known_bugs/2026-11-05 `up_to_one_none_chosen_crashes` (Cavalier of Dawn) | C: the card is verified and `mapped/M20/cavalier_of_dawn_no_target_makes_no_golem` passes | — | — | — | — | — | W0 remove |

**Directions, checked against the staged lines.** F14: the pump lands on the new object and the
equip attaches a new Hammer for free (stronger); in FDN the old end-step trigger sacrifices the new
Ball Lightning (weaker); the fix removes both. F44: Dub stays on Riddleform after its animation and
pumps it again whenever it animates (stronger for its controller); a Pacifism-like Aura staying on
a non-creature changes nothing. F45d: a free Aura on the returned creature (stronger). F13: the Hold
fails where the ruling says it resolves (weaker). F27: "whenever you gain life" never sees a gain
that a loss offsets in the same atom (weaker; Vengeful Warchief's "first time each turn" misses the
loss too).

## 5. The waves

Grouped by cause (212's practice), then by file so that no two waves in flight touch one file
(209 §6), and ordered by severity: STRONGER and reachable first, two-player before multiplayer.
Every wave takes CARD_AGENT_BRIEFS §5's form: root cause read first, each fix with a pack or test
that fails on main, the blast-radius protocol (§8), a fresh-eyes reviewer before the report, the
BACKLOG entries closed in the fixing commit and their packs moved to `tools/scenarios/`.

**W0 — the instruments first (tools only; parallel with W1).** Why first: every wave's acceptance
rests on packs and on the soak, and a pack that passes vacuously or a detector that cries wolf hides
a regression (212 §3: "a fixture that is not the real thing").
- G3: the runner fails a pack whose game ended before its last step; a decision word meant for a
  one-candidate target ask fails the pack instead of drifting; a card key equal to a player word is
  refused; the two stale notes refreshed. G2: a refused `"tap"` cast reports the engine's reason
  (`spell_castable`'s), not "cannot pay".
- G1: `gates._draw_idiom` reads the executor's lane (an ALL over a library top is a partition, not
  the draw); See the Truth's survivor dies and the card can be stamped.
- F65, the detectors (`tools/audit/detectors.py`), each traced (`soak_seeds.txt`, `d5_trace.py`,
  `d6_pending_check.py`, `d6_two_replacements_check.py`): D5 folds counters across a card's lives
  (M21 seed 229: a Watcher bounced by Niambi and recast carries no counters, rightly; FDN 123, 262);
  D5 ignores static and end-of-turn P/T layers (Hooded Blightfang 2/5, Thieves' Guild Enforcer 4/3,
  Pack Leader 3/3, Mold Adder 0/0 after Stab are each right); D6(i) counts an end-of-turn delayed
  trigger of a game that ended inside that turn (M21 seeds 9, 193, 235, 281: Subira or Basri,
  activated in the final turn); D6(iii) counts two copies of one replacement (seeds 114, 297: two
  Fiery Emancipations, both legal, CR 616.1). The one real residue, D6(iv)'s end-of-turn
  `mandate_block` record still bound to a dead card (FDN seeds 50, 64: Joraga Invocation), has no
  reachable effect, since every same-turn return in FDN enters tapped (probe: the returned creature
  is a plain tapped 2/2); W1 clears it.
- **The latent-fault guard** (new; `tools/audit/test_fault_reachability.py`): `census.py`'s
  detectors as assertions over the three verified deal pools. Each latent shape's expected set is
  empty; each open reachable fault's set is pinned and shrinks as waves close it. A verification
  wave that stamps a card holding a latent shape turns it red, and that fault's fix becomes the
  wave's merge condition. Fails on main with a synthetic card holding a shape (its own test).
- Stale entries (F01, F15, F49, F64, K1) removed after the red team confirms §4's evidence; the card
  tools read `menu.menu` instead of `query.legal_casts` (F15), which then goes.
- Optional, cheap: E3's replay and compare scripts promoted to `tools/audit/blast_radius.py`, so
  every wave runs one protocol.
- Effort about 300 agent-minutes.

**W1 — STRONGER and reachable (engine only).**
- *Cause A, an ability names the object its source was (CR 400.7, 113.7a, 608.2h).*
  - F14: every non-information read of "this object" (a `referent="source"` selector, or a zone
    selector filtered on IS_SOURCE) skips a source in the `gone` register, as E3 made PUT_COUNTER do
    (`verbs._v_put_counter`); that special case then folds into the general rule in
    `selectors.resolve_selector`.
  - The exceptions the rule must keep, each with a test: an ability triggered by the source's own
    move finds it in a public zone (already `binding.TriggerBinder._source_gone`); an Aura's
    leaves-the-battlefield ability finds the Aura in its owner's graveyard (CR 400.7e: M21 Angelic
    Destiny, verified); an object an earlier part of the effect or its cost moved to a public zone
    is found.
  - F14b: an ability-scoped last-known snapshot of its source, taken as it is activated or
    triggers (XMage's reference pattern), so a chosen quality, and any information read, comes from
    the object the source was.
  - Riders, same cause, same files: F14c, F33, F48, F50, and D6(iv)'s `mandate_block` record ended
    with its object (`LayerRegistry.forget_departed`).
- *Cause B, an Aura's attachment must stay legal (CR 303.4f-g, 704.5m).*
  - F44: `Executor._unattached_auras` also buries an Aura whose host fails its enchant filter,
    `aura_entry._enchant_filter`, read in the Aura's controller's coordinates.
  - F45d: an Aura entering by an effect chooses its host among objects already on the battlefield,
    not those entering in the same move (`verbs._v_move_zone` chooses hosts before moving;
    `aura_entry.aura_entry_hosts` takes the move's set).
  - Rider: F32 (`_state_checks` pops the 704.5n edges after the departures are snapshotted).
- **Acceptance:** the five W1 packs pass; E3's `scavenging_ooze_that_left_the_battlefield_gets_no_counter`
  and the Angelic Destiny packs still pass; a synthetic test for each rider fails on main.
- **Prediction:** at most 3 of the 600 replays change outcome (0 firings in 600 games, rule of
  three); journal-only changes where the riders change bookkeeping, each explained.
- **Files:** selectors.py, binding.py, legality.py, quantity.py, verbs.py, layers.py, aura_entry.py,
  `executor/__init__.py`.
- **Effort** about 450 agent-minutes.

**W2 — WEAKER and reachable (engine only; after W1, which shares its files).**
- *Cause C, a target restriction belongs to its moment (CR 601.2c, 608.2b).*
  - F13: a spell's own "as you cast it" restriction on its targets (a static PREVENT_EFFECT over its
    own TargetingEvent) is read when the targets are chosen, never by `stack.recheck_targets`;
    hexproof, protection and every other "can't be the target" quality stay rechecked.
  - Rider F17: the folded activate announces X before the targets (CR 601.2b).
- *Cause D, the journal records each event, not the net (CR 120.3a, 702.15b, 120.3f).*
  - F27: player damage and lifelink gains are journalled from the verbs' own results (the damage
    tuple, `verbs._lifelink_gain`), not from the life total's net change in `Journal.record_atom`.
  - Riders: F25 (a per-row cause, so each fight blow names its own dealer); F30 (a planeswalker an
    effect puts onto the battlefield journals its loyalty, seeded in `_apply_etb_state`).
- **Acceptance:** the two W2 packs; a test per rider.
- **Prediction:** outcomes change only where a lifelink source damages its own controller beside a
  lifegain watcher (0 expected in the replays); journal rows change in every replay with a fight
  (F25), each explained.
- **Interface:** the network's turn-so-far columns (`features.P_GAINED` ... `P_CAST`, built
  2026-11-18) read these life rows; their code does not change, their values become right in
  those games.
- **Effort** about 400 agent-minutes.

**W3 — one gate round, three lanes (IR changes; CARD_AGENT_BRIEFS §3-§4).**
- **F23**: a state-trigger node (CR 603.8). It is checked whenever a player would receive priority,
  does not trigger again while its instance waits, and triggers again at once if that instance
  leaves the stack while the state holds. M21 Nine Lives and Mazemind Tome (M21, FDN) are re-baked
  and re-verified. **It must merge before B3 verifies Sublime Epiphany.**
- **F24**: "triggers an additional time" as a static (CR 603.2d). The binder counts the copies when
  the ability triggers and queues them with the original (`binding._fan_ability_triggers`); the
  carrier trigger and its option in the order ask go. M21 Sanctum of All (and M20 Yarok, when
  mapped) re-baked.
- **F63 (with F51)**: REVEAL names the zone it reveals (a hand, a library's top), and SCRY rows name
  their cards, read by the scryer only. Duress (M21, M20, FDN), Kitesail Freebooter, Thought
  Distortion and Pilfer are re-baked. **It must merge before memory v1 reads reveals** (PLAN_PLANNING
  §5 P1): with today's rows, "what they revealed" would hold the opponent's whole library.
- **Files:** ability_tree.py, compiler templates, binding.py, verbs.py, events.py.
  - 209 §6 orders binding.py's rounds B6, B8, B17: W3 goes before B6 and after W2.
- **Effort** about 330 agent-minutes, plus about 3 a card to re-verify the 10-12 re-baked stamps.

**W-D — decisions of nothing (with the readiness plan's item 7; after W2, which shares query.py).**
- F43: a may, or a Choose inside it, offers only actions that can be done (CR 609.3; AGENTS §10);
  Crypt Lurker with no creature card in hand asks only "sacrifice".
- F45e: no Kitesail Freebooter choice once its exile cannot happen (its ruling).
- The readiness plan's own (the order ask between identical triggers; Duress and Freebooter listing
  each card twice) are the same lane.
- **Interface:** the network's ask menus shrink there; the planner's "use" labels are read off asks
  and need no change.
- **Effort** about 150 agent-minutes.

**W4 — the cheap latent riders (engine and compiler; after W3).**
- Engine: F18f, F21, F31a-c, F34 (audited card by card, as its entry asks), F36, F42, F46, F28.
- Compiler riders: F05-F07, accepted by a tree diff with 0 verified trees changed.
- Why now and not with a card: each is CR-clear, small and testable with a synthetic card, and
  each is a trap for the next card that holds its shape (212 §3: "a shortcut outlived its reason").
- **Prediction:** 0 of 600 replays differ (latent by census).
- **Effort** about 350 agent-minutes.

**W5 — multiplayer and Commander (after the two-player waves).**
- F02, F20, F57, F58, F59, F52, F35, and F10b, F11 and F56 with their first cards.
- Three of them add decisions the network makes, and each is a design for the network's owner
  before it is built:
  - whom each creature attacks (CR 506.2, 802);
  - who chooses "an opponent";
  - the order of replacements (CR 616.1).
- None runs in a two-player game, so the wave may merge during a run when its 600 two-player replays
  are identical.
- PLAN_LONG_RUN puts Commander after the long run.
- **Effort** over 800 agent-minutes; the combat lane is the bulk.

**With the card that reaches them** (merge conditions on the rounds of 209 §6, enforced by W0's
guard):
- B3 (copy, round 14):
  - F29: a token's binder record keyed by its spec's hash, as an emblem's is. B3 builds token
    copies in `_v_create_token`, so the fix belongs there.
  - F40: a copy that entered without choosing reads "nothing was chosen" (Icon of Ancestry's
    ruling).
  - F60's copy half, which is B3 itself.
  - Sublime Epiphany's stamp waits for W3's F23 lane.
- B13 (round 24, SHUFFLEIN): F53 (a "from anywhere" self-replacement's record lives in every zone).
- The first card holding the shape: F03, F10a, F10c, F10d, F16, F18a, F18d, F22, F26, F37, F38, F39,
  F41, F45a, F47, F54, F60's dependencies, F61.

**Routed to other plans:**
- the readiness plan's single observation-schema change: F18b, F19;
- the search, before any search A/B or P3: F08, F09;
- the league plan: F62;
- the LLM benchmark items: F12;
- the automatic-payment scaffold: F55, retired with the network's own payment (the owner's
  deferral).

## 6. Order, conflicts, and the planner v1 build

| Order | Wave | Files | Waits on | Merges into training |
|---|---|---|---|---|
| 1 | W0 ∥ W1 | tools/ (W0); executor/ (W1) | nothing | W1 at the next run boundary (the FDN segment if ready, else the long run's start) |
| 2 | W2 | executor/ (shares verbs, legality, `__init__` with W1) | W1 merged | the long run's start |
| 3 | W3 (gate round) | ability_tree, compiler, binding, verbs, events | W2 merged; before Sublime Epiphany's stamp and before B6 | the long run's start; its re-baked cards leave the verified pool until re-stamped |
| 3' | W-D | query, binding, verbs | W2 merged; one agent with the readiness plan's item 7 | the long run's start |
| 4 | W4 | executor/, compiler | W3 merged | any boundary (0 replays differ) |
| 5 | W5 | executor/, selectors | the two-player waves | mid-run allowed when the 600 replays are identical |

- **Beside the planner v1 build.** That agent edits tools/selfplay/features.py, model.py, actor.py,
  learner.py and ppo.py; no wave edits them. The interfaces between them:
  - the journal's life rows (W2), which feed the turn-so-far columns;
  - the ask menus (W-D removes phantom options; W5 adds asks), which feed the option tokens and the
    planner's "use" labels;
  - the REVEAL and SCRY rows (W3), which memory v1 will read after the planner;
  - the observation gaps F18b and F19, which go with the readiness plan's one schema change.
- **Beside the card rounds.**
  - W3's binding.py work sits before B6, B8 and B17 (209 §6).
  - B3 (copy) can be built beside W1. Both touch verbs.py, so the second to merge rebases.
  - F29 and F40 are B3's own merge conditions. Sublime Epiphany's stamp alone waits for W3's F23.

**Amended 2026-11-18, after the red team (KNOWLEDGE/2026-11-18/216 §4: GO, four minor notes) and by
the coordinator.**
- **E1. W2 follows W1 because they share files, not because WEAKER ranks lower.** SYSTEM_MAP §3
  ranks a weaker-than-printed fault with the stronger ones. W2's packs are acceptance lines of the
  same bug hunt as W1's.
- **E2. The five stale entries** (F01, F15, F49, F64, K1). The red team grepped F49's one reader
  (`replacements.py:911`) and did not run any closing check. So W0 removes each entry only after
  running its closing check and its control, with the wave's fresh-eyes reviewer confirming.
- **E3. F63 with F51 has one owner: W3, as an IR change in a gate round.** A reveal's zone is a tree
  concept. PLAN_NETWORK_READINESS's J1-J2 point here (PLAN_LONG_RUN, "Who owns what").
- **E4. The network read records each fault's rate per 1,000 resolutions as well as per game**, so a
  run with longer games compares.
- **W3 is built beside W1, not after W2** (the coordinator; a change to the order above).
  - Why: W3's F23 is the last engine piece M21 needs (Sublime Epiphany), and the M20 rounds B6, B8
    and B17 wait on W3's `binding.py` work. The owner put M21 and M20 before everything else.
  - The cost: W1 and W3 both touch `binding.py` and `verbs.py`, in different functions. The
    second of them to merge rebases, as B3 did beside E3.
  - W2 still follows W1, and W-D still follows W2.

## 7. Logic check against the project's goals

| Goal | How the plan serves it | What could go wrong, and why the design survives it |
|---|---|---|
| King: play the trained sets really well | A STRONGER fault is a line the learner is paid for that real Magic forbids; a WEAKER one is a legal line it can never learn. Severity-first order removes the paid-for illegal lines before the league's exploiters can find them | The faults are rare (under 0.5% of heuristic games), so the network may not have learned any; §8's network read checks rather than assumes |
| Auto-extend to new cards (zero code) | Each fix is a rule over a primitive, not a card. F14's covers 112 Equip and 32 MODIFY_PT trees across the 19 sets (E3's census) | A fix tuned to the staged card would not generalise: acceptance uses the census's carriers in other sets too (Equip, pumps) |
| The match clock | Engine time is measured per wave (§8 f) | F14b's snapshot and more `moved_since` reads cost time; ±5% games per CPU-second is an acceptance line, so a slow fix is caught |
| Learnable over hardcoded | The rules are not heuristics (NORTH_STAR §3); no cap or schedule is added; W-D removes decisions with no consequence. Hand-set numbers here: the 600 replays and 300 soak games per pool (E-waves' sizes), the 0.5% bound, the ±5% speed band, the 5× escalation ratio (§8) | Each number is an acceptance line for a merge, never something the network sees. They go to BACKLOG only if they become standing gates |
| Generalisation through components | W3's three IR changes each add one CR concept as one encoding (a state trigger, an extra trigger as a static, a reveal's zone), shared by every card that prints it | A second encoding the validator accepts: the gate round's reviewer checks exactly that (CARD_AGENT_BRIEFS §4) |
| Honesty (play never reads a hidden zone) | F63 is fixed before memory v1 reads reveals; SCRY rows are the scryer's | If memory v1 lands first, it reads the opponent's library as "revealed": W3's F63 lane is a stated prerequisite of memory v1 |
| The ceiling | Nothing caps play; WEAKER fixes restore legal lines | — |
| Commander | W5 holds every multiplayer-only fault, with its asks designed for the network | Commander raises the reach of the latent shapes (hybrid, multi-block, replacement order); the guard test gets a Commander pool when one exists |

Three logic risks found while drafting, and their resolution:
- **The general F14 rule would break a verified card.** Angelic Destiny's leaves-the-battlefield
  ability must find the Aura in its graveyard (CR 400.7e); its packs are acceptance lines.
- **"Latent" goes stale.** Four entries of this section were closed or no fault, and three latent
  claims were overtaken by new stamps: Idol of Endurance now reads "exiled with"; Mystic Forge and
  Radha read a library top; Faebloom Trick holds F47's shape harmlessly. Hence W0's guard: latency
  becomes a test, not a sentence.
- **Two fixes are prerequisites of other plans, not just faults.** F23 must precede Sublime
  Epiphany's stamp; F63 must precede memory v1.

## 8. The registered experiment: what decides that a wave merges

The rules stay whatever they do to strength (NORTH_STAR §3); what is registered is the evidence that
each fix is right and that nothing else moved. Per wave, all CPU (no GPU job; one run holds the GPU):
- **(a) The packs.** Every known-bug pack of the wave fails on main and passes on the branch; it moves
  to `tools/scenarios/`.
- **(b) The suite.** `tools/check.sh` green; the counts rise only by the new tests.
- **(c) Trees.** Engine waves change 0 trees; W3 changes exactly its listed trees (tree_dump and
  tree_diff, as C1 and E3).
- **(d) Blast radius.** 600 seeded heuristic replays, 200 per pool, E3's harness (seeds 930000 + i,
  decks from cards verified with the same tree on both checkouts): 0 crashes, and every differing
  game's first differing journal row explained.
  - Predicted changed outcomes: W1 ≤ 3, W2 ≤ 3, W4 0, W5 0.
  - More than predicted is not a failure but an investigation: a side effect, or a rate the
    occurrence run missed.
- **(e) Soak.** With W0's detectors, 300 games per pool: 0 crashes, and no detector class above W0's
  baseline.
- **(f) Engine speed.** Games per CPU-second within ±5% of main over the 600 replays.

**The network read (once, before W1 merges; CPU, about 2 CPU-hours at nice 19).**
- `occurrence.py` with r29's newest main checkpoint on both seats in place of the heuristic, 200
  games per pool on main.
- *Registered prediction:* F14, F44 and F45d fire in under 1% of network games (the heuristic: 0 of
  600, 95% bound 0.5%), with a 95% Clopper-Pearson band.
- *Escalation:* at least 5 firings and at least 5 times the heuristic's bound means the network has
  found the line. Then the owner is told, the line is named in the next segment's confound record,
  and W1 jumps ahead of everything else.
- *Kill:* none, since a rules fix is not reverted for strength. A fix is reverted only for an
  unexplained differing game or a crash in (d).

**Bands.** Rates with 0 events use the rule of three; others use Clopper-Pearson 95%. Replay
differences are counted, not sampled (the replays are deterministic).

## 9. Effort, and what "fix all" means here

- **Effort.** The basis is C1's 247 agent-minutes for four engine faults with their blast radius and
  review (209 §6), about 60 a fault, and 209 §6's gate rounds of 195-474.
  - Totals: W0 300, W1 450, W2 400, W3 330 + re-verification, W-D 150, W4 350, W5 800+. That is
    about 2,000 agent-minutes for the two-player waves.
  - *If wrong:* F14 and F27 have the most readers, so either can double. The order (severity
    first) does not change; only the calendar does. At this week's budget (one round in flight,
    PLAN_PLANNING §6), W0 and W1 fit before the reset of 2026-11-23, and W2-W4 after it.
- **"Fix all" (the owner).** What gets fixed, and where:
  - every fault reachable today: W1, W2, W3, W-D;
  - the faults the copy round makes reachable: as B3's merge conditions (F29, F40), or before
    Sublime Epiphany's stamp (F23);
  - the cheap latent ones: W4;
  - every multiplayer one: W5.
- **Not worth fixing yet**, said plainly: the capability gaps and tripwires that no card in the
  pools or the queued rounds holds:
  - F03, F10a, F10c, F10d, F16, F18a, F18d, F22, F26, F37, F38, F39, F41, F45a, F47, F54, F61, and
    F60's dependencies.
  - Why:
    - no printed text exists to test a fix against, and every acceptance line so far comes from a
      card's text and rulings, so a synthetic-only reading can pin the wrong rule;
    - each fails loudly today (a refusal or a raise, never a silent wrong play);
    - W0's guard makes "no card holds it" a checked fact and turns each into the merge condition of
      the round that first reaches it.
  - F55 stays with its scaffold by the owner's deferral of payment.
- **If the owner wants these built blind anyway**, W4 can take them at about 45 agent-minutes each,
  with the risk named above.

## 10. What this note changed, and why

- **The note itself.** Why: the brief's deliverable, and the input to the red team and the waves.
- **`docs/BACKLOG.md`.** Every entry of "Open engine faults" and the three gate entries carries a
  one-line triage tag: its 215 id, reach, direction, wave. Why: the BACKLOG is where a wave agent
  starts (CARD_AGENT_BRIEFS §5), and the tag points back here. The four entries found closed or no
  fault are tagged, not removed, until the red team confirms the evidence; the section's preamble
  points to this note and the new repro folder.
- **Seven repro packs** in `tools/scenarios/known_bugs/2026-11-18/` (README there). Why: each proves a
  reachable fault on verified cards and is the acceptance line of its wave. They sit outside the
  default sweep, as known bugs do.
- **The evidence**, all under `reports/engine_fault_triage_2026-11-18/`:
  - the scripts: `census.py`, `text_census.py`, `occurrence.py`, `soak.sh`, `soak_seeds.*`,
    `d5_trace.py`, `d6_*_check.py`;
  - their outputs;
  - the closed checks and the probes.

  Why: every number above can be rerun from them.

## 11. The assumptions behind the conclusions, and what changes if one is wrong

| Conclusion | Assumes | If wrong |
|---|---|---|
| A fault is latent | No card of main 8d85e0a7's verified pools holds its shape (census, text census); the detectors encode the shape; a game deals one set | A missed shape or a newer stamp makes it reachable. The guard test (W0) catches a stamp; a missed shape is caught only by verifiers, packs or the soak. Mixed-set games would need a union census |
| A fault is reachable | A legal line with verified cards of one pool exists; the packs stage it with the runner's `move` standing in for removal the pool has | If a stand-in hides a timing the real removal cannot meet, a line could be illegal. Each folder's README names the stand-in, and the census lists the pool's real removal and returns |
| How often it fires | Heuristic play, 600 games: 0 firings of F14, F44 and F45d | Network play may seek the lines; §8's network read measures it. An escalation reorders nothing below W1, which is already first |
| Its direction | Judged on the staged line from the printed text and the card's rulings | Another line can flip it (F14 is weaker for Ball Lightning). The fix is the same either way; only the order within a wave would change |
| Effort | C1's 60 agent-minutes a fault and 209 §6's round costs | F14 and F27 can double; the calendar moves, the order does not |
| The wave order | One wave in flight (this week's budget); the planner keeps to tools/selfplay; B3 runs on PLAN_PLANNING §6's calendar | With two in flight, W0 ∥ W1 then W2 ∥ W3's F63 lane (distinct files). If B3 is ready first, only Sublime Epiphany's stamp waits. If memory v1 comes before W3, its reveal reader waits for the F63 lane |
| A closure (F01, F15, F49, F64, K1) | The test or pack named, and the code read, cover every lane of the fault | A lane not proven reopens it. For F01, the trigger lane is read and pinned, the spell lane rests on `menu.menu` dropping undesignatable rows, and the activated lane on BACKLOG's record that `activate()` refuses an empty required designation (2026-11-13), with no pack of mine. The red team is asked to check exactly these |
