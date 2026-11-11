"""The opponent simulator (docs/PLAN_LEARNING.md §8, DECISIONS D20): a network trained only by
supervision on finished games to predict the opponent's hidden cards from what one seat may know.

Data. Capture games (``learner.py --capture``) wrap both seats in ``actor.Capture``: at sampled
decisions it records the seat's view (``features.sim_view``) and, apart, the truth (the
opponent's hand and library). They are saved as ``views_<k>.npz`` and ``truth_<k>.npz``; the
truth is only ever a training target.

Network. The policy network's input embedding and encoder (``model.PolicyValueNet.tokens``,
built here with its own size; its policy and value heads are unused) read the view. Two decoders
run in the same encoder as a prefix language model (decoder tokens see the view and the steps
before them):
- the hand as a sorted multiset, h steps (h is public): each step emits a vector scored by dot
  product against every card's embedding (name plus components); the product of the steps is the
  probability of the whole hand, so combinations are represented;
- the library contents given the hand, the same way (l steps). The order is not modelled: the
  next draws are random draws from the contents.
Only rules mask a step, never habits: the format's pool (the set's deckable cards), the copy
limit (``MAX_COPIES`` of a card that is not a basic land, counting the public copies), the sorted
order, and that the remaining steps still fit. So both are distributions over multisets
(test_simulator.py). A marginal head reads P(card in hand) and each card's expected library count.

Loss: the joint NLL of hand and library plus the marginal head's (binary cross-entropy, Poisson).

    .venv/bin/python -m tools.selfplay.simulator train --data DIR... --out CKPT
    .venv/bin/python -m tools.selfplay.simulator eval --data DIR... --ckpt CKPT --out FILE.npz
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torch.nn.functional as F
from torch import nn

from MTG_bot.core.executor.games import MAX_COPIES, get_supply
from tools.selfplay import features as FT
from tools.selfplay import model as M
from tools.selfplay.ppo import chunks

#: The pool every capture game deals from (the learner's --pool): the format's cards.
POOL = "verified"
#: A basic land's copies: no copy limit (CR 100.2a); any number above a library's size will do.
BASIC_CAP = 99
#: Parameters of the reused policy network that the simulator never reads.
UNUSED = ("view.policy_head", "view.value_head")
#: Held-out games: those whose seed is a multiple of this (E0's evaluation set).
HOLDOUT = 25
_POOLS: dict[tuple[int, str], tuple[np.ndarray, np.ndarray]] = {}


def pool_rows(table: FT.CardTable, set_code: str) -> tuple[np.ndarray, np.ndarray]:
    """The table rows of the set's dealt pool, and which of them are basic lands."""
    key = (id(table), set_code)
    if key not in _POOLS:
        supply = get_supply(POOL, set_code)
        pool = np.zeros(len(table.oracle_ids), bool)
        basic = np.zeros(len(table.oracle_ids), bool)
        for oid in supply.deckable:
            pool[table.row(oid)] = True
            basic[table.row(oid)] = supply.metas[oid].is_basic
        _POOLS[key] = (pool, basic)
    return _POOLS[key]


def _ragged(lists: list) -> tuple[np.ndarray, np.ndarray]:
    off = np.concatenate([[0], np.cumsum([len(x) for x in lists])]).astype(np.int64)
    flat = np.concatenate([np.asarray(x, np.int16) for x in lists]) if lists else np.zeros(0)
    return off, flat.astype(np.int16)


