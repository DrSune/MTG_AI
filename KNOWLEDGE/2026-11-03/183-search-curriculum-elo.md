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

## 17. Four worlds per candidate: not worth it; switch to a long PPO run (r15)

r14 gen 3 (resumed from r13; k 3, **d 4**, search where top < 0.95): searching seat vs heuristic
**0.614** over 1,499 games (r13 gen 2 at d 2 / top < 0.99: 0.603; r12 gen 1: 0.608; each +-0.025),
**0.56** searched games/s (d 2: 0.96), value net 0.5467 -> 0.5381 held-out MSE on 132,301
positions. Twice the worlds: +0.006-0.011 (inside the noise) for 1.7x the time.

r15 = the PPO curriculum from r14/last.pt: teacher stage (PPO vs the heuristic, 98,304 learner
decisions ~ 2,000 games per update, lr 1e-4, 1 epoch, ent 0.002, KL anchor 0.01 to the newest
frozen version) for up to 30 updates or a 0.65 gate, then frozen self-play (gate 0.55 with Wilson
lower bound > 0.5 every 5 updates, 15% heuristic, 15% past versions). r4 ran this loop for 12
updates only.

## 18. What the search corrects (clear overrides, margin >= 0.1)

`python -m tools.selfplay.clear_changes runs/selfplay/r13_exit/state.pkl 0
runs/selfplay/r12_exit/v0.pt`: 1,715 clear overrides of 33,246 searched asks (r12 gen 1), all on
the searcher's own turn, 736 at turn >= 12. Network -> search: cast A -> cast B 393, ATTACK ->
DECLINE 247, land A -> land B 198, cast -> PASS 186, land -> cast 168, DECLINE -> ATTACK 122,
land -> PASS 110. So: spell choice, attack/hold-back, land sequencing (e.g. a tapped land on a
turn whose mana is not needed). Some look like artefacts of the leaf value or of the network's
own continuation, e.g. casting Heroic Intervention with no creature in play instead of a land
drop (margin 0.14); `legal_casts` offers only payable casts (`MTG_bot/core/executor/query.py:912`),
so these are real choices the search prefers, not free no-ops.

## 19. PPO works when it runs long enough (r15, 2026-11-04)

r15 = PPO curriculum from r14/last.pt (the ExIt network, raw 0.536 vs heuristic), teacher stage.
Per update: 98,304 learner decisions (~2,000 sampled games vs the heuristic), lr 1e-4, 1 epoch,
ent 0.002, KL anchor 0.01 to v0, trainer process; ~140 s per update (update ~95 s, GPU 93%).

| update | training-game win vs heuristic | KL | entropy | explained var | KL to v0 |
|---|---|---|---|---|---|
| 1-5 (mean) | 0.537 | 0.012-0.020 | 0.243 -> 0.219 | 0.58 -> 0.72 | 0.012 -> 0.038 |
| 6-11 (mean) | 0.550 | 0.013-0.018 | ~0.21 | 0.72 -> 0.75 | 0.045 -> 0.074 |

Greedy evals vs heuristic: v0 0.5357 (ladder, 196 games); update 5 0.5556 [0.5052, 0.6048];
update 10 **0.5664** [0.5164, 0.6151] (400 games each). Paired over 98 shared deals, update 10 vs
v0: **+0.0536 [+0.0102, +0.0995]** (16 deals better, 5 worse); update 10 vs update 5 (189 deals)
+0.0146 [-0.0132, +0.0423]. Ten PPO updates (~22K games, ~25 minutes) matched what four ExIt
generations since r6 did not. r4's flat 12 updates started from the BC net (raw 0.47).

## 20. bf16 serving is safe for PPO; block-plan search (2026-11-04)

`python -m tools.selfplay.bf16_logp` (4,096 saved positions, r15 net): KL(trainer numerics ||
bf16 serving copy) mean **0.00001** (p99 0.00017), |d logp(top)| mean 0.001 (p99 0.013), against
PPO's ~0.015 per update. r15 resumed at update 15 with --infer-bf16: update ~88 s (from ~95),
iteration ~113 s (from ~140).

