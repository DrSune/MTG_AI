# 216 — Red team of the readiness package (2026-11-18)

**Who and what.** One independent reviewer (Fable, max effort), reading main at 9bebc7ff, who
wrote none of the package. The brief: break every plan where it can be broken, verify claims
against the code and the data, and name the exact fix. The package:

1. `docs/PLAN_LONG_RUN.md`
2. `docs/DESIGN_PLANNER.md` (§1-§6 design; §7 v1 as built behind `--planner`; §8 transfer)
3. `docs/DESIGN_LEAGUE.md`
4. `KNOWLEDGE/2026-11-18/215-engine-fault-triage.md`
5. `docs/PLAN_NETWORK_READINESS.md`

**Verdicts.**

| Plan | Verdict | FATAL | MAJOR | MINOR |
|---|---|---|---|---|
| PLAN_LONG_RUN | **FIX-THEN-GO** | 0 | 2 | 3 |
| DESIGN_PLANNER (v1 code and its A/B) | **FIX-THEN-GO** (the code may stay merged behind its flag as is) | 0 | 3 | 5 |
| DESIGN_LEAGUE | **FIX-THEN-GO** | 0 | 2 | 5 |
| 215 engine triage | **GO** (minor fixes; one ownership conflict to settle, cross-plan C6) | 0 | 0 | 4 |
| PLAN_NETWORK_READINESS | **FIX-THEN-GO** (items 2, 4, 5 GO; item 1's adoption rule and its R5 to fix) | 0 | 3 | 7 |
| Cross-plan | — | 0 | 5 | 4 |

No finding is FATAL: each plan can reach its purpose once the fixes below are in. The three
findings that matter most are cross-plan: C1 (the long run has no stated purpose or stall rule
while the package's own evidence predicts it stays flat), C2 (the GPU calendar is not summed and
the A/Bs cannot share controls as written), and C4 (name dropout has been off in PPO since
2026-11-03 while three documents and the owner's §2 assume it is on). The ranking rule I used:
FATAL = the plan cannot reach its purpose as written; MAJOR = a conclusion, a measurement or a
decision rule would be wrong or misleading unless fixed; MINOR = correctness or coherence that
costs little and should be fixed, or a stated assumption that should be pinned.

---

## 1. PLAN_LONG_RUN — FIX-THEN-GO

**What it is for.** The owner asked what to spar on, plan, red-team and implement before the
cleanup and bug hunt ahead of a multi-day self-play run. The plan triages the backlog and sets the
order. As a triage it is sound; as a plan for the run it leaves the run itself undefined.

### MAJOR

**L1. The long run has no purpose, success criterion or stall rule, and the package's own
evidence predicts it stays flat.**
- *Evidence.* r28 was flat after update 1,000 (199 §9: the 32 gates after v2 average 0.50).
  Neither r29 arm moved off its init in 5.5 machine-hours (208 §11: A 637.7, B 633.8, init
  633.2, se ≈ 4). r29's main run at update 200 (`runs/selfplay/r29b_pself055/metrics.jsonl`,
  last row: `win.frozen` 0.489, `ev` 0.372) shows the same. DESIGN_LEAGUE says in its own summary
  "It is not a lever for the plateau". PLAN_NETWORK_READINESS §1.6 says "From a plateaued init,
  11 hours cannot show a strength gain for either arm". DESIGN_PLANNER §8 calls the planner "a
  hypothesis". So every item the package adds is insurance, hygiene or a hypothesis, and none is
  expected to move L.
- *The registered lever for a plateau is deferred without a decision.* Gate B (search-improved
  training, F1 of PLAN_CEILING §6, D22 item 4) was closed "as not run" with a reopening rule:
  "a training run whose rate falls to 0.70 Elo per machine-hour or less" (196 §10). r29's rate is
  0 ± 0.7. The rule is met; CLAUDE.md says so; neither PLAN_LONG_RUN nor PLAN_PLANNING §6 puts
  gate B on the calendar before the long run ("then P3's gate B", after the planning A/B and the
  curriculum arm). D22's order was F1 → H1 → the ceiling read → H2. The package's "long run" is
  none of these: not H1 (F1 at +200 Elo does not exist), not H2 (fresh weights, after the read).
  The package quietly replaces an owner-approved order with a run that has no name on either
  ladder.
- *Fix.* Add to PLAN_LONG_RUN, before "The order the owner set":
  1. **What the long run is.** Name it on PLAN_PLANNING's ladder (a P1 run: planner, memory,
     value, league) and say that it is not D22's H1 or H2, so the owner sees the deviation and
     rules on it (the overrule clause runs both ways: this is a decision the owner should take
     knowingly).
  2. **A stall rule, registered.** "If L (coherent) has not risen by 2 SE (about 10 Elo) over the
     init at the read at 48 machine-hours, and the puzzle suite's twin-consistent pair count has
     not risen, the run converts to P3: gate B's generation on the run's newest checkpoint
     (reports/gate_b_2026-11-12/queue.sh at a new pin), with the run's remaining budget." The run
     then yields the next lever instead of days of flat.
  3. **What success looks like**: a band for L per machine-day, as PLAN_CEILING §7.3 has for
     H1 ("less than 10 per doubling" is its plateau rule; use its inverse as the success line).
- *Why.* NORTH_STAR §4: "Does this make the bot stronger on the trained pool, or unblock something
  that will? If no, it probably should not have been built yet." A multi-day run that the
  evidence predicts flat, without a rule that turns it into the next lever, fails that test.
  Assumption behind this finding: that r29's flatness is the learning signal's limit, as
  DESIGN_PLANNER §8 argues (the capacity probe 194 found no gain from size). If deals were the
  limit, the league's deck mix would be the lever; the stall rule reads either way.

**L2. The GPU calendar of the package is not in this plan, and it is 45-70 machine-hours of
A/Bs before the run.** See cross-plan C2 for the sum and the fix. PLAN_LONG_RUN's "staged tests"
list only the smoke, the pilot and the run.

### MINOR

