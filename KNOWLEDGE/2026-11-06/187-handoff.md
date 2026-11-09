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
- **E1 passes (2026-11-08 20:05):** A at look 8, B*_FP 2.17M [1.43M, 4.54M] (bar 2.65M), placebo z
  -0.77; B failed at look 2 (28.8M). C runs (`runs/labels/e1_C.2`); its result is a measurement, since
  A's pass fixes E3's configuration as A. Recorded in NUMBERS and the labels note §2. Only a greedy
  configuration passed, so PLAN §14.1 (greedy playouts) goes to the owner. Correction: this note said
  on 2026-11-06 that A had stopped at 22:37; it had not (a process listing cut short by `head`).
- Generator `runs/selfplay/r23_mulligan/gen.pt` (pinned): r20 v2 plus 31 PPO updates against the
  heuristic; mulligan rate 0.50 -> ~0.003; greedy 0.0475 below r20 v2 against the heuristic.

## The queue
`tools/selfplay/experiments/phase0_queue.py` on `phase0/labels`, run by the user services
`mtg-phase0@sim` and `mtg-phase0@labels` (`~/.config/systemd/user/mtg-phase0@.service`; enabled, so a
reboot resumes them; a step leaves `runs/phase0/<lane>/<step>.done`, a failed one `.failed`).
- sim lane: E0's measurements (done or nearly: bench, eval, score, consistency, next card, epochs).
- labels lane, two 10-worker label jobs at a time: E1 A's extension beside B, C when the first ends;
  E3 on the configuration the rule in 186 §5 fixes (`runs/phase0/e3_config.json`): labels to 100k
  beside 2,000 regret positions (k 8, d 4), distillation at 10k/30k/100k, regret, gain (900 games);
  then label scaling (exploratory, 186 §5): two label jobs (seeds 35M+ and 36M+), distilled and
  measured at 300k, 600k and 1M. The lane started on a one-job-after-another driver; the transient
  unit `mtg-phase0-switch` restarts it on the two-job driver (5312778) once E1 A and B have ended (the
  run worktree is already at that commit, so a reboot also picks it up).
- Watch: `tail -n 20 runs/phase0/labels.log runs/phase0/sim.log`; E1 looks in `runs/phase0/e1_<cfg>.looks`;
  label jobs in `runs/labels/<job>.out` (`label_progress` lines); `systemctl --user status mtg-phase0@labels`.
- Stop: `systemctl --user stop mtg-phase0@labels` (stops its label jobs too; they flush on SIGTERM).
  Restart: `systemctl --user start mtg-phase0@labels` (resumes at the first undone step). For good:
  `systemctl --user disable --now mtg-phase0@sim mtg-phase0@labels`.
- Rough timing (each job ~1,000 forward passes a second): E1 A and B end by about 20:30 on 11-08 (B
  earlier if its fail rule fires), C about 3 h later; E3 2-8 h by configuration; label scaling then
  runs until stopped (about 8 h to 300k labels with two jobs).
- The owner offered handing monitoring to `agy` (Antigravity CLI); not needed for the machine to stay
  busy (the services restart themselves). The bookkeeping below waits for an agent.

## Tasks, in order
1. **E0: done** (2026-11-08): recorded (NUMBERS, the simulator note §4), window and yardstick
   removed, merged into main at dd1e43f (gates green, replay digests identical over 200 games), branch,
   worktrees and the sim service removed.
2. **E1: A and B recorded.** When C ends (`runs/phase0/e1_C.looks`, last line = its verdict), record
   it in the labels note §2 and NUMBERS beside A and B.
3. **E3: scored, it fails (2026-11-08 22:47) — STOP for the owner.** NUMBERS and the labels note §5
   hold the verdict and an exploratory diagnostic: the distiller kept the generator (every trained
   epoch fit held-out targets worse); trained epochs cut regret by up to 3.6% [0.932, 0.994], with no
   measurable gain over 900 games. The kill rule (PLAN §12): search at play time only, and PPO as the
   learner. For the owner: the kill, §14.1 (greedy playouts), and whether the label-scaling results
   (task 4) change the picture.
4. **Label scaling** (exploratory; amended before any of its distillations ran: every epoch saved and
   measured): results in `runs/phase0/regret_<n>.json` and `runs/selfplay/scale_gain_<n>_ep<e>/` for
   n = 300k (about 07:45 on 11-09), 600k (about 21:00), 1M (11-10). Record them as exploratory.
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
**Phase 0, 2026-11-08 (for the owner).**
- **E0, the opponent simulator: passes.** It reads the opponent's hand 11% better than a deck-aware
  prior (18% late in the game), with honest probabilities; its picture of the library is no better
  than the prior's. Merged into main.
- **E1, the label signal: passes, narrowly.** A playout label buys a useful gradient step for 2.17M
  forward passes, 2.4x cheaper than outcome-only PPO; only greedy playouts pass (PLAN §14.1 is yours).
- **E3, distillation: fails.** One round of training on 100k labels changes 3% of the network's
  choices and makes them slightly better (3.6% less regret), far too little to win more games;
  the pre-registered epoch rule even kept the untrained network. The plan's kill rule says: search at
  play time only, and PPO as the learner.
- **Open for the owner:** accept the kill, or revise the distillation (pick epochs by regret rather
  than held-out fit; a smaller step per PLAN §1.4 and 186 §3; more labels). The label-scaling runs
  (300k on 11-09 morning, then 600k, 1M) show whether more labels make the effect matter.
(later results are appended below)
- **Label scaling, 300k (11-09 07:21):** tripling the labels left the effect unchanged: 2-4% less
  regret, no measurable gain (each of four epochs within +-0.013 of zero over 900 games). More labels
  alone do not rescue this distillation; the 600k and 1M points follow (11-09 evening, 11-10).
