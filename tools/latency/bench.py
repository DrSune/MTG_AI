"""Decision-latency benchmark.

The size-vs-speed decision gets made from this script's output. See docs/DESIGN_LATENCY.md
for what the numbers mean and NORTH_STAR.md section 1a for why they matter.

Run it on this box today and on the DGX Spark when it arrives. Same script, same output
schema, so the two are directly comparable:

    python tools/latency/bench.py --reps 60
    python tools/latency/bench.py --reps 200 --dtype bf16 --out reports/latency_dgx.json

WHAT IS AND IS NOT TRANSFERABLE between the Intel-XPU dev box and the GB10:

  transferable      the analytic columns (parameters, bytes per decision, FLOPs per
                    decision, kernel launches). These are properties of the architecture
                    and are exact.
  transferable      the RATIO of wall-clock between two configurations on the same box.
                    If v1 is 2.6x the cost of v0.5 here, it is close to that there.
  NOT transferable  absolute wall-clock. Different bandwidth, different compute, and a
                    different host CPU dispatching the kernels.

So the GB10 columns are a roofline PROJECTION, not a measurement, and they are labelled
as such. Replace them with real numbers by running this on the Spark.

A NOTE ON THE ACTION-COUNT SWEEP. The current engine produces a median of 1 legal action
and a maximum of 6 (measured, tools/latency/positions.py). That is not Magic; it is the
symptom of broken targeting and absent priority documented in docs/ARCHITECTURE.md. A
real four-player Commander decision faces tens to low hundreds of legal actions. So the
sweep covers the projected range and the measured range is only the floor.
"""

from __future__ import annotations

import argparse
import json
import platform
import statistics
import sys
import time
from pathlib import Path

import torch

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from tools.latency.shapes import (  # noqa: E402
    PRESETS, PRESETS_BY_NAME, ArchSpec, LatencyProbe, cost_model, project_gb10, GB10,
    measure_launches,
)


# --------------------------------------------------------------------------------------

def pick_device(requested: str | None) -> torch.device:
    if requested:
        return torch.device(requested)
    try:
        from MTG_bot.utils.device import get_device
        return get_device()
    except Exception:
        if torch.cuda.is_available():
            return torch.device("cuda")
        if hasattr(torch, "xpu") and torch.xpu.is_available():
            return torch.device("xpu")
        return torch.device("cpu")


def sync(device: torch.device) -> None:
    """Barrier. Without this every measurement on an async accelerator is a lie."""
    if device.type == "cuda":
        torch.cuda.synchronize()
    elif device.type == "xpu":
        torch.xpu.synchronize()


def percentiles(xs_ms: list[float]) -> dict:
    xs = sorted(xs_ms)

    def p(q):
        i = min(len(xs) - 1, max(0, int(round(q * (len(xs) - 1)))))
        return round(xs[i], 3)

    return {
        "n": len(xs), "min": round(xs[0], 3), "p50": p(.50), "p90": p(.90),
        "p99": p(.99), "max": round(xs[-1], 3), "mean": round(statistics.mean(xs), 3),
        # Tail ratio is the number that actually decides whether a config is safe under a
        # match clock. A p99 five times the median means the bot stalls on hard turns.
        "tail_ratio_p99_over_p50": round(p(.99) / max(p(.50), 1e-9), 2),
    }


def free_cache(device: torch.device) -> None:
    if device.type == "cuda":
        torch.cuda.empty_cache()
    elif device.type == "xpu":
        torch.xpu.empty_cache()


def burn_in(device: torch.device, dtype: torch.dtype, seconds: float = 3.0) -> None:
    """Drive the accelerator to a steady clock before measuring anything.

    On an integrated GPU sharing power and memory with the CPU, the first seconds of any
    workload run at a different clock than the rest. Skipping this makes whichever config
    is measured first look slow, which is exactly the artefact that made board caching
    appear to be a pessimisation in the first version of this script.
    """
    a = torch.randn(1024, 1024, device=device, dtype=dtype)
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < seconds:
        for _ in range(20):
            a = torch.nn.functional.gelu(a @ a) * 0.02
    sync(device)
    del a
    free_cache(device)


def _measure_block(model: LatencyProbe, inputs, device: torch.device,
                   reps: int, warmup: int, force) -> list[float]:
    ids, comp, acts = inputs
    with torch.inference_mode():
        model.reset_cache()
        _, _, state = model(ids, comp, acts, None, force_tier_a=True)
        for _ in range(warmup):
            _, _, state = model(ids, comp, acts, state, force_tier_a=force)
        sync(device)

        out = []
        for _ in range(reps):
            t0 = time.perf_counter()
            _, _, state = model(ids, comp, acts, state, force_tier_a=force)
            sync(device)
            out.append((time.perf_counter() - t0) * 1000.0)
    return out


