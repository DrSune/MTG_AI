# MTG_AI — agent operating instructions

## Before anything else

Read **[`NORTH_STAR.md`](NORTH_STAR.md)** in full. It is the project charter and it outranks this
file, every doc under `docs/`, and any idea raised mid-session. The summary below is a reminder, not
a replacement — read the real thing.

**Current state (2026-11-09):** Phase 0 of `docs/PLAN_LEARNING.md` is done (its outcome in
`KNOWLEDGE/2026-11-06/187-handoff.md`); the owner chose outcome PPO as the learner and search at
play time, with the distillation parked (DECISIONS D21).

**Current plan (2026-11-11):** `docs/PLAN_CEILING.md`, approved by the owner (DECISIONS D22).

**Running since 2026-11-11 18:03:** window 1 of that plan: the n-curve, gate A and the simulator on
the game with priority, pre-registered in `KNOWLEDGE/2026-11-11/192`. It runs as the transient user
unit `mtg-window1` (`systemctl --user is-active mtg-window1`), which executes
`reports/window1_2026-11-11/queue.sh` from the worktree `/home/sune/Desktop/MTG_AI-w1`. Results go
to `runs/window1/`: `queue.log`, and one `.done` file per finished step, so a restarted queue skips
those steps. When the window ends, the transient unit `mtg-clock1`
(`reports/window1_2026-11-11/clock.sh`) measures the clock's latency, one game at a time (192 §6,
`runs/window1/clock.log`), and then starts r27 (`KNOWLEDGE/2026-11-11/191`, unit `mtg-r27`). r26
stopped at update 1,002 (`KNOWLEDGE/2026-11-10/189` §11). One run at a time, and nothing else on
the GPU beside it.

## The King Goal, in one line

> Build a genuinely strong Magic: The Gathering bot for the sets it has been trained on.

Priority ladder, highest first:

1. **(King)** Play the trained sets really well.
1. **(King, tied)** Auto-extend to unseen cards composed of already-practised primitives, with zero
   code changes. Only genuinely new keywords should need work.
1. **(King, tied)** Play well within a real match clock (promoted from rank 2 by the owner on
   2026-09-10; NORTH_STAR §1a). A decision that arrives too late is worth zero.
2. Extend to all sets via shared knowledge.

**Format priority: Commander.** Multiplayer, command zone, 100-card singleton, huge boards, long
games, effectively-everything-legal card pool.

## Two standing instructions from the owner

**Overrule authority.** The owner has greenlit you to overrule their own mid-session ideas when
those ideas do not move the ladder. Say so plainly, log the idea in `docs/BACKLOG.md`, and stay on
the King Goal. If they hear the objection and repeat the instruction, it is their call — build it.

**Learnable over hardcoded.** Prefer incentives and railed self-play over authored heuristics, caps,
clamps, and hand-tuned schedules. Strong preference, not absolute. When you must add a hard limit,
say out loud that you are adding it, why, and what would remove it later. Never add a cap silently.
The MTG rules themselves are not heuristics — implement those exactly.

## Repository layout

