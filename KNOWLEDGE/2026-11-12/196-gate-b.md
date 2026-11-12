# 196 — Gate B: does a network distilled from 300k search targets beat its original? (pre-registration)

**Context.**
- `docs/PLAN_CEILING.md` §6.2. F1, the fast model trained on its own search, runs only if gates A
  and B pass.
- Gate A passed on u1000: the search at n = 16 scored 0.555 against its own network on fresh deals
  (192 §4). D23 fixed n = 16 for F1's targets.
- **E3 is the failure gate B must not repeat** (186 §5).
  - 100k true-future labels, 92% of them ties, were distilled.
  - Every trained epoch fit the held-out targets worse than the original, so the rule "lowest
    held-out KL, epoch 0 included" kept the unchanged network.
  - Its gain was exactly 0.500, and that hid the trained epochs' small effect: 3.6% less regret,
    no gain in results.
- **What differs now:**
  - The leaf is the value head one turn ahead, not a game's ±1 end. At n = 16, 16.0% of targets
    showed no difference in result (192 §4), against E3's 92% of labels.
  - Under a continuous leaf, a difference also counts noise, so the share is not a measure of
    signal. Clear corrections, a search pick at least 0.1 above the network's own, came at
    0.64 per game.
  - The step is scaled by the standard error of the means.
- The design was red-teamed before any data (one reviewer, 2026-11-12). §5 lists what changed.
- Written before any gate B target exists. Results are appended below and never edit this
  section.

## 1. The protocol

**When and where.**
- After r27's registered read at update 500 (191 §6), about 2026-11-13 (§6: moved from 1,000
  before any data).
- The queue, `reports/gate_b_2026-11-12/queue.sh`, runs as a systemd unit from a worktree pinned at
  this note's commit. It pauses r27 the way window 2's queue does: at the first save 10-20 updates
  past a gate. The pause is logged, nothing else runs on the GPU, and r27 resumes after the last
  step.
- About 30 machine-hours: generation about 26, distillation about 2.5, the play checks about 1.

**The generator G.**
- r27's `last.pt` at the pause, copied to `runs/gateb/gen.pt`, with its sha256 logged.
- v0 is r27's `v0.pt`.

**Generation.** `learner.py --eval-only` in chunks of 1,875 deals. Chunk k's command:
```
--run runs/gateb/gen_k --init G --eval-seat eval+search --eval-opponents snap:opp
--opp-ckpt G --search-root gumbel --search-m 16 --search-n 16 --search-record
--eval-set M21 --pool verified --infer-bf16 --workers 18 --slots 16 --groups 4
--eval-deals 1875 --eval-seed0 1000000+1875k
```
- The search runs on one seat, against G raw, both greedy. Every other setting is window 1's
  n = 16 point: act decisions and attack plans searched, horizon 1, greedy continuation, skip at
  0.97.
  - Searching both seats costs the same per target. But it gives half as many deals for the same
    300k, and deals are the unit of the held-out split.
  - Act decisions are recorded, as `search.target_record`.
- **Uniform worlds.** 192 registered that simulator worlds would not become the default "for the
  search or for gate B's generation" once its P7 failed, and P7 failed (192 §2, §7.1).
  - 195's audit, whatever it finds, leads to further tests at n = 64 and horizon 2 (195 §4), not
    to this generation.
- **Gate A on G.** Gate A was measured on u1000, not on G.
  - Chunk 0's own score (the searched G against G) must be at least 0.54: PLAN_CEILING §6.2's
    gate A bar, +0.04. Its standard error is about 0.005 at 1,875 deals.
  - Below 0.54, generation stops. Gate B is not run, r27 resumes, and the number goes to the
    owner.
- **Chunks.**
  - Chunks run in order until their shards hold 300,000 targets.
  - Window 1's fresh deals gave 9.4 targets per game, so about 9 chunks of about 2.9 hours.
  - A chunk that fails or hits its 4-hour cap keeps the shards it wrote, which hold whole games.
    The next chunk starts at the next seed block, so no seed block is played twice. A chunk dying
    loses its unsaved partial shard, at most 20,000 targets.