class Data:
    """Captured positions as flat arrays: the views (``model.Packed`` without options, the
    opponent's public cards and hidden-zone sizes, turn, seat, set, seed) and the truth (hand,
    lib: ragged rows). ``batch`` joins them for training and evaluation only."""

    TRUTH = ("hand_off", "hand", "lib_off", "lib")

    def __init__(self, a: dict[str, np.ndarray], table: FT.CardTable) -> None:
        self.a = a
        self.table = table
        self.views = M.Packed(**{k: a[k] for k in M.Packed.FIELDS})

    def __len__(self) -> int:
        return len(self.a["h"])

    @classmethod
    def from_records(cls, views: list[dict], truth: list, sets: list[str], table: FT.CardTable,
                     **meta: np.ndarray) -> Data:
        if any((len(t[0]), len(t[1])) != (v["h"], v["l"]) for v, t in zip(views, truth, strict=True)):
            raise ValueError("a label's size differs from the public size of its zone")
        none = {"opts_i": np.zeros((0, 4), np.int16), "opts_f": np.zeros((0, 2), np.float16)}
        packed = M.pack([{**v, **none} for v in views])
        a = {k: getattr(packed, k) for k in M.Packed.FIELDS}
        # no position has an option (o_off stays 0); one unread row keeps collate_packed's
        # padding index in range
        a["opts_i"], a["opts_f"] = np.zeros((1, 4), np.int16), np.zeros((1, 2), np.float16)
        a.update(set=np.array(sets), **{k: np.array([v[k] for v in views])
                                        for k in ("h", "l", "turn", "seat")})
        for name, lists in (("public", [v["public"] for v in views]), ("hand", [t[0] for t in truth]),
                            ("lib", [t[1] for t in truth])):
            a[name + "_off"], a[name] = _ragged(lists)
        return cls({**a, **meta}, table)

    def save(self, out: Path, k: int) -> None:
        np.savez(out / f"views_{k}.npz", **{n: v for n, v in self.a.items() if n not in self.TRUTH})
        np.savez(out / f"truth_{k}.npz", seed=self.a["seed"], **{n: self.a[n] for n in self.TRUTH})

    @classmethod
    def load(cls, dirs: list[str], table: FT.CardTable) -> Data:
        parts = []
        for d in dirs:
            for vf in sorted(Path(d).glob("views_*.npz"), key=lambda p: int(p.stem.split("_")[1])):
                v, t = dict(np.load(vf)), dict(np.load(vf.with_name("truth" + vf.name[5:])))
                if not np.array_equal(v["seed"], t.pop("seed")):
                    raise ValueError(f"{vf}: views and truth are not the same positions")
                parts.append({**v, **t})
        a = {}
        for k in parts[0]:
            if k.endswith("off"):  # offsets continue across shards
                base = np.cumsum([0] + [p[k][-1] for p in parts[:-1]])
                a[k] = np.concatenate([[0]] + [p[k][1:] + b for p, b in zip(parts, base, strict=True)])
            else:
                a[k] = np.concatenate([p[k] for p in parts])
        return cls(a, table)

    def lengths(self) -> np.ndarray:
        """Tokens per position (view and decoders): the minibatch sort key."""
        return np.diff(self.a["c_off"]) + self.a["h"] + self.a["l"] + 3

    def batch(self, idx: np.ndarray, device: Any) -> dict[str, torch.Tensor]:
        a = self.a
        idx = np.asarray(idx, np.int64)
        b = M.collate_packed(self.views, idx, device)
        cap = np.zeros((len(idx), len(self.table.oracle_ids)), np.int64)
        for s in np.unique(a["set"][idx]):
            pool, basic = pool_rows(self.table, str(s))
            cap[a["set"][idx] == s] = np.where(basic, BASIC_CAP, np.where(pool, MAX_COPIES, 0))
        out: dict[str, Any] = {"h": a["h"][idx], "l": a["l"][idx]}
        for name in ("public", "hand", "lib"):
            rows, mask = M._rows(a[name + "_off"], idx)
            flat = a[name] if len(a[name]) else np.zeros(1, np.int16)
            out[name] = np.where(mask, flat[rows], 0).astype(np.int64)
        pos, col = np.nonzero(out["public"])
        np.subtract.at(cap, (pos, out.pop("public")[pos, col]), 1)  # the public copies
        out["cap"] = cap.clip(min=0)
        b.update({k: torch.as_tensor(np.asarray(v, np.int64)).to(device) for k, v in out.items()})
        return b


def counts(seq: torch.Tensor, n: torch.Tensor, rows: int) -> torch.Tensor:
    """[B, rows] copies of each row in ``seq``'s first ``n`` entries."""
    real = torch.arange(seq.shape[1], device=seq.device)[None] < n[:, None]
    return torch.zeros(len(seq), rows, device=seq.device).scatter_add_(1, seq, real.float())


