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

## Working conventions

- Cite `file.py:line` when describing behaviour. Do not describe code you have not read.
- Any new hard limit, cap, or schedule must be recorded in `docs/BACKLOG.md` under "scaffolds to
  remove", with the condition that would let it go.
- Prefer editing an existing doc over adding a near-duplicate one.
- Tests: `python -m pytest MTG_bot -q`. Report real results, never assumed ones.