def time_one(spec: ArchSpec, n_tokens: int, n_actions: int, device: torch.device,
             dtype: torch.dtype, reps: int, warmup: int, cached_board: bool,
             rounds: int = 3) -> dict:
    """Measure one configuration.

    Measured over `rounds` independent blocks rather than one long run, and the reported
    figure is the median of the per-round medians. A single block is not trustworthy on a
    shared-memory accelerator: thermal drift and allocator state move the number by more
    than the architectural differences we are trying to resolve.
    """
    torch.manual_seed(0)
    model = LatencyProbe(spec).to(device=device, dtype=dtype).eval()

    inputs = (
        torch.randint(0, spec.vocab_size, (1, n_tokens), device=device),
        torch.randn(1, n_tokens, spec.component_dim, device=device, dtype=dtype),
        torch.randn(1, n_actions, spec.action_desc_dim, device=device, dtype=dtype),
    )
    force = False if cached_board else None

    # Discard the first block entirely. Constructing a several-hundred-megabyte model
    # immediately before measuring means the first block pays allocator growth and page
    # faults, and that pollutes the median. This was measurably the case: it made v1 read
    # 30 ms when its true blended cost is 12 ms.
    _measure_block(model, inputs, device, max(4, reps // 4), warmup, force)

    all_samples: list[float] = []
    round_p50: list[float] = []
    for _ in range(max(1, rounds)):
        block = _measure_block(model, inputs, device, reps, warmup, force)
        all_samples.extend(block)
        block.sort()
        round_p50.append(block[len(block) // 2])

    cm = cost_model(spec, n_tokens, n_actions, dtype_bytes=torch.finfo(dtype).bits // 8)
    # Count real ATen dispatches rather than trusting the analytic estimate. Op count is
    # device independent, so a dev-box count is valid for the GB10 projection, and the
    # dispatch term is a large share of batch-1 latency on a 20-core ARM host.
    try:
        launches = measure_launches(spec, n_tokens, n_actions)
    except Exception:
        launches = None
    proj = project_gb10(cm, launches=(launches["blended"] if launches else None))

    del model, inputs
    free_cache(device)

    stats = percentiles(all_samples)
    round_p50.sort()
    stats["p50_median_of_rounds"] = round(round_p50[len(round_p50) // 2], 3)
    # If the rounds disagree by more than ~15% the box is too noisy to separate configs
    # this close together, and the run should be repeated on a quiet machine.
    stats["round_spread_pct"] = round(
        100.0 * (round_p50[-1] - round_p50[0]) / max(round_p50[len(round_p50) // 2], 1e-9), 1
    )
    # Effective achieved bandwidth. This is the calibration number: it says how close this
    # device gets to streaming the weights at full speed, and it is what makes the GB10
    # roofline projection checkable rather than a guess. Compare it against the device's
    # theoretical bandwidth; a large gap means the model is launch-bound, not bandwidth-bound.
    p50_s = stats["p50_median_of_rounds"] / 1000.0
    stats["effective_gb_per_s"] = round(cm.bytes_per_decision / max(p50_s, 1e-9) / 1e9, 1)

    return {
        "arch": spec.name,
        "n_tokens": n_tokens,
        "n_actions": n_actions,
        "cached_board": cached_board,
        "measured_ms": stats,
        "analytic": cm.as_dict(),
        "kernel_launches_measured": launches,
        "gb10_projection_ms": {k: (round(v * 1000, 3) if isinstance(v, float) else v)
                               for k, v in proj.items()},
    }


# --------------------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Decision-latency benchmark for candidate architectures.")
    ap.add_argument("--archs", nargs="*", default=[p.name for p in PRESETS])
    ap.add_argument("--tokens", nargs="*", type=int, default=[64, 128, 256, 384],
                    help="board token counts. 64 is roughly today's visible-entity p90; "
                         "256-384 is a projected 4-player Commander board.")
    ap.add_argument("--actions", nargs="*", type=int, default=[8, 32, 96, 192],
                    help="legal action counts. Today's engine maxes at 6 (measured); a real "
                         "Commander decision is tens to low hundreds.")
    ap.add_argument("--reps", type=int, default=60)
    ap.add_argument("--warmup", type=int, default=10)
    ap.add_argument("--dtype", default="bf16", choices=["bf16", "fp16", "fp32"])
    ap.add_argument("--device", default=None)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--rounds", type=int, default=5,
                    help="independent measurement blocks per config; the reported p50 is the "
                         "median of their medians. More rounds, less drift.")
    ap.add_argument("--burn-in", type=float, default=3.0,
                    help="seconds of dummy work before measuring, to reach a steady clock")
    ap.add_argument("--quick", action="store_true",
                    help="one representative point per arch instead of the full sweep")
    a = ap.parse_args()

    device = pick_device(a.device)
    dtype = {"bf16": torch.bfloat16, "fp16": torch.float16, "fp32": torch.float32}[a.dtype]

    env = {
        "device": str(device),
        "torch": torch.__version__,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "dtype": a.dtype,
        "cuda_available": torch.cuda.is_available(),
        "device_name": (torch.cuda.get_device_name(0) if device.type == "cuda"
                        else (torch.xpu.get_device_name(0) if device.type == "xpu" else platform.processor())),
        "gb10_assumptions": GB10,
    }
    if device.type == "cuda":
        env["cuda_capability"] = list(torch.cuda.get_device_capability())
        env["cuda_arch_list"] = torch.cuda.get_arch_list()

    print(json.dumps(env, indent=2, default=str))
    print()

    grid = ([(a.tokens[len(a.tokens) // 2], a.actions[len(a.actions) // 2])] if a.quick
            else [(t, n) for t in a.tokens for n in a.actions])

    print(f"burn-in ({a.burn_in:.0f}s) to reach a steady clock ...", flush=True)
    burn_in(device, dtype, a.burn_in)

    results = []
    hdr = (f"{'arch':<14}{'tok':>5}{'act':>5}{'p50':>9}{'p99':>9}{'tail':>7}{'spread':>8}"
           f"{'params':>12}{'MB/dec':>9}{'GB/s':>7}{'GB10*':>9}")
    print(hdr)
    print("-" * len(hdr))

    jobs = []
    for name in a.archs:
        spec = PRESETS_BY_NAME.get(name)
        if spec is None:
            print(f"  ! unknown arch {name!r}, skipping")
            continue
        for n_tok, n_act in grid:
            jobs.append((spec, n_tok, n_act, name.endswith("-cached")))

    for spec, n_tok, n_act, cached in jobs:
        try:
            r = time_one(spec, n_tok, n_act, device, dtype, a.reps, a.warmup, cached,
                         rounds=a.rounds)
        except Exception as exc:                     # keep the sweep going
            print(f"{spec.name:<14}{n_tok:>5}{n_act:>5}   FAILED: {type(exc).__name__}: {exc}")
            results.append({"arch": spec.name, "n_tokens": n_tok, "n_actions": n_act,
                            "error": f"{type(exc).__name__}: {exc}"})
            continue
        results.append(r)
        m, an, pj = r["measured_ms"], r["analytic"], r["gb10_projection_ms"]
        flag = " !" if m["round_spread_pct"] > 15 else ""
        print(f"{spec.name:<14}{n_tok:>5}{n_act:>5}"
              f"{m['p50_median_of_rounds']:>9.2f}{m['p99']:>9.2f}"
              f"{m['tail_ratio_p99_over_p50']:>7.1f}{m['round_spread_pct']:>7.1f}%{flag}"
              f"{an['params_total'] / 1e6:>10.1f}M"
              f"{an['bytes_per_decision'] / 1e6:>9.1f}"
              f"{m['effective_gb_per_s']:>7.0f}"
              f"{pj['cuda_graph_s']:>9.2f}")

    print("\n  p50          : median of per-round medians, milliseconds, on this device")
    print("  tail         : p99 / p50. This is the number that decides whether a config is")
    print("                 safe under a match clock, not the median.")
    print("  spread       : disagreement between rounds. Above 15% (flagged !) the box is too")
    print("                 noisy to separate configs this close together; re-run when quiet.")
    print("  MB/dec       : weight bytes streamed per decision, bf16. Machine independent.")
    print("  GB/s         : effective achieved bandwidth = MB/dec / p50. The calibration")
    print("                 number. If it is far below the device's theoretical bandwidth,")
    print("                 the config is launch-bound rather than bandwidth-bound.")
    print("  GB10*        : ROOFLINE PROJECTION for the DGX Spark with CUDA graphs, ms.")
    print("                 NOT a measurement. Re-run this script on the Spark to replace it.")
    print(f"                 Assumes {GB10['streaming_efficiency']:.0%} streaming efficiency on "
          f"{GB10['bandwidth_bytes_s']/1e9:.0f} GB/s and {GB10['compute_efficiency']:.0%} of "
          f"{GB10['dense_bf16_flops']/1e12:.0f} TFLOPS.")
    print("                 Kernel launches are MEASURED, not estimated.")

    payload = {"env": env, "results": results,
               "note": "See docs/DESIGN_LATENCY.md. GB10 columns are projections until run on the Spark."}
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(payload, indent=1, default=str), encoding="utf-8")
        print(f"\nwrote {a.out}")


if __name__ == "__main__":
    main()
