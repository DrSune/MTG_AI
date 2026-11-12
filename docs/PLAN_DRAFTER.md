# The drafter, v0: decks for the game we play, from a deck value function

**Status.** Plan, 2026-11-12. Red-teamed before anything is built (§10).

**Why now.** The owner, 2026-11-12: "Also consider getting started on the drafter based on value
function and opponent simulator, getting that working and up to speed would be a nice tool to have
or knob to turn on when things get hard or we get stuck." `docs/PLAN_CEILING.md` had the drafter
last (§9.2, §10). This plan pulls its first working piece forward, beside r27, without taking r27's
GPU except in short windows.

**What it builds on.**
- NORTH_STAR §4a: three modes and two knobs.
- D15: the drafter is a generative policy, and it shares a critic with the Teacher.
- D16: nicheness and randomness are two knobs, never one.
- `docs/DESIGN_DRAFTER.md` is the long-term design. It is Commander-first, and it put Limited last.
  This plan is that design's first piece, on the format the network plays today.

## 1. The format, as it is

- A deck is 60 cards from one set's verified pool (M21, or M20 in a quarter of games). It holds at
  most 4 copies of a card (`games.py:126-129`).
- Today's training decks are "coherent" (`build_coherent_deck`, `games.py:1510`): two colours, 24
  basics split evenly, and 36 spells drawn uniformly from the pair's cards. They are coherent in
  colour and random in everything else.
- So "drafting" here means building that deck card by card, as in DESIGN_DRAFTER's scope note.
  Booster drafting (eight seats, packs) is a different format. MTGJSON carries M21's real booster
  sheets (`MTG_bot/data/M21.json`, `booster.arena` and `booster.draft`), so it is a contained later
  step (§9).

## 2. The pieces: the game's design, applied to decks

| | In a game | In the drafter |
|---|---|---|
| Value function | the network's value head | the **deck critic**: the chance that deck A beats deck B when our network plays both |
| Opponent model | the opponent simulator (the hidden cards) | the **field model**: the decks the drafter's decks will meet |
| Search | sequential halving over moves, scored by the value | **construction**: one intent drawn, then cards added by the critic's value against the field |
| Distilled policy | F1, trained on search's choices | the **pick head**, trained on construction's choices (later, §8) |

The game's opponent simulator gains from the drafter as well: it learns the decks it meets, and
realistic decks are what PLAN_CEILING §5.5 asks for.

## 3. Data: the critic starts from games already played

- Every evaluation row records the game's seed, deck mode and set (`learner.py:663`).
- Self-play deals both decks with `deal_decks(seed, 1409, get_supply(pool, set), mode)`
  (`rig.py:150-159`, `games.py:1550-1563`). That is a deterministic function of the seed and of the
  code that built the pool.
- So both decks of every recorded game can be rebuilt. Each rebuild uses **the run's own commit**,
  extracted with `git archive`, because a later pool or deck builder would rebuild other decks.
- **The rebuild is checked**, not assumed:
  - every rebuilt deck is legal: 60 cards, at most 4 copies, in the recorded set's pool;
  - window 1's simulator capture (40,000 games, at e462628) stores, for every recorded position,
    the game's seed and the opponent's true hand and library (`simulator.Data`, `truth_*.npz`).
    Those cards must all lie in the rebuilt deck of that seat, and early in a game they are nearly
    the whole deck. That checks the procedure exactly on the new game's code;
  - each other source is rebuilt with its own run's code, and its decks pass the legality check.
    No record of r26's decks exists to compare with, so for r26 the commit is the guard.
- **Sources**, all played by our networks:
  - r26's gates and ladders: about 80,000 games on the old game, rebuilt at 4409527. Half of the
    gate deals were five-colour stress piles, which widens what the critic sees;
  - window 1's points: about 8,000 games on the new game, at e462628;
  - r27's gates: 2,000 games every 25 updates, on the new game, at f473c44, growing for days.
- **One known bias.** In these games one seat often searches, or is a newer snapshot. The critic's
  inputs therefore include who played each seat, so a deck is not credited for its pilot.

## 4. The critic

- **v0: one value per card.**
  - Logistic regression on the difference of the two decks' card counts, plus the seat and the two
    pilots: P(A wins) = sigmoid(sum over cards of w_c (n_A,c - n_B,c) + seat + pilot terms).
  - L2-regularised, fitted on CPU in minutes.
  - Each card's w_c is its value as our network plays it, the way 17Lands' card tables are for
    humans.