def allowed(seq: torch.Tensor, n: torch.Tensor, cap: torch.Tensor) -> torch.Tensor:
    """[B, T, rows]: what the rules allow at each step of placing the sorted multiset ``seq``
    (real for ``n`` steps; later steps allow everything): a row with copies left, not below the
    previous card, and only where the steps still to come fit (the copies left in this row and
    every row above it)."""
    t = seq.shape[1]
    one = F.one_hot(seq, cap.shape[1]).int()
    left = (cap[:, None] - (one.cumsum(1) - one)).clamp(min=0)
    room = left.flip(-1).cumsum(-1).flip(-1)
    need = n[:, None] - torch.arange(t, device=seq.device)[None]
    prev = F.pad(seq[:, :-1], (1, 0))
    rows = torch.arange(cap.shape[1], device=seq.device)
    return ((left > 0) & (room >= need[..., None]) & (rows >= prev[..., None])
            | (need <= 0)[..., None])


def seq_logp(logits: torch.Tensor, seq: torch.Tensor, n: torch.Tensor, cap: torch.Tensor) -> torch.Tensor:
    """log P of each sorted multiset ``seq`` under the step ``logits`` and the rules' masks."""
    lp = torch.log_softmax(logits.float().masked_fill(~allowed(seq, n, cap), float("-inf")), -1)
    lp = lp.gather(-1, seq[..., None]).squeeze(-1)
    real = torch.arange(seq.shape[1], device=seq.device)[None] < n[:, None]
    return torch.where(real, lp, 0.0).sum(1)


