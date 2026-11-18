"""The policy/value network: a transformer over one decision's entities and options.

Tokens: one global token (turn, ask kind, ask details), two player tokens (me, opponent), one
token per visible card, one token per option. A card token is its name embedding plus the mean
of its component-token embeddings (the compiled ability tree, features.ir_tokens) plus its live
state. An option token is its type plus the embeddings of the entities it points at. Every token
attends to every other (no causal mask: there is no time axis inside one decision).

Heads: one logit per option token (the pointer policy) and a scalar value in [-1, 1] from the
global token, the expected outcome for the deciding seat. A planner network (``planner``,
docs/DESIGN_PLANNER.md v1, planner.py) also reads each card's read-back columns and forecasts,
on each card token, the card's next use (``forward(b, plan=True)``).

Name dropout (training only) swaps a card's name embedding for the unknown-card row, so the
network must also read the components; at play time an unseen card uses the unknown row and
its components.

Everything that decides what a network computes lives in its ``config`` and its state (weights
and buffers), so a copy, a checkpoint and the trainer's rebuild all compute the same function:
``mask_names`` too. A checkpoint is written whole or not at all (``save``), and ``load`` returns
the network in eval mode (training code switches to train mode itself).
"""

from __future__ import annotations

import math
import os
from collections.abc import Callable
from typing import Any

import numpy as np
import torch
from torch import nn

from tools.selfplay import features as FT
from tools.selfplay import planner as PL