Blocks were the one big decision the search could not touch: the engine ran all of combat in
one call. `Executor.combat_step` is now `combat_attacks` + `combat_blocks` (byte-identical
games; engine suite 2 failed by design / 3505 passed), and `games._play` has an opt-in
`pre_blocks` boundary for a policy with a `before_blocks` hook (the selfplay router), where
`Searcher.plan_blocks` searches up to 6 block assignments (the network's, none, one blocker moved
to its second choice). Pipeline smoke with the r15 net (`--eval-only --eval-seat eval+search
--search-blocks`, 6 deals): 8 block plans searched, **4 changed**, 0 simulation errors (attack
plans change ~20%). Strength effect not measured yet.

## 21. The engine spent two thirds of a game finding which zone a card is in (2026-11-04)

cProfile of 12 self-play games (a seat that encodes every decision like NetAgent, vs the
heuristic): `GameWorld.zone_of` 10.2 s of 15.4 s. 834K calls, each scanning every zone of every
seat (libraries first) with the dataclass `Handle.__eq__` (53M calls, 4.8 s); the main caller is
the trigger binder's `controller_of` (~700K calls). `MTG_bot/core/state.py:zone_of` now remembers
each card's last zone and re-validates membership before returning it (a stale entry falls
through to the historical scan, so no code path can make it answer wrong). Profiled 15.4 s ->
8.5 s; `tools/selfplay/zone_identity.py` 20 seeded games old vs new **20/20 identical** (digest,
world fingerprint, end reason), 12.3 s -> **5.8 s**; engine suite unchanged (2 by-design fails /
3505 passed) and 85 s -> 68 s. r15's workers went from **20.5 to 38.2 games/s**.

The PPO trainer (~88-98 s per 98K-step update, GPU-bound) is now the bottleneck: workers can
outrun it, and the update took the whole buffer, so batches would have grown every update.
`next_job` gives no training game while a full next batch waits (`throttled` in the iter event).

## 22. r15 teacher stage done: raw network 0.598 vs heuristic; self-play begins (2026-11-04)

Greedy teacher evals (400 games each): update 5 0.556, 10 0.566, 20 0.581, 25 0.596,
**30 0.598** [0.548, 0.646]. Paired over 98 shared deals, update 30 vs its start (r14 ExIt net)
**+0.074** [+0.031, +0.120] (20 deals better, 4 worse); vs the original BC net **+0.138**
[+0.082, +0.196] (27 vs 4). Training-game win rate (sampled play, ~2,000 games per update): mean
0.537 over updates 1-5, ~0.59-0.61 over 26-31.

