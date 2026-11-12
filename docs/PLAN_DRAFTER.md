# The drafter, v0: decks for the game we play, from a deck value function

**Status.** Plan, 2026-11-12, revised the same night after its red team (§10). Nothing is built
yet except the data it needs: every training game's deal and result are logged from r27 on (§3).

**Why now.** The owner, 2026-11-12: "Also consider getting started on the drafter based on value
function and opponent simulator, getting that working and up to speed would be a nice tool to have
or knob to turn on when things get hard or we get stuck." `docs/PLAN_CEILING.md` had the drafter
last (§9.2, §10). This plan pulls its first working piece forward, beside r27, taking r27's GPU
only in short windows.

**What it builds on.**
- NORTH_STAR §4a: three modes and two knobs.
- D15: the drafter is a generative policy, and it shares a critic with the Teacher.
- D16: nicheness and randomness are two knobs, never one.
- `docs/DESIGN_DRAFTER.md` is the long-term design. It is Commander-first and put Limited last;
  this plan is its first piece, on the format the network plays today.
- OWNER_VISION_LEARNING §2 and PLAN_CEILING §9.3: every deal stays fresh, so nothing is memorised.

## 1. The format, as it is

- A deck is 60 cards from one set's verified pool (M21, or M20 in a quarter of training games), at
  most 4 copies of a card (`games.py:126-129`).
- Today's decks are "coherent" (`build_coherent_deck`, `games.py:1510`): two colours, 24 basics
  split evenly, and 36 spells drawn uniformly from the pair's cards. They are coherent in colour and
  random in everything else.
- So "drafting" here means building that deck, as in DESIGN_DRAFTER's scope note. Booster
  drafting (eight seats, packs) is a different format. MTGJSON carries M21's real booster sheets
  (`MTG_bot/data/M21.json`, `booster.arena` and `booster.draft`), so it is a contained later step
  (§8).

## 2. The pieces: the game's design, applied to decks

| | In a game | In the drafter |
|---|---|---|
| Value function | the network's value head | the **deck critic**: the chance that deck A beats deck B when our networks play them |
| Opponent model | the opponent simulator (the hidden cards) | the **field model**: the decks a drafted deck will meet. In v0 it is the mix of decks dealt, and with v0's additive critic it changes nothing (§4); it matters from the v1 critic on |
| Search | sequential halving over moves, scored by the value | **construction**: k swaps on a freshly dealt deck, each the swap the critic values most |
| Distilled policy | F1, trained on search's choices | the **pick head** (later, §8) |

The value head cannot judge a deck: the network reads only its library's size
(`features.py:669`). So the critic is a separate model. The game's opponent simulator gains from
the drafter: it learns the decks it meets, and realistic decks are what PLAN_CEILING §5.5 asks for.

## 3. Data: rebuilt decks and their results

- Self-play deals both decks with `deal_decks(seed, 1409, get_supply(pool, set), mode)`
  (`rig.py:150-159`, `games.py:1550-1563`). Deck i goes to seat i (`games.py:1092`), and seat 0 is
  on the play.
- The decks are a function of the seed and of the code that built the pool. **Every rebuild uses the
  run's own commit**, extracted with `git archive`. The verified M21 pool has 263 cards at r26's
  4409527 and 262 at e462628 and later. Rebuilt at a later commit, every r26 stress deck and 64% of
  its coherent deals come out wrong, and they still pass a legality check.
- **The check.** Window 1's simulator capture stores, per position, the game's seed, the opponent's
  true hand and library, and the public cards. Together they equal the rebuilt deck at every one of
  shard 0's 53,366 positions (red team, 0 mismatches, M21 and M20). Every rebuilt deck is also
  legal: 60 cards, at most 4 copies of a non-basic, in the recorded set's pool.