class PolicyValueNet(nn.Module):
    def __init__(self, n_cards: int, n_ir: int, ir_counts: np.ndarray, d: int = 256,
                 layers: int = 6, heads: int = 8, ff: int = 1024, name_dropout: float = 0.1,
                 mask_names: bool = False, planner: bool = False):
        super().__init__()
        # mask_names: every card name read as the unknown card (a generalisation probe: the
        # network must play from components and live state alone)
        self.config = {"n_cards": n_cards, "n_ir": n_ir, "d": d, "layers": layers,
                       "heads": heads, "ff": ff, "name_dropout": name_dropout,
                       "mask_names": bool(mask_names)}
        if planner:  # in the config only when on: a network without it is saved as before
            self.config["planner"] = True
        self.d = d
        self.name_dropout = name_dropout
        self.name_emb = nn.Embedding(n_cards, d)
        self.ir_emb = nn.Embedding(n_ir, d, padding_idx=0)
        # the card table's rows as token counts (FT.CardTable.ir_counts), rebuilt from the
        # table on every load, so a checkpoint holds the table, not this
        self.register_buffer("ir_counts", torch.as_tensor(ir_counts), persistent=False)
        self.zone_emb = nn.Embedding(len(FT.ZONES), d)
        self.ctrl_emb = nn.Embedding(3, d)
        self.owner_emb = nn.Embedding(3, d)
        self.card_f = nn.Linear(FT.CF, d)
        self.host = nn.Linear(d, d, bias=False)
        # a stack object's pointers: an ability to its source, the object to its first target
        self.source_ptr = nn.Linear(d, d, bias=False)
        self.target_ptr = nn.Linear(d, d, bias=False)
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
        # a named card (features.O_NAMED, C_NAMED), read as a card token reads its identity.
        # Registered last; its construction draw, before _init, moved the seeded weights of every
        # older layer (the planner's layers are built after _init, so they move none)
        self.named_ptr = nn.Linear(d, d, bias=False)
        self._init()
        if planner:
            self._add_planner()

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

    def _add_planner(self) -> None:
        """The planner's layers (planner.py), built after ``_init``, so a seeded build draws every
        older layer's weights as a build without them does: the read-back's embeddings (when, verb
        and window; id 0, none, a zero term) and its target pointer; the forecast heads on each
        card token (when, verb and window logits and the target's "none" logit; the target's
        pointer to the entities), at zero: they start forecasting uniformly, as the policy's last
        layer starts.

        Why linear heads: an older network made a planner gets every planner layer at zero
        (``upgraded``), and a zero linear layer still learns (its gradient is the hidden state
        times the error), where a zero two-layer head would never move (each layer's gradient
        passes through the other's zeros). Why a bilinear pointer for the target: the policy's
        options point at entities the same way, so the target needs no card vocabulary and fits
        any number of entities."""
        d = self.d
        self.plan_when = nn.Embedding(len(PL.WHEN) + 1, d)
        self.plan_verb = nn.Embedding(len(PL.VERBS) + 1, d)
        self.plan_window = nn.Embedding(len(PL.WINDOWS) + 1, d)
        self.plan_target = nn.Linear(d, d, bias=False)
        self.plan_head = nn.Linear(d, len(PL.WHEN) + len(PL.VERBS) + len(PL.WINDOWS) + 1)
        self.plan_ptr = nn.Linear(d, d, bias=False)
        for w in (self.plan_when.weight, self.plan_verb.weight, self.plan_window.weight,
                  self.plan_target.weight):
            nn.init.normal_(w, std=0.02)
        for w in (self.plan_head.weight, self.plan_head.bias, self.plan_ptr.weight):
            nn.init.zeros_(w)

    @property
    def mask_names(self) -> bool:
        return self.config["mask_names"]

    @mask_names.setter
    def mask_names(self, on: bool) -> None:
        self.config["mask_names"] = bool(on)

    @property
    def planner(self) -> bool:
        return bool(self.config.get("planner"))

    def card_table_emb(self) -> torch.Tensor:
        """Every table row's component vector: the mean of the embeddings of all its component
        tokens, as counts times the embedding table ([N, vocab] @ [vocab, d]; KNOWLEDGE 210, N1:
        nothing is cut, and no [N, tokens, d] gather). In fp32 under autocast too, as the
        gather was, then in the weights' dtype."""
        w = self.ir_emb.weight
        with torch.autocast(w.device.type, enabled=False):
            c = self.ir_counts.float()
            return ((c @ w.float()) / c.sum(1, keepdim=True).clamp(min=1.0)).to(w.dtype)

    def value_emb(self, ids: torch.Tensor) -> torch.Tensor:
        """A chosen value's component token, id 0 (none) a zero vector. Masked, as
        ``card_table_emb`` never counts the padding token: ``_init`` and every checkpoint give
        the padding row random values, so a term that read it would move every token of an
        older network."""
        return self.ir_emb(ids) * (ids > 0).unsqueeze(-1).to(self.ir_emb.weight.dtype)

    def _names(self, idx: torch.Tensor, dropout: bool = True) -> torch.Tensor:
        """The name rows card rows ``idx`` read: the unknown card's under ``mask_names``, and,
        with ``dropout``, at the name-dropout rate in training."""
        if self.mask_names:
            return torch.where(idx > FT.UNK, torch.full_like(idx, FT.UNK), idx)
        if dropout and self.training and self.name_dropout > 0:
            drop = torch.rand(idx.shape, device=idx.device) < self.name_dropout
            return torch.where(drop & (idx > FT.UNK), torch.full_like(idx, FT.UNK), idx)
        return idx

    def _named(self, idx: torch.Tensor, ir: torch.Tensor) -> torch.Tensor:
        """The card a chosen or offered card name names (features.C_NAMED, O_NAMED), read as a
        card token reads its identity; row 0, none, a zero term. The name is the choice (Runed
        Halo's protection is from that name, not from what the card does), so it never drops."""
        x = self.name_emb(self._names(idx, dropout=False)) + ir[idx]
        return self.named_ptr(x * (idx > 0).unsqueeze(-1).to(x.dtype))

    def _readback(self, cards_i: torch.Tensor) -> torch.Tensor:
        """The planner's read-back of when, verb and window (features.C_PLAN_WHEN .. _WINDOW):
        each column's embedding, 0 (none) a zero term as in ``value_emb``."""
        out = 0
        for emb, col in ((self.plan_when, FT.C_PLAN_WHEN), (self.plan_verb, FT.C_PLAN_VERB),
                         (self.plan_window, FT.C_PLAN_WINDOW)):
            ids = cards_i[..., col]
            out = out + emb(ids) * (ids > 0).unsqueeze(-1).to(emb.weight.dtype)
        return out

    def tokens(self, b: dict[str, torch.Tensor]) -> tuple[torch.Tensor, torch.Tensor]:
        """The input tokens [global, me, opponent, cards..., options...] and which are real (the
        opponent simulator reads the same view through them: simulator.py)."""
        cards_i, cards_f = b["cards_i"], b["cards_f"]
        bsz = cards_i.shape[0]
        card_idx = cards_i[..., 0]
        ir = self.card_table_emb()
        x_card = (self.name_emb(self._names(card_idx)) + ir[card_idx]
                  + self.zone_emb(cards_i[..., 1])
                  + self.ctrl_emb(cards_i[..., 2]) + self.owner_emb(cards_i[..., 3])
                  + self.card_f(cards_f)
                  # a permanent's chosen colour or creature type by its component token (0 for
                  # none, a zero term: an older network computes what it computed before), and
                  # the card name it chose
                  + self.value_emb(cards_i[..., FT.C_CHOSEN])
                  + self._named(cards_i[..., FT.C_NAMED], ir))
        # a planner network's read-back, each term after the sums it joins: one from a network
        # without the planner, its layers at zero (``upgraded``), computes what that one did
        if self.planner:
            x_card = x_card + self._readback(cards_i)
        x_play = self.player_f(b["players_f"]) + self.player_role.weight[None]
        ent = torch.cat([x_play, x_card], dim=1)  # [B, 2+E, d]
        zero = ent.new_zeros(bsz, 1, self.d)
        ent_ext = torch.cat([zero, ent], dim=1)
        x_card = (x_card + self.host(_gather(ent_ext, cards_i[..., FT.C_HOST]))
                  + self.source_ptr(_gather(ent_ext, cards_i[..., FT.C_SOURCE]))
                  + self.target_ptr(_gather(ent_ext, cards_i[..., FT.C_TARGET])))
        if self.planner:
            x_card = x_card + self.plan_target(_gather(ent_ext, cards_i[..., FT.C_PLAN_TARGET]))
        ent = torch.cat([x_play, x_card], dim=1)
        ent_ext = torch.cat([zero, ent], dim=1)
        opts_i, opts_f = b["opts_i"], b["opts_f"]
        x_opt = (self.opt_type(opts_i[..., 0]) + self.opt_ab(opts_i[..., 3].clamp(0, 23))
                 + self.opt_f(opts_f) + self.opt_ref(_gather(ent_ext, opts_i[..., 1]))
                 + self.opt_ref2(_gather(ent_ext, opts_i[..., 2]))
                 + self.value_emb(opts_i[..., FT.O_VALUE])  # a quality ask's value, as above
                 + self._named(opts_i[..., FT.O_NAMED], ir))  # a name option's card
        x_glob = (self.glob_f(b["glob_f"]) + self.ask_emb(b["ask_i"][:, 0]))[:, None]
        seg = self.segment.weight
        x = torch.cat([x_glob + seg[0], x_play + seg[1], x_card + seg[2], x_opt + seg[3]], dim=1)
        valid = torch.cat([
            torch.ones(bsz, 3, dtype=torch.bool, device=x.device),
            b["card_mask"], b["opt_mask"]], dim=1)
        return x, valid

    def forward(self, b: dict[str, torch.Tensor], plan: bool = False) -> tuple[torch.Tensor, ...]:
        """The option logits and the value; with ``plan`` (a planner network), also the forecast
        heads (``forecast``)."""
        x, valid = self.tokens(b)
        bsz, e = b["cards_i"].shape[:2]
        k = b["opts_i"].shape[1]
        h = self.encoder(self.in_norm(x), src_key_padding_mask=~valid)
        h = self.out_norm(h)
        logits = self.policy_head(h[:, 3 + e:]).squeeze(-1).float()
        logits = logits.masked_fill(~b["opt_mask"], -1e9)
        value = torch.tanh(self.value_head(h[:, 0]).squeeze(-1).float())
        assert logits.shape == (bsz, k)
        if plan:
            return logits, value, self.forecast(h, b["card_mask"])
        return logits, value

    def forecast(self, h: torch.Tensor, card_mask: torch.Tensor) -> tuple[torch.Tensor, ...]:
        """The planner's heads (planner.HEADS) on the card tokens of the final hidden states
        ``h``: when [B, E, |WHEN|], verb [B, E, |VERBS|], window [B, E, |WINDOWS|] and target
        [B, E, 3 + E]: "none", then a pointer to each entity (me, the opponent, the cards; a
        padded card -1e9), as features.C_PLAN_TARGET counts them."""
        if not self.planner:
            raise ValueError("a forecast needs a planner network (model.load(..., planner=True))")
        bsz, e = card_mask.shape
        cards = h[:, 3:3 + e]
        out = self.plan_head(cards).float()
        when, verb, win, none = out.split([len(PL.WHEN), len(PL.VERBS), len(PL.WINDOWS), 1], -1)
        ptr = torch.einsum("bed,bjd->bej", self.plan_ptr(cards), h[:, 1:3 + e]).float()
        valid = torch.cat([card_mask.new_ones(bsz, 2), card_mask], 1)
        ptr = (ptr / math.sqrt(self.d)).masked_fill(~valid[:, None, :], -1e9)
        return when, verb, win, torch.cat([none, ptr], -1)


