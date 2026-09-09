# Latency findings, first pass

Measured 2026-09-10 with [`tools/latency/bench.py`](../tools/latency/bench.py) on the **dev box**,
not the DGX. Raw data in `latency_devbox.json` and `latency_sweep_devbox.json`.

```
device      Intel Arc 140V (16 GB), torch 2.11.0+xpu, bf16, batch 1
sweep       5 architectures x {64,128,256,384} tokens x {8,32,96,192} legal actions
method      3-5 independent rounds per config, first block discarded, 3 s burn-in,
            reported p50 is the median of per-round medians
```

**These are not DGX numbers.** What transfers is the analytic cost model and the ratios between
configurations. What does not is absolute wall-clock. Re-run the same script on the Spark.

## Finding 1 — latency is flat in board size and in action count

This is the headline, and it is not what I expected.

| config | 64 tokens | 384 tokens | 8 actions | 192 actions |
|---|---|---|---|---|
| v0.5 | 17.9 ms | 15.6 ms | 15.8 ms | 16.9 ms |
| v1 | 16.4 ms | 17.3 ms | 15.4 ms | 17.5 ms |
| v1-cached | 15.0 ms | 17.1 ms | 14.6 ms | 16.6 ms |
| v2-wide | 28.2 ms | 34.8 ms | 25.9 ms | 29.8 ms |

A six-fold increase in board tokens and a twenty-four-fold increase in legal actions move the
median by less than the run-to-run noise.

**Why:** at batch 1 these models are bound by weight bytes and kernel dispatch, not by FLOPs.
Activations are tiny next to the weights, so adding tokens adds arithmetic the device was not
using anyway. Effective achieved bandwidth sits at 20 to 50 GB/s against roughly 120 GB/s
theoretical on this part, which is the signature of a launch-bound, low-occupancy workload.

**This should transfer to the GB10, and it is the same argument for the same reason.** The Spark
shares one 273 GB/s bus between CPU and GPU, so it has the same character: capacity is cheap,
bandwidth per decision is the scarce thing, and batch-1 work is dispatch-dominated.

**What it means.** The worry that big Commander boards and long legal-move lists would blow the
clock is, at these sizes, unfounded. A 400-token four-player board with 200 legal actions costs
about the same as a 64-token board with 8. Do not spend engineering effort shrinking the board
representation for latency reasons. Spend it on the thing that does cost.

## Finding 2 — reasoning passes are the entire latency variance budget

| config | passes | p50 | weight bytes per decision |
|---|---|---|---|
| current | 1 | 19.0 ms | 800 MB |
| **current-8pass** | **8** | **169 ms** | **4,325 MB** |
| v1 | 1 | 16.3 ms | 602 MB |
| **v1-3pass** | **3** | **46.4 ms** | **1,542 MB** |
| v1-cached | 1, board cached | 15.9 ms | 517 MB |
| v2-wide (1.05 B params) | 1 | 31.4 ms | 1,498 MB |

Going from one reasoning pass to eight costs **8.9×**. Going from a 413M model to a 1.05B model
costs **1.9×**. **The adaptive thinking loop is roughly five times more expensive per unit of
latency than making the model two and a half times bigger.**

The current model's default is `num_passes=8` at collection time
(`strategic_brain/student.py`, `max_thoughts` from `config_rl.py:37`). On this evidence that
default is the single most expensive latency decision in the codebase, and it buys nothing today
because the rethink gate is an untrained head.

**This directly answers the concern about variable difficulty.** The variance does not come from
the board or the action list. It comes from how many times the agent chooses to run the network.
That is under the agent's control, which makes it a metareasoning problem rather than a scaling
problem, and metareasoning is learnable. See [`../docs/DESIGN_LATENCY.md`](../docs/DESIGN_LATENCY.md).

## Finding 3 — board caching is worth about 2×, and the cost model is validated

Measured directly on one model instance, interleaved to cancel drift:

| | p50 |
|---|---|
| board encoder every decision | 23.0 ms |
| board encoder never (cached) | 10.1 ms |
| blended at 1-in-6 cadence | 12.3 ms |

