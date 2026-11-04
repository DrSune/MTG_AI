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

## 10. The value head collapses under aggressive distillation -> a separate value network (r9)

Fixed probe: 120 fresh heuristic-vs-heuristic games (seeds 7,700,000+), 11,420 positions, both
seats, outcome z = +-1 (var 0.988). Value MSE / explained variance / correlation:

| Network | MSE | EV | corr |
|---|---|---|---|
| BC r1 (16K games) | 0.589 | 0.404 | 0.640 |
| r5 gen 2 (ExIt 1 epoch, lr 1e-4, vcoef 0.5) | **0.565** | **0.428** | **0.659** |
| r6 gen 2 (3 epochs, lr 2e-4, vcoef 0.5) | 0.964 | 0.024 | 0.452 |
| r7 gen 1 (from r6, 2 epochs, vcoef 0.25, + rollout net) | 0.876 | 0.113 | 0.482 |

The setting that finally moved the POLICY (r6: +0.064 paired vs BC) destroyed the VALUE head the
search scores its leaves with. r7 also showed the small rollout network weakening the search
(searching seat 0.554 vs ~0.60) for no real speed-up (round trips now bound simulations).

r9: policy = r6 gen 2 (strong distillation, value weight 0.1); leaf values from a separate value
network initialised from r5 gen 2, trained value-only each generation (1 epoch, lr 5e-5) on a
10-generation value window that includes the opponent's positions, reverted whenever its
held-out MSE gets worse; 16 game slots per worker; no rollout net.

## 11. Inference server: the bottleneck of searched play

Searched play is ~99% inference inside simulations (r6 gen 1: 140K simulations, ~2.5M simulated
decisions per generation). Measured on the 25M net:

| Change | Effect |
|---|---|
| per-request costs | unpickle 4.3 us, collate 19.9 us, forward ~220 us/decision at batch 128 |
| length buckets (sorted, 1.4x rule) | 128-request batch with a 114-token outlier (mean 25): 78 -> 43 ms; no change without outliers |
| bf16 inference copies vs autocast over fp32 weights | batch 8 6.28 -> 3.38 ms, 32 9.54 -> 5.45, 128 22.84 -> 14.09; same argmax, values within 8.8e-4 |
| one read-back per call (pinned inputs) | no measurable gain (47 vs 52 ms, GPU shared) - not adopted |
| 16 game slots per worker (from 8) | r9: workers 68% CPU, learner serving thread 86% |
| small rollout net in simulations | rejected (r7: weaker search, little speed) |

r10 = r9 + --infer-bf16 (policy r6 gen 2, value net r5 gen 2).

## 12. r10: the separate value net makes the strongest search; value data must be sampled

r10 gen 1 (policy r6 gen 2, value net r5 gen 2, bf16 inference, 16 slots): searching seat vs
heuristic **0.639** over 1,500 games (r6: 0.610/0.592; r7 with the collapsed head: 0.554). The
value net's update on all positions of those games made it worse on held-out games
(0.645 -> 0.712) and was reverted: positions of one game share the outcome and are near copies.

r11: value net trained only on positions sampled with p = 0.06 (~5 per game) from 6,000 fast
unsearched value games per generation plus the search games, 10-generation value window, 3
epochs early-stopped at the best held-out epoch; 16 slots in 4 pipelined groups per worker.

## 13. r11: value net finally improves on held-out games; the raw network plateaus

| Gen | value net held-out MSE (before -> kept) | value positions / games | searching seat vs heuristic | raw net gate |
|---|---|---|---|---|
| 1 | 0.4755 -> **0.4486** | 44,250 / 7,399 | 0.600 | - |
| 2 | 0.5653 -> **0.5528** | 88,191 / ~15K | 0.593 | **0.5434** [0.4735, 0.6116] |

Paired over 98 deals, r11 gen 2 vs the original BC net **+0.0714** [+0.0153, +0.1276]; vs r6 gen 2
+0.0077 [-0.0306, +0.0459]: the raw network has not moved since r6 gen 2 (~4 generations) while
the searching seat keeps ~0.59-0.64. Hypothesis: hard labels from a noisy search (k 3, d 2) flip
on small score edges. r12: soft targets prior x exp(score / 0.05), resumable state, serving
window 5 ms with coarser buckets (ratio 2.0, min 24).

## 14. r12-r13: soft targets, resumable runs; the plateau is label noise