**Distillation.**
- `tools.selfplay.distill` at this commit: lr 3e-5, 4 epochs, minibatch 512, `--seed 0`,
  `--save-epochs`. The chunks' runs are given in order, so "the first n targets" are the earliest
  chunks' targets, extended to the end of their game.
- Four arms, over the same records:

| Arm | Rule | Sizes | Why |
|---|---|---|---|
| `se` | the mirror-descent step scaled by the standard error (PLAN_CEILING §6.2) | 100k, 300k | the gate |
| `placebo` | `se` with each record's per-option results permuted among its options (`--placebo`) | 300k | a control: the same structure without the information |
| `se1` | `se` on the first round's means only (§1.1) | 300k | free of the halving's selection |
| `sigma` | Gumbel MuZero's completed-Q target (PLAN_CEILING §3.2) | 300k | the other rule F1 could use |

- **The held-out split.** Every 20th deal, in the order deals first appear, is held out
  (`distill.split`). It serves the held-out KL and GB2 and never picks a network the gate reads.

**§1.1 The halving's selection** (the red team's finding).
- Under sequential halving each round draws fresh worlds, which only its surviving candidates
  play (`search.Searcher._halve`).
- A candidate that lost the first round has only that round's mean, and that mean was selected
  low. A survivor's mean adds fresh rounds. So `q` sets losers against survivors with a bias of
  its own, and the `se` step moves mass from first-round losers to survivors beyond what the
  evidence says.
- The halving's key weighs a result difference of 0.1 at about 2.6 logits (C_VISIT 50, C_SCALE
  1.0). So survivors are chosen mostly by their first round, not by the network's prior. The
  bias adds noise and exaggeration rather than a lean toward G's own choice.
- Decisions with two candidates play one round, all worlds shared, and carry no such bias.
- Since this commit each record also holds `q1` and `n1`, the means and counts over the first
  round's worlds alone, which every compared option played. `se1` is the step on those.
- `se` stays the gate's rule, as PLAN_CEILING §6.2 has it. The comparison between survivors, which
  decides most changes of the top choice, pools worlds both survivors played. `se1` measures what
  the selection adds.
- Also reported:
  - the share of records played in one round (`one_round`);
  - the mean of `q - q1` for first-round losers and for survivors.

**Choosing each arm's network by play, not by held-out KL.**
- Each arm's four trained epochs (at both sizes for `se`) play G on 500 deals, seeds
  970,000-970,499, 1,000 games each.
- The arm's network is the epoch with the highest score; a tie goes to the earlier epoch.
- Epoch 0 is not a candidate. The question is what training did, and the test says whether it
  helps.
- The epoch held-out KL would keep is reported beside it.

**The tests.**
- 1,000 fresh deals, seeds 980,000-980,999, each played with the seats swapped (2,000 games).
- M21, coherent, verified pool. Raw and greedy, with `--infer-bf16` as in every evaluation since
  183.
- Matches:
  - each arm's chosen network against G;
  - G and `se`'s chosen 300k network, each against v0. This checks that a gain is not an
    exploitation of G alone: the search plays G as its opponent's model, and the generation
    played G.
- Pairing: by deal with `tools.selfplay.paired` (bootstrap over deals).

**GB2** (`reports/gate_b_2026-11-12/agreement.py`, committed with this note).
- On the 300k held-out targets, which neither size trained on, the share where a network's top
  option is the search's pick. Computed for G and for `se`'s chosen networks at 100k and 300k.
- The difference 300k - 100k is paired by target, with a 95% interval from 2,000 bootstrap
  resamples of deals.
- It also reports the share of G's top choices each network changes.

**Also reported:**
- `distill.json`: the share of targets with no difference, the share that moves the policy, the
  one-round share;
