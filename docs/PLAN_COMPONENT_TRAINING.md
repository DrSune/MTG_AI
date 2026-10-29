# Plan: train the playing network to understand its components (2026-10-28)

**For the local agents to execute.** Claude wrote this plan and does not run it (owner, 2026-10-28:
"prepare a plan, and then the agent later can do the actual plan ... we can save some usage").

## The goal, in the owner's words
- "The network that places the card knows what the atomiser components mean."
- It knows "when to choose what it can choose, when to choose which volumes, how much to sacrifice,
  what it means to sacrifice".
- "The bottleneck is making the model generalise. It's playing level."
- Reading components as input is a **prerequisite only**. The work is **training understanding**:
  - each component's effect, and how to act on it in every decision;
  - finding the components the network does not yet understand, and fixing those specifically.
- Mapping new card text onto components is a separate chore (agents write card records as data);
  it is not part of this plan.

## What we know (CPU kill tests, 2026-10-27/28)
| Test | Result | Note |
|---|---|---|
| K1/K1b | Engine-supervised effect prediction over a component bag transfers to unseen cards, more so with more real sets (+0.205 from 1 to 16 sets). | /165, /166 |
| K1c | Per card, a bag of components beats a transformer over its IR (at current volume). | /166 |
| K2 | Engine-labelled choices: on unseen cards a component chooser scores 0.861, a name chooser 0.709, no card info 0.733. Names only memorize. | /169 |
| Sharing | 48 of 193 component types cover 90% of uses, and 26% of types appear on two cards or fewer. | B-44, B-48 |
| RL pilot | Flat two nights running: the mirror is 0.523, then 0.528 [0.458, 0.596]; against the teacher, 0.343. One update per night cannot teach anything. | /156, `reports/rl_window_2026-10-27.md` |

## Step 0: fix what blocks training (do first; mostly CPU)
1. **Stop learning choices from `HeuristicTeacher`.** It takes the first option at every target,
   sacrifice and mode ask, and the minimum number (`tools/eval/gameplay_eval_v2.py:168-269`).
   - For those asks, use the engine's replay label instead (`tools/k2/gen.py`).
   - Keep the heuristic, if at all, only for the act window, attacks and blocks, and only until RL
     takes over.
2. **Let "volumes" be learned.**
   - The bench fixes X at 0 (a registered scaffold). Add an X-choice ask to `MTG_bot/bench/router.py`
     (X from 0 to the mana available) so X can be labelled and trained.
   - Same for excess trample damage, which already asks.
3. **Make discard and hand choices labelable.** The 24-number board summary cannot see which card
   left the hand, so K2 marks every discard uninformative. Score those options by a short rollout
   (to the end of the next turn) with a value model, or by the K1 effect value of the card kept.
4. **Fold the component tail** (B-44, B-48) before the big training run. Fewer, more general
   components get more training each, which is the owner's point.
   - Eight "this turn" predicates become one counted-event atom.
   - Five comparators become one property comparison.
   - Discard gets one encoding, not two.
   - Re-bake the goldens and the vocabulary once, at an era boundary.
5. **RL must actually update.** One gradient step per night is a no-op (/156, /158). Collect, then
   train many epochs (PPO-style, with a learned value for per-decision advantages) before the next
   collect. Keep the outcome reward (D10: cap and stall draws are a loss). Add no shaping.
6. **Prerequisite only.** The policy must see each card's components, as one card token from a
   component-bag encoder in place of name words (`tools/training/ab_duel.py:572-578`,
   `bc_model.py:45`). Necessary, not the point.

## Step 1: teach what each component DOES (engine-supervised, dense)
- **Train** the card encoder plus a state encoder on K1's task, the board change of casting or
  activating a card (`tools/k1/gen.py`, `tools/k1/train.py`), on every compiled card of the 19
  sets.
- **Widen the labels beyond 24 counts:** where each moved card went, counters by kind, keywords and
  abilities granted or removed, tapped and untapped objects. Components like "grant hexproof" or
  "tap target" are invisible in today's lanes.
- **Gate.** Unseen-card median skill must be at least K1b's 0.52. Report it per component (see
  Measurement below).

## Step 2: teach what to CHOOSE given a component (engine-labelled)
- **Train** the choice head on K2's replay labels (`tools/k2`), sharing Step 1's encoder. Cover
  target, sacrifice, may, modes and, after Step 0, X and discard.
- **Lengthen the horizon.** Score options at the end of the next turn, with the current policy as
  the continuation instead of do-nothing. Once a value model exists, score with it instead of the
  hand-made probe value.
- **Gate.** On unseen source cards, at least 0.861 (K2 run 2), and no major component group below
  the no-card floor.

## Step 3: drill the components the network gets wrong
- **Find the weak components** with the report card (Measurement below).
- **Build drill boards** from the scenario-pack format (`tools/scenarios/*.json`): real cards in
  positions where the right choice hinges on that component.
  - Examples: X damage against creatures of mixed toughness; a sacrifice among permanents of
    different worth; a "may" that hurts its controller.
  - The engine labels each drill by replay, as in K2.
