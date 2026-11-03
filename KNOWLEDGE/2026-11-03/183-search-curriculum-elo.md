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

## 6. Throughput engineering (same day)

| Run | Change | Iteration (98K decisions) | Notes |
|---|---|---|---|
| r1 | synchronous, 2 PPO epochs | BC only (stopped after bc.pt) | update ~118 s measured in r2 |
| r2 | --async-update (thread, one CUDA stream), 2 epochs | ~100 s collect + 118 s update | stopped at the memory floor: MemAvailable 80 -> 7 GiB at it 4 (allocator growth, varying shapes) |
| r3 | + expandable_segments, tok-budget 98K, cache release every 16 steps, 1 epoch | ~95 s collect + 62-82 s update; 5-10K decisions played during an update | stopped for r4 |
| r4 | --trainer-proc (PPO in its own process/CUDA context) | **~105 s total**: 64-84K of the 98K decisions are played during the previous update; train_s ~88-90 s | 22-24 games/s, MemAvailable min ~54 GiB |

Elo at r4 start (uniform random = 0, 594 games): heuristic +387.6, v0 (25M BC) +376.0.

## 7. PPO against the teacher does not move at this scale (r4) -> adaptation by expert iteration (r5)

r4: 25M BC net, PPO vs the heuristic only, 12 iterations x 98K learner decisions (~26K games,
1 epoch, lr 1e-4, KL anchor 0.01 to v0, entropy 0.003):

| Number | Value |
|---|---|
| teacher-gate eval (greedy, 100 deals x 2) | it5 **0.500** [0.431, 0.569]; it9 **0.497** [0.428, 0.567] |
| training win rate vs heuristic (sampled) | 0.48-0.51, flat over 12 iterations |
| KL(learner || v0) | 0.013 -> 0.122 (diffusing) |
| PPO surrogate on fresh minibatches | positive on average (0.01-0.065): updates on other minibatches made it worse |
| entropy | stable 0.13-0.16 (no drift, unlike m2/m3) |

Reading: noise-dominated updates. The imitation policy is near-deterministic (~3% of actions
explore) and one +-1 outcome per ~45 decisions credits the rare useful deviation too weakly. Not
evidence that PPO cannot work here; evidence that at ~2K games per update it does not, from a
peaked BC start. r5 keeps the curriculum, gates and Elo ladder and adapts by expert iteration
(search distillation), whose per-decision targets compare alternatives in the same position.

## 8. r5: expert iteration vs the teacher, first two generations

| Gen | searching seat vs heuristic (training games) | games/s (18x8) | distillation (held-out agreement with search labels / value MSE) |
|---|---|---|---|
| 1 | **0.560** (1,499 games) | 3.63 | 0.9552 / 0.5149 |
| 2 | **0.609** (1,500 games) | 1.38 | 0.9216 / 0.2509 |

Raw network (no search) vs heuristic after gen 2: **0.500** [0.431, 0.569]; paired vs v0 on the
same 98 deals **+0.028** [-0.013, +0.071] (10 deals better, 6 worse). Searching player +11 points
above its own raw network: distillation under-fit (1 epoch, lr 1e-4, ~4K-decision minibatches =
~35 optimizer steps for 137K samples). r6 restarts from r5's gen-2 net (last.pt, it 2) with 3
epochs, lr 2e-4, minibatches <= 1024 (~400 steps per generation).

## 9. r6 and the first significant gain; r7

r6 (from r5's gen-2 net; 3 epochs lr 2e-4 mb 1024): gen 1 searching seat 0.610 vs heuristic (search
on 49% of act asks, changing 30% of those; 33% of attack plans changed; 0.6% of simulations hit an
engine error and score neutral); gen 2 0.592. Raw net after gen 2: **0.5357** [0.466, 0.604];
paired vs the original BC net **+0.0638** [+0.0153, +0.1148]. Distillation curves in gen 2: policy
agreement 0.886/0.888/0.888 per epoch while held-out value MSE rose 0.695/0.728/0.789 (value
memorises game outcomes). Holdout made fixed per game id (it was re-sampled per generation).

r7 (from r6's gen-2 net): + fast rollout network (m1 5.3M BC) for the moves inside simulations,
length-bucketed inference, 2 epochs, value weight 0.25, 4-generation window.