- held-out KL by epoch;
- the per-chunk search statistics (searched, changed and clear decisions per game);
- every arm's epochs on the 500 selection deals.

## 2. Gate and predictions

| # | Measure | Gate | Prediction |
|---|---|---|---|
| A_G | Chunk 0: the searched G against G | at least 0.54 to go on | 0.54-0.57 (u1000: 0.555) |
| GB1 | `se`'s 300k network against G | at least 0.515 (E3's bar: a gain of +0.015) | 0.500-0.525, most likely about 0.510 |
| GB1c | `se`'s 300k network minus `placebo`'s, paired by deal | the 95% lower bound above 0 | — (`placebo` against G: 0.495-0.505) |
| GB2 | Agreement on the held-out targets, 300k - 100k | the 95% lower bound above 0 | +0.002 to +0.015 |
| GB3 | Targets with no difference in result | — | 0.12-0.20 (u1000: 0.160) |
| GB4 | `se1`'s 300k network against G | — | within ±0.010 of `se`'s |
| GB5 | Against v0: `se`'s 300k network minus G, paired by deal | — | at least 0, within 0.01 of GB1's gain |
| GB6 | `sigma`'s 300k network against G | — | at or above `se`'s: its target moves further |

**Gate B passes when A_G, GB1, GB1c and GB2 all hold.**

**The statistics.**
- Matches between near-identical networks are tight. E3's distilled networks against their
  generator had 95% half-widths of about 0.012 at 450 deals (186 §5), so the standard error here
  is about 0.004 at 1,000 deals.
- With the bar at 0.515:
  - a true gain of 0 passes with probability about 0.0001;
  - +0.010 passes about 10% of the time;
  - +0.020 about 90%.
- I put passing at about 30%: my uncertainty about the gain is wider than the test's.

**Why GB1 is likely to miss, but not by much.**
- The search at n = 16 adds +0.055 on u1000.
- About 80% of the decisions it changes are act decisions, and only those are recorded. Across
  window 1's n = 16 variants it was 78-85%: 905 of 1,121 changes with simulator worlds (NUMBERS,
  WINDOW 1 N5).
- The `se` step moves a target's log-odds by at most 0.5 per standard error. Candidates differ by
  about 0.8 standard errors (192 §7.1), so a target moves pi by a few tenths of a logit and seldom
  flips the top choice.
- E3's trained epochs changed 2.6-3.4% of greedy choices and gained nothing measurable.
- Here many more targets carry a clear correction. A gain of about +0.01 is my best guess:
  positive, and on the edge of the bar.

## 3. What each outcome means

- **A_G fails.** The search does not clearly beat r27's network, so F1's premise fails at r27's
  level. The number goes to the owner, F1 is not run, and r27 resumes.
- **Gate B passes.** F1 runs (PLAN_CEILING §6.3-§6.4).
  - The loop is built next: self-play with search on both seats, the shared-memory replay buffer
    and the fixed replay ratio.
  - It is pre-registered with the 48-hour check. Whether it starts from G or from `se`'s 300k
    network, and with which rule, is settled there with GB4 and GB6 in hand.
  - If GB5 is below 0 with its upper bound under 0, the gain is mostly an exploitation of G, and
    F1's games need opponents other than itself.
- **GB1 passes and GB1c fails.** The placebo gains as much: the gain comes from the fine-tuning,
  not from the search's information. F1 is not run, and the artefact is reported.
- **GB1 passes and GB2 fails.** The network plays G better without agreeing more with the search
  at 300k than at 100k. The gate fails as written, and the case goes to the owner with GB1c and
  GB5.
- **GB2 passes and GB1 fails.** The network learns the search's picks, but at 300k too little to
  show in play.
  - By PLAN_CEILING, F1 is not run. The difficult opponents are the learner's own versions plus
    searched anchors at n = 4.
  - The owner decides whether 1M targets, about 51 more machine-hours, is worth it. If GB4 or GB6
    passes 0.515 with its lower bound above 0.5, that number goes with the report.