def extend_cards(net: PolicyValueNet, table: FT.CardTable) -> PolicyValueNet:
    """Grow ``net`` to an extended or refreshed table (FT.CardTable.extend/refresh): new name
    rows start as the unknown-card embedding (what name dropout trained), new component rows at
    zero, and the rows' token counts are rebuilt."""
    old = net.name_emb.weight.data
    n = len(table.oracle_ids)
    if n > old.shape[0]:
        emb = nn.Embedding(n, old.shape[1]).to(old.device, old.dtype)
        emb.weight.data[: old.shape[0]] = old
        emb.weight.data[old.shape[0]:] = old[FT.UNK]
        net.name_emb = emb
    # new component types (CardTable.refresh, extend(add_tokens=True)) start at zero. That is no
    # neutral term: a card's component vector is the mean over all its tokens, so a row holding
    # k new tokens of n is scaled by (n - k) / n until training moves them (a refresh of r28's
    # v2: 46 rows 1.5-4.5% shorter). Leaving them out of the count until trained would need a
    # per-token state saved with the network and a moment they start to count, which changes the
    # function again; the scale happens once, at an explicit, logged refresh or extension (the
    # bug hunt of 2026-11-17)
    old_ir = net.ir_emb.weight.data
    n_ir = len(table.ir_vocab)
    if n_ir > old_ir.shape[0]:
        emb = nn.Embedding(n_ir, old_ir.shape[1], padding_idx=0).to(old_ir.device, old_ir.dtype)
        emb.weight.data.zero_()
        emb.weight.data[: old_ir.shape[0]] = old_ir
        net.ir_emb = emb
        net.config["n_ir"] = n_ir
    net.ir_counts = torch.as_tensor(table.ir_counts(), device=net.ir_counts.device)
    net.config["n_cards"] = n
    return net


