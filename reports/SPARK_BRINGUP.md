# DGX Spark bring-up, 2026-09-10

First session run on the training machine rather than the Windows development box. This records
what was measured, what was broken, and what the numbers mean, so nobody re-derives it.

Everything below is **measured on this hardware** unless a line says otherwise.

## The machine, verified

| | |
|---|---|
| Host | `spark-92ad`, Linux 6.17.0-1032-nvidia, aarch64 |
| CPU | 20 cores: 10x Cortex-X925 + 10x Cortex-A725, max 3.9 GHz, boost disabled |
| GPU | NVIDIA GB10, compute capability **(12, 1) = sm_121**, architecture 12.1 |
| Driver / CUDA | 580.173.02 / CUDA 13.0 |
| Memory | 121 GiB unified, `torch` reports 130.7 GB addressable, 15 GiB swap |
| Disk | 3.7 TB root, 46 GB used. The C:-drive pressure noted in `CLAUDE.md` does not apply here |
| Profilers | `nsys` and `nsight-compute` already on PATH, under `/opt/nvidia` |

## Python environment

`torch 2.14.0+cu130`, aarch64 wheel, installed into the repo `.venv` from
`https://download.pytorch.org/whl/cu130`. Pulls cuDNN 9.24.0, NCCL 2.30.7, cuBLAS 13.1.1,
Triton 3.8.0. Venv is 5.3 GB.

`python` does not exist on this box, only `python3`. Inside the repo, use `.venv/bin/python`.

### The arch-list check that `pyproject.toml` demands

```
torch.cuda.get_device_capability() -> (12, 1)
torch.cuda.get_arch_list()         -> ['sm_80', 'sm_90', 'sm_100', 'sm_110', 'sm_120']
```

`sm_121` is **not** in the list and that is fine. sm_120 and sm_121 are binary compatible, so the
shipped sm_120 SASS executes natively. The failure mode `pyproject.toml` warns about is an arch
list containing only `compute_90`, which would mean PTX JIT and a multi-second stall on every new
kernel. Measured first-kernel time including CUDA context creation was **0.47 s**, and the first
4096-wide bf16 matmul **0.20 s**. Those are context-setup costs, not JIT compilation.

One pip wheel is inert: `nvidia-cusparselt-cu13` reports "not supported on this platform", because
cuSPARSELt ships x86-only. It provides 2:4 structured-sparsity inference kernels, which nothing in
this project uses. `pip check` flags it and it can be ignored.

### Raw device numbers

| What | Measured | Note |
|---|---|---|
| bf16 matmul 2048^3 | 85.0 TFLOP/s | |
| bf16 matmul 4096^3 | 74.0 TFLOP/s | |
| bf16 matmul 8192^3 | 78.7 TFLOP/s | |
| Device-to-device copy, 2 GB | **223.7 GB/s** | versus ~273 GB/s theoretical, so 82% |
| Tiny-op kernel launch | **6.93 us/op** | the number that binds batch-1 RL |

`docs/HARDWARE_DGX_SPARK.md` quotes ~273 GB/s, which is the spec figure. **223.7 GB/s is what
you actually get**, and the cost model in `docs/COST_MODEL.md` should be calibrated against the
measured number, not the spec one.

The 6.93 us launch cost is the important one. The hardware doc predicted that small-batch rollout
would be bound by kernel-launch overhead and Python rather than FLOPs, and that prediction holds:
any decision made of a few hundred sequential small kernels pays milliseconds in launch overhead
before it does any useful arithmetic, at any model size.

## Defect found: pip `torch` has a working forward pass and a broken backward pass

This is the single most useful thing the session turned up, and nothing in the test suite catches it.

`test_model_forward` passes. A forward pass at full training scale passes. The **first backward
pass crashes**:

```
torch/_native/ops/bmm_outer_product/triton_impl.py -> triton_kernels.bmm_outer_product
  -> triton/backends/nvidia/driver.py  CudaUtils()
    -> gcc .../triton/backends/nvidia/driver.c
      fatal error: Python.h: No such file or directory
```