| Path | What it is |
|---|---|
| `NORTH_STAR.md` | Charter. Read first. |
| `docs/` | Design docs, open-problem write-ups, backlog, hardware notes |
| `docs/DECISIONS.md` | Settled calls, and the register of questions needing deeper reasoning |
| `docs/TRAINING_REVIEW_PROTOCOL.md` | **What to do before, during and after every training run** |
| `docs/METRICS.md` | The metric catalogue. Check §17 before adding any metric |
| `docs/PLAN_LEARNING.md` | **The learning plan** (owner-approved): playout labels on the true future, the opponent simulator, memory, phases and powered gates (D20) |
| `docs/OWNER_VISION_LEARNING.md` | **The owner's learning vision**: full credit, memory, inputs, the opponent simulator, the Teacher. Read before changing how the network learns |
| `docs/COST_MODEL.md` | Why a parameter's cost depends on where you put it |
| `docs/BACKLOG.md` | Scaffolds to remove, open engine faults, card-onboarding and training items, parked ideas; each with its reason |
| `docs/PLAN_CARD_ONBOARDING.md`, `docs/MAPPER_GUIDE.md` | How a card gets a record, and the gates it passes |
| `MTG_bot/core/` | **The rules engine**: compiler (oracle text to ability tree), executor, state |
| `MTG_bot/bench/` | Benchmark core shared by the bot and LLM seats: per-seat view, agent protocol, duplicate duels, stats, rules track ([`docs/DESIGN_BENCHMARK.md`](docs/DESIGN_BENCHMARK.md)) |
| `MTG_bot/data/` | Set files (MTGJSON) and one record per mapped card (`data/cards/<SET>/`) |
| `tools/selfplay/` | **The network that trains**: self-play PPO learner, model, heuristic opponent, decision-time search ([`tools/selfplay/README.md`](tools/selfplay/README.md)) |
| `tools/cards/` | Card onboarding: mapping tool, gates, soak |
| `tools/scenarios/`, `tools/run_scenarios.py` | The scenario packs (the executable rules-conformance suite) and their runner |
| `tools/search/fork.py` | Clones a live game for the self-play search |
| `tools/audit/` | Anomaly detectors (the card soak runs them), set intake (`new_set.py`), the ontology checker behind the red-first battery |
| `tools/check.sh`, `tools/save.sh` | The pre-push gate; commit and push with the large-file guard |
| `tools/gen_buckets.py` | Writes `/tmp/opencode/phase1_buckets/`, which the core template tests read. Rerun it after a reboot |
| `KNOWLEDGE/`, `reports/` | The dated knowledge tree, and the evidence it cites |
| `MTG_bot/docs/`, other `MTG_bot/*.md` and `*.txt`, top-level `ideas.md`, `notes.txt` and the other loose notes | Pre-rebuild notes about deleted code, kept as owner-idea sources ([`docs/OWNER_IDEAS.md`](docs/OWNER_IDEAS.md)). Not instructions |

Deleted on 2026-11-05 and reachable with `git show dbd6e9d:<path>`: the pre-rebuild engine and
model (`MTG_bot/rule_engine/`, `MTG_bot/strategic_brain/`), `attic/`, and the `PointerBC` stack the
self-play stack replaced (`tools/training/`, `tools/eval/`, the rest of `tools/search/`). Unmerged
work on that stack is kept as the tags `archive/rl-v2-offline-core` and `archive/era-dryrun-2026-11-03`
(the branches were deleted 2026-11-06; there are no branches besides `main`).

## Environment facts that will bite you

**Since 2026-09-10 this repo is checked out on the DGX Spark itself.** Tests, benchmarks and
training all run here. Measured bring-up detail in [`reports/SPARK_BRINGUP.md`](reports/SPARK_BRINGUP.md).

- **This box is the DGX Spark.** aarch64, 20 cores (10x Cortex-X925 + 10x Cortex-A725), NVIDIA GB10
  at sm_121, CUDA 13.0, 121 GiB unified memory. `torch 2.14.0+cu130`. Capacity is huge (a full-scale
  315.7M-param training step peaks at 5.5 GB of 130.7); bandwidth is mid-range and **measures
  223.7 GB/s**, not the 273 GB/s spec figure.
- **`python` does not exist here, only `python3`.** Inside the repo always use `.venv/bin/python`.
- **A forward pass passing does not mean training works.** torch 2.14 routes some backward ops
  through Triton, which JIT-compiles with `gcc` against CPython headers (`python3.12-dev`). The
  headers are installed: a bf16 CUDA backward pass runs without `TORCH_DISABLE_NATIVE_JIT`
  (checked 2026-11-05). Commands that still set it to 1 are harmless; if a box lacks the headers,
  the first gradient raises `Python.h: No such file or directory` and the variable is the fix.
- There is **also a Windows Intel Arc box** (`torch 2.11.0+xpu`) used for dev and the spectator app.
  It cannot run CUDA. So code that assumes `torch.cuda` still breaks there.
- **Never use the `random` module directly.** Go through `MTG_bot/utils/rng.py`:
  `stream("shuffle" | "engine" | "policy" | "exploration" | "deckbuild" | "teacher" | "scenario")`.
  Sharing a stream couples two concerns' draw counts, which is what pre-flight P11 forbids. Add a name
  to `STREAM_NAMES` rather than reusing one. Call `seed_all(master_seed)` once at run start and record
  the seed in the manifest.
- Disk here is 3.7 TB (1.1 TB used on 2026-10-24, mostly outside this repo), so the old C:-drive
  pressure note does not apply. Still keep large caches and checkpoints behind a configurable path,
  because the Windows box is tight. **Never commit a checkpoint**: GitHub rejects files over 100 MB
  and one such blob makes `main` unpushable. Pin it in `reports/LARGE_FILES.sha256` instead.
  Before pruning checkpoints, keep every one pinned there or cited by a `KNOWLEDGE/NUMBERS.md`
  command (2026-11-06: a prune deleted four cited ones).