Marginal cost of the board encoder is 12.9 ms, and amortising it over six decisions recovers most
of that. This is the two-tier split in [`../docs/DESIGN_TRAINING.md`](../docs/DESIGN_TRAINING.md),
and it is the idea that was deleted from `RL_ARCHITECTURE.md` in commit `db5e024`.

The analytic weight-byte model was checked against measurement and holds:

| comparison | predicted | measured |
|---|---|---|
| board every decision vs cached | 1.97× | 2.27× |
| board at 1-in-6 cadence vs cached | 1.16× | 1.21× |

Within about 15%, which is what low-occupancy effects explain. So the GB10 roofline projection
built on that model is worth something, though it remains a projection.

## Finding 4 — the current engine's action space is degenerate

Measured over 2,400 real decisions across 6 Commander games
([`tools/latency/positions.py`](../tools/latency/positions.py)):

| | value |
|---|---|
| legal actions, median | **1** |
| legal actions, p99 / max | 5 / 6 |
| spell casts in 2,400 decisions | **25** |
| visible entities, median / max | 37 / 60 |
| total graph entities | constant 214 |

A median of one legal action is not Magic. It is the direct symptom of the broken targeting and
absent priority in [`../docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md). Every latency and strength
number taken on the current engine measures a degenerate game, which is why the benchmark sweeps a
projected action range rather than the measured one.

The constant 214 entities is the library leak: libraries never leave the graph, so the encoder sees
them. Visible entities peak at 60.

## GB10 roofline projections

Not measurements. Derived from exact byte counts and **measured** kernel-launch counts, at
273 GB/s with a stated 70% streaming efficiency and 125 TFLOPS dense bf16 at 40% utilisation,
with CUDA graphs assumed so dispatch collapses.

| config | projected ms | measured launches per decision | bound by |
|---|---|---|---|
| v0.5 | 1.83 | 492 | bandwidth |
| v1-cached | 2.86 | 492 | bandwidth |
| v1 | 3.31 | 526 | bandwidth |
| v2-wide (1.05 B) | 8.00 | 560 | bandwidth |
| v1-3pass | 8.23 | 1,458 | bandwidth |
| current | 4.35 | 696 | bandwidth |
| current-8pass | 22.79 | 5,505 | bandwidth |

Every configuration is bandwidth bound; none is compute bound. That is the expected character of
the machine and it is why parameter count is cheap and repeated passes are not.

An earlier version of this file quoted projections about 1.43x lower. Those divided by the full
273 GB/s with no streaming derate and used a guessed kernel count. Both are now fixed: the derate
is stated explicitly in `tools/latency/shapes.py` so it can be replaced with a measurement, and
launch counts are counted with `TorchDispatchMode` rather than estimated. Op count is device
independent, so a dev-box count is valid for the Spark.

## Reconciling against the clock budget

[`../docs/DESIGN_LATENCY.md`](../docs/DESIGN_LATENCY.md) derives a per-priority-window engineering
target of **140 ms** at the pessimistic end, from a 1,050 s per-seat bank and a design estimate of
7,500 windows per match.

| config | projected | headroom against 140 ms |
|---|---|---|
| v0.5 | 1.83 ms | 76x |
| v1 (392 M) | 3.31 ms | 42x |
| v2-wide (1.05 B) | 8.00 ms | 17x |
| current-8pass | 22.8 ms | 6x |

**The model is not the thing that will breach the clock.** Even a billion-parameter dense model at
one pass has an order of magnitude of headroom. Two things eat that headroom instead, and both are
larger than any model-size decision:

1. **Reasoning passes.** Eight passes multiply the cost by roughly nine.
2. **Decision count.** Block declaration emits one action per attacker-blocker pair, so a
   20-versus-20 Commander board is up to 400 *sequential* model calls in one combat step. At 140 ms
   each that is 56 seconds on a single combat step. This is the only mechanism found that actually
   threatens the match clock, and the fix is in the action space, not the network.

## What this does not yet tell us

- **Nothing about quality.** Latency without a strength axis cannot decide model size. The sizing
  decision needs a strength-per-millisecond curve, and there is currently no trustworthy strength
  measurement at all.
- **Nothing about the environment.** The engine costs 7.7 ms per step today, which is *comparable
  to the whole network forward pass*. On the real decision path the environment may well dominate.
- **Nothing measured on the target hardware.** Everything above is a dev-box measurement plus a
  projection.