- **L3.** Tier 1 item 2 says "The puzzles' combat failures are value errors." PLAN_NETWORK_READINESS
  §1.2 corrects this (both heads read one trunk that does not compute lethal; a better value
  cannot fix the blocks). Update the item so the two plans agree, or the value A/B is read as a
  fix for C it cannot deliver.
- **L4.** "The weakness scan" (tier 3, SYSTEM_MAP §3) has no owner, no build step and no
  definition of its flags' thresholds in any plan of the package. 215 does not schedule it (its
  WEAKER wave fixes known faults, it does not scan for unknown ones); DESIGN_LEAGUE's X6
  (bottom-20 exposure) is the nearest instrument. Give it an owner and a build step (CPU: cast
  rate when drawn, abilities never used, per card, from `train_rows.jsonl` and the game journals;
  a flag is read against the printed text), before the bug hunt it is supposed to run in.
- **L5.** Tier 2 item 8 says "Triage first which are reachable"; PLAN_NETWORK_READINESS §3.1 has
  done it. Replace with a pointer, and add F18b (215's "a multi-slot trigger's ask does not name
  its slot"), which 215 routes to this plan and the readiness plan does not list (cross-plan C6).

---

## 2. DESIGN_PLANNER — FIX-THEN-GO

**What was read.** `tools/selfplay/planner.py` whole; the planner paths of `features.py` (191-192,
614-679), `model.py` (36-260, 440-470, 536-580), `actor.py` (84-151, 396-400), `learner.py`
(559-574, 853-894, 1474-1487), `ppo.py` (117-296); `tools/selfplay/test_planner.py` (261-420);
`tools/puzzles/runner.py` (80-200); `stack.py` 826-846 (the cast's journal order).

**What is right, checked.**
- *Honesty.* Only visible objects get a forecast or a label: `plannable` (planner.py:130-141)
  masks the seat's own hand and battlefield rows plus `permits.playable`'s cards, and only rows
  that are already entities of the encoding. A target label needs the target to be an entity at
  the decision (`hindsight`, planner.py:349: `where[target] + 1 if target in where else 0`), so a
  card the opponent later casts from hand is never pointed at before it is visible. The read-back
  at play time is the network's own forecast (actor.py:149-150); nothing hidden enters it. The
  relabelled input (`plan_x`) is a training-time side-loss input built from the seat's own later
  decisions, never from a hidden zone (planner.py:308-320). OWNER_PREFERENCES #1 holds.
- *Identity across zones.* `Tracker._sync` reads each ZONE_CHANGE row once and keys an object by
  (handle, latest zone-change clock) (planner.py:213-226): CR 400.7 as the engine reads it. The
  mulligan's unjournalled moves are renewed (planner.py:228-237). A cast's target is attached to
  the hand object because the engine journals the targets before the park and the hand→stack
  ZONE_CHANGE row only at the park (stack.py:831-840), so `_aim` (planner.py:301-306) finds the
  use recorded at the act ask; `test_plan_following_reads_the_previous_decisions_hindsight_labels`
  pins it on the real engine (test_planner.py:283-299, `_game` runs `play_game`).
- *The off path.* `tokens` adds the read-back only when `self.planner` (model.py:203-204,
  212-213); `ppo_train` reads the planner arrays only under `a.planner` (ppo.py:136-140,
  188-197); `_job` sets `plan` only when a seat's network is a planner (learner.py:571-573);
  `_load_net` loads frozen members with `planner=False` (learner.py:441), so a pre-planner member
  keeps its computation; `upgraded` zeroes every `plan_*` key for an older checkpoint
  (model.py:560-563). `test_without_the_planner_nothing_changes` and
  `test_an_older_network_becomes_a_planner_computing_what_it_did` cover it (test_planner.py:
  334-418). The design's bitwise claim at the final commit is consistent with what I read.
- *The index conventions* agree end to end: the forecast's target classes are [none, me, opp,
  cards...] (model.py:256-260), `plan_of` reads `keys[t − 1]` (planner.py:152), `readback` writes
  `where[t] + 1` (planner.py:168), `hindsight` writes `where[target] + 1` (planner.py:349).

### MAJOR

**P1. The puzzle runner reads a planner network with a blank read-back, so the A/B's primary
read is taken off the distribution the planner trains on.**
- *Evidence.* `runner.read` encodes the root with `FT.encode_entities` (runner.py:112) and the
  prelude is answered by a scripted `_Prelude` driver (runner.py:81-84), so no `Tracker` runs
  through the decider's earlier decisions and `C_PLAN_*` are 0 at the root. In training, every
  decision after a seat's first reads back its last forecast (actor.py:138, 149-150). A planner
  network that has learned to use the read-back is therefore measured at the puzzles in a state
  it never meets after its first decision; a network whose policy follows the read-back (P2
  below) is measured without the input it follows. The §7 note "the read-back is blank in the
  search's simulations, the labeller's path, linevalue.py and trace.py" does not mention the
  runner, and §5 makes the puzzle categories the A/B's reads.
- *Fix (about 20 lines).* In `runner.root`, when the checkpoint is a planner, give the decider's
  scripted driver a `planner.Tracker(seat, keep=False)`: at each of the decider's asks in the
  prelude call `begin`, encode through `tracker.encode`, ask the network for its forecast
  (`slot.infer((..., feats, 4))`), call `tracker.forecast`, then answer with the scripted word
  and call `end`; at the root encode through the same tracker. Report both roots (blank and
  carried) for one checkpoint once, so the size of the difference is on record. Also add a
  planner-aware path to `rate.py`'s L reads only if they do not already go through `_job`
  (they do when run through the learner's `--eval-only`, which sets `job["plan"]`: fine; say so
  in §7).
- *Why.* A measurement that would mislead. The A/B decides whether the long run carries the
  planner; its puzzle reads would compare the control on its own distribution with the planner
  off its own.

**P2. Plan-following in v1 is self-imitation on an input that names the current action, so it
can only sharpen the policy toward its own mode; v1 has commitment without exploration, and the
A/B has no entropy read or kill.**
- *Evidence.* `plan_x` at decision t is the previous sample's realized labels read back onto t
  (planner.py:316-317). A label is the object's *next use from that decision on, its own answer
  included* (planner.py:323-327), so when t's answer uses object O, the read-back row of O says
  A1 or A2, the verb and the target of exactly that use. The side loss is the NLL of the action
  taken given that input (ppo.py:288-295). Its minimiser is the behaviour conditional π(a | s, x),
  which is near-deterministic because x identifies a. At play time x is the argmax forecast
  (model.py:465-469), trained by hindsight to predict the policy's own most frequent use. So the
  loop is: the forecast predicts the habit, plan-following teaches the policy to execute the
  read-back, the read-back is the habit. Nothing in v1 samples a plan (§3.3: forecasts are never
  sampled; styles arrive in v2), so the owner's "exploration by commitment" is absent in v1 and
  only the commitment half is built. Weighted `--follow-coef 0.1` on 25% of rows at 1/share
  (ppo.py:191-192), it is a per-decision pull of 0.1 toward determinism. The puzzles found one
  habit per decision kind (214 §5); this term reinforces habits by construction.
- *Fix.*
  1. Register the planner A/B (it is named in §5 and scheduled in PLAN_NETWORK_READINESS §6, and
     written nowhere): arms C, P (hindsight + following), and **P0 (`--follow-coef 0`, hindsight
     only)**, so the forecasting task and the following term are read apart; reads R1-R6 as the
     value A/B's (harm screen, L, puzzles, drift, entropy); **a kill on entropy** (per-kind `ent`
     of `priority` and `act` below the control's by more than 0.03 over 10 updates: KNOWLEDGE
     189 §8 showed 0.003 per update is already a near-deterministic day) and on `kinds[*].pass`
     (the pass rate of `priority`, 0.974 today, rising above 0.99 is the collapse 198 §3 describes).
  2. Say in §3.1 and §7 that plan-following in v1 is a commitment term with no exploration, and
     that its gain is expected only with v2's sampled styles or v3's search; the v1 read of it is
     therefore "does it cost" (harm, entropy), not "does it help".
  3. Consider excluding the current decision's own use from the read-back used in plan-following
     (shift the labels to uses strictly after t), so the term teaches "act consistently with what
     you will do later" rather than "copy the row that names this action". Measure both on the
     CPU smoke before choosing; the v3 search needs the unshifted form, so keep it as a flag.
