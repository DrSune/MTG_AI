# MTG_AI — agent operating instructions

## Before anything else

Read **[`NORTH_STAR.md`](NORTH_STAR.md)** in full. It is the project charter and it outranks this
file, every doc under `docs/`, and any idea raised mid-session. The summary below is a reminder, not
a replacement — read the real thing.

**Current state (2026-11-09):** Phase 0 of `docs/PLAN_LEARNING.md` is done (its outcome in
`KNOWLEDGE/2026-11-06/187-handoff.md`); the owner chose outcome PPO as the learner and search at
play time, with the distillation parked (DECISIONS D21).

**Current plan (2026-11-11):** `docs/PLAN_CEILING.md`, approved by the owner (DECISIONS D22).

**Running since 2026-11-12 16:32:** r28 (`KNOWLEDGE/2026-11-12/199`): r27's configuration on the
fixed trainer, every optimizer step a stratified sample of the batch (`KNOWLEDGE/2026-11-12/198`),
from r27's v1. It runs as the transient user unit `mtg-r28` from the worktree
`/home/sune/Desktop/MTG_AI-r28` pinned at 44a62d9 (do not edit it), into
`runs/selfplay/r28_stratified_ppo/`. `systemctl --user stop mtg-r28` pauses it (the unit then goes
away); `reports/r28_2026-11-12/start.sh` resumes it from its last save, also after a reboot. The
guard `mtg-r28-guard` (`tools/selfplay/guard.py`) stops it on a mulligan runaway or a falling win
rate against the heuristic (199 §3). r27 ended at update 165: its mulligan ran away (191 §8, 198).
Window 1 is scored in `KNOWLEDGE/2026-11-11/192`, window 2 in notes 193-195, 192 §7.6 and 191 §8.
Gate B (`KNOWLEDGE/2026-11-12/196`, §8: on r28; §9: no automatic start) is a decision at r28's
read at update 400 by a registered break-even rule; its worktree `/home/sune/Desktop/MTG_AI-gateb`
(pinned at 8aabbc8, do not edit it) is re-pinned and re-smoked before it runs. The plan after r27:
`docs/PLAN_CEILING.md` §14-§15. The ceiling-read window (`KNOWLEDGE/2026-11-13/205`) ran 2026-11-13 04:52-08:08 as a pause
in r28 (at update 195): package decks hold no extra one-turn search headroom (S1 falsified), so r29
is not the package A/B; the held-out pool L is frozen (`reports/ceiling_window/pool_L.json`). r28
resumed when it ended. r26 stopped at update 1,002 (`KNOWLEDGE/2026-11-10/189` §11). One run at a time,
and nothing else on the GPU beside it.

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
  **Baseline B9** (2026-11-13, after gate rounds 5-10, the card backlog's waves 2-3 and the engine wave
  on events, KNOWLEDGE/2026-11-12/203-204, 2026-11-13/206; `tools/check.sh` green at 6bd77ef4): **5775
  passed / 39 deselected / 71 subtests passed, nothing failed or xfailed**, about 85 s beside a
  training run. B8 (2026-11-13 morning, 203) was 5345. B7 (after
  wave 1, 201) was 5176. B6 (after the bug hunt, 197) was 5116. B5 (2026-11-12, the cleanup pass
  after the priority engine) was 5113. B4 (2026-11-06, 6003dd4) was 5091, before the priority
  engine's tests.
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
  - Companion numbers: `pytest tools -q` = 271 passed (2026-11-13, B9; 227 after wave 2: + the
    dead-role rules, package mode, the line-value instrument, the trigger-timing and qualifier
    checks; 192 after wave 1: + the gate, probe and conformance tests; 187 after 198's fix: + the stratified-step, step-accumulation and
    guard tests; 184 after the bug hunt: + the
    commit, evalrows, plan-turn, option-class and generator tests; 176 before it: + the
    training-game log, `--collect`, `model.grow`, the search audit and the drafter's
    `test_decks.py`; every test seeded by `tools/conftest.py`, as the engine's are), 37-40 s
    beside a training run (the ontology baselines were re-recorded after the reviewed M21
    campaign; NUMBERS.md). `tools/run_scenarios.py` = 764/764.
  - `tools/check.sh` (or `--quick`) runs all of it and is the pre-push gate. There is no CI.