def _gather(ent_ext: torch.Tensor, idx: torch.Tensor) -> torch.Tensor:
    """ent_ext [B, N, d], idx [B, M] long -> [B, M, d]."""
    d = ent_ext.shape[-1]
    return torch.gather(ent_ext, 1, idx.clamp(0, ent_ext.shape[1] - 1).unsqueeze(-1)
                        .expand(-1, -1, d))


def widened(a: np.ndarray, width: int) -> np.ndarray:
    """``a`` with zero columns appended up to ``width``. Columns are only ever appended
    (C_CHOSEN, O_VALUE on 2026-11-13; the planner's read-back, C_PLAN_WHEN .. C_PLAN_TARGET, on
    2026-11-18), and 0 is none, so an encoding recorded before one existed (a ceiling window's
    --search-record shards, a simulator's views) reads exactly."""
    if a.shape[-1] > width:
        raise ValueError(f"an encoding {a.shape[-1]} columns wide, wider than this code's {width}")
    if a.shape[-1] == width:
        return a
    return np.concatenate([a, np.zeros((*a.shape[:-1], width - a.shape[-1]), a.dtype)], axis=-1)


def collate(obs: list[dict[str, np.ndarray]], device: torch.device | str) -> dict[str, torch.Tensor]:
    """Pad a list of features.encode() dicts into one batch."""
    bsz = len(obs)
    e = max(1, max(o["cards_i"].shape[0] for o in obs))
    k = max(1, max(o["opts_i"].shape[0] for o in obs))
    cards_i = np.zeros((bsz, e, FT.CI), np.int64)
    cards_f = np.zeros((bsz, e, FT.CF), np.float32)
    card_mask = np.zeros((bsz, e), bool)
    opts_i = np.zeros((bsz, k, FT.OI), np.int64)
    opts_f = np.zeros((bsz, k, 2), np.float32)
    opt_mask = np.zeros((bsz, k), bool)
    for i, o in enumerate(obs):
        n = o["cards_i"].shape[0]
        cards_i[i, :n] = widened(o["cards_i"], FT.CI)
        cards_f[i, :n] = o["cards_f"]
        card_mask[i, :n] = True
        m = o["opts_i"].shape[0]
        opts_i[i, :m] = widened(o["opts_i"], FT.OI)
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
    #: a planner run's rows also hold (planner.attach): per card row the hindsight labels and the
    #: read-back plan-following trains on, per decision whether it has one; None otherwise
    PLAN = ("plan_y", "plan_x", "plan_m")

    def __init__(self, **arrays: np.ndarray) -> None:
        for k in self.FIELDS:
            setattr(self, k, arrays[k])
        for k in self.PLAN:
            setattr(self, k, arrays.get(k))

    def __len__(self) -> int:
        return len(self.c_off) - 1

    def lengths(self) -> np.ndarray:
        """Per-decision token count (cards + options), the minibatch sort key."""
        return np.diff(self.c_off) + np.diff(self.o_off)

    def __getstate__(self) -> dict:
        return {k: getattr(self, k) for k in self.FIELDS + self.PLAN}

    def __setstate__(self, state: dict) -> None:
        for k in self.PLAN:
            setattr(self, k, None)
        for k, v in state.items():
            setattr(self, k, v)


