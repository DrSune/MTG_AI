# Design: network sizing, BPTT, and throughput on the DGX Spark

Status: **proposed.** Numbers are computed from the code as it stands plus the hardware in
[`HARDWARE_DGX_SPARK.md`](HARDWARE_DGX_SPARK.md). Arithmetic is shown so you can check it.

## The one number that determines every decision

~273 GB/s of unified LPDDR5X, shared by CPU and GPU.

A bf16 matrix multiply that reads N weights (2N bytes) and processes B rows does 2·B·N FLOPs,
so arithmetic intensity is B FLOPs per byte. To be compute-bound you need

```
B_crit = peak_FLOPS / bandwidth = 125e12 / 273e9 = 458 rows
```

The advertised 1 PFLOP is FP4 **sparse**. Standard Blackwell ratios give roughly 125 TFLOPS
dense bf16. Everything below plans at 125 TFLOPS peak and 50 TFLOPS achieved. If the machine
really delivers double that, halve every wall-clock figure.

Three consequences drive the whole design.

| Consequence | Implication |
|---|---|
| Batch-1 inference is bandwidth-bound, 458× below roofline | Latency is roughly *bytes of weights touched* divided by 273 GB/s. Doubling the trunk doubles interactive latency regardless of FLOPs. |
| 128 GB does **not** buy a bigger dense trunk | It buys a GPU-resident replay buffer, many parallel workers, a self-play league of frozen opponents, and mixture-of-experts parameters. |
| Every byte the Python workers touch comes out of the *same* 273 GB/s | A slow pure-Python engine does not just waste CPU, it steals matmul bandwidth. |

**Practical rule: capacity is free, FLOPs are moderately scarce, bandwidth per decision is the
scarce resource.**

> **Superseded in one place, 2026-09-10.** An earlier version of this document recommended
> deleting the plan decoder because 50.4M of its parameters receive no gradient.
> [`DECISIONS.md`](DECISIONS.md) **D3 overrides that**: the owner's instruction is to keep
> multi-step planning and train every step, and the head is untrained rather than useless. The
> cost-model consequence is in [`COST_MODEL.md`](COST_MODEL.md): parameters inside the plan and
> pass loops are read up to 40 times per decision, so the decoder must be made **narrow**, not
> removed. The loss that trains it is [`DESIGN_ACTION_SPACE.md`](DESIGN_ACTION_SPACE.md) §4.

## 1. What is wrong with the current network — shape, not size

315,666,955 parameters, of which about 207M are live.

| Block | Params | Status |
|---|---|---|
| `CardEmbedder.atomic_embedding`, 50000 × 1024 | 51,200,000 | Live, but only rows 1–424 are ever indexed. Over 99% dead weight that Adam still allocates moments for. |
| `CardEmbedder` MLP + fusion | 3,181,568 | Live |
| `BoardEncoder`, 16 layers, d=1024, ff=2048 | 134,397,952 | Live. **`dim_feedforward` is the PyTorch default 2048, i.e. 2×d_model rather than the standard 4×.** A silent capacity leak. |
| `OpponentPredictor` | 1,574,400 | Live |
| `System2ReasoningHead.action_memory_embedder`, 50000 × 1024 | 51,200,000 | **Never referenced in forward. Zero gradient. Pure waste.** |
| `System2ReasoningHead` remainder | 8,924,160 | Mostly reachable only on a rethink pass, which never fires |
| `ActionPointerHead.intent_proj` | 1,049,600 | **Never referenced in forward.** |
| `ActionPointerHead` remainder | 2,118,209 | Live |
| `ActionSequenceDecoder`, 4 decoder layers | 50,401,280 | Runs 5× per decision; only plan step 0 reaches the loss |
| `ActionSequenceDecoder` heads | 2,109,450 | Zero gradient — used only for argmax and log strings |
| `LSTMCell(1024, 1024)` | 8,396,800 | Live, the only temporal carrier |
| `temporal_fusion` | 2,098,176 | Live |
| **Total** | **315,666,955** | **54.4M (17.2%) receives no gradient, ever** |

Worse than the sizing:

- **Hidden-information leak.** The state converter includes every card in every library and
  every hand of both players, and `controller_ids` is computed and then discarded. The model
  sees the opponent's hand and both decks in order, and cannot distinguish its own permanents
  from the opponent's.
- **Token count is inflated roughly 2× by libraries.** 214 tokens for two players, 428 for a
  four-player pod, of which about 400 are library cards that should be one aggregate token per
  seat.
- **The board is re-encoded from scratch on every priority pass.** At 256 tokens and 20 layers
  that is about 85% of all FLOPs, spent re-deriving a board that did not change.

## 2. Proposed architecture

Transformer over *space*, recurrence over *time*, **two tiers so the heavy part is cached.**
This is the "frozen board cross-attention" idea that was deleted in commit `db5e024` — recover
it. On this hardware it is not an optimisation, it is a requirement.

```
                 ┌─ atomic id  ──► Embed(65536, 512) ──► ↑1024 ─┐
per card object ─┼─ ability tree ─► RulesEncoder(2L, d256) ─────┼─► Fusion(3072→1024)
                 └─ component feats(96) ─► MLP(96→1024) ────────┘
                                             │
      [pool tokens][seat tokens][zone tokens][object tokens]   T ≈ 256
                                             │
              TIER A: board encoder, 20 layers, d=1024, ff=4096
              ── runs ONLY on board-material change ──►  cached KV
                                             │
                        GRU core, d_state = 2048   (the BPTT carrier)
                                             │
      [priority ctx][stack][changed objects][legal action tokens]  T ≈ 64
                                             │
              TIER B: 4 layers, self-attention + cross-attention to Tier A
              ── every decision ──►
                                             │
        pointer logits over legal actions  │  value  │  auxiliary heads
```

| Block | Config | Params | bf16 bytes | Read per decision? |
|---|---|---|---|---|
| Atomic embedding | 65,536 × 512 | 33,554,432 | 67.1 MB | No, gather only |
| Atomic up-projection | 512→1024 | 524,288 | 1.0 MB | Tier-A cadence |
| Primitive embedding | 1,024 × 256 | 262,144 | 0.5 MB | Cached per card |
| Rules encoder | 2L, d=256 | 1,572,864 | 3.1 MB | Cached per card |
| Rules up-projection | 256→1024 | 262,144 | 0.5 MB | Cached |
| Component MLP | 96→1024→1024 | 1,146,880 | 2.3 MB | Tier-A cadence |
| Fusion | 3072→1024 | 3,145,728 | 6.3 MB | Tier-A cadence |
| **Tier A board encoder** | 20L, d=1024, h=16, ff=4096 | **251,699,200** | **503.4 MB** | **Tier-A cadence only** |
| Temporal GRU | 1024 → 2048 state | 20,971,520 | 41.9 MB | Every decision |
| Episodic memory attention | 32 slots, 1 layer | 4,194,304 | 8.4 MB | Every decision |
| **Tier B decision head** | 4L, d=1024, self+cross, ff=4096 | **67,121,152** | **134.2 MB** | **Every decision** |
| Action encoder | 128 → 1024 → 1024 | 1,179,648 | 2.4 MB | Every decision |
| Policy pointer + value | | 2,099,201 | 4.2 MB | Every decision |
| Auxiliary heads (belief, win prob, loop flag) | | ~4,000,000 | 8.0 MB | Every decision |
| **Total** | | **391,733,505** | **783.5 MB** | |

### Old versus proposed