| Run / gen | searching seat vs heuristic | raw gate | paired vs original BC | paired vs r11 gen 2 | games/s |
|---|---|---|---|---|---|
| r12 g1 (soft targets, serve-wait 5, coarse buckets) | 0.608 | - | - | - | 0.94 |
| r13 g2 (resumed from r12; 32 slots x 4 groups) | 0.603 | **0.5485** [0.4785, 0.6165] | **+0.0765** [+0.0281, +0.1250] (20 vs 5 deals) | +0.0051 [-0.0306, +0.0434] | 0.96 |

Throughput levers exhausted for this architecture (0.91-0.97 searched games/s through r10-r13
whatever the slots, groups, batching window or buckets). Resume works (r13 restored 71,827
policy + 44,482 value samples).

Diagnosis of the plateau: after distillation the network still disagrees with ~11% of HELD-OUT
search labels, about the share the search changes; it fits the changes on training positions but
cannot predict them on new ones, i.e. the changes are mostly decided by the two sampled worlds,
not by the position. r14: 4 worlds per candidate (score noise halved) and search only where the
network's top option is below 0.95 (instead of 0.99).

## 15. Correction: search labels are reproducible (the plateau is not label noise)

`python -m tools.selfplay.label_noise --policy runs/selfplay/r13_exit/last.pt --value
runs/selfplay/r13_exit/value.pt --games 12 --d 2 4` (96 main-phase asks where the network's top
option < 0.95; two independent searches with different sampled worlds, k = 3):

| worlds per candidate | repeat agreement | search changes the network's move (per run) |
|---|---|---|
| 2 | **0.823** | 0.328 |
| 4 | **0.875** | 0.333 |

§14's diagnosis is superseded: the search's changes are consistent, the network fails to
predict them on unseen positions. They are lookahead decisions (combat arithmetic, the opponent's
reply) that need many more labelled examples to generalise. Next lever: a larger policy window
(more generations of labels at 1 epoch) rather than better labels; d = 4 gives +5 points of
agreement only.

## 16. Why distillation stalls: few clear labels, half the changes are ties (2026-11-04)

`python -m tools.selfplay.distill_probe --state runs/selfplay/r13_exit/state.pkl --gen 0 --prior
runs/selfplay/r12_exit/v0.pt --nets runs/selfplay/r13_exit/last.pt` (gen 0 = r12 gen 1, labels by
r12/v0.pt; r13/last.pt trained on it ~4 epochs over two generations):

| rows of gen 0 (changed = the search overrode the generating network) | n (train) | p(label) before -> after | acc after |
|---|---|---|---|
| changed, score margin >= 0.1 | 1,657 | 0.219 -> 0.304 | 0.229 |
| changed, margin 0.02-0.1 | 1,896 | 0.231 -> 0.251 | 0.141 |
| changed, margin < 0.02 (ties) | 3,490 | 0.233 -> 0.225 | 0.066 |
| kept (search agreed) | 25,150 | 0.791 -> 0.823 | 0.972 |

On held-out games (gid % 33, n 58) the clear changes moved 0.198 -> 0.214. Margins recovered from
the soft targets: median **0.021**, 65% < 0.05; the soft target keeps the network's move as its
mode on 62% of changed rows. Clear changes are ~1.6K per generation (~1 per game).

`tools.selfplay.distill_lab` (offline recipes, hashed 20% holdout, regret = score given up vs the
search's best on held-out searched rows; untrained init 0.0248 on gen 0):

| recipe (2 epochs, lr 2e-4) | trained on | gen-0 held regret | gen-1 held regret |
|---|---|---|---|
| soft (tau 0.05) | gen 0 | 0.0256 | - |
| hard | gen 0 | 0.0266 | - |
| sharp (tau 0.02) | gen 0 | 0.0257 | - |
| margin >= 0.05 x3, else own move | gen 0 | 0.0260 | - |
| soft, 1 epoch lr 5e-5 | gen 0 | 0.0256 | - |
| soft | gens 0+1 | 0.0251 | 0.0221 (init 0.0239) |

Every recipe lowers training-row regret (0.025 -> ~0.019) and raises held-out regret on the
generator's own labels; a second generation of data shrinks the damage. Caveat: this regret
favours the label-generating network (it has zero regret on every kept row by construction, and
the noisy max inflates the cost of any deviation), so it cannot rank recipes; games can. In games
the learner's two generations of soft distillation gained +0.0051 [-0.0306, +0.0434] (r11 gen 2
-> r13 gen 2, paired, §14).

Conclusion: at ~1.6K clear labels per generation the network cannot generalise the search's
corrections (~1 per game); it learns the generating network's style instead. The search's value
is realised at play time (searching seat ~0.60 vs raw ~0.55). Next: a long PPO run. r4's
"flat PPO" was 12 updates (~26K games, ~20 minutes, KL ~0.015 per update), too short to show
anything.
