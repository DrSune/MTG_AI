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

**Red-teamed 2026-11-18** (KNOWLEDGE/2026-11-18/216, Fable at max effort: FIX-THEN-GO, no FATAL).
Its findings are folded in below, each marked with its number and the reason. One is adapted, not
taken literally: C3's accumulation bound (its literal form fails every time; see "The accumulation
bound").

## What the long run is (216 L1 and C1)

**Why this section exists.** The package's own evidence predicts a flat run:
- r28 was flat after update 1,000 (199 §9);
- neither r29 arm moved off its init (208 §11);
- every item below is insurance, hygiene or a hypothesis. None is expected to move L by itself.

A multi-day run with no purpose and no rule for a stall would fail NORTH_STAR §4's test ("does this
make the bot stronger, or unblock something that will?").

**It is a P1 run** on PLAN_PLANNING's ladder (§5): the main line, trained from the pilot's
combination of the adopted P1 levers, on M21 and M20 complete. The levers are the planner, memory
v1, the value package, the league with its exploiters, and the deal mix.

**It is not D22's H1 or H2.**
- D22's order was F1 → H1 → the ceiling read → H2 (PLAN_CEILING §6-§8).
- H1 needs F1 at +200 Elo, which does not exist. H2 starts from fresh weights after the ceiling
  read.
- So this run departs from an owner-approved order, and the owner should see it. It answers the
  owner's own request of 2026-11-18 for "the long-running self-play we are planning". The
  coordinator decided this under the autonomy rule; the owner can overrule it.

**Why P1 before P3.**
- The puzzles found one habit per decision kind (214). Memory and the plan are limits of what the
  network can represent. Search targets cannot remove them (PLAN_PLANNING §2).