`torch 2.14` routes some backward ops through its `_native` registry into **Triton**, and Triton
JIT-compiles a small CUDA driver shim with `gcc` on first use. That compile needs the CPython
development headers. `/usr/include/python3.12/Python.h` does not exist, because `python3.12-dev`
is not installed. `gcc 13.3.0` itself is present.

So `pip install torch` is **not sufficient to train on this box**, and the gap is invisible until
the first gradient. Two fixes:

```bash
sudo apt install python3.12-dev          # one-time, needs the owner's password
```

or set `TORCH_DISABLE_NATIVE_JIT=1`, which routes those ops back to eager implementations. That
env var was used for every training-path measurement below and produced correct, finite results.

**This is the concrete case for the NGC container.** The NGC PyTorch image ships the Python
headers, a matched toolchain, and a warm Triton cache, so this class of failure cannot occur there.
It is exactly the "training stability" the container buys: not faster kernels, but an environment
where a dependency that is only reachable from one code path is not missing.

**Coverage hole this exposes:** no test in the repository runs a backward pass. `test_model.py`
tests forward only. A single fwd+bwd+step test would have caught this at collection time.

## Training-path stability at full scale, measured

315.7M parameters (`vocab 50000, d_model 1024, nhead 16, layers 16, belief 512`), bf16 autocast,
batch 1, 60 board tokens and 40 legal actions, which is the p99 of the measured position
distribution. Twelve AdamW steps, `TORCH_DISABLE_NATIVE_JIT=1`.

| | |
|---|---|
| Non-finite loss or grad-norm | **none in 12 steps** |
| Parameters that went non-finite | **none** |
| Grad-norm range | **663 to 1744** |
| Peak GPU memory | **5.52 GB of 130.7** |

Two readings, and the second one is a finding rather than a reassurance.

**bf16 on sm_121 is numerically fine.** No NaN, no Inf, loss moving, nothing special required
beyond bf16 autocast as `docs/HARDWARE_DGX_SPARK.md` already prescribes.

**Grad norms in the high hundreds to low thousands, with no gradient clipping in the optimiser.**
`docs/ARCHITECTURE.md` records that PPO here has no gradient clipping; this measures what that
costs. A single unlucky batch at grad-norm 1744 into AdamW at lr 1e-4 is a large parameter jump.
This is a measured confirmation, not a new claim, but it upgrades the claim from "missing feature"
to "missing feature with numbers attached".

**Capacity is a non-issue, exactly as predicted.** 5.52 GB of 130.7 at full scale. Being greedy
with parameters is cheap here; being greedy with memory traffic per decision is not.

## Defect found: `num_passes` is inert, so every multi-pass latency number is a one-pass number

Inference latency measured flat across requested pass counts:

| requested `num_passes` | inference p50 | |
|---|---|---|
| 1 | 14.6 ms | |
| 2 | 14.9 ms | |
| 4 | 14.4 ms | |
| 8 | 14.5 ms | |

Instrumenting `passes_taken` over 50 random positions with `num_passes=8` requested:

```
1 pass(es):  50 positions
```

Fifty out of fifty. The loop at `MTG_bot/strategic_brain/model.py:231-249` breaks after the first
iteration unless `argmax(res["plan_sequence"][0]["type_logits"]) == 9`, that is, unless the plan
decoder's top prediction for the first plan step is the literal action-type integer 9, read as
RETHINK. At initialisation that never happens, so the reasoning loop never runs twice.

Three consequences, and they bear directly on settled decisions:

- **The halting head is wired to nothing.** The decoder computes `rethink_prob` and the forward
  pass returns it in the output dict, but the loop gates on the argmax of a discrete type instead.
  `docs/DESIGN_LATENCY.md` section 3.3 and D11 both specify a *learned* halting decision trained
  as a sampled policy action. What exists is an argmax against a magic constant, which has no
  gradient path from the halting choice to the loss, so it cannot be learned as written.
- **`p >= 0` in the break condition is always true.** It reads as the residue of a removed
  minimum-pass rail. Whatever it was guarding is gone.
