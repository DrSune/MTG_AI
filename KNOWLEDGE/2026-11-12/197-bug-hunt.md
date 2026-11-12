# 197 — The bug hunt of 2026-11-12: the causes behind the bugs, and the fixes

**The request** (the owner, 2026-11-12): "Do a bug hunting round. Dont fix them instantly, be
thorough so you can see deeper causes rather than symptom fix the bugs. And do routine
maintenance and Cleanup".

**How it was done.**
- Six hunters worked in parallel. They were read-only, used only the CPU, and their briefs did
  not suggest what they would find. Each had one area:
  - gate B's pipeline;
  - the PPO training path;
  - hidden information;
  - the evaluation statistics;
  - window 2's scoring;
  - the priority engine.
- I read the cited code for every finding before listing it. Most were also reproduced by the
  hunters, with repros in the session's scratch `hunt/`.
- Findings were grouped by cause before anything was fixed. Each fix comes with a test or a pack,
  which fails on the old code where that was practical.
- All six hunts found the core sound:
  - the training data per decision: action index, log-prob, mask, return, seat, and no opponent
    rows;
  - the deal seeds: no overlap between training, selection, test and gates;
  - the gate interval and the Elo fit;
  - the held-out splits;
  - the encoding: no hidden card reaches the network, and permuting the opponent's hidden cards
    changed no search result;
  - the engine's determinism and fork-resume equivalence: 320 forks, 0 mismatches.
- About 590,000 priority points under invariant checks gave no violation. Every defect below sits
  around that core.

## 1. The causes, each with its findings and its fix

### C1. A run's durable state had no commit point

last.pt, state.pkl, v<k>.pt, best.pt and three append-only logs were written independently, and
last.pt was written in place.

**What went wrong:**
- **A torn checkpoint.** A SIGTERM 0.05-0.2 s into a save left last.pt unloadable (reproduced).
  The unit would fail to resume six times and give up.
- **Freezes lost on a crash.** A freeze wrote v<k>.pt and logged at once, but the state only
  reached state.pkl at the next save, every 5 updates. A crash in between orphaned the version:
  the next freeze reused its name and overwrote the file.
- **Ladders lost on a resume.** A new version's ladder is always running at the next save, so a
  resume dropped it for good (reproduced: v1 never rated). A gate running at a save was lost the
  same way.
- **Replayed deals.** Games issued after a save were issued again on resume with the same seeds,
  and logged twice in train_rows.
- **A torn target shard** crashed every gate-B arm; capture shards were written the same way.

**The fix** (commit 9aed39e):
- `model.atomic_write` writes every checkpoint and shard whole or not at all.
- last.pt carries the run state, so the weights and the state are one commit. state.pkl is the
  scripts' copy, written second.
- A passed gate freezes, queues the ladder, writes best.pt, commits, and only then logs.
- The running evaluation's spec is part of the state.
- A resume continues job ids past every game already logged.
- Test: `test_a_freeze_is_committed_at_once_and_best_is_the_gated_snapshot`, which includes the
  resume.

### C2. One rule, several copies, drifted apart

**The copies and how they drifted:**
- **What a row scores** had five copies: `eval_summary`, `_eval_rows_as_games`, `paired._load`,
  `rate.games` and `ncurve.point`. rate and ncurve dropped a void game but kept its seat-swapped
  partner, and counted a re-run step's rows twice.
- **Who a player is** had three copies: rate.member, ncurve.SAME and the learner's version names.
  - rate merged every n = 16 variant of window 1 into one player, simulator worlds and horizon 2
    included, and named a multi-opponent run's opponent "heuristic,random".
  - ncurve fitted the simulator-worlds run as a second n = 16 point.
- **Answering combat asks from a plan** had two copies. SimAgent had no turn check, so a
  playout replayed the root's attack plan in every later combat. That confounds window 1's N4
  (192 §7.4).
- **Resolving the top of the stack** had two drivers, and the trigger-loop tripwire lived only in
  the undriven settle. A self-retriggering loop in the game loop never ended (reproduced).
- **The bench router's two branches:** only the cast branch handled `menu.perform` refusing.

**The fixes:**
- `tools/selfplay/evalrows.py` is the one reading of rows and the one name per player (a891a0c).
  paired reproduces window 1's paired number and the n-curve its fit.
- `search.planned` is the one turn-gated plan rule (9aed39e).
- `Executor._resolve_top` is the one resolution path, with the tripwire inside it (aeb76fc).
- The router's activation branch handles a refusal (aeb76fc).