class Simulator(nn.Module):
    def __init__(self, table: FT.CardTable, d: int = 256, layers: int = 4, heads: int = 8,
                 ff: int = 1024) -> None:
        super().__init__()
        self.config = {"d": d, "layers": layers, "heads": heads, "ff": ff}
        self.view = M.build(table, d=d, layers=layers, heads=heads, ff=ff)
        self.step = nn.Embedding(4, d)  # start of the hand, of the library; a hand, a library step
        self.left = nn.Linear(1, d)  # cards still to place (this one included) / 10
        self.hand_q = nn.Linear(d, d)
        self.lib_q = nn.Linear(d, d)
        self.marg = nn.Linear(d, 2 * d)  # P(card in hand), expected library count
        self.marg_bias = nn.Parameter(torch.zeros(2))
        for name, m in self.named_modules():  # the policy network's own initialisation
            if not name.startswith("view") and isinstance(m, (nn.Linear, nn.Embedding)):
                nn.init.normal_(m.weight, std=0.02)

    def cards(self) -> torch.Tensor:
        """Every table row's embedding: name plus components."""
        return self.view.name_emb.weight + self.view.card_table_emb()

    def _inputs(self, cards: torch.Tensor, seq: torch.Tensor, n: torch.Tensor, which: int) -> torch.Tensor:
        """A step's input: the card placed before it (a start token first) and the cards left."""
        left = (n[:, None] - torch.arange(seq.shape[1], device=seq.device)[None]).float()
        prev = torch.cat([self.step.weight[which].expand(len(seq), 1, -1), cards[seq[:, :-1]]], 1)
        return prev + self.step.weight[2 + which] + self.left(left[..., None] / 10)

    def run(self, b: dict[str, torch.Tensor], blocks: list[tuple]) -> tuple[torch.Tensor, int, torch.Tensor]:
        """Encode the view and the decoder ``blocks`` [(seq, n, which)]: (states, view length, cards)."""
        v = self.view
        cards = self.cards()
        x, valid = v.tokens(b)
        p = x.shape[1]
        pads = [torch.arange(s.shape[1], device=s.device)[None] >= n[:, None] for s, n, _ in blocks]
        x = torch.cat([x] + [self._inputs(cards, s, n, w) for s, n, w in blocks], 1)
        ar = torch.arange(x.shape[1], device=x.device)
        causal = (ar[None] > ar[:, None]) & (ar[None] >= p)  # decoder steps see only earlier ones
        o = v.encoder(v.in_norm(x), mask=causal, src_key_padding_mask=torch.cat([~valid] + pads, 1))
        return v.out_norm(o), p, cards

    def forward(self, b: dict[str, torch.Tensor]) -> tuple[torch.Tensor, ...]:
        """(log P(hand), log P(library | hand), P(card in hand) logits, expected library counts)."""
        hand, lib, h, l, cap = b["hand"], b["lib"], b["h"], b["l"], b["cap"]
        o, p, cards = self.run(b, [(hand, h, 0), (lib, l, 1)])
        th = hand.shape[1]
        hand_lp = seq_logp(self.hand_q(o[:, p:p + th]) @ cards.T, hand, h, cap)
        lib_cap = cap - counts(hand, h, cap.shape[1]).long()
        lib_lp = seq_logp(self.lib_q(o[:, p + th:]) @ cards.T, lib, l, lib_cap)
        mh, ml = self.marg(o[:, 0]).chunk(2, -1)
        ok = cap > 0
        marg = (mh @ cards.T + self.marg_bias[0]).float().masked_fill(~ok, float("-inf"))
        rate = F.softplus((ml @ cards.T + self.marg_bias[1]).float()) * ok
        return hand_lp, lib_lp, marg, rate

    @torch.no_grad()
    def sample_hands(self, b: dict[str, torch.Tensor]) -> torch.Tensor:
        """One hand per position, drawn step by step from the hand decoder."""
        h, cap = b["h"], b["cap"]
        hand = torch.zeros(len(h), max(1, int(h.max())), dtype=torch.long, device=h.device)
        for t in range(hand.shape[1]):
            o, p, cards = self.run(b, [(hand, h, 0)])
            logits = (self.hand_q(o[:, p + t]) @ cards.T).float()
            logits = logits.masked_fill(~allowed(hand, h, cap)[:, t], float("-inf"))
            pick = torch.multinomial(torch.softmax(logits, -1), 1)[:, 0]
            hand[:, t] = torch.where(h > t, pick, 0)
        return hand

    @torch.no_grad()
    def sample_worlds(self, b: dict[str, torch.Tensor]) -> tuple[torch.Tensor, torch.Tensor]:
        """One hidden state per position, for the search's ``sim`` worlds (PLAN_CEILING §3.2):
        a whole hand from the hand decoder, so combinations keep their joint probability, and the
        library's contents drawn card by card in proportion to the marginal head's expected
        counts, within the copies the rules leave. E0 found the library decoder no better than
        the prior, so the cheap head serves. Table rows, [B, max h] and [B, max l]."""
        hand = self.sample_hands(b)
        o, _, cards = self.run(b, [])  # view tokens never see the decoder's
        rate = F.softplus((self.marg(o[:, 0]).chunk(2, -1)[1] @ cards.T
                           + self.marg_bias[1]).float())
        h, n, cap = b["h"], b["l"], b["cap"]
        left = cap - counts(hand, h, cap.shape[1]).long()
        lib = torch.zeros(len(n), max(1, int(n.max())), dtype=torch.long, device=n.device)
        for t in range(lib.shape[1]):
            w = rate * (left > 0)
            w = torch.where(w.sum(-1, keepdim=True) > 0, w, (cap > 0).float())  # no copies left
            pick = torch.multinomial(w, 1)[:, 0]
            real = n > t
            lib[:, t] = torch.where(real, pick, 0)
            left = left - F.one_hot(pick, cap.shape[1]) * real[:, None]
        return hand, lib


def load(path: str, device: Any = "cpu") -> tuple[Simulator, FT.CardTable]:
    """A trained simulator (``train``'s checkpoint), in evaluation mode, and its card table."""
    ck = torch.load(path, map_location="cpu", weights_only=False)
    table = FT.CardTable.from_json(ck["table"])
    net = Simulator(table, **ck["config"]).to(device).eval()
    net.load_state_dict(ck["state"])
    return net, table