Forced exit at update 30 (gate 0.65 not reached): v1 frozen at update 31, stage selfplay
(70% vs v1, 15% heuristic, 15% past versions). First self-play update: 0.512 vs v1, 0.625 vs
heuristic. Elo (random = 0, 1,174 games): heuristic 414, v0 448, **v1 484** (v1's ladder partial).

## 23. Self-play gates and dropping the KL anchor (2026-11-04)

Self-play updates 32-40: training games vs v1 0.495-0.533 (mean ~0.515), vs heuristic 0.53-0.64,
vs v0 0.54-0.60. Gate after update 35 (4 updates past the freeze): **0.4885** [0.4394, 0.5379]
vs v1 (not passed; the gate needs >= 0.55 with the Wilson lower bound > 0.5).

Self-play iterations took ~130 s (update ~90 s + ~39 s collect): both seats are networks, so
inference doubles and the GPU is shared three ways. Resumed at update 40 with `--kl-anchor 0`:
the anchor costs one extra forward of the frozen net per minibatch (~25% of the update), and at
0.01 it did not hold the policy anyway (KL to v0 reached 0.21 by update 30) - PPO's clip and one
epoch at lr 1e-4 bound each update (KL ~0.01-0.02). Gates 300 deals (600 games), ladders 150.

## 24. Second engine hotspot: the trigger binder's controller lookups (2026-11-04)

After §21, `Binder.on_events` was 3.24 s of 8.0 s in the same 12-game profile, 2.36 s of it in
`_controller_of` (the matching itself, `_match_node`, 0.02 s): per journal event it looked up the
controller of every attached trigger's source (twice on a match) and of every card in the world,
granted abilities or not. Matching one event moves no card, so the lookup is now memoised for
one event's pass and skipped for hosts with no granted ability
(`MTG_bot/core/executor/binding.py:_controller_memo`). on_events 3.24 -> 0.88 s; profiled games
8.0 -> 5.8 s (15.4 -> 5.8 s with §21, **2.7x**). `python -m tools.selfplay.games_hash` (30 seeded
games): hash `2a01d4c6824fab56` before and after, 6.4 -> 4.5 s. Engine suite unchanged
(2 by-design / 3505 passed, 49 s).

## 25. The deployed model: v1 + search = 0.651 vs heuristic (2026-11-04)

`python -m tools.selfplay.learner --run runs/selfplay/e1_v1_search --init runs/selfplay/r15_ppo/v1.pt
--eval-only --eval-seat eval+search --eval-opponents heuristic --eval-deals 150 --search-blocks
--search-k 3 --search-d 2 --search-skip-p 0.99 --infer-bf16` (v1's own value head at the leaves):
**0.6507** [0.5944, 0.7031] over 292 games; paired vs raw v1 on the same 146 deals (teacher:it30)
**+0.0599** [+0.0188, +0.1027] (26 deals better, 10 worse). Elo-equivalent vs the heuristic
(414): ~522. Search changed 29% of searched acts (1,095 / 3,767), 36% of attack plans
(299 / 833) and **54% of block plans** (166 / 308); 220 / 28,440 simulations errored (scored 0).

Control without block search (`runs/selfplay/e2_v1_search_noblocks`, same command minus
`--search-blocks`): **0.6552** [0.5988, 0.7075] over 290 games, +0.0638 [+0.0190, +0.1103] over
raw v1. With minus without blocks, paired over 145 deals: **-0.0034 [-0.0345, +0.0241]** (9 vs 10
deals). The block search changes 54% of block plans and moves nothing: at d 2 worlds and v1's own
value head those changes are ties or noise, like the act search's (§16). `--search-blocks` stays
off by default; the pre-blocks boundary stays for a better leaf value.

## 26. Self-play is serving-bound: bigger slot groups (2026-11-04)

Self-play gates vs v1: update 35 0.4885, 50 0.5357, **55 0.5441 [0.5037, 0.5838]** (lower bound
above 0.5, score under the 0.55 freeze line). Training games vs v1 ~0.55, vs heuristic 0.58-0.67;
entropy settled at 0.17-0.18 (0.21 at the start of self-play).

With both seats networks (learner + v1: two forwards per serving batch) the learner's serving
thread ran at 92% of a core while workers idled at 37% CPU. Resumed at update 60 with
`--slots 16 --groups 4` (was 8 x 2) and `--save-every 1` (state each update, so a restart no
longer drops the gate queued with every fifth save): mean inference batch 67 -> 120, collect per
update 41 -> 25 s, games/s over the iteration 18 -> 21-24, iteration ~110 -> ~93 s. The PPO update
(~68 s for 98K steps) is the bottleneck again.

## 27. Freeze on significance, not on 0.55 (2026-11-04)

Gates vs v1: update 50 0.5357 [0.4953, 0.5757], 55 **0.5441 [0.5037, 0.5838]**, 65 **0.5449
[0.5046, 0.5847]** (600 games each): two gates running significantly above v1, stuck under the
0.55 line for 15 updates while the vs-heuristic training win rate kept rising (0.603 -> 0.622 by
10-update block). The 0.55 line was a convention (AlphaGo Zero's), not the owner's rule ("some
elo/winrate increase should trigger a re-freeze"). Resumed at update 67 with `--gate-score 0.5`:
a version is frozen when the 600-game gate's 95% Wilson lower bound is above 0.5 (score >~ 0.541),
i.e. when the learner is significantly better than the newest frozen version. Smaller, more
frequent steps; the Elo ladder still places every version.

**First self-play re-freeze.** Gate after update 70: **0.5515 [0.5113, 0.5911]** vs v1 (600 games;
would also have passed 0.55) -> v2 frozen at update 71. v2's ladder: vs random 0.946 (296 games),
vs heuristic **0.613** [0.556, 0.667] (292). Elo (random = 0, 2,354 games): heuristic 412.6,
v0 446.6, v1 473.3, **v2 503.0** - each version ~+27-30 over the last.

## 28. v3, and the search's gain shrinks as the network improves (2026-11-04)

Gate after update 85: **0.5488 [0.5086, 0.5884]** vs v2 (14 updates after v2's freeze; the
update-80 gate was 0.4966) -> v3 frozen at update 87. v3 vs heuristic **0.625** [0.568, 0.679],
vs random 0.949. Elo (random = 0, 3,536 games): heuristic 412.6, v0 446.7, v1 467.8, v2 493.5,
**v3 518.2** (+21, +26, +25 per freeze).

v2 + search (k 3, d 2, no blocks; `runs/selfplay/e3_v2_search`): **0.6575** [0.6014, 0.7096] over
292 games; paired vs raw v2 (ladder:v2, 145 deals) +0.0448 [+0.0069, +0.0828]; vs v1 + search on
the same deals +0.0034 [-0.0379, +0.0483]. v1 gained +0.064 from the same search. The sharper
network leaves the search fewer asks (searched 2,715 / skipped 5,155 at top >= 0.99; v1: 3,605 /
4,119), and the searched model sits near 0.66 either way: this shallow search (3 candidates,
2 worlds, leaf at the next turn, the network's own value head) has a ceiling of its own.

## 29. The only crash in 9,036 eval games: Kinetic Augur's undefined power (2026-11-04)

r15's eval rows: 8,996 decided, 16 mutual draws, 6 turn-cap draws, **18 void-crash, all one deal**
(seed 900165, coherent decks; 18 of its 28 games), all `ValueError: executor: POWER undefined on
handle card:77` = Kinetic Augur (printed */4). Reproduced with a v2 seat vs the heuristic: 8 of
24 games crash (`cast -> _settle -> fire_all -> _v_deal_damage -> quantity._prop_value`); the
heuristic and random seats never do (0 of 41). A damage-equal-to-power effect reads the Augur's
power, whose characteristic-defining ability the engine does not model: the registered /99
shape-gap (`MTG_bot/core/executor/quantity.py:569`), strict by design (never a guessed zero). The
networks play into it where the heuristic does not; training voids ~0.35% of games. Fix =
modelling the CDA (CR 604.3), engine-track work. 116 of 9,036 rows carried a leaky ask
(CHOOSE_NAME), voided in eval by design.

## 30. vs-heuristic progress flattens after ~update 60 while the self-play ladder climbs (2026-11-04)

Training-game win rate vs the heuristic by 10-update block (sampled play, ~3,000 games per
block, SE ~0.009): 0.544, 0.571, 0.587 (teacher), 0.603, 0.600, 0.611, **0.625, 0.630, 0.622,
0.618** (self-play, updates 61-100). Greedy frozen versions vs heuristic: v1 0.598 (382 games),
v2 0.613, v3 0.625 (292 each) - rising inside the noise. Gates vs v3 after its freeze (update
87): 0.5025, 0.5396 [0.4994, 0.5793], 0.4983. The Elo steps (v2 +26, v3 +25) come mostly from the
head-to-head gate games against the predecessor. Health normal (KL ~0.013 per update, entropy
~0.19, explained variance ~0.77). Levers if it persists: opponent mix (more past versions /
heuristic, or win-rate-weighted league sampling), a decaying learning rate, a larger network.
