# Design: decision latency under a championship clock

Status: **proposed.** Referenced by [`NORTH_STAR.md`](../NORTH_STAR.md) §1a and by
`tools/latency/bench.py:3`. Every number below is either measured on this box, counted from the
code, or derived by arithmetic that is shown so you can check it. Verified against working-tree
`000e37c`.

This document answers one question the owner made binding: **can we afford a bigger model under a
real match clock, and how does the agent learn to spend that clock itself?**

---

## 0. The four findings that set the frame

**(i) The literal world championship final is untimed.** MTR Appendix B: *"Single-elimination final
matches—no time limit."* The clock that actually binds is the Swiss rounds you must survive to reach
the final (50 minutes head-to-head, 75 minutes for a multiplayer pod), the 90-minute
quarter/semifinal, and MTR 5.5 Slow Play, which says players must act in a timely fashion
*"regardless of the complexity of the play situation."* That last clause is the exact refutation of
the owner's stated hard part. The rules grant no allowance for a complicated board. Design against
that, not against a sympathetic judge.

**(ii) The clock has room, but the room is ~3.5×, not ~650×.** §1 derives a per-priority-window
budget of **140 ms** at the pessimistic end. §2 projects the current 250M-parameter model at eight
reasoning passes, CUDA-graphed on the GB10, at **~40 ms end to end including the environment**. The
answer to "test before committing to a bigger model" is *yes, go bigger* — but the honest headroom
is a factor of three to four at the tight end, not two orders of magnitude. Anyone quoting a 650×
margin is quoting `tools/latency/shapes.py:347`, which divides by the full 273 GB/s with no
streaming derate and adds a hardcoded 20-launch residual. §5 fixes both.

**(iii) A parameter inside the pass loop costs forty times a parameter in the board encoder.** At
eight passes × five autoregressive plan steps, `ActionSequenceDecoder`'s 4-layer stack
(`model.py:94`, 50,401,280 params) is read **40 times per decision**. It is 16% of the parameters
and **86.6% of the decision's weight traffic**. The board encoder is 2.7× larger and costs 5.8%.
On a bandwidth-bound machine this is the single most important input to the approved rebuild.

**(iv) The thing that actually threatens the clock is decision *count*, not model size.**
`engine.py:145-148` emits one `DeclareBlockerAction` per (blocker, attacker) pair. A 20-attacker /
20-blocker Commander board is 400 menu entries **and up to 400 sequential engine steps, each one a
full model call.** Menu *width* is measured free (A=1 → 87.2 ms, A=256 → 95.3 ms, +9%). Sequential
*count* is linear in the match clock. Fixing the action space is worth more clock than any kernel
optimisation in this document.

---

## 1. The latency contract

### 1.1 What the rules actually say

| Rule | Content | Source |
|---|---|---|
| Minimum match time | **40 minutes**, any match | MTR App. B |
| Swiss round, Constructed & Limited | **50 minutes** | MTR App. B |
| Single-elim quarter/semifinal | **90 minutes** | MTR App. B |
| **Single-elim final** | **no time limit** | MTR App. B |
| End of match, 1v1 | Active player finishes their turn, then **five additional turns**. Incomplete game = **draw** | MTR 2.4 |
| Slow Play | *"regardless of the complexity of the play situation"* | MTR 5.5 |
| Slow Play penalty | Warning; **two additional turns are added** to the end-of-match extension | IPG 3.3 |
| **Multiplayer pod (Commander)** | **75 minutes** Swiss, **no additional turns**; active player finishes their turn, then **draw**; hard 15-minute last-turn cap; single-elim untimed | Multiplayer Addendum |

**A correction to the framing, offered respectfully.** There is no "skipped turn" punishment in
paper Magic. The three real punishments are sharper and all implementable in the environment:

1. **An unfinished game is a draw** — in Swiss that is 1 match point instead of 3, so a draw is
   worth *half a loss*, not zero.
2. **A Slow Play Warning gives the opponent two extra turns.** Being slow is a gift, not merely
   self-harm.
3. **A second Warning is a Game Loss.**

`NORTH_STAR.md:33` says "a decision that arrives too late is worth zero." That is close, but the
real rule is better, because it is what the environment can implement directly.

### 1.2 The budget arithmetic

**Commander, 75-minute Swiss pod, four seats, one game per round.** This is the priority format
(`NORTH_STAR.md:57`), so it sets the contract.

```
Round clock                                            4,500 s
  − seating, shuffle, mulligans                         −300 s
                                                       --------
Play time for the pod                                  4,200 s
Per seat (even split)                                  1,050 s
```

Two decision-count regimes, and the gap between them is a design choice we control:

*Regime A — every priority window is a model call.* This is what the code does today. Measured:
1,500 decisions per game in a two-player match, **21.2% of which have exactly one legal move** and
**75.5% of whose offered options are `ActivateManaAbilityAction`**. A four-seat pod with real
priority is materially higher; call it **2,500 per seat**.

*Regime B — substantive decisions only.* A window with exactly one legal action is not a decision
(that is CR, not a heuristic). 15 turn cycles × 4 seats = 60 turns; our seat faces ~8 substantive
windows on each of its own 15 turns and ~3 on each of the other 45. **255, round to 250.**

```
Regime A   1,050 s / 2,500 =   420 ms per priority window
Regime B   1,050 s /   250 = 4,200 ms per substantive decision
```

**Two-player Constructed, 50-minute Bo3**, for comparison:

```
3,000 s − 360 s sideboarding − 270 s pregame = 2,370 s play; halve → 1,185 s per player per match
÷ 2.4 games per match                                          →   494 s per game
11 turn cycles × ~12 substantive decisions                     →   132 decisions
                                                               → 3,745 ms per substantive decision
```

**Commander is the *looser* format per decision, not the tighter one** — one game per round instead
of three, and a longer round. That is the opposite of the intuition and worth stating: the King
Goal's priority format is not the binding one for latency.

### 1.3 The contract, and where the margin goes

The margin does **not** go on the per-decision figure. It goes on `N`, because that is the number
the measured engine understates. Targeting is structurally broken — `effect_handlers.py:111` reads
`effect.get("target")` while the card DB carries `selector` on 117 of 397 cards and `target` on 10 —
so every targeted spell currently offers exactly one option. `MakeChoiceAction` fired **0 times in
3,000 decisions**. Block declaration is per-pair, not a combinatorial assignment. Real targeting
alone is a 10–30× multiplier on the CastSpell branch.

> ### The contract
>
> | | Value | Provenance |
> |---|---|---|
> | **Bank `B`** | **1,050 s** per seat per match | MTR Multiplayer Addendum, 75-min pod, 4 seats |
> | Priority windows per seat, measured floor | 2,500 | `tools/latency/positions.py` corpus, scaled to 4 seats |
> | **Design `N`** | **7,500** | 3× the floor, for real targeting, real choices, real priority |
> | **Engineering target `µ = B/N`** | **140 ms** per priority window | The number to build against |
> | Same, at the measured floor | 420 ms | The number if the action space does not grow |
> | Same, substantive decisions only | 4,200 ms | The number a real client would see |
> | **Hard rail** | anytime interrupt at `2 · B̂/N̂` | Derived by the agent, not authored. §4 |

**There is no authored per-decision deadline and no tier ladder in this design.** A fixed ceiling is
exactly the hand-tuned clamp `NORTH_STAR.md` §3 defaults to *no* on, and it is also wrong on its own
terms: it is wasteful on the 21.2% of windows with one legal move and inadequate on a lethal-blocks
decision at turn 40. The only hard rail is a non-termination interrupt whose threshold the agent
computes from its own remaining bank and its own estimate of remaining decisions.

### 1.4 The acceptance criterion, and why p99 is the wrong target

