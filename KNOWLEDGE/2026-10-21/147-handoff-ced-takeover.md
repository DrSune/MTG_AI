# 147 — HANDOFF: CED takes the Spark GPU (owner instruction 2026-10-21, relayed by CED session); RL pilot paused at fully-armed state

## Why stopped
Owner authorized handing the Spark GPU to CED experiments; Flash-Next stopped ~06:45. My instruction: wrap up, no new work, no engines. NOT a failure stop — the RL pilot was armed and ready; capacity is the scarce resource, owner reallocated it.

## State at handoff (all committed; tree carries only sibling lanes' work, untouched)
- Plateau ledger COMPLETE (/133): tokens /78 + volume /80 + labels /83 + capacity (S4x3, mirror 0.42-0.43 vs 10M clone, eval_acc frozen 0.707) all NEGATIVE ⇒ imitation caps at greedy-teacher class; binding constraint = LABEL INFORMATION. Fresh current-engine anchor: bsh_S3a_s1 vs teacher 0.394 [0.347,0.442] 400g (ce3b50b).
- RL pilot /134 v2 (owner GO'd): design adversarial-gated (3 FATAL fixed: mirror-only verdict; pilot = instrument NOT verdict; no-op discriminator). Precond-2 (/137: sampling collection + rl_logprob_audit, cross-process GREEN), trainer (/138 + device fix 7403155, cuda-revert test, grad-norm CPU==CUDA 44.70), window ops (11b1cef, FULL dry-run proof, --cancel-file opt-out proven).
- Night-1 (23:59): P0 audit-GREEN real path, trainer CUDA crash (cpu t_anc vs cuda lp), honest halt, engine restored in ~55s (2-min exposure). Bug fixed + PITFALL law (/146): dry-modes pinning a dimension cannot prove paths crossing it.
- Night-1b was ARMED on fixed HEAD — cancelled tonight per owner: /tmp/opencode/RL_WINDOW_CANCEL exists, tmux rlwindow killed. Engine stays whatever CED needs.
- T-G5 audit (/135): cross-set ELO ladder NOT hostable (M21-locked ab_duel/elo plumbing; puzzle meter vocab-relative ⇒ WR-only cross-set verdict meter); 5-step fix ladder in entry; protocol memo (home-pool law) awaits owner. T-G7 datum-1: 3-arm parallel training scales 3.0 engine-off.
- Calibration partials: collection engine-off CPU 6 workers 0.25 g/s (n=2) ⇒ 1000g ≈ 67 min; GPU only needed for trainer step.

## RESUME EXACTLY LIKE THIS (when GPU returns and owner says GO)
1. `ls /tmp/opencode/RL_WINDOW_CANCEL` — delete only with owner GO.
2. Sanity: `.venv/bin/python -m pytest tools/training/test_rl_train.py -q` (expect 7 passed, cuda test active) + one real-CUDA smoke (rl_pilot_phases.sh call pattern, episodes_smoke.jsonl, device cuda). PITFALL law: re-smoke ANY dimension changed since.
3. Re-arm: `tmux new-session -d -s rlwindow "bash tools/ops/rl_window.sh --start-at 23:59 --restart-at 07:00 --gpu-train"` (phases P0 smoke→P1 calib 50g→P2 iter-1 1000g budget-guarded; artifacts /tmp/opencode/rld_n1/; owner opt-out = the cancel file).
4. Morning harvest: timing ledger (rates per phase), F4 diag jsons (THE question: does learning happen — mean|Δlogp|>0, grad-norms alive, KL<ceiling ⇒ yes; flat ⇒ "no learning occurred", NOT lever-negative), mirror probe vs frozen pre-RL clone (verdict axis; teacher rows descriptive only).
5. If learning-moves: P2 result feeds the 3-iteration plan (PIN law: export rev → /tmp/opencode/RL_PILOT_PIN, all later windows export from it; /146 ERA caveat: post-R3 engine changes ask-shape — era-local numbers).
6. Pilot verdicts follow /134 v2 stop rules (draw-halt ≥5/200, eval_acc drop >3pts halt, ANY-iteration reward/WR divergence halt; SUCCESS ⇒ 3-seed×400g rotated-seed confirmation before wave-2 funding).

## Awaiting OWNER (unchanged, not blocked by me)
T-G1 protocol sign-off (/135 §C); ZNR source verification; T-G5 fix-ladder execution (ab_duel/elo set-plumb — safe CPU work, first candidate for any CPU-only stretch); RL iteration-2+ windows cadence vs CED occupancy.

## Artifacts quick-map
Commits: /133 1c77c71 · /134+anchor d188ddf..ce3b50b · /135 bd041ba · precond2 140caee · trainer f2d693f + fix 7403155 · ops 11b1cef · /146 7c730c9. Ledgers: reports/rl_window_run.log, reports/r1_window_run.log. Probes: tools/eval/gameplay_{r1_s1..s3,anchor_bsh_cur_engine}.json. Diags: /tmp/opencode/rld_n1/ (NOTE: /tmp is not durable — re-collectable).