- **Mix drills into Steps 1–2** at a small share, and grow the share until the weak component
  passes.
- **Synthetic cards** (new compositions of known components) come only after real-card drills, as
  the clean test of new combinations (owner, 2026-10-27).

## Step 4: refine long-horizon play with RL
- Initialize from Steps 1–3, and keep their heads as auxiliary losses so component meaning is not
  forgotten.
- RL covers what one-turn labels cannot: when to cast, sequencing, combat, racing.
- Use self-play against a frozen panel (the heuristic plus earlier checkpoints); add exploiters
  later (REVIEW_ARCHITECTURE F4/F5).

### Exploration in the long run (owner, 2026-10-29)
Owner: huge exploration from the very beginning, over all or nearly all sets, "will likely cause
slow improvement rate, but also ensure we are more likely to converge on the best solutions for each
deck" and generalise better to new cards and decks. Agreed, with these refinements:
1. **Breadth comes mostly from the environment.**
   - Train on every verified set and many decks from the first update. This is domain
     randomisation.
   - In Procgen (Cobbe et al. 2020), generalisation grows with the number of distinct training
     levels.
   - A policy that never sees one meta for long cannot overfit to it.
2. **Explore over strategies, not clicks.**
   - Uniformly random actions in MTG are mostly plainly bad (K2's random base games), so raw noise
     wastes games.
   - Use an entropy bonus with an adaptive target entropy, a learned temperature as in SAC, rather
     than a hand-set annealing schedule ("learnable over hardcoded").
   - Use a league (AlphaStar):
     - several main agents with different seeds;
     - exploiters that hunt the main agents' weaknesses;
     - prioritised fictitious self-play against the pool.
   - The league keeps non-transitive strategies alive and stops a collapse onto one exploitable
     line.
   - Report learning curves per deck archetype.
3. **Start from Steps 1–3, not from scratch.**
   - Exploration then happens around play that already understands its components.
   - Keep their auxiliary losses.
   - Do not anchor with a fixed KL to the BC policy; it fights exploration. If a KL is used, let an
     adaptive coefficient set it.
4. **Exploration finds engine bugs.**
   - A high-entropy policy is a fuzzer. It will build its play around any card that is stronger
     than printed.
   - Gate: every dealt card passes the gates of `docs/PLAN_CARD_ONBOARDING.md` before the run.
   - During the run, watch each card's usage and its win rate when cast. A jump means either a
     discovery or a bug, so review it.
5. **How many sets first: a measurable trigger, not a count.** Start when:
   - the component inventory saturates, meaning a newly mapped set adds few component types never
     seen before (for example, under 3% of its component uses), measured from the mapped records;
   - every dealt card is verified;
   - the policy reads components (Step 0, item 6). Without that, more sets only add names.
   - Adding verified cards of known components during the run needs no restart; that is the
     auto-extend goal. A new atom is an era boundary.
6. **Measure that exploration pays.** Hold out whole sets (zero-shot, as M20/KHM) and plot their
   curve next to the training sets' curve.

## Measurement: the component report card (build it before Step 1)
- **Grouping.** For every labelled decision, take the component group that drives it: the source
  ability's verbs and predicates (DEAL_DAMAGE, MODIFY_PT, MOVE_ZONE→graveyard, SACRIFICE cost, X
  quantity, ...).
- **Report per group:** accuracy against the engine label on seen and on unseen cards, the number of
  decisions, and the floor (no card info) and chance.
- **Weak** = unseen accuracy within 0.05 of the floor, or under 200 decisions. Weak groups feed
  Step 3, and the card is re-run after every training run.
- **Paired** with play-level numbers (METRICS §17): a report card alone can be gamed by a policy
  that never reaches those decisions.

## Gates before the new network replaces the pinned one
1. **Name-permutation invariance.** Byte-identical logits when card names are swapped.
2. **Report card.** No major group weak on unseen cards.
3. **Duplicate-duel swap test** (`MTG_bot/bench` `play_duplicate`). Swap trained cards for unseen
   cards made of known components: functional twins first, then new combinations. Win rate against
   the heuristic must stay inside the original decks' interval, and the name-reading policy must
   drop.
4. **Zero-shot set.** M20 and KHM compiled-pool duels, reported next to M21.

## Rules for whoever executes
- **One pre-registration file per run,** written before results (`docs/TRAINING_REVIEW_PROTOCOL.md`).
  Floors in every table. Every seed reported: K1c showed single fits move by about 0.1.
- **PIN law.** `MTG_bot`, `tools/eval` and `tools/training` are fingerprinted. Build next to the RL
  payload and adopt at an era boundary with an explicit re-pin.
  - **Note:** `main` already drifted on 2026-10-28 when the compiler branch merged (fingerprint
    `297f66c4` against the pin `07fd1a6e`). Re-smoke and re-pin before the next window.
- **GPU** is shared with CED. Data generation and the report card are CPU work. Training waits for
  an agreed slot.
- **Do not:**
  - train on `HeuristicTeacher` choice labels;
  - add shaping rewards;
  - spend effort on automatic text parsing (the mapping chore is separate).