- Gate B (P3: does training on the search's choices move the network?) has its reopening rule met
  (196 §10; r29's rate is 0 ± 0.7 Elo per machine-hour). It runs:
  - next on the GPU if B8 is falsified, as 208 §5 registered;
  - and in any case the moment the stall rule below fires.

**The stall rule (registered).** It is read at 48 machine-hours, the run's first read.
- **Measured:**
  - L on coherent decks (pool L, 208's B2 method), the newest snapshot minus the init;
  - the whole puzzle suite's twin-consistent pair count, from the runner with a carried tracker
    (216 P1).
- **Stalled when both hold:**
  - the L difference is below 2 of its standard errors, about 11 Elo at 208 §11's se of 4 per
    rating;
  - the pair count has not risen.
- **Then the run converts to P3.** Gate B's generation runs on the run's newest checkpoint
  (`reports/gate_b_2026-11-12/queue.sh` at a new pin), on the run's remaining budget. So a stalled
  run yields the next lever instead of days of flat play.
- **Why both conditions.** L reads strength on a held-out pool. The puzzles read planning, which
  can rise before L does. Either one rising is progress.
- **Assumption (216 R1):** the flatness is the learning signal's limit, not the deals'. If the
  deals are the limit, the league's mix is the lever, and this same rule reads it (L rises).

**Success** has two parts:
- L rises at least 10 Elo per doubling of machine time (24, 48, 96 machine-hours), the inverse of
  PLAN_CEILING §7.3's plateau rule;
- the twin-consistent pair count rises.

Each later doubling is read the same way. A doubling below 10 with the pairs flat is a stall.

**The registration also states (216 C5, C9):**
- the combination's throughput, against r29b's rows per machine-hour;
- the p99 decision time of the deployed network with search, at the match clock (NORTH_STAR §1a).

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
6. Staged tests (the GPU calendar below):
   - the GPU smoke with the real flags;
   - one multi-arm A/B from one init, in place of the separate A/Bs (216 C2);
   - a registered pilot of 8-12 machine-hours, which tests the combination (216 C3);
   - then the multi-day run, with its guards, its stall rule, its registered reads and the puzzles
     as a monitor.

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
   - **Why now.** The value misreads the combat puzzles: it reads 0.88-0.98 where not blocking
     loses on the spot. That error matters later, at the search's leaves and for the plan critic.
   - **What it cannot fix** (corrected after 216 L3; PLAN_NETWORK_READINESS §1.2):
     - The policy's failure to block is learned from the result alone. Under γ = λ = 1 the value
       is only a baseline, which cannot steer it.
     - Both heads read one trunk that does not compute "incoming damage ≥ my life".
     - So the value A/B is not a fix for the combat puzzles, and is not read as one.
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
4. **The planner, v1.** Built behind `--planner`, off by default (e5101b1e; DESIGN_PLANNER §7). Its
   arms in the multi-arm A/B decide whether the long run carries it.
   - It is P1's *hypothesis*, not its target (216 P3).
   - The falsifier is in DESIGN_PLANNER §5. If P does not beat C on the twin-consistent pair count,
     v1's side losses are dropped from the long run.
   - v1's plan-following is a commitment term with no exploration (216 P2). So its arms are read
     for harm (entropy, harm screens), not for help.
5. **Memory: what a player has legitimately seen in hidden zones** (PLAN_PLANNING §5, P1). Certain,
   and next after planner v1, since it touches the same files.

## Tier 2: certain and small (implement, no sparring needed)

6. **Save the optimizer's state for a resume.** BACKLOG "Optimizer state is not saved for resume".
   A multi-day run pauses for measurement windows, and each resume restarts AdamW's moments.
   - **First of the network builds** (216 C2): CPU, small, and nothing blocks it now that the
     planner is merged.
   - **The main line must run on it before the multi-arm A/B's init is saved.** Otherwise every
     arm starts from fresh moments. That is equal across arms but a distortion all the same.
7. **Remove the decisions of nothing:**
   - the order ask between identical triggers;
   - Duress and Kitesail Freebooter's choose ask listing each card twice.
8. **One observation-schema change for the gaps reachable in M21, M20 and FDN.**
   - The triage is done: PLAN_NETWORK_READINESS §3.1, with its verdict per gap (216 L5).
   - Added from 215: F18b, a multi-slot trigger's ask that does not name its slot (Drakuseth). Its
     fix is an `AskContext.slot` the trigger's ask fills; `G_SLOT` already exists
     (`features.py:151`; 216 C6).
   - The long run starts on one schema, with zero-initialised columns.
   - Every entity type the long run carries is on from the pilot (216 N9). Columns can be filled
     later without a shift; a new kind of entity mid-run changes attention, a shift bounded only
     by the measured KL.

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
- **Owner and build step** (216 L4: it had neither).
  - **Owner:** the coordinator.
  - **Build:** an agent, CPU only, before the bug hunt it runs in. It writes
    `tools/audit/weakness_scan.py`, which reads the training games' journals and the iter rows'
    `train_rows.jsonl`. It also produces the card statistics of SYSTEM_MAP §5, which the exploit
    scan and the drafter read.
- **The flags.** Each is a statistical statement, not a hand-tuned cut:
  - **An ability never used:** offered at least 300 times and used 0 times. By the rule of three,
    its use rate is under 1% at 95%.
  - **A card rarely played:** among cards of its mana value and card type, in the bottom tenth for
    "cast or activated when it could be", with at least 100 such decisions. Its 95% interval must
    lie below the group's median.
  - **A card rated low:** in the bottom tenth of the critic's rank within the same group.
- **Reading a flag.** Each flag is checked against the printed text as one of:
  - an engine fault;
  - a missing piece;
  - an observation gap;
  - a missing decision;
  - a genuinely weak card, which alone is left as it is.
- **Said aloud:** 300, 100 and "bottom tenth" set how sensitive the scan is. A false flag costs
  one reading of a card's text; a missed weak card costs that card's gradient.

## The GPU calendar (216 C2 and L2)

**Why.** The package's A/Bs, summed, came to 45-70 machine-hours before the run, with four
different inits, so no two could share a control. One GPU and one job at a time means the calendar
must exist to be kept.

**One multi-arm A/B from one init** replaces the separate A/Bs: the value's, the planner's, the
league's E-L and memory's.
- **The arms:**
  - **C**, the control: the main line's flags;
  - **V**, the value package in the form stage 0 picks (PLAN_NETWORK_READINESS §1.6);
  - **P**, the planner with hindsight and plan-following;
  - **P0**, the planner with hindsight only (`--follow-coef 0`; 216 P2);
  - **M**, memory v1;
  - **G**, the league with its exploiters and the deal mix (DESIGN_LEAGUE's E-L);
  - **N**, names masked at encoding (216 C4).
- **The setup:**
  - all arms from one checkpoint of the main line, which already runs on item 6, so the init
    carries its optimizer state;
  - deals matched by `--seed`; C first.
- **Each arm is matched on updates, not machine-hours** (216 N2). About 120 updates is r29's 5.5
  hours. The screens then compare learning per update, which is what each change claims to alter.
  What an arm costs in time is the throughput budget's question, below.
- **The reads, the same for every arm:**
  - R1, the harm screen: the arm against C head to head;
  - R2: L;
  - entropy per kind of decision, with the planner's kill (DESIGN_PLANNER §5);
  - the whole puzzle suite: its twin-consistent pair count and the mean probability on the right
    options, bootstrapped over puzzles. A category falling is reported, never a falsifier: one
    greedy flip moves a category (216 N3).
  - throughput.
- **Each arm's own reads and decision rule** stay in its plan:
  - PLAN_NETWORK_READINESS §1.6 for V and §4.7 for M;
  - DESIGN_PLANNER §5 for P and P0;
  - DESIGN_LEAGUE §5 for G;
  - PLAN_NETWORK_READINESS §3 for N.
- **Cost:** 7 arms × about 5.5 hours, plus about 5 hours of reads: about 44 machine-hours. That is
  one control instead of four.

| Order | GPU job | Init | Machine-hours | Reads | Waits on |
|---|---|---|---|---|---|
| 1 | r29 B to update 300 | (running) | to about 19:40 on 11-18 | B8 (208 §2) | — |
| 2a | if B8 is falsified: gate B (P3) | B's newest | about 30 | 196's registered reads | B8 |
| 2b | otherwise: the M21+M20 segment (the main line under a short registration of its own) | B's update 300, or 500 if B8 is undecided | until the A/B's builds are ready | its gates; B8 again at 500 if undecided | B8 |
| 3 | stage 0, the value's mechanism probe | the main line, at a pause | 0.7 | stage 0's rule | its probe script |
| 4 | B9, the cycle check among versions (216 G5) | r28's and r29's versions | about 1 | B9 | — |
| 5 | the GPU smoke with every arm's real flags | the main line | about 2 | rows per machine-hour per arm | the builds |
| 6 | the multi-arm A/B | one main-line checkpoint | about 44 | above | the builds; item 6 in the main line; P1's runner fix; the puzzle generator (216 N3) |
| 7 | the pilot: the combination of the adopted arms against C | the same checkpoint | 8-12 | the accumulation bound (below) | 6 |
| 8 | the long run | the pilot's combination | days; first read at 48 | the stall rule; L; the puzzles; p99 decision time | 7; M21 and M20 complete; the bug hunt |
| any | gate B | the newest checkpoint | about 30 | 196 | the stall rule, or B8 falsified |

**What runs on CPU beside it** (agents, one GPU job untouched):
- the card rounds, M21 and M20 first;
- the engine waves (215);
- the network builds, in this order:
  - item 6;
  - the planner A/B's fixes (DESIGN_PLANNER §7);
  - the encoding-level name mask;
  - the schema change;
  - the decisions of nothing;
  - memory v1, after W3's F63;
  - the value package, after stage 0;
  - the league;
- the puzzle generator;
- the weakness scan.

## The accumulation bound (216 C3, adapted)

**The problem the red team found.** Each change's own screen only rules out harms larger than about
9 Elo. R1's se is 0.0063 and R2's is 4.6 Elo per difference (208 §11). Five changes, each "not worse
than −9", can sum to −30 or more, and nothing bounded the sum.

**The bound is tested directly, on the combination.**
- The pilot trains the combination of every adopted change against C, from the same init, matched
  on updates, with the screens' deal counts.
- The combination is adopted only if the 95% lower bound of (combination − C) on L is above −15
  Elo, that is, a point estimate above about −6.
- Otherwise the next pilot arm drops the change whose own screen read worst, and so on.

**Why not the red team's literal form**, "the sum of the adopted changes' lower bounds above −15":
- Each lower bound sits about 9 Elo below its point estimate. Five harmless changes would sum to
  about −45 and fail every time.
- The arms share one control, so summing their estimates multiplies that control's noise by the
  number of arms.
- The direct test reads the whole combination at one screen's resolution.

**−15 is a hand-set number, said aloud.**
- It rests on 208 §11's standard errors. A harmless combination fails it about 10% of the time. A
  combination costing 10 Elo is caught about 80% of the time; one costing 15, about 97%.
- The long run's 48-hour read replaces it: it is the second check that the combination did not
  cost what the screens could not see.

## The throughput budget (216 C5 and N2)

**Why.** Every band in the package was set at today's rate:
- r29b trains about 139,000 rows an update in about 164 seconds, about 3.06M rows a machine-hour;
- r29b is train-bound, so every component that adds trainer work slows every update.

**The candidates:**
- the planner's heads and its second forward on a quarter of the rows;
- the value branch, which is K more encoder layers in the forward and backward passes, about +25%
  of the encoder (216 N2);
- memory's and the emblems' tokens;
- the league's fragmented inference.

A plausible sum is +40-50% per update.

**The rule:**
- The GPU smoke with the real flags (calendar row 5) measures each arm's and the combination's rows
  per machine-hour, against r29b's.
- The pilot's and the long run's registrations state the cost.
- **Kill, said aloud:** the long run's combination keeps at least 75% of r29b's rows per
  machine-hour. Below that, the costliest component takes its registered response before the run
  starts:
  - the value branch: K = 1, or the value computed in the trainer only;
  - the planner: a smaller following share.
- **What 75% rests on:** a quarter of the run's updates is the most we pay for components whose
  gain the screens cannot show. The 48-hour read replaces it with strength per machine-hour,
  measured.

## Who owns what (216 C6)

| Item | Owner and order | Why |
|---|---|---|
| F63 with F51 (what a reveal records) | 215's W3, a gate round (running since 2026-11-18). PLAN_NETWORK_READINESS's J1-J2 point to it | A reveal's zone is a tree concept, so re-baking Duress, Kitesail Freebooter, Thought Distortion and Pilfer is a gate round. 215's argument is the stronger one |
| W-D with the readiness plan's F1, F2 and F4 (F3 only under the owner's no-merge rule) | one lane, one agent, after W2 merges | They share `query.py`, `binding.py` and `verbs.py` with W2. The file-sharing order wins over "waits on nothing" |
| F18b (a multi-slot trigger's slot) | the readiness plan's one schema change (§3.1) | It is an observation gap, not a rules fault |
| The weakness scan | the coordinator; built by an agent before the bug hunt | 216 L4 |
| W3 beside W1 (a change to 215 §6's order) | coordinator, 2026-11-18 | M21's last card (Sublime Epiphany, after F23) and the M20 rounds B6, B8 and B17 wait on W3. The owner put M21 and M20 first. The second of W1 and W3 to merge rebases, as B3 did beside E3 |

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
