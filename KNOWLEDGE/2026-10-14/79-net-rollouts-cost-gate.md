# 79 — /74 §5 on-policy net-rollouts: plumbing + IMPROVEMENT label shipped; 32-game pilot STOPPED at the cost gate (90.9 s/ask CPU)

Date: 2026-10-14 12:30. Closes the /74 §5 gap mechanically, NOT empirically.

## Shipped (all executed, no commits)
- mcts `rollout_mix="net"`: both rollout seats = FRESH BcAsk instances of the
  root net on `--rollout-device` (default cpu; weights shared per-process via
  BcAsk._MODEL_CACHE). pi_mix 0.75/0.25 unchanged.
- IMPROVEMENT label `adv_mix = value(search-top1) - value(net-argmax champion
  pick)` (root-seat view, arm mean backed values; 0.0 if either arm
  unevaluated; verify_episode range [-1,1]). Learner NOT touched.
- gen_games `--rollout-mix net --rollout-device`; stats addendum:
  mean_adv_mix / mean_abs_adv_mix / share_adv_gt_0.1 / mean_adv_on_disagree
  (cold-feet map WITH on-policy values — the number /74 couldn't produce).
- pytest tools/search -q: 30 passed (2 new: net-seat rollout determinism under
  seed + is-net probe; adv_mix math incl. unevaluated-arm path).

## Cost measurement (clean load ~3.9, 1 torch thread, bsh_S3a_s1_best.pt, k=4 N=12 cap=40)
- ONE root_search at seed 9000 turn-12: **90.9 s/ask** — rollout_ms 90.8 s of
  it (12 net-rollouts ~7.5 s each cap-40; apply 31 ms; root fwd 66 ms).
  policy_mix {"net":24} — seats really net (not HeuristicTeacher).
- gen_games --smoke (2 serial games, pilot knobs): game 1 NOT finished after
  19 min serial single core; killed per gate (>6 min/game -> STOP, no fleet).
- Projection: 65.8 asks/game (gen_stats_g3) x 90.9 s = **~100 min/game clean**;
  32 games / 6 workers sharing 20 cores with gen-big (16 workers) ->
  wall **~20-30 h** pilot. Gate verdict: not launchable as scoped.

## What this says (hypothesis, not conclusion — no pilot data yet)
/74 (b) named net-rollouts on GPU as the value-signal fix; on CPU the SAME
law bites the other way: rollout POLICY speed is the bottleneck, and one GPU
is occupied by training waves. Options to make the pilot feasible (~2 min/ask
budget): rollout turn_cap 40->10-15 (shorter horizon), N 12->6, or batched
rollout inference (multi-seat forward) — cap/N cuts trade value horizon.
Cold-feet-with-values map + improvement-opportunity share remain UNMEASURED
(gen_stats_improve1.json NOT written, eps_improve1.jsonl NOT written).

Repro: root_search(pos9000@t12, k=4,n=12,cap=40, rollout_mix="net",
net=bsh_S3a_s1_best.pt) on cpu, torch threads 1.