- **`current-8pass` in `tools/latency/bench.py` is honest but is not this model.** The harness
  models eight genuine passes and reports 31.0 ms against 6.0 ms for one pass, which is the right
  projection of what eight passes *would* cost. The real model pays the one-pass price. Do not
  read bench.py's 8-pass row as a measurement of current behaviour.

`passes_taken` is returned by the forward pass and recorded nowhere. It should be a monitored
metric before any adaptive-compute claim is made.

## The 54.4M ungradiented parameters are unwired layers, not an untrained decoder

`docs/ARCHITECTURE.md` records that 315.7M parameters include 54.4M that "receive no gradient,
ever", and attributes it to only plan step 0 reaching the loss. The number is right. **The
attribution is wrong**, and the difference changes what has to be built.

Measured at the real training shape, under a loss constructed to touch *every* differentiable
output including every plan step, so that "no gradient" means unreachable from the architecture
rather than merely absent from today's loss:

| params | tensor | why it gets nothing |
|---|---|---|
| **51.20M** | `reasoning_head.action_memory_embedder.weight` | declared `model.py:56`, **referenced nowhere else in the file** |
| **2.10M** | `reasoning_head.action_fusion.weight` | declared `:57`, used `:64`, but only when `prev_plan_embeddings is not None`, which is only true from reasoning pass 2 |
| **1.05M** | `decoder.intent_proj.weight` | declared `:152`, **referenced nowhere else in the file** |
| 0.00M | the two matching biases | same |
| **54.3M total** | **17.2% of 315.7M** | matches the audit's 54.4M |

Three things follow.

**52.25M of it is two layers no code path touches.** An `nn.Embedding(50000, 1024)` and an
`nn.Linear(1024, 1024)` are constructed and never called. That is not an untrained parameter, it is
an unwired one, and D3's ruling does not reach it. D3 overturned an audit recommendation to delete
the `ActionSequenceDecoder`, on the premise that its parameters were "untrained, not worthless".
That ruling stands and is still right, but it was defending the wrong tensors.

**The plan sequence heads are not in the list.** `sequence_decoder.type_head`, `source_head` and
`target_head` all receive gradient as soon as the loss includes the plan steps. So D3's requirement
that every plan step be trained is **a change to the loss in `student.py`, not a change to the
model.** That is a materially smaller job than the audit implied, and it is the one actually on the
critical path.

**2.10M wakes up for free when halting is fixed.** `action_fusion` is the layer that injects the
previous pass's plan back into the next pass, so it is unreachable precisely because the reasoning
loop never reaches pass 2. The dead-parameter defect and the inert-loop defect are one defect.

Both findings are now gated by tests in `MTG_bot/strategic_brain/test_model.py`:
`test_no_parameter_is_orphaned_from_the_architecture` and
`test_reasoning_loop_can_actually_iterate`. Both fail today, by design, and name the exact tensors
and counts in the failure message.

## Engine position complexity, re-measured on this hardware

`tools/latency/positions.py --games 8 --mode Commander`, seed 20260910, 5,607 decisions.
Full output in `reports/positions_dgx.json`.

| | |
|---|---|
| Legal actions per decision | p50 **1**, p90 3, p99 5, max 6 |
| Engine step incl. legal moves | **5.477 ms** (7.7 ms on the Intel Arc box) |
| Visible entities | p50 37, p99 60, max 63 |
| Total graph entities | constant **214**, every position |

Action mix: PassPriority 57.1%, ActivateManaAbility 29.2%, PassTurn 10.8%, PlayLand 2.4%,
CastSpell **0.5%**. Twenty-eight spells in 5,607 decisions.

The median of one legal action, which `docs/DECISIONS.md` calls out as "not Magic", **reproduces on
the training hardware**. It is not a dev-box artefact. The step time being 1.4x faster here than on
the Intel Arc box measures the Cortex-X925 cores, because this path is pure Python over a linearly
scanned relationship list and touches no GPU at all.

## The latency harness has now run on the Spark, which is what D5 was waiting for