| | Current | Proposed v1 | Note |
|---|---|---|---|
| Total parameters | 315.7M | 391.7M | +24% |
| **Trained** parameters | ~207M | 391.7M | **+89% live capacity** |
| d_model | 1024 | 1024 | unchanged, bandwidth-bound |
| d_ff | **2048** (a default nobody chose) | **4096** | +134M where it does work |
| Encoder depth | 16 | 20 (Tier A) + 4 (Tier B) | |
| Heads | 16 | 16 | unchanged |
| Card vocab | 50,000 rows on an unstable rowid | 65,536 on stable oracle id, factorised | |
| Component dim | 32, no controller | 96, with 4-seat controller, 8 zones, colours, types, counters, commander damage | |
| Temporal core | LSTMCell, 8.4M | GRU d_state 2048 + 32-slot episodic KV, 25.2M | |
| Plan decoder | 4L, 50.4M, 3 of 4 heads untrained | **kept, and every step trained** (D3) | narrow it instead of deleting it: see below |
| `action_memory_embedder` | 51.2M, zero gradient | **deleted** | −51.2M |
| Tokens, 4-player Commander | 428, including both libraries | **256** | closes the clairvoyance leak too |
| Weight bytes per decision | 631 MB, all of it, every pass | **199 MB** | **3.2× lower latency** |

### Three variants

| Variant | Change | Params | Active per token | When |
|---|---|---|---|---|
| **v0.5 — start here** | d=768, Tier A 12L, ff=3072 | ~150M | 150M | First few weeks. Throughput scales inversely with size and you need throughput more than capacity until the engine and reward are correct. |
| **v1 — target** | as the table above | 392M | 392M | Once win rate against the league plateaus at v0.5 |
| **v2 — spend the 128 GB** | Tier A feed-forward becomes mixture of experts, 8 experts, top-2 | **892M** | 392M-equivalent | Batched self-play only, **not** the interactive path |

**Why mixture-of-experts is the right way to spend 128 GB and why it does not help latency.**
Top-2-of-8 keeps FLOPs per token constant while quadrupling feed-forward parameters. At batch
8 or more, tokens spread across experts and each expert read amortises over many tokens. But at
**batch 1**, 256 tokens routing independently touch all 8 experts, so you read 4× the
feed-forward bytes and Tier A goes from 503 MB to 1,510 MB, a 5.5 ms bandwidth floor. So:
**train mixture-of-experts for strength, distil to dense v1 for interactive latency.** Two
goals, two artifacts, one training run.

## 3. Full-game BPTT: the arithmetic

### Activation memory per decision

Per pre-layer-norm transformer layer per token, with fused attention so the T² matrix is not
stored: 9·d + 2·d_ff elements = 9(1024) + 2(4096) = 17,408 elements × 2 bytes = **34,816 bytes
per token per layer**.

| Component | Calculation | Bytes |
|---|---|---|
| Tier A, T=256, L=20 | 256 × 20 × 34,816 | **178.3 MB** |
| Tier B self + feed-forward, T=64, L=4 | 64 × 4 × 34,816 | 8.9 MB |
| Tier B cross-attention | | 4.7 MB |
| Embedding, fusion, GRU, heads | | ~3.0 MB |
| **Per decision, no mitigation** | | **~195 MB** |

**If you use `nn.MultiheadAttention` or `TransformerEncoderLayer` as the code does today, the
T² attention matrix IS materialised**, adding 5·heads·T bytes per token per layer and taking
this to 283 MB. Switching to `F.scaled_dot_product_attention` is a free 1.45× memory win and
works on sm_121 with no flash-attention source build. Do it.

### Where full BPTT breaks

Usable activation budget is about 100 GB.

```
2,500-decision Commander game × 195 MB = 487.5 GB    → 3.8× over budget
break point = 100 GB / 0.195 GB        = 512 decisions
```

**Full-game BPTT breaks at roughly 512 priority decisions at batch 1** — turn 25 to 40 of a
four-player Commander game. With the attention layers as written today, it breaks at ~353.

### The mitigation ladder

| | Mitigation | Memory per decision | 2,500-step game | Extra compute |
|---|---|---|---|---|
| — | Baseline with fused attention | 195 MB | 487 GB ✗ | 1.00× |
| a | Tier-A caching only (fires 1 in 6) | 46.3 MB | 116 GB ✗ | 0.20× (saves) |
| b | a + selective checkpointing of Tier A | 16.8 MB | **42 GB ✓** | 1.28× |
| **c** | **Step-level gradient checkpointing** — store only the GRU state and raw inputs, recompute the whole step in backward | **141 KB** | **353 MB ✓✓** | **1.33×** |
| d | Truncated BPTT, K=256, carried state | as (c) | 36 MB/segment | 1.33× |

