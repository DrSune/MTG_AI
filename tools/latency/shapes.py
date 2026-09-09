"""Shape-accurate stand-ins for candidate network architectures.

Why these exist. Decision latency depends on the *computational shape* of a network
(dimensions, depth, token counts, how often each part runs), not on whether its weights
are trained. So we can measure the latency of an architecture we have not built yet, by
building something with the same shape and timing it.

These modules are deliberately NOT the real model. They exist only to be timed. Do not
train them, do not import them from the training code.

Two things are reported for every config:

  * measured wall-clock on whatever device is present (Intel XPU here, CUDA on the Spark)
  * analytic parameter count, weight bytes read per decision, and FLOPs per decision

The analytic numbers are machine independent and are what lets us project GB10 latency
from a machine that is not a GB10. See docs/DESIGN_LATENCY.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional

import torch
import torch.nn as nn
import torch.nn.functional as F


# --------------------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------------------

@dataclass(frozen=True)
class ArchSpec:
    """One candidate architecture.

    tier_a_* is the board encoder, which only re-runs when the board materially changes.
    tier_b_* is the decision head, which runs on every single decision.
    A single-tier architecture (like the current model) is expressed as tier_b_layers=0
    with tier_a_every=1, i.e. the whole trunk runs every decision.
    """

    name: str
    d_model: int
    n_heads: int
    tier_a_layers: int
    tier_b_layers: int
    d_ff: int
    # How often the expensive board encoder actually runs, as 1-in-N decisions.
    # 1 means "every decision", which is what the current model does.
    tier_a_every: int = 1
    # Recurrent temporal carrier.
    d_state: int = 0
    # Reasoning passes over the decision head. The current model can run up to 8.
    reasoning_passes: int = 1
    # Autoregressive plan length. The current model emits 5 steps, each through a
    # 4-layer transformer decoder.
    plan_steps: int = 0
    plan_layers: int = 0
    # Card identity table. Large but gathered, not streamed, so it barely costs latency.
    vocab_size: int = 65536
    d_vocab: int = 512
    component_dim: int = 96
    action_desc_dim: int = 128
    use_sdpa: bool = True

    def label(self) -> str:
        return self.name


# The configurations the sizing decision will be made from.
# "current" reproduces the shape of MTG_bot/strategic_brain/model.py at
# config_rl.py defaults, including the dim_feedforward=2048 that nobody chose.
PRESETS = [
    ArchSpec(
        name="current",
        d_model=1024, n_heads=16, tier_a_layers=16, tier_b_layers=0, d_ff=2048,
        tier_a_every=1, d_state=1024, reasoning_passes=1,
        plan_steps=5, plan_layers=4, vocab_size=50000, d_vocab=1024, component_dim=32,
        action_desc_dim=65,
    ),
    ArchSpec(
        name="current-8pass",
        d_model=1024, n_heads=16, tier_a_layers=16, tier_b_layers=0, d_ff=2048,
        tier_a_every=1, d_state=1024, reasoning_passes=8,
        plan_steps=5, plan_layers=4, vocab_size=50000, d_vocab=1024, component_dim=32,
        action_desc_dim=65,
    ),
    ArchSpec(
        name="v0.5",
        d_model=768, n_heads=12, tier_a_layers=12, tier_b_layers=4, d_ff=3072,
        tier_a_every=6, d_state=1536, reasoning_passes=1, plan_steps=5, plan_layers=2,
    ),
    ArchSpec(
        name="v1",
        d_model=1024, n_heads=16, tier_a_layers=20, tier_b_layers=4, d_ff=4096,
        tier_a_every=6, d_state=2048, reasoning_passes=1, plan_steps=5, plan_layers=2,
    ),
    ArchSpec(
        name="v1-cached",  # v1 on a decision where the board did not change
        d_model=1024, n_heads=16, tier_a_layers=20, tier_b_layers=4, d_ff=4096,
        tier_a_every=10 ** 9, d_state=2048, reasoning_passes=1, plan_steps=5, plan_layers=2,
    ),
    ArchSpec(
        name="v1-3pass",  # v1 on a hard position that wants three reasoning passes
        d_model=1024, n_heads=16, tier_a_layers=20, tier_b_layers=4, d_ff=4096,
        tier_a_every=6, d_state=2048, reasoning_passes=3, plan_steps=5, plan_layers=2,
    ),
    ArchSpec(
        name="v2-wide",  # what "be greedy with the 128 GB" looks like as a dense model
        d_model=1536, n_heads=24, tier_a_layers=24, tier_b_layers=6, d_ff=6144,
        tier_a_every=6, d_state=2048, reasoning_passes=1, plan_steps=5, plan_layers=2,
    ),
]

PRESETS_BY_NAME = {p.name: p for p in PRESETS}


# --------------------------------------------------------------------------------------
# Modules
# --------------------------------------------------------------------------------------

class _Block(nn.Module):
    """A pre-norm transformer block, optionally with cross-attention.

    Uses F.scaled_dot_product_attention rather than nn.MultiheadAttention. That is not a
    detail: SDPA avoids materialising the T-by-T attention matrix, which is a 1.45x
    activation-memory win, and it is what the real model should use too.
    """

    def __init__(self, d: int, h: int, d_ff: int, cross: bool = False, use_sdpa: bool = True):
        super().__init__()
        self.h, self.dh, self.use_sdpa = h, d // h, use_sdpa
        self.n1 = nn.LayerNorm(d)
        self.qkv = nn.Linear(d, 3 * d, bias=False)
        self.proj = nn.Linear(d, d, bias=False)
        self.cross = cross
        if cross:
            self.nc = nn.LayerNorm(d)
            self.q_c = nn.Linear(d, d, bias=False)
            self.kv_c = nn.Linear(d, 2 * d, bias=False)
            self.proj_c = nn.Linear(d, d, bias=False)
        self.n2 = nn.LayerNorm(d)
        self.ff1 = nn.Linear(d, d_ff, bias=False)
        self.ff2 = nn.Linear(d_ff, d, bias=False)

    def _heads(self, x, B, T):
        return x.view(B, T, self.h, self.dh).transpose(1, 2)

    def _attn(self, q, k, v):
        if self.use_sdpa:
            return F.scaled_dot_product_attention(q, k, v)
        a = (q @ k.transpose(-2, -1)) * (self.dh ** -0.5)
        return a.softmax(dim=-1) @ v

    def forward(self, x, memory: Optional[torch.Tensor] = None):
        B, T, _ = x.shape
        q, k, v = self.qkv(self.n1(x)).chunk(3, dim=-1)
        o = self._attn(self._heads(q, B, T), self._heads(k, B, T), self._heads(v, B, T))
        x = x + self.proj(o.transpose(1, 2).reshape(B, T, -1))

        if self.cross and memory is not None:
            S = memory.shape[1]
            qc = self._heads(self.q_c(self.nc(x)), B, T)
            kc, vc = self.kv_c(memory).chunk(2, dim=-1)
            o = self._attn(qc, self._heads(kc, B, S), self._heads(vc, B, S))
            x = x + self.proj_c(o.transpose(1, 2).reshape(B, T, -1))

        h = self.n2(x)
        return x + self.ff2(F.gelu(self.ff1(h)))


class LatencyProbe(nn.Module):
    """Shape-accurate stand-in for a candidate architecture. Timing only."""

    def __init__(self, spec: ArchSpec):
        super().__init__()
        self.spec = spec
        d = spec.d_model

        self.card_emb = nn.Embedding(spec.vocab_size, spec.d_vocab)
        self.card_up = nn.Linear(spec.d_vocab, d, bias=False)
        self.comp_mlp = nn.Sequential(
            nn.Linear(spec.component_dim, d), nn.GELU(), nn.Linear(d, d)
        )
        self.fuse = nn.Linear(2 * d, d, bias=False)

        self.tier_a = nn.ModuleList(
            _Block(d, spec.n_heads, spec.d_ff, cross=False, use_sdpa=spec.use_sdpa)
            for _ in range(spec.tier_a_layers)
        )
        self.tier_b = nn.ModuleList(
            _Block(d, spec.n_heads, spec.d_ff, cross=True, use_sdpa=spec.use_sdpa)
            for _ in range(spec.tier_b_layers)
        )

        self.rnn = nn.GRUCell(d, spec.d_state) if spec.d_state else None
        self.state_proj = nn.Linear(spec.d_state, d, bias=False) if spec.d_state else None

        self.act_enc = nn.Sequential(
            nn.Linear(spec.action_desc_dim, d), nn.GELU(), nn.Linear(d, d)
        )
        self.plan = nn.ModuleList(
            _Block(d, spec.n_heads, spec.d_ff, cross=True, use_sdpa=spec.use_sdpa)
            for _ in range(spec.plan_layers)
        )
        self.ptr = nn.Linear(d, d, bias=False)
        self.value = nn.Linear(d, 1)

        # Cached board encoding, standing in for the Tier A KV cache.
        self._cache: Optional[torch.Tensor] = None
        self._since = 10 ** 9

    def reset_cache(self):
        self._cache, self._since = None, 10 ** 9

    def forward(self, card_ids, comp, act_desc, state=None, force_tier_a: Optional[bool] = None):
        s = self.spec
        B, T = card_ids.shape

        run_a = force_tier_a if force_tier_a is not None else (self._since >= s.tier_a_every)
        if run_a or self._cache is None:
            x = self.fuse(torch.cat([self.card_up(self.card_emb(card_ids)),
                                     self.comp_mlp(comp)], dim=-1))
            for blk in self.tier_a:
                x = blk(x)
            self._cache, self._since = x, 0
        else:
            x = self._cache
            self._since += 1

        pooled = x.mean(dim=1)
        if self.rnn is not None:
            if state is None:
                state = torch.zeros(B, s.d_state, device=card_ids.device, dtype=pooled.dtype)
            state = self.rnn(pooled, state)
            ctx = self.state_proj(state).unsqueeze(1)
        else:
            ctx = pooled.unsqueeze(1)

        actions = self.act_enc(act_desc)                      # (B, A, d)
        logits = None
        for _ in range(max(1, s.reasoning_passes)):
            dec = torch.cat([ctx, actions], dim=1)            # (B, 1+A, d)
            for blk in self.tier_b:
                dec = blk(dec, memory=x)
            q = dec[:, :1, :]
            for _ in range(max(0, s.plan_steps)):
                for blk in self.plan:
                    q = blk(q, memory=dec)
            logits = torch.bmm(actions, self.ptr(q[:, 0]).unsqueeze(2)).squeeze(2)
        return logits, self.value(q[:, 0]), state


# --------------------------------------------------------------------------------------
# Analytic cost model - machine independent, this is what projects to the GB10
# --------------------------------------------------------------------------------------

@dataclass
class CostModel:
    params_total: int
    params_streamed_per_decision: int   # weights actually READ for one decision
    bytes_per_decision: int             # the above in bf16
    flops_per_decision: int
    kernel_launches: int                # approximate; drives ARM dispatch overhead

    def as_dict(self):
        return asdict(self)


def _block_params(d: int, d_ff: int, cross: bool) -> int:
    p = 3 * d * d + d * d + 2 * d * d_ff + 4 * d      # qkv, proj, ff, 2 layernorms
    if cross:
        p += d * d + 2 * d * d + d * d + 2 * d        # q, kv, proj, layernorm
    return p


def _block_flops(d: int, d_ff: int, T: int, S: int, cross: bool) -> int:
    f = 2 * T * (3 * d * d + d * d + 2 * d * d_ff)   # projections + feed-forward
    f += 4 * T * T * d                                # self attention scores and values
    if cross:
        f += 2 * T * d * d + 2 * S * 2 * d * d + 2 * T * d * d
        f += 4 * T * S * d
    return f


# Kernel launch count matters because on a 20-core ARM host each launch costs roughly
# 6-10 us of dispatch, and at these model sizes that is comparable to the compute itself.
# Ignoring it is how you predict 3 ms and measure 7 ms.
#
# This used to be an analytic guess of 14 kernels per block plus a 20-launch residual.
# It is now MEASURED with measure_launches() below, because the guess was load-bearing
# for every GB10 projection and a guess has no business there. The analytic figure
# survives only as a fallback when the measurement cannot run.
_KERNELS_PER_BLOCK = 14


def cost_model(spec: ArchSpec, n_tokens: int, n_actions: int, dtype_bytes: int = 2) -> CostModel:
    d, d_ff = spec.d_model, spec.d_ff
    T, A = n_tokens, n_actions
    T_dec = 1 + A

    embed_p = spec.vocab_size * spec.d_vocab
    front_p = (spec.d_vocab * d) + (spec.component_dim * d + d * d) + (2 * d * d)
    a_p = spec.tier_a_layers * _block_params(d, d_ff, cross=False)
    b_p = spec.tier_b_layers * _block_params(d, d_ff, cross=True)
    plan_p = spec.plan_layers * _block_params(d, d_ff, cross=True)
    rnn_p = (3 * (d * spec.d_state + spec.d_state * spec.d_state) + spec.d_state * d) if spec.d_state else 0
    head_p = (spec.action_desc_dim * d + d * d) + d * d + d

    total = embed_p + front_p + a_p + b_p + plan_p + rnn_p + head_p

    # Amortise Tier A over its cadence. The embedding table is gathered, not streamed:
    # only the rows for tokens actually on the board are read.
    a_share = (front_p + a_p) / max(1, spec.tier_a_every)
    gathered = T * spec.d_vocab
    passes = max(1, spec.reasoning_passes)
    streamed = a_share + gathered + rnn_p + head_p + passes * (b_p + spec.plan_steps * plan_p)

    a_fl = spec.tier_a_layers * _block_flops(d, d_ff, T, T, cross=False)
    a_fl += 2 * T * (spec.d_vocab * d + spec.component_dim * d + d * d + 2 * d * d)
    b_fl = spec.tier_b_layers * _block_flops(d, d_ff, T_dec, T, cross=True)
    plan_fl = spec.plan_layers * _block_flops(d, d_ff, 1, T_dec, cross=True) * spec.plan_steps
    rnn_fl = 2 * 3 * (d * spec.d_state + spec.d_state ** 2) if spec.d_state else 0
    head_fl = 2 * A * (spec.action_desc_dim * d + d * d) + 2 * A * d

    flops = a_fl / max(1, spec.tier_a_every) + passes * (b_fl + plan_fl) + rnn_fl + head_fl

    launches = (
        spec.tier_a_layers * _KERNELS_PER_BLOCK / max(1, spec.tier_a_every)
        + passes * (spec.tier_b_layers + spec.plan_layers * spec.plan_steps) * (_KERNELS_PER_BLOCK + 2)
        + 20
    )

    return CostModel(
        params_total=int(total),
        params_streamed_per_decision=int(streamed),
        bytes_per_decision=int(streamed * dtype_bytes),
        flops_per_decision=int(flops),
        kernel_launches=int(launches),
    )


def measure_launches(spec: ArchSpec, n_tokens: int, n_actions: int) -> dict:
    """Count real ATen dispatches for one decision, on both the hot and cached paths.

    Op count is device independent, so this is valid to run on the dev box and apply to
    the GB10. Runs on CPU with tiny inputs; it counts operations, it does not time them.

    Returns the cold path (board encoder runs), the cached path (it does not), and the
    cadence-blended figure that a steady-state decision actually pays.
    """
    from torch.utils._python_dispatch import TorchDispatchMode

    class _Counter(TorchDispatchMode):
        def __init__(self):
            self.n = 0

        def __torch_dispatch__(self, func, types, args=(), kwargs=None):
            self.n += 1
            return func(*args, **(kwargs or {}))

    model = LatencyProbe(spec).eval()
    ids = torch.randint(0, spec.vocab_size, (1, n_tokens))
    comp = torch.randn(1, n_tokens, spec.component_dim)
    acts = torch.randn(1, n_actions, spec.action_desc_dim)

    counts = {}
    with torch.inference_mode():
        for label, force in (("cold", True), ("cached", False)):
            model.reset_cache()
            _, _, st = model(ids, comp, acts, None, force_tier_a=True)
            c = _Counter()
            with c:
                model(ids, comp, acts, st, force_tier_a=force)
            counts[label] = c.n

    every = max(1, spec.tier_a_every)
    counts["blended"] = counts["cached"] + (counts["cold"] - counts["cached"]) / every
    del model
    return counts


# GB10 / DGX Spark. Bandwidth is the published figure. Dense bf16 is derived from the
# advertised 1 PFLOP FP4 sparse by the standard Blackwell ratios: /2 for sparse->dense,
# /4 for FP4->BF16. If the machine turns out to do better, the projection is pessimistic
# and every number below improves. See docs/HARDWARE_DGX_SPARK.md.
#
# STREAMING EFFICIENCY. Dividing by the full 273 GB/s assumes a perfect stream, which no
# real workload achieves. The dev box measures 20-50 GB/s against roughly 120 GB/s
# theoretical, i.e. 17-42%. 70% is a generous figure for a graph-captured, well-shaped
# batch-1 forward on a unified-memory part, and it is stated here rather than hidden so
# it can be replaced with a measurement the day the Spark arrives. Without it every
# projection is optimistic by 1/0.70 = 1.43x.
GB10 = dict(
    bandwidth_bytes_s=273e9,
    streaming_efficiency=0.70,
    dense_bf16_flops=125e12,
    compute_efficiency=0.40,          # achieved MFU at batch 1; also generous
    launch_overhead_s=8e-6,
    graph_residual_launches=20,
)


def project_gb10(cm: CostModel, hw: dict = GB10, launches: Optional[float] = None) -> dict:
    """Roofline projection. Returns seconds.

    Bandwidth and compute overlap, so take the max. Kernel dispatch does NOT overlap in
    eager mode on this host, so it adds. Under CUDA graphs the per-kernel dispatch cost
    collapses to a small fixed residual, which is why both are reported and why graphs
    are mandatory rather than optional on a 20-core ARM host.

    Pass `launches` from measure_launches() to remove the last guess from this function.
    """
    eff_bw = hw["bandwidth_bytes_s"] * hw.get("streaming_efficiency", 1.0)
    eff_fl = hw["dense_bf16_flops"] * hw.get("compute_efficiency", 1.0)

    n_launch = cm.kernel_launches if launches is None else launches
    bw = cm.bytes_per_decision / eff_bw
    fl = cm.flops_per_decision / eff_fl
    dispatch = n_launch * hw["launch_overhead_s"]
    roof = max(bw, fl)
    return {
        "bandwidth_s": bw,
        "compute_s": fl,
        "roofline_s": roof,
        "dispatch_s": dispatch,
        "eager_s": roof + dispatch,
        "cuda_graph_s": roof + hw["graph_residual_launches"] * hw["launch_overhead_s"],
        "bound_by": "bandwidth" if bw >= fl else "compute",
        "launches_used": n_launch,
        "launches_measured": launches is not None,
        "effective_bandwidth_gb_s": round(eff_bw / 1e9, 1),
    }
