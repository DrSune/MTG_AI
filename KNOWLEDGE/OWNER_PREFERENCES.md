# OWNER PREFERENCES (binding, standing — read every session, every subagent prompt inherits these)

Owner-stated preferences, kept short because local models follow few explicit rules better
than walls of guidance. Newest first. Dated audit trail lives in the numbered day folders.

1. **Play must never be built on hidden information.** (owner 2026-10-18, /94) An omniscient
   view is fine as a *labeled mode* (analysis/teacher/audit); the play encoding is perspective-
   masked, and hidden zones are handled by beliefs derived from public information only
   (registered lists/pool minus the public record). Any feature computable only by reading a
   hidden zone is cheating — including inside "worst-case" or "guess" features.
2. **Simple, clean implementations.** (owner 2026-10-06, reaffirmed; operational form:
   AGENTS.md §7) Prefer the simplest implementation a human and an agent can both inspect.
   No unnecessary abstraction, indirection, cleverness, or premature generalization — but
   never drop error handling or validation to save lines. Minimal diffs: touch only what the
   task requires; a drive-by rewrite is a bug surface.
3. **VERIFIED means EXECUTED.** (owner 2026-10-06) Report what you ran and what happened.
   A claim without a command + result behind it is not evidence; same-context self-review is
   review theater. Substantive changes get fresh-eyes review (diff + requirements only).
4. **Communication = numbers.** (owner 2026-10-04) Progress/status is valued as measurements
   (NUMBERS.md law: date + producing command) and the monitoring board, not prose vibes.
5. **Validation is paramount; bugs/loopholes are the main hunt.** (owner 2026-10-04)
   Divergence must be locatable; the model must be rewarded for intelligent task-completion,
   never for engine shortcuts.