- **Both fail.** The corrections do not generalise at this scale, E3's outcome on a different
  signal. F1 is not run. The epochs on the selection deals say whether training moved play at
  all.

## 4. Before the run

- The tools at this commit:
  - `search.target_record` writes `q1` and `n1`;
  - `distill.py` has the rules `se`, `se1` and `sigma`, `--placebo`, `--seed` and
    `--save-epochs`, and the split function `split`;
  - `agreement.py`.
  - Tests: `test_gumbel_halving_spends_its_budget_on_shared_worlds`,
    `test_the_search_answers_instant_speed_decisions` and
    `test_distilling_search_targets_moves_the_network_toward_the_better_move`.
- **The queue's CPU smoke passed** (2026-11-12 08:25-08:37, beside r27, which it never touched:
  `PAUSE=0`).
  - Settings: G = r27's `v0.pt`; chunks of one deal at n = 2; sizes 20 and 40; one deal each for
    the selection and the tests; `AG_MIN=0`.
  - Every step exited 0:
    - two chunks wrote 28 and 16 targets, and generation stopped at 44 against 40;
    - A_G read 0.5;
    - all four arms distilled, and the placebo is flagged in its `distill.json`;
    - every epoch played, and the ties went to epoch 1;
    - all seven tests ran;
    - `agreement.py` wrote `gb2.json`;
    - `paired.py` paired the tests.
  - The shards hold `q1` and `n1`. At n = 2 every decision has at most two candidates, so all
    were one round with `q1 = q`. The several-round case is the unit test's
    (`test_gumbel_halving_spends_its_budget_on_shared_worlds`, on `_halve` itself).

## 5. The red team's findings and what changed (2026-11-12, before any data)

| Finding | Change |
|---|---|
| BLOCKER: the kept network was still chosen by E3's rule (lowest held-out KL, epoch 0 included) | each arm's network is chosen by play among its trained epochs on separate deals, then tested once on fresh ones; the KL pick is reported beside it |
| BLOCKER: nothing checked that the search beats G; the draft could switch to simulator worlds against 192's registration | uniform worlds; chunk 0 is gate A on G (A_G) |
| GB2 had no code, and its held-out targets also chose the epochs | `agreement.py` before the run; the gate's networks are chosen on separate deals, so the held-out targets choose nothing |
| No control for a gain from the fine-tuning itself or from exploiting G; no seed | the `placebo` arm and GB1c; GB5 against v0; `--seed 0` |
| The halving's selection biases `q` | `q1`/`n1` recorded; `se1` arm; one-round share and the inflation reported (§1.1) |
| Commands lacked `--run`, carried a flag evaluations ignore, and mixed fp32 and bf16 | fixed; `--infer-bf16` throughout |
| The standard errors were wrong (450 deals give about 0.006 for near-identical networks, not 0.01) | corrected, and the pass probabilities with them |
| 9.4 targets per game on fresh deals, so about 9 chunks; nothing said what a capped chunk does | corrected; a capped chunk keeps its shards and is not rerun |

## 6. The timing, moved before any data (2026-11-12 07:55)

**Gate B starts after r27's read at update 500, about 2026-11-13 midday, not after the read at
1,000.**
- Gate B asks whether distilling the search makes a network stronger. That question does not need
  r27's network at 1,000: chunk 0 checks gate A on whatever network G is.
- The answer comes about a day sooner, and F1, the plan's critical path, starts sooner if it
  passes.
- r27 loses nothing it registered. Its reads go by update count (191 §6), so the pause only moves
  the read at 1,000 later.
- Window 2's results (194, 195, 193) are read before gate B starts. If any of them changes gate B's
  design, the change is appended here before the run.

## 7. The bug hunt's changes, before any data (2026-11-12 ~14:00; KNOWLEDGE/2026-11-12/197)