- *Why.* Learnable over hardcoded is about incentives; a side loss that makes the policy copy a
  column is an incentive toward determinism, and the entropy of the policy is what PPO explores
  with. The owner's directive to spar and not rush applies: v1's following term should be shown
  harmless before it rides in the long run.

**P3. The A/B's expectation "memory, holds and coherence should move B, D and A" has no mechanism
at a puzzle root, and the design does not say what a null result ends.**
- *Evidence.* At a seat's first decision the read-back is blank (planner.py:205, 264 with
  `plan = {}`); at later decisions it is `argmax f(s_{t−1})`, a one-step recurrence through a
  four-column argmax bottleneck trained only to predict the policy's own future use (§2 table:
  "it predicts the policy, not the best play"). The B2/D holds the puzzles test are decided by
  visible facts (open Islands, land count) that the policy already sees; the planner adds no
  input about them and no better value. §8 is honest ("a hypothesis... if wrong, dropped") but §5
  predicts movement, and 214 §5 names "the plan module through the opponent's turn" as the B/D
  remedy, which the readiness plan and the league plan both quote as if settled.
- *Fix.* Write the falsifier: "if P does not beat C on the suite's twin-consistent pair count by
  at least 2 pairs of 8 at both 90% and 100% snapshots, and L is within noise, v1's side losses
  are dropped from the long run and v2 is not built on v1's evidence." Correct 214 §5's and
  PLAN_LONG_RUN's wording from "P1's target" to "P1's hypothesis".
- *Why.* An experiment that cannot falsify its claim is the brief's third question. Without the
  rule, a null result motivates v2 (styles, the critic) on the strength of the design alone.

### MINOR

- **P4.** The hindsight loss is the mean over the four heads' cross-entropies and the "when" head's
  labels are 60-80% "never" (§7). Report per-class accuracy (or the macro-averaged recall) per
  head in the iter row's `plan`, not the overall accuracy, which "always never" already scores
  0.6-0.8. `ppo.planner_terms` counts `(argmax == label) & mask` only (ppo.py:285).
- **P5.** The planner's `follow` mask is drawn from the trainer's rng (ppo.py:140), which also
  deals the minibatch order (ppo.py:132), so a planner run's minibatch order differs from the
  control's at the same seed. Harmless; say it in §7 so nobody reads the control as the same rng
  path, or draw `follow` from `substream`.
- **P6.** `_aim` depends on the cast's hand→stack ZONE_CHANGE row being journalled after the target
  asks (stack.py:838-840). The test covers a player target (Shock at "their"); add a creature
  target and an activated ability with a target, and a comment in `Tracker.end` naming the engine
  fact it relies on, so an engine change in the park's boundary turns a test red.
- **P7.** The search's simulations, `linevalue.py` and `trace.py` encode with a blank read-back
  (§7). This is fine for v1's training (no search), but the owner's deployment target is search
  at play time (NORTH_STAR §1a; PLAN_PLANNING P4), so a planner network with search is
  off-distribution in its own playouts. Put "the searcher's simulated seats carry a Tracker" on
  v3's build list explicitly, and before any L read "with search" of a planner network.
- **P8.** §8's table says HER "claims none of its sample-efficiency gains" and the side loss "makes
  plan inputs causal". Causal for the realized plan, yes; for the forecast the read-back is only
  as causal as P2's loop allows. Add the loop to the "if wrong" column.

**On the code as built:** it may stay merged behind `--planner` (off by default) as it is. The
pieces I could check (identity tracking, label alignment, honesty, the off path, the index
conventions) are right. The fixes above are to the A/B, the runner, and two sentences of design.

---

## 3. DESIGN_LEAGUE — FIX-THEN-GO

