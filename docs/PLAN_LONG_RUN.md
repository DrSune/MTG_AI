# Plan: readiness for the multi-day self-play run (draft for sparring, 2026-11-18)

The owner, 2026-11-18: "What is in backlog, that might be relevant to spar on, make a plan for,
red-team and implement, before we do a cleanup/bughunt ahead of the long-running self-play we are
planning?"

**Status.** A draft. The candidates come from `docs/BACKLOG.md` (about 250 entries), read with
today's evidence:
- the planning puzzles: every network plays one habit per kind of decision
  (KNOWLEDGE/2026-11-18/214);
- r29's A/B: neither arm moved off its init (208 §11);
- r29's last 20,000 training games: 0.18% end in a turn-cap draw, none in a stall draw.

Nothing here is built until it has been sparred, planned and red-teamed.

## The owner's decisions (2026-11-18, second round)

- **A league with exploiters:** agreed.
- **The value function:** "try it and see what it yields". A registered A/B.
- **The deals:** agreed, and more. "I would even prefer we implement the drafter and the trainer or
  critic ... that can both draft intelligent decks, as well as make good matchups, utilize
  synergies, utilize exploiting experts etc." It must be "coherent with the rest".
- **The engine:** "Fix all the engine faults as well."
- **Tier 2:** meaningless decisions and observation gaps count "for stability and such". The tier 1
  items get "sufficient time and energy".
- **Every item:** field experts' methods, a logic check before the plan, then a red team, whose
  solid findings are implemented if they do not go against the project's goals.
- **The rails, done 984aa3c4:**
  - TURN_CAP 125, from the decking horizon plus one turn (the owner);
  - MAX_ACTS_PER_STEP 30;
  - every binding counted per update.
- **Who does what:**
  - Opus agents draft the plans, each in a fresh context:
    - the league, Teacher, critic and drafter as one system;
    - the engine-fault triage and waves;
    - the network's readiness: value, meaningless decisions, observation gaps, memory, optimizer
      state.

    Briefs are `brief_draft_*.txt` in the coordinator's scratchpad.
  - A Fable reviewer at max effort red-teams the whole package once it is drafted. A stronger,
    independent reviewer catches what a drafter cannot see in its own work.
  - Opus agents implement, with gate reviews.

## The order the owner set

1. Spar on the candidates.
2. A plan for the chosen ones.
3. A red team of that plan.
4. Implementation.
5. The cleanup and the bug hunt.
6. Staged tests:
   - the GPU smoke with the real flags;
   - a registered pilot of 8-12 machine-hours;
   - then the multi-day run, with its guards, its registered reads and the puzzles as a monitor.

## Tier 1: what shapes what the network learns (spar, plan, red-team, implement)

1. **A league with exploiters.**
   - BACKLOG: "Self-play league / opponent pool", "Prioritized past opponents against strategy
     cycles", "Explore/exploit league"; PLAN_CEILING §7.1.
   - **Why now.** Each network plays one habit per decision kind: always or never countering,
     attacking into a lethal crack-back. Those are exactly what a targeted exploiter punishes, and
     what days of self-play can entrench or cycle (r29's arm B moved from never countering to
     always countering).
   - **The candidate.** The main learner faces frozen versions, the heuristic and exploiters
     trained against the current main, all weighted by prioritized fictitious self-play.
   - **To decide:** the exploiters' share and how often they are refreshed.
   - **Plan (draft, 2026-11-18):** [`DESIGN_LEAGUE.md`](DESIGN_LEAGUE.md), with item 3, the
     Teacher, the critic and the drafter as one system.
2. **The value function.**
   - BACKLOG: "The value loss moves the policy through the shared trunk": a value-only update
     moved the policy as much as a full one (189 §8).
   - **Why now.** The puzzles' combat failures are value errors. The value reads 0.88-0.98 where
     not blocking loses on the spot.
   - **The candidates:**
     - a value head that sends no gradient into the trunk;
     - phasic policy gradient;
     - a lower value coefficient.

     γ = λ = 1 stays (the owner).
   - **To decide:** one registered A/B before the long run.