`tools/latency/bench.py --reps 200 --rounds 7 --burn-in 5`, 112 configurations, full output in
`reports/latency_dgx.json`. The harness's own docstring said to run it here and replace its GB10
projections with measurements. Done. 111 of the 112 configs came in under the 15% between-round spread
threshold, so they are separable; the exception is `current-8pass` at 64 tokens / 192 actions at 18.3%.

At 256 board tokens and 96 legal actions:

| arch | params | MB/dec | launches | p50 | p99 | tail | eager proj | graph proj | GB/s |
|---|---|---|---|---|---|---|---|---|---|
| `current` | 249.6M | 800.1 | 564 | 5.75 | 7.18 | 1.25 | 12.24 (−53%) | 4.35 (+32%) | 138 |
| `current-8pass` | 249.6M | 4325.1 | 2804 | 30.73 | 33.81 | 1.10 | 69.16 (−56%) | 22.79 (+35%) | 141 |
| `v0.5` | 190.5M | 319.9 | 272 | **2.45** | 4.39 | 1.79 | 5.92 (−59%) | 1.83 (+34%) | 130 |
| `v1` | 413.0M | 601.8 | 290 | 3.57 | 9.16 | **2.56** | 7.60 (−53%) | 3.31 (+8%) | 169 |
| `v1-cached` | 413.0M | 516.6 | 244 | 3.50 | **4.05** | **1.16** | 6.64 (−47%) | 2.86 (+22%) | 147 |
| `v1-3pass` | 413.0M | 1541.6 | 738 | 10.28 | 15.25 | 1.48 | 20.25 (−49%) | 8.23 (+25%) | 149 |
| `v2-wide` | 1053.3M | 1497.9 | 332 | 8.79 | 19.65 | 2.24 | 12.94 (−32%) | 8.00 (+10%) | 170 |

**The cost model brackets reality correctly, which is a real validation of
[`../docs/COST_MODEL.md`](../docs/COST_MODEL.md).** Measured eager latency is 32% to 59% *faster* than the
eager projection and 8% to 35% *slower* than the CUDA-graph projection. Since the measurement is eager and
graphs are not implemented, sitting between the two bounds and nearer the graph bound is exactly right.
Keep the bracket and stop treating either end as the answer.

**These configurations are bandwidth-bound, not launch-bound.** Every row reports `bound_by: bandwidth`,
and achieved bandwidth is 130 to 170 GB/s against the 223.7 GB/s this device actually delivers, so 58% to
76% of achievable. That does not contradict the 6.93 us launch cost: launch overhead binds the *real*
model at batch 1 with hundreds of tiny sequential kernels, whereas these probes stream real weight volume.
Both are true of different workloads, and the distinction decides whether the fix is architecture or CUDA
graphs, so do not collapse them.

### Every candidate is far inside a match clock, and that reframes the clock work

Worst p99 anywhere in the sweep, per architecture:

| arch | worst p99 | worst single observation |
|---|---|---|
| `v1-cached` | **4.49 ms** | 5.16 ms |
| `v0.5` | 5.27 ms | 6.05 ms |
| `current` | 8.70 ms | 9.38 ms |
| `v1` | 10.38 ms | 12.82 ms |
| `v1-3pass` | 17.08 ms | 17.84 ms |
| `v2-wide` | 22.58 ms | 23.26 ms |
| `current-8pass` | 71.72 ms | 89.63 ms |

Against [`../docs/CLOCK_TARGETS.md`](../docs/CLOCK_TARGETS.md)'s budget these have enormous headroom. So
**the network is not currently what threatens the clock.** The engine is: 5.477 ms of pure Python per step
against 2.45 ms for a whole v0.5 forward pass. Rollout throughput, not model size, is the binding
constraint, exactly as [`../docs/HARDWARE_DGX_SPARK.md`](../docs/HARDWARE_DGX_SPARK.md) predicted.

### `v1-cached` dominates on the thing NORTH_STAR section 1a actually asks for

