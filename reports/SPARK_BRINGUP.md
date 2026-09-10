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