3. **The deals.**
   - Scaffolds: "Coherent-deck recipe", "Package decks", "Drafted decks stay inside the critic's
     band"; the Teacher.
   - **Why now.** Random coherent decks rarely hold a combo or a planned sweeper, so the planner
     cannot learn the owner's combo and sweeper cases from deals that never contain them.
   - **The candidate.** A package share as a curriculum (`--package-share`, built), plus deals
     replayed by learning value: prioritized level replay, the Teacher's cheapest form
     (OWNER_VISION_LEARNING §6).
   - **To decide:** the mix for the long run.
   - **Plan (draft, 2026-11-18):** [`DESIGN_LEAGUE.md`](DESIGN_LEAGUE.md) §3.4 and §3.8.
4. **The planner, v1.** Being built (DESIGN_PLANNER §5). Its registered A/B decides whether the long
   run carries it.
5. **Memory: what a player has legitimately seen in hidden zones** (PLAN_PLANNING §5, P1). Certain,
   and next after planner v1, since it touches the same files.

## Tier 2: certain and small (implement, no sparring needed)

6. **Save the optimizer's state for a resume.** BACKLOG "Optimizer state is not saved for resume".
   A multi-day run pauses for measurement windows, and each resume restarts AdamW's moments.
7. **Remove the decisions of nothing:**
   - the order ask between identical triggers;
   - Duress and Kitesail Freebooter's choose ask listing each card twice.
8. **One observation-schema change for the gaps reachable in M21, M20 and FDN.** Triage first which
   are reachable:
   - a player's keywords (hexproof, protection);
   - standing permissions, which the planner's plannable objects also need;
   - numbers above 5 bucketed (25 and 30 life thresholds);
   - the X a target ask announces;
   - a delayed or reflexive trigger's index;
   - an ability whose token source ceased.

   The long run should start on one schema, with zero-initialised columns.

## Tier 3: input to the bug hunt (triage now, fix in the hunt)

9. **The open engine faults** (about 60 across Combat, Casting, Triggers, Effects, Mana, Multiplayer,
   To triage).
   - Triage them by reachability in the three pools and by direction, stronger than printed
     first, since that is exploitable.
   - Known stronger-than-printed and still open: "An ability whose source left and came back
     still acts on the source". E3 fixed the counters case; a pump still lands on the new object.
   - The hunt itself repeats 2026-11-17's form: parallel unanchored hunters, the exploit scan,
     and the exploitability probe, now with an exploiter.
10. **Scaffolds that cap play.**
    - TURN_CAP and the stall rule are measured as harmless (0.18% and 0 of games).
    - Still to measure: how often "10 actions per player per step" binds, and the trigger
      quarantine.

**The weakness scan** (the owner, 2026-11-18): weaker-than-printed play ranks with stronger-than-printed
play, because a weakened card loses its gradient, its critic rank and its place in decks, and then
disappears from what the network learns (docs/SYSTEM_MAP.md §3). The scan is the exploit scan's
mirror:
- **Per card:** cast or activated rate when drawn, abilities never used, effect when played, and
  critic rank against mana value.
- **Each flag** is read against the printed text.
- **When:** in every bug hunt. The fix waves rank weaker faults beside stronger ones.

## Not before the long run (by decision)
- **Mana payment by the network** (the owner: later; BACKLOG "Automatic payment").
- **Repeated reasoning with a game clock** (BACKLOG, until size limits quality).
- **Search over plans** (DESIGN_PLANNER v3, after the planner's A/B).
- **Commander and multiplayer items.**
- **The LLM benchmark items.**

## The owner, 2026-11-18, later
- **M21 and M20 in full before FDN.** "Focus on finishing M21 and M20 FULLY before moving to FDN
  (I want tests and self-play with full sets)." So:
  - the segment after B8 trains on M21 and M20 only, with today's fixes;
  - FDN's card work and FDN's training segment wait until both sets are complete.

  This replaces 208 §9's "FDN joins after B8".
- **Usage and draft statistics trigger the strength checks** (SYSTEM_MAP §5).
