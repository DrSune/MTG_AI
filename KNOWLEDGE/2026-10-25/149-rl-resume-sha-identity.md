# 149 — RL pilot resumed (owner: "continue the RL pilot"): checkpoint-governance collision caught pre-arm, fixed as SHA identity, smoke GREEN cross-path

Date: 2026-10-25. Owner GO after CED GPU handback (engine now 27B, gateway 200). Resume protocol /147 executed: pytest test_rl_train 7/7 → real-CUDA smoke FAILED on a NEW surface: load_episodes rejected night-1 rows because their `policy` field carries the EXPORT-DIR path, checked by exact resolved-path string. The window is self-consistent (collection+trainer share paths) so it would have passed tonight anyway — but exact-path policy identity is exactly the fragility the 2026-10-24 checkpoint governance (evidence-by-SHA, /147 addendum f938ba7) was written to kill.

## Fix
`_ckpt_key()`: identity = SHA-256 of checkpoint bytes when the file exists (cached per distinct path — big files hash once), resolved-path fallback when absent. load_episodes compares keys; error message names the rule. Tests: same-bytes-foreign-path ACCEPTED (export-dir/moved copy = same policy); same-name-different-bytes REJECTED fail-loud (0/2 episodes). 9/9 file suite.

## Verification (executed)
- Real-CUDA smoke with the window's exact call, cross-path (repo path vs export-dir rows): exit 0, 2g/41 asks, grad=44.70 IDENTICAL to CPU and to the 2026-10-21 fixcheck (reproducibility holds across 3 runs), KL -1.83e-09 (step-0 anchor identity), |Δlogp| 3.2e-06.
- tools/training full suite re-run at arm time (gate before arm).

## Armed again
Night window re-armed 23:59 / restart 07:00 / --gpu-train on HEAD incl. this fix; cancel file deleted per owner GO; opt-out file remains the ONLY stop mechanism. Engine note: 27B now loaded — window stops/starts the container regardless; window payload is torch-only, no agent inference inside.