**What is right, checked.** The assumption-transfer table (§2) is the best in the package: PSRO,
NFSP, PAIRED, ACCEL's score and PLR's seed replay are dropped for stated reasons that hold here
(one GPU; PLR's replay would teach hidden draws, which is OWNER_PREFERENCES #1 read correctly).
The value-function argument (§3.5) is right under γ = λ = 1 (`gae`, learner.py:259-270: the
advantage telescopes to z − V). The registry's refusal of L members keeps PLAN_CEILING §7.2. The
interface list (§6) matches the code: `curriculum_job` (learner.py:606-629), the result tuple
(learner.py:890-891), `_load_net`'s prefix check (learner.py:441-445), `upgraded`
(model.py:536-564). `train_rows.jsonl` exists (learner.py:849-851). The role census's numbers
match `reports/league_teacher_2026-11-18/role_census.json` (M21: 4 counterspells, 2 sweepers).

### MAJOR

**G1. The PFSP payoff estimates' precision is overstated by a factor of 3-5 for the league the
plan builds, so the x(1 − x) weights are noise and the plan should say what then carries the
forgetting check.**
- *Evidence.* §2.1: "a member drawn in 5% of games gets about 50 games an update, so its decayed
  estimate has an SE near 0.02-0.03"; §3.2: "an SE near 0.03 at 50 games an update". With the
  plan's own numbers (history branch 0.25 or 0.55 of about 1,000 games; 37 snapshots a week plus
  externals and exploiters; an active set of K = 8 of about 40; decay 0.9, about 10 updates of
  memory), a member is active in about one update in five and gets about 6-14 games an update on
  average, so its decayed estimate rests on 60-140 games: SE 0.04-0.065 near x = 0.5, and
  stale for any member not drawn in ten updates. The 0.03 holds only while the league has under
  about ten members (the first days).
- *Fix.* Correct §2.1 and §3.2 to the week-end numbers; state that in a 40-member league PFSP is
  near-uniform over the history branch and that forgetting is detected by X0's 48-hour sweep (200
  deals a member) and the floor, not by the weights; or raise the per-member sample by drawing
  the active set once per 5 updates instead of per update (fewer, longer exposures: the same
  throughput, 5× the games per estimate). Add the estimates' SE to the iter row beside x.
- *Why.* A weighting that the plan presents as adaptive but is noise is a hand-set schedule in
  disguise; the owner's rule is that every such number is said aloud with what it really does.

**G2. The exploiter is started from the snapshot it targets, which is the opposite of the
AlphaStar mechanism the plan cites, and 211's result already shows what that produces.**
- *Evidence.* §2.1 marks AlphaStar's assumption (b) failed ("exploiters reset to a supervised human
  policy, which keeps them diverse") and adapts by "start from the snapshot they target". The
  reset's purpose in Vinyals et al. 2019 is diversity: an exploiter initialised at its target's
  weights searches the target's own neighbourhood. 211 §4 did exactly this (an exploiter from
  v2 against v2): +20 Elo greedy in 4 h, sampled win rate flat at 0.50, "no line v2 fails to
  answer". The plan then budgets 8 h per phase on the one measured rate from that same design.
- *Fix.* Alternate the phase's init: odd phases from the target, even phases from another
  lineage already in the registry (r28's v1; later the heuristic-imitating start of
  PLAN_CEILING §8, or a specialist). Record X1 per init kind. Keep the stop rule per init kind
  (two null phases of the same kind end that kind). This costs nothing extra.
- *Why.* The league's one promised reading is exploitability; an exploiter that can only find
  the target's own lines bounds it weakly, and the plan's own transfer table says so without
  acting on it.

### MINOR

- **G3.** Attribution: AlphaStar's main agents weight their 50% PFSP branch by f_hard = (1 − x)^p,
  and f_var = x(1 − x) is the main exploiters' weighting against the main's checkpoints. The plan
  (§2.1, §3.2) credits the branch structure to the main agents while using the exploiters'
  weighting in the history branch, "as D22 settled". Keep x(1 − x) (D22 is the owner's decision
  and the argument for it in PLAN_CEILING §7.1 holds), but say which function is whose.
- **G4.** E-L's familiarity check (L on package and drafted decks, 500 deals per opponent, "0 to
  +30 Elo") has an SE near 10-15 Elo per shape; at 5.5 h it cannot distinguish 0 from +30. It is
  marked "not a kill" (good); mark it "uninformative at this size" and read it only at X4 inside
  the run.
- **G5.** B9 (208 §7, the cycle check among versions) is unread. It is the one measurement that
  says whether the league's insurance is for a real risk; it costs about an hour of evaluation.
  Read it before E-L, not after.
- **G6.** The deck mix cuts coherent practice to 40% per seat (16% of games have both seats
  coherent). L's anchor and r29's whole history are coherent. R1/R2 on coherent decks are the
  right harm screen for this, but say in §4.3 that the familiarity gain is bought with coherent
  practice, and that X4's "coherent L not below the init's" is the standing guard.
- **G7.** §3.5's unbiasedness argument assumes the policy is trained by PPO alone. With the
  planner on, the policy is also trained by a supervised side loss (DESIGN_PLANNER §3.1), for
  which the baseline argument does not apply. Not a league problem, but §3.5 should name the
  assumption since the league and the planner are meant to run together.

---

## 4. 215 — Engine fault triage — GO

**What is right, checked.** The occurrence numbers match `reports/engine_fault_triage_2026-11-18/
occurrence.json` (600 games; 21,568 activated and 4,601 triggered resolutions; 10 sources changed
zones while an ability waited, 0 came back). The five known-bug pack folders exist
(`tools/scenarios/known_bugs/2026-11-18/`). The CR readings I checked hold: 400.7 and its
exceptions 400.7d (a leaves-the-zone trigger finds the object in a public zone), 400.7e (an
Aura's LTB ability finds the Aura in its owner's graveyard) and 400.7h (an effect finds what an
earlier part of it moved to a public zone), which is the list W1 keeps; 603.8 for state triggers
(F23); 702.15b for lifelink as a gain event beside the damage (F27); 603.3b and 603.2d for F24.
The rule of three is applied correctly (0 of 600 → under 0.5% at 95%). The method table (FMEA,
ODC, differential testing, a failing test first) fits a rules engine, and the "no flags" rule for
rule fixes is right (a flag would let a run train on a known-wrong rule). The wave order by shared
files is argued, and the latent-fault guard turns "latent" into a test, which answers the real
risk (three latent claims had gone stale).

