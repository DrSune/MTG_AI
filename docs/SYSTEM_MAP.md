# System map: how the engine, the cards, the networks and the training loops connect

Written 2026-11-18 at the owner's request: "Add this to the ontology of how all our networks and
everything connect. If we dont have a document describing those, make one now."

**Why it exists.** Every part learns from the parts upstream of it. A fault anywhere propagates
downstream, and often comes back around a loop, as §3 shows. This is the one place that shows the
whole system. Each section points to its detailed home; this file holds no design of its own.

## 1. The parts, upstream to downstream

| # | Part | What it is | Its home |
|---|---|---|---|
| 1 | **Rules engine** | Plays a game exactly by the CR: stack, priority, layers, triggers, combat, zones | `MTG_bot/core/executor/`, DESIGN_PRIORITY.md |
| 2 | **Cards (the IR)** | Each card's oracle text compiled into a tree of shared components (atoms); a verified record stamps the tree | `MTG_bot/core/compiler/`, DESIGN_ATOM_ONTOLOGY.md, PLAN_CARD_ONBOARDING.md |
| 3 | **Gates** | G0 lints, G1 probe, G2 blind verifiers with planted faults, G3 mutants, G4 spec packs; the soak and the exploit scan | `tools/cards/`, `tools/audit/`, MAPPER_GUIDE.md |
| 4 | **Observation (the encoder)** | What one seat may know at one decision, as tokens: its hand, every public card, the stack, players, the turn so far, the options | `tools/selfplay/features.py` |
| 5 | **The policy/value network** | A transformer over those tokens: a pointer policy over the options, a value (the expected result), and the planner's per-object forecasts (DESIGN_PLANNER) | `tools/selfplay/model.py`, `planner.py` |
| 6 | **Self-play training** | Actors play games, and the learner trains by PPO on ±1 results with γ = λ = 1 | `tools/selfplay/actor.py`, `learner.py`, `ppo.py` |
| 7 | **The league and the Teacher** | Who the learner plays (frozen versions, exploiters, the heuristic) and with which decks (recipes) | DESIGN_LEAGUE.md |
| 8 | **The critic and the drafter** | How good a card or deck is for the current pilot; building decks | DESIGN_LEAGUE.md, DESIGN_DRAFTER.md |
| 9 | **Search and the opponent simulator** | Lookahead in copies of the game, over worlds sampled from beliefs about hidden cards; search-trained networks (F1) | `tools/selfplay/search.py`, PLAN_CEILING.md |
| 10 | **Measurement** | The frozen pool L (Elo), the proven planning puzzles, gates, guards, the iter rows' counts (voids, rails, fallback 0) | KNOWLEDGE 205, 214; METRICS.md; TRAINING_REVIEW_PROTOCOL.md |

## 2. What trains what (the signals)

- **The engine and the cards** are trained by nothing. They must be right by construction, which
  is why the gates are blind and planted.
- **The policy** is trained by PPO from game results (6). The planner's side losses (hindsight,
  plan-following) shape it, and the search's targets later pull on it (9).
- **The value** is trained by the results. It is read by PPO (as a baseline), by the search (at
  its leaves), by the plan critic, and by the Teacher's signals.
- **The critic** is trained by game results grouped by card and deck, played by the current pilot.
  So it measures cards as *this* network plays them.
- **The drafter** is trained by imitation of deck construction, scored by the critic (DESIGN_LEAGUE).
- **The league and the Teacher** are adapted by win rates and coverage counts, not by a learned
  reward.
- **The simulator** is trained by what the opponent actually held, from capture games.

## 3. How faults propagate (the loops that matter)

**A card that plays stronger than printed**, an engine fault or a wrong tree, is an exploit:
1. self-play finds it;
2. the policy leans on it;
3. the critic rates it highly;
4. the drafter puts it in decks;
5. the league is shaped by it.

Everything downstream learns a game that is not Magic. The guards are the gates, the exploit scan
(per card and per card pair) and the exploitability probe. The engine triage
(KNOWLEDGE/2026-11-18/215) fixes the reachable stronger faults first.

**A card that plays WEAKER than printed** (the owner, 2026-11-18) is just as harmful, and harder to
see:
1. It does nothing, or less than printed, so casting it is not rewarded.
2. The policy stops casting it: its gradient dies, and no game teaches its real use.
3. The critic sees a card that never helps and rates it at the bottom.
4. The drafter leaves it out, so it is dealt less and played less.
5. The fault never shows in any win-rate scan, because the card is simply absent.

The loop closes on itself. The card disappears from the game the network learns, together with
every interaction it would have taught.

The causes are of four kinds:
- **an engine fault** (WEAKER in 215: Enthralling Hold, Midnight Reaper's lifelink);
- **a suppressed or missing piece** (a KNOWN-GAP sentence, a payment the engine cannot make, as
  Chandra, Flame's Catalyst's −2 before E3);
- **an observation gap**, where the network cannot see what the card does (Drakuseth's slot, a
  player's hexproof);
- **a meaningless or missing decision**, where the network cannot make the card's choice (the
  fallback, now 0; automatic payment).

The guard is the **weakness scan**, the exploit scan's mirror:
- **What it flags,** per card and per set:
  - the rate at which it is cast or activated when drawn;
  - its abilities never used;
  - its effect on the game state when it is played;
  - its critic rank against its mana value and type.
- **How a flag is read,** against the card's printed text: an engine fault, a gap, the
  observation, or a genuinely weak card. Only the last is left alone.
- **Order:** this scan runs in every bug hunt before a long run (PLAN_LONG_RUN, tier 3). A
  weaker-than-printed fault ranks with the stronger ones in the fix waves, not after them.

**An observation gap** (the network cannot see X) makes every decision that depends on X a guess.
The network learns the average and loses the situational skill. This is why every gap reachable in
the pools is closed in one schema change (PLAN_LONG_RUN, tier 2).

**A meaningless decision**, whose options all lead to the same state, adds noise to the policy
gradient and costs a decision of compute. Each one is removed.

**A rail that binds** (the turn cap, the action cap) turns real play into an artificial result,
and so into a wrong signal. Each rail is counted every update with a target of 0 (984aa3c4).

**Pilot-relative evaluation** feeds the next loop. The critic and the drafter rate cards as today's
network plays them, so a card that needs skill is under-rated until the pilot improves. Decks and
pilot have to improve together (DESIGN_LEAGUE). A weaker-than-printed card is the extreme case of
this: no pilot can make it good.

## 4. Where each check lives

| Check | Catches | When it runs |
|---|---|---|
| Gates G0-G4 | A card's tree against its printed text | Every card, before it is dealt |
| Engine tests and scenario packs | The rules, per mechanic and per card | Every commit (`tools/check.sh`) |
| Soak detectors | Anomalies in random games | Bug hunts |
| Exploit scan, exploitability probe | Stronger-than-printed play | Before long runs |
| **Weakness scan** (§3) | Weaker-than-printed play | Before long runs, in every bug hunt |
| Planning puzzles (proven) | Whether the network plans | Every gate checkpoint |
| L ratings | Strength against a frozen pool | Registered reads |
| Iter-row counts (voids, rails, fallback, overflow) | Artificial outcomes in training | Every update, target 0 |