def pack(obs: list[dict[str, np.ndarray]]) -> Packed:
    e = np.array([o["cards_i"].shape[0] for o in obs], dtype=np.int64)
    k = np.array([o["opts_i"].shape[0] for o in obs], dtype=np.int64)
    plan = {}
    if "plan_y" in obs[0]:
        plan = {"plan_y": np.concatenate([o["plan_y"] for o in obs]).astype(np.int16),
                "plan_x": np.concatenate([o["plan_x"] for o in obs]).astype(np.int16),
                "plan_m": np.concatenate([o["plan_m"] for o in obs]).astype(np.int8)}
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
        **plan,
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
        "cards_i": widened(p.cards_i[c_rows].astype(np.int64), FT.CI) * c_mask[..., None],
        "cards_f": p.cards_f[c_rows].astype(np.float32) * c_mask[..., None],
        "card_mask": c_mask,
        "players_f": p.players_f[idx].astype(np.float32),
        "glob_f": p.glob_f[idx].astype(np.float32),
        "ask_i": p.ask_i[idx].astype(np.int64),
        "opts_i": widened(p.opts_i[o_rows].astype(np.int64), FT.OI) * o_mask[..., None],
        "opts_f": p.opts_f[o_rows].astype(np.float32) * o_mask[..., None],
        "opt_mask": o_mask,
    }
    if p.plan_y is not None:  # a padded card row has no label (-1) and no read-back
        out["plan_y"] = np.where(c_mask[..., None], p.plan_y[c_rows], -1).astype(np.int64)
        out["plan_x"] = p.plan_x[c_rows].astype(np.int64) * c_mask[..., None]
        out["plan_m"] = p.plan_m[idx].astype(bool)
    return {k: torch.from_numpy(np.ascontiguousarray(v)).to(device, non_blocking=True)
            for k, v in out.items()}