def sample_for_views(net: Simulator, table: FT.CardTable, views: list[dict], sets: list[str],
                     k: list[int], device: Any) -> list[list[tuple[list[str], list[str]]]]:
    """For each seat's view (``features.sim_view``) and set, ``k`` hidden states of the
    opponent drawn by ``net``: (hand, library) lists of oracle ids, sized as the view says."""
    rows = [j for j, kj in enumerate(k) for _ in range(kj)]
    vs = [views[j] for j in rows]
    data = Data.from_records(vs, [([0] * v["h"], [0] * v["l"]) for v in vs],
                             [sets[j] for j in rows], table)
    hand, lib = net.sample_worlds(data.batch(np.arange(len(vs)), device))
    hand, lib = hand.cpu().numpy(), lib.cpu().numpy()
    ids = table.oracle_ids
    out: list[list] = [[] for _ in views]
    for r, j in enumerate(rows):
        out[j].append(([ids[x] for x in hand[r, :vs[r]["h"]]], [ids[x] for x in lib[r, :vs[r]["l"]]]))
    return out


def loss(net: Simulator, b: dict[str, torch.Tensor]) -> torch.Tensor:
    """Per position: the joint NLL of hand and library plus the marginal head's losses."""
    hand_lp, lib_lp, marg, rate = net(b)
    ok = b["cap"] > 0
    rows = ok.shape[1]
    in_hand = counts(b["hand"], b["h"], rows) > 0
    lib_n = counts(b["lib"], b["l"], rows)
    bce = F.binary_cross_entropy_with_logits(marg[ok], in_hand[ok].float(), reduction="sum")
    poisson = (rate - lib_n * torch.log(rate.clamp(min=1e-8)))[ok].sum()
    return (bce + poisson - (hand_lp + lib_lp).sum()) / len(hand_lp)


def held_out(seed: np.ndarray) -> np.ndarray:
    return seed % HOLDOUT == 0


def train(a: argparse.Namespace) -> None:
    table = FT.CardTable.from_json(json.loads((Path(a.data[0]) / "table.json").read_text()))
    data = Data.load(a.data, table)
    idx = np.flatnonzero(~held_out(data.a["seed"]))
    if a.positions:
        idx = np.random.default_rng(a.seed).permutation(idx)[: a.positions]
    dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    torch.manual_seed(a.seed)
    np.random.seed(a.seed)
    random.seed(a.seed)
    net = Simulator(table, d=a.d, layers=a.layers, heads=a.heads, ff=a.ff).to(dev)
    opt = torch.optim.AdamW(net.parameters(), lr=a.lr, weight_decay=a.wd)
    lengths = data.lengths()[idx]
    total = a.epochs * len(chunks(lengths, a.mb, a.tok_budget))
    sched = torch.optim.lr_scheduler.LambdaLR(opt, lambda s: min(1.0, (s + 1) / 200) * (
        0.05 + 0.95 * 0.5 * (1 + math.cos(math.pi * min(1.0, s / total)))))
    print(json.dumps({**vars(a), "positions": len(idx), "steps": total, "params": sum(
        p.numel() for p in net.parameters())}), flush=True)
    for epoch in range(a.epochs):
        net.train()
        t0, ls = time.time(), []
        for ch in chunks(lengths, a.mb, a.tok_budget):
            b = data.batch(idx[ch], dev)
            with torch.autocast(dev.type, dtype=torch.bfloat16, enabled=dev.type == "cuda"):
                lo = loss(net, b)
            opt.zero_grad(set_to_none=True)
            lo.backward()
            torch.nn.utils.clip_grad_norm_(net.parameters(), 1.0)
            opt.step()
            sched.step()
            ls.append(lo.item())
            if len(ls) % 500 == 0:
                print(json.dumps({"epoch": epoch, "step": len(ls), "loss": round(float(
                    np.mean(ls[-500:])), 4), "secs": round(time.time() - t0, 1)}), flush=True)
        torch.save({"config": net.config, "state": net.state_dict(), "table": table.to_json(),
                    "epoch": epoch}, a.out)
        print(json.dumps({"epoch": epoch, "loss": round(float(np.mean(ls)), 4),
                          "secs": round(time.time() - t0, 1)}), flush=True)


