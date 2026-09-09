# Hardware: the DGX Spark training target

All training runs on an **NVIDIA DGX Spark**. The Windows machine holding this repo is a
**development and tooling box only** and cannot run CUDA.

## The two machines

| | Dev box (this one) | Training target |
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
- **Bandwidth is mid-range.** ~273 GB/s is roughly consumer-GPU territory, about a fifth of an
  H100's HBM3. Anything that streams large tensors repeatedly will be bandwidth-starved.
- **Therefore: be greedy with parameters, stingy with memory traffic per decision.** A wider
  network that is read once per decision is cheap. A "thinking loop" that re-reads the whole model
  eight times per decision costs eight times the bandwidth and is the single most expensive design
  choice currently in the codebase.

A second consequence: at batch size 1, which is what naive RL rollout does, this machine is bound by
**kernel-launch overhead and Python**, not by FLOPs. A 300M-parameter model at batch 1 will not be
compute-limited. Throughput work belongs in the environment, in process-level parallelism, and in
batching inference across many concurrent games — not in shrinking the network.

## Software gotchas on aarch64 + sm_121

- **PyTorch:** official wheels historically topped out at `sm_120` and emitted a warning on
  `sm_121`. sm_120 and sm_121 are binary compatible, so an sm_120 build runs correctly. PyTorch 2.9
  added CUDA 13 wheel variants and Linux aarch64 CUDA wheel builds; use **2.9 or newer** and verify
  with `torch.cuda.get_device_capability()` on first boot.
- **Wheels in general:** aarch64 + CUDA is a much thinner ecosystem than x86-64. Expect to build
  from source or use NVIDIA's NGC containers for anything exotic. Prefer the NGC PyTorch container
  as the training base image rather than pip-installing into the host Python.
- **Do not assume a package exists for aarch64.** Check before depending on it. This applies to
  `flash-attn`, `bitsandbytes`, `xformers`, and most CUDA-kernel packages.
- **Numerics:** Blackwell does bf16 well and has FP4/FP6 tensor cores. Use **bf16 autocast**, not
  fp16. FP4 is an inference-time option, not a training one.

## Sanity checks to run on first boot

```bash
python -c "import torch; print(torch.__version__, torch.version.cuda, torch.cuda.is_available(), torch.cuda.get_device_capability(), torch.cuda.get_device_name(0))"
```

```bash
nvidia-smi; nproc; free -g
```

## Cited sources

- [NVIDIA DGX Spark product page](https://www.nvidia.com/en-us/products/workstations/dgx-spark/)
- [Analysis of NVIDIA DGX Spark's GB10 SoC — chiplog](https://www.chiplog.io/p/analysis-of-nvidia-dgx-sparks-gb10)
- [Tom's Hardware DGX Spark review](https://www.tomshardware.com/pc-components/gpus/nvidia-dgx-spark-review)
- [PyTorch sm_121 support notes](https://github.com/jethac/dgx-spark-hijinks/blob/main/docs/PYTORCH_SM121_SUPPORT.md)
- [DGX Spark ML training setup guide](https://github.com/natolambert/dgx-spark-setup)
