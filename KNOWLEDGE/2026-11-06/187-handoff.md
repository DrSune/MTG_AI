# 187 — Handoff (2026-11-06, evening): finish Phase 0's measurements

For the next agent. The work left is mechanical: watch the running experiments, score their gates
exactly as pre-registered, record the numbers, merge what is scored. **Do not design or redesign
anything.** At every point marked STOP, write what you found under "Outcome" below, commit, push,
and stop for the owner.

## Read first
1. `CLAUDE.md` (git, checkpoint and memory rules) and `KNOWLEDGE/OWNER_PREFERENCES.md`.
2. `docs/PLAN_LEARNING.md`: the summary, §12 (the gates) and §13. Decisions `docs/DECISIONS.md` D20, D6.
3. The two Phase 0 state notes, on their branches (each has a hand-over section with exact commands):
   - `git show origin/phase0/labels:KNOWLEDGE/2026-11-06/186-phase0-labels.md` (its §4);
   - `git show origin/phase0/simulator:KNOWLEDGE/2026-11-06/186-phase0-simulator.md` (its §3).
4. Why the plan exists: `KNOWLEDGE/2026-11-05/184-bug-hunt-verified-pool-cleanup.md` §22-27.

## State at handoff
- `main` 0660d66 (+ this note): all gates green, baseline B4 in CLAUDE.md (pytest MTG_bot 5091
  passed / 39 deselected / 71 subtests; pytest tools 139; tools/run_scenarios.py 738/738).
- Branches (pushed, unmerged), each with its own worktree:
  - `phase0/labels` f442360, worktree `../MTG_AI-labels`: the true-future labeller (`search.Labeller`),
    the actor's `label` job, 6 tests (`tools/selfplay/test_labels.py`), experiment scripts in
    `tools/selfplay/experiments/`. Generator `runs/selfplay/r23_mulligan/gen.pt` (pinned): r20 v2 plus 31
    PPO updates against the heuristic; mulligan rate 0.50 -> ~0.003; greedy play 0.0475 below r20 v2
    against the heuristic.
  - `phase0/simulator` 75ae5aa, worktree `../MTG_AI-sim`: capture (`actor.Capture`, `learner --capture`),
    `features.sim_view`, `tools/selfplay/simulator.py` (network, decoders, marginal head, yardstick,
    train, eval), 5 tests incl. a leak test; data: 40,000 games, 1,388,124 positions (54,886 held out).
- `../MTG_AI-run`: detached worktree pinned for training runs (docs/TRAINING_REVIEW_PROTOCOL §1); no run
  is active.
- Running when this was written (they stop on their own; do not kill them unless memory drops below
  15 GB available):
  - E1 configuration A: output `runs/labels/e1_A/`, progress `runs/labels/e1_A.looks`; its watcher stops
    it by 10.6M forward passes (~23:00). Look 2: 17,374 labels, B* 3.07M forward passes [1.59M, 45.6M],
    signal z 2.14, placebo z 0.30 (the gate is B* <= 2.65M and placebo z < 2: borderline).
  - E0 training, two arms under `runs/simulator/`: PIDs 1993685 (no event window, ~22:30) and 1993686
    (event window, ~22:45). Timings so far: capture 435 positions/s at 10 workers; 33-37 min per epoch,
    8 GB RSS.

## Monitoring
- Processes: `ps -eo pid,etime,args | grep -E "[l]abel_run|[s]imulator|[l]earner" | grep -v bash`
- Memory: `free -g` (keep at least 15 GB available; heavy jobs under `nice -n 10`).
- Progress: `tail -3 runs/labels/e1_A.looks`; the simulator note's §3 commands.

## Tasks, in order
1. **E0.** When both training arms end, run `simulator eval` on each and then
   `tools/selfplay/experiments/e0_score_e0.py`, as the simulator note §3 says. Score the gate exactly as
   pre-registered there (and PLAN_LEARNING §12: hand NLL at most the yardstick's and at least 5% lower by
   mid-game; per-card calibration error < 0.05; the event window kept only if it adds at least 5%).
   Re-measure the inference costs on the trained model with the GPU idle (the earlier figures came from
   an untrained model on a busy GPU). Record every number with its command in `KNOWLEDGE/NUMBERS.md` and
   the note. If the gate fails, the plan allows one retry on 4M positions; after that, STOP.
2. **E1.** When configuration A's watcher stops, score it as the labels note §4 says (gate: B*_label
   <= 2.65M forward passes and placebo z < 2; one pre-registered extension allowed). Then run
   configurations B and C as pre-registered, and score them the same way. Record everything.
   - If E1 fails its gate (the kill rule): record it and STOP. The fallback (slow outcome PPO plus
     throughput work; the owner ruled out a privileged critic) is the owner's call to start.
3. **E3**, only if E1 passes: run it as the labels note says and score it. Known issue, a judgement call:
   the plan's eta rule (0.5 log-odds per standard error) is too large for distillation to converge in
   the owner's 45/30/25 example (labels note §3). Do not change the rule yourself: run E3 as
   pre-registered, record the issue, and STOP if E3 fails because of it. Cost: a label is ~300 forward
   passes, so 100k labels take ~8 hours.
4. **Merge** each branch once its gates are scored, pass or fail (the code is tested either way):
   - merge into main and run the three gates on the merge;
   - where the branch claims play is unchanged, compare `python -m tools.replay_digest 100` run from main
     and from the branch (it imports the code of the directory it runs in);
   - push, verify with `git fetch`, then delete the branch, remote branch and worktree;
   - delete `tools/selfplay/experiments/` once its numbers are recorded (OWNER_PREFERENCES #2);
   - pin in `reports/LARGE_FILES.sha256` any checkpoint a recorded number cites.
5. Write the owner a plain-language summary under "Outcome": each gate's verdict with its numbers and
   what it means for the plan. Commit and push.

## Rules that bite
- Commit and push to main after each coherent piece; check the push with `git fetch` (GitHub SSH is
  intermittent: retry). Never commit a checkpoint. Never prune a pinned or cited checkpoint.
- Never use bare `git stash`. Never `pkill -f` a pattern that matches your own shell.
- No network may read the true hidden state (D20 guards; the leak tests on both branches).
- IDE (Pyright) diagnostics are noise from other checkouts; trust pytest and ruff.
- The owner's decisions in force: D20 as amended, no privileged critic ever, two players only, nothing
  hardcoded about opponents (the deck-consistent sampler is a yardstick only), memory starts as the
  public history table. Open owner questions: PLAN_LEARNING §14.

## Outcome
(the next agent appends here)