@torch.no_grad()
def evaluate(a: argparse.Namespace) -> None:
    """Every held-out position's hand and library NLL, and every (position, pool card) pair's
    P(card in hand), to ``--out``."""
    dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    net, table = load(a.ckpt, dev)
    data = Data.load(a.data, table)
    idx = np.flatnonzero(held_out(data.a["seed"]))
    rows: dict[str, list] = {k: [] for k in ("sim_hand", "sim_lib", "uniform_hand")}
    pairs: dict[str, list] = {k: [] for k in ("pos", "card", "p_sim", "y")}
    for ch in np.array_split(idx, max(1, len(idx) // a.mb)):
        b = data.batch(ch, dev)
        hand_lp, lib_lp, marg, _ = net(b)
        rows["sim_hand"] += (-hand_lp).tolist()
        rows["sim_lib"] += (-lib_lp).tolist()
        cap, hand = b["cap"].cpu().numpy(), b["hand"].cpu().numpy()
        p_sim = torch.sigmoid(marg).cpu().numpy()
        for j, i in enumerate(ch):
            rows["uniform_hand"].append(uniform_hand_nll(
                hand[j, :data.a["h"][i]], int(pool_rows(table, str(data.a["set"][i]))[0].sum())))
            cand = np.flatnonzero(cap[j] > 0)
            pairs["pos"].append(np.full(len(cand), i))
            pairs["card"].append(cand)
            pairs["p_sim"].append(p_sim[j, cand])
            pairs["y"].append(np.isin(cand, hand[j, :data.a["h"][i]]))
    out = {k: np.array(v) for k, v in rows.items()}
    out.update({k: np.concatenate(v) for k, v in pairs.items()})
    out.update({k: data.a[k][idx] for k in ("seed", "turn", "h", "l", "set", "seat", "net")
                if k in data.a})
    np.savez(a.out, idx=idx, **out)
    print(json.dumps({"positions": len(idx), **{k: round(float(v.mean()), 4)
                                                 for k, v in out.items() if k in rows},
                      "hand_vs_uniform": round(float(out["sim_hand"].mean()
                                                     / out["uniform_hand"].mean()), 4),
                      "ece": round(ece(out["p_sim"], out["y"]), 5)}))


def uniform_hand_nll(hand: np.ndarray, pool: int) -> float:
    """-log P of a hand (a multiset of table rows) when every hidden card is drawn uniformly
    from the ``pool`` deckable cards, as the search's ``uniform`` worlds draw them."""
    counts = np.unique(hand, return_counts=True)[1]
    return len(hand) * math.log(pool) - math.lgamma(len(hand) + 1) + sum(
        math.lgamma(c + 1) for c in counts)


def ece(p: np.ndarray, y: np.ndarray, bins: int = 15) -> float:
    """Expected calibration error over equal-mass bins of the predicted probabilities."""
    order = np.argsort(p)
    err = 0.0
    for part in np.array_split(order, bins):
        if len(part):
            err += len(part) * abs(float(p[part].mean()) - float(y[part].mean()))
    return err / max(len(p), 1)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("cmd", choices=("train", "eval"))
    p.add_argument("--data", nargs="+", required=True, help="capture directories")
    p.add_argument("--out", required=True)
    p.add_argument("--ckpt", default="")
    p.add_argument("--positions", type=int, default=0, help="train on this many (0: all)")
    p.add_argument("--d", type=int, default=256)
    p.add_argument("--layers", type=int, default=4)
    p.add_argument("--heads", type=int, default=8)
    p.add_argument("--ff", type=int, default=1024)
    p.add_argument("--epochs", type=int, default=4)
    p.add_argument("--lr", type=float, default=1e-3)  # E0 chose it on its pilot (186 §2)
    p.add_argument("--wd", type=float, default=0.01)
    p.add_argument("--mb", type=int, default=512)
    p.add_argument("--tok-budget", type=int, default=131072)
    p.add_argument("--seed", type=int, default=1)
    a = p.parse_args(argv)
    (train if a.cmd == "train" else evaluate)(a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
