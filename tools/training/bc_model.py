"""S1 pointer decision-stream transformer (design doc 09 §6, ruling 1).

d=512, L=8, 8 heads, causal (prefix-LM style: every step attends the full
past stream), F.scaled_dot_product_attention via TransformerEncoderLayer,
STEP-LEVEL GRADIENT CHECKPOINTING per block (DESIGN_TRAINING §3(c) — the
full-episode BPTT arm; dropout is 0.0, which also satisfies the
recompute-RNG-preservation law trivially).

Pointer law (§1): the action score is ``v·tanh(W_q h + W_k cand) +
b_pass·is_pass`` over the CANONICAL candidate list — never a vocab softmax.
Candidate spans carry NO positional embedding, so scores are permutation
-equivariant over candidates (shuffle-invariance unit-tested; rank-sorted
vocab must never leak position-identity).

fp32 master weights; mixed precision = autocast(bf16) around forward only.
"""

from __future__ import annotations

import torch
import torch.nn.functional as F
from torch import nn
from torch.utils import checkpoint as ckpt


class PointerBC(nn.Module):
    """Causal decision-stream encoder + pointer candidate scorer."""

    def __init__(
        self,
        vocab_size: int,
        d: int = 512,
        layers: int = 8,
        heads: int = 8,
        ff: int = 3072,
        max_len: int = 1024,
        grad_checkpoint: bool = True,
    ) -> None:
        super().__init__()
        self.d = d
        self.max_len = max_len
        self.grad_checkpoint = grad_checkpoint
        self.tok_emb = nn.Embedding(vocab_size, d)
        self.pos_emb = nn.Embedding(max_len, d)

        def _make_block() -> nn.TransformerEncoderLayer:
            # A FRESH layer per block: nn.ModuleList(block for _ in range(L))
            # would hand the same instance L times and silently weight-tie
            # the stack (measured: 5.5M params instead of ~35M).
            return nn.TransformerEncoderLayer(
                d_model=d,
                nhead=heads,
                dim_feedforward=ff,
                activation="gelu",
                batch_first=True,
                norm_first=True,
                dropout=0.0,
            )

        self.blocks = nn.ModuleList(_make_block() for _ in range(layers))
        self.ln_f = nn.LayerNorm(d)
        self.w_cand = nn.Linear(d, d)  # candidate projection (content-only)
        self.w_q = nn.Linear(d, d)  # query from the step summary state
        self.w_key = nn.Linear(d, d)  # key from the candidate
        self.v = nn.Linear(d, 1)  # additive pointer score
        self.b_pass = nn.Parameter(torch.zeros(1))  # PASS prior (bias only)
        self._init_weights()

    def _init_weights(self) -> None:
        for m in self.modules():
            if isinstance(m, nn.Linear):
                nn.init.normal_(m.weight, std=0.02)
                if m.bias is not None:
                    nn.init.zeros_(m.bias)
            elif isinstance(m, nn.Embedding):
                nn.init.normal_(m.weight, std=0.02)

    # ------------------------------------------------------------------ encode
    def encode(self, tokens: torch.Tensor, pad_mask: torch.Tensor) -> torch.Tensor:
        """tokens [B,T] long, pad_mask [B,T] bool (True = padding slot)."""
        t = tokens.shape[1]
        if t > self.max_len:
            raise ValueError(f"episode stream {t} > max_len {self.max_len}")
        pos = torch.arange(t, device=tokens.device)
        x = self.tok_emb(tokens) + self.pos_emb(pos)[None]
        for block in self.blocks:
            if self.grad_checkpoint and self.training and torch.is_grad_enabled():
                x = ckpt.checkpoint(
                    block,
                    x,
                    src_key_padding_mask=pad_mask,
                    use_reentrant=False,
                )
            else:
                x = block(x, src_key_padding_mask=pad_mask)
        return self.ln_f(x)

    # ------------------------------------------------------------- candidate
    def candidate_emb(
        self, cand_ids: torch.Tensor, cand_mask: torch.Tensor
    ) -> torch.Tensor:
        """[G,Cmax,Lmax] token ids + [G,Cmax,Lmax] valid-mask -> [G,Cmax,d].

        Mean-pool over the candidate's tokens — content only, no position."""
        emb = self.tok_emb(cand_ids) * cand_mask.unsqueeze(-1)
        denom = cand_mask.sum(-1, keepdim=True).clamp(min=1)
        return self.w_cand(emb.sum(-2) / denom)

    def pointer_logits(
        self,
        h: torch.Tensor,
        cand_emb: torch.Tensor,
        cand_valid: torch.Tensor,
        is_pass: torch.Tensor,
    ) -> torch.Tensor:
        """h [G,d] step states, cand_emb [G,Cmax,d], cand_valid/is_pass
        [G,Cmax] bool -> scores [G,Cmax] (-inf on invalid slots)."""
        s = self.v(torch.tanh(self.w_q(h)[:, None, :] + self.w_key(cand_emb)))
        s = s.squeeze(-1) + self.b_pass * is_pass.to(s.dtype)
        return s.masked_fill(~cand_valid, torch.finfo(s.dtype).min)

    # ------------------------------------------------------------------ full
    def forward(
        self,
        tokens: torch.Tensor,
        pad_mask: torch.Tensor,
        gold_batch: torch.Tensor,
        gold_pos: torch.Tensor,
        cand_ids: torch.Tensor,
        cand_mask: torch.Tensor,
        is_pass: torch.Tensor,
    ) -> torch.Tensor:
        """Returns pointer logits [G,Cmax] for every gold row of the batch."""
        hidden = self.encode(tokens, pad_mask)
        h = hidden[gold_batch, gold_pos]
        cand_emb = self.candidate_emb(cand_ids, cand_mask)
        return self.pointer_logits(h, cand_emb, cand_mask.any(-1), is_pass)

    def loss(
        self,
        tokens: torch.Tensor,
        pad_mask: torch.Tensor,
        gold_batch: torch.Tensor,
        gold_pos: torch.Tensor,
        cand_ids: torch.Tensor,
        cand_mask: torch.Tensor,
        is_pass: torch.Tensor,
        gold_idx: torch.Tensor,
    ) -> torch.Tensor:
        logits = self.forward(
            tokens, pad_mask, gold_batch, gold_pos, cand_ids, cand_mask, is_pass
        )
        return F.cross_entropy(logits.float(), gold_idx)