The charter says to optimise the tail, not the mean, and that predictability is a feature. On that
criterion `v1-cached` wins the sweep outright: **413M parameters at p50 3.50 ms with a tail ratio of 1.16
and a worst-case p99 of 4.49 ms anywhere.** It is both 2.2x the parameters of `v0.5` and *more* predictable
than it (`v0.5` reaches a 2.02 tail ratio). Caching the board encoder is what buys this: 244 kernel
launches against `v1`'s 290, and a tail ratio of 1.16 against the same architecture's 2.56 uncached.

**This does not overturn D12, and it is not a size decision.** D12 starts at `v0.5` for *throughput*, not
latency, and a 43% higher per-decision cost does reduce games per hour. What the measurement removes is the
**latency** objection to scaling: D5 forbade a size commitment before the harness ran here, and the harness
now says no candidate in this range, up to 1.05B parameters, is anywhere near a clock limit. The remaining
argument for starting small is purely games-per-hour, which is the right argument and should be made on
throughput numbers that do not exist yet.

### There is currently no mechanism producing compute variance at all

NORTH_STAR section 1a rests on the owner's observation that *"some turns will require more reasoning passes
than others, due to increased complexity of the board and state or number of possible actions to take"*.
Measured, from the easiest shape (64 tokens, 8 actions) to the hardest (384 tokens, 192 actions):

| arch | easiest p50 | hardest p50 | growth |
|---|---|---|---|
| `current-8pass` | 30.93 | 32.98 | 1.07x |
| `v1` | 3.58 | 4.03 | 1.12x |
| `v1-cached` | 3.17 | 3.65 | 1.15x |
| `v2-wide` | 8.07 | 9.49 | 1.18x |
| `current` | 5.39 | 6.50 | 1.20x |
| `v1-3pass` | 9.38 | 11.21 | 1.20x |
| `v0.5` | 2.13 | 2.82 | 1.33x |

**A six-fold increase in board size and a twenty-four-fold increase in action count buy at most 1.33x in
latency.** Position complexity, in the range the engine can even produce, barely moves the cost. The only
mechanism in the design that would create real compute variance is the number of reasoning passes, and
that loop is inert (see above: 50 of 50 positions take one pass). So **today nothing in the system
produces compute variance, and the adaptive-compute programme has nothing to adapt.** The halting head is
the whole mechanism, not a refinement of one, which raises how much D11 is load-bearing.

## Determinism, re-verified and worse than recorded

`docs/ARCHITECTURE.md` says nothing is seeded. Confirmed: every `random.seed`, `manual_seed` and
`default_rng` call in the repository is under `tools/`, which holds the offline analysis scripts.
There is not one in `MTG_bot/`, the training path.

The stronger finding is that the separation required by protocol check P11, four independent
streams for shuffle, engine, policy and exploration, is **structurally absent rather than merely
unseeded**. Every call site draws from the one global `random` module:

| stream | call sites |
|---|---|
| shuffle / setup | `game_initializer.py:44` starting player, `:90` deck shuffle |
| deck generation | `deck_generator.py:38, 86, 87, 112, 137, 144, 193, 196` |
| engine | `engine.py:116` sampling, `:340` discard to hand size |
| policy / exploration | `student.py:27` buffer sample, `:100` random action, `:132` exploration roll |

So even after adding a single global seed, changing the exploration rate alters how many draws are
consumed and therefore shifts every subsequent shuffle. Runs would not be comparable across a
config change, which is the thing seeding was supposed to buy. P11 needs four named generators
threaded through, not a seed call.

## Benchmark hygiene note

The desktop session contends for the GPU. During these measurements Xorg, gnome-shell, Firefox and
LM Studio together held roughly 850 MiB and were actively rendering. The quick latency sweep
flagged a 48.6% between-round spread on the widest configuration, which is the harness correctly
refusing to separate configurations on a noisy box. Close the browser and LM Studio before taking
numbers that a decision will rest on.

## What this does not establish

No strength number. `docs/TRAINING_REVIEW_PROTOCOL.md` gate P7 requires the rules conformance suite
green, and it is 17 passed / 22 failed. P8 through P13 are all blocked. Under the protocol's own
precedence rule, correctness before strength, nothing about play quality can be concluded yet, and
a training run started now would spend DGX hours producing numbers the protocol forbids citing.