## Git: commit and push often, to main

**Standing instruction from the owner, 2026-09-10: commit and push to `main` after changes. Err
heavily toward too many commits rather than too few. Nothing may be lost.**

This overrides the usual caution about committing only when asked, and the usual habit of working
on a side branch. Work on `main` and push to `origin`.

- Commit when a coherent piece of work is done, not at the end of a session. If you have been
  working for a while without committing, that is already too long.
- **Push after every commit.** A commit that is not pushed is not safe. `git push origin main`, then
  check that `git ls-remote origin refs/heads/main` equals `git rev-parse HEAD`. On 2026-10-24 local
  `main` was found 326 commits ahead: nothing had been pushed for five weeks
  (`KNOWLEDGE/PITFALLS.md`). `tools/save.sh` now verifies the push.
- Never leave the working tree dirty at the end of a turn. If it is not worth committing, it is not
  worth leaving on disk.
- Before starting work, `git pull` so you are not building on a stale tree.
- Write real commit messages. They are the project's history of *why*, and this repo has already
  lost design content to a doc rewrite that a good message would have preserved.

Why this exists: an earlier working copy of this project at `Videos\MTG_AI` had its index
destroyed, showing 320 staged deletions against files that were still on disk, and a stale partial
tree that looked authoritative. That near-miss is the reason for the rule. The working copy is now
`/home/sune/Desktop/MTG_AI` on the DGX Spark, and `origin` on GitHub (public) is the backup.

## Before and after any training run

Follow [`docs/TRAINING_REVIEW_PROTOCOL.md`](docs/TRAINING_REVIEW_PROTOCOL.md). Do not start a run
that fails pre-flight and do not report a number that skipped a gate.

Two rules that catch most of the damage:

- **Correctness before strength before style.** An engine error invalidates every strength number
  computed after it, so never review play tendencies from a run whose simulator was throwing.
- **Check `docs/METRICS.md` §17 before adding any metric.** If a do-nothing policy scores well on
  it, it must be published paired with a metric that only acting well can satisfy. This project has
  already shipped a benchmark that paid a do-nothing policy 0.900.

## Working conventions

- Cite `file.py:line` when describing behaviour. Do not describe code you have not read.
- Any new hard limit, cap, or schedule must be recorded in `docs/BACKLOG.md` under "scaffolds to
  remove", with the condition that would let it go.
- Prefer editing an existing doc over adding a near-duplicate one.
- Tests: `.venv/bin/python -m pytest MTG_bot -q`. Report real results, never assumed ones.
  **Baseline B4** (2026-11-06, after the two lean passes, main 6003dd4; KNOWLEDGE/NUMBERS.md):
  **5091 passed / 39 deselected / 71 subtests passed, nothing failed or xfailed**, about 45 s.
  B3 (2026-11-06, f332d17) was 5297: the lean passes removed 231 duplicate, can't-fail or dead-code
  tests and added mulligan and multi-slot tests. B2 (2026-11-05) was 4686. Other docs point here. It is
  reproducible: `MTG_bot/conftest.py` seeds every test. The parts:
  - **No expected failures: any failure is a regression.** B0 (2026-10-24) carried 2 by-design
    failures and 23 xfails; all were legacy tests, deleted with `rule_engine/` and `strategic_brain/`.
  - The 39 deselected are the R3b red-first battery (`MTG_bot/core/test_ontology_r3b.py`).
    `-m red_first` gives 13 passed / 26 failed on 2026-11-05, the same on `main`; the 15 / 24 in
    `reports/r3b_red_prechange.txt` is from 2026-10-24.
  - The 732 scenario packs run inside this suite (`MTG_bot/core/test_scenario_packs.py`). The runner
    fails a pack whose expect lane it never reads or whose decision word its ask does not offer.
  - The core template tests read `/tmp/opencode/phase1_buckets/`, which only
    `tools/gen_buckets.py` writes. After a reboot, run it before the suite.
  - Companion numbers: `pytest tools -q` = 173 passed (2026-11-12: + the training-game log and
    the drafter's `test_decks.py`; every test seeded by `tools/conftest.py`, as the engine's
    are), 37 s beside a training run (the ontology
    baselines were re-recorded after the reviewed M21 campaign; NUMBERS.md).
    `tools/run_scenarios.py` = 743/743.
  - `tools/check.sh` (or `--quick`) runs all of it and is the pre-push gate. There is no CI.
