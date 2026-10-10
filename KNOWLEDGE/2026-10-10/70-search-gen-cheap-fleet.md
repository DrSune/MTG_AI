# 70 — Cheap-rollout search gen: first real fleet lands (2026-10-10)

Follows 69-search-gen-wave. Command:
`.venv/bin/python tools/search/gen_games.py --games 16 --workers 12 --budget-min 60 --seeds 9100`
(k=3, n=6, cap=25, `--cheap-rollout` ON). Wall 530 s; deterministic rerun reproduced
identically (219 eps both runs, same headline).

## Headline numbers
- Cost: **233.7 s serialised CPU/game median** (min 62.7, max 527.6) — was 60–100 CPU-MIN.
  Fleet: 16 games / 0 crashes / 715 asks / 4290 rollouts / **219 episodes**, 12 workers.
- Cost ledger (sum, ms): rollout 2,749,050 (73%) | net_fwd 896,814 (24%, 715 fwds) |
  apply 73,935 | probe 7,506. Probe cache: 309/715 asks (43%) served from branch
  handover, 406 real probes — cuts probe COUNT 43% but only ~0.2% of CPU.
  **Cheap-rollout+cap is the whole story; probe cache is rounding error** (honest).
- Rollouts never net-driven: policy_mix greedy 4399 / random 4181, net = 0 (mix is
  per-rollout-per-seat, 2 seats × 4290). rollout_fail_rate 0.0016.
- Quality: top1_visit_share 0.475 | mean|v−0.5| 0.337 | decided 90.3% / shaping 9.5%
  | swallowed 215 | **net_disagree 0.667 overall**; by kind: choose 132/153=86%,
  act 334/476=70%, attack 11/85=13%. Cold-feet map says search most overrides the
  net on `choose` asks, least on `attack`.
- Results: 7 draw (CR 104.4b STALL), 3 seat0, 6 seat1. All 219 eps re-pass verify_episode.

## Fixes landed this session (tools/search only; engine untouched, MTG_bot/core 2521+2st)
1. **pi rounding bug** (latent, pre-cheap-era): `"pi": [round(x,6)…]` broke the
   sum==1±1e-6 verify law on big menus → now raw `list(out.pi)`.
2. **mid_act probe-cache stall race** (seed 9100 turn 8): cached-ask handover skipped
   the engine's first-resume-iteration CR 104.4b check; all 3 apply forks "forced ask
   never reached". Fix: `mcts._resume_stalls()` mirrors the engine check (imports
   `_stall_fingerprint`, `REPEAT_ROUNDS` from games); walk sets honest STALL draw
   reason and breaks. Regression test `test_resume_stall_guard_mirrors_engine`
   ground-truths the helper against a real `_run`.
3. `_worker(seed,k,n,cap,cheap)` + CLI knobs `--k/--n/--cap/--cheap-rollout`;
   gen_stats cost ledger block (`_mix_total`); per-game probe/apply/rollout/net ms.
4. Budget guard re-verified on zero-harvest path (8 workers, 2-core cpuset, budget
   0.2 min → "BUDGET exceeded; cutting pool at 0/8", workers reaped).
5. Fleet launching gotcha: `nohup … &` from the tool shell gets SIGKILLed with the
   shell's process group at command timeout; **must use `setsid`** (own session).
   tools/search suite now 24 passed.

## Standing readouts for next wave
- net_fwd is now 24% of CPU — batching root forwards (or k-trees sharing a root
  forward) is the next lever; rollouts at cap25 ≈ 0.64 s/rollout.
- 43% STALL-draw rate (7/16) is high — walk line (search-top1) + default-opponent
  produces repeat-loop draws; consider anti-stall tie-break in walk choice.
- 86% disagree on choose asks with mean|dev| 0.337: either the net is badly
  miscalibrated on choose or search visits are noisy at k=3 — disambiguate with a
  k=6 mini-ablation before trusting either as training signal.