def collate(episodes: list[dict], vocab_size: int, device: torch.device) -> dict:
    """Pad a list of bc_data.encode_episode records into batch tensors.

    Token 0 is <pad>; candidate token slot 0 likewise. Pure function of its
    inputs (eval determinism)."""
    b = len(episodes)
    t_max = max(len(ep["seq"]) for ep in episodes)
    tokens = torch.zeros(b, t_max, dtype=torch.long)
    pad_mask = torch.ones(b, t_max, dtype=torch.bool)
    for i, ep in enumerate(episodes):
        ids = torch.tensor(ep["seq"], dtype=torch.long)
        tokens[i, : len(ids)] = ids
        pad_mask[i, : len(ids)] = False

    rows = [(i, g) for i, ep in enumerate(episodes) for g in ep["gold"]]
    g_max = max(len(r[1]["cand_ids"]) for r in rows) if rows else 1
    l_max = max(
        (len(ids) for r in rows for ids in r[1]["cand_ids"]),
        default=1,
    )
    gold_batch = torch.tensor([i for i, _ in rows], dtype=torch.long)
    gold_pos = torch.tensor([g["pos"] for _, g in rows], dtype=torch.long)
    gold_idx = torch.tensor([g["gold_idx"] for _, g in rows], dtype=torch.long)
    cand_ids = torch.zeros(len(rows), g_max, l_max, dtype=torch.long)
    cand_mask = torch.zeros(len(rows), g_max, l_max, dtype=torch.bool)
    is_pass = torch.zeros(len(rows), g_max, dtype=torch.bool)
    for gi, (_bi, g) in enumerate(rows):
        for ci, ids in enumerate(g["cand_ids"]):
            t = torch.tensor(ids, dtype=torch.long)
            cand_ids[gi, ci, : len(t)] = t
            cand_mask[gi, ci, : len(t)] = True
        is_pass[gi, : len(g["is_pass"])] = torch.tensor(g["is_pass"], dtype=torch.bool)

    out = {
        "tokens": tokens.to(device),
        "pad_mask": pad_mask.to(device),
        "gold_batch": gold_batch.to(device),
        "gold_pos": gold_pos.to(device),
        "gold_idx": gold_idx.to(device),
        "cand_ids": cand_ids.to(device),
        "cand_mask": cand_mask.to(device),
        "is_pass": is_pass.to(device),
        "n_rows": len(rows),
    }
    assert tokens.le(vocab_size - 1).all(), "token id outside vocab"
    return out