- **v1: a set network.**
  - It encodes a deck as a set of cards, using card embeddings taken from the game network's card
    encoder (D8: inherit representations).
  - So it can see the curve, the colour balance and synergy, which v0 cannot.
  - It is kept only if it beats v0 on held-out games (G1).
- **Its limit, stated before it is fitted.**
  - Coherent decks are uniform samples, so the data barely vary the curve or the card mix. The
    critic is extrapolating wherever construction leaves those samples.
  - §6's loop is the fix: the drafter's own decks are played, and their games are added.

## 5. Construction: the drafter's search

- **v0 keeps today's frame.** Two colours and 24 basics split evenly; it chooses the 36 spells.
  - This is a scaffold: it enters `docs/BACKLOG.md` "Scaffolds to remove".
  - It goes once the critic is fitted on decks whose land count and colours vary, so it can price
    them.
- **One draw, then near-greedy** (D16; DESIGN_DRAFTER §4.2-4.3).
  - An intent is drawn once: in v0 the colour pair, and later a learned intent.
  - Cards are then added in order of the critic's value against the field.
  - **Randomness** acts on the intent draw and on a budget of value the deck may give up. It does
    not act on each pick. Turning randomness up therefore gives a different good deck, not a worse
    one.
  - **Nicheness** waits for a reference population to be measured against (DESIGN_DRAFTER §2). v0
    has no nicheness knob.
- **With v0's critic, construction is close to "the best cards of the pair, four of each".** That
  is a real deck in a 4-copy format, and it is exactly the case v1 and the loop must test (curve,
  diversity). G3 measures it.

## 6. The loop

1. Fit the critic on rebuilt games.
2. Build decks.
3. In a GPU window, play them with the current network on both seats, evaluation only (no training):
   - drafted decks against coherent decks;
   - drafted decks against drafted decks.

   18 workers play about 60,000 games an hour (r26 played 14-17 games a second).
4. Refit, and repeat.

The field model in v0 is the mix those games are dealt: coherent decks and the drafter's own. A
learned field model, and the counter-drafter mode against one named deck, come with v1.

## 7. Gates, each pre-registered in a KNOWLEDGE note before it is scored

- **G1, the critic.**
  - Held-out games are every 25th seed, never fitted.
  - Its log-loss must beat a critic that knows only the colour pair, the seat and the pilots.
  - Its calibration is checked in 15 equal-mass bins.
- **G2, strength.**
  - Drafted decks against coherent decks, the network on both seats, paired by seed with the seats
    swapped.
  - The bar is 0.60 or more, with the lower bound above 0.55.
  - That is a weak bar on purpose: v0 must first show that the critic's values carry to play.
- **G3, a deck worth training on.** Measured on 1,000 drafted decks at the default randomness:
  - distinct cards per deck;
  - colour pairs used;
  - the mana curve;
  - the share of creatures, removal and lands drawn by turn 4.

  It fails if one colour pair or one list takes more than half the decks.
- **G4, the knob works** (before any training run deals drafted decks).
  - The network plays drafted-deck games without engine errors in 10,000 games.
  - The simulator's NLL on drafted-deck positions is reported, against coherent ones.

## 8. Later pieces, in order

1. The v1 critic (set network), gated against v0.
2. The field model learned from the games, and the counter-drafter mode.
3. The pick head: a pointer over the pool, trained on construction's choices (expert iteration),
   so a deck costs one forward pass per card.
4. Booster drafting on M21's real sheets: packs, eight seats, and a model of the other seats'
   picks.
5. The Teacher's use (PLAN_CEILING §9.1): deals with drafted decks at a share, chosen by the
   learning score L.

## 9. What v0 does not do

- **Booster drafting.** The network plays 60-card decks from the whole pool, so 40-card draft decks
  would be a new format for it. It is listed as later piece 4.
- **Nicheness.** It has no reference population yet.
- **Training runs on drafted decks.** That is the knob. It is turned on when a run stalls, or by
  the Teacher, never silently: a run that deals drafted decks says so in its pre-registration.

## 10. Red team

Before anything is built: a reviewer reads this plan and the code it cites, and its findings are
answered here.

## 11. Order and cost

| When | Machine | Work |
|---|---|---|
| 2026-11-12 | r27 (CPU work beside it, at low priority) | the deck rebuild and its checks; critic v0; G1; construction v0; tests |
| a GPU window of about 1 hour (r27 paused, the pause logged) | drafted-deck games | G2, G3 and G4; the first loop round |
| then | r27 | critic v1; the field model; the pick head |