State the criterion as an outcome, not a percentile. With `N` priority windows per seat per match
and per-window miss probability `q`:

```
P(≥1 forfeited decision per match) ≈ 1 − (1−q)^N

N = 2,500   q = 1e-2 (p99)    → P ≈ 100%   several misses every match
            q = 1e-3 (p99.9)  → P ≈  92%   near-certain
            q = 1e-4          → P ≈  22%
            q < 4.0e-6        → P <   1%   ⟸ the criterion
```

**To meet a 1% match-forfeit target you must control the p99.9996, not the p99.** No sampling of a
few thousand positions estimates that percentile directly, which is why the criterion is stated as a
*resampled match simulation over a fitted tail* (§5.2), and why the mitigations in §4 are structural
— bucketing, graphs, anytime interrupt — rather than statistical. **The anytime interrupt is what
makes the criterion achievable at all:** it converts an unbounded tail into a bounded one, at the
price of a lower-quality action. That is the anytime trade, and it is why the reasoning loop must be
interruptible.

Weight the miss rate by what is at stake. A missed deadline on "tap a land for mana" — 75.5% of all
options offered — costs nothing. A missed deadline on a block assignment loses the game. **Report
value-weighted miss rate alongside raw miss rate**, using the value spread
`max_a Q̂ − Σ_a π(a)Q̂` the model already computes.

---

## 2. What one decision costs on the GB10

### 2.1 The roofline, from a parameter table that reproduces exactly

Derived analytically from `model.py` at `config_rl.py:31-37` defaults (d=1024, nhead=16, 16 encoder
layers, 4 decoder layers, `dim_feedforward=2048` — the PyTorch default nobody chose, `model.py:38`,
`model.py:93`). The total reproduces the reported 315,666,955 exactly, so the split is trustworthy.

| Block | params | reads per decision | why |
|---|---|---|---|
| `card_embedder.atomic_embedding` | 51,200,000 | **T rows only** (214 × 2 KB = 0.44 MB) | gather, not a matmul |
| `card_embedder` dense | 3,181,568 | 1× | |
| `board_encoder`, 16 × 8,399,872 | 134,397,952 | 1× | `model.py:206` |
| `rnn` LSTMCell + `temporal_fusion` | 10,494,976 | 1× | `model.py:218`, `model.py:224` |
| `opponent_predictor` | 1,574,400 | 1× | `model.py:226` |
| `reasoning_head` live path | 6,825,984 | 1× **per pass** | `model.py:235` |
| `reasoning_head.action_fusion` | 2,098,176 | 1× per pass from pass 2 | `model.py:61-64` |
| `decoder` proj / value / plan-query | 1,118,209 | 1× per pass | `model.py:163`, `:170`, `:180` |
| **`sequence_decoder` 4-layer stack** | **50,401,280** | **5× per pass** | `model.py:117`, unconditional |
| `sequence_decoder` type/src/tgt heads | 2,109,450 | 5× per pass | `model.py:124-126` |
| `reasoning_head.action_memory_embedder` | 51,200,000 | **0×** | declared `model.py:56`, never called |
| `decoder.intent_proj` | 1,049,600 | **0×** | declared `model.py:152`, never called |
| **Total** | **315,666,955** | | ✓ |

bf16, 2 bytes per parameter:

```
fixed    = (3,181,568 + 134,397,952 + 10,494,976 + 1,574,400) × 2 B + 0.44 MB gather = 299.7 MB
per pass = (6,825,984 + 1,118,209 + 5 × (50,401,280 + 2,109,450)) × 2 B             = 541.0 MB

1 pass  : 299.7 + 541.0                  =   841 MB
8 passes: 299.7 + 8 × 541.0 + 7 × 4.2    = 4,657 MB
```

**Use 70% streaming efficiency, i.e. 191 GB/s, not the published 273 GB/s.** LPDDR5X at batch 1 with
mixed access patterns does not hit peak, and every projection currently in
`reports/latency_devbox.json` is optimistic by 1.43× because `shapes.py:347` divides by the full
figure.

| | weight traffic | bandwidth @191 GB/s | real kernel launches (measured) | ARM dispatch @6–10 µs | **eager** | **CUDA-graphed** |
|---|---|---|---|---|---|---|
| 1 pass | 841 MB | **4.40 ms** | 515 | 3.09–5.15 ms | **7.5–9.6 ms** | **≈4.5 ms** |
| 8 passes | 4,657 MB | **24.37 ms** | 3,925 | 23.55–39.25 ms | **48–64 ms** | **≈24.5 ms** |

Launch counts are from `TorchDispatchMode`, metadata-only ops excluded. They are a property of the
graph, not of the silicon, and they transfer exactly.

Plus environment CPU: `convert_graph_to_tokens` measures **14.5 ms mean / 19.7 p99 / 23.7 max** on
x86; a Cortex-X925 is within roughly ±30% for pointer-chasing Python, so **12–20 ms**.

> **End to end, CUDA-graphed, 8 passes: ≈ 40 ms.** Against the 140 ms engineering target: **3.5×**.
> Against the 420 ms measured-floor target: 10×. Against a substantive-decision reading: 105×.

### 2.2 Where to spend the next parameter

Weight traffic per decision barely moves with token count — the embedding table is *gathered*, so
T=214 and T=512 differ by 0.6 MB out of 841. What `T` buys is FLOPs and attention. GB10's batch-1
balance point is

```
125e12 FLOP/s ÷ 191e9 B/s = 654 FLOP per byte
```

| Block | FLOP/byte | verdict |
|---|---|---|
| Board encoder, T=214 | 225 | bandwidth-bound (0.48 ms compute vs 1.41 ms bandwidth) |
| Board encoder, T=512 | 575 | near balance (1.24 ms vs 1.41 ms) |
| Board encoder, T=1024 | 1,278 | **compute-bound** |
| Plan decoder, 5 AR steps | **61** | 10× below balance — pure bandwidth waste |

At 8 passes the plan decoder's 4-layer stack is **86.6% of decision bandwidth** (90.2% including its
heads); the board encoder is **5.8%**.

> **Sizing rule for the rebuild: spend parameters in the once-per-decision encoder and in token
> count. Be miserly in anything inside the reasoning-pass loop or the autoregressive loop.** A wider
> encoder over more tokens is nearly free until T ≈ 1,000. A deeper plan decoder costs 40×.

Two corollaries worth saying out loud:

- **Deleting the 102 MB of dead weights (`action_memory_embedder`, `intent_proj`) buys exactly zero
  latency.** They are never read. Deleting them buys optimiser state and capacity, nothing else. Do
  not let anyone claim a speedup for it.
- **The affordable budget.** At the 140 ms target with 15 ms of environment, 125 ms of GPU at
  191 GB/s is **23.9 GB of weight traffic per decision** against today's 4.66 GB — roughly **5×**,
  and ~29× at the 420 ms target. That is the honest size licence.

### 2.3 The throughput gate — and it is the GPU, not the environment

This is where the size decision is actually made, and the intuitive attribution is backwards.

```
Batch is structurally pinned to 1: the policy pointer's output length equals the legal-move
count exactly (model.py:172) — no padding, no mask. So every worker's forward serialises
onto one GPU.

GPU, graphed, 8 passes : 24.4 ms/decision  →      41 decisions/s aggregate
Environment, 19 workers × 15 ms            →   1,267 decisions/s aggregate
```

**The GPU is the throughput wall by a factor of 31.** Not the environment. The environment runs at a
27% duty cycle inside a 40 ms decision, so 19 workers need about 5 of the 20 ARM cores, not 19.

```
Self-play volume: 1,500 decisions/game × 50 episodes × 1,000 generations   (config_rl.py:7-9)
                = 75,000,000 decisions

batch 1, GPU-serialised                          : 75e6 /    41 =  21 days of pure GPU
batch 32, weights amortised (0.76 ms/decision)   : 75e6 / 1,313 =  16 hours GPU,
                                                   environment now co-equal
```

