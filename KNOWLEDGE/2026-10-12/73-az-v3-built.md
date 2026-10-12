# 73 — AZ-v3 loop built + smoked (2026-10-12)

- AZ-v3 driver `tools/search/az_v3.sh`: gen(64g, k4/n10/cap40, greedy
  rollouts, --net = adopted) -> warm-start S3a `--mix search --search-data
  eps_g{g}` (+15 ep) -> 100g WR-gate (tol 0.02, one seed+7 retry) x4 ->
  200g finals vs teacher/bc10_S4_s2/bc9_S3_s1. Never dead-stops.
- Two resume-path bugs found & fixed (they made ANY warm-start chain a
  silent no-op): (1) vocab was rebuilt from the new stream (ids drift —
  smoke: ckpt 455 vs stream-rebuild 555; 338 words correctly -> <unk>);
  resume now reuses `ckpt["vocab"]` always. (2) resume `best` was seeded
  from the OLD corpus optimum -> no fresh epoch could ever win ->
  `_best.pt` never rewritten; best now re-bases on the current stream
  (smoke proof: azr_best.pt rewritten best_epoch 250 @ 0.74047 fresh loss).
- pi_mix = 0.75*visits + 0.25*net_menu over FULL menu (mcts.pi_mix_of,
  rows carry it, trainer distills it when present; renorm keeps sum==1).
  rollout_mix="greedy" is now the gen_games CLI default (both seats).
- Cost (measured 19:03-19:07, `gen_games.py --games 2 --k 4 --n 10 --cap 40
  --rollout-mix greedy --net bc10_S3a_s2_best.pt`, 2 workers): 822.5 /
  1050.4 s/game -> 64g/gen / 10 workers ~= 1.8 h gen + ~0.5-0.75 h train
  (+15 ep, GPU) + ~0.1-0.2 h gate ~= 2.4-2.7 h/gen < 3.5 h budget; chain
  4 gens ~= 10-11 h wall. Stats: net_disagree 0.64, top1_visit 0.40.
- Tests: tools/search 26/26 (2 new: pi_mix math, greedy-mix mini game);
  test_bc_v3+bc_v2 29/29; test_dagger_wave 5/5 (needs `-m pytest` — path).
  `--smoke` clamps epochs to 2 (train_bc_v3.py:613) -> resume+smoke is a
  no-range fallback exercise ONLY; real resume smokes must drop --smoke.
