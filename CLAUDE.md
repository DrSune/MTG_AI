# MTG_AI — agent operating instructions

## Before anything else

Read **[`NORTH_STAR.md`](NORTH_STAR.md)** in full. It is the project charter and it outranks this
file, every doc under `docs/`, and any idea raised mid-session. The summary below is a reminder, not
a replacement — read the real thing.

## The King Goal, in one line

> Build a genuinely strong Magic: The Gathering bot for the sets it has been trained on.

Priority ladder, highest first:

1. **(King)** Play the trained sets really well.
1. **(King, tied)** Auto-extend to unseen cards composed of already-practised primitives, with zero
   code changes. Only genuinely new keywords should need work.
2. Fast, near-real-time inference.
3. Extend to all sets via shared knowledge.

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
| `docs/ARCHITECTURE.md` | How the system actually fits together today |
| `docs/DECISIONS.md` | Settled calls, and the register of questions needing deeper reasoning |
| `docs/TRAINING_REVIEW_PROTOCOL.md` | **What to do before, during and after every training run** |
| `docs/METRICS.md` | The metric catalogue. Check §17 before adding any metric |
| `docs/COST_MODEL.md` | Why a parameter's cost depends on where you put it |
| `docs/BACKLOG.md` | Parked ideas, with the reason they are parked |
| `MTG_bot/rule_engine/` | The Magic rules simulator |
| `MTG_bot/strategic_brain/` | Network, RL training, environment wrapper |
| `MTG_bot/scenarios/` | Curriculum / puzzle scenarios |
| `MTG_bot/visualizer/` | Spectator tooling |
| `attic/` | Dead legacy code, kept for reference only. Do not extend. |

## Environment facts that will bite you

- **Training runs on a DGX Spark**, not on this machine. ARM64, CUDA 13, sm_121, 128 GB unified
  memory at ~273 GB/s. Capacity is huge, bandwidth is mid-range.
- **This Windows box is Intel Arc XPU** (`torch 2.11.0+xpu`). CUDA is unavailable locally. Any code
  that assumes `torch.cuda` will fail here. Always go through the central device helper.
- Use `MTG_bot/utils/device.py` for device selection (CUDA → XPU → CPU). Never call
  `torch.device("cuda")` directly.
- The C: drive on this machine is near full. Do not write large caches or checkpoints into the repo;
  put them behind a configurable path.

## Git: commit and push often, to main

**Standing instruction from the owner, 2026-09-10: commit and push to `main` after changes. Err
heavily toward too many commits rather than too few. Nothing may be lost.**

This overrides the usual caution about committing only when asked, and the usual habit of working
on a side branch. Work on `main` and push to `origin`.

- Commit when a coherent piece of work is done, not at the end of a session. If you have been
  working for a while without committing, that is already too long.
- **Push after every commit.** A commit that is not pushed is not safe. `git push origin main`.
- Never leave the working tree dirty at the end of a turn. If it is not worth committing, it is not
  worth leaving on disk.
- Before starting work, `git pull` so you are not building on a stale tree.
- Write real commit messages. They are the project's history of *why*, and this repo has already
  lost design content to a doc rewrite that a good message would have preserved.

Why this exists: an earlier working copy of this project at `Videos\MTG_AI` had its index
destroyed, showing 320 staged deletions against files that were still on disk, and a stale partial
tree that looked authoritative. The fresh clone in `Documents\MTG_AI` is the only real one. That
near-miss is the reason for the rule.

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
- Tests: `python -m pytest MTG_bot -q`. Report real results, never assumed ones.
