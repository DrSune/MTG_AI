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

## NGC: what it is, what it actually buys here, and when to adopt it

NGC is not a cloud you rent. It is three separate things sharing one name:

1. **The registry `nvcr.io`**, an ordinary OCI registry you pull from with plain `docker pull`.
2. **The images**, built monthly and tagged by *date*, not framework version.
   `nvcr.io/nvidia/pytorch:26.08-py3` is NVIDIA's August 2026 PyTorch image. Inside it, every NVIDIA
   library is a set NVIDIA tested *together* on that date. **That co-testing is the product.**
3. **The `ngc` CLI and API keys**, for private or gated content and non-container artifacts. **You do not
   need an account or a login for the PyTorch image** — verified: an anonymous bearer token from
   `nvcr.io/proxy_auth?scope=repository:nvidia/pytorch:pull` returns pull access and the `26.08-py3`
   manifest then returns 200. The bare `401` from `curl https://nvcr.io/v2/` is the standard registry auth
   challenge, not a paywall.

`/opt/NVIDIA AI Workbench` is a separate Electron GUI over the same containers. Ignore it for this project.

### The usual argument for the container is false on this box

The common pitch is "the container has kernels compiled for your arch, pip gives you PTX JIT and stalls".
Checked directly with `cuobjdump` on the installed pip wheel's `libtorch_cuda.so`: **475 `sm_120` cubins,
one `sm_121a` cubin, and zero PTX sections.** No PTX means PTX JIT is not even possible for torch's own
kernels — the driver loads `sm_120` SASS natively on this `sm_121` device, which is legal because 12.0 and
12.1 are one binary family. And the container's own build-time `TORCH_CUDA_ARCH_LIST` is
`8.0 8.6 9.0 10.0 11.0 12.0+PTX`, the **same** `sm_120` ceiling with a PTX fallback added. Neither build
compiles `sm_121`. The container does not fix a problem that exists.

### What it does buy, in order of how much it matters here

- **Reproducibility by digest.** This is the real "training stability" argument. Pinning
  `nvcr.io/nvidia/pytorch@sha256:<digest>` gets byte-identical libraries in a year.
  `pip install torch --index-url .../cu130` does not: PyTorch's index moves and old aarch64 builds are not
  retained. For a project whose protocol forbids citing a number that skipped a gate, **a published
  training number should name the image digest it was produced under.** Proposed as a new pre-flight line
  beside P6 in [`TRAINING_REVIEW_PROTOCOL.md`](TRAINING_REVIEW_PROTOCOL.md).
- **It fixes the missing-CPython-headers defect** described above, which is the one that actually bit us.
  The image ships the headers and a matched toolchain, so a dependency reachable from only one code path
  cannot be missing.
- **Transformer Engine prebuilt for aarch64** (2.18). The genuinely hard thing to get on ARM; building it
  yourself on a 20-core ARM box is a bad afternoon. Only matters once fused attention or MXFP8 is wanted.
- **nvFuser, CUTLASS DSL, and `TORCHINDUCTOR_CUTLASS_DIR` / `TRITON_PTXAS_PATH` preset.** That is
  `torch.compile` wired against a CUTLASS tree out of the box, which is the fix for the launch-bound
  batch-1 problem the 6.93 us measurement confirms.
- **A year-newer profiler.** Container Nsight Systems 2026.5 against host 2025.3.
- **A matched NCCL / NVSHMEM / OpenMPI / UCX / cuBLASMp set**, if multi-Spark clustering ever happens.

### What it costs, and one trap

A ~12 GB pull, 25-30 GB extracted. `docker exec` in front of every test run. Root-owned files appearing in
the git tree through the bind mount. An editor and LSP that no longer see the interpreter imports resolve
against. Against a 6-second `pytest` cycle over a pure-Python rules engine, that is a real tax.