A bug hunt went through gate B's whole pipeline before the run. Nothing of gate B has run, so
this section changes the run, and §1-§6 stand where it does not. **The worktree is pinned at
3c718a0, or at the later commit that records this section, not at cc6d833.**

**The queue** (`reports/gate_b_2026-11-12/queue.sh`). Its control flow failed in ways that
would have produced plausible numbers from the wrong run:
- **`--groups ${GROUPS:-4}`.** `GROUPS` is a bash builtin holding the user's group id, so
  production would have passed `--groups 1000` (16 groups of one slot, never measured). The old
  smoke set `GROUPS=1` itself and so never saw this. Now `--groups 4`, as registered.
- **A_G.** A restart after chunk 0 began skipped A_G for good. A_G is now its own saved verdict.
  An interrupted chunk 0 is set aside unread and played again, and no other chunk runs before
  A_G is read and passes.
- **Failed steps.** A failed or capped step no longer lets its dependants run. A distillation
  capped after two epochs would otherwise have been "the best of four" chosen among two.
  Required steps stop the queue, log it, and give the GPU back to r27.
- **Sizes.** A generation short of 300,000 targets stops the queue. It would otherwise have
  produced networks named 300000.
- **Restarts.** A lock and the commit that began the run guard a restart, and r27 is paused at
  any restart that finds it running.
- **H1′.** 192 §7.6's H1′ runs at the end: u1000 against the heuristic on `heur_raw`'s 300
  deals, once in bf16 and once in fp32, both at this commit. It is not required for gate B.

**The targets and the distillation.**
- `distill.improved` pooled each option's variance over n, not over its degrees of freedom.
  Sequential halving gives first-round losers one world each, which shrank the pooled variance
  to 0.73 of the unbiased one on window 1's n = 16 records. Steps were 9% larger on average, so
  the targets broke §2's "at most 0.5 per standard error". The variance is now pooled unbiased:
  the sum of n × var over the sum of (n − 1).
- `se1` leaves a record unmoved when an option has no first-round world, instead of silently
  reading all of its rounds.
- `--seed` now fixes the minibatches as well as the dropout: `ppo.chunks` takes the run's
  generator.
- `distill.json` reports §1.1's mean of q − q1 for first-round losers and survivors, which no
  code computed before.
- Target shards are written whole: a stop during a write left a shard cut short, and every arm
  would have crashed on it.
- G's description ran with name dropout on. `model.load` now returns eval mode.

**The engine.** Three fixes change rare game situations:
- a turn ended in the end step now ends at once (CR 724.1);
- the trigger-loop tripwire now guards the game loop too;
- a multi-target counterspell no longer crashes when its target was removed (CR 608.2b).

So G plays a slightly different game in those situations than r27 trained on. Chunk 0's A_G
gates G on this engine.

**Two premises of §2, corrected.**
- **"Seldom flips the top choice" was wrong.** On window 1's 11,740 records at n = 16, the `se`
  target's top option differs from the network's in 13.9% of records. By menu size: 2.0% with
  2 options, 18.4% with 4 and 28.1% with 6, close to the search's own 15-17% rate of changed
  moves. That rate is itself inflated by copies, which the next point explains.
- **The search treats copies of a card as distinct moves.** Window 2's audit found two Forests in
  hand counted as two candidates. Their means differ only by noise, and 65% of the search's
  changed moves there were swaps to an equal-prior copy. Targets can move mass between copies.
  The network cannot tell identical tokens apart, so that part of the loss is noise it cannot
  fit, not a wrong lesson. Gate B runs the search as registered. Collapsing copies is a search
  change to measure on its own first (BACKLOG).

**The smoke, redone.** The 08:25 smoke trained nothing:
- one deal a chunk, and the first deal is held out, so the size-20 arm had 0 training records;
- it also set `GROUPS=1`.