Storage for (c): GRU state 8 KB + token ids 2 KB + component features 98 KB + action
descriptors 33 KB ≈ **141 KB per decision**. Times 2,500 decisions is 353 MB, plus one step's
activations, so peak is about 548 MB.

> **Answer to "feasibility is a memory question, not a wish": with step-level gradient
> checkpointing, full-game BPTT costs 0.14 MB per decision and about +33% compute. It is
> feasible with roughly 200× headroom. Memory is not the binding constraint — serial
> wall-clock is.**

Batched, 64 games in lockstep is 35 GB peak. Fits comfortably.

The real cost is that the backward pass is strictly serial over 2,500 steps:

```
per step, B=64: 64 games × 32 GFLOP forward × 4 (fwd + recompute + 2× bwd) = 8.2 TFLOP
8.2 TFLOP / 50 TFLOP/s = 164 ms per step
2,500 steps = 410 s = 6.8 min per pass over 64 games  →  560 games/hour of learning
```

**Recommendation:** implement (c) unconditionally — it is nearly free and turns the memory
question into a non-question. Then pick the BPTT horizon on **credit-assignment evidence, not
memory**. Default to K=256 with carried state, which is 12 to 20 turns of Commander, enough for
combat, sequencing, and most combo setups. Run full-game BPTT as a periodic ablation to measure
whether the extra 10× serial cost buys anything. You can afford to answer that empirically,
which is the point.

Two practical notes. Bucket games to {128, 256, 512} tokens and pad, since lengths differ. And
the recompute must be **deterministic** — disable dropout in the recomputed region or preserve
RNG state, or the recomputed activations will not match and the gradients will be silently
wrong.

## 4. Throughput

### Environment cost model

| Stage | Change | ms/step | Source |
|---|---|---|---|
| 0 | Today, recorder on | ~41 | measured |
| **0b** | **Recorder gated off** ✔ *done* | **24.9** | measured |
| **1** | **+ memoised id mapper** ✔ *done* | **7.7** | **measured** |
| 2 | + relationship indexes, integer handles, `__slots__`, no deepcopy | ~4 | estimate |
| 3 | Struct-of-arrays or Rust core with make/unmake | ~0.1 | estimate |

Stage 1 is already applied. ARM derate is about ×1.18: Grace cores run single-threaded Python
at roughly 0.85× the dev box.

### Process map on 20 cores

```
 1 core  : learner (owns the GPU stream, bf16, step checkpointing)
 1 core  : batched inference server (own CUDA stream, captured CUDA graphs)
16 cores : environment worker processes  (spawn, NOT fork — fork plus CUDA is unsafe)
 2 cores : OS, logging, checkpoint I/O, W&B
```

Each worker runs the engine and tokeniser with **no CUDA torch import** and
`OMP_NUM_THREADS=1`. Communication is shared-memory ring buffers of fixed-shape tensors, not
pickled dicts.

Use **asynchronous actors with a batched inference server**, not synchronous vectorised
environments. Games desynchronise — different lengths, different legal-move counts — so a
lockstep vector environment wastes most of the batch. Workers push observations into a queue;
the server pops up to 64 or waits 2 ms, buckets by shape, runs the graph-captured forward, and
scatters results back. Target a server batch of at least 32; that is what clears the bandwidth
cliff.

### Games per hour

Assuming 2,500 decisions per four-player Commander game.

Environment ceiling, 16 workers, ARM-derated:

| Stage | steps/s/worker | ×16 | games/hr |
|---|---|---|---|
| 0 (was) | 11.3 | 181 | 260 |
| **1 (now)** | **52.1** | **833** | **1,200** |
| 2 | 213 | 3,404 | 4,900 |

GPU ceiling at v1, Tier A firing 1 in 6, amortised 32 GFLOP per decision forward and 128 GFLOP
for training:

| Regime | GFLOP/dec | games/hr @50 TF/s |
|---|---|---|
| Rollout only | 32 | 2,250 |
| Rollout + train every decision | 160 | **450** |
| Rollout + train 25% | 64 | 1,125 |
| **v0.5, train every decision** | 60 | **1,200** |