> **Unpinning batch=1 is worth roughly 30× on training throughput and is the prerequisite for
> everything else in this document.** It is also the prerequisite for CUDA graphs. It is the highest
> leverage change in the repository, and it costs one padding mask on the pointer head.
>
> **Model-size gate, stated as an inequality rather than a percentile:**
> ```
> bytes_per_decision / 191e9 × 75e6 / parallelism  ≤  acceptable wall-clock
> ```
> `bytes_per_decision` comes from `tools/latency/shapes.py:294` and is machine-independent;
> `191e9` is validated by one DGX calibration run. The size decision hangs on that inequality and on
> the §1.3 contract, not on a p99.

### 2.4 The plan as a compute amortiser — directive (b) pays twice, but not 5×

`train.py:223-306` already executes plan steps 1–4 against the live environment, re-scoring the
current legal moves with only `decoder.action_proj` + `torch.mv` under `no_grad`
(`train.py:249-251`). That path skips the whole trunk.

But it does **not** skip the environment: `env.step()` still returns `_get_obs()`
(`environment.py:237-243`), which re-tokenises at 14.5 ms. So the amortisation applies to the model
only:

| | 5 separate decisions | one 5-step plan | speedup |
|---|---|---|---|
| Today, 8 passes graphed (24.4 + 15) | 197 ms | 24.4 + 5×15 + 4×1 = 103 ms | **1.9×** |
| 1 pass graphed (4.4 + 15) | 97 ms | 4.4 + 75 + 4 = 83 ms | 1.2× |
| **A 5× bigger model (122 + 15)** | **685 ms** | 122 + 75 + 4 = **201 ms** | **3.4×** |

> **Plan amortisation is not a fix for today's model. It is what makes the bigger model
> affordable.** The lever grows exactly as the model grows, which is the regime the rebuild is
> heading into. Training every plan step (directive (b), `NORTH_STAR.md` §5) is therefore
> simultaneously the quality fix the owner mandated and the latency lever that pays for the size
> increase.
>
> The machinery is 90% present and mislabelled. `train.py:295-298` pushes every plan step into the
> buffer with **step 0's `log_prob` and step 0's `value` reused verbatim**, and with
> `"action": best_move_idx` indexing `current_legal` while the stored `obs` holds descriptors over
> the *full* list. Fix the labelling and the same code pays both ways.

---

## 3. How the agent learns to allocate its own clock

### 3.1 What exists today, and why it cannot work

```python
# model.py:243-247
predicted_first_type = torch.argmax(res["plan_sequence"][0]["type_logits"], dim=-1)
is_rethink_requested = (predicted_first_type == 9).any()
if not is_rethink_requested and p >= 0:   # p >= 0 is always True
    break
```

Token 9 is `RETHINK` (`model.py:88`). The head that decides it, `type_head` (`model.py:97`),
**receives no gradient anywhere in the repository**. `threshold` is accepted at `model.py:201` and
never referenced in the body; `config_rl.py:41`'s `thought_threshold = 0.2` does nothing. So the
halting decision is made by an argmax over an untrained head, from evidence that says nothing about
whether another pass would help, at zero cost.

Three things are missing: **inputs, a gradient, and a price.**

### 3.2 The price — the clock as an environment resource

The textbook answer is an ACT-style ponder cost, `loss += λ · n_passes`. It is what
`docs/BACKLOG.md` currently proposes, and it is exactly what `NORTH_STAR.md` §3 forbids: an authored
penalty with a hand-tuned coefficient, shaping the objective away from winning. **Reject it.**

Instead, `MTGEnv` gains a per-seat bank and applies the actual tournament rule.

```
bank[seat] -= cost(decision)          every decision
bank[seat] == 0   ⇒  the seat force-passes every remaining priority window
match clock == 0  ⇒  MTR 2.4 / Multiplayer Addendum end-of-match procedure:
                     1v1  — five additional turns, then incomplete ⇒ DRAW (0.5 return)
                     pod  — active player finishes their turn, then DRAW
```

**No penalty term is attached to bank exhaustion.** A seat that force-passes every window loses on
its own, and that loss is already in the return. Incentives, not rules.

**Is this shaping? No, and the distinction is the one `NORTH_STAR.md:130-132` draws.** The
tournament clock is *how the game works*, not *how to play well*. There is no λ. The only authored
numbers are the round length and the seat count, and both come from MTR Appendix B and the
Multiplayer Addendum.

This buys something the compute allocator was never the point of: **§1.1's draw rule changes correct
play.** Ahead on board with a short clock, take the faster line even at some EV cost — a draw is
half a loss. Behind with a short clock, the draw is a *good* outcome and grindy lines a fresh game
would reject become correct. At the five-additional-turns boundary the value function is
discontinuous: a lethal that needs six turns is worth exactly zero. **Remaining clock and remaining
turns therefore belong in the state fed to the *value function*, not merely to the halting head.** A
value head blind to the clock is systematically wrong in precisely the positions that decide
tournaments. This is a strength gain, not a latency fix.

### 3.3 The gradient — halting as a sampled policy action

Replace the argmax at `model.py:243-244` with a `stop_head` emitting a Bernoulli logit from the
pass-`p` summary. Sample it during collection. Its log-probability joins the action log-probability
in the *same* PPO objective at `student.py:180-181`:

```
log π_joint = log π_action(a | s) + Σ_p log π_halt(h_p | s, p, clock)
PPO ratio on the joint; same advantage A_t for both terms.
```

That is the whole incentive. No new loss term, no coefficient. If pass 5 changed the chosen action
into a better one, the advantage credits both the action and the decision to take pass 5. If pass 5
changed nothing and burned bank that a later decision needed, the advantage debits both.

**Why the long-horizon cost reaches PPO at all.** The cost of thinking at decision `t` is felt at
decision `t+400`, and PPO will not bridge that on its own. With `bank_remaining` in the observation,
the successor state after CONTINUE has a strictly lower bank, so

```
A(CONTINUE) = r + γ·V(s', bank − c) − V(s, bank)  ≈  γ · ∂V/∂bank · (−c)
```

which is **immediately negative and locally computable**. The value function compresses the
long-horizon cost into a one-step TD error. No shaping term needed. This is the trick the whole
design rests on, and §9 records honestly that it depends on `V` becoming accurate in the bank
dimension, which early in training it is not.

Two supporting changes are required, not optional:

- **Straight-through Gumbel-softmax replaces hard-argmax teacher forcing** at `model.py:138-140`.
  Today `action_type_embed.weight` has identically zero gradient and `type_head` has `None`. This is
  also what directive (b) needs, so it is shared work.
- **Two auxiliary heads, both supervised on genuine observables, neither in the policy gradient:**
  `N̂` (decisions remaining this game, SmoothL1 in log space — the *denominator* of the budget, and
  it must be learned rather than looked up from a turn-number table, because measured decisions per
  turn range from 12.0 to 28.5 across turn buckets) and `P(time-forfeit before game end)` (BCE
  against observed forfeits, to bootstrap `∂V/∂bank`).

### 3.4 What the halting head must observe

Add a single **clock token** prepended to the board sequence, so it flows through the existing
encoder with no new pathway — the same pattern `DESIGN_CARD_POOL.md` uses for pool tokens. Do not
concatenate it onto every entity token.