**The trap:** cuDNN and cuBLASLt *do* JIT at runtime, independently of torch. Measured:
`~/.nv/ComputeCache` grew 78 MB during one cold softmax plus SDPA run, and a warm rerun grew it by 0 KB.
With `--rm` that cache lives inside the container and is discarded on exit, so **uncached, the container
loses to the venv on first-iteration latency.** Mount the cache if you care.

### The recommendation

**Keep the pip venv as the primary environment. Pull the container once as an oracle. Adopt it for
training at the moment you start producing numbers you intend to publish or compare across months.**

The work in front of this project is a rules-engine rebuild: pure Python, numpy, a 6-second `pytest`
cycle. That cycle is the most valuable asset the project has right now and `pyproject.toml` declares
nothing a container helps with. Use the container as the answer to *"is this the engine, my code, or my
environment?"* — re-run the same script in it, same answer means your code, different answer means a
library version and you know which side to chase. That is a high-value use of a co-tested stack and costs
nothing day to day.

### Setup, in order

**Step 1, owner action, the only blocking one.** The user is not in the `docker` group and `sudo` needs a
password, so this cannot be done by an agent. Note it is effectively a root grant on this box; accept that
knowingly.

```bash
sudo usermod -aG docker $USER    # then log out and back in, or: newgrp docker
sudo apt install python3.12-dev  # fixes the Triton backward-pass defect in the venv too
```

Everything else is already in place, verified: Docker 29.2.1 active, `nvidia-container-toolkit` 1.20.0
installed, `/var/run/cdi/nvidia.yaml` present declaring `nvidia.com/gpu`, and `/dev/nvidia*` world-readable.

**Step 2.** `docker pull nvcr.io/nvidia/pytorch:26.08-py3` — no login needed. 3.5 TB free, so free in practice.

**Step 3, the learning exercise.** Compare the two environments side by side:

```bash
docker run --rm -it --device nvidia.com/gpu=all --ipc=host \
  -v "$PWD":/workspace -w /workspace nvcr.io/nvidia/pytorch:26.08-py3 \
  python -c "import torch; print(torch.__version__, torch.version.cuda, torch.cuda.get_arch_list())"
```

Use `--device nvidia.com/gpu=all`, not `--gpus all`: CDI is on by default in Docker >= 28.3.0 and the spec
already declares an `all` device, so no `daemon.json` edit is needed. If it fails, that is when to run
`sudo nvidia-ctk runtime configure --runtime=docker && sudo systemctl restart docker` and switch to
`--gpus all`. Expect the container to report an **alpha** torch (`2.14.0a0+...`) and CUDA 13.4 against the
venv's `2.14.0+cu130` and CUDA 13.0 — and expect its arch list to stop at `sm_120` too.

**Also on NGC, for later:** `nvcr.io/nvidia/tensorrt:26.08-py3` (inference only), and
`nvcr.io/nvidia/cuda-dl-base:26.08-cuda13.4-devel-ubuntu24.04` if a slim project image is ever wanted
instead of inheriting 12 GB. `nvcr.io/nvidia/nemo-rl` exists and is **parked in
[`BACKLOG.md`](BACKLOG.md)**: it is shaped around LLM post-training with vLLM rollouts, and this project's
rollout is a Magic rules engine with a command zone and four-player boards, not token generation.

## Cited sources

- [NVIDIA DGX Spark product page](https://www.nvidia.com/en-us/products/workstations/dgx-spark/)
- [Analysis of NVIDIA DGX Spark's GB10 SoC — chiplog](https://www.chiplog.io/p/analysis-of-nvidia-dgx-sparks-gb10)
- [Tom's Hardware DGX Spark review](https://www.tomshardware.com/pc-components/gpus/nvidia-dgx-spark-review)
- [PyTorch sm_121 support notes](https://github.com/jethac/dgx-spark-hijinks/blob/main/docs/PYTORCH_SM121_SUPPORT.md)
- [DGX Spark ML training setup guide](https://github.com/natolambert/dgx-spark-setup)