- **Sources** (only coherent games between two networks; stress piles worsened the held-out fit
  in every fold, and 7,000 of r26's ladder games had a random or heuristic seat):
  - **r27's training games.** From r27 on, `learner.py` writes every training game's seed, deck
    mode, set, seats, result and update to `train_rows.jsonl`: about 1,875 games per update, on the
    new game, with M20. This is DESIGN_TEACHER §6.4's "one triple per game ever played", and it is
    the main source.
  - **r26's gates:** 20,000 coherent deals, each played twice with the pilots swapped, on the old
    game.
  - **Window 1:** too small to use. It replays the same 600 deals at every point.
- **Pilots.**
  - Gates swap the pilots within a deal, so there the pilot terms only reduce variance.
  - Training games are not paired, and the learner meets older versions and the heuristic, so the
    critic carries a term per pilot (run, update block, opponent version).

## 4. The critic

- **v0: one value per card, per game version.**
  - It is a logistic regression on the difference of the two decks' card counts, plus the seat and
    the pilot terms.
  - It is fitted on r26's old game as a prior, then on the new game as a penalised deviation from
    that prior.
  - Each card's value is its worth as our networks play it, as 17Lands' tables are for humans.
  - On r26's 20,000 coherent gate deals it beats the colour-pair baseline in 5 of 5 seed-grouped
    folds, and its top cards are M21's bombs (Baneslayer Angel, Elder Gargaroth, Terror of the
    Peaks; red team).
- **v1: a set network** over card embeddings taken from the game network's card encoder (D8).
  - It can see the curve, the colour balance and synergy.
  - It is kept only if it beats v0 on held-out games.
- **The limit, stated first.**
  - Coherent decks are uniform samples, so the data barely vary the curve or the card mix.
  - The critic is therefore trusted only inside the range the data cover. §5 keeps construction
    there, and §6's loop widens the range.

## 5. Construction: k swaps on a fresh deal

The red team found that "the best cards of the pair, four of each" collapses to 10 decks built
from 25 of 240 spells. Their mean mana value is 4.07, against the coherent decks' 3.26, whose 99th
percentile is 4.08. That breaks "every deal stays fresh" and leaves the critic's range. So
construction starts from the deal.

- **The start** is today's coherent deck, dealt by the game's seed. That is D16's single draw, and
  it gives the undirected variety: no two deals start the same.
- **Then k swaps.** Each removes the deck's least valuable spell copy and adds the most valuable
  card of the pair that still has a copy free, by the critic.
  - The swap is deterministic given the critic, so a seed and the critic's hash rebuild the deck.
  - A swap that would leave the coherent decks' 1st-99th percentile band (curve, creature count,
    copies of one card) is skipped. This is a guard on the critic's range, written to
    `docs/BACKLOG.md` "Scaffolds to remove". It lifts as §6's loop widens the range.
- **k is the strength knob.** k = 0 is today's dealing. With the red team's fitted critic, on 1,000
  deals:

  | k | Predicted gain | Mean mana value | Spells in at least 1% of decks |
  |---|---|---|---|
  | 4 | +0.77 logits | 3.56 | 229 |
  | 8 | +1.31 logits | 3.81 | 212 |
  | 16 | +2.02 logits | 4.12 | 164 |

  All 1,000 lists were distinct at every k. The gains are the critic's own predictions; G2 tests
  them.
- **D16, in these terms.** Randomness is the start deal. k sets how much of the critic's value is
  spent, so a smaller k is a more varied and weaker deck: NORTH_STAR §4a's "a worse standard deck"
  is the price of randomness, and k states it. Nicheness waits for a reference population
  (DESIGN_DRAFTER §2). v0 has no nicheness knob.

## 6. The loop

1. Fit the critic.
2. In a GPU window, play drafted decks with the current network on both seats, evaluation only:
   - drafted against coherent, at k = 0, 4, 8 and 16;
   - the decks swap seats within a deal, not the pilots.

   18 workers play about 60,000 games an hour.
3. Add the games and refit, so the critic learns the decks it built; widen the band; repeat.

## 7. Gates, each pre-registered in a KNOWLEDGE note before it is scored