| Feature | Why | Status today |
|---|---|---|
| `bank_remaining / bank_initial`, and `log(bank_remaining)` | resource level; the value of time is multiplicative near exhaustion | new |
| `spent_this_decision`, `passes_taken` so far | proprioception; a loop that cannot see its own depth cannot halt | new |
| `N̂`, and `bank_remaining / N̂` | the affordable mean, handed over rather than synthesised from a division | new head, §3.3 |
| `ĉ_next / bank_remaining` | cost of the next pass **as a fraction of the bank**, never in milliseconds | §3.5 |
| `turns_remaining`, including the five-additional-turns rule | makes the draw discontinuity visible to `V` | new |
| **`KL(π_p ‖ π_{p−1})`** and **`\|V_p − V_{p−1}\|`** | the load-bearing signal | derivable in-loop |
| policy entropy, top-1 margin, top-1 churn across passes | uncertainty | free at `model.py:249` |
| value spread `max_a Q̂ − Σ_a π(a)Q̂` | how much is at stake here at all | free |
| `log A`, `log T` | complexity proxies | free (`get_legal_moves` is 0.43 ms) |
| **phase / step / priority holder / is-my-turn** | **the network currently cannot see any of these** | `convert_graph_to_observation` (`state_converter.py:143-167`) computes them and every consumer discards the result. Wire it in. |

The KL-and-value-delta pair is the core claim, so state it flatly:

> **The right halting question is not "is this position complex?" but "would another pass change my
> answer?"** Complexity proxies predict *cost*. Policy movement predicts *value*. A 40-permanent
> board with one obviously-lethal attack deserves one pass; a three-permanent board where two lines
> are within half a percent deserves ten. This converts Russell & Wefald's unobservable `E[ΔV]` into
> a quantity the agent measures on-line about itself — an empirical anytime profile, sampled live,
> per position. `res` is already in scope from the prior loop iteration at `model.py:232-247`; the
> KL is one softmax and one dot product over `A ≤ a few hundred`, free next to a ~51 ms pass.

### 3.5 What is charged at train time

Wall-clock is the wrong currency at training time, for four reasons that can each be substantiated:

1. Training runs on different hardware from play; a millisecond means something different.
2. **Training-mode forward is a different model.** `student.py:102` calls `self.model.train()` when
   `requires_grad=True`, so dropout is active while acting (184 `aten.native_dropout` calls
   measured) and attention falls off the fused-SDPA path (125 `bmm` + 56 `_safe_softmax` instead of
   40 fused SDPA). The agent would learn frugality about a cost that does not exist at play time.
3. Measured wall-clock is noisy and non-stationary — `reports/latency_devbox.json` shows
   `round_spread_pct` of 41.7% and 63.4% on two rows. A noisy cost on a resource is a noisy reward.
4. Twenty concurrent workers on one node corrupt each other's clocks, and actor and learner would
   disagree on the cost of the same decision — exactly the class of bug `DESIGN_TRAINING.md` §5
   already flags for PPO ratios.

> **The environment charges an analytic, deterministic cost drawn from a table fitted to the
> *target* hardware.** The function already exists: `tools/latency/shapes.py:294` `cost_model(...)`
> → `shapes.py:347` `project_gb10(...)`, scaled by `passes_taken` and plan steps actually executed.
> Materialise it as a versioned artifact, `bench/cost_table_gb10_<sha>.json`. Self-play never reads
> a wall clock.

Properties this buys: determinism and replayability (identical cost for actor and learner);
portability (the policy is fed `ĉ_next / bank_remaining`, a *fraction*, so retargeting swaps the
table without retraining); speed (no timers in the hot loop); and falsifiability
(`measured_ms / modelled_ms` on the target box is a publishable number — if it drifts past 1.2, the
agent is being undercharged and will be too slow in a real match). Fit the table **pessimistically**
— p90 of the measurement, not the median — add small noise so no exact bucket edge is exploitable,
and emit `cost_table_max_residual_pct` to the logger next to the loss.

**One trap, and it is nasty.** Environment cost is on the match clock too, and it scales with board
size: `_get_zone_priority` (`state_converter.py:81-95`) and `graph.get_controller_id` linearly scan
all 412 relationships for each of 214 entities. If you charge that cost *as a function of board
size*, you have taught the agent that **big boards are expensive**, in the format whose entire
identity is big boards.

> **Charge model cost as a function of what the agent chose (passes, plan steps). Charge environment
> cost as a flat per-decision constant.** This is a lie that protects against a worse one, and it is
> logged as a scaffold in §7. Make tokenisation incremental and it evaporates.

### 3.6 Preventing always-max and always-min

**Always-minimum is prevented only if extra passes actually buy quality — and today they provably
cannot.** `type_head`, `source_head`, `target_head`, `intent_proj` and `action_memory_embedder` all
have `grad is None`; `action_type_embed` is identically zero; and `action_fusion` (`model.py:61-64`),
the *only* path by which pass ≥2 differs from pass 1, is reachable only when the untrained rethink
argmax fires. **A model whose passes are functionally identical will correctly learn to take exactly
one.** This is a hard prerequisite, not a caveat: run the §5.4 quality-vs-passes curve *after*
directive (b) lands, and do not build §3 until it comes back positive.

The cold-start collapse is the failure that will actually happen: early in training the marginal
value of a pass is ≈0, the clock cost dominates, the policy collapses to one pass, the deep-pass
parameters never receive gradient, and the collapse becomes permanently correct. Two responses:

- *Learnable:* a small head predicting **"will pass p+1 change my action?"**, supervised against the
  observed `KL(π_{p+1} ‖ π_p)`. That predicts a measurable fact, not a preferred behaviour, so it
  survives `NORTH_STAR.md` §3. Feed the prediction to the halting policy so the agent explores
  compute where it predicts the answer might move. Note the exploit: the model can learn to make its
  plan artificially unstable to justify thinking. The signature is `passes_taken` rising while win
  rate is flat — alarm on it.
- *Scaffold, declared:* force the halt open to a random depth on a fraction of rollouts so deep
  passes always receive some gradient. PPO absorbs the off-policyness through the importance ratio
  it already computes (`student.py:183`). Logged in §7 with a removal condition.

**Always-maximum is where the arithmetic threatens the mechanism, and it must be said plainly.** The
intended incentive is arithmetic impossibility, but at 40 ms per decision, 2,500 decisions consume
100 s of a 1,050 s bank — **9.5%.** The bank does not bind. **A learned time controller trained
against a budget it cannot exhaust learns nothing.** Two legitimate resolutions, and the owner
should see them together:

1. **Grow until the clock is real.** §2.2 licences ~5× the current per-decision weight traffic at the
   140 ms target. A model whose max-compute policy costs 25%+ of the bank is a model whose time
   controller has something to learn. *This is the direct answer to "test latency before committing
   to a bigger model": the test says yes, and it says the adaptive-compute mechanism needs the
   bigger model to be meaningful.*
2. **Bank randomisation.** Sample the per-match bank log-uniformly and give it to the agent as an
   observation. Because the bank is *in the state*, the network learns a conditional policy
   `π(a | s, bank)` rather than one fixed habit: under a tight sampled bank always-max genuinely
   loses, under a loose one it genuinely wins. This is domain randomisation over a game parameter,
   not a curriculum schedule — but it *is* a deviation from the real game, so it is a scaffold with a
   numeric exit: **remove when the max-compute policy consumes >25% of the real 1,050 s bank.**

### 3.7 Is any of this shaping? The audit

