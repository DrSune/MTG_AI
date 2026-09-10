# Hardware: the DGX Spark training target

All training runs on an **NVIDIA DGX Spark**. There is also a Windows Intel Arc box used for
development and tooling, which cannot run CUDA.

**As of 2026-09-10 the repository is checked out on the Spark itself** and tests, benchmarks and
training all run there directly. Earlier revisions of this file said "this one" meaning the Windows
box; that is no longer where work happens. Measured bring-up numbers are in
[`../reports/SPARK_BRINGUP.md`](../reports/SPARK_BRINGUP.md).

## The two machines

| | Windows dev box | Training target (where the repo now lives) |
|---|---|---|
| Chip | Intel Core Ultra + Arc iGPU | NVIDIA GB10 Grace-Blackwell |
| Accelerator API | Intel XPU (`torch 2.11.0+xpu`) | CUDA 13, compute capability **sm_121** |
| Memory | shared system RAM | **128 GB unified LPDDR5X** |
| Memory bandwidth | low | **~273 GB/s** |
| CPU | x86-64 Windows | **20-core ARM64** (10× Cortex-X925 + 10× Cortex-A725) |
| OS | Windows 11 | DGX OS (Ubuntu-derived), aarch64 |
| Role | engine dev, spectator tool, tests | all self-play and all training |

Because the two disagree on accelerator, **never write `torch.device("cuda")` directly.** Go through
`MTG_bot/utils/device.py`. Existing violations live in `strategic_brain/student.py` and
`strategic_brain/teacher.py` and should be fixed.

## The one fact that should drive every design decision

The GB10's GPU has **no dedicated VRAM**. It reads the same LPDDR5X the ARM cores read, over the
same ~273 GB/s bus. That produces a very unusual profile:

- **Capacity is enormous.** 128 GB is more than an H100 80GB. Holding a large model, long
  trajectories, and a big replay buffer simultaneously is genuinely easy here.
- **Bandwidth is mid-range, and the spec figure is not what you get.** ~273 GB/s is the spec,
  roughly consumer-GPU territory and about a fifth of an H100's HBM3. A measured 2 GB
  device-to-device copy achieves **223.7 GB/s**, so 82% of spec. Calibrate
  [`COST_MODEL.md`](COST_MODEL.md) against the measured number. Anything that streams large tensors
  repeatedly will be bandwidth-starved.
- **Therefore: be greedy with parameters, stingy with memory traffic per decision.** A wider
  network that is read once per decision is cheap. A "thinking loop" that re-reads the whole model
  eight times per decision costs eight times the bandwidth and is the single most expensive design
  choice currently in the codebase.

A second consequence: at batch size 1, which is what naive RL rollout does, this machine is bound by
**kernel-launch overhead and Python**, not by FLOPs. A 300M-parameter model at batch 1 will not be
compute-limited. Throughput work belongs in the environment, in process-level parallelism, and in
batching inference across many concurrent games — not in shrinking the network.

## Software gotchas on aarch64 + sm_121

The first three are now **measured on the machine**, not anticipated. Full detail in
[`../reports/SPARK_BRINGUP.md`](../reports/SPARK_BRINGUP.md).

- **PyTorch: `sm_121` is absent from the arch list and that is correct.** `torch 2.14.0+cu130`
  reports `get_device_capability() == (12, 1)` and
  `get_arch_list() == ['sm_80','sm_90','sm_100','sm_110','sm_120']`. sm_120 and sm_121 are binary
  compatible, so the shipped SASS runs natively. The failure this check is really for is an arch
  list holding only `compute_90`, which means PTX JIT. Measured first-kernel time including CUDA
  context creation is 0.47 s, which is context setup, not JIT.
- **`pip install torch` leaves the backward pass broken on a fresh DGX OS image.** torch 2.14 routes
  some backward ops through its `_native` registry into Triton; Triton JIT-compiles a driver shim
  with `gcc` on first use, and that needs CPython's development headers. A stock image has no
  `python3.12-dev`, so the forward pass works, the forward test passes, and the **first gradient
  raises `fatal error: Python.h: No such file or directory`**. Fix with
  `sudo apt install python3.12-dev`, or set `TORCH_DISABLE_NATIVE_JIT=1` to route those ops back to
  eager. This is the concrete reason to prefer the NGC container for training: the image ships the
  headers and a matched toolchain, so a dependency reachable from only one code path cannot be
  missing.
- **`nvidia-cusparselt-cu13` installs but is inert**, because cuSPARSELt ships x86-only wheels.
  `pip check` flags it. It supplies 2:4 structured-sparsity inference kernels that nothing here uses.
- **Wheels in general:** aarch64 + CUDA is a much thinner ecosystem than x86-64. Expect to build
  from source or use NVIDIA's NGC containers for anything exotic. Prefer the NGC PyTorch container
  as the training base image rather than pip-installing into the host Python.
- **Do not assume a package exists for aarch64.** Check before depending on it. This applies to
  `flash-attn`, `bitsandbytes`, `xformers`, and most CUDA-kernel packages.
- **Numerics:** Blackwell does bf16 well and has FP4/FP6 tensor cores. Use **bf16 autocast**, not
  fp16. FP4 is an inference-time option, not a training one.

## Sanity checks, and what they returned on 2026-09-10

Note `python` does not exist on this box, only `python3`. Inside the repo use `.venv/bin/python`.

```bash
.venv/bin/python -c "import torch; print(torch.__version__, torch.version.cuda, torch.cuda.is_available(), torch.cuda.get_device_capability(), torch.cuda.get_arch_list())"
nvidia-smi; nproc; free -g
```

A forward-pass check is **not sufficient**. Run a gradient, or the missing-headers defect above
stays invisible:

```bash
.venv/bin/python -m pytest MTG_bot/strategic_brain/test_model.py -q
```

Measured device numbers, for comparison on any future re-image:

| What | Measured |
|---|---|
| bf16 matmul 2048 / 4096 / 8192 cubed | 85.0 / 74.0 / 78.7 TFLOP/s |
| device-to-device copy, 2 GB | 223.7 GB/s |
| tiny-op kernel launch | **6.93 us** |
| first kernel incl. CUDA context | 0.47 s |
| train step, 315.7M params, batch 1, bf16, fwd+bwd+AdamW | 331 ms |
| peak GPU memory at that scale | 5.52 GB of 130.7 |

The 6.93 us launch cost is the one that constrains design. It confirms the prediction below: a
decision composed of a few hundred small sequential kernels pays milliseconds in launch overhead
before doing any arithmetic, **at any model size**. The 5.52 GB confirms capacity is a non-issue.

**Benchmark hygiene.** The desktop session contends for the GPU. During bring-up, Xorg,
gnome-shell, Firefox and LM Studio together held ~850 MiB and were actively rendering, and the
latency harness correctly flagged a 48.6% between-round spread on the widest configuration. Close
the browser and LM Studio before taking numbers a decision will rest on.

## Cited sources

- [NVIDIA DGX Spark product page](https://www.nvidia.com/en-us/products/workstations/dgx-spark/)
- [Analysis of NVIDIA DGX Spark's GB10 SoC — chiplog](https://www.chiplog.io/p/analysis-of-nvidia-dgx-sparks-gb10)
- [Tom's Hardware DGX Spark review](https://www.tomshardware.com/pc-components/gpus/nvidia-dgx-spark-review)
- [PyTorch sm_121 support notes](https://github.com/jethac/dgx-spark-hijinks/blob/main/docs/PYTORCH_SM121_SUPPORT.md)
- [DGX Spark ML training setup guide](https://github.com/natolambert/dgx-spark-setup)
