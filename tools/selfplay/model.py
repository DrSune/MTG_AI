"""The policy/value network: a transformer over one decision's entities and options.

Tokens: one global token (turn, ask kind, ask details), two player tokens (me, opponent), one
token per visible card, one token per option. A card token is its name embedding plus the mean
of its component-token embeddings (the compiled ability tree, features.ir_tokens) plus its live
state. An option token is its type plus the embeddings of the entities it points at. Every token
attends to every other (no causal mask: there is no time axis inside one decision).

Heads: one logit per option token (the pointer policy) and a scalar value in [-1, 1] from the
global token, the expected outcome for the deciding seat.

Name dropout (training only) swaps a card's name embedding for the unknown-card row, so the
network must also read the components; at play time an unseen card uses the unknown row and
its components.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import torch
from torch import nn

from tools.selfplay import features as FT

class PolicyValueNet(nn.Module):
    def __init__(self, n_cards: int, n_ir: int, ir_table: np.ndarray, d: int = 256,
                 layers: int = 6, heads: int = 8, ff: int = 1024, name_dropout: float = 0.1,
                 mask_names: bool = False):
        super().__init__()
        self.config = {"n_cards": n_cards, "n_ir": n_ir, "d": d, "layers": layers,
                       "heads": heads, "ff": ff, "name_dropout": name_dropout}
        self.d = d
        self.name_dropout = name_dropout
        # every card name read as the unknown card (a generalisation probe: the network must
        # play from components and live state alone); not saved in the config
        self.mask_names = mask_names
        self.name_emb = nn.Embedding(n_cards, d)
        self.ir_emb = nn.Embedding(n_ir, d, padding_idx=0)
        self.register_buffer("ir_table", torch.as_tensor(ir_table, dtype=torch.long),
                             persistent=False)
        self.zone_emb = nn.Embedding(len(FT.ZONES), d)
        self.ctrl_emb = nn.Embedding(3, d)
        self.owner_emb = nn.Embedding(3, d)
        self.card_f = nn.Linear(FT.CF, d)
        self.host = nn.Linear(d, d, bias=False)
        self.player_f = nn.Linear(FT.PF, d)
        self.player_role = nn.Embedding(2, d)
        self.glob_f = nn.Linear(FT.GF, d)
        self.ask_emb = nn.Embedding(len(FT.ASK_KINDS), d)
        self.opt_type = nn.Embedding(len(FT.OPTION_TYPES), d)
        self.opt_ab = nn.Embedding(24, d)
        self.opt_f = nn.Linear(2, d)
        self.opt_ref = nn.Linear(d, d, bias=False)
        self.opt_ref2 = nn.Linear(d, d, bias=False)
        self.segment = nn.Embedding(4, d)
        self.in_norm = nn.LayerNorm(d)
        layer = nn.TransformerEncoderLayer(d, heads, ff, dropout=0.0, activation="gelu",
                                           batch_first=True, norm_first=True)
        self.encoder = nn.TransformerEncoder(layer, layers, enable_nested_tensor=False)
        self.out_norm = nn.LayerNorm(d)
        self.policy_head = nn.Sequential(nn.Linear(d, d), nn.GELU(), nn.Linear(d, 1))
        self.value_head = nn.Sequential(nn.Linear(d, d), nn.GELU(), nn.Linear(d, 1))
        self._init()

    def _init(self) -> None:
        for m in self.modules():
            if isinstance(m, nn.Linear):
                nn.init.normal_(m.weight, std=0.02)
                if m.bias is not None:
                    nn.init.zeros_(m.bias)
            elif isinstance(m, nn.Embedding):
                nn.init.normal_(m.weight, std=0.02)
        nn.init.zeros_(self.policy_head[-1].weight)
        nn.init.zeros_(self.value_head[-1].weight)

    def card_table_emb(self) -> torch.Tensor:
        ids = self.ir_table
        emb = self.ir_emb(ids)  # [N, L, d]
        mask = (ids > 0).unsqueeze(-1).to(emb.dtype)
        return (emb * mask).sum(1) / mask.sum(1).clamp(min=1.0)

    def forward(self, b: dict[str, torch.Tensor]) -> tuple[torch.Tensor, torch.Tensor]:
        cards_i, cards_f = b["cards_i"], b["cards_f"]
        bsz, e = cards_i.shape[:2]
        card_idx = cards_i[..., 0]
        name_idx = card_idx
        if self.mask_names:
            name_idx = torch.where(card_idx > FT.UNK, torch.full_like(card_idx, FT.UNK),
                                   card_idx)
        elif self.training and self.name_dropout > 0:
            drop = torch.rand(card_idx.shape, device=card_idx.device) < self.name_dropout
            name_idx = torch.where(drop & (card_idx > FT.UNK), torch.full_like(card_idx, FT.UNK),
                                   card_idx)
        ir = self.card_table_emb()
        x_card = (self.name_emb(name_idx) + ir[card_idx] + self.zone_emb(cards_i[..., 1])
                  + self.ctrl_emb(cards_i[..., 2]) + self.owner_emb(cards_i[..., 3])
                  + self.card_f(cards_f))
        x_play = self.player_f(b["players_f"]) + self.player_role.weight[None]
        ent = torch.cat([x_play, x_card], dim=1)  # [B, 2+E, d]
        zero = ent.new_zeros(bsz, 1, self.d)
        ent_ext = torch.cat([zero, ent], dim=1)
        host = cards_i[..., 4]
        x_card = x_card + self.host(_gather(ent_ext, host))
        ent = torch.cat([x_play, x_card], dim=1)
        ent_ext = torch.cat([zero, ent], dim=1)
        opts_i, opts_f = b["opts_i"], b["opts_f"]
        x_opt = (self.opt_type(opts_i[..., 0]) + self.opt_ab(opts_i[..., 3].clamp(0, 23))
                 + self.opt_f(opts_f) + self.opt_ref(_gather(ent_ext, opts_i[..., 1]))
                 + self.opt_ref2(_gather(ent_ext, opts_i[..., 2])))
        x_glob = (self.glob_f(b["glob_f"]) + self.ask_emb(b["ask_i"][:, 0]))[:, None]
        seg = self.segment.weight
        x = torch.cat([x_glob + seg[0], x_play + seg[1], x_card + seg[2], x_opt + seg[3]], dim=1)
        k = opts_i.shape[1]
        valid = torch.cat([
            torch.ones(bsz, 3, dtype=torch.bool, device=x.device),
            b["card_mask"], b["opt_mask"]], dim=1)
        h = self.encoder(self.in_norm(x), src_key_padding_mask=~valid)
        h = self.out_norm(h)
        logits = self.policy_head(h[:, 3 + e:]).squeeze(-1).float()
        logits = logits.masked_fill(~b["opt_mask"], -1e9)
        value = torch.tanh(self.value_head(h[:, 0]).squeeze(-1).float())
        assert logits.shape == (bsz, k)
        return logits, value


def extend_cards(net: PolicyValueNet, table: FT.CardTable) -> PolicyValueNet:
    """Grow ``net`` to an extended or refreshed table (FT.CardTable.extend/refresh): new name
    rows start as the unknown-card embedding (what name dropout trained), new component rows at
    zero, and the component table is rebuilt."""
    old = net.name_emb.weight.data
    n = len(table.oracle_ids)
    if n > old.shape[0]:
        emb = nn.Embedding(n, old.shape[1]).to(old.device, old.dtype)
        emb.weight.data[: old.shape[0]] = old
        emb.weight.data[old.shape[0]:] = old[FT.UNK]
        net.name_emb = emb
    # new component types (CardTable.refresh, extend(add_tokens=True)) start at zero: a
    # neutral term in the card's component mean until training gives it a meaning
    old_ir = net.ir_emb.weight.data
    n_ir = len(table.ir_vocab)
    if n_ir > old_ir.shape[0]:
        emb = nn.Embedding(n_ir, old_ir.shape[1], padding_idx=0).to(old_ir.device, old_ir.dtype)
        emb.weight.data.zero_()
        emb.weight.data[: old_ir.shape[0]] = old_ir
        net.ir_emb = emb
        net.config["n_ir"] = n_ir
    net.ir_table = torch.as_tensor(table.ir_array(), dtype=torch.long,
                                   device=net.ir_table.device)
    net.config["n_cards"] = n
    return net


def _gather(ent_ext: torch.Tensor, idx: torch.Tensor) -> torch.Tensor:
    """ent_ext [B, N, d], idx [B, M] long -> [B, M, d]."""
    d = ent_ext.shape[-1]
    return torch.gather(ent_ext, 1, idx.clamp(0, ent_ext.shape[1] - 1).unsqueeze(-1)
                        .expand(-1, -1, d))


def collate(obs: list[dict[str, np.ndarray]], device: torch.device | str) -> dict[str, torch.Tensor]:
    """Pad a list of features.encode() dicts into one batch."""
    bsz = len(obs)
    e = max(1, max(o["cards_i"].shape[0] for o in obs))
    k = max(1, max(o["opts_i"].shape[0] for o in obs))
    cards_i = np.zeros((bsz, e, 5), np.int64)
    cards_f = np.zeros((bsz, e, FT.CF), np.float32)
    card_mask = np.zeros((bsz, e), bool)
    opts_i = np.zeros((bsz, k, 4), np.int64)
    opts_f = np.zeros((bsz, k, 2), np.float32)
    opt_mask = np.zeros((bsz, k), bool)
    for i, o in enumerate(obs):
        n = o["cards_i"].shape[0]
        cards_i[i, :n] = o["cards_i"]
        cards_f[i, :n] = o["cards_f"]
        card_mask[i, :n] = True
        m = o["opts_i"].shape[0]
        opts_i[i, :m] = o["opts_i"]
        opts_f[i, :m] = o["opts_f"]
        opt_mask[i, :m] = True
    out = {
        "cards_i": cards_i, "cards_f": cards_f, "card_mask": card_mask,
        "players_f": np.stack([o["players_f"] for o in obs]).astype(np.float32),
        "glob_f": np.stack([o["glob_f"] for o in obs]).astype(np.float32),
        "ask_i": np.stack([o["ask_i"] for o in obs]).astype(np.int64),
        "opts_i": opts_i, "opts_f": opts_f, "opt_mask": opt_mask,
    }
    return {k2: torch.from_numpy(v).to(device, non_blocking=True) for k2, v in out.items()}


class Packed:
    """Many decisions as flat arrays: every sample's card rows (and option rows) back to back,
    with offsets. Cheap to pickle across processes, and ``collate_packed`` pads a minibatch from
    it with a handful of vectorised numpy ops instead of a Python loop over decisions."""

    FIELDS = ("cards_i", "cards_f", "c_off", "opts_i", "opts_f", "o_off", "players_f", "glob_f",
              "ask_i")

    def __init__(self, **arrays: np.ndarray) -> None:
        for k in self.FIELDS:
            setattr(self, k, arrays[k])

    def __len__(self) -> int:
        return len(self.c_off) - 1

    def lengths(self) -> np.ndarray:
        """Per-decision token count (cards + options), the minibatch sort key."""
        return np.diff(self.c_off) + np.diff(self.o_off)

    def __getstate__(self) -> dict:
        return {k: getattr(self, k) for k in self.FIELDS}

    def __setstate__(self, state: dict) -> None:
        for k, v in state.items():
            setattr(self, k, v)


def pack(obs: list[dict[str, np.ndarray]]) -> Packed:
    e = np.array([o["cards_i"].shape[0] for o in obs], dtype=np.int64)
    k = np.array([o["opts_i"].shape[0] for o in obs], dtype=np.int64)
    return Packed(
        cards_i=np.concatenate([o["cards_i"] for o in obs]).astype(np.int16),
        cards_f=np.concatenate([o["cards_f"] for o in obs]).astype(np.float16),
        c_off=np.concatenate([[0], np.cumsum(e)]),
        opts_i=np.concatenate([o["opts_i"] for o in obs]).astype(np.int16),
        opts_f=np.concatenate([o["opts_f"] for o in obs]).astype(np.float16),
        o_off=np.concatenate([[0], np.cumsum(k)]),
        players_f=np.stack([o["players_f"] for o in obs]).astype(np.float16),
        glob_f=np.stack([o["glob_f"] for o in obs]).astype(np.float16),
        ask_i=np.stack([o["ask_i"] for o in obs]).astype(np.int16),
    )


def _rows(off: np.ndarray, idx: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    start = off[idx]
    n = off[idx + 1] - start
    width = max(1, int(n.max()) if len(n) else 1)
    ar = np.arange(width)
    mask = ar[None, :] < n[:, None]
    rows = np.where(mask, start[:, None] + ar[None, :], 0)
    return rows, mask


def collate_packed(p: Packed, idx: np.ndarray, device: torch.device | str) -> dict[str, torch.Tensor]:
    """The same batch ``collate`` builds, for the decisions ``idx`` of ``p``."""
    idx = np.asarray(idx, dtype=np.int64)
    c_rows, c_mask = _rows(p.c_off, idx)
    o_rows, o_mask = _rows(p.o_off, idx)
    out = {
        "cards_i": p.cards_i[c_rows].astype(np.int64) * c_mask[..., None],
        "cards_f": p.cards_f[c_rows].astype(np.float32) * c_mask[..., None],
        "card_mask": c_mask,
        "players_f": p.players_f[idx].astype(np.float32),
        "glob_f": p.glob_f[idx].astype(np.float32),
        "ask_i": p.ask_i[idx].astype(np.int64),
        "opts_i": p.opts_i[o_rows].astype(np.int64) * o_mask[..., None],
        "opts_f": p.opts_f[o_rows].astype(np.float32) * o_mask[..., None],
        "opt_mask": o_mask,
    }
    return {k: torch.from_numpy(np.ascontiguousarray(v)).to(device, non_blocking=True)
            for k, v in out.items()}


class LocalSlot:
    """In-process stand-in for an actor slot: answers inference requests in the worker protocol
    (actor.py) synchronously and greedily, each spec's network on its own device and dtype."""

    def __init__(self, nets: dict[str, nn.Module]) -> None:
        self.nets = nets

    @torch.no_grad()
    def infer(self, req: tuple) -> Any:
        spec, feats = req[2], req[5]
        want = req[6] if len(req) > 6 else 0
        net = self.nets[spec]
        p = next(net.parameters())
        b = {k: (v.to(p.dtype) if v.is_floating_point() else v)
             for k, v in collate([feats], p.device).items()}
        logits, value = net(b)
        probs = torch.softmax(logits[0, : feats["opts_i"].shape[0]].float(), -1)
        a, v = int(probs.argmax()), float(value.float()[0])
        return a if want == 0 else (a, v) if want == 1 else (a, v, probs.tolist())