| Mechanism | Kind | `NORTH_STAR.md` §3 verdict |
|---|---|---|
| Win / draw / loss return, with MTR 2.4 draw semantics | genuine objective | Yes |
| Bank and end-of-match as environment rules | rules of the game | Yes — round length and seat count are authored and logged |
| Halting log-prob in the PPO objective | an existing decision becomes part of the policy | Yes; this is the design |
| Bank exhaustion ⇒ forced pass, no extra penalty | the loss it causes *is* the penalty | Yes |
| Clock features in the observation | learned representation | Yes |
| `N̂` and forfeit-probability heads | auxiliary supervision on observables, never in the return | Yes |
| Anytime interrupt at `2·B̂/N̂` | non-termination rail, threshold derived not authored | Yes — logged |
| Emitted-latency quantisation (§4, row 14) | information-leak rail on the output channel | Judgment call; logged as scaffold |
| Entropy bonus on the halting Bernoulli, annealed | standard exploration | Log as scaffold, anneal to zero |
| Bank randomisation | domain randomisation, deviates from the real game | **Scaffold**, numeric exit |
| Forced-random-depth rollouts | scaffold to break cold start | **Scaffold**, measurable exit |
| `loss += λ · n_passes` (ACT ponder cost) | authored penalty, hand-tuned λ | **No. Rejected.** |
| A fixed per-decision ceiling or a tier ladder | hand-tuned cap and schedule | **No. Rejected.** |

---

## 4. The variance problem

`NORTH_STAR.md:35` names the target: *"A median of 3 ms with a 99th percentile of 800 ms is far
worse in a timed match than a flat 60 ms."* The current design produces exactly that pathology —
`current` at 1 pass has a dev-box p50 of 18.95 ms; `current-8pass` has a p99 of 582.32 ms, a **31×
spread from the reasoning loop alone.**

The framing that makes it tractable: **stop trying to make latency low, and make it a lookup.**
Reduce every decision to a small enumerable shape key, pre-measure every key, and the cost of a
decision is *known* rather than measured. p99.9 becomes the maximum over a finite ladder rather than
the tail of an unbounded distribution.

| # | Source | Measured magnitude | Mitigation | Residual |
|---|---|---|---|---|
| 1 | **Reasoning-pass count** | 4.6–5.1× on the real model; 10.5× p50 on the shape stand-in; GB10 4.4 → 24.4 ms | **Desired variance — it is the point.** Make each pass one fixed-cost graph replay so `cost = fixed + k·passes` exactly, and keep the loop **interruptible** (a valid action exists after every pass; `model.py:172` already recomputes logits per pass, but `model.py:249` returns only the last). Add best-so-far retention and a clock check between passes. | The pass distribution *is* the tail. Report it as a distribution; never publish a mean. |
| 2 | **Token count `T`** | 56.4 ms @64 → 132.4 @500 on the dev box; constant at 214 today only because entities are created at init and never destroyed | Bucket to **{128, 256, 384, 512}**, pad, and pass a real `src_key_padding_mask`. `model.py:40` accepts one; `model.py:206` passes `None`. Prerequisite for graph capture. Also: excluding library contents takes 428 → 256 for a 4-seat pod, a correctness fix that is also the largest single variance reduction. | 214 → 256 costs +20% encoder FLOPs. Encoder is bandwidth-bound there, so nearly free. |
| 3 | **Menu size `A`** | **+9% from A=1 to A=256** | Bucket to {16, 64, 256}, mask padded logits with `-inf`. Do it for graph capture, not for speed. | ≈0. **Menu width is a non-problem. Stop budgeting for it.** |
| 4 | **Sequential decision count** | `engine.py:145-148`: one action per (blocker, attacker) pair ⇒ a 20×20 board is up to **400 sequential model calls**, 16 s at 40 ms each, on one combat step | **Collapse block assignment into one structured decision emitted by the plan decoder.** This is what preserved-directive (a), the action tokenizer, is for. | **The only measured mechanism that actually threatens the match clock.** Highest-value fix in this document. |
| 5 | **Plan length / no KV cache** | 6.17 ms @1 step → 31.67 @5; `model.py:117-121` re-runs the whole growing prefix each step, O(L²) where O(L) suffices | Static preallocated KV cache. Honest note: at L=5, batch 1, the *bandwidth* saving is small — the reason to do it is that graph capture needs static buffers. | none |
| 6 | **Forced device syncs** | `next_type.item()` **twice per plan step** at `model.py:142-143`, into a branch whose body is literally `pass` — 10 syncs/pass, **80 at 8 passes** | **Delete `model.py:142-143`.** A literal no-op costing 80 host-device serialisations and blocking graph capture outright. | none |
| 7 | **Host control flow between passes** | `argmax(...).any()` at `model.py:243-244` | One graph replay = one pass; the host reads a single scalar between replays. **1 sync per pass, not 10.** | ~5–20 µs/pass, bounded |
| 8 | **Kernel launch / ARM dispatch** | 515 launches @1 pass, **3,925 @8** — 3.1 → 39.3 ms of pure dispatch before a byte is read | CUDA graphs, one capture per (T, A, pass-count) bucket. Needs #2, #3, #6. | Largest single GB10 win, ~2.4× |
| 9 | **Environment tokenisation** | **14.5 ms mean / 19.7 p99 / 23.7 max** — O(entities × relationships) at `state_converter.py:81-95` | Incremental / dirty-set tokenisation from the engine's already-built-and-discarded event list; relationship indexes; overlap it with the GPU by tokenising the next state during the current forward. Free win: `zone_ids`, `controller_ids` (`state_converter.py:56-57`) and the whole 64-dim observation vector are built every step and never consumed. | **The largest CPU tail and the least graph-able part of the system.** |
| 10 | `get_legal_moves` called twice | 0.43 ms mean, 1.86 max — `environment.py:128` and again at `environment.py:243` | Call once, cache, index *that* list. Also fixes the correctness bug where `step` re-derives a fresh list and indexes it with an index computed against a different one. | small but free |
| 11 | **Batch pinned to 1** | `model.py:172` output length = menu length | Fixed by #3. Prerequisite for graphs *and* for the 30× throughput win in §2.3. | none |
| 12 | **`.train()` mode while acting** | `student.py:102`; 184 dropout ops, fused SDPA lost | Collect in `eval()`; separate mode from `no_grad`. | **Train/serve skew is a correctness risk, not only a timing one** |
| 13 | **Recurrent state** | `rnn_state` threads decision to decision (`model.py:218`) | Treat `(h, c)` as static input buffers copied in before replay. | Implies: **latency measured over shuffled positions is not the in-game distribution** |
| 14 | **The timing side channel** | not measurable; structural | If think-time is a monotone function of the agent's own uncertainty, every decision leaks a calibrated confidence read to the opponent, and the bot is physically incapable of the bluff a human makes by tanking and passing. Compute may depend on publicly observable complexity; **emitted latency must be quantised** — round up to a coarse grid before releasing the action. | Authored output-channel rail; §7. Costs nothing. The learnable alternative (let the agent learn to bluff by spending compute it does not need) is strictly better and strictly more expensive. |
| 15 | **Unified-memory contention (GB10-specific)** | not measurable here | The ARM cores' env work reads the **same 273 GB/s bus** as the GPU. A p99 measured with an idle CPU is not the p99 you get with 19 workers training. Pin the match process's env thread; never co-schedule training during a measured match. | Zero on a discrete GPU. Non-zero here. Must be quantified on the DGX. |
| 16 | **Caching allocator** | unmeasured | A `cudaMalloc` mid-match costs tens of ms. Warm every bucket before play; graph memory pools; `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`; **assert zero allocator events inside the timed window.** | none if warm-up covers the ladder |
| 17 | **Python GC** | unmeasured — **measure it** | `gc.freeze()` after warm-up; `gc.disable()` inside the decision window; explicit `gc.collect()` between turns, when the clock is not ours. | bounded, moved off the critical path |
| 18 | **Thermal / clock drift** | dev box shows `round_spread_pct` 41.7% and 63.4% on two rows | Already handled by the harness: burn-in (`bench.py:100-115`), median-of-round-medians (`:165-179`), spread flag (`:283`). **Trust the flag — the `v2-wide` row at 63.4% is not evidence and must not be cited.** Soak-test the DGX and report post-soak p99 separately. | Must be measured on the DGX |
| 19 | **Allocator misprediction** | introduced by §3 | Anytime interrupt returns the best action found so far. Legitimate under `NORTH_STAR.md:127` as a non-termination rail; logged in §7. **It must not exist in the training-time cost model** — in training, exceeding the budget must genuinely forfeit, so the agent feels it. | Firing rate is a first-class alarmed metric |

