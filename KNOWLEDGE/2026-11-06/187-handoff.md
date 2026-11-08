# 187 — Handoff: Phase 0 runs unattended (updated 2026-11-08 17:30)

For the next agent. The owner asked (2026-11-08) that the Spark not idle until they return, so
Phase 0's remaining pre-registered steps run from an unattended queue (two user services). Your work
is mechanical: watch the queue, record and score its results exactly as pre-registered, merge what
is scored. **Do not design or redesign anything.** At every point marked STOP, write what you found
under "Outcome" below, commit, push, and stop for the owner.

## Read first
1. `CLAUDE.md` (git, checkpoint and memory rules) and `KNOWLEDGE/OWNER_PREFERENCES.md`.
2. `docs/PLAN_LEARNING.md`: the summary, §12 (the gates) and §13. Decisions `docs/DECISIONS.md` D20, D6.
3. The Phase 0 notes, on their branches: `git show origin/phase0/labels:KNOWLEDGE/2026-11-06/186-phase0-labels.md`
   (§2 E1 and its look 4; §5 E3's pre-registration, committed before any E3 label) and
   `git show origin/phase0/simulator:KNOWLEDGE/2026-11-06/186-phase0-simulator.md`.
4. Why the plan exists: `KNOWLEDGE/2026-11-05/184-bug-hunt-verified-pool-cleanup.md` §22-27.

## State (2026-11-08 17:30)
- `main`: all gates green, baseline B4 in CLAUDE.md. Branches (pushed, unmerged), with worktrees:
  `phase0/labels` (`../MTG_AI-labels`). Run worktrees (detached, pinned; nobody edits them):
  `../MTG_AI-labels-run` (the labels branch at the queue's commit), `../MTG_AI-run` (main's training
  runs; idle). `phase0/simulator` is merged (dd1e43f).
- **E0 is scored: it passes** (the no-window arm; the event window adds 0.1%, so it is not kept):
  hand NLL / yardstick 0.889 [0.886, 0.892] overall (G1 <= 1), 0.883 [0.879, 0.886] mid-game turns
  7-12 (G2 <= 0.95), 0.975 early, 0.821 late; ECE 0.0004 (G3 < 0.05; top-24 0.0025; yardstick 0.0034);
  library NLL given the true hand 1.012x the yardstick's (context, not gated). Costs on the trained
  model, quiet GPU (`runs/phase0/e0_bench_nowin.json`): belief 4.3 ms (batch 1), 10.8 ms (128
  decisions); 1 hand 22 ms, 32 hands 26 ms; hand + library + next 3-5 cards 241 ms (1 world), 403 ms
  (32 worlds; the library decoder is ~49 sequential steps); hand + next 3-5 from the marginal head's
  counts 26-31 ms. Files: `runs/phase0/e0_*.json`.
- **E1 A, look 4 (2026-11-06 23:01): gray** (B*_FP 4.36M [2.31M, 39.5M], placebo z -0.16), so the
  pre-registered extension runs: four more looks to 21.2M forward passes, then the point estimate
  decides. Correction: this note said on 2026-11-06 that A had stopped at 22:37 with 9.07M; that was
  wrong (a process listing cut short by `head`). A ran to its budget and its watcher scored look 4.
- Generator `runs/selfplay/r23_mulligan/gen.pt` (pinned): r20 v2 plus 31 PPO updates against the
  heuristic; mulligan rate 0.50 -> ~0.003; greedy 0.0475 below r20 v2 against the heuristic.

## The queue
`tools/selfplay/experiments/phase0_queue.py` on `phase0/labels`, run by the user services
`mtg-phase0@sim` and `mtg-phase0@labels` (`~/.config/systemd/user/mtg-phase0@.service`; enabled, so a
reboot resumes them; a step leaves `runs/phase0/<lane>/<step>.done`, a failed one `.failed`).
- sim lane: E0's measurements (done or nearly: bench, eval, score, consistency, next card, epochs).
- labels lane, in order: E1 A's extension beside E1 B (two 10-worker jobs), then E1 C; E3 on the
  configuration the rule in 186 §5 fixes (`runs/phase0/e3_config.json`): labels to 100k, 2,000 regret
  positions (k 8, d 4), distillation at 10k/30k/100k, regret, gain (900 games); then label scaling
  (exploratory, 186 §5): more labels distilled and measured at 300k, 600k and 1M.
- Watch: `tail -n 20 runs/phase0/labels.log runs/phase0/sim.log`; E1 looks in `runs/phase0/e1_<cfg>.looks`;
  label jobs in `runs/labels/<job>.out` (`label_progress` lines); `systemctl --user status mtg-phase0@labels`.
- Stop: `systemctl --user stop mtg-phase0@labels` (stops its label jobs too; they flush on SIGTERM).
  Restart: `systemctl --user start mtg-phase0@labels` (resumes at the first undone step). For good:
  `systemctl --user disable --now mtg-phase0@sim mtg-phase0@labels`.
- Rough timing: E1 A and B about 4 h from 17:25, C about 3 h, E3 3-10 h by configuration; label
  scaling then runs until stopped (about 17 h to 300k labels).

## Tasks, in order
1. **E0: done** (2026-11-08): recorded (NUMBERS, the simulator note §4), window and yardstick
   removed, merged into main at dd1e43f (gates green, replay digests identical over 200 games), branch,
   worktrees and the sim service removed.
2. **E1**, as each configuration ends (`runs/phase0/e1_<cfg>.looks`, last line = verdict): record it
   in the labels note §2 and NUMBERS. E1 passes when a configuration passes. If none passes, the kill
   rule stands: record it and STOP for the owner on that point (the fallback, slow outcome PPO plus
   throughput work, is the owner's call); the queue still runs E3 as a measurement (186 §5).
3. **E3**, when the queue's `e3_gain` step is done: score it as 186 §5 says: regret from
   `runs/phase0/e3_regret.json` (the 100k apprentice's ratio, one-sided 95% bound <= 0.8), gain from
   the eval in `runs/selfplay/e3_gain/` (score - 0.5 >= +0.015 over the 450 pairs). Check the
   predictions in §5. A known issue, the owner's call: the plan's eta (1.61 at A's look 4) is near
   hard labels (186 §3). If E3 fails, record it and STOP.
4. **Label scaling** results (`runs/phase0/regret_<n>.json`, `runs/selfplay/scale_gain_<n>/`): record
   them as exploratory, not gates.
5. **Merge** each branch once its gates are scored, pass or fail (the code is tested either way): merge
   into main and run the three gates on the merge; where the branch claims play is unchanged, compare
   `python -m tools.replay_digest 100` run from main and from the branch; push, check with `git fetch`,
   then delete the branch, remote branch and worktree. Do not touch `phase0/labels` or its run worktree
   while the queue runs (it runs from them); merge it after the queue is stopped. Delete
   `tools/selfplay/experiments/` once its numbers are recorded (OWNER_PREFERENCES #2), and remove the
   two services (`systemctl --user disable --now ...`, delete the unit file). Pin in
   `reports/LARGE_FILES.sha256` any checkpoint a recorded number cites.
6. Write the owner a plain-language summary under "Outcome": each gate's verdict with its numbers and
   what it means for the plan. Commit and push.

## Rules that bite
- Commit and push to main after each coherent piece; check the push with `git fetch` (GitHub SSH is
  intermittent: retry). Never commit a checkpoint. Never prune a pinned or cited checkpoint.
- Never use bare `git stash`. Never `pkill -f` a pattern that matches your own shell; stop the queue
  with systemctl, not by killing its processes.
- No network may read the true hidden state (D20 guards; the leak tests on both branches).
- IDE (Pyright) diagnostics are noise from other checkouts; trust pytest and ruff.
- The owner's decisions in force: D20 as amended, no privileged critic ever, two players only, nothing
  hardcoded about opponents (the deck-consistent sampler is a yardstick only), memory starts as the
  public history table. Open owner questions: PLAN_LEARNING §14.

## Outcome
(the next agent appends here)