def build(table: FT.CardTable, **kw: Any) -> PolicyValueNet:
    return PolicyValueNet(len(table.oracle_ids), len(table.ir_vocab), table.ir_array(), **kw)


def save(path: str, model: PolicyValueNet, table: FT.CardTable, extra: dict | None = None) -> None:
    torch.save({"config": model.config, "state": model.state_dict(), "table": table.to_json(),
                "extra": extra or {}}, path)


def load(path: str, device: torch.device | str = "cpu") -> tuple[PolicyValueNet, FT.CardTable, dict]:
    ck = torch.load(path, map_location="cpu", weights_only=False)
    table = FT.CardTable.from_json(ck["table"])
    cfg = dict(ck["config"])
    n_cards, n_ir = cfg.pop("n_cards"), cfg.pop("n_ir")
    model = PolicyValueNet(n_cards, n_ir, table.ir_array(), **cfg)
    state = ck["state"]
    # ask kinds and option types appended since this checkpoint start as what they were encoded
    # as before: the ASK_GROWN_FROM kind or "other"
    for key, names, index, grown_from in (
            ("ask_emb.weight", FT.ASK_KINDS, FT.ASK_INDEX, FT.ASK_GROWN_FROM),
            ("opt_type.weight", FT.OPTION_TYPES, FT.OPT_INDEX, {})):
        w = state[key]
        grown = [w[index[grown_from.get(k, "other")]] for k in names[w.shape[0]:]]
        if grown:
            state[key] = torch.cat([w, torch.stack(grown)])
    # feature columns appended since this checkpoint (features.F_TARGETED, P_TARGETED, G_SLOT)
    # get zero weights: the old network reads them as absent and computes what it computed before
    for key, width in (("card_f.weight", FT.CF), ("player_f.weight", FT.PF),
                       ("glob_f.weight", FT.GF)):
        w = state[key]
        if w.shape[1] < width:
            state[key] = torch.cat([w, w.new_zeros(w.shape[0], width - w.shape[1])], dim=1)
    model.load_state_dict(state)
    return model.to(device), table, ck.get("extra", {})