**Ordering.** #6, #3+#11, and #2 are cheap prerequisites for everything else; three of them are
literal no-ops or one-line masks. CUDA graphs (#8) are unreachable until they are done.

**The structural answer.** Do not try to make the tail small; make it **safe**:

> The model holds a valid, usable action from pass 1 onward, and every subsequent pass may only
> improve it. Then the deadline is enforced by **interruption**, not by prediction.

Anytime-plus-interrupt is a far stronger contract than "our p99 is low," because it holds even when
the allocator is wrong and even on a position shape nobody benchmarked. Note that the two anytime
mechanisms are distinct and both are wanted: the reasoning-pass loop (`model.py:232`) is
**interruptible** — a valid action exists after every pass, and the learned decision is *when to
stop thinking*; the plan (`ActionSequenceDecoder`) is a **contract** — commit `k` steps up front,
and the learned decision is *how far to commit before re-deliberating*. Plan abandonment needs one
genuine rules rail (if the planned action is no longer legal, re-deliberate — mandatory) and one
learned signal (a cheap revalidation head reading the engine's delta event set decides whether the
world surprised the plan enough to re-forward).

---

## 5. The measurement plan

**The harness already exists and it is good.** `tools/latency/bench.py` gets the hard parts right:
device sync (`:69-75`), burn-in with a docstring recording why (`:100-115`), first-block discard
after it made `v1` read 30 ms instead of 12 ms (`:157-161`), median-of-round-medians (`:165-179`), a
`round_spread_pct` validity gate (`:182`), `effective_gb_per_s` as the calibration number (`:190`),
an explicit transferable/not-transferable contract (`:12-23`), and honest labelling of the GB10
columns as projections (`:301-302`). **Do not rewrite it.** Close six gaps.

### 5.1 The six gaps

**(a) It sweeps a synthetic grid and never touches the real position distribution.**
`tools/latency/positions.py` collects exactly the right corpus — `n_entities`, `n_visible`,
`n_actions` per real decision point (`positions.py:36-45`) — and **`bench.py` never imports it**;
the only mention is a docstring at `bench.py:26`. A p99 over a uniform shape grid is not a p99 over
a game. Fix: for each of N sampled real decision points, time at *that position's* (T, A), and
report **position-weighted** percentiles.

**(b) The environment is excluded.** Tokenisation (14.5 ms) and legal-move generation (0.43 ms) are
on the match clock and absent. **A decision is state → action, not tensor → tensor.** A harness that
times only `model.forward` omits 15–25 ms and its entire tail, and would have reported today's
system as far more predictable than it is.

**(c) The pass count is fixed per preset** (`shapes.py:56`; presets hardcode 1, 3, 8), so the pass
*distribution* — the whole question — is never exercised. Until the allocator exists, invert it:
report per architecture *"what pass-count distribution fits the §1.3 budget?"* That is directly
actionable for sizing.

**(d) Two magic numbers carry the GB10 projection.** `shapes.py:291` hardcodes
`_KERNELS_PER_BLOCK = 14` and `shapes.py:364` assumes 20 residual launches under CUDA graphs. Launch
count is hardware-independent and countable *anywhere* with `TorchDispatchMode` — 515 at 1 pass,
3,925 at 8, metadata-only ops excluded. **Fold that counter in as a measured column** and the
projection loses a guess. Separately, `shapes.py:347` divides by the full 273 GB/s: **apply the 70%
streaming derate** (§2.1) or every projection stays 1.43× optimistic.

**(e) No real CUDA-graph path.** `cuda_graph_s` is modelled, not measured. It is the largest single
projected win and it is currently unverified. Capture a real `torch.cuda.graph` on the Spark.

**(f) No verdict.** The output should not be a table of milliseconds; it should be **pass/fail
against the §1.3 contract and the §2.3 throughput inequality, per architecture.** That is what makes
the size decision mechanical rather than a matter of taste.

### 5.2 The metrics the size decision will be made from

| Metric | Population | Why it is the one |
|---|---|---|
| **Match-budget occupancy** = Σ latency over a simulated game ÷ per-seat allowance; p50 and p95 **across games** | whole games, recurrent state threaded | **The only metric measured against the real contract.** This is what answers "can we afford a bigger model." |
| **Throughput inequality** — `bytes_per_decision / 191e9 × 75e6 / parallelism` | analytic + one calibration | §2.3. The binding constraint for the rebuild. |
| **p50 / p90 / p99 / p99.9 / max**, end to end, stratified | ≥5,000 real decision points across ≥20 games | The p99.9 is the worst decision of roughly every third match |
| **Match-forfeit probability** | resample latencies against the bank, ≥10,000 simulated matches | The §1.4 acceptance criterion. No percentile substitutes. |
| **Value-weighted miss rate** | same, weighted by value spread | A missed deadline on a mana tap costs nothing; on a block it loses the game |
| **Slow-play exposure** — count of decisions over 5 s, and the single longest decision, per game | whole games | MTR 5.5 gate. Must be 0. |
| `tail_ratio_p99_over_p50` | per config | `bench.py:89`. Literally the `NORTH_STAR.md:35` number. |
| `params_total`, `bytes_per_decision`, `flops_per_decision`, **measured** `kernel_launches`, sync count | analytic + dispatch counter | Machine-independent; already mostly in `CostModel` (`shapes.py:260-267`) |
| `effective_gb_per_s`, and its **ratio to theoretical** | per config | `bench.py:190`. The ratio says "how launch-bound am I", which is architectural |
| `round_spread_pct` | per config | **Validity gate: >15% ⇒ the row is not evidence** |
| Warm-up cost, `graph_hits` / `graph_misses` by stratum, allocator events | per run | Reported separately, never folded into steady state |

**Sample size.** A p99.9 estimate does not exist below n ≈ 3,000. Use **n = 30,000 per
configuration**, attach a bootstrap 95% CI to every published percentile, and make the harness
**refuse to print p99.9 below n = 10,000** rather than print a number that is one unlucky sample.

### 5.3 The position corpus

Three populations, all three reported, none of them a uniform sample of live rollouts:

1. **Stratified real states** from `positions.py`, bucketed `A ∈ {1, 2–4, 5–8, 9–16, 17–32, 33–128,
   129–512}` × `T ∈ {≤128, ≤256, ≤512}` × phase ∈ {main, declare-blockers, stack-non-empty}. Report
   each cell *and* the reweighted aggregate under a **declared** game-mix prior. Never report a
   single number without saying which prior produced it. Freeze the corpus to
   `bench/positions_v1.jsonl` with a content hash; the harness refuses to run on a mismatch.
2. **Synthetic shapes** at every point on the ladder, because the engine cannot currently produce the
   hard cases: 0 creatures reached the battlefield across an entire 1,500-decision game, every
   targeted spell offers one option, `MakeChoiceAction` never fires, and there are only two seats.
   **Real states validate the model; synthetic shapes bound it.** The bound is what the contract
   needs.
3. **Full-match replay** with the recurrent state threaded, producing the occupancy integral. Because
   of §4 row 13, this is the only population whose distribution is the in-game distribution.

Keep every corpus version. The rebuild changes the position distribution fundamentally, the corpus
must be re-cut precisely when the size decision is being made, and cross-version comparisons will be
invalid. There is no clean fix; report against both.

### 5.4 The quality-vs-passes curve — the go/no-go gate

**Without this, latency measurement is meaningless: you cannot trade quality for time without a
price.** For forced `n_passes ∈ {1, 2, 4, 8, 16}`, against a reference of the same weights at 16
passes: top-1 agreement, `KL(π_b ‖ π*)`, value MAE, puzzle score (`benchmarker.py:19`), and — the
only one that matters — **Elo of `π_b` vs `π_{b/2}` head-to-head over ≥400 games.**

**Declared judgment call, revisable:** require **≥25 Elo per doubling of passes, 95% CI excluding
zero**, before building §3. Chess engines gain roughly 50–70 Elo per doubling; if MTG yields under
~10, ship a fixed-1-pass model, delete the pass loop, re-size the 86.6%-of-bandwidth plan decoder,
and spend the engineering on the engine instead.

**This gate cannot pass today, and that is not the profile's fault** — the pass loop is provably
degenerate (§3.6). Run it *after* directive (b) lands.

### 5.5 Confounds that would make the numbers lie

| Confound | Consequence | Control |
|---|---|---|
| Timing `model.forward` only | omits ~15 ms of environment and its whole tail | time priority → action index |
| No device synchronisation | async queues report *launch* time, not completion. Note that the 10 forced syncs at `model.py:142` currently *mask* this bug; delete them (rightly) and a naive harness silently reports 0.1 ms | `cuda.Event` / `xpu.Event` + explicit sync; record that it ran |
| Benchmarking in `eval()` while playing in `train()` | different kernels entirely; understates real latency 2–3× | harness asserts eval + `inference_mode` (`bench.py:121` already does) **and `student.py:102` must be fixed to match** |
| Ambiguous pass count | `student.py:118` uses 1 when deterministic; `student.py:175` omits the arg and gets 8 from `model.py:201`. Two different models under one name | sweep pass count as an independent variable; never report "as it runs" alone |
| Live-rollout position sampling | 75% mana taps, constant `T`, no creatures, no targets | frozen hashed corpus, §5.3 |
| Min-of-N reporting | hides the tail, which *is* the KPI | full distribution; min only for the compute-floor question |
| Reporting a mean | the mean of a multimodal-over-pass-count distribution describes no decision that ever happened | percentiles and occupancy only |
| Clock drift (±30% here) | whichever config ran first looks slow | interleave A/B rounds **in one process**; report ratios |
| Cold clocks / first-block allocator growth | lands in the tail | already handled, `bench.py:100-115`, `:157-161` |
| Idle-machine measurement | on unified memory, an idle-CPU p99 is not the p99 with 19 workers training | measure under load; §4 row 15 |
| Silent backend degradation | `torch.compile` falling back, graphs not capturing — looks like a result | probe and **record what was actually enabled** into the output JSON |
| Shuffled-position measurement | breaks the recurrent state; changes numerics *and* the position distribution | replay in game order |
| Batch-1 vs batched server | play is batch 1, self-play is batched; different regimes, different bottlenecks | report both, labelled; never average them |
| Citing a noisy row | `v2-wide` at 63.4% spread | `bench.py:283` already says >15% invalidates; say so in the report rather than quietly citing it |

### 5.6 One script, two machines

The harness routes through `MTG_bot/utils/device.py` (`get_device()`, `autocast_dtype()`) plus a
`Timer` shim resolving to `cuda.Event` / `xpu.Event` / `perf_counter`+sync. One JSON schema on both
machines, so a diff tool compares directly. Plain CLI, no pytest dependency, headless-safe.

**The bridge is a roofline predictor built into the harness**, so a GB10 number exists today:

```
t_pred = bytes_per_decision / BW_eff  +  measured_launches × dispatch_µs  +  syncs × sync_µs
```

1. On the dev box, fit `(BW_eff, dispatch_µs, sync_µs)` from measured wall-clock across the sweep.
2. **Assert the model predicts the dev box's own wall-clock within 15%.** If it cannot, no GB10
   prediction is credible and the run is void.
3. Substitute GB10 constants — `BW_eff = 191 GB/s` (0.70 × 273), `dispatch_µs = 6–10`, graphed
   residual from a real capture — and emit a prediction **with an explicit uncertainty band**.
4. When the DGX arrives, run the identical script and **score the prediction.** The predictor is
   falsifiable, which is the point. The numbers in §2.1 are this predictor run by hand.

---

## 6. What transfers, and what does not

| Transfers | Why |
|---|---|
| `params_total`, `bytes_per_decision`, `flops_per_decision`, arithmetic intensity | analytic properties of the architecture (`shapes.py:294`) |
| **Real kernel-launch count** — 515 @1 pass, 3,925 @8 | pure graph structure, counted via `TorchDispatchMode` |
| Device-sync count, aten op histogram | structural |
| Scaling exponents: `dt/dT`, `dt/dA` (+9% over a 256× range), `dt/d(passes)` (4.6–5.1× for 8:1) | shape properties |
| **Ratios between configs measured in one process** | every row of the current report is `bound_by: bandwidth`, so ratios ≈ byte ratios |
| **The quality-vs-passes curve** | a property of the weights, not the silicon. Fully portable. |
| Position corpus and decision counts | pure engine, no torch — `positions.py:14-15` is explicit |
| Correctness of padding, masking, numerics under bucketing | logic |

| Does not transfer | Why |
|---|---|
| **Absolute milliseconds** | Arc 140V vs 273 GB/s; x86 vs 20-core ARM; ±30% local clock drift |
| **Anything CUDA-graph-related** | XPU has no CUDA graphs. **The single largest mitigation in §4 is unmeasurable on the dev box.** |
| **The dispatch/compute balance** | ARM Grace dispatch is *slower* than this box's x86 while GB10 compute is *faster*, so **the DGX will be relatively MORE dispatch-bound than local numbers suggest.** This is the most dangerous inference to get backwards: launch count matters *more* there, not less. |
| Memory-bandwidth behaviour under contention | unified memory with 19 concurrent env workers has no dev-box analogue |
| bf16 / FP4 numerics and speed | those paths do not exist on the Arc route |
| Jitter magnitude and thermal behaviour | the 41.7–63.4% round spread is a Windows/Arc artefact; the DGX figure must be measured |
| `effective_gb_per_s` — **but its ratio to theoretical does** | that ratio is "how launch-bound am I", which is architectural |

> **Rule: the dev box measures ratios and validates the harness. The Spark measures milliseconds.
> Never make a sizing decision from a dev-box millisecond.** Plan a half-day of DGX bring-up whose
> only job is to re-run the harness and score the §2.1 predictions.

---

## 7. Scaffolds to remove

These belong in [`BACKLOG.md`](BACKLOG.md) under "Scaffolds to remove" and are reproduced here with
their reasoning. Per `CLAUDE.md`, none of them may be added silently.

| Scaffold | Where it will live | Removal condition |
|---|---|---|
| **Bank randomisation** | `MTGEnv` clock resource, §3.6 | Remove when the max-compute policy consumes **>25% of the real 1,050 s bank** — i.e. when the real clock binds on its own. |
| **Forced-random-depth rollouts** | collection loop, §3.6 | Remove when measured `KL(π_p ‖ π_{p−1})` at `p ≥ 2` exceeds noise on held-out positions, i.e. deep passes have become genuinely informative. |
| **Entropy bonus on the halting Bernoulli** | PPO loss, §3.6 | Anneal to zero on the same schedule as the action-entropy bonus. |
| **Flat environment cost in the clock model** | cost table, §3.5 | Remove when `convert_graph_to_tokens` is incremental and O(changed), so charging the true board-size-dependent cost no longer teaches the agent to avoid playing creatures. |
| **Surrogate cost table** `bench/cost_table_gb10_<sha>.json` | §3.5 | Remove when the inference path reports true per-decision cost deterministically enough (CUDA-graph-captured, fixed shapes, locked clocks) to be charged directly without injecting timing noise into the policy gradient. |
| **Emitted-latency quantisation** | inference wrapper, §4 row 14 | This is an information-leak rail, not a strategy heuristic — but it *is* authored behaviour that deliberately burns clock, and the genuinely learnable alternative (let the agent learn to bluff with compute) is better and more expensive. **The owner should rule.** Remove if they prefer the learned version. |
| **Anytime interrupt at `2·B̂/N̂`** | reasoning loop, §4 row 19 | Never removed — it is a genuine non-termination rail. But its **firing rate is a first-class alarmed metric**, and it must **not** exist in the training-time cost model, where exceeding the budget must genuinely forfeit. |
| **The `≥25 Elo per doubling` gate** | §5.4 | A declared judgment call, revisable once the profile is known. |
| **Authored constants** | §1.3 | Round length (4,500 s), seat count (4), and the 3× design multiplier on `N`. The first two come from the Multiplayer Addendum. The third is a judgment call and must be re-derived after the engine rebuild. |

---

## 8. Recommended order of work

| # | Item | Why here | Payoff |
|---|---|---|---|
| 1 | Fix `benchmarker.py:106` — it unpacks **five** values from the **eight**-tuple `student.py:139` returns, so it raises `ValueError` on the first call. It is also the only place running `deterministic=True`, which at `student.py:118` hardcodes `num_passes=1`. | **The repository's only play path has never executed.** Nothing can be measured until it does. | Unblocks everything |
| 2 | Fix `student.py:102` so collection runs in `eval()`; separate mode from `no_grad`. | Dropout is active while acting; fused SDPA is lost. Correctness *and* latency. | Free |
| 3 | Delete `model.py:142-143` — a literal `pass` costing up to 80 device syncs per decision. | Blocks graph capture outright. | Minutes of work |
| 4 | Pad and mask the action menu (`model.py:172`) and the board tokens (`model.py:40` / `:206`). | Unpins batch=1. Prerequisite for CUDA graphs **and** for the §2.3 30× throughput win. | **Highest-leverage change in the repository** |
| 5 | Close the six harness gaps (§5.1): drive from `positions.py`, include environment cost, sweep pass count, measure launches with `TorchDispatchMode`, apply the 70% derate, emit a verdict. | `NORTH_STAR.md` §1a: numbers before decisions. | The size decision becomes mechanical |
| 6 | **Directive (b): train every plan step.** Gumbel-softmax at `model.py:138`, per-step log-probs and values instead of step 0's reused five times (`train.py:295-298`), plus a KV cache. | Quality fix the owner mandated, *and* the amortiser that pays for the bigger model (§2.4). | 3.4× at 5× model size |
| 7 | Collapse combinatorial block declaration into one structured decision (`engine.py:145-148`). | The only measured mechanism that actually threatens the clock (§4 row 4). Lands on preserved-directive (a). | Removes a 400-call combat step |
| 8 | Run the quality-vs-passes curve; apply the §5.4 gate. | Decides whether §3 gets built at all. | Go / no-go |
| 9 | Incremental tokenisation + relationship indexes (`state_converter.py:81-95`). | 14.5 ms mean / 23.7 max with its own tail; also removes the §3.5 env-cost trap. | Largest remaining ms-per-hour |
| 10 | **Only then**: clock as environment resource, clock token, `N̂` and forfeit heads, halting head, bank randomisation. | Needs 6 and 8 to have landed, and needs a model whose max compute costs a real fraction of the bank. | The championship-clock goal |
| 11 | Run the harness on the Spark with a real CUDA-graph capture; score every §2.1 prediction. | Needs 3–5 done and the DGX in hand. | The real tail fix, and the first honest millisecond |

---

## 9. Open questions that genuinely need deeper reasoning

Recorded per `NORTH_STAR.md` §6. These are not hedges; each one is a place where a wrong answer is
expensive to discover late and where measurement or first principles did not settle it.

1. **Does halting credit assignment actually resolve under PPO?** The halting action's effect on the
   return is mediated through the action it changed, across ~2,500 halting decisions per game, from a
   sparse win/draw/loss signal, with `batch_size = 32` (`config_rl.py:25`) and full-episode BPTT
   (`student.py:161-196`). The `∂V/∂bank` argument in §3.3 says the cost *can* be compressed into a
   one-step TD error — but it assumes `V` becomes accurate in the bank dimension, and early in
   training `∂V/∂bank ≈ 0`, so the CONTINUE advantage is noise for an unknown number of generations.
   The forfeit-probability head is meant to bootstrap it. **That is a bet, not a proof, and I do not
   know how long it takes to pay off or whether it pays off at all.**

2. **What is the deployment target's clock?** All of §1 assumes the paper MTR. A bot on Arena faces a
   per-priority rope plus a match reserve; a bot on MTGO faces a per-player chess clock with **no
   five-additional-turns mercy**, which makes the contract materially harsher and destroys the
   draw-vs-loss structure that §3.2's incentive rests on. I did not verify those clients' current
   specifics and will not guess. **If the target is a digital client, §1's arithmetic and §3.2's
   return structure must both be re-derived.**

3. **Flat environment cost is a lie; is it the right lie?** §3.5 charges tokenisation flat to avoid
   teaching the agent that big boards are expensive — in the format whose identity is big boards. But
   real tokenisation cost genuinely does scale with board size, so flattening it hides a real cost and
   will make the agent too slow on exactly the positions Commander produces. The two errors point in
   opposite directions and I have no principled way to choose between them short of running both,
   which requires a training run long enough for the clock to bind — which §3.6 says does not happen
   at the current model size. **Circular, and I could not break the circle.**

4. **Can the clock live in the value function without being reward-hacked?** If `V` learns "low bank
   ⇒ low value", the policy may prefer lines that *end* the game over lines that *win* it, because
   ending it stops the bleeding — and under MTR 2.4 a draw returns 0.5, which makes the hack pay.
   Detection is easy (ablate the clock token at evaluation and compare win rate at matched bank
   levels; if win rate *rises* with it ablated, the token is being exploited). **Whether it is
   avoidable in principle, rather than merely detectable, I could not determine.**

5. **Padded-and-graphed for play vs tight-and-dynamic for collection.** §4 rows 2 and 3 raise the mean
   to lower the variance, which is right for match predictability and wrong for the throughput that
   §2.3 identifies as the binding constraint. The obvious resolution is two configurations — which
   reintroduces the train/serve skew of §4 row 12, now at the kernel level rather than the dropout
   level. **There is no free version of this and I do not know which side should give.**

---

**Sources**

- [Magic: The Gathering Tournament Rules](https://media.wizards.com/ContentResources/WPN/MTG_MTR_2026_Feb27_EN.pdf) — Appendix B (Time Limits: 40 min minimum match, 50 min Constructed/Limited round, 90 min elimination quarter/semifinal, **no limit for elimination finals**); §2.4 End-of-Match Procedure; §5.5 Slow Play
- [MTR Appendix B — Time Limits](https://blogs.magicjudges.org/rules/mtr-appendix-b/)
- [IPG 3.3 — Slow Play](https://blogs.magicjudges.org/rules/ipg3-3/)
- [Multiplayer Addendum to the Magic Tournament Rules](https://juizes-mtg-portugal.github.io/multiplayer-addendum-mtr) — 75-minute Swiss pod, no additional turns, 15-minute last-turn cap, single-elim untimed
- [`HARDWARE_DGX_SPARK.md`](HARDWARE_DGX_SPARK.md), [`DESIGN_TRAINING.md`](DESIGN_TRAINING.md), [`NORTH_STAR.md`](../NORTH_STAR.md)
- Repository facts cited inline at `file.py:line`, verified at `000e37c`. The parameter table in §2.1
  was derived analytically from `model.py` and `config_rl.py` and reproduces the reported
  315,666,955 exactly; the roofline in §2.1 and the throughput arithmetic in §2.3 were re-computed
  from it rather than quoted.