class LocalSlot:
    """In-process stand-in for an actor slot: answers inference requests in the worker protocol
    (actor.py) synchronously and greedily, each spec's network on its own device and dtype."""

    def __init__(self, nets: dict[str, nn.Module], sim: tuple | None = None) -> None:
        self.nets = nets
        self.sim = sim  # (simulator, its card table): answers the "sim" requests of a search

    @torch.no_grad()
    def infer(self, req: tuple) -> Any:
        spec, feats = req[2], req[5]
        want = req[6] if len(req) > 6 else 0
        if want == 3:  # the simulator's hidden states for a search's worlds (req[7] of them)
            from tools.selfplay import simulator as S

            if self.sim is None:
                raise ValueError("a 'sim' request needs LocalSlot(..., sim=(simulator, table))")
            sim, table = self.sim
            return S.sample_for_views(sim, table, [feats], [req[8]], [req[7]],
                                      next(sim.parameters()).device)[0]
        net = self.nets[spec]
        p = next(net.parameters())
        b = {k: (v.to(p.dtype) if v.is_floating_point() else v)
             for k, v in collate([feats], p.device).items()}
        out = net(b, plan=want == 4)
        probs = torch.softmax(out[0][0, : feats["opts_i"].shape[0]].float(), -1)
        a, v = int(probs.argmax()), float(out[1].float()[0])
        if want == 4:  # a planning seat's decision: the action and its forecast (actor.NetAgent)
            return a, forecasts(out[2])[0, : feats["cards_i"].shape[0]]
        return a if want == 0 else (a, v) if want == 1 else (a, v, probs.tolist())


def forecasts(heads: tuple[torch.Tensor, ...]) -> np.ndarray:
    """The forecast heads' best classes, [B, E, 4] (when, verb, window, target), as the read-back
    keeps them (planner.plan_of): a forecast is the network's best, never sampled
    (DESIGN_PLANNER §3.3)."""
    return torch.stack([h.argmax(-1) for h in heads], -1).to(torch.int16).cpu().numpy()


def build(table: FT.CardTable, **kw: Any) -> PolicyValueNet:
    return PolicyValueNet(len(table.oracle_ids), len(table.ir_vocab), table.ir_counts(), **kw)


def grow(model: PolicyValueNet, table: FT.CardTable, layers: int | None = None,
         ff: int | None = None, seed: int = 0) -> PolicyValueNet:
    """The same function in a bigger network (PLAN_CEILING §4.1). The encoder's layers are
    pre-norm, so a layer whose attention and feed-forward outputs (weights and biases) are zero
    adds nothing to the residual stream:
    - ``layers`` (a multiple of the current count) follows each layer with new ones like that,
      each with its own random inner weights (cloned layers would start identical);
    - ``ff`` widens every feed-forward layer; the new units' outgoing weights are zero."""
    cfg = {k: v for k, v in model.config.items() if k not in ("n_cards", "n_ir")}
    old_layers, old_ff = cfg["layers"], cfg["ff"]
    layers, ff = layers or old_layers, ff or old_ff
    if layers % old_layers or ff < old_ff:
        raise ValueError(f"grow: {old_layers} layers to {layers}, ff {old_ff} to {ff}")
    torch.manual_seed(seed)
    big = build(table, **{**cfg, "layers": layers, "ff": ff})
    state = model.state_dict()
    new = big.state_dict()
    step = layers // old_layers
    for key, value in new.items():
        if not key.startswith("encoder.layers."):
            new[key] = state[key].clone()
            continue
        i, rest = key[len("encoder.layers."):].split(".", 1)
        i = int(i)
        if i % step:  # a new layer: zero its outputs, keep its fresh inner weights
            if rest.startswith(("self_attn.out_proj.", "linear2.")):
                new[key] = torch.zeros_like(value)
            elif rest == "self_attn.in_proj_weight":
                nn.init.xavier_uniform_(new[key])
            continue
        old = state[f"encoder.layers.{i // step}.{rest}"]
        if old.shape == value.shape:
            new[key] = old.clone()
        elif rest == "linear1.weight":  # [ff, d]: old rows, then fresh ones
            new[key] = torch.cat([old, value[old.shape[0]:]])
        elif rest == "linear1.bias":
            new[key] = torch.cat([old, torch.zeros(value.shape[0] - old.shape[0])])
        elif rest == "linear2.weight":  # [d, ff]: old columns, then zeros
            new[key] = torch.cat([old, torch.zeros(old.shape[0], value.shape[1] - old.shape[1])], 1)
        else:
            raise ValueError(f"grow: no rule for {key} {tuple(old.shape)} -> {tuple(value.shape)}")
    big.load_state_dict(new)
    return big