### MINOR

- **E1.** W2 (WEAKER) runs after W1 (STRONGER) for file-sharing reasons. SYSTEM_MAP §3 and
  PLAN_LONG_RUN say a weaker-than-printed fault "ranks with the stronger ones, not after them".
  The order is defensible (verbs.py, legality.py and `__init__` are shared); say in §5 that the
  sequencing is file-sharing, not rank, and that W2's packs are acceptance lines of the same bug
  hunt as W1's.
- **E2.** The closures I was asked to check: F49 ("doesn't untap" blocks every untap). I found one
  reader of the wording, in `replacements.py:911` (the Aura's "doesn't untap during its
  controller's untap step" as an IS_ATTACHED_TO filter), consistent with the note's claim that
  only the untap step reads it; I did not run the closed check and its control. F01, F15, F64 and
  K1 I did not verify beyond reading the cited test names. Keep these five removals behind the
  owner's or a second reviewer's confirmation, as the note itself asks.
- **E3.** F63/J1 is owned twice and scheduled twice (cross-plan C6). Settle it here, since 215 has
  the IR argument (REVEAL's zone is a tree concept, so the re-bake of Duress, Freebooter, Thought
  Distortion and Pilfer is a gate round) and the readiness plan's J1 treats it as engine-only.
- **E4.** The network read (§8) measures F14, F44 and F45d under network play with the heuristic's
  bound as reference. Also record the rate per 1,000 *resolutions*, not only per game, so a
  later run with longer games compares.

---

## 5. PLAN_NETWORK_READINESS — FIX-THEN-GO

**What is right, checked.** The detector's counts match `reports/network_readiness_2026-11-18/
tables.txt` (28,837 decisions, 103 of nothing, 58 trigger orders, 2,085 redundant decisions;
the EV-by-turn table to the digit). The learner facts (§0) match the code: `gae`
(learner.py:259-270), the loss (ppo.py:183-186), per-batch normalisation (ppo.py:124), AdamW
(trainer.py:44-45), `glob_f[0] = turn / 20` (features.py:816), and r29b's batch (139,272 steps
and 1,559 learner seats at update 200). A13 (the trainer is idle when the learner commits) is
right: `update()` serves until the trainer's reply and returns after it (learner.py:462-475).
F1's exactness argument is right and the sentinel-event property test is the right guard. F2 is
a protocol-layer change that keeps the engine's replay contract. The memory rules E1-E10 are
sound as lower bounds and the invariants I1-I3 are the right proofs of OWNER_PREFERENCES #1. The
cross-entropy arithmetic (§1.3 e) is right (0.72 against 1.9 at v = 0.9, z = −1). The BCE/tanh
identity is right (tanh x = 2σ(2x) − 1).

### MAJOR

**N1. The adoption rule for the value package adopts by construction.**
- *Evidence.* §1.6: "Adopt V if R1 and R2 are not falsified, R3 is not falsified, and R3 or R4
  favours V." R3 is the value's EV per turn bucket. V's value has two layers of its own and its
  own loss on a 28M trunk whose capacity is not the limit of the value's fit (M5); within 220
  updates its EV will not be below C's, and "favours" (beyond 2 SE of the per-update spread) will
  be met where V's branch fits the early turns better. R4 (directedness of the policy) is the
  only read of the policy-side mechanism, and it is not required. So the rule adopts a change
  whose effect on the policy is within noise on the strength of a value metric that the design
  guarantees.
- *Fix.* Require R4 or R4b (the policy's directedness or its alignment per unit of movement) as
  the mechanism; keep R3 as a check (not falsified). State that if only R3 favours V, the package
  is adopted for its later uses (the search's leaves, the style critic) and not as a policy
  improvement, and say so in the long run's registration. The red team was asked to test this
  rule hardest; this is the failure mode.
- *Why.* The plan's own §1.2 says the value cannot bias the gradient; adopting on the value's
  accuracy alone contradicts the plan's own reason for the A/B (interference with the policy).

**N2. The value branch costs the trainer, not only inference, and the A/B's arms are matched on
machine time in a train-bound run.**
- *Evidence.* K = 2 branch layers on every token are 2 more encoder layers in the forward and the
  backward: 10 layer-passes against 8, +25% of the encoder's work, and the encoder is 25.2M of
  28.07M parameters (`params.py`). r29b is train-bound (160 s an update, "refused about 17 times
  an update while a full batch waits", DESIGN_LEAGUE §1.1). §1.4 "Inference cost" accounts for
  the actors only ("play without search does not ask for it", but the actors do ask for v on
  every recorded decision, actor.py:142-149, and the trainer always computes it). At 11 matched
  machine-hours V gets about 176 updates to C's 220.
- *Fix.* Add a throughput read (trained rows per machine-hour, V over C, as DESIGN_LEAGUE's R3)
  with a band and a response (K = 1, or the value computed in the trainer only), and match the
  arms on updates, or state the update deficit in R1/R2's interpretation. Put the +20% on the
  package's throughput budget (cross-plan C5).
- *Why.* The match clock is King-tied for play, and for training the machine-hours are the
  currency every plan spends; an uncounted 20% is a quarter of a day per day.

**N3. R5 (the puzzles per category) will fire by noise, here and in every plan that reads
"categories".**
- *Evidence.* The suite is 16 puzzles, 8 twin pairs; categories hold 1-2 pairs each (214 §3).
  R5's falsifier is "a category falls by one pair or more": one greedy flip. 214 §5 shows how
  thin the margins are: b70's only pass was B1 at p 0.51 and 0.43, and b80 lost it. The same read
  is DESIGN_LEAGUE's P and the planner A/B's gate.
- *Fix.* Until P2's generator gives hundreds of variants per category, read the whole suite's
  twin-consistent pair count and the mean probability on the right options with a bootstrap over
  puzzles; make "a category falls" a reported observation, not a falsifier. Put the generator
  (PLAN_PLANNING P2) on the critical path before the planning A/B, since three plans read
  categories.
- *Why.* A falsifier that fires by noise either kills good arms or is quietly ignored; both
  corrupt the registration.

### MINOR

- **N4.** R4's "bootstrap over the probe set's decisions" understates the SE: decisions of one
  game share its states and outcome (the plan says so itself at M3). Resample games.
- **N5.** Stage 0's rule ("20% in at least three of the five frequent kinds") is a hand-set
  threshold not listed in §8. List it, with what it rests on (A2's noise gauge) and what replaces
  it (a paired test over kinds).
- **N6.** F4 cites CR 117.3 ("no resources, no action"); 117.3 is about priority. The rules that
  apply are 608.2d/609.3 (an impossible part of an effect is skipped) and the "may" is still a
  choice in paper play. The change is right for a bot (the choice has no consequence); cite it
  as a phantom-decision removal under AGENTS §10, not as a CR requirement.
- **N7.** §4.3/§4.5: say what `F_LIB_POS` shows for a card whose identity is known and position is
  not (E5's scryer side keeps positions; E5/E9 for v ≠ p drop the card entirely). If L[v][p] holds
  only position-known cards, say so in one sentence; the invariants I1 then need no "unknown"
  case.
- **N8.** F3 reads "the resolving effect's remaining atoms" at the agent layer (actor.py) to decide
  whether a library position matters. That is engine knowledge in the actor (OWNER_PREFERENCES #2,
  "no patchwork"). Expose it as an engine accessor (`query`) with its own test, and have the
  actor call it.
- **N9.** "Every column exists from the start, and flags decide which are filled" is right for
  columns and not for entities: memory's known cards and emblems are tokens whose appearance
  renormalises attention (§3.3 says so). Say that a flag turning an entity type on mid-run is a
  shift bounded by the measured KL, and that the pilot runs with every entity type the long run
  will carry.
- **N10.** §1.3 (e)'s switch to cross-entropy "alone on the shared trunk" (stage 0's fallback)
  raises the value's gradient at confident errors by 3-6×; without the detach this *increases* the
  value's pull on the trunk, the thing item 2 set out to reduce. If stage 0 says the branch is not
  built, run the loss-alone arm with the coefficient halved, or read the drift (R4) as a kill, not
  a read.

---

## 6. Cross-plan findings

**C1 (MAJOR). The long run has no purpose or stall rule; gate B's reopening rule is met and P3 is
not on the calendar.** See L1 for the evidence and the fix. This is the finding I would put in
front of the owner first.

**C2 (MAJOR). The GPU calendar is not summed, and the A/Bs cannot share controls as written.**
- *Evidence.* PLAN_NETWORK_READINESS §6: stage 0 (0.7 h, tonight at B8); the value A/B (11 h for V,
  C being the FDN segment) at the FDN segment's start; the planning A/B from 11-23 with arms
  control, memory, planner, value-if-open (4 × 5.5-11 h); then a pilot of 8-12 h. DESIGN_LEAGUE
  §5-§6: a GPU smoke (1 h), E-L (5.5 + 5.5 h, "7.5 h if C is shared with the other A/Bs from the
  same init"), then exploiter phases (8 h per 48) and reads (1.3 h per 48) inside the run. The
  sum before the long run is 45-70 machine-hours, two to three days of the one GPU, during which
  the FDN segment's own registered reads are displaced. The inits differ: the value A/B from B8's
  checkpoint, the planning A/B from "the FDN segment's checkpoint", E-L from "the FDN segment's
  checkpoint or B's latest"; a control can be shared only among arms from one init with the same
  flags, so "if C is shared" is not available as written. Every pause is a moment restart until
  item 6 lands (PLAN_NETWORK_READINESS §5; DESIGN_LEAGUE §4.2's last row), and the planner's
  learner.py merge is a prerequisite of item 6's build (§6 step 4), so the first pauses will be
  restarts.
- *Fix.* One table in PLAN_LONG_RUN: every GPU job, its init, its hours, its reads, in order.
  Prefer **one multi-arm A/B from one init** (control, value, planner P and P0, memory, league +
  mix): 6 arms × 5.5 h plus reads ≈ 36 h, one control, every arm read on L, the whole suite's
  pair count, entropy and throughput, each as a harm screen (the plans agree none can show a
  gain). Build item 6 (the optimizer state) **first**, before any pause: it is CPU, small, and
  its tests are written; the plan's own order puts it behind the planner merge, which is already
  on main (e5101b1e), so nothing blocks it now.
- *Why.* The owner's rule is one run at a time and nothing else on the GPU; a calendar that does
  not exist cannot be kept, and the FDN segment is a registered run.

**C3 (MAJOR). "No harm" screens at −9 Elo resolution are being used to adopt five changes whose
benefits are unmeasurable, and nothing bounds their sum.**
- *Evidence.* R1 at 4 × 1,000 deals has SE 0.0063 (208 §11's B1); its falsifier (upper bound
  below 0.50) needs a mean below 0.4876, about −9 Elo. R2's SE is about 4.6 Elo per difference of
  means. Five changes each cleared at "not worse than −9 Elo" can sum to −30 Elo; the pilot's
  harm screen for the combination (8-12 h) has the same resolution and compares against one
  control.
- *Fix.* State the accumulation bound in PLAN_LONG_RUN ("the sum of the lower bounds of the
  adopted changes' R2 reads must stay above −15 Elo; otherwise the pilot's control is the main
  line without the weakest change"), and make the long run's first 48-hour read (C1's stall rule)
  the check that the combination did not cost what the screens could not see.
- *Why.* Honesty about what the reads can and cannot show (TRAINING_REVIEW_PROTOCOL: "do not report
  a number that skipped a gate").

**C4 (MAJOR, "what is missing"). Name dropout is off in PPO training and has been since
2026-11-03, while OWNER_VISION §2, 184 §16 and the package's premises assume names are masked 10%
of the time.**
- *Evidence.* `_names` drops names only `if dropout and self.training and self.name_dropout > 0`
  (model.py:163). `ppo_train` sets `model.eval()` before every pass (ppo.py:126); the trainer
  builds its network with `.eval()` (trainer.py:41); the learner serves inference in eval
  (learner.py:362). The only `train()` calls are the BC phase's (learner.py:936, 986). The change
  was deliberate: 183 §4 item 1 recorded "PPO ran the net in train() mode, i.e. with name dropout,
  so the ratio compared the acting policy with a dropout-perturbed one" and fixed it (16805b39,
  2026-11-03) by running PPO in eval mode. Two days later 184 §16 wrote "Training masks names only
  10% of the time (`name_dropout` 0.1)", OWNER_VISION §2 (2026-11-06) wrote "Card names are visible
  90% of the time ... so more name masking is planned", and `--name-dropout` still defaults to 0.1
  (learner.py:1447) and is saved in every config. The regulariser the King-tied generalisation goal
  leans on (NORTH_STAR §1: "a design that gets strong play by memorising specific cards has failed
  rank 1"; OWNER_VISION §2) has been inactive for every run from r25 on, and the documents that
  argue "no memorisation" (DESIGN_LEAGUE §4.1, PLAN_NETWORK_READINESS §1.5) do not know it.
- *Fix.* (1) Correct OWNER_VISION §2, 184 §16's pointer and the model's docstring now: names are
  never masked in PPO; the `name_dropout` config field is inert outside BC. (2) If masking is
  wanted (the owner's §2 says it is), apply it where the ratio stays exact: at encoding in the
  actor (a seeded per-decision mask on `cards_i[:, 0]` written into the recorded observation, so
  the trainer sees exactly what the actor saw), behind a flag, as an arm of C2's multi-arm A/B,
  read on the mask-names probe (`mask_names`, a generalisation read that exists) and on L.
  (3) Add a test that fails today: a planner-off network's logits differ between two encodings
  of one decision when the mask flag is on, and `ppo_train`'s forward uses the recorded mask.
- *Why.* The owner's assumption and the drafters' assumption are both false, and neither plan
  could have found it since none is about names; the brief asked for "a measurement that would
  mislead", and "visible 90% of the time" is one.

**C5 (MAJOR). The package's throughput cost in a train-bound run is not summed, and only the
league has a read and a kill for it.**
- *Evidence.* The planner adds the forecast heads on every row, a second forward pass on 25% of
  rows (ppo.py:288-295) and the worker's labels (3-8 ms a game, §7); the value branch adds about
  +25% to the trainer (N2); memory and emblems add tokens; F3 removes some option tokens; the
  league's K networks fragment inference (DESIGN_LEAGUE R3/KL1 cover that part only). r29b trains
  at 162 s an update now; a plausible sum is +40-50% per update, which is 13-14 updates a
  machine-hour instead of 20.
- *Fix.* One throughput budget in PLAN_LONG_RUN: the GPU smoke with the real flags (PLAN_LONG_RUN
  step 6) measures rows per machine-hour for the combination against r29b's, and the pilot's and
  the long run's registrations state the updates-per-hour cost and a kill for it (as KL1).
- *Why.* The reads are per machine-hour; a 40% slower trainer makes "48 machine-hours" 30 of
  today's, and every band in the package was set on today's rate.

**C6 (MINOR). Ownership and ordering conflicts between 215 and PLAN_NETWORK_READINESS.**
- F63/F51 (REVEAL's zone; SCRY's cards) is 215's W3 lane (an IR change, after W2, before B6, a gate
  round with re-bakes) and the readiness plan's J1-J2 (engine-only, "waits on nothing", step 3).
  One owner, one decision on IR-or-not; 215's argument (a reveal's zone is a tree concept) is the
  stronger.
- W-D (F43, F45e) waits on W2 in 215 §6; the readiness plan's F1, F2, F4 "wait on nothing" (§6
  step 2) and 215 says they are "the same lane". Pick one order.
- F18b (Drakuseth's two slots look alike) is routed by 215 to the readiness plan and appears in
  neither of its tables (§3.1) nor PLAN_LONG_RUN item 8. Add it (an `AskContext.slot` the trigger's
  ask fills, as `G_SLOT` already exists: features.py:151).
- The weakness scan has no owner (L4).

**C7 (MINOR). Interfaces, checked and consistent.** The planner's `C_PLAN_*` are the last card
integer columns (features.py:191-192) and the readiness plan appends after them (§3.2);
`job["plan"]` is set per seat by its network's kind (learner.py:571-573) and `_load_net` keeps a
pre-planner member as such (learner.py:441), which is DESIGN_LEAGUE's test 11; the league's
`train_rows.jsonl` fields extend an existing file (learner.py:849-851); memory's known-card
entities would be `plannable` through `permits.playable` only when a permission reaches them,
which is DESIGN_PLANNER §1's "a known library top". The schedule constraints 215 names (F63 before
memory v1; F23 before Sublime Epiphany's stamp) are consistent with the readiness plan's order
(memory's tracker is step 6, after J1-J4). One gap: DESIGN_LEAGUE B3 ("the stats read the right
head") waits on item 2's choice of value head, and the value A/B is scheduled after E-L in one
reading of §6 and before it in another (C2's table resolves it).

**C8 (MINOR). The owner's directives, checked across the package.**
- *Learnable over hardcoded.* Every plan has a said-aloud table (DESIGN_LEAGUE §4.4,
  PLAN_NETWORK_READINESS §8, DESIGN_PLANNER §6-§7, 215 §7). Missing from them: stage 0's 20%/3-of-5
  rule (N5); the planner's `--follow-share 0.25` and the two coefficients' defaults are named as
  BACKLOG scaffolds in §7 but not yet in BACKLOG (enter them when the A/B is registered).
- *Honesty.* Holds in all five (DESIGN_PLANNER checked in code; memory by I1-I3; the league's
  value reads no label; counter-drafting uses training-time identity only). The planner's
  plan-following input is training-time only (P2 is about sharpening, not leakage).
- *No capped ceiling.* F1, F3 and the trigger merge remove no legal move; the deck mix changes
  what is met, not what is paid for. Holds.
- *Weaker-than-printed cards.* 215 fixes the known ones; the scan for unknown ones is unowned (L4).
- *No patchwork.* N8 (engine knowledge in the actor) is the one instance.

**C9 (MINOR). The match clock.** No plan mentions it. Nothing in the package changes play-time
cost except the value branch with search (+25% per leaf) and the planner's one pass; both are
said. Fine for now; the long run's registration should state the p99 decision time of its
deployed network with search, as NORTH_STAR §1a requires of every design decision.

---

## 7. What I checked, how, and what I could not

**Read in full:** NORTH_STAR, CLAUDE.md, OWNER_VISION_LEARNING (§12 twice), SYSTEM_MAP, the five
package documents, PLAN_PLANNING, 214, 213, 208 §11, PLAN_CEILING §6.4, §7.1-§7.3, §8, §9.1, §10,
§14.2-§14.4, DECISIONS D20/D22, OWNER_PREFERENCES, 189 §8, 196 §10, 199 §9, 205 §9, 211 §4,
183 §4, and the BACKLOG entries the plans cite.

**Read in code:** `tools/selfplay/planner.py` whole; `model.py`, `ppo.py`, `actor.py`,
`learner.py`, `features.py`, `trainer.py`, `search.py` (option_classes), `tools/puzzles/runner.py`
at the lines cited above; `MTG_bot/core/executor/binding.py` `_resolution_order`,
`stack.py` 727-846, `permits.playable`, `verbs._look`'s head, `Executor.step_actions`;
`tools/selfplay/test_planner.py` 261-420.

**Read in data:** `reports/network_readiness_2026-11-18/tables.txt`,
`reports/engine_fault_triage_2026-11-18/occurrence.json`,
`reports/league_teacher_2026-11-18/role_census.json`, r29b's last iter row (update 200),
`runs/r29_ab/queue.log`, the known-bug pack folders of 2026-11-18. Every number I quote from them
matched the plans.

**Run (CPU only, nice 19, two threads, the GPU untouched):** `pytest tools/selfplay/test_planner.py
tools/puzzles/test_runner.py -q -x` from this worktree (9bebc7ff) with the main checkout's
interpreter (`CUDA_VISIBLE_DEVICES= OMP_NUM_THREADS=2 PYTHONPATH=. nice -n 19`). Result:
**15 passed in 9.35 s**, nothing failed. That covers DESIGN_PLANNER §7's 12 planner tests and
the runner's, at the commit reviewed.

**Not checked, said plainly:**
- DESIGN_PLANNER §7's bitwise claim against 1daae58e and its CPU smoke numbers (no GPU; the
  bitwise run takes a seeded learner path I did not reproduce). I read the paths and the tests
  that pin them instead.
- The "60-80% never" share of labels, and the per-head accuracies.
- 215's closed checks and probes (F01, F15, F49, F64, K1) were not run; F49's reader was grepped.
- The detector's own code (`meaningless.py`) and the census scripts: their outputs were read, not
  their logic.
- The critic's gates (193) and r28's numbers (199): cited from the notes.
- Whether `rate.py`'s L reads of a planner network run through `_job` in every path (they do
  through `--eval-only`; a direct `rate.py` path, if one exists, would need the tracker: P1).
- No helper agents were spawned: every claim above is from my own reading, and the spawning
  budget was not needed.

---

## 8. The assumptions behind this review, and what changes if one is wrong

| # | Assumption (mine) | Where it binds | If wrong |
|---|---|---|---|
| R1 | r29's flatness is the signal's limit, not the deals' or capacity's (194; DESIGN_PLANNER §8) | L1/C1's stall rule and the ranking of P3 above the long run | If deals are the limit, the league's mix is the lever and the stall rule still reads it; the order of the fixes does not change |
| R2 | The value branch is K extra layers on all tokens (+25% of the encoder) | N2, C5 | If the branch reads a pooled global token only, its cost is negligible and N2 falls to MINOR (the plan should then say so) |
| R3 | Plan-following's input identifies the current action in most decisions where a use is made | P2 | If the A-order is often ambiguous (several rows of one object), the sharpening is weaker; the entropy read then shows nothing, at no cost |
| R4 | The puzzle runner is the A/B's puzzle read (214 §4; DESIGN_PLANNER §5) | P1 | If a tracker-fed path exists elsewhere, P1 is a documentation fix |
| R5 | 183 §4's eval-mode change is still the reason PPO runs in eval (no later commit re-enabled masking elsewhere) | C4 | I grepped every `train()`/`eval()` in tools/selfplay and `name_dropout`'s readers; a mask applied in a path I did not read would overturn C4's "off", not its "undocumented" |
| R6 | The league reaches about 40 members in a week (37 snapshots at one per 100 updates, plus externals) | G1 | With fewer members the SE claim holds longer; the fix (report the SE) is right either way |
| R7 | The harm screens' SEs are 208 §11's (0.0063 on R1; 4.6 Elo on R2) | C3 | Larger deal counts shrink them linearly in cost; the accumulation bound stays |
| R8 | The owner wants to be told when a plan departs from an approved order (NORTH_STAR §2, D22) | L1/C1 | If the owner has already ruled that the long run replaces H1 (not recorded in DECISIONS or PLAN_LONG_RUN), L1 becomes "record the ruling" |

**Why no FATAL.** Each plan's purpose survives its findings: PLAN_LONG_RUN needs a definition of
the run and a calendar; DESIGN_PLANNER's code is right and its A/B needs a runner fix, an entropy
kill and a falsifier; DESIGN_LEAGUE needs two numbers corrected and one init alternated; 215 is
ready; PLAN_NETWORK_READINESS needs its adoption rule and R5 changed and a throughput read. The
one thing that would have been FATAL — hidden information reaching play — I looked for in the
planner's code and the memory rules and did not find.