### C3. A name that said one thing while the code did another

- **`--infer-bf16`.** Without it, inference still ran bf16 autocast on CUDA. There was no fp32
  path, so window 2's "fp32" check (192 §7.6 H1) compares two bf16 paths.
  - Fix: no autocast in inference (9aed39e).
  - 192 §7.6 is amended, and H1′ runs in gate B's queue.
- **`turn_open`** meant both "a turn is in progress" and "the sorcery window is open". The end
  step cleared it and deferred an effect that ends the turn to the step's own end. Under priority,
  the spells below Discontinuity kept resolving: Eliminate killed the creature, then went to
  exile, and players kept getting priority (reproduced with real M21 cards).
  - Fix: `turn_open` means only the turn, a request is consumed at once in every step, and
    `_closing_turn` is gone (aeb76fc).
  - Siblings fixed with it:
    - `defending_player` was kept: the end-the-turn process now leaves combat through
      `_leave_combat`;
    - two cleanup steps followed every turn-ending effect;
    - the bench view had no step name in the end step and cleanup.
  - Pack `cards/M21/discontinuity_2` passes on the fix and fails on d6dcdff.
- **Docs that followed a name.** "Wilson" intervals that are deal-level normal ones; "about twice
  as wide", where the measured factor is 1.3-1.6; 191's gate SE of 0.011, where the deal-level
  value is 0.0071-0.0081; "v1 frozen at 77", whose weights are update 75's. Corrected in ae9ad16.

### C4. What defines a network did not travel with it

- **`mask_names`.** Only two of five reconstruction paths copied it. The trainer rebuilt networks
  without it: KL 0.26 to the actors, reproduced. It was latent, since no training run used the
  flag.
- **`--opp-ckpt`.** The opponent was loaded with its own card table, which was then thrown away,
  while every seat's features use the learner's table. Its component rows depended on the
  precision.
- **The fix** (9aed39e):
  - `mask_names` lives in the config;
  - copies are deep copies;
  - another checkpoint must share the learner's card rows (a prefix check, then `extend_cards`);
  - `model.load` returns eval mode. distill had described G with name dropout on.

### C5. Queues treated "a step ran" as "a step succeeded with the inputs I meant" (gate B)

- **GROUPS.** `--groups ${GROUPS:-4}` read bash's own `GROUPS` (the user's gid), so production
  would have run `--groups 1000`. The smoke set `GROUPS=1` itself and so hid it.
- **A_G.** A restart after chunk 0 began skipped A_G for good.
- **Failed steps.** A failed or capped step never stopped its dependants, and the log still ended
  "gateb done".
- **Sizes.** A generation short of 300k still named everything 300000.
- **Markers.** Step markers were not tied to a run, and a restart could share the GPU with r27.
- **The fix** (3c718a0, b73d562):
  - `--groups 4`;
  - A_G a saved verdict, with an interrupted chunk 0 set aside and played again;
  - required steps stop the queue;
  - the target count checked against the size requested;
  - the commit that began the run recorded, plus a lock;
  - r27 paused at any restart that finds it running.
  - Mock runs of every restart path and a real CPU smoke that trains both sizes pass (196 §7).

### C6. Contracts between modules left implicit

- **The pooled variance.** search.target_record stores each option's population variance, and
  distill pooled it over n. A first-round loser's single world shrank the pooled variance to 0.73
  of the unbiased one on real n = 16 records: steps 9% larger, target KL 22% larger. Fixed: the
  sum of n × var over the sum of (n − 1).
- **Minibatches.** `ppo.chunks` drew from numpy's global state, which distill never seeded. Fixed:
  the caller passes a generator.
- **q1 and n1.** They fell back silently to all of an option's rounds. Fixed: n1 = 0, and se1
  leaves such a record at pi.
- **The journal used as a knowledge record.** `reshuffle_unknown` rebuilt what players know from
  it, and pinned unseen cards in 17% of the audit's decisions, mostly the next draw. Its only test
  asserted the approximation.
  - SCRY journals a count.
  - REVEAL has no zone role, so Duress's hand reveal journals the target's whole library.
  - Fix: true worlds reshuffle both libraries whole (9aed39e). 195 §5 marks that run confounded.