The new smoke ran end to end and exited 0. G was r27's `v0.pt` on the CPU, with 2 deals a chunk
at n = 2, sizes 30 and 60, `AG_MIN=0`, and one deal each for selection, the tests and H1′.
- Generation reached 107 targets in two chunks.
- A_G read 0.5.
- Size 30 trained on 16 records and size 60 on 40, with 28 held out.
- Every arm's four epochs played, and all seven tests ran.
- `gb2.json` was written, both H1′ twins played, and the log ends "gateb done".
- Mock runs covered every restart path:
  - a stop during chunk 0, then a restart;
  - A_G below the bar;
  - a capped distillation;
  - a short generation;
  - a second queue on the same directory.

## 8. The training run is r28, on the fixed trainer (2026-11-12 ~16:45, before any data)

r27 ended at update 165: its mulligan ran away because every optimizer step was one stratum of
decision length (KNOWLEDGE/2026-11-12/198). Its successor r28 (199) runs from r27's v1 on the
fixed trainer. Gate B had not started, and nothing of its protocol, gates or predictions changes.
What changes:
- **The training run.** The queue pauses r28 and takes G from r28's `last.pt` at the pause.
  - r28 runs as a transient unit, so a stop removes it. The queue resumes it with
    `reports/r28_2026-11-12/start.sh`.
  - v0, GB5's fixed reference, stays r27's `v0.pt`, as §1 registered. It is not G and not in
    r28's opponents.
- **The pin moves** from b73d562 to the commit that holds this section. Distillation
  (`distill.ce_epoch`) then takes stratified steps (198 §4), as every training loop does. At
  b73d562 each optimizer step would have been one length stratum, the defect behind r27's
  runaway.
- **When.** After r28's read at update 400. `reports/gate_b_2026-11-12/starter.sh`, as the
  transient unit `mtg-gateb-starter`, starts the queue once r28 passes update 405. That is about
  20 hours after r28's launch (2026-11-12 16:32), so about 2026-11-13 13:00. r28's reads go by
  update count, so the pause changes nothing in them.
- H1′ (u1000 against the heuristic) and 195's confirming audit (u1000) do not involve the
  training run and are unchanged.

## 9. A decision at r28's read at 400, not an automatic start (2026-11-12 ~18:15, before any data)

The red team (PLAN_CEILING §15) found that gate B would commit about 34 machine-hours by itself,
though by this plan's own numbers its best case does not beat PPO's rate:
- one round earns 0.25-0.35 Elo per machine-hour at GB1's bar (0.515, about +10 Elo, over about
  30 hours);
- PPO's late rate was 1-2 Elo per hour (r26), and r27 gained +37 in its first 3.6 hours.

**The starter is removed** (`mtg-gateb-starter` stopped at 18:10). If nobody decides, r28 keeps
training, so the GPU is not idle.

**The rule, applied at r28's registered read at 400:**
1. **r28's rate.**
   - Its newest frozen version's Elo less its v0's, from its ladder's last fit, divided by the
     machine-hours from r28's launch to that freeze, pauses excluded.
   - With no freeze after v0, the rate is 0.
2. **The break-even GB1.**
   - The rate times 30 hours is the Elo PPO would gain meanwhile; s* = 1 / (1 + 10^(-Elo/400))
     is the gate score that matches it.
   - **Generation runs only if s* is 0.53 or less.** Otherwise only H1′ and 195's confirming
     audit run (about 2 hours), and r28 resumes.
3. **Before it runs:**
   - **a futility look:** after 100k targets, the `se` arm is distilled at 100k and GB2 is read.
     If its agreement gain over G has a 95% lower bound at or below 0, generation stops and gate
     B is read as failed at 100k;
   - the queue's CPU smoke is re-run on the final pin, since `distill.ce_epoch` moved to
     `ppo.steps` after the last smoke;
   - the pin and the commit are registered here.
4. **F1's 48-hour check** (PLAN_CEILING §6.2) compares against r28's rate from step 1, not r27's,
   which was the mulligan defect's stall.

H1′ and 195's confirming audit do not depend on gate B. They can run in any GPU window, and they
take the first one if gate B does not run.
