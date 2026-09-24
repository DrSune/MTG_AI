# Micro-Checkpoint: DGX Spark Unified RAM Allocation Safety
- **Timestamp**: 2026-09-21 16:44:14
- **Scope**: `runtime/memory`
- **Outcome**: CRITICAL
- **Tags**: machine-quirk, unified-memory

## Attempted
Running standalone PyTorch/diffusers processes alongside 60GB vLLM pool.

## What Worked
vLLM + gateway circuit breaker trips at RAM_available < 2.5GB.

## What Failed & Root Cause
- **Failure**: Out-of-band PyTorch processes (qwen-image) bypass gateway and exhaust LPDDR5X unified RAM, causing kernel DMA starvation.
- **Root Cause**: Host RAM and GPU VRAM share the same physical 121GB memory bus on NVIDIA GB10.

## Actionable Invariant (Rule for Future Prompts)
> **Rule**: Never run standalone diffusion or large PyTorch scripts concurrently with vLLM unless available RAM > 40GB.