> **After the fixes already applied, the environment stops being the bottleneck and the GPU
> becomes the limit at 450 to 1,200 games per hour.** That is 11k to 29k games per day.

Two blunt implications:

1. **Do not rewrite the engine in Rust for training throughput.** Stage 1 was a few hours and
   bought 5.3×; stage 2 buys another 4×. Stage 3 is needed for **search**, not for self-play.
2. **11k to 29k games per day is far below AlphaZero-class budgets.** Every FLOP must count.

Four levers, in order of payoff:

| Lever | Effect | Note |
|---|---|---|
| Auto-resolve states with exactly one legal action, no network call | **40–70% fewer decisions** | This is a *rules* shortcut, not a strategy heuristic, so it passes the learnability test. With real priority added, most windows are forced. |
| Drop libraries and hidden hands from the token set | T 428→256, **1.7×** | A correctness fix that happens to be the second-largest speedup. Do it first. |
| Tier-A cadence 1-in-6 → 1-in-15 via delta tokens | **1.8×** | Needs the engine to emit a structured change set per move. It already builds an events list and throws it away. |
| Start at v0.5 rather than v1 | **2.7×** | Scale up when the win-rate curve flattens, not before. |

Stacked conservatively: **1,600 to 2,200 games per hour at v0.5**, 900 to 1,300 at v1. That is
20k to 50k games a day, a workable single-machine budget.

**Scaling path:** the Spark has 200 GbE. Two Sparks over RDMA is roughly 2× with a data-parallel
learner and shared replay. Expect about 85% scaling on gradient all-reduce for a 392M model.

### Memory budget

| Item | GB |
|---|---|
| DGX OS and services | 6.0 |
| 16 environment workers | 10.0 |
| Model weights bf16 (392M) | 0.78 |
| FP32 master weights | 1.57 |
| Adam moments | 3.13 |
| Gradients | 1.57 |
| FP8 actor copy + 8 frozen league opponents | 6.7 |
| BPTT stored states, B=32, K=256 | 1.16 |
| Peak recompute activations, B=32 | 6.24 |
| **Replay buffer, 400k decisions** | **33.2** |
| CUDA context, workspaces, graphs, fragmentation | 8.0 |
| **Total** | **~78 GB** |
| **Headroom** | **~50 GB** |

**This is where 128 GB actually pays off:** a 400k-decision replay buffer resident in
GPU-addressable memory with no PCIe hop, plus a real self-play league of eight or more frozen
opponents held simultaneously. Both are things the dropped opponent-pool work needed and could
not have on a normal GPU.

## 5. The inference path

| Path | Weight bytes | Bandwidth time | FLOPs | Compute | max |
|---|---|---|---|---|---|
| Full pass (Tier A + B) | 691 MB | 2.53 ms | 143 GFLOP | 2.86 ms | ~2.9 ms |
| Cached board (Tier B + GRU + heads) | 199 MB | 0.73 ms | 9.4 GFLOP | 0.19 ms | ~0.7 ms |

Add kernel-launch overhead: eager mode is roughly 400 launches at 6–10 µs of ARM CPU dispatch
each, so **2.4 to 4.0 ms of pure dispatch**. That doubles the latency and is invisible in FLOP
accounting.

| Config | Full pass | Cached board |
|---|---|---|
| Eager bf16 | ~6.5 ms | ~2.5 ms |
| `torch.compile(mode="reduce-overhead")` + CUDA graphs | **~3.0 ms** | **~0.8 ms** |
| + FP8 weights | ~1.8 ms | ~0.5 ms |

**CUDA graphs are mandatory on this machine, not optional.** Launch overhead is comparable to
the entire compute time.

### What blocks graph capture in the current code