def atomic_write(path: str | os.PathLike, write: Callable[[str], None]) -> None:
    """``write(tmp)`` then rename over ``path``: a reader (a resume, a queue, distill) sees the
    old file or the whole new one, never a file cut short by a stop mid-write (SIGTERM, the
    memory floor's exit)."""
    tmp = f"{os.fspath(path)}.tmp"
    write(tmp)
    os.replace(tmp, path)


def save(path: str, model: PolicyValueNet, table: FT.CardTable, extra: dict | None = None) -> None:
    ck = {"config": model.config, "state": model.state_dict(), "table": table.to_json(),
          "extra": extra or {}}
    atomic_write(path, lambda tmp: torch.save(ck, tmp))


def upgraded(state: dict, model: nn.Module, prefix: str = "") -> dict:
    """A checkpoint's ``state`` (a PolicyValueNet's, under ``prefix`` inside ``model``: the
    simulator's ``view.``) in this code's shapes, the old network computing what it computed
    before."""
    state = dict(state)
    # ask kinds and option types appended since this checkpoint start as what they were encoded
    # as before: the ASK_GROWN_FROM kind or "other"
    for key, names, index, grown_from in (
            ("ask_emb.weight", FT.ASK_KINDS, FT.ASK_INDEX, FT.ASK_GROWN_FROM),
            ("opt_type.weight", FT.OPTION_TYPES, FT.OPT_INDEX, {})):
        w = state[prefix + key]
        grown = [w[index[grown_from.get(k, "other")]] for k in names[w.shape[0]:]]
        if grown:
            state[prefix + key] = torch.cat([w, torch.stack(grown)])
    # feature columns appended since this checkpoint (features.F_TARGETED, P_TARGETED, G_SLOT, G_TOP)
    # get zero weights: the old network reads them as absent and computes what it computed before
    for key, width in (("card_f.weight", FT.CF), ("player_f.weight", FT.PF),
                       ("glob_f.weight", FT.GF)):
        w = state[prefix + key]
        if w.shape[1] < width:
            state[prefix + key] = torch.cat([w, w.new_zeros(w.shape[0], width - w.shape[1])], dim=1)
    # pointer layers added since this checkpoint (features.C_SOURCE, C_TARGET) start at zero too;
    # so do the planner's layers on a network from without it (``load(..., planner=True)``): the
    # read-back adds nothing and the heads forecast uniformly, so it computes what it did
    for key, w in model.state_dict().items():
        if key.startswith(prefix) and key not in state and (
                key.endswith("_ptr.weight") or key.startswith(prefix + "plan_")):
            state[key] = torch.zeros_like(w)
    return state


def load(path: str, device: torch.device | str = "cpu",
         planner: bool = False) -> tuple[PolicyValueNet, FT.CardTable, dict]:
    """A checkpoint's network in eval mode, its card table and its extra. An older checkpoint's
    table rows are read as saved (before 2026-11-17 cut at 128 tokens: FT.CardTable). With
    ``planner`` a network saved without the planner becomes a planner network computing what it
    computed (``upgraded``); a planner network loads as one either way."""
    ck = torch.load(path, map_location="cpu", weights_only=False)
    table = FT.CardTable.from_json(ck["table"])
    cfg = dict(ck["config"])
    n_cards, n_ir = cfg.pop("n_cards"), cfg.pop("n_ir")
    cfg["planner"] = planner or cfg.get("planner", False)
    model = PolicyValueNet(n_cards, n_ir, table.ir_counts(), **cfg)
    model.load_state_dict(upgraded(ck["state"], model))
    return model.to(device).eval(), table, ck.get("extra", {})
