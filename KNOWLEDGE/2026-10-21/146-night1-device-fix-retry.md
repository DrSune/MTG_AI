# 146 — RL night-1: production plumbing PROVEN (honest halt at first real crash, 2-min engine exposure), device bug fixed with regression proof; retry armed night-1b

Date: 2026-10-21. Window fired 23:59; P0 collect 2g CPU 0.25 g/s (6 workers, engine-off), audit GREEN (real path, cross-process), trainer CUDA step CRASHED in 4s: cpu-built t_anc vs cuda lp at post-step KL (train_rl_v1.py:278) — the ONLY host->device construction in the file (audited). rc=8 halt -> trap restore: docker start + healthy + plugin-check within 55s of crash. **Total engine downtime 2 min — the /130-pattern failure path is now production-proven end-to-end.**

## Why the dry-run missed it (PITFALL-CLASS, new)
DRY mode forces cpu => device-mismatch paths structurally untestable. Law: a dry-run that pins a config dimension (device, worker count, pool) cannot prove paths crossing that dimension; each live-mode dimension needs at least one real-config smoke BEFORE arming a night. Here: today's real-CUDA smoke (exit 0, grad_norm 44.70 CPU==CUDA cross-device agreement, kl ~1.8e-9 at step-0 anchor-identity) now covers it + cuda regression test whose REVERT reproduces the exact crash.

## Calibration partials (provisional, n small)
Collection engine-off CPU 6 workers: 0.25 g/s (n=2, noisy) => 1000g ~ 67 min — P2 1000g fits easily (guard: P1 wall x18 + 45min). GPU not needed for collection; --gpu-train only for the trainer step.

## ERA CAVEAT (R3 landed 6e4027d: silent-CHOOSE ask-lift, 14 cards ask-visible; R2/R3b also landed)
Tonight's export = post-R3 engine: ask-count per game changes vs pre-R3 era. Calibration numbers (g/s, asks/game) are era-local; F4 no-op diagnostics era-local; WR verdict axis is the in-window MIRROR (frozen pre-RL clone in same export) — unaffected by design. PIN law: if P2 completes tonight, export rev recorded to /tmp/opencode/RL_PILOT_PIN in the morning; night-2+ exports from PIN.

## Retry state
Armed 2026-10-21 23:59 (tmux rlwindow, real, --gpu-train, restart-at 07:00) on HEAD 7403155+. Cancel: touch /tmp/opencode/RL_WINDOW_CANCEL.