| Blocker | Where | Fix |
|---|---|---|
| `.item()` inside the plan loop, a device sync and graph break every step, which also locks batch to 1 | `model.py:142` | Remove the `.item()`. Keep the plan decoder: **D3 is a binding instruction to train every plan step.** The sync is the bug, not the head |
| `.any()` plus a Python `if ... break` on a device tensor | `model.py:244-247` | Fixed pass count with masking |
| Python loop mutating logits in place | `student.py:126-129` | Vectorise as an additive mask. **Also fixes the 10-nat old/new log-prob mismatch that pins the PPO ratio to e^±10 on every pass action.** |
| No `src_key_padding_mask` passed | `model.py:206` | Required for any batch above 1 |

Bucket T to {128, 256, 512} and legal-move count to {16, 32, 64, 128} for twelve captured
graphs.

### Search, and why the engine rewrite is really needed

A single decision at 5 ms is far under any human real-time bar. The interesting question is how
much search fits in 200 ms. Batched leaf evaluation with a shared board KV gives roughly 4,200
leaf evaluations. **But the network is not the constraint — the environment is.** 4,200
simulations at ~30 plies is 126,000 engine steps in 200 ms, i.e. 1.6 µs per make/unmake. Today
a single `deepcopy` of a Commander state costs 6 ms.

> **The engine rewrite is required for search, not for training throughput.** Clone-based
> tree search is dead on arrival. You need make/unmake with an append-only undo journal on a
> struct-of-arrays state. Target 10–50 µs per make and unmake, which allows 200 to 800
> simulations in 200 ms — enough to matter.

### Quantisation

| Component | Precision |
|---|---|
| Actor / rollout forward | FP8 (E4M3) |
| Interactive play forward | FP8, with the value head and pointer matmul in bf16 |
| Learner forward and backward | **bf16 activations, FP32 master weights, FP32 Adam** |
| NVFP4 | phase 2, after FP8 is stable |

**A trap this codebase has already been bitten by.** PPO's ratio is
`exp(new_log_prob − old_log_prob)`. If the actor collects in FP8 and the learner recomputes in
bf16, the numeric difference appears as a spurious policy change — a 0.01 logit discrepancy is a
1% systematic gradient error in a fixed direction. **Fix: store the chosen action index, not
the log-probability, and recompute the old log-probability at training time under `no_grad`
with the same graph the learner uses.** That also fixes the existing proactivity-bias offset bug
and the train-mode-during-collection dropout mismatch for free.

## 6. Recommended order of work

Each line is a measured or computed payoff.

1. ~~Gate the recorder off, memoise the id mapper~~ ✔ **done, 5.3× measured.**
2. **Drop libraries and opponent hands from the token set; actually feed `controller_ids`.**
   Closes the clairvoyance leak and takes T from 428 to 256. A correctness fix that is also the
   second-largest speedup.
3. **Swap to `F.scaled_dot_product_attention`, add padding masks, delete `.item()` from the
   forward path.** Unblocks batch > 1, `torch.compile`, and CUDA graphs simultaneously, and
   cuts activation memory 1.45×.
4. **Step-level gradient checkpointing.** Removes the BPTT memory question permanently.
5. **Delete the 52.2M genuinely unreachable parameters, then widen `d_ff` to 4096.** That is
   `action_memory_embedder` and `intent_proj`, neither of which is referenced in `forward` at all.
   **Not the plan decoder's heads:** D3 requires those trained, not removed. Same total size,
   roughly double the trained capacity.
6. **Stable oracle-id vocabulary, atomic-id dropout, pool token.** This is the whole mechanism
   for tied-rank-1 and rank-3, and it is a few hundred lines.
7. **Async actors plus a batched inference server.** Gets you to the GPU ceiling.
8. Relationship indexes, integer handles, `__slots__`.
9. CUDA graphs and an FP8 actor.
10. Make/unmake journaling on struct-of-arrays state. Required for search — and search, not raw
    self-play volume, is what turns 20k games a day into strong play.

**The uncomfortable summary:** one DGX Spark gives roughly 11k to 29k self-play Commander games
per day at these sizes. That is enough to train a genuinely strong bot only if each game is
worth a lot, which means a correct engine, an honest evaluation signal, and search at play
time. The hardware is not the constraint. Items 1 to 4 are about a week of work and remove
every *hardware* excuse.
