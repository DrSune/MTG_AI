# 183: decision-time search, the owner's RL curriculum, Elo anchored at random (2026-11-03)

Author: Claude (Opus 5.5). Continues /182.

## 1. Owner direction (2026-11-03, verbatim gist)

- "It is fine if the model can 'reason' about the choice it is about to take, and what it means
  for later turns."
- "Drop the vLLM while working, we want more concurrency" (done: `docker stop qwen-nvfp4`,
  `systemctl --user stop opencode-supervisor`; MemAvailable 17 -> 91 GiB. Restore with
  `docker start qwen-nvfp4` and `systemctl --user start opencode-supervisor`).
- Curriculum: learn from teacher inter-play, then from playing the teacher, then self-play
  against a frozen version that the other side adapts to over thousands of games; an Elo/winrate
  increase re-freezes. "This is the actual RL part where the ceiling is almost limitless."
- Zero Elo = uniform random over the available choices.

## 2. Decision-time search (tools/selfplay/search.py)

Belief-sampled forks of the live game (own library shuffled; opponent hand + library redrawn
uniformly from the dealt pool), each candidate played forward through the opponent's next turn
by the network on both seats, scored by outcome or value head; common random numbers across
candidates. Main-phase asks plus whole attack plans at the pre-combat boundary.

| Number | Value | Command / source |
|---|---|---|
| BC m1 net, no search, vs heuristic (100 deals x 2) | 0.4745 [0.4057, 0.5442] | `runs/selfplay/s0_nosearch` |
| same net + search (k4 d3 skip 0.99) | **0.5281** [0.4583, 0.5967] | `runs/selfplay/s2_search` |
| paired difference over 98 deals | **+0.0536** [+0.0102, +0.0995]; 18 deals better, 6 worse | `python -m tools.selfplay.paired s0/eval_rows.jsonl s2/eval_rows.jsonl` |
| act-only search, no common random numbers | 0.5179 (+0.036, not significant) | `runs/selfplay/s1_search_eval` |
| search cost | 196 games in 231 s on 12 workers x 4 slots | s2 |

Reading: real but small. The value head (BC, heuristic-vs-heuristic outcomes only) limits it.
The legacy AZ line (/67-/74) failed with greedy/random playouts and 4-10 rollouts; a learned
value at the leaf and paired worlds are what differ here.

## 3. The curriculum (learner.py --curriculum)

v0 = BC; stage teacher (PPO vs heuristic, gate 0.65 or --teacher-iters); stage selfplay (PPO vs
the newest frozen version + 10% older versions + 10% heuristic; gate every --gate-every its on
--gate-deals deals, >= 0.55 with Wilson lower bound > 0.5 freezes the evaluated weights).
KL(learner || newest frozen) in the loss (--kl-anchor). Elo = Bradley-Terry over frozen
players with one virtual draw per pair, uniform random = 0.

Anchoring at random does not distort Elo (it only fixes the zero), but a player far above
random scores ~100% against it, which bounds the gap from below only; the ladder therefore
places each version through its neighbours.

## 4. Bugs found and fixed today (for the record)

1. PPO ran the net in train() mode, i.e. with name dropout, so the ratio compared the acting
   policy with a dropout-perturbed one. Effect measured directly on 1,166 BC decisions:
   KL(eval || dropout) mean 0.0030, median ~0, |ratio-1| > 0.2 on 0.6% of greedy actions. Small:
   it does NOT explain the m2/m3 drift. **Correction to commit b0a1ee1's message**: its "KL 0.16-0.26
   before, 0.012-0.027 after" compares a run that also had bug 2; the large KL came from bug 2.
2. --async-update first version read inference results back on the default CUDA stream while
   they were computed on a side stream: recorded logps were partly garbage -> NaN -> device
   assert. Fixed by reading back on the computing stream; a remaining device-side assert with two
   concurrent streams (never with CUDA_LAUNCH_BLOCKING=1) was removed by keeping inference on the
   default stream. 10-iteration smoke through the stage switch: clean.
3. Unified-memory training limits (/182 pitfalls): token-budget minibatches, memory floor.

## 5. Runs

- r1_curriculum (started 19:23, synchronous, old PPO code): d512 L8 heads 8 ff 2048 (~25M
  params); BC on 16,000 heuristic games (1,545,443 decisions, 692 s at 23 games/s on 18 workers x
  8 slots); BC epoch 0 held-out agreement 0.9495, value MSE 0.5726, 741 s/epoch. Restarted from
  its bc.pt with --async-update and the fixed PPO once BC finished (r2).