- **G1, the critic.**
  - It is scored per game version, by 5-fold cross-validation grouped by seed.
  - Its log-loss must beat a baseline of the colour pair, the seat, the pilots and 12 deck
    summaries: mana-value buckets, creature count and rarity counts. That baseline already takes
    54% of the cards' gain on r26, so the gate tests the cards themselves, which still beat it by
    0.007 on r26.
  - Calibration in 15 equal-mass bins.
  - The new game's G1 needs at least 2,000 new-game deals: an hour of r27's training games.
- **G2, the values carry to play.**
  - At least 1,000 deals per k (standard error about 0.013), with the network on both seats and
    the decks swapping seats.
  - Observed win rate against the critic's prediction at k = 0, 4, 8 and 16.
  - It passes if the calibration slope's lower bound is above 0 and k = 8 beats k = 0 with its
    lower bound above 0.5.
- **G3, decks worth training on.** On 1,000 drafted decks at each k, all of these:
  - at least 990 distinct lists;
  - at least 150 spells in 1% or more of the decks;
  - the mean curve, the creature count and the copies of one card inside the coherent decks' 1st-99th
    percentile band.
- **G4, the knob itself: does it help learning?** This is the owner's purpose.
  - In seat-swapped pairs of the current network against an older one, it measures the share of
    deals whose winner changes when the pilots swap. That is the share of games that skill decides,
    a direct proxy for learning signal per game. On r26's coherent gates it was 23%.
  - It is measured on drafted and on coherent decks, in the same window.
  - It also requires 10,000 drafted-deck games without engine errors, and reports the simulator's
    NLL on drafted-deck positions.

## 8. Later pieces, in order

1. The v1 critic (set network), gated against v0.
2. The field model learned from the games, and the counter-drafter mode against a named deck.
3. The pick head: a pointer over the pool, trained on construction's choices (expert iteration),
   so a deck from scratch costs one forward pass per card.
4. Booster drafting on M21's real sheets: packs, eight seats, and a model of the other seats'
   picks.
5. The Teacher's use (PLAN_CEILING §9.1): deals with drafted decks at a chosen k and share, chosen
   by the learning score L.

## 9. What v0 does not do

- **Booster drafting.** The network plays 60-card decks from the whole pool; 40-card draft decks
  would be a new format for it.
- **Nicheness.** It has no reference population yet.
- **Training runs on drafted decks.** That is the knob. It is turned on when a run stalls, or by
  the Teacher, never silently: a run that deals drafted decks says so in its pre-registration.

## 10. Red team (2026-11-12, one reviewer, CPU checks on r26's rebuilt decks)

| Finding | Answer |
|---|---|
| BLOCKER: "best cards, four of each" gives 10 decks from 25 spells, outside the data, and G3 could not fail | §5: k swaps on a fresh deal; G3's bars can fail |
| BLOCKER: G1 cannot be scored on the new game: window 1 is 600 deals, r27 has no data, stress piles and non-network seats pollute | §3: coherent network games only; r27's training games logged (in r27 from its launch); G1 per version |
| G1's baseline is too easy: deck summaries take 54% of the gain | §7: summaries in the baseline |
| G2 has no sample size, and its bar ignores the critic's own prediction | §7: 1,000 deals per k, a calibration slope |
| No way to deal drafted decks; the harness swaps pilots, not decks | §6, §11: a deck mode in `tools/selfplay` (the engine is not touched), with seat-swapped decks; the deck mode and critic hash go into the rows |
| Nothing tests the owner's purpose | §7: G4 |
| The field model does nothing in v0 | §2 says so |
| The randomness wording contradicted NORTH_STAR §4a | §5 |
| Pilot keys and the legality check | §3 |

## 11. Order and cost

| When | Machine | Work |
|---|---|---|
| 2026-11-12 night | window 1, then r27 | `train_rows.jsonl` in r27 from its launch |
| 2026-11-12 | r27 (CPU work beside it, at low priority) | the rebuild and its capture check; critic v0 on r26, then on r27's games; G1; the drafted deck mode, seat-swapped decks, and tests |
| a window of about 2.5 hours (r27 paused, logged), shared with PLAN_CEILING §4.1's probe | drafted-deck games | G2, G3 and G4; the first loop round |
| then | r27 | critic v1; the field model; the pick head |