- **Copies of a card counted as different moves** by the search and its audit, so 195's "best
  candidate" was a coin flip between copies.
  - Fix: `search.option_classes`; the audit compares distinct moves (b73d562).
  - The search itself is unchanged (BACKLOG: measure first).
- **COUNTER_SPELL** raised on an empty designation, an assumption from single-target
  counterspells. CR 608.2b keeps a multi-target spell resolving.
  - Fix: aeb76fc. Pack `cards/M21/sublime_epiphany_3` passes on the fix and fails on d6dcdff.

### Why the tests and smokes did not catch these (the process causes)

- **Smokes that missed the production path.** The gate-B smoke set `GROUPS=1` and played one deal
  a chunk, so the small arm trained nothing. CPU runs never reach the CUDA autocast path.
- **Tests that asserted the approximation, not the property.** The reshuffle test pinned what the
  code did. The audit test had one candidate, so it never met two equivalent ones. The tripwire
  test ran only undriven.
- **Scripts that parse logs by string match** (`'"event": "eval"' in x`). The queue and ncurve now
  parse the JSON.
- **Changed assumptions not traced to their dependants.** The end step's deferral was right when
  the end step was a single settle. COUNTER_SPELL's guard was right for single-target spells.

## 2. What changed in the registered record (all before the affected data, or marked so)

- **192:**
  - §7.6: H1 compares two bf16 paths, and H1′ (bf16 and fp32 twins) runs in gate B's queue.
  - §7.4: N4 is confounded.
  - The n-curve table's "moves changed" counts copies.
- **195 §5:** this run is read as confounded and decides nothing. The confirming run is gate B's
  last step, on deals 965,000-965,099, with fixed true worlds and distinct moves. The hunt's
  sensitivity table was seen, and that is disclosed.
- **196 §7:** every gate-B change, two premises corrected ("seldom flips the top choice" was 13.9%
  in fact), and the pin moves to b73d562.
- **191 and NUMBERS:** the gate SE, and v1's update.

## 3. What stays open

- **r27 runs d6dcdff and is not restarted.** Its registered reads cite that code, and a restart
  onto the fixed engine would change its game mid-run. It keeps:
  - the torn-save risk, about 0.05 s of exposure per save, which the window queues avoid by
    stopping right after a save;
  - the orphan-version risk after a crash within 3 updates of a freeze;
  - the end-step Discontinuity error;
  - the driven trigger-loop hang (no natural loop exists in the pools);
  - the rare double-counter crash, which voids a game.
  - **Recovery, if last.pt is ever torn:** copy best.pt or the newest v<k>.pt over last.pt.
    state.pkl is written atomically and stays good. Then resume, and record the rollback in 191.
- **BACKLOG:**
  - the search collapsing copies, to measure before use;
  - the journal as a knowledge record (REVEAL's zone, SCRY's cards);
  - Teferi, Master of Time's −3 duration (suspected);
  - the audit's simulator generator.
- **Window 2's scorers** (scratch `w2/`), fixed before their data:
  - audit_b's rank correlation, its NaN guard never fired: average ranks, fully tied lists left
    out;
  - drafter_g2g4: voids counted, arms checked for 1,000 deals, G4's pass condition computed both
    ways, and a paired interval;
  - probe_k: a bootstrap that bounds the bias of choosing the learning rate on the test games;
  - mulligan_read: void games left out of M3.
  - They run on the w2 worktree's code (`PYTHONPATH` set to it, no bytecode written).
- **An observation, not a bug** (r27 metrics): the mulligan kind's per-update KL averages 0.04,
  about 10 times every other kind's. It follows real movement of the mulligan policy (correlation
  0.43 with the total KL, 0.31 with the change in mulligan entropy, 0.04 with the overlap share),
  not a mismatch. It belongs with 191 §7's mulligan read.

## 4. Maintenance in the same pass

- Ruff's 212 "undefined name" findings all come from the M20 mappers' draft trees in
  `tools/scenarios/known_bugs/2026-11-05/`, which are data. The four known-bug packs still fail
  as designed. Ruff is clean on `tools/selfplay` apart from three deliberate cases.
- Pyright over `tools/selfplay` found no real defect beyond those above; its findings are about
  dynamic attributes and narrowing.
- Doc paths to deleted files sit in dated historical reviews, which already say the code was
  deleted, and are left as history.
- Baselines after the fixes:
  - `pytest MTG_bot`: 5,116 passed, 39 deselected, 71 subtests;
  - `pytest tools`: 184;
  - scenario packs: 743/743.
