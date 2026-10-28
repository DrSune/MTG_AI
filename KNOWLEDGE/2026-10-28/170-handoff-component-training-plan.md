# 170 — Handoff to the local agents: train component understanding (2026-10-28)

**Owner, 10:20.** Reading components as input is a prerequisite, not the point. The point is
training the network to understand each component and act on it, and finding and fixing the
components it gets wrong. "Prepare a plan, and then the agent later can do the actual plan ... we
can save some usage."

**The plan:** `docs/PLAN_COMPONENT_TRAINING.md`.
- **Step 0, fix what blocks training:**
  - no choice labels from HeuristicTeacher;
  - an X-choice ask;
  - labels for discard choices;
  - the B-44/B-48 component fold;
  - RL that takes real updates;
  - component card tokens, as a prerequisite.
- **Steps 1–3:**
  - teach what components do (K1 effects with wider labels);
  - teach what to choose (K2 replay labels, longer horizon);
  - drill the weak components.
- **Step 4:** RL for long-horizon play.
- **Measurement:** a per-component report card, built first, and gates before adoption.

**Open on main for whoever runs next.** Fingerprint `297f66c4` against the pin `07fd1a6e` since
the 03:45 compiler merge (/163). Re-smoke and re-pin before the next RL window, or it aborts as
PIN DRIFT.

Evidence: /165, /166, /169. Tools exist and are tested: `tools/k1`, `tools/k2`.
